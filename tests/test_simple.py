"""Tests for the simple/nursery pot features: square style, side drainage,
and the uniform scale."""

from __future__ import annotations

import math
import pathlib

import numpy as np
import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit, build_pot
from flowerpot.export import export_pot

NURSERY = dict(wall_thickness=1.4, base_thickness=2.0, rim_width=2.5,
               rim_height=5.0, segments=72, vertical_step=3.0)


@pytest.mark.parametrize("style", ["classic_tapered", "square", "hexagonal"])
def test_thin_wall_nursery_pots_print_clean(style):
    p = PotParams(pot_style=style, num_side_holes=6, **NURSERY)
    pot = build_pot(p)
    report = audit(pot, p.overhang_limit_deg)
    assert pot.is_watertight and report.overhang_faces == 0


def test_side_holes_go_all_the_way_through():
    """Bottom ring + side ports: every hole is a handle."""
    p = PotParams(num_side_holes=6, drainage_pattern="ring",
                  num_drainage_holes=5, **NURSERY)
    pot = build_pot(p)
    genus = round((2 - pot.euler_number) / 2)
    assert genus == 5 + 6
    # side-only grow pot works too
    p2 = PotParams(num_side_holes=8, drainage_pattern="none", **NURSERY)
    genus2 = round((2 - build_pot(p2).euler_number) / 2)
    assert genus2 == 8


def test_scale_resizes_the_pot_but_not_the_walls(tmp_path):
    p = PotParams(scale=0.5, belly=0.0, drainage_pattern="center", **NURSERY)
    assert export_pot(p, "half", tmp_path, ("stl",), quiet=True).ok
    m = trimesh.load(tmp_path / "half.stl")
    assert m.extents[2] == pytest.approx(72.5, abs=0.1)        # half height
    sec = m.section(plane_origin=[0, 0, 36.0], plane_normal=[0, 0, 1])
    radii = [np.hypot(l[:, 0], l[:, 1]).mean() for l in sec.discrete]
    slope = (75.0 - 52.5) / 145.0
    expected_wall = 1.4 * math.hypot(1.0, slope)               # UNSCALED
    assert max(radii) - min(radii) == pytest.approx(expected_wall, abs=0.15)


def test_scale_up_works_and_bad_scales_are_rejected(tmp_path):
    p = PotParams(scale=1.5, **NURSERY)
    assert export_pot(p, "big", tmp_path, ("stl",), quiet=True).ok
    m = trimesh.load(tmp_path / "big.stl")
    assert m.extents[2] == pytest.approx(145.0 * 1.5, abs=0.1)
    with pytest.raises(ParameterError):
        PotParams(scale=0.1).validate()
    with pytest.raises(ParameterError):
        PotParams(scale=5.0).validate()


def test_square_jar_seat_checks_the_flats_not_the_corners():
    """A square pot whose corners could hold the jar but whose flats cannot
    must be rejected - the groove would breach the walls."""
    p = PotParams(pot_style="square", jar_greenhouse=True,
                  top_diameter=125.0, bottom_diameter=100.0,
                  segments=72, vertical_step=3.0)
    # corner cavity ~59 > groove 46.5, but flats ~42 < 46.5: must raise
    with pytest.raises(ParameterError):
        build_pot(p)


def test_square_style_is_a_box():
    p = PotParams(pot_style="square", add_top_rim=False, belly=0.0,
                  segments=72, vertical_step=3.0)
    pot = build_pot(p)
    # across flats = corner diameter * cos(45)
    assert pot.extents[0] == pytest.approx(150.0 * math.cos(math.pi / 4), abs=1.5)
