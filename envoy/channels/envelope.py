"""envoy.channels.envelope — frozen dataclasses for the adapter contract.

Implements `specs/channel-adapters.md` § Message envelope (lines 148-159) and
§ `ChannelCapabilities` (lines 132-143) verbatim. Every concrete adapter
returns and accepts only these shapes; per-channel wire formats translate at
the adapter boundary.

Payload dataclasses for the 4 ritual-delivery methods carry the field shape
the runtime composes; the runtime owns rendering semantics (per channel
adapter UI rendering) — these dataclasses are the wire-shape only.

Per `rules/zero-tolerance.md` Rule 2: no `pass`-bodied stubs. Phase-02
ritual-delivery payload shapes ship with explicit `Phase 02` provenance
docstrings and the receiving methods raise `PhaseDeferredError` until the
Phase 02 facade wires them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class ChannelCapabilities:
    """Static capability descriptor per channel (spec § ChannelCapabilities).

    Phase 01 surfaces declare capabilities at construction; the runtime
    consults `ChannelAdapter.capabilities` before routing a payload (e.g.,
    refusing to send a `supports_attachments=False` channel an attachment).

    All 6 fields are explicit (no defaults) — every adapter MUST declare
    every capability, so a new capability in `specs/channel-adapters.md`
    landing later loudly breaks every adapter at construction. That is the
    failure mode this dataclass is designed to surface, not hide.
    """

    supports_buttons: bool
    supports_attachments: bool
    supports_markdown: bool
    supports_voice: bool
    supports_reactions: bool
    max_message_length: int


@dataclass(frozen=True, slots=True)
class RateLimitStatus:
    """Result of `ChannelAdapter.rate_limit_status()` per spec lines 124-129.

    Soft warning at 80% utilisation flips `soft_quota_warning=True`. The hard
    quota path raises `RateLimitExceededError` from `send_*` methods.
    """

    requests_remaining: int
    window_resets_at: datetime
    soft_quota_warning: bool


@dataclass(frozen=True, slots=True)
class VisibleSecret:
    """Per-channel visible-secret carrier (T-018 dialog-spoofing defense).

    The phrase travels with the GrantMomentRequest dispatched to a channel
    so the adapter can render the secret next to the action prompt. The
    `phrase` field is treated as a plaintext string at this layer; the
    Trust Vault stores the canonical form and the renderer compares hashes.

    Per `rules/security.md` § "No secrets in logs", VisibleSecret MUST NEVER
    appear in a log line — adapters that log a VisibleSecret are blocked by
    `tests/regression/test_t070_clipboard_autoclear.py` and the redaction
    review gate.
    """

    phrase: str
    icon: str


@dataclass(frozen=True, slots=True)
class MessagePayload:
    """Wire-shape payload for `send_message` (spec § Receive / send).

    Free-form `body` plus structured `kind` discriminator (one of
    `"text" | "system_notice" | "ack" | "error_notice"`). Per-channel
    adapters translate `kind` to channel-native formatting.
    """

    kind: Literal["text", "system_notice", "ack", "error_notice"]
    body: str
    attachments: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GrantMomentPayload:
    """Wire-shape payload for `send_grant_moment` (spec § Ritual delivery).

    The runtime constructs this from `envoy.grant_moment.runtime` M0 issue
    and dispatches via `ChannelHandoff.dispatch(request, channel, timeout)`
    per `01-analysis/16-channel-adapters-implementation.md` § 3 line 36.
    """

    request_id: str
    intent_id: str
    decision_options: tuple[str, ...]
    visible_secret: VisibleSecret
    body: str
    high_stakes: bool


@dataclass(frozen=True, slots=True)
class GrantMomentReceipt:
    """Wire-shape return of `send_grant_moment` (spec lines 78-79).

    `decision` is the option from `GrantMomentPayload.decision_options` the
    user picked; `channel_signature` is a channel-native attestation
    (CLI: empty; Web: SHA-256 of session cookie; messaging: per-vendor
    callback nonce verified by the WebhookSigner).
    """

    request_id: str
    grant_id: str
    decision: str
    decided_at: datetime
    channel_signature: str


@dataclass(frozen=True, slots=True)
class SendReceipt:
    """Wire-shape return of `send_message` / `send_digest` / `send_monthly_report`.

    `channel_native_id` is the channel-native message identifier (Telegram
    `message_id`, Slack `ts`, Discord `id`, CLI: monotonic counter,
    Web: SSE event id). `receipt_hash` is non-None only on the monthly-report
    path per `specs/monthly-trust-report.md`.
    """

    message_id: str
    delivered_at: datetime
    channel_native_id: str
    receipt_hash: str | None = None


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """8-field envelope per spec § Message envelope (lines 148-159).

    `principal_genesis_id` is verified at the adapter boundary (the adapter
    refuses messages whose claimed sender does not match the bound bot's
    known principal mapping; mismatch raises `PrincipalNotFoundError`).
    `timestamp` is adapter-assigned UTC per the cited spec.
    """

    channel_id: str
    session_id: str
    principal_genesis_id: str
    direction: Literal["inbound", "outbound"]
    content_trust_level: Literal["user", "system", "tool", "agent"]
    payload: MessagePayload
    visible_secret_rendered: VisibleSecret | None
    timestamp: datetime


# ---------------------------------------------------------------------------
# Phase 02 ritual-delivery payload shapes
#
# Phase 01 does NOT wire `send_posture_review` or `send_monthly_report` —
# the receiving methods raise `PhaseDeferredError`. The payload dataclasses
# ship today because downstream catch sites + type checkers need the wire
# shape to compile (per `rules/zero-tolerance.md` Rule 6: implement fully or
# document the deferral with a typed error, never a `pass` body).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DailyDigestPayload:
    """`specs/daily-digest.md` § Payload schema (Phase 01 sibling shard 11).

    Adapters render this as a single message; `markdown_body` is the
    canonical pre-rendered form (channels lacking markdown strip per their
    own renderer). Sibling shard 11 (envoy.daily_digest) owns the field
    schema; this shape captures the wire surface adapter callers see.
    """

    digest_date: str
    markdown_body: str
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WeeklyPostureReviewPayload:
    """`specs/weekly-posture-review.md` payload (Phase 02 scope).

    Captured here so the abstract method signature compiles today; the
    adapter implementation raises `PhaseDeferredError` until shard 11+.
    """

    review_id: str
    week_starts: str
    state: Literal["W0", "W1", "W2", "W3", "W4", "W5", "W6", "W_PAUSED"]
    summary_body: str


@dataclass(frozen=True, slots=True)
class PostureReviewReceipt:
    """`send_posture_review` return per spec lines 99-100 (Phase 02 scope)."""

    review_id: str
    current_state: str
    persisted_decisions: tuple[str, ...]
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class MonthlyTrustReportPayload:
    """`specs/monthly-trust-report.md` payload (Phase 02 scope)."""

    report_id: str
    month: str
    pdf_url: str
    json_url: str
    summary_body: str
