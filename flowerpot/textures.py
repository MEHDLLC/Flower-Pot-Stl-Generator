"""Relief textures pressed into the outside of the wall.

A texture is a displacement field ``0..texture_depth`` (millimetres) added
*outside* the nominal wall - like the ribs, it never thins the wall below
``wall_thickness``.  Textures are independent of ``pot_style``, so a
herringbone hexagonal pot or a honeycomb spiral pot is fair game (the one
exception is ``low_poly_faceted``, whose deliberately sparse mesh cannot
carry a texture - there the texture is ignored with a warning).

Printability is designed in, then audited:

* every pattern is built from smoothstep ramps whose steepest gradient is
  bounded by ``depth / groove_width``, chosen so the worst additional lean
  stays around 30 degrees - inside the 45 degree budget even on top of the
  wall's own taper;
* the field fades to zero at the base (clean footprint), and below the rim
  chamfer (so the texture cannot stack on top of the chamfer's slope);
* patterns repeat an integer number of times around the pot, so there is
  no seam.
"""

from __future__ import annotations

import math

import numpy as np

from .params import PotParams
from .profile import Profiles, slope_budget, wall_radius, wall_slope

#: texture names -> Texture method (validated against params.TEXTURES)
_ROW = math.sqrt(3.0) / 2.0


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _ridge(frac, groove):
    """1 on a plateau, easing to 0 inside ``groove`` of either edge of the cell."""
    g = max(groove, 1e-6)
    return _smoothstep(frac / g) * _smoothstep((1.0 - frac) / g)


class Texture:
    """Callable displacement field ``tex(theta, z) -> mm`` for one pot."""

    def __init__(self, p: PotParams, r_ref: float, z_lo: float, z_hi: float,
                 section_slope=None):
        self.p = p
        self.depth = p.texture_depth
        #: gradient the style underneath already spends (ribs, mostly)
        self.section_slope = section_slope or (lambda z: 0.0)
        circumference = 2.0 * math.pi * r_ref
        #: whole number of pattern cells around the pot -> seamless wrap
        self.n_around = max(3, round(circumference / p.texture_cell))
        #: the arc length one cell actually gets
        self.cell_u = circumference / self.n_around
        self.cell_v = p.texture_cell
        self.z_lo, self.z_hi = z_lo, z_hi
        self.fade = 6.0                       # vertical ease-in/out band, mm
        self.fn = getattr(self, "_" + p.surface_texture)
        #: steepest dr/dz the pattern itself makes, per 1 mm of amplitude
        self.grad = self._measure_gradient()
        #: how much gradient the amplitude *ramp* may spend, and hence how
        #: far a ramp has to stretch (see :meth:`_window`)
        self.ramp = 0.10
        self.reach = max(2.0, self.depth / self.ramp)
        self._table_z, self._table = self._build_window_table()

    def _measure_gradient(self) -> float:
        """Max ``|d fn / dz|`` of the pattern, sampled over two cells."""
        theta = np.linspace(0.0, 2.0 * math.pi, 256, endpoint=False)
        step = 0.2
        zs = np.arange(0.0, 2.0 * self.cell_v + step, step)
        vals = np.array([self.fn(theta, float(z)) for z in zs])
        if len(vals) < 2:
            return 1.0
        return max(float(np.abs(np.diff(vals, axis=0)).max()) / step, 1e-6) * 1.1

    # -- amplitude window ------------------------------------------------
    def _envelope(self, z: float) -> float:
        """Amplitude fraction the overhang budget can afford at ``z``.

        The printed lean is ``arctan`` of the total radial gradient, and the
        wall has already spent ``|wall_slope|`` of it before the texture adds
        anything.  What is left over, minus the reserve kept for the ramp,
        divided by the pattern's own gradient, is the deepest the texture may
        be here - so it melts away exactly as fast as steep walls demand
        (vase bellies, bottle shoulders, wave flanks) and no faster.
        """
        a = float(_smoothstep(np.float64((z - self.z_lo) / self.fade)))
        b = float(_smoothstep(np.float64((self.z_hi - z) / self.fade)))
        room = (slope_budget(self.p) - self.ramp
                - abs(wall_slope(self.p, z)) - self.section_slope(z))
        afford = room / max(self.depth * self.grad, 1e-9)
        return min(a, b, max(afford, 0.0))

    def _build_window_table(self) -> tuple[np.ndarray, np.ndarray]:
        """Rate-limit the envelope so the ramp is a bounded gradient too.

        Melting is not free: sweeping the amplitude from nothing to full is
        itself a radial ramp, and a fast one stacks onto the wall just like
        the grooves do (a texture that snapped back to full depth beside a
        wave crest is what used to break the audit there).

        So the envelope is eroded by a cone of slope ``1 / reach``: the
        result is the lower envelope of cones planted on a *fixed* grid,
        which makes it ``1 / reach``-Lipschitz at every z, not merely at the
        sample points - a cone measured relative to z instead staircases,
        and a staircase has exactly the cliff this is meant to prevent.
        """
        step = 0.5
        zs = np.arange(self.z_lo - self.reach - step,
                       self.z_hi + self.reach + 2.0 * step, step)
        # each sample is the *minimum* across its cell, not the value at the
        # centre: the wall's slope steps at every curve breakpoint, and a
        # table that interpolated across such a step would ride over the top
        # of it and hand the texture amplitude the budget cannot afford
        env = np.array([min(self._envelope(float(z) + f * step)
                            for f in (-0.5, -0.25, 0.0, 0.25, 0.5))
                        for z in zs])
        eroded = env.copy()
        for i in range(1, int(math.ceil(self.reach / step)) + 1):
            penalty = i * step / self.reach
            eroded[i:] = np.minimum(eroded[i:], env[:-i] + penalty)
            eroded[:-i] = np.minimum(eroded[:-i], env[i:] + penalty)
        return zs, np.clip(eroded, 0.0, 1.0)

    def _window(self, z: float) -> float:
        return float(np.interp(z, self._table_z, self._table))

    def __call__(self, theta: np.ndarray, z: float) -> np.ndarray:
        amp = self.depth * self._window(z)
        if amp <= 0.0:
            return np.zeros_like(theta)
        return amp * self.fn(theta, float(z))

    # -- patterns (each returns values in [0, 1]) -------------------------
    def _waves(self, theta, z):
        """Concentric horizontal ripples, like a coil-built pot."""
        v = 0.5 - 0.5 * math.cos(2.0 * math.pi * z / self.cell_v)
        return np.full_like(theta, v)

    def _diamonds(self, theta, z):
        """Quilted diamonds: pillows between two crossing families of grooves.

        The product of the two wave families doubles the visual density, so
        the angular count is halved to keep one diamond per ``texture_cell``.
        """
        m = max(3, round(self.n_around / 2))
        cv = self.cell_v * 1.6                # diamonds look best a bit tall
        a = m * theta / (2.0 * math.pi) + z / cv
        b = m * theta / (2.0 * math.pi) - z / cv
        # flat-topped tiles with grooves along both diagonal families
        return _ridge(np.mod(a, 1.0), 0.22) * _ridge(np.mod(b, 1.0), 0.22)

    def _honeycomb(self, theta, z):
        """Raised hexagon tiles separated by grooves.

        The tiles are the Voronoi cells of a triangular lattice (rows offset
        by half a cell), evaluated per point: the groove lives where the
        nearest two lattice sites are equally far away.  Row-offset
        orientation is chosen deliberately - it avoids purely horizontal
        cell edges, which would carry the full displacement gradient as
        overhang.
        """
        n = self.n_around
        u = theta * (n / (2.0 * math.pi))            # column units, wraps at n
        row_h = self.cell_v * _ROW
        v = z / row_h                                 # row units

        j0 = math.floor(v)
        dists = []
        for j in (j0 - 1, j0, j0 + 1):
            off = 0.5 * (j & 1)
            i0 = np.floor(u - off)
            for di in (0.0, 1.0):
                cu = i0 + di + off
                du = (np.mod(u - cu + n / 2.0, n) - n / 2.0) * self.cell_u
                dv = (v - j) * row_h
                dists.append(np.hypot(du, dv))
        d = np.sort(np.stack(dists), axis=0)
        groove = self.cell_v * 0.28
        return _smoothstep((d[1] - d[0]) / groove)

    def _herringbone(self, theta, z):
        """Vertical columns of diagonal planks, direction alternating per column."""
        n = self.n_around
        u = theta * (n / (2.0 * math.pi))
        col = np.floor(u)
        t = u - col - 0.5                              # -0.5 .. 0.5 across a column
        direction = 1.0 - 2.0 * np.mod(col, 2.0)       # +1 / -1 alternating

        pitch = self.cell_v * 0.55                     # plank spacing
        s = (z + direction * t * self.cell_u) / pitch  # 45 degree stripe coordinate
        planks = _ridge(np.mod(s, 1.0), 0.28)

        # a groove where neighbouring columns meet, so the zigzag reads clearly
        edge = _smoothstep((0.5 - np.abs(t)) * self.cell_u / (self.cell_v * 0.15))
        return planks * edge


def make_texture(p: PotParams, prof: Profiles, section=None) -> Texture | None:
    """Build the texture field for a pot, or None if there is nothing to do.

    ``section`` is the style the texture will sit on: its own radial
    gradient comes out of the same overhang budget, so the texture has to
    know about it (ribs plus a deep texture on a vase flank used to add up
    past the limit).
    """
    if p.surface_texture == "none" or p.texture_depth <= 0:
        return None
    if p.pot_style == "low_poly_faceted":
        return None      # validate() warns about this combination

    z_hi = min(prof.decoration_freeze_z, p.height) - 2.0
    z_lo = 2.0
    if z_hi - z_lo < 10.0:
        return None      # pot too short for the fades to fit anything between

    r_ref = 0.5 * (wall_radius(p, z_lo) + wall_radius(p, z_hi))
    return Texture(p, r_ref, z_lo, z_hi,
                   section.decoration_slope if section is not None else None)
