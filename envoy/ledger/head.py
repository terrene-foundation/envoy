"""HeadCommitment + HaltedByRollbackRecord — Ledger head + rollback halt.

Per `specs/ledger.md` § Head commitment (line 525 ff., HaltedByRollback
record JSON at lines 532-548) — the head commitment is the signed
(head_sequence, head_entry_id, signed_at) tuple that anchors the chain.
Monotonic non-decreasing `head_sequence` is the primary defense against
T-100 (rollback attack).

Phase 01 narrow scope (T-01-17): foundation lands the dataclasses + the
freshness contract; T-01-18 `EnvoyLedger.head_commitment()` returns these
after each `append()` so external verifiers can audit chain progress.

Per `rules/trust-plane-security.md` MUST NOT Rule 4 (frozen constraint
dataclasses) — both records are `@dataclass(frozen=True)` so a captured
head cannot be silently mutated mid-audit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from envoy.ledger.canonical import is_canonical_timestamp


@dataclass(frozen=True, slots=True)
class HeadCommitment:
    """Signed (head_sequence, head_entry_id) anchor.

    Per specs/ledger.md § Head commitment:
    - `head_sequence`: monotonic non-decreasing across syncs. A decrease
      raises `LedgerRollbackDetectedError` and the runtime appends a
      `HaltedByRollback` entry before halting writes (see
      HaltedByRollbackRecord below).
    - `head_entry_id`: the latest entry's `entry_id` (sha256-prefixed).
    - `signed_at`: ISO 8601 microsecond-padded UTC (the moment the runtime
      computed this commitment; canonical-encoded per #731 byte pinning).
    - `signature_hex`: Ed25519 signature over canonical_dumps of the
      first 3 fields. Re-verified on every external load.
    """

    head_sequence: int
    head_entry_id: str
    signed_at: str
    signature_hex: str

    def __post_init__(self) -> None:
        if not isinstance(self.head_sequence, int) or self.head_sequence < 0:
            raise ValueError(f"head_sequence must be non-negative int (got {self.head_sequence!r})")
        if not self.head_entry_id.startswith("sha256:"):
            raise ValueError(f"head_entry_id must be 'sha256:<hex>' (got {self.head_entry_id!r})")
        # signed_at MUST match the 27-char #731 microsecond-padded UTC ISO 8601
        # shape — otherwise a Rust verifier reading the same logical commitment
        # would compute a different canonical-bytes vector silently.
        if not is_canonical_timestamp(self.signed_at):
            raise ValueError(
                f"signed_at MUST match Phase 01 ISO 8601 microsecond shape "
                f"'YYYY-MM-DDTHH:MM:SS.NNNNNNZ' (got {self.signed_at!r})"
            )
        if not isinstance(self.signature_hex, str) or not self.signature_hex:
            raise ValueError("signature_hex must be non-empty hex str")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "HeadCommitment":
        return cls(
            head_sequence=data["head_sequence"],
            head_entry_id=data["head_entry_id"],
            signed_at=data["signed_at"],
            signature_hex=data["signature_hex"],
        )


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    """Runtime attestation triple bound into the HaltedByRollback record.

    Per `specs/ledger.md` § Halted state (`runtime_identity` field at line 545):
    the halt record carries the runtime's identifying triple — device_id +
    signing_key_id + algorithm_identifier — so an external verifier can
    bind the halt event to a specific runtime instance and re-verify the
    outer envelope's Ed25519 signature.

    `algorithm_identifier` is the same dict the EnvoyLedger holds at
    `self._algorithm_identifier`; we model it as a sorted tuple of
    `(key, value)` pairs so the frozen dataclass can hash + canonical-dump
    deterministically. `to_dict()` re-materializes the dict for wire form.
    """

    device_id: str
    signing_key_id: str
    algorithm_identifier: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.device_id, str) or not self.device_id:
            raise ValueError("device_id must be non-empty str")
        if not isinstance(self.signing_key_id, str) or not self.signing_key_id:
            raise ValueError("signing_key_id must be non-empty str")
        if not isinstance(self.algorithm_identifier, tuple) or not self.algorithm_identifier:
            raise ValueError("algorithm_identifier must be non-empty tuple of (key, value) pairs")
        for pair in self.algorithm_identifier:
            if not (isinstance(pair, tuple) and len(pair) == 2):
                raise ValueError("algorithm_identifier entries must be 2-tuples")
            if not (isinstance(pair[0], str) and isinstance(pair[1], str)):
                raise ValueError("algorithm_identifier keys and values must be str")
        # Sorted-by-key invariant: external verifiers depend on canonical ordering.
        if list(self.algorithm_identifier) != sorted(self.algorithm_identifier):
            raise ValueError("algorithm_identifier must be sorted by key for canonical dumps")

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "signing_key_id": self.signing_key_id,
            "algorithm_identifier": dict(self.algorithm_identifier),
        }

    @classmethod
    def from_runtime(
        cls,
        *,
        device_id: str,
        signing_key_id: str,
        algorithm_identifier: dict,
    ) -> "RuntimeIdentity":
        """Construct from the runtime's live state. Sorts algorithm_identifier
        items by key so the canonical-dump is stable across runs."""
        return cls(
            device_id=device_id,
            signing_key_id=signing_key_id,
            algorithm_identifier=tuple(sorted(algorithm_identifier.items())),
        )


@dataclass(frozen=True, slots=True)
class HaltedByRollbackRecord:
    """Forensic record minted when the runtime detects a rollback.

    Naming note: the Python class name carries the `Record` suffix for
    convention; the wire-form `entry_type` literal is the bare
    `"HaltedByRollback"` per spec § Halted state. `EnvoyLedger._persist_halt_record`
    constructs the EntryEnvelope with `type_="HaltedByRollback"` (no
    suffix) when persisting. Audit-trail consumers grep the audit_store
    for `action == "HaltedByRollback"`.

    Per specs/ledger.md § Halted state (lines 532-548): the runtime appends
    this entry BEFORE halting further Ledger writes when:

    - `head_sequence` decreases between syncs, OR
    - The head signature fails verification, OR
    - An entry's `algorithm_identifier` downgrades unexpectedly.

    The record preserves the divergence forensic trail so post-mortem
    recovery can locate the rollback point. Consumed by
    `envoy ledger audit` (T-15+).

    `detection_reason` is one of (per spec):
    - `sequence_decrease` — head_sequence non-monotonic
    - `head_signature_mismatch` — HeadCommitment signature failed
    - `algorithm_identifier_downgrade` — entry algorithm regressed

    Wire-form note: the inner content emitted by `to_dict()` matches spec
    JSON shape lines 537-548 exactly. The outer `EntryEnvelope` carries
    `type`, `signed_by`, and `signature_hex`; the inner content carries
    `schema_version`, `last_known_good_head`, `detected_head`,
    `detection_reason`, `runtime_identity`, and `halted_at`.
    """

    last_known_good_sequence: int
    last_known_good_entry_id: str
    detected_sequence: int
    detected_entry_id: str
    detection_reason: str
    halted_at: str
    schema_version: str
    runtime_identity: RuntimeIdentity

    _VALID_REASONS = frozenset(
        {
            "sequence_decrease",
            "head_signature_mismatch",
            "algorithm_identifier_downgrade",
        }
    )
    _SCHEMA_VERSION = "halt/1.0"

    def __post_init__(self) -> None:
        if self.detection_reason not in self._VALID_REASONS:
            raise ValueError(
                f"detection_reason must be one of {sorted(self._VALID_REASONS)} "
                f"(got {self.detection_reason!r})"
            )
        if not self.last_known_good_entry_id.startswith("sha256:"):
            raise ValueError("last_known_good_entry_id must be 'sha256:<hex>'")
        if not self.detected_entry_id.startswith("sha256:"):
            raise ValueError("detected_entry_id must be 'sha256:<hex>'")
        if not isinstance(self.last_known_good_sequence, int) or self.last_known_good_sequence < 0:
            raise ValueError("last_known_good_sequence must be non-negative int")
        if not isinstance(self.detected_sequence, int) or self.detected_sequence < 0:
            raise ValueError("detected_sequence must be non-negative int")
        # halted_at MUST match the 27-char #731 microsecond-padded UTC ISO 8601
        # shape — same reason as HeadCommitment.signed_at.
        if not is_canonical_timestamp(self.halted_at):
            raise ValueError(
                f"halted_at MUST match Phase 01 ISO 8601 microsecond shape "
                f"'YYYY-MM-DDTHH:MM:SS.NNNNNNZ' (got {self.halted_at!r})"
            )
        if self.schema_version != self._SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {self._SCHEMA_VERSION!r} " f"(got {self.schema_version!r})"
            )
        if not isinstance(self.runtime_identity, RuntimeIdentity):
            raise ValueError(
                f"runtime_identity must be a RuntimeIdentity instance "
                f"(got {type(self.runtime_identity).__name__})"
            )

    def to_dict(self) -> dict:
        # Order matches spec JSON shape (specs/ledger.md:537-548) so
        # canonical_dumps produces bytes external verifiers can re-derive.
        return {
            "schema_version": self.schema_version,
            "last_known_good_head": {
                "sequence": self.last_known_good_sequence,
                "entry_id": self.last_known_good_entry_id,
            },
            "detected_head": {
                "sequence": self.detected_sequence,
                "entry_id": self.detected_entry_id,
            },
            "detection_reason": self.detection_reason,
            "runtime_identity": self.runtime_identity.to_dict(),
            "halted_at": self.halted_at,
        }


__all__ = ["HaltedByRollbackRecord", "HeadCommitment", "RuntimeIdentity"]
