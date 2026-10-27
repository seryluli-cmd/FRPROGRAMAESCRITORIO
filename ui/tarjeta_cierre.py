"""
tarjeta_cierre.py
==================
El resumen de un Cierre de Turno tal como lo ve la empleada al cerrar.

Lo dibujan dos pantallas con la MISMA tarjeta:
- CierreTurnoWindow (ui/caja_window.py): el turno en curso, antes de cerrarlo.
- DialogoDetalleCierre (ui/control_cierres_window.py): cualquier cierre ya
  hecho, común, forzoso o en ausencia (pedido del dueño, 2026-10-20: el cierre
  forzoso lo hace el programa solo y nadie veía este resumen; quiere verlo
  "como si fuera un cierre común").
Por eso vive acá y no en una de las dos: un cambio de diseño del Cierre de
Turno se ve también en Control de Cierres sin tocar nada más.

Desde el 2026-10-26 (el dueño la vio "muy vulgar" y pidió un diseño de alto nivel,
con el criterio de Configuración ADMIN) tiene la cabecera oscura de las otras
ventanas, arriba las dos cifras que importan (A RETIRAR EN EFECTIVO y el TOTAL) y
abajo la tabla de dónde vino la plata, negocio por negocio, con el efectivo y lo
digital en columnas. La tabla (TablaDeNegocios) la comparte con la pantalla Caja.
Los datos son los mismos de antes: cambia solo cómo se ven.
"""

from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

import dominio
from ui.piezas_ventana import TONO_AZUL, TONO_VERDE, cabecera_oscura, cifra_destacada
from ui.utils import formato_pesos

# La nota de abajo de la tarjeta en el Cierre de Turno de todos los días.
NOTA_AL_CERRAR = (
    "Retirá el efectivo indicado y guardalo en el sobre. Dejá el cambio "
    "fijo en el cajón para que arranque el próximo turno."
)

# Los renglones y nombres vienen de dominio.NEGOCIOS_DEL_CIERRE.
_DIBUJITOS = ("🛒", "🖨️")
NEGOCIOS = tuple(
    (clave, dibujito, nombre)
    for (clave, nombre), dibujito in zip(dominio.NEGOCIOS_DEL_CIERRE, _DIBUJITOS, strict=True)
)


def titulo_de_la_caja(resumen) -> str:
    """"Caja Nº 12 de Lucía · " si el resumen es de una caja (ver
    turnos_repo.resumen_turno_actual); si no, nada."""
    if resumen["caja_numero"] is None:
        return ""
    return f"Caja Nº {resumen['caja_numero']} de {resumen['responsable']} · "


def detalle_de_la_cabecera(resumen) -> str:
    """La línea de abajo del título en Caja y en Cierre de Turno: "Caja Nº 22 de MATI ·
    Turno Domingo T2" (sin caja, solo el turno)."""
    return f"{titulo_de_la_caja(resumen)}Turno {resumen['turno_actual_label']}"


def etiqueta_dato(titulo, valor_texto, destacado=False, color_titulo=None, color_valor=None, negrita_titulo=False):
    """Un dato suelto: título gris arriba y valor grande abajo (en azul si
    `destacado`). `color_titulo`/`color_valor` pintan cada etiqueta aparte y
    `negrita_titulo` pone el título en negrita.
    Devuelve (layout, etiqueta_del_valor) para poder actualizarla."""
    contenedor = QVBoxLayout()
    titulo_lbl = QLabel(titulo)
    valor_lbl = QLabel(valor_texto)
    fuente_valor = QFont()
    fuente_valor.setPointSize(14)
    fuente_valor.setBold(True)
    valor_lbl.setFont(fuente_valor)
    if negrita_titulo:
        fuente_titulo = QFont()
        fuente_titulo.setBold(True)
        titulo_lbl.setFont(fuente_titulo)
    titulo_lbl.setStyleSheet(f"color: {color_titulo or '#6B7585'};")
    if color_valor:
        valor_lbl.setStyleSheet(f"color: {color_valor};")
    elif destacado:
        valor_lbl.setStyleSheet("color: #2F6FED;")
    contenedor.addWidget(titulo_lbl)
    contenedor.addWidget(valor_lbl)
    return contenedor, valor_lbl


def _marcar(etiqueta: QLabel, propiedad: str, valor):
    """Cambia una propiedad que mira la hoja de estilos y le pide a Qt que la vuelva
    a pintar (sin eso se queda con el aspecto de antes)."""
    etiqueta.setProperty(propiedad, valor)
    etiqueta.style().unpolish(etiqueta)
    etiqueta.style().polish(etiqueta)


def _linea(nombre: str) -> QFrame:
    linea = QFrame()
    linea.setObjectName(nombre)
    linea.setFixedHeight(2 if nombre == "lineaTotal" else 1)
    return linea


def _monto(nombre: str) -> QLabel:
    etiqueta = QLabel()
    etiqueta.setObjectName(nombre)
    etiqueta.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return etiqueta


class RenglonDeNegocio:
    """Un renglón de la tabla: el dibujito y el nombre del negocio y lo cobrado en
    efectivo y en digital, cada uno en su columna. En cero se ve apagado, así salta
    a la vista de dónde vino la plata del turno."""

    def __init__(self, grilla: QGridLayout, fila: int, icono: str, nombre: str):
        self.icono = QLabel(icono)
        self.icono.setObjectName("iconoNegocio")
        # Un emoji no se apaga con un color: se le baja la opacidad.
        self._apagado = QGraphicsOpacityEffect(self.icono)
        self._apagado.setOpacity(0.35)
        self._apagado.setEnabled(False)
        self.icono.setGraphicsEffect(self._apagado)
        self.nombre = QLabel(nombre)
        self.nombre.setObjectName("nombreNegocio")
        self.efectivo = _monto("montoNegocio")
        self.digital = _monto("montoNegocio")
        for columna, etiqueta in enumerate((self.icono, self.nombre, self.efectivo, self.digital)):
            grilla.addWidget(etiqueta, fila, columna)

    def poner(self, efectivo: float, digital: float):
        self.efectivo.setText(formato_pesos(efectivo))
        self.digital.setText(formato_pesos(digital))
        vacio = not efectivo and not digital
        for etiqueta in (self.nombre, self.efectivo, self.digital):
            _marcar(etiqueta, "vacio", vacio)
        self._apagado.setEnabled(vacio)


class TablaDeNegocios(QFrame):
    """
    De dónde vino la plata, en Caja y en Cierre de Turno: un renglón por negocio
    (NEGOCIOS) con el efectivo y lo digital en columnas; abajo, lo cobrado en total
    (los mismos "Efectivo" y "Digital" de antes) y el cambio, que no es cobrado: en
    Caja es la caja inicial (aparte: la Caja Actual es solo el efectivo cobrado) y en
    el Cierre de Turno lo que queda en el cajón.

    - `nombre_cambio` / `nota_cambio`: cómo se llama ese último renglón en cada pantalla
      y una línea chica que dice qué es.
    """

    def __init__(self, nombre_cambio: str, nota_cambio: str, parent=None):
        super().__init__(parent)
        # Con el mismo nombre que los paneles blancos de las otras ventanas: misma hoja de estilos.
        self.setObjectName("panelBlanco")
        grilla = QGridLayout(self)
        grilla.setContentsMargins(16, 10, 16, 12)
        grilla.setHorizontalSpacing(10)
        grilla.setVerticalSpacing(0)
        grilla.setColumnMinimumWidth(0, 26)
        grilla.setColumnStretch(1, 1)
        grilla.setColumnMinimumWidth(2, 92)
        grilla.setColumnMinimumWidth(3, 92)

        encabezado = QLabel("DE DÓNDE VIENE")
        encabezado.setObjectName("encabezadoTabla")
        grilla.addWidget(encabezado, 0, 0, 1, 2)
        for columna, texto in ((2, "Efectivo"), (3, "Digital")):
            titulo = _monto("encabezadoTabla")
            titulo.setText(texto)
            grilla.addWidget(titulo, 0, columna)
        fila = 1

        self.renglones = {}
        for clave, icono, nombre in NEGOCIOS:
            grilla.addWidget(_linea("lineaRenglon"), fila, 0, 1, 4)
            self.renglones[clave] = RenglonDeNegocio(grilla, fila + 1, icono, nombre)
            fila += 2
        grilla.addWidget(_linea("lineaTotal"), fila, 0, 1, 4)
        cobrado = QLabel("Cobrado")
        cobrado.setObjectName("nombreTotal")
        self.valor_efectivo = _monto("montoTotal")
        self.valor_digital = _monto("montoTotal")
        grilla.addWidget(cobrado, fila + 1, 1)
        grilla.addWidget(self.valor_efectivo, fila + 1, 2)
        grilla.addWidget(self.valor_digital, fila + 1, 3)
        fila += 2

        grilla.addWidget(_linea("lineaRenglon"), fila, 0, 1, 4)
        cambio = QLabel(nombre_cambio)
        cambio.setObjectName("nombreCambio")
        nota = QLabel(nota_cambio)
        nota.setObjectName("notaCambio")
        # El cambio es efectivo: va en esa columna, a la altura de su nombre.
        self.valor_cambio = _monto("montoCambio")
        grilla.addWidget(cambio, fila + 1, 1)
        grilla.addWidget(self.valor_cambio, fila + 1, 2)
        grilla.addWidget(nota, fila + 2, 1, 1, 3)

    def renglon(self, clave: str) -> RenglonDeNegocio:
        return self.renglones[clave]

    def mostrar(self, resumen):
        """Llena la tabla con un resumen con las claves de turnos_repo.resumen_turno_actual."""
        for clave, _icono, _nombre in NEGOCIOS:
            self.renglones[clave].poner(resumen[f"{clave}_efectivo"], resumen[f"{clave}_digital"])
        self.valor_efectivo.setText(formato_pesos(resumen["ventas_efectivo"]))
        self.valor_digital.setText(formato_pesos(resumen["ventas_digital"]))
        self.valor_cambio.setText(formato_pesos(resumen["cambio_inicial"]))


class TarjetaCierreDeTurno(QWidget):
    """El resumen de un Cierre de Turno (ver el comentario del módulo): la cabecera con
    la caja y el turno, A RETIRAR EN EFECTIVO y el TOTAL, la tabla de dónde vino la
    plata y una nota abajo. No tiene botones: los pone cada pantalla."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._armar_interfaz()

    def _armar_interfaz(self):
        self.cabecera = cabecera_oscura("🧾", "Cierre de Turno")

        # Lo que la empleada guarda en el sobre, en verde como la Caja Actual de la
        # pantalla Caja, y el TOTAL en azul (los colores que eligió el dueño el 2026-10-20).
        retirar = cifra_destacada("A RETIRAR EN EFECTIVO", "Va al sobre · el cambio queda en el cajón", TONO_VERDE)
        # Efectivo + Digital de todo lo cobrado, SIN el Cambio Fijo.
        total = cifra_destacada("TOTAL (EFECTIVO + DIGITAL)", "Todo lo cobrado en el turno", TONO_AZUL)
        self.valor_retirar = retirar.valor
        self.valor_total = total.valor
        cifras = QHBoxLayout()
        cifras.setSpacing(10)
        cifras.addWidget(retirar, 1)
        cifras.addWidget(total, 1)

        # "Cambio Fijo" es como lo llama el dueño en esta pantalla (es lo que las
        # empleadas le mandan como resumen del turno); por dentro sigue siendo el
        # "fondo de cambio" (`fondo_cambio`).
        self.tabla = TablaDeNegocios("Cambio Fijo", "Queda en el cajón para el próximo turno")
        self.valor_efectivo = self.tabla.valor_efectivo
        self.valor_digital = self.tabla.valor_digital
        self.valor_fondo = self.tabla.valor_cambio
        self.nota = QLabel()
        self.nota.setObjectName("notaCierre")
        self.nota.setWordWrap(True)
        self.poner_nota(NOTA_AL_CERRAR)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.cabecera)
        layout.addLayout(cifras)
        layout.addWidget(self.tabla)
        layout.addWidget(self.nota)
        self.setLayout(layout)

    def renglon(self, clave: str) -> RenglonDeNegocio:
        """El renglón de un negocio de la tabla (las claves son las de NEGOCIOS)."""
        return self.tabla.renglon(clave)

    def mostrar(self, resumen):
        """Llena la tarjeta con un resumen con las claves de
        turnos_repo.resumen_turno_actual: el del turno en curso o el de un
        cierre ya hecho (control_cierres_repo.detalle_cierre()["resumen"])."""
        self.cabecera.detalle.setText(detalle_de_la_cabecera(resumen))
        self.valor_retirar.setText(formato_pesos(resumen["ventas_efectivo"]))
        self.valor_total.setText(formato_pesos(resumen["ventas_total"]))
        self.tabla.mostrar(resumen)

    def poner_nota(self, texto: str, alerta: bool = False):
        """La nota de abajo, en un recuadro gris, o rojo si `alerta` (un cierre
        forzoso o en ausencia, con el mismo rojo que en la tabla de Control de
        Cierres)."""
        self.nota.setText(texto)
        _marcar(self.nota, "alerta", alerta)
