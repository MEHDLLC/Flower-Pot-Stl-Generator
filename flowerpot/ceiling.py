"""Loops on the pot's own rim, and a plate to hang them from.

The hanging cradle is a **gadget**: five printed parts that grip a pot
somebody else made.  That is right for a nursery pot and wrong when you are
printing the pot anyway - the same argument the wall pot settled.  So this
is the other route for a ceiling: three **ears on the rim**, each with a
hole through it, and cord.

It is a better answer than the cradle in three ways.  There is nothing to
assemble.  The cord carries the tension, and cord does not creep the way
PLA does under a load that never comes off - which is the failure mode the
cradle's own docstring says it cannot fix.  And the parts count drops from
five to none, because the loops are part of a pot you were printing.

The one thing to be careful about
---------------------------------
A pot prints standing up, so a cord pulling up on its rim pulls **across
the layer lines** - the one direction printed plastic is genuinely bad at,
and the thing the cradle was contorted to avoid.

It is fine here, and the reason is worth saying rather than assuming: the
cradle's arms had a section set by the arm, and this one has a section set
by *the rim*, which is enormous by comparison.  The loops work at about a
quarter of a megapascal against an interlayer working stress of three, so
there is more than a factor of ten in hand.  The generator reports both
numbers rather than waving at them.

That is also why the hole is **vertical**.  A horizontal eye for an S-hook
would want a gabled roof to print, and worse, it would put the pull on a
fin standing up off the rim - a section a tenth the size, in the same bad
direction.  A vertical bore through a locally widened rim keeps the load in
the rim's own plane, where the layers are, and needs no roof at all.

The ear
-------
Each ear widens the rim outward far enough to get a hole through it with a
web all round, and is gusseted underneath by a cone at 43 degrees - a local
flare of the pot's own wall, so it springs from material rather than from
air.  Everything about it is either a vertical face, a flat top, or that
one cone, so it prints with nothing under it.

The bore goes right through and comes out under the rim, which is where the
knot sits: out of sight, and bearing on the underside rather than on the
edge of a hole.

The plate
---------
``hang_ceiling_plate`` writes a flat bar to screw to the ceiling, with a
countersunk screw at each end and an eye in the middle.  It prints flat, so
the bending that holds the load runs along the layer lines.

It is also the one part here worth arguing about: a steel screw hook costs
pennies, will not creep, and is a better idea.  The plate is offered
because it was asked for, it is sized honestly, and what it screws into
matters far more than what it is made of.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _finish, lathe
from .hanger import _CSK_DEG, _G, _SCREW_INSET, _SIGMA
from .params import ParameterError, PotParams
from .profile import build_profiles, outer_radius_at, wall_cavity_radius
from .sections import make_section

_WEB = 3.5               # material round the bore, in the rim's own plane
_GUSSET = 0.07           # taken off the overhang budget under the ear
_EAR_MIN = 4.0           # ear proud of the rim, at the very least
_SLACK = 1               # one loop assumed slack, as the cradle assumes
_SOIL = 1.2              # g/cm3 of potting mix with water in it
_EXTRA_KG = 0.6          # the plant, and the pot's own plastic
_SIGMA_Z = 3.0           # MPa ACROSS the layers - the working stress in the
#                          direction a cord pulls on a rim.  Well under the
#                          8 MPa used in the plane of the layers, because a
#                          layer bond is not the plastic.
_PLATE_W = 30.0          # the ceiling bar, across
_PLATE_T_MIN = 4.0
_PLATE_REACH = 26.0      # eye to screw
_EYE_R = 5.0


# ---------------------------------------------------------------------------
# sizing
# ---------------------------------------------------------------------------
def ear_section(p: PotParams):
    """The pot's OWN cross-section, minus the texture.

    Not a circle.  A polygon's polyline carries its **corner** radius, so an
    ear placed at that distance from the axis hangs in the air over a flat,
    and the cone that is supposed to gusset it springs from nothing.
    """
    q = p.with_(surface_texture="none")
    sec = make_section(q)
    sec.freeze_z = build_profiles(q).decoration_freeze_z
    return sec


def local_radius(sec, a: float, z: float, r_nominal: float) -> float:
    """What the outline actually measures at azimuth ``a``."""
    return float(sec.radius(np.array([a]), z, r_nominal, False)[0])


def plan(p: PotParams) -> dict:
    """Where each ear goes, and what the cord does to it."""
    n = int(p.hang_loops)
    if n and not 2 <= n <= 6:
        raise ParameterError(
            "hang_loops should be 2-6 - three hangs level on its own, and "
            "more has to be knotted truer. 0 turns them off")
    prof = build_profiles(p)
    sec = ear_section(p)
    z_top = p.height
    r_bore = 0.5 * float(p.hang_loop_bore)
    if not 1.5 <= r_bore <= 8.0:
        raise ParameterError(
            "hang_loop_bore should be 3-16 mm - it is a hole for cord")
    r_pad = r_bore + _WEB
    slope = math.tan(math.radians(p.overhang_limit_deg)) - _GUSSET
    n_top = outer_radius_at(prof, z_top)
    n_cav = wall_cavity_radius(p, z_top)

    ears = []
    for a in [2.0 * math.pi * i / n for i in range(max(n, 1))]:
        r_wall = local_radius(sec, a, z_top, n_top)
        r_cav = local_radius(sec, a, z_top, n_cav)
        # the bore clears the cavity by a web, and stands proud enough to be
        # an ear rather than a bulge
        r_c = max(r_wall, r_cav + _WEB + r_bore,
                  r_wall + _EAR_MIN + r_bore - r_pad)
        r_out = r_c + r_pad
        # how far down the gusset has to reach to find wall AT THIS AZIMUTH
        h = (r_out - r_wall) / slope
        for _ in range(8):
            z0 = max(z_top - h, 0.0)
            here = local_radius(sec, a, z0, outer_radius_at(prof, z0))
            h = min(max((r_out - here) / slope, 1.0), z_top - 1.0)
        z0 = max(z_top - h, 0.0)
        # the lathe takes NOMINAL radii, so the top one is solved back
        n_out = r_out * n_top / max(r_wall, 1e-6)
        for _ in range(4):
            got = local_radius(sec, a, z_top, n_out)
            n_out *= r_out / max(got, 1e-6)
        ears.append(dict(a=a, r_wall=r_wall, r_cav=r_cav, r_c=r_c,
                         r_out=r_out, h=h, z0=z0, n_out=n_out,
                         n_ref=outer_radius_at(prof, z0)))

    soil = _cavity_millilitres(p, prof)
    load = soil * _SOIL / 1000.0 + _EXTRA_KG
    weight = load * _G
    pull = weight / max(n - _SLACK, 1) if n else 0.0

    # the section a cord has to part to pull an ear off: the ear's own
    # footprint, less its hole, in a horizontal plane - which is a plane
    # BETWEEN LAYERS, so it is the interlayer stress that matters
    area = math.pi * (r_pad ** 2 - r_bore ** 2)
    worst = max(ears, key=lambda e: e["h"]) if ears else dict(h=0.0, r_out=0.0,
                                                              r_wall=0.0,
                                                              r_c=0.0,
                                                              r_cav=0.0)
    return dict(prof=prof, sec=sec, n=n, z_top=z_top, r_bore=r_bore,
                r_pad=r_pad, ears=ears, worst=worst, slope=slope, soil=soil,
                load=load, weight=weight, pull=pull, area=area,
                sigma=pull / area if n else 0.0)


def _cavity_millilitres(p: PotParams, prof) -> float:
    """What the pot holds, off its own cavity polyline."""
    zs = np.linspace(prof.floor_top_z, p.height, 241)
    r = np.interp(zs, [z for _, z in prof.inner], [rr for rr, _ in prof.inner])
    return float(np.trapezoid(math.pi * r ** 2, zs)) / 1000.0


def loop_azimuths(p: PotParams) -> list[float]:
    n = int(p.hang_loops)
    return [2.0 * math.pi * i / n for i in range(n)]


def plate_plan(p: PotParams) -> dict:
    """The ceiling bar: how thick it has to be, and how many screws."""
    k = plan(p)
    weight = k["weight"]
    n_screw = max(2, int(p.hang_plate_screws)) if p.hang_plate_screws else 2
    bore = 0.5 * float(p.hang_plate_screw_bore)
    head = bore + 2.25
    reach = _PLATE_REACH + head
    # a bar carrying the whole load at its middle, held at its ends
    t = max(_PLATE_T_MIN,
            math.sqrt(6.0 * weight * reach / (2.0 * _PLATE_W * _SIGMA)))
    length = 2.0 * (reach + head + 4.0)
    return dict(weight=weight, n_screw=n_screw, bore=bore, head=head,
                reach=reach, t=t, length=length,
                sigma=6.0 * weight * reach / (2.0 * _PLATE_W * t ** 2))


def check_ceiling(p: PotParams) -> list[str]:
    out: list[str] = []
    if not p.hang_loops:
        if p.hang_ceiling_plate:
            raise ParameterError(
                "hang_ceiling_plate is the thing the cord goes up to, and "
                "there is no cord without hang_loops - set hang_loops, or "
                "turn the plate off")
        return out
    k = plan(p)
    if any(e["r_c"] - k["r_bore"] - _WEB < e["r_cav"] - 1e-9 for e in k["ears"]):
        raise ParameterError(
            "the loop's bore would break into the pot - this mouth has no "
            "room for a hole beside it. Use a smaller hang_loop_bore, or a "
            "thicker wall")
    if k["worst"]["h"] > 0.55 * p.height:
        raise ParameterError(
            f"the gusset under each ear would run {k['worst']['h']:.0f} mm down a "
            f"{p.height:.0f} mm pot before it found wall to spring from - "
            f"the mouth is too narrow for a loop this size. Use a smaller "
            f"hang_loop_bore, or add a rim")
    if k["sigma"] > _SIGMA_Z:
        raise ParameterError(
            f"each loop would work at {k['sigma']:.1f} MPa ACROSS the layer "
            f"lines against a {_SIGMA_Z:.0f} MPa working stress - a bigger "
            f"hang_loop_bore gives it more section, or use fewer litres")
    out.append(
        f"{k['n']} loops on the rim, each an ear "
        f"{k['worst']['r_out'] - k['worst']['r_wall']:.0f} "
        f"mm proud with a {2 * k['r_bore']:.0f} mm hole through it and a "
        f"{math.degrees(math.atan(k['slope'])):.0f} deg gusset under it. The "
        f"bore comes out below the rim, which is where the knot goes")
    out.append(
        f"full and watered this holds about {k['soil']:.0f} ml and weighs "
        f"around {k['load']:.1f} kg, so each cord pulls about "
        f"{k['pull']:.0f} N with one loop assumed slack. Nothing was asked "
        f"for there - the cavity says how much goes in it")
    out.append(
        f"that is {k['sigma']:.2f} MPa ACROSS the layer lines, against "
        f"{_SIGMA_Z:.0f} MPa. A cord on a rim IS pulling the wrong way for "
        f"a printed part - it is fine because the rim's section is enormous, "
        f"not because the direction stopped mattering. Print hot, and hang "
        f"it with a bag of soil in it before you trust it with a plant")
    out.append(
        "the hole is vertical on purpose: a horizontal eye for an S-hook "
        "needs a gabled roof to print AND puts the pull on a fin standing "
        "off the rim, which is a tenth of the section in the same bad "
        "direction. Use cord, or a split ring through the bore")
    out.append(
        "the cord is what carries the load, and cord does not creep - which "
        "is the one thing no amount of geometry fixes about a printed "
        "hanger. Polyester or nylon; cotton rots")
    if p.hang_ceiling_plate:
        q = plate_plan(p)
        out.append(
            f"the ceiling bar is {q['length']:.0f}x{_PLATE_W:.0f}x"
            f"{q['t']:.1f} mm with {q['n_screw']} countersunk screws, "
            f"working at {q['sigma']:.1f} MPa. Print it FLAT, as modelled, "
            f"so the bending runs along the layer lines")
        out.append(
            f"a steel screw hook costs pennies, will not creep, and is a "
            f"better idea than this bar. What it goes into matters more "
            f"than either: a joist, or a fixing rated well past "
            f"{q['weight']:.0f} N")
    return out


# ---------------------------------------------------------------------------
# the ears, handed to the pot builder
# ---------------------------------------------------------------------------
def loop_parts(p: PotParams
               ) -> tuple[list[trimesh.Trimesh], list[trimesh.Trimesh]]:
    """Solids to add to the pot, and cutters to take out of it."""
    k = plan(p)
    if not k["n"]:
        return [], []
    sec = k["sec"]
    rim = p.rim_height if p.add_top_rim else 0.0
    solids, cutters = [], []
    for e in k["ears"]:
        # the gusset is a flare of the pot's own outline, so it springs from
        # wall at this azimuth rather than from air over a flat
        flare = lathe([(e["n_ref"], e["z0"]), (e["n_out"], k["z_top"])],
                      sec, decorate=False)
        x, y = e["r_c"] * math.cos(e["a"]), e["r_c"] * math.sin(e["a"])
        pad = trimesh.creation.cylinder(
            radius=k["r_pad"], height=4.0 * k["z_top"] + 40.0,
            sections=max(32, p.segments // 3))
        pad.apply_translation((x, y, k["z_top"]))
        solids.append(_boolean("intersection", [flare, pad]))
        depth = e["h"] + rim + 8.0
        bore = trimesh.creation.cylinder(
            radius=k["r_bore"], height=depth + 2.0,
            sections=max(24, p.segments // 4))
        bore.apply_translation((x, y, k["z_top"] + 1.0 - 0.5 * (depth + 2.0)))
        cutters.append(bore)
    return solids, cutters


# ---------------------------------------------------------------------------
# the ceiling bar
# ---------------------------------------------------------------------------
def build_ceiling_plate(p: PotParams) -> trimesh.Trimesh:
    """A flat bar for the ceiling.  Prints FLAT, as modelled."""
    check_ceiling(p)
    if not p.hang_ceiling_plate:
        raise ParameterError(
            "hang_ceiling_plate is off, so there is no bar to write")
    q = plate_plan(p)
    t, half = q["t"], 0.5 * q["length"] - 0.5 * _PLATE_W
    sec = make_section(p.with_(pot_style="classic_tapered",
                               surface_texture="none"))
    bar = trimesh.creation.box(extents=(2.0 * half, _PLATE_W, t))
    bar.apply_translation((0.0, 0.0, 0.5 * t))
    ends = []
    for s in (-1.0, 1.0):
        cap = trimesh.creation.cylinder(radius=0.5 * _PLATE_W, height=t,
                                        sections=64)
        cap.apply_translation((s * half, 0.0, 0.5 * t))
        ends.append(cap)
    body = _boolean("union", [bar] + ends)

    # the heads go on the bed face, so every countersink is a cone that
    # narrows GOING UP: 90 degrees would be exactly the overhang budget, so
    # these are 80, which is what a wood screw wants anyway
    csk = (q["head"] - q["bore"]) / math.tan(math.radians(_CSK_DEG))
    cuts = []
    for s in (-1.0, 1.0):
        x = s * (0.5 * q["length"] - _SCREW_INSET)
        cut = lathe([(q["head"], -1.0), (q["head"], 0.0),
                     (q["bore"], csk), (q["bore"], t + 1.0)], sec,
                    decorate=False)
        cut.apply_translation((x, 0.0, 0.0))
        cuts.append(cut)
    if q["n_screw"] > 2:                     # the rest, evenly between them
        span = 2.0 * (0.5 * q["length"] - _SCREW_INSET) / (q["n_screw"] - 1)
        for i in range(1, q["n_screw"] - 1):
            x = -(0.5 * q["length"] - _SCREW_INSET) + i * span
            cut = lathe([(q["head"], -1.0), (q["head"], 0.0),
                         (q["bore"], csk), (q["bore"], t + 1.0)], sec,
                        decorate=False)
            cut.apply_translation((x, 0.0, 0.0))
            cuts.append(cut)
    # the eye, chamfered underneath by the same 80 degree cone so the cord
    # bears on a slope instead of on the edge of a hole
    cuts.append(lathe([(_EYE_R + 2.0, -1.0), (_EYE_R + 2.0, 0.0),
                       (_EYE_R, 2.0 / math.tan(math.radians(_CSK_DEG))),
                       (_EYE_R, t + 1.0)], sec, decorate=False))
    return _finish(_boolean("difference", [body] + cuts), center=False)
