"""Vertical silhouette (the "lathe profile") of the pot.

Two polylines are produced, both single valued in ``z``:

``outer``
    the outside of the pot, from the build plate up over the rim.
``inner``
    the cavity that gets subtracted, from the top of the floor up past the
    rim (it overshoots so the boolean opens the mouth of the pot).

Every segment is straight, so resampling a segment only ever adds points that
lie exactly on it -- important for the low-poly style, where extra rings must
not round off a facet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .params import ParameterError, PotParams

#: how far the cavity pokes out of the top of the pot before the boolean
_TOP_OVERSHOOT = 5.0


@dataclass
class Profiles:
    outer: list[tuple[float, float]]      # [(radius, z)] bottom -> top
    inner: list[tuple[float, float]]      # [(radius, z)] floor -> above rim
    rim_outer_radius: float               # widest point of the pot
    floor_top_z: float                    # top face of the solid floor
    cavity_floor_radius: float            # radius of the flat floor inside
    decoration_freeze_z: float            # ribs / facets stop evolving above this
    notes: list[str] = field(default_factory=list)


def wall_radius(p: PotParams, z: float) -> float:
    """Nominal outside radius of the *wall* (rim and ribs excluded) at height z."""
    u = min(max(z / p.height, 0.0), 1.0)
    r = p.bottom_radius + (p.top_radius - p.bottom_radius) * u
    if p.pot_style == "classic_tapered" and p.belly:
        # a gentle outward bow: zero at both ends, maximum in the middle
        r += p.belly * p.top_radius * math.sin(math.pi * u)
    return r


def wall_slope(p: PotParams, z: float) -> float:
    """dr/dz of the wall, by central difference."""
    h = min(0.5, p.height * 1e-3)
    lo, hi = max(0.0, z - h), min(p.height, z + h)
    if hi <= lo:
        return 0.0
    return (wall_radius(p, hi) - wall_radius(p, lo)) / (hi - lo)


def _solve_chamfer_start(p: PotParams, rim_radius: float, rim_bottom_z: float) -> float:
    """Height where the rim's underside chamfer leaves the wall.

    Found by bisection so the chamfer hits ``rim_underside_angle`` exactly,
    whatever the wall is doing underneath it (taper, belly, ...).
    """
    target = math.radians(p.rim_underside_angle)

    def angle_at(z: float) -> float:
        run = rim_radius - wall_radius(p, z)
        rise = rim_bottom_z - z
        if run <= 1e-9:
            return math.pi / 2
        return math.atan2(rise, run)

    lo, hi = 0.0, rim_bottom_z - 1e-6      # angle grows as the start drops
    if angle_at(hi) >= target:             # already steep enough: keep it short
        return hi
    if angle_at(lo) <= target:             # cannot reach the angle at all
        return lo
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if angle_at(mid) > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def build_profiles(p: PotParams) -> Profiles:
    """Turn the parameters into the outer and inner lathe polylines."""
    notes: list[str] = []
    outer: list[tuple[float, float]] = [(p.bottom_radius, 0.0)]
    freeze_z = float("inf")

    # ---------------- outer wall + rim --------------------------------
    if p.add_top_rim and p.rim_width > 0:
        rim_bottom_z = max(0.0, p.height - p.rim_height)
        rim_radius = wall_radius(p, p.height) + p.rim_width
        z_chamfer = _solve_chamfer_start(p, rim_radius, rim_bottom_z)

        # wall up to where the chamfer starts
        outer.append((wall_radius(p, z_chamfer), z_chamfer))
        # 45+ degree underside so the rim needs no support
        outer.append((rim_radius, rim_bottom_z))
        # straight collar
        outer.append((rim_radius, p.height))
        widest = rim_radius
        freeze_z = z_chamfer
        achieved = math.degrees(
            math.atan2(rim_bottom_z - z_chamfer, rim_radius - wall_radius(p, z_chamfer))
        )
        if achieved + 1e-6 < p.rim_underside_angle:
            notes.append(
                f"rim underside came out at {achieved:.1f} deg (asked for "
                f"{p.rim_underside_angle:.0f} deg) - the pot is too short for that rim"
            )
    else:
        outer.append((wall_radius(p, p.height), p.height))
        widest = wall_radius(p, p.height)

    # ---------------- inner cavity ------------------------------------
    section_factor = 1.0
    if p.pot_style in ("hexagonal", "low_poly_faceted"):
        section_factor = 1.0 / math.cos(math.pi / p.sides)

    def cavity_radius(z: float) -> float:
        """Wall radius pulled in by a true perpendicular wall thickness."""
        slope = wall_slope(p, z)
        horiz = p.wall_thickness * math.sqrt(1.0 + slope * slope) * section_factor
        return wall_radius(p, z) - horiz

    floor_z = p.base_thickness
    r_floor_wall = cavity_radius(floor_z)
    if r_floor_wall <= 1.0:
        raise ParameterError(
            "the walls meet before the floor does - increase the diameters or "
            "reduce wall_thickness"
        )

    # 45 degree fillet where the cavity meets the floor: strong, and printable
    chamfer = min(p.inner_base_chamfer, r_floor_wall * 0.5, (p.height - floor_z) * 0.4)
    if chamfer < 0:
        chamfer = 0.0

    inner: list[tuple[float, float]] = []
    if chamfer > 0:
        inner.append((r_floor_wall - chamfer, floor_z))
        inner.append((cavity_radius(floor_z + chamfer), floor_z + chamfer))
    else:
        inner.append((r_floor_wall, floor_z))

    if p.jar_greenhouse:
        from .jar import check_jar_fit, neck_rings
        # polygonal pots: the round jar seat must fit inside the FLATS
        fmin = math.cos(math.pi / p.sides) if p.sides > 1 else 1.0
        check_jar_fit(p, cavity_radius(p.height) * fmin)
        tail = neck_rings(p, cavity_radius, p.height, _TOP_OVERSHOOT)
        inner = [ring for ring in inner if ring[1] < tail[0][1] - 1e-6] + tail
    else:
        inner.append((cavity_radius(p.height), p.height))
        inner.append((cavity_radius(p.height), p.height + _TOP_OVERSHOOT))

    # keep both polylines strictly increasing in z (they are functions of z)
    for name, poly in (("outer", outer), ("inner", inner)):
        for (r0, z0), (r1, z1) in zip(poly, poly[1:]):
            if z1 <= z0:
                raise ParameterError(f"{name} profile is not monotonic in z near z={z0:.2f}")
            if min(r0, r1) <= 0:
                raise ParameterError(f"{name} profile collapses to zero radius at z={z0:.2f}")

    return Profiles(
        outer=outer,
        inner=inner,
        rim_outer_radius=widest,
        floor_top_z=floor_z,
        cavity_floor_radius=max(r_floor_wall - chamfer, 0.1),
        decoration_freeze_z=freeze_z,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# resampling
# ---------------------------------------------------------------------------
def resample(
    poly: list[tuple[float, float]],
    step: float,
    extra_heights: list[float] | None = None,
    smooth: bool = True,
) -> list[tuple[float, float]]:
    """Add rings along a polyline.

    Points are always interpolated *on* the original segments, so the
    silhouette never changes shape.  ``extra_heights`` forces a ring at a
    given z (used for the low-poly band boundaries); ``smooth=False`` skips
    the regular subdivision and keeps only the corners plus those extras.
    """
    extra = sorted(extra_heights or [])
    out: list[tuple[float, float]] = []

    for (r0, z0), (r1, z1) in zip(poly, poly[1:]):
        cuts = [0.0]
        if smooth and step > 0:
            span = math.hypot(r1 - r0, z1 - z0)
            n = max(1, int(math.ceil(span / step)))
            cuts += [k / n for k in range(1, n)]
        cuts += [(e - z0) / (z1 - z0) for e in extra if z0 < e < z1]
        cuts = sorted(set(round(c, 9) for c in cuts if 0.0 <= c < 1.0))
        for t in cuts:
            out.append((r0 + (r1 - r0) * t, z0 + (z1 - z0) * t))
    out.append(poly[-1])
    return out
