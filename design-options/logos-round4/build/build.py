"""Write round four's SVGs and PNGs, the 16px gate sheet, and the contact sheet for James (#581).

Reuses round two's Chromium rasteriser (render.py) and its geometry helpers (geom.py) verbatim,
copied in beside this file so the round is self-contained: same grid, same sizes, same renderer,
so round four's sheets are directly comparable with round three's.

    python design-options/logos-round4/build/build.py

The gate sheet is not decoration. Rounds two and three both had a candidate that looked fine at
512 and turned to porridge at 16, and the only way that was caught was magnifying the real 16 and
32px rasters and looking at them. Nothing here ships before that sheet has been looked at.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from PIL import Image, ImageDraw  # noqa: E402

import mark  # noqa: E402
from render import render_many  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SVG_DIR = os.path.join(ROOT, "svg")
PNG_DIR = os.path.join(ROOT, "png")
SIZES = (512, 64, 32, 16)

# Both candidates are built every time, so the gate sheet compares like with like rather than
# comparing the shipped mark against a memory of the other one.
VARIANTS = ((3, "three"), (2, "two"))


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")


def build() -> None:
    jobs = []
    for streams, tag in VARIANTS:
        for theme in ("dark", "light"):
            surface = mark.DARK["surface"] if theme == "dark" else mark.LIGHT["surface"]
            write(os.path.join(SVG_DIR, f"{tag}-{theme}.svg"), mark.svg(theme, streams=streams))
            on_surface = mark.svg(theme, streams=streams, surface=surface)
            for size in SIZES:
                jobs.append((on_surface, os.path.join(PNG_DIR, f"{tag}-{theme}-{size}.png"), size, size))
        # Single colour on the dark surface: the tray-icon case, and the one a second tone kills.
        write(os.path.join(SVG_DIR, f"{tag}-mono.svg"), mark.svg("dark", mono=True, streams=streams))
        mono = mark.svg("dark", mono=True, streams=streams, surface=mark.DARK["surface"])
        for size in SIZES:
            jobs.append((mono, os.path.join(PNG_DIR, f"{tag}-mono-{size}.png"), size, size))
    render_many(jobs, transparent=False)
    print(f"wrote {len(jobs)} PNGs")


def gate(out_name: str = "gate-16px.png") -> str:
    """Magnify the real 16 and 32px rasters 9x and put them side by side.

    Nearest-neighbour on purpose: the question is which pixels are actually set, not what a
    smooth resample would like us to believe.
    """
    z, pad = 9, 14
    label_w = 190
    row_w = pad + (16 * z + pad + 32 * z + pad) * 3 + label_w
    row_h = 32 * z + pad
    sheet = Image.new("RGB", (row_w, row_h * len(VARIANTS) + pad + 26), "#111517")
    draw = ImageDraw.Draw(sheet)
    x0 = pad
    for i, theme in enumerate(("dark", "light", "mono")):
        draw.text((x0 + i * (16 * z + pad + 32 * z + pad) + 4, 8), f"{theme}  16px / 32px",
                  fill="#9fb3bc")
    y = pad + 26
    for streams, tag in VARIANTS:
        x = pad
        for theme in ("dark", "light", "mono"):
            for size in (16, 32):
                im = Image.open(os.path.join(PNG_DIR, f"{tag}-{theme}-{size}.png"))
                sheet.paste(im.resize((size * z, size * z), Image.NEAREST), (x, y))
                x += size * z + pad
        draw.text((x + 6, y + 8), f"{streams} streams", fill="#e8f1f4")
        y += row_h
    out = os.path.join(ROOT, out_name)
    sheet.save(out)
    print("gate sheet:", out, sheet.size)
    return out


def contact_sheet(streams: int, out_name: str) -> str:
    """The sheet James looks at: dark / light / mono at 512, then the real 64, 32 and 16."""
    # PIL's built-in bitmap font is ASCII only, so every caption here stays ASCII: an em dash
    # comes out as a tofu box, which is a silly thing to hand someone as a design deliverable.
    cell, pad, label = 240, 26, 56
    small = (64, 32, 16)
    tag = {3: "three", 2: "two"}[streams]
    width = pad + (cell + pad) * 3 + sum(small) + pad * len(small) + pad
    height = pad + label + cell + label + pad
    sheet = Image.new("RGB", (width, height), "#0b1418")
    draw = ImageDraw.Draw(sheet)
    x, y = pad, pad + label
    for theme, caption in (("dark", "dark"), ("light", "light"), ("mono", "single colour")):
        im = Image.open(os.path.join(PNG_DIR, f"{tag}-{theme}-512.png")).resize((cell, cell), Image.LANCZOS)
        sheet.paste(im, (x, y))
        draw.text((x, y - 18), caption, fill="#a6bcc6")
        draw.text((x, y + cell + 8), "512px", fill="#4a6068")
        x += cell + pad
    draw.text((x, y - 18), "actual size", fill="#a6bcc6")
    for size in small:
        im = Image.open(os.path.join(PNG_DIR, f"{tag}-dark-{size}.png"))
        sheet.paste(im, (x, y + cell - size))
        draw.text((x, y + cell + 8), f"{size}", fill="#4a6068")
        x += size + pad
    draw.text((pad, pad), f"Weir mark, {streams} streams - traced from source.png, "
                          f"regularised, Theme A 'Tailrace' tokens", fill="#e8f1f4")
    out = os.path.join(ROOT, out_name)
    sheet.save(out)
    print("contact sheet:", out, sheet.size)
    return out


# --------------------------------------------------------------------------- #
# the product assets
# --------------------------------------------------------------------------- #
# packaging/brand/*.svg is the source of truth for every raster icon
# (scripts/generate-brand-icons.py renders them with Chromium). Emitting them from mark.py
# rather than hand-copying path data is the point: a transcription typo in a 90-character path
# is invisible in review and shows up as a kinked arc in a tray icon three months later.
REPO = os.path.abspath(os.path.join(ROOT, "..", ".."))
BRAND = os.path.join(REPO, "packaging", "brand")

_HEAD = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" role="img" aria-label="Weir">'
_NOTE = (
    "\n  <!-- Generated by design-options/logos-round4/build/build.py from the geometry traced"
    "\n       out of design-options/logos-round4/source.png (see mark.py). Do not hand-edit the"
    "\n       path data: edit mark.py and re-run the build. -->"
)

# Tile corner radius: 7/32 on the old 32-unit mark, kept proportional on the 24-unit grid.
TILE_RADIUS = 24 * 7 / 32


def emit_brand() -> None:
    def mark_paths(colour: str, streams: int = mark.SHIPPED_STREAMS) -> str:
        return "".join(f'\n  <path d="{d}" fill="{colour}"/>' for d in mark.paths(streams))

    files = {
        "weir-mark.svg": (
            _HEAD + _NOTE
            + '\n  <!-- Mark for dark backgrounds: the Theme A "Tailrace" accent. -->'
            + mark_paths(mark.DARK["accent"]) + "\n</svg>"
        ),
        "weir-mark-light.svg": (
            _HEAD + _NOTE
            + "\n  <!-- Mark for light backgrounds: the light-theme accent. -->"
            + mark_paths(mark.LIGHT["accent"]) + "\n</svg>"
        ),
        "weir-app-icon.svg": (
            _HEAD + _NOTE
            + "\n  <!-- App icon: the mark on the dark surface, so it reads on any tab bar,"
            + "\n       taskbar or tray. Source of every favicon and Windows icon 48px and"
            + "\n       above (see weir-app-icon-small.svg for 16/32px). -->"
            + f'\n  <rect width="24" height="24" rx="{TILE_RADIUS:.2f}"'
            + f' fill="{mark.DARK["surface"]}"/>'
            + mark_paths(mark.DARK["accent"]) + "\n</svg>"
        ),
        # The optical-size fallback (#582, reopened): the .ico formats are the one place two
        # optical sizes of the same mark have to live side by side in a single file, so the small
        # size needs its own tile source for scripts/generate-brand-icons.py to render at 16 and
        # 32px, the same way weir-app-icon.svg is the source for 48px and above. Not used anywhere
        # else — every SVG a person actually looks at (favicon.svg, the in-app logo, the docs
        # logo, packaging/brand/weir-mark*.svg) is the three-stream primary mark. See mark.py's
        # SHIPPED_STREAMS / SMALL_STREAMS comment and packaging/brand/README.md for the reasoning
        # and the 32px call.
        "weir-app-icon-small.svg": (
            _HEAD + _NOTE
            + "\n  <!-- Small-size fallback tile: two streams, used only for the 16 and 32px"
            + "\n       frames of the .ico files. Everywhere else uses weir-app-icon.svg's three"
            + "\n       streams. See mark.py's SHIPPED_STREAMS/SMALL_STREAMS note. -->"
            + f'\n  <rect width="24" height="24" rx="{TILE_RADIUS:.2f}"'
            + f' fill="{mark.DARK["surface"]}"/>'
            + mark_paths(mark.DARK["accent"], mark.SMALL_STREAMS) + "\n</svg>"
        ),
    }
    for name, text in files.items():
        write(os.path.join(BRAND, name), text)
        print("brand:", "packaging/brand/" + name)
    print("\npath data for apps/web/src/components/brand/weir-logo.tsx:")
    for d in mark.paths():
        print(" ", d)


if __name__ == "__main__":
    build()
    gate()
    contact_sheet(3, "contact-sheet-three.png")
    contact_sheet(2, "contact-sheet.png")
    emit_brand()
