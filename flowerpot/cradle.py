"""A pot that sits in a dish, and drinks out of it.

Two parts and no hardware:

* a **dish** - a solid bowl, no holes below its rim, that holds the water;
* a **pot** whose bottom is not a floor but a **keel**: a cone that hangs
  down inside the dish and dips into the water.  Slots up the keel let the
  soil touch the water directly, so the column wicks and the pot waters
  itself.

The pot lands on the dish's rim by a **cone seat** - the underside of the
pot's collar and the top of the dish's rim are the same cone, so the pot
centres itself as it goes down and cannot be put on crooked.  It is left
``_SEAT_CLEAR`` mm loose on the perpendicular: two printed cones never mate
on their nominal surfaces, and a pot that lands on one high spot rocks.

Everything here is driven by one number
---------------------------------------
``s = slope_budget(p)`` - the steepest ``dr/dz`` a surface may have and
still print without supports.  The keel *is* that slope, because a keel at
the budget is the deepest one that fits under a given rim, and the seat is
the keel, and the dish's rim is the seat.  Change the overhang limit and
the whole pair re-solves.

What a printer cannot copy
--------------------------
A dish shaped like a real bowl - round bottom, walls rising to vertical -
is a 90 degree overhang at its pole and 60 degrees round its flanks.  Ours
flares the other way: it stands on a flat foot and opens **outwards** all
the way to the rim, never past ``s``.  ``cradle_bowl`` picks how hard:

* ``round`` - a circular arc that leaves the foot at exactly the budget and
  is vertical by the time it reaches the rim.  The closest a support-free
  bowl gets to a bowl.
* ``cone``  - a straight flare from a narrow foot.  The least water.
* ``tub``   - nearly straight sides on a wide foot.  The most water.

Where the water goes in
-----------------------
Through a **notch in the dish's rim**, not through the pot.  At the joint
the pot's skirt is one wall thick with the soil right behind it, so a hole
there empties the pot; the dish's rim has nothing above it at all, so a
notch in it has no roof to hold up.  Assembled, the two read as the same
thing - a gap at the seam, with the pot's keel sloping down over it and
carrying whatever you pour straight into the water.

The dish itself stays **solid** - no port, no grommet, nothing below its
rim to leak.  The notch is the overflow as well as the inlet: fill until it
runs back out at you, and the level is set to the millimetre by where the
notch's sill was cut.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _finish, lathe
from .params import ParameterError, PotParams
from .profile import slope_budget
from .sections import Section

BOWLS = ("round", "cone", "tub")

#: how much of the overhang budget the bowl's straight flares actually use
_BOWL_SLOPE = {"cone": 0.72, "tub": 0.20}

_RESERVE = 0.10          # held back from tan(limit): the seat is at the budget
_SEAT_CLEAR = 0.25       # perpendicular slack on the cone seat
_COLLAR = 4.0            # extra wall at the pot's seat, over wall_thickness
_LIP_OUT = 3.0           # how far the pot's lip stands past its wall
_LIP_H = 4.0             # ... and the straight part of it

_SLOT_W = 2.2            # half-width of a wicking slot
_SLOT_GAP = 0.8          # clear of the pad, so the pad prints as one disc
_SLOT_REACH = 0.45       # of the keel's radial run
_SLOT_KEEP = 1.5         # clear of the collar, so a slot stays in the keel

_WINDOW_DEEP = 7.0       # how far the fill notch cuts into the dish's rim
_WINDOW_WIDE = 0.30      # ... as a fraction of the rim radius, per side

_GAP_MIN = 2.0           # narrowest water gap, keel to bowl
_DROP_MIN = 4.0          # ... and under it
_PAD_MIN = 12.0          # smallest keel pad worth standing a print on


# ---------------------------------------------------------------------------
# sizing
# ---------------------------------------------------------------------------
def _round_section(p: PotParams) -> Section:
    return Section(p.with_(surface_texture="none"))


def wall_of(p: PotParams) -> float:
    return max(2.2, p.wall_thickness)


def floor_of(p: PotParams) -> float:
    return max(3.0, p.base_thickness)


def plan(p: PotParams) -> dict:
    """Every number both parts are cut from.

    Solved in one place because the two parts share a surface: the pot's
    seat and the dish's rim are the same cone, and the dish's cavity is
    sized round the keel that hangs in it.
    """
    if p.cradle_bowl not in BOWLS:
        raise ParameterError(
            f"unknown cradle_bowl {p.cradle_bowl!r}; choose from {list(BOWLS)}")

    s = slope_budget(p, _RESERVE)
    t = wall_of(p)
    floor = floor_of(p)
    r_rim = 0.5 * float(p.cradle_diameter)          # outside, at the joint
    z_seam = float(p.cradle_dish_height)
    keel = float(p.cradle_keel)
    body = float(p.cradle_height) - z_seam

    if r_rim <= 20.0:
        raise ParameterError("cradle_diameter should be at least 40 mm")
    if body <= 20.0:
        raise ParameterError(
            f"cradle_height {p.cradle_height:.0f} mm leaves only "
            f"{body:.0f} mm of pot above a {z_seam:.0f} mm dish - raise one "
            f"or lower the other")
    if keel <= 0.0:
        raise ParameterError("cradle_keel must be greater than zero")

    r_pad = r_rim - s * keel                        # the keel's flat tip
    if r_pad < _PAD_MIN:
        raise ParameterError(
            f"a {keel:.0f} mm keel under a {2 * r_rim:.0f} mm rim comes to a "
            f"point: at the overhang limit it can only fall {s:.2f} mm per mm "
            f"of radius, so keep cradle_keel under "
            f"{(r_rim - _PAD_MIN) / s:.0f} mm or widen cradle_diameter")

    z_pad = z_seam - keel                           # where the keel bottoms out
    # the dish's rim is the keel, moved _SEAT_CLEAR out of its way; that is
    # the radial shift which leaves that much clearance on the perpendicular
    slack = _SEAT_CLEAR * math.hypot(1.0, s)
    z_dish = z_seam - slack / s                     # top of the dish
    z_a = z_seam - (t + slack) / s                  # top of the dish's cavity
    depth = z_a - floor                             # ... and how deep it is
    if depth <= 8.0:
        raise ParameterError(
            f"cradle_dish_height {z_seam:.0f} mm leaves no bowl under the rim")
    if z_pad - floor < _DROP_MIN:
        raise ParameterError(
            f"the keel reaches to {z_pad - floor:.1f} mm above the dish's "
            f"floor, which is not a reservoir - shorten cradle_keel or raise "
            f"cradle_dish_height")

    r_top = r_rim - t                               # the dish's mouth, inside
    if p.cradle_bowl == "round":
        # the arc that leaves the foot at exactly the budget and stands
        # vertical at the rim: rho from d/sqrt(rho^2 - d^2) = s
        rho = depth * math.hypot(1.0, 1.0 / s)
        bowl = dict(kind="round", rho=rho, r_c=r_top - rho, z_c=z_a)
        r_floor = bowl["r_c"] + math.sqrt(max(rho * rho - depth * depth, 0.0))
    else:
        slope = _BOWL_SLOPE[p.cradle_bowl] * s
        r_floor = r_top - slope * depth
        bowl = dict(kind="line", slope=slope)
    if r_floor < 8.0:
        raise ParameterError(
            f"a {p.cradle_bowl} bowl {depth:.0f} mm deep comes to a point "
            f"before it reaches the plate - lower cradle_dish_height, or "
            f"choose a fuller cradle_bowl")
    bowl.update(r_top=r_top, z_a=z_a, r_floor=r_floor, floor=floor)

    f_p = t + _COLLAR                               # the pot's seat collar
    r_off = t * math.hypot(1.0, s)                  # wall t, measured across
    k = dict(
        s=s, wall=t, floor=floor, r_off=r_off, slack=slack,
        r_rim=r_rim, z_seam=z_seam, keel=keel, body=body,
        r_pad=r_pad, z_pad=z_pad, z_a=z_a, z_dish=z_dish, depth=depth,
        r_top=r_top, r_floor=r_floor, bowl=bowl,
        collar=f_p, z_collar=z_seam - (f_p - r_off) / s,
        r_mouth=r_rim + float(p.cradle_flare),
        z_top=z_seam + body,
    )

    # the wicking slots, and with them the level the reservoir is filled to
    a = r_pad + _SLOT_W + _SLOT_GAP
    b = min(a + _SLOT_REACH * (r_rim - r_pad),
            r_rim - f_p - _SLOT_KEEP - _SLOT_W)
    k["slot_r0"], k["slot_r1"], k["slot_w"] = a, b, _SLOT_W
    k["z_fill"] = min(z_pad + max(b - r_pad, 0.0) / s, z_a)

    # the fill notch is also the overflow, so it has to sit above the level
    # the pot wicks from - on a shallow dish it gives ground rather than
    # letting the water reach the soil
    deep = min(_WINDOW_DEEP, max(3.0, z_dish - k["z_fill"] - 3.0))
    k["window_deep"] = deep
    k["z_brim"] = (z_dish - deep) if int(p.cradle_windows) else z_a
    return k


def bowl_radius(k: dict, z: float) -> float:
    """Inside of the dish at height ``z``."""
    b = k["bowl"]
    z = min(max(z, k["floor"]), b["z_a"])
    if b["kind"] == "round":
        u = b["z_c"] - z
        return b["r_c"] + math.sqrt(max(b["rho"] ** 2 - u * u, 0.0))
    return b["r_top"] - b["slope"] * (b["z_a"] - z)


def bowl_slope(k: dict, z: float) -> float:
    """``dr/dz`` of that surface - what the outer wall inherits."""
    b = k["bowl"]
    if b["kind"] != "round":
        return b["slope"]
    z = min(max(z, k["floor"]), b["z_a"])
    u = b["z_c"] - z
    return u / math.sqrt(max(b["rho"] ** 2 - u * u, 1e-9))


def keel_radius(k: dict, z: float) -> float:
    """Outside of the pot at height ``z``, in the assembled frame."""
    return k["r_pad"] + k["s"] * (z - k["z_pad"])


def water_gap(k: dict) -> float:
    """Narrowest water gap between the keel and the bowl it hangs in.

    Measured over the wetted part of the keel only.  Higher up the two
    close on each other on purpose - they meet at the rim, because the rim
    *is* the keel's own cone, and that contact is the seat.
    """
    lo, hi = k["z_pad"], k["z_fill"]
    if hi <= lo:
        return 0.0
    return min(bowl_radius(k, z) - keel_radius(k, z)
               for z in np.linspace(lo, hi, 61))


def water_millilitres(p: PotParams, level: float | None = None) -> float:
    """Water the assembled pair holds up to ``level`` (default: the top of
    the wicking slots, which is as high as it is worth filling)."""
    k = plan(p)
    hi = k["z_fill"] if level is None else float(level)
    if hi <= k["floor"]:
        return 0.0
    z = np.linspace(k["floor"], hi, 161)
    bowl = np.array([math.pi * bowl_radius(k, v) ** 2 for v in z])
    keel = np.array([math.pi * max(keel_radius(k, v), 0.0) ** 2
                     if v >= k["z_pad"] else 0.0 for v in z])
    net = np.maximum(bowl - keel, 0.0)
    return float(0.5 * np.sum((net[:-1] + net[1:]) * np.diff(z))) / 1000.0


def check_cradle(p: PotParams) -> list[str]:
    out: list[str] = []
    if p.cradle not in ("none", "set", "pot", "dish"):
        raise ParameterError(
            f"unknown cradle {p.cradle!r}; choose from ['set', 'pot', 'dish']")
    if p.cradle == "none":
        return out
    if not 0 <= int(p.cradle_windows) <= 4:
        raise ParameterError("cradle_windows should be 0-4")
    if not 0 <= int(p.cradle_drains) <= 24:
        raise ParameterError("cradle_drains should be 0-24")
    if p.cradle_flare < 0.0:
        raise ParameterError("cradle_flare cannot be negative (the mouth may "
                             "match the joint, but not undercut it)")
    k = plan(p)
    if k["slot_r1"] <= k["slot_r0"] and p.cradle_drains:
        need = (k["collar"] + _SLOT_KEEP + 2.0 * _SLOT_W + _SLOT_GAP) / k["s"]
        raise ParameterError(
            f"a {p.cradle_keel:.0f} mm keel has no flank left to slot once "
            f"the seat collar has had its share - cradle_keel needs about "
            f"{need:.0f} mm (widening the pot does not help: the keel falls "
            f"at a fixed slope, so a wider rim moves its pad out with it)")
    # a backstop, not a knob: the keel falls at the budget and every bowl
    # is shallower, so the two can only diverge going down.  It is here so
    # that a future bowl steeper than the keel is caught rather than shipped
    gap = water_gap(k)
    if gap < _GAP_MIN:
        raise ParameterError(
            f"the keel comes within {gap:.1f} mm of the bowl, which leaves "
            f"nowhere for the water - choose a fuller cradle_bowl than "
            f"{p.cradle_bowl!r}, or shorten cradle_keel")
    out.append(
        f"the dish holds about {water_millilitres(p):.0f} ml to the top of "
        f"the wicking slots and {water_millilitres(p, k['z_brim']):.0f} ml "
        f"before it runs back out of the fill notch - a {p.cradle_bowl!r} "
        f"bowl is the dial: 'tub' holds the most, 'cone' the least, 'round' "
        f"looks the most like a dish")
    if not p.cradle_drains:
        out.append(
            "cradle_drains 0 leaves the keel closed: the pot will hold its "
            "own water and take nothing from the dish (fine as a cachepot)")
    if not p.cradle_windows:
        out.append(
            "cradle_windows 0 leaves nowhere to pour: the dish has to be "
            "filled with the pot lifted off")
    return out


# ---------------------------------------------------------------------------
# the dish
# ---------------------------------------------------------------------------
def dish_cavity_rings(p: PotParams, over: float = 0.0) -> list[tuple[float, float]]:
    """The bowl, floor to rim.  ``over`` lifts the top ring past the rim so
    the same list can be used as a cutter."""
    k = plan(p)
    z = np.linspace(k["floor"], k["z_a"], 49)
    rings = [(bowl_radius(k, v), float(v)) for v in z]
    # the seat: the rim's top face is the keel's own cone, moved out of its
    # way by the fit, so the pot slides down it until the two are in contact
    rings.append((k["r_rim"], k["z_dish"]))
    if over > 0.0:
        rings.append((k["r_rim"] + over, k["z_dish"] + over / k["s"]))
    return rings


def dish_rings(p: PotParams) -> list[tuple[float, float]]:
    """The outside: the bowl offset by one wall, clamped at the joint.

    Clamped because the rim is where the two parts agree - whatever the
    bowl is doing inside, the outside arrives at ``cradle_diameter`` and
    goes vertical for the last few millimetres.
    """
    k = plan(p)
    z = np.linspace(k["floor"], k["z_a"], 49)
    rings = [(k["r_floor"] + k["wall"] * math.hypot(1.0, bowl_slope(k, k["floor"])),
              0.0)]
    for v in z:
        r = bowl_radius(k, v) + k["wall"] * math.hypot(1.0, bowl_slope(k, v))
        rings.append((min(r, k["r_rim"]), float(v)))
    rings.append((k["r_rim"], k["z_dish"]))
    # drop any ring the clamp made non-monotonic in z
    out = [rings[0]]
    for r, v in rings[1:]:
        if v > out[-1][1] + 1e-6:
            out.append((max(r, out[-1][0]), v))
    return out


def _window_cutters(p: PotParams) -> list[trimesh.Trimesh]:
    """Notches down into the dish's rim - what you pour through.

    A box, flat bottomed: cut downwards into a rim, every face it leaves is
    either vertical or pointing at the ceiling.  There is nothing above a
    rim to hold up, which is the whole reason the fill port lives here and
    not in the pot's skirt.
    """
    n = int(p.cradle_windows)
    if n <= 0:
        return []
    k = plan(p)
    half = _WINDOW_WIDE * k["r_rim"]
    deep = k["window_deep"]
    x0 = 0.55 * k["r_rim"]                   # well inside the bowl: free air
    x1 = k["r_rim"] + 8.0
    tall = k["z_dish"]
    out = []
    for i in range(n):
        box = trimesh.creation.box(extents=(x1 - x0, 2.0 * half, tall))
        box.apply_translation((0.5 * (x0 + x1), 0.0,
                               k["z_dish"] - deep + 0.5 * tall))
        box.apply_transform(trimesh.transformations.rotation_matrix(
            2.0 * math.pi * i / n, [0, 0, 1]))
        out.append(box)
    return out


def build_cradle_dish(p: PotParams) -> trimesh.Trimesh:
    """The dish: prints on its foot, no supports, no holes below the rim."""
    check_cradle(p)
    sec = _round_section(p)
    body = lathe(dish_rings(p), sec, decorate=False)
    body = _boolean("difference",
                    [body, lathe(dish_cavity_rings(p, over=10.0), sec,
                                 decorate=False)])
    cutters = _window_cutters(p)
    if cutters:
        body = _boolean("difference", [body] + cutters)
    return _finish(body, center=False)


# ---------------------------------------------------------------------------
# the pot
# ---------------------------------------------------------------------------
def pot_rings(p: PotParams) -> list[tuple[float, float]]:
    """Outside of the pot, pad to lip, in the pot's own frame (pad at 0)."""
    k = plan(p)
    top = k["keel"] + k["body"]
    r_mouth = k["r_mouth"]
    rings = [(k["r_pad"], 0.0), (k["r_rim"], k["keel"])]
    if p.cradle_lip:
        rings += [(r_mouth, top - _LIP_H - _LIP_OUT / k["s"]),
                  (r_mouth + _LIP_OUT, top - _LIP_H),
                  (r_mouth + _LIP_OUT, top)]
    else:
        rings.append((r_mouth, top))
    return rings


def pot_cavity_rings(p: PotParams) -> list[tuple[float, float]]:
    """The soil space, in the pot's own frame.

    The keel offset by one wall; a short vertical band where the seat
    collar thickens; the collar shed again at the overhang limit, because
    carrying it up the body would cost more plastic than the whole dish;
    then parallel to the wall and straight out past the lip, so the lip
    reads as a thickened edge rather than a shelf over the soil.
    """
    k = plan(p)
    top = k["keel"] + k["body"]
    r_collar = k["r_rim"] - k["collar"]
    z_shed = k["keel"] + (k["collar"] - k["wall"]) / k["s"]
    r_wall = k["r_rim"] - k["wall"]
    z_lip = top - _LIP_H - _LIP_OUT / k["s"] if p.cradle_lip else top
    slope = float(p.cradle_flare) / max(z_lip - k["keel"], 1e-9)
    return [
        (max(k["r_pad"] + k["s"] * k["floor"] - k["r_off"], 1.0), k["floor"]),
        (r_collar, k["z_collar"] - k["z_pad"]),
        (r_collar, k["keel"]),
        (r_wall, z_shed),
        (r_wall + slope * (top + 2.0 - z_shed), top + 2.0),
    ]


def _slot_cutters(p: PotParams, z0: float = 0.0) -> list[trimesh.Trimesh]:
    """Wicking slots up the keel: rounded radial trenches, cut straight down.

    A vertical cut is the one cut that can never leave an overhang - every
    face it makes is a vertical plane or a vertical cylinder.  Through a
    45 degree keel that reads as a slit running up the cone, which is
    exactly what has to be there: the soil has to touch the water.
    """
    n = int(p.cradle_drains)
    if n <= 0:
        return []
    k = plan(p)
    a, b, w = k["slot_r0"], k["slot_r1"], k["slot_w"]
    if b <= a:
        return []
    tall = k["keel"] + 30.0
    z_mid = z0 + 0.5 * tall - 8.0
    out = []
    for i in range(n):
        ang = 2.0 * math.pi * i / n
        rot = trimesh.transformations.rotation_matrix(ang, [0, 0, 1])
        box = trimesh.creation.box(extents=(b - a, 2.0 * w, tall))
        box.apply_translation((0.5 * (a + b), 0.0, z_mid))
        box.apply_transform(rot)
        out.append(box)
        for r in (a, b):
            end = trimesh.creation.cylinder(radius=w, height=tall, sections=24)
            end.apply_translation((r, 0.0, z_mid))
            end.apply_transform(rot)
            out.append(end)
    return out


def build_cradle_pot(p: PotParams) -> trimesh.Trimesh:
    """The pot: prints standing on its keel's pad, no supports."""
    check_cradle(p)
    sec = _round_section(p)
    body = lathe(pot_rings(p), sec, decorate=False)
    body = _boolean("difference",
                    [body, lathe(pot_cavity_rings(p), sec, decorate=False)])
    cutters = _slot_cutters(p)
    if cutters:
        body = _boolean("difference", [body] + cutters)
    return _finish(body, center=False)


# ---------------------------------------------------------------------------
# how they go together
# ---------------------------------------------------------------------------
def seated_pot(p: PotParams) -> trimesh.Trimesh:
    """The pot, lifted to where its seat meets the dish's rim."""
    pot = build_cradle_pot(p)
    pot.apply_translation((0.0, 0.0, plan(p)["z_pad"]))
    return pot
