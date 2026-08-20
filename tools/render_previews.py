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


def mesh_grid(cases, path: Path, elev: float = 22.0, azim: float = -58.0) -> None:
    """Like grid(), but for prebuilt meshes."""
    fig = plt.figure(figsize=(4 * len(cases), 4.6), dpi=110)
    for i, (label, mesh, color) in enumerate(cases):
        ax = fig.add_subplot(1, len(cases), i + 1, projection="3d")
        render_to_axes(ax, mesh, hex_to_rgb01(color), elev=elev, azim=azim)
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


def modular_figure(out: Path) -> None:
    import math
    import trimesh
    from flowerpot.modular import (_BOSS_OUT, _HUB_R, _HUB_WALL, _hub_height,
                                   build_flower_center, build_flower_petal,
                                   build_seed_tray, build_stack_hub,
                                   build_stack_pod)
    p = PotParams(modular_kit="seed_cubes", **FAST)

    tray = build_seed_tray(p, 2)
    cube = build_seed_tray(p, 1)
    W1, W2 = p.cube_size + 2.4, 2 * p.cube_size + 2.4
    c = cube.copy()
    c.apply_translation((W2 / 2 + _BOSS_OUT + W1 / 2, p.cube_size / 2, 0))
    seed = trimesh.util.concatenate([tray, c])

    parts = [build_flower_center(p)]
    petal = build_flower_petal(p)
    for k in range(5):
        q = petal.copy()
        q.apply_transform(trimesh.transformations.rotation_matrix(
            2 * math.pi * k / 5, [0, 0, 1]))
        parts.append(q)
    flower = trimesh.util.concatenate(parts)

    hub = build_stack_hub(p)
    pod = build_stack_pod(p)
    zu = _hub_height(p) + _HUB_WALL + 0.2
    pieces = [hub]
    upper = hub.copy()
    upper.apply_transform(trimesh.transformations.rotation_matrix(
        math.radians(45), [0, 0, 1]))
    upper.apply_translation((0, 0, zu))
    pieces.append(upper)
    for level, angles in ((0.0, (0, 90, 180, 270)), (zu, (45, 135))):
        for a in angles:
            q = pod.copy()
            q.apply_transform(trimesh.transformations.rotation_matrix(
                math.pi, [0, 0, 1]))
            q.apply_translation((_HUB_R + _BOSS_OUT + p.stack_pod_diameter / 2,
                                 0, 0))
            q.apply_transform(trimesh.transformations.rotation_matrix(
                math.radians(a), [0, 0, 1]))
            q.apply_translation((0, 0, level))
            pieces.append(q)
    stack = trimesh.util.concatenate(pieces)

    mesh_grid([
        ("seed tray 2x2 + docked single", seed, "terracotta"),
        ("flower: centre + 5 petals", flower, "blush"),
        ("rotating stack, level 2 at 45\u00b0", stack, "sage"),
    ], out / "modular.png")


def drainage_figure(out: Path) -> None:
    """Underside views: this is where the drainage options actually live."""
    cases = []
    for pattern in ("center", "ring", "grid", "none"):
        p = PotParams(drainage_pattern=pattern, num_drainage_holes=5, **FAST)
        cases.append((f"drainage: {pattern}", build_pot(p), "clay"))
    mesh_grid(cases, out / "drainage.png", elev=-38, azim=-58)


def extras_figure(out: Path) -> None:
    from flowerpot import build_saucer
    with_rim = PotParams(**FAST)
    no_rim = PotParams(add_top_rim=False, **FAST)
    saucer_p = PotParams(generate_saucer=True, **FAST)
    mesh_grid([
        ("rim (default)", build_pot(with_rim), "terracotta"),
        ("no rim", build_pot(no_rim), "terracotta"),
        ("drip saucer", build_saucer(saucer_p), "terracotta"),
    ], out / "extras.png")


def colors_figure(out: Path) -> None:
    from flowerpot.colors import PALETTE
    p = PotParams(height=70, top_diameter=80, bottom_diameter=60,
                  drainage_hole_radius=3.0, rim_width=4.0, rim_height=6.0,
                  segments=80, vertical_step=3.0)
    mesh = build_pot(p)
    names = sorted(PALETTE)
    fig = plt.figure(figsize=(2.1 * 6, 2.4 * 2), dpi=110)
    for i, name in enumerate(names):
        ax = fig.add_subplot(2, 6, i + 1, projection="3d")
        render_to_axes(ax, mesh, hex_to_rgb01(name))
        ax.set_title(name, fontsize=10, pad=-4)
        print(f"rendered color {name}")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.97, bottom=0.0,
                        wspace=0.02, hspace=0.05)
    fig.savefig(out / "colors.png", facecolor="white")
    print(f"-> {out / 'colors.png'}")


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
    modular_figure(out)
    drainage_figure(out)
    extras_figure(out)
    colors_figure(out)


if __name__ == "__main__":
    main(*sys.argv[1:])
