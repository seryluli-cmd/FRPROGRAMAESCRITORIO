"""
tests/test_cuentas_de_articulos_y_reportes.py
===============================================
Tres cuentas que hacían las pantallas y hoy salen de dominio.py, con los
mismos números de antes:

- La calculadora de margen de Artículos (costo → precio de venta y al revés):
  `dominio.precio_con_margen` y `dominio.costo_sin_margen`.
- El "bajo el stock mínimo" (en rojo en Artículos y ORDENAR Stock, el aviso de
  Ventas con lo que ya está en el carrito): `dominio.bajo_el_minimo`.
- La fila TOTAL de Reportes > Totales: `dominio.suma_de_las_filas`.
- Los números de arriba de Artículos (maqueta B, 2026-10-30):
  `dominio.numeros_de_los_articulos`, y el filtro por rubro de esa grilla.

Las pantallas se prueban sin abrir ninguna ventana (plataforma "offscreen" de Qt).

Se ejecutan con:

    python -m unittest discover tests
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QTableWidgetItem  # noqa: E402

import dominio  # noqa: E402
from database import conexion_db  # noqa: E402
from repositories import articulos_repo, reportes_repo, usuarios_repo  # noqa: E402
from ui.articulos_tabla import poner_stock  # noqa: E402
from ui.articulos_window import ArticulosWindow, DialogoArticulo  # noqa: E402
from ui.reportes_window import PestañaTotales  # noqa: E402
from ui.utils import formato_pesos  # noqa: E402
from ui.ventas_window import VentasWindow  # noqa: E402
from base import BaseConBaseTemporal  # noqa: E402

_app = QApplication.instance() or QApplication([])


def _venta_de_siempre(costo, porcentaje):
    """La cuenta que hacía Artículos antes de pasar a dominio.py."""
    return round(costo * (1 + porcentaje / 100), 2)


def _costo_de_siempre(venta, porcentaje):
    return round(venta / (1 + porcentaje / 100), 2)


_COLUMNAS = ("kiosko", "impresiones", "total")


def _suma_de_siempre(filas):
    """La fila TOTAL que armaba Reportes > Totales antes de pasar a dominio.py."""
    return {clave: sum(fila[clave] for fila in filas) for clave in _COLUMNAS}


# ---------------------------------------------------------------------
# Margen
# ---------------------------------------------------------------------

class TestMargen(unittest.TestCase):
    def test_ida_y_vuelta_con_el_80_por_ciento(self):
        self.assertEqual(dominio.precio_con_margen(1000, 80), 1800.0)
        self.assertEqual(dominio.costo_sin_margen(1800, 80), 1000.0)

    def test_con_margen_0_queda_el_mismo_numero(self):
        for monto in (0, 1500, 1234.56, 0.07):
            self.assertEqual(dominio.precio_con_margen(monto, 0), monto)
            self.assertEqual(dominio.costo_sin_margen(monto, 0), monto)

    def test_con_costo_0_da_0(self):
        self.assertEqual(dominio.precio_con_margen(0, 80), 0.0)
        self.assertEqual(dominio.costo_sin_margen(0, 500), 0.0)

    def test_redondea_al_centavo_como_siempre(self):
        # Escrita como costo + costo * 250 / 100 daría 0,24: la cuenta se queda
        # multiplicando por (1 + %/100), como estaba en la pantalla.
        self.assertEqual(dominio.precio_con_margen(0.07, 250), 0.25)
        self.assertEqual(dominio.precio_con_margen(0.35, 190), 1.01)
        self.assertEqual(dominio.costo_sin_margen(1000, 30), 769.23)

    def test_da_lo_mismo_que_la_cuenta_de_siempre_en_todo_el_rango_del_porcentaje(self):
        # El % de la pantalla va de 0 a 500; los montos, con y sin centavos.
        for monto in (0, 0.07, 0.35, 1, 99.99, 333.33, 1234.5, 1500, 99_999.99, 12_345_678.91):
            for porcentaje in range(0, 501):
                self.assertEqual(dominio.precio_con_margen(monto, porcentaje),
                                 _venta_de_siempre(monto, porcentaje), (monto, porcentaje))
                self.assertEqual(dominio.costo_sin_margen(monto, porcentaje),
                                 _costo_de_siempre(monto, porcentaje), (monto, porcentaje))

    def test_con_pesos_enteros_la_vuelta_devuelve_el_mismo_costo(self):
        for costo in range(0, 20_001, 137):
            for porcentaje in range(0, 501, 5):
                precio = dominio.precio_con_margen(costo, porcentaje)
                self.assertEqual(dominio.costo_sin_margen(precio, porcentaje), costo, (costo, porcentaje))


class TestCalculadoraDeArticulos(BaseConBaseTemporal):
    def _dialogo(self, codigo=None):
        dialogo = DialogoArticulo(None, codigo)
        self.addCleanup(dialogo.deleteLater)
        return dialogo

    def test_calcular_la_venta_desde_el_costo(self):
        dialogo = self._dialogo()
        dialogo.spin_precio_compra.setValue(1000)
        dialogo.spin_pct_desde_costo.setValue(80)
        dialogo._calcular_venta_desde_costo()
        self.assertEqual(dialogo.spin_precio_venta.value(), 1800.0)
        self.assertEqual(dialogo.spin_precio_venta.text(), "$ 1.800")

    def test_calcular_el_costo_desde_la_venta(self):
        dialogo = self._dialogo()
        dialogo.spin_precio_venta.setValue(1800)
        dialogo.spin_pct_desde_venta.setValue(80)
        dialogo._calcular_costo_desde_venta()
        self.assertEqual(dialogo.spin_precio_compra.value(), 1000.0)
        self.assertEqual(dialogo.spin_precio_compra.text(), "$ 1.000")

    def test_con_centavos_y_con_costo_0(self):
        dialogo = self._dialogo()
        dialogo.spin_precio_compra.setValue(0.07)
        dialogo.spin_pct_desde_costo.setValue(250)
        dialogo._calcular_venta_desde_costo()
        self.assertEqual(dialogo.spin_precio_venta.value(), 0.25)

        dialogo.spin_precio_compra.setValue(0)
        dialogo._calcular_venta_desde_costo()
        self.assertEqual(dialogo.spin_precio_venta.value(), 0.0)


# ---------------------------------------------------------------------
# Bajo el stock mínimo
# ---------------------------------------------------------------------

class TestBajoElMinimo(unittest.TestCase):
    def test_el_borde(self):
        self.assertTrue(dominio.bajo_el_minimo(1, 2))     # uno menos: avisa
        self.assertFalse(dominio.bajo_el_minimo(2, 2))    # justo en el mínimo: todavía no
        self.assertFalse(dominio.bajo_el_minimo(3, 2))    # uno más

    def test_sin_minimo_y_con_stock_negativo(self):
        self.assertFalse(dominio.bajo_el_minimo(0, 0))
        # El stock puede quedar negativo a propósito: también sale en rojo.
        self.assertTrue(dominio.bajo_el_minimo(-1, 0))


class _ConAgua(BaseConBaseTemporal):
    """Un artículo con mínimo 2 y el stock que pida cada prueba."""

    MINIMO = 2

    def setUp(self):
        super().setUp()
        articulos_repo.crear_articulo("AGUA", "Agua", None, None, 1000.0, 500.0, self.MINIMO)

    def _poner_stock(self, stock):
        with conexion_db() as conexion:
            conexion.execute("UPDATE articulos SET stock = ? WHERE codigo = 'AGUA'", (stock,))


class TestStockEnRojoEnArticulos(_ConAgua):
    def _color_de_la_etiqueta(self, stock):
        self._poner_stock(stock)
        dialogo = DialogoArticulo(None, "AGUA")
        self.addCleanup(dialogo.deleteLater)
        self.assertEqual(dialogo.etiqueta_stock.text(), str(stock))
        return dialogo.etiqueta_stock.styleSheet()

    def test_modificar_muestra_en_rojo_solo_por_debajo_del_minimo(self):
        self.assertEqual(self._color_de_la_etiqueta(1), "color: red;")
        self.assertEqual(self._color_de_la_etiqueta(2), "")
        self.assertEqual(self._color_de_la_etiqueta(3), "")
        self.assertEqual(self._color_de_la_etiqueta(-1), "color: red;")

    def test_la_grilla_de_articulos_y_ordenar_stock(self):
        # poner_stock es la celda del stock de las dos grillas.
        item = QTableWidgetItem()
        poner_stock(item, 1, self.MINIMO)
        self.assertEqual(item.foreground().color(), Qt.red)
        poner_stock(item, 2, self.MINIMO)
        self.assertIsNone(item.data(Qt.ForegroundRole))
        poner_stock(item, 3, self.MINIMO)
        self.assertIsNone(item.data(Qt.ForegroundRole))


class TestNumerosDeLosArticulos(unittest.TestCase):
    def _articulo(self, codigo, stock, minimo, compra):
        return {"codigo": codigo, "stock": stock, "stock_minimo": minimo, "precio_compra": compra}

    def test_cuenta_los_bajo_el_minimo_y_el_valor_a_precio_de_compra(self):
        numeros = dominio.numeros_de_los_articulos([
            self._articulo("A", 10, 2, 150.5),   # 1505
            self._articulo("B", 1, 2, 100.0),    # bajo el mínimo: 100
            self._articulo("C", 2, 2, 300.0),    # justo en el mínimo: no avisa; 600
        ])
        self.assertEqual(numeros, {"cantidad": 3, "bajo_el_minimo": 1, "valor_del_stock": 2205.0})

    def test_el_stock_negativo_vale_cero_pero_cuenta_como_bajo_el_minimo(self):
        numeros = dominio.numeros_de_los_articulos([self._articulo("A", -5, 0, 100.0)])
        self.assertEqual(numeros, {"cantidad": 1, "bajo_el_minimo": 1, "valor_del_stock": 0})

    def test_impresiones_no_entra(self):
        numeros = dominio.numeros_de_los_articulos(
            [self._articulo(dominio.CODIGO_ARTICULO_IMPRESIONES, -130, 0, 40.0)])
        self.assertEqual(numeros, {"cantidad": 0, "bajo_el_minimo": 0, "valor_del_stock": 0})


class TestArticulosConLaMaquetaB(_ConAgua):
    def setUp(self):
        super().setUp()
        self.bebidas = articulos_repo.crear_rubro("BEBIDAS")
        articulos_repo.crear_rubro("GOLOSINAS")
        articulos_repo.crear_articulo("COCA", "Coca", None, self.bebidas, 2000.0, 1000.0, 0)
        self.ventana = ArticulosWindow(None, None)
        self.addCleanup(self.ventana.deleteLater)

    def _codigos(self):
        return sorted(self.ventana.tabla.item(fila, 0).text() for fila in range(self.ventana.tabla.rowCount()))

    def test_arriba_dice_cuantos_hay_y_cuantos_quedaron_bajo_el_minimo(self):
        self._poner_stock(1)
        self.ventana._cargar_grilla()
        self.assertEqual(self.ventana.indicador_articulos.valor.text(), "2")
        self.assertEqual(self.ventana.indicador_bajo_minimo.valor.text(), "1")
        self.assertTrue(self.ventana.indicador_bajo_minimo.property("alerta"))
        self.assertEqual(self.ventana.indicador_rubros.valor.text(), str(len(articulos_repo.listar_rubros())))

    def test_el_filtro_por_rubro_y_el_buscador_se_suman(self):
        self.assertEqual(self._codigos(), ["AGUA", "COCA"])
        pastilla = next(p for p in self.ventana.filtros.pastillas if p.text() == "BEBIDAS")
        pastilla.click()
        self.assertEqual(self._codigos(), ["COCA"])
        self.ventana.campo_buscar.setText("AGUA")
        self.assertEqual(self._codigos(), [])
        self.ventana.filtros.pastillas[0].click()   # Todos
        self.assertEqual(self._codigos(), ["AGUA"])


class TestAvisoDeStockEnVentas(_ConAgua):
    def setUp(self):
        super().setUp()
        self.usuario = usuarios_repo.obtener_usuario(
            usuarios_repo.crear_usuario("Lucia", "1234", dominio.ROL_EMPLEADA))

    def _ventas(self):
        ventana = VentasWindow(self.usuario)
        self.addCleanup(ventana.deleteLater)
        ventana.show()
        _app.processEvents()
        return ventana

    @staticmethod
    def _escanear(ventana):
        QTest.keyClicks(ventana.campo_codigo, "AGUA")
        QTest.keyClick(ventana.campo_codigo, Qt.Key_Return)
        aviso = ventana.etiqueta_aviso_stock
        return aviso.text() if aviso.isVisibleTo(ventana) else ""

    def test_descuenta_lo_que_ya_esta_en_el_carrito(self):
        # Hay 5 y el mínimo es 2: avisa recién cuando lo que queda, contando el
        # carrito, es menos que 2.
        self._poner_stock(5)
        ventana = self._ventas()
        self.assertEqual(self._escanear(ventana), "")   # quedan 4
        self.assertEqual(self._escanear(ventana), "")   # quedan 3: uno más que el mínimo
        self.assertEqual(self._escanear(ventana), "")   # quedan 2: justo en el mínimo
        self.assertEqual(self._escanear(ventana), "Agua debajo de Stock Mín. Actualmente hay 1")
        self.assertEqual(ventana.carrito[0]["cantidad"], 4)

    def test_con_stock_negativo_avisa_con_el_numero_que_queda(self):
        self._poner_stock(0)
        ventana = self._ventas()
        self.assertEqual(self._escanear(ventana), "Agua debajo de Stock Mín. Actualmente hay -1")


# ---------------------------------------------------------------------
# Fila TOTAL de Reportes > Totales
# ---------------------------------------------------------------------

class TestSumaDeLasFilas(unittest.TestCase):
    def test_suma_cada_clave_en_el_orden_de_las_filas(self):
        filas = [{"etiqueta": "a", "x": 0.1, "y": 1}, {"etiqueta": "b", "x": 0.2, "y": 2},
                 {"etiqueta": "c", "x": 0.3, "y": 3}]
        self.assertEqual(dominio.suma_de_las_filas(filas, ("x", "y")),
                         {"x": sum(fila["x"] for fila in filas), "y": 6})

    def test_no_vuelve_a_redondear(self):
        # Las filas llegan ya redondeadas del repo; el TOTAL no se toca.
        self.assertEqual(dominio.suma_de_las_filas([{"x": 0.004}, {"x": 0.004}], ("x",)), {"x": 0.008})


class TestFilaTotalDeReportes(BaseConBaseTemporal):
    def setUp(self):
        super().setUp()
        self.usuario_id = usuarios_repo.crear_usuario("Lucia", "1234", dominio.ROL_EMPLEADA)
        articulos_repo.crear_articulo(dominio.CODIGO_ARTICULO_IMPRESIONES, "IMPRESIONES", None, None, 150.0, 0.0, 0)
        articulos_repo.crear_articulo("COD9", "Producto", None, None, 100.0, 50.0, 0)
        # Tres días seguidos (lunes 5 al miércoles 7), con centavos y con impresiones.
        self._venta("2026-01-05T10:00:00", [("COD9", 1500.10), ("4", 300.25)])
        self._venta("2026-01-06T10:00:00", [("COD9", 2300.20), ("4", 150.15)])
        self._venta("2026-01-07T10:00:00", [("COD9", 999.30)])

    def _venta(self, fecha, renglones):
        total = round(sum(subtotal for _, subtotal in renglones), 2)
        with conexion_db() as conexion:
            venta_id = conexion.execute(
                """INSERT INTO ventas (fecha, usuario_id, turno, total, estado, origen)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (fecha, self.usuario_id, dominio.TURNO_MANANA, total,
                 dominio.VENTA_CONFIRMADA, dominio.ORIGEN_KIOSKO),
            ).lastrowid
            for codigo, subtotal in renglones:
                conexion.execute(
                    """INSERT INTO venta_detalle
                       (venta_id, articulo_codigo, descripcion, cantidad, precio_unitario, subtotal)
                       VALUES (?, ?, ?, 1, ?, ?)""",
                    (venta_id, codigo, codigo, subtotal, subtotal),
                )
            conexion.execute(
                "INSERT INTO venta_pagos (venta_id, metodo, monto) VALUES (?, ?, ?)",
                (venta_id, dominio.PAGO_EFECTIVO, total),
            )

    def test_da_lo_mismo_que_la_suma_de_siempre(self):
        for agrupar_por in ("turno", "dia", "semana", "rango"):
            filas = reportes_repo.resumen_por_origen("2026-01-05", "2026-01-07", agrupar_por)
            self.assertEqual(dominio.suma_de_las_filas(filas, _COLUMNAS), _suma_de_siempre(filas), agrupar_por)

    def _pestaña(self, desde, hasta):
        pestaña = PestañaTotales()
        self.addCleanup(pestaña.deleteLater)
        pestaña.fecha_desde.setDate(desde)
        pestaña.fecha_hasta.setDate(hasta)
        return pestaña

    @staticmethod
    def _agrupar(pestaña, agrupar_por):
        pestaña.combo_agrupar.setCurrentIndex(pestaña.combo_agrupar.findData(agrupar_por))

    @staticmethod
    def _textos(pestaña, fila):
        return [pestaña.tabla.item(fila, columna).text() for columna in range(pestaña.tabla.columnCount())]

    def test_por_dia_el_total_va_al_pie_en_negrita_con_los_mismos_numeros(self):
        pestaña = self._pestaña(QDate(2026, 1, 5), QDate(2026, 1, 7))
        self._agrupar(pestaña, "dia")

        self.assertEqual(pestaña.tabla.rowCount(), 4)
        self.assertEqual(self._textos(pestaña, 0), ["05/01/2026", "$ 1.500,10", "$ 300,25", "$ 1.800,35"])
        self.assertFalse(pestaña.tabla.item(0, 0).font().bold())
        self.assertEqual(self._textos(pestaña, 3), ["TOTAL", "$ 4.799,60", "$ 450,40", "$ 5.250"])
        self.assertTrue(all(pestaña.tabla.item(3, columna).font().bold() for columna in range(4)))

        # Lo mismo que daba la suma que hacía la pantalla.
        filas = reportes_repo.resumen_por_origen("2026-01-05", "2026-01-07", "dia")
        sumas = _suma_de_siempre(filas)
        self.assertEqual(self._textos(pestaña, 3)[1:], [formato_pesos(sumas[clave]) for clave in _COLUMNAS])

    def test_por_turno_suma_los_tres_turnos(self):
        pestaña = self._pestaña(QDate(2026, 1, 5), QDate(2026, 1, 7))
        self._agrupar(pestaña, "turno")
        self.assertEqual(pestaña.tabla.rowCount(), len(dominio.TURNOS) + 1)
        self.assertEqual(self._textos(pestaña, len(dominio.TURNOS)), ["TOTAL", "$ 4.799,60", "$ 450,40", "$ 5.250"])

    def test_sin_fila_total_con_el_total_del_rango_o_con_un_solo_periodo(self):
        pestaña = self._pestaña(QDate(2026, 1, 5), QDate(2026, 1, 7))
        pestaña._buscar()   # "Total del rango" es el que viene elegido
        self.assertEqual(pestaña.tabla.rowCount(), 1)
        self.assertEqual(self._textos(pestaña, 0), ["Total del período", "$ 4.799,60", "$ 450,40", "$ 5.250"])

        pestaña.fecha_hasta.setDate(QDate(2026, 1, 5))
        self._agrupar(pestaña, "dia")
        self.assertEqual(pestaña.tabla.rowCount(), 1)
        self.assertEqual(self._textos(pestaña, 0)[0], "05/01/2026")


if __name__ == "__main__":
    unittest.main()
