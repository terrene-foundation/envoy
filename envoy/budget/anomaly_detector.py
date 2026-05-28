# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.budget.anomaly_detector — T-093 budget-exhaustion fraud defense.

Per `workspaces/phase-01-mvp/01-analysis/12-budget-tracker-implementation.md`
§ 3.2 item 6 + § 4, implementing `specs/budget-tracker.md` § Budget-exhaustion
fraud defense (lines 41-45):

1. **Single-call > 50% session budget** — a call that would consume more than
   half of the remaining session budget is paused for confirmation.
2. **5 calls at ceiling in 60s** — a high-velocity burst routes to a Grant
   Moment.

Both thresholds are `specs/budget-tracker.md` § Open-question constants
(LOW ambiguity per design § 7.3); Phase 01 implements the spec defaults and
surfaces telemetry for Phase-02 empirical calibration. The detector RETURNS
the typed error (or `None`) rather than raising — the orchestrator decides
whether to raise immediately or route to a Grant Moment.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from envoy.budget.errors import AnomalyDetectedError, HighVelocityPatternError

__all__ = ["AnomalyDetector"]


class AnomalyDetector:
    """Stateful fraud-pattern detector (single-call magnitude + velocity burst).

    The velocity ring buffer holds the timestamps of the last
    `velocity_count_threshold` ceiling hits; older entries are evicted lazily
    on each `record_ceiling_hit`.
    """

    def __init__(
        self,
        *,
        single_call_session_pct_threshold: float = 0.50,
        velocity_window_seconds: int = 60,
        velocity_count_threshold: int = 5,
    ) -> None:
        self._pct_threshold = single_call_session_pct_threshold
        self._velocity_window = timedelta(seconds=velocity_window_seconds)
        self._velocity_window_seconds = velocity_window_seconds
        self._velocity_count_threshold = velocity_count_threshold
        # Bounded ring buffer — only the last N hits matter for the predicate.
        self._ceiling_hits: deque[datetime] = deque(maxlen=velocity_count_threshold)

    def check_single_call(
        self,
        *,
        estimated_microdollars: int,
        per_session_remaining_microdollars: int,
    ) -> AnomalyDetectedError | None:
        """Return an `AnomalyDetectedError` if the call exceeds the session-pct
        threshold, else `None`.

        Guards against the degenerate `remaining <= 0` case: when no session
        budget remains, exhaustion (not anomaly) is the binding condition, so
        this returns `None` and lets the ceiling check raise
        `BudgetExhaustedError` instead.
        """
        if per_session_remaining_microdollars <= 0:
            return None
        if estimated_microdollars > self._pct_threshold * per_session_remaining_microdollars:
            return AnomalyDetectedError(
                requested_microdollars=estimated_microdollars,
                session_remaining_microdollars=per_session_remaining_microdollars,
                threshold_pct=self._pct_threshold,
            )
        return None

    def record_ceiling_hit(self, at_time: datetime) -> HighVelocityPatternError | None:
        """Record a per-call-ceiling hit; return `HighVelocityPatternError` when
        `velocity_count_threshold` hits fall within `velocity_window_seconds`.

        The buffer is `maxlen`-bounded, so a full buffer whose oldest entry is
        within the window is exactly the fire condition.
        """
        self._ceiling_hits.append(at_time)
        if len(self._ceiling_hits) < self._velocity_count_threshold:
            return None
        span = at_time - self._ceiling_hits[0]
        if span <= self._velocity_window:
            return HighVelocityPatternError(
                hits=self._velocity_count_threshold,
                window_seconds=self._velocity_window_seconds,
            )
        return None
