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

    jobs: list[tuple] = [(build_pot, name, True)]
    if params.generate_saucer:
        jobs.append((build_saucer, f"{name}_saucer", False))

    # the accent color goes on the rim, whose foot height comes from the profile
    rim_z = build_profiles(params).decoration_freeze_z if params.accent_color else None

    for builder, stem, is_pot in jobs:
        if single_stem is not None:
            stem = single_stem if is_pot else f"{single_stem}_saucer"

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
