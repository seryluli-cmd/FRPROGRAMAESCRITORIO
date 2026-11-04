"""
rotacion_repo.py
==================
RANKING DE ROTACIÓN (pedido del dueño, 2026-11-04): qué tan rápido se vende cada
artículo, de dos maneras (las dos pestañas de la ventana):

- POR COMPRA (ranking_por_compras, la idea del dueño): cuánto tardó en venderse
  cada compra, desde que entró la mercadería hasta que salió la última unidad, en
  promedio de las últimas dominio.COMPRAS_PARA_PROMEDIAR que ya se vendieron enteras.
- POR PERÍODO (ranking_de_rotacion): cuántas unidades salieron en los últimos días,
  a cuántas por día, el stock de hoy y para cuántos días alcanza a ese ritmo.

Las dos cuentan solo ventas confirmadas (una anulada ya devolvió su stock). Las
impresiones (dominio.CODIGO_ARTICULO_IMPRESIONES, también la seña de un pedido) no
entran: son hojas que se cobran, no mercadería de un estante, y su stock no dice
cuándo hay que comprar.
"""

from datetime import date, datetime

import dominio
from database import conexion_db
from turnos import limites_de_los_dias

# Qué movió el stock, en el orden en que se aplica si dos cosas caen en el mismo
# instante: la compra primero (lo vendido en ese segundo ya salió de ella).
_COMPRA, _AJUSTE, _VENTA = 0, 1, 2


def ranking_de_rotacion(desde: str, hasta: str):
    """
    Todos los artículos (menos las impresiones), del que más se vendió entre
    `desde` y `hasta` ("YYYY-MM-DD", incluidos los dos, días del local) al que
    menos. Cada renglón es un dict con: puesto, codigo, descripcion, rubro ("" si
    no tiene), stock, vendidas, por_dia y alcanza (dias_que_alcanza: None si no
    se vendió nada, 0 sin stock).

    Los que no vendieron nada van al final, de la A a la Z y sin puesto (None):
    es la mercadería quieta. ValueError si `desde` es posterior a `hasta`.
    """
    dias = (date.fromisoformat(hasta) - date.fromisoformat(desde)).days + 1
    if dias <= 0:
        raise ValueError("La fecha de inicio tiene que ser anterior o igual a la del final.")
    inicio, fin = limites_de_los_dias(desde, hasta)
    with conexion_db() as conexion:
        filas = conexion.execute(
            """
            SELECT a.codigo, a.descripcion, a.stock, COALESCE(r.nombre, '') AS rubro,
                   COALESCE(v.vendidas, 0) AS vendidas
            FROM articulos a
            LEFT JOIN rubros r ON r.id = a.rubro_id
            LEFT JOIN (
                SELECT venta_detalle.articulo_codigo AS codigo, SUM(venta_detalle.cantidad) AS vendidas
                FROM venta_detalle
                JOIN ventas ON ventas.id = venta_detalle.venta_id
                WHERE ventas.estado = ? AND ventas.fecha >= ? AND ventas.fecha < ?
                GROUP BY venta_detalle.articulo_codigo
            ) v ON v.codigo = a.codigo
            WHERE a.codigo <> ?
            """,
            (dominio.VENTA_CONFIRMADA, inicio, fin, dominio.CODIGO_ARTICULO_IMPRESIONES),
        ).fetchall()

    # El orden se arma acá y no en el SQL: los empates y los quietos van de la A a
    # la Z como los lee una persona (sin mayúsculas ni acentos, dominio.sin_acentos).
    def orden(fila):
        return (-max(fila["vendidas"], 0), dominio.sin_acentos(fila["descripcion"]), fila["codigo"])

    ranking = []
    puesto = 0
    for fila in sorted(filas, key=orden):
        vendidas = fila["vendidas"]
        if vendidas > 0:
            puesto += 1
        ranking.append({
            "puesto": puesto if vendidas > 0 else None,
            "codigo": fila["codigo"],
            "descripcion": fila["descripcion"],
            "rubro": fila["rubro"],
            "stock": fila["stock"],
            "vendidas": vendidas,
            "por_dia": dominio.unidades_por_dia(max(vendidas, 0), dias),
            "alcanza": dominio.dias_que_alcanza(fila["stock"], vendidas, dias),
        })
    return ranking


# ---------------------------------------------------------------------
# POR COMPRA: cuánto tardó en venderse cada compra
# ---------------------------------------------------------------------
# Se rearma la historia del stock de cada artículo desde su primera compra: las
# compras (con el stock que había, compra_detalle.stock_antes), las ventas
# confirmadas y las correcciones de ORDENAR Stock (ajustes_stock). La mercadería
# sale en el orden en que entró: lo que ya estaba en el estante se vende antes que
# lo que llega (como se repone un estante, lo nuevo atrás). Una compra "se vendió
# entera" cuando sale su última unidad, y lo que tardó es desde la hora de la compra
# hasta esa venta.

def ranking_por_compras(ahora=None):
    """
    Todos los artículos (menos las impresiones), del que más rápido vende cada
    compra al que más tarda. Cada renglón es un dict con: puesto, codigo,
    descripcion, rubro, stock, dias (lo que tardaron en venderse enteras las
    últimas dominio.COMPRAS_PARA_PROMEDIAR compras, en promedio y en días con
    decimales; None si ninguna se vendió entera), compras_medidas (cuántas entraron
    en ese promedio), compras (cuántas compras tuvo en total) y, de la última compra,
    ultima_fecha (ISO), ultima_cantidad, ultima_quedan (cuántas de esa compra siguen
    en el estante; 0 si ya se vendió entera) y ultima_hace (días desde que entró).
    Sin ninguna compra, esas cuatro van en None.

    Los que no tienen ninguna compra vendida entera van al final, de la A a la Z y
    sin puesto (None). `ahora` (datetime) es para las pruebas.
    """
    ahora = ahora or datetime.now()
    impresiones = dominio.CODIGO_ARTICULO_IMPRESIONES
    with conexion_db() as conexion:
        articulos = conexion.execute(
            """
            SELECT a.codigo, a.descripcion, a.stock, COALESCE(r.nombre, '') AS rubro
            FROM articulos a
            LEFT JOIN rubros r ON r.id = a.rubro_id
            WHERE a.codigo <> ?
            """,
            (impresiones,),
        ).fetchall()
        compras = conexion.execute(
            """
            SELECT compra_detalle.articulo_codigo AS codigo, compras.fecha, compra_detalle.cantidad,
                   compra_detalle.stock_antes
            FROM compra_detalle
            JOIN compras ON compras.id = compra_detalle.compra_id
            WHERE compra_detalle.articulo_codigo <> ?
            ORDER BY compras.fecha, compra_detalle.id
            """,
            (impresiones,),
        ).fetchall()
        # Lo de antes de la primera compra no hace falta: la historia arranca con el
        # stock que había en ella. Así se lee solo desde ahí (con el índice de fecha).
        ventas, ajustes = [], []
        if compras:
            primera = compras[0]["fecha"]
            ventas = conexion.execute(
                """
                SELECT venta_detalle.articulo_codigo AS codigo, ventas.fecha, venta_detalle.cantidad
                FROM venta_detalle
                JOIN ventas ON ventas.id = venta_detalle.venta_id
                WHERE ventas.estado = ? AND ventas.fecha >= ? AND venta_detalle.articulo_codigo <> ?
                """,
                (dominio.VENTA_CONFIRMADA, primera, impresiones),
            ).fetchall()
            ajustes = conexion.execute(
                "SELECT articulo_codigo AS codigo, fecha, stock_nuevo - stock_anterior AS cambio "
                "FROM ajustes_stock WHERE fecha >= ?",
                (primera,),
            ).fetchall()

    eventos = {}
    for compra in compras:
        eventos.setdefault(compra["codigo"], []).append(
            (compra["fecha"], _COMPRA, compra["cantidad"], compra["stock_antes"]))
    for venta in ventas:
        if venta["codigo"] in eventos:
            eventos[venta["codigo"]].append((venta["fecha"], _VENTA, venta["cantidad"], None))
    for ajuste in ajustes:
        if ajuste["codigo"] in eventos:
            eventos[ajuste["codigo"]].append((ajuste["fecha"], _AJUSTE, ajuste["cambio"], None))

    renglones = [_renglon_por_compras(articulo, eventos.get(articulo["codigo"], []), ahora)
                 for articulo in articulos]

    def orden(renglon):
        sin_medir = renglon["dias"] is None
        return (sin_medir, 0 if sin_medir else renglon["dias"],
                dominio.sin_acentos(renglon["descripcion"]), renglon["codigo"])

    renglones.sort(key=orden)
    puesto = 0
    for renglon in renglones:
        if renglon["dias"] is not None:
            puesto += 1
            renglon["puesto"] = puesto
    return renglones


def _renglon_por_compras(articulo, eventos, ahora) -> dict:
    """El renglón de un artículo con lo que tardaron sus compras (ver ranking_por_compras)."""
    renglon = {
        "puesto": None, "codigo": articulo["codigo"], "descripcion": articulo["descripcion"],
        "rubro": articulo["rubro"], "stock": articulo["stock"], "dias": None, "compras_medidas": 0,
        "compras": 0, "ultima_fecha": None, "ultima_cantidad": None, "ultima_quedan": None, "ultima_hace": None,
    }
    lotes = _lotes_de_compra(eventos)
    if not lotes:
        return renglon
    medidas = [lote for lote in lotes if lote["vendida_en"] is not None][-dominio.COMPRAS_PARA_PROMEDIAR:]
    if medidas:
        dias = [_dias_entre(lote["fecha"], lote["vendida_en"]) for lote in medidas]
        renglon["dias"] = round(sum(dias) / len(dias), 2)
    ultima = lotes[-1]
    renglon.update({
        "compras_medidas": len(medidas),
        "compras": len(lotes),
        "ultima_fecha": ultima["fecha"],
        "ultima_cantidad": ultima["cantidad"],
        "ultima_quedan": ultima["quedan"],
        "ultima_hace": round(max(_dias_entre(ultima["fecha"], ahora), 0), 2),
    })
    return renglon


def _dias_entre(desde, hasta) -> float:
    """Días (con decimales) entre dos momentos: textos ISO de la base o datetime."""
    desde = desde if isinstance(desde, datetime) else datetime.fromisoformat(desde)
    hasta = hasta if isinstance(hasta, datetime) else datetime.fromisoformat(hasta)
    return (hasta - desde).total_seconds() / 86400


def _lotes_de_compra(eventos) -> list:
    """
    Cada compra de un artículo, en orden, con cuántas de sus unidades siguen en el
    estante (`quedan`) y, si ya salió la última, cuándo (`vendida_en`). `eventos`
    son tuplas (fecha ISO, tipo, cantidad, stock_antes) de UN artículo; para un
    ajuste, la cantidad es lo que sumó (o restó, en negativo) la corrección.

    La mercadería sale en el orden en que entró. Lo que había antes de una compra
    (su stock_antes, también lo de antes de la primera) va adelante y sin fecha: no
    se mide. Si el stock quedó en negativo (se vendió sin haber), la próxima compra
    primero tapa lo que se debía: esas unidades ya estaban vendidas, y una compra
    que se tapa entera se vendió en el momento (0 días).

    Solo se mide una compra cuya última unidad salió con una VENTA: si la terminó
    una corrección de ORDENAR Stock (faltaba mercadería), no se sabe cuánto tardaba
    en venderse. Antes de cada compra, la cuenta se empareja con el stock que
    guardó esa compra: si algo no cuadra (una anulación de una venta vieja), manda
    lo que había de verdad.
    """
    estante = []     # lo que hay, en el orden en que sale: {"fecha", "quedan", "lote"}
    deuda = 0        # unidades vendidas sin stock (stock negativo)
    lotes = []

    def stock():
        return sum(parte["quedan"] for parte in estante) - deuda

    def sale(cantidad, fecha, con_una_venta):
        nonlocal deuda
        while cantidad > 0 and estante:
            parte = estante[0]
            saca = min(cantidad, parte["quedan"])
            parte["quedan"] -= saca
            cantidad -= saca
            lote = parte["lote"]
            if lote is not None:
                lote["quedan"] = parte["quedan"]
            if parte["quedan"] == 0:
                estante.pop(0)
                if lote is not None and con_una_venta:
                    lote["vendida_en"] = fecha
        deuda += cantidad

    def entra(cantidad, fecha=None, lote=None):
        nonlocal deuda
        tapa = min(deuda, cantidad)
        deuda -= tapa
        cantidad -= tapa
        if lote is not None:
            lote["quedan"] = cantidad
            if cantidad == 0:
                lote["vendida_en"] = fecha
        if cantidad > 0:
            estante.append({"quedan": cantidad, "lote": lote})

    for fecha, tipo, cantidad, stock_antes in sorted(eventos, key=lambda evento: (evento[0], evento[1])):
        if tipo == _COMPRA:
            diferencia = stock_antes - stock()
            if diferencia > 0:
                entra(diferencia)
            elif diferencia < 0:
                sale(-diferencia, fecha, con_una_venta=False)
            if cantidad <= 0:
                continue
            lote = {"fecha": fecha, "cantidad": cantidad, "quedan": cantidad, "vendida_en": None}
            lotes.append(lote)
            entra(cantidad, fecha, lote)
        elif tipo == _VENTA:
            sale(cantidad, fecha, con_una_venta=True)
        elif cantidad > 0:
            entra(cantidad)
        elif cantidad < 0:
            sale(-cantidad, fecha, con_una_venta=False)
    return lotes
