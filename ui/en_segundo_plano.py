"""
ui/en_segundo_plano.py
======================
Un botón que espera la red (la app de gastos, una carpeta de otra PC, un pendrive
lento) no congela el mostrador. Llamada directa desde la pantalla, esa espera traba
TODO el programa: la ventana no se puede mover ni cerrar, Windows la marca "No
responde", no corre ningún reloj (el titileo de Cierre de Turno, la revisión de la
caja) y no se vuelve a vender hasta que la red conteste. Y puede ser larga: un
pedido a Google encadena varios (renovar el token, entrar de nuevo, el PATCH), cada
uno con su propia espera, y una carpeta de otra PC apagada tarda segundos en
contestar.

Por eso la MISMA función del repo corre en un hilo aparte y un QTimer de la ventana
mira cada 100 ms si terminó, como la barra de ui/envio_pwa_progreso.py. Mientras
tanto las teclas que mandan algo quedan apagadas (Cerrar sigue andando), el cursor
ocupado se ve solo en esa ventana y otro clic no arranca otra vez. Al terminar, la
ventana recibe lo que devolvió la función, o su error, y lo muestra igual que si la
hubiera llamado ella. Si la ventana se cerró antes (el mostrador queda libre para
seguir vendiendo), no se muestra nada: lo que hizo el repo (un cierre mandado, una
copia hecha, una carpeta agregada) queda hecho igual.

Dos reglas que no hay que romper:
- El hilo recibe SOLO la función del repo, sus argumentos (datos: números y textos)
  y un dict donde deja el valor o el error. Nunca la ventana, un widget ni un método
  de la ventana: si un hilo suelta la última referencia a un objeto de Qt, Qt lo
  destruye desde ese hilo y el programa se puede cerrar sin ningún cartel (es la
  trampa del recolector, ver main.py). `arrancar` lo controla.
- El hilo es daemon, con threading.Thread y no un ThreadPoolExecutor (Python espera
  a esos hilos al salir): cerrar FRKiosko con un pedido colgado no espera a que
  Google o la otra PC contesten.
"""

import threading

from PySide6.QtCore import QObject, Qt, QTimer

MILISEGUNDOS_ENTRE_VISTAS = 100


def _correr(trabajo, argumentos: tuple, resultado: dict):
    """Lo único que corre en el hilo: la función del repo, y en `resultado` su valor
    ("valor") o el error que levantó ("error")."""
    try:
        resultado["valor"] = trabajo(*argumentos)
    except Exception as error:
        resultado["error"] = error
        # El error guarda este renglón (en su traceback) y este renglón guarda
        # `resultado`: soltándolo acá no queda un ciclo, que con el recolector
        # apagado (main.py) no se libera nunca.
        del resultado


def _lleva_un_objeto_de_qt(cosa) -> bool:
    """Un widget, el método de una ventana o una función que nombra a una (un lambda con self)."""
    if isinstance(cosa, QObject) or isinstance(getattr(cosa, "__self__", None), QObject):
        return True
    for celda in getattr(cosa, "__closure__", None) or ():
        try:
            if isinstance(celda.cell_contents, QObject):
                return True
        except ValueError:  # una celda todavía vacía
            pass
    return False


class Respuesta:
    """Lo que devolvió la función del repo en el hilo, o el error que levantó."""

    def __init__(self, resultado: dict):
        self._resultado = resultado

    def valor(self):
        """Lo que devolvió. Si levantó un error, lo levanta acá, en el hilo de la
        pantalla: con @manejar_errores sale el mismo cartel que con la llamada directa
        (y lo inesperado va al log con el renglón del repo donde falló)."""
        error = self._resultado.pop("error", None)
        if error is None:
            return self._resultado["valor"]
        try:
            raise error
        finally:
            error = None  # el mismo ciclo que en _correr, ahora con este renglón


class EnSegundoPlano(QObject):
    """
    La espera de un diálogo (`ventana`, un QDialog). `teclas` son las que se apagan
    mientras espera: las que mandan algo, nunca la de cerrar. Las que ya estaban
    apagadas quedan apagadas al terminar.
    """

    def __init__(self, ventana, teclas):
        super().__init__(ventana)  # vive y muere con la ventana; el hilo no la ve nunca
        self._teclas = list(teclas)
        self._apagadas = []
        self._hilo = None
        self._resultado = None
        self._al_terminar = None
        self._timer = QTimer(self)
        self._timer.setInterval(MILISEGUNDOS_ENTRE_VISTAS)
        self._timer.timeout.connect(self._revisar_si_termino)
        # Cerrar, la cruz y Esc pasan por `finished`. Hace falta porque el diálogo
        # sigue vivo, escondido, hasta que se cierra la ventana que lo abrió (es su
        # hijo): sin esto, la respuesta abriría un cartel sobre una ventana cerrada.
        ventana.finished.connect(self._olvidar)

    def esta_esperando(self) -> bool:
        return self._resultado is not None

    def arrancar(self, trabajo, *argumentos, al_terminar) -> bool:
        """
        Corre `trabajo(*argumentos)` en un hilo aparte y, al terminar, llama a
        `al_terminar(respuesta)` con una Respuesta: `respuesta.valor()` da lo que
        devolvió o levanta su error. Si ya hay una espera en curso no hace nada y
        devuelve False (un Enter o un segundo clic no mandan dos veces). TypeError si
        algo de lo que se le pasaría al hilo es de Qt.
        """
        if self.esta_esperando():
            return False
        if any(_lleva_un_objeto_de_qt(cosa) for cosa in (trabajo, *argumentos)):
            raise TypeError("A un hilo no se le pasa nada de Qt: solo la función del repo y datos.")
        self._resultado = {}
        self._al_terminar = al_terminar
        self._apagadas = [tecla for tecla in self._teclas if tecla.isEnabled()]
        for tecla in self._apagadas:
            tecla.setEnabled(False)
        # Solo en esta ventana: un reloj de arena de todo el programa quedaría puesto
        # si se la cierra antes de que conteste.
        self.parent().setCursor(Qt.BusyCursor)
        self._hilo = threading.Thread(
            target=_correr, args=(trabajo, argumentos, self._resultado), name="espera-de-una-pantalla",
            daemon=True,
        )
        self._hilo.start()
        self._timer.start()
        return True

    def _revisar_si_termino(self):
        # is_alive y no el dict: cuando da False, el hilo ya soltó todo lo que tenía.
        if not self.esta_esperando() or self._hilo.is_alive():
            return
        resultado, al_terminar = self._resultado, self._al_terminar
        self._dejar_de_esperar()
        al_terminar(Respuesta(resultado))

    def _olvidar(self):
        """La ventana se cerró mientras esperaba: lo que conteste el hilo no se muestra."""
        if self.esta_esperando():
            self._dejar_de_esperar()

    def _dejar_de_esperar(self):
        self._timer.stop()
        self._resultado = None
        self._al_terminar = None
        for tecla in self._apagadas:
            tecla.setEnabled(True)
        self._apagadas = []
        self.parent().unsetCursor()
