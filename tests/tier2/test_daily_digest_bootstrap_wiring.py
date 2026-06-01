"""Tier 2 — daily-digest bootstrap wiring (production call site).

Source: T-04-83 `build_digest_service` + `rules/orphan-detection.md` Rule 1 —
the bootstrap is the production call site the CLI uses; it MUST have automated
coverage (the EC-3 / service-wiring tests build the service manually, so the
actual bootstrap assembly path was previously exercised only by manual CLI
smoke-testing).

Verifies the real `build_digest_service` assembles a fully-wired, runnable
service against a real on-disk Trust vault: it starts, binds the cli channel,
drives `trigger_now` end-to-end, and tears down cleanly. Since B3 the ledger
backing is durable (file-backed `SqliteAuditStore` + OS-keychain signing key),
so the suite also pins the cross-process property: a fresh `build_digest_service`
over the SAME vault + keychain reopens the SAME ledger (EC-4).

No mocks (`rules/testing.md` Tier 2). The keychain backend is a pure-dict
adapter satisfying `envoy.ledger.keystore`'s contract — a Protocol-satisfying
deterministic adapter (NOT a mock per `rules/testing.md` § Tier 2 exception),
matching `tests/tier2/test_ledger_keystore_wiring.py` — so coverage exercises
the real durable-key persistence path without touching the host OS keychain.
"""

from __future__ import annotations

import keyring.errors
import pytest

from envoy.daily_digest import DailyDigestService
from envoy.daily_digest.bootstrap import build_digest_service
from envoy.ledger.keystore import LedgerKeyUnavailableError
from envoy.trust.store import TrustStoreAdapter

_PID = "principal-bootstrap-01"


class _MemBackend:
    """Pure-dict keyring backend (mirrors `test_ledger_keystore_wiring.py`)."""

    def __init__(self) -> None:
        self._d: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._d[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._d.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        key = (service, username)
        if key not in self._d:
            raise keyring.errors.PasswordDeleteError("not found")
        del self._d[key]


class _FailingBackend(_MemBackend):
    """Simulates a locked/unavailable OS keychain — read+write both raise."""

    def set_password(self, service: str, username: str, password: str) -> None:
        raise keyring.errors.KeyringError("keychain locked")

    def get_password(self, service: str, username: str) -> str | None:
        raise keyring.errors.KeyringError("keychain locked")


@pytest.fixture
def vault_path(tmp_path):
    return tmp_path / "trust_vault.db"


@pytest.fixture
def keyring_backend() -> _MemBackend:
    """A fresh in-memory keychain backend per test (function scope)."""
    return _MemBackend()


class TestBootstrapWiring:
    @pytest.mark.asyncio
    async def test_returns_wired_service_and_store(self, vault_path, keyring_backend) -> None:
        service, trust_store, channels, durable = await build_digest_service(
            vault_path=vault_path, principal_id=_PID, keyring_backend=keyring_backend
        )
        try:
            assert isinstance(service, DailyDigestService)
            assert isinstance(trust_store, TrustStoreAdapter)
            assert "cli" in channels
        finally:
            await durable.aclose()
            await trust_store.close()

    @pytest.mark.asyncio
    async def test_binds_cli_channel_as_primary(self, vault_path, keyring_backend) -> None:
        _service, trust_store, _channels, durable = await build_digest_service(
            vault_path=vault_path, principal_id=_PID, keyring_backend=keyring_backend
        )
        try:
            # The bootstrap idempotently binds cli as active+primary so the
            # duress reader + back-fill window have a primary to resolve.
            row = await trust_store.digest_active_channels_get(_PID)
            assert row is not None
            active, primary = row
            assert active == ["cli"]
            assert primary == "cli"
        finally:
            await durable.aclose()
            await trust_store.close()

    @pytest.mark.asyncio
    async def test_trigger_now_runs_through_bootstrap_path(
        self, vault_path, keyring_backend
    ) -> None:
        service, trust_store, channels, durable = await build_digest_service(
            vault_path=vault_path, principal_id=_PID, keyring_backend=keyring_backend
        )
        cli_adapter = channels["cli"]
        try:
            await cli_adapter.startup()
            await service.start()
            payload = await service.trigger_now(_PID)
            # End-to-end through the real bootstrap-assembled pipeline.
            assert payload.schema_version == "digest/1.0"
            assert payload.channel_id == "cli"
        finally:
            await service.stop()
            await cli_adapter.shutdown()
            await durable.aclose()
            await trust_store.close()

    @pytest.mark.asyncio
    async def test_existing_binding_not_overwritten(self, vault_path, keyring_backend) -> None:
        """Idempotency: a pre-existing channel binding survives bootstrap."""
        store = TrustStoreAdapter(vault_path=vault_path, principal_id=_PID)
        await store.initialize()
        from envoy.daily_digest.schedule_registry import ScheduleRegistry

        await ScheduleRegistry(trust_store=store).set_active_channels(
            _PID, channel_ids=["cli", "web"], primary="web"
        )
        await store.close()

        _service, trust_store, _channels, durable = await build_digest_service(
            vault_path=vault_path, principal_id=_PID, keyring_backend=keyring_backend
        )
        try:
            row = await trust_store.digest_active_channels_get(_PID)
            assert row is not None
            active, primary = row
            # Bootstrap MUST NOT clobber the pre-existing web-primary binding.
            assert primary == "web"
            assert set(active) == {"cli", "web"}
        finally:
            await durable.aclose()
            await trust_store.close()

    @pytest.mark.asyncio
    async def test_ledger_is_durable_across_bootstrap_calls(self, vault_path) -> None:
        """B3 deliverable: the production digest wiring uses the durable store +
        durable keychain key, so a FRESH `build_digest_service` over the SAME
        vault + SAME keychain backend reopens the SAME ledger — entries persist
        across "processes" and `verify_chain()` / `export()` succeed against the
        re-minted head (the EC-4 property the digest writer + `envoy ledger
        export` reader depend on). This is the B1+B2+shard-A integration at the
        production call site (each primitive's own Tier-2 test proves it in
        isolation; this proves the bootstrap wires them together)."""
        # ONE keychain backend reused across both builds → the SAME signing key,
        # so process-2's verify_chain checks process-1's entries against the key
        # that signed them (not a fresh ephemeral key, which would fail loud).
        backend = _MemBackend()

        # "Process 1": append a ledger entry through the bootstrap-wired ledger.
        _svc1, store1, _ch1, durable1 = await build_digest_service(
            vault_path=vault_path, principal_id=_PID, keyring_backend=backend
        )
        try:
            await durable1.ledger.append(entry_type="action", content={"k": "v"})
        finally:
            await durable1.aclose()
            await store1.close()

        # "Process 2": a fresh bootstrap over the same vault + keychain.
        _svc2, store2, _ch2, durable2 = await build_digest_service(
            vault_path=vault_path, principal_id=_PID, keyring_backend=backend
        )
        try:
            # The entry persisted and the chain rehydrated under the durable key.
            report = await durable2.ledger.verify_chain()
            assert report.success is True
            assert report.entries_verified == 1
            # export() works on the fresh process: rehydrate re-minted the signed
            # head (B2) and the durable key (B1) verifies it.
            bundle = await durable2.ledger.export()
            assert len(bundle.entries) == 1
        finally:
            await durable2.aclose()
            await store2.close()

    @pytest.mark.asyncio
    async def test_build_failure_closes_trust_store_no_leak(self, vault_path, monkeypatch) -> None:
        """Partial-construction guard (B3 gate finding): if the keychain load
        fails AFTER `trust_store.initialize()`, `build_digest_service` MUST close
        the trust store before re-raising. The caller never receives the 4-tuple,
        so its `finally` cannot run — without the guard the trust-store SQLite
        handles leak with no owner (per failed tick on the EC-3 cron daemon)."""
        closed: dict[str, int] = {"trust_store": 0}
        real_close = TrustStoreAdapter.close

        async def _spy_close(self: TrustStoreAdapter) -> None:
            closed["trust_store"] += 1
            await real_close(self)

        monkeypatch.setattr(TrustStoreAdapter, "close", _spy_close)

        # A locked keychain → fail-loud LedgerKeyUnavailableError, raised in the
        # window AFTER trust_store.initialize() — the exact leak path.
        with pytest.raises(LedgerKeyUnavailableError):
            await build_digest_service(
                vault_path=vault_path,
                principal_id=_PID,
                keyring_backend=_FailingBackend(),
            )

        # The guard ran trust_store.close() exactly once on the failure path.
        assert closed["trust_store"] == 1
