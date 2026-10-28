# Guía de trabajo para agentes — FRKiosko

La referencia vigente del proyecto es [CLAUDE.md](CLAUDE.md). Leela antes de
modificar código: contiene las 15 reglas, los puntos únicos de verdad, las
trampas del negocio y lo que el dueño pidió no cambiar sin hablarlo.
[README.md](README.md) describe los módulos actuales y
[LEEME.txt](LEEME.txt) explica el uso para el mostrador.

Este programa salió de CYBERCONTROL (el programa del cyber) el 2026-10-27,
sin nada de PCs, Miembros, Bonos, Trámites, PlayStation 5 ni Cliente PC. No
traigas de vuelta nada de eso: es otro negocio y otro repo.

Reglas esenciales:
- La UI no escribe SQL ni abre conexiones. Los repositorios contienen las
  reglas de negocio; `database.py` administra conexiones, claves y copias;
  `database_esquema.py` (+ `_cajas` y `_envios`) crea tablas e índices, y
  `database_migraciones.py` lleva la versión del esquema.
- Los estados, métodos de pago, turnos y orígenes viven en dominio.py.
- Cada operación que mueve plata o stock se guarda en una transacción.
- No toques data_fr/ ni la base real para desarrollar o probar. Los tests usan
  bases temporales.
- Verificá con python -m unittest discover tests y abrí Login y la ventana
  principal con una base temporal antes de declarar listo un cambio.
- La UI, los comentarios, los commits y las explicaciones al dueño van en
  español rioplatense.
- El repo es PÚBLICO: nunca una clave, contraseña o token real en el código,
  en una prueba, en un doc ni en un commit. La excepción es
  `CLAVE_PUBLICA_FIREBASE` (repositories/envio_pwa_repo.py): es la clave
  pública de la app de gastos, la misma que tiene la página, y va a propósito.
  No la saques.
- Puede haber otro agente (Claude) trabajando en la misma carpeta. Hacé cada
  cambio en una rama nueva (rama por cambio, como dice CLAUDE.md) y commiteá
  solo lo tuyo: antes de `git add` mirá el `git diff` de cada archivo y
  agregalos por nombre, nunca con `git add -A` ni `git commit -a`. Usá un
  mensaje que diga qué cambiaste, mergealo a `main` y dejá la carpeta otra vez
  en `main`. No dejes cambios sin commitear al terminar: lo que queda suelto se
  mezcla con el trabajo del otro.
- El `.exe` se arma solo cuando el dueño lo pide, con el Python instalado en la
  PC (no con el Python propio del agente) y la receta de CLAUDE.md. No agregues
  al `Kiosko.spec` archivos de tu entorno.
- Los comentarios explican el porqué de una decisión (regla 13 de CLAUDE.md):
  si sacás historia o fechas, no borres el motivo.
