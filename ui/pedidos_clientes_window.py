"""
pedidos_clientes_window.py
===========================
PEDIDOS DE CLIENTES (pedido del dueño, 2026-11-03, con la maqueta A aprobada ese
día): el quinto acceso de la pantalla de inicio. Lo que los clientes vienen a
buscar y no tenemos, contado por clientes, para saber qué conviene traer. Las
reglas, en repositories/pedidos_clientes_repo.py.

- Arriba, el campo "¿Qué pidió el cliente?" y GUARDAR (o Enter): si ya está en la
  lista (sin importar mayúsculas, tildes ni espacios) suma 1 cliente; si no, abre
  un renglón con 1. Mientras se escribe salen los parecidos: tocar uno le suma el
  cliente sin escribirlo entero.
- La lista, lo más pedido arriba, con cuántos clientes lo pidieron y la última vez
  (cuándo y quién). En cada renglón, +1 (otro cliente lo pidió) y TRAJIMOS (sale
  de la lista y pasa al HISTORIAL). El dueño pidió que diga solo "TRAJIMOS".
- RENOMBRAR, JUNTAR y BORRAR, solo el Administrador.

No cobra, pero por ahora se abre solo en el mostrador
(MainWindow._abrir_pedidos_clientes): al dueño se le preguntó el 2026-11-03 si la
quiere también desde otra PC y todavía no contestó. Para eso habría que sumar sus
funciones a admin_remoto/lista_blanca.py.
"""

import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QPushButton, QSizePolicy, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

import dominio
from repositories import pedidos_clientes_repo
from ui.piezas_ventana import (
    agregar_indicador, cabecera_oscura, marcar_solo_admin, panel_de_tabla, pie_de_ventana, poner_indicador, tecla,
    tecla_de_renglon,
)
from ui.utils import (
    aplicar_clase, confirmar, crear_tabla, encadenar_enter, formato_fecha_hora, manejar_errores, mostrar_aviso,
    sin_boton_por_defecto,
)

TITULO = "Pedidos de Clientes"
TEXTO_TRAJIMOS = "TRAJIMOS"
COLUMNAS = ["Producto", "Clientes", "Última vez", "", ""]
COLUMNA_PRODUCTO = 0
COLUMNA_CLIENTES = 1
COLUMNA_MAS_UNO = 3
COLUMNA_TRAJIMOS = 4
# Los renglones son más altos que en las otras listas: llevan dos teclas adentro, y el
# dueño las pidió más grandes (2026-11-03: "queda chico, agrandalo"). La letra de las
# teclas, en QPushButton[teclaDeRenglon] de ui/hoja_de_estilos.py.
ALTO_RENGLON = 58
ALTO_TECLA_RENGLON = 44
ANCHO_COLUMNA_MAS_UNO = 96
ANCHO_COLUMNA_TRAJIMOS = 170
# Con el nombre de quien anotó ("· Administrador") en un solo renglón.
ANCHO_COLUMNA_ULTIMA_VEZ = 260
# El número de clientes, en el azul oscuro de la tecla elegida (ui/hoja_de_estilos.py).
COLOR_CLIENTES = "#1D48A0"
# Cuántos parecidos se muestran debajo del campo mientras se escribe, y hasta qué
# ancho se ve el nombre de cada uno (más largo se corta con "…" y entero va en el
# cartelito): con los cinco de 60 letras la ventana se ensanchaba más que la pantalla.
PARECIDOS_A_LA_VISTA = 5
ANCHO_NOMBRE_PARECIDO = 150
# Lo que se anotó, en verde; lo que falta, en rojo (sin cartel: un Enter de más
# después de GUARDAR no tiene por qué abrir una ventana).
COLOR_HECHO = "#1F7A45"
COLOR_FALTA = "#A6323C"


def _texto_de_boton(texto: str) -> str:
    """En el texto de un botón Qt toma el "&" como letra de atajo: "M&M" se vería
    "MM" y Alt+M lo apretaría. Doblado se ve tal cual."""
    return texto.replace("&", "&&")


def _ultima_vez(pedido) -> str:
    """"03/11/2026 18:40 · Gaby": cuándo lo pidieron la última vez y quién lo anotó."""
    return f"{formato_fecha_hora(pedido['ultima_vez'])} · {pedido['ultima_vez_por'] or '—'}"


def _clientes_en_texto(clientes: int) -> str:
    return "1 cliente" if clientes == 1 else f"{clientes} clientes"


def _tecla_del_renglon(texto: str, al_apretar, clase: str) -> QWidget:
    """+1 y TRAJIMOS: la tecla de renglón que comparte con Tareas del Turno."""
    return tecla_de_renglon(texto, al_apretar, clase, ALTO_TECLA_RENGLON)


class VentanaPedidosClientes(QDialog):
    """La lista de lo que piden y no tenemos, con el campo para anotar."""

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.es_admin = dominio.es_admin(usuario)
        self._pedidos = []
        # Cuándo se armó la lista por última vez (ver _recien_reordenada).
        self._reordenada_a = 0.0
        self.setWindowTitle(TITULO)
        self.resize(1200, 720)
        self._armar_interfaz()
        self._cargar()

    def se_puede_cerrar_sola(self) -> bool:
        """Solo es una lista: el cierre forzoso de la caja la puede cerrar (lo que
        se guardó ya está guardado; a lo sumo se pierde lo que estaba a medio
        escribir en el campo)."""
        return True

    def _armar_interfaz(self):
        cabecera = cabecera_oscura(
            "🙋", TITULO, f"Lo que vienen a buscar y no tenemos · atiende: {self.usuario['nombre']}")
        self.indicador_productos = agregar_indicador(cabecera, "Productos")
        self.indicador_clientes = agregar_indicador(cabecera, "Clientes")

        self.campo = QLineEdit()
        self.campo.setObjectName("buscador")
        self.campo.setPlaceholderText("¿Qué pidió el cliente?  Ej.: Mantecol")
        self.campo.setMaxLength(dominio.LARGO_MAXIMO_PEDIDO_CLIENTE)
        self.campo.setMinimumHeight(40)
        self.campo.textChanged.connect(self._mostrar_parecidos)
        # Como en el resto del programa: un Enter que se repite por tener la tecla
        # apretada no cuenta otra vez.
        encadenar_enter(self.campo, accion_final=self._guardar)
        self.boton_guardar = tecla("GUARDAR", self._guardar, "teclaAzul")
        self.boton_guardar.setMinimumHeight(40)
        fila_anotar = QHBoxLayout()
        fila_anotar.setSpacing(8)
        fila_anotar.addWidget(self.campo, 1)
        fila_anotar.addWidget(self.boton_guardar)

        # Los parecidos a lo que se está escribiendo: una pastilla por cada uno,
        # "Mantecol (4)  +1". Se arman de nuevo con cada letra.
        self.fila_parecidos = QHBoxLayout()
        self.fila_parecidos.setContentsMargins(0, 0, 0, 0)
        self.fila_parecidos.setSpacing(6)
        self.titulo_parecidos = QLabel("¿Es alguno de estos? Tocalo y suma 1:")
        self.titulo_parecidos.setStyleSheet("color: #58677D;")
        self.fila_parecidos.addWidget(self.titulo_parecidos)
        self.fila_parecidos.addStretch()
        self._pastillas_parecidos = []
        contenedor_parecidos = QWidget()
        contenedor_parecidos.setLayout(self.fila_parecidos)
        contenedor_parecidos.setFixedHeight(34)
        # Que las pastillas no le pongan ancho mínimo a la ventana: si no entran, se
        # recortan las de la punta en vez de empujar la ventana fuera de la pantalla.
        contenedor_parecidos.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.titulo_parecidos.hide()

        # Lo que pasó con el último GUARDAR o +1 (o lo que falta para guardar).
        self.etiqueta_hecho = QLabel()

        self.tabla = crear_tabla(COLUMNAS, estirar=COLUMNA_PRODUCTO, por_filas=True, una_sola=True)
        for columna, ancho in ((COLUMNA_CLIENTES, 100), (2, ANCHO_COLUMNA_ULTIMA_VEZ),
                               (COLUMNA_MAS_UNO, ANCHO_COLUMNA_MAS_UNO), (COLUMNA_TRAJIMOS, ANCHO_COLUMNA_TRAJIMOS)):
            self.tabla.setColumnWidth(columna, ancho)
        self.tabla.horizontalHeaderItem(COLUMNA_CLIENTES).setTextAlignment(Qt.AlignCenter)

        self.boton_historial = tecla("📋  HISTORIAL", self._ver_historial)
        self.boton_historial.setToolTip("Lo que ya trajimos, con cuántos clientes lo habían pedido.")
        barra_botones = QHBoxLayout()
        barra_botones.setSpacing(8)
        barra_botones.addWidget(self.boton_historial)
        if self.es_admin:
            self.boton_renombrar = tecla("RENOMBRAR", self._renombrar)
            self.boton_juntar = tecla("JUNTAR", self._juntar)
            self.boton_juntar.setToolTip("Dos renglones que son lo mismo escrito distinto: se suman los clientes.")
            self.boton_borrar = tecla("BORRAR", self._borrar, "teclaRoja")
            for boton in (self.boton_renombrar, self.boton_juntar, self.boton_borrar):
                marcar_solo_admin(boton)
                barra_botones.addWidget(boton)
        barra_botones.addStretch()
        barra_botones.addWidget(tecla("CERRAR", self.close, "teclaRoja"))

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)
        layout.addWidget(cabecera)
        layout.addLayout(barra_botones)
        layout.addLayout(fila_anotar)
        layout.addWidget(contenedor_parecidos)
        layout.addWidget(self.etiqueta_hecho)
        layout.addWidget(panel_de_tabla(self.tabla, ALTO_RENGLON), 1)
        layout.addWidget(pie_de_ventana(
            "Si ya está en la lista, escribilo igual o tocá +1: suma en el mismo renglón  ·  "
            "TRAJIMOS lo saca de la lista; si lo vuelven a pedir, arranca de nuevo en 1"))
        self.setLayout(layout)
        sin_boton_por_defecto(self)
        self.campo.setFocus()

    @manejar_errores
    def _cargar(self, marcar_id=None):
        """Vuelve a leer la lista. Con `marcar_id`, deja elegido ese renglón (el que
        se acaba de anotar o sumar), así se ve dónde quedó."""
        self._pedidos = pedidos_clientes_repo.listar_pendientes()
        self._reordenada_a = time.monotonic()
        poner_indicador(self.indicador_productos, str(len(self._pedidos)))
        poner_indicador(self.indicador_clientes, str(sum(p["clientes"] for p in self._pedidos)))
        self.tabla.setRowCount(len(self._pedidos))
        for fila, pedido in enumerate(self._pedidos):
            producto = QTableWidgetItem(pedido["producto"])
            producto.setData(Qt.UserRole, pedido["id"])
            self.tabla.setItem(fila, COLUMNA_PRODUCTO, producto)
            clientes = QTableWidgetItem(str(pedido["clientes"]))
            clientes.setTextAlignment(Qt.AlignCenter)
            fuente = clientes.font()
            fuente.setBold(True)
            fuente.setPointSizeF(fuente.pointSizeF() * 1.2)
            clientes.setFont(fuente)
            clientes.setForeground(QColor(COLOR_CLIENTES))
            self.tabla.setItem(fila, COLUMNA_CLIENTES, clientes)
            self.tabla.setItem(fila, 2, QTableWidgetItem(_ultima_vez(pedido)))
            self.tabla.setCellWidget(fila, COLUMNA_MAS_UNO, _tecla_del_renglon(
                "+1", lambda _=False, i=pedido["id"]: self._mas_uno_del_renglon(i), "teclaAzul"))
            self.tabla.setCellWidget(fila, COLUMNA_TRAJIMOS, _tecla_del_renglon(
                TEXTO_TRAJIMOS, lambda _=False, i=pedido["id"]: self._trajimos(i), "teclaBlanca"))
            if pedido["id"] == marcar_id:
                self.tabla.selectRow(fila)
        if marcar_id is None:
            self.tabla.clearSelection()

    def _limpiar_parecidos(self):
        for pastilla in self._pastillas_parecidos:
            self.fila_parecidos.removeWidget(pastilla)
            # Escondida ya: deleteLater la borra recién en la próxima vuelta del bucle
            # de eventos, y hasta entonces quedaba dibujada como un recuadro blanco.
            pastilla.hide()
            pastilla.deleteLater()
        self._pastillas_parecidos = []
        self.titulo_parecidos.hide()

    @manejar_errores
    def _mostrar_parecidos(self, texto: str):
        self._limpiar_parecidos()
        self.etiqueta_hecho.clear()
        parecidos = pedidos_clientes_repo.parecidos(texto, PARECIDOS_A_LA_VISTA)
        self.titulo_parecidos.setVisible(bool(parecidos))
        for pedido in parecidos:
            pastilla = QPushButton()
            nombre = pastilla.fontMetrics().elidedText(pedido["producto"], Qt.ElideRight, ANCHO_NOMBRE_PARECIDO)
            pastilla.setText(_texto_de_boton(f"{nombre} ({pedido['clientes']})  +1"))
            pastilla.setToolTip(pedido["producto"])
            aplicar_clase(pastilla, "filtro")
            pastilla.setCursor(Qt.PointingHandCursor)
            pastilla.setAutoDefault(False)
            pastilla.clicked.connect(lambda _=False, i=pedido["id"]: self._sumar_uno(i))
            # Antes del estirón del final, en el orden en que vinieron.
            self.fila_parecidos.insertWidget(self.fila_parecidos.count() - 1, pastilla)
            self._pastillas_parecidos.append(pastilla)

    def _contar_lo_hecho(self, texto: str, falta: bool = False):
        self.etiqueta_hecho.setStyleSheet(f"color: {COLOR_FALTA if falta else COLOR_HECHO}; font-weight: bold;")
        self.etiqueta_hecho.setText(texto)

    @manejar_errores
    def _guardar(self):
        texto = self.campo.text()
        if not texto.strip():
            self._contar_lo_hecho("Escribí qué pidió el cliente y apretá GUARDAR.", falta=True)
            self.campo.setFocus()
            return
        anotado = pedidos_clientes_repo.anotar(self.usuario["id"], texto)
        if anotado["nuevo"]:
            self._contar_lo_hecho(f"Nuevo: 1 cliente pidió {anotado['producto']}")
        else:
            self._contar_lo_hecho(
                f"Sumado: ya son {_clientes_en_texto(anotado['clientes'])} que pidieron {anotado['producto']}")
        self._terminar(anotado["pedido_id"])

    def _recien_reordenada(self) -> bool:
        """Si la lista se volvió a armar hace menos que un doble clic. Cada +1 la
        reordena (lo más pedido arriba), así que un segundo clic rápido en el mismo
        lugar caería en el +1 de OTRO producto, el que quedó ahí."""
        return (time.monotonic() - self._reordenada_a) * 1000 < QApplication.doubleClickInterval()

    def _mas_uno_del_renglon(self, pedido_id: int):
        if self._recien_reordenada():
            return
        self._sumar_uno(pedido_id)

    @manejar_errores
    def _sumar_uno(self, pedido_id: int):
        clientes = pedidos_clientes_repo.sumar_uno(self.usuario["id"], pedido_id)
        producto = next((p["producto"] for p in self._pedidos if p["id"] == pedido_id), "")
        self._contar_lo_hecho(f"Sumado: ya son {_clientes_en_texto(clientes)} que pidieron {producto}")
        self._terminar(pedido_id)

    def _terminar(self, pedido_id: int):
        """Después de anotar: campo vacío y con el cursor, listo para el próximo, y la
        lista con el renglón marcado. El texto de lo hecho se pone antes y no se
        borra al vaciar el campo."""
        hecho = self.etiqueta_hecho.text()
        self.campo.clear()
        self.etiqueta_hecho.setText(hecho)
        self._volver_al_campo(marcar_id=pedido_id)

    @manejar_errores
    def _trajimos(self, pedido_id: int):
        pedido = next((p for p in self._pedidos if p["id"] == pedido_id), None)
        if pedido is None:
            return
        if not confirmar(self, TEXTO_TRAJIMOS,
                         f"¿Ya trajimos {pedido['producto']}?\n"
                         f"Sale de la lista ({_clientes_en_texto(pedido['clientes'])} lo pidieron) y queda en "
                         "el historial. Si lo vuelven a pedir, arranca de nuevo en 1."):
            return
        pedidos_clientes_repo.ya_lo_trajimos(self.usuario["id"], pedido_id)
        self._contar_lo_hecho(f"Trajimos {pedido['producto']}: pasó al historial")
        self._volver_al_campo()

    def _volver_al_campo(self, marcar_id=None):
        """Después de tocar un botón de la lista: la lista al día y el cursor en el
        campo. El botón apretado se borra al rearmar la lista y, sin esto, el foco
        quedaba en ninguna parte: lo que se escribía después se perdía."""
        self._cargar(marcar_id=marcar_id)
        self.campo.setFocus()

    def _pedido_elegido(self, para: str):
        """El renglón marcado en la lista, o None (con el aviso de que falta elegirlo)."""
        fila = self.tabla.currentRow()
        if fila < 0 or not self.tabla.selectionModel().hasSelection() or self.tabla.item(fila, 0) is None:
            mostrar_aviso(self, "Elegí un producto", f"Marcá en la lista el producto que querés {para}.")
            return None
        pedido_id = self.tabla.item(fila, 0).data(Qt.UserRole)
        return next(p for p in self._pedidos if p["id"] == pedido_id)

    @manejar_errores
    def _renombrar(self):
        pedido = self._pedido_elegido("renombrar")
        if pedido is None:
            return
        nuevo, aceptado = QInputDialog.getText(
            self, "Renombrar", "Nombre correcto del producto:", QLineEdit.Normal, pedido["producto"])
        if not aceptado or nuevo.strip() == pedido["producto"]:
            return
        pedidos_clientes_repo.renombrar(self.usuario["id"], pedido["id"], nuevo)
        self._volver_al_campo(marcar_id=pedido["id"])

    @manejar_errores
    def _juntar(self):
        origen = self._pedido_elegido("juntar con otro")
        if origen is None:
            return
        otros = [p for p in self._pedidos if p["id"] != origen["id"]]
        if not otros:
            mostrar_aviso(self, "No hay con cuál", "Es el único producto de la lista.")
            return
        opciones = [f"{p['producto']} ({_clientes_en_texto(p['clientes'])})" for p in otros]
        elegido, aceptado = QInputDialog.getItem(
            self, "Juntar",
            f"{origen['producto']} ({_clientes_en_texto(origen['clientes'])}) es lo mismo que:", opciones, 0, False)
        if not aceptado:
            return
        destino = otros[opciones.index(elegido)]
        if not confirmar(self, "Juntar",
                         f"Los clientes de {origen['producto']} pasan a {destino['producto']} y "
                         f"{origen['producto']} sale de la lista. ¿Seguro?"):
            return
        clientes = pedidos_clientes_repo.juntar(self.usuario["id"], origen["id"], destino["id"])
        self._contar_lo_hecho(f"Juntados: {destino['producto']} tiene {_clientes_en_texto(clientes)}")
        self._volver_al_campo(marcar_id=destino["id"])

    @manejar_errores
    def _borrar(self):
        pedido = self._pedido_elegido("borrar")
        if pedido is None:
            return
        if not confirmar(self, "Borrar",
                         f"¿Borrar {pedido['producto']} ({_clientes_en_texto(pedido['clientes'])})?\n"
                         "Es para un renglón anotado por error: no pasa al historial."):
            return
        pedidos_clientes_repo.borrar(self.usuario["id"], pedido["id"])
        self._volver_al_campo()

    @manejar_errores
    def _ver_historial(self):
        DialogoHistorialPedidos(self).exec()


class DialogoHistorialPedidos(QDialog):
    """Lo que ya trajimos: cuántos clientes lo habían pedido, quién apretó TRAJIMOS
    y cuándo, el último primero."""

    COLUMNAS = ["Producto", "Clientes", "Lo pidieron desde", "Trajimos", "Lo marcó"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{TITULO} · Historial")
        self.resize(900, 560)
        cabecera = cabecera_oscura("📋", "Historial", "Lo que ya trajimos, el último primero")
        self.tabla = crear_tabla(self.COLUMNAS, estirar=0, por_filas=True, una_sola=True)
        for columna, ancho in ((1, 90), (2, 150), (3, 150), (4, 120)):
            self.tabla.setColumnWidth(columna, ancho)
        self.tabla.horizontalHeaderItem(1).setTextAlignment(Qt.AlignCenter)
        traidos = pedidos_clientes_repo.listar_historial()
        self.tabla.setRowCount(len(traidos))
        for fila, pedido in enumerate(traidos):
            textos = (pedido["producto"], str(pedido["clientes"]), formato_fecha_hora(pedido["primera_vez"]),
                      formato_fecha_hora(pedido["fecha_traido"]), pedido["traido_por_nombre"] or "—")
            for columna, texto in enumerate(textos):
                celda = QTableWidgetItem(texto)
                if columna == 1:
                    celda.setTextAlignment(Qt.AlignCenter)
                self.tabla.setItem(fila, columna, celda)
        # Sin celda actual: si no, la primera se dibuja con el recuadro del foco.
        self.tabla.setCurrentCell(-1, -1)

        barra = QHBoxLayout()
        barra.addStretch()
        barra.addWidget(tecla("CERRAR", self.close, "teclaRoja"))
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(cabecera)
        layout.addWidget(panel_de_tabla(self.tabla), 1)
        layout.addLayout(barra)
        self.setLayout(layout)
        sin_boton_por_defecto(self)

    def se_puede_cerrar_sola(self) -> bool:
        """Solo es una lista, como la ventana de la que sale: el cierre forzoso la
        cierra y sigue con la de abajo (no se pierde nada)."""
        return True
