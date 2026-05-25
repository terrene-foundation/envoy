"""Tier 2 wiring: TokenBudgetFilter truncation emits a Ledger entry.

T-01-23 per shard 13 § 6.1 row 8 + `specs/model-adapter.md` line 41
(Stage 1 token-budget check) + spec § Error taxonomy line 68 +
shard 13 § 3.6 (Stage 1 only — Stages 2-4 are Phase 04).

Per `rules/testing.md` Tier 2: NO mocking. Real EnvoyLedger over real
InMemoryAuditStore + real Ed25519 sign. Per
`rules/orphan-detection.md` Rule 1: this test IS the hot-path call
site for `TokenBudgetFilter.check()`.

Verifies the T-094 defense surface (spec § Response filter line 41):
oversized responses MUST truncate with sentinel AND emit a
`model_response_filter_token_budget` Ledger entry per shard 13 § 5.6
(Ledger entry classes).
"""

from __future__ import annotations

import pytest
from kailash.trust.audit_store import AuditFilter, InMemoryAuditStore

from envoy.ledger import EnvoyLedger
from envoy.model import (
    TRUNCATION_SENTINEL,
    ResponseTokenBudgetExceededError,
    TokenBudgetFilter,
)


@pytest.fixture
def filter_under_test(envoy_ledger: EnvoyLedger) -> TokenBudgetFilter:
    return TokenBudgetFilter(envoy_ledger)


class TestUnderBudget:
    """Under-budget responses pass through unchanged; no Ledger entry."""

    async def test_under_budget_passes_through_unchanged(
        self,
        filter_under_test: TokenBudgetFilter,
        audit_store: InMemoryAuditStore,
    ) -> None:
        payload = b"hello model response under budget"
        result = await filter_under_test.check(
            payload, tool_output_budget_bytes=10_000, action_id="action-under"
        )
        assert result == payload
        events = await audit_store.query(AuditFilter())
        assert events == [], "no Ledger entry under budget"


class TestOverBudgetTruncate:
    """Over-budget responses truncate WITH sentinel + emit Ledger entry."""

    async def test_over_budget_truncates_with_sentinel(
        self,
        filter_under_test: TokenBudgetFilter,
        audit_store: InMemoryAuditStore,
    ) -> None:
        # 5_000-byte payload, 1_000-byte budget — truncates.
        payload = b"x" * 5_000
        result = await filter_under_test.check(
            payload,
            tool_output_budget_bytes=1_000,
            action_id="action-over-allowed",
        )
        # Truncated AND carries the sentinel marker — distinguishable
        # from successful-pass per `rules/observability.md` Rule 6.1.
        assert len(result) <= 1_000
        assert TRUNCATION_SENTINEL in result

        # Ledger entry emitted per shard 13 § 5.6.
        events = await audit_store.query(AuditFilter())
        assert len(events) == 1, "truncation MUST emit one Ledger entry"
        ev = events[0]
        # `entry_type` lives on the AuditEvent's `action` field AND on
        # the canonical envelope's `type` field (per T-01-18 facade).
        assert ev.action == "model_response_filter_token_budget"
        envelope = (ev.metadata or {}).get("_envoy_envelope_v1", {})
        assert envelope.get("type") == "model_response_filter_token_budget"
        content = envelope.get("content", {})
        assert content.get("action_id") == "action-over-allowed"

    async def test_downstream_blocked_raises_typed_error(
        self,
        filter_under_test: TokenBudgetFilter,
        audit_store: InMemoryAuditStore,
    ) -> None:
        """Per spec line 68: if downstream consumption is forbidden by
        the envelope, raise ResponseTokenBudgetExceededError."""
        with pytest.raises(ResponseTokenBudgetExceededError):
            await filter_under_test.check(
                b"y" * 9_000,
                tool_output_budget_bytes=512,
                action_id="action-over-blocked",
                downstream_consumption_allowed=False,
            )

        # Even on raise, the Ledger entry MUST still be emitted —
        # the audit trail is the structural defense per
        # `rules/observability.md` Rule 7 (partial failures WARN).
        events = await audit_store.query(AuditFilter())
        assert len(events) == 1
        assert events[0].action == "model_response_filter_token_budget"


class TestBoundaryConditions:
    """Boundary: exact-budget passes; one-byte-over truncates."""

    async def test_exact_budget_passes(self, filter_under_test: TokenBudgetFilter) -> None:
        payload = b"a" * 256
        result = await filter_under_test.check(
            payload, tool_output_budget_bytes=256, action_id="action-exact"
        )
        assert result == payload

    async def test_one_byte_over_truncates(
        self,
        filter_under_test: TokenBudgetFilter,
        audit_store: InMemoryAuditStore,
    ) -> None:
        payload = b"b" * 257
        result = await filter_under_test.check(
            payload, tool_output_budget_bytes=256, action_id="action-one-over"
        )
        assert len(result) <= 256
        assert TRUNCATION_SENTINEL in result
        events = await audit_store.query(AuditFilter())
        assert len(events) == 1
