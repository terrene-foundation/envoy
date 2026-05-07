"""Tier 1: TrustVault — AES-256-GCM container + Argon2id + idle-lock lifecycle.

Source: T-01-13 per `01-wave-1-foundation.md` line 111 + spec authority
`specs/trust-vault.md` § File format + § Encryption + § Memory hygiene +
§ Error taxonomy.

Capacity: ~300 LOC test (parametric coverage of the 5 R2-M-02 lifecycle
invariants + the 4 typed errors that fire at Wave 1).

Per `rules/testing.md` Tier 1: pure helpers + dataclass surfaces. Argon2id
KDF is real (not mocked) — the test parameters use the canonical m=2^17
values per `specs/trust-vault.md` § Encryption, so a Tier 1 invocation runs
the full KDF (~50ms each) which is well within Tier 1's <1s budget.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from envoy.trust.errors import (
    Argon2ParameterMismatchError,
    AutoLockIdleTimeoutError,
    VaultLockedError,
    VaultMACVerificationFailedError,
    VaultUnlockFailedError,
)
from envoy.trust.vault import DEFAULT_IDLE_TTL_SECONDS, TrustVault


PASSPHRASE = "test-passphrase-with-enough-entropy-r2-m-02"
PAYLOAD = b"phase-01 trust-vault test payload"


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / "vault.dat"


# ---------------------------------------------------------------------------
# Construction + introspection
# ---------------------------------------------------------------------------


class TestConstructionDefaults:
    def test_default_idle_ttl_is_15_minutes(self, vault_path: Path) -> None:
        """Per specs/trust-vault.md § Memory hygiene 'Auto-lock after 15min idle'."""
        v = TrustVault(vault_path)
        assert v._idle_ttl_seconds == 15 * 60
        assert DEFAULT_IDLE_TTL_SECONDS == 15 * 60

    def test_idle_ttl_must_be_positive(self, vault_path: Path) -> None:
        with pytest.raises(ValueError, match="idle_ttl_seconds"):
            TrustVault(vault_path, idle_ttl_seconds=0)
        with pytest.raises(ValueError, match="idle_ttl_seconds"):
            TrustVault(vault_path, idle_ttl_seconds=-1)

    def test_constructed_vault_is_sealed(self, vault_path: Path) -> None:
        v = TrustVault(vault_path)
        assert not v.is_unlocked
        assert not v.exists_on_disk


# ---------------------------------------------------------------------------
# create() — fresh container initialization
# ---------------------------------------------------------------------------


class TestCreate:
    async def test_create_writes_file_and_leaves_sealed(self, vault_path: Path) -> None:
        """create() initializes the on-disk container but does NOT leave the
        vault unlocked — caller must explicitly unlock to read the payload.
        Defensive against the "create-then-walk-away-still-decrypted" leak."""
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        assert v.exists_on_disk
        assert not v.is_unlocked

    async def test_create_refuses_to_overwrite_existing(self, vault_path: Path) -> None:
        """Re-create requires explicit destroy-keys workflow (Phase 02 CLI).
        Silent overwrite would lose the existing master key irrecoverably."""
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        with pytest.raises(FileExistsError, match="destroy-keys"):
            await v.create(b"different", PASSPHRASE)

    async def test_create_rejects_empty_passphrase(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        with pytest.raises(VaultUnlockFailedError, match="passphrase"):
            await v.create(PAYLOAD, "")


# ---------------------------------------------------------------------------
# unlock() — passphrase verification + payload retrieval
# ---------------------------------------------------------------------------


class TestUnlock:
    @pytest.fixture
    async def created(self, vault_path: Path) -> Path:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        return vault_path

    async def test_correct_passphrase_unlocks_and_decrypts(self, created: Path) -> None:
        v = TrustVault(created, idle_ttl_seconds=10)
        await v.unlock(PASSPHRASE)
        assert v.is_unlocked
        assert (await v.read()) == PAYLOAD
        await v.lock()

    async def test_wrong_passphrase_raises_unlock_failed(self, created: Path) -> None:
        v = TrustVault(created, idle_ttl_seconds=10)
        with pytest.raises(VaultUnlockFailedError):
            await v.unlock("wrong-passphrase")
        assert not v.is_unlocked

    async def test_unlock_on_missing_file_raises_filenotfound(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        with pytest.raises(FileNotFoundError):
            await v.unlock(PASSPHRASE)

    async def test_unlock_is_idempotent(self, created: Path) -> None:
        v = TrustVault(created, idle_ttl_seconds=10)
        await v.unlock(PASSPHRASE)
        await v.unlock(PASSPHRASE)  # second call no-ops; should not re-derive
        assert v.is_unlocked
        await v.lock()

    async def test_empty_passphrase_rejected(self, created: Path) -> None:
        v = TrustVault(created, idle_ttl_seconds=10)
        with pytest.raises(VaultUnlockFailedError, match="passphrase"):
            await v.unlock("")

    async def test_empty_passphrase_rejected_even_when_already_unlocked(
        self, created: Path
    ) -> None:
        """L-03 contract: empty passphrase MUST raise BEFORE the is_unlocked
        idempotent short-circuit. Defense against zero-cost brute force AND
        consistent error contract — the rejection happens regardless of vault
        state."""
        v = TrustVault(created, idle_ttl_seconds=10)
        await v.unlock(PASSPHRASE)
        assert v.is_unlocked
        with pytest.raises(VaultUnlockFailedError, match="passphrase"):
            await v.unlock("")
        # Vault should still be unlocked from the first call (the second call
        # rejected the bad input but did not undo the prior unlock).
        assert v.is_unlocked
        await v.lock()


# ---------------------------------------------------------------------------
# read() / write() — sealed-state guards + round-trip
# ---------------------------------------------------------------------------


class TestReadWriteGuards:
    async def test_read_on_sealed_vault_raises_vault_locked(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        # Vault is sealed after create() — reading without unlock() must fail.
        with pytest.raises(VaultLockedError):
            await v.read()

    async def test_write_on_sealed_vault_raises_vault_locked(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        with pytest.raises(VaultLockedError):
            await v.write(b"would corrupt")

    async def test_write_then_read_round_trip(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        await v.unlock(PASSPHRASE)
        await v.write(b"updated payload")
        assert (await v.read()) == b"updated payload"
        await v.lock()
        # Re-unlock with a fresh adapter and verify on-disk state survived.
        v2 = TrustVault(vault_path, idle_ttl_seconds=10)
        await v2.unlock(PASSPHRASE)
        assert (await v2.read()) == b"updated payload"
        await v2.lock()


# ---------------------------------------------------------------------------
# lock() — lifecycle + zeroize
# ---------------------------------------------------------------------------


class TestLock:
    async def test_lock_seals_vault(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        await v.unlock(PASSPHRASE)
        assert v.is_unlocked
        await v.lock()
        assert not v.is_unlocked
        with pytest.raises(VaultLockedError):
            await v.read()

    async def test_lock_is_idempotent(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        await v.lock()  # already sealed; should be a no-op
        await v.lock()
        assert not v.is_unlocked

    async def test_lock_zeroes_internal_master_key_reference(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        await v.unlock(PASSPHRASE)
        # Snapshot the bytearray BEFORE lock; lock() zeros it in place AND
        # drops the reference. Defensive: post-lock, the bytearray we held
        # should be all zeros (best-effort hygiene per
        # rules/trust-plane-security.md MUST NOT Rule 3).
        held = v._master_key
        assert held is not None
        assert any(b != 0 for b in held), "pre-lock key should be non-zero"
        await v.lock()
        assert v._master_key is None
        # The bytearray we still reference SHOULD have been zeroed in-place.
        assert all(b == 0 for b in held), "lock() must zeroize the master-key bytearray in-place"


# ---------------------------------------------------------------------------
# Idle-lock timer (R2-M-02)
# ---------------------------------------------------------------------------


class TestIdleLock:
    async def test_idle_timer_auto_locks_after_ttl(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=0.2)
        await v.create(PAYLOAD, PASSPHRASE)
        await v.unlock(PASSPHRASE)
        assert v.is_unlocked
        await asyncio.sleep(0.4)  # past the 0.2s TTL
        assert not v.is_unlocked
        with pytest.raises(AutoLockIdleTimeoutError):
            await v.read()

    async def test_activity_resets_idle_timer(self, vault_path: Path) -> None:
        """`read()` / `write()` must reset the idle timer; otherwise active
        use within the TTL window would surprise the caller with auto-lock."""
        v = TrustVault(vault_path, idle_ttl_seconds=0.3)
        await v.create(PAYLOAD, PASSPHRASE)
        await v.unlock(PASSPHRASE)
        # Tick activity at half-TTL twice — total elapsed ~0.4s but each gap
        # is only 0.15s, so the timer never fires.
        await asyncio.sleep(0.15)
        assert (await v.read()) == PAYLOAD
        await asyncio.sleep(0.15)
        assert (await v.read()) == PAYLOAD
        # Vault is still unlocked because every access reset the timer.
        assert v.is_unlocked
        await v.lock()

    async def test_idle_timer_burst_cancel_recreate_no_premature_lock(
        self, vault_path: Path
    ) -> None:
        """100 rapid activity ticks MUST NOT race with the idle-lock task into
        a state where the vault auto-locks while the caller is actively using
        it. Coverage for the cancel-and-recreate race-safety guarantee per
        the captured-task-identity check in `_idle_lock_after_ttl`.
        """
        v = TrustVault(vault_path, idle_ttl_seconds=0.5)
        await v.create(PAYLOAD, PASSPHRASE)
        await v.unlock(PASSPHRASE)
        # Burst of 100 read() calls in tight succession — each call invokes
        # `_touch_activity()` which cancels the prior timer task and schedules
        # a new one. The captured-task-identity check inside the timer body
        # guards against the race where a stale timer task finds itself no
        # longer the owner and silently exits.
        for _ in range(100):
            assert (await v.read()) == PAYLOAD
        # Vault MUST still be unlocked after the burst — none of the 100
        # cancelled timer tasks should have fired auto-lock.
        assert v.is_unlocked
        # Final on-disk state survived (write path is unaffected).
        await v.write(b"after-burst")
        assert (await v.read()) == b"after-burst"
        await v.lock()


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestUnlockedContextManager:
    async def test_unlocked_cm_unlocks_on_entry_locks_on_exit(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        async with v.unlocked(PASSPHRASE) as inner:
            assert inner.is_unlocked
            assert (await inner.read()) == PAYLOAD
        assert not v.is_unlocked  # lock() ran on exit

    async def test_unlocked_cm_locks_on_exception_path(self, vault_path: Path) -> None:
        """Exception during the `async with` body MUST still trigger lock()
        (anti-leak: if the body crashes mid-decrypted, vault must seal)."""
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        with pytest.raises(RuntimeError, match="boom"):
            async with v.unlocked(PASSPHRASE):
                raise RuntimeError("boom")
        assert not v.is_unlocked


# ---------------------------------------------------------------------------
# File-format integrity (AAD covers the header)
# ---------------------------------------------------------------------------


class TestFileFormatIntegrity:
    async def test_truncated_file_raises_mac_verification_error(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        # Truncate the file to half its size; reading should raise.
        size = vault_path.stat().st_size
        data = vault_path.read_bytes()
        vault_path.write_bytes(data[: size // 2])
        v2 = TrustVault(vault_path, idle_ttl_seconds=10)
        with pytest.raises(VaultMACVerificationFailedError):
            await v2.unlock(PASSPHRASE)

    async def test_magic_bytes_corruption_raises_mac_verification_error(
        self, vault_path: Path
    ) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        # Flip the first magic byte
        data = bytearray(vault_path.read_bytes())
        data[0] = data[0] ^ 0xFF
        vault_path.write_bytes(bytes(data))
        v2 = TrustVault(vault_path, idle_ttl_seconds=10)
        with pytest.raises(VaultMACVerificationFailedError, match="magic"):
            await v2.unlock(PASSPHRASE)

    async def test_ciphertext_byte_flip_raises_unlock_failed(self, vault_path: Path) -> None:
        """A flipped byte INSIDE the ciphertext (not the header) trips the
        AES-GCM tag verifier rather than the header-level magic check.
        Surfaces as VaultUnlockFailedError per the documented mapping (the
        decrypt path can't distinguish wrong-key from tamper)."""
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        data = bytearray(vault_path.read_bytes())
        # Flip one byte well inside the ciphertext (past the 53-byte header)
        flip_index = 60
        if flip_index < len(data):
            data[flip_index] = data[flip_index] ^ 0xFF
        vault_path.write_bytes(bytes(data))
        v2 = TrustVault(vault_path, idle_ttl_seconds=10)
        with pytest.raises(VaultUnlockFailedError):
            await v2.unlock(PASSPHRASE)


# ---------------------------------------------------------------------------
# Argon2id parameter strict-match
# ---------------------------------------------------------------------------


class TestPayloadLenMemoryDosBound:
    async def test_inflated_payload_len_rejected(self, vault_path: Path) -> None:
        """M-3 (gate review): a tampered header that declares a multi-GiB
        payload_len MUST be rejected at read-time before f.read() allocates.
        The bound is the Phase 04 padding-bucket ceiling (64 MiB)."""
        import struct

        from envoy.trust.vault import _HEADER_FMT, _HEADER_LEN

        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        data = bytearray(vault_path.read_bytes())
        magic, version, payload_len, salt, m, t, p, nonce = struct.unpack(
            _HEADER_FMT, bytes(data[:_HEADER_LEN])
        )
        # Inflate payload_len to 1 GiB — well past the 64 MiB ceiling.
        new_header = struct.pack(
            _HEADER_FMT,
            magic,
            version,
            1 << 30,  # 1 GiB
            salt,
            m,
            t,
            p,
            nonce,
        )
        data[:_HEADER_LEN] = new_header
        vault_path.write_bytes(bytes(data))
        v2 = TrustVault(vault_path, idle_ttl_seconds=10)
        with pytest.raises(VaultMACVerificationFailedError, match="exceeds max"):
            await v2.unlock(PASSPHRASE)


class TestSymlinkRejection:
    async def test_symlink_redirect_rejected(self, tmp_path: Path) -> None:
        """M-01 (security review): vault file resolved via O_NOFOLLOW so a
        symlink redirect (e.g. an attacker pointing the vault path at
        /etc/shadow) is rejected at open time rather than silently followed."""
        import os
        import sys

        if not hasattr(os, "O_NOFOLLOW"):
            pytest.skip("O_NOFOLLOW not available on this platform")
        if sys.platform == "win32":
            pytest.skip("symlink redirect test runs on POSIX only")

        real_target = tmp_path / "real-vault.dat"
        v = TrustVault(real_target, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)

        # Create a symlink from a different path pointing at the real vault
        symlink_path = tmp_path / "symlinked.dat"
        symlink_path.symlink_to(real_target)
        # A vault opened via the symlink path MUST be rejected.
        v2 = TrustVault(symlink_path, idle_ttl_seconds=10)
        with pytest.raises(VaultMACVerificationFailedError, match="symlink redirect"):
            await v2.unlock(PASSPHRASE)


class TestArgon2ParameterStrictMatch:
    async def test_non_canonical_params_raise_mismatch_error(self, vault_path: Path) -> None:
        """Phase 01 hard-codes m=2^17, t=3, p=1. A vault file with different
        params MUST be rejected — the Foundation publishes parameter
        migrations explicitly per specs/trust-vault.md § Error taxonomy."""
        import struct

        from envoy.trust.vault import _HEADER_FMT, _HEADER_LEN

        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)
        data = bytearray(vault_path.read_bytes())
        # Re-pack the header with different Argon2id params
        magic, version, payload_len, salt, m, t, p, nonce = struct.unpack(
            _HEADER_FMT, bytes(data[:_HEADER_LEN])
        )
        # Drop memory cost to a non-canonical value
        new_header = struct.pack(
            _HEADER_FMT,
            magic,
            version,
            payload_len,
            salt,
            1 << 16,  # 2^16, not 2^17
            t,
            p,
            nonce,
        )
        data[:_HEADER_LEN] = new_header
        vault_path.write_bytes(bytes(data))
        v2 = TrustVault(vault_path, idle_ttl_seconds=10)
        with pytest.raises(Argon2ParameterMismatchError):
            await v2.unlock(PASSPHRASE)


# ---------------------------------------------------------------------------
# Metadata slot (T-02-35) — read_metadata / write_metadata round-trip
# ---------------------------------------------------------------------------


class TestMetadataSlot:
    """T-02-35 added a JSON-envelope metadata slot inside the vault payload.
    Used by `TrustVaultChecklistPersister` to persist DistributionChecklists
    keyed by ritual_id. Phase 01 contract: arbitrary JSON-serializable
    metadata round-trips across vault lock/unlock cycles.
    """

    async def test_read_metadata_on_fresh_vault_returns_empty_dict(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(b"", PASSPHRASE)
        await v.unlock(PASSPHRASE)
        assert (await v.read_metadata()) == {}
        await v.lock()

    async def test_read_metadata_legacy_payload_returns_empty_dict(self, vault_path: Path) -> None:
        """A vault created before the metadata API landed has an opaque-
        bytes payload. `read_metadata` MUST gracefully return an empty
        dict rather than raising on JSON-decode failure.
        """
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(PAYLOAD, PASSPHRASE)  # raw bytes, not JSON
        await v.unlock(PASSPHRASE)
        assert (await v.read_metadata()) == {}
        await v.lock()

    async def test_write_then_read_metadata_round_trip(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(b"", PASSPHRASE)
        await v.unlock(PASSPHRASE)
        metadata = {
            "shamir_distribution_checklists": {
                "ritual-a": {"slot_labels": ["slot-1", "slot-2", "slot-3"]},
            },
            "other_phase02_slot": {"key": "value"},
        }
        await v.write_metadata(metadata)
        loaded = await v.read_metadata()
        assert loaded == metadata
        await v.lock()

    async def test_metadata_persists_across_lock_unlock(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(b"", PASSPHRASE)
        await v.unlock(PASSPHRASE)
        await v.write_metadata({"foo": "bar", "nested": [1, 2, 3]})
        await v.lock()
        # Fresh adapter — proves the persistence is on disk, not in
        # the in-memory payload of the original instance.
        v2 = TrustVault(vault_path, idle_ttl_seconds=10)
        await v2.unlock(PASSPHRASE)
        assert (await v2.read_metadata()) == {"foo": "bar", "nested": [1, 2, 3]}
        await v2.lock()

    async def test_write_metadata_rejects_non_dict(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(b"", PASSPHRASE)
        await v.unlock(PASSPHRASE)
        with pytest.raises(TypeError, match="metadata"):
            await v.write_metadata("not-a-dict")  # type: ignore[arg-type]
        await v.lock()

    async def test_write_metadata_requires_unlocked(self, vault_path: Path) -> None:
        v = TrustVault(vault_path, idle_ttl_seconds=10)
        await v.create(b"", PASSPHRASE)
        with pytest.raises(VaultLockedError):
            await v.write_metadata({"foo": "bar"})
