"""Click-through splash used by Deadlock Game Tools GUIs."""
from __future__ import annotations

import ctypes
import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk

PROJECT_NAME = "Deadlock Game Tools"
AUTHOR = "Josh Burns"
AUTHOR_EMAIL = "deadlock-game-tools@joshburns.me"
GITHUB_URL = "https://github.com/joshburns-git/deadlock-game-tools"
SOURCEFORGE_URL = "https://sourceforge.net/projects/deadlock-game-tools"


def os_display_scale() -> float:
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


def show_splash(
    app: tk.Tk,
    image_path: Path,
    *,
    geometry: str,
    minsize: tuple[int, int],
    on_ready,
) -> bool:
    """Show a centered splash. Returns True if on_ready will run after a click."""
    if not image_path.is_file():
        return False
    try:
        from PIL import Image, ImageTk
    except ImportError:
        return False

    src = Image.open(image_path)
    state = {"src": src, "photo": None, "drawn": None, "frame": None, "ready": False}

    def finish() -> None:
        if state["ready"]:
            return
        state["ready"] = True
        app.unbind("<Return>")
        app.unbind("<space>")
        frame = state["frame"]
        if frame is not None:
            frame.destroy()
        state["frame"] = None
        state["src"] = None
        state["photo"] = None
        try:
            app.state("normal")
        except tk.TclError:
            pass
        app.configure(bg="")
        on_ready()

    def draw(_event=None) -> None:
        image = state["src"]
        if image is None:
            return
        canvas = state["canvas"]
        cw = max(canvas.winfo_width(), 1)
        ch = max(canvas.winfo_height(), 1)
        iw, ih = image.size
        scale = os_display_scale()
        fit = min((cw * scale) / iw, (ch * scale) / ih, 1.0)
        size = (
            max(1, int(round(iw * fit / scale))),
            max(1, int(round(ih * fit / scale))),
        )
        drawn = (cw, ch, size)
        if state["drawn"] == drawn:
            return
        state["drawn"] = drawn
        shown = image if size == (iw, ih) else image.resize(size, Image.Resampling.LANCZOS)
        state["photo"] = ImageTk.PhotoImage(shown)
        canvas.delete("all")
        canvas.create_image(cw // 2, ch // 2, image=state["photo"], anchor="center")

    def dismiss(_event=None) -> None:
        finish()

    app.configure(bg="black")
    app.minsize(400, 300)
    try:
        app.state("zoomed")
    except tk.TclError:
        sw = max(app.winfo_screenwidth(), 1)
        sh = max(app.winfo_screenheight(), 1)
        app.geometry(f"{sw}x{sh}+0+0")

    frame = tk.Frame(app, bg="black")
    frame.place(relx=0, rely=0, relwidth=1, relheight=1)
    canvas = tk.Canvas(frame, bg="black", highlightthickness=0, bd=0, cursor="hand2")
    canvas.pack(fill=tk.BOTH, expand=True)
    state["frame"] = frame
    state["canvas"] = canvas
    canvas.bind("<Configure>", draw)
    for widget in (frame, canvas):
        widget.bind("<Button-1>", dismiss)
    app.bind("<Return>", dismiss)
    app.bind("<space>", dismiss)
    return True


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
