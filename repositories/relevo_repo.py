"""
relevo_repo.py
===============
Qué pasa con la caja cuando alguien entra al programa, y el cierre forzoso
(pedido del dueño, 2026-10-18). Las reglas:

- Una empleada no trabaja sin caja. Si no hay ninguna abierta, abre una
  contando el cambio del cajón. Si la abre la misma persona que acaba de cerrar
  la anterior (su reemplazo no llegó), no cuenta: arranca con el cambio que ella
  misma dejó (salvo que en el medio el Admin haya cobrado algo sin caja).
- Si la caja abierta es de otra persona y su turno todavía no terminó (el
  reemplazo llegó tarde y la caja la tiene quien lo cubrió), la recibe contando
  TODO el cajón: el cambio más el efectivo vendido. Desde ahí la responsable es
  ella, y lo vendido antes va en su sobre.
- Si la caja abierta es de otra persona y su turno ya terminó (desde 5 minutos
  antes del fin, cuando titila el botón), la cierra la que llega: queda "cerrada
  por Gaby en ausencia de Lucía". Después abre la suya.
- Si quedaron ventas sin caja (del Admin vendiendo sin nadie en el mostrador),
  pasan a la caja que se abre (pedido del dueño, 2026-10-29: "lo que yo
  facture queda a cargo de la operadora que viene"; hasta ese día se cerraban
  aparte). Quien abre cuenta TODO el cajón, el cambio más lo que cobró el
  Admin, y esa plata va en su sobre: si algo no está, se ve al abrir y no
  recién al cerrar.
- El Admin (el dueño, que entra a cargar mercadería o cambiar precios) no abre
  caja: entra directo. Lo que cobre va a nombre de la responsable de la caja
  abierta (cajas_repo._quien_vende).
- A la hora del fin del turno (turnos.MINUTOS_PARA_CIERRE_FORZOSO) la
  caja se cierra sola (cierre forzoso):
  lo dispara la pantalla principal (ver cierre_forzoso_si_corresponde), o el
  ingreso de la propia responsable si el programa estuvo cerrado.

La plata del cierre sigue saliendo de turnos_repo (la ventana entre cierres):
acá solo se decide quién hace qué y se deja anotado. Las diferencias al contar
salen de dominio.diferencia_de_plata, como el sobre en Control de Cierres.
"""

from datetime import datetime

import dominio
from database import conexion_db
from repositories import cajas_repo, turnos_repo, usuarios_repo
from repositories.config_repo import obtener_fondo_cambio
from repositories.turnos_ventas_repo import _contar_ventas_entre
from turnos import (
    dia_del_turno_que_arranca_tras_un_cierre, etiqueta_turno, inicio_del_aviso_de_cierre,
    turno_que_arranca_tras_un_cierre, turno_vencimiento,
)

# Qué tiene que pasar cuando alguien entra (ver situacion_al_entrar). Son un
# rótulo entre este repo y la pantalla de ingreso, no algo que se guarde.
SITUACION_ADMIN = "ADMIN"                          # entra sin caja
SITUACION_SU_CAJA = "SU_CAJA"                      # la caja abierta es suya: entra
SITUACION_SU_CAJA_VENCIDA = "SU_CAJA_VENCIDA"      # es suya pero pasó el cierre forzoso: se cierra ya
SITUACION_ABRIR = "ABRIR"                          # no hay caja: abre una
SITUACION_RECIBIR = "RECIBIR"                      # caja de otra, turno en curso: la recibe contando
SITUACION_CERRAR_LA_DE_OTRA = "CERRAR_LA_DE_OTRA"  # caja de otra, turno terminado: la cierra

# Las que se resuelven con un Cierre de Turno antes de poder entrar.
_SITUACIONES_QUE_CIERRAN = (SITUACION_SU_CAJA_VENCIDA, SITUACION_CERRAR_LA_DE_OTRA)


def _datos_de_caja(caja) -> dict:
    """Lo que la pantalla muestra de una caja abierta."""
    return {
        "caja_id": caja["id"],
        "caja_numero": caja["id"],
        "responsable": caja["responsable"],
        "responsable_id": caja["responsable_id"],
        "turno": caja["turno"],
        "turno_label": etiqueta_turno(caja["fecha"], caja["turno"]),
        "abierta_en": caja["abierta_en"],
        # A qué hora se cierra sola si nadie la cierra (cierre forzoso).
        "cierre_forzoso_a": turno_vencimiento(caja["fecha"], caja["turno"]),
    }


def _apertura(conexion, usuario_id: int) -> dict:
    """Cuánto cambio se espera en la caja que se abra ahora y si hay que
    contarlo: lo que dejó la caja del último cierre (su cambio inicial), o el
    Cambio Fijo si ese cierre no tenía caja. No se cuenta si quien abre es la
    misma persona que tenía esa caja y la cerró ella (o se le cerró sola)."""
    ultimo = turnos_repo._obtener_ultimo_cierre(conexion)
    caja_anterior = cajas_repo._caja_del_cierre(conexion, ultimo["id"]) if ultimo else None
    if caja_anterior is None:
        return {"cambio_esperado": obtener_fondo_cambio(), "cuenta_cambio": True}
    la_cerro_ella = caja_anterior["responsable_id"] == usuario_id and ultimo["usuario_id"] == usuario_id
    return {"cambio_esperado": cajas_repo.cambio_inicial(caja_anterior), "cuenta_cambio": not la_cerro_ella}


def _situacion(conexion, usuario, ahora: datetime) -> dict:
    """situacion_al_entrar() sobre una conexión ya abierta (las acciones de
    abajo la vuelven a pedir en su propia transacción antes de grabar)."""
    caja = cajas_repo._caja_abierta(conexion)
    if dominio.es_admin(usuario):
        return {"situacion": SITUACION_ADMIN, **(_datos_de_caja(caja) if caja else {})}

    if caja is not None:
        datos = _datos_de_caja(caja)
        if caja["responsable_id"] == usuario["id"]:
            vencida = ahora >= turno_vencimiento(caja["fecha"], caja["turno"])
            return {"situacion": SITUACION_SU_CAJA_VENCIDA if vencida else SITUACION_SU_CAJA, **datos}
        resumen = turnos_repo._resumen_en_curso(conexion, ahora)
        if ahora >= inicio_del_aviso_de_cierre(caja["fecha"], caja["turno"]):
            return {
                "situacion": SITUACION_CERRAR_LA_DE_OTRA, **datos,
                "a_retirar": resumen["monto_a_retirar"], "cambio_que_queda": resumen["cambio_inicial"],
            }
        return {"situacion": SITUACION_RECIBIR, **datos, "esperado": resumen["caja_actual"],
                "cambio_inicial": resumen["cambio_inicial"], "ventas_efectivo": resumen["ventas_efectivo"]}

    apertura = _apertura(conexion, usuario["id"])
    situacion = {
        "situacion": SITUACION_ABRIR, **apertura,
        "turno_label": etiqueta_turno(dia_del_turno_que_arranca_tras_un_cierre(ahora),
                                      turno_que_arranca_tras_un_cierre(ahora)),
        "ventas_sin_caja": 0, "efectivo_sin_caja": 0.0, "desde": None,
        "esperado": apertura["cambio_esperado"],
    }
    ventana = turnos_repo._ventana_en_curso(conexion, ahora)
    confirmadas, _ = _contar_ventas_entre(conexion, ventana["desde"], ventana["hasta"])
    if confirmadas:
        # Lo que cobró el Admin sin caja pasa a la caja que se abre (ver
        # abrir_caja): su efectivo está en el cajón junto con el cambio, y se
        # cuenta todo junto aunque quien abre haya cerrado ella la anterior.
        efectivo = round(turnos_repo._resumen_en_curso(conexion, ahora)["ventas_efectivo"], 2)
        primera = conexion.execute(
            "SELECT MIN(fecha) AS fecha FROM ventas WHERE fecha > ? AND fecha <= ? AND estado = ?",
            (ventana["desde"], ventana["hasta"], dominio.VENTA_CONFIRMADA),
        ).fetchone()["fecha"]
        situacion.update({
            "cuenta_cambio": True, "ventas_sin_caja": confirmadas, "efectivo_sin_caja": efectivo,
            "desde": primera, "esperado": round(apertura["cambio_esperado"] + efectivo, 2),
        })
    return situacion


def situacion_al_entrar(usuario_id: int, ahora: datetime = None) -> dict:
    """
    Qué tiene que pasar con la caja para que `usuario_id` pueda entrar. Devuelve
    {"situacion": una de las SITUACION_*, ...} con lo que la pantalla necesita
    mostrar:
    - con caja abierta: "caja_numero", "responsable", "turno_label", "abierta_en";
    - RECIBIR: "esperado" (lo que tiene que haber en el cajón), "cambio_inicial"
      y "ventas_efectivo" (de dónde sale);
    - CERRAR_LA_DE_OTRA: "a_retirar" y "cambio_que_queda" (lo que va al sobre,
      el mismo "monto_a_retirar" que graba el cierre, y lo que se deja);
    - ABRIR: "cambio_esperado", "cuenta_cambio" y "turno_label" de la caja nueva;
      "ventas_sin_caja" (cuántas cobró el Admin sin caja, que pasan a esta),
      "efectivo_sin_caja" y "desde" (la primera de esas ventas, o None), y
      "esperado": lo que tiene que haber en el cajón (el cambio más ese efectivo).
    La pantalla de ingreso resuelve la situación (abrir_caja, recibir_caja o
    cerrar_para_entrar) y vuelve a preguntar hasta que da SU_CAJA o ADMIN.
    PermissionError si el usuario ya no está habilitado.
    """
    usuario = usuarios_repo.usuario_habilitado(usuario_id)
    ahora = ahora or datetime.now()
    with conexion_db() as conexion:
        return _situacion(conexion, usuario, ahora)


def _exigir_situacion(conexion, usuario, ahora, permitidas) -> dict:
    """La situación actual, o ValueError si ya no es ninguna de `permitidas`
    (cambió algo entre que la pantalla preguntó y la empleada confirmó)."""
    situacion = _situacion(conexion, usuario, ahora)
    if situacion["situacion"] not in permitidas:
        raise ValueError("La caja cambió mientras tanto. Volvé a entrar para ver cómo está ahora.")
    return situacion


def abrir_caja(usuario_id: int, cambio_contado=None, ahora: datetime = None) -> dict:
    """
    Abre una caja nueva a cargo de `usuario_id`, con el turno que corresponde a
    esta hora (con la tolerancia de turnos.turno_que_arranca_tras_un_cierre:
    quien abre a las 05:55 abre la Mañana). `cambio_contado` es lo que contó en
    el cajón (con lo que cobró el Admin sin caja, si hubo: ver
    situacion_al_entrar); None solo si no hace falta contar (ver _apertura): si
    hace falta y no viene, ValueError. Las ventas sin caja pasan a esta caja
    (_pasar_las_ventas_sin_caja). Devuelve {"caja_numero", "turno_label",
    "cambio_esperado", "cambio_contado", "diferencia", "ventas_sin_caja"}: el
    cambio esperado y el contado son los de la caja, sin la plata del Admin.
    """
    usuario = usuarios_repo.usuario_habilitado(usuario_id)
    ahora = ahora or datetime.now()
    with conexion_db() as conexion:
        situacion = _exigir_situacion(conexion, usuario, ahora, (SITUACION_ABRIR,))
        if situacion["cuenta_cambio"] and cambio_contado is None:
            raise ValueError("Contá la plata del cajón antes de abrir la caja.")
        # En la caja queda anotado solo el cambio, que es lo que tiene que quedar
        # en el cajón al cerrarla (cajas_repo.cambio_inicial): el efectivo del
        # Admin se va en el sobre con el resto de lo cobrado. La diferencia es
        # la misma que la de todo lo contado contra todo lo esperado.
        if cambio_contado is not None:
            cambio_contado = round(cambio_contado - situacion["efectivo_sin_caja"], 2)
        ventana = turnos_repo._ventana_en_curso(conexion, ahora)
        turno = turno_que_arranca_tras_un_cierre(ahora)
        dia = dia_del_turno_que_arranca_tras_un_cierre(ahora)
        cursor = conexion.execute(
            """
            INSERT INTO cajas (fecha, turno, abierta_por, abierta_en, cambio_esperado, cambio_contado, responsable_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (dia.isoformat(), turno, usuario_id, ahora.isoformat(timespec="microseconds"),
             situacion["cambio_esperado"], cambio_contado, usuario_id),
        )
        _pasar_las_ventas_sin_caja(conexion, cursor.lastrowid, usuario_id, ventana["desde"], ventana["hasta"])
    return {
        "caja_numero": cursor.lastrowid,
        "turno_label": etiqueta_turno(dia, turno),
        "cambio_esperado": situacion["cambio_esperado"],
        "cambio_contado": cambio_contado,
        "diferencia": (dominio.diferencia_de_plata(cambio_contado, situacion["cambio_esperado"])
                       if cambio_contado is not None else 0.0),
        "ventas_sin_caja": situacion["ventas_sin_caja"],
    }


def _pasar_las_ventas_sin_caja(conexion, caja_id: int, usuario_id: int, desde: str, hasta: str):
    """
    Las ventas de la ventana en curso que no tienen caja (las del Admin, sin
    nadie en el mostrador) pasan a la caja `caja_id` que acaba de abrir
    `usuario_id`: quedan a su nombre, y en `cargada_por` queda quién las cobró,
    igual que si el Admin las hubiera cobrado con su caja abierta
    (cajas_repo._quien_vende). Su plata ya entra en el cierre de esta caja,
    porque el cierre suma la ventana desde el cierre anterior (turnos_repo).
    """
    conexion.execute(
        """
        INSERT INTO ventas_caja (venta_id, caja_id, cargada_por)
        SELECT id, ?, NULLIF(usuario_id, ?) FROM ventas
        WHERE fecha > ? AND fecha <= ? AND id NOT IN (SELECT venta_id FROM ventas_caja)
        """,
        (caja_id, usuario_id, desde, hasta),
    )
    conexion.execute(
        "UPDATE ventas SET usuario_id = ? WHERE id IN (SELECT venta_id FROM ventas_caja WHERE caja_id = ?)",
        (usuario_id, caja_id),
    )


def recibir_caja(usuario_id: int, caja_id: int, monto_contado: float, ahora: datetime = None) -> dict:
    """
    `usuario_id` recibe la caja `caja_id` de quien la tenía: contó todo el cajón
    (`monto_contado`) y desde ahora la responsable es ella. Queda el relevo con
    lo que tendría que haber, lo contado y la diferencia. Devuelve {"esperado",
    "contado", "diferencia", "de" (quién la tenía), "caja_numero"}. ValueError
    si esa caja ya no está para recibir (ver situacion_al_entrar).
    """
    usuario = usuarios_repo.usuario_habilitado(usuario_id)
    ahora = ahora or datetime.now()
    monto_contado = round(monto_contado, 2)
    with conexion_db() as conexion:
        situacion = _exigir_situacion(conexion, usuario, ahora, (SITUACION_RECIBIR,))
        if situacion["caja_id"] != caja_id:
            raise ValueError("La caja cambió mientras tanto. Volvé a entrar para ver cómo está ahora.")
        esperado = situacion["esperado"]
        diferencia = dominio.diferencia_de_plata(monto_contado, esperado)
        conexion.execute(
            """
            INSERT INTO relevos_caja
                (caja_id, fecha, de_usuario_id, a_usuario_id, monto_esperado, monto_contado, diferencia)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (caja_id, ahora.isoformat(timespec="microseconds"), situacion["responsable_id"], usuario_id,
             esperado, monto_contado, diferencia),
        )
        conexion.execute("UPDATE cajas SET responsable_id = ? WHERE id = ?", (usuario_id, caja_id))
    return {
        "esperado": esperado, "contado": monto_contado, "diferencia": diferencia,
        "de": situacion["responsable"], "caja_numero": caja_id,
    }


def cerrar_para_entrar(usuario_id: int, situacion_esperada: str, ahora: datetime = None) -> dict:
    """
    El Cierre de Turno que hace falta antes de entrar: la caja de otra persona
    cuyo turno ya terminó (queda cerrada en su ausencia) o la propia que pasó el
    cierre forzoso (queda como forzoso).
    `situacion_esperada` es la que vio la pantalla: si ya no es esa, ValueError
    y no se cierra nada. Devuelve lo mismo que turnos_repo.cerrar_turno.
    """
    if situacion_esperada not in _SITUACIONES_QUE_CIERRAN:
        raise ValueError("Esa situación no se resuelve cerrando la caja.")
    usuario = usuarios_repo.usuario_habilitado(usuario_id)
    ahora = ahora or datetime.now()
    with conexion_db() as conexion:
        _exigir_situacion(conexion, usuario, ahora, (situacion_esperada,))
    return turnos_repo.cerrar_turno(
        usuario_id, forzoso=situacion_esperada == SITUACION_SU_CAJA_VENCIDA, ahora_dt=ahora
    )


def estado_de_la_caja(ahora: datetime = None):
    """
    Para la pantalla principal (cada pocos segundos): la caja abierta con
    "titilar" (desde 5 minutos antes del fin del turno: el botón Cierre de Turno
    titila en rojo) y "vencida" (pasaron los minutos de gracia: toca el
    cierre forzoso), o None si no hay caja abierta.
    """
    ahora = ahora or datetime.now()
    caja = cajas_repo.caja_abierta()
    if caja is None:
        return None
    return {
        **_datos_de_caja(caja),
        "titilar": ahora >= inicio_del_aviso_de_cierre(caja["fecha"], caja["turno"]),
        "vencida": ahora >= turno_vencimiento(caja["fecha"], caja["turno"]),
    }


def cierre_forzoso_si_corresponde(ahora: datetime = None):
    """
    Si la caja abierta pasó los minutos de gracia, la cierra a nombre de su
    responsable, como cierre forzoso, y devuelve lo mismo que
    turnos_repo.cerrar_turno. Si no hay caja o todavía no venció, None. La
    pantalla principal lo llama solo cuando no hay un cobro a medias (ver
    MainWindow._revisar_la_caja).
    """
    ahora = ahora or datetime.now()
    estado = estado_de_la_caja(ahora)
    if estado is None or not estado["vencida"]:
        return None
    return turnos_repo.cerrar_turno(estado["responsable_id"], forzoso=True, ahora_dt=ahora)
