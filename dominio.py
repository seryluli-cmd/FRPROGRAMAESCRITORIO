"""Valores y cuentas compartidos por el kiosko, sin dependencias de interfaz ni base."""

import unicodedata
from urllib.parse import quote


ROL_ADMIN = "ADMIN"
ROL_EMPLEADA = "EMPLEADA"
ROLES = (ROL_ADMIN, ROL_EMPLEADA)


def es_admin(usuario) -> bool:
    return usuario is not None and usuario["rol"] == ROL_ADMIN


VENTA_CONFIRMADA = "CONFIRMADA"
VENTA_ANULADA = "ANULADA"
ESTADOS_VENTA = (VENTA_CONFIRMADA, VENTA_ANULADA)

PAGO_EFECTIVO = "EFECTIVO"
PAGO_DIGITAL = "DIGITAL"
METODOS_PAGO = (PAGO_EFECTIVO, PAGO_DIGITAL)
NOMBRE_METODO_PAGO = {
    PAGO_EFECTIVO: "Efectivo",
    PAGO_DIGITAL: "Digital (Mercado Pago / Transferencia)",
}

# La venta sigue llevando origen para que el dato guardado sea explícito.
ORIGEN_KIOSKO = "KIOSKO"
ORIGENES_VENTA = (ORIGEN_KIOSKO,)

# Impresiones es un artículo de mercadería, pero se muestra aparte en Caja.
CODIGO_ARTICULO_IMPRESIONES = "4"

TURNO_MANANA = "MAÑANA"
TURNO_TARDE = "TARDE"
TURNO_NOCHE = "NOCHE"
TURNOS = (TURNO_MANANA, TURNO_TARDE, TURNO_NOCHE)

MINUTOS_ADMIN_VUELVE_SOLO = 10

ENVIO_PENDIENTE = "PENDIENTE"
ENVIO_ENVIADO = "ENVIADO"
ENVIO_ERROR = "ERROR"
ESTADOS_ENVIO_PWA = (ENVIO_PENDIENTE, ENVIO_ENVIADO, ENVIO_ERROR)

# Orden y nombres compartidos por el cierre en pantalla y la PWA.
NEGOCIOS_DEL_CIERRE = (
    ("kiosko_solo", "Kiosko"),
    ("impresiones", "Impresiones"),
)


def lo_que_falta_para(total: float, monto: float) -> float:
    """Monto que completa un cobro entre efectivo y digital."""
    return round(max(0.0, total - monto), 2)


def cuenta_del_cobro(total: float, efectivo: float, digital: float, paga_con: float = 0.0) -> dict:
    """Separa un cobro entre métodos y calcula el vuelto sin guardarlo como ingreso."""
    total = round(total, 2)
    digital = round(min(max(digital, 0.0), total), 2)
    parte_efectivo = round(total - digital, 2)
    entrega = round(paga_con if paga_con > 0 else max(efectivo, 0.0), 2)
    if parte_efectivo <= 0:
        entrega = 0.0
    falta = round(max(0.0, parte_efectivo - entrega), 2)
    vuelto = round(entrega - parte_efectivo, 2) if not falta else 0.0
    pagos = []
    if parte_efectivo > 0.001:
        pagos.append({"metodo": PAGO_EFECTIVO, "monto": parte_efectivo})
    if digital > 0.001:
        pagos.append({"metodo": PAGO_DIGITAL, "monto": digital})
    return {
        "parte_efectivo": parte_efectivo, "digital": digital, "entrega": entrega,
        "vuelto": max(vuelto, 0.0), "falta": falta, "pagos": pagos,
    }


# ---------------------------------------------------------------------------
# La plata de la caja y del sobre
# ---------------------------------------------------------------------------
# Cada regla en una sola función, para que Caja, el Cierre de Turno, el relevo,
# Control de Cierres, el Resumen del Día y la app de gastos digan lo mismo.

# Una diferencia de plata menor que esto es cero. Todo se guarda al centavo
# (regla 9) y las diferencias salen redondeadas de diferencia_de_plata: la más
# chica que no es cero es un centavo, y el medio centavo solo se come la cola
# del punto flotante (0.1 + 0.2 - 0.3). No es la misma regla que
# ventas_repo.DIFERENCIA_MAXIMA_DE_PAGOS ni que el 0.005 de texto_pesos.
TOLERANCIA_DE_PLATA = 0.005


def total_cobrado(efectivo: float, digital: float) -> float:
    """Todo lo cobrado en un turno: el efectivo más lo digital, sin el Cambio
    Fijo (que no es cobrado). Es el TOTAL del Cierre de Turno, de Caja y el
    importe que va a la app de gastos."""
    return round(efectivo + digital, 2)


def monto_a_retirar(efectivo_cobrado: float) -> float:
    """Lo que va al sobre al cerrar una caja: todo el efectivo cobrado en el
    turno, de todos los orígenes. El cambio con que arrancó la caja no se toca:
    queda en el cajón para la siguiente (cajas_repo.cambio_inicial). Es lo que
    graba el cierre y lo que se espera encontrar al contar el sobre."""
    return round(efectivo_cobrado, 2)


def diferencia_de_plata(contado: float, esperado: float) -> float:
    """Lo contado menos lo que tendría que haber: negativo = falta plata. Es la
    cuenta que se muestra al contar y la que se guarda (la apertura y el relevo
    de una caja, y el sobre de un cierre)."""
    return round(contado - esperado, 2)


def coincide(diferencia: float) -> bool:
    """Si una diferencia de plata (de diferencia_de_plata) es cero: lo contado
    es lo que tenía que haber."""
    return abs(diferencia) < TOLERANCIA_DE_PLATA


def falta_plata(diferencia: float) -> bool:
    """Si una diferencia de plata dice que falta: es negativa y no coincide. Un
    sobrante no es un faltante."""
    return diferencia < 0 and not coincide(diferencia)


def sin_acentos(texto) -> str:
    """Texto en minúsculas y sin acentos para búsquedas y orden natural."""
    return "".join(
        letra for letra in unicodedata.normalize("NFD", (texto or "").lower())
        if not unicodedata.combining(letra)
    )


def orden_de_codigo(codigo) -> tuple:
    """Ordena códigos numéricos por valor y luego códigos con letras."""
    texto = (codigo or "").strip()
    if texto.isascii() and texto.isdigit():
        return (0, int(texto), texto)
    return (1, 0, sin_acentos(texto))


def texto_pesos(monto) -> str:
    """Presenta pesos con miles y centavos solo cuando existen."""
    try:
        monto = round(float(monto), 2)
    except (TypeError, ValueError):
        monto = 0.0
    if abs(monto - round(monto)) < 0.005:
        texto = f"{round(monto):,}"
    else:
        texto = f"{monto:,.2f}"
    return "$ " + texto.replace(",", "TEMP").replace(".", ",").replace("TEMP", ".")


def texto_cantidad(cantidad) -> str:
    """Unidades con el punto de los miles, como los pesos pero sin el "$":
    -13055 -> "-13.055" (el stock de Modificar artículo)."""
    return f"{int(cantidad):,}".replace(",", ".")


# ---------------------------------------------------------------------
# Cuentas de Artículos, Ventas y Reportes
# ---------------------------------------------------------------------
# Acá y no en un repo: Artículos, ORDENAR Stock y Reportes se abren también
# desde otra PC, y una función de un repo que usen tendría que entrar en la
# lista blanca (admin_remoto/lista_blanca.py), cambiando la huella.

# La ganancia sobre el costo con que arranca la calculadora de precios de un
# artículo (pedido del dueño, 2026-10-31: "el margen por defecto, del 80%").
MARGEN_POR_DEFECTO = 80


def precio_con_margen(costo: float, porcentaje: float) -> float:
    """Precio de venta con `porcentaje` de margen sobre el costo. Va como
    costo * (1 + %/100): costo + costo * %/100 da a veces otro centavo."""
    return round(costo * (1 + porcentaje / 100), 2)


def costo_sin_margen(precio_venta: float, porcentaje: float) -> float:
    """La vuelta de precio_con_margen (estimar el costo si se perdió la
    factura). La pantalla no deja un % negativo: nunca divide por cero."""
    return round(precio_venta / (1 + porcentaje / 100), 2)


def porcentaje_de_ganancia(costo: float, precio_venta: float):
    """El % que se le gana sobre el costo vendiendo a `precio_venta`, el que usa
    precio_con_margen: costo $ 20 y venta $ 200 da 900. Sin costo no hay % (None).
    Con dos decimales: con ese % precio_con_margen vuelve a dar la misma venta."""
    if costo <= 0:
        return None
    return round((precio_venta / costo - 1) * 100, 2)


def ganancia_por_unidad(costo: float, precio_venta: float) -> float:
    """Lo que dice la ayuda de la calculadora de precios: cuánto se gana por unidad
    (venta $ 200 y costo $ 20: $ 180), negativo si se vende por debajo del costo.
    Sin el % sobre la venta (90%): al lado del % sobre el costo confundía y el dueño
    pidió sacarlo (2026-10-31)."""
    return round(precio_venta - costo, 2)


def bajo_el_minimo(stock: int, stock_minimo: int) -> bool:
    """Stock en rojo o aviso en Ventas. Justo en el mínimo no avisa; el stock
    negativo (puede quedar a propósito) sí."""
    return stock < stock_minimo


def numeros_de_los_articulos(articulos) -> dict:
    """
    Los números de arriba de Artículos (maqueta B, 2026-10-30): cuántos artículos
    hay, cuántos quedaron bajo el mínimo y cuánto vale la mercadería del estante a
    precio de compra. Impresiones no entra: no es mercadería que se cuenta y su
    stock baja sin que nadie lo cargue, así que siempre estaría "bajo el mínimo".
    El stock negativo (puede quedar a propósito) vale cero, no resta.
    """
    mercaderia = [a for a in articulos if a["codigo"] != CODIGO_ARTICULO_IMPRESIONES]
    return {
        "cantidad": len(mercaderia),
        "bajo_el_minimo": sum(1 for a in mercaderia if bajo_el_minimo(a["stock"], a["stock_minimo"])),
        "valor_del_stock": round(sum(max(0, a["stock"]) * a["precio_compra"] for a in mercaderia), 2),
    }


# LISTA DE COMPRAS (pedido del dueño, 2026-10-31): salen los artículos que tienen
# esta cantidad de unidades o menos.
STOCK_PARA_LISTA_DE_COMPRAS = 4


def articulos_para_comprar(articulos) -> list:
    """
    Los artículos de la LISTA DE COMPRAS: los que tienen STOCK_PARA_LISTA_DE_COMPRAS
    unidades o menos (también los que están en 0 o en negativo), de la A a la Z sin
    mirar mayúsculas ni acentos. Impresiones no entra: no es mercadería que se compra.
    """
    return sorted(
        (a for a in articulos
         if a["codigo"] != CODIGO_ARTICULO_IMPRESIONES and a["stock"] <= STOCK_PARA_LISTA_DE_COMPRAS),
        key=lambda a: sin_acentos(a["descripcion"]),
    )


def suma_de_las_filas(filas, claves) -> dict:
    """La fila TOTAL de un reporte: suma las filas tal como se ven (ya
    redondeadas), en su orden y sin redondear de nuevo. Otro SUM en la base
    podría no dar lo mismo que lo de arriba: Kiosko sale por resta en cada fila."""
    return {clave: sum(fila[clave] for fila in filas) for clave in claves}


# GESTIÓN IMPRESIONES (pedido del dueño, 2026-11-02): pedidos grandes que se dejan
# con seña (o pagados enteros) y se retiran después. Reglas en
# repositories/pedidos_impresion_repo.py.
PEDIDO_PENDIENTE = "PENDIENTE"        # tomado, todavía no lo retiraron
PEDIDO_RETIRADO = "RETIRADO"          # lo retiraron y pagaron lo que faltaba
PEDIDO_SENA_PERDIDA = "SEÑA PERDIDA"  # no vino nunca: la seña queda para el local
PEDIDO_ANULADO = "ANULADO"            # mal cargado: se anularon sus cobros
ESTADOS_PEDIDO = (PEDIDO_PENDIENTE, PEDIDO_RETIRADO, PEDIDO_SENA_PERDIDA, PEDIDO_ANULADO)

# El renglón de la seña en la venta (artículo Impresiones, 1 x la seña) y, con la
# misma descripción, el que la descuenta al retirar (-1 x la seña): en los reportes
# se compensan, y las hojas se cuentan una sola vez, al retirar.
DESCRIPCION_SENA_IMPRESIONES = "SEÑA DE IMPRESIONES"

# Un pedido de más hojas es casi seguro un número tipeado de más.
HOJAS_MAXIMAS_POR_PEDIDO = 9_999


def total_del_pedido(hojas: int, precio_hoja: float) -> float:
    """Lo que cuesta un pedido: las hojas por el precio de Impresiones (el mismo en
    color o en blanco y negro, sin descuento por cantidad: lo dijo el dueño)."""
    return round(hojas * precio_hoja, 2)


def falta_abonar(total: float, sena: float) -> float:
    """Lo que el cliente paga al retirar: el total menos la seña."""
    return round(total - sena, 2)


def revisar_sena(total: float, sena: float):
    """ValueError si la seña no sirve: sin seña no se toma el pedido (dueño), y no
    puede pasar del total (pagarlo entero de entrada sí se puede)."""
    if round(sena, 2) <= 0:
        raise ValueError("Sin seña no se toma el pedido: cobrá una seña o el total.")
    if round(sena, 2) > round(total, 2):
        raise ValueError(f"La seña no puede ser más que el total ({texto_pesos(total)}).")


def numeros_de_los_pedidos(pedidos) -> dict:
    """Los números de arriba de Gestión Impresiones: cuántos pedidos esperan que los
    retiren, cuánto se cobró de seña de esos y cuánto falta cobrar."""
    pendientes = [p for p in pedidos if p["estado"] == PEDIDO_PENDIENTE]
    return {
        "pendientes": len(pendientes),
        "senas": round(sum(p["sena"] for p in pendientes), 2),
        "falta": round(sum(falta_abonar(p["total"], p["sena"]) for p in pendientes), 2),
    }


# WhatsApp del cliente: en el kiosko se escribe el celular con la característica,
# sin el 0 y sin el 15 (11 5555 1234: 10 números). Para WhatsApp va con el 54 del
# país y el 9 de los celulares adelante.
CARACTERISTICA_WHATSAPP = "549"
_AYUDA_TELEFONO = "Escribí el celular con la característica, sin 0 y sin 15 (por ejemplo, 11 5555 1234)."


def telefono_limpio(telefono) -> str:
    """El celular como se guarda: solo los 10 números ("1155551234"), o "" si no se
    escribió. Acepta espacios, guiones y paréntesis, y que lo peguen con el 0 o
    con +54 9 adelante. ValueError si no quedan 10 números."""
    numeros = "".join(caracter for caracter in str(telefono or "") if caracter.isdigit())
    if not numeros:
        return ""
    if len(numeros) == 13 and numeros.startswith(CARACTERISTICA_WHATSAPP):
        numeros = numeros[3:]
    elif len(numeros) == 12 and numeros.startswith("54"):
        numeros = numeros[2:]
    elif len(numeros) == 11 and numeros.startswith("0"):
        numeros = numeros[1:]
    if len(numeros) != 10:
        raise ValueError(_AYUDA_TELEFONO)
    return numeros


def mensaje_pedido_listo(nombre: str, hojas: int, falta: float) -> str:
    """Lo que se le escribe al cliente cuando el pedido está listo."""
    mensaje = f"Hola {nombre}! Tu pedido de {hojas} impresiones ya está listo para retirar en el kiosko."
    if round(falta, 2) > 0:
        mensaje += f" Te falta abonar {texto_pesos(falta)}."
    return mensaje + " ¡Gracias!"


def enlace_whatsapp(telefono: str, mensaje: str) -> str:
    """La dirección que abre WhatsApp Web con el chat del cliente y el mensaje ya
    escrito (lo manda quien atiende, con Enter)."""
    return f"https://web.whatsapp.com/send?phone={CARACTERISTICA_WHATSAPP}{telefono}&text={quote(mensaje)}"
