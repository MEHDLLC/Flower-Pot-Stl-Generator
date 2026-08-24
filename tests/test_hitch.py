"""The trailer-hitch mount: a sliced socket that snaps over the ball.

The mechanism is a snap fit, so the tests are about the two things a snap
fit can get wrong - it does not hold, or it breaks going on - plus the
usual print gates.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit
from flowerpot.build import _boolean
from flowerpot.hitch import (BALL_SIZES, _CLEAR, _PRESS, _STRAIN, ball_diameter,
                             build_hitch_cap, build_hitch_collar,
                             build_hitch_cover, cavity_radius, collar_top,
                             flange_radius, solve, spring_strain, thread_core)

FAST = dict(segments=96)
BALLS = sorted(BALL_SIZES)


def _ball(k: dict, sections: int = 64) -> trimesh.Trimesh:
    """The trailer ball, seated: a sphere at the height the socket holds it."""
    s = trimesh.creation.icosphere(subdivisions=4, radius=k["r_ball"])
    s.apply_translation((0.0, 0.0, k["z_ball"]))
    return s


# ---------------------------------------------------------------------------
# does it hold?
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ball", BALLS)
def test_the_mouth_is_narrower_than_the_ball(ball):
    """No undercut, no retention - the whole mechanism is this one number."""
    p = PotParams(hitch_mount="cover", hitch_ball=ball, **FAST)
    k = solve(p)
    assert k["r_mouth"] == pytest.approx(k["r_ball"] - p.hitch_grip)
    # ... and the socket reaches past the equator to get it
    assert k["z_ball"] > k["z_lip"]
    assert cavity_radius(k, k["z_ball"]) > cavity_radius(k, k["z_lip"])


@pytest.mark.parametrize("ball", BALLS)
def test_the_seat_stays_on_the_spherical_part_of_the_ball(ball):
    """A real hitch ball is only a sphere down to about its equator before
    it flares into the shank.  The mouth has to grip above that."""
    k = solve(PotParams(hitch_mount="cover", hitch_ball=ball, **FAST))
    below_centre = k["z_ball"] - k["z_lip"]
    assert below_centre < 0.45 * k["r_ball"]


def test_pushing_it_on_splays_the_fingers_and_then_lets_go():
    """Walk the ball down through the mouth and watch the interference: it
    has to rise to exactly the undercut at the equator and come back."""
    p = PotParams(hitch_mount="cover", hitch_ball="2", **FAST)
    k = solve(p)
    ring = k["r_mouth"]                      # the ring that does the gripping
    splay = []
    for i in range(201):
        # centre of the ball, relative to the gripping ring
        u = k["r_ball"] * (1.4 - 2.8 * i / 200.0)
        half = math.sqrt(max(k["r_ball"] ** 2 - u * u, 0.0))
        splay.append(max(half - ring, 0.0))
    peak = max(splay)
    assert peak == pytest.approx(p.hitch_grip, abs=1e-3)
    assert splay[0] == 0.0 and splay[-1] == 0.0        # free before and after
    # and it is a single hump, not a ramp that never lets go
    top = splay.index(peak)
    assert all(a <= b + 1e-9 for a, b in zip(splay[:top], splay[1:top + 1]))
    assert all(a >= b - 1e-9 for a, b in zip(splay[top:], splay[top + 1:]))


@pytest.mark.parametrize("ball", BALLS)
def test_a_seated_ball_fits_the_socket_with_the_clearance_it_was_given(ball):
    """Solid proof, not arithmetic: boolean the real ball into the real
    part.  The only place they may touch is the squeeze band under the
    equator, which is there to stop it rattling."""
    p = PotParams(hitch_mount="cover", hitch_ball=ball, **FAST)
    k = solve(p)
    mount = build_hitch_cover(p)
    clash = _boolean("intersection", [mount, _ball(k)])
    if clash.volume > 0.0:
        z = clash.vertices[:, 2]
        assert z.max() <= k["z_ball"] + 0.3, "the ball fouls the roof"
        # a shell _PRESS deep over a band, no more
        band = 2.0 * math.pi * k["r_ball"] ** 2 * _PRESS
        assert clash.volume < band, clash.volume


@pytest.mark.parametrize("ball", BALLS)
def test_the_roof_clears_the_ball_completely(ball):
    """Above the equator the cavity is pure clearance - that is what lets it
    push on without wedging."""
    k = solve(PotParams(hitch_mount="cover", hitch_ball=ball, **FAST))
    lo = k["z_ball"] + 1e-6              # the equator itself is the squeeze
    crown = k["z_ball"] + k["r_ball"]    # above this there is no ball left
    for i in range(120):
        z = lo + (crown - lo) * i / 119.0
        u = z - k["z_ball"]
        ball_r = math.sqrt(max(k["r_ball"] ** 2 - u * u, 0.0))
        assert cavity_radius(k, z) >= ball_r + _CLEAR - 1e-9
    # ... and the cone carries on over the crown without touching it
    assert k["z_apex"] > crown


# ---------------------------------------------------------------------------
# does it survive going on?
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ball", BALLS)
def test_the_fingers_are_long_enough_not_to_snap(ball):
    """A finger prints standing up, so splaying it pulls across the layer
    lines.  The slots are sized from that, so the strain must land on the
    target rather than wherever the geometry felt like."""
    p = PotParams(hitch_mount="cover", hitch_ball=ball, **FAST)
    assert spring_strain(p) <= _STRAIN + 1e-9
    assert p.validate() == []


def test_a_greedy_grip_is_reported_not_silently_weakened():
    p = PotParams(hitch_mount="cover", hitch_ball="1-7/8", hitch_grip=3.0,
                  **FAST)
    warn = p.validate()
    assert any("strained" in w for w in warn), warn
    assert any("PETG" in w for w in warn), warn


def test_the_slots_run_past_the_equator():
    """A slot that stops below the widest point leaves an unbroken ring
    there, and an unbroken ring cannot open."""
    for ball in BALLS:
        k = solve(PotParams(hitch_mount="cover", hitch_ball=ball, **FAST))
        assert k["slot"] > k["z_ball"] + 4.0
        assert k["slot"] <= k["z_knee"]      # ... but leaves a ring above


# ---------------------------------------------------------------------------
# does it print?
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ball", BALLS)
def test_the_cover_prints_without_supports(ball):
    p = PotParams(hitch_mount="cover", hitch_ball=ball, **FAST)
    mount = build_hitch_cover(p)
    report = audit(mount, p.overhang_limit_deg)
    assert mount.is_watertight and report.overhang_faces == 0, report
    assert report.genus == 0                 # a cup, notched down to the rim
    assert len(mount.split(only_watertight=False)) == 1
    assert report.base_area_cm2 > 5.0


def test_the_collar_and_its_cap_print_without_supports():
    p = PotParams(hitch_mount="screw", hitch_ball="2", **FAST)
    collar = build_hitch_collar(p)
    cap = build_hitch_cap(p)
    for part, expect_genus in ((collar, 1), (cap, 0)):
        report = audit(part, p.overhang_limit_deg)
        assert part.is_watertight and report.overhang_faces == 0, report
        assert report.genus == expect_genus
    # the collar is a tube: the ball goes in the bottom, the bore is open


def test_the_cap_screws_onto_the_collar():
    """A thread mates at one phase, so sweep the phase and keep the best:
    somewhere in a turn the cap has to drop onto the shoulder with the two
    helices sharing no material at all."""
    p = PotParams(hitch_mount="screw", hitch_ball="2", **FAST)
    _core, z0, _z1 = thread_core(p)
    collar = build_hitch_collar(p)
    cap = build_hitch_cap(p)
    cap.apply_translation((0.0, 0.0, z0))
    best = math.inf
    for k in range(36):
        turned = cap.copy()
        turned.apply_transform(trimesh.transformations.rotation_matrix(
            2.0 * math.pi * k / 36.0, [0, 0, 1]))
        clash = _boolean("intersection", [collar, turned])
        best = min(best, clash.volume if len(clash.faces) else 0.0)
        if best < 0.01:
            break
    assert best < 0.01, f"{best:.2f} mm3 at the best of 36 phases"


def test_the_cap_lands_flush_on_the_collar():
    p = PotParams(hitch_mount="screw", hitch_ball="2", **FAST)
    cap = build_hitch_cap(p)
    r = np.hypot(cap.vertices[:, 0], cap.vertices[:, 1])
    assert r.max() == pytest.approx(flange_radius(p), abs=0.2)


# ---------------------------------------------------------------------------
# guardrails
# ---------------------------------------------------------------------------
def test_ball_sizes_and_guardrails():
    assert ball_diameter(PotParams(hitch_ball="2")) == pytest.approx(50.8)
    assert ball_diameter(PotParams(hitch_ball="54.0")) == pytest.approx(54.0)
    with pytest.raises(ParameterError, match="unknown hitch_ball"):
        ball_diameter(PotParams(hitch_ball="2 inch"))
    with pytest.raises(ParameterError, match="30-120"):
        ball_diameter(PotParams(hitch_ball="200"))
    with pytest.raises(ParameterError, match="unknown hitch_mount"):
        PotParams(hitch_mount="glue").validate()
    with pytest.raises(ParameterError, match="hitch_fingers"):
        PotParams(hitch_mount="cover", hitch_fingers=2).validate()
    with pytest.raises(ParameterError, match="hitch_grip"):
        solve(PotParams(hitch_mount="cover", hitch_grip=0.0))


def test_an_even_finger_count_is_allowed_but_flagged():
    warn = PotParams(hitch_mount="cover", hitch_fingers=4).validate()
    assert any("odd" in w for w in warn), warn


def test_the_finger_count_is_what_you_asked_for():
    """Count the notches around the mouth's first layer."""
    p = PotParams(hitch_mount="cover", hitch_ball="2", hitch_fingers=7, **FAST)
    mount = build_hitch_cover(p)
    ring = mount.section(plane_origin=[0, 0, 0.6], plane_normal=[0, 0, 1])
    assert ring is not None
    planar, _ = ring.to_2D()
    assert len(planar.polygons_full) == 7
