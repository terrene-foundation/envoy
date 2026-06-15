# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2: `envoy runtime show / switch` CLI surface (S3p Wire).

In-process `CliRunner` against the real `envoy.cli.main:cli`, exercising the
real `TrustVault` + durable `EnvoyLedger` end-to-end (the `InMemoryKeyringBackend`
via `ENVOY_KEYRING=memory` is the headless signing seam, NOT a mock). These ARE
the user-flow walk for S3p Wire (`rules/user-flow-validation.md`): invoke the
command the user invokes, observe the output the user sees.

Signature verification in `show --principal` is NOT exercised here: under the
memory keyring each process mints a fresh key (the documented headless seam), so
a switch-then-show pair across two invocations cannot share the signing key.
That cross-process path is covered by the in-process Tier-2 state-machine tests
(`test_runtime_switch.py`) where one key manager spans the write+verify.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from click.testing import CliRunner

from envoy.cli.main import cli
from envoy.runtime.runtime_picker import read_runtime_choice
from envoy.trust.vault import TrustVault

_PRINCIPAL_ID = "s3p-cli-principal"
_PASSPHRASE = "correct horse battery staple"


def _make_vault(vault_path: Path) -> None:
    async def _create() -> None:
        vault = TrustVault(vault_path, idle_ttl_seconds=900)
        await vault.create(b"envoy-genesis-install", _PASSPHRASE)

    asyncio.run(_create())


@pytest.fixture
def runtime_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Path]:
    """Point the runtime CLI at tmp vault + config paths under a memory keyring."""
    vault_path = tmp_path / "trust_vault.db"
    choice_path = tmp_path / "runtime-choice.json"
    monkeypatch.setenv("ENVOY_KEYRING", "memory")
    monkeypatch.setenv("ENVOY_VAULT_PATH", str(vault_path))
    monkeypatch.setenv("ENVOY_RUNTIME_CHOICE_PATH", str(choice_path))
    monkeypatch.setenv("ENVOY_PRINCIPAL_ID", _PRINCIPAL_ID)
    return {"vault": vault_path, "choice": choice_path}


def test_runtime_registered_on_root_group() -> None:
    assert "runtime" in cli.commands


def test_runtime_has_show_and_switch() -> None:
    sub = cli.commands["runtime"].commands  # type: ignore[attr-defined]
    assert set(sub) == {"show", "switch"}


def test_show_no_config_reports_default(runtime_env: dict[str, Path]) -> None:
    result = CliRunner().invoke(cli, ["runtime", "show"])
    assert result.exit_code == 0, result.output
    assert "no explicit choice yet" in result.output
    assert "kailash-py" in result.output


def test_switch_happy_path_flips_default(runtime_env: dict[str, Path]) -> None:
    _make_vault(runtime_env["vault"])
    result = CliRunner().invoke(
        cli,
        ["runtime", "switch", "kailash-py", "--passphrase-stdin"],
        input=_PASSPHRASE + "\n",
    )
    assert result.exit_code == 0, result.output
    # Confirm copy — transparent disclosure of exactly what changed.
    assert "Runtime switched: kailash-py → kailash-py" in result.output
    assert "Ledger entry:" in result.output
    assert "Active runtime is now kailash-py." in result.output
    # The durable default was written.
    choice = read_runtime_choice()
    assert choice is not None
    assert choice.runtime_family == "kailash-py"


def test_show_after_switch_reports_active_family(runtime_env: dict[str, Path]) -> None:
    _make_vault(runtime_env["vault"])
    runner = CliRunner()
    switch = runner.invoke(
        cli,
        ["runtime", "switch", "kailash-py", "--passphrase-stdin"],
        input=_PASSPHRASE + "\n",
    )
    assert switch.exit_code == 0, switch.output
    # `show` without --principal reports the active family + honestly states the
    # signature was not checked (never a fake "verified").
    show = runner.invoke(cli, ["runtime", "show"], env={"ENVOY_PRINCIPAL_ID": ""})
    assert show.exit_code == 0, show.output
    assert "Active runtime: kailash-py" in show.output
    assert "Signature: not checked" in show.output


def test_show_with_principal_under_memory_keyring_is_honest(
    runtime_env: dict[str, Path],
) -> None:
    # Under the ephemeral memory keyring the show-process key differs from the
    # switch-process key, so the signature does not verify. The output MUST be
    # the honest ambiguous ⚠ message — NEVER a false "TAMPERED" alarm and NEVER
    # a fake "verified".
    _make_vault(runtime_env["vault"])
    runner = CliRunner()
    switch = runner.invoke(
        cli,
        ["runtime", "switch", "kailash-py", "--passphrase-stdin"],
        input=_PASSPHRASE + "\n",
    )
    assert switch.exit_code == 0, switch.output
    show = runner.invoke(cli, ["runtime", "show"])  # ENVOY_PRINCIPAL_ID set by fixture
    assert show.exit_code == 0, show.output
    assert "could not be verified" in show.output
    assert "TAMPERED" not in show.output
    assert "✓ verified" not in show.output


def test_switch_no_vault_exits_50(runtime_env: dict[str, Path]) -> None:
    # No vault created — switch refuses with the run-init guidance.
    result = CliRunner().invoke(
        cli,
        ["runtime", "switch", "kailash-py", "--passphrase-stdin"],
        input=_PASSPHRASE + "\n",
    )
    assert result.exit_code == 50, result.output
    assert "envoy init" in result.output


def test_switch_no_principal_exits_20(
    runtime_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_vault(runtime_env["vault"])
    monkeypatch.delenv("ENVOY_PRINCIPAL_ID", raising=False)
    result = CliRunner().invoke(
        cli,
        ["runtime", "switch", "kailash-py", "--passphrase-stdin"],
        input=_PASSPHRASE + "\n",
    )
    assert result.exit_code == 20, result.output
    assert "no principal" in result.output


def test_switch_wrong_passphrase_exits_51(runtime_env: dict[str, Path]) -> None:
    _make_vault(runtime_env["vault"])
    result = CliRunner().invoke(
        cli,
        ["runtime", "switch", "kailash-py", "--passphrase-stdin"],
        input="wrong-passphrase\n",
    )
    assert result.exit_code == 51, result.output
    assert "Vault unlock failed" in result.output
    # The default was NOT flipped.
    assert read_runtime_choice() is None


def test_switch_rejects_unknown_target() -> None:
    # Click's Choice validation rejects an unknown target before any work.
    result = CliRunner().invoke(
        cli, ["runtime", "switch", "kailash-julia", "--passphrase-stdin"]
    )
    assert result.exit_code != 0
