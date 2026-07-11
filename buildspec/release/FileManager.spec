# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['/mnt/pharos/Data/Documents/Python/FileManager_Repo/DataForge/run_ui.py'],
    pathex=[],
    binaries=[],
    datas=[('/mnt/pharos/Data/Documents/Python/FileManager_Repo/DataForge/filemanager/ui/plugins', 'filemanager/ui/plugins')],
    hiddenimports=['PyQt5', 'PyQt5.QtCore', 'PyQt5.QtWidgets', 'PyQt5.QtGui', 'PIL', 'send2trash', 'pypdf'],
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
    name='FileManager',
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
)
