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

from pathlib import Path

from click.testing import CliRunner

from envoy.cli.init import EXIT_ALREADY_INITIALIZED
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


# ---------------------------------------------------------------------------
# Write-once already-initialized pre-check (ENVOY-P2-W2G-001).
#
# Re-running `init run` against a vault that already exists MUST exit cleanly
# with code 30 + a plain-language message, WITHOUT first prompting for the
# passphrase or the 9 ritual answers. These tests go through the REAL CLI
# composition (root group → init run → existence pre-check); they do NOT call
# build_init_runtime directly — the pre-check lives in the click command itself,
# so only a CLI-composition test exercises it (the tier-3 idempotency test
# bypasses the command and drives build_init_runtime).
# ---------------------------------------------------------------------------


def test_init_run_existing_vault_exits_30_without_prompting(tmp_path: Path) -> None:
    """`init run` against a PRE-EXISTING vault exits 30 + plain-language message,
    and consumes NO passphrase input (empty stdin still yields a clean exit 30,
    proving the prompt was never reached)."""
    vault_file = tmp_path / "trust_vault.db"
    vault_file.write_bytes(b"pre-existing vault container")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["init", "run", "--principal", "user-42", "--vault", str(vault_file)],
        # Empty stdin: if the command reached the passphrase prompt it would
        # error on EOF (non-zero, NOT 30). A clean exit 30 proves the pre-check
        # short-circuited BEFORE any prompt consumed input.
        input="",
    )

    assert result.exit_code == EXIT_ALREADY_INITIALIZED, result.output
    # Plain-language message a non-technical user can act on (no traceback).
    assert "already set up" in result.output.lower()
    assert "shamir recover" in result.output.lower()
    # The passphrase prompt text MUST NOT appear — the pre-check fired first.
    assert "choose a vault passphrase" not in result.output.lower()
    # No traceback / exception leaked through.
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_init_run_existing_vault_via_env_var_exits_30(tmp_path: Path) -> None:
    """The same pre-check fires when the vault path comes from ENVOY_VAULT_PATH
    (the env-var resolution path), not just the --vault flag."""
    vault_file = tmp_path / "env_vault.db"
    vault_file.write_bytes(b"pre-existing vault container")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["init", "run"],
        env={"ENVOY_PRINCIPAL_ID": "user-99", "ENVOY_VAULT_PATH": str(vault_file)},
        input="",
    )

    assert result.exit_code == EXIT_ALREADY_INITIALIZED, result.output
    assert "already set up" in result.output.lower()
