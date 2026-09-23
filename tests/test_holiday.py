"""Holiday pots: a shape with a season, and a face cut right through it.

Three things are being tested.

The first is that a face is really a face.  Every feature is a hole all
the way through the wall, and the invariant that says so exactly is the
**genus**: a blind pocket adds nothing, a through hole adds one.  So the
pot's genus has to be the bare pot's plus the number of ports - not more,
which would mean a cutter had wandered, and not less, which would mean two
holes had run together into one, or that a cutter had stopped inside the
wall.  Both of those happened while this was being written, and both are
invisible in a render.

The second is that it prints standing up, with no supports, which for a
carved face is the whole trick.  A round eye or a flat-topped grin is a
ceiling.  Every port here is pointed, and the teeth of the grin point UP.

The third is the liner, and the number nobody would guess: a hole in the
side of a pot is a waterline.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from flowerpot import ParameterError, PotParams, audit
from flowerpot.build import _boolean
from flowerpot.holiday import (FACES, PARTS, SHAPES, _FACE, _POST, _POSTS,
                               _SHAPE, _WEB, _WELL, build_holiday_liner,
                               build_holiday_pot, check_holiday, face_plan,
                               has_liner, liner_plan, port_profile,
                               seated_liner, shape_params, spill_height,
                               spill_millilitres, well_posts)

FAST = dict(segments=96, vertical_step=2.5)

#: each shape at proportions it actually wants - a gourd curve asked to be
#: squat is rejected by the profile checker, and rightly
DIMS = {
    "pumpkin": dict(top_diameter=150.0, bottom_diameter=105.0, height=105.0),
    "gourd": dict(top_diameter=130.0, bottom_diameter=95.0, height=170.0),
    "cauldron": dict(top_diameter=150.0, bottom_diameter=110.0, height=112.0),
}


def _p(shape: str = "pumpkin", **kw) -> PotParams:
    base = dict(DIMS[shape], holiday=shape, **FAST)
    base.update(kw)
    return PotParams(**base)


def _bores(p: PotParams) -> int:
    """Holes the pot would have with no face on it at all."""
    return {"none": 0, "center": 1}.get(p.drainage_pattern,
                                        int(p.num_drainage_holes))


# ---------------------------------------------------------------------------
# the body is a pot, built out of things the generator already had
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("shape", SHAPES[1:])
def test_every_shape_is_a_pot_that_prints_standing_up(shape):
    p = _p(shape, holiday_face="classic")
    pot = build_holiday_pot(p)
    report = audit(pot, p.overhang_limit_deg)
    assert pot.is_watertight and report.overhang_faces == 0, report
    assert len(pot.split(only_watertight=False)) == 1
    assert report.base_area_cm2 > 5.0


@pytest.mark.parametrize("shape", SHAPES[1:])
def test_a_shape_is_expressed_in_the_generators_own_terms(shape):
    """Nothing here is a new kind of geometry.

    That is the point of the whole module: a silhouette, a rib count and a
    rib depth with the twist turned off.  So the styles, the colours, the
    textures and the drainage all keep working on a holiday pot.
    """
    q = shape_params(_p(shape))
    assert q.vase_profile == _SHAPE[shape]["vase"]
    assert q.rib_twist_degrees == 0.0
    assert q.base_flat is False           # it stands on its own lobes
    if _SHAPE[shape]["lobes"]:
        assert q.pot_style == "ribbed_spiral"
        assert q.rib_count == _SHAPE[shape]["lobes"]
        assert q.rib_depth > 0.0


def test_shape_params_is_idempotent():
    """It has to be: the derived params still say ``holiday``, and
    ``validate()`` calls straight back into the checker."""
    p = _p("pumpkin", holiday_face="classic")
    once = shape_params(p)
    twice = shape_params(once)
    assert once.to_json() == twice.to_json()


def test_the_lobes_stand_outside_the_wall_so_the_pot_is_never_thinner():
    """A rib carved IN would be a thin spot; ribbed_spiral adds material."""
    p = _p("pumpkin", holiday_face="none", holiday_liner=False)
    lobed = build_holiday_pot(p)
    plain = build_holiday_pot(p.with_(holiday_lobes=0, holiday_lobe_depth=0.0,
                                      holiday="cauldron",
                                      **DIMS["cauldron"]))
    assert lobed.volume > 0.0 and plain.volume > 0.0
    # the lobed pot reaches further out than its nominal wall
    prof_r = 0.5 * DIMS["pumpkin"]["top_diameter"]
    assert lobed.bounds[1][0] > prof_r


def test_an_unknown_shape_or_face_says_what_the_choices_are():
    with pytest.raises(ParameterError, match="unknown holiday"):
        shape_params(PotParams(holiday="menorah"))
    with pytest.raises(ParameterError, match="unknown holiday_face"):
        face_plan(_p("pumpkin", holiday_face="smirk"))


def test_a_face_needs_a_shape_to_go_on():
    with pytest.raises(ParameterError, match="needs a holiday shape"):
        PotParams(holiday="none", holiday_face="classic", **FAST).validate()


def test_a_holiday_pot_does_not_combine_with_the_mounts():
    with pytest.raises(ParameterError, match="pot in its own right"):
        _p("pumpkin", wall_pot="round").validate()


# ---------------------------------------------------------------------------
# the face is really a face - the genus says so exactly
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("shape", SHAPES[1:])
@pytest.mark.parametrize("face", FACES[1:])
def test_every_hole_in_the_face_goes_all_the_way_through(shape, face):
    """The cheapest exact test there is.

    A blind pocket adds 0 to the genus and a through hole adds 1, so the
    pot's genus has to be the drainage plus one per port.  Under-count and
    two holes have run together, or a cutter stopped inside the wall -
    which is what happened when the cutters were cut to the RIM's radius
    on a pot whose belly is wider than its mouth.  Over-count and one has
    wandered somewhere it should not be.
    """
    p = _p(shape, holiday_face=face, holiday_liner=False)
    ports = len(face_plan(p)["ports"])
    assert ports > 0
    assert audit(build_holiday_pot(p)).genus == _bores(p) + ports


@pytest.mark.parametrize("face", FACES[1:])
def test_no_two_holes_in_a_face_touch(face):
    """Two holes that touch are one hole - a different face, and a grin
    with no teeth in it."""
    ports = face_plan(_p("pumpkin", holiday_face=face))["ports"]
    for i, a in enumerate(ports):
        for b in ports[i + 1:]:
            du = abs(a["u"] - b["u"]) - a["half"] - b["half"]
            dv = max((a["v"] - a["down"]) - (b["v"] + b["up"]),
                     (b["v"] - b["down"]) - (a["v"] + a["up"]))
            assert max(du, dv) >= _WEB, (
                f"{face}: two holes leave {max(du, dv):.1f} mm between them")


@pytest.mark.parametrize("face", FACES[1:])
def test_a_grin_has_teeth_left_between_its_gaps(face):
    """``pitch - 2 * half_w`` is the tooth.  At zero the cells merge."""
    mouth = _FACE[face]["mouth"]
    assert mouth["pitch"] > 2.0 * mouth["half_w"], face


def test_the_posts_do_not_change_the_genus():
    """They are a union of four solid boxes - no new holes, and none of
    them may bridge into a tunnel."""
    p = _p("pumpkin", holiday_face="classic")
    with_posts = audit(build_holiday_pot(p)).genus
    without = audit(build_holiday_pot(p.with_(holiday_liner=False))).genus
    assert with_posts == without


# ---------------------------------------------------------------------------
# ... and it prints standing up, which is why the shapes are what they are
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("face", FACES[1:])
def test_every_port_is_pointed_and_its_roof_beats_the_budget(face):
    p = _p("pumpkin", holiday_face=face)
    limit = math.tan(math.radians(p.overhang_limit_deg))
    for port in face_plan(p)["ports"]:
        for span in (port["half"] + port["shift"],
                     port["half"] - port["shift"]):
            if span > 1e-9:
                assert port["up"] / span > limit, (
                    f"{face}: a roof at "
                    f"{math.degrees(math.atan(port['up'] / span)):.0f} deg "
                    f"would need supports")


@pytest.mark.parametrize("face", FACES[1:])
def test_the_teeth_of_a_grin_point_up(face):
    """A tooth hanging DOWN from the top of the mouth starts as a speck of
    plastic in mid air.  So every mouth cell is flat-based: the gaps are
    pointed at the top, and the triangles left between them stand up off
    the bottom of the mouth."""
    assert _FACE[face]["mouth"]["floor"] == 0.0
    ports = face_plan(_p("pumpkin", holiday_face=face))["ports"]
    mouth = [port for port in ports if port["down"] == 0.0]
    assert mouth, face
    for port in mouth:
        assert len(port_profile(port)) == 3      # a triangle, not a diamond
        base = [z for _, z in port_profile(port) if z == port["v"]]
        assert len(base) == 2                    # ... standing on its base


def test_a_flat_based_port_is_a_triangle_and_a_floored_one_is_a_diamond():
    tri = dict(u=0.0, v=10.0, half=4.0, shift=0.0, up=5.4, down=0.0)
    dia = dict(tri, down=3.4)
    assert len(port_profile(tri)) == 3
    assert len(port_profile(dia)) == 4
    assert min(z for _, z in port_profile(dia)) == pytest.approx(6.6)


@pytest.mark.parametrize("shape", SHAPES[1:])
def test_a_cutter_reaches_past_the_widest_ring_and_not_just_the_rim(shape):
    """Every one of these shapes has a belly wider than its mouth.  A
    cutter cut to the rim's radius stops inside the wall and leaves a
    blind pocket - which still looks like a hole from the inside."""
    k = face_plan(_p(shape, holiday_face="classic"))
    widest = max(r for r, _ in k["prof"].outer)
    assert k["reach"] > widest + k["q"].rib_depth


def test_a_face_that_is_too_big_is_refused_rather_than_printed_wrong():
    with pytest.raises(ParameterError):
        check_holiday(_p("pumpkin", holiday_face="classic",
                         holiday_face_scale=3.0))


def test_a_face_may_be_scaled_within_reason():
    for scale in (0.7, 1.0, 1.25):
        p = _p("pumpkin", holiday_face="classic", holiday_face_scale=scale)
        assert check_holiday(p)


# ---------------------------------------------------------------------------
# the liner, and the waterline the face sets
# ---------------------------------------------------------------------------
def test_there_is_only_a_liner_when_there_is_a_face_to_hide_soil_behind():
    assert has_liner(_p("pumpkin", holiday_face="classic"))
    assert not has_liner(_p("pumpkin", holiday_face="none"))
    assert not has_liner(_p("pumpkin", holiday_face="classic",
                            holiday_liner=False))
    assert not has_liner(PotParams(holiday="none", holiday_liner=True))


def test_a_plain_holiday_pot_with_no_face_is_not_an_error():
    """``holiday_liner`` defaults on, and a pumpkin with no face keeps its
    own soil in - so asking for one must just work."""
    notes = check_holiday(_p("pumpkin", holiday_face="none"))
    assert any("no face" in n for n in notes)
    assert well_posts(_p("pumpkin", holiday_face="none")) == []


@pytest.mark.parametrize("shape", SHAPES[1:])
def test_the_liner_prints_standing_up_in_one_piece(shape):
    p = _p(shape, holiday_face="classic")
    liner = build_holiday_liner(p)
    report = audit(liner, p.overhang_limit_deg)
    assert liner.is_watertight and report.overhang_faces == 0, report
    assert len(liner.split(only_watertight=False)) == 1


@pytest.mark.parametrize("shape", SHAPES[1:])
def test_the_liner_drops_in_without_touching_the_pot(shape):
    p = _p(shape, holiday_face="classic")
    clash = _boolean("intersection", [build_holiday_pot(p), seated_liner(p)])
    assert clash.volume < 1.0, f"{shape}: {clash.volume:.1f} mm3 of clash"


@pytest.mark.parametrize("shape", SHAPES[1:])
def test_the_liner_goes_in_through_the_mouth(shape):
    """It is a cone and not a copy of the cavity, because every one of
    these shapes is narrower at the mouth than at the belly - so nothing
    belly-shaped would go in."""
    k = liner_plan(_p(shape, holiday_face="classic"))
    assert k["r_bot"] < k["r_top"]            # widest at the top, so it slides
    mouth = np.interp(k["top"], [z for _, z in k["prof"].inner],
                      [r for r, _ in k["prof"].inner])
    assert k["r_top"] < mouth                 # ... with slack all round


@pytest.mark.parametrize("shape", SHAPES[1:])
def test_the_liner_sits_below_the_rim(shape):
    p = _p(shape, holiday_face="classic")
    assert seated_liner(p).bounds[1][2] < build_holiday_pot(p).bounds[1][2]


def test_the_liner_stands_on_posts_so_its_drainage_is_not_blocked():
    p = _p("pumpkin", holiday_face="classic")
    k = liner_plan(p)
    posts = well_posts(p)
    assert len(posts) == _POSTS
    assert k["seat"] == pytest.approx(k["floor"] + _WELL)
    for post in posts:
        assert post.bounds[1][2] == pytest.approx(k["seat"])
        assert post.bounds[0][2] < k["floor"]      # buried, so it fuses
        # inside the liner's footprint, so the liner actually lands on it.
        # Measured off the corners themselves - the axis-aligned bounding
        # box of a box turned to face the axis is not the box.
        reach = np.hypot(post.vertices[:, 0], post.vertices[:, 1]).max()
        assert reach < k["r_bot"], f"post reaches {reach:.1f} mm"
    assert k["well"] > 0.0


def test_the_posts_miss_the_liners_drainage_holes():
    p = _p("pumpkin", holiday_face="classic", holiday_liner_holes=4)
    k = liner_plan(p)
    r_holes = 0.55 * (k["r_bot"] - 1.6)
    r_posts = 0.80 * k["r_bot"]
    assert abs(r_posts - r_holes) > 0.5 * _POST


@pytest.mark.parametrize("holes", [0, 3, 6])
def test_the_holes_go_in_the_liner_and_never_in_the_face_pot(holes):
    p = _p("pumpkin", holiday_face="classic", holiday_liner_holes=holes)
    assert audit(build_holiday_liner(p)).genus == holes
    # the pot's own genus is its drainage plus its ports, and nothing else
    assert audit(build_holiday_pot(p)).genus == _bores(p) + len(
        face_plan(p)["ports"])


def test_a_liner_is_refused_when_the_mouth_is_too_narrow_for_one():
    with pytest.raises(ParameterError, match="liner to drop through"):
        liner_plan(_p("pumpkin", top_diameter=44.0, bottom_diameter=32.0,
                      height=32.0, holiday_face="kawaii",
                      holiday_face_scale=0.4))


def test_asking_for_a_liner_with_no_face_says_why_there_is_none():
    with pytest.raises(ParameterError, match="no face to hide the soil"):
        build_holiday_liner(_p("pumpkin", holiday_face="none"))


# ---------------------------------------------------------------------------
# the number nobody would guess
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("face", FACES[1:])
def test_the_waterline_is_the_lowest_hole_in_the_face(face):
    p = _p("pumpkin", holiday_face=face)
    ports = face_plan(p)["ports"]
    assert spill_height(p) == pytest.approx(
        min(port["v"] - port["down"] for port in ports))


def test_a_pot_with_no_face_has_no_waterline():
    assert spill_height(_p("pumpkin", holiday_face="none")) == float("inf")
    assert spill_millilitres(
        _p("pumpkin", holiday_face="none")) == float("inf")


def test_the_spill_volume_counts_what_is_standing_in_the_pot():
    """The posts and the liner are in there taking up room, so the free
    volume is less than the cavity's."""
    p = _p("pumpkin", holiday_face="classic")
    free = spill_millilitres(p)
    gross = spill_millilitres(p.with_(holiday_liner=False))
    assert 0.0 < free < gross


def test_the_face_is_kept_clear_of_the_floor_and_the_rim():
    p = _p("pumpkin", holiday_face="classic")
    k = face_plan(p)
    assert spill_height(p) > k["prof"].floor_top_z + 2.0
    assert max(port["v"] + port["up"] for port in k["ports"]) < k["q"].height


def test_the_checker_reports_the_waterline_and_the_well():
    notes = check_holiday(_p("pumpkin", holiday_face="classic"))
    assert any("waterline" in n for n in notes)
    assert any("reservoir" in n for n in notes)
    assert any("pointed holes" in n for n in notes)


def test_a_shape_asked_for_the_wrong_proportions_says_so_without_refusing():
    """A squat gourd is a judgement, not an error - so it is a note, and
    the note carries the height that would fix it."""
    notes = check_holiday(_p("gourd", height=1.05 * DIMS["gourd"]["height"]))
    assert not any("times as tall" in n for n in notes)
    squat = PotParams(holiday="gourd", top_diameter=130.0,
                      bottom_diameter=95.0, height=250.0, **FAST)
    assert any("times as tall" in n for n in check_holiday(squat))


# ---------------------------------------------------------------------------
# it is still a pot, so everything else still works on it
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kw", [
    dict(surface_texture="honeycomb"),
    dict(drainage_pattern="center"),
    dict(drainage_pattern="none"),
    dict(num_drainage_holes=7),
    dict(wall_thickness=2.4),
    dict(holiday_lobes=12),
    dict(holiday_lobe_depth=4.0),
    dict(holiday_face_scale=0.8),
])
def test_a_holiday_pot_takes_the_generators_other_options(kw):
    p = _p("pumpkin", holiday_face="classic", **kw)
    pot = build_holiday_pot(p)
    report = audit(pot, p.overhang_limit_deg)
    assert pot.is_watertight and report.overhang_faces == 0, report
    assert report.genus == _bores(p) + len(face_plan(p)["ports"])


def test_the_parts_list_is_what_export_writes():
    assert set(PARTS) == {"set", "pot", "liner"}
