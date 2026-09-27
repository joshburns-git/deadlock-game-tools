#!/usr/bin/env python3
"""Patch Deadlock v1.31 cities-to-win default (10 -> 40).

Patches four locations in deadlock.exe:
  - Runtime default in the options blob (0x47FB70)
  - Setup default table dword after the citiesToWin config key
  - UTF-16 menu label for the highest victory option ("10 Cities" -> "40 Cities")
  - Victory-option lookup table dword (2, 3, 5, 7, 10 -> last entry becomes 40)

Usage:
  python patch_cities_to_win.py --exe "C:\\Games\\Deadlock\\deadlock.exe"
  python patch_cities_to_win.py --exe "C:\\Games\\Deadlock\\deadlock.exe" --value 30
  python patch_cities_to_win.py --exe "C:\\Games\\Deadlock\\deadlock.exe" --status
  python patch_cities_to_win.py --exe "C:\\Games\\Deadlock\\deadlock.exe" --revert
  python patch_cities_to_win.py --exe "C:\\Games\\Deadlock\\deadlock.exe" --save "C:\\Games\\Deadlock\\base.sav"
"""
from __future__ import annotations

import argparse
import shutil
import struct
import sys
from pathlib import Path

DEFAULT_CITIES = 10
MAX_CITIES = 40

# Verified on deadlock.exe v1.31 (size 1_056_800, citiesToWin string present).
RUNTIME_DEFAULT_OFF = 0x65F70
SETUP_DEFAULT_OFF = 0x658BC
UI_LABEL_DIGITS_OFF = 0xAE448  # UTF-16 digits in "&10 Cities" menu label
LOGIC_TABLE_OFF = 0x9548C  # dwords 2, 3, 5, 7, 10
LOGIC_TABLE_LAST_OFF = LOGIC_TABLE_OFF + 4 * 4
CITIES_TO_WIN_STR = b"citiesToWin\x00"
UI_LABEL_STR = "10 Cities".encode("utf-16-le")
EXPECTED_EXE_SIZE = 1_056_800

# Section 3 blob in .SAV files: header 0x7A + section2 0x6A + byte 16.
SAVE_CITIES_TO_WIN_OFF = 0x7A + 0x6A + 16


def resolve_exe(path: Path) -> Path:
    exe = path.expanduser().resolve()
    if exe.is_dir():
        exe = exe / "deadlock.exe"
    if not exe.is_file():
        raise FileNotFoundError(f"deadlock.exe not found: {exe}")
    if exe.name.lower() != "deadlock.exe":
        raise ValueError(f"--exe must point to deadlock.exe, got: {exe.name}")
    return exe


def resolve_save(path: Path) -> Path:
    save = path.expanduser().resolve()
    if not save.is_file():
        raise FileNotFoundError(f"save file not found: {save}")
    if save.suffix.lower() != ".sav":
        raise ValueError(f"--save must be a .SAV file, got: {save}")
    return save


def cities_label_digits(value: int) -> bytes:
    text = str(value)
    if not text.isdigit() or not 1 <= len(text) <= 2:
        raise ValueError("UI label supports 1-2 digit city counts (1-99)")
    if len(text) == 1:
        text = f" {text}"
    return text.encode("utf-16-le")


def read_ui_label_digits(exe: bytes) -> str:
    raw = exe[UI_LABEL_DIGITS_OFF : UI_LABEL_DIGITS_OFF + 4]
    return raw.decode("utf-16-le").strip()


def read_patch_state(exe: bytes) -> dict[str, int | str]:
    return {
        "runtime": exe[RUNTIME_DEFAULT_OFF],
        "setup": struct.unpack_from("<I", exe, SETUP_DEFAULT_OFF)[0],
        "logic_last": struct.unpack_from("<I", exe, LOGIC_TABLE_LAST_OFF)[0],
        "ui_label": read_ui_label_digits(exe),
    }


def check_exe_image(exe: bytes) -> None:
    if len(exe) != EXPECTED_EXE_SIZE:
        raise ValueError(
            f"unexpected deadlock.exe size {len(exe)} (expected {EXPECTED_EXE_SIZE}); "
            "this patch targets v1.31"
        )
    if exe.find(CITIES_TO_WIN_STR) < 0:
        raise ValueError("citiesToWin string not found; wrong executable?")
    if exe[UI_LABEL_DIGITS_OFF : UI_LABEL_DIGITS_OFF + 4] not in (
        cities_label_digits(DEFAULT_CITIES),
        cities_label_digits(MAX_CITIES),
    ):
        raise ValueError(
            "victory menu label is not the expected UTF-16 '10' or '40'; "
            "already modified by another patch?"
        )
    table = [struct.unpack_from("<I", exe, LOGIC_TABLE_OFF + i * 4)[0] for i in range(5)]
    if table[:4] != [2, 3, 5, 7]:
        raise ValueError(f"unexpected victory option table prefix: {table[:4]}")
    if table[4] not in (DEFAULT_CITIES, MAX_CITIES):
        raise ValueError(f"unexpected victory option table last value: {table[4]}")


def patch_exe_bytes(exe: bytearray, cities: int) -> None:
    if not 1 <= cities <= 99:
        raise ValueError("cities must be between 1 and 99")
    exe[RUNTIME_DEFAULT_OFF] = cities
    struct.pack_into("<I", exe, SETUP_DEFAULT_OFF, cities)
    struct.pack_into("<I", exe, LOGIC_TABLE_LAST_OFF, cities)
    exe[UI_LABEL_DIGITS_OFF : UI_LABEL_DIGITS_OFF + 4] = cities_label_digits(cities)


def restore_exe_bytes(exe: bytearray) -> None:
    patch_exe_bytes(exe, DEFAULT_CITIES)


def backup_path(exe: Path) -> Path:
    return exe.with_suffix(exe.suffix + ".bak")


def apply_patch(exe_path: Path, cities: int, force: bool, log=print) -> None:
    data = bytearray(exe_path.read_bytes())
    try:
        check_exe_image(data)
    except ValueError as exc:
        if not force:
            raise ValueError(f"refusing to patch: {exc}\n(use Force to override)") from exc
        log(f"warning: {exc}")

    state = read_patch_state(data)
    if (
        state["runtime"] == cities
        and state["setup"] == cities
        and state["logic_last"] == cities
        and state["ui_label"] == str(cities)
    ):
        log(f"already patched to {cities} (runtime, setup, menu label, logic table)")
        return

    bak = backup_path(exe_path)
    if not bak.exists():
        shutil.copy2(exe_path, bak)
        log(f"backup written to {bak}")
    else:
        log(f"backup already exists at {bak}")

    patch_exe_bytes(data, cities)
    exe_path.write_bytes(data)
    log(f"patched {exe_path}")
    log(f"  runtime default (0x{RUNTIME_DEFAULT_OFF:X}) -> {cities}")
    log(f"  setup default   (0x{SETUP_DEFAULT_OFF:X}) -> {cities}")
    log(f"  menu label      (0x{UI_LABEL_DIGITS_OFF:X}) -> {cities} Cities")
    log(f"  option table    (0x{LOGIC_TABLE_LAST_OFF:X}) -> {cities}")
    log("start a new game to test; existing saves keep their own citiesToWin byte.")


def revert_patch(exe_path: Path, log=print) -> None:
    bak = backup_path(exe_path)
    if not bak.is_file():
        data = bytearray(exe_path.read_bytes())
        restore_exe_bytes(data)
        exe_path.write_bytes(data)
        log(f"reverted {exe_path} to default ({DEFAULT_CITIES}) without backup")
        return
    shutil.copy2(bak, exe_path)
    log(f"restored {exe_path} from {bak}")


def show_status(exe_path: Path, log=print) -> None:
    data = exe_path.read_bytes()
    state = read_patch_state(data)
    log(f"exe: {exe_path}")
    log(f"  size: {len(data)}")
    log(f"  runtime default (0x{RUNTIME_DEFAULT_OFF:X}): {state['runtime']}")
    log(f"  setup default   (0x{SETUP_DEFAULT_OFF:X}): {state['setup']}")
    log(f"  menu label      (0x{UI_LABEL_DIGITS_OFF:X}): {state['ui_label']} Cities")
    log(f"  option table    (0x{LOGIC_TABLE_LAST_OFF:X}): {state['logic_last']}")
    bak = backup_path(exe_path)
    log(f"  backup: {'yes' if bak.is_file() else 'no'} ({bak})")


def patch_save(save_path: Path, cities: int, log=print) -> None:
    if not 1 <= cities <= 255:
        raise ValueError("cities must be between 1 and 255")
    data = bytearray(save_path.read_bytes())
    if len(data) <= SAVE_CITIES_TO_WIN_OFF:
        raise ValueError(f"save file too small for expected layout: {save_path}")
    old = data[SAVE_CITIES_TO_WIN_OFF]
    data[SAVE_CITIES_TO_WIN_OFF] = cities
    save_path.write_bytes(data)
    log(f"patched {save_path}")
    log(f"  citiesToWin at 0x{SAVE_CITIES_TO_WIN_OFF:X}: {old} -> {cities}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--exe",
        type=Path,
        required=True,
        help="Full path to deadlock.exe (required)",
    )
    ap.add_argument(
        "--value",
        type=int,
        default=MAX_CITIES,
        help=f"cities required to win (default: {MAX_CITIES})",
    )
    ap.add_argument("--revert", action="store_true", help="restore deadlock.exe from .bak")
    ap.add_argument("--status", action="store_true", help="show current patch values")
    ap.add_argument("--force", action="store_true", help="patch even if pre-checks fail")
    ap.add_argument(
        "--save",
        type=Path,
        action="append",
        default=[],
        help="full path to a .SAV file to patch as well (repeatable)",
    )
    args = ap.parse_args()

    exe_path = resolve_exe(args.exe)

    if args.status:
        show_status(exe_path)
        return

    if args.revert:
        revert_patch(exe_path)
        return

    apply_patch(exe_path, args.value, args.force)

    for save in args.save:
        patch_save(resolve_save(save), args.value)


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
