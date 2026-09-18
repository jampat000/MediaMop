"""Regenerate every raster Weir icon from the SVG sources in packaging/brand.

The SVGs are the source of truth. This renders them with Playwright's Chromium (already a test
dependency: tests/requirements.txt) and writes PNG-framed .ico files, the format Windows has read
since Vista and the format the previous icons used.

    python scripts/generate-brand-icons.py

Outputs (all committed):
  apps/web/public/favicon.svg, favicon.ico, apple-touch-icon.png
  packaging/windows/assets/weir-tray-icon.ico      (tray and installer icon)
  docs-site/static/img/favicon.ico, logo.svg, logo-dark.svg

## Two optical sizes in one .ico (James's three-stream request, reopening #582)

`weir-app-icon.svg` carries the three-stream primary mark and is the source for every frame
48px and above, same as every other asset here. But a multi-resolution .ico is exactly the one
place two different drawings of "the same icon" have to live side by side in a single file, and
`design-options/logos-round4/build/mark.py`'s SHIPPED_STREAMS/SMALL_STREAMS note (plus the 32px
check recorded in packaging/brand/README.md) found that three streams still don't earn their
keep at 16 or 32px: the bands are sub-pixel at 16, and at 32 they are wide enough to count but
the crest still softens under anti-aliasing, most visibly in the single-colour tray rendering
that is exactly what the .ico's 32px frame is used for. So the 16 and 32px frames render from
`weir-app-icon-small.svg` instead — the same tile with the two-stream fallback geometry — and
only 48px and above use the three-stream `weir-app-icon.svg`. `favicon.svg` itself (the SVG
favicon, not the .ico) is unaffected: browsers scale one vector for it, at whatever size they
show it, so it is always the three-stream primary mark like every other SVG in this repo.
"""

from __future__ import annotations

import shutil
import struct
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "packaging" / "brand"
APP_ICON = BRAND / "weir-app-icon.svg"
APP_ICON_SMALL = BRAND / "weir-app-icon-small.svg"
MARK_DARK = BRAND / "weir-mark.svg"
MARK_LIGHT = BRAND / "weir-mark-light.svg"

# Below this size, .ico frames render from the two-stream fallback tile; at and above it, from
# the three-stream primary tile. See the module docstring and packaging/brand/README.md.
SMALL_ICON_MAX = 32


def render_png(page, svg_path: Path, size: int) -> bytes:
    svg = svg_path.read_text(encoding="utf-8").replace("<svg ", f'<svg width="{size}" height="{size}" ', 1)
    page.set_viewport_size({"width": size, "height": size})
    page.set_content(f"<html><body style='margin:0;background:transparent'>{svg}</body></html>")
    return page.locator("svg").screenshot(omit_background=True, type="png")


def pack_ico(frames: dict[int, bytes]) -> bytes:
    sizes = sorted(frames)
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b""
    data = b""
    for size in sizes:
        png = frames[size]
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    return header + entries + data


def main() -> None:
    web_public = ROOT / "apps" / "web" / "public"
    docs_img = ROOT / "docs-site" / "static" / "img"
    tray_ico = ROOT / "packaging" / "windows" / "assets" / "weir-tray-icon.ico"

    icon_sizes = (16, 24, 32, 48, 64, 128, 256)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=1)
        frames = {
            n: render_png(page, APP_ICON_SMALL if n <= SMALL_ICON_MAX else APP_ICON, n)
            for n in icon_sizes
        }
        # The touch icon (180px, iOS home screen) and favicon.svg are both well above the small
        # cutoff and always the three-stream primary mark, rendered from the full-size tile.
        touch = render_png(page, APP_ICON, 180)
        browser.close()

    favicon = pack_ico({n: frames[n] for n in (16, 24, 32, 48, 64, 256)})
    (web_public / "favicon.ico").write_bytes(favicon)
    (web_public / "apple-touch-icon.png").write_bytes(touch)
    shutil.copyfile(APP_ICON, web_public / "favicon.svg")
    tray_ico.write_bytes(pack_ico(frames))
    (docs_img / "favicon.ico").write_bytes(favicon)
    shutil.copyfile(MARK_LIGHT, docs_img / "logo.svg")
    shutil.copyfile(MARK_DARK, docs_img / "logo-dark.svg")
    print("Brand icons regenerated from", BRAND.relative_to(ROOT))


if __name__ == "__main__":
    main()
