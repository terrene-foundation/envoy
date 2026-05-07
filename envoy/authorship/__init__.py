"""envoy.authorship — Authorship Score primitive (T-02-30 count-only).

Phase 01 ships the count-only deterministic recompute per
`specs/authorship-score.md` § Re-derivation from the Ledger. The novelty +
minimum-impact algorithms + classifier registry + standard-action-corpus
dependency are Phase-04 hardening (see spec § "Out of scope (Phase 01)").

Public facade per `rules/orphan-detection.md` Rule 6 — every module-scope
import below appears in `__all__`.
"""

from envoy.authorship.score import (
    AuthorshipCounters,
    AuthorshipScoreDivergenceError,
    recompute_authorship_counters,
)

__all__ = [
    "AuthorshipCounters",
    "AuthorshipScoreDivergenceError",
    "recompute_authorship_counters",
]
