"""
lista_compras_window.py
=========================
LISTA DE COMPRAS (pedido del dueño, 2026-10-31): los artículos que tienen
dominio.STOCK_PARA_LISTA_DE_COMPRAS unidades o menos (4), de la A a la Z, para
saber qué hay que comprar. Los que están en 0 o en negativo salen en rojo.

Se abre desde la barra de la ventana principal, con el botón que va antes de
Operador, y la puede abrir cualquiera. Solo muestra: el stock se corrige en
Artículos. La hoja impresa trae además una columna "Comprar" vacía, para anotar
a mano cuánto pedir de cada uno.

Con la maqueta B que eligió el dueño el 2026-10-30 (ui/piezas_ventana.py): la
cabecera oscura con cuántos son y cuántos ya no tienen, los filtros por rubro, la
grilla en su panel y la ayuda abajo. Usa solo funciones del repo que ya usa
Artículos, así también se abre desde otra PC.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QTableWidgetItem, QVBoxLayout

import dominio
from repositories import articulos_repo
from ui import imprimir
from ui.dibujos_tabla import DelegadoEtiqueta
from ui.piezas_ventana import (
    agregar_indicador, cabecera_oscura, fila_de_filtros, panel_de_tabla, pie_de_ventana, poner_indicador, tecla,
)
from ui.utils import crear_tabla, sin_boton_por_defecto

TITULO = "Lista de Compras"
COLUMNAS = ["Artículo", "Marca", "Rubro", "Stock"]
COLUMNA_RUBRO = 2
COLUMNA_STOCK = 3
# La hoja impresa suma "Comprar": una raya en cada renglón para escribir encima.
COLUMNAS_IMPRESAS = COLUMNAS + ["Comprar"]
_PARA_ANOTAR = "_" * 12


def _subtitulo(cantidad: int) -> str:
    if cantidad == 0:
        return f"No hay ningún artículo con {dominio.STOCK_PARA_LISTA_DE_COMPRAS} unidades o menos."
    articulos = "1 artículo" if cantidad == 1 else f"{cantidad} artículos"
    return f"{articulos} con {dominio.STOCK_PARA_LISTA_DE_COMPRAS} unidades o menos, de la A a la Z."


class VentanaListaDeCompras(QDialog):
    """Lo que hay que comprar, lista para imprimir."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._articulos = dominio.articulos_para_comprar(articulos_repo.listar_articulos())
        self._rubro_elegido = None
        self.setWindowTitle(TITULO)
        self.resize(980, 720)
        self._armar_interfaz()
        self._cargar_grilla()

    def _armar_interfaz(self):
        cabecera = cabecera_oscura("📝", TITULO, _subtitulo(len(self._articulos)))
        self.etiqueta = cabecera.detalle
        sin_stock = sum(1 for articulo in self._articulos if articulo["stock"] <= 0)
        poner_indicador(agregar_indicador(cabecera, "Artículos"), str(len(self._articulos)))
        poner_indicador(agregar_indicador(cabecera, "Sin stock"), str(sin_stock), alerta=sin_stock > 0)

        self.boton_imprimir = tecla("🖨  IMPRIMIR", self._imprimir, "teclaAzul")
        self.boton_imprimir.setToolTip("Abre la vista previa para imprimir la lista (o guardarla en PDF).")
        self.boton_imprimir.setEnabled(bool(self._articulos))
        barra_botones = QHBoxLayout()
        barra_botones.setSpacing(8)
        barra_botones.addWidget(self.boton_imprimir)
        barra_botones.addStretch()
        barra_botones.addWidget(tecla("CERRAR", self.close))

        # Las pastillas, solo con los rubros que tienen algo para comprar.
        rubros = sorted({articulo["rubro"] for articulo in self._articulos if articulo["rubro"]},
                        key=dominio.sin_acentos)
        self.filtros = fila_de_filtros(rubros, self._elegir_rubro)

        self.tabla = crear_tabla(COLUMNAS, estirar=0, por_filas=True)
        # Cada rubro con el mismo color que en Artículos: el orden es el de listar_rubros.
        etiqueta_rubro = DelegadoEtiqueta(self.tabla)
        etiqueta_rubro.colores_en_orden([rubro["nombre"] for rubro in articulos_repo.listar_rubros()])
        self.tabla.setItemDelegateForColumn(COLUMNA_RUBRO, etiqueta_rubro)
        self.tabla.setColumnWidth(1, 170)
        self.tabla.setColumnWidth(COLUMNA_RUBRO, 170)
        self.tabla.setColumnWidth(COLUMNA_STOCK, 110)
        self.tabla.horizontalHeaderItem(COLUMNA_STOCK).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(cabecera)
        layout.addLayout(barra_botones)
        layout.addWidget(self.filtros)
        layout.addWidget(panel_de_tabla(self.tabla), 1)
        layout.addWidget(pie_de_ventana(
            f"Salen los artículos con {dominio.STOCK_PARA_LISTA_DE_COMPRAS} unidades o menos; en rojo, los que ya no tienen  ·  "
            "La hoja impresa trae la columna \"Comprar\" para anotar a mano"))
        self.setLayout(layout)
        sin_boton_por_defecto(self)

    def _a_la_vista(self):
        """Los artículos del rubro elegido (o todos)."""
        if self._rubro_elegido is None:
            return self._articulos
        return [articulo for articulo in self._articulos if articulo["rubro"] == self._rubro_elegido]

    def _elegir_rubro(self, rubro):
        self._rubro_elegido = rubro
        self._cargar_grilla()

    def _cargar_grilla(self):
        articulos = self._a_la_vista()
        self.tabla.setRowCount(len(articulos))
        for fila, articulo in enumerate(articulos):
            self.tabla.setItem(fila, 0, QTableWidgetItem(articulo["descripcion"]))
            self.tabla.setItem(fila, 1, QTableWidgetItem(articulo["marca"] or ""))
            self.tabla.setItem(fila, COLUMNA_RUBRO, QTableWidgetItem(articulo["rubro"] or ""))
            stock = QTableWidgetItem(str(articulo["stock"]))
            stock.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if articulo["stock"] <= 0:
                stock.setForeground(Qt.red)
            self.tabla.setItem(fila, COLUMNA_STOCK, stock)

    def html_para_imprimir(self, impreso=None) -> str:
        """La hoja impresa: lo que se está viendo (si hay un rubro elegido, solo ese)."""
        articulos = self._a_la_vista()
        titulo = TITULO if self._rubro_elegido is None else f"{TITULO} — {self._rubro_elegido}"
        filas = [
            ((articulo["descripcion"], articulo["marca"] or "", articulo["rubro"] or "", articulo["stock"], _PARA_ANOTAR),
             False)
            for articulo in articulos
        ]
        return imprimir.html_del_listado(
            titulo, _subtitulo(len(articulos)), COLUMNAS_IMPRESAS, filas,
            a_la_derecha=(COLUMNA_STOCK,), impreso=impreso,
        )

    def _imprimir(self):
        imprimir.vista_previa(self, self.html_para_imprimir(), TITULO)
