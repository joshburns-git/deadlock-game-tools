"""Deadlock colony tile terrain and bonus catalog (v1.31 research)."""
from __future__ import annotations

from dataclasses import dataclass

# Special combined terrain word used for open water tiles.
WATER_TERRAIN = 4095

# High-byte modifiers OR'd with a base terrain code in the tile row u16[1] field.
# These are NOT the same as the resource bonus field (u16[2]). On colonized territories
# they commonly appear on tiles that also carry colony building rows (see u16[10] in the
# same 0x20-byte record), but the exact meaning of each bit is not fully mapped yet.
TERRAIN_FLAG_1000 = 0x1000
TERRAIN_FLAG_2000 = 0x2000
TERRAIN_FLAG_4000 = 0x4000
TERRAIN_FLAG_8000 = 0x8000

KNOWN_TERRAIN_FLAGS: dict[int, str] = {
    TERRAIN_FLAG_1000: "modifier 0x1000",
    TERRAIN_FLAG_2000: "modifier 0x2000",
    TERRAIN_FLAG_4000: "modifier 0x4000",
    TERRAIN_FLAG_8000: "modifier 0x8000",
}

TERRAIN_MODIFIER_FLAGS: list[tuple[int, str]] = [
    (TERRAIN_FLAG_1000, "0x1000"),
    (TERRAIN_FLAG_2000, "0x2000"),
    (TERRAIN_FLAG_4000, "0x4000"),
    (TERRAIN_FLAG_8000, "0x8000"),
]

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
    3: "Wood-Rich",
    4: "Mineral-Rich (Iron)",
    6: "Endurium-Rich",
}

BONUS_CHOICES: list[tuple[int, str]] = list(BONUS.items())

YIELD_NAMES = ("energy", "food", "wood", "iron", "endurium")

# Colony tile rows store each yield as a signed 16-bit centi-unit (hundredths).
# Values above 327.00 (32800 centi) wrap negative in-game (328.00 → -327.36).
YIELD_MIN_CENTI = 0
YIELD_MAX_CENTI = 32700

YIELD_FIELD_LABELS: dict[str, str] = {
    "energy": "Energy",
    "food": "Food",
    "wood": "Wood",
    "iron": "Iron",
    "endurium": "Endurium",
}


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
    centi = clamp_yield(centi)
    return f"{centi // 100}.{centi % 100:02d}"


def clamp_yield(centi: int) -> int:
    """Clamp a centi-unit yield into the range the game treats as non-negative."""
    return max(YIELD_MIN_CENTI, min(int(centi), YIELD_MAX_CENTI))


def parse_yield(text: str) -> int:
    """Parse a yield display value like '25', '25.0', or '14.75' to stored centi-units."""
    cleaned = text.strip()
    if not cleaned:
        return YIELD_MIN_CENTI
    try:
        if "." in cleaned:
            whole, frac = cleaned.split(".", 1)
            frac = (frac + "00")[:2]
            if not whole:
                whole = "0"
            if not whole.lstrip("-").isdigit() or not frac.isdigit():
                return YIELD_MIN_CENTI
            value = int(whole) * 100 + int(frac)
        else:
            if not cleaned.lstrip("-").isdigit():
                return YIELD_MIN_CENTI
            value = int(cleaned) * 100
    except ValueError:
        return YIELD_MIN_CENTI
    return clamp_yield(value)


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
