"""Per-pixel compositing ports of deadlock.exe world-map blit helpers.

Simplified from the scanline span plotter at 0x454D8D — we target a fixed 32×32
cell buffer instead of the game's diamond clip tables.
"""
from __future__ import annotations

from enum import Enum

from world_map_terrain_cache import CELL_PX


class BlitMode(str, Enum):
    PLAIN = "plain"  # 0x432064 — byte cache only
    BLEND = "blend"  # 0x432622 — word low-byte merged with byte cache
    WAIL = "wail"  # 0x432438 — WAIL mask overrides byte cache
    WAIL_BLEND = "wail_blend"  # 0x4327AD — WAIL mask with word-style merge


def merge_word_palette(word_byte: int, param: int = 2) -> int:
    """Port of the (byte & 0xF8) | min((byte & 7) + param, 7) merge in 0x432622."""
    capped = 7
    sub = (word_byte & 0x07) + param
    if sub >= capped:
        sub = capped
    return (word_byte & 0xF8) | sub


def compose_palette_index(
    mode: BlitMode,
    *,
    byte_val: int,
    word_val: int,
    mask_val: int = 0,
    blend_param: int = 2,
) -> int:
    """Return the palette index chosen for one cache pixel."""
    if mode == BlitMode.PLAIN:
        return byte_val & 0xFF

    word_byte = word_val & 0xFF

    if mode == BlitMode.BLEND:
        return merge_word_palette(word_byte, blend_param)

    if mode == BlitMode.WAIL:
        if mask_val != 0:
            return mask_val & 0xFF
        return byte_val & 0xFF

    # WAIL_BLEND
    source = mask_val if mask_val != 0 else byte_val
    return merge_word_palette(source & 0xFF, blend_param)


def select_blit_mode(*, territory_blend: bool, mask_index: int) -> BlitMode:
    """Mirror the branch tree at 0x432FDF (cell+0x06 and territory+0x1c)."""
    if mask_index != 0:
        return BlitMode.WAIL_BLEND if territory_blend else BlitMode.WAIL
    if territory_blend:
        return BlitMode.BLEND
    return BlitMode.PLAIN


def rasterize_cell(
    byte_slice: list[int],
    word_slice: list[int],
    *,
    mode: BlitMode,
    mask_slice: list[int] | None = None,
    blend_param: int = 2,
) -> list[int]:
    """Build a 32×32 palette-index raster for one map cell."""
    count = CELL_PX * CELL_PX
    if mask_slice is None:
        mask_slice = [0] * count
    out: list[int] = []
    for idx in range(count):
        out.append(
            compose_palette_index(
                mode,
                byte_val=byte_slice[idx],
                word_val=word_slice[idx],
                mask_val=mask_slice[idx],
                blend_param=blend_param,
            )
        )
    return out
