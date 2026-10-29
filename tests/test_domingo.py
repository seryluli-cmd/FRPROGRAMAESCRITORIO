"""El kiosko usa tres turnos todos los días, sin la excepción de CyberBIOS."""

import unittest
from datetime import date, datetime, time, timedelta
from unittest import mock

import database
import dominio
import turnos
from base import BaseConBaseTemporal
from repositories import articulos_repo, envio_pwa_repo, relevo_repo, reportes_repo, turnos_repo, usuarios_repo, ventas_repo

DOMINGO = date(2026, 1, 4)


class TestCalendarioUniforme(unittest.TestCase):
    def test_cada_minuto_de_la_semana_tiene_el_turno_esperado(self):
        # Incluye las 18:00 del domingo, que antes adelantaban la Noche.
        for dia in range(7):
            fecha = DOMINGO + timedelta(days=dia)
            for minuto in range(24 * 60):
                momento = datetime.combine(fecha, time()) + timedelta(minutes=minuto)
                esperado = "MAÑANA" if 360 <= minuto < 840 else "TARDE" if 840 <= minuto < 1320 else "NOCHE"
                self.assertEqual(turnos.calcular_turno(momento), esperado, momento)

    def test_domingo_conserva_tres_turnos_con_cualquier_tipo_de_fecha(self):
        for fecha in (DOMINGO, datetime(2026, 1, 4, 18), "2026-01-04", "2026-01-04T18:00:00"):
            self.assertEqual(turnos.turnos_del_dia(fecha), ("MAÑANA", "TARDE", "NOCHE"))
            self.assertEqual([turnos.etiqueta_turno(fecha, t) for t in dominio.TURNOS],
                             ["Mañana", "Tarde", "Noche"])

    def test_fin_aviso_y_vencimiento_de_los_tres_turnos_del_domingo(self):
        for turno, fin in (("MAÑANA", datetime(2026, 1, 4, 14)),
                           ("TARDE", datetime(2026, 1, 4, 22)),
                           ("NOCHE", datetime(2026, 1, 5, 6))):
            with self.subTest(turno=turno):
                self.assertEqual(turnos.fin_del_turno(DOMINGO, turno), fin)
                self.assertEqual(turnos.inicio_del_aviso_de_cierre(DOMINGO, turno), fin - timedelta(minutes=5))
                self.assertEqual(turnos.turno_vencimiento(DOMINGO, turno), fin + timedelta(hours=1))
                self.assertEqual(turnos.turno_que_arranca_tras_un_cierre(fin - timedelta(hours=1)),
                                 {"MAÑANA": "TARDE", "TARDE": "NOCHE", "NOCHE": "MAÑANA"}[turno])


class TestDomingoConCajas(BaseConBaseTemporal):
    def setUp(self):
        super().setUp()
        self.operadora = usuarios_repo.crear_usuario("Operadora de prueba", "1234", dominio.ROL_EMPLEADA)
        articulos_repo.crear_articulo("DOM", "Artículo de prueba", None, None, 500, 300, 0)

    def _vender(self, momento, monto):
        with mock.patch("repositories.ventas_repo.datetime") as reloj:
            reloj.now.return_value = momento
            ventas_repo.confirmar_venta(self.operadora,
                [{"codigo": "DOM", "descripcion": "Artículo de prueba", "cantidad": 1, "precio_unitario": monto}],
                [{"metodo": dominio.PAGO_EFECTIVO, "monto": monto}])

    def test_los_tres_cierres_concilian_con_reportes_y_datos_para_la_app(self):
        # La mañana cierra tarde y la noche vende pasada la medianoche:
        # el turno pertenece a la caja y toda la noche pertenece al domingo.
        casos = (
            (datetime(2026, 1, 4, 6), datetime(2026, 1, 4, 14, 5), datetime(2026, 1, 4, 14, 10), "MAÑANA", "mañana", 500),
            (datetime(2026, 1, 4, 14, 10), datetime(2026, 1, 4, 18), datetime(2026, 1, 4, 22), "TARDE", "tarde", 700),
            (datetime(2026, 1, 4, 22), datetime(2026, 1, 5, 2), datetime(2026, 1, 5, 6), "NOCHE", "noche", 900),
        )
        for indice, (abre, vende, cierra, turno, nombre_app, monto) in enumerate(casos):
            with self.subTest(turno=turno):
                relevo_repo.abrir_caja(self.operadora, 50000 if indice == 0 else None, abre)
                self._vender(vende, monto)
                cierre = turnos_repo.cerrar_turno(self.operadora, ahora_dt=cierra)
                self.assertEqual((cierre["turno"], cierre["monto_a_retirar"]),
                                 (turno, monto))
                with database.conexion_db() as conexion:
                    datos = envio_pwa_repo.datos_del_cierre(conexion, cierre["id"])
                    fecha = conexion.execute("SELECT fecha FROM cierres_turno WHERE id = ?", (cierre["id"],)).fetchone()[0]
                self.assertEqual(fecha, DOMINGO.isoformat())
                self.assertEqual((datos["turno"], datos["importe"]), (nombre_app, monto))
        resumen = turnos_repo.resumen_del_dia(DOMINGO)
        self.assertEqual([fila["etiqueta"] for fila in resumen["turnos"]], ["Mañana", "Tarde", "Noche"])
        self.assertEqual([fila["total"] for fila in resumen["turnos"]], [500, 700, 900])
        self.assertEqual([fila["estado"] for fila in resumen["turnos"]], [turnos_repo.ESTADO_CERRADO] * 3)
        por_turno = reportes_repo.resumen_por_turno(DOMINGO.isoformat(), DOMINGO.isoformat())
        self.assertEqual([(fila["turno"], fila["total"]) for fila in por_turno],
                         [("MAÑANA", 500), ("TARDE", 700), ("NOCHE", 900)])

    def test_cierre_forzoso_del_domingo_a_las_15_y_a_las_23(self):
        for indice, (abre, fin, turno) in enumerate(((6, 15, "MAÑANA"), (15, 23, "TARDE"))):
            with self.subTest(turno=turno):
                relevo_repo.abrir_caja(self.operadora, 50000 if indice == 0 else None, datetime(2026, 1, 4, abre))
                self.assertIsNone(relevo_repo.cierre_forzoso_si_corresponde(datetime(2026, 1, 4, fin - 1, 59)))
                cierre = relevo_repo.cierre_forzoso_si_corresponde(datetime(2026, 1, 4, fin))
                self.assertTrue(cierre["forzoso"])
                self.assertEqual(cierre["turno"], turno)
