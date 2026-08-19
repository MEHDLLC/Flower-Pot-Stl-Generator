"""Tests for the surface textures, colors, 3MF export and preview pipeline."""

from __future__ import annotations

import zipfile

import numpy as np
import pytest
import trimesh

from flowerpot import ParameterError, PotParams, audit, build_pot
from flowerpot.colors import PALETTE, parse_color
from flowerpot.export import export_pot
from flowerpot.params import TEXTURES
from flowerpot.profile import build_profiles
from flowerpot.sections import make_section
from flowerpot.textures import make_texture
from flowerpot.threemf import rim_accent_mask, write_3mf

# small pot + coarse mesh: same properties, much faster
FAST = dict(height=80.0, top_diameter=90.0, bottom_diameter=70.0,
            segments=72, vertical_step=3.0, drainage_hole_radius=4.0)

REAL_TEXTURES = [t for t in TEXTURES if t != "none"]


# ---------------------------------------------------------------------------
# textures
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("texture", REAL_TEXTURES)
def test_textured_pots_stay_manifold_and_printable(texture):
    p = PotParams(surface_texture=texture, texture_cell=12.0, **FAST)
    mesh = build_pot(p)
    assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 0
    report = audit(mesh, p.overhang_limit_deg)
    assert report.overhang_faces == 0, (
        f"{texture}: worst {report.worst_overhang_deg:.1f} deg"
    )


@pytest.mark.parametrize("texture", REAL_TEXTURES)
def test_texture_only_ever_adds_material(texture):
    """The relief stands proud of the wall - it must never thin it."""
    p = PotParams(surface_texture=texture, **FAST)
    prof = build_profiles(p)
    section = make_section(p)
    section.texture = make_texture(p, prof)
    assert section.texture is not None
    theta = section.thetas()
    for z in np.linspace(1.0, p.height - 1.0, 15):
        plain = section.radius(theta, float(z), 40.0, decorate=False)
        dressed = section.radius(theta, float(z), 40.0, decorate=True)
        assert (dressed >= plain - 1e-9).all()
        assert (dressed - plain <= p.texture_depth + 1e-9).all()


def test_texture_is_seamless_around_the_wrap():
    """The pattern must close on itself at theta = 0 == 2*pi."""
    p = PotParams(surface_texture="honeycomb", **FAST)
    tex = make_texture(p, build_profiles(p))
    eps = 1e-6
    theta = np.array([eps, 2.0 * np.pi - eps])
    for z in (20.0, 35.0, 50.0):
        lo, hi = tex(theta, z)
        assert lo == pytest.approx(hi, abs=1e-3)


def test_texture_fades_out_at_base_and_rim():
    p = PotParams(surface_texture="diamonds", **FAST)
    prof = build_profiles(p)
    tex = make_texture(p, prof)
    theta = np.linspace(0, 2 * np.pi, 64, endpoint=False)
    assert np.allclose(tex(theta, 0.5), 0.0)                       # footprint
    assert np.allclose(tex(theta, prof.decoration_freeze_z), 0.0)  # rim chamfer


def test_texture_is_ignored_on_low_poly():
    p = PotParams(pot_style="low_poly_faceted", surface_texture="honeycomb", **FAST)
    assert any("ignored" in w for w in p.validate())
    textured = build_pot(p)
    plain = build_pot(p.with_(surface_texture="none"))
    assert len(textured.faces) == len(plain.faces)


def test_unknown_texture_is_rejected():
    with pytest.raises(ParameterError):
        PotParams(surface_texture="tartan").validate()


# ---------------------------------------------------------------------------
# colors
# ---------------------------------------------------------------------------
def test_color_parsing():
    assert parse_color("terracotta") == PALETTE["terracotta"]
    assert parse_color("#b06040") == "#B06040"
    assert parse_color("#abc") == "#AABBCC"
    for bad in ("banana", "#12345", "#gggggg"):
        with pytest.raises(ValueError):
            parse_color(bad)


def test_bad_colors_are_rejected_at_validation():
    with pytest.raises(ParameterError):
        PotParams(color="banana").validate()
    with pytest.raises(ParameterError):
        PotParams(accent_color="#12").validate()


# ---------------------------------------------------------------------------
# 3MF
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def small_pot():
    return build_pot(PotParams(**FAST))


def test_3mf_round_trips_through_trimesh(tmp_path, small_pot):
    path = write_3mf(tmp_path / "pot.3mf", small_pot, color="teal")
    scene = trimesh.load(path)
    geo = next(iter(scene.geometry.values()))
    assert geo.is_watertight
    assert geo.volume == pytest.approx(small_pot.volume, rel=1e-4)


def test_3mf_carries_the_colors_and_accent(tmp_path, small_pot):
    p = PotParams(**FAST)
    mask = rim_accent_mask(small_pot, build_profiles(p).decoration_freeze_z)
    assert 0 < mask.sum() < len(mask)
    path = write_3mf(tmp_path / "pot.3mf", small_pot, color="sage",
                     accent_color="sand", accent_mask=mask,
                     thumbnail_png=b"\x89PNG fake")
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        assert {"[Content_Types].xml", "_rels/.rels",
                "3D/3dmodel.model", "Metadata/thumbnail.png"} <= names
        xml = zf.read("3D/3dmodel.model").decode()
    assert PALETTE["sage"] + "FF" in xml
    assert PALETTE["sand"] + "FF" in xml
    assert xml.count('p1="1"') == int(mask.sum())


def test_accent_mask_is_empty_without_a_rim(small_pot):
    mask = rim_accent_mask(small_pot, float("inf"))
    assert not mask.any()


# ---------------------------------------------------------------------------
# export pipeline (what the GitHub workflow runs)
# ---------------------------------------------------------------------------
def test_export_pot_writes_stl_3mf_and_preview(tmp_path):
    pytest.importorskip("matplotlib")
    p = PotParams(**FAST)
    result = export_pot(p, "mypot", tmp_path, ("stl", "3mf"),
                        preview=True, quiet=True)
    assert result.ok
    names = sorted(f.name for f in result.written)
    assert names == ["mypot.3mf", "mypot.png", "mypot.stl"]
    # the preview is embedded in the 3mf as its thumbnail
    with zipfile.ZipFile(tmp_path / "mypot.3mf") as zf:
        assert "Metadata/thumbnail.png" in zf.namelist()
        assert zf.read("Metadata/thumbnail.png")[:4] == b"\x89PNG"


def test_export_refuses_a_failing_design(tmp_path):
    # 180 degree twist drives the rib helix past the overhang limit
    p = PotParams(pot_style="ribbed_spiral", rib_twist_degrees=180.0, **FAST)
    result = export_pot(p, "bad", tmp_path, ("stl",), quiet=True)
    assert not result.ok
    assert result.written == []
    assert not list(tmp_path.glob("*.stl"))


def test_cli_format_both(tmp_path):
    from flowerpot.cli import main
    code = main(["--pot-style", "hexagonal", "--format", "both",
                 "--color", "cobalt", "--height", "80", "--top-diameter", "90",
                 "--bottom-diameter", "70", "--segments", "72",
                 "--vertical-step", "3", "--out", str(tmp_path), "--quiet"])
    assert code == 0
    assert (tmp_path / "hexagonal.stl").exists()
    assert (tmp_path / "hexagonal.3mf").exists()


# ---------------------------------------------------------------------------
# slicer project payload (Creality Cloud "Print Settings" uploads)
# ---------------------------------------------------------------------------
def test_project_3mf_carries_a_creality_machine(tmp_path, small_pot):
    import json
    path = write_3mf(tmp_path / "proj.3mf", small_pot, name="pot",
                     color="teal", printer="creality-k1-max")
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        assert {"Metadata/project_settings.config",
                "Metadata/model_settings.config"} <= names
        cfg = json.loads(zf.read("Metadata/project_settings.config"))
        xml = zf.read("3D/3dmodel.model").decode()
        model_xml = zf.read("Metadata/model_settings.config").decode()
    # the machine model is what Creality Cloud's validator looks for
    assert cfg["printer_model"] == "Creality K1 Max"
    assert cfg["printer_settings_id"] == "Creality K1 Max 0.4 nozzle"
    assert cfg["printable_area"] == ["0x0", "300x0", "300x300", "0x300"]
    # the pot's color rides into the filament slot
    assert cfg["filament_colour"] == ["#2E7F86"]
    # BBS-family metadata + plate-centred placement
    assert "BambuStudio:3mfVersion" in xml
    assert 'transform="1 0 0 0 1 0 0 0 1 150.000 150.000 0"' in xml
    assert 'object_id" value="2"' in model_xml
    # Creality Cloud's previewer requires the assemble block, with the same
    # placement transform as the build item
    assert ('assemble_item object_id="2" instance_id="0" '
            'transform="1 0 0 0 1 0 0 0 1 150.000 150.000 0"') in model_xml
    assert "mesh_stat" in model_xml


def test_model_settings_is_valid_xml_with_and_without_thumbnail(tmp_path, small_pot):
    import xml.dom.minidom as minidom
    for i, thumb in enumerate((None, b"\x89PNG fake")):
        path = write_3mf(tmp_path / f"m{i}.3mf", small_pot, color="teal",
                         printer="creality-k1-max", thumbnail_png=thumb)
        with zipfile.ZipFile(path) as zf:
            ms = zf.read("Metadata/model_settings.config").decode()
            minidom.parseString(ms)
            # never reference plate thumbnails that are not in the package
            for ref in ("Metadata/plate_1.png", "Metadata/plate_no_light_1.png"):
                if ref in ms:
                    assert ref in zf.namelist()


def test_project_3mf_still_reads_as_a_plain_3mf(tmp_path, small_pot):
    """The payload is additive: any standard 3MF consumer still gets the mesh."""
    path = write_3mf(tmp_path / "proj.3mf", small_pot, color="sage",
                     printer="creality-k1")
    scene = trimesh.load(path)
    geo = next(iter(scene.geometry.values()))
    assert geo.is_watertight
    assert geo.volume == pytest.approx(small_pot.volume, rel=1e-4)


def test_printer_none_writes_a_plain_3mf(tmp_path, small_pot):
    path = write_3mf(tmp_path / "plain.3mf", small_pot, color="sage",
                     printer=None)
    with zipfile.ZipFile(path) as zf:
        assert "Metadata/project_settings.config" not in zf.namelist()
        assert "BambuStudio" not in zf.read("3D/3dmodel.model").decode()


def test_every_printer_profile_is_well_formed():
    import json
    from flowerpot.printers import PRINTERS, build_project_settings
    for key in PRINTERS:
        cfg = json.loads(build_project_settings(key, "terracotta"))
        assert "Creality" in cfg["printer_model"]
        w = int(cfg["printable_area"][2].split("x")[0])
        assert w >= 200 and int(cfg["printable_height"]) >= 200


def test_unknown_printer_is_rejected():
    with pytest.raises(ParameterError):
        PotParams(printer="bambu-x1c").validate()


def test_export_warns_when_the_pot_overflows_the_bed(tmp_path, capsys):
    p = PotParams(height=230, top_diameter=240, bottom_diameter=190,
                  printer="creality-k1", segments=72, vertical_step=3.0,
                  drainage_hole_radius=8.0)
    export_pot(p, "big", tmp_path, ("3mf",), quiet=True)
    assert "does not fit" in capsys.readouterr().err
