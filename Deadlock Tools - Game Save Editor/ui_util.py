"""Small Tk helpers shared by the Game Save Editor UI."""
from __future__ import annotations

import tkinter as tk


def tk_configure_resized(event: tk.Event, last_size: list[tuple[int, int] | None]) -> bool:
    """True when Configure reflects a size change (ignore position-only moves on Windows)."""
    size = (event.width, event.height)
    if size == last_size[0]:
        return False
    last_size[0] = size
    return True
