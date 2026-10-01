#!/usr/bin/env python3
"""
Deadlock WAIL32 Patch — GUI

Copyright (c) 2026 Josh Burns <deadlock-game-tools@joshburns.me>
https://sourceforge.net/projects/deadlock-game-tools
"""
from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from patch_wail32 import Wail32State, apply_patch, restore_original, resolve_exe, show_status
from tool_splash import add_help_menu, place_main_window, show_splash


class Wail32PatchApp(tk.Tk):
    def __init__(self, initial_exe: Path | None = None) -> None:
        super().__init__()
        self.title("Deadlock WAIL32 Patch")
        self.geometry("720x580")
        self.minsize(620, 520)

        self.exe_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Choose your Deadlock install folder or deadlock.exe.")
        self._icon_photo: tk.PhotoImage | None = None
        self._pending_exe = initial_exe

        self._set_window_icon()
        if not show_splash(
            self,
            self._resource_path("assets", "deadlock-game-tools-image.jpg"),
            geometry="720x580",
            minsize=(620, 520),
            on_ready=self._reveal_main,
        ):
            self._reveal_main()

    def _resource_path(self, *parts: str) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS).joinpath(*parts)
        return Path(__file__).resolve().parent.joinpath(*parts)

    def _set_window_icon(self) -> None:
        png_path = self._resource_path("assets", "Wail32Patch.png")
        ico_path = self._resource_path("assets", "Wail32Patch.ico")

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

    def _apply_windows_icon(self, ico_path: Path) -> None:
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                hwnd = self.winfo_id()
            ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, 0)  # WM_SETICON small
            ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, 0)  # WM_SETICON big
            self.iconbitmap(str(ico_path))
        except OSError:
            pass

    def _reveal_main(self) -> None:
        place_main_window(self, "720x580", (620, 520))
        self._build_menu()
        self._build_body()
        self._build_actions()
        if self._pending_exe is not None:
            self.exe_var.set(str(self._pending_exe))
            self._refresh_status()
            self._pending_exe = None

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="Exit", command=self.destroy)
        menu.add_cascade(label="File", menu=file_menu)
        add_help_menu(
            menu,
            self,
            tool_name="WAIL32 Patch",
            image_path=self._resource_path("assets", "deadlock-game-tools-image.jpg"),
        )
        self.config(menu=menu)

    def _build_body(self) -> None:
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)

        intro = (
            "On Windows 10/11, the retail WAIL32.DLL that ships with Deadlock v1.31 can "
            "freeze during audio startup (DEBUG.TXT stops at LoadWail).\n\n"
            "Unlike renaming, deleting, or swapping in a replacement DLL, this tool "
            "patches your original Miles file in place (a 5-byte fix). You keep the real "
            "game audio library, so background music and colony sound effects should still "
            "work after the patch. Your unmodified copy is backed up first."
        )
        ttk.Label(outer, text=intro, wraplength=660, justify=tk.LEFT).pack(
            anchor="w", pady=(0, 16)
        )

        path_row = ttk.Frame(outer)
        path_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(path_row, text="Deadlock folder:").pack(side=tk.LEFT)
        ttk.Entry(path_row, textvariable=self.exe_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8)
        )
        ttk.Button(path_row, text="Browse…", command=self._browse_exe).pack(side=tk.LEFT)

        status_frame = ttk.LabelFrame(outer, text="Status", padding=12)
        status_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        ttk.Label(
            status_frame,
            textvariable=self.status_var,
            wraplength=640,
            justify=tk.LEFT,
        ).pack(anchor="w")

        details = (
            "Tested with Deadlock v1.31 on Windows 10.\n\n"
            "The patch changes one instruction inside the original Miles DLL "
            "(CALLBACK_FUNCTION → CALLBACK_NULL at waveOutOpen). "
            "WAIL32.DLL stays in your game folder — same filename, same Miles engine, "
            "full music and SFX — not a stripped-down substitute."
        )
        ttk.Label(status_frame, text=details, wraplength=640, justify=tk.LEFT).pack(
            anchor="w", pady=(12, 0)
        )

    def _build_actions(self) -> None:
        bar = ttk.Frame(self, padding=(16, 0, 16, 16))
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="Refresh status", command=self._refresh_status).pack(
            side=tk.LEFT
        )
        ttk.Button(bar, text="Apply patch", command=self._apply_patch).pack(
            side=tk.RIGHT, padx=(8, 0)
        )
        ttk.Button(bar, text="Restore original", command=self._restore_original).pack(
            side=tk.RIGHT
        )

    def _browse_exe(self) -> None:
        initial = self.exe_var.get().strip()
        initial_dir = initial if initial else None
        path = filedialog.askopenfilename(
            title="Select deadlock.exe",
            filetypes=[("Deadlock executable", "deadlock.exe"), ("All files", "*.*")],
            initialdir=str(Path(initial_dir).parent) if initial_dir else None,
        )
        if path:
            self.exe_var.set(path)
            self._refresh_status()

    def _current_exe(self) -> Path | None:
        raw = self.exe_var.get().strip()
        if not raw:
            return None
        return Path(raw)

    def _refresh_status(self) -> None:
        exe = self._current_exe()
        if exe is None:
            self.status_var.set("Choose your Deadlock install folder or deadlock.exe.")
            return
        try:
            status = show_status(exe)
        except (FileNotFoundError, ValueError) as exc:
            self.status_var.set(str(exc))
            return
        self.status_var.set(status.message)

    def _apply_patch(self) -> None:
        exe = self._current_exe()
        if exe is None:
            messagebox.showwarning("WAIL32 Patch", "Select deadlock.exe first.")
            return
        try:
            result = apply_patch(exe)
        except (FileNotFoundError, ValueError) as exc:
            messagebox.showerror("WAIL32 Patch", str(exc))
            return
        self.status_var.set(result.message)
        if result.state is Wail32State.PATCHED:
            messagebox.showinfo("WAIL32 Patch", result.message)

    def _restore_original(self) -> None:
        exe = self._current_exe()
        if exe is None:
            messagebox.showwarning("WAIL32 Patch", "Select deadlock.exe first.")
            return
        if not messagebox.askyesno(
            "Restore original",
            "Restore WAIL32.DLL from the backup copy?",
        ):
            return
        try:
            result = restore_original(exe)
        except (FileNotFoundError, ValueError) as exc:
            messagebox.showerror("WAIL32 Patch", str(exc))
            return
        self.status_var.set(result.message)
        messagebox.showinfo("WAIL32 Patch", result.message)


def main() -> None:
    initial: Path | None = None
    if len(sys.argv) > 1:
        try:
            initial = resolve_exe(Path(sys.argv[1]))
        except (FileNotFoundError, ValueError):
            initial = Path(sys.argv[1])
    app = Wail32PatchApp(initial_exe=initial)
    app.mainloop()


if __name__ == "__main__":
    main()
