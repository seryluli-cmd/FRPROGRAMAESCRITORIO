"""
ventas_dibujos.py
===================
Los dibujos del diseño de Venta de Mercadería que eligió el dueño (2026-10-26,
la maqueta "B": el total y COBRAR siempre grandes a la derecha): las teclas con
la tecla marcada aparte ("F5" en un recuadro azul y "Código" al lado), el dibujo
de adentro del campo de escaneo (el código de barras, o "ABC" y la etiqueta cuando
busca por descripción o por marca) y el renglón del carrito con el código y el
precio por unidad chiquitos debajo del producto.

Se dibujan con QPainter: un emoji puede salir como un rectángulo en el Windows
del mostrador (pasó en CYBERCONTROL con el cubito de hielo 🧊 del botón
DESCONGELAR, que por eso pasó a ser un copo de nieve dibujado).
"""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPixmap, QPolygonF
from PySide6.QtWidgets import QPushButton, QStyle, QStyledItemDelegate, QStyleOptionViewItem

# Se dibujan al doble y Qt los muestra a su tamaño: así salen prolijos también con la
# escala de Windows al 125 % o al 150 %.
_ESCALA = 2
ALTO_TECLA = 20
COLOR_TECLA_FONDO = "#E6EEFE"
COLOR_TECLA_LETRA = "#1D48A0"
COLOR_BARRAS = "#2F6FED"
COLOR_PRODUCTO = "#1B2233"
COLOR_DETALLE = "#8A93A3"

# Lo que va en el renglón chiquito de debajo del producto (código · precio c/u).
ROL_DETALLE = Qt.UserRole + 1


def _fuente_de_tecla() -> QFont:
    fuente = QFont()
    fuente.setPixelSize(11 * _ESCALA)
    fuente.setBold(True)
    return fuente


def icono_de_tecla(tecla: str):
    """La tecla en un recuadro azul clarito ("F5", "*", "Supr"), para ponerla
    adelante del nombre del botón. Devuelve el ícono y su tamaño: el recuadro es
    más ancho cuanto más largo es el texto, y Qt achicaría un ícono que no entra
    en el tamaño de siempre."""
    fuente = _fuente_de_tecla()
    ancho = QFontMetrics(fuente).horizontalAdvance(tecla) // _ESCALA + 10
    dibujo = QPixmap(ancho * _ESCALA, ALTO_TECLA * _ESCALA)
    dibujo.fill(Qt.transparent)
    pincel = QPainter(dibujo)
    pincel.setRenderHint(QPainter.Antialiasing)
    pincel.setPen(Qt.NoPen)
    pincel.setBrush(QColor(COLOR_TECLA_FONDO))
    pincel.drawRoundedRect(QRectF(0, 0, dibujo.width(), dibujo.height()), 4 * _ESCALA, 4 * _ESCALA)
    pincel.setPen(QColor(COLOR_TECLA_LETRA))
    pincel.setFont(fuente)
    pincel.drawText(QRectF(0, 0, dibujo.width(), dibujo.height()), Qt.AlignCenter, tecla)
    pincel.end()
    dibujo.setDevicePixelRatio(_ESCALA)
    return QIcon(dibujo), QSize(ancho, ALTO_TECLA)


def boton_con_tecla(tecla: str, nombre: str) -> QPushButton:
    """Un botón con su tecla dibujada adelante, como F5/F6/F7."""
    boton = QPushButton(nombre)
    icono, tamano = icono_de_tecla(tecla)
    boton.setIcon(icono)
    boton.setIconSize(tamano)
    return boton


# Los dibujos de adentro del campo de escaneo. Van en una etiqueta propia y no como
# ícono del campo (QLineEdit.addAction): ahí Qt los achica a 16 px y "ABC" no se leía.
ANCHO_DIBUJO_CAMPO = 30
ALTO_DIBUJO_CAMPO = 22


def _lienzo():
    dibujo = QPixmap(ANCHO_DIBUJO_CAMPO * _ESCALA, ALTO_DIBUJO_CAMPO * _ESCALA)
    dibujo.fill(Qt.transparent)
    return dibujo


def _terminado(pincel, dibujo) -> QPixmap:
    pincel.end()
    dibujo.setDevicePixelRatio(_ESCALA)
    return dibujo


def dibujo_codigo_de_barras() -> QPixmap:
    """Un código de barras azul (rayas de distinto grueso): el campo espera la pistola."""
    dibujo = _lienzo()
    pincel = QPainter(dibujo)
    pincel.setPen(Qt.NoPen)
    pincel.setBrush(QColor(COLOR_BARRAS))
    x = 3 * _ESCALA
    for grueso, espacio in ((2, 1), (1, 1), (2, 1), (1, 2), (3, 1), (1, 1), (2, 1), (1, 1), (2, 0)):
        pincel.drawRect(QRectF(x, 2 * _ESCALA, grueso * _ESCALA, 18 * _ESCALA))
        x += (grueso + espacio) * _ESCALA
    return _terminado(pincel, dibujo)


def dibujo_abc() -> QPixmap:
    """"ABC" en azul: el campo busca por descripción, se escribe el nombre del producto
    (pedido del dueño, 2026-11-02)."""
    dibujo = _lienzo()
    fuente = QFont()
    fuente.setBold(True)
    fuente.setPixelSize(15 * _ESCALA)
    # Que entre a lo ancho con la letra que tenga la PC.
    ancho_maximo = ANCHO_DIBUJO_CAMPO * _ESCALA
    while QFontMetrics(fuente).horizontalAdvance("ABC") > ancho_maximo and fuente.pixelSize() > 8 * _ESCALA:
        fuente.setPixelSize(fuente.pixelSize() - 1)
    pincel = QPainter(dibujo)
    pincel.setRenderHint(QPainter.TextAntialiasing)
    pincel.setFont(fuente)
    pincel.setPen(QColor(COLOR_BARRAS))
    pincel.drawText(QRectF(0, 0, dibujo.width(), dibujo.height()), Qt.AlignCenter, "ABC")
    return _terminado(pincel, dibujo)


def dibujo_de_marca() -> QPixmap:
    """Una etiqueta azul con su agujerito: el campo busca por marca."""
    dibujo = _lienzo()
    e = _ESCALA
    etiqueta = QPainterPath()
    etiqueta.addPolygon(QPolygonF([QPointF(2 * e, 11 * e), QPointF(10 * e, 3 * e), QPointF(28 * e, 3 * e),
                                   QPointF(28 * e, 19 * e), QPointF(10 * e, 19 * e)]))
    etiqueta.closeSubpath()
    agujero = QPainterPath()
    agujero.addEllipse(QPointF(10.5 * e, 11 * e), 2.5 * e, 2.5 * e)
    pincel = QPainter(dibujo)
    pincel.setRenderHint(QPainter.Antialiasing)
    pincel.fillPath(etiqueta.subtracted(agujero), QColor(COLOR_BARRAS))
    return _terminado(pincel, dibujo)


class DelegadoProducto(QStyledItemDelegate):
    """Dibuja la celda del producto en dos renglones: la descripción y, debajo,
    chiquito y en gris, lo que trae en ROL_DETALLE (el código y el precio por
    unidad). El fondo (filas alternadas, la fila elegida) lo pinta Qt como en
    cualquier celda."""

    _MARGEN = 8

    def _fuentes(self, option):
        grande = QFont(option.font)
        chica = QFont(option.font)
        # La hoja de estilos fija la letra en píxeles: ahí el tamaño en puntos es -1.
        if grande.pixelSize() > 0:
            chica.setPixelSize(max(grande.pixelSize() - 2, 9))
        else:
            chica.setPointSizeF(max(grande.pointSizeF() - 1.5, 7))
        return grande, chica

    def paint(self, painter, option, index):
        opcion = QStyleOptionViewItem(option)
        self.initStyleOption(opcion, index)
        texto = opcion.text
        opcion.text = ""
        estilo = opcion.widget.style() if opcion.widget else None
        if estilo is not None:
            estilo.drawControl(QStyle.CE_ItemViewItem, opcion, painter, opcion.widget)
        grande, chica = self._fuentes(option)
        alto_grande = QFontMetrics(grande).height()
        alto_chica = QFontMetrics(chica).height()
        caja = option.rect.adjusted(self._MARGEN, 0, -self._MARGEN, 0)
        arriba = caja.top() + (caja.height() - alto_grande - alto_chica) // 2
        painter.save()
        painter.setFont(grande)
        painter.setPen(QColor(COLOR_PRODUCTO))
        painter.drawText(caja.left(), arriba, caja.width(), alto_grande, Qt.AlignLeft | Qt.AlignVCenter, texto)
        painter.setFont(chica)
        painter.setPen(QColor(COLOR_DETALLE))
        painter.drawText(caja.left(), arriba + alto_grande, caja.width(), alto_chica,
                         Qt.AlignLeft | Qt.AlignVCenter, index.data(ROL_DETALLE) or "")
        painter.restore()

    def sizeHint(self, option, index):
        grande, chica = self._fuentes(option)
        ancho = max(QFontMetrics(grande).horizontalAdvance(index.data(Qt.DisplayRole) or ""),
                    QFontMetrics(chica).horizontalAdvance(index.data(ROL_DETALLE) or ""))
        return QSize(ancho + 2 * self._MARGEN, QFontMetrics(grande).height() + QFontMetrics(chica).height() + 12)
