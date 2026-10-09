"""Shared world-map drawing helpers for the Game Save Editor."""

from __future__ import annotations

import colorsys
from typing import TYPE_CHECKING

import tkinter as tk

if TYPE_CHECKING:
    from world_map_tiles import WorldMapTileLibrary



MAP_CELL = 22

BOUNDARY_LINE = "#111111"

BOUNDARY_WIDTH = 3

INTERNAL_GRID_LINE = "#999999"

INTERNAL_LINE_WIDTH = 1

# Editor-only: highlight selected / hovered cells on the world map.

SELECT_OUTLINE = "#ffffff"

HOVER_OUTLINE = "#ffcc00"

EMPTY_COLOR = "#1a1a1a"





def territory_ids_in_map_order(grid: list[list[int]]) -> list[int]:

    """Return territory ids in first-seen order scanning the world map (row-major)."""

    seen: set[int] = set()

    ordered: list[int] = []

    for row in grid:

        for territory_id in row:

            if territory_id > 0 and territory_id not in seen:

                seen.add(territory_id)

                ordered.append(territory_id)

    return ordered





def territory_color(territory_id: int) -> str:

    if territory_id <= 0:

        return EMPTY_COLOR

    hue = (territory_id * 0.61803398875) % 1.0

    red, green, blue = colorsys.hls_to_rgb(hue, 0.42, 0.72)

    return f"#{int(red * 255):02x}{int(green * 255):02x}{int(blue * 255):02x}"





def grid_cell_value_color(cell_value: int) -> str:

    """Approximate debug fill color for grid u16[2] (+0x04).



    This is editor visualization only. It does not reproduce in-game rendering and

    does not imply that u16[2] selects a terrain sprite. See SAVE_RESEARCH.md.

    """

    if cell_value <= 0:

        return "#1d6fb8"

    if cell_value < 256:

        return "#2488cc"

    base = cell_value & 0xFF

    if base == 0:

        return "#c8a868"

    if base == 1:

        return "#a89070"

    if base in (2, 3):

        return "#5a8a48"

    if base == 4:

        return "#8a8078"

    return "#b89868"





def map_cell_rect(

    pad: int, x: int, y: int, cell_size: int = MAP_CELL

) -> tuple[int, int, int, int]:

    """Return (x0, y0, x1, y1) with x1/y1 on the shared edge to the next cell."""

    x0 = pad + x * cell_size

    y0 = pad + y * cell_size

    return x0, y0, x0 + cell_size, y0 + cell_size





def draw_world_map_terrain_tiles(
    canvas: tk.Canvas,
    grid: list[list[int]],
    grid_cell_values: list[list[int]],
    tile_library: WorldMapTileLibrary,
    *,
    pad: int,
    cell_size: int = MAP_CELL,
    photo_cache: list[tk.PhotoImage] | None = None,
    soft_borders: bool = True,
) -> None:
    """Draw world-map cells using one reused image per autotile type (high byte 0–5)."""
    height = len(grid)
    width = len(grid[0]) if height else 0
    photos = photo_cache if photo_cache is not None else []
    seen: set[int] = set()

    for y in range(height):
        for x in range(width):
            tid = grid[y][x]
            x0, y0, x1, y1 = map_cell_rect(pad, x, y, cell_size)
            if tid <= 0:
                canvas.create_rectangle(x0, y0, x1, y1, fill=EMPTY_COLOR, outline="")
                continue
            cell_value = grid_cell_values[y][x]
            photo = tile_library.photo_for_cell_value(cell_value)
            if photo is None:
                fill = grid_cell_value_color(cell_value)
                canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline="")
                continue
            high = (cell_value >> 8) & 0xFF
            if high not in seen:
                photos.append(photo)
                seen.add(high)
            canvas.create_image(x0, y0, anchor=tk.NW, image=photo)

    _draw_territory_borders(
        canvas,
        grid,
        pad=pad,
        cell_size=cell_size,
        line_color="#2a2a2a" if soft_borders else BOUNDARY_LINE,
        line_width=1 if soft_borders else BOUNDARY_WIDTH,
    )


def _draw_territory_borders(
    canvas: tk.Canvas,
    grid: list[list[int]],
    *,
    pad: int,
    cell_size: int,
    line_color: str = BOUNDARY_LINE,
    line_width: int = BOUNDARY_WIDTH,
    only_territory_id: int | None = None,
) -> None:
    height = len(grid)
    width = len(grid[0]) if height else 0

    for y in range(height):
        for x in range(width):
            tid = grid[y][x]
            if only_territory_id is not None:
                if tid != only_territory_id:
                    continue
            x0, y0, x1, y1 = map_cell_rect(pad, x, y, cell_size)

            if only_territory_id is not None:
                if x == 0 or grid[y][x - 1] != tid:
                    canvas.create_line(
                        x0, y0, x0, y1, fill=line_color, width=line_width
                    )
                if y == 0 or grid[y - 1][x] != tid:
                    canvas.create_line(
                        x0, y0, x1, y0, fill=line_color, width=line_width
                    )

            if x + 1 < width:
                neighbor = grid[y][x + 1]
                if tid != neighbor:
                    canvas.create_line(
                        x1, y0, x1, y1, fill=line_color, width=line_width
                    )
            else:
                canvas.create_line(x1, y0, x1, y1, fill=line_color, width=line_width)

            if y + 1 < height:
                neighbor = grid[y + 1][x]
                if tid != neighbor:
                    canvas.create_line(
                        x0, y1, x1, y1, fill=line_color, width=line_width
                    )
            else:
                canvas.create_line(x0, y1, x1, y1, fill=line_color, width=line_width)


def draw_territory_selection_outline(
    canvas: tk.Canvas,
    grid: list[list[int]],
    territory_id: int,
    *,
    pad: int,
    cell_size: int = MAP_CELL,
    line_color: str = SELECT_OUTLINE,
    line_width: int = 2,
) -> None:
    """Draw white outline segments on the outer edges of one territory."""
    _draw_territory_borders(
        canvas,
        grid,
        pad=pad,
        cell_size=cell_size,
        line_color=line_color,
        line_width=line_width,
        only_territory_id=territory_id,
    )


def draw_territory_map_cells(

    canvas: tk.Canvas,

    grid: list[list[int]],

    *,

    pad: int,

    cell_size: int = MAP_CELL,
) -> None:
    """Fill cells with territory colors, then internal lines and borders."""
    height = len(grid)
    width = len(grid[0]) if height else 0

    for y in range(height):
        for x in range(width):
            tid = grid[y][x]
            x0, y0, x1, y1 = map_cell_rect(pad, x, y, cell_size)
            fill = EMPTY_COLOR if tid <= 0 else territory_color(tid)
            canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline="")

    for y in range(height):
        for x in range(width):
            tid = grid[y][x]
            x0, y0, x1, y1 = map_cell_rect(pad, x, y, cell_size)

            if x + 1 < width:
                neighbor = grid[y][x + 1]
                if tid > 0 and neighbor > 0 and tid == neighbor:
                    canvas.create_line(
                        x1,
                        y0,
                        x1,
                        y1,
                        fill=INTERNAL_GRID_LINE,
                        width=INTERNAL_LINE_WIDTH,
                    )

            if y + 1 < height:
                neighbor = grid[y + 1][x]
                if tid > 0 and neighbor > 0 and tid == neighbor:
                    canvas.create_line(
                        x0,
                        y1,
                        x1,
                        y1,
                        fill=INTERNAL_GRID_LINE,
                        width=INTERNAL_LINE_WIDTH,
                    )

    _draw_territory_borders(canvas, grid, pad=pad, cell_size=cell_size)


