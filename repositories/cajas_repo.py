"""
cajas_repo.py
==============
Los datos de las cajas con número (pedido del dueño, 2026-10-18; tablas en
database_esquema_cajas.py): cuál está abierta, a nombre de quién queda una
venta y lo que se muestra de una caja en Caja y en Control de Cierres.

Este archivo no decide nada del ingreso (abrir, recibir o cerrar la caja de
otra persona): eso es relevo_repo, que usa a este y a turnos_repo. Acá solo hay
lo que necesitan ventas_repo y turnos_repo, para que ninguno de los dos tenga
que importar al otro.

Sin caja abierta (el Admin vendiendo sin nadie en el mostrador) las ventas
quedan sin caja y el cierre sale igual de la ventana entre cierres (ver
turnos_repo); relevo_repo las pasa a la próxima caja que se abre.
"""

import dominio
from database import conexion_db


def _caja_abierta(conexion):
    """La caja que está abierta ahora, con el nombre de su responsable
    ("responsable"), o None si no hay ninguna. Solo puede haber una (ver
    relevo_repo.abrir_caja)."""
    return conexion.execute(
        """
        SELECT cajas.*, usuarios.nombre AS responsable
        FROM cajas
        JOIN usuarios ON usuarios.id = cajas.responsable_id
        WHERE cajas.cierre_id IS NULL
        ORDER BY cajas.id DESC
        LIMIT 1
        """
    ).fetchone()


def caja_abierta():
    """La caja abierta como diccionario (ver _caja_abierta), o None."""
    with conexion_db() as conexion:
        caja = _caja_abierta(conexion)
    return dict(caja) if caja else None


def cambio_inicial(caja) -> float:
    """Con cuánto cambio arrancó una caja: lo que se contó al abrirla, o lo que
    se esperaba si no se contó (la abrió quien acababa de cerrar la anterior).
    Es lo que tiene que quedar en el cajón al cerrarla."""
    if caja["cambio_contado"] is not None:
        return caja["cambio_contado"]
    return caja["cambio_esperado"]


def cerrada_en_ausencia(caja, quien_cierra_id) -> bool:
    """Si la caja `caja` (o None, un cierre sin caja) la cierra otra persona que
    su responsable: la que llega o el Admin, porque la responsable se fue sin
    cerrar. Se compara por número de usuario, no por nombre: el nombre se puede
    cambiar en Usuarios con la sesión abierta, y una usuaria dada de baja puede
    llamarse igual que una activa."""
    return caja is not None and quien_cierra_id != caja["responsable_id"]


def _quien_vende(conexion, usuario_id: int) -> tuple:
    """
    A nombre de quién queda una venta que cobra `usuario_id` y en qué caja:
    (usuario_id de la venta, caja_id o None, cargada_por o None).

    - Sin caja abierta (el Admin vendiendo sin nadie en el mostrador): a su
      nombre y sin caja, hasta que alguien abra una y pase a la suya
      (relevo_repo._pasar_las_ventas_sin_caja).
    - El Admin con la caja de una empleada abierta: a nombre de ELLA, dentro de
      su caja, y queda anotado que la cargó el Admin (pedido del dueño,
      2026-10-18: "que lo asiente como la empleada que estaba antes de que yo
      entrara", así no hay que andar cambiando de usuario). Es la plata de su
      cajón y va en su sobre.
    - Cualquier otra persona: a su nombre, dentro de la caja abierta.
    """
    caja = _caja_abierta(conexion)
    if caja is None:
        return usuario_id, None, None
    if usuario_id == caja["responsable_id"]:
        return usuario_id, caja["id"], None
    usuario = conexion.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    if usuario is not None and dominio.es_admin(usuario):
        return caja["responsable_id"], caja["id"], usuario_id
    return usuario_id, caja["id"], None


def _anotar_venta_en_caja(conexion, venta_id: int, caja_id, cargada_por):
    """Deja anotado en qué caja quedó una venta (nada si no hay caja). Lo llama
    ventas_repo._insertar_cabecera_venta en la misma transacción que la venta."""
    if caja_id is None:
        return
    conexion.execute(
        "INSERT INTO ventas_caja (venta_id, caja_id, cargada_por) VALUES (?, ?, ?)",
        (venta_id, caja_id, cargada_por),
    )


def _marcar_cerrada(conexion, caja_id: int, cierre_id: int, forzoso: bool):
    """Une la caja con su cierre (deja de estar abierta). Lo llama
    turnos_repo.cerrar_turno en la misma transacción que el cierre."""
    conexion.execute(
        "UPDATE cajas SET cierre_id = ?, cierre_forzoso = ? WHERE id = ? AND cierre_id IS NULL",
        (cierre_id, 1 if forzoso else 0, caja_id),
    )


def _caja_del_cierre(conexion, cierre_id: int):
    """La caja que se cerró con el cierre `cierre_id` (con los nombres de quien
    la abrió y de su responsable), o None si es un cierre sin caja (el Admin
    cerró sin ninguna caja abierta)."""
    return conexion.execute(
        """
        SELECT cajas.*, responsables.nombre AS responsable, abridores.nombre AS abierta_por_nombre
        FROM cajas
        JOIN usuarios AS responsables ON responsables.id = cajas.responsable_id
        JOIN usuarios AS abridores ON abridores.id = cajas.abierta_por
        WHERE cajas.cierre_id = ?
        """,
        (cierre_id,),
    ).fetchone()


def _relevos_de(conexion, caja_id: int) -> list:
    """Los relevos de una caja, en orden, con los nombres de quien la entregó
    ("de") y de quien la recibió ("a")."""
    return conexion.execute(
        """
        SELECT relevos_caja.*, de_usuario.nombre AS de_nombre, a_usuario.nombre AS a_nombre
        FROM relevos_caja
        JOIN usuarios AS de_usuario ON de_usuario.id = relevos_caja.de_usuario_id
        JOIN usuarios AS a_usuario ON a_usuario.id = relevos_caja.a_usuario_id
        WHERE relevos_caja.caja_id = ?
        ORDER BY relevos_caja.id
        """,
        (caja_id,),
    ).fetchall()

