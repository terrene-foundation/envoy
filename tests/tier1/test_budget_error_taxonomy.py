# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 — Budget error taxonomy: subclassing pins + dual-catch contract.

Pins the multiple-inheritance contract for `envoy.budget.errors.BudgetExhaustedError`:
it MUST be catchable both as the package base (`EnvoyBudgetError`) AND as the
runtime-protocol contract error (`envoy.runtime.errors.BudgetExhaustedError`).
A future refactor of either base that silently breaks the dual-catch is the
exact failure this test guards against (per reviewer LOW-5).
"""

from __future__ import annotations

import pytest

from envoy.budget.errors import (
    AnomalyDetectedError,
    BudgetExhaustedError,
    EnvoyBudgetError,
    HighVelocityPatternError,
    MicrodollarOverflowError,
    ReservationDoubleRecordError,
    ReservationExpiredError,
    VelocityRaiseInlineBlockError,
)
from envoy.runtime.errors import BudgetExhaustedError as _RuntimeBudgetExhaustedError


class TestSubclassingContract:
    def test_budget_exhausted_is_envoy_budget_error(self) -> None:
        e = BudgetExhaustedError(
            window="per_session",
            requested_microdollars=1,
            remaining_microdollars=0,
            allocated_microdollars=10,
        )
        assert isinstance(e, EnvoyBudgetError)

    def test_budget_exhausted_is_runtime_contract_error(self) -> None:
        e = BudgetExhaustedError(
            window="per_session",
            requested_microdollars=1,
            remaining_microdollars=0,
            allocated_microdollars=10,
        )
        # Existing `except envoy.runtime.errors.BudgetExhaustedError` handlers
        # MUST catch the concrete budget-package error.
        assert isinstance(e, _RuntimeBudgetExhaustedError)

    def test_all_other_budget_errors_share_the_envoy_base(self) -> None:
        # Every typed error in the spec's taxonomy subclasses EnvoyBudgetError
        # so `except EnvoyBudgetError` catches the whole package.
        cases = [
            VelocityRaiseInlineBlockError(
                window="per_hour_velocity", current_microdollars=1, requested_microdollars=2
            ),
            AnomalyDetectedError(
                requested_microdollars=10, session_remaining_microdollars=15, threshold_pct=0.5
            ),
            HighVelocityPatternError(hits=5, window_seconds=60),
            ReservationExpiredError(reservation_id="r", expired_at="now", recorded_at="later"),
            MicrodollarOverflowError(value=2**64, field_name="f"),
            ReservationDoubleRecordError(reservation_id="r", first_recorded_at="t"),
        ]
        for e in cases:
            assert isinstance(e, EnvoyBudgetError), f"{type(e).__name__} must be EnvoyBudgetError"

    def test_runtime_contract_does_not_leak_to_unrelated_budget_errors(self) -> None:
        # Only BudgetExhaustedError straddles the runtime contract; the rest
        # of the taxonomy MUST NOT be caught as runtime BudgetExhaustedError.
        e = ReservationDoubleRecordError(reservation_id="r", first_recorded_at="t")
        assert not isinstance(e, _RuntimeBudgetExhaustedError)


class TestDualCatchContract:
    def test_dual_catch_via_envoy_base(self) -> None:
        with pytest.raises(EnvoyBudgetError):
            raise BudgetExhaustedError(
                window="per_call",
                requested_microdollars=1,
                remaining_microdollars=0,
                allocated_microdollars=1,
            )

    def test_dual_catch_via_runtime_contract(self) -> None:
        with pytest.raises(_RuntimeBudgetExhaustedError):
            raise BudgetExhaustedError(
                window="per_call",
                requested_microdollars=1,
                remaining_microdollars=0,
                allocated_microdollars=1,
            )
