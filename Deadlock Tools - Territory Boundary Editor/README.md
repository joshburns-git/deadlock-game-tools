# Deadlock Tools — Territory Boundary Editor

Edit Deadlock territory **boundaries**, **names**, and **owners** in a save file.

## Map editor (GUI)

```bash
python territory_map_editor.py
python territory_map_editor.py "..\Deadlock\territory-edits.SAV"
```

- **Open** a `.SAV` file and view the world map as a colored grid.
- **Paint** tool: select a territory in the list, then click or drag on the map to assign cells.
- **Eyedropper**: click a cell to select its territory.
- Edit **name** and **owner** in the properties panel (owner is the player slot for that game).
- **Save** / **Save As** writes grid assignments, outline cell lists, names, and owners back into the save.

## ASCII export/import (CLI)

Edit territory boundaries by painting an ASCII map, then writing the changes back into a `.SAV` file.

The game stores boundaries twice:

1. **World grid** — each map cell has a territory id (`u16[1]`). This drives tile ownership.
2. **Territory outline** — each territory record lists its `(x, y)` cells **in a specific order**. Deadlock walks this list to draw etched border lines. New cells must be **spliced in right after an adjacent neighbor** in that list — not sorted, and not appended at the tail unless that neighbor is the last cell.

3. **Border bytes** — for capital-site territories (`* Landing`), one byte per outline cell at `record+0x68` (parallel to the outline list) controls etched border rendering. These bytes must be reordered and updated when the outline changes.

4. **Grid border flags** — `u16[4]` on each world cell (when present) also drives etched lines. Landing territories get refreshed border flags on save.

This tool keeps all of these in sync. Small edits preserve the original outline order and splice extensions beside the correct neighbor; larger reshapes rebuild a contiguous cell chain.

## Requirements

- Python 3.10+
- A Deadlock save file (`.SAV`)

## Quick start

From this folder:

```bash
python territory_boundary.py export --sav "..\Deadlock\territory-edits.SAV"
```

That writes `territory-edits.map.txt` next to the save (unless you pass `--out`).

Edit the `@MAP` section: one character per cell. Each symbol maps to a territory id via the legend in the header.

Import:

```bash
python territory_boundary.py import --sav "..\Deadlock\territory-edits.SAV" --map territory-edits.map.txt
```

By default this writes `territory-edits-boundaries.SAV` beside the source save. Use `--output` to choose another path.

Validate before importing:

```bash
python territory_boundary.py validate --sav "..\Deadlock\territory-edits.SAV" --map territory-edits.map.txt
```

## ASCII map format

```text
# Deadlock territory map (ASCII)
# source: territory-edits.SAV
# width: 20  height: 20
# legend: symbol  id  owner  name
#   A    1  ChCh't    ChCh't Landing
#   B    2  Unowned   Vunta Steppe
@MAP
   01234567890123456789
00 00111111112222222222
01 00111111112222222222
...
```

- **Rows** are prefixed with `yy ` (two-digit y).
- **Columns** are listed in the helper row above the map (`x` increases to the right).
- **`.`** means unassigned (territory id `0`).
- Only change characters in the map rows; keep the legend in sync if you introduce a new symbol.

## Editing tips

- To move a border, change the symbol on a cell and give the neighboring cell to the other territory.
- Territories must stay **contiguous** (one connected blob). Erasing or reshaping that splits a territory is blocked on save.
- Each territory's **bounding box** must be at least **4 columns wide and 3 rows tall**. Smaller territories crash Deadlock on load.
- Each territory can have at most **48** cells. The outline coordinate list at `record+0x80` shares space with other territory data from about `+0x142` onward; larger outlines overwrite that tail and crash Deadlock on load.
- Prefer copying a save first (`territory-edits.SAV` → `territory-edits-test.SAV`) before importing.
- Owner in the legend is the **player slot** for that game (resolved from capital names like `Maug Landing` when possible), not a fixed race id. Slot `0` is Tarth in `base.sav` but Maug in `territory-edits.SAV`.

## Commands

| Command | Purpose |
|---|---|
| `export --sav PATH [--out PATH]` | Save → ASCII map |
| `import --sav PATH --map PATH [--output PATH] [--dry-run] [--force]` | ASCII map → new `.SAV` |
| `validate --sav PATH --map PATH` | Compare map against save without writing |

`--dry-run` parses and validates only. `--force` writes even when validation reports warnings.
