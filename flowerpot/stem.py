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
the vessel.  A screw-in stem taller than the printer is split again into
sections joined by threaded *nodes* - bamboo-like swellings, because the
shaft is barely thicker than its own bore and a thread needs somewhere to
live.  Nodes only ever land above the rim, where the bore is dry.

``soil_cap`` adds the potted-plant illusion: a removable disc that seats
into the vessel's taper just below the rim, its top sculpted like raked
soil (every bump faces up - trivially printable), with a centre hole the
stem passes through and two finger holes that double as watering holes.

Leaves are **lenses** - intersections of two shallow ellipsoids - the one
leaf shape that prints support-free; they spiral up at the golden angle,
tilted at most ``leaf_angle`` (hard cap 30 degrees) off the stem.

Above the rim the stem is a *sheared* ring stack rather than a lathe:
``stem_curve`` sways the centreline into a gentle lean (dead straight
below the rim, where the socket, the water holes and the soil cap live),
and ``num_branches`` side stems fork off it - leaving at ~35 degrees off
vertical, easing upright, each ending in an open bore that connects to
the main water column so every branch holds its own flower.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _diamond_port, _finish, _prism, lathe
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
_BRANCH_TIP_R = 4.5
_BRANCH_BORE_R = 2.8

# mid-stem joint: a swollen node, like the node of a bamboo cane, with room
# in its wall for a thread.  The shaft itself is far too slim to hide one -
# it is barely thicker than the bore - so the joint has to stand proud.
# the joint reuses the vessel thread's proven profile: the flank angle is
# depth/(pitch/4), and at 4.0/1.0 that is exactly 45 deg - dead on the limit.
# Only the core radius shrinks, which the flank angle does not depend on.
_NODE_PITCH = _PITCH
_NODE_DEPTH = _THREAD_DEPTH
_NODE_CLEAR = 0.3
_NODE_ENGAGE = 9.0          # thread engagement, and how far the stub hangs
_NODE_WALL = 2.2
_NODE_FLARE = 6.0           # height the bulge takes to swell out of the shaft

# insert-leaf joint: a vertical slot with a gable roof (printable in the
# standing stem) takes a flat rectangular tab on the leaf (printable lying
# down).  One slot shape fits every leaf; flip the leaf to make it droop.
_SLOT_HALF_T = 1.45          # slot half-thickness (tangential)
_SLOT_HALF_H = 4.0           # slot half-height, main stem
_SLOT_HALF_H_BR = 2.6        # slot half-height, branches
_SLOT_PEAK = 2.2             # gable above the half-height: 56 deg roof
_TAB_HALF_T = 1.3            # tab half-thickness: 0.15 mm play per side
_TAB_DEPTH = 4.5             # engagement, main stem (through-wall + 2)
_TAB_DEPTH_BR = 3.5


class _ThreadSection(Section):
    """Radius modulated by a helical trapezoid ridge: crest 1/8 pitch, root
    3/8, flanks 1/4 each - flank slope depth/(pitch/4) = 50 deg from
    horizontal, printable inside AND outside.  ``widen`` fattens the ridge
    axially (used on the female cutter for clearance)."""

    def __init__(self, params, depth: float, z0: float, z1: float,
                 widen: float = 0.0, pitch: float = _PITCH):
        super().__init__(params)
        self.depth, self.z0, self.z1, self.widen = depth, z0, z1, widen
        self.pitch = pitch

    def _theta_count(self) -> int:
        return 96

    def _shape_radius(self, theta, z, r, decorate):
        t = z / self.pitch - theta / (2.0 * math.pi)
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
                 widen: float = 0.0, depth: float = _THREAD_DEPTH,
                 pitch: float = _PITCH) -> trimesh.Trimesh:
    sec = _ThreadSection(p.with_(surface_texture="none"), depth,
                         z0 + 0.2, z1 - 0.2, widen, pitch)
    return lathe(resample([(r_core, z0), (r_core, z1)], pitch / 10.0),
                 sec, decorate=False)


# ---------------------------------------------------------------------------
# splitting a tall stem into printable sections
# ---------------------------------------------------------------------------
def node_core_radius(p: PotParams, r_shaft: float = 0.0) -> float:
    """Male core radius of a mid-stem joint.

    Two things have to fit through it.  The bore runs straight past - the
    flower stem and its water have to pass - so the core clears it with a
    wall left over.  And the socket's root has to be wider than the shaft
    that drops into it, or the shaft lands on the node's mouth instead of
    the threads taking the load.
    """
    return max(6.0, p.stem_bore / 2.0 + 1.6, r_shaft + 0.15)


def node_radius(p: PotParams, r_shaft: float = 0.0) -> float:
    """Outside radius of the node bulge that houses the female thread."""
    return (node_core_radius(p, r_shaft)
            + _NODE_CLEAR + _NODE_DEPTH + _NODE_WALL)


def _bed_height(p: PotParams) -> float | None:
    if p.printer == "none":
        return None
    from .printers import PRINTERS
    return float(PRINTERS[p.printer]["height"])


def _clear_of(z: float, spans, margin: float = 3.0) -> bool:
    return all(not (lo - margin < z < hi + margin) for lo, hi in spans)


def _section_height(z_lo: float, z_hi: float, first: bool, reaches) -> float:
    """How tall the section actually prints.

    Not simply ``z_hi - z_lo``: section 0 reaches down to the vessel stub at
    z = 0, a later one hangs its own stub below z_lo, and in either case a
    leaf or branch attached inside the section can stand well above its top.
    """
    bottom = 0.0 if first else z_lo - _NODE_ENGAGE
    top = max([z_hi] + [reach for z_att, reach in reaches
                        if z_lo <= z_att < z_hi])
    return top - bottom


def stem_splits(p: PotParams, lay: "_Layout") -> list[float]:
    """Heights (piece frame) at which to put a threaded node.

    Three constraints shape the answer.  No section may print taller than
    the bed.  No node may sit below the rim - down there the bore is full
    of water, and a threaded joint is exactly where it would weep.  And no
    node may land in a leaf or a branch, because a feature split across two
    pieces would leave a fragment floating beside the shaft.

    Each node is placed as high as those allow, so the sections come out as
    few and as full as possible.
    """
    if p.stem_mount != "screw" or p.stem_split == "never":
        return []
    bed = _bed_height(p)
    limit = (bed - 5.0) if bed else None        # gantry / fan clearance
    floor = max(lay.z_f2 + 25.0, lay.z_rim + 8.0)      # first dry height
    ceiling = lay.top - 25.0
    if ceiling <= floor:
        return []
    spans = _feature_spans(p, lay)
    reaches = _feature_reaches(p, lay)

    def fits(z_lo, z_hi, first):
        return (limit is None
                or _section_height(z_lo, z_hi, first, reaches) <= limit)

    nodes: list[float] = []
    if p.stem_split == "always" and fits(lay.z_f2, lay.top, True):
        for step in range(0, 401):              # one node, near the middle
            z = 0.5 * (floor + ceiling) - step * 0.25
            if z < floor:
                break
            if _clear_of(z, spans):
                return [z]
        return []

    while True:
        z_lo = nodes[-1] if nodes else lay.z_f2
        first = not nodes
        if fits(z_lo, lay.top, first):
            break
        best = None
        z = ceiling
        while z >= max(floor, z_lo + 25.0):     # highest cut that works
            if _clear_of(z, spans) and fits(z_lo, z, first):
                best = z
                break
            z -= 0.25
        if best is None:
            break        # cannot split further; the bed warning will say so
        nodes.append(best)
    return nodes


def _tube(path, radii, nt: int = 48) -> trimesh.Trimesh:
    """Watertight tube: horizontal circular rings stacked along ``path``
    (strictly rising z), capped with centre fans at both ends.  A ring
    stack with drifting centres is a *sheared* cylinder, so the underside
    lean is simply the centreline's lateral slope (plus any taper) - keep
    that under 45 degrees and the tube prints support-free."""
    verts, faces = [], []
    n = len(path)
    for (x, y, z), r in zip(path, radii):
        for j in range(nt):
            a = 2.0 * math.pi * j / nt
            verts.append((x + r * math.cos(a), y + r * math.sin(a), z))
    cb = len(verts)
    verts.append(tuple(path[0]))
    ct = len(verts)
    verts.append(tuple(path[-1]))

    def ring(i, j):
        return i * nt + (j % nt)

    for j in range(nt):
        faces.append([cb, ring(0, j + 1), ring(0, j)])        # bottom, -z
        faces.append([ct, ring(n - 1, j), ring(n - 1, j + 1)])  # top, +z
    for i in range(n - 1):
        for j in range(nt):
            a, b = ring(i, j), ring(i, j + 1)
            c, d = ring(i + 1, j + 1), ring(i + 1, j)
            faces.append([a, b, c])
            faces.append([a, c, d])
    return trimesh.Trimesh(vertices=verts, faces=faces, process=True)


def _centerline(p: PotParams, z_rim: float, top: float):
    """(cx, cy) sway of the stem axis at height z.  Dead straight below
    the rim - the socket, the water holes and the soil cap's hole all live
    down there - then a gentle cosine lean with a sine cross-sway above.
    Validation caps the slope at ~15 degrees (stem_length >= 6 x curve)."""
    amp = p.stem_curve
    length = max(top - z_rim, 1.0)

    def at(z: float) -> tuple[float, float]:
        if amp <= 0.0 or z <= z_rim:
            return 0.0, 0.0
        u = min(1.0, (z - z_rim) / length)
        return (amp * 0.5 * (1.0 - math.cos(math.pi * u)),
                0.35 * amp * math.sin(math.pi * u))
    return at


def _shaft_tube(p: PotParams, z0: float, z1: float, r_fn, cl,
                step: float = 2.5) -> trimesh.Trimesh:
    zs = list(np.arange(z0, z1, step)) + [z1]
    path = [(*cl(z), z) for z in zs]
    return _tube(path, [r_fn(z) for z in zs], nt=max(48, p.segments // 2))


def _taper(r0: float, z0: float, r1: float, z1: float):
    def r_fn(z: float) -> float:
        u = min(1.0, max(0.0, (z - z0) / max(z1 - z0, 1e-9)))
        return r0 + (r1 - r0) * u
    return r_fn


def planned_branches(p: PotParams, z_rim: float, top: float
                     ) -> list[tuple[float, float, float]]:
    """(z_attach, climb, azimuth) per branch that actually fits.  Shared
    with the tests so genus expectations track the skip logic."""
    out = []
    n = int(p.num_branches)
    span = top - z_rim
    for k in range(n):
        frac = 0.28 + (0.44 * k / (n - 1) if n > 1 else 0.12)
        z_att = z_rim + span * frac
        climb = min(p.branch_length, top - 8.0 - z_att)
        if climb >= 22.0:
            out.append((z_att, climb, k * _GOLDEN + 0.8))
    return out


def branch_leaf_length(p: PotParams, top: float, z_att: float, climb: float
                       ) -> float | None:
    """Length of the leaf a branch carries at mid-climb, clipped so it
    never rises past the main stem's tip; None when there is no room."""
    steps = max(8, int(climb / 2.5))
    pz = z_att + climb * (int(steps * 0.5) / steps)
    length = min(p.leaf_length * 0.55, (top - 1.0 - pz) / 0.95)
    return length if length >= 12.0 else None


def _branches(p: PotParams, z_rim: float, top: float, r_fn, cl,
              z_lo: float = -1e9, z_hi: float = 1e9
              ) -> tuple[list[trimesh.Trimesh], list[trimesh.Trimesh]]:
    """Side stems curving off the main one: they leave at ~35 degrees off
    vertical (printable), ease upright, and end in an open bore of their
    own that connects to the main water column - one flower per branch."""
    solids, cutters = [], []
    for z_att, climb, azim in planned_branches(p, z_rim, top):
        if not z_lo <= z_att < z_hi:      # belongs to another section
            continue
        reach = 0.40 * climb          # base slope 0.63 -> 32 deg + sway
        rb0 = min(5.4, 0.8 * r_fn(z_att))
        steps = max(8, int(climb / 2.5))
        path, radii = [], []
        for i in range(steps + 1):
            t = i / steps
            rad = reach * math.sin(t * math.pi / 2.0)
            z = z_att + climb * t
            cx, cy = cl(z)
            path.append((cx + rad * math.cos(azim),
                         cy + rad * math.sin(azim), z))
            radii.append(rb0 + (_BRANCH_TIP_R - rb0) * t)
        solids.append(_tube(path, radii))
        tip = path[-1]
        bore_path = path + [(tip[0], tip[1], tip[2] + 3.0)]
        cutters.append(_tube(bore_path, [_BRANCH_BORE_R] * len(bore_path)))

        # one small leaf at mid-branch, swung away from the branch's own
        # direction so it never hangs over the open tip (the bore must
        # exit into clear air, not into a leaf's underside), and clipped
        # so no branch leaf rises past the main stem's tip
        length = branch_leaf_length(p, top, z_att, climb)
        if length is None:
            continue
        i_leaf = int(steps * 0.5)
        px, py, pz = path[i_leaf]
        if p.leaf_mount == "insert":
            r_here = radii[i_leaf]
            cutters.append(_place_slot(_slot(r_here + 3.0, _SLOT_HALF_H_BR),
                                       azim + 1.1, px, py, pz))
            continue
        leaf = _leaf(length, length * 0.34, max(3.0, length * 0.075))
        leaf.apply_translation((0, 0, length * 0.42))
        leaf.apply_transform(trimesh.transformations.rotation_matrix(
            math.radians(min(p.leaf_angle, 28.0)), [0, 1, 0]))
        leaf.apply_transform(trimesh.transformations.rotation_matrix(
            azim + 1.1, [0, 0, 1]))
        leaf.apply_translation((px, py, pz))
        solids.append(leaf)
    return solids, cutters


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


def _leaf_sites(p: PotParams, z_rim: float, z_top: float
                ) -> list[tuple[float, float, float, float]]:
    """(z_attach, length, azimuth, tilt_deg) per main-stem leaf - shared by
    the fused leaves, the insert slots and the leaf plate.

    A leaf whose sector a branch climbs through is swung aside: fused it
    would merely merge into the branch, but an insert leaf has to actually
    fit.  Swinging it has to clear the other *leaves* too - two blades on
    the same bearing weld into each other, which closes a loop through the
    shaft and quietly adds a handle to the model.
    """
    branches = planned_branches(p, z_rim, z_top)

    def _gap(a: float, b: float) -> float:
        return abs((a - b + math.pi) % (2.0 * math.pi) - math.pi)

    def clashes(azim: float, z_att: float, length: float, placed) -> bool:
        for zb, climb, ab in branches:
            if _gap(azim, ab) < 0.95 and z_att < zb + climb \
                    and z_att + 0.8 * length > zb + 4.0:
                return True
        for z0, a0, l0 in placed:
            if _gap(azim, a0) < 0.55 \
                    and abs(z_att - z0) < 0.8 * max(length, l0):
                return True
        return False

    sites = []
    n = max(1, int(p.num_leaves))
    # the first leaf starts a little clear of the rim: that gap is where a
    # mid-stem node lands on a tall stem, and it is the natural place for
    # one anyway - right where the stem emerges from the pot
    z_lo = z_rim + 20.0
    z_hi = max(z_lo, z_top - p.leaf_length * 0.75)
    cap = 60.0 if p.leaf_mount == "insert" else 30.0
    placed: list[tuple[float, float, float]] = []
    for k in range(n):
        frac = k / max(1, n - 1) if n > 1 else 0.5
        z_att = z_lo + (z_hi - z_lo) * frac
        length = p.leaf_length * (1.0 - 0.35 * frac)
        azim = k * _GOLDEN
        for _ in range(4):
            if not clashes(azim, z_att, length, placed):
                break
            azim += 1.15          # not a multiple of the golden angle
        placed.append((z_att, azim, length))
        sites.append((z_att, length, azim,
                      min(p.leaf_angle + 4.0 * math.sin(2.1 * k), cap)))
    return sites


def _leaves(p: PotParams, z_rim: float, z_top: float, r_tip: float, cl,
            z_lo: float = -1e9, z_hi: float = 1e9) -> list[trimesh.Trimesh]:
    out = []
    for z_att, length, azim, tilt in _leaf_sites(p, z_rim, z_top):
        if not z_lo <= z_att < z_hi:      # belongs to another section
            continue
        leaf = _leaf(length, length * 0.34, max(3.0, length * 0.075))
        leaf.apply_translation((0, 0, length * 0.42))
        leaf.apply_transform(trimesh.transformations.rotation_matrix(
            math.radians(tilt), [0, 1, 0]))
        leaf.apply_translation((r_tip * 0.4, 0.0, z_att))
        leaf.apply_transform(
            trimesh.transformations.rotation_matrix(azim, [0, 0, 1]))
        cx, cy = cl(z_att)                     # ride the stem's sway
        leaf.apply_translation((cx, cy, 0.0))
        out.append(leaf)
    return out


def _slot(x_outer: float, half_h: float) -> trimesh.Trimesh:
    """Slot cutter at the origin: prism along +x (the insertion axis),
    vertical sides, gable roof so the standing stem needs no supports."""
    prof = [(-_SLOT_HALF_T, -half_h), (_SLOT_HALF_T, -half_h),
            (_SLOT_HALF_T, half_h), (0.0, half_h + _SLOT_PEAK),
            (-_SLOT_HALF_T, half_h)]
    return _prism(prof, 0.5, x_outer)


def _place_slot(slot: trimesh.Trimesh, azim: float,
                x: float, y: float, z: float) -> trimesh.Trimesh:
    slot.apply_transform(
        trimesh.transformations.rotation_matrix(azim, [0, 0, 1]))
    slot.apply_translation((x, y, z))
    return slot


def _leaf_slots(p: PotParams, z_rim: float, z_top: float, r_fn, cl,
                z_lo: float = -1e9, z_hi: float = 1e9
                ) -> list[trimesh.Trimesh]:
    out = []
    for z_att, _length, azim, _tilt in _leaf_sites(p, z_rim, z_top):
        if not z_lo <= z_att < z_hi:
            continue
        cx, cy = cl(z_att)
        out.append(_place_slot(_slot(r_fn(z_att) + 3.0, _SLOT_HALF_H),
                               azim, cx, cy, z_att))
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
    cl = _centerline(p, p.height, top)
    r_fn = _taper(_STEM_R_BASE, floor_top_z - 2.0, _STEM_R_TIP, top)
    stem = _shaft_tube(p, floor_top_z - 2.0, top, r_fn, cl)
    bore = _shaft_tube(p, floor_top_z + 6.0, top + 2.0,
                       lambda z: p.stem_bore / 2.0, cl)
    b_solids, b_cutters = _branches(p, p.height, top, r_fn, cl)
    solids = [stem] + b_solids
    cutters = ([bore] + b_cutters
               + _water_holes(p, floor_top_z + 14.0, p.height - 10.0))
    if p.leaf_mount == "insert":
        cutters += _leaf_slots(p, p.height, top, r_fn, cl)
    else:
        solids += _leaves(p, p.height, top, _STEM_R_TIP, cl)
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


class _Layout:
    """Heights of the screw-in stem in the PIECE frame (stub base at z=0)."""

    def __init__(self, p: PotParams, floor_top_z: float):
        # the flange is a cone rising at ~41 deg from the stub core out to
        # _FLANGE_R: printable upside up (the piece prints standing on the
        # stub) and, screwed home, it self-centres on the socket's top edge
        rise = 1.15
        self.z_f0 = _STUB_H - 1.0
        self.z_f1 = self.z_f0 + (_FLANGE_R - _CORE_R) * rise
        self.z_f2 = self.z_f1 + 1.5                     # grip band
        self.z_neck = self.z_f2 + (_FLANGE_R - _STEM_R_BASE)   # 45 deg taper
        # screwed home, the cone meets the socket rim (bore radius
        # _CORE_R + _THREAD_CLEAR) at piece z = z_f0 + _THREAD_CLEAR * rise,
        # which lands at vessel z = floor_top_z + _SOCKET_H
        self.z_seat = self.z_f0 + _THREAD_CLEAR * rise
        self.z_rim = self.z_seat + (p.height - (floor_top_z + _SOCKET_H))
        self.top = self.z_rim + p.stem_length
        self.r_fn = _taper(_STEM_R_BASE, self.z_f2, _STEM_R_TIP, self.top)
        self.cl = _centerline(p, self.z_rim, self.top)


def _feature_spans(p: PotParams, lay: "_Layout") -> list[tuple[float, float]]:
    """Height ranges a node must not land in, one per leaf and branch."""
    spans = []
    for z_att, length, _azim, _tilt in _leaf_sites(p, lay.z_rim, lay.top):
        # an insert leaf is a separate part - only its slot is in the way
        spans.append((z_att - 5.0, z_att + 5.0) if p.leaf_mount == "insert"
                     else (z_att - 2.0, z_att + 0.9 * length))
    for z_att, climb, _azim in planned_branches(p, lay.z_rim, lay.top):
        spans.append((z_att - 2.0, z_att + climb + 4.0))
    return spans


def _feature_reaches(p: PotParams, lay: "_Layout"
                     ) -> list[tuple[float, float]]:
    """(z_attach, how high it stands) per leaf and branch."""
    out = []
    for z_att, length, _azim, _tilt in _leaf_sites(p, lay.z_rim, lay.top):
        out.append((z_att, z_att + (6.0 if p.leaf_mount == "insert"
                                    else 0.95 * length)))
    for z_att, climb, _azim in planned_branches(p, lay.z_rim, lay.top):
        reach = z_att + climb
        leaf = branch_leaf_length(p, lay.top, z_att, climb)
        if leaf is not None and p.leaf_mount != "insert":
            reach = max(reach, z_att + 0.5 * climb + 0.95 * leaf)
        out.append((z_att, reach))
    return out


def stem_section_bounds(p: PotParams, floor_top_z: float
                        ) -> list[tuple[float, float]]:
    """(z_lo, z_hi) of each printed stem section, in the piece frame."""
    lay = _Layout(p, floor_top_z)
    edges = [lay.z_f2] + stem_splits(p, lay) + [lay.top]
    return list(zip(edges, edges[1:]))


def stem_piece_count(p: PotParams, floor_top_z: float) -> int:
    return len(stem_section_bounds(p, floor_top_z))


def build_stem_piece(p: PotParams, floor_top_z: float,
                     index: int = 0) -> trimesh.Trimesh:
    """One printed section of the screw-in stem, standing on its stub.

    Section 0 carries the threaded stub and flange that screw into the
    vessel; every later section starts with a smaller male stub that screws
    into the node on top of the section below it.
    """
    lay = _Layout(p, floor_top_z)
    bounds = stem_section_bounds(p, floor_top_z)
    z_lo, z_hi = bounds[index]
    first, last = index == 0, index == len(bounds) - 1
    r_fn, cl = lay.r_fn, lay.cl
    section = _round(p)

    solids: list[trimesh.Trimesh] = []
    cutters: list[trimesh.Trimesh] = []

    if first:
        solids.append(_thread_mesh(p, _CORE_R, 0.0, _STUB_H + 0.5))
        solids.append(lathe(resample([(_CORE_R, lay.z_f0),
                                      (_FLANGE_R, lay.z_f1),
                                      (_FLANGE_R, lay.z_f2),
                                      (_STEM_R_BASE, lay.z_neck)], 2.0),
                            section, False))
        bore_lo = _STUB_H + 2.0
        cutters += _water_holes(p, lay.z_neck + 6.0, lay.z_rim - 10.0)
    else:
        # male stub hanging below the shaft, screwing into the node beneath
        core = node_core_radius(p, r_fn(z_lo))
        stub = _thread_mesh(p, core, z_lo - _NODE_ENGAGE, z_lo + 0.5,
                            depth=_NODE_DEPTH, pitch=_NODE_PITCH)
        stub.apply_translation((*cl(z_lo), 0.0))     # ride the stem's sway
        solids.append(stub)
        # ... and a cone easing the stub out to the shaft, so the shaft's
        # underside is not left hanging over the thread roots.  It starts
        # strictly *inside* the stub core: flush with it, the two surfaces
        # only graze and leave slivers of downward-facing rim behind.
        base = core - 0.8
        lead = max(2.5, (r_fn(z_lo) - base) * 1.3)
        solids.append(_shaft_tube(
            p, z_lo - lead, z_lo,
            lambda z, zl=z_lo, ld=lead, b=base: b + (r_fn(zl) - b)
            * min(1.0, max(0.0, (z - (zl - ld)) / ld)), cl, step=0.75))
        bore_lo = z_lo - _NODE_ENGAGE - 2.0

    solids.append(_shaft_tube(p, z_lo, z_hi, r_fn, cl))

    if not last:
        # the node: a bamboo-like swelling with the female thread inside it
        node_r = node_radius(p, r_fn(z_hi))
        z_flare = z_hi - _NODE_ENGAGE - _NODE_FLARE
        solids.append(_shaft_tube(
            p, z_flare, z_hi,
            lambda z, zf=z_flare, zh=z_hi, nr=node_r: max(
                r_fn(z), r_fn(zf) + (nr - r_fn(zf))
                * min(1.0, (z - zf) / _NODE_FLARE)), cl, step=1.0))
        socket = _thread_mesh(
            p, node_core_radius(p, r_fn(z_hi)) + _NODE_CLEAR,
            z_hi - _NODE_ENGAGE,
            z_hi + 2.0, widen=0.075, depth=_NODE_DEPTH, pitch=_NODE_PITCH)
        # the same offset the mating stub uses, so the two still line up
        socket.apply_translation((*cl(z_hi), 0.0))
        cutters.append(socket)

    cutters.append(_shaft_tube(p, bore_lo, z_hi + 2.0,
                               lambda z: p.stem_bore / 2.0, cl))

    b_solids, b_cutters = _branches(p, lay.z_rim, lay.top, r_fn, cl,
                                    z_lo, z_hi)
    solids += b_solids
    cutters += b_cutters
    if p.leaf_mount == "insert":
        cutters += _leaf_slots(p, lay.z_rim, lay.top, r_fn, cl, z_lo, z_hi)
    else:
        solids += _leaves(p, lay.z_rim, lay.top, _STEM_R_TIP, cl, z_lo, z_hi)

    piece = _boolean("union", solids)
    piece = _boolean("difference", [piece] + cutters)
    piece = _finish(piece, center=False)
    if not first:            # print it standing on its stub
        piece.apply_translation((0.0, 0.0, -piece.bounds[0][2]))
    return piece


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


def leaf_pose(r_att: float, azim: float, cx: float, cy: float,
              z_att: float) -> "np.ndarray":
    """Print frame -> stem frame for an inserted leaf: stand it upright,
    push the tab to the stem surface, swing to the slot's azimuth."""
    return (trimesh.transformations.translation_matrix((cx, cy, z_att))
            @ trimesh.transformations.rotation_matrix(azim, [0, 0, 1])
            @ trimesh.transformations.translation_matrix(
                (r_att, _TAB_HALF_T, 0.0))
            @ trimesh.transformations.rotation_matrix(
                math.pi / 2.0, [1, 0, 0]))


def _leaf_insert(p: PotParams, length: float, tilt_deg: float,
                 main: bool, relief: trimesh.Trimesh) -> trimesh.Trimesh:
    """One flat leaf: a rectangular tab (slides into the stem's slot)
    with the blade bent off it at the leaf angle - the tilt is baked into
    the part, so the slot never changes.  Prints lying down; flip it in
    the slot to make the leaf droop instead of rise.  ``relief`` is the
    stem (or branch), widened and mapped into the print frame: it gets
    scooped out of the blade so the leaf hugs the stem it plugs into."""
    hh = (_SLOT_HALF_H if main else _SLOT_HALF_H_BR) - 0.3
    depth = _TAB_DEPTH if main else _TAB_DEPTH_BR
    tab = _prism([(-hh, 0.0), (hh, 0.0),
                  (hh, 2.0 * _TAB_HALF_T), (-hh, 2.0 * _TAB_HALF_T)],
                 -depth, 2.5)

    phi = math.radians(min(tilt_deg, 60.0))
    # double-thick lens, then shave the bottom half flat: a D-section
    # blade whose ENTIRE underside is bed contact - no overhang anywhere
    blade = _leaf(length, length * 0.34, 2.0 * max(3.0, length * 0.075))
    # lay it flat: lens axis +z -> +y, faces +-y -> +-z
    blade.apply_transform(trimesh.transformations.rotation_matrix(
        -math.pi / 2.0, [1, 0, 0]))
    # bend the blade off the tab axis by the leaf angle (in the bed plane)
    blade.apply_transform(trimesh.transformations.rotation_matrix(
        -phi, [0, 0, 1]))
    reach = 0.5 * length - 1.5
    blade.apply_translation((reach * math.sin(phi),
                             reach * math.cos(phi), 0.0))
    blade = _boolean("difference", [blade, relief])

    piece = _boolean("union", [tab, blade])
    shave = trimesh.creation.box(extents=(600.0, 600.0, 100.0))
    shave.apply_translation((0.0, 0.0, -50.0))     # flat underside at z = 0
    return _boolean("difference", [piece, shave])


def _main_leaf_piece(p: PotParams, z_att: float, length: float, azim: float,
                     tilt: float, r_fn, cl) -> trimesh.Trimesh:
    """A main-stem insert leaf whose saddle is the ACTUAL swept stem
    (taper, curve and all) widened 1 mm, mapped into the print frame."""
    relief = _shaft_tube(p, z_att - 30.0, z_att + 0.9 * length + 10.0,
                         lambda z: r_fn(z) + 1.0, cl)
    cx, cy = cl(z_att)
    relief.apply_transform(np.linalg.inv(
        leaf_pose(r_fn(z_att), azim, cx, cy, z_att)))
    return _leaf_insert(p, length, tilt, True, relief)


def build_leaf_inserts(p: PotParams) -> trimesh.Trimesh:
    """The whole foliage as one flat plate of push-in leaves - print it in
    a second color/filament, then slide each tab into a stem slot.  Main
    leaves first (big tabs), branch leaves after (small tabs)."""
    top = p.height + p.stem_length
    r_fn = _taper(_STEM_R_BASE, 0.0, _STEM_R_TIP, top)
    cl = _centerline(p, p.height, top)
    pieces = [_main_leaf_piece(p, z_att, length, azim, tilt, r_fn, cl)
              for z_att, length, azim, tilt in _leaf_sites(p, p.height, top)]
    for z_att, climb, _azim in planned_branches(p, p.height, top):
        length = branch_leaf_length(p, top, z_att, climb)
        if length is None:
            continue
        # branches are slim and lean away from their leaf: a straight
        # widened cylinder is relief enough
        relief = trimesh.creation.cylinder(radius=4.9 + 1.5, height=400.0,
                                           sections=96)
        relief.apply_transform(trimesh.transformations.rotation_matrix(
            math.pi / 2.0, [1, 0, 0]))
        relief.apply_translation((-4.9, 0.0, _TAB_HALF_T))
        pieces.append(_leaf_insert(p, length, min(p.leaf_angle, 28.0),
                                   False, relief))
    x = 0.0
    for piece in pieces:
        piece.apply_translation((x - piece.bounds[0][0], 0.0, 0.0))
        x = piece.bounds[1][0] + 6.0
    return _finish(trimesh.util.concatenate(pieces), center=True)
