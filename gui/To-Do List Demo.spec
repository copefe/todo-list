# -*- mode: python ; coding: utf-8 -*-
# Demo build: same UI/logic, sample data in %LOCALAPPDATA%\To-Do List Demo (see demo_app.py).
# Build: cd gui; pyinstaller --distpath dist-demo --workpath build-demo "To-Do List Demo.spec"
import os

# Paths are relative to this spec file (SPECPATH). The icon is optional: if gui/assets/icon.ico
# is missing the .exe is built with the default icon. pywebview takes the window icon on Windows
# from the running .exe, so no runtime code is needed.
_ICON = os.path.join(SPECPATH, "assets", "icon.ico")
ICON = _ICON if os.path.isfile(_ICON) else None


a = Analysis(
    ['demo_app.py'],
    pathex=[],
    binaries=[],
    datas=[('web', 'web')],
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
    name='To-Do List Demo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon=ICON,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
