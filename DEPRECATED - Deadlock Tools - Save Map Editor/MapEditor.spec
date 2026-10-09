# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

boundary_dir = Path(SPECPATH).resolve().parent / "DEPRECATED - Deadlock Tools - Territory Boundary Editor"

a = Analysis(
    ['map_editor_gui.py'],
    pathex=[str(boundary_dir)],
    binaries=[],
    datas=[
        ('assets/MapEditor.ico', 'assets'),
        ('assets/MapEditor.png', 'assets'),
        ('assets/logo.jpg', 'assets'),
        ('assets/deadlock-game-tools-image.jpg', 'assets'),
    ],
    hiddenimports=[
        'deadlock_territory_save',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL.JpegImagePlugin',
    ],
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
    name='MapEditor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/MapEditor.ico'],
)
