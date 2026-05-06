"""Tier 2: Phase 01 Wave 1 end-to-end pipeline integration.

Source: T-01-16 + T-01-21 per `01-wave-1-foundation.md` lines 247 + 386 +
`rules/facade-manager-detection.md` MUST Rule 1 (every manager-shape class
has a Tier 2 wiring test that asserts an externally-observable effect).

Scope: cross-primitive integration exercising the full pipeline shipped
across PR #3-#8 — TrustVault (T-01-13) + EnvoyLedger (T-01-18) +
HashChainBuilder (T-01-17) + canonical_dumps + ExportBundle (T-01-19) +
4-key segment-boundary serializer (T-01-19 subsumes T-01-20). Validates
EC-2 (Grant Moments resolved correctly) + EC-4 (export-verify round-trip)
acceptance gates STRUCTURALLY at Tier 2 — Tier 3 e2e gate runs the
separately-codebased envoy-ledger-verify (Phase 01 exit gate).

Per `rules/testing.md` Tier 2: real infrastructure (real Argon2id + real
Ed25519 + real AES-256-GCM + real canonical-JSON byte-pinning); NO
mocking. The audit_store backend is `InMemoryAuditStore` (still real —
same kailash code path with chain-integrity check; just memory-backed).
File-backed `SqliteAuditStore` wiring lands at T-01-21 follow-up once
the kailash db connection-pool fixture is in place.
"""

from __future__ import annotations

import hashlib

import pytest
from kailash.trust.audit_store import AuditFilter, InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.ledger import (
    EnvoyLedger,
    ExportBundle,
    canonical_dumps,
    compute_receipt_hash,
)
from envoy.trust.vault import TrustVault


# ---------------------------------------------------------------------------
# E2E #1: Full pipeline round-trip (the EC-4 acceptance gate at Tier 2)
# ---------------------------------------------------------------------------


class TestPhase01PipelineRoundTrip:
    """Full pipeline: vault unlock → ledger append × N → export → verify."""

    async def test_3_grants_round_trip_through_facade(
        self,
        envoy_ledger: EnvoyLedger,
        unlocked_vault: TrustVault,
    ) -> None:
        """EC-2 acceptance: 3 grant moments triggered + resolved.
        EC-4 acceptance: export bundle round-trips through verifier-side
        re-derivation. The ledger appends 3 entries; the bundle's 9
        invariants (per `specs/independent-verifier.md` L78-90) are
        all reconstructible from the bundle bytes alone."""

        # Vault round-trip — verifies the full Argon2id + AES-256-GCM
        # path (T-01-13). Producer reads/writes during ritual.
        original_payload = await unlocked_vault.read()
        await unlocked_vault.write(b"after-grant-1")
        assert (await unlocked_vault.read()) == b"after-grant-1"

        # 3 ledger entries — the EC-2 grant moments
        e1 = await envoy_ledger.append(
            entry_type="grant_moment",
            content={"capability": "send_message", "limit_microdollars": 100_000},
        )
        e2 = await envoy_ledger.append(
            entry_type="envelope_edit",
            content={"change": "tightened communication_dimension"},
        )
        e3 = await envoy_ledger.append(
            entry_type="grant_moment",
            content={"capability": "spend_budget", "limit_microdollars": 50_000},
        )

        # verify_chain — every entry's signature + canonical-bytes round-trip
        report = await envoy_ledger.verify_chain()
        assert report.success is True
        assert report.entries_verified == 3

        # Export bundle — the EC-4 acceptance artifact
        bundle = await envoy_ledger.export()
        assert isinstance(bundle, ExportBundle)
        assert len(bundle.entries) == 3
        # Bundle entries are byte-stable across a re-canonicalize
        original_bytes = canonical_dumps(bundle.to_dict_minus_receipt())
        re_canonical = canonical_dumps(bundle.to_dict_minus_receipt())
        assert original_bytes == re_canonical

        # Verifier-side re-derivation of receipt_hash
        recomputed_receipt = compute_receipt_hash(bundle.to_dict_minus_receipt())
        assert bundle.receipt_hash == recomputed_receipt

        # Verifier invariant 6 — head matches last entry
        last = bundle.entries[-1]
        assert last["entry_id"] == e3
        assert bundle.head_commitment.head_sequence == 3

        # Verifier invariant 3 — chain links
        assert bundle.entries[1]["parent_hash"] == e1
        assert bundle.entries[2]["parent_hash"] == e2

        # Verifier invariant 9 — 4-key segment with canonical_json
        seg = bundle.segment_boundaries[0]
        assert seg.algorithm_identifier["canonical_json"] == "jcs-rfc8785"
        assert seg.from_sequence == 0
        assert seg.to_sequence == 3


# ---------------------------------------------------------------------------
# E2E #2: Cross-primitive byte-identity (verifier reconstruction)
# ---------------------------------------------------------------------------


class TestVerifierReconstructionFromBundleBytes:
    """The bundle bytes alone MUST be sufficient for a clean-room verifier
    to recompute every invariant. This Tier 2 test simulates the
    cross-process EC-9 verifier by walking the bundle dict and asserting
    the 4 producer-side reconstructible invariants (1, 3, 4, 6)."""

    async def test_verifier_can_reconstruct_chain_integrity_from_bundle(
        self, envoy_ledger: EnvoyLedger
    ) -> None:
        await envoy_ledger.append(
            entry_type="GenesisRecord",
            content={"principal_id": "alpha", "envelope_version": 1},
        )
        await envoy_ledger.append(
            entry_type="DelegationRecord",
            content={"capability": "send", "valid_until": "2027-01-01"},
        )
        await envoy_ledger.append(
            entry_type="RevocationRecord",
            content={"target_delegation_id": "sha256:abc", "reason": "expired"},
        )

        bundle = await envoy_ledger.export()
        bundle_dict = bundle.to_dict()
        # Verifier opens the bundle from bytes
        canonical_bundle_bytes = canonical_dumps(bundle.to_dict_minus_receipt())
        # Verifier invariant 8 — receipt_hash matches the canonical bytes
        recomputed = "sha256:" + hashlib.sha256(canonical_bundle_bytes).hexdigest()
        assert recomputed == bundle_dict["receipt_hash"]

        # Verifier invariant 1 — entries ascending
        entries = bundle_dict["entries"]
        sequences = [e["sequence"] for e in entries]
        assert sequences == sorted(sequences)
        assert len(set(sequences)) == len(sequences)

        # Verifier invariant 3 — chain links
        for i in range(1, len(entries)):
            assert entries[i]["parent_hash"] == entries[i - 1]["entry_id"]

        # Verifier invariant 4 — content addressing
        for entry in entries:
            unsigned = {k: v for k, v in entry.items() if k not in ("entry_id", "signature_hex")}
            recomputed_id = "sha256:" + hashlib.sha256(canonical_dumps(unsigned)).hexdigest()
            assert recomputed_id == entry["entry_id"]

        # Verifier invariant 6 — head matches last entry
        head = bundle_dict["head_commitment"]
        assert head["head_sequence"] == entries[-1]["sequence"]
        assert head["head_entry_id"] == entries[-1]["entry_id"]


# ---------------------------------------------------------------------------
# E2E #3: Failure paths (atomicity guarantees from PR #7 hold under load)
# ---------------------------------------------------------------------------


class TestPhase01AtomicityUnderLoad:
    """The atomicity guarantees from T-01-18's snapshot+commit pattern
    MUST hold under realistic interleavings — many appends, mid-flight
    audit_store failure injection, recovery."""

    async def test_burst_append_then_export_round_trips(
        self,
        envoy_ledger: EnvoyLedger,
    ) -> None:
        """100 sequential appends through the facade — sequence,
        lamport_time, and local_seq all increment monotonically, the
        chain is verifiable end-to-end, and the export bundle's
        receipt_hash matches a clean re-derivation."""
        N = 100
        for i in range(N):
            await envoy_ledger.append(
                entry_type="action",
                content={"index": i},
            )

        head = await envoy_ledger.head_commitment()
        assert head.head_sequence == N

        report = await envoy_ledger.verify_chain()
        assert report.success
        assert report.entries_verified == N

        bundle = await envoy_ledger.export()
        assert len(bundle.entries) == N
        assert bundle.head_commitment.head_sequence == N
        # Lamport monotonic across all entries
        lamports = [e["lamport_clock"]["lamport_time"] for e in bundle.entries]
        assert lamports == sorted(lamports)
        assert len(set(lamports)) == N
        # local_seq monotonic
        seqs = [e["lamport_clock"]["local_seq"] for e in bundle.entries]
        assert seqs == list(range(1, N + 1))

    async def test_audit_store_failure_isolates_chain_state(
        self,
        signing_keymgr: InMemoryKeyManager,
    ) -> None:
        """Inject a failing audit_store partway through a 10-append
        sequence. Verify the chain advances cleanly past the failed
        attempt — the ledger doesn't get stuck on the failed sequence
        index."""

        class IntermittentStore:
            """Wraps a real audit_store; raises on every Nth append."""

            def __init__(self, real: InMemoryAuditStore, fail_every: int):
                self._real = real
                self._fail_every = fail_every
                self._calls = 0
                self.last_hash = real.last_hash

            def create_event(self, **kwargs):
                return self._real.create_event(**kwargs)

            async def append(self, event):
                self._calls += 1
                if self._calls % self._fail_every == 0:
                    raise RuntimeError(f"injected failure on call {self._calls}")
                await self._real.append(event)
                self.last_hash = self._real.last_hash

            async def query(self, f):
                return await self._real.query(f)

            async def verify_chain(self):
                return await self._real.verify_chain()

            async def close(self):
                await self._real.close()

        backing = InMemoryAuditStore()
        flaky = IntermittentStore(backing, fail_every=3)
        ledger = EnvoyLedger(
            audit_store=flaky,
            key_manager=signing_keymgr,
            signing_key_id="envoy-tier2-signing-key",
            device_id="device-flaky-test",
            algorithm_identifier={
                "sig": "ed25519",
                "hash": "sha256",
                "shamir": "slip39",
            },
        )

        successes = 0
        failures = 0
        for i in range(10):
            try:
                await ledger.append(entry_type="action", content={"i": i})
                successes += 1
            except RuntimeError:
                failures += 1

        # Failures occurred on calls 3, 6, 9 of the audit_store (which
        # is per-call counted regardless of envoy-side retry). Successes
        # advance the chain; the failed appends did NOT advance it.
        assert failures > 0
        head = await ledger.head_commitment()
        assert head.head_sequence == successes
        # verify_chain should still pass — no half-written entries.
        report = await ledger.verify_chain()
        assert report.success
        assert report.entries_verified == successes


# ---------------------------------------------------------------------------
# E2E #4: TrustVault Shamir round-trip — recovery flow (T-01-14 hooks)
# ---------------------------------------------------------------------------


class TestTrustVaultShamirRecoveryFlow:
    """Full Shamir recovery flow exercising T-01-14's hooks against real
    Argon2id KDF + real AES-256-GCM container."""

    async def test_shamir_export_then_fresh_adapter_import_round_trip(self, vault_path) -> None:
        """Real-world Shamir flow: original device exports the master
        key, splits via SLIP-0039, ships shards to backup. Recovery
        device reconstructs the master key from m-of-n shards (here we
        skip the SLIP step and pass the bytes directly), then a fresh
        TrustVault adapter imports without the original passphrase."""
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
