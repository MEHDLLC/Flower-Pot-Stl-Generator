"""The bouquet planter: a ring of blooms around a flower-shaped mouth."""

from __future__ import annotations

import math

import pytest

from flowerpot import ParameterError, PotParams, audit, build_pot
from flowerpot.bouquet import (_CONE_RISE, _SHAPES, _closing_fraction,
                               _profile_radius, center_ring, gather_radius,
                               head_placements, plan, throat_radius)
from flowerpot.profile import build_profiles, effective_vase

FAST = dict(segments=96, vertical_step=2.5)
BQ = dict(bouquet=True, height=190, top_diameter=115, drainage_pattern="none",
          add_top_rim=False, **FAST)


@pytest.mark.parametrize("flower", ["tulip", "rose"])
def test_a_bouquet_planter_prints_without_supports(flower):
    p = PotParams(**{**BQ, "bouquet_flower": flower})
    pot = build_pot(p)
    report = audit(pot, p.overhang_limit_deg)
    assert pot.is_watertight and report.overhang_faces == 0, report
    assert len(pot.split(only_watertight=False)) == 1


@pytest.mark.parametrize("n", [3, 5, 8])
def test_every_bloom_count_works(n):
    p = PotParams(**{**BQ, "bouquet_count": n})
    report = audit(build_pot(p), p.overhang_limit_deg)
    assert report.overhang_faces == 0, report
    # one drain per bloom is the only tunnel through the solid
    assert len(head_placements(p)) == n


def test_it_is_actually_hollow_and_actually_drains():
    p = PotParams(**{**BQ, "bouquet_count": 5})
    pot = build_pot(p)
    # the mouth is open: the cavity comes up through the collar's throat
    assert throat_radius(p) > 6.0
    section = pot.section(plane_origin=[0, 0, p.height - 1.0],
                          plane_normal=[0, 0, 1])
    assert section is not None
    # ... and each ring bloom drains into the body, so the pockets empty
    assert round((2 - pot.euler_number) / 2) == 5


def test_blooms_stand_on_solid_shoulder_not_over_the_cavity():
    """A foot over the mouth - or over the cone under it - is unsupported."""
    p = PotParams(**BQ)
    pl = plan(p)
    kind = p.bouquet_flower
    from flowerpot.bouquet import _DRAIN_R, _base_frac, _BASE_SINK
    foot = (_base_frac(p, kind, pl["r"], _DRAIN_R + 1.3) * pl["r"]
            * (1.0 + _SHAPES[kind]["amp"]))
    inner_edge = pl["r_base"] - foot
    # the cavity has not finished coning in at the depth the foot sinks to
    under = throat_radius(p) + (_BASE_SINK + 3.0) / _CONE_RISE
    assert inner_edge >= under - 1e-6
    # and the outer edge stays on the wall
    from flowerpot.profile import wall_radius
    assert pl["r_base"] + foot <= wall_radius(p, p.height - _BASE_SINK - 3.0)


def test_blooms_never_roof_each_other():
    """Two cups that both flare meet in a valley; one that has started to
    close over its neighbour makes a ceiling.  Check the closing zone."""
    p = PotParams(**BQ)
    pl = plan(p)
    kind, n = p.bouquet_flower, pl["n"]
    lean = math.tan(math.radians(pl["tilt"]))
    t_close = _closing_fraction(kind)
    rc, hc, cfrac = center_ring(p)
    from flowerpot.bouquet import _DRAIN_R, _base_frac
    frac = _base_frac(p, kind, pl["r"], _DRAIN_R + 1.3)

    for i in range(30):
        zl = pl["h"] * (t_close + (1.0 - t_close) * i / 29.0)
        ring = _profile_radius(kind, pl["r"], pl["h"], zl, frac)
        axis = pl["r_base"] + zl * lean
        # neighbours, measured chord to chord around the ring
        assert axis * math.sin(math.pi / n) >= ring - 1e-6
        if zl <= hc:                       # ... and the collar in the middle
            assert axis - ring >= _profile_radius(kind, rc, hc, zl, cfrac) - 1e-6


def test_the_default_silhouette_is_a_trumpet():
    """A bouquet needs a wide mouth to stand on, so bouquet mode picks one."""
    p = PotParams(bouquet=True)
    assert effective_vase(p) == "bouquet"
    assert gather_radius(p) > 0.55 * p.top_radius
    # an explicit choice is still honoured
    assert effective_vase(PotParams(bouquet=True, vase_profile="cone")) == "cone"


def test_a_narrow_necked_vase_is_rejected_with_the_fix():
    with pytest.raises(ParameterError, match="too narrow"):
        build_profiles(PotParams(**{**BQ, "vase_profile": "bud"}))


def test_the_cavity_ceiling_is_printable():
    """The shoulder's underside is the interior's roof - it has to slope."""
    p = PotParams(**BQ)
    inner = build_profiles(p).inner
    (r0, z0), (r1, z1) = inner[-3], inner[-2]
    assert z1 == pytest.approx(p.height)
    assert (r0 - r1) / (z1 - z0) <= 1.0 + 1e-6      # 45 degrees or shallower
    assert r1 == pytest.approx(throat_radius(p), abs=1e-6)


def test_bouquet_guardrails():
    with pytest.raises(ParameterError):
        PotParams(bouquet=True, bouquet_flower="daisy").validate()
    with pytest.raises(ParameterError):
        PotParams(bouquet=True, bouquet_count=12).validate()
    with pytest.raises(ParameterError):
        PotParams(bouquet=True, bouquet_tilt=30).validate()
    with pytest.raises(ParameterError):
        PotParams(bouquet=True, stem=True).validate()
    with pytest.raises(ParameterError):
        PotParams(bouquet=True, jar_greenhouse=True).validate()
