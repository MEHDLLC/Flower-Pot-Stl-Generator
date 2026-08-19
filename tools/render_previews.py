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


def main(outdir: str = "docs/img") -> None:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    grid([(s, PotParams(pot_style=s, **FAST)) for s in STYLES], out / "styles.png")
    grid(
        [(t, PotParams(surface_texture=t, **FAST))
         for t in TEXTURES if t != "none"],
        out / "textures.png",
    )


if __name__ == "__main__":
    main(*sys.argv[1:])
