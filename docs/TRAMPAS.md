# Trampas conocidas — FRKiosko

Movido tal cual desde `CLAUDE.md` el 2026-11-04, para que ese archivo cargue
más rápido; allá queda el título de cada una. Las que tocan la plata, la caja,
la base real o el repo público siguen enteras en `CLAUDE.md`. Las reglas que
se nombran son las 15 de `CLAUDE.md`.

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
- **Todos los días tienen tres turnos, incluidos los domingos.** `MAÑANA`
  va de 06 a 14, `TARDE` de 14 a 22 y `NOCHE` de 22 a 06 del día siguiente.
  FRKiosko tiene su propio calendario: no hereda la excepción de CyberBIOS.
  Las etiquetas y los envíos usan Mañana/Tarde/Noche todos los días.
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
  borran archivos con nombre de copia automática de ESTE programa
  (`frkiosko_AAAA-MM-DD_HHMMSS.db`): nunca las manuales, las `antes_de_migrar_...`
  (las deja `database_migraciones` antes de un paso) ni las de CYBERCONTROL,
  que se llaman `kiosko_...` y borran con la misma regla (con el mismo prefijo,
  los dos programas en una misma carpeta se borraban las copias entre sí; no
  vuelvas a `kiosko_`, lo vigila `tests/test_copias.py`); (3) las copias cuentan
  días CON copias, no días del calendario; (4) una carpeta de otra PC se
  pregunta primero con `_que_conteste` (3 s al puerto 445): con esa PC apagada
  Windows tarda ~50 s; (5) el usuario y la clave de una carpeta de red se le
  pasan a Windows con `cmdkey` y NO se guardan en la base ni en un log (este
  repo es público: nunca escribas la clave real en un test o un doc); (6) las
  copias nunca crean una carpeta que falta. La pantalla lee lo que pasó de
  `_estado`, en memoria, y no mira las carpetas. Los botones de la pantalla que
  copian o prueban una carpeta ("Hacer copia de seguridad ahora", la copia al
  pendrive y "Agregar" otra carpeta) corren el repo en un hilo aparte
  (`ui.en_segundo_plano`): con una PC de la red apagada el mostrador no se traba.
  Mientras prueba una carpeta nueva, "Agregar carpeta" no se cierra (Cancelar,
  "Buscar..." y los campos se apagan, y Esc y la cruz no hacen nada): `agregar_carpeta_extra` lee la lista antes
  de probar y la graba después, y otra carpeta agregada o quitada en el medio se
  perdería sin aviso. Para dejar cancelar, primero hace falta un candado en
  `copias_repo` para leer y grabar la lista (el `_candado` que hay es solo el de
  las copias). Lo vigila
  `test_mientras_prueba_la_carpeta_no_se_cierra_y_la_lista_no_se_pisa`.
- **El envío de un cierre a la app de gastos nunca frena el cierre ni lo
  duplica** (`envio_pwa_repo`). El cierre se graba como siempre y en la MISMA
  transacción queda la fila de la cola (hay fila si y solo si hay cierre);
  mandarlo es tarea del hilo, nunca de `cerrar_turno` ni del hilo de una
  pantalla: ningún pedido de red va dentro de una transacción de la base, y
  "Probar la conexión" y "Reintentar ahora" (`ui/envio_pwa_dialogo.py`) corren la
  función del repo en un hilo aparte (`ui.en_segundo_plano.EnSegundoPlano`): la
  ventana se puede cerrar mientras esperan y lo que se mandó queda mandado.
  `cerrar_turno` solo lo
  despierta (`avisar_que_hay_un_cierre`, después del commit), y la barra
  "ENVIANDO CIERRE DE TURNO" (`ui/envio_pwa_progreso.py`, 3 s como mínimo) solo
  mira la cola. El documento allá tiene nombre fijo por cierre (`documento_id`,
  `frkiosko-<id>-<fecha>`) y el PATCH lo pisa entero: un reintento tras un corte
  no deja dos. Un ENVIADO no se vuelve a mandar solo; a mano sí: Control de
  Cierres > "Mandar a la app de gastos" (solo Admin). Solo se encola con el envío
  prendido, y nunca en la base de prueba (`database.es_base_de_prueba()`: ahí
  `activar` lo rechaza y el hilo no manda nada, porque sus cierres son
  inventados). `registradoPor` es la responsable de la caja, no quien apretó el
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
- **En pantalla, el fondo de cambio se llama "Cambio Fijo" en TODOS lados**
  (Caja, Cierre de Turno, Control de Cierres y su tarjeta de Administrar Kiosko,
  `ui/cambio_fijo_dialogo.py`; hasta el 2026-11-04 estaba adentro de Usuarios). Por dentro sigue siendo
  `fondo_cambio` (columnas, repos, claves): no se renombra, solo el texto que se
  ve.
- **En pantalla, quien atiende se llama "Operador", nunca empleado/empleada**
  (pedido del dueño, 2026-11-04). El rol se muestra con `dominio.nombre_del_rol`
  ("OPERADOR"); por dentro sigue siendo `ROL_EMPLEADA` / `'EMPLEADA'` en la base
  (con su CHECK), y los comentarios no se renombraron: no lo migres sin pedido.
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
  de referencias. Por lo mismo, un hilo que arranca una pantalla
  (`ui/en_segundo_plano.py`) recibe solo la función del repo, datos y un dict
  para la respuesta: nunca la ventana, un widget ni un método de la ventana (si
  el hilo soltara la última referencia, Python destruiría el objeto de Qt desde
  ese hilo). `arrancar` rechaza con TypeError los casos comunes (un widget, un
  método o un lambda que nombra la ventana, un partial, una lista o un dict con
  uno adentro), no todos. El error que vuelve de ese hilo se suelta sin dejar
  ciclos; lo vigila `test_el_error_no_queda_dando_vueltas_con_el_recolector_apagado`.
