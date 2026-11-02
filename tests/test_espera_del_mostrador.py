"""
tests/test_espera_del_mostrador.py
====================================
La copia abierta desde otra PC no se traba mientras el mostrador contesta
(ui/espera_del_mostrador.py): cada pedido va en un hilo aparte; lo que contesta
rápido no muestra nada, lo que tarda muestra el cartel "Esperando al mostrador"
con la pantalla andando, y DEJAR DE ESPERAR avisa como un corte de la red (el
mostrador pudo haberlo hecho). La revisión de la caja de la ventana principal
pregunta en su propio hilo, sin cartel y sin trabar nada.

Las esperas son funciones de mentira que esperan un threading.Event; las pruebas
con la conexión de verdad (admin_remoto/cliente.py) usan un mostrador de mentira
en 127.0.0.1 que no contesta.

Se ejecutan con:

    python -m unittest discover tests
"""

import json
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main  # noqa: E402
from admin_remoto import cliente  # noqa: E402
from ui import espera_del_mostrador  # noqa: E402
from ui.espera_del_mostrador import CartelEsperandoAlMostrador, SeDejoDeEsperar, esperar  # noqa: E402

_app = QApplication.instance() or QApplication([])


def _cartel_abierto():
    cartel = QApplication.activeModalWidget()
    return cartel if isinstance(cartel, CartelEsperandoAlMostrador) else None


def _cuando_salga_el_cartel(hacer, segundos=5.0):
    """Llama a `hacer(cartel)` apenas aparece el cartel (lo mira un reloj de la
    pantalla: si la espera trabara la pantalla, no correría nunca)."""
    limite = time.monotonic() + segundos
    reloj = QTimer()
    reloj.setInterval(20)

    def mirar():
        cartel = _cartel_abierto()
        if cartel is not None:
            reloj.stop()
            hacer(cartel)
        elif time.monotonic() > limite:
            reloj.stop()
    reloj.timeout.connect(mirar)
    reloj.start()
    return reloj


class _ConEsperaCorta(unittest.TestCase):
    def setUp(self):
        parche = mock.patch.object(espera_del_mostrador, "SEGUNDOS_SIN_CARTEL", 0.05)
        parche.start()
        self.addCleanup(parche.stop)
        self.suelta = threading.Event()
        self.addCleanup(self.suelta.set)  # ningún hilo de mentira queda colgado

    def _tarda(self, valor="listo"):
        """Una espera de mentira que contesta recién cuando la prueba suelta."""
        suelta = self.suelta

        def trabajo():
            suelta.wait(10)
            return valor
        return trabajo


class TestLoDeCasiSiempre(_ConEsperaCorta):
    def test_lo_que_contesta_rapido_no_muestra_ningun_cartel(self):
        with mock.patch.object(espera_del_mostrador, "CartelEsperandoAlMostrador",
                               side_effect=AssertionError("no tenía que salir")):
            self.assertEqual(esperar(lambda a, b: a + b, 2, 3), 5)

    def test_el_error_del_pedido_vuelve_igual(self):
        def falla():
            raise ValueError("el mostrador dijo que no")
        with self.assertRaises(ValueError) as error:
            esperar(falla)
        self.assertEqual(str(error.exception), "el mostrador dijo que no")


class TestCuandoElMostradorTarda(_ConEsperaCorta):
    def test_sale_el_cartel_la_pantalla_sigue_andando_y_se_cierra_solo(self):
        vistos, latidos = [], []
        latido = QTimer()
        latido.timeout.connect(lambda: latidos.append(1))
        latido.start(20)
        self.addCleanup(latido.stop)

        def al_salir(cartel):
            vistos.append(cartel.windowTitle())
            QTimer.singleShot(150, self.suelta.set)
        reloj = _cuando_salga_el_cartel(al_salir)

        self.assertEqual(esperar(self._tarda("la respuesta")), "la respuesta")
        reloj.stop()
        self.assertEqual(vistos, ["FRKiosko - Esperando al mostrador"])
        self.assertGreater(len(latidos), 3)
        self.assertIsNone(_cartel_abierto())

    def test_dejar_de_esperar_es_un_corte_de_la_red(self):
        reloj = _cuando_salga_el_cartel(lambda cartel: cartel.boton_dejar.click())
        with self.assertRaises(SeDejoDeEsperar) as error:
            esperar(self._tarda())
        reloj.stop()
        # Un TimeoutError: cliente._pedir lo trata como una espera vencida.
        self.assertIsInstance(error.exception, TimeoutError)

    def test_esc_tambien_deja_de_esperar(self):
        reloj = _cuando_salga_el_cartel(lambda cartel: cartel.reject())
        with self.assertRaises(SeDejoDeEsperar):
            esperar(self._tarda())
        reloj.stop()

    def test_desde_otro_hilo_se_espera_ahi_mismo_sin_cartel(self):
        respuestas = []
        threading.Timer(0.2, self.suelta.set).start()
        with mock.patch.object(espera_del_mostrador, "CartelEsperandoAlMostrador",
                               side_effect=AssertionError("no tenía que salir")):
            hilo = threading.Thread(target=lambda: respuestas.append(esperar(self._tarda("de otro hilo"))))
            hilo.start()
            hilo.join(5)
        self.assertEqual(respuestas, ["de otro hilo"])

    def test_con_el_cartel_abierto_otro_pedido_no_abre_otro_cartel(self):
        de_adentro = []

        def al_salir(cartel):
            # Como un reloj de una pantalla que pide algo mientras se espera.
            de_adentro.append(esperar(lambda: "sin otro cartel"))
            de_adentro.append(len([c for c in _app.topLevelWidgets()
                                   if isinstance(c, CartelEsperandoAlMostrador) and c.isVisible()]))
            self.suelta.set()
        reloj = _cuando_salga_el_cartel(al_salir)
        esperar(self._tarda())
        reloj.stop()
        self.assertEqual(de_adentro, ["sin otro cartel", 1])


class _MostradorQueNoContesta(BaseHTTPRequestHandler):
    """Lee el pedido entero y se queda callado hasta que la prueba lo suelta."""

    def log_message(self, formato, *args):
        pass

    def do_POST(self):
        json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.suelta.wait(10)


class TestConLaConexionDeVerdad(unittest.TestCase):
    def setUp(self):
        parche = mock.patch.object(espera_del_mostrador, "SEGUNDOS_SIN_CARTEL", 0.05)
        parche.start()
        self.addCleanup(parche.stop)
        self.mostrador = ThreadingHTTPServer(("127.0.0.1", 0), _MostradorQueNoContesta)
        self.mostrador.suelta = threading.Event()
        threading.Thread(target=self.mostrador.serve_forever, daemon=True).start()
        self.addCleanup(self.mostrador.server_close)
        self.addCleanup(self.mostrador.shutdown)
        self.addCleanup(self.mostrador.suelta.set)
        self.conexion = cliente.ConexionConElMostrador(
            "127.0.0.1", self.mostrador.server_address[1], esperar=esperar,
        )
        self.conexion._token = "sesion de prueba"  # como si ya hubiera entrado

    def test_dejar_de_esperar_una_compra_avisa_que_pudo_guardarse(self):
        reloj = _cuando_salga_el_cartel(lambda cartel: cartel.boton_dejar.click())
        with self.assertRaises(cliente.SinRespuesta) as error:
            self.conexion.llamar("compras_repo", "registrar_compra", (1, []), {})
        reloj.stop()
        self.assertIn("fijate antes de repetirlo", str(error.exception))

    def test_dejar_de_esperar_al_entrar_no_habla_de_algo_guardado(self):
        reloj = _cuando_salga_el_cartel(lambda cartel: cartel.boton_dejar.click())
        with self.assertRaises(cliente.SinConexion) as error:
            self.conexion.hola()
        reloj.stop()
        self.assertNotIsInstance(error.exception, cliente.SinRespuesta)
        self.assertIn("no contestó a tiempo", str(error.exception))


class TestElProgramaLaUsa(unittest.TestCase):
    def test_la_copia_remota_conecta_con_la_espera_sin_trabar(self):
        with mock.patch.object(main.cliente_remoto, "conectar") as conectar, \
                mock.patch.object(main.cliente_remoto, "instalar"):
            main._conectar_con_el_mostrador("192.168.1.50")
        conectar.assert_called_once_with("192.168.1.50", esperar=espera_del_mostrador.esperar)


if __name__ == "__main__":
    unittest.main()
