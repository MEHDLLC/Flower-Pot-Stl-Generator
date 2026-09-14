"""Moss pole: a hollow column you pack with sphagnum, in stacking segments.

An aroid climbs by putting aerial roots into something damp.  A moss pole
is the something: a tube, open enough that the roots can get through the
wall and into the moss, tall enough to be worth climbing, and therefore
much taller than any build plate.  So it comes in segments.

The three parts
---------------
* **segment** - one tube with the fill pattern through its wall.  Print
  ``pole_segments`` of them; they are identical, which is the whole point
  of a segment.
* **base** - a wide foot with a socket on top.  It goes in the pot under
  the soil and stops the column from sinking or leaning.
* **cap** - a funnel that drops on the top.  It closes the column so the
  moss stays in, and it is where you pour: water runs down the packed moss
  instead of off the outside.

The joint
---------
A **spigot**: the top of each segment steps in to slip inside the mouth of
the next, and the step it leaves is a flat annulus facing straight up -
which is what the segment above lands on, so the stack has an exact pitch.
Both surfaces are vertical, so both print as walls.

The bore has to neck in by a wall plus the fit to get inside the segment
above, and a bore that narrows going up is a ceiling, so the neck is coned
at the overhang budget rather than stepped.

For a square or hexagonal pole the spigot is the same polygon as the tube,
which keys the joint: segments can only go together one way round, the
pattern lines up, and nothing twists once it is loaded.

The pattern
-----------
Every opening is a **pointed prism** - a rectangle with a gabled top and a
V-shaped bottom, cut straight through the wall.  A plain rectangular slot
through a standing tube has a flat ceiling across the top of it; put a
gable on that ceiling and the same opening prints with nothing under it.
The gable's slope is the overhang budget, so the openings are as wide as
the budget allows and no wider.

* ``lattice`` - short diamonds in a staggered grid, the classic moss-pole
  look and the most open wall for the least loss of stiffness.
* ``slots``   - the same openings with a straight waist let into them:
  fewer, taller windows, easier to pack and more open, but less edge for a
  root to hook on to.
* ``solid``   - no openings at all, for a plain climbing stake.

``pole_open`` is how much of the wall goes away.  What stops it going to 1
is the strut left between openings: below about two extrusions wide the
wall stops being a wall, so the generator says no with the number it
wanted.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _finish, _prism, lathe
from .params import ParameterError, PotParams
from .profile import slope_budget
from .sections import Section, make_section

SHAPES = {"square": ("square", 4), "hex": ("hexagonal", 6),
          "round": ("classic_tapered", 1)}
PATTERNS = ("lattice", "slots", "solid")

_RESERVE = 0.08          # held back from tan(limit)
_JOINT = 0.22            # spigot height, as a fraction of the segment
_JOINT_MAX = 28.0        # ... but this many mm is plenty
_FIT = 0.35              # perpendicular slip fit, spigot into mouth
_STRUT_MIN = 2.0         # narrowest wall left between two openings
_MARGIN = 4.0            # solid band at the ends of a segment's pattern

_FOOT_SPREAD = 1.9       # base plate, in pole widths across the flats
_FOOT_HOLES = 6
_FUNNEL_MOUTH = 1.6      # cap mouth, in pole diameters
_CAP_COLLAR = 10.0       # straight socket under the funnel


# ---------------------------------------------------------------------------
# sizing
# ---------------------------------------------------------------------------
def pole_section(p: PotParams) -> Section:
    """The pole's cross-section.  Re-uses the pot sections, so a square
    pole is the same rounded square the square pot is cut from."""
    style, sides = SHAPES[p.pole_shape]
    return make_section(p.with_(pot_style=style, hex_sides=sides,
                                hex_corner_round=corner_round(p),
                                surface_texture="none"))


def wall_of(p: PotParams) -> float:
    return max(2.4, p.wall_thickness)


def corner_round(p: PotParams) -> float:
    return max(2.0, 0.11 * 0.5 * float(p.pole_diameter))


def circumradius(p: PotParams) -> float:
    """``pole_diameter`` is the width **across the flats** - the number a
    ruler gives you, and the number a shop pole is sold by.  The sections
    are cut from the corner-to-corner radius instead, so convert.

    With rounded corners the flat sits at ``r cos(h) + q (1 - cos(h))`` from
    the centre, where ``h`` is half a facet; invert that.
    """
    w = 0.5 * float(p.pole_diameter)
    n = SHAPES[p.pole_shape][1]
    if n <= 2:
        return w
    h = math.cos(math.pi / n)
    q = corner_round(p)
    return (w - q * (1.0 - h)) / h


def across_flats(p: PotParams, r: float) -> float:
    """A circumradius, back in ruler units."""
    n = SHAPES[p.pole_shape][1]
    if n <= 2:
        return 2.0 * r
    h = math.cos(math.pi / n)
    return 2.0 * (r * h + corner_round(p) * (1.0 - h))


def plan(p: PotParams) -> dict:
    """Every number the three parts are cut from."""
    if p.pole_shape not in SHAPES:
        raise ParameterError(
            f"unknown pole_shape {p.pole_shape!r}; choose from "
            f"{sorted(SHAPES)}")
    if p.pole_pattern not in PATTERNS:
        raise ParameterError(
            f"unknown pole_pattern {p.pole_pattern!r}; choose from "
            f"{list(PATTERNS)}")

    s = slope_budget(p, _RESERVE)
    t = wall_of(p)
    r = circumradius(p)
    h = float(p.pole_segment_height)
    n = max(1, int(p.pole_segments))
    sec = pole_section(p)
    f = sec.inner_offset_factor              # corner-to-flat, for a polygon
    sides = sec.n if hasattr(sec, "n") else 1

    if float(p.pole_diameter) < 30.0:
        raise ParameterError(
            "pole_diameter should be at least 30 mm - under that there is no "
            "bore left to pack moss into once the wall and the joint have "
            "had their share")
    r_bore = r - t * f
    r_spig = r - (t + _FIT) * f              # outside of the spigot
    r_neck = r_spig - t * f                  # ... and its bore
    if across_flats(p, r_neck) < 16.0:
        raise ParameterError(
            f"a {p.pole_diameter:.0f} mm pole with {t:.1f} mm walls necks down "
            f"to {across_flats(p, r_neck):.0f} mm at the joint - widen "
            f"pole_diameter or "
            f"thin wall_thickness")

    joint = min(_JOINT * h, _JOINT_MAX)
    neck = (t + _FIT) * f / s                # coned, not stepped: see above
    # the joint is a fixed share of the segment, so a short segment is not a
    # short pole - it is mostly spigot
    need = 24.0 / (1.0 - _JOINT)
    if h < need:
        raise ParameterError(
            f"pole_segment_height {h:.0f} mm is mostly joint: {joint:.0f} mm "
            f"of it is spigot, and what is left is not worth packing - give a "
            f"segment at least {need:.0f} mm")

    return dict(s=s, wall=t, r=r, r_bore=r_bore, r_spig=r_spig, r_neck=r_neck,
                h=h, n=n, joint=joint, neck=neck, f=f, sides=sides,
                pitch=h - joint,             # what one more segment buys you
                height=n * (h - joint) + joint)


def assembled_height(p: PotParams) -> float:
    """Plate to the top of the last spigot, before the cap goes on."""
    return plan(p)["height"]


def face_width(k: dict) -> float:
    """Width of one flat face, or of a sixth of a round pole."""
    if k["sides"] <= 2:
        return 2.0 * math.pi * k["r"] / 6.0
    return 2.0 * k["r"] * math.sin(math.pi / k["sides"])


def perimeter(p: PotParams) -> float:
    """Once round the outside, measured off the section itself - a rounded
    square is neither four faces nor a circle, and the openings are laid
    out along it."""
    k = plan(p)
    sec = pole_section(p)
    theta = np.linspace(0.0, 2.0 * math.pi, 360, endpoint=False)
    x, y = sec.xy(theta, 0.0, k["r"], decorate=False)
    return float(np.hypot(np.diff(x, append=x[0]),
                          np.diff(y, append=y[0])).sum())


def pattern_grid(p: PotParams) -> dict | None:
    """Where the openings go: columns round the pole, rows up it.

    Columns are a whole number per face, so an opening never lands on a
    corner - the corner is the stiffest part of the section and the part
    you tie a stem to.  The cell they sit in is sized in millimetres rather
    than as a fraction of the pole, because what has to be big enough is a
    root and a finger, and neither scales with the pole.

    ``pole_open`` then splits each cell between opening and strut, and the
    rows are pitched so the strut between two rows matches the one beside
    them: the wall left behind is an even lattice, not bars.
    """
    if p.pole_pattern == "solid":
        return None
    k = plan(p)
    tall = p.pole_pattern == "slots"
    ring = perimeter(p)

    cell_target = max(14.0, 0.34 * 2.0 * k["r"])
    if k["sides"] > 2:
        per_face = max(1, int(round(face_width(k) / cell_target)))
        cols = k["sides"] * per_face
    else:
        cols = max(6, int(round(ring / cell_target)))

    cell = ring / cols
    open_frac = float(np.clip(p.pole_open, 0.05, 0.95))
    half = 0.5 * open_frac * cell
    strut = cell - 2.0 * half
    if strut < _STRUT_MIN:
        raise ParameterError(
            f"pole_open {p.pole_open:.2f} leaves {strut:.1f} mm of wall "
            f"between openings, which is not a wall - keep it under "
            f"{1.0 - _STRUT_MIN / cell:.2f} on a {p.pole_diameter:.0f} mm "
            f"{p.pole_shape} pole")

    # gable the roof at the budget, and the same on the sill, so the opening
    # reads as one shape rather than a slot wearing a hat
    up = half / k["s"]
    span = k["h"] - k["joint"] - 2.0 * _MARGIN
    if span < 20.0:
        raise ParameterError(
            "there is no wall left to open up between the ends of this "
            "segment and its joint - lengthen pole_segment_height")

    # a slot is the same opening with a straight waist let into it
    body = 2.2 * (2.0 * half) if tall else 0.0
    want = body + 2.0 * up + strut                 # one row, plus its strut
    rows = int(p.pole_rows) if int(p.pole_rows) > 0 else max(
        1, int(span // want))
    pitch = span / rows
    if pitch < body + 2.0 * up + _STRUT_MIN:
        raise ParameterError(
            f"{rows} rows of {body + 2.0 * up:.0f} mm openings do not fit in "
            f"the {span:.0f} mm this segment has to give - lower pole_rows, "
            f"or lengthen pole_segment_height")
    return dict(cols=cols, rows=rows, pitch=pitch, half=half, up=up,
                body=body, strut=strut, cell=cell,
                z0=_MARGIN + 0.5 * pitch)


def open_area_fraction(p: PotParams) -> float:
    """Roughly how much of the wall is opening rather than wall."""
    g = pattern_grid(p)
    if g is None:
        return 0.0
    k = plan(p)
    one = 2.0 * g["half"] * (g["body"] + g["up"])      # a body + two gables
    wall = perimeter(p) * k["h"]
    return min(g["cols"] * g["rows"] * one / wall, 1.0)


def check_mosspole(p: PotParams) -> list[str]:
    out: list[str] = []
    if p.moss_pole not in ("none", "set", "segment", "base", "cap"):
        raise ParameterError(
            f"unknown moss_pole {p.moss_pole!r}; choose from "
            f"['set', 'segment', 'base', 'cap']")
    if p.moss_pole == "none":
        return out
    if not 1 <= int(p.pole_segments) <= 12:
        raise ParameterError("pole_segments should be 1-12")
    if int(p.pole_rows) < 0:
        raise ParameterError("pole_rows cannot be negative (0 = auto)")
    k = plan(p)
    pattern_grid(p)                          # raises on an impossible pattern
    out.append(
        f"{k['n']} segments give a {k['height'] / 10.0:.0f} cm column - each "
        f"joint swallows {k['joint']:.0f} mm of the segment above it, so a "
        f"segment buys {k['pitch']:.0f} mm and not {k['h']:.0f}")
    if p.pole_pattern != "solid":
        out.append(
            f"about {100.0 * open_area_fraction(p):.0f}% of the wall is "
            f"opening, on a {pattern_grid(p)['strut']:.1f} mm strut - pack it "
            f"with damp sphagnum before you stand it up, not after")
    if p.printer != "none":
        from .printers import PRINTERS
        bed_h = PRINTERS[p.printer]["height"]
        if k["h"] > bed_h:
            out.append(
                f"a {k['h']:.0f} mm segment does not stand up on a "
                f"{bed_h:.0f} mm machine - lower pole_segment_height and "
                f"raise pole_segments")
    return out


# ---------------------------------------------------------------------------
# the openings
# ---------------------------------------------------------------------------
def _pointed_port(x0: float, x1: float, z0: float, z1: float,
                  half: float, up: float) -> trimesh.Trimesh:
    """A rectangle with a gable on top and a V underneath, run along X.

    ``z0``/``z1`` are the straight part; at ``z1 == z0`` it collapses to a
    diamond.  The roof is the only face a printer cares about, and its lean
    from vertical is ``atan(half / up)``.
    """
    if z1 - z0 <= 1e-6:                       # no waist: a plain diamond,
        profile = [(0.0, z0 - up), (half, z0),  # and never a repeated vertex,
                   (0.0, z0 + up), (-half, z0)]  # which is not a solid
    else:
        profile = [(0.0, z0 - up), (half, z0), (half, z1),
                   (0.0, z1 + up), (-half, z1), (-half, z0)]
    return _prism(profile, x0, x1)


def _pattern_cutters(p: PotParams) -> list[trimesh.Trimesh]:
    g = pattern_grid(p)
    if g is None:
        return []
    k = plan(p)
    reach = k["r"] + 6.0
    out = []
    for row in range(g["rows"]):
        z = g["z0"] + row * g["pitch"]
        # every other row steps round by half a column: a staggered grid
        # keeps a continuous strut running up the pole instead of lining the
        # openings up into one long slit
        turn = 0.5 if (row % 2 and p.pole_pattern == "lattice") else 0.0
        for col in range(g["cols"]):
            a = 2.0 * math.pi * (col + turn) / g["cols"]
            port = _pointed_port(x0=-1.0, x1=reach, z0=z - 0.5 * g["body"],
                                 z1=z + 0.5 * g["body"], half=g["half"],
                                 up=g["up"])
            port.apply_transform(
                trimesh.transformations.rotation_matrix(a, [0, 0, 1]))
            out.append(port)
    return out


# ---------------------------------------------------------------------------
# the segment
# ---------------------------------------------------------------------------
def segment_rings(p: PotParams) -> list[tuple[float, float]]:
    """Outside of one segment: a tube that steps in to a spigot on top."""
    k = plan(p)
    shoulder = k["h"] - k["joint"]
    return [(k["r"], 0.0), (k["r"], shoulder),
            (k["r_spig"], shoulder),          # the seat, facing straight up
            (k["r_spig"], k["h"])]


def segment_bore_rings(p: PotParams) -> list[tuple[float, float]]:
    """The bore, necking in under the spigot at the overhang budget."""
    k = plan(p)
    shoulder = k["h"] - k["joint"]
    return [(k["r_bore"], -2.0),
            (k["r_bore"], shoulder - k["neck"]),
            (k["r_neck"], shoulder),
            (k["r_neck"], k["h"] + 2.0)]


def build_pole_segment(p: PotParams) -> trimesh.Trimesh:
    """One segment: prints standing on its own footprint, no supports."""
    check_mosspole(p)
    sec = pole_section(p)
    body = lathe(segment_rings(p), sec, decorate=False)
    body = _boolean("difference",
                    [body, lathe(segment_bore_rings(p), sec, decorate=False)])
    cutters = _pattern_cutters(p)
    if cutters:
        body = _boolean("difference", [body] + cutters)
    return _finish(body, center=False)


# ---------------------------------------------------------------------------
# the base
# ---------------------------------------------------------------------------
def build_pole_base(p: PotParams) -> trimesh.Trimesh:
    """A wide foot with a socket on top.

    It buries in the pot: the plate spreads the load so the column does not
    sink, and it is pierced so water and roots are not asked to go round
    it.  The socket is the segment's own spigot, so the first segment sits
    in the base exactly the way every other one sits in the one below.
    """
    check_mosspole(p)
    k = plan(p)
    sec = pole_section(p)
    # wide enough to spread the load, and never so close to the collar
    # that the drainage ring has nowhere to go
    plate_r = max(_FOOT_SPREAD * 0.5 * float(p.pole_diameter), k["r"] + 14.0)
    floor = max(4.0, p.base_thickness)
    rise = floor + k["joint"]

    # the plate is round whatever the pole is: it wants area, not corners
    round_sec = Section(p.with_(pot_style="classic_tapered",
                                surface_texture="none"))
    plate = lathe([(plate_r, 0.0), (plate_r, floor - 1.2),
                   (plate_r - 1.2, floor)], round_sec, decorate=False)
    collar = lathe([(k["r"], 0.0), (k["r"], rise - k["joint"]),
                    (k["r_spig"], rise - k["joint"]), (k["r_spig"], rise)],
                   sec, decorate=False)
    body = _boolean("union", [plate, collar])
    # the socket bore stops short of the plate, so the column stands on
    # something solid rather than on the moss below it
    body = _boolean("difference", [body, lathe(
        [(k["r_neck"], floor), (k["r_neck"], rise + 2.0)], sec,
        decorate=False)])

    # the holes live in the annulus between the collar's corners and the
    # plate's edge, so they stay holes instead of breaking out into notches
    inner, outer = k["r"] + 2.0, plate_r - 2.5
    holes = []
    ring = 0.5 * (inner + outer)
    for i in range(_FOOT_HOLES):
        a = 2.0 * math.pi * (i + 0.5) / _FOOT_HOLES
        hole = trimesh.creation.cylinder(radius=0.40 * (outer - inner),
                                         height=40.0, sections=32)
        hole.apply_translation((ring * math.cos(a), ring * math.sin(a), 0.0))
        holes.append(hole)
    return _finish(_boolean("difference", [body] + holes), center=False)


# ---------------------------------------------------------------------------
# the cap
# ---------------------------------------------------------------------------
def build_pole_cap(p: PotParams) -> trimesh.Trimesh:
    """A funnel that drops onto the top spigot.

    Printed mouth up it is all flare and no ceiling: the bore opens
    outwards the whole way, and the outside follows it at the same slope,
    which is the budget.  Pour into it and the water goes down the moss.
    """
    check_mosspole(p)
    k = plan(p)
    sec = pole_section(p)
    t = k["wall"]
    mouth = _FUNNEL_MOUTH * k["r"]
    flare = (mouth - k["r"]) / k["s"]                  # at the budget exactly
    top = _CAP_COLLAR + flare

    body = lathe([(k["r"], 0.0), (k["r"], _CAP_COLLAR), (mouth, top)],
                 sec, decorate=False)
    # the bore: the socket the spigot goes into, then the funnel, carried
    # past the mouth so the lip reads as an edge instead of a shelf
    bore = lathe([(k["r_bore"], -2.0), (k["r_bore"], _CAP_COLLAR),
                  (mouth - t * k["f"] + k["s"] * 2.0, top + 2.0)],
                 sec, decorate=False)
    return _finish(_boolean("difference", [body, bore]), center=False)


# ---------------------------------------------------------------------------
# how they go together
# ---------------------------------------------------------------------------
def stacked(p: PotParams, n: int | None = None) -> trimesh.Trimesh:
    """Base, ``n`` segments and the cap, in their assembled places."""
    k = plan(p)
    n = k["n"] if n is None else n
    base = build_pole_base(p)
    z = base.bounds[1][2] - k["joint"]
    parts = [base]
    seg = build_pole_segment(p)
    for _ in range(n):
        one = seg.copy()
        one.apply_translation((0.0, 0.0, z))
        parts.append(one)
        z += k["pitch"]
    cap = build_pole_cap(p)
    cap.apply_translation((0.0, 0.0, z))
    parts.append(cap)
    return trimesh.util.concatenate(parts)
