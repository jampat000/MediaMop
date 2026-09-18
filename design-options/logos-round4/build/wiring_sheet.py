"""Draw design-options/logos-round4/wiring-comparison.png from the files that actually ship.

The top row is the three primary SVGs at 512. The bottom row is the real frames unpacked
out of the committed .ico files and magnified, so the sheet cannot drift from what the
icons contain: if the cutoff in scripts/generate-brand-icons.py moves, re-running this
shows the move rather than describing it.

    python design-options/logos-round4/build/wiring_sheet.py
"""

from __future__ import annotations

import io
import pathlib

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "design-options" / "logos-round4" / "wiring-comparison.png"

BG = (11, 20, 24)
INK = (232, 241, 244)
DIM = (122, 146, 154)
LIGHT_TILE = (234, 240, 242)

PRIMARY = [
    (ROOT / "packaging" / "brand" / "weir-mark.svg", "dark (primary, three streams)", None),
    (ROOT / "packaging" / "brand" / "weir-mark-light.svg", "light (primary, three streams)", LIGHT_TILE),
]

# One .ico is enough: the tray icon is the same tile through the same cutoff.
ICO = (ROOT / "apps" / "web" / "public" / "favicon.ico", "favicon.ico")
FRAME_SIZES = (16, 24, 32, 48)
ZOOM = 6


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_svg(page, path: pathlib.Path, size: int) -> Image.Image:
    svg = path.read_text(encoding="utf-8").replace("<svg ", f'<svg width="{size}" height="{size}" ', 1)
    page.set_viewport_size({"width": size, "height": size})
    page.set_content(f"<html><body style='margin:0;background:transparent'>{svg}</body></html>")
    return Image.open(io.BytesIO(page.locator("svg").screenshot(omit_background=True, type="png"))).convert("RGBA")


def ico_frame(path: pathlib.Path, size: int) -> Image.Image:
    im = Image.open(path)
    im.size = (size, size)  # Pillow selects the .ico frame by assignment.
    return im.convert("RGBA")


def main() -> int:
    big = 300
    sheet = Image.new("RGBA", (1000, 800), BG + (255,))
    draw = ImageDraw.Draw(sheet)
    f_title, f_label, f_small = font(15), font(13), font(12)

    draw.text((24, 22), "Weir mark wiring: three streams everywhere except the 16px .ico frame", INK, f_title)

    draw.text((24, 58), "Primary mark (packaging/brand, favicon.svg, sidebar, docs) - 300px", DIM, f_label)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=1)

        x = 24
        for path, caption, tile in PRIMARY:
            art = render_svg(page, path, big)
            if tile is not None:
                plate = Image.new("RGBA", (big, big), tile + (255,))
                plate.alpha_composite(art)
                art = plate
            sheet.alpha_composite(art, (x, 82))
            draw.text((x, 82 + big + 10), caption, DIM, f_small)
            x += big + 40

        ico_path, ico_label = ICO
        frames = {size: ico_frame(ico_path, size) for size in FRAME_SIZES}
        browser.close()

    top = 432
    draw.text((24, top), f"Actual {ico_label} frames - what each size really shows (zoomed {ZOOM}x)", DIM, f_label)
    baseline = top + 28 + 48 * ZOOM
    x = 24
    for size in FRAME_SIZES:
        art = frames[size].resize((size * ZOOM, size * ZOOM), Image.NEAREST)
        sheet.alpha_composite(art, (x, baseline - size * ZOOM))
        streams = "two streams" if size <= 16 else "three streams"
        draw.text((x, baseline + 10), f"{size}px", INK, f_small)
        draw.text((x, baseline + 28), streams, DIM, f_small)
        x += size * ZOOM + 30

    sheet.convert("RGB").save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
