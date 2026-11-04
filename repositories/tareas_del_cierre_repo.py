"""
tareas_del_cierre_repo.py
==========================
Las TAREAS DEL TURNO de un Cierre de Turno (pedido del dueño, 2026-11-03: que las
tareas "aparezcan y se envíen en el resumen a la pwa, junto con el cierre de caja",
abajo del resumen de caja, que queda intacto). Viajan a la app de gastos con el
cierre (envio_pwa_repo.datos_del_cierre); en FRKiosko la tarjeta del cierre no
cambia.

Qué tareas son de un cierre: las que tocaban en la ventana del cierre (después del
cierre anterior y hasta este, la misma ventana que la de lo vendido), con cómo
estaban AL CERRAR: HECHA (quién y cuándo) o sin hacer, y quiénes la pospusieron hasta
entonces. Lo que pasa después no cambia el cierre, igual que la plata: marcarla
HECHA a las 22:10 no la pasa a hecha en el cierre de las 22:05, una tarea cargada o
cambiada después no aparece, y mandar el cierre de nuevo días después manda lo
mismo. Una tarea hecha antes de su hora (se puede) va en el cierre en cuya ventana
cae su hora.

Qué toca cada día y cómo está lo decide tareas_turno_repo (_apariciones_del_dia):
acá solo se mira la ventana del cierre, con el reloj parado en la hora del cierre.
Está aparte para no pasar tareas_turno_repo de las ~600 líneas (regla 12).
"""

from datetime import datetime, timedelta

import turnos
from repositories import tareas_turno_repo


def tareas_del_cierre(conexion, desde: str, hasta: str) -> list:
    """
    Las apariciones cuya hora cae después de `desde` y hasta `hasta` (ISO: el cierre
    anterior y este; `desde` puede ser control_cierres_repo._PRINCIPIO_DE_LOS_TIEMPOS,
    el año 0, si es el primer cierre), en el orden del turno y como estaban a la hora
    del cierre. Mismos dicts que tareas_turno_repo.tareas_del_dia: `estado` es HECHA,
    ATRASADA o NO SE HIZO (de un día que terminó antes del cierre) y las
    posposiciones son solo las de hasta el cierre. Con la conexión de quien llama.
    """
    primera = conexion.execute("SELECT MIN(creada) AS creada FROM tareas_turno").fetchone()["creada"]
    if primera is None:
        return []
    # Antes de la primera tarea no hay nada: el primer cierre no recorre dos mil años.
    # Se comparan como texto porque el año 0 no es una fecha de Python.
    desde_dt = datetime.fromisoformat(max(desde, primera))
    hasta_dt = datetime.fromisoformat(hasta)
    if desde_dt >= hasta_dt:
        return []
    primer_dia = turnos.dia_en_que_empezo_el_turno(desde_dt)
    ultimo_dia = turnos.dia_en_que_empezo_el_turno(hasta_dt)
    tareas, cambios, marcas = tareas_turno_repo._leer_todo(conexion, primer_dia, ultimo_dia)
    # Lo que se anotó después del cierre no cuenta: el cierre queda como estaba al cerrar.
    marcas = {
        clave: [marca for marca in lo_anotado if datetime.fromisoformat(marca["fecha"]) <= hasta_dt]
        for clave, lo_anotado in marcas.items()
    }
    del_cierre = []
    dia = primer_dia
    while dia <= ultimo_dia:
        for aparicion in tareas_turno_repo._apariciones_del_dia(tareas, cambios, marcas, dia, hasta_dt):
            # Después del cierre anterior: lo que tocaba justo en ese momento ya fue suyo.
            if desde_dt < datetime.fromisoformat(aparicion["momento"]) <= hasta_dt:
                del_cierre.append(aparicion)
        dia += timedelta(days=1)
    return del_cierre
