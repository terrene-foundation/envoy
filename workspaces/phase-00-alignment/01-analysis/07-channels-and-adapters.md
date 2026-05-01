# 07 — Channels and Adapters

**Document status:** draft v1 — ready for `/redteam`
**Scope:** The channel-adapter contract that Envoy ritual UX renders through (doc 01). The 6 Phase 01 messaging channels (iMessage-via-BlueBubbles, Telegram, Slack, Discord, WhatsApp, Signal) plus CLI + Web = 8 surfaces. Per-channel compliance + legal posture. Cross-channel session continuity. 17 additional Phase 04 channels sketched.
**Sources:** doc 00 v3 (Phase 01 expanded to 6 channels + CLI + Web = 8 surfaces; 23+ messaging by Phase 04), doc 01 v1 (ritual rendering per channel), doc 02 v3 (envelope.communication.channel_allowlist), doc 09 v3 (T-018 visible secret; T-070 side channels; T-080 network MITM).

---

## 1. Purpose

Envoy is channel-native: the user operates in their existing messaging channels, not in a separate app. Phase 01 ships 6 messaging channels + CLI + Web. Phase 04 expands to 23+.

### In scope

- Adapter contract (common interface all adapters implement).
- Per-channel specifications (the 8 Phase 01 surfaces).
- Cross-channel session continuity — same envelope / ledger / posture across channels.
- Per-channel compliance — legal posture, terms of service, third-party client constraints.
- Message routing + signature propagation.
- Per-channel visible-secret rendering.
- Rate limits + backoff.
- Phase 04 channel sketch.

### Out of scope

- Ritual state machines + prompts (doc 01).
- Envelope enforcement at tool-call time (doc 02, doc 05).
- Ledger entry writes (doc 04).
- Distribution / installer (doc 06).

---

## 2. Adapter contract

Every channel adapter implements the abstract interface:

```python
class ChannelAdapter(ABC):
    @abstractmethod
    def channel_id(self) -> str: ...
    @abstractmethod
    def startup(self, config: ChannelConfig, credentials: ChannelCredentials) -> None: ...
    @abstractmethod
    def shutdown(self) -> None: ...

    # --- Inbound (user → Envoy) ---
    @abstractmethod
    def receive_message(self, handler: Callable[[InboundMessage], None]) -> None: ...

    # --- Outbound (Envoy → user) ---
    @abstractmethod
    def send_message(self, msg: OutboundMessage) -> DeliveryReceipt: ...
    @abstractmethod
    def send_grant_moment(self, gm: GrantMomentRender) -> DeliveryReceipt: ...
    @abstractmethod
    def send_digest(self, digest: DigestContent) -> DeliveryReceipt: ...

    # --- Capabilities reporting ---
    @abstractmethod
    def capabilities(self) -> ChannelCapabilities:
        """{supports_buttons, supports_attachments, supports_voice, max_message_length, supports_markdown, ...}"""

    # --- Rate limits ---
    @abstractmethod
    def rate_limit_status(self) -> RateLimitStatus: ...
```

`ChannelCapabilities` dictates how rituals render:

- **supports_buttons** — Grant Moment dialogs render inline keyboards vs quick-reply numbers.
- **supports_attachments** — Daily Digest can include file attachments.
- **supports_markdown** — Monthly Trust Report rendered as markdown vs plain text.
- **supports_voice** — channel supports voice notes (WhatsApp, iMessage).
- **supports_reactions** — iMessage reactions; Slack emoji reactions; channel can encode simple yes/no via reaction.

---

## 3. Message envelope

Every inbound / outbound message carries:

```json
{
  "channel_id": "telegram | slack | discord | whatsapp | signal | imessage-bluebubbles | cli | web",
  "session_id": "uuid-v7 — links to Envoy session",
  "principal_genesis_id": "sha256:...",
  "direction": "inbound | outbound",
  "content_trust_level": "user-authored | derived-external | system",
  "payload": {<channel-specific>},
  "visible_secret_rendered": true,
  "timestamp": "iso8601"
}
```

Every inbound message is content-hashed + entered in Ledger at the point of arrival (`content_trust_level: channel-message`). Every outbound message is Ledger-recorded BEFORE send (`content_trust_level: system` for Envoy-generated; `user-authored` echo for user-initiated drafts).

---

## 4. Cross-channel session continuity

A user starts a Grant Moment in Telegram, continues in Slack. Envoy's session state (SessionObservedState per doc 02 §15) is shared across channels for that principal.

### 4.1 Continuity semantics

```text
principal.active_channels: {telegram: active, slack: active, imessage: idle}
principal.current_session: session_id_X
principal.active_grant_moments: [gm_id_Y (rendered in: telegram + slack + imessage)]

When user approves in Slack:
  1. gm_id_Y marked resolved in session.
  2. Outbound "resolved" notification to other channels.
  3. Ledger entry records which channel hosted the approval.
```

### 4.2 Visible-secret propagation

The visible secret (doc 09 T-018) is rendered in EVERY channel where a Grant Moment is active. If one channel renders without the secret (e.g. Signal lacks image support), fallback is the phrase-only form.

### 4.3 Multi-principal routing

In Shared Household (Phase 03), each principal has their own channels. Cross-principal Grant Moments (§4.7 doc 01) route independently to each principal's designated channels.

---

## 5. Phase 01 channels — per-channel specification

### 5.1 CLI

- **Phase:** 01.
- **Credentials:** none.
- **Compliance:** none.
- **Capabilities:** text-only; Unicode box-drawing; ANSI colors; no buttons (quick-reply via numeric input).
- **Rate limits:** none (local process).
- **Visible secret:** rendered above every prompt via ANSI color + Unicode icon.
- **Notes:** onboarding + admin affordance per doc 00 v3. Not intended as daily-use surface; channel-native surfaces (below) carry daily flow.

### 5.2 Web (local HTTP)

- **Phase:** 01.
- **Credentials:** localhost-binding only; no external auth in Phase 01 (doc 06 installer configures).
- **Compliance:** none.
- **Capabilities:** full — buttons, modals, markdown, attachments (local).
- **Rate limits:** none (local).
- **Visible secret:** rendered as colored banner with user-chosen icon + phrase.
- **Notes:** same role as CLI — admin + onboarding.

### 5.3 Telegram

- **Phase:** 01.
- **Credentials:** Telegram bot token (user creates bot via @BotFather; enters token in Grant Moment).
- **API:** Telegram Bot API over HTTPS + webhook OR long-poll. Official and supported.
- **Compliance:** Telegram ToS permits bots; no legal friction.
- **Capabilities:** inline keyboards, markdown, attachments (photo, document, voice), reactions (Phase 04), webhook delivery.
- **Rate limits:** Telegram enforces ~30 messages/sec per bot globally; per-chat ~1/sec. Adapter implements exponential backoff.
- **Visible secret:** Telegram bot's avatar + name encode static part; inline message header carries dynamic phrase.
- **Phase 02 addition:** voice note transcription via local Whisper.

### 5.4 Slack

- **Phase:** 01.
- **Credentials:** Slack bot token + (optional) user token via OAuth. User installs Envoy-bot app into their Slack workspace.
- **API:** Slack Bot API (chat.postMessage, events API, socket mode). Block Kit for rich UI.
- **Compliance:** Slack App Directory permits bot apps; Envoy-bot to be listed by Foundation Phase 02+.
- **Capabilities:** block kit (buttons, selects, modals), attachments, threads, reactions.
- **Rate limits:** Slack tiered rate limits; Tier 2 (events) ~20 req/min per method.
- **Visible secret:** rendered in Slack message as block with custom emoji + phrase.

### 5.5 Discord

- **Phase:** 01.
- **Credentials:** Discord bot token.
- **API:** Discord Gateway (WebSocket) + REST API. Slash commands + message components.
- **Compliance:** Discord Developer Terms permit bots.
- **Capabilities:** buttons, selects, modals, embeds, slash commands, attachments, voice-channel audio (Phase 04).
- **Rate limits:** per-route rate limits returned in response headers.
- **Visible secret:** bot's custom-emoji + phrase in embed footer.

### 5.6 WhatsApp

- **Phase:** 01.
- **Credentials:** WhatsApp Business API access (Meta-approved business; not consumer WhatsApp Web reverse-engineered path — that path is BLOCKED in doc 09 T-080).
- **API:** WhatsApp Business Cloud API (Meta-hosted) OR self-hosted WhatsApp Business API (via BSP).
- **Compliance:** WhatsApp Business ToS; $0.01-$0.08 per conversation (depending on category). Foundation-operated gateway accepted OR user brings own WhatsApp Business account.
- **Capabilities:** quick-reply buttons, list messages, media (image, video, audio, doc, location), interactive messages.
- **Rate limits:** category-dependent; user-initiated messages (responding to user within 24h) have lower limits.
- **Visible secret:** image message with user's icon + phrase + color in visible-secret-template.
- **Phase 01 caveat:** some users may not have WhatsApp Business access; fallback path is Telegram + Signal.

### 5.7 Signal

- **Phase:** 01 (with legal-gate caveat per doc 00 v3 §4.3).
- **Credentials:** `signal-cli` registration OR Signal Group Link + webhook path.
- **API:** two viable paths:
  - **Path A** — `signal-cli` (community-maintained; uses Signal protocol as third-party client). Legal posture: Signal tolerance inconsistent historically. Risk: Signal bans user's number.
  - **Path B** — Signal Group Link + webhook (Signal's SUPPORTED API surface). User adds Envoy to a group; Envoy receives group messages; replies via group message. Less-rich UX but compliant.
- **Compliance:** Phase 01 legal-gate review (per doc 09 T-023 Signal row) required before shipping Path A. Default to Path B.
- **Capabilities:** text, markdown (limited), attachments, emoji reactions.
- **Rate limits:** per-group message limits.
- **Visible secret:** text-only phrase-header per message.

### 5.8 iMessage (via BlueBubbles)

- **Phase:** 01 (with Mac-requirement caveat).
- **Credentials:** BlueBubbles server running on a user-owned Mac with Apple ID. User runs BlueBubbles → Mac relays iMessages to Envoy.
- **API:** BlueBubbles WebSocket + REST.
- **Compliance:** Apple ToS question around relay; BlueBubbles is community-maintained; user-responsibility. Envoy-side: only connects to user's OWN BlueBubbles server — no Envoy-centralized iMessage relay.
- **Capabilities:** iMessage reactions, effects (Phase 04), images, taptic feedback (where supported).
- **Rate limits:** Apple-imposed; BlueBubbles relays.
- **Visible secret:** icon + phrase in iMessage text header.
- **Phase 01 caveat:** user MUST have a Mac running BlueBubbles server; not universal. If not, fallback channels.

---

## 6. Phase 04 channel sketch

17 additional messaging channels per doc 00 v3 §3.1:

- Matrix — via `matrix-bot-sdk` or Synapse Application Service.
- Feishu — Lark API.
- LINE — LINE Messaging API.
- Mattermost — Mattermost WebSocket API.
- WeChat — WeChat Work Bot API (business only).
- QQ — QQ Bot API (regional).
- Teams — Teams Bot Framework.
- Google Chat — Google Chat API.
- IRC — standard IRC bot.
- Nostr — Nostr protocol relay.
- Twitch — Twitch IRC bot (chat).
- Tlon — Urbit-adjacent messaging.
- Zalo — Zalo Official Account API.
- Nextcloud Talk — Nextcloud Talk webhook.
- Synology Chat — Synology Chat API.
- Apple Shortcuts — URL schemes + local action.
- Calendar — iCal subscription + bidirectional event creation.
- Browser extension — right-click → delegate to Envoy.
- IDE extensions — VS Code / JetBrains / Zed / Cursor.
- Voice — local Whisper → Envoy → local TTS.
- RCS / SMS — Twilio / MessageBird.

Per doc 00 §3.1 Phase 04 exit: "23+ messaging channels active, including 5 Envoy-native channels (Apple Shortcuts, Calendar, browser extension, IDE extensions, voice)."

---

## 7. Per-channel compliance matrix

| Channel              | Legal posture                    | Phase 01 ship?       | Phase 01 caveat                                    |
| -------------------- | -------------------------------- | -------------------- | -------------------------------------------------- |
| CLI                  | N/A                              | Yes                  | Local only                                         |
| Web                  | N/A                              | Yes                  | Local HTTP                                         |
| Telegram             | Official bot API                 | Yes                  | Clean                                              |
| Slack                | Official bot API                 | Yes                  | Clean                                              |
| Discord              | Official bot API                 | Yes                  | Clean                                              |
| WhatsApp             | Business API required            | Yes                  | User needs WhatsApp Business OR Foundation-gateway |
| Signal               | Path A fragile, Path B supported | Yes (Path B default) | Phase 01 legal-gate review                         |
| iMessage-BlueBubbles | Community relay, user-owned Mac  | Yes (optional)       | User needs Mac + BlueBubbles                       |

---

## 8. Rate limits + backoff

Adapter-level rate limits enforced per channel's upstream limits. Envoy-level adds:

- **Per-channel outbound rate** — configurable in envelope.communication.rate_limits (inherits from doc 02 §3.5).
- **Per-session outbound rate** — prevent one user from flooding a shared household channel.
- **Exponential backoff** — on upstream rate-limit 429 response, adapter backs off with jitter.
- **Degraded-mode** — if a channel has been rate-limit-exceeded for >N minutes, Envoy surfaces Grant Moment to either (a) wait, (b) switch to alternate channel, (c) cancel action.

---

## 9. Side-channel hygiene

Per doc 09 T-070:

- **Clipboard** — no Envoy content auto-copied to clipboard; explicit user action required.
- **Screen recording** — Envoy detects active screen recording in Flutter mobile clients; warns user before Grant Moment renders sensitive content.
- **Accessibility API** — Envoy uses accessibility correctly; sensitive content (credentials, Shamir shards, ledger entries) excluded from accessibility tree unless user opts in.

Per-channel specifics:

- Telegram: messages NOT end-to-end encrypted by default (secret chats only); Envoy warns user at connection time.
- Slack: all content seen by workspace admins (enterprise Slack); Envoy warns at connection time if workspace-admin-visibility detected.
- Discord: similar admin-visibility warning.
- WhatsApp: E2E encrypted.
- Signal: E2E encrypted.
- iMessage: E2E encrypted (via BlueBubbles relay — relay operator sees metadata).

---

## 10. Network-security integration (doc 09 T-080)

All channel-adapter traffic via TLS 1.3 minimum. Certificate pinning for Foundation-operated endpoints (none at Phase 01; Phase 02+ includes Foundation Health Heartbeat relay). Standard OS trust store for third-party channel providers.

---

## 11. Error + failure

| Error                             | When                                                             | Recovery                                                           |
| --------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------ |
| `ChannelCredentialInvalidError`   | Bot token expired / revoked                                      | User re-authenticates via Grant Moment                             |
| `ChannelRateLimitExceededError`   | Upstream rate limit hit                                          | Exponential backoff; surface Grant Moment for degraded-mode        |
| `ChannelUnreachableError`         | Network / service outage                                         | Retry with backoff; degraded-mode after N min                      |
| `ChannelMessageRejectedError`     | Upstream refused message (e.g. banned keyword, policy violation) | Ledger entry + user notification                                   |
| `ChannelComplianceViolationError` | Channel's ToS changed; Envoy adapter no longer compliant         | Disable channel; warn user; suggest alternate                      |
| `CrossChannelSessionRoutingError` | Session state inconsistency across channels                      | Sync state; if unrecoverable, terminate session + require re-start |

---

## 12. Cross-references

- **doc 00 v3** — Phase 01 6 channels + CLI + Web; Phase 04 23+ channels.
- **doc 01 v1** — ritual prompt rendering per channel.
- **doc 02 v3** — envelope.communication dimension — channel_allowlist, recipient_allowlist.
- **doc 03 v2** — cross-channel disablement confirmation for enterprise-mode.
- **doc 05 v1** — runtime invokes adapter.send_message + adapter.receive_message.
- **doc 09 v3** — T-018 visible secret; T-070 side channels; T-080 network MITM; T-023 Signal legal gate.

---

## 13. Open questions

1. WhatsApp Business gateway — Foundation-operated vs user-owned? Foundation-operated simplifies UX but introduces a Foundation-infrastructure dependency that doc 00 §4.1 item 15 seeks to minimize.
2. Signal Path A vs Path B — default to Path B for compliance. Reassess at Phase 04 when Signal API evolves.
3. Multi-device-per-channel — user logs into Slack from laptop + phone. Envoy sends message; arrives in both. Does user approve on which device count as authoritative? Resolution: any device's approval wins; other devices see "resolved elsewhere."
4. Channel-credential-rotation ritual — quarterly? On-demand? User-driven.
5. Cross-channel cross-principal conflicts — Alice approves in Slack; Bob (Shared Household) denies in Telegram. Dual-signed Grant Moment requires both; the FIRST response wins for single-principal actions.

---

**End of doc 07 v1.**
