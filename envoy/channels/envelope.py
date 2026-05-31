"""envoy.channels.envelope — frozen dataclasses for the adapter contract.

Implements `specs/channel-adapters.md` § Message envelope and
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

# Canonical `VisibleSecret` ships in `envoy.trust.types` per
# `specs/boundary-conversation.md` § Questions S7 (set-visible-secret) — the
# Trust Vault is the authoritative producer; channels are consumers. Importing
# rather than redefining closes the spec H-1 finding (shape divergence) and
# satisfies `rules/specs-authority.md` Rule 5b (full-sibling re-derivation
# requires one canonical shape across the trust + channels boundary).
from envoy.trust.types import VisibleSecret as VisibleSecret

# Closed vocabulary for `GrantMomentReceipt.decision` per
# `specs/grant-moment.md` § Resolution shape — adapter MUST NOT silently coin
# an out-of-vocabulary decision string. Synchronised verbatim with
# `envoy.grant_moment.signed_consent.GrantMomentResult.decision`. Per /redteam
# R3 HIGH-R3-2 closure: `approve_author` (typo) is NOT a valid value — the
# canonical name is `approve_and_author`; production resolution paths never
# emit `approve_author`, so accepting it at the adapter boundary was the
# divergent-vocabulary failure mode.
GrantMomentDecision = Literal[
    "approve_once",
    "approve_and_author",
    "deny",
    "modify",
]


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
    """Result of `ChannelAdapter.rate_limit_status()` per spec § Capabilities + observability.

    Soft warning at 80% utilisation flips `soft_quota_warning=True`. The hard
    quota path raises `RateLimitExceededError` from `send_*` methods.

    `window_resets_at` is `None` when the channel has no enforced rate limit
    (e.g. CLI, Web — local-only surfaces). External-quota channels carry the
    UTC datetime at which the quota window rolls.
    """

    requests_remaining: int
    window_resets_at: datetime | None
    soft_quota_warning: bool


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

    `__post_init__` enforces non-empty `decision_options` — an empty options
    tuple makes `_coerce_decision` reach an out-of-bounds index AND lets a
    caller silently dispatch a grant the user cannot resolve. Fail loud at
    construction per `rules/zero-tolerance.md` Rule 3a (typed delegate guards).
    """

    request_id: str
    intent_id: str
    decision_options: tuple[str, ...]
    visible_secret: VisibleSecret
    body: str
    high_stakes: bool

    def __post_init__(self) -> None:
        if not self.decision_options:
            raise ValueError(
                "GrantMomentPayload.decision_options MUST be non-empty — "
                "a Grant Moment with no decision options cannot resolve."
            )


@dataclass(frozen=True, slots=True)
class GrantMomentReceipt:
    """Wire-shape return of `send_grant_moment` (spec § Ritual delivery).

    `decision` is the option from `GrantMomentPayload.decision_options` the
    user picked (constrained to the `GrantMomentDecision` closed vocabulary);
    `channel_signature` is a channel-native attestation (CLI: empty; Web:
    SHA-256 of session cookie; messaging: per-vendor callback nonce verified
    by the WebhookSigner).

    `request_id` extends the spec's 4-field shape (§ Ritual delivery) by one field
    — the original-request correlation token. The extension is documented
    inline in `specs/channel-adapters.md` § Ritual delivery (Phase 01 surface
    contract) per `rules/specs-authority.md` Rule 6 deviation acknowledgement
    so the runtime can correlate without holding a side-table.
    """

    request_id: str
    grant_id: str
    decision: GrantMomentDecision
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
    """8-field envelope per spec § Message envelope.

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
