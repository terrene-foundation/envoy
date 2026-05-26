"""Tier 2 (NO LLM): BET12TelemetryHook per-state latency + EC-1 duration.

Source: shard 8 § 6.1 row "test_boundary_conversation_bet12_latency_telemetry"
+ § 3.4 (per-step latency budget) + § 5.4 (BET-12 measurement hook).

Drives the telemetry hook directly against a REAL EnvoyLedger (real Ed25519
sign, real InMemoryAuditStore chain-integrity) — NO LLM, NO conversation. The
``envoy_ledger`` / ``audit_store`` fixtures come from tests/tier2/conftest.py.

Asserts:

1. Per-state telemetry rows land in the Ledger (state_entered +
   state_completed) and the chain verifies.
2. The conversation_completed summary records the EC-1 duration boundary
   verdict (``within_ec1_budget``) — both the within-budget and the
   over-budget cases.
3. Negative latency / retry / duration raise (no silent coercion).

Per `rules/testing.md` Tier 2: real Ledger, NO mocking. Per
`rules/probe-driven-verification.md` MUST-3: structural assertions
(entry-type membership, content-field equality, chain-verify boolean).
"""

from __future__ import annotations

import pytest
from kailash.trust.audit_store import AuditFilter, InMemoryAuditStore

from envoy.boundary_conversation.bet12_telemetry import (
    EC1_MAX_DURATION_SECONDS,
    BET12TelemetryHook,
)
from envoy.ledger import EnvoyLedger

# Sentinel key the EnvoyLedger stores the full envoy envelope under (per
# envoy/ledger/facade.py::_ENVELOPE_METADATA_KEY).
_ENVELOPE_KEY = "_envoy_envelope_v1"

RITUAL = "ritual-bet12"
_STATES = ("S1_money", "S2_people", "S3_topics", "S4_hours", "S5_first_task")


async def _entry_types(audit_store: InMemoryAuditStore) -> list[str]:
    """Return the envoy entry `type` field for every appended event, in order."""
    events = await audit_store.query(AuditFilter(limit=1_000_000))
    envelopes = [e.metadata[_ENVELOPE_KEY] for e in events if _ENVELOPE_KEY in (e.metadata or {})]
    envelopes.sort(key=lambda env: env["sequence"])
    return [env["type"] for env in envelopes]


async def _entry_contents(audit_store: InMemoryAuditStore) -> list[dict]:
    events = await audit_store.query(AuditFilter(limit=1_000_000))
    envelopes = [e.metadata[_ENVELOPE_KEY] for e in events if _ENVELOPE_KEY in (e.metadata or {})]
    envelopes.sort(key=lambda env: env["sequence"])
    return [env["content"] for env in envelopes]


class TestPerStateTelemetry:
    async def test_state_entered_and_completed_land_in_ledger(
        self, envoy_ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """Each state emits an entered + completed row; the chain verifies."""
        hook = BET12TelemetryHook(ledger=envoy_ledger)
        for i, state in enumerate(_STATES):
            await hook.state_entered(RITUAL, state)
            await hook.state_completed(RITUAL, state, latency_ms=1200 + i, retry_count=0)

        types = await _entry_types(audit_store)
        entered = [t for t in types if t == "boundary_conversation_state_entered"]
        completed = [t for t in types if t == "boundary_conversation_state_completed"]
        assert len(entered) == len(_STATES)
        assert len(completed) == len(_STATES)

        report = await envoy_ledger.verify_chain()
        assert report.success is True
        assert report.entries_verified == 2 * len(_STATES)

    async def test_completed_row_carries_latency_and_retry(
        self, envoy_ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """The completed row records latency_ms + retry_count + state — never
        the user's answer (privacy)."""
        hook = BET12TelemetryHook(ledger=envoy_ledger)
        await hook.state_completed(RITUAL, "S3_topics", latency_ms=4200, retry_count=2)
        contents = await _entry_contents(audit_store)
        row = next(c for c in contents if c.get("state") == "S3_topics")
        assert row["latency_ms"] == 4200
        assert row["retry_count"] == 2
        assert row["ritual_id"] == RITUAL
        # Privacy: no answer / phrase / extracted PII fields.
        assert set(row.keys()) == {"ritual_id", "state", "latency_ms", "retry_count"}

    async def test_negative_measurements_raise(self, envoy_ledger: EnvoyLedger) -> None:
        hook = BET12TelemetryHook(ledger=envoy_ledger)
        with pytest.raises(ValueError):
            await hook.state_completed(RITUAL, "S1_money", latency_ms=-1, retry_count=0)
        with pytest.raises(ValueError):
            await hook.state_completed(RITUAL, "S1_money", latency_ms=0, retry_count=-1)


class TestConversationDurationBoundary:
    async def test_within_budget_records_true(
        self, envoy_ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """A 12-minute conversation is within the 25-minute EC-1 budget."""
        hook = BET12TelemetryHook(ledger=envoy_ledger)
        await hook.conversation_completed(RITUAL, total_duration_seconds=12 * 60)
        contents = await _entry_contents(audit_store)
        summary = next(
            c for c in contents if "total_duration_seconds" in c and "within_ec1_budget" in c
        )
        assert summary["total_duration_seconds"] == 12 * 60
        assert summary["within_ec1_budget"] is True

    async def test_at_exact_boundary_records_true(
        self, envoy_ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """Exactly 25 minutes is within budget (<=, not <)."""
        hook = BET12TelemetryHook(ledger=envoy_ledger)
        await hook.conversation_completed(RITUAL, total_duration_seconds=EC1_MAX_DURATION_SECONDS)
        summary = (await _entry_contents(audit_store))[-1]
        assert summary["within_ec1_budget"] is True

    async def test_over_budget_records_false_without_raising(
        self, envoy_ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """A 30-minute conversation breaches EC-1: recorded False, no raise (the
        telemetry records reality; the acceptance gate adjudicates)."""
        hook = BET12TelemetryHook(ledger=envoy_ledger)
        await hook.conversation_completed(RITUAL, total_duration_seconds=30 * 60)
        summary = (await _entry_contents(audit_store))[-1]
        assert summary["within_ec1_budget"] is False
        assert summary["total_duration_seconds"] == 30 * 60

    async def test_negative_duration_raises(self, envoy_ledger: EnvoyLedger) -> None:
        hook = BET12TelemetryHook(ledger=envoy_ledger)
        with pytest.raises(ValueError):
            await hook.conversation_completed(RITUAL, total_duration_seconds=-5)
