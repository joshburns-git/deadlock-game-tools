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
INTERIOR_BORDER_FLAG = 0x7FFF

UNOWNED_OWNER = 255
LANDING_SUFFIX = " Landing"
MAX_NAME_LEN = STABLE_ID_OFF - NAME_OFF - 1  # null-terminated field before +0x1A
# Outline (x, y) pairs at record+0x80 share the record with other fields that
# start around +0x142. 49+ cells overwrite that tail and crash on load.
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

    merged = kept[:]
    for cell in sorted(added, key=outline_sort_key):
        merged = _insert_outline_cell_adjacent(merged, cell)
    return merged

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
class TerritoryInfo:
    index: int
    territory_id: int
    name: str
    owner: int
    cells: list[tuple[int, int]] = field(default_factory=list)


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


def find_grid_offset(data: bytes, width: int, height: int, start: int = 0) -> int:
    cells = width * height
    need = cells * 10
    limit = len(data) - need
    for offset in range(max(0, start), limit + 1, 2):
        ok = 0
        for y in range(height):
            row_base = offset + y * width * 10
            for x in range(width):
                encoded = struct.unpack_from("<H", data, row_base + x * 10)[0]
                if encoded == y * 256 + x:
                    ok += 1
        if ok == cells:
            return offset
    raise ValueError("Could not locate world grid in save file")


def parse_layout(data: bytes) -> SaveLayout:
    width, height, territory_count, section4_count, event_count = _read_header(data)
    section6_end = _section6_end(data, section4_count)
    grid_offset = find_grid_offset(data, width, height, section6_end)
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
            cell_off = grid_offset + (y * width + x) * 10
            grid[y][x] = struct.unpack_from("<H", data, cell_off + 2)[0]
    return grid


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
        count = record[NAME_OFF + OUTLINE_COUNT_OFF]
        cells = [
            struct.unpack_from("<HH", record, NAME_OFF + OUTLINE_DATA_OFF + i * 4)
            for i in range(count)
        ]
        territories.append(
            TerritoryInfo(
                index=index,
                territory_id=territory_id,
                name=name,
                owner=owner,
                cells=cells,
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
    if len(cells) > MAX_TERRITORY_CELLS:
        return f"{label} would have {len(cells)} cells (limit {MAX_TERRITORY_CELLS})"
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
        if len(cells) > MAX_TERRITORY_CELLS:
            raise ValueError(
                f"Territory {tid} ({territory.name!r}) has {len(cells)} cells; "
                f"save limit is {MAX_TERRITORY_CELLS}"
            )
        if cells:
            box_w, box_h = territory_bounding_box(cells)
            if box_w < MIN_TERRITORY_WIDTH or box_h < MIN_TERRITORY_HEIGHT:
                raise ValueError(
                    f"Territory {tid} ({territory.name!r}) bounding box is {box_w}x{box_h}; "
                    f"Deadlock requires at least {MIN_TERRITORY_WIDTH} wide and "
                    f"{MIN_TERRITORY_HEIGHT} tall (crashes on load if smaller)"
                )
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
    """Bitmask of exposed W/E/N/S edges (1/2/4/8) for a territory cell."""
    flags = 0
    if x == 0 or grid[y][x - 1] != territory_id:
        flags |= 1
    if x == width - 1 or grid[y][x + 1] != territory_id:
        flags |= 2
    if y == 0 or grid[y - 1][x] != territory_id:
        flags |= 4
    if y == height - 1 or grid[y + 1][x] != territory_id:
        flags |= 8
    return flags


def _border_byte_for_exposure(exposure: int) -> int:
    """Map an exposed-edge mask to a territory-record border byte at ``+0x68``."""
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
        flags |= 1
    if x == width - 1 or (x + 1, y) not in cells:
        flags |= 2
    if y == 0 or (x, y - 1) not in cells:
        flags |= 4
    if y == height - 1 or (x, y + 1) not in cells:
        flags |= 8
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
    return struct.unpack_from("<I", data, 0x7A + 12)[0]


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
    data[name_start : name_start + STABLE_ID_OFF] = b"\x00" * STABLE_ID_OFF
    data[name_start : name_start + len(encoded)] = encoded


def _write_territory_owner(data: bytearray, record_off: int, owner: int) -> None:
    data[record_off + NAME_OFF + OWNER_OFF] = owner & 0xFF


def build_save_bytes(
    data: bytes,
    grid: list[list[int]],
    territories: list[TerritoryInfo],
    *,
    strict: bool = False,
) -> bytes:
    """Write grid boundaries plus territory names and owners."""
    patched = bytearray(apply_grid(data, grid, strict=strict))
    layout = parse_layout(patched)
    for territory in territories:
        record_off = layout.territory_offset + (territory.index - 1) * STORED_RECORD
        _write_territory_name(patched, record_off, territory.name)
        _write_territory_owner(patched, record_off, territory.owner)
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
        return cls(path=path, data=data, layout=layout, grid=grid, territories=territories)

    @classmethod
    def from_path(cls, path: Path) -> LoadedSave:
        return cls.from_bytes(load_save(path), path.resolve())

    def owner_choices(self) -> list[tuple[int, str]]:
        return owner_choices(self.territories, self.data)

    def validate(self) -> list[str]:
        return validate_grid(self.grid, self.layout, self.territories)

    def to_bytes(self, *, strict: bool = False) -> bytes:
        return build_save_bytes(self.data, self.grid, self.territories, strict=strict)
