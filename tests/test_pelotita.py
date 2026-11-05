"""
tests/test_pelotita.py
======================
La pelotita que rebota por el inicio (ui/pelotita.py; pedido del dueño 2026-11-04,
que eligió la maqueta A: solo el inicio, celeste, velocidad media): que rebote como
en el Arkanoid sin salirse nunca, con el ángulo un poco distinto en cada choque y a
velocidad pareja; que no se coma los clics, no haga nada mientras no se ve y repinte
solo por donde pasa; y que el Administrador la prenda y la apague en Configuración
ADMIN (repositories/pelotita_repo.py), solo en el mostrador.

Se ejecutan con:

    python -m unittest discover tests
"""

import math
import os
import random
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication, QFrame, QPushButton  # noqa: E402

import dominio  # noqa: E402
from admin_remoto import modo as modo_remoto  # noqa: E402
from repositories import pelotita_repo, usuarios_repo  # noqa: E402
from ui.configuracion_admin_window import DETALLE_PELOTITA, ConfiguracionAdminWindow  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.pelotita import (  # noqa: E402
    INCLINACION_MAXIMA, INCLINACION_MINIMA, LARGO_COLA, PASO_MAXIMO_SEGUNDOS, RADIO, VELOCIDAD,
    PelotitaQueRebota, Rebote, largo_de,
)
from base import BaseConBaseTemporal  # noqa: E402

_app = QApplication.instance() or QApplication([])

# El lugar del inicio en la pantalla del mostrador (1920 x 1080, ventana maximizada).
ANCHO_INICIO, ALTO_INICIO = 1896, 881
# Lo que corre en un cuadro a la velocidad elegida (unos 30 cuadros por segundo).
PASO = VELOCIDAD * 0.033


def _recorrido_del_ultimo_paso(rebote, desde):
    """Lo que caminó la cabeza en el último avanzar(): de la cabeza nueva, pasando por
    el choque si lo hubo, hasta donde estaba antes (`desde`)."""
    hasta = rebote.cola.index(desde)
    return largo_de(rebote.cola[:hasta + 1])


def _apuntar(rebote, x, y, grados_x, grados_y):
    """Pone la pelotita en (x, y) yendo a 45° hacia el lado que digan los signos."""
    rebote.x, rebote.y = x, y
    rebote.vx = math.copysign(math.cos(math.radians(45)), grados_x)
    rebote.vy = math.copysign(math.sin(math.radians(45)), grados_y)
    rebote.cola = [(x, y)]


class TestElRebote(unittest.TestCase):
    def test_nunca_se_sale_del_inicio(self):
        for semilla in range(20):
            rebote = Rebote(ANCHO_INICIO, ALTO_INICIO, random.Random(semilla))
            for _ in range(900):  # unos 30 segundos de pelotita
                rebote.avanzar(PASO)
                self.assertTrue(RADIO <= rebote.x <= ANCHO_INICIO - RADIO, (semilla, rebote.x))
                self.assertTrue(RADIO <= rebote.y <= ALTO_INICIO - RADIO, (semilla, rebote.y))
            self.assertGreater(rebote.rebotes, 5, semilla)

    def test_va_siempre_a_la_misma_velocidad_aunque_choque(self):
        rebote = Rebote(400, 300, random.Random(1))
        for _ in range(500):
            antes = rebote.cola[0]
            rebote.avanzar(PASO)
            self.assertAlmostEqual(_recorrido_del_ultimo_paso(rebote, antes), PASO, places=6)
        self.assertGreater(rebote.rebotes, 20)

    def test_en_cada_choque_sale_con_otro_angulo_pero_nunca_acostada_ni_parada(self):
        rebote = Rebote(ANCHO_INICIO, ALTO_INICIO, random.Random(7))
        angulos = []
        for _ in range(3000):
            antes = rebote.rebotes
            rebote.avanzar(PASO)
            if rebote.rebotes > antes:
                angulos.append(rebote.inclinacion())
        self.assertGreater(len(angulos), 20)
        for angulo in angulos:
            self.assertGreaterEqual(angulo, INCLINACION_MINIMA - 1e-9)
            self.assertLessEqual(angulo, INCLINACION_MAXIMA + 1e-9)
        # Al azar: no repite siempre el mismo camino.
        self.assertGreater(len({round(angulo) for angulo in angulos}), 10)

    def test_despues_de_chocar_se_aleja_de_la_pared_y_la_estela_dobla_justo_ahi(self):
        rebote = Rebote(400, 300, random.Random(3))
        _apuntar(rebote, 400 - RADIO - 5, 150, +1, +1)  # va derecho a la pared de la derecha

        rebote.avanzar(20)

        self.assertEqual(rebote.rebotes, 1)
        self.assertLess(rebote.vx, 0)       # vuelve para la izquierda
        self.assertGreater(rebote.vy, 0)    # y sigue bajando
        self.assertIn(400 - RADIO, [round(x, 9) for x, _ in rebote.cola])

    def test_en_una_esquina_vuelve_por_donde_vino(self):
        rebote = Rebote(400, 300, random.Random(4))
        _apuntar(rebote, 400 - RADIO - 10, 300 - RADIO - 10, +1, +1)

        rebote.avanzar(20)

        self.assertLess(rebote.vx, 0)
        self.assertLess(rebote.vy, 0)

    def test_la_estela_no_pasa_de_su_largo(self):
        rebote = Rebote(ANCHO_INICIO, ALTO_INICIO, random.Random(5))
        for _ in range(200):
            rebote.avanzar(PASO)
        self.assertAlmostEqual(largo_de(rebote.cola), LARGO_COLA, places=6)

    def test_si_achican_la_ventana_vuelve_adentro(self):
        rebote = Rebote(ANCHO_INICIO, ALTO_INICIO, random.Random(6))
        rebote.x, rebote.y = 1800, 800

        rebote.cambiar_tamano(600, 400)
        for _ in range(300):
            rebote.avanzar(PASO)
            self.assertTrue(RADIO <= rebote.x <= 600 - RADIO and RADIO <= rebote.y <= 400 - RADIO)

    def test_sin_lugar_para_la_pelotita_no_se_mueve(self):
        rebote = Rebote(10, 10, random.Random(8))
        antes = (rebote.x, rebote.y)

        rebote.avanzar(100)

        self.assertEqual((rebote.x, rebote.y), antes)


class TestLaPelotitaEnPantalla(unittest.TestCase):
    def setUp(self):
        self.lugar = QFrame()
        self.lugar.setStyleSheet("background: black;")
        self.lugar.resize(800, 500)
        self.lugar.show()
        self.addCleanup(self.lugar.deleteLater)
        self.addCleanup(self.lugar.close)
        self.reloj = [100.0]
        self.pelotita = PelotitaQueRebota(self.lugar, random.Random(5), reloj=lambda: self.reloj[0])
        # Las pruebas la mueven a mano, cuadro por cuadro.
        self.pelotita.detener()

    def _cuadros(self, cuantos, segundos=0.033):
        for _ in range(cuantos):
            self.reloj[0] += segundos
            self.pelotita._avanzar()

    def test_no_se_come_los_clics(self):
        boton = QPushButton("VENTA DE MERCADERÍA", self.lugar)
        boton.setGeometry(20, 20, 192, 69)
        boton.show()
        self.pelotita.raise_()  # encima de todo, como en el inicio

        self.assertIs(self.lugar.childAt(QPoint(100, 50)), boton)

    def test_cubre_el_inicio_y_lo_sigue_si_cambia_de_tamano(self):
        self.assertEqual(self.pelotita.geometry(), self.lugar.rect())

        self.lugar.resize(1000, 600)

        self.assertEqual(self.pelotita.geometry(), self.lugar.rect())
        self.assertEqual((self.pelotita.rebote.ancho, self.pelotita.rebote.alto), (1000, 600))

    def test_avanza_con_el_reloj_y_no_salta_si_la_pantalla_estuvo_trabada(self):
        self._cuadros(1)  # el primer cuadro solo arranca el reloj
        antes = self.pelotita.rebote.cola[0]
        self._cuadros(1)
        self.assertAlmostEqual(_recorrido_del_ultimo_paso(self.pelotita.rebote, antes), PASO, places=6)

        antes = self.pelotita.rebote.cola[0]
        self._cuadros(1, segundos=5)  # un reporte largo trabó la pantalla 5 segundos
        self.assertAlmostEqual(_recorrido_del_ultimo_paso(self.pelotita.rebote, antes),
                               VELOCIDAD * PASO_MAXIMO_SEGUNDOS, places=6)

    def test_mientras_no_se_ve_no_hace_nada(self):
        self._cuadros(2)
        self.lugar.hide()
        antes = (self.pelotita.rebote.x, self.pelotita.rebote.y)

        self._cuadros(30)

        self.assertEqual((self.pelotita.rebote.x, self.pelotita.rebote.y), antes)

    def test_repinta_solo_el_pedacito_por_donde_pasa(self):
        self.lugar.resize(ANCHO_INICIO, ALTO_INICIO)
        self._cuadros(120)

        zona = self.pelotita.zona_a_pintar()
        area = sum(rect.width() * rect.height() for rect in zona)
        self.assertLess(area, 0.04 * ANCHO_INICIO * ALTO_INICIO)
        # Tiene adentro la cabeza y la punta de la estela.
        for x, y in (self.pelotita.rebote.cola[0], self.pelotita.rebote.cola[-1]):
            self.assertTrue(zona.contains(QPoint(round(x), round(y))))

    def test_se_dibuja_celeste_sobre_el_inicio(self):
        self._cuadros(60)
        imagen = self.lugar.grab().toImage()
        rebote = self.pelotita.rebote

        cabeza = imagen.pixelColor(round(rebote.x), round(rebote.y))
        self.assertGreater(min(cabeza.red(), cabeza.green(), cabeza.blue()), 180)  # casi blanca
        x, y = rebote.cola[len(rebote.cola) // 2]
        cola = imagen.pixelColor(round(x), round(y))
        self.assertGreater(cola.blue(), cola.red() + 40)  # la estela, azul

    def test_detener_la_deja_quieta(self):
        otra = PelotitaQueRebota(self.lugar)
        self.assertTrue(otra._timer.isActive())

        otra.detener()

        self.assertFalse(otra._timer.isActive())


class TestPrenderYApagar(BaseConBaseTemporal):
    def setUp(self):
        super().setUp()
        self.admin = usuarios_repo.listar_usuarios()[0]
        usuarios_repo.crear_usuario("LUCIA", "4321", dominio.ROL_EMPLEADA)
        self.lucia = next(u for u in usuarios_repo.listar_usuarios() if u["nombre"] == "LUCIA")

    def _ventana_principal(self):
        ventana = MainWindow(self.admin, lambda: None)
        self.addCleanup(ventana.deleteLater)
        self.addCleanup(ventana.close)
        return ventana

    def _tarjeta(self, ventana):
        return [b for b in ventana.findChildren(QPushButton) if b.accessibleName() == "Pelotita que rebota"]

    def test_viene_prendida(self):
        self.assertTrue(pelotita_repo.esta_prendida())

    def test_el_admin_la_apaga_y_la_prende_para_todos(self):
        pelotita_repo.prender(self.admin["id"], False)
        self.assertFalse(pelotita_repo.esta_prendida())
        pelotita_repo.prender(self.admin["id"], True)
        self.assertTrue(pelotita_repo.esta_prendida())

    def test_una_operadora_no_la_puede_apagar(self):
        with self.assertRaises(PermissionError):
            pelotita_repo.prender(self.lucia["id"], False)
        self.assertTrue(pelotita_repo.esta_prendida())

    def test_rebota_en_el_inicio_y_no_sobre_la_barra(self):
        ventana = self._ventana_principal()

        self.assertIs(ventana.pelotita.parent(), ventana.findChild(QFrame, "inicioKiosko"))
        self.assertIsNone(ventana.findChild(QFrame, "encabezadoInicio").findChild(PelotitaQueRebota))

    def test_apagada_no_esta_y_al_volver_de_config_admin_se_pone_o_se_saca(self):
        pelotita_repo.prender(self.admin["id"], False)
        ventana = self._ventana_principal()
        self.assertIsNone(ventana.pelotita)

        def config_admin_que_la(prendida):
            dialogo = mock.Mock()
            dialogo.return_value.exec.side_effect = lambda: pelotita_repo.prender(self.admin["id"], prendida)
            return dialogo

        with mock.patch("ui.main_window.ConfiguracionAdminWindow", config_admin_que_la(True)):
            ventana._abrir_configuracion_admin()
        pelotita = ventana.pelotita
        self.assertIsInstance(pelotita, PelotitaQueRebota)
        self.assertTrue(pelotita._timer.isActive())

        with mock.patch("ui.main_window.ConfiguracionAdminWindow", config_admin_que_la(False)):
            ventana._abrir_configuracion_admin()
        self.assertIsNone(ventana.pelotita)
        self.assertFalse(pelotita._timer.isActive())

    def test_al_cerrar_la_ventana_se_queda_quieta(self):
        # La ventana del Admin, ya cerrada, sigue viva (VueltaDelAdmin la tiene agarrada).
        ventana = self._ventana_principal()
        pelotita = ventana.pelotita

        ventana.close()

        self.assertFalse(pelotita._timer.isActive())

    def test_si_no_se_puede_leer_la_ventana_abre_igual_sin_pelotita(self):
        with mock.patch.object(pelotita_repo, "esta_prendida", side_effect=RuntimeError("base ocupada")), \
                mock.patch("ui.main_window.registrar_error") as registrar:
            ventana = self._ventana_principal()
        self.assertIsNone(ventana.pelotita)
        registrar.assert_called_once()

    def test_desde_otra_pc_no_hay_pelotita(self):
        no_preguntar = mock.patch.object(pelotita_repo, "esta_prendida", side_effect=AssertionError("no va a la base"))
        with mock.patch.object(modo_remoto, "es_copia_remota", return_value=True), \
                mock.patch.object(modo_remoto, "mostrador_en_uso", return_value="MOSTRADOR"), \
                mock.patch.object(MainWindow, "_mostrar_la_caja_del_mostrador"), no_preguntar:
            ventana = self._ventana_principal()
            self.assertIsNone(ventana.pelotita)
            configuracion = ConfiguracionAdminWindow(self.admin)
            self.addCleanup(configuracion.deleteLater)
            self.assertEqual(self._tarjeta(configuracion), [])

    def test_la_tarjeta_de_config_admin_la_prende_y_la_apaga(self):
        ventana = ConfiguracionAdminWindow(self.admin)
        self.addCleanup(ventana.deleteLater)
        [tarjeta] = self._tarjeta(ventana)
        self.assertEqual(tarjeta.detalle.text(), DETALLE_PELOTITA[True])

        tarjeta.click()
        self.assertFalse(pelotita_repo.esta_prendida())
        self.assertEqual(tarjeta.detalle.text(), DETALLE_PELOTITA[False])

        tarjeta.click()
        self.assertTrue(pelotita_repo.esta_prendida())
        self.assertEqual(tarjeta.detalle.text(), DETALLE_PELOTITA[True])

    def test_a_una_operadora_la_tarjeta_le_dice_acceso_restringido(self):
        ventana = ConfiguracionAdminWindow(self.lucia)
        self.addCleanup(ventana.deleteLater)
        [tarjeta] = self._tarjeta(ventana)

        with mock.patch("ui.piezas_ventana.avisar_acceso_restringido") as aviso:
            tarjeta.click()

        aviso.assert_called_once()
        self.assertTrue(pelotita_repo.esta_prendida())


if __name__ == "__main__":
    unittest.main()
