"""A cover for the nursery pot the plant came in.

A sleeve is a pot with a pot inside it, so the tests split the same way:
the outside has to be everything the generator can already do, and the
inside has to actually take the nursery pot - land it on its step, leave
the well under it, and never close in on it anywhere up the wall.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit
from flowerpot.build import _boolean
from flowerpot.sleeve import (_HEIGHT_RATIO, _WALL_MIN, build_sleeve,
                              cavity_radius, cavity_rings, flat_factor,
                              nursery, nursery_solid, plan, sleeve_params,
                              wall_at, well_millilitres)
from flowerpot.underpot import NURSERY, _BASE_RATIO

FAST = dict(segments=96, vertical_step=2.5)
STYLES = ["classic_tapered", "hexagonal", "square", "low_poly_faceted",
          "ribbed_spiral"]


def _p(**kw) -> PotParams:
    base = dict(sleeve=True, **FAST)
    base.update(kw)
    return PotParams(**base)


# ---------------------------------------------------------------------------
# does it print?
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("style", STYLES)
def test_a_sleeve_prints_standing_up(style):
    p = _p(pot_style=style)
    part = build_sleeve(p)
    report = audit(part, p.overhang_limit_deg)
    assert part.is_watertight and report.overhang_faces == 0, report
    assert len(part.split(only_watertight=False)) == 1
    assert report.genus == 0                   # a cachepot has no holes


@pytest.mark.parametrize("size", ["4in", "6in", "10in"])
def test_another_size_prints_and_still_takes_its_pot(size):
    p = _p(sleeve_pot_size=size)
    part = build_sleeve(p)
    report = audit(part, p.overhang_limit_deg)
    assert part.is_watertight and report.overhang_faces == 0, report
    assert _boolean("intersection", [part, nursery_solid(p)]).volume < 1.0


# ---------------------------------------------------------------------------
# a sleeve is a pot
# ---------------------------------------------------------------------------
def test_the_outside_is_the_pot_builder_doing_its_usual_job():
    """The point of the design: every style and texture already works, and
    it works because the sleeve hands the pot builder a PotParams."""
    q = sleeve_params(_p())
    assert q.validate() is not None            # it is a legal pot
    assert q.drainage_pattern == "none" and not q.sleeve
    plain = build_sleeve(_p())
    textured = build_sleeve(_p(surface_texture="honeycomb"))
    assert len(textured.faces) > len(plain.faces)
    assert textured.volume != pytest.approx(plain.volume, rel=1e-3)
    hexy = build_sleeve(_p(pot_style="hexagonal"))
    assert hexy.extents[0] != pytest.approx(plain.extents[0], rel=1e-3)


def test_the_height_and_the_mouth_come_off_the_pot_inside():
    p = _p()
    k, q = plan(p), sleeve_params(p)
    assert k["height"] == pytest.approx(
        k["floor"] + p.sleeve_well + k["pot"]["height"] - p.sleeve_reveal)
    assert q.height == pytest.approx(k["height"])
    # the mouth clears the pot where the rim crosses it, plus a wall
    assert (0.5 * q.top_diameter * flat_factor(p)
            >= cavity_radius(k, k["height"]) + p.wall_thickness - 1e-6)


# ---------------------------------------------------------------------------
# does the nursery pot go in?
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("style", STYLES)
def test_the_nursery_pot_drops_in_without_touching(style):
    p = _p(pot_style=style)
    assert _boolean("intersection",
                    [build_sleeve(p), nursery_solid(p)]).volume < 1.0


def test_the_pot_lands_on_the_step_rather_than_the_floor():
    """Clearance everywhere is a pot that keeps going.  Drop it and the
    step has to be what stops it - and the well has to survive."""
    p = _p()
    k = plan(p)
    sleeve = build_sleeve(p)
    dropped = nursery_solid(p)
    dropped.apply_translation((0.0, 0.0, -1.5))
    clash = _boolean("intersection", [sleeve, dropped])
    assert clash.volume > 100.0
    assert clash.bounds[1][2] < k["z_seat"] + 1.0, "it is jamming on the wall"


@pytest.mark.parametrize("style", ["hexagonal", "square"])
def test_a_polygon_puts_its_flats_on_the_pot_not_its_corners(style):
    """A section is cut from its corner radius.  Use the pot's radius as
    that and a square sleeve gets a hole its own pot cannot go in, pinched
    at the four flats."""
    p = _p(pot_style=style)
    k = plan(p)
    flat = flat_factor(p)
    assert flat < 1.0
    for r, z in cavity_rings(p):
        assert r * flat == pytest.approx(cavity_radius(k, z), abs=1e-6) \
            or z <= k["z_seat"]
    # the inscribed circle of the cavity is on the pot, with the fit on it
    top = k["height"]
    assert cavity_rings(p)[-1][0] * flat > k["pot"]["top_r"]
    assert wall_at(p, 0.5 * top) >= _WALL_MIN


def test_the_wall_never_closes_in_on_the_pot():
    p = _p()
    k = plan(p)
    assert min(wall_at(p, float(z))
               for z in np.linspace(0.0, k["height"], 121)) >= _WALL_MIN


# ---------------------------------------------------------------------------
# the well
# ---------------------------------------------------------------------------
def test_the_well_is_under_the_pot_and_is_reported():
    p = _p()
    k = plan(p)
    assert k["z_seat"] == pytest.approx(k["floor"] + p.sleeve_well)
    assert k["r_well"] < k["r_seat"], "the step has nothing to sit on"
    assert well_millilitres(p) > 30.0
    assert (well_millilitres(_p(sleeve_well=28.0))
            == pytest.approx(2.0 * well_millilitres(p), rel=1e-6))
    assert any("ml" in w and "no drain" in w for w in p.validate())


def test_standing_the_pot_on_the_floor_is_allowed_and_is_argued_with():
    p = _p(sleeve_well=0.0)
    assert well_millilitres(p) == 0.0
    assert audit(build_sleeve(p), p.overhang_limit_deg).overhang_faces == 0
    assert any("holes are blocked" in w for w in p.validate())


def test_the_step_faces_the_sky():
    """The cavity only ever gets wider going up - well, then step, then the
    pot's own taper - which is why none of it needs a cone."""
    k = plan(_p())
    rings = cavity_rings(_p())
    assert all(b[0] >= a[0] - 1e-9 for a, b in zip(rings, rings[1:]))
    assert all(b[1] >= a[1] - 1e-9 for a, b in zip(rings, rings[1:]))
    assert cavity_radius(k, k["height"]) > cavity_radius(k, k["z_seat"] + 1.0)


# ---------------------------------------------------------------------------
# the reveal
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("reveal", [-15.0, 0.0, 12.0])
def test_the_reveal_puts_the_rims_where_it_says(reveal):
    p = _p(sleeve_reveal=reveal)
    k = plan(p)
    sleeve = build_sleeve(p)
    pot_top = k["z_seat"] + k["pot"]["height"]
    assert pot_top - sleeve.bounds[1][2] == pytest.approx(reveal, abs=0.05)
    assert _boolean("intersection", [sleeve, nursery_solid(p)]).volume < 1.0


# ---------------------------------------------------------------------------
# sizing from a pot you did not make
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("size", sorted(NURSERY))
def test_a_nominal_size_fills_in_all_three_measurements(size):
    k = nursery(_p(sleeve_pot_size=size))
    assert 2.0 * k["top_r"] == pytest.approx(NURSERY[size])
    assert 2.0 * k["base_r"] == pytest.approx(_BASE_RATIO * NURSERY[size])
    assert k["height"] == pytest.approx(_HEIGHT_RATIO * NURSERY[size])
    assert k["slope"] > 0.0, "a nursery pot is wider at the top"
    assert any("nominal size" in w for w in _p(sleeve_pot_size=size).validate())


def test_measured_numbers_win_over_the_table():
    p = _p(sleeve_pot_top=130.0, sleeve_pot_base=100.0,
           sleeve_pot_height=118.0)
    k = nursery(p)
    assert (2 * k["top_r"], 2 * k["base_r"], k["height"]) == (130.0, 100.0,
                                                              118.0)
    assert _boolean("intersection",
                    [build_sleeve(p), nursery_solid(p)]).volume < 1.0
    assert not any("nominal" in w for w in p.validate())


# ---------------------------------------------------------------------------
# guardrails
# ---------------------------------------------------------------------------
def test_a_vase_silhouette_is_refused_rather_than_half_working():
    """They all neck in at the mouth and narrow at the foot.  A sleeve has
    a pot inside it and a well under it, so there is nothing to negotiate."""
    for vase in ("classic", "bud", "gourd", "bottle", "cone", "wave"):
        with pytest.raises(ParameterError, match="cannot be a sleeve"):
            _p(vase_profile=vase).validate()


def test_a_silhouette_that_pinches_says_where_and_by_how_much():
    with pytest.raises(ParameterError, match="closes onto the nursery pot"):
        _p(sleeve_base=95.0).validate()
    with pytest.raises(ParameterError, match="Raise sleeve_fit by about"):
        _p(belly=-14.0).validate()


def test_guardrails():
    with pytest.raises(ParameterError, match="unknown sleeve_pot_size"):
        _p(sleeve_pot_size="9in").validate()
    with pytest.raises(ParameterError, match="does not combine"):
        _p(underpot="set").validate()
    with pytest.raises(ParameterError, match="is not a nursery pot"):
        _p(sleeve_pot_base=40.0).validate()
    with pytest.raises(ParameterError, match="out of proportion"):
        _p(sleeve_pot_height=600.0).validate()
    with pytest.raises(ParameterError, match="not a well"):
        _p(sleeve_well=3.0).validate()
    with pytest.raises(ParameterError, match="barely taller"):
        _p(sleeve_reveal=140.0).validate()
    with pytest.raises(ParameterError, match="40-500 mm"):
        _p(sleeve_pot_top=20.0, sleeve_pot_base=14.0,
           sleeve_pot_height=19.0).validate()
