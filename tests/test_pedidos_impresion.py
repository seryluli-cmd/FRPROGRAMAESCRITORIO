"""
tests/test_pedidos_impresion.py
================================
GESTIÓN IMPRESIONES (pedido del dueño, 2026-11-02): pedidos grandes de
impresiones que se dejan con seña o pagados enteros y se retiran después.

- La seña entra en la caja de quien toma el pedido; lo que falta, en la de quien
  lo entrega. Las dos, como Impresiones en Caja y en el Cierre de Turno.
- Las hojas se cuentan una sola vez, al retirar.
- Sin seña no se toma; pagarlo entero de entrada sí.
- Si no viene nunca, la seña la pierde (solo el Administrador lo marca).
- Anular un pedido (Administrador, con motivo) anula sus cobros; esos cobros no
  se anulan sueltos desde Consulta de Ventas.
- Teléfono opcional y botón para avisarle por WhatsApp que está listo.

Se ejecutan con:

    python -m unittest discover tests
"""

import os
import unittest
from datetime import datetime
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

import dominio  # noqa: E402
from database import conexion_db  # noqa: E402
from repositories import (  # noqa: E402
    articulos_repo, pedidos_impresion_repo, relevo_repo, reportes_repo, turnos_repo, usuarios_repo, ventas_repo,
)
from repositories.config_repo import obtener_fondo_cambio  # noqa: E402
from turnos import dia_en_que_empezo_el_turno  # noqa: E402
from ui.gestion_impresiones_window import (  # noqa: E402
    DialogoEntregarPedido, DialogoNuevoPedido, VentanaGestionImpresiones,
)
from base import BaseConBaseTemporal  # noqa: E402

_app = QApplication.instance() or QApplication([])

EF = dominio.PAGO_EFECTIVO
DIG = dominio.PAGO_DIGITAL
PRECIO = 150.0


def _pago(metodo, monto):
    return {"metodo": metodo, "monto": monto}


class _ConPedidos(BaseConBaseTemporal):
    def setUp(self):
        super().setUp()
        self.lucia_id = usuarios_repo.crear_usuario("Lucia", "1234", dominio.ROL_EMPLEADA)
        self.gaby_id = usuarios_repo.crear_usuario("Gaby", "1234", dominio.ROL_EMPLEADA)
        self.admin_id = usuarios_repo.crear_usuario("Sergio", "1234", dominio.ROL_ADMIN)
        articulos_repo.crear_articulo(dominio.CODIGO_ARTICULO_IMPRESIONES, "IMPRESIONES", None, None, PRECIO, 0.0, 0)

    def _tomar(self, sena=5000.0, hojas=100, quien=None, telefono="", pagos=None):
        return pedidos_impresion_repo.tomar_pedido(
            quien or self.lucia_id, "Martina López", telefono, hojas, PRECIO, sena,
            pagos if pagos is not None else [_pago(EF, sena)],
        )

    def _pedido(self, pedido_id):
        return next(p for p in pedidos_impresion_repo.listar_pedidos() if p["id"] == pedido_id)

    def _caja_de_la_venta(self, venta_id):
        with conexion_db() as conexion:
            fila = conexion.execute("SELECT caja_id FROM ventas_caja WHERE venta_id = ?", (venta_id,)).fetchone()
        return fila["caja_id"] if fila else None


class TestTomarPedido(_ConPedidos):
    def test_graba_el_pedido_con_quien_lo_tomo_y_la_cuenta(self):
        pedido_id = self._tomar(telefono="11 5555-1234")

        pedido = self._pedido(pedido_id)
        self.assertEqual((pedido["nombre"], pedido["telefono"], pedido["hojas"]), ("Martina López", "1155551234", 100))
        self.assertEqual((pedido["precio_hoja"], pedido["total"], pedido["sena"]), (150.0, 15000.0, 5000.0))
        self.assertEqual(pedido["estado"], dominio.PEDIDO_PENDIENTE)
        self.assertEqual(pedido["tomado_por_nombre"], "Lucia")

    def test_la_sena_es_una_venta_de_impresiones_en_la_caja_de_quien_lo_toma(self):
        caja = relevo_repo.abrir_caja(self.lucia_id, obtener_fondo_cambio())

        pedido_id = self._tomar(pagos=[_pago(EF, 3000.0), _pago(DIG, 2000.0)])

        venta_id = self._pedido(pedido_id)["venta_sena_id"]
        venta, detalle, pagos = ventas_repo.buscar_venta(venta_id)
        self.assertEqual(venta["total"], 5000.0)
        self.assertEqual([(d["articulo_codigo"], d["descripcion"], d["cantidad"], d["subtotal"]) for d in detalle],
                         [(dominio.CODIGO_ARTICULO_IMPRESIONES, dominio.DESCRIPCION_SENA_IMPRESIONES, 1, 5000.0)])
        self.assertEqual(sorted((p["metodo"], p["monto"]) for p in pagos), [(DIG, 2000.0), (EF, 3000.0)])
        self.assertEqual(self._caja_de_la_venta(venta_id), caja["caja_numero"])
        resumen = turnos_repo.resumen_turno_actual()
        self.assertEqual((resumen["impresiones_efectivo"], resumen["impresiones_digital"]), (3000.0, 2000.0))

    def test_sin_sena_no_se_toma_y_no_queda_nada(self):
        with self.assertRaisesRegex(ValueError, "Sin seña"):
            self._tomar(sena=0.0, pagos=[])
        self.assertEqual(pedidos_impresion_repo.listar_pedidos(), [])
        self.assertEqual(ventas_repo.listar_ventas_recientes(), [])

    def test_la_sena_no_puede_pasar_el_total_pero_puede_ser_el_total(self):
        with self.assertRaisesRegex(ValueError, "más que el total"):
            self._tomar(sena=15001.0)
        pedido_id = self._tomar(sena=15000.0)
        self.assertEqual(self._pedido(pedido_id)["sena"], 15000.0)

    def test_los_pagos_tienen_que_sumar_la_sena(self):
        with self.assertRaisesRegex(ValueError, "no coincide"):
            self._tomar(sena=5000.0, pagos=[_pago(EF, 4000.0)])
        self.assertEqual(pedidos_impresion_repo.listar_pedidos(), [])

    def test_sin_nombre_o_con_un_telefono_que_no_sirve_no_se_toma(self):
        with self.assertRaisesRegex(ValueError, "a nombre de quién"):
            pedidos_impresion_repo.tomar_pedido(self.lucia_id, "  ", "", 10, PRECIO, 500.0, [_pago(EF, 500.0)])
        with self.assertRaisesRegex(ValueError, "característica"):
            self._tomar(telefono="5555-1234")
        self.assertEqual(pedidos_impresion_repo.listar_pedidos(), [])

    def test_si_cambio_el_precio_mientras_tanto_no_graba(self):
        with conexion_db() as conexion:
            conexion.execute("UPDATE articulos SET precio_venta = 200 WHERE codigo = ?",
                             (dominio.CODIGO_ARTICULO_IMPRESIONES,))
        with self.assertRaisesRegex(ValueError, "cambió"):
            self._tomar()
        self.assertEqual(pedidos_impresion_repo.listar_pedidos(), [])


class TestEntregarPedido(_ConPedidos):
    def test_lo_que_falta_entra_en_la_caja_de_quien_lo_entrega(self):
        caja_lucia = relevo_repo.abrir_caja(self.lucia_id, obtener_fondo_cambio())
        pedido_id = self._tomar()
        turnos_repo.cerrar_turno(self.lucia_id)
        caja_gaby = relevo_repo.abrir_caja(self.gaby_id, obtener_fondo_cambio())

        venta_id = pedidos_impresion_repo.entregar_pedido(self.gaby_id, pedido_id, [_pago(DIG, 10000.0)])

        pedido = self._pedido(pedido_id)
        self.assertEqual(pedido["estado"], dominio.PEDIDO_RETIRADO)
        self.assertEqual((pedido["entregado_por_nombre"], pedido["venta_entrega_id"]), ("Gaby", venta_id))
        self.assertEqual(self._caja_de_la_venta(pedido["venta_sena_id"]), caja_lucia["caja_numero"])
        self.assertEqual(self._caja_de_la_venta(venta_id), caja_gaby["caja_numero"])
        self.assertEqual(ventas_repo.buscar_venta(venta_id)[0]["total"], 10000.0)
        self.assertEqual(turnos_repo.resumen_turno_actual()["impresiones_digital"], 10000.0)

    def test_las_hojas_se_cuentan_una_sola_vez_y_la_plata_suma_el_total(self):
        hoy = dia_en_que_empezo_el_turno(datetime.now()).isoformat()

        def ranking():
            return {fila["descripcion"]: (fila["cantidad"], fila["importe"])
                    for fila in reportes_repo.ranking_ventas(hoy, hoy)}

        pedido_id = self._tomar()
        self.assertEqual(ranking()[dominio.DESCRIPCION_SENA_IMPRESIONES], (1, 5000.0))

        pedidos_impresion_repo.entregar_pedido(self.gaby_id, pedido_id, [_pago(EF, 10000.0)])

        self.assertEqual(ranking()["IMPRESIONES"], (100, 15000.0))
        # Seña cobrada y descontada el mismo día: da 0 y $ 0 y no se muestra.
        self.assertNotIn(dominio.DESCRIPCION_SENA_IMPRESIONES, ranking())
        self.assertEqual(reportes_repo.resumen_por_origen(hoy, hoy)[0]["impresiones"], 15000.0)
        self.assertEqual(articulos_repo.buscar_por_codigo(dominio.CODIGO_ARTICULO_IMPRESIONES)["stock"], -100)

    def test_pagado_entero_se_entrega_sin_cobrar_nada(self):
        pedido_id = self._tomar(sena=15000.0)

        venta_id = pedidos_impresion_repo.entregar_pedido(self.gaby_id, pedido_id, [])

        venta, _detalle, pagos = ventas_repo.buscar_venta(venta_id)
        self.assertEqual((venta["total"], list(pagos)), (0.0, []))
        self.assertEqual(self._pedido(pedido_id)["estado"], dominio.PEDIDO_RETIRADO)

    def test_hay_que_cobrar_justo_lo_que_falta(self):
        pedido_id = self._tomar()
        with self.assertRaisesRegex(ValueError, "no coincide"):
            pedidos_impresion_repo.entregar_pedido(self.gaby_id, pedido_id, [_pago(EF, 15000.0)])
        self.assertEqual(self._pedido(pedido_id)["estado"], dominio.PEDIDO_PENDIENTE)

    def test_el_precio_que_vale_es_el_del_dia_que_se_tomo(self):
        pedido_id = self._tomar()
        with conexion_db() as conexion:
            conexion.execute("UPDATE articulos SET precio_venta = 300 WHERE codigo = ?",
                             (dominio.CODIGO_ARTICULO_IMPRESIONES,))
        venta_id = pedidos_impresion_repo.entregar_pedido(self.gaby_id, pedido_id, [_pago(EF, 10000.0)])
        self.assertEqual(ventas_repo.buscar_venta(venta_id)[0]["total"], 10000.0)

    def test_no_se_entrega_dos_veces(self):
        pedido_id = self._tomar(sena=15000.0)
        pedidos_impresion_repo.entregar_pedido(self.gaby_id, pedido_id, [])
        with self.assertRaisesRegex(ValueError, "RETIRADO"):
            pedidos_impresion_repo.entregar_pedido(self.gaby_id, pedido_id, [])


class TestSenaPerdidaYAnular(_ConPedidos):
    def test_la_sena_perdida_la_marca_solo_el_admin_y_la_plata_queda(self):
        pedido_id = self._tomar()
        with self.assertRaises(PermissionError):
            pedidos_impresion_repo.dar_por_perdida(self.lucia_id, pedido_id)

        pedidos_impresion_repo.dar_por_perdida(self.admin_id, pedido_id)

        pedido = self._pedido(pedido_id)
        self.assertEqual(pedido["estado"], dominio.PEDIDO_SENA_PERDIDA)
        self.assertEqual(ventas_repo.buscar_venta(pedido["venta_sena_id"])[0]["estado"], dominio.VENTA_CONFIRMADA)
        self.assertEqual(turnos_repo.resumen_turno_actual()["impresiones"], 5000.0)
        with self.assertRaisesRegex(ValueError, "SEÑA PERDIDA"):
            pedidos_impresion_repo.entregar_pedido(self.gaby_id, pedido_id, [_pago(EF, 10000.0)])

    def test_anular_un_pedido_anula_sus_cobros(self):
        pedido_id = self._tomar()
        venta_entrega = pedidos_impresion_repo.entregar_pedido(self.gaby_id, pedido_id, [_pago(EF, 10000.0)])
        with self.assertRaises(PermissionError):
            pedidos_impresion_repo.anular_pedido(self.lucia_id, pedido_id, "mal cargado")
        with self.assertRaisesRegex(ValueError, "motivo"):
            pedidos_impresion_repo.anular_pedido(self.admin_id, pedido_id, "  ")

        pedidos_impresion_repo.anular_pedido(self.admin_id, pedido_id, "mal cargado")

        pedido = self._pedido(pedido_id)
        self.assertEqual((pedido["estado"], pedido["motivo"]), (dominio.PEDIDO_ANULADO, "mal cargado"))
        for venta_id in (pedido["venta_sena_id"], venta_entrega):
            self.assertEqual(ventas_repo.buscar_venta(venta_id)[0]["estado"], dominio.VENTA_ANULADA)
        self.assertEqual(turnos_repo.resumen_turno_actual()["impresiones"], 0.0)
        self.assertEqual(articulos_repo.buscar_por_codigo(dominio.CODIGO_ARTICULO_IMPRESIONES)["stock"], 0)

    def test_sus_cobros_no_se_anulan_sueltos_desde_consulta_de_ventas(self):
        pedido_id = self._tomar()
        with self.assertRaisesRegex(ValueError, "Gestión Impresiones"):
            ventas_repo.anular_venta(self._pedido(pedido_id)["venta_sena_id"], self.admin_id, "error")

    def test_el_aviso_queda_anotado(self):
        pedido_id = self._tomar(telefono="1155551234")
        self.assertIsNone(self._pedido(pedido_id)["avisado"])
        pedidos_impresion_repo.anotar_aviso(pedido_id)
        self.assertIsNotNone(self._pedido(pedido_id)["avisado"])


class TestCuentasDelPedido(unittest.TestCase):
    def test_telefono_limpio(self):
        for escrito in ("11 5555 1234", "(11) 5555-1234", "011 5555 1234", "+54 9 11 5555 1234", "54 11 5555 1234"):
            self.assertEqual(dominio.telefono_limpio(escrito), "1155551234", escrito)
        self.assertEqual(dominio.telefono_limpio("  "), "")
        for escrito in ("5555 1234", "11 15 5555 1234"):
            with self.assertRaises(ValueError, msg=escrito):
                dominio.telefono_limpio(escrito)

    def test_enlace_y_mensaje_de_whatsapp(self):
        mensaje = dominio.mensaje_pedido_listo("Martina", 100, 10000.0)
        self.assertIn("100 impresiones", mensaje)
        self.assertIn("$ 10.000", mensaje)
        self.assertNotIn("abonar", dominio.mensaje_pedido_listo("Martina", 100, 0.0))
        enlace = dominio.enlace_whatsapp("1155551234", "Hola Martina! Listo")
        self.assertTrue(enlace.startswith("https://web.whatsapp.com/send?phone=5491155551234&text=Hola%20Martina"))

    def test_numeros_de_arriba_solo_cuentan_los_pendientes(self):
        pedidos = [
            {"estado": dominio.PEDIDO_PENDIENTE, "total": 15000.0, "sena": 5000.0},
            {"estado": dominio.PEDIDO_PENDIENTE, "total": 6000.0, "sena": 6000.0},
            {"estado": dominio.PEDIDO_RETIRADO, "total": 9000.0, "sena": 1000.0},
        ]
        self.assertEqual(dominio.numeros_de_los_pedidos(pedidos), {"pendientes": 2, "senas": 11000.0, "falta": 10000.0})


class TestPantallas(_ConPedidos):
    def _cobro_justo(self):
        """Reemplaza la ventana de cobro (modal) por un pago justo en efectivo."""
        llamados = []

        class _Pago:
            def __init__(self, _parent, total):
                llamados.append(total)
                self.pagos = [_pago(EF, total)]
                self.vuelto = 0.0

            def exec(self):
                return True

        mock.patch("ui.gestion_impresiones_window.DialogoPago", _Pago).start()
        mock.patch("ui.gestion_impresiones_window.mostrar_info").start()
        self.addCleanup(mock.patch.stopall)
        return llamados

    def test_nuevo_pedido_calcula_lo_que_falta_y_cobra_la_sena(self):
        llamados = self._cobro_justo()
        lucia = usuarios_repo.obtener_usuario(self.lucia_id)
        dialogo = DialogoNuevoPedido(lucia, {"codigo": "4", "descripcion": "IMPRESIONES", "precio_venta": PRECIO})
        self.addCleanup(dialogo.deleteLater)

        dialogo.campo_nombre.setText("Martina López")
        dialogo.campo_telefono.setText("11 5555 1234")
        dialogo.spin_hojas.setValue(100)
        dialogo.campo_sena.setValue(5000.0)
        self.assertEqual(dialogo.cifra_falta.valor.text(), "$ 10.000")
        dialogo._cobrar()

        self.assertEqual(llamados, [5000.0])
        pedido = pedidos_impresion_repo.listar_pedidos()[0]
        self.assertEqual((pedido["hojas"], pedido["sena"], pedido["tomado_por_nombre"]), (100, 5000.0, "Lucia"))

    def test_paga_el_total_pone_la_sena_en_el_total(self):
        lucia = usuarios_repo.obtener_usuario(self.lucia_id)
        dialogo = DialogoNuevoPedido(lucia, {"codigo": "4", "descripcion": "IMPRESIONES", "precio_venta": PRECIO})
        self.addCleanup(dialogo.deleteLater)
        dialogo.spin_hojas.setValue(40)
        dialogo.boton_todo.click()
        self.assertEqual(dialogo.campo_sena.value(), 6000.0)
        self.assertEqual(dialogo.cifra_falta.valor.text(), "$ 0")

    def test_entregar_cobra_lo_que_falta(self):
        llamados = self._cobro_justo()
        pedido_id = self._tomar()
        gaby = usuarios_repo.obtener_usuario(self.gaby_id)
        dialogo = DialogoEntregarPedido(gaby, self._pedido(pedido_id))
        self.addCleanup(dialogo.deleteLater)

        dialogo._entregar()

        self.assertEqual(llamados, [10000.0])
        self.assertEqual(self._pedido(pedido_id)["estado"], dominio.PEDIDO_RETIRADO)

    def test_la_lista_abre_en_pendientes_y_sena_perdida_y_anular_son_del_admin(self):
        self._tomar()
        otro = self._tomar(sena=15000.0)
        pedidos_impresion_repo.entregar_pedido(self.gaby_id, otro, [])

        for usuario_id, es_admin in ((self.lucia_id, False), (self.admin_id, True)):
            ventana = VentanaGestionImpresiones(usuarios_repo.obtener_usuario(usuario_id))
            self.addCleanup(ventana.deleteLater)
            self.assertEqual(ventana.tabla.rowCount(), 1)
            self.assertEqual(ventana.indicador_pendientes.valor.text(), "1")
            self.assertEqual(ventana.indicador_falta.valor.text(), "$ 10.000")
            # Las ven todos igual; a los demás les dicen "Acceso Restringido" (2026-11-04).
            for boton in (ventana.boton_perdida, ventana.boton_anular):
                self.assertFalse(boton.isHidden())
                self.assertEqual(bool(boton.property("restringido")), not es_admin)
            ventana.filtros.pastillas[0].click()
            self.assertEqual(ventana.tabla.rowCount(), 2)

    def test_avisar_abre_whatsapp_y_lo_anota(self):
        pedido_id = self._tomar(telefono="1155551234")
        ventana = VentanaGestionImpresiones(usuarios_repo.obtener_usuario(self.lucia_id))
        self.addCleanup(ventana.deleteLater)
        ventana.tabla.selectRow(0)
        with mock.patch("ui.gestion_impresiones_window.QDesktopServices") as escritorio:
            escritorio.openUrl.return_value = True
            ventana._avisar()
        self.assertIn("phone=5491155551234", escritorio.openUrl.call_args[0][0].toString())
        self.assertIsNotNone(self._pedido(pedido_id)["avisado"])


if __name__ == "__main__":
    unittest.main()
