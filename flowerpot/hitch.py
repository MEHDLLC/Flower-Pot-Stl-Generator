"""Trailer-hitch ball mount: a sliced socket that snaps over the ball.

The socket is a spherical cup cut off *below* the ball's equator, so its
mouth is narrower than the widest part of the ball.  Slots up the side turn
the wall into fingers; push the socket down and the fingers spread as the
equator goes past, then close under it.  Nothing to tighten, nothing to
lose, and it comes off with a firm pull.

Three numbers decide whether that works, and all three are solved for
rather than guessed at:

* **The undercut** ``hitch_grip`` - how much narrower the mouth is than the
  ball.  It is the whole retention, and it is also exactly how far each
  finger has to bend, so it sets the next number.
* **The slot length.**  A finger is a cantilever: bending its tip by the
  undercut strains its outer fibre by ``3*t*d / (2*L^2)``.  Short fingers
  snap.  The slots are therefore sized *from* the strain target, not from
  looks - see :func:`spring_strain`.  The finger is printed standing up, so
  that strain is pulling across layer lines, which is the weak direction:
  the target is set well under what a layer bond will take.
* **Where the cavity stops being a sphere.**  A sphere's roof is flat at
  the top and no printer will bridge it.  Above the latitude where the
  ball's own surface reaches the overhang limit, the cavity leaves the
  sphere on the tangent and closes as a cone - which is both printable and
  the *smallest* enclosure that still clears the ball.

Everything below the ball's equator is free: there the cavity widens as it
rises, and a cavity that widens upward hangs over nothing.

.. warning::
   A hitch ornament is for a parked vehicle.  Take it off before towing -
   it is in the way of the coupler and it is not a structural part.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _finish, _prism, lathe
from .params import ParameterError, PotParams
from .profile import slope_budget
from .sections import Section

#: Standard trailer-ball diameters, in millimetres.  ``hitch_ball`` takes
#: one of these keys or a plain number.
BALL_SIZES: dict[str, float] = {
    "1-7/8": 47.63,
    "2": 50.80,
    "2-5/16": 58.74,
    "3": 76.20,
}

_CLEAR = 0.30        # radial clearance above the ball's equator
_PRESS = 0.12        # radial squeeze below it - takes the rattle out
_ENTRY = 1.0         # lead-in chamfer at the mouth, radial ...
_ENTRY_RISE = 1.25   # ... and its rise per mm of that (a 51 deg lead)
_RESERVE = 0.10      # overhang budget held back on the cavity's cone

_SLOT_HALF = 1.05    # half the slot width at the mouth, tangential
_SLOT_RELIEF = 1.9   # ... widening to this at the root, as a stress relief
_SLOT_PEAK = 1.35    # gable over the relief, as a multiple of its half width
_SLOT_MARGIN = 6.0   # slot must run this far past the equator to free it

_STRAIN = 0.012      # peak bending strain a splayed finger may see
_SKIRT = 3.0         # flare at the very bottom, for bed contact
_SKIRT_RUN = 0.85    # ... its dr/dz, kept under the overhang limit
_TIP = 7.0           # round-off on the outside of the dome's point

_THREAD_PITCH = 5.0
_THREAD_DEPTH = 1.1
_THREAD_CLEAR = 0.3
_THREAD_RUN = 9.0    # engagement
_CAP_WALL = 3.2


# ---------------------------------------------------------------------------
# sizing
# ---------------------------------------------------------------------------
def ball_diameter(p: PotParams) -> float:
    """The ball this mount is cut for, in mm.

    The value can arrive from a workflow form, so strip stray quotes: a
    shell that word-splits its arguments hands over ``'"2"'`` rather than
    ``'2'``, and rejecting that is technically right and completely useless.
    """
    key = str(p.hitch_ball).strip().strip("\"'").strip()
    if key in BALL_SIZES:
        return BALL_SIZES[key]
    try:
        d = float(key)
    except ValueError:
        raise ParameterError(
            f"unknown hitch_ball {p.hitch_ball!r}; use one of "
            f"{list(BALL_SIZES)} or a diameter in mm"
        ) from None
    if not 30.0 <= d <= 120.0:
        raise ParameterError(
            f"hitch_ball {d} mm is outside 30-120 mm; standard balls are "
            f"{list(BALL_SIZES)}"
        )
    return d


def wall(p: PotParams) -> float:
    """Socket wall thickness - it is the spring, so it has a floor."""
    return max(3.2, p.wall_thickness)


def solve(p: PotParams) -> dict:
    """Every height and radius the socket is built from.

    Heights are measured from the mouth, which is the build plate.
    """
    d = ball_diameter(p)
    r_ball = 0.5 * d
    g = float(p.hitch_grip)
    if g <= 0.0 or g >= 0.35 * r_ball:
        raise ParameterError(
            f"hitch_grip {g} mm must be between 0 and {0.35 * r_ball:.1f} mm "
            f"for a {d:.1f} mm ball"
        )

    t = wall(p)
    s = slope_budget(p, _RESERVE)            # dr/dz the cavity's roof may use
    z_lip = _ENTRY * _ENTRY_RISE             # top of the lead-in chamfer
    r_mouth = r_ball - g                     # the ring that has to stretch

    # the ball seats where its own surface is r_mouth wide
    z_ball = z_lip + math.sqrt(max(2.0 * r_ball * g - g * g, 1e-9))
    rho = r_ball + _CLEAR                    # cavity sphere, above the equator

    # leave the sphere on the tangent, at the latitude where it reaches the
    # budget; the cone from there is the tightest printable lid over a ball
    r_knee = rho / math.hypot(1.0, s)
    z_knee = z_ball + s * r_knee
    z_apex = z_knee + r_knee / s

    # a finger is a cantilever rooted at the top of its slot
    l_strain = math.sqrt(1.5 * t * g / _STRAIN)
    slot = max(l_strain, z_ball + _SLOT_MARGIN)
    slot = min(slot, z_knee)                 # keep a solid ring above them

    return dict(r_ball=r_ball, grip=g, wall=t, slope=s,
                r_mouth=r_mouth, z_lip=z_lip, z_ball=z_ball, rho=rho,
                r_knee=r_knee, z_knee=z_knee, z_apex=z_apex,
                slot=slot, l_strain=l_strain,
                fingers=int(p.hitch_fingers))


def cavity_radius(k: dict, z: float) -> float:
    """Radius of the socket's cavity at height ``z``."""
    if z <= k["z_lip"]:                       # lead-in chamfer
        return k["r_mouth"] + (k["z_lip"] - z) / _ENTRY_RISE
    if z <= k["z_ball"]:                      # squeezed band, under the equator
        u = k["z_ball"] - z
        return math.sqrt(max(k["r_ball"] ** 2 - u * u, 0.0)) - _PRESS
    if z <= k["z_knee"]:                      # clearance sphere, over it
        u = z - k["z_ball"]
        return math.sqrt(max(k["rho"] ** 2 - u * u, 0.0))
    return max(k["r_knee"] - k["slope"] * (z - k["z_knee"]), 0.0)


def spring_strain(p: PotParams) -> float:
    """Peak bending strain in a finger at full splay.

    ``e = 3*t*d / (2*L^2)`` for a cantilever of thickness ``t`` and length
    ``L`` deflected ``d`` at the tip.  The finger prints standing up, so
    this strain pulls across the layer lines.
    """
    k = solve(p)
    return 1.5 * k["wall"] * k["grip"] / (k["slot"] ** 2)


def check_hitch(p: PotParams) -> list[str]:
    """Soft warnings about a mount that will work but not well."""
    out: list[str] = []
    k = solve(p)
    e = spring_strain(p)
    if e > _STRAIN * 1.02:
        out.append(
            f"hitch fingers are strained {100 * e:.1f}% at full splay (target "
            f"{100 * _STRAIN:.1f}%) - the socket is too shallow to grow "
            f"{k['l_strain']:.0f} mm slots. Drop hitch_grip to about "
            f"{_STRAIN * k['slot'] ** 2 / (1.5 * k['wall']):.2f} mm, or print "
            f"it in PETG rather than PLA"
        )
    if k["fingers"] < 3:
        out.append("fewer than three fingers cannot centre on the ball")
    return out


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------
def _round(p: PotParams) -> Section:
    return Section(p.with_(surface_texture="none"))


def _rings(k: dict, z0: float, z1: float, fn, step: float = 0.4
           ) -> list[tuple[float, float]]:
    n = max(2, int(math.ceil((z1 - z0) / step)))
    return [(fn(z0 + (z1 - z0) * i / n), z0 + (z1 - z0) * i / n)
            for i in range(n + 1)]


def cavity_rings(k: dict) -> list[tuple[float, float]]:
    """The void the ball lives in, overshooting the plate at the bottom."""
    lead = 2.0
    rings = [(k["r_mouth"] + (k["z_lip"] + lead) / _ENTRY_RISE, -lead)]
    rings += _rings(k, 0.0, k["z_apex"] - 0.05,
                    lambda z: max(cavity_radius(k, z), 0.05))
    rings.append((0.02, k["z_apex"]))
    return rings


def _tip_circle(r0: float, z0: float, s: float, tip: float
                ) -> tuple[float, float, float]:
    """``(centre z, radius, tangency z)`` of the ball that rounds off a
    cone's point.

    The cone rises from ``(r0, z0)`` at slope ``-s``.  Only *downward*
    facing surfaces need the overhang budget, so the outside of a dome may
    close however it likes - and a point is a spike, not a dome.  Below the
    tangency the cone still rules; above it, the arc.
    """
    a = max(0.5, min(tip, 0.45 * r0))
    h = math.hypot(1.0, s)
    z_o = z0 + r0 / s - a * h / s
    return z_o, a, z_o + a * s / h


def _tipped(r_cone: float, z: float, tip: tuple[float, float, float]) -> float:
    z_o, a, z_t = tip
    if z < z_t:
        return r_cone
    return math.sqrt(max(a * a - (z - z_o) ** 2, 0.0))


def shell_radius(k: dict, z: float, top_flat: float = 0.0,
                 tip: float = 0.0) -> float:
    """Outside of the socket: the cavity's own offset, plus a skirt.

    ``top_flat`` stops the taper at that radius, which is what turns the
    dome into a collar with somewhere to put a thread.
    """
    t = k["wall"]
    if z <= k["z_ball"]:                       # offset sphere under the equator
        u = k["z_ball"] - z
        rho_o = k["r_ball"] + t
        r = math.sqrt(max(rho_o * rho_o - u * u, 0.0))
    elif z <= k["z_knee"]:
        u = z - k["z_ball"]
        rho_o = k["rho"] + t
        r = math.sqrt(max(rho_o * rho_o - u * u, 0.0))
    else:
        # the cone, offset perpendicular: it keeps its slope and moves out
        s = k["slope"]
        r = (k["r_knee"] + t * math.hypot(1.0, s)) - s * (z - k["z_knee"])
    r = max(r, cavity_radius(k, z) + t)        # never thinner than the wall
    if z <= _SKIRT / _SKIRT_RUN:               # flare onto the plate
        r = max(r, cavity_radius(k, 0.0) + t + _SKIRT - _SKIRT_RUN * z)
    r = max(r, top_flat)
    if tip > 0.0:                              # take the point off the dome
        s = k["slope"]
        r0 = k["r_knee"] + t * math.hypot(1.0, s)
        r = _tipped(r, z, _tip_circle(r0, k["z_knee"], s, tip))
    return r


def _slot_cutter(k: dict, azim: float, reach: float) -> trimesh.Trimesh:
    """One radial slot, as a teardrop: narrow at the mouth, widening to a
    relief at the root, gabled over so nothing in it faces down.

    Widening upward costs nothing - the void grows as it rises, so no layer
    is ever laid over air - and it puts the wide part of the slot exactly
    where a bent finger concentrates its stress.  The gable is the only
    surface in here that faces down, and it is steeper than the limit.
    """
    w, wr = _SLOT_HALF, _SLOT_RELIEF
    top = k["slot"]
    z_a = top - _SLOT_PEAK * wr                # shoulders of the gable
    prof = [(-w, -2.0), (w, -2.0), (wr, z_a), (0.0, top), (-wr, z_a)]
    cut = _prism(prof, 0.0, reach)
    cut.apply_transform(
        trimesh.transformations.rotation_matrix(azim, [0, 0, 1]))
    return cut


def socket_parts(p: PotParams, top_flat: float = 0.0, z_top: float = 0.0,
                 tip: float = 0.0
                 ) -> tuple[list[trimesh.Trimesh], list[trimesh.Trimesh]]:
    """``(solids, cutters)`` for a socket standing on the plate.

    ``z_top`` truncates the shell - a collar stops short and lets whatever
    sits on top carry the cavity's cone.  ``0`` means "all the way".
    """
    k = solve(p)
    sec = _round(p)
    hi = z_top or shell_top(k, tip)
    shell = lathe(_rings(k, 0.0, hi - (0.02 if tip else 0.0),
                         lambda z: max(shell_radius(k, z, top_flat, tip),
                                       0.02)),
                  sec, decorate=False)
    reach = max(shell_radius(k, z, top_flat)
                for z in np.linspace(0.0, hi, 40)) + 2.0
    cutters = [lathe(cavity_rings(k), sec, decorate=False)]
    n = k["fingers"]
    cutters += [_slot_cutter(k, 2.0 * math.pi * i / n, reach) for i in range(n)]
    return [shell], cutters


def shell_top(k: dict, tip: float = 0.0) -> float:
    """Where a closed cover's dome finishes."""
    s = k["slope"]
    t = k["wall"]
    if tip <= 0.0:
        return k["z_apex"] + t * math.hypot(1.0, s) / s
    z_o, a, _z_t = _tip_circle(k["r_knee"] + t * math.hypot(1.0, s),
                               k["z_knee"], s, tip)
    return z_o + a


def collar_top(k: dict) -> float:
    """Where an open collar stops: clear of the ball, above the slots."""
    return max(k["slot"] + 2.0, k["z_ball"] + k["r_ball"] * 0.55)


def body_radius(p: PotParams) -> float:
    """Widest the socket's own body gets, ignoring the skirt."""
    k = solve(p)
    return max(shell_radius(k, z)
               for z in np.linspace(_SKIRT / _SKIRT_RUN, collar_top(k), 60))


def thread_core(p: PotParams) -> tuple[float, float, float]:
    """``(core radius, z0, z1)`` of the collar's male thread."""
    k = solve(p)
    z0 = collar_top(k) + 1.0
    z1 = z0 + _THREAD_RUN
    core = max(12.0, cavity_radius(k, z0) + k["wall"],
               cavity_radius(k, z1) + k["wall"])
    return core, z0, z1


def flange_radius(p: PotParams) -> float:
    """Outside of the collar under its shoulder - and of whatever screws on.

    Sized so the two are flush: the joint reads as one object rather than a
    lid perched on a jar.
    """
    core, _z0, _z1 = thread_core(p)
    return max(core + _THREAD_CLEAR + _CAP_WALL, body_radius(p))


# ---------------------------------------------------------------------------
# the parts
# ---------------------------------------------------------------------------
def build_hitch_cover(p: PotParams) -> trimesh.Trimesh:
    """One-piece cover: the socket, domed over."""
    solids, cutters = socket_parts(p, tip=_TIP)
    mesh = _boolean("difference", [solids[0]] + cutters)
    return _finish(mesh, center=False)


def build_hitch_collar(p: PotParams) -> trimesh.Trimesh:
    """The socket on its own, with a thread on top for whatever goes there."""
    from .stem import _thread_mesh
    k = solve(p)
    core, z0, z1 = thread_core(p)
    flange = flange_radius(p)
    sec = _round(p)
    solids, cutters = socket_parts(p, top_flat=flange, z_top=z0)
    boss = lathe([(core, z0 - 0.5), (core, z1)], sec, decorate=False)
    body = _boolean("union", [solids[0], boss,
                              _thread_mesh(p, core, z0, z1,
                                           depth=_THREAD_DEPTH,
                                           pitch=_THREAD_PITCH)])
    # the bore keeps going straight up out of the collar: above the ball
    # there is nothing left to clear, and an open top is one less ceiling
    r_bore = cavity_radius(k, collar_top(k))
    bore = lathe([(r_bore, collar_top(k) - 6.0), (r_bore, z1 + 2.0)],
                 sec, decorate=False)
    return _finish(_boolean("difference", [body] + cutters + [bore]),
                   center=False)


def cap_socket_cutters(p: PotParams, z_face: float
                       ) -> list[trimesh.Trimesh]:
    """The female thread that screws onto :func:`build_hitch_collar`.

    ``z_face`` is where the part's underside sits; the socket is bored up
    from there and closed with a cone, because a flat-topped bore in a part
    printed mouth-down is a ceiling the width of the thread.
    """
    from .stem import _thread_mesh
    k = solve(p)
    core, z0, z1 = thread_core(p)
    run = z1 - z0
    r = core + _THREAD_CLEAR
    z_hi = z_face + run + 1.2
    # the male shape, fattened axially by the clearance: its own body is the
    # bore and its ridge cuts the matching groove, exactly as the stem's
    # socket does.  Same depth as the male thread - clearance is radial (the
    # bore is wider) and axial (the widen), never a steeper flank.
    thread = _thread_mesh(p, r, z_face - 1.0, z_hi, widen=0.075,
                          depth=_THREAD_DEPTH, pitch=_THREAD_PITCH)
    rings = [(r, z_hi - 0.5)]
    rings += _rings(k, z_hi, z_hi + r / k["slope"] - 0.05,
                    lambda z: max(r - k["slope"] * (z - z_hi), 0.05))
    rings.append((0.02, z_hi + r / k["slope"]))
    lid = lathe(rings, _round(p), decorate=False)
    return [_boolean("union", [thread, lid])]


def cap_clear_z(p: PotParams) -> float:
    """How far above its underside a screw-on part is still hollow."""
    k = solve(p)
    core, z0, z1 = thread_core(p)
    r = core + _THREAD_CLEAR
    return (z1 - z0) + 1.2 + r / k["slope"]


def cap_face_z(p: PotParams) -> float:
    """Height of the collar's shoulder - where a cap lands."""
    _core, z0, _z1 = thread_core(p)
    return z0


def build_hitch_cap(p: PotParams) -> trimesh.Trimesh:
    """A plain domed lid for the collar - the stand-in for a flower."""
    k = solve(p)
    skirt = flange_radius(p)
    s_max = k["slope"]
    straight = cap_clear_z(p) - skirt / s_max
    straight = max(straight, (thread_core(p)[2] - thread_core(p)[1]) + 2.0)
    tip = _tip_circle(skirt, straight, s_max, _TIP)
    top = tip[0] + tip[1]
    rings = [(skirt, 0.0), (skirt, straight)]
    rings += _rings(k, straight, top - 0.02,
                    lambda z: max(_tipped(skirt - s_max * (z - straight),
                                          z, tip), 0.02))
    body = lathe(rings, _round(p), decorate=False)
    cap = _boolean("difference", [body] + cap_socket_cutters(p, 0.0))
    return _finish(cap, center=False)
