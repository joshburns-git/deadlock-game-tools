#!/usr/bin/env python3
"""Graphical Deadlock research editor.

Load a .SAV, toggle which technologies each player has researched, and save.

Usage:
  python research_editor.py
  python research_editor.py "..\\Deadlock\\base.sav"
"""
from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from deadlock_research_save import (
    LoadedTechSave,
    editable_technologies,
    is_researched,
    set_researched,
)


class ResearchEditor(tk.Tk):
    def __init__(self, initial_path: Path | None = None) -> None:
        super().__init__()
        self.title("Deadlock Research Editor")
        self.geometry("1180x760")
        self.minsize(900, 600)

        self.save: LoadedTechSave | None = None
        self.dirty = False
        self._checkboxes: dict[tuple[int, int], tk.BooleanVar] = {}
        self._icon_photo: tk.PhotoImage | None = None

        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._build_status()
        self._set_window_icon()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if initial_path is not None:
            self._load_path(initial_path)

    def _resource_path(self, *parts: str) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS).joinpath(*parts)
        return Path(__file__).resolve().parent.joinpath(*parts)

    def _set_window_icon(self) -> None:
        png_path = self._resource_path("assets", "ResearchEditor.png")
        ico_path = self._resource_path("assets", "ResearchEditor.ico")

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

        if ico_path.is_file() and sys.platform == "win32":
            self.after(0, lambda: self._apply_windows_icon(ico_path))

    def _apply_windows_icon(self, icon_path: Path) -> None:
        """Set title-bar and taskbar icons via Win32 (Tk defaults to a feather)."""
        self.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        if not hwnd:
            return

        icon_path_str = str(icon_path.resolve())
        image_icon = 1
        load_from_file = 0x10
        wm_seticon = 0x80
        icon_small = 0
        icon_big = 1
        sm_cxsmicon = 49
        sm_cxicon = 11

        user32 = ctypes.windll.user32
        # Request high-res assets so Windows can scale down crisply on modern DPI.
        title_size = max(user32.GetSystemMetrics(sm_cxsmicon), 32)
        taskbar_size = max(user32.GetSystemMetrics(sm_cxicon), 64)
        for size, role in ((title_size, icon_small), (taskbar_size, icon_big)):
            handle = user32.LoadImageW(
                None,
                icon_path_str,
                image_icon,
                size,
                size,
                load_from_file,
            )
            if not handle:
                continue
            user32.SendMessageW(hwnd, wm_seticon, role, handle)

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

        ttk.Button(bar, text="Select all (column)", command=self._select_all_column).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Button(bar, text="Clear all (column)", command=self._clear_all_column).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Button(bar, text="Select all (row)", command=self._select_all_row).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Button(bar, text="Clear all (row)", command=self._clear_all_row).pack(side=tk.LEFT)

        self.column_var = tk.StringVar()
        self.column_combo = ttk.Combobox(
            bar,
            textvariable=self.column_var,
            state="readonly",
            width=28,
        )
        self.column_combo.pack(side=tk.LEFT, padx=(16, 4))

        self.row_var = tk.StringVar()
        self.row_combo = ttk.Combobox(
            bar,
            textvariable=self.row_var,
            state="readonly",
            width=34,
        )
        self.row_combo.pack(side=tk.LEFT, padx=(4, 0))

        self.file_label = ttk.Label(bar, text="No file loaded")
        self.file_label.pack(side=tk.RIGHT)

    def _build_body(self) -> None:
        body = ttk.Frame(self, padding=(8, 0, 8, 8))
        body.pack(fill=tk.BOTH, expand=True)

        hint = ttk.Label(
            body,
            text=(
                "Checked = researched for that player slot. "
                "Research is stored per player slot (race shown in each column header), "
                "not as a single global value per race."
            ),
            wraplength=1100,
        )
        hint.pack(anchor=tk.W, pady=(0, 8))

        table_shell = ttk.Frame(body)
        table_shell.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(table_shell, highlightthickness=0)
        y_scroll = ttk.Scrollbar(table_shell, orient=tk.VERTICAL, command=self.canvas.yview)
        x_scroll = ttk.Scrollbar(table_shell, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.table = ttk.Frame(self.canvas)
        self.table_window = self.canvas.create_window((0, 0), window=self.table, anchor=tk.NW)
        self.table.bind("<Configure>", self._on_table_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_shell.rowconfigure(0, weight=1)
        table_shell.columnconfigure(0, weight=1)

    def _build_status(self) -> None:
        self.status_var = tk.StringVar(value="Open a .SAV file to begin.")
        ttk.Label(self, textvariable=self.status_var, anchor=tk.W, padding=(8, 6)).pack(
            fill=tk.X
        )

    def _on_table_configure(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.table_window, width=event.width)

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _update_title(self) -> None:
        name = self.save.path.name if self.save and self.save.path else "unsaved"
        mark = " *" if self.dirty else ""
        self.title(f"Deadlock Research Editor — {name}{mark}")

    def _mark_dirty(self) -> None:
        self.dirty = True
        self._update_title()

    def _open_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Open Deadlock save",
            filetypes=[("Deadlock saves", "*.SAV"), ("All files", "*.*")],
        )
        if path:
            self._load_path(Path(path))

    def _load_path(self, path: Path) -> None:
        try:
            loaded = LoadedTechSave.from_path(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Open failed", str(exc), parent=self)
            return
        self.save = loaded
        self.dirty = False
        self.file_label.configure(text=str(path))
        self._rebuild_table()
        self._update_title()
        self._set_status(
            f"Loaded {path.name} — {loaded.player_count} player(s), "
            f"{len(editable_technologies(loaded.technologies))} technologies."
        )

    def _rebuild_table(self) -> None:
        for child in self.table.winfo_children():
            child.destroy()
        self._checkboxes.clear()

        if self.save is None:
            return

        players = self.save.players
        technologies = editable_technologies(self.save.technologies)

        self.column_combo.configure(values=[player.label for player in players])
        if players:
            self.column_combo.current(0)
        self.row_combo.configure(values=[tech.name for tech in technologies])
        if technologies:
            self.row_combo.current(0)

        ttk.Label(self.table, text="Technology", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky=tk.W, padx=(4, 12), pady=4
        )
        for column, player in enumerate(players, start=1):
            ttk.Label(
                self.table,
                text=player.label,
                font=("Segoe UI", 9, "bold"),
                wraplength=120,
                justify=tk.CENTER,
            ).grid(row=0, column=column, padx=6, pady=4)

        current_tier: int | None = None
        row = 1
        for tech in technologies:
            if tech.tier != current_tier:
                current_tier = tech.tier
                ttk.Separator(self.table, orient=tk.HORIZONTAL).grid(
                    row=row, column=0, columnspan=len(players) + 1, sticky="ew", pady=(8, 4)
                )
                row += 1
                ttk.Label(
                    self.table,
                    text=f"Tier {tech.tier}",
                    font=("Segoe UI", 9, "italic"),
                ).grid(row=row, column=0, columnspan=len(players) + 1, sticky=tk.W, padx=4)
                row += 1

            ttk.Label(
                self.table,
                text=f"{tech.name}  ({tech.cost} cr)",
                wraplength=260,
                justify=tk.LEFT,
            ).grid(row=row, column=0, sticky=tk.W, padx=(4, 12), pady=2)

            for column, player in enumerate(players, start=1):
                var = tk.BooleanVar(value=is_researched(tech, player.slot))
                self._checkboxes[(tech.index, player.slot)] = var

                def on_toggle(
                    *args: object,
                    tech_index: int = tech.index,
                    slot: int = player.slot,
                    variable: tk.BooleanVar = var,
                ) -> None:
                    self._apply_toggle(tech_index, slot, variable.get())

                check = ttk.Checkbutton(self.table, variable=var, command=on_toggle)
                check.grid(row=row, column=column, padx=6, pady=2)
            row += 1

    def _apply_toggle(self, tech_index: int, slot: int, researched: bool) -> None:
        if self.save is None:
            return
        tech = self.save.technologies[tech_index]
        set_researched(tech, slot, researched)
        self._mark_dirty()

    def _selected_player_slot(self) -> int | None:
        if self.save is None or not self.save.players:
            return None
        label = self.column_var.get()
        for player in self.save.players:
            if player.label == label:
                return player.slot
        return self.save.players[0].slot

    def _selected_tech_index(self) -> int | None:
        if self.save is None:
            return None
        name = self.row_var.get()
        for tech in editable_technologies(self.save.technologies):
            if tech.name == name:
                return tech.index
        return None

    def _select_all_column(self) -> None:
        slot = self._selected_player_slot()
        if slot is None or self.save is None:
            return
        for tech in editable_technologies(self.save.technologies):
            set_researched(tech, slot, True)
            var = self._checkboxes.get((tech.index, slot))
            if var is not None:
                var.set(True)
        self._mark_dirty()

    def _clear_all_column(self) -> None:
        slot = self._selected_player_slot()
        if slot is None or self.save is None:
            return
        for tech in editable_technologies(self.save.technologies):
            set_researched(tech, slot, False)
            var = self._checkboxes.get((tech.index, slot))
            if var is not None:
                var.set(False)
        self._mark_dirty()

    def _select_all_row(self) -> None:
        tech_index = self._selected_tech_index()
        if tech_index is None or self.save is None:
            return
        tech = self.save.technologies[tech_index]
        for player in self.save.players:
            set_researched(tech, player.slot, True)
            var = self._checkboxes.get((tech.index, player.slot))
            if var is not None:
                var.set(True)
        self._mark_dirty()

    def _clear_all_row(self) -> None:
        tech_index = self._selected_tech_index()
        if tech_index is None or self.save is None:
            return
        tech = self.save.technologies[tech_index]
        for player in self.save.players:
            set_researched(tech, player.slot, False)
            var = self._checkboxes.get((tech.index, player.slot))
            if var is not None:
                var.set(False)
        self._mark_dirty()

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
            data = self.save.to_bytes()
            path.write_bytes(data)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)
            return False
        self.save.path = path.resolve()
        self.save.data = data
        self.dirty = False
        self.file_label.configure(text=str(self.save.path))
        self._update_title()
        self._set_status(f"Saved {path}")
        return True

    def _on_close(self) -> None:
        if self.dirty:
            answer = messagebox.askyesnocancel(
                "Unsaved changes", "Save changes before exiting?", parent=self
            )
            if answer is None:
                return
            if answer and not self._save():
                return
        self.destroy()


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Deadlock.ResearchEditor.1"
        )
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    _set_windows_app_id()
    args = list(sys.argv[1:] if argv is None else argv)
    initial = Path(args[0]).expanduser() if args else None
    app = ResearchEditor(initial)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
