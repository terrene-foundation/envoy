"""Tier 1 unit tests for envoy.trust.store.TrustStoreAdapter.

Per `rules/testing.md` § Tier 1: mocking allowed; <1s per test. The kailash-py
SQLite stores accept `:memory:` paths so Tier 1 can exercise the integration
boundary without persistent infrastructure (the Tier 2 wiring test T-01-16
exercises against real file-backed SQLite).

Covers:
- principal_id discipline per `rules/tenant-isolation.md` Rule 2.
- Genesis seed lifecycle (seed once, refuse re-seed).
- Cross-principal seeding refusal.
- Delegation routing through TrustOperations.delegate (R2-M-04).
- TrustChainNotFoundError on missing principal.

Tests are async per `pyproject.toml [tool.pytest.ini_options].asyncio_mode = "auto"`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from envoy.trust.errors import (
    GenesisAlreadySeededError,
    PrincipalRequiredError,
    TrustChainNotFoundError,
)
from envoy.trust.store import TrustStoreAdapter
from envoy.trust.types import DelegationRequest, GenesisSeed


@pytest.fixture
def vault_path(tmp_path):
    return tmp_path / "alice.vault"


@pytest.fixture
async def adapter(vault_path):
    a = TrustStoreAdapter(vault_path=vault_path, principal_id="alice@example")
    await a.initialize()
    yield a
    await a.close()


@pytest.fixture
def alice_seed():
    return GenesisSeed(
        principal_id="alice@example",
        authority_id="authority-001",
        capabilities=("read_email", "send_email", "draft_response"),
        constraints=(),
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=30),
        metadata={"authority_name": "alice's home authority"},
    )


# ---------------------------------------------------------------------------
# principal_id discipline
# ---------------------------------------------------------------------------


class TestConstructorPrincipalIdDiscipline:
    def test_empty_principal_id_raises(self, vault_path) -> None:
        with pytest.raises(PrincipalRequiredError, match="principal_id"):
            TrustStoreAdapter(vault_path=vault_path, principal_id="")

    def test_none_principal_id_raises(self, vault_path) -> None:
        with pytest.raises(PrincipalRequiredError, match="principal_id"):
            TrustStoreAdapter(vault_path=vault_path, principal_id=None)  # type: ignore[arg-type]

    def test_non_string_principal_id_raises(self, vault_path) -> None:
        with pytest.raises(PrincipalRequiredError, match="principal_id"):
            TrustStoreAdapter(vault_path=vault_path, principal_id=42)  # type: ignore[arg-type]

    def test_valid_principal_id_succeeds(self, vault_path) -> None:
        a = TrustStoreAdapter(vault_path=vault_path, principal_id="alice@example")
        assert a.principal_id == "alice@example"


# ---------------------------------------------------------------------------
# Genesis seeding lifecycle
# ---------------------------------------------------------------------------


class TestGenesisSeedingLifecycle:
    async def test_seed_genesis_succeeds_for_fresh_principal(
        self, adapter: TrustStoreAdapter, alice_seed: GenesisSeed
    ) -> None:
        result = await adapter.seed_genesis(alice_seed)
        assert result.principal_id == "alice@example"
        assert result.chain_hash  # non-empty hex
        assert len(result.chain_hash) == 64  # sha256 hex
        assert result.capabilities_seeded == ("read_email", "send_email", "draft_response")
        # signature_algorithm matches kailash-py's algorithm_identifier
        assert "ed25519" in result.genesis_signature_algorithm.lower()

    async def test_re_seed_raises_genesis_already_seeded(
        self, adapter: TrustStoreAdapter, alice_seed: GenesisSeed
    ) -> None:
        await adapter.seed_genesis(alice_seed)
        with pytest.raises(GenesisAlreadySeededError, match="cascade revoke"):
            await adapter.seed_genesis(alice_seed)

    async def test_seed_genesis_with_cross_principal_seed_refused(
        self, adapter: TrustStoreAdapter
    ) -> None:
        wrong_seed = GenesisSeed(
            principal_id="bob@example",  # adapter is alice's
            authority_id="authority-001",
            capabilities=("read_email",),
        )
        with pytest.raises(PrincipalRequiredError, match="does not match"):
            await adapter.seed_genesis(wrong_seed)


# ---------------------------------------------------------------------------
# get_chain
# ---------------------------------------------------------------------------


class TestGetChain:
    async def test_missing_principal_raises_chain_not_found(
        self, adapter: TrustStoreAdapter
    ) -> None:
        with pytest.raises(TrustChainNotFoundError):
            await adapter.get_chain("nonexistent@example")

    async def test_empty_principal_id_raises(self, adapter: TrustStoreAdapter) -> None:
        with pytest.raises(PrincipalRequiredError, match="principal_id required"):
            await adapter.get_chain("")

    async def test_seeded_principal_chain_is_retrievable(
        self, adapter: TrustStoreAdapter, alice_seed: GenesisSeed
    ) -> None:
        await adapter.seed_genesis(alice_seed)
        chain = await adapter.get_chain("alice@example")
        assert chain is not None
        assert chain.genesis.agent_id == "alice@example"


# ---------------------------------------------------------------------------
# Delegation routing (R2-M-04 — through TrustOperations.delegate)
# ---------------------------------------------------------------------------


class TestDelegationRouting:
    """R2-M-04 carry-forward — delegation routes through kailash-py 10-step
    verification (cycle-free, depth-bounded, capability-intersection)."""

    async def test_delegate_with_cross_principal_delegator_refused(
        self, adapter: TrustStoreAdapter
    ) -> None:
        # delegator_id must equal the adapter's principal_id (the adapter IS
        # the delegator's adapter — bob would use his own adapter to delegate).
        req = DelegationRequest(
            delegator_id="bob@example",  # adapter is alice's
            delegatee_id="charlie@example",
            task_id="task-001",
            capabilities=("read_email",),
        )
        with pytest.raises(PrincipalRequiredError, match="does not match"):
            await adapter.record_delegation(req)

    async def test_delegate_succeeds_for_owned_capability(
        self, adapter: TrustStoreAdapter, alice_seed: GenesisSeed
    ) -> None:
        """R2-M-04: happy-path delegation through TrustOperations.delegate."""
        await adapter.seed_genesis(alice_seed)
        req = DelegationRequest(
            delegator_id="alice@example",
            delegatee_id="bob@example",
            task_id="task-fwd-email-001",
            capabilities=("send_email",),  # alice WAS seeded with send_email
        )
        record = await adapter.record_delegation(req)
        assert record.delegator_id == "alice@example"
        assert record.delegatee_id == "bob@example"
        assert record.task_id == "task-fwd-email-001"

    async def test_delegate_unowned_capability_refused_by_kailash(
        self, adapter: TrustStoreAdapter, alice_seed: GenesisSeed
    ) -> None:
        """R2-M-04: kailash-py's 10-step verification rejects delegating
        capabilities the delegator does not own. This is the structural
        defense the carry-forward mandate exists to ensure runs."""
        from kailash.trust.exceptions import CapabilityNotFoundError

        await adapter.seed_genesis(alice_seed)
        # alice was seeded with (read_email, send_email, draft_response);
        # 'admin_settings' is NOT in that set.
        req = DelegationRequest(
            delegator_id="alice@example",
            delegatee_id="bob@example",
            task_id="task-admin-001",
            capabilities=("admin_settings",),
        )
        with pytest.raises(CapabilityNotFoundError):
            await adapter.record_delegation(req)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_close_is_idempotent(self, vault_path) -> None:
        a = TrustStoreAdapter(vault_path=vault_path, principal_id="alice@example")
        await a.initialize()
        await a.close()
        # Second close should not raise
        await a.close()

    async def test_initialize_is_idempotent(self, vault_path) -> None:
        a = TrustStoreAdapter(vault_path=vault_path, principal_id="alice@example")
        await a.initialize()
        await a.initialize()
        await a.close()

    async def test_vault_path_property(self, vault_path) -> None:
        a = TrustStoreAdapter(vault_path=vault_path, principal_id="alice@example")
        assert a.vault_path == vault_path
        await a.close()
