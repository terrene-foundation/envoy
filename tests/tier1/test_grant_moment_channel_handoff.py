"""Tier 1 unit tests for envoy.grant_moment.channel_handoff.

Per `rules/testing.md` § Tier 1: mocking allowed, <1s per test. Stub
channel adapters defined inline (no real channel transports). The
project's pytest-asyncio runs in ``asyncio_mode = auto`` (see root
pyproject.toml), so ``async def test_...`` functions execute without
``@pytest.mark.asyncio``.

Covers `specs/grant-moment.md` § Rendering + § Novelty-aware friction
invariants for T-03-51:
- empty adapters → ValueError (cannot deliver to zero channels).
- primary_channel_id absent from adapters → ValueError.
- low-stakes dispatch hits ALL adapters in primary-first order.
- high_stakes=True → primary-only; siblings refused with
  not_primary_for_high_stakes.
- request.primary_only=True (low-stakes) → primary-only; siblings
  refused with not_primary_for_primary_only.
- sibling raising during render → captured as render_failed:<Type>;
  remaining siblings still dispatched.
- primary raising during render → does NOT short-circuit siblings;
  primary refusal recorded + siblings still get the dispatch.
"""

from __future__ import annotations

import pytest

from envoy.grant_moment.channel_handoff import (
    ChannelHandoff,
    HandoffPlan,
)
from envoy.grant_moment.signed_consent import (
    ConsequencePreview,
    GrantMomentRequest,
)

# ---------------------------------------------------------------------------
# Stub channel adapter — records dispatch calls; can be configured to raise
# ---------------------------------------------------------------------------


class _StubChannelAdapter:
    """Inline stub satisfying ChannelAdapterProtocol.

    Records every dispatched request so tests can assert call order and
    primary-binding refusals. The ``raise_with`` constructor arg makes
    the adapter raise an arbitrary exception type on render — used to
    exercise the capture-and-continue contract.
    """

    def __init__(self, channel_id: str, *, raise_with: type[Exception] | None = None) -> None:
        self.channel_id = channel_id
        self.calls: list[GrantMomentRequest] = []
        self._raise_with = raise_with

    async def render_grant_moment(
        self, request: GrantMomentRequest, *, visible_secret: object = None
    ) -> None:
        self.calls.append(request)
        if self._raise_with is not None:
            raise self._raise_with("simulated render failure")


def _make_request(*, primary_only: bool = False) -> GrantMomentRequest:
    """Construct a baseline GrantMomentRequest the dispatcher relays."""
    return GrantMomentRequest(
        request_id="req-001",
        session_id="sess-abc",
        principal_genesis_id="principal-jane",
        envelope_id="env-abc-123",
        envelope_version=1,
        envelope_hash="sha256:" + ("0" * 64),
        intent_id="intent-xyz",
        nonce="nonce-deadbeef",
        tool_name="send_email",
        tool_args_canonical={"to": "alice@example.com"},
        tool_args_canonical_hash="sha256:" + ("1" * 64),
        why_asking="envelope_violation",
        consequence_preview=ConsequencePreview(
            budget_microdollars=1000,
            reversibility="reversible",
            recipient="alice@example.com",
            data_classification="Internal",
        ),
        novelty_class="familiar_repeat",
        primary_only=primary_only,
        timeout_seconds=300,
        issued_at="2026-05-26T00:00:00Z",
        delegation_key_pubkey_hex="ab" * 32,
    )


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


class TestConstructorValidation:
    """ChannelHandoff refuses misconfigured adapter sets with plain-language errors."""

    def test_empty_adapters_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="at least one channel adapter required"):
            ChannelHandoff(adapters=(), primary_channel_id="cli")

    def test_primary_channel_id_not_in_adapters_raises_value_error(self) -> None:
        adapter = _StubChannelAdapter("web")
        with pytest.raises(ValueError, match="primary_channel_id 'cli' not in adapters"):
            ChannelHandoff(adapters=(adapter,), primary_channel_id="cli")

    def test_primary_channel_id_present_in_single_adapter_is_ok(self) -> None:
        adapter = _StubChannelAdapter("cli")
        handoff = ChannelHandoff(adapters=(adapter,), primary_channel_id="cli")
        # No raise; object constructed successfully.
        assert handoff is not None


# ---------------------------------------------------------------------------
# Low-stakes dispatch (all adapters, primary-first order)
# ---------------------------------------------------------------------------


class TestLowStakesDispatch:
    """All adapters dispatched; primary first, then siblings in adapter order."""

    async def test_low_stakes_hits_all_adapters_in_primary_first_order(self) -> None:
        primary = _StubChannelAdapter("cli")
        sibling_a = _StubChannelAdapter("web")
        sibling_b = _StubChannelAdapter("telegram")
        # Note: primary listed SECOND in adapters to confirm reordering logic.
        handoff = ChannelHandoff(
            adapters=(sibling_a, primary, sibling_b),
            primary_channel_id="cli",
        )
        plan = await handoff.dispatch(request=_make_request(), high_stakes=False)

        assert isinstance(plan, HandoffPlan)
        assert plan.request_id == "req-001"
        assert plan.channels_dispatched == ("cli", "web", "telegram")
        assert plan.refused_channels == ()
        # Every adapter saw the request exactly once.
        assert len(primary.calls) == 1
        assert len(sibling_a.calls) == 1
        assert len(sibling_b.calls) == 1


# ---------------------------------------------------------------------------
# High-stakes dispatch (primary only)
# ---------------------------------------------------------------------------


class TestHighStakesPrimaryBinding:
    """high_stakes=True → primary only; siblings refused with the named reason."""

    async def test_high_stakes_dispatches_only_to_primary(self) -> None:
        primary = _StubChannelAdapter("cli")
        sibling_a = _StubChannelAdapter("web")
        sibling_b = _StubChannelAdapter("telegram")
        handoff = ChannelHandoff(
            adapters=(primary, sibling_a, sibling_b),
            primary_channel_id="cli",
        )
        plan = await handoff.dispatch(request=_make_request(), high_stakes=True)

        assert plan.channels_dispatched == ("cli",)
        assert set(plan.refused_channels) == {
            ("web", "not_primary_for_high_stakes"),
            ("telegram", "not_primary_for_high_stakes"),
        }
        assert len(primary.calls) == 1
        assert len(sibling_a.calls) == 0
        assert len(sibling_b.calls) == 0


# ---------------------------------------------------------------------------
# request.primary_only=True (low-stakes) → primary only with distinct reason
# ---------------------------------------------------------------------------


class TestPrimaryOnlyRequestRouting:
    """primary_only=True (low_stakes=False) routes only to primary."""

    async def test_primary_only_request_dispatches_only_to_primary(self) -> None:
        primary = _StubChannelAdapter("cli")
        sibling = _StubChannelAdapter("web")
        handoff = ChannelHandoff(
            adapters=(primary, sibling),
            primary_channel_id="cli",
        )
        plan = await handoff.dispatch(
            request=_make_request(primary_only=True),
            high_stakes=False,
        )

        assert plan.channels_dispatched == ("cli",)
        assert plan.refused_channels == (("web", "not_primary_for_primary_only"),)
        assert len(primary.calls) == 1
        assert len(sibling.calls) == 0

    async def test_high_stakes_reason_takes_precedence_when_both_set(self) -> None:
        """high_stakes=True AND primary_only=True → refusal reason is high_stakes."""
        primary = _StubChannelAdapter("cli")
        sibling = _StubChannelAdapter("web")
        handoff = ChannelHandoff(
            adapters=(primary, sibling),
            primary_channel_id="cli",
        )
        plan = await handoff.dispatch(
            request=_make_request(primary_only=True),
            high_stakes=True,
        )
        assert plan.refused_channels == (("web", "not_primary_for_high_stakes"),)


# ---------------------------------------------------------------------------
# Adapter render failure capture
# ---------------------------------------------------------------------------


class TestAdapterRenderFailureCapture:
    """Adapter raise during render is captured; dispatch continues."""

    async def test_sibling_raise_is_captured_other_adapters_still_get_dispatch(
        self,
    ) -> None:
        primary = _StubChannelAdapter("cli")
        broken = _StubChannelAdapter("web", raise_with=RuntimeError)
        healthy = _StubChannelAdapter("telegram")
        handoff = ChannelHandoff(
            adapters=(primary, broken, healthy),
            primary_channel_id="cli",
        )
        plan = await handoff.dispatch(request=_make_request(), high_stakes=False)

        assert plan.channels_dispatched == ("cli", "telegram")
        assert plan.refused_channels == (("web", "render_failed: RuntimeError"),)
        # The healthy sibling DID receive the request even though the
        # earlier sibling raised.
        assert len(primary.calls) == 1
        assert len(broken.calls) == 1  # render_grant_moment was entered before the raise
        assert len(healthy.calls) == 1

    async def test_primary_raise_does_not_short_circuit_siblings(self) -> None:
        broken_primary = _StubChannelAdapter("cli", raise_with=ConnectionError)
        sibling_a = _StubChannelAdapter("web")
        sibling_b = _StubChannelAdapter("telegram")
        handoff = ChannelHandoff(
            adapters=(broken_primary, sibling_a, sibling_b),
            primary_channel_id="cli",
        )
        plan = await handoff.dispatch(request=_make_request(), high_stakes=False)

        # Primary failed → recorded in refused; siblings still dispatched.
        assert plan.channels_dispatched == ("web", "telegram")
        assert plan.refused_channels == (("cli", "render_failed: ConnectionError"),)
        assert len(sibling_a.calls) == 1
        assert len(sibling_b.calls) == 1

    async def test_capture_records_exception_type_name_not_message(self) -> None:
        """Per rules/security.md: refusal reason carries type name, not str(exc)."""

        class _ConfidentialError(Exception):
            """An exception whose message could carry sensitive transport state."""

        primary = _StubChannelAdapter("cli")
        broken = _StubChannelAdapter("web", raise_with=_ConfidentialError)
        handoff = ChannelHandoff(
            adapters=(primary, broken),
            primary_channel_id="cli",
        )
        plan = await handoff.dispatch(request=_make_request(), high_stakes=False)

        refused_reasons = [reason for (_cid, reason) in plan.refused_channels]
        assert refused_reasons == ["render_failed: _ConfidentialError"]
        # The simulated message MUST NOT appear in the refusal reason.
        assert "simulated render failure" not in refused_reasons[0]


# ---------------------------------------------------------------------------
# HandoffPlan shape invariants
# ---------------------------------------------------------------------------


class TestHandoffPlanShape:
    """HandoffPlan is a frozen dataclass; request_id round-trips from request."""

    async def test_handoff_plan_request_id_matches_request(self) -> None:
        primary = _StubChannelAdapter("cli")
        handoff = ChannelHandoff(adapters=(primary,), primary_channel_id="cli")
        plan = await handoff.dispatch(request=_make_request(), high_stakes=False)
        assert plan.request_id == "req-001"

    async def test_channels_dispatched_is_a_tuple(self) -> None:
        primary = _StubChannelAdapter("cli")
        handoff = ChannelHandoff(adapters=(primary,), primary_channel_id="cli")
        plan = await handoff.dispatch(request=_make_request(), high_stakes=False)
        assert isinstance(plan.channels_dispatched, tuple)
        assert isinstance(plan.refused_channels, tuple)
