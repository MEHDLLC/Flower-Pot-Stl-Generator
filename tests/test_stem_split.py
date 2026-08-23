"""A screw-in stem taller than the bed prints in threaded sections."""

from __future__ import annotations

import math

import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit
from flowerpot.build import _boolean
from flowerpot.printers import PRINTERS
from flowerpot.profile import build_profiles
from flowerpot.stem import (_NODE_ENGAGE, build_stem_piece, node_radius,
                            planned_branches, stem_piece_count,
                            stem_section_bounds, _Layout, _leaf_sites)

FAST = dict(segments=96, vertical_step=2.5)
TALL = dict(vase_profile="bud", stem=True, stem_mount="screw", height=220,
            top_diameter=110, stem_length=130, drainage_pattern="none",
            add_top_rim=False, printer="creality-k1-max", **FAST)


def _pieces(p):
    floor_z = build_profiles(p).floor_top_z
    return [build_stem_piece(p, floor_z, i)
            for i in range(stem_piece_count(p, floor_z))]


def test_a_stem_too_tall_for_the_bed_is_split_to_fit():
    p = PotParams(**TALL)
    bed = PRINTERS[p.printer]["height"]
    pieces = _pieces(p)
    assert len(pieces) == 2                       # 341 mm needs one node
    for piece in pieces:
        report = audit(piece, p.overhang_limit_deg)
        assert piece.is_watertight and report.overhang_faces == 0
        assert piece.extents[2] <= bed
        # one solid: a feature split across the joint would leave a fragment
        assert len(piece.split(only_watertight=False)) == 1
        assert piece.bounds[0][2] == pytest.approx(0.0, abs=1e-3)


def test_the_sections_screw_together():
    p = PotParams(**TALL)
    floor_z = build_profiles(p).floor_top_z
    bounds = stem_section_bounds(p, floor_z)
    lower, upper = _pieces(p)
    dz = bounds[1][0] - _NODE_ENGAGE

    best = math.inf
    for k in range(24):                           # screwing sweeps the phase
        m = upper.copy()
        m.apply_transform(trimesh.transformations.rotation_matrix(
            2.0 * math.pi * k / 24.0, [0, 0, 1]))
        m.apply_translation((0.0, 0.0, dz))
        inter = _boolean("intersection", [lower, m])
        best = min(best, inter.volume if len(inter.faces) else 0.0)
        if best < 0.01:
            break
    # a thread that genuinely bound would measure in the tens of mm3; this
    # bound is facet noise at the phase where the crests nest
    assert best < 0.01


def test_splitting_changes_how_it_prints_not_what_it_is():
    p = PotParams(**TALL)
    whole = p.with_(stem_split="never")
    one = build_stem_piece(whole, build_profiles(whole).floor_top_z)
    floor_z = build_profiles(p).floor_top_z
    lower, upper = _pieces(p)
    upper.apply_translation(
        (0.0, 0.0, stem_section_bounds(p, floor_z)[1][0] - _NODE_ENGAGE))
    assembled = trimesh.util.concatenate([lower, upper])
    assert assembled.extents[2] == pytest.approx(one.extents[2], abs=0.5)
    assert one.extents[2] > PRINTERS[p.printer]["height"]   # ... and warns


def test_no_node_lands_underwater_or_inside_a_feature():
    p = PotParams(**TALL)
    floor_z = build_profiles(p).floor_top_z
    lay = _Layout(p, floor_z)
    nodes = [hi for hi, _ in stem_section_bounds(p, floor_z)[1:]]
    assert nodes
    for z in nodes:
        assert z > lay.z_rim, "a joint below the rim would sit in the water"
        for z_att, length, _a, _t in _leaf_sites(p, lay.z_rim, lay.top):
            assert not z_att - 2.0 < z < z_att + 0.9 * length
        for z_att, climb, _a in planned_branches(p, lay.z_rim, lay.top):
            assert not z_att - 2.0 < z < z_att + climb + 4.0


def test_the_node_stands_proud_enough_to_hold_a_thread():
    p = PotParams(**TALL)
    # the shaft is barely thicker than its bore, so the joint must bulge
    assert node_radius(p) > p.stem_bore / 2.0 + 3.0


def test_split_policy_is_respected():
    never = PotParams(**{**TALL, "stem_split": "never"})
    assert stem_piece_count(never, build_profiles(never).floor_top_z) == 1

    short = PotParams(**{**TALL, "height": 150, "stem_length": 60})
    floor_z = build_profiles(short).floor_top_z
    assert stem_piece_count(short, floor_z) == 1          # already fits
    forced = short.with_(stem_split="always")
    assert stem_piece_count(forced, build_profiles(forced).floor_top_z) == 2

    # no printer profile means no bed to respect
    free = PotParams(**{**TALL, "printer": "none"})
    assert stem_piece_count(free, build_profiles(free).floor_top_z) == 1


def test_a_forced_node_on_a_short_stem_still_prints():
    p = PotParams(**{**TALL, "height": 150, "stem_length": 60,
                     "stem_split": "always"})
    for piece in _pieces(p):
        report = audit(piece, p.overhang_limit_deg)
        assert piece.is_watertight and report.overhang_faces == 0
        assert len(piece.split(only_watertight=False)) == 1


def test_export_names_the_sections(tmp_path):
    from flowerpot.export import export_pot

    p = PotParams(**TALL)
    result = export_pot(p, "vase", tmp_path, ("stl",), preview=False,
                        force=True)
    written = {path.name for path in result.written}
    assert {"vase.stl", "vase_stem_part1.stl", "vase_stem_part2.stl"} <= written
    assert "vase_stem.stl" not in written

    # ... and an unsplit stem keeps the plain name
    short = PotParams(**{**TALL, "height": 150, "stem_length": 60})
    result = export_pot(short, "short", tmp_path, ("stl",), preview=False,
                        force=True)
    assert "short_stem.stl" in {path.name for path in result.written}


def test_split_guardrail():
    with pytest.raises(ParameterError):
        PotParams(stem=True, stem_split="sometimes").validate()
