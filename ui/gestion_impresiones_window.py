"""
gestion_impresiones_window.py
==============================
GESTIÓN IMPRESIONES (pedido del dueño, 2026-11-02, con la maqueta aprobada ese
día): el cuarto acceso de la pantalla de inicio. Un cliente encarga muchas
impresiones, deja una seña (o lo paga entero) y lo retira después pagando lo que
falta. Las reglas y dónde queda la plata, en repositories/pedidos_impresion_repo.py.

- La lista, con la maqueta B (ui/piezas_ventana.py): arriba cuántos pedidos
  esperan, cuánto se cobró de seña y cuánto falta cobrar; filtros por estado,
  buscador por nombre o teléfono, y en la grilla quién tomó cada pedido.
- NUEVO PEDIDO: nombre, teléfono, hojas y seña; el total y lo que falta salen
  solos y quien lo toma es el operador del mostrador. Se cobra con la ventana de
  cobro de siempre.
- RETIRA Y PAGA EL RESTO (o doble clic): cobra lo que falta y lo da por entregado.
- AVISAR POR WHATSAPP: abre WhatsApp Web con el chat del cliente y el mensaje ya
  escrito; lo manda quien atiende.
- SEÑA PERDIDA y ANULAR, solo el Administrador.

Cobra, así que se abre solo en el mostrador (MainWindow._abrir_gestion_impresiones).
"""

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QSpinBox, QTableWidgetItem, QVBoxLayout,
)

import dominio
from repositories import impresiones_repo, pedidos_impresion_repo
from ui.dialogo_pago import DialogoPago
from ui.dibujos_tabla import DelegadoEtiqueta
from ui.piezas_ventana import (
    TONO_AZUL, TONO_VERDE, agregar_indicador, buscador, cabecera_oscura, cifra_destacada, fila_de_filtros,
    marcar_solo_admin, panel_blanco, panel_de_tabla, pie_de_ventana, poner_indicador, tecla,
)
from ui.utils import (
    CampoPesos, confirmar, crear_tabla, encadenar_enter, fila_guardar_cancelar, formato_fecha_hora, formato_pesos,
    manejar_errores, mostrar_aviso, mostrar_error, mostrar_info, sin_boton_por_defecto,
)

TITULO = "Gestión Impresiones"
COLUMNAS = ["Nº", "Fecha", "A nombre de", "Teléfono", "Hojas", "Total", "Seña", "Falta", "Tomó", "Estado", "Avisado"]
COLUMNA_NOMBRE = 2
COLUMNA_FALTA = 7
COLUMNA_ESTADO = 9
_A_LA_DERECHA = (4, 5, 6, 7)
_TONOS_DE_ESTADO = {
    dominio.PEDIDO_PENDIENTE: "ámbar",
    dominio.PEDIDO_RETIRADO: "verde",
    dominio.PEDIDO_SENA_PERDIDA: "gris",
    dominio.PEDIDO_ANULADO: "rosa",
}


def _telefono_a_la_vista(telefono: str) -> str:
    """Los 10 números como se leen: "11 5555 1234" en Buenos Aires y, con las
    características de tres números (las más comunes del interior), "351 555 1234".
    Solo es para leerlo: se guarda y se manda sin espacios."""
    if len(telefono or "") != 10:
        return telefono or ""
    if telefono.startswith("11"):
        return f"{telefono[:2]} {telefono[2:6]} {telefono[6:]}"
    return f"{telefono[:3]} {telefono[3:6]} {telefono[6:]}"


def _texto_vuelto(dialogo_pago) -> str:
    return f"\nVuelto a entregar: {formato_pesos(dialogo_pago.vuelto)}" if dialogo_pago.vuelto > 0 else ""


class VentanaGestionImpresiones(QDialog):
    """La lista de pedidos con sus botones."""

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.es_admin = dominio.es_admin(usuario)
        self._pedidos = []
        self._estado_elegido = dominio.PEDIDO_PENDIENTE
        self.setWindowTitle(TITULO)
        self.resize(1280, 720)
        self._armar_interfaz()
        self._cargar()

    def se_puede_cerrar_sola(self) -> bool:
        """Solo es una lista: el cierre forzoso de la caja la puede cerrar. Con un
        pedido o un cobro abierto encima, la que se consulta es esa, y esa espera."""
        return True

    def _armar_interfaz(self):
        cabecera = cabecera_oscura(
            "📑", TITULO, f"Pedidos grandes con seña · atiende: {self.usuario['nombre']}")
        self.indicador_pendientes = agregar_indicador(cabecera, "Pendientes")
        self.indicador_senas = agregar_indicador(cabecera, "Señas cobradas")
        self.indicador_falta = agregar_indicador(cabecera, "Falta cobrar")

        self.boton_nuevo = tecla("＋  NUEVO PEDIDO", self._nuevo_pedido, "teclaAzul")
        self.boton_entregar = tecla("📦  RETIRA Y PAGA EL RESTO", self._entregar, "teclaVerde")
        self.boton_avisar = tecla("💬  AVISAR POR WHATSAPP", self._avisar)
        self.boton_avisar.setToolTip("Abre WhatsApp Web con el mensaje de que el pedido está listo.")
        barra_botones = QHBoxLayout()
        barra_botones.setSpacing(8)
        for boton in (self.boton_nuevo, self.boton_entregar, self.boton_avisar):
            barra_botones.addWidget(boton)
        if self.es_admin:
            self.boton_perdida = tecla("SEÑA PERDIDA", self._sena_perdida)
            self.boton_perdida.setToolTip("El cliente no vino: la seña queda para el local.")
            self.boton_anular = tecla("ANULAR", self._anular, "teclaRoja")
            for boton in (self.boton_perdida, self.boton_anular):
                marcar_solo_admin(boton)
                barra_botones.addWidget(boton)
        barra_botones.addStretch()
        barra_botones.addWidget(tecla("CERRAR", self.close, "teclaRoja"))

        self.campo_buscar = buscador("Buscar por nombre o teléfono")
        self.campo_buscar.textChanged.connect(self._cargar_grilla)
        self.filtros = fila_de_filtros(
            [("Pendientes", dominio.PEDIDO_PENDIENTE), ("Retirados", dominio.PEDIDO_RETIRADO),
             ("Seña perdida", dominio.PEDIDO_SENA_PERDIDA), ("Anulados", dominio.PEDIDO_ANULADO)],
            self._elegir_estado,
        )
        # Se abre en Pendientes: es lo que se busca casi siempre.
        self.filtros.pastillas[1].setChecked(True)

        self.tabla = crear_tabla(COLUMNAS, estirar=COLUMNA_NOMBRE, por_filas=True, una_sola=True)
        etiqueta_estado = DelegadoEtiqueta(self.tabla)
        etiqueta_estado.colores_fijos(_TONOS_DE_ESTADO)
        self.tabla.setItemDelegateForColumn(COLUMNA_ESTADO, etiqueta_estado)
        for columna, ancho in ((0, 50), (1, 135), (3, 115), (4, 60), (5, 95), (6, 95), (7, 95), (8, 110),
                               (COLUMNA_ESTADO, 130), (10, 135)):
            self.tabla.setColumnWidth(columna, ancho)
        for columna in _A_LA_DERECHA:
            self.tabla.horizontalHeaderItem(columna).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.tabla.cellDoubleClicked.connect(lambda _fila, _columna: self._entregar())

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(cabecera)
        layout.addLayout(barra_botones)
        layout.addWidget(self.campo_buscar)
        layout.addWidget(self.filtros)
        layout.addWidget(panel_de_tabla(self.tabla), 1)
        layout.addWidget(pie_de_ventana(
            "Doble clic en un pendiente para entregarlo  ·  La seña entra en la caja de quien toma el pedido; "
            "lo que falta, en la de quien lo entrega"))
        self.setLayout(layout)
        sin_boton_por_defecto(self)

    def _elegir_estado(self, estado):
        self._estado_elegido = estado
        self._cargar_grilla()

    @manejar_errores
    def _cargar(self):
        self._pedidos = pedidos_impresion_repo.listar_pedidos()
        numeros = dominio.numeros_de_los_pedidos(self._pedidos)
        poner_indicador(self.indicador_pendientes, str(numeros["pendientes"]))
        poner_indicador(self.indicador_senas, formato_pesos(numeros["senas"]))
        poner_indicador(self.indicador_falta, formato_pesos(numeros["falta"]), alerta=numeros["falta"] > 0)
        self._cargar_grilla()

    def _a_la_vista(self):
        """Los pedidos del estado elegido (o todos) que coinciden con lo buscado."""
        buscado = dominio.sin_acentos(self.campo_buscar.text().strip())
        buscado_numeros = "".join(c for c in buscado if c.isdigit())
        a_la_vista = []
        for pedido in self._pedidos:
            if self._estado_elegido is not None and pedido["estado"] != self._estado_elegido:
                continue
            if buscado and buscado not in dominio.sin_acentos(pedido["nombre"]) and not (
                    buscado_numeros and buscado_numeros in pedido["telefono"]):
                continue
            a_la_vista.append(pedido)
        return a_la_vista

    def _cargar_grilla(self):
        pedidos = self._a_la_vista()
        self.tabla.setRowCount(len(pedidos))
        for fila, pedido in enumerate(pedidos):
            falta = dominio.falta_abonar(pedido["total"], pedido["sena"])
            textos = (
                str(pedido["id"]), formato_fecha_hora(pedido["fecha"]), pedido["nombre"],
                _telefono_a_la_vista(pedido["telefono"]), str(pedido["hojas"]), formato_pesos(pedido["total"]),
                formato_pesos(pedido["sena"]),
                formato_pesos(falta) if pedido["estado"] == dominio.PEDIDO_PENDIENTE else "",
                pedido["tomado_por_nombre"], pedido["estado"],
                formato_fecha_hora(pedido["avisado"]) if pedido["avisado"] else "",
            )
            for columna, texto in enumerate(textos):
                celda = QTableWidgetItem(texto)
                if columna in _A_LA_DERECHA:
                    celda.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if columna == COLUMNA_FALTA and falta > 0:
                    celda.setForeground(Qt.red)
                if columna == 0:
                    celda.setData(Qt.UserRole, pedido["id"])
                self.tabla.setItem(fila, columna, celda)

    def _pedido_elegido(self, para: str):
        """El pedido marcado en la grilla, o None (con el aviso de que falta elegirlo)."""
        fila = self.tabla.currentRow()
        if fila < 0 or self.tabla.item(fila, 0) is None:
            mostrar_aviso(self, "Elegí un pedido", f"Marcá en la lista el pedido que querés {para}.")
            return None
        pedido_id = self.tabla.item(fila, 0).data(Qt.UserRole)
        return next(pedido for pedido in self._pedidos if pedido["id"] == pedido_id)

    def _pedido_pendiente(self, para: str):
        pedido = self._pedido_elegido(para)
        if pedido is not None and pedido["estado"] != dominio.PEDIDO_PENDIENTE:
            mostrar_aviso(self, "Ese pedido no está pendiente",
                          f"El pedido Nº {pedido['id']} está {pedido['estado']}.")
            return None
        return pedido

    @manejar_errores
    def _nuevo_pedido(self):
        articulo = impresiones_repo.articulo_impresiones()
        if articulo is None:
            mostrar_error(self, "Falta el artículo", impresiones_repo.mensaje_sin_articulo())
            return
        if DialogoNuevoPedido(self.usuario, articulo, self).exec():
            self._cargar()

    @manejar_errores
    def _entregar(self):
        pedido = self._pedido_pendiente("entregar")
        if pedido is not None and DialogoEntregarPedido(self.usuario, pedido, self).exec():
            self._cargar()

    @manejar_errores
    def _avisar(self):
        pedido = self._pedido_pendiente("avisar")
        if pedido is None:
            return
        if not pedido["telefono"]:
            mostrar_aviso(self, "Sin teléfono", f"El pedido de {pedido['nombre']} no tiene teléfono anotado.")
            return
        mensaje = dominio.mensaje_pedido_listo(
            pedido["nombre"], pedido["hojas"], dominio.falta_abonar(pedido["total"], pedido["sena"]))
        if not QDesktopServices.openUrl(QUrl(dominio.enlace_whatsapp(pedido["telefono"], mensaje))):
            mostrar_error(self, "No se abrió WhatsApp", "No se pudo abrir el navegador con WhatsApp Web.")
            return
        pedidos_impresion_repo.anotar_aviso(pedido["id"])
        self._cargar()

    @manejar_errores
    def _sena_perdida(self):
        pedido = self._pedido_pendiente("dar por perdido")
        if pedido is None:
            return
        if not confirmar(self, "Seña perdida",
                         f"¿{pedido['nombre']} no viene más a retirar el pedido Nº {pedido['id']}?\n"
                         f"La seña de {formato_pesos(pedido['sena'])} queda para el local y el pedido "
                         "deja de estar pendiente."):
            return
        pedidos_impresion_repo.dar_por_perdida(self.usuario["id"], pedido["id"])
        self._cargar()

    @manejar_errores
    def _anular(self):
        pedido = self._pedido_elegido("anular")
        if pedido is None:
            return
        if pedido["estado"] == dominio.PEDIDO_ANULADO:
            mostrar_aviso(self, "Ya anulado", f"El pedido Nº {pedido['id']} ya estaba anulado.")
            return
        if not confirmar(self, "Anular pedido",
                         f"¿Anular el pedido Nº {pedido['id']} de {pedido['nombre']}?\n"
                         "Se anulan también sus cobros: salen de la caja y de los reportes."):
            return
        motivo, aceptado = QInputDialog.getText(
            self, "Motivo de la anulación", "Contá brevemente por qué se anula este pedido:")
        if not aceptado or not motivo.strip():
            mostrar_error(self, "Falta el motivo", "Tenés que indicar un motivo para anular el pedido.")
            return
        pedidos_impresion_repo.anular_pedido(self.usuario["id"], pedido["id"], motivo.strip())
        mostrar_info(self, "Pedido anulado", f"Se anuló el pedido Nº {pedido['id']} y sus cobros.")
        self._cargar()


class DialogoNuevoPedido(QDialog):
    """Tomar un pedido: a nombre de quién, teléfono, hojas y seña. Quien lo toma es
    el operador del mostrador. `articulo` es el de impresiones_repo.articulo_impresiones()."""

    def __init__(self, usuario, articulo, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.articulo = articulo
        self.setWindowTitle("Nuevo pedido de impresiones")
        self.resize(520, 600)
        self._armar_interfaz()
        self._actualizar_cuenta()

    def _armar_interfaz(self):
        cabecera = cabecera_oscura(
            "＋", "Nuevo pedido",
            f"{self.articulo['descripcion']} · {formato_pesos(self.articulo['precio_venta'])} la hoja")

        self.campo_nombre = QLineEdit()
        self.campo_nombre.setPlaceholderText("Martina López")
        self.campo_telefono = QLineEdit()
        self.campo_telefono.setPlaceholderText("11 5555 1234 (con la característica, sin 0 y sin 15)")
        self.spin_hojas = QSpinBox()
        self.spin_hojas.setRange(1, dominio.HOJAS_MAXIMAS_POR_PEDIDO)
        self.spin_hojas.setValue(1)
        self.spin_hojas.setButtonSymbols(QSpinBox.NoButtons)
        self.campo_sena = CampoPesos()
        self.campo_sena.setButtonSymbols(CampoPesos.NoButtons)
        self.boton_todo = tecla("PAGA EL TOTAL", self._paga_el_total)
        self.boton_todo.setToolTip("La seña es el total: lo paga entero ahora y retira sin pagar nada más.")
        for campo in (self.campo_nombre, self.campo_telefono, self.spin_hojas, self.campo_sena):
            campo.setMinimumHeight(36)
        self.spin_hojas.valueChanged.connect(self._actualizar_cuenta)
        self.campo_sena.valueChanged.connect(self._actualizar_cuenta)

        grilla = QGridLayout()
        grilla.setHorizontalSpacing(10)
        grilla.setVerticalSpacing(8)
        grilla.addWidget(QLabel("A nombre de"), 0, 0)
        grilla.addWidget(self.campo_nombre, 0, 1, 1, 2)
        grilla.addWidget(QLabel("Teléfono (opcional)"), 1, 0)
        grilla.addWidget(self.campo_telefono, 1, 1, 1, 2)
        grilla.addWidget(QLabel("Cantidad de hojas"), 2, 0)
        grilla.addWidget(self.spin_hojas, 2, 1, 1, 2)
        grilla.addWidget(QLabel("Seña (paga ahora)"), 3, 0)
        grilla.addWidget(self.campo_sena, 3, 1)
        grilla.addWidget(self.boton_todo, 3, 2)
        grilla.setColumnStretch(1, 1)

        self.etiqueta_total = QLabel()
        self.etiqueta_total.setStyleSheet("font-size: 18px; font-weight: bold; color: #1B2233;")
        self.cifra_falta = cifra_destacada("FALTA ABONAR", "Lo paga cuando lo viene a retirar", TONO_AZUL)
        tomado = QLabel(f"Toma el pedido: {self.usuario['nombre']} (el operador de ahora)")
        tomado.setStyleSheet("color: #58677D;")

        panel, capa = panel_blanco()
        capa.addLayout(grilla)
        capa.addWidget(self.etiqueta_total)
        capa.addWidget(self.cifra_falta)
        capa.addWidget(tomado)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(cabecera)
        layout.addWidget(panel)
        layout.addStretch()
        layout.addLayout(fila_guardar_cancelar(self, self._cobrar, texto_guardar="Cobrar seña"))
        self.setLayout(layout)
        encadenar_enter(self.campo_nombre, self.campo_telefono, self.spin_hojas, self.campo_sena,
                        accion_final=self._cobrar)
        sin_boton_por_defecto(self)
        self.campo_nombre.setFocus()

    def showEvent(self, evento):
        super().showEvent(evento)
        QTimer.singleShot(0, self.spin_hojas.selectAll)

    def _total(self) -> float:
        return dominio.total_del_pedido(self.spin_hojas.value(), self.articulo["precio_venta"])

    def _actualizar_cuenta(self):
        total = self._total()
        self.etiqueta_total.setText(f"TOTAL: {formato_pesos(total)}  ({self.spin_hojas.value()} hojas)")
        self.cifra_falta.valor.setText(formato_pesos(max(0.0, dominio.falta_abonar(total, self.campo_sena.value()))))

    def _paga_el_total(self):
        self.campo_sena.setValue(self._total())

    @manejar_errores
    def _cobrar(self):
        nombre = self.campo_nombre.text().strip()
        if not nombre:
            raise ValueError("Escribí a nombre de quién es el pedido.")
        # Antes de abrir el cobro: que no se cobre una seña de un pedido que después
        # no se va a poder grabar (el repo lo vuelve a revisar todo al grabar).
        dominio.telefono_limpio(self.campo_telefono.text())
        total, sena = self._total(), round(self.campo_sena.value(), 2)
        dominio.revisar_sena(total, sena)
        cobro = DialogoPago(self, sena)
        if not cobro.exec():
            return
        numero = pedidos_impresion_repo.tomar_pedido(
            self.usuario["id"], nombre, self.campo_telefono.text(), self.spin_hojas.value(),
            self.articulo["precio_venta"], sena, cobro.pagos,
        )
        falta = dominio.falta_abonar(total, sena)
        mostrar_info(self, "Pedido tomado",
                     f"Pedido Nº {numero} a nombre de {nombre}: {self.spin_hojas.value()} hojas, "
                     f"{formato_pesos(total)}.\nSeña cobrada: {formato_pesos(sena)}\n"
                     f"Falta abonar al retirar: {formato_pesos(falta)}" + _texto_vuelto(cobro))
        self.accept()


class DialogoEntregarPedido(QDialog):
    """El cliente retira el pedido: muestra lo que pagó y cobra lo que falta."""

    def __init__(self, usuario, pedido, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.pedido = pedido
        self.falta = dominio.falta_abonar(pedido["total"], pedido["sena"])
        self.setWindowTitle(f"Retira el pedido Nº {pedido['id']}")
        self.resize(480, 460)
        self._armar_interfaz()

    def _armar_interfaz(self):
        pedido = self.pedido
        cabecera = cabecera_oscura(
            "📦", f"Retira el pedido Nº {pedido['id']}",
            f"{pedido['nombre']} · {pedido['hojas']} hojas · tomado el {formato_fecha_hora(pedido['fecha'])}")

        grilla = QGridLayout()
        grilla.setHorizontalSpacing(10)
        grilla.setVerticalSpacing(6)
        renglones = (
            ("Total del pedido", formato_pesos(pedido["total"])),
            (f"Pagó de seña (lo tomó {pedido['tomado_por_nombre']})", formato_pesos(pedido["sena"])),
        )
        for fila, (texto, monto) in enumerate(renglones):
            grilla.addWidget(QLabel(texto), fila, 0)
            valor = QLabel(monto)
            valor.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grilla.addWidget(valor, fila, 1)
        cifra = cifra_destacada(
            "FALTA ABONAR", "El total menos la seña" if self.falta > 0 else "Ya lo pagó entero", TONO_VERDE)
        cifra.valor.setText(formato_pesos(self.falta))
        entrega = QLabel(f"Entrega: {self.usuario['nombre']} (el operador de ahora)")
        entrega.setStyleSheet("color: #58677D;")

        panel, capa = panel_blanco()
        capa.addLayout(grilla)
        capa.addWidget(cifra)
        capa.addWidget(entrega)

        texto_boton = f"Cobrar {formato_pesos(self.falta)} y entregar" if self.falta > 0 else "Entregar"
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(cabecera)
        layout.addWidget(panel)
        layout.addStretch()
        layout.addLayout(fila_guardar_cancelar(self, self._entregar, texto_guardar=texto_boton))
        self.setLayout(layout)
        sin_boton_por_defecto(self)

    @manejar_errores
    def _entregar(self):
        cobro = None
        pagos = []
        if self.falta > 0:
            cobro = DialogoPago(self, self.falta)
            if not cobro.exec():
                return
            pagos = cobro.pagos
        numero = pedidos_impresion_repo.entregar_pedido(self.usuario["id"], self.pedido["id"], pagos)
        mensaje = f"Pedido Nº {self.pedido['id']} entregado a {self.pedido['nombre']}."
        if self.falta > 0:
            mensaje += f"\nCobrado: {formato_pesos(self.falta)} (venta Nº {numero})" + _texto_vuelto(cobro)
        mostrar_info(self, "Pedido entregado", mensaje)
        self.accept()
