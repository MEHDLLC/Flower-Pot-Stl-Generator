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
from .textures import make_texture

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
          "union": trimesh.boolean.union,
          "intersection": trimesh.boolean.intersection}[op]
    try:
        return fn(meshes, engine=BOOLEAN_ENGINE)
    except Exception as exc:                                  # pragma: no cover
        raise RuntimeError(
            f"boolean {op} failed ({exc}). Install the exact kernel with "
            f"`pip install manifold3d`."
        ) from exc


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


def side_drainage_cutters(p: PotParams, prof: Profiles) -> list[trimesh.Trimesh]:
    """Grow-pot side drainage: diamond ports through the wall just above the
    floor.  Diamond, not round - a round horizontal hole's ceiling would blow
    the overhang budget; the diamond's roof stays near 35 degrees."""
    if p.num_side_holes <= 0:
        return []
    r = p.side_hole_radius
    z_center = prof.floor_top_z + max(p.inner_base_chamfer, 0.0) + r + 3.0
    reach = prof.rim_outer_radius + p.rib_depth + p.texture_depth + 6.0
    cutters = []
    for k in range(int(p.num_side_holes)):
        a = 2.0 * math.pi * k / p.num_side_holes
        port = _diamond_port(x0=p.bottom_radius * 0.35, x1=reach,
                             z_center=z_center, half_w=r,
                             up=r * 1.4, down=r * 1.1)
        port.apply_transform(
            trimesh.transformations.rotation_matrix(a, [0, 0, 1]))
        cutters.append(port)
    return cutters


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
    section.texture = make_texture(p, prof)

    # a texture's grooves need rings a bit closer together than a bare wall
    step = p.vertical_step
    if section.texture is not None:
        step = min(step, p.texture_cell / 12.0)

    smooth = section.smooth_vertically()
    outer_rings = resample(
        prof.outer, step,
        section.extra_ring_heights(0.0, p.height), smooth,
    )
    inner_rings = resample(
        prof.inner, p.vertical_step,
        section.extra_ring_heights(prof.floor_top_z, p.height), smooth,
    )

    body = lathe(outer_rings, section, decorate=True)
    cavity = lathe(inner_rings, section, decorate=False)

    pot = _boolean("difference", [body, cavity])
    cutters = drainage_cutters(p, prof) + side_drainage_cutters(p, prof)
    if p.jar_greenhouse:
        from .jar import seat_cutters
        cutters = cutters + seat_cutters(p, p.height)
    if cutters:
        pot = _boolean("difference", [pot] + cutters)

    if p.stem:
        from .stem import stem_parts
        solids, stem_cutters = stem_parts(p, prof.floor_top_z)
        pot = _boolean("union", [pot] + solids)
        pot = _boolean("difference", [pot] + stem_cutters)

    # the stem grows past the mouth: don't recentre around it
    return _finish(pot, center=not p.stem)


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
        surface_texture="none",
        jar_greenhouse=False,
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


def _finish(mesh: trimesh.Trimesh, center: bool = True) -> trimesh.Trimesh:
    """Tidy a boolean result and drop it on the build plate.

    The repair passes only run when the mesh actually needs them: an exact
    boolean can emit legitimate sliver triangles (e.g. where a trim plane
    grazes a union seam), and ``process(validate=True)`` would delete those
    as "degenerate" - tearing holes into a mesh that was watertight.
    """
    if not (mesh.is_watertight and mesh.is_winding_consistent):
        mesh.process(validate=True)
        mesh.remove_unreferenced_vertices()
        mesh.merge_vertices()
    if not mesh.is_winding_consistent:
        mesh.fix_normals()
    if mesh.volume < 0:
        mesh.invert()
    # sit exactly on z = 0; recentre in x/y unless the caller keeps the pot
    # axis at the origin (asymmetric adds like the refill tube would drag
    # the bounding-box centre - and the cavity - off axis)
    lo = mesh.bounds[0]
    hi = mesh.bounds[1]
    dx = -(lo[0] + hi[0]) / 2.0 if center else 0.0
    dy = -(lo[1] + hi[1]) / 2.0 if center else 0.0
    mesh.apply_translation((dx, dy, -lo[2]))
    return mesh
