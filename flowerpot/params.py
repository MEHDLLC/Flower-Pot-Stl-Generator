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
    "square": "Four-sided box pot with rounded corners - the nursery classic.",
}

#: Drainage layouts understood by the generator.
DRAINAGE_PATTERNS = ("center", "ring", "grid", "none")

#: Vase silhouettes: named wall curves that replace the straight taper.
#: Implementations live in :mod:`flowerpot.profile`.
VASE_PROFILES = ("none", "classic", "bud", "gourd", "bottle", "cone",
                 "wave", "bouquet")

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
    # 1a. Vase silhouette
    # ------------------------------------------------------------------
    vase_profile: str = "none"       # replace the straight taper with a curvy
    #                                  vase wall: "classic" (amphora), "bud",
    #                                  "gourd", "bottle", "cone", "wave".
    #                                  Sized by height and top_diameter (the
    #                                  mouth); bottom_diameter and belly are
    #                                  ignored.  Composes with every style and
    #                                  texture.  Curves too steep for the
    #                                  overhang budget at your height are
    #                                  rejected with the height they need.

    # ------------------------------------------------------------------
    # 1b. Uniform scale
    # ------------------------------------------------------------------
    scale: float = 1.0               # resizes the pot's PROPORTIONS (height,
    #                                  diameters, rim, hole sizes, texture
    #                                  cells...) while wall_thickness,
    #                                  base_thickness and every print-fit
    #                                  clearance stay exactly as set - shrink
    #                                  a design without thinning its walls.

    # ------------------------------------------------------------------
    # 2. Drainage
    # ------------------------------------------------------------------
    drainage_pattern: str = "ring"   # "center" | "ring" | "grid" | "none"
    drainage_hole_radius: float = 6.0    # radius (not diameter) of each hole
    num_drainage_holes: int = 5          # used by "ring" and "grid"
    drainage_ring_fraction: float = 0.55  # ring radius as a fraction of the usable
    #                                       floor radius (0.3 lazy centre, 0.8 near wall)
    num_side_holes: int = 0          # grow-pot style drainage: diamond ports
    #                                  through the wall just above the floor.
    #                                  0 = none; combine freely with the
    #                                  bottom patterns above.
    side_hole_radius: float = 4.0    # half-width of each side port

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
    printer: str = "creality-k1-max" # machine profile embedded in the .3mf so
    #                                  Creality Print / Bambu Studio / OrcaSlicer
    #                                  (and Creality Cloud's "Print Settings"
    #                                  upload) recognise it as a print project.
    #                                  "none" = plain geometry-only 3MF.

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
    # 4d. Sculptural stem (the "planted flower" vase)
    # ------------------------------------------------------------------
    stem: bool = False               # a hollow stem rises from the pot floor
    #                                  through the mouth, with leaves spiralling
    #                                  off it - drop a real flower into the
    #                                  bore and the vase reads as its extension
    stem_length: float = 130.0       # how far the stem rises above the rim
    stem_bore: float = 9.0           # inner diameter; holds a real stem, and
    #                                  water too if the vessel is watertight
    num_leaves: int = 5              # leaves spiralling up the exposed stem
    leaf_length: float = 55.0
    leaf_angle: float = 25.0         # tilt from the stem axis.  Hard-capped at
    #                                  30 so the leaves print support-free -
    #                                  except with leaf_mount "insert", where
    #                                  leaves print flat and may droop to 60.
    leaf_mount: str = "printed"      # "printed" fuses the leaves to the stem;
    #                                  "insert" cuts slots instead and writes
    #                                  the leaves as a flat <name>_leaves
    #                                  plate - print it in a second color on a
    #                                  single-color printer and slide each
    #                                  leaf's tab into a slot.
    stem_mount: str = "printed"      # "printed" fuses the stem into the vessel;
    #                                  "screw" adds a threaded socket to the
    #                                  floor and exports the stem separately -
    #                                  easier cleaning, and stems taller than
    #                                  the vessel print.
    soil_cap: bool = False           # removable cover that seats just below
    #                                  the rim and looks like raked soil, with
    #                                  a hole for the stem and two finger /
    #                                  watering holes.  The planted-plant look.
    stem_split: str = "auto"         # a screw-in stem taller than the bed is
    #                                  printed in sections joined by threaded
    #                                  nodes: "auto" splits only when it must,
    #                                  "never" keeps one piece (and warns),
    #                                  "always" forces a node in every stem
    stem_curve: float = 6.0          # gentle lean (mm of sway) of the stem
    #                                  above the rim; 0 = perfectly straight.
    #                                  Below the rim the stem stays coaxial so
    #                                  the socket and water holes are untouched.
    num_branches: int = 2            # side stems branching off the main one
    #                                  above the rim, each curving upright to
    #                                  its own open tip - one flower per branch
    branch_length: float = 70.0      # how far each branch climbs; branches
    #                                  that would poke past the stem tip are
    #                                  shortened or skipped automatically

    # ------------------------------------------------------------------
    # 4e. Bouquet planter (the mouth becomes a cluster of blooms)
    # ------------------------------------------------------------------
    bouquet: bool = False            # gather the vessel to a neck and grow a
    #                                  ring of hollow flower heads out of it;
    #                                  each cup opens into the pot, so the
    #                                  whole thing plants like one pot
    bouquet_flower: str = "tulip"    # "tulip" (pointed petals, open cup) or
    #                                  "rose" (spiralled petals, closing bud)
    bouquet_count: int = 5           # blooms in the ring, 3-8; the mouth
    #                                  itself flares into a bloom in the
    #                                  middle of them - that is what you
    #                                  plant in
    bouquet_head_diameter: float = 0.0   # 0 = size it from the pot
    bouquet_tilt: float = 15.0       # how far the ring leans out; the lean
    #                                  adds to the cup's flare, so 18 is the
    #                                  cap before the petals need supports

    # ------------------------------------------------------------------
    # 5a. Mason-jar greenhouse seat (classic pot, self-watering inner,
    #     or a standalone collar ring with the reservoir insert)
    # ------------------------------------------------------------------
    jar_greenhouse: bool = False     # seat an upside-down canning jar over
    #                                  the seedling as a mini greenhouse
    jar_mouth_od: float = 86.0       # jar OUTSIDE mouth diameter: ~86 for US
    #                                  wide-mouth canning jars, ~70 regular
    jar_seat_depth: float = 10.0     # groove depth holding the jar's lip

    # ------------------------------------------------------------------
    # 5b. Self-watering set (exports <name>_outer and <name>_inner)
    # ------------------------------------------------------------------
    self_watering: bool = False      # two-piece set: outer reservoir pot with a
    #                                  refill tube + funnel, inner plant liner
    #                                  standing on a wick cup, rims flush.
    reservoir_height: float = 35.0   # water depth the outer pot holds, in mm.
    sw_wall_gap: float = 5.0         # radial gap between inner and outer walls
    refill_tube_bore: float = 16.0   # inner diameter of the refill tube
    wick_hole_radius: float = 4.0    # rope holes around the inner pot's cup
    num_wick_holes: int = 3          # how many rope holes

    # ------------------------------------------------------------------
    # 5c. Universal reservoir insert (exports <name>_insert + _insert_tube)
    # ------------------------------------------------------------------
    reservoir_insert: bool = False   # standalone platform + fill tube that
    #                                  drops into ANY watertight pot and makes
    #                                  it self-watering.  Uses reservoir_height
    #                                  and refill_tube_bore from above.
    insert_shape: str = "round"      # "round" | "square" | "hexagonal" | "octagon"
    #                                  - mirror your pot's cross-section
    insert_width: float = 120.0      # your pot's INSIDE width where the deck
    #                                  will sit (across the flats for polygons)
    insert_tube_length: float = 150.0  # fill tube length; reach from the pot
    #                                    floor to above the soil line

    # ------------------------------------------------------------------
    # 5d. Hydroponic tower (exports <name>_segment, _cup and _cap)
    # ------------------------------------------------------------------
    hydro_tower: bool = False        # stackable column segments with angled
    #                                  side ports; plants grow out of net cups
    tower_diameter: float = 110.0    # column outside diameter
    segment_height: float = 160.0    # one stackable segment
    ports_per_segment: int = 3       # plant ports, spiralling up the column
    port_bore: float = 50.0          # socket diameter the net cups drop into
    port_angle: float = 48.0         # cup tilt above horizontal.  The port's
    #                                  worst overhang is 90 - port_angle, so
    #                                  anything under 46 needs supports.
    drip_hole_diameter: float = 22.0 # hole in the cap for the drip line

    # ------------------------------------------------------------------
    # 5e. Modular garden kits (dovetail-connected sets)
    # ------------------------------------------------------------------
    modular_kit: str = "none"        # "seed_cubes" | "flower" | "stack".
    #                                  All three share one dovetail standard,
    #                                  so pieces from any kit interconnect.
    cube_size: float = 55.0          # seed cube footprint (one cell)
    cube_depth: float = 60.0         # seed cube depth
    flower_diameter: float = 140.0   # flower centre pot outside diameter
    stack_pod_diameter: float = 70.0 # clip-on pod diameter for the stack

    # ------------------------------------------------------------------
    # 5g. Yard art: a plant with a face and an opinion
    # ------------------------------------------------------------------
    yard_plant: str = "none"         # "sunflower" | "daisy" | "cactus".
    #                                  The flowers come apart into three
    #                                  prints - <name>_body (standing),
    #                                  <name>_head (petals, flat) and
    #                                  <name>_face (the middle, flat) - so
    #                                  one printer gives you three colours.
    #                                  A cactus is one standing piece.
    yard_height: float = 200.0       # plate to the top of the head,
    #                                  including whatever mount is under it
    yard_head_diameter: float = 0.0  # 0 = sized from yard_height
    yard_face: str = "angry"         # "angry" | "smug" | "grin" | "sideeye"
    #                                  | "none"
    yard_left_hand: str = "bird"     # "bird" | "fist" | "thumbs" | "peace"
    yard_right_hand: str = "bird"    # | "horns" | "wave" | "shrug" | "none".
    #                                  Mix them: one bird and one shrug.

    # ------------------------------------------------------------------
    # 5h. Shop-vessel replicas (a self-watering pair)
    # ------------------------------------------------------------------
    replica: str = "none"            # "kyra"  a 6 in. round planter with an
    #                                  attached saucer; "hdx" the reservoir
    #                                  it drops into, in the manner of a
    #                                  2.5 qt mixing bucket; "set" both,
    #                                  plus the wick cup that joins them.
    replica_pot_top: float = 152.4   # 6.00 in. across the mouth
    replica_pot_base: float = 119.38  # 4.70 in. across the saucer
    replica_pot_height: float = 139.95  # 5.51 in. tall (the listing's
    #                                  number; its own drawing says 7.32 -
    #                                  5.51 is the one that sits flush in
    #                                  the bucket)
    replica_standoff: float = 25.0   # how far the pot is held above the
    #                                  water.  This is the whole trade:
    #                                  flush rims, a real reservoir and the
    #                                  shop bucket's depth are three things
    #                                  you can have two of.  0 gives the
    #                                  bucket's proportions and no water.
    replica_plumbing: bool = True    # ribs to stand the pot on, an overflow,
    #                                  a notch to pour through and a wick
    #                                  cup.  Off = the bare shapes.

    # ------------------------------------------------------------------
    # 5m. Hanging pot cradle (three flat parts, printed lying down)
    # ------------------------------------------------------------------
    hanger: str = "none"             # "set" writes the lot; "base", "arm"
    #                                  or "top" writes one, and with a wall
    #                                  mount also "cleat", "plate", "stay".
    #                                  EVERY part prints FLAT, as modelled:
    #                                  a part that carries a hanging pot
    #                                  standing up is being pulled apart
    #                                  across its layers.
    hanger_pot_size: str = "custom"  # or a nominal nursery size, "3in" ...
    #                                  "12in", which fills in all three below
    hanger_pot_top: float = 152.4    # the pot, across the top
    hanger_pot_base: float = 114.3   # ... across the base
    hanger_pot_height: float = 144.8  # ... and standing
    hanger_arms: int = 3             # 3-5.  Three hangs level on its own.
    hanger_drop: float = 240.0       # base ring to top ring.  The arm is
    #                                  a little longer than this, and it has
    #                                  to lie flat on the bed.
    hanger_load: float = 5.0         # kg the set is sized for: pot, soil and
    #                                  water at their heaviest.  One arm is
    #                                  assumed slack.
    hanger_top: str = "hole"         # "hole" for a hook, "slot" for webbing,
    #                                  "ring" to pass a rope through
    hanger_clearance: float = 8.0    # how far the arms run off the pot
    hanger_mount: str = "ceiling"    # "wall" adds a French cleat, the plate
    #                                  that hangs on it and the rib that
    #                                  carries the reach.  A wall bracket is
    #                                  a cantilever, not a hook, so those
    #                                  three are sized off the moment.
    hanger_reach: float = 150.0      # wall to the point the pot hangs from
    hanger_cleat_length: float = 120.0  # the rail, along the wall
    hanger_screws: int = 0           # 0 = as many as the pull-out needs
    hanger_screw_bore: float = 4.5   # the screw's shank; the head is
    #                                  countersunk 45 deg, which prints

    # ------------------------------------------------------------------
    # 5n. Wall pot (the mount is IN the pot, not a bracket round it)
    # ------------------------------------------------------------------
    wall_pot: str = "none"           # "set" writes the pot and its rail;
    #                                  "pot" or "cleat" writes one. A wall
    #                                  pot IS a pot: pot_style, vase_profile,
    #                                  surface_texture and the rim all work
    #                                  on it. It is flat across the back and
    #                                  the French cleat is a pocket inside
    #                                  that flat, so nothing of the mount
    #                                  shows once it is hung.
    wall_pot_round: float = 0.0      # fraction of the circumference left
    #                                  round where the pot is NARROWEST -
    #                                  0.5 (half a pot) to about 0.95. The
    #                                  back is ONE plane, so a tapered pot
    #                                  is less round at its wide end and the
    #                                  generator reports both numbers.
    #                                  0 = as flat as the pot allows
    wall_pot_rail: float = 0.0       # the rail, along the wall. 0 = as long
    #                                  as the flat back has room for
    wall_pot_screws: int = 0         # 0 = as many as the pull-out needs
    wall_pot_screw_bore: float = 4.5  # the screw's shank
    wall_pot_liner: bool = True      # a thin pot that drops inside it. The
    #                                  OUTER then gets no holes at all -
    #                                  drainage_pattern, num_drainage_holes
    #                                  and drainage_hole_radius point at the
    #                                  LINER instead, and what runs out of
    #                                  them lands in the well, not the wall
    wall_pot_well: float = 25.0      # open space left under the liner: the
    #                                  reservoir. 0 stands the liner on the
    #                                  floor of the pot
    wall_pot_liner_wall: float = 1.6  # how thin the liner is
    wall_pot_fill: bool = True       # a standpipe up the inside of the
    #                                  liner: fills the well without wetting
    #                                  the soil, and the water standing in
    #                                  it is the level in the reservoir
    wall_pot_wick: bool = True       # a bore and a collar in the liner's
    #                                  floor for a wicking cord, so the well
    #                                  waters the plant instead of just
    #                                  catching what it drops

    # ------------------------------------------------------------------
    # 5l. Nursery pot sleeve (a cover for the pot the plant came in)
    # ------------------------------------------------------------------
    sleeve: bool = False             # the nursery pot drops in, pot and all.
    #                                  A sleeve IS a pot: pot_style,
    #                                  vase_profile, surface_texture and the
    #                                  rim all work on it as usual.
    sleeve_pot_size: str = "custom"  # or a nominal nursery size, "3in" ...
    #                                  "12in", which fills in all three
    #                                  measurements below with typical ones
    sleeve_pot_top: float = 152.4    # the nursery pot, across the top
    sleeve_pot_base: float = 114.3   # ... across the base
    sleeve_pot_height: float = 144.8  # ... and standing
    sleeve_fit: float = 1.5          # radial slack round the nursery pot
    sleeve_reveal: float = 0.0       # mm the pot's rim stands proud of the
    #                                  sleeve's; negative hides it below
    sleeve_well: float = 14.0        # drip well under the pot.  There is no
    #                                  drain, so it is also the most the
    #                                  sleeve can hold.
    sleeve_base: float = 0.0         # the sleeve's own bottom diameter,
    #                                  0 = derived from its mouth

    # ------------------------------------------------------------------
    # 5k. Under the pot (drip tray, risers, drainage mesh)
    # ------------------------------------------------------------------
    underpot: str = "none"           # "set" writes all three; "tray",
    #                                  "riser" or "mesh" writes one.  Sized
    #                                  for a pot you did NOT print - the only
    #                                  measurement needed is its base.
    under_pot_base: float = 110.0    # the pot's base diameter in mm, across
    #                                  the bottom.  Used when under_pot_size
    #                                  is "custom".
    under_pot_size: str = "custom"   # or a nominal nursery size: "3in" ...
    #                                  "12in".  That is the pot's width across
    #                                  the TOP; the base is taken as 0.75 of
    #                                  it, which is about where they land.
    under_clearance: float = 3.0     # radial gap, pot to tray wall
    under_waffle: float = 6.0        # rib height in the tray's floor, which
    #                                  is also how much water it can hold
    #                                  before the pot is standing in it.
    #                                  0 = a flat saucer.
    under_rim: float = 9.0           # tray wall above the rib tops
    under_riser_height: float = 18.0  # how far a foot lifts the pot
    under_feet: int = 3              # 3 or 4.  Three cannot rock; four
    #                                  spreads the load.
    under_mesh_diameter: float = 0.0  # mesh disc across, 0 = from the base
    under_mesh_open: float = 0.35    # fraction of the disc that is hole
    under_mesh_legs: bool = True     # nubs so it cannot seal the drain holes

    # ------------------------------------------------------------------
    # 5j. Moss pole (a hollow column you pack with sphagnum)
    # ------------------------------------------------------------------
    moss_pole: str = "none"          # "set" writes one segment, the base and
    #                                  the cap; "segment", "base" or "cap"
    #                                  writes just that one.  Print
    #                                  pole_segments copies of the segment -
    #                                  they are identical.
    pole_diameter: float = 55.0      # width ACROSS THE FLATS - the number a
    #                                  ruler gives you, on any of the shapes
    pole_segment_height: float = 150.0  # one segment, joint included
    pole_segments: int = 3           # how many you mean to stack; drives the
    #                                  reported height and the bed warning
    pole_shape: str = "square"       # "square" | "hex" | "round".  A polygon
    #                                  keys the joint and gives you flats to
    #                                  tie a stem to.
    pole_pattern: str = "lattice"    # "lattice" staggered diamonds |
    #                                  "slots" tall windows | "solid" none
    pole_open: float = 0.68          # how much of the wall is opening.  What
    #                                  caps it is the strut left between two
    #                                  openings.
    pole_rows: int = 0               # rows of openings per segment; 0 = auto
    pole_barbs: str = "inside"       # "none" | "inside" | "outside" | "both".
    #                                  Little shelves with ramped undersides:
    #                                  inside they stop the packed column
    #                                  settling, outside they hold a sheet of
    #                                  moss wrapped round the pole.
    pole_reservoir: float = 0.0      # mm of water the base holds under the
    #                                  column.  0 leaves it a foot that
    #                                  drains.  It is a sump, not a tank: it
    #                                  catches what you pour through the cap
    #                                  and feeds it back to the bottom of the
    #                                  moss, and an overflow sets the level.
    pole_wick: bool = False          # eyes in the cap and a post in the base,
    #                                  so a string can run down the column and
    #                                  back up.  It spreads what you pour down
    #                                  the whole pole, and keeps the bottom of
    #                                  the moss in touch with the sump.

    # ------------------------------------------------------------------
    # 5i. Dish-and-keel pair (a pot that sits in a bowl and drinks from it)
    # ------------------------------------------------------------------
    cradle: str = "none"             # "set" writes both parts, "pot" or
    #                                  "dish" one of them.  The pot's bottom
    #                                  is a cone - a keel - that hangs into
    #                                  the dish's water; slots up the keel
    #                                  let the soil wick it back up.
    cradle_diameter: float = 120.0   # outside diameter at the joint, which
    #                                  is the dish's widest point.  The pot's
    #                                  lip stands cradle_flare + 3 mm proud
    #                                  of it.
    cradle_height: float = 108.0     # assembled height, plate to the lip
    cradle_dish_height: float = 44.0 # the dish's share of it - and so how
    #                                  deep the reservoir can be
    cradle_keel: float = 26.0        # how far the pot's keel hangs below the
    #                                  joint.  Deeper = a narrower pad to
    #                                  print on, since the keel falls at the
    #                                  overhang limit.
    cradle_bowl: str = "round"       # "round" | "cone" | "tub" - the dish's
    #                                  silhouette, and with it how much water
    #                                  it holds: tub the most, cone the least,
    #                                  round the most like a dish.
    cradle_flare: float = 1.5        # how much wider the pot's mouth is than
    #                                  the joint, per side
    cradle_windows: int = 1          # notches in the dish's rim to pour
    #                                  through; 0-4
    cradle_drains: int = 8           # wicking slots up the keel; 0 closes it
    cradle_lip: bool = True          # a rolled lip round the pot's mouth

    # ------------------------------------------------------------------
    # 5f. Trailer-hitch ball mount
    # ------------------------------------------------------------------
    hitch_mount: str = "none"        # with yard_plant set: "fused" builds
    #                                  the socket into the plant's base and
    #                                  "screw" gives it a thread for the
    #                                  collar; "none" puts it on a disc.
    #                                  On its own:
    #                                  "cover" writes a one-piece cover that
    #                                  snaps over a trailer ball; "screw"
    #                                  splits it into <name>_hitch_collar
    #                                  (the gripping socket, with a thread on
    #                                  top) and <name>_hitch_cap (a lid) so
    #                                  one collar per ball size can carry
    #                                  anything you screw onto it.
    #                                  Take it off before towing.
    hitch_ball: str = "2"            # ball diameter: "1-7/8" | "2" |
    #                                  "2-5/16" | "3", or a number in mm
    hitch_fingers: int = 5           # slices the socket is cut into; odd
    #                                  counts avoid a weak diameter
    hitch_grip: float = 1.1          # how much narrower the mouth is than the
    #                                  ball.  This IS the retention, and it is
    #                                  also how far each finger must bend, so
    #                                  bigger means a firmer snap and a more
    #                                  strained spring.  0.8-1.6 is the range.

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
        if self.pot_style == "square":
            return 4
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
        if self.vase_profile not in VASE_PROFILES:
            raise ParameterError(
                f"unknown vase_profile {self.vase_profile!r}; "
                f"choose from {list(VASE_PROFILES)}"
            )
        if self.stem_mount not in ("printed", "screw"):
            raise ParameterError('stem_mount must be "printed" or "screw"')
        if self.soil_cap and self.jar_greenhouse:
            raise ParameterError(
                "soil_cap and jar_greenhouse both occupy the mouth - pick one"
            )
        if self.leaf_mount not in ("printed", "insert"):
            raise ParameterError('leaf_mount must be "printed" or "insert"')
        if self.stem_split not in ("auto", "never", "always"):
            raise ParameterError(
                'stem_split must be "auto", "never" or "always"')
        if self.bouquet:
            if self.bouquet_flower not in ("tulip", "rose"):
                raise ParameterError('bouquet_flower must be "tulip" or "rose"')
            if not 3 <= int(self.bouquet_count) <= 8:
                raise ParameterError("bouquet_count should be 3-8")
            if not 0.0 <= self.bouquet_tilt <= 18.0:
                raise ParameterError(
                    "bouquet_tilt must be 0-18 degrees: past 18 the lean and "
                    "the cup's own flare together need supports"
                )
            if self.bouquet_head_diameter and not \
                    16.0 <= self.bouquet_head_diameter <= 60.0:
                raise ParameterError("bouquet_head_diameter should be 16-60 mm")
            if self.stem:
                raise ParameterError(
                    "bouquet and stem both fill the mouth - pick one")
            if self.jar_greenhouse:
                raise ParameterError(
                    "bouquet and jar_greenhouse both occupy the mouth - "
                    "pick one")
        if self.stem:
            max_leaf = 60.0 if self.leaf_mount == "insert" else 30.0
            if not 10.0 <= self.leaf_angle <= max_leaf:
                raise ParameterError(
                    f"leaf_angle must be 10-{max_leaf:.0f} degrees for "
                    f'leaf_mount "{self.leaf_mount}": fused leaves past 30 '
                    "need supports; insert leaves print flat and may droop "
                    "to 60"
                )
            if not 5.0 <= self.stem_bore <= 20.0:
                raise ParameterError("stem_bore should be 5-20 mm")
            if self.jar_greenhouse:
                raise ParameterError(
                    "stem and jar_greenhouse both occupy the mouth - pick one"
                )
            if self.drainage_pattern == "center":
                raise ParameterError(
                    "the stem stands where the center drainage hole goes - "
                    "use ring, grid or none"
                )
            if not 0.0 <= self.stem_curve <= 14.0:
                raise ParameterError("stem_curve should be 0-14 mm of sway")
            if self.stem_curve > 0 and self.stem_length < 6.0 * self.stem_curve:
                raise ParameterError(
                    "stem_curve is too strong for this stem_length: the lean "
                    "would overhang - keep stem_length >= 6 x stem_curve"
                )
            if not 0 <= int(self.num_branches) <= 5:
                raise ParameterError("num_branches should be 0-5")
            if self.num_branches and not 25.0 <= self.branch_length <= 150.0:
                raise ParameterError("branch_length should be 25-150 mm")
        if self.surface_texture not in TEXTURES:
            raise ParameterError(
                f"unknown surface_texture {self.surface_texture!r}; "
                f"choose from {list(TEXTURES)}"
            )
        if self.surface_texture != "none":
            if self.texture_depth < 0 or self.texture_cell <= 0:
                raise ParameterError("texture_depth/texture_cell must be positive")
        from .printers import PRINTER_CHOICES
        if self.printer not in PRINTER_CHOICES:
            raise ParameterError(
                f"unknown printer {self.printer!r}; choose from {list(PRINTER_CHOICES)}"
            )
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
        if not 0.2 <= self.scale <= 3.0:
            raise ParameterError("scale should be between 0.2 and 3.0")
        if self.num_side_holes < 0:
            raise ParameterError("num_side_holes cannot be negative")

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
        if self.self_watering:
            if self.pot_style == "low_poly_faceted":
                raise ParameterError(
                    "self_watering cannot use a low_poly_faceted outer pot - "
                    "its rotating facets leave no straight wall line for the "
                    "refill tube"
                )
            if not 8.0 <= self.refill_tube_bore <= 30.0:
                raise ParameterError("refill_tube_bore should be 8-30 mm")
            if self.generate_saucer:
                warn.append("generate_saucer is ignored for a self-watering set")
        if self.modular_kit != "none":
            from .modular import KITS
            if self.modular_kit not in KITS:
                raise ParameterError(
                    f"unknown modular_kit {self.modular_kit!r}; "
                    f"choose from {list(KITS)}"
                )
            if self.self_watering or self.reservoir_insert or self.hydro_tower \
                    or self.jar_greenhouse:
                raise ParameterError(
                    "modular_kit cannot combine with the other product flags"
                )
        if self.jar_greenhouse and self.hydro_tower:
            raise ParameterError(
                "jar_greenhouse is not available on the hydro tower - use it "
                "with the classic pot, self-watering set or reservoir insert"
            )
        if self.hydro_tower and (self.self_watering or self.reservoir_insert):
            raise ParameterError(
                "hydro_tower cannot combine with self_watering or "
                "reservoir_insert - generate them separately"
            )
        if self.replica != "none":
            from .replica import check_replica
            warn += check_replica(self)
            if (self.yard_plant != "none" or self.bouquet or self.stem
                    or self.self_watering or self.hydro_tower
                    or self.modular_kit != "none"):
                raise ParameterError(
                    "replica is its own object - it does not combine with "
                    "the pots, the yard art or the other product flags"
                )
        if self.hanger != "none":
            from .hanger import check_hanger
            warn += check_hanger(self)
            if (self.sleeve or self.underpot != "none"
                    or self.moss_pole != "none" or self.cradle != "none"
                    or self.replica != "none" or self.yard_plant != "none"
                    or self.bouquet or self.stem or self.self_watering
                    or self.hydro_tower or self.reservoir_insert
                    or self.modular_kit != "none"):
                raise ParameterError(
                    "hanger is its own set - it does not combine with the "
                    "pots or the other product flags")
        if self.wall_pot != "none":
            from .wallpot import check_wall_pot
            warn += check_wall_pot(self)
            if (self.sleeve or self.hanger != "none"
                    or self.underpot != "none" or self.moss_pole != "none"
                    or self.cradle != "none" or self.replica != "none"
                    or self.yard_plant != "none" or self.bouquet or self.stem
                    or self.self_watering or self.hydro_tower
                    or self.reservoir_insert or self.modular_kit != "none"
                    or self.jar_greenhouse):
                raise ParameterError(
                    "wall_pot is a pot in its own right - it does not "
                    "combine with the other product flags")
        if self.sleeve:
            from .sleeve import check_sleeve
            warn += check_sleeve(self)
            if (self.underpot != "none" or self.moss_pole != "none"
                    or self.cradle != "none" or self.replica != "none"
                    or self.yard_plant != "none" or self.bouquet or self.stem
                    or self.self_watering or self.hydro_tower
                    or self.reservoir_insert or self.modular_kit != "none"):
                raise ParameterError(
                    "sleeve is its own object - it does not combine with the "
                    "pots or the other product flags")
        if self.underpot != "none":
            from .underpot import check_underpot
            warn += check_underpot(self)
            if (self.moss_pole != "none" or self.cradle != "none"
                    or self.replica != "none" or self.yard_plant != "none"
                    or self.bouquet or self.stem or self.self_watering
                    or self.hydro_tower or self.reservoir_insert
                    or self.modular_kit != "none"):
                raise ParameterError(
                    "underpot is its own set - it does not combine with the "
                    "pots or the other product flags")
        if self.moss_pole != "none":
            from .mosspole import check_mosspole
            warn += check_mosspole(self)
            if (self.cradle != "none" or self.replica != "none"
                    or self.yard_plant != "none" or self.bouquet or self.stem
                    or self.self_watering or self.hydro_tower
                    or self.reservoir_insert or self.modular_kit != "none"):
                raise ParameterError(
                    "moss_pole is its own object - it does not combine with "
                    "the pots or the other product flags")
        if self.cradle != "none":
            from .cradle import check_cradle
            warn += check_cradle(self)
            if (self.replica != "none" or self.yard_plant != "none"
                    or self.bouquet or self.stem or self.self_watering
                    or self.hydro_tower or self.reservoir_insert
                    or self.modular_kit != "none"):
                raise ParameterError(
                    "cradle is its own pair - it does not combine with the "
                    "pots, the yard art or the other product flags")
        if self.yard_plant != "none":
            from .yard import check_yard
            warn += check_yard(self)
            if self.self_watering or self.hydro_tower or self.bouquet \
                    or self.stem or self.modular_kit != "none":
                raise ParameterError(
                    "yard_plant is its own object - it does not combine with "
                    "the pots, the bouquet or the planted stem"
                )
        if self.hitch_mount != "none":
            if self.hitch_mount not in ("cover", "screw", "fused"):
                raise ParameterError(
                    f"unknown hitch_mount {self.hitch_mount!r}; "
                    f"choose from ['cover', 'screw', 'fused']"
                )
            if self.hitch_mount == "fused" and self.yard_plant == "none":
                raise ParameterError(
                    "hitch_mount 'fused' fuses the socket into a yard_plant; "
                    "on its own use 'cover' or 'screw'"
                )
            if not 3 <= self.hitch_fingers <= 9:
                raise ParameterError("hitch_fingers should be 3-9")
            if self.hitch_fingers % 2 == 0:
                warn.append(
                    f"{self.hitch_fingers} hitch fingers puts a slot opposite "
                    f"a slot, which is the socket's weakest diameter - an odd "
                    f"count spreads the grip"
                )
            from .hitch import ball_diameter, check_hitch
            ball_diameter(self)             # raises on an unknown ball
            warn += check_hitch(self)
        if self.reservoir_insert:
            if self.self_watering:
                raise ParameterError(
                    "pick one: self_watering (a full two-pot set) or "
                    "reservoir_insert (a drop-in for an existing pot)"
                )
            from .insert import INSERT_SHAPES
            if self.insert_shape not in INSERT_SHAPES:
                raise ParameterError(
                    f"unknown insert_shape {self.insert_shape!r}; "
                    f"choose from {sorted(INSERT_SHAPES)}"
                )
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
