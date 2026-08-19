"""Command line front end.

Every field of :class:`~flowerpot.params.PotParams` automatically becomes a
``--flag`` (underscores turn into dashes), so the CLI can never drift out of
sync with the parameter model.

    python -m flowerpot --list-styles
    python -m flowerpot --pot-style hexagonal --height 120 --out pots/
    python -m flowerpot --all --generate-saucer
    python -m flowerpot --config my_pot.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path

from .analysis import Report, audit
from .build import build_pot, build_saucer
from .params import DRAINAGE_PATTERNS, ParameterError, PotParams, STYLES


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="flowerpot",
        description="Procedurally generate watertight, 3D-printable flower pot STLs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--out", "-o", default="output",
                    help="output directory (or a .stl path for a single pot)")
    ap.add_argument("--name", default=None, help="base filename; defaults to the style")
    ap.add_argument("--config", type=Path, default=None,
                    help="load parameters from a JSON file (CLI flags still win)")
    ap.add_argument("--save-config", type=Path, default=None,
                    help="write the resolved parameters to a JSON file")
    ap.add_argument("--all", action="store_true",
                    help="export one pot per style instead of a single pot")
    ap.add_argument("--list-styles", action="store_true", help="print the styles and exit")
    ap.add_argument("--ascii", action="store_true", help="write ASCII STL instead of binary")
    ap.add_argument("--force", action="store_true",
                    help="write the STL even if the print-readiness audit fails")
    ap.add_argument("--quiet", "-q", action="store_true", help="only print file paths")

    grp = ap.add_argument_group("pot parameters")
    for f in fields(PotParams):
        flag = "--" + f.name.replace("_", "-")
        default = getattr(PotParams(), f.name)
        if f.type == "bool" or isinstance(default, bool):
            grp.add_argument(flag, dest=f.name, action=argparse.BooleanOptionalAction,
                             default=None, help=f"(default: {default})")
        else:
            caster = {"float": float, "int": int, "str": str}[f.type]
            choices = None
            if f.name == "pot_style":
                choices = sorted(STYLES)
            elif f.name == "drainage_pattern":
                choices = list(DRAINAGE_PATTERNS)
            grp.add_argument(flag, dest=f.name, type=caster, default=None,
                             choices=choices, help=f"(default: {default})")
    return ap


def params_from_args(args: argparse.Namespace) -> PotParams:
    data: dict = {}
    if args.config:
        data.update(json.loads(Path(args.config).read_text()))
    for f in fields(PotParams):
        value = getattr(args, f.name, None)
        if value is not None:
            data[f.name] = value
    return PotParams.from_dict(data)


def _export(mesh, path: Path, ascii_stl: bool) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = mesh.export(file_type="stl_ascii" if ascii_stl else "stl")
    mode = "w" if isinstance(data, str) else "wb"
    with open(path, mode) as fh:
        fh.write(data)
    return path


def _emit(p: PotParams, out: Path, name: str, args) -> tuple[list[Path], bool]:
    """Build, audit and write one pot (plus its saucer).  Returns (paths, ok)."""
    written: list[Path] = []
    everything_ok = True

    for warning in p.validate():
        print(f"  WARN {warning}", file=sys.stderr)

    jobs = [(build_pot, f"{name}.stl")]
    if p.generate_saucer:
        jobs.append((build_saucer, f"{name}_saucer.stl"))

    for builder, filename in jobs:
        mesh = builder(p)
        report: Report = audit(mesh, p.overhang_limit_deg)
        if not args.quiet:
            print(f"\n{filename}")
            print(report)
        everything_ok &= report.ok
        if report.ok or args.force:
            target = out if out.suffix.lower() == ".stl" else out / filename
            written.append(_export(mesh, target, args.ascii))
            print(f"  -> {written[-1]}")
        else:
            print(f"  !! not written: audit failed (use --force to write anyway)",
                  file=sys.stderr)
    return written, everything_ok


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_styles:
        print("Available pot styles:\n")
        for key, blurb in STYLES.items():
            print(f"  {key:<18} {blurb}")
        print("\nDrainage patterns: " + ", ".join(DRAINAGE_PATTERNS))
        return 0

    try:
        params = params_from_args(args)
        params.validate()
    except ParameterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.save_config:
        Path(args.save_config).write_text(params.to_json())
        print(f"  -> {args.save_config}")

    out = Path(args.out)
    ok = True
    try:
        if args.all:
            for style in STYLES:
                sp = params.with_(pot_style=style)
                _, style_ok = _emit(sp, out, args.name or style, args)
                ok &= style_ok
        else:
            _, ok = _emit(params, out, args.name or params.pot_style, args)
    except ParameterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 0 if (ok or args.force) else 1


if __name__ == "__main__":
    raise SystemExit(main())
