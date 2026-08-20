"""Tests for the modular garden kits and the shared dovetail standard."""

from __future__ import annotations

import math

import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit
from flowerpot.export import export_pot
from flowerpot.modular import (
    _BOSS_OUT,
    _HUB_R,
    _HUB_WALL,
    _hub_height,
    build_flower_center,
    build_flower_petal,
    build_seed_tray,
    build_stack_hub,
    build_stack_pod,
)

FAST = dict(segments=72, vertical_step=3.0)


def _overlap(a, b):
    ov = trimesh.boolean.intersection([a, b], engine="manifold")
    return float(ov.volume) if len(ov.faces) else 0.0


@pytest.fixture(scope="module")
def p():
    return PotParams(modular_kit="seed_cubes", **FAST)


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_trays_are_printable_with_a_hole_per_quarter_cell(p, n):
    tray = build_seed_tray(p, n)
    report = audit(tray, p.overhang_limit_deg)
    assert tray.is_watertight and report.overhang_faces == 0
    genus = round((2 - tray.euler_number) / 2)
    assert genus == 4 * n * n                       # 4 drainage holes per cell
    # bbox = body + protruding rail (3.6) + boss (5.2)
    assert tray.extents[0] == pytest.approx(n * p.cube_size + 2.4 + 8.8, abs=0.2)


def test_single_docks_onto_a_tray_edge(p):
    """Rail in slot at any cell offset: zero intersection, level bottoms."""
    cube = build_seed_tray(p, 1)
    tray = build_seed_tray(p, 3)
    W1, W3 = p.cube_size + 2.4, 3 * p.cube_size + 2.4
    docked = cube.copy()
    docked.apply_translation((W3 / 2 + _BOSS_OUT + W1 / 2, p.cube_size, 0))
    assert _overlap(tray, docked) < 0.5
    assert abs(docked.bounds[0][2] - tray.bounds[0][2]) < 1e-6


def test_flower_assembles_without_touching(p):
    center = build_flower_center(p)
    petal = build_flower_petal(p)
    assert audit(center, p.overhang_limit_deg).ok
    assert audit(petal, p.overhang_limit_deg).ok
    petals = []
    for k in range(5):
        q = petal.copy()
        q.apply_transform(trimesh.transformations.rotation_matrix(
            2 * math.pi * k / 5, [0, 0, 1]))
        petals.append(q)
    assert max(_overlap(center, q) for q in petals) < 0.5
    assert max(_overlap(petals[i], petals[(i + 1) % 5]) for i in range(5)) < 0.5


def test_stack_levels_rotate_freely(p):
    """The round spigot joint means ANY rotation stacks cleanly - proven at
    an arbitrary 37 degrees."""
    hub = build_stack_hub(p)
    assert audit(hub, p.overhang_limit_deg).ok
    upper = hub.copy()
    upper.apply_transform(trimesh.transformations.rotation_matrix(
        math.radians(37), [0, 0, 1]))
    upper.apply_translation((0, 0, _hub_height(p) + _HUB_WALL + 0.2))
    assert _overlap(hub, upper) < 0.5


def test_pods_clip_onto_the_hub(p):
    hub = build_stack_hub(p)
    pod = build_stack_pod(p)
    assert audit(pod, p.overhang_limit_deg).ok
    genus = round((2 - pod.euler_number) / 2)
    assert genus == 4                               # 4 drainage holes
    clipped = pod.copy()
    clipped.apply_transform(trimesh.transformations.rotation_matrix(
        math.pi, [0, 0, 1]))
    clipped.apply_translation((_HUB_R + _BOSS_OUT + p.stack_pod_diameter / 2, 0, 0))
    assert _overlap(hub, clipped) < 0.5


def test_bad_modular_parameters_are_rejected():
    with pytest.raises(ParameterError):
        PotParams(modular_kit="lego").validate()
    with pytest.raises(ParameterError):
        build_seed_tray(PotParams(modular_kit="seed_cubes", cube_size=30, **FAST), 1)
    with pytest.raises(ParameterError):
        build_flower_center(PotParams(modular_kit="flower",
                                      flower_diameter=90, **FAST))
    with pytest.raises(ParameterError):
        PotParams(modular_kit="flower", self_watering=True).validate()


@pytest.mark.parametrize("kit,expected", [
    ("seed_cubes", ["m_cube.stl", "m_tray_2x2.stl", "m_tray_3x3.stl",
                    "m_tray_4x4.stl"]),
    ("flower", ["m_flower_center.stl", "m_flower_petal.stl"]),
    ("stack", ["m_stack_hub.stl", "m_stack_pod.stl"]),
])
def test_export_per_kit(tmp_path, kit, expected):
    p = PotParams(modular_kit=kit, **FAST)
    result = export_pot(p, "m", tmp_path / kit, ("stl",), quiet=True)
    assert result.ok
    assert sorted(f.name for f in result.written) == sorted(expected)
