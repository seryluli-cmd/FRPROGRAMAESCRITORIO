"""
config_repo.py
================
Acceso a la configuración del fondo de cambio del kiosko.
"""

from database import conexion_db


def obtener_fondo_cambio() -> float:
    """El fondo de cambio que queda en el cajón al cerrar cada turno."""
    with conexion_db() as conexion:
        fila = conexion.execute(
            "SELECT valor FROM configuracion WHERE clave = 'fondo_cambio'"
        ).fetchone()
        return float(fila["valor"]) if fila else 0.0


def actualizar_fondo_cambio(nuevo_valor: float):
    """Solo el Admin puede llamar a esto (se valida en la pantalla)."""
    with conexion_db() as conexion:
        conexion.execute(
            "UPDATE configuracion SET valor = ? WHERE clave = 'fondo_cambio'",
            (str(round(nuevo_valor, 2)),),
        )


