# channel-adapters

## Purpose

8 Phase-01 surface (CLI + Web + 6 messaging channels) and 17 Phase-04 channels. Adapter contract + per-channel specs + compliance.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/07-channels-and-adapters.md v1`.
- **Threats mitigated:** T-018 visible secret propagation, T-070 side channels, T-080 network MITM, T-023 Signal legal gate.
- **BETs tested:** BET-6 contract parity across channels, BET-12 channel-native UX.

## Adapter contract

`ChannelAdapter` is the abstract base class every channel implementation extends. All methods are async (Phase 01 Python uses `asyncio`; Phase 02 Rust uses `tokio`). Per-method signatures, return types, timeout semantics, and rate-limit / failure semantics:

### Lifecycle methods

```python
@property
def channel_id(self) -> str:
    """Stable identifier (e.g. "telegram", "signal", "slack"). MUST be unique across registered adapters."""

async def startup(self, config: ChannelConfig) -> None:
    """
    Initialize adapter (open WebSocket, register webhook, authenticate).
    Timeout: 10s; fail-closed → raises StartupTimeoutError.
    Rate-limit: N/A (one-shot).
    Idempotent: calling twice MUST raise AlreadyStartedError.
    """

async def shutdown(self, drain_timeout_seconds: int = 5) -> None:
    """
    Drain pending sends, close transports.
    Timeout: drain_timeout_seconds (default 5s); after timeout, force-close.
    Idempotent: calling on already-shutdown adapter is a no-op.
    Pending in-flight grant moment coroutines are cancelled: Future-based adapters
    (Web, Slack, Discord) call `.cancel()` on each pending Future; queue-based
    adapters (Telegram) push a shutdown sentinel into each pending queue. Awaiting
    `send_grant_moment` calls raise `GrantMomentExpiredError`.
    """
```

### Receive / send

```python
def receive_message(self) -> AsyncIterator[InboundMessage]:
    """
    Yield inbound messages as they arrive. Returns an async iterator
    (defined as plain `def` returning `AsyncIterator`, NOT `async def` —
    the function returns the iterator; the caller drives it with `async for`).
    Backpressure: bounded queue size 100 per channel; overflow drops with `OverflowDropEvent` to Ledger
    via WARN log (`channel.inbound.overflow_drop`).
    Failure semantics: transport errors propagated as `ChannelTransportError` and fed to runtime's reconnection backoff.
    """

async def send_message(
    self, target_principal_id: str, payload: MessagePayload, *,
    visible_secret: VisibleSecret | None = None,
    timeout_seconds: int = 10,
) -> SendReceipt:
    """
    Deliver a structured message.
    Timeout: timeout_seconds; on timeout raises `SendTimeoutError`.
    Rate-limit: per-channel `rate_limit_status()` consulted before send; on quota exhaustion raises `RateLimitExceededError` with `retry_after_seconds`.
    Failure semantics: transient errors retried with jitter (max 3 attempts); permanent failures (auth, principal-not-found) raise immediately.
    Returns `SendReceipt {message_id, delivered_at, channel_native_id}`.
    """
```

### Ritual delivery (Phase 01 surface contract)

Phase 01 wires **2 of 4** ritual-delivery methods (`send_grant_moment` + `send_digest`); `send_posture_review` + `send_monthly_report` raise `envoy.channels.errors.PhaseDeferredError` from the ABC default and are wired in Phase 02 (`specs/weekly-posture-review.md` + `specs/monthly-trust-report.md`). All four method signatures ship in Phase 01 so Phase 03 rituals route through the adapter contract without channel-specific shims; the two Phase-02 methods MUST NOT be re-implemented to `pass` per `rules/zero-tolerance.md` Rule 2 + Rule 6.

**Phase 01 deviation note** (per `rules/specs-authority.md` Rule 6): the abstract method body for `send_posture_review` + `send_monthly_report` raises `PhaseDeferredError(method_name=..., deferred_to_phase="Phase 02")`. Concrete Phase-01 adapters inherit this default; concrete Phase-02 adapters override.

**Dual M1 dispatch surface** (per `rules/specs-authority.md` Rule 5b sibling re-derivation): the channels ABC also exposes `async def render_grant_moment(request) -> None` matching `envoy.grant_moment.channel_handoff.ChannelAdapterProtocol`. The two surfaces coexist by design:

- `send_grant_moment(target, grant, *, primary_only, timeout_seconds) -> GrantMomentReceipt` — full single-channel ritual (render + await decision + receipt).
- `render_grant_moment(request) -> None` — M1 dispatch primitive used by `ChannelHandoff.dispatch` to fire render across every active channel WITHOUT awaiting a decision; the decision arrives async via `EnvoyGrantMomentRuntime.post_decision` per `specs/grant-moment.md` § State machine M1→M2.

Every Phase-01 surface MUST implement BOTH methods:

```python
async def send_grant_moment(
    self, target_principal_id: str, grant: GrantMomentPayload, *,
    primary_only: bool = False, timeout_seconds: int = 30,
) -> GrantMomentReceipt:
    """
    Render Grant Moment. If `primary_only=True` AND this is not the user's primary channel,
    raise `NotPrimaryChannelError` (per H-03 primary-channel binding for high-stakes grants).
    Timeout: timeout_seconds (default 30s — user has time to read); on timeout marks grant
    as expired and raises `GrantMomentExpiredError`.
    Returns `GrantMomentReceipt {request_id, grant_id, decision, decided_at, channel_signature}`
    — `request_id` extends the original 4-field shape per `rules/specs-authority.md` Rule 6
    so runtime callers correlate without holding a side-table. `decision` is constrained to
    the `GrantMomentDecision` closed vocabulary
    (`approve_once | approve_and_author | deny | modify`) per `specs/grant-moment.md`
    § Resolution shape; out-of-vocabulary decisions raise at the adapter boundary.

    **Defense-in-depth (H-03 primary-channel binding)**: when `grant.high_stakes is True`,
    the adapter MUST refuse on a non-primary channel even when the caller forgot
    `primary_only=True`. Single-layer kwarg gating is insufficient — the payload-level
    discriminator is the structural defense.
    """

async def send_digest(
    self, target_principal_id: str, digest: DailyDigestPayload, *,
    timeout_seconds: int = 10,
) -> SendReceipt:
    """
    Deliver morning digest (specs/daily-digest.md owns payload schema).
    Timeout: timeout_seconds; on timeout raises `SendTimeoutError`.
    Rate-limit: 1 digest per principal per 24h enforced by adapter; redundant calls return cached `SendReceipt`.
    """

async def send_posture_review(
    self, target_principal_id: str, review: WeeklyPostureReviewPayload, *,
    timeout_seconds: int = 15,
) -> PostureReviewReceipt:
    """
    Deliver Sunday 90-second weekly posture review (specs/weekly-posture-review.md owns content + state machine).
    Receipt MUST capture state-machine progression (W0→W6) so partial sessions resume.
    Timeout: timeout_seconds; on timeout the review enters W_PAUSED and resumes on next channel-touch.
    Rate-limit: 1 review per principal per week enforced by adapter; redundant calls return the in-progress receipt.
    Returns `PostureReviewReceipt {review_id, current_state, persisted_decisions, completed_at?}`.
    """

async def send_monthly_report(
    self, target_principal_id: str, report: MonthlyTrustReportPayload, *,
    timeout_seconds: int = 30,
) -> SendReceipt:
    """
    Deliver month-end trust report (specs/monthly-trust-report.md owns content + receipt_hash).
    Payload includes pre-rendered PDF/JSON references (URLs to user-local archive); adapter renders
    summary card + delivers signed receipt_hash.
    Timeout: timeout_seconds; on timeout raises `SendTimeoutError`.
    Rate-limit: 1 report per principal per calendar month enforced by adapter.
    Returns `SendReceipt {message_id, delivered_at, channel_native_id, receipt_hash}`.
    """
```

### Capabilities + observability

```python
@property
def capabilities(self) -> ChannelCapabilities:
    """Static channel capabilities — see §ChannelCapabilities below."""

async def rate_limit_status(self) -> RateLimitStatus:
    """
    Returns `RateLimitStatus {requests_remaining, window_resets_at, soft_quota_warning}`.
    `soft_quota_warning` always False in the current implementation.
    Hard quota raises `RateLimitExceededError` from `send_*` methods.
    """
```

### Gate ordering invariant (INV-4)

`send_message` and `send_grant_moment` MUST check gates in this order:

1. **Lifecycle guard** — `_require_started(...)` raises `NotStartedError` if adapter not running.
2. **Principal validation** — raises `PrincipalNotFoundError` if `target_principal_id` is empty/blank. Precedes rate-limit to prevent quota information leakage to callers supplying invalid principal IDs.
3. **Rate-limit gate** — consults `rate_limit_status()` before every send; raises `RateLimitExceededError` if `requests_remaining == 0` or `soft_quota_warning` is True.

Swapping 2 and 3 is BLOCKED: a caller supplying an invalid principal ID would receive quota information before identity is validated.

### Pending-decision isolation

`send_grant_moment` writes one `asyncio.Future` (or `asyncio.Queue` for queue-based adapters) per `request_id` into `_pending_decisions` at call entry via `_register_pending`. The entry is removed in a `finally` block regardless of outcome (timeout, cancellation, or decision). Each call gets a fresh Future/Queue — concurrent calls for different `request_id` values are fully isolated and do not share state.

## `ChannelCapabilities`

```python
@dataclass(frozen=True)
class ChannelCapabilities:
    supports_buttons: bool          # Inline action buttons (Telegram inline-kbd, Slack blocks)
    supports_attachments: bool      # File / image upload
    supports_markdown: bool         # Rich text rendering
    supports_voice: bool            # Voice-note send/receive
    supports_reactions: bool        # Per-message reactions for non-modal feedback
    max_message_length: int         # Hard payload ceiling in characters
```

Phase 01 capabilities matrix per channel published in `foundation-ops.md` registry #18 (channel-capability registry, `envoy-registry:channel-capabilities:v1`, signed Foundation key).

## Message envelope

```python
@dataclass(frozen=True)
class InboundMessage:
    channel_id: str
    session_id: str                 # cross-channel session continuity key
    principal_genesis_id: str       # signer of the message (verified at adapter boundary)
    direction: Literal["inbound", "outbound"]
    content_trust_level: Literal["user", "system", "tool", "agent"]
    payload: MessagePayload
    visible_secret_rendered: VisibleSecret | None
    timestamp: datetime             # adapter-assigned UTC; clock-skew tolerance via specs/remote-time-anchor.md
```

## Phase 01 surfaces (8)

| Channel                | Credentials                                                               | Compliance                                | Phase 01 ship                                                                        |
| ---------------------- | ------------------------------------------------------------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------ |
| CLI                    | none                                                                      | N/A                                       | Yes                                                                                  |
| Web                    | localhost bind                                                            | N/A                                       | Yes                                                                                  |
| Telegram               | webhook `secret_token` + injected `send_fn` (`send_fn=None` is test-only) | Clean (official bot API)                  | Yes                                                                                  |
| Slack                  | bot token + OAuth + signing_secret                                        | Clean (App Directory)                     | Yes                                                                                  |
| Discord                | bot token + Ed25519 application_public_key + webhook_url (SSRF-guarded)   | Clean (Dev Terms)                         | Yes (adapter + signature + ritual; outbound delivery raises `ChannelTransportError`) |
| WhatsApp               | WhatsApp Business API                                                     | Paid tier; Foundation gateway OR user-own | Yes (caveat)                                                                         |
| Signal                 | signal-cli OR Group Link                                                  | Phase 01 legal gate (Path B default)      | Yes (Path B)                                                                         |
| iMessage (BlueBubbles) | user-owned Mac                                                            | Apple ToS grey; user responsibility       | Yes (caveat)                                                                         |

## Phase 04 surfaces (17+)

Matrix, Feishu, LINE, Mattermost, WeChat, QQ, Teams, Google Chat, IRC, Nostr, Twitch, Tlon, Zalo, Nextcloud Talk, Synology Chat, Apple Shortcuts, Calendar, browser extension, IDE extensions, voice (Whisper), RCS/SMS (Twilio).

## Cross-channel session continuity

Single session across all active channels for a principal. Visible secret rendered in every channel. Grant Moment approval on any channel resolves session globally; other channels see "resolved elsewhere."

## Primary-channel binding (H-03 doc 01 fix)

High-stakes Grant Moments (above Financial/Communication threshold) render + approvable ONLY on user's designated primary channel. Adapter enforces via `primary_only=True` kwarg on `send_grant_moment` raising `NotPrimaryChannelError` from non-primary adapters.

## Side-channel hygiene (T-070)

- Clipboard auto-clear after 30s.
- Screen recording detection (Flutter mobile Phase 02).
- Accessibility API hardening per platform.
- E2E encryption per-channel (WhatsApp/Signal/iMessage = yes; Telegram secret-chats-only; Slack/Discord admin-visible).

## Network security (T-080)

TLS 1.3 minimum. Certificate pinning for Foundation endpoints. Standard OS trust store for third-party channels.

Discord `webhook_url` is SSRF-guarded at `startup()` via `_validate_webhook_url_ssrf` (`envoy/channels/discord.py`): rejects loopback (`127.0.0.0/8`, `::1/128`), private (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `fc00::/7` IPv6 ULA), link-local, RFC 1122 "this-network" (`0.0.0.0/8`), IMDS (`169.254.169.254`), IPv6-mapped IPv4 (`::ffff:0.0.0.0/96`), and numeric-encoded literal IPs in decimal (`2130706433`), hex-integer (`0x7f000001`), dotted-hex (`0x7f.0.0.1`), and octal-dotted (`0177.0.0.1`) forms. Hostname-level blocklist additionally rejects `localhost`, `metadata.google.internal`, `metadata.internal`, `169.254.169.254`, `fd00::ec2:254`, `::1`, `0.0.0.0`, `[::]`. Failure raises `ChannelTransportError`.

## Error taxonomy

| Error                                         | Trigger                                                             | User action                                                               | Retry                                      |
| --------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------ |
| `StartupTimeoutError`                         | Adapter `startup` exceeds 10s (network, auth, webhook registration) | Check channel credentials + connectivity; restart adapter                 | Auto with exponential backoff (5 attempts) |
| `AlreadyStartedError`                         | `startup` called on running adapter                                 | None — programming error                                                  | Never                                      |
| `ChannelTransportError`                       | WebSocket / HTTP transport failure during receive_message           | Wait for runtime reconnect                                                | Auto (runtime backoff)                     |
| `OverflowDropEvent` (Ledger only, not raised) | Inbound queue exceeds 100                                           | Investigate sender pattern; consider higher posture                       | N/A                                        |
| `SendTimeoutError`                            | `send_*` exceeds method timeout                                     | User retries action; runtime surfaces channel-degraded warning            | Manual after diagnosis                     |
| `RateLimitExceededError`                      | Quota exhausted (channel-imposed or adapter soft-cap)               | Wait `retry_after_seconds`; high-stakes payloads route to primary channel | Auto after window reset                    |
| `NotPrimaryChannelError`                      | High-stakes Grant Moment routed to non-primary channel              | Approve on primary channel (named in error)                               | Never (structural defense)                 |
| `GrantMomentExpiredError`                     | User did not respond within timeout_seconds (default 30s)           | Re-issue Grant Moment via runtime; cooldown applies if repeated           | Manual                                     |
| `PrincipalNotFoundError`                      | `target_principal_id` not registered with adapter                   | Verify Connection Vault entry; re-pair channel                            | Never                                      |
| `AuthenticationError`                         | Bot token / OAuth token expired or revoked                          | Re-authenticate via channel-specific flow                                 | Never                                      |
| `PayloadTooLargeError`                        | Payload exceeds `capabilities.max_message_length`                   | Caller must split or summarize                                            | Never                                      |

All errors persisted to Ledger with `content_trust_level: system` and `format_record_id_for_event(target_principal_id)` redaction per specs/classification-policy.md.

### Adapter-internal hygiene errors (NOT in the spec taxonomy table above)

The implementation also ships 4 adapter-internal typed errors that are NOT part of the spec § Error taxonomy contract — they surface programming / config / hygiene failures rather than channel-traffic failures, and they all subclass `ChannelAdapterError` so callers catching the family catch them uniformly:

| Error                          | Trigger                                                                                                              | User action                                       | Retry              |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- | ------------------ |
| `NotStartedError`              | `send_*` / `render_grant_moment` called before `startup`                                                             | Caller programming error — call `startup` first   | Never              |
| `PendingDecisionsCeilingError` | In-flight pending-decision map at ceiling (DoS defense, all Wave-A adapters: Web, Discord, Slack, Telegram)          | Wait for existing grants to resolve, then retry   | Auto after drain   |
| `InvalidDecisionError`         | `_resolve_pending_decision` received a decision string NOT in `GrantMomentDecision` Literal vocabulary               | WS-handler programming / injection — check source | Never              |
| `PhaseDeferredError`           | Phase-02 ritual surface called (`send_posture_review` / `send_monthly_report`) OR Web `send_message` (Phase-01 hold) | Phase 02 / Wave-4 sibling-shard wiring required   | Never (structural) |

## Cross-references

- specs/grant-moment.md — adapter.send_grant_moment.
- specs/daily-digest.md — adapter.send_digest.
- specs/weekly-posture-review.md — adapter.send_posture_review.
- specs/monthly-trust-report.md — adapter.send_monthly_report.
- specs/network-security.md — TLS + cert pinning.
- specs/ui-platform.md — per-platform accessibility + clipboard.
- specs/threat-model.md — T-018, T-070, T-080.
- specs/classification-policy.md — `format_record_id_for_event` redaction at audit-row write.
- specs/foundation-ops.md — channel-capability registry #18.

## Test location

**Shipped today** (Phase 01 channels foundation, PR #42):

- `tests/integration/channels/test_<channel>_adapter_lifecycle.py` — startup/shutdown idempotency, drain timeout (Tier 2, real channel sandbox where available). File-pattern template: `<channel>` ∈ {cli, web, telegram, slack, discord, whatsapp, signal, imessage}. Phase 01 foundation ships `cli` + `web`; Wave-A/B siblings populate the remaining channels.
- `tests/integration/channels/test_adapter_abc_contract.py` — ABC method-signature parity with spec § Adapter contract; Phase-02 ritual surfaces inherit `PhaseDeferredError`.
- `tests/integration/channels/test_redteam_r{1,2,3,4}_closures.py` — /redteam round closure pins for the foundation shard.
- `tests/integration/test_h03_primary_channel_binding.py` — high-stakes Grant Moment routing (`NotPrimaryChannelError`).

## Open questions

1. WhatsApp Foundation gateway vs user-own pricing/SLA model — Phase 01 launch-blocker decision pending.
2. Signal Path B (Group Link only) UX impact vs Path A (signal-cli) — adoption metric to track post-Phase-01.
3. Cross-channel session continuity merge semantics when concurrent decisions arrive on two channels within the timeout window — last-writer-wins vs reject-second.
4. Phase 04 17-channel matrix — which subset to ship first based on user demand telemetry (foundation-health-heartbeat aggregate).
5. Voice-channel transcription provenance — recorded audio vs transcribed-only; storage retention per classification-policy.
