"""
pelotita_repo.py
================
Si la pelotita que rebota por el inicio (ui/pelotita.py) está prendida. La prende y
la apaga el Administrador en Configuración ADMIN (pedido del dueño, 2026-11-04,
cuando eligió la maqueta); viene prendida. Vale para todos los que entran en el
mostrador: se guarda en la tabla `configuracion`, con la clave de este repo.

Es solo del mostrador: la copia que se abre desde otra PC no muestra la pelotita ni
el interruptor, así que estas funciones no van en admin_remoto/lista_blanca.py.
"""

from database import conexion_db
from repositories import config_repo, usuarios_repo

_CLAVE_PRENDIDA = "pelotita_prendida"
_APAGADA = "0"
_PRENDIDA = "1"


def esta_prendida() -> bool:
    """True salvo que el Administrador la haya apagado (sin nada guardado, prendida)."""
    with conexion_db() as conexion:
        return config_repo.leer(conexion, _CLAVE_PRENDIDA) != _APAGADA


def prender(usuario_id: int, prendida: bool):
    """La prende o la apaga para todos. Solo un Administrador activo."""
    usuarios_repo.exigir_admin(usuario_id, "prender o apagar la pelotita del inicio")
    with conexion_db() as conexion:
        config_repo.guardar(conexion, _CLAVE_PRENDIDA, _PRENDIDA if prendida else _APAGADA)
