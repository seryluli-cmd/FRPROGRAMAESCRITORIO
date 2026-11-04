"""Valores y cuentas compartidos por el kiosko, sin dependencias de interfaz ni base."""

import unicodedata
from datetime import date, datetime, timedelta
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


# PEDIDOS DE CLIENTES (pedido del dueño, 2026-11-03): mercadería que NO tenemos y
# que los clientes vienen a buscar ("Mantecol"). Cada vez que alguien lo pide se
# suma un cliente al mismo renglón. Reglas en repositories/pedidos_clientes_repo.py.
# No confundir con los PEDIDO_* de Gestión Impresiones de arriba: son otra cosa
# (pedidos de impresiones con seña) y tienen su propia tabla y sus propios estados.
PEDIDO_CLIENTE_PENDIENTE = "PENDIENTE"  # lo piden y todavía no lo trajimos
PEDIDO_CLIENTE_TRAIDO = "TRAÍDO"        # ya lo trajimos: sale de la lista y queda en el historial
PEDIDO_CLIENTE_BORRADO = "BORRADO"      # anotado por error o juntado con otro (solo el Admin)
ESTADOS_PEDIDO_CLIENTE = (PEDIDO_CLIENTE_PENDIENTE, PEDIDO_CLIENTE_TRAIDO, PEDIDO_CLIENTE_BORRADO)

# Más largo que esto es casi seguro un texto pegado sin querer: un producto se
# nombra con pocas palabras ("Alfajor Jorgito de membrillo").
LARGO_MAXIMO_PEDIDO_CLIENTE = 60

# Con una sola letra los parecidos serían casi toda la lista: recién desde la
# segunda se muestran.
LETRAS_MINIMAS_PARECIDOS = 2


def _sin_invisibles(texto) -> str:
    """Saca los caracteres invisibles de formato (categoría Cf de Unicode: el
    espacio de ancho cero, las marcas de dirección, el BOM, el guion suave...).
    Con el teclado no se escriben, pero vienen pegados en un texto copiado de
    WhatsApp Web o de una página, y split() no los toma como espacios: un
    "Mantecol" con uno de esos se vería igual al otro y abriría un renglón aparte.
    Sale también el U+200D que arma los emojis compuestos (quedan sus partes una
    al lado de la otra): dejarlo sería dejar abierto ese mismo agujero."""
    return "".join(letra for letra in str(texto or "") if unicodedata.category(letra) != "Cf")


def pedido_cliente_limpio(texto) -> str:
    """Lo escrito como se muestra en la lista: sin espacios de más ni caracteres
    invisibles, y con la primera letra en mayúscula, sin tocar las demás
    ("  mantecol  grande" da "Mantecol grande"; "7UP" queda "7UP")."""
    texto = " ".join(_sin_invisibles(texto).split())
    return texto[:1].upper() + texto[1:]


def clave_pedido_cliente(texto) -> str:
    """Con qué se compara un pedido con otro: minúsculas, sin tildes, sin espacios
    de más ni caracteres invisibles ("Mantecól ", "MANTECOL" y "mantecol" son el
    mismo). Ojo: la ñ también pierde su tilde (sin_acentos), así que "Ñoquis" y
    "Noquis" son el mismo."""
    return " ".join(sin_acentos(_sin_invisibles(texto)).split())


def revisar_pedido_cliente(texto) -> tuple:
    """(como se muestra, clave) de lo que escribió la empleada, o ValueError si está
    vacío o es más largo que LARGO_MAXIMO_PEDIDO_CLIENTE."""
    producto = pedido_cliente_limpio(texto)
    clave = clave_pedido_cliente(producto)
    if not clave:
        raise ValueError("Escribí qué producto pidió el cliente.")
    if len(producto) > LARGO_MAXIMO_PEDIDO_CLIENTE:
        raise ValueError(
            f"Es muy largo: escribí el producto con hasta {LARGO_MAXIMO_PEDIDO_CLIENTE} letras."
        )
    return producto, clave


# ---------------------------------------------------------------------
# TAREAS DEL TURNO (pedido del dueño, 2026-11-03)
# ---------------------------------------------------------------------
# Cosas para hacer a una hora ("PRENDER LAS LUCES DE AFUERA" a las 19:30). Las
# carga el Admin; a la hora sale un aviso hasta que alguien pone TAREA HECHA.
# Reglas en repositories/tareas_turno_repo.py; cuándo pasa cada una, con la Noche
# que cruza la medianoche, en turnos.momento_de_la_tarea.

# Una tarea cargada. Nada se borra (regla 7): la que el Admin saca queda BORRADA.
TAREA_ACTIVA = "ACTIVA"
TAREA_BORRADA = "BORRADA"
ESTADOS_TAREA = (TAREA_ACTIVA, TAREA_BORRADA)

# Cada cuánto se repite. Los días son del LOCAL (de 06:00 a 06:00): una tarea de
# las 02:00 "los lunes" pasa el martes a las 02:00, en la Noche del lunes.
TAREA_TODOS_LOS_DIAS = "TODOS LOS DÍAS"
TAREA_ALGUNOS_DIAS = "ALGUNOS DÍAS"   # los días de la semana que eligió el Admin
TAREA_UN_SOLO_DIA = "UN SOLO DÍA"     # solo el día en que se cargó
REPETICIONES_TAREA = (TAREA_TODOS_LOS_DIAS, TAREA_ALGUNOS_DIAS, TAREA_UN_SOLO_DIA)
# Cómo se llaman en las pastillas de SE REPITE (la maqueta que vio el dueño).
NOMBRE_REPETICION_TAREA = {
    TAREA_TODOS_LOS_DIAS: "TODOS LOS DÍAS",
    TAREA_ALGUNOS_DIAS: "ELEGIR DÍAS",
    TAREA_UN_SOLO_DIA: "SOLO HOY",
}

# Lo que se anota de cada vez que una tarea toca (una "aparición": la tarea y el
# día del local). HECHA hay una sola por aparición (lo cuida un índice único);
# POSPUESTA, una fila por cada vez, con quién, cuándo y los minutos.
ACCION_TAREA_HECHA = "HECHA"
ACCION_TAREA_POSPUESTA = "POSPUESTA"
ACCIONES_TAREA = (ACCION_TAREA_HECHA, ACCION_TAREA_POSPUESTA)

# Las dos teclas del aviso: POSPONER 5 MIN y POSPONER 10 MIN.
MINUTOS_PARA_POSPONER = (5, 10)

# Cómo está una aparición en la grilla. No se guarda: sale de la hora, de lo
# anotado y del reloj (estado_de_la_tarea).
TAREA_HECHA = "HECHA"
TAREA_ATRASADA = "ATRASADA"     # ya es la hora (o pasó) y nadie la hizo: avisa
TAREA_PRONTO = "PRONTO"         # falta menos de MINUTOS_TAREA_PRONTO
TAREA_MAS_TARDE = "MÁS TARDE"
TAREA_NO_SE_HIZO = "NO SE HIZO"  # de un día que ya terminó: queda en el historial
ESTADOS_TAREA_DEL_DIA = (TAREA_HECHA, TAREA_ATRASADA, TAREA_PRONTO, TAREA_MAS_TARDE, TAREA_NO_SE_HIZO)

# Desde cuántos minutos antes una tarea sale "EN 18 MIN" en ámbar.
MINUTOS_TAREA_PRONTO = 30

# El aviso la muestra en letra grande: más larga que esto no entra y es casi
# seguro un texto pegado sin querer.
LARGO_MAXIMO_TAREA = 80

DIAS_DE_LA_SEMANA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
DIAS_DE_LA_SEMANA_CORTOS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")


def revisar_tarea(texto) -> str:
    """El texto de una tarea como se guarda: sin espacios de más ni caracteres
    invisibles, con las mayúsculas como las escribieron (el dueño las carga en
    mayúscula). ValueError si queda vacío o pasa de LARGO_MAXIMO_TAREA."""
    tarea = " ".join(_sin_invisibles(texto).split())
    if not tarea:
        raise ValueError("Escribí qué hay que hacer (por ejemplo, PRENDER LAS LUCES DE AFUERA).")
    if len(tarea) > LARGO_MAXIMO_TAREA:
        raise ValueError(f"Es muy larga: escribí la tarea con hasta {LARGO_MAXIMO_TAREA} letras.")
    return tarea


def hora_de_tarea(texto) -> str:
    """
    La hora de una tarea como se guarda, "HH:MM", a partir de como la escriban:
    "19:30", "19.30", "19,30" (el punto del teclado numérico), "1930", "730"
    (07:30), "7:05", "19" (19:00) o con "hs" al final. ValueError si no se
    entiende o no es una hora del reloj: "24:00", "19:60" o "7:5" (¿07:05 o
    07:50?) no se adivinan.
    """
    escrito = " ".join(_sin_invisibles(texto).split()).lower()
    for final in ("hs.", "hs", "h"):
        if escrito.endswith(final):
            escrito = escrito[:-len(final)].strip()
            break
    if not escrito:
        raise ValueError("Escribí a qué hora hay que hacerla (por ejemplo, 19:30).")
    for separador in (".", ",", " "):
        escrito = escrito.replace(separador, ":")
    while "::" in escrito:  # "19 : 30" o "19 .30": un solo separador
        escrito = escrito.replace("::", ":")
    if ":" in escrito:
        horas, _, minutos = escrito.partition(":")
        bien_escrita = 1 <= len(horas) <= 2 and len(minutos) == 2
    elif len(escrito) in (3, 4):
        horas, minutos = escrito[:-2], escrito[-2:]
        bien_escrita = True
    else:
        horas, minutos = escrito, "00"
        bien_escrita = len(escrito) in (1, 2)
    # isascii: isdigit() también acepta otros números de Unicode ("١٩").
    bien_escrita = bien_escrita and all(parte.isascii() and parte.isdigit() for parte in (horas, minutos))
    if not bien_escrita or int(horas) > 23 or int(minutos) > 59:
        raise ValueError(f'No entiendo la hora "{" ".join(str(texto or "").split())}": escribila como 19:30 (o 1930).')
    return f"{int(horas):02d}:{int(minutos):02d}"


def revisar_repeticion(repeticion, dias_semana=None) -> tuple:
    """
    (repeticion, días como se guardan) de lo que eligió el Admin en SE REPITE.
    `dias_semana` son los números de los días de ELEGIR DÍAS (0 = lunes ... 6 =
    domingo, como date.weekday()): se guardan en orden y sin repetir, "0,2,4". Solo
    cuentan con TAREA_ALGUNOS_DIAS (con las otras se guardan como None), y ahí hace
    falta al menos uno. Con los siete es lo mismo que todos los días.
    """
    if repeticion not in REPETICIONES_TAREA:
        raise ValueError("Elegí cuándo se repite la tarea: todos los días, algunos días o solo hoy.")
    if repeticion != TAREA_ALGUNOS_DIAS:
        return repeticion, None
    dias = set()
    for dia in dias_semana or ():
        if isinstance(dia, bool) or not isinstance(dia, int) or not 0 <= dia <= 6:
            raise ValueError("Los días de la semana van del 0 (lunes) al 6 (domingo).")
        dias.add(dia)
    if not dias:
        raise ValueError("Elegí al menos un día de la semana.")
    if len(dias) == len(DIAS_DE_LA_SEMANA):
        return TAREA_TODOS_LOS_DIAS, None
    return repeticion, ",".join(str(dia) for dia in sorted(dias))


def dias_de_la_tarea(dias_guardados) -> tuple:
    """Los días de la semana de una tarea de ELEGIR DÍAS como números (0 = lunes),
    a partir de como los guarda revisar_repeticion ("0,2,4"). Sin días, ()."""
    return tuple(int(dia) for dia in (dias_guardados or "").split(",") if dia.strip())


def _como_fecha(fecha) -> date:
    return fecha if isinstance(fecha, date) else date.fromisoformat(str(fecha)[:10])


def nombre_del_dia(fecha) -> str:
    """Un día (date o "YYYY-MM-DD") como lo dice la cabecera: "lunes 03/11"."""
    fecha = _como_fecha(fecha)
    return f"{DIAS_DE_LA_SEMANA[fecha.weekday()]} {fecha:%d/%m}"


def texto_se_repite(repeticion, dias_guardados=None, dia=None) -> str:
    """La columna "Se repite" de TODAS LAS TAREAS: "Todos los días", "Lun · Mié ·
    Vie" o "Solo el lunes 03/11" (`dia`, el de una tarea de un solo día)."""
    if repeticion == TAREA_ALGUNOS_DIAS:
        return " · ".join(DIAS_DE_LA_SEMANA_CORTOS[d] for d in dias_de_la_tarea(dias_guardados))
    if repeticion == TAREA_UN_SOLO_DIA:
        return f"Solo el {nombre_del_dia(dia)}"
    return "Todos los días"


def texto_minutos(minutos) -> str:
    """Un rato en minutos como lo lee una persona: "18 min", "1 h 12 min", "2 h"
    (ATRASADA · 1 h 12 min, EN 18 MIN)."""
    horas, resto = divmod(max(0, int(minutos)), 60)
    if not horas:
        return f"{resto} min"
    return f"{horas} h {resto} min" if resto else f"{horas} h"


def estado_de_la_tarea(hecha: bool, dia_ya_termino: bool, momento: datetime, ahora: datetime) -> str:
    """
    Cómo está una tarea en un día (ESTADOS_TAREA_DEL_DIA). HECHA gana siempre; si
    el día del local ya terminó y nadie la hizo, NO SE HIZO (no vuelve a avisar).
    Si no, desde su `momento` en punto está ATRASADA (es la que avisa), y antes,
    PRONTO si falta menos de MINUTOS_TAREA_PRONTO o MÁS TARDE.
    """
    if hecha:
        return TAREA_HECHA
    if dia_ya_termino:
        return TAREA_NO_SE_HIZO
    if momento <= ahora:
        return TAREA_ATRASADA
    if momento - ahora < timedelta(minutes=MINUTOS_TAREA_PRONTO):
        return TAREA_PRONTO
    return TAREA_MAS_TARDE


def numeros_de_las_tareas(tareas) -> dict:
    """Los números de la cabecera de Tareas del Turno, de las tareas que se ven:
    cuántas faltan y todavía no es la hora (PARA HACER), cuántas ya pasaron su
    hora sin hacerse (ATRASADAS, también las pospuestas) y cuántas están HECHAS.
    Cada tarea cuenta en uno solo."""
    estados = [tarea["estado"] for tarea in tareas]
    return {
        "para_hacer": sum(estado in (TAREA_PRONTO, TAREA_MAS_TARDE) for estado in estados),
        "atrasadas": estados.count(TAREA_ATRASADA),
        "hechas": estados.count(TAREA_HECHA),
    }


# ---------------------------------------------------------------------
# RANKING DE ROTACIÓN (pedido del dueño, 2026-11-04)
# ---------------------------------------------------------------------
# Qué tan rápido sale cada artículo y para cuántos días alcanza lo que hay. La
# consulta está en repositories/rotacion_repo.py; acá, las cuentas y los textos,
# sin base, para que la copia de otra PC los haga igual que el mostrador.

# Lo que se acaba en menos de una semana pide atención: sale en rojo y se cuenta
# arriba. Una semana es lo que tarda, más o menos, en llegar un pedido nuevo.
DIAS_PARA_AVISAR_ROTACION = 7

# POR COMPRA: cuántas compras (de las que ya se vendieron enteras) se promedian
# para decir cuánto tarda en venderse un artículo. Lo eligió el dueño el
# 2026-11-04: con una sola, una semana rara (un feriado, la lluvia) da vuelta todo.
COMPRAS_PARA_PROMEDIAR = 3


def texto_tiempo_de_venta(dias, compras=1) -> str:
    """Lo que tardó en venderse una compra (`dias`, con decimales) como se lee:
    "Menos de 1 hora", "18 horas", "1 día", "2,5 días". Sin medida (None): "Sin
    compras" si el artículo nunca se compró (`compras` 0) o "Sin vender entera" si
    ninguna de sus compras terminó de venderse todavía."""
    if dias is None:
        return "Sin compras" if not compras else "Sin vender entera"
    if dias < 1:
        horas = round(dias * 24)
        if horas < 1:
            return "Menos de 1 hora"
        if horas < 24:
            return "1 hora" if horas == 1 else f"{horas} horas"
    dias = round(dias, 1)
    return "1 día" if dias == 1 else f"{texto_por_dia(dias)} días"


def unidades_por_dia(vendidas, dias: int) -> float:
    """Lo vendido en el período repartido en sus días, con dos decimales: 3
    unidades en 30 días son 0,1 por día, no 0."""
    if dias <= 0:
        raise ValueError("El período tiene que tener al menos un día.")
    return round(vendidas / dias, 2)


def dias_que_alcanza(stock, vendidas, dias: int):
    """Para cuántos días alcanza `stock` si se sigue vendiendo como en el período
    (`vendidas` en `dias`). En días enteros y para abajo: con dos días y medio de
    mercadería, el tercero ya falta. None si no se vendió nada (a ese ritmo no se
    acaba nunca) y 0 sin stock (0 o negativo). Se cuenta con lo vendido y no con
    unidades_por_dia, que viene redondeado."""
    if vendidas <= 0:
        return None
    if stock <= 0:
        return 0
    return int(stock * dias // vendidas)


def se_acaba_pronto(alcanza) -> bool:
    """Si un artículo se queda sin mercadería antes de DIAS_PARA_AVISAR_ROTACION
    (`alcanza`, de dias_que_alcanza). Sin stock también: ya se acabó."""
    return alcanza is not None and alcanza < DIAS_PARA_AVISAR_ROTACION


def texto_por_dia(valor) -> str:
    """Las unidades por día como se leen: "12", "1,5", "0,03" (coma decimal y sin
    ceros de más)."""
    texto = f"{float(valor):.2f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",")


def texto_alcanza(alcanza) -> str:
    """La columna "Alcanza para": "12 días", "1 día", "Sin stock" o, si no se vendió
    nada en el período, "Sin ventas"."""
    if alcanza is None:
        return "Sin ventas"
    if alcanza <= 0:
        return "Sin stock"
    return "1 día" if alcanza == 1 else f"{alcanza} días"
