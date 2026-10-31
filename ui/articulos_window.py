"""
articulos_window.py
=====================
Pantalla de Artículos: la grilla con todos los productos, y el cuadro de
alta/edición. La usa el Admin o una Empleada con `permiso_articulos`.
Importante: el alta/edición NUNCA toca el stock — el stock se carga desde
Compras (ver compras_window.py) y solo se corrige a mano con ORDENAR Stock
(ordenar_stock_window.py: solo Admin, con contraseña).
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidgetItem, QLineEdit, QLabel,
    QComboBox, QSpinBox, QFormLayout, QInputDialog, QFrame, QGridLayout,
)
from PySide6.QtCore import Qt, QDate

import dominio
from repositories import articulos_repo
from ui.articulos_tabla import (
    COLUMNA_CODIGO, COLUMNA_PRECIO_COMPRA, COLUMNA_PRECIO_VENTA, COLUMNA_RUBRO, COLUMNA_STOCK,
    COLUMNA_STOCK_MINIMO, crear_tabla_de_articulos, llenar_tabla_de_articulos,
)
from ui.dibujos_tabla import DelegadoEtiqueta, DelegadoStock
from ui.ordenar_stock_window import OrdenarStockWindow
from ui.piezas_ventana import (
    TONO_AZUL, agregar_indicador, agregar_pastilla, buscador, cabecera_oscura, fila_de_filtros,
    marcar_solo_admin, panel_blanco, panel_de_tabla, pie_de_ventana, poner_indicador, tecla,
)
from ui.utils import (
    CampoPesos, CampoPorcentaje, mostrar_error, mostrar_aviso, confirmar, manejar_errores,
    encadenar_enter, armar_filtro_por_fechas, sin_boton_por_defecto, fila_guardar_cancelar,
    crear_tabla, rango_de_fechas, formato_pesos, formato_fecha_hora,
)


class ArticulosWindow(QDialog):
    """Grilla de artículos con buscador; desde acá se abre el alta/edición,
    los movimientos de stock, la gestión de rubros y, para el Admin, la de
    marcas y ORDENAR Stock (`usuario` es quien la abrió; sin él no aparecen
    esos dos botones).

    Con la maqueta B que eligió el dueño el 2026-10-30 (ui/piezas_ventana.py): la
    cabecera oscura con los números del catálogo, las teclas, el buscador con los
    filtros por rubro y la grilla con el rubro en una etiqueta de color y el stock
    con su barrita (ui/dibujos_tabla.py). Es el modelo de las demás listas."""

    def __init__(self, parent=None, usuario=None):
        super().__init__(parent)
        self.usuario = usuario
        self.setWindowTitle("Artículos")
        self.resize(1180, 720)
        self._rubro_elegido = None
        self._armar_interfaz()
        self._cargar_grilla()

    def _armar_interfaz(self):
        cabecera = cabecera_oscura("📦", "Artículos", "Precios, stock, rubros y marcas")
        self.indicador_articulos = agregar_indicador(cabecera, "Artículos")
        self.indicador_rubros = agregar_indicador(cabecera, "Rubros")
        self.indicador_bajo_minimo = agregar_indicador(cabecera, "Bajo el mínimo")
        self.indicador_valor = agregar_indicador(cabecera, "Valor del stock")

        barra_botones = QHBoxLayout()
        barra_botones.setSpacing(8)
        self.boton_nuevo = tecla("＋  NUEVO", self._nuevo_articulo, "teclaAzul")
        self.boton_modificar = tecla("✎  MODIFICAR", self._modificar_articulo)
        self.boton_movimientos = tecla("⇄  MOVIMIENTOS", self._ver_movimientos)
        self.boton_rubros = tecla("▤  RUBROS", self._gestionar_rubros)
        self.boton_marcas = tecla("◆  MARCAS", self._gestionar_marcas)
        self.boton_ordenar_stock = tecla("⚙  ORDENAR STOCK", self._ordenar_stock)
        self.boton_borrar = tecla("✕  BORRAR", self._borrar_articulo, "teclaRoja")
        self.boton_salir = tecla("SALIR", self.close)
        for boton in (self.boton_nuevo, self.boton_modificar, self.boton_movimientos, self.boton_rubros,
                      self.boton_marcas, self.boton_ordenar_stock, self.boton_borrar):
            barra_botones.addWidget(boton)
        barra_botones.addStretch()
        barra_botones.addWidget(self.boton_salir)
        # Solo lo ve un Admin (pedido del dueño, 2026-10-20); una empleada con
        # permiso de Artículos no. El repo lo vuelve a exigir en cada cambio.
        self.boton_ordenar_stock.setVisible(dominio.es_admin(self.usuario))
        # Corregir las marcas, también solo el Admin (pedido del dueño, 2026-10-23).
        self.boton_marcas.setVisible(dominio.es_admin(self.usuario))
        marcar_solo_admin(self.boton_ordenar_stock)
        marcar_solo_admin(self.boton_marcas)

        self.campo_buscar = buscador("Buscar por código o descripción...")
        self.campo_buscar.setMinimumWidth(380)
        self.campo_buscar.textChanged.connect(self._cargar_grilla)
        self.fila_buscar = QHBoxLayout()
        self.fila_buscar.setSpacing(12)
        self.fila_buscar.addWidget(self.campo_buscar)

        self.tabla = crear_tabla_de_articulos()
        self.tabla.doubleClicked.connect(self._modificar_articulo)
        # El rubro en una etiqueta de color y el stock con su barrita: los dibuja la
        # celda, que sigue teniendo su texto (ordenar por columna sigue andando).
        self.etiqueta_rubro = DelegadoEtiqueta(self.tabla)
        self.tabla.setItemDelegateForColumn(COLUMNA_RUBRO, self.etiqueta_rubro)
        self.tabla.setItemDelegateForColumn(COLUMNA_STOCK, DelegadoStock(COLUMNA_STOCK_MINIMO, self.tabla))
        self.tabla.setColumnWidth(COLUMNA_RUBRO, 170)
        self.tabla.setColumnWidth(COLUMNA_STOCK, 150)
        for columna in (COLUMNA_PRECIO_VENTA, COLUMNA_PRECIO_COMPRA):
            self.tabla.setColumnWidth(columna, 125)
        self.filtros = None
        self._armar_filtros()

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(cabecera)
        layout.addLayout(barra_botones)
        layout.addLayout(self.fila_buscar)
        layout.addWidget(panel_de_tabla(self.tabla), 1)
        layout.addWidget(pie_de_ventana(
            "Doble clic en un artículo para modificarlo  ·  El stock en rojo quedó por debajo del mínimo  ·  "
            "Las teclas con borde punteado las ve solo el Administrador"))
        self.setLayout(layout)
        sin_boton_por_defecto(self)

    def _armar_filtros(self):
        """Las pastillas de los rubros, al lado del buscador. Se vuelven a armar
        después de Gestionar Rubros (puede haber uno nuevo o uno renombrado)."""
        if self.filtros is not None:
            self.fila_buscar.removeWidget(self.filtros)
            self.filtros.deleteLater()
        nombres = [rubro["nombre"] for rubro in articulos_repo.listar_rubros()]
        if self._rubro_elegido not in nombres:
            self._rubro_elegido = None
        self.filtros = fila_de_filtros(nombres, self._elegir_rubro)
        for pastilla in self.filtros.pastillas:
            pastilla.setChecked(pastilla.text() == (self._rubro_elegido or "Todos").upper())
        self.fila_buscar.addWidget(self.filtros, 1)
        self.etiqueta_rubro.colores_en_orden(nombres)
        poner_indicador(self.indicador_rubros, str(len(nombres)))

    def _elegir_rubro(self, rubro):
        self._rubro_elegido = rubro
        self._cargar_grilla()

    @manejar_errores
    def _cargar_grilla(self, _=None):
        # El "_=None" no se usa: absorbe el texto que manda `textChanged`
        # (ver ControlCierresWindow._ver_detalle en control_cierres_window.py, que
        # explica por qué hace falta con @manejar_errores).
        texto = self.campo_buscar.text().strip()
        articulos = articulos_repo.listar_articulos(texto)
        if self._rubro_elegido is not None:
            articulos = [a for a in articulos if a["rubro"] == self._rubro_elegido]
        llenar_tabla_de_articulos(self.tabla, articulos)
        # Los números de arriba son de todo el catálogo, no de lo que se está buscando.
        numeros = dominio.numeros_de_los_articulos(articulos_repo.listar_articulos())
        poner_indicador(self.indicador_articulos, str(numeros["cantidad"]))
        poner_indicador(self.indicador_bajo_minimo, str(numeros["bajo_el_minimo"]),
                        alerta=numeros["bajo_el_minimo"] > 0)
        poner_indicador(self.indicador_valor, formato_pesos(numeros["valor_del_stock"]))

    def _codigo_seleccionado(self):
        fila = self.tabla.currentRow()
        if fila < 0:
            mostrar_aviso(self, "Nada seleccionado", "Elegí primero un artículo de la lista.")
            return None
        return self.tabla.item(fila, COLUMNA_CODIGO).text()

    def _nuevo_articulo(self):
        dialogo = DialogoArticulo(self)
        if dialogo.exec():
            self._cargar_grilla()

    def _modificar_articulo(self):
        codigo = self._codigo_seleccionado()
        if not codigo:
            return
        dialogo = DialogoArticulo(self, codigo)
        if dialogo.exec():
            self._cargar_grilla()

    @manejar_errores
    def _borrar_articulo(self):
        codigo = self._codigo_seleccionado()
        if not codigo:
            return
        if confirmar(self, "Confirmar borrado", f"¿Borrar el artículo {codigo}? Esta acción no se puede deshacer."):
            # Si el artículo ya tiene compras o ventas registradas,
            # articulos_repo.borrar_articulo tira un ValueError con un
            # mensaje claro en vez de dejar pasar el error de SQLite;
            # el decorador @manejar_errores se encarga de mostrarlo.
            articulos_repo.borrar_articulo(codigo)
            self._cargar_grilla()

    def _ver_movimientos(self):
        codigo = self._codigo_seleccionado()
        if not codigo:
            return
        dialogo = DialogoMovimientos(self, codigo)
        dialogo.exec()

    def _gestionar_rubros(self):
        DialogoGestionRubros(self).exec()
        self._armar_filtros()
        self._cargar_grilla()   # la grilla muestra el nombre del rubro

    def _gestionar_marcas(self):
        DialogoGestionMarcas(self, self.usuario["id"]).exec()
        self._cargar_grilla()   # la grilla muestra el nombre de la marca

    @manejar_errores
    def _ordenar_stock(self):
        clave, aceptado = QInputDialog.getText(
            self, "ORDENAR Stock", "Contraseña de ORDENAR Stock:", QLineEdit.Password
        )
        if not aceptado:
            return
        # Una contraseña equivocada (o un usuario que dejó de ser Admin) levanta
        # PermissionError y @manejar_errores lo muestra: la pantalla no se abre.
        articulos_repo.comprobar_clave_para_ordenar_stock(self.usuario["id"], clave)
        OrdenarStockWindow(self, self.usuario["id"], clave).exec()
        self._cargar_grilla()


class DialogoArticulo(QDialog):
    """Cuadro de alta o edición de un artículo (según si se le pasa un
    código existente o no)."""

    def __init__(self, parent, codigo_existente: str = None):
        super().__init__(parent)
        self.codigo_existente = codigo_existente
        self.setWindowTitle("Modificación de Artículos" if codigo_existente else "Nuevo Artículo")
        self.resize(700, 600)
        self._armar_interfaz()
        if codigo_existente:
            self._cargar_datos(codigo_existente)
        self._actualizar_ayuda_de_precios()

    def _armar_interfaz(self):
        self.campo_codigo = QLineEdit()
        if self.codigo_existente:
            self.campo_codigo.setText(self.codigo_existente)
            self.campo_codigo.setReadOnly(True)  # no se cambia el código de un artículo ya creado

        self.campo_descripcion = QLineEdit()

        self.combo_marca = QComboBox()
        self.combo_marca.setEditable(True)
        for marca in articulos_repo.listar_marcas():
            self.combo_marca.addItem(marca["nombre"], marca["id"])

        # A diferencia de Marca, Rubro NO es editable a mano: solo se puede
        # elegir de la lista que administra el Admin (ver "Gestionar
        # Rubros"), para que no queden rubros mal escritos o duplicados
        # por typos ("Bebidas" vs "BEBIDAS" vs "Bebida").
        self.combo_rubro = QComboBox()
        self.combo_rubro.addItem("(Sin rubro)", None)
        for rubro in articulos_repo.listar_rubros():
            self.combo_rubro.addItem(rubro["nombre"], rubro["id"])

        # Calculadora de precios, la maqueta D que eligió el dueño el 2026-10-31:
        # COSTO + GANANCIA % = PRECIO DE VENTA, cada casillero con su "＝ Calcular",
        # que lo saca de los otros dos. Así sirve para las tres cosas: con el costo
        # y el % sale la venta; con la venta y el % se estima el costo (cuando se
        # perdió la factura y se sabe el precio de otro local); y con el costo y la
        # venta sale el % que se le está ganando (Impresiones: $ 20 y $ 200, 900%).
        # Es a botón, no en vivo: así no pisa un precio que ya se cargó a mano. El %
        # arranca en dominio.MARGEN_POR_DEFECTO (80%, pedido del dueño); la línea de
        # abajo sí va en vivo, con lo que se gana de verdad con los dos precios.
        self.spin_precio_compra = CampoPesos()
        self.campo_porcentaje = CampoPorcentaje()
        self.campo_porcentaje.setValue(dominio.MARGEN_POR_DEFECTO)
        self.spin_precio_venta = CampoPesos()
        self.boton_calcular_costo = tecla("＝  Calcular", self._calcular_costo_desde_venta)
        self.boton_calcular_porcentaje = tecla("＝  Calcular", self._calcular_porcentaje)
        self.boton_calcular_venta = tecla("＝  Calcular", self._calcular_venta_desde_costo)
        self.ayuda_de_precios = QLabel()
        self.ayuda_de_precios.setObjectName("ayudaCalculadora")
        self.spin_precio_compra.valueChanged.connect(self._actualizar_ayuda_de_precios)
        self.spin_precio_venta.valueChanged.connect(self._actualizar_ayuda_de_precios)

        self.spin_stock_minimo = QSpinBox()
        self.spin_stock_minimo.setMaximum(999_999)

        self.etiqueta_stock = QLabel("(el stock se carga desde Compras)")
        self.etiqueta_stock.setStyleSheet("color: gray; font-style: italic;")

        # La pistola lectora escribe el código y manda un Enter sola. Ese
        # Enter pasa el foco al siguiente campo, como si se apretara Tab,
        # para seguir cargando el artículo sin tocar el mouse — encadenado
        # por todo el formulario, terminando en Guardar (ver encadenar_enter).
        encadenar_enter(
            self.campo_codigo, self.campo_descripcion, self.combo_marca, self.combo_rubro,
            self.spin_precio_compra, self.campo_porcentaje, self.spin_precio_venta, self.spin_stock_minimo,
            accion_final=self._guardar,
        )

        # Maqueta B (2026-10-30): la cabecera oscura y el formulario en un panel blanco.
        cabecera = cabecera_oscura(
            "✎" if self.codigo_existente else "＋",
            "Modificar artículo" if self.codigo_existente else "Nuevo artículo",
            f"Código {self.codigo_existente}" if self.codigo_existente
            else "Escaneá el código y completá los datos: el stock se carga desde Compras",
        )
        panel, capa_panel = panel_blanco()
        formulario = QFormLayout()
        formulario.setVerticalSpacing(10)
        formulario.addRow("Código (de barras):", self.campo_codigo)
        formulario.addRow("Descripción:", self.campo_descripcion)
        formulario.addRow("Marca:", self.combo_marca)
        formulario.addRow("Rubro:", self.combo_rubro)
        formulario.addRow("Precios:", self._armar_calculadora())
        formulario.addRow("Stock Mínimo:", self.spin_stock_minimo)
        formulario.addRow("Stock actual:", self.etiqueta_stock)
        capa_panel.addLayout(formulario)

        botones = fila_guardar_cancelar(self, self._guardar)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(12)
        layout.addWidget(cabecera)
        layout.addWidget(panel)
        layout.addStretch()
        layout.addLayout(botones)
        self.setLayout(layout)
        sin_boton_por_defecto(self)

    @manejar_errores
    def _cargar_datos(self, codigo):
        articulo = articulos_repo.buscar_por_codigo(codigo)
        if articulo is None:
            return
        self.campo_descripcion.setText(articulo["descripcion"])
        if articulo["marca"]:
            self.combo_marca.setCurrentText(articulo["marca"])
        indice_rubro = self.combo_rubro.findData(articulo["rubro_id"])
        self.combo_rubro.setCurrentIndex(indice_rubro if indice_rubro >= 0 else 0)
        self.spin_precio_venta.setValue(articulo["precio_venta"])
        self.spin_precio_compra.setValue(articulo["precio_compra"])
        self.spin_stock_minimo.setValue(articulo["stock_minimo"])
        self.etiqueta_stock.setText(str(articulo["stock"]))
        bajo = dominio.bajo_el_minimo(articulo["stock"], articulo["stock_minimo"])
        self.etiqueta_stock.setStyleSheet("color: red;" if bajo else "")

    def _armar_calculadora(self) -> QFrame:
        """COSTO + GANANCIA % = PRECIO DE VENTA, en tres casilleros con su
        "＝ Calcular" debajo, y la ayuda en vivo abajo de todo."""
        calculadora = QFrame()
        calculadora.setObjectName("calculadoraPrecios")
        grilla = QGridLayout(calculadora)
        grilla.setContentsMargins(12, 10, 12, 12)
        grilla.setHorizontalSpacing(10)
        grilla.setVerticalSpacing(6)
        casilleros = (
            ("COSTO", self.spin_precio_compra, self.boton_calcular_costo),
            ("GANANCIA SOBRE EL COSTO", self.campo_porcentaje, self.boton_calcular_porcentaje),
            ("PRECIO DE VENTA", self.spin_precio_venta, self.boton_calcular_venta),
        )
        for numero, (titulo, campo, boton) in enumerate(casilleros):
            columna = numero * 2
            etiqueta = QLabel(titulo)
            etiqueta.setObjectName("tituloCalculadora")
            grilla.addWidget(etiqueta, 0, columna)
            grilla.addWidget(campo, 1, columna)
            grilla.addWidget(boton, 2, columna)
            grilla.setColumnStretch(columna, 1)
            if numero < len(casilleros) - 1:
                signo = QLabel("＋" if numero == 0 else "＝")
                signo.setObjectName("signoCalculadora")
                signo.setAlignment(Qt.AlignCenter)
                grilla.addWidget(signo, 1, columna + 1)
        grilla.addWidget(self.ayuda_de_precios, 3, 0, 1, 2 * len(casilleros) - 1)
        return calculadora

    def _actualizar_ayuda_de_precios(self):
        """La línea de abajo de la calculadora: qué hay que hacer y, con los dos
        precios cargados, cuánto se gana por unidad y qué parte de la venta es."""
        texto = "Cargá dos y apretá Calcular en el que falta"
        costo, venta = self.spin_precio_compra.value(), self.spin_precio_venta.value()
        cuenta = dominio.ganancia_por_unidad(costo, venta)
        perdida = costo > 0 and venta > 0 and cuenta["ganancia"] < 0
        if perdida:
            texto += f"  ·  ¡Se vende por debajo del costo! Perdés {formato_pesos(-cuenta['ganancia'])} por unidad"
        elif costo > 0 and venta > 0:
            margen = dominio.texto_pesos(cuenta["margen"])[2:]
            texto += f"  ·  Ganás {formato_pesos(cuenta['ganancia'])} por unidad ({margen}% del precio de venta)"
        self.ayuda_de_precios.setText(texto)
        self.ayuda_de_precios.setProperty("alerta", perdida)
        self.ayuda_de_precios.style().unpolish(self.ayuda_de_precios)
        self.ayuda_de_precios.style().polish(self.ayuda_de_precios)

    def _calcular_venta_desde_costo(self):
        costo = self.spin_precio_compra.value()
        porcentaje = self.campo_porcentaje.value()
        self.spin_precio_venta.setValue(dominio.precio_con_margen(costo, porcentaje))

    def _calcular_costo_desde_venta(self):
        venta = self.spin_precio_venta.value()
        porcentaje = self.campo_porcentaje.value()
        self.spin_precio_compra.setValue(dominio.costo_sin_margen(venta, porcentaje))

    def _calcular_porcentaje(self):
        """El % que se le gana con el costo y la venta que ya están cargados."""
        costo, venta = self.spin_precio_compra.value(), self.spin_precio_venta.value()
        porcentaje = dominio.porcentaje_de_ganancia(costo, venta)
        if porcentaje is None:
            mostrar_aviso(self, "Calcular la ganancia", "Primero cargá el costo.")
        elif porcentaje < 0:
            mostrar_aviso(self, "Calcular la ganancia",
                          "El precio de venta es menor que el costo: con ese precio se pierde plata.")
        else:
            self.campo_porcentaje.setValue(porcentaje)

    def _resolver_marca(self):
        texto = self.combo_marca.currentText().strip()
        if not texto:
            return None, None
        indice = self.combo_marca.findText(texto)
        if indice >= 0:
            return self.combo_marca.itemData(indice), None
        return None, texto  # el repo la crea junto con el artículo

    @manejar_errores
    def _guardar(self):
        codigo = self.campo_codigo.text().strip()
        descripcion = self.campo_descripcion.text().strip()

        if not codigo or not descripcion:
            mostrar_error(self, "Faltan datos", "El código y la descripción son obligatorios.")
            return

        marca_id, nombre_marca_nueva = self._resolver_marca()
        rubro_id = self.combo_rubro.currentData()  # ya viene resuelto: no es editable

        if self.codigo_existente:
            articulos_repo.modificar_articulo(
                codigo, descripcion, marca_id, rubro_id,
                self.spin_precio_venta.value(), self.spin_precio_compra.value(),
                self.spin_stock_minimo.value(), nombre_marca_nueva=nombre_marca_nueva,
            )
        else:
            if articulos_repo.buscar_por_codigo(codigo):
                mostrar_error(self, "Código repetido", "Ya existe un artículo con ese código.")
                return
            articulos_repo.crear_articulo(
                codigo, descripcion, marca_id, rubro_id,
                self.spin_precio_venta.value(), self.spin_precio_compra.value(),
                self.spin_stock_minimo.value(), nombre_marca_nueva=nombre_marca_nueva,
            )
        self.accept()


class DialogoMovimientos(QDialog):
    """Historial de Movimientos de stock de un artículo (compras y
    ventas), filtrable por rango de fechas."""

    def __init__(self, parent, codigo: str):
        super().__init__(parent)
        self.codigo = codigo
        self.setWindowTitle(f"Histórico de Movimientos de {codigo}")
        self.resize(700, 560)
        self._armar_interfaz()
        self._buscar()

    def _armar_interfaz(self):
        self.fecha_desde, self.fecha_hasta, filtros = armar_filtro_por_fechas(
            self._buscar, QDate.currentDate().addMonths(-1)
        )

        self.tabla = crear_tabla(["Fecha", "Comprobante", "Nro", "Cantidad"], estirar=0)
        # El tipo de movimiento (compra, venta, ajuste) en una etiqueta de color.
        self.tabla.setItemDelegateForColumn(1, DelegadoEtiqueta(self.tabla))
        self.tabla.setColumnWidth(1, 190)

        # Maqueta B (2026-10-30): cabecera oscura con lo que entró y salió en el rango.
        cabecera = cabecera_oscura("⇄", "Movimientos", f"Compras, ventas y ajustes del artículo {self.codigo}")
        self.indicador_entradas = agregar_indicador(cabecera, "Entró")
        self.indicador_salidas = agregar_indicador(cabecera, "Salió")

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(cabecera)
        layout.addLayout(filtros)
        layout.addWidget(panel_de_tabla(self.tabla), 1)
        layout.addWidget(pie_de_ventana("Las cantidades en rojo son lo que salió del estante"))
        self.setLayout(layout)
        sin_boton_por_defecto(self)

    @manejar_errores
    def _buscar(self):
        desde, hasta = rango_de_fechas(self.fecha_desde, self.fecha_hasta)
        movimientos = articulos_repo.obtener_movimientos(self.codigo, desde, hasta)
        self.tabla.setRowCount(0)
        for movimiento in movimientos:
            fila = self.tabla.rowCount()
            self.tabla.insertRow(fila)
            self.tabla.setItem(fila, 0, QTableWidgetItem(formato_fecha_hora(movimiento["fecha"])))
            self.tabla.setItem(fila, 1, QTableWidgetItem(movimiento["comprobante"]))
            self.tabla.setItem(fila, 2, QTableWidgetItem(str(movimiento["numero"])))
            item_cantidad = QTableWidgetItem(str(movimiento["cantidad"]))
            if movimiento["cantidad"] < 0:
                item_cantidad.setForeground(Qt.red)
            self.tabla.setItem(fila, 3, item_cantidad)
        poner_indicador(self.indicador_entradas, str(sum(m["cantidad"] for m in movimientos if m["cantidad"] > 0)))
        poner_indicador(self.indicador_salidas, str(-sum(m["cantidad"] for m in movimientos if m["cantidad"] < 0)))


class DialogoGestionRubros(QDialog):
    """
    Administración del catálogo de Rubros (se abre desde Artículos, así
    que la ve quien tenga acceso a esa pantalla). Acá es el ÚNICO lugar
    donde se pueden crear, renombrar o borrar rubros — en el alta/edición
    de un artículo, Rubro es un desplegable cerrado que solo permite elegir
    uno de los ya existentes, para que no queden rubros mal escritos o
    duplicados por typos.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gestionar Rubros")
        self.resize(520, 560)
        self._armar_interfaz()
        self._cargar()

    def _armar_interfaz(self):
        self.lista = crear_tabla(["Rubro"], estirar=0, por_filas=True, una_sola=True)
        self.lista.horizontalHeader().setVisible(False)
        self.lista.setItemDelegateForColumn(0, DelegadoEtiqueta(self.lista))

        self.campo_nuevo = QLineEdit()
        self.campo_nuevo.setPlaceholderText("Nombre del rubro nuevo...")
        boton_agregar = tecla("＋  AGREGAR", self._agregar, "teclaAzul")
        encadenar_enter(self.campo_nuevo, accion_final=self._agregar)

        fila_agregar = QHBoxLayout()
        fila_agregar.addWidget(self.campo_nuevo)
        fila_agregar.addWidget(boton_agregar)

        boton_renombrar = tecla("✎  RENOMBRAR", self._renombrar)
        boton_borrar = tecla("✕  BORRAR", self._borrar, "teclaRoja")
        boton_cerrar = tecla("CERRAR", self.close)

        fila_acciones = QHBoxLayout()
        fila_acciones.addWidget(boton_renombrar)
        fila_acciones.addWidget(boton_borrar)
        fila_acciones.addStretch()
        fila_acciones.addWidget(boton_cerrar)

        # Maqueta B (2026-10-30): cabecera oscura con cuántos rubros hay.
        cabecera = cabecera_oscura("▤", "Rubros", "Los únicos que se pueden elegir al cargar un artículo")
        self.indicador_rubros = agregar_indicador(cabecera, "Rubros")

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(cabecera)
        layout.addLayout(fila_agregar)
        layout.addWidget(panel_de_tabla(self.lista), 1)
        layout.addLayout(fila_acciones)
        self.setLayout(layout)
        sin_boton_por_defecto(self)

        self.campo_nuevo.setFocus()

    @manejar_errores
    def _cargar(self):
        self.rubros = articulos_repo.listar_rubros()
        self.lista.setRowCount(0)
        for rubro in self.rubros:
            fila = self.lista.rowCount()
            self.lista.insertRow(fila)
            self.lista.setItem(fila, 0, QTableWidgetItem(rubro["nombre"]))
        # Los mismos colores que en la grilla de Artículos (en el mismo orden).
        self.lista.itemDelegateForColumn(0).colores_en_orden([rubro["nombre"] for rubro in self.rubros])
        poner_indicador(self.indicador_rubros, str(len(self.rubros)))

    def _rubro_seleccionado(self):
        fila = self.lista.currentRow()
        if fila < 0:
            mostrar_error(self, "Nada seleccionado", "Elegí primero un rubro de la lista.")
            return None
        return self.rubros[fila]

    @manejar_errores
    def _agregar(self):
        nombre = self.campo_nuevo.text().strip()
        if not nombre:
            mostrar_error(self, "Falta el nombre", "Escribí el nombre del rubro nuevo.")
            return
        articulos_repo.crear_rubro(nombre)
        self.campo_nuevo.clear()
        self._cargar()
        self.campo_nuevo.setFocus()

    @manejar_errores
    def _renombrar(self):
        rubro = self._rubro_seleccionado()
        if rubro is None:
            return
        nuevo_nombre, aceptado = QInputDialog.getText(
            self, "Renombrar rubro", "Nuevo nombre:", text=rubro["nombre"]
        )
        if not aceptado:
            return
        articulos_repo.renombrar_rubro(rubro["id"], nuevo_nombre)
        self._cargar()

    @manejar_errores
    def _borrar(self):
        rubro = self._rubro_seleccionado()
        if rubro is None:
            return
        if confirmar(self, "Confirmar borrado",
                     f"¿Borrar el rubro '{rubro['nombre']}'? Esta acción no se puede deshacer."):
            articulos_repo.borrar_rubro(rubro["id"])
            self._cargar()


class DialogoGestionMarcas(QDialog):
    """
    Corregir el catálogo de Marcas (pedido del dueño, 2026-10-23): solo el
    Admin, que es el único que ve el botón (y articulos_repo lo vuelve a exigir
    en cada cambio). Las marcas nuevas se siguen pudiendo escribir al cargar un
    artículo; acá se agregan, se renombran, se borran las que no usa nadie y se
    juntan dos que son la misma escrita distinto: al renombrar una con el
    nombre de otra que ya existe, pregunta si juntarlas.
    """

    def __init__(self, parent, usuario_id: int):
        super().__init__(parent)
        self.usuario_id = usuario_id
        self.setWindowTitle("Gestionar Marcas")
        self.resize(560, 620)
        self._armar_interfaz()
        self._cargar()

    def _armar_interfaz(self):
        self.lista = crear_tabla(["Marca", "Artículos"], estirar=0, por_filas=True, una_sola=True)

        self.lista.setColumnWidth(1, 110)

        self.campo_nuevo = QLineEdit()
        self.campo_nuevo.setPlaceholderText("Nombre de la marca nueva...")
        boton_agregar = tecla("＋  AGREGAR", self._agregar, "teclaAzul")
        encadenar_enter(self.campo_nuevo, accion_final=self._agregar)

        fila_agregar = QHBoxLayout()
        fila_agregar.addWidget(self.campo_nuevo)
        fila_agregar.addWidget(boton_agregar)

        self.boton_renombrar = tecla("✎  RENOMBRAR", self._renombrar)
        self.boton_borrar = tecla("✕  BORRAR", self._borrar, "teclaRoja")
        boton_cerrar = tecla("CERRAR", self.close)

        fila_acciones = QHBoxLayout()
        fila_acciones.addWidget(self.boton_renombrar)
        fila_acciones.addWidget(self.boton_borrar)
        fila_acciones.addStretch()
        fila_acciones.addWidget(boton_cerrar)

        # Maqueta B (2026-10-30): cabecera oscura con cuántas marcas hay.
        cabecera = cabecera_oscura("◆", "Marcas", "Solo el Administrador las corrige")
        agregar_pastilla(cabecera, "ADMIN", TONO_AZUL)
        self.indicador_marcas = agregar_indicador(cabecera, "Marcas")

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(cabecera)
        layout.addLayout(fila_agregar)
        layout.addWidget(panel_de_tabla(self.lista), 1)
        layout.addWidget(pie_de_ventana(
            "Si dos son la misma escrita distinto, renombrá una con el nombre de la otra y se juntan"))
        layout.addLayout(fila_acciones)
        self.setLayout(layout)
        sin_boton_por_defecto(self)

        self.campo_nuevo.setFocus()

    @manejar_errores
    def _cargar(self):
        self.marcas = articulos_repo.listar_marcas_con_cantidad()
        self.lista.setRowCount(0)
        for marca in self.marcas:
            fila = self.lista.rowCount()
            self.lista.insertRow(fila)
            self.lista.setItem(fila, 0, QTableWidgetItem(marca["nombre"]))
            cantidad = QTableWidgetItem(str(marca["cantidad"]))
            cantidad.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.lista.setItem(fila, 1, cantidad)
        poner_indicador(self.indicador_marcas, str(len(self.marcas)))

    def _marca_seleccionada(self):
        fila = self.lista.currentRow()
        if fila < 0:
            mostrar_error(self, "Nada seleccionado", "Elegí primero una marca de la lista.")
            return None
        return self.marcas[fila]

    @manejar_errores
    def _agregar(self):
        nombre = self.campo_nuevo.text().strip()
        if not nombre:
            mostrar_error(self, "Falta el nombre", "Escribí el nombre de la marca nueva.")
            return
        articulos_repo.crear_marca(self.usuario_id, nombre)
        self.campo_nuevo.clear()
        self._cargar()
        self.campo_nuevo.setFocus()

    @manejar_errores
    def _renombrar(self):
        marca = self._marca_seleccionada()
        if marca is None:
            return
        nuevo_nombre, aceptado = QInputDialog.getText(
            self, "Renombrar marca", "Nuevo nombre:", text=marca["nombre"]
        )
        nuevo_nombre = nuevo_nombre.strip()
        if not aceptado or nuevo_nombre == marca["nombre"]:
            return
        otra = articulos_repo.buscar_marca_por_nombre(nuevo_nombre)
        if otra is not None and otra["id"] != marca["id"]:
            if confirmar(
                self, "Juntar marcas",
                f"Ya existe la marca '{otra['nombre']}'.\n\n¿Pasar los {marca['cantidad']} artículo(s) "
                f"de '{marca['nombre']}' a '{otra['nombre']}' y borrar '{marca['nombre']}'?",
            ):
                articulos_repo.juntar_marcas(self.usuario_id, marca["id"], otra["id"])
                self._cargar()
            return
        articulos_repo.renombrar_marca(self.usuario_id, marca["id"], nuevo_nombre)
        self._cargar()

    @manejar_errores
    def _borrar(self):
        marca = self._marca_seleccionada()
        if marca is None:
            return
        if confirmar(self, "Confirmar borrado",
                     f"¿Borrar la marca '{marca['nombre']}'? Esta acción no se puede deshacer."):
            articulos_repo.borrar_marca(self.usuario_id, marca["id"])
            self._cargar()
