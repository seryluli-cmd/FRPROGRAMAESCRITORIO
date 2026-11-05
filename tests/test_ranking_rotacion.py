"""
tests/test_ranking_rotacion.py
================================
RANKING DE ROTACIÓN (pedido del dueño, 2026-11-04): las cuentas de dominio.py
(unidades por día, para cuántos días alcanza el stock, lo que tarda en venderse una
compra y sus textos), los dos rankings de repositories/rotacion_repo.py (POR COMPRA:
cuánto tardó en venderse cada compra, con lo viejo saliendo primero y el promedio de
las últimas 3; POR PERÍODO: orden, días del local, sin anuladas ni impresiones), la
ventana con sus dos pestañas y el séptimo acceso del inicio, que abre quien tiene el
permiso de Reportes.

Se ejecutan con:

    python -m unittest discover tests
"""

import os
import unittest
from datetime import datetime, timedelta
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

import dominio  # noqa: E402
import turnos  # noqa: E402
from database import conexion_db  # noqa: E402
from repositories import articulos_repo, compras_repo, rotacion_repo, usuarios_repo, ventas_repo  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.ranking_rotacion_window import (  # noqa: E402
    COLUMNA_ALCANZA, COLUMNA_TARDA, PESTAÑA_COMPRA, PESTAÑA_PERIODO, VentanaRankingRotacion,
)
from base import BaseConBaseTemporal  # noqa: E402

_app = QApplication.instance() or QApplication([])


class TestCuentasDeLaRotacion(unittest.TestCase):
    def test_unidades_por_dia(self):
        self.assertEqual(dominio.unidades_por_dia(30, 30), 1.0)
        # Poco no es cero: 3 en 30 días es 0,1 por día.
        self.assertEqual(dominio.unidades_por_dia(3, 30), 0.1)
        self.assertEqual(dominio.unidades_por_dia(1, 90), 0.01)
        self.assertEqual(dominio.unidades_por_dia(0, 7), 0.0)
        with self.assertRaises(ValueError):
            dominio.unidades_por_dia(5, 0)

    def test_dias_que_alcanza(self):
        # 10 vendidas en 7 días con 25 en el estante: 17,5 días; el 18 ya falta.
        self.assertEqual(dominio.dias_que_alcanza(25, 10, 7), 17)
        self.assertEqual(dominio.dias_que_alcanza(30, 30, 30), 30)
        # Lo que no se vendió no se acaba nunca a ese ritmo.
        self.assertIsNone(dominio.dias_que_alcanza(12, 0, 30))
        # Sin stock (también en negativo) ya no alcanza para ningún día.
        self.assertEqual(dominio.dias_que_alcanza(0, 5, 30), 0)
        self.assertEqual(dominio.dias_que_alcanza(-3, 5, 30), 0)
        # Con lo vendido y no con el por día redondeado: 1 en 90 días con 1 en stock
        # son 90 días, no 100 (que daría 1 / 0,01).
        self.assertEqual(dominio.dias_que_alcanza(1, 1, 90), 90)

    def test_se_acaba_pronto(self):
        aviso = dominio.DIAS_PARA_AVISAR_ROTACION
        self.assertTrue(dominio.se_acaba_pronto(0))
        self.assertTrue(dominio.se_acaba_pronto(aviso - 1))
        self.assertFalse(dominio.se_acaba_pronto(aviso))
        self.assertFalse(dominio.se_acaba_pronto(None))

    def test_textos(self):
        self.assertEqual(dominio.texto_por_dia(12.0), "12")
        self.assertEqual(dominio.texto_por_dia(1.5), "1,5")
        self.assertEqual(dominio.texto_por_dia(0.03), "0,03")
        self.assertEqual(dominio.texto_por_dia(0), "0")
        self.assertEqual(dominio.texto_alcanza(None), "Sin ventas")
        self.assertEqual(dominio.texto_alcanza(0), "Sin stock")
        self.assertEqual(dominio.texto_alcanza(1), "1 día")
        self.assertEqual(dominio.texto_alcanza(12), "12 días")

    def test_texto_tiempo_de_venta(self):
        self.assertEqual(dominio.texto_tiempo_de_venta(0.01), "Menos de 1 hora")
        self.assertEqual(dominio.texto_tiempo_de_venta(1 / 24), "1 hora")
        self.assertEqual(dominio.texto_tiempo_de_venta(0.5), "12 horas")
        # Casi un día ya es "1 día", no "24 horas".
        self.assertEqual(dominio.texto_tiempo_de_venta(0.99), "1 día")
        self.assertEqual(dominio.texto_tiempo_de_venta(1), "1 día")
        self.assertEqual(dominio.texto_tiempo_de_venta(2.54), "2,5 días")
        self.assertEqual(dominio.texto_tiempo_de_venta(None, 0), "Sin compras")
        self.assertEqual(dominio.texto_tiempo_de_venta(None, 2), "Sin vender entera")


class _ConArticulos(BaseConBaseTemporal):
    """Un Admin, artículos con stock y ventas de hoy (que se pueden mover de día)."""

    def setUp(self):
        super().setUp()
        self.usuario_id = usuarios_repo.crear_usuario("Admin", "1234", dominio.ROL_ADMIN)
        self.hoy = turnos.dia_en_que_empezo_el_turno(datetime.now())

    def _articulo(self, codigo, nombre, stock=0, rubro=None):
        rubro_id = articulos_repo.crear_rubro(rubro) if rubro else None
        articulos_repo.crear_articulo(codigo, nombre, None, rubro_id, 100.0, 50.0, 0)
        if stock:
            compras_repo.registrar_compra(
                self.usuario_id, [{"codigo": codigo, "cantidad": stock, "costo_unitario": 50.0}])

    def _vender(self, codigo, cantidad, fecha=None):
        venta_id = ventas_repo.confirmar_venta(
            self.usuario_id,
            [{"codigo": codigo, "descripcion": codigo, "cantidad": cantidad, "precio_unitario": 100.0}],
            [{"metodo": dominio.PAGO_EFECTIVO, "monto": cantidad * 100.0}],
        )
        if fecha is not None:
            with conexion_db() as conexion:
                conexion.execute("UPDATE ventas SET fecha = ? WHERE id = ?", (fecha.isoformat(), venta_id))
        return venta_id

    def _comprar(self, codigo, cantidad, fecha):
        """Una compra pasada a `fecha`. Se llaman en orden de fecha, así el stock que
        guarda cada compra (el de ese momento) es el que había ese día."""
        compra_id = compras_repo.registrar_compra(
            self.usuario_id, [{"codigo": codigo, "cantidad": cantidad, "costo_unitario": 50.0}])
        with conexion_db() as conexion:
            conexion.execute("UPDATE compras SET fecha = ? WHERE id = ?", (fecha.isoformat(), compra_id))

    def _ultimos(self, dias):
        return rotacion_repo.ranking_de_rotacion((self.hoy - timedelta(days=dias - 1)).isoformat(),
                                                 self.hoy.isoformat())


class TestRankingDeRotacion(_ConArticulos):
    def test_ordena_del_que_mas_se_vende_y_deja_los_quietos_al_final(self):
        self._articulo("1", "Alfajor", stock=40, rubro="Golosinas")
        self._articulo("2", "Coca 500", stock=50)
        self._articulo("3", "Encendedor", stock=10)
        self._articulo("5", "álbum de figuritas", stock=3)
        self._vender("1", 6)
        self._vender("2", 12)

        ranking = self._ultimos(30)
        self.assertEqual([r["descripcion"] for r in ranking], ["Coca 500", "Alfajor", "álbum de figuritas", "Encendedor"])
        self.assertEqual([r["puesto"] for r in ranking], [1, 2, None, None])
        coca, alfajor, album, _ = ranking
        self.assertEqual((coca["vendidas"], coca["stock"], coca["por_dia"], coca["alcanza"]), (12, 38, 0.4, 95))
        self.assertEqual((alfajor["rubro"], coca["rubro"]), ("Golosinas", ""))
        # Quieta: no se vendió, no tiene "por día" ni se acaba.
        self.assertEqual((album["vendidas"], album["por_dia"], album["alcanza"]), (0, 0.0, None))

    def test_el_periodo_cambia_el_ritmo(self):
        self._articulo("1", "Alfajor", stock=100)
        self._vender("1", 7)
        self._vender("1", 21, fecha=datetime.combine(self.hoy - timedelta(days=60), datetime.min.time()).replace(hour=12))

        ultima_semana = self._ultimos(7)[0]
        self.assertEqual((ultima_semana["vendidas"], ultima_semana["por_dia"]), (7, 1.0))
        ultimos_90 = self._ultimos(90)[0]
        self.assertEqual((ultimos_90["vendidas"], ultimos_90["por_dia"]), (28, 0.31))
        # Quedan 72: a 1 por día alcanzan 72 días; a 28 en 90 días, 231.
        self.assertEqual((ultima_semana["alcanza"], ultimos_90["alcanza"]), (72, 231))

    def test_no_cuenta_las_anuladas(self):
        self._articulo("1", "Alfajor", stock=10)
        venta_id = self._vender("1", 4)
        ventas_repo.anular_venta(venta_id, self.usuario_id, "Se cobró de más")

        alfajor = self._ultimos(30)[0]
        # La anulada devolvió su stock y no cuenta como vendida.
        self.assertEqual((alfajor["vendidas"], alfajor["stock"], alfajor["puesto"]), (0, 10, None))

    def test_deja_afuera_las_impresiones_y_las_fotocopias(self):
        self._articulo(dominio.CODIGO_ARTICULO_IMPRESIONES, "IMPRESIONES", stock=500)
        self._articulo(dominio.CODIGO_ARTICULO_FOTOCOPIAS, "FOTOCOPIAS", stock=0)
        self._articulo("1", "Alfajor", stock=10)
        self._vender(dominio.CODIGO_ARTICULO_IMPRESIONES, 80)
        self._vender(dominio.CODIGO_ARTICULO_FOTOCOPIAS, 30)

        self.assertEqual([r["codigo"] for r in self._ultimos(30)], ["1"])

    def test_cuenta_los_dias_como_el_local(self):
        self._articulo("1", "Alfajor", stock=10)
        dia = datetime(2026, 1, 10)
        # La madrugada del 11 es la Noche del 10: entra. La del 10 es la Noche del 9: no.
        self._vender("1", 2, fecha=dia + timedelta(days=1, hours=5, minutes=30))
        self._vender("1", 5, fecha=dia + timedelta(hours=5, minutes=59))

        alfajor = rotacion_repo.ranking_de_rotacion("2026-01-10", "2026-01-10")[0]
        self.assertEqual(alfajor["vendidas"], 2)

    def test_las_fechas_al_reves_avisan(self):
        with self.assertRaises(ValueError):
            rotacion_repo.ranking_de_rotacion("2026-01-10", "2026-01-09")


class TestRankingPorCompras(_ConArticulos):
    """POR COMPRA (la idea del dueño): desde que entra una compra hasta que se vende
    su última unidad."""

    INICIO = datetime(2026, 9, 1, 8, 0)
    AHORA = datetime(2026, 9, 20, 12, 0)

    def _en(self, dias, horas=0):
        return self.INICIO + timedelta(days=dias, hours=horas)

    def _por_codigo(self):
        return {r["codigo"]: r for r in rotacion_repo.ranking_por_compras(self.AHORA)}

    def test_ordena_del_que_mas_rapido_vende_su_compra(self):
        for codigo, nombre in (("1", "Alfajor"), ("2", "Coca 500"), ("3", "Encendedor"), ("5", "Chicle")):
            self._articulo(codigo, nombre)
        self._comprar("1", 10, self._en(0))
        self._comprar("2", 10, self._en(0))
        self._comprar("3", 5, self._en(0))
        self._vender("2", 10, self._en(0, 12))
        self._vender("1", 4, self._en(1))
        self._vender("1", 6, self._en(2, 12))
        self._vender("3", 2, self._en(3))

        ranking = rotacion_repo.ranking_por_compras(self.AHORA)
        self.assertEqual([r["descripcion"] for r in ranking], ["Coca 500", "Alfajor", "Chicle", "Encendedor"])
        self.assertEqual([r["puesto"] for r in ranking], [1, 2, None, None])
        coca, alfajor, chicle, encendedor = ranking
        self.assertEqual((coca["dias"], alfajor["dias"]), (0.5, 2.5))
        self.assertEqual((coca["ultima_quedan"], coca["compras_medidas"]), (0, 1))
        # Nunca se compró, o se compró y todavía queda: sin medir, al final.
        self.assertEqual((chicle["compras"], chicle["dias"], chicle["ultima_fecha"]), (0, None, None))
        self.assertEqual((encendedor["compras"], encendedor["dias"]), (1, None))
        self.assertEqual((encendedor["ultima_cantidad"], encendedor["ultima_quedan"]), (5, 3))
        # Del 1/9 a las 8:00 al 20/9 a las 12:00.
        self.assertEqual(encendedor["ultima_hace"], 19.17)

    def test_lo_viejo_sale_primero_y_promedia_las_ultimas_tres(self):
        self._articulo("1", "Alfajor")
        self._comprar("1", 5, self._en(0))         # A
        self._vender("1", 2, self._en(1))
        self._comprar("1", 10, self._en(2))        # B: quedaban 3 de A adelante
        self._vender("1", 3, self._en(4))          # se termina A: 4 días
        self._vender("1", 10, self._en(5))         # se termina B: 3 días
        self._comprar("1", 4, self._en(6))         # C
        self._vender("1", 4, self._en(6, 12))      # 12 horas
        self._comprar("1", 6, self._en(7))         # D
        self._vender("1", 6, self._en(8))          # 1 día

        alfajor = self._por_codigo()["1"]
        # Las últimas 3 (B, C y D): (3 + 0,5 + 1) / 3. A (4 días) ya no entra.
        self.assertEqual((alfajor["dias"], alfajor["compras_medidas"], alfajor["compras"]), (1.5, 3, 4))

    def test_lo_vendido_sin_stock_lo_tapa_la_compra_siguiente(self):
        self._articulo("1", "Alfajor")
        self._comprar("1", 2, self._en(0))
        self._vender("1", 5, self._en(1))          # se termina la primera (1 día) y queda en -3
        self._comprar("1", 3, self._en(2))         # tapa lo que se debía: vendida en el momento
        self._comprar("1", 5, self._en(3))
        self._vender("1", 5, self._en(4))          # 1 día

        alfajor = self._por_codigo()["1"]
        self.assertEqual((alfajor["dias"], alfajor["compras_medidas"]), (0.67, 3))

    def test_las_anuladas_no_cuentan(self):
        self._articulo("1", "Alfajor")
        self._comprar("1", 5, self._en(0))
        venta_id = self._vender("1", 5, self._en(1))
        ventas_repo.anular_venta(venta_id, self.usuario_id, "Se cobró de más")
        self.assertIsNone(self._por_codigo()["1"]["dias"])

        self._vender("1", 5, self._en(2))
        self.assertEqual(self._por_codigo()["1"]["dias"], 2.0)

    def test_deja_afuera_las_impresiones_y_las_fotocopias(self):
        for codigo in dominio.CODIGOS_QUE_NO_SON_MERCADERIA:
            self._articulo(codigo, f"HOJAS {codigo}")
            self._comprar(codigo, 500, self._en(0))
        por_codigo = self._por_codigo()
        for codigo in dominio.CODIGOS_QUE_NO_SON_MERCADERIA:
            self.assertNotIn(codigo, por_codigo)


class TestLotesDeCompra(unittest.TestCase):
    """La historia de las compras de un artículo, con lo que no pasa por una venta."""

    def test_una_correccion_de_stock_que_termina_la_compra_no_la_mide(self):
        lotes = rotacion_repo._lotes_de_compra([
            ("2026-09-01T08:00:00", rotacion_repo._COMPRA, 10, 0),
            ("2026-09-02T08:00:00", rotacion_repo._VENTA, 7, None),
            # ORDENAR Stock: faltaban 3 en el estante. No se sabe cuánto tardaban en venderse.
            ("2026-09-03T08:00:00", rotacion_repo._AJUSTE, -3, None),
        ])
        self.assertEqual((lotes[0]["quedan"], lotes[0]["vendida_en"]), (0, None))

    def test_lo_que_suma_una_correccion_va_detras_de_la_compra(self):
        lotes = rotacion_repo._lotes_de_compra([
            ("2026-09-01T08:00:00", rotacion_repo._COMPRA, 4, 0),
            ("2026-09-02T08:00:00", rotacion_repo._AJUSTE, 5, None),
            ("2026-09-03T08:00:00", rotacion_repo._VENTA, 4, None),
        ])
        self.assertEqual(lotes[0]["vendida_en"], "2026-09-03T08:00:00")

    def test_si_la_cuenta_no_cuadra_manda_el_stock_que_guardo_la_compra(self):
        # La compra dice que había 4 antes (por ejemplo, una venta vieja que se anuló
        # después): esos 4 salen primero.
        lotes = rotacion_repo._lotes_de_compra([
            ("2026-09-01T08:00:00", rotacion_repo._COMPRA, 6, 4),
            ("2026-09-02T08:00:00", rotacion_repo._VENTA, 4, None),
            ("2026-09-03T08:00:00", rotacion_repo._VENTA, 6, None),
        ])
        self.assertEqual(lotes[0]["vendida_en"], "2026-09-03T08:00:00")

    def test_en_el_mismo_segundo_la_compra_va_antes_que_la_venta(self):
        lotes = rotacion_repo._lotes_de_compra([
            ("2026-09-01T08:00:00", rotacion_repo._VENTA, 2, None),
            ("2026-09-01T08:00:00", rotacion_repo._COMPRA, 2, 0),
        ])
        self.assertEqual((lotes[0]["quedan"], lotes[0]["vendida_en"]), (0, "2026-09-01T08:00:00"))


class TestElAccesoDelInicio(_ConArticulos):
    def _inicio(self, usuario_id):
        ventana = MainWindow(usuarios_repo.obtener_usuario(usuario_id), lambda: None)
        self.addCleanup(ventana.deleteLater)
        self.addCleanup(ventana.close)
        accesos = {b.accessibleName(): b for b in ventana.findChildren(QPushButton)
                   if b.objectName() == "accesoInicio"}
        return ventana, accesos["RANKING DE ROTACIÓN"]

    def test_va_debajo_de_tareas_del_turno(self):
        ventana, acceso = self._inicio(self.usuario_id)
        ventana.show()
        _app.processEvents()
        self.assertGreater(acceso.y(), ventana.acceso_tareas.y())
        self.assertEqual(acceso.x(), ventana.acceso_tareas.x())

    def test_el_admin_lo_abre(self):
        ventana, acceso = self._inicio(self.usuario_id)
        with mock.patch("ui.main_window.VentanaRankingRotacion") as abierta:
            acceso.click()
        abierta.assert_called_once_with(ventana)
        abierta.return_value.exec.assert_called_once()

    def test_una_empleada_lo_abre_solo_con_el_permiso_de_reportes(self):
        sin_permiso = usuarios_repo.crear_usuario("Carla", "1234", dominio.ROL_EMPLEADA)
        con_permiso = usuarios_repo.crear_usuario("Sofía", "1234", dominio.ROL_EMPLEADA, {"permiso_reportes": True})

        _ventana, acceso = self._inicio(sin_permiso)
        # Desde el 2026-11-04 dice "Acceso Restringido" (ui.utils.avisar_acceso_restringido).
        # Sin tapar ese cartel, la prueba se quedaba esperando que alguien lo cerrara.
        with mock.patch("ui.main_window.VentanaRankingRotacion") as abierta, \
                mock.patch("ui.utils.mostrar_aviso") as aviso:
            acceso.click()
        abierta.assert_not_called()
        aviso.assert_called_once()
        self.assertIn("Acceso Restringido", aviso.call_args.args[2])

        _ventana, acceso = self._inicio(con_permiso)
        with mock.patch("ui.main_window.VentanaRankingRotacion") as abierta:
            acceso.click()
        abierta.return_value.exec.assert_called_once()


class TestLaVentana(_ConArticulos):
    def _ventana(self):
        ventana = VentanaRankingRotacion()
        self.addCleanup(ventana.deleteLater)
        return ventana

    def test_abre_por_compra_con_la_que_mas_rapido_se_vende_arriba(self):
        self._articulo("1", "Alfajor")
        self._articulo("2", "Coca 500")
        hace_diez = datetime.combine(self.hoy - timedelta(days=10), datetime.min.time())
        self._comprar("1", 4, hace_diez.replace(hour=8))
        self._comprar("2", 4, hace_diez.replace(hour=8))
        self._vender("2", 4, hace_diez.replace(hour=20))                   # 12 horas
        self._vender("1", 4, hace_diez.replace(hour=8) + timedelta(days=3))  # 3 días

        ventana = self._ventana()
        self.assertEqual(ventana.pestañas.currentIndex(), PESTAÑA_COMPRA)
        self.assertIn("del más rápido al más lento", ventana.cabecera.detalle.text())
        self.assertEqual(ventana.tabla_compras.item(0, 1).text(), "Coca 500")
        self.assertEqual(ventana.tabla_compras.item(0, COLUMNA_TARDA).text(), "12 horas")
        self.assertEqual(ventana.tabla_compras.item(1, COLUMNA_TARDA).text(), "3 días")
        self.assertEqual(ventana.tabla_compras.item(1, 6).text(), "Se vendió toda")
        self.assertEqual(ventana.indicador_medidos.valor.text(), "2")
        # Arriba, solo los números de la pestaña a la vista.
        self.assertFalse(ventana.indicador_medidos.isHidden())
        self.assertTrue(ventana.indicador_articulos.isHidden())
        html = ventana.html_para_imprimir(datetime(2026, 11, 4, 10, 0))
        self.assertIn("Por compra", html)
        self.assertIn("12 horas", html)

        ventana.pestañas.setCurrentIndex(PESTAÑA_PERIODO)
        self.assertIn("Últimos 30 días", ventana.cabecera.detalle.text())
        self.assertTrue(ventana.indicador_medidos.isHidden())
        self.assertFalse(ventana.indicador_articulos.isHidden())

    def test_por_periodo_muestra_los_ultimos_30_dias_y_cambia_de_periodo(self):
        self._articulo("1", "Alfajor", stock=33)
        self._articulo("2", "Encendedor", stock=10)
        self._vender("1", 2)
        self._vender("1", 30, fecha=datetime.combine(self.hoy - timedelta(days=60), datetime.min.time()).replace(hour=12))

        ventana = self._ventana()
        ventana.pestañas.setCurrentIndex(PESTAÑA_PERIODO)
        self.assertEqual(ventana.periodos.elegido(), 30)
        self.assertIn("Últimos 30 días", ventana.cabecera.detalle.text())
        self.assertEqual(ventana.tabla_periodo.rowCount(), 2)
        self.assertEqual(ventana.tabla_periodo.item(0, 1).text(), "Alfajor")
        # Quedó 1 y se venden 2 en 30 días: alcanza para 15 días.
        self.assertEqual(ventana.tabla_periodo.item(0, COLUMNA_ALCANZA).text(), "15 días")
        self.assertEqual(ventana.tabla_periodo.item(1, COLUMNA_ALCANZA).text(), "Sin ventas")
        self.assertEqual(ventana.indicador_quietos.valor.text(), "1")
        self.assertEqual(ventana.indicador_pronto.valor.text(), "0")

        # En 90 días entran las 30 de hace dos meses: 32 en 90 días con 1 en stock
        # alcanza para 2 días, y se pinta de rojo.
        noventa = next(p for p in ventana.periodos.pastillas if "90" in p.text())
        noventa.click()
        self.assertIn("Últimos 90 días", ventana.cabecera.detalle.text())
        self.assertEqual(ventana.tabla_periodo.item(0, COLUMNA_ALCANZA).text(), "2 días")
        self.assertEqual(ventana.tabla_periodo.item(0, COLUMNA_ALCANZA).foreground().color(), QColor(Qt.red))
        self.assertEqual(ventana.indicador_pronto.valor.text(), "1")

    def test_la_hoja_impresa_es_la_de_la_pestana_a_la_vista(self):
        self._articulo("1", "Alfajor", stock=3)
        self._vender("1", 2)
        ventana = self._ventana()
        ventana.pestañas.setCurrentIndex(PESTAÑA_PERIODO)
        html = ventana.html_para_imprimir(datetime(2026, 11, 4, 10, 0))
        self.assertIn("Ranking de Rotación · Por período", html)
        self.assertIn("Alfajor", html)
        self.assertIn("15 días", html)

    def test_sin_articulos_no_hay_nada_para_imprimir(self):
        ventana = self._ventana()
        self.assertEqual(ventana.tabla_compras.rowCount(), 0)
        self.assertFalse(ventana.boton_imprimir.isEnabled())
        ventana.pestañas.setCurrentIndex(PESTAÑA_PERIODO)
        self.assertEqual(ventana.tabla_periodo.rowCount(), 0)
        self.assertFalse(ventana.boton_imprimir.isEnabled())


if __name__ == "__main__":
    unittest.main()
