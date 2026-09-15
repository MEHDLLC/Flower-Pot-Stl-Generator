"""The three things that go under a pot you did not print.

``generate_saucer`` already makes a tray for a pot this generator built,
and it sizes itself by measuring that pot.  This module is for the other
case - the nursery pot, the glazed one from the shop, the one already full
of soil - where the only numbers available are the ones you can get a tape
measure to.  So everything here is driven by **one measurement**: the
diameter of the pot's base.

* **tray** - a drip saucer with a waffle floor, so the pot stands on ribs
  and the water sits in the channels between them rather than round the
  pot's feet.
* **riser** - a foot.  Print three (or four) and the pot stands clear of
  whatever it is on, which is how you stop a ring on the furniture and how
  air gets under a pot that has just been watered.
* **mesh** - a pierced disc for the bottom of the pot, to keep the soil on
  the inside of the drainage holes.

Sizing from a pot you did not make
----------------------------------
``under_pot_size`` is a nominal nursery size and nothing more.  A pot sold
as a 6 inch pot is 6 inches across the **top**; its base is narrower, and
by how much is up to whoever moulded it.  The table takes
``_BASE_RATIO`` of the nominal top, which is about where they land - near
enough to print a saucer that works, not near enough to argue with a tape
measure.  Measure yours and set ``under_pot_base`` instead; every part here
is derived from that one number, so one measurement fixes all three.

Why a waffle
------------
A flat saucer puts the pot's base in the water it just drained, which is
the thing a saucer is supposed to prevent.  Ribs lift it clear, and the
water goes in the channels.  They are **crossing** ribs rather than radial
fins because the pot's base has to land on at least three of them wherever
it is put down, and a radial fan leaves the middle of the tray empty.

Every rib is a vertical extrusion with a flat top, so the whole floor
prints as walls and ceilings-facing-up.  The water the tray holds is the
volume under the rib tops, which is what the warning reports - above them
the pot is standing in it again.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _finish, lathe
from .params import ParameterError, PotParams
from .profile import slope_budget
from .sections import Section

#: Nominal nursery sizes, in millimetres across the **top**.  Inches are a
#: fact; what the base of such a pot measures is not, which is what
#: ``_BASE_RATIO`` is for.
NURSERY = {"3in": 76.2, "4in": 101.6, "5in": 127.0, "6in": 152.4,
           "7in": 177.8, "8in": 203.2, "10in": 254.0, "12in": 304.8}
_BASE_RATIO = 0.75
#: ... and a nursery pot is about as tall as it is wide across the top.
#: Both are typicals, not measurements.
_HEIGHT_RATIO = 0.95

PARTS = ("none", "set", "tray", "riser", "mesh")


def nursery_dims(size: str, top: float, base: float, height: float,
                 prefix: str) -> dict:
    """The three measurements of a nursery pot, and the taper they imply.

    ``size`` is either "custom" - in which case the three numbers are used
    as given - or a nominal entry in :data:`NURSERY`, which fills all three
    in from typicals.  Shared by everything that has to fit round a pot it
    did not make; ``prefix`` only names the fields in the error messages.
    """
    if size == "custom":
        top, base, height = float(top), float(base), float(height)
    elif size in NURSERY:
        top = NURSERY[size]
        base, height = _BASE_RATIO * top, _HEIGHT_RATIO * top
    else:
        raise ParameterError(
            f"unknown {prefix}_pot_size {size!r}; choose from "
            f"{['custom'] + sorted(NURSERY)}")
    if not 40.0 <= top <= 500.0:
        raise ParameterError(
            f"{prefix}_pot_top should be 40-500 mm, measured across the top "
            f"of the nursery pot")
    if not 0.35 * top <= base < top:
        raise ParameterError(
            f"a {base:.0f} mm base under a {top:.0f} mm top is not a nursery "
            f"pot - {prefix}_pot_base wants to be between {0.35 * top:.0f} "
            f"and {top:.0f} mm")
    if not 0.3 * top <= height <= 3.0 * top:
        raise ParameterError(
            f"{prefix}_pot_height {height:.0f} mm is out of proportion with a "
            f"{top:.0f} mm pot - measure it again")
    return dict(top_r=0.5 * top, base_r=0.5 * base, height=height,
                slope=(0.5 * top - 0.5 * base) / height)

_RESERVE = 0.10
_RIB_W = 2.6             # waffle rib width
_RIB_JUNCTION = 3.0      # radius taken out of every crossing
_RIB_CHANNELS = 6.0      # channels wanted across the tray
_RIM_FLARE = 6.0         # degrees the tray's wall leans out
_TRAY_FLOOR = 3.0        # least floor under a tray

_RISER_TAPER = 0.26      # dr/dz of a foot's side, inwards going up
_RISER_DISH = 0.55       # of the foot's top, recessed for the pot to sit in
_RISER_EDGE = 6.0        # feet keep this far inside the pot's base

_MESH_T = 2.2            # disc thickness
_MESH_MIN_R = 1.4        # hole radius: under 3 mm across, soil is all
#                          that gets through
_MESH_WEB = 1.6          # least web left between two holes
_MESH_LEGS = 4
_MESH_LEG_H = 2.5


# ---------------------------------------------------------------------------
# sizing
# ---------------------------------------------------------------------------
def _round(p: PotParams) -> Section:
    return Section(p.with_(pot_style="classic_tapered",
                           surface_texture="none"))


def wall_of(p: PotParams) -> float:
    return max(2.2, p.wall_thickness)


def pot_base(p: PotParams) -> float:
    """The one measurement everything here is cut from."""
    if p.under_pot_size == "custom":
        return float(p.under_pot_base)
    if p.under_pot_size not in NURSERY:
        raise ParameterError(
            f"unknown under_pot_size {p.under_pot_size!r}; choose from "
            f"{['custom'] + sorted(NURSERY)}")
    return _BASE_RATIO * NURSERY[p.under_pot_size]


def plan(p: PotParams) -> dict:
    base = pot_base(p)
    if not 40.0 <= base <= 500.0:
        raise ParameterError(
            f"a {base:.0f} mm pot base is outside what these parts are for - "
            f"under_pot_base should be 40-500 mm, measured across the bottom "
            f"of the pot")
    t = wall_of(p)
    floor = max(_TRAY_FLOOR, p.base_thickness)
    waffle = max(0.0, float(p.under_waffle))
    rim = max(0.0, float(p.under_rim))
    if waffle and waffle < 2.5:
        raise ParameterError(
            "under_waffle under 2.5 mm is a texture, not a stand-off - give "
            "the water somewhere to go, or set it to 0 for a flat saucer")
    r_in = 0.5 * base + float(p.under_clearance)
    depth = floor + waffle + rim
    if depth <= floor + 2.0:
        raise ParameterError(
            "under_waffle and under_rim together leave the tray no wall at "
            "all - raise one of them")
    return dict(s=slope_budget(p, _RESERVE), wall=t, base=base, floor=floor,
                waffle=waffle, rim=rim, r_in=r_in, depth=depth,
                flare=math.tan(math.radians(_RIM_FLARE)))


def rib_pitch(p: PotParams) -> float:
    k = plan(p)
    return (2.0 * k["r_in"]) / _RIB_CHANNELS


def tray_millilitres(p: PotParams) -> float:
    """Water held under the rib tops - above them the pot is standing in
    it again, so that is the number worth quoting."""
    k = plan(p)
    if not k["waffle"]:
        return 0.0
    gross = math.pi * k["r_in"] ** 2 * k["waffle"]
    ribs = _waffle(p)
    return max(gross - (ribs.volume if ribs is not None else 0.0),
               0.0) / 1000.0


def mesh_diameter(p: PotParams) -> float:
    """The disc drops *inside* the pot, so it is the inside of the base it
    has to fit - a couple of wall thicknesses in from the outside."""
    if float(p.under_mesh_diameter) > 0.0:
        return float(p.under_mesh_diameter)
    return max(20.0, plan(p)["base"] - 8.0)


def mesh_grid(p: PotParams) -> dict:
    """Hexagonally packed holes, sized from the open fraction you asked for.

    Hex packing because it is the arrangement that gets the most open area
    for a given web between holes, and the web is what actually limits
    this: below a couple of extrusions the disc stops being a disc.
    """
    r_disc = 0.5 * mesh_diameter(p)
    frac = float(np.clip(p.under_mesh_open, 0.05, 0.75))
    # in a hex array of pitch d with holes of radius a, the open fraction is
    # (2 pi / sqrt(3)) (a/d)^2 - invert for a/d, then pick d from the web
    ratio = math.sqrt(frac * math.sqrt(3.0) / (2.0 * math.pi))
    # the web is what sets the scale: pitch - 2a >= web with a = ratio*pitch
    pitch = _MESH_WEB / max(1.0 - 2.0 * ratio, 1e-6)
    hole = ratio * pitch
    if hole < _MESH_MIN_R:          # too fine to drain: open the holes out
        hole = _MESH_MIN_R          # and let the pitch follow them
        pitch = hole / ratio
    if 2.0 * hole + _MESH_WEB > pitch + 1e-9:
        raise ParameterError(
            f"under_mesh_open {p.under_mesh_open:.2f} leaves under "
            f"{_MESH_WEB:.1f} mm of web between holes - it has to come down")
    sites = []
    rows = int(math.ceil(2.0 * r_disc / (pitch * math.sqrt(3.0) / 2.0))) + 2
    cols = int(math.ceil(2.0 * r_disc / pitch)) + 2
    edge = r_disc - hole - 1.2                     # keep a rim round the lot
    for j in range(-rows, rows + 1):
        y = j * pitch * math.sqrt(3.0) / 2.0
        for i in range(-cols, cols + 1):
            x = (i + 0.5 * (j % 2)) * pitch
            if math.hypot(x, y) <= edge:
                sites.append((x, y))
    return dict(hole=hole, pitch=pitch, sites=sites, r_disc=r_disc,
                open_fraction=len(sites) * math.pi * hole ** 2
                / (math.pi * r_disc ** 2))


def check_underpot(p: PotParams) -> list[str]:
    out: list[str] = []
    if p.underpot not in PARTS:
        raise ParameterError(
            f"unknown underpot {p.underpot!r}; choose from {list(PARTS)[1:]}")
    if p.underpot == "none":
        return out
    if int(p.under_feet) not in (3, 4):
        raise ParameterError("under_feet should be 3 or 4")
    k = plan(p)
    pot_base(p)
    if p.under_pot_size != "custom":
        out.append(
            f"{p.under_pot_size} is a nominal size: that is the pot's width "
            f"across the TOP, and this takes {_BASE_RATIO:.2f} of it - "
            f"{k['base']:.0f} mm - as the base. Measure yours and set "
            f"under_pot_base if it matters")
    if p.underpot in ("tray", "set"):
        if k["waffle"]:
            out.append(
                f"the tray holds about {tray_millilitres(p):.0f} ml under the "
                f"rib tops, which is as much as it can hold before the pot is "
                f"standing in it again")
        else:
            out.append(
                "under_waffle 0 makes a flat saucer: it will hold more water, "
                "and the pot will be sitting in all of it")
    if p.underpot in ("riser", "set"):
        out.append(
            f"print {p.under_feet} risers and stand the pot on them spaced "
            f"evenly round a {riser_ring_diameter(p):.0f} mm circle - as far "
            f"out as they go without showing past the pot. Three cannot rock "
            f"on an uneven surface "
            f"and four can - four spreads the load, so take four on a heavy "
            f"pot and a flat shelf")
    if p.underpot in ("mesh", "set"):
        g = mesh_grid(p)
        out.append(
            f"the mesh disc is {mesh_diameter(p):.0f} mm across with "
            f"{len(g['sites'])} holes of {2 * g['hole']:.1f} mm, about "
            f"{100 * g['open_fraction']:.0f}% open"
            + (" - it prints legs up and goes in legs down"
               if p.under_mesh_legs else ""))
    return out


# ---------------------------------------------------------------------------
# the tray
# ---------------------------------------------------------------------------
def tray_rings(p: PotParams) -> list[tuple[float, float]]:
    k = plan(p)
    r0 = k["r_in"] + k["wall"]
    return [(r0, 0.0), (r0 + k["flare"] * k["depth"], k["depth"])]


def tray_cavity_rings(p: PotParams) -> list[tuple[float, float]]:
    k = plan(p)
    return [(k["r_in"], k["floor"]),
            (k["r_in"] + k["flare"] * (k["depth"] - k["floor"]) + 2.0,
             k["depth"] + 2.0)]


def _waffle(p: PotParams) -> trimesh.Trimesh | None:
    """Crossing ribs standing off the floor.

    Vertical extrusions with flat tops: nothing here leans at all, which is
    the point of a waffle over anything moulded.  Clipped to the cavity
    afterwards so every rib dies into the wall instead of stopping short of
    it and leaving a slot that traps water.
    """
    k = plan(p)
    if not k["waffle"]:
        return None
    pitch = rib_pitch(p)
    reach = 2.0 * k["r_in"] + 6.0
    z_mid = k["floor"] + 0.5 * k["waffle"]
    n = int(math.floor(k["r_in"] / pitch))
    bars = []
    for i in range(-n, n + 1):
        off = i * pitch
        for axis in (0, 1):
            extents = ((reach, _RIB_W, k["waffle"]) if axis == 0
                       else (_RIB_W, reach, k["waffle"]))
            bar = trimesh.creation.box(extents=extents)
            bar.apply_translation((0.0, off, z_mid) if axis == 0
                                  else (off, 0.0, z_mid))
            bars.append(bar)
    grid = _boolean("union", bars)
    # break every crossing.  A continuous waffle is a tray full of closed
    # cells: each one keeps its own puddle and none of them can level with
    # the others.  Taking a disc out of each junction lets the water round
    # the corner, and a vertical cut leaves nothing to hold up
    voids = []
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            hub = trimesh.creation.cylinder(radius=_RIB_JUNCTION,
                                            height=k["waffle"] + 4.0,
                                            sections=24)
            hub.apply_translation((i * pitch, j * pitch, z_mid))
            voids.append(hub)
    grid = _boolean("difference", [grid, trimesh.util.concatenate(voids)])
    disc = trimesh.creation.cylinder(radius=k["r_in"] - 0.3,
                                     height=k["waffle"] + 2.0, sections=96)
    disc.apply_translation((0.0, 0.0, z_mid))
    return _boolean("intersection", [grid, disc])


def build_under_tray(p: PotParams) -> trimesh.Trimesh:
    """The drip tray: prints on its own floor, no supports."""
    check_underpot(p)
    sec = _round(p)
    body = lathe(tray_rings(p), sec, decorate=False)
    body = _boolean("difference",
                    [body, lathe(tray_cavity_rings(p), sec, decorate=False)])
    ribs = _waffle(p)
    if ribs is not None:
        body = _boolean("union", [body, ribs])
    return _finish(body, center=False)


# ---------------------------------------------------------------------------
# the riser
# ---------------------------------------------------------------------------
def build_under_riser(p: PotParams) -> trimesh.Trimesh:
    """One foot.  Print ``under_feet`` of them.

    A truncated cone, narrowing going up, which is the direction that
    cannot overhang; and a dished top, which is a cavity opening upwards,
    so the pot's edge sits in it and will not walk off.
    """
    check_underpot(p)
    k = plan(p)
    h = float(p.under_riser_height)
    if not 6.0 <= h <= 80.0:
        raise ParameterError("under_riser_height should be 6-80 mm")
    r_top = max(9.0, 0.10 * k["base"])
    r_bot = r_top + _RISER_TAPER * h
    sec = _round(p)
    body = lathe([(r_bot, 0.0), (r_top, h)], sec, decorate=False)
    dish_r = _RISER_DISH * r_top
    dish_d = min(0.30 * h, 0.8 * r_top)
    # the dish is a cone opening upwards: a flat-bottomed pocket would be a
    # ceiling the moment anything bridged it
    cup = lathe([(0.05, h - dish_d), (dish_r, h), (dish_r + 2.0, h + 2.0)],
                sec, decorate=False)
    return _finish(_boolean("difference", [body, cup]), center=False)


def riser_radius(p: PotParams) -> float:
    """Radius of the foot where it meets the ground."""
    k = plan(p)
    h = float(p.under_riser_height)
    return max(9.0, 0.10 * k["base"]) + _RISER_TAPER * h


def riser_ring_diameter(p: PotParams) -> float:
    """The circle to stand the feet on: as far out as they go without any
    of the foot showing past the edge of the pot, because a foot inboard of
    the base is a foot the pot can tip over."""
    k = plan(p)
    return max(0.30 * k["base"],
               k["base"] - 2.0 * riser_radius(p) - 2.0 * _RISER_EDGE)


# ---------------------------------------------------------------------------
# the mesh disc
# ---------------------------------------------------------------------------
def build_under_mesh(p: PotParams) -> trimesh.Trimesh:
    """A pierced disc for the bottom of the pot.

    Every hole is a vertical bore, which is the one cut that leaves nothing
    to hold up.  The legs print pointing **up** and the disc goes in the pot
    the other way round - printed downwards they would be four pillars with
    a disc bridged across them.
    """
    check_underpot(p)
    g = mesh_grid(p)
    sec = _round(p)
    disc = lathe([(g["r_disc"], 0.0), (g["r_disc"], _MESH_T)], sec,
                 decorate=False)
    solids = [disc]
    if p.under_mesh_legs:
        ring = 0.62 * g["r_disc"]
        for i in range(_MESH_LEGS):
            a = 2.0 * math.pi * i / _MESH_LEGS
            leg = trimesh.creation.cylinder(radius=2.6, height=_MESH_LEG_H,
                                            sections=24)
            leg.apply_translation((ring * math.cos(a), ring * math.sin(a),
                                   _MESH_T + 0.5 * _MESH_LEG_H))
            solids.append(leg)
    body = _boolean("union", solids) if len(solids) > 1 else disc
    holes = []
    for x, y in g["sites"]:
        bore = trimesh.creation.cylinder(radius=g["hole"], height=30.0,
                                         sections=20)
        bore.apply_translation((x, y, 0.0))
        holes.append(bore)
    return _finish(_boolean("difference", [body] + holes), center=False)
