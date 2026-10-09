# Deadlock Tools — Military Unit Spec Extractor

Exports military unit statistics compiled into `deadlock.exe` (Accolade *Deadlock* v1.31) to CSV spreadsheets for analysis, balance mods, or wiki work.

## Compatibility

Tested against **Deadlock v1.31** only. The tool reads fixed virtual addresses inside `deadlock.exe`; other builds may differ.

## What it extracts

### Base table (`deadlock_military_unit_specs.csv`)

One row per military unit type (IDs 1–24, excluding optional fortifications):

| Column | Source (exe) | Meaning |
| --- | --- | --- |
| `attack` | type record `+0x15` | Attack strength shown in Unit Orders |
| `defense` | type record `+0x16` | Defense / hit points shown in Unit Orders |
| `health` | type record `+0x0C` (word) | Word at `+0x0C` in the type record |
| `movement_speed` | type record `+0x14` | Movement points (base, before racial combat tweaks) |
| `movement_timer` | type record `+0x0F` | Related timing byte used by the game |
| `credits_word`, `aux_word` | `+0x04`, `+0x06` | Raw words in the type record |
| `cost_credits` … `cost_art` | table `0x498798` | Build cost vector (11 resource slots) |
| `classification`, `classification_id` | byte `+0x0B` | infantry, artillery, air, naval, scout, warhead, etc. |
| `raw_record_hex` | 24-byte record | Full type record at `0x498540 + id×0x18` |

After `cost_art`, each race adds two columns (same row as the unit):

| Column pattern | Meaning |
| --- | --- |
| `{race}_traits` | General racial trait summary (e.g. `tarth_traits`, `maug_traits`) |
| `{race}_notes` | When that race’s known modifiers apply to this unit class |

Slugs: `chcht`, `cyth`, `human`, `maug`, `relu`, `tarth`, `uva_mosk`.

**Unit specs in the exe are not duplicated per race.** Base `attack`, `defense`, `movement_speed`, and `health` are shared; racial differences are applied at runtime. The trait/note columns are documentation only—verify in-game when modding.

## Quick start (no Python required)

A pre-built Windows app is in the `dist` folder after you run `build.bat` (or use a release build).

1. Open **`dist`**.
2. Double-click **`MilitaryUnitSpecExtractor.exe`**.
3. Click the splash image to continue.
4. Choose your Deadlock folder (output defaults to **`extracted_deadlock_unit_specs`** next to the `.exe`), then click **Export spreadsheets**.

## Requirements

- Python 3.8+ with Tkinter (for the GUI or CLI)
- `Pillow` (splash screen and About dialog)
- Optional: `openpyxl` for Excel output
- `pyinstaller` only if you rebuild the `.exe`

## Usage

```powershell
cd "Deadlock Tools - Military Unit Spec Extractor"
pip install -r requirements.txt

# GUI (splash screen, folder pickers)
python military_unit_spec_gui.py

# Command line
python extract_military_unit_specs.py --deadlock-path "C:\Games\Deadlock"
```

## Rebuild the executable (developers)

```powershell
cd "Deadlock Tools - Military Unit Spec Extractor"
pip install -r requirements.txt
build.bat
```

Output: `dist\MilitaryUnitSpecExtractor.exe`. Place a source icon at `MilitaryUnitSpecExtractor.png` in this folder (or use the generated `assets\MilitaryUnitSpecExtractor.png` after the first build). The splash uses `assets\deadlock-game-tools-image.jpg`.

Outputs:

- `deadlock_military_unit_specs.csv` (optional `.xlsx` with a single `units` sheet)

### Arguments

| Argument | Description |
| --- | --- |
| `--exe` | Path to `deadlock.exe` |
| `--deadlock-path` | Folder containing `deadlock.exe` |
| `--out` | CSV path (default: `deadlock_military_unit_specs.csv`) |
| `--xlsx` | Also write an Excel workbook (`units` sheet) |
| `--include-fortifications` | Include defensive structures (types 19–21) |

### Examples

```powershell
# Excel workbook
python extract_military_unit_specs.py --exe "..\Deadlock\deadlock.exe" --xlsx deadlock_units.xlsx

# Include forts, custom output folder
python extract_military_unit_specs.py --deadlock-path "D:\Deadlock" --include-fortifications --out D:\out\units.csv
```

## Data location in the game

- **Unit type catalog:** VA `0x498540`, stride `0x18` bytes
- **Build costs:** VA `0x498798`, stride `0x2C` (11×`uint32` per type)
- **Not in save files:** `.SAV` army records hold instances (position, mission, experience), not the master stat table
- **Not in config files:** retail v1.31 stores these tables only in the executable

## License

MIT — see [LICENSE.txt](LICENSE.txt). Copyright (c) 2026 Josh Burns.
