"""A pot with the wall mount built into its back.

Two things are being tested, and they are not the same thing.  One is that
a wall pot is still a pot - every style, texture and silhouette, still
watertight, still printable standing up with two new planes and a pocket in
it.  The other is that the cleat in its back is ripped the right way round,
which is the whole mount and is invisible if you get it wrong.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit
from flowerpot.build import _boolean, lathe
from flowerpot.hanger import _CLEAT_RISE, _SIGMA
from flowerpot.profile import build_profiles, resample
from flowerpot.sections import make_section
from flowerpot.wallpot import (PARTS, _BACK_RATIO, _SKIN, back_pad,
                               build_wall_cleat, build_wall_pot, governs,
                               outer_radius, plan, roundness, seated_cleat,
                               soil_and_centre, socket_cutter, stresses)

FAST = dict(segments=96, vertical_step=2.5)
STYLES = ["classic_tapered", "hexagonal", "square", "low_poly_faceted",
          "ribbed_spiral"]


def _p(**kw) -> PotParams:
    base = dict(wall_pot="set", drainage_pattern="none", **FAST)
    base.update(kw)
    return PotParams(**base)


def _clash(a: trimesh.Trimesh, b: trimesh.Trimesh) -> float:
    return _boolean("intersection", [a, b]).volume


def _soil_mesh(p: PotParams) -> trimesh.Trimesh:
    """The soil itself: the cavity, trimmed the way the pot trims it."""
    k = plan(p)
    q = p.with_(wall_pot="none")
    prof, sec = build_profiles(q), make_section(q)
    cav = lathe(resample(prof.inner, q.vertical_step,
                         sec.extra_ring_heights(prof.floor_top_z, q.height),
                         sec.smooth_vertically()), sec, decorate=False)
    for shift, axis in ((-k["x_back"] + k["t_wall"], 0), (q.height, 2)):
        box = trimesh.creation.box(extents=(900.0, 900.0, 900.0))
        off = [0.0, 0.0, 0.0]
        off[axis] = shift + (450.0 if axis == 2 else -450.0)
        box.apply_translation(off)
        cav = _boolean("difference", [cav, box])
    cav = _boolean("difference", [cav, back_pad(p)])
    cav.apply_translation((k["x_back"], 0.0, 0.0))
    return cav


# ---------------------------------------------------------------------------
# a wall pot is still a pot
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("style", STYLES)
def test_every_style_still_prints_standing_up(style):
    p = _p(pot_style=style)
    pot = build_wall_pot(p)
    report = audit(pot, p.overhang_limit_deg)
    assert pot.is_watertight and report.overhang_faces == 0, report
    assert len(pot.split(only_watertight=False)) == 1
    assert report.genus == 0                 # no drainage asked for


@pytest.mark.parametrize("kw", [
    dict(surface_texture="honeycomb"), dict(add_top_rim=False),
    dict(vase_profile="cone", height=230.0),
    dict(height=220.0, top_diameter=190.0, bottom_diameter=170.0),
    dict(wall_pot_round=0.80), dict(wall_pot_round=0.50),
])
def test_everything_the_pot_builder_can_do_still_works(kw):
    p = _p(**kw)
    pot = build_wall_pot(p)
    report = audit(pot, p.overhang_limit_deg)
    assert pot.is_watertight and report.overhang_faces == 0, report
    assert len(pot.split(only_watertight=False)) == 1


def test_the_holes_are_the_drainage_and_no_others():
    assert audit(build_wall_pot(_p()), 45.0).genus == 0
    assert audit(build_wall_pot(_p(drainage_pattern="ring",
                                   num_drainage_holes=5)), 45.0).genus == 5
    assert audit(build_wall_pot(_p(num_side_holes=4)), 45.0).genus == 4


def test_the_outside_is_the_pot_builder_doing_its_usual_job():
    plain = build_wall_pot(_p())
    textured = build_wall_pot(_p(surface_texture="honeycomb"))
    hexy = build_wall_pot(_p(pot_style="hexagonal"))
    assert len(textured.faces) > len(plain.faces)
    assert hexy.volume != pytest.approx(plain.volume, rel=1e-3)


# ---------------------------------------------------------------------------
# the back
# ---------------------------------------------------------------------------
def test_the_back_is_one_plane_and_it_is_on_the_wall():
    p = _p()
    pot = build_wall_pot(p)
    assert pot.bounds[0][0] == pytest.approx(0.0, abs=1e-6)
    # there is a real face there, not a tangent line: slice just inside it
    face = pot.section(plane_origin=[0.2, 0, 0], plane_normal=[1, 0, 0])
    ys = np.concatenate([np.array(loop)[:, 1] for loop in face.discrete])
    assert ys.max() - ys.min() > 0.5 * plan(p)["chord"]


def test_one_plane_gives_two_roundnesses_and_that_is_reported():
    """The pot is not the same width all the way up, so one back plane is
    rounder at the narrow end.  Quote it at the WIDE end and almost every
    tapered pot asks for a plane its own foot cannot reach."""
    p = _p()
    k = plan(p)
    assert roundness(p, 0.0) > roundness(p, p.height)
    # the plane is one number; the roundness is that number against
    # whatever the pot happens to be doing at that height
    for z in (0.0, 0.5 * p.height, p.height):
        assert roundness(p, z) == pytest.approx(
            1.0 - math.acos(k["x_back"] / outer_radius(k["prof"], z))
            / math.pi, abs=1e-9)
    assert roundness(p, 0.0) == pytest.approx(
        1.0 - math.acos(_BACK_RATIO) / math.pi, abs=1e-6)
    assert any("% round at the foot" in m and "at the mouth" in m
               for m in p.validate())
    # half a pot is half a pot at both ends
    half = _p(wall_pot_round=0.50)
    assert roundness(half, 0.0) == pytest.approx(0.5, abs=1e-6)
    assert roundness(half, half.height) == pytest.approx(0.5, abs=1e-6)
    assert plan(half)["x_back"] == pytest.approx(0.0, abs=1e-9)


def _back_at(pot: trimesh.Trimesh, z: float) -> tuple[float, float]:
    """Where the pot's back starts and ends on the centreline at ``z``,
    measured out from the wall."""
    probe = trimesh.creation.box(extents=(60.0, 5.0, 3.0))
    probe.apply_translation((30.0, 0.0, z))
    hit = _boolean("intersection", [pot, probe])
    return float(hit.bounds[0][0]), float(hit.bounds[1][0])


def test_the_back_is_only_thick_where_the_pocket_is():
    """A back thick enough for the pocket everywhere is most of a kilo of
    plastic for nothing, so the thickness is a pad behind the pocket and
    nothing else."""
    p = _p()
    k = plan(p)
    pot = build_wall_pot(p)
    # at the cleat: the pocket has taken the first d_gap of it, and what is
    # left behind that is the pad
    lo, hi = _back_at(pot, 0.5 * (k["y_nb"] + k["y_nt"]))
    assert lo == pytest.approx(k["d_gap"], abs=0.3)
    assert hi == pytest.approx(k["t_back"], abs=0.3)
    # well below it there is no pad and no pocket: a plain wall on the wall
    lo, hi = _back_at(pot, 0.35 * k["y_nb"])
    assert lo == pytest.approx(0.0, abs=0.3)
    assert hi == pytest.approx(k["t_wall"], abs=0.6)


def test_the_pocket_never_breaks_into_the_pot():
    p = _p()
    k = plan(p)
    assert k["t_back"] - k["d_gap"] == pytest.approx(_SKIN)
    # the cutter that makes the pocket does not reach the soil
    assert _clash(socket_cutter(p), _soil_mesh(p).apply_translation(
        (-k["x_back"], 0.0, 0.0))) < 1.0


# ---------------------------------------------------------------------------
# which way the cleat is ripped IS the mount
# ---------------------------------------------------------------------------
def test_tipping_the_pot_the_way_a_full_one_tips_drives_it_into_the_rail():
    """A pot of wet soil off a wall is a cantilever, and a French cleat
    carries no moment on its own.  Ripped so the bevel rises AWAY from the
    wall, tipping jams the pocket onto the rail; ripped the usual way round,
    the same motion slides the two faces apart and the pot comes off."""
    p = _p()
    pot, rail = build_wall_pot(p), seated_cleat(p)
    assert _CLEAT_RISE > 1.0, "a 45 deg mating face is a 45 deg overhang"
    assert _clash(pot, rail) < 1.0
    for deg in (0.5, 1.0, 2.0):
        tipped = pot.copy()
        tipped.apply_transform(trimesh.transformations.rotation_matrix(
            math.radians(deg), [0, 1, 0], (0.0, 0.0, 0.0)))
        assert _clash(tipped, rail) > 50.0, deg
        assert tipped.bounds[0][0] >= -1e-6, "the pot went through the wall"


def test_it_cannot_be_pulled_straight_off_the_wall_either():
    p = _p()
    pot, rail = build_wall_pot(p), seated_cleat(p)
    for out in (1.5, 4.0, 8.0):
        moved = pot.copy()
        moved.apply_translation((out, 0.0, 0.0))
        assert _clash(moved, rail) > 50.0, out
    down = pot.copy()
    down.apply_translation((0.0, 0.0, -1.5))     # the soil's own weight
    assert _clash(down, rail) > 50.0


def test_but_it_lifts_off_once_you_raise_it_past_the_rail():
    p = _p()
    k = plan(p)
    rail = seated_cleat(p)
    lift = _CLEAT_RISE * k["d_gap"]
    for out in (0.0, 5.0, 40.0):
        pot = build_wall_pot(p)
        pot.apply_translation((out, 0.0, lift + 0.5))
        assert _clash(pot, rail) < 1.0, out
    assert any("Lift the pot" in m for m in p.validate())


def test_nothing_of_the_rail_shows_once_the_pot_is_on_it():
    """The point of putting the cleat inside the pot: from the front there
    is no bracket.  Sweep the rail out into the room and the pot has to
    cover every bit of it."""
    p = _p()
    pot, rail = build_wall_pot(p), seated_cleat(p)
    swept = rail.copy()
    for step in np.arange(2.0, 60.0, 4.0):
        shifted = rail.copy()
        shifted.apply_translation((float(step), 0.0, 0.0))
        swept = _boolean("union", [swept, shifted])
    covered = _boolean("intersection", [swept, pot])
    for axis in (1, 2):
        assert covered.bounds[0][axis] <= rail.bounds[0][axis] + 0.2
        assert covered.bounds[1][axis] >= rail.bounds[1][axis] - 0.2


# ---------------------------------------------------------------------------
# the load is the one thing nobody has to type in
# ---------------------------------------------------------------------------
def test_the_pot_says_how_much_it_will_weigh():
    """Every other mount here has to be told the load.  This one has the
    cavity that the soil goes in, so it works it out - and the sum is exact
    enough that the mesh agrees with it."""
    p = _p()
    k = plan(p)
    soil = _soil_mesh(p)
    assert k["soil"] == pytest.approx(soil.volume / 1000.0, rel=0.02)
    assert k["reach"] == pytest.approx(soil.center_mass[0], abs=1.5)
    assert k["reach"] > 0.0
    assert any("ml of soil" in m and "N.m at the fixing" in m
               for m in p.validate())


def test_a_bigger_pot_is_a_bigger_moment():
    small, big = plan(_p()), plan(_p(height=220.0, top_diameter=190.0,
                                     bottom_diameter=170.0))
    assert big["soil"] > 2.0 * small["soil"]
    assert big["moment"] > small["moment"]
    assert big["pull"] > small["pull"]
    assert max(stresses(_p(height=220.0, top_diameter=190.0,
                           bottom_diameter=170.0)).values()) <= _SIGMA + 1e-6


def test_the_soil_sum_is_the_pot_and_not_a_cylinder():
    """The back plane takes a slice off every disc, and the pad takes
    another bite out of the middle of it.  Both are in the sum."""
    p = _p()
    k = plan(p)
    prof = build_profiles(p.with_(wall_pot="none"))
    full, _ = soil_and_centre(p, prof, 1e6, k["w_sock"])
    cut, _ = soil_and_centre(p, prof, k["x_back"] - k["t_wall"], k["w_sock"])
    assert cut < full
    # and the centre of what is left is pushed out into the room
    assert k["reach"] > k["x_back"]


def test_the_pots_own_back_is_never_what_limits_it():
    p = _p()
    s = stresses(p)
    assert governs(p) == "cleat"
    assert max(s["hook"], s["bevel"]) < 0.2 * s["cleat"]
    assert max(s.values()) <= _SIGMA + 1e-6
    assert any("never what limits this" in m for m in p.validate())


def test_the_screws_are_counted_and_the_fixing_is_called_out():
    p = _p()
    k = plan(p)
    assert k["n_screw"] >= 2
    assert plan(_p(wall_pot_screws=4))["n_screw"] == 4
    assert k["span"] >= 2.0 * k["head"] + 6.0
    assert any("countersunk screws" in m and "stud" in m for m in p.validate())
    assert any("hidden behind the pot" in m for m in p.validate())


# ---------------------------------------------------------------------------
# the rail
# ---------------------------------------------------------------------------
def test_the_rail_prints_face_down_with_its_countersinks_in_the_bed():
    p = _p()
    k = plan(p)
    rail = build_wall_cleat(p)
    report = audit(rail, p.overhang_limit_deg)
    assert rail.is_watertight and report.overhang_faces == 0, report
    assert rail.extents[2] == pytest.approx(k["t_c"], abs=0.05)
    assert rail.extents[0] == pytest.approx(k["rail"], abs=0.05)
    assert report.genus == k["n_screw"]
    assert any("FACE DOWN" in m for m in p.validate())


def test_the_rail_is_cut_to_the_pot_rather_than_the_other_way_round():
    """It has to hide behind the flat, so the flat's width is what sets it."""
    narrow, wide = plan(_p()), plan(_p(wall_pot_round=0.65))
    assert wide["chord"] > narrow["chord"]
    assert wide["rail"] > narrow["rail"]
    assert plan(_p(wall_pot_rail=70.0))["rail"] == 70.0


# ---------------------------------------------------------------------------
# guardrails
# ---------------------------------------------------------------------------
def test_guardrails():
    with pytest.raises(ParameterError, match="unknown wall_pot"):
        PotParams(wall_pot="bracket").validate()
    with pytest.raises(ParameterError, match="wall_pot_round is the fraction"):
        _p(wall_pot_round=0.30).validate()
    with pytest.raises(ParameterError, match="can go up to wall_pot_round"):
        _p(wall_pot_round=0.99).validate()
    with pytest.raises(ParameterError, match="does not combine"):
        _p(sleeve=True).validate()
    with pytest.raises(ParameterError, match="does not combine"):
        _p(hanger="set").validate()
    with pytest.raises(ParameterError, match="wall_pot_screws"):
        _p(wall_pot_screws=1).validate()
    with pytest.raises(ParameterError, match="leaves"):
        _p(height=110.0, top_diameter=120.0, bottom_diameter=110.0).validate()


def test_a_pot_too_short_to_get_a_back_under_the_cleat_says_so():
    with pytest.raises(ParameterError, match="a wall pot wants to be at least"):
        _p(height=60.0).validate()


def test_drainage_down_a_wall_is_argued_with_rather_than_forbidden():
    p = _p(drainage_pattern="ring")
    assert audit(build_wall_pot(p), p.overhang_limit_deg).overhang_faces == 0
    assert any("waters the wall" in m for m in p.validate())
    assert not any("waters the wall" in m for m in _p().validate())


def test_the_parts_can_be_asked_for_one_at_a_time():
    for part in PARTS[2:]:
        assert _p(wall_pot=part).validate() is not None
