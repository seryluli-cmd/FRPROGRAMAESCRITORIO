"""
database_esquema_pedidos.py
============================
Los pedidos de impresiones con seña de GESTIÓN IMPRESIONES (pedido del dueño,
2026-11-02; reglas en repositories/pedidos_impresion_repo.py). En archivo aparte,
como las cajas y la cola de envíos. La crea database_esquema.inicializar_base_de_datos
con CREATE TABLE IF NOT EXISTS: es una tabla nueva, no cambia ninguna que ya
estuviera, así que una base vieja la recibe vacía sin paso de migración (un FRKiosko
viejo la ignora).

La plata NO vive acá: la seña y lo que se paga al retirar son ventas de kiosko
comunes (con su caja, sus pagos y su anulación); el pedido solo apunta a ellas.
"""

import dominio


def crear_tabla_pedidos_impresion(cursor, valores_sql):
    """Crea la tabla si todavía no existe. `valores_sql` es database._valores_sql
    (se recibe para no importar database desde acá, como en database_esquema_cajas)."""

    # Una fila por pedido.
    # - hojas / precio_hoja / total / sena: lo acordado al tomarlo. El precio queda
    #   fijo: si después cambia el de Impresiones, el cliente paga lo que se le dijo.
    # - tomado_por / venta_sena_id: quién lo tomó (el operador del mostrador en ese
    #   momento) y la venta de la seña, que quedó en la caja abierta entonces.
    # - entregado_por / fecha_entrega / venta_entrega_id: quién lo entregó y la venta
    #   de lo que faltaba (con total 0 si lo había pagado entero).
    # - cerrado_por / fecha_cerrado / motivo: quién lo dio por perdido o lo anuló.
    # - avisado: la última vez que se le abrió el WhatsApp de "ya está listo".
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS pedidos_impresion (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha             TEXT NOT NULL,
            nombre            TEXT NOT NULL,
            telefono          TEXT NOT NULL DEFAULT '',
            hojas             INTEGER NOT NULL CHECK (hojas > 0),
            precio_hoja       REAL NOT NULL,
            total             REAL NOT NULL,
            sena              REAL NOT NULL CHECK (sena > 0),
            tomado_por        INTEGER NOT NULL REFERENCES usuarios(id),
            venta_sena_id     INTEGER NOT NULL REFERENCES ventas(id),
            estado            TEXT NOT NULL CHECK (estado IN ({valores_sql(dominio.ESTADOS_PEDIDO)})),
            entregado_por     INTEGER REFERENCES usuarios(id),
            fecha_entrega     TEXT,
            venta_entrega_id  INTEGER REFERENCES ventas(id),
            cerrado_por       INTEGER REFERENCES usuarios(id),
            fecha_cerrado     TEXT,
            motivo            TEXT,
            avisado           TEXT
        )
    """)
    # Anular una venta pregunta si es de un pedido (ventas_repo.anular_venta).
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pedidos_impresion_sena ON pedidos_impresion(venta_sena_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pedidos_impresion_entrega ON pedidos_impresion(venta_entrega_id)")
