"""Holiday pots: shapes with a season, and faces cut right through them.

A jack-o'-lantern turns out to be three things this generator very nearly
had already.

The **body** is a squat sphere with lobes, and the lobes are
``ribbed_spiral`` with the twist turned off - the ribs are added outside
the nominal wall and never carved into it, so a deep untwisted rib IS a
pumpkin lobe.  The silhouette is one new curve.

The **face** is the interesting part, and the reason a carved pumpkin
prints at all.  A round eye or a flat-topped mouth is a ceiling, and a
ceiling over a hole needs supports - which is exactly why the side
drainage ports in this generator are diamonds and not circles.  Every
feature of a face here is a **pointed port**: a prism whose roof comes to
a peak, so the roof is two faces inside the overhang budget instead of one
flat span across the top.

That is not a compromise on the look.  A jack-o'-lantern's grin already
*is* a row of pointed cells - the triangles of material between the gaps
are the teeth, and the gaps' ceilings come to a point because the teeth
do.  Carve the classic face and you have carved a printable one.

The **feet** are the lobes: with ``base_flat`` off the ribs run all the
way down and the pot sits on eight little pads of its own.

The liner
---------
A face cut right through is a hole into the soil, so the set comes with a
**liner**: a plain tapered cup that drops in and holds the soil behind the
face.  It has to be a cone rather than a copy of the cavity, because the
pot's mouth is narrower than its belly and nothing shaped like the belly
will go through the mouth.  So it sits well inside the wall, and what you
see through the eyes is a dark gap - which is what should be behind a
jack-o'-lantern's eyes anyway.

The number that matters
-----------------------
The lowest point of the face is a hole in the side of a pot, so it is also
the **waterline**: fill past it and it runs down the outside.  The
generator works out how many millilitres that is and says so, because it
is not a number you would guess.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _finish, _prism, build_pot, lathe
from .params import ParameterError, PotParams
from .profile import build_profiles
from .sections import make_section

SHAPES = ("none", "pumpkin", "gourd", "cauldron")
FACES = ("none", "classic", "cat", "angry", "kawaii")
PARTS = ("set", "pot", "liner")

#: each shape, in the pot builder's own terms
#: ``aspect`` is the height the silhouette wants, as a fraction of the
#: mouth: a pumpkin is squat and a gourd is not, and a curve asked to do
#: the wrong one of those either loses its waist or leans past the
#: overhang budget.
_SHAPE = {
    "pumpkin": dict(vase="pumpkin", lobes=8, lobe=0.075, rim=False,
                    aspect=0.70),
    "gourd": dict(vase="gourd", lobes=12, lobe=0.045, rim=False,
                  aspect=1.30),
    "cauldron": dict(vase="pumpkin", lobes=0, lobe=0.0, rim=True,
                     aspect=0.75),
}

#: Every feature is ``(u, v, half_width, apex_shift, floor)`` in units of
#: the face's own scale, with u across the surface and v up it.  ``eye`` is
#: given once and mirrored; ``apex_shift`` leans a brow, positive =
#: outward.
#:
#: ``floor`` is what makes a face look carved.  At 0 the feature is a
#: **triangle standing on a flat base** - which is the jack-o'-lantern
#: shape, and is printable for the same reason it is iconic: the base
#: faces up, so it is free, and the two rising edges are the roof.  Above
#: 0 the base drops to a point that far below and the feature is a
#: diamond, which suits a cat's eye.
#:
#: A grin is a row of gaps, so the pitch is what is left of a tooth: the
#: teeth are ``pitch - 2 * half_w`` wide and if that goes to zero the cells
#: merge into one slot - which is a different face, and one hole instead of
#: five.  ``check_holiday`` measures it in millimetres and says so.
#:
#: The teeth point UP, always.  A tooth hanging down from the top of the
#: mouth starts, layer by layer, as a speck of plastic in mid air with
#: nothing under it; a tooth standing up off the bottom of the mouth only
#: ever narrows as it rises.  So the mouth is a row of gaps pointed at the
#: top, and the triangles left between them are the teeth.
_FACE = {
    "classic": dict(
        eye=(1.00, 0.30, 0.42, 0.00, 0.0), nose=(0.0, 0.12, 0.24, 0.0, 0.0),
        mouth=dict(v=-0.75, cells=5, pitch=0.86, half_w=0.33, floor=0.0)),
    "cat": dict(
        eye=(0.95, 0.28, 0.34, 0.00, 1.0), nose=(0.0, 0.06, 0.20, 0.0, 0.0),
        mouth=dict(v=-0.62, cells=3, pitch=0.76, half_w=0.29, floor=0.0)),
    "angry": dict(
        eye=(1.02, 0.30, 0.46, 0.26, 0.0), nose=(0.0, 0.10, 0.22, 0.0, 0.0),
        mouth=dict(v=-0.78, cells=6, pitch=0.70, half_w=0.26, floor=0.0)),
    "kawaii": dict(
        eye=(0.80, 0.26, 0.30, 0.00, 1.0), nose=None,
        mouth=dict(v=-0.52, cells=3, pitch=0.60, half_w=0.21, floor=0.0)),
}

_ROOF = 1.35             # a port's roof rises this much per unit of half
#                          width: 1.0 would be exactly 45 degrees, which is
#                          the budget with nothing left
_FLOOR = 0.85            # ... and its underside, which faces up and is free
_SCALE = 0.22            # the face, against the smaller of height and width
_FACE_Z = 0.46           # where its middle sits up the pot
_FIT = 1.2               # slack round the liner - it is a drop-in, not a fit
_LINER_WALL = 1.6
_LINER_FLOOR = 2.0
_LINER_TAPER = 0.78      # the liner's foot, as a fraction of its mouth
_WELL = 22.0             # how far the liner stands off the pot's own floor
_POSTS = 4               # ... on this many posts
_POST = 9.0              # ... this far across
_SPILL = 3.0             # water kept this far under the lowest hole
_WEB = 2.4               # thinnest bridge of pot left between two
#                          holes - a tooth, or the bone between an
#                          eye and the nose


# ---------------------------------------------------------------------------
# the body
# ---------------------------------------------------------------------------
def shape_params(p: PotParams) -> PotParams:
    """The holiday pot's body, in the pot builder's own terms.

    Everything that makes the shape is a parameter the generator already
    has - a silhouette, a rib count and a rib depth with no twist - so the
    styles, the colours, the rim and the drainage all still work on it.
    """
    if p.holiday not in SHAPES:
        raise ParameterError(
            f"unknown holiday {p.holiday!r}; choose from {list(SHAPES)[1:]}")
    if p.holiday == "none":
        return p
    s = _SHAPE[p.holiday]
    lobes = int(p.holiday_lobes) if p.holiday_lobes > 0 else s["lobes"]
    depth = (float(p.holiday_lobe_depth) if p.holiday_lobe_depth > 0
             else s["lobe"] * p.top_radius)
    style = "ribbed_spiral" if lobes else "classic_tapered"
    return p.with_(
        vase_profile=s["vase"], pot_style=style, rib_count=max(lobes, 1),
        rib_depth=depth if lobes else 0.0, rib_twist_degrees=0.0,
        # the lobes run to the bed and the pot stands on them, which is
        # what a pumpkin does and what the reference print does
        base_flat=False, add_top_rim=s["rim"])


def face_plan(p: PotParams) -> dict:
    """Where the face goes and how big it is, in millimetres."""
    if p.holiday_face not in FACES:
        raise ParameterError(
            f"unknown holiday_face {p.holiday_face!r}; choose from "
            f"{list(FACES)}")
    q = shape_params(p)
    prof = build_profiles(q)
    z = _FACE_Z * q.height
    r_wall = _radius_at(prof, z)
    scale = (_SCALE * min(q.height, 2.0 * r_wall)
             * max(0.2, float(p.holiday_face_scale)))
    # far enough out to clear the WIDEST ring, not the rim: on every one
    # of these shapes the belly is wider than the mouth, and a cutter cut
    # to the rim's radius stops inside the wall and leaves a blind pocket
    # instead of a hole
    reach = (max(max(r for r, _ in prof.outer), prof.rim_outer_radius)
             + max(q.rib_depth, 0.0) + 8.0)
    return dict(q=q, prof=prof, z=z, r_wall=r_wall, scale=scale, reach=reach,
                ports=_ports(p.holiday_face, scale, z))


def _radius_at(prof, z: float) -> float:
    from .profile import outer_radius_at
    return outer_radius_at(prof, z)


def _ports(face: str, s: float, z0: float) -> list[dict]:
    """Every hole in the face, in millimetres.

    A port's roof has to rise at more than 45 degrees or it is a ceiling,
    so the rise is taken off the half width - including the apex shift,
    which makes one side of a leaning brow shallower than the other.
    """
    if face == "none":
        return []
    spec = _FACE[face]
    out: list[dict] = []

    def add(u: float, v: float, half: float, shift: float,
            floor: float) -> None:
        span = half + abs(shift)
        out.append(dict(u=u, v=z0 + v, half=half, shift=shift,
                        up=_ROOF * span, down=floor * _FLOOR * half))

    eu, ev, eh, esh, ef = spec["eye"]
    for side in (-1.0, 1.0):
        add(side * eu * s, ev * s, eh * s, side * esh * s, ef)
    if spec["nose"]:
        nu, nv, nh, nsh, nf = spec["nose"]
        add(nu * s, nv * s, nh * s, nsh * s, nf)
    m = spec["mouth"]
    n = int(m["cells"])
    for i in range(n):
        u = (i - 0.5 * (n - 1)) * m["pitch"] * s
        add(u, m["v"] * s, m["half_w"] * s, 0.0, m["floor"])
    return out


def port_profile(port: dict) -> list[tuple[float, float]]:
    """The hole's outline, across the surface and up it.

    Flat-based when ``down`` is zero - a triangle standing on its base,
    which is the carved-pumpkin shape - and a diamond when it is not.
    """
    roof = [(-port["half"], port["v"]),
            (port["shift"], port["v"] + port["up"]),
            (port["half"], port["v"])]
    if port["down"] <= 1e-9:
        return roof
    return roof + [(0.0, port["v"] - port["down"])]


def _web(a: dict, b: dict) -> float:
    """How much pot is left standing between two holes, in millimetres.

    Two ports are separate if their boxes clear each other in u or in v,
    so the web is the wider of the two clearances - the bounding boxes are
    a shade pessimistic against a pointed roof, which is the safe way
    round.
    """
    du = abs(a["u"] - b["u"]) - a["half"] - b["half"]
    lo_a, hi_a = a["v"] - a["down"], a["v"] + a["up"]
    lo_b, hi_b = b["v"] - b["down"], b["v"] + b["up"]
    dv = max(lo_a - hi_b, lo_b - hi_a)
    return max(du, dv)


def face_cutters(p: PotParams) -> list[trimesh.Trimesh]:
    """The face, as pointed prisms to take out of the wall."""
    if p.holiday_face == "none":
        return []
    k = face_plan(p)
    r = k["r_wall"]
    cuts = []
    for port in k["ports"]:
        # u is an arc along the surface; a port is small enough that the
        # chord and the arc are the same thing to a tenth of a millimetre
        az = port["u"] / max(r, 1e-6)
        prism = _prism(port_profile(port), 0.25 * r, k["reach"])
        prism.apply_transform(
            trimesh.transformations.rotation_matrix(az, [0, 0, 1]))
        cuts.append(prism)
    return cuts


def has_liner(p: PotParams) -> bool:
    """A liner only exists to hide the soil behind a face.

    So ``holiday_liner`` on its own is not enough, and asking for a plain
    pumpkin with no face is not an error - it is a pot, and it keeps its
    own soil in.
    """
    return (p.holiday != "none" and bool(p.holiday_liner)
            and p.holiday_face != "none")


def well_posts(p: PotParams) -> list[trimesh.Trimesh]:
    """Posts on the pot's floor for the liner to stand on.

    Without them the liner sits flat on the floor, its drainage holes
    against the floor, and the water has nowhere to go.  With them there
    is a well underneath - and posts are the one way to make that well
    that costs nothing in print: a post is vertical on every side and flat
    on top, so there is no new overhang anywhere.

    A shelf around the cavity would do the same job and would have to be
    chamfered under, and feet on the LINER would not work at all - feet
    hold a floor up in the air, and that floor is a ceiling to whatever
    prints under it.
    """
    if not has_liner(p) or _POSTS <= 0:
        return []
    k = liner_plan(p)
    # buried a little in the floor so the union has something to bite on,
    # and stopping exactly at the seat, which is what sets the liner's
    # height
    bottom, top = k["floor"] - 4.0, k["seat"]
    r = 0.80 * k["r_bot"]
    out = []
    for i in range(_POSTS):
        # offset half a step off the liner's drain holes, which sit on
        # their own ring at the same angles
        a = 2.0 * math.pi * (i + 0.5) / _POSTS
        post = trimesh.creation.box(extents=(_POST, _POST, top - bottom))
        post.apply_transform(
            trimesh.transformations.rotation_matrix(a, [0, 0, 1]))
        post.apply_translation((r * math.cos(a), r * math.sin(a),
                                0.5 * (bottom + top)))
        out.append(post)
    return out


def build_holiday_pot(p: PotParams) -> trimesh.Trimesh:
    """The pot, with its face cut right through."""
    check_holiday(p)
    return build_pot(shape_params(p))


# ---------------------------------------------------------------------------
# the liner, and the waterline the face sets
# ---------------------------------------------------------------------------
def liner_plan(p: PotParams) -> dict:
    """A cone that goes in through the mouth and holds the soil back.

    Not a copy of the cavity: the pot's mouth is narrower than its belly,
    so nothing shaped like the belly would go in.
    """
    k = face_plan(p)
    q = k["q"]
    prof = k["prof"]
    top = q.height - 2.0
    r_top = _cavity_at(q, prof, top) - _FIT
    r_bot = _LINER_TAPER * r_top
    if r_top < 18.0:
        raise ParameterError(
            f"the mouth leaves only {2 * r_top:.0f} mm for a liner to drop "
            f"through - widen the pot, or set holiday_liner off and treat "
            f"the face as a cachepot")
    # it stands on posts, not on the floor, so the water has somewhere to go
    seat = prof.floor_top_z + _WELL
    height = top - seat
    inner = 0.5 * math.pi * (height - _LINER_FLOOR) * (
        (r_top - _LINER_WALL) ** 2 + (r_bot - _LINER_WALL) ** 2) / 1000.0
    return dict(q=q, prof=prof, floor=prof.floor_top_z, seat=seat, top=top,
                r_top=r_top, r_bot=r_bot, height=height, soil=inner,
                well=_well_millilitres(prof, prof.floor_top_z, seat))


def _well_millilitres(prof, lo: float, hi: float) -> float:
    """What stands under the liner before it reaches its feet."""
    zs = np.linspace(lo, hi, 61)
    r = np.interp(zs, [zz for _, zz in prof.inner],
                  [rr for rr, _ in prof.inner])
    gross = float(np.trapezoid(math.pi * r ** 2, zs)) / 1000.0
    return max(gross - _POSTS * _POST ** 2 * (hi - lo) / 1000.0, 0.0)


def _cavity_at(q: PotParams, prof, z: float) -> float:
    return float(np.interp(z, [zz for _, zz in prof.inner],
                           [rr for rr, _ in prof.inner]))


def spill_height(p: PotParams) -> float:
    """The lowest hole in the face - which is the waterline."""
    k = face_plan(p)
    if not k["ports"]:
        return float("inf")
    return min(port["v"] - port["down"] for port in k["ports"])


def spill_millilitres(p: PotParams) -> float:
    """What stands in the pot before the face leaks.

    Free volume, not cavity volume: the posts and the liner are in there
    taking up room, so they come off.
    """
    k = face_plan(p)
    z = spill_height(p)
    if not math.isfinite(z):
        return float("inf")
    prof = k["prof"]
    floor = prof.floor_top_z
    if z <= floor:
        return 0.0
    zs = np.linspace(floor, z, 241)
    r = np.interp(zs, [zz for _, zz in prof.inner],
                  [rr for rr, _ in prof.inner])
    free = math.pi * r ** 2
    if has_liner(p):
        liner = liner_plan(p)
        free -= np.where(zs <= liner["seat"],
                         _POSTS * _POST ** 2,
                         math.pi * np.interp(
                             zs, [liner["seat"], liner["top"]],
                             [liner["r_bot"], liner["r_top"]]) ** 2)
    return float(np.trapezoid(np.maximum(free, 0.0), zs)) / 1000.0


def build_holiday_liner(p: PotParams) -> trimesh.Trimesh:
    """The plain cup that drops inside it."""
    check_holiday(p)
    if p.holiday_face == "none":
        raise ParameterError(
            "there is no face to hide the soil behind, so the pot holds it "
            "on its own - set holiday_liner off, or carve a face")
    k = liner_plan(p)
    sec = make_section(k["q"].with_(pot_style="classic_tapered",
                                    surface_texture="none",
                                    vase_profile="none"))
    t = _LINER_WALL
    body = lathe([(k["r_bot"], 0.0), (k["r_top"], k["height"])], sec,
                 decorate=False)
    hollow = lathe([(k["r_bot"] - t, _LINER_FLOOR),
                    (k["r_top"] - t, k["height"] + 2.0)], sec, decorate=False)
    liner = _boolean("difference", [body, hollow])

    cuts = []
    n = max(0, int(p.holiday_liner_holes))
    if n:
        r_ring = 0.55 * (k["r_bot"] - t)
        for i in range(n):
            a = 2.0 * math.pi * i / n
            hole = trimesh.creation.cylinder(
                radius=0.5 * float(p.drainage_hole_radius),
                height=4.0 * _LINER_FLOOR, sections=32)
            hole.apply_translation((r_ring * math.cos(a),
                                    r_ring * math.sin(a), _LINER_FLOOR))
            cuts.append(hole)
    if cuts:
        liner = _boolean("difference", [liner] + cuts)
    return _finish(liner, center=True)


def seated_liner(p: PotParams) -> trimesh.Trimesh:
    liner = build_holiday_liner(p)
    liner.apply_translation((0.0, 0.0, liner_plan(p)["seat"]))
    return liner


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------
def check_holiday(p: PotParams) -> list[str]:
    out: list[str] = []
    if p.holiday == "none":
        if p.holiday_face != "none":
            raise ParameterError(
                "holiday_face needs a holiday shape to go on - set holiday "
                "to a pumpkin, a gourd or a cauldron")
        return out
    # note: no q.validate() - shape_params is idempotent, so the derived
    # params still carry the holiday and validate() would call straight
    # back into here
    q = shape_params(p)
    k = face_plan(p)

    # the roof of every hole has to be steeper than the overhang budget
    limit = math.tan(math.radians(p.overhang_limit_deg))
    for port in k["ports"]:
        for span in (port["half"] + port["shift"],
                     port["half"] - port["shift"]):
            if span > 1e-9 and port["up"] / span < limit + 1e-9:
                raise ParameterError(
                    f"a hole in this face has a roof at "
                    f"{math.degrees(math.atan(port['up'] / span)):.0f} deg, "
                    f"which would need supports - lower holiday_face_scale")
    # ... and no two holes may run into each other.  Two that touch are
    # one hole, which is why the genus of the finished pot is the proof
    # that a face came out as drawn: a through hole adds exactly 1.
    ports = k["ports"]
    for i, a in enumerate(ports):
        for b in ports[i + 1:]:
            gap = _web(a, b)
            if gap < _WEB:
                raise ParameterError(
                    f"two holes in this face leave only {max(gap, 0.0):.1f} "
                    f"mm of pot between them"
                    + (" - they overlap, so they would come out as one hole"
                       if gap < 0 else "")
                    + ". Lower holiday_face_scale, or use a wider pot")

    if ports:
        lo = spill_height(p)
        hi = max(port["v"] + port["up"] for port in ports)
        if lo < k["prof"].floor_top_z + 2.0:
            raise ParameterError(
                f"the face reaches down to {lo:.0f} mm, which is into the "
                f"pot's own floor - lower holiday_face_scale, or use a "
                f"taller pot")
        if hi > q.height - 4.0:
            raise ParameterError(
                f"the face reaches {hi:.0f} mm up a {q.height:.0f} mm pot "
                f"and would break the rim - lower holiday_face_scale")
        out.append(
            f"the {p.holiday_face} face is {len(k['ports'])} pointed holes "
            f"with roofs at "
            f"{math.degrees(math.atan(_ROOF)):.0f} deg. A round eye or a "
            f"flat-topped grin is a ceiling and needs supports; a pointed "
            f"one is two faces inside the budget, which is why a carved "
            f"pumpkin prints and a drilled one does not")
        out.append(
            f"the lowest hole is {lo:.0f} mm up, so that is the waterline: "
            f"about {spill_millilitres(p):.0f} ml of free space under it and "
            f"then it runs down the outside. Water it in the sink, or lift "
            f"the liner out")
    aspect = q.height / max(q.top_diameter, 1e-6)
    want = _SHAPE[p.holiday]["aspect"]
    if not 0.75 * want <= aspect <= 1.35 * want:
        out.append(
            f"a {p.holiday} is {want:.2f} times as tall as it is wide and "
            f"this one is {aspect:.2f} - it will still print, but for the "
            f"silhouette try height {want * q.top_diameter:.0f} mm at this "
            f"mouth, or a {q.height / want:.0f} mm mouth at this height")
    if q.pot_style == "ribbed_spiral":
        out.append(
            f"{q.rib_count} lobes {q.rib_depth:.1f} mm deep, no twist - the "
            f"ribs stand OUTSIDE the wall so the pot is never thinner for "
            f"them, and with base_flat off they run to the bed and it "
            f"stands on them")
    if p.holiday_face == "none":
        out.append(
            "no face, so this is a plain holiday-shaped pot: it keeps its "
            "own soil in and no liner is written")
    elif p.holiday_liner:
        liner = liner_plan(p)
        out.append(
            f"the liner is a plain cone {2 * liner['r_top']:.0f} mm across "
            f"its mouth holding about {liner['soil']:.0f} ml. It has to be "
            f"a cone and not a copy of the cavity, because this pot's mouth "
            f"is narrower than its belly and nothing belly-shaped goes in")
        out.append(
            "what you see through the eyes is the gap between the liner and "
            "the wall, which is the right thing to see through a "
            "jack-o'-lantern's eyes")
        out.append(
            f"it stands on {_POSTS} posts {_WELL:.0f} mm off the floor, so "
            f"its drainage holes are not pressed against it. That well is "
            f"about {liner['well']:.0f} ml: with the pot's own drainage on "
            f"it is clearance and the water runs through, and with "
            f"drainage_pattern set to none it is a reservoir instead")
    else:
        out.append(
            "no liner, so the soil is up against the face and will show "
            "through it - that is a cachepot: drop a nursery pot in, or "
            "turn holiday_liner on")
    return out
