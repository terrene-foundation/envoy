# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2: F12-a — EC-8(c) cross-channel cascade against the REAL trust store.

Source authority:
- `01-analysis/02-mvp-objectives.md` EC-8 line 116 sub-clause (c) verbatim:
  "cascade revocation of a Day-1 grant correctly revokes a Day-6 child grant
  initiated from a different channel."
- `specs/trust-lineage.md` § Cascade revocation (BFS over the delegation graph).

Gap this closes (journal/0042 finding F12): every existing cascade test wires
a *stubbed* ``trust_cascade_revoke`` (`tests/helpers/grant_moment_harness.py`
``StubTrustRuntime``; `tests/tier2/test_grant_moment_cascade_cross_channel.py`
configures ``cascade_responses`` on the stub). The TIER-1 cascade tests
(`tests/tier1/test_trust_cascade_and_shamir.py`) deliberately exercise only the
idempotent no-op path (revoking an agent with no chain) to avoid standing up a
Genesis chain. So NO test seeds a real delegation chain WITH descendants and
asserts that revoking the root cascades to the children — the literal EC-8(c)
shape. This file is that test, against real infrastructure.

Per `rules/testing.md` Tier 2: NO mocking. Real ``TrustStoreAdapter`` over
real kailash-backed Genesis + delegation + ``cascade_revoke`` BFS + the
pre-revoke descendant snapshot that backs ``verify_cascade_complete``.

Scope note (journal/0042): F12-a proves the cascade ENGINE works against real
infra. It does NOT make cascade-revoke reachable from a user action — the
sync<->async facade bridge (F12-b, Phase-02) and the production entrypoint
wiring (F12-c, Wave-2 Grant Moment) remain deferred to their planned phases.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from envoy.trust.store import TrustStoreAdapter
from envoy.trust.types import DelegationRequest, GenesisSeed


# "Day-1" root principal — the original grant, established on the CLI channel.
ROOT_PRINCIPAL = "alice-day1-root@example"
# "Day-6" child grants, each delegated from the root on a DIFFERENT channel.
CHILD_TELEGRAM = "bob-day6-telegram@example"
CHILD_SLACK = "carol-day6-slack@example"


@pytest.fixture
async def root_adapter(tmp_path: Path) -> AsyncGenerator[TrustStoreAdapter, None]:
    """Real kailash-backed TrustStoreAdapter for the Day-1 root principal.

    The adapter is per-principal (the delegator's adapter), so all delegations
    recorded here have ``delegator_id == ROOT_PRINCIPAL`` — the Day-1 root
    fanning out Day-6 child grants. NO mock.
    """
    adapter = TrustStoreAdapter(
        vault_path=tmp_path / "ec8c-vault.dat",
        principal_id=ROOT_PRINCIPAL,
    )
    await adapter.initialize()
    yield adapter
    await adapter.close()


@pytest.fixture
async def seeded_cross_channel_chain(
    root_adapter: TrustStoreAdapter,
) -> TrustStoreAdapter:
    """Seed the Day-1 root Genesis + two Day-6 child grants on distinct channels.

    Mirrors EC-8(c): a Day-1 grant (CLI) fans out to a Day-6 child on Telegram
    and another on Slack. The ``channel`` metadata records the cross-channel
    origin; the cascade BFS operates on the delegation graph regardless of
    channel — which is exactly why revocation MUST cross channels.
    """
    await root_adapter.seed_genesis(
        GenesisSeed(
            principal_id=ROOT_PRINCIPAL,
            authority_id="authority-ec8c",
            capabilities=("read_email", "send_email", "draft_response"),
            expires_at=datetime.now(tz=timezone.utc) + timedelta(days=30),
            metadata={"authority_name": "day-1 root authority", "channel": "cli"},
        )
    )
    # Day-6 child grant initiated from Telegram.
    await root_adapter.record_delegation(
        DelegationRequest(
            delegator_id=ROOT_PRINCIPAL,
            delegatee_id=CHILD_TELEGRAM,
            task_id="task-day6-telegram",
            capabilities=("send_email",),  # subset of root's owned caps
            metadata={"channel": "telegram", "day": 6},
        )
    )
    # Day-6 child grant initiated from Slack (a DIFFERENT channel).
    await root_adapter.record_delegation(
        DelegationRequest(
            delegator_id=ROOT_PRINCIPAL,
            delegatee_id=CHILD_SLACK,
            task_id="task-day6-slack",
            capabilities=("read_email",),
            metadata={"channel": "slack", "day": 6},
        )
    )
    return root_adapter


# ---------------------------------------------------------------------------
# EC-8(c) — revoking the Day-1 root cascades to the cross-channel children
# ---------------------------------------------------------------------------


class TestEC8cCrossChannelCascade:
    async def test_revoke_day1_root_revokes_day6_cross_channel_children(
        self, seeded_cross_channel_chain: TrustStoreAdapter
    ) -> None:
        """The literal EC-8(c) acceptance shape: revoke the Day-1 root and the
        Day-6 children created on Telegram + Slack are in the revoked set."""
        adapter = seeded_cross_channel_chain

        result = await adapter.revoke(
            agent_id=ROOT_PRINCIPAL,
            reason="ec8c.cross_channel_cascade",
            revoked_by=ROOT_PRINCIPAL,
        )

        revoked = set(result.revoked_agents)
        # The cascade is NOT silently empty (the F10 facade-bug failure mode)
        # — the real engine actually revokes the descendants.
        assert revoked, "cascade revoked nothing — descendants survived the root revocation"
        # EC-8(c): both Day-6 cross-channel children are revoked.
        assert (
            CHILD_TELEGRAM in revoked
        ), f"Telegram child {CHILD_TELEGRAM} survived Day-1 root revocation"
        assert CHILD_SLACK in revoked, f"Slack child {CHILD_SLACK} survived Day-1 root revocation"

    async def test_verify_cascade_complete_passes_for_full_chain(
        self, seeded_cross_channel_chain: TrustStoreAdapter
    ) -> None:
        """The pre-revoke descendant snapshot (ground truth at revoke-time)
        matches the post-revoke revoked set — no descendant under-reported.
        This is the EC-8 gap-detector (`verify_cascade_complete`) running
        against a real chain, not a stub."""
        adapter = seeded_cross_channel_chain

        await adapter.revoke(
            agent_id=ROOT_PRINCIPAL,
            reason="ec8c.cross_channel_cascade",
            revoked_by=ROOT_PRINCIPAL,
        )

        assert await adapter.verify_cascade_complete(agent_id=ROOT_PRINCIPAL) is True

    async def test_revoked_set_is_idempotent_on_re_revoke(
        self, seeded_cross_channel_chain: TrustStoreAdapter
    ) -> None:
        """Re-revoking the already-revoked root is a kailash idempotent no-op:
        the chain is already soft-deleted, so the second cascade revokes
        nothing new (the children are already gone)."""
        adapter = seeded_cross_channel_chain

        first = await adapter.revoke(
            agent_id=ROOT_PRINCIPAL,
            reason="ec8c.cross_channel_cascade",
            revoked_by=ROOT_PRINCIPAL,
        )
        assert CHILD_TELEGRAM in set(first.revoked_agents)

        second = await adapter.revoke(
            agent_id=ROOT_PRINCIPAL,
            reason="ec8c.cross_channel_cascade.re_revoke",
            revoked_by=ROOT_PRINCIPAL,
        )
        # Already-revoked = no-op: the second pass revokes nothing new.
        assert set(second.revoked_agents) == set()
