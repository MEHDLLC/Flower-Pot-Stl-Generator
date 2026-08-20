"""Tests for the hydroponic tower."""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit
from flowerpot.export import export_pot
from flowerpot.hydro import (
    _SPIGOT_H,
    build_hydro_cap,
    build_hydro_cup,
    build_hydro_segment,
)

FAST = dict(hydro_tower=True, segments=72, vertical_step=3.0)


@pytest.fixture(scope="module")
def pieces():
    p = PotParams(**FAST)
    return (p, build_hydro_segment(p), build_hydro_cup(p), build_hydro_cap(p))


def test_all_pieces_are_manifold_and_printable(pieces):
    p, seg, cup, cap = pieces
    for name, mesh in (("segment", seg), ("cup", cup), ("cap", cap)):
        report = audit(mesh, p.overhang_limit_deg)
        assert mesh.is_watertight and mesh.is_winding_consistent, name
        assert report.overhang_faces == 0, (
            f"{name}: worst {report.worst_overhang_deg:.1f} deg"
        )


def test_segments_stack_without_touching(pieces):
    """Spigot in mouth: two stacked segments must not intersect - including
    the top port's shroud, which leans toward the stacking zone."""
    p, seg, _, _ = pieces
    upper = seg.copy()
    upper.apply_translation((0, 0, p.segment_height - _SPIGOT_H + 0.001))
    overlap = trimesh.boolean.intersection([seg, upper], engine="manifold")
    assert len(overlap.faces) == 0 or overlap.volume < 1.0


def test_segment_topology(pieces):
    """One tunnel per port plus the column bore itself."""
    p, seg, _, _ = pieces
    genus = round((2 - seg.euler_number) / 2)
    assert genus == p.ports_per_segment + 1
    assert seg.extents[2] == pytest.approx(p.segment_height, abs=0.2)


def test_spigot_fits_the_mouth(pieces):
    """The bottom 10 mm must slip inside the column's inner radius."""
    p, seg, _, _ = pieces
    low = seg.vertices[seg.vertices[:, 2] < 10.0]
    r_max = float(np.hypot(low[:, 0], low[:, 1]).max())
    assert r_max <= p.tower_diameter / 2.0 - p.wall_thickness - 0.2


def test_cup_fits_the_port(pieces):
    """The basket slips into the bore; the lip does not."""
    p, _, cup, _ = pieces
    lip = cup.vertices[cup.vertices[:, 2] < 2.9]
    body = cup.vertices[cup.vertices[:, 2] > 6.0]
    assert float(np.hypot(lip[:, 0], lip[:, 1]).max()) > p.port_bore / 2.0
    assert float(np.hypot(body[:, 0], body[:, 1]).max()) <= p.port_bore / 2.0 - 0.3


def test_shallow_port_angles_are_rejected():
    with pytest.raises(ParameterError):
        build_hydro_segment(PotParams(port_angle=35.0, **FAST))


def test_oversized_ports_are_rejected():
    with pytest.raises(ParameterError):
        build_hydro_segment(PotParams(port_bore=95.0, **FAST))
    with pytest.raises(ParameterError):
        build_hydro_segment(PotParams(segment_height=70.0, **FAST))


def test_hydro_excludes_the_other_products():
    with pytest.raises(ParameterError):
        PotParams(hydro_tower=True, self_watering=True).validate()
    with pytest.raises(ParameterError):
        PotParams(hydro_tower=True, reservoir_insert=True).validate()


def test_export_writes_all_three_pieces(tmp_path):
    p = PotParams(**FAST)
    result = export_pot(p, "tower", tmp_path, ("stl",), quiet=True)
    assert result.ok
    names = sorted(f.name for f in result.written)
    assert names == ["tower_cap.stl", "tower_cup.stl", "tower_segment.stl"]
