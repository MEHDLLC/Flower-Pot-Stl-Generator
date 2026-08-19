"""Cross-section shapes: what the pot looks like when sliced horizontally.

A :class:`Section` turns a *nominal radius* ``r`` at a height ``z`` into the
actual (x, y) outline of the pot at that height.  Keeping this separate from
the vertical silhouette means every style works with every set of dimensions,
every drainage pattern and the saucer.

Conventions
-----------
* ``r`` is the **maximum** radius of the outline (corner-to-corner for the
  polygonal styles), so the bounding box of a finished pot always matches
  ``top_diameter``/``bottom_diameter``.
* The inner cavity re-uses the same section so the wall keeps a constant
  thickness; decorative additions (the ribs) are switched off for the cavity
  with ``decorate=False``.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from .params import PotParams


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _rounded_polygon_radius(theta: np.ndarray, sides: int, corner_frac: float) -> np.ndarray:
    """Radius of a regular polygon with rounded corners, normalised to max 1.

    Built as the Minkowski sum of a smaller polygon (circumradius ``1 - q``)
    and a disc of radius ``q`` where ``q = corner_frac``.  That keeps the
    corners tangent-continuous, which both looks better and avoids knife
    edges that a slicer cannot reproduce.
    """
    n = int(sides)
    q = float(np.clip(corner_frac, 0.0, 0.45))
    ri = 1.0 - q                       # circumradius of the inner (sharp) polygon
    half = math.pi / n                 # half angle of one facet
    apo = ri * math.cos(half) + q      # distance to the flat faces
    ymax = ri * math.sin(half)         # half width of the straight part of a face

    # fold every angle into a single facet: theta_local in [-half, +half]
    tl = np.mod(theta + half, 2.0 * half) - half

    if q <= 1e-9:                      # sharp polygon, closed form
        return apo / np.cos(tl)

    theta_flat = math.atan2(ymax, apo)
    flat = np.abs(tl) <= theta_flat

    out = np.empty_like(tl)
    # straight faces
    out[flat] = apo / np.cos(tl[flat])
    # corner arcs: intersect the ray with the circle centred on the corner
    if np.any(~flat):
        tc = tl[~flat]
        cx = ri * math.cos(half)
        cy = ri * math.sin(half) * np.sign(tc)
        b = cx * np.cos(tc) + cy * np.sin(tc)
        c = ri * ri - q * q
        out[~flat] = b + np.sqrt(np.maximum(b * b - c, 0.0))
    return out


def _triangle_wave(u: np.ndarray | float) -> np.ndarray | float:
    """0 -> 1 -> 0 -> 1 ... with period 2.  Continuous, which keeps the
    faceted style printable (no horizontal ledges between bands)."""
    f = np.mod(u, 2.0)
    return np.where(f <= 1.0, f, 2.0 - f)


# ---------------------------------------------------------------------------
# sections
# ---------------------------------------------------------------------------
class Section:
    """Base class: a plain circle."""

    #: multiplies the horizontal wall offset so the *perpendicular* wall
    #: thickness comes out right (flats of a polygon sit closer to the centre
    #: than its corners).
    inner_offset_factor: float = 1.0

    def __init__(self, params: PotParams):
        self.p = params
        #: Optional relief displacement field (see :mod:`flowerpot.textures`),
        #: set by the builder.  Applied outside the style's own shape, and
        #: only on the decorated (outer) surface.
        self.texture = None
        #: Above this height the decoration stops evolving (ribs stop
        #: twisting, facets stop rotating).  The builder sets it to the foot
        #: of the rim chamfer: if the outline kept turning while the chamfer
        #: sloped outwards, the two motions would add up and push the
        #: underside of the rim past the overhang limit.
        self.freeze_z: float = float("inf")

    def _dec_z(self, z: float) -> float:
        """Height used for decoration, clamped at :attr:`freeze_z`."""
        return min(z, self.freeze_z)

    # -- outline -------------------------------------------------------
    def radius(self, theta: np.ndarray, z: float, r: float, decorate: bool) -> np.ndarray:
        rad = self._shape_radius(theta, z, r, decorate)
        if decorate and self.texture is not None:
            rad = rad + self.texture(theta, z)
        return rad

    def _shape_radius(self, theta: np.ndarray, z: float, r: float, decorate: bool) -> np.ndarray:
        return np.full_like(theta, r)

    def xy(self, theta: np.ndarray, z: float, r: float, decorate: bool = True):
        rad = self.radius(theta, z, r, decorate)
        return rad * np.cos(theta), rad * np.sin(theta)

    # -- sampling ------------------------------------------------------
    def _theta_count(self) -> int:
        """Samples around the pot: at least ``segments``, more when a texture
        needs the resolution to draw its grooves."""
        n = int(self.p.segments)
        if self.texture is not None:
            n = max(n, min(480, self.texture.n_around * 12))
        return n

    def thetas(self) -> np.ndarray:
        """Angles sampled around the pot.  Polygonal styles round the count up
        so that every corner lands exactly on a sample."""
        return np.linspace(0.0, 2.0 * math.pi, self._theta_count(), endpoint=False)

    def extra_ring_heights(self, z0: float, z1: float) -> list[float]:
        """Heights that must get their own ring of vertices (style features)."""
        return []

    def smooth_vertically(self) -> bool:
        """True if the wall should be resampled at ``vertical_step``.

        The low-poly style says no: leaving long spans between rings is
        exactly what makes the facets read as flat triangles.
        """
        return True


class RoundSection(Section):
    """classic_tapered - a plain circle."""


class RibbedSection(Section):
    """ribbed_spiral - sinusoidal flutes standing proud of the wall.

    The ribs are *added* outside the nominal radius, never carved into it,
    so the wall is never thinner than ``wall_thickness``.  They fade out over
    the first few millimetres so the pot still meets the bed with a clean
    round footprint.
    """

    def _shape_radius(self, theta, z, r, decorate):
        p = self.p
        if not decorate or p.rib_depth <= 0 or p.rib_count <= 0:
            return np.full_like(theta, r)

        twist = math.radians(p.rib_twist_degrees) * (self._dec_z(z) / max(p.height, 1e-9))
        wave = 0.5 + 0.5 * np.cos(p.rib_count * (theta + twist))

        depth = p.rib_depth
        if p.base_flat:
            # ramp the ribs in above the base; the ramp angle stays well under
            # the overhang limit because fade >= 2 * rib_depth.
            fade = max(2.0 * p.rib_depth, 5.0)
            depth *= min(1.0, max(0.0, z / fade))
        return r + depth * wave


class PolygonSection(Section):
    """hexagonal - a straight prism with rounded corners."""

    def __init__(self, params: PotParams):
        super().__init__(params)
        self.n = params.sides
        self.inner_offset_factor = 1.0 / math.cos(math.pi / self.n)

    def _corner_frac(self, r: float) -> float:
        return self.p.hex_corner_round / max(r, 1e-6)

    def phase(self, z: float) -> float:
        return 0.0

    def _shape_radius(self, theta, z, r, decorate):
        return r * _rounded_polygon_radius(
            theta + self.phase(z), self.n, self._corner_frac(r)
        )

    def thetas(self) -> np.ndarray:
        # a multiple of 2 * sides guarantees samples land on both the corner
        # tips and the middle of every flat face
        step = 2 * self.n
        n = int(math.ceil(self._theta_count() / step) * step)
        return np.linspace(0.0, 2.0 * math.pi, n, endpoint=False)


class FacetedSection(PolygonSection):
    """low_poly_faceted - a polygon whose corners zig-zag up the pot.

    Over one band the outline rotates by half a facet, over the next it
    rotates back.  Rings are only placed at the band boundaries, so the
    surface between them is a ruled band of flat triangles: the low-poly
    crystal look.  Because the rotation is continuous there are no downward
    facing ledges, so the whole thing still prints unsupported.
    """

    def __init__(self, params: PotParams):
        super().__init__(params)
        self.bands = max(1, int(params.facet_bands))

    def phase(self, z: float) -> float:
        if not self.p.facet_rotate:
            return 0.0
        u = (self._dec_z(z) / max(self.p.height, 1e-9)) * self.bands
        return (math.pi / self.n) * float(_triangle_wave(u))

    def extra_ring_heights(self, z0: float, z1: float) -> list[float]:
        h = self.p.height
        return [h * k / self.bands for k in range(self.bands + 1) if z0 < h * k / self.bands < z1]

    def smooth_vertically(self) -> bool:
        return False


_SECTIONS = {
    "classic_tapered": RoundSection,
    "ribbed_spiral": RibbedSection,
    "hexagonal": PolygonSection,
    "low_poly_faceted": FacetedSection,
}


def make_section(params: PotParams) -> Section:
    """Section factory for ``params.pot_style``."""
    return _SECTIONS[params.pot_style](params)
