"""Isometric colony tile layout (2:1 diamond grid, matching in-game colony view)."""
from __future__ import annotations

GRID_SIZE = 6
# Diamond is twice as wide as it is tall (matches in-game colony tiles).
TILE_HALF_W = 48
TILE_HALF_H = 24
TILE_WIDTH = TILE_HALF_W * 2
TILE_HEIGHT = TILE_HALF_H * 2
TILE_CELL = TILE_WIDTH
PADDING = 10


def _origin() -> tuple[int, int, int, int]:
    """Canvas offset so the full 6x6 diamond grid fits with padding."""
    min_cx = -(GRID_SIZE - 1) * TILE_HALF_W
    max_cx = (GRID_SIZE - 1) * TILE_HALF_W
    max_cy = (GRID_SIZE - 1) * TILE_HALF_H * 2
    origin_x = PADDING - min_cx + TILE_HALF_W
    origin_y = PADDING + TILE_HALF_H
    width = max_cx - min_cx + 2 * TILE_HALF_W + 2 * PADDING
    height = max_cy + 2 * TILE_HALF_H + 2 * PADDING
    return origin_x, origin_y, width, height


def colony_canvas_size() -> tuple[int, int]:
    _, _, width, height = _origin()
    return width, height


def colony_tile_center(row: int, col: int) -> tuple[int, int]:
    origin_x, origin_y, _, _ = _origin()
    cx = origin_x + (col - row) * TILE_HALF_W
    cy = origin_y + (col + row) * TILE_HALF_H
    return cx, cy


def colony_tile_polygon(row: int, col: int, *, inset: int = 0) -> list[int]:
    """Return flat [x0, y0, x1, y1, ...] diamond vertices for a tile."""
    cx, cy = colony_tile_center(row, col)
    half_w = max(TILE_HALF_W - inset, 1)
    half_h = max(TILE_HALF_H - max(inset // 2, 0), 1)
    return [
        cx,
        cy - half_h,
        cx + half_w,
        cy,
        cx,
        cy + half_h,
        cx - half_w,
        cy,
    ]


def colony_tiles_draw_order() -> list[tuple[int, int]]:
    """Back-to-front order for painter's algorithm on the diamond grid."""
    coords = [(row, col) for row in range(GRID_SIZE) for col in range(GRID_SIZE)]
    return sorted(coords, key=lambda rc: (rc[0] + rc[1], rc[0]))


def colony_point_in_tile(row: int, col: int, x: int, y: int) -> bool:
    cx, cy = colony_tile_center(row, col)
    dx = abs(x - cx) / TILE_HALF_W
    dy = abs(y - cy) / TILE_HALF_H
    return dx + dy <= 1.0


def colony_tile_at_point(x: int, y: int) -> tuple[int, int] | None:
    """Map canvas coordinates to the nearest grid cell, if inside its diamond."""
    origin_x, origin_y, _, _ = _origin()
    rx = x - origin_x
    ry = y - origin_y
    col = round((ry / TILE_HALF_H + rx / TILE_HALF_W) / 2)
    row = round((ry / TILE_HALF_H - rx / TILE_HALF_W) / 2)
    if 0 <= row < GRID_SIZE and 0 <= col < GRID_SIZE and colony_point_in_tile(row, col, x, y):
        return row, col
    return None
