"""
tests/test_base_de_prueba.py
==============================
La base de prueba (armar_base_de_prueba.py, pedido del dueño 2026-10-28) y la
opción `--base` de main.py para abrirla: que lo que arma cuadre como lo dejaría
el programa (una caja por turno, ninguna venta fuera de su caja, la plata de los
cierres igual a la de las ventas, el cierre forzoso que hace el mostrador solo),
que nunca pise una carpeta que no armó y que al terminar (o al fallar) deje el
reloj y la base del programa como estaban.

Se ejecutan con:

    python -m unittest discover tests
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import armar_base_de_prueba  # noqa: E402
import database  # noqa: E402
import dominio  # noqa: E402
import main  # noqa: E402
from repositories import ventas_repo  # noqa: E402
from turnos import turno_vencimiento, turnos_del_dia  # noqa: E402

_HASTA = date(2026, 10, 20)  # martes: entran dos lunes (12 y 19)
_DIAS = 10
_SEMILLAS = (2, 3, 4)  # con estas, antes del arreglo una caja vieja vendía el turno siguiente
# Que en pocos días pase de todo: olvidos, cierres forzosos, relevos, reemplazos,
# ventas sin caja y el cambio siempre mal contado.
_SEGUIDO = {"olvido": 0.3, "forzoso": 0.3, "relevo": 0.4, "reemplazo": 0.2, "anulada": 0.05,
            "venta_sin_caja": 0.3, "cambio_mal_contado": 1.0}
_COLUMNAS_CON_FECHA = (
    ("ventas", "fecha"), ("cierres_turno", "fecha_cierre"), ("cajas", "abierta_en"),
    ("relevos_caja", "fecha"), ("sesiones", "fecha_hora"), ("compras", "fecha"),
    ("verificaciones_cierre", "fecha"),
)


def _sin_avisos(*_args):
    pass


def _armar(carpeta, semilla=3, dias=_DIAS, escala=0.1):
    with mock.patch.dict(armar_base_de_prueba.PROBABILIDADES, _SEGUIDO):
        return armar_base_de_prueba.armar(carpeta, dias=dias, semilla=semilla, escala=escala, hasta=_HASTA,
                                          avisar=_sin_avisos)


def _modulos_con_el_reloj_simulado():
    return [nombre for nombre, modulo in list(sys.modules.items())
            if getattr(modulo, "datetime", None) is armar_base_de_prueba._RelojDeLaSimulacion]


class TestLaBaseCuadra(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.antes = (database.DATA_DIR, database.DB_PATH, database.get_connection)
        cls.bases = {}
        for semilla in _SEMILLAS:
            carpeta = os.path.join(cls._tmp.name, f"prueba_{semilla}")
            resumen = _armar(carpeta, semilla)
            cls.bases[semilla] = (carpeta, resumen, sqlite3.connect(os.path.join(carpeta, "kiosko.db")))

    @classmethod
    def tearDownClass(cls):
        for _, _, conexion in cls.bases.values():
            conexion.close()
        cls._tmp.cleanup()

    def _bases(self):
        """[(semilla, (carpeta, resumen, uno))]: `uno(sql, *parámetros)` es el
        primer valor de una consulta sobre esa base."""
        return [
            (semilla, (carpeta, resumen, lambda sql, *p, c=conexion: c.execute(sql, p).fetchone()[0]))
            for semilla, (carpeta, resumen, conexion) in self.bases.items()
        ]

    def test_una_caja_por_turno_y_ninguna_abierta(self):
        simulados = {((_HASTA - timedelta(days=d)).isoformat(), turno)
                     for d in range(_DIAS) for turno in turnos_del_dia(_HASTA - timedelta(days=d))}
        for semilla, (_, _, uno) in self._bases():
            with self.subTest(semilla=semilla):
                self.assertEqual(uno("SELECT COUNT(*) FROM cajas"), len(simulados))
                self.assertEqual(uno("SELECT COUNT(DISTINCT fecha || '|' || turno) FROM cajas"), len(simulados))
                self.assertEqual(uno("SELECT COUNT(*) FROM cajas WHERE cierre_id IS NULL"), 0)

    def test_ninguna_venta_fuera_de_su_caja(self):
        for semilla, (_, _, uno) in self._bases():
            with self.subTest(semilla=semilla):
                self.assertEqual(uno(
                    "SELECT COUNT(*) FROM ventas JOIN ventas_caja ON ventas_caja.venta_id = ventas.id "
                    "JOIN cajas ON cajas.id = ventas_caja.caja_id "
                    "JOIN cierres_turno ON cierres_turno.id = cajas.cierre_id "
                    "WHERE ventas.fecha < cajas.abierta_en OR ventas.fecha > cierres_turno.fecha_cierre"
                ), 0)
                # tampoco la de quien recibe la caja antes de recibirla
                self.assertEqual(uno(
                    "SELECT COUNT(*) FROM ventas JOIN ventas_caja ON ventas_caja.venta_id = ventas.id "
                    "JOIN relevos_caja ON relevos_caja.caja_id = ventas_caja.caja_id "
                    "WHERE ventas.usuario_id = relevos_caja.a_usuario_id AND ventas.fecha < relevos_caja.fecha"
                ), 0)

    def test_la_plata_de_los_cierres_es_la_de_las_ventas(self):
        for semilla, (_, _, uno) in self._bases():
            with self.subTest(semilla=semilla):
                en_cierres = uno("SELECT ROUND(SUM(ventas_efectivo + ventas_digital), 2) FROM cierres_turno")
                cobrado = uno(
                    "SELECT ROUND(SUM(venta_pagos.monto), 2) FROM venta_pagos "
                    "JOIN ventas ON ventas.id = venta_pagos.venta_id WHERE ventas.estado = ?",
                    dominio.VENTA_CONFIRMADA,
                )
                self.assertGreater(cobrado, 0)
                self.assertEqual(en_cierres, cobrado)

    def test_ninguna_caja_pasa_su_cierre_forzoso(self):
        # El mostrador cierra solo la caja a la hora del fin de su turno:
        # ninguna puede cerrarse después (ni seguir vendiendo el turno siguiente).
        for semilla, (carpeta, resumen, conexion) in self.bases.items():
            with self.subTest(semilla=semilla):
                cajas = conexion.execute(
                    "SELECT cajas.id, cajas.fecha, cajas.turno, cierres_turno.fecha_cierre FROM cajas "
                    "JOIN cierres_turno ON cierres_turno.id = cajas.cierre_id"
                ).fetchall()
                tarde = [caja_id for caja_id, fecha, turno, cerrada in cajas
                         if datetime.fromisoformat(cerrada) > turno_vencimiento(fecha, turno) + timedelta(minutes=1)]
                self.assertEqual(tarde, [])

    def test_se_cierra_sola_la_caja_vieja_de_quien_sigue_atendiendo(self):
        # La que se olvidó de cerrar atiende también el turno siguiente: el
        # mostrador cierra su caja a la hora y ella abre otra sin contar.
        for semilla, (_, _, uno) in self._bases():
            with self.subTest(semilla=semilla):
                self.assertGreater(uno(
                    "SELECT COUNT(*) FROM cajas AS vieja JOIN cajas AS nueva ON nueva.id = vieja.id + 1 "
                    "WHERE vieja.cierre_forzoso = 1 AND nueva.responsable_id = vieja.responsable_id "
                    "AND nueva.cambio_contado IS NULL"
                ), 0)

    def test_pasa_de_todo_como_en_el_mostrador(self):
        for semilla, (_, resumen, uno) in self._bases():
            with self.subTest(semilla=semilla):
                self.assertGreater(resumen["forzosos"], 0)
                self.assertGreater(resumen["relevos"], 0)
                self.assertGreater(resumen["anuladas"], 0)
                self.assertGreater(resumen["sin_caja"], 0)  # ventas del Admin sin nadie en el mostrador
                self.assertGreater(uno(  # cerradas "en ausencia" de la responsable
                    "SELECT COUNT(*) FROM cierres_turno JOIN cajas ON cajas.cierre_id = cierres_turno.id "
                    "WHERE cajas.responsable_id <> cierres_turno.usuario_id AND cajas.cierre_forzoso = 0"
                ), 0)
                self.assertGreater(uno("SELECT COUNT(*) FROM cierres_turno WHERE monto_contado IS NOT NULL"), 0)
                self.assertGreater(uno("SELECT COUNT(*) FROM venta_detalle WHERE articulo_codigo = ?",
                                       dominio.CODIGO_ARTICULO_IMPRESIONES), 0)

    def test_los_lunes_el_cajon_vuelve_al_cambio_fijo(self):
        # Con el cambio siempre mal contado, el cajón baja durante la semana; el
        # lunes a la mañana el dueño lo deja otra vez en el Cambio Fijo.
        for semilla, (_, _, uno) in self._bases():
            with self.subTest(semilla=semilla):
                fondo = float(uno("SELECT valor FROM configuracion WHERE clave = 'fondo_cambio'"))
                self.assertLess(uno("SELECT MIN(cambio_esperado) FROM cajas WHERE fecha < '2026-10-19'"), fondo)
                self.assertEqual(uno(
                    "SELECT cambio_contado FROM cajas WHERE fecha = '2026-10-19' AND turno = ? ORDER BY id LIMIT 1",
                    dominio.TURNO_MANANA,
                ), fondo)

    def test_todas_las_fechas_son_las_de_los_dias_simulados(self):
        desde = (_HASTA - timedelta(days=_DIAS - 1)).isoformat()
        hasta = datetime(2026, 10, 21, 8).isoformat()
        for semilla, (_, _, uno) in self._bases():
            with self.subTest(semilla=semilla):
                for tabla, columna in _COLUMNAS_CON_FECHA:
                    with self.subTest(tabla=tabla):
                        self.assertGreaterEqual(uno(f"SELECT MIN({columna}) FROM {tabla}")[:10], desde)
                        self.assertLessEqual(uno(f"SELECT MAX({columna}) FROM {tabla}"), hasta)

    def test_queda_marcada_y_sin_el_armado_a_medias(self):
        for semilla, (carpeta, _, _) in self._bases():
            with self.subTest(semilla=semilla):
                self.assertTrue(database.es_base_de_prueba(carpeta))
                self.assertFalse(os.path.exists(os.path.join(carpeta, armar_base_de_prueba.ARMANDO)))

    def test_deja_el_programa_como_estaba(self):
        self.assertEqual((database.DATA_DIR, database.DB_PATH, database.get_connection), self.antes)
        self.assertEqual(_modulos_con_el_reloj_simulado(), [])
        self.assertIs(ventas_repo.datetime, datetime)


class TestDondeArma(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.carpeta = os.path.join(self._tmp.name, "prueba")
        self.antes = (database.DATA_DIR, database.DB_PATH, database.get_connection)

    def tearDown(self):
        database.DATA_DIR, database.DB_PATH = self.antes[:2]
        self._tmp.cleanup()

    def test_una_carpeta_que_no_es_de_prueba_no_se_toca(self):
        os.makedirs(self.carpeta)
        with open(os.path.join(self.carpeta, "kiosko.db"), "wb") as archivo:
            archivo.write(b"la base real")
        with self.assertRaises(ValueError):
            _armar(self.carpeta, dias=1)
        with open(os.path.join(self.carpeta, "kiosko.db"), "rb") as archivo:
            self.assertEqual(archivo.read(), b"la base real")
        self.assertEqual(os.listdir(self.carpeta), ["kiosko.db"])

    def test_nunca_en_la_carpeta_de_la_base_del_programa(self):
        # Ni siquiera vacía (una PC recién instalada): ahí iría la base real.
        database.DATA_DIR = os.path.join(self._tmp.name, "data_fr")
        os.makedirs(database.DATA_DIR)
        with self.assertRaises(ValueError):
            _armar(database.DATA_DIR, dias=1)
        self.assertEqual(os.listdir(database.DATA_DIR), [])

    def test_una_de_prueba_se_rearma(self):
        primera = _armar(self.carpeta, dias=1)
        # lo que dejó el programa abierto con --base era de la anterior: se va
        os.makedirs(os.path.join(self.carpeta, "backups"))
        with open(os.path.join(self.carpeta, "kiosko.db-journal"), "wb") as archivo:
            archivo.write(b"de la base anterior")
        segunda = _armar(self.carpeta, dias=1)
        self.assertEqual(primera["ventas"], segunda["ventas"])  # misma semilla, misma base
        self.assertEqual(sorted(os.listdir(self.carpeta)), [database.ARCHIVO_DE_BASE_DE_PRUEBA, "kiosko.db"])

    def test_una_carpeta_vacia_se_puede_usar(self):
        os.makedirs(self.carpeta)
        _armar(self.carpeta, dias=1)
        self.assertTrue(database.es_base_de_prueba(self.carpeta))

    def test_si_falla_a_mitad_de_camino_deja_todo_como_estaba(self):
        primera = _armar(self.carpeta, dias=1)
        original = ventas_repo.confirmar_venta
        llamadas = []

        def falla_a_la_quinta(*argumentos):
            llamadas.append(1)
            if len(llamadas) == 5:
                raise RuntimeError("se cortó la luz")
            return original(*argumentos)

        with mock.patch.object(ventas_repo, "confirmar_venta", side_effect=falla_a_la_quinta):
            with self.assertRaises(RuntimeError):
                _armar(self.carpeta, dias=2, semilla=9)
        self.assertEqual((database.DATA_DIR, database.DB_PATH, database.get_connection), self.antes)
        self.assertEqual(_modulos_con_el_reloj_simulado(), [])
        # la base anterior sigue entera
        conexion = sqlite3.connect(os.path.join(self.carpeta, "kiosko.db"))
        try:
            ventas = conexion.execute("SELECT COUNT(*) FROM ventas WHERE estado = ?",
                                      (dominio.VENTA_CONFIRMADA,)).fetchone()[0]
        finally:
            conexion.close()
        self.assertEqual(ventas, primera["ventas"])

    def test_el_candado_es_el_del_programa(self):
        self.assertEqual(armar_base_de_prueba.PUERTO_DEL_PROGRAMA_ABIERTO, main.PUERTO_INSTANCIA_UNICA)


class TestAbrirConOtraBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._antes = (database.DATA_DIR, database.DB_PATH)

    def tearDown(self):
        database.DATA_DIR, database.DB_PATH = self._antes
        self._tmp.cleanup()

    def test_la_opcion_base(self):
        self.assertEqual(main._carpeta_de_la_opcion_base(["main.py", "--base", "data_prueba"]), "data_prueba")
        self.assertEqual(main._carpeta_de_la_opcion_base(["main.py", "--base=data_prueba"]), "data_prueba")
        self.assertIsNone(main._carpeta_de_la_opcion_base(["main.py"]))

    def test_base_sin_carpeta_no_sigue_con_la_real(self):
        for argv in (["main.py", "--base"], ["main.py", "--base="], ["main.py", "--base", "--mostrador", "x"]):
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                main._carpeta_de_la_opcion_base(argv)

    def test_una_carpeta_sin_letra_va_al_lado_del_programa(self):
        database.usar_carpeta_de_datos("data_prueba")
        self.assertEqual(database.DATA_DIR, os.path.join(database.BASE_DIR, "data_prueba"))
        self.assertEqual(database.DB_PATH, os.path.join(database.BASE_DIR, "data_prueba", "kiosko.db"))
        database.usar_carpeta_de_datos(self._tmp.name)
        self.assertEqual(database.DATA_DIR, self._tmp.name)

    def test_sin_base_avisa_y_no_arma_una_vacia(self):
        with mock.patch("main.QMessageBox") as carteles:
            self.assertFalse(main._usar_otra_base(os.path.join(self._tmp.name, "data_prueva")))
        carteles.warning.assert_called_once()
        self.assertFalse(os.path.exists(os.path.join(self._tmp.name, "data_prueva")))

    def test_avisa_que_es_la_de_prueba_y_lo_dice_el_titulo(self):
        open(os.path.join(self._tmp.name, "kiosko.db"), "wb").close()
        open(os.path.join(self._tmp.name, database.ARCHIVO_DE_BASE_DE_PRUEBA), "w").close()
        with mock.patch("main.QMessageBox") as carteles:
            self.assertTrue(main._usar_otra_base(self._tmp.name))
        self.assertIn("BASE DE PRUEBA", carteles.information.call_args[0][1])
        ventana = mock.Mock()
        ventana.windowTitle.return_value = "FRKiosko - Ingreso"
        main._marcar_si_es_de_prueba(ventana)
        ventana.setWindowTitle.assert_called_once_with("FRKiosko - Ingreso - BASE DE PRUEBA")


if __name__ == "__main__":
    unittest.main()
