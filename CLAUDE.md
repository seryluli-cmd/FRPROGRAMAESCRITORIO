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
otra base (`data_fr/`, arranca de cero). Los arreglos a la lógica común (cajas,
turnos, cierres) hay que hacerlos en los dos repos; nada de PCs vuelve acá.

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
entonces aquello" del negocio, está en el lugar equivocado.

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
| Turno | `TURNO_MANANA`, `TURNO_TARDE`, `TURNO_NOCHE`, `TURNOS`, `TURNOS_DOMINGO` |
| Origen de una venta | `ORIGEN_KIOSKO`, `ORIGENES_VENTA` (hoy uno solo; sumar otro toca la caja, ver "Trampas") |
| Negocios del cierre | `NEGOCIOS_DEL_CIERRE` (los renglones de Caja, Cierre de Turno y lo que viaja a la app de gastos) |
| Envío a la app de gastos | `ENVIO_PENDIENTE`, `ENVIO_ENVIADO`, `ENVIO_ERROR`, `ESTADOS_ENVIO_PWA` |
| Impresiones | `CODIGO_ARTICULO_IMPRESIONES` (el código "4") |

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
Hoy la base arranca de cero (`database_migraciones.VERSION_ESQUEMA` = 1, y
`comprobar_base_kiosko` no deja abrir una base de CYBERCONTROL por error). En
cuanto el programa esté en uso en el kiosko habrá una base con datos reales:
toda columna o tabla nueva se agrega como un paso idempotente en
`database_migraciones.py` (seguro de correr dos veces) y se sube
`VERSION_ESQUEMA`. Nunca "borrá el .db y volvé a empezar". Una tabla MADRE
(`ventas`, `articulos`, `usuarios`) no se reconstruye con un RENAME primero:
SQLite re-apunta las claves foráneas de las hijas a la renombrada; el orden es
crear `<tabla>_nueva`, copiar, borrar la vieja y recién ahí renombrar, con las
claves foráneas apagadas y todo en UNA transacción (en CYBERCONTROL está hecho
en `_migrar_check_origen_en_ventas`).

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
(Configuración ADMIN en `ui/configuracion_admin_window.py` y Administrar Kiosko
en `ui/administrar_kiosko_window.py`).
Conservá las funciones públicas al partirlos para no tocar otras pantallas.

**13. Comentar el porqué, no el qué.**
Es la mejor costumbre que tiene este código y hay que sostenerla. Los
comentarios explican decisiones no obvias y trampas (por qué el turno
noche cruza la medianoche, por qué el `.exe` guarda la base al lado del
ejecutable). Un comentario que repite lo que dice la línea de abajo
sobra; uno que explica por qué esa línea es así vale oro.

### Cómo se verifica

**14. Regla de negocio nueva, test nuevo.**
`tests/` cubre turnos, stock, ORDENAR Stock, marcas, cierres, cajas con
número, el detalle del día, el cobro con Enter, impresiones, reportes,
administrar desde otra PC, copias de seguridad, los envíos a la app de gastos,
la vuelta sola del Admin, el formato de pesos y el aspecto de las pantallas.
Todo lo que se calcule con plata, fechas o turnos entra ahí antes de darse por
terminado. La UI se prueba a mano; la lógica, no.

**15. Antes de decir "listo": correr los tests y abrir el programa.**

```
python -m unittest discover tests
python main.py
```

Que los tests pasen no alcanza si la pantalla no abre. Que la pantalla
abra no alcanza si los tests no pasan.

---

## Puntos únicos de verdad ya establecidos (usalos, no los repitas)

| Función | Es el único lugar donde... |
|---|---|
| `turnos.calcular_turno(fecha_hora)` | se decide a qué turno pertenece una hora |
| `turnos.es_domingo(fecha)` | se pregunta si un día es domingo (acepta date, datetime o string) |
| `turnos.turnos_del_dia(fecha)` | se decide qué turnos existen en un día (3, o 2 el domingo) |
| `turnos.etiqueta_turno(fecha, turno)` | se arma el nombre legible de un turno |
| `turnos.dia_en_que_empezo_el_turno(fecha_hora)` | se decide a qué día pertenece el turno de un momento (antes de las 06:00 es la Noche del día anterior): pasarle eso a `etiqueta_turno`, nunca el día calendario de una venta de madrugada |
| `turnos.limites_de_los_dias(desde, hasta)` · `turnos.sql_dia_del_local(columna)` | se filtra y se agrupa por día en un reporte de ventas: días de 06:00 a 06:00, con la Noche entera en el día en que empezó |
| `turnos.dia_del_turno_que_arranca_tras_un_cierre(momento)` | se decide con qué DÍA queda anotado lo que sigue a un cierre (misma tolerancia que el turno) |
| `ui.utils.hoy_del_local()` | se decide qué es "hoy" en los reportes de ventas (hasta las 06:00, el día anterior) |
| `turnos.turno_vencimiento(dia, turno)` | se decide si un turno ya debería estar cerrado: su fin + `MINUTOS_PARA_CIERRE_FORZOSO` (30 min). Es también la hora del cierre forzoso de la caja. Los carteles que nombran esos minutos leen la constante |
| `turnos.fin_del_turno(dia, turno)` · `.inicio_del_aviso_de_cierre(dia, turno)` | se decide a qué hora termina un turno (Mañana 14, Tarde 22, Noche 06; domingo 18 y 06) y desde cuándo titila el botón Cierre de Turno (`MINUTOS_AVISO_ANTES_DEL_FIN`, 5 min antes) |
| `turnos.turno_que_arranca_tras_un_cierre(momento)` | se decide con qué turno queda anotado lo que sigue a un cierre (la hora del cierre + `TURNO_GRACIA_MIN`); la usa `turnos_repo._desde_y_turno_en_curso`, que es lo que ven Caja y Cierre de Turno y lo que graba `cerrar_turno`. Con la misma regla `relevo_repo.abrir_caja` decide el turno de una caja que se abre |
| `turnos.turno_para_la_app_de_gastos(fecha, turno)` | se traduce un turno al nombre que usa la app de gastos ("mañana", "tarde", "noche"; los domingos "t1"/"t2") |
| `relevo_repo.situacion_al_entrar(usuario_id)` · `.abrir_caja` · `.recibir_caja` · `.cerrar_para_entrar` | se decide qué pasa con la caja cuando alguien entra (abrirla contando, recibirla contando todo el cajón, cerrar la de quien se fue, cerrar aparte las ventas sin caja; el Admin entra sin caja). La pantalla es `ui/ingreso_caja.py` |
| `relevo_repo.estado_de_la_caja()` · `.cierre_forzoso_si_corresponde()` | se decide si el botón Cierre de Turno titila y si toca el cierre forzoso (lo dispara `MainWindow._revisar_la_caja`, que espera si hay un cobro a medias) |
| `cajas_repo._quien_vende(conexion, usuario_id)` | se decide a nombre de quién y en qué caja queda una venta (lo que cobra el Admin va a nombre de la responsable de la caja abierta, con `ventas_caja.cargada_por`); lo usa `ventas_repo._insertar_cabecera_venta` |
| `cajas_repo.cambio_inicial(caja)` | se decide con cuánto cambio arrancó una caja (lo contado, o lo esperado si no se contó): es lo que queda en el cajón al cerrarla y lo que se espera en la siguiente |
| `control_cierres_repo.listar_cierres()` · `.detalle_cierre(id)` · `.verificar_cierre(...)` | se arma lo que muestra Control de Cierres (cada cierre con su caja, responsables, relevos, si se cerró sola o en ausencia; y en `detalle_cierre(id)["resumen"]` el cierre con las mismas claves que `resumen_turno_actual`) y se carga lo contado del sobre (solo Admin, cada conteo en `verificaciones_cierre`). `turnos_repo` los reexporta con el mismo nombre |
| `turnos_repo._cerrado_pasado_su_vencimiento(dia, turno, cerrado_a)` | se decide si un turno se cerró "tarde": lo usan el aviso y el "Cerrado el dd/mm" del Resumen del Día |
| `turnos_repo._desglose_de_totales(...)` · `turnos_ventas_repo._PREFIJO_COLUMNAS_POR_ORIGEN` | se reparte lo cobrado de un turno por origen y método de pago y se suma el efectivo del cajón sobre TODOS los `ORIGENES_VENTA` |
| `turnos_ventas_repo._vendido_aparte_entre(...)` · `._aparte_por_metodo(...)` · `._separar_de_kiosko(...)` | se calcula cuánto del Kiosko de un turno fue impresiones (para la columna propia del Resumen del Día) y se lo reparte entre efectivo y digital, venta por venta con sus pagos, para armar Kiosko sin impresiones en Caja, Cierre de Turno y el detalle de un cierre (`resumen_turno_actual()["kiosko_solo_*"]`, `["impresiones_*"]`); con `cierre_grabado=True` es la ventana de un cierre ya guardado |
| `turnos_repo._ventanas_del_dia(conexion, dia, ahora)` | se decide qué ventas son de qué turno de un día: la usan las filas del Resumen del Día y su detalle |
| `detalle_dia_repo.detalle_del_dia(dia)` | se arma el detalle venta por venta de un día, con los renglones de cada venta tal cual se cobraron (`lineas`), lo vendido por producto y por operador |
| `reportes_repo.resumen_por_operador(...)` · `.ventas_de_operador(...)` | se calcula cuánto vendió cada usuario y se listan sus ventas con fecha y hora (Reportes > Por Operador) |
| `dominio.es_admin(usuario)` | se pregunta si alguien es Administrador |
| `ventas_repo.subtotal_linea(linea)` | se calcula lo que se cobra por un renglón |
| `ventas_repo.total_carrito(lineas)` | se suma el total de una venta en curso |
| `ventas_repo._grabar_venta_kiosko(...)` | se graba una venta de kiosko sobre una conexión abierta (`confirmar_venta` e `impresiones_repo.cobrar_impresiones`): el único INSERT en `venta_detalle` y el único descuento de stock por una venta |
| `impresiones_repo.cobrar_impresiones(...)` · `.articulo_impresiones()` | se cobran impresiones desde el botón de la barra: venta de kiosko común del artículo, con el precio leído en la misma transacción |
| `dominio.CODIGO_ARTICULO_IMPRESIONES` | se decide qué artículo de kiosko es "Impresiones" (el código "4"), para mostrarlo como renglón propio en Reportes, Caja y Cierre de Turno |
| `dominio.cuenta_del_cobro(total, efectivo, digital, paga_con)` · `.lo_que_falta_para(total, monto)` | se calcula el cobro: la parte en efectivo y la digital, el billete que da el cliente, el vuelto, lo que falta y los pagos que quedan en la caja; y lo que completa el otro medio al escribir en uno |
| `ui.dialogo_pago.cobrar(parent, monto)` | se cobra algo que no es una venta de kiosko con la ventana de cobro de Ventas (medio, reparto y vuelto). Devuelve los pagos netos de vuelto, o None si se canceló. Hoy no la usa ninguna pantalla; una pantalla nueva que cobre la usa a ella |
| `database.conexion_db()` | se abre una transacción contra la base |
| `database.DATA_DIR` / `DB_PATH` | se resuelve dónde viven los datos (código vs `.exe`): `data_fr/` al lado del programa |
| `database.hash_clave()` / `verificar_clave()` | se maneja una contraseña |
| `database_migraciones.comprobar_base_kiosko(conexion)` · `.migrar_base(conexion)` | se rechaza una base de CYBERCONTROL y se lleva la versión del esquema (`VERSION_ESQUEMA`) |
| `usuarios_repo.tiene_permiso(usuario, clave)` | se decide si alguien puede entrar a algo |
| `usuarios_repo.exigir_admin(usuario_id, para)` · `.usuario_habilitado(usuario_id)` | un repo exige que quien opera siga activo (y sea Admin), releyéndolo de la base: un usuario dado de baja con la sesión abierta no puede seguir. Lo usan ORDENAR Stock, las marcas, Control de Stock, anular una venta |
| `config_repo.obtener_fondo_cambio()` | se lee el fondo de cambio del turno |
| `admin_remoto_repo.esta_activo()` · `.activar(...)` · `.entrar(nombre, clave, ip)` · `.exigir_admin_habilitado(id)` | se decide quién administra desde otra PC del local: viene apagado, solo un ADMIN activo, cada ingreso en `sesiones.desde_ip` |
| `admin_remoto.lista_blanca.FUNCIONES` · `.ACTOR` · `.huella()` | qué funciones de los repos se pueden pedir desde otra PC, qué parámetro es "quién lo hizo" (lo completa el mostrador) y la huella que tienen que compartir las dos copias del .exe |
| `admin_remoto.modo.direccion_del_mostrador()` · `.es_copia_remota()` | se decide si esta copia es la del mostrador o una abierta por la red (y a qué PC le habla), y las pantallas esconden lo que solo se hace en el mostrador |
| `ui.utils.solo_en_el_mostrador` · `.avisar_que_es_en_el_mostrador(padre)` | se decide qué hace desde otra PC un botón que vende, cobra o cierra: está igual que en el mostrador y avisa "Esto se hace en el mostrador". En el mostrador no cambia nada |
| `copias_repo.copia_automatica_si_corresponde()` · `.toca_copia(...)` · `.nombres_a_borrar(...)` · `.agregar_carpeta_extra(...)` | se decide cuándo se hace una copia de seguridad (después de cada Cierre de Turno y cada `HORAS_ENTRE_COPIAS`, con el programa abierto; lo corre el hilo de `iniciar_copias_automaticas`), cuántas quedan y en qué otras carpetas se guarda. La pantalla es `ui/copias_dialogo.py` (Usuarios > "Copias de Seguridad") |
| `envio_pwa_repo.encolar(conexion, cierre_id)` · `.enviar_pendientes(ahora, transporte)` · `.datos_del_cierre(conexion, cierre_id)` · `.mandar_cierre(usuario_id, cierre_id)` · `.activar(usuario_id, prendido)` · `.probar_conexion()` · `.estado()` | se manda cada Cierre de Turno a la app de gastos de FR ("Gestión Central", proyecto `frkioskos`, negocio `gestionfr`): la cola `envios_pwa` se llena en la transacción de `turnos_repo.cerrar_turno` solo con el envío prendido (Configuración ADMIN > "Cierres a la app de gastos", solo Admin y solo en el mostrador; viene apagado), un hilo la manda cada minuto con reintentos, y lo que viaja es lo que carga una empleada a mano más el desglose de la tarjeta del cierre (`dominio.NEGOCIOS_DEL_CIERRE`). Se habla con Firestore como un celular: login anónimo con la clave pública de la PWA y REST con `urllib` |
| `vuelta_admin_repo.volver(usuario_id)` · `ui.vuelta_del_admin.VueltaDelAdmin` | se decide si la sesión del Administrador vuelve sola a la empleada: a los `dominio.MINUTOS_ADMIN_VUELVE_SOLO` de entrar, en silencio (sin cartel: el dueño pidió sacarlo; no lo vuelvas a poner), vuelve a quien dejó el mostrador con "🔄 Operador" sin pedirle la clave, solo si su caja sigue abierta a su nombre y en hora; si no, a la pantalla de ingreso. Nunca corta un cobro ni un formulario abierto. Solo en el mostrador |
| `errores.registrar_error(excepcion, contexto)` | la UI y el servidor guardan fallos inesperados en `data_fr/errores.log` sin depender de Qt |
| `main.aplicar_estilo(app)` | se fija el aspecto de TODO el programa: estilo Fusion, esquema de color CLARO y la hoja de estilos (`HOJA_DE_ESTILOS`, en `ui/hoja_de_estilos.py`) |
| `dominio.texto_pesos(monto)` · `ui.utils.formato_pesos(monto)` | un monto se convierte en texto: `"$ 1.500"`, `"$ 30.000"`, con el punto de los miles y SIN centavos (pedido del dueño: todos los precios son en miles); con centavos solo si los tiene de verdad. Los repos lo usan en sus mensajes; la pantalla, con `formato_pesos` |
| `ui.utils.CampoPesos` · `ui.utils.pedir_pesos(parent, titulo, texto, valor)` | se escribe un monto: el campo se ve `"$ 1.500"` igual que `formato_pesos` y `pedir_pesos` es el `getDouble` con ese campo. Ninguna pantalla arma un `QDoubleSpinBox()` ni un `getDouble` suelto para plata (`tests/test_formato_pesos.py` lo vigila) |
| `ui.utils.formato_fecha_hora(fecha)` | una fecha con hora de la base se convierte en `"16/10/2026 22:13"` |
| `ui.utils.manejar_errores` | se atrapa un error de una acción de pantalla |
| `ui.utils.encadenar_enter(...)` | se arma el salto de campo en campo con Enter, como Tab, y la acción del último campo (todo formulario lo usa). Descarta el Enter repetido de una tecla que quedó apretada. Ojo: en un QSpinBox/QDoubleSpinBox/QDateEdit/QComboBox editable el Enter del teclado le llega al campo de AFUERA, no a su `lineEdit()`; una prueba que le manda el Enter al `lineEdit()` pasa aunque en el mostrador no ande. Ver `TestDondeLlegaElEnter` |
| `ui.utils.aplicar_clase(widget, clase)` | un botón se marca como primario/peligro/barra |
| `ui.piezas_ventana.cabecera_oscura(...)` · `.agregar_pastilla(...)` · `.panel_blanco()` · `.titulo_de_seccion(...)` · `.tarjeta_de_menu(...)` · `.bloquear_tarjeta(...)` · `.tecla(...)` · `.cifra_destacada(...)` | se arma una ventana con el diseño "clara con cabecera cyber" que eligió el dueño el 2026-10-26 (Configuración ADMIN, Administrar Kiosko, Caja y Cierre de Turno): cabecera oscura como la barra, con estela celeste y pastillas con números; paneles blancos; tarjetas de menú (dibujito, título y para qué es; la que solo usa el Admin, con candado y "Solo el Administrador"); teclas con relieve (`teclaAzul` lo principal, `teclaRoja` lo peligroso y Cerrar). Los colores van en `ui/hoja_de_estilos.py`, siempre por objectName o "clase" (y `>` para las etiquetas de un panel): los avisos que se abren encima son hijos de la ventana y no heredan nada (`test_estilo_ui`). El título de una tarjeta está en `accessibleName()`, y por ahí la buscan las pruebas |
| `ui.utils.sin_boton_por_defecto(ventana)` | se evita que Enter en un campo active el primer botón de un diálogo (llamarla al final de `_armar_interfaz`) |
| `ui.utils.crear_tabla(titulos, ...)` | se arma una tabla de solo lectura (filas alternadas, columna que se estira, selección por filas) |
| `ui.utils.mostrar_columna_entera(tabla, columna)` | se ensancha una columna para que su texto no se corte con "..." (la de códigos de barras; en el carrito de Ventas el código va chiquito debajo del producto, `ui.ventas_dibujos.DelegadoProducto`) |
| `articulos_repo.ajustar_stock(usuario_id, codigo, stock_nuevo, clave)` · `.comprobar_clave_para_ordenar_stock(...)` | se corrige el stock de un artículo a mano (ORDENAR Stock): solo Admin activo con la contraseña de `CLAVE_ORDENAR_STOCK`, entero de 0 para arriba, anotado en `ajustes_stock` y visible en Movimientos. Es la única forma de mover el stock aparte de Compras y Ventas |
| `articulos_repo.cambiar_codigo(usuario_id, codigo_actual, codigo_nuevo, clave)` · `._TABLAS_CON_CODIGO_DE_ARTICULO` | se corrige el código de un artículo (ORDENAR Stock, doble clic en el código): mismo permiso y contraseña que el stock; las ventas, compras y ajustes de antes pasan al código nuevo en la misma transacción, anotado en `cambios_codigo`. Es el único lugar donde se cambia un código |
| `articulos_repo.crear_marca` · `.renombrar_marca` · `.juntar_marcas` · `.borrar_marca` (usuario_id primero) | se corrige el catálogo de marcas: SOLO el Admin (`exigir_admin`, y el botón "Gestionar Marcas" de Artículos solo lo ve el Admin). Renombrar con el nombre de otra marca pregunta si juntarlas; borrar una con artículos se rechaza. Una marca nueva al cargar un artículo sigue libre para quien entra a Artículos |
| `articulos_repo.listar_para_control_de_stock(usuario_id)` | se arma la lista de Control de Stock (Administrar Kiosko, solo Admin; `ui/control_stock_window.py`): los artículos con stock de 1 para arriba, de la A a la Z, para imprimirla y contar el estante. Solo muestra: corregir es de ORDENAR Stock |
| `dominio.sin_acentos(texto)` | se compara u ordena un texto sin mayúsculas ni acentos, como lo haría una persona |
| `dominio.orden_de_codigo(codigo)` | se ordenan códigos de artículo de menor a mayor como números (1, 2, 10 y no 1, 10, 2; los que tienen letras al final): F5 Código |
| `ui.articulos_tabla.llenar_tabla_de_articulos(...)` · `.poner_stock(...)` | se arma la grilla de artículos (columnas y stock en rojo bajo el mínimo): la usan Artículos y ORDENAR Stock |
| `ui.buscar_articulo.avisar_codigo_no_encontrado(ventana, codigo)` | se avisa en Ventas y Compras que lo escaneado no es ningún artículo, con cuántos dígitos llegaron |
| `ui.buscar_articulo.armar_botones_de_busqueda(ventana, ...)` | se arman los botones F5/F6/F7 y sus atajos (Ventas y Compras) |
| `ui.utils.crear_selector_de_fecha(...)` | se crea un campo de fecha con calendario (usarlo siempre, nunca un `QDateEdit` a mano) |
| `ui.utils.armar_filtro_por_fechas(...)` · `rango_de_fechas(...)` · `fecha_iso(...)` | se arma la fila Desde/Hasta con "Buscar" y se leen sus fechas como `"YYYY-MM-DD"` |
| `ui.utils.fila_guardar_cancelar(dialogo, ...)` · `.fila_agregar_quitar(tabla, ...)` | se arman la fila Guardar/Cancelar de un formulario y los botones Agregar/Quitar de una tabla que se edita a mano |
| `ui.detalle_venta.VentanaConDetalleDeVenta` | lista de ventas + artículos de la elegida (Consulta de Ventas y Detalle de un cierre) |
| `ui.tarjeta_cierre.TarjetaCierreDeTurno` · `.TablaDeNegocios` | se dibuja el resumen de un Cierre de Turno (A RETIRAR y TOTAL en grande; en la tabla, cada negocio con su efectivo y digital en columnas, lo cobrado y el Cambio Fijo). La tabla es también la de Caja; la tarjeta la usan la pantalla Cierre de Turno (turno en curso) y "Ver Detalle" de Control de Cierres (cualquier cierre ya hecho, también el forzoso). Un cambio de diseño del Cierre de Turno se hace ahí y se ve en las dos |
| `ui.imprimir.html_del_listado(...)` · `.vista_previa(parent, html, nombre)` | se imprime un listado: HTML en hojas A4 con los títulos repetidos en cada hoja y vista previa (desde ahí se imprime o se guarda en PDF). Lo usan el "Renglón por renglón" del Detalle del Día y Control de Stock |

Si necesitás uno de esos datos, **llamá a la función existente**.

---

## Trampas conocidas (no las rompas sin entenderlas)

- **El turno NOCHE cruza la medianoche** (22:00–05:59), así que vence a la
  madrugada del día *siguiente*. Por eso **el día del local va de 06:00 a
  06:00** (`turnos.HORA_CAMBIO_DE_DIA`): el día 1 es Mañana, Tarde y la Noche
  ENTERA, aunque termine el día 2. Todo reporte de ventas filtra con
  `turnos.limites_de_los_dias` (nunca `date(?)`/`'+1 day'`), agrupa por día con
  `turnos.sql_dia_del_local` y toma su "hoy" de `ui.utils.hoy_del_local`: a las
  02:00, "Solo Hoy" es todavía el día anterior. Un cierre hecho pasada la
  medianoche deja lo que sigue en la Noche del día ANTERIOR
  (`turnos.dia_del_turno_que_arranca_tras_un_cierre`). Los historiales que no
  son de ventas (accesos, movimientos de un artículo) siguen por día calendario.
  Ver `tests/test_noche_del_dia.py` y `tests/test_reportes_fechas.py`. En las
  pruebas pasa lo mismo: el "hoy" de una prueba de reportes es
  `turnos.dia_en_que_empezo_el_turno(datetime.now())` o `hoy_del_local()`, nunca
  `date.today()` ni `QDate.currentDate()`.
- **Los domingos tienen 2 turnos de 12hs, no 3.** `MAÑANA` dura hasta las
  18:00 y no existe `TARDE`. El sábado a la noche sigue siendo el turno
  normal 22–06. Nunca asumas tres turnos por día.
- **El `.exe` empaquetado resuelve las rutas distinto.** Con PyInstaller
  `__file__` apunta a una carpeta temporal que se borra en cada arranque;
  por eso `BASE_DIR` usa `sys.executable` si está `frozen`. Si guardás un
  archivo nuevo, hacelo bajo `DATA_DIR` (`data_fr/`), nunca al lado de un `.py`.
- **Un objeto de Qt que se pasa a otro sin que lo adopte tiene que quedar en una
  variable.** `QPrintPreviewDialog(QPrinter(...), parent)` usa la impresora
  pero no la guarda: pasada sin variable, Python la borraba apenas se armaba el
  diálogo, la vista previa leía memoria liberada y el programa se cerraba **sin
  ningún cartel** (ni `manejar_errores` ni `sys.excepthook` lo ven: es una caída
  de Qt, no de Python). Le pasó al dueño en el cyber con Control de Stock >
  Imprimir (2026-10-26); vale para todos los listados (`ui/imprimir.vista_previa`).
  Ver `test_la_impresora_sigue_viva_mientras_esta_abierta_la_vista_previa`.
- **El stock puede quedar negativo a propósito.** No agregues una
  validación que lo impida: prefieren vender y corregir después antes que
  frenar la cola en el mostrador.
- **El stock se corrige a mano SOLO con ORDENAR Stock** (botón de Artículos).
  Lo ve solo el Admin y pide una contraseña fija que eligió el dueño; en el
  código está solo su hash con salt (`articulos_repo.CLAVE_ORDENAR_STOCK`, el
  repo es público: nunca la escribas en claro, tampoco en un test). El repo
  vuelve a exigir Admin activo y contraseña en cada cambio, y cada cambio queda
  en `ajustes_stock` y en Movimientos como "ajuste de stock": es lo que deja
  auditar un faltante de mercadería. Ahí sí se rechaza un número negativo (es lo
  que hay contado en el estante). El alta/edición de un artículo sigue sin tocar
  el stock.
- **El código de un artículo se cambia SOLO en ORDENAR Stock** (doble clic en
  el código; pregunta antes de guardar y pasa por `articulos_repo.cambiar_codigo`).
  El código es la clave de `articulos` y lo guardan `venta_detalle`,
  `compra_detalle`, `ajustes_stock` y `cambios_codigo`: se corrigen todas en la
  misma transacción con `PRAGMA defer_foreign_keys`. Una tabla nueva que guarde
  el código de un artículo va en `articulos_repo._TABLAS_CON_CODIGO_DE_ARTICULO`
  (`tests/test_ordenar_stock.py` lo vigila). No deja usar el código de otro
  artículo ni tocar el de Impresiones.
- **El carrito de una venta vive solo en memoria** hasta que se cobra. No
  lo persistas "por las dudas": es lo que permite borrar un renglón mal
  escaneado sin dejar basura en la base.
- **El login es por nombre y exige nombres únicos entre usuarios activos.**
  Dos "Matías" activos romperían el login.
- **Las claves están hasheadas con salt, pero esto no es un sistema
  seguro.** Cualquiera con acceso al archivo `data_fr/kiosko.db` lee y
  modifica todo. No le prometas al usuario que esto protege datos.
- **Todo se cobra con la misma ventana de cobro, nunca con un combo "Medio de
  pago"** (pedido del dueño, 2026-10-18: "a todo"). Ventas abre
  `ui.dialogo_pago.DialogoPago`; Impresiones y cualquier pantalla nueva que
  cobre la abren con `ui.dialogo_pago.cobrar`. Un pago repartido entre los dos
  medios se graba como dos filas reales de `PAGO_EFECTIVO`/`PAGO_DIGITAL`: no
  existe un método "mixto". No lo sumes a `METODOS_PAGO` ni al `CHECK` de
  `venta_pagos.metodo`: Caja y Cierre de Turno no sabrían cuánto de un pago
  "mixto" quedó en el cajón.
- **El cobro arranca con el total escrito y, si pagan justo, un Enter cobra**
  (pedido del dueño, 2026-10-18: casi siempre pagan justo). En `DialogoPago`
  Efectivo y Digital están siempre a la vista y suman el total: arranca con el
  total en Efectivo, seleccionado; al escribir en uno, el otro se completa con
  lo que falta; "Todo efectivo"/"Todo digital"; y "Paga con" (opcional) es el
  billete que da el cliente, para dar vuelto sin tocar lo digital. La cuenta es
  `dominio.cuenta_del_cobro`. Un Enter cobra SIEMPRE: pago justo, una parte en
  cada medio o con vuelto (hasta el 18/10 con vuelto frenaba en Confirmar y se
  sacó a pedido del dueño; no vuelvas a poner la frenada). Un Enter que queda
  apretado no cobra: `encadenar_enter` descarta la repetición del teclado
  (`tests/test_dialogo_pago.py`, `tests/test_enter_como_tab.py`).
- **Sumar un origen de venta nuevo toca la caja, no solo `dominio.py`.** Si un
  origen no figura en `turnos_ventas_repo._PREFIJO_COLUMNAS_POR_ORIGEN` (y en
  las columnas de `cierres_turno`), su plata desaparece del efectivo esperado en
  el cajón sin ningún error visible — el dueño usa este desglose para auditar
  faltantes. El test `TestCadaOrigenSumaEnLaCaja` lo atrapa. `ventas.origen`
  tiene un CHECK: agregar un origen a una base ya en uso exige una migración
  que reconstruya `ventas` (ver regla 6). Hoy el único origen es KIOSKO.
- **El turno de un cierre sale de la hora del cierre ANTERIOR, con 40 minutos
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
  tolerancia). `TURNO_GRACIA_MIN` (40) es SOLO esa tolerancia: lo que tarda en
  cerrarse sola una caja es `MINUTOS_PARA_CIERRE_FORZOSO` (30), no los mezcles.
- **Cajas con número (reglas en `relevo_repo`).** Una empleada no entra sin
  caja y nunca hay dos abiertas. La caja es de UNA persona por vez: si el
  reemplazo llega tarde, quien cubrió cierra a horario y vuelve a entrar con una
  caja nueva (sin contar); el que llega la RECIBE contando todo el cajón
  (`relevos_caja`) y lo vendido antes va en su sobre. Si el turno de la caja
  abierta ya terminó, quien llega la cierra "en ausencia" de la otra. El Admin
  (el dueño) no abre caja: lo que cobra va a nombre de la responsable
  (`cajas_repo._quien_vende`). Las ventas sin caja (del Admin sin nadie en el
  mostrador) se cierran aparte antes de abrir la próxima caja
  (`SITUACION_VENTAS_SIN_CAJA`): si se sumaran a la caja nueva, la empleada
  respondería por plata que no vendió. Lo que queda en el cajón al cerrar es el
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
  `tests/test_admin_remoto.py` lo vigila; (3) lo que solo se hace en el
  mostrador (vender, cobrar, cajas y turnos, Copias de Seguridad, prender la
  entrada remota o el envío a la app) NO entra en la lista: en la pantalla
  principal esos botones avisan con `ui.utils.solo_en_el_mostrador`; en las
  demás pantallas se esconden con `modo.es_copia_remota()`; (4) el cierre
  forzoso de la caja y la vuelta sola del Admin los hace solo el mostrador;
  (5) una consulta de reporte lenta frena las ventas del mostrador mientras dura
  (SQLite no deja grabar mientras otro lee): todo lo que se lee desde otra PC
  tiene que andar rápido con un año de ventas (sin `idx_venta_pagos_venta`, Por
  Operador tardaba 6 minutos).
- **El servidor de red no debe tocar Qt.** Usa conexiones SQLite propias desde
  sus hilos y registra fallos inesperados con `errores.registrar_error`, sin
  incluir claves ni el cuerpo de los pedidos en el contexto del log. Su puerto
  es 8909 (y el candado de instancia única, 8908): distintos de los de
  CYBERCONTROL (8899) a propósito, para que los dos programas convivan en una PC.
- **Las copias de seguridad se hacen en caliente, desde un hilo propio, y nunca
  pueden frenar el mostrador.** `copias_repo` copia a `data_fr/backups` después
  de cada Cierre de Turno (todos pasan por `turnos_repo.cerrar_turno`: se
  compara `MAX(fecha_cierre)` con la última copia) y cada 8 horas, y lleva la
  última a cada "otra carpeta" en cada revisión. Reglas que no hay que romper:
  (1) una copia se graba como `.parcial` y se renombra al final; (2) solo se
  borran archivos con nombre de copia automática
  (`kiosko_AAAA-MM-DD[_HHMMSS].db`): nunca las manuales; (3) las copias cuentan
  días CON copias, no días del calendario; (4) una carpeta de otra PC se
  pregunta primero con `_que_conteste` (3 s al puerto 445): con esa PC apagada
  Windows tarda ~50 s; (5) el usuario y la clave de una carpeta de red se le
  pasan a Windows con `cmdkey` y NO se guardan en la base ni en un log (este
  repo es público: nunca escribas la clave real en un test o un doc); (6) las
  copias nunca crean una carpeta que falta. La pantalla lee lo que pasó de
  `_estado`, en memoria, y no mira las carpetas.
- **El envío de un cierre a la app de gastos nunca frena el cierre ni lo
  duplica** (`envio_pwa_repo`). El cierre se graba como siempre y en la MISMA
  transacción queda la fila de la cola (hay fila si y solo si hay cierre);
  mandarlo es tarea del hilo, nunca de `cerrar_turno` ni de una pantalla: ningún
  pedido de red va dentro de una transacción de la base. `cerrar_turno` solo lo
  despierta (`avisar_que_hay_un_cierre`, después del commit), y la barra
  "ENVIANDO CIERRE DE TURNO" (`ui/envio_pwa_progreso.py`, 3 s como mínimo) solo
  mira la cola. El documento allá tiene nombre fijo por cierre (`documento_id`,
  `frkiosko-<id>-<fecha>`) y el PATCH lo pisa entero: un reintento tras un corte
  no deja dos. Un ENVIADO no se vuelve a mandar solo; a mano sí: Control de
  Cierres > "Mandar a la app de gastos" (solo Admin). Solo se encola con el envío
  prendido. `registradoPor` es la responsable de la caja, no quien apretó el
  botón, y tiene que ser el nombre EXACTO que usa la app. La clave de Firebase
  que está acá es la PÚBLICA de la PWA de FR (ya publicada en su código): no es
  un secreto. **Apunta a la app de FR ("Gestión Central", proyecto `frkioskos`),
  no a la de CyberBIOS**: si alguna vez hay que cambiar de app, son las
  constantes de arriba de `envio_pwa_repo.py`. Las pruebas usan una app de
  mentira: ninguna sale a internet ni toca el Firestore real.
- **Un cierre hecho tras días sin cerrar NO aparece en las filas de hoy.** Cubre
  desde el cierre anterior, así que queda anotado en el turno viejo y el Resumen
  del Día de hoy sale en cero. No es un error ni plata perdida: el reporte lo
  avisa arriba de la tabla (`cierres_de_otro_dia`) con un botón para ir a verlo.
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
- **En pantalla, el fondo de cambio se llama "Cambio Fijo" en TODOS lados**
  (Caja, Cierre de Turno, Control de Cierres, Usuarios). Por dentro sigue siendo
  `fondo_cambio` (columnas, repos, claves): no se renombra, solo el texto que se
  ve.
- **El esquema de color se fija en CLARO a propósito (`main.aplicar_estilo`).**
  Fusion toma los colores de Windows: con el modo oscuro puesto, los widgets que
  la hoja de estilos no pinta salían negros con la letra oscura encima. Si se
  agrega un widget nuevo que se vea oscuro, hay que pintarlo en `HOJA_DE_ESTILOS`
  (no sacar el esquema claro).
- **El "Renglón por renglón" del Detalle del Día muestra cada renglón TAL CUAL se
  cobró** (pedido del dueño: "si se cobran 14 impresiones juntas, que diga 14;
  si se hacen 4 por separado, que las ponga tal cual se cobraron"). No lo
  agrupes por producto "para que sea más corto": para eso está "Lo vendido
  (cantidades)". En pantalla y en papel salen las mismas filas.
- **El recolector cíclico está desactivado a propósito** en `main.py`: evita que
  un hilo (el servidor, el de copias o el de envíos) destruya un `QTimer` de Qt.
  Antes de reactivarlo, revisar la propiedad de los objetos de UI y sus ciclos
  de referencias.

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
- **El modelo de caja** (cajas con número, cierre forzoso a los 30 minutos,
  el Admin que no abre caja, el conteo a ciegas) y **el cobro con un solo Enter**
  son decisiones del dueño tomadas en CYBERCONTROL y heredadas acá tal cual.

---

## Roadmap (a futuro, fuera de alcance hoy)

- Que la app de gastos de FR muestre el `detalle` de cada cierre que llega de
  acá (en la app de CyberBIOS ya está hecho).
- Lo que el dueño vaya pidiendo cuando el programa esté en el kiosko.

---

## Cómo trabajar en este repo

- **Idioma: español (rioplatense).** UI, comentarios, mensajes de commit y
  respuestas al usuario. El usuario no es programador: explicá los
  cambios en términos del kiosko, no de la implementación.
- **Stack:** Python 3.10+, PySide6, SQLite. Sin ORM, sin frameworks.
- **Git:** rama por cambio, después mergear a `main` (la rama principal de este repo). El repo es público:
  nunca una clave real en el código, en un test ni en un doc.
- **Empaquetado:** `python -m PyInstaller Kiosko.spec --clean --noconfirm`
  genera `dist/FRKiosko.exe`. Ojo: `dist/data_fr/` sería la base *real* de la
  copia empaquetada si se abre desde ahí.
- **Dos repos hermanos:** un arreglo a cajas, turnos, cierres, ventas o stock
  que vale para los dos negocios se hace también en CYBERCONTROL (y al revés),
  sin asumir que el código sigue siendo idéntico: diffear antes.

---

## Estado actual

El programa es el kiosko solo: Vender (diseño "B": total y COBRAR grandes a la
derecha), Impresiones, Caja, Cierre de Turno, Administrar Kiosko (Artículos con
ORDENAR Stock y Gestionar Marcas, Compras, Control de Stock, Consulta de Ventas,
Reportes con el Resumen del Día y su detalle para imprimir, Control de Cierres,
Usuarios con Copias de Seguridad), Configuración ADMIN (Accesos de Admin,
Entrar desde otra PC, Cierres a la app de gastos), la barra oscura con los
mismos botones para todos, el Administrador que vuelve solo a la empleada a los
10 minutos y la plata en miles sin centavos ("$ 1.500").

La suite se ejecuta con `python -m unittest discover tests` y tiene 524 pruebas
al 2026-10-27 (el día del corte desde CYBERCONTROL). Lo que pasó antes de esa
fecha está contado en el `CLAUDE.md`, el `README.md` y el `docs/HISTORIAL.md`
de CYBERCONTROL.

La barra de arriba de la ventana principal es oscura, con teclas en relieve
(elegida por el dueño entre cuatro maquetas). Los colores viven en la hoja de
estilos (`ui/hoja_de_estilos.py`: `#encabezadoInicio`, clases `barra` y
`alerta`, y Vender/Operador dentro de la barra). Cuidado al tocar `alerta`:
tiene que llevar los mismos bordes, relleno y letra que `barra`, porque si no
Cierre de Turno cambia de tamaño cada vez que titila (lo cuida `test_estilo_ui`).
Todos los botones de la barra van en negrita y en mayúscula (la pone
`MainWindow._agregar_boton_barra`). La barra muestra los mismos botones a
todos: el que alguien no tiene habilitado (Admin Kiosko, Config ADMIN) se ve
igual pero no hace nada al apretarlo (lo cuida `tests/test_barra_para_todos.py`).
