"""Export bundle — `envoy ledger export --format json` artifact.

Per `specs/independent-verifier.md` § Bundle wire format (lines 21-90) +
`specs/ledger.md` § Export bundle (line 590) + shard 6 § 4 step 6.

The export bundle is the artifact the separately-codebased Independent
Verifier (`envoy-ledger-verify`, Phase 01 exit gate per doc 00 v3) consumes
to certify chain integrity from a clean-room reimplementation. The
Phase 01 EC-4 acceptance gate is the bundle round-trip.

Phase 01 narrow scope (T-01-19):

- Single segment per export (no MigrationAnnouncement boundaries yet).
- 4-key segment_boundary algorithm_identifier per
  `specs/independent-verifier.md` L35 R3-M-02 carry-forward
  (`{sig, hash, shamir, canonical_json}` — strict superset of the
  trust-lineage 3-key form; the `canonical_json: jcs-rfc8785` key
  documents the canonicalization profile).
- Minimal trust anchor key set: just the signing key for Phase 01
  single-device. Phase 02 adds device_attestation_chain.
- JSON-only export (PDF receipt_hash form lands at Wave 5 CLI).

Phase 02+ extends:

- Multiple segment boundaries when MigrationAnnouncement records appear
  (each segment's algorithm_identifier may differ).
- Full device_attestation_chain in trust_anchor_key_set per
  `specs/independent-verifier.md` L99-107.
- PDF form with `receipt_hash` pointing to the JSON form per
  `specs/ledger.md` line 591.
- Partial exports with `start_after_sequence` declaration.

Receipt hash contract per spec L74 + L87:

    receipt_hash = "sha256:" + sha256(canonical_dumps(bundle minus receipt_hash))

The receipt_hash is the bundle's self-integrity check. A verifier that
computes the same hash on the received bundle MUST get the same value;
any tamper anywhere in the bundle propagates into receipt_hash mismatch.

The 9 bundle invariants (verifier MUST detect violations of any) per
`specs/independent-verifier.md` L78-90:

1. `entries[]` non-empty AND ordered ascending by `sequence`.
2. `entries[0].type == "GenesisRecord"` for full export OR `sequence > 0`
   with explicit `start_after_sequence` for partial. (Phase 01 single-
   segment narrow scope: full exports only.)
3. For `i > 0`: `entries[i].parent_hash == entries[i-1].entry_id`.
4. For each entry: recomputed entry_id == stored entry_id.
5. For each entry: signature verifies against the matching trust-anchor key.
6. `head_commitment.head_sequence == entries[-1].sequence` AND
   `head_commitment.head_entry_id == entries[-1].entry_id`.
7. head_commitment signature verifies against runtime_device_key.
8. receipt_hash == sha256(canonical_dumps(bundle minus receipt_hash)).
9. Segment-boundary dispatch: each entry's algorithm_identifier matches
   its containing segment.

Phase 01 producer-side: T-01-19 lands the bundle CONSTRUCTION + receipt
hashing. The verifier-side check of invariants 1-9 lives in the
separately-codebased `envoy-ledger-verify` package (T-01-21 Tier 2 wires
the round-trip; T-01-21+ ships the verifier itself).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from envoy.ledger.canonical import canonical_dumps
from envoy.ledger.head import HeadCommitment

# Phase 01 segment-boundary 4-key algorithm_identifier per
# specs/independent-verifier.md L35 R3-M-02 carry-forward. Strict superset
# of the trust-lineage 3-key form `{sig, hash, shamir}`; adds
# `canonical_json: jcs-rfc8785` documenting the canonicalization profile.
_SEGMENT_BOUNDARY_CANONICAL_JSON = "jcs-rfc8785"
_BUNDLE_SCHEMA_VERSION = "envoy-ledger-export/1.0"


@dataclass(frozen=True, slots=True)
class TrustAnchorKey:
    """A single key entry inside `trust_anchor_key_set` per spec L64-72.

    Phase 01 narrow scope: `attestation_chain` is empty (Phase 02 wires
    the full device_attestation_chain per spec L92-110).
    """

    key_id: str
    public_key_hex: str
    key_class: str
    valid_from: str
    valid_until: str | None

    _VALID_KEY_CLASSES = frozenset({"genesis", "device", "runtime_device"})

    def __post_init__(self) -> None:
        if self.key_class not in self._VALID_KEY_CLASSES:
            raise ValueError(
                f"key_class must be one of {sorted(self._VALID_KEY_CLASSES)} "
                f"(got {self.key_class!r})"
            )
        if not self.key_id.startswith("sha256:"):
            raise ValueError(f"key_id must be 'sha256:<hex>' (got {self.key_id!r})")
        if not self.public_key_hex:
            raise ValueError("public_key_hex must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "public_key_hex": self.public_key_hex,
            "key_class": self.key_class,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "attestation_chain": [],  # Phase 02 populates
        }


@dataclass(frozen=True, slots=True)
class SegmentBoundary:
    """Segment-boundary algorithm_identifier per spec L31-52 R3-M-02.

    Phase 01 narrow scope: every export has exactly ONE segment covering
    `[0, head_sequence]` (no MigrationAnnouncement records to split on).
    The 4-key form (`{sig, hash, shamir, canonical_json}`) is mandatory
    on the wire — the trust-lineage 3-key form is INSUFFICIENT here.
    """

    from_sequence: int
    to_sequence: int
    algorithm_identifier: dict[str, str]

    def __post_init__(self) -> None:
        if self.from_sequence < 0:
            raise ValueError(f"from_sequence must be >= 0 (got {self.from_sequence})")
        if self.to_sequence < self.from_sequence:
            raise ValueError(f"to_sequence {self.to_sequence} < from_sequence {self.from_sequence}")
        # 4-key form per R3-M-02 — this is the segment-boundary contract,
        # NOT the 3-key trust-lineage form. The verifier rejects the 3-key
        # form at segment boundaries.
        expected = {"sig", "hash", "shamir", "canonical_json"}
        if set(self.algorithm_identifier.keys()) != expected:
            raise ValueError(
                f"segment-boundary algorithm_identifier MUST be the 4-key "
                f"{{sig, hash, shamir, canonical_json}} form per "
                f"specs/independent-verifier.md L35 (got "
                f"{sorted(self.algorithm_identifier.keys())})"
            )
        if self.algorithm_identifier["canonical_json"] != _SEGMENT_BOUNDARY_CANONICAL_JSON:
            raise ValueError(
                f"canonical_json key MUST be {_SEGMENT_BOUNDARY_CANONICAL_JSON!r} "
                f"(got {self.algorithm_identifier['canonical_json']!r})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_sequence": self.from_sequence,
            "to_sequence": self.to_sequence,
            "algorithm_identifier": dict(self.algorithm_identifier),
        }

    @classmethod
    def from_trust_lineage_3_key(
        cls,
        from_sequence: int,
        to_sequence: int,
        trust_lineage_form: dict[str, str],
    ) -> SegmentBoundary:
        """Promote the 3-key trust-lineage form to the 4-key segment-
        boundary form by adding the `canonical_json: jcs-rfc8785` key.
        Phase 01 producer-side helper for `EnvoyLedger.export()`."""
        if set(trust_lineage_form.keys()) != {"sig", "hash", "shamir"}:
            raise ValueError(
                f"trust_lineage_form MUST be 3-key {{sig, hash, shamir}} "
                f"(got {sorted(trust_lineage_form.keys())})"
            )
        return cls(
            from_sequence=from_sequence,
            to_sequence=to_sequence,
            algorithm_identifier={
                **trust_lineage_form,
                "canonical_json": _SEGMENT_BOUNDARY_CANONICAL_JSON,
            },
        )


@dataclass(frozen=True, slots=True)
class ExportBundle:
    """Full export bundle per spec L25-75.

    Frozen + slots so an export captured at time T cannot be mutated
    before signing / shipping.

    **Mutability narrow contract** (per security review M-1): the
    `entries` tuple is itself immutable, but each contained `dict[str, Any]`
    is mutable. Phase 01 narrow scope: callers MUST NOT retain references
    to `entries[i]` after `ExportBundle` construction; the producer
    constructs once and ships; `to_dict_minus_receipt()` does a defensive
    copy on read so verifier-side mutation cannot bleed back. Phase 02
    hardens via `MappingProxyType` deep-freeze.

    Phase 01 narrow scope: `runtime_attestation` is `{}` (Phase 02 wires
    real attestation per `specs/runtime-abstraction.md` § Runtime
    attestation). `entries` is a tuple of envelope dicts (already
    canonicalized via EntryEnvelope.to_dict()) so the bundle's canonical
    bytes are stable.

    `receipt_hash` is computed by the producer factory
    (`EnvoyLedger.export()`) FROM the `ExportBundle.to_dict_minus_receipt()`
    of an interim bundle (with placeholder receipt_hash), then a final
    `dataclasses.replace(...)` swaps the placeholder for the real value.
    This eliminates the parallel-dict byte-identity hazard per security
    review H-1 — the receipt hashes the dataclass's own canonical view.
    """

    schema_version: str
    exported_at: str
    device_id: str
    tenant_id: str | None
    segment_boundaries: tuple[SegmentBoundary, ...]
    entries: tuple[dict[str, Any], ...]
    head_commitment: HeadCommitment
    trust_anchor_key_set: tuple[TrustAnchorKey, ...]
    runtime_attestation: dict[str, Any]
    receipt_hash: str

    def __post_init__(self) -> None:
        # Schema + non-empty shape checks
        if self.schema_version != _BUNDLE_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version pinned to {_BUNDLE_SCHEMA_VERSION!r} "
                f"(got {self.schema_version!r})"
            )
        # device_id MUST match the spec L29 sha256:<hex> shape (gate review M-3 +
        # security review M-2). Producer at EnvoyLedger.export() hashes the
        # logical device_id to produce this value.
        if not self.device_id.startswith("sha256:"):
            raise ValueError(
                f"device_id MUST be 'sha256:<hex>' per specs/independent-verifier.md "
                f"L29 (got {self.device_id!r})"
            )
        # exported_at MUST match the canonical 27-char ISO 8601 UTC shape per
        # #731 byte pinning (gate review M-2).
        from envoy.ledger.canonical import is_canonical_timestamp

        if not is_canonical_timestamp(self.exported_at):
            raise ValueError(
                f"exported_at MUST match Phase 01 ISO 8601 microsecond shape "
                f"'YYYY-MM-DDTHH:MM:SS.NNNNNNZ' (got {self.exported_at!r})"
            )
        if not self.entries:
            raise ValueError("entries must be non-empty (full export)")
        if not self.segment_boundaries:
            raise ValueError("segment_boundaries must be non-empty")
        if not self.trust_anchor_key_set:
            raise ValueError("trust_anchor_key_set must be non-empty")
        if not self.receipt_hash.startswith("sha256:"):
            raise ValueError(f"receipt_hash must be 'sha256:<hex>' (got {self.receipt_hash!r})")
        # Verifier invariant 1 — entries ascending by sequence (gate review M-2)
        sequences = [e["sequence"] for e in self.entries]
        if sequences != sorted(sequences) or len(set(sequences)) != len(sequences):
            raise ValueError(
                "entries MUST be ordered ascending by sequence with all "
                f"sequences distinct (got {sequences})"
            )
        # Verifier invariant 2 — Phase 01 full-export narrow scope: first
        # entry's sequence MUST equal segment_boundaries[0].from_sequence + 1
        # (segment from_sequence is the BEFORE-Genesis sentinel; first appended
        # entry is sequence + 1). The Genesis-type assertion (entries[0].type
        # == "GenesisRecord") defers to Wave 3 when Boundary Conversation
        # produces real Genesis records — currently Phase 01 entries are
        # whatever-the-first-append-was. (Gate review H-1.)
        first_seg = self.segment_boundaries[0]
        if self.entries[0]["sequence"] != first_seg.from_sequence + 1:
            raise ValueError(
                f"first entry's sequence ({self.entries[0]['sequence']}) MUST "
                f"equal segment_boundaries[0].from_sequence + 1 "
                f"({first_seg.from_sequence + 1}) per verifier invariant 2"
            )
        # Verifier invariant 6 — head_commitment matches last entry (gate
        # review M-2 — covered by tests but added to __post_init__ as
        # belt-and-suspenders defense for direct-construction callers).
        last = self.entries[-1]
        if self.head_commitment.head_sequence != last["sequence"]:
            raise ValueError(
                f"head_commitment.head_sequence ({self.head_commitment.head_sequence}) "
                f"MUST equal entries[-1].sequence ({last['sequence']})"
            )
        if self.head_commitment.head_entry_id != last["entry_id"]:
            raise ValueError("head_commitment.head_entry_id MUST equal entries[-1].entry_id")
        # Verifier invariant 9 — segment window covers head_sequence
        if first_seg.to_sequence != self.head_commitment.head_sequence:
            raise ValueError(
                f"segment_boundaries[0].to_sequence ({first_seg.to_sequence}) "
                f"MUST equal head_commitment.head_sequence "
                f"({self.head_commitment.head_sequence}) for Phase 01 single-segment"
            )

    def to_dict_minus_receipt(self) -> dict[str, Any]:
        """Canonical dict EXCLUDING receipt_hash. Used for receipt_hash
        derivation (chicken-and-egg avoidance) AND for re-verification at
        the verifier side."""
        return {
            "schema_version": self.schema_version,
            "exported_at": self.exported_at,
            "device_id": self.device_id,
            "tenant_id": self.tenant_id,
            "segment_boundaries": [s.to_dict() for s in self.segment_boundaries],
            "entries": [dict(e) for e in self.entries],
            "head_commitment": _head_commitment_dict(
                self.head_commitment, self.runtime_attestation
            ),
            "trust_anchor_key_set": [k.to_dict() for k in self.trust_anchor_key_set],
        }

    def to_dict(self) -> dict[str, Any]:
        """Full bundle dict including receipt_hash."""
        out = self.to_dict_minus_receipt()
        out["receipt_hash"] = self.receipt_hash
        return out


def compute_receipt_hash(bundle_minus_receipt: dict[str, Any]) -> str:
    """sha256-prefixed canonical-bytes hash of `bundle_minus_receipt`.

    Per spec L74 + L87 (invariant 8): the verifier recomputes this and
    refuses bundles whose stored receipt_hash differs.
    """
    canonical_bytes = canonical_dumps(bundle_minus_receipt)
    return "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()


def _head_commitment_dict(
    head: HeadCommitment, runtime_attestation: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Bundle-shape head_commitment per spec L57-63. `runtime_attestation`
    carries the head-signing runtime's RuntimeAttestation (S3t) — the real
    5-field identity + binary_hash when the ledger was opened with runtime
    context, else `{}` (a runtime-agnostic open). This is a VALUE change, not a
    shape change: the `runtime_attestation` key already existed.

    Integrity note: `runtime_attestation` is protected by the bundle's
    `receipt_hash` (verifier invariant 8 — `compute_receipt_hash` covers this
    nested field via `to_dict_minus_receipt()`), NOT by the head Ed25519
    `signature_hex` (invariant 7), which signs only
    `{head_sequence, head_entry_id, signed_at}`. A future maintainer MUST NOT
    assume the head signature attests the runtime — whole-bundle tamper is
    caught by the receipt-hash recomputation, not the head-signature check."""
    return {
        "head_sequence": head.head_sequence,
        "head_entry_id": head.head_entry_id,
        "signed_at": head.signed_at,
        "runtime_attestation": dict(runtime_attestation) if runtime_attestation else {},
        "signature_hex": head.signature_hex,
    }


__all__ = [
    "ExportBundle",
    "SegmentBoundary",
    "TrustAnchorKey",
    "compute_receipt_hash",
]
