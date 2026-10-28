# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import ssl


datos = [('assets', 'assets')]
# El intérprete auxiliar puede necesitar este PEM al crear conexiones HTTPS.
certificado_ssl = Path(ssl.__file__).with_name('codex-rejected-cas.pem')
if certificado_ssl.is_file():
    datos.append((str(certificado_ssl), '.'))


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datos,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FRKiosko',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icono.ico'],
)

