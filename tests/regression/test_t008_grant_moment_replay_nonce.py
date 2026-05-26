"""Regression: T-008 Grant Moment replay nonce defense (runtime dedup store).

Contract pin: T-008 (Grant Moment replay defense — nonce + intent_id dedup).

Per `specs/grant-moment.md` § Error taxonomy: ``GrantMomentReplayError``
fires when the same ``nonce`` OR ``intent_id`` is observed twice. The wire-
shape Contract pin lives in
``tests/tier1/test_grant_moment_state_machine_transitions.py`` (TestErrorTaxonomy);
THIS file exercises the runtime layer's dedup store refusal.
"""

from __future__ import annotations

import pytest

from envoy.grant_moment import GrantMomentReplayError
from tests.helpers.grant_moment_harness import (
    make_issue_kwargs,
    make_runtime,
)


@pytest.mark.regression
@pytest.mark.asyncio
class TestT008NonceReplay:
    """Contract pin: T-008."""

    async def test_duplicate_nonce_raises_replay_error(self) -> None:
        runtime, *_ = await make_runtime()

        fixed_nonce = "fixed-nonce-deadbeef"
        first = await runtime.issue_grant_moment(**make_issue_kwargs(nonce=fixed_nonce))

        with pytest.raises(GrantMomentReplayError) as exc:
            await runtime.issue_grant_moment(**make_issue_kwargs(nonce=fixed_nonce))

        assert exc.value.duplicate_value == fixed_nonce
        assert exc.value.duplicate_kind == "nonce"
        assert exc.value.prior_request_id == first.request_id

    async def test_duplicate_intent_id_raises_replay_error(self) -> None:
        runtime, *_ = await make_runtime()

        fixed_intent = "sha256:intent-fixed-001"
        first = await runtime.issue_grant_moment(**make_issue_kwargs(intent_id=fixed_intent))

        with pytest.raises(GrantMomentReplayError) as exc:
            await runtime.issue_grant_moment(**make_issue_kwargs(intent_id=fixed_intent))

        assert exc.value.duplicate_value == fixed_intent
        assert exc.value.duplicate_kind == "intent_id"
        assert exc.value.prior_request_id == first.request_id

    async def test_dedup_persists_across_m4_complete(self) -> None:
        # After a grant completes (M4), the in-flight tracking drops — but
        # the dedup store retains the (nonce, intent_id) pair so a delayed
        # replay attempt still fires GrantMomentReplayError. This is the
        # T-008 invariant: replay defense outlives any single lifecycle.
        from envoy.grant_moment import ApproveResolution
        from tests.helpers.grant_moment_harness import DEFAULT_PRINCIPAL_ID

        runtime, *_ = await make_runtime()

        fixed_nonce = "post-completion-nonce"
        request = await runtime.issue_grant_moment(**make_issue_kwargs(nonce=fixed_nonce))
        runtime.post_decision(
            request.request_id,
            ApproveResolution(decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID),
        )
        resolution = await runtime.await_decision(request.request_id, timeout_seconds=5)
        await runtime.submit_resolution(
            request_id=request.request_id,
            resolution=resolution,
            decided_on_channel_id="cli",
        )
        assert runtime.inflight_count() == 0

        # Now replay the nonce — must still raise.
        with pytest.raises(GrantMomentReplayError):
            await runtime.issue_grant_moment(**make_issue_kwargs(nonce=fixed_nonce))

    async def test_different_nonces_and_intent_ids_do_not_dedup(self) -> None:
        # Sanity check — two grants with distinct (nonce, intent_id) pairs
        # both succeed. The dedup store is exact-match only.
        runtime, *_ = await make_runtime()
        await runtime.issue_grant_moment(**make_issue_kwargs())
        await runtime.issue_grant_moment(**make_issue_kwargs())
        assert runtime.inflight_count() == 2
