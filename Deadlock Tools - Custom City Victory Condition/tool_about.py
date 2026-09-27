"""About dialog shared by Deadlock Game Tools GUIs."""
from __future__ import annotations

import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk

PROJECT_NAME = "Deadlock Game Tools"
AUTHOR = "Josh Burns"
AUTHOR_EMAIL = "deadlock-game-tools@joshburns.me"
GITHUB_URL = "https://github.com/joshburns-git/deadlock-game-tools"
SOURCEFORGE_URL = "https://sourceforge.net/projects/deadlock-game-tools"


def add_help_menu(
    menu: tk.Menu,
    parent: tk.Misc,
    *,
    tool_name: str | None = None,
    image_path: Path | None = None,
) -> None:
    help_menu = tk.Menu(menu, tearoff=0)
    help_menu.add_command(
        label="About Deadlock Game Tools",
        command=lambda: show_about_dialog(parent, tool_name=tool_name, image_path=image_path),
    )
    menu.add_cascade(label="Help", menu=help_menu)


def _load_about_banner(image_path: Path | None) -> tk.PhotoImage | None:
    if image_path is None or not image_path.is_file():
        return None
    try:
        from PIL import Image, ImageTk
    except ImportError:
        return None

    max_width = 420
    try:
        image = Image.open(image_path)
        if image.width > max_width:
            ratio = max_width / image.width
            size = (max_width, max(1, int(round(image.height * ratio))))
            image = image.resize(size, Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(image)
    except OSError:
        return None


def show_about_dialog(
    parent: tk.Misc,
    *,
    tool_name: str | None = None,
    image_path: Path | None = None,
) -> None:
    win = tk.Toplevel(parent)
    win.title("About Deadlock Game Tools")
    win.transient(parent)
    win.resizable(False, False)
    win.grab_set()

    frame = ttk.Frame(win, padding=16)
    frame.pack(fill=tk.BOTH, expand=True)

    banner = _load_about_banner(image_path)
    if banner is not None:
        win._about_banner = banner
        tk.Label(frame, image=banner, bd=0).pack(anchor="center", pady=(0, 12))

    ttk.Label(frame, text=PROJECT_NAME, font=("", 14, "bold")).pack(anchor="w")
    if tool_name:
        ttk.Label(frame, text=tool_name).pack(anchor="w", pady=(4, 0))

    description = (
        "Tools for Deadlock: Planetary Conquest (Accolade, 1996): "
        "asset extractors, save-game editors, and more."
    )
    ttk.Label(frame, text=description, wraplength=420, justify=tk.LEFT).pack(
        anchor="w", pady=(12, 8)
    )

    ttk.Label(frame, text=f"Initial author: {AUTHOR}").pack(anchor="w")
    ttk.Label(frame, text=AUTHOR_EMAIL).pack(anchor="w", pady=(0, 8))

    links = ttk.Frame(frame)
    links.pack(anchor="w", fill=tk.X)

    def add_link(row: ttk.Frame, label: str, url: str) -> None:
        link = tk.Label(
            row,
            text=label,
            fg="#0645ad",
            cursor="hand2",
            font=("", 9, "underline"),
        )
        link.pack(anchor="w")
        link.bind("<Button-1>", lambda _event, target=url: webbrowser.open(target))

    add_link(links, "GitHub: github.com/joshburns-git/deadlock-game-tools", GITHUB_URL)
    add_link(links, "SourceForge: sourceforge.net/projects/deadlock-game-tools", SOURCEFORGE_URL)

    ttk.Button(frame, text="Close", command=win.destroy).pack(anchor="e", pady=(16, 0))
    win.bind("<Escape>", lambda _event: win.destroy())

    win.update_idletasks()
    pw = max(parent.winfo_width(), 1)
    ph = max(parent.winfo_height(), 1)
    px = parent.winfo_rootx()
    py = parent.winfo_rooty()
    ww = win.winfo_width()
    wh = win.winfo_height()
    win.geometry(f"+{px + (pw - ww) // 2}+{py + (ph - wh) // 2}")
    win.focus_set()
