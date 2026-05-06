"""Tier 2 integration-test conftest.

Per `rules/testing.md` § Tier 2: real infrastructure recommended; NO mocking.
The Tier 2 fixtures spin up real `InMemoryKeyManager` + real `TrustVault`
(Argon2id + AES-256-GCM) + real `EnvoyLedger` over `InMemoryAuditStore`.

Phase 01 narrow scope: kailash's `SqliteAuditStore` requires a `kailash.db`
ConnectionManager pool (file-backed via `aiosqlite`); the pool plumbing
adds substantial scope beyond Phase 01 Wave 1's foundation work. The Tier 2
integration here uses `InMemoryAuditStore` (still real — same kailash code
path; just memory-backed). T-01-21+ adds the file-backed SqliteAuditStore
wiring once the kailash db pool fixture lands.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from kailash.trust.audit_store import InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.ledger import EnvoyLedger
from envoy.trust.vault import TrustVault


SIGNING_KEY_ID = "envoy-tier2-signing-key"
DEVICE_ID = "device-tier2-integration"
PASSPHRASE = "tier2-integration-passphrase-with-entropy"
VALID_ALGO_ID = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}


@pytest.fixture
async def signing_keymgr() -> AsyncGenerator[InMemoryKeyManager, None]:
    """Real kailash InMemoryKeyManager with one Ed25519 keypair generated.

    Per security review L-1 (T-01-16/21): the keymgr's `_keys` dict is
    cleared on teardown via the close() path that T-01-15 wired —
    minimizes private-key residency across test boundaries.
    """
    mgr = InMemoryKeyManager()
    await mgr.generate_keypair(SIGNING_KEY_ID)
    yield mgr
    # Best-effort zeroize on teardown; mgr.close is sync per kailash 2.13.4
    # but the close path may evolve in future versions — defensive call.
    keys_dict = getattr(mgr, "_keys", None)
    if isinstance(keys_dict, dict):
        keys_dict.clear()


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / "tier2-vault.dat"


@pytest.fixture
async def unlocked_vault(vault_path: Path) -> AsyncGenerator[TrustVault, None]:
    """Real TrustVault: create + unlock + ready to read/write payload.

    Per security review M-3 (T-01-16/21): try/finally around yield so
    the vault locks cleanly on every exit path, including when create
    succeeds but unlock raises mid-fixture.
    """
    v = TrustVault(vault_path, idle_ttl_seconds=60)
    try:
        await v.create(b"tier2-initial-payload", PASSPHRASE)
        await v.unlock(PASSPHRASE)
        yield v
    finally:
        if v.is_unlocked:
            await v.lock()


@pytest.fixture
def audit_store() -> InMemoryAuditStore:
    """Real kailash InMemoryAuditStore (chain-integrity checked)."""
    return InMemoryAuditStore()


@pytest.fixture
async def envoy_ledger(
    audit_store: InMemoryAuditStore, signing_keymgr: InMemoryKeyManager
) -> EnvoyLedger:
    """Real EnvoyLedger over real InMemoryAuditStore + real Ed25519 sign."""
    return EnvoyLedger(
        audit_store=audit_store,
        key_manager=signing_keymgr,
        signing_key_id=SIGNING_KEY_ID,
        device_id=DEVICE_ID,
        algorithm_identifier=VALID_ALGO_ID,
    )
