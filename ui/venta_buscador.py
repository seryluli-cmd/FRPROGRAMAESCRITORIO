"""
venta_buscador.py
===================
El campo de arriba de Venta de Mercadería busca por código de barras, por
descripción o por marca SIN abrir otra ventana (pedido del dueño, 2026-11-02: el
cuadro chico aparte de F6 "no es estético, ni lógico, ni práctico"). F5, F6 y F7
cambian solo el criterio de ese mismo campo: el dibujo de la izquierda (el código
de barras, "ABC" o la etiqueta de la marca), el texto de ayuda y la tecla marcada.

Por descripción o por marca, lo que se escribe abre una lista debajo del campo,
encima del carrito: las flechas eligen (arranca marcado el primero), Enter o un
clic lo agregan y la lista se cierra. El criterio queda hasta que se aprieta otra
tecla (F5 vuelve al código de barras), y la pistola anda igual en los tres: si no
hay nada en la lista, Enter busca el código exacto. Esc borra lo escrito y, con el
campo vacío, vuelve al código de barras (en vez de cerrar la venta).

Por código de barras no hay lista: lo que se escanea entra con Enter como siempre,
y un código que no existe se avisa con cuántos dígitos llegaron (ver
ui/buscar_articulo.avisar_codigo_no_encontrado). Compras sigue con el cuadro
aparte de ui/buscar_articulo.py.
"""

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect, QHeaderView, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
)

from repositories import articulos_repo
from ui.utils import formato_pesos, manejar_errores
from ui.ventas_dibujos import (
    ALTO_DIBUJO_CAMPO, ANCHO_DIBUJO_CAMPO, ROL_DETALLE, DelegadoProducto, boton_con_tecla, dibujo_abc,
    dibujo_codigo_de_barras, dibujo_de_marca,
)

CODIGO, DESCRIPCION, MARCA = "codigo", "descripcion", "marca"

# criterio -> (tecla, botón, ayuda del botón, ayuda de adentro del campo, dibujo de adentro del campo)
_CRITERIOS = {
    CODIGO: ("F5", "Código", "Escanear con la pistola o tipear el código de barras",
             "Escaneá el código de barras y apretá Enter...", dibujo_codigo_de_barras),
    DESCRIPCION: ("F6", "Descripción", "Buscar escribiendo el nombre del producto",
                  "Escribí el nombre del producto, elegilo con las flechas y apretá Enter...", dibujo_abc),
    MARCA: ("F7", "Marca", "Buscar escribiendo la marca del producto",
            "Escribí la marca, elegí el producto con las flechas y apretá Enter...", dibujo_de_marca),
}

_TOPE_DE_RESULTADOS = 100   # se recorre con las flechas o la rueda: más no ayuda a elegir
_RENGLONES_A_LA_VISTA = 6
_ALTO_RENGLON = 46          # el mismo renglón de dos pisos del carrito
_ANCHO_PRECIO = 120
_X_DIBUJO = 10              # el borde (2 px) y el relleno (8 px) del campo en la hoja de estilos


class BuscadorDeLaVenta(QTableWidget):
    """La lista que se abre debajo del campo con lo encontrado, y la que decide qué
    busca ese campo (`criterio`). Es hija de la ventana y flota encima del carrito: no
    ocupa lugar mientras está cerrada. `al_elegir(codigo)` agrega al carrito, lo mismo
    que la pistola. Los botones F5/F6/F7 que la manejan quedan en `botones`."""

    def __init__(self, ventana, campo: QLineEdit, al_elegir):
        super().__init__(0, 2, ventana)
        self.campo = campo
        self.al_elegir = al_elegir
        self.criterio = CODIGO
        self._resultados = []
        self._armar_lista()
        # El dibujo va en una etiqueta encima del campo, con lugar reservado a la
        # izquierda del texto: como ícono del campo (addAction) Qt lo achica a 16 px.
        self.dibujo_del_campo = QLabel(campo)
        self.dibujo_del_campo.setFixedSize(ANCHO_DIBUJO_CAMPO, ALTO_DIBUJO_CAMPO)
        self.dibujo_del_campo.setAttribute(Qt.WA_TransparentForMouseEvents)   # un clic ahí es en el campo
        campo.setTextMargins(ANCHO_DIBUJO_CAMPO + 8, 0, 0, 0)
        self.botones = [self._armar_boton(ventana, criterio) for criterio in _CRITERIOS]
        campo.textChanged.connect(self._buscar)
        campo.installEventFilter(self)
        self.poner_criterio(CODIGO)

    def _armar_lista(self):
        self.setObjectName("resultadosVenta")
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.horizontalHeader().setVisible(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(_ALTO_RENGLON)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.setColumnWidth(1, _ANCHO_PRECIO)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # La letra sigue en el campo mientras se elige: las flechas y Enter van ahí.
        self.setFocusPolicy(Qt.NoFocus)
        # Como el carrito: la descripción grande y, chiquito debajo, el código y la marca.
        self.setItemDelegateForColumn(0, DelegadoProducto(self))
        sombra = QGraphicsDropShadowEffect(self)
        sombra.setBlurRadius(18)
        sombra.setOffset(0, 4)
        sombra.setColor(QColor(20, 30, 50, 70))
        self.setGraphicsEffect(sombra)
        self.cellClicked.connect(self._al_hacer_clic)
        self.hide()

    def _armar_boton(self, ventana, criterio):
        tecla, nombre, ayuda, _ayuda_del_campo, _dibujo = _CRITERIOS[criterio]
        boton = boton_con_tecla(tecla, nombre)
        boton.setToolTip(ayuda)
        boton.clicked.connect(lambda _apretado=False: self.poner_criterio(criterio))
        QShortcut(QKeySequence(tecla), ventana, activated=lambda: self.poner_criterio(criterio))
        return boton

    def poner_criterio(self, criterio):
        """Cambia qué busca el campo. Lo que ya estaba escrito queda y se busca con el
        criterio nuevo."""
        self.criterio = criterio
        _tecla, _nombre, _ayuda, ayuda_del_campo, dibujo = _CRITERIOS[criterio]
        self.dibujo_del_campo.setPixmap(dibujo())
        self.dibujo_del_campo.setAccessibleName(dibujo.__name__)   # por ahí lo reconocen las pruebas
        self.campo.setPlaceholderText(ayuda_del_campo)
        for boton, suyo in zip(self.botones, _CRITERIOS):
            boton.setProperty("elegida", suyo == criterio)
            boton.style().unpolish(boton)
            boton.style().polish(boton)
        self.campo.setFocus()
        self._buscar(self.campo.text())

    def codigo_elegido(self, texto):
        """El código que agrega un Enter con `texto` escrito en el campo. Por código de
        barras, el texto tal cual (si no es ningún artículo, Ventas avisa como siempre).
        Por descripción o marca, el renglón marcado de la lista; si no hay ninguno, el
        código exacto (así la pistola anda en los tres criterios). None: no hay nada que
        agregar, y la lista ya dice por qué."""
        if self.criterio == CODIGO:
            return texto
        fila = self.currentRow()
        if 0 <= fila < len(self._resultados):
            return self._resultados[fila]["codigo"]
        if articulos_repo.buscar_por_codigo(texto) is not None:
            return texto
        return None

    @manejar_errores
    def _buscar(self, texto):
        texto = texto.strip()
        if self.criterio == CODIGO or not texto:
            self._resultados = []
            self.hide()
            return
        if self.criterio == DESCRIPCION:
            encontrados = articulos_repo.buscar_por_descripcion(texto)
        else:
            encontrados = articulos_repo.buscar_por_marca(texto)
        self._resultados = list(encontrados[:_TOPE_DE_RESULTADOS])
        self._llenar(texto)
        self._mostrar()

    def _llenar(self, texto):
        self.clearSpans()
        self.setRowCount(0)
        for articulo in self._resultados:
            fila = self.rowCount()
            self.insertRow(fila)
            producto = QTableWidgetItem(articulo["descripcion"])
            producto.setData(ROL_DETALLE, "  ·  ".join(filter(None, (articulo["codigo"], articulo["marca"]))))
            precio = QTableWidgetItem(formato_pesos(articulo["precio_venta"]))
            precio.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.setItem(fila, 0, producto)
            self.setItem(fila, 1, precio)
        if self._resultados:
            self.setCurrentCell(0, 0)   # Enter agrega el primero sin tocar las flechas
            return
        que = "ningún producto que diga" if self.criterio == DESCRIPCION else "ninguna marca que diga"
        aviso = QTableWidgetItem(f"No hay {que} “{texto}”")
        aviso.setData(ROL_DETALLE, "Probá con otra palabra, o apretá F5 para volver al código de barras")
        aviso.setFlags(Qt.ItemIsEnabled)
        self.insertRow(0)
        self.setItem(0, 0, aviso)
        self.setSpan(0, 0, 1, 2)

    def _mostrar(self):
        """Abre la lista justo debajo del campo, de su mismo ancho y con hasta
        `_RENGLONES_A_LA_VISTA` renglones (los demás, con la rueda)."""
        abajo_del_campo = self.campo.mapTo(self.parentWidget(), QPoint(0, self.campo.height() + 4))
        renglones = min(max(self.rowCount(), 1), _RENGLONES_A_LA_VISTA)
        self.setGeometry(abajo_del_campo.x(), abajo_del_campo.y(), self.campo.width(),
                         renglones * _ALTO_RENGLON + 2 * self.frameWidth() + 2)
        self.show()
        self.raise_()

    def _al_hacer_clic(self, fila, _columna):
        if 0 <= fila < len(self._resultados):
            codigo = self._resultados[fila]["codigo"]
            self.campo.clear()
            self.al_elegir(codigo)

    def eventFilter(self, objeto, evento):
        if objeto is self.campo:
            tipo = evento.type()
            if tipo == QEvent.KeyPress:
                return self._tecla_en_el_campo(evento.key())
            if tipo == QEvent.Resize:
                self.dibujo_del_campo.move(_X_DIBUJO, (self.campo.height() - ALTO_DIBUJO_CAMPO) // 2)
            if tipo in (QEvent.Resize, QEvent.Move) and self.isVisible():
                self._mostrar()
            elif tipo == QEvent.FocusOut:
                # Un clic en el carrito o en otra ventana la cierra: si no, taparía los
                # renglones. Al volver al campo se abre de nuevo con lo que esté escrito.
                self.hide()
            elif tipo == QEvent.FocusIn and self.criterio != CODIGO and self.campo.text().strip():
                self._mostrar()
        return False

    def _tecla_en_el_campo(self, tecla):
        """True si la tecla la usó la lista (y el campo no la recibe)."""
        pasos = {Qt.Key_Down: 1, Qt.Key_Up: -1,
                 Qt.Key_PageDown: _RENGLONES_A_LA_VISTA, Qt.Key_PageUp: -_RENGLONES_A_LA_VISTA}
        if tecla in pasos and self.isVisible() and self._resultados:
            fila = min(max(self.currentRow() + pasos[tecla], 0), len(self._resultados) - 1)
            self.setCurrentCell(fila, 0)
            self.scrollToItem(self.item(fila, 0))
            return True
        if tecla == Qt.Key_Escape and self.criterio != CODIGO:
            if self.campo.text():
                self.campo.clear()
            else:
                self.poner_criterio(CODIGO)
            return True
        return False
