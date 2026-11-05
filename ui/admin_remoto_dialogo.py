"""
admin_remoto_dialogo.py
========================
"Entrar desde otra PC" (Configuración ADMIN, solo en el mostrador): prender o
apagar que el Administrador administre desde otra PC del local, con los pasos
para hacerlo. La regla (viene apagado, solo Admin) vive en
repositories/admin_remoto_repo.py; cómo viaja cada pedido, en admin_remoto/.

Al guardar PRENDIDO, además revisa que el firewall de Windows deje pasar a las
otras PCs al puerto del programa y, si no, lo abre con el permiso de Windows
(admin_remoto/firewall.py explica por qué hizo falta). Las dos cosas corren en
un hilo aparte (ui/en_segundo_plano.py): la de abrir espera a que alguien
conteste el cartel de Windows, y el mostrador no se puede quedar trabado.
"""

import socket

from PySide6.QtWidgets import QCheckBox, QDialog, QLabel, QVBoxLayout

import servidor_red
from admin_remoto import firewall
from repositories import admin_remoto_repo
from ui.en_segundo_plano import EnSegundoPlano
from ui.piezas_ventana import TONO_AZUL, TONO_GRIS, agregar_pastilla, cabecera_oscura, panel_blanco, titulo_de_seccion
from ui.utils import fila_guardar_cancelar, manejar_errores, mostrar_aviso, mostrar_info, sin_boton_por_defecto

_PRENDIDA = "La entrada desde otra PC quedó PRENDIDA."
_NO_LO_ENCUENTRA = "desde otra PC va a decir \"No encuentro el FRKiosko del mostrador\""


def _nombre_y_ips_de_esta_pc():
    """El nombre de esta PC en la red y sus IP del local (para escribir la
    carpeta compartida en la otra PC). Si Windows no las da, lo que haya."""
    nombre = socket.gethostname()
    try:
        ips = sorted({ip for ip in socket.gethostbyname_ex(nombre)[2] if not ip.startswith("127.")})
    except OSError:
        ips = []
    return nombre, ips


class DialogoEntrarDesdeOtraPC(QDialog):
    """Con la cabecera oscura (y una pastilla que dice si hoy está prendido), los
    pasos en un panel blanco y la casilla en otro (maqueta B, 2026-10-30)."""

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.setWindowTitle("Entrar desde otra PC")
        self.resize(640, 620)
        self._armar_interfaz()
        self._espera = EnSegundoPlano(self, [self.boton_guardar, self.check_activo])

    def _armar_interfaz(self):
        nombre, ips = _nombre_y_ips_de_esta_pc()
        ips_texto = " o ".join(ips) if ips else "(no se pudo saber)"

        activo = admin_remoto_repo.esta_activo()
        cabecera = cabecera_oscura("🌐", "Entrar desde otra PC", "Que el Administrador administre desde otra PC del local")
        agregar_pastilla(cabecera, "PRENDIDO" if activo else "APAGADO", TONO_AZUL if activo else TONO_GRIS)

        explicacion = QLabel(
            "Con esto prendido, el <b>Administrador</b> puede administrar desde otra PC del local "
            "(artículos y precios, compras, ventas, reportes, cierres, usuarios y Configuración ADMIN) "
            "mientras acá se sigue atendiendo normal. Los datos son siempre los de esta PC: la otra "
            "no tiene base propia.<br><br>"
            "<b>Cómo se entra:</b><ol>"
            "<li>Compartí en la red la carpeta donde está FRKiosko.exe (con contraseña).</li>"
            "<li>En la otra PC, abrí FRKiosko.exe <b>desde esa carpeta compartida</b>. Si la "
            "carpeta se comparte con el nombre FRKiosko, es:<br>"
            f"<b>\\\\{nombre}\\FRKiosko\\FRKiosko.exe</b></li>"
            "<li>Entrá con el usuario Administrador y su clave.</li></ol>"
            "Al guardar con la casilla tildada, el programa se fija que el firewall de Windows deje "
            "pasar a las otras PCs y, si hace falta, lo arregla: Windows te pide permiso, decile "
            "<b>Sí</b>.<br><br>"
            f"Esta PC es <b>{nombre}</b> (IP {ips_texto}). Este programa tiene que estar abierto acá.<br><br>"
            "Los operadores no pueden entrar desde otra PC. Vender, cobrar y cerrar el turno "
            "se sigue haciendo solo acá."
        )
        explicacion.setWordWrap(True)

        self.check_activo = QCheckBox("Permitir que el Administrador entre desde otra PC")
        self.check_activo.setChecked(activo)

        panel_pasos, capa_pasos = panel_blanco()
        capa_pasos.addWidget(titulo_de_seccion("Cómo funciona"))
        capa_pasos.addWidget(explicacion)
        panel_casilla, capa_casilla = panel_blanco()
        capa_casilla.addWidget(self.check_activo)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(cabecera)
        layout.addWidget(panel_pasos)
        layout.addWidget(panel_casilla)
        layout.addStretch()
        fila = fila_guardar_cancelar(self, self._guardar)
        # La fila es [espacio, Guardar, Cancelar]: Guardar se apaga mientras se
        # revisa el firewall (Cancelar no).
        self.boton_guardar = fila.itemAt(1).widget()
        layout.addLayout(fila)
        self.setLayout(layout)
        sin_boton_por_defecto(self)

    @manejar_errores
    def _guardar(self):
        activo = self.check_activo.isChecked()
        admin_remoto_repo.activar(self.usuario["id"], activo)
        if not activo:
            mostrar_info(
                self, "Listo",
                "La entrada desde otra PC quedó APAGADA (si alguien estaba adentro desde otra PC, ya no puede seguir).",
            )
            self.accept()
            return
        self._programa = firewall.programa_de_este_frkiosko()
        self._espera.arrancar(firewall.revisar, self._programa, al_terminar=self._firewall_revisado)

    @manejar_errores
    def _firewall_revisado(self, respuesta):
        revision = respuesta.valor()
        if revision is None:
            self._terminar(
                f"{_PRENDIDA}\n\nNo pude revisar el firewall de Windows de esta PC. Si {_NO_LO_ENCUENTRA}, "
                "puede ser que el firewall no deje pasar a las otras PCs."
            )
            return
        if revision.abierto:
            self._terminar(_PRENDIDA)
            return
        mostrar_info(
            self, "Falta un permiso de Windows",
            f"{_PRENDIDA}\n\nPero el firewall de Windows de esta PC no deja pasar a las otras PCs: así, "
            f"{_NO_LO_ENCUENTRA}.\n\n"
            "Al apretar OK, Windows te va a preguntar si dejás que haga cambios en el equipo: decile Sí. "
            "(Si el usuario de Windows de esta PC no es Administrador, te va a pedir la clave de uno.)",
        )
        self._espera.arrancar(
            firewall.abrir, self._programa, int(self.winId()), al_terminar=self._firewall_abierto,
        )

    @manejar_errores
    def _firewall_abierto(self, respuesta):
        resultado = respuesta.valor()
        if resultado == firewall.ABIERTO:
            self._terminar(f"{_PRENDIDA}\n\nY el firewall de Windows ya deja pasar a las otras PCs del local.")
            return
        # La entrada ya quedó prendida; la ventana sigue abierta para volver a
        # apretar Guardar.
        if resultado == firewall.CANCELADO:
            mostrar_aviso(
                self, "Entrar desde otra PC",
                f"{_PRENDIDA}\n\nPero Windows no dio el permiso, así que {_NO_LO_ENCUENTRA}.\n\n"
                "Apretá Guardar de nuevo y decile Sí a Windows.",
            )
        else:
            mostrar_aviso(
                self, "Entrar desde otra PC",
                f"{_PRENDIDA}\n\nPero no pude abrir el paso en el firewall de Windows de esta PC, así que "
                f"{_NO_LO_ENCUENTRA}.\n\nSi esta PC tiene un antivirus con firewall propio, ahí hay que "
                f"permitir a FRKiosko (puerto {servidor_red.PUERTO_SERVIDOR}).",
            )

    def _terminar(self, mensaje: str):
        if not servidor_red.esta_escuchando():
            mensaje += (
                f"\n\nOjo: este programa no pudo abrir su puerto de red ({servidor_red.PUERTO_SERVIDOR}); "
                "puede que otro programa lo esté usando. Cerrá FRKiosko y volvé a abrirlo."
            )
        mostrar_info(self, "Listo", mensaje)
        self.accept()
