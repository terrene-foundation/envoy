"""Tier 1: T-01-14 — cascade revocation wrapper + Shamir export/import hooks.

Source: shard `01-analysis/05-trust-store-implementation.md` § 4 steps 4-5 +
`specs/trust-lineage.md` § Cascade revocation + `specs/shamir-recovery.md`
§ Algorithm + § Recovery flow.

Capacity: ~150 LOC of test (parametric coverage of the 3 invariants —
cascade BFS reaches every active descendant; verify_cascade_complete
contract; Shamir master-key export+reimport round-trip).

Per `rules/testing.md` Tier 1: pure helpers + dataclass surfaces. Cascade
on an empty/non-seeded agent is idempotent (kailash contract) so we exercise
the BFS wrapper without standing up a full Genesis chain (which would be a
Tier 2 integration test).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from envoy.trust.errors import (
    CascadeIncompleteError,
    MasterKeySizeError,
    PrincipalRequiredError,
    RevocationNotFoundError,
    VaultLockedError,
    VaultUnlockFailedError,
)
from envoy.trust.store import TrustStoreAdapter
from envoy.trust.vault import TrustVault


PASSPHRASE = "test-passphrase-with-enough-entropy-r2-m-02"
PAYLOAD = b"phase-01 trust-vault test payload"


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / "vault.dat"


@pytest.fixture
async def adapter(tmp_path: Path) -> TrustStoreAdapter:
    a = TrustStoreAdapter(
        vault_path=tmp_path / "vault.dat",
        principal_id="test-principal-cascade",
    )
    await a.initialize()
    yield a
    await a.close()


# ---------------------------------------------------------------------------
# Cascade revocation — wrapper contract
# ---------------------------------------------------------------------------


class TestRevokeWrapper:
    async def test_revoke_unknown_agent_is_idempotent_noop(
        self, adapter: TrustStoreAdapter
    ) -> None:
        """kailash cascade_revoke contract: revoking an agent that is not in
        the chain returns success=True with empty revoked_agents (idempotency
        check at line 154 of kailash.trust.revocation.cascade)."""
        result = await adapter.revoke(
            agent_id="unknown-agent",
            reason="test",
            revoked_by="test-principal-cascade",
        )
        assert result.success is True
        assert result.revoked_agents == []
        assert result.errors == {}

    async def test_revoke_caches_result_for_verify_cascade_complete(
        self, adapter: TrustStoreAdapter
    ) -> None:
        """`revoke()` MUST cache the RevocationResult so subsequent
        `verify_cascade_complete(agent_id=...)` finds it. T-01-17 will
        replace the in-memory cache with persisted Ledger rows."""
        await adapter.revoke(
            agent_id="cached-agent",
            reason="test",
            revoked_by="test-principal-cascade",
        )
        assert "cached-agent" in adapter._last_revocations

    async def test_revoke_re_revoke_is_idempotent(self, adapter: TrustStoreAdapter) -> None:
        """Second revoke of the same agent_id returns the same idempotent
        no-op shape (kailash docstring lines 191-196)."""
        first = await adapter.revoke(
            agent_id="agent-001",
            reason="r1",
            revoked_by="test-principal-cascade",
        )
        second = await adapter.revoke(
            agent_id="agent-001",
            reason="r2",
            revoked_by="test-principal-cascade",
        )
        assert first.success is True
        assert second.success is True
        assert second.revoked_agents == []  # already-revoked = no-op

    @pytest.mark.parametrize(
        "unsafe_agent_id",
        ["../etc/passwd", "agent\x00bypass", ".hidden", "agent/with/slashes"],
    )
    async def test_revoke_rejects_unsafe_agent_id(
        self, adapter: TrustStoreAdapter, unsafe_agent_id: str
    ) -> None:
        """Path-traversal validation per rules/trust-plane-security.md MUST
        Rule 2 — every external ID flows through `_validate_id_safety`."""
        with pytest.raises(PrincipalRequiredError, match="safety validation"):
            await adapter.revoke(
                agent_id=unsafe_agent_id,
                reason="test",
                revoked_by="test-principal-cascade",
            )

    async def test_revoke_rejects_unsafe_revoked_by(self, adapter: TrustStoreAdapter) -> None:
        with pytest.raises(PrincipalRequiredError, match="safety validation"):
            await adapter.revoke(
                agent_id="agent-001",
                reason="test",
                revoked_by="../etc/shadow",
            )


# ---------------------------------------------------------------------------
# verify_cascade_complete — EC-8 cross-channel cascade defense
# ---------------------------------------------------------------------------


class TestVerifyCascadeComplete:
    async def test_returns_true_on_cached_idempotent_revocation(
        self, adapter: TrustStoreAdapter
    ) -> None:
        """An idempotent no-op revocation (no descendants) trivially passes
        verification — there are no descendants to be missing."""
        await adapter.revoke(
            agent_id="agent-leaf",
            reason="test",
            revoked_by="test-principal-cascade",
        )
        assert await adapter.verify_cascade_complete(agent_id="agent-leaf") is True

    async def test_raises_revocation_not_found_for_unknown_agent(
        self, adapter: TrustStoreAdapter
    ) -> None:
        """Looking up a never-revoked agent_id MUST raise RevocationNotFoundError
        (not silently return False) — silent False would hide a forgotten
        revoke() call."""
        with pytest.raises(RevocationNotFoundError, match="no cached"):
            await adapter.verify_cascade_complete(agent_id="never-revoked-agent")

    async def test_rejects_unsafe_agent_id(self, adapter: TrustStoreAdapter) -> None:
        with pytest.raises(PrincipalRequiredError, match="safety validation"):
            await adapter.verify_cascade_complete(agent_id="../etc/passwd")

    async def test_cached_result_per_agent_id(self, adapter: TrustStoreAdapter) -> None:
        """Revoking two distinct agent_ids caches BOTH RevocationResults;
        verify_cascade_complete looks up by agent_id key."""
        await adapter.revoke(
            agent_id="agent-A",
            reason="rA",
            revoked_by="test-principal-cascade",
        )
        await adapter.revoke(
            agent_id="agent-B",
            reason="rB",
            revoked_by="test-principal-cascade",
        )
        assert await adapter.verify_cascade_complete(agent_id="agent-A") is True
        assert await adapter.verify_cascade_complete(agent_id="agent-B") is True
        with pytest.raises(RevocationNotFoundError):
            await adapter.verify_cascade_complete(agent_id="agent-C")


# ---------------------------------------------------------------------------
# Shamir export — vault master key is exposed for SLIP-0039 splitting
# ---------------------------------------------------------------------------


class TestShamirExport:
    async def test_export_returns_32_byte_master_key(self, vault_path: Path) -> None:
        """Per specs/shamir-recovery.md § Algorithm: SLIP-0039 splits the
        32-byte master key (AES-256), NOT the passphrase."""
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        await v.unlock(PASSPHRASE)
        master_key = await v.export_master_key_for_shamir()
        assert isinstance(master_key, bytes)
        assert len(master_key) == 32
        await v.lock()

    async def test_export_returns_independent_copy(self, vault_path: Path) -> None:
        """The exported bytes MUST be a copy, not a reference into the vault's
        internal bytearray — otherwise mutating the export would corrupt the
        in-memory master key."""
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        await v.unlock(PASSPHRASE)
        export1 = await v.export_master_key_for_shamir()
        export2 = await v.export_master_key_for_shamir()
        assert export1 == export2  # same bytes
        assert export1 is not export2  # but different objects (fresh copy each call)
        await v.lock()

    async def test_export_requires_unlocked_vault(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        # Vault is sealed after create() — export must fail.
        with pytest.raises(VaultLockedError):
            await v.export_master_key_for_shamir()


# ---------------------------------------------------------------------------
# Shamir import — reconstructed master key installs vault state
# ---------------------------------------------------------------------------


class TestShamirImport:
    async def test_import_round_trip_through_export(self, vault_path: Path) -> None:
        """Export → lock → fresh-adapter import → read MUST round-trip the
        original payload. This is the canonical Shamir recovery flow:
        original passphrase derives key → split → shards → reconstruct →
        import without passphrase."""
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        await v.unlock(PASSPHRASE)
        master_key = await v.export_master_key_for_shamir()
        await v.lock()

        # Fresh adapter to simulate a clean Shamir recovery session.
        v2 = TrustVault(vault_path, idle_ttl_seconds=10)
        await v2.import_master_key_from_shamir(master_key)
        assert v2.is_unlocked
        assert (await v2.read()) == PAYLOAD
        await v2.lock()

    async def test_import_rejects_wrong_size(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        v2 = TrustVault(vault_path, idle_ttl_seconds=10)
        with pytest.raises(MasterKeySizeError, match="32 bytes"):
            await v2.import_master_key_from_shamir(b"too-short")
        with pytest.raises(MasterKeySizeError, match="32 bytes"):
            await v2.import_master_key_from_shamir(b"\x00" * 64)  # too long
        with pytest.raises(MasterKeySizeError, match="bytes-like"):
            await v2.import_master_key_from_shamir("not-bytes")  # type: ignore[arg-type]

    async def test_import_rejects_wrong_key_bytes(self, vault_path: Path) -> None:
        """Right size, wrong bytes → AES-GCM tag verification fails →
        VaultUnlockFailedError. The vault stays sealed."""
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        v2 = TrustVault(vault_path, idle_ttl_seconds=10)
        with pytest.raises(VaultUnlockFailedError, match="Shamir-reconstructed"):
            await v2.import_master_key_from_shamir(b"\x00" * 32)
        assert not v2.is_unlocked

    async def test_import_refused_on_unlocked_vault(self, vault_path: Path) -> None:
        """Phase 01 narrow scope: import installs a NEW master key on a
        sealed vault. Rotating an in-use master key is Phase 02
        `rotate_master_key` work."""
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        await v.unlock(PASSPHRASE)
        master_key = await v.export_master_key_for_shamir()
        # Vault still unlocked — import must refuse.
        with pytest.raises(VaultLockedError, match="sealed vault"):
            await v.import_master_key_from_shamir(master_key)
        await v.lock()

    async def test_import_on_missing_file_raises_filenotfound(self, tmp_path: Path) -> None:
        v = TrustVault(tmp_path / "no-such.dat", idle_ttl_seconds=10)
        with pytest.raises(FileNotFoundError):
            await v.import_master_key_from_shamir(b"\x00" * 32)
