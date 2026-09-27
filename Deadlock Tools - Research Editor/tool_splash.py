"""Click-through splash used by Deadlock Game Tools GUIs."""
from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from pathlib import Path


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
        app.geometry(geometry)
        app.minsize(*minsize)
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
