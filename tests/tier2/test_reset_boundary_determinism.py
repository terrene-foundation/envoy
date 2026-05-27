# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 — reset-boundary period-key determinism + replay equivalence.

Design § 6.1 test 5. The `BudgetResetScheduler` is a pure function over
`(window, at_time)`; period keys are derived from the call timestamp (not
wall-clock now), so a 2-day session replays to identical keys — the basis for
deterministic Ledger reconstruction.

Phase-01 Option A (UTC) per `journal/0003-GAP-budget-ceiling-timezone.md`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from envoy.budget import BudgetResetScheduler

_S = BudgetResetScheduler


class TestBoundaryDeterminism:
    def test_per_day_boundary_flips_at_utc_midnight(self) -> None:
        last_second = datetime(2026, 5, 3, 23, 59, 59, tzinfo=timezone.utc)
        first_second = datetime(2026, 5, 4, 0, 0, 0, tzinfo=timezone.utc)
        assert (
            _S.current_period_key("per_day", at_time=last_second, session_id="s", intent_id="i")
            == "2026-05-03"
        )
        assert (
            _S.current_period_key("per_day", at_time=first_second, session_id="s", intent_id="i")
            == "2026-05-04"
        )

    def test_per_hour_boundary_flips_at_top_of_hour(self) -> None:
        a = datetime(2026, 5, 3, 10, 59, 59, tzinfo=timezone.utc)
        b = datetime(2026, 5, 3, 11, 0, 0, tzinfo=timezone.utc)
        assert (
            _S.current_period_key("per_hour_velocity", at_time=a, session_id="s", intent_id="i")
            == "2026-05-03T10"
        )
        assert (
            _S.current_period_key("per_hour_velocity", at_time=b, session_id="s", intent_id="i")
            == "2026-05-03T11"
        )

    def test_per_month_boundary_flips_at_month_end(self) -> None:
        a = datetime(2026, 5, 31, 23, 59, 59, tzinfo=timezone.utc)
        b = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert (
            _S.current_period_key("per_month", at_time=a, session_id="s", intent_id="i")
            == "2026-05"
        )
        assert (
            _S.current_period_key("per_month", at_time=b, session_id="s", intent_id="i")
            == "2026-06"
        )

    def test_naive_datetime_treated_as_utc(self) -> None:
        naive = datetime(2026, 5, 3, 12, 0, 0)  # no tzinfo
        aware = datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)
        assert _S.current_period_key(
            "per_day", at_time=naive, session_id="s", intent_id="i"
        ) == _S.current_period_key("per_day", at_time=aware, session_id="s", intent_id="i")

    def test_session_and_call_keys_are_identity(self) -> None:
        t = datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)
        assert (
            _S.current_period_key("per_session", at_time=t, session_id="sess-42", intent_id="i")
            == "sess-42"
        )
        assert (
            _S.current_period_key("per_call", at_time=t, session_id="s", intent_id="intent-99")
            == "intent-99"
        )

    def test_replay_produces_identical_keys(self) -> None:
        # A 2-day sequence of call timestamps replays to identical keys both runs.
        timestamps = [
            datetime(2026, 5, 3, 8, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 5, 3, 23, 30, 0, tzinfo=timezone.utc),
            datetime(2026, 5, 4, 0, 15, 0, tzinfo=timezone.utc),
            datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc),
        ]

        def run() -> list[tuple[str, str, str]]:
            return [
                (
                    _S.current_period_key(
                        "per_hour_velocity", at_time=t, session_id="s", intent_id="i"
                    ),
                    _S.current_period_key("per_day", at_time=t, session_id="s", intent_id="i"),
                    _S.current_period_key("per_month", at_time=t, session_id="s", intent_id="i"),
                )
                for t in timestamps
            ]

        assert run() == run()
