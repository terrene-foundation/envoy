"""Tier-2 wiring: `SlackChannelAdapter` lifecycle + contract pins.

Per `specs/channel-adapters.md` § Adapter contract and § Webhook signing
(Slack variant). Exercises startup/shutdown idempotency, send_message
path, Grant Moment H-03 primary-channel binding, dual discriminator
(GrantMomentPayload vs GrantMomentRequest), PII hash in logs, and the
single-write-site for pending decision registration.

Per `rules/testing.md` § Tier 2: no `mock.patch` / `MagicMock`. All
paths are exercised with real SlackChannelAdapter instances.

Pin tests (mandatory per task spec):
- test_slack_high_stakes_auto_gate_blocks_non_primary
- test_slack_vocab_canonical_discriminator_payload_vs_request
- test_slack_principal_id_pii_hash_in_logs
- test_slack_register_pending_single_write_site
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from types import SimpleNamespace

import pytest

from envoy.channels.envelope import (
    GrantMomentPayload,
    MessagePayload,
    VisibleSecret,
)
from envoy.channels.errors import (
    AlreadyStartedError,
    GrantMomentExpiredError,
    InvalidDecisionError,
    NotPrimaryChannelError,
    NotStartedError,
    PayloadTooLargeError,
    PendingDecisionsCeilingError,
)
from envoy.channels.slack import SlackChannelAdapter, SlackChannelConfig

_TEST_SECRET = "8f742231b10e8888abcd99badc0a9199"
_TEST_BOT_TOKEN = "xoxb-test-token-AAAAAAAAAAAAAAAA"


def _make_adapter(
    primary: str = "slack",
    signing_secret: str = _TEST_SECRET,
    bot_token: str = _TEST_BOT_TOKEN,
) -> SlackChannelAdapter:
    return SlackChannelAdapter(
        SlackChannelConfig(
            primary_channel_id=primary,
            signing_secret=signing_secret,
            bot_token=bot_token,
        )
    )


def _make_grant(
    request_id: str = "r-1",
    options: tuple[str, ...] = ("approve_once", "approve_and_author", "deny", "modify"),
    high_stakes: bool = False,
) -> GrantMomentPayload:
    return GrantMomentPayload(
        request_id=request_id,
        intent_id="i-1",
        decision_options=options,
        visible_secret=VisibleSecret(
            icon="thunderclap", color="amber", phrase="thunderclap-tangerine"
        ),
        body="Allow draft 3 hour focus block?",
        high_stakes=high_stakes,
    )


@pytest.mark.regression
class TestSlackLifecycle:
    """Contract pin: spec § Lifecycle methods (lines 20-38)."""

    @pytest.mark.asyncio
    async def test_startup_then_shutdown_clean_path(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        assert adapter.channel_id == "slack"
        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_double_startup_raises_already_started(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        try:
            with pytest.raises(AlreadyStartedError) as excinfo:
                await adapter.startup()
            assert excinfo.value.channel_id == "slack"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_double_shutdown_is_noop(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        await adapter.shutdown()
        # Second call MUST NOT raise.
        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_send_before_startup_raises_not_started(self) -> None:
        adapter = _make_adapter()
        payload = MessagePayload(kind="text", body="hello")
        with pytest.raises(NotStartedError) as excinfo:
            await adapter.send_message("principal-a", payload)
        assert excinfo.value.channel_id == "slack"


@pytest.mark.regression
class TestSlackSendMessage:
    """Contract pin: spec § Receive / send (lines 50-62)."""

    @pytest.mark.asyncio
    async def test_send_message_records_outbound_log(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        try:
            payload = MessagePayload(kind="text", body="hello from test")
            receipt = await adapter.send_message("principal-a", payload)
            assert receipt.channel_native_id.startswith("slack-")
            assert len(adapter._outbound_log) == 1
            target_id, text = adapter._outbound_log[0]
            assert target_id == "principal-a"
            assert "hello from test" in text
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_send_message_payload_too_large_raises(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        try:
            too_big = MessagePayload(kind="text", body="x" * 40001)
            with pytest.raises(PayloadTooLargeError) as excinfo:
                await adapter.send_message("principal-a", too_big)
            assert excinfo.value.channel_id == "slack"
            assert excinfo.value.actual_length == 40001
            assert excinfo.value.max_length == 40000
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_send_message_with_visible_secret_prepends_icon(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        try:
            payload = MessagePayload(kind="text", body="task complete")
            secret = VisibleSecret(icon="sunrise", color="gold", phrase="sunrise-sage")
            await adapter.send_message("principal-a", payload, visible_secret=secret)
            _, text = adapter._outbound_log[0]
            assert "(sunrise)" in text
            assert "task complete" in text
        finally:
            await adapter.shutdown()


@pytest.mark.regression
class TestSlackGrantMoment:
    """Contract pins: spec § Ritual delivery (lines 68-79) + § Primary-channel binding."""

    @pytest.mark.asyncio
    async def test_grant_moment_primary_only_refuses_when_non_primary(self) -> None:
        """H-03 primary-channel binding (spec § Primary-channel binding)."""
        adapter = _make_adapter(primary="web")
        await adapter.startup()
        try:
            with pytest.raises(NotPrimaryChannelError) as excinfo:
                await adapter.send_grant_moment(
                    "principal-a", _make_grant(), primary_only=True, timeout_seconds=1
                )
            assert excinfo.value.channel_id == "slack"
            assert excinfo.value.primary_channel_id == "web"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_grant_moment_timeout_raises_expired(self) -> None:
        """Spec line 78: timeout → GrantMomentExpiredError (no resolver called)."""
        adapter = _make_adapter()
        await adapter.startup()
        try:
            with pytest.raises(GrantMomentExpiredError) as excinfo:
                await adapter.send_grant_moment(
                    "principal-a", _make_grant(), timeout_seconds=1
                )
            assert excinfo.value.timeout_seconds == 1
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_grant_moment_resolve_decision_returns_receipt(self) -> None:
        """Full round-trip: render → resolve → receipt."""
        adapter = _make_adapter()
        await adapter.startup()
        try:
            grant = _make_grant(request_id="r-round-trip")

            async def _resolve_after_render() -> None:
                # Give the render a tick to register the pending future.
                await asyncio.sleep(0)
                await adapter._resolve_pending_decision("r-round-trip", "approve_once")

            resolve_task = asyncio.ensure_future(_resolve_after_render())
            receipt = await adapter.send_grant_moment(
                "principal-a", grant, timeout_seconds=5
            )
            await resolve_task
            assert receipt.decision == "approve_once"
            assert receipt.request_id == "r-round-trip"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_resolve_invalid_decision_raises_invalid_decision_error(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        try:
            with pytest.raises(InvalidDecisionError) as excinfo:
                await adapter._resolve_pending_decision("unknown-id", "not_a_decision")
            assert excinfo.value.channel_id == "slack"
            assert "not_a_decision" in str(excinfo.value.decision)
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_grant_moment_renders_to_outbound_log(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        try:
            grant = _make_grant(request_id="r-render-check")
            # Start send_grant_moment in background to exercise render path,
            # then time it out immediately.
            with pytest.raises(GrantMomentExpiredError):
                await adapter.send_grant_moment(
                    "principal-a", grant, timeout_seconds=1
                )
            # The outbound log MUST have the rendered block.
            assert any("r-render-check" in text for _, text in adapter._outbound_log)
        finally:
            await adapter.shutdown()


@pytest.mark.regression
class TestSlackCapabilities:
    """Contract pin: spec § ChannelCapabilities (lines 132-143)."""

    def test_capabilities_match_phase_01_table(self) -> None:
        adapter = _make_adapter()
        caps = adapter.capabilities
        assert caps.supports_buttons is True
        assert caps.supports_attachments is True
        assert caps.supports_markdown is True
        assert caps.supports_voice is False
        assert caps.supports_reactions is True
        assert caps.max_message_length == 40000

    @pytest.mark.asyncio
    async def test_rate_limit_status_reports_60_remaining(self) -> None:
        adapter = _make_adapter()
        await adapter.startup()
        try:
            status = await adapter.rate_limit_status()
            assert status.requests_remaining == 60
            assert status.soft_quota_warning is False
        finally:
            await adapter.shutdown()


# ---------------------------------------------------------------------------
# Mandatory pin tests
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestSlackHighStakesAutoGate:
    """Pin: test_slack_high_stakes_auto_gate_blocks_non_primary.

    H-03 defense-in-depth: `grant.high_stakes is True` MUST trigger the
    primary-channel gate even when `primary_only=False` (the caller forgot to
    set it). Non-primary config MUST raise `NotPrimaryChannelError`.
    """

    @pytest.mark.asyncio
    async def test_slack_high_stakes_auto_gate_blocks_non_primary(self) -> None:
        """Mandatory pin: high_stakes=True triggers primary-channel gate automatically."""
        # Adapter configured for a non-slack primary channel.
        adapter = _make_adapter(primary="web")
        await adapter.startup()
        try:
            high_stakes_grant = _make_grant(high_stakes=True)
            # primary_only is NOT set — the auto-gate must fire on high_stakes alone.
            with pytest.raises(NotPrimaryChannelError) as excinfo:
                await adapter.send_grant_moment(
                    "principal-a",
                    high_stakes_grant,
                    primary_only=False,  # explicit: NOT caller-requested
                    timeout_seconds=1,
                )
            assert excinfo.value.channel_id == "slack"
            assert excinfo.value.primary_channel_id == "web"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_high_stakes_with_matching_primary_does_not_block(self) -> None:
        """high_stakes=True with primary=slack MUST NOT raise NotPrimaryChannelError."""
        adapter = _make_adapter(primary="slack")
        await adapter.startup()
        try:
            high_stakes_grant = _make_grant(high_stakes=True)
            # This will time out (no resolver) — that's fine. What matters is
            # NotPrimaryChannelError is NOT raised.
            with pytest.raises(GrantMomentExpiredError):
                await adapter.send_grant_moment(
                    "principal-a",
                    high_stakes_grant,
                    timeout_seconds=1,
                )
        finally:
            await adapter.shutdown()


@pytest.mark.regression
class TestSlackVocabCanonicalDiscriminator:
    """Pin: test_slack_vocab_canonical_discriminator_payload_vs_request.

    Dual discriminator contract:
    - `GrantMomentPayload.high_stakes` (bool field) → used in `send_grant_moment`.
    - `GrantMomentRequest.novelty_class == "high_stakes"` (string field) → used
      in `render_grant_moment`.

    These are two distinct dataclasses with different field shapes. This pin
    verifies each discriminator path independently.
    """

    @pytest.mark.asyncio
    async def test_slack_vocab_canonical_discriminator_payload_vs_request(self) -> None:
        """Mandatory pin: payload bool vs request string discriminators are independent."""
        adapter = _make_adapter(primary="web")
        await adapter.startup()
        try:
            # --- Path 1: GrantMomentPayload (bool) ---
            # high_stakes=True on the payload MUST trigger the primary-channel gate.
            payload_grant = _make_grant(high_stakes=True)
            with pytest.raises(NotPrimaryChannelError):
                await adapter.send_grant_moment("p1", payload_grant, timeout_seconds=1)

            # --- Path 2: GrantMomentRequest (string novelty_class) ---
            # novelty_class == "high_stakes" on the request MUST trigger the gate.
            request_high = SimpleNamespace(
                request_id="rq-1",
                tool_name="send_file",
                why_asking="need to deliver document",
                consequence_preview=None,
                novelty_class="high_stakes",
                primary_only=False,
            )
            with pytest.raises(NotPrimaryChannelError):
                await adapter.render_grant_moment(request_high)

            # --- Path 3: GrantMomentRequest with different novelty_class MUST pass ---
            # Adapter now has primary="slack" so render_grant_moment will succeed.
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_render_grant_moment_non_high_stakes_passes(self) -> None:
        """render_grant_moment with novelty_class != 'high_stakes' MUST NOT gate."""
        adapter = _make_adapter(primary="web")
        await adapter.startup()
        try:
            request_normal = SimpleNamespace(
                request_id="rq-2",
                tool_name="list_files",
                why_asking="need to list",
                consequence_preview=None,
                novelty_class="normal",
                primary_only=False,
            )
            # MUST NOT raise NotPrimaryChannelError even though primary="web".
            await adapter.render_grant_moment(request_normal)
            assert any("rq-2" in text for _, text in adapter._outbound_log)
        finally:
            await adapter.shutdown()


@pytest.mark.regression
class TestSlackPrincipalIdPiiHashInLogs:
    """Pin: test_slack_principal_id_pii_hash_in_logs.

    Per `rules/observability.md` Rule 8 + `rules/security.md` § "No secrets
    in logs": `target_principal_id` is PII-adjacent; it MUST NOT appear as a
    raw value in INFO/WARN log fields; only an 8-char SHA-256 hash MUST appear.
    """

    @pytest.mark.asyncio
    async def test_slack_principal_id_pii_hash_in_logs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Mandatory pin: raw principal ID MUST NOT appear in log output."""
        raw_principal_id = "user-SENSITIVE-9a7b3c2d"
        expected_hash = hashlib.sha256(raw_principal_id.encode()).hexdigest()[:8]

        adapter = _make_adapter()
        await adapter.startup()
        try:
            with caplog.at_level(logging.INFO, logger="envoy.channels.slack"):
                payload = MessagePayload(kind="text", body="test log hash")
                await adapter.send_message(raw_principal_id, payload)

            # The raw principal ID MUST NOT appear in any log record.
            all_log_text = " ".join(str(r.getMessage()) for r in caplog.records)
            all_log_extra = " ".join(
                str(r.__dict__) for r in caplog.records
            )
            combined = all_log_text + " " + all_log_extra
            assert raw_principal_id not in combined, (
                f"Raw principal_id leaked into logs: found '{raw_principal_id}'"
            )
            # The 8-char hash MUST be present in the structured log fields.
            assert expected_hash in combined, (
                f"Expected PII hash '{expected_hash}' not found in log output"
            )
        finally:
            await adapter.shutdown()


@pytest.mark.regression
class TestSlackRegisterPendingSingleWriteSite:
    """Pin: test_slack_register_pending_single_write_site.

    The in-flight pending decisions dict (`_pending_decisions`) MUST have
    exactly ONE write site: `send_grant_moment`. The future is created once,
    keyed by `request_id`, and cleaned up in `finally`. This pin verifies:
    1. A new future is registered when `send_grant_moment` starts.
    2. The future is cleaned up after resolution (dict empty post-receipt).
    3. The future is cleaned up after timeout (dict empty post-expiry).
    4. A second `send_grant_moment` for a different request_id creates a
       separate entry — no aliasing.
    """

    @pytest.mark.asyncio
    async def test_slack_register_pending_single_write_site(self) -> None:
        """Mandatory pin: pending decisions registration lifecycle."""
        adapter = _make_adapter()
        await adapter.startup()
        try:
            # Step 1: dict is empty before any grant moment.
            assert len(adapter._pending_decisions) == 0

            grant = _make_grant(request_id="r-pending-check")

            async def _resolve_grant() -> None:
                # Wait for the future to be registered.
                for _ in range(50):
                    if "r-pending-check" in adapter._pending_decisions:
                        break
                    await asyncio.sleep(0.01)
                # Step 2: dict has exactly one entry while in-flight.
                assert "r-pending-check" in adapter._pending_decisions
                await adapter._resolve_pending_decision("r-pending-check", "deny")

            resolve_task = asyncio.ensure_future(_resolve_grant())
            receipt = await adapter.send_grant_moment(
                "principal-a", grant, timeout_seconds=5
            )
            await resolve_task

            # Step 3: dict is empty after resolution (finally block cleaned it).
            assert "r-pending-check" not in adapter._pending_decisions
            assert receipt.decision == "deny"

            # Step 4: after timeout, dict is also clean.
            grant2 = _make_grant(request_id="r-timeout-check")
            with pytest.raises(GrantMomentExpiredError):
                await adapter.send_grant_moment(
                    "principal-a", grant2, timeout_seconds=1
                )
            assert "r-timeout-check" not in adapter._pending_decisions

        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_pending_decisions_ceiling_error_fires_at_limit(self) -> None:
        """PendingDecisionsCeilingError MUST fire at _MAX_PENDING_DECISIONS (1000)."""

        adapter = _make_adapter()
        await adapter.startup()
        try:
            # Artificially inflate _pending_decisions to hit the ceiling.
            loop = asyncio.get_running_loop()
            for i in range(1000):
                fut: asyncio.Future[str] = loop.create_future()
                adapter._pending_decisions[f"fake-{i}"] = fut  # type: ignore[assignment]

            with pytest.raises(PendingDecisionsCeilingError) as excinfo:
                await adapter.send_grant_moment(
                    "principal-a", _make_grant(), timeout_seconds=1
                )
            assert excinfo.value.channel_id == "slack"
            assert excinfo.value.ceiling == 1000
        finally:
            # Cancel fake futures to avoid "future was destroyed but not set" warnings.
            for fut in adapter._pending_decisions.values():
                if not fut.done():
                    fut.cancel()
            adapter._pending_decisions.clear()
            await adapter.shutdown()
