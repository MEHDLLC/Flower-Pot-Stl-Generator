"""Modular garden: three interconnecting kits built on ONE dovetail standard.

**Dovetail standard.**  Every connection in this module is the same joint:
a vertical male rail (trapezoid, wider at the tip) slides down into a
female boss with a matching slot.  Vertical extrusions print perfectly;
the slot floor sits 6 mm up so mated pieces rest level, and the rail gets
a 48-degree chamfered foot so its underside never overhangs.  Anything
with a rail mates with anything with a boss - cubes, trays, petals, pods.

**Seed cubes** (``modular_kit seed_cubes``) - small square seed-starting
pots, four drainage holes each, male rails on two faces and female bosses
on the opposite two.  Exported as a single cube plus fused 2x2, 3x3 and
4x4 trays whose edges carry one rail/boss per cell, so a single (or
another tray) can dock anywhere along an edge.

**Flower set** (``modular_kit flower``) - a straight-walled round centre
pot with five bosses at 72 degrees, and a petal pot whose back is CONCAVE
to match the centre's curve.  Five petals around the centre read as a
flower from above.  Print one centre and five petals.

**Rotating stack** (``modular_kit stack``) - an open central hub with the
stacking spigot on TOP (mouth below), so levels stack on a round friction
joint - rotatable to any angle by nature - and four boss slots at
90 degrees accept clip-on pod pots.  Print one hub + four pods per level.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _finish, lathe
from .params import ParameterError, PotParams
from .profile import resample
from .sections import make_section

#: seed-cube kit constants
_SEED_WALL = 2.4
_SEED_FLOOR = 3.0

#: dovetail standard (all mm)
_RAIL_ROOT = 3.5        # rail half-width at the wall
_RAIL_TIP = 5.0         # rail half-width at the tip (wider = the lock)
_RAIL_DEPTH = 3.6
_SLOT_CLEAR = 0.35      # slot grows this much per side
_BOSS_OUT = 5.2         # how far the boss stands off the wall
_BOSS_HALF_W = 8.0
_SLOT_FLOOR = 6.0       # rail rests here, keeping mated pieces level


# ---------------------------------------------------------------------------
# tiny mesh builders
# ---------------------------------------------------------------------------
def _prism_z(profile_xy: list[tuple[float, float]], z0: float, z1: float
             ) -> trimesh.Trimesh:
    """Convex prism extruded along Z."""
    n = len(profile_xy)
    verts = ([(x, y, z0) for x, y in profile_xy]
             + [(x, y, z1) for x, y in profile_xy])
    faces = []
    for i in range(1, n - 1):
        faces.append([0, i + 1, i])
        faces.append([n, n + i, n + i + 1])
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j])
        faces.append([i, n + j, n + i])
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def _prism_y(profile_xz: list[tuple[float, float]], y0: float, y1: float
             ) -> trimesh.Trimesh:
    """Convex prism extruded along Y."""
    n = len(profile_xz)
    verts = ([(x, y0, z) for x, z in profile_xz]
             + [(x, y1, z) for x, z in profile_xz])
    faces = []
    for i in range(1, n - 1):
        faces.append([0, i, i + 1])
        faces.append([n, n + i + 1, n + i])
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, n + j, j])
        faces.append([i, n + i, n + j])
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def _place(mesh: trimesh.Trimesh, angle: float, tx: float, ty: float
           ) -> trimesh.Trimesh:
    """Rotate about Z, then translate - the rail/boss placement idiom."""
    m = mesh.copy()
    m.apply_transform(trimesh.transformations.rotation_matrix(angle, [0, 0, 1]))
    m.apply_translation((tx * math.cos(angle) - ty * math.sin(angle),
                         tx * math.sin(angle) + ty * math.cos(angle), 0.0))
    return m


# ---------------------------------------------------------------------------
# the dovetail standard
# ---------------------------------------------------------------------------
def male_rail(z_top: float, embed: float = 0.6) -> trimesh.Trimesh:
    """Rail in local frame: wall face is the x=0 plane, rail points +x.

    The underside is a single 42-degree plane RISING from the wall edge at
    _SLOT_FLOOR toward the tip.  Nothing on the rail ever dips below the
    slot floor, so it cannot collide with the boss body under the slot;
    the wall edge rests exactly on the slot floor, which is what keeps
    mated pieces level.  One boolean cut - no seam can survive under it.
    """
    run = _RAIL_DEPTH + embed
    rise = run * 1.1                        # 42 degrees for any embed depth
    body = _prism_z([(-embed, -_RAIL_ROOT), (_RAIL_DEPTH, -_RAIL_TIP),
                     (_RAIL_DEPTH, _RAIL_TIP), (-embed, _RAIL_ROOT)],
                    _SLOT_FLOOR - 0.01, z_top)
    n = np.array([-rise, 0.0, run])
    n = n / np.linalg.norm(n)
    B = 60.0
    wedge = trimesh.creation.box(extents=(B, B, B))
    theta = math.asin(n[0])
    wedge.apply_transform(
        trimesh.transformations.rotation_matrix(theta, [0, 1, 0]))
    wedge.apply_translation(
        np.array([-embed, 0.0, _SLOT_FLOOR]) - n * (B / 2.0))
    return _boolean("difference", [body, wedge])


def female_boss(z_top: float, embed: float = 0.6
                ) -> tuple[trimesh.Trimesh, trimesh.Trimesh]:
    """(boss solid, slot cutter) in the same local frame, slot opening +x.

    Union the boss BEFORE subtracting the slot.  The slot floor sits at
    _SLOT_FLOOR; the cutter overshoots outward and upward so no coplanar
    seams survive.
    """
    boss = _prism_z([(-embed, -_BOSS_HALF_W), (_BOSS_OUT, -_BOSS_HALF_W),
                     (_BOSS_OUT, _BOSS_HALF_W), (-embed, _BOSS_HALF_W)],
                    0.0, z_top)
    neck = _RAIL_ROOT + _SLOT_CLEAR
    belly = _RAIL_TIP + _SLOT_CLEAR
    x_in = _BOSS_OUT - _RAIL_DEPTH - 0.4
    slot = _prism_z([(_BOSS_OUT + 0.7, -neck), (x_in, -belly),
                     (x_in, belly), (_BOSS_OUT + 0.7, neck)],
                    _SLOT_FLOOR, z_top + 2.0)
    return boss, slot


# ---------------------------------------------------------------------------
# kit 1: seed-starting cubes and trays
# ---------------------------------------------------------------------------
def build_seed_tray(p: PotParams, n: int) -> trimesh.Trimesh:
    """An n x n tray of seed cubes (n=1 is the single cube).

    Male rails run along +x and +y faces, female bosses along -x and -y,
    one per cell, so any unit docks against any other at any cell offset.
    """
    _validate(p)
    pitch = p.cube_size
    depth = p.cube_depth
    W = n * pitch + _SEED_WALL
    body = trimesh.creation.box(extents=(W, W, depth))
    body.apply_translation((0.0, 0.0, depth / 2.0))

    centers = [(-n * pitch / 2.0 + (i + 0.5) * pitch) for i in range(n)]
    z_top = depth * 0.8
    adds, cuts = [], []

    for c in centers:                       # connectors, one per edge cell
        adds.append(_place(male_rail(z_top), 0.0, W / 2.0, c))
        adds.append(_place(male_rail(z_top), math.pi / 2.0, W / 2.0, -c))
        boss, slot = female_boss(z_top)
        adds.append(_place(boss, math.pi, W / 2.0, -c))
        cuts.append(_place(slot, math.pi, W / 2.0, -c))
        boss, slot = female_boss(z_top)
        adds.append(_place(boss, -math.pi / 2.0, W / 2.0, c))
        cuts.append(_place(slot, -math.pi / 2.0, W / 2.0, c))

    for cx in centers:                      # cavities and drainage
        for cy in centers:
            cav = trimesh.creation.box(
                extents=(pitch - _SEED_WALL, pitch - _SEED_WALL,
                         depth - _SEED_FLOOR + 2.0))
            cav.apply_translation((cx, cy, _SEED_FLOOR
                                   + (depth - _SEED_FLOOR + 2.0) / 2.0))
            cuts.append(cav)
            for sx in (-1, 1):
                for sy in (-1, 1):
                    hole = trimesh.creation.cylinder(radius=2.75, height=10.0,
                                                     sections=32)
                    hole.apply_translation((cx + sx * pitch / 5.0,
                                            cy + sy * pitch / 5.0, 1.5))
                    cuts.append(hole)

    out = _boolean("union", [body] + adds)
    return _finish(_boolean("difference", [out] + cuts), center=False)


# ---------------------------------------------------------------------------
# kit 2: the flower - a round centre with five petal pots
# ---------------------------------------------------------------------------
def _petal_radius(p: PotParams) -> float:
    return p.flower_diameter * 0.29


def build_flower_center(p: PotParams) -> trimesh.Trimesh:
    """Straight-walled centre pot with five bosses at 72 degrees."""
    _validate(p)
    R = p.flower_diameter / 2.0
    H = p.height
    wt = p.wall_thickness
    section = make_section(p.with_(pot_style="classic_tapered",
                                   surface_texture="none", belly=0.0))
    body = lathe(resample([(R, 0.0), (R, H)], p.vertical_step), section, False)
    cavity = lathe(resample([(R - wt, p.base_thickness), (R - wt, H + 5.0)],
                            p.vertical_step), section, False)

    embed = 0.6 + _BOSS_HALF_W ** 2 / (2.0 * R)   # cover the wall's curvature
    z_top = H * 0.7
    adds, cuts = [], [cavity]
    for k in range(5):
        a = 2.0 * math.pi * k / 5.0
        boss, slot = female_boss(z_top, embed)
        adds.append(_place(boss, a, R, 0.0))
        cuts.append(_place(slot, a, R, 0.0))
    for k in range(5):                       # drainage ring
        a = math.pi / 5.0 + 2.0 * math.pi * k / 5.0
        hole = trimesh.creation.cylinder(radius=p.drainage_hole_radius * 0.8,
                                         height=p.base_thickness + 6.0,
                                         sections=32)
        hole.apply_translation((R * 0.45 * math.cos(a), R * 0.45 * math.sin(a),
                                p.base_thickness / 2.0))
        cuts.append(hole)

    out = _boolean("union", [body] + adds)
    return _finish(_boolean("difference", [out] + cuts), center=False)


def build_flower_petal(p: PotParams) -> trimesh.Trimesh:
    """A petal pot: half-round with a concave back hugging the centre pot.

    Print five.  Assembled, the set reads as a five-petal flower.
    """
    _validate(p)
    R = p.flower_diameter / 2.0
    H = p.height
    wt = p.wall_thickness
    rp = _petal_radius(p)
    # the concave back stands 0.6 clear of the boss faces: the boss CORNERS
    # sit slightly further from the centre than its flat face, and without
    # the clearance they dig into the petal's curve
    back = R + _BOSS_OUT + 0.6
    d = back + rp * 0.72                     # petal centre: overlaps the back

    section = make_section(p.with_(pot_style="classic_tapered",
                                   surface_texture="none", belly=0.0))

    def cyl(radius, z0, z1, cx):
        m = lathe(resample([(radius, z0), (radius, z1)], p.vertical_step),
                  section, False)
        m.apply_translation((cx, 0.0, 0.0))
        return m

    body = _boolean("difference",
                    [cyl(rp, 0.0, H, d), cyl(back, -1.0, H + 1.0, 0.0)])
    cavity = _boolean("difference",
                      [cyl(rp - wt, p.base_thickness, H + 5.0, d),
                       cyl(back + wt, p.base_thickness - 1.0, H + 6.0, 0.0)])

    embed = 0.6 + _BOSS_HALF_W ** 2 / (2.0 * back)
    # _place translates by the ROTATED offset: tx=-back with a half-turn
    # lands the rail at (+back, 0) pointing at the centre pot
    rail = _place(male_rail(H * 0.7, embed), math.pi, -back, 0.0)

    cuts = [cavity]
    for k in (-1, 0, 1):                     # three drainage holes
        hole = trimesh.creation.cylinder(radius=p.drainage_hole_radius * 0.7,
                                         height=p.base_thickness + 6.0,
                                         sections=32)
        hole.apply_translation((d + rp * 0.3 * (abs(k) - 0.4),
                                k * rp * 0.4, p.base_thickness / 2.0))
        cuts.append(hole)

    out = _boolean("union", [body, rail])
    return _finish(_boolean("difference", [out] + cuts), center=False)


# ---------------------------------------------------------------------------
# kit 3: the rotating stack
# ---------------------------------------------------------------------------
_HUB_R = 32.0
_HUB_WALL = 3.0


def _pod_height(p: PotParams) -> float:
    return p.stack_pod_diameter * 1.15


def _hub_height(p: PotParams) -> float:
    return _pod_height(p) + 20.0


def build_stack_hub(p: PotParams) -> trimesh.Trimesh:
    """The open central column of one level.

    The stacking spigot sits on TOP (the mouth is at the bottom), so the
    four boss slots can run from the build plate up - and because the
    joint is round, every level rotates freely on the one below.
    """
    _validate(p)
    R = _HUB_R
    r_sp = R - _HUB_WALL - 0.4
    h0 = _hub_height(p)
    section = make_section(p.with_(pot_style="classic_tapered",
                                   surface_texture="none", belly=0.0))
    outer = lathe(resample([(R, 0.0), (R, h0), (r_sp, h0 + (R - r_sp)),
                            (r_sp, h0 + 14.0)], p.vertical_step),
                  section, False)
    neck0 = (R - _HUB_WALL) - (r_sp - _HUB_WALL)
    cavity = lathe(resample([(R - _HUB_WALL, -1.0),
                             (R - _HUB_WALL, h0 - 6.0),
                             (r_sp - _HUB_WALL, h0 - 6.0 + neck0 * 1.2),
                             (r_sp - _HUB_WALL, h0 + 16.0)],
                            p.vertical_step), section, False)

    embed = 0.6 + _BOSS_HALF_W ** 2 / (2.0 * R)
    z_top = h0 * 0.75
    adds, cuts = [], [cavity]
    for k in range(4):
        a = k * math.pi / 2.0
        boss, slot = female_boss(z_top, embed)
        adds.append(_place(boss, a, R, 0.0))
        cuts.append(_place(slot, a, R, 0.0))

    out = _boolean("union", [outer] + adds)
    return _finish(_boolean("difference", [out] + cuts), center=False)


def build_stack_pod(p: PotParams) -> trimesh.Trimesh:
    """A clip-on pod pot for the hub.  Print four per level."""
    _validate(p)
    rp = p.stack_pod_diameter / 2.0
    h = _pod_height(p)
    wt = min(p.wall_thickness, 2.8)
    section = make_section(p.with_(pot_style="classic_tapered",
                                   surface_texture="none", belly=0.0))
    body = lathe(resample([(rp, 0.0), (rp, h)], p.vertical_step), section, False)
    cavity = lathe(resample([(rp - wt, _SEED_FLOOR), (rp - wt, h + 5.0)],
                            p.vertical_step), section, False)

    embed = 0.6 + _RAIL_TIP ** 2 / (2.0 * rp)
    rail = _place(male_rail(h * 0.85, embed), 0.0, rp, 0.0)

    cuts = [cavity]
    for k in range(4):
        a = math.pi / 4.0 + k * math.pi / 2.0
        hole = trimesh.creation.cylinder(radius=2.75, height=10.0, sections=32)
        hole.apply_translation((rp * 0.45 * math.cos(a),
                                rp * 0.45 * math.sin(a), 1.5))
        cuts.append(hole)

    out = _boolean("union", [body, rail])
    return _finish(_boolean("difference", [out] + cuts), center=False)


# ---------------------------------------------------------------------------
KITS = ("none", "seed_cubes", "flower", "stack")


def _validate(p: PotParams) -> None:
    if p.modular_kit not in KITS:
        raise ParameterError(
            f"unknown modular_kit {p.modular_kit!r}; choose from {list(KITS)}"
        )
    if not 40.0 <= p.cube_size <= 90.0:
        raise ParameterError("cube_size should be 40-90 mm")
    if p.cube_depth < 35.0:
        raise ParameterError("cube_depth under 35 mm holds no soil")
    if p.flower_diameter < 110.0:
        raise ParameterError(
            "flower_diameter under 110 mm leaves no room for petals"
        )
    if not 50.0 <= p.stack_pod_diameter <= 95.0:
        raise ParameterError("stack_pod_diameter should be 50-95 mm")
    # five petals must fit around the centre
    R = p.flower_diameter / 2.0
    rp = _petal_radius(p)
    if math.asin(min(rp / (R + _BOSS_OUT + rp * 0.72), 1.0)) > math.radians(36.0):
        raise ParameterError("the petals overlap - widen flower_diameter")
