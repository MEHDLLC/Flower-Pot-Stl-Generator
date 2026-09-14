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

from .build import _boolean, _diamond_port, _finish, _prism, lathe
from .params import ParameterError, PotParams
from .profile import slope_budget
from .sections import Section, make_section

SHAPES = {"square": ("square", 4), "hex": ("hexagonal", 6),
          "round": ("classic_tapered", 1)}
PATTERNS = ("lattice", "slots", "solid")
BARBS = ("none", "inside", "outside", "both")

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
_CAP_EYE_CLEAR = 8.0     # wick eyes sit this far above the spigot's top

_SUMP_FREE = 6.0         # air between the water line and the bore's neck
_SUMP_MIN = 8.0          # shallower than this is a puddle, not a sump
_SUMP_MAX = 140.0
_OVERFLOW_W = 3.5        # half width of the port that sets the water line
_PILLAR_R = 5.0          # the post the wick loops under
_EYE_W = 2.4             # half width of the eyes the wick threads through

_BARB_REACH = 1.4        # barb protrusion, in wall thicknesses
_BARB_CAP = 0.09         # ... and never more than this of the pole
_BARB_HALF = 0.35        # barb half width, as a fraction of the strut


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

    floor = max(4.0, p.base_thickness)
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

    sump = max(0.0, float(p.pole_reservoir))
    if sump and not _SUMP_MIN <= sump <= _SUMP_MAX:
        raise ParameterError(
            f"pole_reservoir should be {_SUMP_MIN:.0f}-{_SUMP_MAX:.0f} mm of "
            f"water, or 0 for a foot that drains instead of holding")
    # the base is the plate, then the water, then air, then the bore's neck,
    # then the spigot the first segment lands on
    base_rise = floor + (sump + _SUMP_FREE if sump else 0.0) + neck + joint

    return dict(s=s, wall=t, r=r, r_bore=r_bore, r_spig=r_spig, r_neck=r_neck,
                h=h, n=n, joint=joint, neck=neck, f=f, sides=sides,
                floor=floor, sump=sump, base_rise=base_rise,
                pitch=h - joint,             # what one more segment buys you
                height=n * (h - joint) + joint)


def section_area(p: PotParams, radius: float) -> float:
    """Area enclosed by the section at ``radius`` - a rounded square is
    neither a square nor a circle, so measure it rather than assume."""
    sec = pole_section(p)
    theta = np.linspace(0.0, 2.0 * math.pi, 720, endpoint=False)
    x, y = sec.xy(theta, 0.0, radius, decorate=False)
    return float(0.5 * abs(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)))


def sump_millilitres(p: PotParams) -> float:
    """Water the closed base holds, less the wick post standing in it."""
    k = plan(p)
    if not k["sump"]:
        return 0.0
    gross = section_area(p, k["r_bore"]) * k["sump"]
    post = math.pi * _PILLAR_R ** 2 * k["sump"] if p.pole_wick else 0.0
    return max(gross - post, 0.0) / 1000.0


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

    cell_target = max(14.0, 0.34 * float(p.pole_diameter))
    if k["sides"] > 2:
        # an EVEN number of columns per face, so they straddle the face
        # centre instead of sitting on it: that leaves the centre of every
        # face solid, which is where the barbs go and where a corner never is
        per_face = max(2, 2 * int(round(face_width(k) / (2.0 * cell_target))))
        cols, phase = k["sides"] * per_face, 0.5
    else:
        cols, phase = max(6, int(round(ring / cell_target))), 0.0

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
                body=body, strut=strut, cell=cell, phase=phase,
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
    if p.pole_barbs not in BARBS:
        raise ParameterError(
            f"unknown pole_barbs {p.pole_barbs!r}; choose from {list(BARBS)}")
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
    if k["sump"]:
        out.append(
            f"the base holds about {sump_millilitres(p):.0f} ml under the "
            f"column, and an overflow sets the level - but it is a sump, not "
            f"a tank: a string lifts water about a hand's width, so this "
            f"feeds the bottom of the pole and the cap feeds the rest")
        if not p.pole_wick:
            out.append(
                "there is water under the column and nothing reaching down "
                "to it - set pole_wick and run a string, or the moss has to "
                "bridge the gap on its own")
    elif p.pole_wick:
        out.append(
            "pole_wick with no pole_reservoir leaves the string hanging out "
            "of the base into the pot's soil, which wicks too - set "
            "pole_reservoir if you would rather it drew from its own water")
    if p.pole_barbs in ("inside", "both"):
        reach, _rise, _half = barb_size(p)
        out.append(
            f"{reach:.1f} mm barbs inside the wall hold the packed column up "
            f"- they start above the socket at the bottom of a segment, "
            f"because down there the bore is full of the spigot below it")
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


def barb_grid(p: PotParams) -> dict | None:
    """Barbs sit on the lattice too - a solid pole borrows the lattice's
    grid without cutting it, so the two patterns never argue."""
    if p.pole_barbs == "none":
        return None
    return pattern_grid(p) or pattern_grid(p.with_(pole_pattern="lattice"))


def _barb(x_wall: float, reach: float, rise: float, half: float
          ) -> trimesh.Trimesh:
    """A little shelf with a ramped underside.

    Flat on top, because that is the face the moss rests on; and nothing
    underneath it steeper than the budget, because the ramp **is** the
    budget - ``rise = reach / s`` and the underside lands exactly on the
    limit.  ``reach`` is signed: negative points into the bore.
    """
    tip = x_wall + reach
    v = [(x_wall, -half, 0.0), (x_wall, half, 0.0),
         (x_wall, -half, rise), (x_wall, half, rise),
         (tip, -half, rise), (tip, half, rise)]
    faces = [[0, 3, 1], [0, 2, 3],        # the face buried in the wall
             [2, 4, 5], [2, 5, 3],        # the flat top
             [0, 1, 5], [0, 5, 4],        # the ramp underneath
             [0, 4, 2], [1, 3, 5]]        # the two ends
    m = trimesh.Trimesh(vertices=v, faces=faces, process=True)
    if not m.is_winding_consistent:
        m.fix_normals()
    if m.volume < 0:
        m.invert()
    return m


def barb_size(p: PotParams) -> tuple[float, float, float]:
    """(reach, rise, half width) of one barb."""
    k = plan(p)
    g = barb_grid(p)
    reach = min(_BARB_REACH * k["wall"], _BARB_CAP * float(p.pole_diameter))
    return reach, reach / k["s"], min(_BARB_HALF * g["strut"], 4.0)


def barb_sites(p: PotParams) -> list[tuple[float, float, bool]]:
    """``(height, azimuth, inward)`` for every barb.

    One per face, on the middle of the flat - never on a corner, where a
    flat-backed wedge would not sit, and never where an opening is about to
    be cut.  A staggered row moves its openings half a cell, so the barbs
    step half a cell with them and stay on the strut.
    """
    g = barb_grid(p)
    if g is None:
        return []
    k = plan(p)
    lattice = p.pole_pattern == "lattice"
    want_in = p.pole_barbs in ("inside", "both")
    want_out = p.pole_barbs in ("outside", "both")
    cell_angle = 2.0 * math.pi / g["cols"]
    sites = []
    for row in range(g["rows"]):
        z = g["z0"] + row * g["pitch"]
        turn = 0.5 if (row % 2 and lattice) else 0.0
        if k["sides"] > 2:
            azimuths = [2.0 * math.pi * j / k["sides"] + turn * cell_angle
                        for j in range(k["sides"])]
        else:
            azimuths = [cell_angle * (c + 0.5 + turn) for c in range(g["cols"])]
        # the bottom of a segment is a socket: down there the bore is full
        # of the spigot below it, so an inward barb would be interference
        # and not grip.  Outward ones have nothing to hit and carry on.
        inside_here = want_in and z >= k["joint"] + 1.0
        for a in azimuths:
            if inside_here:
                sites.append((z, a, True))
            if want_out:
                sites.append((z, a, False))
    return sites


def _barbs(p: PotParams) -> trimesh.Trimesh | None:
    """Nubs on the wall, at the crossings of the pattern.

    They are unioned on **before** the openings are cut, which means an
    opening always wins: a barb can never end up plugging one.

    Inside they stop the packed column settling away from the wall; outside
    they hold a sheet of moss you have wrapped round the pole while you get
    the twine on, and give roots something to sit against.
    """
    sites = barb_sites(p)
    if not sites:
        return None
    k = plan(p)
    sec = pole_section(p)
    reach, rise, half = barb_size(p)
    out = []
    for z, a, inward in sites:
        rot = trimesh.transformations.rotation_matrix(a, [0, 0, 1])
        radius = k["r_bore"] if inward else k["r"]
        x = float(sec.radius(np.array([a]), z, radius, False)[0])
        one = _barb(x + (0.6 if inward else -0.6),
                    -reach if inward else reach, rise, half)
        one.apply_translation((0.0, 0.0, z))
        one.apply_transform(rot)
        out.append(one)
    return trimesh.util.concatenate(out) if out else None


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
            a = 2.0 * math.pi * (col + g["phase"] + turn) / g["cols"]
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
    barbs = _barbs(p)
    if barbs is not None:
        body = _boolean("union", [body, barbs])
    cutters = _pattern_cutters(p)
    if cutters:
        body = _boolean("difference", [body] + cutters)
    return _finish(body, center=False)


# ---------------------------------------------------------------------------
# the base
# ---------------------------------------------------------------------------
def build_pole_base(p: PotParams) -> trimesh.Trimesh:
    """A wide foot with a socket on top - and, if you ask for one, a sump.

    It buries in the pot: the plate spreads the load so the column does not
    sink, and its flange is pierced so water and roots are not asked to go
    round it.  The socket is the segment's own spigot, so the first segment
    sits in the base the way every other one sits in the one below.

    With ``pole_reservoir`` set, the cup under that socket is deepened and
    holds water.  **It is a sump, not a tank.**  What fills it is what you
    pour through the cap and what the column does not hold; what empties it
    is the bottom of the moss, and a string if you fitted one.  A cotton
    wick lifts water about a hand's width before the flow stops being worth
    counting, so this feeds the bottom of the pole and the cap feeds the
    rest.  An overflow through the wall sets the level, and what goes over
    it waters the pot, which is where it was going anyway.
    """
    check_mosspole(p)
    k = plan(p)
    sec = pole_section(p)
    # wide enough to spread the load, and never so close to the collar
    # that the drainage ring has nowhere to go
    plate_r = max(_FOOT_SPREAD * 0.5 * float(p.pole_diameter), k["r"] + 14.0)
    floor, rise = k["floor"], k["base_rise"]
    shoulder = rise - k["joint"]

    # the plate is round whatever the pole is: it wants area, not corners
    round_sec = Section(p.with_(pot_style="classic_tapered",
                                surface_texture="none"))
    plate = lathe([(plate_r, 0.0), (plate_r, floor - 1.2),
                   (plate_r - 1.2, floor)], round_sec, decorate=False)
    collar = lathe([(k["r"], 0.0), (k["r"], shoulder),
                    (k["r_spig"], shoulder), (k["r_spig"], rise)],
                   sec, decorate=False)
    body = _boolean("union", [plate, collar])

    # the cup: the segment's own bore, closed at the plate.  With no sump
    # asked for there is no cup to speak of and the bore is all neck - the
    # cone still gets its full height, because shortening it is what would
    # tip it past the budget
    z_neck = max(shoulder - k["neck"], floor)
    body = _boolean("difference", [body, lathe(
        [(k["r_bore"], floor), (k["r_bore"], z_neck),
         (k["r_neck"], shoulder), (k["r_neck"], rise + 2.0)],
        sec, decorate=False)])

    post_top = floor + max(k["sump"], 10.0) + 4.0
    if p.pole_wick:
        # the post the wick loops under, so the string can be pulled taut
        # down the middle of the column instead of lying against the wall.
        # It goes on *after* the cup is bored, or the bore takes it with it
        post = trimesh.creation.cylinder(radius=_PILLAR_R,
                                         height=post_top - floor, sections=32)
        post.apply_translation((0.0, 0.0, 0.5 * (post_top + floor)))
        body = _boolean("union", [body, post])

    cutters = []
    if p.pole_wick:
        cutters.append(_diamond_port(
            x0=-1.5 * _PILLAR_R, x1=1.5 * _PILLAR_R,
            z_center=post_top - 4.0,
            half_w=2.0, up=2.0 / k["s"], down=1.8))
    if k["sump"]:
        # a diamond, not a round hole: a round hole through a standing wall
        # has a ceiling straight across the top of it.  Started clear of the
        # post so it cuts the wall and not the anchor.
        cutters.append(_diamond_port(
            x0=1.6 * _PILLAR_R, x1=k["r"] + 8.0, z_center=floor + k["sump"],
            half_w=_OVERFLOW_W, up=_OVERFLOW_W / k["s"],
            down=0.9 * _OVERFLOW_W))

    # the flange holes live in the annulus between the collar's corners and
    # the plate's edge, so they stay holes instead of breaking out into
    # notches - and being outside the collar, they never drain the cup
    inner, outer = k["r"] + 2.0, plate_r - 2.5
    ring = 0.5 * (inner + outer)
    for i in range(_FOOT_HOLES):
        a = 2.0 * math.pi * (i + 0.5) / _FOOT_HOLES
        hole = trimesh.creation.cylinder(radius=0.40 * (outer - inner),
                                         height=40.0, sections=32)
        hole.apply_translation((ring * math.cos(a), ring * math.sin(a), 0.0))
        cutters.append(hole)
    return _finish(_boolean("difference", [body] + cutters), center=False)


# ---------------------------------------------------------------------------
# the cap
# ---------------------------------------------------------------------------
def cap_plan(p: PotParams) -> dict:
    """The funnel's numbers.

    A cap that carries the wick eyes needs a collar long enough to put them
    **above** the spigot buried in its socket - otherwise the eye opens into
    the half-millimetre gap round the spigot, where no string will go.
    """
    k = plan(p)
    mouth = _FUNNEL_MOUTH * k["r"]
    flare = (mouth - k["r"]) / k["s"]                  # at the budget exactly
    collar = (max(_CAP_COLLAR, k["joint"] + _CAP_EYE_CLEAR) if p.pole_wick
              else _CAP_COLLAR)
    return dict(mouth=mouth, flare=flare, collar=collar, top=collar + flare,
                eye_z=k["joint"] + 0.5 * _CAP_EYE_CLEAR)


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
    c = cap_plan(p)
    mouth, collar, top = c["mouth"], c["collar"], c["top"]

    body = lathe([(k["r"], 0.0), (k["r"], collar), (mouth, top)],
                 sec, decorate=False)
    # the bore: the socket the spigot goes into, then the funnel, carried
    # past the mouth so the lip reads as an edge instead of a shelf
    bore = lathe([(k["r_bore"], -2.0), (k["r_bore"], collar),
                  (mouth - t * k["f"] + k["s"] * 2.0, top + 2.0)],
                 sec, decorate=False)
    cap = _boolean("difference", [body, bore])
    if p.pole_wick:
        # two eyes to tie the string off, above where the spigot ends
        for i in range(2):
            eye = _diamond_port(x0=0.0, x1=k["r"] + 8.0,
                                z_center=c["eye_z"],
                                half_w=_EYE_W, up=_EYE_W / k["s"],
                                down=0.9 * _EYE_W)
            eye.apply_transform(trimesh.transformations.rotation_matrix(
                math.pi * i, [0, 0, 1]))
            cap = _boolean("difference", [cap, eye])
    return _finish(cap, center=False)


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
