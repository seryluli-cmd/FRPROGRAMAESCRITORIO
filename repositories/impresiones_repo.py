"""
impresiones_repo.py
=====================
El cobro rápido de IMPRESIONES y FOTOCOPIAS desde el botón IMPRE/FOTOC (pedido
del dueño, 2026-10-19: "quiero una tarjeta para que esté más a mano"; las
fotocopias se sumaron el 2026-11-04, "el botón solo hace referencia a estas dos
por practicidad"), sin tener que entrar a Vender y buscar el artículo.

No es un negocio aparte: es una venta de kiosko común de los artículos
dominio.CODIGO_ARTICULO_IMPRESIONES y CODIGO_ARTICULO_FOTOCOPIAS, un renglón
de cada uno en venta_detalle, que descuenta stock y entra en la caja abierta
igual que si se los hubiera escaneado en Vender. Por eso Caja, Cierre de Turno,
Reportes, el Detalle del Día y anular desde Consulta de Ventas la tratan sin
saber de dónde vino (en Caja, las fotocopias siguen dentro de Kiosko).
"""

import dominio
from database import conexion_db
from repositories import ventas_repo

# Tope de una sola vez: alcanza de sobra para un pedido grande y frena un
# número tipeado de más (un 1500 en vez de 15) antes de cobrarlo.
CANTIDAD_MAXIMA = 999

# Los dos artículos del botón: código -> (cómo se llaman en los avisos, en plural).
NOMBRES = {
    dominio.CODIGO_ARTICULO_IMPRESIONES: "impresiones",
    dominio.CODIGO_ARTICULO_FOTOCOPIAS: "fotocopias",
}


def _leer_articulo(conexion, codigo=dominio.CODIGO_ARTICULO_IMPRESIONES):
    return conexion.execute(
        "SELECT codigo, descripcion, precio_venta FROM articulos WHERE codigo = ?",
        (codigo,),
    ).fetchone()


def articulo_impresiones():
    """El artículo de las impresiones (código, descripción y precio), o None
    si no está cargado con el código dominio.CODIGO_ARTICULO_IMPRESIONES."""
    with conexion_db() as conexion:
        return _leer_articulo(conexion)


def articulos_del_boton() -> dict:
    """{código: artículo o None} de impresiones y fotocopias, en ese orden."""
    with conexion_db() as conexion:
        return {codigo: _leer_articulo(conexion, codigo) for codigo in NOMBRES}


def mensaje_sin_articulo(codigo=dominio.CODIGO_ARTICULO_IMPRESIONES) -> str:
    """Qué decirle a quien atiende si el artículo no está cargado."""
    return (
        f"No hay ningún artículo con el código {codigo} "
        f"({NOMBRES[codigo].upper()}). Un encargado lo tiene que cargar en Admin Kiosko > Artículos "
        "con ese código."
    )


def cobrar_impresiones(usuario_id: int, cantidad: int, precio_unitario: float, pagos: list) -> int:
    """Graba la venta de `cantidad` impresiones solas y devuelve su número (ver
    `cobrar_impre_fotoc`)."""
    if not isinstance(cantidad, int) or cantidad < 1:
        raise ValueError("Ingresá cuántas impresiones son (al menos 1).")
    return cobrar_impre_fotoc(
        usuario_id, {dominio.CODIGO_ARTICULO_IMPRESIONES: (cantidad, precio_unitario)}, pagos)


def cobrar_impre_fotoc(usuario_id: int, cantidades: dict, pagos: list) -> int:
    """
    Graba en UNA venta las impresiones y las fotocopias, y devuelve su número.
    `cantidades` es {código: (cantidad, precio por unidad)} de los artículos del
    botón (NOMBRES); el que va con 0 no lleva renglón, pero al menos uno tiene
    que tener algo. `pagos` son los que devuelve la ventana de cobro (netos de
    vuelto): tienen que sumar el total, si no, no se graba nada.

    Cada precio es el que vio quien atiende al cobrar: si alguien cambió el
    precio en Artículos mientras tanto, no se graba (se le cobró al cliente otra
    plata que la que quedaría anotada). Los precios y la venta se leen y se
    graban en la misma transacción.
    """
    for codigo, (cantidad, _precio) in cantidades.items():
        if codigo not in NOMBRES:
            raise ValueError(f"El código {codigo} no es de impresiones ni de fotocopias.")
        nombre = NOMBRES[codigo]
        if not isinstance(cantidad, int) or cantidad < 0:
            raise ValueError(f"Revisá cuántas {nombre} son.")
        if cantidad > CANTIDAD_MAXIMA:
            raise ValueError(f"Son más de {CANTIDAD_MAXIMA} {nombre}: revisá la cantidad.")
    a_cobrar = {codigo: valores for codigo, valores in cantidades.items() if valores[0] > 0}
    if not a_cobrar:
        raise ValueError("Escribí cuántas impresiones o fotocopias son.")

    with conexion_db() as conexion:
        lineas = []
        # En el orden de NOMBRES: primero las impresiones, como en la pantalla.
        for codigo in (codigo for codigo in NOMBRES if codigo in a_cobrar):
            cantidad, precio_visto = a_cobrar[codigo]
            nombre = NOMBRES[codigo]
            articulo = _leer_articulo(conexion, codigo)
            if articulo is None:
                raise ValueError(mensaje_sin_articulo(codigo))
            if articulo["precio_venta"] <= 0:
                raise ValueError(
                    f"Las {nombre} no tienen precio cargado. Un encargado lo tiene que "
                    "poner en Admin Kiosko > Artículos."
                )
            if round(articulo["precio_venta"], 2) != round(precio_visto, 2):
                raise ValueError(
                    f"El precio de las {nombre} cambió mientras cobrabas. No se grabó nada: "
                    "volvé a abrir IMPRE/FOTOC."
                )
            lineas.append({
                "codigo": articulo["codigo"],
                "descripcion": articulo["descripcion"],
                "cantidad": cantidad,
                "precio_unitario": articulo["precio_venta"],
            })
        # Que los pagos sumen el total lo revisa _grabar_venta_kiosko, igual
        # que para cualquier venta de kiosko.
        return ventas_repo._grabar_venta_kiosko(conexion, usuario_id, lineas, pagos)
