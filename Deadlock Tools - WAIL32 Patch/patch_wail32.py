#!/usr/bin/env python3
"""Patch retail Deadlock v1.31 WAIL32.DLL for Windows 10/11 startup hangs.

The retail Miles Sound System DLL opens wave output with CALLBACK_FUNCTION and a
callback that SuspendThread()s the loading thread. On modern Windows that can
deadlock during waveOutOpen while the game is still in LoadWail.

This applies a 5-byte in-place change: push 0x30000 -> push 0 (CALLBACK_NULL).

Usage:
  python patch_wail32.py --exe "C:\\Games\\Deadlock\\deadlock.exe"
  python patch_wail32.py --exe "C:\\Games\\Deadlock" --status
  python patch_wail32.py --exe "C:\\Games\\Deadlock\\deadlock.exe" --restore
"""
from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Verified on retail WAIL32.DLL shipped with Deadlock v1.31 (114,688 bytes).
RETAIL_WAIL32_SIZE = 114_688
PATCH_FILE_OFFSET = 0x8421
ORIGINAL_PATCH_BYTES = b"\x68\x00\x00\x03\x00"  # push 0x30000 (CALLBACK_FUNCTION)
PATCHED_BYTES = b"\x6a\x00\x90\x90\x90"  # push 0 (CALLBACK_NULL); nop padding
BACKUP_NAME = "WAIL32.original.bak.DLL"
WAIL32_CANDIDATES = ("WAIL32.DLL", "WAIL32.dll")


class Wail32State(str, Enum):
    MISSING = "missing"
    UNKNOWN = "unknown"
    RETAIL = "retail"
    PATCHED = "patched"


@dataclass(frozen=True)
class Wail32Status:
    game_dir: Path
    wail32_path: Path | None
    backup_path: Path
    state: Wail32State
    message: str


def resolve_exe(path: Path) -> Path:
    exe = path.expanduser().resolve()
    if exe.is_dir():
        exe = exe / "deadlock.exe"
    if not exe.is_file():
        raise FileNotFoundError(f"deadlock.exe not found: {exe}")
    if exe.name.lower() != "deadlock.exe":
        raise ValueError(f"--exe must point to deadlock.exe, got: {exe.name}")
    return exe


def find_wail32(game_dir: Path) -> Path | None:
    for name in WAIL32_CANDIDATES:
        candidate = game_dir / name
        if candidate.is_file():
            return candidate
    return None


def classify_wail32(path: Path) -> Wail32State:
    data = path.read_bytes()
    if len(data) != RETAIL_WAIL32_SIZE:
        return Wail32State.UNKNOWN
    if not data.startswith(b"MZ"):
        return Wail32State.UNKNOWN
    site = data[PATCH_FILE_OFFSET : PATCH_FILE_OFFSET + len(ORIGINAL_PATCH_BYTES)]
    if site == ORIGINAL_PATCH_BYTES:
        return Wail32State.RETAIL
    if site == PATCHED_BYTES:
        return Wail32State.PATCHED
    return Wail32State.UNKNOWN


def show_status(exe_path: Path) -> Wail32Status:
    exe = resolve_exe(exe_path)
    game_dir = exe.parent
    wail32 = find_wail32(game_dir)
    backup = game_dir / BACKUP_NAME

    if wail32 is None:
        return Wail32Status(
            game_dir=game_dir,
            wail32_path=None,
            backup_path=backup,
            state=Wail32State.MISSING,
            message="WAIL32.DLL was not found in the Deadlock folder.",
        )

    state = classify_wail32(wail32)
    if state is Wail32State.RETAIL:
        msg = "Retail WAIL32.DLL is present and not yet patched."
    elif state is Wail32State.PATCHED:
        msg = "WAIL32.DLL is already patched for Windows 10/11."
    elif state is Wail32State.UNKNOWN:
        msg = (
            "WAIL32.DLL is present but does not match the expected retail v1.31 file "
            f"({RETAIL_WAIL32_SIZE:,} bytes with the known patch site). "
            "Restore the original game DLL before patching."
        )
    else:
        msg = "WAIL32.DLL status could not be determined."

    if backup.is_file() and state is not Wail32State.MISSING:
        msg += f" Backup: {backup.name}"

    return Wail32Status(
        game_dir=game_dir,
        wail32_path=wail32,
        backup_path=backup,
        state=state,
        message=msg,
    )


def _ensure_backup(wail32: Path, backup: Path) -> None:
    if backup.is_file():
        return
    shutil.copy2(wail32, backup)


def apply_patch(exe_path: Path) -> Wail32Status:
    status = show_status(exe_path)
    if status.wail32_path is None:
        raise FileNotFoundError(status.message)
    if status.state is Wail32State.PATCHED:
        status = Wail32Status(
            game_dir=status.game_dir,
            wail32_path=status.wail32_path,
            backup_path=status.backup_path,
            state=status.state,
            message="WAIL32.DLL is already patched.",
        )
        return status
    if status.state is not Wail32State.RETAIL:
        raise ValueError(status.message)

    wail32 = status.wail32_path
    backup = status.backup_path
    _ensure_backup(wail32, backup)

    data = bytearray(wail32.read_bytes())
    site = data[PATCH_FILE_OFFSET : PATCH_FILE_OFFSET + len(ORIGINAL_PATCH_BYTES)]
    if site != ORIGINAL_PATCH_BYTES:
        raise ValueError(
            "Patch site changed before write; aborting. "
            "Restore from backup and try again."
        )
    data[PATCH_FILE_OFFSET : PATCH_FILE_OFFSET + len(PATCHED_BYTES)] = PATCHED_BYTES
    wail32.write_bytes(data)

    return Wail32Status(
        game_dir=status.game_dir,
        wail32_path=wail32,
        backup_path=backup,
        state=Wail32State.PATCHED,
        message=(
            f"Patched {wail32.name}. Original saved as {backup.name}. "
            "Launch Deadlock and listen for background music and colony sounds."
        ),
    )


def restore_original(exe_path: Path) -> Wail32Status:
    status = show_status(exe_path)
    backup = status.backup_path
    if not backup.is_file():
        raise FileNotFoundError(
            f"No backup found ({BACKUP_NAME}). Cannot restore the original DLL."
        )

    wail32 = status.wail32_path or find_wail32(status.game_dir)
    if wail32 is None:
        wail32 = status.game_dir / WAIL32_CANDIDATES[0]

    shutil.copy2(backup, wail32)
    restored = show_status(exe_path)
    return Wail32Status(
        game_dir=restored.game_dir,
        wail32_path=restored.wail32_path,
        backup_path=backup,
        state=restored.state,
        message=f"Restored {wail32.name} from {backup.name}.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exe",
        type=Path,
        required=True,
        help="Path to deadlock.exe or its install folder",
    )
    parser.add_argument("--status", action="store_true", help="Show current WAIL32 status")
    parser.add_argument("--restore", action="store_true", help="Restore from backup")
    args = parser.parse_args(argv)

    try:
        if args.restore:
            result = restore_original(args.exe)
        elif args.status:
            result = show_status(args.exe)
        else:
            result = apply_patch(args.exe)
    except (FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    print(result.message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
