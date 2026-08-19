"""Print-readiness audit for a finished mesh.

Checks the three things that actually stop a pot from printing:

* **manifold** - watertight, consistently wound, positive volume, no
  degenerate faces.  Slicers silently mangle anything else.
* **overhangs** - every downward facing surface must lean no more than
  ``overhang_limit_deg`` from vertical, otherwise it needs supports.  The
  footprint touching the build plate is exempt: it is supported by the bed.
* **flat base** - enough contact area with the plate to stick.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import trimesh

#: faces whose vertices all sit within this many mm of z=0 count as "on the plate"
PLATE_TOL = 0.05


@dataclass
class Report:
    watertight: bool
    winding_consistent: bool
    positive_volume: bool
    degenerate_faces: int
    faces: int
    vertices: int
    genus: int
    volume_cm3: float
    size_mm: tuple[float, float, float]
    base_area_cm2: float
    worst_overhang_deg: float
    overhang_faces: int
    overhang_area_cm2: float
    overhang_limit_deg: float
    warnings: list[str] = field(default_factory=list)

    @property
    def manifold(self) -> bool:
        return (
            self.watertight
            and self.winding_consistent
            and self.positive_volume
            and self.degenerate_faces == 0
        )

    @property
    def ok(self) -> bool:
        return self.manifold and self.overhang_faces == 0

    def __str__(self) -> str:
        tick = lambda b: "OK  " if b else "FAIL"
        lines = [
            f"  {tick(self.watertight)} watertight",
            f"  {tick(self.winding_consistent)} consistent normals (no inverted faces)",
            f"  {tick(self.positive_volume)} positive volume, {self.degenerate_faces} degenerate faces",
            f"  {tick(self.overhang_faces == 0)} overhangs: worst {self.worst_overhang_deg:.1f} deg "
            f"vs {self.overhang_limit_deg:.0f} deg limit"
            + ("" if self.overhang_faces == 0
               else f" ({self.overhang_faces} faces, {self.overhang_area_cm2:.2f} cm2)"),
            f"       {self.faces} faces / {self.vertices} vertices, genus {self.genus}",
            f"       size {self.size_mm[0]:.1f} x {self.size_mm[1]:.1f} x {self.size_mm[2]:.1f} mm, "
            f"material {self.volume_cm3:.1f} cm3, bed contact {self.base_area_cm2:.1f} cm2",
        ]
        lines += [f"  WARN {w}" for w in self.warnings]
        return "\n".join(lines)


def audit(mesh: trimesh.Trimesh, overhang_limit_deg: float = 45.0) -> Report:
    """Measure a mesh against the print requirements."""
    normals = mesh.face_normals
    areas = mesh.area_faces
    tris = mesh.triangles

    # --- overhangs ----------------------------------------------------
    # For a downward facing triangle the lean from vertical is
    # arcsin(-nz): 0 deg for a vertical wall, 90 deg for a flat ceiling.
    nz = np.clip(-normals[:, 2], -1.0, 1.0)
    lean = np.degrees(np.arcsin(nz))
    on_plate = np.all(tris[:, :, 2] <= PLATE_TOL, axis=1)
    considered = ~on_plate
    bad = considered & (lean > overhang_limit_deg + 1e-6)

    worst = float(lean[considered].max()) if considered.any() else 0.0
    base_area = float(areas[on_plate].sum())

    # --- topology -----------------------------------------------------
    degenerate = int((areas <= 1e-9).sum())
    genus = int(round((2 - mesh.euler_number) / 2)) if mesh.is_watertight else -1

    warnings: list[str] = []
    if base_area < 200.0:
        warnings.append(
            f"only {base_area / 100:.1f} cm2 touching the plate - use a brim"
        )
    if mesh.body_count > 1:
        warnings.append(f"mesh contains {mesh.body_count} separate bodies")

    return Report(
        watertight=bool(mesh.is_watertight),
        winding_consistent=bool(mesh.is_winding_consistent),
        positive_volume=bool(mesh.volume > 0),
        degenerate_faces=degenerate,
        faces=len(mesh.faces),
        vertices=len(mesh.vertices),
        genus=genus,
        volume_cm3=float(mesh.volume) / 1000.0,
        size_mm=tuple(float(v) for v in mesh.extents),
        base_area_cm2=base_area / 100.0,
        worst_overhang_deg=worst,
        overhang_faces=int(bad.sum()),
        overhang_area_cm2=float(areas[bad].sum()) / 100.0,
        overhang_limit_deg=float(overhang_limit_deg),
        warnings=warnings,
    )
