"""
ui/espera_del_mostrador.py
==========================
En la copia abierta desde otra PC (admin_remoto/), cada pantalla le pide los datos
al mostrador por la red y espera la respuesta. Casi siempre tarda milisegundos, pero
un reporte largo, la red lenta o el mostrador ocupado la estiran: hasta
`cliente.ESPERA_HOLA_SEGUNDOS` al entrar y `cliente.ESPERA_LLAMADA_SEGUNDOS` en
cualquier pantalla. Con el pedido en el hilo de la pantalla, en ese rato la copia
quedaba trabada: no se movía ni se cerraba, Windows la marcaba "No responde" y
ofrecía cerrarla.

Por eso el pedido va en un hilo aparte (`esperar`, que main.py le pasa a la
conexión). Si contesta en menos de SEGUNDOS_SIN_CARTEL, como casi siempre, no se ve
nada distinto. Si no, sale el cartel "Esperando al mostrador" con los segundos que
van y DEJAR DE ESPERAR. El cartel es modal: las ventanas de atrás no reciben clics,
así que nadie aprieta otra cosa con la respuesta en camino. Dejar de esperar es como
un corte de la red: el mostrador pudo haberlo hecho igual, y el aviso de
admin_remoto/cliente.py (SinRespuesta) dice que se fije antes de repetirlo.

Las reglas de ui/en_segundo_plano.py valen acá también: al hilo van solo la función
del pedido y datos (nunca Qt), es daemon y el error vuelve sin ciclos (con las mismas
_correr y Respuesta).

Espera así solo en el hilo de la pantalla y de a un pedido por vez. Un pedido desde
otro hilo (la revisión de la caja de la ventana principal) o uno que llega con un
cartel ya abierto (desde un reloj de una pantalla) se hace y se espera ahí mismo,
como antes: un cartel encima de otro no se cerraría en orden.
"""

import threading
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout

from ui.en_segundo_plano import Respuesta, _correr
from ui.piezas_ventana import cabecera_oscura, tecla
from ui.utils import sin_boton_por_defecto

# Hasta acá se espera sin mostrar nada: lo de casi siempre (milisegundos) no hace
# aparecer y desaparecer un cartel.
SEGUNDOS_SIN_CARTEL = 0.7
MILISEGUNDOS_ENTRE_VISTAS = 100

_hay_un_cartel_abierto = False


class SeDejoDeEsperar(TimeoutError):
    """Se apretó DEJAR DE ESPERAR. Es un TimeoutError a propósito: cliente._pedir lo
    trata igual que una espera vencida (SinRespuesta; al entrar, "no contestó a
    tiempo"), porque el pedido ya pudo haber llegado al mostrador."""


def esperar(trabajo, *argumentos):
    """
    Hace `trabajo(*argumentos)` (el pedido al mostrador: cliente._mandar) en un hilo
    aparte y devuelve lo que devuelve, o levanta su error acá. Si tarda más de
    SEGUNDOS_SIN_CARTEL, espera con el cartel; SeDejoDeEsperar si se lo cierra antes
    de que conteste.
    """
    global _hay_un_cartel_abierto
    if _hay_un_cartel_abierto or threading.current_thread() is not threading.main_thread():
        return trabajo(*argumentos)
    resultado = {}
    hilo = threading.Thread(
        target=_correr, args=(trabajo, argumentos, resultado), name="espera-del-mostrador", daemon=True,
    )
    hilo.start()
    hilo.join(SEGUNDOS_SIN_CARTEL)
    if hilo.is_alive():
        _hay_un_cartel_abierto = True
        try:
            # Sin ventana madre a propósito: la que está al frente puede estar por
            # borrarse (un deleteLater pendiente), y el cartel, su hijo, se borraría
            # con ella en medio de la espera. Es modal igual, para todo el programa.
            cartel = CartelEsperandoAlMostrador(hilo)
            cartel.exec()
            cartel.deleteLater()
        finally:
            _hay_un_cartel_abierto = False
        # Se mira el hilo y no cómo se cerró el cartel: si contestó justo cuando se
        # apretaba DEJAR DE ESPERAR, la respuesta está y vale.
        if hilo.is_alive():
            raise SeDejoDeEsperar("Se dejó de esperar la respuesta del mostrador.")
    return Respuesta(resultado).valor()


class CartelEsperandoAlMostrador(QDialog):
    """El cartel de cuando el mostrador tarda: se cierra solo cuando el hilo termina,
    y DEJAR DE ESPERAR, Esc o la cruz lo cierran antes. Al hilo no lo toca: solo
    mira si sigue vivo."""

    def __init__(self, hilo, parent=None):
        super().__init__(parent)
        self._hilo = hilo
        # Ya pasó la espera sin cartel: los segundos cuentan desde que salió el pedido.
        self._desde = time.monotonic() - SEGUNDOS_SIN_CARTEL
        self.setWindowTitle("FRKiosko - Esperando al mostrador")
        self.setModal(True)
        self._armar_interfaz()
        self._timer = QTimer(self)
        self._timer.setInterval(MILISEGUNDOS_ENTRE_VISTAS)
        self._timer.timeout.connect(self._revisar)
        self._timer.start()

    def _armar_interfaz(self):
        self.cabecera = cabecera_oscura("⏳", "Esperando al mostrador", self._texto_de_los_segundos())
        aclaracion = QLabel(
            "Lo que pediste ya salió para el FRKiosko del mostrador y todavía no contestó. "
            "Este cartel se cierra solo cuando llega la respuesta."
        )
        aclaracion.setWordWrap(True)
        self.boton_dejar = tecla("✕  DEJAR DE ESPERAR", self.reject)
        botones = QHBoxLayout()
        botones.addStretch()
        botones.addWidget(self.boton_dejar)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(self.cabecera)
        layout.addWidget(aclaracion)
        layout.addLayout(botones)
        self.setLayout(layout)
        self.setMinimumWidth(460)
        # Un Enter que venía apretado de la pantalla de atrás no deja de esperar.
        sin_boton_por_defecto(self)

    def _texto_de_los_segundos(self) -> str:
        return f"Van {int(time.monotonic() - self._desde)} segundos"

    def _revisar(self):
        # No se revisa en __init__: si el hilo ya terminó, accept() antes de exec()
        # dejaría el cartel abierto sin nadie que lo cierre.
        if not self._hilo.is_alive():
            self._timer.stop()
            self.accept()
            return
        self.cabecera.detalle.setText(self._texto_de_los_segundos())
