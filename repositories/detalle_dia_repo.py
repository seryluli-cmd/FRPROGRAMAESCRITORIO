"""
detalle_dia_repo.py
====================
El detalle de lo vendido en un día del local, venta por venta, para
Reportes > Resumen del Día: cantidades, hora, turno y operador.

Qué venta es de qué turno lo decide `turnos_repo._ventanas_del_dia`, la misma
función que arma las filas de cada turno del Resumen del Día: así la suma del
detalle de un turno da lo mismo que su fila (salvo una venta anulada DESPUÉS de
cerrar: el cierre guardó una foto con ella adentro; acá se la marca).

Qué se vendió en cada venta sale de venta_detalle. Impresiones conserva el
detalle de cada renglón tal como se cobró.

Cada venta trae además sus `lineas`, renglón por renglón tal cual se cobró (con el
código del artículo), para el listado "Renglón por renglón" que se imprime (pedido
del dueño, 2026-10-18: "si se cobran 14 impresiones juntas, que diga 14; si se
hacen 4 por separado, que las ponga tal cual se cobraron, con su horario y su
operador").
"""

from datetime import datetime

import dominio
from database import conexion_db
from repositories import turnos_repo
from turnos import etiqueta_turno


def _texto_cantidad(cantidad) -> str:
    return str(int(cantidad)) if float(cantidad).is_integer() else str(cantidad)


def _sin_articulo(importe: float) -> tuple:
    """Descripción de respaldo para una venta que no tiene renglones."""
    return (
        "(sin detalle)", [("(sin detalle)", 1, importe)],
        [{"codigo": "", "descripcion": "(sin detalle)", "cantidad": 1, "importe": round(importe, 2)}],
    )


def _ventas_entre(conexion, desde: str, hasta: str):
    return conexion.execute(
        """
        SELECT ventas.id, ventas.fecha, ventas.estado, ventas.total, ventas.anulada_fecha,
               usuarios.nombre AS operador, cargadores.nombre AS cargada_por,
               COALESCE((SELECT SUM(monto) FROM venta_pagos
                         WHERE venta_id = ventas.id AND metodo = ?), 0) AS efectivo,
               COALESCE((SELECT SUM(monto) FROM venta_pagos
                         WHERE venta_id = ventas.id AND metodo = ?), 0) AS digital
        FROM ventas
        JOIN usuarios ON usuarios.id = ventas.usuario_id
        LEFT JOIN ventas_caja ON ventas_caja.venta_id = ventas.id
        LEFT JOIN usuarios AS cargadores ON cargadores.id = ventas_caja.cargada_por
        WHERE ventas.fecha > ? AND ventas.fecha <= ?
        ORDER BY ventas.fecha, ventas.id
        """,
        (dominio.PAGO_EFECTIVO, dominio.PAGO_DIGITAL, desde, hasta),
    ).fetchall()


def _que_se_vendio_entre(conexion, desde: str, hasta: str) -> dict:
    """
    {venta_id: (detalle, renglones, lineas)} de las ventas de (desde, hasta]
    que tienen algo vendido anotado. `renglones` es [(producto, cantidad,
    importe)] para sumar por producto; `lineas` es lo cobrado tal cual,
    [{"codigo", "descripcion", "cantidad", "importe"}].
    """
    rango = (desde, hasta)
    resultado = {}

    lineas = {}
    for fila in conexion.execute(
        """
        SELECT venta_detalle.venta_id, venta_detalle.articulo_codigo AS codigo, venta_detalle.descripcion,
               venta_detalle.cantidad, venta_detalle.subtotal
        FROM venta_detalle JOIN ventas ON ventas.id = venta_detalle.venta_id
        WHERE ventas.fecha > ? AND ventas.fecha <= ?
        ORDER BY venta_detalle.id
        """, rango,
    ):
        lineas.setdefault(fila["venta_id"], []).append(fila)
    for venta_id, filas in lineas.items():
        resultado[venta_id] = (
            ", ".join(f"{_texto_cantidad(f['cantidad'])} x {f['descripcion']}" for f in filas),
            [(f["descripcion"], f["cantidad"], f["subtotal"]) for f in filas],
            [{"codigo": f["codigo"], "descripcion": f["descripcion"], "cantidad": f["cantidad"],
              "importe": round(f["subtotal"], 2)} for f in filas],
        )

    return resultado


def _por_producto(ventas: list) -> list:
    """Cuánto se vendió de cada cosa (solo las ventas no anuladas): una fila
    {"producto", "cantidad", "importe"} por producto, de la que más se vendió
    a la que menos."""
    acumulado = {}
    for venta in ventas:
        if venta["anulada"]:
            continue
        for producto, cantidad, importe in venta["renglones"]:
            fila = acumulado.setdefault(producto, {"producto": producto, "cantidad": 0, "importe": 0.0})
            fila["cantidad"] += cantidad
            fila["importe"] = round(fila["importe"] + importe, 2)
    return sorted(acumulado.values(), key=lambda f: (-f["cantidad"], f["producto"]))


def _por_operador(ventas: list) -> list:
    """Cuánto vendió cada operador (a nombre de quien quedó cada venta, como en
    Reportes > Por Operador): ventas, anuladas, efectivo, digital y total (sin
    las anuladas). Del que más vendió al que menos."""
    acumulado = {}
    for venta in ventas:
        fila = acumulado.setdefault(venta["operador"], {
            "operador": venta["operador"], "ventas": 0, "anuladas": 0,
            "efectivo": 0.0, "digital": 0.0, "total": 0.0,
        })
        if venta["anulada"]:
            fila["anuladas"] += 1
            continue
        fila["ventas"] += 1
        for campo in ("efectivo", "digital", "total"):
            fila[campo] = round(fila[campo] + venta[campo], 2)
    return sorted(acumulado.values(), key=lambda f: (-f["total"], f["operador"]))


def _totales(ventas: list) -> dict:
    """Ventas, anuladas, unidades (la suma de las cantidades de todos los
    renglones, como el pie del listado que se imprime), efectivo, digital y
    total, sin las anuladas."""
    validas = [venta for venta in ventas if not venta["anulada"]]
    return {
        "ventas": len(validas),
        "anuladas": len(ventas) - len(validas),
        "unidades": sum(linea["cantidad"] for venta in validas for linea in venta["lineas"]),
        **{campo: round(sum(venta[campo] for venta in validas), 2) for campo in ("efectivo", "digital", "total")},
    }


def detalle_del_dia(dia) -> dict:
    """
    Todo lo vendido en `dia` (date o "YYYY-MM-DD", el día del local: la Noche
    entera, hasta su cierre). Devuelve:

    {"fecha", "turnos": [...], "ventas": [...], "por_producto": [...],
     "por_operador": [...], "totales": {...}}

    Cada turno: {"turno", "etiqueta", "ventas", "por_producto", "por_operador",
    "totales"} (solo los turnos que tienen un cierre o están abiertos, en el
    orden del día). Cada venta: {"id", "fecha", "turno", "etiqueta_turno",
    "operador", "cargada_por" (quien la cobró si no fue el operador, o None),
    "detalle", "efectivo", "digital", "total", "anulada",
    "anulada_despues_del_cierre", "renglones", "lineas"}. "totales" y los
    resúmenes cuentan solo las ventas no anuladas.
    """
    dia = datetime.fromisoformat((dia if isinstance(dia, str) else dia.isoformat())[:10]).date()
    with conexion_db() as conexion:
        ventanas = turnos_repo._ventanas_del_dia(conexion, dia, datetime.now())
        ventas_por_turno = {}
        for ventana in ventanas:
            ventas_por_turno.setdefault(ventana["turno"], [])
            vendido = _que_se_vendio_entre(conexion, ventana["desde"], ventana["hasta"])
            etiqueta = etiqueta_turno(dia, ventana["turno"])
            for fila in _ventas_entre(conexion, ventana["desde"], ventana["hasta"]):
                anulada = fila["estado"] == dominio.VENTA_ANULADA
                detalle, renglones, lineas = vendido.get(fila["id"], _sin_articulo(fila["total"]))
                ventas_por_turno.setdefault(ventana["turno"], []).append({
                    "id": fila["id"],
                    "fecha": fila["fecha"],
                    "turno": ventana["turno"],
                    "etiqueta_turno": etiqueta,
                    "operador": fila["operador"],
                    "cargada_por": fila["cargada_por"],
                    "detalle": detalle,
                    "efectivo": round(fila["efectivo"], 2),
                    "digital": round(fila["digital"], 2),
                    "total": round(fila["total"], 2),
                    "anulada": anulada,
                    # El cierre ya la había contado (guardó una foto de lo cobrado).
                    "anulada_despues_del_cierre": bool(
                        anulada and ventana["cierre"] is not None and fila["anulada_fecha"]
                        and datetime.fromisoformat(fila["anulada_fecha"]) > datetime.fromisoformat(ventana["hasta"])
                    ),
                    "renglones": renglones,
                    "lineas": lineas,
                })

    orden = {turno: posicion for posicion, turno in enumerate(dominio.TURNOS)}
    turnos = []
    todas = []
    for turno in sorted(ventas_por_turno, key=lambda t: orden.get(t, len(orden))):
        ventas = sorted(ventas_por_turno[turno], key=lambda v: (v["fecha"], v["id"]))
        todas += ventas
        turnos.append({
            "turno": turno,
            "etiqueta": etiqueta_turno(dia, turno),
            "ventas": ventas,
            "por_producto": _por_producto(ventas),
            "por_operador": _por_operador(ventas),
            "totales": _totales(ventas),
        })
    return {
        "fecha": dia,
        "turnos": turnos,
        "ventas": todas,
        "por_producto": _por_producto(todas),
        "por_operador": _por_operador(todas),
        "totales": _totales(todas),
    }

