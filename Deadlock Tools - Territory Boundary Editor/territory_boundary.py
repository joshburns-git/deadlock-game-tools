#!/usr/bin/env python3
"""Export and import Deadlock territory boundaries as an ASCII map.

Usage:
  python territory_boundary.py export --sav "..\\Deadlock\\territory-edits.SAV"
  python territory_boundary.py export --sav "..\\Deadlock\\base.sav" --out base-territories.txt
  python territory_boundary.py import --sav "..\\Deadlock\\territory-edits.SAV" --map territory-edits.map.txt
  python territory_boundary.py import --sav "..\\Deadlock\\territory-edits.SAV" --map edited.txt --output patched.SAV
  python territory_boundary.py validate --map territory-edits.map.txt --sav "..\\Deadlock\\territory-edits.SAV"
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from deadlock_territory_save import (
    apply_grid,
    export_ascii_map,
    load_save,
    parse_ascii_map,
    parse_layout,
    read_grid,
    validate_grid,
    read_territories,
)


def resolve_sav(path: Path) -> Path:
    sav = path.expanduser().resolve()
    if not sav.is_file():
        raise FileNotFoundError(f"Save file not found: {sav}")
    if sav.suffix.lower() != ".sav":
        raise ValueError(f"--sav must point to a .SAV file, got: {sav.name}")
    return sav


def resolve_map(path: Path) -> Path:
    map_path = path.expanduser().resolve()
    if not map_path.is_file():
        raise FileNotFoundError(f"Map file not found: {map_path}")
    return map_path


def default_map_path(sav: Path) -> Path:
    return sav.with_suffix(".map.txt")


def cmd_export(args: argparse.Namespace) -> int:
    sav = resolve_sav(Path(args.sav))
    data = load_save(sav)
    text = export_ascii_map(data, source_name=sav.name)
    out_path = Path(args.out).expanduser().resolve() if args.out else default_map_path(sav)
    out_path.write_text(text, encoding="utf-8", newline="\n")
    layout = parse_layout(data)
    print(f"Exported {layout.width}x{layout.height} map to {out_path}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    sav = resolve_sav(Path(args.sav))
    map_path = resolve_map(Path(args.map))
    data = load_save(sav)
    text = map_path.read_text(encoding="utf-8")
    _, _, _, grid = parse_ascii_map(text)

    if args.dry_run:
        layout = parse_layout(data)
        territories = read_territories(data, layout)
        warnings = validate_grid(grid, layout, territories)
        print("Dry run OK: map parses and validates.")
        for warning in warnings:
            print(f"  warning: {warning}")
        return 0

    patched = apply_grid(data, grid, strict=not args.force)
    out_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else sav.with_name(f"{sav.stem}-boundaries{sav.suffix}")
    )
    out_path.write_bytes(patched)
    print(f"Wrote {out_path}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    sav = resolve_sav(Path(args.sav))
    map_path = resolve_map(Path(args.map))
    data = load_save(sav)
    text = map_path.read_text(encoding="utf-8")
    _, _, _, grid = parse_ascii_map(text)
    layout = parse_layout(data)
    territories = read_territories(data, layout)
    warnings = validate_grid(grid, layout, territories)
    current = read_grid(data, layout, layout.grid_offset)
    changed = sum(
        1
        for y in range(layout.height)
        for x in range(layout.width)
        if current[y][x] != grid[y][x]
    )
    print(f"Map validates for {layout.width}x{layout.height}.")
    print(f"Cells changed vs save: {changed}")
    for warning in warnings:
        print(f"warning: {warning}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export/import Deadlock territory boundaries as an ASCII map.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    export_p = sub.add_parser("export", help="Write an ASCII territory map from a .SAV")
    export_p.add_argument("--sav", required=True, help="Path to input .SAV file")
    export_p.add_argument(
        "--out",
        help="Output .map.txt path (default: same name as save with .map.txt)",
    )

    import_p = sub.add_parser("import", help="Apply an ASCII map back into a .SAV")
    import_p.add_argument("--sav", required=True, help="Path to source .SAV file")
    import_p.add_argument("--map", required=True, help="Path to edited ASCII map")
    import_p.add_argument(
        "--output",
        help="Output .SAV path (default: <save>-boundaries.SAV)",
    )
    import_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the map without writing a save",
    )
    import_p.add_argument(
        "--force",
        action="store_true",
        help="Import even if validation reports warnings",
    )

    validate_p = sub.add_parser("validate", help="Check an ASCII map against a .SAV")
    validate_p.add_argument("--sav", required=True, help="Path to .SAV file")
    validate_p.add_argument("--map", required=True, help="Path to ASCII map")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            return cmd_export(args)
        if args.command == "import":
            return cmd_import(args)
        if args.command == "validate":
            return cmd_validate(args)
    except (OSError, ValueError, struct.error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
