# 16 — Channel Adapters Implementation (CLI + Web + 6 messaging)

**Document role:** Phase 01 implementation deep-dive for the 8-channel adapter primitive (shard 16 of /analyze; Group D per `01-shard-plan.md` § 5; depends on shards 4, 5, 6, 8, 10, 14). Establishes the verified upstream provider surface (3 of 9 channels present in `kailash-py`; Nexus webhook + websocket primitives), the Envoy-new-code surface (6 messaging adapters + unified `ChannelAdapter` Protocol + `InboundRouter` to Boundary Conversation + Grant Moment renderer per channel + cross-channel coherence delegated to Trust store + Ledger), the class structure, the integration points, the Tier 2 / Tier 3 test surface, the EC-7 + EC-8 acceptance gates, and the de-scope #1 disposition recommendation.

**Date:** 2026-05-03 (shard 16 of /analyze).
**Status:** DRAFT — load-bearing for shards 11 (Daily Digest outbound rendering) and 19 (pipx distribution dependency tree).
**Owning shard:** 16 (per `01-shard-plan.md` § 2).
**Exit criteria served:** EC-7 (Single user onboards via any of 8 channels — `02-mvp-objectives.md` lines 94–104), EC-8 (User operates for a week across channels — lines 107–116).
**Discipline:** Cite, do not paraphrase frozen specs. Per `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`, the shard's question is "given this spec is frozen, how do I wire `kailash-py` + Nexus to deliver it?" Per `rules/specs-authority.md` Rule 4 + Rule 5b (no spec edits at this shard).

**Capacity check:** 1 primitive-family (8 adapters), 2 source specs (`channel-adapters.md` + `a2a-messaging.md`), ~7 invariants tracked (unified `ChannelAdapter` ABC; `InboundMessage` envelope identity; Trust-store-delegated cross-channel coherence; Ledger-emit on every adapter lifecycle event; Connection Vault credential flow; Grant Moment dispatch contract; primary-channel binding H-03), ≤6 cross-primitive references (Connection Vault, Boundary Conversation, Grant Moment, Ledger, Trust store, Daily Digest). Within `rules/autonomous-execution.md` budget because the 6 social-channel adapters share one ABC and differ only in transport-layer glue (~150 LOC each pattern-matched on the same shape, NOT 6 independent invariants).

---

## 1. Source spec citation

Frozen specs the channel adapters implement against (cited; not edited):

- `specs/channel-adapters.md` § Adapter contract (lines 14–130) — abstract `ChannelAdapter` ABC: lifecycle (`startup` 10s timeout `StartupTimeoutError`, `shutdown` drain timeout default 5s), receive (`receive_message` AsyncIterator, bounded queue 100 with `OverflowDropEvent`), send (`send_message` 10s default timeout, retry-with-jitter, `SendReceipt`), 4 ritual-delivery methods (`send_grant_moment` 30s + primary_only, `send_digest` 10s + 1/24h cache, `send_posture_review` 15s + W0→W6 state-machine receipt + 1/week, `send_monthly_report` 30s + receipt_hash + 1/calendar-month), capabilities + observability (`capabilities`, `rate_limit_status`).
- `specs/channel-adapters.md` § `ChannelCapabilities` (lines 132–143) — 6-field static struct (supports_buttons, supports_attachments, supports_markdown, supports_voice, supports_reactions, max_message_length).
- `specs/channel-adapters.md` § Message envelope (lines 148–159) — `InboundMessage` 8 fields: `channel_id`, `session_id` (cross-channel session-continuity key), `principal_genesis_id` (verified at adapter boundary), `direction`, `content_trust_level`, `payload`, `visible_secret_rendered`, `timestamp` (adapter-assigned UTC).
- `specs/channel-adapters.md` § Phase 01 surfaces (lines 163–173) — 8-row table: CLI (no creds), Web (localhost bind), Telegram (bot token), Slack (bot token + OAuth), Discord (bot token), WhatsApp (paid tier; Foundation gateway OR user-own — caveat), Signal (signal-cli OR Group Link — Path B legal-gate default), iMessage/BlueBubbles (user-owned Mac — caveat).
- `specs/channel-adapters.md` § Cross-channel session continuity (lines 179–181) — single session across all active channels for a principal; visible secret rendered every channel; Grant Moment approval on any channel resolves session globally; other channels see "resolved elsewhere."
- `specs/channel-adapters.md` § Primary-channel binding (H-03 doc 01 fix; lines 183–185) — high-stakes Grant Moments approvable ONLY on user's designated primary channel; adapter enforces `primary_only=True` raising `NotPrimaryChannelError` from non-primary adapters.
- `specs/channel-adapters.md` § Side-channel hygiene (T-070; lines 188–192) — clipboard auto-clear 30s; screen-recording detection (Phase 02 mobile); accessibility-API hardening; per-channel E2E status (WhatsApp/Signal/iMessage = E2E yes; Telegram secret-chats-only; Slack/Discord admin-visible).
- `specs/channel-adapters.md` § Network security (T-080; lines 195–196) — TLS 1.3 minimum; certificate pinning for Foundation endpoints; standard OS trust store for third-party channels.
- `specs/channel-adapters.md` § Error taxonomy (lines 199–214) — 11 typed errors (`StartupTimeoutError`, `AlreadyStartedError`, `ChannelTransportError`, `OverflowDropEvent` Ledger-only, `SendTimeoutError`, `RateLimitExceededError`, `NotPrimaryChannelError`, `GrantMomentExpiredError`, `PrincipalNotFoundError`, `AuthenticationError`, `PayloadTooLargeError`); ALL persisted to Ledger with `content_trust_level: system` and `format_record_id_for_event(target_principal_id)` redaction per `specs/classification-policy.md`.
- `specs/channel-adapters.md` § Cross-references (lines 218–226) — explicit forward to grant-moment.md, daily-digest.md, weekly-posture-review.md (Phase 02), monthly-trust-report.md (Phase 02), network-security.md, ui-platform.md, threat-model.md, classification-policy.md, foundation-ops.md (registry #18).
- `specs/channel-adapters.md` § Test location (lines 229–238) — 9 test files including `tests/integration/channels/test_<channel>_adapter_lifecycle.py`, `..._send_message.py`, `..._ritual_delivery.py`, `tests/regression/test_t018_visible_secret_per_channel.py`, `..._t070_clipboard_autoclear.py`, `..._t080_tls13_pin.py`, `..._t023_signal_path_b.py`, `tests/integration/test_h03_primary_channel_binding.py`, `tests/e2e/test_session_continuity_8_channels.py`.
- `specs/channel-adapters.md` § Open questions (lines 241–246) — five open questions; Phase 01 disposition in § 7 below.

Cross-spec citations (read-only at this shard):

- `specs/a2a-messaging.md` line 13 — **"Phase 03 deliverable"** — A2A messaging is a Phase 03 primitive. Phase 01 channel adapters MUST NOT implement the cross-principal A2A flow; the `principal_genesis_id` field on `InboundMessage` is verified at the adapter boundary but only the single-principal channel-traffic case operates in Phase 01 per `00-inheritance-from-phase-00.md` § 6 invariant #1.
- `specs/connection-vault.md` § "Per-entry schema" — channel adapter credentials live in the Connection Vault per shard 14 § 5.1; adapters resolve `entry_id` → secret at startup; per `02-mvp-objectives.md` § 3 row 5 ("Channel adapters need API keys to function; without Connection Vault, channel adapters store secrets ad-hoc").
- `specs/grant-moment.md` § State machine + § Rendering — channel adapters host the Grant Moment dialog UI per shard 10 § 3.2 item 5 (`ChannelHandoff.dispatch(request, channel, timeout)` calls `channel.render_grant_moment(request)` returning `result_future`); the Grant Moment's `request_grant_moment(violation, channel) → resolution` contract is satisfied by `send_grant_moment` per `specs/channel-adapters.md` § Ritual delivery line 69.
- `specs/ledger.md` § Entry types (lines 47–91) — channel adapters write `channel_connected` and `channel_disconnected` entries on lifecycle events per shard 6 § 5.1 row "Channel adapters"; ALL `Error taxonomy` entries from § 1 above persist as `system_error` Ledger entries.
- `specs/boundary-conversation.md` (cross-spec via shard 8) — inbound user messages route from each adapter's `receive_message()` AsyncIterator into the active Boundary Conversation per shard 8; the channel adapter is the I/O substrate, not the conversation host.

---

## 2. Verified provider citation — kailash-py + Nexus

Per `03-kailash-py-mvp-readiness.md` § 5 verification protocol: the Channel adapters primitive is **B grade** at the 2026-04-21 baseline (3 of 9 channels present — `02-kailash-py-survey.md` item 24 lines 743–778: APIChannel, CLIChannel, MCPChannel). Five Nexus-side closures since 2026-04-21 materially improved the production surface for the messaging adapters.

### 2.1 What `kailash-py` provides today

| Surface needed by Channel adapters                                                                            | `kailash-py` / Nexus provider                                                                          | Verified citation                                                                                                                                                                                                                                                |
| ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| HTTP API channel (Web Phase 01 surface)                                                                       | `kailash.channels.api_channel.APIChannel`                                                              | `~/repos/loom/kailash-py/src/kailash/channels/api_channel.py` (verified present); `02-kailash-py-survey.md` § item 24 line 743                                                                                                                                   |
| CLI channel (CLI Phase 01 surface)                                                                            | `kailash.channels.cli_channel.CLIChannel`                                                              | `~/repos/loom/kailash-py/src/kailash/channels/cli_channel.py` (verified present); `02-kailash-py-survey.md` § item 24 line 743                                                                                                                                   |
| MCP channel (out-of-scope Phase 01)                                                                           | `kailash.channels.mcp_channel.MCPChannel`                                                              | `~/repos/loom/kailash-py/src/kailash/channels/mcp_channel.py` (verified present); MCP is a Phase 02 channel surface per `00-inheritance-from-phase-00.md` (MCP server NOT in Phase 01 scope)                                                                     |
| Channel base class                                                                                            | `kailash.channels.base.Channel`                                                                        | `~/repos/loom/kailash-py/src/kailash/channels/base.py`                                                                                                                                                                                                           |
| Event router across channels                                                                                  | `kailash.channels.event_router`                                                                        | `~/repos/loom/kailash-py/src/kailash/channels/event_router.py`                                                                                                                                                                                                   |
| Cross-channel session                                                                                         | `kailash.channels.session`                                                                             | `~/repos/loom/kailash-py/src/kailash/channels/session.py`                                                                                                                                                                                                        |
| Webhook transport (load-bearing for Telegram, Slack, Discord, WhatsApp, signal-cli REST hooks)                | `nexus.transports.webhook.WebhookTransport` + `WebhookSigner` Protocol + `TwilioSigner` reference impl | `~/repos/loom/kailash-py/packages/kailash-nexus/src/nexus/transports/webhook.py` lines 32 (`TwilioSigner` export), 40 (`class WebhookSigner(Protocol)`), 125 (`class TwilioSigner`), 301 (`class WebhookTransport(Transport)`), 335/459/533 (signer plug points) |
| WebSocket transport (load-bearing for Web channel + real-time messaging adapters that prefer WS over webhook) | `nexus.transports.websocket` + `Nexus.register_websocket(path, handler_cls, *, allowed_origins=...)`   | `~/repos/loom/kailash-py/packages/kailash-nexus/src/nexus/core.py` line 705 (`def register_websocket`), line 710 (`allowed_origins: Optional[List[str]] = None`), line 765 (`ValueError: if allowed_origins fails validation`)                                   |
| HTTP/CORS hardening for Web channel                                                                           | `Nexus._validate_cors_origins` + `_get_cors_defaults`                                                  | `~/repos/loom/kailash-py/packages/kailash-nexus/src/nexus/core.py` lines 2365–2425 (refuses `allow_origins=['*']` in production); `2440–2448` (warns on `allow_credentials=True` with `*`)                                                                       |

### 2.2 Indirect-closure PR refs improving Channel adapter surface (since 2026-04-21)

Per `03-kailash-py-mvp-readiness.md` § 2.2 four upstream closures directly affect Channel adapters; cited:

1. **#687 — nexus `WebhookTransport` pluggable signer for Twilio.** Effect: the `WebhookSigner` Protocol (line 40 of `webhook.py`) is now a stable plug point — every per-vendor signature scheme (Telegram's `X-Telegram-Bot-Api-Secret-Token`, Slack's `X-Slack-Signature` HMAC, Discord's `X-Signature-Ed25519`, WhatsApp's `X-Hub-Signature-256`, Twilio SMS) implements `WebhookSigner` and is dispatched by the same `WebhookTransport`. The `TwilioSigner` (line 125) is the reference implementation Phase 01 follows for the per-channel signer. Without this closure, every messaging adapter would have to re-implement the webhook receive path.
2. **#767 — nexus `durability_middleware` drains StreamingResponse body.** Effect: the Web channel's SSE / streaming path (used for Daily Digest live-update preview, Grant Moment streaming render, real-time inbound message events in the Web UI) no longer leaves connections half-drained on durability-middleware short-circuit. Without this, a Web-channel Grant Moment that fires mid-streaming would leak a half-rendered modal and the SSE connection would hang.
3. **#737 — Nexus WorkflowServer lifespan disables consumer @on_event.** Effect: the channel adapter lifecycle (`startup` / `shutdown` per `specs/channel-adapters.md` § Lifecycle methods) hooks into Nexus's lifespan mechanism via `@on_event` decorators; this closure ensures consumer-registered events fire during the adapter's startup/shutdown windows. Without it, an adapter's `startup` would complete but the per-adapter `channel_connected` Ledger emit hooked off the lifespan event would silently not fire.
4. **#673 — nexus `Origin`/`Host` allowlist on register_websocket.** Effect: `register_websocket(path, handler_cls, *, allowed_origins=[...])` (verified at `core.py:705`) enforces an explicit allowlist for the WebSocket upgrade. The Web channel's WebSocket binds to localhost (Phase 01 per `specs/channel-adapters.md` line 167 "localhost bind") AND validates Origin against `["http://localhost:*", "http://127.0.0.1:*"]`. Without this closure, a malicious page in the user's browser could initiate a DNS-rebind WebSocket upgrade to the local Envoy port and impersonate the Web channel — exactly the threat that `rules/security.md` § "Network Transport Hardening" enumerates.

### 2.3 What `kailash-py` does NOT provide — Envoy-new-code surface preview

`kailash-py` does NOT provide:

1. **6 social-messaging adapters** — Telegram, Slack, Discord, WhatsApp, iMessage (BlueBubbles bridge), Signal (signal-cli or Group Link). The Phase 00 survey at `02-kailash-py-survey.md` item 24 explicitly enumerates "B (3 of 9 present)" — only API + CLI + MCP exist upstream. Per `03-primitive-reconciliation.md` § 2 row 23 (cited via `01-shard-plan.md` § 2 row 16), the 6 messaging channels are Envoy-new-code by design.
2. **Unified `ChannelAdapter` Protocol matching `specs/channel-adapters.md` § Adapter contract** — `kailash.channels.base.Channel` exists upstream as a base class but does NOT enforce the 4 ritual-delivery methods (`send_grant_moment`, `send_digest`, `send_posture_review`, `send_monthly_report`) that `specs/channel-adapters.md` § Ritual delivery requires. Envoy ships its own `ChannelAdapter` ABC layered on top of upstream `Channel`.
3. **`InboundMessage` envelope per `specs/channel-adapters.md` § Message envelope** — the 8-field schema with `principal_genesis_id` verified at adapter boundary. Upstream `Channel` has no equivalent; Envoy ships the envelope dataclass.
4. **Cross-channel session-continuity store** — single session across channels (per `specs/channel-adapters.md` § Cross-channel session continuity). Upstream `kailash.channels.session` exists but is NOT a cross-channel session-equivalence store; it is per-channel session. The cross-channel coherence contract (Grant Moment approved on Telegram honored on Slack 3 days later) is satisfied via Trust store + Ledger as the state surface, NOT via a parallel Channel-adapter-side store. **This is the answer to key design question #5: cross-channel coherence is a STATE-STORE concern delegated to shard 5 + shard 6, NOT an adapter concern.**
5. **`InboundRouter` from adapter inbound queue → Boundary Conversation** — channel adapters are the I/O substrate; routing inbound user messages into the active Boundary Conversation per shard 8 is Envoy-new orchestration glue.
6. **Per-channel Grant Moment renderer** — each adapter MUST implement `render_grant_moment(request) → result_future` per shard 10 § 3.2 item 5; the renderer translates the wire-format `GrantMomentRequest` into channel-native UI (Telegram inline keyboard, Slack Block Kit, Discord component buttons, WhatsApp template message with quick-reply, iMessage rich link unfurl, Signal text-with-action-keywords, CLI prompt, Web modal) and yields the user's response back as a wire-format `GrantMomentResult`.
7. **Per-channel rate-limit translation** — each channel has its own quota (Telegram 30 msg/sec/bot, Slack rate-limit-tier headers, Discord 5/sec/channel, WhatsApp 24h customer-care window, Signal no documented quota, iMessage best-effort). Each adapter implements `rate_limit_status() → RateLimitStatus` translating the channel-native quota signal into the unified `RateLimitStatus` shape.

These seven items are the Envoy-new-code surface; § 3 below itemises them.

---

## 3. Envoy-new-code surface

### 3.1 Module shape: `envoy.channels` package layered on `kailash.channels` + `nexus.transports`

The Phase 01 Envoy-new-code surface is a Python package `envoy.channels` exposing the `ChannelAdapter` Protocol (the unified ABC every adapter implements) plus 8 concrete adapter classes. The package composes:

- `kailash.channels.base.Channel` — base class extended; per `rules/orphan-detection.md` Rule 1 + Rule 3, Envoy `ChannelAdapter` does NOT replace upstream `Channel`, it layers ABCs on top.
- `kailash.channels.api_channel.APIChannel` — wrapped by `WebChannelAdapter` for the Phase 01 Web channel (localhost-bound HTTP API).
- `kailash.channels.cli_channel.CLIChannel` — wrapped by `CLIChannelAdapter` for the Phase 01 CLI channel.
- `nexus.transports.webhook.WebhookTransport` + `WebhookSigner` Protocol (verified provider, § 2.1) — Telegram / Slack / Discord / WhatsApp / signal-cli REST webhooks all wrap `WebhookTransport` with a per-channel `WebhookSigner` impl.
- `nexus.transports.websocket` + `Nexus.register_websocket(..., allowed_origins=[...])` (verified, § 2.2 #673) — Web channel's real-time inbound feed.
- `envoy.connection_vault.ConnectionVault.get(entry_id) → secret` (shard 14 § 4) — every adapter's `startup(config)` resolves bot token / API key from the Vault.
- `envoy.ledger.EnvoyLedger.append(entry_type, content, ...)` (shard 6 § 4) — every adapter writes `channel_connected` / `channel_disconnected` lifecycle Ledger rows AND every error in `specs/channel-adapters.md` § Error taxonomy persists as `system_error`.
- `envoy.grant_moment.GrantMomentOrchestrator` (shard 10 § 4) — the orchestrator dispatches to each adapter's `render_grant_moment(request)`.
- `envoy.trust.TrustStoreAdapter` (shard 5) — the cross-channel coherence state surface; adapters READ session-equivalence from the Trust store, never maintain a parallel store.

Composition philosophy: per `rules/orphan-detection.md` Rule 1 + `rules/facade-manager-detection.md` Rule 1 + Rule 3, every adapter is a _consumer_ of upstream/sibling primitives; explicit constructor dependencies (no global lookup, no self-construction). Per `rules/orphan-detection.md` Rule 1, each of the 8 adapter classes has at least one production call site within 5 commits — the call site is `envoy.runtime.session.SessionRouter` which iterates registered adapters at session start and routes Grant Moments / Digests through them.

### 3.2 Surface to be built (Envoy-new-code)

1. **`envoy.channels.adapter.ChannelAdapter`** — abstract base class (Python `abc.ABC`) implementing `specs/channel-adapters.md` § Adapter contract verbatim. Inherits from `kailash.channels.base.Channel`. Defines abstract methods: `channel_id` (property), `startup(config)`, `shutdown(drain_timeout_seconds=5)`, `receive_message() → AsyncIterator[InboundMessage]`, `send_message(target_principal_id, payload, *, visible_secret=None, timeout_seconds=10) → SendReceipt`, `send_grant_moment(target_principal_id, grant, *, primary_only=False, timeout_seconds=30) → GrantMomentReceipt`, `send_digest(target_principal_id, digest, *, timeout_seconds=10) → SendReceipt`, `send_posture_review(...)` (Phase 02 stub raising `NotImplementedError` until shard 11+), `send_monthly_report(...)` (Phase 02 stub), `capabilities → ChannelCapabilities`, `rate_limit_status() → RateLimitStatus`. The Phase 02 stubs are NOT `pass`-bodied per `rules/zero-tolerance.md` Rule 2 — they raise a typed `PhaseDeferredError` with a clear message naming the deferring phase, per the test-skip triage convention adapted to runtime.

2. **`envoy.channels.envelope` — `InboundMessage`, `MessagePayload`, `VisibleSecret`, `SendReceipt`, `GrantMomentReceipt`, `RateLimitStatus`, `ChannelCapabilities`** — frozen dataclasses matching `specs/channel-adapters.md` § Message envelope + § ChannelCapabilities verbatim. The `InboundMessage.principal_genesis_id` field is verified at the adapter boundary (the adapter SHALL refuse messages whose claimed sender does not match the bound bot's known principal mapping; mismatch raises `PrincipalNotFoundError`).

3. **`envoy.channels.errors` — 11 typed errors** per `specs/channel-adapters.md` § Error taxonomy. Each subclasses a base `ChannelAdapterError`. Each error's emission path writes a `system_error` Ledger entry via `EnvoyLedger.append("system_error", {fault_class, channel_id, principal_genesis_id_redacted})` per `rules/event-payload-classification.md` Rule 1 (single-point filter at the emitter; `format_record_id_for_event` applied to `target_principal_id`).

4. **`envoy.channels.cli.CLIChannelAdapter`** — wraps `kailash.channels.cli_channel.CLIChannel`. Phase 01 surface for the developer / power-user / first-time-installer onboarding path. No credentials (per `specs/channel-adapters.md` line 165). Render Grant Moment as a Click/argparse-style prompt with 4 options (Approve once / Approve+author / Deny / Modify) per `specs/grant-moment.md` § Rendering (lines 78–86). Reads stdin via `prompt_toolkit` (existing dependency) for the secure-input path. Capabilities: `supports_buttons=False, supports_attachments=False, supports_markdown=True (terminal-rendered), supports_voice=False, supports_reactions=False, max_message_length=4096`.

5. **`envoy.channels.web.WebChannelAdapter`** — wraps `kailash.channels.api_channel.APIChannel` + `nexus.register_websocket`. Phase 01 localhost bind only (per `specs/channel-adapters.md` line 167; cross-references `rules/security.md` § "Network Transport Hardening" — local-only HTTP servers MUST validate Origin/Host against an allowlist before dispatching). The WebSocket upgrade goes through `Nexus.register_websocket(path="/envoy/ws", handler_cls=WebChannelHandler, allowed_origins=["http://localhost:*", "http://127.0.0.1:*"])` (per § 2.2 #673). Render Grant Moment as a modal in the Web UI; SSE for inbound message stream uses the post-#767 StreamingResponse drain. Capabilities: `supports_buttons=True, supports_attachments=True, supports_markdown=True, supports_voice=False (Phase 02), supports_reactions=False, max_message_length=65536`.

6. **`envoy.channels.telegram.TelegramChannelAdapter`** — wraps `nexus.transports.webhook.WebhookTransport` with a `TelegramWebhookSigner` (impl of `WebhookSigner` Protocol per § 2.2 #687) verifying the `X-Telegram-Bot-Api-Secret-Token` header against the bot's stored secret. Bot token resolved at `startup` from Connection Vault entry of type `BOT_TOKEN`. Capabilities: `supports_buttons=True (inline keyboard), supports_attachments=True, supports_markdown=True (Telegram MarkdownV2), supports_voice=True (voice notes), supports_reactions=True (Telegram 8.0+), max_message_length=4096`. Render Grant Moment as inline keyboard with 4 buttons.

7. **`envoy.channels.slack.SlackChannelAdapter`** — wraps `WebhookTransport` with a `SlackWebhookSigner` verifying `X-Slack-Signature` (HMAC-SHA256 of `v0:{timestamp}:{body}` against `signing_secret`). Bot token (`xoxb-...`) AND signing secret resolved at `startup` from two Connection Vault entries. Slack OAuth flow is Phase 02 (per `02-mvp-objectives.md` § 3 row 5 and `connection-vault.md` § Open question 4 cross-device migration UX); Phase 01 uses pre-installed bot token only. Capabilities: `supports_buttons=True (Block Kit), supports_attachments=True, supports_markdown=True (Slack mrkdwn), supports_voice=False, supports_reactions=True, max_message_length=40000`. Render Grant Moment as Slack Block Kit modal/message with action buttons.

8. **`envoy.channels.discord.DiscordChannelAdapter`** — wraps `WebhookTransport` with a `DiscordWebhookSigner` verifying `X-Signature-Ed25519` over the request body (Discord uses Ed25519, not HMAC). Bot token + Discord public-key resolved at `startup` from Connection Vault. Capabilities: `supports_buttons=True (Components), supports_attachments=True, supports_markdown=True (Discord markdown), supports_voice=False (voice channels not in scope Phase 01), supports_reactions=True, max_message_length=2000`. Render Grant Moment as Discord Components row with 4 buttons.

9. **`envoy.channels.whatsapp.WhatsAppChannelAdapter` (caveat: paid-tier — `specs/channel-adapters.md` line 171 "Foundation gateway OR user-own")** — wraps `WebhookTransport` with `WhatsAppWebhookSigner` verifying `X-Hub-Signature-256` (HMAC-SHA256 with App Secret). Phase 01 disposition per `specs/channel-adapters.md` § Open question 1 (line 242, "WhatsApp Foundation gateway vs user-own pricing/SLA model — Phase 01 launch-blocker decision pending"): Phase 01 ships the adapter with user-own credentials path ONLY (the user provides their own WhatsApp Business API credentials); the Foundation gateway path is Phase 02. WhatsApp Cloud API endpoint is `graph.facebook.com/v17.0/{phone_number_id}/messages`. Capabilities: `supports_buttons=True (interactive messages with quick-reply), supports_attachments=True, supports_markdown=False (WhatsApp uses limited formatting only), supports_voice=True, supports_reactions=True (WhatsApp Cloud API 2024+), max_message_length=4096`. Render Grant Moment as interactive message with `button` reply type.

10. **`envoy.channels.imessage.IMessageChannelAdapter` (caveat: BlueBubbles bridge — `specs/channel-adapters.md` line 173 "user-owned Mac; Apple ToS grey; user responsibility")** — wraps `WebhookTransport` pointing at the user's local BlueBubbles server (typically `http://<user-mac>.local:1234`). Authentication via BlueBubbles password. Phase 01 ships with the BlueBubbles server URL + password resolved from Connection Vault. **This is the structurally hardest of the 8 adapters per key design question #4.** Apple does NOT provide a public iMessage API outside Continuity / Messages.app on macOS. The Phase 01 minimum is: "if the user has a BlueBubbles server running on their own Mac, Envoy can route iMessage traffic through it"; Phase 02 may explore native macOS Continuity bridging via AppleScript or `osascript`-driven Messages.app automation. The user explicitly accepts the Apple-ToS grey-area risk per `specs/channel-adapters.md` line 173. Capabilities: `supports_buttons=False (iMessage Tapback only), supports_attachments=True, supports_markdown=False, supports_voice=False (Phase 02 voice memos), supports_reactions=True (Tapback), max_message_length=20000 (BlueBubbles practical cap)`. Render Grant Moment as text-with-numbered-options (1=Approve 2=Approve+author 3=Deny 4=Modify) since iMessage has no inline-button surface.

11. **`envoy.channels.signal.SignalChannelAdapter` (caveat: Path B legal-gate default — `specs/channel-adapters.md` line 172)** — Phase 01 ships Path B (Group Link) ONLY per the `specs/channel-adapters.md` line 172 "Phase 01 legal gate (Path B default)" disposition. Path A (`signal-cli` with linked phone number) is the Phase 01-blocker per T-023 cross-reference; the legal-gate concerns are documented in `specs/threat-model.md` § T-023 (out of scope this shard). Path B uses Signal Group Links: the user joins a Group with the Envoy bot via a pre-shared Group Link; Envoy reads/writes via `signal-cli --group-link` REST API on the user's local machine. **This is the second structurally hard adapter per key design question #4.** Phase 01 minimum: text-only group-link routing; advanced Signal features (disappearing messages, sealed sender, payment messages) are Phase 02+. Capabilities: `supports_buttons=False (Signal has no inline button), supports_attachments=True, supports_markdown=False, supports_voice=True (voice notes), supports_reactions=True (Signal 6.0+ reactions), max_message_length=2048`. Render Grant Moment as text-with-numbered-options identical to iMessage.

12. **`envoy.channels.router.InboundRouter`** (per key design question #6) — singleton orchestrator constructed at runtime startup. Subscribes to every registered adapter's `receive_message()` AsyncIterator concurrently via `asyncio.gather(*[adapter.receive_message() for adapter in registered])`. For each `InboundMessage`:
    1. Verify `principal_genesis_id` against Trust store (rejects spoofing; raises `PrincipalNotFoundError` and writes a `system_error` Ledger row).
    2. Resolve the cross-channel `session_id` via Trust store (per § 3.3 below; Trust-store-delegated coherence).
    3. Route to the active Boundary Conversation OR Daily-Digest-reply OR Grant-Moment-resolution path based on the active session's state-machine position (BoundaryConversation primitive shard 8 owns the state; the router merely dispatches).
    4. Write an inbound-message Ledger row (NOT a `channel_connected` event; this is the per-message audit row referenced in `specs/channel-adapters.md` § Error taxonomy footer "All errors persisted to Ledger").

    Per `rules/facade-manager-detection.md` Rule 3, the `InboundRouter`'s `__init__` takes its dependencies (every registered `ChannelAdapter`, the Boundary Conversation runtime, the `EnvoyLedger`, the `TrustStoreAdapter`, the `GrantMomentOrchestrator`) explicitly.

13. **`envoy.channels.grant_moment_renderer.GrantMomentRenderer`** (per key design question #7) — per-channel implementation of `render_grant_moment(request: GrantMomentRequest) → asyncio.Future[GrantMomentResult]` declared on each `ChannelAdapter` subclass. The renderer:
    1. Translates the wire-format `GrantMomentRequest` into the channel-native UI shape (Telegram inline keyboard, Slack Block Kit, Discord Components, WhatsApp interactive, iMessage / Signal numbered text, CLI prompt, Web modal).
    2. Verifies `request.primary_only` against `self.is_primary` (per `specs/channel-adapters.md` § Primary-channel binding line 183-185); raises `NotPrimaryChannelError` from non-primary adapters.
    3. Renders the visible secret per `specs/channel-adapters.md` § Side-channel hygiene (T-018 — `tests/regression/test_t018_visible_secret_per_channel.py` line 233); the rendered bytes MUST byte-match the Trust-Vault stored secret (the Grant Moment orchestrator's `VisibleSecretMismatchError` check per shard 10 § 3.2 item 6 fires from the orchestrator side; the renderer's responsibility is faithful render, not the comparison).
    4. Awaits user response via channel-native callback (Telegram callback_query, Slack interaction payload, Discord interaction, WhatsApp button reply webhook, iMessage / Signal text reply parsing, CLI input, Web POST).
    5. Constructs `GrantMomentResult` (canonicalized via shared JCS+NFC pipeline; signed by `delegation_key` for approve/modify, unsigned for deny per `specs/grant-moment.md` line 51) and resolves the future.

14. **`envoy.channels.rate_limit.PerChannelRateLimiter`** (per key design question #3) — **per-channel queue, NOT unified.** Each adapter has its own `RateLimitStatus` because each channel has its own quota: Telegram 30 msg/sec/bot; Slack tier-based (Tier 1: 1 msg/min, Tier 4: 100+/min); Discord 5/sec/channel; WhatsApp 24h customer-care window; Signal undocumented; iMessage best-effort (BlueBubbles relays); CLI no quota; Web no quota (localhost). A unified queue would couple unrelated channels — a Discord rate-limit hit would block Slack sends, which is wrong. Per-channel queues with cross-channel session-state coordination via Trust store + Ledger is the structural shape. **This is the answer to key design question #3: per-channel, not unified.**

15. **`envoy.channels.credentials.CredentialResolver`** (per key design question #2) — adapter `startup(config)` calls `CredentialResolver.resolve(channel_id)` which:
    1. Queries `ConnectionVault.list_by_principal()` for entries with matching `service_identifier` (e.g. `"telegram.bot_token"`, `"slack.bot_token"`, `"slack.signing_secret"`, `"discord.bot_token"`, `"whatsapp.app_secret"`, `"bluebubbles.password"`, `"signal.group_link"`).
    2. Validates the entry's `entry_envelope_scope` is included in the active envelope (per `specs/connection-vault.md` § Per-entry schema; raises `EnvelopeScopeMismatchError`).
    3. Returns the secret + entry metadata.
    4. **Failure mode if credentials missing: raises `AuthenticationError` (per `specs/channel-adapters.md` § Error taxonomy line 211); the adapter's `startup` raises `StartupTimeoutError` after the 10s window if Vault unreachable** (per spec line 25 + line 202). The Boundary Conversation onboarding ritual (shard 8) is the structural defense — first-time installation ALWAYS lands credentials in the Vault before adapters startup. **This is the answer to key design question #2: missing creds → typed `AuthenticationError`, fail-closed; the adapter never falls back to insecure behavior or env-var ad-hoc lookup.**

16. **`envoy.channels.cross_channel_coherence` — STATE-STORE delegation contract (NOT a module of its own; documented here as the structural contract).** Per key design question #5: cross-channel coherence (Grant approved on Telegram is honored when an action initiates from Slack 3 days later) is a STATE STORE concern. The contract is:
    - **Trust store (shard 5) is the authoritative state surface for cross-channel session continuity.** A DelegationRecord written on Telegram-channel Grant Moment approval is queried by Slack-channel action-evaluation 3 days later via `TrustStoreAdapter.find_active_delegation(principal_id, action_signature, time_window=7d)`. The delegation is channel-agnostic; `chain_parent_id` traverses regardless of origin channel.
    - **Ledger (shard 6) is the audit surface for cross-channel events.** `channel_connected`, `channel_disconnected`, every `system_error`, and every `grant_moment` Ledger row carries `channel_id` so cross-channel queries are auditable.
    - **Channel adapters MUST NOT maintain a parallel session-state store.** The single deviation from this rule is the per-adapter `rate_limit_status()` cache, which is intentionally per-adapter because it tracks channel-API-vendor quotas, not session state.
    - **The 7-day cross-channel coherence test (EC-8 acceptance gate per `02-mvp-objectives.md` line 116) is structurally answered by Trust-store-driven coherence, NOT by adapter coordination.** The adapter is stateless from the coherence-perspective; the Trust store + Ledger pair is the coherent state.

### 3.3 Cross-channel coherence — answered as Trust-store + Ledger delegation

This subsection collapses key design question #5 explicitly. Per `specs/channel-adapters.md` § Cross-channel session continuity (line 179): "Single session across all active channels for a principal. Visible secret rendered in every channel. Grant Moment approval on any channel resolves session globally; other channels see 'resolved elsewhere.'"

The **session_id** field on `InboundMessage` per `specs/channel-adapters.md` § Message envelope (line 152) is the cross-channel session-continuity key. The session_id is generated by the BoundaryConversation primitive (shard 8) at session start; it is associated with the `principal_genesis_id` in the Trust store via a `SessionRecord` (Envoy-new-code dataclass; persisted in the Trust store sqlite layer per shard 5 § 4 with `principal_id` keying ready for Phase 03 multi-principal). Every channel adapter looks up the session_id via Trust store on inbound message arrival; every Grant Moment orchestrator reads / writes session_id-keyed delegation records.

**EC-8 acceptance test (`tests/e2e/test_session_continuity_8_channels.py` per `specs/channel-adapters.md` line 238) verification path:**

1. User opens session on Telegram (Day 1).
2. Trust store records `SessionRecord(principal_id, session_id, channels_active=["telegram"])`.
3. User approves a Grant Moment on Telegram (Day 1) — `DelegationRecord` written via `TrustStoreAdapter.record_delegation` is keyed by session_id, not channel_id.
4. User adds Slack channel mid-session (Day 3); `SessionRecord.channels_active=["telegram", "slack"]` updated.
5. User initiates an action from Slack (Day 6) that requires the Day-1 grant.
6. Slack adapter routes via `InboundRouter`; the router queries Trust store for the active delegation by `(principal_id, action_signature, time_window=7d)`; the Day-1 delegation is found; action proceeds.
7. User revokes Day-1 grant from CLI (Day 7); cascade revocation per shard 5 § 3.3 + shard 10 § 3.2 item 7 reaches every descendant regardless of origin channel; both grants revoked.

The EC-8 test passes structurally because the Trust store is channel-agnostic; channel adapters are stateless I/O substrates.

### 3.4 What is explicitly NOT Envoy-new-code

- **Webhook receive path** — `nexus.transports.webhook.WebhookTransport` is the upstream provider. Per `rules/zero-tolerance.md` Rule 4, Envoy MUST NOT re-implement webhook receive; Envoy MUST implement the per-channel `WebhookSigner` Protocol for signature verification.
- **WebSocket upgrade with Origin allowlist** — `Nexus.register_websocket(..., allowed_origins=[...])` is the upstream provider per #673.
- **CLI / API / MCP base channel** — `kailash.channels.{cli_channel, api_channel, mcp_channel}` are the upstream providers. Phase 01 wraps the first two (CLI + API for Web); MCP is Phase 02.
- **Session storage primitives** — Trust store (shard 5) + Ledger (shard 6); the channel adapters are clients, not maintainers.
- **A2A messaging cross-principal flow** — `specs/a2a-messaging.md` line 13 — "Phase 03 deliverable." Phase 01 channel adapters MUST NOT implement the A2A wire protocol or cross-principal dual-signed action.
- **Grant Moment state machine** — owned by `envoy.grant_moment.GrantMomentOrchestrator` per shard 10 § 4. The adapter's `render_grant_moment` is a UI-translation function; the M0→M4 state machine is not the adapter's concern.
- **Boundary Conversation runtime** — owned by `envoy.boundary` per shard 8. The adapter routes inbound messages via `InboundRouter`; the conversation script DAG, the suspension primitive, the model-router invocation are all upstream-of-the-adapter.
- **Phase 02 ritual surfaces** — `send_posture_review` and `send_monthly_report` are on the Phase 01 ABC for forward-compatibility but raise typed `PhaseDeferredError` until shard 11 + future shards land their producer side.

---

## 4. Class structure sketch (interfaces only)

Module path (Envoy-side, proposed): `envoy.channels`.

```python
# envoy/channels/__init__.py
from envoy.channels.adapter import ChannelAdapter
from envoy.channels.envelope import (
    InboundMessage, MessagePayload, VisibleSecret,
    SendReceipt, GrantMomentReceipt, PostureReviewReceipt,
    RateLimitStatus, ChannelCapabilities,
)
from envoy.channels.errors import (
    ChannelAdapterError, StartupTimeoutError, AlreadyStartedError,
    ChannelTransportError, SendTimeoutError, RateLimitExceededError,
    NotPrimaryChannelError, GrantMomentExpiredError, PrincipalNotFoundError,
    AuthenticationError, PayloadTooLargeError,
)
from envoy.channels.cli import CLIChannelAdapter
from envoy.channels.web import WebChannelAdapter
from envoy.channels.telegram import TelegramChannelAdapter
from envoy.channels.slack import SlackChannelAdapter
from envoy.channels.discord import DiscordChannelAdapter
from envoy.channels.whatsapp import WhatsAppChannelAdapter
from envoy.channels.imessage import IMessageChannelAdapter
from envoy.channels.signal import SignalChannelAdapter
from envoy.channels.router import InboundRouter
from envoy.channels.credentials import CredentialResolver

__all__ = [
    "ChannelAdapter",
    "InboundMessage", "MessagePayload", "VisibleSecret",
    "SendReceipt", "GrantMomentReceipt", "PostureReviewReceipt",
    "RateLimitStatus", "ChannelCapabilities",
    "ChannelAdapterError", "StartupTimeoutError", "AlreadyStartedError",
    "ChannelTransportError", "SendTimeoutError", "RateLimitExceededError",
    "NotPrimaryChannelError", "GrantMomentExpiredError", "PrincipalNotFoundError",
    "AuthenticationError", "PayloadTooLargeError",
    "CLIChannelAdapter", "WebChannelAdapter",
    "TelegramChannelAdapter", "SlackChannelAdapter", "DiscordChannelAdapter",
    "WhatsAppChannelAdapter", "IMessageChannelAdapter", "SignalChannelAdapter",
    "InboundRouter", "CredentialResolver",
]
```

```python
# envoy/channels/envelope.py
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

@dataclass(frozen=True)
class ChannelCapabilities:
    """Per specs/channel-adapters.md § ChannelCapabilities (lines 132-143)."""
    supports_buttons: bool
    supports_attachments: bool
    supports_markdown: bool
    supports_voice: bool
    supports_reactions: bool
    max_message_length: int

@dataclass(frozen=True)
class VisibleSecret:
    """Per specs/visible-secret.md (cross-spec). Bytes rendered in every channel
    per specs/channel-adapters.md § Cross-channel session continuity."""
    bytes_hex: str
    nonce: str
    rendered_at: datetime

@dataclass(frozen=True)
class MessagePayload:
    body: str
    attachments: tuple = ()
    metadata: dict | None = None

@dataclass(frozen=True)
class InboundMessage:
    """Per specs/channel-adapters.md § Message envelope (lines 148-159).
    8 fields exactly; principal_genesis_id verified at adapter boundary."""
    channel_id: str
    session_id: str
    principal_genesis_id: str  # sha256 hex
    direction: Literal["inbound", "outbound"]
    content_trust_level: Literal["user", "system", "tool", "agent"]
    payload: MessagePayload
    visible_secret_rendered: VisibleSecret | None
    timestamp: datetime  # adapter-assigned UTC

@dataclass(frozen=True)
class SendReceipt:
    message_id: str
    delivered_at: datetime
    channel_native_id: str

@dataclass(frozen=True)
class GrantMomentReceipt:
    grant_id: str
    decision: Literal["approve_once", "approve_and_author", "deny", "modify", "expired"]
    decided_at: datetime
    channel_signature: str | None  # None for "deny" per specs/grant-moment.md line 51

@dataclass(frozen=True)
class RateLimitStatus:
    requests_remaining: int
    window_resets_at: datetime
    soft_quota_warning: bool  # True at >=80% utilization

# envoy/channels/adapter.py
from abc import ABC, abstractmethod
from typing import AsyncIterator

class ChannelAdapter(ABC):
    """Abstract base class implementing specs/channel-adapters.md § Adapter contract.

    Per rules/facade-manager-detection.md Rule 3, subclass __init__ takes
    dependencies (ConnectionVault, EnvoyLedger, TrustStoreAdapter,
    GrantMomentOrchestrator) explicitly.

    Per rules/orphan-detection.md Rule 1, every concrete subclass has at least
    one production call site (envoy.runtime.session.SessionRouter iterates
    registered adapters at startup).
    """

    @property
    @abstractmethod
    def channel_id(self) -> str: ...

    @property
    @abstractmethod
    def is_primary(self) -> bool:
        """Per specs/channel-adapters.md § Primary-channel binding (H-03).
        High-stakes Grant Moments only render on primary channel."""

    @property
    @abstractmethod
    def capabilities(self) -> ChannelCapabilities: ...

    @abstractmethod
    async def startup(self, config: "ChannelConfig") -> None:
        """Per specs/channel-adapters.md lines 24-30.
        Timeout 10s, fail-closed, raises StartupTimeoutError.
        Idempotent: second call raises AlreadyStartedError."""

    @abstractmethod
    async def shutdown(self, drain_timeout_seconds: int = 5) -> None:
        """Per specs/channel-adapters.md lines 32-37.
        Drain pending sends; force-close after timeout; idempotent."""

    @abstractmethod
    async def receive_message(self) -> AsyncIterator[InboundMessage]:
        """Per specs/channel-adapters.md lines 43-48.
        Bounded queue 100 per channel; OverflowDropEvent to Ledger on overflow."""

    @abstractmethod
    async def send_message(
        self, target_principal_id: str, payload: MessagePayload, *,
        visible_secret: VisibleSecret | None = None,
        timeout_seconds: int = 10,
    ) -> SendReceipt: ...

    @abstractmethod
    async def send_grant_moment(
        self, target_principal_id: str, grant: "GrantMomentPayload", *,
        primary_only: bool = False, timeout_seconds: int = 30,
    ) -> GrantMomentReceipt:
        """Per specs/channel-adapters.md lines 69-79 + specs/grant-moment.md
        § Rendering (lines 78-86)."""

    @abstractmethod
    async def render_grant_moment(
        self, request: "envoy.grant_moment.GrantMomentRequest",
    ) -> "asyncio.Future[envoy.grant_moment.GrantMomentResult]":
        """Per shard 10 § 3.2 item 5. Per-channel UI rendering of the
        GrantMomentRequest; awaits user response; resolves with signed
        GrantMomentResult (or unsigned for deny per specs/grant-moment.md
        line 51).
        Raises NotPrimaryChannelError if request.primary_only and not is_primary."""

    @abstractmethod
    async def send_digest(
        self, target_principal_id: str, digest: "DailyDigestPayload", *,
        timeout_seconds: int = 10,
    ) -> SendReceipt:
        """Per specs/channel-adapters.md lines 81-89.
        Rate-limit: 1/principal/24h enforced by adapter."""

    async def send_posture_review(self, *args, **kwargs):
        """Phase 02 — raises PhaseDeferredError per rules/zero-tolerance.md Rule 2."""
        raise PhaseDeferredError("send_posture_review is Phase 02 (shard 11+)")

    async def send_monthly_report(self, *args, **kwargs):
        """Phase 02 — raises PhaseDeferredError per rules/zero-tolerance.md Rule 2."""
        raise PhaseDeferredError("send_monthly_report is Phase 02")

    @abstractmethod
    async def rate_limit_status(self) -> RateLimitStatus: ...

# envoy/channels/router.py
from typing import Iterable

class InboundRouter:
    """Singleton orchestrator routing inbound messages to Boundary Conversation
    or Grant Moment resolution. Per § 3.2 item 12.

    Per rules/facade-manager-detection.md Rule 3: explicit deps."""

    def __init__(
        self,
        *,
        adapters: Iterable[ChannelAdapter],
        boundary_conversation: "envoy.boundary.BoundaryConversationRuntime",
        grant_moment: "envoy.grant_moment.GrantMomentOrchestrator",
        ledger: "envoy.ledger.EnvoyLedger",
        trust_store: "envoy.trust.TrustStoreAdapter",
    ) -> None: ...

    async def run(self) -> None:
        """Subscribe to every adapter's receive_message() concurrently;
        for each InboundMessage:
          1. Verify principal_genesis_id against Trust store
          2. Resolve cross-channel session_id via Trust store SessionRecord
          3. Route to Boundary Conversation or Grant Moment resolution
          4. Write inbound-message Ledger row (channel_id, session_id, principal_id_redacted)
        """
        ...

# envoy/channels/credentials.py
from uuid import UUID

class CredentialResolver:
    """Per § 3.2 item 15. Adapter startup resolves credentials via this class.

    Failure mode (per shard 14 § 3.1 fail-closed defaults):
      - Vault unreachable → KeychainUnavailableError → adapter.startup raises StartupTimeoutError
      - Entry not found → EntryNotFoundError → AuthenticationError raised
      - Envelope-scope mismatch → EnvelopeScopeMismatchError raised
      - Expired entry → EntryExpiredError → AuthenticationError raised
    """

    def __init__(
        self,
        *,
        connection_vault: "envoy.connection_vault.ConnectionVault",
        active_envelope: "envoy.envelope.SessionEnvelope",
    ) -> None: ...

    async def resolve(self, channel_id: str, service_identifier: str) -> tuple[UUID, str]:
        """Returns (entry_id, secret) tuple. Raises typed errors per failure mode."""
        ...
```

Per `rules/orphan-detection.md` Rule 1, the 8 concrete adapter classes have a single production call site each: `envoy.runtime.session.SessionRouter.bootstrap_channels()` constructs each enabled adapter at runtime startup and registers it with the `InboundRouter`. Per `rules/facade-manager-detection.md` Rule 1 + Rule 2, the Tier 2 wiring tests in § 6 are named per the convention.

Per `rules/orphan-detection.md` § 6 (`__all__` discipline), the package's `__init__.py` lists every exported symbol; per § 7 (consumer tree sweep), Phase 01 has no in-tree consumers outside `envoy.runtime` so no cross-tree grep is required.

---

## 5. Integration points

The 8-adapter primitive composes 6 neighbouring primitives. Each is a clean unidirectional or bidirectional hop. Per `rules/orphan-detection.md` Rule 1, each integration MUST have a production call site within 5 commits of the adapter classes landing.

| Neighbouring primitive (shard) | Hook                                                                                                                                                                                                                                                                                                                                                                                                      | Direction      | Spec citation                                                                                                                     |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Connection Vault (14)          | `CredentialResolver.resolve(channel_id, service_identifier) → (entry_id, secret)` invoked at every adapter's `startup(config)`; failure → `AuthenticationError` per § 3.2 item 15                                                                                                                                                                                                                         | CA → CV (read) | shard 14 § 5.1; `specs/connection-vault.md` § Per-entry schema                                                                    |
| Boundary Conversation (8)      | `InboundRouter` dispatches inbound `InboundMessage` to the active Boundary Conversation runtime; the conversation's PlanSuspension-resume path consumes the message                                                                                                                                                                                                                                       | CA → BC        | shard 8 (boundary-conversation-implementation.md); `specs/boundary-conversation.md` § PlanSuspension                              |
| Grant Moment (10)              | Each adapter's `render_grant_moment(request) → Future[result]` is the UI-side of `ChannelHandoff.dispatch(request, channel, timeout)`; the orchestrator dispatches per shard 10 § 3.2 item 5                                                                                                                                                                                                              | GM → CA → GM   | shard 10 § 3.2; `specs/grant-moment.md` § Rendering + § Cross-references                                                          |
| Envoy Ledger (6)               | Every adapter writes `channel_connected` at `startup` complete; `channel_disconnected` at `shutdown` complete; every error from § 1 Error taxonomy persists as `system_error`; every inbound message persists as an audit row (per `specs/channel-adapters.md` Error taxonomy footer); the `format_record_id_for_event(target_principal_id)` redaction per `rules/event-payload-classification.md` Rule 1 | CA → L         | shard 6 § 5.1 row "Channel adapters"; `rules/event-payload-classification.md` Rule 1                                              |
| Trust store (5)                | `InboundRouter` queries `TrustStoreAdapter.find_session(principal_id) → SessionRecord` to resolve cross-channel `session_id`; queries `TrustStoreAdapter.find_active_delegation(principal_id, action_signature, time_window=7d)` for cross-channel coherence (EC-8 acceptance)                                                                                                                            | CA → TS (read) | shard 5 § 4; `specs/trust-lineage.md` § Schema § DelegationRecord; `specs/channel-adapters.md` § Cross-channel session continuity |
| Daily Digest (11)              | Daily Digest renders per-channel via `adapter.send_digest(target_principal_id, digest, timeout_seconds=10)`; the adapter is the outbound rendering substrate; the digest content is composed by shard 11 from Ledger query                                                                                                                                                                                | DD → CA        | shard 11 (TBD); `specs/channel-adapters.md` § Ritual delivery line 81-89                                                          |

Per `rules/orphan-detection.md` Rule 1, the adapter shard's PR ships:

- Each of the 8 concrete adapter classes (6 messaging + CLI + Web)
- The `InboundRouter` with at least one routed inbound message asserting end-to-end through Boundary Conversation
- The `CredentialResolver` with at least one production resolve call from an adapter startup
- The Grant Moment renderer per channel with at least one Grant Moment request flowing GM → adapter → GM through the dispatch contract

Secondary integrations (Daily Digest outbound rendering; cross-channel descendant revoke from EC-8) land with their respective shard PRs.

---

## 6. Tier 2 / Tier 3 test surface

Per `rules/testing.md` § "Tier 2 (Integration): Real infrastructure recommended" — real channels (Telegram bot in test mode against the real Telegram Bot API; real Slack workspace against the real Slack API; real Discord channel against the real Discord API for at least 3 of the 8 channels per the prompt's guidance); Tier 3 with cassette / fixture for the remaining (WhatsApp Cloud API sandbox; signal-cli local instance; BlueBubbles local instance for iMessage). Per `rules/testing.md` no mocking at the binding boundary — channel-API client libs are real; what we record/replay is the HTTP traffic via `vcrpy` / `pytest-recording` for the channels we cannot exercise live in CI.

Per `rules/orphan-detection.md` Rule 1 + Rule 2 + `rules/facade-manager-detection.md` Rule 1 + Rule 2: every adapter MUST have a Tier 2 wiring test that imports through the facade and asserts an externally-observable effect.

### 6.1 Tier 2 — per-channel adapter wiring (8 files)

Per `specs/channel-adapters.md` § Test location lines 230–238:

| Test file                                                       | What it exercises                                                                                                                                                                               | EC tested |
| --------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| `tests/integration/channels/test_cli_adapter_lifecycle.py`      | startup/shutdown idempotency, drain timeout, real stdin/stdout via pexpect                                                                                                                      | EC-7      |
| `tests/integration/channels/test_web_adapter_lifecycle.py`      | localhost bind, register_websocket allowed_origins enforcement, SSE drain post-#767                                                                                                             | EC-7      |
| `tests/integration/channels/test_telegram_adapter_lifecycle.py` | real Telegram Bot API with test bot token; webhook signer verifies `X-Telegram-Bot-Api-Secret-Token`; rate_limit_status reports actual quota                                                    | EC-7      |
| `tests/integration/channels/test_slack_adapter_lifecycle.py`    | real Slack workspace with test bot; HMAC-SHA256 signer; Tier-N quota reporting                                                                                                                  | EC-7      |
| `tests/integration/channels/test_discord_adapter_lifecycle.py`  | real Discord test guild with test bot; Ed25519 signer; quota tracking                                                                                                                           | EC-7      |
| `tests/integration/channels/test_whatsapp_adapter_lifecycle.py` | WhatsApp Cloud API sandbox via vcrpy cassette; HMAC-SHA256 signer                                                                                                                               | EC-7      |
| `tests/integration/channels/test_signal_adapter_lifecycle.py`   | local signal-cli instance via Path B Group Link (per spec line 172); cassette-replay where signal-cli unavailable in CI                                                                         | EC-7      |
| `tests/integration/channels/test_imessage_adapter_lifecycle.py` | local BlueBubbles server via cassette (no CI Mac in default Linux runner); marked `@pytest.mark.skipif(not BLUEBUBBLES_AVAILABLE)` per `rules/testing.md` § Test-Skip Triage ACCEPTABLE pattern | EC-7      |

Per `rules/testing.md` § "MUST: Verify NEW modules have NEW tests": every new module in `envoy.channels.*` has at least one importing test in `tests/integration/channels/`; the audit-mode grep is `grep -rln "from envoy.channels.<channel> import\|import envoy.channels.<channel>" tests/`.

### 6.2 Tier 2 — per-channel send + ritual-delivery (16 files)

Per `specs/channel-adapters.md` line 231 + 232:

For each of the 8 channels, two test files:

- `tests/integration/channels/test_<channel>_send_message.py` — send_message timeout, rate-limit, payload-too-large, real channel send + read-back per `rules/testing.md` § Tier 3 ("every write MUST be verified with a read-back").
- `tests/integration/channels/test_<channel>_ritual_delivery.py` — `send_grant_moment` (with `primary_only=True/False`), `send_digest` (1/24h cache enforcement), `render_grant_moment` (UI-translation correctness per § 3.2 item 13).

### 6.3 Tier 2 — cross-cutting wiring (per `rules/facade-manager-detection.md` Rule 2)

| Test file                                                       | What it exercises                                                                                                                                                                                                                                                                                                            | EC tested   |
| --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| `tests/integration/test_inbound_router_wiring.py`               | Constructs a real `InboundRouter` with all 8 adapters + real Boundary Conversation runtime + real Trust store + real Ledger; injects an `InboundMessage` from each adapter's mock receive queue; asserts each routes correctly to the active Boundary Conversation; asserts a Ledger inbound-message row is written for each | EC-7        |
| `tests/integration/test_credential_resolver_wiring.py`          | Adapter startup with missing Vault entry → `AuthenticationError`; Vault unreachable → `KeychainUnavailableError` → `StartupTimeoutError` from adapter; envelope-scope mismatch → `EnvelopeScopeMismatchError`                                                                                                                | EC-7        |
| `tests/integration/test_grant_moment_render_all_channels.py`    | (Cross-shard with shard 10 § 6.1) For each of the 8 channels, dispatch a `GrantMomentRequest`; assert the channel-native UI renders all 4 spec decisions (`approve_once / approve_and_author / deny / modify`); assert the resolution future resolves with valid signed result                                               | EC-2 + EC-7 |
| `tests/integration/test_h03_primary_channel_binding.py`         | Per `specs/channel-adapters.md` line 237: high-stakes Grant Moment with `primary_only=True` raises `NotPrimaryChannelError` from non-primary adapters; the error message names the user's designated primary channel                                                                                                         | EC-2        |
| `tests/integration/test_session_id_cross_channel_continuity.py` | Per § 3.3: open session on Telegram, write a `SessionRecord`; add Slack channel; assert `session_id` is consistent across both adapters via Trust-store query                                                                                                                                                                | EC-7 + EC-8 |

### 6.4 Tier 2 — regression (T-018, T-070, T-080, T-023)

Per `specs/channel-adapters.md` § Test location lines 233–236:

| Test file                                                  | Threat                                                                                                 | Phase 01 ship?                     |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------- |
| `tests/regression/test_t018_visible_secret_per_channel.py` | T-018; visible-secret rendered every channel; bytes byte-match Trust-Vault stored secret               | Yes — load-bearing for EC-2 + EC-7 |
| `tests/regression/test_t070_clipboard_autoclear.py`        | T-070; clipboard auto-clear 30s for credential paste paths                                             | Yes — Phase 01 desktop             |
| `tests/regression/test_t080_tls13_pin.py`                  | T-080; TLS 1.3 minimum + Foundation cert pin for Foundation endpoints; OS trust store for third-party  | Yes                                |
| `tests/regression/test_t023_signal_path_b.py`              | T-023; Signal Path B legal-gate enforcement (Group Link only; Path A signal-cli linked-phone deferred) | Yes — Path B default               |

### 6.5 Tier 3 — EC-7 + EC-8 acceptance gates

| Test file                                            | What it exercises                                                                                                                                                                                                                                                                                                    | EC tested |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| `tests/e2e/test_session_continuity_8_channels.py`    | Per `specs/channel-adapters.md` line 238: single session resolves Grant Moment from any channel; "resolved elsewhere" surface on other channels; full N=24 onboarding battery (8 channels × N=3 sessions per `02-mvp-objectives.md` line 104)                                                                        | **EC-7**  |
| `tests/e2e/test_ec8_7day_cross_channel_coherence.py` | Per `02-mvp-objectives.md` lines 116–117: 7-day operating window across ≥4 of the 8 channels; (a) zero state-drift findings via daily cross-channel state-equivalence test; (b) no double-billing in Budget tracker; (c) cascade revocation Day-1 grant on Channel A → Day-6 child grant on Channel B → both revoked | **EC-8**  |

### 6.6 Cross-channel session-equivalence test (continuous; runs daily during EC-8 window)

Per `02-mvp-objectives.md` line 116 acceptance gate: "a cross-channel state-equivalence test that runs daily." Test shape:

1. Snapshot `TrustStoreAdapter.find_session(principal_id) → SessionRecord` from each of the active channels' adapter-bound runtime.
2. Assert all snapshots return the same `SessionRecord` (channel-agnostic state).
3. Snapshot the active envelope hash from each adapter's `CredentialResolver` checks.
4. Assert all envelope hashes match — no per-adapter drift.
5. Snapshot Ledger query `EnvoyLedger.query(filter={types: ["grant_moment"], session_id: <session>}, limit=100)` from each adapter's process boundary.
6. Assert all queries return identical row sets.

Failure of any snapshot assertion is a HIGH finding — channel adapters have drifted into maintaining per-adapter state, violating § 3.3 cross-channel coherence delegation.

### 6.7 Mechanical sweep (for /redteam)

Per `rules/agents.md` § "Reviewer Prompts Include Mechanical AST/Grep Sweep":

```bash
# Every concrete adapter has a wiring test
for ch in cli web telegram slack discord whatsapp signal imessage; do
  count=$(grep -rln "from envoy.channels.${ch} import\|import envoy.channels.${ch}" tests/integration/channels/ | wc -l)
  if [ "$count" -eq 0 ]; then
    echo "MISSING: tests/integration/channels/test_${ch}_*.py does not import the adapter"
  fi
done

# Every adapter writes channel_connected/channel_disconnected Ledger rows
grep -rln 'EnvoyLedger.append("channel_connected"' envoy/channels/  # ≥8 hits
grep -rln 'EnvoyLedger.append("channel_disconnected"' envoy/channels/  # ≥8 hits

# No adapter maintains a parallel session store (forbidden per § 3.3)
grep -rln 'session_state\|session_cache\|local_session' envoy/channels/
# ↑ should be empty; any hit is a violation of Trust-store-delegated coherence

# render_grant_moment is implemented on every adapter (8 hits)
grep -rln 'def render_grant_moment\|async def render_grant_moment' envoy/channels/  # ≥8

# No raw signature comparison (rules/security.md § Constant-time comparison)
grep -rln 'signature ==\|hmac\.compare_digest\b\|secrets\.compare_digest\b' envoy/channels/
# ↑ raw `==` is BLOCKED; only secrets.compare_digest acceptable

# Connection Vault is the credential source (no env-var ad-hoc lookup)
grep -rln 'os\.environ\.get.*TOKEN\|os\.getenv.*TOKEN' envoy/channels/
# ↑ should be empty; credentials route through CredentialResolver only

# Origin allowlist on Web channel websocket (per #673)
grep -rln 'allowed_origins=' envoy/channels/web.py  # ≥1 hit
```

Per `rules/event-payload-classification.md` Rule 4: a Tier 2 test asserts `principal_genesis_id` redaction in the inbound-message Ledger row's DomainEvent payload — `record_id` is `sha256:XXXXXXXX`-prefixed; raw value not in `repr(payload)`.

Per `rules/tenant-isolation.md` Rule 5: every adapter's Ledger writes carry `tenant_id` (= `principal_genesis_id` in single-principal Phase 01 per `00-inheritance-from-phase-00.md` § 6 invariant #1) AND `channel_id`; verified via `EXPLAIN QUERY PLAN` that both are indexed.

### 6.8 Test-skip triage discipline (per `rules/testing.md` § Test-Skip Triage)

Where live channels are unavailable in CI:

```python
# ACCEPTABLE — per rules/testing.md ACCEPTABLE tier
@pytest.mark.skipif(
    os.environ.get("TELEGRAM_TEST_BOT_TOKEN") is None,
    reason="requires TELEGRAM_TEST_BOT_TOKEN env var (test-mode bot)",
)
async def test_telegram_send_message_real_api(): ...

# ACCEPTABLE — BlueBubbles requires user-owned Mac
@pytest.mark.skipif(
    os.environ.get("BLUEBUBBLES_TEST_URL") is None,
    reason="requires BlueBubbles server on user-owned Mac",
)
async def test_imessage_adapter_real_bluebubbles(): ...
```

Cassette-recorded paths (vcrpy) for vendor-API rate-limit-sensitive tests run unconditionally in CI; live tests run when env vars present (developer machine + per-vendor CI key).

Per `rules/testing.md` § Env-Var Test Isolation: tests that mutate `*_BOT_TOKEN` / `*_SIGNING_SECRET` env vars MUST hold the module-scope lock; the adapter constructor reads env vars only when `CredentialResolver` Vault path is unset (test-fixture path), so the env-var race is real.

---

## 7. Frozen-spec ambiguity check + de-scope #1 disposition

Per `01-shard-plan.md` § 4 failure-mode protocol: if a primitive deep-dive surfaces a HIGH gap, STOP the deep-dive; convene MUST-Rule-5b sweep before continuing.

This shard surfaced **NO HIGH-severity ambiguity** in `specs/channel-adapters.md` or `specs/a2a-messaging.md`. Two MEDIUM-severity items are noted; one (de-scope #1 candidate) is structurally pre-declared in `02-mvp-objectives.md` § 5 row "EC-7" so it is a budget-management decision, not a spec ambiguity.

### 7.1 MED-1 — iMessage / Signal feasibility (key design question #4 + de-scope #1 candidate)

The shard prompt asks: "iMessage / Signal: These are particularly hard (no public API for iMessage outside macOS Continuity; Signal requires linking a phone). State the Phase 01 minimum and document Phase 02+ extensions; recommend the de-scope #1 disposition (drop these two if needed for ship)."

**Phase 01 minimum stated in § 3.2 items 10 + 11:**

- iMessage: BlueBubbles bridge against user-owned Mac. User accepts Apple-ToS grey-area risk per `specs/channel-adapters.md` line 173 ("user responsibility"). Phase 01 ships the adapter; Tier 2 test marked `skipif` when no Mac available.
- Signal: Path B (Group Link only) per `specs/channel-adapters.md` line 172 ("Phase 01 legal gate (Path B default)"). Path A (signal-cli with linked phone) is the Phase 01-blocker per T-023.

**De-scope #1 disposition recommendation (RECOMMENDED: SHIP 8, fall back to drop iMessage + Signal if EC-7 cohort fails):**

Per `02-mvp-objectives.md` § 5 row "EC-7": "DEGRADE-ACCEPTABLE — execute pre-declared de-scope #1 (reduce 6 messaging channels to 3); EC-7 acceptance becomes 5-channel set." This is a structurally pre-declared escape hatch for EC-7 cohort failure.

The recommendation: **attempt 8-channel ship (CLI + Web + 6 messaging), with iMessage + Signal as the de-scope candidates if cohort falls below N=3 successful onboardings on those two channels.** The reasoning:

1. **Telegram + Slack + Discord + WhatsApp are clean** — public APIs, Foundation-friendly compliance posture, well-documented webhook patterns. The Envoy-new-code surface is ~150 LOC per adapter pattern-matched on the same `WebhookTransport` + `WebhookSigner` shape (per § 2.2 #687). These four are NOT the de-scope candidates.
2. **iMessage requires user-owned Mac + Apple-ToS grey-area BlueBubbles bridge**. Cohort UX risk: the user must install BlueBubbles on their own Mac before Envoy onboarding — a non-trivial pre-requisite that may break EC-7's 25-minute first-time-user budget for users without an existing Mac+BlueBubbles setup.
3. **Signal Path B (Group Link) is materially weaker UX than Path A** — every message routes through a Signal Group, not 1:1 DMs. Cohort feedback may show that "Envoy DMs me on Signal" expectations don't match the Group-Link reality, lowering the EC-7 "completion time deviation within 2x of CLI baseline" gate.
4. **De-scope #1 retains 5 channels (CLI + Web + Telegram + Slack + Discord OR WhatsApp)** — this 5-set still demonstrates BET-11 (channel-as-UI thesis) credibly because it spans CLI + Web + 3 distinct messaging vendors with different UX shapes (Telegram inline-keyboard, Slack Block Kit, Discord Components, WhatsApp interactive). The thesis is NOT "8 channels"; the thesis is "channel-native onboarding works across distinct UX shapes." 5 channels of distinct shape suffice.

The structural de-scope trigger per `02-mvp-objectives.md` § 5: "if EC-7 cohort fails." Concretely: if N=3 first-time-user sessions on iMessage and on Signal each fail to complete EC-1 within 25 minutes (per `02-mvp-objectives.md` line 28 acceptance gate), drop those two channels from the EC-7 acceptance set. This is a **runtime cohort-driven decision**, not a Phase 01 architecture-time decision; this shard ships all 8 adapter classes and lets EC-7 cohort data drive the de-scope.

**Phase 02+ extensions for iMessage and Signal:**

- iMessage Phase 02+: native macOS Continuity bridging via AppleScript / `osascript`-driven Messages.app automation; native iOS CarBridge / CarPlay extension; Apple Business Messages enrollment (Foundation-led).
- Signal Phase 02+: Path A enrollment via signal-cli with linked-phone (legal gate clearance); Signal Stories integration; Signal sealed-sender / disappearing messages.

This recommendation is logged here for shard 23/24 redteam consumption and for `02-mvp-objectives.md` § 5 row "EC-7" structural reference. The doc does NOT trigger a spec edit (no MUST Rule 5b sweep) because `specs/channel-adapters.md` already enumerates iMessage + Signal with caveat language; the recommendation is operational, not structural.

### 7.2 MED-2 — A2A messaging Phase boundary (key design question #5 cross-spec consequence)

`specs/a2a-messaging.md` line 13 — "Phase 03 deliverable." Phase 01 single-principal channel adapters MUST NOT implement the A2A wire protocol or the cross-principal dual-signed action.

**Phase 01 disposition (LOW, no escalation):** the `principal_genesis_id` field on `InboundMessage` is verified at the adapter boundary in Phase 01 single-principal — the adapter rejects messages whose claimed sender does not match the bot's known principal mapping (raises `PrincipalNotFoundError`). This single-check does not require A2A primitives; it is a per-adapter principal-binding check. Phase 03 will extend this to cross-principal A2A, at which point the adapter will additionally invoke `kailash.eatp.A2A.verify(message)` (Phase 03 primitive) before routing to the recipient principal's runtime.

The `tests/integration/test_a2a_envelope_binding.py` and sibling A2A regression tests per `specs/a2a-messaging.md` § Test location lines 68–71 are Phase 03 deliverables; Phase 01 ships placeholders that `pytest.skip` with `reason="Phase 03 deliverable per specs/a2a-messaging.md line 13"`.

### 7.3 LOW — Other open questions

`specs/channel-adapters.md` § Open questions:

1. WhatsApp Foundation gateway vs user-own pricing/SLA — Phase 01 ships user-own only; Foundation gateway is Phase 02 dispositioned in § 3.2 item 9.
2. Signal Path B vs Path A — Phase 01 Path B per spec line 172; Path A Phase 02+.
3. Cross-channel session continuity merge semantics on concurrent decisions — Phase 01 disposition: **last-writer-wins via Trust-store transaction ordering**, with the loser surfacing "resolved elsewhere" per `specs/channel-adapters.md` line 181. The `find_active_delegation` query is by-time-window; the Trust store sqlite layer's atomic transaction is the merge primitive.
4. Phase 04 17-channel matrix — out of scope Phase 01.
5. Voice-channel transcription provenance — Phase 02+; `supports_voice` capability is declared but no voice path is wired.

### 7.4 None HIGH-severity surfaced

No HIGH-severity ambiguity surfaced. The Channel adapters primitive is well-specified for Phase 01 (8-channel surface explicit; per-channel caveats explicit; cross-channel coherence delegated to Trust store + Ledger; Grant Moment dispatch contract pinned at shard 10; Connection Vault credential flow pinned at shard 14). The MED items (iMessage / Signal feasibility; A2A Phase boundary) are implementation latitude, not spec gaps. Phase 01 implementation can proceed against `specs/channel-adapters.md` as frozen. No `01-shard-plan.md` § 4 escalation needed; no MUST-Rule-5b sweep needed.

---

## 8. Cross-references

### Frozen specs (DO NOT EDIT — read-only at this shard)

- `/Users/esperie/repos/dev/envoy/specs/channel-adapters.md` § Adapter contract (lines 14-130), § ChannelCapabilities (lines 132-143), § Message envelope (lines 148-159), § Phase 01 surfaces (lines 163-173), § Cross-channel session continuity (lines 179-181), § Primary-channel binding (H-03; lines 183-185), § Side-channel hygiene (T-070; lines 188-192), § Network security (T-080; lines 195-196), § Error taxonomy (lines 199-214), § Cross-references (lines 218-226), § Test location (lines 229-238), § Open questions (lines 241-246).
- `/Users/esperie/repos/dev/envoy/specs/a2a-messaging.md` line 13 (Phase 03 deliverable boundary), § A2A message schema (lines 17-29), § Test location (lines 68-71).
- `/Users/esperie/repos/dev/envoy/specs/connection-vault.md` § Per-entry schema (cross-spec via shard 14).
- `/Users/esperie/repos/dev/envoy/specs/grant-moment.md` § State machine + § Rendering + § Primary-channel binding (cross-spec via shard 10).
- `/Users/esperie/repos/dev/envoy/specs/ledger.md` § Entry types `channel_connected` / `channel_disconnected` + § System error (cross-spec via shard 6).
- `/Users/esperie/repos/dev/envoy/specs/boundary-conversation.md` § PlanSuspension (cross-spec via shard 8).

### Phase 01 prior shard outputs (cited; not re-derived)

- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 2 row 16, § 4 failure-mode protocol, § 5 sequencing (Group D — Channel adapters depends on shards 4, 5, 6, 8, 10, 14).
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` EC-7 (8-channel onboarding + 5-channel de-scope #1; lines 94-104), EC-8 (7-day cross-channel coherence; lines 107-116), § 5 row "EC-7" DEGRADE-ACCEPTABLE disposition.
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/03-kailash-py-mvp-readiness.md` § 3 row 13 (B grade, 3 of 9 present), § 2.2 (#687 + #767 + #737 + #673 closures), § 5 verification protocol.
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md` § 4 `TrustStoreAdapter` interface (cross-channel session-equivalence state surface).
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/06-envoy-ledger-implementation.md` § 4 `EnvoyLedger.append` contract, § 5.1 row "Channel adapters" (entry types).
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md` § 5 InboundRouter reference (BC is the inbound destination).
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/10-grant-moment-implementation.md` § 3.2 item 5 `ChannelHandoff.dispatch`, § 4 `GrantMomentOrchestrator` interface, § 6.1 `test_grant_moment_render_all_channels.py`.
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/14-connection-vault-implementation.md` § 4 `ConnectionVault` interface, § 5.1 channel-adapter consumer.
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` (citation discipline; no re-derivation; freshness gate).

### Phase 00 verified citations

- `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` item 24 lines 743–778 (B grade — 3 of 9 channels present).
- `workspaces/phase-00-alignment/01-analysis/03-primitive-reconciliation.md` row 23 (Envoy-new-code commitment for 6 messaging adapters).

### Verified upstream provider (read-only references)

- `~/repos/loom/kailash-py/src/kailash/channels/api_channel.py` (APIChannel — verified present).
- `~/repos/loom/kailash-py/src/kailash/channels/cli_channel.py` (CLIChannel — verified present).
- `~/repos/loom/kailash-py/src/kailash/channels/mcp_channel.py` (MCPChannel — Phase 02 surface).
- `~/repos/loom/kailash-py/src/kailash/channels/base.py` (Channel ABC).
- `~/repos/loom/kailash-py/src/kailash/channels/event_router.py` (event router).
- `~/repos/loom/kailash-py/src/kailash/channels/session.py` (per-channel session — NOT cross-channel).
- `~/repos/loom/kailash-py/packages/kailash-nexus/src/nexus/transports/webhook.py` lines 32 (TwilioSigner export), 40 (`class WebhookSigner(Protocol)`), 125 (`class TwilioSigner` reference), 301 (`class WebhookTransport(Transport)`), 335/459/533 (signer plug points).
- `~/repos/loom/kailash-py/packages/kailash-nexus/src/nexus/core.py` line 705 (`def register_websocket(...)`), line 710 (`allowed_origins: Optional[List[str]] = None`), line 765 (validation error path), lines 2365–2425 (`_validate_cors_origins`), lines 2440–2448 (CORS+credentials warning).

### Closed upstream issues verified

- terrene-foundation/kailash-py#687 (nexus `WebhookTransport` pluggable signer for Twilio) — closed; verified `WebhookSigner` Protocol at `webhook.py:40` + `TwilioSigner` reference at `webhook.py:125`.
- terrene-foundation/kailash-py#767 (nexus `durability_middleware` drains StreamingResponse body) — closed; effect: Web channel SSE / streaming integrity.
- terrene-foundation/kailash-py#737 (Nexus WorkflowServer lifespan disables consumer @on_event) — closed; effect: adapter lifecycle Ledger emits.
- terrene-foundation/kailash-py#673 (nexus `Origin`/`Host` allowlist on register_websocket) — closed; verified `allowed_origins=` parameter at `core.py:705-710`.

### Applicable rules

- `.claude/rules/zero-tolerance.md` Rule 4 (no SDK workarounds — channel adapters compose Nexus + kailash.channels, never re-implement webhook receive or WebSocket upgrade), Rule 6 (Implement Fully — all 4 spec decisions render across all 8 channels).
- `.claude/rules/orphan-detection.md` Rule 1 (production call site within 5 commits — `envoy.runtime.session.SessionRouter.bootstrap_channels()` per § 4), Rule 2 (Tier 2 wiring per facade), Rule 6 (`__all__` discipline per § 4 init), Rule 7 (consumer-tree sweep — none in Phase 01 outside `envoy.runtime`).
- `.claude/rules/facade-manager-detection.md` Rule 1 (Tier 2 wiring tests per § 6.1), Rule 2 (test naming convention `test_<channel>_adapter_lifecycle.py`), Rule 3 (explicit constructor deps; no global lookup).
- `.claude/rules/event-payload-classification.md` Rule 1 (single-point filter at emitter — `format_record_id_for_event(target_principal_id)` for every Ledger emit), Rule 2 (cross-SDK 8-hex SHA-256 prefix), Rule 4 (end-to-end Tier 2 redaction test).
- `.claude/rules/tenant-isolation.md` Rule 5 (Ledger writes carry `tenant_id` + `channel_id`, both indexed).
- `.claude/rules/security.md` § "Network Transport Hardening" (HTTP MCP transport Origin/Host allowlist; WebSocket equivalent via #673), § "Credential Comparison" (constant-time signature verify; no raw `==`), § "No Hardcoded Secrets" (credentials route through Connection Vault, never env-var ad-hoc).
- `.claude/rules/specs-authority.md` Rule 4 (read specs before acting; this shard reads `specs/channel-adapters.md` + `specs/a2a-messaging.md` + cross-spec via shards 4, 5, 6, 8, 10, 14), Rule 5b (no spec edits at this shard).
- `.claude/rules/testing.md` § 3-Tier Testing § Tier 2 + Tier 3 (real channels in test mode for ≥3 of 8; cassette-replay for the rest), § Test-Skip Triage (ACCEPTABLE skip pattern for missing-credentials test), § Env-Var Test Isolation (locked tests for token env vars), § "MUST: Verify NEW modules have NEW tests" (per-channel-module test-file presence sweep).
- `.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget (7 invariants tracked across 8 adapters — pattern-matched on shared ABC; ≤6 cross-primitive references; within budget because boilerplate scaling per § 2 Rule 2 "differentiated sizing" — 6 social adapters are pattern-instances of one shape, not 6 independent shards).

### Forward references (next shards / future phases)

- shard 11 — Daily Digest renders outbound via each adapter's `send_digest`.
- shard 19 — pipx distribution dependency tree (transitively pulls vendor SDK clients: `python-telegram-bot`, `slack_sdk`, `discord.py`, `whatsapp-cloud-api` or direct `requests`-based; `signal-cli` is system dep, NOT pip; BlueBubbles requires no pip dep — REST API only).
- Phase 02 — A2A messaging cross-principal (per `specs/a2a-messaging.md` line 13); MCP channel; Signal Path A; iMessage native Continuity; voice channel transcription.
- Phase 03 — multi-principal channel adapter principal-binding (extend per-adapter `principal_genesis_id` verification to cross-principal A2A).
- Phase 04 — 17-channel matrix per `specs/channel-adapters.md` § Phase 04 surfaces (lines 175-177).
