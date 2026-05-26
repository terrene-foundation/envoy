"""Tier-2: cross-principal dual-signed contract pin.

Per `specs/grant-moment.md` § Cross-principal (Phase 03): dual-signed if the
action affects both principals; first principal's dialog → second principal's
dialog on their channel; action executes only after both signed; 24h
cooling-off for high-stakes.

Phase 01 narrow scope: the full dual-sign + 24h cool-off flow is Phase 03
scope. Phase 01 MUST refuse cross-principal grants at the runtime boundary
because Phase 01 has NO path to verify ``co_signature_hex``. A single
principal that can populate ``co_signer_principal_genesis_id`` would
otherwise produce a "cross-principal grant" without the second principal's
actual signature — exactly the wire-shape-only-defense gap security
review surfaced.

The Phase-01 contract pin: ``is_cross_principal=True`` raises
``DualSignatureRequiredError`` at ``issue_grant_moment``. Phase 03 lifts
the gate and implements the dual-sign + cooling-off flow.
"""

from __future__ import annotations

import pytest

from envoy.grant_moment import DualSignatureRequiredError
from tests.helpers.grant_moment_harness import make_issue_kwargs, make_runtime


@pytest.mark.asyncio
class TestCrossPrincipalPhase01Refusal:
    async def test_cross_principal_at_issue_raises_dual_signature_required(self) -> None:
        # Phase 01 contract pin: cross-principal grants are refused at the
        # M0 boundary because Phase 01 lacks the co-signature verification
        # path. Phase 03 ships the actual flow.
        runtime, *_ = await make_runtime()
        with pytest.raises(DualSignatureRequiredError) as exc:
            await runtime.issue_grant_moment(**make_issue_kwargs(is_cross_principal=True))
        assert "phase-03" in str(exc.value).lower() or "co-signer" in str(exc.value).lower()
        # The refused grant did NOT pollute the in-flight tracking.
        assert runtime.inflight_count() == 0

    async def test_non_cross_principal_default_path_completes(self) -> None:
        # Sanity check: the default path — single-principal Grant Moment —
        # completes without engaging the dual-signature gate.
        from envoy.grant_moment import ApproveResolution
        from tests.helpers.grant_moment_harness import DEFAULT_PRINCIPAL_ID

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
