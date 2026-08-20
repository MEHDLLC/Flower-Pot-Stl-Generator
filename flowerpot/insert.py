"""Universal reservoir insert: drop it into ANY pot to make it self-watering.

Two pieces, both exported ready to print (no supports, no flipping in the
slicer):

**Platform** - a false floor that stands on a skirt wall at
``reservoir_height`` above the pot's own floor, which becomes the tank.
Soil sits on the deck; a slotted wick cone descends into the water and
soil pressed into it wicks moisture up.  The deck carries drainage holes
(excess top-watering drains into the reservoir), stiffening fins, and a
collared socket for the fill tube.  The outline mirrors the pot:
round, square, hexagonal or octagon, with rounded corners, plus a small
draft on the skirt so it drops into tapered pots.  Exported deck-down,
which is also its print orientation - every feature rises from the deck.

**Fill tube** - funnel mouth, straight tube, tip mitered at 50 degrees so
water can always exit even with the tube resting on the pot floor.
Exported funnel-down (its print orientation); in use it slips through the
platform's socket.

Because the pot's own bottom is the tank, the pot must be watertight -
use a cachepot, a generated pot with ``drainage_pattern none``, or plug
the hole.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _finish, lathe
from .params import ParameterError, PotParams
from .profile import resample
from .sections import make_section
from .selfwatering import _diamond_port

#: outline choices -> polygon side count (1 = round)
INSERT_SHAPES = {"round": 1, "square": 4, "hexagonal": 6, "octagon": 8}

_DECK_T = 4.0            # deck slab thickness
_DRAFT_DEG = 3.0         # inward skirt draft so it drops into tapered pots
_FIT_CLEARANCE = 0.8     # total width clearance against the measured pot
_CUP_WALL = 2.4          # wick cone wall
_FUNNEL_RISE = 14.0
_FUNNEL_FLARE = 6.0
_TUBE_WALL = 2.4


def _shape_params(p: PotParams) -> PotParams:
    """A params clone whose Section machinery yields the insert outline."""
    sides = INSERT_SHAPES[p.insert_shape]
    if sides == 1:
        return p.with_(pot_style="classic_tapered", surface_texture="none",
                       belly=0.0)
    return p.with_(pot_style="hexagonal", hex_sides=sides,
                   surface_texture="none")


def _corner_radius(p: PotParams) -> float:
    """Corner radius that puts the ACROSS-FLATS width at insert_width.

    Corner rounding is a Minkowski disc, which pushes the flats outward by
    the rounding amount - solve for that so square inserts do not eat their
    own fit clearance: half = (R - cr) * cos(pi/n) + cr.
    """
    sides = INSERT_SHAPES[p.insert_shape]
    half = (p.insert_width - _FIT_CLEARANCE) / 2.0
    if sides == 1:
        return half
    cr = min(p.hex_corner_round, half * 0.4)
    return (half - cr) / math.cos(math.pi / sides) + cr


def _flat_radius(p: PotParams) -> float:
    return (p.insert_width - _FIT_CLEARANCE) / 2.0


def build_insert_platform(p: PotParams) -> trimesh.Trimesh:
    """The false floor, built (and exported) in its print orientation:
    deck on the plate, skirt / cone / fins / collar rising."""
    _validate(p)
    sp = _shape_params(p)
    section = make_section(sp)
    sides = INSERT_SHAPES[p.insert_shape]
    sf = 1.0 / math.cos(math.pi / sides) if sides > 1 else 1.0

    wt = p.wall_thickness
    R = _corner_radius(p)
    R_flat = _flat_radius(p)
    height = _DECK_T + p.reservoir_height
    draft = math.tan(math.radians(_DRAFT_DEG)) * p.reservoir_height

    body = lathe(resample([(R, 0.0), (R - draft, height)], p.vertical_step),
                 section, decorate=False)
    cavity = lathe(resample([(R - wt * sf, _DECK_T),
                             (R - draft - wt * sf, height + 5.0)],
                            p.vertical_step), section, decorate=False)

    # ---- wick cone: rises from the deck, closed near-point tip ----------
    round_sec = make_section(sp.with_(pot_style="classic_tapered"))
    rc0 = min(26.0, R_flat * 0.35)
    cup_h = height - 2.0            # in use: tip stops 2 mm above pot floor
    cone = lathe(resample([(rc0 + 2.0, 0.5), (1.2, cup_h)], 2.0), round_sec, False)
    cone_bore = lathe(resample([(rc0 + 2.0 - _CUP_WALL * 1.5, -2.0),
                                (0.4, cup_h - _CUP_WALL * 1.8)], 2.0),
                      round_sec, False)

    # ---- fill tube socket ------------------------------------------------
    rb = p.refill_tube_bore / 2.0
    hole_r = rb + _TUBE_WALL + 0.3           # tube outer + slip fit
    tube_x = R_flat - wt - hole_r - 2.0
    collar = trimesh.creation.cylinder(radius=hole_r + 2.4, height=_DECK_T + 8.0,
                                       sections=64)
    collar.apply_translation((tube_x, 0.0, (_DECK_T + 8.0) / 2.0))
    hole = trimesh.creation.cylinder(radius=hole_r, height=60.0, sections=64)
    hole.apply_translation((tube_x, 0.0, 10.0))

    # ---- stiffening fins under the deck (in use) --------------------------
    fins = []
    for k in range(4):
        a = math.pi / 4.0 + k * math.pi / 2.0
        fin = trimesh.creation.box(extents=(R_flat - wt - rc0 - 4.0, 2.4, 10.0))
        fin.apply_translation(((rc0 + R_flat - wt) / 2.0 - 1.0, 0.0, _DECK_T + 5.0))
        rot = trimesh.transformations.rotation_matrix(a, [0, 0, 1])
        fin.apply_transform(rot)
        fins.append(fin)

    body = _boolean("union", [body, cone, collar] + fins)

    # ---- cutters ----------------------------------------------------------
    cutters = [cavity, cone_bore, hole]

    # wick slots: pointed-top diamonds so nothing bridges in print
    slot_z = 0.35 * cup_h
    for k in range(6):
        a = math.pi / 6.0 + k * math.pi / 3.0
        slot = _diamond_port(x0=2.0, x1=rc0 + 2.0, z_center=slot_z,
                             half_w=1.1, up=14.0, down=10.0)
        rot = trimesh.transformations.rotation_matrix(a, [0, 0, 1])
        slot.apply_transform(rot)
        cutters.append(slot)

    # deck drainage: a ring of holes, skipping any that would foul the socket
    rr = (rc0 + 4.0 + R_flat - wt) / 2.0
    n = max(4, int(p.num_drainage_holes))
    dr = min(p.drainage_hole_radius, 5.0)
    for k in range(n):
        a = math.pi / n + 2.0 * math.pi * k / n
        x, y = rr * math.cos(a), rr * math.sin(a)
        if math.hypot(x - tube_x, y) < hole_r + dr + 5.0:
            continue
        cyl = trimesh.creation.cylinder(radius=dr, height=_DECK_T + 6.0, sections=32)
        cyl.apply_translation((x, y, _DECK_T / 2.0))
        cutters.append(cyl)

    # level notches in the skirt's standing edge (open cuts, no roofs)
    for k in range(4):
        a = k * math.pi / 2.0 + math.pi / 4.0
        notch = trimesh.creation.box(extents=(wt * sf + 8.0, 8.0, 8.0))
        notch.apply_translation((R_flat - wt / 2.0, 0.0, height + 1.0))
        rot = trimesh.transformations.rotation_matrix(a, [0, 0, 1])
        notch.apply_transform(rot)
        cutters.append(notch)

    return _finish(_boolean("difference", [body] + cutters), center=False)


def build_insert_tube(p: PotParams) -> trimesh.Trimesh:
    """The fill tube, funnel-down (its print orientation)."""
    _validate(p)
    rb = p.refill_tube_bore / 2.0
    r_out = rb + _TUBE_WALL
    r_mouth = r_out + _FUNNEL_FLARE
    L = p.insert_tube_length
    sec = make_section(_shape_params(p).with_(pot_style="classic_tapered"))

    body = lathe(resample([(r_mouth, 0.0), (r_out, _FUNNEL_RISE), (r_out, L)], 2.0),
                 sec, False)
    bore_funnel = lathe(resample([(r_mouth - 2.5, -1.0), (rb, _FUNNEL_RISE + 0.5)],
                                 2.0), sec, False)
    bore = lathe(resample([(rb, _FUNNEL_RISE - 0.5), (rb, L + 1.0)], 2.0), sec, False)

    # miter the far end at 50 deg so water always finds a way out, even with
    # the tube standing square on the pot floor
    B = 12.0 * r_out
    wedge = trimesh.creation.box(extents=(B, B, B))
    wedge.apply_transform(
        trimesh.transformations.rotation_matrix(math.radians(40.0), [0, 1, 0]))
    normal = np.array([math.sin(math.radians(40.0)), 0.0,
                       math.cos(math.radians(40.0))])
    wedge.apply_translation(np.array([0.0, 0.0, L - 1.5]) + normal * (B / 2.0))

    return _finish(_boolean("difference", [body, bore_funnel, bore, wedge]),
                   center=False)


def _validate(p: PotParams) -> None:
    if p.insert_shape not in INSERT_SHAPES:
        raise ParameterError(
            f"unknown insert_shape {p.insert_shape!r}; "
            f"choose from {sorted(INSERT_SHAPES)}"
        )
    if p.insert_width < 80.0:
        raise ParameterError(
            "insert_width under 80 mm leaves no room for the wick cone and "
            "the fill tube side by side"
        )
    rb = p.refill_tube_bore / 2.0
    needed = min(26.0, _flat_radius(p) * 0.35) + (rb + _TUBE_WALL + 0.3) * 2 + 12.0
    if _flat_radius(p) < needed:
        raise ParameterError(
            f"insert_width {p.insert_width} is too tight for a "
            f"{p.refill_tube_bore} mm fill tube next to the wick cone - "
            f"widen the insert or shrink refill_tube_bore"
        )
    if p.insert_tube_length < p.reservoir_height + 30.0:
        raise ParameterError(
            "insert_tube_length must clear the reservoir and the soil - "
            f"use at least {p.reservoir_height + 30.0:.0f} mm"
        )
