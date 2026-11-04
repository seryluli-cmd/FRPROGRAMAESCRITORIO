# Guía de trabajo para Claude — FRKiosko (Sistema de Kiosko)

## Por qué existe este archivo

Este programa salió de CYBERCONTROL (el programa del cyber del dueño) el
2026-10-27: se copió la base de código y se sacó todo lo de PCs, Miembros,
Bonos, Trámites, PlayStation 5 y Cliente PC. Quedó el kiosko puro: ventas,
stock, compras, cajas con número, cierres de turno, reportes, usuarios con
permisos, copias de seguridad, administración desde otra PC y el envío de los
cierres a la app de gastos. Hereda las reglas de trabajo de CYBERCONTROL, que
son **el contrato para que el código siga ordenado** cuando crezca.

Es otro negocio, otro repo (`seryluli-cmd/FRPROGRAMAESCRITORIO`, público) y
otra base (`data_fr/`, arranca de cero). Desde el 2026-10-29 es un proyecto
aparte (pedido del dueño: "olvidate de cybercontrol, ya es otro proyecto"):
los arreglos de acá no se llevan a CYBERCONTROL ni al revés, salvo que él lo
pida; nada de PCs vuelve acá.

---

## La arquitectura en una línea

```
main.py  →  ui/  →  repositories/  →  database.py  →  data_fr/kiosko.db
           (qué       (reglas de       (esquema y
            se ve)     negocio)         conexión)

        dominio.py  ·  turnos.py     ← los usa cualquier capa
     (nombres fijos)  (calendario)      (no importan nada del programa)
```

**La flecha va en un solo sentido y nunca al revés.** Un repo jamás
importa nada de `ui/`. `database.py` no sabe que existen las pantallas.

`dominio.py` y `turnos.py` están fuera de la fila a propósito: son
funciones y constantes puras, sin base de datos ni Qt, así que las puede
usar cualquier capa sin ensuciar la dirección de las flechas.

Aparte quedan `admin_remoto/` (la copia que se abre desde otra PC le pide todo
al mostrador por la red) y `servidor_red.py` (el servidor HTTP del mostrador,
puerto 8909, que solo atiende esa administración remota).

---

## Las 15 reglas

### Cómo se reparte el código

**1. Tres capas, flecha en un solo sentido.**
`ui/` dibuja y pregunta. `repositories/` decide. `database.py` guarda.
Una pantalla **nunca** importa `sqlite3`, ni escribe SQL, ni abre
`conexion_db()`. Hoy esto se cumple al 100% (cero SQL en `ui/`) — es lo más
valioso que tiene el proyecto, no lo rompas por apuro. Si necesitás un dato
que ningún repo te da, la respuesta es **agregar la función al repo**, no
meter un SELECT en la pantalla.

**2. Un dato, un solo lugar que lo calcula.**
Si vas a repetir una cuenta que ya existe en otro lado, extraela a una
función compartida *primero* y usala en los dos lugares. Nunca copiar y
pegar lógica.
> Caso resuelto que dejó el patrón: `cantidad * precio_unitario` estaba
> escrito tres veces en `ui/ventas_window.py`. Hoy vive solo en
> `ventas_repo.subtotal_linea()`, y `confirmar_venta()` la usa en vez de
> confiar en el subtotal que le manda la pantalla.

**3. La regla de negocio vive en el repo, no en la pantalla.**
La pantalla junta lo que la usuaria escribió, se lo pasa al repo y
muestra el resultado. Validar, calcular y decidir es tarea del repo.
Si en un `.py` de `ui/` aparece una cuenta de plata o un "si pasa esto
entonces aquello" del negocio, está en el lugar equivocado. Si la pantalla
también se abre desde otra PC y la cuenta no necesita la base, va como función
pura en `dominio.py` (como `precio_con_margen`, `bajo_el_minimo` o
`suma_de_las_filas`): una función nueva de un repo tendría que entrar en
`admin_remoto/lista_blanca.py` y cambiaría la huella.

**4. Cambio local, efecto local.**
Tocar una pantalla no puede obligar a tocar otras tres. Si te pasa eso,
falta una abstracción: hacela antes de seguir.

**5. Nada de strings mágicos sueltos.**
Los valores fijos del negocio están todos en **`dominio.py`** y se usan
desde ahí, nunca escritos a mano:

| Concepto | Constantes |
|---|---|
| Rol | `ROL_ADMIN`, `ROL_EMPLEADA`, `ROLES` — y `dominio.es_admin(usuario)` |
| Estado de venta | `VENTA_CONFIRMADA`, `VENTA_ANULADA`, `ESTADOS_VENTA` |
| Método de pago | `PAGO_EFECTIVO`, `PAGO_DIGITAL`, `METODOS_PAGO` (no hay "mixto": ver más abajo) |
| Turno | `TURNO_MANANA`, `TURNO_TARDE`, `TURNO_NOCHE`, `TURNOS` |
| Origen de una venta | `ORIGEN_KIOSKO`, `ORIGENES_VENTA` (hoy uno solo; sumar otro toca la caja, ver "Trampas") |
| Negocios del cierre | `NEGOCIOS_DEL_CIERRE` (los renglones de Caja, Cierre de Turno y lo que viaja a la app de gastos) |
| Envío a la app de gastos | `ENVIO_PENDIENTE`, `ENVIO_ENVIADO`, `ENVIO_ERROR`, `ESTADOS_ENVIO_PWA` |
| Impresiones | `CODIGO_ARTICULO_IMPRESIONES` (el código "4") |
| Acomodar Caja | `CODIGO_ARTICULO_ACOMODAR_CAJA`, `DESCRIPCION_ACOMODAR_CAJA` (el artículo escondido de lo que cobró el programa anterior) |

Un typo en uno de esos strings **no falla ruidosamente**: la consulta
devuelve cero filas y nadie se entera hasta que falta plata en un cierre.
Nombrándolos, un typo es un error de Python que salta al instante.

Esto vale también dentro del SQL: el estado va como parámetro
(`WHERE estado = ?` con `dominio.VENTA_CONFIRMADA`), no como literal
pegado en la consulta. Y los `CHECK (... IN (...))` del esquema también salen
de las listas de `dominio.py` con `database._valores_sql`: una base NUEVA
nunca queda desfasada. Pero SQLite no deja cambiar un CHECK ya grabado: si se
agrega un valor a una lista, las bases que ya existen necesitan una migración
que reconstruya la tabla (ver regla 6).

### Cómo se tratan los datos

**6. El esquema se cambia con migración, nunca a mano.**
La versión de la base vive en el archivo (`PRAGMA user_version`). Hoy es la 1
(`database_migraciones.VERSION_ESQUEMA`, sin ningún paso). Antes de crear nada,
`comprobar_base_kiosko` no deja abrir una base de CYBERCONTROL ni una de un
FRKiosko más nuevo (versión mayor que `VERSION_ESQUEMA`): un programa viejo podría
dañarla. En cuanto el programa esté en uso en el kiosko habrá una base con datos
reales: toda columna nueva, índice sobre ella o tabla reconstruida se agrega como
un paso con el molde de `database_migraciones.py`:
(1) escribir `_paso_N(conexion)` idempotente: mira con `PRAGMA table_info`/`sqlite_master`
si ya está hecho, porque corre también sobre una base nueva;
(2) sumarlo a `PASOS = {N: _paso_N}` y subir `VERSION_ESQUEMA` a N. Van las dos
cosas: un paso sin subir la versión no corre nunca, `tests/test_migraciones.py`
exige un paso por versión, y una base en uso a la que le falte un paso no se marca
como nueva (`migrar_base` frena);
(3) el paso no hace commit ni rollback, no usa `executescript` (hace COMMIT antes
de correr y lo de antes ya no se deshace) y no toca `PRAGMA foreign_keys`:
`migrar_base` corre cada paso pendiente en orden, en su propia transacción (BEGIN
explícito, claves foráneas apagadas ANTES del BEGIN), con la versión anotada en esa
misma transacción, y lo rechaza si deja referencias rotas. Antes del primero deja
la copia `data_fr/backups/antes_de_migrar_v<versión>_AAAAMMDD_HHMMSS.db`, que nunca
se borra;
(4) su prueba: una base de la versión anterior, con datos, pasa a la nueva sin
perder nada.
Un índice sobre una columna nueva va en el paso, no en `database_esquema.py`: ese
corre antes, y en una base vieja la columna todavía no existe. Nunca "borrá el .db
y volvé a empezar". Una tabla MADRE (`ventas`, `articulos`, `usuarios`) no se
reconstruye con un RENAME primero, porque SQLite re-apunta las claves foráneas de
las hijas a la renombrada: dentro del paso, el orden es crear `<tabla>_nueva`,
copiar, borrar la vieja y recién ahí renombrar (en CYBERCONTROL está hecho en
`_migrar_check_origen_en_ventas`). Las trampas de SQLite que el molde ya resuelve
están explicadas, y probadas, arriba de `database_migraciones.py`.

**7. Nada se borra: se marca.**
Una venta anulada cambia de estado y guarda quién, cuándo y por qué —
nunca desaparece de la tabla. Un usuario que se va se desactiva. Esto es
lo que permite auditar un faltante tres meses después.
> Sin excepciones: en CYBERCONTROL hubo un "Limpiar base de datos" que el
> dueño pidió sacar ("ya es peligroso": el local trabaja con plata real). No
> sumes un borrado así sin que el dueño lo pida.

**8. Una operación de negocio = una transacción.**
Cabecera, detalle, pagos y descuento de stock se graban juntos o no se
graba nada (ver `confirmar_venta`). Nunca dejar la puerta abierta a una
venta a medio grabar con el stock ya descontado.

**9. La plata se redondea al guardar y se formatea al mostrar.**
`round(..., 2)` en el repo, justo antes del INSERT. `formato_pesos()` en
la pantalla, justo antes de mostrar. Nunca al revés, y nunca un
`f"{monto:.2f}"` suelto en una pantalla.

**10. Los permisos se preguntan, no se deducen.**
Siempre `usuarios_repo.tiene_permiso(usuario, "permiso_x")`, nunca
comparando el rol a mano. Un permiso nuevo se agrega en el repo y las
pantallas no se enteran.

### Cómo se crece

**11. Un archivo por pantalla, un repo por tema.**
Módulo nuevo = pantalla nueva en `ui/` + su repo en `repositories/`. No
se cuelga de uno existente "porque es parecido".

**12. Cuando un archivo pasa las ~600 líneas, se parte.**
Ya se hizo con `ventas_window.py` (carrito y diálogo de pago), `turnos.py`
(calendario separado de la base), `turnos_faltantes_repo.py`,
`turnos_ventas_repo.py` (qué se vendió en la ventana de un turno),
`control_cierres_repo.py` (con su pantalla `ui/control_cierres_window.py`),
`ui/reportes_resumen_dia.py` y `ui/reportes_detalle_dia.py` (salieron de
`reportes_window.py`), `database.py` (esquema en `database_esquema.py` +
`_cajas` + `_envios`, migraciones en `database_migraciones.py`), `main.py` (la
hoja de estilos en `ui/hoja_de_estilos.py`) y `ui/main_window.py`
(Configuración ADMIN en `ui/configuracion_admin_window.py`, Administrar Kiosko
en `ui/administrar_kiosko_window.py` y la foto de fondo en
`ui/fondo_del_inicio.py`) y `ui/articulos_window.py` (el alta y
modificación de un artículo en `ui/dialogo_articulo.py`). Tareas del Turno nació
partida: la ventana en `ui/tareas_turno_window.py`, el formulario y el historial
en `ui/tareas_turno_dialogos.py` y el aviso en `ui/aviso_tarea.py`.
Conservá las funciones públicas al partirlos para no tocar otras pantallas.

**13. Comentar el porqué, no el qué.**
Es la mejor costumbre que tiene este código y hay que sostenerla. Los
comentarios explican decisiones no obvias y trampas (por qué el turno
noche cruza la medianoche, por qué el `.exe` guarda la base al lado del
ejecutable). Un comentario que repite lo que dice la línea de abajo
sobra; uno que explica por qué esa línea es así vale oro.

### Cómo se verifica

**14. Regla de negocio nueva, test nuevo.**
`tests/` cubre turnos, stock, ORDENAR Stock, marcas, rubros, cierres, cajas con
número, el detalle del día, el cobro con Enter, impresiones, reportes,
administrar desde otra PC, copias de seguridad (también la que se guarda a mano
en un pendrive), las migraciones de la base (con pasos de mentira,
`tests/test_migraciones.py`), los envíos a la app de gastos, la vuelta sola del
Admin, que siempre quede un Administrador activo, las reglas de plata de la caja
y del sobre (`tests/test_reglas_de_la_caja.py`), las cuentas que salieron de las
pantallas (margen de Artículos, stock bajo el mínimo y la fila TOTAL de Reportes,
`tests/test_cuentas_de_articulos_y_reportes.py`), la tabla de configuración y lo
cobrado por medio en cada venta (`tests/test_config_repo.py`), la base de
prueba, el formato de pesos, el aspecto de las pantallas y que los botones que
esperan la red no congelen el mostrador (`tests/test_en_segundo_plano.py`), ni la
copia de otra PC mientras el mostrador contesta (`tests/test_espera_del_mostrador.py`).
Todo lo que se calcule con plata, fechas o turnos entra ahí antes de darse por
terminado. La UI se prueba a mano; la lógica, no.

**15. Antes de decir "listo": correr los tests y abrir el programa.**

```
python -m unittest discover tests
python armar_base_de_prueba.py        (si todavía no está data_prueba/)
python main.py --base data_prueba
```

Que los tests pasen no alcanza si la pantalla no abre. Que la pantalla
abra no alcanza si los tests no pasan. Se abre con la BASE DE PRUEBA, nunca
con `python main.py` a secas: eso usa `data_fr/`, y una venta o un cierre de
prueba no se pueden borrar después (regla 7). La de prueba es un año inventado
que pasa por los mismos repos que el mostrador (ver `armar_base_de_prueba.py`):
sirve también para ver cuánto tarda un reporte con mucho movimiento. Si un
cambio de esquema la deja vieja, se vuelve a armar.

---

## Detalle aparte, en `docs/`

Para que este archivo se cargue rápido en cada sesión, el detalle largo vive
aparte (movido tal cual el 2026-11-04). Leé el que toque tu tarea ANTES de
empezar:

- `docs/PUNTOS_DE_VERDAD.md` — qué hace cada punto único de verdad, sus reglas
  y sus pruebas (acá abajo queda una línea por cada uno).
- `docs/TRAMPAS.md` — las trampas que no tocan plata, caja, base real ni repo
  público (acá abajo queda su título; las otras siguen enteras acá).
- `docs/ESTADO.md` — qué tiene hoy el programa, pantalla por pantalla.

Algo nuevo va al doc que le toca, con su línea acá si es un punto único o una
trampa. No vuelvas a copiar el detalle en este archivo.

---

## Puntos únicos de verdad ya establecidos (usalos, no los repitas)

Una línea por cada uno, en el mismo orden que la tabla completa de
`docs/PUNTOS_DE_VERDAD.md` (buscá ahí el nombre antes de tocar o usar uno).

- `turnos.calcular_turno` — a qué turno pertenece una hora
- `turnos.es_domingo` — si un día es domingo
- `turnos.turnos_del_dia` — qué turnos tiene un día (siempre 3)
- `turnos.etiqueta_turno` — el nombre legible de un turno
- `turnos.dia_en_que_empezo_el_turno` — a qué día pertenece el turno de un momento (de madrugada, la Noche del día anterior)
- `turnos.limites_de_los_dias` · `.sql_dia_del_local` — filtrar y agrupar por día en un reporte de ventas (días de 06:00 a 06:00)
- `reportes_repo._filtro_por_caja` · `._CON_SU_CAJA` · `._TURNO_DE_LA_CAJA` — repartir un reporte POR TURNO según la caja de cada venta
- `turnos.dia_del_turno_que_arranca_tras_un_cierre` — con qué día queda anotado lo que sigue a un cierre
- `ui.utils.hoy_del_local` — qué es "hoy" en los reportes de ventas
- `turnos.turno_vencimiento` — cuándo un turno ya debería estar cerrado (y la hora del cierre forzoso)
- `turnos.fin_del_turno` · `.inicio_del_aviso_de_cierre` — a qué hora termina un turno y desde cuándo titila Cierre de Turno
- `turnos.turno_que_arranca_tras_un_cierre` — con qué turno queda anotado lo que sigue a un cierre (y el de una caja que se abre)
- `turnos.turno_para_la_app_de_gastos` — el nombre del turno para la app de gastos
- `relevo_repo.situacion_al_entrar` · `.abrir_caja` · `.recibir_caja` · `.cerrar_para_entrar` — qué pasa con la caja cuando alguien entra
- `relevo_repo.estado_de_la_caja` · `.cierre_forzoso_si_corresponde` — si titila Cierre de Turno y si toca el cierre forzoso
- `cajas_repo._quien_vende` — a nombre de quién y en qué caja queda una venta
- `cajas_repo.cambio_inicial` — con cuánto cambio arrancó una caja
- `cajas_repo.cerrada_en_ausencia` — si una caja se cerró en ausencia de su responsable
- `control_cierres_repo.listar_cierres` · `.detalle_cierre` · `.verificar_cierre` — lo que muestra Control de Cierres y el conteo del sobre
- `turnos_repo._cerrado_pasado_su_vencimiento` — si un turno se cerró "tarde"
- `turnos_repo._desglose_de_totales` · `turnos_ventas_repo._PREFIJO_COLUMNAS_POR_ORIGEN` — lo cobrado de un turno por origen y medio, y el efectivo del cajón
- `turnos_ventas_repo._vendido_aparte_entre` · `._aparte_por_metodo` · `._separar_de_kiosko` — las impresiones aparte de Kiosko en Caja, Cierre de Turno y el detalle de un cierre
- `turnos_ventas_repo._efectivo_y_digital_de_cada_venta` — lo cobrado por cada medio en UNA venta (pedazo de SQL compartido)
- `turnos_repo._ventanas_del_dia` — qué ventas son de qué turno de un día
- `detalle_dia_repo.detalle_del_dia` — el detalle venta por venta de un día
- `reportes_repo.resumen_por_operador` · `.ventas_de_operador` — Reportes > Por Operador
- `dominio.es_admin` — si alguien es Administrador
- `ventas_repo.subtotal_linea` — lo que se cobra por un renglón
- `ventas_repo.total_carrito` — el total de una venta en curso
- `ventas_repo._grabar_venta_kiosko` — grabar una venta de kiosko (único INSERT en `venta_detalle`, descuento de stock y control de los pagos)
- `impresiones_repo.cobrar_impresiones` (y las demás de su fila) — el cobro del botón de impresiones de la barra
- `acomodar_caja_repo.acomodar_caja` — ORDENAR $: sumar a la caja lo que ya había cobrado el programa anterior
- `pedidos_impresion_repo.tomar_pedido` · `.entregar_pedido` · `.dar_por_perdida` · `.anular_pedido` · `.anotar_aviso` — los pedidos de Gestión Impresiones
- `pedidos_clientes_repo.anotar` · `.sumar_uno` · `.parecidos` · `.ya_lo_trajimos` y compañía — Pedidos de Clientes
- `tareas_turno_repo.crear_tarea` y compañía · `turnos.momento_de_la_tarea` — Tareas del Turno
- `ui.aviso_tarea.RevisorDeTareas` · `.AvisoDeTarea` — el aviso de Tareas del Turno
- `dominio.telefono_limpio` · `.enlace_whatsapp` · `.mensaje_pedido_listo` — el celular de un pedido y el WhatsApp de "ya está listo"
- `dominio.CODIGO_ARTICULO_IMPRESIONES` — qué artículo es Impresiones (el código "4")
- `dominio.cuenta_del_cobro` · `.lo_que_falta_para` — la cuenta del cobro (efectivo, digital, vuelto, lo que falta)
- `dominio.total_cobrado` · `.monto_a_retirar` · `.diferencia_de_plata` · `.coincide` · `.falta_plata` — la plata de la caja y del sobre
- `dominio.precio_con_margen` · `.costo_sin_margen` — el margen de Artículos
- `dominio.porcentaje_de_ganancia` · `.ganancia_por_unidad` · `.MARGEN_POR_DEFECTO` — el % que se le gana a un artículo y la ganancia por unidad
- `dominio.bajo_el_minimo` — si un artículo quedó por debajo de su stock mínimo
- `dominio.suma_de_las_filas` — la fila TOTAL de un reporte
- `ui.dialogo_pago.cobrar` — cobrar algo que no es una venta de kiosko
- `database.conexion_db` — abrir una transacción contra la base
- `database.DATA_DIR` / `DB_PATH` · `.usar_carpeta_de_datos` · `.es_base_de_prueba` — dónde viven los datos
- `database.hash_clave` / `verificar_clave` — manejar una contraseña
- `database_migraciones.comprobar_base_kiosko` · `.migrar_base` · `.PASOS` — rechazar una base ajena o más nueva y migrar la base
- `usuarios_repo.tiene_permiso` — si alguien puede entrar a algo
- `usuarios_repo.exigir_admin` · `.usuario_habilitado` — que quien opera siga activo (y sea Admin)
- `usuarios_repo._exigir_que_quede_otro_admin` — que siempre quede un Administrador activo
- `config_repo.leer` · `.guardar` · `.obtener_fondo_cambio` · `.actualizar_fondo_cambio` — la tabla `configuracion` (y el Cambio Fijo)
- `admin_remoto_repo.esta_activo` · `.activar` · `.entrar` · `.exigir_admin_habilitado` — quién administra desde otra PC
- `admin_remoto.lista_blanca.FUNCIONES` · `.ACTOR` · `.huella` — qué funciones se pueden pedir desde otra PC
- `admin_remoto.modo.direccion_del_mostrador` · `.es_copia_remota` — si esta copia es la del mostrador o una abierta por la red
- `ui.utils.solo_en_el_mostrador` · `.avisar_que_es_en_el_mostrador` — los botones que desde otra PC avisan "Esto se hace en el mostrador"
- `ui.piezas_ventana.restringir` · `.solo_para_el_admin` · `ui.utils.avisar_acceso_restringido` — un botón sin permiso se ve igual y dice "Acceso Restringido"
- `copias_repo.copia_automatica_si_corresponde` · `.toca_copia` · `.nombres_a_borrar` · `.agregar_carpeta_extra` — cuándo y dónde se hacen las copias de seguridad
- `database.carpeta_de_copias` — en qué carpeta de esta PC quedan las copias
- `envio_pwa_repo.encolar` · `.enviar_pendientes` · `.mandar_cierre` y compañía — mandar cada Cierre de Turno a la app de gastos
- `tareas_del_cierre_repo.tareas_del_cierre` — qué Tareas del Turno viajan con un cierre a la app de gastos
- `vuelta_admin_repo.volver` · `ui.vuelta_del_admin.VueltaDelAdmin` — la vuelta sola del Administrador a la operadora
- `errores.registrar_error` — guardar fallos inesperados en `data_fr/errores.log`
- `main.aplicar_estilo` — el aspecto de TODO el programa
- `dominio.texto_pesos` · `ui.utils.formato_pesos` — un monto como texto ("$ 1.500")
- `ui.utils.CampoPesos` · `ui.utils.pedir_pesos` — escribir un monto
- `ui.utils.formato_fecha_hora` — una fecha con hora como texto
- `ui.utils.manejar_errores` — atrapar un error de una acción de pantalla
- `ui.en_segundo_plano.EnSegundoPlano` · `.arrancar` — un botón que espera la red sin congelar el mostrador
- `ui.espera_del_mostrador.esperar` · `.CartelEsperandoAlMostrador` · `.SeDejoDeEsperar` — la copia de otra PC espera al mostrador sin trabarse
- `ui.utils.encadenar_enter` — Enter de campo en campo, como Tab
- `ui.utils.aplicar_clase` — marcar un botón como primario/peligro/barra
- `ui.piezas_ventana.cabecera_oscura` · `.tarjeta_de_menu` · `.tecla` y compañía — una ventana "clara con cabecera cyber"
- `ui.piezas_ventana.agregar_indicador` · `.buscador` · `.panel_de_tabla` y compañía · `ui.dibujos_tabla.DelegadoEtiqueta` · `.DelegadoStock` — una LISTA con la maqueta B
- `ui.login_dibujos.FichasDeJugadores` · `.FondoDelIngreso` · `.TextoDegradado` — la pantalla de ingreso "Elegí tu Jugador"
- `ui.utils.sin_boton_por_defecto` — que Enter en un campo no apriete el primer botón de un diálogo
- `ui.utils.crear_tabla` — una tabla de solo lectura
- `ui.utils.mostrar_columna_entera` — una columna que no se corta con "..."
- `articulos_repo.ajustar_stock` · `.comprobar_clave_para_ordenar_stock` — corregir el stock a mano (ORDENAR Stock)
- `articulos_repo.cambiar_codigo` · `._TABLAS_CON_CODIGO_DE_ARTICULO` — corregir el código de un artículo
- `articulos_repo.crear_marca` · `.renombrar_marca` · `.juntar_marcas` · `.borrar_marca` — el catálogo de marcas (solo Admin)
- `articulos_repo.listar_para_control_de_stock` — la lista de Control de Stock
- `dominio.sin_acentos` — comparar u ordenar un texto sin mayúsculas ni acentos
- `dominio.orden_de_codigo` — ordenar códigos de artículo como números
- `ui.articulos_tabla.llenar_tabla_de_articulos` · `.poner_stock` — la grilla de artículos
- `ui.buscar_articulo.avisar_codigo_no_encontrado` — el aviso de que lo escaneado no es ningún artículo
- `ui.buscar_articulo.armar_botones_de_busqueda` — los botones F5/F6/F7 de Compras
- `ui.venta_buscador.BuscadorDeLaVenta` — el buscador de Ventas en su mismo campo
- `ui.utils.crear_selector_de_fecha` — un campo de fecha con calendario
- `ui.utils.armar_filtro_por_fechas` · `rango_de_fechas` · `fecha_iso` — la fila Desde/Hasta
- `ui.utils.fila_guardar_cancelar` — la fila Guardar/Cancelar de un formulario
- `ui.detalle_venta.VentanaConDetalleDeVenta` — lista de ventas con los artículos de la elegida
- `ui.tarjeta_cierre.TarjetaCierreDeTurno` · `.TablaDeNegocios` — la tarjeta del Cierre de Turno (y la tabla de Caja)
- `dominio.articulos_para_comprar` · `.STOCK_PARA_LISTA_DE_COMPRAS` — la Lista de Compras
- `rotacion_repo.ranking_por_compras` · `._lotes_de_compra` · `dominio.COMPRAS_PARA_PROMEDIAR` — Ranking de Rotación > POR COMPRA
- `rotacion_repo.ranking_de_rotacion` · `dominio.unidades_por_dia` · `.dias_que_alcanza` · `.se_acaba_pronto` — Ranking de Rotación > POR PERÍODO
- `ui.imprimir.html_del_listado` · `.vista_previa` — imprimir un listado en hojas A4 con vista previa

Si necesitás uno de esos datos, **llamá a la función existente**.

---

## Trampas conocidas (no las rompas sin entenderlas)

Estas van enteras porque tocan la plata, la caja, la base real o el repo
público:

- **El `.exe` empaquetado resuelve las rutas distinto.** Con PyInstaller
  `__file__` apunta a una carpeta temporal que se borra en cada arranque;
  por eso `BASE_DIR` usa `sys.executable` si está `frozen`. Si guardás un
  archivo nuevo, hacelo bajo `DATA_DIR` (`data_fr/`), nunca al lado de un `.py`.
- **El stock se corrige a mano SOLO con ORDENAR Stock** (botón de Artículos).
  Lo ve solo el Admin y pide una contraseña fija que eligió el dueño; en el
  código está solo su hash con salt (`articulos_repo.CLAVE_ORDENAR_STOCK`, el
  repo es público: nunca la escribas en claro, tampoco en un test). El repo
  vuelve a exigir Admin activo y contraseña en cada cambio, y cada cambio queda
  en `ajustes_stock` y en Movimientos como "ajuste de stock": es lo que deja
  auditar un faltante de mercadería. Ahí sí se rechaza un número negativo (es lo
  que hay contado en el estante). El alta/edición de un artículo sigue sin tocar
  el stock.
- **Todo se cobra con la misma ventana de cobro, nunca con un combo "Medio de
  pago"** (pedido del dueño, 2026-10-18: "a todo"). Ventas e Impresiones abren
  `ui.dialogo_pago.DialogoPago`; una pantalla nueva que cobre algo que no es una
  venta de kiosko usa `ui.dialogo_pago.cobrar` (hoy no la usa ninguna). Un pago repartido entre los dos
  medios se graba como dos filas reales de `PAGO_EFECTIVO`/`PAGO_DIGITAL`: no
  existe un método "mixto". No lo sumes a `METODOS_PAGO` ni al `CHECK` de
  `venta_pagos.metodo`: Caja y Cierre de Turno no sabrían cuánto de un pago
  "mixto" quedó en el cajón.
- **Sumar un origen de venta nuevo toca la caja, no solo `dominio.py`.** Si un
  origen no figura en `turnos_ventas_repo._PREFIJO_COLUMNAS_POR_ORIGEN` (y en
  las columnas de `cierres_turno`), su plata desaparece del efectivo esperado en
  el cajón sin ningún error visible — el dueño usa este desglose para auditar
  faltantes. El test `TestCadaOrigenSumaEnLaCaja` (`tests/test_cajas.py`) lo atrapa. `ventas.origen`
  tiene un CHECK: agregar un origen a una base ya en uso exige una migración
  que reconstruya `ventas` (ver regla 6). Hoy el único origen es KIOSKO.
- **El turno de un cierre sale de la hora del cierre ANTERIOR, con 60 minutos
  de tolerancia.** `cerrar_turno` anota el cierre en el turno donde ARRANCÓ lo
  que cierra, no en el de la hora en que se aprieta el botón (cerrar la Mañana a
  las 14:05 sigue siendo "Mañana"). Pero la hora del cierre anterior se toma con
  `TURNO_GRACIA_MIN` de más (`turnos.turno_que_arranca_tras_un_cierre`): quien
  cierra a las 13:55 ya está cerrando la Mañana, y lo que sigue es de la Tarde.
  Sin esa tolerancia todos los cierres siguientes quedaban un turno corrido. No
  usarla para el primer cierre de todos (no hay cierre anterior). Cambiar esta
  regla toca lo que ven Caja, Cierre de Turno y Resumen del Día a la vez: todo
  sale de `turnos_repo._desde_y_turno_en_curso`. **Con una caja abierta, el
  turno y el día son los de la caja** (decididos al abrirla con la misma
  tolerancia). `TURNO_GRACIA_MIN` (60) es SOLO esa tolerancia: lo que tarda en
  cerrarse sola una caja es `MINUTOS_PARA_CIERRE_FORZOSO` (60), no los mezcles.
- **Cajas con número (reglas en `relevo_repo`).** Una empleada no entra sin
  caja y nunca hay dos abiertas. La caja es de UNA persona por vez. Si el
  reemplazo llega poco tarde (el caso de todos los días), la que espera sigue
  con su caja y la cierra ella cuando llega la otra: para eso el forzoso es
  recién a la hora. Si tarda más, quien cubrió cierra a horario y vuelve a
  entrar con una caja nueva (sin contar); el que llega la RECIBE contando todo el cajón
  (`relevos_caja`) y lo vendido antes va en su sobre. Si el turno de la caja
  abierta ya terminó, quien llega la cierra "en ausencia" de la otra. El Admin
  (el dueño) no abre caja: lo que cobra va a nombre de la responsable
  (`cajas_repo._quien_vende`). Las ventas sin caja (del Admin sin nadie en el
  mostrador) pasan a la próxima caja que se abre, a nombre de quien la abre y con
  `cargada_por` (pedido del dueño, 2026-10-29: "lo que yo facture queda a cargo
  de la operadora que viene"; antes se cerraban aparte): quien abre cuenta TODO el
  cajón, el cambio más ese efectivo, aunque haya cerrado ella la anterior. En
  `cajas.cambio_contado` queda solo el cambio (lo contado menos lo del Admin),
  porque es lo que se deja en el cajón al cerrar; lo del Admin va en el sobre. Así
  un faltante de esa plata se ve al abrir, una sola vez
  (`relevo_repo._pasar_las_ventas_sin_caja`). Lo que queda en el cajón al cerrar es el
  cambio con que arrancó la caja (`cajas_repo.cambio_inicial`), no el Cambio
  Fijo: así un faltante del cambio se ve una sola vez. `ventas_caja` es una
  tabla aparte (no columnas de `ventas`) para no tocar la reconstrucción de la
  tabla madre. El cierre forzoso espera a que no haya un cobro a medias (una
  pantalla modal abierta; Ventas con el carrito vacío y Caja se cierran solas
  con `se_puede_cerrar_sola`). El conteo es a ciegas
  (`ui/ingreso_caja.DialogoContarPlata`): no muestres lo esperado antes de que
  se escriba lo contado. Ver `tests/test_cajas.py`.
- **Administrar desde otra PC: la base la toca SOLO el mostrador** (ver
  `admin_remoto/` y `docs/ADMIN_REMOTO.md`). El `FRKiosko.exe` abierto desde la
  carpeta compartida del mostrador es una copia remota (`admin_remoto/modo.py`):
  no abre ninguna base (`conexion_db` queda cerrada a propósito) y cada función
  de la lista blanca viaja al mostrador por `POST /admin/...` del servidor de
  red. Nunca hagas que una copia abra `data_fr/kiosko.db` por la red: SQLite por
  una carpeta compartida puede dañar el archivo con todas las ventas.
  Consecuencias: (1) una pantalla **nunca** importa una función suelta de un
  repo (`from repositories.x import f`): la copia remota reemplaza las funciones
  en su módulo y una suelta seguiría yendo a la base; (2) si una pantalla que se
  abre desde otra PC empieza a usar otra función de un repo, va a
  `admin_remoto/lista_blanca.py` (con su `ACTOR` si recibe quién lo hace) —
  `tests/test_admin_remoto.py` lo vigila; si empieza a leer una clave NUEVA de lo
  que devuelve una función de la lista, se sube `lista_blanca.VERSION_DEL_PROTOCOLO`
  (un mostrador con el programa viejo no la mandaría y la pantalla fallaría sin
  explicar por qué; con la versión nueva, las huellas no coinciden y avisa);
  (3) lo que solo se hace en el
  mostrador (vender, cobrar, cajas y turnos, Copias de Seguridad, prender la
  entrada remota o el envío a la app) NO entra en la lista: en la pantalla
  principal esos botones avisan con `ui.utils.solo_en_el_mostrador`; en las
  demás pantallas se esconden con `modo.es_copia_remota()`; (4) el cierre
  forzoso de la caja y la vuelta sola del Admin los hace solo el mostrador;
  (5) una consulta de reporte lenta frena las ventas del mostrador mientras dura
  (sin WAL, SQLite no deja grabar mientras otro lee): cada conexión de
  `get_connection` espera hasta 30 s (`database.ESPERA_BASE_OCUPADA_SEGUNDOS`;
  con la espera de fábrica de 5 s la venta FALLABA con "database is locked"), así
  que la venta espera y se graba, pero el mostrador queda trabado mientras tanto, y
  pasados los 30 s falla igual. Todo lo que se lee desde otra PC tiene que andar
  rápido con un año de ventas (sin `idx_venta_pagos_venta`, Por Operador tardaba 6
  minutos; con la base de prueba se mide). No pases la base a WAL sin hablarlo:
  deja archivos -wal/-shm y cambia la receta de "Recuperar una copia" del LEEME;
  (6) si la red se corta DESPUÉS de mandar un pedido (se perdió la respuesta o
  pasó la espera), el mostrador pudo haberlo grabado: `admin_remoto/cliente.py`
  lo distingue (`SinRespuesta`, una `SinConexion`) y avisa que se fije antes de
  repetirlo. No lo juntes con el "No encuentro el FRKiosko del mostrador", que es
  solo para cuando el pedido no llegó (repetir a ciegas una compra la carga dos
  veces y suma el stock doble; lo vigila `TestSeCortaEsperandoLaRespuesta`). El
  saludo y el ingreso no graban nada: ahí un corte da un aviso neutro. DEJAR DE
  ESPERAR en el cartel de `ui/espera_del_mostrador.py` cuenta como un corte;
  (7) cada pedido de la copia remota se espera en un hilo aparte con ese cartel:
  no lo vuelvas a esperar en el hilo de la pantalla (la copia quedaba "No
  responde" hasta 60 s).
- **Un cierre guarda una foto de lo cobrado.** En Resumen del Día, si una venta
  se anula después de cerrar, el desglose de Impresiones debe seguir conciliando
  con ese cierre; ver `turnos_ventas_repo._vendido_aparte_entre` y
  `_condicion_vigente`.
- **En Caja y Cierre de Turno, Kiosko se muestra SIN impresiones, pero se GRABA
  entero** (lo eligió el dueño el 2026-10-19). Lo que se guarda en `cierres_turno`
  (`kiosko_efectivo`/`kiosko_digital`), el efectivo a retirar y el TOTAL no
  cambian: separarlos es solo cómo se muestra. Las impresiones se cuentan por
  renglón de venta y se reparten venta por venta con los pagos de esa venta
  (`turnos_ventas_repo._aparte_por_metodo`); Kiosko sale por resta, con los
  centavos redondeados una sola vez (`_separar_de_kiosko`). No guardes estos
  importes repartidos en el cierre como si fueran exactos. "Ver Detalle" de
  Control de Cierres muestra cada cierre con la tarjeta del Cierre de Turno,
  con las impresiones recalculadas de las ventas de esa ventana contadas como
  estaban al cerrar.

Las demás están enteras en `docs/TRAMPAS.md` (leé la que toque tu tarea):

- El turno NOCHE cruza la medianoche: el día del local va de 06:00 a 06:00 (leela antes de tocar un reporte de ventas)
- Todos los días tienen tres turnos, incluidos los domingos.
- Un objeto de Qt que se pasa a otro sin que lo adopte tiene que quedar en una variable.
- El stock puede quedar negativo a propósito.
- El código de un artículo se cambia SOLO en ORDENAR Stock
- El carrito de una venta vive solo en memoria
- El login es por nombre y exige nombres únicos entre usuarios activos.
- Las claves están hasheadas con salt, pero esto no es un sistema seguro.
- El cobro arranca con el total escrito y, si pagan justo, un Enter cobra
- El servidor de red no debe tocar Qt.
- Las copias de seguridad se hacen en caliente, desde un hilo propio, y nunca pueden frenar el mostrador.
- El envío de un cierre a la app de gastos nunca frena el cierre ni lo duplica
- Un cierre hecho tras días sin cerrar NO aparece en las filas de hoy.
- En pantalla, el fondo de cambio se llama "Cambio Fijo" en TODOS lados
- En pantalla, quien atiende se llama "Operador", nunca empleado/empleada
- El esquema de color se fija en CLARO a propósito (`main.aplicar_estilo`).
- El "Renglón por renglón" del Detalle del Día muestra cada renglón TAL CUAL se cobró
- El recolector cíclico está desactivado a propósito

---

## Qué no cambiar sin que el dueño lo pida explícitamente

- **Nada de PCs vuelve a este programa.** Lo de PCs, Miembros, Bonos, Trámites,
  PlayStation 5 y Cliente PC vive en CYBERCONTROL. Si el dueño pide algo
  parecido para el kiosko, se charla como una función nueva, no se copia el
  paquete `control_pcs/` de allá.
- **La base es propia y arranca de cero** (`data_fr/`). No se importa nada de la
  base de CYBERCONTROL (`comprobar_base_kiosko` lo rechaza) y los dos programas
  pueden convivir en la misma PC: `FRKiosko.exe` + `data_fr/` al lado de
  `CyberBios.exe` + `data/`, con puertos distintos.
- **`data_fr/`, a mano.** Ahí vive la base real del negocio (está en
  `.gitignore` a propósito, no llega a git). No asumas que su contenido es
  descartable ni lo edites por fuera de una migración.
- **El envío de cierres va a la app de FR ("Gestión Central"),** no a la de
  CyberBIOS. Viene apagado; prenderlo es decisión del dueño.
- **El modelo de caja** (cajas con número, cierre forzoso a la hora del fin del turno,
  el Admin que no abre caja, el conteo a ciegas) y **el cobro con un solo Enter**
  son decisiones del dueño tomadas en CYBERCONTROL y heredadas acá tal cual.

---

## Roadmap (a futuro, fuera de alcance hoy)

- Lo que el dueño vaya pidiendo cuando el programa esté en el kiosko.

---

## Cómo trabajar en este repo

- **Idioma: español (rioplatense).** UI, comentarios, mensajes de commit y
  respuestas al usuario. El usuario no es programador: explicá los
  cambios en términos del kiosko, no de la implementación.
- **Stack:** Python 3.10+, PySide6, SQLite. Sin ORM, sin frameworks.
- **Git:** rama por cambio, después mergear a `main` (la rama principal de este repo). Puede haber otro
  agente (Codex/ChatGPT) en la misma carpeta: antes de `git add` mirá el `git diff` de cada archivo y
  subí solo lo tuyo (nunca `git add -A` ni `git commit -a`). El repo es público: nunca una clave real
  en el código, en un test ni en un doc.
- **Empaquetado (solo cuando el dueño lo pide):** `python -m PyInstaller Kiosko.spec --clean --noconfirm`,
  con el Python instalado en la PC (no el que trae un agente como Codex),
  genera `dist/FRKiosko.exe`. Ojo: `dist/data_fr/` sería la base *real* de la
  copia empaquetada si se abre desde ahí.
- **Proyecto aparte:** desde el 2026-10-29 no se pasan arreglos a CYBERCONTROL
  ni se traen de allá, salvo pedido del dueño (ver arriba, "Por qué existe
  este archivo").

---

## Estado actual

Está en `docs/ESTADO.md`: qué tiene hoy el programa, cuántas pruebas tiene la
suite y cómo son la barra y el fondo de la ventana principal.
