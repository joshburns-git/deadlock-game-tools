"""Research grid for the Game Save Editor Players tab."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from deadlock_research_save import (
    LoadedTechSave,
    editable_technologies,
    is_researched,
    set_researched,
)
from ui_util import tk_configure_resized


class ResearchPanel:
    def __init__(self, parent: ttk.Widget, *, on_dirty: Callable[[], None]) -> None:
        self._on_dirty = on_dirty
        self._tech_save: LoadedTechSave | None = None
        self._column_labels: list[str] | None = None
        self._checkboxes: dict[tuple[int, int], tk.BooleanVar] = {}
        self._initial_researched: dict[tuple[int, int], bool] = {}

        shell = ttk.LabelFrame(parent, text="Research", padding=8)
        shell.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        self._placeholder = ttk.Label(shell, text="Open a save file to edit research.")
        self._placeholder.pack(anchor=tk.W)

        self._content = ttk.Frame(shell)
        # packed when a save is loaded

        hint = ttk.Label(
            self._content,
            text=(
                "Checked = researched for that player slot. "
                "Use All / None / Reset on each row (technology) or column (player slot)."
            ),
            wraplength=520,
            justify=tk.LEFT,
        )
        hint.pack(anchor=tk.W, pady=(0, 6))

        table_shell = ttk.Frame(self._content)
        table_shell.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(table_shell, highlightthickness=0, height=320)
        y_scroll = ttk.Scrollbar(table_shell, orient=tk.VERTICAL, command=self.canvas.yview)
        x_scroll = ttk.Scrollbar(table_shell, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.table = ttk.Frame(self.canvas)
        self.table_window = self.canvas.create_window((0, 0), window=self.table, anchor=tk.NW)
        self._table_configure_size: list[tuple[int, int] | None] = [None]
        self._canvas_configure_size: list[tuple[int, int] | None] = [None]
        self.table.bind("<Configure>", self._on_table_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_scroll_wheel(self.canvas)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_shell.rowconfigure(0, weight=1)
        table_shell.columnconfigure(0, weight=1)

    @property
    def tech_save(self) -> LoadedTechSave | None:
        return self._tech_save

    def clear(self) -> None:
        self._tech_save = None
        self._column_labels = None
        self._checkboxes.clear()
        self._initial_researched.clear()
        for child in self.table.winfo_children():
            child.destroy()
        self._content.pack_forget()
        self._placeholder.pack(anchor=tk.W)

    def load(
        self,
        tech_save: LoadedTechSave,
        *,
        column_labels: list[str] | None = None,
    ) -> None:
        self._tech_save = tech_save
        self._column_labels = column_labels
        self._initial_researched.clear()
        for tech in editable_technologies(tech_save.technologies):
            for player in tech_save.players:
                key = (tech.index, player.slot)
                self._initial_researched[key] = is_researched(tech, player.slot)
        self._placeholder.pack_forget()
        self._content.pack(fill=tk.BOTH, expand=True)
        self._rebuild_table()

    def _on_table_configure(self, event: tk.Event) -> None:
        if not tk_configure_resized(event, self._table_configure_size):
            return
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        if not tk_configure_resized(event, self._canvas_configure_size):
            return
        # Widen with content so horizontal scrolling works; still fill narrow viewports.
        table_w = self.table.winfo_reqwidth()
        self.canvas.itemconfigure(self.table_window, width=max(event.width, table_w))

    def _bind_scroll_wheel(self, widget: tk.Widget) -> None:
        def on_wheel(event: tk.Event) -> None:
            delta = int(-1 * (event.delta / 120))
            if event.state & 0x1:
                self.canvas.xview_scroll(delta, "units")
            else:
                self.canvas.yview_scroll(delta, "units")

        widget.bind("<MouseWheel>", on_wheel)
        for child in widget.winfo_children():
            self._bind_scroll_wheel(child)

    def _mark_dirty(self) -> None:
        self._on_dirty()

    def _rebuild_table(self) -> None:
        for child in self.table.winfo_children():
            child.destroy()
        self._checkboxes.clear()
        if self._tech_save is None:
            return

        players = self._tech_save.players
        technologies = editable_technologies(self._tech_save.technologies)
        name_col = 1
        first_player_col = 2
        table_cols = len(players) + 2

        ttk.Label(self.table, text="", width=1).grid(row=0, column=0, padx=(0, 4))
        ttk.Label(self.table, text="Technology", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=name_col, sticky=tk.NW, padx=(4, 12), pady=4
        )
        header_font = ("Segoe UI", 9, "bold")
        role_font = ("Segoe UI", 8)
        for column, player in enumerate(players, start=first_player_col):
            if self._column_labels and player.slot < len(self._column_labels):
                header_text = self._column_labels[player.slot]
            else:
                header_text = f"({player.slot}) {player.display_race}"
            header = ttk.Frame(self.table)
            ttk.Label(header, text=header_text, font=header_font).pack(anchor=tk.CENTER)
            role = "(human)" if player.is_human else "(bot)"
            ttk.Label(header, text=role, font=role_font).pack(anchor=tk.CENTER)
            col_actions = ttk.Frame(header)
            ttk.Button(
                col_actions,
                text="All",
                width=5,
                command=lambda slot=player.slot: self._set_player_column(slot, True),
            ).pack(side=tk.LEFT, padx=(0, 2))
            ttk.Button(
                col_actions,
                text="None",
                width=5,
                command=lambda slot=player.slot: self._set_player_column(slot, False),
            ).pack(side=tk.LEFT, padx=(0, 2))
            ttk.Button(
                col_actions,
                text="Reset",
                width=5,
                command=lambda slot=player.slot: self._reset_player_column(slot),
            ).pack(side=tk.LEFT)
            col_actions.pack(anchor=tk.CENTER, pady=(4, 0))
            header.grid(row=0, column=column, padx=6, pady=4)

        current_tier: int | None = None
        row = 1
        for tech in technologies:
            if tech.tier != current_tier:
                current_tier = tech.tier
                ttk.Separator(self.table, orient=tk.HORIZONTAL).grid(
                    row=row, column=0, columnspan=table_cols, sticky="ew", pady=(8, 4)
                )
                row += 1
                ttk.Label(
                    self.table,
                    text=f"Tier {tech.tier}",
                    font=("Segoe UI", 9, "italic"),
                ).grid(row=row, column=0, columnspan=table_cols, sticky=tk.W, padx=4)
                row += 1

            actions = ttk.Frame(self.table)
            ttk.Button(
                actions,
                text="All",
                width=5,
                command=lambda idx=tech.index: self._set_tech_row(idx, True),
            ).pack(side=tk.LEFT, padx=(0, 2))
            ttk.Button(
                actions,
                text="None",
                width=5,
                command=lambda idx=tech.index: self._set_tech_row(idx, False),
            ).pack(side=tk.LEFT, padx=(0, 2))
            ttk.Button(
                actions,
                text="Reset",
                width=5,
                command=lambda idx=tech.index: self._reset_tech_row(idx),
            ).pack(side=tk.LEFT)
            actions.grid(row=row, column=0, sticky=tk.W, padx=(0, 4), pady=2)

            ttk.Label(
                self.table,
                text=f"{tech.name}  ({tech.cost} cr)",
                wraplength=220,
                justify=tk.LEFT,
            ).grid(row=row, column=name_col, sticky=tk.W, padx=(4, 12), pady=2)

            for column, player in enumerate(players, start=first_player_col):
                var = tk.BooleanVar(value=is_researched(tech, player.slot))
                self._checkboxes[(tech.index, player.slot)] = var

                def on_toggle(
                    *,
                    tech_index: int = tech.index,
                    slot: int = player.slot,
                    variable: tk.BooleanVar = var,
                ) -> None:
                    self._apply_toggle(tech_index, slot, variable.get())

                ttk.Checkbutton(self.table, variable=var, command=on_toggle).grid(
                    row=row, column=column, padx=6, pady=2
                )
            row += 1

        self.table.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._bind_scroll_wheel(self.table)

    def _apply_toggle(self, tech_index: int, slot: int, researched: bool) -> None:
        if self._tech_save is None:
            return
        tech = self._tech_save.technologies[tech_index]
        set_researched(tech, slot, researched)
        self._mark_dirty()

    def _set_tech_row(self, tech_index: int, researched: bool) -> None:
        if self._tech_save is None:
            return
        tech = self._tech_save.technologies[tech_index]
        changed = False
        for player in self._tech_save.players:
            slot = player.slot
            key = (tech_index, slot)
            var = self._checkboxes.get(key)
            if var is None:
                continue
            if is_researched(tech, slot) == researched and var.get() == researched:
                continue
            set_researched(tech, slot, researched)
            var.set(researched)
            changed = True
        if changed:
            self._mark_dirty()

    def _reset_tech_row(self, tech_index: int) -> None:
        if self._tech_save is None:
            return
        tech = self._tech_save.technologies[tech_index]
        changed = False
        for player in self._tech_save.players:
            slot = player.slot
            key = (tech_index, slot)
            researched = self._initial_researched.get(key, False)
            var = self._checkboxes.get(key)
            if var is None:
                continue
            if is_researched(tech, slot) == researched and var.get() == researched:
                continue
            set_researched(tech, slot, researched)
            var.set(researched)
            changed = True
        if changed:
            self._mark_dirty()

    def _set_player_column(self, slot: int, researched: bool) -> None:
        if self._tech_save is None:
            return
        changed = False
        for tech in editable_technologies(self._tech_save.technologies):
            key = (tech.index, slot)
            var = self._checkboxes.get(key)
            if var is None:
                continue
            if is_researched(tech, slot) == researched and var.get() == researched:
                continue
            set_researched(tech, slot, researched)
            var.set(researched)
            changed = True
        if changed:
            self._mark_dirty()

    def _reset_player_column(self, slot: int) -> None:
        if self._tech_save is None:
            return
        changed = False
        for tech in editable_technologies(self._tech_save.technologies):
            key = (tech.index, slot)
            researched = self._initial_researched.get(key, False)
            var = self._checkboxes.get(key)
            if var is None:
                continue
            if is_researched(tech, slot) == researched and var.get() == researched:
                continue
            set_researched(tech, slot, researched)
            var.set(researched)
            changed = True
        if changed:
            self._mark_dirty()
