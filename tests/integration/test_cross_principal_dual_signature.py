"""Tier-2: cross-principal dual-signed flow contract pin.

Per `specs/grant-moment.md` § Cross-principal (Phase 03): dual-signed if the
action affects both principals; first principal's dialog → second principal's
dialog on their channel; action executes only after both signed; 24h
cooling-off for high-stakes.

Phase 01 narrow scope: the runtime ships the WIRE-SHAPE contract — the
``DualSignatureRequiredError`` raise path fires when a cross-principal
resolution arrives without the co-signer's signature. Full Phase 03 flow
(channel hop + cooling-off pause + final co-sign) lives in Phase 03.
"""

from __future__ import annotations

import pytest

from envoy.grant_moment import (
    ApproveResolution,
    DualSignatureRequiredError,
)
from tests.helpers.grant_moment_harness import (
    DEFAULT_PRINCIPAL_ID,
    make_issue_kwargs,
    make_runtime,
)


@pytest.mark.asyncio
class TestCrossPrincipalDualSignature:
    async def test_cross_principal_without_co_signer_raises_dual_signature_required(self) -> None:
        runtime, *_ = await make_runtime()
        request = await runtime.issue_grant_moment(**make_issue_kwargs(is_cross_principal=True))
        runtime.post_decision(
            request.request_id,
            ApproveResolution(
                decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID,
                co_signer_principal_genesis_id=None,  # no co-signer yet
            ),
        )
        resolution = await runtime.await_decision(request.request_id, timeout_seconds=5)

        outcome = await runtime.submit_resolution(
            request_id=request.request_id,
            resolution=resolution,
            decided_on_channel_id="cli",
        )
        assert outcome.state == "ERROR"
        assert isinstance(outcome.error, DualSignatureRequiredError)
        assert outcome.error.request_id == request.request_id

    async def test_cross_principal_with_co_signer_completes(self) -> None:
        # Contract pin: when the resolution arrives WITH a co-signer id, the
        # dual-signature path is structurally satisfied — Phase 01 does not
        # exercise the Phase-03 cooling-off + cross-channel hop, but the
        # wire-shape Approve flow MUST complete cleanly.
        runtime, *_ = await make_runtime()
        request = await runtime.issue_grant_moment(**make_issue_kwargs(is_cross_principal=True))
        co_signer_id = "sha256:co-signer-principal-genesis-id"
        runtime.post_decision(
            request.request_id,
            ApproveResolution(
                decided_by_principal_genesis_id=DEFAULT_PRINCIPAL_ID,
                co_signer_principal_genesis_id=co_signer_id,
            ),
        )
        resolution = await runtime.await_decision(request.request_id, timeout_seconds=5)

        outcome = await runtime.submit_resolution(
            request_id=request.request_id,
            resolution=resolution,
            decided_on_channel_id="cli",
        )
        assert outcome.state == "APPROVED"
        assert outcome.result is not None
        assert outcome.result.co_signer_principal_genesis_id == co_signer_id

    async def test_non_cross_principal_does_not_require_co_signer(self) -> None:
        # The default path — single-principal Grant Moment — completes
        # without a co-signer. Sanity check that the dual-signature gate
        # only fires on the cross-principal axis.
        runtime, *_ = await make_runtime()
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
