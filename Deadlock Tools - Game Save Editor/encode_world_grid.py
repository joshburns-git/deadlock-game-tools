#!/usr/bin/env python3
"""Re-encode world-map grid terrain bytes in a Deadlock .SAV file."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "DEPRECATED - Deadlock Tools - Territory Boundary Editor"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from deadlock_territory_save import LoadedSave, load_save, regenerate_world_grid_terrain  # noqa: E402
from world_gen_grid import find_rng_advance_for_save, read_world_seed2_from_save  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-encode outline grid terrain bytes (exposure + 0x43EBA3 profiles)."
    )
    parser.add_argument("input", type=Path, help="Source .SAV file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path (default: overwrite input)",
    )
    parser.add_argument(
        "--calibrate-rng",
        action="store_true",
        help="Brute-force RNG advance for best profile match (~91%% vs ~90%%)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report seed2 and RNG calibration only; do not write",
    )
    args = parser.parse_args()

    path = args.input.expanduser().resolve()
    data = load_save(path)
    save = LoadedSave.from_bytes(data, path)
    seed2 = read_world_seed2_from_save(data)
    advance = 0
    if args.calibrate_rng:
        advance, matched, total = find_rng_advance_for_save(save, data)
        print(f"seed2={seed2:#010x}  calibrated advance={advance}  profile {matched}/{total}")

    if args.dry_run:
        return 0

    out = regenerate_world_grid_terrain(
        data,
        save.layout,
        save.grid,
        save.territories,
        rng_advance=advance if args.calibrate_rng else None,
        calibrate_rng=args.calibrate_rng,
    )
    dest = (args.output or path).expanduser().resolve()
    dest.write_bytes(out)
    print(f"Wrote {dest.name} ({len(out)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
