"""WAIL coast/terrain mask atlas for world-map rendering (SPRITELG @ 0x4A00).

Ports mask lookup from 0x432438 / 0x4327AD using the static descriptor table at
0x48281C (pointer stored in 0x47950C). Runtime +8 pointers are rebuilt from the
64×64 palette-index sheet loaded from SPRITELG offset 0x4A00.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import pefile

from world_map_terrain_cache import CELL_PX, _va_to_offset

WAIL_TABLE_VA = 0x48281C
WAIL_PTR_VA = 0x47950C
WAIL_MASK_BASE = 0xF80
SPRITELG_MASK_OFF = 0x4A00
SPRITELG_MASK_SIZE = 64 * 64


@dataclass(frozen=True)
class WailEntry:
    """16-byte records from the static table at 0x48281C."""

    raw: bytes
    stride_word: int
    runtime_offset: int
    file_hint: int

    @classmethod
    def from_bytes(cls, data: bytes) -> WailEntry:
        return cls(
            raw=data,
            stride_word=struct.unpack_from("<h", data, 4)[0],
            runtime_offset=struct.unpack_from("<I", data, 8)[0],
            file_hint=struct.unpack_from("<I", data, 12)[0],
        )


def load_wail_entries(exe: bytes) -> list[WailEntry]:
    pe = pefile.PE(data=exe, fast_load=True)
    pe.parse_data_directories()
    table_off = _va_to_offset(pe, WAIL_TABLE_VA)
    entries: list[WailEntry] = []
    for i in range(32):
        chunk = exe[table_off + i * 16 : table_off + (i + 1) * 16]
        if not chunk or chunk == b"\x00" * 16:
            break
        entries.append(WailEntry.from_bytes(chunk))
    return entries


class WailMaskAtlas:
    """Provides 32×32 mask byte streams indexed by grid cell +0x06."""

    def __init__(self, sheet: bytes, entries: list[WailEntry]) -> None:
        if len(sheet) < SPRITELG_MASK_SIZE:
            raise ValueError("WAIL mask sheet must be at least 64×64 bytes")
        self._sheet = sheet[:SPRITELG_MASK_SIZE]
        self._entries = entries

    @classmethod
    def from_deadlock_dir(cls, deadlock_dir: Path) -> WailMaskAtlas | None:
        spritelg = deadlock_dir / "SPRITELG.DAT"
        exe_path = deadlock_dir / "deadlock.exe"
        if not spritelg.is_file() or not exe_path.is_file():
            return None
        dat = spritelg.read_bytes()
        if len(dat) < SPRITELG_MASK_OFF + SPRITELG_MASK_SIZE:
            return None
        sheet = dat[SPRITELG_MASK_OFF : SPRITELG_MASK_OFF + SPRITELG_MASK_SIZE]
        entries = load_wail_entries(exe_path.read_bytes())
        return cls(sheet, entries)

    def _entry_index(self, mask_index: int, *, parity: int = 0) -> int:
        """Port of the entry index math at the top of 0x432438."""
        mixed = ((mask_index & 1) + (parity << 1)) & 0x03
        return min(mixed, len(self._entries) - 1) if self._entries else 0

    def _sheet_offset(self, mask_index: int, entry: WailEntry) -> int:
        """Choose a 32×32 window inside the 64×64 atlas."""
        if entry.file_hint:
            rel = (entry.file_hint & 0xFFFF) % SPRITELG_MASK_SIZE
            return rel
        quad = mask_index & 0x03
        band = (mask_index >> 2) & 0x03
        row = ((quad >> 1) * 32 + band * 4) % 32
        col = ((quad & 1) * 32) % 32
        return row * 64 + col

    def mask_slice(self, mask_index: int, *, parity: int = 0) -> list[int]:
        """Return 32×32 mask bytes (0 = use byte cache, non-zero = override)."""
        if mask_index == 0:
            return [0] * (CELL_PX * CELL_PX)

        if not self._entries:
            return self._fallback_quadrant(mask_index)

        entry = self._entries[self._entry_index(mask_index, parity=parity)]
        base = self._sheet_offset(mask_index, entry)
        base = (base + WAIL_MASK_BASE + entry.stride_word * ((mask_index >> 2) & 0x1F)) % (
            SPRITELG_MASK_SIZE - CELL_PX
        )

        out: list[int] = []
        for row in range(CELL_PX):
            row_off = (base + row * 64) % SPRITELG_MASK_SIZE
            for col in range(CELL_PX):
                out.append(self._sheet[(row_off + col) % SPRITELG_MASK_SIZE])
        return out

    def _fallback_quadrant(self, mask_index: int) -> list[int]:
        quad = mask_index & 0x03
        row0 = 0 if quad < 2 else 32
        col0 = 0 if (quad & 1) == 0 else 32
        out: list[int] = []
        for row in range(CELL_PX):
            for col in range(CELL_PX):
                out.append(self._sheet[(row0 + row) * 64 + (col0 + col)])
        return out
