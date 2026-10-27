"""Versionado del esquema propio de Kiosko.

Este proyecto arranca con una base nueva. Las versiones futuras se agregan acá
como pasos idempotentes; la base de CYBERCONTROL no se importa ni se modifica.
"""


VERSION_ESQUEMA = 1
TABLAS_DEL_PROGRAMA_ORIGINAL = ("estaciones", "miembros", "sesiones_pc", "bonos_tiempo")


def comprobar_base_kiosko(conexion):
    """Evita abrir por error una base que todavía pertenece a CYBERCONTROL."""
    nombres = {fila[0] for fila in conexion.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if nombres.intersection(TABLAS_DEL_PROGRAMA_ORIGINAL):
        raise RuntimeError(
            "Esta base pertenece a CYBERCONTROL. Kiosko usa una base nueva y separada."
        )


def migrar_base(conexion):
    """Registra la versión inicial una sola vez, sin alterar datos existentes."""
    actual = conexion.execute("PRAGMA user_version").fetchone()[0]
    if actual > VERSION_ESQUEMA:
        raise RuntimeError("La base fue creada por una versión más nueva de Kiosko.")
    if actual < VERSION_ESQUEMA:
        conexion.execute(f"PRAGMA user_version = {VERSION_ESQUEMA}")
