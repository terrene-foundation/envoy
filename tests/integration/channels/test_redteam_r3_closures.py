"""Tier-2: pins for /redteam R3 same-shard closures (PR #42).

R3 audit verdict (3-axis):
- security: CLEAN (0 CRIT/0 HIGH) + 6 MED + 4 LOW.
- reviewer: NOT CLEAN — 2 HIGH (H-R3-1 dead H-03 check vs real
  `GrantMomentRequest`; H-R3-2 `approve_author` typo divergence) + 2 MED + 2 LOW.
- spec-compliance: CLEAN + 3 MED + 2 LOW.

R3 closures landed same-shard per `rules/autonomous-execution.md` MUST-4.
Each test docstring names the R3 finding it pins (e.g. ``H-R3-1``).
"""

from __future__ import annotations

import asyncio
import logging
import typing
import uuid

import pytest

from envoy.channels import (
    CLIChannelAdapter,
    InvalidDecisionError,
    NotPrimaryChannelError,
    WebChannelAdapter,
)
from envoy.channels.cli import CLIChannelConfig
from envoy.channels.envelope import GrantMomentDecision
from envoy.channels.web import _ALLOWED_DECISIONS, WebChannelConfig


class _Request:
    """Duck-typed shim mirroring canonical `GrantMomentRequest` fields."""

    def __init__(
        self,
        *,
        request_id: str = "r-r3",
        novelty_class: str = "familiar_repeat",
        primary_only: bool = False,
        tool_name: str = "",
        why_asking: str = "",
        consequence_preview: object | None = None,
    ) -> None:
        self.request_id = request_id
        self.novelty_class = novelty_class
        self.primary_only = primary_only
        self.tool_name = tool_name
        self.why_asking = why_asking
        self.consequence_preview = consequence_preview


# ---------------------------------------------------------------------------
# H-R3-1 — render_grant_moment honors canonical GrantMomentRequest discriminator
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestRenderGrantMomentCanonicalH03:
    """Pin: `render_grant_moment` reads `novelty_class` + `primary_only`.

    Pre-R3 the R2 closure read a non-existent `high_stakes` attribute —
    dead code against the real `envoy.grant_moment.signed_consent.GrantMomentRequest`
    dataclass. The R3 closure switches to the canonical discriminators.
    """

    @pytest.mark.asyncio
    async def test_cli_render_refuses_on_novelty_high_stakes_non_primary(self) -> None:
        adapter = CLIChannelAdapter(CLIChannelConfig(primary_channel_id="web"))
        await adapter.startup()
        try:
            with pytest.raises(NotPrimaryChannelError) as excinfo:
                await adapter.render_grant_moment(
                    _Request(novelty_class="high_stakes", primary_only=False)
                )
            assert excinfo.value.channel_id == "cli"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_cli_render_refuses_on_primary_only_kwarg_non_primary(self) -> None:
        adapter = CLIChannelAdapter(CLIChannelConfig(primary_channel_id="web"))
        await adapter.startup()
        try:
            with pytest.raises(NotPrimaryChannelError):
                await adapter.render_grant_moment(
                    _Request(novelty_class="familiar_repeat", primary_only=True)
                )
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_web_render_refuses_on_novelty_high_stakes_non_primary(self) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="cli"))
        await adapter.startup()
        try:
            with pytest.raises(NotPrimaryChannelError):
                await adapter.render_grant_moment(_Request(novelty_class="high_stakes"))
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_render_proceeds_on_low_stakes_non_primary(self) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="cli"))
        await adapter.startup()
        try:
            await adapter.render_grant_moment(
                _Request(novelty_class="familiar_repeat", primary_only=False)
            )
        finally:
            for fut in adapter._pending_decisions.values():
                if not fut.done():
                    fut.cancel()
            await adapter.shutdown()


# ---------------------------------------------------------------------------
# H-R3-2 — approve_author typo removed from vocabulary
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestDecisionVocabularyCanonical:
    """Pin: the divergent `approve_author` typo is gone from both surfaces."""

    def test_grant_moment_decision_does_not_admit_approve_author(self) -> None:
        members = set(typing.get_args(GrantMomentDecision))
        assert "approve_author" not in members
        # The canonical 4-vocab matches the production resolution path.
        assert members == {"approve_once", "approve_and_author", "deny", "modify"}

    def test_allowed_decisions_does_not_admit_approve_author(self) -> None:
        assert "approve_author" not in _ALLOWED_DECISIONS
        assert _ALLOWED_DECISIONS == {
            "approve_once",
            "approve_and_author",
            "deny",
            "modify",
        }

    def test_allowed_decisions_derived_from_literal(self) -> None:
        """MED-R3-04 closure: vocabulary derives from the Literal, no drift."""
        assert _ALLOWED_DECISIONS == frozenset(typing.get_args(GrantMomentDecision))


# ---------------------------------------------------------------------------
# M-R3-1 — Web send_grant_moment.ok log line
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestWebSendGrantMomentOkLog:
    """Pin: Web `send_grant_moment` emits `.ok` on success path."""

    @pytest.mark.asyncio
    async def test_web_send_grant_moment_emits_ok_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from envoy.channels.envelope import GrantMomentPayload, VisibleSecret

        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        await adapter.startup()
        rid = f"r-ok-{uuid.uuid4().hex[:8]}"
        grant = GrantMomentPayload(
            request_id=rid,
            intent_id="i-1",
            decision_options=("approve_once", "deny"),
            visible_secret=VisibleSecret(icon="i", color="c", phrase="p"),
            body="b",
            high_stakes=False,
        )
        try:

            async def resolver() -> None:
                await asyncio.sleep(0.01)
                await adapter._resolve_pending_decision(rid, "approve_once")

            with caplog.at_level(logging.INFO, logger="envoy.channels.web"):
                send_task = asyncio.create_task(
                    adapter.send_grant_moment("p", grant, timeout_seconds=5)
                )
                resolver_task = asyncio.create_task(resolver())
                await asyncio.gather(send_task, resolver_task)
            events = [r.message for r in caplog.records]
            assert any("channel.send_grant_moment.ok" in e for e in events)
        finally:
            await adapter.shutdown()


# ---------------------------------------------------------------------------
# M-R3-2 — CLI render_grant_moment emits structured log line
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestCLIRenderGrantMomentLog:
    """Pin: CLI `render_grant_moment` emits `channel.render_grant_moment`."""

    @pytest.mark.asyncio
    async def test_cli_render_emits_log_line(self, caplog: pytest.LogCaptureFixture) -> None:
        import io

        adapter = CLIChannelAdapter(
            CLIChannelConfig(
                primary_channel_id="cli",
                output_stream=io.StringIO(),
                input_stream=io.StringIO(),
            )
        )
        await adapter.startup()
        try:
            with caplog.at_level(logging.INFO, logger="envoy.channels.cli"):
                await adapter.render_grant_moment(
                    _Request(request_id="r-cli-log", novelty_class="familiar_repeat")
                )
            events = [r.message for r in caplog.records]
            assert any("channel.render_grant_moment" in e for e in events)
        finally:
            await adapter.shutdown()


# ---------------------------------------------------------------------------
# MED-R3-05 (security) — InvalidDecisionError truncates attacker-influenced input
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestInvalidDecisionTruncation:
    """Pin: `InvalidDecisionError` truncates the rejected decision string.

    Reflected-input-in-error-message defense (CWE-117): a future WS handler
    that log-captures the exception MUST NOT leak attacker-controlled
    long-form prose or non-printable bytes into the log stream.
    """

    @pytest.mark.asyncio
    async def test_long_decision_string_truncated(self) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        await adapter.startup()
        try:
            attacker_payload = "force_approve" + "A" * 1000
            with pytest.raises(InvalidDecisionError) as excinfo:
                await adapter._resolve_pending_decision("r-1", attacker_payload)
            assert len(excinfo.value.decision) <= 32

        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_non_printable_bytes_stripped(self) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        await adapter.startup()
        try:
            payload = "force\x00\x01\x02\nappro\x7fve"
            with pytest.raises(InvalidDecisionError) as excinfo:
                await adapter._resolve_pending_decision("r-1", payload)
            assert "\x00" not in excinfo.value.decision
            assert "\x7f" not in excinfo.value.decision
        finally:
            await adapter.shutdown()


# ---------------------------------------------------------------------------
# LOW-R3-02 — unknown_request warn on _resolve_pending_decision
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_resolve_pending_decision_unknown_request_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
    await adapter.startup()
    try:
        sentinel_request_id = "request-DO-NOT-LEAK-c0ffee99"
        with caplog.at_level(logging.WARNING, logger="envoy.channels.web"):
            await adapter._resolve_pending_decision(sentinel_request_id, "approve_once")
        events = [r.message for r in caplog.records]
        assert any("channel.resolve_pending_decision.unknown_request" in e for e in events)
        # Sentinel MUST NOT appear in raw form — should be hashed.
        for record in caplog.records:
            assert sentinel_request_id not in record.getMessage()
            assert sentinel_request_id not in str(record.__dict__)
    finally:
        await adapter.shutdown()


# ---------------------------------------------------------------------------
# LOW-R3-1 — _register_pending idempotency invariant
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_register_pending_idempotent_returns_existing_future() -> None:
    """Pin: re-registering the same request_id returns the same Future."""
    adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
    await adapter.startup()
    try:
        first = adapter._register_pending("r-idem")
        second = adapter._register_pending("r-idem")
        assert first is second
        assert len(adapter._pending_decisions) == 1
    finally:
        for fut in adapter._pending_decisions.values():
            if not fut.done():
                fut.cancel()
        await adapter.shutdown()


# ---------------------------------------------------------------------------
# MED-R3-02 (security) — CLI render_grant_moment_request_prose canonical fields
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestRenderRequestProseCanonical:
    """Pin: render reads canonical `GrantMomentRequest` fields, not phantoms.

    Pre-R3 the renderer read `body` / `decision_options` / `visible_secret`
    which do NOT exist on the canonical dataclass — silent-fallback pattern.
    """

    def test_render_prose_includes_tool_name(self) -> None:
        rendered = CLIChannelAdapter._render_grant_moment_request_prose(
            _Request(request_id="r-canon", tool_name="send_email")
        )
        assert "send_email" in rendered
        assert "Proposed action: send_email" in rendered

    def test_render_prose_includes_why_asking_and_consequence(self) -> None:
        # Use a real `ConsequencePreview`-shaped object for the rendering.
        class _CP:
            budget_microdollars = 50_000  # $0.05
            reversibility = "reversible"
            data_classification = "Internal"

        rendered = CLIChannelAdapter._render_grant_moment_request_prose(
            _Request(
                request_id="r-canon",
                why_asking="Cron-scheduled invoice send",
                consequence_preview=_CP(),
            )
        )
        assert "Cron-scheduled invoice send" in rendered
        assert "reversible" in rendered
        assert "Internal" in rendered
        # Spend rendered as dollars (not raw microdollars) per /redteam R3
        # MED-R3-03 closure.
        assert "$0.05" in rendered or "$0.0500" in rendered

    def test_render_prose_missing_request_id_raises(self) -> None:
        with pytest.raises(ValueError, match="request_id"):
            CLIChannelAdapter._render_grant_moment_request_prose(_Request(request_id=""))  # type: ignore[arg-type]
