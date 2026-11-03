"""
ui/fondo_del_inicio.py
======================
La foto del kiosko de noche que va de fondo en toda la ventana principal (la eligió
el dueño, 2026-11-03). Salió de ui/main_window.py el mismo día, sin cambios, cuando
el sexto acceso (Tareas del Turno) lo hizo pasar las ~600 líneas (regla 12 de
CLAUDE.md); main_window la sigue ofreciendo con los mismos nombres.
"""

from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

# Está en assets, junto al código, como el ícono de ui/login_window.py (Kiosko.spec
# mete la carpeta entera en el .exe). Si faltara, el fondo es este azul oscuro: el
# título del inicio es claro y sobre el gris de siempre no se leería.
RUTA_FONDO_INICIO = Path(__file__).resolve().parent.parent / "assets" / "fondo_inicio.jpg"
COLOR_SIN_FONDO = "#0E1A33"


class FondoDelInicio(QWidget):
    """El widget de toda la ventana principal, con la foto de fondo. La foto tapa
    la ventana entera sin deformarse: se agranda hasta cubrirla y se recorta lo que
    sobra de los costados (o de arriba y abajo), siempre centrada. La agrandada se
    guarda y se rehace solo si cambia el tamaño: agrandarla en cada repintada le
    costaría a la PC con cada botón que titila."""

    # La foto y la agrandada son UNA para todo el programa, no una por ventana: la
    # ventana principal se vuelve a armar con cada "🔄 Operador" y con la vuelta sola
    # del Admin, y la del Admin, ya cerrada, sigue viva (VueltaDelAdmin la tiene
    # agarrada): con una agrandada propia, cada salida del Admin dejaba ~8 MB en la
    # memoria del mostrador. Se lee al armar la primera ventana y no al importar el
    # módulo: un QPixmap antes de que exista la QApplication cierra el programa.
    _foto = None
    _agrandada = None
    _agrandada_para = None  # (ancho, alto) en puntos reales de la pantalla

    def __init__(self):
        super().__init__()
        if FondoDelInicio._foto is None:
            FondoDelInicio._foto = QPixmap(str(RUTA_FONDO_INICIO))

    def paintEvent(self, _evento):
        pintor = QPainter(self)
        foto = FondoDelInicio._foto
        if foto.isNull():
            pintor.fillRect(self.rect(), QColor(COLOR_SIN_FONDO))
            pintor.end()
            return
        # En puntos reales de la pantalla: con Windows al 125% la ventana mide menos
        # "píxeles" que los que se ven, y agrandada a ese tamaño la foto saldría borrosa.
        escala = self.devicePixelRatioF()
        ancho, alto = round(self.width() * escala), round(self.height() * escala)
        if FondoDelInicio._agrandada_para != (ancho, alto):
            FondoDelInicio._agrandada = foto.scaled(ancho, alto, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            FondoDelInicio._agrandada_para = (ancho, alto)
        agrandada = FondoDelInicio._agrandada
        sobra_x = (agrandada.width() - ancho) // 2
        sobra_y = (agrandada.height() - alto) // 2
        pintor.drawPixmap(self.rect(), agrandada, QRect(sobra_x, sobra_y, ancho, alto))
        pintor.end()
