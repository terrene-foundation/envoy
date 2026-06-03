"""Regression: round-1 /redteam observability fixes (MED-1, MED-2, MED-3, MED-10).

Round 1 of the /implement-cycle redteam landed 4 distinct WARN log lines that
operators rely on to surface degraded paths in the WARN+ scan
(`rules/observability.md` Rule 5):

- `trust_vault.write.chmod_failed` — POSIX chmod failed; vault may be world-readable.
- `trust_vault.read_metadata.parse_failed` — payload exists but is not the
  metadata envelope (legacy passthrough OR corruption).
- `envelope.compiler.using_noop_authorship_scorer` — Phase-01 NoOp default in use.
- `envelope.compiler.using_noop_ledger_writer` — Phase-01 NoOp default in use.

These were shipped without regression tests asserting the log key. Round 2
of /redteam classified that as MED (R2-MED-LOG-1 + R2-MED-COV-1, same surface):
the underlying behavior IS exercised, but the operator's WARN-key contract
is unguarded — a future refactor that renames or drops the log key would
break the `grep mode=fake` / `grep trust_vault.write.chmod_failed` audit
without any test signal.

This file pins the contract: each of the 4 log keys MUST fire on its
documented trigger condition. Per `rules/testing.md` § Regression Testing
this test is permanent and MUST NOT be deleted.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from envoy.envelope.compiler import EnvelopeCompiler
from envoy.envelope.template_resolver import LocalTemplateResolver
from envoy.trust.vault import TrustVault


PASSPHRASE = "regression-r2-observability-passphrase-with-entropy"


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / "vault.dat"


@pytest.fixture
async def unlocked_vault(vault_path: Path) -> AsyncGenerator[TrustVault, None]:
    """Created + unlocked TrustVault, locked on teardown so it is not GC'd
    while unlocked (rules/testing.md "Fixtures Yield + Cleanup"; mirrors the
    tier2/3 conftest `unlocked_vault`). Without the teardown lock, the vault's
    `__del__` emits a ResourceWarning at GC."""
    v = TrustVault(vault_path, idle_ttl_seconds=10)
    await v.create(b"phase-01-init", PASSPHRASE)
    await v.unlock(PASSPHRASE)
    try:
        yield v
    finally:
        await v.lock()


@pytest.fixture
def resolver(tmp_path: Path) -> LocalTemplateResolver:
    return LocalTemplateResolver(root=tmp_path)


@pytest.mark.regression
class TestRound1EnvelopeCompilerNoopWarns:
    """MED-10 — `envelope.compiler.using_noop_*` WARN at construction when
    Phase-01 NoOp defaults are used. Per `rules/observability.md` Rule 3
    (`mode=fake` field) and `rules/zero-tolerance.md` Rule 2 fake-dispatch
    defense. Operator's `grep mode=fake` audit MUST find these."""

    def test_noop_authorship_scorer_emits_warn_at_construction(
        self, resolver: LocalTemplateResolver, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="envoy.envelope.compiler"):
            EnvelopeCompiler(template_resolver=resolver)
        keys = {r.message for r in caplog.records}
        assert "envelope.compiler.using_noop_authorship_scorer" in keys
        # mode=fake field is the operator's grep target.
        scorer_records = [
            r
            for r in caplog.records
            if r.message == "envelope.compiler.using_noop_authorship_scorer"
        ]
        assert len(scorer_records) == 1
        assert getattr(scorer_records[0], "mode", None) == "fake"
        assert getattr(scorer_records[0], "reason", None) == "phase_01_default"

    def test_noop_ledger_writer_emits_warn_at_construction(
        self, resolver: LocalTemplateResolver, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="envoy.envelope.compiler"):
            EnvelopeCompiler(template_resolver=resolver)
        keys = {r.message for r in caplog.records}
        assert "envelope.compiler.using_noop_ledger_writer" in keys
        writer_records = [
            r for r in caplog.records if r.message == "envelope.compiler.using_noop_ledger_writer"
        ]
        assert len(writer_records) == 1
        assert getattr(writer_records[0], "mode", None) == "fake"


@pytest.mark.regression
class TestRound1TrustVaultReadMetadataParseFailedWarn:
    """MED-3 — `trust_vault.read_metadata.parse_failed` WARN when the
    decrypted payload exists but is not a JSON metadata envelope. The
    legacy-passthrough returns `{}` to preserve backward-compat, but the
    operator MUST see the WARN to investigate corruption-vs-legacy."""

    async def test_read_metadata_logs_parse_failed_on_non_json_payload(
        self, unlocked_vault: TrustVault, caplog: pytest.LogCaptureFixture
    ) -> None:
        vault = unlocked_vault
        # Write OPAQUE bytes the metadata envelope cannot parse — this is the
        # legacy-passthrough scenario the WARN is designed to surface.
        await vault.write(b"opaque-non-json-payload-from-legacy-callsite")

        with caplog.at_level(logging.WARNING, logger="envoy.trust.vault"):
            result = await vault.read_metadata()

        assert result == {}
        keys = {r.message for r in caplog.records}
        assert "trust_vault.read_metadata.parse_failed" in keys

        parse_records = [
            r for r in caplog.records if r.message == "trust_vault.read_metadata.parse_failed"
        ]
        assert len(parse_records) == 1
        # error_type + payload_len fields are the triage signals (NOT the
        # raw payload — secrets must never be logged per rules/security.md).
        assert getattr(parse_records[0], "error_type", None) is not None
        assert getattr(parse_records[0], "payload_len", None) is not None
        assert isinstance(parse_records[0].payload_len, int)


@pytest.mark.regression
class TestRound1TrustVaultWriteChmodFailedWarn:
    """MED-2 — `trust_vault.write.chmod_failed` WARN when POSIX `os.chmod`
    raises after `os.replace`. Disk-full / immutable-bit / FS-without-chmod
    paths MUST surface in the operator's WARN+ scan because the vault file
    may be world-readable. Silent-swallow is BLOCKED per
    `rules/zero-tolerance.md` Rule 3."""

    async def test_write_logs_chmod_failed_when_chmod_raises(
        self,
        unlocked_vault: TrustVault,
        vault_path: Path,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        if os.name != "posix":
            pytest.skip("chmod path is POSIX-only per vault.py guard")
        vault = unlocked_vault

        # Patch os.chmod ONLY for the upcoming write — the vault.create()
        # already finished, so we don't disturb the existing file's perms.
        original_chmod = os.chmod
        chmod_calls = {"count": 0}

        def chmod_raises(path, mode, *args, **kwargs):
            # Match the post-replace chmod target only — the vault path itself.
            if str(path) == str(vault_path):
                chmod_calls["count"] += 1
                raise OSError("simulated chmod failure (regression r2)")
            return original_chmod(path, mode, *args, **kwargs)

        monkeypatch.setattr(os, "chmod", chmod_raises)

        with caplog.at_level(logging.WARNING, logger="envoy.trust.vault"):
            await vault.write(b"phase-01 payload after chmod-fail simulation")

        assert chmod_calls["count"] >= 1
        keys = {r.message for r in caplog.records}
        assert "trust_vault.write.chmod_failed" in keys

        chmod_records = [r for r in caplog.records if r.message == "trust_vault.write.chmod_failed"]
        assert len(chmod_records) == 1
        # path_repr is the operator's triage breadcrumb — quoted (repr)
        # so embedded whitespace / special chars do not break log parsing.
        assert getattr(chmod_records[0], "path_repr", None) is not None


@pytest.mark.regression
class TestRound1MetadataEnvelopeRoundTripDoesNotLog:
    """Negative regression: a NORMAL metadata envelope round-trip MUST NOT
    fire `trust_vault.read_metadata.parse_failed` (the WARN is degraded-path
    only). Without this guard, a future refactor that mis-classifies the
    happy path as "parse failed" would silently flood operator logs."""

    async def test_round_trip_emits_no_parse_failed_warn(
        self, unlocked_vault: TrustVault, caplog: pytest.LogCaptureFixture
    ) -> None:
        vault = unlocked_vault

        await vault.write_metadata({"hello": "world", "n": 42})

        with caplog.at_level(logging.WARNING, logger="envoy.trust.vault"):
            result = await vault.read_metadata()

        assert result == {"hello": "world", "n": 42}
        keys = {r.message for r in caplog.records}
        assert "trust_vault.read_metadata.parse_failed" not in keys
