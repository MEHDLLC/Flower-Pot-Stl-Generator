#!/usr/bin/env python3
"""
=============================================================================
 FLOWER POT STL GENERATOR  --  edit the values below, then run:

     python generate_pot.py

 Every pot is exported to ./output as a watertight, support-free STL and is
 automatically audited for 3D printability before it is written.

 Prefer the command line?  Every value below is also a flag:

     python -m flowerpot --pot-style hexagonal --height 120 --out output/
     python -m flowerpot --all --generate-saucer      # one pot per style
     python -m flowerpot --list-styles

 All dimensions are in MILLIMETRES.  Angles are in DEGREES.
=============================================================================
"""

from pathlib import Path

from flowerpot.export import export_pot
from flowerpot.params import PotParams

# ---------------------------------------------------------------------------
# 1.  PICK A STYLE
# ---------------------------------------------------------------------------
#   "classic_tapered"   smooth traditional nursery / terracotta pot
#   "low_poly_faceted"  geometric crystal, stacked bands of facets
#   "ribbed_spiral"     vertical flutes, optionally twisted into a spiral
#   "hexagonal"         modern six-sided prism
POT_STYLE = "classic_tapered"

# ---------------------------------------------------------------------------
# 2.  DIMENSIONS
# ---------------------------------------------------------------------------
PARAMS = dict(
    pot_style=POT_STYLE,

    # -- overall size -------------------------------------------------------
    height=145.0,             # plate to rim
    top_diameter=150.0,       # outside width at the top of the wall (under the rim)
    bottom_diameter=105.0,    # outside width at the plate. Bigger = more stable and
    #                           less wall lean; must stay under ~55 deg of taper.
    wall_thickness=3.0,       # 2.4-3.2 mm is the sweet spot for a 0.4 mm nozzle
    base_thickness=5.0,       # floor under the soil; keep it above wall_thickness

    # -- drainage -----------------------------------------------------------
    drainage_pattern="ring",  # "center" | "ring" | "grid" | "none"
    drainage_hole_radius=6.0, # radius, not diameter
    num_drainage_holes=5,     # used by "ring" and "grid"
    drainage_ring_fraction=0.55,   # 0.3 = huddled in the middle, 0.8 = near the wall

    # -- rim ----------------------------------------------------------------
    add_top_rim=True,
    rim_width=6.0,            # how far the rim sticks out, per side
    rim_height=10.0,          # height of the straight collar
    rim_underside_angle=48.0, # chamfer under the rim, from HORIZONTAL.
    #                           Keep it above 45 so the rim needs no supports.

    # -- style specific -----------------------------------------------------
    belly=0.04,               # classic_tapered: 0 = straight cone, 0.10 = plump urn
    facet_count=9,            # low_poly_faceted: sides per band
    facet_bands=6,            # low_poly_faceted: bands stacked up the pot
    rib_count=24,             # ribbed_spiral: flutes around the pot
    rib_depth=3.0,            # ribbed_spiral: how far they stand proud
    rib_twist_degrees=45.0,   # ribbed_spiral: 0 = straight, 45 = gentle spiral
    hex_sides=6,              # hexagonal: 6 = hexagon, 8 = octagon
    hex_corner_round=2.0,     # hexagonal: corner rounding

    # -- surface texture (any style except low_poly_faceted) -----------------
    surface_texture="none",   # "none" | "herringbone" | "honeycomb"
    #                           | "diamonds" | "waves"
    texture_depth=1.0,        # relief height in mm; ~2 starts risking overhangs
    texture_cell=16.0,        # pattern cell size in mm

    # -- color (rides in the .3mf and the preview; STL is colorless) ---------
    color="terracotta",       # palette name (see flowerpot/colors.py) or "#B06040"
    accent_color="",          # optional second color for the rim
    printer="creality-k1-max", # machine profile embedded in the .3mf; also
    #                            "creality-k1", "creality-ender3-v3-ke", or
    #                            "none" for a plain geometry-only 3MF

    # -- hydroponic tower (writes <name>_segment, _cup and _cap) -------------
    hydro_tower=False,        # stackable column segments with angled ports
    tower_diameter=110.0,
    segment_height=160.0,
    ports_per_segment=3,
    port_bore=50.0,           # net-cup socket diameter
    port_angle=48.0,          # cup tilt; below 46 would need supports

    # -- matching drip saucer ----------------------------------------------
    generate_saucer=False,    # True also writes <name>_saucer.stl
    saucer_clearance=4.0,     # gap around the pot foot

    # -- self-watering set (writes <name>_outer.* and <name>_inner.*) --------
    self_watering=False,      # outer reservoir pot with refill tube + funnel,
    #                           inner liner standing on a wick cup, rims flush
    reservoir_height=35.0,    # water depth the outer pot holds
    refill_tube_bore=16.0,    # inner diameter of the refill tube
    wick_hole_radius=4.0,     # rope holes around the inner pot's cup
    num_wick_holes=3,

    # -- mesh quality -------------------------------------------------------
    segments=192,             # around the circumference: 128 fast, 256 glassy
    vertical_step=1.5,        # mm between rings up the wall
)

OUTPUT_DIR = Path("output")
FORMATS = ("stl",)            # any of "stl", "3mf" - 3mf carries the color
PREVIEW = False               # True also renders <name>.png (needs matplotlib)
#                               and embeds it in the 3mf as its thumbnail

# ---------------------------------------------------------------------------
# 3.  WANT A WHOLE SET?  Add entries here; each one overrides PARAMS.
#     Leave the list empty to just build PARAMS on its own.
# ---------------------------------------------------------------------------
VARIANTS: list[dict] = [
    # dict(pot_style="hexagonal",        name="hex_medium"),
    # dict(pot_style="ribbed_spiral",    name="spiral_tall", height=200, rib_twist_degrees=60),
    # dict(pot_style="low_poly_faceted", name="crystal_seedling", height=80,
    #      top_diameter=90, bottom_diameter=70, drainage_pattern="center"),
]


# ---------------------------------------------------------------------------
def make(overrides: dict) -> None:
    """Build, audit and export one pot (and its saucer, if enabled)."""
    settings = dict(PARAMS)
    settings.update(overrides)
    name = settings.pop("name", settings["pot_style"])
    params = PotParams(**settings)
    export_pot(params, name, OUTPUT_DIR, FORMATS, preview=PREVIEW, force=True)


if __name__ == "__main__":
    for variant in VARIANTS or [{}]:
        make(variant)
