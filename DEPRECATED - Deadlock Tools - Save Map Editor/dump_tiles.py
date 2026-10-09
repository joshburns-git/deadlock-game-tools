#!/usr/bin/env python3
"""CLI for inspecting and patching colony tile tables in Deadlock .SAV files."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from terrain_catalog import TERRITORY_PRESETS
from territory_tiles import (
    apply_base_preset,
    find_territory,
    format_tile_report,
    load_save_path,
    patch_territory_tiles,
    read_tiles_for_territory,
)


def cmd_list(args: argparse.Namespace) -> int:
    save = load_save_path(args.save)
    print(f"{args.save.name}: {len(save.territories)} territories\n")
    for territory in save.territories:
        tiles = read_tiles_for_territory(save, territory)
        summary = "empty" if not tiles else f"{len(tiles)} tiles"
        print(f"  {territory.index:2}. {territory.name:24} {summary}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    save = load_save_path(args.save)
    territory = find_territory(save, args.territory)
    tiles = read_tiles_for_territory(save, territory)
    print(format_tile_report(territory.name, tiles))
    return 0


def cmd_preset(args: argparse.Namespace) -> int:
    source = args.save.expanduser().resolve()
    output = args.output.expanduser().resolve() if args.output else source.with_name(
        f"{source.stem}-{args.preset}{source.suffix}"
    )
    if output != source and not output.is_file():
        shutil.copy2(source, output)

    def mutator(tiles: list):
        if not tiles:
            raise ValueError(
                f"{args.territory!r} has no colony tile table to patch "
                "(colonize it in-game first, or pick another territory)."
            )
        return apply_base_preset(
            tiles,
            args.preset,
            keep_flags=args.keep_flags,
            keep_bonus=not args.clear_bonus,
            keep_yields=not args.clear_yields,
        )

    patch_territory_tiles(output, args.territory, mutator, output_path=output)
    save = load_save_path(output)
    territory = find_territory(save, args.territory)
    print(f"Wrote {output}")
    print()
    print(format_tile_report(territory.name, read_tiles_for_territory(save, territory)))
    return 0


def cmd_set_tile(args: argparse.Namespace) -> int:
    source = args.save.expanduser().resolve()
    output = args.output.expanduser().resolve() if args.output else source.with_name(
        f"{source.stem}-tile-edit{source.suffix}"
    )
    if output != source:
        shutil.copy2(source, output)

    preset_base = args.base
    if args.preset:
        from terrain_catalog import preset_base as resolve_preset

        preset_base = resolve_preset(args.preset)

    def mutator(tiles: list):
        if not tiles:
            raise ValueError(f"{args.territory!r} has no colony tile table to patch")
        updated: list = []
        found = False
        for tile in tiles:
            if tile.row == args.row and tile.col == args.col:
                found = True
                new_tile = tile.with_base_terrain(preset_base, keep_flags=args.keep_flags)
                if args.bonus is not None:
                    new_tile = new_tile.with_bonus(args.bonus)
                updated.append(new_tile)
            else:
                updated.append(tile)
        if not found:
            raise ValueError(f"No tile at ({args.row}, {args.col}) in {args.territory!r}")
        return updated

    patch_territory_tiles(output, args.territory, mutator, output_path=output)
    save = load_save_path(output)
    territory = find_territory(save, args.territory)
    print(f"Wrote {output}")
    print()
    print(format_tile_report(territory.name, read_tiles_for_territory(save, territory)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, required=True, help="Path to a .SAV file")
    sub = parser.add_subparsers(dest="command", required=True)

    list_cmd = sub.add_parser("list", help="List territories and tile-table presence")
    list_cmd.set_defaults(func=cmd_list)

    show_cmd = sub.add_parser("show", help="Show decoded 6x6 tile rows for one territory")
    show_cmd.add_argument("territory", help="Territory name (exact match)")
    show_cmd.set_defaults(func=cmd_show)

    preset_cmd = sub.add_parser("preset", help="Apply a named base-terrain preset to all tiles")
    preset_cmd.add_argument("territory", help="Territory name")
    preset_cmd.add_argument(
        "preset",
        choices=sorted(TERRITORY_PRESETS),
        help="Preset base terrain for every tile row",
    )
    preset_cmd.add_argument("--output", type=Path, help="Output .SAV (default: copy beside source)")
    preset_cmd.add_argument(
        "--keep-flags",
        action="store_true",
        help="Preserve high-byte terrain flags when changing base terrain",
    )
    preset_cmd.add_argument("--clear-bonus", action="store_true", help="Zero all tile bonus flags")
    preset_cmd.add_argument("--clear-yields", action="store_true", help="Use generic water yields for water preset")
    preset_cmd.set_defaults(func=cmd_preset)

    set_cmd = sub.add_parser("set-tile", help="Change one tile's base terrain/bonus")
    set_cmd.add_argument("territory")
    set_cmd.add_argument("row", type=int)
    set_cmd.add_argument("col", type=int)
    set_cmd.add_argument("--base", type=int, help="Raw base terrain code (0-255)")
    set_cmd.add_argument("--preset", help="Named preset instead of --base")
    set_cmd.add_argument("--bonus", type=int, help="Bonus code")
    set_cmd.add_argument("--keep-flags", action="store_true")
    set_cmd.add_argument("--output", type=Path)
    set_cmd.set_defaults(func=cmd_set_tile)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "set-tile" and args.base is None and args.preset is None:
        parser.error("set-tile requires --base or --preset")
    try:
        return args.func(args)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
