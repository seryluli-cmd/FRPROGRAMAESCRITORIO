"""
armar_base_de_prueba.py
=========================
Arma una BASE DE PRUEBA con datos inventados (artículos, cuatro empleadas y un
año de ventas con sus cajas y cierres) para mirar las pantallas con contenido,
medir cuánto tardan los reportes con mucho movimiento y probar sin tocar ninguna
base real (pedido del dueño, 2026-10-28).

Pasa por las MISMAS funciones que usa el programa (entrar y abrir o recibir la
caja, vender, cobrar impresiones, anular, cerrar el turno, el cierre forzoso,
comprar, subir precios, contar el sobre), con el reloj puesto en cada momento del
pasado. Lo que queda es lo que habría dejado el programa en el mostrador, no
filas escritas a mano que podrían no cuadrar con las reglas de las cajas.

    python armar_base_de_prueba.py               un año, en data_prueba/
    python armar_base_de_prueba.py --dias 60     dos meses
    python main.py --base data_prueba            abre el programa con esa base

Opciones: --dias (365), --carpeta (data_prueba), --escala (1 = unas 180 ventas
por día; 0.5, la mitad) y --semilla (con la misma sale siempre la misma base).

Usuarios: Administrador, Lucía, Mariana, Carla y Sofía, todos con la clave de
prueba CLAVE_DE_PRUEBA. El envío de cierres a la app de gastos y la entrada
desde otra PC quedan apagados, como en una base nueva, y en una base de prueba
el envío no se puede prender (envio_pwa_repo).

Nunca toca data_fr/: arma solo en una carpeta que no existe, que está vacía o
que ya es una base de prueba (tiene database.ARCHIVO_DE_BASE_DE_PRUEBA), y nunca
en data_fr/ aunque esté vacía. Hay que cerrar FRKiosko antes de armarla.
"""

import argparse
import math
import os
import random
import shutil
import socket
import sys
import time as reloj_de_verdad
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta

import database
import dominio
from repositories import (
    articulos_repo, compras_repo, config_repo, control_cierres_repo, envio_pwa_repo, impresiones_repo,
    relevo_repo, turnos_repo, usuarios_repo, ventas_repo,
)
from turnos import dia_en_que_empezo_el_turno, es_domingo, fin_del_turno, turno_vencimiento, turnos_del_dia

CARPETA_POR_DEFECTO = "data_prueba"
# El candado de instancia única de main.py (PUERTO_INSTANCIA_UNICA; no se importa
# main para no cargar Qt, y tests/test_base_de_prueba.py vigila que sea el mismo):
# con FRKiosko abierto, la base se cambiaría debajo del programa.
PUERTO_DEL_PROGRAMA_ABIERTO = 8908
ARMANDO = "kiosko_armando.db"  # la base nueva, mientras se arma
CLAVE_DE_PRUEBA = "1234"
ADMIN = "Administrador"  # el que crea database._cargar_datos_iniciales

# Qué tan seguido pasa cada cosa (por turno, por venta o por cierre). Las
# pruebas las suben para que aparezcan todas en pocos días.
PROBABILIDADES = {
    "olvido": 0.04,      # quien se va no cierra: la que llega la cierra "en ausencia"
    "forzoso": 0.015,    # nadie la cierra: se cierra sola a los 30 minutos
    "venta_sin_caja": 0.01,  # el Admin vende entre un cierre y la llegada de la siguiente
    "relevo": 0.03,      # a mitad de turno llega otra y RECIBE la caja contando
    "reemplazo": 0.03,   # el turno lo cubre otra empleada que la de siempre
    "impresiones": 0.04,
    "venta_admin": 0.01,
    "anulada": 0.004,
    "cambio_mal_contado": 0.06,
    "sobre_contado": 0.92,
    "sobre_con_faltante": 0.07,
    "sobre_con_sobrante": 0.03,
}

# Ventas de un turno común; los fines de semana se venden más.
_VENTAS_POR_TURNO = {dominio.TURNO_MANANA: 55, dominio.TURNO_TARDE: 80, dominio.TURNO_NOCHE: 35}
_VENTAS_DEL_DOMINGO = {dominio.TURNO_MANANA: 100, dominio.TURNO_NOCHE: 60}
_FIN_DE_SEMANA = {dominio.TURNO_TARDE: 1.2, dominio.TURNO_NOCHE: 1.6}  # viernes y sábado

_MOTIVOS_DE_ANULACION = (
    "Se cobró dos veces", "El cliente se arrepintió", "Se cargó mal el producto",
    "Pagó con otro medio",
)

_RUBROS_NUEVOS = ("CIGARRILLOS", "GOLOSINAS")

# (descripción, marca, rubro, precio de venta al empezar, cuánto se vende)
_CATALOGO = (
    ("Coca-Cola 500 ml", "Coca-Cola", "BEBIDAS", 2200, 30),
    ("Coca-Cola 1,5 L", "Coca-Cola", "BEBIDAS", 4000, 14),
    ("Coca-Cola 2,25 L", "Coca-Cola", "BEBIDAS", 5200, 10),
    ("Coca-Cola Zero 500 ml", "Coca-Cola", "BEBIDAS", 2200, 10),
    ("Sprite 500 ml", "Coca-Cola", "BEBIDAS", 2100, 8),
    ("Fanta 500 ml", "Coca-Cola", "BEBIDAS", 2100, 8),
    ("Pepsi 500 ml", "Pepsi", "BEBIDAS", 2000, 8),
    ("7Up 1,5 L", "Pepsi", "BEBIDAS", 3500, 5),
    ("Agua sin gas 500 ml", "Villavicencio", "BEBIDAS", 1400, 18),
    ("Agua sin gas 2 L", "Villavicencio", "BEBIDAS", 2300, 6),
    ("Agua con gas 500 ml", "Villa del Sur", "BEBIDAS", 1400, 7),
    ("Aquarius pera 500 ml", "Aquarius", "BEBIDAS", 2000, 9),
    ("Gatorade manzana 500 ml", "Gatorade", "BEBIDAS", 2600, 7),
    ("Speed 250 ml", "Speed", "BEBIDAS", 2300, 12),
    ("Monster Energy 473 ml", "Monster", "BEBIDAS", 3800, 6),
    ("Cerveza Quilmes lata 473 ml", "Quilmes", "BEBIDAS", 2400, 14),
    ("Cerveza Brahma lata 473 ml", "Brahma", "BEBIDAS", 2300, 10),
    ("Cerveza Stella Artois lata 473 ml", "Stella Artois", "BEBIDAS", 3000, 6),
    ("Jugo Cepita naranja 1 L", "Cepita", "BEBIDAS", 2800, 5),
    ("Jugo Baggio multifruta 200 ml", "Baggio", "BEBIDAS", 900, 8),
    ("Alfajor Jorgito chocolate", "Jorgito", "GOLOSINAS", 1000, 20),
    ("Alfajor Guaymallén blanco", "Guaymallén", "GOLOSINAS", 500, 16),
    ("Alfajor Havanna chocolate", "Havanna", "GOLOSINAS", 2900, 6),
    ("Alfajor Fantoche triple", "Fantoche", "GOLOSINAS", 1300, 10),
    ("Alfajor Milka Mousse", "Milka", "GOLOSINAS", 1600, 8),
    ("Chocolate Milka 55 g", "Milka", "GOLOSINAS", 2300, 6),
    ("Chocolate Cofler 55 g", "Arcor", "GOLOSINAS", 1900, 6),
    ("Bon o Bon", "Arcor", "GOLOSINAS", 700, 14),
    ("Turrón Arcor", "Arcor", "GOLOSINAS", 500, 10),
    ("Gomitas Mogul 30 g", "Arcor", "GOLOSINAS", 900, 7),
    ("Chupetín Pico Dulce", "Arcor", "GOLOSINAS", 400, 6),
    ("Pastillas Menthoplus", "Arcor", "GOLOSINAS", 900, 9),
    ("Rhodesia", "Terrabusi", "GOLOSINAS", 900, 8),
    ("Tita", "Terrabusi", "GOLOSINAS", 800, 8),
    ("Mantecol 41 g", "Mantecol", "GOLOSINAS", 1500, 5),
    ("Barrita Cereal Mix", "Cereal Mix", "GOLOSINAS", 900, 8),
    ("Chicle Beldent menta", "Beldent", "GOLOSINAS", 1200, 12),
    ("Chicle Bazooka", "Bazooka", "GOLOSINAS", 200, 10),
    ("Pastillas Halls", "Halls", "GOLOSINAS", 1100, 10),
    ("Kinder Sorpresa", "Kinder", "GOLOSINAS", 3500, 3),
    ("Papas Lays clásicas 85 g", "Lays", "KIOSKO", 2900, 9),
    ("Papas Pringles original 124 g", "Pringles", "KIOSKO", 6500, 3),
    ("Doritos queso 77 g", "Doritos", "KIOSKO", 2800, 6),
    ("Palitos salados 100 g", "Pehuamar", "KIOSKO", 1600, 5),
    ("Maní salado 120 g", "Pehuamar", "KIOSKO", 1500, 4),
    ("Galletitas Oreo 118 g", "Oreo", "KIOSKO", 1900, 7),
    ("Galletitas Pepitos 119 g", "Pepitos", "KIOSKO", 1900, 6),
    ("Galletitas Criollitas 100 g", "Criollitas", "KIOSKO", 1300, 5),
    ("Bizcochos de grasa 200 g", "Don Satur", "KIOSKO", 1200, 7),
    ("Bizcochos dulces 200 g", "Don Satur", "KIOSKO", 1200, 6),
    ("Yerba Playadito 500 g", "Playadito", "KIOSKO", 3900, 4),
    ("Leche entera 1 L", "La Serenísima", "KIOSKO", 1900, 5),
    ("Pañuelos descartables", "Elite", "KIOSKO", 800, 5),
    ("Encendedor Bic", "Bic", "KIOSKO", 1800, 8),
    ("Preservativos x3", "Prime", "KIOSKO", 3200, 3),
    ("Pilas AA x2", "Duracell", "KIOSKO", 4200, 2),
    ("Marlboro box 20", "Marlboro", "CIGARRILLOS", 4800, 16),
    ("Marlboro común 20", "Marlboro", "CIGARRILLOS", 4600, 8),
    ("Philip Morris box 20", "Philip Morris", "CIGARRILLOS", 4500, 14),
    ("Camel box 20", "Camel", "CIGARRILLOS", 4500, 6),
    ("Lucky Strike 20", "Lucky Strike", "CIGARRILLOS", 4400, 9),
    ("Chesterfield 20", "Chesterfield", "CIGARRILLOS", 3600, 10),
    ("Red Point 20", "Red Point", "CIGARRILLOS", 3000, 5),
    ("Lavandina 1 L", "Ayudín", "ARTÍCULOS DE LIMPIEZA", 1500, 3),
    ("Detergente 300 ml", "Magistral", "ARTÍCULOS DE LIMPIEZA", 2400, 3),
    ("Papel higiénico x4", "Higienol", "ARTÍCULOS DE LIMPIEZA", 3300, 3),
    ("Esponja de cocina", "Mortimer", "ARTÍCULOS DE LIMPIEZA", 900, 2),
    ("Jabón de tocador", "Dove", "ARTÍCULOS DE LIMPIEZA", 1800, 2),
    ("Lapicera azul", "Bic", "INSUMOS DE PAPELERÍA", 800, 5),
    ("Cuaderno 48 hojas", "Rivadavia", "INSUMOS DE PAPELERÍA", 3800, 2),
    ("Sobre manila A4", "Ledesma", "INSUMOS DE PAPELERÍA", 400, 2),
    ("Cinta adhesiva", "Scotch", "INSUMOS DE PAPELERÍA", 1500, 2),
)
_PRECIO_DE_LAS_IMPRESIONES = 300


# ---------------------------------------------------------------------------
# El reloj y la velocidad
# ---------------------------------------------------------------------------

class _RelojDeLaSimulacion(datetime):
    """Un datetime cuyo now() es el momento que se está simulando. Los repos
    toman la hora con datetime.now() (la venta, el login, la compra, el
    conteo del sobre): con esto la toman del pasado."""
    momento = None

    @classmethod
    def now(cls, tz=None):
        return cls.momento if tz is None else cls.momento.astimezone(tz)


@contextmanager
def _reloj_simulado():
    """Pone el reloj de la simulación en database, errores y los repos (los que
    hacen `from datetime import datetime`), y deja el de verdad al terminar."""
    cambiados = []
    for nombre, modulo in list(sys.modules.items()):
        es_del_programa = nombre in ("database", "errores") or nombre.startswith("repositories.")
        if es_del_programa and getattr(modulo, "datetime", None) is datetime:
            modulo.datetime = _RelojDeLaSimulacion
            cambiados.append(modulo)
    try:
        yield _RelojDeLaSimulacion
    finally:
        for modulo in cambiados:
            modulo.datetime = datetime


@contextmanager
def _conexiones_rapidas():
    """Un año son decenas de miles de ventas, cada una en su transacción. Sin
    esperar a que el disco confirme cada una tarda minutos en vez de horas; si
    se corta, la base a medias es ARMANDO y la anterior sigue sana."""
    original = database.get_connection

    def rapida():
        conexion = original()
        conexion.execute("PRAGMA synchronous = OFF")
        conexion.execute("PRAGMA journal_mode = MEMORY")
        return conexion

    database.get_connection = rapida
    try:
        yield
    finally:
        database.get_connection = original


# ---------------------------------------------------------------------------
# La simulación
# ---------------------------------------------------------------------------

def _redondear(precio: float) -> float:
    """Los precios del kiosko van de 50 en 50."""
    return max(50, round(precio / 50) * 50)


def _codigo_de_barras(rng, usados: set) -> str:
    """Un EAN-13 argentino (779...) inventado, con su dígito verificador."""
    while True:
        cuerpo = "779" + "".join(str(rng.randrange(10)) for _ in range(9))
        suma = sum(int(digito) * (3 if posicion % 2 else 1) for posicion, digito in enumerate(cuerpo))
        codigo = cuerpo + str((10 - suma % 10) % 10)
        if codigo not in usados:
            usados.add(codigo)
            return codigo


class _Simulacion:
    def __init__(self, rng, reloj, escala, avisar):
        self.rng = rng
        self.reloj = reloj
        self.escala = escala
        self.avisar = avisar
        self.ids = {}            # nombre -> id de usuario
        self.articulos = {}      # código -> datos para modificar_articulo
        self.precio = {}         # código -> precio de venta de hoy
        self.costo = {}          # código -> precio de compra de hoy
        self.objetivo = {}       # código -> hasta cuánto stock se compra
        self.codigos, self.pesos = [], []
        self.por_verificar = []  # (cierre_id, monto_a_retirar, cuándo se cerró)

    def _a_las(self, momento: datetime):
        self.reloj.momento = momento

    def _minutos(self, desde: float, hasta: float) -> timedelta:
        return timedelta(minutes=self.rng.uniform(desde, hasta))

    # --- lo que se carga una sola vez ---

    def preparar(self, primer_dia: date):
        self._a_las(datetime.combine(primer_dia, time(5, 0)))
        database.inicializar_base_de_datos()
        self.ids[ADMIN] = usuarios_repo.autenticar_por_nombre(ADMIN, CLAVE_DE_PRUEBA)["id"]
        self.fondo = config_repo.obtener_fondo_cambio()
        for nombre in ("Lucía", "Mariana", "Carla", "Sofía"):
            self.ids[nombre] = usuarios_repo.crear_usuario(nombre, CLAVE_DE_PRUEBA, dominio.ROL_EMPLEADA)
        for rubro in _RUBROS_NUEVOS:
            articulos_repo.crear_rubro(rubro)
        rubros = {fila["nombre"]: fila["id"] for fila in articulos_repo.listar_rubros()}

        # Cuánto se vende de cada artículo en una semana, para el stock mínimo y
        # para cuánto se compra los lunes.
        semana = [primer_dia + timedelta(days=numero) for numero in range(7)]
        ventas_por_semana = sum(self._ventas_esperadas(dia, turno) for dia in semana for turno in turnos_del_dia(dia))
        renglones_por_semana = ventas_por_semana * 1.6 * (1 - PROBABILIDADES["impresiones"])
        peso_total = sum(peso for *_, peso in _CATALOGO)
        usados = {dominio.CODIGO_ARTICULO_IMPRESIONES}
        for descripcion, marca, rubro, precio, peso in _CATALOGO:
            codigo = _codigo_de_barras(self.rng, usados)
            por_semana = renglones_por_semana * peso / peso_total * 1.15
            costo = round(precio * (0.8 if rubro == "CIGARRILLOS" else 0.65))
            stock_minimo = max(2, round(por_semana * 0.4))
            articulos_repo.crear_articulo(codigo, descripcion, None, rubros[rubro], precio, costo,
                                          stock_minimo, nombre_marca_nueva=marca)
            self.articulos[codigo] = {"descripcion": descripcion, "rubro_id": rubros[rubro],
                                      "stock_minimo": stock_minimo}
            self.precio[codigo], self.costo[codigo] = precio, costo
            self.objetivo[codigo] = max(6, math.ceil(por_semana * 1.4))
            self.codigos.append(codigo)
            self.pesos.append(peso)
        impresiones = dominio.CODIGO_ARTICULO_IMPRESIONES
        articulos_repo.crear_articulo(impresiones, "IMPRESIONES", None, rubros["INSUMOS DE PAPELERÍA"],
                                      _PRECIO_DE_LAS_IMPRESIONES, 40, 0)
        self.articulos[impresiones] = {"descripcion": "IMPRESIONES", "rubro_id": rubros["INSUMOS DE PAPELERÍA"],
                                       "stock_minimo": 0}
        self.precio[impresiones], self.costo[impresiones] = _PRECIO_DE_LAS_IMPRESIONES, 40
        marcas = {fila["codigo"]: fila["marca_id"] for fila in articulos_repo.listar_articulos()}
        for codigo, datos in self.articulos.items():
            datos["marca_id"] = marcas[codigo]

        self._a_las(datetime.combine(primer_dia, time(5, 30)))
        self._comprar()

    # --- un turno ---

    def _ventas_esperadas(self, dia: date, turno: str) -> float:
        if es_domingo(dia):
            base = _VENTAS_DEL_DOMINGO[turno]
        else:
            base = _VENTAS_POR_TURNO[turno] * (_FIN_DE_SEMANA.get(turno, 1) if dia.weekday() >= 4 else 1)
        return base * self.escala

    def _de_turno(self, dia: date, turno: str) -> str:
        """Quién atiende cada turno de la semana: Lucía las mañanas, Mariana las
        tardes, Carla las noches y Sofía el viernes a la noche, el sábado a la
        tarde y el domingo a la mañana."""
        dia_de_la_semana = dia.weekday()
        if turno == dominio.TURNO_MANANA:
            return "Sofía" if dia_de_la_semana == 6 else "Lucía"
        if turno == dominio.TURNO_TARDE:
            return "Sofía" if dia_de_la_semana == 5 else "Mariana"
        return "Sofía" if dia_de_la_semana == 4 else "Carla"

    def _quien_atiende(self, dia, turno, la_anterior) -> str:
        nombre = self._de_turno(dia, turno)
        if self.rng.random() < PROBABILIDADES["reemplazo"]:
            otras = [n for n in ("Lucía", "Mariana", "Carla", "Sofía") if n not in (nombre, la_anterior)]
            nombre = self.rng.choice(otras)
        return nombre

    def _contar(self, esperado: float) -> float:
        """Lo que cuenta una empleada: casi siempre lo justo."""
        if self.rng.random() < PROBABILIDADES["cambio_mal_contado"]:
            return max(0, esperado + self.rng.choice((-1000, -500, -500, 500)))
        return esperado

    def _anotar_cierre(self, cierre: dict, momento: datetime):
        if cierre is not None:
            self.por_verificar.append((cierre["id"], cierre["monto_a_retirar"], momento))

    def entrar(self, nombre: str, momento: datetime, repone_el_cambio: bool = False) -> datetime:
        """Lo que hace la pantalla de ingreso (ui/ingreso_caja.py): pregunta la
        situación y la resuelve (cerrar la de otra, abrir contando el cambio,
        recibir contando el cajón) hasta que la caja es suya.

        `repone_el_cambio`: el dueño dejó el cajón con el Cambio Fijo justo antes
        de que se abra (los lunes a la mañana). El cambio que queda al cerrar es
        el que se contó al abrir (cajas_repo.cambio_inicial): sin reponerlo, cada
        faltante del cambio se arrastraría el año entero."""
        usuario_id = self.ids[nombre]
        self._a_las(momento)
        usuarios_repo.autenticar_por_nombre(nombre, CLAVE_DE_PRUEBA)
        for _ in range(4):
            momento += timedelta(seconds=30)
            self._a_las(momento)
            situacion = relevo_repo.situacion_al_entrar(usuario_id, momento)
            que = situacion["situacion"]
            if que == relevo_repo.SITUACION_SU_CAJA:
                return momento
            if que == relevo_repo.SITUACION_ABRIR:
                contado = None
                if situacion["cuenta_cambio"]:
                    contado = self.fondo if repone_el_cambio else self._contar(situacion["cambio_esperado"])
                relevo_repo.abrir_caja(usuario_id, contado, momento)
            elif que == relevo_repo.SITUACION_RECIBIR:
                relevo_repo.recibir_caja(usuario_id, situacion["caja_id"], self._contar(situacion["esperado"]),
                                         momento)
            elif que in (relevo_repo.SITUACION_CERRAR_LA_DE_OTRA, relevo_repo.SITUACION_VENTAS_SIN_CAJA,
                         relevo_repo.SITUACION_SU_CAJA_VENCIDA):
                self._anotar_cierre(relevo_repo.cerrar_para_entrar(usuario_id, que, momento), momento)
            else:
                raise RuntimeError(f"{nombre} no tendría que encontrarse con {que} al entrar.")
        raise RuntimeError(f"{nombre} no pudo entrar a las {momento}.")

    def _si_vencio_se_cierra_sola(self, atiende: str, momento: datetime) -> datetime:
        """Lo que hace el mostrador solo cada pocos segundos
        (MainWindow._revisar_la_caja): si la caja abierta ya pasó su cierre
        forzoso, la cierra y quien atiende vuelve a entrar. Pasa cuando la que se
        olvidó de cerrar (o recibió la caja) atiende también el turno siguiente:
        sin esto vendería el turno entero en la caja vieja. Devuelve desde qué hora
        se puede seguir."""
        estado = relevo_repo.estado_de_la_caja(momento)
        if estado is None or not estado["vencida"]:
            return momento
        vence = estado["cierre_forzoso_a"] + timedelta(seconds=5)
        self._a_las(vence)
        self._anotar_cierre(relevo_repo.cierre_forzoso_si_corresponde(vence), vence)
        return self.entrar(atiende, vence + timedelta(seconds=10))

    def turno(self, dia: date, turno: str, nombre: str, llegada: datetime, como_termina: str,
              es_el_ultimo: bool = False) -> tuple:
        """Un turno entero, de la llegada a cómo termina ("normal": lo cierra
        quien atiende; "olvido": se va sin cerrar; "forzoso": se cierra solo).
        Devuelve a qué hora llega la siguiente y quién terminó atendiendo. Después
        del último no llega nadie: no puede quedar nada sin cerrar."""
        fin = fin_del_turno(dia, turno)
        abre = self.entrar(nombre, llegada, repone_el_cambio=turno == dominio.TURNO_MANANA and dia.weekday() == 0)
        se_va = fin + self._minutos(-4, 10)

        eventos = []
        cantidad = max(0, round(self._ventas_esperadas(dia, turno) * self.rng.gauss(1, 0.15)))
        for _ in range(cantidad):
            eventos.append((abre + (se_va - abre) * self.rng.uniform(0.01, 0.99), "venta", None))
        if self.rng.random() < PROBABILIDADES["relevo"]:
            otra = self.rng.choice([n for n in self.ids if n not in (ADMIN, nombre)])
            eventos.append((abre + (fin - abre) * self.rng.uniform(0.3, 0.6), "relevo", otra))
        if turno == dominio.TURNO_MANANA:
            if dia.toordinal() % 30 == 0:
                eventos.append((datetime.combine(dia, time(9, 0)), "precios", None))
            if dia.weekday() == 0:
                eventos.append((datetime.combine(dia, time(10, 0)), "compra", None))
            eventos.append((datetime.combine(dia, time(11, 0)), "sobres", None))
        eventos.sort(key=lambda evento: evento[0])

        # `piso`: nada puede quedar antes de lo último que pasó (entrar, recibir
        # la caja o una anulación corren el reloj unos segundos).
        atiende, piso = nombre, abre + timedelta(minutes=1)
        for momento, que, dato in eventos:
            piso = self._si_vencio_se_cierra_sola(atiende, max(momento, piso))
            momento = max(momento, piso)
            self._a_las(momento)
            if que == "venta":
                piso = self._vender(atiende, momento)
            elif que == "relevo":
                atiende = dato
                piso = self.entrar(atiende, momento)
            elif que == "precios":
                self._subir_precios()
            elif que == "compra":
                self._comprar()
            elif que == "sobres":
                self._contar_sobres(momento)
        se_va = max(se_va, piso)
        sigue = self._si_vencio_se_cierra_sola(atiende, se_va)
        if sigue > se_va:  # se cerró sola la caja vieja y abrió otra justo ahora
            se_va = sigue + timedelta(minutes=1)

        if como_termina == "normal":
            self._a_las(se_va)
            self._anotar_cierre(turnos_repo.cerrar_turno(self.ids[atiende], ahora_dt=se_va), se_va)
            llega = se_va + self._minutos(1, 6)
            if not es_el_ultimo and self.rng.random() < PROBABILIDADES["venta_sin_caja"]:
                # El Admin cobra algo con el mostrador sin nadie: la que llega
                # primero cierra esas ventas aparte (SITUACION_VENTAS_SIN_CAJA).
                self._a_las(se_va + timedelta(seconds=20))
                usuarios_repo.autenticar_por_nombre(ADMIN, CLAVE_DE_PRUEBA)
                self._vender(ADMIN, se_va + timedelta(seconds=30))
            return llega, atiende
        if como_termina == "olvido":
            return max(se_va, fin) + self._minutos(1, 8), atiende
        # Forzoso: lo hace el programa del mostrador solo (MainWindow._revisar_la_caja).
        vence = turno_vencimiento(dia, turno) + timedelta(seconds=5)
        self._a_las(vence)
        self._anotar_cierre(relevo_repo.cierre_forzoso_si_corresponde(vence), vence)
        return vence + self._minutos(5, 40), atiende

    # --- lo que pasa adentro de un turno ---

    def _pagos(self, total: float) -> list:
        """Cómo paga el cliente (netos de vuelto, como los devuelve la ventana de cobro)."""
        sorteo = self.rng.random()
        if sorteo < 0.55 or total < 1000:
            return [{"metodo": dominio.PAGO_EFECTIVO, "monto": total}]
        if sorteo < 0.95:
            return [{"metodo": dominio.PAGO_DIGITAL, "monto": total}]
        efectivo = min(total - 50, _redondear(total * self.rng.uniform(0.3, 0.7)))
        return [{"metodo": dominio.PAGO_EFECTIVO, "monto": efectivo},
                {"metodo": dominio.PAGO_DIGITAL, "monto": total - efectivo}]

    def _vender(self, atiende: str, momento: datetime) -> datetime:
        """Una venta (o un cobro de impresiones) a la hora `momento`. Devuelve la
        hora de lo último que hizo: una anulación es unos segundos después."""
        self._a_las(momento)
        if self.rng.random() < PROBABILIDADES["impresiones"]:
            cantidad = self.rng.choice((1, 1, 1, 2, 2, 3, 4, 5, 10, 20))
            precio = self.precio[dominio.CODIGO_ARTICULO_IMPRESIONES]
            impresiones_repo.cobrar_impresiones(self.ids[atiende], cantidad, precio,
                                                self._pagos(cantidad * precio))
            return momento
        quien = ADMIN if self.rng.random() < PROBABILIDADES["venta_admin"] else atiende
        carrito = {}
        renglones = self.rng.choices((1, 2, 3, 4), weights=(60, 25, 10, 5))[0]
        for codigo in self.rng.choices(self.codigos, weights=self.pesos, k=renglones):
            carrito[codigo] = carrito.get(codigo, 0) + self.rng.choices((1, 2, 3), weights=(85, 12, 3))[0]
        lineas = [
            {"codigo": codigo, "descripcion": self.articulos[codigo]["descripcion"],
             "cantidad": cantidad, "precio_unitario": self.precio[codigo]}
            for codigo, cantidad in carrito.items()
        ]
        venta_id = ventas_repo.confirmar_venta(self.ids[quien], lineas, self._pagos(ventas_repo.total_carrito(lineas)))
        if self.rng.random() < PROBABILIDADES["anulada"]:
            momento += timedelta(seconds=20)
            self._a_las(momento)
            ventas_repo.anular_venta(venta_id, self.ids[ADMIN], self.rng.choice(_MOTIVOS_DE_ANULACION))
        return momento

    def _comprar(self):
        """El Admin repone lo que está bajo (los lunes, y todo al empezar)."""
        lineas = []
        for articulo in articulos_repo.listar_articulos():
            codigo = articulo["codigo"]
            if codigo in self.objetivo and articulo["stock"] < self.objetivo[codigo] * 0.6:
                lineas.append({"codigo": codigo, "cantidad": self.objetivo[codigo] - articulo["stock"],
                               "costo_unitario": self.costo[codigo]})
        if lineas:
            compras_repo.registrar_compra(self.ids[ADMIN], lineas)

    def _subir_precios(self):
        """Cada mes el Admin sube los precios entre 2 y 6% (las impresiones,
        $ 50 cada tanto)."""
        suba = self.rng.uniform(1.02, 1.06)
        for codigo, datos in self.articulos.items():
            if codigo == dominio.CODIGO_ARTICULO_IMPRESIONES:
                if self.rng.random() < 0.34:
                    self.precio[codigo] += 50
            else:
                self.precio[codigo] = _redondear(self.precio[codigo] * suba)
                self.costo[codigo] = round(self.costo[codigo] * suba)
            articulos_repo.modificar_articulo(codigo, datos["descripcion"], datos["marca_id"], datos["rubro_id"],
                                              self.precio[codigo], self.costo[codigo], datos["stock_minimo"])

    def _contar_sobres(self, momento: datetime):
        """El dueño cuenta a la mañana los sobres de lo que se cerró antes
        (Control de Cierres); alguno queda sin contar."""
        usuarios_repo.autenticar_por_nombre(ADMIN, CLAVE_DE_PRUEBA)
        quedan = []
        for cierre_id, a_retirar, cerrado in self.por_verificar:
            if cerrado >= momento:
                quedan.append((cierre_id, a_retirar, cerrado))
                continue
            if self.rng.random() >= PROBABILIDADES["sobre_contado"]:
                continue
            sorteo = self.rng.random()
            diferencia = 0
            if sorteo < PROBABILIDADES["sobre_con_faltante"]:
                diferencia = -self.rng.choice((500, 1000, 1000, 2000, 5000))
            elif sorteo < PROBABILIDADES["sobre_con_faltante"] + PROBABILIDADES["sobre_con_sobrante"]:
                diferencia = self.rng.choice((500, 1000))
            control_cierres_repo.verificar_cierre(cierre_id, max(0, a_retirar + diferencia), self.ids[ADMIN])
        self.por_verificar = quedan

    # --- todo junto ---

    def correr(self, turnos: list):
        primer_dia = turnos[0][0]
        self.preparar(primer_dia)
        llegada = datetime.combine(primer_dia, time(5, 55))
        la_anterior = None
        mes = None
        for posicion, (dia, turno) in enumerate(turnos):
            if (dia.year, dia.month) != mes:
                mes = (dia.year, dia.month)
                self.avisar(f"  {dia.strftime('%m/%Y')}...")
            nombre = self._quien_atiende(dia, turno, la_anterior)
            es_el_ultimo = posicion == len(turnos) - 1
            if es_el_ultimo:
                como_termina = "normal"  # la base queda sin ninguna caja abierta
            else:
                sorteo = self.rng.random()
                como_termina = ("forzoso" if sorteo < PROBABILIDADES["forzoso"]
                                else "olvido" if sorteo < PROBABILIDADES["forzoso"] + PROBABILIDADES["olvido"]
                                else "normal")
            llegada, la_anterior = self.turno(dia, turno, nombre, llegada, como_termina, es_el_ultimo)


# ---------------------------------------------------------------------------
# Armar la carpeta
# ---------------------------------------------------------------------------

def _con_reintentos(accion, *argumentos):
    """Windows a veces no deja reemplazar o borrar por un instante lo que se acaba
    de escribir (el antivirus o el indexador lo están mirando): se reintenta."""
    for intento in range(5):
        try:
            return accion(*argumentos)
        except PermissionError:
            if intento == 4:
                raise
            reloj_de_verdad.sleep(1)


def _borrar_si_esta(ruta: str):
    if os.path.isdir(ruta):
        shutil.rmtree(ruta, ignore_errors=True)
    elif os.path.exists(ruta):
        _con_reintentos(os.remove, ruta)


def _turnos_a_simular(dias: int, hasta: date, ahora: datetime) -> list:
    """Los (día, turno) de `dias` días hasta `hasta` inclusive, sin los que
    todavía no terminaron (con margen: el último se cierra pasado su fin)."""
    desde = hasta - timedelta(days=dias - 1)
    turnos = [
        (desde + timedelta(days=numero), turno)
        for numero in range(dias)
        for turno in turnos_del_dia(desde + timedelta(days=numero))
    ]
    return [(dia, turno) for dia, turno in turnos if fin_del_turno(dia, turno) + timedelta(minutes=90) < ahora]


def armar(carpeta: str = CARPETA_POR_DEFECTO, dias: int = 365, semilla: int = 2026, escala: float = 1.0,
          hasta: date = None, avisar=print) -> dict:
    """
    Arma la base de prueba en `carpeta` (al lado del programa si no tiene la
    letra del disco) con `dias` días de movimiento hasta `hasta` (por defecto,
    ayer). Si la carpeta ya existe tiene que ser una base de prueba o estar
    vacía: si no, ValueError y no se toca nada. Devuelve cuántas cosas quedaron.

    Se arma en ARMANDO, al lado de la base anterior, y recién al final la
    reemplaza: si se corta a mitad de camino, la anterior sigue sana.
    """
    if dias < 1:
        raise ValueError("Tiene que ser al menos un día.")
    ahora = datetime.now()
    hasta = hasta or dia_en_que_empezo_el_turno(ahora) - timedelta(days=1)
    turnos = _turnos_a_simular(dias, hasta, ahora)
    if not turnos:
        raise ValueError("No hay ningún turno terminado en esos días.")

    anterior = (database.DATA_DIR, database.DB_PATH)
    try:
        database.usar_carpeta_de_datos(carpeta)
        destino, final = database.DATA_DIR, database.DB_PATH
    finally:
        database.DATA_DIR, database.DB_PATH = anterior
    if os.path.normcase(os.path.abspath(destino)) == os.path.normcase(os.path.abspath(anterior[0])):
        raise ValueError(f"{destino} es la carpeta de la base del programa: la de prueba va en otra.")
    if os.path.exists(destino) and os.listdir(destino) and not database.es_base_de_prueba(destino):
        raise ValueError(f"{destino} ya existe y no es una base de prueba: no la toco.")
    os.makedirs(destino, exist_ok=True)
    with open(os.path.join(destino, database.ARCHIVO_DE_BASE_DE_PRUEBA), "w", encoding="utf-8") as archivo:
        archivo.write(
            "Esta carpeta es una BASE DE PRUEBA con datos inventados, armada con\n"
            "armar_base_de_prueba.py. No es la base del kiosko. Para abrirla:\n"
            f"python main.py --base {carpeta}\n"
        )
    armando = os.path.join(destino, ARMANDO)
    _borrar_si_esta(armando)  # de un armado anterior que se cortó

    empezo = reloj_de_verdad.monotonic()
    avisar(f"Armando la base de prueba en {destino} ({turnos[0][0]:%d/%m/%Y} a {turnos[-1][0]:%d/%m/%Y})")
    try:
        database.usar_carpeta_de_datos(destino)
        database.DB_PATH = armando
        with _reloj_simulado() as reloj, _conexiones_rapidas():
            _Simulacion(random.Random(semilla), reloj, escala, avisar).correr(turnos)
        resumen = _resumen()
    finally:
        database.DATA_DIR, database.DB_PATH = anterior

    # Un -journal que quedó de la base anterior (el programa se cerró a mitad de
    # una venta) SQLite lo aplicaría sobre la nueva y la dañaría: se va antes.
    # Las copias y los errores que dejó el programa abierto con --base eran de la
    # anterior.
    _borrar_si_esta(final + "-journal")
    _borrar_si_esta(os.path.join(destino, "backups"))
    _borrar_si_esta(os.path.join(destino, "errores.log"))
    try:
        _con_reintentos(os.replace, armando, final)
    except PermissionError:
        raise ValueError(f"No se pudo reemplazar {final}: ¿está abierto el programa con esa base? "
                         "Cerralo y volvé a armarla.") from None
    resumen["carpeta"] = destino
    resumen["segundos"] = round(reloj_de_verdad.monotonic() - empezo)
    return resumen


def _resumen() -> dict:
    """Cuántas cosas quedaron (y que la base quedó como una nueva en lo que no
    se simula: sin caja abierta y sin envíos a la app de gastos)."""
    with database.conexion_db() as conexion:
        def contar(sql, *parametros):
            return conexion.execute(sql, parametros).fetchone()[0]

        resumen = {
            "ventas": contar("SELECT COUNT(*) FROM ventas WHERE estado = ?", dominio.VENTA_CONFIRMADA),
            "anuladas": contar("SELECT COUNT(*) FROM ventas WHERE estado = ?", dominio.VENTA_ANULADA),
            "cierres": contar("SELECT COUNT(*) FROM cierres_turno"),
            "sin_caja": contar("SELECT COUNT(*) FROM cierres_turno WHERE id NOT IN "
                               "(SELECT cierre_id FROM cajas WHERE cierre_id IS NOT NULL)"),
            "relevos": contar("SELECT COUNT(*) FROM relevos_caja"),
            "forzosos": contar("SELECT COUNT(*) FROM cajas WHERE cierre_forzoso = 1"),
            "compras": contar("SELECT COUNT(*) FROM compras"),
            "articulos": contar("SELECT COUNT(*) FROM articulos"),
        }
        abiertas = contar("SELECT COUNT(*) FROM cajas WHERE cierre_id IS NULL")
        sin_cerrar = contar("SELECT COUNT(*) FROM ventas WHERE fecha > (SELECT MAX(fecha_cierre) FROM cierres_turno)")
    if abiertas or sin_cerrar or envio_pwa_repo.esta_activado():
        raise RuntimeError("La base de prueba quedó con algo sin cerrar o con el envío prendido.")
    resumen["megas"] = round(os.path.getsize(database.DB_PATH) / 1024 / 1024, 1)
    return resumen


def _hay_un_frkiosko_abierto() -> bool:
    """Si alguna copia de FRKiosko tiene tomado su candado en esta PC (ver
    PUERTO_DEL_PROGRAMA_ABIERTO)."""
    candado = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        candado.bind(("127.0.0.1", PUERTO_DEL_PROGRAMA_ABIERTO))
    except OSError:
        return True
    finally:
        candado.close()
    return False


def main():
    parser = argparse.ArgumentParser(description="Arma una base de prueba con datos inventados.")
    parser.add_argument("--dias", type=int, default=365, help="cuántos días de movimiento (365)")
    parser.add_argument("--carpeta", default=CARPETA_POR_DEFECTO, help=f"dónde ({CARPETA_POR_DEFECTO})")
    parser.add_argument("--semilla", type=int, default=2026, help="con la misma, sale la misma base")
    parser.add_argument("--escala", type=float, default=1.0,
                        help="más o menos ventas (1 = unas 180 por día)")
    argumentos = parser.parse_args()
    if _hay_un_frkiosko_abierto():
        print("Cerrá FRKiosko antes de armar la base de prueba: si está abierto con esa base, "
              "se la cambiaría mientras la usa.")
        sys.exit(1)
    try:
        resumen = armar(argumentos.carpeta, argumentos.dias, argumentos.semilla, argumentos.escala)
    except ValueError as error:
        print(error)
        sys.exit(1)
    print(
        f"Listo en {resumen['segundos']} s: {resumen['ventas']} ventas ({resumen['anuladas']} anuladas), "
        f"{resumen['cierres']} cierres ({resumen['forzosos']} forzosos, {resumen['sin_caja']} de ventas "
        f"sin caja, {resumen['relevos']} relevos), "
        f"{resumen['compras']} compras, {resumen['articulos']} artículos, {resumen['megas']} MB.\n"
        f"Para abrirla: python main.py --base {argumentos.carpeta}"
    )


if __name__ == "__main__":
    main()
