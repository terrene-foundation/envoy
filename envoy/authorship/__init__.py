"""envoy.authorship — Authorship Score primitive (T-02-30) + PostureGate (T-02-31)
+ BET-12 cadence emitter (T-02-32).

Phase 01 ships:

- The count-only deterministic recompute per `specs/authorship-score.md` §
  Re-derivation from the Ledger (T-02-30). Novelty + minimum-impact +
  classifier registry + standard-action-corpus are Phase-04 hardening
  (see spec § "Out of scope (Phase 01)").
- The 5-step fail-closed posture transition gate per `specs/posture-ladder.md`
  § Algorithm (T-02-31). Cooling-off TIMER and annual-decay scheduler are
  Phase 03; this module enforces both as input booleans.
- The BET-12 cohort-cadence emitter per
  `briefs/00-phase-01-mvp-scope.md` § Phase 01 invariants #3 (T-02-32).
  Phase 01 ships the primitive + Protocol-typed `BET12Sink`; the concrete
  Phase-01 default sink that writes ritual-style Ledger entries lands
  with `specs/ledger.md` schema disposition at T-02-33 (Tier 2 wiring).

Public facade per `rules/orphan-detection.md` Rule 6 — every module-scope
import below appears in `__all__`.
"""

from envoy.authorship.bet12_emitter import (
    BET12CadenceEmitter,
    BET12CadencePayload,
    BET12Sink,
)
from envoy.authorship.posture_gate import (
    PostureAuthorshipInsufficientError,
    PostureChangeResult,
    PostureCoolingOffActiveError,
    PostureEnterpriseAutonomousForbidden,
    PostureEnvelopeMutationInvariantError,
    PostureEvidence,
    PostureGate,
    PostureGateError,
    PostureGenesisGrantMissingError,
    PostureLevel,
    PostureMode,
    PostureNoopError,
    PostureRatchetEnvelopeMissingError,
)
from envoy.authorship.novelty import (
    NoveltyChecker,
    NoveltyFeedbackBlockError,
    NoveltyResult,
)
from envoy.authorship.score import (
    AuthorshipCounters,
    AuthorshipScoreDivergenceError,
    recompute_authorship_counters,
)

__all__ = [
    "AuthorshipCounters",
    "AuthorshipScoreDivergenceError",
    "BET12CadenceEmitter",
    "BET12CadencePayload",
    "BET12Sink",
    "NoveltyChecker",
    "NoveltyFeedbackBlockError",
    "NoveltyResult",
    "PostureAuthorshipInsufficientError",
    "PostureChangeResult",
    "PostureCoolingOffActiveError",
    "PostureEnterpriseAutonomousForbidden",
    "PostureEnvelopeMutationInvariantError",
    "PostureEvidence",
    "PostureGate",
    "PostureGateError",
    "PostureGenesisGrantMissingError",
    "PostureLevel",
    "PostureMode",
    "PostureNoopError",
    "PostureRatchetEnvelopeMissingError",
    "recompute_authorship_counters",
]
