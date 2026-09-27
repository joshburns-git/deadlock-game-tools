# Deadlock Tools - Custom City Victory Condition

Patch Deadlock v1.31 so the highest city-victory option is something other than 10 (40 by default).

This writes four places in `deadlock.exe`:

- Runtime default in the options blob
- Setup default table
- UTF-16 menu label (`10 Cities` → `40 Cities`)
- Victory-option lookup table (2, 3, 5, 7, **10** → last entry becomes your value)

Existing saves keep their own `citiesToWin` byte unless you also patch a `.SAV`.

## Quick start (no Python required)

**A pre-built Windows app is in the `dist` folder.**

1. Open **`dist`**.
2. Double-click **`CityVictory.exe`**.
3. Browse to `deadlock.exe`.
4. Set the city count (default 40) and click **Patch**.
5. A `deadlock.exe.bak` backup is created next to the executable the first time.

Optional: drag `CityVictory.exe` onto `deadlock.exe`, or run:

```bat
dist\CityVictory.exe "C:\Games\Deadlock\deadlock.exe"
```

## Compatibility

This tool has **only been tested on Deadlock version 1.31**. It refuses to patch unexpected executables unless you turn on **Force**.

## Run from Python (optional)

Requires Python 3.10+ with Tkinter (included with most Windows Python installs).

```bash
cd "Deadlock Tools - Custom City Victory Condition"
python city_victory_gui.py
python patch_cities_to_win.py --exe "C:\Games\Deadlock\deadlock.exe"
python patch_cities_to_win.py --exe "C:\Games\Deadlock\deadlock.exe" --value 30
python patch_cities_to_win.py --exe "C:\Games\Deadlock\deadlock.exe" --status
python patch_cities_to_win.py --exe "C:\Games\Deadlock\deadlock.exe" --revert
python patch_cities_to_win.py --exe "C:\Games\Deadlock\deadlock.exe" --save "C:\Games\Deadlock\base.sav"
```

## Rebuild the executable (developers)

Requires Python 3.10+ and PyInstaller. Pillow is only needed if you change icon assets.

```bash
cd "Deadlock Tools - Custom City Victory Condition"
build.bat
```

Or manually:

```bash
python -m PyInstaller --noconfirm --clean CityVictory.spec
```

Output: `dist\CityVictory.exe`. Icon assets live in `assets\`. `logo.jpg` is the source art; `build_icon.py` writes `CityVictory.ico` (file icon) and `CityVictory.png` (in-app window icon).

## Command line

| Argument   | Description                                      |
| ---------- | ------------------------------------------------ |
| `--exe`    | Path to `deadlock.exe` (or its folder)           |
| `--value`  | Cities required to win (default 40, range 1–99)  |
| `--status` | Show the current patched values                  |
| `--revert` | Restore from `deadlock.exe.bak`, or the default 10 |
| `--force`  | Patch even if version checks fail                |
| `--save`   | Also patch a `.SAV` (repeatable)                 |

Start a new game after patching the executable. A save already in progress keeps its own city-victory value unless you patch that save too.
