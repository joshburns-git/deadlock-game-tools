"""Colony tile sprites from Deadlock SPRITELG.DAT (scaffolding).

Maps colony tile terrain codes to catalog sprite ids in deadlock.exe, then decodes
still frames from SPRITELG.DAT for display in the Colony tab.

Fill in TERRAIN_SPRITE_CATALOG once tile sprite locations are known.
"""
from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - optional until feature enabled
    Image = None  # type: ignore[assignment,misc]
    ImageTk = None  # type: ignore[assignment,misc]

ROOT = Path(__file__).resolve().parents[1]
SPRITE_EXTRACTOR_DIR = ROOT / "Deadlock Tools - Sprite and Animation Extractor"

WATER_TERRAIN = 4095


@dataclass(frozen=True)
class SpriteFrameRef:
    """Catalog sprite id + frame index within its chain."""

    catalog_id: int
    frame_index: int

    @classmethod
    def from_static_filename(cls, filename: str) -> SpriteFrameRef:
        """Parse sprite_0008_static_f02_15x24_hot-8_-26.gif style names."""
        stem = Path(filename).stem
        parts = stem.split("_")
        if len(parts) < 4 or parts[0] != "sprite" or parts[2] != "static":
            raise ValueError(f"Not a static sprite filename: {filename!r}")
        catalog_id = int(parts[1], 10)
        frame_index = int(parts[3][1:], 10)
        return cls(catalog_id=catalog_id, frame_index=frame_index)


TERRAIN_SPRITE_SLOTS: dict[int, str] = {
    1: "Rough",
    2: "Lightly wooded",
    3: "Heavily wooded",
    4: "Rocky",
    96: "Bog",
    101: "Wetland",
    WATER_TERRAIN: "Water",
}

# Resource tile sprites when territory type is Land/Water (not Swamp).
TERRAIN_SPRITE_CATALOG_LAND: dict[int, tuple[SpriteFrameRef, ...]] = {
    1: (
        SpriteFrameRef.from_static_filename("sprite_0101_static_f00_65x34_hot-32_-37.gif"),
        SpriteFrameRef.from_static_filename("sprite_0101_static_f01_65x34_hot-32_-37.gif"),
    ),
    4: (
        SpriteFrameRef.from_static_filename("sprite_0101_static_f10_55x36_hot-26_-39.gif"),
        SpriteFrameRef.from_static_filename("sprite_0101_static_f11_61x31_hot-30_-37.gif"),
    ),
    2: (
        SpriteFrameRef.from_static_filename("sprite_0102_static_f00_75x43_hot-38_-48.gif"),
        SpriteFrameRef.from_static_filename("sprite_0102_static_f01_68x41_hot-36_-47.gif"),
    ),
    3: (
        SpriteFrameRef.from_static_filename("sprite_0102_static_f04_69x44_hot-35_-47.gif"),
        SpriteFrameRef.from_static_filename("sprite_0102_static_f05_74x43_hot-34_-49.gif"),
    ),
    96: (
        SpriteFrameRef.from_static_filename("sprite_0101_static_f12_63x35_hot-31_-38.gif"),
    ),
    101: (
        SpriteFrameRef.from_static_filename("sprite_0101_static_f14_63x35_hot-31_-38.gif"),
    ),
}

# Resource tile sprites when territory type is Swamp.
TERRAIN_SPRITE_CATALOG_SWAMP: dict[int, tuple[SpriteFrameRef, ...]] = {
    1: (
        SpriteFrameRef.from_static_filename("sprite_0101_static_f04_65x34_hot-32_-37.gif"),
    ),
    4: (
        SpriteFrameRef.from_static_filename("sprite_0101_static_f08_58x32_hot-25_-38.gif"),
        SpriteFrameRef.from_static_filename("sprite_0101_static_f09_58x31_hot-29_-37.gif"),
    ),
    2: (
        SpriteFrameRef.from_static_filename("sprite_0102_static_f02_82x50_hot-40_-56.gif"),
        SpriteFrameRef.from_static_filename("sprite_0102_static_f03_82x54_hot-41_-61.gif"),
    ),
    3: (
        SpriteFrameRef.from_static_filename("sprite_0102_static_f06_92x56_hot-43_-62.gif"),
        SpriteFrameRef.from_static_filename("sprite_0102_static_f07_93x59_hot-46_-63.gif"),
    ),
    96: (
        SpriteFrameRef.from_static_filename("sprite_0101_static_f13_63x35_hot-31_-38.gif"),
    ),
    101: (
        SpriteFrameRef.from_static_filename("sprite_0101_static_f15_63x35_hot-31_-38.gif"),
    ),
}

# Backward-compatible alias for land/normal sprites.
TERRAIN_SPRITE_CATALOG = TERRAIN_SPRITE_CATALOG_LAND

DEFAULT_TERRAIN_DISPLAY_BOX = (0.92, 0.88)
TERRAIN_DISPLAY_BOX: dict[int, tuple[float, float]] = {}

RESOURCE_ICON_SIZE = 18

# Stockpile / yield row icons (catalog sprite 8).
RESOURCE_SPRITE_CATALOG: dict[str, SpriteFrameRef] = {
    "food": SpriteFrameRef.from_static_filename("sprite_0008_static_f02_15x24_hot-8_-26.gif"),
    "energy": SpriteFrameRef.from_static_filename("sprite_0008_static_f01_26x27_hot-12_-28.gif"),
    "wood": SpriteFrameRef.from_static_filename("sprite_0008_static_f00_24x17_hot-11_-23.gif"),
    "iron": SpriteFrameRef.from_static_filename("sprite_0008_static_f09_21x22_hot-9_-25.gif"),
    "steel": SpriteFrameRef.from_static_filename("sprite_0008_static_f07_25x20_hot-11_-24.gif"),
    "endurium": SpriteFrameRef.from_static_filename("sprite_0008_static_f04_21x22_hot-9_-25.gif"),
    "triidium": SpriteFrameRef.from_static_filename("sprite_0008_static_f03_25x20_hot-11_-24.gif"),
    "electronics": SpriteFrameRef.from_static_filename("sprite_0008_static_f05_27x20_hot-12_-23.gif"),
    "anti_matter": SpriteFrameRef.from_static_filename("sprite_0008_static_f08_26x27_hot-12_-28.gif"),
    "art": SpriteFrameRef.from_static_filename("sprite_0008_static_f06_12x30_hot-5_-29.gif"),
}


# Max display box as a fraction of colony tile diamond size (from in-game screenshot).
BONUS_DISPLAY_BOX: dict[int, tuple[float, float]] = {
    1: (0.14, 0.38),  # Food — narrow, tall stalks
    2: (0.28, 0.30),  # Energy atom
    3: (0.52, 0.38),  # Wood trees
    4: (0.36, 0.34),  # Iron rocks
    6: (0.36, 0.34),  # Endurium crystals
}

# Colony Terrain map: resource bonus overlay on tiles (not stockpile row icons).
BONUS_TILE_ICON_SCALE = 1.3

# Resource bonus icons from catalog sprite 8 (u16[2] in colony tile rows).
BONUS_SPRITE_CATALOG: dict[int, SpriteFrameRef] = {
    1: RESOURCE_SPRITE_CATALOG["food"],  # Fertile
    2: RESOURCE_SPRITE_CATALOG["energy"],  # Energy-rich
    3: RESOURCE_SPRITE_CATALOG["wood"],  # Wood-rich
    4: RESOURCE_SPRITE_CATALOG["iron"],  # Mineral-rich
    6: RESOURCE_SPRITE_CATALOG["endurium"],  # Endurium-rich
}


def terrain_sprite_catalog(*, is_swamp: bool = False) -> dict[int, tuple[SpriteFrameRef, ...]]:
    return TERRAIN_SPRITE_CATALOG_SWAMP if is_swamp else TERRAIN_SPRITE_CATALOG_LAND


@dataclass
class ColonySpriteLibrary:
    """Loads Deadlock art files and serves Tk-ready colony tile sprites."""

    deadlock_dir: Path | None = None
    load_error: str | None = None
    _exe: bytes | None = field(default=None, repr=False)
    _dat: bytes | None = field(default=None, repr=False)
    _palette: list[tuple[int, int, int]] | None = field(default=None, repr=False)
    _catalog_size: int = field(default=0, repr=False)
    _rgba_cache: dict[tuple[int, int], Image.Image] = field(default_factory=dict, repr=False)
    _photo_cache: dict[tuple[int, int, int], object] = field(default_factory=dict, repr=False)

    def is_ready(self) -> bool:
        return self.load_error is None and self._exe is not None and self._dat is not None

    def configure(self, deadlock_dir: Path) -> str | None:
        """Load deadlock.exe + SPRITELG.DAT from an install folder. Returns error text."""
        self.clear()
        self.deadlock_dir = deadlock_dir.resolve()

        if Image is None or ImageTk is None:
            return "Pillow is required for in-game colony sprites (pip install pillow)."

        exe_path = self.deadlock_dir / "deadlock.exe"
        dat_path = self.deadlock_dir / "SPRITELG.DAT"
        if not exe_path.is_file():
            return f"Could not find deadlock.exe in:\n{self.deadlock_dir}"
        if not dat_path.is_file():
            return f"Could not find SPRITELG.DAT in:\n{self.deadlock_dir}"

        try:
            extractor = _load_sprite_extractor()
            self._exe = exe_path.read_bytes()
            self._dat = dat_path.read_bytes()
            palette = extractor.load_palette_from_bitmap_resource(self._exe)
            self._palette = extractor.overlay_exe_palette(self._exe, palette)
            self._catalog_size = len(extractor.read_catalog(self._exe))
        except Exception as exc:  # pragma: no cover - surfaced in GUI
            self.clear()
            return f"Could not load Deadlock sprite data:\n{exc}"

        self.load_error = None
        return None

    def clear(self) -> None:
        self.deadlock_dir = None
        self.load_error = None
        self._exe = None
        self._dat = None
        self._palette = None
        self._catalog_size = 0
        self._rgba_cache.clear()
        self._photo_cache.clear()

    def catalog_size(self) -> int:
        return self._catalog_size

    def sprite_ref_for_terrain(
        self,
        base_terrain: int,
        row: int,
        col: int,
        *,
        is_swamp: bool = False,
    ) -> SpriteFrameRef | None:
        variants = terrain_sprite_catalog(is_swamp=is_swamp).get(base_terrain)
        if not variants:
            return None
        if len(variants) == 1:
            return variants[0]
        seed = hash((is_swamp, base_terrain, row, col)) & 0xFFFFFFFF
        return random.Random(seed).choice(variants)

    def terrain_sprite_configured(self, base_terrain: int, *, is_swamp: bool = False) -> bool:
        return base_terrain in terrain_sprite_catalog(is_swamp=is_swamp)

    def sprite_ref_for_bonus(self, bonus_code: int) -> SpriteFrameRef | None:
        return BONUS_SPRITE_CATALOG.get(bonus_code)

    def bonus_sprite_configured(self, bonus_code: int) -> bool:
        return bonus_code in BONUS_SPRITE_CATALOG

    def decode_still_sprite(self, sprite_id: int) -> Image.Image | None:
        """Decode catalog sprite still frame (index 0) to RGBA."""
        return self.decode_sprite_frame(sprite_id, 0)

    def decode_sprite_frame(self, sprite_id: int, frame_index: int) -> Image.Image | None:
        """Decode one frame from a catalog sprite chain to RGBA."""
        if not self.is_ready() or Image is None:
            return None

        cache_key = (sprite_id, frame_index)
        if cache_key in self._rgba_cache:
            return self._rgba_cache[cache_key]

        if sprite_id < 0 or sprite_id >= self._catalog_size:
            return None

        extractor = _load_sprite_extractor()
        assert self._exe is not None and self._dat is not None and self._palette is not None

        chain_va, _script_va, _delay = extractor.read_catalog(self._exe)[sprite_id]
        frames = extractor.iter_frames(self._exe, chain_va)
        if frame_index < 0 or frame_index >= len(frames):
            return None

        _hx, _hy, width, height, file_off = frames[frame_index]
        if width <= 0 or height <= 0:
            return None

        pixel_count = width * height
        pixels = self._dat[file_off : file_off + pixel_count]
        if len(pixels) < pixel_count:
            return None

        image = extractor.pixels_to_rgba(
            pixels,
            width,
            height,
            self._palette,
            extractor.TRANSPARENT,
        )
        self._rgba_cache[cache_key] = image
        return image

    def photo_for_terrain(
        self,
        base_terrain: int,
        tile_width: int,
        tile_height: int,
        master,
        *,
        row: int = 0,
        col: int = 0,
        is_swamp: bool = False,
    ) -> object | None:
        ref = self.sprite_ref_for_terrain(base_terrain, row, col, is_swamp=is_swamp)
        if ref is None or ImageTk is None or not self.is_ready():
            return None

        width_ratio, height_ratio = TERRAIN_DISPLAY_BOX.get(
            base_terrain,
            DEFAULT_TERRAIN_DISPLAY_BOX,
        )
        max_w = max(int(tile_width * width_ratio), 1)
        max_h = max(int(tile_height * height_ratio), 1)
        cache_key = ("terrain", is_swamp, base_terrain, ref.catalog_id, ref.frame_index, max_w, max_h)
        if cache_key in self._photo_cache:
            return self._photo_cache[cache_key]

        rgba = self.decode_sprite_frame(ref.catalog_id, ref.frame_index)
        if rgba is None:
            return None

        fitted = _fit_sprite_in_box(rgba, max_w, max_h)
        photo = ImageTk.PhotoImage(fitted, master=master)
        self._photo_cache[cache_key] = photo
        return photo

    def photo_for_bonus(
        self,
        bonus_code: int,
        tile_width: int,
        tile_height: int,
        master,
    ) -> object | None:
        ref = self.sprite_ref_for_bonus(bonus_code)
        if ref is None or ImageTk is None or not self.is_ready():
            return None

        width_ratio, height_ratio = BONUS_DISPLAY_BOX.get(bonus_code, (0.30, 0.30))
        width_ratio *= BONUS_TILE_ICON_SCALE
        height_ratio *= BONUS_TILE_ICON_SCALE
        max_w = max(int(tile_width * width_ratio), 1)
        max_h = max(int(tile_height * height_ratio), 1)
        cache_key = ("bonus", bonus_code, max_w, max_h)
        if cache_key in self._photo_cache:
            return self._photo_cache[cache_key]

        rgba = self.decode_sprite_frame(ref.catalog_id, ref.frame_index)
        if rgba is None:
            return None

        fitted = _fit_sprite_in_box(rgba, max_w, max_h)
        photo = ImageTk.PhotoImage(fitted, master=master)
        self._photo_cache[cache_key] = photo
        return photo

    def photo_for_resource(
        self,
        resource_key: str,
        size: int,
        master,
    ) -> object | None:
        ref = RESOURCE_SPRITE_CATALOG.get(resource_key)
        if ref is None or ImageTk is None or not self.is_ready():
            return None
        return self.photo_for_sprite_frame(ref.catalog_id, ref.frame_index, size, master)

    def photo_for_sprite_frame(
        self,
        sprite_id: int,
        frame_index: int,
        size: int,
        master,
    ) -> object | None:
        if ImageTk is None or not self.is_ready():
            return None

        cache_key = (sprite_id, frame_index, size)
        if cache_key in self._photo_cache:
            return self._photo_cache[cache_key]

        rgba = self.decode_sprite_frame(sprite_id, frame_index)
        if rgba is None:
            return None

        fitted = _fit_sprite(rgba, size)
        photo = ImageTk.PhotoImage(fitted, master=master)
        self._photo_cache[cache_key] = photo
        return photo


def register_terrain_sprite(
    base_terrain: int,
    filename: str,
    *,
    is_swamp: bool = False,
) -> None:
    """Register one terrain overlay sprite variant from a static extractor filename."""
    if base_terrain not in TERRAIN_SPRITE_SLOTS:
        known = ", ".join(f"{code}={label}" for code, label in TERRAIN_SPRITE_SLOTS.items())
        raise KeyError(f"Unknown terrain code {base_terrain}. Known slots: {known}")
    ref = SpriteFrameRef.from_static_filename(filename)
    catalog = terrain_sprite_catalog(is_swamp=is_swamp)
    existing = catalog.get(base_terrain, ())
    catalog[base_terrain] = (*existing, ref)


def _fit_sprite_in_box(image: Image.Image, max_w: int, max_h: int) -> Image.Image:
    width, height = image.size
    if width <= 0 or height <= 0:
        return image.copy()
    scale = min(max_w / width, max_h / height, 1.0)
    if scale >= 1.0:
        return image.copy()
    new_w = max(int(width * scale), 1)
    new_h = max(int(height * scale), 1)
    return image.resize((new_w, new_h), Image.Resampling.NEAREST)


def _fit_sprite(image: Image.Image, size: int) -> Image.Image:
    margin = 4
    max_size = max(size - margin, 1)
    fitted = image.copy()
    fitted.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return fitted


def _load_sprite_extractor():
    if getattr(sys, "frozen", False):
        import extract_deadlock_sprites

        return extract_deadlock_sprites
    if not SPRITE_EXTRACTOR_DIR.is_dir():
        raise FileNotFoundError(f"Sprite extractor not found: {SPRITE_EXTRACTOR_DIR}")
    path = str(SPRITE_EXTRACTOR_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    import extract_deadlock_sprites

    return extract_deadlock_sprites
