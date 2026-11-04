"""Ventana principal del kiosko: ventas, impresiones, caja y administración.

La copia para administrar desde otra PC conserva las mismas pantallas de
consulta y gestión. Los cobros y el cierre de turno se hacen en el mostrador.
"""

import threading

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
)
from PySide6.QtCore import Qt, QTimer

import dominio
from admin_remoto import modo as modo_remoto
from errores import registrar_error
from repositories import impresiones_repo, relevo_repo, usuarios_repo
from turnos import MINUTOS_PARA_CIERRE_FORZOSO
from ui.acomodar_caja_window import DialogoAcomodarCaja
from ui.administrar_kiosko_window import AdministrarKioskoWindow
from ui.configuracion_admin_window import ConfiguracionAdminWindow
from ui.gestion_impresiones_window import VentanaGestionImpresiones
from ui.impresiones_window import DialogoImpresiones
from ui.pedidos_clientes_window import VentanaPedidosClientes
from ui.ranking_rotacion_window import VentanaRankingRotacion
from ui.aviso_tarea import RevisorDeTareas
from ui.tareas_turno_window import VentanaTareasTurno
from ui.ventas_window import VentasWindow
from ui.caja_window import CajaWindow, CierreTurnoWindow
from ui.usuarios_window import DialogoCambiarClave
from ui.ingreso_caja import mensaje_del_sobre
from ui.lista_compras_window import VentanaListaDeCompras
from ui.vuelta_del_admin import VueltaDelAdmin
from ui.en_segundo_plano import MILISEGUNDOS_ENTRE_VISTAS, Respuesta, _correr
# La foto de fondo vive en su archivo desde el 2026-11-03; se sigue pidiendo de acá.
from ui.fondo_del_inicio import COLOR_SIN_FONDO, RUTA_FONDO_INICIO, FondoDelInicio  # noqa: F401
from ui.piezas_ventana import restringir
from ui.utils import (
    aplicar_clase, avisar_acceso_restringido, icono_de_emoji, mostrar_error, mostrar_info, solo_en_el_mostrador,
)

# Cada cuánto se mira cómo está la caja (si tiene que titilar el botón, o si ya
# toca el cierre forzoso). Es una consulta chica, con su índice.
INTERVALO_REVISION_CAJA_MS = 10_000
# Cada cuánto cambia de color el botón Cierre de Turno mientras titila.
INTERVALO_PARPADEO_MS = 600
# El dibujito del botón Operador (lo eligió el dueño entre cinco, 2026-10-24) y cuánto más grande
# va que los de los otros botones de la barra.
DIBUJITO_OPERADOR = "🔄"
AGRANDAR_DIBUJITO_OPERADOR = 1.25
# Alto de los botones de la barra de arriba: 38 hasta el 2026-11-02, cuando el dueño
# pidió los botones y su letra un 10% más grandes (la letra y el relleno, en la hoja de
# estilos). Con eso la barra mide ~1410 px de ancho: en una pantalla de 1366 ya no entra.
ALTO_BOTON_BARRA = 42
SEPARACION_BOTONES_BARRA = 7
# Los accesos de la pantalla de inicio (Venta de Mercadería, Impresiones, Caja,
# Gestión Impresiones, Pedidos de Clientes, Tareas del Turno y Ranking de
# Rotación): todos del mismo tamaño, uno debajo del otro a la izquierda (pedido del
# dueño, 2026-11-02, con un dibujo: antes eran tres botones que ocupaban toda la
# fila; Gestión Impresiones se sumó el mismo día, Pedidos de Clientes y Tareas del
# Turno el 2026-11-03 y Ranking de Rotación el 2026-11-04). Medían 110 de alto con
# 20 entre uno y otro; con el sexto pasaron a 98 y 14, y con el séptimo a 86 y 10,
# para que el inicio siga entrando en la pantalla de 1920 x 1080 del mostrador
# (lo cuida tests/test_estilo_ui.py).
ANCHO_ACCESO = 240
ALTO_ACCESO = 86
SEPARACION_ACCESOS = 10
TAMANO_DIBUJITO_ACCESO = 34
# El numerito amarillo de la esquina de un acceso (cuántas tareas del turno están
# atrasadas): alto y lo que lo separa del borde.
ALTO_INSIGNIA = 26
MARGEN_INSIGNIA = 8
# Lo que separa el panel del título y los accesos del borde de la foto.
MARGEN_DEL_PANEL = 16


class MainWindow(QMainWindow):
    """Accesos del kiosko, con permisos y estado de la caja."""

    def __init__(self, usuario, al_cerrar_sesion, volver_a=None, al_volver_a=None):
        """
        `usuario` es la fila del usuario logueado (con su rol).
        `al_cerrar_sesion` es una función que se llama al elegir
        "🔄 Operador", para volver a la pantalla de login.
        Solo para el Administrador en el mostrador (pedido del dueño, 2026-10-26):
        `volver_a` es el id de quien dejó el mostrador con "🔄 Operador" antes de
        que él entrara (o None) y `al_volver_a(fila)` abre su sesión. A los
        dominio.MINUTOS_ADMIN_VUELVE_SOLO la sesión vuelve sola a ella, o al
        ingreso si no se puede (ver ui/vuelta_del_admin.py).
        """
        super().__init__()
        self.usuario = usuario
        self.es_admin = dominio.es_admin(usuario)
        self._volver_a = volver_a
        self._al_volver_a = al_volver_a
        # A quién volvería el Administrador que entre después de esta sesión: lo
        # completa "🔄 Operador" (_cambiar_operador) y lo lee main.Aplicacion. Un
        # Cierre de Turno o el cierre forzoso lo dejan en None: esa caja ya no está.
        self.a_quien_volveria = None
        # "Encargado" no es un rol propio en la base — es un Admin, o una
        # Empleada con al menos uno de los permisos de administración de
        # usuarios_repo.PERMISOS_EMPLEADA. Decide si el botón "Administrar
        # Kiosko" abre algo (se ve siempre).
        self._es_encargado = self.es_admin or any(
            usuarios_repo.tiene_permiso(usuario, clave_permiso)
            for clave_permiso, _ in usuarios_repo.PERMISOS_EMPLEADA
        )
        self._al_cerrar_sesion = al_cerrar_sesion
        self._remota = modo_remoto.es_copia_remota()
        self._titilar = False
        self._encendido = False
        # Las tareas del turno que llegaron a su hora sin hacerse: el acceso TAREAS DEL
        # TURNO titila en rojo y muestra cuántas son (ver _poner_tareas_atrasadas).
        self._tareas_atrasadas = 0
        self._encendido_tareas = False
        self._armar_interfaz()
        if self._remota:
            self._mostrar_la_caja_del_mostrador()
        else:
            self._actualizar_estado_de_la_caja()
        self._timer_caja = QTimer(self)
        self._timer_caja.setInterval(INTERVALO_REVISION_CAJA_MS)
        self._timer_caja.timeout.connect(self._revisar_la_caja)
        self._timer_caja.start()
        self._timer_parpadeo = QTimer(self)
        self._timer_parpadeo.setInterval(INTERVALO_PARPADEO_MS)
        self._timer_parpadeo.timeout.connect(self._parpadear)
        self._timer_parpadeo.start()
        # Desde otra PC, la pregunta de cada revisión va en un hilo aparte (ver
        # _preguntar_la_caja_al_mostrador): (hilo, resultado) mientras no contesta.
        self._pregunta_de_la_caja = None
        self._timer_respuesta_caja = QTimer(self)
        self._timer_respuesta_caja.setInterval(MILISEGUNDOS_ENTRE_VISTAS)
        self._timer_respuesta_caja.timeout.connect(self._ver_si_contesto_la_caja)
        # Desde otra PC no: ahí no hay una empleada a la que volver.
        self._vuelta = None
        if self.es_admin and not self._remota:
            self._vuelta = VueltaDelAdmin(self, volver_a, self._volver_sola, self._hay_un_cobro_a_medias)
        # El aviso de las tareas del turno sale solo en el mostrador (ver ui/aviso_tarea.py).
        self._tareas = None
        if not self._remota:
            self._tareas = RevisorDeTareas(self, usuario, self._poner_tareas_atrasadas)

    def _armar_interfaz(self):
        if self._remota:
            self.setWindowTitle(
                f"FRKiosko - {self.usuario['nombre']} - desde otra PC (mostrador: {modo_remoto.mostrador_en_uso()})"
            )
        else:
            self.setWindowTitle(f"FRKiosko - {self.usuario['nombre']} ({self.usuario['rol']})")
        self.resize(980, 680)

        # Barra oscura "#encabezadoInicio" (estilo en la hoja de estilos
        # global de main.py), en dos renglones (pedido del dueño, 2026-10-18: en
        # la pantalla del mostrador, de 1366 de ancho, todo en una sola fila no
        # entraba y se cortaban los textos): arriba quién está y la caja, abajo
        # los botones, empezando por Vender desde la izquierda.
        barra = QFrame()
        barra.setObjectName("encabezadoInicio")
        layout_barra = QVBoxLayout()
        layout_barra.setContentsMargins(16, 10, 16, 10)
        layout_barra.setSpacing(8)

        # Pedido del dueño (2026-10-16): el nombre de quien está en el mostrador
        # como "Operador: TOBY", sin saludo y sin la palabra "EMPLEADA" (el rol
        # por dentro sigue siendo EMPLEADA). El Admin se sigue distinguiendo.
        cargo = "Administrador" if self.es_admin else "Operador"
        # Letra clara sobre la barra oscura: "#nombreEncabezado" y "#cajaEncabezado"
        # en ui/hoja_de_estilos.py.
        titulo = QLabel(f"{cargo}: {self.usuario['nombre']}")
        titulo.setObjectName("nombreEncabezado")
        # La caja abierta, al lado del nombre: "Caja Nº 12 · Mañana" (ver
        # _actualizar_estado_de_la_caja).
        self.etiqueta_caja = QLabel()
        self.etiqueta_caja.setObjectName("cajaEncabezado")
        self.etiqueta_caja.hide()
        renglon_nombre = QHBoxLayout()
        renglon_nombre.setSpacing(10)
        renglon_nombre.addWidget(titulo)
        renglon_nombre.addWidget(self.etiqueta_caja)
        renglon_nombre.addStretch()
        layout_barra.addLayout(renglon_nombre)

        botones = QHBoxLayout()
        botones.setSpacing(SEPARACION_BOTONES_BARRA)
        layout_barra.addLayout(botones)
        self._armar_botones_de_la_barra(botones)
        barra.setLayout(layout_barra)

        contenedor = FondoDelInicio()
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        layout.addWidget(barra)

        inicio = QFrame()
        inicio.setObjectName("inicioKiosko")
        lugar_del_panel = QVBoxLayout(inicio)
        lugar_del_panel.setContentsMargins(MARGEN_DEL_PANEL, MARGEN_DEL_PANEL, MARGEN_DEL_PANEL, MARGEN_DEL_PANEL)
        # El título y los accesos van en un panel oscuro medio transparente, como los
        # cuadros de vidrio de la foto de fondo: sueltos sobre la foto, el título caía
        # encima de los paquetes del estante y no se leía. El panel mide lo que su
        # contenido (no toda la pantalla) y queda arriba a la izquierda.
        panel = QFrame()
        panel.setObjectName("panelInicio")
        lugar_del_panel.addWidget(panel, 0, Qt.AlignLeft | Qt.AlignTop)
        columna_inicio = QVBoxLayout(panel)
        columna_inicio.setContentsMargins(24, 20, 24, 24)
        columna_inicio.setSpacing(12)
        # Letra clara sobre la foto de fondo: "#tituloInicio" y "#detalleInicio" en
        # ui/hoja_de_estilos.py.
        titulo_inicio = QLabel("KIOSKO")
        titulo_inicio.setObjectName("tituloInicio")
        columna_inicio.addWidget(titulo_inicio)
        descripcion = QLabel("Venta de mercadería, impresiones y control de caja")
        descripcion.setObjectName("detalleInicio")
        columna_inicio.addWidget(descripcion)
        columna_inicio.addSpacing(16)
        accesos = QVBoxLayout()
        accesos.setSpacing(SEPARACION_ACCESOS)
        por_nombre = {}
        for dibujito, texto, accion in (
            ("🛒", "VENTA DE MERCADERÍA", self._abrir_ventas),
            ("🖨️", "IMPRESIONES", self._abrir_impresiones),
            ("💵", "CAJA", self._abrir_caja),
            ("📑", "GESTIÓN IMPRESIONES", self._abrir_gestion_impresiones),
            ("🙋", "PEDIDOS DE CLIENTES", self._abrir_pedidos_clientes),
            ("⏰", "TAREAS DEL TURNO", self._abrir_tareas_turno),
            ("📈", "RANKING DE ROTACIÓN", self._abrir_ranking_rotacion),
        ):
            por_nombre[texto] = self._acceso_de_inicio(dibujito, texto, accion)
            # Sin AlignLeft, un botón de tamaño fijo queda centrado en la fila.
            accesos.addWidget(por_nombre[texto], 0, Qt.AlignLeft)
        # Titila y lleva el numerito de las atrasadas. Se busca por el nombre: hasta
        # el 2026-11-04 era el último de la lista, y ya no lo es.
        self.acceso_tareas = por_nombre["TAREAS DEL TURNO"]
        columna_inicio.addLayout(accesos)
        layout.addWidget(inicio, 1)
        contenedor.setLayout(layout)
        self.setCentralWidget(contenedor)

    def _acceso_de_inicio(self, dibujito, texto, funcion):
        """Uno de los accesos de la pantalla de inicio: botón azul de tamaño fijo
        con el dibujito arriba y el nombre abajo. Van como etiquetas adentro del botón (y
        no como ícono + texto) porque cada emoji recortado mide distinto: con el ícono, el
        nombre quedaba a otra altura en cada botón. Colores en ui/hoja_de_estilos.py
        (#accesoInicio); el nombre queda en accessibleName()."""
        boton = QPushButton()
        boton.setObjectName("accesoInicio")
        boton.setAccessibleName(texto)
        boton.setFixedSize(ANCHO_ACCESO, ALTO_ACCESO)
        capa = QVBoxLayout(boton)
        capa.setContentsMargins(8, 8, 8, 8)
        capa.setSpacing(6)
        icono, tamano = icono_de_emoji(dibujito, TAMANO_DIBUJITO_ACCESO)
        dibujo = QLabel()
        dibujo.setPixmap(icono.pixmap(tamano))
        dibujo.setFixedHeight(round(TAMANO_DIBUJITO_ACCESO * 1.2))
        dibujo.setAlignment(Qt.AlignCenter)
        nombre = QLabel(texto)
        nombre.setObjectName("nombreAcceso")
        nombre.setAlignment(Qt.AlignCenter)
        capa.addStretch()
        # El numerito de la esquina (hoy lo usa solo Tareas del Turno): fuera del
        # layout, encima del botón, y escondido mientras no haya nada que contar.
        boton.insignia = QLabel(boton)
        boton.insignia.setObjectName("insigniaAcceso")
        boton.insignia.setAlignment(Qt.AlignCenter)
        boton.insignia.setFixedHeight(ALTO_INSIGNIA)
        boton.insignia.hide()
        for etiqueta in (dibujo, nombre, boton.insignia):
            # El clic tiene que llegarle al botón, no a la etiqueta que tiene encima.
            etiqueta.setAttribute(Qt.WA_TransparentForMouseEvents)
        for etiqueta in (dibujo, nombre):
            capa.addWidget(etiqueta)
        capa.addStretch()
        boton.clicked.connect(funcion)
        return boton

    def _armar_botones_de_la_barra(self, layout_barra):
        """El renglón de botones, de izquierda a derecha empezando por Vender y
        terminando en "🔑 Cambiar Pass", a la derecha de "🔄 Operador" (pedido del
        dueño, 2026-11-04: se llamaba "Clave" e iba antes de Lista de Compras).
        Operador va pegado a Lista de Compras desde el 2026-10-23: hasta ese día iba
        solo en la punta derecha y, con la pantalla de 1920 del mostrador, quedaba
        lejos de todo. Se llamaba
        "Cerrar sesión": el dueño pidió que diga lo que hace de verdad, volver
        al ingreso para que entre otro operador. Primero fue "Camb Operador"; el
        2026-10-24 pasó a las flechas en círculo + "Operador" (el dueño eligió
        🔄 entre cinco dibujitos).

        Desde otra PC van los mismos botones (pedido del dueño, 2026-10-24): los
        que venden, cobran o cierran el turno avisan que eso se hace en el
        mostrador (ver los `_abrir_...` con `solo_en_el_mostrador`)."""
        self._agregar_boton_barra(layout_barra, "🛒  Vender", self._abrir_ventas, clase="primario")
        # Cobro rápido de impresiones, sin entrar a Vender.
        self._agregar_boton_barra(layout_barra, "🖨️  Impresiones", self._abrir_impresiones)
        # Nombres cortos en la barra (pedido del dueño, 2026-10-18); las ventanas
        # que abren siguen con su nombre entero.
        self._agregar_boton_barra(
            layout_barra, "🛠️  Admin Kiosko", self._abrir_administrar_kiosko, habilitado=self._es_encargado
        )
        self._agregar_boton_barra(
            layout_barra, "⚙️  Config ADMIN", self._abrir_configuracion_admin, habilitado=self.es_admin,
        )
        self._agregar_boton_barra(layout_barra, "💵  Caja", self._abrir_caja)
        self.boton_cierre_turno = self._agregar_boton_barra(layout_barra, "🧾  Cierre de Turno", self._abrir_cierre_turno)
        # Para cualquiera (pedido del dueño, 2026-10-31).
        self._agregar_boton_barra(layout_barra, "📝  Lista de Compras", self._abrir_lista_de_compras)
        # Tres espacios entre el dibujito y el texto: uno más que en los otros botones (pedido del dueño).
        boton_operador = self._agregar_boton_barra(layout_barra, "   Operador", self._cambiar_operador, clase="peligro")
        # Su dibujito va un 25% más grande que los de los otros botones (pedido del dueño,
        # 2026-10-24): uno dentro del texto mide lo que la letra, así que este va como ícono.
        boton_operador.ensurePolished()
        icono, tamano = icono_de_emoji(DIBUJITO_OPERADOR, boton_operador.fontInfo().pixelSize() * AGRANDAR_DIBUJITO_OPERADOR)
        boton_operador.setIcon(icono)
        boton_operador.setIconSize(tamano)
        # A la derecha de Operador, el último (pedido del dueño, 2026-11-04).
        self._agregar_boton_barra(layout_barra, "🔑  Cambiar Pass", self._abrir_cambiar_clave)
        # Para pasar del programa anterior a mitad de turno (pedido del dueño,
        # 2026-11-04: "es por esta vez nomás"; pidió que se llame "Ordenar $"). Solo el
        # Admin; los demás lo ven igual.
        self._agregar_boton_barra(
            layout_barra, "🧮  Ordenar $", self._abrir_acomodar_caja, habilitado=self.es_admin,
        )
        layout_barra.addStretch()

    def _agregar_boton_barra(self, layout, texto, funcion, clase=None, habilitado=True):
        """Botón de la barra superior: alto fijo, ancho según el texto
        (van en fila, así que no hace falta que midan todos igual).

        Todos ven todos los botones (pedido del dueño, 2026-10-19: con solo los
        suyos la barra de una empleada quedaba muy vacía). Uno sin `habilitado`
        se ve igual que los demás y al apretarlo dice "Acceso Restringido"
        (`restringir`, pedido del dueño, 2026-11-04; antes no hacía nada): no se
        lo apaga con setEnabled(False) porque se vería gris, distinto del resto.

        El texto va en mayúscula (y en negrita, por ui/hoja_de_estilos.py),
        pedido del dueño 2026-10-22; acá y no en la hoja porque Qt no tiene
        text-transform."""
        boton = QPushButton(texto.upper())
        boton.setFixedHeight(ALTO_BOTON_BARRA)
        # Los que no son ni "primario" ni "peligro" son teclas oscuras con relieve
        # (clase "barra", ver ui/hoja_de_estilos.py).
        aplicar_clase(boton, clase or "barra")
        if habilitado:
            boton.clicked.connect(funcion)
        else:
            restringir(boton)
        layout.addWidget(boton)
        return boton

    def closeEvent(self, evento):
        self._timer_caja.stop()
        self._timer_parpadeo.stop()
        if self._vuelta is not None:
            self._vuelta.detener()
        # Sin nadie adentro no hay quién conteste: el aviso abierto se va con la sesión.
        if self._tareas is not None:
            self._tareas.detener()
        super().closeEvent(evento)

    # -----------------------------------------------------------------
    # La caja: número arriba, botón que titila y cierre forzoso
    # -----------------------------------------------------------------

    def _actualizar_estado_de_la_caja(self):
        """Lee cómo está la caja, la muestra al lado del nombre y decide si el
        botón Cierre de Turno titila. Devuelve el estado (ver
        relevo_repo.estado_de_la_caja) o None si no hay caja abierta."""
        estado = relevo_repo.estado_de_la_caja()
        self._poner_estado_de_la_caja(estado)
        return estado

    def _poner_estado_de_la_caja(self, estado):
        """Muestra `estado` (ver relevo_repo.estado_de_la_caja) al lado del nombre y
        decide si el botón Cierre de Turno titila."""
        if estado is None:
            self._mostrar_texto_de_la_caja("·  Sin caja abierta" if self.es_admin else "")
        elif self.es_admin or estado["responsable_id"] != self.usuario["id"]:
            self._mostrar_texto_de_la_caja(
                f"·  Caja Nº {estado['caja_numero']} de {estado['responsable']} · {estado['turno_label']}"
            )
        else:
            self._mostrar_texto_de_la_caja(f"·  Caja Nº {estado['caja_numero']} · {estado['turno_label']}")
        self._titilar = bool(estado and estado["titilar"])

    def _mostrar_texto_de_la_caja(self, texto: str):
        """La caja, al lado del nombre (escondida si no hay nada que decir)."""
        self.etiqueta_caja.setText(texto)
        self.etiqueta_caja.setVisible(bool(texto))

    def _mostrar_la_caja_del_mostrador(self):
        """Desde otra PC, al abrir la ventana: el número de caja que ve el mostrador,
        o que no hay conexión (sin carteles: se vuelve a probar en la próxima
        revisión, ver _preguntar_la_caja_al_mostrador)."""
        try:
            self._actualizar_estado_de_la_caja()
        except (ValueError, PermissionError):  # sin red, o se cerró la sesión en el mostrador
            self._mostrar_texto_de_la_caja("·  Sin conexión con el mostrador")

    def _preguntar_la_caja_al_mostrador(self):
        """
        Desde otra PC, en cada revisión: la pregunta va en un hilo aparte y la
        respuesta se muestra cuando llega (_ver_si_contesto_la_caja). Esperada en el
        hilo de la pantalla, con el mostrador cerrado o la red lenta la copia se
        trababa cada 10 segundos aunque nadie tocara nada (y en un hilo tampoco sale
        el cartel de ui/espera_del_mostrador.py, que acá aparecería solo). Mientras
        la anterior no vuelve, no se pregunta de nuevo.
        """
        if self._pregunta_de_la_caja is not None:
            return
        resultado = {}
        # Al hilo va la función del repo (en la copia remota, la que le pregunta al
        # mostrador) y el dict, nunca la ventana (ver ui/en_segundo_plano.py).
        hilo = threading.Thread(
            target=_correr, args=(relevo_repo.estado_de_la_caja, (), resultado),
            name="caja-del-mostrador", daemon=True,
        )
        self._pregunta_de_la_caja = (hilo, resultado)
        hilo.start()
        self._timer_respuesta_caja.start()

    def _ver_si_contesto_la_caja(self):
        hilo, resultado = self._pregunta_de_la_caja
        if hilo.is_alive():
            return
        self._timer_respuesta_caja.stop()
        self._pregunta_de_la_caja = None
        try:
            self._poner_estado_de_la_caja(Respuesta(resultado).valor())
        except (ValueError, PermissionError):  # sin red, o se cerró la sesión en el mostrador
            self._mostrar_texto_de_la_caja("·  Sin conexión con el mostrador")

    def _parpadear(self):
        """Titila en rojo (alterna con su color de siempre) mientras toca
        cerrar; si no, se queda con su color de siempre. El rojo es la clase
        "alerta" de la hoja de estilos (ui/hoja_de_estilos.py). Desde otra PC
        titila igual, con la caja del mostrador."""
        self._encendido = self._titilar and not self._encendido
        clase = "alerta" if self._encendido else "barra"
        if self.boton_cierre_turno.property("clase") != clase:
            aplicar_clase(self.boton_cierre_turno, clase)
        # TAREAS DEL TURNO, mientras haya atrasadas: el mismo rojo por propiedad, con
        # los mismos bordes (QPushButton#accesoInicio[alerta] en la hoja de estilos).
        self._encendido_tareas = bool(self._tareas_atrasadas) and not self._encendido_tareas
        if bool(self.acceso_tareas.property("alerta")) != self._encendido_tareas:
            self.acceso_tareas.setProperty("alerta", self._encendido_tareas)
            self.acceso_tareas.style().unpolish(self.acceso_tareas)
            self.acceso_tareas.style().polish(self.acceso_tareas)

    def _poner_tareas_atrasadas(self, cuantas: int):
        """Lo que cuenta ui/aviso_tarea.RevisorDeTareas: el numerito amarillo arriba a la
        derecha del acceso (y, con alguna, el titileo de _parpadear)."""
        self._tareas_atrasadas = cuantas
        insignia = self.acceso_tareas.insignia
        insignia.setText(str(cuantas))
        insignia.setVisible(cuantas > 0)
        insignia.setMinimumWidth(ALTO_INSIGNIA)
        insignia.adjustSize()
        insignia.move(ANCHO_ACCESO - insignia.width() - MARGEN_INSIGNIA, MARGEN_INSIGNIA)

    def _hay_un_cobro_a_medias(self) -> bool:
        """
        Si hay una pantalla abierta encima que no se puede cerrar sin perder
        algo (un carrito con artículos, el cobro, un formulario): el cierre
        forzoso espera a que termine, como esperaría una persona para apretar
        el botón. Una pantalla que avisa que se puede cerrar sola (Ventas con el
        carrito vacío, Caja) se cierra y se sigue en la próxima revisión.
        """
        encima = QApplication.activeModalWidget()
        if encima is None:
            return False
        se_puede_cerrar_sola = getattr(encima, "se_puede_cerrar_sola", None)
        if se_puede_cerrar_sola is not None and se_puede_cerrar_sola():
            encima.reject()
        return True

    def _revisar_la_caja(self):
        """
        Cada INTERVALO_REVISION_CAJA_MS: actualiza el número de caja y el
        titileo, y si pasaron los minutos de gracia hace el cierre forzoso
        (pedido del dueño: "el programa aprieta solo Cierre de Turno"). Después,
        quien atiende vuelve a la pantalla de ingreso como con un cierre normal;
        el Admin se queda donde estaba (no estaba atendiendo esa caja).

        Desde otra PC solo se actualizan el número de caja y el titileo:
        el cierre forzoso lo hace el mostrador.
        """
        if self._remota:
            self._preguntar_la_caja_al_mostrador()
            return
        try:
            estado = self._actualizar_estado_de_la_caja()
            if estado is None or not estado["vencida"]:
                return
            if self._hay_un_cobro_a_medias():
                return
            resultado = relevo_repo.cierre_forzoso_si_corresponde()
        except Exception as error:  # un fallo de la base no puede tirar abajo el mostrador
            registrar_error(error, "Revisar la caja (cierre forzoso)")
            return
        if resultado is None:
            return
        self._actualizar_estado_de_la_caja()
        if self.es_admin:
            mostrar_info(
                self, "Cierre forzoso",
                f"La caja Nº {resultado['caja_numero']} de {resultado['responsable']} "
                f"({resultado['turno_label']}) se cerró sola: pasaron {MINUTOS_PARA_CIERRE_FORZOSO} minutos del fin del turno.\n\n"
                f"{resultado['responsable']} tiene que armar el sobre. {mensaje_del_sobre(resultado)}",
            )
            return
        mostrar_info(
            self, "Cierre forzoso",
            f"Tu caja Nº {resultado['caja_numero']} ({resultado['turno_label']}) se cerró sola: pasaron "
            f"{MINUTOS_PARA_CIERRE_FORZOSO} minutos del fin del turno.\n\n"
            f"{mensaje_del_sobre(resultado)}\n\n"
            "Ahora volvés a la pantalla de ingreso. Si tu reemplazo no llegó, volvé a entrar con tu "
            "usuario y seguí vendiendo: no hace falta contar el Cambio Fijo.",
        )
        self._cerrar_sesion()

    # -----------------------------------------------------------------
    # Abrir cada módulo (diálogos modales)
    # -----------------------------------------------------------------

    @solo_en_el_mostrador
    def _abrir_ventas(self):
        VentasWindow(self.usuario, self).exec()

    @solo_en_el_mostrador
    def _abrir_impresiones(self):
        articulo = impresiones_repo.articulo_impresiones()
        if articulo is None:
            mostrar_error(self, "Falta el artículo", impresiones_repo.mensaje_sin_articulo())
            return
        DialogoImpresiones(self.usuario, articulo, self).exec()

    def _abrir_caja(self):
        CajaWindow(self).exec()

    @solo_en_el_mostrador
    def _abrir_gestion_impresiones(self):
        VentanaGestionImpresiones(self.usuario, self).exec()

    @solo_en_el_mostrador
    def _abrir_pedidos_clientes(self):
        VentanaPedidosClientes(self.usuario, self).exec()

    @solo_en_el_mostrador
    def _abrir_tareas_turno(self):
        ventana = VentanaTareasTurno(self.usuario, self)
        # Lo que se contesta en el aviso con la ventana abierta se ve ya en la lista:
        # esperando su repaso de los 30 s, seguía ATRASADA con su tecla HECHA.
        al_contestar = ventana._repasar
        self._tareas.contestaron.connect(al_contestar)
        try:
            ventana.exec()
        finally:
            self._tareas.contestaron.disconnect(al_contestar)
        # Lo que se marcó o se cargó adentro se ve ya en el numerito del acceso.
        self._tareas.contar()

    def _abrir_ranking_rotacion(self):
        """RANKING DE ROTACIÓN (2026-11-04). Es un reporte: lo abre quien tiene el
        permiso de Reportes (el Admin siempre). El acceso lo ven todos, como los
        demás; a quien no tiene el permiso le dice "Acceso Restringido", como todo
        botón que no puede usar (pedido del dueño, 2026-11-04). Desde otra PC
        también se abre: solo mira."""
        if not usuarios_repo.tiene_permiso(self.usuario, "permiso_reportes"):
            avisar_acceso_restringido(self)
            return
        VentanaRankingRotacion(self).exec()

    @solo_en_el_mostrador
    def _abrir_cierre_turno(self):
        dialogo = CierreTurnoWindow(self.usuario, self)
        dialogo.exec()
        # Cerrar un turno implica que ya llegó el relevo -- en vez de
        # dejar la sesión de quien cerró abierta, se vuelve sola al Login
        # (mismo camino que el botón "🔄 Operador") para que la próxima
        # persona entre con su propio usuario. Si se canceló el diálogo
        # sin confirmar el cierre (turno_cerrado sigue en False), no pasa
        # nada -- sigue todo como estaba.
        if dialogo.turno_cerrado:
            self._cerrar_sesion()

    def _abrir_cambiar_clave(self):
        DialogoCambiarClave(self.usuario, self).exec()

    @solo_en_el_mostrador
    def _abrir_acomodar_caja(self):
        DialogoAcomodarCaja(self.usuario, self).exec()

    def _abrir_lista_de_compras(self):
        VentanaListaDeCompras(self).exec()

    def _abrir_administrar_kiosko(self):
        AdministrarKioskoWindow(self.usuario, self.es_admin, self).exec()

    def _abrir_configuracion_admin(self):
        ConfiguracionAdminWindow(self.usuario, self).exec()

    def _cambiar_operador(self):
        """"🔄 Operador": vuelve al ingreso para que entre otro. Si el que entra es
        el Administrador, a los minutos vuelve solo a quien estaba (ver
        ui/vuelta_del_admin.py): esta empleada, o la que tenía el Administrador
        para volver (salir y entrar de nuevo como Administrador no la pierde)."""
        self.a_quien_volveria = self._volver_a if self.es_admin else self.usuario["id"]
        self._cerrar_sesion()

    def _volver_sola(self, usuario):
        """Pasaron los minutos del Administrador: vuelve a la empleada (`usuario`,
        con su ingreso ya anotado) o, si no se pudo, a la pantalla de ingreso."""
        if usuario is None or self._al_volver_a is None:
            self._cerrar_sesion()
            return
        self.close()
        self._al_volver_a(usuario)

    def _cerrar_sesion(self):
        self.close()
        self._al_cerrar_sesion()

