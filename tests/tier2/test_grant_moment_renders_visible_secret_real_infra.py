# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2: F15-a — a production Grant Moment MUST render the user's REAL
visible secret (T-018 anti-spoofing).

Source authority — `specs/grant-moment.md` § Rendering (lines 80-82) verbatim:

> Every dialog shows:
> - Visible secret (icon + color + phrase, stored in Trust Vault).

The visible secret is the structural anti-spoofing defense: the user confirms a
Grant-Moment prompt genuinely came from Envoy by checking it shows THEIR private
icon+color+phrase (a spoofer cannot reproduce it). `specs/grant-moment.md` § 10
lists T-018 (dialog spoofing) as a mitigated threat; the spec gives NO Phase-02
carve-out for the visible-secret render.

CONFIRMED GAP (journal/0044 F15): the production dispatch path
(`EnvoyGrantMomentRuntime.issue_grant_moment` → `ChannelHandoff.dispatch` →
`adapter.render_grant_moment(request)` at `channel_handoff.py:241` →
`CLIChannelAdapter._render_grant_moment_request_prose` at `cli.py:433`) renders
the action / why / novelty but NOT the visible secret — the renderer's own
comment (`cli.py:442-444`) states "the M1 dispatch surface does not carry it".
The only renderer that DOES emit the phrase (`_render_grant_moment_prose`,
consuming `GrantMomentPayload`) is orphaned: `GrantMomentPayload(` is never
constructed anywhere in `envoy/`. Every prior render test passed because it
asserted against a hardcoded STUB secret through the dead path.

This test drives the ACTUAL user-facing path — a real `TrustStoreAdapter`
holding a real set secret, a real `CLIChannelAdapter` capturing its output, the
real runtime dispatch — and asserts the rendered Grant Moment the user sees
contains the user's real phrase. It FAILS today (the dispatch render omits the
secret) and is marked `xfail(strict=True)` so that when F15-b wires the
runtime-resolved `VisibleSecret` into `render_grant_moment` across the channel
adapters (phrase kept OUT of the signed request / ledger per R1-HIGH-1b), the
xpass fires and strict-mode forces removal of this marker.

Per `rules/testing.md` Tier 2: NO mocking. Real `TrustStoreAdapter` (sqlite +
Ed25519), real `EnvoyLedger` over `InMemoryAuditStore`, real `CLIChannelAdapter`
over `io.StringIO`, real `ChannelHandoff` dispatch.
"""

from __future__ import annotations

import io
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from kailash.trust.audit_store import InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.channels.cli import CLIChannelAdapter, CLIChannelConfig
from envoy.grant_moment import ChannelHandoff, EnvoyGrantMomentRuntime, NoveltyClassifier
from envoy.ledger import EnvoyLedger
from envoy.trust.store import TrustStoreAdapter
from tests.helpers.grant_moment_harness import (
    DEFAULT_ALGO_ID,
    DEFAULT_DELEGATION_KEY,
    DEFAULT_DEVICE_ID,
    DEFAULT_LEDGER_SIGNING_KEY,
    DEFAULT_PRINCIPAL_ID,
    make_issue_kwargs,
)


# A unique phrase that could ONLY appear in the rendered output if the real
# stored secret reached the render path — never a stub default.
_REAL_PHRASE = "tide-pool-lantern-quartz-2026"
_REAL_ICON = "lantern"
_REAL_COLOR = "#1b4d3e"


@pytest.fixture
async def runtime_with_real_secret(
    tmp_path: Path,
) -> AsyncGenerator[tuple[EnvoyGrantMomentRuntime, io.StringIO], None]:
    """Real runtime wired to a real CLIChannelAdapter (output captured) + a real
    TrustStoreAdapter holding a set visible secret for the runtime's principal."""
    key_manager = InMemoryKeyManager()
    await key_manager.generate_keypair(DEFAULT_DELEGATION_KEY)
    await key_manager.generate_keypair(DEFAULT_LEDGER_SIGNING_KEY)

    audit_store = InMemoryAuditStore()
    ledger = EnvoyLedger(
        audit_store=audit_store,
        key_manager=key_manager,
        signing_key_id=DEFAULT_LEDGER_SIGNING_KEY,
        device_id=DEFAULT_DEVICE_ID,
        algorithm_identifier=DEFAULT_ALGO_ID,
    )

    trust_store = TrustStoreAdapter(
        vault_path=tmp_path / "f15-vault.dat",
        principal_id=DEFAULT_PRINCIPAL_ID,
    )
    await trust_store.initialize()
    await trust_store.set_visible_secret(
        DEFAULT_PRINCIPAL_ID, icon=_REAL_ICON, color=_REAL_COLOR, phrase=_REAL_PHRASE
    )

    captured = io.StringIO()
    cli = CLIChannelAdapter(
        CLIChannelConfig(
            primary_channel_id="cli",
            output_stream=captured,
            input_stream=io.StringIO(),
        )
    )
    await cli.startup()
    # Real CLIChannelAdapter; structural ChannelAdapterProtocol match, nominal-only
    # mismatch (channel_id is a read-only property vs the protocol's mutable str).
    # Runtime-compatible; the dispatch invokes it for real below.
    handoff = ChannelHandoff(adapters=(cli,), primary_channel_id="cli")  # type: ignore[arg-type]

    runtime = EnvoyGrantMomentRuntime(
        key_manager=key_manager,
        delegation_key_id=DEFAULT_DELEGATION_KEY,
        principal_id=DEFAULT_PRINCIPAL_ID,
        device_id=DEFAULT_DEVICE_ID,
        ledger=ledger,
        channel_handoff=handoff,
        # Real TrustStoreAdapter; structural _VisibleSecretProviderProtocol match,
        # nominal-only mismatch (returns VisibleSecret, structurally ≡ _VisibleSecretShape).
        trust_store=trust_store,  # type: ignore[arg-type]
        novelty_classifier=NoveltyClassifier(),
        novelty_read_delay_seconds=0.0,
    )
    try:
        yield runtime, captured
    finally:
        await trust_store.close()


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="F15-b: the M1 dispatch render path (render_grant_moment → "
    "_render_grant_moment_request_prose) omits the visible secret "
    "(cli.py:442-444); GrantMomentPayload is orphaned. Wiring the "
    "runtime-resolved VisibleSecret into the channel-adapter render — phrase "
    "kept out of the signed request/ledger — flips this xpass. See "
    "journal/0044 F15 + specs/grant-moment.md:80-82 (T-018 anti-spoofing).",
)
async def test_production_grant_moment_renders_real_visible_secret(
    runtime_with_real_secret: tuple[EnvoyGrantMomentRuntime, io.StringIO],
) -> None:
    """specs/grant-moment.md:80-82 — every dialog MUST show the visible secret.

    Drive the real dispatch path and assert the rendered Grant Moment the user
    sees contains their REAL stored phrase. FAILS today (xfail strict)."""
    runtime, captured = runtime_with_real_secret

    await runtime.issue_grant_moment(**make_issue_kwargs())

    rendered = captured.getvalue()
    assert rendered, "no Grant Moment was rendered to the CLI channel at all"
    assert _REAL_PHRASE in rendered, (
        "production Grant-Moment render omits the user's real visible secret — "
        "T-018 anti-spoofing surface absent (F15)"
    )
