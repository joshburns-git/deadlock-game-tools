"""Convert SpriteExtractor.png into bundled .png and Windows .ico assets."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

TOOL_DIR = Path(__file__).resolve().parent
OUTPUT_ICON = TOOL_DIR / "assets" / "SpriteExtractor.ico"
OUTPUT_PNG = TOOL_DIR / "assets" / "SpriteExtractor.png"
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def source_path() -> Path:
    source = TOOL_DIR / "SpriteExtractor.png"
    if source.is_file():
        return source
    if OUTPUT_PNG.is_file():
        return OUTPUT_PNG
    raise FileNotFoundError("Source icon not found. Place SpriteExtractor.png in this folder.")


def square_canvas(image: Image.Image) -> Image.Image:
    width, height = image.size
    side = max(width, height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - width) // 2, (side - height) // 2), image)
    return canvas


def main() -> None:
    OUTPUT_ICON.parent.mkdir(exist_ok=True)
    source = source_path()
    master = square_canvas(Image.open(source).convert("RGBA")).resize(
        (256, 256), Image.Resampling.LANCZOS
    )

    master.save(OUTPUT_ICON, format="ICO", sizes=ICO_SIZES)
    master.save(OUTPUT_PNG, format="PNG")
    print(f"Wrote {OUTPUT_ICON} and {OUTPUT_PNG} from {source.name}")


if __name__ == "__main__":
    main()
