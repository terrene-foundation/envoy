"""Tier-2: visible secret + dialog content rendered every active channel.

Per `specs/grant-moment.md` § Rendering: "Every dialog shows: Visible secret
(icon + color + phrase, stored in Trust Vault). Proposed action. Why asking.
Consequence preview. Options."

The Wave-4 facade dispatches a fully-populated ``GrantMomentRequest`` to every
active channel adapter; the adapter is responsible for rendering all five
required elements. This test verifies the runtime dispatches the same request
shape to every channel — channel adapters surface the actual render under
their own per-channel test surface.
"""

from __future__ import annotations

import pytest

from tests.helpers.grant_moment_harness import (
    StubTrustStore,
    make_high_stakes_signals,
    make_issue_kwargs,
    make_runtime,
)


@pytest.mark.asyncio
class TestRenderAcrossChannels:
    async def test_low_stakes_dispatches_request_to_every_channel(self) -> None:
        runtime, *_, adapters = await make_runtime(
            primary_channel_id="cli",
            adapter_channel_ids=("cli", "web", "telegram"),
            novelty_read_delay_seconds=0.0,
        )

        request = await runtime.issue_grant_moment(**make_issue_kwargs())

        for adapter in adapters:
            assert (
                len(adapter.renders) == 1
            ), f"{adapter.channel_id}: expected 1 render; got {len(adapter.renders)}"
            received = adapter.renders[0]
            # Every adapter receives the same request object — all five spec
            # render elements live on the request: visible_secret hash lookup
            # is the adapter's job, but the other four arrive on the wire.
            assert received.tool_name == "send_email"  # proposed action
            assert received.why_asking == "envelope_violation"  # why asking
            assert received.consequence_preview.budget_microdollars == 1000  # preview
            # Options arrive via the spec wire — resolution shapes are the
            # decision side. The adapter renders Approve/Decline/Modify UI;
            # the request carries the dispatch context that drives them.
            assert received.request_id == request.request_id

    async def test_high_stakes_renders_only_on_primary_channel(self) -> None:
        runtime, *_, adapters = await make_runtime(
            primary_channel_id="cli",
            adapter_channel_ids=("cli", "web", "telegram"),
        )

        await runtime.issue_grant_moment(
            **make_issue_kwargs(novelty_signals=make_high_stakes_signals())
        )

        cli = next(a for a in adapters if a.channel_id == "cli")
        siblings = [a for a in adapters if a.channel_id != "cli"]
        assert len(cli.renders) == 1
        for sibling in siblings:
            assert (
                len(sibling.renders) == 0
            ), f"{sibling.channel_id}: high-stakes must NOT render on sibling channels"

    async def test_primary_only_flag_restricts_render_even_when_low_stakes(self) -> None:
        runtime, *_, adapters = await make_runtime(
            primary_channel_id="cli",
            adapter_channel_ids=("cli", "web"),
        )

        await runtime.issue_grant_moment(**make_issue_kwargs(primary_only=True))

        cli = next(a for a in adapters if a.channel_id == "cli")
        web = next(a for a in adapters if a.channel_id == "web")
        assert len(cli.renders) == 1
        assert len(web.renders) == 0

    async def test_visible_secret_hash_plumbing_exposed_by_runtime(self) -> None:
        # T-018 defense: the runtime exposes the user's visible-secret hash
        # so channel adapters can compare what they'd render against the
        # canonical stored hash. The adapter raises VisibleSecretMismatchError
        # on divergence; the runtime supplies only the hash (never the phrase).
        secret = StubTrustStore()  # default phrase
        runtime, *_ = await make_runtime(trust_store=secret)

        h = await runtime.visible_secret_hash_for("any-principal-id")
        assert h is not None
        # Hex digest of a sha256 is 64 chars.
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    async def test_visible_secret_hash_returns_none_when_no_store_or_no_secret(self) -> None:
        # No trust_store injected → None (graceful for Phase 01 narrow scope).
        runtime, *_ = await make_runtime(trust_store=None)
        assert await runtime.visible_secret_hash_for("p") is None

        # Trust store injected but no secret stored → None.
        empty = StubTrustStore(secret=None)
        runtime2, *_ = await make_runtime(trust_store=empty)
        assert await runtime2.visible_secret_hash_for("p") is None
