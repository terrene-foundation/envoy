"""Tier 1: T-01-22 — TokenBudgetFilter (Stage 1 of the 4-stage response
filter pipeline).

Source: T-01-22 per shard 13 § 3.4 + spec `specs/model-adapter.md` §
Response filter (lines 39-47) + § Error taxonomy line 68. Stage 1 only;
Stages 2-4 are spec-acknowledged Phase 04 deferrals per shard 13 § 3.4.

Capacity coverage (6 invariants):

1. Within-budget responses pass through unchanged.
2. Over-budget + downstream_consumption_allowed=True → truncated bytes
   with the public sentinel suffix.
3. Over-budget + downstream_consumption_allowed=False → raises
   ResponseTokenBudgetExceededError per spec line 68.
4. Ledger entry emitted on every truncation (audit trail even when the
   downstream-blocked path raises).
5. Non-positive budget raises ValueError (fail-loud guard per
   rules/zero-tolerance.md Rule 3a).
6. Truncated payload length is exactly the budget (sentinel fits within).

Per `rules/testing.md` Tier 1: real EnvoyLedger via InMemoryAuditStore +
InMemoryKeyManager (kailash's Phase 01 zero-dep test fixtures).
"""

from __future__ import annotations

import pytest
from kailash.trust.audit_store import InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.ledger import EnvoyLedger
from envoy.model import (
    TRUNCATION_SENTINEL,
    ResponseTokenBudgetExceededError,
    TokenBudgetFilter,
)

VALID_ALGO_ID = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}
DEVICE_ID = "device-tbf-22"
SIGNING_KEY_ID = "envoy-tbf-key"


@pytest.fixture
async def keymgr() -> InMemoryKeyManager:
    mgr = InMemoryKeyManager()
    await mgr.generate_keypair(SIGNING_KEY_ID)
    return mgr


@pytest.fixture
def audit_store() -> InMemoryAuditStore:
    return InMemoryAuditStore()


@pytest.fixture
async def ledger(audit_store: InMemoryAuditStore, keymgr: InMemoryKeyManager) -> EnvoyLedger:
    return EnvoyLedger(
        audit_store=audit_store,
        key_manager=keymgr,
        signing_key_id=SIGNING_KEY_ID,
        device_id=DEVICE_ID,
        algorithm_identifier=VALID_ALGO_ID,
    )


class TestWithinBudgetPassThrough:
    """Invariant 1: response within budget returns unchanged."""

    async def test_under_budget_returns_unchanged(self, ledger: EnvoyLedger) -> None:
        filter_ = TokenBudgetFilter(ledger=ledger)
        response = b"short response under budget"
        result = await filter_.check(
            response,
            tool_output_budget_bytes=4096,
            action_id="action-tbf-1",
        )
        assert result == response

    async def test_exactly_at_budget_returns_unchanged(self, ledger: EnvoyLedger) -> None:
        """Boundary check: response of exactly N bytes against budget=N
        is within-budget (the spec mandate is ``≤`` per line 41)."""
        filter_ = TokenBudgetFilter(ledger=ledger)
        response = b"x" * 100
        result = await filter_.check(
            response,
            tool_output_budget_bytes=100,
            action_id="action-tbf-boundary",
        )
        assert result == response


class TestOverBudgetTruncation:
    """Invariants 2 + 6: over-budget responses are truncated + the
    sentinel is appended."""

    async def test_over_budget_truncates_with_sentinel(self, ledger: EnvoyLedger) -> None:
        filter_ = TokenBudgetFilter(ledger=ledger)
        response = b"x" * 10000  # well over budget
        budget = 1024
        result = await filter_.check(
            response,
            tool_output_budget_bytes=budget,
            action_id="action-tbf-truncate",
            downstream_consumption_allowed=True,
        )
        # The result MUST be exactly the budget length (head + sentinel
        # combined fit within the budget per the implementation).
        assert len(result) == budget
        # The sentinel MUST be present at the end (grep-able per
        # rules/observability.md Rule 6.2).
        assert result.endswith(TRUNCATION_SENTINEL)

    async def test_truncated_payload_preserves_head_bytes(self, ledger: EnvoyLedger) -> None:
        """The truncated payload starts with the original response's
        head bytes (so downstream consumers see the actual model
        output up to the cut)."""
        filter_ = TokenBudgetFilter(ledger=ledger)
        response = b"<head>" + (b"x" * 10000) + b"<tail>"
        budget = 512
        result = await filter_.check(
            response,
            tool_output_budget_bytes=budget,
            action_id="action-tbf-head",
            downstream_consumption_allowed=True,
        )
        assert result.startswith(b"<head>")
        assert result.endswith(TRUNCATION_SENTINEL)
        assert b"<tail>" not in result


class TestDownstreamConsumptionForbidden:
    """Invariant 3: over-budget + downstream_consumption_allowed=False
    raises ResponseTokenBudgetExceededError per spec line 68."""

    async def test_over_budget_raises_when_consumption_forbidden(self, ledger: EnvoyLedger) -> None:
        filter_ = TokenBudgetFilter(ledger=ledger)
        response = b"x" * 10000
        with pytest.raises(ResponseTokenBudgetExceededError) as exc:
            await filter_.check(
                response,
                tool_output_budget_bytes=512,
                action_id="action-tbf-forbid",
                downstream_consumption_allowed=False,
            )
        # Error MUST name the actual + budget bytes per the typed-
        # error contract.
        assert "10000" in str(exc.value)
        assert "512" in str(exc.value)

    async def test_within_budget_does_not_raise_when_forbidden(self, ledger: EnvoyLedger) -> None:
        """downstream_consumption_allowed only fires on EXCEED — the
        flag is a no-op when the response is within budget."""
        filter_ = TokenBudgetFilter(ledger=ledger)
        response = b"short"
        result = await filter_.check(
            response,
            tool_output_budget_bytes=1024,
            action_id="action-tbf-noop",
            downstream_consumption_allowed=False,
        )
        assert result == response


class TestLedgerEmission:
    """Invariant 4: every truncation emits a model_response_filter_token_
    budget Ledger entry, even when the consumption-blocked path raises."""

    async def test_truncation_emits_ledger_entry_with_action_id(
        self, ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        filter_ = TokenBudgetFilter(ledger=ledger)
        before_count = audit_store.count
        await filter_.check(
            b"x" * 10000,
            tool_output_budget_bytes=1024,
            action_id="action-tbf-emit",
            downstream_consumption_allowed=True,
        )
        after_count = audit_store.count
        # Exactly one new entry was emitted (the
        # model_response_filter_token_budget audit row).
        assert after_count == before_count + 1

    async def test_forbidden_path_emits_ledger_before_raising(
        self, ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """The audit trail MUST exist even when the consumption-blocked
        path raises — the Ledger emit lands FIRST so the audit row
        records the event regardless of caller behavior."""
        filter_ = TokenBudgetFilter(ledger=ledger)
        before_count = audit_store.count
        with pytest.raises(ResponseTokenBudgetExceededError):
            await filter_.check(
                b"x" * 10000,
                tool_output_budget_bytes=512,
                action_id="action-tbf-raise-emit",
                downstream_consumption_allowed=False,
            )
        after_count = audit_store.count
        assert after_count == before_count + 1

    async def test_within_budget_emits_no_ledger_entry(
        self, ledger: EnvoyLedger, audit_store: InMemoryAuditStore
    ) -> None:
        """Stage 1 only audits truncations — the within-budget happy
        path should NOT spam the audit store with a row per response."""
        filter_ = TokenBudgetFilter(ledger=ledger)
        before_count = audit_store.count
        await filter_.check(
            b"short",
            tool_output_budget_bytes=1024,
            action_id="action-tbf-noemit",
        )
        after_count = audit_store.count
        assert after_count == before_count


class TestBudgetGuard:
    """Invariant 5: non-positive budget raises ValueError per
    rules/zero-tolerance.md Rule 3a (fail-loud structural guard)."""

    async def test_zero_budget_raises_value_error(self, ledger: EnvoyLedger) -> None:
        filter_ = TokenBudgetFilter(ledger=ledger)
        with pytest.raises(ValueError) as exc:
            await filter_.check(
                b"x",
                tool_output_budget_bytes=0,
                action_id="action-tbf-zero",
            )
        assert "tool_output_budget_bytes" in str(exc.value)

    async def test_negative_budget_raises_value_error(self, ledger: EnvoyLedger) -> None:
        filter_ = TokenBudgetFilter(ledger=ledger)
        with pytest.raises(ValueError):
            await filter_.check(
                b"x",
                tool_output_budget_bytes=-1,
                action_id="action-tbf-neg",
            )


class TestSentinelContract:
    """The public TRUNCATION_SENTINEL is part of the spec contract
    (downstream consumers grep for it per rules/observability.md Rule
    6.2 uniform mask form). Pin the bytes so a rename surfaces as a
    test failure."""

    def test_sentinel_is_grep_able_token(self) -> None:
        assert TRUNCATION_SENTINEL == b"\n<!-- ENVOY_TRUNCATED_T094 -->"

    def test_sentinel_is_ascii_safe(self) -> None:
        # Decoding to ASCII MUST succeed — log emitters serialize the
        # sentinel as a string in the Ledger entry's `content` dict.
        decoded = TRUNCATION_SENTINEL.decode("ascii")
        assert "ENVOY_TRUNCATED_T094" in decoded
