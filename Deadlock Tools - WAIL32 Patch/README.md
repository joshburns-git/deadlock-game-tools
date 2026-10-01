# Deadlock Tools - WAIL32 Patch

Patch the **retail** `WAIL32.DLL` that ships with Deadlock v1.31 so the game starts on Windows 10/11 without freezing at audio init (`DEBUG.TXT` stops at `LoadWail`).

## Why patch instead of removing or replacing the DLL?

Many workarounds tell you to **rename**, **delete**, or **swap out** `WAIL32.DLL` for a smaller replacement file. That can stop the crash, but you often lose most of the game’s audio along the way.

**This tool is different:** it **patches the original Miles Sound System DLL in place** (a 5-byte fix). You keep the same file the game was built to use, so **background music, colony sound effects, and the rest of Deadlock’s Miles audio should still work** — not just a silent boot to the main menu.

Your unmodified copy is backed up as `WAIL32.original.bak.DLL` the first time you patch. Nothing is renamed or deleted unless you choose **Restore original**.

## What the patch changes

Retail Miles opens wave output with `CALLBACK_FUNCTION` (`0x30000`). The callback immediately calls `SuspendThread()` on the thread that is loading the DLL. On modern Windows that can deadlock inside `waveOutOpen` during startup.

The patch changes one instruction at file offset `0x8421`:

- Before: `push 0x30000` (callback function)
- After: `push 0` (`CALLBACK_NULL`)

Tested with Deadlock v1.31 on Windows 10.

## Quick start (no Python required)

**A pre-built Windows app is in the `dist` folder.**

1. Open **`dist`**.
2. Double-click **`Wail32Patch.exe`**.
3. Browse to `deadlock.exe`.
4. Click **Apply patch**.
5. Launch Deadlock and confirm the game reaches the main menu **with background music and colony sounds**.

Optional: drag `Wail32Patch.exe` onto `deadlock.exe`, or run:

```bat
dist\Wail32Patch.exe "C:\Games\Deadlock\deadlock.exe"
```

Use **Restore original** to copy `WAIL32.original.bak.DLL` back over `WAIL32.DLL`.

## Compatibility

This tool only accepts the retail v1.31 `WAIL32.DLL` (114,688 bytes) with the expected bytes at the patch site. If you previously renamed, deleted, or replaced that file, restore the **original game DLL** from your install media or from `WAIL32.original.bak.DLL` before patching.

## Run from Python (optional)

Requires Python 3.10+ with Tkinter (included with most Windows Python installs).

```bash
cd "Deadlock Tools - WAIL32 Patch"
python wail32_patch_gui.py
python patch_wail32.py --exe "C:\Games\Deadlock\deadlock.exe"
python patch_wail32.py --exe "C:\Games\Deadlock\deadlock.exe" --status
python patch_wail32.py --exe "C:\Games\Deadlock\deadlock.exe" --restore
```

## Rebuild the executable (developers)

Requires Python 3.10+ and PyInstaller. Pillow is only needed if you change icon assets.

```bash
cd "Deadlock Tools - WAIL32 Patch"
python build_icon.py
build.bat
```

Or manually:

```bash
python -m PyInstaller --noconfirm --clean Wail32Patch.spec
```

Output: `dist\Wail32Patch.exe`. Icon assets live in `assets\`. `logo.jpg` is the source art; `build_icon.py` writes `Wail32Patch.ico` (file icon) and `Wail32Patch.png` (in-app window icon).

## Command line

| Argument   | Description                                |
| ---------- | ------------------------------------------ |
| `--exe`    | Path to `deadlock.exe` (or its folder)     |
| `--status` | Show whether WAIL32 is retail or patched   |
| `--restore`| Restore from `WAIL32.original.bak.DLL`     |

With no extra flags, the CLI applies the patch.
