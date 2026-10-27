# Administrar FRKiosko desde otra PC del local

**Programado el 18/10/2026 en CYBERCONTROL** y heredado tal cual por este
programa (sin la parte de las PCs del cyber). Si lo querés revisar con ChatGPT,
este archivo se puede adjuntar tal cual.

## Lo que pediste

> "Desde la PC de mi casa entro con UltraVNC a otra PC que no está en uso, y con
> esa PC accedo al programa por red, me logueo como admin y de ahí hago las
> modificaciones que quiera hacer, o miro reportes, controlo, etc. Esto sin
> interrumpir a la operadora que está trabajando en ese momento."

## Cómo quedó

- **Una sola vez, en el mostrador:**
  1. Configuración ADMIN > **Entrar desde otra PC**: tildar "Permitir que el
     Administrador entre desde otra PC" y Guardar. Viene **apagado**.
  2. Compartir en la red la carpeta donde está FRKiosko.exe (con contraseña).
     La pantalla del paso 1 dice el nombre y la IP del mostrador.
- **Cada vez, en la otra PC:** abrir FRKiosko.exe **desde la carpeta
  compartida** (por ejemplo `\\MOSTRADOR\FRKiosko\FRKiosko.exe`) y entrar con
  el usuario Administrador y su clave.
- El programa se da cuenta solo de que lo abriste por la red. Esa copia **no
  abre ninguna base**: cada vez que una pantalla necesita un dato o guarda algo,
  se lo pide al FRKiosko del mostrador por la red del local (puerto 8909, uno
  distinto del de CYBERCONTROL para que los dos programas puedan convivir en la
  misma PC). El único que toca la base es el mostrador, como siempre.
- En la otra PC la ventana principal se ve como en el mostrador, con la caja
  abierta arriba y todos los botones. Los que venden, cobran o cierran el turno
  (Vender, Impresiones, Cierre de Turno) están, pero al apretarlos avisan
  **"Esto se hace en el mostrador"** y no hacen nada.
- Si el mostrador deja de contestar (se cortó la red, se cerró el programa del
  mostrador o se reinició), cada acción avisa que no lo encuentra; para
  conectarse espera 2 segundos como mucho y nunca pasa por un proxy de Windows.
- La operadora no ve nada ni se le traba la pantalla.

### Qué se puede hacer desde la otra PC

- **Administrar Kiosko completo:** Artículos (y precios), Compras, Control de
  Stock, Consulta de Ventas **con anular**, Reportes, Control de Cierres (con la
  carga de lo contado en el sobre y "Mandar a la app de gastos") y Usuarios.
- **Configuración ADMIN:** Accesos de Admin.
- **Caja** (solo mirar) y **Clave** (cambiar la propia).

### Qué sigue solo en el mostrador

Vender, cobrar, Cierre de Turno y las cajas, Copia de Seguridad, prender o
apagar la entrada desde otra PC y prender o apagar el envío de cierres a la app
de gastos. El cierre forzoso de la caja y el Administrador que vuelve solo a la
empleada también son cosas del mostrador.

## Por qué así y no "abriendo la base por la carpeta compartida"

La base (SQLite) no está hecha para que dos PCs la escriban por la red: si las
dos guardan justo a la vez, **se puede dañar el archivo con todas las ventas**.
Por eso, aunque abras el .exe desde la carpeta compartida, el programa nunca
abre la base de esa carpeta: le habla al programa del mostrador.

## Seguridad (dicho sin exagerar)

- Solo entra un usuario **Administrador** activo, con su clave. Una empleada no
  entra, ni siquiera con permisos de encargada.
- Viene **apagado**. Apagarlo en el mostrador corta en el acto a quien estaba
  adentro desde otra PC.
- **5 claves mal seguidas desde una PC** dejan a esa PC sin poder probar por 5
  minutos (las demás PCs no se afectan), y cada PC prueba de a una clave por
  vez. Además hay un tope para todas las PCs juntas: con 20 claves mal en 15
  minutos, nadie puede entrar desde otra PC hasta que pase ese rato (en el
  mostrador se sigue entrando normal). Alguien podría usar eso para no dejarte
  entrar desde otra PC un rato; nunca para entrar.
- La sesión vale solo desde la PC que entró, vence a las 3 horas sin uso y se
  pierde si se cierra el programa del mostrador. **Al terminar, cerrá sesión o
  cerrá el programa.**
- Solo se pueden pedir las funciones de una **lista cerrada**
  (`admin_remoto/lista_blanca.py`); cualquier otra se rechaza aunque venga con
  la clave del Administrador.
- **Quién hizo cada cosa** (quién anuló, quién cargó la compra o el sobre) lo
  anota el mostrador con el Administrador que entró, no con lo que mande la otra
  PC.
- Cada ingreso queda en **Accesos de Admin**, con la IP de la PC desde donde se
  entró.
- El hash de las claves nunca sale del mostrador.
- **Límite honesto:** dentro de la red del local la clave viaja sin cifrar.
  Alguien que logre espiar la red del local podría verla. Como se puede entrar
  desde cualquier PC del local, **la clave del Administrador tiene que ser
  buena** (no 1234, ni el nombre, ni una fecha). Nada de esto queda abierto a
  internet: desde tu casa seguís entrando por UltraVNC.

## Qué pasa si...

- **El mostrador está apagado o con FRKiosko cerrado:** la otra PC avisa "No
  encuentro el FRKiosko del mostrador". Lo que ya guardaste quedó guardado.
- **Se corta la red con la sesión abierta:** cada acción avisa que no encuentra
  el mostrador; cuando vuelve la red, sigue andando (si pasaron más de 3 horas,
  hay que cerrar sesión y volver a entrar).
- **Se reinicia el programa del mostrador:** la sesión de la otra PC se pierde;
  la próxima acción avisa "La sesión desde esta PC se cerró": cerrás sesión y
  volvés a entrar.
- **Cambiás un precio mientras ella tiene ese artículo en el carrito:** ese
  cliente paga el precio viejo; el próximo escaneo trae el nuevo.
- **Cargás una compra mientras ella vende ese artículo:** el stock queda bien
  (cada operación se guarda entera, una detrás de la otra).
- **El .exe del mostrador y el de la otra PC no son el mismo:** no deja entrar
  y avisa. Abriéndolo siempre desde la carpeta compartida, son el mismo.
- **Sacás un reporte de un año:** medido en CYBERCONTROL con una base de prueba
  de un año (110.000 ventas): todos los reportes tardan menos de 0,2 segundos,
  así que la venta del mostrador ni lo nota.
- **Windows pregunta si querés ejecutar el archivo** al abrirlo desde la red:
  decile que sí.

## Cómo se prueba

- `tests/test_admin_remoto.py`: sin clave o con la de una empleada no se entra;
  con la entrada apagada tampoco; una función fuera de la lista se rechaza; la
  sesión no sirve desde otra PC; las 5 claves mal (también mandadas todas juntas,
  o desde varias PCs); quién anula es quien entró; el hash no viaja; y una
  **copia remota de verdad** contra un **mostrador de prueba en otro proceso**
  (`tests/mostrador_de_prueba.py`, con una base de prueba, nunca la real): abre
  todas las pantallas de administración sin errores, cambia un precio, carga una
  compra, anula una venta, carga un sobre, y todo queda en la base del
  mostrador; esa copia nunca crea una base propia.
- Una prueba revisa las pantallas que se abren desde otra PC: si alguna empieza
  a usar una función que no está en la lista, falla y dice cuál.

---

## Anexo técnico

- `admin_remoto/modo.py`: copia remota si `database.BASE_DIR` es una ruta
  `\\PC\carpeta` (o `\\?\UNC\...`) o una unidad de red (`GetDriveTypeW` =
  `DRIVE_REMOTE` → `WNetGetConnectionW`); la PC es la de la ruta. Para probar:
  `python main.py --mostrador <ip>`.
- `admin_remoto/cliente.py`: `instalar()` cierra la base local (reemplaza
  `conexion_db`/`get_connection` en `database` y en todo módulo que se trajo su
  referencia), manda `DATA_DIR` (solo el log de errores) a
  `%LOCALAPPDATA%\FRKiosko\administracion_remota` y reemplaza en su módulo cada
  función de la lista blanca por un representante que hace `POST /admin/llamar`.
  `listar_usuarios`/`autenticar_por_nombre` antes de entrar van por
  `/admin/usuarios` y `/admin/entrar`. Errores: `ValueError`/`PermissionError`
  del mostrador llegan con su mensaje; sin red, `SinConexion` (un `ValueError`).
- `admin_remoto/servidor.py` (lo llama `servidor_red.do_POST` para `/admin/`;
  es lo único que atiende el servidor de red de este programa): token
  `secrets.token_urlsafe(32)` en memoria, atado a la IP del socket, vence a los
  180 min sin uso; bloqueo por IP tras 5 claves mal (5 min), una prueba de clave
  a la vez por IP, un bloqueo nunca se acorta, y tope global de 20 claves mal en
  15 min; en cada llamada, `admin_remoto_repo.exigir_admin_habilitado`;
  `inspect.signature(...).bind` de los argumentos y el `ACTOR` se pisa con el
  usuario del token; tope de 16 MB por pedido; nunca loguea claves ni cuerpos.
- `admin_remoto/codec.py`: JSON con etiquetas de una clave (`__t` tupla, `__s`
  conjunto, `__d` diccionario con claves no-texto, `__r` fila, `__dt`/`__da`
  fechas, `__b` bytes en base64). Del otro lado solo se arman esos tipos.
  `FilaRemota` se comporta como `sqlite3.Row`. `clave_hash` sale vacío.
- `admin_remoto/lista_blanca.py`: `FUNCIONES` (módulo → nombres), `ACTOR`
  ((módulo, función) → parámetro) y `huella()` (sha256 de la lista, las firmas y
  los actores + versión del protocolo; se compara en `/admin/hola`, `usuarios` y
  `entrar`).
- Esquema: `sesiones.desde_ip` (viene en el esquema de una base nueva) e índice
  `idx_venta_pagos_venta`.
- Concurrencia: el servidor corre en hilos con conexiones propias; SQLite sin
  WAL, así que una lectura larga frena una escritura del mostrador hasta 5 s
  (timeout por defecto) — por eso se midieron los reportes con un año de datos.
