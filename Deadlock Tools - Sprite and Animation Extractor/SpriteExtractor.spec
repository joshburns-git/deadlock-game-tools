# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['sprite_extractor_gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/SpriteExtractor.ico', 'assets'),
        ('assets/SpriteExtractor.png', 'assets'),
        ('assets/deadlock-game-tools-image.jpg', 'assets'),
    ],
    hiddenimports=['PIL', 'PIL.Image', 'PIL.ImageTk', 'PIL.GifImagePlugin', 'PIL.PngImagePlugin', 'PIL.JpegImagePlugin'],
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
    name='SpriteExtractor',
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
    icon=['assets/SpriteExtractor.ico'],
)
