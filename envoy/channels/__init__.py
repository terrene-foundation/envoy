"""envoy.channels — Phase 01 channel adapter foundation.

Implements `specs/channel-adapters.md` § Adapter contract + § Message envelope
+ § ChannelCapabilities + § Error taxonomy as the unified abstract surface
every Phase-01 channel adapter (CLI, Web, Telegram, Slack, Discord, WhatsApp,
iMessage, Signal) implements.

This shard ships:

- `ChannelAdapter` ABC (specs lines 14-130).
- `InboundMessage` + supporting dataclasses (specs lines 148-159, 132-143).
- 11 typed errors (specs lines 199-214) + `PhaseDeferredError` for Phase-02
  ritual-delivery surfaces.
- `CLIChannelAdapter` wrapping `kailash.channels.cli_channel.CLIChannel`.
- `WebChannelAdapter` wrapping `kailash.channels.api_channel.APIChannel`,
  localhost-bound with Origin allowlist enforcement per
  `rules/security.md` § "Network Transport Hardening".

Wave-4 next shards (deferred to siblings of this PR):

- Telegram + Slack + Discord adapters wrapping `nexus.transports.webhook`.
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
    NotPrimaryChannelError,
    NotStartedError,
    OverflowDropEvent,
    PayloadTooLargeError,
    PhaseDeferredError,
    PrincipalNotFoundError,
    RateLimitExceededError,
    SendTimeoutError,
    StartupTimeoutError,
)
from envoy.channels.web import WebChannelAdapter

__all__ = [
    # ABC
    "ChannelAdapter",
    # Concrete adapters (Phase 01 foundation surfaces)
    "CLIChannelAdapter",
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
    # 11 typed errors per spec § Error taxonomy + 2 hygiene errors
    # (NotStartedError + PhaseDeferredError)
    "AlreadyStartedError",
    "AuthenticationError",
    "ChannelAdapterError",
    "ChannelTransportError",
    "GrantMomentExpiredError",
    "NotPrimaryChannelError",
    "NotStartedError",
    "OverflowDropEvent",
    "PayloadTooLargeError",
    "PhaseDeferredError",
    "PrincipalNotFoundError",
    "RateLimitExceededError",
    "SendTimeoutError",
    "StartupTimeoutError",
]
