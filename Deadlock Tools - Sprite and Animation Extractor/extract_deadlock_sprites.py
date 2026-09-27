#!/usr/bin/env python3
"""
Deadlock Sprite and Animation Extractor

Copyright (c) 2026 Josh Burns <deadlock-game-tools@joshburns.me>
https://sourceforge.net/projects/deadlock-game-tools

Licensed under the MIT License (see LICENSE.txt file).

This program extracts sprites and animations from the 1996 game Deadlock.

Catalog at VA 0x479470, 12 bytes per sprite:
  +0  pointer to frame chain (16-byte records, ends at width==0)
  +4  optional animation script (0 if none)
  +8  word: default frame delay (copied to anim+0x20 / +0x1e timer)
  +0xA word: flags

Frame record (16 bytes):
  int16 hotspot_x, hotspot_y, width, height
  uint32 runtime_pixel_ptr (0 on disk)
  uint32 file_offset into SPRITELG.DAT

Building sprites (common 11-frame layout) are layered:
  [0]     still image (game option: animations off / Force Small Sprites)
  [1]     anim base (persistent underlay)
  [2..n-2] overlays composited onto the base
  [n-1]   damaged
  Overlay paste offset inside the base = (overlay_hotspot - base_hotspot),
  because both are drawn with their hotspot on the same world point.

Flat sprites (units, etc.) animate whole frames in chain order.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from PIL import Image

CATALOG_VA = 0x479470
FRAME_STRIDE = 0x10
CATALOG_STRIDE = 12
BITMAP_RES_ID = 55
TRANSPARENT = {0, 207}

# Opcode immediate sizes in bytes after the opcode word itself.
# None = variable / special.
OPCODE_SKIP = {
    0: 0,  # fall through (end-of-step)
    1: 4,  # GOTO dword — handled specially
    2: 2,  # index into word regs, then call helper (uses more; see walk)
    3: 2 + 4,  # word + dword loop
    4: 2 + 2 + 2 + 4,
    5: 2 + 2 + 2 + 4,
    6: 2 + 2,  # set reg
    7: 2 + 2 + 2,  # random range into reg
    8: 0,  # destroy
    9: 2,  # set delay
    10: 2,  # delay from reg
    11: 0,  # sound cues
}


def pe_sections(exe: bytes) -> list[tuple[int, int, int, int]]:
    pe = struct.unpack_from("<I", exe, 0x3C)[0]
    nsec = struct.unpack_from("<H", exe, pe + 6)[0]
    opt = struct.unpack_from("<H", exe, pe + 20)[0]
    sec = pe + 24 + opt
    out = []
    for i in range(nsec):
        s = sec + i * 40
        vsz, va, rsz, raw = struct.unpack_from("<IIII", exe, s + 8)
        out.append((va, vsz, raw, rsz))
    return out


def va_to_off(exe: bytes, va: int, sections: list[tuple[int, int, int, int]] | None = None) -> int:
    rva = va - 0x400000
    secs = sections or pe_sections(exe)
    for va0, vsz, raw, rsz in secs:
        if va0 <= rva < va0 + max(vsz, rsz):
            return raw + (rva - va0)
    raise ValueError(f"VA {va:#x} not in any section")


def rva_to_off(exe: bytes, rva: int) -> int:
    return va_to_off(exe, 0x400000 + rva)


def load_palette_from_bitmap_resource(exe: bytes) -> list[tuple[int, int, int]]:
    pe = struct.unpack_from("<I", exe, 0x3C)[0]
    rsrc_rva = struct.unpack_from("<I", exe, pe + 136)[0]
    root = rva_to_off(exe, rsrc_rva)

    def dir_entries(dir_off: int):
        named, ids = struct.unpack_from("<HH", exe, dir_off + 12)
        for i in range(named + ids):
            name, offset = struct.unpack_from("<II", exe, dir_off + 16 + i * 8)
            yield name, offset & 0x7FFFFFFF, bool(offset & 0x80000000)

    def find_bitmap(res_id: int) -> tuple[int, int]:
        for tname, toff, tisdir in dir_entries(root):
            if tname != 2 or not tisdir:
                continue
            for nname, noff, nisdir in dir_entries(root + toff):
                if nname != res_id or not nisdir:
                    continue
                for _, loff, lisdir in dir_entries(root + noff):
                    if lisdir:
                        continue
                    data_rva, size = struct.unpack_from("<II", exe, root + loff)
                    return data_rva, size
        raise LookupError(f"BITMAP resource {res_id} not found")

    data_rva, size = find_bitmap(BITMAP_RES_ID)
    data = exe[rva_to_off(exe, data_rva) : rva_to_off(exe, data_rva) + size]
    bi_size = struct.unpack_from("<I", data, 0)[0]
    bpp = struct.unpack_from("<H", data, 14)[0]
    if bpp != 8:
        raise ValueError(f"expected 8-bit bitmap, got bpp={bpp}")
    clr_used = struct.unpack_from("<I", data, 32)[0] or 256
    pal = data[bi_size : bi_size + clr_used * 4]
    colors: list[tuple[int, int, int]] = []
    for i in range(256):
        if i < clr_used:
            b, g, r = pal[i * 4], pal[i * 4 + 1], pal[i * 4 + 2]
            colors.append((r, g, b))
        else:
            colors.append((0, 0, 0))
    return colors


def overlay_exe_palette(exe: bytes, colors: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    off = va_to_off(exe, 0x4AFBF0)
    out = list(colors)
    for i in range(256):
        b, g, r = exe[off + i * 4 : off + i * 4 + 3]
        if r or g or b:
            out[i] = (r, g, b)
    return out


def read_catalog(exe: bytes) -> list[tuple[int, int, int]]:
    """Return [(frame_chain_va, script_va_or_0, delay_word), ...]."""
    sections = pe_sections(exe)
    off = va_to_off(exe, CATALOG_VA, sections)
    out: list[tuple[int, int, int]] = []
    for i in range(2000):
        ptr, script, rest = struct.unpack_from("<III", exe, off + i * CATALOG_STRIDE)
        if not (0x470000 <= ptr < 0x4A8000):
            break
        delay = rest & 0xFFFF
        out.append((ptr, script, delay))
    return out


def iter_frames(exe: bytes, chain_va: int) -> list[tuple[int, int, int, int, int]]:
    frames = []
    va = chain_va
    sections = pe_sections(exe)
    for _ in range(512):
        off = va_to_off(exe, va, sections)
        hx, hy, w, h = struct.unpack_from("<hhhh", exe, off)
        file_off = struct.unpack_from("<I", exe, off + 0xC)[0]
        if w == 0:
            break
        if w < 0 or h < 0 or w > 1024 or h > 1024:
            break
        frames.append((hx, hy, w, h, file_off))
        va += FRAME_STRIDE
    return frames


def is_chain_padding_frame(w: int, h: int) -> bool:
    """True for 1x1 catalog chain slots that pad fixed-index image banks."""
    return w * h <= 1


def without_padding_frames(indices: list[int], frames: list) -> list[int]:
    return [i for i in indices if not is_chain_padding_frame(frames[i][2], frames[i][3])]


def _script_reader(exe: bytes) -> tuple:
    """Shared helpers for walking animation bytecode."""
    sections = pe_sections(exe)

    def read_u16(va: int) -> int:
        return struct.unpack_from("<H", exe, va_to_off(exe, va, sections))[0]

    def read_u32(va: int) -> int:
        return struct.unpack_from("<I", exe, va_to_off(exe, va, sections))[0]

    def is_code_ptr(va: int) -> bool:
        return 0x004A0000 <= va <= 0x004BFFFF

    def read_ptr_table(ip: int) -> tuple[list[int], int]:
        ptrs: list[int] = []
        while True:
            try:
                ptr = read_u32(ip)
            except ValueError:
                break
            if not is_code_ptr(ptr):
                break
            ptrs.append(ptr)
            ip += 4
        return ptrs, ip

    return read_u16, read_u32, is_code_ptr, read_ptr_table


def _branch_sets_disjoint(parts: list[list[int]]) -> bool:
    """True when op-2 branches look like alternate variants, not phases."""
    sets = [set(p) for p in parts if p]
    if len(sets) < 2:
        return False
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            overlap = len(sets[i] & sets[j])
            if overlap == 0:
                continue
            smaller = min(len(sets[i]), len(sets[j]))
            if smaller and overlap > smaller // 4:
                return False
    return True


def script_animation_segments(
    exe: bytes, script_va: int, frame_count: int, max_frames: int = 256
) -> list[list[int]]:
    """Return one or more frame-index sequences from an animation script.

    Scripts with opcode-2 variant tables (e.g. selection highlight on/off)
    yield multiple segments when their branches use disjoint frame banks.
    """
    if not script_va:
        return []
    read_u16, read_u32, _is_code_ptr, read_ptr_table = _script_reader(exe)

    def walk_fragment(ip: int, seen: set[int], depth: int = 0) -> list[int] | None:
        if depth > 32:
            return None
        seq: list[int] = []
        steps = 0
        while steps < 2000 and len(seq) < max_frames:
            if ip in seen:
                return seq
            seen.add(ip)
            steps += 1
            try:
                w = read_u16(ip)
            except ValueError:
                return None
            ip += 2
            if w & 0x8000:
                op = w & 0xFF
                if op == 1 or op == 8:
                    return seq
                if op == 0:
                    continue
                if op == 2:
                    try:
                        ip += 2
                        ptrs, ip = read_ptr_table(ip)
                    except ValueError:
                        return None
                    if ptrs and ip == ptrs[0]:
                        gaps = [ptrs[i + 1] - ptrs[i] for i in range(len(ptrs) - 1)]
                        if gaps and max(gaps) <= 4:
                            sub = walk_fragment(ptrs[0], set(), depth + 1)
                            if sub is None:
                                return None
                            seq.extend(sub)
                        else:
                            for ptr in ptrs:
                                sub = walk_fragment(ptr, set(), depth + 1)
                                if sub is None:
                                    return None
                                seq.extend(sub)
                    continue
                skip = OPCODE_SKIP.get(op)
                if skip is None:
                    return None
                ip += skip
                continue
            if w >= frame_count:
                return None
            seq.append(w)
        return seq

    def expand_op2_branches(ptrs: list[int]) -> list[list[int]]:
        parts: list[list[int]] = []
        for ptr in ptrs:
            sub = walk_fragment(ptr, set())
            if sub is None:
                return []
            if sub:
                parts.append(sub)
        if not parts:
            return []
        if len(parts) >= 2 and _branch_sets_disjoint(parts):
            return [p for p in parts if len(p) >= 2]
        combined: list[int] = []
        for p in parts:
            combined.extend(p)
        return [combined] if len(combined) >= 2 else []

    # Many unit scripts begin with op-7 setup then an op-2 variant table.
    ip = script_va
    for _ in range(4):
        try:
            w = read_u16(ip)
        except ValueError:
            break
        if w & 0x8000 and (w & 0xFF) == 7:
            ip += 2 + OPCODE_SKIP[7]
        else:
            break

    try:
        w = read_u16(ip)
    except ValueError:
        w = 0
    if w & 0x8000 and (w & 0xFF) == 2:
        ip += 2
        try:
            ip += 2
            ptrs, _after = read_ptr_table(ip)
        except ValueError:
            ptrs = []
        if len(ptrs) >= 2:
            return expand_op2_branches(ptrs)

    single = walk_fragment(script_va, set())
    if single is None or len(single) < 2:
        return []
    return [single]


def script_frame_sequence(exe: bytes, script_va: int, frame_count: int, max_frames: int = 256) -> list[int] | None:
    """Walk an anim script and collect frame indices until loop/destroy."""
    segments = script_animation_segments(exe, script_va, frame_count, max_frames)
    if not segments:
        return None
    if len(segments) == 1:
        return segments[0]
    combined: list[int] = []
    for seg in segments:
        combined.extend(seg)
    return combined or None


def is_layered_building(frames: list) -> bool:
    """True for the common building layout with small overlay cells.

    [0] still (animations off)
    [1] anim base
    [2 .. n-2] overlays composited onto the base
    [n-1] damaged
    """
    n = len(frames)
    if n < 4:
        return False
    base_w, base_h = frames[1][2], frames[1][3]
    base_area = base_w * base_h
    if base_area <= 0:
        return False
    overlays = frames[2:-1]
    if not overlays:
        return False
    if not all(f[2] * f[3] < base_area // 2 for f in overlays):
        return False
    for i in (0, n - 1):
        a = frames[i][2] * frames[i][3]
        if a < base_area // 2:
            return False
    return True


def is_classic_building_layout(frames: list) -> bool:
    """11-frame building: still at [0], damaged at [n-1], similar full-building size."""
    n = len(frames)
    if n != 11:
        return False
    a0 = frames[0][2] * frames[0][3]
    an = frames[-1][2] * frames[-1][3]
    if a0 <= 0 or an <= 0:
        return False
    return min(a0, an) / max(a0, an) >= 0.6


def is_dual_building_layout(frames: list) -> bool:
    """27-frame building with two overlay animation banks."""
    return len(frames) == 27


def is_extended_layered_building(frames: list) -> bool:
    """14-frame layered building: still at [0], base at [1], overlays [2..n-1].

    Unlike the 11-frame layout there is no separate damaged still at the end.
    Overlays may be large (most of the base area) but still smaller than the base.
    """
    n = len(frames)
    if n != 14:
        return False
    still_area = frames[0][2] * frames[0][3]
    base_area = frames[1][2] * frames[1][3]
    if still_area <= 0 or base_area <= 0:
        return False
    if base_area < still_area // 2:
        return False
    overlays = frames[2:]
    if len(overlays) < 2:
        return False
    return all(f[2] * f[3] <= base_area for f in overlays)


def is_still_base_extended_layered_building(frames: list) -> bool:
    """14-frame layered building with the anim base at [0].

    [0] still / anim base (composited under overlays)
    [1] small unused cell
    [2 .. n-1] building-aligned overlay layers on frame 0
    """
    n = len(frames)
    if n != 14:
        return False
    still_area = frames[0][2] * frames[0][3]
    if still_area <= 0:
        return False
    if frames[1][2] * frames[1][3] >= still_area // 2:
        return False
    overlays = frames[2:]
    if len(overlays) < 2:
        return False
    bx, bw = frames[0][0], frames[0][2]
    return all(abs(f[0] - bx) <= 2 and f[2] >= bw * 0.9 for f in overlays)


def is_compact_layered_building(frames: list) -> bool:
    """Layered building without a separate damaged frame at the end.

    [0] still / anim base (composited under overlays)
    [1] duplicate base cell (unused in playback)
    [2 .. n-1] small overlays composited onto frame 0
    """
    n = len(frames)
    if n < 4 or n in (11, 27):
        return False
    base_w, base_h = frames[0][2], frames[0][3]
    base_area = base_w * base_h
    if base_area <= 0:
        return False
    if frames[1][2] != base_w or frames[1][3] != base_h:
        return False
    overlays = frames[2:]
    if len(overlays) < 2:
        return False
    return all(f[2] * f[3] < base_area // 2 for f in overlays)


def overlay_ping_pong(lo: int, hi: int) -> list[int]:
    if hi < lo:
        return []
    fwd = list(range(lo, hi + 1))
    if hi <= lo:
        return fwd
    return fwd + list(range(hi - 1, lo, -1))


def overlay_indices_from_script(scripted: list[int] | None, lo: int, hi: int) -> list[int]:
    """Overlay playback order for layered buildings.

    Building scripts expose alternate entry points for game state, but playback
    is always a ping-pong across the overlay bank.
    """
    del scripted
    return overlay_ping_pong(lo, hi)


def layered_static_frame_indices(frame_count: int, segments: list[tuple[str, list[int], int | None]]) -> list[int]:
    """Still/damaged frames exported as static images for layered buildings."""
    if not segments or segments[0][0] != "layered":
        return []
    if frame_count == 27 and len(segments) >= 2:
        return [0, 18, frame_count - 1]
    base = segments[0][2]
    if base == 0:
        # Frame 0 is the anim underlay; frame 1 is a spare duplicate base cell.
        # Neither is exported as a separate static.
        return []
    if base == 1 and frame_count == 14:
        # Extended layout: still at 0, base at 1, overlays through last frame.
        return [0]
    if frame_count >= 4:
        return [0, frame_count - 1]
    return []


def overlay_paste_xy(base: tuple, overlay: tuple) -> tuple[int, int]:
    """Pixel offset of overlay top-left inside the base image.

    Both frames are drawn with their hotspot on the same world point, so:
        paste = (overlay_hotspot - base_hotspot)
    """
    bx, by = base[0], base[1]
    ox, oy = overlay[0], overlay[1]
    return ox - bx, oy - by


def layered_overlay_sequence(exe: bytes, script_va: int, frame_count: int) -> list[int]:
    """Overlay frame indices for a layered building.

    Building anim scripts ping-pong the overlay bank (2 .. n-2). Still (0),
    base (1), and damaged (n-1) are never themselves the drawn anim cell.
    """
    del exe, script_va  # layout is fixed for this sprite class
    lo, hi = 2, frame_count - 2
    return list(range(lo, hi + 1)) + list(range(hi - 1, lo, -1))


def animation_plan(
    exe: bytes, script_va: int, delay: int, frames: list, *, force_static: bool = False
) -> list[tuple[str, list[int], int | None]]:
    """Return animation segments as (mode, indices, base_index) tuples.

    mode:
      'layered' — composite frames[base] under each overlay index
      'flat'    — each index is a full frame

    Empty list means no animation (all frames are static).
    """
    n = len(frames)
    if n == 0 or force_static:
        return []

    scripted_segments = script_animation_segments(exe, script_va, n) if script_va else []

    # 27-frame buildings carry two overlay animation banks.
    # Both animations composite onto the same anim base (frame 1); only the
    # overlay bank differs (frames 2-17 vs 20..n-2).
    if script_va and is_dual_building_layout(frames):
        seg1 = overlay_indices_from_script(None, 2, 17)
        seg2 = overlay_indices_from_script(None, 20, n - 2)
        segments: list[tuple[str, list[int], int | None]] = []
        if len(seg1) >= 2:
            segments.append(("layered", seg1, 1))
        if len(seg2) >= 2:
            segments.append(("layered", seg2, 1))
        if segments:
            return segments

    # 11-frame (and similar) layered buildings: overlays may be large relative
    # to the base; compositing is still correct when a script is present.
    if script_va and (
        is_classic_building_layout(frames)
        or is_layered_building(frames)
    ):
        anim = overlay_indices_from_script(None, 2, n - 2)
        if len(anim) >= 2:
            return [("layered", anim, 1)]

    # Compact layered buildings (e.g. 10-frame): frame 0 is the underlay,
    # overlays run through the last frame (no separate damaged still).
    if script_va and is_compact_layered_building(frames):
        anim = overlay_indices_from_script(None, 2, n - 1)
        if len(anim) >= 2:
            return [("layered", anim, 0)]

    # 14-frame layered buildings: still at 0, anim base at 1, overlays [2..n-1].
    if script_va and is_extended_layered_building(frames):
        anim = overlay_indices_from_script(None, 2, n - 1)
        if len(anim) >= 2:
            return [("layered", anim, 1)]

    # 14-frame variant: anim base at 0, small spare at 1, overlays [2..n-1].
    if script_va and is_still_base_extended_layered_building(frames):
        anim = overlay_indices_from_script(None, 2, n - 1)
        if len(anim) >= 2:
            return [("layered", anim, 0)]

    # Flat scripted animation (units, effects, etc.). Frame sizes may vary.
    # Opcode-2 variant tables can yield multiple disjoint segments.
    flat_segments = [("flat", anim, None) for anim in scripted_segments if len(anim) >= 2]
    if flat_segments:
        return flat_segments

    return []


def layered_canvas_bounds(base: tuple, overlays: list) -> tuple[int, int, int, int]:
    """Bounding box in hotspot-space covering the base and all overlays.

    Returns (origin_x, origin_y, width, height) where origin is the top-left
    of the canvas in the same coordinate system as frame hotspots (hotspot at 0,0).
    """
    pieces = [base, *overlays]
    min_x = min(f[0] for f in pieces)
    min_y = min(f[1] for f in pieces)
    max_x = max(f[0] + f[2] for f in pieces)
    max_y = max(f[1] + f[3] for f in pieces)
    return min_x, min_y, max_x - min_x, max_y - min_y


def composite_layered_frame(
    dat: bytes,
    frames: list,
    base_index: int,
    overlay_index: int,
    palette: list[tuple[int, int, int]],
    transparent: set[int],
    canvas: tuple[int, int, int, int] | None = None,
) -> Image.Image:
    """Composite overlay onto base. Expands the canvas when overlays stick out."""
    base = frames[base_index]
    overlay = frames[overlay_index]
    if canvas is None:
        canvas = layered_canvas_bounds(base, [overlay])
    origin_x, origin_y, cw, ch = canvas

    _, _, bw, bh, boff = base
    _, _, ow, oh, ooff = overlay
    base_img = pixels_to_rgba(dat[boff : boff + bw * bh], bw, bh, palette, transparent)
    over_img = pixels_to_rgba(dat[ooff : ooff + ow * oh], ow, oh, palette, transparent)

    out = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    out.paste(base_img, (base[0] - origin_x, base[1] - origin_y), base_img)
    out.paste(over_img, (overlay[0] - origin_x, overlay[1] - origin_y), over_img)
    return out


def pixels_to_rgba(
    pixels: bytes, width: int, height: int, palette: list[tuple[int, int, int]], transparent: set[int]
) -> Image.Image:
    img = Image.new("RGBA", (width, height))
    px = img.load()
    for y in range(height):
        row = y * width
        for x in range(width):
            idx = pixels[row + x]
            r, g, b = palette[idx]
            a = 0 if idx in transparent else 255
            px[x, y] = (r, g, b, a)
    return img


def write_gif(
    path: Path,
    frames_rgba: list[Image.Image],
    delay_cs: int,
    palette: list[tuple[int, int, int]],
) -> None:
    """Write an animated GIF using the exact game palette for color consistency."""
    if not frames_rgba:
        return

    # Build the exact 256-color palette bytes
    palette_bytes = bytearray()
    for r, g, b in palette:
        palette_bytes.extend((r, g, b))
    if len(palette_bytes) < 768:
        palette_bytes.extend([0] * (768 - len(palette_bytes)))

    pal_img = Image.new("P", (1, 1))
    pal_img.putpalette(palette_bytes)

    # We use index 0 as the transparent index (it is black and the most commonly used transparent index in the data)
    trans_idx = 0

    synced: list[Image.Image] = []
    for fr in frames_rgba:
        # fr is RGBA; pixels with alpha=0 are the transparent ones (originally indices 0 or 207)
        # Composite onto black so transparent regions become the transparent color
        bg = Image.new("RGB", fr.size, (0, 0, 0))
        bg.paste(fr.convert("RGB"), mask=fr.split()[3])

        # Quantize to the exact game palette (no dithering for clean pixel art)
        p_frame = bg.quantize(palette=pal_img, dither=0)

        # Force truly transparent pixels (from the original alpha channel) to trans_idx
        alpha = fr.split()[3]
        trans_mask = alpha.point(lambda a: 255 if a == 0 else 0)
        trans_solid = Image.new("P", fr.size, trans_idx)
        trans_solid.putpalette(palette_bytes)
        p_frame.paste(trans_solid, mask=trans_mask)

        synced.append(p_frame)

    if synced:
        synced[0].save(
            path,
            save_all=True,
            append_images=synced[1:],
            loop=0,
            duration=max(delay_cs, 1) * 10,  # PIL wants milliseconds
            transparency=trans_idx,
            disposal=2,
            optimize=False,
        )


def default_output_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "extracted_deadlock_sprites"
    return Path(__file__).resolve().parent / "extracted_deadlock_sprites"


def resolve_game_paths(
    deadlock_path: Path | None,
    exe_path: Path | None,
    dat_path: Path | None,
) -> tuple[Path, Path]:
    if exe_path is not None and dat_path is not None:
        return exe_path, dat_path
    if deadlock_path is not None:
        return (
            exe_path if exe_path is not None else (deadlock_path / "deadlock.exe"),
            dat_path if dat_path is not None else (deadlock_path / "SPRITELG.DAT"),
        )
    raise ValueError("Provide a Deadlock folder, or both deadlock.exe and SPRITELG.DAT")


def parse_id_list(text: str) -> list[int]:
    ids: list[int] = []
    for raw in text.replace(";", ",").replace(" ", ",").split(","):
        token = raw.strip()
        if not token:
            continue
        ids.append(int(token, 0))
    return ids


def extract(
    exe_path: Path,
    dat_path: Path,
    out_dir: Path,
    limit: int | None = None,
    sprite_ids: list[int] | None = None,
    animations_only: bool = False,
    static_only: bool = False,
    gif_delay_cs: int | None = None,
    forced_static_ids: set[int] | None = None,
    write_frames_txt: bool = False,
    progress=None,
) -> int:
    def emit(message: str) -> None:
        print(message)
        if progress is not None:
            progress(message)

    exe = exe_path.read_bytes()
    dat = dat_path.read_bytes()
    palette = overlay_exe_palette(exe, load_palette_from_bitmap_resource(exe))
    catalog = read_catalog(exe)
    out_dir.mkdir(parents=True, exist_ok=True)

    tsv_rows: list[tuple[str, str, str, str]] = []
    gif_count = 0
    ids = sprite_ids if sprite_ids is not None else range(len(catalog))
    for sid in ids:
        if sid < 0 or sid >= len(catalog):
            continue
        chain_va, script_va, delay = catalog[sid]
        frames = iter_frames(exe, chain_va)
        if not frames:
            continue
        forced = bool(forced_static_ids and sid in forced_static_ids)
        segments = animation_plan(exe, script_va, delay, frames, force_static=forced)
        is_animated = any(len(anim) >= 2 for _, anim, _ in segments)
        has_layered = any(mode == "layered" for mode, _, _ in segments)
        used_anim_frames: set[int] = set()
        for mode, anim, base_index in segments:
            used_anim_frames.update(anim)
            if mode == "layered" and base_index is not None:
                used_anim_frames.add(base_index)

        if animations_only and not is_animated:
            continue
        # Layered buildings still export still/damaged static frames in static-only mode.
        if static_only and is_animated and not has_layered:
            continue

        emit(f"Sprite {sid:04d}")
        if write_frames_txt:
            primary_mode = segments[0][0] if segments else "flat"
            primary_anim = segments[0][1] if segments else []
            primary_base = segments[0][2] if segments else None
            meta_lines = [
                f"frames\t{len(frames)}",
                f"script\t{script_va:#x}" if script_va else "script\t0",
                f"delay_word\t{delay}",
                f"anim_mode\t{primary_mode}",
                f"anim_base\t{primary_base}" if primary_base is not None else "anim_base\t-",
                f"anim_indices\t{','.join(map(str, primary_anim))}",
                f"anim_segments\t{len(segments)}",
            ]
            for seg_i, (mode, anim, base_index) in enumerate(segments, start=1):
                meta_lines.append(
                    f"anim_seg_{seg_i}\t{mode}\tbase={base_index if base_index is not None else '-'}"
                    f"\t{','.join(map(str, anim))}"
                )
                if mode == "layered" and base_index is not None:
                    for oi in sorted(set(anim)):
                        px, py = overlay_paste_xy(frames[base_index], frames[oi])
                        meta_lines.append(f"paste\tseg{seg_i}\tf{oi:02d}\tat\t{px},{py}")
            if has_layered:
                meta_lines.append("note\tstill/damaged frames export as static; overlays paste at hotspot delta")
            padding_count = sum(1 for _, _, w, h, _ in frames if is_chain_padding_frame(w, h))
            if padding_count:
                meta_lines.append(
                    f"padding_frames\t{padding_count}\t(1x1 chain slots; skipped on static export)"
                )
            meta_lines.append("")
            meta_lines += [
                f"{i}\t{w}x{h}\thotspot={hx},{hy}\toffset={foff:#x}"
                + ("\tpadding" if is_chain_padding_frame(w, h) else "")
                for i, (hx, hy, w, h, foff) in enumerate(frames)
            ]
            (out_dir / f"sprite_{sid:04d}_frames.txt").write_text("\n".join(meta_lines) + "\n", encoding="utf-8")

        cs = gif_delay_cs if gif_delay_cs is not None else (delay if delay > 0 else 50)
        do_animated = not static_only and is_animated
        do_static = not animations_only

        if do_animated:
            for seg_i, (mode, anim, base_index) in enumerate(segments, start=1):
                if len(anim) < 2:
                    continue
                if mode == "layered" and base_index is not None:
                    overlays = [frames[i] for i in sorted(set(anim))]
                    canvas = layered_canvas_bounds(frames[base_index], overlays)
                    rgba_frames: list[Image.Image] = []
                    for oi in anim:
                        rgba_frames.append(
                            composite_layered_frame(
                                dat, frames, base_index, oi, palette, TRANSPARENT, canvas=canvas
                            )
                        )
                else:
                    rgba_frames = []
                    max_w = max(frames[i][2] for i in anim)
                    max_h = max(frames[i][3] for i in anim)
                    for i in anim:
                        _, _, w, h, foff = frames[i]
                        pixels = dat[foff : foff + w * h]
                        img = pixels_to_rgba(pixels, w, h, palette, TRANSPARENT)
                        if w != max_w or h != max_h:
                            canvas_img = Image.new("RGBA", (max_w, max_h), (0, 0, 0, 0))
                            canvas_img.paste(img, (0, max_h - h), img)
                            img = canvas_img
                        rgba_frames.append(img)
                if len(segments) == 1:
                    gif_name = f"sprite_{sid:04d}_animated.gif"
                else:
                    gif_name = f"sprite_{sid:04d}_animated_{seg_i}.gif"
                write_gif(out_dir / gif_name, rgba_frames, cs, palette)
                gif_count += 1
                tsv_rows.append((f"{sid:04d}", gif_name, "animated", str(len(anim))))
                if limit is not None and gif_count >= limit:
                    break

        if do_static and (limit is None or gif_count < limit):
            if has_layered:
                static_fis = layered_static_frame_indices(len(frames), segments)
            elif is_animated:
                static_fis = [i for i in range(len(frames)) if i not in used_anim_frames]
            else:
                static_fis = list(range(len(frames)))
            static_fis = without_padding_frames(static_fis, frames)
            for fi in static_fis:
                if limit is not None and gif_count >= limit:
                    break
                _, _, w, h, foff = frames[fi]
                if foff + w * h > len(dat):
                    emit(f"skip sprite {sid} frame {fi}: offset past EOF")
                    continue
                pixels = dat[foff : foff + w * h]
                img = pixels_to_rgba(pixels, w, h, palette, TRANSPARENT)
                hx, hy = frames[fi][0], frames[fi][1]
                name_part = f"f{fi:02d}_{w}x{h}_hot{hx:+d}_{hy:+d}"
                gif_name = f"sprite_{sid:04d}_static_{name_part}.gif"
                write_gif(out_dir / gif_name, [img], cs, palette)
                gif_count += 1
                tsv_rows.append((f"{sid:04d}", gif_name, "static", ""))

        if limit is not None and gif_count >= limit:
            break

    if tsv_rows:
        tsv_rows.sort(key=lambda r: r[0])
        tsv_path = out_dir / "sprite_manifest.tsv"
        with open(tsv_path, "w", encoding="utf-8", newline="") as f:
            f.write("sprite\tfilename\ttype\tframes\n")
            for row in tsv_rows:
                f.write("\t".join(row) + "\n")

    return gif_count


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--deadlock-path",
        type=Path,
        default=None,
        help="Path to the Deadlock installation folder (must contain deadlock.exe and SPRITELG.DAT)",
    )
    ap.add_argument("--exe", type=Path, default=None, help="Path to deadlock.exe (overrides --deadlock-path)")
    ap.add_argument("--dat", type=Path, default=None, help="Path to SPRITELG.DAT (overrides --deadlock-path)")
    ap.add_argument("--out", type=Path, default=default_output_dir())
    ap.add_argument("--limit", type=int, default=None, help="Max GIFs to write (test runs)")
    ap.add_argument("--id", type=int, action="append", dest="ids", help="Only these sprite ids")
    ap.add_argument(
        "--static-id",
        type=int,
        action="append",
        dest="static_ids",
        help="Force these sprite IDs to be treated as static (no animation); repeatable",
    )
    ap.add_argument("--animations-only", action="store_true", help="Only output animated sprites as GIFs (skip all static sprites)")
    ap.add_argument("--static-only", action="store_true", help="Only output static (non-animated) sprites as GIFs")
    ap.add_argument(
        "--delay",
        type=int,
        default=None,
        help="GIF frame delay in centiseconds (default: catalog delay word, else 50)",
    )
    ap.add_argument(
        "--write-frames-txt",
        action="store_true",
        help="Also write sprite_XXXX_frames.txt metadata files (off by default)",
    )
    args = ap.parse_args()

    try:
        exe_path, dat_path = resolve_game_paths(args.deadlock_path, args.exe, args.dat)
    except ValueError as exc:
        ap.error(str(exc))

    if not exe_path.exists():
        raise SystemExit(f"Could not find deadlock.exe at: {exe_path}")
    if not dat_path.exists():
        raise SystemExit(f"Could not find SPRITELG.DAT at: {dat_path}")

    if args.animations_only and args.static_only:
        ap.error("--animations-only and --static-only cannot be used together")

    forced_static = set(args.static_ids) if getattr(args, "static_ids", None) else None
    gif_n = extract(
        exe_path,
        dat_path,
        args.out,
        limit=args.limit,
        sprite_ids=args.ids,
        animations_only=args.animations_only,
        static_only=args.static_only,
        gif_delay_cs=args.delay,
        forced_static_ids=forced_static,
        write_frames_txt=args.write_frames_txt,
    )
    print(f"Wrote {gif_n} GIFs under {args.out}")


if __name__ == "__main__":
    main()
