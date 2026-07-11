# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\coron\\OneDrive\\Documents\\Python\\FileManager\\run_ui.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\coron\\OneDrive\\Documents\\Python\\FileManager\\filemanager\\ui\\plugins', 'filemanager/ui/plugins')],
    hiddenimports=['ttkbootstrap', 'PIL', 'PIL.ImageTk', 'send2trash', 'pypdf'],
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
    name='FileManager-debug',
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
    name='FileManager-debug',
)
