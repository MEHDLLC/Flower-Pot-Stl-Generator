"""Parameter model for the flower pot generator.

Everything the generator can do is driven by a single :class:`PotParams`
dataclass.  Each field carries a comment describing what it does, what the
sensible range is, and which styles it affects.

All dimensions are in **millimetres** and all angles in **degrees** --
the same units a slicer expects from an STL.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, fields, replace
from typing import Any

# ----------------------------------------------------------------------------
# Style catalogue
# ----------------------------------------------------------------------------
#: The four selectable outer-surface treatments.  ``pot_style`` must be one of
#: these keys; the value is the human readable blurb used by ``--list-styles``.
STYLES: dict[str, str] = {
    "classic_tapered": "Smooth traditional nursery / terracotta pot with a gently curved wall.",
    "low_poly_faceted": "Geometric crystal look - stacked bands of polygonal facets, rotated band to band.",
    "ribbed_spiral": "Fluted vertical ribs that can be twisted into a spiral.",
    "hexagonal": "Modern six-sided prism with crisp vertical corners.",
}

#: Drainage layouts understood by the generator.
DRAINAGE_PATTERNS = ("center", "ring", "grid", "none")

#: Relief textures that can be pressed into the outside of the wall.  They
#: are independent of ``pot_style`` (except low_poly_faceted, whose sparse
#: mesh cannot carry one).  Implementations live in :mod:`flowerpot.textures`.
TEXTURES = ("none", "herringbone", "honeycomb", "diamonds", "waves")


class ParameterError(ValueError):
    """Raised when a combination of parameters cannot produce a valid solid."""


@dataclass
class PotParams:
    """Every knob of the generator, with print-ready defaults.

    The defaults describe a ~145 mm tall, 150 mm wide tapered pot with a
    rim, five ring drainage holes and 3 mm walls -- a good general purpose
    houseplant pot that prints without supports on any FDM machine.
    """

    # ------------------------------------------------------------------
    # 1. Overall dimensions
    # ------------------------------------------------------------------
    height: float = 145.0            # total pot height, build plate to rim
    top_diameter: float = 150.0      # outside diameter at the top of the wall
    #                                  (measured *under* the rim - the rim adds
    #                                   rim_width per side on top of this)
    bottom_diameter: float = 105.0   # outside diameter where the pot meets the plate.
    #                                  Keep it >= 0.6 * top_diameter for stability;
    #                                  making it *larger* than top_diameter is allowed
    #                                  and prints even better (no outward lean).
    wall_thickness: float = 3.0      # side wall thickness. 2.4-3.2 mm suits 0.4 mm nozzles.
    base_thickness: float = 5.0      # solid floor thickness under the soil.
    #                                  Must exceed wall_thickness so drainage holes
    #                                  do not undercut the wall.

    # ------------------------------------------------------------------
    # 2. Drainage
    # ------------------------------------------------------------------
    drainage_pattern: str = "ring"   # "center" | "ring" | "grid" | "none"
    drainage_hole_radius: float = 6.0    # radius (not diameter) of each hole
    num_drainage_holes: int = 5          # used by "ring" and "grid"
    drainage_ring_fraction: float = 0.55  # ring radius as a fraction of the usable
    #                                       floor radius (0.3 lazy centre, 0.8 near wall)

    # ------------------------------------------------------------------
    # 3. Rim
    # ------------------------------------------------------------------
    add_top_rim: bool = True         # collar around the mouth of the pot
    rim_width: float = 6.0           # how far the rim projects past the wall, per side
    rim_height: float = 10.0         # vertical height of the straight part of the rim
    rim_underside_angle: float = 48.0  # angle of the chamfer under the rim, measured
    #                                    from horizontal.  Must stay above
    #                                    overhang_limit_deg or the rim needs supports.

    # ------------------------------------------------------------------
    # 4. Style specific shaping
    # ------------------------------------------------------------------
    pot_style: str = "classic_tapered"  # see STYLES

    belly: float = 0.04              # classic_tapered only: outward bow of the wall as a
    #                                  fraction of the top radius.  0 = dead straight cone,
    #                                  0.08 = plump urn.
    facet_count: int = 9             # low_poly_faceted: sides per band (5-16 look good)
    facet_bands: int = 6             # low_poly_faceted: horizontal bands stacked up the pot
    facet_rotate: bool = True        # low_poly_faceted: rotate every other band by half a
    #                                  facet so the facets read as triangles
    rib_count: int = 24              # ribbed_spiral: number of flutes around the pot
    rib_depth: float = 3.0           # ribbed_spiral: how far the ribs stand proud, in mm.
    #                                  Ribs are added *outside* the nominal wall, so the
    #                                  wall never gets thinner than wall_thickness.
    rib_twist_degrees: float = 45.0  # ribbed_spiral: total twist from base to rim.
    #                                  0 = straight flutes, 45 = gentle spiral.
    hex_sides: int = 6               # hexagonal: 6 is a hexagon, 8 an octagon, etc.
    hex_corner_round: float = 2.0    # hexagonal / low_poly: corner rounding in mm.
    #                                  Small values keep crisp edges but avoid a knife edge.

    # ------------------------------------------------------------------
    # 4b. Surface texture (works on top of any style except low_poly)
    # ------------------------------------------------------------------
    surface_texture: str = "none"    # "none" | "herringbone" | "honeycomb"
    #                                  | "diamonds" | "waves"
    texture_depth: float = 1.0       # how far the relief stands proud, in mm.
    #                                  1.0 reads clearly; past ~2 the grooves
    #                                  start flirting with the overhang limit.
    texture_cell: float = 16.0       # size of one pattern cell, in mm.

    # ------------------------------------------------------------------
    # 4c. Color (carried in the .3mf and the preview image; STL has none)
    # ------------------------------------------------------------------
    color: str = "terracotta"        # palette name or hex like "#B06040"
    accent_color: str = ""           # optional second color for the rim.
    #                                  Empty = single color everywhere.

    # ------------------------------------------------------------------
    # 5. Print optimisation
    # ------------------------------------------------------------------
    overhang_limit_deg: float = 45.0   # steepest unsupported overhang allowed, measured
    #                                    from vertical.  Used to build the rim chamfer and
    #                                    to audit the finished mesh.
    inner_base_chamfer: float = 4.0    # 45 degree fillet where the inside wall meets the
    #                                    floor.  Adds strength and removes a stress riser.
    base_flat: bool = True             # keep the footprint perfectly flat for bed adhesion.
    #                                    Setting False lets the style texture wrap the base.

    # ------------------------------------------------------------------
    # 6. Matching drip saucer (exported as a second STL)
    # ------------------------------------------------------------------
    generate_saucer: bool = False
    saucer_clearance: float = 4.0    # radial gap between the pot foot and the saucer wall
    saucer_height: float = 20.0      # overall saucer height
    saucer_wall: float = 3.0         # saucer wall thickness
    saucer_base: float = 4.0         # saucer floor thickness

    # ------------------------------------------------------------------
    # 7. Mesh resolution
    # ------------------------------------------------------------------
    segments: int = 192              # samples around the circumference.  128 is fast,
    #                                  256 is glassy smooth, 64 is deliberately chunky.
    vertical_step: float = 1.5       # max distance between profile rings, in mm.

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------
    @property
    def top_radius(self) -> float:
        return self.top_diameter / 2.0

    @property
    def bottom_radius(self) -> float:
        return self.bottom_diameter / 2.0

    @property
    def sides(self) -> int:
        """Number of straight sides for the polygonal styles (1 == round)."""
        if self.pot_style == "hexagonal":
            return max(3, int(self.hex_sides))
        if self.pot_style == "low_poly_faceted":
            return max(3, int(self.facet_count))
        return 1

    def wall_lean_deg(self) -> float:
        """Outward lean of the side wall from vertical, in degrees.

        Positive means the pot gets wider going up, which is the direction
        that can overhang.  Anything under ``overhang_limit_deg`` prints
        without support.
        """
        return math.degrees(
            math.atan2(self.top_radius - self.bottom_radius, self.height)
        )

    # ------------------------------------------------------------------
    # Validation & serialisation
    # ------------------------------------------------------------------
    def validate(self) -> list[str]:
        """Raise on impossible geometry, return a list of soft warnings."""
        warn: list[str] = []

        if self.pot_style not in STYLES:
            raise ParameterError(
                f"unknown pot_style {self.pot_style!r}; choose from {sorted(STYLES)}"
            )
        if self.drainage_pattern not in DRAINAGE_PATTERNS:
            raise ParameterError(
                f"unknown drainage_pattern {self.drainage_pattern!r}; "
                f"choose from {list(DRAINAGE_PATTERNS)}"
            )
        if self.surface_texture not in TEXTURES:
            raise ParameterError(
                f"unknown surface_texture {self.surface_texture!r}; "
                f"choose from {list(TEXTURES)}"
            )
        if self.surface_texture != "none":
            if self.texture_depth < 0 or self.texture_cell <= 0:
                raise ParameterError("texture_depth/texture_cell must be positive")
        from .colors import parse_color
        try:
            parse_color(self.color)
            if self.accent_color:
                parse_color(self.accent_color)
        except ValueError as exc:
            raise ParameterError(str(exc)) from None
        for name in ("height", "top_diameter", "bottom_diameter", "wall_thickness",
                     "base_thickness", "segments", "vertical_step"):
            if getattr(self, name) <= 0:
                raise ParameterError(f"{name} must be greater than zero")

        smallest_radius = min(self.top_radius, self.bottom_radius)
        if self.wall_thickness >= smallest_radius * 0.8:
            raise ParameterError(
                "wall_thickness leaves no cavity: reduce it or widen the pot"
            )
        if self.base_thickness >= self.height * 0.8:
            raise ParameterError("base_thickness leaves no room for soil")
        if self.segments < 12:
            raise ParameterError("segments must be at least 12")

        # --- soft warnings ------------------------------------------------
        lean = self.wall_lean_deg()
        if lean > self.overhang_limit_deg:
            warn.append(
                f"side wall leans {lean:.1f} deg from vertical, past the "
                f"{self.overhang_limit_deg:.0f} deg limit - raise bottom_diameter "
                f"or the pot will need supports"
            )
        # rim_underside_angle is measured from horizontal, overhang_limit_deg
        # from vertical, so the chamfer has to be at least 90 - limit.
        min_rim_angle = 90.0 - self.overhang_limit_deg
        if self.add_top_rim and self.rim_underside_angle < min_rim_angle:
            warn.append(
                f"rim_underside_angle {self.rim_underside_angle:.0f} deg (from horizontal) "
                f"is shallower than the {min_rim_angle:.0f} deg needed to stay inside a "
                f"{self.overhang_limit_deg:.0f} deg overhang limit"
            )
        if self.base_thickness < self.wall_thickness:
            warn.append("base_thickness below wall_thickness: the floor is the weak point")
        if self.wall_thickness < 1.6:
            warn.append("wall_thickness under 1.6 mm is fragile for a soil filled pot")
        if self.drainage_pattern == "none":
            warn.append("no drainage holes: the pot will hold water (fine as a cachepot)")
        if self.pot_style == "ribbed_spiral":
            # A rib is a helix; its flank angle depends on how fast it twists.
            circ = math.pi * self.top_diameter
            travel = circ * (abs(self.rib_twist_degrees) / 360.0)
            helix = math.degrees(math.atan2(travel, self.height))
            if helix > self.overhang_limit_deg:
                warn.append(
                    f"rib helix angle {helix:.1f} deg exceeds the overhang limit - "
                    f"reduce rib_twist_degrees"
                )
        if self.surface_texture != "none":
            if self.pot_style == "low_poly_faceted":
                warn.append(
                    "surface_texture is ignored on low_poly_faceted (its sparse "
                    "mesh cannot carry a relief pattern)"
                )
            elif self.pot_style == "ribbed_spiral" and abs(self.rib_twist_degrees) > 25:
                warn.append(
                    "a texture on top of twisted ribs stacks their slopes and can "
                    "pass the overhang limit - reduce rib_twist_degrees (<= 25) or "
                    "texture_depth if the audit fails"
                )
            elif self.texture_depth / self.texture_cell > 0.12:
                warn.append(
                    f"texture_depth {self.texture_depth} is aggressive for "
                    f"{self.texture_cell} mm cells - the groove walls may pass "
                    f"the overhang limit"
                )
        if self.accent_color and not self.add_top_rim:
            warn.append("accent_color colors the rim, but add_top_rim is off")
        return warn

    # -- dict / json ---------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def field_names(cls) -> list[str]:
        return [f.name for f in fields(cls)]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PotParams":
        known = set(cls.field_names())
        unknown = set(data) - known
        if unknown:
            raise ParameterError(f"unknown parameter(s): {sorted(unknown)}")
        return cls(**data)

    def with_(self, **overrides: Any) -> "PotParams":
        """Return a copy with some fields replaced (handy for presets)."""
        return replace(self, **overrides)
