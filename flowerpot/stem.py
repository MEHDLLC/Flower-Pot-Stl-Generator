"""The "planted flower" stem: a hollow sculptural stem with leaves.

Enabled with ``stem``, a tapered tube rises from the vessel's floor,
through the mouth, to ``stem_length`` above the rim.  Its bore is open at
the top and closed near the floor: drop a real cut flower in and the
printed vase reads as the flower's own stem - and in a watertight vessel
the bore holds water for it.

Leaves spiral up the exposed stem at the golden angle.  Each leaf is a
**lens** - the intersection of two shallow ellipsoids - which is the one
leaf shape that prints support-free: its faces are near-parallel to the
leaf plane, so with the leaf tilted no more than ``leaf_angle`` (hard cap
30 degrees) from the stem, every face stays far inside the overhang
budget.  A sharp botanical edge comes free with the construction.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, lathe
from .params import PotParams
from .profile import resample
from .sections import make_section

_GOLDEN = math.radians(137.508)


def _leaf(length: float, width: float, thickness: float) -> trimesh.Trimesh:
    """Lens leaf at the origin: axis +z, faces +-y, sharp edge all around."""
    R = 60.0
    d = 58.0                                  # shallow caps: ~15 deg max slope
    a = trimesh.creation.icosphere(subdivisions=3, radius=R)
    b = a.copy()
    a.apply_translation((0, +d, 0))
    b.apply_translation((0, -d, 0))
    lens = _boolean("intersection", [a, b])
    lens_d = 2.0 * math.sqrt(R * R - d * d)   # sharp-edge diameter
    lens_t = 2.0 * (R - d)
    lens.apply_scale((width / lens_d, thickness / lens_t, length / lens_d))
    return lens


def stem_parts(p: PotParams, floor_top_z: float
               ) -> tuple[list[trimesh.Trimesh], list[trimesh.Trimesh]]:
    """(solids to union, cutters to subtract) for the stem and leaves."""
    top = p.height + p.stem_length
    r_base, r_tip = 8.0, 6.0
    section = make_section(p.with_(pot_style="classic_tapered",
                                   surface_texture="none", belly=0.0))
    stem = lathe(resample([(r_base, floor_top_z - 2.0), (r_tip, top)], 3.0),
                 section, False)
    bore = lathe(resample([(p.stem_bore / 2.0, floor_top_z + 6.0),
                           (p.stem_bore / 2.0, top + 2.0)], 4.0),
                 section, False)

    solids = [stem]
    n = max(1, int(p.num_leaves))
    z_lo = p.height + 14.0                    # leaves live on the exposed stem
    z_hi = top - p.leaf_length * 0.75
    for k in range(n):
        frac = k / max(1, n - 1) if n > 1 else 0.5
        z_att = z_lo + (z_hi - z_lo) * frac
        length = p.leaf_length * (1.0 - 0.35 * frac)      # smaller going up
        tilt = math.radians(min(p.leaf_angle + 4.0 * math.sin(2.1 * k), 30.0))
        leaf = _leaf(length, length * 0.34, max(3.0, length * 0.075))
        # tilt the leaf axis off the stem, lean its base into the stem wall
        leaf.apply_translation((0, 0, length * 0.42))     # base near origin
        leaf.apply_transform(
            trimesh.transformations.rotation_matrix(tilt, [0, 1, 0]))
        leaf.apply_translation((r_tip * 0.4, 0.0, z_att))
        leaf.apply_transform(
            trimesh.transformations.rotation_matrix(k * _GOLDEN, [0, 0, 1]))
        solids.append(leaf)
    return solids, [bore]
