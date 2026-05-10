"""BET-12 cadence emitter — cohort-level posture-transition telemetry.

Per `briefs/00-phase-01-mvp-scope.md` § Phase 01 invariants #3 (BET-12
falsifiability) + `01-analysis/09-authorship-score-implementation.md` § 3.3.
BET-12 (governance-primary-surface palatability per `02-mvp-objectives.md` § 3)
requires falsifiable measurement; without a cadence emitter shipped in
Phase 01, the BET is unfalsifiable until Phase 02.

The emitter is a structural prerequisite, not an exit criterion. Phase 01
sink: pluggable via `BET12Sink` Protocol — concrete Phase-01 default sink
that writes ritual-style Ledger entries lands at T-02-33 (Tier 2 wiring;
also schema-edits `specs/ledger.md` to either extend `ritual_completion`
or introduce a `posture_transition_cadence` entry type). Phase 02 sink:
Foundation Health Heartbeat STAR/Prio aggregation per
`specs/foundation-health-heartbeat.md`.

Privacy contract (per `rules/event-payload-classification.md` Rule 2 + Rule 3):

- `principal_id` MUST be hashed before emission. Phase 01 fingerprint shape
  matches `format_record_id_for_event` (kailash-py
  `dataflow.classification.event_payload`) — `f"sha256:{sha256(pid)[:8]}"`.
  Cross-SDK forensic correlation works without leaking raw principal IDs
  into eventual Heartbeat aggregation.
- `posture` content MUST NOT exceed (from, to) levels. Envelope hash,
  authored_constraints names, classified field names are BLOCKED in payloads
  — the emitter intentionally does not accept those fields, structurally
  defending against Rule 3 leakage at the API boundary.

Invariants (verified at construction + emit time):

1. `bet_id` tag is canonical "BET-12" on every emit (`_BET_ID_CANONICAL`
   module constant; no per-call override).
2. Emit fires on every posture-transition `PostureGate` accepts (call site:
   `envoy/authorship/posture_gate.py::PostureGate.request_transition` Step 5+
   post-Ledger). Per `rules/orphan-detection.md` Rule 1, the call site lives
   in the framework's hot path — not in tests, not in downstream consumers.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from envoy.authorship.posture_gate import PostureLevel

__all__ = [
    "BET12CadenceEmitter",
    "BET12CadencePayload",
    "BET12Sink",
]


# Invariant 1: bet_id tag canonical. Module-level constant; no per-call
# override is exposed on `BET12CadenceEmitter.emit`. Future BET measurement
# emitters (BET-N) ship as separate emitter classes with their own
# `_BET_ID_CANONICAL` constants — never as a configurable kwarg on this one.
_BET_ID_CANONICAL: str = "BET-12"

# Phase 01 fingerprint shape per `rules/event-payload-classification.md`
# Rule 2: `f"sha256:{sha256(pid)[:8]}"`. Length matches kailash-py
# `format_record_id_for_event` so cross-SDK correlation works on the
# 8-hex prefix without expanding to a full 64-hex digest (which would
# inflate Foundation Heartbeat aggregation payload bytes).
_PRINCIPAL_ID_HASH_PREFIX: str = "sha256:"
_PRINCIPAL_ID_HASH_LEN: int = 8


def _hash_principal_id(principal_id: str) -> str:
    """Hash `principal_id` per `rules/event-payload-classification.md` Rule 2.

    Raises `ValueError` for empty / non-string input — fail-loud at the
    boundary per `rules/zero-tolerance.md` Rule 3a (typed-guard pattern).
    """
    if not isinstance(principal_id, str) or not principal_id:
        raise ValueError(
            "principal_id must be a non-empty str (got "
            f"{type(principal_id).__name__}={principal_id!r})"
        )
    digest = hashlib.sha256(principal_id.encode("utf-8")).hexdigest()[:_PRINCIPAL_ID_HASH_LEN]
    return f"{_PRINCIPAL_ID_HASH_PREFIX}{digest}"


@dataclass(frozen=True)
class BET12CadencePayload:
    """Cohort-level posture-transition cadence event payload.

    Wire-form contract:

    - `bet_id` always `"BET-12"` (module invariant; verified at emit time).
    - `principal_id_hash` shape `sha256:XXXXXXXX` (8 hex chars).
    - `from_level`, `to_level` are `PostureLevel` enum values — string-
      serialized as `"PSEUDO" | "TOOL" | "SUPERVISED" | "DELEGATING" |
      "AUTONOMOUS"` per `specs/posture-ladder.md` § Canonical enum wire
      format. The integer values 0..4 are internal-comparison-only.
    - `days_at_current_posture` is non-negative `float`. Phase 03 Weekly
      Posture Review computes from PostureStore history; Phase 01 callers
      may pass 0.0 if not tracked.
    - `authored_count_at_transition` is non-negative `int` — mirrors
      `evidence.authorship_score_recomputed` at the gate's Step 5 entry.

    Per `rules/event-payload-classification.md` Rule 3, the payload does
    NOT expose envelope hashes, authored_constraints names, or classified
    field names — those would be schema-revealing leakage to log
    aggregators / Foundation Heartbeat. The from/to enum is the only
    posture content that crosses the wire.
    """

    bet_id: str
    principal_id_hash: str
    from_level: PostureLevel
    to_level: PostureLevel
    days_at_current_posture: float
    authored_count_at_transition: int


@runtime_checkable
class BET12Sink(Protocol):
    """Sink for BET-12 cadence events.

    Phase 01 default sink (T-02-33): writes ritual-style Ledger entry with
    `bet_id="BET-12"` (specs/ledger.md schema disposition is part of T-02-33).
    Phase 02 sink: Foundation Health Heartbeat STAR/Prio aggregation per
    `specs/foundation-health-heartbeat.md`.

    The Protocol shape is `runtime_checkable` so Tier 2 wiring (T-02-33)
    can assert structural conformance against fakes without inheritance
    coupling, mirroring the pattern in
    `envoy/shamir/types.py::CommitmentBinder`.
    """

    async def write(self, payload: BET12CadencePayload) -> None: ...


class BET12CadenceEmitter:
    """Hash-fingerprinted posture-transition cadence emitter.

    Constructor takes a `BET12Sink` (Protocol-typed). `__init__` rejects
    `None` with a typed `ValueError` so misconfiguration fails at gate
    construction time, never at emit time mid-transition.

    Per `rules/facade-manager-detection.md` Rule 3, the emitter receives
    its sink as an explicit dependency — no global lookup, no
    self-construction of the underlying ledger / aggregator handle.
    """

    def __init__(self, *, sink: BET12Sink) -> None:
        if sink is None:
            raise ValueError("sink is required (no None default)")
        self._sink = sink

    async def emit(
        self,
        *,
        principal_id: str,
        from_level: PostureLevel,
        to_level: PostureLevel,
        days_at_current_posture: float,
        authored_count_at_transition: int,
    ) -> None:
        """Emit one cadence event to the configured sink.

        Args:
            principal_id: raw principal id; hashed before emission.
            from_level: posture level at start of transition.
            to_level: posture level after transition.
            days_at_current_posture: time at `from_level` (non-negative).
            authored_count_at_transition: authorship score recomputed at
                the gate's Step 5 entry (non-negative).

        Raises:
            `ValueError` for negative `days_at_current_posture` /
                `authored_count_at_transition` OR empty `principal_id`.
                Value-range guards are reachable because `>= 0` cannot be
                expressed in the annotation; type-shape guards are NOT
                performed here — the gate's Step 5+ call site is the
                boundary, and the type annotations are the contract
                (per CLAUDE.md "trust internal code and framework
                guarantees; only validate at system boundaries").

        Sink errors propagate unchanged — the gate's Step 5+ call site
        decides whether to swallow (best-effort telemetry) or re-raise.
        """
        if days_at_current_posture < 0:
            raise ValueError(
                f"days_at_current_posture must be non-negative, got " f"{days_at_current_posture!r}"
            )
        if authored_count_at_transition < 0:
            raise ValueError(
                f"authored_count_at_transition must be non-negative, got "
                f"{authored_count_at_transition!r}"
            )
        # principal_id validation (non-empty str) happens inside
        # `_hash_principal_id` at the boundary where the bytes are encoded.

        payload = BET12CadencePayload(
            bet_id=_BET_ID_CANONICAL,
            principal_id_hash=_hash_principal_id(principal_id),
            from_level=from_level,
            to_level=to_level,
            days_at_current_posture=float(days_at_current_posture),
            authored_count_at_transition=authored_count_at_transition,
        )
        await self._sink.write(payload)
