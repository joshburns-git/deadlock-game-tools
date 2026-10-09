#!/usr/bin/env python3
"""
Deadlock Game Save Editor — unified world map + territory editor.

Copyright (c) 2026 Josh Burns <deadlock-game-tools@joshburns.me>
"""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from colony_sprites import (
    ColonySpriteLibrary,
    RESOURCE_ICON_SIZE,
    TERRAIN_SPRITE_CATALOG,
    TERRAIN_SPRITE_SLOTS,
)
from colony_view import (
    TILE_HALF_H,
    TILE_HALF_W,
    TILE_HEIGHT,
    TILE_WIDTH,
    colony_canvas_size,
    colony_tile_at_point,
    colony_tile_center,
    colony_tile_polygon,
    colony_tiles_draw_order,
)
from map_view import (
    HOVER_OUTLINE,
    MAP_CELL,
    SELECT_OUTLINE,
    draw_territory_selection_outline,
    draw_world_map_terrain_tiles,
    map_cell_rect,
    territory_ids_in_map_order,
)
from world_map_tiles import WorldMapTileLibrary
from world_map_tile_types import (
    WORLD_MAP_TILE_BY_HIGH,
    WORLD_MAP_PALETTE_ORDER,
    WORLD_PALETTE_TERRITORY_SELECT,
    tile_label_for_high,
)
from terrain_catalog import (
    BONUS_CHOICES,
    PALETTE_CHOICES,
    TERRAIN_COLORS,
    TERRAIN_MODIFIER_FLAGS,
    bonus_label,
    format_yield,
    parse_yield,
    split_terrain,
    YIELD_FIELD_LABELS,
    YIELD_NAMES,
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

from deadlock_territory_save import (  # noqa: E402
    MAX_NAME_LEN,
    MAX_TERRITORY_CELLS,
    MIN_TERRITORY_HEIGHT,
    MIN_TERRITORY_WIDTH,
    TERRAIN_KIND_LAND,
    TERRAIN_KIND_SWAMP,
    TERRAIN_KIND_UNSET,
    TERRAIN_KIND_WATER,
    TERRAIN_SUBTYPE_CHOICES,
    TERRAIN_SUBTYPE_PLAINS,
    UNOWNED_OWNER,
    LoadedSave,
    MAX_PLAYER_CREDITS,
    MAX_RESOURCE_QUANTITY,
    STOCKPILE_FIELDS,
    STOCKPILE_LABELS,
    TerritoryInfo,
    TerritoryStockpile,
    outline_cells_for_grid,
    oversized_territory_warnings,
    parse_resource_quantity,
    patch_player_credits,
    patch_territory_metadata,
    regenerate_world_grid_terrain,
    read_grid_cell_values,
    read_grid_cell_value,
    read_player_credits,
    resolve_owner_labels,
    terrain_kind_label,
    terrain_subtype_label,
    territory_bounding_box,
    refresh_world_map_terrain_cells,
    word_for_world_map_terrain_paint,
    write_grid_cell_value,
)

TILE_GRID_LINE = "#333333"
MAP_PAD = 28
MAP_SCROLLBAR_WIDTH = 18
MAP_FRAME_PADDING = 8
APP_TITLE = "Deadlock Game Save Editor"
WORLD_EDITOR_IN_GAME_DISCLAIMER = (
    "Important: Deadlock must be fully closed and restarted before you load your "
    "edited save. Edits will not appear if you load another save first in the same "
    "session. Quit deadlock.exe completely, reopen it, then load your edited .SAV."
)
BOUNDARY_WARNING = (
    f"All territories must be at least {MIN_TERRITORY_WIDTH} tiles wide and "
    f"{MIN_TERRITORY_HEIGHT} tiles tall. It is highly recommended that the upper-left "
    "corner not jut up more than one tile—doing so can cause strange military unit bugs."
)
TERRITORY_TYPE_CHOICES: list[tuple[int, str, str]] = [
    (
        TERRAIN_KIND_LAND,
        "Land",
        "May be colonized, and traversable by land and air units.",
    ),
    (
        TERRAIN_KIND_WATER,
        "Ocean",
        "Traversable by sea and air units, cannot be colonized.",
    ),
    (
        TERRAIN_KIND_SWAMP,
        "Swamp",
        "Appears to function the same as Land.",
    ),
]


def tile_color(tile: ColonyTile | None) -> str:
    if tile is None:
        return "#222222"
    base = split_terrain(tile.terrain).base
    return TERRAIN_COLORS.get(base, "#555555")


class GameSaveEditorApp(tk.Tk):
    def __init__(self, initial_path: Path | None = None) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1400x820")
        self.minsize(1100, 680)

        self.save: LoadedSave | None = None
        self.path: Path | None = None
        self.dirty = False
        self.selected_id: int | None = None
        self._pending_path = initial_path
        self._id_to_record: dict[int, TerritoryInfo] = {}
        self._tile_cache: dict[int, list[ColonyTile]] = {}
        self._metadata_dirty: set[int] = set()
        self._credits_dirty = False
        self._player_credit_vars: list[tk.StringVar] = []
        self._loading_credits = False
        self._stockpile_vars: dict[str, tk.StringVar] = {}
        self._loading_stockpile = False
        self._tile_items: dict[tuple[int, int], int] = {}
        self._territory_labels: list[str] = []
        self._territory_ids: list[int] = []
        self._owner_values: list[tuple[int, str]] = []
        self._loading_properties = False
        self._map_hover: tuple[int, int] | None = None
        self._map_dragging = False
        self._selected_colony_tile: tuple[int, int] | None = None
        self._colony_hover: tuple[int, int] | None = None
        self._loading_colony_tile = False
        self._icon_photo: tk.PhotoImage | None = None
        self._colony_sprite_photos: list[tk.PhotoImage] = []
        self._world_map_photos: list[tk.PhotoImage] = []
        self._world_palette_photos: list[tk.PhotoImage] = []
        self._resource_label_photos: list[tk.PhotoImage] = []
        self._resource_label_widgets: list[tuple[tk.Label, str]] = []
        self.deadlock_install_dir: Path | None = None
        self._colony_sprite_library = ColonySpriteLibrary()
        self._world_map_tile_library = WorldMapTileLibrary()
        self._world_map_tile_assets = self._resource_path("assets")

        self.show_colony_sprites = tk.BooleanVar(value=False)
        self.boundary_tool = tk.StringVar(value="pick")
        self.world_tile_tool = tk.StringVar(value="paint")
        self.world_tile_high = tk.IntVar(value=3)
        self._grid_dirty = False
        self._world_tiles_dirty = False
        self._brush_base = tk.IntVar(value=0)
        self._keep_modifiers = tk.BooleanVar(value=False)
        self._tile_bonus_var = tk.StringVar(value=BONUS_CHOICES[0][1])
        self._modifier_vars = {
            flag: tk.BooleanVar(value=False) for flag, _label in TERRAIN_MODIFIER_FLAGS
        }
        self._yield_vars = {name: tk.StringVar(value="0.00") for name in YIELD_NAMES}
        self._yield_entries: dict[str, ttk.Entry] = {}
        self.territory_var = tk.StringVar()
        self._status = tk.StringVar(value="Open a .SAV file to begin.")

        self._set_window_icon()
        self._try_auto_configure_deadlock()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if not show_splash(
            self,
            self._resource_path("assets", "deadlock-game-tools-image.jpg"),
            geometry="1400x820",
            minsize=(1100, 680),
            on_ready=self._reveal_main,
        ):
            self._reveal_main()

    def _resource_path(self, *parts: str) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS).joinpath(*parts)
        return Path(__file__).resolve().parent.joinpath(*parts)

    def _ui_background(self) -> str:
        return ttk.Style().lookup("TFrame", "background") or "SystemButtonFace"

    def _create_scroll_area(
        self,
        parent: tk.Misc,
        *,
        stretch_vertical: bool = False,
    ) -> tuple[ttk.Frame, tk.Canvas]:
        """Canvas-backed scroll region; returns (inner frame, canvas)."""
        shell = ttk.Frame(parent)
        shell.pack(fill=tk.BOTH, expand=True)
        shell.rowconfigure(0, weight=1)
        shell.columnconfigure(0, weight=1)

        canvas = tk.Canvas(shell, highlightthickness=0, background=self._ui_background())
        y_scroll = ttk.Scrollbar(shell, orient=tk.VERTICAL, command=canvas.yview)
        x_scroll = ttk.Scrollbar(shell, orient=tk.HORIZONTAL, command=canvas.xview)
        canvas.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        inner = ttk.Frame(canvas, padding=8)
        window_id = canvas.create_window((0, 0), window=inner, anchor=tk.NW)

        def _on_inner_configure(_event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event: tk.Event) -> None:
            inner_w = inner.winfo_reqwidth()
            canvas.itemconfigure(window_id, width=max(event.width, inner_w))
            if stretch_vertical:
                inner_h = inner.winfo_reqheight()
                canvas.itemconfigure(window_id, height=max(event.height, inner_h))

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_wheel(event: tk.Event) -> None:
            delta = int(-1 * (event.delta / 120))
            if event.state & 0x1:
                canvas.xview_scroll(delta, "units")
            else:
                canvas.yview_scroll(delta, "units")

        for widget in (shell, canvas, inner):
            widget.bind("<MouseWheel>", _on_wheel)

        return inner, canvas

    def _bind_scroll_wheel(self, widget: tk.Misc, canvas: tk.Canvas) -> None:
        def _on_wheel(event: tk.Event) -> None:
            delta = int(-1 * (event.delta / 120))
            if event.state & 0x1:
                canvas.xview_scroll(delta, "units")
            else:
                canvas.yview_scroll(delta, "units")

        widget.bind("<MouseWheel>", _on_wheel)
        for child in widget.winfo_children():
            self._bind_scroll_wheel(child, canvas)

    def _apply_window_chrome(self) -> None:
        bg = self._ui_background()
        self.configure(bg=bg)

    def _set_window_icon(self) -> None:
        png_path = self._resource_path("assets", "GameSaveEditor.png")
        ico_path = self._resource_path("assets", "GameSaveEditor.ico")
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
        place_main_window(self, "1400x820", (1100, 680))
        self._apply_window_chrome()
        self._main = ttk.Frame(self, padding=8)
        self._main.pack(fill=tk.BOTH, expand=True)
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

        map_menu = tk.Menu(menu, tearoff=0)
        map_menu.add_command(
            label="Regenerate world terrain...",
            command=self._regenerate_world_terrain,
        )
        menu.add_cascade(label="Map", menu=map_menu)

        options_menu = tk.Menu(menu, tearoff=0)
        options_menu.add_checkbutton(
            label="Show in-game sprites",
            variable=self.show_colony_sprites,
            command=self._on_colony_sprites_toggled,
        )
        options_menu.add_command(
            label="Set Deadlock Install Folder...",
            command=self._choose_deadlock_install_dir,
        )
        menu.add_cascade(label="Options", menu=options_menu)

        add_help_menu(
            menu,
            self,
            tool_name=APP_TITLE,
            image_path=self._resource_path("assets", "deadlock-game-tools-image.jpg"),
        )
        self.config(menu=menu)
        self.bind_all("<Control-o>", lambda _e: self._open_dialog())
        self.bind_all("<Control-s>", lambda _e: self._save())
        self.bind_all("<Control-Shift-S>", lambda _e: self._save_as())

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self._main, padding=(0, 0, 0, 6))
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="Open...", command=self._open_dialog).pack(side=tk.LEFT)
        ttk.Button(bar, text="Save", command=self._save).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(bar, text="Save As...", command=self._save_as).pack(side=tk.LEFT, padx=(6, 0))
        self.file_label = ttk.Label(bar, text="No file loaded")
        self.file_label.pack(side=tk.RIGHT)

    def _build_body(self) -> None:
        self._body_pane = ttk.Panedwindow(self._main, orient=tk.HORIZONTAL)
        self._body_pane.pack(fill=tk.BOTH, expand=True)
        self._body_pane.bind("<Configure>", self._update_left_pane_width)

        self._left_pane = ttk.Frame(self._body_pane)
        self._body_pane.add(self._left_pane, weight=0)

        self._map_frame = ttk.LabelFrame(self._left_pane, text="World map", padding=4)
        self._map_frame.pack(fill=tk.BOTH, expand=True)
        self.map_canvas = tk.Canvas(
            self._map_frame,
            background=self._ui_background(),
            highlightthickness=0,
        )
        x_scroll = ttk.Scrollbar(self._map_frame, orient=tk.HORIZONTAL, command=self.map_canvas.xview)
        y_scroll = ttk.Scrollbar(self._map_frame, orient=tk.VERTICAL, command=self.map_canvas.yview)
        self.map_canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        self.map_canvas.grid(row=0, column=0, sticky="nsew")
        x_scroll.grid(row=1, column=0, sticky="ew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        self._map_frame.rowconfigure(0, weight=1)
        self._map_frame.columnconfigure(0, weight=1)
        self.map_canvas.bind("<Button-1>", self._on_map_press)
        self.map_canvas.bind("<B1-Motion>", self._on_map_drag)
        self.map_canvas.bind("<ButtonRelease-1>", self._on_map_release)
        self.map_canvas.bind("<Button-3>", self._on_map_right_click)
        self.map_canvas.bind("<Motion>", self._on_map_motion)
        self.map_canvas.bind("<Leave>", self._on_map_leave)
        for widget in (self._map_frame, self.map_canvas):
            widget.bind("<MouseWheel>", self._on_map_wheel)
            widget.bind("<Button-3>", self._on_map_right_click)

        right = ttk.Frame(self._body_pane)
        self._body_pane.add(right, weight=1)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        picker = ttk.Frame(right)
        picker.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(picker, text="Territory:").pack(side=tk.LEFT)
        self.territory_combo = ttk.Combobox(
            picker,
            textvariable=self.territory_var,
            state="readonly",
            width=48,
        )
        self.territory_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        self.territory_combo.bind("<<ComboboxSelected>>", self._on_territory_combo)

        self._side_notebook = ttk.Notebook(right)
        self._side_notebook.grid(row=1, column=0, sticky="nsew")

        world_tab = ttk.Frame(self._side_notebook)
        boundary_tab = ttk.Frame(self._side_notebook, padding=8)
        territory_tab = ttk.Frame(self._side_notebook)
        self._side_notebook.add(boundary_tab, text="Boundary Editor")
        self._side_notebook.add(world_tab, text="World Editor")
        self._side_notebook.add(territory_tab, text="Territory Editor")
        players_tab = ttk.Frame(self._side_notebook, padding=8)
        self._side_notebook.add(players_tab, text="Players")

        self._build_boundary_editor_tab(boundary_tab)
        world_scroll, _world_scroll_canvas = self._create_scroll_area(world_tab)
        self._build_world_editor_tab(world_scroll)
        territory_tab.rowconfigure(0, weight=1)
        territory_tab.columnconfigure(0, weight=1)
        self._build_territory_editor_panel(territory_tab)
        self._build_players_tab(players_tab)
        self._side_notebook.bind("<<NotebookTabChanged>>", self._on_side_tab_changed)

    def _active_side_tab(self) -> str:
        try:
            tab_id = self._side_notebook.select()
        except tk.TclError:
            return ""
        return str(self._side_notebook.tab(tab_id, "text"))

    def _boundary_editor_active(self) -> bool:
        return self._active_side_tab() == "Boundary Editor"

    def _world_editor_active(self) -> bool:
        return self._active_side_tab() == "World Editor"

    def _world_editor_territory_select_mode(self) -> bool:
        return (
            self._world_editor_active()
            and self.world_tile_high.get() == WORLD_PALETTE_TERRITORY_SELECT
        )

    def _select_territory_at_cell(self, x: int, y: int) -> None:
        assert self.save is not None
        tid = self.save.grid[y][x]
        if tid > 0:
            self._select_territory(tid)
            return
        self._set_status(f"Cell ({x}, {y}) has no territory.")

    def _on_side_tab_changed(self, _event: tk.Event | None = None) -> None:
        self._redraw_map()

    def _build_boundary_editor_tab(self, parent: ttk.Frame) -> None:
        tools = ttk.LabelFrame(parent, text="Boundary tools", padding=8)
        tools.pack(fill=tk.X, anchor=tk.N)
        tools_row = ttk.Frame(tools)
        tools_row.pack(fill=tk.X)
        ttk.Label(tools_row, text="Tool:").pack(side=tk.LEFT)
        ttk.Radiobutton(
            tools_row,
            text="Territory Selector",
            value="pick",
            variable=self.boundary_tool,
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Radiobutton(
            tools_row,
            text="Paint",
            value="paint",
            variable=self.boundary_tool,
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(
            parent,
            text=BOUNDARY_WARNING,
            wraplength=360,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(8, 0))

    def _build_world_editor_tab(self, parent: ttk.Frame) -> None:
        self._ensure_world_map_tiles()

        notice = ttk.LabelFrame(parent, text="In-game testing", padding=8)
        notice.pack(fill=tk.X, anchor=tk.N, pady=(0, 8))
        ttk.Label(
            notice,
            text=WORLD_EDITOR_IN_GAME_DISCLAIMER,
            wraplength=360,
            justify=tk.LEFT,
            foreground="#884444",
        ).pack(anchor=tk.W)

        palette = ttk.LabelFrame(parent, text="Terrain type", padding=8)
        palette.pack(fill=tk.X, anchor=tk.N)
        ttk.Radiobutton(
            palette,
            text="Territory Selector",
            value=WORLD_PALETTE_TERRITORY_SELECT,
            variable=self.world_tile_high,
        ).pack(anchor=tk.W, pady=(0, 8))
        terrain_grid = ttk.Frame(palette)
        terrain_grid.pack(fill=tk.X)
        for index, high in enumerate(WORLD_MAP_PALETTE_ORDER):
            photo = self._world_map_tile_library.palette_photo_for_high(high)
            if photo is None:
                continue
            self._world_palette_photos.append(photo)
            tk.Radiobutton(
                terrain_grid,
                image=photo,
                value=high,
                variable=self.world_tile_high,
                indicatoron=0,
                borderwidth=3,
                selectcolor=self._ui_background(),
            ).grid(row=index // 3, column=index % 3, padx=3, pady=3)

        tools = ttk.LabelFrame(parent, text="Tile tools", padding=8)
        tools.pack(fill=tk.X, pady=(8, 0))
        tools_row = ttk.Frame(tools)
        tools_row.pack(fill=tk.X)
        ttk.Label(tools_row, text="Tool:").pack(side=tk.LEFT)
        ttk.Radiobutton(
            tools_row,
            text="Eyedropper",
            value="pick",
            variable=self.world_tile_tool,
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Radiobutton(
            tools_row,
            text="Paint",
            value="paint",
            variable=self.world_tile_tool,
        ).pack(side=tk.LEFT, padx=(6, 0))

    def _build_players_tab(self, parent: ttk.Frame) -> None:
        players = ttk.LabelFrame(parent, text="Player credits", padding=8)
        players.pack(fill=tk.BOTH, expand=True, anchor="n")
        self._players_panel = ttk.Frame(players)
        self._players_panel.pack(fill=tk.X)

    def _build_properties_panel(self, parent: ttk.Frame) -> None:
        label_pad = (0, 6)

        ttk.Label(parent, text="Id").grid(row=0, column=0, sticky="e", padx=label_pad)
        self.id_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.id_var, state="readonly", width=8).grid(
            row=0, column=1, sticky="w"
        )

        ttk.Label(parent, text="Name").grid(row=1, column=0, sticky="e", padx=label_pad, pady=(6, 0))
        self.name_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.name_var).grid(row=1, column=1, sticky="ew", pady=(6, 0))
        self.name_var.trace_add("write", self._on_name_edited)

        ttk.Label(parent, text="Owner").grid(row=2, column=0, sticky="e", padx=label_pad, pady=(6, 0))
        self.owner_var = tk.StringVar()
        self.owner_combo = ttk.Combobox(parent, textvariable=self.owner_var, state="readonly")
        self.owner_combo.grid(row=2, column=1, sticky="ew", pady=(6, 0))
        self.owner_combo.bind("<<ComboboxSelected>>", self._on_owner_edited)

        ttk.Label(parent, text="Type").grid(row=3, column=0, sticky="ne", padx=label_pad, pady=(6, 0))
        type_frame = ttk.Frame(parent)
        type_frame.grid(row=3, column=1, sticky="ew", pady=(6, 0))
        type_frame.columnconfigure(1, weight=1)
        self.terrain_kind = tk.IntVar(value=TERRAIN_KIND_LAND)
        self._type_radios: list[ttk.Radiobutton] = []
        for index, (value, label, description) in enumerate(TERRITORY_TYPE_CHOICES):
            row = ttk.Frame(type_frame)
            row.grid(row=index, column=0, sticky="ew")
            row.columnconfigure(1, weight=1)
            radio = ttk.Radiobutton(
                row,
                text=label,
                value=value,
                variable=self.terrain_kind,
                command=self._on_type_edited,
            )
            radio.grid(row=0, column=0, sticky="nw")
            ttk.Label(
                row,
                text=description,
                wraplength=360,
                justify=tk.LEFT,
            ).grid(row=0, column=1, sticky="w", padx=(8, 0))
            self._type_radios.append(radio)

        ttk.Label(parent, text="Sub-Type").grid(row=4, column=0, sticky="e", padx=label_pad, pady=(6, 0))
        self._terrain_subtype_var = tk.StringVar(value=TERRAIN_SUBTYPE_CHOICES[0][1])
        self._terrain_subtype_combo = ttk.Combobox(
            parent,
            textvariable=self._terrain_subtype_var,
            values=[label for _code, label in TERRAIN_SUBTYPE_CHOICES],
            state="readonly",
            width=18,
        )
        self._terrain_subtype_combo.grid(row=4, column=1, sticky="w", pady=(6, 0))
        self._terrain_subtype_combo.bind("<<ComboboxSelected>>", self._on_subtype_edited)

        ttk.Label(parent, text="Cells").grid(row=5, column=0, sticky="e", padx=label_pad, pady=(6, 0))
        self.cells_var = tk.StringVar(value="0")
        ttk.Label(parent, textvariable=self.cells_var).grid(row=5, column=1, sticky="w", pady=(6, 0))

        self._stockpile_frame = ttk.LabelFrame(parent, text="Stockpile", padding=6)
        self._stockpile_frame.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._stockpile_entries: dict[str, ttk.Entry] = {}
        for index, (field_name, _offset) in enumerate(STOCKPILE_FIELDS):
            row = index // 2
            col = (index % 2) * 3
            ttk.Label(self._stockpile_frame, text=STOCKPILE_LABELS[field_name]).grid(
                row=row, column=col, sticky="w", padx=(0, 4), pady=2
            )
            icon = self._make_resource_icon(self._stockpile_frame, field_name)
            icon.grid(row=row, column=col + 1, sticky="e", padx=(0, 2), pady=2)
            var = tk.StringVar()
            var.trace_add("write", self._on_stockpile_edited)
            self._stockpile_vars[field_name] = var
            entry = ttk.Entry(self._stockpile_frame, textvariable=var, width=8)
            entry.grid(row=row, column=col + 2, sticky="w", padx=(0, 12), pady=2)
            self._stockpile_entries[field_name] = entry

        parent.columnconfigure(1, weight=1)

    def _build_territory_editor_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(parent)
        notebook.grid(row=0, column=0, sticky="nsew")

        properties_tab = ttk.Frame(notebook)
        properties_tab.rowconfigure(0, weight=1)
        properties_tab.columnconfigure(0, weight=1)
        notebook.add(properties_tab, text="Properties")
        properties_scroll, properties_scroll_canvas = self._create_scroll_area(
            properties_tab,
            stretch_vertical=True,
        )
        self._build_properties_panel(properties_scroll)
        self._bind_scroll_wheel(properties_scroll, properties_scroll_canvas)

        colony_tab = ttk.Frame(notebook)
        colony_tab.rowconfigure(0, weight=1)
        colony_tab.columnconfigure(0, weight=1)
        notebook.add(colony_tab, text="Terrain")

        colony_scroll, colony_scroll_canvas = self._create_scroll_area(
            colony_tab,
            stretch_vertical=True,
        )
        colony_main = ttk.Frame(colony_scroll)
        colony_main.pack(anchor=tk.NW)

        colony_map_row = ttk.Frame(colony_main)
        colony_map_row.pack(fill=tk.X, anchor="w")

        map_frame = ttk.Frame(colony_map_row)
        map_frame.pack(side=tk.LEFT)

        colony_w, colony_h = colony_canvas_size()
        self.tile_canvas = tk.Canvas(
            map_frame,
            width=colony_w,
            height=colony_h,
            bg=self._ui_background(),
            highlightthickness=0,
        )
        self.tile_canvas.pack()
        self.tile_canvas.bind("<Button-1>", self._on_tile_click)
        self.tile_canvas.bind("<B1-Motion>", self._on_tile_drag)
        self.tile_canvas.bind("<Motion>", self._on_colony_motion)
        self.tile_canvas.bind("<Leave>", self._on_colony_leave)

        palette = ttk.LabelFrame(colony_map_row, text="Resource Tiles", padding=8)
        palette.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0), anchor="n")
        for index, (label, base) in enumerate(PALETTE_CHOICES):
            color = TERRAIN_COLORS.get(base, "#666666")
            tk.Radiobutton(
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
            ).grid(row=index, column=0, padx=3, pady=3, sticky="ew")
        palette.columnconfigure(0, weight=1)

        colony_opts = ttk.Frame(colony_main)
        colony_opts.pack(fill=tk.X, pady=(8, 0))
        ttk.Checkbutton(
            colony_opts,
            text="Keep terrain modifiers when painting base type",
            variable=self._keep_modifiers,
        ).pack(anchor="w")
        ttk.Button(
            colony_opts,
            text="Apply brush to all tiles in territory",
            command=self._apply_brush_all,
        ).pack(anchor="w", pady=(6, 0))

        tile_details = ttk.LabelFrame(colony_main, text="Selected tile", padding=8)
        tile_details.pack(fill=tk.X, pady=(8, 0))

        bonus_row = ttk.Frame(tile_details)
        bonus_row.pack(fill=tk.X)
        ttk.Label(bonus_row, text="Resource bonus").pack(side=tk.LEFT)
        self._tile_bonus_combo = ttk.Combobox(
            bonus_row,
            textvariable=self._tile_bonus_var,
            values=[label for _code, label in BONUS_CHOICES],
            state="readonly",
            width=24,
        )
        self._tile_bonus_combo.pack(side=tk.LEFT, padx=(8, 0))
        self._tile_bonus_combo.bind("<<ComboboxSelected>>", self._on_tile_bonus_edited)
        ttk.Label(
            tile_details,
            text=(
                "Adding a resource bonus adds +50% of the associated resource to "
                "the tile's final resource yield value."
            ),
            wraplength=420,
            justify=tk.LEFT,
        ).pack(anchor="w", fill=tk.X, pady=(6, 0))

        yields_frame = ttk.LabelFrame(tile_details, text="Resource yields", padding=(8, 6))
        yields_frame.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(
            yields_frame,
            text="Valid values are from 0–327.",
            wraplength=420,
            justify=tk.LEFT,
        ).pack(anchor="w", fill=tk.X, pady=(0, 6))
        yield_grid = ttk.Frame(yields_frame)
        yield_grid.pack(anchor="w")
        for index, name in enumerate(YIELD_NAMES):
            label = self._make_resource_label(
                yield_grid,
                name,
                YIELD_FIELD_LABELS[name],
            )
            label.grid(
                row=index // 3,
                column=(index % 3) * 2,
                sticky="w",
                padx=(0, 4),
                pady=2,
            )
            entry = ttk.Entry(yield_grid, textvariable=self._yield_vars[name], width=8, state="disabled")
            entry.grid(row=index // 3, column=(index % 3) * 2 + 1, sticky="w", padx=(0, 16), pady=2)
            entry.bind("<FocusOut>", self._on_tile_yields_edited)
            entry.bind("<Return>", self._on_tile_yields_edited)
            self._yield_entries[name] = entry

        modifier_frame = ttk.LabelFrame(
            tile_details,
            text="Terrain modifiers",
            padding=(8, 6),
        )
        modifier_frame.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(
            modifier_frame,
            text="These modifiers have not been properly documented yet.",
            wraplength=420,
            justify=tk.LEFT,
        ).pack(anchor="w", fill=tk.X, pady=(0, 6))
        modifier_checks = ttk.Frame(modifier_frame)
        modifier_checks.pack(anchor="w")
        for flag, label in TERRAIN_MODIFIER_FLAGS:
            ttk.Checkbutton(
                modifier_checks,
                text=label,
                variable=self._modifier_vars[flag],
                command=self._on_tile_modifiers_edited,
            ).pack(side=tk.LEFT, padx=(0, 10))

        self._clear_colony_tile_details()
        self._bind_scroll_wheel(colony_main, colony_scroll_canvas)

        buildings_tab = ttk.Frame(notebook)
        buildings_tab.rowconfigure(0, weight=1)
        buildings_tab.columnconfigure(0, weight=1)
        notebook.add(buildings_tab, text="Buildings")
        buildings_scroll, _buildings_scroll_canvas = self._create_scroll_area(
            buildings_tab,
            stretch_vertical=True,
        )
        ttk.Label(buildings_scroll, text="Coming soon.", font=("Segoe UI", 11)).pack(anchor="w")

        units_tab = ttk.Frame(notebook)
        units_tab.rowconfigure(0, weight=1)
        units_tab.columnconfigure(0, weight=1)
        notebook.add(units_tab, text="Units")
        units_scroll, _units_scroll_canvas = self._create_scroll_area(
            units_tab,
            stretch_vertical=True,
        )
        ttk.Label(units_scroll, text="Coming soon.", font=("Segoe UI", 11)).pack(anchor="w")

    def _build_status(self) -> None:
        ttk.Label(self._main, textvariable=self._status, padding=(0, 4, 0, 0)).pack(fill=tk.X)

    def _try_auto_configure_deadlock(self) -> None:
        candidates = [
            ROOT / "Deadlock",
            Path(__file__).resolve().parent.parent / "Deadlock",
        ]
        for candidate in candidates:
            if not (candidate / "deadlock.exe").is_file() or not (candidate / "SPRITELG.DAT").is_file():
                continue
            if self._configure_deadlock_install(candidate):
                return

    def _configure_deadlock_install(self, deadlock_dir: Path) -> bool:
        colony_error = self._colony_sprite_library.configure(deadlock_dir)
        if colony_error:
            return False
        self.deadlock_install_dir = deadlock_dir.resolve()
        return True

    def _choose_deadlock_install_dir(self) -> bool:
        initial = str(self.deadlock_install_dir) if self.deadlock_install_dir else None
        chosen = filedialog.askdirectory(
            title="Select Deadlock install folder",
            initialdir=initial,
            parent=self,
        )
        if not chosen:
            return False
        deadlock_dir = Path(chosen)
        colony_error = self._colony_sprite_library.configure(deadlock_dir)
        if colony_error:
            messagebox.showerror("Deadlock install folder", colony_error, parent=self)
            return False
        self.deadlock_install_dir = deadlock_dir.resolve()
        self._set_status(f"Deadlock install folder: {self.deadlock_install_dir}")
        self._refresh_resource_label_icons()
        self._redraw_colony()
        self._redraw_map()
        return True

    def _on_colony_sprites_toggled(self) -> None:
        if not self.show_colony_sprites.get():
            self._redraw_colony()
            return
        if not self._colony_sprite_library.is_ready():
            if not self._choose_deadlock_install_dir():
                self.show_colony_sprites.set(False)
                return
        if not TERRAIN_SPRITE_CATALOG:
            self._set_status(
                "In-game sprites enabled. Terrain sprite filenames are still pending — "
                f"awaiting mappings for: {', '.join(TERRAIN_SPRITE_SLOTS.values())}."
            )
        else:
            self._set_status(
                f"In-game sprites enabled from {self.deadlock_install_dir} "
                f"({self._colony_sprite_library.catalog_size()} catalog entries)."
            )
        self._redraw_colony()

    def _ensure_world_map_tiles(self) -> None:
        if self._world_map_tile_library.is_ready():
            return
        self._world_map_tile_library.configure(
            self._world_map_tile_assets,
            master=self,
        )

    def _set_status(self, text: str) -> None:
        self._status.set(text)

    def _make_resource_label(self, parent: tk.Misc, resource_key: str, text: str) -> tk.Label:
        label = tk.Label(parent, text=text, bg=self._ui_background(), anchor="w")
        self._resource_label_widgets.append((label, resource_key))
        self._apply_resource_icon(label, resource_key)
        return label

    def _make_resource_icon(self, parent: tk.Misc, resource_key: str) -> tk.Label:
        label = tk.Label(parent, bg=self._ui_background())
        self._resource_label_widgets.append((label, resource_key))
        self._apply_resource_icon(label, resource_key, icon_only=True)
        return label

    def _apply_resource_icon(
        self,
        label: tk.Label,
        resource_key: str,
        *,
        icon_only: bool = False,
    ) -> None:
        if not self._colony_sprite_library.is_ready():
            label.configure(image="", compound=tk.NONE)
            return
        photo = self._colony_sprite_library.photo_for_resource(
            resource_key,
            RESOURCE_ICON_SIZE,
            self,
        )
        if photo is None:
            label.configure(image="", compound=tk.NONE)
            return
        self._resource_label_photos.append(photo)
        if icon_only:
            label.configure(image=photo, compound=tk.NONE)
        else:
            label.configure(image=photo, compound=tk.LEFT)

    def _refresh_resource_label_icons(self) -> None:
        self._resource_label_photos.clear()
        for label, resource_key in self._resource_label_widgets:
            icon_only = not bool(label.cget("text"))
            self._apply_resource_icon(label, resource_key, icon_only=icon_only)

    def _mark_metadata_dirty(self, territory_id: int) -> None:
        self._metadata_dirty.add(territory_id)
        self._mark_dirty()

    def _regenerate_world_terrain(self) -> None:
        if self.save is None:
            messagebox.showinfo("Regenerate terrain", "Open a save file first.", parent=self)
            return
        if not messagebox.askyesno(
            "Regenerate world terrain",
            "Rebuild every outline cell's terrain bytes from the current map layout, "
            "territory sub-types, and header seed2?\n\n"
            "Use this after editing sub-types or when preparing a save for in-game load.",
            parent=self,
        ):
            return
        try:
            data = regenerate_world_grid_terrain(
                self.save.data,
                self.save.layout,
                self.save.grid,
                self.save.territories,
            )
        except FileNotFoundError as exc:
            messagebox.showerror("Regenerate terrain", str(exc), parent=self)
            return
        self.save = LoadedSave.from_bytes(data, self.path)
        self._id_to_record = {
            territory.territory_id: territory
            for territory in self.save.territories
            if territory.territory_id > 0
        }
        self._mark_dirty()
        self._redraw_map()
        self._set_status("Regenerated world-map terrain bytes for all outline cells.")

    def _mark_dirty(self) -> None:
        self.dirty = True
        self._update_title()

    def _update_title(self) -> None:
        title = APP_TITLE
        if self.path is not None:
            title = f"{self.path.name} — {title}"
        if self.dirty:
            title = f"* {title}"
        self.title(title)
        if self.path is not None:
            self.file_label.configure(text=self.path.name)
        else:
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
        self.path = path
        self.dirty = False
        self._grid_dirty = False
        self._world_tiles_dirty = False
        self.selected_id = None
        self._tile_cache = {}
        self._metadata_dirty.clear()
        self._credits_dirty = False
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
        self._owner_values = loaded.owner_choices()
        self.owner_combo.configure(values=[label for _, label in self._owner_values])
        self._refresh_player_credits_panel(read_player_credits(loaded.data))
        self._refresh_territory_picker()
        self._clear_properties()
        self._redraw_map()
        self._redraw_colony()
        self._update_title()
        self._set_status(
            f"Loaded {loaded.layout.width}x{loaded.layout.height} map; "
            f"{sum(1 for t in self._tile_cache.values() if t)} territories with colony tiles."
        )

    def _filtered_territories(self) -> list[TerritoryInfo]:
        assert self.save is not None
        rows = [t for t in self.save.territories if t.territory_id > 0 and t.name]
        map_order = {
            territory_id: index
            for index, territory_id in enumerate(territory_ids_in_map_order(self.save.grid))
        }
        rows.sort(key=lambda t: map_order.get(t.territory_id, len(map_order)))
        return rows

    def _territory_picker_label(self, territory: TerritoryInfo) -> str:
        owner = self._owner_label_for(territory.owner)
        kind = terrain_kind_label(territory.terrain_kind)
        subtype = terrain_subtype_label(territory.terrain_subtype)
        tile_count = len(self._tile_cache.get(territory.territory_id, []))
        tiles = f"{tile_count} colony tiles" if tile_count else "no colony tiles"
        biome = subtype if subtype != "N/A" else kind
        return (
            f"{territory.territory_id:3d}  {territory.name}  "
            f"({len(territory.cells)} cells, {biome}, {tiles})"
        )

    def _refresh_territory_picker(self) -> None:
        if self.save is None:
            self._territory_labels = []
            self._territory_ids = []
            self.territory_combo.configure(values=[])
            self.territory_var.set("")
            return
        rows = self._filtered_territories()
        self._territory_labels = [self._territory_picker_label(t) for t in rows]
        self._territory_ids = [t.territory_id for t in rows]
        self.territory_combo.configure(values=self._territory_labels)
        if self.selected_id is not None and self.selected_id in self._territory_ids:
            index = self._territory_ids.index(self.selected_id)
            self.territory_var.set(self._territory_labels[index])
        elif self._territory_labels:
            self.territory_var.set("")
        else:
            self.territory_var.set("")

    def _owner_label_for(self, owner: int) -> str:
        for value, label in self._owner_values:
            if value == owner:
                return label
        return "Unowned" if owner == UNOWNED_OWNER else f"Player {owner}"

    def _refresh_player_credits_panel(self, credits: list[int]) -> None:
        for child in self._players_panel.winfo_children():
            child.destroy()
        self._loading_credits = True
        self._player_credit_vars = []
        if self.save is None:
            ttk.Label(self._players_panel, text="Open a save file to edit credits.").pack(
                anchor="w"
            )
            self._loading_credits = False
            return
        labels = resolve_owner_labels(self.save.territories)
        for slot, amount in enumerate(credits):
            row = ttk.Frame(self._players_panel)
            row.pack(fill=tk.X, pady=2)
            player_label = labels.get(slot, f"Player {slot}")
            ttk.Label(row, text=f"Slot {slot} - {player_label}", width=28).pack(
                side=tk.LEFT
            )
            var = tk.StringVar(value=str(amount))
            var.trace_add("write", self._on_credit_edited)
            self._player_credit_vars.append(var)
            ttk.Entry(row, textvariable=var, width=10).pack(side=tk.LEFT)
        self._loading_credits = False

    def _sync_credits_from_ui(self) -> list[int] | None:
        if not self._player_credit_vars:
            return read_player_credits(self.save.data) if self.save else None
        credits: list[int] = []
        for var in self._player_credit_vars:
            parsed = parse_resource_quantity(var.get())
            if parsed is None:
                return None
            credits.append(parsed)
        return credits

    def _on_credit_edited(self, *_args: object) -> None:
        if self._loading_credits or self.save is None:
            return
        credits = self._sync_credits_from_ui()
        if credits is None:
            return
        if credits != read_player_credits(self.save.data):
            self._credits_dirty = True
            self._mark_dirty()

    def _set_stockpile_controls_state(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for entry in self._stockpile_entries.values():
            entry.configure(state=state)

    def _load_stockpile_fields(self, stockpile: TerritoryStockpile) -> None:
        self._loading_stockpile = True
        for field_name, _offset in STOCKPILE_FIELDS:
            value = getattr(stockpile, field_name)
            self._stockpile_vars[field_name].set(str(value))
        self._loading_stockpile = False

    def _stockpile_editable(self, territory: TerritoryInfo) -> bool:
        """Stockpile bytes exist on all territory records; owner/population must not block edits."""
        return territory.territory_id > 0 and bool(territory.name)

    def _commit_selected_stockpile(self) -> bool:
        if self._loading_stockpile or self.save is None or self.selected_id is None:
            return True
        territory = self._id_to_record.get(self.selected_id)
        if territory is None or not self._stockpile_editable(territory):
            return True
        updated = TerritoryStockpile()
        for field_name, _offset in STOCKPILE_FIELDS:
            parsed = parse_resource_quantity(self._stockpile_vars[field_name].get())
            if parsed is None:
                return False
            setattr(updated, field_name, parsed)
        if updated == territory.stockpile:
            return True
        territory.stockpile = updated
        self._mark_metadata_dirty(territory.territory_id)
        return True

    def _on_stockpile_edited(self, *_args: object) -> None:
        if self._loading_stockpile:
            return
        if not self._commit_selected_stockpile():
            self._set_status(f"Stockpile values must be whole numbers from 0 to {MAX_RESOURCE_QUANTITY}.")

    def _owner_value_for_label(self, label: str) -> int | None:
        for value, candidate in self._owner_values:
            if candidate == label:
                return value
        return None

    def _clear_properties(self) -> None:
        self._loading_properties = True
        self.id_var.set("")
        self.name_var.set("")
        self.owner_var.set("")
        self.terrain_kind.set(TERRAIN_KIND_LAND)
        self._terrain_subtype_var.set(TERRAIN_SUBTYPE_CHOICES[0][1])
        self._set_type_controls_state(False)
        self._set_subtype_controls_state(False)
        self.cells_var.set("0")
        self._loading_stockpile = True
        for field_name, _offset in STOCKPILE_FIELDS:
            self._stockpile_vars[field_name].set("")
        self._loading_stockpile = False
        self._set_stockpile_controls_state(False)
        self._loading_properties = False

    def _set_type_controls_state(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for widget in self._type_radios:
            widget.configure(state=state)

    def _set_subtype_controls_state(self, enabled: bool) -> None:
        self._terrain_subtype_combo.configure(state="readonly" if enabled else "disabled")

    def _subtype_code_for_label(self, label: str) -> int | None:
        for code, candidate in TERRAIN_SUBTYPE_CHOICES:
            if candidate == label:
                return code
        return None

    def _subtype_editable(self, terrain_kind: int) -> bool:
        return terrain_kind in (TERRAIN_KIND_LAND, TERRAIN_KIND_SWAMP)

    def _select_territory(self, territory_id: int | None) -> None:
        self._commit_selected_stockpile()
        self.selected_id = territory_id
        self._selected_colony_tile = None
        self._colony_hover = None
        self._clear_colony_tile_details()
        if self.save is None or territory_id is None:
            self._clear_properties()
            self._redraw_map()
            self._redraw_colony()
            return
        territory = self._id_to_record.get(territory_id)
        if territory is None:
            self._clear_properties()
            self._redraw_map()
            self._redraw_colony()
            return
        self.id_var.set(str(territory.territory_id))
        self.name_var.set(territory.name)
        self.owner_var.set(self._owner_label_for(territory.owner))
        self._loading_properties = True
        if territory.terrain_kind in (TERRAIN_KIND_LAND, TERRAIN_KIND_WATER, TERRAIN_KIND_SWAMP):
            self.terrain_kind.set(territory.terrain_kind)
            self._set_type_controls_state(True)
        else:
            self.terrain_kind.set(TERRAIN_KIND_LAND)
            self._set_type_controls_state(False)
            self._set_subtype_controls_state(False)
        if self._subtype_editable(territory.terrain_kind):
            label = terrain_subtype_label(territory.terrain_subtype)
            if label.startswith("Unknown"):
                self._terrain_subtype_var.set(TERRAIN_SUBTYPE_CHOICES[0][1])
            else:
                self._terrain_subtype_var.set(label)
            self._set_subtype_controls_state(True)
        else:
            self._terrain_subtype_var.set("N/A")
            self._set_subtype_controls_state(False)
        self._loading_properties = False
        box_w, box_h = territory_bounding_box(territory.cells)
        self.cells_var.set(f"{len(territory.cells)}  ({box_w}x{box_h})")
        if self._stockpile_editable(territory):
            self._load_stockpile_fields(territory.stockpile)
            self._set_stockpile_controls_state(True)
        else:
            self._loading_stockpile = True
            for field_name, _offset in STOCKPILE_FIELDS:
                self._stockpile_vars[field_name].set("")
            self._loading_stockpile = False
            self._set_stockpile_controls_state(False)
        if territory_id in self._territory_ids:
            index = self._territory_ids.index(territory_id)
            self.territory_var.set(self._territory_labels[index])
        self._redraw_map()
        self._redraw_colony()

    def _on_territory_combo(self, _event: tk.Event | None = None) -> None:
        label = self.territory_var.get()
        if label not in self._territory_labels:
            return
        index = self._territory_labels.index(label)
        self._select_territory(self._territory_ids[index])

    def _on_name_edited(self, *_args: object) -> None:
        if self._loading_properties or self.save is None or self.selected_id is None:
            return
        territory = self._id_to_record[self.selected_id]
        new_name = self.name_var.get()
        if len(new_name.encode("latin-1")) > MAX_NAME_LEN:
            self._set_status(f"Name too long (max {MAX_NAME_LEN} characters).")
            return
        if territory.name != new_name:
            territory.name = new_name
            self._mark_metadata_dirty(territory.territory_id)
            self._refresh_territory_picker()
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
            self._mark_metadata_dirty(territory.territory_id)
            self._owner_values = self.save.owner_choices()
            self.owner_combo.configure(values=[label for _, label in self._owner_values])
            self._refresh_territory_picker()
            self._set_status(f"Set owner for {territory.name!r}.")

    def _on_type_edited(self) -> None:
        if self._loading_properties or self.save is None or self.selected_id is None:
            return
        territory = self._id_to_record[self.selected_id]
        if territory.terrain_kind == TERRAIN_KIND_UNSET:
            return
        new_kind = self.terrain_kind.get()
        if new_kind not in (TERRAIN_KIND_LAND, TERRAIN_KIND_WATER, TERRAIN_KIND_SWAMP):
            return
        if territory.terrain_kind == new_kind:
            return
        territory.terrain_kind = new_kind
        if new_kind == TERRAIN_KIND_WATER:
            territory.terrain_subtype = 0
            self._terrain_subtype_var.set("N/A")
            self._set_subtype_controls_state(False)
        elif self._subtype_editable(new_kind):
            if territory.terrain_subtype == 0:
                territory.terrain_subtype = TERRAIN_SUBTYPE_PLAINS
            self._terrain_subtype_var.set(terrain_subtype_label(territory.terrain_subtype))
            self._set_subtype_controls_state(True)
        self._mark_metadata_dirty(territory.territory_id)
        self._refresh_territory_picker()
        self._set_status(
            f"Set {territory.name!r} to {terrain_kind_label(new_kind)} "
            f"({terrain_subtype_label(territory.terrain_subtype)})."
        )
        self._redraw_colony()

    def _on_subtype_edited(self, _event: tk.Event | None = None) -> None:
        if self._loading_properties or self.save is None or self.selected_id is None:
            return
        territory = self._id_to_record[self.selected_id]
        if not self._subtype_editable(territory.terrain_kind):
            return
        new_subtype = self._subtype_code_for_label(self._terrain_subtype_var.get())
        if new_subtype is None:
            return
        if territory.terrain_subtype == new_subtype:
            return
        territory.terrain_subtype = new_subtype
        self._mark_metadata_dirty(territory.territory_id)
        self._refresh_territory_picker()
        self._set_status(f"Set {territory.name!r} sub-type to {terrain_subtype_label(new_subtype)}.")

    def _selected_territory_is_swamp(self) -> bool:
        if self.selected_id is None:
            return False
        territory = self._id_to_record.get(self.selected_id)
        return territory is not None and territory.terrain_kind == TERRAIN_KIND_SWAMP

    def _map_scrollregion_size(self) -> tuple[int, int] | None:
        if self.save is None:
            return None
        width = self.save.layout.width
        height = self.save.layout.height
        return (
            MAP_PAD * 2 + width * MAP_CELL,
            MAP_PAD * 2 + height * MAP_CELL,
        )

    def _left_pane_target_width(self, body_width: int) -> int | None:
        region = self._map_scrollregion_size()
        if region is None or body_width <= 1:
            return None
        content_w, _content_h = region
        chrome = MAP_FRAME_PADDING * 2 + MAP_SCROLLBAR_WIDTH + 4
        natural_left_w = content_w + chrome
        max_left_w = max(body_width // 2, 320)
        min_right_w = 320
        target = min(natural_left_w, max_left_w, max(body_width - min_right_w, max_left_w))
        return max(target, 240)

    def _update_left_pane_width(self, _event: tk.Event | None = None) -> None:
        if not hasattr(self, "_body_pane"):
            return
        body_width = self._body_pane.winfo_width()
        if body_width <= 1:
            self.after_idle(self._update_left_pane_width)
            return
        target = self._left_pane_target_width(body_width)
        if target is None:
            return
        try:
            current = self._body_pane.sashpos(0)
        except tk.TclError:
            return
        if abs(current - target) > 1:
            self._body_pane.sashpos(0, target)

    def _map_can_scroll(self) -> tuple[bool, bool]:
        region = self._map_scrollregion_size()
        if region is None:
            return False, False
        content_w, content_h = region
        canvas_w = max(self.map_canvas.winfo_width(), 1)
        canvas_h = max(self.map_canvas.winfo_height(), 1)
        return content_w > canvas_w, content_h > canvas_h

    def _on_map_wheel(self, event: tk.Event) -> None:
        if event.state & 0x0001:
            self._on_map_shift_wheel(event)
            return
        can_x, can_y = self._map_can_scroll()
        if not can_y:
            return
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta:
            self.map_canvas.yview_scroll(delta, "units")

    def _on_map_shift_wheel(self, event: tk.Event) -> None:
        can_x, _can_y = self._map_can_scroll()
        if not can_x:
            return
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta:
            self.map_canvas.xview_scroll(delta, "units")

    def _redraw_map(self) -> None:
        self.map_canvas.delete("all")
        if self.save is None:
            return
        width = self.save.layout.width
        height = self.save.layout.height
        pad = MAP_PAD
        total_w = pad * 2 + width * MAP_CELL
        total_h = pad * 2 + height * MAP_CELL
        self.map_canvas.configure(scrollregion=(0, 0, total_w, total_h))
        ui_bg = self._ui_background()
        self.map_canvas.create_rectangle(0, 0, total_w, total_h, fill=ui_bg, outline="")

        for x in range(width):
            px = pad + x * MAP_CELL + MAP_CELL // 2
            self.map_canvas.create_text(px, 10, text=str(x % 10), fill="#888888", font=("Segoe UI", 8))
        for y in range(height):
            py = pad + y * MAP_CELL + MAP_CELL // 2
            self.map_canvas.create_text(12, py, text=f"{y:02d}", fill="#888888", font=("Segoe UI", 8))

        grid_cell_values = read_grid_cell_values(
            self.save.data, self.save.layout, self.save.grid
        )
        self._ensure_world_map_tiles()
        self._world_map_photos.clear()
        draw_world_map_terrain_tiles(
            self.map_canvas,
            self.save.grid,
            grid_cell_values,
            self._world_map_tile_library,
            pad=pad,
            cell_size=MAP_CELL,
            photo_cache=self._world_map_photos,
        )

        if self.selected_id is not None and self.selected_id in self._id_to_record:
            draw_territory_selection_outline(
                self.map_canvas,
                self.save.grid,
                self.selected_id,
                pad=pad,
                cell_size=MAP_CELL,
            )

        for y in range(height):
            for x in range(width):
                if self._map_hover != (x, y):
                    continue
                x0, y0, x1, y1 = map_cell_rect(pad, x, y)
                self.map_canvas.create_rectangle(
                    x0 + 1,
                    y0 + 1,
                    x1 - 2,
                    y1 - 2,
                    outline=HOVER_OUTLINE,
                    width=2,
                    fill="",
                )
        self.after_idle(self._update_left_pane_width)

    def _map_cell_at(self, event: tk.Event) -> tuple[int, int] | None:
        if self.save is None:
            return None
        pad = MAP_PAD
        x = int((self.map_canvas.canvasx(event.x) - pad) // MAP_CELL)
        y = int((self.map_canvas.canvasy(event.y) - pad) // MAP_CELL)
        if 0 <= x < self.save.layout.width and 0 <= y < self.save.layout.height:
            return x, y
        return None

    def _on_map_press(self, event: tk.Event) -> None:
        cell = self._map_cell_at(event)
        if cell is None:
            return
        self._map_dragging = True
        self._apply_map_cell(*cell)

    def _on_map_drag(self, event: tk.Event) -> None:
        if not self._map_dragging:
            return
        cell = self._map_cell_at(event)
        if cell is None:
            return
        if self._boundary_editor_active():
            if self.boundary_tool.get() == "paint":
                self._apply_boundary_map_cell(*cell)
        elif self._world_editor_active():
            if self._world_editor_territory_select_mode():
                return
            if self.world_tile_tool.get() == "paint":
                self._apply_world_tile_cell(*cell)

    def _on_map_release(self, _event: tk.Event) -> None:
        self._map_dragging = False

    def _on_map_right_click(self, event: tk.Event) -> None:
        if not self._world_editor_active() or self._world_editor_territory_select_mode():
            return
        cell = self._map_cell_at(event)
        if cell is None:
            return
        self._select_territory_at_cell(*cell)

    def _on_map_motion(self, event: tk.Event) -> None:
        cell = self._map_cell_at(event)
        if cell == self._map_hover:
            return
        self._map_hover = cell
        self._redraw_map()
        if self.save is None or cell is None:
            return
        x, y = cell
        tid = self.save.grid[y][x]
        if self._world_editor_active():
            word = read_grid_cell_value(self.save.data, self.save.layout, x, y)
            terrain = tile_label_for_high((word >> 8) & 0xFF)
            name = self._id_to_record[tid].name if tid in self._id_to_record else "(empty)"
            self._set_status(f"Cell ({x}, {y}) — {terrain} — id {tid} — {name}")
            return
        name = self._id_to_record[tid].name if tid in self._id_to_record else "(empty)"
        self._set_status(f"Cell ({x}, {y}) — id {tid} — {name}")

    def _on_map_leave(self, _event: tk.Event) -> None:
        self._map_hover = None
        self._redraw_map()

    def _write_grid_cell_value(self, x: int, y: int, word: int) -> None:
        assert self.save is not None
        patched = bytearray(self.save.data)
        write_grid_cell_value(patched, self.save.layout, x, y, word)
        self.save.data = bytes(patched)

    def _apply_map_cell(self, x: int, y: int) -> None:
        if self._boundary_editor_active():
            self._apply_boundary_map_cell(x, y)
        elif self._world_editor_active():
            if self._world_editor_territory_select_mode():
                self._select_territory_at_cell(x, y)
                return
            self._apply_world_tile_cell(x, y)
        else:
            assert self.save is not None
            tid = self.save.grid[y][x]
            if tid > 0:
                self._select_territory(tid)

    def _apply_boundary_map_cell(self, x: int, y: int) -> None:
        assert self.save is not None
        tool = self.boundary_tool.get()
        if tool == "pick":
            tid = self.save.grid[y][x]
            if tid > 0:
                self._select_territory(tid)
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
        self._grid_dirty = True
        self._mark_dirty()
        box_w, box_h = territory_bounding_box(territory.cells)
        self.cells_var.set(f"{len(territory.cells)}  ({box_w}x{box_h})")
        self._redraw_map()
        self._refresh_territory_picker()

    def _apply_world_tile_cell(self, x: int, y: int) -> None:
        assert self.save is not None
        if self._world_editor_territory_select_mode():
            return
        if self.save.grid[y][x] <= 0:
            self._set_status("Terrain type can only be set on occupied map cells.")
            return
        if self.world_tile_tool.get() == "pick":
            word = read_grid_cell_value(self.save.data, self.save.layout, x, y)
            high = (word >> 8) & 0xFF
            picked = high if high in WORLD_MAP_TILE_BY_HIGH else 3
            self.world_tile_high.set(picked)
            self._set_status(f"Picked {tile_label_for_high(picked)}")
            return
        new_high = self.world_tile_high.get()
        current = read_grid_cell_value(self.save.data, self.save.layout, x, y)
        if (current >> 8) & 0xFF == new_high:
            return
        word = word_for_world_map_terrain_paint(
            self.save.data,
            self.save.layout,
            self.save.grid,
            x,
            y,
            new_high,
        )
        patched = bytearray(self.save.data)
        write_grid_cell_value(patched, self.save.layout, x, y, word)
        territory_id = self.save.grid[y][x]
        refresh_cells: set[tuple[int, int]] = {(x, y)}
        width = self.save.layout.width
        height = self.save.layout.height
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height and self.save.grid[ny][nx] == territory_id:
                refresh_cells.add((nx, ny))
        refresh_world_map_terrain_cells(
            patched,
            self.save.layout,
            self.save.grid,
            refresh_cells,
        )
        self.save.data = bytes(patched)
        self._world_tiles_dirty = True
        self._mark_dirty()
        self._redraw_map()

    def _current_tiles(self) -> list[ColonyTile] | None:
        if self.save is None or self.selected_id is None:
            return None
        return self._tile_cache.get(self.selected_id)

    def _set_current_tiles(self, tiles: list[ColonyTile]) -> None:
        if self.selected_id is None:
            return
        self._tile_cache[self.selected_id] = tiles
        self._mark_dirty()
        self._refresh_territory_picker()
        self._redraw_colony()

    def _bonus_code_for_label(self, label: str) -> int:
        for code, candidate in BONUS_CHOICES:
            if candidate == label:
                return code
        return 0

    def _colony_tile_at(self, row: int, col: int) -> ColonyTile | None:
        tiles = self._current_tiles()
        if not tiles:
            return None
        for tile in tiles:
            if tile.row == row and tile.col == col:
                return tile
        return None

    def _replace_colony_tile(self, row: int, col: int, tile: ColonyTile) -> None:
        tiles = self._current_tiles()
        if not tiles:
            return
        updated = [tile if existing.row == row and existing.col == col else existing for existing in tiles]
        self._set_current_tiles(updated)

    def _clear_colony_tile_details(self) -> None:
        self._loading_colony_tile = True
        self._tile_bonus_var.set(BONUS_CHOICES[0][1])
        for var in self._modifier_vars.values():
            var.set(False)
        self._tile_bonus_combo.configure(state="disabled")
        for name in YIELD_NAMES:
            self._yield_vars[name].set("0.00")
        for entry in self._yield_entries.values():
            entry.configure(state="disabled")
        self._loading_colony_tile = False

    def _sync_yield_fields(self, yields: tuple[int, int, int, int, int]) -> None:
        self._loading_colony_tile = True
        for name, value in zip(YIELD_NAMES, yields):
            self._yield_vars[name].set(format_yield(value))
        self._loading_colony_tile = False

    def _commit_selected_tile_yields(self, *, refresh_fields: bool = False) -> None:
        if self._loading_colony_tile or self._selected_colony_tile is None:
            return
        row, col = self._selected_colony_tile
        tile = self._colony_tile_at(row, col)
        if tile is None:
            return
        new_yields = tuple(parse_yield(self._yield_vars[name].get()) for name in YIELD_NAMES)
        if tile.yields != new_yields:
            updated = tile.with_yields(new_yields)
            self._replace_colony_tile(row, col, updated)
            new_yields = updated.yields
        if refresh_fields:
            self._sync_yield_fields(new_yields)

    def _load_colony_tile_details(self, tile: ColonyTile) -> None:
        self._loading_colony_tile = True
        self._tile_bonus_var.set(bonus_label(tile.bonus))
        for name, value in zip(YIELD_NAMES, tile.yields):
            self._yield_vars[name].set(format_yield(value))
        for entry in self._yield_entries.values():
            entry.configure(state="normal")
        for flag, _label in TERRAIN_MODIFIER_FLAGS:
            self._modifier_vars[flag].set(bool(tile.decoded_terrain.flags & flag))
        self._tile_bonus_combo.configure(state="readonly")
        self._loading_colony_tile = False

    def _on_tile_yields_edited(self, _event: tk.Event | None = None) -> None:
        self._commit_selected_tile_yields(refresh_fields=True)

    def _select_colony_tile(self, row: int, col: int) -> None:
        self._commit_selected_tile_yields()
        tile = self._colony_tile_at(row, col)
        if tile is None:
            self._selected_colony_tile = None
            self._clear_colony_tile_details()
            return
        self._selected_colony_tile = (row, col)
        self._load_colony_tile_details(tile)

    def _on_tile_bonus_edited(self, _event: tk.Event | None = None) -> None:
        if self._loading_colony_tile or self._selected_colony_tile is None:
            return
        row, col = self._selected_colony_tile
        tile = self._colony_tile_at(row, col)
        if tile is None:
            return
        bonus = self._bonus_code_for_label(self._tile_bonus_var.get())
        if tile.bonus == bonus:
            return
        updated = tile.with_bonus(bonus)
        self._replace_colony_tile(row, col, updated)
        self._load_colony_tile_details(updated)

    def _on_tile_modifiers_edited(self) -> None:
        if self._loading_colony_tile or self._selected_colony_tile is None:
            return
        row, col = self._selected_colony_tile
        tile = self._colony_tile_at(row, col)
        if tile is None:
            return
        flags = sum(flag for flag, var in self._modifier_vars.items() if var.get())
        if tile.decoded_terrain.flags == flags:
            return
        updated = tile.with_terrain_modifiers(flags)
        self._replace_colony_tile(row, col, updated)
        self._load_colony_tile_details(updated)

    def _draw_colony_tile_modifiers(self, tile: ColonyTile | None, cx: int, cy: int) -> None:
        if tile is None:
            return
        marker_x = cx - TILE_HALF_W + 8
        marker_y = cy - TILE_HALF_H + 4
        for flag, _label in TERRAIN_MODIFIER_FLAGS:
            if tile.decoded_terrain.flags & flag:
                self.tile_canvas.create_text(
                    marker_x,
                    marker_y,
                    text="*",
                    anchor="nw",
                    fill="#ffffaa",
                    font=("Segoe UI", 9, "bold"),
                )
                marker_x += 9

    def _draw_colony_tile_bonus(self, tile: ColonyTile | None, cx: int, cy: int) -> None:
        if tile is None:
            return
        bonus_photo = self._colony_bonus_photo(tile)
        if bonus_photo is not None:
            self.tile_canvas.create_image(
                cx,
                cy,
                image=bonus_photo,
                anchor="center",
            )

    def _colony_bonus_photo(self, tile: ColonyTile) -> tk.PhotoImage | None:
        if not self._colony_sprite_library.is_ready() or tile.bonus <= 0:
            return None
        photo = self._colony_sprite_library.photo_for_bonus(
            tile.bonus,
            TILE_WIDTH,
            TILE_HEIGHT,
            self.tile_canvas,
        )
        if photo is None:
            return None
        self._colony_sprite_photos.append(photo)
        return photo

    def _colony_tile_fill(self, tile: ColonyTile | None) -> str:
        is_swamp = self._selected_territory_is_swamp()
        if (
            self._colony_sprite_library.is_ready()
            and tile is not None
            and self._colony_sprite_library.terrain_sprite_configured(
                split_terrain(tile.terrain).base,
                is_swamp=is_swamp,
            )
        ):
            return self._ui_background()
        return tile_color(tile)

    def _colony_terrain_photo(self, tile: ColonyTile | None) -> tk.PhotoImage | None:
        if not self._colony_sprite_library.is_ready() or tile is None:
            return None
        base = split_terrain(tile.terrain).base
        is_swamp = self._selected_territory_is_swamp()
        if not self._colony_sprite_library.terrain_sprite_configured(base, is_swamp=is_swamp):
            return None
        photo = self._colony_sprite_library.photo_for_terrain(
            base,
            TILE_WIDTH,
            TILE_HEIGHT,
            self.tile_canvas,
            row=tile.row,
            col=tile.col,
            is_swamp=is_swamp,
        )
        if photo is None:
            return None
        self._colony_sprite_photos.append(photo)
        return photo

    def _redraw_colony(self) -> None:
        self.tile_canvas.delete("all")
        self._tile_items.clear()
        self._colony_sprite_photos.clear()
        tiles = self._current_tiles()
        if self.save is None or self.selected_id is None:
            self._selected_colony_tile = None
            self._colony_hover = None
            self._clear_colony_tile_details()
            return
        territory = self._id_to_record.get(self.selected_id)
        if territory is None:
            self._selected_colony_tile = None
            self._colony_hover = None
            self._clear_colony_tile_details()
            return
        if not tiles:
            self._selected_colony_tile = None
            self._colony_hover = None
            self._clear_colony_tile_details()
            return
        grid = grid_from_tiles(tiles)
        tile_layers: list[tuple[int, int, ColonyTile, int, int]] = []
        for row, col in colony_tiles_draw_order():
            cx, cy = colony_tile_center(row, col)
            tile = grid[row][col]
            item = self.tile_canvas.create_polygon(
                colony_tile_polygon(row, col),
                fill=self._colony_tile_fill(tile),
                outline=TILE_GRID_LINE,
            )
            self._tile_items[(row, col)] = item
            tile_layers.append((row, col, tile, cx, cy))

        for _row, _col, tile, cx, cy in tile_layers:
            terrain_photo = self._colony_terrain_photo(tile)
            if terrain_photo is not None:
                self.tile_canvas.create_image(
                    cx,
                    cy,
                    image=terrain_photo,
                    anchor="center",
                )

        for _row, _col, tile, cx, cy in tile_layers:
            self._draw_colony_tile_modifiers(tile, cx, cy)
            self._draw_colony_tile_bonus(tile, cx, cy)

        for row, col, _tile, _cx, _cy in tile_layers:
            if self._colony_hover == (row, col):
                self.tile_canvas.create_polygon(
                    colony_tile_polygon(row, col, inset=3),
                    outline=HOVER_OUTLINE,
                    width=2,
                    fill="",
                )
            elif self._selected_colony_tile == (row, col):
                self.tile_canvas.create_polygon(
                    colony_tile_polygon(row, col, inset=3),
                    outline=SELECT_OUTLINE,
                    width=2,
                    fill="",
                )
        if self._selected_colony_tile is not None:
            if self._colony_tile_at(*self._selected_colony_tile) is None:
                self._selected_colony_tile = None
                self._clear_colony_tile_details()

    def _tile_at(self, event: tk.Event) -> tuple[int, int] | None:
        return colony_tile_at_point(event.x, event.y)

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
                updated.append(tile.with_base_terrain(base, keep_flags=self._keep_modifiers.get()))
            else:
                updated.append(tile)
        if not found:
            return
        self._commit_selected_tile_yields()
        self._selected_colony_tile = (row, col)
        self._set_current_tiles(updated)
        tile = self._colony_tile_at(row, col)
        if tile is not None:
            self._load_colony_tile_details(tile)

    def _on_tile_click(self, event: tk.Event) -> None:
        pos = self._tile_at(event)
        if pos is None:
            return
        row, col = pos
        if self._colony_tile_at(row, col) is None:
            return
        self._commit_selected_tile_yields()
        self._selected_colony_tile = (row, col)
        tile = self._colony_tile_at(row, col)
        if tile is not None:
            self._load_colony_tile_details(tile)
        self._redraw_colony()

    def _on_tile_drag(self, event: tk.Event) -> None:
        pos = self._tile_at(event)
        if pos is not None:
            self._paint_tile(*pos)

    def _on_colony_motion(self, event: tk.Event) -> None:
        hover = self._tile_at(event)
        if hover == self._colony_hover:
            return
        self._colony_hover = hover
        self._redraw_colony()

    def _on_colony_leave(self, _event: tk.Event) -> None:
        if self._colony_hover is None:
            return
        self._colony_hover = None
        self._redraw_colony()

    def _update_brush(self) -> None:
        base = self._brush_base.get()
        for label, code in PALETTE_CHOICES:
            if code == base:
                self._set_status(f"Brush: {label}")
                return

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
            keep_flags=self._keep_modifiers.get(),
            keep_bonus=True,
            keep_yields=True,
        )
        self._set_current_tiles(updated)
        self._set_status(f"Applied {preset} to all tiles.")

    def _build_save_bytes(self) -> bytes | None:
        if self.save is None:
            return None
        if not self._commit_selected_stockpile():
            messagebox.showerror(
                "Cannot save",
                f"Stockpile values must be whole numbers from 0 to {MAX_RESOURCE_QUANTITY}.",
                parent=self,
            )
            return None
        credits = self._sync_credits_from_ui()
        if credits is None:
            messagebox.showerror(
                "Cannot save",
                f"Player credits must be whole numbers from 0 to {MAX_PLAYER_CREDITS}.",
                parent=self,
            )
            return None
        apply_grid = self._grid_dirty
        if apply_grid:
            try:
                warnings = self.save.validate()
            except ValueError as exc:
                messagebox.showerror("Cannot save", str(exc), parent=self)
                return None
            oversized = oversized_territory_warnings(self.save.grid, self.save.territories)
            if oversized:
                detail = "\n".join(f"• {line}" for line in oversized)
                if not messagebox.askokcancel(
                    "Territory exceeds 48-cell limit",
                    "One or more territories exceed Deadlock's recommended "
                    f"{MAX_TERRITORY_CELLS}-cell limit:\n\n"
                    f"{detail}\n\n"
                    "Saving larger territories may overwrite other save data and "
                    "cause Deadlock to crash on load.\n\n"
                    "Save anyway?",
                    parent=self,
                ):
                    return None
            other_warnings = [line for line in warnings if line not in oversized]
            if other_warnings:
                detail = "\n".join(f"• {line}" for line in other_warnings)
                if not messagebox.askyesno(
                    "Validation warnings",
                    "The map has warnings:\n\n"
                    f"{detail}\n\n"
                    "Save anyway?",
                    parent=self,
                ):
                    return None
            data = self.save.to_bytes(strict=False, apply_grid_changes=True)
        elif self._world_tiles_dirty or self._metadata_dirty:
            data = self.save.data
            if self._metadata_dirty:
                data = patch_territory_metadata(
                    data,
                    self.save.layout,
                    self.save.grid,
                    self.save.territories,
                    only_territory_ids=set(self._metadata_dirty),
                )
                data = regenerate_world_grid_terrain(
                    data,
                    self.save.layout,
                    self.save.grid,
                    self.save.territories,
                    only_territory_ids=set(self._metadata_dirty),
                    full_territory=True,
                )
        else:
            data = self.save.data
        if self._credits_dirty:
            try:
                data = patch_player_credits(data, credits)
            except ValueError as exc:
                messagebox.showerror("Cannot save", str(exc), parent=self)
                return None
        return save_tile_tables(data, self.save, self._tile_cache)

    def _confirm_save(self) -> bool:
        if self._grid_dirty:
            return messagebox.askokcancel(
                "Save with map edits?",
                BOUNDARY_WARNING + "\n\nSave this file anyway?",
                parent=self,
            )
        return messagebox.askokcancel(
            "Save changes?",
            "Write game, territory, and colony tile edits to this save file?",
            parent=self,
        )

    def _write_path(self, path: Path) -> bool:
        if not self._confirm_save():
            return False
        data = self._build_save_bytes()
        if data is None:
            return False
        try:
            path.write_bytes(data)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)
            return False
        self.path = path.resolve()
        self.save = LoadedSave.from_bytes(data, self.path)
        self._id_to_record = {
            territory.territory_id: territory
            for territory in self.save.territories
            if territory.territory_id > 0
        }
        self._metadata_dirty.clear()
        self._credits_dirty = False
        self._grid_dirty = False
        self._world_tiles_dirty = False
        self._refresh_player_credits_panel(read_player_credits(self.save.data))
        self.dirty = False
        self._update_title()
        self._set_status(f"Saved {path.name}")
        return True

    def _save(self) -> None:
        if self.save is None:
            messagebox.showinfo("Save", "Open a save file first.", parent=self)
            return
        if self.path is None:
            self._save_as()
            return
        self._write_path(self.path)

    def _save_as(self) -> None:
        if self.save is None:
            messagebox.showinfo("Save As", "Open a save file first.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            title="Save Deadlock save as",
            defaultextension=".SAV",
            filetypes=[("Deadlock saves", "*.SAV"), ("All files", "*.*")],
            initialfile=self.path.name if self.path else "game-edit.SAV",
        )
        if path:
            self._write_path(Path(path))

    def _on_close(self) -> None:
        if self.dirty:
            answer = messagebox.askyesnocancel(
                "Unsaved changes",
                "Save changes before closing?",
                parent=self,
            )
            if answer is None:
                return
            if answer:
                if self.path is not None:
                    if not self._write_path(self.path):
                        return
                else:
                    path = filedialog.asksaveasfilename(
                        title="Save Deadlock save as",
                        defaultextension=".SAV",
                        filetypes=[("Deadlock saves", "*.SAV"), ("All files", "*.*")],
                        initialfile="game-edit.SAV",
                    )
                    if not path or not self._write_path(Path(path)):
                        return
        self.destroy()


def main() -> None:
    initial: Path | None = None
    if len(sys.argv) > 1:
        initial = Path(sys.argv[1])
    GameSaveEditorApp(initial_path=initial).mainloop()


if __name__ == "__main__":
    main()
