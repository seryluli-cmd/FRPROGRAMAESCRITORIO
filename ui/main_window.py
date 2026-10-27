"""Ventana principal del kiosko: ventas, impresiones, caja y administración.

La copia para administrar desde otra PC conserva las mismas pantallas de
consulta y gestión. Los cobros y el cierre de turno se hacen en el mostrador.
"""

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
)
from PySide6.QtCore import QTimer

import dominio
from admin_remoto import modo as modo_remoto
from errores import registrar_error
from repositories import impresiones_repo, relevo_repo, usuarios_repo
from turnos import MINUTOS_PARA_CIERRE_FORZOSO
from ui.administrar_kiosko_window import AdministrarKioskoWindow
from ui.configuracion_admin_window import ConfiguracionAdminWindow
from ui.impresiones_window import DialogoImpresiones
from ui.ventas_window import VentasWindow
from ui.caja_window import CajaWindow, CierreTurnoWindow
from ui.usuarios_window import DialogoCambiarClave
from ui.ingreso_caja import mensaje_del_sobre
from ui.vuelta_del_admin import VueltaDelAdmin
from ui.utils import (
    aplicar_clase, icono_de_emoji, mostrar_error, mostrar_info, solo_en_el_mostrador,
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
        # Desde otra PC no: ahí no hay una empleada a la que volver.
        self._vuelta = None
        if self.es_admin and not self._remota:
            self._vuelta = VueltaDelAdmin(self, volver_a, self._volver_sola, self._hay_un_cobro_a_medias)

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
        botones.setSpacing(6)
        layout_barra.addLayout(botones)
        self._armar_botones_de_la_barra(botones)
        barra.setLayout(layout_barra)

        contenedor = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        layout.addWidget(barra)

        inicio = QFrame()
        inicio.setObjectName("inicioKiosko")
        columna_inicio = QVBoxLayout(inicio)
        columna_inicio.setContentsMargins(28, 24, 28, 24)
        columna_inicio.setSpacing(12)
        titulo_inicio = QLabel("KIOSKO")
        titulo_inicio.setStyleSheet("font-size: 28px; font-weight: 800; color: #263B5A;")
        columna_inicio.addWidget(titulo_inicio)
        descripcion = QLabel("Venta de mercadería, impresiones y control de caja")
        descripcion.setStyleSheet("font-size: 15px; color: #58677D;")
        columna_inicio.addWidget(descripcion)
        columna_inicio.addSpacing(16)
        accesos = QHBoxLayout()
        for texto, accion in (
            ("🛒  VENTA DE MERCADERÍA", self._abrir_ventas),
            ("🖨️  IMPRESIONES", self._abrir_impresiones),
            ("💵  CAJA", self._abrir_caja),
        ):
            boton = QPushButton(texto)
            boton.setMinimumHeight(64)
            aplicar_clase(boton, "primario")
            boton.clicked.connect(accion)
            accesos.addWidget(boton)
        columna_inicio.addLayout(accesos)
        columna_inicio.addStretch()
        layout.addWidget(inicio, 1)
        contenedor.setLayout(layout)
        self.setCentralWidget(contenedor)

    def _armar_botones_de_la_barra(self, layout_barra):
        """El renglón de botones, de izquierda a derecha empezando por Vender y
        terminando en "🔄 Operador", pegado a la derecha de Clave (pedido del
        dueño, 2026-10-23; hasta ese día iba solo en la punta derecha y, con la
        pantalla de 1920 del mostrador, quedaba lejos de todo). Se llamaba
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
        self._agregar_boton_barra(layout_barra, "🔑  Clave", self._abrir_cambiar_clave)
        # Tres espacios entre el dibujito y el texto: uno más que en los otros botones (pedido del dueño).
        boton_operador = self._agregar_boton_barra(layout_barra, "   Operador", self._cambiar_operador, clase="peligro")
        # Su dibujito va un 25% más grande que los de los otros botones (pedido del dueño,
        # 2026-10-24): uno dentro del texto mide lo que la letra, así que este va como ícono.
        boton_operador.ensurePolished()
        icono, tamano = icono_de_emoji(DIBUJITO_OPERADOR, boton_operador.fontInfo().pixelSize() * AGRANDAR_DIBUJITO_OPERADOR)
        boton_operador.setIcon(icono)
        boton_operador.setIconSize(tamano)
        layout_barra.addStretch()

    def _agregar_boton_barra(self, layout, texto, funcion, clase=None, habilitado=True):
        """Botón de la barra superior: alto fijo, ancho según el texto
        (van en fila, así que no hace falta que midan todos igual).

        Todos ven todos los botones (pedido del dueño, 2026-10-19: con solo los
        suyos la barra de una empleada quedaba muy vacía). Uno sin `habilitado`
        se ve igual que los demás pero no hace nada al apretarlo: no se lo
        apaga con setEnabled(False) porque se vería gris, distinto del resto.

        El texto va en mayúscula (y en negrita, por ui/hoja_de_estilos.py),
        pedido del dueño 2026-10-22; acá y no en la hoja porque Qt no tiene
        text-transform."""
        boton = QPushButton(texto.upper())
        boton.setFixedHeight(38)
        # Los que no son ni "primario" ni "peligro" son teclas oscuras con relieve
        # (clase "barra", ver ui/hoja_de_estilos.py).
        aplicar_clase(boton, clase or "barra")
        if habilitado:
            boton.clicked.connect(funcion)
        layout.addWidget(boton)
        return boton

    def closeEvent(self, evento):
        self._timer_caja.stop()
        self._timer_parpadeo.stop()
        if self._vuelta is not None:
            self._vuelta.detener()
        super().closeEvent(evento)

    # -----------------------------------------------------------------
    # La caja: número arriba, botón que titila y cierre forzoso
    # -----------------------------------------------------------------

    def _actualizar_estado_de_la_caja(self):
        """Lee cómo está la caja, la muestra al lado del nombre y decide si el
        botón Cierre de Turno titila. Devuelve el estado (ver
        relevo_repo.estado_de_la_caja) o None si no hay caja abierta."""
        estado = relevo_repo.estado_de_la_caja()
        if estado is None:
            self._mostrar_texto_de_la_caja("·  Sin caja abierta" if self.es_admin else "")
        elif self.es_admin or estado["responsable_id"] != self.usuario["id"]:
            self._mostrar_texto_de_la_caja(
                f"·  Caja Nº {estado['caja_numero']} de {estado['responsable']} · {estado['turno_label']}"
            )
        else:
            self._mostrar_texto_de_la_caja(f"·  Caja Nº {estado['caja_numero']} · {estado['turno_label']}")
        self._titilar = bool(estado and estado["titilar"])
        return estado

    def _mostrar_texto_de_la_caja(self, texto: str):
        """La caja, al lado del nombre (escondida si no hay nada que decir)."""
        self.etiqueta_caja.setText(texto)
        self.etiqueta_caja.setVisible(bool(texto))

    def _mostrar_la_caja_del_mostrador(self):
        """Desde otra PC: el número de caja que ve el mostrador, o que no hay
        conexión (sin carteles: se vuelve a probar en la próxima revisión)."""
        try:
            self._actualizar_estado_de_la_caja()
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
            self._mostrar_la_caja_del_mostrador()
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

