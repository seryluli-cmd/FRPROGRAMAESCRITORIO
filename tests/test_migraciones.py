"""
tests/test_migraciones.py
===========================
El molde de las migraciones de la base (database_migraciones.py, CLAUDE.md,
regla 6). Hoy no hay ningún paso (VERSION_ESQUEMA = 1), pero el primero va a
correr sobre la base real del kiosko, con la plata adentro. Con pasos de mentira
estas pruebas vigilan que cada paso corra una sola vez, en orden, en su propia
transacción y con su versión anotada; que antes quede la copia "antes_de_migrar"
(que copias_repo nunca borra); y que una base de CYBERCONTROL o una de un
FRKiosko más nuevo no se abran, sin tocarlas.

Se ejecutan con:

    python -m unittest discover tests -p "test_migraciones.py"
"""

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

import database
import database_migraciones as migraciones
from repositories import copias_repo


class _ConCarpetaTemporal(unittest.TestCase):
    """Apunta la base a una carpeta temporal SIN crearla (a diferencia de
    base.BaseConBaseTemporal): cada prueba arma la base que necesita, sea de
    CYBERCONTROL, de un programa más nuevo o una del kiosko ya en uso."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._data_dir_original = database.DATA_DIR
        self._db_path_original = database.DB_PATH
        database.DATA_DIR = self._tmp.name
        database.DB_PATH = os.path.join(self._tmp.name, "kiosko_test.db")
        self.corridas = []

    def tearDown(self):
        database.DATA_DIR = self._data_dir_original
        database.DB_PATH = self._db_path_original
        self._tmp.cleanup()

    def _sql(self, *sentencias, parametros=()):
        """SQL suelto contra la base, por fuera del programa (como lo haría otro
        programa o una versión vieja/nueva de este)."""
        conexion = sqlite3.connect(database.DB_PATH)
        try:
            for sentencia in sentencias:
                conexion.execute(sentencia, parametros)
            conexion.commit()
        finally:
            conexion.close()

    def _leer(self, consulta, ruta=None):
        conexion = sqlite3.connect(ruta or database.DB_PATH)
        try:
            return conexion.execute(consulta).fetchall()
        finally:
            conexion.close()

    def _foto(self):
        """El esquema entero y la versión: lo que no cambia en una base sin tocar."""
        return (
            self._leer("SELECT type, name, sql FROM sqlite_master ORDER BY type, name"),
            self._version(),
        )

    def _version(self, ruta=None):
        return self._leer("PRAGMA user_version", ruta)[0][0]

    def _tablas(self):
        return {fila[0] for fila in self._leer("SELECT name FROM sqlite_master WHERE type = 'table'")}

    def _columnas(self, tabla, ruta=None):
        return {fila[1] for fila in self._leer(f"PRAGMA table_info({tabla})", ruta)}

    def _copias_antes_de_migrar(self):
        carpeta = copias_repo.carpeta_local()
        if not os.path.isdir(carpeta):
            return []
        return sorted(n for n in os.listdir(carpeta) if n.startswith(migraciones.PREFIJO_COPIA_ANTES_DE_MIGRAR))

    def _usar_pasos(self, pasos):
        """Como si el programa trajera estos pasos y VERSION_ESQUEMA fuera el último."""
        for parche in (
            mock.patch.object(migraciones, "VERSION_ESQUEMA", max(pasos)),
            mock.patch.dict(migraciones.PASOS, pasos, clear=True),
        ):
            parche.start()
            self.addCleanup(parche.stop)

    # Pasos de mentira, idempotentes como tienen que ser los de verdad.

    def _paso_columna_nota(self, conexion):
        self.corridas.append("nota")
        if "nota" not in {fila[1] for fila in conexion.execute("PRAGMA table_info(ventas)")}:
            conexion.execute("ALTER TABLE ventas ADD COLUMN nota TEXT")

    def _paso_tabla_avisos(self, conexion):
        self.corridas.append("avisos")
        conexion.execute("CREATE TABLE IF NOT EXISTS avisos (id INTEGER PRIMARY KEY, texto TEXT)")

    def _articulo_con_rubro(self):
        """Un artículo que apunta a un rubro: rubros pasa a ser una tabla MADRE con
        una hija, como ventas o articulos en el kiosko."""
        rubro_id = self._leer("SELECT id FROM rubros ORDER BY id LIMIT 1")[0][0]
        ahora = datetime.now().isoformat(timespec="seconds")
        self._sql(
            "INSERT INTO articulos (codigo, descripcion, rubro_id, fecha_creacion, fecha_modif) "
            "VALUES ('77', 'Agua', ?, ?, ?)",
            parametros=(rubro_id, ahora, ahora),
        )
        return rubro_id


class TestBasesQueNoSeAbren(_ConCarpetaTemporal):
    def test_una_base_de_cybercontrol_no_se_abre_ni_se_toca(self):
        for tabla in migraciones.TABLAS_DEL_PROGRAMA_ORIGINAL:
            with self.subTest(tabla=tabla):
                database.DB_PATH = os.path.join(self._tmp.name, f"cyber_{tabla}.db")
                self._sql(f"CREATE TABLE {tabla} (id INTEGER PRIMARY KEY)")
                antes = self._foto()
                with self.assertRaisesRegex(RuntimeError, "CYBERCONTROL"):
                    database.inicializar_base_de_datos()
                # Ni una tabla del kiosko: se rechaza antes de crear nada.
                self.assertEqual(self._foto(), antes)
        self.assertEqual(self._copias_antes_de_migrar(), [])

    def test_una_base_de_un_frkiosko_mas_nuevo_no_se_abre_ni_se_toca(self):
        database.inicializar_base_de_datos()
        # Como si un FRKiosko más nuevo hubiera sacado una tabla y subido la versión.
        self._sql("DROP TABLE sesiones", f"PRAGMA user_version = {migraciones.VERSION_ESQUEMA + 1}")
        antes = self._foto()

        with self.assertRaisesRegex(RuntimeError, "FRKiosko más nuevo"):
            database.inicializar_base_de_datos()

        # Hasta el 2026-10-28 se rechazaba recién después de los CREATE TABLE, que
        # le volvían a crear "sesiones" a la base del programa nuevo.
        self.assertEqual(self._foto(), antes)
        self.assertNotIn("sesiones", self._tablas())

    def test_migrar_base_tampoco_acepta_una_base_mas_nueva(self):
        database.inicializar_base_de_datos()
        self._sql(f"PRAGMA user_version = {migraciones.VERSION_ESQUEMA + 1}")
        conexion = database.get_connection()
        try:
            with self.assertRaisesRegex(RuntimeError, "FRKiosko más nuevo"):
                migraciones.migrar_base(conexion)
        finally:
            conexion.close()
        self.assertEqual(self._version(), migraciones.VERSION_ESQUEMA + 1)


class TestSinPasosPendientes(_ConCarpetaTemporal):
    def test_una_base_nueva_queda_con_la_version_del_programa(self):
        database.inicializar_base_de_datos()
        self.assertEqual(self._version(), migraciones.VERSION_ESQUEMA)
        self.assertEqual(self._copias_antes_de_migrar(), [])

    def test_migrar_dos_veces_no_cambia_nada(self):
        database.inicializar_base_de_datos()
        antes = self._foto()

        database.inicializar_base_de_datos()
        conexion = database.get_connection()
        try:
            migraciones.migrar_base(conexion)
            migraciones.migrar_base(conexion)
        finally:
            conexion.close()

        self.assertEqual(self._foto(), antes)
        self.assertEqual(self._copias_antes_de_migrar(), [])

    def test_cada_version_tiene_su_paso(self):
        # La 1 es el esquema de database_esquema.py; de ahí para arriba, un paso
        # por versión. Atrapa el olvido más fácil: sumar un paso sin subir
        # VERSION_ESQUEMA (no correría nunca) o subirla sin escribir el paso.
        self.assertEqual(set(migraciones.PASOS), set(range(2, migraciones.VERSION_ESQUEMA + 1)))
        for version, paso in migraciones.PASOS.items():
            self.assertTrue(callable(paso), version)


class TestConPasosDeMentira(_ConCarpetaTemporal):
    def setUp(self):
        super().setUp()
        database.inicializar_base_de_datos()  # una base de la versión 1, como la del kiosko

    def test_el_paso_corre_una_sola_vez_y_queda_anotado(self):
        self._usar_pasos({2: self._paso_columna_nota})

        database.inicializar_base_de_datos()
        self.assertEqual(self.corridas, ["nota"])
        self.assertEqual(self._version(), 2)
        self.assertIn("nota", self._columnas("ventas"))

        database.inicializar_base_de_datos()
        self.assertEqual(self.corridas, ["nota"])  # ya estaba anotado: no vuelve a correr
        self.assertEqual(len(self._copias_antes_de_migrar()), 1)  # ni se vuelve a copiar

    def test_antes_del_paso_queda_una_copia_que_nunca_se_borra(self):
        self._usar_pasos({2: self._paso_columna_nota})
        database.inicializar_base_de_datos()

        copias = self._copias_antes_de_migrar()
        self.assertEqual(len(copias), 1)
        ruta = os.path.join(copias_repo.carpeta_local(), copias[0])
        # Es la base de ANTES del paso: versión 1, sin la columna nueva y con sus datos.
        self.assertEqual(self._version(ruta), 1)
        self.assertNotIn("nota", self._columnas("ventas", ruta))
        self.assertEqual(self._leer("SELECT nombre FROM usuarios", ruta), [("Administrador",)])
        # copias_repo no la toma por automática, así que no la borra nunca, por
        # muchas copias automáticas que se junten.
        self.assertIsNone(copias_repo.momento_de_la_copia(copias[0]))
        automaticas = [
            copias_repo.nombre_de_copia(datetime(2026, 1, 1, 22) + timedelta(days=dia)) for dia in range(60)
        ]
        self.assertNotIn(copias[0], copias_repo.nombres_a_borrar(automaticas + copias))
        # Y no quedó nada a medias.
        self.assertEqual([n for n in os.listdir(copias_repo.carpeta_local()) if n.endswith(".parcial")], [])

    def test_una_base_nueva_corre_los_pasos_pero_sin_copia(self):
        self._usar_pasos({2: self._paso_columna_nota})
        database.DB_PATH = os.path.join(self._tmp.name, "nueva.db")

        database.inicializar_base_de_datos()

        self.assertEqual(self.corridas, ["nota"])
        self.assertEqual(self._version(), 2)
        self.assertIn("nota", self._columnas("ventas"))
        self.assertEqual(self._copias_antes_de_migrar(), [])  # no tenía nada que cuidar

    def test_los_pasos_corren_en_orden_desde_la_version_de_la_base(self):
        self._usar_pasos({3: self._paso_tabla_avisos, 2: self._paso_columna_nota})
        database.inicializar_base_de_datos()
        self.assertEqual(self.corridas, ["nota", "avisos"])
        self.assertEqual(self._version(), 3)

        # Una base que ya tenía el paso 2 solo corre el 3.
        self.corridas.clear()
        self._sql("DROP TABLE avisos", "PRAGMA user_version = 2")
        database.inicializar_base_de_datos()
        self.assertEqual(self.corridas, ["avisos"])
        self.assertEqual(self._version(), 3)

    def test_un_paso_que_falla_no_deja_nada_a_medias(self):
        def paso_que_se_corta(conexion):
            conexion.execute("CREATE TABLE a_medias (id INTEGER PRIMARY KEY)")
            conexion.execute("ALTER TABLE ventas ADD COLUMN otra TEXT")
            raise RuntimeError("se cortó la luz")

        self._usar_pasos({2: self._paso_columna_nota, 3: paso_que_se_corta})
        with self.assertRaisesRegex(RuntimeError, "se cortó la luz"):
            database.inicializar_base_de_datos()

        # El 2 quedó hecho y anotado; del 3 no quedó nada: sin el BEGIN, el
        # CREATE y el ALTER se habrían grabado igual (trampa a).
        self.assertEqual(self._version(), 2)
        self.assertNotIn("a_medias", self._tablas())
        self.assertNotIn("otra", self._columnas("ventas"))

        # Arreglado el paso, el próximo arranque sigue desde el 3.
        migraciones.PASOS[3] = self._paso_tabla_avisos
        database.inicializar_base_de_datos()
        self.assertEqual(self.corridas, ["nota", "avisos"])
        self.assertEqual(self._version(), 3)
        # Una copia por cada arranque que tenía pasos pendientes, sin pisarse
        # aunque sean del mismo segundo.
        self.assertEqual(len(self._copias_antes_de_migrar()), 2)

    def test_un_paso_puede_reconstruir_una_tabla_madre(self):
        # La receta de la regla 6, con rubros como tabla madre de articulos. Con
        # las claves foráneas prendidas, el DROP TABLE de la madre falla: el
        # molde las apaga ANTES del BEGIN (trampa b).
        rubro_id = self._articulo_con_rubro()

        def paso_reconstruir_rubros(conexion):
            if "orden" in {fila[1] for fila in conexion.execute("PRAGMA table_info(rubros)")}:
                return
            conexion.execute("""
                CREATE TABLE rubros_nueva (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL UNIQUE,
                    orden INTEGER NOT NULL DEFAULT 0
                )
            """)
            conexion.execute("INSERT INTO rubros_nueva (id, nombre) SELECT id, nombre FROM rubros")
            conexion.execute("DROP TABLE rubros")
            conexion.execute("ALTER TABLE rubros_nueva RENAME TO rubros")

        self._usar_pasos({2: paso_reconstruir_rubros})
        conexion = database.get_connection()
        try:
            migraciones.migrar_base(conexion)
            # Las claves foráneas vuelven a quedar prendidas al terminar.
            self.assertEqual(conexion.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        finally:
            conexion.close()

        self.assertEqual(self._version(), 2)
        self.assertIn("orden", self._columnas("rubros"))
        self.assertEqual(self._leer("PRAGMA foreign_key_check"), [])
        self.assertEqual(self._leer("SELECT rubro_id FROM articulos WHERE codigo = '77'"), [(rubro_id,)])
        sql_articulos = self._leer("SELECT sql FROM sqlite_master WHERE name = 'articulos'")[0][0]
        self.assertIn("REFERENCES rubros(id)", sql_articulos)  # la hija sigue apuntando a "rubros"

    def test_un_paso_que_deja_referencias_rotas_no_se_hace(self):
        rubro_id = self._articulo_con_rubro()

        def paso_que_borra_un_rubro_en_uso(conexion):
            conexion.execute("DELETE FROM rubros WHERE id = ?", (rubro_id,))

        self._usar_pasos({2: paso_que_borra_un_rubro_en_uso})
        with self.assertRaisesRegex(RuntimeError, "no se hizo"):
            database.inicializar_base_de_datos()

        self.assertEqual(self._version(), 1)
        self.assertEqual(self._leer(f"SELECT COUNT(*) FROM rubros WHERE id = {rubro_id}"), [(1,)])

    def test_un_paso_que_hace_commit_por_su_cuenta_se_frena(self):
        def paso_que_comitea(conexion):
            conexion.execute("CREATE TABLE IF NOT EXISTS avisos (id INTEGER PRIMARY KEY)")
            conexion.commit()

        self._usar_pasos({2: paso_que_comitea, 3: self._paso_columna_nota})
        with self.assertRaisesRegex(RuntimeError, "commit por su cuenta"):
            database.inicializar_base_de_datos()

        # No se anota y no sigue con el 3: el próximo arranque lo vuelve a correr.
        self.assertEqual(self._version(), 1)
        self.assertEqual(self.corridas, [])

    def test_si_la_copia_no_se_puede_hacer_se_sigue_y_queda_en_el_log(self):
        def copia_que_se_queda_sin_lugar(destino):
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            with open(destino, "wb") as archivo:
                archivo.write(b"a medias")
            raise OSError(28, "No queda lugar en el disco")

        self._usar_pasos({2: self._paso_columna_nota})
        with mock.patch.object(database, "_backup_consistente", side_effect=copia_que_se_queda_sin_lugar):
            database.inicializar_base_de_datos()

        self.assertEqual(self._version(), 2)
        self.assertEqual(self._copias_antes_de_migrar(), [])  # ni una copia a medias que parezca buena
        with open(os.path.join(database.DATA_DIR, "errores.log"), encoding="utf-8") as log:
            self.assertIn("antes de actualizarla", log.read())


if __name__ == "__main__":
    unittest.main()
