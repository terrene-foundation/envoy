# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.budget.reset_scheduler — pure period-key derivation for the five windows.

Per `workspaces/phase-01-mvp/01-analysis/12-budget-tracker-implementation.md`
§ 3.2 item 5 + § 4. The scheduler is the load-bearing primitive for key
design question #5 (reset boundary): the upstream `BudgetTracker` is a
single-allocation primitive, so multi-window reset is Envoy orchestration.

The scheduler is **lazy / event-driven** — NO wall-clock timer. The
orchestrator calls `current_period_key(window, at_time=now)` at every
`reserve_for_call(...)` entry and either reuses the existing per-window
tracker or mints a fresh one when the period has rolled over. Because the
period key is derived from the call's timestamp (not wall-clock now passed
implicitly), a replay test can re-execute a 2-day session and recompute
identical period keys — boundary determinism per design § 6.1 test 5.

## Timezone disposition (Phase 01 = Option A, UTC)

`specs/budget-tracker.md` § Ceilings does NOT specify the timezone basis for
the per_day / per_month boundary; design § 7.1 flags this HIGH ambiguity.
Phase 01 ships **Option A (UTC)** per `journal/0003-GAP-budget-ceiling-timezone.md`
and `03-user-flows/04-daily-digest-flow.md` (both budget reset AND digest
schedule fire at UTC midnight in Phase 01). Known UX surprise: a Singapore
user (UTC+8) sees their per-day budget reset at 8 AM local. Phase 02 ships
Option B (user-local IANA timezone) via the `specs/envelope-model.md`
§ Financial dimension additive edit deferred to shard 22 — that edit triggers
a full 37-sibling re-derivation sweep per `rules/specs-authority.md` Rule 5b,
hence the Phase-02 defer. Option A is within the spec's pre-declared
disposition, so this module makes NO spec edit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from envoy.budget.types import WindowName

__all__ = ["BudgetResetScheduler"]


class BudgetResetScheduler:
    """Pure function over `(window, at_time)` → `period_key`.

    Stateless: every method is a `@staticmethod`. The orchestrator owns the
    mapping from `period_key` → live `BudgetTracker`; this class only computes
    the key.
    """

    @staticmethod
    def current_period_key(
        window: WindowName,
        *,
        at_time: datetime,
        session_id: str,
        intent_id: str,
    ) -> str:
        """Return the period key identifying the active reset window.

        - `per_call` → the call's `intent_id` (resets every call).
        - `per_session` → `session_id` (resets at session boundary; no time basis).
        - `per_hour_velocity` → `"YYYY-MM-DDTHH"` UTC (resets top of each clock hour).
        - `per_day` → `"YYYY-MM-DD"` UTC (Phase-01 Option A; resets UTC midnight).
        - `per_month` → `"YYYY-MM"` UTC (Phase-01 Option A; resets 1st-of-month UTC).

        `at_time` is normalized to UTC; a naive datetime is treated as UTC
        (the canonical Phase-01 clock — `DailyDigestService._utc_now()` seam
        and the Ledger all use UTC).
        """
        utc = _as_utc(at_time)
        if window == "per_call":
            return intent_id
        if window == "per_session":
            return session_id
        if window == "per_hour_velocity":
            return utc.strftime("%Y-%m-%dT%H")
        if window == "per_day":
            return utc.strftime("%Y-%m-%d")
        if window == "per_month":
            return utc.strftime("%Y-%m")
        # `window` is a Literal; an unknown value is a programming error, not
        # a runtime input — surface it loudly rather than returning a silent
        # wrong key (`rules/zero-tolerance.md` Rule 3).
        raise ValueError(f"unknown budget window: {window!r}")


def _as_utc(at_time: datetime) -> datetime:
    """Normalize `at_time` to UTC; treat a naive datetime as already-UTC."""
    if at_time.tzinfo is None:
        return at_time.replace(tzinfo=timezone.utc)
    return at_time.astimezone(timezone.utc)
