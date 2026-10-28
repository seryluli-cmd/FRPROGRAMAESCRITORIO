"""
tests/test_rubros.py
====================
Los rubros de los artículos (Artículos > Gestionar Rubros): se borra uno que
ningún artículo tiene; uno que todavía tiene artículos se rechaza con un mensaje
claro y queda como estaba, para no dejar artículos sin rubro sin darse cuenta.
Y un rubro de fábrica que se borra no vuelve solo al abrir el programa de nuevo.

Se ejecutan con:

    python -m unittest discover tests
"""

import unittest

import database
from repositories import articulos_repo
from base import BaseConBaseTemporal


def _nombres_de_rubros():
    return [rubro["nombre"] for rubro in articulos_repo.listar_rubros()]


class TestBorrarRubro(BaseConBaseTemporal):
    def test_se_borra_un_rubro_sin_articulos(self):
        rubro_id = articulos_repo.crear_rubro("GOLOSINAS")
        self.assertIn("GOLOSINAS", _nombres_de_rubros())

        articulos_repo.borrar_rubro(rubro_id)

        self.assertNotIn("GOLOSINAS", _nombres_de_rubros())

    def test_no_se_borra_un_rubro_que_tiene_articulos(self):
        rubro_id = articulos_repo.crear_rubro("GOLOSINAS")
        articulos_repo.crear_articulo("111", "Chicle", None, rubro_id, 100.0, 50.0, 0)

        with self.assertRaisesRegex(ValueError, "No se puede borrar este rubro"):
            articulos_repo.borrar_rubro(rubro_id)

        self.assertIn("GOLOSINAS", _nombres_de_rubros())
        self.assertEqual(articulos_repo.buscar_por_codigo("111")["rubro"], "GOLOSINAS")

    def test_con_el_articulo_en_otro_rubro_ya_se_puede_borrar(self):
        # Lo que dice el aviso: cambiarle el rubro desde "Modificar" y volver a borrar.
        golosinas = articulos_repo.crear_rubro("GOLOSINAS")
        bebidas = articulos_repo.crear_rubro("BEBIDAS")
        articulos_repo.crear_articulo("111", "Chicle", None, golosinas, 100.0, 50.0, 0)
        articulos_repo.modificar_articulo("111", "Chicle", None, bebidas, 100.0, 50.0, 0)

        articulos_repo.borrar_rubro(golosinas)

        self.assertNotIn("GOLOSINAS", _nombres_de_rubros())
        self.assertEqual(articulos_repo.buscar_por_codigo("111")["rubro"], "BEBIDAS")

    def test_un_rubro_de_fabrica_borrado_no_vuelve_al_abrir_de_nuevo(self):
        kiosko = next(r for r in articulos_repo.listar_rubros() if r["nombre"] == "KIOSKO")

        articulos_repo.borrar_rubro(kiosko["id"])
        database.inicializar_base_de_datos()  # lo que hace cada arranque del programa

        self.assertNotIn("KIOSKO", _nombres_de_rubros())
        self.assertIn("BEBIDAS", _nombres_de_rubros())


if __name__ == "__main__":
    unittest.main()
