#!/usr/bin/env python3
"""
Deadlock Custom City Victory Condition — GUI

Copyright (c) 2026 Josh Burns <deadlock-game-tools@joshburns.me>
https://sourceforge.net/projects/deadlock-game-tools
"""
from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from patch_cities_to_win import (
    MAX_CITIES,
    apply_patch,
    patch_save,
    resolve_exe,
    resolve_save,
    revert_patch,
    show_status,
)
from tool_about import add_help_menu


def center_geometry(app: tk.Tk, geometry: str) -> str:
    """Return a WxH+X+Y geometry string centered on the primary screen."""
    size = geometry.split("+", 1)[0]
    if "x" not in size:
        return geometry
    width_str, height_str = size.split("x", 1)
    width, height = int(width_str), int(height_str)
    sw = max(app.winfo_screenwidth(), 1)
    sh = max(app.winfo_screenheight(), 1)
    x = max(0, (sw - width) // 2)
    y = max(0, (sh - height) // 2)
    return f"{width}x{height}+{x}+{y}"


def place_main_window(app: tk.Tk, geometry: str, minsize: tuple[int, int]) -> None:
    app.geometry(center_geometry(app, geometry))
    app.minsize(*minsize)


class CityVictoryApp(tk.Tk):
    def __init__(self, initial_exe: Path | None = None) -> None:
        super().__init__()
        self.title("Deadlock Custom City Victory Condition")
        self.geometry("680x520")
        self.minsize(560, 420)

        self.exe_var = tk.StringVar()
        self.save_var = tk.StringVar()
        self.value_var = tk.StringVar(value=str(MAX_CITIES))
        self.force_var = tk.BooleanVar(value=False)
        self.patch_save_var = tk.BooleanVar(value=False)
        self._icon_photo: tk.PhotoImage | None = None
        self._splash_src = None
        self._splash_photo = None
        self._splash_drawn = None
        self._pending_exe = initial_exe

        self._set_window_icon()
        if not self._show_splash():
            self._reveal_main()

    def _resource_path(self, *parts: str) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS).joinpath(*parts)
        return Path(__file__).resolve().parent.joinpath(*parts)

    def _set_window_icon(self) -> None:
        png_path = self._resource_path("assets", "CityVictory.png")
        ico_path = self._resource_path("assets", "CityVictory.ico")

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

    def _splash_image_path(self) -> Path:
        return self._resource_path("assets", "deadlock-game-tools-image.jpg")

    def _os_display_scale(self) -> float:
        """Windows stretch factor for a DPI-unaware Tk window."""
        if sys.platform != "win32":
            return 1.0
        try:
            hdc = ctypes.windll.user32.GetDC(0)
            try:
                logical = ctypes.windll.gdi32.GetDeviceCaps(hdc, 8)
                physical = ctypes.windll.gdi32.GetDeviceCaps(hdc, 118)
            finally:
                ctypes.windll.user32.ReleaseDC(0, hdc)
            if logical > 0 and physical > logical:
                return physical / logical
        except OSError:
            pass
        try:
            factor = int(ctypes.windll.shcore.GetScaleFactorForDevice(0))
            if factor >= 100:
                return factor / 100.0
        except OSError:
            pass
        return 1.0

    def _show_splash(self) -> bool:
        path = self._splash_image_path()
        if not path.is_file():
            return False
        try:
            from PIL import Image
        except ImportError:
            return False

        self._splash_src = Image.open(path)
        self.configure(bg="black")
        self.minsize(400, 300)
        try:
            self.state("zoomed")
        except tk.TclError:
            sw = max(self.winfo_screenwidth(), 1)
            sh = max(self.winfo_screenheight(), 1)
            self.geometry(f"{sw}x{sh}+0+0")

        self._splash = tk.Frame(self, bg="black")
        self._splash.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._splash_canvas = tk.Canvas(
            self._splash, bg="black", highlightthickness=0, bd=0, cursor="hand2"
        )
        self._splash_canvas.pack(fill=tk.BOTH, expand=True)
        self._splash_canvas.bind("<Configure>", self._draw_splash)
        for widget in (self._splash, self._splash_canvas):
            widget.bind("<Button-1>", self._dismiss_splash)
        self.bind("<Return>", self._dismiss_splash)
        self.bind("<space>", self._dismiss_splash)
        return True

    def _draw_splash(self, _event=None) -> None:
        if self._splash_src is None:
            return
        from PIL import Image, ImageTk

        canvas = self._splash_canvas
        cw = max(canvas.winfo_width(), 1)
        ch = max(canvas.winfo_height(), 1)
        iw, ih = self._splash_src.size
        os_scale = self._os_display_scale()
        phys_w = cw * os_scale
        phys_h = ch * os_scale
        fit = min(phys_w / iw, phys_h / ih, 1.0)
        size = (
            max(1, int(round(iw * fit / os_scale))),
            max(1, int(round(ih * fit / os_scale))),
        )
        drawn = (cw, ch, size)
        if self._splash_drawn == drawn:
            return
        self._splash_drawn = drawn
        shown = self._splash_src if size == (iw, ih) else self._splash_src.resize(
            size, Image.Resampling.LANCZOS
        )
        self._splash_photo = ImageTk.PhotoImage(shown)
        canvas.delete("all")
        canvas.create_image(cw // 2, ch // 2, image=self._splash_photo, anchor="center")

    def _dismiss_splash(self, _event=None) -> None:
        if not getattr(self, "_splash", None):
            return
        self.unbind("<Return>")
        self.unbind("<space>")
        self._splash.destroy()
        self._splash = None
        self._splash_src = None
        self._splash_photo = None
        self._splash_drawn = None
        self._reveal_main()

    def _reveal_main(self) -> None:
        try:
            self.state("normal")
        except tk.TclError:
            pass
        self.configure(bg="")
        place_main_window(self, "680x520", (560, 420))
        self._build_menu()
        self._build_body()
        if self._pending_exe is not None:
            self.exe_var.set(str(self._pending_exe))
            self._pending_exe = None

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        add_help_menu(
            menu,
            self,
            tool_name="Deadlock Custom City Victory Condition",
            image_path=self._resource_path("assets", "deadlock-game-tools-image.jpg"),
        )
        self.config(menu=menu)

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

        files = ttk.LabelFrame(root, text="Files", padding=8)
        files.pack(fill=tk.X)
        self._path_row(files, 0, "deadlock.exe", self.exe_var, self._browse_exe)
        ttk.Checkbutton(
            files,
            text="Also patch a save file",
            variable=self.patch_save_var,
            command=self._toggle_save,
        ).grid(row=1, column=1, sticky="w", pady=(6, 0))
        self.save_label = ttk.Label(files, text=".SAV file")
        self.save_entry = ttk.Entry(files, textvariable=self.save_var)
        self.save_browse = ttk.Button(files, text="Browse…", command=self._browse_save)
        files.columnconfigure(1, weight=1)

        opts = ttk.LabelFrame(root, text="Victory condition", padding=8)
        opts.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(opts, text="Cities required to win").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(opts, from_=1, to=99, textvariable=self.value_var, width=8).grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )
        ttk.Label(opts, text="Default original value is 10; typical patch is 40").grid(
            row=0, column=2, sticky="w", padx=(8, 0)
        )
        ttk.Checkbutton(
            opts,
            text="Force patch if version checks fail",
            variable=self.force_var,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(root)
        buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons, text="Show status", command=self._status).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Patch", command=self._patch).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Revert", command=self._revert).pack(side=tk.LEFT, padx=(8, 0))

        log_frame = ttk.LabelFrame(root, text="Log", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.log = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.status = ttk.Label(root, text="Ready — tested on Deadlock v1.31")
        self.status.pack(fill=tk.X, pady=(8, 0))

    def _path_row(self, parent: ttk.Widget, row: int, label: str, variable: tk.StringVar, browse) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=2)
        ttk.Button(parent, text="Browse…", command=browse).grid(row=row, column=2, pady=2)

    def _toggle_save(self) -> None:
        if self.patch_save_var.get():
            self.save_label.grid(row=2, column=0, sticky="w", pady=2)
            self.save_entry.grid(row=2, column=1, sticky="ew", padx=8, pady=2)
            self.save_browse.grid(row=2, column=2, pady=2)
        else:
            self.save_label.grid_forget()
            self.save_entry.grid_forget()
            self.save_browse.grid_forget()

    def _browse_exe(self) -> None:
        path = filedialog.askopenfilename(
            title="Select deadlock.exe",
            filetypes=[("Deadlock executable", "deadlock.exe"), ("Executables", "*.exe"), ("All files", "*.*")],
        )
        if path:
            self.exe_var.set(path)

    def _browse_save(self) -> None:
        path = filedialog.askopenfilename(
            title="Select a Deadlock save",
            filetypes=[("Deadlock saves", "*.sav;*.SAV"), ("All files", "*.*")],
        )
        if path:
            self.save_var.set(path)

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _cities(self) -> int:
        try:
            value = int(self.value_var.get().strip())
        except ValueError as exc:
            raise ValueError("Cities required to win must be a number") from exc
        if not 1 <= value <= 99:
            raise ValueError("Cities required to win must be between 1 and 99")
        return value

    def _exe_path(self) -> Path:
        raw = self.exe_var.get().strip()
        if not raw:
            raise ValueError("Choose deadlock.exe first")
        return resolve_exe(Path(raw))

    def _run(self, action: str, work) -> None:
        try:
            work()
        except (FileNotFoundError, ValueError) as exc:
            self._append_log(f"Error: {exc}")
            self.status.configure(text="Failed")
            messagebox.showerror(action, str(exc))
            return
        self.status.configure(text=action)

    def _status(self) -> None:
        def work() -> None:
            exe = self._exe_path()
            self._append_log(f"Status for {exe}")
            show_status(exe, log=self._append_log)

        self._run("Status updated", work)

    def _patch(self) -> None:
        try:
            exe = self._exe_path()
            cities = self._cities()
        except (FileNotFoundError, ValueError) as exc:
            messagebox.showerror("Patch", str(exc))
            return
        if not messagebox.askyesno(
            "Patch deadlock.exe",
            f"Patch {exe.name} so the highest city victory option is {cities}?\n\n"
            "A .bak backup is created next to the executable the first time.",
        ):
            return

        def work() -> None:
            self._append_log(f"Patching {exe} to {cities} cities")
            apply_patch(exe, cities, self.force_var.get(), log=self._append_log)
            if self.patch_save_var.get():
                save = resolve_save(Path(self.save_var.get().strip()))
                patch_save(save, cities, log=self._append_log)

        self._run(f"Patched to {cities} cities", work)

    def _revert(self) -> None:
        try:
            exe = self._exe_path()
        except (FileNotFoundError, ValueError) as exc:
            messagebox.showerror("Revert", str(exc))
            return
        if not messagebox.askyesno(
            "Revert deadlock.exe",
            f"Restore {exe.name} from its .bak backup (or the original 10-city default)?",
        ):
            return

        def work() -> None:
            self._append_log(f"Reverting {exe}")
            revert_patch(exe, log=self._append_log)

        self._run("Reverted", work)


def main() -> None:
    initial = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    app = CityVictoryApp(initial)
    app.mainloop()


if __name__ == "__main__":
    main()
