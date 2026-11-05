"""
ui/pelotita.py
==============
La pelotita que rebota por el inicio, como la del Arkanoid y con estela de cometa
(pedido del dueño, 2026-11-04: "una pelotita tipo arcanoid como si fuera un cometa
valla rebotando aleatoriamente por el programa"). De las maquetas animadas
(PROPUESTA_PELOTITA, en la carpeta de los proyectos) eligió la A: solo en el
inicio, debajo de la barra de botones, celeste y a velocidad media. Es solo
adorno: no muestra nada ni se puede tocar, y el Administrador la apaga y la prende
en Configuración ADMIN (repositories/pelotita_repo.py).

Va en un widget transparente encima del inicio (`#inicioKiosko`, la foto de abajo
de la barra), que lo cubre entero y deja pasar los clics a los accesos. Para que no
le cueste nada al mostrador (ni a Vender ni a la pistola de códigos, que usan el
mismo hilo), cada cuadro vuelve a pintar solo los cuadraditos por donde estaba y
por donde está la pelotita con su estela, no el rectángulo entero que la encierra,
y mientras no se ve no hace nada.

`Rebote` es la cuenta del movimiento, sin Qt (la prueban tests/test_pelotita.py);
`PelotitaQueRebota` la dibuja.
"""

import math
import random
import time

from PySide6.QtCore import QEvent, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient, QRegion
from PySide6.QtWidgets import QWidget

# Puntos de la pantalla por segundo: la "Media" de la maqueta. Va por el reloj y no por
# cuadros, así no se pone lenta si un cuadro llega tarde.
VELOCIDAD = 420
# Unos 30 cuadros por segundo, como el cometa del cyber.
MILISEGUNDOS_POR_CUADRO = 33
# Si la pantalla estuvo trabada (un reporte largo), sigue desde donde estaba en vez de
# saltar todo lo que se perdió.
PASO_MAXIMO_SEGUNDOS = 0.1
# Rebote "tipo Arkanoid": en cada choque el ángulo cambia un poco al azar, así nunca
# repite el mismo camino. Pero nunca sale casi acostada ni casi parada: tardaría una
# eternidad en cruzar la pantalla, yendo y viniendo contra el mismo par de paredes.
DESVIO_GRADOS = 12
INCLINACION_MINIMA = 25
INCLINACION_MAXIMA = 65

# El dibujo, en puntos de la pantalla del mostrador (1920 x 1080).
RADIO = 8                 # la pelotita; rebota cuando su borde toca la pared
RADIO_BRILLO = 22         # el brillo de alrededor
LARGO_COLA = 260          # cuánto camino recorrido muestra la estela
# La estela se dibuja como la del cometa del cyber: capas encimadas, cada una más
# corta, gruesa y clara. Cada capa es un solo trazo continuo: en tramos sueltos se
# notan los cortes o sale punteada.
CAPAS_COLA = 16
OPACIDAD_CAPA = 0.22
GROSOR_PUNTA = 1.5
GROSOR_CABEZA = 11

COLOR_CABEZA = QColor("#EAF4FF")   # casi blanco
COLOR_COLA = QColor("#4C8DFF")     # el azul de la barra y del cometa del cyber


def _hasta(puntos: list, largo: float) -> list:
    """Los puntos de `puntos` (de la cabeza a la punta) hasta recorrer `largo`; el
    último se corta en el medio de su tramo si hace falta."""
    if not puntos:
        return []
    recorrido = [puntos[0]]
    hecho = 0.0
    for (x1, y1), (x2, y2) in zip(puntos, puntos[1:]):
        tramo = math.hypot(x2 - x1, y2 - y1)
        if hecho + tramo >= largo:
            parte = (largo - hecho) / tramo if tramo else 0.0
            recorrido.append((x1 + (x2 - x1) * parte, y1 + (y2 - y1) * parte))
            return recorrido
        recorrido.append((x2, y2))
        hecho += tramo
    return recorrido


def largo_de(puntos: list) -> float:
    """Lo que mide el camino que une `puntos`, uno tras otro."""
    return sum(math.hypot(x2 - x1, y2 - y1) for (x1, y1), (x2, y2) in zip(puntos, puntos[1:]))


class Rebote:
    """Dónde está la pelotita, para dónde va y el camino que dejó atrás (la estela),
    dentro de un rectángulo de `ancho` x `alto` con la esquina en (0, 0). Sin Qt."""

    def __init__(self, ancho: float, alto: float, al_azar: random.Random = None):
        self._azar = al_azar or random.Random()
        self.ancho, self.alto = ancho, alto
        self.x = ancho * self._azar.uniform(0.25, 0.75)
        self.y = alto * self._azar.uniform(0.25, 0.75)
        inclinacion = math.radians(self._azar.uniform(INCLINACION_MINIMA, INCLINACION_MAXIMA))
        self.vx = math.cos(inclinacion) * self._azar.choice((-1, 1))
        self.vy = math.sin(inclinacion) * self._azar.choice((-1, 1))
        # De la cabeza a la punta de la estela. Cada choque deja su punto exacto: así
        # la estela dobla justo en la pared y no corta camino por adentro.
        self.cola = [(self.x, self.y)]
        self.rebotes = 0

    def cambiar_tamano(self, ancho: float, alto: float):
        """La ventana cambió de tamaño: si la pelotita quedó afuera, vuelve adentro."""
        self.ancho, self.alto = ancho, alto
        self.x = min(max(self.x, RADIO), max(RADIO, ancho - RADIO))
        self.y = min(max(self.y, RADIO), max(RADIO, alto - RADIO))
        self.cola = [(self.x, self.y)]

    def avanzar(self, distancia: float):
        """Corre `distancia` puntos, rebotando en cada pared que toque en el camino."""
        minimo_x, maximo_x = RADIO, self.ancho - RADIO
        minimo_y, maximo_y = RADIO, self.alto - RADIO
        if maximo_x <= minimo_x or maximo_y <= minimo_y:
            return  # no hay lugar para la pelotita (la ventana está achicada del todo)
        resto = distancia
        # Un tope de choques por paso: con un paso normal (14 puntos) hay uno como mucho.
        for _ in range(8):
            if resto <= 1e-9:
                break
            hasta_x = self._hasta_la_pared(self.x, self.vx, minimo_x, maximo_x)
            hasta_y = self._hasta_la_pared(self.y, self.vy, minimo_y, maximo_y)
            hasta_el_choque = max(0.0, min(hasta_x, hasta_y))
            if hasta_el_choque >= resto:
                self.x += self.vx * resto
                self.y += self.vy * resto
                break
            self.x += self.vx * hasta_el_choque
            self.y += self.vy * hasta_el_choque
            resto -= hasta_el_choque
            self.cola.insert(0, (self.x, self.y))
            # En una esquina choca con las dos paredes a la vez y vuelve por donde vino.
            vx = -self.vx if hasta_x <= hasta_y else self.vx
            vy = -self.vy if hasta_y <= hasta_x else self.vy
            self.vx, self.vy = self._desviar(vx, vy)
            self.rebotes += 1
        # Por si una cuenta con decimales la dejó un pelito afuera.
        self.x = min(max(self.x, minimo_x), maximo_x)
        self.y = min(max(self.y, minimo_y), maximo_y)
        self.cola.insert(0, (self.x, self.y))
        self.cola = _hasta(self.cola, LARGO_COLA)

    @staticmethod
    def _hasta_la_pared(donde: float, hacia: float, minimo: float, maximo: float) -> float:
        """Cuánto camino le falta para tocar la pared a la que va, en esa dirección."""
        if hacia > 0:
            return (maximo - donde) / hacia
        if hacia < 0:
            return (minimo - donde) / hacia
        return math.inf

    def _desviar(self, vx: float, vy: float) -> tuple:
        """La dirección después del choque: la que sale del rebote, con el ángulo un poco
        cambiado al azar y entre INCLINACION_MINIMA e INCLINACION_MAXIMA. Conserva para
        qué lado va en cada eje, así siempre se aleja de la pared que tocó."""
        inclinacion = math.degrees(math.atan2(abs(vy), abs(vx)))
        inclinacion += self._azar.uniform(-DESVIO_GRADOS, DESVIO_GRADOS)
        inclinacion = math.radians(min(INCLINACION_MAXIMA, max(INCLINACION_MINIMA, inclinacion)))
        return (math.copysign(math.cos(inclinacion), vx), math.copysign(math.sin(inclinacion), vy))

    def inclinacion(self) -> float:
        """El ángulo con la horizontal hacia donde va, en grados (de 0 a 90)."""
        return math.degrees(math.atan2(abs(self.vy), abs(self.vx)))


def _mezcla(desde: QColor, hasta: QColor, cuanto: float) -> QColor:
    """El color que está `cuanto` (0 a 1) del camino entre `desde` y `hasta`."""
    return QColor(
        round(desde.red() + (hasta.red() - desde.red()) * cuanto),
        round(desde.green() + (hasta.green() - desde.green()) * cuanto),
        round(desde.blue() + (hasta.blue() - desde.blue()) * cuanto),
    )


class PelotitaQueRebota(QWidget):
    def __init__(self, lugar: QWidget, al_azar: random.Random = None, reloj=time.monotonic):
        """Se pone encima de `lugar` (el inicio), rebota en sus bordes y lo sigue si
        cambia de tamaño."""
        super().__init__(lugar)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.rebote = Rebote(lugar.width(), lugar.height(), al_azar)
        self._reloj = reloj
        self._antes = None             # la hora del cuadro anterior (None: recién arranca)
        self._zona_pintada = QRegion()
        lugar.installEventFilter(self)
        self._acomodar()
        # Si el inicio ya estaba a la vista (al prenderla desde Configuración ADMIN), un
        # hijo nuevo no se muestra solo.
        self.show()

        self._timer = QTimer(self)
        self._timer.setInterval(MILISEGUNDOS_POR_CUADRO)
        self._timer.timeout.connect(self._avanzar)
        self._timer.start()

    def detener(self):
        """La deja quieta para siempre (al cerrarse la ventana principal o al apagarla):
        la ventana del Admin, ya cerrada, sigue viva (ui/vuelta_del_admin.py)."""
        self._timer.stop()

    def eventFilter(self, objeto, evento):
        if objeto is self.parent() and evento.type() == QEvent.Resize:
            self._acomodar()
        return False

    def _acomodar(self):
        """La estira al tamaño del inicio, la deja encima de todo lo de adentro y le
        avisa al rebote el tamaño nuevo."""
        self.setGeometry(self.parent().rect())
        self.raise_()
        self.rebote.cambiar_tamano(self.width(), self.height())
        self._zona_pintada = QRegion()
        self.update()

    def _avanzar(self):
        if not self.isVisible() or self.window().isMinimized():
            self._antes = None
            return  # el inicio no se ve: no se gasta nada
        ahora = self._reloj()
        paso = 0.0 if self._antes is None else min(PASO_MAXIMO_SEGUNDOS, max(0.0, ahora - self._antes))
        self._antes = ahora
        self.rebote.avanzar(VELOCIDAD * paso)
        zona_nueva = self.zona_a_pintar()
        # Se borra donde estaba y se pinta donde está: nada más.
        self.update(self._zona_pintada.united(zona_nueva))
        self._zona_pintada = zona_nueva

    def zona_a_pintar(self) -> QRegion:
        """Lo que ocupa la pelotita con su estela: un cuadradito por cada tramo de la
        estela y uno para el brillo. Con un solo rectángulo, una estela en diagonal
        haría repintar tres veces más foto y botones en cada cuadro."""
        margen = math.ceil(GROSOR_CABEZA / 2) + 2
        zona = QRegion()
        cola = self.rebote.cola
        for (x1, y1), (x2, y2) in zip(cola, cola[1:]):
            izquierda, arriba = math.floor(min(x1, x2)) - margen, math.floor(min(y1, y2)) - margen
            derecha, abajo = math.ceil(max(x1, x2)) + margen, math.ceil(max(y1, y2)) + margen
            zona = zona.united(QRect(izquierda, arriba, derecha - izquierda, abajo - arriba))
        cabeza_x, cabeza_y = cola[0]
        lado = RADIO_BRILLO + 2
        return zona.united(QRect(math.floor(cabeza_x) - lado, math.floor(cabeza_y) - lado, 2 * lado + 1, 2 * lado + 1))

    def paintEvent(self, _evento):
        cola = self.rebote.cola
        pincel = QPainter(self)
        pincel.setRenderHint(QPainter.Antialiasing)
        # La estela: capas que salen todas de la cabeza, cada una más corta, más gruesa y
        # más clara que la anterior. Cerca de la cabeza se juntan todas (gruesa, blanca y
        # opaca) y en la punta queda solo la primera (finita, azul y casi transparente).
        if len(cola) > 1:
            largo = largo_de(cola)
            for capa in range(CAPAS_COLA):
                cerca = (capa + 1) / CAPAS_COLA          # la última capa es la de la cabeza
                puntos = _hasta(cola, largo * (CAPAS_COLA - capa) / CAPAS_COLA)
                trazo = QPainterPath(QPointF(*puntos[0]))
                for punto in puntos[1:]:
                    trazo.lineTo(QPointF(*punto))
                color = _mezcla(COLOR_COLA, COLOR_CABEZA, cerca ** 2)
                color.setAlphaF(OPACIDAD_CAPA)
                grosor = GROSOR_PUNTA + (GROSOR_CABEZA - GROSOR_PUNTA) * cerca
                pincel.setPen(QPen(color, grosor, Qt.SolidLine, Qt.FlatCap, Qt.RoundJoin))
                pincel.drawPath(trazo)
        cabeza = QPointF(*cola[0])
        pincel.setPen(Qt.NoPen)
        # El brillo de alrededor.
        brillo = QRadialGradient(cabeza, RADIO_BRILLO)
        brillo.setColorAt(0.0, QColor(234, 244, 255, 230))
        brillo.setColorAt(0.35, QColor(76, 141, 255, 140))
        brillo.setColorAt(1.0, QColor(76, 141, 255, 0))
        pincel.setBrush(brillo)
        pincel.drawEllipse(cabeza, RADIO_BRILLO, RADIO_BRILLO)
        # La pelotita: una bolita con el reflejo arriba a la izquierda, como la del Arkanoid.
        bolita = QRadialGradient(cabeza, RADIO, cabeza - QPointF(RADIO * 0.35, RADIO * 0.35))
        bolita.setColorAt(0.0, QColor("#FFFFFF"))
        bolita.setColorAt(0.55, COLOR_CABEZA)
        bolita.setColorAt(1.0, COLOR_COLA)
        pincel.setBrush(bolita)
        pincel.drawEllipse(cabeza, RADIO, RADIO)
        pincel.end()
