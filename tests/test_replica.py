"""Two shop vessels, and the self-watering pair they make.

The point of this pair is that one drops into the other, so the tests are
mostly about the fit: booleans between the actual parts, not arithmetic
about what they ought to measure.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit
from flowerpot.build import _boolean
from flowerpot.replica import (KYRA, _FREEBOARD, _RIBS, _WICK_MIN_STAND,
                               build_replica_pot, build_replica_reservoir,
                               build_replica_wick, pot_plan,
                               reservoir_millilitres, reservoir_plan,
                               seated_pot, wants_wick)

FAST = dict(segments=96)


def _p(**kw) -> PotParams:
    base = dict(replica="set", **FAST)
    base.update(kw)
    return PotParams(**base)


def _wick_in_place(p: PotParams) -> trimesh.Trimesh:
    cup = build_replica_wick(p)
    cup.apply_translation((0.0, 0.0, reservoir_plan(p)["floor"]))
    return cup


# ---------------------------------------------------------------------------
# the shapes
# ---------------------------------------------------------------------------
def test_the_pot_is_the_pot_on_the_listing():
    p = _p()
    k = pot_plan(p)
    assert 2 * k["top_r"] == pytest.approx(6.00 * 25.4)
    assert 2 * k["saucer_r"] == pytest.approx(4.70 * 25.4)
    assert k["height"] == pytest.approx(5.51 * 25.4, abs=0.01)
    assert KYRA["top_od"] == pytest.approx(2 * k["top_r"])


@pytest.mark.parametrize("build", [build_replica_pot, build_replica_reservoir,
                                   build_replica_wick])
def test_every_part_prints_standing_up(build):
    p = _p()
    part = build(p)
    report = audit(part, p.overhang_limit_deg)
    assert part.is_watertight and report.overhang_faces == 0, report
    assert len(part.split(only_watertight=False)) == 1
    assert report.base_area_cm2 > 1.0


def test_the_holes_are_the_holes_and_no_others():
    """Genus is an exact count here: four drains plus the wick's hole in the
    pot, one overflow in the reservoir, four slots in the cup.  The notch in
    the rim is open at the top, so it is not a hole at all."""
    p = _p()
    assert audit(build_replica_pot(p), 45.0).genus == 5
    assert audit(build_replica_reservoir(p), 45.0).genus == 1
    assert audit(build_replica_wick(p), 45.0).genus == 4


# ---------------------------------------------------------------------------
# the fit
# ---------------------------------------------------------------------------
def test_the_pot_drops_into_the_reservoir_and_the_rims_finish_flush():
    """The whole reason for wanting both of them."""
    p = _p()
    pot, res = seated_pot(p), build_replica_reservoir(p)
    assert _boolean("intersection", [pot, res]).volume < 1.0
    assert pot.bounds[1][2] == pytest.approx(res.bounds[1][2], abs=0.05)
    # ... and it is a drop-in, not a press: real clearance all round the lip
    k = reservoir_plan(p)
    assert k["mouth_r"] - (k["pot"]["top_r"] + 2.5) > 0.8


def test_the_pot_lands_on_the_ribs_not_on_the_floor():
    p = _p()
    k = reservoir_plan(p)
    pot = seated_pot(p)
    assert pot.bounds[0][2] == pytest.approx(k["z_sit"], abs=0.01)
    assert k["z_sit"] - k["floor"] == pytest.approx(p.replica_standoff)
    # there really is something under it: sweep the ring the saucer lands
    # on and see how many separate pieces of reservoir it meets
    res = build_replica_reservoir(p)
    seat = trimesh.creation.annulus(r_min=k["pot"]["saucer_r"] - 8.0,
                                    r_max=k["pot"]["saucer_r"] + 2.0,
                                    height=2.0, sections=96)
    seat.apply_translation((0.0, 0.0, k["z_sit"] - 1.0))
    landing = _boolean("intersection", [res, seat])
    assert landing.volume > 100.0
    assert len(landing.split(only_watertight=False)) == _RIBS


def test_the_wick_reaches_the_water_without_touching_either_part():
    p = _p()
    cup = _wick_in_place(p)
    assert _boolean("intersection", [cup, build_replica_reservoir(p)]).volume < 1.0
    assert _boolean("intersection", [cup, seated_pot(p)]).volume < 1.0
    k = reservoir_plan(p)
    # it stands on the reservoir's floor and its flange clears the pot's
    assert cup.bounds[0][2] == pytest.approx(k["floor"], abs=0.01)
    assert cup.bounds[1][2] > k["z_sit"] + k["pot"]["floor"]


def test_the_soil_never_sits_in_water():
    """The overflow has to be below the pot's floor, or the reservoir just
    fills the pot up."""
    p = _p()
    k = reservoir_plan(p)
    assert k["z_sit"] - k["z_water"] == pytest.approx(_FREEBOARD)
    assert k["z_water"] < k["z_sit"]
    assert reservoir_millilitres(p) > 100.0


# ---------------------------------------------------------------------------
# the trade the reservoir cannot dodge
# ---------------------------------------------------------------------------
def test_the_standoff_is_what_buys_the_water():
    """Flush rims, a reservoir, and the shop bucket's depth: pick two.  Ask
    for the bucket's depth and the water goes away, on purpose."""
    tall, flat = _p(), _p(replica_standoff=0.0)
    assert reservoir_millilitres(flat) == 0.0
    assert not wants_wick(flat)
    assert (reservoir_plan(tall)["depth"] - reservoir_plan(flat)["depth"]
            == pytest.approx(tall.replica_standoff))
    # ... and it still builds, and the rims are still flush
    pot, res = seated_pot(flat), build_replica_reservoir(flat)
    assert audit(res, flat.overhang_limit_deg).overhang_faces == 0
    assert pot.bounds[1][2] == pytest.approx(res.bounds[1][2], abs=0.05)
    assert _boolean("intersection", [pot, res]).volume < 1.0


def test_a_measured_pot_still_fits_its_reservoir():
    """The listing may be wrong; a tape measure is not.  Whatever numbers
    go in, the reservoir is derived from them and the pair still nests."""
    p = _p(replica_pot_top=7.32 * 25.4, replica_pot_base=5.4 * 25.4,
           replica_pot_height=7.32 * 25.4)
    pot, res = seated_pot(p), build_replica_reservoir(p)
    assert _boolean("intersection", [pot, res]).volume < 1.0
    assert pot.bounds[1][2] == pytest.approx(res.bounds[1][2], abs=0.05)
    assert audit(res, p.overhang_limit_deg).overhang_faces == 0


def test_plain_replicas_have_no_plumbing_in_them():
    p = _p(replica_plumbing=False)
    res = build_replica_reservoir(p)
    assert audit(res, p.overhang_limit_deg).genus == 0     # no overflow
    assert audit(build_replica_pot(p), 45.0).genus == 4    # drains only
    # a bare wall and nothing standing off the floor
    k = reservoir_plan(p)
    seat = trimesh.creation.annulus(r_min=k["pot"]["saucer_r"] - 8.0,
                                    r_max=k["pot"]["saucer_r"] + 2.0,
                                    height=2.0, sections=96)
    seat.apply_translation((0.0, 0.0, k["z_sit"] - 1.0))
    assert _boolean("intersection", [res, seat]).volume < 1.0


# ---------------------------------------------------------------------------
# guardrails
# ---------------------------------------------------------------------------
def test_guardrails():
    with pytest.raises(ParameterError, match="unknown replica"):
        PotParams(replica="terracotta").validate()
    with pytest.raises(ParameterError, match="does not combine"):
        _p(bouquet=True).validate()
    with pytest.raises(ParameterError, match="is not a pot"):
        pot_plan(_p(replica_pot_base=20.0))
    with pytest.raises(ParameterError, match="no wall between"):
        pot_plan(_p(replica_pot_height=20.0))
    with pytest.raises(ParameterError, match="too shallow for a wick"):
        build_replica_wick(_p(replica_standoff=0.0))


def test_the_saucer_being_a_foot_is_said_out_loud():
    warn = _p().validate()
    assert any("flared foot" in w for w in warn), warn
    assert any("ml" in w for w in warn), warn
