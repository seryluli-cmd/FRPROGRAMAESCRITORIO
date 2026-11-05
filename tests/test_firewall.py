"""
tests/test_firewall.py
======================
"Entrar desde otra PC" abre el firewall de Windows del mostrador al guardar
PRENDIDO (admin_remoto/firewall.py y ui/admin_remoto_dialogo.py).

La pantalla se prueba con revisar() y abrir() de mentira: ninguna prueba pide el
permiso de Administrador ni cambia el firewall de esta PC. En Windows, además, se
corre PowerShell de verdad para lo que solo LEE: la revisión, que los scripts no
tengan errores de sintaxis (se analizan, no se corren) y que un texto con
comillas llegue entero.

Se ejecutan con:

    python -m unittest discover tests
"""

import base64
import os
import subprocess
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

import dominio  # noqa: E402
import servidor_red  # noqa: E402
from admin_remoto import firewall  # noqa: E402
from repositories import admin_remoto_repo, usuarios_repo  # noqa: E402
from ui.admin_remoto_dialogo import DialogoEntrarDesdeOtraPC  # noqa: E402
from base import BaseConBaseTemporal  # noqa: E402
from test_en_segundo_plano import esperar_la_respuesta  # noqa: E402

_app = QApplication.instance() or QApplication([])

EN_WINDOWS = os.name == "nt"
# Con comillas simples, una comilla "tipográfica" (PowerShell también la toma
# como comilla) y dos espacios seguidos: tiene que llegar igual.
CARPETA_DIFICIL = "C:\\Mis  Cosas\\D'Angelo’s\\FRKiosko.exe"


class TestLoQueContestaPowerShell(unittest.TestCase):
    def test_lee_la_revision(self):
        self.assertEqual(firewall._leer_revision(b"1;0\r\n"), firewall.Revision(True, 0))
        self.assertTrue(firewall._leer_revision(b"2;0").abierto)
        self.assertFalse(firewall._leer_revision(b"0;0").abierto)  # falta nuestra regla
        self.assertFalse(firewall._leer_revision(b"1;2").abierto)  # Windows lo bloquea
        self.assertEqual(firewall._leer_revision(b"algo antes\r\n1;0\r\n\r\n"), firewall.Revision(True, 0))

    def test_si_no_contesta_lo_esperado_no_se_sabe(self):
        self.assertIsNone(firewall._leer_revision(b""))
        self.assertIsNone(firewall._leer_revision(b"Error: algo"))

    def test_el_programa_es_el_exe_solo_empaquetado(self):
        self.assertIsNone(firewall.programa_de_este_frkiosko())
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "executable", "C:\\FRKIOSKO\\FRKiosko.exe"):
            self.assertEqual(firewall.programa_de_este_frkiosko(), os.path.abspath("C:\\FRKIOSKO\\FRKiosko.exe"))

    def test_la_regla_es_solo_para_la_red_del_local(self):
        script = firewall._script_abrir("C:\\FRKIOSKO\\FRKiosko.exe")
        self.assertIn(f"localport={servidor_red.PUERTO_SERVIDOR}", script)
        self.assertIn("remoteip=localsubnet", script)
        self.assertIn("profile=any", script)
        self.assertIn("dir=in", script)


@unittest.skipUnless(EN_WINDOWS, "el firewall es de Windows")
class TestAbrir(unittest.TestCase):
    """Lo que devuelve abrir() según el cartel de Windows y lo que quedó después."""

    def _abrir(self, codigo, revision):
        with mock.patch.object(firewall, "_correr_como_administrador", return_value=codigo) as correr, \
                mock.patch.object(firewall, "revisar", return_value=revision):
            resultado = firewall.abrir("C:\\FRKIOSKO\\FRKiosko.exe", 1234)
        self.assertEqual(correr.call_args.args[2], 1234)  # el cartel sale sobre la ventana
        return resultado

    def test_dijeron_que_no(self):
        self.assertEqual(self._abrir(None, None), firewall.CANCELADO)

    def test_manda_lo_que_quedo_y_no_lo_que_contesto(self):
        self.assertEqual(self._abrir(0, firewall.Revision(True, 0)), firewall.ABIERTO)
        self.assertEqual(self._abrir(0, firewall.Revision(True, 1)), firewall.NO_SE_PUDO)
        self.assertEqual(self._abrir(4, firewall.Revision(True, 0)), firewall.ABIERTO)

    def test_sin_poder_revisar_vale_lo_que_contesto(self):
        self.assertEqual(self._abrir(0, None), firewall.ABIERTO)
        self.assertEqual(self._abrir(4, None), firewall.NO_SE_PUDO)
        self.assertEqual(self._abrir(-1, None), firewall.NO_SE_PUDO)


@unittest.skipUnless(EN_WINDOWS, "el firewall es de Windows")
class TestPowerShellDeVerdad(unittest.TestCase):
    """Solo lectura: nada de esto cambia el firewall."""

    def _correr(self, script: str) -> str:
        hecho = subprocess.run(
            [firewall._powershell(), *firewall._argumentos(script)],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=60,
        )
        return hecho.stdout.decode("ascii", errors="replace").strip()

    def test_revisa_sin_pedir_permiso(self):
        self.assertIsInstance(firewall.revisar(None), firewall.Revision)
        self.assertIsInstance(firewall.revisar(CARPETA_DIFICIL), firewall.Revision)

    def test_los_scripts_no_tienen_errores_de_sintaxis(self):
        for nombre, script in (
            ("revisar", firewall._script_revisar(CARPETA_DIFICIL)),
            ("abrir", firewall._script_abrir(CARPETA_DIFICIL)),
            ("abrir desde el código", firewall._script_abrir(None)),
        ):
            with self.subTest(nombre):
                analizar = (
                    "$e=$null;[void][Management.Automation.Language.Parser]::ParseInput("
                    + firewall._texto_en_powershell(script) + ",[ref]$null,[ref]$e);Write-Output $e.Count"
                )
                self.assertEqual(self._correr(analizar), "0")

    def test_la_carpeta_llega_entera(self):
        llega = self._correr(
            "[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("
            + firewall._texto_en_powershell(CARPETA_DIFICIL) + "))"
        )
        self.assertEqual(base64.b64decode(llega).decode("utf-8"), CARPETA_DIFICIL)

    def test_espera_al_programa_y_trae_su_codigo(self):
        # "open" en vez de "runas": el mismo camino, sin el cartel de Windows. La
        # línea es larga como la de abrir() (más de 2.048 letras).
        script = "$a='" + "x" * 1507 + "';exit ($a.Length % 250)"
        linea = subprocess.list2cmdline(firewall._argumentos(script))
        self.assertGreater(len(linea), 2048)
        self.assertEqual(firewall._correr_como_administrador(firewall._powershell(), linea, 0, verbo="open"), 7)


class TestLaPantalla(BaseConBaseTemporal):
    def setUp(self):
        super().setUp()
        admin_id = usuarios_repo.crear_usuario("Dueño", "1234", dominio.ROL_ADMIN)
        self.admin = dict(usuarios_repo.obtener_usuario(admin_id))
        self.revisiones = []
        self.aperturas = []
        self.contesta_revisar = [firewall.Revision(True, 0)]
        self.contesta_abrir = firewall.ABIERTO
        self.ventana = DialogoEntrarDesdeOtraPC(self.admin)
        parches = [
            mock.patch.object(firewall, "revisar", self._revisar),
            mock.patch.object(firewall, "abrir", self._abrir),
            mock.patch.object(servidor_red, "esta_escuchando", return_value=True),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)

    def tearDown(self):
        if self.ventana._espera._hilo is not None:
            self.ventana._espera._hilo.join(5)
        self.ventana.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        super().tearDown()

    def _revisar(self, programa):
        self.revisiones.append(programa)
        return self.contesta_revisar.pop(0)

    def _abrir(self, programa, ventana):
        self.aperturas.append((programa, ventana))
        return self.contesta_abrir

    def _guardar(self, prendido=True):
        """Guarda y devuelve los carteles que salieron: [(tipo, mensaje)]."""
        carteles = []
        with mock.patch("ui.admin_remoto_dialogo.mostrar_info",
                        side_effect=lambda _p, _t, texto: carteles.append(("info", texto))), \
                mock.patch("ui.admin_remoto_dialogo.mostrar_aviso",
                           side_effect=lambda _p, _t, texto: carteles.append(("aviso", texto))):
            self.ventana.check_activo.setChecked(prendido)
            self.ventana.boton_guardar.click()
            esperar_la_respuesta(self.ventana)
        return carteles

    def test_apagar_no_toca_el_firewall(self):
        carteles = self._guardar(prendido=False)
        self.assertEqual(self.revisiones, [])
        self.assertIn("APAGADA", carteles[0][1])
        self.assertEqual(self.ventana.result(), QDialog.Accepted)

    def test_con_el_firewall_bien_no_pide_permiso(self):
        carteles = self._guardar()
        self.assertTrue(admin_remoto_repo.esta_activo())
        self.assertEqual(len(self.revisiones), 1)
        self.assertEqual(self.aperturas, [])
        self.assertEqual(carteles, [("info", "La entrada desde otra PC quedó PRENDIDA.")])
        self.assertEqual(self.ventana.result(), QDialog.Accepted)

    def test_con_el_firewall_cerrado_avisa_y_lo_abre(self):
        self.contesta_revisar = [firewall.Revision(False, 1)]
        carteles = self._guardar()
        self.assertEqual(len(self.aperturas), 1)
        # El número de la ventana (para que el cartel de Windows salga adelante):
        # un número, nunca la ventana misma, que no puede viajar al hilo.
        self.assertIsInstance(self.aperturas[0][1], int)
        self.assertIn("decile Sí", carteles[0][1])  # el aviso ANTES del cartel de Windows
        self.assertIn("ya deja pasar", carteles[1][1])
        self.assertEqual(self.ventana.result(), QDialog.Accepted)

    def test_si_dicen_que_no_queda_abierta_para_probar_otra_vez(self):
        self.contesta_revisar = [firewall.Revision(False, 0), firewall.Revision(False, 0)]
        self.contesta_abrir = firewall.CANCELADO
        carteles = self._guardar()
        self.assertEqual(carteles[-1][0], "aviso")
        self.assertIn("Windows no dio el permiso", carteles[-1][1])
        self.assertTrue(admin_remoto_repo.esta_activo())  # lo prendido no se deshace
        self.assertNotEqual(self.ventana.result(), QDialog.Accepted)
        self.assertTrue(self.ventana.boton_guardar.isEnabled())
        self.contesta_abrir = firewall.ABIERTO
        carteles = self._guardar()
        self.assertEqual(len(self.aperturas), 2)
        self.assertEqual(self.ventana.result(), QDialog.Accepted)

    def test_si_no_se_puede_revisar_lo_dice_y_no_pide_permiso(self):
        self.contesta_revisar = [None]
        carteles = self._guardar()
        self.assertEqual(self.aperturas, [])
        self.assertIn("No pude revisar el firewall", carteles[0][1])

    def test_avisa_si_el_programa_no_pudo_abrir_su_puerto(self):
        with mock.patch.object(servidor_red, "esta_escuchando", return_value=False):
            carteles = self._guardar()
        self.assertIn("no pudo abrir su puerto de red", carteles[0][1])


if __name__ == "__main__":
    unittest.main()
