#!/usr/bin/env python3
"""Graphical Deadlock territory map editor.

Load a .SAV, paint territory boundaries on a grid, and edit territory names and owners.

Usage:
  python territory_map_editor.py
  python territory_map_editor.py "..\\Deadlock\\territory-edits.SAV"
"""
from __future__ import annotations

import colorsys
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from deadlock_territory_save import (
    MAX_NAME_LEN,
    MIN_TERRITORY_HEIGHT,
    MIN_TERRITORY_WIDTH,
    UNOWNED_OWNER,
    LoadedSave,
    TerritoryInfo,
    outline_cells_for_grid,
    territory_bounding_box,
    territory_cells_error,
)

CELL_SIZE = 22
GRID_LINE = "#333333"
EMPTY_COLOR = "#1a1a1a"
SELECT_OUTLINE = "#ffffff"
HOVER_OUTLINE = "#ffcc00"


def territory_color(territory_id: int) -> str:
    if territory_id <= 0:
        return EMPTY_COLOR
    hue = (territory_id * 0.61803398875) % 1.0
    red, green, blue = colorsys.hls_to_rgb(hue, 0.42, 0.72)
    return f"#{int(red * 255):02x}{int(green * 255):02x}{int(blue * 255):02x}"


class TerritoryMapEditor(tk.Tk):
    def __init__(self, initial_path: Path | None = None) -> None:
        super().__init__()
        self.title("Deadlock Territory Map Editor")
        self.geometry("1180x760")
        self.minsize(900, 600)

        self.save: LoadedSave | None = None
        self.dirty = False
        self.selected_id: int | None = None
        self.tool = tk.StringVar(value="paint")
        self.show_labels = tk.BooleanVar(value=False)
        self._dragging = False
        self._hover: tuple[int, int] | None = None
        self._cell_items: dict[tuple[int, int], int] = {}
        self._label_items: dict[tuple[int, int], int] = {}
        self._id_to_record: dict[int, TerritoryInfo] = {}

        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._build_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if initial_path is not None:
            self._load_path(initial_path)

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="Open...", accelerator="Ctrl+O", command=self._open_dialog)
        file_menu.add_command(label="Save", accelerator="Ctrl+S", command=self._save)
        file_menu.add_command(label="Save As...", accelerator="Ctrl+Shift+S", command=self._save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menu.add_cascade(label="File", menu=file_menu)
        self.config(menu=menu)
        self.bind_all("<Control-o>", lambda _e: self._open_dialog())
        self.bind_all("<Control-s>", lambda _e: self._save())
        self.bind_all("<Control-Shift-S>", lambda _e: self._save_as())

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill=tk.X)
        ttk.Label(bar, text="Tool:").pack(side=tk.LEFT)
        ttk.Radiobutton(bar, text="Paint", value="paint", variable=self.tool).pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(bar, text="Eyedropper", value="pick", variable=self.tool).pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(bar, text="Eraser", value="erase", variable=self.tool).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(bar, text="Show id labels", variable=self.show_labels, command=self._redraw_map).pack(
            side=tk.LEFT, padx=(16, 0)
        )
        self.file_label = ttk.Label(bar, text="No file loaded")
        self.file_label.pack(side=tk.RIGHT)

    def _build_body(self) -> None:
        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        map_frame = ttk.LabelFrame(body, text="Map", padding=4)
        body.add(map_frame, weight=3)

        self.canvas = tk.Canvas(map_frame, background="#111111", highlightthickness=0)
        x_scroll = ttk.Scrollbar(map_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        y_scroll = ttk.Scrollbar(map_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        x_scroll.grid(row=1, column=0, sticky="ew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        map_frame.rowconfigure(0, weight=1)
        map_frame.columnconfigure(0, weight=1)

        self.canvas.bind("<Button-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Leave>", self._on_canvas_leave)

        side = ttk.LabelFrame(body, text="Territory", padding=8)
        body.add(side, weight=1)

        filter_row = ttk.Frame(side)
        filter_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(filter_row, text="Filter:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._refresh_territory_list())
        ttk.Entry(filter_row, textvariable=self.filter_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        list_frame = ttk.Frame(side)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.territory_list = tk.Listbox(list_frame, exportselection=False, activestyle="dotbox")
        list_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.territory_list.yview)
        self.territory_list.configure(yscrollcommand=list_scroll.set)
        self.territory_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.territory_list.bind("<<ListboxSelect>>", self._on_list_select)

        props = ttk.LabelFrame(side, text="Properties", padding=8)
        props.pack(fill=tk.X, pady=(8, 0))

        ttk.Label(props, text="Id").grid(row=0, column=0, sticky="w")
        self.id_var = tk.StringVar()
        ttk.Entry(props, textvariable=self.id_var, state="readonly", width=8).grid(row=0, column=1, sticky="w")

        ttk.Label(props, text="Name").grid(row=1, column=0, sticky="nw", pady=(6, 0))
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(props, textvariable=self.name_var)
        self.name_entry.grid(row=1, column=1, sticky="ew", pady=(6, 0))
        self.name_var.trace_add("write", self._on_name_edited)

        ttk.Label(props, text="Owner").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.owner_var = tk.StringVar()
        self.owner_combo = ttk.Combobox(props, textvariable=self.owner_var, state="readonly")
        self.owner_combo.grid(row=2, column=1, sticky="ew", pady=(6, 0))
        self.owner_combo.bind("<<ComboboxSelected>>", self._on_owner_edited)

        ttk.Label(props, text="Cells").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.cells_var = tk.StringVar(value="0")
        ttk.Label(props, textvariable=self.cells_var).grid(row=3, column=1, sticky="w", pady=(6, 0))

        props.columnconfigure(1, weight=1)

        hint = (
            "Paint: click or drag to assign cells to the selected territory.\n"
            "Eyedropper: click a cell to select its territory.\n"
            "Eraser: click or drag to clear cells (unassigned).\n"
            f"Each territory must span at least {MIN_TERRITORY_WIDTH} columns "
            f"and {MIN_TERRITORY_HEIGHT} rows or Deadlock crashes on load."
        )
        ttk.Label(side, text=hint, wraplength=260, justify=tk.LEFT).pack(fill=tk.X, pady=(8, 0))

    def _build_status(self) -> None:
        self.status = ttk.Label(self, anchor="w", padding=(8, 4))
        self.status.pack(fill=tk.X)
        self._set_status("Open a .SAV file to begin.")

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def _mark_dirty(self) -> None:
        self.dirty = True
        self._update_title()

    def _update_title(self) -> None:
        base = "Deadlock Territory Map Editor"
        if self.save and self.save.path:
            name = self.save.path.name
            prefix = "*" if self.dirty else ""
            self.title(f"{prefix}{name} — {base}")
            self.file_label.configure(text=str(self.save.path))
        else:
            self.title(base)
            self.file_label.configure(text="No file loaded")

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
        self.dirty = False
        self.selected_id = None
        self._rebuild_territory_index()
        self._refresh_owner_choices()
        self._refresh_territory_list()
        self._redraw_map()
        self._clear_properties()
        self._update_title()
        self._set_status(
            f"Loaded {loaded.layout.width}x{loaded.layout.height} map, "
            f"{loaded.layout.territory_count} territory records."
        )

    def _rebuild_territory_index(self) -> None:
        assert self.save is not None
        self._id_to_record = {
            territory.territory_id: territory for territory in self.save.territories if territory.territory_id > 0
        }

    def _refresh_owner_choices(self) -> None:
        assert self.save is not None
        self._owner_values = self.save.owner_choices()
        labels = [label for _, label in self._owner_values]
        self.owner_combo.configure(values=labels)

    def _owner_label_for(self, owner: int) -> str:
        for value, label in getattr(self, "_owner_values", []):
            if value == owner:
                return label
        return "Unowned" if owner == UNOWNED_OWNER else f"Player {owner}"

    def _owner_value_for_label(self, label: str) -> int | None:
        for value, candidate in getattr(self, "_owner_values", []):
            if candidate == label:
                return value
        return None

    def _filtered_territories(self) -> list[TerritoryInfo]:
        assert self.save is not None
        needle = self.filter_var.get().strip().lower()
        rows = [t for t in self.save.territories if t.territory_id > 0 and t.name]
        if needle:
            rows = [
                t
                for t in rows
                if needle in t.name.lower() or needle in str(t.territory_id)
            ]
        rows.sort(key=lambda t: (-len(t.cells), t.territory_id))
        return rows

    def _refresh_territory_list(self) -> None:
        if self.save is None:
            return
        self.territory_list.delete(0, tk.END)
        self._list_index_to_id: list[int] = []
        for territory in self._filtered_territories():
            owner = self._owner_label_for(territory.owner)
            label = f"{territory.territory_id:3d}  {territory.name}  ({len(territory.cells)}, {owner})"
            self.territory_list.insert(tk.END, label)
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

    def _clear_properties(self) -> None:
        self.id_var.set("")
        self.name_var.set("")
        self.owner_var.set("")
        self.cells_var.set("0")

    def _select_territory(self, territory_id: int | None) -> None:
        self.selected_id = territory_id
        if self.save is None or territory_id is None:
            self._clear_properties()
            self._redraw_map()
            return
        territory = self._id_to_record.get(territory_id)
        if territory is None:
            self._clear_properties()
            self._redraw_map()
            return
        self.id_var.set(str(territory.territory_id))
        self.name_var.set(territory.name)
        self.owner_var.set(self._owner_label_for(territory.owner))
        box_w, box_h = territory_bounding_box(territory.cells)
        self.cells_var.set(f"{len(territory.cells)}  ({box_w}x{box_h})")
        self._select_list_by_id(territory_id)
        self._redraw_map()

    def _on_list_select(self, _event: tk.Event | None = None) -> None:
        selection = self.territory_list.curselection()
        if not selection:
            return
        territory_id = self._list_index_to_id[selection[0]]
        self._select_territory(territory_id)

    def _on_name_edited(self, *_args: object) -> None:
        if self.save is None or self.selected_id is None:
            return
        territory = self._id_to_record[self.selected_id]
        new_name = self.name_var.get()
        if len(new_name.encode("latin-1")) > MAX_NAME_LEN:
            self._set_status(f"Name too long (max {MAX_NAME_LEN} characters).")
            return
        if territory.name != new_name:
            territory.name = new_name
            self._mark_dirty()
            self._refresh_territory_list()
            self._set_status(f"Renamed territory {territory.territory_id}.")

    def _on_owner_edited(self, _event: tk.Event | None = None) -> None:
        if self.save is None or self.selected_id is None:
            return
        territory = self._id_to_record[self.selected_id]
        owner = self._owner_value_for_label(self.owner_var.get())
        if owner is None:
            return
        if territory.owner != owner:
            territory.owner = owner
            self._mark_dirty()
            self._refresh_owner_choices()
            self._refresh_territory_list()
            self._set_status(f"Set owner for {territory.name!r}.")

    def _redraw_map(self) -> None:
        self.canvas.delete("all")
        self._cell_items.clear()
        self._label_items.clear()
        if self.save is None:
            return

        width = self.save.layout.width
        height = self.save.layout.height
        pad = 28
        total_w = pad * 2 + width * CELL_SIZE
        total_h = pad * 2 + height * CELL_SIZE
        self.canvas.configure(scrollregion=(0, 0, total_w, total_h))

        for x in range(width):
            px = pad + x * CELL_SIZE + CELL_SIZE // 2
            self.canvas.create_text(px, 10, text=str(x % 10), fill="#888888", font=("Segoe UI", 8))
        for y in range(height):
            py = pad + y * CELL_SIZE + CELL_SIZE // 2
            self.canvas.create_text(12, py, text=f"{y:02d}", fill="#888888", font=("Segoe UI", 8))

        selected_cells: set[tuple[int, int]] = set()
        if self.selected_id is not None:
            territory = self._id_to_record.get(self.selected_id)
            if territory is not None:
                selected_cells = set(territory.cells)

        for y in range(height):
            for x in range(width):
                tid = self.save.grid[y][x]
                x0 = pad + x * CELL_SIZE
                y0 = pad + y * CELL_SIZE
                x1 = x0 + CELL_SIZE - 1
                y1 = y0 + CELL_SIZE - 1
                fill = territory_color(tid)
                outline = GRID_LINE
                width_px = 1
                if self._hover == (x, y):
                    outline = HOVER_OUTLINE
                    width_px = 2
                if (x, y) in selected_cells:
                    outline = SELECT_OUTLINE
                    width_px = 2
                item = self.canvas.create_rectangle(
                    x0, y0, x1, y1, fill=fill, outline=outline, width=width_px
                )
                self._cell_items[(x, y)] = item
                if self.show_labels.get() and tid > 0:
                    label = self.canvas.create_text(
                        (x0 + x1) // 2,
                        (y0 + y1) // 2,
                        text=str(tid),
                        fill="#000000" if tid % 2 == 0 else "#ffffff",
                        font=("Segoe UI", 7),
                    )
                    self._label_items[(x, y)] = label

    def _canvas_to_cell(self, event: tk.Event) -> tuple[int, int] | None:
        if self.save is None:
            return None
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        pad = 28
        x = int((canvas_x - pad) // CELL_SIZE)
        y = int((canvas_y - pad) // CELL_SIZE)
        width = self.save.layout.width
        height = self.save.layout.height
        if 0 <= x < width and 0 <= y < height:
            return x, y
        return None

    def _apply_cell(self, x: int, y: int) -> None:
        assert self.save is not None
        if self.tool.get() == "pick":
            tid = self.save.grid[y][x]
            if tid > 0:
                self._select_territory(tid)
            return
        if self.tool.get() == "erase":
            old_id = self.save.grid[y][x]
            if old_id == 0:
                return
            if old_id in self._id_to_record:
                territory = self._id_to_record[old_id]
                remaining_cells = [
                    (cx, cy)
                    for cy, row in enumerate(self.save.grid)
                    for cx, tid in enumerate(row)
                    if tid == old_id and (cx, cy) != (x, y)
                ]
                error = territory_cells_error(
                    remaining_cells,
                    label=f"{territory.name} (id {old_id})",
                )
                if error:
                    self._set_status(f"Cannot erase: {error}")
                    return
            self.save.grid[y][x] = 0
            if old_id in self._id_to_record:
                territory = self._id_to_record[old_id]
                grid_cells = [
                    (cx, cy)
                    for cy, row in enumerate(self.save.grid)
                    for cx, tid in enumerate(row)
                    if tid == old_id
                ]
                territory.cells = outline_cells_for_grid(territory.cells, grid_cells)
            self._mark_dirty()
            if self.selected_id == old_id:
                territory = self._id_to_record[old_id]
                box_w, box_h = territory_bounding_box(territory.cells)
                self.cells_var.set(f"{len(territory.cells)}  ({box_w}x{box_h})")
            self._paint_cell(x, y)
            self._refresh_territory_list()
            return
        if self.selected_id is None:
            self._set_status("Select a territory to paint with.")
            return
        if self.save.grid[y][x] == self.selected_id:
            return
        old_id = self.save.grid[y][x]
        self.save.grid[y][x] = self.selected_id
        if old_id > 0 and old_id in self._id_to_record:
            old_grid_cells = [
                (cx, cy)
                for cy, row in enumerate(self.save.grid)
                for cx, tid in enumerate(row)
                if tid == old_id
            ]
            self._id_to_record[old_id].cells = outline_cells_for_grid(
                self._id_to_record[old_id].cells,
                old_grid_cells,
            )
        territory = self._id_to_record[self.selected_id]
        if (x, y) not in territory.cells:
            grid_cells = [
                (cx, cy)
                for cy, row in enumerate(self.save.grid)
                for cx, tid in enumerate(row)
                if tid == self.selected_id
            ]
            territory.cells = outline_cells_for_grid(territory.cells, grid_cells)
        self._mark_dirty()
        box_w, box_h = territory_bounding_box(territory.cells)
        self.cells_var.set(f"{len(territory.cells)}  ({box_w}x{box_h})")
        self._paint_cell(x, y)
        self._refresh_territory_list()

    def _paint_cell(self, x: int, y: int) -> None:
        assert self.save is not None
        tid = self.save.grid[y][x]
        item = self._cell_items.get((x, y))
        if item is None:
            return
        self.canvas.itemconfigure(item, fill=territory_color(tid))
        if self.show_labels.get():
            if (x, y) in self._label_items:
                self.canvas.delete(self._label_items[(x, y)])
            if tid > 0:
                coords = self.canvas.coords(item)
                label = self.canvas.create_text(
                    (coords[0] + coords[2]) / 2,
                    (coords[1] + coords[3]) / 2,
                    text=str(tid),
                    fill="#000000" if tid % 2 == 0 else "#ffffff",
                    font=("Segoe UI", 7),
                )
                self._label_items[(x, y)] = label

    def _on_canvas_press(self, event: tk.Event) -> None:
        cell = self._canvas_to_cell(event)
        if cell is None:
            return
        self._dragging = True
        self._apply_cell(*cell)

    def _on_canvas_drag(self, event: tk.Event) -> None:
        if not self._dragging:
            return
        cell = self._canvas_to_cell(event)
        if cell is not None:
            self._apply_cell(*cell)

    def _on_canvas_release(self, _event: tk.Event) -> None:
        self._dragging = False

    def _on_canvas_motion(self, event: tk.Event) -> None:
        cell = self._canvas_to_cell(event)
        if cell == self._hover:
            return
        self._hover = cell
        self._redraw_map()
        if self.save is None or cell is None:
            return
        x, y = cell
        tid = self.save.grid[y][x]
        name = self._id_to_record.get(tid).name if tid in self._id_to_record else "(empty)"
        self._set_status(f"Cell ({x}, {y}) — id {tid} — {name}")

    def _on_canvas_leave(self, _event: tk.Event) -> None:
        self._hover = None
        self._redraw_map()

    def _save(self) -> bool:
        if self.save is None:
            return False
        if self.save.path is None:
            return self._save_as()
        return self._write_path(self.save.path)

    def _save_as(self) -> bool:
        if self.save is None:
            return False
        path = filedialog.asksaveasfilename(
            title="Save Deadlock save",
            defaultextension=".SAV",
            filetypes=[("Deadlock saves", "*.SAV"), ("All files", "*.*")],
            initialfile=self.save.path.name if self.save.path else "edited.SAV",
        )
        if not path:
            return False
        return self._write_path(Path(path))

    def _write_path(self, path: Path) -> bool:
        assert self.save is not None
        try:
            warnings = self.save.validate()
        except ValueError as exc:
            messagebox.showerror("Cannot save", str(exc), parent=self)
            return False
        if warnings:
            detail = "\n".join(f"• {line}" for line in warnings)
            if not messagebox.askyesno(
                "Validation warnings",
                "The map has warnings:\n\n"
                f"{detail}\n\n"
                "Save anyway?",
                parent=self,
            ):
                return False
        try:
            data = self.save.to_bytes(strict=False)
            path.write_bytes(data)
        except ValueError as exc:
            messagebox.showerror("Cannot save", str(exc), parent=self)
            return False
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)
            return False
        self.save.path = path.resolve()
        self.save.data = data
        self.dirty = False
        self._update_title()
        self._set_status(f"Saved {path}")
        return True

    def _on_close(self) -> None:
        if self.dirty:
            answer = messagebox.askyesnocancel("Unsaved changes", "Save changes before exiting?", parent=self)
            if answer is None:
                return
            if answer and not self._save():
                return
        self.destroy()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    initial = Path(args[0]).expanduser() if args else None
    app = TerritoryMapEditor(initial)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
