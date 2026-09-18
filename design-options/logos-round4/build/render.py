"""Render SVG strings to PNG with Chromium (same rasteriser a browser tab uses)."""

from __future__ import annotations

import os

from playwright.sync_api import sync_playwright

_PAGE = """<!doctype html><meta charset="utf-8">
<style>html,body{{margin:0;padding:0;background:transparent}}
svg{{display:block}}</style>{body}"""


def render_many(jobs, transparent=True):
    """jobs: [(svg_markup, out_png_path, px_w, px_h)]"""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb"])
        page = browser.new_page(device_scale_factor=1)
        for svg, out, w, h in jobs:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            page.set_viewport_size({"width": max(1, int(w)), "height": max(1, int(h))})
            page.set_content(_PAGE.format(body=svg))
            page.screenshot(path=out, omit_background=transparent)
        browser.close()


def render_html(html, out, w, h, transparent=False, scale=1):
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb"])
        page = browser.new_page(device_scale_factor=scale)
        page.set_viewport_size({"width": int(w), "height": int(h)})
        page.set_content(html)
        page.wait_for_timeout(120)
        page.screenshot(path=out, omit_background=transparent)
        browser.close()
