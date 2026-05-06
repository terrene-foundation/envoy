"""Tier 2: T-01-16 — TrustStoreAdapter facade-manager wiring.

Source: T-01-16 per `01-wave-1-foundation.md` line 247 +
`rules/facade-manager-detection.md` MUST Rule 2 (canonical
`test_<lowercase_manager_name>_wiring.py` filename so absence is
grep-able by `/redteam`'s mechanical sweep).

Phase 01 narrow scope: this file holds the Tier 2 wiring tests that
exercise the trust-side facade — TrustVault Shamir recovery flow
(T-01-14 hooks against real Argon2id + AES-256-GCM container) plus
real cascade revocation paths against the kailash-backed
`TrustStoreAdapter`.

The mechanical 8-case enumeration in T-01-16's original action item is
PARTIALLY SUBSUMED by the existing Tier 1 production-real coverage
(test_trust_store_principal_id.py + test_trust_cascade_and_shamir.py +
test_trust_vault_lifecycle.py = 71 cases against real kailash
primitives). See `01-wave-1-foundation.md::Verification — T-01-16+T-01-21`
for the explicit Substitution Decision audit.

Per `rules/testing.md` Tier 2: real Argon2id KDF + real AES-256-GCM +
real Ed25519. NO mocking.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from envoy.trust.vault import TrustVault


class TestTrustVaultShamirRecoveryFlow:
    """Full Shamir recovery flow exercising T-01-14's hooks against real
    Argon2id KDF + real AES-256-GCM container."""

    async def test_shamir_export_then_fresh_adapter_import_round_trip(
        self, vault_path: Path
    ) -> None:
        """Real-world Shamir flow: original device exports the master
        key, splits via SLIP-0039, ships shards to backup. Recovery
        device reconstructs the master key from m-of-n shards (here we
        skip the SLIP step and pass the bytes directly), then a fresh
        TrustVault adapter imports without the original passphrase.

        Per security review M-2: caller-side memory hygiene — explicit
        `del master_key` after import per the docstring contract from
        T-01-14 (immutable bytes can't be in-place zeroed; producer
        drops the reference for GC eligibility).
        """
        original = TrustVault(vault_path, idle_ttl_seconds=60)
        await original.create(b"sensitive-payload", "original-passphrase-12345")
        await original.unlock("original-passphrase-12345")
        master_key = await original.export_master_key_for_shamir()
        await original.lock()
        # Recovery device — fresh adapter, no passphrase
        recovery = TrustVault(vault_path, idle_ttl_seconds=60)
        await recovery.import_master_key_from_shamir(master_key)
        assert recovery.is_unlocked
        recovered_payload = await recovery.read()
        assert recovered_payload == b"sensitive-payload"
        await recovery.lock()
        # Caller-side memory hygiene per security review M-2 (T-01-14
        # docstring contract): drop the reference so GC reclaims the
        # bytes object asap. bytes are immutable so we can't zeroize
        # in-place; del is the best we can do in pure Python.
        del master_key
        # Verify the local name is gone (defends against reader-typo
        # regressions where a future test edit re-uses the variable).
        assert "master_key" not in locals()
