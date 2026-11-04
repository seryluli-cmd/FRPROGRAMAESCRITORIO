"""
tests/test_barra_para_todos.py
================================
La barra de arriba de la ventana principal muestra los mismos botones a todos
(pedido del dueño, 2026-10-19: con solo los suyos, la barra de una empleada quedaba
muy vacía). Los que no le tocan a alguien se ven igual que los demás y al apretarlos
dicen "Acceso Restringido" (pedido del dueño, 2026-11-04; antes no hacían nada, y las
tarjetas iban en gris con candado). Configuración ADMIN es solo del Administrador (acá
adentro no quedó nada que use un Operador): una empleada ve el botón igual, pero no abre. Las
tarjetas de Configuración ADMIN y Administrar Kiosko (diseño del 2026-10-26) llevan el
título en `accessibleName()`: su texto lo dibujan etiquetas de adentro (ver
ui/piezas_ventana.tarjeta_de_menu). Se prueba sin abrir ninguna ventana (plataforma
"offscreen").

Se ejecutan con:

    python -m unittest discover tests
"""

import os
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QPushButton  # noqa: E402

import dominio  # noqa: E402
from repositories import usuarios_repo  # noqa: E402
from ui.administrar_kiosko_window import AdministrarKioskoWindow  # noqa: E402
from ui.main_window import ConfiguracionAdminWindow, MainWindow  # noqa: E402
from base import BaseConBaseTemporal  # noqa: E402

_app = QApplication.instance() or QApplication([])

# El cartel de ui.piezas_ventana.restringir: en las pruebas no se abre (es modal).
_AVISO = "ui.piezas_ventana.avisar_acceso_restringido"


def _nombre(boton):
    """Cómo se llama un botón: el título de una tarjeta o el texto de una tecla."""
    return boton.accessibleName() or boton.text()


def _restringido(boton):
    return bool(boton.property("restringido"))

# Botón de la barra -> la ventana que abre (el nombre en ui.main_window).
_CON_PERMISO = {
    "🛠️  ADMIN KIOSKO": "AdministrarKioskoWindow",
    "⚙️  CONFIG ADMIN": "ConfiguracionAdminWindow",
}


class _ConUsuarios(BaseConBaseTemporal):
    def _usuario(self, nombre, rol, permisos=None):
        return usuarios_repo.obtener_usuario(usuarios_repo.crear_usuario(nombre, "1234", rol, permisos))


class TestBarraParaTodos(_ConUsuarios):
    def _ventana(self, nombre, rol, permisos=None):
        ventana = MainWindow(self._usuario(nombre, rol, permisos), lambda: None)
        self.addCleanup(ventana.deleteLater)
        return ventana

    def _botones(self, ventana):
        barra = ventana.findChild(QFrame, "encabezadoInicio")
        return {boton.text(): boton for boton in barra.findChildren(QPushButton)}

    def _que_abre(self, ventana, avisados=None):
        """Aprieta cada botón con permiso y devuelve cuáles abrieron su ventana; los
        que dijeron "Acceso Restringido" van a `avisados`."""
        botones = self._botones(ventana)
        abiertos = set()
        for texto, ventana_que_abre in _CON_PERMISO.items():
            with mock.patch(f"ui.main_window.{ventana_que_abre}") as clase, mock.patch(_AVISO) as aviso:
                botones[texto].click()
            if clase.called:
                abiertos.add(texto)
            if aviso.called and avisados is not None:
                avisados.add(texto)
        return abiertos

    def test_una_empleada_ve_los_mismos_botones_que_el_admin(self):
        admin = self._ventana("Admin", dominio.ROL_ADMIN)
        empleada = self._ventana("TOBY", dominio.ROL_EMPLEADA)

        self.assertEqual(list(self._botones(empleada)), list(self._botones(admin)))

    def test_cambiar_pass_va_a_la_derecha_de_operador(self):
        # Pedido del dueño, 2026-11-04: el botón que se llamaba "Clave" iba antes de
        # Lista de Compras; lo quiso a la derecha de Operador y llamado "Cambiar Pass".
        # Ese mismo día sumó ORDENAR $ a su derecha (tests/test_acomodar_caja.py).
        ventana = self._ventana("TOBY", dominio.ROL_EMPLEADA)
        textos = [texto.strip() for texto in self._botones(ventana)]

        self.assertEqual(textos[-4:], ["📝  LISTA DE COMPRAS", "OPERADOR", "🔑  CAMBIAR PASS", "🧮  ORDENAR $"])
        self.assertFalse(any(texto.endswith("CLAVE") for texto in textos), textos)

    def test_los_que_no_le_tocan_se_ven_igual_y_dicen_acceso_restringido(self):
        empleada = self._ventana("TOBY", dominio.ROL_EMPLEADA)
        botones = self._botones(empleada)

        for texto in _CON_PERMISO:
            # Ni gris ni de otro color: la misma tecla que el resto de la barra.
            self.assertTrue(botones[texto].isEnabled(), texto)
            self.assertEqual(botones[texto].property("clase"), "barra", texto)
        avisados = set()
        self.assertEqual(self._que_abre(empleada, avisados), set())
        self.assertEqual(avisados, set(_CON_PERMISO))

    def test_el_admin_abre_todo(self):
        admin = self._ventana("Admin", dominio.ROL_ADMIN)

        self.assertEqual(self._que_abre(admin), set(_CON_PERMISO))

    def test_cada_empleada_abre_solo_lo_que_tiene_habilitado(self):
        encargada = self._ventana("Encargada", dominio.ROL_EMPLEADA, {"permiso_reportes": True})

        self.assertEqual(self._que_abre(encargada), {"🛠️  ADMIN KIOSKO"})

    def test_config_admin_no_se_delega_con_ningun_permiso(self):
        todos = {clave: True for clave, _ in usuarios_repo.PERMISOS_EMPLEADA}
        encargada = self._ventana("Encargada", dominio.ROL_EMPLEADA, todos)

        self.assertEqual(self._que_abre(encargada), {"🛠️  ADMIN KIOSKO"})


class TestConfiguracionAdminParaUnOperador(_ConUsuarios):
    def _tarjetas(self, usuario):
        """Las tarjetas (sin el Cerrar del final)."""
        ventana = ConfiguracionAdminWindow(usuario)
        self.addCleanup(ventana.deleteLater)
        return [b for b in ventana.findChildren(QPushButton) if b.accessibleName()]

    def test_un_operador_lo_ve_todo_igual_pero_restringido(self):
        tarjetas = self._tarjetas(self._usuario("TOBY", dominio.ROL_EMPLEADA))

        self.assertGreater(len(tarjetas), 1)
        for tarjeta in tarjetas:
            # Ni gris ni con candado: igual que las ve el Admin.
            self.assertTrue(tarjeta.isEnabled(), _nombre(tarjeta))
            self.assertNotEqual(tarjeta.icono.text(), "🔒", _nombre(tarjeta))
            self.assertTrue(_restringido(tarjeta), _nombre(tarjeta))

    def test_al_apretarla_dice_acceso_restringido_y_no_abre_nada(self):
        for tarjeta in self._tarjetas(self._usuario("TOBY", dominio.ROL_EMPLEADA)):
            with mock.patch(_AVISO) as aviso, \
                    mock.patch("ui.configuracion_admin_window.AccesosAdminWindow") as accesos, \
                    mock.patch("ui.configuracion_admin_window.DialogoEntrarDesdeOtraPC") as remota, \
                    mock.patch("ui.configuracion_admin_window.DialogoEnvioPwa") as envio:
                tarjeta.click()
            aviso.assert_called_once()
            self.assertFalse(accesos.called or remota.called or envio.called, _nombre(tarjeta))

    def test_ni_con_todos_los_permisos_usa_nada(self):
        todos = {clave: True for clave, _ in usuarios_repo.PERMISOS_EMPLEADA}
        tarjetas = self._tarjetas(self._usuario("TOBY", dominio.ROL_EMPLEADA, todos))

        self.assertTrue(all(_restringido(tarjeta) for tarjeta in tarjetas))

    def test_el_admin_usa_todo(self):
        tarjetas = self._tarjetas(self._usuario("Admin", dominio.ROL_ADMIN))

        self.assertFalse(any(_restringido(tarjeta) for tarjeta in tarjetas))


class TestAdministrarKiosko(_ConUsuarios):
    """Administrar Kiosko con el diseño de Configuración ADMIN (pedido del dueño,
    2026-10-26): una encargada usa solo las pantallas que tiene habilitadas y ve las
    demás igual, pero dicen "Acceso Restringido" (2026-11-04; antes iban en gris con
    candado, y antes de eso no aparecían)."""

    def _ventana(self, usuario):
        ventana = AdministrarKioskoWindow(usuario, dominio.es_admin(usuario))
        self.addCleanup(ventana.deleteLater)
        return ventana

    def _tarjetas(self, ventana):
        return {b.accessibleName(): b for b in ventana.findChildren(QPushButton) if b.accessibleName()}

    def test_el_admin_usa_todo_y_puede_anular(self):
        tarjetas = self._tarjetas(self._ventana(self._usuario("Admin", dominio.ROL_ADMIN)))

        self.assertEqual(sorted(tarjetas), ["Artículos", "Cambio Fijo", "Compras", "Consulta de Ventas / Anular",
                                            "Control de Cierres de Turno", "Control de Stock", "Reportes",
                                            "Usuarios"])
        self.assertFalse(any(_restringido(tarjeta) for tarjeta in tarjetas.values()))

    def test_una_encargada_usa_solo_lo_que_tiene_habilitado(self):
        encargada = self._usuario("TOBY", dominio.ROL_EMPLEADA, {"permiso_reportes": True})

        tarjetas = self._tarjetas(self._ventana(encargada))

        # Las mismas tarjetas que el Admin, ninguna en gris ni con candado.
        self.assertIn("Consulta de Ventas / Anular", tarjetas)
        self.assertTrue(all(tarjeta.isEnabled() for tarjeta in tarjetas.values()))
        self.assertNotIn("🔒", [tarjeta.icono.text() for tarjeta in tarjetas.values()])
        # Usuarios, Control de Stock y Cambio Fijo son solo del Admin: ningún permiso los habilita.
        self.assertEqual([nombre for nombre, tarjeta in tarjetas.items() if not _restringido(tarjeta)], ["Reportes"])
        with mock.patch(_AVISO) as aviso, mock.patch("ui.administrar_kiosko_window.UsuariosWindow") as usuarios:
            tarjetas["Usuarios"].click()
        aviso.assert_called_once()
        usuarios.assert_not_called()
        with mock.patch(_AVISO) as aviso, mock.patch("ui.administrar_kiosko_window.DialogoFondoCambio") as cambio:
            tarjetas["Cambio Fijo"].click()
        aviso.assert_called_once()
        cambio.assert_not_called()

    def test_el_cambio_fijo_se_cambia_desde_su_tarjeta(self):
        # Pedido del dueño, 2026-11-04: la tecla estaba adentro de Usuarios y la quiso
        # afuera, a la vista con solo entrar a ADMIN KIOSKO.
        from repositories import config_repo

        ventana = self._ventana(self._usuario("Admin", dominio.ROL_ADMIN))
        with mock.patch("ui.administrar_kiosko_window.DialogoFondoCambio") as clase, \
                mock.patch("ui.administrar_kiosko_window.mostrar_info") as aviso:
            clase.return_value.exec.return_value = True
            clase.return_value.spin_monto.value.return_value = 42000.0
            self._tarjetas(ventana)["Cambio Fijo"].click()

        # Abre con el que está guardado y graba el nuevo.
        self.assertEqual(clase.call_args.args[1], 50000.0)
        self.assertEqual(config_repo.obtener_fondo_cambio(), 42000.0)
        aviso.assert_called_once()

    def test_cancelar_no_cambia_el_cambio_fijo(self):
        from repositories import config_repo

        ventana = self._ventana(self._usuario("Admin", dominio.ROL_ADMIN))
        with mock.patch("ui.administrar_kiosko_window.DialogoFondoCambio") as clase:
            clase.return_value.exec.return_value = False
            clase.return_value.spin_monto.value.return_value = 1.0
            self._tarjetas(ventana)["Cambio Fijo"].click()

        self.assertEqual(config_repo.obtener_fondo_cambio(), 50000.0)

    def test_usuarios_ya_no_tiene_la_tecla_del_cambio_fijo(self):
        from ui.usuarios_window import UsuariosWindow

        usuarios = UsuariosWindow(self._usuario("Admin", dominio.ROL_ADMIN))
        self.addCleanup(usuarios.deleteLater)

        textos = [boton.text() for boton in usuarios.findChildren(QPushButton)]
        self.assertFalse([texto for texto in textos if "CAMBIO" in texto.upper()], textos)

    def test_cada_tarjeta_abre_su_pantalla(self):
        tarjetas = self._tarjetas(self._ventana(self._usuario("Admin", dominio.ROL_ADMIN)))

        for nombre, pantalla in (("Artículos", "ArticulosWindow"), ("Compras", "ComprasWindow"),
                                 ("Control de Stock", "VentanaControlStock"),
                                 ("Consulta de Ventas / Anular", "ConsultaVentasWindow"),
                                 ("Reportes", "ReportesWindow"),
                                 ("Control de Cierres de Turno", "ControlCierresWindow"),
                                 ("Usuarios", "UsuariosWindow")):
            with mock.patch(f"ui.administrar_kiosko_window.{pantalla}") as clase:
                tarjetas[nombre].click()
            clase.assert_called_once()
