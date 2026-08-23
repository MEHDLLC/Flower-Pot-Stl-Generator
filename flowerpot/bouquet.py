"""The bouquet planter: a pot whose mouth is a cluster of blooms.

The vessel gathers to a neck like a bunch of stems held in a fist, and out
of that gather rises a ring of flower heads - tulips or roses - each one a
hollow cup opening upward.  Every cup is bored down through the gather into
the vessel's own cavity, so the whole thing is one planter: fill it through
the blooms and each becomes a pocket for a succulent, with the body below
as shared root room and reservoir.

Everything here has to print standing up with no supports, which drives
four decisions:

* **The middle bloom is the pot's mouth.**  The cavity does not stop at the
  neck and get capped - it cones in (at ~52 degrees, so the ceiling it makes
  is printable) to the middle bloom's throat and carries on up inside it.
  That bloom is the planting well; the ring around it are pockets, each with
  a drain into the body.  It also leaves a solid shoulder between throat and
  neck, which is what the ring blooms stand on.
* **A cup is a cone that opens upward**, so its own outside is its support.
  What it costs is the *tilt*: leaning a head outward adds its tilt to the
  flare on the downhill side, so ``flare + tilt`` is the budget, and the
  tilt is capped at 18 degrees.
* **Petals are a scalloped cross-section**, not applied geometry - a
  radius modulated around theta, swept by the same lathe as everything
  else, so the blooms are watertight by construction.  The rose's scallop
  also winds with height, which is what makes it read as a rose rather
  than a fluted cup; that wind adds vertical gradient of its own and is
  charged against the same budget.
* **The shoulder is hollow.**  Solid, it is the heaviest thing in the model
  and most of it carries nothing - but the deck the blooms stand on cannot
  simply be left over a void, because a flat roof does not print.  So the
  void is a tent (see :func:`shoulder_chamber`), cut by radial ribs into one
  pocket per bloom, each pierced by that bloom's own drain on its way down
  to the body.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, lathe
from .params import ParameterError, PotParams
from .profile import resample
from .sections import Section

_PLUG_H = 4.0           # solid gather above the capped cavity
_CONE_RISE = 1.25       # cavity cap slope: 51 deg from horizontal
_BASE_SINK = 2.0        # how far a head's base sinks into the gather
_DRAIN_R = 2.2          # drain from a ring bloom into the body
_WIND_BUDGET = 0.22     # dr/dz a petal spiral may spend

_CHAMBER_RISE = 1.30    # the chamber's tent roof: 52 deg, a 38 deg overhang
_CHAMBER_DECK = 1.6     # deck left under the blooms, in wall thicknesses
_CHAMBER_MIN_H = 8.0    # not worth a void below this
_CHAMBER_MIN_W = 4.0    # ... nor below this: the slicer would just fill it
_VENT_R = 2.4           # the chamber's own drain, down into the body

#: (height fraction, radius fraction) up one bloom.  Both open upward so
#: the outside of the cup supports itself; the tulip flares to a wide mouth
#: and the rose closes back over into a bud.
_SHAPES: dict[str, dict] = {
    "tulip": dict(
        profile=[(0.00, 0.34), (0.25, 0.62), (0.58, 0.90),
                 (0.80, 1.00), (1.00, 0.94)],
        petals=6, amp=0.13, wind=0.0, tips=True,
    ),
    "rose": dict(
        profile=[(0.00, 0.46), (0.30, 0.80), (0.58, 1.00),
                 (0.80, 0.95), (1.00, 0.74)],
        petals=7, amp=0.10, wind=0.55, tips=False,
    ),
}


class _PetalSection(Section):
    """A circle scalloped into petals: ``r * (1 + amp * cos(n * theta))``.

    ``wind`` turns the scallop as it rises - a rose's petals spiral, a
    tulip's do not.  The wind is deliberately gentle: it adds
    ``r * amp * n * dtheta/dz`` to the vertical gradient, and that lands in
    the same overhang budget as the cup's flare.
    """

    def __init__(self, params: PotParams, petals: int, amp: float,
                 wind_per_mm: float = 0.0):
        super().__init__(params)
        self.petals, self.amp, self.wind = petals, amp, wind_per_mm

    def _theta_count(self) -> int:
        return max(96, int(self.petals) * 16)

    def _shape_radius(self, theta, z, r, decorate):
        phase = self.petals * (theta + self.wind * z)
        return r * (1.0 + self.amp * np.cos(phase))


def _profile_radius(kind: str, r: float, h: float, z_local: float,
                    base_frac: float | None = None) -> float:
    """Outside radius of a cup at ``z_local``, petal bulge included."""
    spec = _SHAPES[kind]
    pts = spec["profile"]
    t = min(max(z_local / max(h, 1e-9), 0.0), 1.0)
    rf = pts[-1][1]
    for (t0, f0), (t1, f1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            if base_frac is not None:
                f0, f1 = max(f0, base_frac), max(f1, base_frac)
            rf = f0 + (f1 - f0) * (t - t0) / max(t1 - t0, 1e-9)
            break
    return r * rf * (1.0 + spec["amp"])


def _closing_fraction(kind: str) -> float:
    """Height fraction where a cup stops opening out and starts closing
    over - the point past which it can roof a gap with its neighbour."""
    pts = _SHAPES[kind]["profile"]
    return max(pts, key=lambda tf: tf[1])[0]


def _nominal_head_radius(p: PotParams) -> float:
    if p.bouquet_head_diameter > 0:
        return p.bouquet_head_diameter / 2.0
    return min(30.0, max(9.0, 0.32 * p.top_radius))


def plan(p: PotParams) -> dict:
    """Size and place the blooms so no two of them roof over each other.

    Two cups that both flare upward meet in a *valley*, and a valley drains
    to the sky - it prints.  The trouble starts where one cup has begun to
    close over while its neighbour is still opening: the pair bridge the gap
    between them and the bridge faces down.  So rather than guess at a
    spacing, walk both silhouettes and demand real clearance at every height
    above the merge zone, and shrink the blooms until the ring fits on the
    shoulder with that clearance.
    """
    kind = p.bouquet_flower
    n = max(1, int(p.bouquet_count))
    tilt = min(p.bouquet_tilt, 18.0)
    lean = math.tan(math.radians(tilt))
    gather = gather_radius(p)
    r = _nominal_head_radius(p)

    for _ in range(14):
        h = r * 3.0
        rc, hc, cfrac = center_ring(p)
        # the ring stands outside the collar's own foot, on solid shoulder
        frac = _base_frac(p, kind, r, _DRAIN_R + 1.3)
        foot = frac * r * (1.0 + _SHAPES[kind]["amp"])
        # ... and inside the mouth, for the same reason: measure with the
        # real foot, petal bulge included, not a fraction of the radius.
        # The foot sinks below the top, and down there the cavity has not
        # finished coning in yet - so clear the cone at THAT depth, not the
        # throat at the surface
        sink = _BASE_SINK + 3.0
        under = throat_radius(p) + sink / _CONE_RISE
        lo = max(rc * cfrac if rc else 0.0, under) + foot
        # the foot sinks into the shoulder, so measure the wall down there:
        # a bloom perched over the rim's edge has nothing under half of it
        from .profile import wall_radius
        hi = wall_radius(p, p.height - _BASE_SINK - 3.0) - foot - 1.0

        # Where both surfaces are still opening out they meet in a valley,
        # and a valley drains to the sky - blooms may overlap all they like
        # down there, which is exactly the gathered look.  Clearance is only
        # demanded from the height where one of them starts closing over,
        # because that is what roofs the gap between them.
        t_ring = _closing_fraction(kind)
        need = lo
        for i in range(41):
            zl = h * (0.30 + 0.70 * i / 40.0)
            ring = _profile_radius(kind, r, h, zl, frac)
            axis_gain = zl * lean
            closing = zl >= t_ring * h
            if rc and zl <= hc:                      # clear the collar
                if closing or zl >= t_ring * hc:
                    mid = _profile_radius(kind, rc, hc, zl, cfrac)
                    need = max(need, mid + ring + 1.2 - axis_gain)
            if n > 1:                                # ... and each other
                need = max(need, (ring + 0.8) / math.sin(math.pi / n)
                           - axis_gain)
        if need <= hi or r <= 9.0:
            break
        r *= 0.93

    rc, hc, cfrac = center_ring(p)
    return dict(r=r, h=r * 3.0, rc=rc, hc=hc, cfrac=cfrac,
                r_base=min(max(need, lo), max(hi, lo)), tilt=tilt, n=n)


def head_radius(p: PotParams) -> float:
    """Radius of one bloom in the ring."""
    return plan(p)["r"]


def head_height(p: PotParams) -> float:
    return plan(p)["h"]


def center_radius(p: PotParams) -> float:
    """Radius of the flared collar that forms the mouth."""
    return plan(p)["rc"]


def gather_radius(p: PotParams) -> float:
    """Outer radius of the neck the blooms stand on."""
    from .profile import wall_radius
    return wall_radius(p, p.height)


def _base_frac(p: PotParams, kind: str, r: float, need_inner: float) -> float:
    """Radius fraction of a cup's foot.

    The shape's own foot is slender, which looks right but leaves a throat
    barely wider than the wall.  Where a cup has to pass something - the
    pot's mouth, or a drain - the foot is widened until it can.
    """
    wall = min(p.wall_thickness, 0.30 * r)
    return max(_SHAPES[kind]["profile"][0][1], (need_inner + wall) / r)


def throat_radius(p: PotParams) -> float:
    """Inside radius of the pot's mouth, where the cavity comes through.

    Wide on purpose: this is what you plant in, and every millimetre the
    cavity has to cone in below it is another millimetre of solid shoulder
    to print.  The ring of blooms stands on that shoulder, around it.
    """
    return max(6.0, 0.38 * gather_radius(p))


def center_ring(p: PotParams) -> tuple[float, float, float]:
    """(radius, height, base fraction) of the flared collar around the mouth.

    Not a cup on a stem - at this throat a bloom slender enough to look like
    one would have to be wider than the pot.  It is the mouth itself opening
    into a scalloped flower.
    """
    throat = throat_radius(p)
    wall = min(p.wall_thickness, 4.0)
    # the collar's cavity is scalloped, so its NARROWEST point is what has
    # to match the throat - size the foot off that, or the pinch between
    # petals leaves a lip of collar hanging over the mouth
    inner = throat / (1.0 - _SHAPES[p.bouquet_flower]["amp"])
    base = inner + wall
    # a low, barely-flared lip: every millimetre it spreads is a millimetre
    # of shoulder the ring of blooms does not get
    rc = base / 0.90
    return rc, rc * 0.62, base / rc


def check_bouquet_fit(p: PotParams) -> None:
    """A bouquet needs a mouth to stand on.  Narrow-necked silhouettes
    cannot carry one, and squeezing the blooms in until they fit produces
    buds the size of peas - so say so instead."""
    need = 0.55 * p.top_radius
    if gather_radius(p) < need:
        raise ParameterError(
            f"a {p.vase_profile!r} vase gathers to "
            f"{2 * gather_radius(p):.0f} mm at the mouth, too narrow to ring "
            f"with blooms - use the default silhouette (a trumpet, which "
            f"opens back out) or one at least {2 * need:.0f} mm across the top"
        )


def gather_radius(p: PotParams) -> float:
    """Outer radius of the neck the blooms stand on."""
    from .profile import wall_radius
    return wall_radius(p, p.height)


def cavity_cone(p: PotParams) -> tuple[float, float, float, float]:
    """``(r0, z0, throat, z_top)`` of the cone that necks the cavity in.

    The cavity climbs the wall as usual, then at ``z0`` starts coning in at
    ``_CONE_RISE`` until it is the middle bloom's throat at the top.  Where
    that cone starts depends on how wide the wall is there, which depends on
    where it starts - so solve it, the same way :func:`cavity_cap_rings` does.
    """
    from .profile import wall_cavity_radius
    throat = throat_radius(p)
    z_top = p.height
    z0 = z_top - _CONE_RISE * max(wall_cavity_radius(p, z_top) - throat, 1.0)
    for _ in range(3):
        z0 = z_top - _CONE_RISE * max(wall_cavity_radius(p, z0) - throat, 1.0)
    return wall_cavity_radius(p, z0), z0, throat, z_top


def _section_min_factor(p: PotParams) -> float:
    """Smallest radius the cross-section reaches, per unit nominal radius.

    A hexagon's flats sit inside its corners and a rib's groove inside its
    crest; a *round* void carved in the wall has to clear whichever is
    nearest the axis, or it opens out through the side of the pot.
    """
    from .sections import make_section
    section = make_section(p)
    theta = section.thetas()
    lo = 1.0
    _, _, _, z_top = cavity_cone(p)
    for i in range(5):
        z = z_top - 40.0 * i / 4.0
        x, y = section.xy(theta, z, 1.0, True)
        lo = min(lo, float(np.min(np.hypot(x, y))))
    return max(0.2, lo)


def shoulder_chamber(p: PotParams) -> dict | None:
    """A void carved inside the shoulder, or ``None`` if there is no room.

    The shoulder - the ring of solid between the cavity's cone and the deck
    the blooms stand on - is the heaviest thing in the model, because the
    cone can only close at 52 degrees and everything above it has to be
    filled.  Most of that fill does nothing.

    What stops us simply hollowing it is that the deck would then be a
    horizontal ceiling over a void, and a ceiling does not print.  So the
    void is a *tent*: an annular chamber whose roof rises to a ridge at
    ``_CHAMBER_RISE`` from both sides, tucked one deck under the top and one
    skin over the cone.  Both roof faces lean 38 degrees, the same budget
    every other overhang in this model is charged against, and the chamber
    tapers to a point at the bottom, which is a valley and prints.

    The ridge radius is chosen by measurement, not by rule: the roof and the
    cone under it are very nearly parallel, so where the ridge sits decides
    how much of the shoulder is reachable at all.  Sweep it and keep the
    best.
    """
    from .profile import wall_radius, wall_slope
    r0, z0, throat, z_top = cavity_cone(p)
    deck = max(4.0, _CHAMBER_DECK * p.wall_thickness)
    skin = max(3.0, p.wall_thickness)
    z_apex = z_top - deck
    if z_apex <= z0 + _CHAMBER_MIN_H:
        return None

    gmin = _section_min_factor(p)

    def r_limit(z: float) -> float:
        """As far out as a round void may go and still leave a wall."""
        slope = wall_slope(p, z)
        relief = p.texture_depth if p.surface_texture != "none" else 0.0
        return (wall_radius(p, z) * gmin - relief
                - p.wall_thickness * math.sqrt(1.0 + slope * slope))

    # the cone's own skin, measured perpendicular to it
    drop = 1.0 / _CONE_RISE
    off = skin * math.sqrt(1.0 + drop * drop)
    # ... and the collar's cavity, which hangs down inside the neck
    amp = _SHAPES[p.bouquet_flower]["amp"]
    r_neck = throat * (1.0 + amp) / (1.0 - amp) + skin

    def r_floor(z: float) -> float:
        cone = r0 + (throat - r0) * (z - z0) / (z_top - z0)
        return max(min(cone, r0) + off, r_neck)

    k = 1.0 / _CHAMBER_RISE
    step = 0.5
    zs = [z0 + step * i for i in range(int((z_apex - z0) / step) + 1)]

    def walls(apex: float):
        out = []
        for z in zs:
            spread = k * (z_apex - z)
            out.append((max(r_floor(z), apex - spread),
                        min(r_limit(z), apex + spread)))
        return out

    # each pocket is emptied by the drain of the bloom above it, so a ridge
    # that puts the void out of the drain's way is no use however big it is
    r_drain = plan(p)["r_base"]

    def pierced(w) -> float:
        return step * sum(1 for ri, ro in w if ri < r_drain < ro)

    best, best_v = None, 0.0
    hi = r_limit(z_apex)
    for i in range(61):
        apex = throat + (hi - throat) * i / 60.0
        w = walls(apex)
        if pierced(w) < 3.0:
            continue
        v = sum(math.pi * (ro * ro - ri * ri) * step
                for ri, ro in w if ro > ri)
        if v > best_v:
            best, best_v = apex, v
    if best is None:
        return None

    w = walls(best)
    live = [i for i, (ri, ro) in enumerate(w) if ro - ri > 1e-9]
    if not live:
        return None
    z_lo, z_hi = zs[live[0]], zs[live[-1]]
    if (z_hi - z_lo < _CHAMBER_MIN_H
            or max(ro - ri for ri, ro in w) < _CHAMBER_MIN_W):
        return None

    return dict(apex=best, z_apex=z_apex, z_lo=z_lo, z_hi=z_hi,
                spread=k, r_floor=r_floor, r_limit=r_limit,
                volume=best_v, z0=z0, r0=r0, throat=throat, z_top=z_top)


def chamber_bounds(ch: dict, z: float) -> tuple[float, float]:
    """``(inner, outer)`` radius of the chamber at height ``z``."""
    spread = ch["spread"] * (ch["z_apex"] - z)
    return (max(ch["r_floor"](z), ch["apex"] - spread),
            min(ch["r_limit"](z), ch["apex"] + spread))


def chamber_span_at(ch: dict, radius: float) -> tuple[float, float] | None:
    """The height band the chamber occupies at ``radius``, if any."""
    lo = hi = None
    n = 200
    for i in range(n + 1):
        z = ch["z_lo"] + (ch["z_hi"] - ch["z_lo"]) * i / n
        ri, ro = chamber_bounds(ch, z)
        if ri < radius < ro:
            lo = z if lo is None else lo
            hi = z
    if lo is None or hi - lo < 2.0:
        return None
    return lo, hi


def _chamber_cutters(p: PotParams, ch: dict, azimuths: list[float]
                     ) -> list[trimesh.Trimesh]:
    """The chamber, cut into one pocket per bloom.

    The void is built as the difference of two lathes - an outer surface and
    an inner one that overtake each other above the ridge and below the
    point, so it closes at both ends without leaving a coplanar sliver.

    Left as one ring it would be a gallery, and a gallery is a tunnel: it
    would hang an extra handle off the pot and pool water at whichever
    radius the floor is lowest.  Radial ribs at the midpoints between blooms
    cut it into pockets instead - one per bloom, each one pierced by that
    bloom's own drain, which passes through on its way to the body.  So each
    pocket empties into the pot exactly the way the pocket above it does,
    the ribs carry the deck where the blooms actually stand, and the handle
    count is unchanged.
    """
    section = Section(p.with_(surface_texture="none"))
    rings_in, rings_out = [], []
    lo, hi = ch["z_lo"] - 2.0, ch["z_hi"] + 2.0
    n = max(24, int((hi - lo) / 0.6))
    for i in range(n + 1):
        z = lo + (hi - lo) * i / n
        ri, ro = chamber_bounds(ch, z)
        rings_in.append((max(ri, 0.5), z))
        rings_out.append((max(ro, 0.4), z))
    shell = _boolean("difference", [lathe(rings_out, section, decorate=False),
                                    lathe(rings_in, section, decorate=False)])

    if len(azimuths) < 2:
        return [shell]
    rib = max(3.0, p.wall_thickness)
    reach = 2.0 * ch["r_limit"](ch["z_apex"]) + 10.0
    step = 2.0 * math.pi / len(azimuths)
    walls = []
    for a in azimuths:
        mid = a + 0.5 * step
        box = trimesh.creation.box(extents=(reach, rib, (hi - lo) + 10.0))
        box.apply_transform(trimesh.transformations.rotation_matrix(
            mid, [0, 0, 1]))
        box.apply_translation((0.5 * reach * math.cos(mid),
                               0.5 * reach * math.sin(mid),
                               0.5 * (lo + hi)))
        walls.append(box)
    return [_boolean("difference", [shell] + walls)]


def cavity_cap_rings(p: PotParams) -> list[tuple[float, float]]:
    """Rings that neck the vessel's cavity into the middle bloom's throat.

    A cone, not a dome: this is the *ceiling* of the interior under the
    shoulder, so it rises at ``_CONE_RISE`` (about 52 degrees from
    horizontal, a 38 degree overhang) and the shoulder above it - the ring
    blooms' footing - is solid all the way across.
    """
    r0, z0, throat, z_top = cavity_cone(p)
    # overshoot the top: the middle bloom's own cavity starts just below it,
    # and two cutters that merely touch leave coplanar slivers behind
    return [(r0, z0), (throat, z_top), (throat, z_top + 1.5)]


def head_placements(p: PotParams) -> list[tuple[float, float, float, float]]:
    """(azimuth, base radius, tilt degrees, scale) per bloom.

    The ring leans outward so the blooms open away from each other; the
    centre bloom stands straight and a little taller, the way the middle of
    a bunch does.
    """
    pl = plan(p)
    return [(2.0 * math.pi * k / pl["n"], pl["r_base"], pl["tilt"], 1.0)
            for k in range(pl["n"])]


def _cup(p: PotParams, kind: str, r: float, h: float, shrink: float,
         z_extra: float, base_frac: float | None = None) -> trimesh.Trimesh:
    """One cup as a lathe: ``shrink`` mm off the wall makes the cavity,
    ``z_extra`` extends it below the base so the bore can meet it."""
    spec = _SHAPES[kind]
    # the spiral's gradient is r * amp * petals * (dtheta/dz), which grows
    # with the cup's radius and shrinks with its height - unbounded, it is
    # the widest shallow cup that blows the overhang budget, not the tallest
    wind = spec["wind"] * 2.0 / max(h, 1e-9)
    if spec["wind"] and spec["amp"] and spec["petals"]:
        wind = min(wind, _WIND_BUDGET / (r * spec["amp"] * spec["petals"]))
    section = _PetalSection(p.with_(surface_texture="none"), spec["petals"],
                            spec["amp"], wind)
    rings = []
    for zf, rf in spec["profile"]:
        if base_frac is not None:
            rf = max(rf, base_frac)
        rr = max(0.6, r * rf - shrink)
        rings.append((rr, zf * h))
    if z_extra > 0.0:                      # straight skirt below the base
        rings = [(rings[0][0], -z_extra)] + rings
    if shrink > 0.0:
        # the cavity has to break out through the top, so the cutter
        # overshoots - but a cutter that ends in a flat disc leaves a
        # ceiling wherever that disc happens to land inside something, and
        # a bloom leaning in over the collar's mouth is exactly such a
        # somewhere.  Close the overshoot with a cone instead: worst case
        # it bores a cone-topped hole, which prints.
        top = rings[-1][0]
        rings = rings[:-1] + [(top, h + 0.4),
                              (0.02, h + 0.4 + top * 1.3)]
    return lathe(resample(rings, 1.2), section, decorate=False)


def _vee(radius: float, apex_z: float, x: float, y: float,
         rise: float = 1.35) -> trimesh.Trimesh:
    """A cone standing on its point: cut it out and the notch it leaves has
    sloping walls.  A ball would leave the underside of its own curve
    hanging over the gap."""
    cone = trimesh.creation.cone(radius=radius, height=radius * rise,
                                 sections=32)
    cone.apply_transform(trimesh.transformations.rotation_matrix(
        math.pi, [1, 0, 0]))                      # apex down, mouth up
    cone.apply_translation((x, y, apex_z + radius * rise))
    return cone


def _spike(radius: float, base_z: float, x: float, y: float,
           rise: float = 1.3) -> trimesh.Trimesh:
    """A cone standing upright, apex up: it caps a bore so the hole narrows
    to nothing instead of ending in a flat ceiling."""
    cone = trimesh.creation.cone(radius=radius, height=radius * rise,
                                 sections=32)
    cone.apply_translation((x, y, base_z))
    return cone


def _tip_cutters(p: PotParams, kind: str, r: float, h: float
                 ) -> list[trimesh.Trimesh]:
    """Scoop a V between petals at the rim, so the tips come to points."""
    spec = _SHAPES[kind]
    if not spec["tips"]:
        return []
    n = spec["petals"]
    notch = max(2.0, 0.52 * math.pi * r / n)
    return [_vee(notch, h - notch * 0.30,
                 r * 1.02 * math.cos(2.0 * math.pi * (k + 0.5) / n),
                 r * 1.02 * math.sin(2.0 * math.pi * (k + 0.5) / n))
            for k in range(n)]


def bouquet_parts(p: PotParams
                  ) -> tuple[list[trimesh.Trimesh], list[trimesh.Trimesh]]:
    """(solids, cutters) for the blooms, in vessel coordinates."""
    kind = p.bouquet_flower
    pl = plan(p)
    solids: list[trimesh.Trimesh] = []
    cutters: list[trimesh.Trimesh] = []

    def place(mesh, azim, r_base, tilt, z):
        mesh.apply_transform(trimesh.transformations.rotation_matrix(
            math.radians(tilt), [0, 1, 0]))
        mesh.apply_transform(trimesh.transformations.rotation_matrix(
            azim, [0, 0, 1]))
        mesh.apply_translation((r_base * math.cos(azim),
                                r_base * math.sin(azim), z))
        return mesh

    # -- the middle bloom: the mouth, standing on the neck ----------------
    # -- the mouth: a scalloped collar flaring out of the neck ------------
    rc, hc = pl["rc"], pl["hc"]
    if rc > 0.0:
        wall = min(p.wall_thickness, 0.30 * rc)
        cfrac = pl["cfrac"]
        # no petal tips on the collar: its notches are wide enough to reach
        # the ring blooms leaning over it, and clipping them leaves the flat
        # top of the notch cutter facing down inside a bloom
        # no skirt: below the neck the cavity is wider than the throat, so
        # anything hanging down from the bloom would hang over the void
        solids.append(place(_cup(p, kind, rc, hc, 0.0, 0.0, cfrac),
                            0.0, 0.0, 0.0, p.height))

        # its cavity runs down past the vessel's cap rings, which have
        # already coned in to exactly this throat
        cutters.append(place(_cup(p, kind, rc, hc, wall, 8.0, cfrac),
                             0.0, 0.0, 0.0, p.height))

    # -- the shoulder: solid where it has to be, hollow where it can be ---
    chamber = shoulder_chamber(p)
    placements = head_placements(p)
    if chamber is not None:
        cutters += _chamber_cutters(p, chamber,
                                    [a for a, _, _, _ in placements])

    # -- the ring: pockets on the shoulder, each with a drain -------------
    r0, h0 = pl["r"], pl["h"]
    z_base = p.height - _BASE_SINK
    for azim, r_base, tilt, scale in placements:
        r, h = r0 * scale, h0 * scale
        wall = min(p.wall_thickness, 0.30 * r)
        frac = _base_frac(p, kind, r, _DRAIN_R + 1.3)
        solids.append(place(_cup(p, kind, r, h, 0.0, _BASE_SINK + 3.0, frac),
                            azim, r_base, tilt, z_base))
        for cut in _tip_cutters(p, kind, r, h):
            cutters.append(place(cut, azim, r_base, tilt, z_base))
        cutters.append(place(_cup(p, kind, r, h, wall, 0.0, frac),
                             azim, r_base, tilt, z_base))

        # a drain, not a doorway: a hole sized to pass soil would cut the
        # bloom off the shoulder it stands on.  Water finds its way down to
        # the body, which drains as any pot does.
        drain_r = _DRAIN_R
        if drain_r > 0.8:
            x, y = r_base * math.cos(azim), r_base * math.sin(azim)
            # it runs all the way to the body, straight through the hollow
            # pocket in the shoulder on the way - which is what empties the
            # pocket too
            shaft = trimesh.creation.cylinder(radius=drain_r, height=50.0,
                                              sections=32)
            shaft.apply_translation((x, y, z_base - 25.0))
            cutters.append(shaft)
            # cone the top: a flat-topped bore ends in a ceiling inside the
            # bloom, where the cup's throat is still narrower than the bore
            cutters.append(_spike(drain_r, z_base, x, y))
    return solids, cutters
