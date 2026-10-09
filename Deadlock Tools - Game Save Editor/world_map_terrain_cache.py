"""Deadlock v1.31 world-map terrain cache builder (RE of 0x43E296 / 0x43EA14).

Builds the same word/byte height caches the game fills at 0x4DD880 / 0x4DD87C
from stamp profiles at 0x47F6E0 indexed by grid cell high byte (+0x05).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import pefile

PROFILE_BASE_VA = 0x47F6E0
PROFILE_SIZE = 32
CELL_PX = 32

# Palette indices written by 0x43E9E9 before neighbor blending.
PAL_INDEX_LOW = 0x40
PAL_INDEX_HIGH = 0x30


@dataclass(frozen=True)
class StampProfile:
    fill_word: int
    stamp_count: int
    y_bias: int
    strength_max: int
    strength_min: int
    mag_table: tuple[int, ...]


class DeadlockRng:
    """64-bit LCG matching deadlock.exe 0x4636FC (seedable for reproducible maps)."""

    def __init__(self, lo: int = 1, hi: int = 0) -> None:
        self.lo = lo & 0xFFFFFFFF
        self.hi = hi & 0xFFFFFFFF

    @classmethod
    def from_seed(cls, seed: int) -> DeadlockRng:
        return cls(seed & 0xFFFFFFFF, (seed >> 32) & 0xFFFFFFFF)

    def next(self) -> int:
        lo, hi = self.lo, self.hi
        if hi:
            # 64×64 bit multiply by 0x4E35 with add, as in 0x4636FC.
            mult = 0x4E35
            a = (hi * mult) & 0xFFFFFFFF
            b = ((lo * mult) + a) & 0xFFFFFFFF
            c = ((hi * mult) >> 32) + ((lo * mult) >> 32) + (1 if b < (lo * mult) else 0)
            lo = (b + 1) & 0xFFFFFFFF
            hi = (c + (1 if lo == 0 else 0)) & 0xFFFFFFFF
        else:
            lo = (lo + 1) & 0xFFFFFFFF
        self.lo, self.hi = lo, hi
        return hi & 0x7FFFFFFF

    def rand_mod(self, mod: int) -> int:
        if mod <= 0:
            return 0
        return self.next() % mod


def load_stamp_profiles(exe: bytes) -> list[StampProfile]:
    """Parse six stamp profiles from deadlock.exe."""
    pe = pefile.PE(data=exe, fast_load=True)
    pe.parse_data_directories()
    base_off = _va_to_offset(pe, PROFILE_BASE_VA)
    profiles: list[StampProfile] = []
    for hi in range(6):
        off = base_off + hi * PROFILE_SIZE
        words = struct.unpack_from("<8I", exe, off)
        fill = words[0] & 0xFFFF
        if fill >= 0x8000:
            fill -= 0x10000
        mag_va = words[7]
        mag_off = _va_to_offset(pe, mag_va)
        mags = struct.unpack_from("<64h", exe, mag_off)
        profiles.append(
            StampProfile(
                fill_word=fill,
                stamp_count=words[1],
                y_bias=words[4],
                strength_max=words[5],
                strength_min=words[6],
                mag_table=mags,
            )
        )
    return profiles


def build_map_caches(
    width: int,
    height: int,
    high_grid: list[list[int]],
    profiles: list[StampProfile],
    *,
    map_seed: int = 0xDEAD10CC,
) -> tuple[list[int], list[int], int, int]:
    """Return (word_cache, byte_cache, cache_w, cache_h)."""
    cache_w = width * CELL_PX
    cache_h = height * CELL_PX
    total = cache_w * cache_h
    words = [0] * total

    # Phase 1 — 0x43E2B8: fill each cell's 32×32 slice.
    for cy in range(height):
        for cx in range(width):
            high = _clamp_high(high_grid[cy][cx])
            fill = profiles[high].fill_word
            for ly in range(CELL_PX):
                row = (cy * CELL_PX + ly) * cache_w + cx * CELL_PX
                for lx in range(CELL_PX):
                    words[row + lx] = fill

    # Phase 2 — 0x43E38B: procedural stamps in global pixel coordinates.
    rng = DeadlockRng.from_seed(map_seed)
    for cy in range(height):
        for cx in range(width):
            high = _clamp_high(high_grid[cy][cx])
            prof = profiles[high]
            for _ in range(prof.stamp_count):
                _apply_stamp(words, cache_w, cache_h, cx, cy, prof, rng)

    bytes_ = _words_to_bytes(words)
    bytes_ = _neighbor_blend(bytes_, words, cache_w, cache_h, rng)
    bytes_ = _smooth_byte_cache(bytes_, cache_w, cache_h)
    return words, bytes_, cache_w, cache_h


def cell_word_slice(
    word_cache: list[int],
    cache_w: int,
    cell_x: int,
    cell_y: int,
) -> list[int]:
    """Extract 32×32 height words for one map cell."""
    out: list[int] = []
    base_y = cell_y * CELL_PX
    base_x = cell_x * CELL_PX
    for ly in range(CELL_PX):
        row = (base_y + ly) * cache_w + base_x
        out.extend(word_cache[row : row + CELL_PX])
    return out


def cell_byte_slice(
    byte_cache: list[int],
    cache_w: int,
    cell_x: int,
    cell_y: int,
) -> list[int]:
    """Extract 32×32 palette indices for one map cell."""
    out: list[int] = []
    base_y = cell_y * CELL_PX
    base_x = cell_x * CELL_PX
    for ly in range(CELL_PX):
        row = (base_y + ly) * cache_w + base_x
        out.extend(byte_cache[row : row + CELL_PX])
    return out


def _clamp_high(high: int) -> int:
    return high if 0 <= high <= 5 else 3


def _va_to_offset(pe: pefile.PE, va: int) -> int:
    rva = va - pe.OPTIONAL_HEADER.ImageBase
    return pe.get_offset_from_rva(rva)


def _apply_stamp(
    words: list[int],
    cache_w: int,
    cache_h: int,
    cell_x: int,
    cell_y: int,
    prof: StampProfile,
    rng: DeadlockRng,
) -> None:
    """Port of 0x43E400–0x43E57E stamp ellipse."""
    base_x = rng.rand_mod(0x1F) + (cell_x << 5)
    base_y = rng.rand_mod(0x1F) + (cell_y << 5)

    mag_idx = rng.rand_mod(0x40)
    mag = prof.mag_table[mag_idx] * 8
    sign = 1
    if mag < 0:
        sign = -1
        mag = -mag

    y_radius = rng.rand_mod(0x10) + prof.y_bias
    if y_radius > prof.strength_max:
        y_radius = prof.strength_max

    if mag == 0:
        return

    y_scale = max(1, (mag >> 3) if mag >= 0 else 1)
    if y_scale <= 0:
        y_scale = 1
    x_radius = max(1, mag // y_scale)

    x0 = base_x - x_radius
    x1 = base_x + x_radius
    y0 = base_y - y_radius
    y1 = base_y + y_radius

    for gy in range(y0, y1 + 1):
        if gy < 0 or gy >= cache_h:
            continue
        for gx in range(x0, x1 + 1):
            if gx < 0 or gx >= cache_w:
                continue
            dx = abs(gx - base_x) << 3
            dy = abs(gy - base_y) << 3
            dist = max(dx, dy)
            if dx < dy:
                dist = (dx >> 1) + dy
            else:
                dist = (dy >> 1) + dx
            dist = (dist * y_scale) >> 4
            if dist >= mag:
                continue
            delta = (mag - dist) * sign
            idx = gy * cache_w + gx
            words[idx] = _clamp_word(words[idx] + delta, prof.strength_min)


def _clamp_word(value: int, minimum: int) -> int:
    if value < minimum:
        return minimum
    if value > 0x7FFF:
        return 0x7FFF
    if value < -0x8000:
        return -0x8000
    return value


def _words_to_bytes(words: list[int]) -> list[int]:
    """0x43E9E9: positive word → 0x30, else 0x40."""
    return [PAL_INDEX_HIGH if w > 0 else PAL_INDEX_LOW for w in words]


class _BlendState:
    """Global magnitude / peak tracking used by 0x43E88C across a blend pass."""

    magnitude: int = 1
    peak: int = 0


def _height_flags(word: int, magnitude: int) -> int:
    """Port of 0x43E85B."""
    if word < 0:
        return 0x40
    if word >= 0x280:
        return 0x10
    if magnitude > 0x64:
        return 0x20
    return 0


def _blend_code(
    center: int,
    left: int,
    up: int,
    rng: DeadlockRng,
    state: _BlendState,
) -> int:
    """Port of 0x43E88C — returns low 3-bit palette variation."""
    if center <= 0:
        base = min(5, max(0, ((-center) >> 2) + 7))
        return min(7, base + rng.rand_mod(2))

    bx = (rng.next() % 9) + ((left - center) - 5)
    cx = (rng.next() % 9) + ((up - center) - 5)
    bx_abs = abs(bx)
    cx_abs = abs(cx)
    if cx_abs >= bx_abs:
        state.magnitude = max(bx_abs, cx_abs // 2, 1)
    else:
        state.magnitude = max(cx_abs, bx_abs // 2, 1)
    if state.magnitude <= 0:
        state.magnitude = 1

    ecx = (cx_abs * 100) // state.magnitude
    ebx = (bx_abs * 100) // state.magnitude
    eax = 0x8D - ecx
    edx = (-0x8D) - ebx
    if edx >= eax:
        ecx = edx // 2 + eax
    else:
        ecx = eax // 2 + edx
    ebx = (ecx // 0x96) + 3
    delta_left = left - center
    if delta_left < 0:
        delta_left += 0xF
    ebx -= delta_left >> 4
    if center < state.peak:
        ebx -= (state.peak - center) >> 3
    else:
        state.peak = center
    state.peak -= 0x18
    if ebx < 0:
        ebx = 0
    if ebx > 7:
        ebx = 7
    return ebx


def _neighbor_blend(
    bytes_: list[int],
    words: list[int],
    cache_w: int,
    cache_h: int,
    rng: DeadlockRng,
) -> list[int]:
    """Port of 0x43EA14 — height deltas → low-bit palette variation."""
    out = bytes_[:]
    state = _BlendState()
    state.magnitude = 1
    state.peak = 0
    for row in range(cache_h):
        for col in range(cache_w):
            idx = row * cache_w + col
            center_w = words[idx]
            left_w = words[idx - 1] if col > 0 else center_w
            up_w = words[idx - cache_w] if row > 0 else center_w

            base = out[idx] & 0xF8
            work_center = center_w
            if base == 0x38 and row % 6 == 0 and rng.rand_mod(2) == 0:
                work_center += rng.rand_mod(8) + 0x20

            blend = _blend_code(work_center, left_w, up_w, rng, state)
            flags = _height_flags(work_center, state.magnitude)
            if flags == 0:
                base = out[idx] & 0xF8
            elif flags == 0x20 and base == 0x20 and blend > 2:
                blend -= rng.rand_mod(2)
            else:
                base = flags & 0xF8

            out[idx] = (base & 0xF8) | (blend & 0x07)
    return out


def _smooth_byte_cache(
    bytes_: list[int],
    cache_w: int,
    cache_h: int,
) -> list[int]:
    """Box-filter palette sub-bands to remove stamp speckle while keeping shading."""
    out = bytes_[:]
    for row in range(1, cache_h - 1):
        for col in range(1, cache_w - 1):
            idx = row * cache_w + col
            base = bytes_[idx] & 0xF8
            if base not in (PAL_INDEX_HIGH, PAL_INDEX_LOW, 0x10, 0x38):
                continue
            total = 0
            count = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    sample = bytes_[idx + dy * cache_w + dx]
                    if (sample & 0xF8) == base:
                        total += sample & 0x07
                        count += 1
            if count:
                out[idx] = base | (total // count)
    return out


def remap_byte_for_terrain(pal_idx: int, high: int) -> int:
    """Keep RE shading within palette bands that match each autotile profile."""
    band = pal_idx & 0xF8
    sub = pal_idx & 0x07
    if high == 0:
        if band == PAL_INDEX_HIGH:
            return PAL_INDEX_LOW | sub
        return PAL_INDEX_LOW | sub
    if band == PAL_INDEX_LOW:
        return 0x43 if high in (4, 5) else 0x45
    if band == 0x10:
        return 0x34 | min(sub, 3)
    if band == 0x20:
        return 0x33 | sub
    if band == 0x38 and high in (2, 3):
        return band | sub
    if band == 0x38 and high not in (1, 2):
        return PAL_INDEX_HIGH | min(sub, 5)
    return band | sub


def byte_to_rgb(
    pal_idx: int,
    palette: list[tuple[int, int, int]],
) -> tuple[int, int, int]:
    """Resolve a post-blend cache byte to RGB."""
    idx = pal_idx & 0xFF
    if idx < len(palette):
        return palette[idx]
    band = idx & 0xF8
    sub = idx & 0x07
    if (band + sub) < len(palette):
        return palette[band + sub]
    if band < len(palette):
        return palette[band]
    return (128, 128, 128)
