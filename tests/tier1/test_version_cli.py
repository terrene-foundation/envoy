"""Tier 1 tests for `envoy version` (F5.2 Wave-5 CLI surface).

Pins three invariants:

1. **Output shape** — `envoy version` prints `envoy <__version__>` and exits 0.
2. **Surface stability** — the command is registered on the root group under
   the name `version` (AST/registration-locked so a rename is a loud failure).
3. **Version consistency** — `pyproject.toml::version` equals
   `envoy.__version__` (per `rules/zero-tolerance.md` Rule 5; guards against
   the 0.0.0/0.1.0 drift this shard reconciled).

Tier 1 scope: pure in-process click `CliRunner` + a file read of
`pyproject.toml`. No infrastructure, no disk state.
"""

from __future__ import annotations

import pathlib

import tomllib
from click.testing import CliRunner

import envoy
from envoy.cli.main import cli
from envoy.cli.version import version as version_command

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_version_command_prints_dunder_and_exits_ok() -> None:
    result = CliRunner().invoke(cli, ["version"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == f"envoy {envoy.__version__}"


def test_version_registered_on_root_group() -> None:
    assert "version" in cli.commands
    assert cli.commands["version"] is version_command


def test_version_consistency_pyproject_vs_dunder() -> None:
    """pyproject.toml::version MUST equal envoy.__version__ (zero-tolerance R5)."""
    pyproject = _REPO_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    declared = data["project"]["version"]
    assert declared == envoy.__version__, (
        f"pyproject.toml version={declared!r} drifts from "
        f"envoy.__version__={envoy.__version__!r} — keep them in lockstep "
        f"(rules/zero-tolerance.md Rule 5)."
    )
