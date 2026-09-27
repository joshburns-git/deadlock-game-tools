# Deadlock Tools - Sprite and Animation Extractor

This tool extracts sprites and animations from the 1996 game *Deadlock* (Accolade).

It reads the game's sprite data from `SPRITELG.DAT` (using information embedded in `deadlock.exe`) and writes **GIFs** that use the game's exact palette.

## Quick start (no Python required)

**A pre-built Windows app is in the `dist` folder.**

1. Open **`dist`**.
2. Double-click **`SpriteExtractor.exe`**.
3. Browse to your Deadlock folder and an output folder.
4. Choose animated, static, or both, then click **Extract**.
5. When it finishes, the output folder opens automatically.

## Compatibility

This tool has **only been tested on Deadlock version 1.31**. It parses data structures directly from `deadlock.exe` at fixed addresses, so it may not work with other versions.

If you have tested it with a different version of the game, please let me know so the compatibility expectations can be updated.

## Features

- Correctly handles **layered building animations** (a base image + moving overlays)
- Composites overlays onto the base for GIF playback
- Supports the game's animation scripts (including ping-pong loops and random timing)
- Respects the "Force Small Sprites" / animation-off behavior (frame 0 is the static version)
- Damaged building states (last frame) are excluded from animations by default
- Optional metadata files (`*_frames.txt`) describing every frame and overlay position
- Preserves the game's exact 256-color palette
- Handles transparency via specific palette indices (not color-keying)

## Run from Python (optional)

Requires Python 3.8+ with Tkinter (included with most Windows Python installs) and Pillow.

```bash
cd "Deadlock Tools - Sprite and Animation Extractor"
pip install -r requirements.txt
python sprite_extractor_gui.py
python extract_deadlock_sprites.py --deadlock-path "C:\Games\Deadlock"
```

## Rebuild the executable (developers)

Requires Python 3.10+, PyInstaller, and Pillow.

```bash
cd "Deadlock Tools - Sprite and Animation Extractor"
build.bat
```

Or manually:

```bash
python -m PyInstaller --noconfirm --clean SpriteExtractor.spec
```

Output: `dist\SpriteExtractor.exe`. Icon assets live in `assets\` (`SpriteExtractor.ico` for the `.exe` file icon, `SpriteExtractor.png` for the in-app window icon).

## Command Line Arguments

| Argument            | Description                                                            | Example                                  |
| ------------------- | ---------------------------------------------------------------------- | ---------------------------------------- |
| `--deadlock-path`   | Path to the Deadlock folder (contains `deadlock.exe` + `SPRITELG.DAT`) | `--deadlock-path "C:\Games\Deadlock"`    |
| `--exe`             | Path to `deadlock.exe` (overrides value derived from `--deadlock-path`) | `--exe "C:\Games\Deadlock\deadlock.exe"` |
| `--dat`             | Path to `SPRITELG.DAT` (overrides value derived from `--deadlock-path`) | `--dat "C:\Games\Deadlock\SPRITELG.DAT"` |
| `--out`             | Output directory                                                       | `--out my_sprites`                       |
| `--id`              | Only process specific sprite IDs (repeatable)                          | `--id 24 --id 83`                        |
| `--animations-only` | Only output animated sprites as GIFs (skip static sprites)             | `--animations-only`                      |
| `--static-only`     | Only output static (non-animated) sprites as GIFs                      | `--static-only`                          |
| `--delay`           | Force a specific frame delay in centiseconds for GIFs                  | `--delay 10`                             |
| `--limit`             | Limit the total number of GIFs written (useful for testing)            | `--limit 50`                             |
| `--static-id`         | Force these sprite IDs to be treated as static (repeatable)            | `--static-id 0`                          |
| `--write-frames-txt`  | Write `sprite_XXXX_frames.txt` metadata files (off by default)         | `--write-frames-txt`                     |

### `--deadlock-path`, `--exe`, and `--dat`

Provide one of:

- `--deadlock-path` pointing to the folder that contains both `deadlock.exe` and `SPRITELG.DAT`
- `--exe` **and** `--dat` for direct paths (useful if the files are in separate locations)

You can combine them to override just one file:

```bash
python extract_deadlock_sprites.py --deadlock-path "C:\Games\Deadlock" --dat "D:\Other\SPRITELG.DAT"
```

### `--out`

Directory where output will be written.

**Default:** `extracted_deadlock_sprites/` next to the script, or next to `SpriteExtractor.exe` when running the packaged app.

### `--id`

Process only the listed sprite IDs. Can be used multiple times.

```bash
python extract_deadlock_sprites.py --animations-only --id 24 --id 83 --id 1
```

### `--animations-only`

Only output **animated** sprites as GIFs. Static sprites are skipped.

### `--static-only`

Only output **static** sprites as single-frame GIFs. Layered buildings still export their still/damaged frames.

### `--delay`

Overrides the frame delay (in centiseconds) for all generated GIFs.

- 1 centisecond = 10 milliseconds
- Default: the delay stored in the game data. If that value is 0, it falls back to 50 (500 ms).

### `--limit`

Limits how many GIFs are written. Useful for test runs.

### `--write-frames-txt`

Writes a `sprite_XXXX_frames.txt` file for each processed sprite (frame count, animation mode, overlay paste offsets, hotspots, and file offsets). Off by default.

## Output Format

For each sprite the tool processes, you will get:

- `sprite_XXXX_animated.gif` (for animated sprites)
- `sprite_XXXX_static_....gif` (for static stills / unused frames)
- `sprite_manifest.tsv` — an index of every GIF written
- `sprite_XXXX_frames.txt` — only if `--write-frames-txt` is on, or the GUI checkbox is checked

### GIF Animations

- Use the exact game palette.
- For layered sprites, overlays are composited onto the base using hotspot deltas.
- The damaged last frame is excluded from the animation.

### Layered Building Animations

Many buildings use a composite system:

- One base image (usually frame 1)
- Several small overlay images drawn on top
- Paste position is calculated from hotspot deltas

When metadata is enabled, the `_frames.txt` file will list lines like:

```
paste   f02     at      7,14
paste   f03     at      7,14
```

## Color Palette and Transparency

The tool extracts the game's full 256-color palette directly from `deadlock.exe`.

- Transparency is **index-based**:
  - Palette indices **0** and **207** are treated as fully transparent.
  - Both of those indices are black `(0, 0, 0)`.
- Black in the extracted images represents transparency.

## Tips

- The first run can take a little while because it has to parse the sprite catalog from the executable.
- Use `--animations-only` + `--id` to preview one animation.
- Sprite IDs 0, 1, 22, 24, and 83 are good test cases.
- Enable **Write sprite_XXXX_frames.txt metadata files** (or `--write-frames-txt`) if you need structure information for later re-packing.
- Frame 0 in every sprite is the static version used when "Force Small Sprites" or animations-off is enabled.

## Credits

Reverse-engineered from the original 1996 *Deadlock* executable and data files.

## License

This project is released under the **MIT License**.

See the `LICENSE.txt` file for the full text.

We appreciate attribution when you use or share this tool. A suggested way to credit the project is:

> Based on the Deadlock Sprite and Animation Extractor by Josh Burns  
> [https://sourceforge.net/projects/deadlock-game-tools](https://sourceforge.net/projects/deadlock-game-tools)
