# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 — budget_velocity_check raises on committed+reserved breach.

Surfaced by the security review on `feat/phase-01-shard-12-budget-tracker`
(MEDIUM-2): the prior implementation read `BudgetSnapshot.committed` only,
which silently under-reports an in-flight reservation that has not yet been
recorded. Per `specs/runtime-abstraction.md` § budget_velocity_check the
contract is "raise if any ceiling breached" — held capacity counts.

Fix: route through `EnvoyBudgetOrchestrator.window_check` which returns the
per-window `BudgetCheckResult` (committed + reserved + remaining), so the
breach predicate is `committed + reserved >= allocated`.
"""

from __future__ import annotations

import pytest

from envoy.budget import (
    EnvoyBudgetOrchestrator,
    WindowCeilings,
)
from envoy.budget.runtime_adapter import BudgetRuntimeAdapter
from envoy.runtime.errors import BudgetVelocityExceededError

_CEIL = WindowCeilings(
    per_call_ceiling_microdollars=10_000_000,
    per_session_ceiling_microdollars=100_000_000,
    per_hour_velocity_microdollars=5_000_000,
    per_day_ceiling_microdollars=50_000_000,
    per_month_ceiling_microdollars=1_000_000_000,
)


def _adapter() -> BudgetRuntimeAdapter:
    orch = EnvoyBudgetOrchestrator(
        ceilings=_CEIL, store=None, principal_id="alice", session_id="s1"
    )
    return BudgetRuntimeAdapter(orchestrator=orch)


class TestVelocityCheckReservedAware:
    def test_unreserved_window_does_not_raise(self) -> None:
        result = _adapter().budget_velocity_check("s1")
        assert result.allowed is True

    def test_full_window_reserved_but_not_recorded_raises(self) -> None:
        adapter = _adapter()
        # Fully reserve the 5M per_hour window — committed=0 yet, but
        # reserved=5M. The check MUST raise (committed+reserved >= allocated).
        adapter.budget_reserve("s1", 5_000_000)
        with pytest.raises(BudgetVelocityExceededError) as ei:
            adapter.budget_velocity_check("s1")
        assert "5000000 reserved" in str(ei.value) or "reserved" in str(ei.value)

    def test_full_window_committed_raises(self) -> None:
        adapter = _adapter()
        rid = adapter.budget_reserve("s1", 5_000_000)
        adapter.budget_record(rid, 5_000_000)
        with pytest.raises(BudgetVelocityExceededError):
            adapter.budget_velocity_check("s1")
