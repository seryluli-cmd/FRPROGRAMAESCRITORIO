"""
acomodar_caja_repo.py
=======================
ACOMODAR CAJA (pedido del dueño, 2026-11-04): pasar del programa anterior a
FRKiosko a mitad de turno sin que la caja quede corta. El Admin escribe cuánto
había cobrado el otro programa en efectivo y en digital, y eso entra en la caja
abierta. "Es por esta vez nomás": no es una herramienta para el día a día.

Entra como una venta de kiosko común de un artículo que no es mercadería
(dominio.CODIGO_ARTICULO_ACOMODAR_CAJA), con sus dos pagos reales. Así Caja,
Cierre de Turno, A RETIRAR, Control de Cierres y la app de gastos la suman sin
saber de dónde vino, igual que la seña de Gestión Impresiones. No hace falta un
origen de venta nuevo (tocaría la caja y un CHECK de `ventas`, ver CLAUDE.md) ni
una tabla nueva.

Si se cargó mal, se anula desde Consulta de Ventas como cualquier venta (Admin y
motivo) y se vuelve a cargar.
"""

from datetime import datetime

import dominio
from database import conexion_db
from repositories import usuarios_repo, ventas_repo


def _asegurar_articulo(conexion):
    """El artículo de ACOMODAR CAJA, creado la primera vez: `venta_detalle`
    exige un artículo de verdad. Precio 0 y escondido de las listas
    (articulos_repo._SIN_ACOMODAR): nadie lo vende a mano."""
    ahora = datetime.now().isoformat(timespec="seconds")
    conexion.execute(
        """
        INSERT OR IGNORE INTO articulos
            (codigo, descripcion, precio_venta, precio_compra, stock, stock_minimo,
             fecha_creacion, fecha_modif)
        VALUES (?, ?, 0, 0, 0, 0, ?, ?)
        """,
        (dominio.CODIGO_ARTICULO_ACOMODAR_CAJA, dominio.DESCRIPCION_ACOMODAR_CAJA, ahora, ahora),
    )


def _monto(valor, que: str) -> float:
    try:
        monto = round(float(valor), 2)
    except (TypeError, ValueError):
        raise ValueError(f"El {que} tiene que ser un número.")
    if monto < 0:
        raise ValueError(f"El {que} no puede ser negativo.")
    return monto


def acomodar_caja(usuario_id: int, efectivo, digital) -> int:
    """
    Suma a la caja lo que cobró el programa anterior: `efectivo` y `digital`
    (uno de los dos puede ser 0, no los dos). Solo un Administrador activo.
    Devuelve el número de la venta.

    Va a la caja abierta, a nombre de su responsable (cajas_repo._quien_vende,
    como todo lo que cobra el Admin); sin caja abierta, queda a nombre del Admin
    y pasa a la próxima caja que se abra, igual que una venta suya.
    """
    usuarios_repo.exigir_admin(usuario_id, "acomodar la caja")
    efectivo = _monto(efectivo, "efectivo")
    digital = _monto(digital, "digital")
    total = round(efectivo + digital, 2)
    if total <= 0:
        raise ValueError("Escribí cuánto cobró el programa anterior (efectivo, digital o los dos).")

    pagos = [{"metodo": metodo, "monto": monto}
             for metodo, monto in ((dominio.PAGO_EFECTIVO, efectivo), (dominio.PAGO_DIGITAL, digital))
             if monto > 0]
    linea = {
        "codigo": dominio.CODIGO_ARTICULO_ACOMODAR_CAJA,
        "descripcion": dominio.DESCRIPCION_ACOMODAR_CAJA,
        "cantidad": 1,
        "precio_unitario": total,
    }
    with conexion_db() as conexion:
        _asegurar_articulo(conexion)
        venta_id = ventas_repo._grabar_venta_kiosko(conexion, usuario_id, [linea], pagos)
        # No es mercadería: que la venta no le deje el stock en -1.
        conexion.execute(
            "UPDATE articulos SET stock = 0 WHERE codigo = ?", (dominio.CODIGO_ARTICULO_ACOMODAR_CAJA,)
        )
    return venta_id
