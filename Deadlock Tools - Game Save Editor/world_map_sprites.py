"""World-map rendering from Deadlock stamp profiles (RE tier D).

The strategic world map does NOT use SPRITELG catalog sprites 101/102 — those
are only referenced from the colony zoom view (deadlock.exe ~0x44A200).

World-map per-cell draw (~0x432F37) uses:
  1. Byte terrain cache @ 0x4DD87C (built by 0x43E296 from profiles @ 0x47F6E0)
  2. Word height cache @ 0x4DD880 (feeds 0x432622 / 0x4327AD palette merge)
  3. Palette blit (0x432064 / 0x432622 / 0x4327AD / 0x432438)
  4. WAIL masked passes when cell+0x06 ≠ 0 (table 0x47950C, SPRITELG @ 0x4A00)
  5. Exposure edge shading from cell+0x04 low byte (0x4329C5 / 0x431484)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageTk

from world_map_blit import BlitMode, rasterize_cell, select_blit_mode
from world_map_terrain_cache import (
    CELL_PX,
    StampProfile,
    build_map_caches,
    byte_to_rgb,
    cell_byte_slice,
    cell_word_slice,
    load_stamp_profiles,
    remap_byte_for_terrain,
)
from world_map_wail import WailMaskAtlas

ROOT = Path(__file__).resolve().parents[1]
SPRITE_DIR = ROOT / "Deadlock Tools - Sprite and Animation Extractor"
if str(SPRITE_DIR) not in sys.path:
    sys.path.insert(0, str(SPRITE_DIR))

from extract_deadlock_sprites import (  # noqa: E402
    load_palette_from_bitmap_resource,
    overlay_exe_palette,
)

MAP_DISPLAY_PX = 22

# Exposure bits (0x438960) — must match deadlock_territory_save.
EXP_W = 0x02
EXP_N = 0x01
EXP_E = 0x08
EXP_S = 0x04

COAST_INDEX = 0x45


def split_grid_u16_2(word: int) -> tuple[int, int]:
    word &= 0xFFFF
    return word & 0xFF, (word >> 8) & 0xFF


class WorldMapSpriteLibrary:
    """Builds the RE terrain byte cache and blits palette indices per map cell."""

    def __init__(self) -> None:
        self.deadlock_dir: Path | None = None
        self._exe: bytes | None = None
        self._palette: list[tuple[int, int, int]] | None = None
        self._profiles: list[StampProfile] | None = None
        self._word_cache: list[int] | None = None
        self._byte_cache: list[int] | None = None
        self._cache_w = 0
        self._cache_h = 0
        self._high_grid: list[list[int]] | None = None
        self._mask_grid: list[list[int]] | None = None
        self._blend_grid: list[list[bool]] | None = None
        self._wail: WailMaskAtlas | None = None
        self._cache_key: tuple | None = None
        self._photo_cache: dict[tuple, ImageTk.PhotoImage] = {}

    def configure(self, deadlock_dir: Path) -> str | None:
        self.clear()
        deadlock_dir = deadlock_dir.resolve()
        exe_path = deadlock_dir / "deadlock.exe"
        if not exe_path.is_file():
            return f"Could not find deadlock.exe in {deadlock_dir}"
        try:
            self._exe = exe_path.read_bytes()
            self._palette = overlay_exe_palette(
                self._exe, load_palette_from_bitmap_resource(self._exe)
            )
            self._profiles = load_stamp_profiles(self._exe)
            self._wail = WailMaskAtlas.from_deadlock_dir(deadlock_dir)
        except Exception as exc:  # pragma: no cover
            self.clear()
            return f"Failed to load world-map terrain data: {exc}"
        self.deadlock_dir = deadlock_dir
        return None

    def clear(self) -> None:
        self.deadlock_dir = None
        self._exe = None
        self._palette = None
        self._profiles = None
        self._word_cache = None
        self._byte_cache = None
        self._cache_w = 0
        self._cache_h = 0
        self._high_grid = None
        self._mask_grid = None
        self._blend_grid = None
        self._wail = None
        self._cache_key = None
        self._photo_cache.clear()

    def set_render_metadata(
        self,
        *,
        mask_grid: list[list[int]] | None = None,
        blend_grid: list[list[bool]] | None = None,
    ) -> None:
        """Attach per-cell WAIL mask indices (+0x06) and territory blend flags (+0x1c)."""
        self._mask_grid = mask_grid
        self._blend_grid = blend_grid
        self._cache_key = None
        self._photo_cache.clear()

    def is_ready(self) -> bool:
        return self._profiles is not None and self._palette is not None

    def ensure_map_cache(
        self,
        grid: list[list[int]],
        grid_cell_values: list[list[int]],
    ) -> None:
        if not self.is_ready() or self._profiles is None:
            return
        height = len(grid)
        width = len(grid[0]) if height else 0
        key = (width, height, tuple(tuple(row) for row in grid_cell_values))
        if self._cache_key == key and self._byte_cache is not None:
            return
        high_grid: list[list[int]] = []
        for y in range(height):
            row: list[int] = []
            for x in range(width):
                if grid[y][x] <= 0:
                    row.append(0)
                else:
                    _, high = split_grid_u16_2(grid_cell_values[y][x])
                    row.append(high)
            high_grid.append(row)
        words, bytes_, cache_w, cache_h = build_map_caches(
            width,
            height,
            high_grid,
            self._profiles,
        )
        self._word_cache = words
        self._byte_cache = bytes_
        self._cache_w = cache_w
        self._cache_h = cache_h
        self._high_grid = high_grid
        self._cache_key = key
        self._photo_cache.clear()

    def photo_for_cell(
        self,
        cell_value: int,
        *,
        display_px: int = MAP_DISPLAY_PX,
        grid: list[list[int]] | None = None,
        grid_cell_values: list[list[int]] | None = None,
        x: int = 0,
        y: int = 0,
    ) -> ImageTk.PhotoImage | None:
        if not self.is_ready() or grid is None or grid_cell_values is None:
            return None
        self.ensure_map_cache(grid, grid_cell_values)
        if self._byte_cache is None:
            return None
        key = (display_px, cell_value & 0xFFFF, x, y)
        cached = self._photo_cache.get(key)
        if cached is not None:
            return cached
        tile = self.compose_cell(
            cell_value,
            grid=grid,
            grid_cell_values=grid_cell_values,
            x=x,
            y=y,
        )
        if display_px != CELL_PX:
            tile = tile.resize((display_px, display_px), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(tile)
        self._photo_cache[key] = photo
        return photo

    def compose_cell(
        self,
        cell_value: int,
        *,
        grid: list[list[int]] | None = None,
        grid_cell_values: list[list[int]] | None = None,
        x: int = 0,
        y: int = 0,
    ) -> Image.Image:
        exposure, _high = split_grid_u16_2(cell_value)
        if grid is not None and grid_cell_values is not None:
            self.ensure_map_cache(grid, grid_cell_values)
        if (
            self._byte_cache is not None
            and self._word_cache is not None
            and self._palette is not None
            and self._high_grid is not None
        ):
            byte_indices = cell_byte_slice(self._byte_cache, self._cache_w, x, y)
            word_indices = cell_word_slice(self._word_cache, self._cache_w, x, y)
            high = (
                self._high_grid[y][x]
                if y < len(self._high_grid) and x < len(self._high_grid[0])
                else 3
            )
            mask_index = 0
            if self._mask_grid and y < len(self._mask_grid) and x < len(self._mask_grid[0]):
                mask_index = self._mask_grid[y][x]
            territory_blend = False
            if self._blend_grid and y < len(self._blend_grid) and x < len(self._blend_grid[0]):
                territory_blend = self._blend_grid[y][x]
            mode = select_blit_mode(
                territory_blend=territory_blend,
                mask_index=mask_index,
            )
            mask_slice = None
            if mode in (BlitMode.WAIL, BlitMode.WAIL_BLEND) and self._wail is not None:
                mask_slice = self._wail.mask_slice(mask_index, parity=(x + y) & 1)
            palette_indices = rasterize_cell(
                byte_indices,
                word_indices,
                mode=mode,
                mask_slice=mask_slice,
            )
            pal = self._palette
            img = Image.new("RGBA", (CELL_PX, CELL_PX))
            px = img.load()
            for j in range(CELL_PX):
                for i in range(CELL_PX):
                    raw = remap_byte_for_terrain(palette_indices[j * CELL_PX + i], high)
                    pal_idx = raw & 0xFF
                    px[i, j] = byte_to_rgb(pal_idx, pal) + (255,)
            if high != 0 and grid is not None and mode == BlitMode.PLAIN:
                self._apply_coast_fringe(img, x, y, grid, self._high_grid, pal)
        else:
            img = self._fallback_tile(_high)

        if exposure:
            self._apply_exposure_overlay(img, exposure, self._palette or [])
        return img

    @staticmethod
    def _fallback_tile(high: int) -> Image.Image:
        colors = {
            0: (36, 111, 184),
            1: (58, 82, 48),
            2: (42, 98, 52),
            3: (196, 176, 132),
            4: (128, 122, 118),
            5: (148, 146, 152),
        }
        rgb = colors.get(high, (120, 120, 120))
        return Image.new("RGBA", (CELL_PX, CELL_PX), rgb + (255,))

    @staticmethod
    def _apply_coast_fringe(
        target: Image.Image,
        x: int,
        y: int,
        grid: list[list[int]],
        high_grid: list[list[int]],
        palette: list[tuple[int, int, int]],
    ) -> None:
        height = len(grid)
        width = len(grid[0]) if height else 0
        surf = palette[COAST_INDEX] if COAST_INDEX < len(palette) else (120, 185, 228)
        mid = palette[0x43] if 0x43 < len(palette) else (56, 120, 178)
        deep = palette[0x40] if 0x40 < len(palette) else (28, 86, 158)

        def neighbor_is_ocean(dx: int, dy: int) -> bool:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                return True
            if grid[ny][nx] <= 0:
                return True
            return high_grid[ny][nx] == 0

        def blend_edge(facing: str) -> None:
            px = target.load()
            colors = (surf, mid, deep)
            if facing in ("w", "e"):
                cols = (0, 1, 2) if facing == "w" else (CELL_PX - 1, CELL_PX - 2, CELL_PX - 3)
                for j in range(CELL_PX):
                    for k, ci in enumerate(cols):
                        if k >= len(colors):
                            break
                        r, g, b, a = px[ci, j]
                        cr, cg, cb = colors[k]
                        px[ci, j] = (
                            (r + cr * 2) // 3,
                            (g + cg * 2) // 3,
                            (b + cb * 2) // 3,
                            a,
                        )
            else:
                rows = (0, 1, 2) if facing == "n" else (CELL_PX - 1, CELL_PX - 2, CELL_PX - 3)
                for i in range(CELL_PX):
                    for k, ri in enumerate(rows):
                        if k >= len(colors):
                            break
                        r, g, b, a = px[i, ri]
                        cr, cg, cb = colors[k]
                        px[i, ri] = (
                            (r + cr * 2) // 3,
                            (g + cg * 2) // 3,
                            (b + cb * 2) // 3,
                            a,
                        )

        if neighbor_is_ocean(-1, 0):
            blend_edge("w")
        if neighbor_is_ocean(1, 0):
            blend_edge("e")
        if neighbor_is_ocean(0, -1):
            blend_edge("n")
        if neighbor_is_ocean(0, 1):
            blend_edge("s")

    @staticmethod
    def _apply_exposure_overlay(
        target: Image.Image,
        exposure: int,
        palette: list[tuple[int, int, int]],
    ) -> None:
        px = target.load()
        shadow = palette[0x31] if len(palette) > 0x31 else (48, 42, 28)
        shadow = tuple(c // 2 for c in shadow)
        width = 2
        for j in range(CELL_PX):
            for i in range(CELL_PX):
                if exposure & EXP_W and i < width:
                    pass
                elif exposure & EXP_E and i >= CELL_PX - width:
                    pass
                elif exposure & EXP_N and j < width:
                    pass
                elif exposure & EXP_S and j >= CELL_PX - width:
                    pass
                else:
                    continue
                r, g, b, a = px[i, j]
                px[i, j] = (
                    (r + shadow[0]) // 2,
                    (g + shadow[1]) // 2,
                    (b + shadow[2]) // 2,
                    a,
                )


def build_world_map_render_grids(
    save_data: bytes,
    layout,
    grid: list[list[int]],
) -> tuple[list[list[int]], list[list[bool]]]:
    """Build per-cell WAIL mask indices (+0x06) and territory blend flags (+0x1c)."""
    sys.path.insert(0, str(ROOT / "DEPRECATED - Deadlock Tools - Territory Boundary Editor"))
    from deadlock_territory_save import GRID_CELL_BYTES, STORED_RECORD

    height = len(grid)
    width = len(grid[0]) if height else 0
    blend_by_tid: dict[int, bool] = {}
    for index in range(1, layout.territory_count + 1):
        rec_off = layout.territory_offset + (index - 1) * STORED_RECORD
        flag = save_data[rec_off + 0x1C] & 0x03
        territory_id = save_data[rec_off + 0x1A] | (save_data[rec_off + 0x1B] << 8)
        blend_by_tid[territory_id] = flag != 0

    mask_grid: list[list[int]] = []
    blend_grid: list[list[bool]] = []
    for y in range(height):
        mask_row: list[int] = []
        blend_row: list[bool] = []
        for x in range(width):
            tid = grid[y][x]
            if tid <= 0:
                mask_row.append(0)
                blend_row.append(False)
                continue
            cell_off = layout.grid_offset + (y * width + x) * GRID_CELL_BYTES
            mask_row.append(save_data[cell_off + 6])
            blend_row.append(blend_by_tid.get(tid, False))
        mask_grid.append(mask_row)
        blend_grid.append(blend_row)
    return mask_grid, blend_grid


def build_tile_manifest_from_save(save_path: Path) -> dict[str, int]:
    sys.path.insert(0, str(ROOT / "DEPRECATED - Deadlock Tools - Territory Boundary Editor"))
    from deadlock_territory_save import LoadedSave, read_grid_cell_value

    save = LoadedSave.from_path(save_path)
    words: set[int] = set()
    for y, row in enumerate(save.grid):
        for x, tid in enumerate(row):
            if tid <= 0:
                continue
            words.add(read_grid_cell_value(save.data, save.layout, x, y))
    return {f"{word:04X}": word for word in sorted(words)}
