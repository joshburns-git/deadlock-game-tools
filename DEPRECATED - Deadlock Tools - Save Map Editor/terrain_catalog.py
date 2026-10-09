"""Deadlock colony tile terrain and bonus catalog (v1.31 research)."""
from __future__ import annotations

from dataclasses import dataclass

# Special combined terrain word used for open water tiles.
WATER_TERRAIN = 4095

# High-byte flags OR'd with a base terrain code in the tile row u16[1] field.
# Observed on colonized territories in base.sav (e.g. ChCh't Landing).
TERRAIN_FLAG_1000 = 0x1000
TERRAIN_FLAG_2000 = 0x2000
TERRAIN_FLAG_4000 = 0x4000
TERRAIN_FLAG_8000 = 0x8000

KNOWN_TERRAIN_FLAGS: dict[int, str] = {
    TERRAIN_FLAG_1000: "flag 0x1000",
    TERRAIN_FLAG_2000: "flag 0x2000",
    TERRAIN_FLAG_4000: "flag 0x4000",
    TERRAIN_FLAG_8000: "flag 0x8000",
}

# Base terrain codes (low byte of the stored u16, unless value is WATER_TERRAIN).
BASE_TERRAIN: dict[int, str] = {
    0: "Clear",
    1: "Rough",
    2: "Lightly Wooded",
    3: "Heavily Wooded",
    4: "Rocky",
    5: "Terrain 5",
    6: "Terrain 6",
    8: "Terrain 8",
    9: "Terrain 9",
    10: "Terrain 10",
    11: "Terrain 11",
    12: "Terrain 12",
    96: "Bog",
    97: "Bog (alt)",
    101: "Wetland",
    115: "Shoal",
}

# Friendly presets for map editing (base code only; flags/yields copied separately).
TERRITORY_PRESETS: dict[str, int] = {
    "plains": 0,
    "clear": 0,
    "rough": 1,
    "light-woods": 2,
    "woods": 2,
    "forest": 3,
    "heavy-woods": 3,
    "mountains": 4,
    "rocky": 4,
    "bog": 96,
    "wetland": 101,
    "water": WATER_TERRAIN,
}

BONUS: dict[int, str] = {
    0: "(none)",
    1: "Fertile (Food)",
    2: "Energy-Rich",
    4: "Mineral-Rich (Iron)",
    6: "Endurium-Rich",
}

YIELD_NAMES = ("energy", "food", "wood", "iron", "endurium")


@dataclass(frozen=True)
class DecodedTerrain:
    raw: int
    base: int
    flags: int

    @property
    def label(self) -> str:
        if self.raw == WATER_TERRAIN:
            return "Water"
        base_label = BASE_TERRAIN.get(self.base, f"terrain?{self.base}")
        if not self.flags:
            return base_label
        flag_text = ",".join(
            KNOWN_TERRAIN_FLAGS[f] for f in sorted(KNOWN_TERRAIN_FLAGS) if self.flags & f
        )
        return f"{base_label} ({flag_text})" if flag_text else base_label


def split_terrain(raw: int) -> DecodedTerrain:
    if raw == WATER_TERRAIN:
        return DecodedTerrain(raw=WATER_TERRAIN, base=WATER_TERRAIN, flags=0)
    return DecodedTerrain(raw=raw & 0xFFFF, base=raw & 0xFF, flags=raw & 0xFF00)


def combine_terrain(base: int, flags: int = 0) -> int:
    if base == WATER_TERRAIN:
        return WATER_TERRAIN
    return ((flags & 0xFF00) | (base & 0xFF)) & 0xFFFF


def bonus_label(code: int) -> str:
    return BONUS.get(code, f"bonus?{code}")


def format_yield(centi: int) -> str:
    return f"{centi // 100}.{centi % 100:02d}"


def preset_base(name: str) -> int:
    key = name.strip().lower().replace("_", "-")
    if key not in TERRITORY_PRESETS:
        known = ", ".join(sorted(TERRITORY_PRESETS))
        raise KeyError(f"Unknown preset {name!r}. Known presets: {known}")
    return TERRITORY_PRESETS[key]


# Canvas colors for the 6x6 tile painter (base terrain codes).
TERRAIN_COLORS: dict[int, str] = {
    0: "#c8b48a",
    1: "#9a7b3c",
    2: "#7cab5a",
    3: "#2f6b3a",
    4: "#8a8a95",
    5: "#6f88aa",
    6: "#5d79a8",
    8: "#4f8ea8",
    96: "#4a5d3a",
    97: "#445636",
    101: "#56704a",
    115: "#5a8cad",
    WATER_TERRAIN: "#245f9a",
}

PALETTE_CHOICES: list[tuple[str, int]] = [
    ("Clear", 0),
    ("Rough", 1),
    ("Lightly Wooded", 2),
    ("Heavily Wooded", 3),
    ("Rocky", 4),
    ("Bog", 96),
    ("Wetland", 101),
    ("Water", WATER_TERRAIN),
]
