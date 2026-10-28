"""
tests/test_config_repo.py
==========================
Dos pedazos de SQL que estaban copiados y hoy viven en un solo lugar:

- La tabla `configuracion`: config_repo.leer y config_repo.guardar (con la
  clave que no está, el UPDATE que no la crea y la conexión de quien llama), el
  Cambio Fijo (obtener_fondo_cambio / actualizar_fondo_cambio) y lo que hace
  cada repo que guarda algo ahí cuando su clave falta.
- El efectivo y el digital de cada venta
  (turnos_ventas_repo._efectivo_y_digital_de_cada_venta): una venta cobrada en
  los dos medios dice lo mismo en el detalle del día, en Reportes > Por
  Operador y en el reparto de las impresiones de Caja y Cierre de Turno.

Se ejecutan con:

    python -m unittest discover tests
"""

import re
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import database
import dominio
from database import conexion_db
from repositories import (
    admin_remoto_repo, articulos_repo, config_repo, copias_repo, detalle_dia_repo, envio_pwa_repo,
    relevo_repo, reportes_repo, turnos_repo, turnos_ventas_repo, usuarios_repo, ventas_repo,
)
from turnos import dia_en_que_empezo_el_turno
from base import BaseConBaseTemporal

RAIZ = Path(__file__).resolve().parent.parent

EF = dominio.PAGO_EFECTIVO
DIG = dominio.PAGO_DIGITAL


def _leer_por_fuera(clave):
    """Lo que ve otra conexión (lo ya grabado con commit)."""
    with conexion_db() as conexion:
        return config_repo.leer(conexion, clave)


def _borrar_clave(clave):
    with conexion_db() as conexion:
        conexion.execute("DELETE FROM configuracion WHERE clave = ?", (clave,))


def _archivos_del_programa():
    """Los .py del programa: los de la raíz y los de sus paquetes (repositories,
    ui, admin_remoto...). Sin las pruebas, que no son un paquete, ni las
    carpetas de datos o del .exe."""
    yield from RAIZ.glob("*.py")
    for paquete in RAIZ.glob("*/__init__.py"):
        yield from paquete.parent.rglob("*.py")


class TestLeerYGuardar(BaseConBaseTemporal):
    def test_una_clave_que_no_esta_da_none(self):
        self.assertIsNone(_leer_por_fuera("no_existe"))

    def test_guardar_crea_la_clave_y_la_segunda_vez_la_pisa(self):
        with conexion_db() as conexion:
            config_repo.guardar(conexion, "de_prueba", "uno")
        self.assertEqual(_leer_por_fuera("de_prueba"), "uno")

        with conexion_db() as conexion:
            config_repo.guardar(conexion, "de_prueba", "dos")
        self.assertEqual(_leer_por_fuera("de_prueba"), "dos")
        with conexion_db() as conexion:
            cantidad = conexion.execute(
                "SELECT COUNT(*) FROM configuracion WHERE clave = 'de_prueba'").fetchone()[0]
        self.assertEqual(cantidad, 1)

    def test_sin_crear_solo_cambia_una_clave_que_ya_esta(self):
        with conexion_db() as conexion:
            config_repo.guardar(conexion, "de_prueba", "uno", crear_si_falta=False)
        self.assertIsNone(_leer_por_fuera("de_prueba"))

        with conexion_db() as conexion:
            config_repo.guardar(conexion, "de_prueba", "uno")
            config_repo.guardar(conexion, "de_prueba", "dos", crear_si_falta=False)
        self.assertEqual(_leer_por_fuera("de_prueba"), "dos")

    def test_lee_y_graba_con_la_transaccion_de_quien_llama(self):
        # Dentro de la transacción se ve lo que ya grabó; otra conexión todavía
        # no, y si la operación falla no queda nada (guardar no hace commit).
        with self.assertRaises(RuntimeError):
            with conexion_db() as conexion:
                config_repo.guardar(conexion, "de_prueba", "uno")
                self.assertEqual(config_repo.leer(conexion, "de_prueba"), "uno")
                self.assertIsNone(_leer_por_fuera("de_prueba"))
                raise RuntimeError("se cortó a mitad de la operación")
        self.assertIsNone(_leer_por_fuera("de_prueba"))

    def test_el_envio_a_la_app_pregunta_con_la_conexion_del_cierre(self):
        # encolar corre dentro de la transacción de cerrar_turno: lo que pregunta
        # tiene que ser lo de ESA conexión.
        with conexion_db() as conexion:
            config_repo.guardar(conexion, envio_pwa_repo._CLAVE_ACTIVADO, "1")
            self.assertTrue(envio_pwa_repo._activado(conexion))
            self.assertFalse(envio_pwa_repo.esta_activado())
            conexion.rollback()


class TestCambioFijo(BaseConBaseTemporal):
    def test_una_base_nueva_arranca_con_50000(self):
        self.assertEqual(_leer_por_fuera(database.CLAVE_FONDO_CAMBIO), "50000")
        self.assertEqual(config_repo.obtener_fondo_cambio(), 50000.0)

    def test_se_guarda_redondeado_a_centavos(self):
        config_repo.actualizar_fondo_cambio(1234.567)

        self.assertEqual(_leer_por_fuera(database.CLAVE_FONDO_CAMBIO), "1234.57")
        self.assertEqual(config_repo.obtener_fondo_cambio(), 1234.57)

    def test_un_monto_redondo_vuelve_igual(self):
        config_repo.actualizar_fondo_cambio(30000.0)

        self.assertEqual(config_repo.obtener_fondo_cambio(), 30000.0)

    def test_sin_la_clave_da_cero_y_cambiarlo_no_la_crea(self):
        _borrar_clave(database.CLAVE_FONDO_CAMBIO)

        self.assertEqual(config_repo.obtener_fondo_cambio(), 0.0)
        config_repo.actualizar_fondo_cambio(1000.0)
        self.assertIsNone(_leer_por_fuera(database.CLAVE_FONDO_CAMBIO))
        self.assertEqual(config_repo.obtener_fondo_cambio(), 0.0)

    def test_volver_a_inicializar_no_pisa_lo_que_cambio_el_admin(self):
        config_repo.actualizar_fondo_cambio(42000.0)

        database.inicializar_base_de_datos()

        self.assertEqual(config_repo.obtener_fondo_cambio(), 42000.0)


class TestCadaRepoConSuClave(BaseConBaseTemporal):
    """Qué hace cada repo que guarda algo en `configuracion` si su clave no
    está o tiene algo raro (lo mismo que hacía con su propio SQL)."""

    def setUp(self):
        super().setUp()
        self.admin_id = usuarios_repo.listar_usuarios()[0]["id"]

    def test_entrar_desde_otra_pc(self):
        self.assertFalse(admin_remoto_repo.esta_activo())
        admin_remoto_repo.activar(self.admin_id, True)
        self.assertTrue(admin_remoto_repo.esta_activo())
        admin_remoto_repo.activar(self.admin_id, False)
        self.assertEqual(_leer_por_fuera(admin_remoto_repo._CLAVE_ACTIVO), "0")
        self.assertFalse(admin_remoto_repo.esta_activo())

    def test_las_otras_carpetas_de_las_copias(self):
        self.assertEqual(copias_repo.carpetas_extra(), [])
        for raro in ("", "no es json", '{"una": "carpeta"}'):
            with conexion_db() as conexion:
                config_repo.guardar(conexion, copias_repo._CLAVE_CARPETAS_EXTRA, raro)
            self.assertEqual(copias_repo.carpetas_extra(), [], raro)

        copias_repo._guardar_carpetas_extra(["D:\\BACKUPS", "E:\\OTRA"])
        self.assertEqual(copias_repo.carpetas_extra(), ["D:\\BACKUPS", "E:\\OTRA"])

    def test_el_envio_a_la_app_de_gastos(self):
        self.assertFalse(envio_pwa_repo.esta_activado())
        envio_pwa_repo.activar(self.admin_id, True)
        self.assertTrue(envio_pwa_repo.esta_activado())
        envio_pwa_repo.activar(self.admin_id, False)
        self.assertEqual(_leer_por_fuera(envio_pwa_repo._CLAVE_ACTIVADO), "0")

        self.addCleanup(envio_pwa_repo._olvidar_sesion)  # el token queda en memoria
        self.assertIsNone(envio_pwa_repo._leer_renovacion())
        envio_pwa_repo._guardar_sesion("token", 3600, "")
        self.assertIsNone(envio_pwa_repo._leer_renovacion())  # vacía es como no tenerla
        envio_pwa_repo._guardar_sesion("token", 3600, "renovacion-1")
        self.assertEqual(envio_pwa_repo._leer_renovacion(), "renovacion-1")


class TestElSqlDeConfiguracionEstaEnUnSoloLugar(unittest.TestCase):
    def test_solo_config_repo_y_la_siembra_tocan_la_tabla(self):
        patron = re.compile(r"\b(FROM|INTO|UPDATE)\s+configuracion\b", re.IGNORECASE)
        permitidos = {"repositories/config_repo.py", "database.py"}
        encontrados = sorted(
            archivo.relative_to(RAIZ).as_posix() for archivo in _archivos_del_programa()
            if patron.search(archivo.read_text(encoding="utf-8"))
        )
        self.assertEqual([a for a in encontrados if a not in permitidos], [],
                         "Usá config_repo.leer / config_repo.guardar")

    def test_la_clave_del_cambio_fijo_se_escribe_una_sola_vez(self):
        # En los dos archivos que tocan la tabla. En el resto "fondo_cambio" es
        # el nombre de una columna o de una clave del resumen, no la de esta tabla.
        veces = {
            nombre: len(re.findall(r"""["']fondo_cambio["']""", (RAIZ / nombre).read_text(encoding="utf-8")))
            for nombre in ("database.py", "repositories/config_repo.py")
        }
        self.assertEqual(veces, {"database.py": 1, "repositories/config_repo.py": 0})


class TestEfectivoYDigitalDeCadaVenta(BaseConBaseTemporal):
    """Lucía vende impresiones cobradas $ 600 en efectivo y $ 400 en digital,
    una Coca pagada con dos pagos en efectivo, un regalo de $ 0 sin pagos, y una
    venta de impresiones repartida que se anula. Se cierra el turno."""

    def setUp(self):
        super().setUp()
        self.admin_id = usuarios_repo.listar_usuarios()[0]["id"]
        self.lucia_id = usuarios_repo.crear_usuario("LUCIA", "4321", dominio.ROL_EMPLEADA)
        articulos_repo.crear_articulo(dominio.CODIGO_ARTICULO_IMPRESIONES, "IMPRESIONES", None, None, 100.0, 0.0, 0)
        articulos_repo.crear_articulo("COCA", "Coca 500", None, None, 1000.0, 500.0, 0)
        articulos_repo.crear_articulo("REGALO", "Regalo", None, None, 0.0, 0.0, 0)

        relevo_repo.abrir_caja(self.lucia_id, cambio_contado=50000.0)
        self.mezclada = self._vender(dominio.CODIGO_ARTICULO_IMPRESIONES, 10, 100.0, [(EF, 600.0), (DIG, 400.0)])
        self.dos_en_efectivo = self._vender("COCA", 1, 1000.0, [(EF, 300.0), (EF, 700.0)])
        self.sin_pagos = self._vender("REGALO", 1, 0.0, [])
        self.anulada = self._vender(dominio.CODIGO_ARTICULO_IMPRESIONES, 5, 100.0, [(EF, 200.0), (DIG, 300.0)])
        ventas_repo.anular_venta(self.anulada, self.admin_id, "mal cobrada")
        turnos_repo.cerrar_turno(self.lucia_id)
        self.dia = turnos_repo.listar_cierres()[0]["fecha"]

        self.esperado = {
            self.mezclada: (600.0, 400.0),
            self.dos_en_efectivo: (1000.0, 0.0),
            self.sin_pagos: (0.0, 0.0),
            self.anulada: (200.0, 300.0),  # anular no borra sus pagos
        }

    def _vender(self, codigo, cantidad, precio, pagos):
        return ventas_repo.confirmar_venta(
            self.lucia_id,
            [{"codigo": codigo, "descripcion": codigo, "cantidad": cantidad, "precio_unitario": precio}],
            [{"metodo": metodo, "monto": monto} for metodo, monto in pagos],
        )

    def _ventas_de_lucia(self):
        # El "hoy" de las pruebas de reportes es el día del local (ver CLAUDE.md).
        hoy = dia_en_que_empezo_el_turno(datetime.now())
        return reportes_repo.ventas_de_operador(
            self.lucia_id, (hoy - timedelta(days=1)).isoformat(), (hoy + timedelta(days=1)).isoformat())

    def test_el_detalle_del_dia_trae_lo_de_cada_medio(self):
        detalle = detalle_dia_repo.detalle_del_dia(self.dia)
        ventas = {venta["id"]: (venta["efectivo"], venta["digital"]) for venta in detalle["ventas"]}

        self.assertEqual(ventas, self.esperado)
        self.assertEqual((detalle["totales"]["efectivo"], detalle["totales"]["digital"]), (1600.0, 400.0))
        lucia = next(fila for fila in detalle["por_operador"] if fila["operador"] == "LUCIA")
        self.assertEqual((lucia["efectivo"], lucia["digital"]), (1600.0, 400.0))

    def test_por_operador_trae_lo_mismo_que_el_detalle(self):
        ventas = {venta["id"]: (venta["efectivo"], venta["digital"]) for venta in self._ventas_de_lucia()}

        self.assertEqual(ventas, self.esperado)

    def test_las_ventas_de_un_operador_suman_lo_mismo_que_su_resumen(self):
        confirmadas = [venta for venta in self._ventas_de_lucia() if venta["estado"] == dominio.VENTA_CONFIRMADA]
        hoy = dia_en_que_empezo_el_turno(datetime.now())
        resumen = next(
            fila for fila in reportes_repo.resumen_por_operador(
                (hoy - timedelta(days=1)).isoformat(), (hoy + timedelta(days=1)).isoformat())
            if fila["usuario_id"] == self.lucia_id
        )

        self.assertEqual(round(sum(venta["efectivo"] for venta in confirmadas), 2), resumen["efectivo"])
        self.assertEqual(round(sum(venta["digital"] for venta in confirmadas), 2), resumen["digital"])

    def test_el_reparto_de_las_impresiones_usa_los_mismos_pagos(self):
        # Solo la venta mezclada tiene impresiones y no está anulada: se reparten
        # justo como se cobró.
        with conexion_db() as conexion:
            aparte = turnos_ventas_repo._aparte_por_metodo(conexion, "2000-01-01", "2100-01-01")
        self.assertEqual(aparte["impresiones"], {EF: 600.0, DIG: 400.0})

        # Y así lo muestra "Ver Detalle" del cierre en Control de Cierres.
        resumen = turnos_repo.detalle_cierre(turnos_repo.listar_cierres()[0]["id"])["resumen"]
        self.assertEqual((resumen["impresiones_efectivo"], resumen["impresiones_digital"]), (600.0, 400.0))

    def test_los_pagos_de_cada_venta_se_buscan_por_su_indice(self):
        pagos, parametros = turnos_ventas_repo._efectivo_y_digital_de_cada_venta()
        with conexion_db() as conexion:
            plan = " ".join(
                str(tuple(fila)) for fila in conexion.execute(f"EXPLAIN QUERY PLAN SELECT {pagos} FROM ventas",
                                                              parametros)
            )
        # Una búsqueda por el índice para el efectivo y otra para el digital.
        self.assertEqual(plan.count("idx_venta_pagos_venta"), 2, plan)

    def test_la_cuenta_esta_escrita_una_sola_vez(self):
        patron = re.compile(r"FROM\s+venta_pagos\s+WHERE\s+(venta_pagos\.)?venta_id\s*=\s*ventas\.id", re.IGNORECASE)
        encontrados = sorted(
            archivo.relative_to(RAIZ).as_posix() for archivo in _archivos_del_programa()
            if patron.search(archivo.read_text(encoding="utf-8"))
        )
        self.assertEqual(encontrados, ["repositories/turnos_ventas_repo.py"],
                         "Usá turnos_ventas_repo._efectivo_y_digital_de_cada_venta")


if __name__ == "__main__":
    unittest.main()
