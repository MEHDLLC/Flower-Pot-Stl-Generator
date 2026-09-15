"""A hanger for a pot, in flat parts - from a ceiling hook or a wall.

Everything else in this generator is held up by the bench.  This is not:
a hanging pot is a **sustained tensile load** on printed plastic, which is
the one thing FDM is worst at, so the whole design is arranged round that.

Print orientation is the design
-------------------------------
A printed part is weakest **across** its layer lines.  An arm printed
standing up is a stack of discs being pulled apart, and it will let go at a
layer bond long before the plastic itself yields.  So every part that
carries load here is a **flat plate, printed lying down**, with the tension
running along the layer lines - in the plane where the material is actually
strong.  The parts are modelled in that orientation, so what you slice is
what you print: lay them on the bed as they come.

That one decision settles the rest of the shape.  A flat plate can only
widen in its own plane, so every hook, notch and shoulder here works in the
plane of the plate and none of them needs the plate to be thicker
anywhere.

The three parts
---------------
* **base** - a spoked ring the pot stands on.  The pot's weight goes into
  the seat, out along the spokes, and into the arms at the pads.
* **arm** - a flat strap, hooked at both ends.  Print ``hanger_arms`` of
  them.
* **top** - the ring they gather at, with whatever you are hanging it from.

Both joints are the same **toggle**: a plain slot through the plate, and a
return on the end of the arm that is longer than the slot.  The arm threads
through - up from under the base, down through the top ring - and its
return lies across the slot and cannot come back.

It goes together because a flat plate tilted over presents a shorter
shadow: tip the arm about fifty degrees and the return passes the slot,
stand it up and it does not.  Hanging, every arm is within a few degrees of
vertical, so nothing can back out while there is a pot on it.  No
fasteners, no open-ended notches for a hook to walk out of, and the top
ring keeps a solid middle to hang from.

The kink, and why the plates stand on edge
------------------------------------------
An arm runs straight up past the pot and only turns in above its rim,
because a straight line from a wide base to a narrow gather would cut
through the pot at its widest point.  That turn is a bend, and a bend has
to be carried by the plate's **depth**, so the plates stand on edge -
radially - rather than wrapping the pot like a strap.  It is the same
reason a shelf bracket is a plate on edge and not a ribbon.

What actually fails
-------------------
Not the arm.  At the loads a pot reaches, the tensile section is enormously
oversized and the sizing is driven by the **spokes in bending** instead -
the generator reports the stress in each and says which one governs.

What does fail is **creep**.  PLA under a permanent load slowly stretches,
and a hanging planter is about as permanent a load as a household part
sees.  Nothing in the geometry fixes that: print it in PETG or PLA+, check
it now and then, and do not hang it over anything that would mind.

Hanging it off a wall instead
-----------------------------
``hanger_mount="wall"`` adds three more flat parts - a **cleat**, a **rib**
(print two) and a **yoke** - that put the same set on a wall rather than a
hook.  A French cleat is a board ripped at 45 degrees, and 45 degrees is
exactly this generator's overhang limit, so the joint that makes a cleat
work is also the one angle that prints with nothing under it.

A wall bracket is a different problem from a ceiling hook, though, and the
difference is what decides the shape:

* A hook carries **tension**.  A bracket carries a **cantilever** - the pot
  hangs ``hanger_reach`` millimetres out from the wall, so the fixing sees a
  moment an order of magnitude larger than anything else here.
* A bare French cleat only resists **shear**.  It has nothing to say about a
  moment, which tries to peel the top of the cleat straight off the wall.
  So each rib's **back edge bears flat on the wall below its notch**, and
  the moment becomes a couple: the back pushes in low down, the notch holds
  out up top.  It is the reason a real French cleat gets a filler strip
  along the bottom, and it is not optional here.
* A shelf bracket is a plate on edge, not a ribbon, for the same reason the
  arms are.  So the reach is carried by two ribs standing on edge, and a
  **yoke** spans between them to hold them parallel and to give the pot one
  point to hang from.

Everything about a rib is outline - the 45 degree hook, the taper, the
yoke's slot are all edges in the plane it prints in - so a rib has no
overhang anywhere by construction.

The rib tapers, because the moment does.  A triangle that runs to a point
is the wrong shape for a load hung at the tip: the section falls away
faster than the moment does, and the worst stress ends up out near the tip
rather than at the wall.  So the rib keeps a tip deep enough for what is
left, and the generator reports where along it the worst section is.

The yoke goes on by **lifting it and sliding a rib onto each end**: the lug
on the end of each tenon hangs below it, so raised it lines up with the
slot and lowered it sits under the slot's floor with the rib in the way.
The capture is across the direction it slides in, which is the only way a
part that can only grow in its own plane can be caught at all.

The screws are the part this generator does not make.  How many there are
is worked out from the pull-out the cantilever produces, but what they go
into is yours: a stud, or a fixing rated for the load in plasterboard.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _finish, _prism, lathe
from .modular import _prism_z
from .params import ParameterError, PotParams
from .sections import Section
from .underpot import nursery_dims

WALL_PARTS = ("cleat", "rib", "yoke")
PARTS = ("none", "set", "base", "arm", "top") + WALL_PARTS
TOPS = ("hole", "slot", "ring")
MOUNTS = ("ceiling", "wall")

_G = 9.80665
_SIGMA = 8.0             # MPa working stress, along the layer lines.  About
#                          a sixth of PLA's short-term tensile strength; the
#                          rest of the margin is creep, warmth and the day
#                          somebody hangs a wetter pot on it.
_SLACK = 1               # arms assumed slack when it swings: n - 1 carry it

_PLATE_MIN = 3.2         # nothing structural thinner than this
_ARM_W_MIN = 15.0        # arm depth (radial), whatever the sums say
_SPOKE_W = 16.0
_SLOT_FIT = 0.45         # slack round the plate in its slot
_GRIP = 9.0              # how far a return reaches past its slot
_RETURN_T = 4.0          # thickness of a return
_TILT_MAX = 65.0         # the most anybody should have to tip an arm to fit it
_STUB = 7.0              # vertical run before the arm meets the top ring

_KINK_UP = 14.0          # the arms turn in this far above the pot's rim
_SEAT_IN = 0.70          # base hole, as a fraction of the pot's base radius
_SEAT_OUT = 6.0          # seat annulus reaching past the pot's base
_SEAT_CHAMFER = 3.0      # ... opening upward, to centre the pot
_TOP_R_MIN = 22.0
_BOSS = 9.0              # solid middle of the top ring

# --- the wall mount ---------------------------------------------------------
_CLEAT_T = 9.0           # rail thickness - and so the stand-off it creates
_CLEAT_BODY = 14.0       # straight part under the bevel; the screws live here
_CLEAT_RISE = 1.2        # how fast the bevel climbs away from the wall.
#                          NOT 1: a 45 deg mating face is a 45 deg overhang
#                          for whatever has to print the socket side of it,
#                          which is exactly the budget with nothing left. A
#                          steeper rip prints (40 deg), wedges harder on the
#                          way down, and holds the same way against tipping -
#                          the restraint works for any rise above zero.
_CLEAT_FIT = 0.5         # slack between the rail and the notch that hooks it
_SCREW_INSET = 8.5       # first screw, in from the end of the rail
_RIB_T_MIN = 4.8         # a rib is on edge and carries half the pot
_RIB_H_MIN = 110.0       # ... and its height is the couple arm, so it is tall
_RIB_H_FACTOR = 2.6      # height, as a multiple of what bending alone asks
_RIB_LIP = 20.0          # rib carried on above the notch's top corner
_RIB_BEAR_MIN = 40.0     # least back edge left bearing flat on the wall
_RIB_WEB = 6.0           # material left round the yoke's slot
_RIB_INSET = 22.0        # ribs, in from the ends of the rail
_NOTCH_DROP = 18.0       # notch taller than the rail, so it hangs easily
_CSK_DEG = 40.0          # countersink half-angle: 45 would be the limit
_SPREAD_MIN = 60.0
_YOKE_D_MIN = 32.0
_YOKE_SHOULDER = 13.0    # yoke deeper than its tenon, so it cannot follow it
_YOKE_LIFT = 6.0         # lift the yoke this much and the lugs line up
_YOKE_OUT = 5.0          # how far a lug stands off the outside of a rib
_EYE_R = 5.0
_RING_CLEAR = 8.0        # air under the bracket, over the top ring
_HOOK = 25.0             # least hook or rope, yoke to top ring
_WALL_CLEAR = 12.0       # least air between the pot and the wall


# ---------------------------------------------------------------------------
# sizing
# ---------------------------------------------------------------------------
def _round(p: PotParams) -> Section:
    return Section(p.with_(pot_style="classic_tapered",
                           surface_texture="none"))


def pot_of(p: PotParams) -> dict:
    return nursery_dims(p.hanger_pot_size, p.hanger_pot_top,
                        p.hanger_pot_base, p.hanger_pot_height, "hanger")


def plan(p: PotParams) -> dict:
    """Every number the three parts are cut from, and the load in each."""
    if p.hanger_top not in TOPS:
        raise ParameterError(
            f"unknown hanger_top {p.hanger_top!r}; choose from {list(TOPS)}")
    pot = pot_of(p)
    n = int(p.hanger_arms)
    if not 3 <= n <= 5:
        raise ParameterError(
            "hanger_arms should be 3-5. Three is what hangs level on its own; "
            "more shares the load but has to be built truer")
    load = float(p.hanger_load)
    if not 0.5 <= load <= 25.0:
        raise ParameterError(
            "hanger_load should be 0.5-25 kg - the weight of the pot, its "
            "soil and the water in it, at its heaviest")
    clear = max(3.0, float(p.hanger_clearance))
    drop = float(p.hanger_drop)

    weight = load * _G                       # newtons, all in
    # one arm is assumed slack: a hanger that has swung is carrying on the
    # others, and that is the case worth sizing for
    pull = weight / max(n - _SLACK, 1)

    z_kink = pot["height"] + _KINK_UP
    if drop <= z_kink + 40.0:
        raise ParameterError(
            f"hanger_drop {drop:.0f} mm leaves nothing above the pot for the "
            f"arms to gather in - it needs at least {z_kink + 40.0:.0f} mm "
            f"for a {pot['height']:.0f} mm pot")

    # the arm: tension along its length, on a section that is width x plate
    t_arm = max(_PLATE_MIN, p.wall_thickness)
    w_arm = max(_ARM_W_MIN, pull / (_SIGMA * t_arm))
    # the clearance is to the arm's INNER EDGE, which is what would touch
    # the pot - its centreline is half a plate further out
    r_arm = pot["top_r"] + clear + 0.5 * w_arm

    # the base: the pot's weight goes out along a spoke to the pad, so the
    # spoke is a cantilever and that is what sets the plate's thickness
    r_seat_in = _SEAT_IN * pot["base_r"]
    r_seat_out = pot["base_r"] + _SEAT_OUT
    r_pad_out = r_arm + 0.5 * w_arm + 6.0
    r_pad_in = r_arm - 0.5 * w_arm - _GRIP
    # the spoke is a cantilever from the seat out to where the arm pulls,
    # which is the arm's own line and not the near edge of its pad
    lever = max(r_arm - r_seat_out, 1.0)
    share = weight / n
    t_base = max(_PLATE_MIN,
                 math.sqrt(6.0 * share * lever / (_SPOKE_W * _SIGMA)))

    # the top ring: the arms pull down at its rim, the hook up at its middle
    r_top = max(_TOP_R_MIN, n * (w_arm + 9.0) / (2.0 * math.pi))
    t_top = max(_PLATE_MIN,
                math.sqrt(6.0 * share * max(r_top - _BOSS, 1.0)
                          / (_SPOKE_W * _SIGMA)))

    # the arm stands vertical again for the last few millimetres, so it
    # goes through the top ring square: an inclined plate through a
    # horizontal slot needs a longer slot, and lands its load at an angle
    z_gather = drop - _STUB
    lean = math.atan2(r_arm - r_top, z_gather - z_kink)

    return dict(lean=lean, z_gather=z_gather,
                pot=pot, n=n, load=load, weight=weight, pull=pull,
                clear=clear, drop=drop, r_arm=r_arm, z_kink=z_kink,
                t_arm=t_arm, w_arm=w_arm, t_base=t_base, t_top=t_top,
                r_seat_in=r_seat_in, r_seat_out=r_seat_out,
                r_pad_in=r_pad_in, r_pad_out=r_pad_out, lever=lever,
                r_top=r_top, share=share)


def stresses(p: PotParams) -> dict:
    """What each section is actually working at, in MPa."""
    k = plan(p)
    return dict(
        arm=k["pull"] / (k["w_arm"] * k["t_arm"]),
        spoke=6.0 * k["share"] * k["lever"] / (_SPOKE_W * k["t_base"] ** 2),
        top=6.0 * k["share"] * max(k["r_top"] - _BOSS, 1.0)
        / (_SPOKE_W * k["t_top"] ** 2))


def governs(p: PotParams) -> str:
    s = stresses(p)
    return max(s, key=s.get)


def arm_clearance(p: PotParams) -> float:
    """Narrowest gap between an arm and the pot it runs past."""
    k = plan(p)
    pot = k["pot"]
    inner = k["r_arm"] - 0.5 * k["w_arm"]
    return min(inner - (pot["base_r"] + pot["slope"] * z)
               for z in np.linspace(0.0, pot["height"], 81))


def check_hanger(p: PotParams) -> list[str]:
    out: list[str] = []
    if p.hanger not in PARTS:
        raise ParameterError(
            f"unknown hanger {p.hanger!r}; choose from {list(PARTS)[1:]}")
    if p.hanger == "none":
        return out
    if p.hanger_mount not in MOUNTS:
        raise ParameterError(
            f"unknown hanger_mount {p.hanger_mount!r}; choose from "
            f"{list(MOUNTS)}")
    if p.hanger in WALL_PARTS and p.hanger_mount != "wall":
        raise ParameterError(
            f"hanger {p.hanger!r} is part of the wall mount - set "
            f"hanger_mount='wall' as well, or ask for a ceiling part")
    k = plan(p)
    s = stresses(p)
    gap = arm_clearance(p)
    if gap < 2.0:
        raise ParameterError(
            f"the arms would run {gap:.1f} mm from the pot - raise "
            f"hanger_clearance")
    out.append(
        f"sized for {k['load']:.1f} kg on {k['n']} arms, one of them assumed "
        f"slack: {k['pull']:.0f} N per arm. Worst section is the "
        f"{governs(p)} at {max(s.values()):.1f} MPa against a "
        f"{_SIGMA:.0f} MPa working stress")
    out.append(
        "print every part FLAT, as modelled - a load-bearing part "
        "printed standing up is being pulled apart across its layer lines, "
        "which is the one direction printed plastic is bad at")
    out.append(
        "PLA creeps under a load that never comes off, and a hanging pot is "
        "exactly that: use PETG or PLA+, look at it now and then, and do not "
        "hang it over anything that would mind it coming down")
    if k["load"] > 12.0:
        out.append(
            f"{k['load']:.0f} kg is a lot to ask of printed plastic on a "
            f"ceiling hook - at this weight the hook and its fixing are the "
            f"thing to worry about, not the hanger")
    if p.printer != "none":
        from .printers import PRINTERS
        bw, bd = PRINTERS[p.printer]["bed"]
        span = k["drop"] + k["t_top"] + 2.0 * _RETURN_T
        if span > math.hypot(bw, bd) - 12.0:
            out.append(
                f"a {span:.0f} mm arm does not lie on a {bw:.0f}x{bd:.0f} mm "
                f"bed even cornerwise - lower hanger_drop")
        elif span > max(bw, bd):
            out.append(
                f"the {span:.0f} mm arm only fits the bed diagonally - set "
                f"the part on the skew in the slicer, and keep it flat")
    out.append(
        f"the pot sits on a {2 * k['r_seat_in']:.0f}-{2 * k['r_seat_out']:.0f} "
        f"mm seat and the arms clear it by {gap:.0f} mm; a hanging pot drips, "
        f"so put a tray under it (--underpot tray) or water it in the sink")
    if p.hanger_mount == "wall":
        out += check_wall(p)
    return out


# ---------------------------------------------------------------------------
# flat-plate helpers - everything below is built lying on the bed
# ---------------------------------------------------------------------------
def _bar(x0: float, y0: float, x1: float, y1: float, w: float, t: float
         ) -> trimesh.Trimesh:
    """A flat bar of width ``w`` and thickness ``t`` from (x0,y0) to (x1,y1),
    lying in the XY plane with its underside on z = 0."""
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    bar = trimesh.creation.box(extents=(length, w, t))
    bar.apply_transform(trimesh.transformations.rotation_matrix(
        math.atan2(dy, dx), [0, 0, 1]))
    bar.apply_translation((0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * t))
    return bar


def _block(x0: float, x1: float, y0: float, y1: float, t: float
           ) -> trimesh.Trimesh:
    box = trimesh.creation.box(extents=(abs(x1 - x0), abs(y1 - y0), t))
    box.apply_translation((0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * t))
    return box


# ---------------------------------------------------------------------------
# the arm
# ---------------------------------------------------------------------------
def arm_frame(p: PotParams) -> dict:
    """The arm's outline, in the plane it prints in.

    ``x`` is radius and ``y`` is height, both as they will be once it is
    hanging - so the part is modelled lying on the bed in exactly the
    attitude it is meant to print in, and stood up in the assembly.  The
    datum is the **underside of the base plate**, which is where that plate
    sits on the bed too.
    """
    k = plan(p)
    w = k["w_arm"]
    return dict(
        w=w, t=k["t_arm"],
        y_bot=-_RETURN_T,                       # under the base plate
        y_top=k["drop"] + k["t_top"] + _RETURN_T,   # over the top ring
        x_bot_in=k["r_arm"] - 0.5 * w - _GRIP,
        x_bot_out=k["r_arm"] + 0.5 * w + 2.0,
        x_top_in=k["r_top"] - 0.5 * w - _GRIP,
        x_top_out=k["r_top"] + 0.5 * w + 2.0,
        reach=w + _GRIP + 2.0,                  # the return, radially
        **k)


def insert_tilt(p: PotParams) -> float:
    """Degrees an arm has to be tipped for its return to pass its slot.

    A flat plate on edge, tilted, presents a shorter shadow: the return
    goes through at ``acos(slot / reach)`` and at nothing less.
    """
    a = arm_frame(p)
    ratio = min(1.0, (a["w"] + _SLOT_FIT) / a["reach"])
    return math.degrees(math.acos(ratio))


def build_hanger_arm(p: PotParams) -> trimesh.Trimesh:
    """One arm.  Print ``hanger_arms`` of them, flat, as modelled."""
    check_hanger(p)
    a = arm_frame(p)
    w, t = a["w"], a["t"]
    parts = [
        # straight up past the pot, then the turn in above its rim
        _bar(a["r_arm"], a["y_bot"], a["r_arm"], a["z_kink"], w, t),
        _bar(a["r_arm"], a["z_kink"], a["r_top"], a["z_gather"], w, t),
        _bar(a["r_top"], a["z_gather"], a["r_top"], a["y_top"], w, t),
        # the returns: longer than their slots, which is the whole joint
        _block(a["x_bot_in"], a["x_bot_out"], a["y_bot"], 0.0, t),
        _block(a["x_top_in"], a["x_top_out"],
               a["drop"] + a["t_top"], a["y_top"], t),
    ]
    return _finish(_boolean("union", parts), center=False)


def seated_arm(p: PotParams, index: int = 0) -> trimesh.Trimesh:
    """An arm, stood up and swung round to where it hangs."""
    k = plan(p)
    arm = build_hanger_arm(p)
    # modelled flat: x = radius, y = height, z = thickness.  Stand it up so
    # y becomes height and the thickness becomes tangential
    arm.apply_translation((0.0, 0.0, -0.5 * k["t_arm"]))
    arm.apply_transform(trimesh.transformations.rotation_matrix(
        math.pi / 2.0, [1, 0, 0]))
    arm.apply_transform(trimesh.transformations.rotation_matrix(
        2.0 * math.pi * index / k["n"], [0, 0, 1]))
    return arm


# ---------------------------------------------------------------------------
# the base
# ---------------------------------------------------------------------------
def build_hanger_base(p: PotParams) -> trimesh.Trimesh:
    """The spoked ring the pot stands on.  Prints flat, as modelled."""
    check_hanger(p)
    k = plan(p)
    t = k["t_base"]
    sec = _round(p)
    # the seat: an annulus whose hole opens upward, so a pot dropped into it
    # centres itself instead of sitting wherever it landed
    seat = lathe([(k["r_seat_out"], 0.0), (k["r_seat_out"], t)], sec,
                 decorate=False)
    hole = lathe([(k["r_seat_in"], -1.0),
                  (k["r_seat_in"], t - _SEAT_CHAMFER),
                  (k["r_seat_in"] + _SEAT_CHAMFER, t + 1.0)], sec,
                 decorate=False)
    body = _boolean("difference", [seat, hole])

    spokes, notches = [], []
    for i in range(k["n"]):
        ang = 2.0 * math.pi * i / k["n"]
        rot = trimesh.transformations.rotation_matrix(ang, [0, 0, 1])
        spoke = _block(k["r_seat_out"] - 6.0, k["r_pad_out"],
                       -0.5 * _SPOKE_W, 0.5 * _SPOKE_W, t)
        spoke.apply_transform(rot)
        spokes.append(spoke)
        # a plain slot, closed all round: the arm threads up through it
        # from below and its return lies across it
        half = 0.5 * (k["t_arm"] + _SLOT_FIT)
        slot = _block(k["r_arm"] - 0.5 * (k["w_arm"] + _SLOT_FIT),
                      k["r_arm"] + 0.5 * (k["w_arm"] + _SLOT_FIT),
                      -half, half, t + 4.0)
        slot.apply_translation((0.0, 0.0, -2.0))
        slot.apply_transform(rot)
        notches.append(slot)
    body = _boolean("union", [body] + spokes)
    return _finish(_boolean("difference", [body] + notches), center=False)


# ---------------------------------------------------------------------------
# the top ring
# ---------------------------------------------------------------------------
def build_hanger_top(p: PotParams) -> trimesh.Trimesh:
    """The ring the arms gather at.  Prints flat, as modelled."""
    check_hanger(p)
    k = plan(p)
    t = k["t_top"]
    sec = _round(p)
    body = lathe([(k["r_top"] + 0.5 * k["w_arm"] + 2.5, 0.0),
                  (k["r_top"] + 0.5 * k["w_arm"] + 2.5, t)], sec,
                 decorate=False)

    cuts = []
    if p.hanger_top == "hole":
        cuts.append(trimesh.creation.cylinder(radius=5.0, height=4.0 * t,
                                              sections=32))
    elif p.hanger_top == "slot":
        cuts.append(_block(-13.0, 13.0, -3.0, 3.0, 4.0 * t))
        cuts[-1].apply_translation((0.0, 0.0, -t))
    else:                                    # a ring you can pass a rope round
        cuts.append(trimesh.creation.cylinder(
            radius=max(6.0, k["r_top"] - 0.5 * k["w_arm"] - 6.0),
            height=4.0 * t, sections=64))

    for i in range(k["n"]):
        ang = 2.0 * math.pi * i / k["n"]
        # the same slot as the base's, which is why the middle of this ring
        # can stay solid for something to hang it from
        half = 0.5 * (k["t_arm"] + _SLOT_FIT)
        notch = _block(k["r_top"] - 0.5 * (k["w_arm"] + _SLOT_FIT),
                       k["r_top"] + 0.5 * (k["w_arm"] + _SLOT_FIT),
                       -half, half, t + 4.0)
        notch.apply_translation((0.0, 0.0, -2.0))
        notch.apply_transform(
            trimesh.transformations.rotation_matrix(ang, [0, 0, 1]))
        cuts.append(notch)
    return _finish(_boolean("difference", [body] + cuts), center=False)


def seated_top(p: PotParams) -> trimesh.Trimesh:
    """The top ring, lifted to where the arms reach it."""
    k = plan(p)
    ring = build_hanger_top(p)
    ring.apply_translation((0.0, 0.0, k["drop"]))
    return ring


def hung_set(p: PotParams) -> trimesh.Trimesh:
    """Base, arms and top ring, where they hang under their own datum."""
    k = plan(p)
    parts = [build_hanger_base(p), seated_top(p)]
    parts += [seated_arm(p, i) for i in range(k["n"])]
    return trimesh.util.concatenate(parts)


# ---------------------------------------------------------------------------
# the wall mount: a French cleat, and the frame that hangs on it
# ---------------------------------------------------------------------------
def _screw_span(l_c: float, n: int) -> float:
    return (l_c - 2.0 * _SCREW_INSET) / max(n - 1, 1)


def cleat_stress(pull: float, l_c: float, n: int) -> float:
    """The rail between two screws, bent by whatever is pulling it off.

    The whole pull is put at midspan of one bay, which nothing hanging on
    the rail can actually manage - it is the cheapest honest way to be
    conservative.
    """
    return 1.5 * pull * _screw_span(l_c, n) / (
        (_CLEAT_BODY + _CLEAT_RISE * _CLEAT_T) * _CLEAT_T ** 2)


def _yoke_modulus(t: float, d: float, r: float) -> float:
    """Section modulus of a plate ``d`` deep with a hole ``r`` at its middle.

    The eye goes on the neutral axis, where a hole costs least - but it
    still costs, so the sum says so instead of using the gross depth.
    """
    return t * (d ** 3 - 8.0 * r ** 3) / (6.0 * d)


def wall_plan(p: PotParams) -> dict:
    """The rail, the two ribs and the yoke - and the couple they work as."""
    if p.hanger_mount not in MOUNTS:
        raise ParameterError(
            f"unknown hanger_mount {p.hanger_mount!r}; choose from "
            f"{list(MOUNTS)}")
    k = plan(p)
    reach = float(p.hanger_reach)
    if not 60.0 <= reach <= 400.0:
        raise ParameterError(
            "hanger_reach should be 60-400 mm - the wall to the point the "
            "pot hangs from")
    l_c = float(p.hanger_cleat_length)
    if not 60.0 <= l_c <= 400.0:
        raise ParameterError("hanger_cleat_length should be 60-400 mm")
    t_c, d_gap = _CLEAT_T, _CLEAT_T + _CLEAT_FIT
    h_c = _CLEAT_BODY + _CLEAT_RISE * t_c
    t_rib = max(_RIB_T_MIN, p.wall_thickness)
    t_yoke = t_rib
    spread = max(_SPREAD_MIN, l_c - 2.0 * _RIB_INSET)

    # each rib carries half the pot, out at the reach
    moment = 0.5 * k["weight"] * reach
    d_root = math.sqrt(6.0 * moment / (t_rib * _SIGMA))
    h_rib = max(_RIB_H_MIN, _RIB_H_FACTOR * d_root,
                _RIB_LIP + _CLEAT_FIT + _CLEAT_BODY + _NOTCH_DROP
                + _RIB_BEAR_MIN)

    # the notch's ceiling is a 45 deg face that RISES away from the wall,
    # and that direction is the whole mount.  Tip the rib the way a
    # cantilever tips it - top out, bottom in - and the ceiling drives down
    # and out INTO the rail's bevel.  Rip the cleat the other way round, the
    # way a picture rail is usually cut, and the same motion slides the two
    # bevels apart: it carries shear beautifully and the moment not at all
    y_nt = h_rib - _RIB_LIP                   # the ceiling, at the wall
    z_rail = y_nt - _CLEAT_FIT - _CLEAT_BODY  # the rail's bottom edge
    y_nb = z_rail - _NOTCH_DROP               # the notch's floor
    # the couple: the rib's back bears flat on the wall below the notch and
    # the notch holds it in up top.  The bearing is taken at the middle of
    # that face rather than the third of it a wedge of pressure would really
    # act at, which shortens the arm and so raises the force
    arm = (y_nt + 0.5 * _CLEAT_RISE * t_c) - 0.5 * y_nb
    force = moment / arm

    # the yoke: a beam between the ribs with the pot hung at its middle,
    # and the eye is a hole right where that beam is worst
    m_yoke = 0.25 * k["weight"] * spread
    d_yoke = _YOKE_D_MIN
    while (d_yoke < 300.0
           and _yoke_modulus(t_yoke, d_yoke, _EYE_R) < m_yoke / _SIGMA):
        d_yoke += 0.5
    tab = d_yoke - _YOKE_SHOULDER
    slot_h = tab + _YOKE_LIFT + _SLOT_FIT

    # the rib's tip: enough to hold the yoke's slot, and enough that the
    # taper does not run out of section before the load does
    tip = max(slot_h + 2.0 * _RIB_WEB,
              0.5 * (h_rib - math.sqrt(max(h_rib ** 2 - d_root ** 2, 0.0))))
    x_tip = reach + 0.5 * t_yoke + _RIB_WEB
    z_yoke = h_rib - 0.5 * tip                # the slot's middle
    # seated, the tenon rests on the floor of its slot - which is where the
    # load puts it anyway - and the eye sits at the yoke's own mid-depth
    z_eye = (z_yoke - 0.5 * slot_h + 0.5 * _SLOT_FIT + tab) - 0.5 * d_yoke

    n_screw = int(p.hanger_screws)
    if n_screw <= 0:                          # as many as the pull-out needs
        n_screw = 2
        while n_screw < 8 and cleat_stress(2.0 * force, l_c, n_screw) > _SIGMA:
            n_screw += 1
    elif n_screw < 2:
        raise ParameterError("hanger_screws should be 2 or more, or 0 to let "
                             "the pull-out decide")
    bore = 0.5 * float(p.hanger_screw_bore)
    head = bore + 2.25                        # a 45 deg countersink

    # where the hanging set goes: under the yoke, and clear of the ribs
    ring_r = k["r_top"] + 0.5 * k["w_arm"] + 4.0
    z_top = z_eye - 0.5 * d_yoke - _HOOK
    if ring_r > 0.5 * spread - 0.5 * t_rib - _RING_CLEAR:
        # the top ring is too wide to pass between the ribs, so it has to
        # hang below their undersides as well
        x_in = max(0.0, reach - ring_r)
        z_top = min(z_top,
                    (h_rib - tip) * x_in / x_tip - _RING_CLEAR)

    return dict(k=k, reach=reach, moment=moment, t_c=t_c, d_gap=d_gap,
                h_c=h_c, l_c=l_c, t_rib=t_rib, t_yoke=t_yoke, spread=spread,
                d_root=d_root, h_rib=h_rib, y_nt=y_nt, y_nb=y_nb,
                z_rail=z_rail, arm=arm,
                force=force, m_yoke=m_yoke, d_yoke=d_yoke, tab=tab,
                slot_h=slot_h, tip=tip, x_tip=x_tip, z_yoke=z_yoke,
                z_eye=z_eye, n_screw=n_screw, span=_screw_span(l_c, n_screw),
                bore=bore, head=head, ring_r=ring_r, z_top=z_top)


def rib_depth(w: dict, x: float) -> float:
    """How deep the rib is, ``x`` out from the wall."""
    return w["h_rib"] - (w["h_rib"] - w["tip"]) * min(x, w["x_tip"]) / w["x_tip"]


def rib_bending(p: PotParams) -> tuple[float, float]:
    """Worst stress along a rib, and how far out along it that is."""
    w = wall_plan(p)
    load = 0.5 * w["k"]["weight"]
    xs = np.linspace(0.0, w["reach"], 241)
    depth = np.array([rib_depth(w, float(x)) for x in xs])
    sig = 6.0 * load * (w["reach"] - xs) / (w["t_rib"] * depth ** 2)
    i = int(np.argmax(sig))
    return float(sig[i]), float(xs[i])


def wall_stresses(p: PotParams) -> dict:
    """What the three wall parts are actually working at, in MPa."""
    w = wall_plan(p)
    return dict(
        rib=rib_bending(p)[0],
        yoke=w["m_yoke"] / _yoke_modulus(w["t_yoke"], w["d_yoke"], _EYE_R),
        cleat=cleat_stress(2.0 * w["force"], w["l_c"], w["n_screw"]))


def wall_governs(p: PotParams) -> str:
    s = wall_stresses(p)
    return max(s, key=s.get)


def wall_clearance(p: PotParams) -> float:
    """Air between the wall and the widest part of the hanging set."""
    w = wall_plan(p)
    k = w["k"]
    return w["reach"] - max(k["r_pad_out"], k["r_arm"] + 0.5 * k["w_arm"],
                            k["pot"]["top_r"])


def hook_length(p: PotParams) -> float:
    """Hook or rope wanted between the yoke's eye and the top ring."""
    w = wall_plan(p)
    return w["z_eye"] - w["z_top"]


def check_wall(p: PotParams) -> list[str]:
    out: list[str] = []
    w = wall_plan(p)
    k = w["k"]
    gap = wall_clearance(p)
    if gap < _WALL_CLEAR:
        raise ParameterError(
            f"the pot would come within {max(gap, 0.0):.0f} mm of the wall - "
            f"a {2 * k['pot']['top_r']:.0f} mm pot on {k['n']} arms needs "
            f"hanger_reach of at least "
            f"{w['reach'] - gap + _WALL_CLEAR:.0f} mm")
    if w["tip"] > 0.8 * w["h_rib"]:
        raise ParameterError(
            f"at {w['reach']:.0f} mm of reach with {k['load']:.1f} kg on the "
            f"end the rib barely tapers at all - shorten hanger_reach, or "
            f"lighten hanger_load")
    if w["span"] < 2.0 * w["head"] + 6.0:
        raise ParameterError(
            f"{w['n_screw']} screws do not fit along a {w['l_c']:.0f} mm "
            f"rail - lengthen hanger_cleat_length")
    if max(wall_stresses(p).values()) > _SIGMA + 1e-6:
        raise ParameterError(
            f"the wall mount works the {wall_governs(p)} to "
            f"{max(wall_stresses(p).values()):.1f} MPa against a "
            f"{_SIGMA:.0f} MPa working stress - put hanger_screws back to 0 "
            f"and let the pull-out choose it, or shorten hanger_reach, or "
            f"lighten hanger_load")
    s = wall_stresses(p)
    sig, at = rib_bending(p)
    out.append(
        f"the wall mount hangs the set {w['reach']:.0f} mm off the wall, "
        f"which is {2 * w['moment'] / 1000.0:.1f} N.m at the fixing - an "
        f"order more than a ceiling hook ever sees. Print TWO ribs. Worst "
        f"section is the {wall_governs(p)} at {max(s.values()):.1f} MPa")
    out.append(
        f"each rib is worst {at:.0f} mm out from the wall rather than at its "
        f"back edge, which is why it keeps a {w['tip']:.0f} mm tip instead of "
        f"running to a point: with the load hung at the end, a triangle runs "
        f"out of section faster than the moment falls away")
    out.append(
        f"the couple is {w['force']:.0f} N per rib: the back edge below the "
        f"notch pushes that into the wall and the notch's bevel holds it "
        f"back up top. That flat back is not a spacer - hold the rib off the "
        f"wall and the bracket pivots on the rail and the screws come out")
    out.append(
        f"{w['n_screw']} countersunk screws at {w['span']:.0f} mm centres, "
        f"{2 * w['bore']:.1f} mm shank: between them they see about "
        f"{2 * w['force']:.0f} N pulling off the wall and "
        f"{k['weight']:.0f} N down. That is the one part this generator does "
        f"not make - put them in a stud, or in a plasterboard fixing rated "
        f"well past those numbers")
    out.append(
        "print the cleat with its FLAT BACK on the bed: the 45 deg bevel "
        "then faces up, which is the one angle that needs nothing under it. "
        "The ribs and the yoke lie on their sides like the arms")
    out.append(
        f"to put it together, hold the yoke {_YOKE_LIFT:.0f} mm high and "
        f"slide a rib on from each side, then let it down - the lugs on the "
        f"ends of the yoke drop below their slots and cannot come back "
        f"through. Then hook both ribs over the rail")
    out.append(
        f"leave about {hook_length(p):.0f} mm of hook or rope between the "
        f"yoke's eye and the top ring, or the ring fouls the bracket")
    out.append(
        f"the bracket lifts off: raise it {w['d_gap']:.0f} mm and it pulls "
        f"straight forward off the rail. Short of that it cannot - the "
        f"bevel rising away from the wall is in the way of a straight pull "
        f"as well as of the tipping")
    if p.printer != "none":
        from .printers import PRINTERS
        bw, bd = PRINTERS[p.printer]["bed"]
        for what, dx, dy in (
                ("rib", w["x_tip"], w["h_rib"]),
                ("yoke", w["spread"] + w["t_rib"] + 2.0 * _YOKE_OUT,
                 w["d_yoke"])):
            if max(dx, dy) > math.hypot(bw, bd) - 12.0:
                out.append(
                    f"the {what} is {dx:.0f}x{dy:.0f} mm and does not lie on "
                    f"a {bw:.0f}x{bd:.0f} mm bed - lower hanger_reach")
            elif max(dx, dy) > max(bw, bd):
                out.append(
                    f"the {what} only fits the bed diagonally at "
                    f"{dx:.0f}x{dy:.0f} mm - set it on the skew, kept flat")
    return out


# ---------------------------------------------------------------------------
# the wall parts, each modelled in the attitude it prints in
# ---------------------------------------------------------------------------
def _box3(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float
          ) -> trimesh.Trimesh:
    box = trimesh.creation.box(extents=(abs(x1 - x0), abs(y1 - y0),
                                        abs(z1 - z0)))
    box.apply_translation((0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1)))
    return box


def cleat_solid(sec: Section, l_c: float, n_screw: int, span: float,
                bore: float, head: float) -> trimesh.Trimesh:
    """The wall rail itself - shared by everything that hangs on one.

    Modelled lying FACE DOWN, which is how it prints: the bevel then faces
    up and the countersinks are cones in the bed face.
    """
    t_c = _CLEAT_T
    h_c = _CLEAT_BODY + _CLEAT_RISE * t_c
    # (height, thickness): full thickness up to the rip, then the bevel
    # running back to the wall.  The long point of a French cleat is the one
    # against the wall, and that is the edge the ribs hook over
    body = _prism([(0.0, 0.0), (h_c, 0.0), (_CLEAT_BODY, t_c), (0.0, t_c)],
                  -0.5 * l_c, 0.5 * l_c)
    depth = (head - bore) / math.tan(math.radians(_CSK_DEG))
    cuts = []
    for i in range(n_screw):
        x = -0.5 * l_c + _SCREW_INSET + i * span
        # the heads go on the bed face, so the countersink is a cone that
        # narrows GOING UP and has to stay inside the overhang budget: a
        # 90 deg countersink is exactly 45 deg of it, so this is an 80 deg
        # one, which is what a wood screw wants anyway.  Flush heads are
        # also what let a rib sit anywhere along the rail
        cut = lathe([(head, -1.0), (head, 0.0),
                     (bore, depth), (bore, t_c + 1.0)], sec, decorate=False)
        cut.apply_translation((x, 0.5 * _CLEAT_BODY, 0.0))
        cuts.append(cut)
    return _finish(_boolean("difference", [body] + cuts), center=False)


def build_hanger_cleat(p: PotParams) -> trimesh.Trimesh:
    """The wall rail.  Prints FACE DOWN, so the bevel faces up."""
    check_hanger(p)
    w = wall_plan(p)
    return cleat_solid(_round(p), w["l_c"], w["n_screw"], w["span"],
                       w["bore"], w["head"])


def build_hanger_rib(p: PotParams) -> trimesh.Trimesh:
    """One side of the bracket.  Print TWO, flat, as modelled.

    Everything about a rib is outline: it is a flat plate standing on edge,
    so the 45 deg hook, the taper and the yoke's slot are all edges in the
    plane it prints in and none of them is an overhang at all.
    """
    check_hanger(p)
    w = wall_plan(p)
    t, d_gap = w["t_rib"], w["d_gap"]
    body = _prism_z([(0.0, 0.0), (w["x_tip"], w["h_rib"] - w["tip"]),
                     (w["x_tip"], w["h_rib"]), (0.0, w["h_rib"])], 0.0, t)
    # the notch that hooks the rail: a pocket in the back edge whose ceiling
    # RISES away from the wall, so that tipping drives it into the rail
    # rather than off it.  Everything below it stays flat against the wall
    notch = _prism_z([(-1.0, w["y_nb"]), (d_gap, w["y_nb"]),
                      (d_gap, w["y_nt"] + _CLEAT_RISE * d_gap),
                      (-1.0, w["y_nt"] - _CLEAT_RISE)], -1.0, t + 1.0)
    half_x = 0.5 * (w["t_yoke"] + _SLOT_FIT)
    slot = _box3(w["reach"] - half_x, w["reach"] + half_x,
                 w["z_yoke"] - 0.5 * w["slot_h"],
                 w["z_yoke"] + 0.5 * w["slot_h"], -1.0, t + 1.0)
    return _finish(_boolean("difference", [body, notch, slot]), center=False)


def build_hanger_yoke(p: PotParams) -> trimesh.Trimesh:
    """The beam between the ribs, and the eye the pot hangs from."""
    check_hanger(p)
    w = wall_plan(p)
    d, tab, t = w["d_yoke"], w["tab"], w["t_yoke"]
    x_i = 0.5 * w["spread"] - 0.5 * w["t_rib"]     # a rib's inner face
    x_o = x_i + w["t_rib"]
    parts = [
        _box3(-x_i, x_i, 0.0, d, 0.0, t),          # the beam
    ]
    for side in (-1.0, 1.0):
        a, b = sorted((side * x_i, side * x_o))
        c, e = sorted((side * x_o, side * (x_o + _YOKE_OUT)))
        # the tenon, and outboard of it a lug that hangs BELOW it: lift the
        # yoke and the lug lines up with the slot, let it down and the lug
        # is under the slot's floor with the rib in the way
        parts.append(_box3(a, b, d - tab, d, 0.0, t))
        parts.append(_box3(c, e, d - tab - _YOKE_LIFT, d, 0.0, t))
    eye = trimesh.creation.cylinder(radius=_EYE_R, height=4.0 * t,
                                    sections=48)
    eye.apply_translation((0.0, 0.5 * d, 0.5 * t))
    return _finish(_boolean("difference", [_boolean("union", parts), eye]),
                   center=False)


# ---------------------------------------------------------------------------
# where they all go
# ---------------------------------------------------------------------------
def _place(mesh: trimesh.Trimesh, rows, offset) -> trimesh.Trimesh:
    m = np.eye(4)
    m[:3, :3] = np.array(rows, dtype=float)
    m[:3, 3] = offset
    out = mesh.copy()
    out.apply_transform(m)
    return out


def seated_cleat(p: PotParams) -> trimesh.Trimesh:
    """The rail on the wall.  X runs out from the wall, Y along it, Z up
    from the bottom of a rib's back edge."""
    w = wall_plan(p)
    # the rail prints face down, so the bed face is the one that ends up
    # pointing into the room; its bevel line sits _CLEAT_FIT under the
    # notch's, so the two 45 deg faces mate on air, not on a press fit
    return _place(build_hanger_cleat(p),
                  [[0, 0, -1], [-1, 0, 0], [0, 1, 0]],
                  (w["t_c"], 0.0, w["z_rail"]))


def seated_rib(p: PotParams, side: int = 1, lift: float = 0.0
               ) -> trimesh.Trimesh:
    w = wall_plan(p)
    y = side * 0.5 * w["spread"] + 0.5 * w["t_rib"]
    return _place(build_hanger_rib(p),
                  [[1, 0, 0], [0, 0, -1], [0, 1, 0]], (0.0, y, lift))


def seated_yoke(p: PotParams, lift: float = 0.0) -> trimesh.Trimesh:
    """The yoke, where it sits - or ``lift`` mm up, which is where its lugs
    line up with the slots and it comes apart."""
    w = wall_plan(p)
    z0 = (w["z_yoke"] - 0.5 * w["slot_h"] + 0.5 * _SLOT_FIT
          + w["tab"] - w["d_yoke"])
    return _place(build_hanger_yoke(p),
                  [[0, 0, -1], [-1, 0, 0], [0, 1, 0]],
                  (w["reach"] + 0.5 * w["t_yoke"], 0.0, z0 + lift))


def wall_assembled(p: PotParams) -> trimesh.Trimesh:
    """Rail, ribs, yoke and the whole hanging set, on the wall."""
    w = wall_plan(p)
    k = w["k"]
    hung = hung_set(p)
    hung.apply_translation(
        (w["reach"], 0.0,
         w["z_top"] - (k["drop"] + k["t_top"] + _RETURN_T)))
    return trimesh.util.concatenate(
        [seated_cleat(p), seated_rib(p, -1), seated_rib(p, 1),
         seated_yoke(p), hung])


def assembled(p: PotParams) -> trimesh.Trimesh:
    """Everything, where it hangs - off a hook or off a wall."""
    if p.hanger_mount == "wall":
        return wall_assembled(p)
    return hung_set(p)
