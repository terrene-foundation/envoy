"""Tier-2: EnvoyGrantMomentRuntime M0→M4 with 5-minute timeout.

Per `specs/grant-moment.md` § State machine + § Timeout: M0 construct → M1
render → M2 await → M3 sign → M4 complete; default 5min M2 timeout raises
``GrantMomentExpiredError``. Per-request override is honored.

Wave-4 facade runtime-layer test per spec § Test location.
"""

from __future__ import annotations

import asyncio

import pytest

from envoy.grant_moment import (
    ApproveResolution,
    DeclineResolution,
    GrantMomentExpiredError,
    GrantMomentState,
    GrantMomentTimeoutError,
)
from tests.helpers.grant_moment_harness import (
    DEFAULT_PRINCIPAL_ID,
    _list_events,
    make_issue_kwargs,
    make_runtime,
)


@pytest.mark.asyncio
class TestM0Construct:
    async def test_issue_signs_request_and_emits_phase_a_ledger_entry(self) -> None:
        runtime, _km, _ledger, audit_store, adapters = await make_runtime()

        request = await runtime.issue_grant_moment(**make_issue_kwargs())

        assert request.signature_by_delegator_hex != ""
        assert request.nonce
        assert request.intent_id
        # Phase A ledger entry exists with the request's intent_id.
        events = await _list_events(audit_store)
        phase_a = [e for e in events if getattr(e, "action", "") == "PhaseARecord"]
        assert (
            phase_a
        ), f"expected PhaseARecord; got actions: {[getattr(e, 'action', '?') for e in events]}"
        # The intent_id from the request must back-link the Phase A row.
        env = phase_a[0].metadata["_envoy_envelope_v1"]
        assert env["intent_id"] == request.intent_id
        assert runtime.current_state(request.request_id) == GrantMomentState.M2_AWAIT
        # Adapter received the render call (M1 dispatch fired).
        assert len(adapters[0].renders) == 1

    async def test_issue_rejects_missing_delegation_key(self) -> None:
        # Constructor-time refusal — proven in tier-1 inspect; here we
        # verify the facade flags an invalid configuration before any
        # ledger writes happen.
        from envoy.grant_moment import ChannelHandoff, EnvoyGrantMomentRuntime, NoveltyClassifier
        from kailash.trust.key_manager import InMemoryKeyManager
        from tests.helpers.grant_moment_harness import (
            RecordingChannelAdapter,
            StubTrustRuntime,
            DEFAULT_DEVICE_ID,
        )

        km = InMemoryKeyManager()
        # NOTE: no key registered.
        adapter = RecordingChannelAdapter(channel_id="cli")
        handoff = ChannelHandoff(adapters=(adapter,), primary_channel_id="cli")

        class _DummyLedger:
            async def append(self, **_kw: object) -> str:
                return "ledger-stub"

        with pytest.raises(ValueError, match="delegation_key_id"):
            EnvoyGrantMomentRuntime(
                key_manager=km,
                delegation_key_id="missing-key",
                principal_id=DEFAULT_PRINCIPAL_ID,
                device_id=DEFAULT_DEVICE_ID,
                ledger=_DummyLedger(),
                channel_handoff=handoff,
                novelty_classifier=NoveltyClassifier(),
            )


@pytest.mark.asyncio
class TestM1Dispatch:
    async def test_render_propagates_to_all_active_channels_when_low_stakes(self) -> None:
        runtime, _km, _ledger, _audit, adapters = await make_runtime(
            primary_channel_id="cli", adapter_channel_ids=("cli", "web", "telegram")
        )
        request = await runtime.issue_grant_moment(**make_issue_kwargs())

        rendered_ids = [a.channel_id for a in adapters if a.renders]
        assert set(rendered_ids) == {
            "cli",
            "web",
            "telegram",
        }, f"expected all three channels rendered for low-stakes; got {rendered_ids}"
        assert runtime.current_state(request.request_id) == GrantMomentState.M2_AWAIT

    async def test_render_failure_on_every_channel_raises_timeout_error(self) -> None:
        runtime, _km, _ledger, _audit, adapters = await make_runtime(
            primary_channel_id="cli", adapter_channel_ids=("cli",)
        )
        adapters[0].raise_on_render = RuntimeError

        with pytest.raises(GrantMomentTimeoutError) as exc:
            await runtime.issue_grant_moment(**make_issue_kwargs())
        assert exc.value.channel_id == "cli"
        # Failed dispatch drops the in-flight tracking — no lingering state.
        assert runtime.inflight_count() == 0


@pytest.mark.asyncio
class TestM2Timeout:
    async def test_await_decision_raises_expired_when_timeout_elapses(self) -> None:
        runtime, *_ = await make_runtime(default_timeout_seconds=1)
        request = await runtime.issue_grant_moment(**make_issue_kwargs(timeout_seconds=1))

        with pytest.raises(GrantMomentExpiredError) as exc:
            await runtime.await_decision(request.request_id, timeout_seconds=0)
        assert exc.value.timeout_seconds == 0
        # After M2 expiry the in-flight tracking is gone.
        assert runtime.inflight_count() == 0

    async def test_await_decision_returns_resolution_when_post_decision_fires(self) -> None:
        runtime, *_ = await make_runtime()
        request = await runtime.issue_grant_moment(**make_issue_kwargs())

        approve = ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID)

        async def _post_after_short_delay() -> None:
            await asyncio.sleep(0.01)
            runtime.post_decision(request.request_id, approve)

        post_task = asyncio.create_task(_post_after_short_delay())
        result = await runtime.await_decision(request.request_id, timeout_seconds=5)
        await post_task
        assert result is approve


@pytest.mark.asyncio
class TestM3M4SignComplete:
    async def test_approve_path_emits_delegation_record_linked_to_phase_a(self) -> None:
        runtime, _km, _ledger, audit_store, _adapters = await make_runtime()
        request = await runtime.issue_grant_moment(**make_issue_kwargs())
        runtime.post_decision(
            request.request_id,
            ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID),
        )
        resolution = await runtime.await_decision(request.request_id, timeout_seconds=5)

        outcome = await runtime.submit_resolution(
            request_id=request.request_id,
            resolution=resolution,
            decided_on_channel_id="cli",
        )

        assert outcome.state == "APPROVED"
        assert outcome.result is not None
        assert outcome.result.decision == "approve_once"
        assert outcome.phase_a_record_ref
        assert outcome.delegation_record_ref
        # Per specs/ledger.md § grant_moment the Phase-B row is tagged
        # "grant_moment" (NOT "DelegationRecord" — that tag is reserved
        # for capability-delegation chains per trust-lineage.md).
        events = await _list_events(audit_store)
        grant_moment_rows = [e for e in events if getattr(e, "action", "") == "grant_moment"]
        assert grant_moment_rows, (
            f"expected grant_moment row; got actions: "
            f"{[getattr(e, 'action', '?') for e in events]}"
        )
        env = grant_moment_rows[0].metadata["_envoy_envelope_v1"]
        assert env["content"]["phase_a_ref"] == outcome.phase_a_record_ref
        # Spec § grant_moment canonical fields.
        for required in (
            "request_ref",
            "result_ref",
            "intent_id",
            "decision",
            "decided_at",
            "envelope_version_at_decision",
            "novelty_class",
            "signed_by",
        ):
            assert required in env["content"], f"grant_moment row missing {required!r}"

    async def test_decline_path_signs_only_ledger_entry(self) -> None:
        runtime, *_ = await make_runtime()
        request = await runtime.issue_grant_moment(**make_issue_kwargs())
        decline = DeclineResolution(
            decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID, reason="not now"
        )
        runtime.post_decision(request.request_id, decline)
        resolution = await runtime.await_decision(request.request_id, timeout_seconds=5)

        outcome = await runtime.submit_resolution(
            request_id=request.request_id,
            resolution=resolution,
            decided_on_channel_id="cli",
        )

        assert outcome.state == "DECLINED"
        assert outcome.result is not None
        assert outcome.result.decision == "deny"
        # Per signed_consent contract: Deny carries the DENY sentinel
        # (not a delegation_key signature) — wire-form check.
        assert outcome.result.signature_by_delegator_hex == "DENY_SIGNED_BY_LEDGER_ONLY"
        assert runtime.inflight_count() == 0
