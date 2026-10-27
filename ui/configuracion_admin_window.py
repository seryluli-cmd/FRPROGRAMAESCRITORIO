"""Configuración del kiosko reservada al Administrador."""

from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QVBoxLayout

import dominio
from admin_remoto import modo as modo_remoto
from ui.accesos_admin_window import AccesosAdminWindow
from ui.admin_remoto_dialogo import DialogoEntrarDesdeOtraPC
from ui.envio_pwa_dialogo import DialogoEnvioPwa
from ui.piezas_ventana import (
    TONO_AZUL, TONO_GRIS, agregar_pastilla, bloquear_tarjeta,
    cabecera_oscura, tarjeta_de_menu, tecla, titulo_de_seccion,
)
from ui.utils import sin_boton_por_defecto


class ConfiguracionAdminWindow(QDialog):
    """Accesos de Admin, administración remota y envío de cierres."""

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.setWindowTitle("Configuración ADMIN")
        self.resize(660, 430)
        self._armar_interfaz()

    def _armar_interfaz(self):
        es_admin = dominio.es_admin(self.usuario)
        cabecera = cabecera_oscura(
            "⚙️", "Configuración ADMIN",
            f"{self.usuario['nombre']} · " + ("Administrador" if es_admin else "Operador"),
        )
        agregar_pastilla(cabecera, "ADMIN" if es_admin else "OPERADOR", TONO_AZUL if es_admin else TONO_GRIS)

        accesos = [
            ("🔐", "Accesos de Admin", "Quién entró con una cuenta de administrador", self._abrir_accesos_admin),
        ]
        # La entrada remota se prende y se apaga únicamente en el mostrador.
        if not modo_remoto.es_copia_remota():
            accesos.append((
                "🌐", "Entrar desde otra PC", "Administrar el kiosko desde otra compu del local",
                self._abrir_entrar_desde_otra_pc,
            ))
        grupos = [("Administración", accesos)]
        if not modo_remoto.es_copia_remota():
            grupos.append(("La app de gastos", [
                ("📲", "Cierres a la app de gastos", "Cada Cierre de Turno se asienta solo en Gestión Central",
                 self._abrir_envio_pwa),
            ]))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(cabecera)
        for titulo, tarjetas in grupos:
            layout.addSpacing(4)
            layout.addWidget(titulo_de_seccion(titulo))
            grilla = QGridLayout()
            grilla.setSpacing(10)
            for numero, (icono, nombre, detalle, funcion) in enumerate(tarjetas):
                tarjeta = tarjeta_de_menu(icono, nombre, detalle, funcion)
                if not es_admin:
                    bloquear_tarjeta(tarjeta)
                ancho = 2 if numero == len(tarjetas) - 1 and numero % 2 == 0 else 1
                grilla.addWidget(tarjeta, numero // 2, numero % 2, 1, ancho)
            grilla.setColumnStretch(0, 1)
            grilla.setColumnStretch(1, 1)
            layout.addLayout(grilla)
        layout.addStretch()

        pie = QHBoxLayout()
        pie.addStretch()
        pie.addWidget(tecla("CERRAR", self.close, "teclaRoja"))
        layout.addLayout(pie)
        sin_boton_por_defecto(self)

    def _abrir_accesos_admin(self):
        AccesosAdminWindow(self).exec()

    def _abrir_entrar_desde_otra_pc(self):
        DialogoEntrarDesdeOtraPC(self.usuario, self).exec()

    def _abrir_envio_pwa(self):
        DialogoEnvioPwa(self.usuario, self).exec()
