# Deadlock Tools - Save Map Editor

> **DEPRECATED.** Superseded by the [Game Save Editor](../Deadlock%20Tools%20-%20Game%20Save%20Editor). Use that tool for colony tile editing; this folder is kept for reference.

Research and tooling for editing **colony terrain** inside Deadlock v1.31 `.SAV` files.

This is separate from the experimental Territory Boundary Editor. That tool reshapes territory **boundaries** on the world map. This project targets the **6×6 colony tile table** stored inside each territory record (`name + 0x140`), which controls plains/forest/mountains/water tiles, resource bonuses, and per-tile yields.

## What we learned (Phase 1)

Territory “type” is **not** one byte on the world map. Each colonized territory stores up to **36 tile rows** (`0x20` bytes each):

| Offset in row | Field |
| --- | --- |
| `u16[0]` | Slot `row×256 + col` (6×6 colony grid) |
| `u16[1]` | Terrain word (base type + optional high-byte flags) |
| `u16[2]` | Bonus flag (Fertile, Energy-rich, etc.) |
| `u16[3..7]` | Yields: Energy / Food / Wood / Iron / Endurium ×100 |

### Base terrain codes (low byte)

| Code | Label | Notes |
| --- | --- | --- |
| 0 | Clear | Plains-like |
| 1 | Rough | |
| 2 | Lightly Wooded | |
| 3 | Heavily Wooded | Common in `Blue-Green Forest` |
| 4 | Rocky | Mountains |
| 96 | Bog | Seen in swamp territories |
| 101 | Wetland | `Traca Wetplace` |
| 4095 | Water | Special full-word code (`0xFFF`) |

Colonized saves also OR high-byte flags into terrain words (for example `0x4000 | Clear` on `ChCh't Landing`). The editor keeps flags optional when applying presets.

Territory names (`Dare Mountains`, `Vunta Steppe`, etc.) are mostly cosmetic. The playable terrain is in the tile table.

## Quick start

### GUI (recommended)

Requires Python 3.10+ with Tkinter and Pillow (for the splash screen).

```bash
cd "DEPRECATED - Deadlock Tools - Save Map Editor"
python map_editor_gui.py
python map_editor_gui.py "..\Deadlock\base.sav"
```

Or run `dist\MapEditor.exe` after building (see below).

1. Open a `.SAV` file.
2. Click a territory on the world map (or in the list).
3. Paint the 6×6 colony grid with the terrain brush, or **Apply brush to all tiles in territory**.
4. **Save As** to a new file and load it in Deadlock.

This tool edits **colony tile tables only**. It does not reshape territory boundaries.

### CLI

```bash
cd "DEPRECATED - Deadlock Tools - Save Map Editor"

# List territories and whether they have a tile table
python dump_tiles.py --save "..\Deadlock\base.sav" list

# Inspect one territory
python dump_tiles.py --save "..\Deadlock\base.sav" show "Blue-Green Forest"

# Write a copy with every tile set to rocky mountains base terrain
python dump_tiles.py --save "..\Deadlock\base.sav" preset "Vunta Steppe" rocky

# Change one tile
python dump_tiles.py --save "..\Deadlock\base.sav" set-tile "Blue-Green Forest" 2 3 --preset forest
```

Presets: `plains`, `clear`, `rough`, `light-woods`, `woods`, `forest`, `heavy-woods`, `mountains`, `rocky`, `bog`, `wetland`, `water`.

## Modules

| File | Purpose |
| --- | --- |
| `terrain_catalog.py` | Terrain/bonus labels, presets, flag decoding |
| `territory_tiles.py` | Read/write colony tile rows in territory records |
| `map_editor_gui.py` | GUI world map + 6×6 tile painter |
| `dump_tiles.py` | CLI list/show/preset/set-tile |
| `test_tile_io.py` | Round-trip test on a copied save |

The parser reuses `deadlock_territory_save.py` from `DEPRECATED - Deadlock Tools - Territory Boundary Editor` for layout/territory discovery only.

## Validation workflow

1. Copy a save (`base.sav` → `base-tile-edit.sav`).
2. Patch tiles with `dump_tiles.py`.
3. Load the copy in Deadlock and inspect the colony tile in-game.
4. Keep the original untouched.

Run the round-trip test:

```bash
python test_tile_io.py "..\Deadlock\base.sav"
```

## Rebuild the executable (developers)

```bash
cd "DEPRECATED - Deadlock Tools - Save Map Editor"
build.bat
```

Output: `dist\MapEditor.exe`.

## Next steps
- Import template tile tables from reference territories
- Do **not** mix with boundary reshaping until that editor is stable
