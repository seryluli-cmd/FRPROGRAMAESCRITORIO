"""
pedidos_clientes_repo.py
=========================
PEDIDOS DE CLIENTES (pedido del dueño, 2026-11-03): mercadería que NO tenemos y
que los clientes vienen a buscar. La empleada escribe "Mantecol" y GUARDAR, y
queda "1 cliente pidió Mantecol". Si otro cliente lo vuelve a pedir, a cualquier
empleada, se suma en el MISMO renglón: 2 clientes. Así el dueño ve qué conviene
traer, lo más pedido arriba.

Reglas:

- Lo escrito se compara sin mayúsculas, tildes ni espacios de más
  (dominio.clave_pedido_cliente): "mantecol", "MANTECOL " y "Mantecól" son el
  mismo. El renglón se ve como lo escribió quien lo anotó primero.
- Se suma un cliente de tres formas, y las tres pasan por acá: escribirlo de nuevo
  (anotar), tocar uno de los parecidos que salen mientras se escribe o el +1 del
  renglón (sumar_uno con su número).
- Cada cliente es una fila de pedidos_clientes_veces con su fecha y hora y el
  operador que estaba en el mostrador. La cantidad de clientes es cuántas filas
  hay: no se guarda aparte, así nunca queda un número que no coincide.
- Anotar, sumar y "YA LO TRAJIMOS" exigen que quien opera siga habilitado
  (usuarios_repo.usuario_habilitado): una usuaria dada de baja con la sesión
  abierta no sigue anotando, y nunca queda un renglón traído sin saber quién.
- "YA LO TRAJIMOS" lo puede apretar cualquiera: el renglón sale de la lista y pasa
  al historial con quién y cuándo. Si después lo vuelven a pedir, arranca un
  renglón NUEVO con 1 (lo de antes ya se resolvió trayéndolo). Nunca hay dos
  pendientes del mismo producto: lo cuida además un índice único de la base.
- Corregir la lista es solo del Administrador, como las marcas: Renombrar (si el
  nombre nuevo es otro pendiente, se usa Juntar), Juntar (dos renglones que son lo
  mismo escrito distinto: los clientes de uno pasan al otro) y Borrar (anotado por
  error). Nada se borra de la base (regla 7): queda BORRADO con quién y cuándo.

Esto no tiene nada que ver con pedidos_impresion_repo (Gestión Impresiones, con
seña): acá no hay plata ni artículos.
"""

from datetime import datetime

import dominio
from database import conexion_db
from repositories import usuarios_repo


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


# Cada renglón con sus clientes contados, la primera y la última vez que lo
# pidieron y quién anotó la última. La primera vez sale de las veces y no de
# pedidos_clientes.fecha: después de Juntar, la más vieja puede ser del otro.
# Se completa con un WHERE sobre `p` y su ORDER BY.
_SELECT_CON_CLIENTES = """
    SELECT p.id, p.producto, p.clave, p.estado, p.fecha,
           p.traido_por, p.fecha_traido, traido.nombre AS traido_por_nombre,
           COUNT(v.id) AS clientes,
           MIN(v.fecha) AS primera_vez,
           MAX(v.fecha) AS ultima_vez,
           (SELECT quien.nombre
            FROM pedidos_clientes_veces AS ultima
            JOIN usuarios AS quien ON quien.id = ultima.usuario_id
            WHERE ultima.pedido_id = p.id
            ORDER BY ultima.fecha DESC, ultima.id DESC
            LIMIT 1) AS ultima_vez_por
    FROM pedidos_clientes AS p
    LEFT JOIN pedidos_clientes_veces AS v ON v.pedido_id = p.id
    LEFT JOIN usuarios AS traido ON traido.id = p.traido_por
"""

# Lo más pedido arriba; entre dos con los mismos clientes, el que pidieron último.
# MAX(v.id) desempata dos veces anotadas en el mismo segundo.
_ORDEN_DE_LA_LISTA = "ORDER BY clientes DESC, ultima_vez DESC, MAX(v.id) DESC"


def listar_pendientes():
    """Los productos que piden y todavía no trajimos, lo más pedido arriba. Cada
    renglón trae `producto`, `clientes`, `primera_vez`, `ultima_vez` y
    `ultima_vez_por` (el nombre de quién anotó la última)."""
    with conexion_db() as conexion:
        return conexion.execute(
            f"{_SELECT_CON_CLIENTES} WHERE p.estado = ? GROUP BY p.id {_ORDEN_DE_LA_LISTA}",
            (dominio.PEDIDO_CLIENTE_PENDIENTE,),
        ).fetchall()


def parecidos(texto: str, limite: int = 5):
    """
    Los pendientes que se parecen a lo que se está escribiendo (su clave contiene
    la de lo escrito: "mante" encuentra "Mantecol"), lo más pedido arriba, para
    tocar uno y sumarle el cliente en vez de escribirlo entero. Con menos de
    dominio.LETRAS_MINIMAS_PARECIDOS letras, ninguno: con una sola saldría casi
    toda la lista.
    """
    clave = dominio.clave_pedido_cliente(texto)
    if len(clave.replace(" ", "")) < dominio.LETRAS_MINIMAS_PARECIDOS or limite < 1:
        return []
    # instr y no LIKE: lo escrito puede traer un % o un _, que LIKE tomaría como
    # comodín. Las dos claves ya están en minúsculas y sin tildes.
    with conexion_db() as conexion:
        return conexion.execute(
            f"{_SELECT_CON_CLIENTES} WHERE p.estado = ? AND instr(p.clave, ?) > 0 "
            f"GROUP BY p.id {_ORDEN_DE_LA_LISTA} LIMIT ?",
            (dominio.PEDIDO_CLIENTE_PENDIENTE, clave, int(limite)),
        ).fetchall()


def listar_historial():
    """Lo que ya trajimos, el último que se marcó primero: cada renglón con sus
    `clientes`, quién apretó "YA LO TRAJIMOS" (`traido_por_nombre`) y cuándo
    (`fecha_traido`)."""
    with conexion_db() as conexion:
        return conexion.execute(
            f"{_SELECT_CON_CLIENTES} WHERE p.estado = ? GROUP BY p.id ORDER BY p.fecha_traido DESC, p.id DESC",
            (dominio.PEDIDO_CLIENTE_TRAIDO,),
        ).fetchall()


def _leer_pedido(conexion, pedido_id: int):
    pedido = conexion.execute("SELECT * FROM pedidos_clientes WHERE id = ?", (pedido_id,)).fetchone()
    if pedido is None:
        raise ValueError("Ese pedido no existe: cerrá y volvé a abrir Pedidos de Clientes.")
    return pedido


def _exigir_pendiente(pedido, para: str):
    """ValueError si el renglón ya no está en la lista (otra empleada pudo haberlo
    marcado como traído mientras tanto)."""
    if pedido["estado"] == dominio.PEDIDO_CLIENTE_TRAIDO:
        raise ValueError(
            f'"{pedido["producto"]}" ya está marcado como traído: no se puede {para}. '
            "Si lo vuelven a pedir, anotalo de nuevo y arranca otra vez en 1."
        )
    if pedido["estado"] != dominio.PEDIDO_CLIENTE_PENDIENTE:
        raise ValueError(f'"{pedido["producto"]}" ya no está en la lista: no se puede {para}.')


def _pendiente_con_clave(conexion, clave: str, salvo_id: int = None):
    """El renglón pendiente con esa clave (hay uno o ninguno), sin contar `salvo_id`."""
    return conexion.execute(
        "SELECT * FROM pedidos_clientes WHERE clave = ? AND estado = ? AND id IS NOT ?",
        (clave, dominio.PEDIDO_CLIENTE_PENDIENTE, salvo_id),
    ).fetchone()


def _sumar_un_cliente(conexion, pedido_id: int, usuario_id: int):
    conexion.execute(
        "INSERT INTO pedidos_clientes_veces (pedido_id, fecha, usuario_id) VALUES (?, ?, ?)",
        (pedido_id, _ahora(), usuario_id),
    )


def _clientes(conexion, pedido_id: int) -> int:
    return conexion.execute(
        "SELECT COUNT(*) FROM pedidos_clientes_veces WHERE pedido_id = ?", (pedido_id,)
    ).fetchone()[0]


def anotar(usuario_id: int, texto: str) -> dict:
    """
    Un cliente pidió `texto`: si ya hay un pendiente con la misma clave le suma
    este cliente; si no, abre un renglón nuevo con 1. `usuario_id` es quien está
    en el mostrador. Devuelve {"pedido_id", "producto" (como se ve en la lista),
    "clientes" (cuántos lo pidieron, con este), "nuevo" (si abrió el renglón)}.
    ValueError si está vacío o es demasiado largo.
    """
    usuarios_repo.usuario_habilitado(usuario_id)
    producto, clave = dominio.revisar_pedido_cliente(texto)
    with conexion_db() as conexion:
        # Con el permiso de escritura tomado antes de buscar: si dos lo anotan a la
        # vez (una desde otra PC), el segundo espera y suma en el renglón del
        # primero en vez de chocar con el índice único.
        conexion.execute("BEGIN IMMEDIATE")
        pedido = _pendiente_con_clave(conexion, clave)
        nuevo = pedido is None
        if nuevo:
            pedido_id = conexion.execute(
                "INSERT INTO pedidos_clientes (fecha, producto, clave, creado_por, estado) VALUES (?, ?, ?, ?, ?)",
                (_ahora(), producto, clave, usuario_id, dominio.PEDIDO_CLIENTE_PENDIENTE),
            ).lastrowid
        else:
            pedido_id, producto = pedido["id"], pedido["producto"]
        _sumar_un_cliente(conexion, pedido_id, usuario_id)
        return {"pedido_id": pedido_id, "producto": producto,
                "clientes": _clientes(conexion, pedido_id), "nuevo": nuevo}


def sumar_uno(usuario_id: int, pedido_id: int) -> int:
    """Otro cliente pidió ese renglón (el +1 o uno de los parecidos): lo suma con la
    fecha y hora y quién lo anotó, y devuelve cuántos clientes lo pidieron. Solo a
    uno pendiente."""
    usuarios_repo.usuario_habilitado(usuario_id)
    with conexion_db() as conexion:
        conexion.execute("BEGIN IMMEDIATE")
        _exigir_pendiente(_leer_pedido(conexion, pedido_id), "sumarle un cliente")
        _sumar_un_cliente(conexion, pedido_id, usuario_id)
        return _clientes(conexion, pedido_id)


def ya_lo_trajimos(usuario_id: int, pedido_id: int):
    """El producto ya está en el kiosko: sale de la lista de pendientes y queda en el
    historial con quién lo marcó y cuándo. Lo puede hacer cualquier operador."""
    usuarios_repo.usuario_habilitado(usuario_id)
    with conexion_db() as conexion:
        conexion.execute("BEGIN IMMEDIATE")
        _exigir_pendiente(_leer_pedido(conexion, pedido_id), "marcarlo como traído")
        conexion.execute(
            "UPDATE pedidos_clientes SET estado = ?, traido_por = ?, fecha_traido = ? WHERE id = ?",
            (dominio.PEDIDO_CLIENTE_TRAIDO, usuario_id, _ahora(), pedido_id),
        )


# ---------------------------------------------------------------------
# Correcciones: solo el Administrador (como Gestionar Marcas)
# ---------------------------------------------------------------------

_PARA_CORREGIR = "corregir los pedidos de clientes"


def renombrar(usuario_id: int, pedido_id: int, nuevo: str):
    """Le corrige el nombre a un renglón pendiente ("mantecool" → "Mantecol"). Si el
    nombre nuevo es el de OTRO pendiente, ValueError: para unirlos está juntar(),
    que no pierde los clientes de ninguno."""
    usuarios_repo.exigir_admin(usuario_id, _PARA_CORREGIR)
    producto, clave = dominio.revisar_pedido_cliente(nuevo)
    with conexion_db() as conexion:
        conexion.execute("BEGIN IMMEDIATE")
        _exigir_pendiente(_leer_pedido(conexion, pedido_id), "cambiarle el nombre")
        otro = _pendiente_con_clave(conexion, clave, salvo_id=pedido_id)
        if otro is not None:
            raise ValueError(
                f'Ya hay otro pedido que se llama "{otro["producto"]}". Si son el mismo producto, '
                "usá Juntar: así se suman los clientes de los dos."
            )
        conexion.execute(
            "UPDATE pedidos_clientes SET producto = ?, clave = ? WHERE id = ?", (producto, clave, pedido_id)
        )


def juntar(usuario_id: int, origen_id: int, destino_id: int) -> int:
    """
    Dos renglones pendientes que son el mismo producto escrito distinto ("Mantecol"
    y "Mantecol grande", por ejemplo): todos los clientes de `origen_id` pasan a
    `destino_id`, con su fecha y quién los anotó, y el origen queda BORRADO con
    `juntado_con` apuntando al destino. Todo junto. Devuelve cuántos clientes tiene
    el destino después de juntarlos.
    """
    usuarios_repo.exigir_admin(usuario_id, _PARA_CORREGIR)
    with conexion_db() as conexion:
        conexion.execute("BEGIN IMMEDIATE")
        origen = _leer_pedido(conexion, origen_id)
        destino = _leer_pedido(conexion, destino_id)
        # Con los números que dio la base y no con los que llegaron: 5 y "5" son
        # distintos para Python pero el mismo renglón para SQLite, y juntarlo
        # consigo mismo lo dejaría BORRADO con todos sus clientes adentro.
        origen_id, destino_id = origen["id"], destino["id"]
        if origen_id == destino_id:
            raise ValueError("Es el mismo pedido: elegí otro para juntarlos.")
        _exigir_pendiente(origen, "juntarlo con otro")
        _exigir_pendiente(destino, "juntarle otro")
        conexion.execute(
            "UPDATE pedidos_clientes_veces SET pedido_id = ? WHERE pedido_id = ?", (destino_id, origen_id)
        )
        conexion.execute(
            "UPDATE pedidos_clientes SET estado = ?, borrado_por = ?, fecha_borrado = ?, juntado_con = ? WHERE id = ?",
            (dominio.PEDIDO_CLIENTE_BORRADO, usuario_id, _ahora(), destino_id, origen_id),
        )
        return _clientes(conexion, destino_id)


def borrar(usuario_id: int, pedido_id: int):
    """Un renglón anotado por error: sale de la lista (y del historial, si ya estaba
    ahí) pero la fila queda, BORRADO con quién y cuándo (regla 7: nada se borra de
    verdad)."""
    usuarios_repo.exigir_admin(usuario_id, _PARA_CORREGIR)
    with conexion_db() as conexion:
        conexion.execute("BEGIN IMMEDIATE")
        pedido = _leer_pedido(conexion, pedido_id)
        if pedido["estado"] == dominio.PEDIDO_CLIENTE_BORRADO:
            raise ValueError(f'"{pedido["producto"]}" ya estaba borrado.')
        conexion.execute(
            "UPDATE pedidos_clientes SET estado = ?, borrado_por = ?, fecha_borrado = ? WHERE id = ?",
            (dominio.PEDIDO_CLIENTE_BORRADO, usuario_id, _ahora(), pedido_id),
        )
