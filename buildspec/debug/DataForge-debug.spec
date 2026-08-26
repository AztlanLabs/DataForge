# -*- mode: python ; coding: utf-8 -*-
# TICK-930 P1.19: no hardcoded user paths — resolve inputs relative to this
# spec file. Stack is PyQt5 (the retired Tk stack is gone).

import os

# SPECPATH is the directory containing this spec file (buildspec/debug).
PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir, os.pardir))


a = Analysis(
    [os.path.join(PROJECT_ROOT, 'run_ui.py')],
    pathex=[],
    binaries=[],
    datas=[(os.path.join(PROJECT_ROOT, 'dataforge', 'ui', 'plugins'), 'dataforge/ui/plugins')],
    hiddenimports=['PyQt5', 'PyQt5.QtCore', 'PyQt5.QtWidgets', 'PyQt5.QtGui', 'PIL', 'send2trash', 'pypdf'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=True,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [('v', None, 'OPTION')],
    exclude_binaries=True,
    name='DataForge-debug',
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DataForge-debug',
)