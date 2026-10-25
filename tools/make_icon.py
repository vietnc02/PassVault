"""Draw the PassVault padlock icon into assets/passvault.ico (and a PNG preview)
and the Chrome extension's PNG icons.

Needs Pillow, which the app itself doesn't: .venv\\Scripts\\pip install pillow
"""

from pathlib import Path

from PIL import Image, ImageDraw

PROJECT = Path(__file__).resolve().parent.parent
ASSETS = PROJECT / "assets"
EXTENSION_ICONS = PROJECT / "extension" / "icons"
SIZE = 1024  # draw large, then downscale for smooth edges
TOP, BOTTOM = (74, 134, 240), (31, 79, 184)
WHITE = (255, 255, 255, 255)


def draw() -> Image.Image:
    gradient = Image.new("RGBA", (SIZE, SIZE))
    for y in range(SIZE):
        t = y / (SIZE - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)) + (255,)
        ImageDraw.Draw(gradient).line([(0, y), (SIZE, y)], fill=color)

    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle([48, 48, 976, 976], radius=220, fill=255)
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    icon.paste(gradient, mask=mask)

    d = ImageDraw.Draw(icon)
    d.rounded_rectangle([322, 190, 702, 640], radius=190, outline=WHITE, width=88)  # shackle
    d.rounded_rectangle([232, 460, 792, 850], radius=90, fill=WHITE)  # body
    d.ellipse([452, 560, 572, 680], fill=BOTTOM)  # keyhole
    d.rounded_rectangle([487, 620, 537, 770], radius=22, fill=BOTTOM)
    return icon


def main():
    ASSETS.mkdir(exist_ok=True)
    EXTENSION_ICONS.mkdir(exist_ok=True)
    big = draw()
    icon = big.resize((256, 256), Image.LANCZOS)
    icon.save(ASSETS / "passvault.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.save(ASSETS / "passvault.png")
    for size in (16, 32, 48, 128):
        big.resize((size, size), Image.LANCZOS).save(EXTENSION_ICONS / f"icon{size}.png")


if __name__ == "__main__":
    main()
