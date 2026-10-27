"""Esquema de una instalación nueva de Kiosko, sin datos de Control de PCs."""

import dominio


def inicializar_base_de_datos():
    """Crea las tablas del kiosko y aplica migraciones idempotentes."""
    from database import get_connection, _cargar_datos_iniciales, _valores_sql
    from database_migraciones import comprobar_base_kiosko, migrar_base
    from database_esquema_cajas import crear_tablas_de_cajas
    from database_esquema_envios import crear_tabla_envios_pwa

    conexion = get_connection()
    try:
        comprobar_base_kiosko(conexion)
        cursor = conexion.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS usuarios (
                id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre                   TEXT NOT NULL,
                clave_hash               TEXT NOT NULL,
                rol                      TEXT NOT NULL CHECK (rol IN ({_valores_sql(dominio.ROLES)})),
                activo                   INTEGER NOT NULL DEFAULT 1,
                fecha_creacion           TEXT NOT NULL,
                permiso_articulos        INTEGER NOT NULL DEFAULT 0,
                permiso_compras          INTEGER NOT NULL DEFAULT 0,
                permiso_consulta_ventas  INTEGER NOT NULL DEFAULT 0,
                permiso_reportes         INTEGER NOT NULL DEFAULT 0,
                permiso_control_cierres  INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS marcas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rubros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS articulos (
                codigo TEXT PRIMARY KEY,
                descripcion TEXT NOT NULL,
                marca_id INTEGER REFERENCES marcas(id),
                rubro_id INTEGER REFERENCES rubros(id),
                precio_venta REAL NOT NULL DEFAULT 0,
                precio_compra REAL NOT NULL DEFAULT 0,
                stock INTEGER NOT NULL DEFAULT 0,
                stock_minimo INTEGER NOT NULL DEFAULT 0,
                fecha_creacion TEXT NOT NULL,
                fecha_modif TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS compras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                usuario_id INTEGER NOT NULL REFERENCES usuarios(id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS compra_detalle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                compra_id INTEGER NOT NULL REFERENCES compras(id),
                articulo_codigo TEXT NOT NULL REFERENCES articulos(codigo),
                cantidad INTEGER NOT NULL,
                costo_unitario REAL NOT NULL,
                stock_antes INTEGER NOT NULL,
                stock_despues INTEGER NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ajustes_stock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                articulo_codigo TEXT NOT NULL REFERENCES articulos(codigo),
                fecha TEXT NOT NULL,
                usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
                stock_anterior INTEGER NOT NULL,
                stock_nuevo INTEGER NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cambios_codigo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                articulo_codigo TEXT NOT NULL REFERENCES articulos(codigo),
                fecha TEXT NOT NULL,
                usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
                codigo_anterior TEXT NOT NULL,
                codigo_nuevo TEXT NOT NULL
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
                turno TEXT NOT NULL CHECK (turno IN ({_valores_sql(dominio.TURNOS)})),
                total REAL NOT NULL,
                estado TEXT NOT NULL DEFAULT '{dominio.VENTA_CONFIRMADA}'
                    CHECK (estado IN ({_valores_sql(dominio.ESTADOS_VENTA)})),
                anulada_por INTEGER REFERENCES usuarios(id),
                anulada_fecha TEXT,
                anulada_motivo TEXT,
                origen TEXT NOT NULL DEFAULT '{dominio.ORIGEN_KIOSKO}'
                    CHECK (origen IN ({_valores_sql(dominio.ORIGENES_VENTA)}))
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS venta_detalle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venta_id INTEGER NOT NULL REFERENCES ventas(id),
                articulo_codigo TEXT NOT NULL REFERENCES articulos(codigo),
                descripcion TEXT NOT NULL,
                cantidad INTEGER NOT NULL,
                precio_unitario REAL NOT NULL,
                subtotal REAL NOT NULL
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS venta_pagos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venta_id INTEGER NOT NULL REFERENCES ventas(id),
                metodo TEXT NOT NULL CHECK (metodo IN ({_valores_sql(dominio.METODOS_PAGO)})),
                monto REAL NOT NULL
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS cierres_turno (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                turno TEXT NOT NULL CHECK (turno IN ({_valores_sql(dominio.TURNOS)})),
                usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
                fecha_cierre TEXT NOT NULL,
                fondo_cambio REAL NOT NULL,
                ventas_efectivo REAL NOT NULL,
                ventas_digital REAL NOT NULL,
                monto_a_retirar REAL NOT NULL,
                monto_contado REAL,
                diferencia REAL,
                verificado_por INTEGER REFERENCES usuarios(id),
                fecha_verificacion TEXT,
                kiosko_efectivo REAL NOT NULL DEFAULT 0,
                kiosko_digital REAL NOT NULL DEFAULT 0
            )
        """)
        # Un ingreso remoto se distingue por desde_ip; la misma tabla sirve
        # para el historial de ingresos del mostrador.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sesiones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
                fecha_hora TEXT NOT NULL,
                desde_ip TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            )
        """)

        crear_tablas_de_cajas(cursor, _valores_sql)
        crear_tabla_envios_pwa(cursor, _valores_sql)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ventas_turno ON ventas(turno, fecha)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_venta_detalle_venta ON venta_detalle(venta_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_venta_pagos_venta ON venta_pagos(venta_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_venta_detalle_articulo ON venta_detalle(articulo_codigo)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_compra_detalle_articulo ON compra_detalle(articulo_codigo)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_compra_detalle_compra ON compra_detalle(compra_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ajustes_stock_articulo ON ajustes_stock(articulo_codigo, fecha)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cambios_codigo_articulo ON cambios_codigo(articulo_codigo, fecha)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sesiones_fecha ON sesiones(fecha_hora)")
        migrar_base(conexion)
        conexion.commit()
        _cargar_datos_iniciales(conexion)
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()
