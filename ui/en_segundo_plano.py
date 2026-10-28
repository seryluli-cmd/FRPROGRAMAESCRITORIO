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
copia hecha) queda hecho igual, y un error inesperado va igual a data_fr/errores.log.

Tres reglas que no hay que romper:
- El hilo recibe SOLO la función del repo, sus argumentos (datos: números y textos)
  y un dict donde deja el valor o el error. Nunca la ventana, un widget ni un método
  de la ventana. Un objeto de Qt es del hilo de la pantalla: si el hilo de la espera
  se queda con la última referencia (la ventana se cerró y se soltó mientras
  esperaba), al terminar Python lo destruye desde ese otro hilo, y Qt deja el objeto
  C++ roto (lo mismo que hacía el recolector desde cualquier hilo, ver main.py).
  `arrancar` rechaza los casos comunes (ver _lleva_un_objeto_de_qt), no todos: la
  regla es de quien lo llama.
- El error que vuelve del hilo no deja ciclos de referencias: con el recolector
  apagado (main.py) un ciclo no se libera nunca. Ver _correr y Respuesta.valor.
- El hilo es daemon, con threading.Thread y no un ThreadPoolExecutor (Python espera
  a esos hilos al salir): cerrar FRKiosko con un pedido colgado no espera a que
  Google o la otra PC contesten.
"""

import functools
import threading

from PySide6.QtCore import QObject, Qt, QTimer

from errores import registrar_error

MILISEGUNDOS_ENTRE_VISTAS = 100
# Los rechazos del repo, con su mensaje listo para el cartel: los mismos que
# @manejar_errores muestra sin anotarlos en el log.
_RECHAZOS_DEL_REPO = (ValueError, PermissionError)
# Hasta dónde se mira adentro de un partial, una lista o un lambda buscando Qt.
_HONDURA_MAXIMA = 4


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


def _lleva_un_objeto_de_qt(cosa, hondura: int = 0) -> bool:
    """Los casos comunes de pasarle Qt a un hilo sin querer: un widget, el método de
    una ventana, una función que nombra a una (un lambda con self), un partial de
    cualquiera de esos y un widget dentro de una lista, tupla o dict. No ve un widget
    guardado como atributo de un objeto propio."""
    if hondura > _HONDURA_MAXIMA:
        return False
    if isinstance(cosa, QObject) or isinstance(getattr(cosa, "__self__", None), QObject):
        return True
    if isinstance(cosa, functools.partial):
        adentro = [cosa.func, *cosa.args, *cosa.keywords.values()]
    elif isinstance(cosa, dict):
        adentro = [*cosa.keys(), *cosa.values()]
    elif isinstance(cosa, (list, tuple, set, frozenset)):
        adentro = list(cosa)
    else:
        adentro = []
        for celda in getattr(cosa, "__closure__", None) or ():
            try:
                adentro.append(celda.cell_contents)
            except ValueError:  # una celda todavía vacía
                pass
    return any(_lleva_un_objeto_de_qt(otra, hondura + 1) for otra in adentro)


def _anotar_si_fallo(resultado: dict):
    """Terminó la espera de una ventana que ya se cerró: nadie va a mostrar su error.
    Un rechazo del repo era solo para el cartel; uno inesperado va a errores.log,
    como lo anota @manejar_errores con la ventana abierta (un disco lleno en una
    copia no queda anotado en ningún otro lado)."""
    error = resultado.pop("error", None)
    if error is not None and not isinstance(error, _RECHAZOS_DEL_REPO):
        registrar_error(error, "Lo corría una pantalla en un hilo aparte y se cerró antes de que terminara.")


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
        # [(hilo, resultado)] de las esperas de cuando la ventana se cerró antes de
        # que contestaran: no se muestran, pero se siguen mirando para anotar un
        # error inesperado.
        self._sin_ventana = []
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
        en lo que se le pasaría al hilo se ve algo de Qt.
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
        for espera in [espera for espera in self._sin_ventana if not espera[0].is_alive()]:
            self._sin_ventana.remove(espera)
            _anotar_si_fallo(espera[1])
        if self.esta_esperando() and not self._hilo.is_alive():
            resultado, al_terminar = self._resultado, self._al_terminar
            self._dejar_de_esperar()
            al_terminar(Respuesta(resultado))
        self._parar_si_no_queda_nada()

    def _olvidar(self):
        """La ventana se cerró mientras esperaba: lo que conteste el hilo no se muestra."""
        if self.esta_esperando():
            self._sin_ventana.append((self._hilo, self._resultado))
            self._dejar_de_esperar()

    def _dejar_de_esperar(self):
        self._resultado = None
        self._al_terminar = None
        for tecla in self._apagadas:
            tecla.setEnabled(True)
        self._apagadas = []
        self.parent().unsetCursor()
        self._parar_si_no_queda_nada()

    def _parar_si_no_queda_nada(self):
        if not self.esta_esperando() and not self._sin_ventana:
            self._timer.stop()
