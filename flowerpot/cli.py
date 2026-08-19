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

from .colors import PALETTE
from .export import export_pot
from .params import DRAINAGE_PATTERNS, ParameterError, PotParams, STYLES, TEXTURES


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
    ap.add_argument("--format", choices=["stl", "3mf", "both"], default="stl",
                    help="output format; 3mf carries the color (and rim accent)")
    ap.add_argument("--preview", action="store_true",
                    help="also render a PNG preview (needs matplotlib); "
                         "the image is embedded in the 3mf as its thumbnail")
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
            elif f.name == "surface_texture":
                choices = list(TEXTURES)
            elif f.name == "printer":
                from .printers import PRINTER_CHOICES
                choices = list(PRINTER_CHOICES)
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


def _emit(p: PotParams, out: Path, name: str, args) -> bool:
    formats = ("stl", "3mf") if args.format == "both" else (args.format,)
    result = export_pot(
        p, name, out, formats,
        preview=args.preview, force=args.force,
        ascii_stl=args.ascii, quiet=args.quiet,
    )
    return result.ok


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_styles:
        print("Available pot styles:\n")
        for key, blurb in STYLES.items():
            print(f"  {key:<18} {blurb}")
        print("\nDrainage patterns: " + ", ".join(DRAINAGE_PATTERNS))
        print("Surface textures:  " + ", ".join(TEXTURES))
        print("Colors:            " + ", ".join(sorted(PALETTE)) + ", or any #RRGGBB")
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
                ok &= _emit(sp, out, args.name or style, args)
        else:
            ok = _emit(params, out, args.name or params.pot_style, args)
    except ParameterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 0 if (ok or args.force) else 1


if __name__ == "__main__":
    raise SystemExit(main())
