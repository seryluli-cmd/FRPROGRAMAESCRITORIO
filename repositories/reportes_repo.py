"""
reportes_repo.py
==================
Consultas para la sección de Reportes: el Resumen (cuánta plata se
trabajó en un rango de fechas), el desglose Kiosko / Impresiones
(por turno, día, semana o el rango completo) y el Ranking de Ventas.
Son solo consultas SQL con agregación (SUM, GROUP BY), apoyadas en los
índices que se crean en database.py — por eso van a ser rápidas incluso
con años de ventas acumuladas.
"""

from datetime import date, timedelta

import dominio
from database import conexion_db
from repositories import turnos_ventas_repo
from turnos import limites_de_los_dias, sql_dia_del_local

# Todos los reportes de este archivo cuentan los días como el local: de 06:00 a
# 06:00 del día siguiente (pedido del dueño, 2026-10-17). Un rango "del 1 al 1"
# es el 1 a las 06:00 hasta el 2 a las 06:00, con la Noche del 1 entera adentro
# y sin la madrugada del 1 (que es la Noche del 30). Cada función pasa sus dos
# fechas por turnos.limites_de_los_dias antes de consultar.
#
# Lo que se reparte POR TURNO sigue a la caja, no al reloj (pedido del dueño,
# 2026-10-29): el turno cambia con la persona, hasta una hora antes o después
# (turnos.TURNO_GRACIA_MIN y MINUTOS_PARA_CIERRE_FORZOSO), y una venta de las
# 13:30 en la caja de la Tarde es de la Tarde. Así Por Turno suma lo mismo que
# los cierres de cada turno (Control de Cierres, Resumen del Día). El turno y el
# día son los de la caja de la venta (cajas.turno, cajas.fecha); una venta sin
# caja sigue con su hora (ventas.turno, el día del local de ventas.fecha).
_CON_SU_CAJA = """
            LEFT JOIN ventas_caja ON ventas_caja.venta_id = ventas.id
            LEFT JOIN cajas ON cajas.id = ventas_caja.caja_id"""
_TURNO_DE_LA_CAJA = "COALESCE(cajas.turno, ventas.turno)"
_DIA_DE_LA_CAJA = f"COALESCE(cajas.fecha, {sql_dia_del_local('ventas.fecha')})"
# El filtro por día de la caja no puede usar el índice de ventas.fecha y
# recorrería todas las ventas de la base: primero se acota por la hora con este
# margen y después se mira el día de la caja. Una venta y su caja difieren en
# horas (el turno se adelanta o se atrasa hasta una hora); lo que el Admin
# cobró sin caja pasa a la caja siguiente, que se abre enseguida.
_MARGEN_DE_DIAS_POR_CAJA = 2


def _filtro_por_caja(desde: str, hasta: str) -> tuple:
    """(condición SQL, parámetros) de las ventas cuya caja es de un día entre
    `desde` y `hasta` ("YYYY-MM-DD", incluidos los dos), para una consulta con
    _CON_SU_CAJA."""
    margen = timedelta(days=_MARGEN_DE_DIAS_POR_CAJA)
    inicio, fin = limites_de_los_dias(date.fromisoformat(desde) - margen, date.fromisoformat(hasta) + margen)
    return (f"ventas.fecha >= ? AND ventas.fecha < ? AND {_DIA_DE_LA_CAJA} BETWEEN ? AND ?",
            (inicio, fin, desde, hasta))

def resumen_ventas(desde: str, hasta: str):
    """
    Totales de ventas confirmadas entre dos fechas (incluidas ambas
    puntas), separados por medio de pago. `desde` y `hasta` son fechas
    en formato "YYYY-MM-DD" (días del local, de 06:00 a 06:00).
    """
    desde, hasta = limites_de_los_dias(desde, hasta)
    with conexion_db() as conexion:
        total_general = conexion.execute(
            """
            SELECT COALESCE(SUM(total), 0) AS total, COUNT(*) AS cantidad_ventas
            FROM ventas
            WHERE estado = ? AND fecha >= ? AND fecha < ?
            """,
            (dominio.VENTA_CONFIRMADA, desde, hasta),
        ).fetchone()

        por_metodo = conexion.execute(
            """
            SELECT venta_pagos.metodo, SUM(venta_pagos.monto) AS total
            FROM venta_pagos
            JOIN ventas ON ventas.id = venta_pagos.venta_id
            WHERE ventas.estado = ? AND ventas.fecha >= ? AND ventas.fecha < ?
            GROUP BY venta_pagos.metodo
            """,
            (dominio.VENTA_CONFIRMADA, desde, hasta),
        ).fetchall()

    totales_por_metodo = {metodo: 0.0 for metodo in dominio.METODOS_PAGO}
    for fila in por_metodo:
        totales_por_metodo[fila["metodo"]] = fila["total"] or 0.0

    return {
        "total": total_general["total"],
        "cantidad_ventas": total_general["cantidad_ventas"],
        "efectivo": totales_por_metodo[dominio.PAGO_EFECTIVO],
        "digital": totales_por_metodo[dominio.PAGO_DIGITAL],
    }


def resumen_por_turno(desde: str, hasta: str):
    """
    Lo mismo que resumen_ventas(), pero desglosado por turno (Mañana/
    Tarde/Noche) en vez de un único total — para responder "¿cuánto
    trabajó la Tarde esta semana?" sin tener que sumar a mano los
    cierres cargados en Control de Cierres de Turno. Devuelve siempre
    los 3 turnos, en orden, aunque alguno no tenga ventas en el rango.
    La Noche de cada día entra entera (días de 06:00 a 06:00).
    El turno y el día de cada venta son los de su caja (ver _CON_SU_CAJA):
    lo de cada turno es lo que suman sus cierres.
    """
    filtro, parametros = _filtro_por_caja(desde, hasta)
    with conexion_db() as conexion:
        por_turno = conexion.execute(
            f"""
            SELECT {_TURNO_DE_LA_CAJA} AS turno, COALESCE(SUM(ventas.total), 0) AS total,
                   COUNT(*) AS cantidad_ventas
            FROM ventas{_CON_SU_CAJA}
            WHERE ventas.estado = ? AND {filtro}
            GROUP BY 1
            """,
            (dominio.VENTA_CONFIRMADA, *parametros),
        ).fetchall()

        pagos_por_turno = conexion.execute(
            f"""
            SELECT {_TURNO_DE_LA_CAJA} AS turno, venta_pagos.metodo, SUM(venta_pagos.monto) AS total
            FROM venta_pagos
            JOIN ventas ON ventas.id = venta_pagos.venta_id{_CON_SU_CAJA}
            WHERE ventas.estado = ? AND {filtro}
            GROUP BY 1, venta_pagos.metodo
            """,
            (dominio.VENTA_CONFIRMADA, *parametros),
        ).fetchall()

    totales = {turno: {"total": 0.0, "cantidad_ventas": 0, "efectivo": 0.0, "digital": 0.0}
               for turno in dominio.TURNOS}
    for fila in por_turno:
        totales[fila["turno"]]["total"] = fila["total"]
        totales[fila["turno"]]["cantidad_ventas"] = fila["cantidad_ventas"]
    for fila in pagos_por_turno:
        clave = "efectivo" if fila["metodo"] == dominio.PAGO_EFECTIVO else "digital"
        totales[fila["turno"]][clave] = fila["total"] or 0.0

    return [{"turno": turno, **datos} for turno, datos in totales.items()]


# El día es el del local (06:00 a 06:00, ver turnos.sql_dia_del_local): una venta
# del martes a la 01:00 es de la Noche del lunes y suma en el lunes.
_DIA_DEL_LOCAL = sql_dia_del_local("ventas.fecha")

_COLUMNA_AGRUPACION = {
    "turno": _TURNO_DE_LA_CAJA,  # con _CON_SU_CAJA, ver resumen_por_origen
    "dia": _DIA_DEL_LOCAL,
    # 'weekday 0' avanza a el próximo domingo (0 = domingo) y '-6 days'
    # retrocede al lunes de esa misma semana -- modismo estándar de
    # SQLite para "lunes de la semana que contiene esta fecha". Parte del día
    # del local: la Noche del domingo (hasta el lunes a las 06:00) es de esa semana.
    "semana": f"date({_DIA_DEL_LOCAL}, 'weekday 0', '-6 days')",
    "rango": "1",
}


def _etiqueta_agrupacion(clave, agrupar_por: str) -> str:
    """El texto que se muestra para una fila de resumen_por_origen, según
    cómo se agrupó (`clave` es el valor de _COLUMNA_AGRUPACION)."""
    if agrupar_por == "turno":
        return clave.capitalize()
    if agrupar_por == "rango":
        return "Total del período"
    fecha = date.fromisoformat(clave)
    if agrupar_por == "dia":
        return fecha.strftime("%d/%m/%Y")
    # "semana": la columna de agrupación ya devuelve el lunes de esa semana.
    fin_semana = fecha + timedelta(days=6)
    return f"Semana del {fecha.strftime('%d/%m')} al {fin_semana.strftime('%d/%m/%Y')}"


def _sumar_por_clave(conexion, consulta: str, parametros) -> dict:
    """{clave: total} de una consulta que devuelve las columnas `clave`
    (el período, ver _COLUMNA_AGRUPACION) y `total`."""
    return {fila["clave"]: fila["total"] or 0.0 for fila in conexion.execute(consulta, parametros)}


def resumen_por_origen(desde: str, hasta: str, agrupar_por: str = "rango"):
    """Ventas de mercadería e impresiones por período; cada peso cuenta una vez.
    Por turno, el turno y el día son los de la caja de cada venta, como en
    resumen_por_turno (ver _CON_SU_CAJA)."""
    columna_grupo = _COLUMNA_AGRUPACION[agrupar_por]
    if agrupar_por == "turno":
        cajas = _CON_SU_CAJA
        filtro, parametros = _filtro_por_caja(desde, hasta)
    else:
        cajas = ""
        filtro, parametros = "ventas.fecha >= ? AND ventas.fecha < ?", limites_de_los_dias(desde, hasta)
    rango = (dominio.VENTA_CONFIRMADA, *parametros)
    with conexion_db() as conexion:
        totales = _sumar_por_clave(
            conexion,
            f"""
            SELECT {columna_grupo} AS clave, COALESCE(SUM(ventas.total), 0) AS total
            FROM ventas{cajas}
            WHERE ventas.estado = ? AND {filtro}
            GROUP BY clave
            """,
            rango,
        )
        impresiones = _sumar_por_clave(
            conexion,
            f"""
            SELECT {columna_grupo} AS clave, COALESCE(SUM(venta_detalle.subtotal), 0) AS total
            FROM venta_detalle
            JOIN ventas ON ventas.id = venta_detalle.venta_id{cajas}
            WHERE venta_detalle.articulo_codigo = ?
              AND ventas.estado = ? AND {filtro}
            GROUP BY clave
            """,
            (dominio.CODIGO_ARTICULO_IMPRESIONES, *rango),
        )
    if agrupar_por == "turno":
        claves = list(dominio.TURNOS)
    elif agrupar_por == "rango":
        claves = [1]
    else:
        claves = sorted(totales)
    return [
        {
            "etiqueta": _etiqueta_agrupacion(clave, agrupar_por),
            "kiosko": round(totales.get(clave, 0.0) - impresiones.get(clave, 0.0), 2),
            "impresiones": round(impresiones.get(clave, 0.0), 2),
            "total": round(totales.get(clave, 0.0), 2),
        }
        for clave in claves
    ]


def ranking_ventas(desde: str, hasta: str, ordenar_por: str = "cantidad"):
    """Artículos vendidos, agrupados por código y descripción cobrados."""
    columna_orden = "cantidad" if ordenar_por == "cantidad" else "importe"
    rango = (dominio.VENTA_CONFIRMADA, *limites_de_los_dias(desde, hasta))
    with conexion_db() as conexion:
        return conexion.execute(
            f"""
            SELECT venta_detalle.articulo_codigo AS codigo,
                   venta_detalle.descripcion AS descripcion,
                   SUM(venta_detalle.cantidad) AS cantidad,
                   SUM(venta_detalle.subtotal) AS importe
            FROM venta_detalle
            JOIN ventas ON ventas.id = venta_detalle.venta_id
            WHERE ventas.estado = ? AND ventas.fecha >= ? AND ventas.fecha < ?
            GROUP BY venta_detalle.articulo_codigo, venta_detalle.descripcion
            ORDER BY {columna_orden} DESC, descripcion
            """,
            rango,
        ).fetchall()

# ---------------------------------------------------------------------
# Por Operador: quién vendió qué y a qué hora
# ---------------------------------------------------------------------
# La venta queda a nombre de quien tenía la sesión abierta en el mostrador
# (ventas.usuario_id), que no siempre es quien atendió: si alguien vende con
# la sesión de otro, sale a nombre del otro. Es el mismo dato que usa el
# detalle de un cierre (turnos_repo.detalle_cierre).

def resumen_por_operador(desde: str, hasta: str):
    """
    Una fila por cada usuario que registró al menos una venta entre dos
    fechas (incluidas ambas puntas, "YYYY-MM-DD"): cuántas ventas confirmadas
    hizo, cuántas se anularon después, y cuánto cobró en efectivo, en digital y
    en total -- solo de las confirmadas, mismo criterio que resumen_ventas(). El
    efectivo de venta_pagos ya viene sin el vuelto, así que efectivo + digital
    da el total. Ordenado de mayor a menor total.
    """
    rango = limites_de_los_dias(desde, hasta)
    with conexion_db() as conexion:
        filas = conexion.execute(
            """
            SELECT usuarios.id AS usuario_id, usuarios.nombre AS nombre,
                   SUM(CASE WHEN ventas.estado = ? THEN 1 ELSE 0 END) AS cantidad_ventas,
                   SUM(CASE WHEN ventas.estado = ? THEN 1 ELSE 0 END) AS cantidad_anuladas,
                   COALESCE(SUM(CASE WHEN ventas.estado = ? THEN ventas.total END), 0) AS total
            FROM ventas
            JOIN usuarios ON usuarios.id = ventas.usuario_id
            WHERE ventas.fecha >= ? AND ventas.fecha < ?
            GROUP BY usuarios.id
            """,
            (dominio.VENTA_CONFIRMADA, dominio.VENTA_ANULADA, dominio.VENTA_CONFIRMADA, *rango),
        ).fetchall()

        pagos = conexion.execute(
            """
            SELECT ventas.usuario_id AS usuario_id, venta_pagos.metodo AS metodo,
                   SUM(venta_pagos.monto) AS total
            FROM venta_pagos
            JOIN ventas ON ventas.id = venta_pagos.venta_id
            WHERE ventas.estado = ? AND ventas.fecha >= ? AND ventas.fecha < ?
            GROUP BY ventas.usuario_id, venta_pagos.metodo
            """,
            (dominio.VENTA_CONFIRMADA, *rango),
        ).fetchall()

    por_metodo = {}
    for fila in pagos:
        por_metodo[(fila["usuario_id"], fila["metodo"])] = fila["total"] or 0.0

    resultado = [
        {
            "usuario_id": fila["usuario_id"],
            "nombre": fila["nombre"],
            "cantidad_ventas": fila["cantidad_ventas"],
            "cantidad_anuladas": fila["cantidad_anuladas"],
            "efectivo": round(por_metodo.get((fila["usuario_id"], dominio.PAGO_EFECTIVO), 0.0), 2),
            "digital": round(por_metodo.get((fila["usuario_id"], dominio.PAGO_DIGITAL), 0.0), 2),
            "total": round(fila["total"], 2),
        }
        for fila in filas
    ]
    resultado.sort(key=lambda fila: (-fila["total"], fila["nombre"].lower()))
    return resultado


def ventas_de_operador(usuario_id: int, desde: str, hasta: str):
    """
    Las ventas de un usuario entre dos fechas, una por una y en orden de hora
    (las anuladas también, con su estado, para que se vea que existieron). Cada
    fila trae "id", "fecha" (con la hora, tal como se grabó), "turno", "estado",
    "total", "efectivo", "digital" y "concepto": qué se vendió, en corto -- los
    artículos de kiosko ("2 x Coca 500").
    """
    pagos, parametros_pagos = turnos_ventas_repo._efectivo_y_digital_de_cada_venta()
    with conexion_db() as conexion:
        return [dict(fila) for fila in conexion.execute(
            f"""
            SELECT ventas.id, ventas.fecha, ventas.turno, ventas.estado,
                   ventas.total,
                   {pagos},
                   COALESCE((SELECT GROUP_CONCAT(cantidad || ' x ' || descripcion, ', ')
                             FROM venta_detalle WHERE venta_id = ventas.id), '') AS concepto
            FROM ventas
            WHERE ventas.usuario_id = ?
              AND ventas.fecha >= ? AND ventas.fecha < ?
            ORDER BY ventas.fecha, ventas.id
            """,
            (*parametros_pagos, usuario_id, *limites_de_los_dias(desde, hasta)),
        )]

