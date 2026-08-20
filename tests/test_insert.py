"""Tests for the universal reservoir insert."""

from __future__ import annotations

import math

import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit
from flowerpot.export import export_pot
from flowerpot.insert import INSERT_SHAPES, build_insert_platform, build_insert_tube

FAST = dict(reservoir_insert=True, segments=72, vertical_step=3.0)


@pytest.mark.parametrize("shape", sorted(INSERT_SHAPES))
def test_platform_is_manifold_and_printable_in_every_shape(shape):
    p = PotParams(insert_shape=shape, **FAST)
    mesh = build_insert_platform(p)
    report = audit(mesh, p.overhang_limit_deg)
    assert mesh.is_watertight and mesh.is_winding_consistent
    assert report.overhang_faces == 0, (
        f"{shape}: worst {report.worst_overhang_deg:.1f} deg"
    )


@pytest.mark.parametrize("shape", sorted(INSERT_SHAPES))
def test_platform_respects_the_measured_pot_width(shape):
    """insert_width is what the user measured across the flats - the print
    must come out slightly UNDER it in every flat direction, rounded
    corners included."""
    p = PotParams(insert_shape=shape, **FAST)
    mesh = build_insert_platform(p)
    across_flats = min(mesh.extents[0], mesh.extents[1])
    assert across_flats <= p.insert_width - 0.5
    assert across_flats >= p.insert_width - 2.0


def test_platform_height_matches_the_reservoir():
    p = PotParams(**FAST)
    mesh = build_insert_platform(p)
    assert mesh.extents[2] == pytest.approx(4.0 + p.reservoir_height, abs=0.2)


def test_tube_is_an_open_pipe_and_printable():
    p = PotParams(**FAST)
    tube = build_insert_tube(p)
    report = audit(tube, p.overhang_limit_deg)
    assert tube.is_watertight and report.overhang_faces == 0
    assert round((2 - tube.euler_number) / 2) == 1      # one bore = one handle
    assert tube.extents[2] == pytest.approx(p.insert_tube_length, abs=0.5)
    # the miter must open the tip: the solid must not reach full length at
    # every angle (a flat-cut pipe standing on the floor would seal itself)
    top = tube.vertices[:, 2] > p.insert_tube_length - 1.0
    assert tube.vertices[top][:, 0].std() < p.refill_tube_bore  # tip is one-sided


def test_tube_slips_through_the_platform_socket():
    p = PotParams(**FAST)
    tube_outer_radius = p.refill_tube_bore / 2.0 + 2.4
    from flowerpot.insert import _flat_radius
    # the socket hole is tube radius + 0.3 slip fit; just confirm the tube
    # is round and under the hole size
    tube = build_insert_tube(p)
    body_r = max(abs(tube.vertices[:, 0]).max(), abs(tube.vertices[:, 1]).max())
    assert body_r <= tube_outer_radius + p.refill_tube_bore / 2.0  # funnel end
    mid = tube.vertices[(tube.vertices[:, 2] > 40) & (tube.vertices[:, 2] < 100)]
    import numpy as np
    assert np.hypot(mid[:, 0], mid[:, 1]).max() <= tube_outer_radius + 0.01


def test_bad_insert_parameters_are_rejected():
    with pytest.raises(ParameterError):
        PotParams(reservoir_insert=True, insert_shape="triangle").validate()
    with pytest.raises(ParameterError):
        build_insert_platform(PotParams(reservoir_insert=True, insert_width=60.0))
    with pytest.raises(ParameterError):
        build_insert_tube(PotParams(reservoir_insert=True, insert_tube_length=40.0))
    with pytest.raises(ParameterError):
        PotParams(reservoir_insert=True, self_watering=True).validate()


def test_export_writes_platform_and_tube(tmp_path):
    p = PotParams(**FAST)
    result = export_pot(p, "fit", tmp_path, ("stl",), quiet=True)
    assert result.ok
    names = sorted(f.name for f in result.written)
    assert names == ["fit_insert.stl", "fit_insert_tube.stl"]
