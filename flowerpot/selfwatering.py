"""Two-piece self-watering pot set.

The set mirrors the classic printed design: an **outer pot** holds the
water reservoir and carries a built-in refill tube with a funnel mouth,
and an **inner pot** stands inside it on a central wick cup, tops flush.
A cotton rope threaded through the wick holes hangs into the reservoir
and keeps the soil moist by capillary action; pouring into the funnel
tops the reservoir up through a port near the floor.

Printability is designed in, same rules as everything else here:

* the inner pot's floor is a cone falling to the wick cup at
  ``_CONE_DEG`` degrees from horizontal, so the pot prints upright with
  no supports and the cup doubles as the stand that props the soil above
  the water;
* the refill tube leans with the outer wall's taper so it stays fused to
  the wall at every height;
* the reservoir port and the cup notches are elongated-diamond prisms,
  never round horizontal holes - their roofs stay inside the overhang
  budget.

The outer pot keeps the user's style, texture and rim; the inner pot is
a plain round liner (mostly hidden in use).  ``low_poly_faceted`` cannot
host the tube (its facets rotate with height, so no straight tube line
stays fused to the wall) - the validator rejects that combination.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _finish, lathe
from .params import ParameterError, PotParams
from .profile import build_profiles, resample, wall_radius, wall_slope
from .sections import make_section
from .textures import make_texture

_CONE_DEG = 50.0          # inner floor cone, from horizontal (overhang 40 deg)
_TUBE_WALL = 3.0          # refill tube wall thickness
_TUBE_EMBED = 2.0         # how deep the tube fuses into the outer wall
_FUNNEL_RISE = 14.0       # funnel height above the tube
_FUNNEL_FLARE = 6.0       # funnel widens by this much (26 deg slope)
_CUP_WALL_H = 8.0         # straight cup wall below the cone
_RIM_CLEAR = 0.5          # radial reveal between inner rim and outer mouth


# ---------------------------------------------------------------------------
# shared geometry helpers
# ---------------------------------------------------------------------------
def _outer_params(p: PotParams) -> PotParams:
    """The outer pot: user's style, but watertight and straight-bellied
    (the tube must hug a straight wall line)."""
    return p.with_(drainage_pattern="none", belly=0.0, generate_saucer=False,
                   jar_greenhouse=False)


def _poly_min_factor(p: PotParams) -> float:
    """Worst-case (flat-to-center / corner-to-center) ratio of the section."""
    return math.cos(math.pi / p.sides) if p.sides > 1 else 1.0


def _outer_cavity_min(p: PotParams, z: float) -> float:
    """Smallest interior radius of the outer pot at height ``z``."""
    op = _outer_params(p)
    slope = wall_slope(op, z)
    section_factor = 1.0 / _poly_min_factor(op) if op.sides > 1 else 1.0
    corner_cavity = (wall_radius(op, z)
                     - op.wall_thickness * math.hypot(1.0, slope) * section_factor)
    return corner_cavity * _poly_min_factor(op)


def _prism(profile_yz: list[tuple[float, float]], x0: float, x1: float) -> trimesh.Trimesh:
    """Convex prism along X from a (y, z) profile - used for the diamond
    ports whose roofs must slope instead of bridging."""
    n = len(profile_yz)
    verts = ([(x0, y, z) for y, z in profile_yz]
             + [(x1, y, z) for y, z in profile_yz])
    faces = []
    for i in range(1, n - 1):                       # end caps (convex fans)
        faces.append([0, i + 1, i])
        faces.append([n, n + i, n + i + 1])
    for i in range(n):                              # side quads
        j = (i + 1) % n
        faces.append([i, j, n + j])
        faces.append([i, n + j, n + i])
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def _diamond_port(x0: float, x1: float, z_center: float,
                  half_w: float, up: float, down: float) -> trimesh.Trimesh:
    """Elongated diamond prism along X: roof slope = atan(half_w / up)."""
    profile = [(0.0, z_center - down), (half_w, z_center),
               (0.0, z_center + up), (-half_w, z_center)]
    return _prism(profile, x0, x1)


# ---------------------------------------------------------------------------
# outer pot: reservoir + refill tube
# ---------------------------------------------------------------------------
def build_self_watering_outer(p: PotParams) -> trimesh.Trimesh:
    """The reservoir pot with the leaning refill tube and funnel."""
    _validate(p)
    op = _outer_params(p)
    from .build import build_pot
    body = build_pot(op)

    fmin = _poly_min_factor(op)
    surf0 = wall_radius(op, 0.0) * fmin              # wall surface at the tube line
    surf1 = wall_radius(op, p.height) * fmin
    lean = math.atan2(surf1 - surf0, p.height)

    rb = p.refill_tube_bore / 2.0
    r_tube = rb + _TUBE_WALL
    d0 = surf0 + r_tube - _TUBE_EMBED                # tube center at z = 0

    section = make_section(op.with_(pot_style="classic_tapered"))

    def tube_part(rings, decorate=False):
        m = lathe(resample(rings, 2.0), section, decorate)
        m.apply_translation((d0, 0.0, 0.0))
        return m

    h = p.height
    tube = tube_part([(r_tube, -8.0), (r_tube, h + 2.0)])
    # the funnel starts slightly narrower than the tube so its bottom cap is
    # buried inside the tube wall - a cap left exactly coplanar with the tube
    # surface survives the union as stray near-horizontal slivers
    funnel = tube_part([(r_tube - 1.5, h + 1.0),
                        (r_tube + _FUNNEL_FLARE, h + _FUNNEL_RISE)])
    bore = tube_part([(rb, p.base_thickness + 3.0), (rb, h + 2.5)])
    # the funnel bore starts WIDER than the bore and below its top, so the
    # bore's ceiling is swallowed whole - starting narrower would leave an
    # annular ceiling ring hanging at the worst possible angle
    funnel_bore = tube_part([(rb + 1.0, h + 1.5),
                             (r_tube + _FUNNEL_FLARE - 2.5, h + _FUNNEL_RISE + 0.5)])

    # reservoir port: from inside the cavity, through the wall, into the bore
    z_port = p.base_thickness + 8.0
    port = _diamond_port(
        x0=_outer_cavity_min(p, z_port) - 6.0,
        x1=d0 + rb * 0.7,
        z_center=z_port, half_w=4.0, up=8.0, down=6.0,
    )

    # the whole tube assembly leans with the wall so it stays fused
    tilt = trimesh.transformations.rotation_matrix(lean, [0, 1, 0], [d0, 0, 0])
    for part in (tube, funnel, bore, funnel_bore, port):
        part.apply_transform(tilt)

    out = _boolean("union", [body, tube, funnel])
    out = _boolean("difference", [out, bore, funnel_bore, port])
    # the tilted tube dips below the plate: shave the assembly flat at z=0
    # so the whole footprint sits on the bed (plate faces are audit-exempt)
    span = float(max(out.extents)) * 2.0
    floor_box = trimesh.creation.box(
        extents=(span, span, span),
        transform=trimesh.transformations.translation_matrix((0, 0, span / 2.0)),
    )
    out = _boolean("intersection", [out, floor_box])
    # keep the pot axis at the origin: bbox-centring would drag the cavity
    # sideways by half the tube bulge and the inner pot would no longer fit
    return _finish(out, center=False)


# ---------------------------------------------------------------------------
# inner pot: liner with a wick cup
# ---------------------------------------------------------------------------
def _inner_wall_radius(p: PotParams, z_inner: float) -> float:
    """Outside radius of the (round) inner pot in its own frame, which
    starts at the top of the outer pot's floor."""
    return _outer_cavity_min(p, z_inner + p.base_thickness) - p.sw_wall_gap


def inner_height(p: PotParams) -> float:
    """Inner pot height: standing on the outer floor, the rims end flush."""
    return p.height - p.base_thickness


def _cup_radius(p: PotParams, hi: float) -> float:
    """Wick cup radius so the floor cone meets the wall at reservoir height."""
    zj = min(max(p.reservoir_height, _CUP_WALL_H + 8.0), hi * 0.6)
    r_cup = _inner_wall_radius(p, zj) - (zj - _CUP_WALL_H) / math.tan(math.radians(_CONE_DEG))
    return max(r_cup, 12.0), zj


def build_self_watering_inner(p: PotParams) -> trimesh.Trimesh:
    """The plant liner: cup foot, cone floor, wick holes, gap-covering rim."""
    _validate(p)
    hi = inner_height(p)
    wt = p.wall_thickness
    r_cup, zj = _cup_radius(p, hi)
    r_at_j = _inner_wall_radius(p, zj)
    r_top = _inner_wall_radius(p, hi)

    # rim: covers the gap up to a small reveal from the outer mouth.  The
    # chamfer start is iterated because the wall keeps widening below the
    # rim - anchoring the 48 deg angle to the top radius alone comes out
    # shallow and fails the overhang audit.
    rim_h = 6.0
    # size the rim against the cavity at the COLLAR'S BOTTOM, not the mouth:
    # the outer wall tapers, so the cavity is narrowest at the rim's low end
    mouth = _outer_cavity_min(p, p.height - rim_h)
    r_rim = mouth - _RIM_CLEAR
    z_chamfer = hi - rim_h - (r_rim - r_top) * math.tan(math.radians(48.0))
    for _ in range(8):
        run = r_rim - _inner_wall_radius(p, z_chamfer)
        z_chamfer = hi - rim_h - run * math.tan(math.radians(48.0))

    outer_rings = [
        (r_cup, 0.0),
        (r_cup, _CUP_WALL_H),
        (r_at_j, zj),
        (_inner_wall_radius(p, z_chamfer), z_chamfer),
        (r_rim, hi - rim_h),
        (r_rim, hi),
    ]

    def cavity_radius(z: float) -> float:
        eps = 0.4
        lo, hi_ = max(0.0, z - eps), min(hi, z + eps)
        slope = ((_shape_r(p, hi_) - _shape_r(p, lo)) / (hi_ - lo)) if hi_ > lo else 0.0
        return _shape_r(p, z) - wt * math.hypot(1.0, slope)

    inner_rings = [(cavity_radius(z), z) for z in
                   _monotonic([p.base_thickness, _CUP_WALL_H + wt * 1.4,
                               zj + wt * 1.4, z_chamfer, hi])]
    if p.jar_greenhouse:
        from .jar import check_jar_fit, neck_rings
        check_jar_fit(p, cavity_radius(hi))
        tail = neck_rings(p, cavity_radius, hi, 4.0)
        inner_rings = [r for r in inner_rings if r[1] < tail[0][1] - 1e-6] + tail
    else:
        inner_rings.append((inner_rings[-1][0], hi + 4.0))

    ip = p.with_(pot_style="classic_tapered", surface_texture="none")
    section = make_section(ip)
    body = lathe(resample(outer_rings, p.vertical_step, smooth=True), section, False)
    cavity = lathe(resample(inner_rings, p.vertical_step, smooth=True), section, False)
    pot = _boolean("difference", [body, cavity])

    # wick holes: a ring of vertical holes through the lower cone - the rope
    # threads through them into the moat of water around the cup
    cutters = []
    r_holes = r_cup + max(5.0, p.wick_hole_radius + 2.0)
    for k in range(max(1, p.num_wick_holes)):
        a = 2.0 * math.pi * k / max(1, p.num_wick_holes)
        cyl = trimesh.creation.cylinder(radius=p.wick_hole_radius, height=40.0,
                                        sections=32)
        cyl.apply_translation((r_holes * math.cos(a), r_holes * math.sin(a), 14.0))
        cutters.append(cyl)

    # notches at the cup's foot so water can equalise into the cup even when
    # it stands flat on the outer floor (bottom watering)
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        notch = _diamond_port(x0=r_cup - wt - 4.0, x1=r_cup + wt + 2.0,
                              z_center=1.0, half_w=4.0, up=7.0, down=4.0)
        rot = trimesh.transformations.rotation_matrix(a, [0, 0, 1])
        notch.apply_transform(rot)
        cutters.append(notch)

    if p.jar_greenhouse:
        from .jar import seat_cutters
        cutters += seat_cutters(p, hi)

    return _finish(_boolean("difference", [pot] + cutters))


def _shape_r(p: PotParams, z: float) -> float:
    """Outside radius of the inner pot along its profile (pre-rim)."""
    hi = inner_height(p)
    r_cup, zj = _cup_radius(p, hi)
    if z <= _CUP_WALL_H:
        return r_cup
    if z <= zj:
        t = (z - _CUP_WALL_H) / max(zj - _CUP_WALL_H, 1e-9)
        return r_cup + (_inner_wall_radius(p, zj) - r_cup) * t
    return _inner_wall_radius(p, z)


def _monotonic(zs: list[float]) -> list[float]:
    out = []
    for z in zs:
        if not out or z > out[-1] + 1e-6:
            out.append(z)
    return out


def _validate(p: PotParams) -> None:
    if p.pot_style == "low_poly_faceted":
        raise ParameterError(
            "self_watering cannot use a low_poly_faceted outer pot: its facets "
            "rotate with height, so no straight refill tube stays fused to the "
            "wall - pick another style"
        )
    hi = inner_height(p)
    if p.reservoir_height >= hi * 0.6:
        raise ParameterError(
            f"reservoir_height {p.reservoir_height} leaves no room for soil - "
            f"keep it under {hi * 0.6:.0f} for this pot"
        )
    r_cup, zj = _cup_radius(p, hi)
    if _inner_wall_radius(p, zj) - r_cup < 8.0:
        raise ParameterError(
            "the wick cup leaves no cone: reduce reservoir_height or widen the pot"
        )
