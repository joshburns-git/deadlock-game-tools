"""Parse and patch territory boundaries in Deadlock .SAV files."""
from __future__ import annotations

import struct
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

STORED_RECORD = 0x5D8
NAME_OFF = 0x0
OUTLINE_COUNT_OFF = 0x7E
OUTLINE_DATA_OFF = 0x80
BORDER_BYTE_OFF = 0x68
MAX_INLINE_BORDER_BYTES = OUTLINE_COUNT_OFF - BORDER_BYTE_OFF
STABLE_ID_OFF = 0x1A
OWNER_OFF = 0x20
TERRAIN_SUBTYPE_OFF = 0x21
TERRAIN_KIND_OFF = 0x22
INTERIOR_BORDER_FLAG = 0x7FFF

TERRAIN_KIND_LAND = 0
TERRAIN_KIND_WATER = 1
TERRAIN_KIND_SWAMP = 2
TERRAIN_KIND_UNSET = 255

TERRAIN_KIND_LABELS = {
    TERRAIN_KIND_LAND: "Land",
    TERRAIN_KIND_WATER: "Ocean",
    TERRAIN_KIND_SWAMP: "Swamp",
}

TERRAIN_SUBTYPE_PLAINS = 1
TERRAIN_SUBTYPE_FOREST = 2
TERRAIN_SUBTYPE_SWAMP = 3
TERRAIN_SUBTYPE_MOUNTAINS = 4

TERRAIN_SUBTYPE_LABELS: dict[int, str] = {
    TERRAIN_SUBTYPE_PLAINS: "Plains",
    TERRAIN_SUBTYPE_FOREST: "Forest",
    TERRAIN_SUBTYPE_SWAMP: "Swamp",
    TERRAIN_SUBTYPE_MOUNTAINS: "Mountains",
}

TERRAIN_SUBTYPE_CHOICES: list[tuple[int, str]] = list(TERRAIN_SUBTYPE_LABELS.items())

# Record bytes at +0x21/+0x22 are territory type/subtype. Grid cell u16[2] at +0x04
# is packed: low byte = neighbor-exposure bitmask (0x438960), high byte = autotile
# variant (0x43EBA3). Not colony tile terrain (+0x140).
EXPOSURE_N = 0x01
EXPOSURE_W = 0x02
EXPOSURE_S = 0x04
EXPOSURE_E = 0x08
EXPOSURE_NW = 0x10
EXPOSURE_NE = 0x20
EXPOSURE_SW = 0x40
EXPOSURE_SE = 0x80
EXPOSURE_CARDINAL = EXPOSURE_N | EXPOSURE_W | EXPOSURE_S | EXPOSURE_E
TERRAIN_KIND_RECORD_BYTES: dict[int, tuple[int, int]] = {
    TERRAIN_KIND_LAND: (1, TERRAIN_KIND_LAND),
    TERRAIN_KIND_WATER: (0, TERRAIN_KIND_WATER),
    TERRAIN_KIND_SWAMP: (3, TERRAIN_KIND_SWAMP),
}
TERRAIN_KIND_GRID_U16_2: dict[int, int] = {
    TERRAIN_KIND_LAND: 768,
    TERRAIN_KIND_WATER: 0,
    TERRAIN_KIND_SWAMP: 256,
}

GRID_CELL_BYTES = 10
GRID_CELL_VALUE_OFF = 4

UNOWNED_OWNER = 255
LANDING_SUFFIX = " Landing"
SECTION2_OFF = 0x7A
SECTION2_SIZE = 0x6A
SECTION3_SIZE = 0x14
PLAYER_SLOT_SIZE = 0x25E
PLAYER_TABLE_OFF = SECTION2_OFF + SECTION2_SIZE + SECTION3_SIZE
PLAYER_CREDITS_OFF = 0xC
TERRITORY_POPULATION_OFF = 0x30
TERRITORY_POPULATION_DUP_OFF = 0x38
MAX_RESOURCE_QUANTITY = 10_000
MAX_PLAYER_CREDITS = 10_000
MAX_NAME_LEN = STABLE_ID_OFF - NAME_OFF - 1  # null-terminated field before +0x1A
# Outline (x, y) pairs at record+0x80 share the record with other fields that
# start around +0x142. More than 48 cells can overwrite that tail and crash on load.
MAX_TERRITORY_CELLS = 48
MIN_TERRITORY_WIDTH = 4
MIN_TERRITORY_HEIGHT = 3


def outline_sort_key(cell: tuple[int, int]) -> tuple[int, int]:
    """Row-major sort key (y then x)."""
    x, y = cell
    return y, x


def sort_outline_cells(cells: list[tuple[int, int]]) -> list[tuple[int, int]]:
    cells.sort(key=outline_sort_key)
    return cells


def _outline_neighbors(cell: tuple[int, int]) -> list[tuple[int, int]]:
    x, y = cell
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def _outline_adjacent(a: tuple[int, int], b: tuple[int, int]) -> bool:
    ax, ay = a
    bx, by = b
    return abs(ax - bx) + abs(ay - by) == 1


def _outline_connected_components(
    cells: list[tuple[int, int]],
) -> list[list[tuple[int, int]]]:
    """Split cells into edge-adjacent connected groups."""
    remaining = set(cells)
    components: list[list[tuple[int, int]]] = []
    while remaining:
        start = min(remaining, key=outline_sort_key)
        group: list[tuple[int, int]] = []
        stack = [start]
        remaining.remove(start)
        while stack:
            current = stack.pop()
            group.append(current)
            for neighbor in _outline_neighbors(current):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
        components.append(sort_outline_cells(group))
    return components


def _count_outline_breaks(
    cells: list[tuple[int, int]],
    *,
    focus: set[tuple[int, int]] | None = None,
) -> int:
    """Count consecutive outline pairs that are not edge-adjacent."""
    breaks = 0
    for index in range(len(cells) - 1):
        left, right = cells[index], cells[index + 1]
        if _outline_adjacent(left, right):
            continue
        if focus is None or left in focus or right in focus:
            breaks += 1
    return breaks


def _splice_component_into_outline(
    merged: list[tuple[int, int]],
    component: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Insert a connected group of new cells as one adjacent sub-chain."""
    if not component:
        return merged
    if len(component) == 1:
        return _insert_outline_cell_adjacent(merged, component[0])

    chain = reorder_outline_as_chain(component)
    component_set = set(component)
    best: list[tuple[int, int]] | None = None
    best_score: tuple[int, int] | None = None

    for orientation in (chain, list(reversed(chain))):
        for index in range(len(merged)):
            if not _outline_adjacent(merged[index], orientation[0]):
                continue
            next_index = index + 1
            if next_index < len(merged):
                if not _outline_adjacent(orientation[-1], merged[next_index]):
                    continue
            candidate = merged[: index + 1] + orientation + merged[next_index:]
            score = (
                _count_outline_breaks(candidate, focus=component_set),
                _count_outline_breaks(candidate),
            )
            if best_score is None or score < best_score:
                best_score = score
                best = candidate

    if best is not None:
        return best

    result = merged
    for cell in sorted(component, key=outline_sort_key):
        result = _insert_outline_cell_adjacent(result, cell)
    return result


def _merge_outline_additions(
    kept: list[tuple[int, int]],
    added: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Insert newly added cells while keeping local outline segments adjacent."""
    if not added:
        return kept

    merged = kept[:]
    for component in sorted(
        _outline_connected_components(added),
        key=lambda group: outline_sort_key(group[0]),
    ):
        merged = _splice_component_into_outline(merged, component)
    return merged


def _insert_outline_cell_adjacent(
    cells: list[tuple[int, int]],
    cell: tuple[int, int],
) -> list[tuple[int, int]]:
    """Insert a cell next to an existing neighbor in the outline chain.

    Deadlock's outline list is not a strict Hamiltonian path: consecutive
    entries can jump (e.g. (10, 9) -> (6, 10)). When extending a territory,
    new cells must be spliced immediately after an adjacent neighbor so the
    border renderer walks them in the right place. Appending at the tail leaves
    the new cells in a disconnected chain fragment and etched borders stay put.

    Prefer splices that keep any existing adjacent link between the neighbor
    and the following cell intact; otherwise prefer straight (same row/column)
    attachments and earlier outline positions.
    """
    cx, cy = cell
    candidates: list[tuple[bool, bool, int]] = []
    for index, existing in enumerate(cells):
        if not _outline_adjacent(existing, cell):
            continue
        ex, ey = existing
        next_cell = cells[index + 1] if index + 1 < len(cells) else None
        breaks_chain = bool(
            next_cell is not None
            and _outline_adjacent(existing, next_cell)
            and not _outline_adjacent(cell, next_cell)
        )
        straight = ex == cx or ey == cy
        candidates.append((breaks_chain, not straight, index))

    if not candidates:
        return cells + [cell]

    _, _, index = min(candidates)
    return cells[: index + 1] + [cell] + cells[index + 1 :]


def reorder_outline_as_chain(cells: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Build an outline path where consecutive cells share an edge when possible."""
    if len(cells) <= 1:
        return list(cells)

    remaining = set(cells)
    ordered: list[tuple[int, int]] = []
    current = min(remaining, key=outline_sort_key)
    ordered.append(current)
    remaining.remove(current)

    while remaining:
        neighbors = [n for n in _outline_neighbors(current) if n in remaining]
        if neighbors:
            current = min(neighbors, key=outline_sort_key)
        else:
            current = min(remaining, key=outline_sort_key)
        ordered.append(current)
        remaining.remove(current)
    return ordered


def outline_cells_for_grid(
    old_cells: list[tuple[int, int]],
    new_cells: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Merge grid cells into an outline list suitable for border rendering.

    Deadlock draws territory borders by connecting consecutive cells in the
    outline list at ``name+0x80``. New cells must be inserted beside an existing
    neighbor in that list; resorting the full list breaks the border polyline.
    """
    new_set = set(new_cells)
    old_set = set(old_cells)
    if old_set == new_set:
        return old_cells
    if not old_cells:
        return reorder_outline_as_chain(list(new_cells))

    kept = [cell for cell in old_cells if cell in new_set]
    added = [cell for cell in new_cells if cell not in old_set]
    removed = len(old_cells) - len(kept)
    if not kept:
        return reorder_outline_as_chain(list(new_cells))

    # Large reshapes can break the old chain; rebuild from scratch.
    if removed + len(added) > max(4, len(old_cells) // 4):
        return reorder_outline_as_chain(list(new_cells))

    return _merge_outline_additions(kept, added)

# 91 single-character symbols (enough for large maps).
# Letters first so map rows like "00 AAB..." stay easy to read.
SYMBOL_ALPHABET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789"
    "!@#$%^&*+=?~[]{}()_:;,.<>/|\\"
)


@dataclass
class SaveLayout:
    width: int
    height: int
    territory_count: int
    grid_offset: int
    section8_offset: int
    territory_offset: int
    building_count: int
    army_count: int


@dataclass
class TerritoryStockpile:
    food: int = 0
    energy: int = 0
    wood: int = 0
    iron: int = 0
    steel: int = 0
    endurium: int = 0
    triidium: int = 0
    electronics: int = 0
    anti_matter: int = 0
    art: int = 0


STOCKPILE_FIELDS: tuple[tuple[str, int], ...] = (
    ("food", 0x3E),
    ("energy", 0x42),
    ("wood", 0x46),
    ("iron", 0x4A),
    ("steel", 0x4E),
    ("endurium", 0x52),
    ("triidium", 0x56),
    ("electronics", 0x5A),
    ("anti_matter", 0x5E),
    ("art", 0x62),
)

# u16 padding after each stockpile value (+0x40, +0x44, …, +0x64); keep zero on save.
STOCKPILE_PADDING_OFFSETS: tuple[int, ...] = tuple(
    offset + 2 for _name, offset in STOCKPILE_FIELDS
)

STOCKPILE_LABELS: dict[str, str] = {
    "food": "Food",
    "energy": "Energy",
    "wood": "Wood",
    "iron": "Iron",
    "steel": "Steel",
    "endurium": "Endurium",
    "triidium": "Triidium",
    "electronics": "Electronics",
    "anti_matter": "Anti-Matter",
    "art": "Art",
}


@dataclass
class TerritoryInfo:
    index: int
    territory_id: int
    name: str
    owner: int
    terrain_kind: int = TERRAIN_KIND_LAND
    terrain_subtype: int = TERRAIN_SUBTYPE_PLAINS
    cells: list[tuple[int, int]] = field(default_factory=list)
    population: int = 0
    stockpile: TerritoryStockpile = field(default_factory=TerritoryStockpile)


def _read_header(data: bytes) -> tuple[int, int, int, int, int]:
    section2 = data[0x7A : 0x7A + 0x6A]
    blob = data[0x7A + 0x6A : 0x7A + 0x6A + 0x14]
    territory_count = struct.unpack_from("<H", blob, 8)[0]
    width = blob[10]
    height = blob[11]
    section4_count = struct.unpack_from("<I", section2, 12)[0]
    event_count = struct.unpack_from("<I", section2, 56)[0]
    return width, height, territory_count, section4_count, event_count


def _section6_end(data: bytes, section4_count: int) -> int:
    offset = 0x7A + 0x6A + 0x14
    offset += section4_count * 0x1092
    offset += 0x2F4 + 36 * 0x12
    return offset


def _section8_offset_from_events(data: bytes, section6_end: int, event_count: int) -> int:
    offset = section6_end
    for _ in range(event_count):
        text_len = struct.unpack_from("<H", data, offset + 2)[0]
        offset += 12 + text_len
    return offset


def _header_data_end(data: bytes) -> int:
    return 0x7A + 0x6A + 0x14


def _validate_grid_layout(
    data: bytes,
    grid_offset: int,
    width: int,
    height: int,
    territory_count: int,
) -> bool:
    """Confirm buildings/armies/territory block fit after a candidate grid."""
    after_grid = grid_offset + width * height * 10
    if after_grid + 4 > len(data):
        return False

    building_count = struct.unpack_from("<I", data, after_grid)[0]
    if building_count > 10_000:
        return False

    offset = after_grid + 4 + building_count * 0x114
    if offset + 4 > len(data):
        return False

    army_count = struct.unpack_from("<I", data, offset)[0]
    if army_count > 10_000:
        return False

    territory_offset = offset + 4 + army_count * 0x5C
    tail = territory_offset + territory_count * STORED_RECORD
    if tail > len(data):
        return False

    if territory_count <= 0:
        return True

    record = data[territory_offset : territory_offset + STORED_RECORD]
    name_end = record.find(b"\x00", NAME_OFF)
    if name_end <= NAME_OFF or name_end - NAME_OFF > MAX_NAME_LEN:
        return False
    name = record[NAME_OFF:name_end].decode("latin-1", errors="replace")
    return len(name) >= 2 and name[0].isprintable()


def _looks_like_territory_record(record: bytes) -> bool:
    """Heuristic for a single stored territory record."""
    if len(record) < STORED_RECORD:
        return False
    name_end = record.find(b"\x00", NAME_OFF)
    if name_end <= NAME_OFF or name_end - NAME_OFF > MAX_NAME_LEN:
        return False
    name = record[NAME_OFF:name_end]
    if len(name) < 2:
        return False
    label = name.decode("latin-1", errors="replace")
    if not label[0].isprintable():
        return False
    territory_id = struct.unpack_from("<H", record, NAME_OFF + STABLE_ID_OFF)[0]
    if territory_id <= 0 or territory_id > 1000:
        return False
    outline_count = record[NAME_OFF + OUTLINE_COUNT_OFF]
    if outline_count > MAX_TERRITORY_CELLS + 8:
        return False
    return True


def _territory_ids_from_block(data: bytes, territory_offset: int, territory_count: int) -> set[int]:
    ids: set[int] = set()
    for index in range(territory_count):
        rec_off = territory_offset + index * STORED_RECORD
        record = data[rec_off : rec_off + STORED_RECORD]
        territory_id = struct.unpack_from("<H", record, NAME_OFF + STABLE_ID_OFF)[0]
        if territory_id > 0:
            ids.add(territory_id)
    return ids


def _score_grid_candidate(
    data: bytes,
    grid_offset: int,
    width: int,
    height: int,
    territory_ids: set[int],
) -> int:
    """Count map cells whose stored territory id matches the record table."""
    if not territory_ids:
        return 0
    score = 0
    for y in range(height):
        row_base = grid_offset + y * width * GRID_CELL_BYTES
        for x in range(width):
            territory_id = struct.unpack_from("<H", data, row_base + x * GRID_CELL_BYTES + 2)[0]
            if territory_id in territory_ids:
                score += 1
    return score


def _find_territory_block(data: bytes, width: int, height: int, territory_count: int) -> int | None:
    """Locate the contiguous territory record table in a save."""
    if territory_count <= 0:
        return 0
    span = territory_count * STORED_RECORD
    if span > len(data):
        return None

    candidates: list[int] = []
    last_index = territory_count - 1
    for off in range(0, len(data) - span + 1):
        if not _looks_like_territory_record(data[off : off + STORED_RECORD]):
            continue
        last_off = off + last_index * STORED_RECORD
        if not _looks_like_territory_record(data[last_off : last_off + STORED_RECORD]):
            continue
        valid = True
        for index in range(1, territory_count - 1):
            rec_off = off + index * STORED_RECORD
            if not _looks_like_territory_record(data[rec_off : rec_off + STORED_RECORD]):
                valid = False
                break
        if valid:
            candidates.append(off)

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    for off in candidates:
        if _grid_offset_from_territory_block(data, off, width, height, territory_count) is not None:
            return off
    return candidates[0]


def _grid_offset_from_territory_block(
    data: bytes,
    territory_offset: int,
    width: int,
    height: int,
    territory_count: int,
) -> int | None:
    """Derive the world grid offset from a known territory record table."""
    cells = width * height
    grid_bytes = cells * GRID_CELL_BYTES
    max_armies = min(10_000, max(0, (territory_offset - grid_bytes - 8) // 0x5C))
    territory_ids = _territory_ids_from_block(data, territory_offset, territory_count)
    best_offset: int | None = None
    best_score = -1

    for army_count in range(max_armies + 1):
        army_count_off = territory_offset - army_count * 0x5C - 4
        if army_count_off < 4:
            break
        if struct.unpack_from("<I", data, army_count_off)[0] != army_count:
            continue

        max_buildings = min(
            10_000,
            max(0, (army_count_off - 4) // 0x114),
        )
        for building_count in range(max_buildings + 1):
            building_count_off = army_count_off - 4 - building_count * 0x114
            grid_end = building_count_off
            grid_offset = grid_end - grid_bytes
            if grid_offset < 0:
                continue
            if struct.unpack_from("<I", data, building_count_off)[0] != building_count:
                continue
            if not _validate_grid_layout(data, grid_offset, width, height, territory_count):
                continue
            if layout_territory_offset(data, grid_offset, width, height) != territory_offset:
                continue
            score = _score_grid_candidate(data, grid_offset, width, height, territory_ids)
            if score > best_score:
                best_score = score
                best_offset = grid_offset

    if best_offset is None or best_score <= 0:
        return None
    return best_offset


def layout_territory_offset(
    data: bytes,
    grid_offset: int,
    width: int,
    height: int,
) -> int:
    """Return the territory record table offset implied by a grid anchor."""
    after_grid = grid_offset + width * height * GRID_CELL_BYTES
    building_count = struct.unpack_from("<I", data, after_grid)[0]
    offset = after_grid + 4 + building_count * 0x114
    army_count = struct.unpack_from("<I", data, offset)[0]
    return offset + 4 + army_count * 0x5C


def _find_grid_offset_via_territory_block(
    data: bytes,
    width: int,
    height: int,
    territory_count: int,
) -> int | None:
    territory_offset = _find_territory_block(data, width, height, territory_count)
    if territory_offset is None:
        return None
    return _grid_offset_from_territory_block(
        data,
        territory_offset,
        width,
        height,
        territory_count,
    )


def _coord_encoded_grid_offset(
    data: bytes,
    width: int,
    height: int,
    start: int,
    limit: int,
    *,
    territory_count: int | None,
    seen: set[int],
) -> int | None:
    """Fast path: locate grid by per-cell coordinate stamp in u16[0]."""
    cells = width * height
    for offset in range(max(0, start), limit + 1, 2):
        if offset in seen:
            continue
        seen.add(offset)
        ok = 0
        for y in range(height):
            row_base = offset + y * width * GRID_CELL_BYTES
            for x in range(width):
                encoded = struct.unpack_from("<H", data, row_base + x * GRID_CELL_BYTES)[0]
                if encoded == y * 256 + x:
                    ok += 1
        if ok != cells:
            continue
        if territory_count is not None and not _validate_grid_layout(
            data, offset, width, height, territory_count
        ):
            continue
        return offset
    return None


def find_grid_offset(
    data: bytes,
    width: int,
    height: int,
    start: int = 0,
    *,
    territory_count: int | None = None,
) -> int:
    cells = width * height
    need = cells * GRID_CELL_BYTES
    limit = len(data) - need
    header_end = _header_data_end(data)

    ranges: list[tuple[int, int]] = [(max(0, start), limit)]
    # Mid-game autosaves can grow section4 while the world grid stays at the
    # earlier anchor, so section6_end overshoots the real grid offset.
    if start > header_end:
        ranges.append((header_end, min(limit, start)))

    if territory_count is not None:
        found = _find_grid_offset_via_territory_block(data, width, height, territory_count)
        if found is not None:
            return found

    seen: set[int] = set()
    for range_start, range_end in ranges:
        found = _coord_encoded_grid_offset(
            data,
            width,
            height,
            range_start,
            range_end,
            territory_count=territory_count,
            seen=seen,
        )
        if found is not None:
            return found

    raise ValueError("Could not locate world grid in save file")


def parse_layout(data: bytes) -> SaveLayout:
    width, height, territory_count, section4_count, event_count = _read_header(data)
    section6_end = _section6_end(data, section4_count)
    grid_offset = find_grid_offset(
        data,
        width,
        height,
        section6_end,
        territory_count=territory_count,
    )
    section8_offset = _section8_offset_from_events(data, section6_end, event_count)

    offset = grid_offset + width * height * 10
    building_count = struct.unpack_from("<I", data, offset)[0]
    offset += 4 + building_count * 0x114
    army_count = struct.unpack_from("<I", data, offset)[0]
    offset += 4 + army_count * 0x5C
    territory_offset = offset

    tail = offset + territory_count * STORED_RECORD
    if tail > len(data):
        raise ValueError(
            f"Save layout parse failed: territory block overruns file "
            f"(expected end at 0x{tail:X}, file size 0x{len(data):X})"
        )

    return SaveLayout(
        width=width,
        height=height,
        territory_count=territory_count,
        grid_offset=grid_offset,
        section8_offset=section8_offset,
        territory_offset=territory_offset,
        building_count=building_count,
        army_count=army_count,
    )


def read_grid(data: bytes, layout: SaveLayout, grid_offset: int) -> list[list[int]]:
    width, height = layout.width, layout.height
    grid = [[0] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            cell_off = grid_offset + (y * width + x) * GRID_CELL_BYTES
            grid[y][x] = struct.unpack_from("<H", data, cell_off + 2)[0]
    return grid


def read_grid_cell_value(
    data: bytes,
    layout: SaveLayout,
    x: int,
    y: int,
) -> int:
    """Return grid cell u16[2] (+0x04): packed exposure (low) + autotile variant (high)."""
    cell_off = layout.grid_offset + (y * layout.width + x) * GRID_CELL_BYTES
    return struct.unpack_from("<H", data, cell_off + GRID_CELL_VALUE_OFF)[0]


def read_grid_cell_values(
    data: bytes,
    layout: SaveLayout,
    grid: list[list[int]],
) -> list[list[int]]:
    """Return u16[2] per-cell values parallel to the territory-id grid."""
    width = layout.width
    values = [[0] * width for _ in range(layout.height)]
    for y, row in enumerate(grid):
        for x, territory_id in enumerate(row):
            if territory_id <= 0:
                continue
            values[y][x] = read_grid_cell_value(data, layout, x, y)
    return values


# Vanilla exposure -> u16[2] words per terrain profile (high byte), from base.sav.
# Ocean (high 0) uses remapped low-byte encodings; never derive edge tiles via
# ``(high << 8) | exposure`` for that profile.
DEFAULT_WORLD_MAP_EXPOSURE_CATALOG: dict[int, dict[int, int]] = {
    0: {
        0: 0, 2: 2, 4: 4, 16: 16, 17: 185, 18: 18, 19: 19, 32: 32, 33: 33, 40: 236,
        41: 41, 48: 48, 49: 49, 51: 51, 56: 56, 59: 59, 64: 64, 68: 236, 80: 80,
        82: 82, 83: 83, 84: 84, 86: 86, 87: 87, 113: 113, 115: 115, 119: 119,
        128: 128, 132: 132, 136: 136, 160: 160, 164: 164, 168: 168, 173: 173,
        185: 185, 187: 187, 192: 192, 196: 196, 198: 198, 204: 204, 206: 206,
        210: 210, 214: 214, 215: 215, 222: 222, 236: 236, 237: 237,
    },
    1: {
        0: 256, 16: 272, 32: 288, 33: 289, 49: 305, 51: 307, 57: 313, 64: 320,
        66: 322, 68: 492, 69: 493, 82: 338, 83: 339, 115: 371, 128: 384, 164: 420,
        168: 424, 172: 428, 185: 441, 196: 452, 198: 454, 204: 460, 214: 470,
        236: 492,
    },
    2: {
        0: 512, 8: 520, 17: 529, 33: 545, 48: 560, 59: 571, 128: 640, 132: 644,
        136: 648, 140: 652, 168: 680, 172: 684, 181: 693, 196: 708, 228: 740,
        236: 748, 237: 749, 253: 765,
    },
    3: {
        0: 768, 1: 769, 2: 770, 4: 772, 8: 972, 16: 784, 17: 785, 18: 786, 19: 787,
        32: 800, 33: 801, 40: 808, 48: 816, 49: 817, 50: 818, 51: 819, 56: 824,
        57: 825, 59: 827, 64: 832, 66: 834, 68: 836, 70: 1006, 80: 848, 82: 850,
        83: 851, 86: 854, 87: 855, 115: 883, 123: 891, 128: 896, 132: 900,
        136: 904, 140: 908, 145: 913, 160: 928, 168: 936, 169: 937, 172: 940,
        173: 941, 177: 945, 185: 953, 187: 955, 189: 957, 192: 960, 194: 962,
        196: 964, 198: 966, 204: 972, 206: 974, 212: 980, 214: 982, 215: 983,
        222: 990, 228: 996, 236: 1004,
    },
    4: {
        0: 1024, 17: 1041, 20: 1044, 40: 1064, 49: 1073, 56: 1080, 82: 1106,
        86: 1110, 115: 1139, 128: 1152, 132: 1156, 136: 1160, 160: 1184, 177: 1201,
        185: 1209, 194: 1218, 196: 1220, 214: 1238, 237: 1261,
    },
    5: {
        0: 1280, 17: 1297, 49: 1329, 82: 1362, 86: 1366, 115: 1395, 168: 1448,
        184: 1464, 187: 1467, 222: 1502, 236: 1516,
    },
}


def build_exposure_catalog_for_high(
    data: bytes,
    layout: SaveLayout,
    grid: list[list[int]],
    high_byte: int,
) -> dict[int, int]:
    """Most common u16[2] word for each exposure mask with a given autotile high byte."""
    width = layout.width
    height = layout.height
    counts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for y, row in enumerate(grid):
        for x, territory_id in enumerate(row):
            if territory_id <= 0:
                continue
            _low, high = _split_grid_cell_u16_2(read_grid_cell_value(data, layout, x, y))
            if high != (high_byte & 0xFF):
                continue
            exposure = _neighbor_exposure(x, y, grid, territory_id, width, height)
            word = read_grid_cell_value(data, layout, x, y)
            counts[exposure][word] += 1
    return {
        exposure: max(tiles, key=tiles.get)
        for exposure, tiles in counts.items()
    }


def merged_exposure_catalog_for_high(
    data: bytes,
    layout: SaveLayout,
    grid: list[list[int]],
    high_byte: int,
) -> dict[int, int]:
    """Vanilla exposure catalog for world-map terrain encoding.

    Save-derived catalogs must not override defaults: different colonies can share
    the same neighbor-exposure mask while using different u16[2] low-byte encodings
    (e.g. Cyth ``0x0311`` vs Bush Plains ``0x03b9`` both at exposure 17).
    """
    _ = (data, layout, grid)
    return dict(DEFAULT_WORLD_MAP_EXPOSURE_CATALOG.get(high_byte & 0xFF, {}))


def word_for_world_map_terrain_paint(
    data: bytes,
    layout: SaveLayout,
    grid: list[list[int]],
    x: int,
    y: int,
    new_high: int,
) -> int:
    """Pick a full grid u16[2] word for painting terrain type at (x, y).

    The game uses the whole packed word (exposure/autotile low byte + profile high
    byte), not the high byte alone. Edge cells in vanilla saves use exposure-specific
    low-byte encodings that must match the target terrain profile.
    """
    territory_id = grid[y][x]
    if territory_id <= 0:
        raise ValueError("Cannot paint terrain on an empty map cell")
    width = layout.width
    height = layout.height
    exposure = _neighbor_exposure(x, y, grid, territory_id, width, height)
    high_byte = new_high & 0xFF
    catalog = merged_exposure_catalog_for_high(data, layout, grid, high_byte)
    interior_default = _pack_grid_cell_u16_2(0, high_byte)
    return _pick_terrain_tile_for_exposure(
        x,
        y,
        exposure,
        catalog,
        width=width,
        height=height,
        interior_default=interior_default,
    )


def refresh_world_map_terrain_cells(
    data: bytearray,
    layout: SaveLayout,
    grid: list[list[int]],
    cells: set[tuple[int, int]],
) -> None:
    """Re-encode u16[2] on cells using each cell's current profile high byte."""
    width = layout.width
    height = layout.height
    for x, y in cells:
        territory_id = grid[y][x]
        if territory_id <= 0:
            continue
        _low, high_byte = _split_grid_cell_u16_2(
            read_grid_cell_value(data, layout, x, y)
        )
        exposure = _neighbor_exposure(x, y, grid, territory_id, width, height)
        catalog = merged_exposure_catalog_for_high(data, layout, grid, high_byte)
        interior_default = _pack_grid_cell_u16_2(0, high_byte)
        word = _pick_terrain_tile_for_exposure(
            x,
            y,
            exposure,
            catalog,
            width=width,
            height=height,
            interior_default=interior_default,
        )
        write_grid_cell_value(data, layout, x, y, word)


def write_grid_cell_value(
    data: bytearray,
    layout: SaveLayout,
    x: int,
    y: int,
    word: int,
) -> None:
    cell_off = layout.grid_offset + (y * layout.width + x) * GRID_CELL_BYTES
    struct.pack_into("<H", data, cell_off + GRID_CELL_VALUE_OFF, word & 0xFFFF)


def read_territories(data: bytes, layout: SaveLayout) -> list[TerritoryInfo]:
    territories: list[TerritoryInfo] = []
    for index in range(1, layout.territory_count + 1):
        record_off = layout.territory_offset + (index - 1) * STORED_RECORD
        record = data[record_off : record_off + STORED_RECORD]
        name_end = record.find(b"\x00", NAME_OFF)
        if name_end <= NAME_OFF:
            name = ""
        else:
            name = record[NAME_OFF:name_end].decode("latin-1")
        territory_id = struct.unpack_from("<H", record, NAME_OFF + STABLE_ID_OFF)[0]
        owner = record[NAME_OFF + OWNER_OFF]
        terrain_subtype = record[NAME_OFF + TERRAIN_SUBTYPE_OFF]
        terrain_kind = record[NAME_OFF + TERRAIN_KIND_OFF]
        count = record[NAME_OFF + OUTLINE_COUNT_OFF]
        cells = [
            struct.unpack_from("<HH", record, NAME_OFF + OUTLINE_DATA_OFF + i * 4)
            for i in range(count)
        ]
        population = struct.unpack_from("<H", record, TERRITORY_POPULATION_OFF)[0]
        stockpile = read_territory_stockpile(record)
        territories.append(
            TerritoryInfo(
                index=index,
                territory_id=territory_id,
                name=name,
                owner=owner,
                terrain_kind=terrain_kind,
                terrain_subtype=terrain_subtype,
                cells=cells,
                population=population,
                stockpile=stockpile,
            )
        )
    return territories


def resolve_owner_labels(territories: list[TerritoryInfo]) -> dict[int, str]:
    """Map owner byte -> faction name for this save.

    The owner byte is a player-slot index (0, 1, 2, ...), not a fixed race id.
    Tarth is only owner 0 when Tarth occupies slot 0. Prefer capital names like
    ``Maug Landing`` when present.
    """
    labels: dict[int, str] = {UNOWNED_OWNER: "Unowned"}
    for territory in territories:
        if territory.owner == UNOWNED_OWNER:
            continue
        if territory.name.endswith(LANDING_SUFFIX):
            labels.setdefault(territory.owner, territory.name[: -len(LANDING_SUFFIX)])
    for territory in territories:
        if territory.owner not in labels and territory.owner != UNOWNED_OWNER:
            labels[territory.owner] = f"Player {territory.owner}"
    return labels


def assign_symbols(territories: list[TerritoryInfo]) -> dict[int, str]:
    used_ids = sorted({t.territory_id for t in territories if t.territory_id > 0})
    if len(used_ids) > len(SYMBOL_ALPHABET):
        raise ValueError(
            f"Too many territories ({len(used_ids)}) for ASCII symbol alphabet "
            f"({len(SYMBOL_ALPHABET)})"
        )
    return {tid: SYMBOL_ALPHABET[i] for i, tid in enumerate(used_ids)}


def symbol_for_id(territory_id: int, symbol_map: dict[int, str]) -> str:
    if territory_id == 0:
        return "."
    try:
        return symbol_map[territory_id]
    except KeyError:
        raise ValueError(f"Territory id {territory_id} is not listed in the legend")


def export_ascii_map(
    data: bytes,
    *,
    source_name: str | None = None,
) -> str:
    layout = parse_layout(data)
    grid = read_grid(data, layout, layout.grid_offset)
    territories = read_territories(data, layout)
    symbol_map = assign_symbols(territories)
    id_to_name = {t.territory_id: t.name for t in territories if t.name}
    id_to_owner = {t.territory_id: t.owner for t in territories if t.territory_id > 0}
    owner_labels = resolve_owner_labels(territories)

    lines: list[str] = []
    lines.append("# Deadlock territory map (ASCII)")
    if source_name:
        lines.append(f"# source: {source_name}")
    lines.append(f"# width: {layout.width}  height: {layout.height}")
    lines.append("# coordinates: x increases right, y increases down (row 00 is top)")
    lines.append("# edit one character per map cell; use '.' for unassigned (id 0)")
    lines.append("#")
    lines.append("# legend: symbol  id  owner  name")
    for territory_id in sorted(symbol_map):
        owner = id_to_owner.get(territory_id, UNOWNED_OWNER)
        owner_label = owner_labels.get(owner, str(owner))
        name = id_to_name.get(territory_id, "")
        lines.append(
            f"#   {symbol_map[territory_id]}  {territory_id:3d}  {owner_label:8s}  {name}"
        )
    lines.append("@MAP")
    x_axis = "".join(str(d % 10) for d in range(layout.width))
    lines.append(f"   {x_axis}")
    for y, row in enumerate(grid):
        chars = "".join(symbol_for_id(tid, symbol_map) for tid in row)
        lines.append(f"{y:02d} {chars}")
    return "\n".join(lines) + "\n"


def parse_ascii_map(text: str) -> tuple[int, int, dict[str, int], list[list[int]]]:
    lines = text.splitlines()
    width = height = 0
    symbol_to_id: dict[str, int] = {}
    map_rows: list[str] = []

    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#   "):
            # legend row: #   A    1  Unowned  Name
            body = stripped[2:].strip()
            parts = body.split(None, 3)
            if len(parts) >= 2 and len(parts[0]) == 1:
                symbol_to_id[parts[0]] = int(parts[1])
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("@MAP"):
            continue
        if stripped.startswith("width:"):
            # legacy support: width: 40  height: 40
            parts = stripped.replace(":", " ").split()
            for i, part in enumerate(parts):
                if part == "width" and i + 1 < len(parts):
                    width = int(parts[i + 1])
                if part == "height" and i + 1 < len(parts):
                    height = int(parts[i + 1])
            continue

        if len(stripped) >= 3 and stripped[:2].isdigit() and stripped[2] == " ":
            y = int(stripped[:2])
            map_rows.append((y, stripped[3:]))
            continue

        if stripped and all(ch in "0123456789" for ch in stripped):
            # x-axis helper row (digits only)
            continue

    if not map_rows:
        raise ValueError("No @MAP rows found in ASCII map")

    map_rows.sort(key=lambda item: item[0])
    grid_chars = [row for _, row in map_rows]
    height = len(grid_chars)
    width = len(grid_chars[0])
    if any(len(row) != width for row in grid_chars):
        raise ValueError("All map rows must have the same width")

    if "." not in symbol_to_id.values():
        symbol_to_id.setdefault(".", 0)

    grid: list[list[int]] = []
    for row in grid_chars:
        ids_row: list[int] = []
        for ch in row:
            if ch not in symbol_to_id:
                raise ValueError(f"Unknown map symbol '{ch}' (not in legend)")
            ids_row.append(symbol_to_id[ch])
        grid.append(ids_row)

    return width, height, symbol_to_id, grid


def _cells_for_id(grid: list[list[int]], territory_id: int) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    for y, row in enumerate(grid):
        for x, tid in enumerate(row):
            if tid == territory_id:
                cells.append((x, y))
    return sort_outline_cells(cells)


def territory_bounding_box(cells: list[tuple[int, int]]) -> tuple[int, int]:
    """Return axis-aligned width and height for a territory's cells."""
    if not cells:
        return 0, 0
    xs = [x for x, _y in cells]
    ys = [y for _x, y in cells]
    return max(xs) - min(xs) + 1, max(ys) - min(ys) + 1


def oversized_territory_warnings(
    grid: list[list[int]],
    territories: list[TerritoryInfo],
) -> list[str]:
    """Return user-facing warnings for territories above ``MAX_TERRITORY_CELLS``."""
    warnings: list[str] = []
    for territory in territories:
        tid = territory.territory_id
        if tid <= 0:
            continue
        cells = _cells_for_id(grid, tid)
        if len(cells) > MAX_TERRITORY_CELLS:
            warnings.append(
                f"{territory.name!r} (id {tid}) has {len(cells)} cells "
                f"(recommended maximum {MAX_TERRITORY_CELLS})"
            )
    return warnings


def territory_cells_error(cells: list[tuple[int, int]], *, label: str = "Territory") -> str | None:
    """Return a user-facing error if ``cells`` cannot be saved, else ``None``."""
    if not cells:
        return f"{label} would have no cells"
    if not _is_contiguous(cells):
        return f"{label} would be split into disconnected pieces"
    box_w, box_h = territory_bounding_box(cells)
    if box_w < MIN_TERRITORY_WIDTH or box_h < MIN_TERRITORY_HEIGHT:
        return (
            f"{label} would be too small ({box_w}x{box_h}); "
            f"Deadlock requires at least {MIN_TERRITORY_WIDTH}x{MIN_TERRITORY_HEIGHT}"
        )
    return None


def _is_contiguous(cells: list[tuple[int, int]]) -> bool:
    if len(cells) <= 1:
        return True
    cell_set = set(cells)
    start = cells[0]
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) in cell_set and (nx, ny) not in seen:
                seen.add((nx, ny))
                stack.append((nx, ny))
    return len(seen) == len(cell_set)


def validate_grid(
    grid: list[list[int]],
    layout: SaveLayout,
    territories: list[TerritoryInfo],
) -> list[str]:
    warnings: list[str] = []
    height = len(grid)
    width = len(grid[0]) if height else 0
    if width != layout.width or height != layout.height:
        raise ValueError(
            f"Map size mismatch: ASCII is {width}x{height}, save is {layout.width}x{layout.height}"
        )

    ids_on_map = {tid for row in grid for tid in row if tid > 0}
    known_ids = {t.territory_id for t in territories if t.territory_id > 0}
    unknown = sorted(ids_on_map - known_ids)
    if unknown:
        warnings.append(f"Unknown territory ids on map: {unknown}")

    for territory in territories:
        tid = territory.territory_id
        if tid <= 0:
            continue
        cells = _cells_for_id(grid, tid)
        if not cells and territory.cells:
            raise ValueError(
                f"Territory {tid} ({territory.name!r}) has no cells on the map"
            )
        if cells and not _is_contiguous(cells):
            raise ValueError(
                f"Territory {tid} ({territory.name!r}) is not contiguous"
            )
        if cells:
            box_w, box_h = territory_bounding_box(cells)
            if box_w < MIN_TERRITORY_WIDTH or box_h < MIN_TERRITORY_HEIGHT:
                raise ValueError(
                    f"Territory {tid} ({territory.name!r}) bounding box is {box_w}x{box_h}; "
                    f"Deadlock requires at least {MIN_TERRITORY_WIDTH} wide and "
                    f"{MIN_TERRITORY_HEIGHT} tall (crashes on load if smaller)"
                )
    warnings.extend(oversized_territory_warnings(grid, territories))
    return warnings


def _write_cell_territory_id(
    data: bytearray,
    grid_offset: int,
    width: int,
    x: int,
    y: int,
    territory_id: int,
) -> None:
    cell_off = grid_offset + (y * width + x) * 10
    struct.pack_into("<H", data, cell_off + 2, territory_id)


def _neighbor_exposure(
    x: int,
    y: int,
    grid: list[list[int]],
    territory_id: int,
    width: int,
    height: int,
) -> int:
    """Neighbor-exposure bitmask matching game ``0x00438960`` (8 directions)."""
    flags = 0
    if x > 0 and grid[y][x - 1] != territory_id:
        flags |= EXPOSURE_W
    if y > 0 and grid[y - 1][x] != territory_id:
        flags |= EXPOSURE_N
    if x + 1 < width and grid[y][x + 1] != territory_id:
        flags |= EXPOSURE_E
    if y + 1 < height and grid[y + 1][x] != territory_id:
        flags |= EXPOSURE_S
    if x > 0 and y > 0 and grid[y - 1][x - 1] != territory_id:
        flags |= EXPOSURE_NW
    if x + 1 < width and y > 0 and grid[y - 1][x + 1] != territory_id:
        flags |= EXPOSURE_NE
    if x > 0 and y + 1 < height and grid[y + 1][x - 1] != territory_id:
        flags |= EXPOSURE_SW
    if x + 1 < width and y + 1 < height and grid[y + 1][x + 1] != territory_id:
        flags |= EXPOSURE_SE
    return flags


def _split_grid_cell_u16_2(word: int) -> tuple[int, int]:
    return word & 0xFF, (word >> 8) & 0xFF


def _pack_grid_cell_u16_2(low: int, high: int) -> int:
    return ((high & 0xFF) << 8) | (low & 0xFF)


def _legacy_border_exposure_key(game_exposure: int) -> int:
    """Map game exposure bits to the legacy key used by ``_border_byte_for_exposure``."""
    key = 0
    if game_exposure & EXPOSURE_N:
        key |= 4
    if game_exposure & EXPOSURE_W:
        key |= 1
    if game_exposure & EXPOSURE_S:
        key |= 8
    if game_exposure & EXPOSURE_E:
        key |= 2
    return key


def _autotile_high_byte_for_subtype(subtype: int) -> int:
    """Deterministic high-byte defaults approximating game ``0x0043EBA3``."""
    if subtype == TERRAIN_SUBTYPE_MOUNTAINS:
        return 5
    if subtype == TERRAIN_SUBTYPE_SWAMP:
        return 1
    if subtype == TERRAIN_SUBTYPE_FOREST:
        return 2
    if subtype == TERRAIN_SUBTYPE_PLAINS:
        return 3
    return 0


def _interior_high_byte_for_territory(
    data: bytes,
    layout: SaveLayout,
    grid: list[list[int]],
    territory_id: int,
    width: int,
    height: int,
) -> int | None:
    """Most common autotile high byte on interior cells of a territory."""
    counts: dict[int, int] = defaultdict(int)
    for y in range(height):
        for x in range(width):
            if grid[y][x] != territory_id:
                continue
            if _neighbor_exposure(x, y, grid, territory_id, width, height) != 0:
                continue
            _, high = _split_grid_cell_u16_2(read_grid_cell_value(data, layout, x, y))
            counts[high] += 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def _cells_with_changed_ownership(
    old_grid: list[list[int]],
    grid: list[list[int]],
) -> set[tuple[int, int]]:
    changed: set[tuple[int, int]] = set()
    for y, row in enumerate(grid):
        for x, old_id in enumerate(row):
            if old_grid[y][x] != old_id:
                changed.add((x, y))
    return changed


def _terrain_exposure_catalog(
    data: bytes,
    layout: SaveLayout,
    grid: list[list[int]],
    territory_id: int,
) -> dict[int, int]:
    """Most common u16[2] value for each edge-exposure mask in a territory (vanilla samples)."""
    width = layout.width
    height = layout.height
    counts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for y, row in enumerate(grid):
        for x, cell_tid in enumerate(row):
            if cell_tid != territory_id:
                continue
            exposure = _neighbor_exposure(x, y, grid, territory_id, width, height)
            tile = read_grid_cell_value(data, layout, x, y)
            counts[exposure][tile] += 1
    return {
        exposure: max(tiles, key=tiles.get)
        for exposure, tiles in counts.items()
    }


def _cells_needing_terrain_refresh(
    changed_cells: set[tuple[int, int]],
    grid: list[list[int]],
    width: int,
    height: int,
) -> set[tuple[int, int]]:
    """Cells whose u16[2] may need rewriting when ownership moves across a border."""
    refresh = set(changed_cells)
    for x, y in changed_cells:
        for nx, ny in ((x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y)):
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if grid[ny][nx] > 0:
                refresh.add((nx, ny))
    return refresh


def _edge_cells_for_territories(
    grid: list[list[int]],
    territory_ids: set[int],
    width: int,
    height: int,
) -> set[tuple[int, int]]:
    """All owned perimeter cells for territories whose borders may have moved."""
    refresh: set[tuple[int, int]] = set()
    for y in range(height):
        for x in range(width):
            territory_id = grid[y][x]
            if territory_id not in territory_ids:
                continue
            exposure = _neighbor_exposure(x, y, grid, territory_id, width, height)
            if exposure != 0:
                refresh.add((x, y))
    return refresh


def _map_edge_adjusted_exposure(
    x: int,
    y: int,
    exposure: int,
    width: int,
    height: int,
) -> int:
    """Drop edges handled by the map rim before exposure-catalog lookup."""
    adjusted = exposure
    if x == 0 and (adjusted & EXPOSURE_W):
        adjusted &= ~EXPOSURE_W
    if x == width - 1 and (adjusted & EXPOSURE_E):
        adjusted &= ~EXPOSURE_E
    if y == 0 and (adjusted & EXPOSURE_N):
        adjusted &= ~EXPOSURE_N
    if y == height - 1 and (adjusted & EXPOSURE_S):
        adjusted &= ~EXPOSURE_S
    if x == 0 and (adjusted & (EXPOSURE_NW | EXPOSURE_SW)):
        adjusted &= ~(EXPOSURE_NW | EXPOSURE_SW)
    if x == width - 1 and (adjusted & (EXPOSURE_NE | EXPOSURE_SE)):
        adjusted &= ~(EXPOSURE_NE | EXPOSURE_SE)
    if y == 0 and (adjusted & (EXPOSURE_NW | EXPOSURE_NE)):
        adjusted &= ~(EXPOSURE_NW | EXPOSURE_NE)
    if y == height - 1 and (adjusted & (EXPOSURE_SW | EXPOSURE_SE)):
        adjusted &= ~(EXPOSURE_SW | EXPOSURE_SE)
    return adjusted


def _terrain_exposure_catalog_by_subtype(
    source_data: bytes,
    layout: SaveLayout,
    source_grid: list[list[int]],
    territories: list[TerritoryInfo],
    subtype: int,
) -> dict[int, int]:
    """Exposure catalog pooled across territories sharing a terrain sub-type."""
    if subtype == 0:
        return {}
    width = layout.width
    height = layout.height
    counts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for territory in territories:
        if territory.terrain_subtype != subtype:
            continue
        territory_id = territory.territory_id
        for y, row in enumerate(source_grid):
            for x, cell_tid in enumerate(row):
                if cell_tid != territory_id:
                    continue
                exposure = _neighbor_exposure(
                    x, y, source_grid, territory_id, width, height
                )
                tile = read_grid_cell_value(source_data, layout, x, y)
                counts[exposure][tile] += 1
    return {
        exposure: max(tiles, key=tiles.get)
        for exposure, tiles in counts.items()
    }


def _pick_terrain_tile_for_exposure(
    x: int,
    y: int,
    exposure: int,
    catalog: dict[int, int],
    *,
    width: int,
    height: int,
    interior_default: int,
    subtype_catalog: dict[int, int] | None = None,
) -> int:
    if exposure == 0:
        return catalog.get(0, interior_default)
    if exposure in catalog:
        return catalog[exposure]
    if subtype_catalog and exposure in subtype_catalog:
        return subtype_catalog[exposure]

    adjusted = _map_edge_adjusted_exposure(x, y, exposure, width, height)
    if adjusted != exposure:
        if adjusted == 0:
            return catalog.get(0, interior_default)
        if adjusted in catalog:
            return catalog[adjusted]
        if subtype_catalog and adjusted in subtype_catalog:
            return subtype_catalog[adjusted]
        exposure = adjusted

    supersets = [
        mask
        for mask in catalog
        if mask != 0 and (mask & exposure) == exposure
    ]
    if supersets:
        best_mask = min(
            supersets,
            key=lambda mask: ((mask & ~exposure).bit_count(), mask.bit_count(), mask),
        )
        return catalog[best_mask]
    if subtype_catalog:
        supersets = [
            mask
            for mask in subtype_catalog
            if mask != 0 and (mask & exposure) == exposure
        ]
        if supersets:
            best_mask = min(
                supersets,
                key=lambda mask: (
                    (mask & ~exposure).bit_count(),
                    mask.bit_count(),
                    mask,
                ),
            )
            return subtype_catalog[best_mask]
    subsets = [
        mask
        for mask in catalog
        if mask != 0 and (exposure & mask) == mask
    ]
    if subsets:
        best_mask = max(subsets, key=lambda mask: (mask.bit_count(), mask))
        return catalog[best_mask]
    edge_tiles = [tile for mask, tile in catalog.items() if mask != 0]
    if edge_tiles:
        return max(set(edge_tiles), key=edge_tiles.count)
    return interior_default


def _world_gen_profile_map(
    source_data: bytes,
    layout: SaveLayout,
    grid: list[list[int]],
    territories: list[TerritoryInfo],
) -> dict[tuple[int, int], int]:
    """Build ``0x0043EBA3`` profile bytes for the current map, if tables are present."""
    try:
        from world_gen_grid import build_profile_high_map
    except ImportError:
        return {}
    save = LoadedSave(
        path=None,
        data=source_data,
        layout=layout,
        grid=grid,
        territories=territories,
    )
    try:
        return build_profile_high_map(save, source_data)
    except FileNotFoundError:
        return {}


def regenerate_world_grid_terrain(
    data: bytes | bytearray,
    layout: SaveLayout,
    grid: list[list[int]],
    territories: list[TerritoryInfo],
    *,
    rng_advance: int | None = None,
    cells: set[tuple[int, int]] | None = None,
    calibrate_rng: bool = False,
    only_territory_ids: set[int] | None = None,
    full_territory: bool = False,
) -> bytes:
    """Re-encode grid u16[2] bytes using world-gen exposure + profile rules."""
    from world_gen_grid import write_outline_grid_terrain

    patched = bytearray(data)
    save = LoadedSave(
        path=None,
        data=bytes(patched),
        layout=layout,
        grid=grid,
        territories=territories,
    )
    write_outline_grid_terrain(
        patched,
        save,
        rng_advance=rng_advance,
        cells=cells,
        calibrate_rng=calibrate_rng,
        only_territory_ids=only_territory_ids,
        full_territory=full_territory,
    )
    return bytes(patched)


def _refresh_grid_cell_values(
    data: bytearray,
    layout: SaveLayout,
    grid: list[list[int]],
    territory_ids: set[int],
    cells_to_refresh: set[tuple[int, int]],
    *,
    source_data: bytes,
    source_grid: list[list[int]],
    territories: list[TerritoryInfo],
) -> None:
    """Rewrite grid u16[2] on affected cells after a boundary edit.

    Low byte (exposure) is recomputed with game ``0x00438960`` rules. High byte
    (autotile variant) is preserved when a cell stays in the same territory,
    otherwise taken from the ``0x0043EBA3`` profile map when available.
    """
    width = layout.width
    height = layout.height
    subtype_by_id = {
        territory.territory_id: territory.terrain_subtype for territory in territories
    }
    interior_high_cache: dict[int, int] = {}
    profile_by_coord = _world_gen_profile_map(source_data, layout, grid, territories)

    for territory_id in territory_ids:
        for x, y in cells_to_refresh:
            if grid[y][x] != territory_id:
                continue

            exposure = _neighbor_exposure(x, y, grid, territory_id, width, height)
            _, source_high = _split_grid_cell_u16_2(
                read_grid_cell_value(source_data, layout, x, y)
            )

            if source_grid[y][x] == territory_id:
                high = source_high
            elif (x, y) in profile_by_coord:
                high = profile_by_coord[(x, y)]
            else:
                if territory_id not in interior_high_cache:
                    interior_high = _interior_high_byte_for_territory(
                        source_data,
                        layout,
                        source_grid,
                        territory_id,
                        width,
                        height,
                    )
                    if interior_high is None:
                        interior_high = _autotile_high_byte_for_subtype(
                            subtype_by_id.get(territory_id, 0)
                        )
                    interior_high_cache[territory_id] = interior_high
                high = interior_high_cache[territory_id]

            tile = _pack_grid_cell_u16_2(exposure, high)
            cell_off = layout.grid_offset + (y * width + x) * GRID_CELL_BYTES
            struct.pack_into("<H", data, cell_off + GRID_CELL_VALUE_OFF, tile)


def _border_byte_for_exposure(exposure: int) -> int:
    """Map an exposed-edge mask to a territory-record border byte at ``+0x68``."""
    return _border_byte_for_legacy_exposure(_legacy_border_exposure_key(exposure))


def _border_byte_for_legacy_exposure(exposure: int) -> int:
    """Map a legacy cardinal exposure key to a territory-record border byte."""
    if exposure == 0:
        return 0x0C
    if exposure == 4:
        return 0x01
    if exposure in (5, 7, 13):
        return 0x03
    if exposure in (9,):
        return 0x03
    if exposure in (10,):
        return 0x00
    return 0x0C


def _read_border_bytes(data: bytes, record_off: int, count: int) -> list[int]:
    start = record_off + NAME_OFF + BORDER_BYTE_OFF
    limit = min(count, MAX_INLINE_BORDER_BYTES)
    return list(data[start : start + limit])


def border_bytes_for_outline(
    old_cells: list[tuple[int, int]],
    new_cells: list[tuple[int, int]],
    old_bytes: list[int],
    grid: list[list[int]],
    territory_id: int,
    width: int,
    height: int,
) -> list[int]:
    """Rebuild per-outline border bytes, keeping stable cells when possible."""
    old_map = {
        cell: old_bytes[index]
        for index, cell in enumerate(old_cells)
        if index < len(old_bytes)
    }
    old_set = set(old_cells)
    new_set = set(new_cells)
    changed_coords = old_set ^ new_set

    result: list[int] = []
    for cell in new_cells:
        exposure = _neighbor_exposure(
            cell[0], cell[1], grid, territory_id, width, height
        )
        if cell in changed_coords or cell not in old_map:
            result.append(_border_byte_for_exposure(exposure))
            continue

        old_exposure = _neighbor_exposure_on_cells(
            cell[0], cell[1], old_set, width, height
        )
        if exposure != old_exposure:
            result.append(_border_byte_for_exposure(exposure))
        else:
            result.append(old_map[cell])
    return result


def _neighbor_exposure_on_cells(
    x: int,
    y: int,
    cells: set[tuple[int, int]],
    width: int,
    height: int,
) -> int:
    flags = 0
    if x == 0 or (x - 1, y) not in cells:
        flags |= EXPOSURE_W
    if x == width - 1 or (x + 1, y) not in cells:
        flags |= EXPOSURE_E
    if y == 0 or (x, y - 1) not in cells:
        flags |= EXPOSURE_N
    if y == height - 1 or (x, y + 1) not in cells:
        flags |= EXPOSURE_S
    return flags


def _patch_border_bytes(
    data: bytearray,
    record_off: int,
    border_bytes: list[int],
    *,
    old_count: int = 0,
) -> None:
    start = record_off + NAME_OFF + BORDER_BYTE_OFF
    for index, value in enumerate(border_bytes[:MAX_INLINE_BORDER_BYTES]):
        data[start + index] = value & 0xFF
    clear_from = len(border_bytes)
    clear_to = max(old_count, clear_from)
    for index in range(clear_from, min(clear_to, MAX_INLINE_BORDER_BYTES)):
        data[start + index] = 0


def _save_has_stamped_border_flags(data: bytes, layout: SaveLayout) -> bool:
    """Return True when the save already uses post-init ``u16[4]`` border flags."""
    width, height = layout.width, layout.height
    grid_offset = layout.grid_offset
    for y in range(height):
        for x in range(width):
            cell_off = grid_offset + (y * width + x) * 10
            if struct.unpack_from("<H", data, cell_off + 8)[0] != 0:
                return True
    return False


def _write_grid_border_flags(
    data: bytearray,
    grid_offset: int,
    width: int,
    height: int,
    grid: list[list[int]],
    territory_ids: set[int],
    *,
    interior_value: int,
) -> None:
    """Write ``u16[4]`` edge flags for territories whose shape changed."""
    for y in range(height):
        for x in range(width):
            territory_id = grid[y][x]
            if territory_id not in territory_ids:
                continue
            exposure = _neighbor_exposure(
                x, y, grid, territory_id, width, height
            )
            value = interior_value if exposure == 0 else exposure
            cell_off = grid_offset + (y * width + x) * 10
            struct.pack_into("<H", data, cell_off + 8, value)


def _patch_outline(
    data: bytearray,
    record_off: int,
    old_cells: list[tuple[int, int]],
    new_cells: list[tuple[int, int]],
) -> None:
    """Write outline cells while preserving unchanged prefix bytes when possible."""
    count = len(new_cells)
    if count > 255:
        raise ValueError(f"Outline count {count} exceeds byte limit (255)")

    count_off = record_off + NAME_OFF + OUTLINE_COUNT_OFF
    outline_start = record_off + NAME_OFF + OUTLINE_DATA_OFF
    old_count = len(old_cells)

    if count < old_count and new_cells == old_cells[:count]:
        data[count_off] = count
        return

    if count > old_count and new_cells[:old_count] == old_cells:
        for index in range(old_count, count):
            x, y = new_cells[index]
            struct.pack_into("<HH", data, outline_start + index * 4, x, y)
        data[count_off] = count
        return

    first_changed = 0
    for index, (old_cell, new_cell) in enumerate(zip(old_cells, new_cells)):
        if old_cell != new_cell:
            first_changed = index
            break
    else:
        first_changed = min(old_count, count)

    data[count_off] = count
    for index in range(first_changed, count):
        x, y = new_cells[index]
        struct.pack_into("<HH", data, outline_start + index * 4, x, y)
    for index in range(count, old_count):
        struct.pack_into("<HH", data, outline_start + index * 4, 0, 0)


def _territory_ids_needing_border_stamp(
    old_grid: list[list[int]],
    grid: list[list[int]],
    width: int,
    height: int,
) -> set[int]:
    """Territory ids whose ``u16[4]`` may change when cells are erased or moved."""
    stamp_ids: set[int] = set()
    for y in range(height):
        for x in range(width):
            if old_grid[y][x] == grid[y][x]:
                continue
            for nx, ny in ((x, y), (x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                tid = grid[ny][nx]
                if tid > 0:
                    stamp_ids.add(tid)
                old_tid = old_grid[ny][nx]
                if old_tid > 0:
                    stamp_ids.add(old_tid)
    return stamp_ids


def _clear_erased_cell_border_flags(
    data: bytearray,
    grid_offset: int,
    width: int,
    old_grid: list[list[int]],
    grid: list[list[int]],
) -> None:
    height = len(grid)
    for y in range(height):
        for x in range(width):
            if old_grid[y][x] == grid[y][x] or grid[y][x] != 0:
                continue
            cell_off = grid_offset + (y * width + x) * 10
            struct.pack_into("<H", data, cell_off + 8, 0)


def apply_grid(
    data: bytes,
    grid: list[list[int]],
    *,
    strict: bool = True,
) -> bytes:
    layout = parse_layout(data)
    territories = read_territories(data, layout)
    warnings = validate_grid(grid, layout, territories)
    if strict and warnings:
        raise ValueError("Map validation failed:\n- " + "\n- ".join(warnings))

    patched = bytearray(data)
    height = layout.height
    width = layout.width
    old_grid = read_grid(data, layout, layout.grid_offset)

    for y in range(height):
        for x in range(width):
            territory_id = grid[y][x]
            _write_cell_territory_id(
                patched, layout.grid_offset, width, x, y, territory_id
            )

    _clear_erased_cell_border_flags(
        patched, layout.grid_offset, width, old_grid, grid
    )

    cells_by_id: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for y, row in enumerate(grid):
        for x, tid in enumerate(row):
            if tid > 0:
                cells_by_id[tid].append((x, y))

    changed_territory_ids: set[int] = set()

    for territory in territories:
        tid = territory.territory_id
        new_cells = cells_by_id.get(tid, [])
        old_cells = territory.cells
        cells = outline_cells_for_grid(old_cells, new_cells)
        if cells == old_cells:
            continue

        changed_territory_ids.add(tid)
        record_off = layout.territory_offset + (territory.index - 1) * STORED_RECORD
        _patch_outline(patched, record_off, old_cells, cells)
        if (
            territory.name.endswith(LANDING_SUFFIX)
            and len(cells) <= MAX_INLINE_BORDER_BYTES
        ):
            old_border_bytes = _read_border_bytes(patched, record_off, len(old_cells))
            border_bytes = border_bytes_for_outline(
                old_cells,
                cells,
                old_border_bytes,
                grid,
                tid,
                width,
                height,
            )
            _patch_border_bytes(
                patched,
                record_off,
                border_bytes,
                old_count=len(old_cells),
            )

    stamp_ids = _territory_ids_needing_border_stamp(old_grid, grid, width, height)
    changed_cells = _cells_with_changed_ownership(old_grid, grid)
    if stamp_ids and changed_cells:
        refresh_cells = _cells_needing_terrain_refresh(
            changed_cells,
            grid,
            width,
            height,
        )
        refresh_cells |= _edge_cells_for_territories(
            grid,
            stamp_ids,
            width,
            height,
        )
        _refresh_grid_cell_values(
            patched,
            layout,
            grid,
            stamp_ids,
            refresh_cells,
            source_data=data,
            source_grid=old_grid,
            territories=territories,
        )
    if stamp_ids:
        landing_ids = {
            territory.territory_id
            for territory in territories
            if territory.name.endswith(LANDING_SUFFIX)
        }
        stamp_ids &= landing_ids
        if stamp_ids:
            interior_border = (
                INTERIOR_BORDER_FLAG
                if _save_has_stamped_border_flags(data, layout)
                else 0
            )
            _write_grid_border_flags(
                patched,
                layout.grid_offset,
                width,
                height,
                grid,
                stamp_ids,
                interior_value=interior_border,
            )

    return bytes(patched)


def load_save(path: Path) -> bytes:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Save file not found: {path}")
    if path.suffix.lower() != ".sav":
        raise ValueError(f"Expected a .SAV file, got: {path.name}")
    return path.read_bytes()


def player_slot_count(data: bytes) -> int:
    return struct.unpack_from("<I", data, SECTION2_OFF + 12)[0]


def clamp_resource_quantity(value: int) -> int:
    return max(0, min(MAX_RESOURCE_QUANTITY, value))


def clamp_player_credits(value: int) -> int:
    return max(0, min(MAX_PLAYER_CREDITS, value))


def parse_resource_quantity(text: str) -> int | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        value = int(stripped)
    except ValueError:
        return None
    return clamp_resource_quantity(value)


def read_territory_stockpile(record: bytes) -> TerritoryStockpile:
    values = {
        name: struct.unpack_from("<H", record, offset)[0]
        for name, offset in STOCKPILE_FIELDS
    }
    return TerritoryStockpile(**values)


def write_territory_stockpile(
    data: bytearray,
    record_off: int,
    stockpile: TerritoryStockpile,
) -> None:
    for name, offset in STOCKPILE_FIELDS:
        value = clamp_resource_quantity(getattr(stockpile, name))
        struct.pack_into("<H", data, record_off + offset, value)
    for pad_off in STOCKPILE_PADDING_OFFSETS:
        struct.pack_into("<H", data, record_off + pad_off, 0)


def read_player_credits(data: bytes) -> list[int]:
    count = player_slot_count(data)
    credits: list[int] = []
    for slot in range(count):
        off = PLAYER_TABLE_OFF + slot * PLAYER_SLOT_SIZE + PLAYER_CREDITS_OFF
        credits.append(struct.unpack_from("<H", data, off)[0])
    return credits


def patch_player_credits(data: bytes, credits: list[int]) -> bytes:
    count = player_slot_count(data)
    if len(credits) != count:
        raise ValueError(f"Expected {count} credit values, got {len(credits)}")
    patched = bytearray(data)
    for slot, amount in enumerate(credits):
        off = PLAYER_TABLE_OFF + slot * PLAYER_SLOT_SIZE + PLAYER_CREDITS_OFF
        struct.pack_into("<H", patched, off, clamp_player_credits(amount))
    return bytes(patched)


def owner_choices(territories: list[TerritoryInfo], data: bytes) -> list[tuple[int, str]]:
    labels = resolve_owner_labels(territories)
    choices: list[tuple[int, str]] = [(UNOWNED_OWNER, labels[UNOWNED_OWNER])]
    for slot in range(player_slot_count(data)):
        choices.append((slot, labels.get(slot, f"Player {slot}")))
    return choices


def grid_from_territories(
    territories: list[TerritoryInfo],
    width: int,
    height: int,
) -> list[list[int]]:
    grid = [[0] * width for _ in range(height)]
    for territory in territories:
        for x, y in territory.cells:
            if 0 <= x < width and 0 <= y < height:
                grid[y][x] = territory.territory_id
    return grid


def sync_territory_cells_from_grid(
    territories: list[TerritoryInfo],
    grid: list[list[int]],
) -> None:
    cells_by_id: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for y, row in enumerate(grid):
        for x, tid in enumerate(row):
            if tid > 0:
                cells_by_id[tid].append((x, y))
    for territory in territories:
        grid_cells = cells_by_id.get(territory.territory_id, [])
        if set(grid_cells) == set(territory.cells):
            continue
        territory.cells = outline_cells_for_grid(territory.cells, grid_cells)


def _write_territory_name(data: bytearray, record_off: int, name: str) -> None:
    encoded = name.encode("latin-1")
    if len(encoded) > MAX_NAME_LEN:
        raise ValueError(f"Territory name too long (max {MAX_NAME_LEN}): {name!r}")
    name_start = record_off + NAME_OFF
    trailing_start = name_start + len(encoded) + 1
    preserved = bytes(data[trailing_start : name_start + STABLE_ID_OFF])
    data[name_start:trailing_start] = encoded + b"\x00"
    data[trailing_start : name_start + STABLE_ID_OFF] = preserved


def _write_territory_owner(data: bytearray, record_off: int, owner: int) -> None:
    data[record_off + NAME_OFF + OWNER_OFF] = owner & 0xFF


def read_territory_terrain_kind(data: bytes, record_off: int) -> int:
    return data[record_off + NAME_OFF + TERRAIN_KIND_OFF]


def terrain_kind_label(kind: int) -> str:
    if kind == TERRAIN_KIND_UNSET:
        return "Unset"
    return TERRAIN_KIND_LABELS.get(kind, f"Unknown ({kind})")


def terrain_subtype_label(subtype: int) -> str:
    if subtype == 0:
        return "N/A"
    return TERRAIN_SUBTYPE_LABELS.get(subtype, f"Unknown ({subtype})")


def read_territory_terrain_subtype(data: bytes, record_off: int) -> int:
    return data[record_off + NAME_OFF + TERRAIN_SUBTYPE_OFF]


def _write_territory_terrain_subtype(data: bytearray, record_off: int, subtype: int) -> None:
    data[record_off + NAME_OFF + TERRAIN_SUBTYPE_OFF] = subtype & 0xFF


def _write_territory_terrain_kind(data: bytearray, record_off: int, kind: int) -> None:
    stored_kind = kind
    if kind in TERRAIN_KIND_RECORD_BYTES:
        _, stored_kind = TERRAIN_KIND_RECORD_BYTES[kind]
    data[record_off + NAME_OFF + TERRAIN_KIND_OFF] = stored_kind & 0xFF


def _write_grid_terrain_kind_for_territory(
    data: bytearray,
    layout: SaveLayout,
    grid: list[list[int]],
    territory_id: int,
    kind: int,
) -> None:
    """Intentionally does not modify grid cell u16[2] values.

    Per-cell world-map values at +0x04 are preserved on metadata-only saves.
    Movement kind is stored separately at territory record +0x22.
    """
    del data, layout, grid, territory_id, kind


def patch_territory_metadata(
    data: bytes,
    layout: SaveLayout,
    grid: list[list[int]],
    territories: list[TerritoryInfo],
    *,
    sync_grid_terrain_kinds: set[int] | None = None,
    only_territory_ids: set[int] | None = None,
) -> bytes:
    """Write territory names, owners, and movement type without reshaping boundaries."""
    patched = bytearray(data)
    sync_grid_terrain_kinds = sync_grid_terrain_kinds or set()
    for territory in territories:
        if only_territory_ids is not None and territory.territory_id not in only_territory_ids:
            continue
        record_off = layout.territory_offset + (territory.index - 1) * STORED_RECORD
        _write_territory_name(patched, record_off, territory.name)
        _write_territory_owner(patched, record_off, territory.owner)
        write_territory_stockpile(patched, record_off, territory.stockpile)
        if territory.terrain_kind != TERRAIN_KIND_UNSET:
            _write_territory_terrain_kind(patched, record_off, territory.terrain_kind)
            _write_territory_terrain_subtype(patched, record_off, territory.terrain_subtype)
            if territory.territory_id in sync_grid_terrain_kinds:
                _write_grid_terrain_kind_for_territory(
                    patched,
                    layout,
                    grid,
                    territory.territory_id,
                    territory.terrain_kind,
                )
    return bytes(patched)


def build_save_bytes(
    data: bytes,
    grid: list[list[int]],
    territories: list[TerritoryInfo],
    *,
    strict: bool = False,
    sync_grid_terrain_kinds: set[int] | None = None,
    apply_grid_changes: bool = True,
    regenerate_terrain: bool = False,
    terrain_territory_ids: set[int] | None = None,
    calibrate_terrain_rng: bool = False,
) -> bytes:
    """Write territory metadata and optionally reshape world-map boundaries."""
    if apply_grid_changes:
        patched = bytearray(apply_grid(data, grid, strict=strict))
        layout = parse_layout(patched)
    else:
        patched = bytearray(data)
        layout = parse_layout(patched)
    patched = bytearray(
        patch_territory_metadata(
            bytes(patched),
            layout,
            grid,
            territories,
            sync_grid_terrain_kinds=sync_grid_terrain_kinds,
        )
    )
    if apply_grid_changes or regenerate_terrain:
        sync_territory_cells_from_grid(territories, grid)
        patched = bytearray(
            regenerate_world_grid_terrain(
                bytes(patched),
                layout,
                grid,
                territories,
                calibrate_rng=calibrate_terrain_rng,
                only_territory_ids=terrain_territory_ids,
                full_territory=terrain_territory_ids is not None,
            )
        )
    return bytes(patched)


@dataclass
class LoadedSave:
    path: Path | None
    data: bytes
    layout: SaveLayout
    grid: list[list[int]]
    territories: list[TerritoryInfo]

    @classmethod
    def from_bytes(cls, data: bytes, path: Path | None = None) -> LoadedSave:
        layout = parse_layout(data)
        grid = read_grid(data, layout, layout.grid_offset)
        territories = read_territories(data, layout)
        sync_territory_cells_from_grid(territories, grid)
        return cls(
            path=path,
            data=data,
            layout=layout,
            grid=grid,
            territories=territories,
        )

    @classmethod
    def from_path(cls, path: Path) -> LoadedSave:
        return cls.from_bytes(load_save(path), path.resolve())

    def owner_choices(self) -> list[tuple[int, str]]:
        return owner_choices(self.territories, self.data)

    def validate(self) -> list[str]:
        return validate_grid(self.grid, self.layout, self.territories)

    def to_bytes(
        self,
        *,
        strict: bool = False,
        sync_grid_terrain_kinds: set[int] | None = None,
        apply_grid_changes: bool = True,
        regenerate_terrain: bool = False,
        terrain_territory_ids: set[int] | None = None,
        calibrate_terrain_rng: bool = False,
    ) -> bytes:
        return build_save_bytes(
            self.data,
            self.grid,
            self.territories,
            strict=strict,
            sync_grid_terrain_kinds=sync_grid_terrain_kinds,
            apply_grid_changes=apply_grid_changes,
            regenerate_terrain=regenerate_terrain,
            terrain_territory_ids=terrain_territory_ids,
            calibrate_terrain_rng=calibrate_terrain_rng,
        )
