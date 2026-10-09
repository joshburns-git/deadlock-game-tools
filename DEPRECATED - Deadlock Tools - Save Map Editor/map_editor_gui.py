#!/usr/bin/env python3
"""
Deadlock Save Map Editor — GUI

Paint colony terrain tiles (6x6) inside each territory record.

Copyright (c) 2026 Josh Burns <deadlock-game-tools@joshburns.me>
"""
from __future__ import annotations

import colorsys
import ctypes
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from terrain_catalog import (
    PALETTE_CHOICES,
    TERRAIN_COLORS,
    WATER_TERRAIN,
    bonus_label,
    format_yield,
    split_terrain,
)
from territory_tiles import (
    ColonyTile,
    apply_base_preset,
    grid_from_tiles,
    read_tiles_for_territory,
    save_tile_tables,
)
from tool_splash import add_help_menu, place_main_window, show_splash

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_DIR = ROOT / "DEPRECATED - Deadlock Tools - Territory Boundary Editor"
if not getattr(sys, "frozen", False) and BOUNDARY_DIR.is_dir():
    boundary_path = str(BOUNDARY_DIR)
    if boundary_path not in sys.path:
        sys.path.insert(0, boundary_path)

from deadlock_territory_save import LoadedSave, TerritoryInfo  # noqa: E402

MAP_CELL = 20
TILE_CELL = 42
GRID_LINE = "#333333"
INTERNAL_GRID_LINE = "#252525"
BOUNDARY_WIDTH = 2
EMPTY_COLOR = "#1a1a1a"
SELECT_OUTLINE = "#ffffff"
HOVER_OUTLINE = "#ffcc00"


def territory_color(territory_id: int) -> str:
    if territory_id <= 0:
        return EMPTY_COLOR
    hue = (territory_id * 0.61803398875) % 1.0
    red, green, blue = colorsys.hls_to_rgb(hue, 0.42, 0.72)
    return f"#{int(red * 255):02x}{int(green * 255):02x}{int(blue * 255):02x}"


def draw_territory_map_cells(
    canvas: tk.Canvas,
    grid: list[list[int]],
    *,
    pad: int,
    cell_size: int,
) -> None:
    """Fill cells and draw light internal lines vs thicker territory boundaries."""
    height = len(grid)
    width = len(grid[0]) if height else 0

    for y in range(height):
        for x in range(width):
            x0 = pad + x * cell_size
            y0 = pad + y * cell_size
            canvas.create_rectangle(
                x0,
                y0,
                x0 + cell_size - 1,
                y0 + cell_size - 1,
                fill=territory_color(grid[y][x]),
                outline="",
            )

    for y in range(height):
        for x in range(width):
            tid = grid[y][x]
            x0 = pad + x * cell_size
            y0 = pad + y * cell_size
            x_edge = pad + (x + 1) * cell_size
            y_edge = y0 + cell_size

            if x + 1 < width:
                neighbor = grid[y][x + 1]
                if tid == neighbor:
                    canvas.create_line(
                        x_edge,
                        y0,
                        x_edge,
                        y_edge,
                        fill=INTERNAL_GRID_LINE,
                        width=1,
                    )
                else:
                    canvas.create_line(
                        x_edge,
                        y0,
                        x_edge,
                        y_edge,
                        fill=GRID_LINE,
                        width=BOUNDARY_WIDTH,
                    )
            else:
                canvas.create_line(
                    x_edge,
                    y0,
                    x_edge,
                    y_edge,
                    fill=GRID_LINE,
                    width=BOUNDARY_WIDTH,
                )

            if y + 1 < height:
                neighbor = grid[y + 1][x]
                if tid == neighbor:
                    canvas.create_line(
                        x0,
                        y_edge,
                        x_edge,
                        y_edge,
                        fill=INTERNAL_GRID_LINE,
                        width=1,
                    )
                else:
                    canvas.create_line(
                        x0,
                        y_edge,
                        x_edge,
                        y_edge,
                        fill=GRID_LINE,
                        width=BOUNDARY_WIDTH,
                    )
            else:
                canvas.create_line(
                    x0,
                    y_edge,
                    x_edge,
                    y_edge,
                    fill=GRID_LINE,
                    width=BOUNDARY_WIDTH,
                )


def tile_color(tile: ColonyTile | None) -> str:
    if tile is None:
        return "#222222"
    base = split_terrain(tile.terrain).base
    return TERRAIN_COLORS.get(base, "#555555")


class SaveMapEditorApp(tk.Tk):
    def __init__(self, initial_path: Path | None = None) -> None:
        super().__init__()
        self.title("Deadlock Save Map Editor")
        self.geometry("1280x780")
        self.minsize(980, 640)

        self.save: LoadedSave | None = None
        self.path: Path | None = None
        self.dirty = False
        self.selected_id: int | None = None
        self._icon_photo: tk.PhotoImage | None = None
        self._pending_path = initial_path
        self._id_to_record: dict[int, TerritoryInfo] = {}
        self._tile_cache: dict[int, list[ColonyTile]] = {}
        self._tile_items: dict[tuple[int, int], int] = {}
        self._brush_base = tk.IntVar(value=0)
        self._keep_flags = tk.BooleanVar(value=False)
        self._tile_info = tk.StringVar(value="Open a .SAV file to begin.")
        self._status = tk.StringVar(value="Ready")

        self._set_window_icon()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if not show_splash(
            self,
            self._resource_path("assets", "deadlock-game-tools-image.jpg"),
            geometry="1280x780",
            minsize=(980, 640),
            on_ready=self._reveal_main,
        ):
            self._reveal_main()

    def _resource_path(self, *parts: str) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS).joinpath(*parts)
        return Path(__file__).resolve().parent.joinpath(*parts)

    def _set_window_icon(self) -> None:
        png_path = self._resource_path("assets", "MapEditor.png")
        ico_path = self._resource_path("assets", "MapEditor.ico")
        if png_path.is_file():
            try:
                self._icon_photo = tk.PhotoImage(file=str(png_path))
                self.iconphoto(True, self._icon_photo)
            except tk.TclError:
                self._icon_photo = None
        if ico_path.is_file():
            for setter in (
                lambda: self.iconbitmap(str(ico_path)),
                lambda: self.iconbitmap(default=str(ico_path)),
            ):
                try:
                    setter()
                    break
                except tk.TclError:
                    continue

    def _reveal_main(self) -> None:
        place_main_window(self, "1280x780", (980, 640))
        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._build_status()
        if self._pending_path is not None:
            self._load_path(self._pending_path)
            self._pending_path = None

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="Open...", accelerator="Ctrl+O", command=self._open_dialog)
        file_menu.add_command(label="Save", accelerator="Ctrl+S", command=self._save)
        file_menu.add_command(label="Save As...", accelerator="Ctrl+Shift+S", command=self._save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menu.add_cascade(label="File", menu=file_menu)
        add_help_menu(
            menu,
            self,
            tool_name="Save Map Editor",
            image_path=self._resource_path("assets", "deadlock-game-tools-image.jpg"),
        )
        self.config(menu=menu)
        self.bind_all("<Control-o>", lambda _e: self._open_dialog())
        self.bind_all("<Control-s>", lambda _e: self._save())
        self.bind_all("<Control-Shift-S>", lambda _e: self._save_as())

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="Open...", command=self._open_dialog).pack(side=tk.LEFT)
        ttk.Button(bar, text="Save", command=self._save).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(bar, text="Save As...", command=self._save_as).pack(side=tk.LEFT, padx=(6, 0))
        self.file_label = ttk.Label(bar, text="No file loaded")
        self.file_label.pack(side=tk.RIGHT)

    def _build_body(self) -> None:
        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        map_frame = ttk.LabelFrame(body, text="World map (click a territory)", padding=4)
        body.add(map_frame, weight=3)
        self.map_canvas = tk.Canvas(map_frame, background="#111111", highlightthickness=0)
        x_scroll = ttk.Scrollbar(map_frame, orient=tk.HORIZONTAL, command=self.map_canvas.xview)
        y_scroll = ttk.Scrollbar(map_frame, orient=tk.VERTICAL, command=self.map_canvas.yview)
        self.map_canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        self.map_canvas.grid(row=0, column=0, sticky="nsew")
        x_scroll.grid(row=1, column=0, sticky="ew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        map_frame.rowconfigure(0, weight=1)
        map_frame.columnconfigure(0, weight=1)
        self.map_canvas.bind("<Button-1>", self._on_map_click)
        self.map_canvas.bind("<Motion>", self._on_map_motion)
        self.map_canvas.bind("<Leave>", lambda _e: self._redraw_map())

        side = ttk.Frame(body)
        body.add(side, weight=2)

        list_frame = ttk.LabelFrame(side, text="Territories", padding=6)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.territory_list = tk.Listbox(list_frame, exportselection=False, height=10)
        list_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.territory_list.yview)
        self.territory_list.configure(yscrollcommand=list_scroll.set)
        self.territory_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.territory_list.bind("<<ListboxSelect>>", self._on_list_select)

        tile_frame = ttk.LabelFrame(side, text="Colony tiles (6×6)", padding=8)
        tile_frame.pack(fill=tk.X, pady=(8, 0))
        self.tile_canvas = tk.Canvas(tile_frame, width=TILE_CELL * 6 + 2, height=TILE_CELL * 6 + 2, bg="#111111", highlightthickness=0)
        self.tile_canvas.pack()
        self.tile_canvas.bind("<Button-1>", self._on_tile_click)
        self.tile_canvas.bind("<B1-Motion>", self._on_tile_drag)

        palette = ttk.LabelFrame(side, text="Terrain brush", padding=8)
        palette.pack(fill=tk.X, pady=(8, 0))
        for index, (label, base) in enumerate(PALETTE_CHOICES):
            color = TERRAIN_COLORS.get(base, "#666666")
            rb = tk.Radiobutton(
                palette,
                text=label,
                value=base,
                variable=self._brush_base,
                indicatoron=0,
                width=14,
                bg=color,
                selectcolor=color,
                activebackground=color,
                command=self._update_brush,
            )
            rb.grid(row=index // 4, column=index % 4, padx=3, pady=3, sticky="ew")
        for col in range(4):
            palette.columnconfigure(col, weight=1)

        opts = ttk.Frame(side)
        opts.pack(fill=tk.X, pady=(8, 0))
        ttk.Checkbutton(opts, text="Keep terrain flags when painting", variable=self._keep_flags).pack(anchor="w")
        ttk.Button(opts, text="Apply brush to all tiles in territory", command=self._apply_brush_all).pack(
            anchor="w", pady=(6, 0)
        )
        ttk.Label(side, textvariable=self._tile_info, wraplength=420, justify=tk.LEFT).pack(
            anchor="w", fill=tk.X, pady=(8, 0)
        )

    def _build_status(self) -> None:
        ttk.Label(self, textvariable=self._status, padding=(8, 4)).pack(fill=tk.X)

    def _update_brush(self) -> None:
        base = self._brush_base.get()
        for label, code in PALETTE_CHOICES:
            if code == base:
                self._set_status(f"Brush: {label}")
                return

    def _open_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Open Deadlock save",
            filetypes=[("Deadlock saves", "*.sav *.SAV"), ("All files", "*.*")],
        )
        if path:
            self._load_path(Path(path))

    def _load_path(self, path: Path) -> None:
        try:
            loaded = LoadedSave.from_path(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Open failed", str(exc), parent=self)
            return
        self.save = loaded
        self.path = path
        self.dirty = False
        self.selected_id = None
        self._tile_cache = {}
        self._id_to_record = {
            territory.territory_id: territory
            for territory in loaded.territories
            if territory.territory_id > 0
        }
        for territory in loaded.territories:
            if territory.territory_id <= 0:
                continue
            tiles = read_tiles_for_territory(loaded, territory)
            if tiles:
                self._tile_cache[territory.territory_id] = tiles
        self._refresh_territory_list()
        self._redraw_map()
        self._redraw_tiles()
        self.file_label.configure(text=path.name)
        self._update_title()
        self._set_status(
            f"Loaded {loaded.layout.width}x{loaded.layout.height} map; "
            f"{sum(1 for t in self._tile_cache.values() if t)} territories with tile tables."
        )

    def _refresh_territory_list(self) -> None:
        self.territory_list.delete(0, tk.END)
        self._list_index_to_id: list[int] = []
        if self.save is None:
            return
        rows = [t for t in self.save.territories if t.territory_id > 0 and t.name]
        rows.sort(key=lambda t: (-len(t.cells), t.territory_id))
        for territory in rows:
            tile_count = len(self._tile_cache.get(territory.territory_id, []))
            suffix = f"{tile_count} tiles" if tile_count else "no tile table"
            self.territory_list.insert(
                tk.END,
                f"{territory.territory_id:3d}  {territory.name}  ({suffix})",
            )
            self._list_index_to_id.append(territory.territory_id)
        if self.selected_id is not None:
            self._select_list_by_id(self.selected_id)

    def _select_list_by_id(self, territory_id: int) -> None:
        for index, tid in enumerate(self._list_index_to_id):
            if tid == territory_id:
                self.territory_list.selection_clear(0, tk.END)
                self.territory_list.selection_set(index)
                self.territory_list.see(index)
                return

    def _select_territory(self, territory_id: int | None) -> None:
        self.selected_id = territory_id
        if territory_id is not None:
            self._select_list_by_id(territory_id)
        self._redraw_map()
        self._redraw_tiles()

    def _on_list_select(self, _event: tk.Event | None = None) -> None:
        selection = self.territory_list.curselection()
        if not selection:
            return
        self._select_territory(self._list_index_to_id[selection[0]])

    def _current_tiles(self) -> list[ColonyTile] | None:
        if self.save is None or self.selected_id is None:
            return None
        return self._tile_cache.get(self.selected_id)

    def _set_current_tiles(self, tiles: list[ColonyTile]) -> None:
        if self.selected_id is None:
            return
        self._tile_cache[self.selected_id] = tiles
        self._mark_dirty()
        self._refresh_territory_list()
        self._redraw_tiles()

    def _redraw_map(self) -> None:
        self.map_canvas.delete("all")
        if self.save is None:
            return
        width = self.save.layout.width
        height = self.save.layout.height
        pad = 24
        total_w = pad * 2 + width * MAP_CELL
        total_h = pad * 2 + height * MAP_CELL
        self.map_canvas.configure(scrollregion=(0, 0, total_w, total_h))
        selected_cells: set[tuple[int, int]] = set()
        if self.selected_id is not None:
            territory = self._id_to_record.get(self.selected_id)
            if territory is not None:
                selected_cells = set(territory.cells)
        hover = getattr(self, "_map_hover", None)

        draw_territory_map_cells(
            self.map_canvas,
            self.save.grid,
            pad=pad,
            cell_size=MAP_CELL,
        )

        for y in range(height):
            for x in range(width):
                x0 = pad + x * MAP_CELL
                y0 = pad + y * MAP_CELL
                x1 = x0 + MAP_CELL - 1
                y1 = y0 + MAP_CELL - 1
                if hover == (x, y):
                    self.map_canvas.create_rectangle(
                        x0,
                        y0,
                        x1,
                        y1,
                        outline=HOVER_OUTLINE,
                        width=2,
                        fill="",
                    )
                elif (x, y) in selected_cells:
                    self.map_canvas.create_rectangle(
                        x0,
                        y0,
                        x1,
                        y1,
                        outline=SELECT_OUTLINE,
                        width=2,
                        fill="",
                    )

    def _map_cell_at(self, event: tk.Event) -> tuple[int, int] | None:
        if self.save is None:
            return None
        pad = 24
        x = int((self.map_canvas.canvasx(event.x) - pad) // MAP_CELL)
        y = int((self.map_canvas.canvasy(event.y) - pad) // MAP_CELL)
        if 0 <= x < self.save.layout.width and 0 <= y < self.save.layout.height:
            return x, y
        return None

    def _on_map_click(self, event: tk.Event) -> None:
        cell = self._map_cell_at(event)
        if cell is None or self.save is None:
            return
        x, y = cell
        tid = self.save.grid[y][x]
        if tid > 0:
            self._select_territory(tid)

    def _on_map_motion(self, event: tk.Event) -> None:
        cell = self._map_cell_at(event)
        if cell != getattr(self, "_map_hover", None):
            self._map_hover = cell
            self._redraw_map()

    def _redraw_tiles(self) -> None:
        self.tile_canvas.delete("all")
        self._tile_items.clear()
        tiles = self._current_tiles()
        if self.save is None or self.selected_id is None:
            self._tile_info.set("Select a territory on the map or in the list.")
            return
        territory = self._id_to_record.get(self.selected_id)
        if territory is None:
            self._tile_info.set("Territory not found.")
            return
        if not tiles:
            self._tile_info.set(
                f"{territory.name} has no colony tile table yet "
                "(uncolonized or not initialized in this save)."
            )
            return
        grid = grid_from_tiles(tiles)
        for row in range(6):
            for col in range(6):
                x0 = col * TILE_CELL
                y0 = row * TILE_CELL
                x1 = x0 + TILE_CELL - 1
                y1 = y0 + TILE_CELL - 1
                tile = grid[row][col]
                item = self.tile_canvas.create_rectangle(
                    x0,
                    y0,
                    x1,
                    y1,
                    fill=tile_color(tile),
                    outline=GRID_LINE,
                )
                self._tile_items[(row, col)] = item
                if tile is not None and tile.bonus:
                    self.tile_canvas.create_text(
                        x0 + 4,
                        y0 + 4,
                        text="*",
                        anchor="nw",
                        fill="#ffffaa",
                        font=("Segoe UI", 10, "bold"),
                    )
        self._tile_info.set(f"{territory.name}: {len(tiles)} tile rows loaded. Click to paint.")

    def _tile_at(self, event: tk.Event) -> tuple[int, int] | None:
        col = int(event.x // TILE_CELL)
        row = int(event.y // TILE_CELL)
        if 0 <= row < 6 and 0 <= col < 6:
            return row, col
        return None

    def _paint_tile(self, row: int, col: int) -> None:
        tiles = self._current_tiles()
        if not tiles:
            return
        base = self._brush_base.get()
        updated: list[ColonyTile] = []
        found = False
        for tile in tiles:
            if tile.row == row and tile.col == col:
                found = True
                updated.append(tile.with_base_terrain(base, keep_flags=self._keep_flags.get()))
            else:
                updated.append(tile)
        if not found:
            return
        self._set_current_tiles(updated)
        tile = next(t for t in updated if t.row == row and t.col == col)
        decoded = split_terrain(tile.terrain)
        self._tile_info.set(
            f"({row},{col}) {decoded.label}  bonus={bonus_label(tile.bonus)}  "
            f"E/F/W/Ir/En={'/'.join(format_yield(v) for v in tile.yields)}"
        )

    def _on_tile_click(self, event: tk.Event) -> None:
        pos = self._tile_at(event)
        if pos is not None:
            self._paint_tile(*pos)

    def _on_tile_drag(self, event: tk.Event) -> None:
        pos = self._tile_at(event)
        if pos is not None:
            self._paint_tile(*pos)

    def _apply_brush_all(self) -> None:
        tiles = self._current_tiles()
        if not tiles:
            messagebox.showinfo("No tiles", "This territory has no tile table to edit.", parent=self)
            return
        base = self._brush_base.get()
        preset = next(label for label, code in PALETTE_CHOICES if code == base)
        if not messagebox.askyesno(
            "Apply to all tiles",
            f"Set every tile in this territory to {preset}?",
            parent=self,
        ):
            return
        key_map = {
            "Clear": "clear",
            "Rough": "rough",
            "Lightly Wooded": "light-woods",
            "Heavily Wooded": "forest",
            "Rocky": "rocky",
            "Bog": "bog",
            "Wetland": "wetland",
            "Water": "water",
        }
        updated = apply_base_preset(
            tiles,
            key_map[preset],
            keep_flags=self._keep_flags.get(),
            keep_bonus=True,
            keep_yields=True,
        )
        self._set_current_tiles(updated)
        self._set_status(f"Applied {preset} to all tiles.")

    def _save_bytes(self) -> bytes | None:
        if self.save is None:
            return None
        return save_tile_tables(self.save.data, self.save, self._tile_cache)

    def _save(self) -> None:
        if self.save is None or self.path is None:
            messagebox.showinfo("Save", "Open a save file first.", parent=self)
            return
        data = self._save_bytes()
        if data is None:
            return
        try:
            self.path.write_bytes(data)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)
            return
        self.save = LoadedSave.from_bytes(data, self.path)
        self.dirty = False
        self._update_title()
        self._set_status(f"Saved {self.path.name}")

    def _save_as(self) -> None:
        if self.save is None:
            messagebox.showinfo("Save As", "Open a save file first.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            title="Save Deadlock save as",
            defaultextension=".sav",
            filetypes=[("Deadlock saves", "*.sav *.SAV"), ("All files", "*.*")],
            initialfile=self.path.name if self.path else "map-edit.sav",
        )
        if not path:
            return
        data = self._save_bytes()
        if data is None:
            return
        dest = Path(path)
        try:
            dest.write_bytes(data)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)
            return
        self.path = dest
        self.save = LoadedSave.from_bytes(data, dest)
        self.dirty = False
        self.file_label.configure(text=dest.name)
        self._update_title()
        self._set_status(f"Saved {dest.name}")

    def _mark_dirty(self) -> None:
        self.dirty = True
        self._update_title()

    def _update_title(self) -> None:
        title = "Deadlock Save Map Editor"
        if self.path is not None:
            title = f"{self.path.name} - {title}"
        if self.dirty:
            title = f"* {title}"
        self.title(title)

    def _set_status(self, text: str) -> None:
        self._status.set(text)

    def _on_close(self) -> None:
        if self.dirty:
            answer = messagebox.askyesnocancel(
                "Unsaved changes",
                "Save tile edits before closing?",
                parent=self,
            )
            if answer is None:
                return
            if answer:
                self._save()
                if self.dirty:
                    return
        self.destroy()


def main() -> None:
    initial: Path | None = None
    if len(sys.argv) > 1:
        initial = Path(sys.argv[1])
    SaveMapEditorApp(initial_path=initial).mainloop()


if __name__ == "__main__":
    main()
