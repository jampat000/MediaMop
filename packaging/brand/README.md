# Weir brand mark

The mark is water going over a weir: the outer stream runs up to the crest, turns, and tips over
it; the inner stream turns a quarter and runs off to the right as the tailrace, with the apron
bar underneath. Two paths, one colour, so it still reads at 16px and so the Windows tray icon —
a single-colour mask — is the same mark as the one in the app.

| File | Use |
| --- | --- |
| `weir-mark.svg` | Mark for dark backgrounds: accent `#3ed7c8`. |
| `weir-mark-light.svg` | Mark for light backgrounds: accent `#0d6f68`. |
| `weir-app-icon.svg` | The mark on the `#0b1418` rounded tile. Source of every favicon and Windows icon. |

Those are the live Theme A "Tailrace" accents from `apps/web/src/styles/weir-tokens.css`. The web
app draws the same geometry inline (`apps/web/src/components/brand/weir-logo.tsx`) so it follows
the theme tokens `--mm-brand-water` and `--mm-brand-wordmark` instead. The wordmark is the word
"Weir" set in the app font (Outfit), not outlines.

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
- `build/build.py` writes the three SVGs in this folder, the contact sheet, and the 16px gate
  sheet.

**The mark ships with two streams, not the three in the source render.** Three do not survive
16px: a band is 1.2 device pixels there and the arcs fuse into a smear. See
`design-options/logos-round4/gate-16px.png`, which magnifies the real 16 and 32px rasters, and
the `SHIPPED_STREAMS` note in `mark.py`.

To change the mark, edit `mark.py` and run:

```
python design-options/logos-round4/build/build.py
```

That rewrites the three SVGs here and prints the path data to paste into `weir-logo.tsx`.

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
