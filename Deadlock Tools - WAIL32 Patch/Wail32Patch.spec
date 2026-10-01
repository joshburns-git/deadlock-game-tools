# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['wail32_patch_gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/Wail32Patch.ico', 'assets'),
        ('assets/Wail32Patch.png', 'assets'),
        ('assets/logo.jpg', 'assets'),
        ('assets/deadlock-game-tools-image.jpg', 'assets'),
    ],
    hiddenimports=['PIL', 'PIL.Image', 'PIL.ImageTk', 'PIL.JpegImagePlugin'],
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
    name='Wail32Patch',
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
    icon=['assets/Wail32Patch.ico'],
)
