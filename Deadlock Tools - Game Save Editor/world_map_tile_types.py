"""World-map autotile types (grid cell u16[2] high byte @ +0x05).

These are NOT colony/territory-view tile codes (see ``terrain_catalog.py``).
Each map cell stores exposure in the low byte and an autotile profile index (0–5)
in the high byte, selecting one of six stamp profiles in deadlock.exe @ 0x47F6E0.
"""
from __future__ import annotations

# High-byte profile index -> stable asset slug
WORLD_MAP_TILE_BY_HIGH: dict[int, str] = {
    0: "ocean",
    1: "swamp",
    2: "forest",
    3: "plains",
    4: "rocky",
    5: "mountains",
}

WORLD_MAP_TILE_LABELS: dict[str, str] = {
    "ocean": "Ocean",
    "swamp": "Swamp",
    "forest": "Forest",
    "plains": "Plains",
    "rocky": "Rocky",
    "mountains": "Mountains",
}

# Drop PNG/JPG files in assets/world-map-tiles/ (see WORLD_MAP_TILE_BY_HIGH slugs).
WORLD_MAP_TILE_DIRNAME = "world-map-tiles"
WORLD_MAP_TILE_DIRNAME_LEGACY = "world_map_tiles"

WORLD_MAP_TILE_RGB: dict[str, tuple[int, int, int]] = {
    "ocean": (36, 111, 184),
    "swamp": (58, 82, 48),
    "forest": (42, 98, 52),
    "plains": (196, 176, 132),
    "rocky": (128, 122, 118),
    "mountains": (148, 146, 152),
}

# World Editor palette: selecting this high-byte value means "pick territory", not paint.
WORLD_PALETTE_TERRITORY_SELECT = -1

# World Editor palette button order (high bytes), three per row.
WORLD_MAP_PALETTE_ORDER: tuple[int, ...] = (0, 3, 1, 2, 4, 5)


def high_byte_from_cell_value(cell_value: int) -> int:
    return (cell_value >> 8) & 0xFF


def tile_slug_for_high(high: int) -> str:
    return WORLD_MAP_TILE_BY_HIGH.get(high & 0xFF, "plains")


def tile_label_for_high(high: int) -> str:
    slug = tile_slug_for_high(high)
    return WORLD_MAP_TILE_LABELS.get(slug, slug.title())


def tile_rgb_hex(slug: str, *, fallback: str = "#666666") -> str:
    """Convert a tile slug RGB tuple to a Tk-compatible ``#rrggbb`` string."""
    rgb = WORLD_MAP_TILE_RGB.get(slug)
    if rgb is None:
        return fallback
    red, green, blue = rgb
    return f"#{red:02x}{green:02x}{blue:02x}"
