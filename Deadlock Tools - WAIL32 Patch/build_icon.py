"""Convert assets/logo.jpg into bundled Wail32Patch.png and Wail32Patch.ico."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

TOOL_DIR = Path(__file__).resolve().parent
SOURCE = TOOL_DIR / "assets" / "logo.jpg"
OUTPUT_ICON = TOOL_DIR / "assets" / "Wail32Patch.ico"
OUTPUT_PNG = TOOL_DIR / "assets" / "Wail32Patch.png"
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def square_canvas(image: Image.Image) -> Image.Image:
    width, height = image.size
    side = max(width, height)
    canvas = Image.new("RGBA", (side, side), (255, 255, 255, 255))
    canvas.paste(image, ((side - width) // 2, (side - height) // 2), image)
    return canvas


def main() -> None:
    if not SOURCE.is_file():
        raise FileNotFoundError(SOURCE)
    master = square_canvas(Image.open(SOURCE).convert("RGBA")).resize(
        (256, 256), Image.Resampling.LANCZOS
    )
    master.save(OUTPUT_ICON, format="ICO", sizes=ICO_SIZES)
    master.save(OUTPUT_PNG, format="PNG")
    print(f"Wrote {OUTPUT_ICON.name} and {OUTPUT_PNG.name} from {SOURCE.name}")


if __name__ == "__main__":
    main()
