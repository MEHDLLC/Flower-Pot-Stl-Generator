"""Mesh construction.

Strategy
--------
1. Sweep the outer silhouette around the chosen cross-section to get a closed
   solid (``lathe``).  The triangulation is generated directly, so this part
   is watertight by construction - no boolean needed and no chance of a gap.
2. Sweep the cavity the same way and subtract it.  The cavity overshoots the
   rim, which is what opens the mouth of the pot.
3. Subtract the drainage hole cylinders.

Steps 2 and 3 go through manifold3d (via trimesh), an exact boolean kernel:
if the inputs are manifold the output is manifold too.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .params import ParameterError, PotParams
from .profile import Profiles, build_profiles, resample, wall_radius
from .sections import Section, make_section

BOOLEAN_ENGINE = "manifold"


# ---------------------------------------------------------------------------
# the lathe
# ---------------------------------------------------------------------------
def lathe(
    rings: list[tuple[float, float]],
    section: Section,
    decorate: bool = True,
) -> trimesh.Trimesh:
    """Sweep ``rings`` = [(radius, z)] around the section into a closed solid.

    The mesh is a quad grid between consecutive rings plus a triangle fan
    cap at each end, all wound counter-clockwise seen from outside, so the
    normals point out and the volume is positive.
    """
    if len(rings) < 2:
        raise ParameterError("a lathe needs at least two rings")

    theta = section.thetas()
    nt = len(theta)

    verts = np.empty((len(rings) * nt + 2, 3), dtype=np.float64)
    for i, (r, z) in enumerate(rings):
        x, y = section.xy(theta, z, r, decorate)
        verts[i * nt:(i + 1) * nt, 0] = x
        verts[i * nt:(i + 1) * nt, 1] = y
        verts[i * nt:(i + 1) * nt, 2] = z

    bottom_c = len(rings) * nt          # centre of the bottom cap
    top_c = bottom_c + 1                # centre of the top cap
    verts[bottom_c] = (0.0, 0.0, rings[0][1])
    verts[top_c] = (0.0, 0.0, rings[-1][1])

    j = np.arange(nt)
    jn = (j + 1) % nt
    faces: list[np.ndarray] = []

    # side wall: two triangles per quad, outward normal = dtheta x dz
    for i in range(len(rings) - 1):
        a = i * nt + j
        b = i * nt + jn
        c = (i + 1) * nt + jn
        d = (i + 1) * nt + j
        faces.append(np.column_stack([a, b, c]))
        faces.append(np.column_stack([a, c, d]))

    # caps (bottom faces down, top faces up)
    faces.append(np.column_stack([np.full(nt, bottom_c), jn, j]))
    last = (len(rings) - 1) * nt
    faces.append(np.column_stack([np.full(nt, top_c), last + j, last + jn]))

    # process=True welds the seam and drops any zero-area face at the caps
    mesh = trimesh.Trimesh(
        vertices=verts, faces=np.vstack(faces), process=True, validate=True
    )
    if not mesh.is_winding_consistent:
        mesh.fix_normals()
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def _boolean(op: str, meshes: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    fn = {"difference": trimesh.boolean.difference,
          "union": trimesh.boolean.union}[op]
    try:
        return fn(meshes, engine=BOOLEAN_ENGINE)
    except Exception as exc:                                  # pragma: no cover
        raise RuntimeError(
            f"boolean {op} failed ({exc}). Install the exact kernel with "
            f"`pip install manifold3d`."
        ) from exc


# ---------------------------------------------------------------------------
# drainage
# ---------------------------------------------------------------------------
def drainage_positions(p: PotParams, prof: Profiles) -> list[tuple[float, float]]:
    """(x, y) centres for the drainage holes, clipped to the flat floor."""
    if p.drainage_pattern == "none" or p.drainage_hole_radius <= 0:
        return []

    # holes must stay clear of the fillet at the foot of the cavity wall
    margin = max(1.5, p.wall_thickness * 0.5)
    usable = prof.cavity_floor_radius - p.drainage_hole_radius - margin
    if usable <= 0:
        raise ParameterError(
            "drainage_hole_radius is too big for this floor: "
            f"holes of r={p.drainage_hole_radius} do not fit inside a floor of "
            f"r={prof.cavity_floor_radius:.1f}"
        )

    n = max(1, int(p.num_drainage_holes))
    pattern = p.drainage_pattern

    if pattern == "center":
        return [(0.0, 0.0)]

    if pattern == "ring":
        rr = usable * float(np.clip(p.drainage_ring_fraction, 0.0, 1.0))
        # keep neighbouring holes from merging into a slot
        min_r = (p.drainage_hole_radius + 1.5) / math.sin(math.pi / n) if n > 1 else 0.0
        rr = max(rr, min(min_r, usable))
        return [
            (rr * math.cos(2 * math.pi * k / n), rr * math.sin(2 * math.pi * k / n))
            for k in range(n)
        ]

    if pattern == "grid":
        pitch = 2.0 * p.drainage_hole_radius + max(3.0, p.wall_thickness)
        span = int(math.ceil(usable / pitch)) + 1
        cand = [
            (i * pitch, j * pitch)
            for i in range(-span, span + 1)
            for j in range(-span, span + 1)
            if math.hypot(i * pitch, j * pitch) <= usable + 1e-9
        ]
        cand.sort(key=lambda xy: (math.hypot(*xy), math.atan2(xy[1], xy[0])))
        return cand[:n]

    raise ParameterError(f"unknown drainage_pattern {pattern!r}")


def drainage_cutters(p: PotParams, prof: Profiles) -> list[trimesh.Trimesh]:
    """Cylinders that punch through the floor."""
    cutters = []
    top = prof.floor_top_z + max(p.inner_base_chamfer, 0.0) + 4.0
    height = top + 4.0
    for x, y in drainage_positions(p, prof):
        cyl = trimesh.creation.cylinder(
            radius=p.drainage_hole_radius,
            height=height,
            sections=max(24, p.segments // 4),
        )
        cyl.apply_translation((x, y, height / 2.0 - 2.0))
        cutters.append(cyl)
    return cutters


# ---------------------------------------------------------------------------
# the pot
# ---------------------------------------------------------------------------
def build_pot(p: PotParams) -> trimesh.Trimesh:
    """Build one pot and return a watertight mesh, positioned on z = 0."""
    p.validate()
    section = make_section(p)
    prof = build_profiles(p)
    section.freeze_z = prof.decoration_freeze_z

    smooth = section.smooth_vertically()
    outer_rings = resample(
        prof.outer, p.vertical_step,
        section.extra_ring_heights(0.0, p.height), smooth,
    )
    inner_rings = resample(
        prof.inner, p.vertical_step,
        section.extra_ring_heights(prof.floor_top_z, p.height), smooth,
    )

    body = lathe(outer_rings, section, decorate=True)
    cavity = lathe(inner_rings, section, decorate=False)

    pot = _boolean("difference", [body, cavity])
    cutters = drainage_cutters(p, prof)
    if cutters:
        pot = _boolean("difference", [pot] + cutters)

    return _finish(pot)


def build_saucer(p: PotParams) -> trimesh.Trimesh:
    """A matching drip tray, styled like the pot it belongs to.

    Sizing is worst case so the pot always drops in freely:

    * the pot is measured at the *top* of the saucer, where its taper has
      made it widest inside the tray;
    * decorative ribs are counted as extra radius;
    * for the polygonal styles the saucer and the pot can end up rotated
      relative to each other, so a pot *corner* has to clear a saucer
      *flat* - which is ``1 / cos(pi / sides)`` further out.
    """
    p.validate()

    bulge = p.rib_depth if p.pot_style == "ribbed_spiral" else 0.0
    reach = max(p.bottom_radius, wall_radius(p, min(p.saucer_height, p.height)) + bulge)
    corner_to_flat = 1.0
    if p.pot_style in ("hexagonal", "low_poly_faceted"):
        corner_to_flat = 1.0 / math.cos(math.pi / p.sides)

    inner_floor = (reach + p.saucer_clearance) * corner_to_flat
    outer_floor = inner_floor + p.saucer_wall
    flare = math.tan(math.radians(8.0)) * p.saucer_height   # gentle outward flare

    sp = p.with_(
        height=p.saucer_height,
        bottom_diameter=2.0 * outer_floor,
        top_diameter=2.0 * (outer_floor + flare),
        wall_thickness=p.saucer_wall,
        base_thickness=p.saucer_base,
        add_top_rim=False,
        belly=0.0,
        inner_base_chamfer=min(2.0, p.saucer_wall),
        drainage_pattern="none",
        facet_bands=max(1, p.facet_bands // 3),
        rib_twist_degrees=p.rib_twist_degrees * p.saucer_height / max(p.height, 1e-9),
    )
    section = make_section(sp)
    prof = build_profiles(sp)
    section.freeze_z = prof.decoration_freeze_z
    smooth = section.smooth_vertically()
    body = lathe(
        resample(prof.outer, sp.vertical_step,
                 section.extra_ring_heights(0.0, sp.height), smooth),
        section, decorate=True)
    cavity = lathe(
        resample(prof.inner, sp.vertical_step,
                 section.extra_ring_heights(prof.floor_top_z, sp.height), smooth),
        section, decorate=False)
    return _finish(_boolean("difference", [body, cavity]))


def _finish(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Tidy a boolean result and drop it on the build plate."""
    mesh.process(validate=True)
    mesh.remove_unreferenced_vertices()
    mesh.merge_vertices()
    if not mesh.is_winding_consistent:
        mesh.fix_normals()
    if mesh.volume < 0:
        mesh.invert()
    # sit exactly on z = 0, centred in x/y
    lo = mesh.bounds[0]
    hi = mesh.bounds[1]
    mesh.apply_translation((-(lo[0] + hi[0]) / 2.0, -(lo[1] + hi[1]) / 2.0, -lo[2]))
    return mesh
