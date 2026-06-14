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

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from envoy.grant_moment import (
    ApproveResolution,
    ApproveWithModificationResolution,
    CascadeIncompleteError,
    DeclineResolution,
    GrantMomentOutcome,
)
from envoy.grant_moment.cascade_orchestrator import CascadeRevocationOrchestrator
from envoy.runtime.adapters.kailash_py import KailashPyRuntime
from envoy.trust.store import TrustStoreAdapter
from envoy.trust.types import DelegationRequest, GenesisSeed
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
    """EC-8 anchor: the CascadeRevocationOrchestrator's verification half —
    complete-vs-missing — exercised through ``revoke_prior_grant``. The literal
    real-engine cascade (the F12-b lift) is ``TestEC8CascadeRevocationRealInfra``
    below; these stub-backed tests pin the orchestrator's verify-or-raise
    contract in isolation (a Protocol-Satisfying Deterministic stub per
    `rules/testing.md` § Tier 2, NOT a mock).
    """

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
        from kailash.trust.audit_store import InMemoryAuditStore
        from kailash.trust.key_manager import InMemoryKeyManager

        from envoy.grant_moment import (
            ChannelHandoff,
            EnvoyGrantMomentRuntime,
            NoveltyClassifier,
        )
        from envoy.ledger import EnvoyLedger
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


# Day-1 root + three Day-6 children — the literal "root + 3 expected
# descendants" tree the spec (`specs/grant-moment.md` § test list) describes.
_ROOT = "alice-day1-root@example"
_CHILDREN = (
    "bob-day6-telegram@example",
    "carol-day6-slack@example",
    "dave-day6-cli@example",
)


class TestEC8CascadeRevocationRealInfra:
    """EC-8(c) cascade through the REAL trust store, driven through the runtime
    facade ``revoke_prior_grant`` via the F12-b sync↔async bridge.

    This is the spec's Phase-02 lift (`specs/grant-moment.md`): the EC-8 cascade
    assertion was previously stubbed (``cascade_responses`` on
    ``StubTrustRuntime``); it now seeds a real ``TrustStoreAdapter`` delegation
    tree and revokes the root through the production binding chain
    ``revoke_prior_grant`` → ``CascadeRevocationOrchestrator.revoke_and_verify``
    → ``KailashPyRuntime.trust_cascade_revoke`` → F12-b bridge → async
    ``TrustStoreAdapter.revoke``. NO mocking (`rules/testing.md` § Tier 2/3).

    This is a SYNC test by design: it seeds on a throwaway ``asyncio.run`` loop
    (persisting to the on-disk SQLite vault), then drives the SYNC
    ``revoke_prior_grant`` from a thread with NO running loop. The bridge runs
    the async revoke on a dedicated worker thread that lazily initializes a
    fresh adapter against the persisted vault — exactly the production CLI
    shape (a ``asyncio.run``-wrapped command driving the sync facade).
    """

    def test_revoke_root_cascades_to_all_three_real_descendants(self, tmp_path) -> None:
        vault = tmp_path / "ec8-real-vault.dat"

        async def _seed() -> None:
            adapter = TrustStoreAdapter(vault_path=vault, principal_id=_ROOT)
            await adapter.initialize()
            await adapter.seed_genesis(
                GenesisSeed(
                    principal_id=_ROOT,
                    authority_id="authority-ec8-real",
                    capabilities=("read_email", "send_email", "draft_response"),
                    expires_at=datetime.now(tz=timezone.utc) + timedelta(days=30),
                    metadata={"authority_name": "day-1 root", "channel": "cli"},
                )
            )
            for child, cap, channel in zip(
                _CHILDREN,
                ("send_email", "read_email", "draft_response"),
                ("telegram", "slack", "cli"),
                strict=True,
            ):
                await adapter.record_delegation(
                    DelegationRequest(
                        delegator_id=_ROOT,
                        delegatee_id=child,
                        task_id=f"task-day6-{channel}",
                        capabilities=(cap,),
                        metadata={"channel": channel, "day": 6},
                    )
                )
            await adapter.close()

        asyncio.run(_seed())

        async def _build_runtime():
            # Fresh, NOT-initialized adapter: the F12-b bridge lazily initializes
            # it on the worker thread (store.revoke()'s `if not self._initialized`
            # guard), so every SQLite op for the cascade runs on one thread
            # against the persisted vault — no cross-thread connection reuse.
            store = TrustStoreAdapter(vault_path=vault, principal_id=_ROOT)
            orchestrator = CascadeRevocationOrchestrator(
                runtime=KailashPyRuntime(trust_store=store)
            )
            runtime, *_ = await make_runtime(cascade_orchestrator=orchestrator)
            return runtime

        runtime = asyncio.run(_build_runtime())

        # Drive the REAL cascade through the sync facade — the bridge runs the
        # async revoke on its worker-thread loop.
        result = runtime.revoke_prior_grant(
            root_id=_ROOT,
            expected_descendants=frozenset(_CHILDREN),
        )

        # The cascade actually revoked the descendants (NOT a silent-empty set).
        assert result.complete, f"missing descendants: {result.missing_descendants}"
        assert frozenset(_CHILDREN) <= result.revoked_ids
        assert result.missing_descendants == frozenset()

    def test_revoke_incomplete_tree_raises_cascade_incomplete(self, tmp_path) -> None:
        """When the real engine revokes FEWER descendants than expected (a
        child was never delegated), ``revoke_and_verify`` raises
        ``CascadeIncompleteError`` naming the missing descendant — the real
        engine driving the orchestrator's verify-or-raise contract end-to-end."""
        vault = tmp_path / "ec8-incomplete-vault.dat"

        async def _seed() -> None:
            adapter = TrustStoreAdapter(vault_path=vault, principal_id=_ROOT)
            await adapter.initialize()
            await adapter.seed_genesis(
                GenesisSeed(
                    principal_id=_ROOT,
                    authority_id="authority-ec8-incomplete",
                    capabilities=("read_email", "send_email"),
                    expires_at=datetime.now(tz=timezone.utc) + timedelta(days=30),
                    metadata={"authority_name": "day-1 root", "channel": "cli"},
                )
            )
            # Only ONE child is actually delegated.
            await adapter.record_delegation(
                DelegationRequest(
                    delegator_id=_ROOT,
                    delegatee_id=_CHILDREN[0],
                    task_id="task-day6-telegram",
                    capabilities=("send_email",),
                    metadata={"channel": "telegram", "day": 6},
                )
            )
            await adapter.close()

        asyncio.run(_seed())

        async def _build_runtime():
            store = TrustStoreAdapter(vault_path=vault, principal_id=_ROOT)
            orchestrator = CascadeRevocationOrchestrator(
                runtime=KailashPyRuntime(trust_store=store)
            )
            runtime, *_ = await make_runtime(cascade_orchestrator=orchestrator)
            return runtime

        runtime = asyncio.run(_build_runtime())

        # Expect all three, but only one was delegated → incomplete.
        with pytest.raises(CascadeIncompleteError) as exc:
            runtime.revoke_prior_grant(
                root_id=_ROOT,
                expected_descendants=frozenset(_CHILDREN),
            )
        # The two un-delegated children are named as missing.
        assert _CHILDREN[1] in exc.value.result.missing_descendants
        assert _CHILDREN[2] in exc.value.result.missing_descendants
