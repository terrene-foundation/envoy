# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 — LedgerEmitter routes principal_id through the classification filter.

Design § 6.1 test 6, implementing `rules/event-payload-classification.md`
Rule 1 (single-point filter) + Rule 4 (Tier-2 exercises the redaction
end-to-end). The `budget_threshold_crossed` payload's `principal_id` MUST be
the post-`format_record_id_for_event` form; the raw in-memory principal value
MUST NOT appear anywhere in the emitted Ledger content.

Mirrors the `envoy.daily_digest.aggregator` redaction-site test: wrap the
module-level redactor with a spy to prove single-point routing, and assert the
redacted (sha256-shaped) value lands while the raw value does not.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

import envoy.budget.ledger_emitter as emitter_mod
from envoy.budget import EnvoyBudgetEvent, LedgerEmitter
from tests.helpers.budget_harness import build_ledger

_SINCE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_UNTIL = datetime(2027, 1, 1, tzinfo=timezone.utc)
_RAW_PRINCIPAL = "alice-secret-principal-id"


def _event() -> EnvoyBudgetEvent:
    return EnvoyBudgetEvent(
        principal_id=_RAW_PRINCIPAL,
        window="per_session",
        period_key="s1",
        threshold_pct=0.80,
        committed_microdollars=800_000,
        reserved_microdollars=0,
        allocated_microdollars=1_000_000,
        observed_at=datetime(2026, 5, 3, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
class TestClassifiedRedaction:
    async def test_principal_routed_through_redactor_and_raw_value_absent(self) -> None:
        ledger = await build_ledger()
        emitter = LedgerEmitter(ledger=ledger)

        calls: list[tuple] = []
        original = emitter_mod.format_record_id_for_event

        def _spy(policy, model_name, record_id, *a, **k):
            calls.append((model_name, record_id))
            # Simulate a classifying policy: return the sha256-prefixed form.
            return "sha256:" + "a" * 16

        emitter_mod.format_record_id_for_event = _spy
        try:
            emitter.enqueue_threshold_crossed(_event())
            await emitter.drain()
        finally:
            emitter_mod.format_record_id_for_event = original

        # Single-point routing: the principal_id went through the redactor with
        # the Principal model name.
        assert calls == [("Principal", _RAW_PRINCIPAL)]

        entries = await ledger.query(filter={}, since=_SINCE, until=_UNTIL)
        crossing = next(e for e in entries if e.type == "budget_threshold_crossed")
        # Redacted form landed; raw principal value absent from the whole payload.
        assert crossing.content["principal_id"] == "sha256:" + "a" * 16
        assert _RAW_PRINCIPAL not in repr(crossing.content)

    async def test_phase01_no_policy_passes_value_through(self) -> None:
        # With no classification policy (Phase-01 default) the helper passes the
        # value through — documented narrow scope, same as envoy.daily_digest.
        ledger = await build_ledger()
        emitter = LedgerEmitter(ledger=ledger, classification_policy=None)
        emitter.enqueue_threshold_crossed(_event())
        await emitter.drain()
        entries = await ledger.query(filter={}, since=_SINCE, until=_UNTIL)
        crossing = next(e for e in entries if e.type == "budget_threshold_crossed")
        assert crossing.content["principal_id"] == _RAW_PRINCIPAL
