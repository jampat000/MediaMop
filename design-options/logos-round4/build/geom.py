"""Geometry primitives for the Weir identity exploration (round 2).

Everything is constructed, not eyeballed: strokes are real outlines produced by
offsetting a polyline with mitred joins, arcs are exact circle arcs, and the
letterforms are built from the same primitives so the wordmark and the marks
share one set of rules.

Coordinate convention: SVG screen coordinates, y increases downwards.
Angles (alpha) are measured from the +x axis and increase clockwise on screen,
so 0 = 3 o'clock, 90 = 6 o'clock, 180 = 9 o'clock, 270 = 12 o'clock.
"""

from __future__ import annotations

import math

# --------------------------------------------------------------------------- #
# number / path formatting
# --------------------------------------------------------------------------- #


def n(v: float) -> str:
    """Trim a float to a compact, deterministic string."""
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def pt(p) -> str:
    return f"{n(p[0])} {n(p[1])}"


# --------------------------------------------------------------------------- #
# vector helpers
# --------------------------------------------------------------------------- #


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def mul(a, k):
    return (a[0] * k, a[1] * k)


def norm(a):
    m = math.hypot(a[0], a[1])
    return (a[0] / m, a[1] / m)


def left_normal(d):
    """Unit normal, 90 degrees anticlockwise on screen from direction d."""
    d = norm(d)
    return (d[1], -d[0])


def line_intersect(p1, d1, p2, d2):
    """Intersection of the infinite lines p1 + t*d1 and p2 + u*d2."""
    det = d1[0] * -d2[1] - d1[1] * -d2[0]
    if abs(det) < 1e-9:
        return None
    rhs = sub(p2, p1)
    t = (rhs[0] * -d2[1] - rhs[1] * -d2[0]) / det
    return add(p1, mul(d1, t))


def on_circle(c, r, alpha_deg):
    a = math.radians(alpha_deg)
    return (c[0] + r * math.cos(a), c[1] + r * math.sin(a))


# --------------------------------------------------------------------------- #
# stroke outlining
# --------------------------------------------------------------------------- #


def _offset_side(pts, h, cap_start, cap_end):
    """One side of an offset polyline, mitred at joins, cut at the ends.

    `cap_*` is one of 'h' (horizontal cut), 'v' (vertical cut) or 'p'
    (perpendicular to the end segment).
    """
    segs = []
    for a, b in zip(pts, pts[1:]):
        d = norm(sub(b, a))
        off = mul(left_normal(d), h)
        segs.append((add(a, off), d))

    out = []

    def cap_dir(kind, seg_dir):
        if kind == "h":
            return (1.0, 0.0)
        if kind == "v":
            return (0.0, 1.0)
        return left_normal(seg_dir)

    p0, d0 = segs[0]
    start = line_intersect(p0, d0, pts[0], cap_dir(cap_start, d0))
    out.append(start)

    for (pa, da), (pb, db) in zip(segs, segs[1:]):
        j = line_intersect(pa, da, pb, db)
        out.append(j if j is not None else pb)

    pl, dl = segs[-1]
    out.append(line_intersect(pl, dl, pts[-1], cap_dir(cap_end, dl)))
    return out


def stroke_outline(pts, width, cap_start="p", cap_end="p"):
    """Closed polygon outline of a mitred monoline stroke through `pts`."""
    h = width / 2.0
    a = _offset_side(pts, h, cap_start, cap_end)
    b = _offset_side(pts, -h, cap_start, cap_end)
    return a + list(reversed(b))


def poly_path(points, close=True):
    d = "M" + pt(points[0]) + "".join("L" + pt(p) for p in points[1:])
    return d + "Z" if close else d


def stroke_path(pts, width, cap_start="p", cap_end="p"):
    return poly_path(stroke_outline(pts, width, cap_start, cap_end))


def round_poly_path(points, radius, close=True):
    """Polygon with every corner replaced by a tangent circular arc."""
    k = len(points)
    parts = []
    idx = range(k) if close else range(1, k - 1)
    first = None
    for i in idx:
        prev = points[(i - 1) % k]
        cur = points[i]
        nxt = points[(i + 1) % k]
        d1 = norm(sub(prev, cur))
        d2 = norm(sub(nxt, cur))
        ang = math.acos(max(-1.0, min(1.0, d1[0] * d2[0] + d1[1] * d2[1])))
        t = radius / math.tan(ang / 2.0)
        t = min(t, math.hypot(*sub(prev, cur)) / 2.0, math.hypot(*sub(nxt, cur)) / 2.0)
        a = add(cur, mul(d1, t))
        b = add(cur, mul(d2, t))
        cross = d1[0] * d2[1] - d1[1] * d2[0]
        sweep = 0 if cross > 0 else 1
        if first is None:
            first = a
            parts.append("M" + pt(a))
        else:
            parts.append("L" + pt(a))
        parts.append(f"A{n(radius)} {n(radius)} 0 0 {sweep} {pt(b)}")
    parts.append("Z")
    return "".join(parts)


def arc_to(p, r, alpha_from, alpha_to):
    """SVG 'A' command travelling from alpha_from to alpha_to on a circle."""
    delta = alpha_to - alpha_from
    large = 1 if abs(delta) > 180 else 0
    sweep = 1 if delta > 0 else 0
    return f"A{n(r)} {n(r)} 0 {large} {sweep} {pt(p)}"


def ring_path(c, r_out, r_in):
    """Full annulus as two circles (use fill-rule evenodd)."""
    return (
        f"M{n(c[0] - r_out)} {n(c[1])}"
        f"A{n(r_out)} {n(r_out)} 0 1 1 {n(c[0] + r_out)} {n(c[1])}"
        f"A{n(r_out)} {n(r_out)} 0 1 1 {n(c[0] - r_out)} {n(c[1])}Z"
        f"M{n(c[0] - r_in)} {n(c[1])}"
        f"A{n(r_in)} {n(r_in)} 0 1 1 {n(c[0] + r_in)} {n(c[1])}"
        f"A{n(r_in)} {n(r_in)} 0 1 1 {n(c[0] - r_in)} {n(c[1])}Z"
    )


def arc_band_path(c, r_out, r_in, a0, a1):
    """A sector of an annulus between angles a0 and a1, radially cut ends."""
    return (
        "M" + pt(on_circle(c, r_out, a0))
        + arc_to(on_circle(c, r_out, a1), r_out, a0, a1)
        + "L" + pt(on_circle(c, r_in, a1))
        + arc_to(on_circle(c, r_in, a0), r_in, a1, a0)
        + "Z"
    )


def squircle_path(x, y, w, h, r):
    """Rounded rectangle whose corners use a smooth (superellipse-ish) curve.

    The corner is a cubic with handles pulled to 0.55 of the radius, which
    removes the tangency kink a plain quarter-circle leaves at icon sizes.
    """
    k = r * 0.44
    return (
        f"M{n(x + r)} {n(y)}"
        f"L{n(x + w - r)} {n(y)}"
        f"C{n(x + w - k)} {n(y)} {n(x + w)} {n(y + k)} {n(x + w)} {n(y + r)}"
        f"L{n(x + w)} {n(y + h - r)}"
        f"C{n(x + w)} {n(y + h - k)} {n(x + w - k)} {n(y + h)} {n(x + w - r)} {n(y + h)}"
        f"L{n(x + r)} {n(y + h)}"
        f"C{n(x + k)} {n(y + h)} {n(x)} {n(y + h - k)} {n(x)} {n(y + h - r)}"
        f"L{n(x)} {n(y + r)}"
        f"C{n(x)} {n(y + k)} {n(x + k)} {n(y)} {n(x + r)} {n(y)}Z"
    )


def rect_path(x, y, w, h):
    return poly_path([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])


def translate(d_list, dx, dy):
    """Wrap paths in a group transform (cheaper than re-emitting geometry)."""
    return f'<g transform="translate({n(dx)} {n(dy)})">' + "".join(d_list) + "</g>"
