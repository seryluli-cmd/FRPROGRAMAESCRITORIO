"""
tests/test_venta_buscar_en_el_campo.py
========================================
Venta de Mercadería busca por descripción o por marca en su MISMO campo de
arriba, sin abrir otra ventana (pedido del dueño, 2026-11-02: el cuadro chico
aparte "no es estético, ni lógico, ni práctico"). F6/F7 cambian el criterio, el
dibujo del campo pasa a "ABC" (o a la etiqueta de la marca) y lo encontrado se
elige en una lista debajo del campo. La pistola sigue andando en los tres
criterios (ver ui/venta_buscador.py).

Se ejecutan con:

    python -m unittest discover tests
"""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import dominio  # noqa: E402
from repositories import articulos_repo, usuarios_repo  # noqa: E402
from ui.buscar_articulo import DialogoBuscarArticulo  # noqa: E402
from ui.ventas_dibujos import ROL_DETALLE  # noqa: E402
from ui.ventas_window import VentasWindow  # noqa: E402
from base import BaseConBaseTemporal  # noqa: E402

_app = QApplication.instance() or QApplication([])

COCA = "7790895000997"
COCA_ZERO = "7790895001000"
JORGITO = "7790580000001"


class TestBuscarEnElMismoCampo(BaseConBaseTemporal):
    def setUp(self):
        super().setUp()
        articulos_repo.crear_articulo(COCA, "Coca Cola 500", None, None, 1500.0, 900.0, 0,
                                      nombre_marca_nueva="Coca-Cola")
        articulos_repo.crear_articulo(COCA_ZERO, "Coca Cola Zero 500", None, None, 1600.0, 950.0, 0,
                                      nombre_marca_nueva="Coca-Cola")
        articulos_repo.crear_articulo(JORGITO, "Alfajor Jorgito", None, None, 800.0, 400.0, 0,
                                      nombre_marca_nueva="Jorgito")
        usuario = usuarios_repo.obtener_usuario(
            usuarios_repo.crear_usuario("Lucia", "1234", dominio.ROL_EMPLEADA))
        self.ventas = VentasWindow(usuario)
        self.addCleanup(self.ventas.deleteLater)
        self.ventas.show()
        _app.processEvents()
        self.campo = self.ventas.campo_codigo
        self.lista = self.ventas.buscador

    def _apretar(self, nombre):
        next(boton for boton in self.lista.botones if boton.text() == nombre).click()

    def _elegida(self):
        return [boton.text() for boton in self.lista.botones if boton.property("elegida")]

    def _en_la_lista(self):
        return [self.lista.item(fila, 0).text() for fila in range(self.lista.rowCount())]

    def _carrito(self):
        return [(linea["codigo"], linea["cantidad"]) for linea in self.ventas.carrito]

    def _dibujo_del_campo(self):
        """Qué dibujo tiene el campo a la izquierda, y cómo se ve."""
        etiqueta = self.lista.dibujo_del_campo
        return etiqueta.accessibleName(), etiqueta.pixmap().toImage()

    def test_arranca_con_el_codigo_de_barras(self):
        self.assertEqual(self.lista.criterio, "codigo")
        self.assertEqual(self._elegida(), ["Código"])
        self.assertEqual(self.campo.placeholderText(), "Escaneá el código de barras o escribí el nombre del producto...")
        # El código de barras con "Abc" al lado: da lo mismo escanear que escribir (2026-11-04).
        self.assertEqual(self._dibujo_del_campo()[0], "dibujo_codigo_o_abc")
        self.assertFalse(self.lista.isVisible())

    def test_f6_cambia_el_criterio_y_el_dibujo_sin_abrir_otra_ventana(self):
        codigo_de_barras = self._dibujo_del_campo()[1]
        with mock.patch.object(DialogoBuscarArticulo, "exec") as cuadro_aparte:
            self._apretar("Descripción")
            _app.processEvents()
        cuadro_aparte.assert_not_called()
        self.assertEqual(self.lista.criterio, "descripcion")
        self.assertEqual(self._elegida(), ["Descripción"])
        self.assertTrue(self.campo.placeholderText().startswith("Escribí el nombre del producto"))
        self.assertEqual(self._dibujo_del_campo()[0], "dibujo_abc")
        self.assertNotEqual(self._dibujo_del_campo()[1], codigo_de_barras)

    def test_lo_escrito_abre_la_lista_y_enter_agrega_el_primero(self):
        self._apretar("Descripción")
        QTest.keyClicks(self.campo, "coca")
        self.assertTrue(self.lista.isVisible())
        self.assertEqual(self._en_la_lista(), ["Coca Cola 500", "Coca Cola Zero 500"])
        # Debajo, chiquito, el código y la marca; a la derecha, el precio.
        self.assertEqual(self.lista.item(0, 0).data(ROL_DETALLE), f"{COCA}  ·  Coca-Cola")
        self.assertEqual(self.lista.item(0, 1).text(), "$ 1.500")
        QTest.keyClick(self.campo, Qt.Key_Return)
        self.assertEqual(self._carrito(), [(COCA, 1)])
        self.assertEqual(self.campo.text(), "")
        self.assertFalse(self.lista.isVisible())
        # El criterio queda para el próximo producto.
        self.assertEqual(self.lista.criterio, "descripcion")

    def test_las_flechas_eligen_otro_de_la_lista(self):
        self._apretar("Descripción")
        QTest.keyClicks(self.campo, "coca")
        QTest.keyClick(self.campo, Qt.Key_Up)      # ya está en el primero: no se va
        self.assertEqual(self.lista.currentRow(), 0)
        QTest.keyClick(self.campo, Qt.Key_Down)
        QTest.keyClick(self.campo, Qt.Key_Down)    # no hay tercero: se queda en el último
        self.assertEqual(self.lista.currentRow(), 1)
        QTest.keyClick(self.campo, Qt.Key_Return)
        self.assertEqual(self._carrito(), [(COCA_ZERO, 1)])

    def test_un_clic_en_la_lista_lo_agrega(self):
        self._apretar("Descripción")
        QTest.keyClicks(self.campo, "coca")
        renglon = self.lista.visualItemRect(self.lista.item(1, 0)).center()
        QTest.mouseClick(self.lista.viewport(), Qt.LeftButton, pos=renglon)
        self.assertEqual(self._carrito(), [(COCA_ZERO, 1)])
        self.assertEqual(self.campo.text(), "")
        self.assertFalse(self.lista.isVisible())

    def test_sin_nada_que_coincida_lo_dice_la_lista_y_enter_no_agrega_ni_cobra(self):
        QTest.keyClicks(self.campo, JORGITO)
        QTest.keyClick(self.campo, Qt.Key_Return)
        self._apretar("Descripción")
        QTest.keyClicks(self.campo, "zzz")
        self.assertEqual(self._en_la_lista(), ["No hay ningún producto que diga “zzz”"])
        with mock.patch.object(self.ventas, "_ir_a_cobrar") as cobrar:
            QTest.keyClick(self.campo, Qt.Key_Return)
        cobrar.assert_not_called()
        self.assertEqual(self._carrito(), [(JORGITO, 1)])
        self.assertEqual(self.campo.text(), "zzz")   # queda para corregirlo

    def test_la_pistola_anda_tambien_buscando_por_descripcion(self):
        self._apretar("Descripción")
        QTest.keyClicks(self.campo, JORGITO)
        QTest.keyClick(self.campo, Qt.Key_Return)
        self.assertEqual(self._carrito(), [(JORGITO, 1)])

    def test_la_cantidad_del_asterisco_vale_tambien(self):
        with mock.patch("ui.ventas_window.QInputDialog.getInt", return_value=(3, True)):
            self.ventas._cambiar_cantidad_pendiente()
        self._apretar("Descripción")
        QTest.keyClicks(self.campo, "jorg")
        QTest.keyClick(self.campo, Qt.Key_Return)
        self.assertEqual(self._carrito(), [(JORGITO, 3)])

    def test_f7_busca_por_marca(self):
        self._apretar("Marca")
        self.assertEqual(self._elegida(), ["Marca"])
        self.assertEqual(self._dibujo_del_campo()[0], "dibujo_de_marca")
        QTest.keyClicks(self.campo, "coca-cola")
        self.assertEqual(self._en_la_lista(), ["Coca Cola 500", "Coca Cola Zero 500"])
        QTest.keyClicks(self.campo, "x")
        self.assertEqual(self._en_la_lista(), ["No hay ninguna marca que diga “coca-colax”"])

    def test_esc_borra_lo_escrito_y_despues_vuelve_al_codigo_sin_cerrar_la_venta(self):
        self._apretar("Descripción")
        QTest.keyClicks(self.campo, "coca")
        QTest.keyClick(self.campo, Qt.Key_Escape)
        self.assertEqual(self.campo.text(), "")
        self.assertEqual(self.lista.criterio, "descripcion")
        self.assertFalse(self.lista.isVisible())
        QTest.keyClick(self.campo, Qt.Key_Escape)
        self.assertEqual(self.lista.criterio, "codigo")
        self.assertEqual(self._elegida(), ["Código"])
        self.assertTrue(self.ventas.isVisible())

    def test_una_letra_pasa_sola_a_la_descripcion_y_los_numeros_al_codigo(self):
        # Pedido del dueño, 2026-11-04: sin apretar F6 ni F5.
        QTest.keyClicks(self.campo, "jorg")
        self.assertEqual(self.lista.criterio, "descripcion")
        self.assertEqual(self._dibujo_del_campo()[0], "dibujo_abc")
        self.assertEqual(self._en_la_lista(), ["Alfajor Jorgito"])
        QTest.keyClick(self.campo, Qt.Key_Return)
        # Con el campo en ABC, la pistola entra como código.
        QTest.keyClicks(self.campo, COCA)
        self.assertEqual(self.lista.criterio, "codigo")
        self.assertFalse(self.lista.isVisible())
        QTest.keyClick(self.campo, Qt.Key_Return)
        self.assertEqual(self._carrito(), [(JORGITO, 1), (COCA, 1)])

    def test_por_marca_las_letras_la_dejan_en_marca(self):
        self._apretar("Marca")
        QTest.keyClicks(self.campo, "jorgito")
        self.assertEqual(self.lista.criterio, "marca")

    def test_f5_vuelve_al_codigo_de_barras_y_cierra_la_lista(self):
        self._apretar("Descripción")
        QTest.keyClicks(self.campo, "coca")
        self._apretar("Código")
        self.assertEqual(self.lista.criterio, "codigo")
        self.assertFalse(self.lista.isVisible())
        self.assertEqual(self.campo.text(), "coca")   # lo escrito queda
        # Por código, lo que no es ningún artículo se avisa como siempre.
        with mock.patch("ui.buscar_articulo.mostrar_error") as aviso:
            QTest.keyClick(self.campo, Qt.Key_Return)
        aviso.assert_called_once()
        self.assertEqual(self._carrito(), [])


if __name__ == "__main__":
    unittest.main()
