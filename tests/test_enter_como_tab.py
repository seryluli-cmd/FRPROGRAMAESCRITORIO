"""
tests/test_enter_como_tab.py
==============================
Enter pasa al siguiente campo, como Tab, y en el último hace la acción principal
(pedido del dueño, 2026-10-18: que el mostrador ande sin tocar el mouse). Acá va el
login y, sobre todo, DÓNDE llega el Enter del teclado de verdad en cada tipo de
campo. La ventana de cobro está en tests/test_dialogo_pago.py y el botón
Impresiones en tests/test_impresiones.py. Se prueba sin abrir ninguna ventana,
plataforma "offscreen" de Qt.

Se ejecutan con:

    python -m unittest discover tests
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QComboBox, QDateEdit, QDialog, QDoubleSpinBox, QLineEdit, QSpinBox, QVBoxLayout,
)

import dominio  # noqa: E402
from repositories import usuarios_repo  # noqa: E402
from ui.login_window import LoginWindow  # noqa: E402
from ui.utils import encadenar_enter  # noqa: E402
from base import BaseConBaseTemporal  # noqa: E402

_app = QApplication.instance() or QApplication([])


def _enter(widget, repetido=False):
    """Un Enter en `widget`, adonde lo manda el teclado de verdad (al campo, no a su
    QLineEdit de adentro, ver TestDondeLlegaElEnter); `repetido` es la repetición del
    teclado (tecla apretada)."""
    for tipo in (QEvent.KeyPress, QEvent.KeyRelease):
        QApplication.sendEvent(widget, QKeyEvent(tipo, Qt.Key_Return, Qt.NoModifier, "\r", repetido))


class TestDondeLlegaElEnter(unittest.TestCase):
    """
    Con el teclado de verdad, el Enter le llega al widget que tiene el foco, y en
    un QSpinBox, QDoubleSpinBox, QDateEdit o QComboBox editable ese es el de
    afuera, no su QLineEdit de adentro. Hasta el 2026-10-18 `encadenar_enter` se
    enganchaba solo al de adentro: en el mostrador Enter no hacía nada en ningún
    importe (no cobraba, no contaba la plata) y las pruebas pasaban igual porque
    le mandaban el Enter directo al de adentro.
    """

    def _con_enter_encadenado(self, campo):
        ventana = QDialog()
        self.addCleanup(ventana.deleteLater)
        QVBoxLayout(ventana).addWidget(campo)
        veces = []
        encadenar_enter(campo, accion_final=lambda: veces.append(1))
        ventana.show()
        ventana.activateWindow()
        campo.setFocus()
        QApplication.processEvents()
        return veces

    def _campos(self):
        combo_editable = QComboBox()
        combo_editable.setEditable(True)
        return [QLineEdit(), QSpinBox(), QDoubleSpinBox(), QDateEdit(), combo_editable, QComboBox()]

    def test_el_enter_del_teclado_dispara_la_accion_en_cada_tipo_de_campo(self):
        for campo in self._campos():
            with self.subTest(campo=type(campo).__name__):
                veces = self._con_enter_encadenado(campo)

                _enter(QApplication.focusWidget())

                self.assertEqual(len(veces), 1)

    def test_un_enter_que_llega_al_campo_de_adentro_tambien_la_dispara_una_sola_vez(self):
        for campo in self._campos():
            interno = campo.lineEdit() if hasattr(campo, "lineEdit") else None
            if interno is None:
                continue
            with self.subTest(campo=type(campo).__name__):
                veces = self._con_enter_encadenado(campo)

                _enter(interno)

                self.assertEqual(len(veces), 1)

    def test_un_enter_que_queda_apretado_no_repite_la_accion(self):
        campo = QLineEdit()
        veces = self._con_enter_encadenado(campo)

        _enter(campo, repetido=True)

        self.assertEqual(veces, [])


class _ConUsuario(BaseConBaseTemporal):
    def setUp(self):
        super().setUp()
        usuario_id = usuarios_repo.crear_usuario("Lucia", "1234", dominio.ROL_ADMIN)
        self.usuario = usuarios_repo.obtener_usuario(usuario_id)

    def _mostrar(self, ventana):
        self.addCleanup(ventana.deleteLater)
        ventana.show()
        ventana.activateWindow()
        QApplication.processEvents()
        return ventana


class TestLogin(_ConUsuario):
    def test_enter_en_el_nombre_pasa_a_la_clave(self):
        login = self._mostrar(LoginWindow(lambda usuario: None))
        login.combo_nombre.setFocus()

        _enter(login.combo_nombre)

        self.assertTrue(login.campo_clave.hasFocus())


if __name__ == "__main__":
    unittest.main()
