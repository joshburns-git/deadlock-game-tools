#!/usr/bin/env python3
"""Python port of Deadlock world-gen strategic grid encoding (partial).

Sources (deadlock.exe v1.31):
- ``0x00438960`` / ``0x00438B94`` — outline exposure -> grid ``+4`` low byte
- ``0x0043EBA3`` — outline profile -> grid ``+5`` high byte from subtype + RNG
- ``0x004290EB`` — runtime strategic cell template (type index + table byte)
- ``DEFAULT_WORLD_MAP_EXPOSURE_CATALOG`` — exposure -> stored low byte per profile
"""
from __future__ import annotations

import json
import struct
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from deadlock_territory_save import (
    DEFAULT_WORLD_MAP_EXPOSURE_CATALOG,
    GRID_CELL_BYTES,
    GRID_CELL_VALUE_OFF,
    STORED_RECORD,
    TERRAIN_SUBTYPE_FOREST,
    TERRAIN_SUBTYPE_MOUNTAINS,
    TERRAIN_SUBTYPE_PLAINS,
    TERRAIN_SUBTYPE_SWAMP,
    LoadedSave,
    SaveLayout,
    TerritoryInfo,
    _neighbor_exposure,
    _pack_grid_cell_u16_2,
    _pick_terrain_tile_for_exposure,
    _split_grid_cell_u16_2,
    outline_sort_key,
    read_grid_cell_value,
    write_grid_cell_value,
)

TABLES_JSON = Path(__file__).with_name("world_gen_tables.json")
SECTION3_SIZE = 0x14

TYPE_TABLE_VA = 0x4979AB
TYPE_TABLE_STRIDE = 40
ANCHOR_CELL_INDEX_OFF = 0x74
TERRAIN_SUBTYPE_OCEAN = 0

# Pass-2 neighbor stamp thresholds @ ``0x0047F4CC`` (index = ``3*dx + dy``).
PASS2_NEIGHBOR_THRESHOLDS: dict[int, int] = {
    -4: 40,
    -3: 30,
    -2: 20,
    -1: 30,
    0: 100,
    1: 100,
    2: 20,
    3: 100,
    4: 100,
}


class DeadlockRng:
    """64-bit LCG matching ``deadlock.exe`` ``0x004636FC`` / seed ``0x004636CC``."""

    _MULT = 0x4E35

    def __init__(self, lo: int, hi: int = 0) -> None:
        self.lo = lo & 0xFFFFFFFF
        self.hi = hi & 0xFFFFFFFF

    @classmethod
    def from_header_seed(cls, seed: int) -> DeadlockRng:
        """Seed like ``0x439737`` → ``0x4636CC([0x47FB60])``."""
        return cls(seed & 0xFFFFFFFF, 0)

    def next(self) -> int:
        hi_in, lo_in = self.hi, self.lo
        mult = self._MULT
        if hi_in:
            eax = (hi_in * mult) & 0xFFFFFFFF
            ecx = ((lo_in * mult) + eax) & 0xFFFFFFFF
            carry = 1 if ecx < ((lo_in * mult) & 0xFFFFFFFF) else 0
            esi = ((hi_in * mult) >> 32) + ((lo_in * mult) >> 32) + carry
            eax = (hi_in * mult) & 0xFFFFFFFF
            edx = (esi + (eax >> 32)) & 0xFFFFFFFF
            new_lo = (eax + 1) & 0xFFFFFFFF
            new_hi = (edx + (1 if new_lo == 0 else 0)) & 0xFFFFFFFF
        else:
            prod = (0x15A4 * lo_in) & 0xFFFFFFFF
            eax = (lo_in * mult) & 0xFFFFFFFF
            edx = (lo_in * mult) >> 32
            new_lo = (eax + 1) & 0xFFFFFFFF
            new_hi = (edx + prod + (1 if new_lo == 0 else 0)) & 0xFFFFFFFF
        self.lo, self.hi = new_lo, new_hi
        return new_hi & 0x7FFFFFFF

    def rand_mod(self, mod: int) -> int:
        if mod <= 0:
            return 0
        return self.next() & (mod - 1)


def profile_high_from_43eba3(
    subtype: int,
    rng: DeadlockRng,
    *,
    existing_hi: int = 0,
    skip_if_hi_is_4: bool = False,
) -> int:
    """One cell assignment from ``0x0043EBA3`` switch on ``record+0x21``."""
    if skip_if_hi_is_4 and (existing_hi & 0xFF) == 4:
        return existing_hi & 0xFF
    if subtype == 0:
        return 0
    if subtype == TERRAIN_SUBTYPE_SWAMP:
        return 1
    if subtype == TERRAIN_SUBTYPE_MOUNTAINS:
        return 5
    if subtype == TERRAIN_SUBTYPE_PLAINS:
        return 4 if rng.rand_mod(16) == 0 else 3
    if subtype == TERRAIN_SUBTYPE_FOREST:
        return 4 if rng.rand_mod(8) == 0 else 2
    return 0


def read_world_seed_from_save(data: bytes) -> int:
    blob = data[0x7A + 0x6A : 0x7A + 0x6A + SECTION3_SIZE]
    return struct.unpack_from("<I", blob, 0)[0]


def read_world_seed2_from_save(data: bytes) -> int:
    """Second seed dword — ``0x439737`` re-seeds RNG via ``0x4636CC([0x47FB60+4])`` before ``0x43F115``."""
    blob = data[0x7A + 0x6A : 0x7A + 0x6A + SECTION3_SIZE]
    return struct.unpack_from("<I", blob, 4)[0]


def rng_for_43eba3(data: bytes, *, advance: int = 0) -> DeadlockRng:
    """RNG state at the ``0x43EBA3`` entry inside ``0x43F115`` (after second ``0x4636CC``)."""
    rng = DeadlockRng.from_header_seed(read_world_seed2_from_save(data))
    for _ in range(advance):
        rng.next()
    return rng


def _territory_record_off(layout: SaveLayout, territory: TerritoryInfo) -> int:
    return layout.territory_offset + (territory.index - 1) * STORED_RECORD


def _anchor_cell_index(data: bytes, layout: SaveLayout, territory: TerritoryInfo) -> int | None:
    """Outline list index stored at record ``+0x74`` for pass-2 anchor stamp."""
    if territory.terrain_subtype == TERRAIN_SUBTYPE_OCEAN:
        return None
    record_off = _territory_record_off(layout, territory)
    raw = data[record_off + ANCHOR_CELL_INDEX_OFF]
    if raw == 0xFF:
        return None
    return raw & 0xFF


def _pass2_neighbor_threshold(dx: int, dy: int) -> int | None:
    if not (-1 <= dx <= 1 and -1 <= dy <= 1):
        return None
    return PASS2_NEIGHBOR_THRESHOLDS.get(3 * dx + dy)


def iter_43eba3_pass1_cells(
    save: LoadedSave,
    data: bytes,
) -> list[tuple[TerritoryInfo, int, int]]:
    """Yield ``(territory, x, y)`` in ``0x0043EBA3`` pass-1 order."""
    out: list[tuple[TerritoryInfo, int, int]] = []
    for territory in sorted(save.territories, key=lambda t: t.index):
        if territory.terrain_subtype > 4:
            continue
        for x, y in sorted(territory.cells, key=outline_sort_key):
            if save.grid[y][x] != territory.territory_id:
                continue
            out.append((territory, x, y))
    return out


def score_43eba3_profile_map(
    save: LoadedSave,
    data: bytes,
    profile_by_coord: dict[tuple[int, int], int],
) -> tuple[int, int]:
    """Return ``(matches, total)`` for outline cells with subtype ``<= 4``."""
    layout = save.layout
    total = 0
    matched = 0
    for territory in save.territories:
        if territory.terrain_subtype > 4:
            continue
        for x, y in territory.cells:
            if save.grid[y][x] != territory.territory_id:
                continue
            total += 1
            _, hi = _split_grid_cell_u16_2(read_grid_cell_value(data, layout, x, y))
            if profile_by_coord.get((x, y)) == hi:
                matched += 1
    return matched, total


def find_rng_advance_for_save(
    save: LoadedSave,
    data: bytes,
    *,
    max_advance: int = 64,
) -> tuple[int, int, int]:
    """Brute-force RNG stream offset before ``0x43EBA3`` (per-save calibration)."""
    best = (0, -1)
    total = 0
    for advance in range(max_advance + 1):
        rng = rng_for_43eba3(data, advance=advance)
        predicted = apply_43eba3_profile_map(save, data, rng=rng)
        matched, total = score_43eba3_profile_map(save, data, predicted)
        if matched > best[1]:
            best = (advance, matched)
    return best[0], best[1], total


def _apply_pass2_neighbor_and_anchor_stamps(
    save: LoadedSave,
    data: bytes,
    layout: SaveLayout,
    profile_by_coord: dict[tuple[int, int], int],
    rng: DeadlockRng,
) -> None:
    """Pass 2 inside ``0x0043EBA3``: RNG neighbor ``hi=5→4`` then anchor ``hi=3``."""
    width = layout.width
    height = layout.height

    for territory in sorted(save.territories, key=lambda t: t.index):
        if territory.terrain_subtype == TERRAIN_SUBTYPE_OCEAN:
            continue
        anchor_idx = _anchor_cell_index(data, layout, territory)
        if anchor_idx is None or anchor_idx >= len(territory.cells):
            continue
        ax, ay = territory.cells[anchor_idx]

        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nx, ny = ax + dx, ay + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                threshold = _pass2_neighbor_threshold(dx, dy)
                if threshold is None:
                    continue
                if rng.next() % 100 >= threshold:
                    continue
                if profile_by_coord.get((nx, ny)) == 5:
                    profile_by_coord[(nx, ny)] = 4

        if save.grid[ay][ax] == territory.territory_id:
            profile_by_coord[(ax, ay)] = 3


def apply_43eba3_profile_map(
    save: LoadedSave,
    data: bytes,
    *,
    rng: DeadlockRng | None = None,
) -> dict[tuple[int, int], int]:
    """Simulate both passes of ``0x0043EBA3`` on outline cells."""
    layout = save.layout
    if rng is None:
        rng = rng_for_43eba3(data)

    profile_by_coord: dict[tuple[int, int], int] = {}

    for territory, x, y in iter_43eba3_pass1_cells(save, data):
        profile_by_coord[(x, y)] = profile_high_from_43eba3(
            territory.terrain_subtype,
            rng,
        )

    _apply_pass2_neighbor_and_anchor_stamps(save, data, layout, profile_by_coord, rng)

    return profile_by_coord


@dataclass(frozen=True)
class TypeTableEntry:
    index: int
    byte0: int
    byte1: int
    byte3: int


@lru_cache(maxsize=1)
def load_type_table() -> list[TypeTableEntry]:
    if not TABLES_JSON.exists():
        raise FileNotFoundError(
            f"Missing {TABLES_JSON}; run tools/extract_world_gen_tables.py first"
        )
    raw = json.loads(TABLES_JSON.read_text(encoding="utf-8"))
    return [
        TypeTableEntry(
            index=e["index"],
            byte0=e["byte0"],
            byte1=e["byte1"],
            byte3=e["byte3"],
        )
        for e in raw["type_table"]["entries"]
    ]


def type_table_byte(entry_index: int, offset: int) -> int:
    """Read byte at ``entry_index * stride + offset`` in the type table."""
    table = load_type_table()
    if not 0 <= entry_index < len(table):
        return 0
    entry = table[entry_index]
    if offset == 0:
        return entry.byte0 & 0xFF
    if offset == 1:
        return entry.byte1 & 0xFF
    if offset == 3:
        return entry.byte3 & 0xFF
    return 0


def autotile_high_for_subtype(subtype: int, *, rng: DeadlockRng | None = None) -> int:
    """Deterministic default or ``0x0043EBA3`` RNG-backed profile byte."""
    if rng is None:
        if subtype == TERRAIN_SUBTYPE_MOUNTAINS:
            return 5
        if subtype == TERRAIN_SUBTYPE_SWAMP:
            return 1
        if subtype == TERRAIN_SUBTYPE_FOREST:
            return 2
        if subtype == TERRAIN_SUBTYPE_PLAINS:
            return 3
        return 0
    return profile_high_from_43eba3(subtype, rng)


def encode_cell_u16_2(
    exposure: int,
    profile_high: int,
    *,
    x: int = 0,
    y: int = 0,
    width: int = 1,
    height: int = 1,
    use_catalog: bool = False,
) -> int:
    """Pack grid u16[2] at ``+4``.

    Fresh world-gen saves store the raw ``0x438960`` exposure byte as the low
    byte on ~90% of cells. Catalog lookup is only needed for legacy ocean
    remaps and editor repaints.
    """
    if not use_catalog:
        return _pack_grid_cell_u16_2(exposure & 0xFF, profile_high & 0xFF)
    catalog = DEFAULT_WORLD_MAP_EXPOSURE_CATALOG.get(profile_high & 0xFF, {})
    interior_default = _pack_grid_cell_u16_2(0, profile_high)
    return _pick_terrain_tile_for_exposure(
        x,
        y,
        exposure,
        catalog,
        width=width,
        height=height,
        interior_default=interior_default,
    )


def profile_high_for_territory(
    territory: TerritoryInfo,
    *,
    observed_hi: int | None = None,
) -> int:
    if observed_hi is not None:
        return observed_hi & 0xFF
    return autotile_high_for_subtype(territory.terrain_subtype)


def observed_profile_high_by_territory(
    data: bytes,
    layout: SaveLayout,
    grid: list[list[int]],
    territory: TerritoryInfo,
) -> int:
    """Most common ``+5`` high byte on cells belonging to this territory."""
    counts: Counter[int] = Counter()
    for x, y in territory.cells:
        if grid[y][x] != territory.territory_id:
            continue
        _, hi = _split_grid_cell_u16_2(read_grid_cell_value(data, layout, x, y))
        counts[hi] += 1
    if not counts:
        return autotile_high_for_subtype(territory.terrain_subtype)
    return counts.most_common(1)[0][0]


def build_profile_high_map(
    save: LoadedSave,
    data: bytes,
    *,
    rng_offset: int = 0,
    skip_if_hi_is_4: bool = False,
    use_legacy_bruteforce: bool = False,
) -> dict[tuple[int, int], int]:
    """Simulate ``0x0043EBA3`` per-cell profile bytes for a loaded save."""
    if not use_legacy_bruteforce and not skip_if_hi_is_4:
        rng = rng_for_43eba3(data, advance=rng_offset)
        return apply_43eba3_profile_map(save, data, rng=rng)

    layout = save.layout
    seed = read_world_seed_from_save(data) if use_legacy_bruteforce else read_world_seed2_from_save(data)
    rng = DeadlockRng.from_header_seed(seed)
    for _ in range(rng_offset):
        rng.next()

    profile_by_coord: dict[tuple[int, int], int] = {}
    for territory in save.territories:
        if territory.terrain_subtype > 4:
            continue
        for x, y in territory.cells:
            if save.grid[y][x] != territory.territory_id:
                continue
            existing_hi = 0
            if skip_if_hi_is_4:
                _, existing_hi = _split_grid_cell_u16_2(
                    read_grid_cell_value(data, layout, x, y)
                )
            hi = profile_high_from_43eba3(
                territory.terrain_subtype,
                rng,
                existing_hi=existing_hi,
                skip_if_hi_is_4=skip_if_hi_is_4,
            )
            profile_by_coord[(x, y)] = hi
    return profile_by_coord


def outline_cell_word(
    x: int,
    y: int,
    grid: list[list[int]],
    territory: TerritoryInfo,
    layout: SaveLayout,
    *,
    profile_high: int | None = None,
) -> int:
    """Encode one grid cell using exposure + profile high byte."""
    exposure = _neighbor_exposure(
        x, y, grid, territory.territory_id, layout.width, layout.height
    )
    high = profile_high_for_territory(
        territory,
        observed_hi=profile_high,
    )
    return encode_cell_u16_2(
        exposure,
        high,
        x=x,
        y=y,
        width=layout.width,
        height=layout.height,
    )


def outline_coords_for_save(save: LoadedSave) -> set[tuple[int, int]]:
    coords: set[tuple[int, int]] = set()
    for territory in save.territories:
        coords.update(territory.cells)
    return coords


def grid_cells_for_territory_ids(
    grid: list[list[int]],
    territory_ids: set[int],
) -> set[tuple[int, int]]:
    """Every strategic cell owned by one of the given territory IDs."""
    return {
        (x, y)
        for y, row in enumerate(grid)
        for x, value in enumerate(row)
        if value in territory_ids
    }


def profile_high_for_cell(
    x: int,
    y: int,
    territory: TerritoryInfo,
    *,
    exposure: int,
    profile_map: dict[tuple[int, int], int],
) -> int:
    """Pick grid ``+0x05`` for one cell during editor regen.

    Outline cells use the ``0x0043EBA3`` map (RNG-backed edge profiles). Interior
    cells (``exposure == 0``) get the deterministic subtype default because the
    game only rewrites outline ``+0x05`` on load; ``0x0043E296`` still reads
    interior bytes when rebuilding ``0x4DD87C``.
    """
    if (x, y) in profile_map:
        return profile_map[(x, y)]
    if exposure == 0:
        return autotile_high_for_subtype(territory.terrain_subtype)
    return autotile_high_for_subtype(territory.terrain_subtype)


def write_outline_grid_terrain(
    data: bytearray,
    save: LoadedSave,
    *,
    rng_advance: int | None = None,
    cells: set[tuple[int, int]] | None = None,
    calibrate_rng: bool = False,
    only_territory_ids: set[int] | None = None,
    full_territory: bool = False,
) -> int:
    """Write grid u16[2] using ``0x438960`` exposure + ``0x43EBA3`` profiles.

    By default only outline-list cells are updated (matching ``0x0043EBA3``).
    With ``full_territory=True``, every owned cell in ``only_territory_ids`` is
    rewritten so sub-type edits reach interior ``+0x05`` bytes that the game
    preserves across save load.

    Returns the RNG advance value used for profile assignment.
    """
    source = bytes(data)
    if calibrate_rng and rng_advance is None:
        rng_advance, _, _ = find_rng_advance_for_save(save, source)
    if rng_advance is None:
        rng_advance = 0

    profile_map = build_profile_high_map(save, source, rng_offset=rng_advance)
    subtype_by_id = {t.territory_id: t for t in save.territories}
    layout = save.layout
    grid = save.grid

    if cells is not None:
        target = cells
    elif full_territory and only_territory_ids is not None:
        target = grid_cells_for_territory_ids(grid, only_territory_ids)
    else:
        target = outline_coords_for_save(save)
        if only_territory_ids is not None:
            target = {
                (x, y)
                for x, y in target
                if grid[y][x] in only_territory_ids
            }

    for x, y in sorted(target, key=lambda coord: (coord[1], coord[0])):
        tid = grid[y][x]
        if tid <= 0:
            continue
        territory = subtype_by_id.get(tid)
        if territory is None:
            continue
        exposure = _neighbor_exposure(
            x, y, grid, tid, layout.width, layout.height
        )
        hi = profile_high_for_cell(
            x,
            y,
            territory,
            exposure=exposure,
            profile_map=profile_map,
        )
        word = encode_cell_u16_2(exposure, hi)
        write_grid_cell_value(data, layout, x, y, word)

    return rng_advance


def strategic_template_bytes(type_index: int) -> tuple[int, int]:
    """Return ``(+4 type index, +5 table byte)`` like ``0x004290EB``."""
    table = load_type_table()
    if not 0 <= type_index < len(table):
        return type_index & 0xFF, 0
    entry = table[type_index]
    return type_index & 0xFF, entry.byte0 & 0xFF


def compare_save_grid(
    save_path: Path,
    *,
    outline_only: bool = True,
    use_observed_profile: bool = False,
    use_43eba3_rng: bool = False,
    rng_offset: int = 0,
    skip_if_hi_is_4: bool = False,
) -> dict[str, int | float]:
    """Compare heuristic encoding against an on-disk save grid."""
    save = LoadedSave.from_path(save_path)
    data = save_path.read_bytes()
    layout = save.layout
    grid = save.grid

    outline_coords: set[tuple[int, int]] = set()
    subtype_by_id = {t.territory_id: t for t in save.territories}
    profile_by_id: dict[int, int] = {}
    profile_by_coord: dict[tuple[int, int], int] = {}
    if use_43eba3_rng:
        profile_by_coord = build_profile_high_map(
            save,
            data,
            rng_offset=rng_offset,
            skip_if_hi_is_4=skip_if_hi_is_4,
        )
    elif use_observed_profile:
        for territory in save.territories:
            profile_by_id[territory.territory_id] = observed_profile_high_by_territory(
                data, layout, grid, territory
            )
    for territory in save.territories:
        outline_coords.update(territory.cells)

    total = 0
    exact = 0
    exposure_match = 0
    profile_match = 0
    low_match = 0

    for y in range(layout.height):
        for x in range(layout.width):
            tid = grid[y][x]
            if tid <= 0:
                continue
            if outline_only and (x, y) not in outline_coords:
                continue
            territory = subtype_by_id.get(tid)
            if territory is None:
                continue

            actual = read_grid_cell_value(data, layout, x, y)
            lo, hi = _split_grid_cell_u16_2(actual)
            if use_43eba3_rng:
                cell_profile = profile_by_coord.get((x, y))
            elif use_observed_profile:
                cell_profile = profile_by_id.get(tid)
            else:
                cell_profile = None
            predicted = outline_cell_word(
                x,
                y,
                grid,
                territory,
                layout,
                profile_high=cell_profile,
            )
            p_lo, p_hi = _split_grid_cell_u16_2(predicted)

            exposure = _neighbor_exposure(
                x, y, grid, tid, layout.width, layout.height
            )
            total += 1
            if actual == predicted:
                exact += 1
            if lo == (exposure & 0xFF) or lo == p_lo:
                exposure_match += 1
            if hi == p_hi:
                profile_match += 1
            if lo == p_lo:
                low_match += 1

    def pct(n: int) -> float:
        return (100.0 * n / total) if total else 0.0

    return {
        "cells": total,
        "exact_word": exact,
        "exact_pct": pct(exact),
        "profile_hi_match": profile_match,
        "profile_hi_pct": pct(profile_match),
        "predicted_lo_match": low_match,
        "predicted_lo_pct": pct(low_match),
        "raw_or_predicted_lo": exposure_match,
        "raw_or_predicted_lo_pct": pct(exposure_match),
    }


def dump_mismatch_samples(save_path: Path, limit: int = 8) -> list[str]:
    save = LoadedSave.from_path(save_path)
    data = save_path.read_bytes()
    layout = save.layout
    grid = save.grid
    subtype_by_id = {t.territory_id: t for t in save.territories}
    outline_coords: set[tuple[int, int]] = set()
    for territory in save.territories:
        outline_coords.update(territory.cells)

    profile_by_id = {
        t.territory_id: observed_profile_high_by_territory(data, layout, grid, t)
        for t in save.territories
    }

    lines: list[str] = []
    for y in range(layout.height):
        for x in range(layout.width):
            if (x, y) not in outline_coords:
                continue
            tid = grid[y][x]
            territory = subtype_by_id.get(tid)
            if territory is None:
                continue
            actual = read_grid_cell_value(data, layout, x, y)
            predicted = outline_cell_word(
                x,
                y,
                grid,
                territory,
                layout,
                profile_high=profile_by_id.get(tid),
            )
            if actual == predicted:
                continue
            lo, hi = _split_grid_cell_u16_2(actual)
            p_lo, p_hi = _split_grid_cell_u16_2(predicted)
            exposure = _neighbor_exposure(
                x, y, grid, tid, layout.width, layout.height
            )
            lines.append(
                f"({x:2d},{y:2d}) tid={tid:3d} sub={territory.terrain_subtype} "
                f"exp={exposure:#04x} actual={actual:#06x}({lo:#04x},{hi}) "
                f"pred={predicted:#06x}({p_lo:#04x},{p_hi})"
            )
            if len(lines) >= limit:
                return lines
    return lines
