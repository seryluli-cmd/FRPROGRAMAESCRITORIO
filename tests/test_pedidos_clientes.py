"""
tests/test_pedidos_clientes.py
===============================
PEDIDOS DE CLIENTES (pedido del dueño, 2026-11-03): mercadería que NO tenemos y
que los clientes vienen a buscar.

- Escribirlo da "1 cliente lo pidió"; escribirlo de nuevo (con otras mayúsculas,
  tildes o espacios), tocar un parecido o el +1 suma en el MISMO renglón.
- Cada cliente queda con su fecha y hora y el operador que lo anotó.
- La lista va con lo más pedido arriba.
- "YA LO TRAJIMOS" (cualquiera) lo pasa al historial; si lo vuelven a pedir,
  arranca un renglón nuevo con 1.
- Renombrar, Juntar y Borrar: solo el Administrador, y nada se borra de la base.

Por ahora es solo la parte de adentro (repositories/pedidos_clientes_repo.py): la
pantalla viene después.

Se ejecutan con:

    python -m unittest discover tests -p "test_pedidos_clientes.py"
"""

import sqlite3
import unittest
from unittest import mock

import database
import database_migraciones
import dominio
from database import conexion_db
from repositories import pedidos_clientes_repo as repo
from repositories import usuarios_repo
from base import BaseConBaseTemporal

DIA = "2026-11-03"


class _ConPedidosClientes(BaseConBaseTemporal):
    def setUp(self):
        super().setUp()
        self.lucia_id = usuarios_repo.crear_usuario("Lucia", "1234", dominio.ROL_EMPLEADA)
        self.gaby_id = usuarios_repo.crear_usuario("Gaby", "1234", dominio.ROL_EMPLEADA)
        self.admin_id = usuarios_repo.crear_usuario("Sergio", "1234", dominio.ROL_ADMIN)
        # El reloj del repo queda quieto en la hora que pone cada prueba: así se
        # puede comparar la fecha y hora exacta que quedó anotada.
        self._a_las("10:00")
        parche = mock.patch.object(repo, "_ahora", side_effect=lambda: self._hora)
        parche.start()
        self.addCleanup(parche.stop)

    def _a_las(self, hora: str):
        self._hora = f"{DIA}T{hora}:00"
        return self._hora

    def _anotar(self, texto, quien=None):
        return repo.anotar(quien or self.lucia_id, texto)

    def _veces(self, pedido_id):
        """Cada cliente de un renglón: (fecha, quién lo anotó), en el orden en que se anotaron."""
        with conexion_db() as conexion:
            return [tuple(fila) for fila in conexion.execute(
                "SELECT fecha, usuario_id FROM pedidos_clientes_veces WHERE pedido_id = ? ORDER BY id",
                (pedido_id,),
            )]

    def _fila(self, pedido_id):
        with conexion_db() as conexion:
            return conexion.execute("SELECT * FROM pedidos_clientes WHERE id = ?", (pedido_id,)).fetchone()

    def _lista(self):
        return [(p["producto"], p["clientes"]) for p in repo.listar_pendientes()]


class TestAnotar(_ConPedidosClientes):
    def test_un_pedido_nuevo_arranca_con_un_cliente(self):
        anotado = self._anotar("Mantecol")

        self.assertEqual((anotado["producto"], anotado["clientes"], anotado["nuevo"]), ("Mantecol", 1, True))
        pendiente, = repo.listar_pendientes()
        self.assertEqual(pendiente["id"], anotado["pedido_id"])
        self.assertEqual((pendiente["producto"], pendiente["clientes"]), ("Mantecol", 1))
        self.assertEqual(pendiente["ultima_vez_por"], "Lucia")

    def test_lo_mismo_escrito_distinto_suma_en_el_mismo_renglon(self):
        primero = self._anotar("Mantecol")

        for clientes, escrito in enumerate(("mantecol", "MANTECOL ", "Mantecól", "  mantecol  ", "MANTECÓL"), start=2):
            with self.subTest(escrito=escrito):
                anotado = self._anotar(escrito, quien=self.gaby_id)
                self.assertEqual(anotado["pedido_id"], primero["pedido_id"])
                self.assertEqual((anotado["clientes"], anotado["nuevo"]), (clientes, False))
                # Se sigue viendo como lo escribió la primera.
                self.assertEqual(anotado["producto"], "Mantecol")
        self.assertEqual(self._lista(), [("Mantecol", 6)])

    def test_los_espacios_de_adentro_tambien_cuentan_como_uno(self):
        primero = self._anotar("Coca  Cola")
        self.assertEqual(primero["producto"], "Coca Cola")
        self.assertEqual(self._anotar("coca cola")["pedido_id"], primero["pedido_id"])
        # Pero otro producto es otro renglón.
        self.assertTrue(self._anotar("Coca Cola Zero")["nuevo"])
        self.assertEqual(self._lista(), [("Coca Cola", 2), ("Coca Cola Zero", 1)])

    def test_cada_vez_queda_con_su_fecha_y_hora_y_quien_lo_anoto(self):
        self._a_las("10:15")
        pedido_id = self._anotar("Mantecol", quien=self.lucia_id)["pedido_id"]
        self._a_las("18:40")
        self._anotar("mantecol", quien=self.gaby_id)

        self.assertEqual(self._veces(pedido_id), [
            (f"{DIA}T10:15:00", self.lucia_id),
            (f"{DIA}T18:40:00", self.gaby_id),
        ])
        fila = self._fila(pedido_id)
        self.assertEqual((fila["fecha"], fila["creado_por"]), (f"{DIA}T10:15:00", self.lucia_id))
        pendiente, = repo.listar_pendientes()
        self.assertEqual(pendiente["primera_vez"], f"{DIA}T10:15:00")
        self.assertEqual(pendiente["ultima_vez"], f"{DIA}T18:40:00")
        self.assertEqual(pendiente["ultima_vez_por"], "Gaby")

    def test_vacio_da_error_y_no_graba_nada(self):
        for escrito in ("", "   ", None):
            with self.subTest(escrito=escrito):
                with self.assertRaisesRegex(ValueError, "Escribí qué producto"):
                    self._anotar(escrito)
        self.assertEqual(repo.listar_pendientes(), [])

    def test_demasiado_largo_da_error_y_no_graba_nada(self):
        largo = dominio.LARGO_MAXIMO_PEDIDO_CLIENTE
        with self.assertRaisesRegex(ValueError, "muy largo"):
            self._anotar("x" * (largo + 1))
        self.assertEqual(repo.listar_pendientes(), [])
        # Justo el máximo, sí.
        self.assertEqual(self._anotar("x" * largo)["clientes"], 1)


class TestSumarUno(_ConPedidosClientes):
    def test_el_mas_uno_suma_un_cliente_con_quien_lo_anoto(self):
        pedido_id = self._anotar("Mantecol")["pedido_id"]
        self._a_las("11:30")

        self.assertEqual(repo.sumar_uno(self.gaby_id, pedido_id), 2)

        self.assertEqual(self._veces(pedido_id)[-1], (f"{DIA}T11:30:00", self.gaby_id))
        self.assertEqual(repo.listar_pendientes()[0]["ultima_vez_por"], "Gaby")

    def test_a_uno_traido_o_borrado_no_se_le_suma(self):
        traido = self._anotar("Mantecol")["pedido_id"]
        borrado = self._anotar("Manaos")["pedido_id"]
        repo.ya_lo_trajimos(self.lucia_id, traido)
        repo.borrar(self.admin_id, borrado)

        with self.assertRaisesRegex(ValueError, "traído"):
            repo.sumar_uno(self.gaby_id, traido)
        with self.assertRaisesRegex(ValueError, "ya no está en la lista"):
            repo.sumar_uno(self.gaby_id, borrado)
        self.assertEqual((len(self._veces(traido)), len(self._veces(borrado))), (1, 1))

    def test_a_uno_que_no_existe_no_se_le_suma(self):
        with self.assertRaisesRegex(ValueError, "no existe"):
            repo.sumar_uno(self.lucia_id, 999)


class TestParecidos(_ConPedidosClientes):
    def setUp(self):
        super().setUp()
        for texto, clientes in (("Mantecol", 3), ("Manteca", 1), ("Mantecol grande", 2), ("Coca Cola", 1)):
            for _ in range(clientes):
                self._anotar(texto)

    @staticmethod
    def _productos(parecidos):
        return [p["producto"] for p in parecidos]

    def test_trae_los_que_contienen_lo_escrito_lo_mas_pedido_arriba(self):
        self.assertEqual(self._productos(repo.parecidos("mante")), ["Mantecol", "Mantecol grande", "Manteca"])
        self.assertEqual(self._productos(repo.parecidos("cola")), ["Coca Cola"])
        self.assertEqual(self._productos(repo.parecidos("col gr")), ["Mantecol grande"])
        self.assertEqual(repo.parecidos("mante")[0]["clientes"], 3)

    def test_sin_importar_mayusculas_tildes_ni_espacios(self):
        for escrito in ("MANTE", "  Manté ", "mAnTe"):
            with self.subTest(escrito=escrito):
                self.assertEqual(self._productos(repo.parecidos(escrito)), ["Mantecol", "Mantecol grande", "Manteca"])

    def test_con_menos_de_dos_letras_no_trae_nada(self):
        self.assertEqual(dominio.LETRAS_MINIMAS_PARECIDOS, 2)
        for escrito in ("", "m", " m ", None):
            with self.subTest(escrito=escrito):
                self.assertEqual(repo.parecidos(escrito), [])
        self.assertEqual(len(repo.parecidos("ma")), 3)

    def test_respeta_el_limite(self):
        self.assertEqual(self._productos(repo.parecidos("mante", limite=2)), ["Mantecol", "Mantecol grande"])
        self.assertEqual(repo.parecidos("mante", limite=0), [])

    def test_los_traidos_y_los_borrados_no_salen(self):
        por_nombre = {p["producto"]: p["id"] for p in repo.listar_pendientes()}
        repo.ya_lo_trajimos(self.lucia_id, por_nombre["Manteca"])
        repo.borrar(self.admin_id, por_nombre["Mantecol grande"])
        self.assertEqual(self._productos(repo.parecidos("mante")), ["Mantecol"])

    def test_un_porcentaje_o_un_guion_bajo_no_son_comodines(self):
        self.assertEqual(repo.parecidos("%%"), [])
        self.assertEqual(repo.parecidos("__"), [])
        self._anotar("Pila AA 100%")
        self.assertEqual(self._productos(repo.parecidos("0%")), ["Pila AA 100%"])


class TestYaLoTrajimos(_ConPedidosClientes):
    def test_sale_de_pendientes_y_queda_en_el_historial_con_quien_y_cuando(self):
        pedido_id = self._anotar("Mantecol")["pedido_id"]
        self._anotar("mantecol", quien=self.gaby_id)
        self._anotar("Manaos")
        self._a_las("20:05")

        # Cualquier operador lo puede marcar, no hace falta ser Admin.
        repo.ya_lo_trajimos(self.gaby_id, pedido_id)

        self.assertEqual(self._lista(), [("Manaos", 1)])
        traido, = repo.listar_historial()
        self.assertEqual((traido["id"], traido["producto"], traido["clientes"]), (pedido_id, "Mantecol", 2))
        self.assertEqual((traido["traido_por_nombre"], traido["fecha_traido"]), ("Gaby", f"{DIA}T20:05:00"))
        self.assertEqual(traido["estado"], dominio.PEDIDO_CLIENTE_TRAIDO)

    def test_si_lo_vuelven_a_pedir_arranca_un_renglon_nuevo_con_uno(self):
        viejo = self._anotar("Mantecol")["pedido_id"]
        self._anotar("Mantecol")
        repo.ya_lo_trajimos(self.lucia_id, viejo)

        otra_vez = self._anotar("MANTECOL", quien=self.gaby_id)

        self.assertTrue(otra_vez["nuevo"])
        self.assertNotEqual(otra_vez["pedido_id"], viejo)
        self.assertEqual((otra_vez["producto"], otra_vez["clientes"]), ("MANTECOL", 1))
        self.assertEqual(self._lista(), [("MANTECOL", 1)])
        # El de antes sigue en el historial con sus 2 clientes.
        self.assertEqual([(p["id"], p["clientes"]) for p in repo.listar_historial()], [(viejo, 2)])

    def test_no_se_marca_dos_veces(self):
        pedido_id = self._anotar("Mantecol")["pedido_id"]
        repo.ya_lo_trajimos(self.lucia_id, pedido_id)
        with self.assertRaisesRegex(ValueError, "traído"):
            repo.ya_lo_trajimos(self.gaby_id, pedido_id)
        self.assertEqual(self._fila(pedido_id)["traido_por"], self.lucia_id)

    def test_el_historial_va_con_el_ultimo_que_se_trajo_primero(self):
        primero = self._anotar("Mantecol")["pedido_id"]
        segundo = self._anotar("Manaos")["pedido_id"]
        self._a_las("12:00")
        repo.ya_lo_trajimos(self.lucia_id, segundo)
        self._a_las("15:00")
        repo.ya_lo_trajimos(self.lucia_id, primero)

        self.assertEqual([p["producto"] for p in repo.listar_historial()], ["Mantecol", "Manaos"])


class TestOrdenDeLaLista(_ConPedidosClientes):
    def test_lo_mas_pedido_arriba_y_entre_iguales_el_ultimo_pedido(self):
        self._a_las("10:00")
        alfajor = self._anotar("Alfajor Jorgito")["pedido_id"]
        for hora in ("10:05", "10:06", "10:07"):
            self._a_las(hora)
            self._anotar("Mantecol", quien=self.gaby_id)
        self._a_las("10:30")
        self._anotar("Manaos")

        self.assertEqual(self._lista(), [("Mantecol", 3), ("Manaos", 1), ("Alfajor Jorgito", 1)])

        self._a_las("11:00")
        repo.sumar_uno(self.admin_id, alfajor)

        lista = repo.listar_pendientes()
        self.assertEqual([(p["producto"], p["clientes"]) for p in lista],
                         [("Mantecol", 3), ("Alfajor Jorgito", 2), ("Manaos", 1)])
        self.assertEqual((lista[1]["ultima_vez"], lista[1]["ultima_vez_por"]), (f"{DIA}T11:00:00", "Sergio"))
        self.assertEqual((lista[0]["ultima_vez"], lista[0]["ultima_vez_por"]), (f"{DIA}T10:07:00", "Gaby"))

    def test_dos_anotados_en_el_mismo_segundo_va_arriba_el_ultimo(self):
        self._anotar("Manaos")
        self._anotar("Mantecol")
        self.assertEqual(self._lista(), [("Mantecol", 1), ("Manaos", 1)])


class TestCorrecciones(_ConPedidosClientes):
    def test_la_empleada_no_puede_renombrar_juntar_ni_borrar(self):
        uno = self._anotar("Mantecool")["pedido_id"]
        otro = self._anotar("Mantecol")["pedido_id"]

        with self.assertRaisesRegex(PermissionError, "Solo un Administrador"):
            repo.renombrar(self.lucia_id, uno, "Mantecol grande")
        with self.assertRaises(PermissionError):
            repo.juntar(self.lucia_id, uno, otro)
        with self.assertRaises(PermissionError):
            repo.borrar(self.gaby_id, uno)

        self.assertEqual(self._lista(), [("Mantecol", 1), ("Mantecool", 1)])

    def test_renombrar_corrige_el_nombre_y_lo_que_se_anota_despues_suma_ahi(self):
        pedido_id = self._anotar("mantecool")["pedido_id"]

        repo.renombrar(self.admin_id, pedido_id, "  mantecol ")

        self.assertEqual(self._lista(), [("Mantecol", 1)])
        self.assertEqual(self._anotar("MANTECÓL")["pedido_id"], pedido_id)
        self.assertEqual(self._lista(), [("Mantecol", 2)])

    def test_renombrar_solo_las_mayusculas_de_si_mismo_se_puede(self):
        pedido_id = self._anotar("mantecol")["pedido_id"]
        repo.renombrar(self.admin_id, pedido_id, "MANTECOL")
        self.assertEqual(self._lista(), [("MANTECOL", 1)])

    def test_renombrar_con_el_nombre_de_otro_pendiente_pide_juntar(self):
        self._anotar("Mantecol")
        otro = self._anotar("Mantecol grande")["pedido_id"]

        with self.assertRaisesRegex(ValueError, "Juntar"):
            repo.renombrar(self.admin_id, otro, "mantecól")

        self.assertEqual(self._fila(otro)["producto"], "Mantecol grande")

    def test_renombrar_con_el_nombre_de_uno_ya_traido_se_puede(self):
        traido = self._anotar("Mantecol")["pedido_id"]
        repo.ya_lo_trajimos(self.lucia_id, traido)
        pedido_id = self._anotar("Mantecool")["pedido_id"]

        repo.renombrar(self.admin_id, pedido_id, "Mantecol")

        self.assertEqual(self._lista(), [("Mantecol", 1)])

    def test_renombrar_vacio_o_uno_traido_da_error(self):
        pedido_id = self._anotar("Mantecol")["pedido_id"]
        with self.assertRaisesRegex(ValueError, "Escribí"):
            repo.renombrar(self.admin_id, pedido_id, "  ")
        repo.ya_lo_trajimos(self.lucia_id, pedido_id)
        with self.assertRaisesRegex(ValueError, "traído"):
            repo.renombrar(self.admin_id, pedido_id, "Manaos")

    def test_juntar_pasa_todos_los_clientes_y_el_otro_queda_borrado(self):
        self._a_las("09:00")
        origen = self._anotar("Mantecol grande", quien=self.lucia_id)["pedido_id"]
        self._a_las("09:30")
        self._anotar("Mantecol grande", quien=self.gaby_id)
        self._a_las("12:00")
        destino = self._anotar("Mantecol", quien=self.admin_id)["pedido_id"]
        self._a_las("13:00")

        self.assertEqual(repo.juntar(self.admin_id, origen, destino), 3)

        self.assertEqual(self._lista(), [("Mantecol", 3)])
        # Cada cliente sigue con su fecha y quién lo anotó.
        self.assertEqual(sorted(self._veces(destino)), [
            (f"{DIA}T09:00:00", self.lucia_id),
            (f"{DIA}T09:30:00", self.gaby_id),
            (f"{DIA}T12:00:00", self.admin_id),
        ])
        self.assertEqual(self._veces(origen), [])
        # La primera vez es la más vieja de los dos.
        self.assertEqual(repo.listar_pendientes()[0]["primera_vez"], f"{DIA}T09:00:00")
        fila = self._fila(origen)
        self.assertEqual((fila["estado"], fila["borrado_por"], fila["fecha_borrado"], fila["juntado_con"]),
                         (dominio.PEDIDO_CLIENTE_BORRADO, self.admin_id, f"{DIA}T13:00:00", destino))
        self.assertEqual(repo.listar_historial(), [])

    def test_juntar_exige_dos_pendientes_distintos(self):
        uno = self._anotar("Mantecol")["pedido_id"]
        traido = self._anotar("Manaos")["pedido_id"]
        repo.ya_lo_trajimos(self.lucia_id, traido)

        with self.assertRaisesRegex(ValueError, "mismo pedido"):
            repo.juntar(self.admin_id, uno, uno)
        with self.assertRaisesRegex(ValueError, "traído"):
            repo.juntar(self.admin_id, uno, traido)
        with self.assertRaisesRegex(ValueError, "traído"):
            repo.juntar(self.admin_id, traido, uno)
        with self.assertRaisesRegex(ValueError, "no existe"):
            repo.juntar(self.admin_id, uno, 999)

        self.assertEqual((len(self._veces(uno)), len(self._veces(traido))), (1, 1))
        self.assertEqual(self._fila(uno)["estado"], dominio.PEDIDO_CLIENTE_PENDIENTE)

    def test_borrar_lo_saca_de_la_lista_pero_la_fila_queda(self):
        pedido_id = self._anotar("Mantecoll")["pedido_id"]
        self._a_las("16:20")

        repo.borrar(self.admin_id, pedido_id)

        self.assertEqual(repo.listar_pendientes(), [])
        self.assertEqual(repo.listar_historial(), [])
        fila = self._fila(pedido_id)
        self.assertEqual((fila["estado"], fila["borrado_por"], fila["fecha_borrado"], fila["juntado_con"]),
                         (dominio.PEDIDO_CLIENTE_BORRADO, self.admin_id, f"{DIA}T16:20:00", None))
        self.assertEqual(len(self._veces(pedido_id)), 1)
        with self.assertRaisesRegex(ValueError, "ya estaba borrado"):
            repo.borrar(self.admin_id, pedido_id)
        # Si lo vuelven a pedir, es un renglón nuevo.
        self.assertTrue(self._anotar("Mantecoll")["nuevo"])

    def test_borrar_uno_del_historial(self):
        pedido_id = self._anotar("Mantecol")["pedido_id"]
        repo.ya_lo_trajimos(self.lucia_id, pedido_id)
        repo.borrar(self.admin_id, pedido_id)
        self.assertEqual(repo.listar_historial(), [])


class TestLaBase(_ConPedidosClientes):
    def _insertar(self, conexion, clave, estado):
        conexion.execute(
            "INSERT INTO pedidos_clientes (fecha, producto, clave, creado_por, estado) VALUES (?, ?, ?, ?, ?)",
            (self._hora, clave, clave, self.lucia_id, estado),
        )

    def test_la_base_no_deja_dos_pendientes_iguales_pero_si_varios_traidos(self):
        with conexion_db() as conexion:
            self._insertar(conexion, "mantecol", dominio.PEDIDO_CLIENTE_PENDIENTE)
            self._insertar(conexion, "mantecol", dominio.PEDIDO_CLIENTE_TRAIDO)
            self._insertar(conexion, "mantecol", dominio.PEDIDO_CLIENTE_TRAIDO)
            self._insertar(conexion, "mantecol", dominio.PEDIDO_CLIENTE_BORRADO)
        with self.assertRaises(sqlite3.IntegrityError):
            with conexion_db() as conexion:
                self._insertar(conexion, "mantecol", dominio.PEDIDO_CLIENTE_PENDIENTE)

    def test_el_estado_tiene_que_ser_uno_de_dominio(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with conexion_db() as conexion:
                self._insertar(conexion, "mantecol", "TRAIDO")

    def test_una_base_vieja_sin_las_tablas_las_recibe_al_inicializar(self):
        # Como una base de antes del 2026-11-03: con datos, sin las dos tablas.
        with conexion_db() as conexion:
            conexion.execute("DROP TABLE pedidos_clientes_veces")
            conexion.execute("DROP TABLE pedidos_clientes")
            version = database_migraciones.version_de_la_base(conexion)

        database.inicializar_base_de_datos()

        with conexion_db() as conexion:
            nombres = {fila["name"] for fila in conexion.execute("SELECT name FROM sqlite_master")}
            self.assertEqual(database_migraciones.version_de_la_base(conexion), version)
        self.assertTrue({"pedidos_clientes", "pedidos_clientes_veces", "idx_pedidos_clientes_pendiente",
                         "idx_pedidos_clientes_veces_pedido"} <= nombres)
        # No se perdió nada de lo que había y se puede anotar.
        self.assertEqual(usuarios_repo.obtener_usuario(self.lucia_id)["nombre"], "Lucia")
        self.assertEqual(self._anotar("Mantecol")["clientes"], 1)


class TestCuentasDelPedidoCliente(unittest.TestCase):
    def test_limpio_para_mostrar(self):
        casos = {
            "  mantecol   grande ": "Mantecol grande",
            "coca COLA": "Coca COLA",
            "7UP": "7UP",
            "ñoquis": "Ñoquis",
            "": "",
            None: "",
        }
        for escrito, esperado in casos.items():
            with self.subTest(escrito=escrito):
                self.assertEqual(dominio.pedido_cliente_limpio(escrito), esperado)

    def test_la_clave_no_mira_mayusculas_tildes_ni_espacios(self):
        for escrito in ("Mantecól ", "MANTECOL", "  mantecol", "mantecol"):
            with self.subTest(escrito=escrito):
                self.assertEqual(dominio.clave_pedido_cliente(escrito), "mantecol")
        self.assertEqual(dominio.clave_pedido_cliente("Coca   Cola"), "coca cola")

    def test_revisar(self):
        self.assertEqual(dominio.revisar_pedido_cliente(" mantecól "), ("Mantecól", "mantecol"))
        with self.assertRaises(ValueError):
            dominio.revisar_pedido_cliente("   ")
        with self.assertRaises(ValueError):
            dominio.revisar_pedido_cliente("a" * (dominio.LARGO_MAXIMO_PEDIDO_CLIENTE + 1))

    def test_no_pisa_los_estados_de_gestion_impresiones(self):
        # Son otra cosa: los de los pedidos de impresiones siguen como estaban.
        self.assertEqual(dominio.ESTADOS_PEDIDO,
                         ("PENDIENTE", "RETIRADO", "SEÑA PERDIDA", "ANULADO"))
        self.assertEqual(len(set(dominio.ESTADOS_PEDIDO_CLIENTE)), 3)


if __name__ == "__main__":
    unittest.main()
