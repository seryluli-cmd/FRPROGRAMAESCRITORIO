"""
login_dibujos.py
==================
Los dibujos de la pantalla de ingreso "Elegí tu Jugador" (la maqueta C que eligió
el dueño el 2026-10-30): el fondo oscuro violeta-azul con rayas diagonales que se
deslizan despacio, el nombre del programa con letras en degradado y las fichas de
los usuarios (un círculo de color con las iniciales; la elegida se agranda y
brilla, tiene una flechita que rebota arriba, la etiqueta "P1" y un brillo que la
cruza).

Todo con QPainter y sin emojis: un emoji puede salir como un rectángulo en el
Windows del mostrador. La letra de lo que se dibuja acá se elige en el pintor, así
que la regla global `QWidget { font-size: 13px }` no la pisa; las etiquetas y los
campos comunes de la pantalla van por objectName en ui/hoja_de_estilos.py.
"""

import math
from dataclasses import dataclass, replace

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QPolygonF, QRadialGradient,
)
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QWidget

import dominio

CIAN, AZUL, VIOLETA = "#22D3EE", "#4C8DFF", "#A855F7"

# Cada cuántos segundos vuelve a empezar la animación. Las rayas, el pulso de la
# ficha elegida, el brillo que la cruza y la flechita van a múltiplos de este
# tiempo, así nada pega un salto al dar la vuelta.
PERIODO = 4.0

# Los dos colores del círculo de cada ficha, uno detrás de otro por el orden de la
# lista: dos fichas vecinas nunca quedan del mismo color.
COLORES_JUGADOR = [
    (CIAN, VIOLETA), ("#F472B6", "#FB923C"), ("#34D399", "#22D3EE"),
    ("#FBBF24", "#F97316"), ("#818CF8", "#EC4899"),
]

# Hasta cuántos usuarios van en una sola fila de fichas grandes; con más, van en
# dos filas de fichas más chicas.
MAX_EN_UNA_FILA = 5


def _color(nombre, alfa=None) -> QColor:
    color = QColor(nombre)
    if alfa is not None:
        color.setAlpha(int(max(0, min(255, alfa))))
    return color


def letra(familia: str, px: int, peso=QFont.Normal, espaciado: float = 0.0) -> QFont:
    """Una letra para el pintor, con su tamaño en píxeles (no en puntos: así mide
    lo mismo con la escala de Windows al 100 % o al 150 %)."""
    fuente = QFont(familia)
    fuente.setPixelSize(px)
    fuente.setWeight(peso)
    if espaciado:
        fuente.setLetterSpacing(QFont.AbsoluteSpacing, espaciado)
    return fuente


def brillo(widget: QWidget, color: str, radio: int, alfa: int):
    """Un resplandor parejo alrededor de `widget` (una sombra sin correr, de color)."""
    efecto = QGraphicsDropShadowEffect(widget)
    efecto.setBlurRadius(radio)
    efecto.setOffset(0, 0)
    efecto.setColor(_color(color, alfa))
    widget.setGraphicsEffect(efecto)


def iniciales(nombre: str) -> str:
    """Lo que va en el círculo de una ficha: la primera letra de las dos primeras
    palabras ("Ana Paula" → "AP") o las dos primeras letras de un nombre solo
    ("Sergio" → "SE")."""
    palabras = nombre.split()
    if not palabras:
        return "?"
    if len(palabras) > 1:
        return (palabras[0][0] + palabras[1][0]).upper()
    return palabras[0][:2].upper()


class TextoDegradado(QLabel):
    """Una etiqueta que se pinta con letras en degradado. El texto sigue siendo el
    de siempre (las pruebas buscan la etiqueta "FRKiosko"); la letra se le da al
    pintor, porque la de la hoja de estilos global le ganaría a setFont."""

    def __init__(self, texto: str, fuente: QFont, colores):
        super().__init__(texto)
        self._fuente = fuente
        self._colores = colores
        medida = QFontMetrics(fuente)
        self.setMinimumSize(medida.horizontalAdvance(texto) + 12, medida.height() + 6)

    def paintEvent(self, _evento):
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.TextAntialiasing)
        pintor.setFont(self._fuente)
        lugar = QRectF(self.contentsRect())
        ancho = pintor.fontMetrics().horizontalAdvance(self.text())
        degradado = QLinearGradient(lugar.left(), 0, lugar.left() + ancho, 0)
        for numero, color in enumerate(self._colores):
            degradado.setColorAt(numero / (len(self._colores) - 1), QColor(color))
        pintor.setPen(QPen(QBrush(degradado), 1))
        pintor.drawText(lugar, int(Qt.AlignLeft | Qt.AlignVCenter), self.text())
        pintor.end()


class FondoDelIngreso:
    """El fondo de la pantalla: el degradado, las rayas diagonales y encima la luz
    violeta del medio y la sombra del piso. Todo se dibuja una sola vez y se guarda;
    en cada cuadro de la animación solo se copian las tres capas, con la de las
    rayas corrida. Dibujar las rayas en cada cuadro le costaba a la PC el triple."""

    SEPARACION_RAYAS = 120
    # Las rayas alternan color (de a 2) y fuerza (de a 3): el dibujo se repite cada
    # 6 rayas, y al correrse eso vuelve a empezar sin que se note el salto.
    VUELTA_RAYAS = 6 * SEPARACION_RAYAS

    def __init__(self, ancho: int, alto: int):
        self._ancho = ancho
        self._alto = alto
        self._escala = None
        self._degradado = None
        self._rayas = None
        self._luces = None

    def _imagen(self, ancho: int, escala: float, relleno=Qt.transparent) -> QPixmap:
        imagen = QPixmap(round(ancho * escala), round(self._alto * escala))
        imagen.setDevicePixelRatio(escala)
        imagen.fill(relleno)
        return imagen

    def _armar_las_capas(self, escala: float):
        self._escala = escala
        todo = QRectF(0, 0, self._ancho, self._alto)

        # Sin transparencia (relleno negro): copiarla es más rápido que mezclarla.
        self._degradado = self._imagen(self._ancho, escala, Qt.black)
        pintor = QPainter(self._degradado)
        degradado = QLinearGradient(0, 0, self._ancho, self._alto)
        degradado.setColorAt(0, QColor("#0A0620"))
        degradado.setColorAt(0.6, QColor("#0B0F2C"))
        degradado.setColorAt(1, QColor("#061A2A"))
        pintor.fillRect(todo, degradado)
        pintor.end()

        # Las rayas, una vuelta más anchas que la pantalla: en cada cuadro se copian
        # corridas hasta una vuelta entera y después vuelven a empezar.
        self._rayas = self._imagen(self._ancho + self.VUELTA_RAYAS, escala)
        pintor = QPainter(self._rayas)
        pintor.setRenderHint(QPainter.Antialiasing)
        pintor.setPen(Qt.NoPen)
        for numero in range(-6, 11):
            x = numero * self.SEPARACION_RAYAS + self.VUELTA_RAYAS
            pintor.setBrush(_color(VIOLETA if numero % 2 else CIAN, 10 + (numero % 3) * 6))
            pintor.drawPolygon(QPolygonF([
                QPointF(x, 0), QPointF(x + 46, 0), QPointF(x - 254, self._alto), QPointF(x - 300, self._alto),
            ]))
        pintor.end()

        self._luces = self._imagen(self._ancho, escala)
        pintor = QPainter(self._luces)
        pintor.setPen(Qt.NoPen)
        luz = QRadialGradient(QPointF(self._ancho / 2, 270), 460)
        luz.setColorAt(0, _color("#6D28D9", 90))
        luz.setColorAt(1, _color("#000000", 0))
        pintor.setBrush(luz)
        pintor.drawRect(todo)
        piso = QLinearGradient(0, 360, 0, self._alto)
        piso.setColorAt(0, _color("#000000", 0))
        piso.setColorAt(1, _color("#000000", 170))
        pintor.setBrush(piso)
        pintor.drawRect(QRectF(0, 360, self._ancho, self._alto - 360))
        pintor.end()

    def pintar(self, pintor: QPainter, segundos: float):
        escala = pintor.device().devicePixelRatioF()
        if escala != self._escala:
            self._armar_las_capas(escala)
        pintor.drawPixmap(0, 0, self._degradado)
        corrida = round(segundos / PERIODO * 240) % self.VUELTA_RAYAS
        pintor.drawPixmap(corrida - self.VUELTA_RAYAS, 0, self._rayas)
        pintor.drawPixmap(0, 0, self._luces)


@dataclass(frozen=True)
class _Medidas:
    """Cómo es una ficha: las grandes (una fila) o las chicas (dos filas)."""
    ancho: float
    alto: float
    separacion: float        # entre dos fichas de la misma fila
    entre_filas: float       # alcanza para la flechita de una elegida de la segunda fila
    crece: tuple             # lo que se agranda la elegida: a cada lado, arriba y abajo
    arriba: float            # del borde de arriba al círculo
    radio: float
    radio_elegida: float
    letra_iniciales: int
    letra_iniciales_elegida: int
    letra_nombre: int
    letra_nombre_elegida: int
    halo: float
    flecha: float            # medio ancho de la flechita
    lugar_flecha: float      # de la punta de la flechita (en lo más alto del rebote) a la ficha
    p1_abajo: bool           # "P1" abajo al medio (grandes) o arriba a la derecha (chicas)


_GRANDES = _Medidas(
    ancho=138, alto=172, separacion=20, entre_filas=0, crece=(9, 12, 8), arriba=22,
    radio=38, radio_elegida=44, letra_iniciales=26, letra_iniciales_elegida=30,
    letra_nombre=14, letra_nombre_elegida=16, halo=150, flecha=9, lugar_flecha=42, p1_abajo=True,
)
_CHICAS = _Medidas(
    ancho=118, alto=96, separacion=14, entre_filas=30, crece=(6, 6, 5), arriba=12,
    radio=25, radio_elegida=28, letra_iniciales=18, letra_iniciales_elegida=20,
    letra_nombre=12, letra_nombre_elegida=13, halo=100, flecha=7, lugar_flecha=30, p1_abajo=False,
)
# Lo que se deja libre a cada costado cuando las fichas chicas no entran y se angostan.
_MARGEN_COSTADOS = 25


class FichasDeJugadores(QWidget):
    """
    Las fichas de los usuarios para elegir quién entra: con un clic (o un toque),
    con las flechas, con Inicio y Fin, o con la primera letra del nombre. Con más de
    MAX_EN_UNA_FILA usuarios, van en dos filas de fichas más chicas.

    Reemplaza a la lista desplegable de antes y tiene lo que se usaba de ella
    (count, itemText, currentIndex, currentText, setCurrentIndex y la señal
    currentIndexChanged), así la pantalla de ingreso y las pruebas la usan igual.
    `momento` son los segundos de la animación: lo pone la pantalla en cada cuadro.
    """

    currentIndexChanged = Signal(int)
    # Un clic o un toque en una ficha: además de elegirla, la pantalla pasa a la clave.
    tocada = Signal(int)

    def __init__(self, nombres):
        super().__init__()
        self._nombres = list(nombres)
        self._actual = 0 if self._nombres else -1
        self._debajo_del_mouse = -1
        self.momento = 0.0
        self._clave_de_lo_quieto = None
        self._otras_fichas = None
        self._halo = None
        self._lugar_del_halo = QPointF()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("Elegí tu jugador")

    # ------------------------------------------------ lo de la lista desplegable
    def count(self) -> int:
        return len(self._nombres)

    def itemText(self, indice: int) -> str:
        return self._nombres[indice] if 0 <= indice < len(self._nombres) else ""

    def currentIndex(self) -> int:
        return self._actual

    def currentText(self) -> str:
        return self.itemText(self._actual)

    def setCurrentIndex(self, indice: int):
        if not 0 <= indice < len(self._nombres) or indice == self._actual:
            return
        self._actual = indice
        self.update()
        self.currentIndexChanged.emit(indice)

    # ------------------------------------------------ dónde va cada ficha
    def sizeHint(self) -> QSize:
        return QSize(960, 270)

    def minimumSizeHint(self) -> QSize:
        return QSize(400, 240)

    def _por_fila(self) -> int:
        cantidad = len(self._nombres)
        return cantidad if cantidad <= MAX_EN_UNA_FILA else math.ceil(cantidad / 2)

    def _medidas(self) -> _Medidas:
        if len(self._nombres) <= MAX_EN_UNA_FILA:
            return _GRANDES
        por_fila = self._por_fila()
        lugar = (self.width() - 2 * _MARGEN_COSTADOS - (por_fila - 1) * _CHICAS.separacion) / por_fila
        if lugar >= _CHICAS.ancho:
            return _CHICAS
        # Muchísimos usuarios: las fichas se angostan (el nombre largo se corta con
        # "...") y el círculo achica para no salirse de la ficha.
        ancho = max(lugar, 40)
        return replace(_CHICAS, ancho=ancho, radio=min(_CHICAS.radio, ancho / 2 - 6),
                       radio_elegida=min(_CHICAS.radio_elegida, ancho / 2 - 3))

    def rectangulo_de_la_ficha(self, indice: int) -> QRectF:
        """Dónde está la ficha `indice`, sin agrandar aunque sea la elegida."""
        medidas = self._medidas()
        por_fila = self._por_fila()
        filas = 1 if len(self._nombres) <= por_fila else 2
        alto_de_todo = (medidas.lugar_flecha + filas * medidas.alto
                        + (filas - 1) * medidas.entre_filas + medidas.crece[2])
        # Más cerca del título que del saludo de abajo, como en la maqueta.
        arriba = max(0.0, (self.height() - alto_de_todo) * 0.2) + medidas.lugar_flecha
        fila, columna = divmod(indice, por_fila)
        en_esta_fila = min(por_fila, len(self._nombres) - fila * por_fila)
        ancho_fila = en_esta_fila * medidas.ancho + (en_esta_fila - 1) * medidas.separacion
        x = (self.width() - ancho_fila) / 2 + columna * (medidas.ancho + medidas.separacion)
        y = arriba + fila * (medidas.alto + medidas.entre_filas)
        return QRectF(x, y, medidas.ancho, medidas.alto)

    def _rectangulo_dibujado(self, indice: int, medidas: _Medidas) -> QRectF:
        rectangulo = self.rectangulo_de_la_ficha(indice)
        if indice != self._actual:
            return rectangulo
        costado, arriba, abajo = medidas.crece
        return rectangulo.adjusted(-costado, -arriba, costado, abajo)

    def _ficha_en(self, punto) -> int:
        medidas = self._medidas()
        # La elegida primero: agrandada, tapa un poco a las vecinas.
        orden = [self._actual] + [i for i in range(len(self._nombres)) if i != self._actual]
        for indice in orden:
            if indice >= 0 and self._rectangulo_dibujado(indice, medidas).contains(QPointF(punto)):
                return indice
        return -1

    # ------------------------------------------------ mouse y teclado
    def mousePressEvent(self, evento):
        indice = self._ficha_en(evento.position())
        if evento.button() == Qt.LeftButton and indice >= 0:
            self.setCurrentIndex(indice)
            self.tocada.emit(indice)
            return
        super().mousePressEvent(evento)

    def mouseMoveEvent(self, evento):
        indice = self._ficha_en(evento.position())
        if indice != self._debajo_del_mouse:
            self._debajo_del_mouse = indice
            if indice >= 0:
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.unsetCursor()
            self.update()
        super().mouseMoveEvent(evento)

    def leaveEvent(self, evento):
        self._debajo_del_mouse = -1
        self.update()
        super().leaveEvent(evento)

    def keyPressEvent(self, evento):
        cantidad = len(self._nombres)
        actual = self._actual
        por_fila = self._por_fila()
        dos_filas = cantidad > por_fila
        tecla = evento.key()
        if cantidad == 0:
            super().keyPressEvent(evento)
        elif tecla == Qt.Key_Left or (tecla == Qt.Key_Up and not dos_filas):
            self.setCurrentIndex(max(0, actual - 1))
        elif tecla == Qt.Key_Right or (tecla == Qt.Key_Down and not dos_filas):
            self.setCurrentIndex(min(cantidad - 1, actual + 1))
        elif tecla == Qt.Key_Up:
            if actual >= por_fila:
                self.setCurrentIndex(actual - por_fila)
        elif tecla == Qt.Key_Down:
            if actual < por_fila:
                self.setCurrentIndex(min(cantidad - 1, actual + por_fila))
        elif tecla == Qt.Key_Home:
            self.setCurrentIndex(0)
        elif tecla == Qt.Key_End:
            self.setCurrentIndex(cantidad - 1)
        elif not self._saltar_a_la_letra(evento.text()):
            super().keyPressEvent(evento)

    def _saltar_a_la_letra(self, texto: str) -> bool:
        """Como hacía la lista desplegable: una letra elige el próximo nombre que
        empieza con ella (sin mirar mayúsculas ni acentos)."""
        letra_buscada = dominio.sin_acentos(texto)
        if len(letra_buscada) != 1 or not letra_buscada.isalnum():
            return False
        cantidad = len(self._nombres)
        for paso in range(1, cantidad + 1):
            indice = (self._actual + paso) % cantidad
            if dominio.sin_acentos(self._nombres[indice]).startswith(letra_buscada):
                self.setCurrentIndex(indice)
                break
        return True

    # ------------------------------------------------ el dibujo
    def paintEvent(self, _evento):
        if not self._nombres:
            return
        pintor = QPainter(self)
        pintor.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        medidas = self._medidas()
        # Lo que no se mueve (el halo a toda fuerza y las fichas que no están
        # elegidas) se dibuja una vez y se guarda hasta que cambia la elegida, el
        # mouse o el tamaño: rehacerlo en cada cuadro de la animación le costaba a la
        # PC tanto como todo el resto de la pantalla.
        clave = (self.width(), self.height(), pintor.device().devicePixelRatioF(),
                 self._actual, self._debajo_del_mouse)
        if clave != self._clave_de_lo_quieto:
            self._armar_lo_quieto(clave[2], medidas)
            self._clave_de_lo_quieto = clave
        if self._halo is not None:
            # El halo late: es la misma imagen, más o menos fuerte.
            pintor.setOpacity((70 + 50 * self._pulso(self.momento)) / 120)
            pintor.drawPixmap(self._lugar_del_halo, self._halo)
            pintor.setOpacity(1)
        pintor.drawPixmap(0, 0, self._otras_fichas)
        if self._actual >= 0:
            self._pintar_ficha(pintor, self._actual, medidas, self.momento)
        pintor.end()

    @staticmethod
    def _imagen_vacia(ancho: float, alto: float, escala: float) -> QPixmap:
        imagen = QPixmap(math.ceil(ancho * escala), math.ceil(alto * escala))
        imagen.setDevicePixelRatio(escala)
        imagen.fill(Qt.transparent)
        return imagen

    def _armar_lo_quieto(self, escala: float, medidas: _Medidas):
        self._otras_fichas = self._imagen_vacia(self.width(), self.height(), escala)
        pintor = QPainter(self._otras_fichas)
        pintor.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        for indice in range(len(self._nombres)):
            if indice != self._actual:
                self._pintar_ficha(pintor, indice, medidas, 0.0)
        pintor.end()

        self._halo = None
        if self._actual < 0:
            return
        centro = self._rectangulo_dibujado(self._actual, medidas).center()
        color, _ = COLORES_JUGADOR[self._actual % len(COLORES_JUGADOR)]
        # Que se apague antes del borde de arriba y de abajo de las fichas: cortado
        # ahí, se veía la línea recta del corte sobre el fondo oscuro.
        radio = max(1.0, min(medidas.halo, centro.y(), self.height() - centro.y()))
        self._halo = self._imagen_vacia(2 * radio, 2 * radio, escala)
        self._lugar_del_halo = QPointF(centro.x() - radio, centro.y() - radio)
        halo = QRadialGradient(QPointF(radio, radio), radio)
        halo.setColorAt(0, _color(color, 120))
        halo.setColorAt(1, _color(color, 0))
        pintor = QPainter(self._halo)
        pintor.setRenderHint(QPainter.Antialiasing)
        pintor.setPen(Qt.NoPen)
        pintor.setBrush(halo)
        pintor.drawEllipse(QPointF(radio, radio), radio, radio)
        pintor.end()

    def _pulso(self, segundos: float) -> float:
        return 0.5 + 0.5 * math.sin(2 * math.pi * segundos / PERIODO * 2)

    def _pintar_ficha(self, pintor, indice, medidas, segundos):
        elegida = indice == self._actual
        lugar = self._rectangulo_dibujado(indice, medidas)
        color1, color2 = COLORES_JUGADOR[indice % len(COLORES_JUGADOR)]
        if elegida:
            self._pintar_marco_de_la_elegida(pintor, lugar, medidas, segundos, color1, color2)
        else:
            encima = indice == self._debajo_del_mouse
            pintor.setPen(QPen(_color("#FFFFFF", 110 if encima else 38), 1))
            pintor.setBrush(_color("#FFFFFF", 22 if encima else 12))
            pintor.drawRoundedRect(lugar, 14, 14)
            # Las que no están elegidas, apagadas: así la elegida se ve de lejos.
            pintor.setOpacity(0.55)

        # El círculo con las iniciales y el nombre debajo.
        radio = medidas.radio_elegida if elegida else medidas.radio
        centro = QPointF(lugar.center().x(), lugar.top() + medidas.arriba + radio)
        circulo = QLinearGradient(centro.x() - radio, centro.y() - radio, centro.x() + radio, centro.y() + radio)
        circulo.setColorAt(0, QColor(color1))
        circulo.setColorAt(1, QColor(color2))
        pintor.setPen(Qt.NoPen)
        pintor.setBrush(circulo)
        pintor.drawEllipse(centro, radio, radio)
        pintor.setPen(QColor("#FFFFFF"))
        pintor.setFont(letra("Bahnschrift",
                             medidas.letra_iniciales_elegida if elegida else medidas.letra_iniciales, QFont.Bold))
        pintor.drawText(QRectF(centro.x() - radio, centro.y() - radio, radio * 2, radio * 2), Qt.AlignCenter,
                        iniciales(self._nombres[indice]))
        fuente_nombre = letra("Segoe UI", medidas.letra_nombre_elegida if elegida else medidas.letra_nombre,
                              QFont.Bold)
        pintor.setFont(fuente_nombre)
        pintor.setPen(QColor("#FFFFFF") if elegida else QColor("#B9B5D9"))
        nombre = QFontMetrics(fuente_nombre).elidedText(self._nombres[indice], Qt.ElideRight, int(lugar.width()) - 12)
        pintor.drawText(QRectF(lugar.left(), centro.y() + radio + 6, lugar.width(), medidas.letra_nombre + 12),
                        Qt.AlignCenter, nombre)
        pintor.setOpacity(1)

    def _pintar_marco_de_la_elegida(self, pintor, lugar, medidas, segundos, color1, color2):
        pulso = self._pulso(segundos)
        cuerpo = QLinearGradient(lugar.topLeft(), lugar.bottomLeft())
        cuerpo.setColorAt(0, _color("#1C1F4A", 245))
        cuerpo.setColorAt(1, _color("#0E1030", 245))
        pintor.setBrush(cuerpo)
        borde = QLinearGradient(lugar.topLeft(), lugar.bottomRight())
        borde.setColorAt(0, QColor(color1))
        borde.setColorAt(1, QColor(color2))
        # El borde que brilla: dos pasadas anchas y suaves y una fina con el degradado.
        for ancho, alfa in ((8, 40 + 30 * pulso), (4, 90)):
            pintor.setPen(QPen(_color(color1, alfa), ancho))
            pintor.drawRoundedRect(lugar, 16, 16)
        pintor.setPen(QPen(QBrush(borde), 2))
        pintor.drawRoundedRect(lugar, 16, 16)

        # El brillo que cruza la ficha, de izquierda a derecha.
        cruce = ((segundos / PERIODO) * 2 % 1.0) * (lugar.width() + 160) - 80
        pintor.save()
        contorno = QPainterPath()
        contorno.addRoundedRect(lugar, 16, 16)
        pintor.setClipPath(contorno)
        reflejo = QLinearGradient(lugar.left() + cruce - 40, 0, lugar.left() + cruce + 40, 0)
        reflejo.setColorAt(0, _color("#FFFFFF", 0))
        reflejo.setColorAt(0.5, _color("#FFFFFF", 40))
        reflejo.setColorAt(1, _color("#FFFFFF", 0))
        pintor.setPen(Qt.NoPen)
        pintor.setBrush(reflejo)
        pintor.drawRect(lugar)
        pintor.restore()

        # La flechita que rebota arriba.
        rebote = medidas.flecha / 9 * 4 * math.sin(2 * math.pi * segundos / PERIODO * 4)
        punta = lugar.top() - medidas.flecha * 2 + rebote
        medio = lugar.center().x()
        pintor.setPen(Qt.NoPen)
        pintor.setBrush(QColor(color1))
        pintor.drawPolygon(QPolygonF([
            QPointF(medio - medidas.flecha, punta - medidas.flecha + 1),
            QPointF(medio + medidas.flecha, punta - medidas.flecha + 1),
            QPointF(medio, punta + 2),
        ]))

        # La etiqueta "P1".
        if medidas.p1_abajo:
            etiqueta = QRectF(medio - 20, lugar.bottom() - 26, 40, 18)
            pintor.setFont(letra("Bahnschrift", 10, QFont.Bold, 2))
        else:
            etiqueta = QRectF(lugar.right() - 32, lugar.top() + 6, 26, 15)
            pintor.setFont(letra("Bahnschrift", 9, QFont.Bold, 1))
        pintor.setBrush(QColor(color1))
        pintor.drawRoundedRect(etiqueta, etiqueta.height() / 2, etiqueta.height() / 2)
        pintor.setPen(QColor("#0B0B1E"))
        pintor.drawText(etiqueta, Qt.AlignCenter, "P1")
