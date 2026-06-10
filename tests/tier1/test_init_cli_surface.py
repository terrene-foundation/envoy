# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1: ``envoy init`` CLI surface registration (S4i).

Source: WS-6 S4i — the ``init`` subcommand is registered on the root ``envoy``
group (8th of 10 canonical CLI groups) and surfaces in ``envoy --help``. Per
`rules/user-flow-validation.md`: the registration is exercised through the
actual click surface (the user's literal `--help` path), not just an import.

Per `rules/testing.md` § Tier 1: in-process click ``CliRunner``, <1s, no infra.
"""

from __future__ import annotations

from click.testing import CliRunner

from envoy.cli.init import init as init_group
from envoy.cli.main import cli


def test_init_group_registered_on_root() -> None:
    assert "init" in cli.commands
    assert cli.commands["init"] is init_group


def test_envoy_help_lists_init() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0, result.output
    assert "init" in result.output


def test_init_help_describes_setup() -> None:
    result = CliRunner().invoke(cli, ["init", "--help"])
    assert result.exit_code == 0, result.output
    # The group surfaces its first-time-setup purpose + the `run` subcommand.
    assert "run" in result.output


def test_init_run_requires_principal() -> None:
    """`init run` with no principal + no ENVOY_PRINCIPAL_ID fails cleanly with a
    usage error naming the missing principal — not a stack trace."""
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "run"], env={"ENVOY_PRINCIPAL_ID": ""})
    assert result.exit_code != 0
    assert "principal" in result.output.lower()
