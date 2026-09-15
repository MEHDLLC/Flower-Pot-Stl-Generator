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

    # -- vase silhouette ------------------------------------------------------
    vase_profile="none",      # "classic"|"bud"|"gourd"|"bottle"|"cone"|"wave":
    #                           curvy vase walls; top_diameter = widest point
    stem=False,               # hollow leafy stem rising from the floor - put
    #                           a real flower in it (leaf tilt capped at 30);
    #                           water holes spiral up the submerged section
    stem_mount="printed",     # "printed" fuses the stem to the floor;
    #                           "screw" adds a threaded socket and writes the
    #                           stem as a separate <name>_stem piece - unscrew
    #                           to clean, or print a taller stem than the pot
    stem_length=130.0,
    stem_bore=9.0,
    stem_split="auto",        # a screw-in stem taller than the printer is
    #                           written as <name>_stem_part1/2..., joined by
    #                           threaded nodes; "never" keeps one tall piece,
    #                           "always" forces a node (handy for shipping)
    stem_curve=6.0,           # mm of gentle sway above the rim; 0 = straight
    num_branches=2,           # side stems curving off the main one, each with
    #                           its own open tip joined to the water column
    branch_length=70.0,       # branch climb; auto-shortened to fit the stem
    num_leaves=5,
    leaf_length=55.0,
    leaf_angle=25.0,          # fused leaves cap at 30; insert leaves at 60
    leaf_mount="printed",     # "insert" cuts slots in the stem and writes a
    #                           flat <name>_leaves plate - print it in a 2nd
    #                           color/filament and push each tab into a slot
    #                           (flip a leaf in its slot to make it droop)
    soil_cap=False,           # removable raked-"soil" lid seated below the
    #                           rim, centre hole for the stem plus two finger
    #                           holes - the potted-plant look, written as
    #                           <name>_soil_cap

    # -- bouquet planter (the mouth becomes a cluster of blooms) -------------
    bouquet=False,            # gather the pot to a wide mouth and ring it
    #                           with hollow blooms; the mouth itself flares
    #                           into a flower and is what you plant in, and
    #                           each ring bloom is a pocket that drains into
    #                           the body.  Defaults to a trumpet silhouette.
    bouquet_flower="tulip",   # "tulip" (pointed petals) | "rose" (spiralled)
    bouquet_count=5,          # blooms in the ring, 3-8
    bouquet_head_diameter=0.0,  # 0 = sized from the pot
    bouquet_tilt=15.0,        # how far the ring leans out; 18 is the cap

    # -- uniform scale --------------------------------------------------------
    scale=1.0,                # resize the pot's proportions; wall_thickness and
    #                           base_thickness stay exactly as set below

    # -- drainage -----------------------------------------------------------
    drainage_pattern="ring",  # "center" | "ring" | "grid" | "none"
    drainage_hole_radius=6.0, # radius, not diameter
    num_drainage_holes=5,     # used by "ring" and "grid"
    drainage_ring_fraction=0.55,   # 0.3 = huddled in the middle, 0.8 = near the wall
    num_side_holes=0,         # grow-pot side ports through the wall above the
    #                           floor; combine freely with the bottom patterns
    side_hole_radius=4.0,

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

    # -- self-watering pair (a planter and the reservoir it drops into) ------
    replica="none",           # "kyra" the 6 in. planter with the attached
    #                           saucer, "hdx" the reservoir it sits in,
    #                           "set" both plus the wick cup between them
    replica_pot_top=152.4,    # 6.00 in. mouth
    replica_pot_base=119.38,  # 4.70 in. saucer
    replica_pot_height=139.95,  # 5.51 in. tall
    replica_standoff=25.0,    # mm the pot is held above the water.  Flush
    #                           rims, a real reservoir and the shop bucket's
    #                           depth are three things you can have two of;
    #                           0 takes the bucket's depth and no water
    replica_plumbing=True,    # ribs, overflow, fill notch and wick cup

    # -- hanging cradle (three flat parts that hang a pot) -------------------
    hanger="none",            # "set" writes all three; "base", "arm" or
    #                           "top" writes one.  EVERY part prints FLAT,
    #                           as modelled - a load-bearing part printed
    #                           standing up is pulled apart across its layers
    hanger_pot_size="custom", # or "3in".."12in"
    hanger_pot_top=152.4,     # the pot, across the top
    hanger_pot_base=114.3,    # ... across the base
    hanger_pot_height=144.8,  # ... and standing
    hanger_arms=3,            # 3-5; three hangs level on its own
    hanger_drop=240.0,        # base ring to top ring
    hanger_load=5.0,          # kg: pot, soil and water at their heaviest.
    #                           One arm is assumed slack.
    hanger_top="hole",        # "hole" | "slot" (webbing) | "ring" (rope)
    hanger_clearance=8.0,     # how far the arms run off the pot

    # -- nursery sleeve (a cover for the pot the plant came in) --------------
    sleeve=False,             # the nursery pot drops in, pot and all.  A
    #                           sleeve IS a pot: pot_style, surface_texture
    #                           and the rim all work on it as usual.
    #                           vase_profile does not - see the README.
    sleeve_pot_size="custom", # or "3in".."12in", which fills in all three
    #                           measurements below with typical ones
    sleeve_pot_top=152.4,     # the nursery pot, across the top
    sleeve_pot_base=114.3,    # ... across the base
    sleeve_pot_height=144.8,  # ... and standing
    sleeve_fit=1.5,           # radial slack round the nursery pot
    sleeve_reveal=0.0,        # mm its rim stands proud of the sleeve's;
    #                           negative hides it below
    sleeve_well=14.0,         # drip well under the pot.  No drain, so it is
    #                           also the most the sleeve can hold.
    sleeve_base=0.0,          # the sleeve's own bottom diameter, 0 = derived

    # -- under the pot (tray, risers, drainage mesh) -------------------------
    underpot="none",          # "set" writes all three; "tray", "riser" or
    #                           "mesh" writes one.  For a pot you did NOT
    #                           print: the only measurement needed is the
    #                           diameter of its base.
    under_pot_size="custom",  # or "3in".."12in" - a NOMINAL nursery size,
    #                           which is the pot's width across the top
    under_pot_base=110.0,     # the pot's base diameter, measured
    under_clearance=3.0,      # radial gap, pot to tray wall
    under_waffle=6.0,         # rib height in the tray - also how much water
    #                           it holds before the pot is standing in it
    under_rim=9.0,            # tray wall above the rib tops
    under_riser_height=18.0,  # how far a foot lifts the pot
    under_feet=3,             # 3 cannot rock; 4 spreads the load
    under_mesh_diameter=0.0,  # 0 = derived from the base
    under_mesh_open=0.35,     # fraction of the disc that is hole
    under_mesh_legs=True,     # nubs so it cannot seal the drain holes

    # -- moss pole (a hollow column you pack with sphagnum) ------------------
    moss_pole="none",         # "set" writes one segment, the base and the
    #                           cap.  The segments are identical - print
    #                           pole_segments copies of the one file.
    pole_diameter=55.0,       # ACROSS THE FLATS, on any of the shapes
    pole_segment_height=150.0,  # one segment, joint included
    pole_segments=3,          # how many you mean to stack
    pole_shape="square",      # "square"|"hex"|"round" - a polygon keys the
    #                           joint and gives you flats to tie a stem to
    pole_pattern="lattice",   # "lattice"|"slots"|"solid"
    pole_open=0.68,           # how much of the wall is opening
    pole_rows=0,              # rows of openings per segment; 0 = auto
    pole_barbs="inside",      # "none"|"inside"|"outside"|"both" - little
    #                           shelves with ramped undersides.  Inside they
    #                           stop the packed column settling; outside they
    #                           hold a sheet of moss wrapped round the pole.
    pole_reservoir=0.0,       # mm of water the base holds under the column.
    #                           A sump, not a tank: it catches what you pour
    #                           through the cap, and an overflow sets the level
    pole_wick=False,          # eyes in the cap and a post in the base, so a
    #                           string can run down the column and back up

    # -- dish and keel (a pot that sits in a dish and drinks out of it) ------
    cradle="none",            # "set" writes both parts, "pot" or "dish" one
    #                           of them.  The pot's bottom is a cone - a keel
    #                           - hanging into the dish's water, slotted so
    #                           the soil can wick it back up
    cradle_diameter=120.0,    # outside diameter at the joint
    cradle_height=108.0,      # assembled height, plate to the pot's lip
    cradle_dish_height=44.0,  # the dish's share of it
    cradle_keel=26.0,         # how far the keel hangs below the joint
    cradle_bowl="round",      # "round" | "cone" | "tub" - the dish's
    #                           silhouette, and the water dial with it:
    #                           tub holds the most, cone the least
    cradle_flare=1.5,         # how much wider the mouth is than the joint
    cradle_windows=1,         # notches in the dish's rim to pour through;
    #                           they are the overflow as well as the inlet
    cradle_drains=8,          # wicking slots up the keel; 0 = a cachepot
    cradle_lip=True,          # a rolled lip round the pot's mouth

    # -- yard art: a plant with a face and an opinion ------------------------
    yard_plant="none",        # "sunflower" | "daisy" | "cactus".  The
    #                           flowers come apart into <name>_body
    #                           (standing), <name>_head (petals, flat) and
    #                           <name>_face (the middle, flat) so a
    #                           single-colour printer makes a 3-colour toy
    yard_height=200.0,        # overall height, mount included
    yard_head_diameter=0.0,   # 0 = sized from the room above the mount
    yard_face="angry",        # "angry"|"smug"|"grin"|"sideeye"|"none"
    yard_left_hand="bird",    # "bird"|"fist"|"thumbs"|"peace"|"horns"
    yard_right_hand="bird",   # |"wave"|"shrug"|"none" - mix them

    # -- trailer hitch mount (snaps over a trailer ball) ---------------------
    hitch_mount="none",       # "cover" = one piece; "screw" = a gripping
    #                           collar plus a screw-on cap, so one collar
    #                           per ball size carries anything.
    #                           TAKE IT OFF BEFORE TOWING.
    hitch_ball="2",           # "1-7/8" | "2" | "2-5/16" | "3", or mm
    hitch_fingers=5,          # slices the socket is cut into; odd is better
    hitch_grip=1.1,           # mm the mouth is narrower than the ball - the
    #                           retention, and how far a finger has to bend

    # -- hydroponic tower (writes <name>_segment, _cup and _cap) -------------
    hydro_tower=False,        # stackable column segments with angled ports
    tower_diameter=110.0,
    segment_height=160.0,
    ports_per_segment=3,
    port_bore=50.0,           # net-cup socket diameter
    port_angle=48.0,          # cup tilt; below 46 would need supports

    # -- modular garden kits (dovetail-connected sets) ------------------------
    modular_kit="none",       # "seed_cubes" | "flower" | "stack"
    cube_size=55.0,
    cube_depth=60.0,
    flower_diameter=140.0,
    stack_pod_diameter=70.0,

    # -- matching drip saucer ----------------------------------------------
    generate_saucer=False,    # True also writes <name>_saucer.stl
    saucer_clearance=4.0,     # gap around the pot foot

    # -- mason-jar greenhouse seat (classic pot / SW inner / insert collar) --
    jar_greenhouse=False,     # seat an upside-down canning jar over the plant
    jar_mouth_od=86.0,        # ~86 wide-mouth, ~70 regular-mouth jars

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
