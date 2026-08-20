"""Mason-jar greenhouse seat: an upside-down canning jar becomes a cloche.

Enabled with ``jar_greenhouse``, the pot's mouth gains a **jar seat**: the
interior necks inward (at no more than 42 degrees from vertical, so it
still prints support-free) into a shelf carrying a circular groove.  The
inverted jar's lip drops into the groove, an upstand ring keeps it
centred, and the plant grows through the shaft in the middle.  Four
diamond vent notches under the lip keep the greenhouse breathing.

Works on the classic pot and on the self-watering set's inner liner.  The
reservoir insert instead gets a standalone **jar collar ring** to set on
the soil surface, with the same groove and vents.

``jar_mouth_od`` is the jar's outside mouth diameter: ~86 mm for US
wide-mouth canning jars (the default), ~70 mm for regular-mouth.
"""

from __future__ import annotations

import math

import trimesh

from .params import ParameterError, PotParams

_GROOVE_HALF = 3.5      # groove half-width: jar lip ~3 mm + clearance
_UPSTAND = 3.0          # ring between the groove and the planting shaft
_SHELF_UNDER = 3.0      # shelf material under the groove floor
_NECK_SLOPE = 0.9       # max dr/dz of the neck = 42 deg from vertical


def jar_radii(p: PotParams) -> tuple[float, float, float]:
    """(planting shaft radius, groove inner radius, groove outer radius)."""
    r_gi = p.jar_mouth_od / 2.0 - _GROOVE_HALF
    r_go = p.jar_mouth_od / 2.0 + _GROOVE_HALF
    return r_gi - _UPSTAND, r_gi, r_go


def check_jar_fit(p: PotParams, mouth_radius: float) -> None:
    """Raise if the pot mouth cannot hold the seat for this jar."""
    _, _, r_go = jar_radii(p)
    if mouth_radius < r_go + 2.0:
        raise ParameterError(
            f"the pot mouth (r={mouth_radius:.0f} mm) is too narrow for a "
            f"{p.jar_mouth_od:.0f} mm jar seat - widen the pot or use a "
            f"regular-mouth jar (jar_mouth_od 70)"
        )


def neck_rings(p: PotParams, cavity_radius, top_z: float,
               overshoot: float) -> list[tuple[float, float]]:
    """Cavity rings for the seat: neck in, shaft up past the mouth.

    ``cavity_radius(z)`` is the pot's own cavity line; the neck leaves it
    at a slope no steeper than 42 degrees from vertical so its underside
    prints unsupported.
    """
    r_hole, _, _ = jar_radii(p)
    z_shaft = top_z - p.jar_seat_depth - _SHELF_UNDER
    z_neck = z_shaft
    for _ in range(8):                        # solve against the moving wall
        z_neck = z_shaft - max(cavity_radius(z_neck) - r_hole, 0.0) / _NECK_SLOPE
    if z_neck < top_z * 0.35:
        raise ParameterError(
            "the jar seat leaves no soil depth - make the pot taller or the "
            "jar smaller"
        )
    return [(cavity_radius(z_neck), z_neck), (r_hole, z_shaft),
            (r_hole, top_z + overshoot)]


def seat_cutters(p: PotParams, top_z: float,
                 vent_down: float = 2.6) -> list[trimesh.Trimesh]:
    """The groove ring (cut from the top - no ceilings) and the vents."""
    from .build import lathe
    from .profile import resample
    from .sections import make_section
    from .selfwatering import _diamond_port

    _, r_gi, r_go = jar_radii(p)
    z_floor = top_z - p.jar_seat_depth
    section = make_section(p.with_(pot_style="classic_tapered",
                                   surface_texture="none", belly=0.0))
    ring_outer = lathe(resample([(r_go, z_floor), (r_go, top_z + 2.0)], 2.0),
                       section, False)
    ring_inner = lathe(resample([(r_gi, z_floor - 1.0), (r_gi, top_z + 3.0)], 2.0),
                       section, False)
    groove = trimesh.boolean.difference([ring_outer, ring_inner],
                                        engine="manifold")

    cutters = [groove]
    r_hole, _, _ = jar_radii(p)
    for k in range(4):                        # vents: pointed roofs, no bridges.
        # each punches THROUGH the upstand into the planting shaft - stopping
        # inside the ring would leave a dead-end pocket and an airtight jar
        a = math.pi / 4.0 + k * math.pi / 2.0
        # the diamond's widest edge sits 0.4 below the groove floor: exactly
        # coplanar seams shed sliver faces that break the STL round-trip
        vent = _diamond_port(x0=r_hole - 2.0, x1=r_go + 2.0,
                             z_center=z_floor - 0.4,
                             half_w=3.0, up=5.4, down=vent_down)
        vent.apply_transform(
            trimesh.transformations.rotation_matrix(a, [0, 0, 1]))
        cutters.append(vent)
    return cutters


def build_jar_ring(p: PotParams) -> trimesh.Trimesh:
    """Standalone jar collar for the reservoir insert: set it on the soil."""
    from .build import _boolean, _finish, lathe
    from .profile import resample
    from .sections import make_section

    r_hole, _, r_go = jar_radii(p)
    h = p.jar_seat_depth + _SHELF_UNDER
    section = make_section(p.with_(pot_style="classic_tapered",
                                   surface_texture="none", belly=0.0))
    slab = lathe(resample([(r_go + 6.0, 0.0), (r_go + 6.0, h)], 2.0),
                 section, False)
    hole = lathe(resample([(r_hole, -1.0), (r_hole, h + 1.0)], 2.0),
                 section, False)
    # the collar is short: the vents punch clean through its underside
    # (a tip landing exactly on the bottom face is a pinch-point seam that
    # breaks the STL round-trip; and open bottoms vent better on soil)
    body = _boolean("difference",
                    [slab, hole] + seat_cutters(p, h, vent_down=6.0))
    return _finish(body, center=False)
