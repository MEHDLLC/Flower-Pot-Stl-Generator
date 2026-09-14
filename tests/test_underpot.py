"""The three things that go under a pot you did not print.

All three are cut from one measurement - the pot's base - so the tests are
about whether that one number is enough: does the pot drop into the tray,
does it stand on the ribs rather than in the water, do the feet stay under
the pot, and does the disc fit down the inside.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit
from flowerpot.build import _boolean
from flowerpot.underpot import (NURSERY, PARTS, _BASE_RATIO, _MESH_WEB,
                                _RISER_EDGE, build_under_mesh,
                                build_under_riser, build_under_tray,
                                mesh_diameter, mesh_grid, plan, pot_base,
                                rib_pitch, riser_radius, riser_ring_diameter,
                                tray_millilitres)

FAST = dict(segments=96)
SIZES = [dict(under_pot_base=b) for b in (70.0, 110.0, 190.0)]


def _p(**kw) -> PotParams:
    base = dict(underpot="set", **FAST)
    base.update(kw)
    return PotParams(**base)


def _pot_stand_in(p: PotParams, z: float) -> trimesh.Trimesh:
    """A stand-in for the pot: a cylinder of its base diameter, put down at
    height ``z``."""
    k = plan(p)
    cyl = trimesh.creation.cylinder(radius=0.5 * k["base"], height=60.0,
                                    sections=120)
    cyl.apply_translation((0.0, 0.0, z + 30.0))
    return cyl


# ---------------------------------------------------------------------------
# does it print?
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kw", SIZES)
def test_every_part_prints_standing_up(kw):
    p = _p(**kw)
    for build in (build_under_tray, build_under_riser, build_under_mesh):
        part = build(p)
        report = audit(part, p.overhang_limit_deg)
        assert part.is_watertight and report.overhang_faces == 0, report
        assert len(part.split(only_watertight=False)) == 1


def test_the_holes_are_the_mesh_and_no_others():
    """A tray and a foot have no holes at all; the disc has exactly the
    ones the pattern asked for."""
    p = _p()
    assert audit(build_under_tray(p), 45.0).genus == 0
    assert audit(build_under_riser(p), 45.0).genus == 0
    assert audit(build_under_mesh(p), 45.0).genus == len(mesh_grid(p)["sites"])


def test_a_flat_saucer_is_allowed_and_is_said_to_be_a_flat_saucer():
    p = _p(under_waffle=0.0)
    report = audit(build_under_tray(p), p.overhang_limit_deg)
    assert report.overhang_faces == 0 and report.genus == 0
    assert tray_millilitres(p) == 0.0
    assert any("sitting in all of it" in w for w in p.validate())


# ---------------------------------------------------------------------------
# does the pot fit, and does it stay out of the water?
# ---------------------------------------------------------------------------
def test_the_pot_drops_into_the_tray_and_lands_on_the_ribs():
    p = _p()
    k = plan(p)
    tray = build_under_tray(p)
    # sat on the rib tops it touches nothing: clear of the wall all round
    on_top = _pot_stand_in(p, k["floor"] + k["waffle"])
    assert _boolean("intersection", [on_top, tray]).volume < 1.0
    # and it cannot get any lower, because the ribs are in the way
    lower = _pot_stand_in(p, k["floor"] + k["waffle"] - 1.0)
    assert _boolean("intersection", [lower, tray]).volume > 100.0


def test_the_pot_stands_above_the_water_and_the_water_is_all_one_puddle():
    """A continuous waffle is a tray full of closed cells, each keeping its
    own puddle.  Every crossing is broken, so the water under the rib tops
    is a single connected body that can level and be poured out."""
    p = _p()
    k = plan(p)
    tray = build_under_tray(p)
    probe = trimesh.creation.cylinder(radius=k["r_in"] - 0.4,
                                      height=k["waffle"] - 0.4, sections=120)
    probe.apply_translation((0.0, 0.0, k["floor"] + 0.5 * (k["waffle"] - 0.4)))
    water = _boolean("difference", [probe, tray])
    assert len(water.split(only_watertight=False)) == 1
    assert water.volume / 1000.0 > 20.0
    assert tray_millilitres(p) > 20.0
    # twice the rib height is more water, and it is reported
    assert tray_millilitres(_p(under_waffle=12.0)) > 1.8 * tray_millilitres(p)
    assert any("ml under the rib tops" in w for w in p.validate())


def test_the_ribs_cross_rather_than_radiate():
    """Wherever the pot is put down it has to land on at least three ribs,
    which a radial fan cannot promise near the middle.  Slice a slab out of
    the waffle and the pieces have to run both ways."""
    p = _p()
    k = plan(p)
    tray = build_under_tray(p)
    slab = trimesh.creation.box(extents=(4.0 * k["r_in"], 4.0 * k["r_in"], 1.0))
    slab.apply_translation((0.0, 0.0, k["floor"] + 0.5 * k["waffle"]))
    pieces = _boolean("intersection", [tray, slab]).split(only_watertight=False)
    along_x = [b for b in pieces if b.extents[0] > 1.5 * b.extents[1]]
    along_y = [b for b in pieces if b.extents[1] > 1.5 * b.extents[0]]
    assert along_x and along_y, "the waffle only runs one way"
    assert len(along_x) == len(along_y), "the grid is not square"
    # and every junction is broken, so the ribs come apart into stubs
    assert len(pieces) > 2 * (2.0 * k["r_in"] / rib_pitch(p))


# ---------------------------------------------------------------------------
# the feet
# ---------------------------------------------------------------------------
def test_the_feet_stay_under_the_pot():
    """A foot that shows past the edge of the base is a foot the pot can
    tip over."""
    for kw in SIZES:
        p = _p(**kw)
        k = plan(p)
        reach = 0.5 * riser_ring_diameter(p) + riser_radius(p)
        assert reach <= 0.5 * k["base"] - _RISER_EDGE + 1e-9, kw
        assert riser_ring_diameter(p) > 0.25 * k["base"]


def test_a_foot_is_dished_so_the_pot_does_not_walk_off():
    p = _p()
    h = p.under_riser_height
    riser = build_under_riser(p)
    assert riser.bounds[1][2] == pytest.approx(h, abs=0.05)
    # just under the top it is a ring, not a disc: that is the dish
    ring = riser.section(plane_origin=[0, 0, h - 0.6], plane_normal=[0, 0, 1])
    assert len(ring.discrete) == 2
    # and it narrows going up, which is the direction that cannot overhang
    low = riser.section(plane_origin=[0, 0, 1.0], plane_normal=[0, 0, 1])
    wide = np.hypot(*np.array(low.discrete[0]).T[:2]).max()
    assert wide > np.hypot(*np.array(ring.discrete[0]).T[:2]).max()


def test_how_many_feet_is_a_real_choice_and_is_explained():
    warn = _p(under_feet=3).validate()
    assert any("cannot rock" in w for w in warn), warn
    assert any("print 4 risers" in w for w in _p(under_feet=4).validate())


# ---------------------------------------------------------------------------
# the mesh disc
# ---------------------------------------------------------------------------
def test_the_disc_fits_down_the_inside_of_the_pot():
    p = _p()
    assert mesh_diameter(p) < plan(p)["base"]
    disc = build_under_mesh(p)
    assert disc.extents[0] == pytest.approx(mesh_diameter(p), abs=0.6)
    # an explicit diameter wins over the derived one
    assert mesh_diameter(_p(under_mesh_diameter=64.0)) == 64.0


def test_the_web_between_holes_is_what_limits_the_open_area():
    p = _p()
    g = mesh_grid(p)
    assert g["pitch"] - 2.0 * g["hole"] >= _MESH_WEB - 1e-9
    assert 2.0 * g["hole"] >= 2.8 - 1e-9         # still drains, not just soil
    assert 0.15 < g["open_fraction"] < 0.60
    # asking for more gets more, right up until the web says no
    assert (mesh_grid(_p(under_mesh_open=0.5))["open_fraction"]
            > g["open_fraction"])
    assert any("% open" in w for w in p.validate())


def test_the_legs_print_up_and_are_said_to():
    p = _p()
    with_legs = build_under_mesh(p)
    without = build_under_mesh(_p(under_mesh_legs=False))
    assert with_legs.extents[2] > without.extents[2]
    assert any("legs up" in w for w in p.validate())
    # the disc still lies flat on the plate, legs or no legs
    for disc in (with_legs, without):
        assert audit(disc, 45.0).base_area_cm2 > 10.0


# ---------------------------------------------------------------------------
# sizing from a pot you did not make
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("size", sorted(NURSERY))
def test_a_nominal_size_is_a_nominal_size(size):
    p = _p(under_pot_size=size)
    assert pot_base(p) == pytest.approx(_BASE_RATIO * NURSERY[size])
    assert pot_base(p) < NURSERY[size], "a pot's base is not its top"
    warn = p.validate()
    assert any("nominal size" in w and "across the TOP" in w for w in warn)


def test_one_measurement_drives_all_three_parts():
    small, big = plan(_p(under_pot_base=80.0)), plan(_p(under_pot_base=200.0))
    assert big["r_in"] > small["r_in"]
    assert (riser_ring_diameter(_p(under_pot_base=200.0))
            > riser_ring_diameter(_p(under_pot_base=80.0)))
    assert (mesh_diameter(_p(under_pot_base=200.0))
            > mesh_diameter(_p(under_pot_base=80.0)))


def test_guardrails():
    with pytest.raises(ParameterError, match="unknown underpot"):
        PotParams(underpot="feet").validate()
    with pytest.raises(ParameterError, match="unknown under_pot_size"):
        _p(under_pot_size="9in").validate()
    with pytest.raises(ParameterError, match="does not combine"):
        _p(moss_pole="set").validate()
    with pytest.raises(ParameterError, match="under_feet"):
        _p(under_feet=5).validate()
    with pytest.raises(ParameterError, match="outside what these parts"):
        _p(under_pot_base=20.0).validate()
    with pytest.raises(ParameterError, match="texture, not a stand-off"):
        _p(under_waffle=1.5).validate()
    with pytest.raises(ParameterError, match="under_riser_height"):
        build_under_riser(_p(under_riser_height=200.0))


def test_the_parts_can_be_asked_for_one_at_a_time():
    for part in PARTS[2:]:
        p = _p(underpot=part)
        assert p.validate() is not None
