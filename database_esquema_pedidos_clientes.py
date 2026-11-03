"""
database_esquema_pedidos_clientes.py
=====================================
Los PEDIDOS DE CLIENTES (pedido del dueño, 2026-11-03; reglas en
repositories/pedidos_clientes_repo.py): mercadería que NO tenemos y que los
clientes vienen a buscar. En archivo aparte, como los pedidos de impresiones. Las
crea database_esquema.inicializar_base_de_datos con CREATE TABLE IF NOT EXISTS: son
tablas nuevas, no cambian ninguna que ya estuviera, así que una base vieja las
recibe vacías sin paso de migración (un FRKiosko viejo las ignora).

No tienen nada que ver con pedidos_impresion (Gestión Impresiones): acá no hay
plata ni artículos, solo lo que pidieron y cuántas veces.
"""

import dominio


def crear_tablas_pedidos_clientes(cursor, valores_sql):
    """Crea las dos tablas si todavía no existen. `valores_sql` es
    database._valores_sql (se recibe para no importar database desde acá, como en
    database_esquema_pedidos)."""

    # Un renglón de la lista: un producto que piden.
    # - producto: como se ve (lo que escribió quien lo anotó primero, limpio con
    #   dominio.pedido_cliente_limpio; el Admin lo puede corregir con Renombrar).
    # - clave: con qué se compara (dominio.clave_pedido_cliente): "Mantecól" y
    #   "MANTECOL " caen en el mismo renglón.
    # - fecha / creado_por: cuándo y quién abrió el renglón (la primera vez que se
    #   pidió; después de Juntar, la primera vez de verdad sale de las veces).
    # - traido_por / fecha_traido: quién apretó "YA LO TRAJIMOS" y cuándo.
    # - borrado_por / fecha_borrado: el Admin que lo sacó por anotado por error o
    #   porque lo juntó con otro; en ese caso, juntado_con es el renglón que se
    #   quedó con sus clientes. Nunca se borra la fila (regla 7).
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS pedidos_clientes (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha          TEXT NOT NULL,
            producto       TEXT NOT NULL,
            clave          TEXT NOT NULL,
            creado_por     INTEGER NOT NULL REFERENCES usuarios(id),
            estado         TEXT NOT NULL CHECK (estado IN ({valores_sql(dominio.ESTADOS_PEDIDO_CLIENTE)})),
            traido_por     INTEGER REFERENCES usuarios(id),
            fecha_traido   TEXT,
            borrado_por    INTEGER REFERENCES usuarios(id),
            fecha_borrado  TEXT,
            juntado_con    INTEGER REFERENCES pedidos_clientes(id)
        )
    """)
    # No puede haber dos renglones PENDIENTES del mismo producto (si no, los
    # clientes se repartirían entre los dos); sí uno pendiente y varios ya traídos,
    # porque lo que se vuelve a pedir después de traerlo arranca un renglón nuevo.
    # El valor va escrito porque el WHERE de un índice no acepta parámetros, pero
    # sale de dominio igual que los CHECK.
    cursor.execute(f"""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_pedidos_clientes_pendiente
        ON pedidos_clientes(clave)
        WHERE estado = {valores_sql((dominio.PEDIDO_CLIENTE_PENDIENTE,))}
    """)

    # Una fila por cliente que lo pidió: cuándo y qué operador lo anotó (el que
    # estaba en el mostrador). La cantidad de clientes es cuántas filas tiene su
    # renglón: no se guarda aparte, así nunca queda un número que no coincide.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pedidos_clientes_veces (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id   INTEGER NOT NULL REFERENCES pedidos_clientes(id),
            fecha       TEXT NOT NULL,
            usuario_id  INTEGER NOT NULL REFERENCES usuarios(id)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pedidos_clientes_veces_pedido ON pedidos_clientes_veces(pedido_id)"
    )
