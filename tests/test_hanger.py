"""A hanger for a pot, in three flat parts.

This is the only thing in the generator that has to hold a load up rather
than stand on a bench, so the tests are about the two ways that goes wrong:
the wrong print orientation, and a joint that comes apart in the direction
the weight is pulling.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit
from flowerpot.build import _boolean, lathe
from flowerpot.hanger import (PARTS, TOPS, WALL_PARTS, _CSK_DEG,
                              _RIB_BEAR_MIN, _SIGMA, _SLOT_FIT, _TILT_MAX,
                              _WALL_CLEAR, _YOKE_LIFT, _round, _yoke_modulus,
                              arm_frame, arm_clearance, assembled,
                              build_hanger_arm, build_hanger_base,
                              build_hanger_cleat, build_hanger_rib,
                              build_hanger_top, build_hanger_yoke, governs,
                              hook_length, hung_set, insert_tilt, plan,
                              rib_bending, rib_depth, seated_arm,
                              seated_cleat, seated_rib, seated_top,
                              seated_yoke, stresses, wall_clearance,
                              wall_governs, wall_plan, wall_stresses)

FAST = dict(segments=96, vertical_step=2.5)


def _p(**kw) -> PotParams:
    base = dict(hanger="set", **FAST)
    base.update(kw)
    return PotParams(**base)


def _pot_solid(p: PotParams) -> trimesh.Trimesh:
    """The pot, sitting on the base's seat."""
    k = plan(p)
    pot = lathe([(k["pot"]["base_r"], 0.0),
                 (k["pot"]["top_r"], k["pot"]["height"])],
                _round(p), decorate=False)
    pot.apply_translation((0.0, 0.0, k["t_base"]))
    return pot


# ---------------------------------------------------------------------------
# print orientation is the design
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("build,thick", [
    (build_hanger_base, "t_base"),
    (build_hanger_arm, "t_arm"),
    (build_hanger_top, "t_top"),
])
def test_every_part_is_a_flat_plate(build, thick):
    """The whole design rests on this: a part that carries a hanging pot
    standing up is being pulled apart across its layer lines.  Each part is
    modelled lying down, so its thinnest dimension is its thickness."""
    p = _p()
    part = build(p)
    assert part.extents[2] == min(part.extents)
    assert part.extents[2] == pytest.approx(plan(p)[thick], abs=0.05)
    report = audit(part, p.overhang_limit_deg)
    assert part.is_watertight and report.overhang_faces == 0, report
    assert len(part.split(only_watertight=False)) == 1
    # a plate lying on the bed is nearly all footprint
    assert report.base_area_cm2 > 4.0


@pytest.mark.parametrize("arms", [3, 4, 5])
def test_the_holes_are_the_slots_and_no_others(arms):
    """One slot per arm, plus the seat's hole in the base and whatever you
    hang the top ring by.  An extra hole in a load path is a crack."""
    p = _p(hanger_arms=arms)
    assert audit(build_hanger_base(p), 45.0).genus == arms + 1
    assert audit(build_hanger_top(p), 45.0).genus == arms + 1
    assert audit(build_hanger_arm(p), 45.0).genus == 0


# ---------------------------------------------------------------------------
# the toggle joint
# ---------------------------------------------------------------------------
def test_the_return_cannot_pass_its_slot_standing_up():
    """That is the entire joint: the return is longer than the slot, so the
    arm threads through and then cannot come back."""
    p = _p()
    a = arm_frame(p)
    assert a["reach"] > a["w"] + _SLOT_FIT


def test_but_it_goes_together_if_you_tip_it():
    """A plate on edge, tilted, presents a shorter shadow.  If that angle
    were too steep the set could not be assembled at all."""
    p = _p()
    tilt = insert_tilt(p)
    a = arm_frame(p)
    assert 20.0 < tilt < _TILT_MAX
    assert math.cos(math.radians(tilt)) == pytest.approx(
        (a["w"] + _SLOT_FIT) / a["reach"], rel=1e-6)


@pytest.mark.parametrize("arms", [3, 4, 5])
def test_the_parts_go_together_without_touching(arms):
    p = _p(hanger_arms=arms)
    base, top = build_hanger_base(p), seated_top(p)
    for i in range(arms):
        arm = seated_arm(p, i)
        assert _boolean("intersection", [arm, base]).volume < 1.0
        assert _boolean("intersection", [arm, top]).volume < 1.0


def test_each_joint_holds_in_the_direction_the_weight_pulls():
    """Nothing is clamped: the base rests on the arms' returns and the top
    ring hangs from theirs.  Push each one the way the load does and it has
    to run into the arm."""
    p = _p()
    arm = seated_arm(p, 0)
    base, top = build_hanger_base(p), seated_top(p)
    down = base.copy()
    down.apply_translation((0.0, 0.0, -1.5))     # the pot's weight
    assert _boolean("intersection", [arm, down]).volume > 20.0
    up = top.copy()
    up.apply_translation((0.0, 0.0, 1.5))        # the hook, pulling
    assert _boolean("intersection", [arm, up]).volume > 20.0


def test_the_arm_goes_through_the_top_ring_square():
    """An inclined plate through a horizontal slot needs a longer slot and
    lands its load at an angle.  The arm stands up again first."""
    k = plan(_p())
    assert k["z_gather"] < k["drop"]
    assert k["lean"] > math.radians(5.0)          # it really does lean
    arm = build_hanger_arm(_p())
    # through the ring itself the arm is a plain vertical plate, so its
    # radial footprint there is its own width and not width / cos(lean)
    sl = arm.section(plane_origin=[0, k["drop"] + 0.5 * k["t_top"], 0],
                     plane_normal=[0, 1, 0])
    xs = np.concatenate([np.array(loop)[:, 0] for loop in sl.discrete])
    assert xs.max() - xs.min() == pytest.approx(k["w_arm"], abs=0.2)
    assert xs.min() == pytest.approx(k["r_top"] - 0.5 * k["w_arm"], abs=0.2)


# ---------------------------------------------------------------------------
# the pot
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("size,drop", [("4in", 200.0), ("6in", 240.0),
                                       ("10in", 360.0)])
def test_the_arms_run_past_the_pot_without_touching_it(size, drop):
    p = _p(hanger_pot_size=size, hanger_drop=drop)
    pot = _pot_solid(p)
    for i in range(plan(p)["n"]):
        assert _boolean("intersection", [seated_arm(p, i), pot]).volume < 1.0
    assert arm_clearance(p) == pytest.approx(p.hanger_clearance, abs=0.05)


def test_the_pot_sits_on_the_seat_and_not_through_it():
    p = _p()
    k = plan(p)
    assert k["r_seat_in"] < k["pot"]["base_r"] < k["r_seat_out"]
    assert _boolean("intersection", [_pot_solid(p),
                                     build_hanger_base(p)]).volume < 1.0
    # and the whole thing is one hanging object
    whole = assembled(p)
    assert whole.bounds[1][2] == pytest.approx(
        k["drop"] + k["t_top"] + 4.0, abs=0.1)


# ---------------------------------------------------------------------------
# the load
# ---------------------------------------------------------------------------
def test_nothing_is_worked_past_the_working_stress():
    p = _p()
    s = stresses(p)
    assert max(s.values()) <= _SIGMA + 1e-6
    assert governs(p) in s
    assert any("MPa" in w and "working stress" in w for w in p.validate())


def test_the_arm_is_not_what_is_being_sized():
    """At the loads a pot reaches the tensile section is enormous, and the
    plates in bending are what the sums actually land on.  Saying so is the
    difference between a number and an understanding."""
    s = stresses(_p())
    assert s["arm"] < 0.25 * max(s["spoke"], s["top"])
    assert governs(_p()) in ("spoke", "top")


def test_a_heavier_pot_gets_more_plate():
    light, heavy = plan(_p(hanger_load=2.0)), plan(_p(hanger_load=16.0))
    assert heavy["t_base"] > light["t_base"]
    assert heavy["pull"] > light["pull"]
    # ... and it is still inside the working stress afterwards
    assert max(stresses(_p(hanger_load=16.0)).values()) <= _SIGMA + 1e-6
    assert any("a lot to ask" in w for w in _p(hanger_load=16.0).validate())


def test_one_arm_is_assumed_slack():
    """A hanger that has swung is carrying on the others, and that is the
    case worth sizing for."""
    k = plan(_p(hanger_arms=3))
    assert k["pull"] == pytest.approx(k["weight"] / 2.0)
    assert plan(_p(hanger_arms=5))["pull"] == pytest.approx(
        plan(_p(hanger_arms=5))["weight"] / 4.0)


def test_the_two_things_that_actually_break_it_are_said_out_loud():
    warn = _p().validate()
    assert any("FLAT" in w and "layer lines" in w for w in warn), warn
    assert any("creeps" in w and "PETG" in w for w in warn), warn


# ---------------------------------------------------------------------------
# the top
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("top", TOPS)
def test_every_way_of_hanging_it_still_prints_and_still_has_its_slots(top):
    p = _p(hanger_top=top)
    ring = build_hanger_top(p)
    report = audit(ring, p.overhang_limit_deg)
    assert ring.is_watertight and report.overhang_faces == 0, report
    assert len(ring.split(only_watertight=False)) == 1
    assert report.genus == plan(p)["n"] + 1
    for i in range(plan(p)["n"]):
        assert _boolean("intersection",
                        [seated_arm(p, i), seated_top(p)]).volume < 1.0


# ---------------------------------------------------------------------------
# guardrails
# ---------------------------------------------------------------------------
def test_guardrails():
    with pytest.raises(ParameterError, match="unknown hanger"):
        PotParams(hanger="rope").validate()
    with pytest.raises(ParameterError, match="unknown hanger_top"):
        _p(hanger_top="chain").validate()
    with pytest.raises(ParameterError, match="does not combine"):
        _p(sleeve=True).validate()
    with pytest.raises(ParameterError, match="hanger_arms"):
        _p(hanger_arms=2).validate()
    with pytest.raises(ParameterError, match="hanger_load"):
        _p(hanger_load=40.0).validate()
    with pytest.raises(ParameterError, match="nothing above the pot"):
        _p(hanger_drop=150.0).validate()
    with pytest.raises(ParameterError, match="unknown hanger_pot_size"):
        _p(hanger_pot_size="9in").validate()


def test_a_long_arm_is_flagged_against_the_bed():
    warn = _p(hanger_drop=420.0, hanger_pot_size="12in",
              printer="creality-ender3-v3-ke").validate()
    assert any("bed" in w for w in warn), warn


def test_the_parts_can_be_asked_for_one_at_a_time():
    for part in [x for x in PARTS[2:] if x not in WALL_PARTS]:
        assert _p(hanger=part).validate() is not None


# ---------------------------------------------------------------------------
# the wall mount: a cantilever, which is a different problem
# ---------------------------------------------------------------------------
WALL_BUILDS = [(build_hanger_cleat, "t_c"), (build_hanger_rib, "t_rib"),
               (build_hanger_yoke, "t_yoke")]


def _w(**kw) -> PotParams:
    base = dict(hanger="set", hanger_mount="wall", **FAST)
    base.update(kw)
    return PotParams(**base)


def _clash(a: trimesh.Trimesh, b: trimesh.Trimesh) -> float:
    return _boolean("intersection", [a, b]).volume


def _hung(p: PotParams) -> trimesh.Trimesh:
    """The whole ceiling set, hung where the bracket puts it."""
    w = wall_plan(p)
    k = w["k"]
    set_ = hung_set(p)
    set_.apply_translation((w["reach"], 0.0,
                            w["z_top"] - (k["drop"] + k["t_top"] + 4.0)))
    return set_


@pytest.mark.parametrize("build,thick", WALL_BUILDS)
def test_every_wall_part_is_a_flat_plate_too(build, thick):
    p = _w()
    part = build(p)
    assert part.extents[2] == min(part.extents)
    assert part.extents[2] == pytest.approx(wall_plan(p)[thick], abs=0.05)
    report = audit(part, p.overhang_limit_deg)
    assert part.is_watertight and report.overhang_faces == 0, report
    assert len(part.split(only_watertight=False)) == 1
    assert report.base_area_cm2 > 2.0


def test_the_only_holes_are_the_screws_the_slots_and_the_eye():
    p = _w()
    assert audit(build_hanger_cleat(p), 45.0).genus == wall_plan(p)["n_screw"]
    assert audit(build_hanger_rib(p), 45.0).genus == 1     # the yoke's slot
    assert audit(build_hanger_yoke(p), 45.0).genus == 1    # the eye


def test_a_ninety_degree_countersink_would_be_exactly_the_overhang_limit():
    """The heads go on the bed face, so the cone narrows going up and is an
    overhang - at 90 degrees included it is 45, which is the budget with
    nothing left. 80 keeps the margin and is what a wood screw wants."""
    assert _CSK_DEG < 45.0
    p = _w(hanger_screw_bore=6.0)
    assert audit(build_hanger_cleat(p), p.overhang_limit_deg).overhang_faces == 0
    # the shank goes all the way through and the head is recessed
    cleat = build_hanger_cleat(p)
    w = wall_plan(p)
    assert cleat.extents[2] == pytest.approx(w["t_c"], abs=0.05)
    assert w["head"] > w["bore"] > 0.0


# ---------------------------------------------------------------------------
# which way the bevel goes IS the design
# ---------------------------------------------------------------------------
def test_tipping_the_rib_the_way_the_load_does_drives_it_into_the_rail():
    """A bracket is a cantilever: the top pulls off the wall and the bottom
    presses on.  Rip the cleat so the bevel rises AWAY from the wall and
    that motion jams; rip it the usual way round and the same motion slides
    the two bevels apart, which is why a picture rail cannot hold a shelf."""
    p = _w()
    rib, cleat = seated_rib(p, -1), seated_cleat(p)
    assert _clash(rib, cleat) < 1.0
    tipped = rib.copy()
    tipped.apply_transform(trimesh.transformations.rotation_matrix(
        math.radians(1.0), [0, 1, 0], (0.0, 0.0, 0.0)))   # top out, bottom in
    assert _clash(tipped, cleat) > 20.0
    assert tipped.bounds[0][0] >= -1e-6, "the rib went through the wall"


def test_the_rib_cannot_be_pulled_straight_off_either():
    p = _w()
    rib, cleat = seated_rib(p, 1), seated_cleat(p)
    out = rib.copy()
    out.apply_translation((1.5, 0.0, 0.0))
    assert _clash(out, cleat) > 20.0
    down = rib.copy()
    down.apply_translation((0.0, 0.0, -1.5))     # the pot's weight
    assert _clash(down, cleat) > 20.0


def test_but_it_lifts_off_once_you_raise_it_past_the_rail():
    """Both 45 degree faces are parallel, so lifting separates them - but
    only by lifting the rail's whole depth does the notch clear it."""
    p = _w()
    cleat = seated_cleat(p)
    lift = wall_plan(p)["d_gap"]
    for out in (0.0, 5.0, 40.0):
        rib = seated_rib(p, 1, lift=lift)
        rib.apply_translation((out, 0.0, 0.0))
        assert _clash(rib, cleat) < 1.0, out
    # ... and not before: without the lift the notch is in the rail's way
    # every step of the journey forward
    for out in (2.0, 5.0, 8.0):
        rib = seated_rib(p, 1)
        rib.apply_translation((out, 0.0, 0.0))
        assert _clash(rib, cleat) > 5.0, out


def test_the_back_of_the_rib_really_does_bear_on_the_wall():
    """The couple has nowhere to go without it.  Below the notch the rib is
    a flat face on the wall plane, and there is a useful amount of it."""
    p = _w()
    w = wall_plan(p)
    rib = build_hanger_rib(p)
    assert rib.bounds[0][0] == pytest.approx(0.0, abs=1e-6)
    back = rib.section(plane_origin=[0.05, 0, 0], plane_normal=[1, 0, 0])
    ys = np.concatenate([np.array(loop)[:, 1] for loop in back.discrete])
    assert ys.min() == pytest.approx(0.0, abs=0.1)
    assert w["y_nb"] >= _RIB_BEAR_MIN
    # ... and the notch is above it, not through it
    assert 0.0 < w["y_nb"] < w["z_rail"] < w["y_nt"] < w["h_rib"]


# ---------------------------------------------------------------------------
# the yoke, and the only kind of catch a flat part can have
# ---------------------------------------------------------------------------
def test_the_yoke_is_caught_across_the_way_it_slides_in():
    """A part that prints flat can only grow in its own plane, so a return
    can never be wider than its slot in the direction it slides through.
    The lug is wider the OTHER way instead: lift the yoke and it lines up,
    let it down and the rib is in front of it."""
    p = _w()
    lift = _YOKE_LIFT
    ribs = [seated_rib(p, -1), seated_rib(p, 1)]
    seated, raised = seated_yoke(p), seated_yoke(p, lift)
    for rib in ribs:
        assert _clash(seated, rib) < 1.0
        assert _clash(raised, rib) < 1.0
        # seated, sliding along the wall runs a lug into a rib
        slid = seated.copy()
        slid.apply_translation((0.0, 2.0, 0.0))
        assert _clash(slid, rib) > 5.0
    # raised, a rib pulls straight off the end of the yoke
    for side, way in ((-1, -1.0), (1, 1.0)):
        off = seated_rib(p, side)
        off.apply_translation((0.0, 6.0 * way, 0.0))
        assert _clash(raised, off) < 1.0
        assert _clash(seated_yoke(p), off) > 5.0


def test_the_yoke_sits_on_the_floor_of_its_slot_which_is_where_load_puts_it():
    p = _w()
    rib = seated_rib(p, 1)
    down = seated_yoke(p, -1.5)
    assert _clash(down, rib) > 10.0
    # and it cannot be lifted past the lift travel either
    assert _clash(seated_yoke(p, _YOKE_LIFT + 1.5), rib) > 1.0


def test_the_eye_sits_on_the_neutral_axis_and_the_sum_says_so():
    """A hole costs least in the middle of a beam's depth, and this one is
    at midspan where the beam is worst - so the modulus is taken net of it
    rather than off the gross depth."""
    p = _w()
    w = wall_plan(p)
    assert w["z_eye"] == pytest.approx(
        w["z_yoke"] - 0.5 * w["slot_h"] + 0.5 * _SLOT_FIT + w["tab"]
        - 0.5 * w["d_yoke"], abs=1e-6)
    gross = w["t_yoke"] * w["d_yoke"] ** 2 / 6.0
    assert _yoke_modulus(w["t_yoke"], w["d_yoke"], 5.0) < gross


# ---------------------------------------------------------------------------
# it all fits together, with the pot on it
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kw", [dict(), dict(hanger_arms=5),
                                dict(hanger_cleat_length=200.0),
                                dict(hanger_reach=250.0, hanger_pot_size="10in",
                                     hanger_drop=360.0)])
def test_nothing_in_the_wall_set_touches_anything_else(kw):
    p = _w(**kw)
    parts = [seated_cleat(p), seated_rib(p, -1), seated_rib(p, 1),
             seated_yoke(p), _hung(p)]
    for i, a in enumerate(parts):
        for b in parts[i + 1:]:
            assert _clash(a, b) < 1.0
    assert wall_clearance(p) >= _WALL_CLEAR


def test_the_pot_hangs_off_the_wall_and_the_number_is_reported():
    p = _w()
    assert _hung(p).bounds[0][0] >= _WALL_CLEAR
    assert hook_length(p) > 0.0
    assert any("off the wall" in m for m in p.validate())
    assert any("hook or rope" in m for m in p.validate())
    # a shorter reach puts it nearer, a longer one further
    assert wall_clearance(_w(hanger_reach=200.0)) > wall_clearance(p)


def test_a_pot_that_would_touch_the_wall_is_refused_with_the_reach_it_needs():
    with pytest.raises(ParameterError, match="needs hanger_reach of at least"):
        _w(hanger_reach=100.0).validate()


# ---------------------------------------------------------------------------
# the load
# ---------------------------------------------------------------------------
def test_nothing_in_the_wall_set_is_worked_past_the_working_stress():
    p = _w()
    s = wall_stresses(p)
    assert max(s.values()) <= _SIGMA + 1e-6
    assert wall_governs(p) in s
    assert any("MPa" in m and "N.m at the fixing" in m for m in p.validate())


def test_a_rib_that_ran_to_a_point_would_be_worst_at_the_point():
    """With the load hung at the tip the section falls off faster than the
    moment does, so the worst place is out along the rib - which is why it
    keeps a tip instead of being a triangle."""
    p = _w()
    w = wall_plan(p)
    sig, at = rib_bending(p)
    assert at > 0.2 * w["reach"], "the root is not what is being sized"
    assert w["tip"] > 0.0 and rib_depth(w, w["reach"]) > w["tip"]
    assert rib_depth(w, 0.0) == pytest.approx(w["h_rib"])
    assert any("worst" in m and "out from the wall" in m for m in p.validate())


def test_the_screws_are_counted_from_the_pull_out():
    light, heavy = wall_plan(_w(hanger_load=2.0)), wall_plan(_w(hanger_load=12.0))
    assert heavy["n_screw"] > light["n_screw"]
    assert heavy["force"] > light["force"]
    for kw in (dict(hanger_load=2.0), dict(hanger_load=12.0),
               dict(hanger_load=20.0, hanger_reach=120.0)):
        assert max(wall_stresses(_w(**kw)).values()) <= _SIGMA + 1e-6
    # ... and you can say how many instead
    assert wall_plan(_w(hanger_screws=5))["n_screw"] == 5
    assert any("countersunk screws" in m and "stud" in m
               for m in _w().validate())


def test_the_couple_is_named_and_so_is_what_happens_without_the_flat_back():
    warn = _w().validate()
    assert any("couple is" in m and "pivots on the rail" in m for m in warn), warn
    assert any("FLAT BACK on the bed" in m for m in warn), warn
    assert any("slide a rib on from each side" in m for m in warn), warn


def test_forcing_too_few_screws_is_refused_rather_than_quietly_overworked():
    with pytest.raises(ParameterError, match="working stress"):
        _w(hanger_load=20.0, hanger_screws=2).validate()


# ---------------------------------------------------------------------------
# guardrails
# ---------------------------------------------------------------------------
def test_wall_guardrails():
    with pytest.raises(ParameterError, match="unknown hanger_mount"):
        _w(hanger_mount="stud").validate()
    with pytest.raises(ParameterError, match="hanger_reach should be"):
        _w(hanger_reach=40.0).validate()
    with pytest.raises(ParameterError, match="hanger_cleat_length should be"):
        _w(hanger_cleat_length=40.0).validate()
    with pytest.raises(ParameterError, match="hanger_screws should be"):
        _w(hanger_screws=1).validate()
    with pytest.raises(ParameterError, match="do not fit along a"):
        _w(hanger_load=25.0, hanger_cleat_length=60.0).validate()
    for part in WALL_PARTS:
        with pytest.raises(ParameterError, match="part of the wall mount"):
            _p(hanger=part).validate()
        assert _w(hanger=part).validate() is not None


def test_the_ceiling_set_is_untouched_by_any_of_this():
    p = _p()
    assert assembled(p).bounds[1][2] == pytest.approx(
        plan(p)["drop"] + plan(p)["t_top"] + 4.0, abs=0.1)
    assert not any("wall" in m and "N.m" in m for m in p.validate())
    # ... and asking for a wall mount hangs the same set off the bracket
    whole = assembled(_w())
    assert whole.bounds[1][2] == pytest.approx(wall_plan(_w())["h_rib"], abs=0.1)
    assert whole.bounds[0][0] == pytest.approx(0.0, abs=1e-6)


def test_a_bracket_too_big_for_the_bed_is_flagged():
    warn = _w(hanger_reach=380.0, hanger_load=1.0,
              printer="creality-ender3-v3-ke").validate()
    assert any("bed" in m and "rib" in m for m in warn), warn
