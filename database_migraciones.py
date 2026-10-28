"""
database_migraciones.py
=======================
Las versiones del esquema de FRKiosko y los pasos que llevan una base vieja a la
versión de este programa (CLAUDE.md, regla 6). Las corre
database_esquema.inicializar_base_de_datos en cada arranque. La base de
CYBERCONTROL no se importa ni se modifica: se rechaza.

La versión de una base vive adentro del archivo (PRAGMA user_version): 0 es una
base recién creada que todavía no la anotó; 1 es el esquema con que arrancó el
programa el 2026-10-27 (lo crea database_esquema.py, sin ningún paso). Desde ese
día migrar_base anota la versión cada vez que abre una base, así que toda base que
ya usó el programa tiene 1 o más.

Cómo se agrega un paso (una columna nueva, un índice sobre ella, o reconstruir una
tabla para cambiarle un CHECK):
  1. Escribir `_paso_N(conexion)` acá abajo. Tiene que ser idempotente: mira si lo
     suyo ya está hecho (PRAGMA table_info, sqlite_master) y, si está, no hace
     nada. Corre también sobre una base NUEVA (ver migrar_base), donde
     database_esquema.py pudo haber creado ya lo mismo.
  2. Sumarlo a PASOS ({N: _paso_N}) y subir VERSION_ESQUEMA a N. Hay que hacer
     las dos cosas: un paso sin subir la versión no corre nunca, y
     tests/test_migraciones.py exige un paso por versión.
  3. El paso no hace commit ni rollback, no usa executescript (ver la trampa d) y
     no toca PRAGMA foreign_keys: corre dentro de la transacción que abre
     _correr_paso, con las claves foráneas ya apagadas, una sentencia por
     conexion.execute. Si falla, levanta la excepción y no queda nada a medias.
  4. Su prueba (regla 14): una base de la versión anterior, con datos, pasa a la
     nueva sin perder nada, y correrlo dos veces no cambia nada.

Trampas de SQLite (probadas con un script el 2026-10-28, Python 3.12.3 y SQLite
3.45.1: no son de memoria):
  (a) Un CREATE TABLE o un ALTER TABLE NO se deshace con rollback() si la
      transacción no se abrió con un BEGIN explícito. El módulo sqlite3 de Python
      abre la transacción solo antes de un INSERT, UPDATE o DELETE; un CREATE,
      ALTER o DROP que va primero se graba en el acto, y un paso que falla a la
      mitad dejaría la base a medio cambiar. Por eso _correr_paso hace el BEGIN.
  (b) PRAGMA foreign_keys = OFF no hace nada dentro de una transacción (ni da
      error: sigue en 1). Va ANTES del BEGIN. Sin eso, borrar una tabla madre
      (ventas, articulos, usuarios) que tiene hijas falla con "FOREIGN KEY
      constraint failed", y es justo lo que pide la receta de la regla 6 para
      reconstruirla: crear <tabla>_nueva, copiar, borrar la vieja y recién ahí
      renombrar (un RENAME primero re-apunta las hijas a la renombrada).
  (c) database_esquema.py corre ANTES que los pasos. Un índice sobre una columna
      que agrega un paso va en el paso, no ahí: en una base vieja la columna
      todavía no existe, el CREATE INDEX falla con "no such column" y el programa
      no abre.
  (d) conexion.executescript() hace COMMIT de lo que esté abierto ANTES de
      correr, aunque se haya hecho el BEGIN: lo que el paso hizo hasta ahí queda
      grabado, y si después falla, el rollback ya no lo deshace (la base queda a
      medio cambiar y con la versión vieja). En un paso, nada de executescript.
      _correr_paso se da cuenta (ver "hizo commit por su cuenta") y lo dice.
"""

import os
import sqlite3
from datetime import datetime

import database
from errores import registrar_error


VERSION_ESQUEMA = 1

# {versión: paso}: el paso que lleva una base de la versión anterior a esa. La 1
# no tiene paso: es el esquema de database_esquema.py. Vacío hasta el primer
# cambio de esquema con el programa ya en uso en el kiosko.
PASOS = {}

TABLAS_DEL_PROGRAMA_ORIGINAL = ("estaciones", "miembros", "sesiones_pc", "bonos_tiempo")

# Con este nombre copias_repo nunca borra la copia de antes de migrar: solo toca
# las automáticas, frkiosko_AAAA-MM-DD_HHMMSS.db (copias_repo._PATRON_COPIA).
PREFIJO_COPIA_ANTES_DE_MIGRAR = "antes_de_migrar_"


def version_de_la_base(conexion) -> int:
    return conexion.execute("PRAGMA user_version").fetchone()[0]


def _exigir_version_conocida(conexion):
    """RuntimeError si la base la anotó un FRKiosko más nuevo que este. Un
    programa viejo no sabe qué cambió el nuevo: abriéndola podría volver a crear
    una tabla que el nuevo sacó o grabar ventas sin las columnas nuevas."""
    version = version_de_la_base(conexion)
    if version > VERSION_ESQUEMA:
        raise RuntimeError(
            f"Esta base es de un FRKiosko más nuevo (versión {version} de la base; este "
            f"programa llega hasta la {VERSION_ESQUEMA}). Abrila con el FRKiosko nuevo: "
            "con este se podría dañar."
        )


def comprobar_base_kiosko(conexion):
    """
    Lo primero de inicializar_base_de_datos, antes de crear nada: una base de
    CYBERCONTROL o una de un FRKiosko más nuevo no se abre. Hasta el 2026-10-28 la
    versión se miraba recién en migrar_base, DESPUÉS de los CREATE TABLE, que ya
    podían haber tocado la base del programa más nuevo.
    """
    nombres = {fila[0] for fila in conexion.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if nombres.intersection(TABLAS_DEL_PROGRAMA_ORIGINAL):
        raise RuntimeError(
            "Esta base pertenece a CYBERCONTROL. Kiosko usa una base nueva y separada."
        )
    _exigir_version_conocida(conexion)


def pasos_pendientes(version: int) -> list:
    """[(versión, paso)] de los pasos que le faltan a una base de `version`, en orden."""
    return [(numero, PASOS[numero]) for numero in sorted(PASOS) if version < numero <= VERSION_ESQUEMA]


def migrar_base(conexion):
    """
    Lleva la base a VERSION_ESQUEMA corriendo en orden los pasos que le faltan,
    cada uno en su transacción y con su versión anotada en esa misma transacción:
    si se corta la luz entre dos pasos, el próximo arranque sigue desde el que
    faltaba.

    Antes del primer paso pendiente deja una copia de la base (ver
    _copia_antes_de_migrar). Una base nueva (versión 0) corre los pasos igual
    (así cada paso corre en cada prueba, que arranca con una base nueva) pero sin
    copia: no tiene nada que cuidar.

    `conexion` tiene que ser a database.DB_PATH, la que abre
    inicializar_base_de_datos: la copia se saca de ese archivo.
    """
    _exigir_version_conocida(conexion)
    # Lo que haya dejado abierto quien llama se guarda antes: con una transacción
    # abierta, el BEGIN de cada paso fallaría y el foreign_keys = OFF no haría nada
    # (trampa b). Hoy inicializar_base_de_datos solo corre CREATE antes, que no
    # abren transacción, así que no hay nada que guardar.
    if conexion.in_transaction:
        conexion.commit()
    actual = version_de_la_base(conexion)
    pendientes = pasos_pendientes(actual)
    if pendientes and actual > 0:
        _copia_antes_de_migrar(actual)
    for version, paso in pendientes:
        _correr_paso(conexion, version, paso)
    if version_de_la_base(conexion) < VERSION_ESQUEMA:
        if actual > 0:
            # Se subió VERSION_ESQUEMA sin sumar su paso a PASOS: anotarla sin
            # correr nada dejaría la base marcada como nueva sin los cambios.
            raise RuntimeError(
                f"A la base le falta un paso para llegar a la versión {VERSION_ESQUEMA} "
                f"(llegó hasta la {version_de_la_base(conexion)}): no se tocó."
            )
        # Una base nueva sin pasos que correr: database_esquema.py ya la creó con
        # el esquema de este programa.
        conexion.execute(f"PRAGMA user_version = {int(VERSION_ESQUEMA)}")


def _correr_paso(conexion, version: int, paso):
    """
    Un paso en UNA transacción, con su versión anotada en la misma: o queda hecho
    y anotado, o no pasó nada (PRAGMA user_version también se deshace con el
    rollback). Las claves foráneas van apagadas para que un paso pueda reconstruir
    una tabla madre; a cambio, al final se mira que el paso no haya dejado
    referencias rotas que no estuvieran antes (el control que pide SQLite para esa
    receta). Se cuentan las de antes para que una base con alguna rota de antes no
    quede sin poder abrir por algo que el paso no hizo.
    """
    conexion.execute("PRAGMA foreign_keys = OFF")  # trampa (b): antes del BEGIN
    try:
        conexion.execute("BEGIN")  # trampa (a): sin esto, un CREATE/ALTER del paso no se deshace
        try:
            rotas_antes = _referencias_rotas(conexion)
            paso(conexion)
            if not conexion.in_transaction:
                raise RuntimeError(
                    f"El paso {version} de la base hizo commit por su cuenta: lo hace migrar_base."
                )
            if _referencias_rotas(conexion) > rotas_antes:
                raise RuntimeError(
                    f"El paso {version} de la base dejaba datos sin su venta, artículo o usuario: "
                    "no se hizo."
                )
            conexion.execute(f"PRAGMA user_version = {int(version)}")
            conexion.commit()
        except BaseException as error:
            seguia_abierta = conexion.in_transaction
            conexion.rollback()
            if not seguia_abierta and not isinstance(error, RuntimeError):
                # Falló DESPUÉS de un commit propio (un executescript, trampa d): lo
                # de antes del commit quedó grabado y el rollback ya no lo deshace.
                raise RuntimeError(
                    f"El paso {version} de la base hizo commit por su cuenta y después falló: "
                    "lo que alcanzó a hacer quedó grabado. Volvé a la copia antes_de_migrar_ "
                    "de data_fr/backups."
                ) from error
            raise
    finally:
        conexion.execute("PRAGMA foreign_keys = ON")


def _referencias_rotas(conexion) -> int:
    """Cuántas filas apuntan a una venta, artículo, usuario... que no existe."""
    return len(conexion.execute("PRAGMA foreign_key_check").fetchall())


def _copia_antes_de_migrar(version: int):
    """
    Copia de la base antes del primer paso que le falta, en la carpeta de las
    copias (data_fr/backups), con la versión en el nombre
    (antes_de_migrar_v1_AAAAMMDD_HHMMSS.db). Ojo: database_esquema.py ya corrió,
    así que puede traer las tablas nuevas que se crean sin paso, vacías (un
    programa viejo las ignora). Los pasos corren sobre la base real
    del kiosko, con la plata adentro: si un paso tiene un error de lógica (copia
    mal una columna) el rollback no lo ve, y esta copia es la vuelta atrás.

    Se graba como .parcial y se renombra al final, como las copias automáticas:
    un corte a mitad de camino no deja un .db a medias que parezca bueno. Nunca
    pisa otra (si ya hay una de ese mismo segundo, le suma _2).

    Es un extra, no un requisito (igual que en CYBERCONTROL): cada paso se deshace
    solo si falla y las copias automáticas siguen estando. Si esta no se puede
    hacer (disco lleno, sin permiso) queda anotado en data_fr/errores.log y se
    sigue, en vez de dejar el kiosko sin poder abrir el programa. Devuelve la ruta
    de la copia, o None si no se pudo.

    Si un paso falla, cada arranque vuelve a copiar la base entera (y estas
    copias no se borran solas): si se reintenta muchas veces, conviene borrar a
    mano las repetidas de la misma versión.
    """
    carpeta = database.carpeta_de_copias()
    nombre = f"{PREFIJO_COPIA_ANTES_DE_MIGRAR}v{int(version)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    destino = os.path.join(carpeta, f"{nombre}.db")
    otra = 2
    while os.path.exists(destino):
        destino = os.path.join(carpeta, f"{nombre}_{otra}.db")
        otra += 1
    a_medias = destino + ".parcial"
    try:
        database._backup_consistente(a_medias)
        os.replace(a_medias, destino)
    except (OSError, sqlite3.Error) as error:
        try:
            os.remove(a_medias)
        except OSError:
            pass
        registrar_error(error, "Copia de la base antes de actualizarla (se siguió sin la copia)")
        return None
    return destino
