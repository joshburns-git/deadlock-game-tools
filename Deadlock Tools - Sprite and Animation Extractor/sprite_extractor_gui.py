#!/usr/bin/env python3
"""
Deadlock Sprite and Animation Extractor — GUI

Copyright (c) 2026 Josh Burns <deadlock-game-tools@joshburns.me>
https://sourceforge.net/projects/deadlock-game-tools

Licensed under the MIT License (see LICENSE.txt file).
"""
from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from extract_deadlock_sprites import (
    default_output_dir,
    extract,
    parse_id_list,
    resolve_game_paths,
)
from tool_splash import show_splash


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    import subprocess

    subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", str(path)])


class SpriteExtractorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Deadlock Sprite and Animation Extractor")
        self.geometry("760x640")
        self.minsize(640, 520)

        self.deadlock_var = tk.StringVar()
        self.out_var = tk.StringVar(value=str(default_output_dir()))
        self.exe_var = tk.StringVar()
        self.dat_var = tk.StringVar()
        self.ids_var = tk.StringVar()
        self.static_ids_var = tk.StringVar()
        self.delay_var = tk.StringVar()
        self.limit_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="all")
        self.open_when_done = tk.BooleanVar(value=True)
        self.write_frames_txt = tk.BooleanVar(value=False)
        self.show_advanced = tk.BooleanVar(value=False)
        self._icon_photo: tk.PhotoImage | None = None
        self._busy = False
        self._log_queue: queue.Queue[str] = queue.Queue()

        self._set_window_icon()
        if not show_splash(
            self,
            self._resource_path("assets", "deadlock-game-tools-image.jpg"),
            geometry="760x640",
            minsize=(640, 520),
            on_ready=self._reveal_main,
        ):
            self._reveal_main()

    def _reveal_main(self) -> None:
        self._build_body()
        self.after(100, self._drain_log)

    def _resource_path(self, *parts: str) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS).joinpath(*parts)
        return Path(__file__).resolve().parent.joinpath(*parts)

    def _set_window_icon(self) -> None:
        png_path = self._resource_path("assets", "SpriteExtractor.png")
        ico_path = self._resource_path("assets", "SpriteExtractor.ico")

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

    def _build_body(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)

        paths = ttk.LabelFrame(root, text="Folders", padding=8)
        paths.pack(fill=tk.X)
        self._path_row(paths, 0, "Deadlock folder", self.deadlock_var, self._browse_deadlock)
        self._path_row(paths, 1, "Output folder", self.out_var, self._browse_output)

        ttk.Checkbutton(
            paths,
            text="Open output folder when finished",
            variable=self.open_when_done,
        ).grid(row=2, column=1, sticky="w", pady=(6, 0))
        paths.columnconfigure(1, weight=1)

        mode = ttk.LabelFrame(root, text="What to extract", padding=8)
        mode.pack(fill=tk.X, pady=(10, 0))
        ttk.Radiobutton(mode, text="Animated and static GIFs", variable=self.mode_var, value="all").pack(anchor="w")
        ttk.Radiobutton(mode, text="Animations only", variable=self.mode_var, value="animations").pack(anchor="w")
        ttk.Radiobutton(mode, text="Static only", variable=self.mode_var, value="static").pack(anchor="w")

        opts = ttk.LabelFrame(root, text="Options", padding=8)
        opts.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(opts, text="Sprite IDs (optional)").grid(row=0, column=0, sticky="w")
        ttk.Entry(opts, textvariable=self.ids_var).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Label(opts, text="Example: 24, 83, 1").grid(row=0, column=2, sticky="w", padx=(8, 0))
        ttk.Label(opts, text="GIF delay (cs)").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(opts, textvariable=self.delay_var, width=10).grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
        ttk.Label(opts, text="Blank = use the game delay").grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(6, 0))
        ttk.Label(opts, text="Limit GIFs").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(opts, textvariable=self.limit_var, width=10).grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
        ttk.Label(opts, text="Blank = no limit").grid(row=2, column=2, sticky="w", padx=(8, 0), pady=(6, 0))
        ttk.Checkbutton(
            opts,
            text="Write sprite_XXXX_frames.txt metadata files",
            variable=self.write_frames_txt,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        opts.columnconfigure(1, weight=1)

        self.advanced_toggle = ttk.Checkbutton(
            root,
            text="Show advanced file paths",
            variable=self.show_advanced,
            command=self._toggle_advanced,
        )
        self.advanced_toggle.pack(anchor="w", pady=(10, 0))

        self.advanced = ttk.LabelFrame(root, text="Advanced", padding=8)
        self._path_row(self.advanced, 0, "deadlock.exe", self.exe_var, self._browse_exe)
        self._path_row(self.advanced, 1, "SPRITELG.DAT", self.dat_var, self._browse_dat)
        ttk.Label(self.advanced, text="Force static IDs").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(self.advanced, textvariable=self.static_ids_var).grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(6, 0)
        )
        self.advanced.columnconfigure(1, weight=1)

        buttons = ttk.Frame(root)
        buttons.pack(fill=tk.X, pady=(10, 0))
        self.extract_btn = ttk.Button(buttons, text="Extract", command=self._start_extract)
        self.extract_btn.pack(side=tk.LEFT)
        ttk.Button(buttons, text="Open output folder", command=self._open_output).pack(side=tk.LEFT, padx=(8, 0))

        log_frame = ttk.LabelFrame(root, text="Log", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.log = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.status = ttk.Label(root, text="Ready")
        self.status.pack(fill=tk.X, pady=(8, 0))

    def _path_row(
        self,
        parent: ttk.Widget,
        row: int,
        label: str,
        variable: tk.StringVar,
        browse,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=2)
        ttk.Button(parent, text="Browse…", command=browse).grid(row=row, column=2, pady=2)
        parent.columnconfigure(1, weight=1)

    def _toggle_advanced(self) -> None:
        if self.show_advanced.get():
            self.advanced.pack(fill=tk.X, pady=(6, 0), after=self.advanced_toggle)
        else:
            self.advanced.pack_forget()

    def _browse_deadlock(self) -> None:
        path = filedialog.askdirectory(title="Select Deadlock folder")
        if path:
            self.deadlock_var.set(path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.out_var.set(path)

    def _browse_exe(self) -> None:
        path = filedialog.askopenfilename(
            title="Select deadlock.exe",
            filetypes=[("Deadlock executable", "deadlock.exe"), ("Executables", "*.exe"), ("All files", "*.*")],
        )
        if path:
            self.exe_var.set(path)

    def _browse_dat(self) -> None:
        path = filedialog.askopenfilename(
            title="Select SPRITELG.DAT",
            filetypes=[("Deadlock sprite data", "SPRITELG.DAT"), ("DAT files", "*.DAT"), ("All files", "*.*")],
        )
        if path:
            self.dat_var.set(path)

    def _open_output(self) -> None:
        raw = self.out_var.get().strip()
        if not raw:
            messagebox.showinfo("Output folder", "Choose an output folder first.")
            return
        open_folder(Path(raw))

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain_log(self) -> None:
        while True:
            try:
                message = self._log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(message)
        self.after(100, self._drain_log)

    def _optional_int(self, raw: str, label: str) -> int | None:
        text = raw.strip()
        if not text:
            return None
        try:
            return int(text, 0)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number") from exc

    def _start_extract(self) -> None:
        if self._busy:
            return
        try:
            deadlock = Path(self.deadlock_var.get().strip()) if self.deadlock_var.get().strip() else None
            exe = Path(self.exe_var.get().strip()) if self.exe_var.get().strip() else None
            dat = Path(self.dat_var.get().strip()) if self.dat_var.get().strip() else None
            out_dir = Path(self.out_var.get().strip() or default_output_dir())
            exe_path, dat_path = resolve_game_paths(deadlock, exe, dat)
            ids = parse_id_list(self.ids_var.get()) or None
            static_ids = set(parse_id_list(self.static_ids_var.get())) or None
            delay = self._optional_int(self.delay_var.get(), "GIF delay")
            limit = self._optional_int(self.limit_var.get(), "Limit GIFs")
        except ValueError as exc:
            messagebox.showerror("Invalid options", str(exc))
            return

        if not exe_path.exists():
            messagebox.showerror("Missing file", f"Could not find deadlock.exe at:\n{exe_path}")
            return
        if not dat_path.exists():
            messagebox.showerror("Missing file", f"Could not find SPRITELG.DAT at:\n{dat_path}")
            return

        mode = self.mode_var.get()
        write_frames_txt = self.write_frames_txt.get()
        self._busy = True
        self.extract_btn.configure(state="disabled")
        self.status.configure(text="Extracting…")
        self._append_log(f"Extracting from {exe_path.parent}")
        self._append_log(f"Writing GIFs to {out_dir}")

        def work() -> None:
            try:
                count = extract(
                    exe_path,
                    dat_path,
                    out_dir,
                    limit=limit,
                    sprite_ids=ids,
                    animations_only=(mode == "animations"),
                    static_only=(mode == "static"),
                    gif_delay_cs=delay,
                    forced_static_ids=static_ids,
                    write_frames_txt=write_frames_txt,
                    progress=self._log_queue.put,
                )
                self._log_queue.put(f"Wrote {count} GIFs under {out_dir}")
                self.after(0, lambda: self._extract_done(out_dir, count, None))
            except Exception as exc:
                self._log_queue.put(f"Error: {exc}")
                self.after(0, lambda: self._extract_done(out_dir, 0, exc))

        threading.Thread(target=work, daemon=True).start()

    def _extract_done(self, out_dir: Path, count: int, error: Exception | None) -> None:
        self._busy = False
        self.extract_btn.configure(state="normal")
        if error is not None:
            self.status.configure(text="Extract failed")
            messagebox.showerror("Extract failed", str(error))
            return
        self.status.configure(text=f"Wrote {count} GIFs")
        if self.open_when_done.get():
            open_folder(out_dir)


def main() -> None:
    app = SpriteExtractorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
