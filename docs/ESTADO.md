# Estado actual — FRKiosko

Movido tal cual desde `CLAUDE.md` el 2026-11-04, para que ese archivo cargue
más rápido. Lo nuevo del programa se anota acá, no en `CLAUDE.md`.

## Estado actual

El programa es el kiosko solo: Vender (diseño "B": total y COBRAR grandes a la
derecha), IMPRE/FOTOC (impresiones y fotocopias, cada una con su precio), Caja, Gestión Impresiones (pedidos con seña y aviso por
WhatsApp), Cierre de Turno, Lista de Compras, Administrar Kiosko (Artículos con
ORDENAR Stock y Gestionar Marcas, Compras, Control de Stock, Consulta de Ventas,
Reportes con el Resumen del Día y su detalle para imprimir, Control de Cierres,
Usuarios con Copias de Seguridad), Configuración ADMIN (Accesos de Admin,
Entrar desde otra PC, Cierres a la app de gastos), la barra oscura con los
mismos botones para todos, el Administrador que vuelve solo a la empleada a los
10 minutos y la plata en miles sin centavos ("$ 1.500").

Pedidos de Clientes (lo que piden y no tenemos, 2026-11-03): quinto acceso del
inicio (`ui/pedidos_clientes_window.py`, maqueta A: campo con GUARDAR, parecidos
mientras se escribe, +1 y TRAJIMOS en cada renglón, HISTORIAL; RENOMBRAR, JUNTAR y
BORRAR solo el Admin). Reglas en `repositories/pedidos_clientes_repo.py`.

Tareas del Turno (cosas para hacer a una hora, 2026-11-03): sexto acceso del inicio
(`ui/tareas_turno_window.py`: PARA HACER, ATRASADAS y HECHAS arriba; ESTE TURNO
(con las atrasadas de un turno anterior de hoy), TODO EL DÍA y TODAS LAS TAREAS;
HECHA en cada renglón; + NUEVA TAREA, MODIFICAR y
BORRAR solo el Admin: a los demás les dicen "Acceso Restringido", como en Pedidos; HISTORIAL). A la
hora sale el aviso de `ui/aviso_tarea.py` encima de todo, con POSPONER 5 MIN,
POSPONER 10 MIN y TAREA HECHA, y el acceso titila en rojo con el numerito de las
atrasadas. Para que entraran seis accesos en la pantalla del mostrador, cada uno
bajó de 110 a 98 de alto y de 20 a 14 de separación. Reglas en
`repositories/tareas_turno_repo.py`.

Ranking de Rotación (qué tan rápido sale cada artículo, 2026-11-04): séptimo acceso
del inicio, debajo de Tareas del Turno (`ui/ranking_rotacion_window.py`), con dos
pestañas. POR COMPRA (la idea del dueño, abre en esta): cuánto tarda en venderse cada
compra, desde que entra hasta que sale su última unidad, promedio de las últimas
`dominio.COMPRAS_PARA_PROMEDIAR` (3) vendidas enteras, del más rápido al más lento
(`rotacion_repo.ranking_por_compras`). POR PERÍODO: últimos 7, 30 o 90 días; vendidas,
por día, stock y para cuántos días alcanza, con los quietos al final y en rojo lo que
se acaba en menos de `dominio.DIAS_PARA_AVISAR_ROTACION`
(`rotacion_repo.ranking_de_rotacion(desde, hasta)`). Las dos consultas están en la
lista blanca de otra PC. Lo abre quien tiene `permiso_reportes`. Con el séptimo, cada
acceso bajó a 86 de alto y 10 de separación. `MainWindow.acceso_tareas` se busca por
nombre: ya no es el último.

La suite se ejecuta con `python -m unittest discover tests` y tiene 1025 pruebas
al 2026-11-04 (el corte desde CYBERCONTROL fue el 2026-10-27). Lo que pasó antes de esa
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

Desde el 2026-11-03 toda la ventana principal tiene de fondo la foto del kiosko de
noche que eligió el dueño (`assets/fondo_inicio.jpg`, dibujada por
`ui/fondo_del_inicio.FondoDelInicio`: tapa todo sin deformarse y se recorta centrada), y
el título y los accesos van en un panel oscuro medio transparente
(`#panelInicio`, `#tituloInicio`, `#detalleInicio`). La foto agrandada es una sola
para todo el programa, no una por ventana: la ventana del Admin ya cerrada sigue
viva (la agarra `VueltaDelAdmin`) y con una copia propia cada salida del Admin
dejaba ~8 MB en memoria. Si falta el archivo, el fondo sale en `COLOR_SIN_FONDO`
(azul oscuro: sobre el gris de siempre el título claro no se leería).
