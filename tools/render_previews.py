#!/usr/bin/env python3
"""Render the documentation images (styles and textures grids).

    python tools/render_previews.py [outdir]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from flowerpot import PotParams, STYLES, build_pot          # noqa: E402
from flowerpot.colors import hex_to_rgb01                   # noqa: E402
from flowerpot.params import TEXTURES                       # noqa: E402
from flowerpot.preview import render_to_axes                # noqa: E402

FAST = dict(segments=120, vertical_step=2.5)


def grid(cases: list[tuple[str, PotParams]], path: Path) -> None:
    fig = plt.figure(figsize=(4 * len(cases), 4.6), dpi=110)
    for i, (label, params) in enumerate(cases):
        mesh = build_pot(params)
        ax = fig.add_subplot(1, len(cases), i + 1, projection="3d")
        render_to_axes(ax, mesh, hex_to_rgb01(params.color))
        ax.set_title(label, fontsize=13, pad=-2)
        print(f"rendered {label}")
    fig.subplots_adjust(left=0.01, right=0.99, top=1.0, bottom=0.0, wspace=0.02)
    fig.savefig(path, facecolor="white")
    print(f"-> {path}")


def mesh_grid(cases, path: Path) -> None:
    """Like grid(), but for prebuilt meshes."""
    fig = plt.figure(figsize=(4 * len(cases), 4.6), dpi=110)
    for i, (label, mesh, color) in enumerate(cases):
        ax = fig.add_subplot(1, len(cases), i + 1, projection="3d")
        render_to_axes(ax, mesh, hex_to_rgb01(color))
        ax.set_title(label, fontsize=13, pad=-2)
        print(f"rendered {label}")
    fig.subplots_adjust(left=0.01, right=0.99, top=1.0, bottom=0.0, wspace=0.02)
    fig.savefig(path, facecolor="white")
    print(f"-> {path}")


def selfwatering_figure(out: Path) -> None:
    from flowerpot.selfwatering import (build_self_watering_inner,
                                        build_self_watering_outer)
    p = PotParams(self_watering=True, **FAST)
    outer = build_self_watering_outer(p)
    inner = build_self_watering_inner(p)
    cases = [("outer: reservoir + refill tube", outer, "teal"),
             ("inner: wick-cup liner", inner, "teal")]
    try:                    # the cutaway needs shapely+rtree; skip if absent
        import trimesh
        half = trimesh.intersections.slice_mesh_plane(
            inner, plane_normal=[0, -1, 0], plane_origin=[0, 0, 0], cap=True)
        cases.append(("inner, cut open", half, "sand"))
    except BaseException as exc:
        print(f"skipping cutaway ({exc})")
    mesh_grid(cases, out / "selfwatering.png")


def insert_figure(out: Path) -> None:
    from flowerpot.insert import build_insert_platform, build_insert_tube
    cases = []
    for shape in ("round", "square", "hexagonal"):
        p = PotParams(reservoir_insert=True, insert_shape=shape, **FAST)
        cases.append((f"platform ({shape})", build_insert_platform(p), "charcoal"))
    cases.append(("fill tube",
                  build_insert_tube(PotParams(reservoir_insert=True, **FAST)),
                  "charcoal"))
    mesh_grid(cases, out / "insert.png")


def hydro_figure(out: Path) -> None:
    import trimesh
    from flowerpot.hydro import (_SPIGOT_H, build_hydro_cap, build_hydro_cup,
                                 build_hydro_segment)
    p = PotParams(hydro_tower=True, **FAST)
    seg = build_hydro_segment(p)
    upper = seg.copy()
    upper.apply_translation((0, 0, p.segment_height - _SPIGOT_H))
    mesh_grid([
        ("segment", seg, "sage"),
        ("two stacked", trimesh.util.concatenate([seg, upper]), "sage"),
        ("net cup", build_hydro_cup(p), "sand"),
        ("cap", build_hydro_cap(p), "sage"),
    ], out / "hydro.png")


def jar_figure(out: Path) -> None:
    import trimesh
    from flowerpot.jar import build_jar_ring
    p = PotParams(jar_greenhouse=True, **FAST)
    pot = build_pot(p)
    half = trimesh.intersections.slice_mesh_plane(
        pot, plane_normal=[0, -1, 0], plane_origin=[0, 0, 0], cap=True)
    ring = build_jar_ring(PotParams(jar_greenhouse=True,
                                    reservoir_insert=True, **FAST))
    mesh_grid([
        ("classic pot + jar seat", pot, "terracotta"),
        ("cut open: neck, groove, shaft", half, "sand"),
        ("jar collar (for the insert)", ring, "charcoal"),
    ], out / "jar.png")


def main(outdir: str = "docs/img") -> None:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    grid([(s, PotParams(pot_style=s, **FAST)) for s in STYLES], out / "styles.png")
    grid(
        [(t, PotParams(surface_texture=t, **FAST))
         for t in TEXTURES if t != "none"],
        out / "textures.png",
    )
    selfwatering_figure(out)
    insert_figure(out)
    hydro_figure(out)
    jar_figure(out)


if __name__ == "__main__":
    main(*sys.argv[1:])
