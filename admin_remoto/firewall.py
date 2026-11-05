"""
firewall.py
===========
Que el firewall de Windows del MOSTRADOR deje entrar a las otras PCs del local
al puerto de la administración remota (servidor_red.PUERTO_SERVIDOR, el 8909).

Por qué hace falta (2026-11-05, en el local): con la entrada prendida y el
programa del mostrador escuchando en el 8909 (netstat: LISTENING), la PC de la
oficina decía "No encuentro el FRKiosko del mostrador". La carpeta compartida
andaba (pasa por otra regla de Windows, la de compartir archivos), el 8909 no.
La primera vez que un .exe abre un puerto, Windows pregunta si lo deja; si nadie
aprieta "Permitir acceso" (o aprietan Cancelar), anota reglas que BLOQUEAN a ese
.exe, y en el firewall de Windows una regla que bloquea le gana a cualquiera que
permita. Por eso no alcanza con agregar la nuestra: hay que sacar esas.

- revisar(): sin pedir permiso, si está nuestra regla y si hay alguna regla que
  bloquee a este .exe. Lee las reglas por COM (HNetCfg.FwPolicy2): con
  Get-NetFirewallRule y el filtro de programa de cada regla tardaba ~50 s en una
  PC con muchas reglas; así, menos de un segundo.
- abrir(): con permiso de Administrador (Windows lo pide con su cartel, el UAC).
  Borra las reglas de entrada de este .exe que bloquean y agrega la nuestra: el
  8909 por TCP, solo desde la red del local (LocalSubnet: nada queda abierto a
  internet) y en cualquier tipo de red (si Windows marcó la red del local como
  "Pública", una regla solo para "Privada" no serviría). Una va atada al puerto
  (sigue sirviendo si el .exe se cambia de carpeta) y otra, igual, atada al .exe:
  con una regla propia del programa Windows no debería volver a preguntar.
  Después revisa de nuevo: lo que manda es lo que quedó, no lo que contestó
  PowerShell.

Este paquete no sabe de Qt: la pantalla (ui/admin_remoto_dialogo.py) llama a las
dos en un hilo aparte y le pasa a abrir() el número de su ventana, para que el
cartel de Windows salga adelante.
"""

import base64
import ctypes
import os
import subprocess
import sys
from typing import NamedTuple, Optional

from servidor_red import PUERTO_SERVIDOR

NOMBRE_DE_LA_REGLA = "FRKiosko - Entrar desde otra PC"

# Lo que devuelve abrir().
ABIERTO = "abierto"
CANCELADO = "cancelado"  # dijeron que No en el cartel de Windows
NO_SE_PUDO = "no_se_pudo"

ESPERA_REVISAR_SEGUNDOS = 30
ESPERA_ABRIR_SEGUNDOS = 120

_SIN_VENTANA_DE_CONSOLA = 0x08000000  # CREATE_NO_WINDOW: que no titile una ventana negra
_ERROR_CANCELADO = 1223  # ERROR_CANCELLED: en el cartel del UAC dijeron que No


class Revision(NamedTuple):
    regla_que_permite: bool  # está nuestra regla, prendida
    bloqueos: int  # reglas de entrada prendidas que bloquean a este .exe

    @property
    def abierto(self) -> bool:
        return self.regla_que_permite and self.bloqueos == 0


def programa_de_este_frkiosko() -> Optional[str]:
    """El .exe al que Windows le anota las reglas cuando abre el puerto. None
    corriendo desde el código: ahí quien abre el puerto es python.exe, y sus
    reglas no se tocan."""
    return os.path.abspath(sys.executable) if getattr(sys, "frozen", False) else None


# --------------------------------------------------------------------
# Lo que corre PowerShell
# --------------------------------------------------------------------

def _texto_en_powershell(texto: str) -> str:
    """Un texto cualquiera puesto dentro del script sin que ninguna comilla lo
    rompa: viaja en base64 y PowerShell lo vuelve a armar."""
    codificado = base64.b64encode(texto.encode("utf-8")).decode("ascii")
    return f"[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{codificado}'))"


# Las reglas de entrada (Direction 1) que bloquean (Action 0) a $p. -eq compara
# sin mayúsculas, y la ruta guardada puede venir con %VARIABLES%.
_REGLAS_QUE_BLOQUEAN_AL_PROGRAMA = (
    "@($fw.Rules|Where-Object{$_.Direction -eq 1 -and $_.Action -eq 0 -and $_.ApplicationName "
    "-and [Environment]::ExpandEnvironmentVariables($_.ApplicationName) -eq $p})"
)


def _comienzo(programa: Optional[str]) -> str:
    # Sin $ProgressPreference, la primera vez PowerShell escribe "Preparando
    # módulos para el primer uso" en la salida de errores.
    return (
        "$ProgressPreference='SilentlyContinue'\n"
        f"$n={_texto_en_powershell(NOMBRE_DE_LA_REGLA)}\n"
        f"$p={_texto_en_powershell(programa or '')}\n"
        "$fw=New-Object -ComObject HNetCfg.FwPolicy2\n"
    )


def _script_revisar(programa: Optional[str]) -> str:
    """Escribe "<reglas nuestras prendidas que permiten>;<reglas que bloquean>"."""
    return _comienzo(programa) + (
        "$r=@($fw.Rules|Where-Object{$_.Name -eq $n -and $_.Enabled -and $_.Direction -eq 1 "
        "-and $_.Action -eq 1}).Count\n"
        f"$b=0;if($p){{$b=@({_REGLAS_QUE_BLOQUEAN_AL_PROGRAMA}|Where-Object{{$_.Enabled}}).Count}}\n"
        "Write-Output ('{0};{1}' -f $r,$b)\n"
    )


def _script_abrir(programa: Optional[str]) -> str:
    """Corre como Administrador. netsh borra por la ruta EXACTA que guardó cada
    regla (por eso se la toma de la regla); `"program=$v"` llega a netsh entre
    comillas aunque la carpeta tenga espacios."""
    reglas_nuevas = (
        f"dir=in action=allow protocol=TCP localport={PUERTO_SERVIDOR} remoteip=localsubnet profile=any"
    )
    return _comienzo(programa) + (
        "if($p){foreach($v in @(" + _REGLAS_QUE_BLOQUEAN_AL_PROGRAMA
        + "|ForEach-Object{$_.ApplicationName}|Sort-Object -Unique)){"
        "netsh advfirewall firewall delete rule name=all dir=in \"program=$v\"|Out-Null}}\n"
        "netsh advfirewall firewall delete rule \"name=$n\"|Out-Null\n"
        f"netsh advfirewall firewall add rule \"name=$n\" {reglas_nuevas}|Out-Null\n"
        "if($LASTEXITCODE -ne 0){exit 4}\n"
        f"if($p){{netsh advfirewall firewall add rule \"name=$n\" \"program=$p\" {reglas_nuevas}|Out-Null\n"
        "if($LASTEXITCODE -ne 0){exit 5}}\n"
        "exit 0\n"
    )


def _powershell() -> str:
    raiz = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.join(raiz, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


def _argumentos(script: str) -> list:
    """-EncodedCommand: el script viaja en base64 (UTF-16), sin pelearse con las
    comillas de la línea de comandos."""
    codificado = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return ["-NoProfile", "-NonInteractive", "-EncodedCommand", codificado]


def _leer_revision(salida: bytes) -> Optional[Revision]:
    for renglon in reversed(salida.decode("ascii", errors="ignore").splitlines()):
        partes = renglon.strip().split(";")
        if len(partes) == 2 and all(parte.isdigit() for parte in partes):
            return Revision(int(partes[0]) > 0, int(partes[1]))
    return None


# --------------------------------------------------------------------
# Lo que usa la pantalla
# --------------------------------------------------------------------

def revisar(programa: Optional[str]) -> Optional[Revision]:
    """Cómo está hoy el firewall para el puerto de la administración remota, o
    None si no se pudo saber (no es Windows, PowerShell no anduvo)."""
    if os.name != "nt":
        return None
    try:
        hecho = subprocess.run(
            [_powershell(), *_argumentos(_script_revisar(programa))],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=ESPERA_REVISAR_SEGUNDOS,
            creationflags=_SIN_VENTANA_DE_CONSOLA,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return _leer_revision(hecho.stdout)


def abrir(programa: Optional[str], ventana: int = 0) -> str:
    """Abre el puerto con permiso de Administrador (sale el cartel de Windows).
    ABIERTO si después de hacerlo la revisión da bien; CANCELADO si en el cartel
    dijeron que No; NO_SE_PUDO si no."""
    if os.name != "nt":
        return NO_SE_PUDO
    codigo = _correr_como_administrador(
        _powershell(), subprocess.list2cmdline(_argumentos(_script_abrir(programa))), ventana,
    )
    if codigo is None:
        return CANCELADO
    revision = revisar(programa)
    if revision is not None:
        return ABIERTO if revision.abierto else NO_SE_PUDO
    return ABIERTO if codigo == 0 else NO_SE_PUDO


# --------------------------------------------------------------------
# Correr algo con permiso de Administrador (ShellExecuteEx con "runas")
# --------------------------------------------------------------------

class _ShellExecuteInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("fMask", ctypes.c_ulong),
        ("hwnd", ctypes.c_void_p),
        ("lpVerb", ctypes.c_wchar_p),
        ("lpFile", ctypes.c_wchar_p),
        ("lpParameters", ctypes.c_wchar_p),
        ("lpDirectory", ctypes.c_wchar_p),
        ("nShow", ctypes.c_int),
        ("hInstApp", ctypes.c_void_p),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", ctypes.c_wchar_p),
        ("hkeyClass", ctypes.c_void_p),
        ("dwHotKey", ctypes.c_uint32),
        ("hIconOrMonitor", ctypes.c_void_p),
        ("hProcess", ctypes.c_void_p),
    ]


_DEVOLVER_EL_PROCESO = 0x00000040  # SEE_MASK_NOCLOSEPROCESS
_SIN_SEGUIR_DE_FONDO = 0x00000100  # SEE_MASK_NOASYNC: lo llama un hilo que después termina
_ESCONDIDA = 0  # SW_HIDE
_TODAVIA_CORRE = 259  # STILL_ACTIVE


def _correr_como_administrador(archivo: str, parametros: str, ventana: int = 0,
                               verbo: str = "runas") -> Optional[int]:
    """Corre `archivo parametros` (escondido) con el permiso que pide `verbo` y
    espera a que termine. Devuelve su código de salida, None si en el cartel de
    Windows dijeron que No, o -1 si no arrancó. `verbo` cambia solo en las
    pruebas ("open": sin cartel)."""
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ole32 = ctypes.WinDLL("ole32")
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_ShellExecuteInfo)]
    shell32.ShellExecuteExW.restype = ctypes.c_int
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole32.CoInitializeEx.restype = ctypes.c_long

    # ShellExecuteEx pide COM prendido en el hilo que lo llama (este es un hilo
    # aparte). 0 o 1 (S_FALSE): quedó prendido y hay que apagarlo al final.
    com_prendido = ole32.CoInitializeEx(None, 0x2 | 0x4) in (0, 1)  # APARTMENTTHREADED | DISABLE_OLE1DDE
    try:
        info = _ShellExecuteInfo()
        info.cbSize = ctypes.sizeof(info)
        info.fMask = _DEVOLVER_EL_PROCESO | _SIN_SEGUIR_DE_FONDO
        info.hwnd = ventana or None
        info.lpVerb = verbo
        info.lpFile = archivo
        info.lpParameters = parametros
        info.nShow = _ESCONDIDA
        if not shell32.ShellExecuteExW(ctypes.byref(info)):
            return None if ctypes.get_last_error() == _ERROR_CANCELADO else -1
        if not info.hProcess:
            return -1
        try:
            kernel32.WaitForSingleObject(info.hProcess, ESPERA_ABRIR_SEGUNDOS * 1000)
            codigo = ctypes.c_uint32()
            if not kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(codigo)):
                return -1
            return -1 if codigo.value == _TODAVIA_CORRE else codigo.value
        finally:
            kernel32.CloseHandle(info.hProcess)
    finally:
        if com_prendido:
            ole32.CoUninitialize()
