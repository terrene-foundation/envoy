"""HeadCommitment + HaltedByRollbackRecord — Ledger head + rollback halt.

Per `specs/ledger.md` § Head commitment (lines 528-545) — the head
commitment is the signed (head_sequence, head_entry_id, signed_at) tuple
that anchors the chain. Monotonic non-decreasing `head_sequence` is the
primary defense against T-100 (rollback attack).

Phase 01 narrow scope (T-01-17): foundation lands the dataclasses + the
freshness contract; T-01-18 `EnvoyLedger.head_commitment()` returns these
after each `append()` so external verifiers can audit chain progress.

Per `rules/trust-plane-security.md` MUST NOT Rule 4 (frozen constraint
dataclasses) — both records are `@dataclass(frozen=True)` so a captured
head cannot be silently mutated mid-audit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


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
        if not isinstance(self.signed_at, str) or not self.signed_at:
            raise ValueError(f"signed_at must be non-empty ISO 8601 str (got {self.signed_at!r})")
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
class HaltedByRollbackRecord:
    """Forensic record minted when the runtime detects a rollback.

    Per specs/ledger.md § Halted state (lines 532-545): the runtime appends
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
    """

    last_known_good_sequence: int
    last_known_good_entry_id: str
    detected_sequence: int
    detected_entry_id: str
    detection_reason: str
    detected_at: str

    _VALID_REASONS = frozenset(
        {
            "sequence_decrease",
            "head_signature_mismatch",
            "algorithm_identifier_downgrade",
        }
    )

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

    def to_dict(self) -> dict:
        return {
            "last_known_good_head": {
                "sequence": self.last_known_good_sequence,
                "entry_id": self.last_known_good_entry_id,
            },
            "detected_head": {
                "sequence": self.detected_sequence,
                "entry_id": self.detected_entry_id,
            },
            "detection_reason": self.detection_reason,
            "detected_at": self.detected_at,
        }


__all__ = ["HaltedByRollbackRecord", "HeadCommitment"]
