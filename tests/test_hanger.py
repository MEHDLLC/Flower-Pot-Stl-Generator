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
from flowerpot.hanger import (PARTS, TOPS, _SIGMA, _SLOT_FIT, _TILT_MAX,
                              _round, arm_frame, arm_clearance, assembled,
                              build_hanger_arm, build_hanger_base,
                              build_hanger_top, governs, insert_tilt, plan,
                              pot_of, seated_arm, seated_top, stresses)

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
    for part in PARTS[2:]:
        assert _p(hanger=part).validate() is not None
