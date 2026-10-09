![Deadlock Game Tools](deadlock-game-tools-image.jpg)

# Deadlock: Planetary Conquest Game Tools

Tools for *Deadlock: Planetary Conquest* (Accolade, 1996): asset extractors, save-game editors, and more.

Tested only on Windows 10 with Deadlock v1.31.

---

## Project goal — read this first

We are building a **save game editor for Deadlock**. The workflow we care about is:

1. Open a Deadlock **`.SAV` file** in the editor.
2. Make changes (territory properties, colony tiles, world map, etc.).
3. Save the file.
4. **Load that save in Deadlock itself** and confirm the edits appear **in-game**.

That in-game result is the definition of success. If a change looks correct in the editor but not after loading the save in Deadlock, the edit is not done.

### Three things — do not confuse them

| Layer | What it is | Role in this project |
| --- | --- | --- |
| **Deadlock (the game)** | The 1996 game (`deadlock.exe`) | **Ground truth.** Loads a save and renders the world map, colonies, borders, icons, etc. This is what we validate against. |
| **Save file (`.SAV`)** | Binary on disk | **What we edit.** Territory records, world grid bytes, colony tile tables, credits, and so on. The game reads this file on load; our tools patch these bytes. |
| **Game Save Editor** | Python/Tk GUI in this repo | **Editing UI.** Helps view and change save data. Its map preview, selection outline, and debug overlays are **not** Deadlock — they are approximations for convenience. |

**Rules of thumb for development:**

- Fix **save bytes** and **in-game behavior**, not editor preview glitches, unless the preview is actively misleading about what was written.
- After changing write logic, test by saving, loading in Deadlock, and checking the result there.
- **Terrain sub-type / ground art:** quit Deadlock completely before loading the edited save (cold load). In-session save swap keeps stale world-map pixels even when save bytes are correct — see [SAVE_RESEARCH.md — cache rebuild](SAVE_RESEARCH.md#save-load-paths-and-terrain-cache-rebuild-confirmed-oct-2026).
- Editor-only visualization (debug coloring, selection outlines, palette tiles) does not need to match Deadlock pixel-for-pixel; **serialized data** does.

Primary editor: [Deadlock Tools - Game Save Editor](Deadlock%20Tools%20-%20Game%20Save%20Editor). Technical byte layouts and RE notes: [SAVE_RESEARCH.md](SAVE_RESEARCH.md).

---

**Save format research** (colony stockpiles, morale, starvation, low energy, plague icons, territory offsets): [SAVE_RESEARCH.md](SAVE_RESEARCH.md)

Each tool lives in its own folder. Windows users can run the pre-built `.exe` in that folder's `dist` directory when one is available.

| Tool | Folder |
| --- | --- |
| **Game Save Editor** | [Deadlock Tools - Game Save Editor](Deadlock%20Tools%20-%20Game%20Save%20Editor) — unified world map + territory properties + colony tiles |
| Sprite and Animation Extractor | [Deadlock Tools - Sprite and Animation Extractor](Deadlock%20Tools%20-%20Sprite%20and%20Animation%20Extractor) |
| Military Unit Spec Extractor | [Deadlock Tools - Military Unit Spec Extractor](Deadlock%20Tools%20-%20Military%20Unit%20Spec%20Extractor) |
| Research Editor | [Deadlock Tools - Research Editor](Deadlock%20Tools%20-%20Research%20Editor) |
| Custom City Victory Condition | [Deadlock Tools - Custom City Victory Condition](Deadlock%20Tools%20-%20Custom%20City%20Victory%20Condition) |
| WAIL32 Patch | [Deadlock Tools - WAIL32 Patch](Deadlock%20Tools%20-%20WAIL32%20Patch) — in-place patch of retail `WAIL32.DLL` (keeps background music and colony sounds) |
| ~~Territory Boundary Editor~~ (deprecated) | [DEPRECATED - Deadlock Tools - Territory Boundary Editor](DEPRECATED%20-%20Deadlock%20Tools%20-%20Territory%20Boundary%20Editor) — use Game Save Editor instead |
| ~~Save Map Editor~~ (deprecated) | [DEPRECATED - Deadlock Tools - Save Map Editor](DEPRECATED%20-%20Deadlock%20Tools%20-%20Save%20Map%20Editor) — use Game Save Editor instead |

## Screenshots

**Sprite and Animation Extractor**

![Sprite and Animation Extractor](screenshots/screenshot-sprite-exporter.png)

**Research Editor**

![Research Editor](screenshots/screenshot-research-editor.png)

**Custom City Victory Condition**

![Custom City Victory Condition](screenshots/screenshot-custom-city-victory.png)

Project home: https://sourceforge.net/projects/deadlock-game-tools

## Bonus: Deadlock sound and startup crashes on Windows 10/11

On modern Windows, the copy of `WAIL32.DLL` that ships with Deadlock often causes the game to **crash after the intro** (on the main menu) or freeze when initializing audio. This is a game install issue, not something these tools change.

[MildewMan1’s DeadlockFixes](https://github.com/MildewMan1/DeadlockFixes) project provides replacement DLLs that restore music and sound without the crash. You need **both** files in your Deadlock install folder (the same directory as `deadlock.exe`):

1. Back up the original `WAIL32.DLL` (rename it to something like `WAIL32.DLL.bak`).
2. Download these two files:
   - [MSS32.DLL](https://github.com/MildewMan1/DeadlockFixes/raw/refs/heads/master/MSS32.DLL)
   - [WAIL32.dll](https://github.com/MildewMan1/DeadlockFixes/raw/refs/heads/master/WAIL32.dll)
3. Copy both into your Deadlock folder, replacing `WAIL32.DLL` when prompted.

The included `WAIL32.dll` is a small stub that forwards audio calls to `MSS32.DLL`. **Do not copy only the stub** — without `MSS32.DLL` in the same folder, the game will still crash during audio init.

Tested with Deadlock v1.31 on Windows 10. Credit and source: [MildewMan1/DeadlockFixes](https://github.com/MildewMan1/DeadlockFixes).

## License

See the license file in each tool folder when one is present. The Sprite and Animation Extractor is MIT.
