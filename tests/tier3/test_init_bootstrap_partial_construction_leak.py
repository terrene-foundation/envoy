"""Partial-construction resource-leak guard for `build_init_runtime` (R2-Q-01).

The Wave-2 red-team review surfaced a leak window: `vault.unlock()`,
`trust_store.initialize()`, and `session_router.open()` were acquired OUTSIDE
the reverse-order cleanup `try`. A failure in any of them propagated WITHOUT
running cleanup — most dangerously leaving the `TrustVault` UNLOCKED, with the
live master key resident in memory, and the trust-store / session-router SQLite
handles open with no owner (the CLI caller never receives the `InitBootstrap`,
so its own `finally` cannot run).

The fix moves those acquisitions inside the `try`; this test pins the
security-critical invariant: a failure after unlock MUST lock the vault and
close every already-acquired handle, exactly once, before re-raising. Mirrors
``tests/tier2/test_daily_digest_bootstrap_wiring.py::test_build_failure_closes_trust_store_no_leak``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from envoy.boundary_conversation.init_bootstrap import build_init_runtime
from envoy.ledger.keystore import (
    InMemoryKeyringBackend,
    LedgerKeyUnavailableError,
)
from envoy.runtime.session import SessionRouter
from envoy.trust.store import TrustStoreAdapter
from envoy.trust.vault import TrustVault

_PASS = "leak-guard-pass-1234"


class _FailingKeyringBackend:
    """A keyring backend whose first access raises — stands in for a locked OS
    keychain. The failure lands at the ledger-key load, AFTER trust_store +
    session_router are fully open and the vault is unlocked."""

    def get_password(self, service: str, username: str) -> str | None:
        raise keyring_unavailable()

    def set_password(self, service: str, username: str, password: str) -> None:
        raise keyring_unavailable()

    def delete_password(self, service: str, username: str) -> None:  # pragma: no cover
        raise keyring_unavailable()


def keyring_unavailable() -> Exception:
    import keyring.errors

    return keyring.errors.KeyringError("injected: keychain locked")


@pytest.mark.asyncio
async def test_build_failure_at_session_open_locks_vault_no_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inject a failure at session_router.open() — the leak window the fix closes.

    The vault is unlocked by then; without the fix it stayed unlocked (master key
    in memory). Assert vault.lock() + trust_store.close() ran exactly once and the
    vault is locked on the failure path, and the ORIGINAL error propagates.
    """
    calls = {"vault_lock": 0, "trust_close": 0, "router_close": 0}

    real_vault_lock = TrustVault.lock
    real_trust_close = TrustStoreAdapter.close

    async def spy_vault_lock(self: TrustVault) -> None:
        calls["vault_lock"] += 1
        await real_vault_lock(self)  # actually lock — prove the master key is gone

    async def spy_trust_close(self: TrustStoreAdapter) -> None:
        calls["trust_close"] += 1
        await real_trust_close(self)  # trust_store fully initialized → real close is safe

    async def spy_router_close(self: SessionRouter) -> None:
        # The router never opened (open() raised), so there is no handle to close;
        # count only, to avoid closing a never-opened router.
        calls["router_close"] += 1

    async def failing_open(self: SessionRouter) -> None:
        raise RuntimeError("injected: session_router.open failure")

    monkeypatch.setattr(TrustVault, "lock", spy_vault_lock)
    monkeypatch.setattr(TrustStoreAdapter, "close", spy_trust_close)
    monkeypatch.setattr(SessionRouter, "close", spy_router_close)
    monkeypatch.setattr(SessionRouter, "open", failing_open)

    vault_path = tmp_path / "leak.vault"
    with pytest.raises(RuntimeError, match="session_router.open failure"):
        await build_init_runtime(
            vault_path=vault_path,
            principal_id="leak-principal",
            passphrase=_PASS,
            trust_anchor_dir=tmp_path,
            keyring_backend=InMemoryKeyringBackend(),
        )

    # The security-critical invariant: the vault was locked on the failure path.
    assert calls["vault_lock"] == 1, "vault not locked → master key leaked in memory"
    assert calls["trust_close"] == 1, "trust_store not closed → SQLite handle leaked"
    assert calls["router_close"] == 1, "session_router cleanup not attempted"


@pytest.mark.asyncio
async def test_build_failure_at_ledger_load_locks_vault_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Daily-digest-style path: the keychain load fails AFTER trust_store +
    session_router are fully open. Cleanup must close both and lock the vault."""
    calls = {"vault_lock": 0, "trust_close": 0, "router_close": 0}

    real_vault_lock = TrustVault.lock
    real_trust_close = TrustStoreAdapter.close
    real_router_close = SessionRouter.close

    async def spy_vault_lock(self: TrustVault) -> None:
        calls["vault_lock"] += 1
        await real_vault_lock(self)

    async def spy_trust_close(self: TrustStoreAdapter) -> None:
        calls["trust_close"] += 1
        await real_trust_close(self)

    async def spy_router_close(self: SessionRouter) -> None:
        calls["router_close"] += 1
        await real_router_close(self)  # router fully open here → real close is safe

    monkeypatch.setattr(TrustVault, "lock", spy_vault_lock)
    monkeypatch.setattr(TrustStoreAdapter, "close", spy_trust_close)
    monkeypatch.setattr(SessionRouter, "close", spy_router_close)

    vault_path = tmp_path / "leak2.vault"
    with pytest.raises(LedgerKeyUnavailableError):
        await build_init_runtime(
            vault_path=vault_path,
            principal_id="leak-principal-2",
            passphrase=_PASS,
            trust_anchor_dir=tmp_path,
            keyring_backend=_FailingKeyringBackend(),
        )

    assert calls["vault_lock"] == 1
    assert calls["trust_close"] == 1
    assert calls["router_close"] == 1
