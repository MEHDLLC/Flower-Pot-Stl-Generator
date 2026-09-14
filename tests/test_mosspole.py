"""A hollow column you pack with sphagnum, in stacking segments.

The whole product is the joint and the pattern, so that is what the tests
are about: segments that actually stack and land on something, a wall that
is open enough to be worth packing and still a wall, and three parts that
come off the plate with nothing under them.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit
from flowerpot.build import _boolean
from flowerpot.mosspole import (PATTERNS, SHAPES, _FOOT_HOLES, _STRUT_MIN,
                                across_flats, assembled_height,
                                build_pole_base, build_pole_cap,
                                build_pole_segment, open_area_fraction,
                                pattern_grid, perimeter, plan, stacked)

FAST = dict(segments=96)
SOLIDS = [s for s in SHAPES]


def _p(**kw) -> PotParams:
    base = dict(moss_pole="set", **FAST)
    base.update(kw)
    return PotParams(**base)


def _seated(p: PotParams, above: trimesh.Trimesh) -> trimesh.Trimesh:
    """A segment dropped onto whatever is under it."""
    seg = build_pole_segment(p)
    seg.apply_translation((0.0, 0.0, above.bounds[1][2] - plan(p)["joint"]))
    return seg


# ---------------------------------------------------------------------------
# does it print?
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("shape", SOLIDS)
@pytest.mark.parametrize("pattern", PATTERNS)
def test_a_segment_prints_standing_up(shape, pattern):
    p = _p(pole_shape=shape, pole_pattern=pattern)
    seg = build_pole_segment(p)
    report = audit(seg, p.overhang_limit_deg)
    assert seg.is_watertight and report.overhang_faces == 0, report
    assert len(seg.split(only_watertight=False)) == 1


@pytest.mark.parametrize("shape", SOLIDS)
def test_the_base_and_the_cap_print_standing_up(shape):
    p = _p(pole_shape=shape)
    for build, genus in ((build_pole_base, _FOOT_HOLES), (build_pole_cap, 1)):
        part = build(p)
        report = audit(part, p.overhang_limit_deg)
        assert part.is_watertight and report.overhang_faces == 0, report
        assert report.genus == genus
        assert len(part.split(only_watertight=False)) == 1


def test_the_holes_are_the_pattern_and_no_others():
    """A tube is already genus 1 before anything is cut in it, so every
    opening is one more handle and the count is exact."""
    p = _p()
    g = pattern_grid(p)
    assert audit(build_pole_segment(p), 45.0).genus == g["cols"] * g["rows"] + 1
    assert audit(build_pole_segment(_p(pole_pattern="solid")), 45.0).genus == 1


def test_every_opening_is_gabled_at_the_budget():
    """The roof is the only face of an opening a printer cares about."""
    for pattern in ("lattice", "slots"):
        p = _p(pole_pattern=pattern)
        k, g = plan(p), pattern_grid(p)
        lean = math.degrees(math.atan2(g["half"], g["up"]))
        assert lean <= p.overhang_limit_deg
        assert g["up"] == pytest.approx(g["half"] / k["s"])


def test_the_bore_is_coned_under_the_spigot_not_stepped():
    """A bore that narrows going up is a ceiling.  The neck has to take the
    height that makes it a slope instead."""
    k = plan(_p())
    drop = k["r_bore"] - k["r_neck"]
    assert k["neck"] == pytest.approx(drop / k["s"], rel=1e-6)
    assert k["neck"] > 3.0


# ---------------------------------------------------------------------------
# does it stack?
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("shape", SOLIDS)
def test_the_parts_go_together_without_touching(shape):
    p = _p(pole_shape=shape)
    base = build_pole_base(p)
    one = _seated(p, base)
    two = _seated(p, one)
    cap = build_pole_cap(p)
    cap.apply_translation((0.0, 0.0, two.bounds[1][2] - plan(p)["joint"]))
    for a, b in ((one, base), (two, one), (cap, two)):
        assert _boolean("intersection", [a, b]).volume < 1.0


def test_a_segment_lands_on_the_shoulder_rather_than_sliding_down():
    """The step the spigot leaves is the stop.  Drop a segment a millimetre
    past it and it has to run into the one below."""
    p = _p()
    seg = build_pole_segment(p)
    low = seg.copy()
    low.apply_translation((0.0, 0.0, plan(p)["pitch"] - 1.0))
    assert _boolean("intersection", [seg, low]).volume > 100.0


@pytest.mark.parametrize("shape,turn,keyed", [
    ("square", math.pi / 4.0, True),
    ("hex", math.pi / 6.0, True),
    ("round", math.pi / 7.0, False),
])
def test_a_polygon_keys_the_joint_and_a_circle_does_not(shape, turn, keyed):
    """Half a facet round is the worst case: on a polygon the spigot simply
    will not go in that way, which is what lines the pattern up.  A round
    pole spins, and the docs say so rather than pretending otherwise."""
    p = _p(pole_shape=shape)
    seg = build_pole_segment(p)
    above = seg.copy()
    above.apply_translation((0.0, 0.0, plan(p)["pitch"]))
    turned = above.copy()
    turned.apply_transform(
        trimesh.transformations.rotation_matrix(turn, [0, 0, 1]))
    assert _boolean("intersection", [seg, above]).volume < 1.0
    clash = _boolean("intersection", [seg, turned]).volume
    assert (clash > 100.0) if keyed else (clash < 1.0)


def test_the_stack_is_as_tall_as_it_says_it_is():
    """Every joint eats the spigot's height out of the segment above it, so
    a segment buys less than its own length - the number that matters is
    the one the generator reports."""
    p = _p(pole_segments=4)
    k = plan(p)
    assert k["pitch"] == pytest.approx(k["h"] - k["joint"])
    assert assembled_height(p) == pytest.approx(4 * k["pitch"] + k["joint"])
    whole = stacked(p)
    cap = build_pole_cap(p)
    base = build_pole_base(p)
    assert whole.bounds[1][2] == pytest.approx(
        base.bounds[1][2] - k["joint"] + 4 * k["pitch"] + cap.bounds[1][2],
        abs=0.05)
    assert any("column" in w for w in p.validate())


# ---------------------------------------------------------------------------
# is it a moss pole?
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("shape", SOLIDS)
def test_the_diameter_is_the_one_you_can_measure(shape):
    """``pole_diameter`` is across the flats on every shape, because that is
    what a ruler and a shop listing both mean by it."""
    p = _p(pole_shape=shape)
    seg = build_pole_segment(p)
    assert seg.extents[0] == pytest.approx(p.pole_diameter, abs=0.3)
    assert across_flats(p, plan(p)["r"]) == pytest.approx(p.pole_diameter,
                                                          abs=1e-6)


def test_there_is_a_column_of_moss_left_inside_it():
    p = _p()
    k = plan(p)
    assert across_flats(p, k["r_bore"]) > 0.8 * p.pole_diameter
    assert across_flats(p, k["r_neck"]) > 0.6 * p.pole_diameter


def test_the_wall_is_open_but_is_still_a_wall():
    p = _p()
    g = pattern_grid(p)
    assert g["strut"] >= _STRUT_MIN
    assert 0.10 < open_area_fraction(p) < 0.55
    assert open_area_fraction(_p(pole_pattern="solid")) == 0.0
    # more open means more open, and the warning says the number
    assert open_area_fraction(_p(pole_open=0.85)) > open_area_fraction(p)
    assert any("% of the wall is opening" in w for w in p.validate())


def test_the_openings_break_the_wall_where_the_pattern_says():
    """Slice through a row and the tube comes apart into one arc per
    column; slice between two rows and it is a tube again."""
    p = _p()
    g = pattern_grid(p)
    seg = build_pole_segment(p)
    row = seg.section(plane_origin=[0, 0, g["z0"]], plane_normal=[0, 0, 1])
    assert len(row.discrete) == g["cols"]
    between = seg.section(plane_origin=[0, 0, g["z0"] + 0.5 * g["pitch"]],
                          plane_normal=[0, 0, 1])
    assert len(between.discrete) == 2          # one wall: outside and bore


def test_the_pattern_keeps_off_the_corners():
    """A corner is the stiffest part of the section and the part you tie a
    stem to, so the columns land on faces."""
    p = _p(pole_shape="square")
    g = pattern_grid(p)
    assert g["cols"] % plan(p)["sides"] == 0


def test_the_cap_is_a_funnel_and_the_base_is_a_foot():
    p = _p()
    k = plan(p)
    cap, base = build_pole_cap(p), build_pole_base(p)
    assert cap.extents[0] > 1.3 * p.pole_diameter        # it opens out
    assert base.extents[0] > 1.5 * p.pole_diameter       # it spreads out
    assert audit(base, 45.0).base_area_cm2 > 20.0
    # the cap's bore never narrows going up: that is what makes it pourable
    # and what makes it printable, and they are the same requirement
    for z in np.linspace(1.0, cap.bounds[1][2] - 1.0, 24):
        ring = cap.section(plane_origin=[0, 0, float(z)],
                           plane_normal=[0, 0, 1])
        bore = min(np.hypot(*np.array(loop).T[:2]).min()
                   for loop in ring.discrete)
        assert bore >= 0.5 * across_flats(p, k["r_bore"]) - 0.6


# ---------------------------------------------------------------------------
# guardrails
# ---------------------------------------------------------------------------
def test_guardrails():
    with pytest.raises(ParameterError, match="unknown moss_pole"):
        PotParams(moss_pole="pole").validate()
    with pytest.raises(ParameterError, match="unknown pole_shape"):
        _p(pole_shape="triangle").validate()
    with pytest.raises(ParameterError, match="unknown pole_pattern"):
        _p(pole_pattern="mesh").validate()
    with pytest.raises(ParameterError, match="does not combine"):
        _p(cradle="set").validate()
    with pytest.raises(ParameterError, match="at least 30 mm"):
        _p(pole_diameter=20.0).validate()
    with pytest.raises(ParameterError, match="mostly joint"):
        _p(pole_segment_height=28.0).validate()
    with pytest.raises(ParameterError, match="not a wall"):
        _p(pole_open=0.97).validate()
    with pytest.raises(ParameterError, match="pole_segments"):
        _p(pole_segments=0).validate()
    with pytest.raises(ParameterError, match="do not fit"):
        _p(pole_rows=14).validate()


def test_a_segment_too_tall_for_the_machine_is_said_out_loud():
    warn = _p(pole_segment_height=340.0,
              printer="creality-ender3-v3-ke").validate()
    assert any("does not stand up" in w for w in warn), warn


@pytest.mark.parametrize("kw", [
    dict(pole_diameter=90.0, pole_segment_height=220.0, pole_shape="hex"),
    dict(pole_diameter=38.0, pole_segment_height=100.0, pole_open=0.5),
    dict(wall_thickness=4.0, pole_pattern="slots", pole_shape="round"),
    dict(overhang_limit_deg=40.0, pole_open=0.75),
])
def test_another_size_still_stacks_and_still_prints(kw):
    p = _p(**kw)
    base = build_pole_base(p)
    one = _seated(p, base)
    two = _seated(p, one)
    assert _boolean("intersection", [one, base]).volume < 1.0
    assert _boolean("intersection", [two, one]).volume < 1.0
    for part in (base, build_pole_segment(p), build_pole_cap(p)):
        report = audit(part, p.overhang_limit_deg)
        assert part.is_watertight and report.overhang_faces == 0, report
