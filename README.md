![Deadlock Game Tools](deadlock-game-tools-image.jpg)

# Deadlock: Planetary Conquest Game Tools

Tools for *Deadlock: Planetary Conquest* (Accolade, 1996): asset extractors, save-game editors, and more.

Tested only on Windows 10 with Deadlock v1.31.

Each tool lives in its own folder. Windows users can run the pre-built `.exe` in that folder's `dist` directory. The Territory Boundary Editor is Python-only, **experimental**, and has **game-breaking bugs** — do not use it on a save you cannot replace.

| Tool | Folder |
| --- | --- |
| Sprite and Animation Extractor | [Deadlock Tools - Sprite and Animation Extractor](Deadlock%20Tools%20-%20Sprite%20and%20Animation%20Extractor) |
| Research Editor | [Deadlock Tools - Research Editor](Deadlock%20Tools%20-%20Research%20Editor) |
| Territory Boundary Editor (experimental, game-breaking bugs) | [Deadlock Tools - Territory Boundary Editor](Deadlock%20Tools%20-%20Territory%20Boundary%20Editor) |
| Custom City Victory Condition | [Deadlock Tools - Custom City Victory Condition](Deadlock%20Tools%20-%20Custom%20City%20Victory%20Condition) |
| WAIL32 Patch | [Deadlock Tools - WAIL32 Patch](Deadlock%20Tools%20-%20WAIL32%20Patch) — in-place patch of retail `WAIL32.DLL` (keeps background music and colony sounds) |

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
