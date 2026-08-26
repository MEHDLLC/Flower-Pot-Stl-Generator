"""Two shop vessels, and the self-watering pair they make.

* a **Vigoro "Kyra"** 6 in. round planter with an attached saucer -
  6.00 in. across the top, 4.70 in. across the saucer, 5.51 in. tall;
* a **reservoir** in the manner of an HDX 2.5 qt mixing container, sized so
  the pot drops into it and the two rims finish flush.

The pot's numbers are the listing's.  Its own spec drawing disagrees with
its title - 7.32 in. against 5.51 - and 5.51 is the one that matches the
reason for wanting both: a 5½ in. pot sits flush in a 5½ in. bucket, and a
7⅓ in. one would stand two inches proud.  Every dimension is a parameter,
so a tape measure beats this reasoning whenever one is to hand.

Sizing the reservoir from the pot
---------------------------------
Its mouth is the pot's rim plus a clearance, and its depth is the pot's
height plus the ``replica_standoff`` the pot is held above the water.  That
last one is the whole trade, and it cannot be dodged: **flush rims, a real
reservoir, and the original bucket's depth are three things you can only
have two of.**  A pot resting on the floor of a 2.5 qt bucket leaves a
couple of hundred millilitres in the gap around it at best; lifting it far
enough to matter makes the bucket that much deeper than the one in the
shop.  The default keeps the rims flush and takes the depth.

What a printer cannot copy
--------------------------
The real pot's saucer is a *tray* - a moulded cavity under the pot's floor.
Printed standing up that cavity is a ceiling the full width of the pot, and
no cone closes a 110 mm span.  So the replica's saucer is a solid flared
foot: the same silhouette from outside, no tray.  In the reservoir it makes
no difference, which is where this pot is going.

The plumbing
------------
* **Ribs** stand up off the reservoir's floor for the pot to sit on.  They
  are vertical fins with flat tops - the standoff has to come from *below*,
  because a shelf moulded round the inside of the wall would be a ledge
  facing down.
* An **overflow** through the wall sets the water line a finger's width
  below the pot's floor, so the soil never sits in water.  It is a diamond
  port, not a round hole: a round hole through a standing wall has a
  ceiling across its top.
* A **notch** in the rim is what you pour through.  The gap between the two
  rims is a couple of millimetres, which no watering can will find.
* A **wick cup** is its own small part.  It drops through the pot's floor
  and hangs into the water; pack it with the same soil and it carries the
  water up.  It is separate because hanging it off the pot's floor would
  put that floor in mid-air with a cone's worth of nothing under it.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _diamond_port, _finish, lathe
from .params import ParameterError, PotParams
from .profile import slope_budget
from .sections import Section

MM = 25.4

#: The Vigoro "Kyra" 6 in. planter, from the listing.  Overridable.
KYRA = dict(top_od=6.00 * MM, saucer_od=4.70 * MM, height=5.51 * MM)

_SAUCER_LIP = 4.0        # the saucer's own vertical edge
_SAUCER_TUCK = 6.0       # ... and the rise the wall takes to step in above it
_SAUCER_STEP = 4.0       # how far the saucer stands proud of the wall
_POT_RIM_OUT = 2.5       # the pot's rolled top lip
_POT_RIM_H = 5.0

_FIT = 1.4               # radial clearance, pot rim to reservoir mouth
_TAPER = 0.10            # the reservoir's dr/dz, in the manner of the bucket
_RIM_OUT = 7.0           # the reservoir's flat rim flange
_BEAD_OUT = 1.6          # the stiffening bead round its waist
_RIBS = 6
_RIB_W = 5.0
_RIB_REACH = 17.0
_FILL_R = 11.0           # the notch you pour through
_FILL_DEPTH = 32.0
_FREEBOARD = 6.0         # air between the water line and the pot's floor
_OVERFLOW_W = 4.5

_WICK_OD = 38.0
_WICK_WALL = 2.2
_WICK_FLANGE = 6.0
_WICK_MIN_STAND = 13.0
_DRAIN_R = 4.0
_DRAINS = 4


# ---------------------------------------------------------------------------
# sizing
# ---------------------------------------------------------------------------
def _round(p: PotParams) -> Section:
    return Section(p.with_(surface_texture="none"))


def wall_of(p: PotParams) -> float:
    return max(2.4, p.wall_thickness)


def floor_of(p: PotParams) -> float:
    return max(3.2, p.base_thickness * 0.7)


def pot_plan(p: PotParams) -> dict:
    """Radii and heights of the planter."""
    top_r = 0.5 * float(p.replica_pot_top)
    saucer_r = 0.5 * float(p.replica_pot_base)
    height = float(p.replica_pot_height)
    wall_r = saucer_r - _SAUCER_STEP
    if not 0.35 * top_r < wall_r < top_r:
        raise ParameterError(
            f"a {2 * saucer_r:.0f} mm base under a {2 * top_r:.0f} mm mouth "
            f"is not a pot - it wants to be between "
            f"{2 * (0.35 * top_r + _SAUCER_STEP):.0f} and {2 * top_r:.0f} mm; "
            f"check replica_pot_top and replica_pot_base"
        )
    z_wall = _SAUCER_LIP + _SAUCER_TUCK
    z_rim = height - _POT_RIM_H
    if z_rim <= z_wall + 8.0:
        raise ParameterError(
            f"replica_pot_height {height:.0f} mm leaves no wall between the "
            f"saucer and the rim - it needs at least "
            f"{z_wall + 8.0 + _POT_RIM_H:.0f} mm"
        )
    return dict(top_r=top_r, saucer_r=saucer_r, wall_r=wall_r, height=height,
                z_wall=z_wall, z_rim=z_rim, floor=floor_of(p),
                slope=(top_r - wall_r) / (z_rim - z_wall))


def reservoir_plan(p: PotParams) -> dict:
    """The bucket, driven by the pot that has to sit in it."""
    pot = pot_plan(p)
    t = wall_of(p)
    floor = floor_of(p)
    stand = max(0.0, float(p.replica_standoff))
    mouth_r = pot["top_r"] + _POT_RIM_OUT + _FIT      # inside, at the lip
    # the pot lands on the ribs at floor + standoff, so the rim has to be
    # its own height above that for the two to finish flush
    depth = floor + stand + pot["height"]
    base_r = mouth_r - _TAPER * depth
    if base_r < pot["saucer_r"] + 2.0:
        # the pot would foul the wall before it reached the ribs
        base_r = pot["saucer_r"] + 2.0
    return dict(mouth_r=mouth_r, base_r=base_r, depth=depth, floor=floor,
                wall=t, stand=stand, pot=pot,
                z_sit=floor + stand,                  # where the pot lands
                z_water=floor + max(stand - _FREEBOARD, 0.0))


def reservoir_millilitres(p: PotParams) -> float:
    """Water held below the overflow, less the ribs and the wick cup."""
    k = reservoir_plan(p)
    h = k["z_water"] - k["floor"]
    if h <= 0.0:
        return 0.0
    r0 = k["base_r"]
    r1 = r0 + _TAPER * h
    gross = math.pi * h * (r0 * r0 + r0 * r1 + r1 * r1) / 3.0
    ribs = _RIBS * _RIB_W * _RIB_REACH * h
    cup = math.pi * (0.5 * _WICK_OD) ** 2 * h
    return max(gross - ribs - cup, 0.0) / 1000.0


def wants_wick(p: PotParams) -> bool:
    """A wick cup needs somewhere to hang.  Below about a centimetre of
    standoff there is no water to reach and no room for the cup."""
    return (p.replica_plumbing
            and reservoir_plan(p)["stand"] >= _WICK_MIN_STAND)


def check_replica(p: PotParams) -> list[str]:
    out: list[str] = []
    if p.replica not in ("none", "kyra", "hdx", "set"):
        raise ParameterError(
            f"unknown replica {p.replica!r}; choose from "
            f"['kyra', 'hdx', 'set']")
    if p.replica == "none":
        return out
    k = reservoir_plan(p)
    out.append(
        "the pot's attached saucer is a solid flared foot, not a tray - a "
        "moulded tray's cavity is a ceiling the full width of the pot"
    )
    if p.replica_plumbing and not wants_wick(p):
        out.append(
            f"replica_standoff {k['stand']:.0f} mm leaves no room for a wick "
            f"cup, so none is written - the pot is sub-irrigated through its "
            f"floor holes instead"
        )
    if p.replica_plumbing and k["stand"] > 0.0:
        out.append(
            f"the reservoir holds about {reservoir_millilitres(p):.0f} ml, "
            f"and is {k['stand']:.0f} mm deeper than the bucket it is modelled "
            f"on - that is what buys the water under the pot. Set "
            f"replica_standoff 0 for the shop bucket's proportions and almost "
            f"no reservoir"
        )
    return out


# ---------------------------------------------------------------------------
# the planter
# ---------------------------------------------------------------------------
def pot_rings(p: PotParams) -> list[tuple[float, float]]:
    """Outside of the pot, bottom to top."""
    k = pot_plan(p)
    return [
        (k["saucer_r"], 0.0),
        (k["saucer_r"], _SAUCER_LIP),                 # the saucer's edge
        (k["wall_r"], k["z_wall"]),                   # step in to the wall
        (k["top_r"], k["z_rim"]),                     # the taper
        (k["top_r"] + _POT_RIM_OUT, k["z_rim"] + 3.5),   # the rolled lip
        (k["top_r"] + _POT_RIM_OUT, k["height"]),
    ]


def pot_bore_rings(p: PotParams) -> list[tuple[float, float]]:
    """The cavity: the wall's own taper, offset perpendicular, carried
    straight out through the rim so the lip reads as a thickened edge."""
    k = pot_plan(p)
    t = wall_of(p)
    horiz = t * math.hypot(1.0, k["slope"])
    lo = k["floor"]
    r_lo = k["wall_r"] + k["slope"] * (lo - k["z_wall"]) - horiz
    r_hi = k["top_r"] + k["slope"] * (k["height"] + 2.0 - k["z_rim"]) - horiz
    return [(max(r_lo, 1.0), lo), (r_hi, k["height"] + 2.0)]


def _pot_cutters(p: PotParams) -> list[trimesh.Trimesh]:
    k = pot_plan(p)
    out = []
    ring = 0.52 * k["wall_r"]
    for i in range(_DRAINS):
        a = 2.0 * math.pi * (i + 0.5) / _DRAINS
        hole = trimesh.creation.cylinder(radius=_DRAIN_R, height=40.0,
                                         sections=32)
        hole.apply_translation((ring * math.cos(a), ring * math.sin(a), 0.0))
        out.append(hole)
    if p.replica_plumbing:
        bore = trimesh.creation.cylinder(radius=0.5 * _WICK_OD + 0.35,
                                         height=40.0, sections=48)
        out.append(bore)
    return out


def build_replica_pot(p: PotParams) -> trimesh.Trimesh:
    """The planter: prints standing on its saucer, no supports."""
    check_replica(p)
    sec = _round(p)
    body = lathe(pot_rings(p), sec, decorate=False)
    body = _boolean("difference",
                    [body, lathe(pot_bore_rings(p), sec, decorate=False)])
    return _finish(_boolean("difference", [body] + _pot_cutters(p)),
                   center=False)


# ---------------------------------------------------------------------------
# the reservoir
# ---------------------------------------------------------------------------
def reservoir_rings(p: PotParams) -> list[tuple[float, float]]:
    k = reservoir_plan(p)
    t, depth = k["wall"], k["depth"]
    z_bead = 0.58 * depth
    return [
        (k["base_r"] + t, 0.0),
        (k["base_r"] + t + _TAPER * z_bead, z_bead),
        (k["base_r"] + t + _TAPER * z_bead + _BEAD_OUT, z_bead + 1.4 * _BEAD_OUT),
        (k["base_r"] + t + _TAPER * (z_bead + 2.8 * _BEAD_OUT),
         z_bead + 2.8 * _BEAD_OUT),
        (k["mouth_r"] + t, depth - 1.22 * _RIM_OUT - 1.0),
        (k["mouth_r"] + t + _RIM_OUT, depth - 1.0),   # the flat rim, 39 under
        (k["mouth_r"] + t + _RIM_OUT, depth),
    ]


def reservoir_bore_rings(p: PotParams) -> list[tuple[float, float]]:
    k = reservoir_plan(p)
    return [(k["base_r"], k["floor"]),
            (k["mouth_r"] + _TAPER * 2.0, k["depth"] + 2.0)]


def _ribs(p: PotParams) -> trimesh.Trimesh:
    """Vertical fins for the pot to stand on.

    Cut back to the cavity afterwards, so each one meets the tapering wall
    along its whole height instead of leaning off it.
    """
    k = reservoir_plan(p)
    top = k["z_sit"]
    boxes = []
    for i in range(_RIBS):
        a = 2.0 * math.pi * i / _RIBS
        far = k["mouth_r"] + 4.0
        box = trimesh.creation.box(extents=(_RIB_REACH + far - k["base_r"],
                                            _RIB_W, top - k["floor"]))
        box.apply_translation((0.5 * (_RIB_REACH + far - k["base_r"])
                               + k["base_r"] - _RIB_REACH, 0.0,
                               0.5 * (top + k["floor"])))
        box.apply_transform(
            trimesh.transformations.rotation_matrix(a, [0, 0, 1]))
        boxes.append(box)
    return trimesh.util.concatenate(boxes)


def _reservoir_cutters(p: PotParams) -> list[trimesh.Trimesh]:
    k = reservoir_plan(p)
    out = []
    if not p.replica_plumbing:
        return out
    # the overflow: a diamond, because a round hole through a standing wall
    # has a ceiling straight across its top
    reach = k["mouth_r"] + k["wall"] + _RIM_OUT + 6.0
    port = _diamond_port(x0=k["base_r"] - 8.0, x1=reach,
                         z_center=k["z_water"], half_w=_OVERFLOW_W,
                         up=_OVERFLOW_W * 1.4, down=_OVERFLOW_W * 1.1)
    port.apply_transform(trimesh.transformations.rotation_matrix(
        math.pi / _RIBS, [0, 0, 1]))
    out.append(port)
    # the notch you pour through, straddling the rim
    notch = trimesh.creation.cylinder(radius=_FILL_R, height=2.0 * _FILL_DEPTH,
                                      sections=48)
    notch.apply_translation((k["mouth_r"] + 0.5 * k["wall"], 0.0,
                             k["depth"] + _FILL_DEPTH - _FILL_DEPTH * 0.5))
    notch.apply_transform(trimesh.transformations.rotation_matrix(
        math.pi, [0, 0, 1]))
    out.append(notch)
    return out


def build_replica_reservoir(p: PotParams) -> trimesh.Trimesh:
    """The bucket: prints standing on its base, no supports."""
    check_replica(p)
    sec = _round(p)
    body = lathe(reservoir_rings(p), sec, decorate=False)
    cavity = lathe(reservoir_bore_rings(p), sec, decorate=False)
    body = _boolean("difference", [body, cavity])
    if p.replica_plumbing and reservoir_plan(p)["stand"] >= 1.0:
        body = _boolean("union",
                        [body, _boolean("intersection", [_ribs(p), cavity])])
    cutters = _reservoir_cutters(p)
    if cutters:
        body = _boolean("difference", [body] + cutters)
    return _finish(body, center=False)


# ---------------------------------------------------------------------------
# the wick
# ---------------------------------------------------------------------------
def build_replica_wick(p: PotParams) -> trimesh.Trimesh:
    """A cup that drops through the pot's floor and hangs into the water.

    Its own part, and printed open end up: hung off the pot's floor it
    would leave that floor spanning the whole pot with nothing under it.
    """
    check_replica(p)
    k = reservoir_plan(p)
    r = 0.5 * _WICK_OD
    t = _WICK_WALL
    # tall enough that the flange starts *above* the pot's floor: any
    # lower and the flare fouls the hole it is meant to sit on
    if not wants_wick(p):
        raise ParameterError(
            f"replica_standoff {k['stand']:.0f} mm is too shallow for a wick "
            f"cup - raise it above {_WICK_MIN_STAND:.0f} mm, or leave it and "
            f"let the pot sub-irrigate through its floor holes")
    height = k["stand"] + k["pot"]["floor"] + 1.25 * _WICK_FLANGE + 4.0
    rings = [(r, 0.0), (r, height - 1.25 * _WICK_FLANGE - 3.0),
             (r + _WICK_FLANGE, height - 3.0),        # 39 deg under the flange
             (r + _WICK_FLANGE, height)]
    cup = lathe(rings, _round(p), decorate=False)
    bore = lathe([(r - t, 3.0), (r - t, height + 2.0)], _round(p),
                 decorate=False)
    cup = _boolean("difference", [cup, bore])
    # slots low down, so the water gets in
    ports = []
    for i in range(4):
        a = 2.0 * math.pi * i / 4.0
        port = _diamond_port(x0=-1.0, x1=r + 4.0, z_center=9.0, half_w=3.6,
                             up=5.0, down=4.0)
        port.apply_transform(
            trimesh.transformations.rotation_matrix(a, [0, 0, 1]))
        ports.append(port)
    return _finish(_boolean("difference", [cup] + ports), center=False)


# ---------------------------------------------------------------------------
# how they go together
# ---------------------------------------------------------------------------
def seated_pot(p: PotParams) -> trimesh.Trimesh:
    """The pot, lifted to where it sits in the reservoir."""
    pot = build_replica_pot(p)
    pot.apply_translation((0.0, 0.0, reservoir_plan(p)["z_sit"]))
    return pot
