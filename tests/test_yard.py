"""Yard art: a plant with a face and an opinion.

The interesting tests here are about *why* the flower comes apart.  A
vertical disc cannot print; a flat one prints perfectly and can be a
different colour.  So the head has to be its own part, it has to fit the
body it drops into, and the parts that stay standing have to obey the same
overhang budget as everything else in this project.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit
from flowerpot.build import _boolean
from flowerpot.yard import (FACES, GESTURES, PLANTS, _CARVE_RESERVE, _EASE,
                            _lens, _rot2, arm_max_slope, arm_path,
                            build_yard_body, build_yard_face, build_yard_head,
                            face_disc_radius, head_pose, lens_aspect, plan,
                            tab_depth)

FAST = dict(segments=80)


def _p(**kw) -> PotParams:
    base = dict(yard_plant="sunflower", hitch_mount="none", **FAST)
    base.update(kw)
    return PotParams(**base)


# ---------------------------------------------------------------------------
# the flat parts
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("plant", ["sunflower", "daisy"])
def test_a_head_printed_flat_has_no_overhang_at_all(plant):
    """This is the whole reason the flower is not one piece: face up on the
    bed, every bit of the face is a *top* surface."""
    p = _p(yard_plant=plant)
    for build in (build_yard_head, build_yard_face):
        part = build(p)
        report = audit(part, p.overhang_limit_deg)
        assert part.is_watertight, report
        assert report.overhang_faces == 0 and report.worst_overhang_deg <= 0.01
        # ... and it really is lying down, on a face the bed can hold
        assert part.bounds[0][2] == pytest.approx(0.0, abs=1e-6)
        assert part.extents[2] < 0.4 * part.extents[0]
        assert report.base_area_cm2 > 10.0


def test_the_face_disc_drops_into_the_head_and_the_tab_into_the_body():
    """Three parts, two joints, and both have to have room."""
    p = _p()
    lay = plan(p)
    head, face, body = build_yard_head(p), build_yard_face(p), build_yard_body(p)

    seated = face.copy()
    seated.apply_translation((0.0, 0.0, 0.45 * lay["thick"]))
    assert _boolean("intersection", [head, seated]).volume < 60.0

    stood = head.copy()
    stood.apply_transform(head_pose(p))
    clash = _boolean("intersection", [body, stood])
    assert clash.volume < 120.0, f"{clash.volume:.0f} mm3 of head inside body"


def test_the_tab_actually_reaches_into_the_slot():
    """Clearance is only half of it - the joint also has to engage."""
    p = _p()
    lay = plan(p)
    stood = build_yard_head(p)
    stood.apply_transform(head_pose(p))
    # material from the head below the body's shoulder is tab in the slot
    below = trimesh.creation.box(extents=(400.0, 400.0, 400.0))
    below.apply_translation((0.0, 0.0, lay["z_pad"] - 200.0))
    tab = _boolean("intersection", [stood, below])
    assert tab.volume > 0.0
    assert lay["z_pad"] - tab.bounds[0][2] >= 0.7 * tab_depth(p)


def test_the_arms_keep_out_of_the_tab_s_way():
    """The tab drops down the middle of the body and the arms start there
    too, so the shoulders are set behind the head's plane.  If they were
    not, the arm would be sitting in the slot."""
    p = _p()
    lay = plan(p)
    corridor = trimesh.creation.box(
        extents=(lay["tab_w"], lay["thick"], tab_depth(p) - 1.0))
    corridor.apply_translation(
        (0.0, 0.0, lay["z_pad"] - 0.5 * tab_depth(p) - 0.5))
    body = build_yard_body(p)
    assert _boolean("intersection", [body, corridor]).volume < 1.0


# ---------------------------------------------------------------------------
# the standing part
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("plant", PLANTS)
@pytest.mark.parametrize("mount", ["none", "fused", "screw"])
def test_every_body_prints_standing_up(plant, mount):
    p = _p(yard_plant=plant, hitch_mount=mount)
    body = build_yard_body(p)
    report = audit(body, p.overhang_limit_deg)
    assert body.is_watertight and report.overhang_faces == 0, report
    assert len(body.split(only_watertight=False)) == 1


@pytest.mark.parametrize("gesture", [g for g in GESTURES if g != "none"])
def test_no_gesture_leans_an_arm_past_the_budget(gesture):
    """A ring stack's underside lean is its lateral slope plus its taper.
    Both are measured, and both are charged to the same budget."""
    p = _p(yard_left_hand=gesture, yard_right_hand=gesture)
    limit = math.tan(math.radians(p.overhang_limit_deg))
    scale = 0.62 if gesture == "shrug" else 1.0
    assert arm_max_slope(p, plan(p), 1, scale) <= limit
    body = build_yard_body(p)
    assert audit(body, p.overhang_limit_deg).overhang_faces == 0


def test_the_hands_end_up_outside_the_petals_and_under_the_top():
    """The two things that fight over an arm's climb."""
    p = _p()
    lay = plan(p)
    path, _radii, _w = arm_path(p, lay, 1)
    assert abs(path[-1][0]) > 0.5 * lay["d"]         # clear of the head
    assert path[-1][2] < lay["top"]


# ---------------------------------------------------------------------------
# carving a standing wall
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tilt", [0.0, 6.0, 11.0])
@pytest.mark.parametrize("limit", [40.0, 45.0, 55.0])
def test_lens_aspect_really_is_the_inverse_it_claims_to_be(tilt, limit):
    """Taller than wide is not enough: a vesica's cusp is the shallowest
    thing on it, and tilting takes the same angle straight off one side.
    Build the mark the formula asks for and measure every segment."""
    k = lens_aspect(tilt, limit, _CARVE_RESERVE)
    prof = _rot2(_lens(10.0, k * 10.0, k), tilt)
    worst = 90.0
    for (x0, y0), (x1, y1) in zip(prof, prof[1:] + prof[:1]):
        run = math.hypot(x1 - x0, y1 - y0)
        if run > 1e-9:
            worst = min(worst, math.degrees(math.asin(abs(y1 - y0) / run)))
    lean = 90.0 - worst
    assert lean <= limit, f"{lean:.1f} deg of lean at a {limit:.0f} limit"
    assert lean >= limit - 2.0 * _CARVE_RESERVE      # ... and not wasteful


@pytest.mark.parametrize("face", [f for f in FACES if f != "none"])
def test_a_carved_cactus_keeps_its_face_printable(face):
    p = _p(yard_plant="cactus", yard_face=face)
    body = build_yard_body(p)
    assert audit(body, p.overhang_limit_deg).overhang_faces == 0
    assert any("eyebrows" in w for w in p.validate())


# ---------------------------------------------------------------------------
# guardrails
# ---------------------------------------------------------------------------
def test_guardrails():
    with pytest.raises(ParameterError, match="unknown yard_plant"):
        plan(_p(yard_plant="triffid"))
    with pytest.raises(ParameterError, match="unknown yard_face"):
        _p(yard_face="bored").validate()
    with pytest.raises(ParameterError, match="yard_left_hand"):
        _p(yard_left_hand="jazz").validate()
    with pytest.raises(ParameterError, match="mount on its own"):
        _p(hitch_mount="cover").validate()
    with pytest.raises(ParameterError, match="does not combine"):
        _p(bouquet=True).validate()
    with pytest.raises(ParameterError, match="yard_height"):
        _p(hitch_mount="screw", yard_height=70.0).validate()
    with pytest.raises(ParameterError, match="no separate head"):
        build_yard_head(_p(yard_plant="cactus"))


def test_a_faceless_plant_is_allowed():
    p = _p(yard_face="none", yard_left_hand="none", yard_right_hand="none")
    assert p.validate() == []
    assert audit(build_yard_body(p), p.overhang_limit_deg).overhang_faces == 0
