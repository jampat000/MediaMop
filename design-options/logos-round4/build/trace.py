"""Trace James's chosen weir mark (source.png) and report its measured geometry (#581).

Why this exists at all
----------------------
Rounds one to three were hand-drawn marks and all four were rejected. The accepted mark is a
Midjourney render, and the first attempt at productionising it was to look at the picture and
redraw the geometry by eye. That produced a symmetric dome: the eye reads "arch", draws an arch,
and the water is gone. So this round does not eyeball anything. It thresholds the PNG to two
colours, walks the actual contours, and least-squares fits circles to each band edge. Every
number in `mark.py` comes out of this script, and the fit residuals are printed so a reviewer can
see that the circles are real features of the artwork and not a story told about it.

No potrace on the build machines and no scipy in tests/requirements.txt, so the tracing is
PIL + numpy only: threshold, flood-fill labelling, run-length scanning per row and column to
recover each band edge, then a Kasa algebraic circle fit per edge.

Run it from anywhere:

    python design-options/logos-round4/build/trace.py

It prints a table and writes trace-overlay.png next to source.png so the fitted circles can be
checked against the pixels they were fitted to.
"""

from __future__ import annotations

import os
from collections import deque

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SOURCE = os.path.join(ROOT, "source.png")

# The render is essentially two colours; everything else is antialiasing along the edges.
# Nearest-of-two classification is therefore the whole thresholding step.
SRC_BG = np.array([2, 19, 39])
SRC_FG = np.array([49, 235, 192])


def load_mask(path: str = SOURCE) -> np.ndarray:
    rgb = np.array(Image.open(path).convert("RGB")).astype(int)
    d_bg = np.linalg.norm(rgb - SRC_BG, axis=2)
    d_fg = np.linalg.norm(rgb - SRC_FG, axis=2)
    return d_fg < d_bg


def label(mask: np.ndarray):
    """4-connected components. Small enough (1024x1024, two blobs) that BFS is fine."""
    h, w = mask.shape
    out = np.zeros((h, w), np.int32)
    count = 0
    for y in range(h):
        for x in range(w):
            if mask[y, x] and out[y, x] == 0:
                count += 1
                queue = deque([(y, x)])
                out[y, x] = count
                while queue:
                    cy, cx = queue.popleft()
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and out[ny, nx] == 0:
                            out[ny, nx] = count
                            queue.append((ny, nx))
    return out, count


def runs(line: np.ndarray):
    """Run-length spans of True along a 1-D slice: the cheap way to find band edges."""
    spans = []
    start = None
    for i, v in enumerate(line):
        if v and start is None:
            start = i
        elif not v and start is not None:
            spans.append((start, i - 1))
            start = None
    if start is not None:
        spans.append((start, len(line) - 1))
    return spans


def fit_circle(points):
    """Kasa algebraic circle fit. Returns (cx, cy, r, max |residual|).

    The max residual is the number that matters here: it says whether the edge really is a
    circular arc. Anything under ~1.5px on a 1024px render means the fit is describing the
    artwork rather than averaging over something that is not a circle.
    """
    p = np.asarray(points, float)
    x, y = p[:, 0], p[:, 1]
    a = np.c_[2 * x, 2 * y, np.ones(len(p))]
    sol, *_ = np.linalg.lstsq(a, x * x + y * y, rcond=None)
    cx, cy = sol[0], sol[1]
    r = float(np.sqrt(sol[2] + cx * cx + cy * cy))
    res = np.abs(np.hypot(x - cx, y - cy) - r)
    return float(cx), float(cy), r, float(res.max())


def measure(mask: np.ndarray) -> dict:
    lab, n = label(mask)
    assert n == 2, f"expected two blobs (arcs, and tailrace+apron), got {n}"
    arcs = lab == 1        # the outer and middle streams, which touch near the crest
    race = lab == 2        # inner stream + tailrace bar + apron, all one piece

    out = {}

    # Outer stream, outer edge: leftmost pixel per row while the edge is still curving, plus
    # topmost pixel per column. Rows past ~505 are the straight leg and would bend the fit.
    pts = [(runs(arcs[y])[0][0], y) for y in range(300, 501)]
    pts += [(x, runs(arcs[:, x])[0][0]) for x in range(250, 716) if len(runs(arcs[:, x]))]
    out["A_out"] = fit_circle(pts)

    # Middle stream, outer edge: start of the second run per row / top of the second run per
    # column, over the range where the two streams are still separated by background.
    pts = [(runs(arcs[y])[1][0], y) for y in range(395, 535) if len(runs(arcs[y])) > 1]
    pts += [(x, runs(arcs[:, x])[1][0]) for x in range(350, 536) if len(runs(arcs[:, x])) > 1]
    out["B_out"] = fit_circle(pts)

    # Middle stream, inner edge.
    pts = [(runs(arcs[y])[1][1], y) for y in range(430, 535) if len(runs(arcs[y])) > 1]
    pts += [(x, runs(arcs[:, x])[1][1]) for x in range(450, 536) if len(runs(arcs[:, x])) > 1]
    out["B_in"] = fit_circle(pts)

    # Inner stream: the elbow corner where the leg turns into the tailrace.
    pts = [(runs(race[y])[0][0], y) for y in range(465, 548)]
    out["C_corner"] = fit_circle(pts)

    # Straight features, read off directly rather than fitted.
    row = 600  # well inside the parallel vertical legs
    out["legs"] = runs(mask[row])
    col = 300  # through the outer leg and the apron
    out["apron_rows"] = runs(mask[:, col])[-1]
    out["race_rows"] = runs(mask[:, 790])[0]
    ys, xs = np.nonzero(mask)
    out["bbox"] = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    return out


def overlay(mask: np.ndarray, m: dict, path: str) -> None:
    img = np.zeros(mask.shape + (3,), np.uint8)
    img[...] = (11, 20, 24)
    img[mask] = (62, 215, 200)
    im = Image.fromarray(img)
    draw = ImageDraw.Draw(im)
    for key in ("A_out", "B_out", "B_in", "C_corner"):
        cx, cy, r, _ = m[key]
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 90, 90))
        draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(255, 210, 90))
    im.save(path)


def main() -> None:
    mask = load_mask()
    m = measure(mask)
    print(f"source bbox x{m['bbox'][0]}..{m['bbox'][2]}  y{m['bbox'][1]}..{m['bbox'][3]}")
    for key in ("A_out", "B_out", "B_in", "C_corner"):
        cx, cy, r, res = m[key]
        print(f"{key:9s} centre=({cx:7.1f},{cy:7.1f})  r={r:6.1f}  max residual={res:5.2f}px")
    print("legs at row 600 (start, end):", m["legs"])
    print("apron rows:", m["apron_rows"], " tailrace bar rows:", m["race_rows"])
    out = os.path.join(ROOT, "trace-overlay.png")
    overlay(mask, m, out)
    print("overlay:", out)


if __name__ == "__main__":
    main()
