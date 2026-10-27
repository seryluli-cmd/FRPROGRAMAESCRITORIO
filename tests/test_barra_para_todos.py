"""
tests/test_barra_para_todos.py
================================
La barra de arriba de la ventana principal muestra los mismos botones a todos
(pedido del dueño, 2026-10-19: con solo los suyos, la barra de una empleada quedaba
muy vacía). Los que no le tocan a alguien se ven igual que los demás pero no abren
nada al apretarlos. Configuración ADMIN es solo del Administrador (acá adentro no
quedó nada que use un Operador): una empleada ve el botón igual, pero no abre. Las
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
from ui.administrar_kiosko_window import TEXTO_SIN_PERMISO, AdministrarKioskoWindow  # noqa: E402
from ui.main_window import ConfiguracionAdminWindow, MainWindow  # noqa: E402
from ui.piezas_ventana import TEXTO_SOLO_ADMIN  # noqa: E402
from base import BaseConBaseTemporal  # noqa: E402

_app = QApplication.instance() or QApplication([])


def _nombre(boton):
    """Cómo se llama un botón: el título de una tarjeta o el texto de una tecla."""
    return boton.accessibleName() or boton.text()

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

    def _que_abre(self, ventana):
        """Aprieta cada botón con permiso y devuelve cuáles abrieron su ventana."""
        botones = self._botones(ventana)
        abiertos = set()
        for texto, ventana_que_abre in _CON_PERMISO.items():
            with mock.patch(f"ui.main_window.{ventana_que_abre}") as clase:
                botones[texto].click()
            if clase.called:
                abiertos.add(texto)
        return abiertos

    def test_una_empleada_ve_los_mismos_botones_que_el_admin(self):
        admin = self._ventana("Admin", dominio.ROL_ADMIN)
        empleada = self._ventana("TOBY", dominio.ROL_EMPLEADA)

        self.assertEqual(list(self._botones(empleada)), list(self._botones(admin)))

    def test_los_que_no_le_tocan_se_ven_igual_pero_no_abren_nada(self):
        empleada = self._ventana("TOBY", dominio.ROL_EMPLEADA)
        botones = self._botones(empleada)

        for texto in _CON_PERMISO:
            # Ni gris ni de otro color: la misma tecla que el resto de la barra.
            self.assertTrue(botones[texto].isEnabled(), texto)
            self.assertEqual(botones[texto].property("clase"), "barra", texto)
        self.assertEqual(self._que_abre(empleada), set())

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
    def _habilitados(self, usuario):
        """Botón -> si se puede apretar (sin el Cerrar del final)."""
        ventana = ConfiguracionAdminWindow(usuario)
        self.addCleanup(ventana.deleteLater)
        return {_nombre(b): b.isEnabled() for b in ventana.findChildren(QPushButton) if b.text() != "CERRAR"}

    def test_un_operador_lo_ve_todo_en_gris(self):
        habilitados = self._habilitados(self._usuario("TOBY", dominio.ROL_EMPLEADA))

        self.assertEqual([texto for texto, si in habilitados.items() if si], [])
        self.assertGreater(len(habilitados), 1)  # sigue a la vista, en gris

    def test_lo_que_no_usa_el_operador_dice_que_es_del_admin(self):
        ventana = ConfiguracionAdminWindow(self._usuario("TOBY", dominio.ROL_EMPLEADA))
        self.addCleanup(ventana.deleteLater)

        for tarjeta in ventana.findChildren(QPushButton):
            if tarjeta.accessibleName() and not tarjeta.isEnabled():
                self.assertEqual((tarjeta.icono.text(), tarjeta.detalle.text()), ("🔒", TEXTO_SOLO_ADMIN))

    def test_ni_con_todos_los_permisos_usa_nada(self):
        todos = {clave: True for clave, _ in usuarios_repo.PERMISOS_EMPLEADA}
        habilitados = self._habilitados(self._usuario("TOBY", dominio.ROL_EMPLEADA, todos))

        self.assertEqual([texto for texto, si in habilitados.items() if si], [])

    def test_el_admin_usa_todo(self):
        habilitados = self._habilitados(self._usuario("Admin", dominio.ROL_ADMIN))

        self.assertTrue(all(habilitados.values()), habilitados)


class TestAdministrarKiosko(_ConUsuarios):
    """Administrar Kiosko con el diseño de Configuración ADMIN (pedido del dueño,
    2026-10-26): una encargada usa solo las pantallas que tiene habilitadas y ve las
    demás en gris, con candado y el porqué (antes no aparecían)."""

    def _ventana(self, usuario):
        ventana = AdministrarKioskoWindow(usuario, dominio.es_admin(usuario))
        self.addCleanup(ventana.deleteLater)
        return ventana

    def _tarjetas(self, ventana):
        return {b.accessibleName(): b for b in ventana.findChildren(QPushButton) if b.accessibleName()}

    def test_el_admin_usa_todo_y_puede_anular(self):
        tarjetas = self._tarjetas(self._ventana(self._usuario("Admin", dominio.ROL_ADMIN)))

        self.assertEqual(sorted(tarjetas), ["Artículos", "Compras", "Consulta de Ventas / Anular",
                                            "Control de Cierres de Turno", "Control de Stock", "Reportes",
                                            "Usuarios"])
        self.assertTrue(all(tarjeta.isEnabled() for tarjeta in tarjetas.values()))

    def test_una_encargada_usa_solo_lo_que_tiene_habilitado(self):
        encargada = self._usuario("TOBY", dominio.ROL_EMPLEADA, {"permiso_reportes": True})

        tarjetas = self._tarjetas(self._ventana(encargada))

        self.assertEqual([nombre for nombre, tarjeta in tarjetas.items() if tarjeta.isEnabled()], ["Reportes"])
        self.assertIn("Consulta de Ventas", tarjetas)  # sin "/ Anular": anular es del Admin
        # Usuarios y Control de Stock son solo del Admin: ningún permiso los habilita.
        self.assertEqual(tarjetas["Usuarios"].detalle.text(), TEXTO_SOLO_ADMIN)
        self.assertEqual(tarjetas["Control de Stock"].detalle.text(), TEXTO_SOLO_ADMIN)
        for nombre in ("Artículos", "Compras", "Consulta de Ventas", "Control de Cierres de Turno"):
            self.assertEqual((tarjetas[nombre].icono.text(), tarjetas[nombre].detalle.text()),
                             ("🔒", TEXTO_SIN_PERMISO), nombre)

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
