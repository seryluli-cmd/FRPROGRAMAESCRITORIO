"""
login_window.py
=================
Pantalla de login con el diseño "Elegí tu Jugador" (la maqueta C que eligió el
dueño el 2026-10-30): cada usuario es una ficha con un círculo de color y sus
iniciales, y se elige tocándola o con las flechas (en vez de tipear el nombre,
para evitar errores de tipeo y que sea cómodo con pantalla táctil). Enter pasa a
la "Clave"; si coinciden, abre la ventana principal con los permisos que
correspondan según el rol (ADMIN o EMPLEADA).

Los dibujos (el fondo animado, el nombre en degradado y las fichas) están en
ui/login_dibujos.py. Los colores de las etiquetas, la clave y ENTRAR van por
objectName en ui/hoja_de_estilos.py, no en una hoja local: los avisos
(mostrar_error) y la caja que se abre al entrar son hijos de esta ventana, y una
hoja local les pasaría el fondo oscuro.
"""

import time
from pathlib import Path

from PySide6.QtWidgets import QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt, QElapsedTimer, QTimer
from PySide6.QtGui import QPainter, QPixmap, QFont

import dominio
from admin_remoto import modo as modo_remoto
from database import verificar_clave
# El módulo y no las funciones sueltas: en la copia para administrar desde otra
# PC, admin_remoto/cliente.py las cambia por las que le preguntan al mostrador.
from repositories import usuarios_repo
from ui.login_dibujos import AZUL, CIAN, VIOLETA, FichasDeJugadores, FondoDelIngreso, TextoDegradado, brillo, letra
from ui.utils import mostrar_error, mostrar_aviso, manejar_errores, encadenar_enter

# Mismo ícono que usa main.py para las ventanas (carpeta assets, junto al código).
RUTA_ICONO_PNG = Path(__file__).resolve().parent.parent / "assets" / "icono.png"

ANCHO, ALTO = 960, 600
# Unos 30 cuadros por segundo: las rayas se corren 2 px por cuadro y se ven
# parejas. La animación corre solo con la pantalla a la vista (showEvent/hideEvent).
MILISEGUNDOS_POR_CUADRO = 33

# Protección simple contra prueba y error de claves: después de
# MAX_INTENTOS fallidos seguidos con el mismo nombre, se bloquea ese
# nombre por BLOQUEO_SEGUNDOS antes de dejar reintentar. Es un
# diccionario a nivel de módulo (no de instancia) para que el conteo
# sobreviva a un "cerrar sesión" y no se resetee volviendo a abrir la
# pantalla de Login dentro de la misma ejecución del programa.
MAX_INTENTOS = 5
BLOQUEO_SEGUNDOS = 60
_intentos_fallidos = {}  # nombre (en minúsculas) -> (cantidad_seguidos, bloqueado_hasta)


class LoginWindow(QWidget):
    def __init__(self, al_loguearse):
        """
        `al_loguearse` es una función que este cuadro llama apenas el
        login es correcto, pasándole la fila del usuario logueado. La
        usa main.py para abrir la ventana principal.
        """
        super().__init__()
        self._al_loguearse = al_loguearse
        self._fondo = FondoDelIngreso(ANCHO, ALTO)
        self._segundos = 0.0
        self._reloj = QElapsedTimer()
        self._reloj.start()
        self._animacion = QTimer(self)
        self._animacion.setInterval(MILISEGUNDOS_POR_CUADRO)
        self._animacion.timeout.connect(self._siguiente_cuadro)
        self._armar_interfaz()

    def _armar_interfaz(self):
        self.setWindowTitle("FRKiosko - Ingreso")
        self.setFixedSize(ANCHO, ALTO)

        # Arriba, el ícono real del programa (el carrito, assets/icono.png) y el
        # nombre en degradado. Si el ícono no estuviera, el nombre queda solo, al medio.
        cabecera = QHBoxLayout()
        cabecera.addStretch()
        imagen = QPixmap(str(RUTA_ICONO_PNG))
        if not imagen.isNull():
            escala = self.devicePixelRatioF()
            imagen = imagen.scaled(round(52 * escala), round(52 * escala), Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
            imagen.setDevicePixelRatio(escala)
            icono = QLabel()
            icono.setPixmap(imagen)
            brillo(icono, AZUL, 30, 180)
            cabecera.addWidget(icono)
            cabecera.addSpacing(10)
        titulo = TextoDegradado("FRKiosko", letra("Bahnschrift", 34, QFont.Bold, 1), [CIAN, AZUL, VIOLETA])
        brillo(titulo, AZUL, 26, 140)
        cabecera.addWidget(titulo)
        cabecera.addStretch()

        subtitulo = QLabel("ELEGÍ TU JUGADOR")
        subtitulo.setObjectName("subtituloIngreso")
        subtitulo.setAlignment(Qt.AlignCenter)

        # Las fichas se arman de nuevo cada vez que se abre esta pantalla (con
        # listar_usuarios(), sin incluir inactivos) para reflejar altas/bajas
        # recientes de Usuarios sin tener que reiniciar el programa. Se ordena acá
        # con Python (dominio.sin_acentos), no con el ORDER BY del repo: en SQLite el
        # orden por defecto es por valor de byte, así que "admin" (minúscula)
        # quedaría después de cualquier nombre en mayúscula, y "Ángela" después de
        # "Zulma", en vez de intercalarse alfabéticamente de verdad. Se sigue
        # llamando combo_nombre: era la lista desplegable, las fichas tienen lo que
        # se usaba de ella y así la buscan las pruebas.
        usuarios_ordenados = sorted(usuarios_repo.listar_usuarios(), key=lambda u: dominio.sin_acentos(u["nombre"]))
        self.combo_nombre = FichasDeJugadores([usuario["nombre"] for usuario in usuarios_ordenados])
        self.combo_nombre.currentIndexChanged.connect(self._saludar)
        # Tocar una ficha la elige y deja todo listo para escribir la clave.
        self.combo_nombre.tocada.connect(self._pasar_a_la_clave)

        self.saludo = QLabel()
        self.saludo.setObjectName("saludoIngreso")
        self.saludo.setAlignment(Qt.AlignCenter)
        self._saludar()

        self.campo_clave = QLineEdit()
        self.campo_clave.setObjectName("claveIngreso")
        self.campo_clave.setEchoMode(QLineEdit.Password)
        # Al apretar Enter en la clave, intenta entrar directamente (más
        # rápido para el uso diario que tener que hacer clic siempre).
        self.campo_clave.returnPressed.connect(self._intentar_ingresar)
        # Enter en las fichas pasa a la clave, como Tab.
        encadenar_enter(self.combo_nombre, self.campo_clave)

        boton_entrar = QPushButton("ENTRAR")
        boton_entrar.setObjectName("botonEntrar")
        boton_entrar.setCursor(Qt.PointingHandCursor)
        boton_entrar.clicked.connect(self._intentar_ingresar)
        brillo(boton_entrar, VIOLETA, 32, 170)

        fila_clave = QHBoxLayout()
        fila_clave.setSpacing(12)
        fila_clave.addStretch()
        self.campo_clave.setFixedWidth(260)
        fila_clave.addWidget(self.campo_clave)
        fila_clave.addWidget(boton_entrar)
        fila_clave.addStretch()

        ayuda = QLabel("←  →  para elegir     ·     Enter para seguir     ·     o tocá tu ficha")
        ayuda.setObjectName("ayudaIngreso")
        ayuda.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 40, 0, 30)
        layout.setSpacing(0)
        layout.addLayout(cabecera)
        layout.addSpacing(10)
        layout.addWidget(subtitulo)
        layout.addWidget(self.combo_nombre, 1)
        layout.addWidget(self.saludo)
        layout.addSpacing(12)
        layout.addLayout(fila_clave)
        if modo_remoto.es_copia_remota():
            # Va en el hueco de arriba de la ayuda: así las fichas no pierden lugar.
            aviso = QLabel(
                f"Desde otra PC · mostrador: {modo_remoto.mostrador_en_uso()} · Entra solo un Administrador."
            )
            aviso.setObjectName("avisoIngreso")
            aviso.setAlignment(Qt.AlignCenter)
            aviso.setWordWrap(True)
            layout.addSpacing(12)
            layout.addWidget(aviso)
            layout.addSpacing(18)
        else:
            layout.addSpacing(50)
        layout.addWidget(ayuda)

        self.combo_nombre.setFocus()

    # ------------------------------------------------ la animación
    def showEvent(self, evento):
        super().showEvent(evento)
        self._animacion.start()

    def hideEvent(self, evento):
        # Cerrada al entrar al programa, no gasta nada dibujando lo que nadie ve.
        self._animacion.stop()
        super().hideEvent(evento)

    def _siguiente_cuadro(self):
        self._segundos = self._reloj.elapsed() / 1000
        self.combo_nombre.momento = self._segundos
        self.update()

    def paintEvent(self, _evento):
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing)
        self._fondo.pintar(pintor, self._segundos)
        pintor.end()

    # ------------------------------------------------ elegir y entrar
    def _saludar(self, _indice=None):
        nombre = self.combo_nombre.currentText()
        if nombre:
            self.saludo.setText(f"Hola, {nombre}. Ingresá tu clave")
        else:
            self.saludo.setText("Todavía no hay ningún usuario cargado")

    def _pasar_a_la_clave(self, _indice=None):
        self.campo_clave.setFocus()

    @manejar_errores
    def _intentar_ingresar(self):
        if self.combo_nombre.count() == 0:
            mostrar_error(self, "No hay usuarios", "Todavía no hay ningún usuario cargado en el sistema.")
            return

        nombre = self.combo_nombre.currentText().strip()
        clave = self.campo_clave.text()

        if not clave:
            mostrar_error(self, "Falta la clave", "Ingresá tu clave.")
            return

        # Clave del diccionario de intentos fallidos: en minúsculas, para
        # que "Matias" y "matias" compartan el mismo contador (autenticar_por_nombre
        # tampoco distingue mayúsculas al buscar).
        clave_intentos = nombre.lower()

        intentos, bloqueado_hasta = _intentos_fallidos.get(clave_intentos, (0, 0.0))
        ahora = time.monotonic()
        if bloqueado_hasta > ahora:
            segundos_restantes = int(bloqueado_hasta - ahora) + 1
            mostrar_error(
                self, "Demasiados intentos",
                f"Se bloqueó este usuario {segundos_restantes} segundos por varias claves "
                "incorrectas seguidas. Esperá un momento y volvé a intentar."
            )
            self.campo_clave.clear()
            return

        usuario = usuarios_repo.autenticar_por_nombre(nombre, clave)
        if usuario is None:
            intentos += 1
            if intentos >= MAX_INTENTOS:
                _intentos_fallidos[clave_intentos] = (0, ahora + BLOQUEO_SEGUNDOS)
                mostrar_error(
                    self, "Demasiados intentos",
                    f"Usuario bloqueado por {BLOQUEO_SEGUNDOS} segundos por reiteradas claves incorrectas."
                )
            else:
                _intentos_fallidos[clave_intentos] = (intentos, 0.0)
                mostrar_error(self, "Datos incorrectos", "Nombre o clave incorrectos.")
            self.campo_clave.clear()
            self.campo_clave.setFocus()
            return

        _intentos_fallidos.pop(clave_intentos, None)
        self.campo_clave.clear()

        # Aviso suave si el Admin todavía tiene la clave por defecto
        # ("1234") con la que se crea el primer usuario del sistema —
        # no bloquea el ingreso, solo recuerda cambiarla.
        if dominio.es_admin(usuario) and verificar_clave("1234", usuario["clave_hash"]):
            mostrar_aviso(
                self, "Cambiá la clave por defecto",
                "Este usuario Admin todavía tiene la clave de fábrica (1234).\n"
                "Te recomendamos cambiarla desde 'Usuarios' apenas puedas."
            )

        self._al_loguearse(usuario)
