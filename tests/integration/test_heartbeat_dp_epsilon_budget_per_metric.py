# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-S11.2 — DP ε published, tracked total-over-window, per-metric independent.

Tier-2 per `rules/testing.md`: drives the REAL `DPBudget` accounting + the REAL
`HeartbeatClient.emit_weekly` pipeline. Each flag has a published per-metric ε;
the enforcement counter tracks ε-spent vs the published budget over the weekly
window (structural counter-vs-budget assertion — exit-code/numeric, no LLM
judge). Exhausting ONE metric's budget drops ONLY that metric; others report
normally.
"""

from __future__ import annotations

import pytest

from envoy.heartbeat.client import (
    DEFAULT_METRIC_EPSILON,
    DPBudget,
    HeartbeatClient,
    OptOutConsentGate,
)
from envoy.heartbeat.errors import DPBudgetExceededError
from envoy.heartbeat.star_prio import StarPrioClient


class TestDPBudgetPerMetric:
    def test_published_default_epsilon(self) -> None:
        budget = DPBudget()
        assert budget.published == DEFAULT_METRIC_EPSILON
        assert budget.spent == 0.0

    def test_charge_accumulates_until_exhausted(self) -> None:
        """ε-spent tracks total-over-window; charging past the budget refuses."""
        budget = DPBudget(published=2.0)
        budget.charge("channel_slack_active", 1.0)
        assert budget.spent == 1.0
        budget.charge("channel_slack_active", 1.0)
        assert budget.spent == 2.0
        # The third charge would exceed published=2.0 → refuse THIS metric.
        with pytest.raises(DPBudgetExceededError) as exc:
            budget.charge("channel_slack_active", 1.0)
        assert "channel_slack_active" in str(exc.value)
        assert "exhausted" in str(exc.value)

    def test_window_reset_clears_spent(self) -> None:
        budget = DPBudget(published=1.0)
        budget.charge("enterprise_mode_active", 1.0)
        assert budget.spent == 1.0
        budget.reset()
        assert budget.spent == 0.0
        # After reset the metric can report again in the new window.
        budget.charge("enterprise_mode_active", 1.0)
        assert budget.spent == 1.0

    def test_exhausting_one_metric_drops_only_that_metric(self) -> None:
        """An exhausted metric is dropped; non-affected metrics report normally.

        Drive the REAL client pipeline: pre-spend one metric's budget to the
        ceiling, accrue two metrics, emit. The exhausted metric produces no
        share; the other does.
        """
        client = HeartbeatClient(
            consent_gate=OptOutConsentGate(granted=True),
            star_client=StarPrioClient(submitter_id="install-budget-test"),
        )
        # Pre-exhaust budget for one metric only.
        exhausted = client._budgets.setdefault("channel_discord_active", DPBudget())
        exhausted.charge("channel_discord_active", DEFAULT_METRIC_EPSILON)
        # Accrue both metrics.
        client.maybe_record_flag("channel_discord_active")
        client.maybe_record_flag("channel_whatsapp_active")
        shares = client.emit_weekly()
        emitted_metrics = {s.metric for s in shares}
        # The exhausted metric is dropped; the healthy metric reports.
        assert "channel_discord_active" not in emitted_metrics
        assert "channel_whatsapp_active" in emitted_metrics

    def test_each_metric_has_independent_budget(self) -> None:
        """Per-metric budgets are independent — one exhausted ≠ all exhausted."""
        client = HeartbeatClient(
            consent_gate=OptOutConsentGate(granted=True),
            star_client=StarPrioClient(submitter_id="install-indep"),
        )
        # Three distinct metrics accrued; none pre-exhausted.
        for flag in (
            "budget_monthly_exceeded_50pct",
            "budget_monthly_exceeded_80pct",
            "force_install_used_skill",
        ):
            client.maybe_record_flag(flag)
        shares = client.emit_weekly()
        assert {s.metric for s in shares} == {
            "budget_monthly_exceeded_50pct",
            "budget_monthly_exceeded_80pct",
            "force_install_used_skill",
        }
