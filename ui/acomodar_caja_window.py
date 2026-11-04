"""
acomodar_caja_window.py
=========================
El botón "ORDENAR $" de la barra (primero se llamó "Acomodar Caja"), a la derecha de Cambiar Pass (pedido del
dueño, 2026-11-04: "voy a cambiar el programa a mitad de turno"). El Admin
escribe cuánto cobró el programa anterior en efectivo y en digital, y entra en
la caja abierta para que el cierre dé bien. Las reglas están en
repositories/acomodar_caja_repo.py: la pantalla solo junta los dos montos.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QGridLayout, QLabel, QVBoxLayout

from repositories import acomodar_caja_repo, cajas_repo
from ui.piezas_ventana import cabecera_oscura, panel_blanco
from ui.utils import (
    CampoPesos, confirmar, encadenar_enter, fila_guardar_cancelar, formato_pesos, manejar_errores,
    mostrar_info, sin_boton_por_defecto,
)


def a_donde_va(caja) -> str:
    """Qué caja se va a acomodar, dicho para quien atiende."""
    if caja is None:
        return ("No hay ninguna caja abierta: queda anotado y pasa a la próxima caja "
                "que se abra.")
    return f"Va a la caja Nº {caja['id']} de {caja['responsable']} ({caja['turno'].capitalize()})."


class DialogoAcomodarCaja(QDialog):
    """Efectivo y digital del programa anterior, con el total abajo."""

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.caja = cajas_repo.caja_abierta()
        self.setWindowTitle("Ordenar $")
        self.resize(480, 380)
        self._armar_interfaz()
        self._actualizar_total()

    def _armar_interfaz(self):
        cabecera = cabecera_oscura(
            "🧮", "Ordenar $", "Lo que ya cobró el programa anterior en este turno")

        self.campo_efectivo = CampoPesos()
        self.campo_digital = CampoPesos()
        for campo in (self.campo_efectivo, self.campo_digital):
            campo.setButtonSymbols(CampoPesos.NoButtons)
            campo.setMinimumHeight(40)
            campo.setStyleSheet("font-size: 18px; font-weight: bold;")
            campo.valueChanged.connect(self._actualizar_total)

        self.etiqueta_destino = QLabel(a_donde_va(self.caja))
        self.etiqueta_destino.setWordWrap(True)

        self.etiqueta_total = QLabel()
        self.etiqueta_total.setAlignment(Qt.AlignCenter)
        self.etiqueta_total.setStyleSheet("font-size: 20px; font-weight: bold; color: #2F6FED;")

        grilla = QGridLayout()
        grilla.addWidget(QLabel("EFECTIVO"), 0, 0)
        grilla.addWidget(self.campo_efectivo, 0, 1)
        grilla.addWidget(QLabel("DIGITAL"), 1, 0)
        grilla.addWidget(self.campo_digital, 1, 1)

        panel, capa = panel_blanco()
        capa.addWidget(self.etiqueta_destino)
        capa.addLayout(grilla)
        capa.addWidget(self.etiqueta_total)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(cabecera)
        layout.addWidget(panel)
        layout.addStretch()
        layout.addLayout(fila_guardar_cancelar(self, self._guardar, texto_guardar="Acomodar"))
        self.setLayout(layout)
        encadenar_enter(self.campo_efectivo, self.campo_digital, accion_final=self._guardar)
        sin_boton_por_defecto(self)
        self.campo_efectivo.setFocus()

    def showEvent(self, evento):
        super().showEvent(evento)
        # Con el $ 0 seleccionado, lo que se escribe lo reemplaza.
        QTimer.singleShot(0, self.campo_efectivo.selectAll)

    def _actualizar_total(self):
        self.etiqueta_total.setText(
            f"SE SUMA A LA CAJA: {formato_pesos(self.campo_efectivo.value() + self.campo_digital.value())}")

    @manejar_errores
    def _guardar(self):
        efectivo, digital = self.campo_efectivo.value(), self.campo_digital.value()
        if not confirmar(
            self, "Ordenar $",
            f"Se suman a la caja {formato_pesos(efectivo)} en efectivo y "
            f"{formato_pesos(digital)} en digital del programa anterior.\n\n"
            f"{a_donde_va(self.caja)}\n\n¿Está bien?",
        ):
            return
        numero = acomodar_caja_repo.acomodar_caja(self.usuario["id"], efectivo, digital)
        mostrar_info(
            self, "Caja acomodada",
            f"Listo: {formato_pesos(efectivo + digital)} sumados a la caja.\nVenta Nº {numero}\n\n"
            "Si te equivocaste, anulala en Consulta de Ventas y cargala de nuevo.")
        self.accept()
