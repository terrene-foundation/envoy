# Flow 05 — Channel onboarding (adding a 7th channel mid-week)

**Document role:** Phase 01 user flow #5 of 8 (shard 21 of /analyze). Describes the user-visible journey of adding a new messaging channel to an already-running Envoy mid-week. The first channel was wired during Flow 02-or-shortly-after (Telegram, say, on Day 1). By Day 4 the user wants to add Slack so they can receive Grant Moments at work. Cross-channel coherence — a grant approved on Telegram is honoured by an action initiated from Slack 3 days later — is delegated to the Trust store (shard 5) + Ledger (shard 6) per shard 16 § 3.2 item 16.

**Date:** 2026-05-03 (shard 21 of /analyze; wave F user flows).
**Owning primitive shards:** 16 (channel adapters: per-adapter `startup`, `WebhookSigner`, `render_grant_moment`, `send_digest`), 14 (Connection Vault: bot token / API key / signing secret resolved at adapter `startup`), 5 (Trust store: cross-channel session continuity, primary-channel binding, `digest_schedule`), 6 (Envoy Ledger: `channel_connected` / `channel_disconnected` lifecycle entries), 8 (Boundary Conversation: NOT re-run when adding a channel; envelope already authored).
**Exit criterion served:** **EC-7** (single user onboards via any of 8 channels) — this flow is the per-channel onboarding ritual replicated 8× in the Tier 3 acceptance test. Also gates **EC-8** (week across channels — cross-channel coherence test).
**Communication discipline:** Plain language per `rules/communication.md`.

**Phase-01 CLI-surface note (added 2026-06-07 — `/redteam` F1 disposition):** `envoy channel add/retry/remove/status` is NOT a Phase-01 CLI subcommand. In Phase 01 the channel adapters (CLI, Web, Telegram, Slack, Discord — the 5-channel set) are library-wired (`envoy/channels/`), not managed through an `envoy channel` CLI group; the `envoy channel` management surface lands in Phase 02 alongside the long-running gateway. This storyboard describes the intended channel-management UX.

**Phase 01 de-scope #1 disposition (per shard 16 § 3.7 + `02-mvp-objectives.md` § 5):** if EC-7 fails on the full 6-messaging cohort, de-scope #1 is to reduce 6 messaging channels to 3. The 3 retained are typically Telegram + Slack + CLI (the easiest webhook + the easiest workplace + the no-creds default); the 3 dropped are typically WhatsApp (paid-tier complexity) + iMessage (BlueBubbles bridge complexity) + Signal (Path B legal-gate complexity). This flow assumes the full 6 are available; degraded behaviour is identical structurally.

---

## 1. Persona & context

**Primary persona:** A returning user who completed Flow 02 (Boundary Conversation) on Day 1 and wired Telegram during the immediate post-conversation onboarding (the "channels to enable" prompt that surfaces at Flow 02 S10). They have been operating with Envoy for 4 days. Now they realise they want Envoy to reach them at work — they want to add Slack as a second channel.

**Device + channel:** the user invokes `envoy channel add slack` from the CLI, OR they tap "add a channel" in the Web UI, OR they ask Envoy via Telegram "add Slack as a channel."

**Trigger:** explicit user command. Adding a channel is NEVER automatic — per `specs/connection-vault.md` § "Per-entry schema" + shard 16 § 3.2 item 15, every adapter's startup REQUIRES a credential to be present in the Connection Vault, and the Vault write is always user-driven.

---

## 2. Trigger

The user runs:

```
$ envoy channel add slack
```

Or equivalent from any active channel. Internally:

1. CLI checks the user's posture and active envelope — adding a channel is NOT a Grant-Moment-protected action in Phase 01 (the user already authored their envelope; adding a notification surface is a configuration change).
2. The CLI starts a guided onboarding ritual that wraps three sub-steps: (a) bot creation (out-of-band), (b) credential capture (Connection Vault write), (c) adapter startup (`Adapter.startup(config)`).
3. The bot is registered with the Slack API (out-of-band by the user); the user pastes the bot token + signing secret; the adapter starts up and emits a `channel_connected` Ledger entry.
4. Cross-channel session-continuity is automatic — the Trust Store's `SessionRecord` is updated with `channels_active = ["telegram", "slack"]` per shard 16 § 3.3.

---

## 3. Happy path (plain language)

### Step 1 — Initial prompt

```
$ envoy channel add slack

I'll help you add Slack as a channel.

Before we start, you'll need to create a bot in your Slack workspace.
This takes about 3-5 minutes; I'll walk you through it.

If you'd like, I can open Slack's bot creation page in your browser:

   [O] Open page in browser
   [I] I already have a bot — I'll paste the credentials
   [Q] Quit, do this later
```

The user picks. Phase 01 ships the OAuth-installed-bot path only (the simplest: user creates a bot in their Slack workspace via Slack's admin UI). Per shard 16 § 3.2 item 7, full Slack OAuth flow (where Envoy itself is an OAuth app the user installs) is Phase 02 — it requires Foundation-side OAuth registration that doesn't exist in Phase 01.

### Step 2 — Bot creation (≈3–5 min, out-of-band on the user's side)

If `[O]`, Envoy opens `https://api.slack.com/apps?new_app=1` in the user's browser and walks them through the page:

```
   I've opened Slack's "Create New App" page in your browser.

   1. Click "From scratch"
   2. Name it whatever you like (e.g., "Envoy")
   3. Pick the workspace you want this bot to live in
   4. After creation, click "OAuth & Permissions" in the left menu
   5. Add these bot scopes:
        chat:write, chat:write.public, im:history, im:write,
        users:read, files:write
   6. Click "Install to Workspace" and authorize
   7. Copy the "Bot User OAuth Token" — it starts with "xoxb-"
   8. Click "Basic Information" in the left menu
   9. Copy the "Signing Secret" — a long hex string

   When you have both, come back here and press Enter.
```

The user follows the steps in their browser. When ready, they press Enter in the CLI.

### Step 3 — Credential capture (≈30s)

```
   Paste the bot token (starts with "xoxb-"):
```

The user pastes. The CLI uses `prompt_toolkit`'s secure-text-field surface so the token doesn't echo. Per `specs/connection-vault.md` § "Clipboard hygiene" + shard 14 § 3.1 item 5, the clipboard is auto-cleared 30 seconds after capture.

```
   Paste the signing secret:
```

Same flow. The CLI now has both credentials in memory.

### Step 4 — Connection Vault write (≈100ms)

Per shard 14 § 3.1 + shard 16 § 3.2 item 15 (`CredentialResolver`), the CLI calls:

```
ConnectionVault.set(
    entry_id = uuid7(),
    principal_genesis_id = current_principal,
    credential_type = "BOT_TOKEN",
    service_identifier = "slack.bot_token",
    entry_envelope_scope = current_envelope_id,
    ciphertext = keyring_seal(bot_token),
    created_at = now(),
    expires_at = None,
    rotation_policy = "manual",
)
ConnectionVault.set(
    ...
    service_identifier = "slack.signing_secret",
    ciphertext = keyring_seal(signing_secret),
    ...
)
```

The credentials are now in the OS keychain (macOS Keychain / Windows Credential Locker / Linux Secret Service per shard 14 § 2.2). Envoy NEVER stores them in `~/.envoy/.env` (per `rules/security.md` § "No Hardcoded Secrets" + shard 14 § 3.1 item 9 — the Vault is the source of truth post-first-run).

### Step 5 — Adapter startup (≈1–3s)

```
   Starting up Slack adapter…
```

Per shard 16 § 3.2 item 7 (`SlackChannelAdapter`), the adapter:

1. Calls `CredentialResolver.resolve(channel_id="slack")` — pulls bot token + signing secret from Connection Vault.
2. Validates the `entry_envelope_scope` is included in the active envelope (per `specs/connection-vault.md` per-entry schema).
3. Initializes the webhook receive path via `nexus.transports.webhook.WebhookTransport` with a `SlackWebhookSigner` (`X-Slack-Signature` HMAC-SHA256 verifier).
4. Registers the bot's POST callback URL with Slack via Slack's API (one-time bot self-registration).
5. Sends a "Hello — Envoy is online" message to a default channel (`#envoy-test` or DM to the installing user).
6. On success, writes a `channel_connected` Ledger entry per shard 6 § 5.1.

The CLI confirms:

```
   Slack is connected.
   Test message sent to #envoy-test (Telegram message ID 12345).

   You now have 2 active channels:
     Telegram (primary, added Mon)
     Slack    (added today)

   Want to set Slack as your primary channel for high-stakes
   questions instead of Telegram?

      [Y] Yes, switch primary to Slack
      [N] No, keep Telegram as primary
```

Per shard 16 § 3.2 item 13 + `specs/channel-adapters.md` § Primary-channel binding, the user's primary channel is the only place where high-stakes Grant Moments render. Phase 01 lets the user explicitly designate; the default keeps the existing primary.

### Step 6 — Cross-channel session update (≈50ms)

Per shard 16 § 3.3, the Trust Store's `SessionRecord(principal_id, session_id, channels_active=...)` is updated:

```
SessionRecord.channels_active = ["telegram", "slack"]
SessionRecord.primary_channel = "telegram"  (or "slack" if user switched)
```

This is the **structural state** that makes EC-8 cross-channel coherence work. A Grant Moment approved on Telegram on Day 1 produces a `DelegationRecord` keyed by `session_id`, NOT by channel. When an action initiates from Slack on Day 6, the `InboundRouter` (shard 16 § 3.2 item 12) queries the Trust Store for the active delegation by `(principal_id, action_signature, time_window=7d)` and finds the Day-1 delegation regardless of origin channel.

### Step 7 — Day-1 grant honoured by Slack action (illustrative, not part of onboarding)

Three days later, the user is on Slack and asks Envoy to handle a task. Envoy needs a delegation that was approved on Telegram four days ago. The InboundRouter queries the Trust Store; the delegation is found; the action proceeds. The user sees:

```
   Done. (I used the rule you authored on Monday — Telegram —
   to do this. Both channels see all your rules.)
```

Per shard 16 § 3.3, this is the EC-8 acceptance gate's "Grant approved on Telegram is honoured by an action initiated from Slack 3 days later" structural test.

---

## 4. Edge cases (≥3 required)

### EC-A — User pastes the wrong token

Scenario: User pastes their Slack signing secret in the bot token field by mistake.

Plain-language UX:

```
   Hmm, that doesn't look like a Slack bot token. Bot tokens
   start with "xoxb-". The secret you pasted starts with what
   looks like a hex string — that's probably your signing secret.

   Want to:
     [1] Try the bot token again
     [2] Tell me they're swapped — I'll re-prompt for both
```

Recovery: per shard 14 § 3.1 + spec error `AuthenticationError`, the adapter's `startup(config)` validates token format before storing. Re-prompt without writing to the Vault.

### EC-B — Adapter `startup` fails after credential write

Scenario: User pasted both correct credentials, the Vault write succeeded, but the Slack API rejects the bot self-registration call (e.g., Slack workspace admin disabled bot installation, or the bot scopes are insufficient).

Plain-language UX:

```
   I saved your credentials, but Slack rejected my self-registration:

      "The bot is missing the chat:write.public scope."

   Two options:
     [1] Go back to your Slack admin page, add the missing scope,
         and tap "retry" (`envoy channel retry slack`)
     [2] Remove this channel and try again later
         (`envoy channel remove slack`)
```

Recovery: per shard 16 § 3.2 item 1 (`StartupTimeoutError`), the adapter's `startup` fails CLOSED with a typed error. The credentials remain in the Vault (so the user doesn't have to re-paste) but the adapter is NOT marked as connected. No `channel_connected` Ledger entry is written; instead a `system_error` entry is written naming the startup failure. The user can fix and retry.

### EC-C — Connection Vault unreachable mid-startup

Scenario: User's macOS keychain is locked because they just rebooted and haven't entered their login password yet.

Plain-language UX:

```
   I can't reach your computer's password keychain right now.
   On macOS, this usually means the keychain is locked — please
   unlock it (you may need to enter your login password) and
   then run:

      envoy channel retry slack
```

Recovery: per shard 14 § 3.1 + spec error `KeychainUnavailableError`, the adapter's `startup` raises typed and the user re-tries. No partial state is left.

### EC-D — Mid-week onboarding doesn't lose Day-1 grant (the load-bearing edge case)

Scenario: User authored a $80/month spending limit on Day 1 over Telegram. They approve a $30 payment to Sam on Day 1 (Telegram). On Day 4 they add Slack. On Day 6 they're at work, they ask Envoy via Slack to send another $30 to Sam. Per `02-mvp-objectives.md` EC-8 acceptance line 116: "cascade revocation of a Day-1 grant correctly revokes a Day-6 child grant initiated from a different channel" — the precondition is that the Day-6 Slack-initiated action MUST find the Day-1 Telegram-approved grant in the first place.

Plain-language UX (Day 6, Slack):

User: "Send another $30 to Sam"

Envoy:

```
   Done — sent $30 to Sam. (I used the rule you authored on
   Monday — Telegram — to do this. Both channels see all your rules.)

   You're at $115 of $90 this month.
```

Behind the scenes: the InboundRouter queries the Trust Store for an active delegation matching `(principal_id, action_signature, time_window=7d)`. The Day-1 DelegationRecord is keyed by `session_id` (not by channel) per shard 16 § 3.3. The query finds the Day-1 delegation; the action proceeds. NO new Grant Moment fires (within the original delegation's scope).

If the user had NOT authored a recurring rule on Day 1 (only `approve_once`), then a fresh Grant Moment WOULD fire on Day 6 because `approve_once` doesn't extend to subsequent actions. That's correct behaviour — the cross-channel-coherence test isn't "every action auto-approves," it's "the same set of authored rules applies regardless of channel."

### EC-E — Adding the 8th channel — WhatsApp paid-tier credentials

Scenario: User wants to add WhatsApp. Per shard 16 § 3.2 item 9, WhatsApp is a "caveat" channel — paid-tier credentials, Foundation gateway in Phase 02, user-own credentials in Phase 01.

Plain-language UX:

```
$ envoy channel add whatsapp

   WhatsApp is a paid-tier channel for Phase 01. You'll need:

     1. A WhatsApp Business API account ($)
     2. A registered phone number on Meta's Cloud API
     3. Your "App Secret" and "Phone Number ID" from the
        WhatsApp Business Manager

   The full setup takes about 30 minutes the first time
   (Meta requires phone-number verification + business
   verification). After Phase 01 you'll be able to use a
   Foundation-managed gateway instead — that's coming in Phase 02.

   Want to:
     [1] Continue with my own credentials
     [2] Skip — I'll wait for Phase 02
     [3] Try a different channel instead
```

Recovery: user picks. Phase 01 only supports user-own credentials; the Foundation gateway path is Phase 02 per shard 16 § 3.2 item 9.

### EC-F — Adding a channel that is already added

Scenario: User runs `envoy channel add slack` but Slack is already wired.

Plain-language UX:

```
   Slack is already connected to your Envoy (added Mon, currently
   active). Did you mean to:

      [1] See the Slack channel's status (`envoy channel status slack`)
      [2] Re-pair (forget the old credentials and add new ones —
          useful if you regenerated the bot token)
      [3] Remove and re-add fresh
      [4] Cancel
```

Recovery: per shard 14 § 3.1 + spec error `EntryNotFoundError` inverse case (entry exists), the CLI does NOT silently overwrite. User-driven choice required.

### EC-G — Channel onboarding initiated FROM another channel

Scenario: User is on Telegram and types "@envoy add slack as a channel."

Plain-language UX (on Telegram):

```
   Adding a new channel needs a few private steps — pasting
   tokens, choosing scopes — that I won't do over Telegram
   (Telegram messages are visible to Telegram, and these
   tokens are sensitive).

   To add Slack:
     1. Open your terminal on the laptop where Envoy lives
     2. Run: `envoy channel add slack`
     3. I'll walk you through the rest there.

   Or, if you'd like, I can open the Envoy desktop app right
   now (only if you have it running on a screen you're at).
```

Recovery: per `rules/security.md` § "No Hardcoded Secrets" + shard 16 § 2.2 #687 (webhook signer hygiene), credential capture MUST happen in a secure-text-field surface. Telegram chat is not such a surface. The user is redirected to CLI / desktop-app onboarding.

---

## 5. Underlying primitives

| Step                                | Primitive (shard)                                                                    | What runs                                                                                                          |
| ----------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| Initial prompt + bot creation guide | shard 16 § 3.2 item 4 (CLI adapter)                                                  | Click/argparse-driven prompt; opens browser at Slack's app creation page                                           |
| Credential capture                  | shard 14 § 3.1 + `prompt_toolkit`                                                    | Secure-text-field input; clipboard auto-clear 30s per `specs/connection-vault.md` § Clipboard hygiene              |
| Connection Vault write              | shard 14 § 3.1 + § 4 (`ConnectionVault.set`)                                         | OS keychain seal via `keyring.set_password(service, username, password)`; per-entry schema serialization           |
| Adapter `startup`                   | shard 16 § 3.2 item 7 (`SlackChannelAdapter`) + § 3.2 item 15 (`CredentialResolver`) | Resolves Vault entry → secret; validates `entry_envelope_scope`; initializes WebhookTransport + SlackWebhookSigner |
| Adapter self-registration           | shard 16 § 2.2 #687 (`WebhookTransport`)                                             | Bot self-registers via Slack API; failure surfaces as `StartupTimeoutError`                                        |
| Test message send                   | shard 16 § 3.2 item 1 (`send_message`)                                               | Sends "Hello — Envoy is online" to `#envoy-test` or DM                                                             |
| `channel_connected` Ledger emit     | shard 6 § 5.1                                                                        | `EnvoyLedger.append("channel_connected", {channel_id, principal_genesis_id_redacted, signed_by})`                  |
| Cross-channel session update        | shard 16 § 3.3 + shard 5 § 4                                                         | `TrustStoreAdapter.update_session(principal_id, channels_active=[...])`                                            |
| Primary-channel determination       | shard 5 § 4 + shard 16 § 3.2 item 13                                                 | User-driven choice; written to Trust Store as `SessionRecord.primary_channel`                                      |

---

## 6. Acceptance criteria served

- **EC-7 (DEGRADE-ACCEPTABLE per `02-mvp-objectives.md` § 5):** This flow is the per-channel onboarding ritual that the EC-7 acceptance gate replicates 8× (CLI + Web + 6 messaging). Each channel's onboarding follows the same shape: bot creation (channel-specific) → credential capture → Connection Vault write → adapter startup → `channel_connected` Ledger entry. Per-channel deviation in completion time / message count MUST stay within 2× of the CLI baseline.
- **EC-8 cross-channel coherence (BLOCKING):** EC-D above is the load-bearing illustrative case. Cross-channel coherence is structurally satisfied by Trust-Store-driven session continuity (shard 16 § 3.3); the channel adapter is stateless from the coherence perspective. Tier 3 test `tests/e2e/test_session_continuity_8_channels.py` per shard 16 § 6.

---

## 7. Failure modes & recovery

| Failure                          | What the user sees                                                                                                                                       | Recovery path                                                                                       |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Wrong credential format (EC-A)   | "Hmm, that doesn't look like a Slack bot token. Bot tokens start with 'xoxb-'. Want to try again?"                                                       | Adapter validates format before Vault write; re-prompt without writing                              |
| Adapter startup fails (EC-B)     | "I saved your credentials, but Slack rejected my self-registration: '...'. Run `envoy channel retry slack` after fixing."                                | `StartupTimeoutError` Ledger row; credentials remain in Vault for retry                             |
| Keychain locked (EC-C)           | "I can't reach your computer's password keychain right now. Please unlock it and run `envoy channel retry slack`."                                       | `KeychainUnavailableError`; no partial state                                                        |
| Channel already added (EC-F)     | "Slack is already connected. Want to see status, re-pair, remove, or cancel?"                                                                            | User-driven choice; no silent overwrite per shard 14 § 3.1                                          |
| Onboarding from messaging (EC-G) | "Adding a channel needs private steps I won't do over Telegram. Open your terminal and run `envoy channel add slack`."                                   | Redirect to secure-text-field surface; per `rules/security.md` no creds over messaging              |
| Bot scope insufficient           | "The bot is missing the `chat:write.public` scope."                                                                                                      | Surface Slack's error verbatim in plain language; user re-configures and retries                    |
| WhatsApp paid-tier (EC-E)        | "WhatsApp needs paid Business API credentials. Phase 02 will use a Foundation gateway. Continue with own credentials, skip, or try a different channel?" | User-driven choice; Foundation gateway is Phase 02                                                  |
| `EnvelopeScopeMismatchError`     | "The Slack credentials you saved are scoped to a different envelope than the one currently active. Re-add and I'll bind them to today's envelope."       | Per `specs/connection-vault.md` per-entry schema; rare in P01 because the active envelope is single |

All recovery paths are user-driven — Phase 01 NEVER auto-retries credential operations (per `rules/zero-tolerance.md` Rule 3).

---

## 8. Cross-references

- `workspaces/phase-01-mvp/01-analysis/16-channel-adapters-implementation.md` § 3 (Envoy-new-code surface, per-adapter), § 3.3 (Trust-Store-driven cross-channel coherence)
- `workspaces/phase-01-mvp/01-analysis/14-connection-vault-implementation.md` § 3 (Connection Vault adapter), § 4 (`ConnectionVault.set/.get`)
- `workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md` § 4 (`SessionRecord` cross-channel session continuity, primary-channel binding)
- `workspaces/phase-01-mvp/01-analysis/06-envoy-ledger-implementation.md` § 5.1 row "Channel adapters" (`channel_connected` / `channel_disconnected` lifecycle entries)
- `workspaces/phase-01-mvp/03-user-flows/02-boundary-conversation-flow.md` (initial channel wired immediately after Flow 02)
- `workspaces/phase-01-mvp/03-user-flows/03-grant-moment-flow.md` (cross-channel cascade revoke — sub-flow 3D — relies on this flow's Trust-Store session updates)
- `workspaces/phase-01-mvp/03-user-flows/04-daily-digest-flow.md` (digest delivers to channels wired here)
- `specs/channel-adapters.md` § Phase 01 surfaces (8-channel table), § Cross-channel session continuity, § Primary-channel binding (H-03), § Side-channel hygiene (T-070), § Network security (T-080), § Error taxonomy
- `specs/connection-vault.md` § Per-entry schema, § Clipboard hygiene, § Error taxonomy
- `rules/security.md` § "No Hardcoded Secrets" + § "Network Transport Hardening"
- `rules/communication.md` (plain-language framing throughout)
