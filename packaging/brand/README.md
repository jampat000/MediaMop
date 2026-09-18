# Weir brand mark

The mark is water going over a weir: the outer stream runs up to the crest, turns, and tips over
it; the inner stream turns a quarter and runs off to the right as the tailrace, with the apron
bar underneath. One colour, all fills, so the Windows tray icon — a single-colour mask — is the
same mark as the one in the app.

## Two optical sizes, on purpose (#582, reopened by James)

There are **two drawings of this mark in the repo, and that is deliberate, not drift**:

- **Three streams — the primary mark.** This is the mark exactly as traced from the Midjourney
  render James accepted, and it is what he asked for after looking at the two-stream mark #582
  shipped ("logo is not exact I want this one"). It is used everywhere the mark is seen at a
  size that can actually show it: `weir-mark.svg`, `weir-mark-light.svg`, `weir-app-icon.svg`
  below, the SVG favicon (`apps/web/public/favicon.svg`), the apple touch icon, the in-app
  sidebar mark (`apps/web/src/components/brand/weir-logo.tsx`), the docs logo, and every
  512/256/128/64 raster.
- **Two streams — the small-size fallback, `weir-app-icon-small.svg` below.** Three bands do not
  survive being rasterised down to 16px: a 1.85-unit band on a 24-unit grid is 1.23 device pixels
  there, sub-pixel by construction, and the arcs fuse into a smear (see
  `design-options/logos-round4/gate-16px.png` and `mark.py`'s `SHIPPED_STREAMS` comment). This
  drawing exists only to be the 16px frame inside the `.ico` files: the favicon `.ico`, the docs
  `.ico`, and the Windows tray icon. It is not used anywhere a person looks at an SVG or a large
  raster directly.

This is the standard type-design move of shipping separate "text" and "display" masters of one
typeface: the identity is one mark, traced once, but which optical size represents it changes
with how small it will actually be shown. Nothing about the underlying geometry differs between
the two — `mark.py`'s `paths(3)` is `paths(2)` plus one more band on the same radius ladder — so
"fixing" the two to match by deleting one of them would be removing a deliberate accommodation,
not tidying up an inconsistency.

**Where the cutoff sits.** Only the 16px frame falls back. `design-options/logos-round4/gate-16px.png`
renders both drawings at 16 and 32 in dark, light and single colour: at 32 a band is 1.33 device
pixels, the three arcs separate cleanly and the crest holds in every rendering including the
single-colour one the tray icon uses; at 16 a band is sub-pixel and they fuse. An earlier revision
of this put the cutoff at 32 out of caution, which cost the real mark two of the three sizes a
person actually sees in a tab strip or a system tray for no legibility gain. See
`scripts/generate-brand-icons.py`'s `SMALL_ICON_MAX` for where the cutoff is enforced, and
`design-options/logos-round4/wiring-comparison.png` for the actual rendered frames at each size.

| File | Streams | Use |
| --- | --- | --- |
| `weir-mark.svg` | three (primary) | Mark for dark backgrounds: accent `#3ed7c8`. |
| `weir-mark-light.svg` | three (primary) | Mark for light backgrounds: accent `#0d6f68`. |
| `weir-app-icon.svg` | three (primary) | The mark on the `#0b1418` rounded tile. Source of every favicon/Windows icon frame **24px and above**. |
| `weir-app-icon-small.svg` | two (fallback) | The same tile with the small-size fallback geometry. Source of the favicon/Windows icon frame at **16px only**. |

Those accents are the live Theme A "Tailrace" tokens from `apps/web/src/styles/weir-tokens.css`.
The web app draws the same geometry inline (`apps/web/src/components/brand/weir-logo.tsx`) so it
follows the theme tokens `--mm-brand-water` and `--mm-brand-wordmark` instead — always the
three-stream primary mark, since the sidebar never renders it anywhere near 16px. The wordmark is
the word "Weir" set in the app font (Outfit), not outlines.

## Where the geometry comes from (#581)

The SVGs here are generated, not drawn. James accepted a rendered mark after four rounds of
hand-drawn ones were rejected; that render is kept at `design-options/logos-round4/source.png`,
and the build traces it rather than redrawing it by eye:

- `design-options/logos-round4/build/trace.py` thresholds the render to two colours, walks the
  contours and least-squares fits a circle to every band edge. Residuals are under 1.3px on a
  1024px render, so the arcs in the SVGs are the arcs in the artwork.
- `build/mark.py` puts those measurements on a 24-unit grid with a 20-unit live area and fixes
  the two defects in the render: a third-colour sliver inside the middle stream, and the middle
  stream being nearly twice the width of the other two. Its module comments carry the reasoning.
- `build/build.py` writes the four SVGs in this folder, the contact sheets, and the 16px gate
  sheet.

**The mark is the three-stream render exactly as traced.** See the "Two optical sizes" section
above for why a two-stream fallback also exists and where it is and is not used — that split is
about small `.ico` frames only, not about which geometry is "the" mark.

To change the mark, edit `mark.py` and run:

```
python design-options/logos-round4/build/build.py
```

That rewrites the four SVGs here and prints the path data to paste into `weir-logo.tsx`.

## Regenerating the raster icons

The SVGs are the source of truth. After changing one, run from the repository root:

```
python -m pip install --require-hashes -r tests/requirements.txt   # once: Playwright
python -m playwright install chromium                               # once
python scripts/generate-brand-icons.py
```

It renders with Chromium and rewrites, all committed:

- `apps/web/public/favicon.svg`, `favicon.ico`, `apple-touch-icon.png`
- `packaging/windows/assets/weir-tray-icon.ico` (tray, executable and installer icon)
- `docs-site/static/img/favicon.ico`, `logo.svg`, `logo-dark.svg`
