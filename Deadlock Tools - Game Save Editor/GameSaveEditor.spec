# -*- mode: python ; coding: utf-8 -*-
import os

spec_dir = os.path.dirname(os.path.abspath(SPEC))
repo_root = os.path.dirname(spec_dir)
sprite_dir = os.path.join(repo_root, "Deadlock Tools - Sprite and Animation Extractor")

a = Analysis(
    ["game_save_editor.py"],
    pathex=[spec_dir, sprite_dir],
    binaries=[],
    datas=[
        ("assets/GameSaveEditor.ico", "assets"),
        ("assets/GameSaveEditor.png", "assets"),
        ("assets/deadlock-game-tools-image.jpg", "assets"),
        ("assets/logo.jpg", "assets"),
        ("assets/world-map-tiles", "assets/world-map-tiles"),
        ("world_gen_tables.json", "."),
    ],
    hiddenimports=[
        "deadlock_territory_save",
        "world_gen_grid",
        "deadlock_research_save",
        "research_panel",
        "extract_deadlock_sprites",
        "pefile",
        "PIL",
        "PIL.Image",
        "PIL.ImageTk",
        "PIL.JpegImagePlugin",
        "PIL.PngImagePlugin",
        "PIL.GifImagePlugin",
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
    name="GameSaveEditor",
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
    icon=["assets/GameSaveEditor.ico"],
)
