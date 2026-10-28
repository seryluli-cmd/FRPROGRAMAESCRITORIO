"""
ventas_repo.py
===============
Todo lo relacionado a registrar ventas (facturación) y, cuando hace
falta, anularlas.

Un detalle importante de diseño: el "carrito" de una venta en curso vive
solo en la memoria de la pantalla de Ventas (una lista de Python) — no se
guarda nada en la base de datos hasta que se confirma el pago. Por eso
una empleada puede borrar un renglón mal escaneado libremente mientras
está armando la venta: recién cuando se llama a `confirmar_venta(...)`
queda algo grabado, y a partir de ahí ya no se puede tocar (solo un
Admin puede anularla después con `anular_venta`).
"""

from datetime import datetime

import dominio
from database import conexion_db
from repositories import cajas_repo, usuarios_repo
from turnos import calcular_turno

# Cuánto pueden diferir lo que suman los pagos y el total de una venta: un
# centavo, lo que se puede perder al repartir un total entre efectivo y
# digital. Más que eso ya no es redondeo: Reportes (que suma ventas.total) y
# el Cierre de Turno (que suma venta_pagos) mostrarían plata distinta.
DIFERENCIA_MAXIMA_DE_PAGOS = 0.01


def subtotal_linea(linea) -> float:
    """
    Cuánto se cobra por un renglón del carrito. Hoy es simplemente
    cantidad × precio, pero pasa por acá a propósito: es el único lugar
    donde se decide esa cuenta, así que el día que haya un descuento por
    cantidad o una promo 2x1, se cambia una sola función y la pantalla
    de Ventas, el total y lo que se graba en la base quedan coherentes
    solos.
    """
    return linea["cantidad"] * linea["precio_unitario"]


def total_carrito(lineas: list) -> float:
    """Total de una venta en curso, sumando el subtotal de cada renglón."""
    return sum(subtotal_linea(linea) for linea in lineas)


def _insertar_cabecera_venta(conexion, ahora: datetime, usuario_id: int, total: float, origen: str) -> int:
    """
    Graba la cabecera de una venta CONFIRMADA y devuelve su id. El
    turno sale de la hora de la venta (turnos.calcular_turno), no de quién
    la hace.

    La fecha lleva microsegundos, no segundos: turnos_repo compara
    "ventas.fecha" contra "cierres_turno.fecha_cierre" con un corte estricto
    (> / <=) para decidir a qué turno pertenece cada venta. Una venta y un
    cierre en el mismo segundo empataban en el string de fecha y la venta
    quedaba afuera de los DOS turnos. turnos_repo.cerrar_turno graba la
    fecha de cierre con la misma precisión, por la misma razón.

    Con una caja abierta, la venta queda anotada en esa caja; si la cobra el
    Admin, queda a nombre de la responsable de la caja (ver
    cajas_repo._quien_vende). Por eso el usuario que se graba puede no ser
    `usuario_id`.
    """
    vendedor_id, caja_id, cargada_por = cajas_repo._quien_vende(conexion, usuario_id)
    cursor = conexion.execute(
        """
        INSERT INTO ventas (fecha, usuario_id, turno, total, estado, origen)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ahora.isoformat(timespec="microseconds"), vendedor_id, calcular_turno(ahora),
         round(total, 2), dominio.VENTA_CONFIRMADA, origen),
    )
    cajas_repo._anotar_venta_en_caja(conexion, cursor.lastrowid, caja_id, cargada_por)
    return cursor.lastrowid


def _insertar_pagos(conexion, venta_id: int, pagos: list):
    """Graba los pagos de una venta, uno por fila (puede haber más de uno
    para un cobro combinado). Único lugar donde se hace el INSERT INTO
    venta_pagos."""
    for pago in pagos:
        conexion.execute(
            "INSERT INTO venta_pagos (venta_id, metodo, monto) VALUES (?, ?, ?)",
            (venta_id, pago["metodo"], round(pago["monto"], 2)),
        )


def confirmar_venta(usuario_id: int, lineas: list, pagos: list) -> int:
    """
    Graba una venta ya armada y cobrada.

    lineas: lista de diccionarios
        {"codigo", "descripcion", "cantidad", "precio_unitario"}
        El subtotal NO se recibe: se calcula acá con `subtotal_linea()`,
        para que la pantalla no pueda mandar una cuenta distinta a la que
        se graba en la base.
    pagos: lista de diccionarios
        {"metodo": dominio.PAGO_EFECTIVO | dominio.PAGO_DIGITAL, "monto": ...}
        (puede haber más de uno, para pagos combinados)

    Descuenta el stock de cada artículo vendido (puede quedar negativo,
    a propósito) y devuelve el número de factura generado. Cabecera,
    detalle, pagos y descuento de stock quedan todos en la misma
    transacción: si algo falla a mitad de camino, no queda una venta a
    medio grabar con el stock ya descontado.

    Los montos se redondean a 2 decimales antes de guardarse, para que
    pequeños errores de redondeo de punto flotante no se vayan
    acumulando venta tras venta a lo largo de los años.
    """
    with conexion_db() as conexion:
        return _grabar_venta_kiosko(conexion, usuario_id, lineas, pagos)


def _revisar_que_los_pagos_sumen_el_total(total: float, pagos: list):
    """
    ValueError si los pagos no suman el total de la venta (con hasta
    DIFERENCIA_MAXIMA_DE_PAGOS de diferencia). Los pagos llegan netos de
    vuelto (como los arma dominio.cuenta_del_cobro), así que tienen que dar
    justo el total: ni menos (se grabaría plata que no entró) ni más (el
    vuelto quedaría como si se hubiera cobrado).

    Se compara lo que se va a GRABAR (cada monto redondeado, como en
    _insertar_pagos y _insertar_cabecera_venta): es lo que suman después
    Reportes y el Cierre de Turno.
    """
    cobrado = round(sum(round(pago["monto"], 2) for pago in pagos), 2)
    if abs(round(cobrado - round(total, 2), 2)) > DIFERENCIA_MAXIMA_DE_PAGOS:
        raise ValueError(
            f"Lo cobrado ({dominio.texto_pesos(cobrado)}) no coincide con el total de la "
            f"venta ({dominio.texto_pesos(total)}). No se grabó nada: volvé a cobrar."
        )


def _grabar_venta_kiosko(conexion, usuario_id: int, lineas: list, pagos: list) -> int:
    """
    Núcleo de confirmar_venta sobre una conexión YA ABIERTA: lo usa también
    impresiones_repo.cobrar_impresiones, que lee el precio del artículo en la
    misma transacción en que graba la venta. Único lugar donde se hace el
    INSERT INTO venta_detalle y se descuenta el stock por una venta.

    Antes de grabar nada revisa que los pagos sumen el total: es el único
    lugar por donde pasan todas las ventas de kiosko, así que ninguna pantalla
    (ni una nueva que cobre distinto) puede dejar una venta descuadrada.
    """
    total = total_carrito(lineas)
    _revisar_que_los_pagos_sumen_el_total(total, pagos)
    venta_id = _insertar_cabecera_venta(
        conexion, datetime.now(), usuario_id, total, dominio.ORIGEN_KIOSKO
    )

    for linea in lineas:
        conexion.execute(
            """
            INSERT INTO venta_detalle
                (venta_id, articulo_codigo, descripcion, cantidad, precio_unitario, subtotal)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (venta_id, linea["codigo"], linea["descripcion"], linea["cantidad"],
             round(linea["precio_unitario"], 2), round(subtotal_linea(linea), 2)),
        )
        # Restamos el stock. Se permite que quede en negativo (ver
        # database.py / articulos_repo.py para la explicación completa).
        conexion.execute(
            "UPDATE articulos SET stock = stock - ? WHERE codigo = ?",
            (linea["cantidad"], linea["codigo"]),
        )

    _insertar_pagos(conexion, venta_id, pagos)
    return venta_id


def _anular_venta(conexion, venta_id: int, usuario_admin_id: int, motivo: str):
    """
    Núcleo de anular_venta que opera sobre una conexión ya abierta.
    """
    venta = conexion.execute("SELECT * FROM ventas WHERE id = ?", (venta_id,)).fetchone()
    if venta is None:
        raise ValueError("La venta no existe.")
    if venta["estado"] == dominio.VENTA_ANULADA:
        raise ValueError("Esa venta ya estaba anulada.")

    lineas = conexion.execute(
        "SELECT articulo_codigo, cantidad FROM venta_detalle WHERE venta_id = ?", (venta_id,)
    ).fetchall()
    for linea in lineas:
        conexion.execute(
            "UPDATE articulos SET stock = stock + ? WHERE codigo = ?",
            (linea["cantidad"], linea["articulo_codigo"]),
        )

    ahora = datetime.now().isoformat(timespec="seconds")
    conexion.execute(
        """
        UPDATE ventas
        SET estado = ?, anulada_por = ?, anulada_fecha = ?, anulada_motivo = ?
        WHERE id = ?
        """,
        (dominio.VENTA_ANULADA, usuario_admin_id, ahora, motivo, venta_id),
    )


def anular_venta(venta_id: int, usuario_admin_id: int, motivo: str):
    """
    Anula una venta ya confirmada. Repone el stock de cada artículo
    vendido y deja constancia de quién anuló, cuándo, y por qué — la
    venta NUNCA se borra de la base, solo cambia su estado a ANULADA,
    para no perder el rastro.

    Solo un Administrador activo: la pantalla ya esconde el botón, pero se
    vuelve a preguntar acá (usuarios_repo.exigir_admin) porque anular saca
    plata de la caja y de los reportes, y también se pide desde otra PC.
    El motivo es obligatorio: sin él, una anulación no se puede explicar
    cuando se audita un faltante.
    """
    usuarios_repo.exigir_admin(usuario_admin_id, "anular una venta")
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("Escribí por qué se anula la venta: sin motivo no se puede anular.")
    with conexion_db() as conexion:
        _anular_venta(conexion, venta_id, usuario_admin_id, motivo)


def buscar_venta(venta_id: int):
    """Trae una venta con su detalle y sus pagos, para mostrarla antes
    de anularla (o simplemente para consultarla)."""
    with conexion_db() as conexion:
        venta = conexion.execute("SELECT * FROM ventas WHERE id = ?", (venta_id,)).fetchone()
        if venta is None:
            return None, [], []
        detalle = conexion.execute(
            "SELECT * FROM venta_detalle WHERE venta_id = ?", (venta_id,)
        ).fetchall()
        pagos = conexion.execute(
            "SELECT * FROM venta_pagos WHERE venta_id = ?", (venta_id,)
        ).fetchall()
        return venta, detalle, pagos


def listar_ventas_recientes(limite: int = 50):
    """Últimas ventas cargadas, para la pantalla de Consulta/Anulación."""
    with conexion_db() as conexion:
        return conexion.execute(
            """
            SELECT ventas.*, usuarios.nombre AS vendedor
            FROM ventas
            JOIN usuarios ON usuarios.id = ventas.usuario_id
            ORDER BY ventas.id DESC
            LIMIT ?
            """,
            (limite,),
        ).fetchall()
