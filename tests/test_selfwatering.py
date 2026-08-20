"""Tests for the two-piece self-watering set."""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit
from flowerpot.export import export_pot
from flowerpot.selfwatering import (
    _outer_cavity_min,
    build_self_watering_inner,
    build_self_watering_outer,
    inner_height,
)

FAST = dict(self_watering=True, segments=72, vertical_step=3.0)


@pytest.fixture(scope="module")
def default_set():
    p = PotParams(**FAST)
    return p, build_self_watering_outer(p), build_self_watering_inner(p)


def test_both_pieces_are_manifold_and_printable(default_set):
    p, outer, inner = default_set
    for name, mesh in (("outer", outer), ("inner", inner)):
        report = audit(mesh, p.overhang_limit_deg)
        assert report.watertight and report.winding_consistent, name
        assert report.overhang_faces == 0, (
            f"{name}: worst {report.worst_overhang_deg:.1f} deg"
        )


@pytest.mark.parametrize("style", ["hexagonal", "ribbed_spiral"])
def test_other_styles_work_too(style):
    p = PotParams(pot_style=style, **FAST)
    assert audit(build_self_watering_outer(p), p.overhang_limit_deg).ok
    assert audit(build_self_watering_inner(p), p.overhang_limit_deg).ok


def test_rims_end_flush(default_set):
    """Inner standing on the outer floor ends level with the outer rim."""
    p, outer, inner = default_set
    # the outer's own height is its rim (the funnel rises above it)
    assert inner.extents[2] + p.base_thickness == pytest.approx(p.height, abs=0.2)
    assert inner_height(p) == pytest.approx(p.height - p.base_thickness)


def test_inner_actually_fits_inside_the_outer(default_set):
    """Drop the inner onto the outer floor: the solids must not collide."""
    p, outer, inner = default_set
    inner = inner.copy()
    inner.apply_translation((0, 0, p.base_thickness))
    overlap = trimesh.boolean.intersection([outer, inner], engine="manifold")
    assert len(overlap.faces) == 0 or overlap.volume < 1.0


def test_refill_tube_reaches_the_reservoir(default_set):
    """The bore + port make exactly one tunnel through the solid (genus 1),
    which is what lets poured water reach the reservoir."""
    p, outer, _ = default_set
    assert outer.is_watertight
    genus = round((2 - outer.euler_number) / 2)
    assert genus == 1
    # and the funnel mouth stands above the rim
    assert outer.extents[2] > p.height + 8.0


def test_inner_has_its_wick_holes(default_set):
    """Wick holes are handles; the four cup notches add one handle each."""
    p, _, inner = default_set
    genus = round((2 - inner.euler_number) / 2)
    assert genus == p.num_wick_holes + 4


def test_reservoir_leaves_room_for_water(default_set):
    """Slice the assembly at half reservoir height: the moat between cup and
    outer wall must be open (that's where the water lives)."""
    p, outer, inner = default_set
    z = p.base_thickness + p.reservoir_height / 2.0
    section = inner.section(plane_origin=[0, 0, z - p.base_thickness],
                            plane_normal=[0, 0, 1])
    r_inner_max = max(np.hypot(loop[:, 0], loop[:, 1]).max()
                      for loop in section.discrete)
    assert _outer_cavity_min(p, z) - r_inner_max > 5.0


def test_low_poly_outer_is_rejected():
    with pytest.raises(ParameterError):
        PotParams(pot_style="low_poly_faceted", **FAST).validate()


def test_absurd_reservoir_is_rejected():
    with pytest.raises(ParameterError):
        build_self_watering_inner(PotParams(reservoir_height=120.0, **FAST))


def test_export_writes_outer_and_inner(tmp_path):
    p = PotParams(**FAST)
    result = export_pot(p, "sw", tmp_path, ("stl",), quiet=True)
    assert result.ok
    names = sorted(f.name for f in result.written)
    assert names == ["sw_inner.stl", "sw_outer.stl"]
