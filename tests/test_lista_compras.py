"""
tests/test_lista_compras.py
===========================
LISTA DE COMPRAS (pedido del dueño, 2026-10-31): el botón de la barra que va antes
de Operador abre la lista de los artículos con 4 unidades o menos (también los de 0
o negativo), de la A a la Z, para imprimirla. Impresiones no sale. La abre
cualquiera. Las pantallas se prueban sin abrir ninguna ventana (plataforma
"offscreen" de Qt).
"""

import os
from datetime import datetime
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QFrame, QPushButton  # noqa: E402

import dominio  # noqa: E402
from database import conexion_db  # noqa: E402
from repositories import articulos_repo, usuarios_repo  # noqa: E402
from ui.lista_compras_window import COLUMNA_STOCK, VentanaListaDeCompras  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from base import BaseConBaseTemporal  # noqa: E402

_app = QApplication.instance() or QApplication([])


def _articulo(codigo, descripcion, stock):
    return {"codigo": codigo, "descripcion": descripcion, "stock": stock}


class TestLaCuenta(BaseConBaseTemporal):
    def test_los_de_4_o_menos_de_la_a_a_la_z_sin_impresiones_ni_fotocopias(self):
        articulos = [
            _articulo("1", "Zucaritas 300 g", 4), _articulo("2", "alfajor Jorgito", 15),
            _articulo("3", "Coca 500", 5), _articulo("5", "Álamo chicles", 2),
            _articulo("6", "Bon o Bon", 0), _articulo("7", "Agua 500", -3),
            _articulo(dominio.CODIGO_ARTICULO_IMPRESIONES, "Impresiones", -40),
            _articulo(dominio.CODIGO_ARTICULO_FOTOCOPIAS, "Fotocopias", 0),
        ]
        self.assertEqual([a["descripcion"] for a in dominio.articulos_para_comprar(articulos)],
                         ["Agua 500", "Álamo chicles", "Bon o Bon", "Zucaritas 300 g"])

    def test_el_tope_es_4(self):
        self.assertEqual(dominio.STOCK_PARA_LISTA_DE_COMPRAS, 4)


class BaseListaDeCompras(BaseConBaseTemporal):
    def setUp(self):
        super().setUp()
        self.rubro_bebidas = articulos_repo.crear_rubro("Bebidas Prueba")
        self.rubro_golosinas = articulos_repo.crear_rubro("Golosinas Prueba")
        for codigo, descripcion, rubro, stock in [
            ("11", "Zucaritas 300 g", None, 4), ("12", "alfajor Jorgito", self.rubro_golosinas, 15),
            ("13", "Coca 500", self.rubro_bebidas, 1), ("14", "Álamo chicles", self.rubro_golosinas, 2),
            ("15", "Agua 500", self.rubro_bebidas, -3),
        ]:
            articulos_repo.crear_articulo(codigo, descripcion, None, rubro, 100.0, 50.0, 0)
            with conexion_db() as conexion:
                conexion.execute("UPDATE articulos SET stock = ? WHERE codigo = ?", (stock, codigo))

    def ventana(self):
        ventana = VentanaListaDeCompras()
        self.addCleanup(ventana.deleteLater)
        return ventana


class TestVentana(BaseListaDeCompras):
    def filas(self, tabla):
        return [(tabla.item(fila, 0).text(), tabla.item(fila, COLUMNA_STOCK).text())
                for fila in range(tabla.rowCount())]

    def test_muestra_los_de_4_o_menos_con_su_stock(self):
        tabla = self.ventana().tabla
        self.assertEqual(self.filas(tabla), [("Agua 500", "-3"), ("Álamo chicles", "2"),
                                             ("Coca 500", "1"), ("Zucaritas 300 g", "4")])
        self.assertEqual(tabla.item(0, COLUMNA_STOCK).textAlignment(), Qt.AlignRight | Qt.AlignVCenter)

    def test_los_que_ya_no_tienen_van_en_rojo(self):
        tabla = self.ventana().tabla
        self.assertEqual(tabla.item(0, COLUMNA_STOCK).foreground().color(), Qt.red)
        self.assertNotEqual(tabla.item(1, COLUMNA_STOCK).foreground().color(), Qt.red)

    def test_el_filtro_por_rubro(self):
        ventana = self.ventana()
        pastillas = {pastilla.text(): pastilla for pastilla in ventana.filtros.pastillas}
        self.assertEqual(list(pastillas), ["TODOS", "BEBIDAS PRUEBA", "GOLOSINAS PRUEBA"])
        pastillas["BEBIDAS PRUEBA"].click()
        self.assertEqual(self.filas(ventana.tabla), [("Agua 500", "-3"), ("Coca 500", "1")])
        self.assertIn("Lista de Compras — Bebidas Prueba", ventana.html_para_imprimir())
        pastillas["TODOS"].click()
        self.assertEqual(ventana.tabla.rowCount(), 4)

    def test_la_hoja_impresa_trae_la_columna_comprar_para_anotar_a_mano(self):
        html = self.ventana().html_para_imprimir(datetime(2026, 10, 31, 9, 30))
        self.assertIn("Lista de Compras", html)
        self.assertIn("Impreso el 31/10/2026 09:30", html)
        self.assertIn("4 artículos con 4 unidades o menos", html)
        self.assertIn(">Comprar<", html)
        self.assertLess(html.index("Agua 500"), html.index("Zucaritas 300 g"))
        self.assertNotIn("alfajor Jorgito", html)

    def test_imprimir_abre_la_vista_previa(self):
        ventana = self.ventana()
        with mock.patch("ui.lista_compras_window.imprimir.vista_previa") as vista_previa:
            ventana.boton_imprimir.click()
        vista_previa.assert_called_once()
        self.assertEqual(vista_previa.call_args.args[2], "Lista de Compras")


class TestElBotonDeLaBarra(BaseListaDeCompras):
    def botones(self, rol):
        usuario = usuarios_repo.obtener_usuario(usuarios_repo.crear_usuario(f"Prueba {rol}", "1234", rol))
        ventana = MainWindow(usuario, lambda: None)
        self.addCleanup(ventana.deleteLater)
        barra = ventana.findChild(QFrame, "encabezadoInicio")
        return [boton.text() for boton in barra.findChildren(QPushButton)]

    def test_va_justo_antes_de_operador(self):
        textos = self.botones(dominio.ROL_EMPLEADA)
        posicion = textos.index("📝  LISTA DE COMPRAS")
        self.assertIn("OPERADOR", textos[posicion + 1])

    def test_la_abre_cualquiera(self):
        usuario = usuarios_repo.obtener_usuario(usuarios_repo.crear_usuario("TOBY", "1234", dominio.ROL_EMPLEADA))
        ventana = MainWindow(usuario, lambda: None)
        self.addCleanup(ventana.deleteLater)
        boton = next(b for b in ventana.findChildren(QPushButton) if b.text() == "📝  LISTA DE COMPRAS")
        with mock.patch("ui.main_window.VentanaListaDeCompras") as clase:
            boton.click()
        clase.assert_called_once()
