#!/usr/bin/env python3
"""Render preview images of each pot style (docs only, not needed to print).

    python tools/render_previews.py [outdir]

Uses matplotlib rather than a GL renderer so it works headless.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flowerpot import PotParams, STYLES, build_pot  # noqa: E402

LIGHT = np.array([0.35, -0.75, 0.55])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


#: direction the camera looks *from* (matches view_init below)
EYE = np.array([0.491, -0.786, 0.375])


def render(ax, mesh, base_rgb=(0.80, 0.42, 0.30)):
    # backface culling: matplotlib has no depth buffer, so drawing the faces
    # that point away from the camera is what makes a solid look see-through
    facing = mesh.face_normals @ EYE > -0.02
    mesh = mesh.submesh([np.flatnonzero(facing)], append=True)

    tris = mesh.triangles
    normals = mesh.face_normals
    # cheap lambert shading + a little ambient
    shade = np.clip(normals @ LIGHT, 0.0, 1.0) * 0.75 + 0.25
    colors = np.clip(np.array(base_rgb)[None, :] * shade[:, None], 0, 1)

    # painter's algorithm: draw far triangles first
    order = np.argsort(tris.mean(axis=1) @ EYE)
    coll = Poly3DCollection(tris[order], facecolors=colors[order],
                            edgecolors="none", shade=False)
    ax.add_collection3d(coll)

    lo, hi = mesh.bounds
    span = (hi - lo).max() * 0.58
    mid = (lo + hi) / 2
    ax.set_xlim(mid[0] - span, mid[0] + span)
    ax.set_ylim(mid[1] - span, mid[1] + span)
    ax.set_zlim(lo[2], lo[2] + 2 * span)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=22, azim=-58)
    ax.set_axis_off()


def main(outdir: str = "docs/img") -> None:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(16, 4.6), dpi=110)
    for i, style in enumerate(STYLES):
        # a lighter mesh keeps matplotlib responsive; shape is identical
        mesh = build_pot(PotParams(pot_style=style, segments=120, vertical_step=2.5))
        ax = fig.add_subplot(1, len(STYLES), i + 1, projection="3d")
        render(ax, mesh)
        ax.set_title(style, fontsize=13, pad=-2)
        print(f"rendered {style}")
    fig.subplots_adjust(left=0.01, right=0.99, top=1.0, bottom=0.0, wspace=0.02)
    fig.savefig(out / "styles.png", transparent=False, facecolor="white")
    print(f"-> {out / 'styles.png'}")


if __name__ == "__main__":
    main(*sys.argv[1:])
