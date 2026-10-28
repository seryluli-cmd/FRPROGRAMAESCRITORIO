"""Valores y cuentas compartidos por el kiosko, sin dependencias de interfaz ni base."""

import unicodedata


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
TURNOS_DOMINGO = (TURNO_MANANA, TURNO_NOCHE)

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
