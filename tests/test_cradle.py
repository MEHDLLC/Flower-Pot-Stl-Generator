"""A pot that sits in a dish and drinks out of it.

Three things have to be true at once and none of them is arithmetic, so
they are tested against the actual meshes: the pot has to *land* on the
dish rather than hover in it or wedge into it; there has to be a way for
water to get from a watering can into the reservoir; and both parts have to
come off a bed with no supports under them.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit
from flowerpot.build import _boolean
from flowerpot.cradle import (BOWLS, _SEAT_CLEAR, bowl_radius, build_cradle_dish,
                              build_cradle_pot, keel_radius, plan, seated_pot,
                              water_gap, water_millilitres)
from flowerpot.profile import slope_budget

FAST = dict(segments=96)


def _p(**kw) -> PotParams:
    base = dict(cradle="set", **FAST)
    base.update(kw)
    return PotParams(**base)


# ---------------------------------------------------------------------------
# does it print?
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bowl", BOWLS)
def test_both_parts_print_standing_up(bowl):
    p = _p(cradle_bowl=bowl)
    for build in (build_cradle_pot, build_cradle_dish):
        part = build(p)
        report = audit(part, p.overhang_limit_deg)
        assert part.is_watertight and report.overhang_faces == 0, report
        assert len(part.split(only_watertight=False)) == 1
        assert report.base_area_cm2 > 10.0        # both stand on a real foot


def test_the_holes_are_the_slots_and_no_others():
    """Genus counts them exactly: every wicking slot is a window through the
    keel, and the dish has no hole at all - a notch cut down into a rim is
    open at the top, so it never closes into one."""
    p = _p()
    assert audit(build_cradle_pot(p), 45.0).genus == p.cradle_drains
    assert audit(build_cradle_dish(p), 45.0).genus == 0
    assert audit(build_cradle_pot(_p(cradle_drains=14)), 45.0).genus == 14


def test_the_dish_spends_its_whole_budget_and_no_more():
    """A round bowl printed standing up is a 90 degree overhang at its pole.
    Ours is the steepest arc that is not: it should come *close* to the
    limit - a dish comfortably inside it would be a dish nobody wanted."""
    p = _p(cradle_bowl="round")
    report = audit(build_cradle_dish(p), p.overhang_limit_deg)
    assert report.overhang_faces == 0
    assert report.worst_overhang_deg > p.overhang_limit_deg - 8.0, report
    # ... and the number it stops at is the declared budget, not luck
    assert math.tan(math.radians(report.worst_overhang_deg)) <= \
        slope_budget(p, 0.0) + 1e-6


# ---------------------------------------------------------------------------
# does it sit down?
# ---------------------------------------------------------------------------
def test_the_pot_seats_in_the_dish_at_the_height_it_was_asked_for():
    p = _p()
    pot, dish = seated_pot(p), build_cradle_dish(p)
    assert _boolean("intersection", [pot, dish]).volume < 1.0
    assert pot.bounds[1][2] == pytest.approx(p.cradle_height, abs=0.05)
    assert dish.bounds[1][2] == pytest.approx(plan(p)["z_dish"], abs=0.05)


def test_it_lands_on_the_seat_instead_of_hanging_in_the_bowl():
    """Clearance everywhere is not a fit - it is a pot that falls through.
    Drop it a millimetre and the seat has to be what stops it."""
    p = _p()
    dish = build_cradle_dish(p)
    dropped = seated_pot(p)
    dropped.apply_translation((0.0, 0.0, -1.0))
    clash = _boolean("intersection", [dropped, dish])
    assert clash.volume > 50.0
    # and it is the rim it lands on, not the bottom of the bowl
    assert clash.bounds[0][2] > plan(p)["z_a"] - 2.0


def test_the_seat_is_one_cone_with_the_fit_left_on_it():
    """The dish's rim and the pot's keel are the same surface, moved apart
    by ``_SEAT_CLEAR`` on the perpendicular.  Anything else and the pot
    either rocks on a high spot or jams before it is down."""
    k = plan(_p())
    slack = _SEAT_CLEAR * math.hypot(1.0, k["s"])
    for z in np.linspace(k["z_a"], k["z_dish"], 9):
        # the rim's top face at this height, from the geometry it was cut on
        assert (keel_radius(k, z) + slack) == pytest.approx(
            k["r_rim"] - k["s"] * (k["z_dish"] - z), abs=1e-6)
    assert slack / math.hypot(1.0, k["s"]) == pytest.approx(_SEAT_CLEAR)


# ---------------------------------------------------------------------------
# can you water it?
# ---------------------------------------------------------------------------
def test_the_fill_notch_opens_onto_the_water():
    """Straight at the notch there is nothing between the outside air and
    the gap the water sits in; a quarter turn away the rim is still a rim."""
    p = _p(cradle_windows=1)
    k = plan(p)
    pot, dish = seated_pot(p), build_cradle_dish(p)
    z = k["z_dish"] - 5.0
    r = np.linspace(keel_radius(k, z) + 1.0, k["r_rim"] + 6.0, 25)
    through = np.column_stack([r, np.zeros_like(r), np.full_like(r, z)])
    assert not pot.contains(through).any()
    assert not dish.contains(through).any()
    away = np.column_stack([-r, np.zeros_like(r), np.full_like(r, z)])
    assert dish.contains(away).sum() >= 3, "the notch took the whole rim"
    # ... and the way down from there is clear all the way to the floor
    for zz in (k["z_brim"] - 1.0, k["z_fill"], k["z_pad"] + 2.0):
        mid = np.array([[0.5 * (keel_radius(k, zz) + bowl_radius(k, zz)),
                         0.0, zz]])
        assert not pot.contains(mid)[0] and not dish.contains(mid)[0]


@pytest.mark.parametrize("n,loops", [(0, 2), (1, 1), (2, 2), (3, 3)])
def test_the_notches_are_where_they_were_asked_for(n, loops):
    """Slice the rim: an unbroken one is two loops (outside and inside), and
    every notch cut through it leaves one arc fewer."""
    p = _p(cradle_windows=n)
    dish = build_cradle_dish(p)
    ring = dish.section(plane_origin=[0, 0, plan(p)["z_dish"] - 3.0],
                        plane_normal=[0, 0, 1])
    assert ring is not None and len(ring.discrete) == loops


def test_the_notch_is_the_overflow_as_well_as_the_inlet():
    """It is the only opening in the dish, so it sets the water line: above
    its sill the water runs back out at you instead of into the soil."""
    p = _p()
    k = plan(p)
    assert k["z_brim"] < k["z_a"]                  # lower than the rim itself
    assert k["z_brim"] > k["z_fill"] + 2.0         # ... but above the wicking
    assert water_millilitres(p, k["z_brim"]) > water_millilitres(p)
    # with no notch there is nothing to spill from, so the rim is the limit
    assert plan(_p(cradle_windows=0))["z_brim"] == pytest.approx(k["z_a"])


# ---------------------------------------------------------------------------
# does it drink?
# ---------------------------------------------------------------------------
def test_the_soil_reaches_the_water_through_the_keel():
    p = _p()
    k = plan(p)
    # the keel hangs below the water line, and the slots span that line
    assert k["z_pad"] < k["z_fill"]
    assert k["z_pad"] + k["floor"] < k["z_fill"], "the soil never gets wet"
    # the slots are cut in the keel and stop short of the seat collar
    assert k["r_pad"] < k["slot_r0"] < k["slot_r1"] < k["r_rim"] - k["collar"]
    # and there really are that many of them down there
    pot = build_cradle_pot(p)
    ring = pot.section(plane_origin=[0, 0, 0.5 * (k["z_fill"] - k["z_pad"])],
                       plane_normal=[0, 0, 1])
    assert len(ring.discrete) == p.cradle_drains


def test_the_water_gap_only_opens_downwards():
    """The keel falls at the overhang limit and every bowl is shallower than
    that, so the two can only converge going up - which is what makes the
    rim, and only the rim, the place they touch."""
    k = plan(_p())
    z = np.linspace(k["z_pad"], k["z_a"] - 0.5, 60)
    gap = [bowl_radius(k, v) - keel_radius(k, v) for v in z]
    assert all(a >= b - 1e-6 for a, b in zip(gap, gap[1:]))
    assert gap[-1] < 1.0 and water_gap(k) > 2.0


def test_the_bowl_is_the_water_dial():
    ml = {b: water_millilitres(_p(cradle_bowl=b)) for b in BOWLS}
    assert ml["tub"] > ml["round"] > ml["cone"] > 0.0
    assert any("ml" in w for w in _p().validate())


def test_closing_the_keel_makes_a_cachepot():
    p = _p(cradle_drains=0)
    assert audit(build_cradle_pot(p), 45.0).genus == 0
    assert any("cachepot" in w for w in p.validate())


# ---------------------------------------------------------------------------
# other sizes
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kw", [
    dict(cradle_diameter=80.0, cradle_height=80.0, cradle_dish_height=32.0,
         cradle_keel=18.0),
    dict(cradle_diameter=180.0, cradle_height=160.0, cradle_dish_height=64.0,
         cradle_keel=40.0),
    dict(cradle_lip=False, cradle_flare=0.0, cradle_bowl="tub"),
    dict(wall_thickness=4.0, overhang_limit_deg=40.0),
])
def test_a_pair_at_another_size_still_nests_and_still_prints(kw):
    p = _p(**kw)
    pot, dish = seated_pot(p), build_cradle_dish(p)
    assert _boolean("intersection", [pot, dish]).volume < 1.0
    assert pot.bounds[1][2] == pytest.approx(p.cradle_height, abs=0.05)
    for part in (pot, dish):
        report = audit(part, p.overhang_limit_deg)
        assert part.is_watertight and report.overhang_faces == 0, report


# ---------------------------------------------------------------------------
# guardrails
# ---------------------------------------------------------------------------
def test_guardrails():
    with pytest.raises(ParameterError, match="unknown cradle"):
        PotParams(cradle="bowl").validate()
    with pytest.raises(ParameterError, match="unknown cradle_bowl"):
        _p(cradle_bowl="hemisphere").validate()
    with pytest.raises(ParameterError, match="does not combine"):
        _p(bouquet=True).validate()
    with pytest.raises(ParameterError, match="cradle_windows"):
        _p(cradle_windows=9).validate()
    with pytest.raises(ParameterError, match="not a reservoir"):
        _p(cradle_keel=38.0).validate()
    with pytest.raises(ParameterError, match="comes to a point"):
        _p(cradle_keel=60.0).validate()
    with pytest.raises(ParameterError, match="no flank left to slot"):
        _p(cradle_keel=12.0).validate()
    with pytest.raises(ParameterError, match="leaves only"):
        _p(cradle_height=50.0).validate()


def test_nothing_you_can_set_closes_the_water_gap():
    """The backstop in ``check_cradle`` should be unreachable: sweep the
    dials and every pair that solves at all has water in it."""
    seen = 0
    for dia in (60.0, 90.0, 120.0, 180.0):
        for dish_h in (28.0, 44.0, 64.0):
            for keel in (16.0, 26.0, 40.0):
                for bowl in BOWLS:
                    for limit in (35.0, 45.0, 55.0):
                        p = _p(cradle_diameter=dia, cradle_dish_height=dish_h,
                               cradle_keel=keel, cradle_bowl=bowl,
                               cradle_height=dish_h + 60.0,
                               overhang_limit_deg=limit)
                        try:
                            k = plan(p)
                            p.validate()
                        except ParameterError:
                            continue        # said no, with a reason: fine
                        seen += 1
                        assert water_gap(k) >= 2.0, (dia, dish_h, keel, bowl)
                        assert water_millilitres(p) > 0.0
    assert seen > 50, f"only {seen} of the sweep solved at all"


def test_no_notch_is_reported_rather_than_quietly_shipped():
    warn = _p(cradle_windows=0).validate()
    assert any("nowhere to pour" in w for w in warn), warn
