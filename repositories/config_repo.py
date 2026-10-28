"""
config_repo.py
================
La tabla `configuracion` (una clave con su valor, siempre texto) y el fondo de
cambio del kiosko, que se guarda ahí.

`leer` y `guardar` son el único lugar que lee y graba esa tabla. Cada repo que
guarda algo ahí (admin_remoto_repo, copias_repo, envio_pwa_repo) tiene su clave
con nombre y decide cómo se entiende su valor ("1" = prendido, una lista en
JSON...). La única excepción es la siembra de la primera vez
(database._cargar_datos_iniciales): database.py no puede importar un repo.
"""

from database import CLAVE_FONDO_CAMBIO, conexion_db


def leer(conexion, clave: str):
    """El valor guardado en `clave`, o None si la clave no está. Lee con
    `conexion`, así dentro de una transacción abierta ve lo que esa misma
    transacción ya grabó."""
    fila = conexion.execute("SELECT valor FROM configuracion WHERE clave = ?", (clave,)).fetchone()
    return fila["valor"] if fila is not None else None


def guardar(conexion, clave: str, valor: str, *, crear_si_falta: bool = True):
    """
    Graba `valor` en `clave` con `conexion`, sin commit (va con la transacción
    de quien llama). Si la clave no está, la crea; con `crear_si_falta=False`
    solo cambia una clave que ya está y, si falta, no hace nada.
    """
    if crear_si_falta:
        conexion.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)", (clave, valor))
    else:
        conexion.execute("UPDATE configuracion SET valor = ? WHERE clave = ?", (valor, clave))


def obtener_fondo_cambio() -> float:
    """El fondo de cambio que queda en el cajón al cerrar cada turno."""
    with conexion_db() as conexion:
        valor = leer(conexion, CLAVE_FONDO_CAMBIO)
        return float(valor) if valor is not None else 0.0


def actualizar_fondo_cambio(nuevo_valor: float):
    """Solo el Admin puede llamar a esto (se valida en la pantalla). Cambia la
    clave que deja la siembra de la primera vez: si faltara, no la crea."""
    with conexion_db() as conexion:
        guardar(conexion, CLAVE_FONDO_CAMBIO, str(round(nuevo_valor, 2)), crear_si_falta=False)
