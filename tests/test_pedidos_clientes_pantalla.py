"""
tests/test_pedidos_clientes_pantalla.py
========================================
La pantalla de PEDIDOS DE CLIENTES (pedido del dueño, 2026-11-03, maqueta A): el
campo con GUARDAR, los parecidos mientras se escribe, el +1 y TRAJIMOS de cada
renglón, y RENOMBRAR / JUNTAR / BORRAR solo para el Administrador. Las reglas de
adentro, en tests/test_pedidos_clientes.py.

Se ejecutan con:

    python -m unittest discover tests
"""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

import dominio  # noqa: E402
from repositories import pedidos_clientes_repo, usuarios_repo  # noqa: E402
from ui.pedidos_clientes_window import (  # noqa: E402
    COLUMNA_CLIENTES, COLUMNA_MAS_UNO, COLUMNA_PRODUCTO, COLUMNA_TRAJIMOS, TEXTO_TRAJIMOS,
    DialogoHistorialPedidos, VentanaPedidosClientes,
)
from ui.utils import formato_fecha_hora  # noqa: E402
from base import BaseConBaseTemporal  # noqa: E402

_app = QApplication.instance() or QApplication([])

COLUMNA_ULTIMA_VEZ = 2
LOS_DEL_ADMIN = {"RENOMBRAR", "JUNTAR", "BORRAR"}


class _ConLaVentana(BaseConBaseTemporal):
    def setUp(self):
        super().setUp()
        self.lucia_id = usuarios_repo.crear_usuario("Lucia", "1234", dominio.ROL_EMPLEADA)
        self.gaby_id = usuarios_repo.crear_usuario("Gaby", "1234", dominio.ROL_EMPLEADA)
        self.admin_id = usuarios_repo.crear_usuario("Sergio", "1234", dominio.ROL_ADMIN)
        # Las preguntas Sí/No contestan que sí (salvo que la prueba diga otra cosa) y
        # los avisos no se abren.
        self.pregunta = mock.patch("ui.pedidos_clientes_window.confirmar", return_value=True).start()
        self.avisos = mock.patch("ui.pedidos_clientes_window.mostrar_aviso").start()
        # Un error que agarra manejar_errores abriría un cartel modal que nadie cierra:
        # que la prueba falle con su texto en vez de quedarse colgada.
        mock.patch("ui.utils.mostrar_error",
                   side_effect=lambda _padre, titulo, texto: self.fail(f"{titulo}: {texto}")).start()
        self.addCleanup(mock.patch.stopall)

    def _ventana(self, usuario_id=None):
        ventana = VentanaPedidosClientes(usuarios_repo.obtener_usuario(usuario_id or self.lucia_id))
        self.addCleanup(ventana.deleteLater)
        return ventana

    def _renglones(self, ventana):
        return [(ventana.tabla.item(fila, COLUMNA_PRODUCTO).text(), ventana.tabla.item(fila, COLUMNA_CLIENTES).text())
                for fila in range(ventana.tabla.rowCount())]

    def _fila_de(self, ventana, producto):
        return next(fila for fila in range(ventana.tabla.rowCount())
                    if ventana.tabla.item(fila, COLUMNA_PRODUCTO).text() == producto)

    def _apretar_mas_uno(self, ventana, producto):
        # Como si pasara un rato desde que se armó la lista (ver _recien_reordenada).
        ventana._reordenada_a -= 10
        ventana.tabla.cellWidget(self._fila_de(ventana, producto), COLUMNA_MAS_UNO).boton.click()


class TestAnotarDesdeLaPantalla(_ConLaVentana):
    def test_guardar_anota_y_la_segunda_vez_suma_en_el_mismo_renglon(self):
        ventana = self._ventana()
        ventana.campo.setText("Mantecol")
        ventana.boton_guardar.click()
        self.assertEqual(self._renglones(ventana), [("Mantecol", "1")])
        self.assertIn("Nuevo: 1 cliente pidió Mantecol", ventana.etiqueta_hecho.text())
        self.assertEqual(ventana.campo.text(), "")

        ventana.campo.setText("MANTECÓL ")
        ventana.boton_guardar.click()
        self.assertEqual(self._renglones(ventana), [("Mantecol", "2")])
        self.assertIn("ya son 2 clientes", ventana.etiqueta_hecho.text())
        self.assertEqual((ventana.indicador_productos.valor.text(), ventana.indicador_clientes.valor.text()),
                         ("1", "2"))

    def test_el_enter_de_verdad_guarda_y_no_aprieta_ningun_boton_de_la_lista(self):
        # La trampa del botón por defecto (se vio en Ventas): que el Enter no apriete
        # además el +1 del primer renglón.
        pedidos_clientes_repo.anotar(self.lucia_id, "Pilas AAA")
        ventana = self._ventana()
        ventana.show()
        self.addCleanup(ventana.close)
        ventana.campo.setFocus()
        QTest.keyClicks(ventana.campo, "mantecol")
        QTest.keyClick(ventana.campo, Qt.Key_Return)
        self.assertEqual(sorted(self._renglones(ventana)), [("Mantecol", "1"), ("Pilas AAA", "1")])

    def test_guardar_vacio_lo_dice_en_rojo_sin_cartel_y_no_anota(self):
        ventana = self._ventana()
        ventana.campo.setText("   ")
        ventana._guardar()
        self.avisos.assert_not_called()
        self.assertIn("Escribí qué pidió el cliente", ventana.etiqueta_hecho.text())
        self.assertEqual(pedidos_clientes_repo.listar_pendientes(), [])

    def test_la_ultima_vez_dice_cuando_y_quien_anoto_la_ultima(self):
        pedidos_clientes_repo.anotar(self.lucia_id, "Mantecol")
        ventana = self._ventana(self.gaby_id)
        self._apretar_mas_uno(ventana, "Mantecol")
        ultima = pedidos_clientes_repo.listar_pendientes()[0]["ultima_vez"]
        self.assertEqual(ventana.tabla.item(0, COLUMNA_ULTIMA_VEZ).text(), f"{formato_fecha_hora(ultima)} · Gaby")

    def test_el_mas_uno_del_renglon_suma_un_cliente_y_reordena(self):
        pedidos_clientes_repo.anotar(self.lucia_id, "Mantecol")
        pedidos_clientes_repo.anotar(self.lucia_id, "Pilas AAA")
        ventana = self._ventana()
        self._apretar_mas_uno(ventana, "Pilas AAA")
        self._apretar_mas_uno(ventana, "Pilas AAA")
        # Con 3 clientes pasa arriba de todo, y el cursor vuelve al campo.
        self.assertEqual(self._renglones(ventana), [("Pilas AAA", "3"), ("Mantecol", "1")])

    def test_un_doble_clic_en_el_mas_uno_no_le_suma_al_que_quedo_debajo(self):
        # Alfajor (2) arriba; Bananita (1) y Chicle (1) abajo. El +1 de Chicle lo sube
        # al primer lugar: el segundo clic rápido, en el mismo lugar, caería en el +1
        # de otro producto.
        for texto, veces in (("Chicle", 1), ("Alfajor", 2), ("Bananita", 1)):
            for _ in range(veces):
                pedidos_clientes_repo.anotar(self.lucia_id, texto)
        ventana = self._ventana()
        fila = self._fila_de(ventana, "Chicle")
        self._apretar_mas_uno(ventana, "Chicle")
        ventana.tabla.cellWidget(fila, COLUMNA_MAS_UNO).boton.click()
        self.assertEqual(dict(self._renglones(ventana)), {"Alfajor": "2", "Chicle": "2", "Bananita": "1"})

    def test_los_parecidos_salen_al_escribir_y_tocarlos_suma(self):
        pedidos_clientes_repo.anotar(self.lucia_id, "Mantecol")
        pedidos_clientes_repo.anotar(self.lucia_id, "Coca-Cola")
        ventana = self._ventana()

        ventana.campo.setText("m")
        self.assertEqual(ventana._pastillas_parecidos, [])
        ventana.campo.setText("mante")
        viejas = list(ventana._pastillas_parecidos)
        self.assertEqual([p.text() for p in viejas], ["Mantecol (1)  +1"])
        self.assertFalse(ventana.titulo_parecidos.isHidden())

        viejas[0].click()
        self.assertEqual(dict(self._renglones(ventana))["Mantecol"], "2")
        self.assertEqual(ventana.campo.text(), "")
        # Las de antes se esconden ya (si no, quedaban dibujadas como un recuadro blanco).
        self.assertTrue(all(p.isHidden() for p in viejas))
        self.assertEqual(ventana._pastillas_parecidos, [])
        self.assertTrue(ventana.titulo_parecidos.isHidden())

    def test_un_ampersand_en_el_nombre_no_es_un_atajo(self):
        pedidos_clientes_repo.anotar(self.lucia_id, "M&M")
        ventana = self._ventana()
        ventana.campo.setText("m&m")
        pastilla = ventana._pastillas_parecidos[0]
        self.assertEqual(pastilla.text(), "M&&M (1)  +1")
        self.assertTrue(pastilla.shortcut().isEmpty())

    def test_cinco_parecidos_largos_no_ensanchan_la_ventana(self):
        for numero in range(5):
            pedidos_clientes_repo.anotar(self.lucia_id, f"Yerba {numero} " + "x" * (dominio.LARGO_MAXIMO_PEDIDO_CLIENTE - 8))
        ventana = self._ventana()
        antes = ventana.minimumSizeHint().width()
        ventana.campo.setText("yerba")
        self.assertEqual(len(ventana._pastillas_parecidos), 5)
        self.assertEqual(ventana.minimumSizeHint().width(), antes)
        # El nombre se corta con "…" y entero queda en el cartelito.
        for pastilla in ventana._pastillas_parecidos:
            self.assertIn("…", pastilla.text())
            self.assertEqual(len(pastilla.toolTip()), dominio.LARGO_MAXIMO_PEDIDO_CLIENTE)


class TestTrajimosDesdeLaPantalla(_ConLaVentana):
    def test_trajimos_pregunta_lo_saca_de_la_lista_y_aparece_en_el_historial(self):
        pedidos_clientes_repo.anotar(self.lucia_id, "Mantecol")
        pedidos_clientes_repo.anotar(self.gaby_id, "Mantecol")
        ventana = self._ventana()
        boton = ventana.tabla.cellWidget(0, COLUMNA_TRAJIMOS).boton
        self.assertEqual(boton.text(), TEXTO_TRAJIMOS)
        self.assertEqual(TEXTO_TRAJIMOS, "TRAJIMOS")
        boton.click()

        self.pregunta.assert_called_once()
        self.assertIn("Mantecol", self.pregunta.call_args.args[2])
        self.assertIn("2 clientes", self.pregunta.call_args.args[2])
        self.assertEqual(ventana.tabla.rowCount(), 0)
        self.assertEqual((ventana.indicador_productos.valor.text(), ventana.indicador_clientes.valor.text()),
                         ("0", "0"))

        historial = DialogoHistorialPedidos(ventana)
        self.addCleanup(historial.deleteLater)
        self.assertTrue(historial.se_puede_cerrar_sola())
        self.assertEqual(historial.tabla.rowCount(), 1)
        textos = [historial.tabla.item(0, columna).text() for columna in range(5)]
        self.assertEqual((textos[0], textos[1], textos[4]), ("Mantecol", "2", "Lucia"))
        self.assertTrue(textos[2] and textos[3])

    def test_si_dice_que_no_no_cambia_nada(self):
        pedidos_clientes_repo.anotar(self.lucia_id, "Mantecol")
        pedidos_clientes_repo.anotar(self.lucia_id, "Pilas AAA")
        self.pregunta.return_value = False
        ventana = self._ventana(self.admin_id)
        antes = pedidos_clientes_repo.listar_pendientes()

        ventana.tabla.cellWidget(0, COLUMNA_TRAJIMOS).boton.click()
        ventana.tabla.selectRow(0)
        ventana._borrar()
        ventana.tabla.selectRow(0)
        # Elige el primero de los otros (getItem recibe la lista como cuarto argumento).
        with mock.patch("ui.pedidos_clientes_window.QInputDialog.getItem",
                        side_effect=lambda *argumentos: (argumentos[3][0], True)):
            ventana._juntar()

        self.assertEqual(self.pregunta.call_count, 3)
        self.assertEqual([dict(p) for p in pedidos_clientes_repo.listar_pendientes()], [dict(p) for p in antes])


class TestCorreccionesDesdeLaPantalla(_ConLaVentana):
    def test_renombrar_juntar_y_borrar_los_ven_todos_pero_son_del_admin(self):
        # Hasta el 2026-11-04 a la empleada ni le aparecían; ahora las ve igual y le
        # dicen "Acceso Restringido" (pedido del dueño).
        def restringidas(usuario_id):
            botones = self._ventana(usuario_id).findChildren(QPushButton)
            self.assertTrue(LOS_DEL_ADMIN <= {boton.text() for boton in botones})
            return {boton.text() for boton in botones if boton.property("restringido")}

        self.assertEqual(restringidas(self.lucia_id), LOS_DEL_ADMIN)
        self.assertEqual(restringidas(self.admin_id), set())

    def test_sin_elegir_un_renglon_avisa(self):
        pedidos_clientes_repo.anotar(self.lucia_id, "Mantecol")
        pedidos_clientes_repo.anotar(self.lucia_id, "Pilas AAA")
        ventana = self._ventana(self.admin_id)
        ventana._borrar()
        # Después de un +1 y TRAJIMOS queda un renglón "actual" que no se ve marcado:
        # tampoco cuenta como elegido.
        self._apretar_mas_uno(ventana, "Pilas AAA")
        ventana.tabla.cellWidget(self._fila_de(ventana, "Pilas AAA"), COLUMNA_TRAJIMOS).boton.click()
        ventana._borrar()
        self.assertEqual(self.avisos.call_count, 2)
        self.assertEqual([p["producto"] for p in pedidos_clientes_repo.listar_pendientes()], ["Mantecol"])

    def test_renombrar_juntar_y_borrar(self):
        pedidos_clientes_repo.anotar(self.lucia_id, "mantecool")
        pedidos_clientes_repo.anotar(self.lucia_id, "Mantecol grande")
        pedidos_clientes_repo.anotar(self.lucia_id, "Mantecol grande")
        pedidos_clientes_repo.anotar(self.lucia_id, "asdf")
        ventana = self._ventana(self.admin_id)

        ventana.tabla.selectRow(self._fila_de(ventana, "Mantecool"))
        with mock.patch("ui.pedidos_clientes_window.QInputDialog.getText", return_value=("Mantecol", True)):
            ventana._renombrar()
        self.assertIn(("Mantecol", "1"), self._renglones(ventana))

        ventana.tabla.selectRow(self._fila_de(ventana, "Mantecol"))
        with mock.patch("ui.pedidos_clientes_window.QInputDialog.getItem",
                        return_value=("Mantecol grande (2 clientes)", True)):
            ventana._juntar()
        self.assertIn(("Mantecol grande", "3"), self._renglones(ventana))
        self.assertNotIn("Mantecol", dict(self._renglones(ventana)))

        ventana.tabla.selectRow(self._fila_de(ventana, "Asdf"))
        ventana._borrar()
        self.assertEqual(self._renglones(ventana), [("Mantecol grande", "3")])


if __name__ == "__main__":
    unittest.main()
