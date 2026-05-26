"""E2E EC-2 acceptance: 3 resolution shapes + cascade revocation.

Per `briefs/00-phase-01-mvp-scope.md` § Exit criteria + `02-plans/02-test-strategy.md`:
EC-2 is "3 Grant Moments triggered and resolved correctly". The Wave-4
facade MUST drive all three resolution shapes (Approve / Decline /
ApproveWithModification) end-to-end AND demonstrate the cascade revocation
surface (EC-8 anchor): a previously-approved Grant Moment can be
retroactively revoked and the cascade reaches every expected descendant.

This is the T-03-55 acceptance gate per
`workspaces/phase-01-mvp/todos/active/03-wave-3-grant-moment-budget.md`.
"""

from __future__ import annotations

import pytest

from envoy.grant_moment import (
    ApproveResolution,
    ApproveWithModificationResolution,
    CascadeIncompleteError,
    DeclineResolution,
    GrantMomentOutcome,
)
from tests.helpers.grant_moment_harness import (
    DEFAULT_PRINCIPAL_ID,
    make_issue_kwargs,
    make_runtime,
)


async def _run_one_lifecycle(runtime, *, resolution_kind: str) -> GrantMomentOutcome:
    request = await runtime.issue_grant_moment(**make_issue_kwargs())
    if resolution_kind == "approve":
        resolution = ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID)
    elif resolution_kind == "approve_and_author":
        resolution = ApproveResolution(
            decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID,
            author_payload={
                "new_constraint": {"rule": "no-after-hours-send"},
                "novelty_check_passed": True,
                "minimum_impact_passed": True,
            },
        )
    elif resolution_kind == "decline":
        resolution = DeclineResolution(
            decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID, reason="not now"
        )
    elif resolution_kind == "modify":
        resolution = ApproveWithModificationResolution(
            decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID,
            modify_payload={
                "new_args_canonical": {"to": "approved-recipient@example.com"},
                "new_args_canonical_hash": "sha256:modified-args",
            },
        )
    else:
        raise ValueError(f"unknown resolution_kind: {resolution_kind!r}")

    runtime.post_decision(request.request_id, resolution)
    received = await runtime.await_decision(request.request_id, timeout_seconds=5)
    return await runtime.submit_resolution(
        request_id=request.request_id,
        resolution=received,
        decided_on_channel_id="cli",
    )


@pytest.mark.asyncio
class TestEC2ThreeResolutionShapes:
    """EC-2 acceptance: 3 resolution shapes (Approve / Decline / Modify)
    execute end-to-end through the runtime facade.
    """

    async def test_approve_once_path_completes_with_signed_delegation_record(self) -> None:
        runtime, *_ = await make_runtime(novelty_read_delay_seconds=0.0)
        outcome = await _run_one_lifecycle(runtime, resolution_kind="approve")

        assert outcome.state == "APPROVED"
        assert outcome.result is not None
        assert outcome.result.decision == "approve_once"
        assert outcome.result.signature_by_delegator_hex  # signed
        assert outcome.delegation_record_ref
        assert outcome.phase_a_record_ref

    async def test_approve_and_author_path_carries_author_payload(self) -> None:
        runtime, *_ = await make_runtime(novelty_read_delay_seconds=0.0)
        outcome = await _run_one_lifecycle(runtime, resolution_kind="approve_and_author")

        assert outcome.state == "APPROVED"
        assert outcome.result is not None
        assert outcome.result.decision == "approve_and_author"
        # Author payload propagated to the signed Result.
        assert outcome.result.author_payload["new_constraint"] == {"rule": "no-after-hours-send"}
        assert outcome.result.author_payload["novelty_check_passed"] is True

    async def test_decline_path_emits_signed_ledger_only(self) -> None:
        runtime, *_ = await make_runtime(novelty_read_delay_seconds=0.0)
        outcome = await _run_one_lifecycle(runtime, resolution_kind="decline")

        assert outcome.state == "DECLINED"
        assert outcome.result is not None
        assert outcome.result.decision == "deny"
        # Spec § GrantMomentResult: Deny carries the sentinel, not a
        # delegation-key signature.
        assert outcome.result.signature_by_delegator_hex == "DENY_SIGNED_BY_LEDGER_ONLY"
        # But the Ledger row IS signed — the runtime's append() path uses
        # the device signing key.
        assert outcome.delegation_record_ref

    async def test_modify_path_carries_modify_payload(self) -> None:
        runtime, *_ = await make_runtime(novelty_read_delay_seconds=0.0)
        outcome = await _run_one_lifecycle(runtime, resolution_kind="modify")

        assert outcome.state == "MODIFIED"
        assert outcome.result is not None
        assert outcome.result.decision == "modify"
        assert outcome.result.modify_payload["new_args_canonical"] == {
            "to": "approved-recipient@example.com"
        }
        assert outcome.result.modify_payload["new_args_canonical_hash"]

    async def test_all_three_shapes_run_in_one_session(self) -> None:
        # EC-2's literal claim — "3 Grant Moments triggered and resolved
        # correctly". This MUST work in one continuous runtime session
        # so the assertion mirrors the brief's wording.
        runtime, *_ = await make_runtime(novelty_read_delay_seconds=0.0)

        approve_outcome = await _run_one_lifecycle(runtime, resolution_kind="approve")
        decline_outcome = await _run_one_lifecycle(runtime, resolution_kind="decline")
        modify_outcome = await _run_one_lifecycle(runtime, resolution_kind="modify")

        assert (
            approve_outcome.state,
            decline_outcome.state,
            modify_outcome.state,
        ) == ("APPROVED", "DECLINED", "MODIFIED")


@pytest.mark.asyncio
class TestEC8CascadeRevocation:
    """EC-8 anchor: cascade revocation of a Day-1 grant reaches every
    descendant in a 3-deep delegation tree.
    """

    async def test_cascade_revoke_succeeds_when_runtime_returns_all_descendants(
        self,
    ) -> None:
        # Configure the stub runtime to return all 3 descendants on cascade.
        runtime, *_ = await make_runtime(
            cascade_responses={
                "root-grant-id": {"child-1", "child-2", "child-3"},
            }
        )
        result = runtime.revoke_prior_grant(
            root_id="root-grant-id",
            expected_descendants=frozenset({"child-1", "child-2", "child-3"}),
        )
        assert result.complete
        assert result.revoked_ids == frozenset({"child-1", "child-2", "child-3"})
        assert result.missing_descendants == frozenset()

    async def test_cascade_revoke_raises_when_descendant_is_missing(self) -> None:
        runtime, *_ = await make_runtime(
            cascade_responses={
                "root-grant-id": {"child-1", "child-3"},  # child-2 missing
            }
        )
        with pytest.raises(CascadeIncompleteError) as exc:
            runtime.revoke_prior_grant(
                root_id="root-grant-id",
                expected_descendants=frozenset({"child-1", "child-2", "child-3"}),
            )
        assert "child-2" in exc.value.result.missing_descendants

    async def test_cascade_revoke_without_orchestrator_raises_value_error(self) -> None:
        # If the runtime was built without a CascadeRevocationOrchestrator
        # (Phase 01 narrow scope), revoke_prior_grant raises ValueError
        # rather than silently no-op'ing.
        from envoy.grant_moment import (
            ChannelHandoff,
            EnvoyGrantMomentRuntime,
            NoveltyClassifier,
        )
        from envoy.ledger import EnvoyLedger
        from kailash.trust.audit_store import InMemoryAuditStore
        from kailash.trust.key_manager import InMemoryKeyManager
        from tests.helpers.grant_moment_harness import (
            DEFAULT_ALGO_ID,
            DEFAULT_DELEGATION_KEY,
            DEFAULT_DEVICE_ID,
            DEFAULT_LEDGER_SIGNING_KEY,
            RecordingChannelAdapter,
        )

        km = InMemoryKeyManager()
        await km.generate_keypair(DEFAULT_DELEGATION_KEY)
        await km.generate_keypair(DEFAULT_LEDGER_SIGNING_KEY)
        audit = InMemoryAuditStore()
        ledger = EnvoyLedger(
            audit_store=audit,
            key_manager=km,
            signing_key_id=DEFAULT_LEDGER_SIGNING_KEY,
            device_id=DEFAULT_DEVICE_ID,
            algorithm_identifier=DEFAULT_ALGO_ID,
        )
        adapter = RecordingChannelAdapter(channel_id="cli")
        handoff = ChannelHandoff(adapters=(adapter,), primary_channel_id="cli")
        runtime_no_cascade = EnvoyGrantMomentRuntime(
            key_manager=km,
            delegation_key_id=DEFAULT_DELEGATION_KEY,
            principal_id=DEFAULT_PRINCIPAL_ID,
            device_id=DEFAULT_DEVICE_ID,
            ledger=ledger,
            channel_handoff=handoff,
            novelty_classifier=NoveltyClassifier(),
            cascade_orchestrator=None,  # explicit
        )
        with pytest.raises(ValueError, match="cascade_orchestrator"):
            runtime_no_cascade.revoke_prior_grant(root_id="root", expected_descendants=frozenset())
