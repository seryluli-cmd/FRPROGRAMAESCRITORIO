"""
cambio_fijo_dialogo.py
========================
La ventana del CAMBIO FIJO (la plata para dar cambio que queda en el cajón en cada
turno). Se abre desde su propia tarjeta de Administrar Kiosko, solo el Admin.
Hasta el 2026-11-04 era una tecla dentro de Usuarios, y el dueño no la encontraba:
la pidió afuera, a la vista con solo entrar a ADMIN KIOSKO.

Por dentro el monto sigue siendo `fondo_cambio` (config_repo); en pantalla se llama
"Cambio Fijo" en todos lados.
"""

from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

from ui.piezas_ventana import cabecera_oscura, panel_blanco
from ui.utils import CampoPesos, encadenar_enter, fila_guardar_cancelar, sin_boton_por_defecto


class DialogoFondoCambio(QDialog):
    """Pide el monto del Cambio Fijo; quien lo abre lo lee de `spin_monto` si se
    aceptó (ver AdministrarKioskoWindow._abrir_cambio_fijo). Con la cabecera oscura
    y el monto en un panel blanco (maqueta B, 2026-10-30)."""

    def __init__(self, parent, valor_actual: float):
        super().__init__(parent)
        self.setWindowTitle("Cambio Fijo")
        self.resize(440, 270)

        cabecera = cabecera_oscura("💵", "Cambio Fijo", "La plata para dar cambio en el cajón")

        self.spin_monto = CampoPesos()
        self.spin_monto.setValue(valor_actual)
        self.spin_monto.setMinimumHeight(36)
        encadenar_enter(self.spin_monto, accion_final=self.accept)

        panel, capa = panel_blanco()
        capa.addWidget(QLabel("Cambio Fijo que arranca cada turno:"))
        capa.addWidget(self.spin_monto)

        botones = fila_guardar_cancelar(self)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(cabecera)
        layout.addWidget(panel)
        layout.addStretch()
        layout.addLayout(botones)
        self.setLayout(layout)
        sin_boton_por_defecto(self)
