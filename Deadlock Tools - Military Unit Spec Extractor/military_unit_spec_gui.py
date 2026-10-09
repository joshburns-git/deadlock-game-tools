#!/usr/bin/env python3
"""
Deadlock Military Unit Spec Extractor — GUI

Copyright (c) 2026 Josh Burns <deadlock-game-tools@joshburns.me>
https://sourceforge.net/projects/deadlock-game-tools
"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from extract_military_unit_specs import (
    DEFAULT_OUT,
    ExportOptions,
    default_output_dir,
    export_specs,
    resolve_exe_path,
)
from tool_splash import add_help_menu, place_main_window, show_splash


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    import subprocess

    subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", str(path)])


class MilitaryUnitSpecApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Deadlock Military Unit Spec Extractor")
        self.geometry("760x640")
        self.minsize(640, 520)

        self.deadlock_var = tk.StringVar()
        self.out_dir_var = tk.StringVar(value=str(default_output_dir()))
        self.include_forts = tk.BooleanVar(value=False)
        self.write_xlsx = tk.BooleanVar(value=False)
        self.open_when_done = tk.BooleanVar(value=True)
        self._icon_photo: tk.PhotoImage | None = None
        self._busy = False

        self._set_window_icon()
        if not show_splash(
            self,
            self._resource_path("assets", "deadlock-game-tools-image.jpg"),
            geometry="760x640",
            minsize=(640, 520),
            on_ready=self._reveal_main,
        ):
            self._reveal_main()

    def _resource_path(self, *parts: str) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS).joinpath(*parts)
        return Path(__file__).resolve().parent.joinpath(*parts)

    def _set_window_icon(self) -> None:
        png_path = self._resource_path("assets", "MilitaryUnitSpecExtractor.png")
        ico_path = self._resource_path("assets", "MilitaryUnitSpecExtractor.ico")

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
        self.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        if not hwnd:
            return
        icon_path_str = str(icon_path.resolve())
        user32 = ctypes.windll.user32
        title_size = max(user32.GetSystemMetrics(49), 32)
        taskbar_size = max(user32.GetSystemMetrics(11), 64)
        for size, role in ((title_size, 0), (taskbar_size, 1)):
            handle = user32.LoadImageW(None, icon_path_str, 1, size, size, 0x10)
            if handle:
                user32.SendMessageW(hwnd, 0x80, role, handle)

    def _reveal_main(self) -> None:
        place_main_window(self, "760x640", (640, 520))
        self._build_menu()
        self._build_body()

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="Exit", command=self.destroy)
        menu.add_cascade(label="File", menu=file_menu)
        add_help_menu(
            menu,
            self,
            tool_name="Deadlock Military Unit Spec Extractor",
            image_path=self._resource_path("assets", "deadlock-game-tools-image.jpg"),
        )
        self.config(menu=menu)

    def _build_body(self) -> None:
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        intro = (
            "Reads military unit statistics compiled into deadlock.exe (v1.31) and "
            "writes a CSV spreadsheet. Base stats are shared by all races; per-race "
            "trait and combat-note columns are included on each unit row."
        )
        ttk.Label(outer, text=intro, wraplength=700, justify=tk.LEFT).pack(anchor="w", pady=(0, 12))

        paths = ttk.LabelFrame(outer, text="Paths", padding=8)
        paths.pack(fill=tk.X)
        self._path_row(paths, 0, "Deadlock folder", self.deadlock_var, self._browse_deadlock)
        self._path_row(paths, 1, "Output folder", self.out_dir_var, self._browse_output)

        opts = ttk.LabelFrame(outer, text="Output", padding=8)
        opts.pack(fill=tk.X, pady=(10, 0))
        ttk.Checkbutton(
            opts,
            text="Include fortifications (Laser / Energy / Anti-Matter Defense)",
            variable=self.include_forts,
        ).pack(anchor="w")
        ttk.Checkbutton(
            opts,
            text="Also write Excel workbook (deadlock_military_unit_specs.xlsx)",
            variable=self.write_xlsx,
        ).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(
            opts,
            text="Open output folder when finished",
            variable=self.open_when_done,
        ).pack(anchor="w", pady=(8, 0))

        buttons = ttk.Frame(outer)
        buttons.pack(fill=tk.X, pady=(10, 0))
        self.export_btn = ttk.Button(buttons, text="Export spreadsheets", command=self._start_export)
        self.export_btn.pack(side=tk.LEFT)
        ttk.Button(buttons, text="Open output folder", command=self._open_output).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        log_frame = ttk.LabelFrame(outer, text="Log", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.log = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.status = ttk.Label(outer, text="Ready")
        self.status.pack(fill=tk.X, pady=(8, 0))

    def _path_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        browse,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=2)
        ttk.Button(parent, text="Browse…", command=browse).grid(row=row, column=2, pady=2)
        parent.columnconfigure(1, weight=1)

    def _browse_deadlock(self) -> None:
        path = filedialog.askdirectory(title="Select Deadlock install folder")
        if path:
            self.deadlock_var.set(path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.out_dir_var.set(path)

    def _open_output(self) -> None:
        raw = self.out_dir_var.get().strip()
        if not raw:
            messagebox.showinfo("Output folder", "Choose an output folder first.")
            return
        open_folder(Path(raw))

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start_export(self) -> None:
        if self._busy:
            return
        deadlock_raw = self.deadlock_var.get().strip()
        out_raw = self.out_dir_var.get().strip() or str(default_output_dir())
        out_dir = Path(out_raw)
        if deadlock_raw:
            exe = resolve_exe_path(deadlock_path=Path(deadlock_raw))
        else:
            exe = resolve_exe_path()

        if not exe.is_file():
            messagebox.showerror(
                "Missing file",
                f"Could not find deadlock.exe at:\n{exe}\n\nSelect your Deadlock install folder.",
            )
            return

        xlsx_path = out_dir / "deadlock_military_unit_specs.xlsx" if self.write_xlsx.get() else None
        options = ExportOptions(
            exe=exe,
            out_csv=out_dir / DEFAULT_OUT,
            xlsx_path=xlsx_path,
            include_fortifications=self.include_forts.get(),
        )

        self._busy = True
        self.export_btn.configure(state="disabled")
        self.status.configure(text="Exporting…")
        self._append_log(f"Reading {exe}")

        def work() -> None:
            try:
                result = export_specs(options)
            except Exception as exc:  # noqa: BLE001 — show errors in the GUI
                self.after(0, lambda: self._export_failed(str(exc)))
                return
            self.after(0, lambda: self._export_done(result, out_dir))

        threading.Thread(target=work, daemon=True).start()

    def _export_failed(self, message: str) -> None:
        self._busy = False
        self.export_btn.configure(state="normal")
        self.status.configure(text="Export failed")
        self._append_log(f"Error: {message}")
        messagebox.showerror("Export failed", message)

    def _export_done(self, result, out_dir: Path) -> None:
        self._busy = False
        self.export_btn.configure(state="normal")
        self.status.configure(text="Done")
        self._append_log(f"Wrote {result.unit_count} units to {result.out_csv.name}")
        if result.xlsx_path is not None:
            self._append_log(f"Wrote {result.xlsx_path.name}")
        if self.open_when_done.get():
            open_folder(out_dir)
        messagebox.showinfo(
            "Export complete",
            f"Exported {result.unit_count} unit types to:\n{out_dir}",
        )


def main() -> None:
    app = MilitaryUnitSpecApp()
    app.mainloop()


if __name__ == "__main__":
    main()
