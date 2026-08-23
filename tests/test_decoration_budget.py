"""Decoration must fit the overhang budget the wall leaves free.

Ribs and textures are *added* on top of the wall, so their radial gradient
stacks onto the wall's own lean.  These are the cases that used to blow the
budget - and, because a piece that fails its audit is not written, used to
reach the user as an artifact with the vase missing and only the stem,
leaves and soil cap inside.
"""

from __future__ import annotations

import math

import pytest

from flowerpot import PotParams, audit, build_pot
from flowerpot.profile import build_profiles, max_wall_slope, slope_budget
from flowerpot.sections import make_section
from flowerpot.textures import make_texture

FAST = dict(segments=96, vertical_step=2.5)
VASE = dict(height=220, top_diameter=110, drainage_pattern="none",
            add_top_rim=False, **FAST)


def test_ribs_on_a_flaring_vase_foot_stay_printable():
    # the bud curve flares ~30 deg at the foot; the old fixed 6 mm rib ramp
    # added another 0.5 of gradient on top and hit 47 deg
    p = PotParams(vase_profile="bud", pot_style="ribbed_spiral", **VASE)
    report = audit(build_pot(p), p.overhang_limit_deg)
    assert report.overhang_faces == 0, report


def test_rib_fade_stretches_only_where_the_wall_is_steep():
    straight = PotParams(pot_style="ribbed_spiral", **FAST)
    flaring = PotParams(vase_profile="bud", pot_style="ribbed_spiral", **VASE)
    plain_fade = make_section(straight)._fade_length()
    vase_fade = make_section(flaring)._fade_length()
    assert plain_fade == pytest.approx(max(2.0 * straight.rib_depth, 5.0))
    assert vase_fade > plain_fade
    # and the stretched ramp really does fit the budget
    spent = max_wall_slope(flaring, 0.0, vase_fade)
    assert spent + flaring.rib_depth / vase_fade <= slope_budget(flaring) + 1e-6


@pytest.mark.parametrize("texture", ["herringbone", "honeycomb", "diamonds"])
def test_textures_survive_the_wave_profile(texture):
    # a wave crest let the melted texture snap back to full depth over ~4 mm,
    # a 0.25 ramp that pushed the flank past the limit
    p = PotParams(vase_profile="wave", surface_texture=texture, **VASE)
    report = audit(build_pot(p), p.overhang_limit_deg)
    assert report.overhang_faces == 0, report


def test_texture_amplitude_ramp_is_rate_limited():
    p = PotParams(vase_profile="wave", surface_texture="honeycomb", **VASE)
    tex = make_texture(p, build_profiles(p))
    zs = [z * 0.5 for z in range(int(2 * 10), int(2 * (p.height - 10)))]
    worst = max(abs(tex._window(b) - tex._window(a)) / (b - a)
                for a, b in zip(zs, zs[1:]))
    assert worst <= 1.0 / tex.reach + 1e-3          # the cone erosion holds
    assert tex.depth * worst <= tex.ramp + 1e-3     # ... in mm of gradient


@pytest.mark.parametrize("profile", ["classic", "bud", "gourd", "wave"])
def test_ribs_and_texture_together_fit_one_budget(profile):
    """Two decorations, one budget: each must charge for the other."""
    p = PotParams(vase_profile=profile, pot_style="ribbed_spiral",
                  surface_texture="herringbone", **VASE)
    report = audit(build_pot(p), p.overhang_limit_deg)
    assert report.overhang_faces == 0, report


def test_the_texture_is_told_what_the_ribs_already_spend():
    p = PotParams(pot_style="ribbed_spiral", surface_texture="honeycomb",
                  **FAST)
    section = make_section(p)
    prof = build_profiles(p)
    section.freeze_z = prof.decoration_freeze_z
    ribbed = make_texture(p, prof, section)
    bare = make_texture(p, prof, make_section(PotParams(
        surface_texture="honeycomb", **FAST)))
    mid = p.height / 2.0
    assert section.decoration_slope(mid) > 0.0
    assert ribbed._window(mid) < bare._window(mid)   # ribs cost the texture
    # ... and the ribs' ramp is charged on top, down at the foot
    assert section.decoration_slope(1.0) > section.decoration_slope(mid)


def test_texture_still_reads_on_an_ordinary_pot():
    """The budget must not quietly sand every texture flat."""
    p = PotParams(surface_texture="honeycomb", **FAST)
    tex = make_texture(p, build_profiles(p))
    mid = [tex._window(z) for z in range(30, int(p.height) - 30, 5)]
    assert min(mid) > 0.85 and max(mid) == pytest.approx(1.0, abs=0.02)


def test_every_texture_fits_the_budget_on_every_vase():
    """The invariant itself: wall + pattern + ramp <= the overhang limit."""
    for profile in ("classic", "bud", "gourd", "bottle", "cone", "wave"):
        for texture in ("herringbone", "honeycomb", "diamonds", "waves"):
            p = PotParams(vase_profile=profile, surface_texture=texture,
                          **VASE)
            tex = make_texture(p, build_profiles(p))
            budget = slope_budget(p)
            for i in range(0, 4 * int(p.height)):
                z = i / 4.0
                total = (abs(_wall_slope(p, z))
                         + tex.depth * tex._window(z) * tex.grad
                         + tex.ramp)
                assert total <= budget + 1e-6, (profile, texture, z, total)


def _wall_slope(p, z):
    from flowerpot.profile import wall_slope
    return wall_slope(p, z)


def _failing_audit(monkeypatch, only: str | None = None):
    """Make the audit fail (optionally for one piece) without needing a
    broken model - the point is the reporting, not the geometry."""
    from flowerpot import export as export_mod
    real = export_mod.audit
    state = {"n": 0}

    def fake(mesh, limit):
        report = real(mesh, limit)
        state["n"] += 1
        if only is None or state["n"] == 1:
            object.__setattr__(report, "overhang_faces", 7)
            object.__setattr__(report, "worst_overhang_deg", 63.0)
        return report

    monkeypatch.setattr(export_mod, "audit", fake)


def test_a_failed_piece_is_reported_loudly(tmp_path, capsys, monkeypatch):
    """A piece that fails the audit must never vanish quietly."""
    from flowerpot.export import export_pot

    _failing_audit(monkeypatch, only="first")
    p = PotParams(stem=True, stem_mount="screw", soil_cap=True,
                  drainage_pattern="ring", **FAST)
    result = export_pot(p, "planted", tmp_path, ("stl",), preview=False)
    out = capsys.readouterr().out

    assert not result.ok
    # the vessel is gone, but the accessories were written - exactly the
    # "only the stem, leaves and soil ring showed up" report
    assert not (tmp_path / "planted.stl").exists()
    assert (tmp_path / "planted_soil_cap.stl").exists()
    # ... and the run says so, on stdout, where the job summary can see it
    assert "planted NOT WRITTEN" in out
    assert "INCOMPLETE" in out and "1 of 3" in out


def test_cli_exits_nonzero_when_a_piece_is_dropped(tmp_path, monkeypatch):
    from flowerpot.cli import main

    _failing_audit(monkeypatch)
    code = main(["--out", str(tmp_path), "--name", "pot",
                 "--segments", "96", "--vertical-step", "2.5"])
    assert code == 1
