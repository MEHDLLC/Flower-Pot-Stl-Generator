"""Loops on the pot's own rim, and the bar they hang from.

Two things are being tested.  One is that an ear is still a pot feature -
every style and silhouette, still watertight, still printable standing up
with a hole through it and nothing under that hole but a cone.  The other
is the direction of the load, because a cord pulling up on a rim pulls
ACROSS the layer lines, and that is the direction the rest of this
generator bends over backwards to avoid.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit
from flowerpot.build import _boolean, build_pot
from flowerpot.ceiling import (_EYE_R, _SIGMA_Z, _WEB, build_ceiling_plate,
                               ear_section, local_radius, loop_azimuths,
                               loop_parts, plan, plate_plan)
from flowerpot.profile import build_profiles, outer_radius_at

FAST = dict(segments=96, vertical_step=2.5)
STYLES = ["classic_tapered", "hexagonal", "square", "low_poly_faceted",
          "ribbed_spiral"]


def _p(**kw) -> PotParams:
    base = dict(hang_loops=3, **FAST)
    base.update(kw)
    return PotParams(**base)


def _bores(p: PotParams) -> int:
    """Holes the pot would have without any loops on it."""
    return {"none": 0, "center": 1}.get(p.drainage_pattern,
                                        int(p.num_drainage_holes))


# ---------------------------------------------------------------------------
# an ear is still a pot feature
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("style", STYLES)
def test_a_pot_with_loops_still_prints_standing_up(style):
    p = _p(pot_style=style)
    pot = build_pot(p)
    report = audit(pot, p.overhang_limit_deg)
    assert pot.is_watertight and report.overhang_faces == 0, report
    assert len(pot.split(only_watertight=False)) == 1


@pytest.mark.parametrize("kw", [
    dict(surface_texture="honeycomb"), dict(add_top_rim=False),
    dict(rim_width=12.0), dict(belly=0.10),
    dict(vase_profile="classic", height=250.0),
    dict(vase_profile="bottle", height=250.0),
    dict(wall_thickness=2.0, add_top_rim=False),
    dict(height=90.0, top_diameter=100.0, bottom_diameter=80.0),
])
def test_everything_the_pot_builder_can_do_still_takes_loops(kw):
    p = _p(**kw)
    pot = build_pot(p)
    report = audit(pot, p.overhang_limit_deg)
    assert pot.is_watertight and report.overhang_faces == 0, report
    assert len(pot.split(only_watertight=False)) == 1


@pytest.mark.parametrize("n", [2, 3, 4, 6])
@pytest.mark.parametrize("drain", ["ring", "none", "grid"])
def test_the_genus_counts_every_bore_as_a_hole_right_through(n, drain):
    """A blind hole adds nothing to the genus and a through hole adds one,
    so this one number says every loop can actually take a cord."""
    p = _p(hang_loops=n, drainage_pattern=drain)
    assert audit(build_pot(p), 45.0).genus == n + _bores(p)


def test_a_cord_has_a_clear_vertical_path_through_every_loop():
    """The point of a vertical bore: no gable, no support, and a straight
    line from above the rim to below it."""
    p = _p()
    k = plan(p)
    pot = build_pot(p)
    for e in k["ears"]:
        probe = trimesh.creation.cylinder(radius=k["r_bore"] - 0.4,
                                          height=4.0 * p.height, sections=32)
        probe.apply_translation((e["r_c"] * math.cos(e["a"]),
                                 e["r_c"] * math.sin(e["a"]), 0.0))
        assert _boolean("intersection", [pot, probe]).volume < 1.0


def test_the_bore_never_breaks_into_the_pot():
    p = _p()
    k = plan(p)
    for e in k["ears"]:
        assert e["r_c"] - k["r_bore"] - _WEB >= e["r_cav"] - 1e-9
    # and the soil, as a solid, reaches none of them
    soil = trimesh.creation.cylinder(
        radius=k["ears"][0]["r_cav"], height=p.height, sections=120)
    soil.apply_translation((0.0, 0.0, 0.5 * p.height))
    ears, bores = loop_parts(p)
    for bore in bores:
        assert _boolean("intersection", [soil, bore]).volume < 1.0


def test_the_loops_do_not_drag_the_pot_off_its_own_axis():
    """Three ears are not symmetric about a bounding box, and everything
    here is measured from the axis."""
    pot = build_pot(_p())
    assert pot.bounds[0][1] == pytest.approx(-pot.bounds[1][1], abs=0.05)
    plain = build_pot(_p(hang_loops=0))
    assert plain.bounds[0][0] == pytest.approx(-plain.bounds[1][0], abs=0.05)


def test_loops_are_off_unless_you_ask_and_then_they_are_where_they_say():
    p0 = PotParams(**FAST)
    assert p0.hang_loops == 0
    assert audit(build_pot(p0), 45.0).genus == _bores(p0)
    assert build_pot(p0).extents[0] < build_pot(_p()).extents[0]
    assert loop_azimuths(_p(hang_loops=4)) == pytest.approx(
        [0.0, math.pi / 2, math.pi, 1.5 * math.pi])


# ---------------------------------------------------------------------------
# the gusset, and the polygon trap
# ---------------------------------------------------------------------------
def test_nothing_under_an_ear_is_air():
    """The gusset is a flare of the pot's own wall, so it springs from
    material.  If it did not, the ear's underside would be a 90 degree
    ledge and the audit would say so."""
    p = _p()
    k = plan(p)
    report = audit(build_pot(p), p.overhang_limit_deg)
    assert report.overhang_faces == 0
    assert report.worst_overhang_deg <= p.overhang_limit_deg
    assert report.worst_overhang_deg == pytest.approx(
        math.degrees(math.atan(k["slope"])), abs=1.5)


@pytest.mark.parametrize("style", ["hexagonal", "square", "low_poly_faceted"])
def test_a_polygon_puts_its_ears_on_the_wall_and_not_on_the_corner_radius(style):
    """A polygon's polyline carries its CORNER radius.  Place an ear that
    far out and it hangs in the air over a flat, with its gusset springing
    from nothing - 90 degrees of overhang and a hole that goes nowhere."""
    p = _p(pot_style=style, hang_loops=3)
    k = plan(p)
    prof, sec = build_profiles(p), ear_section(p)
    corner = outer_radius_at(prof, p.height)
    assert any(e["r_wall"] < corner - 0.5 for e in k["ears"]), \
        "this style has no flats to fall foul of"
    for e in k["ears"]:
        assert e["r_wall"] == pytest.approx(
            local_radius(sec, e["a"], p.height, corner), abs=1e-6)
        assert e["r_c"] >= e["r_wall"] - 1e-9
    report = audit(build_pot(p), p.overhang_limit_deg)
    assert report.overhang_faces == 0, report
    assert audit(build_pot(p), 45.0).genus == 3 + _bores(p)


def test_a_pot_with_no_rim_grows_its_own_ear():
    """Without a rim there is nothing sticking out to widen, so the ear has
    to stand further proud and its gusset has to reach further down."""
    with_rim, without = plan(_p()), plan(_p(add_top_rim=False))
    assert (without["worst"]["r_out"] - without["worst"]["r_wall"]
            > with_rim["worst"]["r_out"] - with_rim["worst"]["r_wall"])
    assert without["worst"]["h"] > with_rim["worst"]["h"]
    assert audit(build_pot(_p(add_top_rim=False)), 45.0).overhang_faces == 0


# ---------------------------------------------------------------------------
# the direction the load pulls
# ---------------------------------------------------------------------------
def test_the_cord_pulls_the_wrong_way_and_the_sum_says_so_out_loud():
    """Everything else in this generator is arranged so the load runs ALONG
    the layer lines.  This one cannot be, so it is checked against an
    interlayer working stress instead of pretending otherwise."""
    p = _p()
    k = plan(p)
    assert _SIGMA_Z < 8.0, "a layer bond is not the plastic"
    assert k["sigma"] <= _SIGMA_Z
    assert k["sigma"] < 0.2 * _SIGMA_Z, "and there is a lot of room in it"
    assert k["area"] == pytest.approx(
        math.pi * (k["r_pad"] ** 2 - k["r_bore"] ** 2))
    assert any("ACROSS the layer lines" in m and "3 MPa" in m
               for m in p.validate())
    assert any("bag of soil in it before you trust it" in m
               for m in p.validate())


def test_the_pot_works_out_what_it_will_weigh():
    p = _p()
    k = plan(p)
    assert k["soil"] > 1000.0
    assert k["load"] == pytest.approx(k["soil"] * 1.2 / 1000.0 + 0.6)
    big = plan(_p(height=250.0, top_diameter=240.0, bottom_diameter=180.0))
    assert big["load"] > 3.0 * k["load"]
    assert any("ml and weighs around" in m for m in p.validate())


def test_one_loop_is_assumed_slack_and_more_loops_share_it():
    two, three, six = plan(_p(hang_loops=2)), plan(_p()), plan(_p(hang_loops=6))
    assert two["pull"] == pytest.approx(two["weight"])
    assert three["pull"] == pytest.approx(three["weight"] / 2.0)
    assert six["pull"] < three["pull"] < two["pull"]
    assert six["sigma"] < three["sigma"] < two["sigma"]


def test_a_bigger_bore_is_more_section_not_less():
    """The web is what carries it, and the web goes out with the hole."""
    small, big = plan(_p(hang_loop_bore=3.0)), plan(_p(hang_loop_bore=10.0))
    assert big["area"] > small["area"]
    assert big["sigma"] < small["sigma"]
    assert audit(build_pot(_p(hang_loop_bore=10.0)), 45.0).overhang_faces == 0


def test_why_it_is_a_bore_and_not_an_eye_is_written_down():
    assert any("vertical on purpose" in m and "gabled roof" in m
               for m in _p().validate())
    assert any("cord does not creep" in m for m in _p().validate())


# ---------------------------------------------------------------------------
# the ceiling bar
# ---------------------------------------------------------------------------
def test_the_bar_prints_flat_so_its_bending_runs_along_the_layers():
    p = _p(hang_ceiling_plate=True)
    q = plate_plan(p)
    bar = build_ceiling_plate(p)
    report = audit(bar, p.overhang_limit_deg)
    assert bar.is_watertight and report.overhang_faces == 0, report
    assert bar.extents[2] == min(bar.extents)
    assert bar.extents[2] == pytest.approx(q["t"], abs=0.05)
    assert report.genus == q["n_screw"] + 1        # the screws, and the eye
    assert q["sigma"] <= 8.0 + 1e-6
    assert any("Print it FLAT" in m for m in p.validate())


def test_the_bar_gets_thicker_for_a_heavier_pot():
    light = plate_plan(_p(hang_ceiling_plate=True, height=90.0,
                          top_diameter=100.0, bottom_diameter=80.0))
    heavy = plate_plan(_p(hang_ceiling_plate=True, height=250.0,
                          top_diameter=240.0, bottom_diameter=180.0))
    assert heavy["weight"] > light["weight"]
    assert heavy["t"] > light["t"]
    for kw in (dict(), dict(height=250.0, top_diameter=240.0,
                            bottom_diameter=180.0)):
        assert plate_plan(_p(hang_ceiling_plate=True, **kw))["sigma"] <= 8.0 + 1e-6


def test_the_eye_is_chamfered_so_the_cord_does_not_bear_on_an_edge():
    p = _p(hang_ceiling_plate=True)
    bar = build_ceiling_plate(p)
    # widest at the bed face, narrowing as it goes up: a printable cone
    lo = bar.section(plane_origin=[0, 0, 0.3], plane_normal=[0, 0, 1])
    hi = bar.section(plane_origin=[0, 0, plate_plan(p)["t"] - 0.3],
                     plane_normal=[0, 0, 1])

    def eye(sl):
        loops = [np.array(loop) for loop in sl.discrete]
        near = min(loops, key=lambda a: np.hypot(a[:, 0], a[:, 1]).min())
        return float(np.hypot(near[:, 0], near[:, 1]).mean())
    assert eye(lo) > eye(hi) + 0.3
    assert eye(hi) == pytest.approx(_EYE_R, abs=0.4)


def test_a_steel_hook_is_admitted_to_be_the_better_idea():
    assert any("steel screw hook costs pennies" in m
               for m in _p(hang_ceiling_plate=True).validate())


# ---------------------------------------------------------------------------
# guardrails
# ---------------------------------------------------------------------------
def test_guardrails():
    with pytest.raises(ParameterError, match="hang_loops should be 2-6"):
        _p(hang_loops=7).validate()
    with pytest.raises(ParameterError, match="hang_loop_bore should be"):
        _p(hang_loop_bore=1.0).validate()
    with pytest.raises(ParameterError, match="hang_loop_bore should be"):
        _p(hang_loop_bore=20.0).validate()
    with pytest.raises(ParameterError, match="no cord without hang_loops"):
        PotParams(hang_ceiling_plate=True, **FAST).validate()
    with pytest.raises(ParameterError, match="hang_ceiling_plate is off"):
        build_ceiling_plate(_p())


@pytest.mark.parametrize("kw", [dict(wall_pot="set"), dict(hanger="set"),
                                dict(underpot="set"), dict(moss_pole="set")])
def test_loops_do_not_combine_with_the_other_mounts(kw):
    with pytest.raises(ParameterError, match="do not combine"):
        _p(**kw).validate()
