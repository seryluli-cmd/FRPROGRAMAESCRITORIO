"""
ranking_rotacion_window.py
============================
RANKING DE ROTACIÓN (pedido del dueño, 2026-11-04): el séptimo acceso del inicio,
debajo de TAREAS DEL TURNO. Dos pestañas:

- POR COMPRA (la idea del dueño, la que abre primero): cuánto tarda en venderse cada
  compra, desde que entra la mercadería hasta que sale la última unidad, en promedio
  de las últimas compras que ya se vendieron enteras. Del más rápido al más lento.
- POR PERÍODO: cuántas unidades por día se vendieron en los últimos 7, 30 o 90 días
  y para cuántos días alcanza el stock a ese ritmo.

Las cuentas son de repositories/rotacion_repo.py y de dominio.py; acá solo se
muestran. La abre quien tiene el permiso de Reportes (el Admin siempre): lo
pregunta MainWindow antes de abrirla. También se abre desde otra PC (solo mira).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget

import dominio
from repositories import rotacion_repo
from ui import imprimir
from ui.piezas_ventana import (
    agregar_indicador, cabecera_oscura, fila_de_filtros, panel_de_tabla, pie_de_ventana, poner_indicador, tecla,
)
from ui.utils import crear_tabla, hoy_del_local, manejar_errores, sin_boton_por_defecto

TITULO = "Ranking de Rotación"
PESTAÑA_COMPRA, PESTAÑA_PERIODO = 0, 1
NOMBRES_DE_PESTAÑA = {PESTAÑA_COMPRA: "Por compra", PESTAÑA_PERIODO: "Por período"}
COLUMNA_PUESTO = 0
COLUMNA_ARTICULO = 1

COLUMNAS_COMPRA = ["#", "Artículo", "Rubro", "Tarda en venderse", "Compras medidas", "Última compra",
                   "De la última quedan"]
COLUMNA_TARDA = 3
A_LA_DERECHA_COMPRA = (0, 3, 4)

# POR PERÍODO: los períodos que se pueden elegir, en días contando hoy. Arranca en
# 30: una semana sola se mueve mucho con un día raro, y tres meses tardan en mostrar
# que algo empezó a venderse más.
PERIODOS = (7, 30, 90)
PERIODO_INICIAL = 30
COLUMNAS_PERIODO = ["#", "Artículo", "Rubro", "Vendidas", "Por día", "Stock", "Alcanza para"]
COLUMNA_ALCANZA = 6
A_LA_DERECHA_PERIODO = (0, 3, 4, 5, 6)

_SUBTITULO_COMPRA = (
    f"Cuánto tarda en venderse cada compra (promedio de las últimas {dominio.COMPRAS_PARA_PROMEDIAR}): "
    "del más rápido al más lento"
)
_PIE_COMPRA = (
    "Se cuenta desde que entra la compra hasta que se vende su última unidad  ·  "
    "Lo que ya estaba en el estante sale primero  ·  "
    f"Promedio de las últimas {dominio.COMPRAS_PARA_PROMEDIAR} compras que se vendieron enteras  ·  "
    "No cuenta ventas anuladas ni impresiones"
)
_PIE_PERIODO = (
    "Por día = vendidas ÷ días del período (hoy cuenta hasta ahora)  ·  "
    "Alcanza para = cuántos días dura el stock a ese ritmo  ·  "
    "No cuenta ventas anuladas ni impresiones  ·  "
    f"En rojo, lo que se acaba en menos de {dominio.DIAS_PARA_AVISAR_ROTACION} días"
)


def _desde_y_hasta(dias: int) -> tuple:
    """Las fechas ("YYYY-MM-DD") de los últimos `dias` días del local, hoy incluido."""
    hasta = hoy_del_local()
    desde = hasta.addDays(-(dias - 1))
    return desde.toString("yyyy-MM-dd"), hasta.toString("yyyy-MM-dd")


def _fecha(texto_iso: str) -> str:
    """ "2026-11-04" (o con la hora después) -> "04/11/2026"."""
    anio, mes, dia = texto_iso[:10].split("-")
    return f"{dia}/{mes}/{anio}"


def _valores_compra(renglon) -> tuple:
    """Lo que se ve en cada columna de un renglón POR COMPRA (en la grilla y en la
    hoja impresa)."""
    sin_compras = renglon["ultima_fecha"] is None
    if sin_compras:
        ultima = queda = ""
    else:
        # Sin el año, para que entre en la columna (el día exacto está en Movimientos del artículo).
        ultima = f"{_fecha(renglon['ultima_fecha'])[:5]} · {dominio.texto_cantidad(renglon['ultima_cantidad'])} u."
        if renglon["ultima_quedan"] == 0:
            queda = "Se vendió toda"
        else:
            hace = dominio.texto_tiempo_de_venta(renglon["ultima_hace"]).lower()
            queda = (f"{dominio.texto_cantidad(renglon['ultima_quedan'])} de "
                     f"{dominio.texto_cantidad(renglon['ultima_cantidad'])} · hace {hace}")
    return (
        "" if renglon["puesto"] is None else str(renglon["puesto"]),
        renglon["descripcion"],
        renglon["rubro"],
        dominio.texto_tiempo_de_venta(renglon["dias"], renglon["compras"]),
        "" if sin_compras else str(renglon["compras_medidas"]),
        ultima,
        queda,
    )


def _valores_periodo(renglon) -> tuple:
    """Lo que se ve en cada columna de un renglón POR PERÍODO (en la grilla y en la
    hoja impresa)."""
    return (
        "" if renglon["puesto"] is None else str(renglon["puesto"]),
        renglon["descripcion"],
        renglon["rubro"],
        dominio.texto_cantidad(renglon["vendidas"]),
        dominio.texto_por_dia(renglon["por_dia"]),
        dominio.texto_cantidad(renglon["stock"]),
        dominio.texto_alcanza(renglon["alcanza"]),
    )


def _llenar(tabla, filas, a_la_derecha, rojo=lambda _columna, _renglon: False):
    """Vuelve a llenar `tabla` con `filas` ((valores, renglón)); `rojo(columna,
    renglón)` dice qué celda va en rojo."""
    tabla.setRowCount(len(filas))
    for fila, (valores, renglon) in enumerate(filas):
        for columna, texto in enumerate(valores):
            celda = QTableWidgetItem(texto)
            if columna in a_la_derecha:
                celda.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if rojo(columna, renglon):
                celda.setForeground(Qt.red)
            tabla.setItem(fila, columna, celda)


def _tabla(columnas, a_la_derecha, anchos):
    tabla = crear_tabla(columnas, estirar=COLUMNA_ARTICULO, por_filas=True)
    for columna in a_la_derecha:
        tabla.horizontalHeaderItem(columna).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    for columna, ancho in anchos.items():
        tabla.setColumnWidth(columna, ancho)
    return tabla


class VentanaRankingRotacion(QDialog):
    """El ranking, con la maqueta B de ui/piezas_ventana.py como Control de Stock:
    la cabecera oscura con los números de la pestaña a la vista, las teclas, las dos
    pestañas con su grilla y la ayuda abajo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._compras = []
        self._periodo = []
        self._subtitulo_periodo = ""
        self.setWindowTitle(TITULO)
        # Ancha para las siete columnas de POR COMPRA (la pantalla del mostrador es de 1920).
        self.resize(1260, 760)
        self._armar_interfaz()
        self._cargar_compras()
        self._cargar_periodo(PERIODO_INICIAL)
        self._mostrar_la_pestaña()

    def _armar_interfaz(self):
        self.cabecera = cabecera_oscura("📈", TITULO, "")
        self.indicador_medidos = agregar_indicador(self.cabecera, "Medidos")
        self.indicador_sin_medir = agregar_indicador(self.cabecera, "Sin vender entera")
        self.indicador_articulos = agregar_indicador(self.cabecera, "Artículos")
        self.indicador_pronto = agregar_indicador(
            self.cabecera, f"Se acaban en {dominio.DIAS_PARA_AVISAR_ROTACION} días")
        self.indicador_quietos = agregar_indicador(self.cabecera, "Sin ventas")
        # Arriba se ven solo los números de la pestaña elegida.
        self._indicadores = {
            PESTAÑA_COMPRA: (self.indicador_medidos, self.indicador_sin_medir),
            PESTAÑA_PERIODO: (self.indicador_articulos, self.indicador_pronto, self.indicador_quietos),
        }

        self.boton_imprimir = tecla("🖨  IMPRIMIR", self._imprimir, "teclaAzul")
        self.boton_imprimir.setToolTip("Abre la vista previa para imprimir la pestaña a la vista (o guardarla en PDF).")
        barra = QHBoxLayout()
        barra.setSpacing(8)
        barra.addStretch()
        barra.addWidget(self.boton_imprimir)
        barra.addWidget(tecla("CERRAR", self.close))

        self.pestañas = QTabWidget()
        self.pestañas.addTab(self._pagina_por_compra(), NOMBRES_DE_PESTAÑA[PESTAÑA_COMPRA])
        self.pestañas.addTab(self._pagina_por_periodo(), NOMBRES_DE_PESTAÑA[PESTAÑA_PERIODO])
        self.pestañas.currentChanged.connect(self._mostrar_la_pestaña)
        self.pie = pie_de_ventana("")

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(self.cabecera)
        layout.addLayout(barra)
        layout.addWidget(self.pestañas, 1)
        layout.addWidget(self.pie)
        self.setLayout(layout)
        sin_boton_por_defecto(self)

    def _pagina_por_compra(self) -> QWidget:
        # Cada columna con su ancho (los títulos van en mayúscula y espaciados): con el
        # de fábrica, "COMPRAS MEDIDAS", la última compra y los rubros largos se cortaban.
        # El puesto, angosto, para dejarle lugar al artículo.
        self.tabla_compras = _tabla(COLUMNAS_COMPRA, A_LA_DERECHA_COMPRA, {
            COLUMNA_PUESTO: 56, 2: 185, COLUMNA_TARDA: 170, 4: 180, 5: 150, 6: 220,
        })
        pagina = QWidget()
        capa = QVBoxLayout(pagina)
        capa.setContentsMargins(0, 10, 0, 0)
        capa.addWidget(panel_de_tabla(self.tabla_compras), 1)
        return pagina

    def _pagina_por_periodo(self) -> QWidget:
        self.periodos = fila_de_filtros(
            [(f"Últimos {dias} días", dias) for dias in PERIODOS], self._cargar_periodo, todos=None)
        self.periodos.pastillas[PERIODOS.index(PERIODO_INICIAL)].setChecked(True)
        # Ancha para "SIN VENTAS" y el título en mayúscula de la hoja de estilos; el
        # puesto, angosta: con el ancho de fábrica se comía lugar del artículo.
        self.tabla_periodo = _tabla(COLUMNAS_PERIODO, A_LA_DERECHA_PERIODO,
                                    {COLUMNA_PUESTO: 56, COLUMNA_ALCANZA: 150})
        pagina = QWidget()
        capa = QVBoxLayout(pagina)
        capa.setContentsMargins(0, 10, 0, 0)
        capa.setSpacing(10)
        capa.addWidget(self.periodos)
        capa.addWidget(panel_de_tabla(self.tabla_periodo), 1)
        return pagina

    @manejar_errores
    def _cargar_compras(self):
        self._compras = rotacion_repo.ranking_por_compras()
        medidos = sum(renglon["puesto"] is not None for renglon in self._compras)
        sin_medir = sum(renglon["puesto"] is None and renglon["compras"] > 0 for renglon in self._compras)
        poner_indicador(self.indicador_medidos, str(medidos))
        poner_indicador(self.indicador_sin_medir, str(sin_medir))
        _llenar(self.tabla_compras, [(_valores_compra(r), r) for r in self._compras], A_LA_DERECHA_COMPRA)

    @manejar_errores
    def _cargar_periodo(self, dias: int):
        desde, hasta = _desde_y_hasta(dias)
        self._periodo = rotacion_repo.ranking_de_rotacion(desde, hasta)
        self._subtitulo_periodo = (
            f"Últimos {dias} días, del {_fecha(desde)} al {_fecha(hasta)}: del que más se vende al que menos"
        )
        pronto = sum(dominio.se_acaba_pronto(renglon["alcanza"]) for renglon in self._periodo)
        quietos = sum(renglon["puesto"] is None for renglon in self._periodo)
        poner_indicador(self.indicador_articulos, str(len(self._periodo)))
        poner_indicador(self.indicador_pronto, str(pronto), alerta=pronto > 0)
        poner_indicador(self.indicador_quietos, str(quietos))
        _llenar(
            self.tabla_periodo, [(_valores_periodo(r), r) for r in self._periodo], A_LA_DERECHA_PERIODO,
            rojo=lambda columna, r: columna == COLUMNA_ALCANZA and dominio.se_acaba_pronto(r["alcanza"]),
        )
        self._mostrar_la_pestaña()

    def _mostrar_la_pestaña(self, *_):
        """La cabecera, los números, la ayuda y IMPRIMIR de la pestaña a la vista."""
        pestaña = self.pestañas.currentIndex()
        self.cabecera.detalle.setText(_SUBTITULO_COMPRA if pestaña == PESTAÑA_COMPRA else self._subtitulo_periodo)
        for cual, indicadores in self._indicadores.items():
            for indicador in indicadores:
                indicador.setVisible(cual == pestaña)
        self.pie.setText(_PIE_COMPRA if pestaña == PESTAÑA_COMPRA else _PIE_PERIODO)
        self.boton_imprimir.setEnabled(bool(self._compras if pestaña == PESTAÑA_COMPRA else self._periodo))

    def html_para_imprimir(self, impreso=None) -> str:
        """La hoja impresa de la pestaña a la vista."""
        if self.pestañas.currentIndex() == PESTAÑA_COMPRA:
            columnas, a_la_derecha, subtitulo = COLUMNAS_COMPRA, A_LA_DERECHA_COMPRA, _SUBTITULO_COMPRA
            filas = [(_valores_compra(renglon), False) for renglon in self._compras]
        else:
            columnas, a_la_derecha, subtitulo = COLUMNAS_PERIODO, A_LA_DERECHA_PERIODO, self._subtitulo_periodo
            filas = [(_valores_periodo(renglon), False) for renglon in self._periodo]
        titulo = f"{TITULO} · {NOMBRES_DE_PESTAÑA[self.pestañas.currentIndex()]}"
        return imprimir.html_del_listado(titulo, subtitulo, columnas, filas, a_la_derecha=a_la_derecha,
                                         impreso=impreso)

    def _imprimir(self):
        imprimir.vista_previa(self, self.html_para_imprimir(), TITULO)
