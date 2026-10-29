"""
tests/test_cajas.py
====================
Las cajas con número (pedido del dueño, 2026-10-18; reglas en
repositories/relevo_repo.py): abrir contando el Cambio Fijo, recibir la caja de
quien cubrió el turno, cerrar la de quien se fue, el cierre forzoso a la hora
del fin del turno, las ventas del Admin a nombre de la responsable (también las
que cobró sin caja, que pasan a la caja siguiente) y el sobre que carga solo el
Admin.

Se ejecutan con:

    python -m unittest discover tests
"""

import sqlite3
import unittest
from datetime import date, datetime
from unittest import mock

import dominio
from database import conexion_db
from repositories import (
    articulos_repo, compras_repo, relevo_repo, reportes_repo, turnos_repo, turnos_ventas_repo,
    usuarios_repo, ventas_repo,
)
from base import BaseConBaseTemporal

LUNES = date(2026, 1, 5)
DOMINGO = date(2026, 1, 4)


def _a_las(hora, minuto=0, dia=LUNES):
    return datetime(dia.year, dia.month, dia.day, hora, minuto)


class _BaseDeCajas(BaseConBaseTemporal):
    def setUp(self):
        super().setUp()
        self.admin_id = usuarios_repo.crear_usuario("Dueño", "1234", dominio.ROL_ADMIN)
        self.lucia_id = usuarios_repo.crear_usuario("Lucia", "1234", dominio.ROL_EMPLEADA)
        self.gaby_id = usuarios_repo.crear_usuario("Gaby", "1234", dominio.ROL_EMPLEADA)
        articulos_repo.crear_articulo("COD1", "Turrón", None, None, 500.0, 300.0, 0)
        compras_repo.registrar_compra(self.admin_id, [{"codigo": "COD1", "cantidad": 100, "costo_unitario": 300.0}])

    def _vender(self, usuario_id, momento, monto=500.0, metodo=dominio.PAGO_EFECTIVO):
        with mock.patch("repositories.ventas_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = momento
            return ventas_repo.confirmar_venta(
                usuario_id,
                [{"codigo": "COD1", "descripcion": "Turrón", "cantidad": 1, "precio_unitario": monto}],
                [{"metodo": metodo, "monto": monto}],
            )

    def _situacion(self, usuario_id, momento):
        return relevo_repo.situacion_al_entrar(usuario_id, momento)

    def _caja_de_la_venta(self, venta_id):
        with conexion_db() as conexion:
            return conexion.execute(
                "SELECT ventas.usuario_id, ventas_caja.caja_id, ventas_caja.cargada_por "
                "FROM ventas LEFT JOIN ventas_caja ON ventas_caja.venta_id = ventas.id WHERE ventas.id = ?",
                (venta_id,),
            ).fetchone()


class TestAbrirCaja(_BaseDeCajas):
    def test_sin_caja_abierta_la_empleada_abre_una_contando_el_cambio_fijo(self):
        situacion = self._situacion(self.lucia_id, _a_las(5, 55))

        self.assertEqual(situacion["situacion"], relevo_repo.SITUACION_ABRIR)
        self.assertTrue(situacion["cuenta_cambio"])
        self.assertEqual(situacion["cambio_esperado"], 50000.0)
        self.assertEqual(situacion["turno_label"], "Mañana")

    def test_quien_abre_a_las_05_55_abre_la_manana(self):
        caja = relevo_repo.abrir_caja(self.lucia_id, 49500.0, _a_las(5, 55))

        self.assertEqual(caja["turno_label"], "Mañana")
        self.assertEqual(caja["diferencia"], -500.0)
        self.assertEqual(self._situacion(self.lucia_id, _a_las(6, 0))["situacion"], relevo_repo.SITUACION_SU_CAJA)

    def test_quien_llega_una_hora_antes_abre_el_turno_que_viene_y_cierra_el_que_termina(self):
        # Pedido del dueño (2026-10-29): la que viene a recuperar horas y abre a las
        # 13:00 abre la Tarde; con 12:59 todavía es la Mañana.
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))
        self._vender(self.lucia_id, _a_las(9), 1000.0)
        self.assertEqual(self._situacion(self.gaby_id, _a_las(12, 59))["situacion"], relevo_repo.SITUACION_RECIBIR)

        manana = turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(13, 0))
        self.assertEqual((manana["turno"], manana["monto_a_retirar"]), (dominio.TURNO_MANANA, 1000.0))
        situacion = self._situacion(self.gaby_id, _a_las(13, 0))
        self.assertEqual((situacion["situacion"], situacion["turno_label"]), (relevo_repo.SITUACION_ABRIR, "Tarde"))
        self.assertEqual(relevo_repo.abrir_caja(self.gaby_id, 50000.0, _a_las(13, 0))["turno_label"], "Tarde")

    def test_si_hay_que_contar_no_se_puede_abrir_sin_el_monto(self):
        with self.assertRaises(ValueError):
            relevo_repo.abrir_caja(self.lucia_id, None, _a_las(5, 55))

    def test_el_admin_entra_sin_caja_y_no_puede_abrir_una(self):
        self.assertEqual(self._situacion(self.admin_id, _a_las(10))["situacion"], relevo_repo.SITUACION_ADMIN)
        with self.assertRaises(ValueError):
            relevo_repo.abrir_caja(self.admin_id, 50000.0, _a_las(10))

    def test_con_una_caja_abierta_otra_persona_no_puede_abrir_otra(self):
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))

        self.assertEqual(self._situacion(self.gaby_id, _a_las(10))["situacion"], relevo_repo.SITUACION_RECIBIR)
        with self.assertRaises(ValueError):
            relevo_repo.abrir_caja(self.gaby_id, 50000.0, _a_las(10))

    def test_la_misma_persona_que_cerro_reabre_sin_contar(self):
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))
        turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(14, 0))

        situacion = self._situacion(self.lucia_id, _a_las(14, 1))
        caja = relevo_repo.abrir_caja(self.lucia_id, None, _a_las(14, 1))

        self.assertFalse(situacion["cuenta_cambio"])
        self.assertEqual(caja["turno_label"], "Tarde")
        self.assertIsNone(caja["cambio_contado"])

    def test_la_siguiente_espera_el_cambio_que_dejo_la_anterior(self):
        # Lucía contó $500 de menos al abrir: deja lo que recibió, y eso es lo que
        # se espera en la caja siguiente (el faltante se ve una sola vez).
        relevo_repo.abrir_caja(self.lucia_id, 49500.0, _a_las(5, 55))
        cierre = turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(14, 0))

        situacion = self._situacion(self.gaby_id, _a_las(14, 2))

        self.assertEqual(cierre["cambio_que_queda"], 49500.0)
        self.assertTrue(situacion["cuenta_cambio"])
        self.assertEqual(situacion["cambio_esperado"], 49500.0)


class TestVentasEnLaCaja(_BaseDeCajas):
    def test_la_venta_queda_en_la_caja_abierta(self):
        caja = relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))
        venta = self._vender(self.lucia_id, _a_las(9))

        fila = self._caja_de_la_venta(venta)
        self.assertEqual((fila["usuario_id"], fila["caja_id"], fila["cargada_por"]),
                         (self.lucia_id, caja["caja_numero"], None))

    def test_lo_que_cobra_el_admin_queda_a_nombre_de_la_responsable(self):
        # Pedido del dueño: "que lo asiente como la empleada que estaba antes de
        # que yo entrara como administrador".
        caja = relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))
        venta = self._vender(self.admin_id, _a_las(9))

        fila = self._caja_de_la_venta(venta)
        self.assertEqual((fila["usuario_id"], fila["caja_id"], fila["cargada_por"]),
                         (self.lucia_id, caja["caja_numero"], self.admin_id))
        cierre = turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(14, 0))
        detalle = turnos_repo.detalle_cierre(cierre["id"])
        self.assertEqual(detalle["ventas"][0]["vendedor"], "Lucia")
        self.assertEqual(detalle["ventas"][0]["cargada_por_nombre"], "Dueño")

    def test_sin_caja_abierta_la_venta_queda_como_siempre(self):
        venta = self._vender(self.admin_id, _a_las(3))

        fila = self._caja_de_la_venta(venta)
        self.assertEqual((fila["usuario_id"], fila["caja_id"]), (self.admin_id, None))


class TestCerrarCaja(_BaseDeCajas):
    def test_el_cierre_queda_unido_a_su_caja(self):
        caja = relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))
        self._vender(self.lucia_id, _a_las(9), 1000.0)
        self._vender(self.lucia_id, _a_las(10), 600.0, dominio.PAGO_DIGITAL)

        cierre = turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(14, 0))

        self.assertEqual((cierre["caja_numero"], cierre["responsable"], cierre["turno"]),
                         (caja["caja_numero"], "Lucia", dominio.TURNO_MANANA))
        self.assertEqual(cierre["monto_a_retirar"], 1000.0)
        guardado = turnos_repo.listar_cierres()[0]
        self.assertEqual(guardado["caja_numero"], caja["caja_numero"])
        self.assertEqual(guardado["responsables"], ["Lucia"])
        self.assertFalse(guardado["cerrada_en_ausencia"])
        self.assertFalse(guardado["cierre_forzoso"])
        self.assertEqual(guardado["minutos_despues_del_fin"], 0)
        self.assertEqual(guardado["cambio_contado"], 50000.0)
        self.assertIsNone(relevo_repo.estado_de_la_caja(_a_las(14, 1)))

    def test_el_turno_del_cierre_es_el_de_la_caja_aunque_el_cierre_anterior_sea_de_hace_horas(self):
        # Último cierre el domingo 22:05 y el programa sin uso a la noche: la caja
        # que se abre el lunes a las 07:00 es la Mañana del lunes, no la Noche del
        # domingo (que es lo que daría contar desde el cierre anterior).
        turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(22, 5, DOMINGO))
        relevo_repo.abrir_caja(self.gaby_id, 50000.0, _a_las(7))

        cierre = turnos_repo.cerrar_turno(self.gaby_id, ahora_dt=_a_las(14, 0))

        self.assertEqual(cierre["turno"], dominio.TURNO_MANANA)
        self.assertEqual(turnos_repo.listar_cierres()[0]["fecha"], LUNES.isoformat())

    def test_el_resumen_de_la_caja_muestra_el_numero_y_el_cambio_contado(self):
        caja = relevo_repo.abrir_caja(self.lucia_id, 49800.0, _a_las(5, 55))
        self._vender(self.lucia_id, _a_las(9), 1000.0)

        resumen = turnos_repo.resumen_turno_actual()

        self.assertEqual((resumen["caja_numero"], resumen["responsable"]), (caja["caja_numero"], "Lucia"))
        self.assertEqual(resumen["cambio_inicial"], 49800.0)
        self.assertEqual(resumen["caja_actual"], 50800.0)


class TestReemplazoQueLlegaTarde(_BaseDeCajas):
    """El ejemplo del dueño: Lucía hace la Mañana y Gaby llega 14:50."""

    def test_lucia_cubre_y_gaby_recibe_la_caja_contando_todo(self):
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))
        self._vender(self.lucia_id, _a_las(9), 1000.0)
        manana = turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(14, 0))
        self.assertEqual(manana["monto_a_retirar"], 1000.0)   # el sobre de la Mañana es solo de la Mañana

        cubre = relevo_repo.abrir_caja(self.lucia_id, None, _a_las(14, 0))   # sin contar: lo dejó ella
        self._vender(self.lucia_id, _a_las(14, 20), 6200.0)
        self._vender(self.lucia_id, _a_las(14, 30), 800.0, dominio.PAGO_DIGITAL)

        situacion = self._situacion(self.gaby_id, _a_las(14, 50))
        self.assertEqual(situacion["situacion"], relevo_repo.SITUACION_RECIBIR)
        self.assertEqual((situacion["esperado"], situacion["cambio_inicial"], situacion["ventas_efectivo"]),
                         (56200.0, 50000.0, 6200.0))

        relevo = relevo_repo.recibir_caja(self.gaby_id, cubre["caja_numero"], 56000.0, _a_las(14, 50))
        self.assertEqual((relevo["diferencia"], relevo["de"]), (-200.0, "Lucia"))
        self.assertEqual(self._situacion(self.gaby_id, _a_las(15))["situacion"], relevo_repo.SITUACION_SU_CAJA)
        # Lucía ya no tiene la caja: si vuelve a entrar, es la caja de Gaby.
        self.assertEqual(self._situacion(self.lucia_id, _a_las(15))["situacion"], relevo_repo.SITUACION_RECIBIR)

        self._vender(self.gaby_id, _a_las(16), 3000.0)
        tarde = turnos_repo.cerrar_turno(self.gaby_id, ahora_dt=_a_las(22, 0))

        # Lo que vendió Lucía en esos 50 minutos va en el sobre de Gaby.
        self.assertEqual(tarde["monto_a_retirar"], 9200.0)
        self.assertEqual(tarde["turno"], dominio.TURNO_TARDE)
        guardado = turnos_repo.listar_cierres()[0]
        self.assertEqual(guardado["responsables"], ["Lucia", "Gaby"])
        self.assertEqual(len(guardado["relevos"]), 1)
        self.assertEqual(guardado["relevos"][0]["monto_contado"], 56000.0)
        self.assertFalse(guardado["cerrada_en_ausencia"])

    def test_si_gaby_llega_14_45_lucia_todavia_cierra_su_propia_caja(self):
        # El caso de todos los días (pedido del dueño, 2026-10-29): la caja se
        # cierra sola recién a las 15, así que Lucía cierra la suya cuando llega
        # Gaby. Todo lo que cobró va a su sobre; en el cajón queda el cambio con
        # que arrancó su caja, y con eso abre Gaby la Tarde.
        relevo_repo.abrir_caja(self.lucia_id, 49500.0, _a_las(5, 55))   # faltaban $ 500
        self._vender(self.lucia_id, _a_las(9), 1000.0)
        self._vender(self.lucia_id, _a_las(14, 30), 2000.0)

        self.assertEqual(self._situacion(self.lucia_id, _a_las(14, 45))["situacion"], relevo_repo.SITUACION_SU_CAJA)
        manana = turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(14, 45))
        self.assertEqual((manana["turno"], manana["monto_a_retirar"]), (dominio.TURNO_MANANA, 3000.0))

        situacion = self._situacion(self.gaby_id, _a_las(14, 45))
        self.assertEqual(situacion["situacion"], relevo_repo.SITUACION_ABRIR)
        self.assertEqual((situacion["cambio_esperado"], situacion["cuenta_cambio"], situacion["turno_label"]),
                         (49500.0, True, "Tarde"))
        tarde = relevo_repo.abrir_caja(self.gaby_id, 49500.0, _a_las(14, 45))
        self.assertEqual((tarde["turno_label"], tarde["diferencia"]), ("Tarde", 0.0))

    def test_no_se_puede_recibir_otra_caja_que_la_abierta(self):
        caja = relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))
        with self.assertRaises(ValueError):
            relevo_repo.recibir_caja(self.gaby_id, caja["caja_numero"] + 1, 50000.0, _a_las(10))


class TestCerrarLaCajaDeOtra(_BaseDeCajas):
    def test_si_su_turno_termino_la_que_llega_la_cierra_en_su_ausencia(self):
        caja = relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))
        self._vender(self.lucia_id, _a_las(9), 1000.0)

        situacion = self._situacion(self.gaby_id, _a_las(13, 56))
        self.assertEqual(situacion["situacion"], relevo_repo.SITUACION_CERRAR_LA_DE_OTRA)
        self.assertEqual((situacion["a_retirar"], situacion["cambio_que_queda"]), (1000.0, 50000.0))

        cierre = relevo_repo.cerrar_para_entrar(self.gaby_id, relevo_repo.SITUACION_CERRAR_LA_DE_OTRA, _a_las(13, 56))

        self.assertEqual((cierre["caja_numero"], cierre["responsable"]), (caja["caja_numero"], "Lucia"))
        guardado = turnos_repo.listar_cierres()[0]
        self.assertTrue(guardado["cerrada_en_ausencia"])
        self.assertEqual((guardado["empleada"], guardado["responsable"]), ("Gaby", "Lucia"))
        # En el Resumen del Día la caja sigue siendo de Lucía.
        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = _a_las(14, 0)
            datetime_mock.fromisoformat = datetime.fromisoformat
            manana = turnos_repo.resumen_del_dia(LUNES)["turnos"][0]
        self.assertEqual(manana["responsables"], ["Lucia"])
        # Y después Gaby abre la suya contando.
        apertura = self._situacion(self.gaby_id, _a_las(13, 57))
        self.assertEqual(apertura["situacion"], relevo_repo.SITUACION_ABRIR)
        self.assertTrue(apertura["cuenta_cambio"])
        self.assertEqual(relevo_repo.abrir_caja(self.gaby_id, 50000.0, _a_las(13, 57))["turno_label"], "Tarde")

    def test_antes_del_aviso_la_caja_de_otra_se_recibe(self):
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))

        self.assertEqual(self._situacion(self.gaby_id, _a_las(13, 54))["situacion"], relevo_repo.SITUACION_RECIBIR)

    def test_cerrar_para_entrar_no_cierra_si_la_situacion_cambio(self):
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))

        with self.assertRaises(ValueError):
            relevo_repo.cerrar_para_entrar(self.gaby_id, relevo_repo.SITUACION_CERRAR_LA_DE_OTRA, _a_las(10))
        self.assertEqual(turnos_repo.listar_cierres(), [])


class TestCierreForzoso(_BaseDeCajas):
    def test_el_boton_titila_desde_5_minutos_antes_y_vence_a_la_hora(self):
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))

        for momento, titilar, vencida in (
            (_a_las(13, 54), False, False), (_a_las(13, 55), True, False),
            (_a_las(14, 59), True, False), (_a_las(15, 0), True, True),
        ):
            with self.subTest(momento=momento):
                estado = relevo_repo.estado_de_la_caja(momento)
                self.assertEqual((estado["titilar"], estado["vencida"]), (titilar, vencida))

    def test_el_domingo_la_manana_titila_a_las_13_55(self):
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(6, 0, DOMINGO))

        self.assertFalse(relevo_repo.estado_de_la_caja(_a_las(13, 54, DOMINGO))["titilar"])
        self.assertTrue(relevo_repo.estado_de_la_caja(_a_las(13, 55, DOMINGO))["titilar"])
        self.assertEqual(relevo_repo.estado_de_la_caja(_a_las(13, 55, DOMINGO))["turno_label"], "Mañana")

    def test_a_la_hora_la_caja_se_cierra_sola(self):
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))
        self._vender(self.lucia_id, _a_las(9), 1000.0)

        self.assertIsNone(relevo_repo.cierre_forzoso_si_corresponde(_a_las(14, 59)))
        cierre = relevo_repo.cierre_forzoso_si_corresponde(_a_las(15, 0))

        self.assertTrue(cierre["forzoso"])
        self.assertEqual((cierre["monto_a_retirar"], cierre["responsable"]), (1000.0, "Lucia"))
        guardado = turnos_repo.listar_cierres()[0]
        self.assertTrue(guardado["cierre_forzoso"])
        self.assertFalse(guardado["cerrada_en_ausencia"])
        self.assertEqual(guardado["minutos_despues_del_fin"], 60)
        # Lucía, si sigue atendiendo, vuelve a entrar sin contar.
        self.assertFalse(self._situacion(self.lucia_id, _a_las(15, 5))["cuenta_cambio"])

    def test_si_el_programa_estuvo_cerrado_la_propia_caja_vencida_se_cierra_al_entrar(self):
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))

        situacion = self._situacion(self.lucia_id, _a_las(15))
        self.assertEqual(situacion["situacion"], relevo_repo.SITUACION_SU_CAJA_VENCIDA)
        cierre = relevo_repo.cerrar_para_entrar(self.lucia_id, relevo_repo.SITUACION_SU_CAJA_VENCIDA, _a_las(15))

        self.assertTrue(cierre["forzoso"])
        self.assertEqual(self._situacion(self.lucia_id, _a_las(15))["situacion"], relevo_repo.SITUACION_ABRIR)


class TestVentasSinCaja(_BaseDeCajas):
    """Lo que cobra el Admin sin ninguna caja abierta pasa a la caja de la que
    llega (pedido del dueño, 2026-10-29: "lo que yo facture queda a cargo de la
    operadora que viene"; hasta ese día se cerraba aparte)."""

    def _el_admin_vende_sin_caja(self):
        primera = self._vender(self.admin_id, _a_las(2, 36), 1500.0)   # sin nadie en el mostrador
        segunda = self._vender(self.admin_id, _a_las(4, 50), 500.0)
        return primera, segunda

    def test_la_que_llega_abre_su_caja_contando_el_cambio_y_lo_que_cobro_el_admin(self):
        self._el_admin_vende_sin_caja()

        situacion = self._situacion(self.lucia_id, _a_las(5, 55))

        self.assertEqual(situacion["situacion"], relevo_repo.SITUACION_ABRIR)
        self.assertTrue(situacion["cuenta_cambio"])
        self.assertEqual((situacion["ventas_sin_caja"], situacion["efectivo_sin_caja"]), (2, 2000.0))
        self.assertEqual((situacion["cambio_esperado"], situacion["esperado"]), (50000.0, 52000.0))
        self.assertTrue(situacion["desde"].startswith("2026-01-05T02:36"))
        with self.assertRaises(ValueError):
            relevo_repo.abrir_caja(self.lucia_id, None, _a_las(5, 55))

    def test_las_ventas_del_admin_quedan_en_su_caja_a_su_nombre_y_van_en_su_sobre(self):
        primera, segunda = self._el_admin_vende_sin_caja()

        apertura = relevo_repo.abrir_caja(self.lucia_id, 52000.0, _a_las(5, 55))
        self._vender(self.lucia_id, _a_las(9), 1000.0)

        self.assertEqual((apertura["ventas_sin_caja"], apertura["diferencia"]), (2, 0.0))
        self.assertEqual(apertura["cambio_contado"], 50000.0)   # el cambio solo: lo del Admin va al sobre
        for venta in (primera, segunda):
            fila = self._caja_de_la_venta(venta)
            self.assertEqual((fila["usuario_id"], fila["caja_id"], fila["cargada_por"]),
                             (self.lucia_id, apertura["caja_numero"], self.admin_id))
        cierre = turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(13, 59))
        self.assertEqual((cierre["caja_numero"], cierre["turno_label"]), (apertura["caja_numero"], "Mañana"))
        self.assertEqual((cierre["monto_a_retirar"], cierre["cambio_que_queda"]), (3000.0, 50000.0))
        self.assertEqual(len(turnos_repo.listar_cierres()), 1)   # ningún cierre aparte

    def test_si_falta_plata_de_lo_del_admin_se_ve_al_abrir_y_una_sola_vez(self):
        self._el_admin_vende_sin_caja()

        apertura = relevo_repo.abrir_caja(self.lucia_id, 51500.0, _a_las(5, 55))

        self.assertEqual((apertura["diferencia"], apertura["cambio_contado"]), (-500.0, 49500.0))
        cierre = turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(13, 59))
        self.assertEqual((cierre["monto_a_retirar"], cierre["cambio_que_queda"]), (2000.0, 49500.0))
        self.assertEqual(self._situacion(self.gaby_id, _a_las(13, 59))["esperado"], 49500.0)

    def test_aunque_haya_cerrado_ella_la_anterior_cuenta_si_el_admin_cobro_en_el_medio(self):
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))
        turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(13, 59))
        self.assertFalse(self._situacion(self.lucia_id, _a_las(14, 0))["cuenta_cambio"])

        self._vender(self.admin_id, _a_las(14, 10), 700.0)
        situacion = self._situacion(self.lucia_id, _a_las(14, 20))

        self.assertTrue(situacion["cuenta_cambio"])
        self.assertEqual(situacion["esperado"], 50700.0)


class TestPorTurnoSigueALaCaja(_BaseDeCajas):
    """Reportes > Por Turno (y Totales por turno) reparten cada venta en el turno
    de su caja, no en el de su hora (pedido del dueño, 2026-10-29): suman lo
    mismo que los cierres de cada turno."""

    def _por_turno(self, dia):
        return {fila["turno"]: fila["total"]
                for fila in reportes_repo.resumen_por_turno(dia.isoformat(), dia.isoformat())}

    def _totales_por_turno(self, dia):
        return [(fila["etiqueta"], fila["total"])
                for fila in reportes_repo.resumen_por_origen(dia.isoformat(), dia.isoformat(), "turno")]

    def test_lo_vendido_a_las_13_30_en_la_caja_de_la_tarde_es_de_la_tarde(self):
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))
        self._vender(self.lucia_id, _a_las(9), 1000.0)
        manana = turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(13, 0))
        relevo_repo.abrir_caja(self.gaby_id, 50000.0, _a_las(13, 0))
        self._vender(self.gaby_id, _a_las(13, 30), 500.0)   # por el reloj sería Mañana
        tarde = turnos_repo.cerrar_turno(self.gaby_id, ahora_dt=_a_las(21, 59))

        self.assertEqual((manana["turno_label"], manana["ventas_efectivo"]), ("Mañana", 1000.0))
        self.assertEqual((tarde["turno_label"], tarde["ventas_efectivo"]), ("Tarde", 500.0))
        self.assertEqual(self._por_turno(LUNES),
                         {dominio.TURNO_MANANA: 1000.0, dominio.TURNO_TARDE: 500.0, dominio.TURNO_NOCHE: 0.0})
        self.assertEqual(self._totales_por_turno(LUNES), [("Mañana", 1000.0), ("Tarde", 500.0), ("Noche", 0.0)])

    def test_la_manana_que_abre_a_las_5_cuenta_en_su_dia(self):
        martes = date(2026, 1, 6)
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 0, martes))
        self._vender(self.lucia_id, _a_las(5, 30, martes), 300.0)   # por el reloj, Noche del lunes

        self.assertEqual(self._por_turno(LUNES)[dominio.TURNO_NOCHE], 0.0)
        self.assertEqual(self._por_turno(martes)[dominio.TURNO_MANANA], 300.0)

    def test_una_venta_sin_caja_sigue_con_su_hora(self):
        self._vender(self.admin_id, _a_las(13, 30), 700.0)   # el Admin, sin nadie en el mostrador

        self.assertEqual(self._por_turno(LUNES)[dominio.TURNO_MANANA], 700.0)


class TestSobreLoCargaSoloElAdmin(_BaseDeCajas):
    def _un_cierre(self):
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))
        self._vender(self.lucia_id, _a_las(9), 1000.0)
        return turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(14, 0))

    def test_una_empleada_no_puede_cargar_lo_contado(self):
        cierre = self._un_cierre()
        with self.assertRaises(PermissionError):
            turnos_repo.verificar_cierre(cierre["id"], 1000.0, self.gaby_id)

    def test_cada_conteo_queda_guardado_y_el_cierre_muestra_el_ultimo(self):
        cierre = self._un_cierre()

        turnos_repo.verificar_cierre(cierre["id"], 900.0, self.admin_id)
        turnos_repo.verificar_cierre(cierre["id"], 1000.0, self.admin_id)

        detalle = turnos_repo.detalle_cierre(cierre["id"])
        self.assertEqual([v["monto_contado"] for v in detalle["verificaciones"]], [900.0, 1000.0])
        self.assertEqual([v["diferencia"] for v in detalle["verificaciones"]], [-100.0, 0.0])
        guardado = turnos_repo.listar_cierres()[0]
        self.assertEqual((guardado["monto_contado"], guardado["diferencia"]), (1000.0, 0.0))


# Lo que muestra la tarjeta del Cierre de Turno (ui/tarjeta_cierre.py).
_LO_QUE_SE_VE_AL_CERRAR = (
    "turno_actual_label", "caja_numero", "responsable", "cambio_inicial", "monto_a_retirar",
    "ventas_efectivo", "ventas_digital", "ventas_total",
    "kiosko_solo_efectivo", "kiosko_solo_digital", "impresiones_efectivo", "impresiones_digital",
)


class TestUnCierreHechoSeVeComoAlCerrarlo(_BaseDeCajas):
    """
    Pedido del dueño (2026-10-20): en Control de Cierres cada cierre se ve como
    la pantalla Cierre de Turno al cerrarlo, también el forzoso (lo hace el
    programa solo y nadie veía ese resumen). detalle_cierre()["resumen"] tiene
    que dar lo mismo que resumen_turno_actual() justo antes de cerrar.
    """

    def setUp(self):
        super().setUp()
        articulos_repo.crear_articulo(dominio.CODIGO_ARTICULO_IMPRESIONES, "IMPRESIONES", None, None, 150.0, 0.0, 0)

    def _vender_impresiones(self, momento, cantidad=3):
        with mock.patch("repositories.ventas_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = momento
            return ventas_repo.confirmar_venta(
                self.lucia_id,
                [{"codigo": dominio.CODIGO_ARTICULO_IMPRESIONES, "descripcion": "IMPRESIONES",
                  "cantidad": cantidad, "precio_unitario": 150.0}],
                [{"metodo": dominio.PAGO_EFECTIVO, "monto": cantidad * 150.0}],
            )

    def _turno_de_lucia(self):
        """Caja de Lucía (contó $500 de menos) con kiosko e impresiones."""
        relevo_repo.abrir_caja(self.lucia_id, 49500.0, _a_las(5, 55))
        self._vender(self.lucia_id, _a_las(8), 1000.0)
        self._vender(self.lucia_id, _a_las(9), 600.0, dominio.PAGO_DIGITAL)
        self.venta_impresiones = self._vender_impresiones(_a_las(10))          # $450 en efectivo

    def _en_pantalla_al_cerrar(self, momento):
        """Lo que mostraba la pantalla Cierre de Turno a esa hora."""
        with conexion_db() as conexion:
            return turnos_repo._resumen_en_curso(conexion, momento)

    def _se_ve(self, resumen):
        return {clave: resumen[clave] for clave in _LO_QUE_SE_VE_AL_CERRAR}

    def test_un_cierre_comun_se_ve_igual_que_al_cerrarlo(self):
        self._turno_de_lucia()
        al_cerrar = self._en_pantalla_al_cerrar(_a_las(14, 0))

        cierre = turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(14, 0))
        resumen = turnos_repo.detalle_cierre(cierre["id"])["resumen"]

        self.assertEqual(self._se_ve(resumen), self._se_ve(al_cerrar))
        self.assertEqual(
            (resumen["cambio_inicial"], resumen["kiosko_solo_efectivo"], resumen["kiosko_solo_digital"],
             resumen["impresiones_efectivo"], resumen["ventas_total"]),
            (49500.0, 1000.0, 600.0, 450.0, 2050.0),
        )

    def test_un_cierre_forzoso_se_ve_igual_que_si_lo_hubiera_cerrado_ella(self):
        self._turno_de_lucia()
        al_cerrar = self._en_pantalla_al_cerrar(_a_las(15, 0))

        cierre = relevo_repo.cierre_forzoso_si_corresponde(_a_las(15, 0))
        resumen = turnos_repo.detalle_cierre(cierre["id"])["resumen"]

        self.assertTrue(cierre["forzoso"])
        self.assertEqual(self._se_ve(resumen), self._se_ve(al_cerrar))
        self.assertEqual(
            (resumen["turno_actual_label"], resumen["caja_numero"], resumen["responsable"]),
            ("Mañana", 1, "Lucia"),
        )

    def test_una_venta_anulada_despues_del_cierre_se_sigue_viendo_como_al_cerrar(self):
        # La plata del cierre es una foto: la venta anulada sigue sumada en el Kiosko guardado,
        # así que tiene que seguir figurando como impresiones (y no pasar a Kiosko).
        self._turno_de_lucia()
        al_cerrar = self._en_pantalla_al_cerrar(_a_las(14, 0))
        cierre = turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(14, 0))

        ventas_repo.anular_venta(self.venta_impresiones, self.admin_id, "se cobró de más")
        resumen = turnos_repo.detalle_cierre(cierre["id"])["resumen"]

        self.assertEqual(self._se_ve(resumen), self._se_ve(al_cerrar))

    def test_un_cierre_sin_caja_muestra_el_cambio_fijo(self):
        self._vender(self.admin_id, _a_las(2, 36), 1500.0)   # el Admin, sin nadie en el mostrador
        cierre = turnos_repo.cerrar_turno(self.admin_id, ahora_dt=_a_las(5, 55))   # y lo cierra él

        resumen = turnos_repo.detalle_cierre(cierre["id"])["resumen"]

        self.assertIsNone(resumen["caja_numero"])
        self.assertEqual((resumen["cambio_inicial"], resumen["ventas_efectivo"]), (50000.0, 1500.0))


class TestCadaOrigenSumaEnLaCaja(_BaseDeCajas):
    """
    Red de seguridad de la trampa "Sumar un origen de venta nuevo toca la caja"
    (CLAUDE.md): un origen que se agregue a dominio.ORIGENES_VENTA y no a la
    caja haría "faltar" su plata en cada cierre, sin ningún error a la vista.
    Hoy hay un solo origen (KIOSKO), pero estas pruebas recorren TODOS los de
    dominio: el día que se sume uno, fallan hasta que la caja lo cuente.
    """

    def _vender_una_de_cada_origen(self):
        # Con las piezas de ventas_repo que reciben el origen (confirmar_venta
        # graba siempre KIOSKO): así cuenta también un origen nuevo que todavía
        # no tenga pantalla para venderlo.
        with conexion_db() as conexion:
            for origen in dominio.ORIGENES_VENTA:
                venta_id = ventas_repo._insertar_cabecera_venta(conexion, _a_las(9), self.admin_id, 150.0, origen)
                ventas_repo._insertar_pagos(conexion, venta_id, [
                    {"metodo": dominio.PAGO_EFECTIVO, "monto": 100.0},
                    {"metodo": dominio.PAGO_DIGITAL, "monto": 50.0},
                ])

    def test_cada_origen_tiene_su_lugar_en_el_desglose_de_la_caja(self):
        self.assertEqual(set(turnos_ventas_repo._PREFIJO_COLUMNAS_POR_ORIGEN), set(dominio.ORIGENES_VENTA))

    def test_cada_importe_del_desglose_tiene_su_columna_en_el_cierre(self):
        with conexion_db() as conexion:
            columnas = {fila["name"] for fila in conexion.execute("PRAGMA table_info(cierres_turno)")}
        self.assertEqual(set(turnos_repo._CAMPOS_PLATA) - columnas, set())

    def test_la_plata_de_cada_origen_entra_en_el_cajon_y_en_el_cierre_grabado(self):
        self._vender_una_de_cada_origen()
        cantidad = len(dominio.ORIGENES_VENTA)

        resumen = turnos_repo.resumen_turno_actual()
        self.assertEqual((resumen["ventas_efectivo"], resumen["ventas_digital"]), (100.0 * cantidad, 50.0 * cantidad))
        self.assertEqual(resumen["caja_actual"], resumen["cambio_inicial"] + 100.0 * cantidad)

        cierre_id = turnos_repo.cerrar_turno(self.admin_id)["id"]
        with conexion_db() as conexion:
            grabado = conexion.execute("SELECT * FROM cierres_turno WHERE id = ?", (cierre_id,)).fetchone()
        self.assertEqual((grabado["ventas_efectivo"], grabado["monto_a_retirar"]), (100.0 * cantidad, 100.0 * cantidad))
        # Cada origen en sus propias columnas: si faltara uno, la suma no llega.
        self.assertEqual(sum(grabado[campo] for campo in turnos_repo._CAMPOS_PLATA), 150.0 * cantidad)
        for origen in dominio.ORIGENES_VENTA:
            prefijo = turnos_ventas_repo._PREFIJO_COLUMNAS_POR_ORIGEN.get(origen)
            self.assertIsNotNone(prefijo, msg=f"{origen} no tiene columnas en la caja")
            self.assertEqual((resumen[f"{prefijo}_efectivo"], resumen[f"{prefijo}_digital"]), (100.0, 50.0), msg=origen)
            self.assertEqual((grabado[f"{prefijo}_efectivo"], grabado[f"{prefijo}_digital"]), (100.0, 50.0), msg=origen)

    def test_el_esquema_de_ventas_admite_cada_origen_y_rechaza_uno_inventado(self):
        # ventas.origen tiene un CHECK armado con dominio.ORIGENES_VENTA (ver regla 5).
        with conexion_db() as conexion:
            for origen in dominio.ORIGENES_VENTA:
                ventas_repo._insertar_cabecera_venta(conexion, _a_las(9), self.admin_id, 10.0, origen)
            with self.assertRaises(sqlite3.IntegrityError):
                ventas_repo._insertar_cabecera_venta(conexion, _a_las(9), self.admin_id, 10.0, "INVENTADO")


if __name__ == "__main__":
    unittest.main()
