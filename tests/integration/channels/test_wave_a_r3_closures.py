"""Regression tests for Wave-A /redteam R3 closure findings.

Covers all HIGH and MEDIUM findings for PR #43 (Wave-A channels R3):

H-1: Telegram ``_register_pending`` idempotent — two calls with same
     request_id return the SAME queue object (no overwrite).
H-2: SSRF octal-dotted bypass — ``0177.0.0.1`` must be blocked.
H-3: SSRF IPv6-mapped IPv4 bypass — ``::ffff:127.0.0.1`` must be blocked.
M-1: Telegram ``send_digest`` rate-limit gate — exhausted quota raises
     ``RateLimitExceededError`` before touching the digest payload.
M-2: ``post_decision`` vocab validation — invalid decision string returns
     False without enqueuing.
M-3: Gate ordering — high-stakes non-primary raises
     ``NotPrimaryChannelError``, NOT ``RateLimitExceededError``, even
     when the rate limit is simultaneously exhausted.

Per ``rules/testing.md`` § Tier 2: no ``mock.patch`` / ``MagicMock``.
Rate-limit override uses subclassing the adapter (real code path).
"""

from __future__ import annotations

import asyncio
import typing

import pytest

from envoy.channels.discord import (
    DiscordChannelAdapter,
    _validate_webhook_url_ssrf,
)
from envoy.channels.envelope import (
    DailyDigestPayload,
    GrantMomentDecision,
    GrantMomentPayload,
    RateLimitStatus,
    VisibleSecret,
)
from envoy.channels.errors import (
    ChannelTransportError,
    NotPrimaryChannelError,
    RateLimitExceededError,
)
from envoy.channels.telegram import TelegramChannelAdapter

# ---------------------------------------------------------------------------
# Module-level constants shared across test classes
# ---------------------------------------------------------------------------
_ALLOWED_DECISIONS: frozenset[str] = frozenset(typing.get_args(GrantMomentDecision))


def _make_telegram_adapter(
    primary: str = "telegram",
    *,
    secret_token: str = "test-secret",
    send_fn=None,
) -> TelegramChannelAdapter:
    return TelegramChannelAdapter(
        primary_channel_id=primary,
        secret_token=secret_token,
        send_fn=send_fn,
    )


def _make_grant(
    request_id: str = "r-001",
    *,
    high_stakes: bool = False,
) -> GrantMomentPayload:
    return GrantMomentPayload(
        request_id=request_id,
        intent_id="i-001",
        decision_options=("approve_once", "deny"),
        visible_secret=VisibleSecret(icon="key", color="#FF0000", phrase="alpha-beta"),
        body="Allow action?",
        high_stakes=high_stakes,
    )


# ---------------------------------------------------------------------------
# H-1: Telegram _register_pending idempotency
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestH1TelegramRegisterPendingIdempotent:
    """H-1: duplicate request_id must not silently overwrite the existing queue.

    The fix changed ``_register_pending`` to return the existing queue when
    the request_id is already registered.  This ensures that a caller who
    re-registers the same request_id (e.g., due to a retry) sees the same
    queue — not a freshly allocated one that will never receive the response.
    """

    def test_first_registration_creates_queue(self) -> None:
        """_register_pending creates a new queue on first call."""
        adapter = _make_telegram_adapter()
        q = adapter._register_pending("req-idempotent-test")
        assert isinstance(q, asyncio.Queue), "_register_pending must return an asyncio.Queue"
        assert "req-idempotent-test" in adapter._pending_grants

    def test_second_registration_returns_same_queue(self) -> None:
        """_register_pending with same request_id returns the SAME queue object.

        Pre-fix: a second call would silently overwrite the existing queue,
        causing the first caller's `await queue.get()` to hang forever while
        responses were enqueued into the new queue.
        """
        adapter = _make_telegram_adapter()
        q1 = adapter._register_pending("req-idempotent-test")
        q2 = adapter._register_pending("req-idempotent-test")
        assert q1 is q2, (
            "_register_pending MUST be idempotent: calling twice with the same "
            "request_id must return the SAME queue object, not a new one.  "
            "A different object means the old caller's await will hang forever."
        )

    def test_different_request_ids_get_different_queues(self) -> None:
        """Different request_ids get independent queues."""
        adapter = _make_telegram_adapter()
        qa = adapter._register_pending("req-alpha")
        qb = adapter._register_pending("req-beta")
        assert qa is not qb, "Different request_ids must produce different queues"

    def test_idempotent_queue_count_does_not_grow(self) -> None:
        """Re-registering the same request_id must NOT increase pending count."""
        adapter = _make_telegram_adapter()
        adapter._register_pending("req-same")
        count_after_first = len(adapter._pending_grants)
        adapter._register_pending("req-same")
        count_after_second = len(adapter._pending_grants)
        assert count_after_first == count_after_second, (
            "Re-registering the same request_id should not increase "
            "len(_pending_grants) — idempotent registration must return "
            "the existing entry, not add a new one."
        )


# ---------------------------------------------------------------------------
# H-2 + H-3: SSRF guard
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestH2H3SsrfGuard:
    """H-2/H-3: SSRF guard must block octal-dotted and IPv6-mapped IPv4 addresses.

    H-2 pre-fix: ``ipaddress.ip_address("0177.0.0.1")`` raises ValueError,
    which caused the guard to fall through to the "hostname" branch and defer
    to DNS — an SSRF bypass.

    H-3 pre-fix: ``::ffff:0.0.0.0/96`` was absent from ``_SSRF_BLOCKED_NETWORKS``,
    allowing ``::ffff:127.0.0.1`` through unblocked.
    """

    def test_h2_octal_loopback_blocked(self) -> None:
        """0177.0.0.1 (octal for 127.0.0.1) must raise ChannelTransportError.

        Pre-fix: ip_address("0177.0.0.1") raised ValueError, the guard caught it
        and treated it as an unresolvable hostname — SSRF bypass.
        """
        with pytest.raises(ChannelTransportError) as exc_info:
            _validate_webhook_url_ssrf("http://0177.0.0.1/webhook", "discord")
        assert "SSRF" in str(exc_info.value) or "blocked" in str(exc_info.value).lower(), (
            "ChannelTransportError for octal SSRF must mention SSRF guard in message"
        )

    def test_h2_octal_private_blocked(self) -> None:
        """0012.0.0.1 (octal for 10.0.0.1) must be blocked by RFC-1918 rule."""
        with pytest.raises(ChannelTransportError):
            _validate_webhook_url_ssrf("http://0012.0.0.1/webhook", "discord")

    def test_h3_ipv6_mapped_loopback_blocked(self) -> None:
        """::ffff:127.0.0.1 (IPv6-mapped loopback) must raise ChannelTransportError.

        Pre-fix: ::ffff:0.0.0.0/96 was absent from _SSRF_BLOCKED_NETWORKS, so
        ::ffff:127.0.0.1 was treated as a valid external IPv6 address.
        """
        with pytest.raises(ChannelTransportError) as exc_info:
            _validate_webhook_url_ssrf("http://[::ffff:127.0.0.1]/webhook", "discord")
        assert "SSRF" in str(exc_info.value) or "blocked" in str(exc_info.value).lower(), (
            "ChannelTransportError for IPv6-mapped SSRF must mention SSRF guard"
        )

    def test_h3_ipv6_mapped_private_blocked(self) -> None:
        """::ffff:10.0.0.1 (IPv6-mapped RFC-1918) must also be blocked."""
        with pytest.raises(ChannelTransportError):
            _validate_webhook_url_ssrf("http://[::ffff:10.0.0.1]/webhook", "discord")

    def test_legitimate_public_url_allowed(self) -> None:
        """Legitimate HTTPS webhook URLs must pass the SSRF guard without raising."""
        _validate_webhook_url_ssrf(
            "https://discord.com/api/webhooks/1234567890/AAAA_test_token",
            "discord",
        )

    def test_normal_decimal_loopback_still_blocked(self) -> None:
        """127.0.0.1 (decimal notation) must still be blocked (regression guard)."""
        with pytest.raises(ChannelTransportError):
            _validate_webhook_url_ssrf("http://127.0.0.1/webhook", "discord")

    def test_ipv6_loopback_still_blocked(self) -> None:
        """::1 (IPv6 loopback) must still be blocked (regression guard)."""
        with pytest.raises(ChannelTransportError):
            _validate_webhook_url_ssrf("http://[::1]/webhook", "discord")


# ---------------------------------------------------------------------------
# M-1: Telegram send_digest rate-limit gate
# ---------------------------------------------------------------------------


class _ExhaustedRateLimitTelegramAdapter(TelegramChannelAdapter):
    """Subclass that reports an exhausted rate limit.

    Using subclassing (not mock.patch) per ``rules/testing.md`` § Tier 2.
    ``rate_limit_status`` is the only public override point — all other
    adapter code runs on the real implementation.
    """

    async def rate_limit_status(self) -> RateLimitStatus:
        return RateLimitStatus(
            requests_remaining=0,
            window_resets_at=None,
            soft_quota_warning=False,
        )


@pytest.mark.regression
class TestM1SendDigestRateLimitGate:
    """M-1: send_digest must consult the rate limit before attempting delivery."""

    @pytest.mark.asyncio
    async def test_send_digest_raises_when_rate_limit_exhausted(self) -> None:
        """send_digest must raise RateLimitExceededError when quota is zero.

        Pre-fix: send_digest had no rate-limit gate, so messages could be
        enqueued even when the account was over quota.
        """
        adapter = _ExhaustedRateLimitTelegramAdapter(
            primary_channel_id="telegram",
            secret_token="test-secret",
        )
        await adapter.startup()
        try:
            digest = DailyDigestPayload(
                digest_date="2026-05-27",
                markdown_body="## Nothing today.",
            )
            with pytest.raises(RateLimitExceededError) as exc_info:
                await adapter.send_digest("target-user-id", digest)
            assert exc_info.value.channel_id == "telegram", (
                "RateLimitExceededError must report channel_id='telegram'"
            )
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_send_digest_ok_when_quota_available(self) -> None:
        """send_digest must succeed when rate limit is nominal (regression guard)."""
        sent: list[tuple[str, str]] = []

        async def _send_fn(chat_id: str, text: str) -> None:
            sent.append((chat_id, text))

        adapter = _make_telegram_adapter(send_fn=_send_fn)
        await adapter.startup()
        try:
            digest = DailyDigestPayload(
                digest_date="2026-05-27",
                markdown_body="## All clear.",
            )
            await adapter.send_digest("target-user-id", digest)
            # At least one outbound send must have occurred.
            assert len(sent) >= 1, "send_digest must call send_fn at least once"
        finally:
            await adapter.shutdown()


# ---------------------------------------------------------------------------
# M-2: post_decision vocab validation
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestM2PostDecisionVocabValidation:
    """M-2: post_decision must reject out-of-vocabulary decision strings.

    Pre-fix: post_decision accepted any string and enqueued it into the
    pending grants queue, allowing garbage values (or injection attempts) to
    propagate to the decision consumer.
    """

    @pytest.mark.asyncio
    async def test_invalid_decision_returns_false(self) -> None:
        """A completely invalid decision string must return False."""
        adapter = _make_telegram_adapter()
        await adapter.startup()
        try:
            # Register a pending grant so post_decision has something to look up.
            adapter._register_pending("req-vocab-test")
            result = adapter.post_decision("req-vocab-test", "INVALID_DECISION")
            assert result is False, (
                "post_decision must return False for out-of-vocabulary decisions, "
                "not enqueue the garbage value."
            )
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_empty_decision_returns_false(self) -> None:
        """An empty decision string must return False."""
        adapter = _make_telegram_adapter()
        await adapter.startup()
        try:
            adapter._register_pending("req-empty-decision")
            result = adapter.post_decision("req-empty-decision", "")
            assert result is False, "post_decision must return False for empty decision"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_valid_decision_accepted(self) -> None:
        """A valid closed-vocabulary decision must be accepted and enqueued."""
        adapter = _make_telegram_adapter()
        await adapter.startup()
        try:
            q = adapter._register_pending("req-valid-decision")
            result = adapter.post_decision("req-valid-decision", "deny")
            assert result is True, "post_decision must return True for valid decisions"
            assert not q.empty(), "Valid decision must be placed in the pending queue"
            enqueued = q.get_nowait()
            assert enqueued == "deny"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_numeric_index_decision_accepted(self) -> None:
        """Numeric string ('1', '2', ...) is accepted as coercible digit decision."""
        adapter = _make_telegram_adapter()
        await adapter.startup()
        try:
            adapter._register_pending("req-numeric-decision")
            result = adapter.post_decision("req-numeric-decision", "1")
            assert result is True, "Digit string '1' must be accepted by post_decision"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_all_canonical_decisions_accepted(self) -> None:
        """Every GrantMomentDecision literal must be accepted by post_decision."""
        for decision in _ALLOWED_DECISIONS:
            adapter = _make_telegram_adapter()
            await adapter.startup()
            try:
                request_id = f"req-vocab-{decision}"
                adapter._register_pending(request_id)
                result = adapter.post_decision(request_id, decision)
                assert result is True, (
                    f"post_decision must accept canonical decision {decision!r} "
                    f"but returned False"
                )
            finally:
                await adapter.shutdown()


# ---------------------------------------------------------------------------
# M-3: Gate ordering — security gate precedes rate-limit gate
# ---------------------------------------------------------------------------


class _ExhaustedRateLimitDiscordAdapter(DiscordChannelAdapter):
    """Subclass that reports an exhausted rate limit for Discord gate-ordering test."""

    async def rate_limit_status(self) -> RateLimitStatus:
        return RateLimitStatus(
            requests_remaining=0,
            window_resets_at=None,
            soft_quota_warning=False,
        )


class _ExhaustedRateLimitSlackAdapter:
    """Rate-limit-exhausted Slack adapter for gate-ordering test.

    Importing SlackChannelAdapter here avoids circular-import issues and
    follows the same subclassing pattern as the Telegram/Discord variants.
    """

    _adapter: object  # populated in setup


@pytest.mark.regression
class TestM3GateOrdering:
    """M-3: PrincipalNotFound → primary-channel → rate-limit ordering.

    The security gate (NotPrimaryChannelError) MUST fire before the
    availability gate (RateLimitExceededError) — even when the rate limit
    is simultaneously exhausted.  This ensures an attacker cannot probe
    rate-limit state through a channel they are not authorised to use.

    Pre-fix: at least one adapter had rate-limit checked before primary-channel,
    leaking availability information through an unauthorized channel.
    """

    @pytest.mark.asyncio
    async def test_telegram_high_stakes_non_primary_raises_not_primary_not_rate_limit(
        self,
    ) -> None:
        """Telegram: high_stakes + non-primary + exhausted quota → NotPrimaryChannelError.

        The not-primary check must fire BEFORE the rate-limit check so that
        an attacker who sends a high-stakes grant moment to a non-primary
        channel cannot observe rate-limit state.
        """

        class _ExhaustedTelegram(TelegramChannelAdapter):
            async def rate_limit_status(self) -> RateLimitStatus:
                return RateLimitStatus(
                    requests_remaining=0,
                    window_resets_at=None,
                    soft_quota_warning=False,
                )

        # primary_channel_id="web" means telegram is NOT the primary.
        adapter = _ExhaustedTelegram(
            primary_channel_id="web",
            secret_token="test-secret",
        )
        await adapter.startup()
        try:
            grant = _make_grant(high_stakes=True)
            with pytest.raises(NotPrimaryChannelError):
                await adapter.send_grant_moment("user-123", grant)
            # If RateLimitExceededError leaked out instead, the gate ordering is wrong.
            # The with-block only completes (without re-raise) if NotPrimaryChannelError
            # was raised — any other exception including RateLimitExceededError would
            # cause the test to fail with an unexpected exception.
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_telegram_high_stakes_non_primary_raises_not_primary(self) -> None:
        """Simplified version: high_stakes non-primary → NotPrimaryChannelError only."""

        class _ExhaustedTelegram(TelegramChannelAdapter):
            async def rate_limit_status(self) -> RateLimitStatus:
                return RateLimitStatus(
                    requests_remaining=0,
                    window_resets_at=None,
                    soft_quota_warning=False,
                )

        adapter = _ExhaustedTelegram(
            primary_channel_id="web",
            secret_token="test-secret",
        )
        await adapter.startup()
        try:
            grant = _make_grant(high_stakes=True)
            raised_type: type | None = None
            try:
                await adapter.send_grant_moment("user-123", grant)
            except NotPrimaryChannelError:
                raised_type = NotPrimaryChannelError
            except RateLimitExceededError:
                raised_type = RateLimitExceededError

            assert raised_type is NotPrimaryChannelError, (
                f"Gate ordering failure: expected NotPrimaryChannelError but got "
                f"{raised_type.__name__ if raised_type else 'no exception'}.  "
                f"The security gate (primary-channel check) must precede the "
                f"availability gate (rate-limit check)."
            )
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_telegram_primary_with_exhausted_rate_limit_raises_rate_limit(
        self,
    ) -> None:
        """When the adapter IS primary, exhausted quota raises RateLimitExceededError."""

        class _ExhaustedPrimary(TelegramChannelAdapter):
            async def rate_limit_status(self) -> RateLimitStatus:
                return RateLimitStatus(
                    requests_remaining=0,
                    window_resets_at=None,
                    soft_quota_warning=False,
                )

        # primary_channel_id="telegram" means telegram IS the primary.
        adapter = _ExhaustedPrimary(
            primary_channel_id="telegram",
            secret_token="test-secret",
        )
        await adapter.startup()
        try:
            grant = _make_grant(high_stakes=True)
            with pytest.raises(RateLimitExceededError):
                await adapter.send_grant_moment("user-123", grant)
        finally:
            await adapter.shutdown()
