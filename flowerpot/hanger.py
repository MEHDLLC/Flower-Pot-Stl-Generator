"""A hanger for a pot, in three flat parts.

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
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _finish, lathe
from .params import ParameterError, PotParams
from .sections import Section
from .underpot import nursery_dims

PARTS = ("none", "set", "base", "arm", "top")
TOPS = ("hole", "slot", "ring")

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
        "print all three parts FLAT, as modelled - a load-bearing part "
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


def assembled(p: PotParams) -> trimesh.Trimesh:
    """Base, arms and top ring, where they hang."""
    k = plan(p)
    parts = [build_hanger_base(p), seated_top(p)]
    parts += [seated_arm(p, i) for i in range(k["n"])]
    return trimesh.util.concatenate(parts)
