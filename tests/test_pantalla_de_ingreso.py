"""
tests/test_pantalla_de_ingreso.py
===================================
La pantalla de ingreso "Elegí tu Jugador" (la maqueta C que eligió el dueño el
2026-10-30): una ficha por usuario, cómo se elige (tocándola, con las flechas,
Inicio y Fin, o con la primera letra), que Enter pase a la clave, que con muchos
usuarios vayan en dos filas sin salirse de la pantalla, y que se entre igual que
con la lista desplegable de antes. Lo de Enter en el nombre está también en
tests/test_enter_como_tab.py y el título en tests/test_estilo_ui.py. Se prueba sin
abrir ninguna ventana, plataforma "offscreen" de Qt.

Se ejecutan con:

    python -m unittest discover tests
"""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout  # noqa: E402

import dominio  # noqa: E402
import main as programa  # noqa: E402
from repositories import usuarios_repo  # noqa: E402
from ui import login_window  # noqa: E402
from ui.login_dibujos import MAX_EN_UNA_FILA, iniciales  # noqa: E402
from ui.login_window import LoginWindow  # noqa: E402
from base import BaseConBaseTemporal  # noqa: E402

_app = QApplication.instance() or QApplication([])


class _ConUsuarios(BaseConBaseTemporal):
    """La base nueva trae al "Administrador"; se suman dos empleadas, una con el
    nombre en minúscula para ver que el orden no mira mayúsculas."""

    def setUp(self):
        super().setUp()
        usuarios_repo.crear_usuario("Camila", "1111", dominio.ROL_EMPLEADA)
        usuarios_repo.crear_usuario("beto", "2222", dominio.ROL_EMPLEADA)
        self.entraron = []
        # Los intentos fallidos se cuentan en el módulo (sobreviven a cerrar la pantalla).
        login_window._intentos_fallidos.clear()
        self.addCleanup(login_window._intentos_fallidos.clear)

    def _ventana(self):
        ventana = LoginWindow(self.entraron.append)
        self.addCleanup(ventana.deleteLater)
        ventana.show()
        ventana.activateWindow()
        QApplication.processEvents()
        return ventana

    @staticmethod
    def _nombres(fichas):
        return [fichas.itemText(i) for i in range(fichas.count())]


class TestElegirLaFicha(_ConUsuarios):
    def test_hay_una_ficha_por_usuario_activo_en_orden_alfabetico(self):
        baja = usuarios_repo.crear_usuario("Zulma", "3333", dominio.ROL_EMPLEADA)
        usuarios_repo.desactivar_usuario(baja)
        usuarios_repo.crear_usuario("Ángela", "4444", dominio.ROL_EMPLEADA)

        ventana = self._ventana()

        # Sin mirar mayúsculas ni acentos: "Ángela" va con las de la A.
        self.assertEqual(self._nombres(ventana.combo_nombre), ["Administrador", "Ángela", "beto", "Camila"])
        self.assertEqual(ventana.combo_nombre.currentText(), "Administrador")
        self.assertEqual(ventana.saludo.text(), "Hola, Administrador. Ingresá tu clave")

    def test_las_flechas_eligen_y_el_saludo_dice_a_quien(self):
        ventana = self._ventana()
        fichas = ventana.combo_nombre
        fichas.setFocus()

        QTest.keyClick(fichas, Qt.Key_Right)
        self.assertEqual(fichas.currentText(), "beto")
        self.assertEqual(ventana.saludo.text(), "Hola, beto. Ingresá tu clave")
        QTest.keyClick(fichas, Qt.Key_Right)
        QTest.keyClick(fichas, Qt.Key_Right)  # en la última se queda ahí
        self.assertEqual(fichas.currentText(), "Camila")
        QTest.keyClick(fichas, Qt.Key_Left)
        self.assertEqual(fichas.currentText(), "beto")
        QTest.keyClick(fichas, Qt.Key_Home)
        self.assertEqual(fichas.currentText(), "Administrador")
        QTest.keyClick(fichas, Qt.Key_End)
        self.assertEqual(fichas.currentText(), "Camila")
        # Con una sola fila, arriba y abajo hacen lo mismo que la lista de antes.
        QTest.keyClick(fichas, Qt.Key_Up)
        self.assertEqual(fichas.currentText(), "beto")
        QTest.keyClick(fichas, Qt.Key_Down)
        self.assertEqual(fichas.currentText(), "Camila")

    def test_una_letra_salta_al_nombre_que_empieza_con_ella(self):
        usuarios_repo.crear_usuario("Ángela", "4444", dominio.ROL_EMPLEADA)
        ventana = self._ventana()
        fichas = ventana.combo_nombre
        fichas.setFocus()

        QTest.keyClicks(fichas, "c")
        self.assertEqual(fichas.currentText(), "Camila")
        QTest.keyClicks(fichas, "B")
        self.assertEqual(fichas.currentText(), "beto")
        # Sin mirar acentos, y si hay dos con la misma letra va a la próxima.
        QTest.keyClicks(fichas, "a")
        self.assertEqual(fichas.currentText(), "Administrador")
        QTest.keyClicks(fichas, "a")
        self.assertEqual(fichas.currentText(), "Ángela")

    def test_tocar_una_ficha_la_elige_y_pasa_a_la_clave(self):
        ventana = self._ventana()
        fichas = ventana.combo_nombre

        QTest.mouseClick(fichas, Qt.LeftButton, Qt.NoModifier, fichas.rectangulo_de_la_ficha(2).center().toPoint())

        self.assertEqual(fichas.currentText(), "Camila")
        self.assertTrue(ventana.campo_clave.hasFocus())

    def test_tocar_entre_las_fichas_no_cambia_nada(self):
        ventana = self._ventana()
        fichas = ventana.combo_nombre
        fichas.setFocus()

        # (2, 2) y no (0, 0): con el punto (0, 0) QTest hace clic en el medio.
        QTest.mouseClick(fichas, Qt.LeftButton, Qt.NoModifier, QPoint(2, 2))

        self.assertEqual(fichas.currentText(), "Administrador")
        self.assertFalse(ventana.campo_clave.hasFocus())


class TestDosFilas(BaseConBaseTemporal):
    def _ventana_con(self, cantidad):
        # La base nueva ya trae al "Administrador".
        for numero in range(1, cantidad):
            usuarios_repo.crear_usuario(f"Usuaria con nombre largo {numero:02d}", "1234", dominio.ROL_EMPLEADA)
        ventana = LoginWindow(lambda _usuario: None)
        self.addCleanup(ventana.deleteLater)
        ventana.show()
        QApplication.processEvents()
        fichas = ventana.combo_nombre
        self.assertEqual(fichas.count(), cantidad)
        return ventana, fichas

    def _comprobar_que_entran(self, fichas):
        rectangulos = [fichas.rectangulo_de_la_ficha(i) for i in range(fichas.count())]
        for numero, rectangulo in enumerate(rectangulos):
            self.assertTrue(fichas.rect().toRectF().contains(rectangulo), (numero, rectangulo, fichas.rect()))
            for otro in rectangulos[numero + 1:]:
                self.assertFalse(rectangulo.intersects(otro), (rectangulo, otro))
        return rectangulos

    def test_hasta_el_maximo_van_en_una_fila(self):
        ventana, fichas = self._ventana_con(MAX_EN_UNA_FILA)

        rectangulos = self._comprobar_que_entran(fichas)

        self.assertEqual(len({r.top() for r in rectangulos}), 1)
        fichas.setCurrentIndex(MAX_EN_UNA_FILA - 1)
        self.assertFalse(ventana.grab().isNull())

    def test_con_mas_van_en_dos_filas_y_no_se_salen_de_la_pantalla(self):
        ventana, fichas = self._ventana_con(MAX_EN_UNA_FILA + 5)

        rectangulos = self._comprobar_que_entran(fichas)

        self.assertEqual(len({r.top() for r in rectangulos}), 2)
        fichas.setCurrentIndex(fichas.count() - 1)  # la elegida, abajo de todo
        self.assertFalse(ventana.grab().isNull())

    def test_con_muchisimos_tambien_entran(self):
        ventana, fichas = self._ventana_con(30)

        self._comprobar_que_entran(fichas)
        self.assertFalse(ventana.grab().isNull())

    def test_arriba_y_abajo_pasan_de_una_fila_a_la_otra(self):
        ventana, fichas = self._ventana_con(MAX_EN_UNA_FILA + 4)  # 5 arriba y 4 abajo
        ventana.activateWindow()
        fichas.setFocus()
        fichas.setCurrentIndex(1)

        QTest.keyClick(fichas, Qt.Key_Down)
        self.assertEqual(fichas.currentIndex(), 6)
        QTest.keyClick(fichas, Qt.Key_Down)  # ya está abajo
        self.assertEqual(fichas.currentIndex(), 6)
        QTest.keyClick(fichas, Qt.Key_Up)
        self.assertEqual(fichas.currentIndex(), 1)
        # La última de arriba no tiene nada justo debajo: va a la última de todas.
        fichas.setCurrentIndex(4)
        QTest.keyClick(fichas, Qt.Key_Down)
        self.assertEqual(fichas.currentIndex(), 8)


class TestEntrar(_ConUsuarios):
    def test_entra_con_la_ficha_elegida_y_su_clave(self):
        ventana = self._ventana()
        fichas = ventana.combo_nombre
        fichas.setFocus()
        QTest.keyClick(fichas, Qt.Key_End)
        QTest.keyClick(fichas, Qt.Key_Return)
        self.assertTrue(ventana.campo_clave.hasFocus())

        QTest.keyClicks(ventana.campo_clave, "1111")
        QTest.keyClick(ventana.campo_clave, Qt.Key_Return)

        self.assertEqual([usuario["nombre"] for usuario in self.entraron], ["Camila"])

    def test_con_la_clave_mal_avisa_y_no_entra(self):
        ventana = self._ventana()
        ventana.combo_nombre.setCurrentIndex(1)
        ventana.campo_clave.setText("1111")  # es la de Camila, no la de beto

        with mock.patch.object(login_window, "mostrar_error") as error:
            ventana._intentar_ingresar()

        error.assert_called_once_with(ventana, "Datos incorrectos", "Nombre o clave incorrectos.")
        self.assertEqual(self.entraron, [])
        self.assertEqual(ventana.campo_clave.text(), "")
        self.assertEqual(ventana.combo_nombre.currentText(), "beto")  # la ficha sigue elegida

    def test_a_las_cinco_claves_mal_se_bloquea_ese_usuario(self):
        ventana = self._ventana()
        ventana.combo_nombre.setCurrentIndex(1)

        with mock.patch.object(login_window, "mostrar_error") as error:
            for _ in range(login_window.MAX_INTENTOS):
                ventana.campo_clave.setText("9999")
                ventana._intentar_ingresar()
            ventana.campo_clave.setText("2222")  # ahora la buena: igual está bloqueado
            ventana._intentar_ingresar()

        self.assertEqual(error.call_args_list[-1].args[1], "Demasiados intentos")
        self.assertEqual(self.entraron, [])

    def test_sin_usuarios_lo_dice_y_no_deja_entrar(self):
        with mock.patch.object(usuarios_repo, "listar_usuarios", return_value=[]):
            ventana = self._ventana()

        self.assertEqual(ventana.combo_nombre.count(), 0)
        self.assertEqual(ventana.saludo.text(), "Todavía no hay ningún usuario cargado")
        self.assertFalse(ventana.grab().isNull())
        with mock.patch.object(login_window, "mostrar_error") as error:
            ventana._intentar_ingresar()
        self.assertEqual(error.call_args.args[1], "No hay usuarios")


class TestComoSeVe(_ConUsuarios):
    def test_las_iniciales_de_la_ficha(self):
        self.assertEqual(iniciales("Sergio"), "SE")
        self.assertEqual(iniciales("ana paula"), "AP")
        self.assertEqual(iniciales("Lu"), "LU")
        self.assertEqual(iniciales("J"), "J")
        self.assertEqual(iniciales("   "), "?")

    def test_la_animacion_corre_solo_con_la_pantalla_a_la_vista(self):
        ventana = self._ventana()
        self.assertTrue(ventana._animacion.isActive())

        ventana.close()  # al entrar, main.py la cierra

        self.assertFalse(ventana._animacion.isActive())

    def test_los_avisos_que_se_abren_encima_no_heredan_el_fondo_oscuro(self):
        # Los avisos (mostrar_error) y la caja que se abre al entrar son hijos de la
        # pantalla de ingreso: sus colores van por objectName en la hoja de estilos
        # global, nunca en una hoja local que pasaría a los hijos.
        self.addCleanup(_app.setStyleSheet, _app.styleSheet())
        _app.setStyleSheet(programa.HOJA_DE_ESTILOS)
        ventana = LoginWindow(lambda _usuario: None)
        self.addCleanup(ventana.deleteLater)
        dialogo = QDialog(ventana)
        texto_del_dialogo = QLabel("Nombre o clave incorrectos.", dialogo)
        QVBoxLayout(dialogo).addWidget(texto_del_dialogo)
        for etiqueta in (ventana.saludo, texto_del_dialogo):
            etiqueta.ensurePolished()

        letra_del_saludo = ventana.saludo.palette().color(QPalette.WindowText).name()
        letra_del_dialogo = texto_del_dialogo.palette().color(QPalette.WindowText).name()

        color_de_siempre = programa.HOJA_DE_ESTILOS.split("QWidget {", 1)[1].split("color:", 1)[1].split(";")[0]
        self.assertEqual(letra_del_dialogo, color_de_siempre.strip().lower())
        self.assertNotEqual(letra_del_saludo, letra_del_dialogo)  # el saludo sí, clarito sobre el oscuro
        self.assertEqual(ventana.styleSheet(), "")


if __name__ == "__main__":
    unittest.main()
