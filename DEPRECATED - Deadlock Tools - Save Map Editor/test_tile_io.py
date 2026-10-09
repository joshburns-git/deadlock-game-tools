#!/usr/bin/env python3
"""Verify colony tile read/write round-trip on a copied .SAV."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from territory_tiles import (
    find_territory,
    load_save_path,
    read_tiles_for_territory,
    write_tiles_for_territory,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAVE = ROOT / "Deadlock" / "base.sav"


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SAVE
    copy_path = source.with_name(f"{source.stem}-tile-roundtrip{source.suffix}")
    shutil.copy2(source, copy_path)

    original = load_save_path(source)
    territory = find_territory(original, "Blue-Green Forest")
    tiles = read_tiles_for_territory(original, territory)

    patched = bytearray(original.data)
    write_tiles_for_territory(patched, original.layout.territory_offset, territory, tiles)
    copy_path.write_bytes(patched)

    if patched == original.data:
        print(f"OK: {len(tiles)} tiles round-tripped with no byte changes -> {copy_path.name}")
        return 0

    # Count differing bytes limited to tile table span
    record_off = original.layout.territory_offset + (territory.index - 1) * 0x5D8
    table_off = record_off + 0x140
    table_end = table_off + 36 * 0x20
    diff = sum(1 for i in range(table_off, table_end) if patched[i] != original.data[i])
    print(f"FAIL: {diff} byte differences inside tile table")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
