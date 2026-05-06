"""Tier 1: T-01-19 — EnvoyLedger.export() bundle + 9 verifier invariants.

Source: T-01-19 per `01-wave-1-foundation.md` line 405 + spec authority
`specs/independent-verifier.md` § Bundle wire format (lines 21-90) +
`specs/ledger.md` § Export bundle (line 590).

Capacity (3 invariants per todo):
1. 4-key segment-boundary algorithm_identifier per spec L35 R3-M-02
2. Receipt hash determinism (sha256 over canonical_dumps minus receipt)
3. Invariants 1-9 verifier contract per spec L78-90 (producer-side
   shape; verifier-side check lives in T-01-21+)

Per `rules/testing.md` Tier 1: real `InMemoryAuditStore` + real
`InMemoryKeyManager`. Tier 2 wiring (T-01-21) repeats against
`SqliteAuditStore` + real Ed25519 timing.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from kailash.trust.audit_store import InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.ledger import (
    EnvoyLedger,
    ExportBundle,
    LedgerError,
    SegmentBoundary,
    TrustAnchorKey,
    canonical_dumps,
    compute_receipt_hash,
)


VALID_ALGO_ID = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}
DEVICE_ID = "device-test-export"
SIGNING_KEY_ID = "envoy-export-key"


@pytest.fixture
async def keymgr() -> InMemoryKeyManager:
    mgr = InMemoryKeyManager()
    await mgr.generate_keypair(SIGNING_KEY_ID)
    return mgr


@pytest.fixture
async def populated_ledger(
    keymgr: InMemoryKeyManager,
) -> EnvoyLedger:
    audit = InMemoryAuditStore()
    ledger = EnvoyLedger(
        audit_store=audit,
        key_manager=keymgr,
        signing_key_id=SIGNING_KEY_ID,
        device_id=DEVICE_ID,
        algorithm_identifier=VALID_ALGO_ID,
    )
    await ledger.append(entry_type="RoleEnvelopeCreated", content={"v": 1})
    await ledger.append(entry_type="envelope_edit", content={"change": "tighten"})
    await ledger.append(entry_type="grant_moment", content={"capability": "send"})
    return ledger


# ---------------------------------------------------------------------------
# SegmentBoundary — 4-key form per spec L35 R3-M-02
# ---------------------------------------------------------------------------


class TestSegmentBoundary:
    def test_3_key_form_rejected(self) -> None:
        """3-key trust-lineage form is INSUFFICIENT at segment boundaries —
        the spec mandates the 4-key strict superset with `canonical_json`."""
        with pytest.raises(ValueError, match="4-key"):
            SegmentBoundary(
                from_sequence=0,
                to_sequence=10,
                algorithm_identifier=VALID_ALGO_ID,  # 3-key — INSUFFICIENT
            )

    def test_4_key_form_accepted(self) -> None:
        sb = SegmentBoundary(
            from_sequence=0,
            to_sequence=10,
            algorithm_identifier={
                "sig": "ed25519",
                "hash": "sha256",
                "shamir": "slip39",
                "canonical_json": "jcs-rfc8785",
            },
        )
        assert sb.from_sequence == 0
        assert sb.to_sequence == 10

    def test_wrong_canonical_json_value_rejected(self) -> None:
        with pytest.raises(ValueError, match="canonical_json"):
            SegmentBoundary(
                from_sequence=0,
                to_sequence=10,
                algorithm_identifier={
                    "sig": "ed25519",
                    "hash": "sha256",
                    "shamir": "slip39",
                    "canonical_json": "rfc7159",  # WRONG profile
                },
            )

    def test_from_trust_lineage_3_key_promotes(self) -> None:
        """Producer-side helper: promotes 3-key trust-lineage form to
        4-key segment-boundary form by appending canonical_json."""
        sb = SegmentBoundary.from_trust_lineage_3_key(
            from_sequence=0, to_sequence=10, trust_lineage_form=VALID_ALGO_ID
        )
        assert sb.algorithm_identifier == {
            **VALID_ALGO_ID,
            "canonical_json": "jcs-rfc8785",
        }

    def test_from_trust_lineage_rejects_4_key_input(self) -> None:
        """Producer error: caller passed already-4-key form to the
        promoter — refuse loudly."""
        with pytest.raises(ValueError, match="3-key"):
            SegmentBoundary.from_trust_lineage_3_key(
                from_sequence=0,
                to_sequence=10,
                trust_lineage_form={**VALID_ALGO_ID, "canonical_json": "jcs-rfc8785"},
            )

    def test_negative_from_sequence_rejected(self) -> None:
        with pytest.raises(ValueError, match="from_sequence"):
            SegmentBoundary.from_trust_lineage_3_key(
                from_sequence=-1, to_sequence=0, trust_lineage_form=VALID_ALGO_ID
            )

    def test_to_sequence_less_than_from_rejected(self) -> None:
        with pytest.raises(ValueError, match="to_sequence"):
            SegmentBoundary.from_trust_lineage_3_key(
                from_sequence=10, to_sequence=5, trust_lineage_form=VALID_ALGO_ID
            )


# ---------------------------------------------------------------------------
# TrustAnchorKey — Phase 01 minimal trust anchor
# ---------------------------------------------------------------------------


class TestTrustAnchorKey:
    def test_valid_runtime_device_key(self) -> None:
        k = TrustAnchorKey(
            key_id="sha256:" + "a" * 64,
            public_key_hex="b" * 64,
            key_class="runtime_device",
            valid_from="2026-05-06T14:23:45.000000Z",
            valid_until=None,
        )
        d = k.to_dict()
        assert d["key_class"] == "runtime_device"
        assert d["attestation_chain"] == []  # Phase 01 empty

    def test_invalid_key_class_rejected(self) -> None:
        with pytest.raises(ValueError, match="key_class"):
            TrustAnchorKey(
                key_id="sha256:" + "a" * 64,
                public_key_hex="b" * 64,
                key_class="oracle",  # not a real class
                valid_from="2026-05-06T14:23:45.000000Z",
                valid_until=None,
            )

    def test_key_id_must_have_sha256_prefix(self) -> None:
        with pytest.raises(ValueError, match="key_id"):
            TrustAnchorKey(
                key_id="a" * 64,
                public_key_hex="b" * 64,
                key_class="runtime_device",
                valid_from="2026-05-06T14:23:45.000000Z",
                valid_until=None,
            )


# ---------------------------------------------------------------------------
# EnvoyLedger.export() round-trip + 9 verifier invariants
# ---------------------------------------------------------------------------


class TestExportRoundTrip:
    async def test_export_returns_bundle_dataclass(self, populated_ledger: EnvoyLedger) -> None:
        bundle = await populated_ledger.export()
        assert isinstance(bundle, ExportBundle)
        assert bundle.schema_version == "envoy-ledger-export/1.0"

    async def test_export_empty_ledger_raises(self, keymgr: InMemoryKeyManager) -> None:
        """Verifier invariant 1 mandates non-empty entries[]; empty ledger
        cannot produce a valid bundle."""
        audit = InMemoryAuditStore()
        ledger = EnvoyLedger(
            audit_store=audit,
            key_manager=keymgr,
            signing_key_id=SIGNING_KEY_ID,
            device_id=DEVICE_ID,
            algorithm_identifier=VALID_ALGO_ID,
        )
        with pytest.raises(LedgerError, match="empty ledger"):
            await ledger.export()


class TestVerifierInvariant1AscendingSequence:
    async def test_entries_ascending_by_sequence(self, populated_ledger: EnvoyLedger) -> None:
        bundle = await populated_ledger.export()
        sequences = [e["sequence"] for e in bundle.entries]
        assert sequences == sorted(sequences)
        assert len(set(sequences)) == len(sequences)  # all distinct


class TestVerifierInvariant3ChainLink:
    async def test_each_entry_parent_hash_links_to_prev_entry_id(
        self, populated_ledger: EnvoyLedger
    ) -> None:
        bundle = await populated_ledger.export()
        for i in range(1, len(bundle.entries)):
            assert bundle.entries[i]["parent_hash"] == bundle.entries[i - 1]["entry_id"]


class TestVerifierInvariant4ContentAddressing:
    async def test_each_entry_id_is_sha256_of_canonical_minus_id_and_sig(
        self, populated_ledger: EnvoyLedger
    ) -> None:
        """Verifier invariant 4: entry_id == sha256(canonical_dumps(envelope
        minus entry_id + signature_hex))."""
        bundle = await populated_ledger.export()
        for envelope in bundle.entries:
            unsigned = {k: v for k, v in envelope.items() if k not in ("entry_id", "signature_hex")}
            recomputed = "sha256:" + hashlib.sha256(canonical_dumps(unsigned)).hexdigest()
            assert recomputed == envelope["entry_id"]


class TestVerifierInvariant6HeadEqualsLastEntry:
    async def test_head_sequence_and_entry_id_match_last_entry(
        self, populated_ledger: EnvoyLedger
    ) -> None:
        """Verifier invariant 6."""
        bundle = await populated_ledger.export()
        last = bundle.entries[-1]
        assert bundle.head_commitment.head_sequence == last["sequence"]
        assert bundle.head_commitment.head_entry_id == last["entry_id"]


class TestVerifierInvariant8ReceiptHash:
    async def test_receipt_hash_matches_canonical_minus_receipt(
        self, populated_ledger: EnvoyLedger
    ) -> None:
        """Verifier invariant 8: receipt_hash == sha256(canonical_dumps(bundle minus receipt))."""
        bundle = await populated_ledger.export()
        recomputed = compute_receipt_hash(bundle.to_dict_minus_receipt())
        assert bundle.receipt_hash == recomputed

    async def test_receipt_hash_determinism(self, populated_ledger: EnvoyLedger) -> None:
        """Same bundle content → same receipt_hash. The bundle has an
        `exported_at` timestamp so two consecutive `export()` calls do
        differ; but a single bundle's receipt_hash is stable across
        repeat compute_receipt_hash invocations."""
        bundle = await populated_ledger.export()
        snapshot = bundle.to_dict_minus_receipt()
        assert compute_receipt_hash(snapshot) == compute_receipt_hash(snapshot)

    async def test_receipt_hash_detects_bundle_tamper(self, populated_ledger: EnvoyLedger) -> None:
        """A tamper anywhere in the bundle propagates into receipt_hash."""
        bundle = await populated_ledger.export()
        # Mutate the canonical bundle dict and recompute.
        d = bundle.to_dict_minus_receipt()
        d["entries"][0]["content"] = {"tampered": "yes"}
        new_hash = compute_receipt_hash(d)
        assert new_hash != bundle.receipt_hash


class TestVerifierInvariant9SegmentBoundaryDispatch:
    async def test_single_segment_covers_all_entries(self, populated_ledger: EnvoyLedger) -> None:
        """Phase 01 narrow scope: single segment from 0 to head_sequence."""
        bundle = await populated_ledger.export()
        assert len(bundle.segment_boundaries) == 1
        seg = bundle.segment_boundaries[0]
        assert seg.from_sequence == 0
        assert seg.to_sequence == bundle.head_commitment.head_sequence
        # Every entry's sequence falls within the segment window.
        for envelope in bundle.entries:
            assert seg.from_sequence <= envelope["sequence"] <= seg.to_sequence

    async def test_segment_uses_4_key_form(self, populated_ledger: EnvoyLedger) -> None:
        """Producer-side: the segment boundary's algorithm_identifier
        MUST be 4-key (not the trust-lineage 3-key form)."""
        bundle = await populated_ledger.export()
        seg = bundle.segment_boundaries[0]
        assert set(seg.algorithm_identifier.keys()) == {
            "sig",
            "hash",
            "shamir",
            "canonical_json",
        }
        assert seg.algorithm_identifier["canonical_json"] == "jcs-rfc8785"


class TestBundleSchemaShape:
    """The bundle dict produced for the verifier matches spec L25-75."""

    async def test_to_dict_includes_receipt_hash(self, populated_ledger: EnvoyLedger) -> None:
        bundle = await populated_ledger.export()
        d = bundle.to_dict()
        assert "receipt_hash" in d
        assert d["receipt_hash"] == bundle.receipt_hash

    async def test_to_dict_minus_receipt_excludes_receipt_hash(
        self, populated_ledger: EnvoyLedger
    ) -> None:
        bundle = await populated_ledger.export()
        d = bundle.to_dict_minus_receipt()
        assert "receipt_hash" not in d

    async def test_top_level_fields_match_spec(self, populated_ledger: EnvoyLedger) -> None:
        """Spec L25-75 enumerates 9 top-level fields including receipt_hash."""
        bundle = await populated_ledger.export()
        d = bundle.to_dict()
        expected = {
            "schema_version",
            "exported_at",
            "device_id",
            "tenant_id",
            "segment_boundaries",
            "entries",
            "head_commitment",
            "trust_anchor_key_set",
            "receipt_hash",
        }
        assert set(d.keys()) == expected

    async def test_head_commitment_carries_runtime_attestation_field(
        self, populated_ledger: EnvoyLedger
    ) -> None:
        """Per spec L57-63, head_commitment carries a `runtime_attestation`
        field (Phase 01 empty dict; Phase 02 wires real attestation)."""
        bundle = await populated_ledger.export()
        d = bundle.to_dict()
        assert "runtime_attestation" in d["head_commitment"]
        assert d["head_commitment"]["runtime_attestation"] == {}

    async def test_trust_anchor_key_set_includes_signing_key(
        self, populated_ledger: EnvoyLedger
    ) -> None:
        bundle = await populated_ledger.export()
        assert len(bundle.trust_anchor_key_set) == 1
        anchor = bundle.trust_anchor_key_set[0]
        assert anchor.key_class == "runtime_device"

    async def test_canonical_dumps_round_trip_is_byte_stable(
        self, populated_ledger: EnvoyLedger
    ) -> None:
        """The bundle's canonical bytes are stable across two
        canonical_dumps invocations on the same bundle dict — this is the
        cross-SDK byte-identity contract per BET-6."""
        bundle = await populated_ledger.export()
        d = bundle.to_dict_minus_receipt()
        b1 = canonical_dumps(d)
        b2 = canonical_dumps(d)
        assert b1 == b2
