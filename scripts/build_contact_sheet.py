"""Builds ``contact-sheet.html``: every screenshot on one scrollable page, grouped by screen,
empty and seeded side by side, with a dark/light and desktop/narrow toggle.

No JavaScript: the viewer this gets read in strips ``<script>`` tags, so the toggle is plain
radio inputs plus ``:checked ~`` sibling-selector CSS. Called by scripts/screenshot-site.py after
it finishes capturing; can also be re-run on its own against an existing output directory.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Protocol


class ScreenLike(Protocol):
    index: int
    slug: str
    label: str


SCENARIOS = ["empty", "seeded"]
THEMES = ["dark", "light"]
WIDTHS = ["desktop", "narrow"]

# `~` is the general-sibling combinator: it only ever looks at LATER siblings of the same parent.
# Every radio and the whole `.sheet` are siblings in that one order, so a selector can chain two
# `:checked` conditions (theme, then width) before finally reaching `.sheet` and the shot inside it.
_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Weir screenshot contact sheet</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    color-scheme: dark;
    --bg: #0b1418;
    --panel: #13212a;
    --border: rgba(232, 241, 244, 0.14);
    --text: #e8f1f4;
    --text-dim: #a6bcc6;
    --accent: #3ed7c8;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font: 15px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif;
  }}
  header {{
    position: sticky;
    top: 0;
    z-index: 10;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    padding: 12px 20px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 24px;
  }}
  header h1 {{
    font-size: 16px;
    margin: 0;
    color: var(--accent);
    white-space: nowrap;
  }}
  .toggle-group {{
    display: flex;
    gap: 4px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 3px;
  }}
  /* The real radios live as direct children of <body> so `~` can reach both the header (for the
     pressed-look on labels) and <main> (for which shots show). Only their <label>s are visible. */
  body > input[type="radio"] {{
    position: absolute;
    opacity: 0;
    width: 0;
    height: 0;
    pointer-events: none;
  }}
  .toggle-group label {{
    padding: 6px 14px;
    border-radius: 999px;
    font-size: 13px;
    cursor: pointer;
    color: var(--text-dim);
  }}
  nav.toc {{
    padding: 14px 20px;
    border-bottom: 1px solid var(--border);
    display: flex;
    flex-wrap: wrap;
    gap: 6px 16px;
  }}
  nav.toc a {{
    color: var(--text-dim);
    text-decoration: none;
    font-size: 13px;
  }}
  nav.toc a:hover {{ color: var(--accent); }}
  main {{ padding: 24px 20px 80px; }}
  section.screen {{
    border-top: 1px solid var(--border);
    padding: 28px 0;
  }}
  section.screen:first-child {{ border-top: none; }}
  section.screen h2 {{
    font-size: 18px;
    margin: 0 0 14px;
  }}
  .cols {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }}
  .col h3 {{
    margin: 0 0 8px;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-dim);
  }}
  .col {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px;
    min-height: 60px;
  }}
  .shot {{
    display: none;
    max-width: 100%;
    border-radius: 6px;
    border: 1px solid var(--border);
  }}
  .missing {{
    color: var(--text-dim);
    font-style: italic;
    font-size: 13px;
  }}

  /* --- the no-JS toggle: two independent radio groups, ANDed together per combination --- */
  #theme-dark:checked ~ #width-desktop:checked ~ main .shot.theme-dark.width-desktop,
  #theme-dark:checked ~ #width-narrow:checked ~ main .shot.theme-dark.width-narrow,
  #theme-light:checked ~ #width-desktop:checked ~ main .shot.theme-light.width-desktop,
  #theme-light:checked ~ #width-narrow:checked ~ main .shot.theme-light.width-narrow {{
    display: block;
  }}

  #theme-dark:checked ~ header label[for="theme-dark"],
  #theme-light:checked ~ header label[for="theme-light"],
  #width-desktop:checked ~ header label[for="width-desktop"],
  #width-narrow:checked ~ header label[for="width-narrow"] {{
    background: var(--accent);
    color: #04191c;
  }}
</style>
</head>
<body>
<input type="radio" name="theme" id="theme-dark" checked>
<input type="radio" name="theme" id="theme-light">
<input type="radio" name="width" id="width-desktop" checked>
<input type="radio" name="width" id="width-narrow">
<header>
  <h1>Weir screenshot contact sheet</h1>
  <div class="toggle-group">
    <label for="theme-dark">Dark</label>
    <label for="theme-light">Light</label>
  </div>
  <div class="toggle-group">
    <label for="width-desktop">Desktop</label>
    <label for="width-narrow">Narrow</label>
  </div>
</header>
<nav class="toc">
{toc}
</nav>
<main>
{body}
</main>
</body>
</html>
"""


def build_contact_sheet(output_dir: Path, screens: list[ScreenLike]) -> None:
    toc_links = []
    sections = []
    for screen in screens:
        toc_links.append(f'<a href="#screen-{escape(screen.slug)}">{screen.index:02d}. {escape(screen.label)}</a>')

        cols = []
        for scenario in SCENARIOS:
            shots = []
            for theme in THEMES:
                for width in WIDTHS:
                    name = f"{screen.index:02d}-{screen.slug}--{scenario}--{theme}--{width}.png"
                    if not (output_dir / name).is_file():
                        continue
                    shots.append(
                        f'<img class="shot theme-{theme} width-{width}" src="{escape(name)}" '
                        f'alt="{escape(screen.label)} ({scenario}, {theme}, {width})" loading="lazy">'
                    )
            if not shots:
                shots.append('<p class="missing">not captured</p>')
            cols.append(f'<div class="col"><h3>{escape(scenario)}</h3>{"".join(shots)}</div>')

        sections.append(
            f'<section class="screen" id="screen-{escape(screen.slug)}">'
            f"<h2>{screen.index:02d}. {escape(screen.label)}</h2>"
            f'<div class="cols">{"".join(cols)}</div>'
            f"</section>"
        )

    html = _TEMPLATE.format(toc="\n".join(toc_links), body="\n".join(sections))
    (output_dir / "contact-sheet.html").write_text(html, encoding="utf-8")
