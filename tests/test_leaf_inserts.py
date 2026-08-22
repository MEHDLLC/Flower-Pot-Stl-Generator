"""Tests for push-in leaves: slots in the stem, a flat plate of tabs."""

from __future__ import annotations

import math

import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit, build_pot
from flowerpot.build import _boolean
from flowerpot.profile import build_profiles
from flowerpot.stem import (_SLOT_HALF_H, _SLOT_HALF_T, _TAB_HALF_T,
                            _leaf_sites, branch_leaf_length,
                            build_leaf_inserts, build_stem_piece,
                            planned_branches)

FAST = dict(segments=72, vertical_step=3.0)


def _params(**kw):
    base = dict(vase_profile="classic", stem=True, leaf_mount="insert",
                stem_length=80.0, drainage_pattern="none",
                add_top_rim=False, **FAST)
    base.update(kw)
    return PotParams(**base)


def _expected_slots(p) -> int:
    top = p.height + p.stem_length
    branches = planned_branches(p, p.height, top)
    n_branch_leaves = sum(
        1 for z, c, _a in branches
        if branch_leaf_length(p, top, z, c) is not None)
    return len(_leaf_sites(p, p.height, top)) + n_branch_leaves


def test_slotted_stem_prints_support_free_with_exact_genus():
    p = _params(stem_mount="printed")
    vase = build_pot(p)
    rep = audit(vase, p.overhang_limit_deg)
    assert vase.is_watertight and rep.overhang_faces == 0
    # tunnels: water holes + branch bores + one slot per leaf
    from flowerpot.stem import _water_holes
    floor_z = build_profiles(p).floor_top_z
    top = p.height + p.stem_length
    expected = (len(_water_holes(p, floor_z + 14.0, p.height - 10.0))
                + len(planned_branches(p, p.height, top))
                + _expected_slots(p))
    assert round((2 - vase.euler_number) / 2) == expected


def test_leaf_plate_is_flat_and_complete():
    p = _params(stem_mount="screw", leaf_angle=45.0)
    plate = build_leaf_inserts(p)
    rep = audit(plate, p.overhang_limit_deg)
    assert plate.is_watertight and rep.overhang_faces == 0
    assert len(plate.split(only_watertight=False)) == _expected_slots(p)
    assert plate.bounds[0][2] == pytest.approx(0.0, abs=1e-3)  # flat on bed
    assert plate.extents[2] < 9.0                              # lies low


def test_tab_slides_into_its_slot():
    p = _params(stem_mount="screw")
    prof = build_profiles(p)
    piece = build_stem_piece(p, prof.floor_top_z)

    # every leaf, posed as inserted into its own slot - built and posed
    # with the piece's own frame (its rim height, taper and sway)
    from flowerpot.stem import (_centerline, _main_leaf_piece, _taper,
                                leaf_pose, _SOCKET_H, _STEM_R_BASE,
                                _STEM_R_TIP, _STUB_H, _THREAD_CLEAR)
    z_f2 = (_STUB_H - 1.0) + (15.0 - 10.0) * 1.15 + 1.5
    z_seat = (_STUB_H - 1.0) + _THREAD_CLEAR * 1.15
    z_rim = z_seat + (p.height - (prof.floor_top_z + _SOCKET_H))
    top = z_rim + p.stem_length
    r_fn = _taper(_STEM_R_BASE, z_f2, _STEM_R_TIP, top)
    cl = _centerline(p, z_rim, top)

    for z_att, length, azim, tilt in _leaf_sites(p, z_rim, top):
        leaf = _main_leaf_piece(p, z_att, length, azim, tilt, r_fn, cl)
        cx, cy = cl(z_att)
        leaf.apply_transform(leaf_pose(r_fn(z_att), azim, cx, cy, z_att))
        inter = _boolean("intersection", [piece, leaf])
        vol = inter.volume if len(inter.faces) else 0.0
        assert vol < 1.0    # grazing facets only - the tab clears its slot

    # and the joint geometry itself guarantees play in the tight direction
    assert _TAB_HALF_T < _SLOT_HALF_T


def test_insert_mode_relaxes_the_leaf_angle():
    PotParams(stem=True, leaf_mount="insert", leaf_angle=45.0).validate()
    with pytest.raises(ParameterError):
        PotParams(stem=True, leaf_mount="printed", leaf_angle=45.0).validate()
    with pytest.raises(ParameterError):
        PotParams(stem=True, leaf_mount="insert", leaf_angle=65.0).validate()
    with pytest.raises(ParameterError):
        PotParams(stem=True, leaf_mount="welded").validate()
