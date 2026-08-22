"""Tests for the vase profiles and the planted stem."""

from __future__ import annotations

import numpy as np
import pytest

from flowerpot import ParameterError, PotParams, audit, build_pot
from flowerpot.params import VASE_PROFILES

FAST = dict(drainage_pattern="none", add_top_rim=False,
            segments=72, vertical_step=3.0)
REAL = [v for v in VASE_PROFILES if v != "none"]


@pytest.mark.parametrize("profile", REAL)
def test_every_vase_profile_is_watertight_and_printable(profile):
    p = PotParams(vase_profile=profile, height=220, top_diameter=110, **FAST)
    vase = build_pot(p)
    report = audit(vase, p.overhang_limit_deg)
    assert vase.is_watertight and report.overhang_faces == 0
    # top_diameter sizes the WIDEST point of the vase
    assert max(vase.extents[0], vase.extents[1]) == pytest.approx(110.0, abs=0.5)


def test_vases_compose_with_styles_and_textures():
    p = PotParams(vase_profile="gourd", pot_style="hexagonal",
                  surface_texture="honeycomb", height=220, top_diameter=110,
                  **FAST)
    assert audit(build_pot(p), p.overhang_limit_deg).ok


def test_too_steep_curves_are_rejected_with_the_fix():
    with pytest.raises(ParameterError, match="height >="):
        build_pot(PotParams(vase_profile="bud", height=120,
                            top_diameter=150, **FAST))


def test_stem_vase_prints_support_free():
    p = PotParams(vase_profile="bud", stem=True, height=180,
                  top_diameter=120, **FAST)
    vase = build_pot(p)
    report = audit(vase, p.overhang_limit_deg)
    assert vase.is_watertight and report.overhang_faces == 0
    # stem rises stem_length above the rim; bore is open at the top
    assert vase.extents[2] == pytest.approx(180.0 + p.stem_length, abs=0.5)
    top = vase.vertices[vase.vertices[:, 2] > vase.extents[2] - 1.0]
    r_top = np.hypot(top[:, 0], top[:, 1])
    assert r_top.min() < p.stem_bore / 2.0 + 0.5      # bore mouth is open
    # blind bore: no through-tunnel, genus stays 0 on a drainless vessel
    assert round((2 - vase.euler_number) / 2) == 0


def test_stem_works_in_a_plain_pot_too():
    p = PotParams(stem=True, drainage_pattern="ring", num_drainage_holes=5,
                  segments=72, vertical_step=3.0)
    pot = build_pot(p)
    assert audit(pot, p.overhang_limit_deg).ok
    assert round((2 - pot.euler_number) / 2) == 5     # drainage only


def test_stem_guardrails():
    with pytest.raises(ParameterError):
        PotParams(stem=True, leaf_angle=45.0).validate()      # supports needed
    with pytest.raises(ParameterError):
        PotParams(stem=True, jar_greenhouse=True).validate()  # both want the mouth
    with pytest.raises(ParameterError):
        PotParams(stem=True, drainage_pattern="center").validate()
    with pytest.raises(ParameterError):
        PotParams(vase_profile="ming").validate()
