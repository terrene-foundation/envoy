"""Tier 3 acceptance conftest — REAL EVERYTHING for the EC-1 acceptance gate.

Per `rules/testing.md` § Tier 3: real browser, real database, real bindings.
For Envoy Phase 01 there is no browser; "real everything" reduces to:
real ``InMemoryKeyManager`` (Ed25519) + real file-backed ``TrustVault``
(Argon2id + AES-256-GCM) + real ``InMemoryAuditStore`` (chain-integrity
checked) + real ``EnvoyLedger`` (Ed25519-signed) + real ``TrustStoreAdapter``
(sqlite + per-principal isolation) + real ``EnvelopeCompiler`` + real
``ShamirRitualCoordinator`` (SLIP-0039 over the real Trust Vault) + real
``NoveltyChecker`` + real Ollama daemon driving real ``kaizen.LlmClient``.

Phase 01 narrow scope per `tests/tier2/conftest.py` rationale: kailash's
``SqliteAuditStore`` requires the kailash.db ConnectionManager pool that
T-01-21+ wires in; until then the InMemoryAuditStore is the chain-integrity-
checked real path. Real-Ollama is the load-bearing CI tier per shard 8 § 6.3.

Per `rules/testing.md` § Tier 2/3 NO mocking: every collaborator above is the
real production class. The deterministic-BYOM-provider shape used in some
Tier 2 sibling tests is NOT used here — Tier 3 EC-1 demands the production
LLM path.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from kailash.trust.audit_store import InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.ledger import EnvoyLedger
from envoy.trust.vault import TrustVault

SIGNING_KEY_ID = "envoy-tier3-signing-key"
DEVICE_ID = "device-tier3-acceptance"
PASSPHRASE = "tier3-acceptance-passphrase-with-entropy"
VALID_ALGO_ID = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}


@pytest.fixture
async def signing_keymgr() -> AsyncGenerator[InMemoryKeyManager, None]:
    mgr = InMemoryKeyManager()
    await mgr.generate_keypair(SIGNING_KEY_ID)
    yield mgr
    keys_dict = getattr(mgr, "_keys", None)
    if isinstance(keys_dict, dict):
        keys_dict.clear()


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / "tier3-vault.dat"


@pytest.fixture
async def unlocked_vault(vault_path: Path) -> AsyncGenerator[TrustVault, None]:
    """Real TrustVault: create + unlock + ready to read/write payload."""
    v = TrustVault(vault_path, idle_ttl_seconds=60)
    try:
        await v.create(b"tier3-initial-payload", PASSPHRASE)
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
