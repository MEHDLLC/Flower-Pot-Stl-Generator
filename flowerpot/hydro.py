"""Hydroponic tower: stackable column segments with angled plant ports.

Three pieces, all exported in their print orientation, no supports:

**Segment** - a circular column section.  A chamfered spigot at the bottom
drops into the plain mouth of the segment below, so any number stack into
a tower.  Plant ports spiral up the column: angled sockets a net cup sits
in, tilted ``port_angle`` degrees above horizontal so the plant grows out
and up while water trickling down the column feeds the roots.

The port angle is where printability lives: a round port tilted A degrees
above horizontal has its worst overhang at ``90 - A`` degrees, so the
default 48 comes out at 42 - inside the no-support budget with margin.
Anything below 46 is rejected rather than silently printing badly.

**Net cup** - a slotted tapered basket with a lip, printed lip-down.  Fill
with growing medium; the open tip and the slots let roots reach the water.

**Cap** - a plug for the top segment with a hole for the drip line or a
low-flow pump hose, printed disc-down.

The reservoir is any watertight vessel - a bucket, or a generated pot with
``drainage_pattern none`` - that the bottom segment stands in.
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

_SPIGOT_H = 12.0        # stacking spigot height
_SPIGOT_CLEAR = 0.4     # radial slip fit into the segment below
_PORT_WALL = 3.0        # port shroud wall
_PORT_STICKOUT = 22.0   # how far the port tube leaves the column
_CUP_LIP = 4.0          # net cup lip width past the bore
_CUP_LEN = 55.0         # net cup basket length


def _round_section(p: PotParams):
    return make_section(p.with_(pot_style="classic_tapered",
                                surface_texture="none", belly=0.0))


def _shroud_start_r(p: PotParams) -> float:
    """Radial start of the port tube.  Deep enough that the tube's entire
    back disc sits inside the cavity (max radius R_in - 2), so the cavity
    re-subtraction swallows the tilted back cap whole - otherwise its lower
    edge pokes out through the downhill side of the wall as a 48-degree
    overhang."""
    a = math.radians(p.port_angle)
    rs = p.port_bore / 2.0 + _PORT_WALL
    R_in = p.tower_diameter / 2.0 - p.wall_thickness
    return R_in - rs * math.sin(a) - 2.0


def _port_frames(p: PotParams) -> list[tuple[float, float]]:
    """(angle around the column, center height) for each port.

    Two ceilings bound the top port: the wall opening must stay inside the
    wall, and - stricter - the shroud tube leans up and inward as it rises,
    so its upper inner edge must clear the stacking zone (the mouth and the
    spigot of the segment above).  Otherwise the stacked tower collides.
    """
    n = max(1, int(p.ports_per_segment))
    a = math.radians(p.port_angle)
    rs = p.port_bore / 2.0 + _PORT_WALL
    ellipse_half = rs / math.sin(a)
    R_in = p.tower_diameter / 2.0 - p.wall_thickness
    start_r = _shroud_start_r(p)

    z0 = _SPIGOT_H + 8.0 + ellipse_half
    # where the shroud's upper inner edge crosses back out of r = R_in
    stack_zone = (p.segment_height - _SPIGOT_H - 2.0
                  - rs * math.cos(a)
                  - math.tan(a) * (R_in - start_r + rs * math.sin(a)))
    z1 = min(p.segment_height - 6.0 - ellipse_half, stack_zone)
    if z1 < z0:
        raise ParameterError(
            "segment_height is too short for these ports - raise it or "
            "shrink port_bore"
        )
    step = (z1 - z0) / max(1, n - 1) if n > 1 else 0.0
    return [(2.0 * math.pi * k / n, z0 + k * step) for k in range(n)]


def _port_cylinder(p: PotParams, radius: float, length: float,
                   start_r: float, angle: float, z: float) -> trimesh.Trimesh:
    """A cylinder along the port axis (port_angle above horizontal),
    starting ``start_r`` from the column axis, rotated to ``angle``."""
    cyl = trimesh.creation.cylinder(radius=radius, height=length, sections=64)
    a = math.radians(p.port_angle)
    axis = np.array([math.cos(a), 0.0, math.sin(a)])
    cyl.apply_transform(
        trimesh.transformations.rotation_matrix(math.pi / 2.0 - a, [0, 1, 0]))
    cyl.apply_translation(np.array([start_r, 0.0, z]) + axis * (length / 2.0))
    cyl.apply_transform(trimesh.transformations.rotation_matrix(angle, [0, 0, 1]))
    return cyl


def build_hydro_segment(p: PotParams) -> trimesh.Trimesh:
    """One stackable column segment with its plant ports."""
    _validate(p)
    section = _round_section(p)
    wt = p.wall_thickness
    R = p.tower_diameter / 2.0
    R_in = R - wt
    r_sp = R_in - _SPIGOT_CLEAR                      # spigot slips inside R_in
    flare_h = (R - r_sp) * math.tan(math.radians(48.0))
    h = p.segment_height

    outer = lathe(resample([(r_sp, 0.0), (r_sp, _SPIGOT_H),
                            (R, _SPIGOT_H + flare_h), (R, h)], 2.0),
                  section, False)
    # cavity: narrow through the spigot, widening at 48 deg above it
    r_cav0 = r_sp - wt
    cav_flare = (R_in - r_cav0) * math.tan(math.radians(48.0))
    cavity_rings = [(r_cav0, -1.0), (r_cav0, _SPIGOT_H + 2.0),
                    (R_in, _SPIGOT_H + 2.0 + cav_flare), (R_in, h + 1.0)]
    cavity = lathe(resample(cavity_rings, 2.0), section, False)

    rb = p.port_bore / 2.0
    a = math.radians(p.port_angle)
    shrouds, bores = [], []
    start_r = _shroud_start_r(p)
    # the tube must still reach _PORT_STICKOUT past the wall from its
    # deeper start, and the bore must start deep enough that its own back
    # disc is inside the cavity too (a buried cutter cap would leave a
    # tilted wall inside the port instead of a through hole)
    length = (R - start_r) / math.cos(a) + _PORT_STICKOUT + 4.0
    bore_start = R_in - rb * math.sin(a) - 6.0
    for angle, z in _port_frames(p):
        shrouds.append(_port_cylinder(p, rb + _PORT_WALL, length,
                                      start_r, angle, z))
        bores.append(_port_cylinder(p, rb,
                                    length + (start_r - bore_start) + 8.0,
                                    bore_start, angle, z))

    body = _boolean("union", [
        _boolean("difference", [outer, cavity])] + shrouds)
    # re-subtract the cavity: it shaves the shroud stubs flush with the
    # inner wall (a stub's tilted end cap inside the column would be a
    # 48-degree ceiling - the one face this design must not have)
    body = _boolean("difference", [body, cavity] + bores)
    return _finish(body, center=False)


def build_hydro_cup(p: PotParams) -> trimesh.Trimesh:
    """Slotted net cup for the ports, exported lip-down (print orientation)."""
    _validate(p)
    section = _round_section(p)
    rb = p.port_bore / 2.0
    r_body = rb - 0.5                                # slip fit in the bore
    r_tip = max(10.0, r_body * 0.55)
    lip_t = 3.0

    outer = lathe(resample([(rb + _CUP_LIP, 0.0), (rb + _CUP_LIP, lip_t),
                            (r_body, lip_t + 2.0), (r_tip, lip_t + _CUP_LEN)],
                           2.0), section, False)
    wall = 2.0
    bore = lathe(resample([(r_body - wall, -1.0),
                           (r_tip - wall, lip_t + _CUP_LEN + 2.0)], 2.0),
                 section, False)

    cutters = [bore]
    for k in range(6):                               # root slots, pointed ends
        a = k * math.pi / 3.0
        slot = _diamond_port(x0=r_tip - wall - 4.0, x1=rb + 2.0,
                             z_center=lip_t + _CUP_LEN * 0.5,
                             half_w=1.6, up=_CUP_LEN * 0.34, down=_CUP_LEN * 0.34)
        slot.apply_transform(
            trimesh.transformations.rotation_matrix(a, [0, 0, 1]))
        cutters.append(slot)

    return _finish(_boolean("difference", [outer] + cutters), center=False)


def build_hydro_cap(p: PotParams) -> trimesh.Trimesh:
    """Top plug with a drip-line hole, exported disc-down (print orientation)."""
    _validate(p)
    section = _round_section(p)
    wt = p.wall_thickness
    R = p.tower_diameter / 2.0
    r_sp = R - wt - _SPIGOT_CLEAR
    disc_t = 4.0

    disc = lathe(resample([(R, 0.0), (R, disc_t)], 2.0), section, False)
    ring = lathe(resample([(r_sp, disc_t - 1.0), (r_sp, disc_t + _SPIGOT_H)],
                          2.0), section, False)
    ring_bore = lathe(resample([(r_sp - wt, disc_t - 2.0),
                                (r_sp - wt, disc_t + _SPIGOT_H + 1.0)], 2.0),
                      section, False)
    hole = trimesh.creation.cylinder(radius=p.drip_hole_diameter / 2.0,
                                     height=disc_t + _SPIGOT_H + 8.0, sections=64)
    hole.apply_translation((0.0, 0.0, disc_t / 2.0))

    body = _boolean("union", [disc, ring])
    return _finish(_boolean("difference", [body, ring_bore, hole]), center=False)


def _validate(p: PotParams) -> None:
    if p.port_angle < 46.0:
        raise ParameterError(
            f"port_angle {p.port_angle} puts the port underside past the "
            f"overhang limit (worst face = {90 - p.port_angle:.0f} deg) - "
            f"use 46 or steeper"
        )
    R_in = p.tower_diameter / 2.0 - p.wall_thickness
    if p.port_bore / 2.0 + _PORT_WALL > R_in - 6.0:
        raise ParameterError(
            "port_bore does not fit this tower_diameter - widen the tower "
            "or shrink the ports"
        )
    n = max(1, int(p.ports_per_segment))
    circumference = math.pi * p.tower_diameter
    if n * (p.port_bore + 2 * _PORT_WALL + 8.0) > circumference:
        raise ParameterError(
            f"{n} ports of {p.port_bore} mm do not fit around a "
            f"{p.tower_diameter} mm column"
        )
    _port_frames(p)
