# FRKiosko — Sistema de Kiosko

Aplicación de escritorio (Windows) en **Python + PySide6 (Qt)**, con **SQLite**
local, para manejar un kiosko: ventas por código de barras, stock, compras,
caja con número, cierres de turno, reportes y usuarios con permisos. La usan el
Admin y las empleadas desde la PC del mostrador.

**De dónde viene:** salió de CYBERCONTROL (el programa del cyber, repo
`seryluli-cmd/CYBERCONTROL`) el 2026-10-27, copiando la base de código y
sacando todo lo de PCs, Miembros, Bonos, Trámites, PlayStation 5 y Cliente PC.
Quedó la misma lógica de turnos, cajas, cierres, usuarios y permisos. Es otro
negocio, otro repo (`seryluli-cmd/FRPROGRAMAESCRITORIO`) y otra base: arranca
de cero en `data_fr/` y no abre ni importa la base de CYBERCONTROL. Desde el
2026-10-29 es un proyecto aparte: los arreglos no se pasan de un repo al otro.

Para la guía de uso pensada para quien opera el kiosko (no técnica), ver
[LEEME.txt](LEEME.txt). Este README es la referencia técnica: para cualquier
tarea de código, leer esto primero en vez de explorar archivo por archivo.
Recién si hace falta el detalle exacto de una función, ir a buscarla
puntualmente (está indexada acá por nombre y archivo).

## Calendario del kiosko — corrección del 29/10/2026

Por indicación del dueño, FRKiosko usa **tres turnos todos los días, de lunes
a domingo**. Se eliminó la excepción dominical de dos turnos heredada de
CyberBIOS.

| Turno | Horario | Aviso de cierre | Cierre forzoso si sigue abierta |
|---|---|---|---|
| Mañana | 06:00–14:00 | 13:55 | 15:00 |
| Tarde | 14:00–22:00 | 21:55 | 23:00 |
| Noche | 22:00–06:00 del día siguiente | 05:55 del día siguiente | 07:00 del día siguiente |

El día comercial sigue siendo de 06:00 a 06:00: por ejemplo, una venta del
lunes a las 02:00 pertenece a la Noche del domingo. La asignación al turno
de la caja y la tolerancia de apertura se conservan; los horarios de la
tabla no reemplazan esas reglas. El cierre forzoso espera si hay un cobro
o formulario abierto.

La corrección alcanza el calendario de `turnos.py`, las etiquetas de las
pantallas, los reportes y turnos faltantes, los cierres y los datos preparados
para Gestión Central: `mañana`, `tarde` y `noche`, también el domingo.
No requiere una migración del esquema ni reescribe las ventas o los cierres
ya guardados. Tampoco modifica el proyecto FRWEB ni genera un nuevo ejecutable.

**Validación previa a la integración:** 714 pruebas ejecutadas, 712 aprobadas
y 2 omitidas por ser exclusivas de Windows. Se verificaron el Login, la
ventana principal y el reporte dominical con Qt offscreen y una base de
prueba de 365 días. `tests/test_domingo.py` cubre cada minuto de la semana,
los límites de los turnos, avisos y cierres forzosos, y la conciliación de
los tres cierres del domingo con reportes y datos para la app, incluida
la madrugada del lunes.

## Stack

- **Python 3.10+**, sin build ni empaquetado en desarrollo (se corre
  directo con `python main.py`).
- **PySide6** (Qt) para toda la UI — ventanas/diálogos, sin HTML/web.
- **SQLite** (`sqlite3` de la librería estándar) como única base de datos,
  un solo archivo `data_fr/kiosko.db`. Todo acceso pasa por el context manager
  `conexion_db()` en `database.py` (commit al salir bien, rollback si hay
  excepción, siempre cierra) y con `PRAGMA foreign_keys = ON`.
- **PyInstaller** (`Kiosko.spec`) para armar el `.exe` final (`FRKiosko.exe`) —
  empaqueta `main.py` + `assets/`; la carpeta `data_fr/` (con la base) **no** se
  empaqueta, queda al lado del `.exe` real (`database.py` detecta `sys.frozen`
  para ubicarla ahí en vez de dentro del temp de extracción).
- Tests con `unittest` de la librería estándar
  (`python -m unittest discover tests`).

## Arquitectura: repositorio + ventana

El código separa **acceso a datos** (`repositories/`, sin Qt) de **UI**
(`ui/`, sin SQL). Comparten `database.py`, `dominio.py` y `turnos.py`.
`main.py` es el único punto de entrada. Ver las reglas en `CLAUDE.md`.

## Archivos

| Archivo | Contenido |
|---|---|
| [main.py](main.py) | Entry point. Clase `Aplicacion` alterna `LoginWindow` ↔ `MainWindow` (para poder cambiar de operador sin cerrar el programa). `aplicar_estilo(app)` pone la hoja de estilos Qt global ([ui/hoja_de_estilos.py](ui/hoja_de_estilos.py): botones `primario`/`peligro`/`barra` vía `setProperty("clase", ...)`) y fija el esquema de color CLARO. Instancia única por PC (un socket en el puerto 8908 como candado). `sys.excepthook` propio: cualquier excepción no capturada se loguea en `data_fr/errores.log` y muestra un cartel. Arranca las copias automáticas, el hilo de envíos a la app de gastos y el servidor de administración remota. |
| [database.py](database.py) · [database_esquema.py](database_esquema.py) · [database_esquema_cajas.py](database_esquema_cajas.py) · [database_esquema_envios.py](database_esquema_envios.py) · [database_migraciones.py](database_migraciones.py) | Conexiones, claves y copias; creación de tablas e índices (las de las cajas con número y la cola de envíos, en su propio archivo); la versión del esquema (`VERSION_ESQUEMA`, hoy 1) con los pasos que llevan una base vieja a la nueva (`PASOS`, hoy ninguno; antes del primero queda una copia `antes_de_migrar_...` en data_fr/backups) y el cerrojo que no deja abrir una base de CYBERCONTROL ni una de un FRKiosko más nuevo (`comprobar_base_kiosko`). `get_connection` espera hasta 30 s si la base está ocupada. Ver modelo de datos abajo. |
| [turnos.py](turnos.py) · [dominio.py](dominio.py) | Calendario del local y constantes/reglas puras de negocio (roles, estados de venta, métodos de pago, turnos, el origen KIOSKO, la cuenta del cobro, el formato de pesos, el margen de Artículos, el stock bajo el mínimo y la suma de la fila TOTAL de Reportes). |
| [repositories/](repositories/) | Capa de datos, un archivo por tema: artículos, compras, configuración, impresiones, reportes, el detalle del día, turnos (con turnos faltantes y lo vendido en la ventana de un turno, `turnos_ventas_repo.py`), cajas con número (`cajas_repo.py` los datos, `relevo_repo.py` las reglas al entrar y el cierre forzoso, `control_cierres_repo.py` lo que se controla después), copias de seguridad, envíos a la app de gastos, la vuelta sola del Admin, administración remota, usuarios y ventas. |
| [ui/](ui/) | Una ventana/diálogo por pantalla — ver detalle abajo. `ui/hoja_de_estilos.py` es la hoja de estilos de todo el programa. `ui/utils.py` tiene los helpers compartidos (formato de pesos, decorador de manejo de errores, encadenar Enter entre campos). `ui/en_segundo_plano.py` corre en un hilo aparte lo que espera la red (la app de gastos, una carpeta de otra PC), para que la pantalla no se trabe. Configuración ADMIN, Administrar Kiosko, Caja y Cierre de Turno usan el diseño "clara con cabecera cyber" que eligió el dueño el 2026-10-26: las piezas están en `ui/piezas_ventana.py` y los colores en `ui/hoja_de_estilos.py`, siempre por objectName o "clase". |
| [admin_remoto/](admin_remoto/) · [repositories/admin_remoto_repo.py](repositories/admin_remoto_repo.py) · [ui/admin_remoto_dialogo.py](ui/admin_remoto_dialogo.py) | Administrar desde otra PC del local (ver la sección propia más abajo). |
| [servidor_red.py](servidor_red.py) · [errores.py](errores.py) | El servidor HTTP del mostrador (puerto 8909, distinto del 8899 de CYBERCONTROL para que los dos programas convivan en una PC): solo atiende `POST /admin/...` de la administración remota; y el registro de fallos compartido con la UI. |
| [tests/](tests/) | Tests de repositorios, servidor y UI sobre bases SQLite temporales (no tocan `data_fr/kiosko.db`). |
| [armar_base_de_prueba.py](armar_base_de_prueba.py) | Arma la base de prueba en `data_prueba/` (un año inventado); se abre con `python main.py --base data_prueba`. Ver "Cómo probarlo en local". |
| [Kiosko.spec](Kiosko.spec) | Config de PyInstaller para generar `dist/FRKiosko.exe`. |
| [assets/](assets/) | Ícono de la app: el carrito (elegido por el dueño el 2026-10-28). Se dibuja en `icono.svg`; `icono.ico` y `icono.png` salen de ahí con `python assets/armar_icono.py`. |
| `data_fr/backups/` | Copias automáticas de la base (después de cada Cierre de Turno y cada 8 horas; todas las de 3 días y una por día hasta 30). |

## Modelo de datos (SQLite, `database_esquema.py`)

- **`usuarios`** — `id` PK, `nombre`, `clave_hash` (`salt$sha256hex`), `rol`
  (`ADMIN` | `EMPLEADA`), `activo` (soft-delete: nunca se borra un usuario con
  historial), `fecha_creacion` y las columnas `permiso_*` de
  `usuarios_repo.PERMISOS_EMPLEADA`.
- **`sesiones`** — `id` PK, `usuario_id`, `fecha_hora`, `desde_ip` (NULL = en
  el mostrador; la IP de la otra PC si el Administrador entró desde otra PC
  del local). Una fila por cada login exitoso (`usuarios_repo._registrar_sesion`).
  Junto con las ventas es la única pista para saber quién podría ser responsable
  de un turno sin cerrar (`turnos_faltantes_repo._responsables_del_mes`).
- **`marcas`** / **`rubros`** — catálogos simples `id` + `nombre` (único).
  Las marcas se crean al vuelo escribiendo un nombre nuevo en el combo del
  artículo (y solo el Admin las corrige desde "Gestionar Marcas"); los **rubros
  son un catálogo cerrado**, se gestionan aparte (`DialogoGestionRubros`).
- **`articulos`** — PK es `codigo` (el código de barras o uno corto cargado a
  mano), `descripcion`, `marca_id`/`rubro_id` (FKs nullable), `precio_venta`,
  `precio_compra`, `stock` (**puede quedar negativo a propósito** si se vende
  antes de cargar la compra — nunca bloquea una venta), `stock_minimo` (solo
  para el aviso visual), `fecha_creacion`, `fecha_modif`.
- **`compras`** (cabecera: `fecha`, `usuario_id`) + **`compra_detalle`**
  (`compra_id`, `articulo_codigo`, `cantidad`, `costo_unitario`, `stock_antes`,
  `stock_despues`) — es la vía normal para que el stock suba
  (`compras_repo.registrar_compra`, transacción única que también actualiza
  `articulos.stock`/`precio_compra`).
- **`ajustes_stock`** y **`cambios_codigo`** — lo que hace ORDENAR Stock:
  cada corrección de stock a mano (antes, después, quién, cuándo) y cada
  cambio de código de un artículo. Salen en Movimientos.
- **`ventas`** (cabecera: `fecha`, `usuario_id`, `turno` — se calcula solo
  con `calcular_turno(fecha_hora)`; `total`, `estado` `CONFIRMADA`|`ANULADA`
  — **una venta nunca se borra**, anular solo cambia el estado y guarda
  `anulada_por`/`anulada_fecha`/`anulada_motivo`; `origen`, hoy siempre
  `KIOSKO`) + **`venta_detalle`** (`descripcion` es una foto del nombre al
  momento de vender) + **`venta_pagos`** (una venta puede tener varias filas —
  pago repartido Efectivo + Digital; índice `idx_venta_pagos_venta`).
- **`cierres_turno`** — `fecha`/`turno` del cierre, `usuario_id` (quién
  cerró), `fecha_cierre` (momento exacto — es el límite "desde" del próximo
  turno), `fondo_cambio`/`ventas_efectivo`/`ventas_digital`/`monto_a_retirar`,
  más `monto_contado`/`diferencia`/`verificado_por`/`fecha_verificacion`
  (nullable, los completa el Admin después desde Control de Cierres) y
  `kiosko_efectivo`/`kiosko_digital` (el desglose por origen: hoy un solo origen).
- **Cajas con número** (`database_esquema_cajas.py`; reglas en
  `repositories/relevo_repo.py`). **`cajas`**: una fila por caja (su `id` es el
  número que se ve), con `fecha`/`turno` decididos al ABRIRLA,
  `abierta_por`/`abierta_en`, `cambio_esperado` y `cambio_contado` (NULL = no
  contó: la abrió la misma persona que acababa de cerrar la anterior),
  `responsable_id` (cambia en un relevo), `cierre_id` (NULL = abierta; nunca hay
  dos abiertas) y `cierre_forzoso`. **`relevos_caja`**: cada vez que la caja
  pasa de mano sin cerrarse. **`ventas_caja`**: en qué caja quedó cada venta y
  `cargada_por` (el Admin que la cobró a nombre de la responsable).
  **`verificaciones_cierre`**: cada conteo del sobre.
- **`envios_pwa`** (`database_esquema_envios.py`) — la cola de cierres que se
  mandan a la app de gastos (ver más abajo): una fila por cierre encolado con
  su estado (`PENDIENTE`/`ENVIADO`/`ERROR`), intentos y último error.
- **`configuracion`** — tabla genérica clave/valor: el fondo de cambio, el
  indicador de rubros iniciales, si está prendida la entrada desde otra PC, si
  está prendido el envío a la app de gastos y su sesión, las otras carpetas de
  copias. Las claves exactas están en los repositorios que las usan (la del
  fondo de cambio, `database.CLAVE_FONDO_CAMBIO`), y todos la leen y graban con
  `config_repo.leer` / `config_repo.guardar`.
- **`calcular_turno(fecha_hora)`** (`turnos.py`) — Mañana 06-14, Tarde
  14-22, Noche 22-06 (cruza medianoche), **todos los días, incluidos los
  domingos**. Se muestran como Mañana, Tarde y Noche (`turnos.etiqueta_turno`).
  ⚠️ Para el **cierre de turno**, la etiqueta y la **`fecha`** usan el momento
  en que **empezó** el turno (el `fecha_cierre` del cierre anterior, con la tolerancia de
  `TURNO_GRACIA_MIN`, 60 min: `turnos.turno_que_arranca_tras_un_cierre`), no el
  clic de cerrar. ⚠️ **Con una caja abierta, el turno y el día del cierre son los
  de la caja** (decididos al abrirla).
- **`turnos.turno_vencimiento(dia, turno)`** — su fin (`turnos.fin_del_turno`)
  + `MINUTOS_PARA_CIERRE_FORZOSO` (60): a esa hora la caja se cierra sola y el
  turno pasa a contar como sin cerrar. El botón Cierre de Turno titila desde
  `turnos.inicio_del_aviso_de_cierre` (5 min antes del fin).
  **`turnos_repo.turnos_faltantes()`** cruza los turnos esperados del mes en
  curso contra `cierres_turno` y devuelve los vencidos sin cerrar, con quién
  vendió o inició sesión en esa ventana.

**Seed inicial** (`database.py`, corre en cada arranque pero es idempotente):
si `usuarios` está vacía, crea **"Administrador" / clave 1234** con rol ADMIN
(el login avisa que hay que cambiarla). Si no existe la clave `fondo_cambio`, la
crea en `50000`. Si no corrió antes, siembra los 4 rubros default.

**Backups** (`repositories/copias_repo.py`): un hilo que arranca `main.py` en
el mostrador revisa cada minuto y copia `data_fr/kiosko.db` →
`data_fr/backups/frkiosko_AAAA-MM-DD_HHMMSS.db` en caliente (Online Backup API
de SQLite) después de cada Cierre de Turno y, si no hubo ninguno, cada 8 horas.
Cada copia va además a las "otras carpetas" que elige el Admin desde la pantalla,
hasta 5 (otro disco, una carpeta compartida de otra PC como
`\\192.168.1.112\Backups`; usuario y clave de red se le pasan a Windows con
`cmdkey`, no se guardan). El prefijo `frkiosko_` es a propósito: CYBERCONTROL
llama a las suyas `kiosko_...` con la misma regla de borrado, y con el mismo
nombre dos programas en una misma carpeta se borraban las copias entre sí.
Quedan todas las de los últimos 3 días con copias y una por día hasta 30. Pantalla: Usuarios → "Copias de Seguridad"
(`ui/copias_dialogo.py`), con "Hacer copia de seguridad ahora" y una copia
suelta a un pendrive (`database.copiar_backup_a`). Esos dos botones y "Agregar"
otra carpeta corren en un hilo aparte (`ui/en_segundo_plano.py`): con una PC de
la red apagada la pantalla no se traba. Mientras prueba una carpeta nueva, la
ventana "Agregar carpeta" no se cierra hasta que la carpeta contesta: así no se
pisa la lista de carpetas.

## Pantallas (`ui/`)

`MainWindow` (`ui/main_window.py`) tiene arriba la barra oscura con los mismos
botones para todos (Vender, Impresiones, Admin Kiosko, Config ADMIN, Caja, Cierre
de Turno, Clave y Operador; los que no le tocan a alguien se ven igual y no
hacen nada) y, debajo, un panel de inicio con tres accesos grandes (Venta de
Mercadería, Impresiones y Caja). Cada módulo se abre como un diálogo modal.

**Ingreso con caja** (`ui/ingreso_caja.py`, entre el login y la ventana
principal; reglas en `relevo_repo.situacion_al_entrar`). Una empleada no entra
sin caja: si no hay ninguna abierta, abre una contando el Cambio Fijo (si la
abre la misma persona que acaba de cerrar la anterior, no cuenta); si la caja
abierta es de otra y su turno sigue, la **recibe** contando todo el cajón; si el
turno de esa caja ya terminó, la **cierra en ausencia** de la otra y después
abre la suya. Si el Admin cobró algo sin ninguna caja abierta, pasa a la caja que
se abre: quien la abre cuenta todo el cajón (el cambio y esa plata) y va en su
sobre (pedido del dueño, 2026-10-29; antes se cerraba aparte). El conteo
es **a ciegas** (`DialogoContarPlata`). El Admin entra directo, sin caja: lo que
cobra queda a nombre de la responsable de la caja abierta, con
`ventas_caja.cargada_por`.

**En la ventana principal**, al lado del nombre se ve la caja ("Caja Nº 12 ·
Mañana"). Cada 10 s `MainWindow._revisar_la_caja` mira
`relevo_repo.estado_de_la_caja`: desde 5 minutos antes del fin del turno el
botón **Cierre de Turno titila en rojo** y a la hora del fin hace el
**cierre forzoso** (`relevo_repo.cierre_forzoso_si_corresponde`) y vuelve al
ingreso (el Admin se queda). Si hay un cobro a medias, espera.

**Para cualquier usuario (Admin o Empleada):**
- **Ventas** (`ventas_window.py`, `VentasWindow`, con el diseño "B" que eligió
  el dueño: total y COBRAR grandes a la derecha, dibujos en `ui/ventas_dibujos.py`)
  — escaneo por código de barras (Enter en el campo código dispara
  `_escanear()`; Enter con el campo vacío y carrito no vacío pasa directo a
  cobrar). Atajos F5/F6/F7 abren el buscador (`buscar_articulo.py`) por
  código/descripción/marca. Botón `*` "Cant." fija la cantidad para el próximo
  escaneo. Doble clic en $ Unit. **solo si es Admin**. Avisa (no bloquea) si el
  stock proyectado queda por debajo de `stock_minimo`. Cobra con
  `ui/dialogo_pago.DialogoPago`: Efectivo y Digital siempre a la vista y suman
  el total; "Paga con" da el vuelto; un Enter cobra siempre. Confirmar llama a
  `ventas_repo.confirmar_venta`.
- **Impresiones** (`impresiones_window.py`, `DialogoImpresiones`) — botón de la
  barra al lado de "Vender": cobro rápido del artículo de impresiones
  (`dominio.CODIGO_ARTICULO_IMPRESIONES`, el código 4). Se escribe la cantidad,
  Enter abre la ventana de cobro y otro Enter cobra. Se graba con
  `impresiones_repo.cobrar_impresiones` como una venta de kiosko común del
  artículo. Si el artículo no está cargado con ese código, avisa y no abre.
- **Caja** (`caja_window.py`, `CajaWindow`) — solo lectura, resumen del turno
  en curso vía `turnos_repo.resumen_turno_actual()`: número de caja y
  responsable, caja inicial (el cambio con que arrancó), caja actual (solo el
  efectivo cobrado: `resumen["monto_a_retirar"]`, lo mismo que A RETIRAR),
  ventas efectivo/digital y la tabla de dónde vino la plata
  (Kiosko e Impresiones, cada uno con su efectivo y digital; `TablaDeNegocios`
  de `ui/tarjeta_cierre.py`).
- **Cierre de Turno** (`caja_window.py`, `CierreTurnoWindow`) — cualquiera
  cierra su propio turno. Muestra la tarjeta (`ui/tarjeta_cierre.py`,
  `TarjetaCierreDeTurno`: cabecera con la caja y el turno, A RETIRAR EN EFECTIVO
  en verde y el TOTAL en azul, la tabla de negocios y el Cambio Fijo abajo) y,
  al confirmar, llama a `turnos_repo.cerrar_turno(usuario['id'])`:
  `monto_a_retirar` = lo vendido en efectivo (`dominio.monto_a_retirar`; el
  cambio con que arrancó la caja queda en el cajón), el mismo que muestran la
  tarjeta y Caja antes de cerrar (`resumen_turno_actual()["monto_a_retirar"]`).
  Si quien cierra no es la responsable de la caja (por número de usuario,
  `cajas_repo.cerrada_en_ausencia`), queda anotado como cerrada en su ausencia.
  **Kiosko e Impresiones van en renglones separados** (`resumen["kiosko_solo_*"]` e `["impresiones_*"]`); los dos suman
  lo que se graba como Kiosko (`kiosko_efectivo`/`kiosko_digital`). Con el envío
  a la app de gastos prendido, antes del aviso "Turno cerrado" se ve la barra
  "ENVIANDO CIERRE DE TURNO" (`ui/envio_pwa_progreso.py`).
- **Clave** (`usuarios_window.DialogoCambiarClave`) — cambia la clave propia
  pidiendo la actual.
- **🔄 Operador** — vuelve al ingreso sin cerrar el programa.

**Administrar Kiosko** (`ui/administrar_kiosko_window.py`): Artículos, Compras,
Consulta de Ventas, Reportes y Control de Cierres pueden delegarse por permiso
individual a una empleada; Control de Stock y Usuarios son exclusivos del Admin.
Lo que una encargada no tiene habilitado lo ve en gris, con candado y el porqué.
- **Artículos** (`articulos_window.py`, `ArticulosWindow`) — grilla con
  búsqueda en vivo (`ui/articulos_tabla.py`, compartida con ORDENAR Stock),
  pinta en rojo el stock de los artículos que quedaron por debajo del mínimo
  (`dominio.bajo_el_minimo`: `stock < stock_minimo`). `DialogoArticulo` para
  alta/edición (código no editable una vez creado; marca se tipea y se crea al
  vuelo; **rubro es un combo cerrado**; el stock es solo lectura); su
  calculadora de margen usa `dominio.precio_con_margen` y
  `dominio.costo_sin_margen`. Botones
  **Gestionar Rubros** (`DialogoGestionRubros`) y, solo para el Admin,
  **Gestionar Marcas** (`DialogoGestionMarcas`: renombrar, juntar, borrar).
  `DialogoMovimientos` muestra el historial de un artículo
  (`articulos_repo.obtener_movimientos`: compras, ventas, ajustes y cambios de
  código).
- **ORDENAR Stock** (`ordenar_stock_window.py`, `OrdenarStockWindow`) — botón
  de Artículos que solo ve el Admin y que pide una contraseña fija (en el código
  está solo su hash con salt, `articulos_repo.CLAVE_ORDENAR_STOCK`; este repo es
  público). La grilla con la columna Stock para escribir: Enter guarda y pasa al
  de abajo. Cada cambio pasa por `articulos_repo.ajustar_stock` (vuelve a exigir
  Admin y contraseña, anota en `ajustes_stock`). También corrige el CÓDIGO de un
  artículo (doble clic): `articulos_repo.cambiar_codigo` lleva ventas, compras y
  ajustes al código nuevo y lo anota en `cambios_codigo`.
- **Control de Stock** (`control_stock_window.py`, `VentanaControlStock`;
  solo Admin) — los artículos con stock de 1 para arriba, de la A a la Z sin
  mirar mayúsculas ni acentos (`articulos_repo.listar_para_control_de_stock`),
  con sus unidades, para imprimirlos (`ui/imprimir.py`) con una columna
  "Contado" vacía. Solo muestra: corregir es de ORDENAR Stock.
- **Compras** (`compras_window.py`, `ComprasWindow`) — carga de mercadería por
  escaneo (mismos F5/F6/F7 que Ventas). Al escanear pide cantidad y costo.
  Confirmar llama a `compras_repo.registrar_compra` con todo el lote junto.
- **Consulta de Ventas** (`consulta_ventas_window.py`,
  `ConsultaVentasWindow`) — últimas 100 ventas, resalta ANULADA. "Anular venta"
  (solo Admin) pide motivo y llama a `ventas_repo.anular_venta`, que vuelve a
  exigir un Admin activo (`usuarios_repo.exigir_admin`) y un motivo escrito,
  **repone el stock** y marca `estado='ANULADA'` con auditoría.
- **Reportes** (`reportes_window.py`, `ReportesWindow`) — 6 pestañas:
  **Resumen de Ventas** (`reportes_repo.resumen_ventas`), **Resumen del Día**
  (`turnos_repo.resumen_del_dia`: un día abierto por turno con estado, quién
  cerró, cantidad de ventas, Kiosko / Impresiones, Efectivo/Digital, Total y la
  diferencia del sobre; con el aviso "Hoy se cerró un turno que quedó anotado en
  otro día" cuando corresponde; y abajo el **detalle de todo lo vendido**,
  `ui/reportes_resumen_dia.py` + `ui/reportes_detalle_dia.py` con datos de
  `detalle_dia_repo.detalle_del_dia`: renglón por renglón tal cual se cobró, con
  Imprimir, venta por venta y por producto con el rubro que tiene HOY cada
  artículo, y por operador), **Por Turno** (`reportes_repo.resumen_por_turno`:
  cada venta en el turno y el día de SU CAJA, no los de su hora, así suma lo
  mismo que los cierres de cada turno; una venta sin caja va por su hora),
  **Totales** (`reportes_repo.resumen_por_origen`: Kiosko / Impresiones / Total
  por turno (también por la caja), día, semana o rango, con una fila TOTAL al pie cuando hay más de un
  período, que suma `dominio.suma_de_las_filas`; las impresiones NO están
  sumadas en Kiosko),
  **Ranking de Ventas** (`reportes_repo.ranking_ventas`, por cantidad o monto) y
  **Por Operador** (`ui/reportes_operador.py`: cuánto vendió cada usuario y sus
  ventas con fecha y hora). El día del local va de 06:00 a 06:00 en todas.
- **Control de Cierres de Turno** (`control_cierres_window.py`,
  `ControlCierresWindow`; se reexporta desde `caja_window.py`) — lista
  `turnos_repo.listar_cierres()`: Turno, Caja, Responsable, Apertura, Cierre ("A
  horario", "Forzoso" o "en ausencia", en rojo), Cambio Fijo, Ventas Ef., Kiosko,
  A Retirar, Contado, Diferencia (en rojo si no coincide, desde $ 0,01:
  `dominio.coincide`). "Cargar monto contado" (solo Admin) guarda
  cada conteo en `verificaciones_cierre`. "Ver Detalle" muestra cada cierre con
  la misma tarjeta del Cierre de Turno (también el forzoso), cómo se cerró, la
  caja, los relevos, los conteos del sobre y las ventas. "Mandar a la app de
  gastos" (solo Admin) reencola un cierre. Arriba, un aviso rojo con los turnos
  del mes vencidos sin cerrar.
- **Usuarios** (`usuarios_window.py`, `UsuariosWindow`) — alta/edición de
  usuarios con sus permisos, "Borrar" (real si nunca vendió/compró/cerró un
  turno; si tiene historial, ofrece desactivarlo), "Mostrar inactivos",
  "Configurar Cambio Fijo" (`config_repo`) y "Copias de Seguridad"
  (`ui/copias_dialogo.py`).

**Configuración ADMIN** (`ui/configuracion_admin_window.py`; la abre solo el
Admin): **Accesos de Admin** (`ui/accesos_admin_window.py`: cada login con
usuario y clave, del mostrador o desde otra PC con su IP), **Entrar desde otra
PC** (`ui/admin_remoto_dialogo.py`, solo en el mostrador) y **Cierres a la app
de gastos** (`ui/envio_pwa_dialogo.py`, solo en el mostrador).

## Administrar desde otra PC (`admin_remoto/`)

Pedido del dueño (2026-10-18, en CYBERCONTROL): desde su casa entra por UltraVNC
a una PC libre del local y administra desde ahí mientras el mostrador sigue
atendiendo. Diseño y decisiones en [docs/ADMIN_REMOTO.md](docs/ADMIN_REMOTO.md).

- **Cómo se abre:** el mismo `FRKiosko.exe`, abierto desde la carpeta
  compartida del mostrador. `admin_remoto/modo.py` lo reconoce (ruta
  `\\PC\carpeta` o unidad de red) y esa copia NO abre ninguna base: le habla al
  FRKiosko de esa PC. Para probar: `python main.py --mostrador <ip>`.
- **Cómo viaja:** `POST /admin/...` en el servidor de red del mostrador (puerto
  8909). `admin_remoto/cliente.instalar` reemplaza en su módulo cada función de
  `admin_remoto/lista_blanca.py` por un representante que manda la llamada; las
  pantallas no se enteran. Por eso **ninguna pantalla importa una función suelta
  de un repo** (un test lo vigila). Los datos van con `admin_remoto/codec.py`.
  Si no se puede conectar o mandar el pedido, avisa que no encuentra el
  mostrador (`SinConexion`); si el pedido ya salió y se cortó la respuesta, avisa
  que el mostrador pudo haberlo guardado y que se fije antes de repetirlo
  (`SinRespuesta`).
- **Quién entra** (`repositories/admin_remoto_repo.py`): viene apagado; solo un
  ADMIN activo; cada ingreso queda en `sesiones.desde_ip`. El servidor
  (`admin_remoto/servidor.py`) da una sesión al azar atada a la IP, que vence a
  las 3 h sin uso; 5 claves mal desde una PC la frenan 5 minutos, y hay un tope
  de 20 claves mal en 15 minutos para todas juntas.
- **Qué no se puede desde otra PC:** vender, cobrar, abrir/cerrar cajas y
  turnos, las Copias de Seguridad, prender/apagar la entrada remota y el envío
  a la app de gastos. En la pantalla principal esos botones están y avisan
  "Esto se hace en el mostrador" (`ui.utils.solo_en_el_mostrador`); y la lista
  blanca lo rechaza igual.
- **Las dos copias tienen que ser el mismo .exe:** `lista_blanca.huella()` se
  compara al entrar.

## Cierres a la app de gastos (`repositories/envio_pwa_repo.py`)

Heredado de CYBERCONTROL (pedido del dueño, 2026-10-26): que cada Cierre de
Turno quede asentado solo en la app de gastos del celular como el cierre de
caja de ese turno. **Acá apunta a la app de FR: "Gestión Central"**
(fradministracion.netlify.app, repo `FRWEB`, proyecto de Firebase `frkioskos`,
negocio `gestionfr`), no a la de CyberBIOS. Las constantes están arriba de
`envio_pwa_repo.py`.

- **Cómo se habla con la app:** igual que un celular: login anónimo con la clave
  pública que está en el código de la PWA y `PATCH` por cierre a la colección
  `facturacion`, con `urllib`. El proyecto de Firebase tiene que tener el login
  anónimo habilitado y sus reglas tienen que dejar escribir a ese usuario (como
  en la app de CyberBIOS); "Probar la conexión" lo verifica sin escribir nada.
- **Qué viaja** (`datos_del_cierre`): `importe`, `efectivo`, `digital`, `turno`
  con el nombre de allá (`turnos.turno_para_la_app_de_gastos`: "mañana",
  "tarde", "noche", también los domingos), `fecha` (el día en que ARRANCÓ el
  turno), `registradoPor` = el NOMBRE de la **responsable de la caja**,
  `creadoEn`, `origen: "frkiosko"`, `cierreId`, `caja`, `forzoso`, `enAusencia`,
  `cerradoPor` y **`detalle`** (la tarjeta del cierre: Cambio Fijo, a retirar,
  cada negocio de `dominio.NEGOCIOS_DEL_CIERRE` con su efectivo y digital, desde
  y hasta). La app de FR todavía no muestra ese `detalle` al tocar el cierre
  (eso se portó solo a la app de CyberBIOS); lo demás lo entiende como un cierre
  cargado a mano. **Los nombres tienen que estar escritos igual en las dos
  apps.**
- **Cuándo:** `turnos_repo.cerrar_turno` deja una fila en `envios_pwa` en la
  misma transacción del cierre, solo si el envío está prendido (viene apagado).
  Un hilo (`iniciar_envios_automaticos`) lo manda en ese momento y, si falló, lo
  reintenta cada minuto esperando `intentos` minutos (hasta 60). **El cierre
  nunca espera a internet.**
- **Una sola vez:** el documento allá tiene nombre fijo
  (`frkiosko-<id>-<fecha>`): un reintento lo pisa, no lo duplica.
- **A mano:** Control de Cierres > "Mandar a la app de gastos" (solo Admin).
- **Pantalla:** Configuración ADMIN > "Cierres a la app de gastos": prender o
  apagar, los últimos envíos, "Probar la conexión" y "Reintentar ahora". Estos
  dos salen a internet desde un hilo aparte (`ui/en_segundo_plano.py`): la
  ventana no se traba y se puede cerrar mientras esperan.
- Tests: `tests/test_envio_pwa.py`, con una app de mentira que hace de Google.

## El Administrador vuelve solo a la empleada (`ui/vuelta_del_admin.py`)

A los `dominio.MINUTOS_ADMIN_VUELVE_SOLO` (10) de entrar como Administrador con
"🔄 Operador", en silencio, vuelve a quien dejó el mostrador
(`MainWindow.a_quien_volveria`, lo guarda `main.Aplicacion`), sin pedirle la
clave, solo si su caja sigue abierta a su nombre y en hora
(`repositories/vuelta_admin_repo.py`); si no, vuelve la pantalla de ingreso.
Nunca corta un cobro ni un formulario abierto. Solo en el mostrador. Tests:
`tests/test_vuelta_del_admin.py`.

## Identidad y permisos

Login por **nombre + clave** (`login_window.py`, vía
`usuarios_repo.autenticar_por_nombre`) — ignora mayúsculas/minúsculas y
espacios de más al comparar (en Python, no con el `LOWER()` de SQLite, que no
pliega acentos). `crear_usuario`/`modificar_usuario` rechazan un nombre vacío
(o de puros espacios) y que dos usuarios **activos** compartan nombre;
`crear_usuario` rechaza una clave vacía (en `modificar_usuario` la clave vacía
quiere decir "no cambiarla"). Siempre queda al menos un Administrador activo:
`modificar_usuario` (pasarlo a Empleada), `desactivar_usuario` y `borrar_usuario`
rechazan tocar al único (`usuarios_repo._exigir_que_quede_otro_admin`); "no te
podés borrar a vos mismo" sigue en la pantalla. Protección contra fuerza bruta en memoria: 5
intentos fallidos → bloqueo de 60 s para ese nombre. No hay sesión persistida:
el dict `usuario` se pasa por parámetro a cada ventana.

`rol` es `ADMIN` o `EMPLEADA`. Una empleada puede recibir permisos para
Artículos, Compras, Consulta de Ventas (sin anular), Reportes y Control de
Cierres (`usuarios_repo.PERMISOS_EMPLEADA`). Usuarios, Control de Stock,
Configuración ADMIN y Anular Venta son exclusivos del Admin. Los repos vuelven
a exigir Admin donde importa (`usuarios_repo.exigir_admin`).

⚠️ No hay cifrado de la base ni protección contra acceso directo al archivo
`data_fr/kiosko.db` — la seguridad es a nivel de la app (login).

## Manejo de errores y logging

Casi todas las acciones de UI que tocan datos están envueltas con el decorador
`@manejar_errores` (`ui/utils.py`): un `ValueError` o `PermissionError` se
muestra tal cual (es un rechazo de negocio con su mensaje); cualquier otra
excepción se loguea completa en `data_fr/errores.log` vía
`errores.registrar_error()` y se muestra un cartel genérico. `main.py` instala
además un `sys.excepthook` global. El servidor de red usa el mismo registro sin
importar Qt ni guardar claves. Lo que una pantalla corre en un hilo aparte
(`ui/en_segundo_plano.py`) le devuelve el error a la pantalla, y sale por el
mismo `@manejar_errores`. Si la ventana ya se cerró, un error inesperado igual
queda en `data_fr/errores.log` (los rechazos del repo, ValueError y
PermissionError, no).

## Cómo probarlo en local

```bash
pip install -r requirements.txt
python main.py
```

Primer arranque: se crea `data_fr/kiosko.db` solo, con el usuario
`Administrador` / clave `1234` (rol ADMIN).

**Base de prueba** (para mirar las pantallas con contenido, medir los reportes con
mucho movimiento o probar sin tocar `data_fr/`):

```bash
python armar_base_de_prueba.py
python main.py --base data_prueba
```

[armar_base_de_prueba.py](armar_base_de_prueba.py) arma en `data_prueba/` (en
`.gitignore`) un año de un kiosko inventado: unos 70 artículos, cuatro empleadas y
unas 180 ventas por día, con sus cajas, relevos, cierres (en ausencia y
forzosos), ventas del Admin sin caja que pasan a la caja siguiente, compras de los lunes, subas de precio y sobres contados. No
escribe filas a mano: pasa por las mismas funciones de los repos que el
mostrador, con el reloj corrido a cada momento del pasado, así que todo cuadra
como lo dejaría el programa. Las claves de prueba y las opciones (`--dias`,
`--escala`, `--semilla`, `--carpeta`) están en el comentario de arriba del
archivo. Solo arma en una carpeta nueva, vacía o que ya sea de prueba (tiene
`ES_BASE_DE_PRUEBA.txt`), nunca en `data_fr/`, y pide cerrar FRKiosko antes. Con
`--base` (o `--base=carpeta`), el programa avisa al abrir qué base usa y, si es
la de prueba, lo dice en el título de la ventana; ahí el envío a la app de gastos
no se puede prender.

## Tests

```bash
python -m unittest discover tests
```

Corren contra una base SQLite temporal (nunca tocan `data_fr/kiosko.db`).
714 tests al 2026-10-29. Cubren turnos, caja y cajas con número
(`tests/test_cajas.py`, `tests/test_cajas_ui.py`), el detalle del día, stock,
ORDENAR Stock, marcas, rubros (`tests/test_rubros.py`), ventas y anulaciones, el
cobro con Enter, impresiones, reportes, administrar desde otra PC
(`tests/test_admin_remoto.py`, con un mostrador de prueba en otro proceso:
`tests/mostrador_de_prueba.py`), las copias de seguridad (también la que se
guarda a mano en un pendrive), las migraciones de la base
(`tests/test_migraciones.py`, con pasos de mentira), los cierres que se mandan a
la app de gastos (`tests/test_envio_pwa.py`, con una app de mentira en vez de
Google), la vuelta sola del Admin, que siempre quede un Administrador activo, las
reglas de plata de la caja y del sobre (`tests/test_reglas_de_la_caja.py`), las
cuentas que salieron de las pantallas (margen, stock bajo el mínimo y la fila
TOTAL de Reportes, `tests/test_cuentas_de_articulos_y_reportes.py`), la tabla de
configuración y lo cobrado por medio en cada venta (`tests/test_config_repo.py`),
la base de prueba (`tests/test_base_de_prueba.py`), el formato de pesos, el
aspecto de las pantallas (Qt "offscreen") y que los botones que esperan la red no
congelen el mostrador (`tests/test_en_segundo_plano.py`).

## Empaquetado (.exe)

Instalá PyInstaller (`pip install pyinstaller`) y ejecutá
`python -m PyInstaller Kiosko.spec --clean --noconfirm`: genera
`dist/FRKiosko.exe` (app sin consola, ícono `assets/icono.ico`). La carpeta
`data_fr/` (base + backups) **no** se empaqueta — queda al lado del `.exe`
instalado, así los datos sobreviven a actualizar el programa. Con el nombre
`FRKiosko.exe` y la carpeta `data_fr/` puede convivir en la misma PC con
`CyberBios.exe` y su `data/`.

## Estado del repo

El remoto `origin` es `https://github.com/seryluli-cmd/FRPROGRAMAESCRITORIO`
(público: nunca escribir una clave real en el código, en un test ni en un doc).
No hay CI configurada; el `.exe` se arma con PyInstaller. Ver
[LEEME.txt](LEEME.txt) para la guía de uso y [CLAUDE.md](CLAUDE.md) para las
reglas de trabajo. La historia de las decisiones anteriores al 2026-10-27 está
en el repo de CYBERCONTROL (`docs/HISTORIAL.md` de allá).
