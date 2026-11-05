"""
impresiones_window.py
=======================
El botón IMPRE/FOTOC de la barra de arriba y del inicio (pedido del dueño,
2026-10-19, como "Impresiones": cobrar impresiones sin entrar a Vender ni buscar
el artículo; el 2026-11-04 se sumaron las fotocopias, que tienen otro precio).

Es la maqueta A que eligió el dueño ese día: dos renglones, "Impresiones [ ]" y
"Fotocopias [ ]", cada uno con su precio y su subtotal, y el TOTAL abajo. Enter
pasa de Impresiones a Fotocopias y otro Enter abre la ventana de cobro de
siempre (ui.dialogo_pago); la que no se usa queda en 0.

Es una venta de kiosko común de los dos artículos (ver
repositories/impresiones_repo.py): la pantalla solo junta las cantidades y
muestra la cuenta.
"""

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QDialog, QFrame, QGridLayout, QLabel, QSpinBox, QVBoxLayout

import dominio
from repositories import impresiones_repo, ventas_repo
from ui.dialogo_pago import DialogoPago
from ui.piezas_ventana import cabecera_oscura, panel_blanco
from ui.utils import (
    encadenar_enter, fila_guardar_cancelar, formato_pesos, manejar_errores, mostrar_info,
    sin_boton_por_defecto,
)

# código -> (dibujito, nombre del renglón, singular y plural para el aviso de cobrado)
_RENGLONES = {
    dominio.CODIGO_ARTICULO_IMPRESIONES: ("🖨️", "Impresiones", "impresión", "impresiones"),
    dominio.CODIGO_ARTICULO_FOTOCOPIAS: ("📄", "Fotocopias", "fotocopia", "fotocopias"),
}
_COLOR_GRIS = "#6B7484"


def _cuantas(cantidad: int, singular: str, plural: str) -> str:
    return f"{cantidad} {singular if cantidad == 1 else plural}"


class DialogoImpresiones(QDialog):
    """Las cantidades de impresiones y de fotocopias, sus precios y el total;
    Cobrar abre la ventana de cobro. `articulos` es el de
    impresiones_repo.articulos_del_boton() ({código: artículo o None}); quien abre
    la ventana ya comprobó que hay al menos uno. El que falta queda apagado, con el
    aviso de qué código hay que cargar.

    Con la cabecera oscura y los renglones en un panel blanco (maqueta B de las
    ventanas, 2026-10-30)."""

    def __init__(self, usuario, articulos, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.articulos = {codigo: articulos.get(codigo) for codigo in _RENGLONES}
        self.cantidades = {}   # código -> su recuadro
        self.subtotales = {}   # código -> la etiqueta de su subtotal
        self.setWindowTitle("Impre/Fotoc")
        self.resize(480, 400)
        self._armar_interfaz()
        self._actualizar_total()

    def se_puede_cerrar_sola(self) -> bool:
        """Mientras solo se están eligiendo las cantidades no se pierde nada: el
        cierre forzoso de la caja la puede cerrar (ver
        MainWindow._hay_un_cobro_a_medias). Con la ventana de cobro abierta
        encima, la que se consulta es esa, y esa espera."""
        return True

    def _armar_interfaz(self):
        precios = [f"{_RENGLONES[codigo][2].capitalize()} {formato_pesos(articulo['precio_venta'])} c/u"
                   for codigo, articulo in self.articulos.items() if articulo is not None]
        cabecera = cabecera_oscura("🖨️", "Impre/Fotoc", "  ·  ".join(precios))

        grilla = QGridLayout()
        grilla.setHorizontalSpacing(12)
        grilla.setVerticalSpacing(10)
        for fila, (codigo, articulo) in enumerate(self.articulos.items()):
            self._armar_renglon(grilla, fila, codigo, articulo)
        grilla.setColumnStretch(3, 1)

        raya = QFrame()
        raya.setFixedHeight(1)
        raya.setStyleSheet("background: #DDE2EA;")

        self.etiqueta_total = QLabel()
        self.etiqueta_total.setAlignment(Qt.AlignCenter)
        self.etiqueta_total.setStyleSheet("font-size: 22px; font-weight: bold; color: #2F6FED;")
        ayuda = QLabel("Enter pasa de Impresiones a Fotocopias y después cobra. La que no se usa queda en 0.")
        ayuda.setWordWrap(True)
        ayuda.setStyleSheet(f"color: {_COLOR_GRIS}; font-size: 11px;")

        panel, capa = panel_blanco()
        capa.addLayout(grilla)
        capa.addWidget(raya)
        capa.addWidget(self.etiqueta_total)
        capa.addWidget(ayuda)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(cabecera)
        layout.addWidget(panel)
        layout.addStretch()
        layout.addLayout(fila_guardar_cancelar(self, self._cobrar, texto_guardar="Cobrar"))
        self.setLayout(layout)

        activos = [self.cantidades[codigo] for codigo, articulo in self.articulos.items() if articulo is not None]
        encadenar_enter(*activos, accion_final=self._cobrar)
        sin_boton_por_defecto(self)
        self._primero = activos[0]
        self._primero.setFocus()

    def _armar_renglon(self, grilla, fila, codigo, articulo):
        dibujito, nombre, _singular, _plural = _RENGLONES[codigo]
        titulo = QLabel(f"{dibujito}  {nombre}")
        titulo.setStyleSheet("font-size: 16px; font-weight: 700;")

        cantidad = QSpinBox()
        cantidad.setRange(0, impresiones_repo.CANTIDAD_MAXIMA)
        cantidad.setValue(0)
        # Sin flechitas, como los importes de la ventana de cobro: se escribe el
        # número (las flechas del teclado igual suben y bajan).
        cantidad.setButtonSymbols(QSpinBox.NoButtons)
        cantidad.setAlignment(Qt.AlignCenter)
        cantidad.setMinimumHeight(40)
        cantidad.setFixedWidth(90)
        cantidad.setStyleSheet("font-size: 18px; font-weight: bold;")
        cantidad.valueChanged.connect(self._actualizar_total)
        # Al llegar al recuadro (Enter, Tab o un clic) queda el número elegido: lo
        # que se escribe lo reemplaza, sin tener que borrar el 0.
        cantidad.installEventFilter(self)
        self.cantidades[codigo] = cantidad

        if articulo is None:
            cantidad.setEnabled(False)
            precio = QLabel(f"Falta el artículo código {codigo}")
        else:
            precio = QLabel(f"× {formato_pesos(articulo['precio_venta'])}")
        precio.setStyleSheet(f"color: {_COLOR_GRIS}; font-size: 13px;")

        subtotal = QLabel()
        subtotal.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        subtotal.setStyleSheet("font-size: 15px; font-weight: 700;")
        self.subtotales[codigo] = subtotal

        grilla.addWidget(titulo, fila, 0)
        grilla.addWidget(cantidad, fila, 1)
        grilla.addWidget(precio, fila, 2)
        grilla.addWidget(subtotal, fila, 3)

    def eventFilter(self, objeto, evento):
        if evento.type() == QEvent.FocusIn and isinstance(objeto, QSpinBox):
            QTimer.singleShot(0, objeto.selectAll)
        return False

    def showEvent(self, evento):
        super().showEvent(evento)
        # Recién después de mostrarse se puede seleccionar (mismo truco que la
        # ventana de cobro).
        QTimer.singleShot(0, self._primero.selectAll)

    def _lineas(self):
        """{código: (cantidad, precio por unidad)} de los artículos que están cargados."""
        return {codigo: (self.cantidades[codigo].value(), articulo["precio_venta"])
                for codigo, articulo in self.articulos.items() if articulo is not None}

    def _total(self):
        return sum(ventas_repo.subtotal_linea({"cantidad": cantidad, "precio_unitario": precio})
                   for cantidad, precio in self._lineas().values())

    def _actualizar_total(self):
        for codigo, (cantidad, precio) in self._lineas().items():
            self.subtotales[codigo].setText(
                formato_pesos(ventas_repo.subtotal_linea({"cantidad": cantidad, "precio_unitario": precio})))
        self.etiqueta_total.setText(f"TOTAL: {formato_pesos(self._total())}")

    @manejar_errores
    def _cobrar(self):
        lineas = self._lineas()
        if not any(cantidad for cantidad, _precio in lineas.values()):
            raise ValueError("Escribí cuántas impresiones o fotocopias son.")
        total = self._total()
        dialogo = DialogoPago(self, total)
        if not dialogo.exec():
            return
        numero = impresiones_repo.cobrar_impre_fotoc(self.usuario["id"], lineas, dialogo.pagos)
        cobrado = " + ".join(_cuantas(cantidad, *_RENGLONES[codigo][2:])
                             for codigo, (cantidad, _precio) in lineas.items() if cantidad)
        mensaje = f"{cobrado}: {formato_pesos(total)}\nVenta Nº {numero}"
        if dialogo.vuelto > 0:
            mensaje += f"\nVuelto a entregar: {formato_pesos(dialogo.vuelto)}"
        mostrar_info(self, "Cobrado", mensaje)
        self.accept()
