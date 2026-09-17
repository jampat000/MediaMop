# Weir brand mark

The mark is a weir in section: a low wall with water running up to it and spilling over its
curved crest. Two shapes, so it still reads at 16px.

| File | Use |
| --- | --- |
| `weir-mark.svg` | Mark for dark backgrounds: gold water `#d4af37`, stone wall `#e7e7ea`. |
| `weir-mark-light.svg` | Mark for light backgrounds: gold water `#9f7417`, ink wall `#211f1a`. |
| `weir-app-icon.svg` | The dark mark on a charcoal rounded tile. Source of every favicon and Windows icon. |

The web app draws the same geometry inline (`apps/web/src/components/brand/weir-logo.tsx`) so
it follows the theme tokens `--mm-brand-water`, `--mm-brand-wall` and `--mm-brand-wordmark`. The
wordmark is the word "Weir" set in the app font (Outfit), not outlines.

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

If you change the mark's geometry, copy the two `<path>` elements into `weir-logo.tsx` as well.
