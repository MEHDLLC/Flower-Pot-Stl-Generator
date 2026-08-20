"""Tests for the mason-jar greenhouse seat."""

from __future__ import annotations

import numpy as np
import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit, build_pot
from flowerpot.export import export_pot
from flowerpot.jar import build_jar_ring, jar_radii
from flowerpot.selfwatering import build_self_watering_inner

FAST = dict(jar_greenhouse=True, segments=72, vertical_step=3.0)


def _groove_radii_at(mesh, z):
    section = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    return sorted(float(np.hypot(l[:, 0], l[:, 1]).mean()) for l in section.discrete)


def test_classic_jar_pot_is_printable_and_seats_the_jar():
    p = PotParams(**FAST)
    pot = build_pot(p)
    report = audit(pot, p.overhang_limit_deg)
    assert report.ok, f"worst {report.worst_overhang_deg:.1f}"
    # a slice through the seat shows shaft, upstand, groove, outer wall
    r_hole, r_gi, r_go = jar_radii(p)
    radii = _groove_radii_at(pot, p.height - 3.0)
    assert any(abs(r - r_gi) < 1.0 for r in radii), radii
    assert any(abs(r - r_go) < 1.0 for r in radii), radii
    # the jar lip's landing ring is wide enough for a lip plus clearance
    assert r_go - r_gi == pytest.approx(7.0, abs=0.1)


def test_vents_reach_the_planting_shaft():
    """Each vent adds a handle through the upstand - an airtight seat would
    cook the seedling.  Genus = drainage holes + 4 vents."""
    p = PotParams(**FAST)
    pot = build_pot(p)
    genus = round((2 - pot.euler_number) / 2)
    assert genus == p.num_drainage_holes + 4


def test_self_watering_inner_takes_the_seat():
    p = PotParams(self_watering=True, **FAST)
    inner = build_self_watering_inner(p)
    report = audit(inner, p.overhang_limit_deg)
    assert report.ok
    genus = round((2 - inner.euler_number) / 2)
    assert genus == p.num_wick_holes + 4 + 4       # wick + notches + vents


def test_insert_gains_a_collar_ring(tmp_path):
    p = PotParams(reservoir_insert=True, **FAST)
    result = export_pot(p, "kit", tmp_path, ("stl",), quiet=True)
    assert result.ok
    names = sorted(f.name for f in result.written)
    assert names == ["kit_insert.stl", "kit_insert_tube.stl", "kit_jar_ring.stl"]
    ring = trimesh.load(tmp_path / "kit_jar_ring.stl")
    assert ring.is_watertight
    assert audit(ring, p.overhang_limit_deg).ok


def test_regular_mouth_jars_work_too():
    p = PotParams(jar_mouth_od=70.0, **FAST)
    assert audit(build_pot(p), p.overhang_limit_deg).ok


def test_too_narrow_pots_are_rejected():
    with pytest.raises(ParameterError):
        build_pot(PotParams(top_diameter=95.0, bottom_diameter=80.0, **FAST))


def test_jar_is_not_available_on_the_hydro_tower():
    with pytest.raises(ParameterError):
        PotParams(hydro_tower=True, jar_greenhouse=True).validate()


def test_saucer_does_not_inherit_the_seat():
    from flowerpot import build_saucer
    p = PotParams(generate_saucer=True, **FAST)
    saucer = build_saucer(p)
    genus = round((2 - saucer.euler_number) / 2)
    assert genus == 0                              # plain tray, no seat carved in
