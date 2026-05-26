"""Tier-2: acknowledge_friction rejects unknown tokens.

Security-R1 MED-1 + reviewer-R1 MED-5: ``acknowledge_friction`` MUST reject
unknown tokens loudly so a typo'd token does not silently fail to satisfy
the friction enforcer.
"""

from __future__ import annotations

import pytest

from envoy.grant_moment import (
    FRICTION_TOKEN_CROSS_CHANNEL_CONFIRM,
    FRICTION_TOKEN_DOUBLE_TAP,
    FRICTION_TOKEN_READ_DELAY_COMPLETE,
)
from tests.helpers.grant_moment_harness import make_issue_kwargs, make_runtime


@pytest.mark.asyncio
class TestFrictionTokenVocabulary:
    async def test_empty_token_rejected(self) -> None:
        runtime, *_ = await make_runtime()
        request = await runtime.issue_grant_moment(**make_issue_kwargs())
        with pytest.raises(ValueError, match="non-empty"):
            runtime.acknowledge_friction(request.request_id, "")

    async def test_unknown_token_rejected_with_canonical_vocabulary(self) -> None:
        runtime, *_ = await make_runtime()
        request = await runtime.issue_grant_moment(**make_issue_kwargs())
        with pytest.raises(ValueError, match="unknown friction token"):
            # typo of FRICTION_TOKEN_READ_DELAY_COMPLETE
            runtime.acknowledge_friction(request.request_id, "read_delay_complte")

    async def test_each_canonical_token_accepted(self) -> None:
        runtime, *_ = await make_runtime()
        request = await runtime.issue_grant_moment(**make_issue_kwargs())
        runtime.acknowledge_friction(request.request_id, FRICTION_TOKEN_READ_DELAY_COMPLETE)
        runtime.acknowledge_friction(request.request_id, FRICTION_TOKEN_DOUBLE_TAP)
        runtime.acknowledge_friction(request.request_id, FRICTION_TOKEN_CROSS_CHANNEL_CONFIRM)
