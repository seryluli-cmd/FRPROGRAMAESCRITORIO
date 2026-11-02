"""
pedidos_impresion_repo.py
==========================
GESTIÓN IMPRESIONES (pedido del dueño, 2026-11-02): un cliente encarga muchas
impresiones (100 hojas, por ejemplo), deja una seña o lo paga entero, y lo retira
después pagando lo que falta.

La plata va por las ventas de kiosko de siempre (ventas_repo._grabar_venta_kiosko),
así Caja, Cierre de Turno, Reportes, el Detalle del Día y las cajas con número la
cuentan sin saber de pedidos:

- Al tomarlo: una venta con UN renglón del artículo Impresiones, "SEÑA DE
  IMPRESIONES", 1 x la seña. Queda en la caja abierta en ese momento, la de quien
  tomó el pedido (con el Admin, la regla de siempre: cajas_repo._quien_vende).
- Al retirarlo: una venta con las hojas a su precio (Impresiones, hojas x precio) y
  la seña descontada (misma descripción, -1 x la seña). Suma justo lo que falta y
  queda en la caja de quien entrega. Si lo pagó entero, la venta da $ 0.

Así cada peso entra una sola vez, en la caja donde entró de verdad, siempre como
Impresiones (Caja separa por el artículo); y las hojas se cuentan una sola vez, el
día que se retiran (los dos renglones de seña se compensan en los reportes).

Una seña perdida (no vino nunca) no mueve plata: ya estaba en la caja y queda para
el local. Anular un pedido mal cargado anula sus ventas (solo el Administrador, con
motivo, como anular una venta); esas ventas no se anulan sueltas desde Consulta de
Ventas (ventas_repo.anular_venta lo rechaza).
"""

from datetime import datetime

import dominio
from database import conexion_db
from repositories import impresiones_repo, usuarios_repo, ventas_repo


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def listar_pedidos():
    """Todos los pedidos, el último primero, con el nombre de quién lo tomó y de
    quién lo entregó (son pocos: la pantalla filtra y busca sobre esta lista)."""
    with conexion_db() as conexion:
        return conexion.execute(
            """
            SELECT pedidos_impresion.*,
                   tomo.nombre AS tomado_por_nombre,
                   entrego.nombre AS entregado_por_nombre
            FROM pedidos_impresion
            JOIN usuarios AS tomo ON tomo.id = pedidos_impresion.tomado_por
            LEFT JOIN usuarios AS entrego ON entrego.id = pedidos_impresion.entregado_por
            ORDER BY pedidos_impresion.id DESC
            """
        ).fetchall()


def _leer_pedido(conexion, pedido_id: int):
    pedido = conexion.execute("SELECT * FROM pedidos_impresion WHERE id = ?", (pedido_id,)).fetchone()
    if pedido is None:
        raise ValueError("Ese pedido no existe.")
    return pedido


def _exigir_pendiente(pedido, para: str):
    if pedido["estado"] != dominio.PEDIDO_PENDIENTE:
        raise ValueError(f"El pedido Nº {pedido['id']} está {pedido['estado']}: no se puede {para}.")


def _articulo_con_precio(conexion):
    """El artículo Impresiones, que tiene que estar cargado y con precio."""
    articulo = impresiones_repo._leer_articulo(conexion)
    if articulo is None:
        raise ValueError(impresiones_repo.mensaje_sin_articulo())
    if articulo["precio_venta"] <= 0:
        raise ValueError(
            "Las impresiones no tienen precio cargado. Un encargado lo tiene que poner en "
            "Admin Kiosko > Artículos."
        )
    return articulo


def tomar_pedido(usuario_id: int, nombre: str, telefono: str, hojas: int, precio_hoja: float,
                 sena: float, pagos: list) -> int:
    """
    Graba un pedido nuevo con su seña y devuelve su número. `usuario_id` es quien
    está en el mostrador: queda como quien tomó el pedido. `pagos` son los de la
    ventana de cobro (netos de vuelto) y tienen que sumar la seña.

    `precio_hoja` es el que vio quien atiende: si alguien cambió el precio de
    Impresiones mientras tanto, no se graba (como en impresiones_repo.cobrar_impresiones).
    Pedido y venta de la seña van en la misma transacción.
    """
    nombre = " ".join((nombre or "").split())
    if not nombre:
        raise ValueError("Escribí a nombre de quién es el pedido.")
    telefono = dominio.telefono_limpio(telefono)
    if not isinstance(hojas, int) or hojas < 1:
        raise ValueError("Escribí cuántas hojas son (al menos 1).")
    if hojas > dominio.HOJAS_MAXIMAS_POR_PEDIDO:
        raise ValueError(f"Son más de {dominio.HOJAS_MAXIMAS_POR_PEDIDO} hojas: revisá la cantidad.")

    with conexion_db() as conexion:
        articulo = _articulo_con_precio(conexion)
        if round(articulo["precio_venta"], 2) != round(precio_hoja, 2):
            raise ValueError(
                "El precio de las impresiones cambió mientras tomabas el pedido. No se grabó nada: "
                "volvé a abrir Gestión Impresiones."
            )
        total = dominio.total_del_pedido(hojas, articulo["precio_venta"])
        sena = round(sena, 2)
        dominio.revisar_sena(total, sena)

        venta_id = ventas_repo._grabar_venta_kiosko(conexion, usuario_id, [{
            "codigo": articulo["codigo"],
            "descripcion": dominio.DESCRIPCION_SENA_IMPRESIONES,
            "cantidad": 1,
            "precio_unitario": sena,
        }], pagos)
        cursor = conexion.execute(
            """
            INSERT INTO pedidos_impresion
                (fecha, nombre, telefono, hojas, precio_hoja, total, sena, tomado_por, venta_sena_id, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_ahora(), nombre, telefono, hojas, round(articulo["precio_venta"], 2), total, sena,
             usuario_id, venta_id, dominio.PEDIDO_PENDIENTE),
        )
        return cursor.lastrowid


def entregar_pedido(usuario_id: int, pedido_id: int, pagos: list) -> int:
    """
    El cliente retira el pedido: graba la venta de lo que faltaba (las hojas a su
    precio menos la seña) y deja anotado quién lo entregó y cuándo. Devuelve el
    número de esa venta. `pagos` tienen que sumar lo que falta (ninguno, si lo
    había pagado entero).
    """
    with conexion_db() as conexion:
        pedido = _leer_pedido(conexion, pedido_id)
        _exigir_pendiente(pedido, "entregar")
        articulo = impresiones_repo._leer_articulo(conexion)
        if articulo is None:
            raise ValueError(impresiones_repo.mensaje_sin_articulo())
        venta_id = ventas_repo._grabar_venta_kiosko(conexion, usuario_id, [
            {"codigo": articulo["codigo"], "descripcion": articulo["descripcion"],
             "cantidad": pedido["hojas"], "precio_unitario": pedido["precio_hoja"]},
            {"codigo": articulo["codigo"], "descripcion": dominio.DESCRIPCION_SENA_IMPRESIONES,
             "cantidad": -1, "precio_unitario": pedido["sena"]},
        ], pagos)
        conexion.execute(
            """
            UPDATE pedidos_impresion
            SET estado = ?, entregado_por = ?, fecha_entrega = ?, venta_entrega_id = ?
            WHERE id = ?
            """,
            (dominio.PEDIDO_RETIRADO, usuario_id, _ahora(), venta_id, pedido_id),
        )
        return venta_id


def anotar_aviso(pedido_id: int):
    """Anota que se le abrió al cliente el WhatsApp de "ya está listo" (la lista
    muestra cuándo, para no avisarle dos veces sin querer)."""
    with conexion_db() as conexion:
        pedido = _leer_pedido(conexion, pedido_id)
        _exigir_pendiente(pedido, "avisar")
        conexion.execute("UPDATE pedidos_impresion SET avisado = ? WHERE id = ?", (_ahora(), pedido_id))


def dar_por_perdida(usuario_id: int, pedido_id: int, motivo: str = ""):
    """
    El cliente no vino nunca: la seña queda para el local (lo decidió el dueño). No
    mueve plata, la seña ya estaba en su caja; el pedido deja de figurar como
    pendiente. Solo el Administrador: si no, alguien podría cerrar un pedido y
    cobrarle a escondidas lo que falta cuando el cliente venga.
    """
    usuarios_repo.exigir_admin(usuario_id, "dar una seña por perdida")
    with conexion_db() as conexion:
        pedido = _leer_pedido(conexion, pedido_id)
        _exigir_pendiente(pedido, "dar por perdida su seña")
        conexion.execute(
            "UPDATE pedidos_impresion SET estado = ?, cerrado_por = ?, fecha_cerrado = ?, motivo = ? WHERE id = ?",
            (dominio.PEDIDO_SENA_PERDIDA, usuario_id, _ahora(), (motivo or "").strip(), pedido_id),
        )


def anular_pedido(usuario_id: int, pedido_id: int, motivo: str):
    """
    Un pedido mal cargado: anula sus ventas (la seña y, si ya lo retiraron, la de la
    entrega), que salen de la caja y de los reportes como cualquier venta anulada, y
    el pedido queda ANULADO (nunca se borra). Solo el Administrador y con motivo,
    como anular una venta (ventas_repo.anular_venta).
    """
    usuarios_repo.exigir_admin(usuario_id, "anular un pedido de impresiones")
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("Escribí por qué se anula el pedido: sin motivo no se puede anular.")
    with conexion_db() as conexion:
        pedido = _leer_pedido(conexion, pedido_id)
        if pedido["estado"] == dominio.PEDIDO_ANULADO:
            raise ValueError(f"El pedido Nº {pedido_id} ya estaba anulado.")
        for venta_id in (pedido["venta_sena_id"], pedido["venta_entrega_id"]):
            if venta_id is None:
                continue
            venta = conexion.execute("SELECT estado FROM ventas WHERE id = ?", (venta_id,)).fetchone()
            if venta["estado"] != dominio.VENTA_ANULADA:
                ventas_repo._anular_venta(conexion, venta_id, usuario_id, f"Pedido de impresiones Nº {pedido_id}: {motivo}")
        conexion.execute(
            "UPDATE pedidos_impresion SET estado = ?, cerrado_por = ?, fecha_cerrado = ?, motivo = ? WHERE id = ?",
            (dominio.PEDIDO_ANULADO, usuario_id, _ahora(), motivo, pedido_id),
        )
