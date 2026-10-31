"""
tests/test_en_segundo_plano.py
================================
Los botones que esperan la red no congelan el mostrador (ui/en_segundo_plano.py):
"Probar la conexión" y "Reintentar ahora" (Cierres a la app de gastos), "Hacer
copia de seguridad ahora", la copia al pendrive y "Agregar" otra carpeta (Copias
de Seguridad) corren la función del repo en un hilo aparte. Mientras espera, la
pantalla sigue andando, las teclas que mandan algo se apagan (Cerrar no) y otro
clic no arranca otra vez; al terminar sale el mismo cartel que con la llamada
directa, letra por letra, y si la ventana se cerró antes no sale nada ni revienta
(un error inesperado va igual a errores.log). "Agregar carpeta" no se cierra
mientras prueba: la lista de carpetas no se pisa.

Las funciones del repo se reemplazan por unas de mentira que esperan un
threading.Event (o por las de verdad con una red caída de mentira): ninguna
prueba sale a internet ni a la red.

Se ejecutan con:

    python -m unittest discover tests
"""

import functools
import gc
import os
import tempfile
import threading
import time
import traceback
import unittest
import weakref
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QObject, Qt, QTimer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QPushButton  # noqa: E402

import database  # noqa: E402
import dominio  # noqa: E402
from repositories import copias_repo, envio_pwa_repo, usuarios_repo  # noqa: E402
from ui.copias_dialogo import DialogoAgregarCarpeta, DialogoCopiasDeSeguridad  # noqa: E402
from ui import en_segundo_plano  # noqa: E402
from ui.en_segundo_plano import EnSegundoPlano, _lleva_un_objeto_de_qt  # noqa: E402
from ui.envio_pwa_dialogo import DialogoEnvioPwa  # noqa: E402
from base import BaseConBaseTemporal  # noqa: E402

_app = QApplication.instance() or QApplication([])


def esperar_la_respuesta(ventana, segundos=5.0):
    """Deja andar la pantalla (sus QTimer incluidos) hasta que la espera de `ventana`
    terminó y mostró lo que volvió del hilo. La usan también test_envio_pwa y
    test_copias, adentro de sus mock.patch: el hilo lee el repo cuando corre."""
    limite = time.monotonic() + segundos
    while ventana._espera.esta_esperando():
        if time.monotonic() > limite:
            raise AssertionError("El hilo de la pantalla no terminó a tiempo.")
        QApplication.processEvents()
        time.sleep(0.01)


def dejar_andar(segundos):
    """La pantalla sigue andando un rato: corren sus eventos y sus QTimer."""
    hasta = time.monotonic() + segundos
    while time.monotonic() < hasta:
        QApplication.processEvents()
        time.sleep(0.01)


class _ErrorDePrueba(ValueError):
    """Un ValueError al que se le puede seguir el rastro (weakref)."""


def _red_caida(*_argumentos):
    """Hace del transporte a Google sin internet."""
    raise OSError("getaddrinfo failed")


class _RepoQueTarda:
    """Hace de una función del repo que espera la red: no contesta hasta que la
    prueba la suelta (o pasan 5 s) y devuelve `valor`, o levanta el error que arma
    `error`. Anota con qué la llamaron."""

    def __init__(self, valor=None, error=None):
        self.suelta = threading.Event()
        self.llamadas = []
        self.valor = valor
        self._armar_error = error
        self.ultimo_error = None  # weakref al último error que levantó

    def __call__(self, *argumentos):
        self.llamadas.append(argumentos)
        self.suelta.wait(5)
        if self._armar_error is not None:
            raise self._error_nuevo()  # sin guardarlo en una variable de este renglón
        return self.valor

    def _error_nuevo(self):
        error = self._armar_error()
        try:
            self.ultimo_error = weakref.ref(error)
        except TypeError:  # los errores de Python no lo permiten; _ErrorDePrueba sí
            self.ultimo_error = None
        return error


class _ConVentanas(BaseConBaseTemporal):
    def setUp(self):
        super().setUp()
        envio_pwa_repo._estado.update(ultimo_error=None, ultima_revision=None)
        copias_repo._estado.update(error_local=None, reintentar_desde=None, extra={})
        admin_id = usuarios_repo.crear_usuario("Dueño", "1234", dominio.ROL_ADMIN)
        self.admin = dict(usuarios_repo.obtener_usuario(admin_id))
        self._repos = []
        self._ventanas = []

    def tearDown(self):
        # Ningún hilo de una prueba sigue vivo en la siguiente: tocaría su base temporal.
        for repo in self._repos:
            repo.suelta.set()
        for ventana in self._ventanas:
            if ventana._espera._hilo is not None:
                ventana._espera._hilo.join(5)
            ventana.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        super().tearDown()

    def _que_tarda(self, **como):
        repo = _RepoQueTarda(**como)
        self._repos.append(repo)
        return repo

    def _ventana(self, clase, *argumentos):
        ventana = clase(*argumentos)
        self._ventanas.append(ventana)
        return ventana

    def _envio(self, padre=None):
        return self._ventana(DialogoEnvioPwa, self.admin, padre)

    def _tecla(self, ventana, texto):
        return next(boton for boton in ventana.findChildren(QPushButton) if boton.text() == texto)

    def _teclas_del_envio(self, ventana):
        return [ventana.tecla_probar.isEnabled(), ventana.tecla_reintentar.isEnabled(),
                ventana.tecla_interruptor.isEnabled()]


class TestCierresALaAppDeGastos(_ConVentanas):
    def test_mientras_espera_la_pantalla_sigue_andando(self):
        repo = self._que_tarda(valor={"nombres_app": ["Sergio"], "faltan": []})
        ventana = self._envio()
        tics = []
        reloj = QTimer()
        reloj.timeout.connect(lambda: tics.append(time.monotonic()))
        reloj.start(20)
        self.addCleanup(reloj.stop)

        with mock.patch.object(envio_pwa_repo, "probar_conexion", repo), \
                mock.patch("ui.envio_pwa_dialogo.mostrar_info") as aviso:
            antes = time.monotonic()
            ventana.tecla_probar.click()
            self.assertLess(time.monotonic() - antes, 1.0)  # el clic vuelve enseguida
            dejar_andar(0.3)
            self.assertGreater(len(tics), 3)  # la app no contestó y los relojes siguieron
            self.assertEqual(len(repo.llamadas), 1)
            aviso.assert_not_called()
            repo.suelta.set()
            esperar_la_respuesta(ventana)

        aviso.assert_called_once()

    def test_mientras_espera_las_teclas_se_apagan_menos_cerrar_y_despues_vuelven(self):
        envio_pwa_repo.activar(self.admin["id"], True)
        repo = self._que_tarda(valor={"enviados": 1, "con_error": 0})
        ventana = self._envio()
        self.assertEqual(self._teclas_del_envio(ventana), [True, True, True])

        with mock.patch.object(envio_pwa_repo, "reintentar_ahora", repo), \
                mock.patch("ui.envio_pwa_dialogo.mostrar_info"):
            ventana.tecla_reintentar.click()
            self.assertEqual(self._teclas_del_envio(ventana), [False, False, False])
            self.assertTrue(self._tecla(ventana, "CERRAR").isEnabled())
            # El cursor ocupado, solo en esta ventana: nada de reloj de arena en todo el programa.
            self.assertEqual(ventana.cursor().shape(), Qt.BusyCursor)
            self.assertIsNone(QApplication.overrideCursor())
            repo.suelta.set()
            esperar_la_respuesta(ventana)

        self.assertEqual(self._teclas_del_envio(ventana), [True, True, True])
        self.assertEqual(ventana.cursor().shape(), Qt.ArrowCursor)

    def test_dos_clics_no_arrancan_dos_veces(self):
        envio_pwa_repo.activar(self.admin["id"], True)
        probar = self._que_tarda(valor={"nombres_app": [], "faltan": []})
        reintentar = self._que_tarda(valor={"enviados": 0, "con_error": 0})
        ventana = self._envio()

        with mock.patch.object(envio_pwa_repo, "probar_conexion", probar), \
                mock.patch.object(envio_pwa_repo, "reintentar_ahora", reintentar), \
                mock.patch("ui.envio_pwa_dialogo.mostrar_info") as aviso:
            ventana.tecla_probar.click()
            ventana.tecla_probar.click()  # apagada: no hace nada
            ventana._probar_conexion()    # ni llamándola de otro lado
            ventana._reintentar()
            dejar_andar(0.2)
            probar.suelta.set()
            reintentar.suelta.set()
            esperar_la_respuesta(ventana)
            dejar_andar(0.2)

        self.assertEqual(len(probar.llamadas), 1)
        self.assertEqual(reintentar.llamadas, [])
        aviso.assert_called_once()

    def test_cerrar_la_ventana_mientras_espera_no_muestra_nada_ni_revienta(self):
        envio_pwa_repo.activar(self.admin["id"], True)
        formas_de_cerrar = {
            "CERRAR": lambda ventana: self._tecla(ventana, "CERRAR").click(),
            "la cruz": lambda ventana: ventana.close(),
            "Esc": lambda ventana: QTest.keyClick(ventana, Qt.Key_Escape),
        }
        for como, cerrar in formas_de_cerrar.items():
            with self.subTest(como):
                repo = self._que_tarda(valor={"enviados": 1, "con_error": 0})
                # Con padre, como la abre Configuración ADMIN: cerrada, sigue viva escondida.
                padre = QDialog()
                self.addCleanup(padre.deleteLater)
                ventana = self._envio(padre)
                ventana.show()
                with mock.patch.object(envio_pwa_repo, "reintentar_ahora", repo), \
                        mock.patch("ui.envio_pwa_dialogo.mostrar_info") as aviso, \
                        mock.patch("ui.utils.mostrar_error") as error:
                    ventana.tecla_reintentar.click()
                    cerrar(ventana)
                    self.assertFalse(ventana.isVisible())
                    repo.suelta.set()
                    ventana._espera._hilo.join(5)
                    dejar_andar(0.3)

                aviso.assert_not_called()
                error.assert_not_called()
                self.assertEqual(len(repo.llamadas), 1)  # lo que hace el repo, se hizo igual
                self.assertFalse(ventana._espera._timer.isActive())
                self.assertEqual(self._teclas_del_envio(ventana), [True, True, True])
                self.assertEqual(ventana.cursor().shape(), Qt.ArrowCursor)

    def test_sin_internet_sale_el_mismo_cartel_que_con_la_llamada_directa(self):
        with self.assertRaises(ValueError) as directo:  # el mensaje del repo llamado directo
            envio_pwa_repo.probar_conexion(transporte=_red_caida)
        ventana = self._envio()

        with mock.patch.object(envio_pwa_repo, "_transporte_http", _red_caida), \
                mock.patch("ui.utils.mostrar_error") as error:
            ventana.tecla_probar.click()
            esperar_la_respuesta(ventana)

        error.assert_called_once_with(ventana, "No se pudo completar", str(directo.exception))
        self.assertIn("Sin internet", str(directo.exception))
        self.assertEqual(self._teclas_del_envio(ventana), [True, True, True])

    def test_un_error_inesperado_va_al_log_con_el_renglon_del_repo_y_al_cartel_generico(self):
        repo = self._que_tarda(error=lambda: KeyError("config"))
        ventana = self._envio()

        with mock.patch.object(envio_pwa_repo, "probar_conexion", repo), \
                mock.patch("ui.utils.registrar_error") as log, \
                mock.patch("ui.utils._mostrar_error_seguro") as cartel:
            ventana.tecla_probar.click()
            repo.suelta.set()
            esperar_la_respuesta(ventana)

        error = log.call_args[0][0]
        self.assertIsInstance(error, KeyError)
        cartel.assert_called_once_with(ventana, error)
        # En errores.log se ve dónde falló adentro del hilo, como con la llamada directa.
        self.assertIn("in __call__", "".join(traceback.format_tb(error.__traceback__)))

    def test_el_error_no_queda_dando_vueltas_con_el_recolector_apagado(self):
        # Como en el mostrador (main.py): un ciclo entre el error y el hilo no se liberaría nunca.
        gc.disable()
        self.addCleanup(gc.enable)
        repo = self._que_tarda(error=lambda: _ErrorDePrueba("No contesta"))
        ventana = self._envio()

        with mock.patch.object(envio_pwa_repo, "probar_conexion", repo), \
                mock.patch("ui.utils.mostrar_error") as error:
            ventana.tecla_probar.click()
            repo.suelta.set()
            esperar_la_respuesta(ventana)
            ventana._espera._hilo.join(5)

        error.assert_called_once_with(ventana, "No se pudo completar", "No contesta")
        self.assertIsNone(repo.ultimo_error())

        # Y si la ventana ya se cerró, el error lo saca del dict _anotar_si_fallo (sin
        # cartel): tampoco queda nada dando vueltas.
        repo = self._que_tarda(error=lambda: _ErrorDePrueba("No contesta"))
        ventana = self._envio()
        ventana.show()
        with mock.patch.object(envio_pwa_repo, "probar_conexion", repo), \
                mock.patch("ui.utils.mostrar_error") as error:
            ventana.tecla_probar.click()
            ventana.close()
            repo.suelta.set()
            ventana._espera._hilo.join(5)
            dejar_andar(0.2)

        error.assert_not_called()
        self.assertIsNone(repo.ultimo_error())

    def test_los_textos_de_resultado_letra_por_letra(self):
        envio_pwa_repo.activar(self.admin["id"], True)
        casos = [
            ("probar_conexion", "tecla_probar", {"nombres_app": ["Sergio", "TOBY"], "faltan": ["Gabriela", "MATI"]},
             "Conexión OK, pero faltan nombres",
             "Se pudo entrar a la app de gastos. Allá están: Sergio, TOBY.\n\n"
             "Estos usuarios de acá NO están escritos igual allá: Gabriela, MATI.\n"
             "Sus cierres se verían sin color y fuera de las estadísticas: escribilos igual en las dos apps."),
            ("probar_conexion", "tecla_probar", {"nombres_app": [], "faltan": []},
             "Conexión OK",
             "Se pudo entrar a la app de gastos. Allá están: (ninguno).\n"
             "Todos los usuarios de acá están escritos igual."),
            ("reintentar_ahora", "tecla_reintentar", {"enviados": 2, "con_error": 1},
             "Reintentar ahora", "Enviados: 2 · Con error: 1."),
        ]
        for funcion, tecla, valor, titulo, mensaje in casos:
            with self.subTest(titulo):
                repo = self._que_tarda(valor=valor)
                ventana = self._envio()
                with mock.patch.object(envio_pwa_repo, funcion, repo), \
                        mock.patch("ui.envio_pwa_dialogo.mostrar_info") as aviso:
                    getattr(ventana, tecla).click()
                    repo.suelta.set()
                    esperar_la_respuesta(ventana)
                aviso.assert_called_once_with(ventana, titulo, mensaje)

    def test_con_el_envio_apagado_reintentar_avisa_sin_arrancar_nada(self):
        repo = self._que_tarda(valor={"enviados": 0, "con_error": 0})
        ventana = self._envio()

        with mock.patch.object(envio_pwa_repo, "reintentar_ahora", repo), \
                mock.patch("ui.envio_pwa_dialogo.mostrar_info") as aviso:
            ventana.tecla_reintentar.click()

        aviso.assert_called_once_with(
            ventana, "Reintentar ahora", "El envío está apagado: prendelo para mandar lo pendiente."
        )
        self.assertFalse(ventana._espera.esta_esperando())
        self.assertEqual(repo.llamadas, [])


class TestCopiasDeSeguridad(_ConVentanas):
    def _copias(self):
        return self._ventana(DialogoCopiasDeSeguridad, self.admin)

    def _teclas_de_copias(self, dialogo):
        return [dialogo.boton_ahora.isEnabled(), dialogo.boton_pendrive.isEnabled(),
                dialogo.boton_agregar.isEnabled(), dialogo.boton_quitar.isEnabled()]

    def _carpeta_de_disco(self):
        """Una carpeta de otro disco de verdad: temporal y fuera de data_fr."""
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        return copias_repo.agregar_carpeta_extra(self.admin["id"], carpeta.name)

    def test_copia_ahora_no_traba_y_dice_donde_quedo(self):
        donde = {"sin carpetas": "en esta PC", "con una carpeta": "en esta PC y en las 1 carpeta(s) de la lista"}
        for caso, texto in donde.items():
            with self.subTest(caso):
                extra = []
                if caso == "con una carpeta":  # Quitar arranca prendida y se tiene que apagar
                    disco = self._carpeta_de_disco()
                    extra = [{"carpeta": disco, "destino": os.path.join(disco, "copia.db"), "error": None}]
                quitar = bool(extra)  # sin carpetas, Quitar está apagada antes y después
                repo = self._que_tarda(valor={"local": "copia.db", "extra": extra})
                dialogo = self._copias()
                self.assertEqual(self._teclas_de_copias(dialogo), [True, True, True, quitar])

                with mock.patch.object(copias_repo, "hacer_copia_ahora", repo), \
                        mock.patch("ui.copias_dialogo.mostrar_info") as aviso:
                    dialogo.boton_ahora.click()
                    self.assertEqual(self._teclas_de_copias(dialogo), [False, False, False, False])
                    self.assertTrue(self._tecla(dialogo, "CERRAR").isEnabled())
                    self.assertEqual(dialogo.boton_abrir_extra.isEnabled(), quitar)  # mirar no cambia la lista
                    dejar_andar(0.2)
                    aviso.assert_not_called()
                    repo.suelta.set()
                    esperar_la_respuesta(dialogo)

                aviso.assert_called_once_with(dialogo, "Copia hecha", f"Listo: la copia quedó guardada {texto}.")
                self.assertEqual(self._teclas_de_copias(dialogo), [True, True, True, quitar])

    def test_cerrada_la_ventana_un_error_inesperado_igual_queda_en_el_log(self):
        casos = {
            "un disco lleno": (lambda: OSError(28, "No space left on device"), True),
            "un rechazo del repo": (lambda: ValueError("Esa carpeta ya está en la lista."), False),
            "sin permiso": (lambda: PermissionError("No tenés permiso."), False),
        }
        log = Path(database.DATA_DIR) / "errores.log"
        for caso, (error, se_anota) in casos.items():
            with self.subTest(caso):
                log.unlink(missing_ok=True)
                repo = self._que_tarda(error=error)
                dialogo = self._copias()
                dialogo.show()
                with mock.patch.object(copias_repo, "hacer_copia_ahora", repo), \
                        mock.patch("ui.utils.mostrar_error") as cartel:
                    dialogo.boton_ahora.click()
                    self._tecla(dialogo, "CERRAR").click()
                    repo.suelta.set()
                    dialogo._espera._hilo.join(5)
                    dejar_andar(0.3)

                cartel.assert_not_called()
                self.assertFalse(dialogo._espera._timer.isActive())
                anotado = log.read_text(encoding="utf-8") if log.exists() else ""
                if se_anota:
                    self.assertIn("se cerró antes de que terminara", anotado)
                    self.assertIn("No space left on device", anotado)
                    self.assertIn("in __call__", anotado)  # el renglón del repo donde falló
                else:  # era para el cartel: no es una falla del programa
                    self.assertEqual(anotado, "")

    def test_con_una_carpeta_que_no_anduvo_avisa_en_cual(self):
        repo = self._que_tarda(valor={"local": "copia.db", "extra": [
            {"carpeta": "D:\\BACKUPS", "destino": "D:\\BACKUPS\\copia.db", "error": None},
            {"carpeta": "\\\\192.168.1.112\\Backups", "destino": None, "error": "La otra PC no contesta."},
        ]})
        dialogo = self._copias()

        with mock.patch.object(copias_repo, "hacer_copia_ahora", repo), \
                mock.patch("ui.copias_dialogo.mostrar_error") as aviso:
            dialogo.boton_ahora.click()
            repo.suelta.set()
            esperar_la_respuesta(dialogo)

        aviso.assert_called_once_with(
            dialogo, "Copia hecha, pero no en todas las carpetas",
            "La copia quedó en esta PC y en 1 carpeta(s) más, pero no en:\n\nLa otra PC no contesta.",
        )

    def test_si_la_copia_falla_la_lista_se_actualiza_antes_del_cartel(self):
        repo = self._que_tarda(error=lambda: OSError(28, "No space left on device"))
        dialogo = self._copias()
        orden = mock.Mock()

        with mock.patch.object(copias_repo, "hacer_copia_ahora", repo), \
                mock.patch.object(dialogo, "_actualizar", orden.actualizar), \
                mock.patch("ui.utils.registrar_error"), \
                mock.patch("ui.utils._mostrar_error_seguro", orden.cartel):
            dialogo.boton_ahora.click()
            repo.suelta.set()
            esperar_la_respuesta(dialogo)

        # Primero la lista al día (lo que pasó con cada carpeta), después el cartel.
        self.assertEqual([llamada[0] for llamada in orden.mock_calls], ["actualizar", "cartel"])
        self.assertIsInstance(orden.cartel.call_args[0][1], OSError)

    def test_la_copia_al_pendrive_no_traba_y_dice_donde_quedo(self):
        ruta = "E:\\frkiosko_backup_20261028_150000.db"
        repo = self._que_tarda(valor=ruta)
        dialogo = self._copias()

        with mock.patch("ui.copias_dialogo.QFileDialog.getExistingDirectory", return_value="E:/"), \
                mock.patch.object(copias_repo, "guardar_copia_en", repo), \
                mock.patch("ui.copias_dialogo.mostrar_info") as aviso:
            dialogo.boton_pendrive.click()
            self.assertEqual(self._teclas_de_copias(dialogo), [False, False, False, False])
            repo.suelta.set()
            esperar_la_respuesta(dialogo)

        self.assertEqual(repo.llamadas, [("E:/",)])
        aviso.assert_called_once_with(dialogo, "Copia guardada", f"Se guardó la copia de seguridad en:\n{ruta}")

    def test_agregar_una_carpeta_no_traba_y_un_enter_no_la_prueba_dos_veces(self):
        carpeta = "\\\\192.168.1.112\\Backups"
        repo = self._que_tarda(valor=carpeta)
        agregar = self._ventana(DialogoAgregarCarpeta, self.admin)
        agregar.campo_carpeta.setText(carpeta)
        agregar.campo_usuario.setText("kiosko")
        agregar.campo_clave.setText("clave-de-prueba-que-no-se-guarda")

        with mock.patch.object(copias_repo, "agregar_carpeta_extra", repo):
            agregar.boton_agregar.click()
            self.assertFalse(agregar.boton_agregar.isEnabled())
            self.assertFalse(agregar.boton_cancelar.isEnabled())  # ver más abajo por qué
            QTest.keyClick(agregar.campo_clave, Qt.Key_Return)  # el Enter del último campo también agrega
            dejar_andar(0.2)
            repo.suelta.set()
            esperar_la_respuesta(agregar)

        self.assertEqual(repo.llamadas, [(self.admin["id"], carpeta, "kiosko", "clave-de-prueba-que-no-se-guarda")])
        self.assertEqual(agregar.result(), QDialog.Accepted)

    def test_una_carpeta_mal_escrita_da_el_mismo_aviso_y_despues_cancelar_cierra(self):
        with self.assertRaises(ValueError) as directo:  # el mensaje del repo llamado directo
            copias_repo.agregar_carpeta_extra(self.admin["id"], "BACKUPS")
        agregar = self._ventana(DialogoAgregarCarpeta, self.admin)
        agregar.campo_carpeta.setText("BACKUPS")
        agregar.show()

        with mock.patch("ui.utils.mostrar_error") as error:
            agregar.boton_agregar.click()
            QTest.keyClick(agregar, Qt.Key_Escape)  # mientras espera la respuesta, Esc no cierra
            self.assertTrue(agregar.isVisible())
            esperar_la_respuesta(agregar)

        error.assert_called_once_with(agregar, "No se pudo completar", str(directo.exception))
        self.assertTrue(agregar.isVisible())  # sigue abierta para corregirla
        self.assertEqual([agregar.boton_agregar.isEnabled(), agregar.boton_cancelar.isEnabled()], [True, True])
        agregar.boton_cancelar.click()
        self.assertEqual(agregar.result(), QDialog.Rejected)

    def test_mientras_prueba_la_carpeta_no_se_cierra_y_la_lista_no_se_pisa(self):
        # agregar_carpeta_extra lee la lista antes de probar y la graba después. Si la
        # ventana se cerrara en el medio, en Copias de Seguridad se podría agregar o
        # quitar otra carpeta, y al terminar la prueba la pisaría. Abierta, Copias
        # queda detrás: su exec() no vuelve hasta que termina la prueba.
        disco = self._carpeta_de_disco()
        red = "\\\\192.168.1.112\\Backups"
        prueba = self._que_tarda()  # la otra PC tarda en contestar, y al final contesta
        copias = self._copias()
        copias.show()

        def ventanas_de_agregar():
            return [hija for hija in copias.findChildren(QDialog) if isinstance(hija, DialogoAgregarCarpeta)]

        # Si la ventana de agregar no se cerrara nunca, la prueba no queda colgada.
        seguro = QTimer(copias)
        seguro.setSingleShot(True)
        seguro.timeout.connect(lambda: [agregar.done(QDialog.Rejected) for agregar in ventanas_de_agregar()])
        seguro.start(8000)
        vista = {}

        def con_la_ventana_de_agregar_abierta():
            agregar = ventanas_de_agregar()[-1]
            agregar.campo_carpeta.setText(red)
            agregar.boton_agregar.click()
            vista["Cancelar prendido"] = agregar.boton_cancelar.isEnabled()
            vista["Buscar o un campo prendido"] = any(cosa.isEnabled() for cosa in (
                agregar.boton_buscar, agregar.campo_carpeta, agregar.campo_usuario, agregar.campo_clave))
            formas_de_cerrar = {
                "Cancelar": agregar.boton_cancelar.click,
                "Esc": lambda: QTest.keyClick(agregar, Qt.Key_Escape),
                "la cruz": agregar.close,
            }
            for como, cerrar in formas_de_cerrar.items():
                cerrar()
                abierta = agregar.isVisible() and agregar._espera.esta_esperando()
                vista[como] = "sigue abierta" if abierta else "se cerró"
            # Y es la modal: Copias de Seguridad, detrás, no recibe clics ni teclas.
            vista["Copias tapada"] = QApplication.activeModalWidget() is agregar
            prueba.suelta.set()

        QTimer.singleShot(0, con_la_ventana_de_agregar_abierta)
        with mock.patch.object(copias_repo, "_probar_que_se_puede_guardar", prueba), \
                mock.patch.object(copias_repo, "hacer_copia_ahora", return_value={"local": "copia.db", "extra": []}), \
                mock.patch("ui.copias_dialogo.mostrar_info"), \
                mock.patch("ui.utils.mostrar_error") as error:
            copias.boton_agregar.click()  # exec(): vuelve recién cuando se cierra la de agregar
            esperar_la_respuesta(copias)  # y después la copia que prueba la carpeta nueva
        seguro.stop()

        self.assertEqual(vista, {"Cancelar prendido": False, "Buscar o un campo prendido": False,
                                 "Cancelar": "sigue abierta",
                                 "Esc": "sigue abierta", "la cruz": "sigue abierta", "Copias tapada": True})
        error.assert_not_called()
        self.assertEqual(prueba.llamadas, [(red,)])
        self.assertEqual(copias_repo.carpetas_extra(), [disco, red])
        self.assertEqual(copias.tabla.rowCount(), 2)


class TestLaPieza(_ConVentanas):
    def test_al_hilo_no_se_le_pasa_nada_de_qt(self):
        dialogo = QDialog()
        self.addCleanup(dialogo.deleteLater)
        tecla = QPushButton("MANDAR", dialogo)
        espera = EnSegundoPlano(dialogo, [tecla])
        prohibidos = {
            "un widget": (len, (tecla,)),
            "el método de una ventana": (dialogo.result, ()),
            "un lambda que nombra la ventana": (lambda: dialogo.result(), ()),
            "un partial de un método de la ventana": (functools.partial(dialogo.done), (1,)),
            "un widget dentro de una lista": (len, ([tecla],)),
            "un widget dentro de un dict": (len, ({"tecla": tecla},)),
        }
        for que, (trabajo, argumentos) in prohibidos.items():
            with self.subTest(que):
                with self.assertRaises(TypeError):
                    espera.arrancar(trabajo, *argumentos, al_terminar=lambda respuesta: None)
                self.assertFalse(espera.esta_esperando())
                self.assertTrue(tecla.isEnabled())
        # Lo que sí va al hilo: la función del repo y datos, también en listas, dicts o un partial.
        datos = (copias_repo.agregar_carpeta_extra, 1, "D:\\BACKUPS", ["a", 2], {"x": (1, 2)},
                 functools.partial(len, "abc"))
        self.assertFalse(any(_lleva_un_objeto_de_qt(cosa) for cosa in datos))

    def test_el_hilo_no_deja_un_ciclo_entre_el_error_y_donde_lo_anota(self):
        # El error guarda en su traceback el renglón de _correr. Si ese renglón siguiera
        # guardando el dict, el dict y el error se sostendrían entre sí y, con el
        # recolector apagado (main.py), no se liberarían nunca.
        gc.disable()
        self.addCleanup(gc.enable)

        class Anotador(dict):
            pass  # a un dict común no se le puede tomar una referencia débil

        def falla():
            raise _ErrorDePrueba("No contesta")

        resultado = Anotador()
        en_segundo_plano._correr(falla, (), resultado)
        self.assertIsInstance(resultado["error"], _ErrorDePrueba)
        vigilado = weakref.ref(resultado)
        del resultado
        self.assertIsNone(vigilado())

    def test_el_hilo_es_daemon_y_lleva_solo_la_funcion_y_datos(self):
        repo = self._que_tarda(valor="D:\\BACKUPS")
        agregar = self._ventana(DialogoAgregarCarpeta, self.admin)
        agregar.campo_carpeta.setText("D:\\BACKUPS")
        hilos = []

        def anotar_el_hilo(**datos):
            hilos.append(datos)
            return threading.Thread(**datos)

        with mock.patch("ui.en_segundo_plano.threading", mock.Mock(Thread=anotar_el_hilo)), \
                mock.patch.object(copias_repo, "agregar_carpeta_extra", repo):
            agregar.boton_agregar.click()
            repo.suelta.set()
            esperar_la_respuesta(agregar)

        self.assertEqual(len(hilos), 1)
        # Daemon: cerrar FRKiosko con un pedido colgado no espera a que conteste.
        self.assertIs(hilos[0]["daemon"], True)
        trabajo, argumentos, resultado = hilos[0]["args"]
        self.assertIs(trabajo, repo)
        self.assertEqual(argumentos, (self.admin["id"], "D:\\BACKUPS", "", ""))
        self.assertIs(type(resultado), dict)
        for cosa in (trabajo, *argumentos, resultado):
            self.assertNotIsInstance(cosa, QObject)
            self.assertNotIsInstance(getattr(cosa, "__self__", None), QObject)


if __name__ == "__main__":
    unittest.main()
