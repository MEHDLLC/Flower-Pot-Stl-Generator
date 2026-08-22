"""Tests for the screw-in stem, its water holes, and the soil cap."""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit, build_pot
from flowerpot.build import _boolean
from flowerpot.profile import build_profiles, wall_radius, wall_slope
from flowerpot.stem import (_CORE_R, _SOCKET_H, _STEM_R_BASE, _STUB_H,
                            _THREAD_CLEAR, build_soil_cap, build_stem_piece,
                            floor_keep_out)

FAST = dict(segments=72, vertical_step=3.0)


def _screw_params(**kw):
    base = dict(vase_profile="classic", stem=True, stem_mount="screw",
                stem_length=80.0, drainage_pattern="none",
                add_top_rim=False, **FAST)
    base.update(kw)
    return PotParams(**base)


def test_screw_vessel_and_stem_piece_print_support_free():
    p = _screw_params()
    prof = build_profiles(p)
    vessel = build_pot(p)
    rep = audit(vessel, p.overhang_limit_deg)
    assert vessel.is_watertight and rep.overhang_faces == 0
    # the vessel keeps its own height: the stem is a separate piece
    assert vessel.extents[2] == pytest.approx(p.height, abs=0.5)

    piece = build_stem_piece(p, prof.floor_top_z)
    rep = audit(piece, p.overhang_limit_deg)
    assert piece.is_watertight and rep.overhang_faces == 0
    # prints standing on the threaded stub
    assert piece.bounds[0][2] == pytest.approx(0.0, abs=1e-3)


def test_screwed_home_stem_does_not_collide_with_the_socket():
    p = _screw_params()
    prof = build_profiles(p)
    vessel = build_pot(p)
    piece = build_stem_piece(p, prof.floor_top_z)

    z_seat = (_STUB_H - 1.0) + _THREAD_CLEAR * 1.15
    dz = prof.floor_top_z + _SOCKET_H - z_seat
    best = math.inf
    for k in range(12):                     # screwing sweeps the phase
        m = piece.copy()
        m.apply_transform(trimesh.transformations.rotation_matrix(
            2.0 * math.pi * k / 12.0, [0, 0, 1]))
        m.apply_translation((0, 0, dz))
        inter = _boolean("intersection", [vessel, m])
        best = min(best, inter.volume if len(inter.faces) else 0.0)
        if best < 0.01:
            break
    # a real thread collision measures in the tens of mm3; anything under
    # a hundredth is facet noise from the coarse test meshes
    assert best < 0.01


def test_stem_piece_reaches_stem_length_above_the_rim():
    p = _screw_params()
    prof = build_profiles(p)
    piece = build_stem_piece(p, prof.floor_top_z)
    z_seat = (_STUB_H - 1.0) + _THREAD_CLEAR * 1.15
    z_rim = z_seat + (p.height - (prof.floor_top_z + _SOCKET_H))
    assert piece.bounds[1][2] == pytest.approx(z_rim + p.stem_length, abs=0.5)


def test_stem_piece_has_water_holes_and_an_open_bore():
    p = _screw_params()
    piece = build_stem_piece(p, build_profiles(p).floor_top_z)
    # bore (1 handle once it exits through the water holes) - every extra
    # handle is a water hole through the wall
    genus = round((2 - piece.euler_number) / 2)
    assert genus >= 2
    top = piece.vertices[piece.vertices[:, 2] > piece.bounds[1][2] - 1.0]
    assert np.hypot(top[:, 0], top[:, 1]).min() < p.stem_bore / 2.0 + 0.5


def test_soil_cap_fits_seats_and_passes_the_stem():
    p = _screw_params(soil_cap=True)
    cap = build_soil_cap(p)
    rep = audit(cap, p.overhang_limit_deg)
    assert cap.is_watertight and rep.overhang_faces == 0
    # centre stem hole + two finger holes
    assert round((2 - cap.euler_number) / 2) == 3

    # rests in the taper ~8 mm below the rim with clearance, and clears the
    # cavity above that (the wall only gets wider towards the mouth)
    z = p.height - 8.0
    cavity = (wall_radius(p, z)
              - p.wall_thickness * math.hypot(1.0, wall_slope(p, z)))
    r_cap = max(cap.extents[0], cap.extents[1]) / 2.0
    assert r_cap < cavity
    # the stem shaft (at most _STEM_R_BASE wide) passes the centre hole
    verts = cap.vertices
    inner = verts[np.hypot(verts[:, 0], verts[:, 1]) < _STEM_R_BASE + 1.5]
    assert len(inner) and np.hypot(inner[:, 0], inner[:, 1]).min() > _STEM_R_BASE


def test_drainage_holes_stay_clear_of_the_socket():
    p = _screw_params(drainage_pattern="ring", num_drainage_holes=6,
                      drainage_ring_fraction=0.35)
    pot = build_pot(p)
    rep = audit(pot, p.overhang_limit_deg)
    assert pot.is_watertight and rep.overhang_faces == 0
    # holes that would have been plugged by the boss were dropped
    genus = round((2 - pot.euler_number) / 2)
    assert genus < 6
    assert floor_keep_out(p) > _CORE_R


def test_screw_and_soil_cap_guardrails():
    with pytest.raises(ParameterError):
        PotParams(stem=True, stem_mount="glue").validate()
    with pytest.raises(ParameterError):
        PotParams(soil_cap=True, jar_greenhouse=True).validate()
