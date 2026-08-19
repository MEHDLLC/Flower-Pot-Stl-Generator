"""Regression tests for the flower pot generator.

The point of these is to lock down the two promises the generator makes:
every export is a manifold solid, and every default design prints without
supports.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from flowerpot import (
    DRAINAGE_PATTERNS,
    ParameterError,
    PotParams,
    STYLES,
    audit,
    build_pot,
    build_saucer,
)
from flowerpot.build import drainage_positions
from flowerpot.profile import build_profiles, resample

# a coarser mesh keeps the suite quick without changing any of the properties
# being tested
FAST = dict(segments=72, vertical_step=3.0)


@pytest.fixture(scope="module")
def default_pots() -> dict[str, trimesh.Trimesh]:
    return {s: build_pot(PotParams(pot_style=s, **FAST)) for s in STYLES}


# ---------------------------------------------------------------------------
# manifoldness
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("style", sorted(STYLES))
def test_every_style_is_a_manifold_solid(default_pots, style):
    mesh = default_pots[style]
    assert mesh.is_watertight, "mesh has holes"
    assert mesh.is_winding_consistent, "mesh has inverted faces"
    assert mesh.is_volume, "mesh is not a valid solid"
    assert mesh.volume > 0
    assert mesh.body_count == 1, "pot should be a single connected body"
    assert (mesh.area_faces > 1e-9).all(), "degenerate faces present"


@pytest.mark.parametrize("style", sorted(STYLES))
def test_no_unsupported_overhangs(default_pots, style):
    p = PotParams(pot_style=style, **FAST)
    report = audit(default_pots[style], p.overhang_limit_deg)
    assert report.overhang_faces == 0, (
        f"{style}: {report.overhang_area_cm2:.2f} cm2 overhanging up to "
        f"{report.worst_overhang_deg:.1f} deg"
    )
    assert report.ok


@pytest.mark.parametrize("style", sorted(STYLES))
def test_survives_an_stl_round_trip(tmp_path, default_pots, style):
    path = tmp_path / f"{style}.stl"
    default_pots[style].export(path)
    reloaded = trimesh.load(path)
    assert reloaded.is_watertight and reloaded.is_winding_consistent
    assert reloaded.volume == pytest.approx(default_pots[style].volume, rel=1e-3)


# ---------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------
def test_dimensions_match_the_request():
    p = PotParams(height=120, top_diameter=140, bottom_diameter=100,
                  rim_width=5, **FAST)
    mesh = build_pot(p)
    lo, hi = mesh.bounds
    assert hi[2] - lo[2] == pytest.approx(120, abs=1e-6)
    assert lo[2] == pytest.approx(0.0, abs=1e-6)      # sits on the build plate
    # widest point is the rim: top diameter + rim_width per side
    assert mesh.extents[0] == pytest.approx(140 + 2 * 5, abs=0.5)


def test_footprint_is_flat_and_on_the_plate():
    mesh = build_pot(PotParams(**FAST))
    on_plate = np.all(mesh.triangles[:, :, 2] <= 1e-6, axis=1)
    assert on_plate.any(), "nothing touching the build plate"
    # the whole footprint is one flat disc, not a wobbly edge
    assert mesh.area_faces[on_plate].sum() > 2000.0   # mm^2
    normals = mesh.face_normals[on_plate]
    assert np.allclose(normals[:, 2], -1.0, atol=1e-6)


def test_wall_thickness_is_what_was_asked_for():
    """Slice the pot half way up and measure the gap between the two loops."""
    p = PotParams(pot_style="classic_tapered", wall_thickness=3.0, belly=0.0, **FAST)
    mesh = build_pot(p)
    z = p.height * 0.5
    section = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    loops = section.discrete
    assert len(loops) == 2, "a slice through the wall should give an outer and inner loop"
    radii = [np.hypot(loop[:, 0], loop[:, 1]).mean() for loop in loops]
    measured = max(radii) - min(radii)
    slope = (p.top_radius - p.bottom_radius) / p.height
    expected = p.wall_thickness * math.sqrt(1 + slope ** 2)   # horizontal offset
    assert measured == pytest.approx(expected, abs=0.15)


# ---------------------------------------------------------------------------
# drainage
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("pattern,expected", [
    ("none", 0), ("center", 1), ("ring", 5), ("grid", 5),
])
def test_drainage_holes_actually_go_through(pattern, expected):
    """Each through-hole adds a handle, so genus == number of holes."""
    p = PotParams(drainage_pattern=pattern, num_drainage_holes=5,
                  drainage_hole_radius=5.0, **FAST)
    mesh = build_pot(p)
    assert mesh.is_watertight
    genus = round((2 - mesh.euler_number) / 2)
    assert genus == expected
    assert len(drainage_positions(p, build_profiles(p))) == expected


def test_drainage_patterns_stay_inside_the_floor():
    for pattern in DRAINAGE_PATTERNS:
        p = PotParams(drainage_pattern=pattern, num_drainage_holes=9,
                      drainage_hole_radius=4.0, **FAST)
        prof = build_profiles(p)
        for x, y in drainage_positions(p, prof):
            assert math.hypot(x, y) + p.drainage_hole_radius < prof.cavity_floor_radius


def test_oversized_holes_are_rejected_not_silently_broken():
    p = PotParams(drainage_hole_radius=60.0, **FAST)
    with pytest.raises(ParameterError):
        build_pot(p)


# ---------------------------------------------------------------------------
# rim
# ---------------------------------------------------------------------------
def test_rim_underside_respects_the_overhang_limit():
    p = PotParams(add_top_rim=True, rim_width=10.0, **FAST)
    report = audit(build_pot(p), p.overhang_limit_deg)
    assert report.overhang_faces == 0
    assert report.worst_overhang_deg == pytest.approx(90 - p.rim_underside_angle, abs=1.0)


def test_pot_without_a_rim_is_nearly_overhang_free():
    p = PotParams(add_top_rim=False, **FAST)
    report = audit(build_pot(p), p.overhang_limit_deg)
    assert report.ok
    # only the wall taper is left
    assert report.worst_overhang_deg == pytest.approx(p.wall_lean_deg(), abs=1.0)


# ---------------------------------------------------------------------------
# saucer
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("style", sorted(STYLES))
def test_saucer_is_manifold_and_fits_the_pot(style):
    p = PotParams(pot_style=style, generate_saucer=True, **FAST)
    saucer = build_saucer(p)
    assert saucer.is_watertight and saucer.is_winding_consistent and saucer.volume > 0
    assert audit(saucer, p.overhang_limit_deg).overhang_faces == 0
    assert saucer.extents[2] == pytest.approx(p.saucer_height, abs=1e-6)

    # the pot's foot has to drop inside the saucer without touching it: stand
    # the pot on the saucer floor and check the two solids do not intersect
    pot = build_pot(p)
    pot.apply_translation((0, 0, p.saucer_base))
    overlap = trimesh.boolean.intersection([pot, saucer], engine="manifold")
    assert len(overlap.faces) == 0 or overlap.volume < 1.0, "pot fouls the saucer wall"


# ---------------------------------------------------------------------------
# parameters
# ---------------------------------------------------------------------------
def test_bad_parameters_raise():
    for bad in (dict(pot_style="nope"), dict(drainage_pattern="nope"),
                dict(height=0), dict(wall_thickness=200), dict(segments=3),
                dict(base_thickness=500)):
        with pytest.raises(ParameterError):
            PotParams(**bad).validate()


def test_risky_parameters_warn_instead_of_failing_silently():
    assert PotParams(top_diameter=400, bottom_diameter=40, height=80).validate()
    assert PotParams(pot_style="ribbed_spiral", rib_twist_degrees=200).validate()
    assert PotParams(rim_underside_angle=20).validate()
    assert PotParams().validate() == []          # the defaults are clean


def test_params_round_trip_through_json():
    p = PotParams(pot_style="hexagonal", height=99.5)
    assert PotParams.from_dict(p.to_dict()) == p
    with pytest.raises(ParameterError):
        PotParams.from_dict({"not_a_field": 1})


# ---------------------------------------------------------------------------
# profile plumbing
# ---------------------------------------------------------------------------
def test_resampling_never_changes_the_silhouette():
    poly = [(10.0, 0.0), (12.0, 50.0), (18.0, 60.0)]
    dense = resample(poly, step=1.0)
    assert len(dense) > len(poly)
    assert dense[0] == poly[0] and dense[-1] == poly[-1]
    for r, z in dense:                    # every new point sits on the original line
        for (r0, z0), (r1, z1) in zip(poly, poly[1:]):
            if z0 - 1e-9 <= z <= z1 + 1e-9:
                t = (z - z0) / (z1 - z0)
                assert r == pytest.approx(r0 + (r1 - r0) * t, abs=1e-9)
                break


def test_low_poly_keeps_its_facets_flat():
    """The faceted style must not be subdivided into a smooth cone."""
    coarse = build_pot(PotParams(pot_style="low_poly_faceted", **FAST))
    smooth = build_pot(PotParams(pot_style="classic_tapered", **FAST))
    assert len(coarse.faces) < len(smooth.faces) / 4


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_cli_writes_files(tmp_path):
    from flowerpot.cli import main
    code = main(["--pot-style", "hexagonal", "--segments", "72",
                 "--vertical-step", "3", "--out", str(tmp_path), "--quiet"])
    assert code == 0
    written = list(tmp_path.glob("*.stl"))
    assert [p.name for p in written] == ["hexagonal.stl"]
    assert trimesh.load(written[0]).is_watertight


def test_cli_rejects_impossible_parameters(tmp_path):
    from flowerpot.cli import main
    assert main(["--wall-thickness", "500", "--out", str(tmp_path)]) == 2
    assert not list(tmp_path.glob("*.stl"))


def test_cli_config_round_trip(tmp_path):
    from flowerpot.cli import main
    cfg = tmp_path / "pot.json"
    assert main(["--pot-style", "hexagonal", "--height", "88",
                 "--save-config", str(cfg), "--out", str(tmp_path / "a"),
                 "--segments", "72", "--vertical-step", "3", "--quiet"]) == 0
    assert main(["--config", str(cfg), "--out", str(tmp_path / "b"), "--quiet"]) == 0
    assert trimesh.load(tmp_path / "b" / "hexagonal.stl").extents[2] == pytest.approx(88)
