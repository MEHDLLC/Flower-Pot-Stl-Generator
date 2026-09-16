"""Every workflow's command line, parsed.

The rest of the suite drives the Python API, so a workflow that builds a
command the CLI cannot parse is invisible to it - the generate step dies
before it writes anything and the first you know is a failed dispatch.

That has happened: three boolean inputs were passed as ``--flag true``,
which argparse takes as a flag plus a stray positional, because the CLI
builds its flags from the dataclass and bools come out as
``BooleanOptionalAction``.  This is the cheap test that would have caught
it - it substitutes each workflow's own declared defaults into its
``cli_args`` and hands the result to the parser.  No geometry is built.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from flowerpot.cli import build_parser, params_from_args

WORKFLOWS = sorted((Path(__file__).resolve().parents[1]
                    / ".github" / "workflows").glob("generate-*.yml"))
#: generate-common.yml is the callee - it has no inputs of its own to run
CALLERS = [w for w in WORKFLOWS if w.name != "generate-common.yml"]


def _defaults(spec: dict) -> dict:
    """Each input's declared default, typed the way GitHub types it."""
    out = {}
    for name, field in (spec.get("on", spec.get(True, {}))
                        .get("workflow_dispatch", {})
                        .get("inputs", {}).items()):
        value = field.get("default", "")
        if field.get("type") == "boolean" and not isinstance(value, bool):
            value = str(value).lower() == "true"
        out[name] = value
    return out


def _expand(text: str, inputs: dict) -> str:
    """Resolve the ``${{ ... }}`` expressions these workflows actually use.

    Only the handful of forms in this repo: a bare input, and the ternary
    ``cond && 'a' || 'b'`` over equality, truthiness, ``startsWith``,
    ``contains`` and ``format``.
    GitHub's ternary and Python's ``and``/``or`` agree as long as the
    middle term is a non-empty string, which it always is here.
    """
    def one(m: re.Match) -> str:
        expr = m.group(1).strip()
        py = expr.replace("&&", " and ").replace("||", " or ")
        py = re.sub(r"\btrue\b", "True", py)
        py = re.sub(r"\bfalse\b", "False", py)
        py = re.sub(r"startsWith\(([^,]+),\s*([^)]+)\)",
                    r"(\1).startswith(\2)", py)
        py = re.sub(r"contains\(([^,]+),\s*('[^']*')\)", r"(\2 in (\1))", py)
        py = re.sub(r"format\((.+)\)$", r"_fmt(\1)", py)
        py = re.sub(r"\binputs\.(\w+)\b", r'I["\1"]', py)
        env = {"I": inputs, "_fmt": lambda t, *a: t.format(*a)}
        value = eval(py, {"__builtins__": {}}, env)  # noqa: S307
        return "" if value is None else str(value)
    return re.sub(r"\$\{\{(.+?)\}\}", one, text)


@pytest.mark.parametrize("path", CALLERS, ids=lambda p: p.name)
def test_the_command_a_workflow_builds_is_one_the_cli_can_parse(path):
    spec = yaml.safe_load(path.read_text())
    inputs = _defaults(spec)
    jobs = spec["jobs"]
    args = [j["with"]["cli_args"] for j in jobs.values() if "with" in j]
    assert args, f"{path.name} passes no cli_args"
    for raw in args:
        argv = _expand(raw, inputs).split()
        assert argv, path.name
        parsed = build_parser().parse_args(argv)     # the bit that broke
        assert params_from_args(parsed) is not None


@pytest.mark.parametrize("path", CALLERS, ids=lambda p: p.name)
def test_every_boolean_input_is_passed_as_a_flag_and_not_as_a_value(path):
    """``--wall-pot-liner true`` is what went wrong: GitHub renders a
    boolean input as the string true/false, and these flags take no
    value."""
    spec = yaml.safe_load(path.read_text())
    fields = (spec.get("on", spec.get(True, {}))
              .get("workflow_dispatch", {}).get("inputs", {}))
    body = path.read_text()
    for name, field in fields.items():
        if field.get("type") != "boolean":
            continue
        assert not re.search(r"--[\w-]+ \$\{\{\s*inputs\." + name + r"\s*\}\}",
                             body), (
            f"{path.name}: {name} is passed as a value; use the "
            f"--${{{{ x == false && 'no-' || '' }}}}flag form")


@pytest.mark.parametrize("path", CALLERS, ids=lambda p: p.name)
def test_every_input_a_workflow_declares_is_one_it_uses(path):
    spec = yaml.safe_load(path.read_text())
    fields = (spec.get("on", spec.get(True, {}))
              .get("workflow_dispatch", {}).get("inputs", {}))
    body = path.read_text()
    for name in fields:
        assert f"inputs.{name}" in body.split("cli_args")[-1] \
            or f"inputs.{name}" in body, f"{path.name}: {name} is declared " \
                                         f"and never used"
