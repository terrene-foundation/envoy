"""Tier 1 tests for `envoy posture` (F5.2 Wave-5 CLI surface).

Pins the invariants of the READ half of the posture-ladder CLI
(`specs/posture-ladder.md`):

1. **Fresh-store default** — a principal with no recorded transition shows
   `SUPERVISED` (the store's safe default); the command NEVER raises on a
   fresh vault, so it works on first run before Genesis seeding.
2. **Plain-language output** — the output names the tier AND a plain-language
   description (per `rules/communication.md`).
3. **Principal required** — no `--principal` and no `ENVOY_PRINCIPAL_ID`
   exits non-zero with an actionable message (no silent default principal,
   per tenant-isolation discipline).
4. **Surface stability** — `posture` is registered on the root group.
5. **Adapter read-delegation** — `TrustStoreAdapter.current_posture()` returns
   the SQLite-backed posture (default `SUPERVISED` on a fresh store).

Tier 1 scope: real `TrustStoreAdapter` over a real (temp-dir) SQLite posture
store — no mocking of the store — plus in-process click `CliRunner`.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from envoy.cli.main import cli
from envoy.cli.posture import posture as posture_command
from envoy.trust.store import TrustStoreAdapter

_PID = "alice@example"


@pytest.fixture()
def vault_path(tmp_path):
    return tmp_path / "trust_vault.db"


def test_posture_show_fresh_store_defaults_supervised(vault_path, monkeypatch) -> None:
    monkeypatch.delenv("ENVOY_PRINCIPAL_ID", raising=False)
    monkeypatch.delenv("ENVOY_VAULT_PATH", raising=False)
    result = CliRunner().invoke(
        cli,
        ["posture", "--principal", _PID, "--vault", str(vault_path)],
    )
    assert result.exit_code == 0, result.output
    assert "SUPERVISED" in result.output
    # Plain-language description present (communication.md) — not a bare enum.
    assert "approve" in result.output.lower() or "plan" in result.output.lower()


def test_posture_requires_principal(vault_path, monkeypatch) -> None:
    monkeypatch.delenv("ENVOY_PRINCIPAL_ID", raising=False)
    result = CliRunner().invoke(cli, ["posture", "--vault", str(vault_path)])
    assert result.exit_code != 0
    assert "principal" in result.output.lower()


def test_posture_registered_on_root_group() -> None:
    assert "posture" in cli.commands
    assert cli.commands["posture"] is posture_command


@pytest.mark.asyncio
async def test_current_posture_adapter_default_supervised(vault_path) -> None:
    adapter = TrustStoreAdapter(vault_path=vault_path, principal_id=_PID)
    try:
        await adapter.initialize()
        current = await adapter.current_posture()
    finally:
        await adapter.close()
    # str-backed enum; value is the lowercase spec token.
    assert current.value == "supervised"
