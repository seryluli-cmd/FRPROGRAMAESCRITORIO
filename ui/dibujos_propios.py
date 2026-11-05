"""
dibujos_propios.py
==================
Los dibujitos que no son emojis de Windows: se pintan acá con QPainter y se piden
por su nombre, igual que un emoji (`ui.utils.icono_de_emoji` y
`ui.piezas_ventana.cabecera_oscura` los aceptan).

Nació el 2026-11-04 con PEDIDOS DE CLIENTES. El 🙋 que tenía es "persona con la
mano levantada", pero Windows lo dibuja como una mujer de pelo naranja, y el dueño
lo quería sin género y gris. Los emojis de silueta de Windows (👤 👥 🗣️) salen
violeta oscuro y casi no se ven sobre el azul de los accesos del inicio, así que
de una maqueta de cuatro dibujos grises eligió las "dos siluetas".

Se pintan sobre una grilla de 64 x 64 (la de la maqueta) escalada al lugar que se
pida, así se ven nítidos en cualquier tamaño. No usan QtSvg a propósito: con eso
el .exe tendría que llevar un módulo más de Qt por un solo dibujo.
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGradient, QLinearGradient, QPainterPath

DOS_SILUETAS = "dos siluetas grises"

# Lado de la grilla en la que están pensados los dibujos.
_GRILLA = 64

# Los grises de las siluetas, de arriba (la luz) hacia abajo. La de adelante, más
# clara; la de atrás, más oscura, para que se separen sin dibujarles un borde.
_GRIS_ADELANTE = ("#E9ECF1", "#9AA4B1")
_GRIS_ATRAS = ("#AEB6C1", "#6E7886")


def es_dibujo_propio(dibujito: str) -> bool:
    """Si `dibujito` es uno de los de acá (y no un emoji)."""
    return dibujito in _DIBUJOS


def pintar(pintor, dibujito: str, lugar: QRectF):
    """Pinta `dibujito` llenando el cuadrado `lugar`."""
    pintor.save()
    pintor.setRenderHint(pintor.RenderHint.Antialiasing)
    pintor.translate(lugar.topLeft())
    pintor.scale(lugar.width() / _GRILLA, lugar.height() / _GRILLA)
    pintor.setPen(Qt.NoPen)
    _DIBUJOS[dibujito](pintor)
    pintor.restore()


def _degradado(arriba: str, abajo: str):
    """De arriba hacia abajo de CADA forma que se pinte con él (como el degradado de
    un SVG): la cabeza y el cuerpo de una silueta tienen cada uno su luz arriba."""
    degradado = QLinearGradient(0, 0, 0, 1)
    degradado.setCoordinateMode(QGradient.ObjectBoundingMode)
    degradado.setColorAt(0, QColor(arriba))
    degradado.setColorAt(1, QColor(abajo))
    return degradado


def _silueta(pintor, cabeza, hombros, colores):
    """Una persona de la cintura para arriba. `cabeza` = (x, y, radio). `hombros` =
    (izquierda, derecha, arriba, abajo, curva): el cuerpo va de punta a punta, sube
    en curva hasta `arriba` en el medio y apoya en `abajo`; `curva` es cuánto más
    abajo de `arriba` empieza a doblar el hombro y `x` de la cabeza es el medio. El
    hombro termina de doblar a la altura del borde de la cabeza."""
    x, y, radio = cabeza
    izquierda, derecha, arriba, abajo, curva = hombros
    redondeo = (derecha - izquierda) / 2 - radio
    cuerpo = QPainterPath(QPointF(izquierda, abajo))
    cuerpo.cubicTo(izquierda, arriba + curva, izquierda + redondeo, arriba, x, arriba)
    cuerpo.cubicTo(derecha - redondeo, arriba, derecha, arriba + curva, derecha, abajo)
    cuerpo.closeSubpath()
    pintor.setBrush(_degradado(*colores))
    pintor.drawEllipse(QPointF(x, y), radio, radio)
    pintor.drawPath(cuerpo)


def _dos_siluetas(pintor):
    # Las medidas de la maqueta que eligió el dueño. Primero la de atrás (más arriba y
    # a la derecha): la de adelante la tapa en parte.
    _silueta(pintor, (43, 17, 9.5), (26, 60, 32, 56, 8), _GRIS_ATRAS)
    _silueta(pintor, (23, 25, 11), (3, 43, 39, 63, 7), _GRIS_ADELANTE)


_DIBUJOS = {
    DOS_SILUETAS: _dos_siluetas,
}
