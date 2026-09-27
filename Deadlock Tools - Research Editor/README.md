# Deadlock Research Editor

Graphical editor for technology research in Deadlock `.SAV` files.

## Quick start (no Python required)

**A pre-built Windows app is in the `dist` folder.**

1. Open **`dist`**.
2. Double-click **`ResearchEditor.exe`**.
3. Use **File → Open** and choose your `.SAV` file.
4. Toggle research checkboxes, then **File → Save** or **Save As**.

Optional: drag `ResearchEditor.exe` onto a `.SAV` file, or run from a terminal:

```bat
dist\ResearchEditor.exe "C:\path\to\your\save.SAV"
```

## Run from Python (optional)

Requires Python 3.10+ with Tkinter (included with most Windows Python installs).

```bash
cd "Deadlock Tools - Research Editor"
python research_editor.py
python research_editor.py "..\\Deadlock\\base.sav"
```

## Rebuild the executable (developers)

Requires Python 3.10+, Pillow, and PyInstaller.

```bash
cd "Deadlock Tools - Research Editor"
build.bat
```

`build.bat` converts `ResearchEditor.png` in this folder into `assets\ResearchEditor.ico` (16–256 px) and a 256×256 bundled PNG, then builds the executable. Keep your master artwork as `ResearchEditor.png` here; `assets\` holds the generated icons.

Or manually:

```bash
python build_icon.py
python -m PyInstaller --noconfirm --clean ResearchEditor.spec
```

Output: `dist\ResearchEditor.exe`.

## What it edits

Deadlock stores technologies in **section 6** of the save (after the section 4 player block and the `0x2F4` section 5 blob). There are **36** records of **18 bytes** each (`0x12`):

| File offset (per record) | Meaning |
|---|---|
| `+0` | `known_mask` — player bits for who has completed this technology |
| `+2` | `stolen_mask` — secondary ownership bits (steal-tech tracking) |
| `+4` … `+16` | Seven per-player progress words (file layout; loaded into memory at `+6`) |

The editor treats a technology as **researched** for a player slot when either:

- that player's bit is set in `known_mask`, or
- the player's progress word is `>= 150`

Turning a technology **on** sets the player bit and bumps progress to `150`. Turning it **off** clears the bit and resets progress to `100` (the usual baseline in sample saves).

## Player columns

Columns are **player slots** (0, 1, 2, …) from the save's section 2 header, labeled with the race assigned to each slot (`ChCh't`, `Cyth`, `Human`, `Maug`, `Re'lu`, `Tarth`, `Uva Mosk`). Research is stored per slot, not as one global flag per race.

## Toolbar shortcuts

- **Select all (column)** / **Clear all (column)** — apply to the player chosen in the dropdown
- **Select all (row)** / **Clear all (row)** — apply to the technology chosen in the dropdown

## Notes

- Index `0` (`Nothing`) is not editable.
- Race-specific research **cost modifiers** live in the same 18-byte record; this tool does not expose them yet.
- Always test edited saves in Deadlock before relying on them in a long game.

See `SAVE_RESEARCH.md` in the repo root for the underlying format research.
