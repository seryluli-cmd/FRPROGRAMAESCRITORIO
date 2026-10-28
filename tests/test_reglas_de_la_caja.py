"""
tests/test_reglas_de_la_caja.py
================================
Cada regla de plata de la caja y del sobre vive en un solo lugar: lo que va al
sobre y el total cobrado (dominio.monto_a_retirar y .total_cobrado, que usa
turnos_repo), la diferencia entre lo contado y lo esperado
(dominio.diferencia_de_plata), cuándo "coincide" y cuándo falta plata
(dominio.coincide y .falta_plata) y si una caja se cerró en ausencia de su
responsable (cajas_repo.cerrada_en_ausencia, por número de usuario).

Estas pruebas miran que Caja, el Cierre de Turno, el relevo, Control de
Cierres, el Resumen del Día y el envío a la app de gastos lean lo mismo que se
graba y digan lo mismo de una diferencia (plataforma "offscreen" de Qt, sin
abrir ninguna ventana).

Se ejecutan con:

    python -m unittest discover tests
"""

import os
import unittest
from datetime import date, datetime
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import dominio  # noqa: E402
from database import conexion_db  # noqa: E402
from repositories import (  # noqa: E402
    articulos_repo, cajas_repo, compras_repo, envio_pwa_repo, relevo_repo, turnos_repo, usuarios_repo,
    ventas_repo,
)
from ui import caja_window, ingreso_caja  # noqa: E402
from ui.caja_window import CajaWindow, CierreTurnoWindow  # noqa: E402
from ui.control_cierres_window import (  # noqa: E402
    ControlCierresWindow, DialogoDetalleCierre, texto_de_la_apertura, texto_del_cierre,
)
from ui.ingreso_caja import DialogoContarPlata, resolver_caja_al_entrar, texto_de_la_diferencia  # noqa: E402
from ui.reportes_resumen_dia import PestañaResumenDelDia  # noqa: E402
from ui.utils import formato_pesos  # noqa: E402
from base import BaseConBaseTemporal  # noqa: E402

_app = QApplication.instance() or QApplication([])

LUNES = date(2026, 1, 5)
MARTES = date(2026, 1, 6)

# Columnas de la tabla de Control de Cierres.
_COLUMNA_A_RETIRAR = 9
_COLUMNA_DIFERENCIA = 11

_ROJO_DEL_RESUMEN = QColor("#C62828")


def _a_las(hora, minuto=0, dia=LUNES):
    return datetime(dia.year, dia.month, dia.day, hora, minuto)


def _pintada_de(item, color) -> bool:
    return item.foreground().style() != Qt.NoBrush and item.foreground().color() == QColor(color)


# (diferencia, coincide, falta plata). Una diferencia sale siempre de
# dominio.diferencia_de_plata, redondeada al centavo.
_CASOS_DE_DIFERENCIA = (
    (0.0, True, False),
    (-0.0, True, False),
    (0.01, False, False),
    (-0.01, False, True),
    (500.0, False, False),
    (-500.0, False, True),
    (-0.02, False, True),
)


class TestLasCuentasDeLaPlata(unittest.TestCase):
    def test_la_diferencia_es_lo_contado_menos_lo_esperado_al_centavo(self):
        for contado, esperado, diferencia in (
            (1000.01, 1000.0, 0.01),
            (1000.0, 1000.01, -0.01),
            (0.1 + 0.2, 0.3, 0.0),
            (49500.0, 50000.0, -500.0),
            (50000.0, 49999.99, 0.01),
        ):
            with self.subTest(contado=contado, esperado=esperado):
                self.assertEqual(dominio.diferencia_de_plata(contado, esperado), diferencia)

    def test_coincide_y_falta_plata_en_cada_caso(self):
        for diferencia, coincide, falta in _CASOS_DE_DIFERENCIA:
            with self.subTest(diferencia=diferencia):
                self.assertEqual(dominio.coincide(diferencia), coincide)
                self.assertEqual(dominio.falta_plata(diferencia), falta)

    def test_una_diferencia_de_medio_centavo_no_puede_darse(self):
        # La tolerancia es medio centavo, pero ninguna diferencia queda cerca: se
        # redondea al centavo. Ni siquiera con montos de medio centavo o con sumas
        # que dejan la cola del punto flotante.
        pares = [(1000.0 + centavos / 100, 1000.0) for centavos in range(-300, 301)]
        pares += [(sum([0.1] * veces), veces / 10) for veces in range(60)]
        pares += [(100.005, 100.0), (100.0, 100.005), (0.125, 0.12), (0.135, 0.13), (0.1 + 0.2, 0.3)]
        for contado, esperado in pares:
            diferencia = dominio.diferencia_de_plata(contado, esperado)
            with self.subTest(contado=contado, esperado=esperado, diferencia=diferencia):
                self.assertTrue(diferencia == 0 or abs(diferencia) >= 0.01)
                self.assertEqual(dominio.coincide(diferencia), diferencia == 0)

    def test_la_cola_del_punto_flotante_coincide(self):
        self.assertTrue(dominio.coincide(0.1 + 0.2 - 0.3))
        self.assertFalse(dominio.falta_plata(0.3 - (0.1 + 0.2)))

    def test_el_texto_de_la_diferencia_dice_lo_mismo_que_coincide_y_falta_plata(self):
        for diferencia, coincide, falta in _CASOS_DE_DIFERENCIA:
            texto = texto_de_la_diferencia(diferencia)
            with self.subTest(diferencia=diferencia, texto=texto):
                self.assertEqual(texto == "coincide", coincide)
                self.assertEqual(texto.startswith("faltan"), falta)
                self.assertEqual(texto.startswith("sobran"), not coincide and not falta)
        self.assertEqual(texto_de_la_diferencia(0.01), "sobran $ 0,01")
        self.assertEqual(texto_de_la_diferencia(-0.01), "faltan $ 0,01")
        self.assertEqual(texto_de_la_diferencia(-500.0), "faltan $ 500")

    def test_el_total_y_lo_que_va_al_sobre_quedan_al_centavo(self):
        self.assertEqual(dominio.total_cobrado(1000.0, 600.0), 1600.0)
        self.assertEqual(dominio.total_cobrado(0.1, 0.2), 0.3)
        self.assertEqual(dominio.monto_a_retirar(0.1 + 0.2), 0.3)
        self.assertEqual(dominio.monto_a_retirar(1000.0), 1000.0)

    def test_en_ausencia_es_por_numero_de_usuario(self):
        self.assertFalse(cajas_repo.cerrada_en_ausencia(None, 4))
        self.assertFalse(cajas_repo.cerrada_en_ausencia({"responsable_id": 3, "responsable": "Lucia"}, 3))
        self.assertTrue(cajas_repo.cerrada_en_ausencia({"responsable_id": 3, "responsable": "Lucia"}, 4))


class _BaseDeLaCaja(BaseConBaseTemporal):
    def setUp(self):
        super().setUp()
        self.admin_id = usuarios_repo.crear_usuario("Dueño", "1234", dominio.ROL_ADMIN)
        self.lucia_id = usuarios_repo.crear_usuario("Lucia", "1234", dominio.ROL_EMPLEADA)
        self.gaby_id = usuarios_repo.crear_usuario("Gaby", "1234", dominio.ROL_EMPLEADA)
        articulos_repo.crear_articulo("COD1", "Caramelo", None, None, 0.1, 0.05, 0)
        compras_repo.registrar_compra(self.admin_id, [{"codigo": "COD1", "cantidad": 100, "costo_unitario": 0.05}])

    def _vender(self, usuario_id, momento, monto, metodo=dominio.PAGO_EFECTIVO):
        with mock.patch("repositories.ventas_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = momento
            return ventas_repo.confirmar_venta(
                usuario_id,
                [{"codigo": "COD1", "descripcion": "Caramelo", "cantidad": 1, "precio_unitario": monto}],
                [{"metodo": metodo, "monto": monto}],
            )

    def _turno_con_centavos(self, usuario_id, desde_hora=9):
        """Tres caramelos de $ 0,10 (SQLite los suma con cola: 0.30000000000000004),
        $ 1.000 en efectivo y $ 600 digital."""
        for minuto in range(3):
            self._vender(usuario_id, _a_las(desde_hora, minuto), 0.1)
        self._vender(usuario_id, _a_las(desde_hora + 1), 1000.0)
        self._vender(usuario_id, _a_las(desde_hora + 2), 600.0, dominio.PAGO_DIGITAL)

    def _grabado(self, cierre_id):
        with conexion_db() as conexion:
            return conexion.execute("SELECT * FROM cierres_turno WHERE id = ?", (cierre_id,)).fetchone()

    def _datos_del_envio(self, cierre_id):
        with conexion_db() as conexion:
            return envio_pwa_repo.datos_del_cierre(conexion, cierre_id)

    def _ventana(self, ventana):
        self.addCleanup(ventana.deleteLater)
        return ventana


class TestElMismoMontoARetirarEnTodosLados(_BaseDeLaCaja):
    def setUp(self):
        super().setUp()
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))
        self._turno_con_centavos(self.lucia_id)

    def test_lo_que_se_ve_antes_de_cerrar_es_lo_que_se_graba_y_lo_que_viaja(self):
        en_curso = turnos_repo.resumen_turno_actual()

        cierre = turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(14, 0))

        self.assertEqual(en_curso["monto_a_retirar"], 1000.3)
        self.assertEqual(en_curso["ventas_total"], 1600.3)
        resumen = turnos_repo.detalle_cierre(cierre["id"])["resumen"]
        datos = self._datos_del_envio(cierre["id"])
        for de_donde, monto in (
            ("cerrar_turno", cierre["monto_a_retirar"]),
            ("cierres_turno", self._grabado(cierre["id"])["monto_a_retirar"]),
            ("detalle_cierre", resumen["monto_a_retirar"]),
            ("listar_cierres", turnos_repo.listar_cierres()[0]["monto_a_retirar"]),
            ("app de gastos", datos["detalle"]["aRetirar"]),
        ):
            with self.subTest(de_donde=de_donde):
                self.assertEqual(monto, en_curso["monto_a_retirar"])
        self.assertEqual((resumen["ventas_total"], datos["importe"]), (1600.3, 1600.3))

    def test_caja_y_cierre_de_turno_muestran_el_monto_a_retirar_del_repo(self):
        # Con un monto distinto del efectivo cobrado: si una pantalla lo calculara
        # por su cuenta, no mostraría este.
        resumen = {**turnos_repo.resumen_turno_actual(), "monto_a_retirar": 1234.0}

        with mock.patch.object(turnos_repo, "resumen_turno_actual", return_value=resumen):
            caja = self._ventana(CajaWindow())
            cierre = self._ventana(CierreTurnoWindow(usuarios_repo.obtener_usuario(self.lucia_id)))

        self.assertEqual(caja.valor_actual.text(), "$ 1.234")
        self.assertEqual(cierre.tarjeta.valor_retirar.text(), "$ 1.234")
        # La tabla sigue mostrando lo cobrado en efectivo.
        self.assertEqual(cierre.tarjeta.valor_efectivo.text(), formato_pesos(resumen["ventas_efectivo"]))

    def test_un_cierre_hecho_se_ve_y_viaja_con_el_monto_a_retirar_grabado(self):
        cierre = turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(14, 0))
        with conexion_db() as conexion:
            conexion.execute("UPDATE cierres_turno SET monto_a_retirar = 999.0 WHERE id = ?", (cierre["id"],))

        control = self._ventana(ControlCierresWindow(usuarios_repo.obtener_usuario(self.admin_id)))
        detalle = self._ventana(DialogoDetalleCierre(turnos_repo.listar_cierres()[0]))
        datos = self._datos_del_envio(cierre["id"])

        self.assertEqual(control.tabla.item(0, _COLUMNA_A_RETIRAR).text(), "$ 999")
        self.assertEqual(detalle.tarjeta.valor_retirar.text(), "$ 999")
        self.assertEqual((datos["detalle"]["aRetirar"], datos["efectivo"]), (999.0, 1000.3))

    def test_la_lista_de_envios_muestra_el_mismo_total_que_viaja(self):
        cierre = turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(14, 0))
        envio_pwa_repo.mandar_cierre(self.admin_id, cierre["id"])

        ultimo = envio_pwa_repo.estado()["ultimos"][0]

        self.assertEqual(ultimo["total"], self._datos_del_envio(cierre["id"])["importe"])
        self.assertEqual(ultimo["total"], 1600.3)


class TestElRelevoAnunciaElMismoSobre(_BaseDeLaCaja):
    def test_la_que_llega_ve_el_sobre_que_despues_graba_el_cierre(self):
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))
        self._turno_con_centavos(self.lucia_id)

        situacion = relevo_repo.situacion_al_entrar(self.gaby_id, _a_las(13, 56))
        cierre = relevo_repo.cerrar_para_entrar(self.gaby_id, relevo_repo.SITUACION_CERRAR_LA_DE_OTRA, _a_las(13, 56))

        self.assertEqual(situacion["a_retirar"], cierre["monto_a_retirar"])
        self.assertEqual(situacion["a_retirar"], self._grabado(cierre["id"])["monto_a_retirar"])

    def test_las_ventas_sin_caja_anuncian_el_sobre_que_graba_su_cierre(self):
        self._turno_con_centavos(self.admin_id, desde_hora=2)   # el Admin, sin nadie en el mostrador

        situacion = relevo_repo.situacion_al_entrar(self.lucia_id, _a_las(5, 55))
        cierre = relevo_repo.cerrar_para_entrar(self.lucia_id, relevo_repo.SITUACION_VENTAS_SIN_CAJA, _a_las(5, 55))

        self.assertEqual((situacion["a_retirar"], cierre["monto_a_retirar"]), (1000.3, 1000.3))

    def test_el_cartel_de_las_ventas_sin_caja_dice_de_quien_son(self):
        self._vender(self.admin_id, _a_las(2, 36), 1500.0)
        self._vender(self.admin_id, _a_las(4, 50), 500.0)

        with mock.patch.object(ingreso_caja, "confirmar", return_value=False) as pregunta:
            self.assertFalse(resolver_caja_al_entrar(None, usuarios_repo.obtener_usuario(self.lucia_id)))

        texto = pregunta.call_args[0][2]
        self.assertIn("Hay 2 ventas sin cerrar desde el 05/01 02:36, hechas sin una caja abierta "
                      "(del Administrador, sin nadie en el mostrador).", texto)
        self.assertNotIn("antes de las cajas", texto)


class TestCoincideConLaMismaReglaEnCadaPantalla(_BaseDeLaCaja):
    def _tres_cierres_contados(self, sobrante_de_cada_uno):
        """Tres cajas de Lucía (Mañana, Tarde y Noche del lunes), cada una con $ 1.000
        en efectivo y con el sobre contado con ese sobrante (negativo: faltante)."""
        # La primera se abre contando; las otras dos, sin contar (las cerró ella).
        turnos = ((_a_las(5, 55), 50000.0, _a_las(9), _a_las(14, 0)),
                  (_a_las(14, 1), None, _a_las(15), _a_las(22, 0)),
                  (_a_las(22, 1), None, _a_las(23), _a_las(5, 50, MARTES)))
        for (abre, contado, vende, cierra), sobrante in zip(turnos, sobrante_de_cada_uno, strict=True):
            relevo_repo.abrir_caja(self.lucia_id, contado, abre)
            self._vender(self.lucia_id, vende, 1000.0)
            cierre = turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=cierra)
            turnos_repo.verificar_cierre(cierre["id"], cierre["monto_a_retirar"] + sobrante, self.admin_id)

    def test_control_de_cierres_pinta_de_rojo_un_centavo_de_diferencia(self):
        self._tres_cierres_contados((0.01, 0.0, -0.01))

        control = self._ventana(ControlCierresWindow(usuarios_repo.obtener_usuario(self.admin_id)))

        # La tabla va del más nuevo al más viejo: Noche, Tarde, Mañana.
        for fila, texto, rojo in ((0, "$ -0,01", True), (1, "$ 0", False), (2, "$ 0,01", True)):
            item = control.tabla.item(fila, _COLUMNA_DIFERENCIA)
            with self.subTest(fila=fila):
                self.assertEqual(item.text(), texto)
                self.assertEqual(_pintada_de(item, Qt.red), rojo)
        # Y el detalle del mismo cierre lo dice igual.
        detalle = self._ventana(DialogoDetalleCierre(control.cierres[2]))
        self.assertIn("(sobran $ 0,01)", detalle.encabezado.text())

    def test_el_resumen_del_dia_pinta_de_rojo_solo_lo_que_falta(self):
        self._tres_cierres_contados((-0.01, 0.01, 0.0))

        pestaña = self._ventana(PestañaResumenDelDia())
        pestaña.fecha.setDate(QDate(LUNES.year, LUNES.month, LUNES.day))

        columna = pestaña.tabla.columnCount() - 1
        for fila, texto, rojo in ((0, "$ -0,01", True), (1, "$ 0,01", False), (2, "$ 0", False)):
            item = pestaña.tabla.item(fila, columna)
            with self.subTest(fila=fila):
                self.assertEqual(item.text(), texto)
                self.assertEqual(_pintada_de(item, _ROJO_DEL_RESUMEN), rojo)

    def test_al_contar_la_cola_del_punto_flotante_coincide_y_un_centavo_no(self):
        for esperado, contado, texto, color in (
            (0.1 + 0.2, 0.3, "coincide", "#1E7B45"),
            (1000.0, 1000.01, "sobran $ 0,01", "#A6323C"),
            (1000.0, 999.99, "faltan $ 0,01", "#A6323C"),
        ):
            dialogo = self._ventana(DialogoContarPlata(None, "Contar", "Contá:", esperado))
            dialogo.spin_monto.setValue(contado)
            dialogo._listo()
            with self.subTest(esperado=esperado, contado=contado):
                self.assertIn(f": {texto}.", dialogo.resultado.text())
                self.assertIn(color, dialogo.resultado.styleSheet())

    def test_la_apertura_en_control_de_cierres_usa_la_misma_diferencia(self):
        relevo_repo.abrir_caja(self.lucia_id, 49500.0, _a_las(5, 55))
        turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(14, 0))
        relevo_repo.abrir_caja(self.gaby_id, 49500.01, _a_las(14, 2))
        turnos_repo.cerrar_turno(self.gaby_id, ahora_dt=_a_las(22, 0))

        tarde, manana = turnos_repo.listar_cierres()

        self.assertEqual(texto_de_la_apertura(manana), "05:55 · contó $ 49.500 (faltan $ 500)")
        self.assertEqual(texto_de_la_apertura(tarde), "14:02 · contó $ 49.500,01 (sobran $ 0,01)")


class TestEnAusenciaPorNumeroDeUsuario(_BaseDeLaCaja):
    def _cerrar_desde_la_pantalla(self, usuario):
        """Cierre de Turno con la pantalla de todos los días; devuelve el cartel final."""
        ventana = self._ventana(CierreTurnoWindow(usuario))
        with mock.patch.object(caja_window, "confirmar", return_value=True), \
                mock.patch.object(caja_window, "mostrar_info") as aviso:
            ventana._cerrar_turno()
        return aviso.call_args[0][2]

    def _dice_lo_mismo_que_control_de_cierres(self, cierre, en_ausencia):
        guardado = turnos_repo.listar_cierres()[0]
        self.assertEqual((cierre["cerrada_en_ausencia"], guardado["cerrada_en_ausencia"]), (en_ausencia, en_ausencia))

    def test_lo_que_devuelve_el_cierre_dice_lo_mismo_que_control_de_cierres(self):
        relevo_repo.abrir_caja(self.lucia_id, 50000.0, _a_las(5, 55))
        la_suya = turnos_repo.cerrar_turno(self.lucia_id, ahora_dt=_a_las(14, 0))
        self._dice_lo_mismo_que_control_de_cierres(la_suya, False)

        relevo_repo.abrir_caja(self.lucia_id, None, _a_las(14, 0))
        la_cierra_el_admin = turnos_repo.cerrar_turno(self.admin_id, ahora_dt=_a_las(21, 0))
        self._dice_lo_mismo_que_control_de_cierres(la_cierra_el_admin, True)

        relevo_repo.abrir_caja(self.gaby_id, 50000.0, _a_las(22, 1))
        forzoso = relevo_repo.cierre_forzoso_si_corresponde(_a_las(6, 30, MARTES))
        self._dice_lo_mismo_que_control_de_cierres(forzoso, False)

        self._vender(self.admin_id, _a_las(7, 0, MARTES), 500.0)
        sin_caja = relevo_repo.cerrar_para_entrar(
            self.lucia_id, relevo_repo.SITUACION_VENTAS_SIN_CAJA, _a_las(7, 5, MARTES)
        )
        self._dice_lo_mismo_que_control_de_cierres(sin_caja, False)

    def test_si_le_cambiaron_el_nombre_con_la_sesion_abierta_no_dice_en_ausencia(self):
        # Lucía entró antes de que el Admin le corrigiera el nombre (desde otra PC):
        # su sesión sigue con el nombre viejo, pero la caja es suya.
        lucia = usuarios_repo.obtener_usuario(self.lucia_id)
        relevo_repo.abrir_caja(self.lucia_id, 50000.0)
        usuarios_repo.modificar_usuario(self.lucia_id, "Lucia G", dominio.ROL_EMPLEADA)

        cartel = self._cerrar_desde_la_pantalla(lucia)

        self.assertNotIn("en ausencia", cartel)
        self.assertFalse(turnos_repo.listar_cierres()[0]["cerrada_en_ausencia"])

    def test_con_dos_usuarias_del_mismo_nombre_dice_en_ausencia_de_la_otra(self):
        # La Lucía empleada dejó su caja abierta y se la dio de baja; ahora hay otra
        # Lucía, Administradora, que cierra esa caja.
        relevo_repo.abrir_caja(self.lucia_id, 50000.0)
        usuarios_repo.desactivar_usuario(self.lucia_id)
        otra_lucia = usuarios_repo.obtener_usuario(usuarios_repo.crear_usuario("Lucia", "1234", dominio.ROL_ADMIN))

        cartel = self._cerrar_desde_la_pantalla(otra_lucia)

        self.assertIn("Queda anotado que la cerraste vos, en ausencia de Lucia.", cartel)
        guardado = turnos_repo.listar_cierres()[0]
        self.assertTrue(guardado["cerrada_en_ausencia"])
        self.assertTrue(texto_del_cierre(guardado).startswith("Lucia, en ausencia de Lucia"))


if __name__ == "__main__":
    unittest.main()
