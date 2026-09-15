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

from .build import (_boolean, _finish, drainage_cutters, lathe,
                    side_drainage_cutters)
from .hanger import (_CLEAT_BODY, _CLEAT_FIT, _CLEAT_RISE, _CLEAT_T, _G,
                     _NOTCH_DROP, _SCREW_INSET, _SIGMA, cleat_solid,
                     cleat_stress)
from .modular import _prism_y
from .params import ParameterError, PotParams
from .profile import build_profiles, resample
from .sections import make_section
from .textures import make_texture

PARTS = ("none", "set", "pot", "cleat")

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
_EXTRA_KG = 1.0          # the plant, and the pot's own plastic
_RAIL_MIN = 55.0


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

    # the soil, and where its middle is: that is what the moment is about
    soil, off_axis = soil_and_centre(p, prof, x_back - t_wall, w_sock)
    reach = x_back + off_axis
    load = soil * _SOIL / 1000.0 + _EXTRA_KG     # kg
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
                rail=rail, w_sock=w_sock, soil=soil, reach=reach, load=load,
                weight=weight, moment=moment, arm=arm, pull=pull,
                n_screw=n_screw, span=span, bore=bore, head=head)


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


def check_wall_pot(p: PotParams) -> list[str]:
    out: list[str] = []
    if p.wall_pot not in PARTS:
        raise ParameterError(
            f"unknown wall_pot {p.wall_pot!r}; choose from {list(PARTS)[1:]}")
    if p.wall_pot == "none":
        return out
    k = plan(p)
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
        f"it holds about {k['soil']:.0f} ml of soil, so full and watered it "
        f"is around {k['load']:.1f} kg with its middle {k['reach']:.0f} mm "
        f"off the wall - {k['moment'] / 1000.0:.1f} N.m at the fixing. "
        f"Nothing was asked for there: the cavity says how much goes in it "
        f"and wet mix has a density")
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
    if p.drainage_pattern != "none":
        out.append(
            "a wall pot with drainage holes waters the wall - use "
            "--drainage-pattern none and water it carefully, or hang it "
            "somewhere a drip does not matter")
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
    cavity = lathe(resample(prof.inner, q.vertical_step,
                            section.extra_ring_heights(prof.floor_top_z,
                                                       q.height), smooth),
                   section, decorate=False)

    # two planes and a pocket: that is the whole difference from a pot
    body = _boolean("difference", [body, _back_box(k, q, 0.0)])
    cavity = _boolean("difference", [cavity, _back_box(k, q, k["t_wall"])])
    cavity = _boolean("difference", [cavity, back_pad(p)])

    pot = _boolean("difference", [body, cavity])
    cutters = ([socket_cutter(p)]
               + drainage_cutters(q, prof) + side_drainage_cutters(q, prof))
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
    return trimesh.util.concatenate([build_wall_pot(p), seated_cleat(p)])
