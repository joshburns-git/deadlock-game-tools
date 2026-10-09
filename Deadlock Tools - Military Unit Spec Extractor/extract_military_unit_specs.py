#!/usr/bin/env python3
"""
Export Deadlock military unit specifications to CSV (and optional XLSX).

Copyright (c) 2026 Josh Burns <deadlock-game-tools@joshburns.me>
https://sourceforge.net/projects/deadlock-game-tools
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from deadlock_unit_specs import (
    BUILD_COST_LABELS,
    iter_unit_types,
    load_exe_bytes,
    race_column_fieldnames,
    race_columns_for_unit,
)

DEFAULT_OUT = "deadlock_military_unit_specs.csv"
DEFAULT_OUTPUT_DIR_NAME = "extracted_deadlock_unit_specs"


def default_output_dir() -> Path:
    """Folder next to the .exe (frozen) or this script (dev), like the sprite extractor."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / DEFAULT_OUTPUT_DIR_NAME
    return Path(__file__).resolve().parent / DEFAULT_OUTPUT_DIR_NAME


def base_fieldnames() -> list[str]:
    return [
        "type_id",
        "name",
        "classification_id",
        "classification",
        "attack",
        "defense",
        "health",
        "movement_speed",
        "movement_timer",
        *BUILD_COST_LABELS,
        *race_column_fieldnames(),
        "credits_word",
        "aux_word",
        "tail_flags_hex",
        "raw_record_hex",
    ]


def record_to_base_dict(rec) -> dict[str, object]:
    out: dict[str, object] = {
        "type_id": rec.type_id,
        "name": rec.name,
        "classification_id": rec.classification_id,
        "classification": rec.classification,
        "attack": rec.attack,
        "defense": rec.defense,
        "health": rec.damage_word,
        "movement_speed": rec.movement_base,
        "movement_timer": rec.movement_timer,
        "credits_word": rec.credits_word,
        "aux_word": rec.aux_word,
        "tail_flags_hex": rec.tail_flags_hex,
        "raw_record_hex": rec.raw_hex,
    }
    for label in BUILD_COST_LABELS:
        out[label] = rec.build_costs.get(label, 0)
    out.update(race_columns_for_unit(rec))
    return out


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_xlsx(path: Path, sheets: dict[str, tuple[list[str], list[dict[str, object]]]]) -> None:
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise SystemExit(
            "XLSX output requires openpyxl. Install with: pip install openpyxl"
        ) from exc

    wb = Workbook()
    first = True
    for title, (fieldnames, rows) in sheets.items():
        if first:
            ws = wb.active
            ws.title = title[:31]
            first = False
        else:
            ws = wb.create_sheet(title[:31])
        ws.append(fieldnames)
        for row in rows:
            ws.append([row[k] for k in fieldnames])
    wb.save(path)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extract military unit stats from Deadlock v1.31 deadlock.exe to spreadsheets."
    )
    p.add_argument("--exe", type=Path, help="Path to deadlock.exe")
    p.add_argument("--deadlock-path", type=Path, help="Deadlock install folder")
    out_default = default_output_dir() / DEFAULT_OUT
    p.add_argument("--out", type=Path, default=out_default, help="Unit specs CSV")
    p.add_argument("--xlsx", type=Path, help="Write the units sheet to an Excel workbook")
    p.add_argument(
        "--include-fortifications",
        action="store_true",
        help="Include Laser/Energy/Anti-Matter Defense entries",
    )
    return p.parse_args(argv)


def resolve_exe_path(
    *,
    exe: Path | None = None,
    deadlock_path: Path | None = None,
) -> Path:
    if exe is not None:
        return exe.expanduser().resolve()
    if deadlock_path is not None:
        return (deadlock_path.expanduser().resolve() / "deadlock.exe")
    here = Path(__file__).resolve().parent
    return (here.parent / "Deadlock" / "deadlock.exe").resolve()


def resolve_exe(args: argparse.Namespace) -> Path:
    return resolve_exe_path(exe=args.exe, deadlock_path=args.deadlock_path)


@dataclass
class ExportResult:
    unit_count: int
    out_csv: Path
    xlsx_path: Path | None


@dataclass
class ExportOptions:
    exe: Path
    out_csv: Path
    xlsx_path: Path | None
    include_fortifications: bool = False


def export_specs(options: ExportOptions) -> ExportResult:
    data = load_exe_bytes(options.exe)
    records = iter_unit_types(data, military_only=not options.include_fortifications)
    fieldnames = base_fieldnames()
    base_rows = [record_to_base_dict(r) for r in records]

    out_csv = options.out_csv.expanduser().resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    write_csv(out_csv, fieldnames, base_rows)

    xlsx_written: Path | None = None
    if options.xlsx_path is not None:
        xlsx_written = options.xlsx_path.expanduser().resolve()
        xlsx_written.parent.mkdir(parents=True, exist_ok=True)
        write_xlsx(xlsx_written, {"units": (fieldnames, base_rows)})

    return ExportResult(
        unit_count=len(base_rows),
        out_csv=out_csv,
        xlsx_path=xlsx_written,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    exe = resolve_exe(args)
    result = export_specs(
        ExportOptions(
            exe=exe,
            out_csv=args.out,
            xlsx_path=args.xlsx,
            include_fortifications=args.include_fortifications,
        )
    )
    print(f"Wrote {result.unit_count} units to {result.out_csv}")
    if result.xlsx_path is not None:
        print(f"Wrote {result.xlsx_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
