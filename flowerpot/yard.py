"""Yard art: a plant with a face and an opinion.

A sunflower, a daisy or a saguaro, with eyes, eyebrows and a pair of arms
that can be told what to do with themselves.  It snaps onto a trailer ball
(see :mod:`flowerpot.hitch`), screws onto the collar, or stands on a plain
disc for a shelf.

Why the flower comes apart
--------------------------
A flower head facing you is a *vertical disc*, and a vertical disc cannot
print without supports however you slice it: the bottom of its rim faces
straight down, and so does the underside of every petal pointing sideways.
Leaning it back far enough to fix that leaves the flower staring at the sky.

So the head is its own part and it prints **lying flat, face up**.  That
turns the problem into the feature - every bit of the face becomes a *top*
surface, which is the best detail an FDM machine can produce and no
overhang at all - and it splits the model along its colour lines.  Green
body, yellow petals, brown face: a single-material printer gets a
three-colour object out of three prints and no paint.

The saguaro stays in one piece, because a cactus is one colour anyway, and
its face is carved instead.  Carving upright has a rule, and it is strict:

    on a standing wall, every mark must be **taller than it is wide**.

A pocket wider than it is tall has a horizontal roof; a bump wider than it
is tall has a horizontal underside.  There is no angle you can set a long
bar at to escape it either - tilting only moves where its ends roof
themselves.  So the cactus has no eyebrows.  It scowls with its eyes, which
are tall lenses tilted inward, and its mouth is a row of separate slits -
gritted teeth, and every one of them legal.

The arms
--------
An arm is a stack of horizontal rings drifting sideways as it climbs (see
:func:`flowerpot.stem._tube`), so its underside lean is exactly the
centreline's lateral slope - keep that inside the budget and the whole arm
prints in mid air with nothing beneath it.  That is the real reason the
arms go up and out rather than straight out: not style, arithmetic.  Hands
are teardrops for the same reason, and fingers are tubes, the one shape
that is always happy pointing at the sky.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh

from .build import _boolean, _finish, _prism, lathe
from .params import ParameterError, PotParams
from .profile import slope_budget
from .sections import Section
from .stem import _leaf, _tube

#: What can be grown.
PLANTS = ("sunflower", "daisy", "cactus")

#: Expressions.
FACES = ("angry", "smug", "grin", "sideeye", "none")

#: What a hand can be caught doing.
GESTURES = ("bird", "fist", "thumbs", "peace", "horns", "wave", "shrug",
            "none")

_ARM_SLOPE = 0.88       # max dr/dz of an arm's centreline (49 deg from flat)
_FINGER_LEAN = 0.30     # ... and of a finger, which stands much straighter
_TEAR = 1.30            # dz/dr of the cone under a hand: 52 deg
_TAB_CLEAR = 0.35       # slot clearance per side on the head joint
_PETAL_GAP = 34.0       # degrees of petal left out at the bottom, for the neck
_CACTUS_TILT = 11.0     # cap on an eye's lean: see lens_aspect()
_CARVE_RESERVE = 3.5    # degrees held back on a carved cusp
_TRUNK_FLARE = 1.22     # how much wider the body is at its foot
_SHOULDER = 1.30        # shoulder radius, in wrist radii
_EASE = 1.20            # peak/average lateral slope of an arm's easing curve
_FIST = 2.35            # fist radius, in wrist radii
_FINGER_TIP = 10.5      # where a fingertip lands above the wrist, same units

#: brow tilt, eye scale, pupil shift, mouth bend and width, per expression.
_EXPRESSION = {
    "angry":   dict(brow=-27.0, eye=1.00, pupil=(0.00, -0.22), bend=-0.34,
                    wide=0.80, tilt=26.0),
    "smug":    dict(brow=-11.0, eye=0.88, pupil=(0.30, 0.10), bend=0.30,
                    wide=0.62, tilt=13.0),
    "grin":    dict(brow=9.0, eye=1.06, pupil=(0.00, 0.04), bend=0.46,
                    wide=0.88, tilt=-8.0),
    "sideeye": dict(brow=-5.0, eye=0.96, pupil=(0.46, 0.06), bend=-0.10,
                    wide=0.64, tilt=6.0),
}

#: ``(offset across the fist, length scale)`` per raised finger.
_HAND = {
    "bird": [(0.00, 1.00)],
    "fist": [],
    "thumbs": [(0.58, 0.72)],
    "peace": [(-0.38, 0.92), (0.38, 0.92)],
    "horns": [(-0.62, 0.86), (0.62, 0.86)],
    "wave": [(-0.64, 0.70), (-0.21, 0.88), (0.21, 0.88), (0.64, 0.70)],
    "shrug": [(-0.64, 0.66), (-0.21, 0.80), (0.21, 0.80), (0.64, 0.66)],
}


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------
def _round(p: PotParams) -> Section:
    return Section(p.with_(surface_texture="none"))


def head_diameter(p: PotParams) -> float:
    """Sized from the room the plant actually has.

    Measuring off ``yard_height`` alone would give a fused socket - which
    can eat five centimetres before the plant starts - the same head as a
    plant standing on a disc, and squash everything above it.
    """
    if p.yard_head_diameter > 0.0:
        return float(p.yard_head_diameter)
    return 0.78 * max(p.yard_height - mount_top(p), 40.0)


def face_disc_radius(p: PotParams) -> float:
    """The brown middle - big on a sunflower, a button on a daisy."""
    return (0.26 if p.yard_plant == "sunflower" else 0.16) * head_diameter(p)


def petal_count(p: PotParams) -> int:
    return 13 if p.yard_plant == "sunflower" else 17


def mount_top(p: PotParams) -> float:
    """Height the plant itself starts at, above whatever holds it down."""
    if p.hitch_mount == "fused":
        from .hitch import solve
        return solve(p)["z_apex"]
    if p.hitch_mount == "screw":
        from .hitch import cap_clear_z
        return cap_clear_z(p) + 3.0
    return 9.0                                  # the plain disc base


def plan(p: PotParams) -> dict:
    """Every height and radius the character hangs off."""
    if p.yard_plant not in PLANTS:
        raise ParameterError(
            f"unknown yard_plant {p.yard_plant!r}; choose from {list(PLANTS)}")
    d = head_diameter(p)
    top = float(p.yard_height)
    z_mount = mount_top(p)
    thick = max(6.0, 0.062 * d)
    tab_w = min(40.0, max(20.0, 0.26 * d))

    if p.yard_plant == "cactus":
        r_trunk = max(13.0, 0.140 * top)
        hub_r = 0.0
        z_head = z_mount + 0.66 * (top - z_mount)
        z_pad = top
    else:
        rc = face_disc_radius(p)
        hub_r = rc + 3.0
        # The head's tab drops straight down the middle of the body, and the
        # arms start near the middle too - so they would share the same
        # space.  Push the shoulders behind the head's plane instead (which
        # is where a pair of arms belongs anyway) and widen the body enough
        # to still bury the end cap of each one.
        r_wrist = max(3.8, 0.052 * d)
        y_back = 0.5 * thick + _SHOULDER * r_wrist + 2.0
        r_trunk = max(0.5 * tab_w + 6.0, y_back + _SHOULDER * r_wrist + 4.0)
        z_head = top - 0.5 * d
        z_pad = z_head - hub_r - 2.0

    if z_pad <= z_mount + 14.0:
        need = (z_mount + 14.0 + hub_r + 2.0) / (1.0 - 0.5 * d / max(top, 1.0))
        raise ParameterError(
            f"yard_height {top:.0f} mm leaves no body between the mount (top "
            f"at {z_mount:.0f} mm) and a {d:.0f} mm head - raise yard_height "
            f"to about {need:.0f} mm, or set a smaller yard_head_diameter"
        )
    y_back = 0.0 if p.yard_plant == "cactus" else \
        0.5 * thick + _SHOULDER * max(3.8, 0.052 * d) + 2.0
    # the notch in the petal ring has to be wide enough for the body to come
    # up through it - the tightest point is where the head meets the pad,
    # because that is where the head's own radius is smallest
    gap = _PETAL_GAP
    if p.yard_plant != "cactus":
        gap = max(gap, 3.0 + math.degrees(
            math.atan2(_TRUNK_FLARE * r_trunk + 2.0, hub_r + 2.0)))
    return dict(d=d, top=top, z_mount=z_mount, z_pad=z_pad, z_head=z_head,
                r_trunk=r_trunk, thick=thick, tab_w=tab_w, hub_r=hub_r,
                y_back=y_back, gap=gap)


def check_yard(p: PotParams) -> list[str]:
    """Raise on anything unbuildable; return soft warnings."""
    if p.yard_face not in FACES:
        raise ParameterError(
            f"unknown yard_face {p.yard_face!r}; choose from {list(FACES)}")
    for side in ("yard_left_hand", "yard_right_hand"):
        g = getattr(p, side)
        if g not in GESTURES:
            raise ParameterError(
                f"unknown {side} {g!r}; choose from {list(GESTURES)}")
    if p.hitch_mount not in ("none", "fused", "screw"):
        raise ParameterError(
            "a yard plant mounts 'fused' (socket built in), 'screw' (onto the "
            f"hitch collar) or 'none' (a plain disc); {p.hitch_mount!r} is a "
            f"mount on its own"
        )
    plan(p)
    warn = []
    if p.yard_plant == "cactus" and p.yard_face != "none":
        warn.append(
            "a carved cactus has no eyebrows - a bar wider than it is tall "
            "roofs itself on a standing wall, so the scowl is in the eyes"
        )
    return warn


# ---------------------------------------------------------------------------
# 2D marks, and the two ways of pressing them into a surface
# ---------------------------------------------------------------------------
def _ellipse(w: float, h: float, n: int = 26) -> list[tuple[float, float]]:
    return [(0.5 * w * math.cos(2.0 * math.pi * i / n),
             0.5 * h * math.sin(2.0 * math.pi * i / n)) for i in range(n)]


def lens_aspect(tilt_deg: float, limit_deg: float,
                reserve_deg: float = 2.0) -> float:
    """How tall a vesica has to be to survive being carved into a wall.

    Taller than wide is *not* enough.  A vesica's cusp closes at
    ``arctan((b^2 - a^2) / 2ab)`` from horizontal, and that is the
    shallowest thing on it; tilting the whole mark by ``tilt`` takes the
    same amount straight off one of the two cusps.  Invert it:

        need = tan(limit - reserve + |tilt|),  h/w = need + sqrt(need^2 + 1)

    An untilted mark at a 45 degree limit needs to be 2.4x as tall as it is
    wide.  Lean it 10 degrees and that jumps to 3.5x - which is why the
    cactus squints rather than glares.
    """
    need = math.tan(math.radians(
        min(82.0, max(1.0, 90.0 - limit_deg + reserve_deg + abs(tilt_deg)))))
    return need + math.hypot(need, 1.0)


def _lens(w: float, h: float, aspect: float = 2.5,
          n: int = 18) -> list[tuple[float, float]]:
    """A vesica: two arcs meeting in cusps at the top and the bottom."""
    h = max(h, aspect * w)
    a, b = 0.5 * w, 0.5 * h
    r = (a * a + b * b) / (2.0 * a)              # arc through the cusps
    c = a - r
    phi = math.asin(min(1.0, b / r))
    # sample by arc angle, not by height: even chords, so the segment that
    # lands on the cusp is as close to the true tangent as the rest
    right = [(c + r * math.cos(phi - 2.0 * phi * i / n),
              r * math.sin(phi - 2.0 * phi * i / n)) for i in range(n + 1)]
    return right + [(-x, y) for x, y in reversed(right[1:-1])]


def _rot2(pts, deg: float, dx: float = 0.0, dy: float = 0.0):
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(x * ca - y * sa + dx, x * sa + y * ca + dy) for x, y in pts]


def _stamp(prof, z0: float, z1: float) -> trimesh.Trimesh:
    """A convex outline in the XY plane, extruded along Z.

    Used on the flat parts, where the print axis is the extrusion axis and
    nothing an outline can do makes an overhang.
    """
    m = _prism(prof, z0, z1)
    t = np.eye(4)
    t[:3, :3] = np.array([[0.0, 1.0, 0.0],       # prism (ext, u, v) -> (u, v, ext)
                          [0.0, 0.0, 1.0],
                          [1.0, 0.0, 0.0]])
    m.apply_transform(t)
    return m


def _carve(prof, y0: float, y1: float) -> trimesh.Trimesh:
    """A convex outline in the XZ plane, driven along +Y into a standing
    wall.  Legal only if the outline is taller than it is wide."""
    m = _prism(prof, -y1, -y0)
    m.apply_transform(
        trimesh.transformations.rotation_matrix(-0.5 * math.pi, [0, 0, 1]))
    return m


def _band(points, half: float):
    """A curved stroke, as a chain of convex quads."""
    out = []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        dx, dy = x1 - x0, y1 - y0
        n = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / n * half, dx / n * half
        out.append([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
                    (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)])
    return out


def _mouth_curve(width: float, bend: float, n: int = 9):
    return [(width * (i / n - 0.5),
             bend * width * (2.0 * (i / n - 0.5)) ** 2)
            for i in range(n + 1)]


# ---------------------------------------------------------------------------
# hands and arms
# ---------------------------------------------------------------------------
def _teardrop(p: PotParams, radius: float) -> trimesh.Trimesh:
    """A hand: round on top, coned underneath at the overhang limit."""
    # the cone under it is a straight one on purpose: it has to get from a
    # point to full width over _TEAR radii of rise, so its average slope IS
    # the budget - any curve that bulges would spend more than that
    # somewhere, and the place it would spend it is the tip.
    n = 6
    rings = [(0.03, -_TEAR * radius)]
    for i in range(1, n + 1):
        t = i / n
        rings.append((max(radius * t, 0.05), -_TEAR * radius * (1 - t)))
    for i in range(1, n + 1):
        a = 0.5 * math.pi * i / n
        rings.append((max(radius * math.cos(a), 0.03), 0.88 * radius * math.sin(a)))
    rings[-1] = (0.03, 0.88 * radius)
    return lathe(rings, _round(p), decorate=False)


def _finger(base: np.ndarray, length: float, radius: float,
            lean: float) -> trimesh.Trimesh:
    n = 18
    lean = max(-_FINGER_LEAN, min(_FINGER_LEAN, lean))
    path, radii = [], []
    for i in range(n + 1):
        t = i / n
        z = length * t
        path.append(base + np.array([lean * z, 0.0, z]))
        # a linear tip taper, not a rounded one: a round tip's last
        # millimetre runs out faster than the budget allows, and the taper
        # adds to the lean of a splayed finger rather than replacing it
        radii.append(radius if t < 0.80 else
                     radius * (1.0 - 0.65 * (t - 0.80) / 0.20))
    return _tube(path, radii, nt=28)


def arm_path(p: PotParams, lay: dict, side: int, climb_scale: float = 1.0):
    """Centreline of one arm: out and up, never leaning past the budget.

    The climb is decided first, from where the hand should end up, and the
    reach is then whatever the budget can buy over that climb.  Doing it the
    other way round - pick a reach, climb as far as it takes - is what makes
    an arm shoot up past the top of the head.

    The hand is part of the same ring stack rather than a ball stuck on the
    end, so the arm *swells* into a fist.  That costs budget too: a ring
    stack's underside lean is its lateral slope plus its taper, and the two
    add.  Hence the short straight wrist between them - it spends the
    lateral slope down to nothing before the swell starts.
    """
    cactus = p.yard_plant == "cactus"
    budget = min(_ARM_SLOPE, slope_budget(p, 0.10))
    # start the shoulder well inside the trunk: the tube's end cap faces
    # down, and any of it that pokes out of the body is a flat ceiling
    r0 = 0.16 * lay["r_trunk"]
    if cactus:
        z0 = lay["z_mount"] + 0.16 * (lay["top"] - lay["z_mount"])
        far = 2.7 * lay["r_trunk"]
        r_wrist = 0.34 * lay["r_trunk"]
    else:
        z0 = lay["z_mount"] + 0.08 * (lay["z_pad"] - lay["z_mount"])
        far = 0.66 * lay["d"]                    # clear of the petals
        r_wrist = max(3.8, 0.052 * lay["d"])
    r_fist = _FIST * r_wrist

    # Two things want the climb, and they pull opposite ways: reaching out
    # past the head needs height to spend on the lean, and the fingertips
    # have to stay under the top of the figure.  Take whichever is smaller.
    over = _FINGER_TIP * r_wrist                 # fist plus finger, above the wrist
    climb = climb_scale * max(
        min(lay["top"] - over - z0, _EASE * (far - r0) / budget), 24.0)
    reach = min(far, r0 + budget * climb / _EASE)
    span = max(reach - r0, 6.0)

    n = 24
    r_sh = _SHOULDER * r_wrist
    back = lay["y_back"]
    path, radii = [], []
    for i in range(n + 1):
        t = i / n
        shape = t - (_EASE - 1.0) * math.sin(2.0 * math.pi * t) / (2.0 * math.pi)
        path.append(np.array([side * (r0 + span * min(max(shape, 0.0), 1.0)),
                              -back - 0.08 * span * math.sin(math.pi * t),
                              z0 + climb * t]))
        radii.append(r_sh + (r_wrist - r_sh) * t)

    wrist = 0.55 * r_wrist                       # straight, to spend the lean
    for j in (0.5, 1.0):
        path.append(path[n] + np.array([0.0, 0.0, wrist * j]))
        radii.append(r_wrist)

    swell, dome = 1.9 * r_wrist, 1.05 * r_fist   # the fist
    base = path[-1]
    m = 8
    for j in range(1, m + 1):
        t = j / m
        path.append(base + np.array([0.0, 0.0, swell * t]))
        radii.append(r_wrist + (r_fist - r_wrist) * t)
    knuckle = path[-1]
    for j in range(1, m + 1):                    # over the top: free, it
        t = j / m                                # leans inward as it rises
        path.append(knuckle + np.array([0.0, 0.0, dome * t]))
        radii.append(max(r_fist * math.sqrt(max(1.0 - t * t, 0.0)), 0.05))
    return path, radii, r_wrist


def arm_max_slope(p: PotParams, lay: dict, side: int = 1,
                  climb_scale: float = 1.0) -> float:
    """Steepest underside lean anywhere on an arm.

    A ring stack's underside lean is its centreline's lateral slope plus
    whatever the radius is doing - so both go in, and the dome at the top
    (where the radius *shrinks* as it rises) costs nothing.
    """
    path, radii, _w = arm_path(p, lay, side, climb_scale)
    worst = 0.0
    for (a, ra), (b, rb) in zip(zip(path, radii), zip(path[1:], radii[1:])):
        dz = b[2] - a[2]
        if dz <= 1e-9:
            continue
        lateral = float(np.hypot(b[0] - a[0], b[1] - a[1])) / dz
        worst = max(worst, lateral + max(rb - ra, 0.0) / dz)
    return worst


def _hand(p: PotParams, path, r_wrist: float, gesture: str,
          side: int) -> list[trimesh.Trimesh]:
    """Fingers, standing on the fist the arm already swelled into."""
    r_fist = _FIST * r_wrist
    top = path[-1][2] - 0.75 * 1.05 * r_fist     # inside the dome
    out = []
    for off, scale in _HAND.get(gesture, []):
        base = np.array([path[-1][0] + side * off * r_fist * 0.68,
                         path[-1][1], top])
        out.append(_finger(base, scale * 2.9 * r_fist, 0.44 * r_fist,
                           side * off * 0.36))
    return out


def arms(p: PotParams, lay: dict) -> list[trimesh.Trimesh]:
    out: list[trimesh.Trimesh] = []
    for side, gesture in ((-1, p.yard_left_hand), (1, p.yard_right_hand)):
        if gesture == "none":
            continue
        path, radii, r_wrist = arm_path(
            p, lay, side, 0.62 if gesture == "shrug" else 1.0)
        out.append(_tube(path, radii, nt=36))
        out += _hand(p, path, r_wrist, gesture, side)
    return out


# ---------------------------------------------------------------------------
# the standing part
# ---------------------------------------------------------------------------
def _mount(p: PotParams, lay: dict
           ) -> tuple[list[trimesh.Trimesh], list[trimesh.Trimesh], float]:
    """``(solids, cutters, radius available at the foot of the body)``.

    That last number matters: a body wider than the thing it stands on
    leaves a flat annulus facing straight down, which is the one shape this
    project does not ship.
    """
    foot = _TRUNK_FLARE * lay["r_trunk"]
    if p.hitch_mount == "fused":
        from .hitch import socket_parts
        solids, cutters = socket_parts(p, top_flat=foot)
        return solids, cutters, foot
    if p.hitch_mount == "screw":
        from .hitch import cap_clear_z, cap_socket_cutters, flange_radius
        r = max(flange_radius(p), foot)
        straight = cap_clear_z(p) + 1.5
        plinth = lathe([(r, 0.0), (r, straight),
                        (lay["r_trunk"], straight + 1.15 * (r - lay["r_trunk"]))],
                       _round(p), decorate=False)
        return [plinth], cap_socket_cutters(p, 0.0), r
    r = max(0.38 * lay["d"], lay["r_trunk"] + 12.0)
    disc = lathe([(r, 0.0), (r, 6.0), (r - 3.2, 9.0)], _round(p),
                 decorate=False)
    return [disc], [], r


def _trunk(p: PotParams, lay: dict, foot: float) -> trimesh.Trimesh:
    lo, hi = lay["z_mount"] - 8.0, lay["z_pad"]
    r0 = min(_TRUNK_FLARE * lay["r_trunk"], foot)
    r1 = lay["r_trunk"]
    n = 18
    rings = [(r0 + (r1 - r0) * (i / n), lo + (hi - lo) * (i / n))
             for i in range(n + 1)]
    return lathe(rings, _round(p), decorate=False)


def _head_slot(p: PotParams, lay: dict) -> trimesh.Trimesh:
    """The notch the head's tab drops into - open at the top, so there is
    no roof over it and nothing to bridge."""
    depth = 0.62 * lay["tab_w"]
    box = trimesh.creation.box(extents=(lay["tab_w"] + 2.0 * _TAB_CLEAR,
                                        lay["thick"] + 2.0 * _TAB_CLEAR,
                                        depth + 3.0))
    box.apply_translation((0.0, 0.0, lay["z_pad"] + 1.5 - 0.5 * depth))
    return box


def tab_depth(p: PotParams) -> float:
    return 0.62 * plan(p)["tab_w"]


def build_yard_body(p: PotParams) -> trimesh.Trimesh:
    """The standing part: mount, body, arms and the head joint."""
    check_yard(p)
    lay = plan(p)
    solids, cutters, foot = _mount(p, lay)
    solids = solids + [_cactus_column(p, lay, foot)
                       if p.yard_plant == "cactus" else _trunk(p, lay, foot)]
    solids = solids + arms(p, lay)
    body = _boolean("union", solids)
    cutters = cutters + (_cactus_face(p, lay) if p.yard_plant == "cactus"
                         else [_head_slot(p, lay)])
    if cutters:
        body = _boolean("difference", [body] + cutters)
    return _finish(body, center=False)


# ---------------------------------------------------------------------------
# the cactus
# ---------------------------------------------------------------------------
class _RibSection(Section):
    """A saguaro's flutes: a scalloped radius that does not twist, so it
    adds no vertical gradient at all and costs nothing off the budget."""

    def __init__(self, params: PotParams, ribs: int, amp: float):
        super().__init__(params)
        self.ribs, self.amp = ribs, amp

    def _theta_count(self) -> int:
        return max(int(self.p.segments), 14 * self.ribs)

    def _shape_radius(self, theta, z, r, decorate):
        return r * (1.0 + self.amp * np.cos(self.ribs * theta))


def _cactus_column(p: PotParams, lay: dict, foot: float) -> trimesh.Trimesh:
    r, lo, hi = min(lay["r_trunk"], foot), lay["z_mount"] - 8.0, lay["top"]
    n = 44
    rings = []
    for i in range(n + 1):
        t = i / n
        s = 1.0 + 0.09 * math.sin(math.pi * t) - 0.05 * t
        if t > 0.86:                              # dome the top over
            s *= math.cos(0.5 * math.pi * (t - 0.86) / 0.14) ** 0.5
        rings.append((max(r * s, 0.05), lo + (hi - lo) * t))
    rings[-1] = (0.05, hi)
    return lathe(rings, _RibSection(p.with_(surface_texture="none"), 9, 0.07),
                 decorate=True)


def _cactus_face(p: PotParams, lay: dict) -> list[trimesh.Trimesh]:
    """Tilted lens eyes and a row of gritted slits - every mark taller than
    it is wide, which on a standing wall is the whole of the law."""
    if p.yard_face == "none":
        return []
    e = _EXPRESSION[p.yard_face]
    r, z = lay["r_trunk"], lay["z_head"]
    # into the front face only: a prism that started behind the axis would
    # bore straight out the back of the column
    y0, y1 = r * 0.93 - 0.24 * r, r * 1.07 + 4.0
    out = []

    tilt = max(-_CACTUS_TILT, min(_CACTUS_TILT, e["tilt"]))
    eye_aspect = lens_aspect(tilt, p.overhang_limit_deg, _CARVE_RESERVE)
    eye_w = 0.30 * r * e["eye"]
    for sx in (-1, 1):
        prof = _rot2(_lens(eye_w, eye_aspect * eye_w, eye_aspect),
                     sx * tilt, sx * 0.46 * r, z + 0.52 * r)
        out.append(_carve(prof, y0, y1))

    # a row of separate slits, not one wide slot: gritted teeth, and each
    # one tall enough to stand up on its own
    slit_aspect = lens_aspect(0.0, p.overhang_limit_deg, _CARVE_RESERVE)
    slits = 5
    span = e["wide"] * 1.7 * r
    for i in range(slits):
        u = span * (i / (slits - 1) - 0.5)
        v = z - 0.78 * r + e["bend"] * 1.1 * r * (2.0 * u / max(span, 1e-6)) ** 2
        w = 0.17 * r
        out.append(_carve(_rot2(_lens(w, slit_aspect * w, slit_aspect),
                                0.0, u, v), y0, y1))
    return out


# ---------------------------------------------------------------------------
# the flower head - printed flat, face up
# ---------------------------------------------------------------------------
def _flat(mesh: trimesh.Trimesh, size: float = 600.0) -> trimesh.Trimesh:
    """Keep only what is above z = 0, so the part has a flat bed face."""
    box = trimesh.creation.box(extents=(size, size, size))
    box.apply_translation((0.0, 0.0, 0.5 * size))
    return _boolean("intersection", [mesh, box])


def build_yard_head(p: PotParams) -> trimesh.Trimesh:
    """The petal ring, lying flat - print it face up in the petal colour."""
    check_yard(p)
    if p.yard_plant == "cactus":
        raise ParameterError("a cactus has no separate head")
    lay = plan(p)
    d, th, rc = lay["d"], lay["thick"], face_disc_radius(p)
    n = petal_count(p)
    # the petals reach in past the hub so they read as a ring of petals
    # rather than a scalloped edge
    petal_len = 0.5 * d - 0.55 * rc
    ring_r = 0.5 * d - 0.5 * petal_len
    fat = 0.62 if p.yard_plant == "sunflower" else 0.40
    petal_w = min(fat * petal_len, 2.0 * math.pi * ring_r / n * 1.45)

    parts = []
    gap = math.radians(lay["gap"])
    for i in range(n):
        a = -0.5 * math.pi + 2.0 * math.pi * (i + 0.5) / n
        off = math.atan2(math.sin(a + 0.5 * math.pi), math.cos(a + 0.5 * math.pi))
        if abs(off) < gap:
            continue                              # room for the neck
        petal = _leaf(petal_len, petal_w,
                      th * (2.0 if p.yard_plant == "sunflower" else 1.7))
        petal.apply_transform(trimesh.transformations.rotation_matrix(
            0.5 * math.pi, [1, 0, 0]))            # length +z -> -y
        petal.apply_transform(trimesh.transformations.rotation_matrix(
            a + 0.5 * math.pi, [0, 0, 1]))
        petal.apply_translation((ring_r * math.cos(a), ring_r * math.sin(a), 0.0))
        parts.append(petal)

    hub_r = lay["hub_r"]
    rings = [(hub_r, 0.0)]
    for i in range(1, 15):
        t = i / 14.0
        rings.append((max(hub_r * math.cos(0.5 * math.pi * t) ** 0.5, 0.05),
                      1.15 * th * math.sin(0.5 * math.pi * t)))
    rings[-1] = (0.05, 1.15 * th)
    parts.append(lathe(rings, _round(p), decorate=False))

    tab_len = tab_depth(p) + 2.0
    tab = trimesh.creation.box(extents=(lay["tab_w"], tab_len, th))
    tab.apply_translation((0.0, -(hub_r + 2.0) - 0.5 * tab_len + 8.0, 0.5 * th))
    parts.append(tab)

    head = _flat(_boolean("union", parts))
    return _finish(_boolean("difference", [head, _face_pocket(p, lay)]),
                   center=False)


def head_pose(p: PotParams) -> np.ndarray:
    """Transform that stands a flat-printed head up on its body.

    Only previews and the fit tests need it - what you print is the part as
    built, lying down.  Mapping the head's own "up" to +Z *and* its face to
    +Y is a swap of two axes, so it flips the third: the assembled figure
    wears its expression mirrored, which is why nothing here depends on a
    left and a right.
    """
    lay = plan(p)
    m = (trimesh.transformations.rotation_matrix(-0.5 * math.pi, [1, 0, 0])
         @ trimesh.transformations.rotation_matrix(math.pi, [0, 0, 1]))
    m[1, 3] = -0.5 * lay["thick"]                # straddle the body's mid-plane
    m[2, 3] = lay["z_head"]
    return m


def _face_pocket(p: PotParams, lay: dict) -> trimesh.Trimesh:
    rc = face_disc_radius(p)
    floor = 0.45 * lay["thick"]
    return lathe([(rc + 0.22, floor), (rc + 0.22, 8.0 * lay["thick"])],
                 _round(p), decorate=False)


def build_yard_face(p: PotParams) -> trimesh.Trimesh:
    """The middle disc with the face on it - flat, face up, third colour."""
    check_yard(p)
    if p.yard_plant == "cactus":
        raise ParameterError("a cactus wears its face carved, not as a part")
    lay = plan(p)
    rc, th = face_disc_radius(p), lay["thick"]
    plug = 0.45 * th                              # sits in the head's pocket
    rim = 0.28 * th                               # rounded edge, then flat

    rings = [(rc, 0.0), (rc, plug)]
    n = 10
    for i in range(1, n + 1):
        a = 0.5 * math.pi * i / n
        rings.append((rc - rim * (1.0 - math.cos(a)), plug + rim * math.sin(a)))
    rings.append((0.02, plug + rim))              # a flat face to draw on
    disc = lathe(rings, _round(p), decorate=False)

    seeds = _seeds(p, rc, plug + rim)
    if seeds is not None:
        disc = _boolean("union", [disc, seeds])
    if p.yard_face == "none":
        return _finish(_flat(disc), center=False)
    add, cut = _face_features(p, rc, plug + rim)
    if add:
        disc = _boolean("union", [disc] + add)
    if cut:
        disc = _boolean("difference", [disc] + cut)
    # nothing may hang over the rim: trim the lot back to the disc
    keep = lathe([(rc, -1.0), (rc, plug + rim + 4.0 * th)], _round(p),
                 decorate=False)
    return _finish(_flat(_boolean("intersection", [disc, keep])), center=False)


def _face_features(p: PotParams, rc: float, z_top: float
                   ) -> tuple[list[trimesh.Trimesh], list[trimesh.Trimesh]]:
    """Eyes, brows and a mouth on the flat top of the face disc.

    Printed flat, every one of these is an upward surface, so the shapes
    are free here in a way they are not on the cactus.  A bump is a prism
    that starts under the disc and stops above it; a groove is a prism that
    starts *inside* it and runs away upward.
    """
    e = _EXPRESSION[p.yard_face]
    add: list[trimesh.Trimesh] = []
    cut: list[trimesh.Trimesh] = []
    deep = 8.0 * rc
    relief = 0.11 * rc                            # how proud the face stands

    eye_w, eye_h = 0.52 * rc * e["eye"], 0.60 * rc * e["eye"]
    for sx in (-1, 1):
        cx, cy = sx * 0.40 * rc, 0.06 * rc
        add.append(_stamp(_rot2(_ellipse(eye_w, eye_h), 0.0, cx, cy),
                          -deep, z_top + relief))
        px = cx + sx * e["pupil"][0] * 0.20 * rc
        py = cy + e["pupil"][1] * 0.24 * rc
        cut.append(_stamp(_rot2(_ellipse(0.46 * eye_w, 0.54 * eye_h), 0.0,
                                px, py),
                          z_top + relief - 0.055 * rc, deep))
        brow = _rot2([(-0.26 * rc, -0.07 * rc), (0.26 * rc, -0.07 * rc),
                      (0.26 * rc, 0.07 * rc), (-0.26 * rc, 0.07 * rc)],
                     sx * e["brow"], sx * 0.36 * rc, 0.50 * rc)
        add.append(_stamp(brow, -deep, z_top + 1.45 * relief))

    for quad in _band(_mouth_curve(e["wide"] * 1.55 * rc, e["bend"]),
                      0.085 * rc):
        cut.append(_stamp([(x, y - 0.58 * rc) for x, y in quad],
                          z_top - 0.085 * rc, deep))
    return add, cut


def _seeds(p: PotParams, rc: float, z_top: float) -> trimesh.Trimesh | None:
    """The middle of a flower is a spiral of seeds, so put one there.

    Golden-angle phyllotaxis, as little cones.  They cost nothing to print -
    the part is lying face up, so a cone is just a bump on a top surface -
    and they are what stops the disc reading as a biscuit.
    """
    golden = math.radians(137.508)
    step = 0.062 * rc if p.yard_plant == "sunflower" else 0.085 * rc
    n = int((0.93 * rc / step) ** 2)
    bumps = []
    for i in range(1, min(n, 260) + 1):
        rho = 0.93 * rc * math.sqrt(i / n)
        a = i * golden
        cone = trimesh.creation.cone(radius=0.62 * step, height=1.45 * step,
                                     sections=8)
        cone.apply_translation((rho * math.cos(a), rho * math.sin(a),
                                z_top - 0.9 * step))
        bumps.append(cone)
    return trimesh.util.concatenate(bumps) if bumps else None
