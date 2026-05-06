"""LamportClock — logical clock for CRDT merge ordering.

Per `specs/ledger.md` § Entry envelope schema lines 18-23:

    "lamport_clock": {
      "lamport_time": <int>,
      "device_id": <sha256>,
      "local_seq": <int>
    }

Sort priority for `specs/ledger-merge.md` § CRDT merge:
1. `lamport_time` — primary key (monotonic logical clock per Phase 00 doc 04 v1 §7)
2. `device_id` — secondary key (SHA-256 of device binding pubkey)
3. `local_seq` — tertiary key (per-device monotonic sequence)

Per `rules/trust-plane-security.md` MUST NOT Rule 4 (frozen constraint
dataclasses) the LamportClock is `@dataclass(frozen=True)` — once minted
into an `EntryEnvelope` it cannot be silently re-numbered.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LamportClock:
    """Logical clock tuple for a single Ledger entry.

    `lamport_time`: max observed `lamport_time` across all local + ingested
    entries on this device, plus 1. Resets only on full vault destroy.

    `device_id`: SHA-256 of the device binding pubkey (hex). Stable across
    the device's lifetime; forms the persistence-domain partition key.

    `local_seq`: per-device monotonic counter, restarts at 1 with each
    fresh device key (post-key-rotation). Tertiary tiebreaker.
    """

    lamport_time: int
    device_id: str
    local_seq: int

    def __post_init__(self) -> None:
        # Defensive shape checks — these dataclasses cross the canonical-JSON
        # boundary and any out-of-shape value would corrupt entry_id derivation.
        if not isinstance(self.lamport_time, int) or self.lamport_time < 0:
            raise ValueError(f"lamport_time must be non-negative int (got {self.lamport_time!r})")
        if not isinstance(self.device_id, str) or not self.device_id:
            raise ValueError(f"device_id must be non-empty str (got {self.device_id!r})")
        if not isinstance(self.local_seq, int) or self.local_seq < 0:
            raise ValueError(f"local_seq must be non-negative int (got {self.local_seq!r})")

    def to_dict(self) -> dict:
        """Wire shape per specs/ledger.md § Entry envelope schema."""
        return {
            "lamport_time": self.lamport_time,
            "device_id": self.device_id,
            "local_seq": self.local_seq,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LamportClock":
        return cls(
            lamport_time=data["lamport_time"],
            device_id=data["device_id"],
            local_seq=data["local_seq"],
        )


__all__ = ["LamportClock"]
