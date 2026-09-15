"""Shared export pipeline: build -> audit -> STL / 3MF / preview PNG.

Used by both the CLI and ``generate_pot.py`` so the two front ends cannot
drift apart.  The rule is the same everywhere: a design that fails the
print-readiness audit is reported and NOT written unless ``force`` is set.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import trimesh

from .analysis import audit
from .build import build_pot, build_saucer
from .params import PotParams
from .printers import PRINTERS
from .profile import build_profiles
from .threemf import rim_accent_mask, write_3mf

FORMATS = ("stl", "3mf")


@dataclass
class ExportResult:
    written: list[Path] = field(default_factory=list)
    ok: bool = True                      # every audited mesh passed


def _write_stl(mesh: trimesh.Trimesh, path: Path, ascii_stl: bool) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = mesh.export(file_type="stl_ascii" if ascii_stl else "stl")
    with open(path, "w" if isinstance(data, str) else "wb") as fh:
        fh.write(data)
    return path


def export_pot(
    params: PotParams,
    name: str,
    out: Path,
    formats: tuple[str, ...] = ("stl",),
    *,
    preview: bool = False,
    force: bool = False,
    ascii_stl: bool = False,
    quiet: bool = False,
) -> ExportResult:
    """Build ``params`` (pot + optional saucer) and write every requested file.

    ``out`` is normally a directory; a path ending in .stl or .3mf names a
    single file and overrides ``formats``.
    """
    result = ExportResult()

    if params.scale != 1.0:
        # resize the design's proportions; walls, floors and print-fit
        # clearances (and the real-world jar_mouth_od) stay as set
        s = params.scale
        params = params.with_(scale=1.0, **{
            f: getattr(params, f) * s
            for f in ("height", "top_diameter", "bottom_diameter",
                      "rim_width", "rim_height", "inner_base_chamfer",
                      "drainage_hole_radius", "side_hole_radius",
                      "texture_cell", "rib_depth", "hex_corner_round",
                      "reservoir_height", "saucer_height",
                      "replica_pot_top", "replica_pot_base",
                      "replica_pot_height", "replica_standoff",
                      "cradle_diameter", "cradle_height",
                      "cradle_dish_height", "cradle_keel", "cradle_flare",
                      "pole_diameter", "pole_segment_height",
                      "pole_reservoir",
                      "under_pot_base", "under_waffle", "under_rim",
                      "under_riser_height", "under_mesh_diameter",
                      "sleeve_pot_top", "sleeve_pot_base",
                      "sleeve_pot_height", "sleeve_well", "sleeve_base",
                      "hanger_pot_top", "hanger_pot_base",
                      "hanger_pot_height", "hanger_drop", "hanger_reach",
                      "hanger_cleat_length", "wall_pot_rail")})

    for warning in params.validate():
        print(f"  WARN {warning}", file=sys.stderr)

    if out.suffix.lower() in (".stl", ".3mf"):
        formats = (out.suffix.lower()[1:],)
        outdir, single_stem = out.parent, out.stem
    else:
        outdir, single_stem = out, None

    if params.modular_kit != "none":
        from functools import partial
        from .modular import (build_flower_center, build_flower_petal,
                              build_seed_tray, build_stack_hub, build_stack_pod)
        jobs: list[tuple] = {
            "seed_cubes": [
                (partial(build_seed_tray, n=1), f"{name}_cube", False),
                (partial(build_seed_tray, n=2), f"{name}_tray_2x2", False),
                (partial(build_seed_tray, n=3), f"{name}_tray_3x3", False),
                (partial(build_seed_tray, n=4), f"{name}_tray_4x4", False),
            ],
            "flower": [
                (build_flower_center, f"{name}_flower_center", False),
                (build_flower_petal, f"{name}_flower_petal", False),
            ],
            "stack": [
                (build_stack_hub, f"{name}_stack_hub", False),
                (build_stack_pod, f"{name}_stack_pod", False),
            ],
        }[params.modular_kit]
    elif params.hydro_tower:
        from .hydro import build_hydro_cap, build_hydro_cup, build_hydro_segment
        jobs: list[tuple] = [
            (build_hydro_segment, f"{name}_segment", False),
            (build_hydro_cup, f"{name}_cup", False),
            (build_hydro_cap, f"{name}_cap", False),
        ]
    elif params.replica != "none":
        from .replica import (build_replica_pot, build_replica_reservoir,
                              build_replica_wick)
        jobs: list[tuple] = []
        if params.replica in ("kyra", "set"):
            jobs.append((build_replica_pot, f"{name}_pot", True))
        if params.replica in ("hdx", "set"):
            jobs.append((build_replica_reservoir, f"{name}_reservoir",
                         not jobs))
        from .replica import wants_wick
        if params.replica == "set" and wants_wick(params):
            jobs.append((build_replica_wick, f"{name}_wick", False))
    elif params.hanger != "none":
        from .hanger import (build_hanger_arm, build_hanger_base,
                             build_hanger_cleat, build_hanger_rib,
                             build_hanger_top, build_hanger_yoke)
        jobs: list[tuple] = []
        if params.hanger in ("base", "set"):
            jobs.append((build_hanger_base, f"{name}_base", True))
        if params.hanger in ("arm", "set"):
            jobs.append((build_hanger_arm, f"{name}_arm", not jobs))
        if params.hanger in ("top", "set"):
            jobs.append((build_hanger_top, f"{name}_top", not jobs))
        if params.hanger_mount == "wall":
            if params.hanger in ("cleat", "set"):
                jobs.append((build_hanger_cleat, f"{name}_cleat", not jobs))
            if params.hanger in ("rib", "set"):
                jobs.append((build_hanger_rib, f"{name}_rib", not jobs))
            if params.hanger in ("yoke", "set"):
                jobs.append((build_hanger_yoke, f"{name}_yoke", not jobs))
    elif params.wall_pot != "none":
        from .wallpot import build_wall_cleat, build_wall_pot
        jobs: list[tuple] = []
        if params.wall_pot in ("pot", "set"):
            jobs.append((build_wall_pot, f"{name}_pot", True))
        if params.wall_pot in ("cleat", "set"):
            jobs.append((build_wall_cleat, f"{name}_cleat", not jobs))
    elif params.sleeve:
        from .sleeve import build_sleeve
        jobs: list[tuple] = [(build_sleeve, f"{name}_sleeve", True)]
    elif params.underpot != "none":
        from .underpot import (build_under_mesh, build_under_riser,
                               build_under_tray)
        jobs: list[tuple] = []
        if params.underpot in ("tray", "set"):
            jobs.append((build_under_tray, f"{name}_tray", True))
        if params.underpot in ("riser", "set"):
            jobs.append((build_under_riser, f"{name}_riser", not jobs))
        if params.underpot in ("mesh", "set"):
            jobs.append((build_under_mesh, f"{name}_mesh", not jobs))
    elif params.moss_pole != "none":
        from .mosspole import (build_pole_base, build_pole_cap,
                               build_pole_segment)
        jobs: list[tuple] = []
        if params.moss_pole in ("segment", "set"):
            jobs.append((build_pole_segment, f"{name}_segment", True))
        if params.moss_pole in ("base", "set"):
            jobs.append((build_pole_base, f"{name}_base", not jobs))
        if params.moss_pole in ("cap", "set"):
            jobs.append((build_pole_cap, f"{name}_cap", not jobs))
    elif params.cradle != "none":
        from .cradle import build_cradle_dish, build_cradle_pot
        jobs: list[tuple] = []
        if params.cradle in ("pot", "set"):
            jobs.append((build_cradle_pot, f"{name}_pot", True))
        if params.cradle in ("dish", "set"):
            jobs.append((build_cradle_dish, f"{name}_dish", not jobs))
    elif params.yard_plant != "none":
        from .yard import build_yard_body, build_yard_face, build_yard_head
        jobs: list[tuple] = [(build_yard_body, f"{name}_body", True)]
        if params.yard_plant != "cactus":
            jobs += [(build_yard_head, f"{name}_head", False),
                     (build_yard_face, f"{name}_face", False)]
        if params.hitch_mount == "screw":
            from .hitch import build_hitch_collar
            jobs.append((build_hitch_collar, f"{name}_hitch_collar", False))
    elif params.hitch_mount == "cover":
        from .hitch import build_hitch_cover
        jobs: list[tuple] = [(build_hitch_cover, f"{name}_hitch_cover", True)]
    elif params.hitch_mount == "screw":
        from .hitch import build_hitch_cap, build_hitch_collar
        jobs = [
            (build_hitch_collar, f"{name}_hitch_collar", True),
            (build_hitch_cap, f"{name}_hitch_cap", False),
        ]
    elif params.reservoir_insert:
        from .insert import build_insert_platform, build_insert_tube
        jobs = [
            (build_insert_platform, f"{name}_insert", False),
            (build_insert_tube, f"{name}_insert_tube", False),
        ]
        if params.jar_greenhouse:
            from .jar import build_jar_ring
            jobs.append((build_jar_ring, f"{name}_jar_ring", False))
    elif params.self_watering:
        from .selfwatering import build_self_watering_inner, build_self_watering_outer
        jobs = [
            (build_self_watering_outer, f"{name}_outer", True),
            (build_self_watering_inner, f"{name}_inner", False),
        ]
    else:
        jobs = [(build_pot, name, True)]
        if params.stem and params.stem_mount == "screw":
            from .stem import build_stem_piece, stem_piece_count
            floor_z = build_profiles(params).floor_top_z
            n = stem_piece_count(params, floor_z)
            for i in range(n):
                # a stem too tall for the bed comes apart at threaded nodes
                suffix = "_stem" if n == 1 else f"_stem_part{i + 1}"
                jobs.append(
                    (lambda q, fz=floor_z, k=i: build_stem_piece(q, fz, k),
                     f"{name}{suffix}", False))
        if params.stem and params.leaf_mount == "insert":
            from .stem import build_leaf_inserts
            jobs.append((build_leaf_inserts, f"{name}_leaves", False))
        if params.soil_cap:
            from .stem import build_soil_cap
            jobs.append((build_soil_cap, f"{name}_soil_cap", False))
        if params.generate_saucer:
            jobs.append((build_saucer, f"{name}_saucer", False))

    # the accent color goes on the rim, whose foot height comes from the profile
    rim_z = build_profiles(params).decoration_freeze_z if params.accent_color else None

    skipped: list[str] = []
    for builder, stem, is_pot in jobs:
        if single_stem is not None:
            suffix = stem[len(name):] if stem.startswith(name) else ""
            stem = single_stem + suffix

        mesh = builder(params)
        report = audit(mesh, params.overhang_limit_deg)
        if not quiet:
            print(f"\n{stem}")
            print(report)
        result.ok &= report.ok
        printer = params.printer if params.printer != "none" else None
        if printer is not None:
            bw, bd = PRINTERS[printer]["bed"]
            bh = PRINTERS[printer]["height"]
            sx, sy, sz = report.size_mm
            if sx > bw or sy > bd or sz > bh:
                print(f"  WARN {stem} ({sx:.0f} x {sy:.0f} x {sz:.0f} mm) does not fit "
                      f"the {PRINTERS[printer]['model']} bed ({bw} x {bd} x {bh} mm)",
                      file=sys.stderr)
        if not (report.ok or force):
            # stdout, not stderr: this line has to reach the workflow's job
            # summary, which only captures stdout.  A piece silently missing
            # from the artifact is the worst possible way to report this.
            print(f"  !! {stem} NOT WRITTEN: it failed the print audit above "
                  f"(pass force to write it anyway)")
            skipped.append(stem)
            continue

        png_bytes = None
        if preview:
            from .preview import render_png       # matplotlib is optional
            png = render_png(mesh, outdir / f"{stem}.png", color=params.color)
            png_bytes = png.read_bytes()
            result.written.append(png)
            print(f"  -> {png}")

        for fmt in formats:
            path = outdir / f"{stem}.{fmt}"
            if fmt == "stl":
                _write_stl(mesh, path, ascii_stl)
            else:
                write_3mf(
                    path, mesh,
                    name=stem,
                    color=params.color,
                    accent_color=params.accent_color or None,
                    accent_mask=(rim_accent_mask(mesh, rim_z)
                                 if is_pot and rim_z is not None else None),
                    thumbnail_png=png_bytes,
                    printer=printer,
                )
            result.written.append(path)
            print(f"  -> {path}")

    if skipped:
        # an incomplete set is easy to miss in a folder of files, so spell it
        # out once at the end, where a reader actually looks
        print(f"\n!! INCOMPLETE: {len(skipped)} of {len(jobs)} piece(s) failed "
              f"the audit and were not written: {', '.join(skipped)}")
        print("!! the pieces that were written are still printable; the set "
              "above is missing.")

    return result
