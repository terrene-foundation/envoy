# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 — integer-microdollar arithmetic: int-only, no float drift, overflow.

Spec authority: `specs/budget-tracker.md` § Data unit ("Integer microdollars
... No float accumulation.") + § Error taxonomy (`MicrodollarOverflowError`).
Pre-declared by spec § Test location as `test_microdollar_arithmetic.py`
(reconciled to `tests/tier1/` per `rules/spec-accuracy.md` Rule 1 — the project
uses tier-based dirs, not `tests/unit/`).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from envoy.budget import EnvoyBudgetOrchestrator, MicrodollarOverflowError, WindowCeilings
from envoy.budget.types import INT64_MAX

_CEIL = WindowCeilings(
    per_call_ceiling_microdollars=INT64_MAX,
    per_session_ceiling_microdollars=INT64_MAX,
    per_hour_velocity_microdollars=INT64_MAX,
    per_day_ceiling_microdollars=INT64_MAX,
    per_month_ceiling_microdollars=INT64_MAX,
)


def _orch() -> EnvoyBudgetOrchestrator:
    return EnvoyBudgetOrchestrator(
        ceilings=_CEIL,
        store=None,
        principal_id="alice",
        session_id="s1",
        clock=lambda: datetime(2026, 5, 3, 10, 0, 0, tzinfo=timezone.utc),
    )


class TestOverflowDetection:
    def test_value_above_int64_max_raises(self) -> None:
        with pytest.raises(MicrodollarOverflowError) as ei:
            _orch().reserve_for_call(INT64_MAX + 1, intent_id="i1")
        assert ei.value.field_name == "estimated_microdollars"
        assert ei.value.value == INT64_MAX + 1

    def test_negative_microdollars_raises(self) -> None:
        with pytest.raises(MicrodollarOverflowError):
            _orch().reserve_for_call(-1, intent_id="i1")

    def test_float_microdollars_raises(self) -> None:
        # No float accumulation — a float estimate is rejected at the boundary.
        with pytest.raises(MicrodollarOverflowError):
            _orch().reserve_for_call(500_000.5, intent_id="i1")  # type: ignore[arg-type]

    def test_bool_is_not_a_valid_microdollar_int(self) -> None:
        # bool is a subclass of int in Python; the boundary MUST reject it so
        # `True` cannot smuggle in as `1` microdollar.
        with pytest.raises(MicrodollarOverflowError):
            _orch().reserve_for_call(True, intent_id="i1")  # type: ignore[arg-type]

    def test_record_actual_above_int64_raises(self) -> None:
        orch = _orch()
        handle = orch.reserve_for_call(1_000, intent_id="i1")
        with pytest.raises(MicrodollarOverflowError) as ei:
            orch.record_for_call(handle, INT64_MAX + 5)
        assert ei.value.field_name == "actual_microdollars"


class TestNoFloatDrift:
    def test_reserve_record_is_exact_integer(self) -> None:
        orch = _orch()
        handle = orch.reserve_for_call(333_333, intent_id="i1")
        orch.record_for_call(handle, 333_333)
        snap = orch.snapshot()
        # Exact integer commit — no float rounding anywhere in the path.
        assert snap.per_session.committed == 333_333
        assert isinstance(snap.per_session.committed, int)

    def test_zero_cost_call_is_valid(self) -> None:
        orch = _orch()
        handle = orch.reserve_for_call(0, intent_id="i1")
        orch.record_for_call(handle, 0)
        assert orch.snapshot().per_session.committed == 0
