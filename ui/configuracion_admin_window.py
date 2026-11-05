"""Configuración del kiosko reservada al Administrador."""

from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QVBoxLayout

import dominio
from admin_remoto import modo as modo_remoto
from repositories import pelotita_repo
from ui.accesos_admin_window import AccesosAdminWindow
from ui.admin_remoto_dialogo import DialogoEntrarDesdeOtraPC
from ui.envio_pwa_dialogo import DialogoEnvioPwa
from ui.piezas_ventana import (
    TONO_AZUL, TONO_GRIS, agregar_pastilla, restringir,
    cabecera_oscura, tarjeta_de_menu, tecla, titulo_de_seccion,
)
from ui.utils import manejar_errores, sin_boton_por_defecto

# Lo que dice la tarjeta de la pelotita del inicio según cómo está.
DETALLE_PELOTITA = {
    True: "PRENDIDA: rebota en el inicio · tocá para apagarla",
    False: "APAGADA · tocá para prenderla",
}


class ConfiguracionAdminWindow(QDialog):
    """Accesos de Admin, administración remota, envío de cierres y la pelotita."""

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
            # La pelotita del inicio (ui/pelotita.py) es solo del mostrador. La tarjeta
            # misma es el interruptor: cada toque la prende o la apaga.
            grupos.append(("La pantalla", [
                ("☄️", "Pelotita que rebota", DETALLE_PELOTITA[pelotita_repo.esta_prendida()],
                 self._prender_o_apagar_pelotita),
            ]))
        self.tarjeta_pelotita = None

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
                if funcion == self._prender_o_apagar_pelotita:
                    self.tarjeta_pelotita = tarjeta
                if not es_admin:
                    restringir(tarjeta)
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

    @manejar_errores
    def _prender_o_apagar_pelotita(self):
        """La da vuelta para todos (el repo vuelve a exigir Admin). La ventana
        principal la pone o la saca al cerrar esta (MainWindow._poner_pelotita)."""
        prendida = not pelotita_repo.esta_prendida()
        pelotita_repo.prender(self.usuario["id"], prendida)
        self.tarjeta_pelotita.detalle.setText(DETALLE_PELOTITA[prendida])
