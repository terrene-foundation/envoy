"""Tier 2 — `envoy ledger export` CLI (EC-4 / EC-9 producer surface).

Source: shard C of the durable-ledger-export workstream + `specs/ledger.md`
§ "Export + independent verifier" + `specs/independent-verifier.md` § "Bundle
wire format". The CLI is the production producer the separately-codebased
Independent Verifier consumes (`envoy ledger export` writes a file; the verifier
reads it).

Verifies the real CLI against a real on-disk durable ledger: it opens the SAME
ledger a writer (the daily digest) appends to — via the shared
`envoy.ledger.bootstrap` identity constants — exports the signed bundle, and the
bundle round-trips with a self-consistent `receipt_hash` (the verifier's
invariant-8 self-integrity check, recomputed here independently).

Per `rules/testing.md` Tier 2: real `SqliteAuditStore` + real Ed25519 signing.
The keychain backend is a Protocol-satisfying in-memory adapter installed via
`keyring.set_keyring` (NOT a mock per the Tier-2 carve-out) so the CLI's real
production keychain path runs without touching the host OS keychain — the CLI
itself takes no backend-injection seam (production uses the OS keychain).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import keyring
import pytest
from click.testing import CliRunner
from keyring.backend import KeyringBackend

from envoy.cli.ledger import ledger as ledger_group
from envoy.ledger import compute_receipt_hash
from envoy.ledger.bootstrap import (
    LEDGER_ALGORITHM_IDENTIFIER,
    LEDGER_DEVICE_ID,
    LEDGER_SIGNING_KEY_ID,
    open_durable_ledger,
)
from envoy.ledger.keystore import load_or_create_ledger_key_manager

PID = "ledger-cli-principal-01"


@pytest.fixture
def mem_keyring() -> Iterator[None]:
    """Install a process-local in-memory keychain backend for the duration of
    the test, then restore the host's real backend. Lets the CLI's production
    keychain path (no injection seam) run hermetically."""
    store: dict[tuple[str, str], str] = {}

    class _Mem(KeyringBackend):
        priority = 1  # type: ignore[assignment]

        def get_password(self, service: str, username: str) -> str | None:
            return store.get((service, username))

        def set_password(self, service: str, username: str, password: str) -> None:
            store[(service, username)] = password

        def delete_password(self, service: str, username: str) -> None:
            store.pop((service, username), None)

    previous = keyring.get_keyring()
    keyring.set_keyring(_Mem())
    try:
        yield
    finally:
        keyring.set_keyring(previous)


async def _seed_entries(vault_path: Path, n: int) -> None:
    """Append `n` entries to the SAME durable ledger the CLI will export — the
    writer side of the cross-process flow, opened through the shared identity."""
    key_manager = await load_or_create_ledger_key_manager(
        principal_id=PID, signing_key_id=LEDGER_SIGNING_KEY_ID
    )
    durable = await open_durable_ledger(
        vault_path=vault_path,
        key_manager=key_manager,
        signing_key_id=LEDGER_SIGNING_KEY_ID,
        device_id=LEDGER_DEVICE_ID,
        algorithm_identifier=LEDGER_ALGORITHM_IDENTIFIER,
    )
    try:
        for i in range(n):
            await durable.ledger.append(entry_type="action", content={"i": i})
    finally:
        await durable.aclose()


class TestLedgerExportCli:
    def test_ledger_group_exposes_only_export(self) -> None:
        """Canonical Phase-01 surface: `ledger {export}` (shard 19 § 3.4)."""
        assert set(ledger_group.commands.keys()) == {"export"}

    def test_export_rejects_pdf_format(self) -> None:
        """Phase 01 is JSON-only; PDF is Phase 02 — click rejects the choice."""
        result = CliRunner().invoke(
            ledger_group, ["export", "--format", "pdf", "--principal", "x@y"]
        )
        assert result.exit_code == 2  # click usage error: invalid choice
        assert "pdf" in result.output.lower() or "invalid" in result.output.lower()

    def test_export_empty_ledger_errors_clean(self, tmp_path: Path, mem_keyring: None) -> None:
        """An empty ledger cannot be exported (verifier invariant 1). The CLI
        surfaces a clean, actionable error — never a raw traceback."""
        vault_path = tmp_path / "trust_vault.db"
        result = CliRunner().invoke(
            ledger_group, ["export", "--principal", PID, "--vault", str(vault_path)]
        )
        assert result.exit_code == 1
        assert "nothing to export" in result.output.lower()
        assert "Traceback" not in result.output

    def test_export_round_trip_writes_verifiable_bundle(
        self, tmp_path: Path, mem_keyring: None
    ) -> None:
        """The EC-4 producer property through the real CLI: a writer appends to
        the durable ledger, then `envoy ledger export -o` writes a bundle whose
        entries are present and whose `receipt_hash` self-verifies (the
        verifier's invariant-8 check, recomputed independently here)."""
        vault_path = tmp_path / "trust_vault.db"
        asyncio.run(_seed_entries(vault_path, 2))

        bundle_path = tmp_path / "bundle.json"
        result = CliRunner().invoke(
            ledger_group,
            ["export", "-o", str(bundle_path), "--principal", PID, "--vault", str(vault_path)],
        )
        assert result.exit_code == 0, result.output
        assert bundle_path.exists()

        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        assert len(bundle["entries"]) == 2
        assert bundle["receipt_hash"].startswith("sha256:")
        # Verifier invariant 8 — receipt is sha256 of the canonical bundle minus
        # receipt_hash. Recomputed independently from the on-disk artifact.
        minus = {k: v for k, v in bundle.items() if k != "receipt_hash"}
        assert compute_receipt_hash(minus) == bundle["receipt_hash"]

    def test_export_to_stdout_when_no_output(self, tmp_path: Path, mem_keyring: None) -> None:
        """With no --output the bundle goes to stdout as clean JSON, so
        `envoy ledger export > bundle.json` works (logs go to stderr)."""
        vault_path = tmp_path / "trust_vault.db"
        asyncio.run(_seed_entries(vault_path, 1))

        result = CliRunner().invoke(
            ledger_group, ["export", "--principal", PID, "--vault", str(vault_path)]
        )
        assert result.exit_code == 0, result.output
        bundle = json.loads(result.output)
        assert len(bundle["entries"]) == 1
        assert bundle["receipt_hash"].startswith("sha256:")
