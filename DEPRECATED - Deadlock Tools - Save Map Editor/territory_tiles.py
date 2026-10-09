"""Read and write colony tile tables inside Deadlock territory records."""
from __future__ import annotations

import struct
import sys
from dataclasses import dataclass
from pathlib import Path

from terrain_catalog import (
    WATER_TERRAIN,
    YIELD_NAMES,
    DecodedTerrain,
    bonus_label,
    combine_terrain,
    format_yield,
    preset_base,
    split_terrain,
)

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_DIR = ROOT / "DEPRECATED - Deadlock Tools - Territory Boundary Editor"
if not getattr(sys, "frozen", False) and BOUNDARY_DIR.is_dir():
    boundary_path = str(BOUNDARY_DIR)
    if boundary_path not in sys.path:
        sys.path.insert(0, boundary_path)

from deadlock_territory_save import (  # noqa: E402
    LoadedSave,
    STORED_RECORD,
    TerritoryInfo,
    load_save,
)

TILE_TABLE_OFF = 0x140
TILE_ROW_SIZE = 0x20
MAX_TILE_ROWS = 36
GRID_SIZE = 6


@dataclass
class ColonyTile:
    row: int
    col: int
    terrain: int
    bonus: int
    yields: tuple[int, int, int, int, int]
    tail: bytes = b"\x00" * 16

    @property
    def slot(self) -> int:
        return self.row * 256 + self.col

    @property
    def decoded_terrain(self) -> DecodedTerrain:
        return split_terrain(self.terrain)

    def with_base_terrain(self, base: int, *, keep_flags: bool = True) -> ColonyTile:
        flags = self.decoded_terrain.flags if keep_flags else 0
        if base == WATER_TERRAIN:
            flags = 0
        return ColonyTile(
            row=self.row,
            col=self.col,
            terrain=combine_terrain(base, flags),
            bonus=self.bonus,
            yields=self.yields,
            tail=self.tail,
        )

    def with_bonus(self, bonus: int) -> ColonyTile:
        return ColonyTile(self.row, self.col, self.terrain, bonus, self.yields, self.tail)

    def with_yields(self, yields: tuple[int, int, int, int, int]) -> ColonyTile:
        return ColonyTile(self.row, self.col, self.terrain, self.bonus, yields, self.tail)


def record_offset(layout_territory_offset: int, territory_index: int) -> int:
    return layout_territory_offset + (territory_index - 1) * STORED_RECORD


def _empty_row_bytes() -> bytes:
    return b"\x00" * TILE_ROW_SIZE


def _encode_row(tile: ColonyTile) -> bytes:
    if not (0 <= tile.row < GRID_SIZE and 0 <= tile.col < GRID_SIZE):
        raise ValueError(f"Tile out of 6x6 range: ({tile.row}, {tile.col})")
    words = (
        tile.slot,
        tile.terrain & 0xFFFF,
        tile.bonus & 0xFFFF,
        *tile.yields,
    )
    if len(words) != 8:
        raise ValueError("Expected five yield values")
    tail = tile.tail if len(tile.tail) == 16 else b"\x00" * 16
    return struct.pack("<8H", *words) + tail


def _decode_row(raw: bytes) -> ColonyTile | None:
    if len(raw) < TILE_ROW_SIZE:
        return None
    slot, terrain, bonus, y0, y1, y2, y3, y4 = struct.unpack("<8H", raw[:16])
    if slot == 0 and terrain == 0 and bonus == 0 and not any((y0, y1, y2, y3, y4)):
        return None
    row, col = slot // 256, slot % 256
    return ColonyTile(row, col, terrain, bonus, (y0, y1, y2, y3, y4), raw[16:TILE_ROW_SIZE])


def read_territory_tiles(data: bytes, record_off: int) -> list[ColonyTile]:
    base = record_off + TILE_TABLE_OFF
    tiles: list[ColonyTile] = []
    for index in range(MAX_TILE_ROWS):
        off = base + index * TILE_ROW_SIZE
        if off + TILE_ROW_SIZE > len(data):
            break
        tile = _decode_row(data[off : off + TILE_ROW_SIZE])
        if tile is None:
            if tiles:
                break
            continue
        tiles.append(tile)
    return tiles


def write_territory_tiles(data: bytearray, record_off: int, tiles: list[ColonyTile]) -> None:
    if len(tiles) > MAX_TILE_ROWS:
        raise ValueError(f"At most {MAX_TILE_ROWS} tile rows are stored per territory")
    seen = {(t.row, t.col) for t in tiles}
    if len(seen) != len(tiles):
        raise ValueError("Duplicate tile coordinates in write list")

    base = record_off + TILE_TABLE_OFF
    encoded = [_encode_row(tile) for tile in tiles]
    for index in range(MAX_TILE_ROWS):
        off = base + index * TILE_ROW_SIZE
        chunk = encoded[index] if index < len(encoded) else _empty_row_bytes()
        data[off : off + TILE_ROW_SIZE] = chunk


def territory_record_offset(save: LoadedSave, territory: TerritoryInfo) -> int:
    return record_offset(save.layout.territory_offset, territory.index)


def read_tiles_for_territory(save: LoadedSave, territory: TerritoryInfo) -> list[ColonyTile]:
    return read_territory_tiles(save.data, territory_record_offset(save, territory))


def write_tiles_for_territory(
    data: bytearray,
    save_layout_territory_offset: int,
    territory: TerritoryInfo,
    tiles: list[ColonyTile],
) -> None:
    write_territory_tiles(data, record_offset(save_layout_territory_offset, territory.index), tiles)


def find_territory(save: LoadedSave, name: str) -> TerritoryInfo:
    for territory in save.territories:
        if territory.name == name:
            return territory
    raise KeyError(f"Territory not found: {name!r}")


def apply_base_preset(
    tiles: list[ColonyTile],
    preset: str,
    *,
    keep_flags: bool = False,
    keep_bonus: bool = True,
    keep_yields: bool = True,
) -> list[ColonyTile]:
    base = preset_base(preset)
    result: list[ColonyTile] = []
    for tile in tiles:
        updated = tile.with_base_terrain(base, keep_flags=keep_flags)
        if not keep_bonus:
            updated = updated.with_bonus(0)
        if not keep_yields and base == WATER_TERRAIN:
            updated = updated.with_yields((500, 2250, 750, 750, 125))
        result.append(updated)
    return result


def grid_from_tiles(tiles: list[ColonyTile]) -> list[list[ColonyTile | None]]:
    grid: list[list[ColonyTile | None]] = [[None] * GRID_SIZE for _ in range(GRID_SIZE)]
    for tile in tiles:
        if 0 <= tile.row < GRID_SIZE and 0 <= tile.col < GRID_SIZE:
            grid[tile.row][tile.col] = tile
    return grid


def format_tile_report(territory_name: str, tiles: list[ColonyTile]) -> str:
    lines = [f"{territory_name} ({len(tiles)} tile rows)", ""]
    if not tiles:
        lines.append("  (no colony tile table — territory may be uncolonized or water-only)")
        return "\n".join(lines)

    counts: dict[int, int] = {}
    for tile in tiles:
        counts[tile.terrain] = counts.get(tile.terrain, 0) + 1

    mix = ", ".join(
        f"{split_terrain(code).label}:{counts[code]}" for code in sorted(counts, key=lambda c: (split_terrain(c).base, c))
    )
    lines.append(f"Terrain mix: {mix}")
    lines.append("")
    for index, tile in enumerate(tiles):
        decoded = tile.decoded_terrain
        yields = "/".join(format_yield(value) for value in tile.yields)
        names = "/".join(YIELD_NAMES)
        lines.append(
            f"  [{index:2}] ({tile.row},{tile.col}) {decoded.label:24} "
            f"bonus={bonus_label(tile.bonus):22} {names}={yields}"
        )
    return "\n".join(lines)


def patch_territory_tiles(
    save_path: Path,
    territory_name: str,
    mutator,
    *,
    output_path: Path | None = None,
) -> Path:
    """Load a save, mutate one territory's tile list, and write bytes to disk."""
    save = LoadedSave.from_path(save_path)
    territory = find_territory(save, territory_name)
    tiles = read_tiles_for_territory(save, territory)
    new_tiles = mutator(list(tiles))
    patched = bytearray(save.data)
    write_tiles_for_territory(patched, save.layout.territory_offset, territory, new_tiles)
    dest = output_path or save_path
    dest.write_bytes(patched)
    return dest


def load_save_path(path: Path) -> LoadedSave:
    return LoadedSave.from_path(path)


def read_save_bytes(path: Path) -> bytes:
    return load_save(path)


def save_tile_tables(
    data: bytes,
    save: LoadedSave,
    tile_cache: dict[int, list[ColonyTile]],
) -> bytes:
    """Return save bytes with updated colony tile tables for cached territories."""
    patched = bytearray(data)
    for territory in save.territories:
        tiles = tile_cache.get(territory.territory_id)
        if tiles:
            write_tiles_for_territory(
                patched,
                save.layout.territory_offset,
                territory,
                tiles,
            )
    return bytes(patched)
