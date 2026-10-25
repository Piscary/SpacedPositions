"""The app icons: packaging/icon.icns (macOS) and packaging/icon.ico (Windows), drawn from the app bar's knight on
the paper theme's main colour. Run once after changing the look: `python packaging/icons.py` (needs Pillow; macOS
for the .icns, via iconutil)."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
MAIN, DARK, LIGHT = (47, 91, 211), (31, 62, 150), (255, 255, 255)
FONTS = ["/System/Library/Fonts/Apple Symbols.ttf", "C:/Windows/Fonts/seguisym.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def draw(size=1024):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    pad, radius = size * 0.09, size * 0.2
    box = (pad, pad, size - pad, size - pad)
    d.rounded_rectangle(box, radius, fill=MAIN)
    # two darker squares of a board behind the knight
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius, fill=255)
    squares = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    half = size / 2
    ImageDraw.Draw(squares).rectangle((pad, pad, half, half), fill=DARK)
    ImageDraw.Draw(squares).rectangle((half, half, size - pad, size - pad), fill=DARK)
    image.paste(squares, (0, 0), Image.composite(squares, Image.new("RGBA", squares.size), mask))
    font = ImageFont.truetype(next(f for f in FONTS if Path(f).exists()), int(size * 0.66))
    d.text((half, half * 1.02), "\u265e", font=font, fill=LIGHT, anchor="mm")
    return image


def main():
    big = draw()
    big.save(HERE / "icon.png")
    big.save(HERE / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    if sys.platform == "darwin" and shutil.which("iconutil"):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "icon.iconset"
            folder.mkdir()
            for s in (16, 32, 128, 256, 512):
                big.resize((s, s), Image.LANCZOS).save(folder / f"icon_{s}x{s}.png")
                big.resize((s * 2, s * 2), Image.LANCZOS).save(folder / f"icon_{s}x{s}@2x.png")
            subprocess.run(["iconutil", "-c", "icns", str(folder), "-o", str(HERE / "icon.icns")], check=True)


if __name__ == "__main__":
    main()
