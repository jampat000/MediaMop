"""The Weir mark, round four: the accepted render, traced and regularised (#581).

Where the numbers come from
---------------------------
`trace.py` thresholds source.png to two colours and least-squares fits a circle to every band
edge. Its output, which is the entire factual basis for this file:

    A_out     centre=(493.9, 521.0)  r=248.9  max residual 1.07px
    B_out     centre=(559.2, 556.4)  r=217.0  max residual 1.23px
    B_in      centre=(562.3, 537.1)  r=114.6  max residual 0.97px
    C_corner  centre=(575.3, 550.9)  r= 87.4  max residual 0.58px
    legs at row 600: (244,303) (343,446) (487,545)
    apron rows (692,751); tailrace bar rows (463,522)

Residuals under 1.3px on a 1024px render mean these really are circular arcs, not an arch drawn
freehand that happens to look round. That matters: the previous attempt at this mark redrew the
geometry by eye and produced a symmetric dome, because that is what an eye does with an arch.

What the trace says the mark is
-------------------------------
Three streams of water, each starting as a vertical leg on the left, turning clockwise over a
crest. The innermost turns a full quarter and runs off to the right as the tailrace. The other
two carry on over the top and are cut off by a horizontal line above the tailrace. Underneath,
an apron bar runs out to the left. That reading — leg, turn, tailrace, apron — is what makes it
read as water going over a weir rather than as an arch, and it is preserved exactly.

The two defects this file fixes (#581)
--------------------------------------
1. THE SLIVER. Inside the middle stream there is a tapering wedge in a third colour,
   rgb(29,136,127), roughly halfway between the accent and the background. A tray icon is a
   single-colour mask; a third tone there either vanishes or punches a hole. It is gone here:
   the middle stream is one flat shape.

2. UNEVEN BANDS. Measured at the leg line, where all three streams are parallel and vertical and
   the eye actually judges the rhythm, the source bands are 59, 103 and 58 units wide with dark
   gaps of 40 and 41. The middle one is nearly twice the others. The sliver turns out to mark
   where it should have been: the sliver's centre (x=393) sits within 2px of the midpoint of the
   band you get by laying three equal bands with equal gaps across the same span
   (244-304 | 364-425 | 485-545). So the regularisation is not invention, it is the artwork's own
   ladder with the fat band pulled back to its centreline.

Regularising the widths forces one more decision. The traced circles are not concentric: each
stream turns about a centre further right than the last, which is why the gap between the outer
two pinches shut near the crest and why the two of them fuse into one blob in the source. Equal
gaps are only possible for concentric arcs, so these are concentric. The pivot is the compromise
that keeps all four of the trace's hard landmarks within ~25px of 1024: the outer arc's left
extent and crest, and the inner elbow's leg and tailrace bar. Losing the pinch is a gain anyway —
it is the first thing that fuses at 16px.

Grid
----
24-unit viewBox, 20-unit live area, same as rounds two and three so the marks stay comparable.
Everything is one module `W` wide with one `G` gap, and every other number is derived from the
pivot and the radius ladder rather than typed in. The mark occupies x 2.10..21.89, y 4.05..19.95.

Three paths. All fills, no strokes: at 16px a stroke and a fill rasterise differently and only
the fill is predictable (round three learned this the hard way).
"""

from __future__ import annotations

import math

import geom

# --------------------------------------------------------------------------- #
# palette — the live Theme A "Tailrace" tokens from apps/web/src/styles/weir-tokens.css
# --------------------------------------------------------------------------- #
# The source render is #2ed6b2, which is close to the token but not it. The token wins: the mark
# has to sit next to accent-coloured UI, and two greens one step apart look like a mistake.
DARK = dict(surface="#0b1418", fg="#e8f1f4", accent="#3ed7c8")
LIGHT = dict(surface="#eaf0f2", fg="#11242b", accent="#0d6f68")


def pal(theme: str, mono: bool = False) -> dict:
    p = dict(DARK if theme == "dark" else LIGHT)
    if mono:
        # The tray-icon case: one colour, no accent to carry the shape.
        p = dict(p, accent=p["fg"])
    return p


# --------------------------------------------------------------------------- #
# the grid
# --------------------------------------------------------------------------- #
W = 1.85          # band width  (traced 59/1024, the module the apron and tailrace bar share)
G = 1.55          # gap         (traced 49/1024 after regularising; 0.84 * W)

# Radius ladder, inside out. C is the tailrace stream, B the middle, A the outer.
C_IN = 1.00
C_OUT = C_IN + W
B_IN = C_OUT + G
B_OUT = B_IN + W
A_IN = B_OUT + G
A_OUT = A_IN + W

# Pivot. Chosen so the mark lands centred in the 20-unit live area: see the derived extents
# asserted at the bottom of this file.
PX, PY = 13.30, 13.70

# Derived, never typed. Each of these is a structural relationship the trace found, not a
# measurement copied across, which is what keeps the mark self-consistent at any size.
CUT_Y = PY - B_IN               # horizontal cut across the two outer streams; tangent to B's crest
RACE_TOP = PY - C_OUT           # tailrace bar, one gap below the cut
RACE_BOT = PY - C_IN
RACE_RIGHT = PX + math.sqrt(A_OUT**2 - B_IN**2)   # where the outer stream meets the cut: the
                                                  # tailrace ends flush with the outer stream's tip
APRON_TOP = PY + B_IN           # the apron is the middle stream's ring continued out to the left
APRON_BOT = PY + B_OUT
APRON_LEFT = PX - A_OUT - G     # overhangs the outer leg by one gap, as the source does
LEG_BOT = APRON_TOP - G         # outer and middle legs stop one gap above the apron
LIVE_LEFT, LIVE_RIGHT = APRON_LEFT, RACE_RIGHT
LIVE_TOP, LIVE_BOT = PY - A_OUT, APRON_BOT


def _on(r: float, alpha_deg: float):
    return geom.on_circle((PX, PY), r, alpha_deg)


def _cut_angle(r: float) -> float:
    """Angle (clockwise from +x, our convention) at which a circle of radius r crosses CUT_Y.

    Negative, i.e. above the 3 o'clock line. B_IN is tangent to the cut, so it returns -90.
    """
    return -math.degrees(math.asin(min(1.0, (PY - CUT_Y) / r)))


def _stream(r_out: float, r_in: float) -> str:
    """One of the two outer streams: vertical leg, arc over the crest, flat cut at the tip.

    Traversed leg-outer-bottom -> up -> over the crest on the outer radius -> across the cut ->
    back along the inner radius -> down the leg. One closed subpath, no self-intersection.
    """
    a_out, a_in = _cut_angle(r_out), _cut_angle(r_in)
    p_out = _on(r_out, a_out)
    p_in = _on(r_in, a_in)
    return (
        f"M{geom.n(PX - r_out)} {geom.n(LEG_BOT)}"
        f"L{geom.n(PX - r_out)} {geom.n(PY)}"
        + geom.arc_to(p_out, r_out, 180.0, 360.0 + a_out)
        + "L" + geom.pt(p_in)
        + geom.arc_to(_on(r_in, 180.0), r_in, 360.0 + a_in, 180.0)
        + f"L{geom.n(PX - r_in)} {geom.n(LEG_BOT)}Z"
    )


def _tailrace() -> str:
    """The inner stream, its quarter turn, the tailrace bar and the apron, as one outline.

    They are one shape in the source too — the inner leg runs straight down through the gap and
    into the apron — and keeping it one path is what stops a hairline seam appearing along the
    shared edge at fractional raster sizes.
    """
    return (
        f"M{geom.n(PX - C_OUT)} {geom.n(PY)}"
        f"L{geom.n(PX - C_OUT)} {geom.n(APRON_TOP)}"
        f"L{geom.n(APRON_LEFT)} {geom.n(APRON_TOP)}"
        f"L{geom.n(APRON_LEFT)} {geom.n(APRON_BOT)}"
        f"L{geom.n(PX - C_IN)} {geom.n(APRON_BOT)}"
        f"L{geom.n(PX - C_IN)} {geom.n(PY)}"
        + geom.arc_to(_on(C_IN, 270.0), C_IN, 180.0, 270.0)
        + f"L{geom.n(RACE_RIGHT)} {geom.n(RACE_BOT)}"
        f"L{geom.n(RACE_RIGHT)} {geom.n(RACE_TOP)}"
        f"L{geom.n(PX)} {geom.n(RACE_TOP)}"
        + geom.arc_to(_on(C_OUT, 180.0), C_OUT, 270.0, 180.0)
        + "Z"
    )


#: Outermost stream first. `paths(3)` is the mark exactly as traced, matching the Midjourney
#: render James picked. `paths(2)` drops the middle band. See SHIPPED_STREAMS below for which one
#: `paths()`'s default now returns, and why that is no longer the same question for every size.
_ALL = [_stream(A_OUT, A_IN), _stream(B_OUT, B_IN), _tailrace()]

#: THE OPTICAL-SIZE SPLIT (#582, reopened by James after that PR shipped).
#:
#: #582 shipped two streams everywhere, because three do not survive 16px: at a 24 viewBox
#: rendered into 16 device pixels a unit is 0.667px, so a 1.85-unit band is 1.23px and a 1.55-unit
#: gap is 1.03px — three bands and two gaps have to land inside 7.8px. gate-16px.png shows the
#: real rasters at 9x, and the three-stream row is a grey smear across the crest in all of dark,
#: light and single colour there — you cannot count the arcs, which is the one thing this mark is.
#: No amount of tuning fixes that; the bands are sub-pixel by construction at 16px.
#:
#: But James looked at the two-stream mark shipped by #582 and asked for the three-stream original
#: back — the version traced straight off his accepted Midjourney render, before the 16px argument
#: trimmed a band out of it. He is right that it is a better logo: the two-stream mark is a
#: simplification made for one hostile size, applied everywhere, including the 512px marketing
#: mark and the in-app sidebar where there was never a legibility problem to solve.
#:
#: The fix is an optical-size split, standard type-design practice (the same reason a typeface
#: ships separate "text" and "display" masters): use the size where the trade-off actually bites,
#: not the mark's identity, as the thing that changes. `paths()`'s default is now three streams —
#: the primary mark, used everywhere it is seen large enough to read: packaging/brand/*.svg, the
#: web favicon.svg, the app icon, the in-app logo, the docs logo, every 512/256/128/64 raster.
#: Two streams survive only as the small-size fallback, generated from `paths(2)` and used
#: nowhere except the 16px (and, per the 32px check below, also 32px) frames of the .ico files —
#: see scripts/generate-brand-icons.py. It is still the same recorded geometry either way: no path
#: here changed, only which one is the default and where each is used.
#:
#: 32px check: at 32 a unit is 1.333px, so bands are 2.47px and gaps 2.07px — wide enough that you
#: can count three arcs, unlike at 16, but the crest is where the two outer arcs run closest
#: together and anti-aliasing still softens that corner, most visibly in the single-colour (tray)
#: rendering that is the actual use of the .ico's 32px frame. Two streams stay crisp at the same
#: size with a clear gap at the crest. So 32px keeps the two-stream fallback too; only 48px and
#: above switch to three. See packaging/brand/README.md for the full table.
#:
#: The middle stream is still the right one to drop at small sizes: it carries no structure of its
#: own. The outer stream is the crest and the whole silhouette; the inner stream is the tailrace
#: and the apron, which is what stops the mark reading as a plain arch. The middle one is a repeat
#: of the outer, which is exactly why removing it is a size accommodation and not a redesign.
SHIPPED_STREAMS = 3

#: The small-size fallback used only inside .ico frames (16px, and 32px per the check above).
SMALL_STREAMS = 2


def paths(streams: int = SHIPPED_STREAMS) -> list[str]:
    """Path data for the mark. `streams` is 3 (the primary mark) or 2 (small-size .ico fallback)."""
    if streams == 3:
        return list(_ALL)
    if streams == 2:
        return [_ALL[0], _ALL[2]]
    raise ValueError("streams must be 2 or 3")


def body(p: dict, streams: int = SHIPPED_STREAMS) -> str:
    """The mark's markup, no <svg> wrapper, in one flat colour."""
    return "".join(f'<path d="{d}" fill="{p["accent"]}"/>' for d in paths(streams))


def svg(theme: str = "dark", mono: bool = False, streams: int = SHIPPED_STREAMS,
        surface: str | None = None) -> str:
    p = pal(theme, mono)
    rect = f'<rect width="24" height="24" fill="{surface}"/>' if surface else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            + rect + body(p, streams) + "</svg>")


# The live-area contract, checked rather than commented: if a radius or the pivot is edited, this
# is what says so instead of a subtly off-centre icon shipping.
assert 2.0 <= LIVE_LEFT and LIVE_RIGHT <= 22.0, (LIVE_LEFT, LIVE_RIGHT)
assert 2.0 <= LIVE_TOP and LIVE_BOT <= 22.0, (LIVE_TOP, LIVE_BOT)
assert abs((LIVE_LEFT - 0) - (24 - LIVE_RIGHT)) < 0.35, "mark is not horizontally centred"
assert abs((LIVE_TOP - 0) - (24 - LIVE_BOT)) < 0.35, "mark is not vertically centred"

if __name__ == "__main__":
    print(f"live area x {LIVE_LEFT:.2f}..{LIVE_RIGHT:.2f}  y {LIVE_TOP:.2f}..{LIVE_BOT:.2f}")
    for i, d in enumerate(paths()):
        print(i, d)
