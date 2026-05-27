"""envoy.channels — Phase 01 channel adapter foundation.

Implements `specs/channel-adapters.md` § Adapter contract + § Message envelope
+ § ChannelCapabilities + § Error taxonomy as the unified abstract surface
every Phase-01 channel adapter (CLI, Web, Telegram, Slack, Discord, WhatsApp,
iMessage, Signal) implements.

This shard ships:

- `ChannelAdapter` ABC (specs § Adapter contract).
- `InboundMessage` + supporting dataclasses (specs § Message envelope).
- Typed errors (specs § Error taxonomy) + `PhaseDeferredError` for Phase-02
  ritual-delivery surfaces.
- `CLIChannelAdapter` wrapping `kailash.channels.cli_channel.CLIChannel`.
- `WebChannelAdapter` wrapping `kailash.channels.api_channel.APIChannel`,
  localhost-bound with Origin allowlist enforcement per
  `rules/security.md` § "Network Transport Hardening".

Wave-4 shipped Telegram, Slack, and Discord adapters (this PR). Deferred
to later shards:

- WhatsApp + iMessage + Signal caveated channels.
- `InboundRouter` concurrent fan-out across registered adapters.
- `envoy.daily_digest` scheduler producing `DailyDigestPayload` payloads.

Composition philosophy per `rules/orphan-detection.md` Rule 1 + Rule 3:
every adapter is a consumer of upstream primitives; explicit constructor
dependency injection; no global lookups.
"""

from __future__ import annotations

from envoy.channels.adapter import ChannelAdapter
from envoy.channels.cli import CLIChannelAdapter
from envoy.channels.discord import DiscordChannelAdapter
from envoy.channels.envelope import (
    ChannelCapabilities,
    DailyDigestPayload,
    GrantMomentPayload,
    GrantMomentReceipt,
    InboundMessage,
    MessagePayload,
    MonthlyTrustReportPayload,
    PostureReviewReceipt,
    RateLimitStatus,
    SendReceipt,
    VisibleSecret,
    WeeklyPostureReviewPayload,
)
from envoy.channels.errors import (
    AlreadyStartedError,
    AuthenticationError,
    ChannelAdapterError,
    ChannelTransportError,
    GrantMomentExpiredError,
    InvalidDecisionError,
    NotPrimaryChannelError,
    NotStartedError,
    OverflowDropEvent,
    PayloadTooLargeError,
    PendingDecisionsCeilingError,
    PhaseDeferredError,
    PrincipalNotFoundError,
    RateLimitExceededError,
    SendTimeoutError,
    StartupTimeoutError,
)
from envoy.channels.slack import SlackChannelAdapter
from envoy.channels.telegram import TelegramChannelAdapter
from envoy.channels.web import WebChannelAdapter

__all__ = [
    # ABC
    "ChannelAdapter",
    # Concrete adapters (Phase 01 foundation surfaces)
    "CLIChannelAdapter",
    "DiscordChannelAdapter",
    "SlackChannelAdapter",
    "TelegramChannelAdapter",
    "WebChannelAdapter",
    # Envelope + payloads
    "ChannelCapabilities",
    "DailyDigestPayload",
    "GrantMomentPayload",
    "GrantMomentReceipt",
    "InboundMessage",
    "MessagePayload",
    "MonthlyTrustReportPayload",
    "PostureReviewReceipt",
    "RateLimitStatus",
    "SendReceipt",
    "VisibleSecret",
    "WeeklyPostureReviewPayload",
    # 11 spec-taxonomy errors + 4 adapter-internal hygiene errors
    # (spec § Adapter-internal hygiene errors) + 1 base class (ChannelAdapterError)
    # = 16 exported error symbols.  OverflowDropEvent is Ledger-only (not raised).
    "AlreadyStartedError",
    "AuthenticationError",
    "ChannelAdapterError",
    "ChannelTransportError",
    "GrantMomentExpiredError",
    "InvalidDecisionError",
    "NotPrimaryChannelError",
    "NotStartedError",
    "OverflowDropEvent",
    "PayloadTooLargeError",
    "PendingDecisionsCeilingError",
    "PhaseDeferredError",
    "PrincipalNotFoundError",
    "RateLimitExceededError",
    "SendTimeoutError",
    "StartupTimeoutError",
]
