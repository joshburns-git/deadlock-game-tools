"""Static world-map tile images keyed by autotile profile (high byte 0–5)."""
from __future__ import annotations

import random
from pathlib import Path

import tkinter as tk
from PIL import Image, ImageDraw, ImageFont, ImageTk

from world_map_tile_types import (
    WORLD_MAP_TILE_BY_HIGH,
    WORLD_MAP_TILE_DIRNAME,
    WORLD_MAP_TILE_DIRNAME_LEGACY,
    WORLD_MAP_TILE_LABELS,
    WORLD_MAP_TILE_RGB,
)

TILE_PX = 32
DISPLAY_PX = 22
PALETTE_BUTTON_PX = 128
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")

# Optional alternate filenames (stem, without extension) beside the default slug.
TILE_FILE_ALIASES: dict[str, tuple[str, ...]] = {
    "ocean": ("water", "0"),
    "swamp": ("1",),
    "forest": ("woods", "2"),
    "plains": ("grass", "grasslands", "3"),
    "rocky": ("hills", "rough", "4"),
    "mountains": ("mountain", "5"),
}


class WorldMapTileLibrary:
    """Loads one PhotoImage per autotile type; reused for every map cell."""

    def __init__(self) -> None:
        self._tile_dir: Path | None = None
        self._photos: dict[int, ImageTk.PhotoImage] = {}
        self._palette_photos: dict[int, ImageTk.PhotoImage] = {}
        self._ready = False

    def configure(
        self,
        assets_dir: Path,
        *,
        master: tk.Misc,
        display_px: int = DISPLAY_PX,
        palette_px: int = PALETTE_BUTTON_PX,
    ) -> None:
        assets_dir = assets_dir.resolve()
        tile_dir = _resolve_tile_dir(assets_dir)
        tile_dir.mkdir(parents=True, exist_ok=True)
        self._photos.clear()
        self._palette_photos.clear()
        for high, slug in WORLD_MAP_TILE_BY_HIGH.items():
            path = _resolve_tile_path(tile_dir, slug)
            if path is None:
                path = tile_dir / f"{slug}.png"
                _write_placeholder_png(path, slug)
            tile = Image.open(path).convert("RGBA")
            if tile.size != (display_px, display_px):
                map_tile = tile.resize((display_px, display_px), Image.Resampling.LANCZOS)
            else:
                map_tile = tile
            self._photos[high] = ImageTk.PhotoImage(map_tile, master=master)
            label = WORLD_MAP_TILE_LABELS.get(slug, slug.title())
            palette_tile = compose_palette_button_image(tile, label, size=palette_px)
            self._palette_photos[high] = ImageTk.PhotoImage(palette_tile, master=master)
        self._tile_dir = tile_dir
        self._ready = True

    def is_ready(self) -> bool:
        return self._ready

    def tile_dir(self) -> Path | None:
        return self._tile_dir

    def photo_for_cell_value(self, cell_value: int) -> ImageTk.PhotoImage | None:
        if not self._ready:
            return None
        high = (cell_value >> 8) & 0xFF
        return self._photos.get(high) or self._photos.get(3)

    def photo_for_high(self, high: int) -> ImageTk.PhotoImage | None:
        if not self._ready:
            return None
        return self._photos.get(high & 0xFF) or self._photos.get(3)

    def palette_photo_for_high(self, high: int) -> ImageTk.PhotoImage | None:
        if not self._ready:
            return None
        return self._palette_photos.get(high & 0xFF) or self._palette_photos.get(3)


def compose_palette_button_image(
    tile: Image.Image,
    label: str,
    *,
    size: int = PALETTE_BUTTON_PX,
) -> Image.Image:
    """Build a square palette button image with centered label text."""
    button = tile.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(button)
    font = _palette_font(max(18, size // 10))
    bbox = draw.textbbox((0, 0), label, font=font)
    text_x = (size - (bbox[2] - bbox[0])) // 2 - bbox[0]
    text_y = (size - (bbox[3] - bbox[1])) // 2 - bbox[1]
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1), (-1, 1), (1, -1)):
        draw.text((text_x + dx, text_y + dy), label, font=font, fill=(0, 0, 0, 220))
    draw.text((text_x, text_y), label, font=font, fill=(255, 255, 255, 255))
    return button


def _palette_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _resolve_tile_dir(assets_dir: Path) -> Path:
    preferred = assets_dir / WORLD_MAP_TILE_DIRNAME
    if preferred.is_dir() and any(preferred.iterdir()):
        return preferred
    legacy = assets_dir / WORLD_MAP_TILE_DIRNAME_LEGACY
    if legacy.is_dir() and any(legacy.iterdir()):
        return legacy
    return preferred


def _resolve_tile_path(tile_dir: Path, slug: str) -> Path | None:
    stems = [slug, *TILE_FILE_ALIASES.get(slug, ())]
    label = WORLD_MAP_TILE_LABELS.get(slug, slug)
    stems.extend(
        [
            label.lower(),
            label.lower().replace(" ", "-"),
            label.lower().replace(" ", "_"),
        ]
    )
    seen: set[str] = set()
    for stem in stems:
        key = stem.lower()
        if key in seen:
            continue
        seen.add(key)
        for suffix in IMAGE_SUFFIXES:
            path = tile_dir / f"{stem}{suffix}"
            if path.is_file():
                return path

    by_stem = {p.stem.lower(): p for p in tile_dir.iterdir() if p.is_file()}
    for stem in stems:
        match = by_stem.get(stem.lower())
        if match is not None:
            return match
    return None


def _write_placeholder_png(path: Path, slug: str) -> None:
    """Create a simple textured placeholder users can replace with extracted art."""
    rgb = WORLD_MAP_TILE_RGB.get(slug, (160, 160, 160))
    img = Image.new("RGBA", (TILE_PX, TILE_PX), rgb + (255,))
    rng = random.Random(hash(slug) & 0xFFFFFFFF)
    px = img.load()
    for y in range(TILE_PX):
        for x in range(TILE_PX):
            delta = rng.randint(-12, 12)
            r, g, b, a = px[x, y]
            px[x, y] = (
                max(0, min(255, r + delta)),
                max(0, min(255, g + delta)),
                max(0, min(255, b + delta)),
                a,
            )
    if slug == "ocean":
        draw = ImageDraw.Draw(img)
        for x in range(0, TILE_PX, 8):
            draw.line([(x, 0), (x, TILE_PX)], fill=(255, 255, 255, 18), width=1)
    elif slug in ("forest", "swamp"):
        draw = ImageDraw.Draw(img)
        for _ in range(18):
            x0, y0 = rng.randint(0, TILE_PX - 1), rng.randint(0, TILE_PX - 1)
            draw.point((x0, y0), fill=(20, 40, 20, 120))
    elif slug == "mountains":
        draw = ImageDraw.Draw(img)
        draw.polygon(
            [(4, 28), (12, 10), (20, 28)],
            fill=(110, 108, 112, 200),
        )
        draw.polygon(
            [(14, 28), (22, 14), (30, 28)],
            fill=(130, 128, 132, 200),
        )
    img.save(path)
