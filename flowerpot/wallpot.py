"""A pot with the wall mount built into its back.

The hanging cradle and the wall bracket are **gadgets**: they grip a pot
somebody else made.  That is the right answer when the pot came from a
nursery, and the wrong one when you are printing the pot anyway - a
bracket you have to look at is a bracket that should have been part of the
pot.

So this is the other route.  A wall pot is round for most of its
circumference and **flat across the back**, and the female half of a French
cleat is a pocket inside that flat back.  The male rail screws to the wall
and disappears into it.  Hung, there is no bracket to see: the pot grows
out of the wall.

**A wall pot is a pot.**  Same as the sleeve: the outside is built by the
same machinery as every other pot here, so ``pot_style``, ``vase_profile``,
``surface_texture``, the rim and the colours all work on it.  Two planes
and a pocket are the only difference.

Which way you rip the cleat
---------------------------
A full pot of wet soil sitting out from a wall is a **cantilever**, and a
French cleat has nothing to say about a moment on its own - it only carries
shear.  Two things make it work, and they are the same two the wall bracket
needed:

* The back **bears flat on the wall** either side of the pocket and below
  it, so the moment becomes a couple: the back pushes in low down, the
  pocket's ceiling holds out up top.
* The rail's bevel **rises away from the wall**.  Tip the pot the way a
  cantilever tips it - top out, bottom in - and the pocket's ceiling drives
  down and out into the rail.  Ripped the other way, the way a picture rail
  usually is, the same motion slides the two faces apart.

The rise is 1.2, not 1.  A 45 degree mating face is a 45 degree overhang
for whoever has to print the socket side of it, and this is that side: the
pot prints mouth up, so the pocket's ceiling is a roof.  A steeper rip
prints with margin, wedges harder on the way down, and restrains the
tipping just the same - the restraint works for any rise above zero.

How thick the back has to be
----------------------------
The pocket is the rail's thickness deep, so the back needs that plus a
skin.  Making the **whole** back that thick is most of a kilo of plastic
for nothing, so it is only thick where the pocket is: a pad on the inside
of the back wall, ramped underneath so it prints, and nowhere else.

What it weighs
--------------
This is the one thing here that does not have to be asked for.  The pot's
own cavity says how much soil goes in it, and wet potting mix has a
density, so the load and the moment are **derived** rather than guessed -
including where the soil's centre of mass sits, which is what the moment
is actually about.  The numbers come out small: a wall pot's own back is
never what limits it.  The rail in bending between its screws is, and after
that it is the wall.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _finish, drainage_positions, lathe
from .hanger import (_CLEAT_BODY, _CLEAT_FIT, _CLEAT_RISE, _CLEAT_T, _G,
                     _NOTCH_DROP, _SCREW_INSET, _SIGMA, cleat_solid,
                     cleat_stress)
from .modular import _prism_y
from .params import ParameterError, PotParams
from .profile import Profiles, build_profiles, resample
from .sections import make_section
from .textures import make_texture

PARTS = ("none", "set", "pot", "liner", "cleat")

_BACK_RATIO = 0.92       # derived back plane, as a fraction of the narrowest
_BACK_MIN = 2.0          # ... and the least it must beat the narrowest by
_SKIN = 5.0              # material left behind the pocket
_SIDE_STRIP = 10.0       # back left either side of the pocket, on the wall
_LIP = 18.0              # back carried on above the pocket's top corner
_RAIL_END = 1.5          # air at each end of the rail
_PAD_RAMP = 1.15         # slope under the pad that thickens the back
_PAD_SIDE = 8.0          # pad wider than the pocket, each side
_PAD_OVER = 8.0          # ... and taller than it
_SOIL = 1.2              # g/cm3 of potting mix with water in it
_WATER = 1.0             # ... and of what is in the well
_EXTRA_KG = 1.0          # the plant, and the pot's own plastic
_RAIL_MIN = 55.0

# --- the liner, and the well under it ---------------------------------------
_FIT = 0.6               # slack all round the liner
_SEAT_W = 5.0            # ledge the liner's floor lands on
_WELL_MIN = 8.0          # under this it is a puddle, not a reservoir
_LINER_FLOOR = 2.0
_COLLAR_R = 4.0          # the wick's bore, and the collar that guides it
_COLLAR_T = 1.6
_COLLAR_H = 16.0
_TUBE_R = 8.0            # the fill pipe's bore, and the wall round it
_TUBE_T = 1.6


# ---------------------------------------------------------------------------
# the back plane
# ---------------------------------------------------------------------------
def outer_radius(prof, z: float) -> float:
    """Nominal outside radius, rim included, at ``z``."""
    for (r0, z0), (r1, z1) in zip(prof.outer, prof.outer[1:]):
        if z0 - 1e-9 <= z <= z1 + 1e-9:
            t = (z - z0) / max(z1 - z0, 1e-9)
            return r0 + (r1 - r0) * t
    return prof.outer[-1][0]


def plan(p: PotParams) -> dict:
    """The back, the pocket in it, and the load the soil puts on both."""
    prof = build_profiles(p)
    zs = np.linspace(0.0, p.height, 161)
    radii = np.array([outer_radius(prof, float(z)) for z in zs])
    r_narrow = float(radii.min())
    r_wide = float(max(radii.max(), prof.rim_outer_radius))

    # roundness is quoted where the pot is NARROWEST, and that is not a
    # detail: the back is one plane, so a tapered pot is roundest at the end
    # the plane barely reaches.  Quote it at the widest instead and almost
    # every pot asks for a plane its own foot cannot reach
    want = float(p.wall_pot_round)
    if want > 0.0:
        if not 0.5 <= want < 1.0:
            raise ParameterError(
                "wall_pot_round is the fraction of the circumference left "
                "round where the pot is NARROWEST - 0.5 (half a pot) to "
                "about 0.95, or 0 to take as much as the pot allows")
        x_back = r_narrow * math.cos(math.pi * (1.0 - want))
    else:
        x_back = _BACK_RATIO * r_narrow
    if x_back > r_narrow - _BACK_MIN:
        most = 1.0 - math.acos((r_narrow - _BACK_MIN) / r_narrow) / math.pi
        raise ParameterError(
            f"the back plane sits {x_back:.0f} mm off the axis but the pot is "
            f"only {r_narrow:.0f} mm at its narrowest, so the flat would not "
            f"reach the wall all the way down. This pot can go up to "
            f"wall_pot_round {most:.2f}, or 0 to derive it")

    t_c, d_gap = _CLEAT_T, _CLEAT_T + _CLEAT_FIT
    t_wall = max(2.4, p.wall_thickness)
    t_back = d_gap + _SKIN

    # the pocket, high up: the couple's arm is the pot's own back
    y_nt = p.height - _LIP                       # its ceiling, at the wall
    z_rail = y_nt - _CLEAT_FIT - _CLEAT_BODY     # the rail's bottom edge
    y_nb = z_rail - _NOTCH_DROP                  # the pocket's floor
    if y_nb < 0.35 * p.height:
        raise ParameterError(
            f"a {p.height:.0f} mm pot leaves no back under the cleat to bear "
            f"on the wall - a wall pot wants to be at least "
            f"{(_LIP + _CLEAT_FIT + _CLEAT_BODY + _NOTCH_DROP) / 0.65:.0f} mm "
            f"tall")

    # how wide the flat is where the pocket has to fit inside it
    chord = 2.0 * math.sqrt(
        max(outer_radius(prof, y_nb) ** 2 - x_back ** 2, 0.0))
    room = chord - 2.0 * _SIDE_STRIP
    rail = float(p.wall_pot_rail)
    if rail <= 0.0:
        rail = room - 2.0 * _RAIL_END
    if rail < _RAIL_MIN:
        raise ParameterError(
            f"the flat on the back is only {chord:.0f} mm across here, which "
            f"leaves {max(rail, 0.0):.0f} mm of rail once the pot still has "
            f"something to bear on - flatten the back more (a lower "
            f"wall_pot_round) or use a wider pot")
    w_sock = rail + 2.0 * _RAIL_END
    if w_sock > room + 1e-6:
        raise ParameterError(
            f"a {rail:.0f} mm rail needs a {w_sock:.0f} mm pocket, and this "
            f"back is only {chord:.0f} mm across at the cleat - shorten "
            f"wall_pot_rail to {room - 2 * _RAIL_END:.0f} mm or less")

    # the liner, and the open space under it.  The OUTER never gets a hole -
    # that is the point of it - so the holes, if any, are the liner's, and
    # what falls through them has somewhere to go that is not the wall
    liner = bool(p.wall_pot_liner)
    well = max(0.0, float(p.wall_pot_well)) if liner else 0.0
    if liner and 0.0 < well < _WELL_MIN:
        raise ParameterError(
            f"wall_pot_well under {_WELL_MIN:.0f} mm is a puddle, not a "
            f"reservoir - raise it, or set it to 0 and stand the liner on "
            f"the floor of the pot")
    t_liner = max(0.8, float(p.wall_pot_liner_wall))
    z_seat = prof.floor_top_z + well
    r_seat = _cav_r(prof, z_seat)
    # the well has to reach the back plane, or the ledge closes across the
    # back and the space behind the liner - the fill port, and the only way
    # to see the level - is cut off from the water it is supposed to show
    r_well = max(r_seat - _SEAT_W, x_back - t_wall + 3.0, 6.0)
    if liner and well > 0.0 and r_well > r_seat - 2.0:
        raise ParameterError(
            f"the well would leave a {max(r_seat - r_well, 0.0):.1f} mm "
            f"ledge for the liner to stand on - flatten the back less (a "
            f"higher wall_pot_round), or use a wider pot")
    x_liner = t_back + _FIT                      # the liner's back, off the
    #                                              wall: it registers on the
    #                                              pad rather than on the
    #                                              back wall, which is what
    #                                              keeps it clear of both
    if liner and x_back - x_liner < 8.0:
        raise ParameterError(
            f"the liner's back would sit {x_back - x_liner:.0f} mm from the "
            f"pot's axis, which leaves a crescent rather than a pot - the "
            f"back is cut too flat for a liner to fit behind the cleat's "
            f"pad. Use a rounder wall_pot_round, a wider pot, or turn "
            f"wall_pot_liner off")
    if liner and p.height - z_seat < 40.0:
        raise ParameterError(
            f"a {well:.0f} mm well in a {p.height:.0f} mm pot leaves "
            f"{p.height - z_seat:.0f} mm of liner above it - lower "
            f"wall_pot_well or use a taller pot")

    # what it will weigh: soil in the liner, water in the well, and the two
    # have different densities AND different arms, so they are kept apart
    if liner:
        soil, soil_off = _content(
            p, np.linspace(z_seat + _LINER_FLOOR, p.height, 241),
            lambda z: _cav_r(prof, z) - _FIT - t_liner,
            x_back - x_liner - t_liner)
        # the standpipe and the wick's collar take soil out of the middle
        # of that, and they are not where its centre of mass was
        r_fl = _cav_r(prof, z_seat + _LINER_FLOOR) - _FIT - t_liner
        for on, vol, off in (
                (p.wall_pot_fill,
                 math.pi * (_TUBE_R + _TUBE_T) ** 2
                 * (p.height - z_seat - _LINER_FLOOR) / 1000.0,
                 r_fl * flat_factor(p) - _TUBE_R - _TUBE_T),
                (p.wall_pot_wick,
                 math.pi * (_COLLAR_R + _COLLAR_T) ** 2 * _COLLAR_H / 1000.0,
                 0.0)):
            if on and soil > vol:
                soil_off = (soil * soil_off - vol * off) / (soil - vol)
                soil -= vol
        water, water_off = _content(
            p, np.linspace(prof.floor_top_z, z_seat, 81),
            lambda z: r_well, x_back - t_wall) if well else (0.0, 0.0)
    else:
        soil, soil_off = soil_and_centre(p, prof, x_back - t_wall, w_sock)
        water, water_off = 0.0, 0.0
    m_soil, m_water = soil * _SOIL, water * _WATER      # grams
    m_extra = _EXTRA_KG * 1000.0                        # the plant, and PLA
    load = (m_soil + m_water + m_extra) / 1000.0        # kg
    # the plant and the plastic ride with the soil
    reach = x_back + ((m_soil + m_extra) * soil_off
                      + m_water * water_off) / (m_soil + m_water + m_extra)
    weight = load * _G
    moment = weight * reach

    arm = (y_nt + 0.5 * _CLEAT_RISE * t_c) - 0.5 * y_nb
    pull = moment / arm

    n_screw = int(p.wall_pot_screws)
    if n_screw <= 0:
        n_screw = 2
        while n_screw < 8 and cleat_stress(pull, rail, n_screw) > _SIGMA:
            n_screw += 1
    elif n_screw < 2:
        raise ParameterError("wall_pot_screws should be 2 or more, or 0 to "
                             "let the pull-out decide")
    span = (rail - 2.0 * _SCREW_INSET) / max(n_screw - 1, 1)
    bore = 0.5 * float(p.wall_pot_screw_bore)
    head = bore + 2.25

    return dict(prof=prof, x_back=x_back, r_narrow=r_narrow, r_wide=r_wide,
                t_c=t_c, d_gap=d_gap, t_wall=t_wall, t_back=t_back,
                y_nt=y_nt, z_rail=z_rail, y_nb=y_nb, chord=chord,
                rail=rail, w_sock=w_sock, soil=soil, water=water,
                reach=reach, load=load, weight=weight, moment=moment,
                arm=arm, pull=pull, n_screw=n_screw, span=span, bore=bore,
                head=head, liner=liner, well=well, z_seat=z_seat,
                r_seat=r_seat, r_well=r_well, t_liner=t_liner,
                x_liner=x_liner)


def flat_factor(p: PotParams) -> float:
    """How far a polygon's flats sit in, as a fraction of its corners.

    The cavity's polyline is a **corner** radius.  Stand a standpipe or a
    drainage hole at that distance from the axis on a square pot and it
    comes straight out through the middle of a flat.
    """
    if p.pot_style in ("hexagonal", "square", "low_poly_faceted"):
        return math.cos(math.pi / p.sides)
    return 1.0


def _cav_r(prof, z: float) -> float:
    """The pot's own cavity radius at ``z``, off its polyline."""
    return float(np.interp(z, [zz for _, zz in prof.inner],
                           [rr for rr, _ in prof.inner]))


def _content(p: PotParams, zs, radius, d: float) -> tuple[float, float]:
    """Millilitres of whatever fills a flat-backed solid of revolution, and
    how far its centre of mass sits from the AXIS.

    Exact: every disc is a circle with a segment sliced off it by the back
    plane, and both the area and its first moment have closed forms.
    """
    area = np.empty_like(zs)
    mom = np.empty_like(zs)
    for i, z in enumerate(zs):
        area[i], mom[i] = _slice(float(radius(float(z))), d)
    vol = float(np.trapezoid(area, zs))
    if vol <= 0.0:
        return 0.0, 0.0
    return vol / 1000.0, float(np.trapezoid(mom, zs)) / vol


def roundness(p: PotParams, z: float) -> float:
    """Fraction of the pot's circumference still round at height ``z``."""
    k = plan(p)
    r = outer_radius(k["prof"], z)
    if r <= k["x_back"]:
        return 1.0
    return 1.0 - math.acos(k["x_back"] / r) / math.pi


# ---------------------------------------------------------------------------
# what it holds, and where the middle of that is
# ---------------------------------------------------------------------------
def _slice(r: float, d: float) -> tuple[float, float]:
    """A disc of radius ``r`` with everything behind a plane ``d`` from its
    centre removed: the area left, and its first moment about the centre.

    Exact, so the load and the moment do not need a mesh to be found - and
    there is a test that says the mesh agrees.
    """
    if d >= r:
        return math.pi * r * r, 0.0
    if d <= -r:
        return 0.0, 0.0
    cut = r * r * math.acos(d / r) - d * math.sqrt(r * r - d * d)
    return math.pi * r * r - cut, (2.0 / 3.0) * (r * r - d * d) ** 1.5


def soil_and_centre(p: PotParams, prof, d: float,
                    w_sock: float) -> tuple[float, float]:
    """Millilitres the flat-backed cavity holds, and how far the middle of
    that sits from the pot's AXIS (positive = out into the room).

    Integrated off the cavity's own polyline rather than off the nominal
    wall, so the fillet at the foot and the overshoot past the rim are both
    accounted for, and the pad that thickens the back is taken back off
    again.  There is a test that says the mesh agrees.
    """
    z0, z1 = prof.floor_top_z, p.height
    zs = np.linspace(z0, z1, 321)
    radii = np.interp(zs, [z for _, z in prof.inner],
                      [r for r, _ in prof.inner])
    area = np.empty_like(zs)
    mom = np.empty_like(zs)
    for i, r in enumerate(radii):
        area[i], mom[i] = _slice(float(r), d)
    vol = float(np.trapezoid(area, zs))
    first = float(np.trapezoid(mom, zs))

    # the pad on the inside of the back wall stands in the soil's way
    dx = _SKIN + _CLEAT_T + _CLEAT_FIT - max(2.4, p.wall_thickness)
    w_pad = w_sock + 2.0 * _PAD_SIDE
    pz0, pz1 = _pad_span(p)
    pad = w_pad * (dx * (pz1 - pz0) - 0.5 * dx * dx * _PAD_RAMP)
    # ... and it sits just inside the back, so it takes soil from the far
    # side of the axis: its own centre is at -(d + dx/2) off the axis
    vol -= pad
    first -= pad * -(d + 0.5 * dx)
    if vol <= 0.0:
        raise ParameterError(
            "the flat back has closed the pot up completely - there is "
            "nothing left inside it to put soil in")
    return vol / 1000.0, first / vol


def stresses(p: PotParams) -> dict:
    """What the mount is working at, in MPa."""
    k = plan(p)
    return dict(
        cleat=cleat_stress(k["pull"], k["rail"], k["n_screw"]),
        # the pot's back above the pocket, pulled off in tension
        hook=k["pull"] / (k["w_sock"] * _SKIN),
        # ... and the two 45-and-a-bit faces bearing on each other: the pull
        # and the weight both press on them, and the contact is the bevel's
        # slant, which is longer than its run by hypot(1, rise)
        bevel=(_CLEAT_RISE * k["pull"] + k["weight"])
        / (k["w_sock"] * k["t_c"] * (1.0 + _CLEAT_RISE ** 2)))


def governs(p: PotParams) -> str:
    s = stresses(p)
    return max(s, key=s.get)


def _liner_notes(p: PotParams, k: dict) -> list[str]:
    """What the liner and the well do, and what they cannot do."""
    out: list[str] = []
    holes = p.drainage_pattern != "none" and p.drainage_hole_radius > 0
    out.append(
        f"the OUTER has no holes in it at all - that is the whole point of "
        f"the liner. Everything that would put one there lives in the thin "
        f"pot that drops in instead, and it stands "
        f"{k['well']:.0f} mm clear of the floor on a "
        f"{k['r_seat'] - k['r_well']:.1f} mm ledge")
    if k["well"] <= 0.0:
        out.append(
            "wall_pot_well 0 stands the liner on the floor of the pot: "
            "nothing drains anywhere and its holes are blocked - raise it "
            "unless this is only ever going to be a dry arrangement")
        return out
    out.append(
        f"the well under it holds about {k['water']:.0f} ml"
        + (f", and the liner's {len(liner_hole_sites(p, _liner_floor_r(p)))} "
           f"holes are what get water down to it"
           if holes else
        ", but the liner has no holes, so nothing you pour on the soil can "
        "reach it - set a drainage_pattern, or fill the well through the "
        "standpipe"))
    if p.wall_pot_fill:
        out.append(
            f"the standpipe fills the well without wetting the soil, and "
            f"the water standing in it IS the level - stop when it is up. "
            f"There is no overflow anywhere (that would be a hole in the "
            f"outside), so {k['water']:.0f} ml is also all it can take "
            f"before the liner is standing in it")
    else:
        out.append(
            f"there is no standpipe, so the well fills through the soil and "
            f"you cannot see the level - and there is no overflow either, "
            f"so {k['water']:.0f} ml is all it takes before the liner is "
            f"standing in it. Lift the liner out to tip it")
    if p.wall_pot_wick:
        out.append(
            "thread a cord down the collar in the middle of the liner's "
            "floor and let it hang in the well: that is what makes this "
            "self-watering rather than just a pot with a drip tray under "
            "it. Polyester or nylon - cotton rots")
    elif holes:
        out.append(
            "wall_pot_wick is off, so the well is a drip tray: it catches "
            "what runs through and nothing brings it back up")
    return out


def _liner_floor_r(p: PotParams) -> float:
    k = plan(p)
    return (_cav_r(k["prof"], k["z_seat"] + _LINER_FLOOR) - _FIT
            - k["t_liner"])


def check_wall_pot(p: PotParams) -> list[str]:
    out: list[str] = []
    if p.wall_pot not in PARTS:
        raise ParameterError(
            f"unknown wall_pot {p.wall_pot!r}; choose from {list(PARTS)[1:]}")
    if p.wall_pot == "none":
        return out
    k = plan(p)
    if p.wall_pot == "liner" and not k["liner"]:
        raise ParameterError(
            "wall_pot 'liner' needs wall_pot_liner on - it is the thin pot "
            "that drops inside, and you have turned it off")
    if p.num_side_holes > 0:
        raise ParameterError(
            "num_side_holes would put ports through the OUTER pot's wall, "
            "which is the one thing a wall pot must not have - and half of "
            "them would come out on the flat back. Put the drainage in the "
            "liner instead (drainage_pattern)")
    s = stresses(p)
    if max(s.values()) > _SIGMA + 1e-6:
        raise ParameterError(
            f"the mount works the {governs(p)} to {max(s.values()):.1f} MPa "
            f"against a {_SIGMA:.0f} MPa working stress - put wall_pot_screws "
            f"back to 0 and let the pull-out choose it, or use a smaller pot")
    if k["span"] < 2.0 * k["head"] + 6.0:
        raise ParameterError(
            f"{k['n_screw']} screws do not fit along a {k['rail']:.0f} mm "
            f"rail - widen the pot, or flatten its back further")
    out.append(
        f"the back is one plane {2 * k['x_back']:.0f} mm across the pot, so "
        f"it comes out {100 * roundness(p, 0.0):.0f}% round at the foot and "
        f"{100 * roundness(p, p.height):.0f}% at the mouth - one plane, two "
        f"numbers, because the pot is not the same width all the way up. The "
        f"cleat is a pocket inside that flat: hung, none of the mount shows")
    out.append(
        f"it holds about {k['soil']:.0f} ml of soil"
        + (f" and {k['water']:.0f} ml of water" if k["water"] else "")
        + f", so full and watered it is around {k['load']:.1f} kg with its "
        f"middle {k['reach']:.0f} mm off the wall - "
        f"{k['moment'] / 1000.0:.1f} N.m at the fixing. Nothing was asked "
        f"for there: the cavity says how much goes in it, and wet mix and "
        f"water both have a density")
    out.append(
        f"the couple is {k['pull']:.0f} N: the flat back pushes that into "
        f"the wall low down and the cleat's bevel holds it out up top. Worst "
        f"section is the {governs(p)} at {max(s.values()):.2f} MPa - the "
        f"pot's own back is never what limits this")
    out.append(
        f"{k['n_screw']} countersunk screws at {k['span']:.0f} mm centres, "
        f"{2 * k['bore']:.1f} mm shank, hidden behind the pot. That is the "
        f"one part this generator does not make - put them in a stud, or in "
        f"a plasterboard fixing rated well past "
        f"{k['pull']:.0f} N out and {k['weight']:.0f} N down")
    out.append(
        f"the rail's bevel rises {_CLEAT_RISE:.1f} in 1 AWAY from the wall, "
        f"which is the whole mount: tipped the way a full pot tips it, the "
        f"pocket drives into the rail instead of off it. Lift the pot "
        f"{_CLEAT_RISE * k['d_gap']:.0f} mm to take it down again")
    out.append(
        "print the pot standing up as usual and the rail FACE DOWN - the "
        "pocket's roof and the rail's bevel are the same 40 deg face seen "
        "from either side, and both print with nothing under them")
    if k["liner"]:
        out += _liner_notes(p, k)
    elif p.drainage_pattern != "none":
        out.append(
            "a wall pot with drainage holes waters the wall - turn "
            "wall_pot_liner back on, or use --drainage-pattern none and "
            "water it carefully")
    if p.vase_profile != "none":
        out.append(
            f"the {p.vase_profile!r} curve is narrowest at the foot, so the "
            f"flat back is a tall wedge rather than a rectangle - it still "
            f"bears, but check the render before you print an hour of it")
    return out


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
def _back_box(k: dict, p: PotParams, x_face: float) -> trimesh.Trimesh:
    """Everything behind the plane ``x_face``, as a solid to cut away."""
    big = 4.0 * k["r_wide"] + 40.0
    box = trimesh.creation.box(extents=(big, big, 4.0 * p.height + 40.0))
    box.apply_translation((-k["x_back"] + x_face - 0.5 * big, 0.0, 0.0))
    return box


def socket_cutter(p: PotParams) -> trimesh.Trimesh:
    """The pocket the rail goes into: open toward the wall, with a ceiling
    that climbs away from it."""
    k = plan(p)
    x0 = -k["x_back"] - 1.0
    x1 = -k["x_back"] + k["d_gap"]
    return _prism_y([(x0, k["y_nb"]), (x1, k["y_nb"]),
                     (x1, k["y_nt"] + _CLEAT_RISE * k["d_gap"]),
                     (x0, k["y_nt"] - _CLEAT_RISE)],
                    -0.5 * k["w_sock"], 0.5 * k["w_sock"])


def _pad_span(p: PotParams) -> tuple[float, float]:
    """Bottom and top of the pad that thickens the back, in z."""
    y_nt = p.height - _LIP
    y_nb = y_nt - _CLEAT_FIT - _CLEAT_BODY - _NOTCH_DROP
    return (y_nb - _PAD_OVER,
            y_nt + _CLEAT_RISE * (_CLEAT_T + _CLEAT_FIT) + _PAD_OVER)


def back_pad(p: PotParams) -> trimesh.Trimesh:
    """The only thick part of the back: a pad inside it, behind the pocket.

    Ramped underneath, because a slab hung on the inside of a wall that
    prints standing up is a ceiling everywhere else.
    """
    k = plan(p)
    x_in = -k["x_back"] + k["t_wall"]
    x_out = -k["x_back"] + k["t_back"]
    z0, z1 = _pad_span(p)
    half = 0.5 * k["w_sock"] + _PAD_SIDE
    return _prism_y([(x_in, z0),
                     (x_out, z0 + (k["t_back"] - k["t_wall"]) * _PAD_RAMP),
                     (x_out, z1), (x_in, z1)], -half, half)


def outer_cavity_rings(p: PotParams, k: dict) -> list[tuple[float, float]]:
    """The outer's inside, as a **step**: a narrow well at the bottom, the
    liner's space above it, and the ledge between the two.

    Going up, this cavity only ever gets wider - well, then ledge, then the
    pot's own taper - so the step faces the sky and the whole inside prints
    as wall.  It is the cavities that narrow going up that need a cone.
    """
    prof = k["prof"]
    if not k["liner"] or k["well"] <= 0.0:
        return prof.inner
    z = k["z_seat"]
    return ([(k["r_well"], prof.floor_top_z), (k["r_well"], z),
             (k["r_seat"], z)]
            + [(r, zz) for r, zz in prof.inner if zz > z + 1e-6])


def cavity_solid(p: PotParams) -> trimesh.Trimesh:
    """The void inside the outer pot: the well, the liner's space, the gap
    behind it and the fill port, all as one solid."""
    k = plan(p)
    q = p.with_(wall_pot="none", generate_saucer=False)
    section = make_section(q)
    prof = build_profiles(q)
    section.freeze_z = prof.decoration_freeze_z
    cav = lathe(resample(outer_cavity_rings(p, k), q.vertical_step,
                         section.extra_ring_heights(prof.floor_top_z,
                                                    q.height),
                         section.smooth_vertically()), section, decorate=False)
    cav = _boolean("difference", [cav, _back_box(k, q, k["t_wall"])])
    cav = _boolean("difference", [cav, back_pad(p)])
    top = trimesh.creation.box(extents=(900.0, 900.0, 900.0))
    top.apply_translation((0.0, 0.0, p.height + 450.0))
    cav = _boolean("difference", [cav, top])
    cav.apply_translation((k["x_back"], 0.0, 0.0))
    return cav


def well_millilitres(p: PotParams) -> float:
    return plan(p)["water"]


def liner_millilitres(p: PotParams) -> float:
    return plan(p)["soil"]


def _liner_section(p: PotParams):
    """The liner is cut with the pot's OWN cross-section, so a hexagonal
    pot gets a hexagonal liner that actually goes into it."""
    q = p.with_(wall_pot="none", surface_texture="none")
    section = make_section(q)
    section.freeze_z = build_profiles(q).decoration_freeze_z
    return section


def build_wall_liner(p: PotParams) -> trimesh.Trimesh:
    """The thin pot that drops into the wall pot.

    Everything that would put a hole in the outside of the thing on your
    wall lives in here instead: the drainage, and the wick.  It lands on
    the ledge, and what is under it is the well.
    """
    check_wall_pot(p)
    k = plan(p)
    if not k["liner"]:
        raise ParameterError(
            "wall_pot_liner is off, so there is no liner to write - turn it "
            "on, or ask for the pot on its own")
    prof, section = k["prof"], _liner_section(p)
    t, fit = k["t_liner"], _FIT
    z0, z1 = k["z_seat"], p.height
    smooth = section.smooth_vertically()

    budget = math.tan(math.radians(p.overhang_limit_deg)) - 0.12

    def rings(shrink: float, base: float) -> list[tuple[float, float]]:
        zs = sorted(set([base] + [z for _, z in prof.inner if base < z < z1]
                        + [z1]))
        out: list[tuple[float, float]] = []
        for z in zs:
            r = _cav_r(prof, z) - shrink
            if out:                      # never flare faster than it prints
                r = min(r, out[-1][0] + budget * (z - out[-1][1]))
            out.append((r, z))
        return out

    body = lathe(resample(rings(fit, z0), p.vertical_step,
                          section.extra_ring_heights(z0, z1), smooth),
                 section, decorate=False)
    hollow = lathe(resample(rings(fit + t, z0 + _LINER_FLOOR),
                            p.vertical_step,
                            section.extra_ring_heights(z0, z1 + 2.0), smooth),
                   section, decorate=False)
    liner = _boolean("difference", [body, hollow])
    # the same flat back, set by the PAD rather than the wall: that is what
    # keeps the liner clear of the thick part and leaves the gap behind it
    liner = _boolean("difference", [liner, _back_box(k, p, k["x_liner"])])

    floor_z = z0 + _LINER_FLOOR
    r_floor = _cav_r(prof, floor_z) - fit - t
    if p.wall_pot_fill:
        # a standpipe, up the inside of the liner and through its floor.
        # This is the only honest place for a fill port: the outer's back is
        # all pocket and skin, and a flute down it would break into the
        # cleat.  Here it is a plain vertical tube - it prints as wall, it
        # fills the well without wetting the soil, and the water standing in
        # it IS the level in the reservoir
        x = fill_tube_centre(p, r_floor)
        # it starts on the liner's own floor, not below it: a pipe hanging
        # past the bottom would stand the liner off the bed and turn its
        # whole floor into a ceiling
        pipe = lathe([(_TUBE_R + _TUBE_T, z0), (_TUBE_R + _TUBE_T, z1)],
                     _round_section(p), decorate=False)
        pipe.apply_translation((x[0], x[1], 0.0))
        liner = _boolean("union", [liner, pipe])
    if p.wall_pot_wick:
        collar = lathe([(_COLLAR_R + _COLLAR_T, floor_z - 1.0),
                        (_COLLAR_R + _COLLAR_T, floor_z + _COLLAR_H)],
                       _round_section(p), decorate=False)
        liner = _boolean("union", [liner, collar])

    cuts = []
    for x, y in liner_hole_sites(p, r_floor):
        cyl = trimesh.creation.cylinder(radius=p.drainage_hole_radius,
                                        height=4.0 * _LINER_FLOOR,
                                        sections=max(24, p.segments // 4))
        cyl.apply_translation((x, y, floor_z))
        cuts.append(cyl)
    if p.wall_pot_wick:
        bore = trimesh.creation.cylinder(radius=_COLLAR_R,
                                         height=4.0 * (_COLLAR_H + z1),
                                         sections=48)
        bore.apply_translation((0.0, 0.0, floor_z))
        cuts.append(bore)
    if p.wall_pot_fill:
        x = fill_tube_centre(p, r_floor)
        bore = trimesh.creation.cylinder(radius=_TUBE_R, height=4.0 * z1,
                                         sections=48)
        bore.apply_translation((x[0], x[1], 0.5 * z1))
        cuts.append(bore)
    if cuts:
        liner = _boolean("difference", [liner] + cuts)
    liner.apply_translation((k["x_back"], 0.0, 0.0))
    return _finish(liner, center=False)


def _round_section(p: PotParams):
    return make_section(p.with_(wall_pot="none", pot_style="classic_tapered",
                                surface_texture="none"))


def fill_tube_centre(p: PotParams, r_floor: float) -> tuple[float, float]:
    """Where the standpipe stands: against the liner's wall at the FRONT.

    The front is the one azimuth guaranteed to be clear of the flat back
    however flat that back is cut, and it is where you can see down it.
    The radius is the inscribed one, so it stays inside a polygon's flats.
    """
    return (r_floor * flat_factor(p) - _TUBE_R - _TUBE_T, 0.0)


def liner_hole_sites(p: PotParams, r_floor: float) -> list[tuple[float, float]]:
    """Where the liner's drainage goes - the pot's own drainage parameters,
    pointed at the liner instead, and anything that would fall outside the
    flat back or into the wick's collar dropped."""
    k = plan(p)
    if p.drainage_pattern == "none" or p.drainage_hole_radius <= 0:
        return []
    inscribed = r_floor * flat_factor(p)
    shim = Profiles(outer=[], inner=[], rim_outer_radius=inscribed,
                    floor_top_z=0.0, cavity_floor_radius=inscribed,
                    decoration_freeze_z=float("inf"))
    keep = []
    back = -(k["x_back"] - k["x_liner"] - k["t_liner"])
    for x, y in drainage_positions(p, shim):
        if x < back + p.drainage_hole_radius + 1.5:
            continue                              # behind the flat back
        if p.wall_pot_wick and math.hypot(x, y) < (_COLLAR_R + _COLLAR_T
                                                   + p.drainage_hole_radius
                                                   + 1.5):
            continue                              # inside the wick's collar
        if p.wall_pot_fill:
            cx, cy = fill_tube_centre(p, r_floor)
            if math.hypot(x - cx, y - cy) < (_TUBE_R + _TUBE_T
                                             + p.drainage_hole_radius + 1.5):
                continue                          # under the standpipe
        keep.append((x, y))
    return keep


def seated_liner(p: PotParams) -> trimesh.Trimesh:
    """The liner where it sits, on the ledge."""
    liner = build_wall_liner(p)
    liner.apply_translation((0.0, 0.0, plan(p)["z_seat"]))
    return liner


def build_wall_pot(p: PotParams) -> trimesh.Trimesh:
    """The pot, flat-backed, with the cleat's pocket inside its back."""
    check_wall_pot(p)
    k = plan(p)
    q = p.with_(wall_pot="none", generate_saucer=False)
    section = make_section(q)
    prof = build_profiles(q)
    section.freeze_z = prof.decoration_freeze_z
    section.texture = make_texture(q, prof, section)
    step = q.vertical_step
    if section.texture is not None:
        step = min(step, q.texture_cell / 12.0)
    smooth = section.smooth_vertically()

    body = lathe(resample(prof.outer, step,
                          section.extra_ring_heights(0.0, q.height), smooth),
                 section, decorate=True)
    cavity = lathe(resample(outer_cavity_rings(p, k), q.vertical_step,
                            section.extra_ring_heights(prof.floor_top_z,
                                                       q.height), smooth),
                   section, decorate=False)

    # two planes and a pocket: that is the whole difference from a pot
    body = _boolean("difference", [body, _back_box(k, q, 0.0)])
    cavity = _boolean("difference", [cavity, _back_box(k, q, k["t_wall"])])
    cavity = _boolean("difference", [cavity, back_pad(p)])

    pot = _boolean("difference", [body, cavity])
    cutters = [socket_cutter(p)]
    if not k["liner"]:
        # no liner, so the pot itself is what the plant lives in and its own
        # drainage applies - with a warning about where it goes.  Anything
        # the back plane would clip is dropped: half a hole leaves a flat
        # roof over the other half, which is an overhang and a nuisance
        back = -(k["x_back"] - k["t_wall"])
        for x, y in drainage_positions(q, prof):
            if x < back + p.drainage_hole_radius + 1.5:
                continue
            cyl = trimesh.creation.cylinder(
                radius=p.drainage_hole_radius, height=4.0 * prof.floor_top_z
                + 16.0, sections=max(24, p.segments // 4))
            cyl.apply_translation((x, y, prof.floor_top_z))
            cutters.append(cyl)
    pot = _boolean("difference", [pot] + cutters)
    pot.apply_translation((k["x_back"], 0.0, 0.0))    # the wall at x = 0
    return _finish(pot, center=False)


def build_wall_cleat(p: PotParams) -> trimesh.Trimesh:
    """The rail that screws to the wall.  Prints FACE DOWN."""
    check_wall_pot(p)
    k = plan(p)
    return cleat_solid(make_section(p.with_(pot_style="classic_tapered",
                                            surface_texture="none")),
                       k["rail"], k["n_screw"], k["span"], k["bore"],
                       k["head"])


def seated_cleat(p: PotParams) -> trimesh.Trimesh:
    """The rail on the wall, in the pot's own coordinates (x = 0 is wall)."""
    k = plan(p)
    m = np.eye(4)
    m[:3, :3] = np.array([[0, 0, -1], [-1, 0, 0], [0, 1, 0]], dtype=float)
    m[:3, 3] = (k["t_c"], 0.0, k["z_rail"])
    rail = build_wall_cleat(p)
    rail.apply_transform(m)
    return rail


def assembled(p: PotParams) -> trimesh.Trimesh:
    parts = [build_wall_pot(p), seated_cleat(p)]
    if plan(p)["liner"]:
        parts.append(seated_liner(p))
    return trimesh.util.concatenate(parts)
