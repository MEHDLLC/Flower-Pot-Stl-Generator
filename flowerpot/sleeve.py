"""A cover for the nursery pot the plant came in.

Nobody wants to look at a black plastic pot, and nobody wants to repot a
plant that has just been moved.  A sleeve solves both: the nursery pot
drops into it, pot and all, and what shows is the sleeve.

**A sleeve is a pot.**  That is the whole design: its outside is built by
the same machinery as every other pot here, so ``pot_style``,
``surface_texture``, the rim and the colours all work on it exactly as they
do on a planter.  Only the inside is different, and the inside is not a
design at all - it is the nursery pot, plus a fit.

The one thing that does not carry over is ``vase_profile``.  Every one of
those silhouettes necks in at the mouth *and* narrows at the foot, and a
sleeve has a pot inside it and a well under it, so they are refused outright
rather than half-working.

The seat, and the well under it
-------------------------------
The cavity is a **step**: a straight well at the bottom, narrower than the
nursery pot's base, and the pot's space above it.  The pot lands on the
step and the well is left under it.

A step in a cavity is often a ceiling, but not this one.  Going up, this
cavity gets *wider* - narrow well, then the pot's space, then the pot's own
taper - so the step faces the sky and the whole inside prints as wall.  It
is the cavities that narrow going up that need a cone.

The well is what a cachepot is usually missing: somewhere for a drink to go
that is not the bottom of the pot.  How much it holds is reported, and it
is also the only thing keeping the pot's drainage holes off the floor, so
it is not decoration.

What the silhouette is not allowed to do
----------------------------------------
Every other pot here can be any shape that prints.  A sleeve cannot: it has
a nursery pot inside it, so anything that closes in on that pot - a narrow
``sleeve_base``, a negative ``belly``, a vase curve - cuts straight through
it.  The wall is swept end to end against the pot it has to contain, and a
silhouette that pinches is rejected **with the height it pinched at and how
much it was short by**, rather than quietly producing a sleeve nothing fits
in.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _finish, lathe
from .params import ParameterError, PotParams
from .profile import build_profiles, resample
from .sections import make_section
from .textures import make_texture
from .underpot import NURSERY, _BASE_RATIO

#: A nursery pot is about as tall as it is wide across the top.  Like
#: ``_BASE_RATIO`` this is a typical, not a measurement.
_HEIGHT_RATIO = 0.95

_FLOOR = 4.0             # least floor under the well
_SEAT_W = 5.0            # ledge the nursery pot's base lands on
_WELL_MIN = 6.0
_WALL_MIN = 1.8          # least wall left between the sleeve and the pot
_OVERSHOOT = 3.0         # how far the cavity carries past the sleeve's rim


# ---------------------------------------------------------------------------
# the pot that goes inside
# ---------------------------------------------------------------------------
def nursery(p: PotParams) -> dict:
    """The nursery pot, as three numbers and the taper they imply."""
    if p.sleeve_pot_size == "custom":
        top, base = float(p.sleeve_pot_top), float(p.sleeve_pot_base)
        height = float(p.sleeve_pot_height)
    elif p.sleeve_pot_size in NURSERY:
        nominal = NURSERY[p.sleeve_pot_size]
        top, base = nominal, _BASE_RATIO * nominal
        height = _HEIGHT_RATIO * nominal
    else:
        raise ParameterError(
            f"unknown sleeve_pot_size {p.sleeve_pot_size!r}; choose from "
            f"{['custom'] + sorted(NURSERY)}")
    if not 40.0 <= top <= 500.0:
        raise ParameterError(
            "sleeve_pot_top should be 40-500 mm, measured across the top of "
            "the nursery pot")
    if not 0.35 * top <= base < top:
        raise ParameterError(
            f"a {base:.0f} mm base under a {top:.0f} mm top is not a nursery "
            f"pot - sleeve_pot_base wants to be between {0.35 * top:.0f} and "
            f"{top:.0f} mm")
    if not 0.3 * top <= height <= 3.0 * top:
        raise ParameterError(
            f"sleeve_pot_height {height:.0f} mm is out of proportion with a "
            f"{top:.0f} mm pot - measure it again")
    return dict(top_r=0.5 * top, base_r=0.5 * base, height=height,
                slope=(0.5 * top - 0.5 * base) / height)


def plan(p: PotParams) -> dict:
    """Where the pot sits, how tall the sleeve is, and the well beneath."""
    pot = nursery(p)
    fit = max(0.0, float(p.sleeve_fit))
    floor = max(_FLOOR, p.base_thickness)
    well = max(0.0, float(p.sleeve_well))
    if well and well < _WELL_MIN:
        raise ParameterError(
            f"sleeve_well under {_WELL_MIN:.0f} mm is not a well - the pot's "
            f"drainage holes would sit on the floor. Raise it, or set it to 0 "
            f"and let the pot stand on the bottom")
    r_seat = pot["base_r"] + fit                 # the cavity at the pot's base
    r_well = max(r_seat - _SEAT_W, 8.0)
    z_seat = floor + well
    height = z_seat + pot["height"] - float(p.sleeve_reveal)
    if height <= z_seat + 15.0:
        raise ParameterError(
            f"sleeve_reveal {p.sleeve_reveal:.0f} mm leaves a sleeve barely "
            f"taller than its own well - lower it, or use a taller pot")
    return dict(pot=pot, fit=fit, floor=floor, well=well, r_seat=r_seat,
                r_well=r_well, z_seat=z_seat, height=height)


def cavity_radius(k: dict, z: float) -> float:
    """Inside of the sleeve at ``z`` - the well, the step, then the pot."""
    if z <= k["z_seat"]:
        return k["r_well"]
    return k["r_seat"] + k["pot"]["slope"] * (z - k["z_seat"])


def cavity_rings(p: PotParams) -> list[tuple[float, float]]:
    """The cavity, in the section's own units.

    The sweep uses the same cross-section as the outside, and a section is
    cut from its **corner** radius - so for a polygon these are divided up
    by the flat factor, which is what puts the *inscribed* circle on the
    nursery pot instead of the circumscribed one.  Get that backwards and a
    square sleeve has a hole its pot cannot go in.
    """
    k = plan(p)
    flat = flat_factor(p)
    top = k["height"] + _OVERSHOOT
    return [(k["r_well"] / flat, k["floor"]),
            (k["r_well"] / flat, k["z_seat"]),   # the well
            (k["r_seat"] / flat, k["z_seat"]),   # the step: it faces the sky
            (cavity_radius(k, top) / flat, top)]  # the pot's own taper


def well_millilitres(p: PotParams) -> float:
    k = plan(p)
    return math.pi * k["r_well"] ** 2 * k["well"] / 1000.0


# ---------------------------------------------------------------------------
# the sleeve, expressed as a pot
# ---------------------------------------------------------------------------
def sleeve_params(p: PotParams) -> PotParams:
    """The sleeve's **outside**, in the generator's own terms.

    Everything the pot builder knows how to do - the styles, the vase
    silhouettes, the textures, the rim - then applies without knowing this
    is a sleeve at all.
    """
    k = plan(p)
    t = max(2.0, p.wall_thickness)
    flat = flat_factor(p)
    # the mouth: the nursery pot where the sleeve's rim crosses it, plus the
    # fit that is already in the cavity, plus a wall.  Divided by the flat
    # factor because a polygon is cut from its corner radius and it is the
    # flats, not the corners, that the pot would come through first
    top_d = 2.0 * (cavity_radius(k, k["height"]) + t) / flat
    # the foot follows the well rather than the mouth: a sleeve whose base is
    # set by its widest point is mostly infill down there.  But the step is
    # the widest the cavity gets low down, so the taper has to clear that too
    z_s, h = k["z_seat"], k["height"]
    at_step = ((k["r_seat"] + t) / flat - 0.5 * top_d * z_s / h) / max(
        1.0 - z_s / h, 1e-6)
    base_d = (float(p.sleeve_base) if float(p.sleeve_base) > 0.0
              else max(2.0 * (k["r_well"] + t) / flat, 2.0 * at_step))
    return p.with_(height=k["height"], top_diameter=top_d,
                   bottom_diameter=base_d, base_thickness=k["floor"],
                   drainage_pattern="none", num_side_holes=0,
                   generate_saucer=False, jar_greenhouse=False,
                   sleeve=False, bouquet=False, stem=False, soil_cap=False)


def flat_factor(p: PotParams) -> float:
    """How far in a style's *flats* sit, as a fraction of its corners.

    1 for anything round; less for a polygon, whose faces are what the pot
    inside would come through first.
    """
    if p.pot_style in ("hexagonal", "square", "low_poly_faceted"):
        return math.cos(math.pi / p.sides)
    return 1.0


def wall_at(p: PotParams, z: float) -> float:
    """Sleeve wall left at ``z``: its outside less the pot it contains."""
    from .profile import wall_radius
    k = plan(p)
    q = sleeve_params(p)
    outer = wall_radius(q, min(max(z, 0.0), q.height)) * flat_factor(p)
    return outer - cavity_radius(k, z)


def check_sleeve(p: PotParams) -> list[str]:
    out: list[str] = []
    if not p.sleeve:
        return out
    if p.vase_profile != "none":
        raise ParameterError(
            f"vase_profile {p.vase_profile!r} cannot be a sleeve: every one "
            f"of those silhouettes necks in at the mouth AND narrows at the "
            f"foot, and a sleeve has a nursery pot inside it and a well under "
            f"it. Shape it with pot_style and surface_texture instead")
    k = plan(p)
    q = sleeve_params(p)
    q.validate()
    # sweep the whole wall against the pot it has to contain
    worst_z, worst = 0.0, math.inf
    for z in np.linspace(0.0, k["height"], 161):
        w = wall_at(p, float(z))
        if w < worst:
            worst_z, worst = float(z), w
    if worst < _WALL_MIN:
        raise ParameterError(
            f"this silhouette closes onto the nursery pot {worst_z:.0f} mm up, "
            f"leaving {max(worst, 0.0):.1f} mm of wall - a sleeve has a pot "
            f"inside it, so it cannot neck in below the pot's widest point. "
            f"Raise sleeve_fit by about {_WALL_MIN - worst:.0f} mm to grow "
            f"the whole sleeve round it, or widen sleeve_base")
    out.append(
        f"the sleeve is {q.top_diameter + 2 * (q.rim_width if q.add_top_rim else 0.0):.0f} mm across its widest and "
        f"{k['height']:.0f} mm tall, for a {2 * k['pot']['top_r']:.0f} mm "
        f"nursery pot that stands {k['pot']['height']:.0f} mm - its rim "
        + (f"finishes {p.sleeve_reveal:.0f} mm proud of the sleeve"
           if p.sleeve_reveal > 0 else
           f"sits {-p.sleeve_reveal:.0f} mm below the sleeve's"
           if p.sleeve_reveal < 0 else "finishes flush with the sleeve's"))
    if p.sleeve_pot_size != "custom":
        out.append(
            f"{p.sleeve_pot_size} is a nominal size - the pot's width across "
            f"the TOP. Its base is taken as {_BASE_RATIO:.2f} of that and its "
            f"height as {_HEIGHT_RATIO:.2f}, which is about where nursery "
            f"pots land. Measure yours into sleeve_pot_top/base/height if the "
            f"reveal matters")
    if k["well"]:
        out.append(
            f"the well under the pot holds about {well_millilitres(p):.0f} ml "
            f"- there is no drain, so that is also all it can hold before the "
            f"pot is standing in it")
    else:
        out.append(
            "sleeve_well 0 stands the nursery pot on the floor of the sleeve: "
            "nothing drains and its holes are blocked - lift it unless the "
            "sleeve is only ever going to be dry")
    return out


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
def _styled_outer(q: PotParams) -> trimesh.Trimesh:
    """The pot builder's outer half, on its own.

    Lifted from :func:`flowerpot.build.build_pot` rather than called
    through it, because a sleeve needs the body without the pot's cavity -
    the nursery pot is the cavity.
    """
    section = make_section(q)
    prof = build_profiles(q)
    section.freeze_z = prof.decoration_freeze_z
    section.texture = make_texture(q, prof, section)
    step = q.vertical_step
    if section.texture is not None:
        step = min(step, q.texture_cell / 12.0)
    rings = resample(prof.outer, step,
                     section.extra_ring_heights(0.0, q.height),
                     section.smooth_vertically())
    return lathe(rings, section, decorate=True)


def build_sleeve(p: PotParams) -> trimesh.Trimesh:
    """The sleeve: prints standing on its own foot, no supports."""
    check_sleeve(p)
    q = sleeve_params(p)
    section = make_section(q)
    body = _styled_outer(q)
    # the cavity gets the same rings the outside would: a section whose
    # outline turns with height (the faceted style) is only followed where
    # there is a ring, and a four-ring cavity walks straight out through a
    # wall that is busy rotating
    rings = resample(cavity_rings(p), q.vertical_step,
                     section.extra_ring_heights(0.0, q.height),
                     section.smooth_vertically())
    cavity = lathe(rings, section, decorate=False)
    return _finish(_boolean("difference", [body, cavity]), center=False)


def nursery_solid(p: PotParams) -> trimesh.Trimesh:
    """The nursery pot itself, where it sits - for proving the fit."""
    k = plan(p)
    pot = k["pot"]
    return lathe([(pot["base_r"], k["z_seat"]),
                  (pot["top_r"], k["z_seat"] + pot["height"])],
                 make_section(p.with_(pot_style="classic_tapered",
                                      surface_texture="none")),
                 decorate=False)
