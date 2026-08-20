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
        if params.generate_saucer:
            jobs.append((build_saucer, f"{name}_saucer", False))

    # the accent color goes on the rim, whose foot height comes from the profile
    rim_z = build_profiles(params).decoration_freeze_z if params.accent_color else None

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
            print("  !! not written: audit failed (use force to write anyway)",
                  file=sys.stderr)
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

    return result
