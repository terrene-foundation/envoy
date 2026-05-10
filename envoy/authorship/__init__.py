"""envoy.authorship — Authorship Score primitive (T-02-30) + PostureGate (T-02-31).

Phase 01 ships:

- The count-only deterministic recompute per `specs/authorship-score.md` §
  Re-derivation from the Ledger (T-02-30). Novelty + minimum-impact +
  classifier registry + standard-action-corpus are Phase-04 hardening
  (see spec § "Out of scope (Phase 01)").
- The 5-step fail-closed posture transition gate per `specs/posture-ladder.md`
  § Algorithm (T-02-31). Cooling-off TIMER and annual-decay scheduler are
  Phase 03; this module enforces both as input booleans.

Public facade per `rules/orphan-detection.md` Rule 6 — every module-scope
import below appears in `__all__`.
"""

from envoy.authorship.posture_gate import (
    PostureAuthorshipInsufficientError,
    PostureChangeResult,
    PostureCoolingOffActiveError,
    PostureEnterpriseAutonomousForbidden,
    PostureEvidence,
    PostureGate,
    PostureGateError,
    PostureGenesisGrantMissingError,
    PostureLevel,
    PostureMode,
    PostureNoopError,
)
from envoy.authorship.score import (
    AuthorshipCounters,
    AuthorshipScoreDivergenceError,
    recompute_authorship_counters,
)

__all__ = [
    "AuthorshipCounters",
    "AuthorshipScoreDivergenceError",
    "PostureAuthorshipInsufficientError",
    "PostureChangeResult",
    "PostureCoolingOffActiveError",
    "PostureEnterpriseAutonomousForbidden",
    "PostureEvidence",
    "PostureGate",
    "PostureGateError",
    "PostureGenesisGrantMissingError",
    "PostureLevel",
    "PostureMode",
    "PostureNoopError",
    "recompute_authorship_counters",
]
