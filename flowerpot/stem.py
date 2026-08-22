"""The "planted flower" stem: hollow, leafy, watered - and screw-in.

Enabled with ``stem``, a tapered tube rises from the vessel's floor,
through the mouth, to ``stem_length`` above the rim.  Its bore is open at
the top: drop a real cut flower in and the printed vase reads as the
flower's own stem.  **Water holes** - diamond ports, so they print
support-free - spiral up the submerged section, letting vessel water
reach the real stem inside the bore.

``stem_mount "screw"`` splits the piece: the vessel grows a threaded
socket boss on its floor and the stem prints separately with a matching
male stub.  The thread is a coarse printable profile (5 mm pitch, 1.1 mm
deep, flanks at 49 degrees from horizontal so BOTH the external and the
internal thread stay inside the overhang budget), with lead-in tapers
and 0.3 mm of clearance.  Unscrew to clean, or print a stem taller than
the vessel.

``soil_cap`` adds the potted-plant illusion: a removable disc that seats
into the vessel's taper just below the rim, its top sculpted like raked
soil (every bump faces up - trivially printable), with a centre hole the
stem passes through and two finger holes that double as watering holes.

Leaves are **lenses** - intersections of two shallow ellipsoids - the one
leaf shape that prints support-free; they spiral up at the golden angle,
tilted at most ``leaf_angle`` (hard cap 30 degrees) off the stem.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _diamond_port, _finish, lathe
from .params import PotParams
from .profile import resample, wall_slope, wall_radius
from .sections import Section, make_section

_GOLDEN = math.radians(137.508)

# printable coarse thread
_PITCH = 5.0
_THREAD_DEPTH = 1.1
_THREAD_CLEAR = 0.3         # radial + axial clearance on the female side
_CORE_R = 10.0              # male core radius
_STUB_H = 10.0              # threaded engagement
_FLANGE_R = 15.0
_FLANGE_H = 4.0
_SOCKET_WALL = 5.0
_SOCKET_H = 13.0

_STEM_R_BASE = 8.0
_STEM_R_TIP = 6.0


class _ThreadSection(Section):
    """Radius modulated by a helical trapezoid ridge: crest 1/8 pitch, root
    3/8, flanks 1/4 each - flank slope depth/(pitch/4) = 50 deg from
    horizontal, printable inside AND outside.  ``widen`` fattens the ridge
    axially (used on the female cutter for clearance)."""

    def __init__(self, params, depth: float, z0: float, z1: float,
                 widen: float = 0.0):
        super().__init__(params)
        self.depth, self.z0, self.z1, self.widen = depth, z0, z1, widen

    def _theta_count(self) -> int:
        return 96

    def _shape_radius(self, theta, z, r, decorate):
        t = z / _PITCH - theta / (2.0 * math.pi)
        f = np.mod(t, 1.0)
        d = np.minimum(f, 1.0 - f)                     # distance to crest
        crest = 0.125 + self.widen
        flank = 0.25
        prof = np.clip((crest + flank - d) / flank, 0.0, 1.0)
        # tapered thread ends: clamp the ridge inside a 41-deg cone rising
        # from the core, so the run-out never overhangs more than the cone
        lead = np.minimum(np.clip((z - self.z0) / 1.15, 0.0, self.depth),
                          np.clip((self.z1 - z) / 1.15, 0.0, self.depth))
        return r + np.minimum(self.depth * prof, lead)


def _thread_mesh(p: PotParams, r_core: float, z0: float, z1: float,
                 widen: float = 0.0) -> trimesh.Trimesh:
    sec = _ThreadSection(p.with_(surface_texture="none"), _THREAD_DEPTH,
                         z0 + 0.2, z1 - 0.2, widen)
    return lathe(resample([(r_core, z0), (r_core, z1)], _PITCH / 10.0),
                 sec, decorate=False)


def floor_keep_out(p: PotParams) -> float:
    """Radius on the floor claimed by the stem (or its socket boss):
    drainage holes inside it would be plugged from above."""
    if p.stem_mount == "screw":
        return _CORE_R + _THREAD_CLEAR + _THREAD_DEPTH + _SOCKET_WALL
    return _STEM_R_BASE


def _round(p: PotParams):
    return make_section(p.with_(pot_style="classic_tapered",
                                surface_texture="none", belly=0.0))


def _leaf(length: float, width: float, thickness: float) -> trimesh.Trimesh:
    """Lens leaf at the origin: axis +z, faces +-y, sharp edge all around."""
    R, d = 60.0, 58.0                          # shallow caps: ~15 deg slope
    a = trimesh.creation.icosphere(subdivisions=3, radius=R)
    b = a.copy()
    a.apply_translation((0, +d, 0))
    b.apply_translation((0, -d, 0))
    lens = _boolean("intersection", [a, b])
    lens_d = 2.0 * math.sqrt(R * R - d * d)
    lens_t = 2.0 * (R - d)
    lens.apply_scale((width / lens_d, thickness / lens_t, length / lens_d))
    return lens


def _leaves(p: PotParams, z_rim: float, z_top: float, r_tip: float
            ) -> list[trimesh.Trimesh]:
    out = []
    n = max(1, int(p.num_leaves))
    z_lo = z_rim + 14.0
    z_hi = z_top - p.leaf_length * 0.75
    for k in range(n):
        frac = k / max(1, n - 1) if n > 1 else 0.5
        z_att = z_lo + (z_hi - z_lo) * frac
        length = p.leaf_length * (1.0 - 0.35 * frac)
        tilt = math.radians(min(p.leaf_angle + 4.0 * math.sin(2.1 * k), 30.0))
        leaf = _leaf(length, length * 0.34, max(3.0, length * 0.075))
        leaf.apply_translation((0, 0, length * 0.42))
        leaf.apply_transform(
            trimesh.transformations.rotation_matrix(tilt, [0, 1, 0]))
        leaf.apply_translation((r_tip * 0.4, 0.0, z_att))
        leaf.apply_transform(
            trimesh.transformations.rotation_matrix(k * _GOLDEN, [0, 0, 1]))
        out.append(leaf)
    return out


def _water_holes(p: PotParams, z_lo: float, z_hi: float
                 ) -> list[trimesh.Trimesh]:
    """Diamond ports through the stem wall so vessel water reaches the bore."""
    holes = []
    n = max(2, int(round((z_hi - z_lo) / 22.0)))
    for k in range(n):
        z = z_lo + (z_hi - z_lo) * (k + 0.5) / n
        port = _diamond_port(x0=-1.0, x1=_STEM_R_BASE + 2.0, z_center=z,
                             half_w=2.0, up=3.2, down=2.6)
        port.apply_transform(trimesh.transformations.rotation_matrix(
            k * _GOLDEN, [0, 0, 1]))
        holes.append(port)
    return holes


def stem_parts(p: PotParams, floor_top_z: float
               ) -> tuple[list[trimesh.Trimesh], list[trimesh.Trimesh]]:
    """(solids, cutters) for a PRINTED (fused) stem, in vessel coordinates."""
    top = p.height + p.stem_length
    section = _round(p)
    stem = lathe(resample([(_STEM_R_BASE, floor_top_z - 2.0),
                           (_STEM_R_TIP, top)], 3.0), section, False)
    bore = lathe(resample([(p.stem_bore / 2.0, floor_top_z + 6.0),
                           (p.stem_bore / 2.0, top + 2.0)], 4.0),
                 section, False)
    solids = [stem] + _leaves(p, p.height, top, _STEM_R_TIP)
    cutters = [bore] + _water_holes(p, floor_top_z + 14.0, p.height - 10.0)
    return solids, cutters


def socket_parts(p: PotParams, floor_top_z: float
                 ) -> tuple[list[trimesh.Trimesh], list[trimesh.Trimesh]]:
    """(solids, cutters) adding the threaded socket to the vessel floor."""
    section = _round(p)
    z0, z1 = floor_top_z - 2.0, floor_top_z + _SOCKET_H
    boss = lathe(resample([(_CORE_R + _THREAD_CLEAR + _THREAD_DEPTH
                            + _SOCKET_WALL, z0),
                           (_CORE_R + _THREAD_CLEAR + _THREAD_DEPTH
                            + _SOCKET_WALL, z1)], 3.0), section, False)
    # the cutter is male-shaped, fattened by the clearance: it carves the
    # matching internal thread into the boss
    cutter = _thread_mesh(p, _CORE_R + _THREAD_CLEAR,
                          floor_top_z + 2.0, z1 + 2.0, widen=0.075)
    return [boss], [cutter]


def build_stem_piece(p: PotParams, floor_top_z: float) -> trimesh.Trimesh:
    """The separate screw-in stem, exported standing on its threaded stub."""
    # the flange is a cone rising at ~41 deg from the stub core out to
    # _FLANGE_R: printable upside up (the piece prints standing on the stub)
    # and, screwed home, it self-centres on the socket's top edge
    rise = 1.15
    z_f0 = _STUB_H - 1.0
    z_f1 = z_f0 + (_FLANGE_R - _CORE_R) * rise
    z_f2 = z_f1 + 1.5                              # grip band
    z_neck = z_f2 + (_FLANGE_R - _STEM_R_BASE)     # 45 deg taper to the shaft

    # heights in the PIECE frame: stub base at z=0; screwed home, the cone
    # meets the socket rim (bore radius _CORE_R + _THREAD_CLEAR) at piece
    # z = z_f0 + _THREAD_CLEAR*rise, which lands at vessel
    # z = floor_top_z + _SOCKET_H
    z_seat = z_f0 + _THREAD_CLEAR * rise
    z_rim = z_seat + (p.height - (floor_top_z + _SOCKET_H))
    top = z_rim + p.stem_length

    section = _round(p)
    stub = _thread_mesh(p, _CORE_R, 0.0, _STUB_H + 0.5)
    flange = lathe(resample([(_CORE_R, z_f0),
                             (_FLANGE_R, z_f1),
                             (_FLANGE_R, z_f2),
                             (_STEM_R_BASE, z_neck)], 2.0),
                   section, False)
    shaft = lathe(resample([(_STEM_R_BASE, z_f2),
                            (_STEM_R_TIP, top)], 3.0), section, False)
    bore = lathe(resample([(p.stem_bore / 2.0, _STUB_H + 2.0),
                           (p.stem_bore / 2.0, top + 2.0)], 4.0),
                 section, False)

    solids = [stub, flange, shaft] + _leaves(p, z_rim, top, _STEM_R_TIP)
    cutters = [bore] + _water_holes(p, z_neck + 6.0, z_rim - 10.0)
    piece = _boolean("union", solids)
    piece = _boolean("difference", [piece] + cutters)
    return _finish(piece, center=False)


def build_soil_cap(p: PotParams) -> trimesh.Trimesh:
    """Removable raked-soil cover, seating into the taper below the rim."""
    # find where a disc rests: the cavity radius ~8 mm below the rim
    slope = wall_slope(p, p.height - 8.0)
    sf = 1.0 / math.cos(math.pi / p.sides) if p.sides > 1 else 1.0
    fmin = math.cos(math.pi / p.sides) if p.sides > 1 else 1.0
    cavity = (wall_radius(p, p.height - 8.0)
              - p.wall_thickness * math.hypot(1.0, slope) * sf) * fmin
    R = cavity - 0.6
    base_t = 3.0

    def soil_z(r, x, y):
        # raked rings + gentle pseudo-random clumps, all facing UP
        bump = (0.55 * (1.0 + math.sin(2.0 * math.pi * r / 9.0))
                + 0.5 * (1.0 + math.sin(0.31 * x + 0.47 * y + 1.3)
                         * math.sin(0.43 * x - 0.29 * y + 0.7)))
        edge = min(1.0, (R - r) / 6.0 + 0.15)
        return base_t + bump * edge

    # rings run 1..nr - a single true centre vertex per surface avoids any
    # degenerate ring at r=0
    nr, nt = 26, 96
    verts, faces = [], []
    for i in range(1, nr + 1):
        r = R * i / nr
        for j in range(nt):
            a = 2.0 * math.pi * j / nt
            x, y = r * math.cos(a), r * math.sin(a)
            verts.append((x, y, soil_z(r, x, y)))
    center_top = len(verts)
    verts.append((0.0, 0.0, soil_z(0.0, 0.0, 0.0)))
    for i in range(1, nr + 1):                    # bottom ring stack (flat)
        r = R * i / nr
        for j in range(nt):
            a = 2.0 * math.pi * j / nt
            verts.append((r * math.cos(a), r * math.sin(a), 0.0))
    center_bot = len(verts)
    verts.append((0.0, 0.0, 0.0))

    def top_i(i, j):
        return (i - 1) * nt + (j % nt)

    def bot_i(i, j):
        return center_top + 1 + (i - 1) * nt + (j % nt)

    for j in range(nt):                            # centre fans to ring 1
        faces.append([center_top, top_i(1, j), top_i(1, j + 1)])
        faces.append([center_bot, bot_i(1, j + 1), bot_i(1, j)])
    for i in range(1, nr):
        for j in range(nt):
            a, b = top_i(i, j), top_i(i, j + 1)
            c, d = top_i(i + 1, j + 1), top_i(i + 1, j)
            faces.append([a, c, b])
            faces.append([a, d, c])
            a, b = bot_i(i, j), bot_i(i, j + 1)
            c, d = bot_i(i + 1, j + 1), bot_i(i + 1, j)
            faces.append([a, b, c])
            faces.append([a, c, d])
    for j in range(nt):                            # side wall, facing +r
        a, b = top_i(nr, j), top_i(nr, j + 1)
        c, d = bot_i(nr, j + 1), bot_i(nr, j)
        faces.append([a, d, c])
        faces.append([a, c, b])
    cap = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    if cap.volume < 0:
        cap.invert()

    hole_r = (_STEM_R_BASE + 1.2) if p.stem else 8.0
    cutters = [trimesh.creation.cylinder(radius=hole_r, height=20.0,
                                         sections=64)]
    for sign in (-1, 1):                           # finger / watering holes
        c = trimesh.creation.cylinder(radius=5.0, height=20.0, sections=48)
        c.apply_translation((sign * R * 0.62, 0.0, 0.0))
        cutters.append(c)
    return _finish(_boolean("difference", [cap] + cutters), center=False)
