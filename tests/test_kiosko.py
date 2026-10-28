"""
tests/test_kiosko.py
======================
Tests de las reglas de negocio más sensibles del sistema: las que
tocan plata y stock (turnos, ventas, anulaciones), la protección del
borrado de artículos, y la migración de contraseñas al formato con
salt. Todos corren contra una base de datos SQLite temporal — nunca
contra data_fr/kiosko.db — así se pueden correr las veces que haga falta
sin riesgo de tocar datos reales.

Se ejecutan con:

    python -m unittest discover tests
"""

import hashlib
import unittest
from datetime import date, datetime, timedelta
from unittest import mock

import database
import dominio
import turnos
from repositories import (
    articulos_repo, compras_repo, reportes_repo, turnos_repo, usuarios_repo,
    ventas_repo,
)
from base import BaseConBaseTemporal


class TestCalcularTurno(unittest.TestCase):
    def test_manana_empieza_a_las_6(self):
        self.assertEqual(turnos.calcular_turno(datetime(2026, 1, 1, 6, 0)), "MAÑANA")

    def test_manana_hasta_las_13_59(self):
        self.assertEqual(turnos.calcular_turno(datetime(2026, 1, 1, 13, 59)), "MAÑANA")

    def test_tarde_empieza_a_las_14(self):
        self.assertEqual(turnos.calcular_turno(datetime(2026, 1, 1, 14, 0)), "TARDE")

    def test_tarde_hasta_las_21_59(self):
        self.assertEqual(turnos.calcular_turno(datetime(2026, 1, 1, 21, 59)), "TARDE")

    def test_noche_empieza_a_las_22(self):
        self.assertEqual(turnos.calcular_turno(datetime(2026, 1, 1, 22, 0)), "NOCHE")

    def test_noche_cruza_la_medianoche(self):
        self.assertEqual(turnos.calcular_turno(datetime(2026, 1, 1, 0, 0)), "NOCHE")
        self.assertEqual(turnos.calcular_turno(datetime(2026, 1, 1, 5, 59)), "NOCHE")

    # El 2026-01-04 es domingo, el 2026-01-03 es sábado (usados también en
    # TestEtiquetaTurno / TestTurnoVencimiento / TestTurnosFaltantes).
    def test_domingo_manana_dura_hasta_las_18(self):
        self.assertEqual(turnos.calcular_turno(datetime(2026, 1, 4, 17, 59)), "MAÑANA")

    def test_domingo_no_existe_el_turno_tarde(self):
        # A las 14:00, un día de semana normal ya sería Tarde.
        self.assertEqual(turnos.calcular_turno(datetime(2026, 1, 4, 14, 0)), "MAÑANA")

    def test_domingo_noche_empieza_a_las_18(self):
        self.assertEqual(turnos.calcular_turno(datetime(2026, 1, 4, 18, 0)), "NOCHE")

    def test_sabado_a_la_noche_sigue_siendo_el_turno_normal(self):
        self.assertEqual(turnos.calcular_turno(datetime(2026, 1, 3, 22, 0)), "NOCHE")


class TestEtiquetaTurno(unittest.TestCase):
    def test_dia_de_semana_usa_los_nombres_normales(self):
        lunes = date(2026, 1, 5)
        self.assertEqual(turnos.etiqueta_turno(lunes, "MAÑANA"), "Mañana")
        self.assertEqual(turnos.etiqueta_turno(lunes, "TARDE"), "Tarde")
        self.assertEqual(turnos.etiqueta_turno(lunes, "NOCHE"), "Noche")

    def test_domingo_usa_las_etiquetas_de_2_turnos(self):
        domingo = date(2026, 1, 4)
        self.assertEqual(turnos.etiqueta_turno(domingo, "MAÑANA"), "Domingo T1")
        self.assertEqual(turnos.etiqueta_turno(domingo, "NOCHE"), "Domingo T2")


class TestTurnosDelDia(unittest.TestCase):
    """`turnos_del_dia` es el único lugar donde se decide qué turnos
    existen en un día; antes esa lista estaba escrita a mano en
    turnos_repo."""

    def test_dia_de_semana_tiene_los_tres_turnos(self):
        lunes = date(2026, 1, 5)
        self.assertEqual(
            turnos.turnos_del_dia(lunes),
            (dominio.TURNO_MANANA, dominio.TURNO_TARDE, dominio.TURNO_NOCHE),
        )

    def test_domingo_tiene_solo_dos_turnos_y_sin_tarde(self):
        domingo = date(2026, 1, 4)
        turnos_domingo = turnos.turnos_del_dia(domingo)
        self.assertEqual(turnos_domingo, (dominio.TURNO_MANANA, dominio.TURNO_NOCHE))
        self.assertNotIn(dominio.TURNO_TARDE, turnos_domingo)

    def test_acepta_string_igual_que_es_domingo(self):
        self.assertEqual(turnos.turnos_del_dia("2026-01-04"), dominio.TURNOS_DOMINGO)


class TestSubtotalDeLinea(unittest.TestCase):
    """El subtotal de un renglón se calcula en un solo lugar
    (`ventas_repo.subtotal_linea`), y `confirmar_venta` lo usa en vez de
    confiar en lo que le manda la pantalla."""

    def test_subtotal_es_cantidad_por_precio(self):
        linea = {"cantidad": 3, "precio_unitario": 100.0}
        self.assertEqual(ventas_repo.subtotal_linea(linea), 300.0)

    def test_total_del_carrito_suma_todos_los_renglones(self):
        carrito = [
            {"cantidad": 3, "precio_unitario": 100.0},
            {"cantidad": 2, "precio_unitario": 50.5},
        ]
        self.assertEqual(ventas_repo.total_carrito(carrito), 401.0)

    def test_carrito_vacio_da_cero(self):
        self.assertEqual(ventas_repo.total_carrito([]), 0)








class TestEsAdmin(unittest.TestCase):
    def test_reconoce_el_rol_admin_y_rechaza_el_resto(self):
        self.assertTrue(dominio.es_admin({"rol": dominio.ROL_ADMIN}))
        self.assertFalse(dominio.es_admin({"rol": dominio.ROL_EMPLEADA}))
        self.assertFalse(dominio.es_admin(None))


class TestTurnoVencimiento(unittest.TestCase):
    """El turno vence (y la caja se cierra sola) 30 minutos después de su fin
    (pedido del dueño, 2026-10-20; desde el 2026-10-18 eran 15, y antes 40)."""

    def test_manana_vence_a_las_14_30_entre_semana(self):
        lunes = date(2026, 1, 5)
        self.assertEqual(turnos.turno_vencimiento(lunes, "MAÑANA"), datetime(2026, 1, 5, 14, 30))

    def test_manana_vence_a_las_18_30_el_domingo(self):
        domingo = date(2026, 1, 4)
        self.assertEqual(turnos.turno_vencimiento(domingo, "MAÑANA"), datetime(2026, 1, 4, 18, 30))

    def test_noche_vence_a_la_madrugada_del_dia_siguiente(self):
        lunes = date(2026, 1, 5)
        self.assertEqual(turnos.turno_vencimiento(lunes, "NOCHE"), datetime(2026, 1, 6, 6, 30))

    def test_la_tarde_vence_a_las_22_30(self):
        lunes = date(2026, 1, 5)
        self.assertEqual(turnos.turno_vencimiento(lunes, "TARDE"), datetime(2026, 1, 5, 22, 30))


class TestAvisoDeCierre(unittest.TestCase):
    """El botón Cierre de Turno titila desde 5 minutos antes del fin del turno."""

    def test_la_manana_avisa_desde_las_13_55(self):
        self.assertEqual(turnos.inicio_del_aviso_de_cierre(date(2026, 1, 5), "MAÑANA"), datetime(2026, 1, 5, 13, 55))

    def test_el_domingo_la_manana_avisa_desde_las_17_55(self):
        self.assertEqual(turnos.inicio_del_aviso_de_cierre(date(2026, 1, 4), "MAÑANA"), datetime(2026, 1, 4, 17, 55))

    def test_la_noche_avisa_a_las_05_55_del_dia_siguiente(self):
        self.assertEqual(turnos.inicio_del_aviso_de_cierre(date(2026, 1, 4), "NOCHE"), datetime(2026, 1, 5, 5, 55))

    def test_el_fin_del_turno_es_el_horario_del_local(self):
        lunes = date(2026, 1, 5)
        self.assertEqual(turnos.fin_del_turno(lunes, "MAÑANA"), datetime(2026, 1, 5, 14, 0))
        self.assertEqual(turnos.fin_del_turno(lunes, "TARDE"), datetime(2026, 1, 5, 22, 0))
        self.assertEqual(turnos.fin_del_turno(lunes, "NOCHE"), datetime(2026, 1, 6, 6, 0))
        self.assertEqual(turnos.fin_del_turno("2026-01-04", "MAÑANA"), datetime(2026, 1, 4, 18, 0))


class TestTurnoQueArrancaTrasUnCierre(unittest.TestCase):
    """Un cierre hecho unos minutos ANTES del cambio de turno cuenta como el
    cierre del turno que termina: lo que se venda después ya es del turno nuevo."""

    def test_un_cierre_a_su_hora_o_un_poco_antes_arranca_el_turno_que_sigue(self):
        casos = [
            (datetime(2026, 1, 5, 5, 55), "MAÑANA"),    # la Noche, cerrada 5 min antes de las 6
            (datetime(2026, 1, 5, 6, 5), "MAÑANA"),
            (datetime(2026, 1, 5, 13, 55), "TARDE"),    # la Mañana, cerrada 5 min antes de las 14
            (datetime(2026, 1, 5, 14, 5), "TARDE"),
            (datetime(2026, 1, 5, 21, 55), "NOCHE"),    # la Tarde, cerrada 5 min antes de las 22
            (datetime(2026, 1, 5, 22, 5), "NOCHE"),
            (datetime(2026, 1, 5, 23, 50), "NOCHE"),
            (datetime(2026, 1, 6, 0, 30), "NOCHE"),
            (datetime(2026, 1, 5, 10, 0), "MAÑANA"),    # a mitad de turno no cambia nada
        ]
        for cuando, esperado in casos:
            with self.subTest(cuando=cuando):
                self.assertEqual(turnos.turno_que_arranca_tras_un_cierre(cuando), esperado)

    def test_la_tolerancia_es_la_misma_gracia_que_tienen_los_turnos_vencidos(self):
        cambio_de_turno = datetime(2026, 1, 5, 14, 0)
        justo_antes_de_la_gracia = cambio_de_turno - timedelta(minutes=turnos.TURNO_GRACIA_MIN + 1)
        justo_en_la_gracia = cambio_de_turno - timedelta(minutes=turnos.TURNO_GRACIA_MIN)

        self.assertEqual(turnos.turno_que_arranca_tras_un_cierre(justo_antes_de_la_gracia), "MAÑANA")
        self.assertEqual(turnos.turno_que_arranca_tras_un_cierre(justo_en_la_gracia), "TARDE")

    def test_los_domingos_el_cambio_es_a_las_18_y_a_las_6_del_lunes(self):
        casos = [
            (datetime(2026, 1, 3, 21, 55), "NOCHE"),    # sábado: la Tarde normal, cerrada 5 min antes de las 22
            (datetime(2026, 1, 3, 23, 50), "NOCHE"),    # sábado a la noche, ya cruzando a domingo
            (datetime(2026, 1, 4, 5, 55), "MAÑANA"),    # la Noche del sábado, cerrada 5 min antes: Domingo T1
            (datetime(2026, 1, 4, 14, 5), "MAÑANA"),    # el domingo no existe la Tarde
            (datetime(2026, 1, 4, 17, 55), "NOCHE"),    # Domingo T1 cerrado 5 min antes: arranca Domingo T2
            (datetime(2026, 1, 5, 5, 55), "MAÑANA"),    # Domingo T2 cerrado 5 min antes de las 6 del lunes
        ]
        for cuando, esperado in casos:
            with self.subTest(cuando=cuando):
                self.assertEqual(turnos.turno_que_arranca_tras_un_cierre(cuando), esperado)


class TestHashClave(unittest.TestCase):
    def test_hash_nuevo_tiene_salt_y_verifica_ok(self):
        hash_generado = database.hash_clave("miClave123")
        self.assertIn("$", hash_generado)
        self.assertTrue(database.verificar_clave("miClave123", hash_generado))
        self.assertFalse(database.verificar_clave("otraClave", hash_generado))

    def test_dos_claves_iguales_dan_hashes_distintos(self):
        # Gracias al salt al azar, dos usuarios con la misma clave no
        # quedan con el mismo hash guardado en la base.
        self.assertNotEqual(database.hash_clave("1234"), database.hash_clave("1234"))

    def test_verifica_hash_formato_viejo_sin_salt(self):
        hash_viejo = hashlib.sha256("miClave123".encode("utf-8")).hexdigest()
        self.assertTrue(database.verificar_clave("miClave123", hash_viejo))
        self.assertFalse(database.verificar_clave("otraClave", hash_viejo))


class TestMigracionHashEnLogin(BaseConBaseTemporal):
    def test_login_migra_hash_viejo_al_formato_nuevo(self):
        hash_viejo = hashlib.sha256("clave123".encode("utf-8")).hexdigest()
        with database.conexion_db() as conexion:
            conexion.execute(
                """
                INSERT INTO usuarios (nombre, clave_hash, rol, activo, fecha_creacion)
                VALUES (?, ?, 'EMPLEADA', 1, ?)
                """,
                ("Empleada Vieja", hash_viejo, datetime.now().isoformat(timespec="seconds")),
            )
            usuario_id = conexion.execute(
                "SELECT id FROM usuarios WHERE nombre = ?", ("Empleada Vieja",)
            ).fetchone()["id"]

        usuario = usuarios_repo.autenticar(usuario_id, "clave123")
        self.assertIsNotNone(usuario)

        usuario_actualizado = usuarios_repo.obtener_usuario(usuario_id)
        self.assertIn("$", usuario_actualizado["clave_hash"])
        # Y sigue pudiendo loguearse con la misma clave después de migrar.
        self.assertIsNotNone(usuarios_repo.autenticar(usuario_id, "clave123"))


class TestCambiarClave(BaseConBaseTemporal):
    def test_cambia_la_clave_propia_con_la_actual_correcta(self):
        usuario_id = usuarios_repo.crear_usuario("Empleada", "vieja123", "EMPLEADA")

        usuarios_repo.cambiar_clave(usuario_id, "vieja123", "nueva456")

        self.assertIsNone(usuarios_repo.autenticar(usuario_id, "vieja123"))
        self.assertIsNotNone(usuarios_repo.autenticar(usuario_id, "nueva456"))

    def test_no_cambia_nada_si_la_clave_actual_es_incorrecta(self):
        usuario_id = usuarios_repo.crear_usuario("Empleada", "vieja123", "EMPLEADA")

        with self.assertRaises(ValueError):
            usuarios_repo.cambiar_clave(usuario_id, "clave_equivocada", "nueva456")

        # La clave vieja sigue funcionando: el rechazo fue limpio.
        self.assertIsNotNone(usuarios_repo.autenticar(usuario_id, "vieja123"))


class TestAutenticarPorNombre(BaseConBaseTemporal):
    def test_loguea_ignorando_mayusculas_y_espacios(self):
        usuarios_repo.crear_usuario("Matías", "1234", "EMPLEADA")

        self.assertIsNotNone(usuarios_repo.autenticar_por_nombre("matías", "1234"))
        self.assertIsNotNone(usuarios_repo.autenticar_por_nombre("MATÍAS", "1234"))
        self.assertIsNotNone(usuarios_repo.autenticar_por_nombre("  Matías  ", "1234"))

    def test_no_loguea_con_nombre_inexistente_o_clave_incorrecta(self):
        usuarios_repo.crear_usuario("Matías", "1234", "EMPLEADA")

        self.assertIsNone(usuarios_repo.autenticar_por_nombre("Nadie", "1234"))
        self.assertIsNone(usuarios_repo.autenticar_por_nombre("Matías", "clave_mala"))

    def test_no_loguea_un_usuario_inactivo_por_nombre(self):
        usuario_id = usuarios_repo.crear_usuario("Matías", "1234", "EMPLEADA")
        usuarios_repo.desactivar_usuario(usuario_id)

        self.assertIsNone(usuarios_repo.autenticar_por_nombre("Matías", "1234"))


class TestListarLogins(BaseConBaseTemporal):
    def _loguear(self, nombre, momento):
        with mock.patch("repositories.usuarios_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = momento
            return usuarios_repo.autenticar_por_nombre(nombre, "1234")

    def setUp(self):
        super().setUp()
        usuarios_repo.crear_usuario("Sergio", "1234", "ADMIN")
        usuarios_repo.crear_usuario("Lucia", "1234", "EMPLEADA")

    def test_por_defecto_trae_solo_los_logins_de_admin_del_mas_nuevo_al_mas_viejo(self):
        self._loguear("Sergio", datetime(2026, 1, 5, 9, 0, 0))
        self._loguear("Lucia", datetime(2026, 1, 5, 10, 0, 0))
        self._loguear("Sergio", datetime(2026, 1, 5, 18, 30, 0))

        logins = usuarios_repo.listar_logins("2026-01-05", "2026-01-05")

        self.assertEqual([l["fecha_hora"] for l in logins], ["2026-01-05T18:30:00", "2026-01-05T09:00:00"])
        self.assertTrue(all(l["nombre"] == "Sergio" and l["rol"] == "ADMIN" for l in logins))

    def test_con_solo_admin_en_falso_trae_los_de_todos(self):
        self._loguear("Sergio", datetime(2026, 1, 5, 9, 0, 0))
        self._loguear("Lucia", datetime(2026, 1, 5, 10, 0, 0))

        logins = usuarios_repo.listar_logins("2026-01-05", "2026-01-05", solo_admin=False)

        self.assertEqual([l["nombre"] for l in logins], ["Lucia", "Sergio"])

    def test_respeta_el_rango_de_fechas_incluyendo_las_dos_puntas(self):
        self._loguear("Sergio", datetime(2026, 1, 4, 23, 59, 0))
        self._loguear("Sergio", datetime(2026, 1, 5, 0, 0, 0))
        self._loguear("Sergio", datetime(2026, 1, 6, 23, 59, 0))
        self._loguear("Sergio", datetime(2026, 1, 7, 0, 0, 0))

        logins = usuarios_repo.listar_logins("2026-01-05", "2026-01-06")

        self.assertEqual([l["fecha_hora"] for l in logins], ["2026-01-06T23:59:00", "2026-01-05T00:00:00"])

    def test_un_login_con_clave_incorrecta_no_queda_registrado(self):
        with mock.patch("repositories.usuarios_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 1, 5, 9, 0, 0)
            self.assertIsNone(usuarios_repo.autenticar_por_nombre("Sergio", "mala"))

        self.assertEqual(usuarios_repo.listar_logins("2026-01-05", "2026-01-05"), [])


class TestPermisosDeEmpleada(BaseConBaseTemporal):
    def test_crear_usuario_guarda_los_permisos_pedidos(self):
        usuario_id = usuarios_repo.crear_usuario(
            "Miguel", "1234", "EMPLEADA",
            permisos={"permiso_articulos": True, "permiso_compras": True},
        )
        usuario = usuarios_repo.obtener_usuario(usuario_id)

        self.assertTrue(usuarios_repo.tiene_permiso(usuario, "permiso_articulos"))
        self.assertTrue(usuarios_repo.tiene_permiso(usuario, "permiso_compras"))
        # Los que no se pidieron quedan en False, no en True por las dudas.
        self.assertFalse(usuarios_repo.tiene_permiso(usuario, "permiso_reportes"))
        self.assertFalse(usuarios_repo.tiene_permiso(usuario, "permiso_consulta_ventas"))
        self.assertFalse(usuarios_repo.tiene_permiso(usuario, "permiso_control_cierres"))

    def test_admin_tiene_todos_los_permisos_sin_importar_las_columnas(self):
        usuario_id = usuarios_repo.crear_usuario("Jefa", "1234", "ADMIN")
        usuario = usuarios_repo.obtener_usuario(usuario_id)

        for columna, _ in usuarios_repo.PERMISOS_EMPLEADA:
            self.assertTrue(usuarios_repo.tiene_permiso(usuario, columna))

    def test_modificar_usuario_reemplaza_los_permisos_en_vez_de_sumarlos(self):
        usuario_id = usuarios_repo.crear_usuario(
            "Miguel", "1234", "EMPLEADA", permisos={"permiso_articulos": True}
        )

        usuarios_repo.modificar_usuario(
            usuario_id, "Miguel", "EMPLEADA", permisos={"permiso_compras": True}
        )
        usuario = usuarios_repo.obtener_usuario(usuario_id)

        # El permiso nuevo quedó, y el viejo que no se volvió a tildar se sacó.
        self.assertTrue(usuarios_repo.tiene_permiso(usuario, "permiso_compras"))
        self.assertFalse(usuarios_repo.tiene_permiso(usuario, "permiso_articulos"))

    def test_crear_usuario_sin_pasar_permisos_los_deja_todos_en_false(self):
        usuario_id = usuarios_repo.crear_usuario("Empleada", "1234", "EMPLEADA")
        usuario = usuarios_repo.obtener_usuario(usuario_id)

        for columna, _ in usuarios_repo.PERMISOS_EMPLEADA:
            self.assertFalse(usuarios_repo.tiene_permiso(usuario, columna))


class TestExigirAdmin(BaseConBaseTemporal):
    """usuarios_repo.exigir_admin: la única forma de pedir "solo un Admin" en un
    repo (la usa, entre otros, la operación ORDENAR Stock)."""

    def test_un_admin_activo_pasa_y_devuelve_su_fila(self):
        admin = usuarios_repo.crear_usuario("Jefa", "1234", dominio.ROL_ADMIN)
        self.assertEqual(usuarios_repo.exigir_admin(admin, "hacer algo")["nombre"], "Jefa")

    def test_una_empleada_no_pasa(self):
        empleada = usuarios_repo.crear_usuario("Ana", "1234", dominio.ROL_EMPLEADA)
        with self.assertRaisesRegex(PermissionError, "Solo un Administrador puede hacer algo."):
            usuarios_repo.exigir_admin(empleada, "hacer algo")

    def test_un_admin_dado_de_baja_no_pasa(self):
        # Se relee de la base: una sesión que quedó abierta no sirve.
        admin = usuarios_repo.crear_usuario("Jefa", "1234", dominio.ROL_ADMIN)
        usuarios_repo.desactivar_usuario(admin)
        with self.assertRaisesRegex(PermissionError, "ya no está habilitado"):
            usuarios_repo.exigir_admin(admin, "hacer algo")
        with self.assertRaises(PermissionError):
            usuarios_repo.exigir_admin(9999, "hacer algo")


class TestGestionDeUsuarios(BaseConBaseTemporal):
    def test_crear_usuario_asigna_numeros_correlativos(self):
        # El id 1 ya lo tiene el Administrador que se siembra solo.
        id_a = usuarios_repo.crear_usuario("A", "1234", "EMPLEADA")
        id_b = usuarios_repo.crear_usuario("B", "1234", "EMPLEADA")
        self.assertEqual(id_a, 2)
        self.assertEqual(id_b, 3)

    def test_borrar_usuario_sin_historial_libera_su_numero(self):
        id_a = usuarios_repo.crear_usuario("A", "1234", "EMPLEADA")

        usuarios_repo.borrar_usuario(id_a)
        self.assertIsNone(usuarios_repo.obtener_usuario(id_a))

        # El próximo usuario que se crea reutiliza el número liberado,
        # en vez de saltar directo al siguiente más alto.
        id_c = usuarios_repo.crear_usuario("C", "1234", "EMPLEADA")
        self.assertEqual(id_c, id_a)

    def test_borrar_usuario_con_ventas_tira_error_y_no_borra_nada(self):
        vendedor_id = usuarios_repo.crear_usuario("Vendedor", "1234", "EMPLEADA")
        articulos_repo.crear_articulo("CODU", "Producto", None, None, 10.0, 5.0, 0)
        compras_repo.registrar_compra(vendedor_id, [{"codigo": "CODU", "cantidad": 5, "costo_unitario": 5.0}])
        ventas_repo.confirmar_venta(
            vendedor_id,
            [{"codigo": "CODU", "descripcion": "Producto", "cantidad": 1,
              "precio_unitario": 10.0}],
            [{"metodo": "EFECTIVO", "monto": 10.0}],
        )

        with self.assertRaises(ValueError):
            usuarios_repo.borrar_usuario(vendedor_id)

        # Sigue existiendo: el rechazo fue limpio, no quedó nada a mitad
        # de camino (mismo criterio que articulos_repo.borrar_articulo).
        self.assertIsNotNone(usuarios_repo.obtener_usuario(vendedor_id))

    def test_no_se_puede_crear_dos_usuarios_activos_con_el_mismo_nombre(self):
        usuarios_repo.crear_usuario("Matías", "1234", "EMPLEADA")

        # Ni exactamente igual, ni con mayúsculas/espacios distintos:
        # el login es por nombre, así que dos activos iguales quedarían
        # ambiguos (ver usuarios_repo.autenticar_por_nombre).
        with self.assertRaises(ValueError):
            usuarios_repo.crear_usuario("  MATÍAS  ", "otraClave", "EMPLEADA")

    def test_se_puede_reusar_el_nombre_de_un_usuario_inactivo(self):
        usuario_id = usuarios_repo.crear_usuario("Matías", "1234", "EMPLEADA")
        usuarios_repo.desactivar_usuario(usuario_id)

        # No está activo, así que no genera ambigüedad para el login.
        nuevo_id = usuarios_repo.crear_usuario("Matías", "5678", "EMPLEADA")
        self.assertNotEqual(nuevo_id, usuario_id)

    def test_modificar_usuario_no_deja_renombrar_a_uno_ya_usado(self):
        usuarios_repo.crear_usuario("Matías", "1234", "EMPLEADA")
        otro_id = usuarios_repo.crear_usuario("Rocío", "1234", "EMPLEADA")

        with self.assertRaises(ValueError):
            usuarios_repo.modificar_usuario(otro_id, "Matías", "EMPLEADA")

        # No cambió nada: sigue llamándose Rocío.
        self.assertEqual(usuarios_repo.obtener_usuario(otro_id)["nombre"], "Rocío")

    def test_modificar_usuario_permite_dejar_el_mismo_nombre(self):
        # Guardar sin cambiar el nombre no debe chocar contra sí mismo.
        usuario_id = usuarios_repo.crear_usuario("Matías", "1234", "EMPLEADA")
        usuarios_repo.modificar_usuario(usuario_id, "Matías", "ADMIN")
        self.assertEqual(usuarios_repo.obtener_usuario(usuario_id)["rol"], "ADMIN")

    def test_no_se_crea_un_usuario_sin_nombre(self):
        # El formulario ya lo frena, pero la regla es del repo (regla 3).
        antes = len(usuarios_repo.listar_usuarios(incluir_inactivos=True))
        for nombre in ("", "   ", None):
            with self.subTest(nombre=nombre):
                with self.assertRaisesRegex(ValueError, "Ingresá el nombre"):
                    usuarios_repo.crear_usuario(nombre, "1234", dominio.ROL_EMPLEADA)
        self.assertEqual(len(usuarios_repo.listar_usuarios(incluir_inactivos=True)), antes)

    def test_no_se_crea_un_usuario_sin_clave(self):
        antes = len(usuarios_repo.listar_usuarios(incluir_inactivos=True))
        for clave in ("", None):
            with self.subTest(clave=clave):
                with self.assertRaisesRegex(ValueError, "necesita una clave"):
                    usuarios_repo.crear_usuario("Rocío", clave, dominio.ROL_EMPLEADA)
        self.assertEqual(len(usuarios_repo.listar_usuarios(incluir_inactivos=True)), antes)

    def test_modificar_no_deja_el_nombre_vacio(self):
        usuario_id = usuarios_repo.crear_usuario("Rocío", "1234", dominio.ROL_EMPLEADA)
        for nombre in ("", "   ", None):
            with self.subTest(nombre=nombre):
                with self.assertRaisesRegex(ValueError, "Ingresá el nombre"):
                    usuarios_repo.modificar_usuario(usuario_id, nombre, dominio.ROL_EMPLEADA)
        self.assertEqual(usuarios_repo.obtener_usuario(usuario_id)["nombre"], "Rocío")

    def test_modificar_con_la_clave_vacia_la_deja_como_estaba(self):
        # En Modificar, el campo Clave vacío quiere decir "no cambiarla".
        usuario_id = usuarios_repo.crear_usuario("Rocío", "1234", dominio.ROL_EMPLEADA)
        usuarios_repo.modificar_usuario(usuario_id, "Rocío", dominio.ROL_EMPLEADA, clave="")
        usuarios_repo.modificar_usuario(usuario_id, "Rocío", dominio.ROL_EMPLEADA, clave=None)
        self.assertIsNotNone(usuarios_repo.autenticar_por_nombre("Rocío", "1234"))


class TestSiempreQuedaUnAdministrador(BaseConBaseTemporal):
    """Sin ningún Administrador activo nadie puede volver a entrar a Usuarios,
    anular ventas ni usar ORDENAR Stock sin tocar la base a mano: el único que
    hay no se puede pasar a Empleada, desactivar ni borrar. Antes el único Admin
    se podía pasar a sí mismo a Empleada desde Usuarios > Modificar."""

    def setUp(self):
        super().setUp()
        # El Administrador que se siembra solo en una base nueva (id 1).
        self.admin_id = usuarios_repo.listar_usuarios()[0]["id"]

    def _rol(self, usuario_id):
        return usuarios_repo.obtener_usuario(usuario_id)["rol"]

    def test_el_unico_administrador_no_se_puede_pasar_a_empleada(self):
        with self.assertRaisesRegex(ValueError, "Administrador es el único Administrador activo"):
            usuarios_repo.modificar_usuario(self.admin_id, "Administrador", dominio.ROL_EMPLEADA)
        self.assertEqual(self._rol(self.admin_id), dominio.ROL_ADMIN)

    def test_el_rechazo_no_deja_nada_a_medio_guardar(self):
        # Ni el nombre, ni la clave, ni los permisos que venían en el mismo pedido.
        with self.assertRaises(ValueError):
            usuarios_repo.modificar_usuario(
                self.admin_id, "Sergio", dominio.ROL_EMPLEADA, clave="nueva",
                permisos={"permiso_reportes": True},
            )
        admin = usuarios_repo.obtener_usuario(self.admin_id)
        self.assertEqual((admin["nombre"], admin["permiso_reportes"]), ("Administrador", 0))
        self.assertIsNotNone(usuarios_repo.autenticar_por_nombre("Administrador", "1234"))

    def test_el_unico_administrador_si_puede_cambiar_su_nombre_y_su_clave(self):
        usuarios_repo.modificar_usuario(self.admin_id, "Sergio", dominio.ROL_ADMIN, clave="nueva")
        self.assertIsNotNone(usuarios_repo.autenticar_por_nombre("Sergio", "nueva"))

    def test_con_otro_administrador_activo_si_se_puede_pasar_a_empleada(self):
        usuarios_repo.crear_usuario("Sergio", "1234", dominio.ROL_ADMIN)
        usuarios_repo.modificar_usuario(self.admin_id, "Administrador", dominio.ROL_EMPLEADA)
        self.assertEqual(self._rol(self.admin_id), dominio.ROL_EMPLEADA)

    def test_un_administrador_dado_de_baja_no_cuenta_como_el_otro(self):
        sergio_id = usuarios_repo.crear_usuario("Sergio", "1234", dominio.ROL_ADMIN)
        usuarios_repo.desactivar_usuario(sergio_id)
        with self.assertRaisesRegex(ValueError, "único Administrador activo"):
            usuarios_repo.modificar_usuario(self.admin_id, "Administrador", dominio.ROL_EMPLEADA)

    def test_el_unico_administrador_no_se_puede_desactivar(self):
        with self.assertRaisesRegex(ValueError, "No se lo puede desactivar"):
            usuarios_repo.desactivar_usuario(self.admin_id)
        self.assertTrue(usuarios_repo.obtener_usuario(self.admin_id)["activo"])

    def test_el_unico_administrador_no_se_puede_borrar(self):
        # Sin historial, antes se borraba del todo.
        with self.assertRaisesRegex(ValueError, "No se lo puede borrar"):
            usuarios_repo.borrar_usuario(self.admin_id)
        self.assertIsNotNone(usuarios_repo.obtener_usuario(self.admin_id))

    def test_con_historial_el_aviso_es_el_del_unico_administrador(self):
        # El del historial sugiere desactivarlo, y eso tampoco se puede.
        articulos_repo.crear_articulo("CODA", "Producto", None, None, 10.0, 5.0, 0)
        compras_repo.registrar_compra(self.admin_id, [{"codigo": "CODA", "cantidad": 1, "costo_unitario": 5.0}])
        with self.assertRaises(ValueError) as error:
            usuarios_repo.borrar_usuario(self.admin_id)
        self.assertIn("único Administrador activo", str(error.exception))
        self.assertNotIn("historial", str(error.exception))

    def test_con_otro_administrador_activo_si_se_puede_desactivar_y_borrar(self):
        usuarios_repo.crear_usuario("Sergio", "1234", dominio.ROL_ADMIN)
        jefa_id = usuarios_repo.crear_usuario("Jefa", "1234", dominio.ROL_ADMIN)
        usuarios_repo.borrar_usuario(jefa_id)
        usuarios_repo.desactivar_usuario(self.admin_id)
        self.assertIsNone(usuarios_repo.obtener_usuario(jefa_id))
        self.assertFalse(usuarios_repo.obtener_usuario(self.admin_id)["activo"])

    def test_las_empleadas_se_dan_de_baja_igual_que_siempre(self):
        lucia_id = usuarios_repo.crear_usuario("Lucia", "1234", dominio.ROL_EMPLEADA)
        rocio_id = usuarios_repo.crear_usuario("Rocío", "1234", dominio.ROL_EMPLEADA)
        usuarios_repo.desactivar_usuario(lucia_id)
        usuarios_repo.borrar_usuario(rocio_id)
        self.assertFalse(usuarios_repo.obtener_usuario(lucia_id)["activo"])
        self.assertIsNone(usuarios_repo.obtener_usuario(rocio_id))


class TestVentasYStock(BaseConBaseTemporal):
    def _crear_admin_y_articulo(self):
        usuario_id = usuarios_repo.crear_usuario("Test", "1234", "ADMIN")
        articulos_repo.crear_articulo("COD1", "Producto de prueba", None, None, 100.0, 50.0, 5)
        compras_repo.registrar_compra(usuario_id, [{"codigo": "COD1", "cantidad": 10, "costo_unitario": 50.0}])
        return usuario_id

    def test_confirmar_venta_descuenta_stock(self):
        usuario_id = self._crear_admin_y_articulo()
        ventas_repo.confirmar_venta(
            usuario_id,
            [{"codigo": "COD1", "descripcion": "Producto de prueba", "cantidad": 3,
              "precio_unitario": 100.0}],
            [{"metodo": "EFECTIVO", "monto": 300.0}],
        )
        articulo = articulos_repo.buscar_por_codigo("COD1")
        self.assertEqual(articulo["stock"], 7)

    def test_anular_venta_repone_stock_y_cambia_estado(self):
        usuario_id = self._crear_admin_y_articulo()
        venta_id = ventas_repo.confirmar_venta(
            usuario_id,
            [{"codigo": "COD1", "descripcion": "Producto de prueba", "cantidad": 3,
              "precio_unitario": 100.0}],
            [{"metodo": "EFECTIVO", "monto": 300.0}],
        )
        ventas_repo.anular_venta(venta_id, usuario_id, "prueba")

        articulo = articulos_repo.buscar_por_codigo("COD1")
        self.assertEqual(articulo["stock"], 10)

        venta, _detalle, _pagos = ventas_repo.buscar_venta(venta_id)
        self.assertEqual(venta["estado"], "ANULADA")

    def test_no_se_puede_anular_una_venta_dos_veces(self):
        usuario_id = self._crear_admin_y_articulo()
        venta_id = ventas_repo.confirmar_venta(
            usuario_id,
            [{"codigo": "COD1", "descripcion": "Producto de prueba", "cantidad": 1,
              "precio_unitario": 100.0}],
            [{"metodo": "EFECTIVO", "monto": 100.0}],
        )
        ventas_repo.anular_venta(venta_id, usuario_id, "prueba")
        with self.assertRaises(ValueError):
            ventas_repo.anular_venta(venta_id, usuario_id, "de nuevo")

    def test_montos_quedan_redondeados_a_dos_decimales(self):
        usuario_id = self._crear_admin_y_articulo()
        # cantidad * precio con más de 2 decimales, a propósito.
        ventas_repo.confirmar_venta(
            usuario_id,
            [{"codigo": "COD1", "descripcion": "Producto de prueba", "cantidad": 3,
              "precio_unitario": 33.333333}],
            [{"metodo": "EFECTIVO", "monto": 99.999999}],
        )
        venta = ventas_repo.listar_ventas_recientes(1)[0]
        self.assertEqual(venta["total"], 100.0)


class TestLosPagosSumanElTotal(BaseConBaseTemporal):
    """ventas_repo._grabar_venta_kiosko (por donde pasan Vender e Impresiones):
    los pagos llegan netos de vuelto y tienen que sumar el total de la venta.
    Si no, Reportes (que suma ventas.total) y el Cierre de Turno (que suma
    venta_pagos) mostrarían plata distinta sin ningún aviso."""

    def setUp(self):
        super().setUp()
        self.usuario_id = usuarios_repo.crear_usuario("Lucia", "1234", dominio.ROL_EMPLEADA)
        articulos_repo.crear_articulo("COD1", "Alfajor", None, None, 1500.0, 900.0, 0)

    def _vender(self, pagos, cantidad=2, precio=1500.0):
        return ventas_repo.confirmar_venta(
            self.usuario_id,
            [{"codigo": "COD1", "descripcion": "Alfajor", "cantidad": cantidad, "precio_unitario": precio}],
            pagos,
        )

    def _no_se_grabo_nada(self):
        self.assertEqual(ventas_repo.listar_ventas_recientes(), [])
        # Ni el stock se descontó: la venta entera quedó afuera.
        self.assertEqual(articulos_repo.buscar_por_codigo("COD1")["stock"], 0)

    def test_pagos_que_no_llegan_al_total_no_graban_nada(self):
        with self.assertRaisesRegex(ValueError, "no coincide con el total"):
            self._vender([{"metodo": dominio.PAGO_EFECTIVO, "monto": 2000.0}])
        self._no_se_grabo_nada()

    def test_pagos_que_pasan_el_total_tampoco(self):
        # Con vuelto, la ventana de cobro manda solo lo que queda en la caja:
        # $ 3.500 por una venta de $ 3.000 sería el vuelto anotado como cobrado.
        with self.assertRaises(ValueError):
            self._vender([{"metodo": dominio.PAGO_EFECTIVO, "monto": 3000.0},
                          {"metodo": dominio.PAGO_DIGITAL, "monto": 500.0}])
        self._no_se_grabo_nada()

    def test_el_pago_justo_repartido_en_los_dos_medios_se_graba(self):
        venta_id = self._vender([{"metodo": dominio.PAGO_EFECTIVO, "monto": 1000.0},
                                 {"metodo": dominio.PAGO_DIGITAL, "monto": 2000.0}])

        venta, _detalle, pagos = ventas_repo.buscar_venta(venta_id)
        self.assertEqual(venta["total"], 3000.0)
        self.assertEqual(sum(pago["monto"] for pago in pagos), 3000.0)

    def test_un_centavo_de_redondeo_se_acepta_y_dos_ya_no(self):
        # 3 x $ 33,333333 = $ 100 (redondeado): repartirlo en tercios puede
        # perder un centavo, y eso no es plata que falte.
        venta_id = self._vender([{"metodo": dominio.PAGO_EFECTIVO, "monto": 33.33},
                                 {"metodo": dominio.PAGO_DIGITAL, "monto": 66.66}],
                                cantidad=3, precio=33.333333)
        self.assertEqual(ventas_repo.buscar_venta(venta_id)[0]["total"], 100.0)

        with self.assertRaises(ValueError):
            self._vender([{"metodo": dominio.PAGO_EFECTIVO, "monto": 99.98}], cantidad=3, precio=33.333333)


class TestAnularVentaSoloElAdminYConMotivo(BaseConBaseTemporal):
    """ventas_repo.anular_venta vuelve a preguntar en el repo lo que la
    pantalla ya esconde: que quien anula sea un Administrador activo
    (usuarios_repo.exigir_admin) y que diga por qué."""

    def setUp(self):
        super().setUp()
        self.admin_id = usuarios_repo.crear_usuario("Dueño", "1234", dominio.ROL_ADMIN)
        self.lucia_id = usuarios_repo.crear_usuario("Lucia", "1234", dominio.ROL_EMPLEADA)
        articulos_repo.crear_articulo("COD1", "Alfajor", None, None, 1500.0, 900.0, 0)
        self.venta_id = ventas_repo.confirmar_venta(
            self.lucia_id,
            [{"codigo": "COD1", "descripcion": "Alfajor", "cantidad": 1, "precio_unitario": 1500.0}],
            [{"metodo": dominio.PAGO_EFECTIVO, "monto": 1500.0}],
        )

    def _sigue_confirmada(self):
        venta, _detalle, _pagos = ventas_repo.buscar_venta(self.venta_id)
        self.assertEqual(venta["estado"], dominio.VENTA_CONFIRMADA)
        self.assertEqual(articulos_repo.buscar_por_codigo("COD1")["stock"], -1)

    def test_una_empleada_no_puede_anular(self):
        with self.assertRaisesRegex(PermissionError, "Solo un Administrador puede anular una venta."):
            ventas_repo.anular_venta(self.venta_id, self.lucia_id, "se cobró dos veces")
        self._sigue_confirmada()

    def test_un_admin_dado_de_baja_no_puede_anular(self):
        # Se relee de la base: una sesión que quedó abierta no alcanza.
        usuarios_repo.desactivar_usuario(self.admin_id)
        with self.assertRaises(PermissionError):
            ventas_repo.anular_venta(self.venta_id, self.admin_id, "se cobró dos veces")
        self._sigue_confirmada()

    def test_sin_motivo_no_se_anula(self):
        for motivo in ("", "   ", None):
            with self.assertRaisesRegex(ValueError, "motivo", msg=repr(motivo)):
                ventas_repo.anular_venta(self.venta_id, self.admin_id, motivo)
        self._sigue_confirmada()

    def test_el_admin_anula_con_motivo_y_queda_quien_y_por_que(self):
        ventas_repo.anular_venta(self.venta_id, self.admin_id, "  se cobró dos veces  ")

        venta, _detalle, _pagos = ventas_repo.buscar_venta(self.venta_id)
        self.assertEqual(venta["estado"], dominio.VENTA_ANULADA)
        self.assertEqual(venta["anulada_por"], self.admin_id)
        self.assertEqual(venta["anulada_motivo"], "se cobró dos veces")
        self.assertEqual(articulos_repo.buscar_por_codigo("COD1")["stock"], 0)


class TestElCierreGrabaLaPlataRedondeada(BaseConBaseTemporal):
    """Regla 9: turnos_repo.cerrar_turno redondea a centavos lo que graba en
    cierres_turno. SQLite suma tres pagos de $ 0,10 como 0.30000000000000004,
    y esa cola quedaría para siempre en el cierre."""

    def test_tres_ventas_de_diez_centavos_quedan_grabadas_como_treinta(self):
        usuario_id = usuarios_repo.crear_usuario("Dueño", "1234", dominio.ROL_ADMIN)
        articulos_repo.crear_articulo("COD1", "Caramelo", None, None, 0.1, 0.05, 0)
        for _ in range(3):
            ventas_repo.confirmar_venta(
                usuario_id,
                [{"codigo": "COD1", "descripcion": "Caramelo", "cantidad": 1, "precio_unitario": 0.1}],
                [{"metodo": dominio.PAGO_EFECTIVO, "monto": 0.1}],
            )
        with database.conexion_db() as conexion:
            sin_redondear = conexion.execute("SELECT SUM(monto) AS total FROM venta_pagos").fetchone()["total"]
        # Si este SQLite ya sumara justo, la prueba no estaría mostrando nada.
        self.assertNotEqual(sin_redondear, 0.3)

        cierre = turnos_repo.cerrar_turno(usuario_id)

        with database.conexion_db() as conexion:
            grabado = conexion.execute("SELECT * FROM cierres_turno WHERE id = ?", (cierre["id"],)).fetchone()
        for campo in ("ventas_efectivo", "monto_a_retirar", *turnos_repo._CAMPOS_PLATA):
            self.assertEqual(grabado[campo], round(grabado[campo], 2), msg=campo)
        self.assertEqual((grabado["ventas_efectivo"], grabado["monto_a_retirar"], grabado["kiosko_efectivo"]),
                         (0.3, 0.3, 0.3))
        # Lo que devuelve (y muestra la pantalla al cerrar) es lo mismo que quedó grabado.
        self.assertEqual((cierre["ventas_efectivo"], cierre["monto_a_retirar"], cierre["kiosko_efectivo"]),
                         (0.3, 0.3, 0.3))




class TestBorrarArticuloProtegido(BaseConBaseTemporal):
    def test_borrar_articulo_sin_movimientos_funciona(self):
        articulos_repo.crear_articulo("SINMOV", "Sin movimientos", None, None, 10.0, 5.0, 0)
        articulos_repo.borrar_articulo("SINMOV")
        self.assertIsNone(articulos_repo.buscar_por_codigo("SINMOV"))

    def test_borrar_articulo_con_ventas_tira_error_claro_y_no_borra_nada(self):
        usuario_id = usuarios_repo.crear_usuario("Test", "1234", "ADMIN")
        articulos_repo.crear_articulo("CONVENTA", "Con venta", None, None, 10.0, 5.0, 0)
        compras_repo.registrar_compra(usuario_id, [{"codigo": "CONVENTA", "cantidad": 5, "costo_unitario": 5.0}])
        ventas_repo.confirmar_venta(
            usuario_id,
            [{"codigo": "CONVENTA", "descripcion": "Con venta", "cantidad": 1,
              "precio_unitario": 10.0}],
            [{"metodo": "EFECTIVO", "monto": 10.0}],
        )

        with self.assertRaises(ValueError):
            articulos_repo.borrar_articulo("CONVENTA")

        # El artículo sigue existiendo: el rechazo fue limpio, no quedó
        # nada a mitad de camino.
        self.assertIsNotNone(articulos_repo.buscar_por_codigo("CONVENTA"))


class TestEtiquetaDeTurnoEnElCierre(BaseConBaseTemporal):
    def test_turno_del_cierre_es_el_que_empezo_no_el_que_esta_corriendo_al_cerrar(self):
        usuario_id = usuarios_repo.crear_usuario("Test", "1234", "ADMIN")

        # Primer cierre: se hace a las 10:00 (turno MAÑANA).
        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 1, 1, 10, 0, 0)
            datetime_mock.fromisoformat = datetime.fromisoformat
            turnos_repo.cerrar_turno(usuario_id)

        # Segundo cierre: el turno arrancó a las 10:00 (MAÑANA), pero
        # la empleada recién cierra a las 14:05 — ya entrada la hora
        # del turno TARDE. El cierre tiene que quedar etiquetado como
        # MAÑANA (el turno que efectivamente se está cerrando), no TARDE.
        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 1, 1, 14, 5, 0)
            datetime_mock.fromisoformat = datetime.fromisoformat
            turnos_repo.cerrar_turno(usuario_id)

        cierres = turnos_repo.listar_cierres()
        cierre_mas_reciente = cierres[0]
        self.assertEqual(cierre_mas_reciente["turno"], "MAÑANA")


class TestResumenTurnoActualCoincideConElCierre(BaseConBaseTemporal):
    """
    Antes, la vista previa de Caja/Cierre de Turno (resumen_turno_actual)
    calculaba el turno mirando la hora ACTUAL, mientras que cerrar_turno
    lo calculaba mirando cuándo arrancó lo que sigue sin cerrar -- podían
    no coincidir. Ver _desde_y_turno_en_curso.
    """

    def test_el_titulo_en_pantalla_anticipa_el_turno_que_va_a_quedar_grabado(self):
        usuario_id = usuarios_repo.crear_usuario("Test", "1234", "ADMIN")

        # Primer cierre a las 10:00 (turno MAÑANA).
        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 1, 1, 10, 0, 0)
            datetime_mock.fromisoformat = datetime.fromisoformat
            turnos_repo.cerrar_turno(usuario_id)

        # Son las 14:05: ya empezó TARDE, pero la MAÑANA todavía no se
        # cerró. La vista previa tiene que seguir mostrando MAÑANA (el
        # turno que efectivamente se va a grabar si alguien cierra ahora),
        # no TARDE.
        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 1, 1, 14, 5, 0)
            datetime_mock.fromisoformat = datetime.fromisoformat
            resumen = turnos_repo.resumen_turno_actual()
            self.assertEqual(resumen["turno_actual"], "MAÑANA")
            self.assertEqual(resumen["turno_actual_label"], "Mañana")

            cierre = turnos_repo.cerrar_turno(usuario_id)
            self.assertEqual(cierre["turno"], "MAÑANA")


class TestFechaDelCierreEsElDiaQueArrancoElTurno(BaseConBaseTemporal):
    def test_turno_noche_cerrado_pasada_la_medianoche_guarda_la_fecha_de_inicio(self):
        usuario_id = usuarios_repo.crear_usuario("Test", "1234", "ADMIN")

        # Primer cierre del sistema, ya entrada la Noche del 5 de enero.
        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 1, 5, 22, 5, 0)
            datetime_mock.fromisoformat = datetime.fromisoformat
            turnos_repo.cerrar_turno(usuario_id)

        # Se cierra recién a las 00:40 del día siguiente: el turno Noche
        # arrancó el 5 (justo después del cierre anterior), no el 6 —
        # "fecha" tiene que quedar en el día 5, aunque el cierre en sí se
        # haga ya entrado el día 6 (mismo criterio que ya se usa para
        # "turno", ver TestEtiquetaDeTurnoEnElCierre).
        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 1, 6, 0, 40, 0)
            datetime_mock.fromisoformat = datetime.fromisoformat
            resultado = turnos_repo.cerrar_turno(usuario_id)

        cierre = turnos_repo.listar_cierres()[0]
        self.assertEqual(cierre["id"], resultado["id"])
        self.assertEqual(cierre["fecha"], "2026-01-05")
        self.assertEqual(cierre["turno"], "NOCHE")
        self.assertEqual(resultado["turno_label"], "Noche")


class TestCierreHechoUnPocoAntesDelCambioDeTurno(BaseConBaseTemporal):
    """
    Quien cierra un par de minutos antes del cambio de turno (el que se va a las
    13:55 porque ya llegó la Tarde) no tiene que correr de turno a todos los cierres
    que vienen después: antes la Tarde quedaba anotada como "Mañana", la Noche como
    "Tarde", y el reporte marcaba "SIN CERRAR" un turno que sí se había cerrado.
    Ver turnos.turno_que_arranca_tras_un_cierre.
    """

    def setUp(self):
        super().setUp()
        self.usuario_id = usuarios_repo.crear_usuario("Test", "1234", "ADMIN")

    def _cerrar(self, momento):
        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = momento
            datetime_mock.fromisoformat = datetime.fromisoformat
            return turnos_repo.cerrar_turno(self.usuario_id)

    def test_cerrando_cinco_minutos_antes_cada_cierre_queda_en_su_turno(self):
        # Martes 6 a la noche arranca el sistema; de ahí en adelante, todos los
        # cierres se hacen 5 minutos antes del cambio de turno.
        self._cerrar(datetime(2026, 1, 6, 21, 55))
        self._cerrar(datetime(2026, 1, 7, 5, 55))     # la Noche del martes
        self._cerrar(datetime(2026, 1, 7, 13, 55))    # la Mañana del miércoles
        self._cerrar(datetime(2026, 1, 7, 21, 55))    # la Tarde del miércoles
        self._cerrar(datetime(2026, 1, 8, 5, 55))     # la Noche del miércoles

        anotados = [(c["fecha"], c["turno"]) for c in reversed(turnos_repo.listar_cierres())][1:]

        self.assertEqual(anotados, [
            ("2026-01-06", "NOCHE"), ("2026-01-07", "MAÑANA"), ("2026-01-07", "TARDE"), ("2026-01-07", "NOCHE"),
        ])

    def test_el_reporte_del_dia_no_marca_sin_cerrar_un_turno_que_si_se_cerro(self):
        self._cerrar(datetime(2026, 1, 7, 6, 5))      # arranca el sistema, sin ventas
        self._cerrar(datetime(2026, 1, 7, 13, 55))    # la Mañana, 5 minutos antes de las 14
        self._cerrar(datetime(2026, 1, 7, 21, 55))    # la Tarde, 5 minutos antes de las 22

        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 1, 7, 23, 0)
            datetime_mock.fromisoformat = datetime.fromisoformat
            resumen = turnos_repo.resumen_del_dia(date(2026, 1, 7))

        # La Tarde ya venció (22:40) y se cerró: no está "sin cerrar". La Noche, recién
        # arrancada, sigue en curso. (Sin la tolerancia, el cierre de las 13:55 contaba como
        # arranque de la Mañana, el de las 21:55 quedaba anotado como "Mañana" y la Tarde
        # figuraba sin cerrar.)
        self.assertEqual([t["estado"] for t in resumen["turnos"]], [
            turnos_repo.ESTADO_CERRADO, turnos_repo.ESTADO_CERRADO, turnos_repo.ESTADO_EN_CURSO,
        ])

    def test_el_primer_cierre_de_todos_sigue_siendo_el_turno_de_la_hora_en_que_se_hace(self):
        # No hay cierre anterior del que tomar la hora: la tolerancia no corre.
        self.assertEqual(self._cerrar(datetime(2026, 1, 7, 13, 55))["turno"], "MAÑANA")
        self.assertEqual(self._cerrar(datetime(2026, 1, 7, 22, 5))["turno"], "TARDE")

    def test_la_vista_previa_de_caja_anticipa_el_turno_que_se_va_a_grabar(self):
        self._cerrar(datetime(2026, 1, 7, 6, 5))
        self._cerrar(datetime(2026, 1, 7, 13, 55))

        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 1, 7, 14, 10)
            datetime_mock.fromisoformat = datetime.fromisoformat
            resumen = turnos_repo.resumen_turno_actual()
            cierre = turnos_repo.cerrar_turno(self.usuario_id)

        self.assertEqual(resumen["turno_actual"], "TARDE")
        self.assertEqual(cierre["turno"], "TARDE")


class TestDetalleCierre(BaseConBaseTemporal):
    def _vender(self, usuario_id, momento, total=10.0):
        with mock.patch("repositories.ventas_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = momento
            return ventas_repo.confirmar_venta(
                usuario_id,
                [{"codigo": "COD9", "descripcion": "Producto", "cantidad": 1,
                  "precio_unitario": total}],
                [{"metodo": "EFECTIVO", "monto": total}],
            )

    def _cerrar(self, usuario_id, momento):
        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = momento
            datetime_mock.fromisoformat = datetime.fromisoformat
            return turnos_repo.cerrar_turno(usuario_id)

    def test_cada_cierre_solo_trae_las_ventas_de_su_propia_ventana(self):
        usuario_id = usuarios_repo.crear_usuario("Test", "1234", "ADMIN")
        articulos_repo.crear_articulo("COD9", "Producto", None, None, 10.0, 5.0, 0)
        compras_repo.registrar_compra(usuario_id, [{"codigo": "COD9", "cantidad": 5, "costo_unitario": 5.0}])

        venta_1 = self._vender(usuario_id, datetime(2026, 1, 1, 9, 0, 0))
        cierre_1 = self._cerrar(usuario_id, datetime(2026, 1, 1, 10, 0, 0))

        venta_2 = self._vender(usuario_id, datetime(2026, 1, 1, 11, 0, 0))
        cierre_2 = self._cerrar(usuario_id, datetime(2026, 1, 1, 14, 0, 0))

        detalle_1 = turnos_repo.detalle_cierre(cierre_1["id"])
        self.assertEqual([v["id"] for v in detalle_1["ventas"]], [venta_1])

        detalle_2 = turnos_repo.detalle_cierre(cierre_2["id"])
        self.assertEqual([v["id"] for v in detalle_2["ventas"]], [venta_2])

    def test_incluye_ventas_anuladas_de_la_ventana_pero_no_cuentan_para_el_total(self):
        usuario_id = usuarios_repo.crear_usuario("Test", "1234", "ADMIN")
        articulos_repo.crear_articulo("COD9", "Producto", None, None, 10.0, 5.0, 0)
        compras_repo.registrar_compra(usuario_id, [{"codigo": "COD9", "cantidad": 5, "costo_unitario": 5.0}])

        venta_ok = self._vender(usuario_id, datetime(2026, 1, 1, 9, 0, 0))
        venta_anulada = self._vender(usuario_id, datetime(2026, 1, 1, 9, 30, 0))
        ventas_repo.anular_venta(venta_anulada, usuario_id, "Test")

        cierre = self._cerrar(usuario_id, datetime(2026, 1, 1, 10, 0, 0))

        # El total del cierre solo contó la confirmada (la anulada no
        # suma, ver _sumar_ventas_por_origen_y_metodo).
        self.assertEqual(cierre["ventas_efectivo"], 10.0)

        detalle = turnos_repo.detalle_cierre(cierre["id"])
        ids = {v["id"]: v["estado"] for v in detalle["ventas"]}
        self.assertEqual(ids[venta_ok], dominio.VENTA_CONFIRMADA)
        self.assertEqual(ids[venta_anulada], dominio.VENTA_ANULADA)

    def test_venta_en_el_mismo_segundo_que_un_cierre_no_se_pierde(self):
        # Reproduce el bug real: una venta hecha justo al abrir el turno
        # siguiente, en el MISMO segundo de reloj que el cierre anterior
        # (pero microsegundos después). Con fecha_cierre y ventas.fecha
        # grabados con precisión de un solo segundo, los dos strings
        # empataban y esta venta quedaba afuera de los DOS turnos: no la
        # contaba el cierre que se estaba cerrando (llegó después del
        # corte) ni el siguiente (el ">" estricto la excluía por el
        # empate) -- ver el porqué de la precisión de microsegundos en
        # ventas_repo.confirmar_venta / turnos_repo.cerrar_turno.
        usuario_id = usuarios_repo.crear_usuario("Test", "1234", "ADMIN")
        articulos_repo.crear_articulo("COD9", "Producto", None, None, 10.0, 5.0, 0)
        compras_repo.registrar_compra(usuario_id, [{"codigo": "COD9", "cantidad": 5, "costo_unitario": 5.0}])

        self._cerrar(usuario_id, datetime(2026, 1, 1, 10, 0, 0, 500000))
        venta_2 = self._vender(usuario_id, datetime(2026, 1, 1, 10, 0, 0, 800000))
        cierre_2 = self._cerrar(usuario_id, datetime(2026, 1, 1, 11, 0, 0))

        detalle_2 = turnos_repo.detalle_cierre(cierre_2["id"])
        self.assertEqual([v["id"] for v in detalle_2["ventas"]], [venta_2])
        self.assertEqual(cierre_2["ventas_efectivo"], 10.0)


class TestResumenDelDia(BaseConBaseTemporal):
    """El reporte de un día abierto por turno (turnos_repo.resumen_del_dia)."""

    def setUp(self):
        super().setUp()
        self.admin_id = usuarios_repo.crear_usuario("Admin", "1234", "ADMIN")
        self.lucia_id = usuarios_repo.crear_usuario("Lucia", "1234", "EMPLEADA")
        self.pedro_id = usuarios_repo.crear_usuario("Pedro", "1234", "EMPLEADA")
        articulos_repo.crear_articulo("COD9", "Producto", None, None, 10.0, 5.0, 0)
        compras_repo.registrar_compra(self.admin_id, [{"codigo": "COD9", "cantidad": 50, "costo_unitario": 5.0}])

    def _vender(self, momento, total, metodo="EFECTIVO", usuario_id=None):
        with mock.patch("repositories.ventas_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = momento
            return ventas_repo.confirmar_venta(
                usuario_id or self.lucia_id,
                [{"codigo": "COD9", "descripcion": "Producto", "cantidad": 1, "precio_unitario": total}],
                [{"metodo": metodo, "monto": total}],
            )

    def _cerrar(self, momento, usuario_id=None):
        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = momento
            datetime_mock.fromisoformat = datetime.fromisoformat
            return turnos_repo.cerrar_turno(usuario_id or self.lucia_id)

    def _resumen(self, dia, ahora):
        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = ahora
            datetime_mock.fromisoformat = datetime.fromisoformat
            return turnos_repo.resumen_del_dia(dia)

    def test_un_dia_con_mañana_y_tarde_cerradas_y_la_noche_en_curso(self):
        # Lunes 5 de enero de 2026. Mañana cerrada a las 14:05, Tarde
        # cerrada a las 22:10 y la Noche todavía abierta a las 23:00.
        self._cerrar(datetime(2026, 1, 5, 6, 0))  # punto de partida, sin ventas
        self._vender(datetime(2026, 1, 5, 9, 0), 10.0)
        self._cerrar(datetime(2026, 1, 5, 14, 5), self.lucia_id)
        self._vender(datetime(2026, 1, 5, 15, 0), 20.0)
        self._vender(datetime(2026, 1, 5, 16, 0), 30.0, metodo="DIGITAL")
        self._cerrar(datetime(2026, 1, 5, 22, 10), self.pedro_id)
        self._vender(datetime(2026, 1, 5, 22, 30), 5.0)

        resumen = self._resumen(date(2026, 1, 5), datetime(2026, 1, 5, 23, 0))
        manana, tarde, noche = resumen["turnos"]

        self.assertEqual([t["etiqueta"] for t in resumen["turnos"]], ["Mañana", "Tarde", "Noche"])
        self.assertEqual([t["estado"] for t in resumen["turnos"]],
                         [turnos_repo.ESTADO_CERRADO, turnos_repo.ESTADO_CERRADO, turnos_repo.ESTADO_EN_CURSO])

        self.assertEqual(manana["total"], 10.0)
        self.assertEqual(manana["responsables"], ["Lucia"])
        self.assertEqual(manana["cantidad_ventas"], 1)

        self.assertEqual(tarde["efectivo"], 20.0)
        self.assertEqual(tarde["digital"], 30.0)
        self.assertEqual(tarde["total"], 50.0)
        self.assertEqual(tarde["kiosko"], 50.0)
        self.assertEqual(tarde["responsables"], ["Pedro"])
        self.assertEqual(tarde["cantidad_ventas"], 2)

        # La Noche sigue abierta: se ve lo que lleva, sin responsable ni hora de cierre.
        self.assertEqual(noche["total"], 5.0)
        self.assertEqual(noche["responsables"], [])
        self.assertIsNone(noche["cerrado_a"])

        self.assertEqual(resumen["total"]["total"], 65.0)
        self.assertEqual(resumen["total"]["cantidad_ventas"], 4)

    def test_el_domingo_tiene_dos_turnos_y_un_dia_pasado_sin_cierres_queda_sin_cerrar(self):
        resumen = self._resumen(date(2026, 1, 4), datetime(2026, 1, 7, 10, 0))
        self.assertEqual([t["etiqueta"] for t in resumen["turnos"]], ["Domingo T1", "Domingo T2"])
        self.assertTrue(all(t["estado"] == turnos_repo.ESTADO_SIN_CERRAR for t in resumen["turnos"]))
        self.assertEqual(resumen["total"]["total"], 0.0)

    def test_turnos_que_todavia_no_empezaron_estan_pendientes(self):
        # Sin ningún cierre previo la ventana abierta arranca ahora (10:00,
        # Mañana): la Tarde y la Noche todavía no tienen por qué estar cerradas.
        resumen = self._resumen(date(2026, 1, 5), datetime(2026, 1, 5, 10, 0))
        estados = [t["estado"] for t in resumen["turnos"]]
        self.assertEqual(estados, [turnos_repo.ESTADO_EN_CURSO, turnos_repo.ESTADO_PENDIENTE,
                                   turnos_repo.ESTADO_PENDIENTE])

    def test_un_turno_cerrado_dos_veces_suma_los_dos_cierres(self):
        self._cerrar(datetime(2026, 1, 5, 6, 0))
        self._vender(datetime(2026, 1, 5, 9, 0), 10.0)
        self._cerrar(datetime(2026, 1, 5, 12, 0), self.lucia_id)
        self._vender(datetime(2026, 1, 5, 12, 30), 7.0)
        self._cerrar(datetime(2026, 1, 5, 14, 5), self.pedro_id)

        manana = self._resumen(date(2026, 1, 5), datetime(2026, 1, 5, 15, 0))["turnos"][0]
        self.assertEqual(manana["estado"], turnos_repo.ESTADO_CERRADO)
        self.assertEqual(manana["total"], 17.0)
        self.assertEqual(manana["cantidad_ventas"], 2)
        self.assertEqual(manana["responsables"], ["Lucia", "Pedro"])

    def test_la_noche_que_cruza_la_medianoche_se_cuenta_en_el_dia_que_arranco(self):
        self._cerrar(datetime(2026, 1, 5, 22, 5))  # arranca la Noche del lunes 5
        self._vender(datetime(2026, 1, 5, 23, 30), 10.0)
        self._vender(datetime(2026, 1, 6, 2, 0), 20.0)
        self._cerrar(datetime(2026, 1, 6, 6, 30), self.pedro_id)

        ahora = datetime(2026, 1, 6, 7, 0)
        noche_del_5 = self._resumen(date(2026, 1, 5), ahora)["turnos"][2]
        self.assertEqual(noche_del_5["estado"], turnos_repo.ESTADO_CERRADO)
        self.assertEqual(noche_del_5["total"], 30.0)

        # Esas dos ventas NO aparecen en el día 6, aunque pasaron de la medianoche.
        dia_6 = self._resumen(date(2026, 1, 6), ahora)
        self.assertEqual(dia_6["total"]["total"], 0.0)

    def test_muestra_la_diferencia_solo_si_el_admin_ya_conto_el_sobre(self):
        cierre_inicial = self._cerrar(datetime(2026, 1, 5, 6, 0))
        self._vender(datetime(2026, 1, 5, 9, 0), 10.0)
        cierre_manana = self._cerrar(datetime(2026, 1, 5, 14, 5))
        self._vender(datetime(2026, 1, 5, 15, 0), 20.0)
        self._cerrar(datetime(2026, 1, 5, 22, 10))

        # La Mañana tiene dos cierres (el inicial, vacío, y el de las 14:05):
        # recién cuenta como verificada cuando el Admin contó los dos.
        turnos_repo.verificar_cierre(cierre_manana["id"], 8.0, self.admin_id)
        manana = self._resumen(date(2026, 1, 5), datetime(2026, 1, 5, 23, 0))["turnos"][0]
        self.assertFalse(manana["verificado"])

        turnos_repo.verificar_cierre(cierre_inicial["id"], 0.0, self.admin_id)

        manana, tarde, _ = self._resumen(date(2026, 1, 5), datetime(2026, 1, 5, 23, 0))["turnos"]
        self.assertTrue(manana["verificado"])
        self.assertEqual(manana["diferencia"], -2.0)
        self.assertFalse(tarde["verificado"])
        self.assertIsNone(tarde["diferencia"])

    def _vender_impresiones(self, momento, cantidad, metodo="EFECTIVO"):
        total = cantidad * 150.0
        with mock.patch("repositories.ventas_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = momento
            return ventas_repo.confirmar_venta(
                self.lucia_id,
                [{"codigo": dominio.CODIGO_ARTICULO_IMPRESIONES, "descripcion": "IMPRESIONES",
                  "cantidad": cantidad, "precio_unitario": 150.0}],
                [{"metodo": metodo, "monto": total}],
            )


    def _anular(self, venta_id, momento):
        """Anula la venta como si fuera `momento` (la fecha de anulación es
        lo que decide si fue antes o después del cierre del turno)."""
        with mock.patch("repositories.ventas_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = momento
            ventas_repo.anular_venta(venta_id, self.admin_id, "Test")


    def test_una_venta_anulada_despues_del_cierre_sigue_en_su_columna(self):
        # El cierre es una foto: la venta anulada después sigue sumada en
        # Impresiones aunque se anule más tarde.
        articulos_repo.crear_articulo(dominio.CODIGO_ARTICULO_IMPRESIONES, "IMPRESIONES", None, None, 150.0, 0.0, 0)
        self._cerrar(datetime(2026, 1, 5, 6, 0))
        venta_impresiones = self._vender_impresiones(datetime(2026, 1, 5, 9, 0), 2)
        self._cerrar(datetime(2026, 1, 5, 14, 5))
        self._anular(venta_impresiones, datetime(2026, 1, 5, 18, 0))

        manana = self._resumen(date(2026, 1, 5), datetime(2026, 1, 5, 19, 0))["turnos"][0]

        self.assertEqual(manana["total"], 300.0)
        self.assertEqual(manana["impresiones"], 300.0)
        self.assertEqual(manana["kiosko"], 0.0)
        self.assertEqual(manana["cantidad_anuladas"], 1)

    def test_una_venta_anulada_antes_del_cierre_no_figura_en_ninguna_columna(self):
        articulos_repo.crear_articulo(dominio.CODIGO_ARTICULO_IMPRESIONES, "IMPRESIONES", None, None, 150.0, 0.0, 0)
        self._cerrar(datetime(2026, 1, 5, 6, 0))
        venta_impresiones = self._vender_impresiones(datetime(2026, 1, 5, 9, 0), 2)
        self._anular(venta_impresiones, datetime(2026, 1, 5, 11, 0))
        self._cerrar(datetime(2026, 1, 5, 14, 5))

        manana = self._resumen(date(2026, 1, 5), datetime(2026, 1, 5, 19, 0))["turnos"][0]

        self.assertEqual(manana["total"], 0.0)
        self.assertEqual(manana["impresiones"], 0.0)
        self.assertEqual(manana["kiosko"], 0.0)

    def test_impresiones_sale_aparte_de_kiosko_en_turnos_cerrados_y_en_curso(self):
        articulos_repo.crear_articulo(dominio.CODIGO_ARTICULO_IMPRESIONES, "IMPRESIONES", None, None, 150.0, 0.0, 0)
        self._cerrar(datetime(2026, 1, 5, 6, 0))
        self._vender(datetime(2026, 1, 5, 9, 0), 10.0)
        self._vender_impresiones(datetime(2026, 1, 5, 10, 0), 2)                    # $300 en efectivo
        self._vender_impresiones(datetime(2026, 1, 5, 11, 0), 1, metodo="DIGITAL")  # $150 digital
        self._cerrar(datetime(2026, 1, 5, 14, 5))
        self._vender_impresiones(datetime(2026, 1, 5, 15, 0), 4)                    # Tarde, todavía abierta

        resumen = self._resumen(date(2026, 1, 5), datetime(2026, 1, 5, 16, 0))
        manana, tarde, noche = resumen["turnos"]

        # Cerrada: el cierre guardó $460 como Kiosko; $450 son impresiones.
        self.assertEqual(manana["kiosko"], 10.0)
        self.assertEqual(manana["impresiones"], 450.0)
        self.assertEqual(manana["total"], 460.0)
        # El cobro por medio de pago no cambia: las impresiones también entraron ahí.
        self.assertEqual(manana["efectivo"], 310.0)
        self.assertEqual(manana["digital"], 150.0)
        # En curso: se ve en vivo, igual que el resto de la plata.
        self.assertEqual(tarde["estado"], turnos_repo.ESTADO_EN_CURSO)
        self.assertEqual(tarde["kiosko"], 0.0)
        self.assertEqual(tarde["impresiones"], 600.0)
        self.assertEqual(noche["impresiones"], 0.0)

        total = resumen["total"]
        self.assertEqual(total["impresiones"], 1050.0)
        self.assertEqual(total["kiosko"] + total["impresiones"], total["total"])

    def test_el_resumen_del_turno_en_curso_trae_las_impresiones_sin_sacarlas_de_kiosko(self):
        # Cierre de Turno le muestra al dueño cuánto se vendió en Impresiones, pero
        # ese importe ya está dentro de Kiosko (que lleva el desglose ef./dig.): no
        # se le resta, y solo cuenta lo confirmado del turno que sigue abierto.
        articulos_repo.crear_articulo(dominio.CODIGO_ARTICULO_IMPRESIONES, "IMPRESIONES", None, None, 150.0, 0.0, 0)
        self._vender_impresiones(datetime(2026, 1, 5, 5, 30), 9)                    # turno anterior: no cuenta
        self._cerrar(datetime(2026, 1, 5, 6, 0))
        self._vender(datetime(2026, 1, 5, 7, 0), 10.0)
        self._vender_impresiones(datetime(2026, 1, 5, 8, 0), 2)                     # $300 en efectivo
        self._vender_impresiones(datetime(2026, 1, 5, 9, 0), 1, metodo="DIGITAL")   # $150 digital
        anulada = self._vender_impresiones(datetime(2026, 1, 5, 9, 30), 4)
        self._anular(anulada, datetime(2026, 1, 5, 9, 40))                          # anulada: no cuenta
        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 1, 5, 10, 0)
            datetime_mock.fromisoformat = datetime.fromisoformat
            resumen = turnos_repo.resumen_turno_actual()

        self.assertEqual(resumen["impresiones"], 450.0)
        self.assertEqual(resumen["kiosko_efectivo"], 310.0)
        self.assertEqual(resumen["kiosko_digital"], 150.0)
        self.assertEqual(resumen["ventas_efectivo"], 310.0)
        # Impresiones es un desglose de Kiosko: no se suma otra vez.
        self.assertEqual(resumen["ventas_total"], 460.0)

    def test_cuenta_las_ventas_anuladas_aparte_y_no_las_suma_al_total(self):
        self._cerrar(datetime(2026, 1, 5, 6, 0))
        self._vender(datetime(2026, 1, 5, 9, 0), 10.0)
        anulada = self._vender(datetime(2026, 1, 5, 9, 30), 99.0)
        ventas_repo.anular_venta(anulada, self.admin_id, "Test")
        self._cerrar(datetime(2026, 1, 5, 14, 5))

        manana = self._resumen(date(2026, 1, 5), datetime(2026, 1, 5, 15, 0))["turnos"][0]
        self.assertEqual(manana["total"], 10.0)
        self.assertEqual(manana["cantidad_ventas"], 1)
        self.assertEqual(manana["cantidad_anuladas"], 1)

    def test_un_cierre_hecho_tras_dias_sin_cerrar_se_avisa_el_dia_en_que_se_hizo(self):
        # El lunes 5 a la noche se cierra por primera vez y el siguiente cierre es
        # recién el jueves 8 a las 19:58: cubre desde el lunes, así que queda anotado
        # en la Noche del lunes 5 y NO en las filas del jueves.
        self._cerrar(datetime(2026, 1, 5, 23, 58))
        self._vender(datetime(2026, 1, 7, 12, 0), 40.0)
        self._cerrar(datetime(2026, 1, 8, 19, 58), self.pedro_id)
        ahora = datetime(2026, 1, 8, 20, 0)

        jueves = self._resumen(date(2026, 1, 8), ahora)

        self.assertEqual(len(jueves["cierres_de_otro_dia"]), 1)
        aviso = jueves["cierres_de_otro_dia"][0]
        self.assertEqual((aviso["fecha"], aviso["turno"], aviso["etiqueta"]), ("2026-01-05", "NOCHE", "Noche"))
        self.assertEqual(aviso["responsable"], "Pedro")
        self.assertTrue(aviso["cerrado_a"].startswith("2026-01-08T19:58"), aviso["cerrado_a"])
        # Las filas del jueves quedan en cero; la plata está en el día anotado.
        self.assertEqual(jueves["total"]["total"], 0.0)
        lunes = self._resumen(date(2026, 1, 5), ahora)
        self.assertEqual(lunes["turnos"][2]["total"], 40.0)
        # Y en ese día el turno queda marcado como cerrado otro día (la pantalla lo aclara).
        self.assertTrue(lunes["turnos"][2]["cerrado_otro_dia"])
        # Ni el lunes (donde quedó anotado) ni los días del medio (no se cerró nada
        # en ellos) tienen nada que avisar.
        for dia in (date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)):
            with self.subTest(dia=dia):
                self.assertEqual(self._resumen(dia, ahora)["cierres_de_otro_dia"], [])

    def test_la_noche_cerrada_a_la_madrugada_y_un_turno_cerrado_tarde_el_mismo_dia_no_se_avisan(self):
        self._cerrar(datetime(2026, 1, 5, 22, 5))                       # arranca la Noche del lunes 5
        self._cerrar(datetime(2026, 1, 6, 6, 10), self.pedro_id)        # la cierra a la madrugada: lo normal
        self._cerrar(datetime(2026, 1, 6, 23, 0), self.pedro_id)        # la Mañana del 6, cerrada tardísimo pero el mismo día

        ahora = datetime(2026, 1, 7, 8, 0)
        self.assertEqual(self._resumen(date(2026, 1, 6), ahora)["cierres_de_otro_dia"], [])
        # La Noche del 5, cerrada a la madrugada, y la Mañana del 6, cerrada tarde pero el mismo
        # día, no se marcan como cerradas otro día.
        self.assertFalse(self._resumen(date(2026, 1, 5), ahora)["turnos"][2]["cerrado_otro_dia"])
        self.assertFalse(self._resumen(date(2026, 1, 6), ahora)["turnos"][0]["cerrado_otro_dia"])

    def test_un_turno_cerrado_pasado_su_vencimiento_al_dia_siguiente_si_se_avisa(self):
        self._cerrar(datetime(2026, 1, 5, 22, 5))
        self._cerrar(datetime(2026, 1, 6, 10, 0), self.pedro_id)         # la Noche del 5, cerrada a las 10 (vence 06:15)

        avisos = self._resumen(date(2026, 1, 6), datetime(2026, 1, 6, 11, 0))["cierres_de_otro_dia"]

        self.assertEqual([(a["fecha"], a["turno"]) for a in avisos], [("2026-01-05", "NOCHE")])


class TestTurnosFaltantes(BaseConBaseTemporal):
    def test_turno_cerrado_no_aparece_pero_los_vencidos_sin_cerrar_si(self):
        usuario_id = usuarios_repo.crear_usuario("Test", "1234", "ADMIN")

        # Primer (y único) cierre: arranca a las 10:00 del lunes 5 de
        # enero de 2026, turno MAÑANA.
        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 1, 5, 10, 0, 0)
            datetime_mock.fromisoformat = datetime.fromisoformat
            turnos_repo.cerrar_turno(usuario_id)

        # "Ahora" es ese mismo lunes a las 20:00: todos los turnos de los
        # días 1 a 4 de enero (y el Mañana del día 5, recién cerrado) ya
        # vencieron con su gracia de 40 min.
        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 1, 5, 20, 0, 0)
            faltantes = turnos_repo.turnos_faltantes()

        claves = {(f["fecha"], f["turno"]) for f in faltantes}

        # El turno recién cerrado no figura como faltante...
        self.assertNotIn((date(2026, 1, 5), "MAÑANA"), claves)
        # ...pero un turno vencido de un día anterior que nunca se cerró, sí.
        self.assertIn((date(2026, 1, 1), "TARDE"), claves)
        # El domingo 4 de enero no tiene turno Tarde (2 turnos de 12hs).
        self.assertIn((date(2026, 1, 4), "MAÑANA"), claves)
        self.assertNotIn((date(2026, 1, 4), "TARDE"), claves)
        # La Tarde de hoy (día 5) todavía no venció (recién son las 20:00,
        # vence a las 22:40): no debería figurar todavía.
        self.assertNotIn((date(2026, 1, 5), "TARDE"), claves)


class TestUsuariosDeTurnoFaltante(BaseConBaseTemporal):
    def _vender(self, usuario_id, momento):
        with mock.patch("repositories.ventas_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = momento
            ventas_repo.confirmar_venta(
                usuario_id,
                [{"codigo": "COD9", "descripcion": "Producto", "cantidad": 1,
                  "precio_unitario": 10.0}],
                [{"metodo": "EFECTIVO", "monto": 10.0}],
            )

    def _loguear(self, usuario_id, clave, momento):
        with mock.patch("repositories.usuarios_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = momento
            usuarios_repo.autenticar(usuario_id, clave)

    def test_turno_faltante_muestra_quien_vendio_incluyendo_noche_que_cruza_medianoche(self):
        vendedora_id = usuarios_repo.crear_usuario("Vendedora Noche", "1234", "EMPLEADA")
        articulos_repo.crear_articulo("COD9", "Producto", None, None, 10.0, 5.0, 0)
        compras_repo.registrar_compra(vendedora_id, [{"codigo": "COD9", "cantidad": 5, "costo_unitario": 5.0}])

        # Una venta a las 23:30 del 5 de enero (Noche, mismo día que
        # arranca) y otra a las 02:00 del 6 (Noche, ya pasada la
        # medianoche) — las dos tienen que atribuirse al turno Noche del
        # día 5, no al del día 6.
        self._vender(vendedora_id, datetime(2026, 1, 5, 23, 30, 0))
        self._vender(vendedora_id, datetime(2026, 1, 6, 2, 0, 0))

        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 1, 6, 10, 0, 0)
            datetime_mock.fromisoformat = datetime.fromisoformat
            faltantes = turnos_repo.turnos_faltantes()

        slot_noche_5 = next(f for f in faltantes if f["fecha"] == date(2026, 1, 5) and f["turno"] == "NOCHE")
        self.assertEqual(slot_noche_5["usuarios"], ["Vendedora Noche"])

        slot_noche_6 = next((f for f in faltantes if f["fecha"] == date(2026, 1, 6) and f["turno"] == "NOCHE"), None)
        self.assertIsNone(slot_noche_6)  # el 6 a las 10:00 el turno Noche del día 6 ni empezó a vencer

        # Un turno vencido sin ninguna venta ni login muestra la lista vacía.
        slot_manana_5 = next(f for f in faltantes if f["fecha"] == date(2026, 1, 5) and f["turno"] == "MAÑANA")
        self.assertEqual(slot_manana_5["usuarios"], [])

    def test_turno_faltante_sin_ventas_muestra_quien_se_logueo(self):
        # Una empleada se loguea a las 07:00 del 5 de enero (turno Mañana)
        # pero no llega a cargar ninguna venta: sin el login, ese turno
        # faltante no tendría a quién preguntarle.
        empleada_id = usuarios_repo.crear_usuario("Empleada Sin Ventas", "1234", "EMPLEADA")
        self._loguear(empleada_id, "1234", datetime(2026, 1, 5, 7, 0, 0))

        with mock.patch("repositories.turnos_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 1, 5, 20, 0, 0)
            datetime_mock.fromisoformat = datetime.fromisoformat
            faltantes = turnos_repo.turnos_faltantes()

        slot_manana_5 = next(f for f in faltantes if f["fecha"] == date(2026, 1, 5) and f["turno"] == "MAÑANA")
        self.assertEqual(slot_manana_5["usuarios"], ["Empleada Sin Ventas"])


class TestResumenPorTurno(BaseConBaseTemporal):
    def _vender(self, usuario_id, momento, metodo="EFECTIVO"):
        with mock.patch("repositories.ventas_repo.datetime") as datetime_mock:
            datetime_mock.now.return_value = momento
            ventas_repo.confirmar_venta(
                usuario_id,
                [{"codigo": "COD8", "descripcion": "Producto", "cantidad": 1,
                  "precio_unitario": 10.0}],
                [{"metodo": metodo, "monto": 10.0}],
            )

    def test_desglosa_ventas_por_turno(self):
        usuario_id = usuarios_repo.crear_usuario("Test", "1234", "ADMIN")
        articulos_repo.crear_articulo("COD8", "Producto", None, None, 10.0, 5.0, 0)
        compras_repo.registrar_compra(usuario_id, [{"codigo": "COD8", "cantidad": 10, "costo_unitario": 5.0}])

        # Un lunes: una venta de Mañana y dos de Tarde (una en efectivo,
        # otra digital) — Noche queda sin ninguna venta ese día.
        self._vender(usuario_id, datetime(2026, 1, 5, 8, 0, 0))
        self._vender(usuario_id, datetime(2026, 1, 5, 15, 0, 0))
        self._vender(usuario_id, datetime(2026, 1, 5, 16, 0, 0), metodo="DIGITAL")

        filas = reportes_repo.resumen_por_turno("2026-01-05", "2026-01-05")
        por_turno = {f["turno"]: f for f in filas}

        self.assertEqual(por_turno["MAÑANA"]["total"], 10.0)
        self.assertEqual(por_turno["MAÑANA"]["cantidad_ventas"], 1)

        self.assertEqual(por_turno["TARDE"]["total"], 20.0)
        self.assertEqual(por_turno["TARDE"]["cantidad_ventas"], 2)
        self.assertEqual(por_turno["TARDE"]["efectivo"], 10.0)
        self.assertEqual(por_turno["TARDE"]["digital"], 10.0)

        self.assertEqual(por_turno["NOCHE"]["total"], 0.0)
        self.assertEqual(por_turno["NOCHE"]["cantidad_ventas"], 0)




class TestRankingVentas(BaseConBaseTemporal):
    """El ranking de artículos cuenta solo ventas confirmadas de Kiosko."""

    def setUp(self):
        super().setUp()
        self.usuario_id = usuarios_repo.crear_usuario("Test", "1234", "ADMIN")
        self.hoy = turnos.dia_en_que_empezo_el_turno(datetime.now()).isoformat()

    def _ranking(self, ordenar_por="cantidad"):
        return reportes_repo.ranking_ventas(self.hoy, self.hoy, ordenar_por)

    def _articulo(self, codigo, nombre, cantidad=10):
        articulos_repo.crear_articulo(codigo, nombre, None, None, 100.0, 50.0, 0)
        compras_repo.registrar_compra(
            self.usuario_id,
            [{"codigo": codigo, "cantidad": cantidad, "costo_unitario": 50.0}],
        )

    def _vender(self, codigo, nombre, cantidad):
        return ventas_repo.confirmar_venta(
            self.usuario_id,
            [{"codigo": codigo, "descripcion": nombre, "cantidad": cantidad, "precio_unitario": 100.0}],
            [{"metodo": "EFECTIVO", "monto": cantidad * 100.0}],
        )

    def test_incluye_articulo_de_kiosko(self):
        self._articulo("COD9", "Producto")
        self._vender("COD9", "Producto", 3)

        fila = next(f for f in self._ranking() if f["descripcion"] == "Producto")
        self.assertEqual(fila["codigo"], "COD9")
        self.assertEqual(fila["cantidad"], 3)
        self.assertEqual(fila["importe"], 300.0)

    def test_ordena_articulos_por_cantidad(self):
        self._articulo("COD9", "Producto")
        self._articulo("COD8", "Otro")
        self._vender("COD9", "Producto", 5)
        self._vender("COD8", "Otro", 1)

        filas = self._ranking()
        self.assertEqual([f["descripcion"] for f in filas], ["Producto", "Otro"])
        self.assertEqual(filas[0]["cantidad"], 5)

    def test_no_incluye_ventas_anuladas_ni_fuera_de_rango(self):
        self._articulo("COD9", "Producto")
        venta_id = self._vender("COD9", "Producto", 1)
        ventas_repo.anular_venta(venta_id, self.usuario_id, "Test")

        self.assertEqual(self._ranking(), [])
        self.assertEqual(reportes_repo.ranking_ventas("2000-01-01", "2000-01-01"), [])



if __name__ == "__main__":
    unittest.main()
