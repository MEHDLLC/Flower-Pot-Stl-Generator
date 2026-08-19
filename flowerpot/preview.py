"""PNG previews of a pot, rendered headless with matplotlib.

matplotlib is an optional dependency - only the ``--preview`` flag and the
docs renderer need it (``pip install matplotlib``).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .colors import hex_to_rgb01

#: direction the camera looks *from* (matches the view_init below)
EYE = np.array([0.491, -0.786, 0.375])
LIGHT = np.array([0.35, -0.75, 0.55]) / np.linalg.norm([0.35, -0.75, 0.55])


def _require_matplotlib():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: F401
        return matplotlib
    except ImportError as exc:                              # pragma: no cover
        raise RuntimeError(
            "previews need matplotlib: pip install matplotlib"
        ) from exc


def render_to_axes(ax, mesh, rgb=(0.80, 0.42, 0.30)) -> None:
    """Draw one mesh into a prepared 3D axes (shared by CLI and docs)."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    # backface culling: matplotlib has no depth buffer, so drawing the faces
    # that point away from the camera is what makes a solid look see-through
    facing = mesh.face_normals @ EYE > -0.02
    mesh = mesh.submesh([np.flatnonzero(facing)], append=True)

    tris = mesh.triangles
    # cheap lambert shading + a little ambient
    shade = np.clip(mesh.face_normals @ LIGHT, 0.0, 1.0) * 0.75 + 0.25
    colors = np.clip(np.asarray(rgb)[None, :] * shade[:, None], 0, 1)

    # painter's algorithm: draw far triangles first
    order = np.argsort(tris.mean(axis=1) @ EYE)
    ax.add_collection3d(Poly3DCollection(
        tris[order], facecolors=colors[order], edgecolors="none", shade=False))

    lo, hi = mesh.bounds
    span = (hi - lo).max() * 0.58
    mid = (lo + hi) / 2
    ax.set_xlim(mid[0] - span, mid[0] + span)
    ax.set_ylim(mid[1] - span, mid[1] + span)
    ax.set_zlim(lo[2], lo[2] + 2 * span)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=22, azim=-58)
    ax.set_axis_off()


def render_png(mesh, path: str | Path, color: str = "terracotta",
               title: str | None = None, dpi: int = 110) -> Path:
    """Render one pot to a PNG file.  Returns the path."""
    _require_matplotlib()
    import matplotlib.pyplot as plt

    path = Path(path)
    fig = plt.figure(figsize=(5.2, 5.2), dpi=dpi)
    ax = fig.add_subplot(projection="3d")
    render_to_axes(ax, mesh, hex_to_rgb01(color))
    if title:
        ax.set_title(title, fontsize=12, pad=-4)
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path
