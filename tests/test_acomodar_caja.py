"""
tests/test_acomodar_caja.py
=============================
ACOMODAR CAJA (pedido del dueño, 2026-11-04): al cambiar del programa anterior a
FRKiosko a mitad de turno, el Admin carga lo que el otro programa ya había
cobrado (efectivo y digital) y la caja tiene que dar bien. Entra como una venta
del artículo dominio.CODIGO_ARTICULO_ACOMODAR_CAJA, escondido de las listas
(repositories/acomodar_caja_repo.py, ui/acomodar_caja_window.py).

Se ejecutan con:

    python -m unittest discover tests
"""

import os
from datetime import datetime
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QPushButton  # noqa: E402

import dominio  # noqa: E402
from database import conexion_db  # noqa: E402
from repositories import (  # noqa: E402
    acomodar_caja_repo, articulos_repo, envio_pwa_repo, relevo_repo, turnos_repo, usuarios_repo, ventas_repo,
)
from repositories.config_repo import obtener_fondo_cambio  # noqa: E402
from ui.acomodar_caja_window import DialogoAcomodarCaja  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from base import BaseConBaseTemporal  # noqa: E402

_app = QApplication.instance() or QApplication([])

EF = dominio.PAGO_EFECTIVO
DIG = dominio.PAGO_DIGITAL
CODIGO = dominio.CODIGO_ARTICULO_ACOMODAR_CAJA


class _ConCaja(BaseConBaseTemporal):
    def setUp(self):
        super().setUp()
        self.admin_id = usuarios_repo.crear_usuario("Sergio", "1234", dominio.ROL_ADMIN)
        self.empleada_id = usuarios_repo.crear_usuario("Lucia", "1234", dominio.ROL_EMPLEADA)
        articulos_repo.crear_articulo("COD9", "ALFAJOR", None, None, 1000.0, 500.0, 0)


class TestAcomodarCaja(_ConCaja):
    def test_lo_del_programa_anterior_suma_en_la_caja_abierta_de_la_empleada(self):
        caja = relevo_repo.abrir_caja(self.empleada_id, obtener_fondo_cambio())
        ventas_repo.confirmar_venta(
            self.empleada_id,
            [{"codigo": "COD9", "descripcion": "ALFAJOR", "cantidad": 1, "precio_unitario": 1000.0}],
            [{"metodo": EF, "monto": 1000.0}],
        )

        venta_id = acomodar_caja_repo.acomodar_caja(self.admin_id, 85_000, 42_500)

        venta, detalle, pagos = ventas_repo.buscar_venta(venta_id)
        self.assertEqual(venta["total"], 127_500)
        # A nombre de la responsable de la caja, como todo lo que cobra el Admin.
        self.assertEqual(venta["usuario_id"], self.empleada_id)
        self.assertEqual([(d["articulo_codigo"], d["cantidad"], d["subtotal"]) for d in detalle],
                         [(CODIGO, 1, 127_500)])
        self.assertEqual(sorted((p["metodo"], p["monto"]) for p in pagos), [(DIG, 42_500), (EF, 85_000)])
        with conexion_db() as conexion:
            fila = conexion.execute("SELECT caja_id FROM ventas_caja WHERE venta_id = ?", (venta_id,)).fetchone()
        self.assertEqual(fila["caja_id"], caja["caja_numero"])

        resumen = turnos_repo.resumen_turno_actual()
        self.assertEqual(resumen["monto_a_retirar"], 86_000)
        self.assertEqual(resumen["ventas_total"], 128_500)

    def test_con_un_solo_medio_graba_un_solo_pago(self):
        relevo_repo.abrir_caja(self.empleada_id, obtener_fondo_cambio())
        venta_id = acomodar_caja_repo.acomodar_caja(self.admin_id, 0, 30_000)
        _, _, pagos = ventas_repo.buscar_venta(venta_id)
        self.assertEqual([(p["metodo"], p["monto"]) for p in pagos], [(DIG, 30_000)])
        self.assertEqual(turnos_repo.resumen_turno_actual()["monto_a_retirar"], 0)

    def test_solo_el_admin(self):
        relevo_repo.abrir_caja(self.empleada_id, obtener_fondo_cambio())
        with self.assertRaises(PermissionError):
            acomodar_caja_repo.acomodar_caja(self.empleada_id, 1000, 0)
        self.assertEqual(ventas_repo.listar_ventas_recientes(), [])

    def test_rechaza_cero_y_negativos_sin_grabar_nada(self):
        for efectivo, digital in ((0, 0), (-100, 500), (500, -100), ("mucho", 0)):
            with self.assertRaises(ValueError, msg=(efectivo, digital)):
                acomodar_caja_repo.acomodar_caja(self.admin_id, efectivo, digital)
        self.assertEqual(ventas_repo.listar_ventas_recientes(), [])

    def test_el_articulo_no_sale_en_las_listas_ni_en_vender(self):
        acomodar_caja_repo.acomodar_caja(self.admin_id, 1000, 0)
        acomodar_caja_repo.acomodar_caja(self.admin_id, 2000, 0)  # la segunda no lo vuelve a crear

        codigos = [a["codigo"] for a in articulos_repo.listar_articulos()]
        self.assertEqual(codigos, ["COD9"])
        self.assertEqual(articulos_repo.listar_articulos("ACOMODAR"), [])
        self.assertEqual(articulos_repo.buscar_por_descripcion("ACOMODAR"), [])
        self.assertIsNone(articulos_repo.buscar_por_codigo(CODIGO))
        self.assertEqual(dominio.numeros_de_los_articulos(articulos_repo.listar_articulos())["cantidad"], 1)
        with conexion_db() as conexion:
            stock = conexion.execute("SELECT stock FROM articulos WHERE codigo = ?", (CODIGO,)).fetchone()
        self.assertEqual(stock["stock"], 0)

    def test_si_se_anula_sale_de_la_caja(self):
        relevo_repo.abrir_caja(self.empleada_id, obtener_fondo_cambio())
        venta_id = acomodar_caja_repo.acomodar_caja(self.admin_id, 5000, 0)
        ventas_repo.anular_venta(venta_id, self.admin_id, "me equivoqué de monto")
        self.assertEqual(turnos_repo.resumen_turno_actual()["monto_a_retirar"], 0)


class TestPrimerDiaConElPrograma(_ConCaja):
    """El caso del dueño (2026-11-04): pasa del programa viejo a mitad de la Mañana.
    Carga con ORDENAR $ lo cobrado hasta ahí, la empleada de la Mañana abre su caja
    a las 13:20, y a las 14:05, cuando llega la de la Tarde, hace el Cierre de Turno.
    Ese cierre (y el que va a la app de gastos) es de la MAÑANA, con lo de ORDENAR $
    y lo que vendió. Sin ese arreglo, la caja de las 13:20 salía como Tarde (la
    tolerancia de una hora de quien llega temprano)."""

    def _a_las(self, hora, minuto=0):
        return datetime(2026, 11, 2, hora, minuto)

    def _con_reloj(self, momento, funcion, *argumentos):
        with mock.patch("repositories.ventas_repo.datetime") as reloj:
            reloj.now.return_value = momento
            return funcion(*argumentos)

    def test_lo_de_ordenar_y_lo_vendido_van_en_el_cierre_de_la_manana(self):
        fondo = obtener_fondo_cambio()
        self._con_reloj(self._a_las(13, 15), acomodar_caja_repo.acomodar_caja, self.admin_id, 58_550, 87_500)

        situacion = relevo_repo.situacion_al_entrar(self.empleada_id, self._a_las(13, 20))
        self.assertEqual(situacion["turno_label"], "Mañana")
        self.assertEqual(situacion["esperado"], fondo + 58_550)
        caja = relevo_repo.abrir_caja(self.empleada_id, fondo + 58_550, self._a_las(13, 20))
        self.assertEqual(caja["turno_label"], "Mañana")
        self.assertEqual(caja["diferencia"], 0)

        self._con_reloj(self._a_las(13, 40), ventas_repo.confirmar_venta, self.empleada_id,
                        [{"codigo": "COD9", "descripcion": "ALFAJOR", "cantidad": 1, "precio_unitario": 1000.0}],
                        [{"metodo": EF, "monto": 1000.0}])
        cierre = turnos_repo.cerrar_turno(self.empleada_id, ahora_dt=self._a_las(14, 5))

        self.assertEqual(cierre["turno_label"], "Mañana")
        with conexion_db() as conexion:
            datos = envio_pwa_repo.datos_del_cierre(conexion, cierre["id"])
        self.assertEqual((datos["turno"], datos["registradoPor"]), ("mañana", "Lucia"))
        self.assertEqual((datos["efectivo"], datos["digital"], datos["importe"]), (59_550, 87_500, 147_050))

        # La de la Tarde, que llega después del cierre, abre la Tarde como siempre.
        gaby_id = usuarios_repo.crear_usuario("Gaby", "1234", dominio.ROL_EMPLEADA)
        self.assertEqual(relevo_repo.abrir_caja(gaby_id, fondo, self._a_las(14, 10))["turno_label"], "Tarde")

    def test_sin_nada_cargado_la_primera_caja_sigue_con_la_tolerancia(self):
        # Sin ORDENAR $ antes, nada cambia: la que abre a las 13:20 es la Tarde que
        # llegó temprano, y la de las 05:55 abre la Mañana.
        self.assertEqual(relevo_repo.abrir_caja(self.empleada_id, obtener_fondo_cambio(),
                                                self._a_las(13, 20))["turno_label"], "Tarde")

    def test_la_de_las_cinco_y_cincuenta_y_cinco_abre_la_manana(self):
        self.assertEqual(relevo_repo.abrir_caja(self.empleada_id, obtener_fondo_cambio(),
                                                self._a_las(5, 55))["turno_label"], "Mañana")


class TestBotonAcomodarCaja(_ConCaja):
    def _boton(self, usuario_id):
        ventana = MainWindow(usuarios_repo.obtener_usuario(usuario_id), lambda: None)
        self.addCleanup(ventana.deleteLater)
        barra = ventana.findChild(QFrame, "encabezadoInicio")
        textos = [b.text() for b in barra.findChildren(QPushButton)]
        # A la derecha de Cambiar Pass, el último.
        self.assertEqual(textos[-2:], ["🔑  CAMBIAR PASS", "🧮  ORDENAR $"])
        return next(b for b in barra.findChildren(QPushButton) if b.text() == "🧮  ORDENAR $")

    def test_el_admin_lo_abre(self):
        boton = self._boton(self.admin_id)
        with mock.patch("ui.main_window.DialogoAcomodarCaja") as dialogo:
            boton.click()
        self.assertTrue(dialogo.called)

    def test_la_empleada_lo_ve_pero_dice_acceso_restringido(self):
        boton = self._boton(self.empleada_id)
        with mock.patch("ui.main_window.DialogoAcomodarCaja") as dialogo, \
                mock.patch("ui.piezas_ventana.avisar_acceso_restringido") as aviso:
            boton.click()
        self.assertFalse(dialogo.called)
        self.assertTrue(aviso.called)

    def test_la_ventana_graba_lo_escrito_al_confirmar(self):
        relevo_repo.abrir_caja(self.empleada_id, obtener_fondo_cambio())
        dialogo = DialogoAcomodarCaja(usuarios_repo.obtener_usuario(self.admin_id))
        self.addCleanup(dialogo.deleteLater)
        self.assertIn("Lucia", dialogo.etiqueta_destino.text())
        dialogo.campo_efectivo.setValue(10_000)
        dialogo.campo_digital.setValue(2_500)
        self.assertIn("$ 12.500", dialogo.etiqueta_total.text())
        with mock.patch("ui.acomodar_caja_window.confirmar", return_value=True), \
                mock.patch("ui.acomodar_caja_window.mostrar_info"):
            dialogo._guardar()
        self.assertEqual(turnos_repo.resumen_turno_actual()["ventas_total"], 12_500)


if __name__ == "__main__":
    import unittest
    unittest.main()
