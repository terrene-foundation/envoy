# Flow 04 — Daily Digest (morning ritual)

**Document role:** Phase 01 user flow #4 of 8 (shard 21 of /analyze). Describes the user-visible journey of the morning ritual — the scheduled per-day summary that fires at the user's chosen morning hour, renders across configured channels, and back-fills missed days. EC-3 is the acceptance gate: the digest fires for ≥7 consecutive days with content sourced from the Ledger.

**Date:** 2026-05-03 (shard 21 of /analyze; wave F user flows).
**Owning primitive shards:** 11 (Daily Digest service: scheduler, aggregator, renderer, fan-out, back-fill, pause, low-engagement, duress banner), 6 (Envoy Ledger: query source for the digest content), 13 (Model adapter: optional NL summary text), 16 (channel adapters: per-channel `send_digest`), 5 (Trust store: `digest_schedule`, primary-channel binding, pause-state, last-success state, shadow-segment duress read).
**Exit criterion served:** **EC-3 (BLOCKING)** directly — Daily Digest renders at scheduled time with real Ledger-sourced content for ≥7 consecutive days; skipped days back-fill in the next-day digest.
**Communication discipline:** Plain language per `rules/communication.md`.

**Important UX caveat — timezone disposition (per `journal/0003-GAP-budget-ceiling-timezone.md`):** Phase 01 ships **Option A (UTC fire)** for both budget reset (shard 12) AND digest schedule (shard 11). For a Singapore user (UTC+8) who configured "8 AM morning ritual," Phase 01 fires at 8 AM **UTC**, which is 4 PM **local time**. This is a known UX surprise. Shard 22's spec gap analysis recommends Option B (user-local IANA timezone) as Phase 02 remediation — but that requires a 37-sibling spec re-derivation sweep per `rules/specs-authority.md` MUST Rule 5b, deferred. § 4 (edge cases) below documents what the user sees and how to mitigate.

---

## 1. Persona & context

**Primary persona:** A returning user who has been operating with Envoy for at least one day. They have completed Flow 02 (Boundary Conversation), wired at least one channel (Flow 05), and have at least one day's worth of activity in the Ledger.

**Device + channel:** the digest delivers to the user's configured `digest_channel` (default: first-connected channel from Flow 05). For most users this is whatever messaging app they checked first in the morning during Flow 05 setup — typically Telegram, Slack, or email/Web.

**Trigger:** time-based, per-principal cron schedule. Per shard 11 § 3.2 item 2 (`DigestScheduler`), the schedule registers a `CronTrigger(hour=<user_hour>, timezone=<user_tz>)` on `apscheduler.AsyncIOScheduler`. Phase 01 timezone disposition is Option A (UTC).

---

## 2. Trigger

The `DailyDigestService.start()` call (per shard 11 § 3.2 item 1) registers a per-principal cron job at session boot. When the cron fires:

1. The scheduler invokes the digest pipeline coroutine for the principal.
2. The pipeline checks pause state (`PauseDisableState` per shard 11 § 3.2 item 7) and skips if paused.
3. `LedgerAggregator.aggregate(principal_id, window_start, window_end)` (item 3) queries `EnvoyLedger.query(filter, since, until)` for the previous-24h window.
4. `BackfillTracker` (item 6) checks per-channel last-success state; if `now - last_success > 24h + tolerance`, missed days are itemized.
5. `DuressBannerReader` (item 9) reads the local-only shadow segment for unread duress events.
6. `DigestRenderer` (item 4) builds the unified `DigestPayload` per `specs/daily-digest.md` § Schema.
7. `PerChannelFanout` (item 5) fans out to active channels in parallel via `asyncio.gather(..., return_exceptions=True)`.
8. Each channel adapter's `send_digest(principal_id, digest, timeout_seconds=10)` translates the unified payload into channel-native form (rich / compact / event-only).
9. Per successful send, a `ritual_completion` Ledger row is written; per failure, a `system_error` row.

---

## 3. Happy path (plain language)

### Step 1 — Schedule fires (≈1ms)

The user sees nothing yet. Internally, the scheduler invokes the digest coroutine.

### Step 2 — Aggregation (≈300–800ms against a 1k-entry Ledger)

The aggregator queries the Ledger for the previous-24h window:

- Actions: every `PhaseBRecord(outcome="success", ...)` — what Envoy DID for the user.
- Refusals: every `grant_moment(decision="deny")` — what Envoy did NOT do because the user said no.
- Spend: sum of `PhaseBRecord` outcomes that touched the financial dimension; current month-to-date vs ceiling.
- Pending grants: `grant_moment` rows with `decision="expired"` or active timeouts the user never resolved.
- Planned today: any scheduled tasks the user authored (e.g., "summarize my mail every morning").

### Step 3 — Render (≈200–400ms; optional 1–2s if NL summary is enabled)

The renderer builds the `DigestPayload` (11 fields exactly per `specs/daily-digest.md` § Schema). Optionally, it invokes `EnvoyModelRouter.for_primitive("daily_digest").chat_async([...])` (shard 13 § 5.2) to generate a 1–2 sentence natural-language summary. Per shard 13, a fast/cheap preset is the default for cost discipline (`ENVOY_DIGEST_MODEL` env override available).

### Step 4 — Per-channel delivery (≈1–10s, parallel)

The user sees the digest arrive on their configured digest channel. Format depends on channel:

**Telegram / Slack / Discord (rich form with inline buttons):**

```
   anchor + deep blue + "salt for soup"

   Good morning. Here's what happened yesterday.

   Did
     • Replied to Alice when she texted (8:14am)
     • Sent $30 to Sam (dinner; you approved)
     • Summarized 4 unread mails (8:32am)

   Didn't
     • Asked about $5,000 to "Cousin Elliot" — you said no
     • (1 question I asked you went unanswered for 5 minutes — see below)

   Spending this month
     $85 of $80 limit (you raised it to $90 on Tuesday)

   Today's plans
     • Summarize unread mail at 8am tomorrow

   Anything from yesterday I asked about?
     • The $5,000 to "Cousin Elliot" question — review or revoke

   [Reply OK]   [Reply with changes]   [Skip digest for a few days]
```

**SMS / WhatsApp (compact 10-line form):**

```
   Envoy 8 AM

   Did 3 things ($30 to Sam, replied Alice, mail summary)
   Said no to 1 ($5K to Cousin Elliot)
   Spent $85 of $90 this month
   1 question went unanswered — tap to review

   Reply OK  •  Reply changes  •  Skip
```

**CLI (`envoy digest today`):**

Same content as the rich form, rendered with terminal markdown.

**Email/Web (richest form with attachments):**

Same content plus optional attachments — e.g., a CSV of yesterday's actions. Localhost-bound web UI per shard 16 § 3.2 item 5.

### Step 5 — User reply (optional)

Per `specs/daily-digest.md` § Interaction (lines 21–25):

- Reply "OK" / no-reply: Envoy proceeds with today's planned actions.
- Reply "changes" / modify: the user types what they want changed. Envoy parses (Phase 01: structured-only — buttons; Phase 02: NL parsing per spec open question 4) and applies. Per shard 11 § 3.2 item 4, the parser uses the model adapter when present.
- Reply "skip digest": Envoy pauses the digest for `duration_days` (default 7 per shard 11 § 3.2 item 7); user runs `envoy digest resume` or waits for auto-resume.

### Step 6 — Ledger write (≈50ms per channel)

Each successful `adapter.send_digest()` returns a `SendReceipt`. The `BackfillTracker` writes `TrustStoreAdapter.set_kv("digest:last_success", principal_id=p, channel_id=c, value={delivered_at, digest_id})`. A `ritual_completion` Ledger row is written per channel. Per `rules/event-payload-classification.md` Rule 1, classified `record_id` and `principal_genesis_id` values are routed through `format_record_id_for_event` BEFORE emission (per shard 11 § 3.2 item 3 — single-point filter at the aggregator).

### Step 7 — Back-fill scenarios (next-day, when applicable)

If the user was offline yesterday, the back-fill tracker reads `last_success` per channel; if `now - last_success > 24h`, the next-day digest itemizes the missed day:

```
   Good morning. (You were offline yesterday — here's the catch-up.)

   Did over the last 2 days
     • [Mon] Replied to Alice (8:14am)
     • [Mon] Sent $30 to Sam (dinner; you approved)
     • [Tue] Summarized 4 unread mails

   Didn't
     • [Tue] Asked about $5,000 to "Cousin Elliot" — you said no

   ...
```

Per shard 11 § 3.2 item 6, the back-fill window is capped at 7 days to prevent unbounded growth on chronic-offline principals.

---

## 4. Edge cases (≥3 required)

### EC-A — Timezone surprise (Singapore user sees 4pm "morning" digest)

Scenario: User in Singapore (UTC+8) configured `digest_hour = 8` during Flow 05 ("I want my morning ritual at 8 AM"). Phase 01 ships Option A (UTC fire per `journal/0003`). The cron fires at 08:00 UTC = 16:00 SGT.

Plain-language UX (the digest itself doesn't carry an apology — but `envoy digest schedule --help` exposes the timezone caveat):

```
$ envoy digest schedule --hour 8

I'll send your digest at 08:00 UTC — that's about 16:00 (4 PM)
where you are. Phase 01 fires the digest on UTC for everyone;
matching your local timezone is coming in Phase 02.

If you'd like the digest closer to your morning, pick a UTC hour
that maps to your local morning. For Singapore (UTC+8), to fire
at 08:00 local you'd choose UTC hour 0 (`--hour 0`).

Override:  envoy digest schedule --hour 0
```

Recovery: user-side workaround is to choose a UTC hour that maps to their local morning. The Daily Digest feature still WORKS — the EC-3 acceptance gate "fires at the user's local morning hour" is degraded but the structural delivery is intact. Phase 02 ships Option B (user-local IANA timezone) per `journal/0003`. The plan-time recommendation (per shard 11 § 7) is to coordinate with shard 22 on the Option A/B decision because the digest's user-visibility of the timezone choice is HIGHER than the budget-tracker's silent reset.

### EC-B — User offline for 3 days

Scenario: User is on a long flight, no signal Sat–Mon. Daily Digest scheduler fires Sat, Sun, Mon — each fan-out reaches a `SendTimeoutError` on the configured channel. On Tuesday morning, the user's phone reconnects.

Plain-language UX (Tuesday's digest):

> "Welcome back. (You were offline since Saturday — here's what's been going on.)
>
> Did over the last 3 days:
> [Sat] (none — you were quiet)
> [Sun] Replied to a query from your sister
> [Mon] Sent $40 to Sam (you'd pre-approved batch payments to him)
>
> Spending this month: $125 of $90 limit (you raised it again on Sunday)
>
> Anything I asked about while you were away?
> • Sun 14:32 — Sam asked for $40. I waited 5 minutes, then stopped.
> • Mon 09:15 — A new contact "Beth" wanted to message you. I waited 5 minutes, then stopped.
>
> Want to review any of those now?"

Recovery: per shard 11 § 3.2 item 6, missed days are NOT silently dropped. The back-fill window is capped at 7 days; if the user is offline for >7 days, the digest summary says "you were offline for more than a week — here's just yesterday's activity," and the older missed days surface only on demand via `envoy digest history`.

### EC-C — Skip digest reply

Scenario: User taps `[Skip digest for a few days]` on Tuesday. Per spec § Interaction line 25.

Plain-language UX (immediate response):

```
   OK — no morning digest for the next 7 days.
   (I'll still ask you about anything important.)

   You can resume anytime: `envoy digest resume`
```

Recovery: per shard 11 § 3.2 item 7, the pause state is written to the Trust Store (`digest:pause:{principal_id}` with `{paused_at, resume_at, reason}`). The state SURVIVES process restart — the scheduler's `start()` reads pause state on init and skips paused principals' job registration until `resume_at`. Time-based resume fires automatically; user-initiated resume is `envoy digest resume`.

If the user pauses for >30 days (`now - paused_at > 30d`), the next scheduler fire surfaces a re-engagement prompt regardless of `resume_at` per spec error `DigestSkippedTooLongWarning`:

```
   It's been 32 days since you turned off your daily digest.
   Want to turn it back on? Or keep it off?

   [ Yes, turn it back on ]   [ Keep it off — I'll come back ]
```

### EC-D — Low-engagement fallback fires after 3 weeks

Scenario: User receives the digest 5 days a week but only opens it once a week for 3 consecutive weeks (per spec § Low-engagement fallback line 29: `<2 opens/week × 3 weeks`).

Plain-language UX (transition is silent — no "you've been bad" prompt; user just notices the digest gets shorter):

The renderer's `form` field flips from `rich` to `compact` (3-line) by default. The next morning's digest is shorter:

```
   3 actions yesterday • $85 of $90 spent this month • 1 question waiting

   Tap to expand
```

If the user still doesn't engage for another 3 weeks, the form flips to `event_only` — the digest fires only on Grant Moment pending OR budget > 80%. Per shard 11 § 3.2 item 8, an advisory `LowEngagementFallbackTriggered` Ledger entry is emitted (advisory not blocking). Recovery: user can manually flip back via `envoy digest schedule --form rich`.

### EC-E — Duress banner: shadow-segment unread duress event

Scenario: A duress event was recorded earlier (Phase 02+ scenario; Phase 01 ships the gate but the shadow segment is empty). Per `specs/daily-digest.md` § Shadow-segment post-duress surface (V2 C-02 fix), the digest renders with priority banner + `[Review duress event]` button — but ONLY on the user's primary channel.

Plain-language UX on **primary channel**:

```
   ⚠ Important — please read first.

   Something happened yesterday that I want you to see.
   I won't say more here on a non-private channel.

   [ Review on your primary device ]
```

Plain-language UX on **non-primary channels** — the standard digest WITHOUT the banner (T-018 defense per shard 11 § 3.2 item 9 — `DuressBannerSuppressedError` if a non-primary channel attempted to render). Phase 01 ships the gate; the shadow segment is empty in P01 normal operation.

### EC-F — All channels fail (network outage)

Scenario: Every configured channel times out. Per shard 11 § 3.2 item 5, the parallel fan-out's `asyncio.gather(..., return_exceptions=True)` collects N exceptions; ALL channel sends failed.

Plain-language UX (next-day digest, when the network is back):

```
   Welcome back. I tried to send your digest yesterday morning
   but couldn't reach any of your channels (Telegram, Slack, email).

   Looks like there was a network issue. Today's digest covers
   both yesterday and today.

   ...
```

Recovery: `DigestDeliveryFailedError` per spec § Error taxonomy line 71. The error is written as a `system_error` Ledger row. The next-day digest's renderer reads the previous-day failure from the Ledger and renders the "X missed deliveries" banner per shard 11 § 3.2 item 5.

### EC-G — User replies "changes" mid-digest with ambiguous text

Scenario: User taps `[ Reply with changes ]` and types "stop summarizing my mail; ask before sending money to anyone new."

Plain-language UX:

```
   I think you said:
     1. Stop the morning mail summary task
     2. Ask before sending money to ANY new recipient
        (currently: I ask only for new recipients OR amounts > $50)

   Did I get that right?

   [ Yes, both ]   [ Just the mail one ]   [ Just the money one ]   [ No, let me try again ]
```

Recovery: per shard 11 § 3.2 item 4, the renderer uses the model adapter when natural-language reply parsing is needed. Phase 01 ships button-confirm semantics; the user must confirm the parsing before changes apply. If the user says "No, let me try again," the runtime re-prompts with structured choices.

---

## 5. Underlying primitives

| Step                           | Primitive (shard)                         | What runs                                                                                                         |
| ------------------------------ | ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Schedule fire                  | shard 11 § 3.2 item 2 (`DigestScheduler`) | `apscheduler.AsyncIOScheduler` + `CronTrigger(hour=<user_hour>, timezone=<UTC in P01>)`; pause-state check        |
| Aggregate Ledger               | shard 11 § 3.2 item 3 + shard 6 § 4       | `LedgerAggregator.aggregate()` queries `EnvoyLedger.query(filter, since, until)`; classified-PK redaction at emit |
| Build payload                  | shard 11 § 3.2 item 4 + 10                | `DigestRenderer` builds `DigestPayload` (11 fields per spec); `receipt_hash` via shared canonical-JSON pipeline   |
| Optional NL summary            | shard 11 § 3.2 item 4 + shard 13 § 5.2    | `EnvoyModelRouter.for_primitive("daily_digest").chat_async()` — fast/cheap preset                                 |
| Back-fill check                | shard 11 § 3.2 item 6 + shard 5 § 4       | `BackfillTracker` reads per-channel `last_success` from Trust Store; itemizes missed days; 7-day cap              |
| Duress banner read             | shard 11 § 3.2 item 9 + shard 5           | `DuressBannerReader` reads local-only shadow segment via `TrustLineageAdapter.read_shadow_segment(...)`           |
| Primary-channel determination  | shard 11 § 3.2 item 9 + shard 5           | `TrustStoreAdapter.get_primary_channel(principal_id)` for duress-banner routing                                   |
| Per-channel fan-out (parallel) | shard 11 § 3.2 item 5 + shard 16 § 3.2    | `asyncio.gather(*[adapter.send_digest(...) for adapter in active_channels], return_exceptions=True)`              |
| Per-channel render             | shard 16 § 3.2 (per-adapter)              | Adapter translates `DigestPayload` to channel-native form (rich / compact / event_only / SMS-10-line)             |
| Ledger emit                    | shard 11 § 3.2 item 5 + shard 6 § 4       | One `ritual_completion` per success; one `system_error` per failure                                               |
| Pause / resume                 | shard 11 § 3.2 item 7 + shard 5 § 4       | `PauseDisableState` writes Trust Store `digest:pause:{principal_id}`; survives restart                            |
| Low-engagement tracking        | shard 11 § 3.2 item 8 + shard 5 § 4       | `LowEngagementTracker` per-principal opens count; rolling 3-week window                                           |

---

## 6. Acceptance criteria served

- **EC-3 (BLOCKING):** This flow IS the EC-3 surface. Acceptance per `02-mvp-objectives.md` EC-3: scheduled Daily Digest fires at user's local morning hour for ≥7 consecutive days, rendering across all configured channels with content sourced from the Ledger; skipped days back-fill in next-day digest, NOT silently dropped. Tier 3 test `tests/e2e/test_daily_digest_morning_delivery.py` per shard 11.
- **EC-3 caveat (timezone):** Phase 01 Option A (UTC fire) means "user's local morning hour" is approximately satisfied via user-side workaround (pick UTC hour mapping to local morning). Tier 3 test asserts the cron fires at the configured hour AND the per-channel delivery happens; it does NOT assert "8 AM local time" because Phase 01 doesn't deliver that.
- **BET-8 falsifiability:** if the digest doesn't fire reliably (or fires at a wildly wrong local time so users stop opening it), BET-8 (the new habit forms) fails. Phase 01 telemetry from EC-3's 7-day cohort run informs whether Option A is acceptable for ship.

---

## 7. Failure modes & recovery

| Failure                            | What the user sees                                                                                                   | Recovery path                                                                                                          |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| All channels timeout (EC-F)        | "I tried yesterday but couldn't reach you. Today's digest covers both."                                              | `DigestDeliveryFailedError` Ledger row; back-fill itemizes missed day; user-visible re-engagement banner               |
| One channel fails, others succeed  | (User sees the digest on at least one channel; failure invisible)                                                    | Parallel fan-out with fault isolation; `system_error` Ledger row for the failing channel                               |
| Pause persists past 30 days (EC-C) | "It's been 32 days since you turned off your daily digest. Want to turn it back on?"                                 | `DigestSkippedTooLongWarning`; re-engagement prompt overrides `resume_at`                                              |
| Low-engagement (EC-D)              | (User notices the digest gets shorter — silent transition)                                                           | `form` field flips: rich → compact → event_only; advisory Ledger entry; user can manually flip back                    |
| Duress banner suppression attempt  | (User on non-primary channel sees standard digest WITHOUT banner)                                                    | `DuressBannerSuppressedError` per shard 11 § 3.2 item 9 — T-018 defense                                                |
| Ledger query timeout               | (User sees a degraded digest with "couldn't read all of yesterday" hint)                                             | Aggregator surfaces partial results with explicit gap markers; per `rules/zero-tolerance.md` Rule 3 no silent fallback |
| Channel cannot render markdown     | (User on SMS sees compact 10-line form; rich features dropped)                                                       | `RedactedFieldRenderError` per spec line 73; classified rows replaced with "N classified entries hidden"               |
| Process restart mid-fan-out        | (User sees only the digests from channels that completed before restart; missed channels fire on next-day back-fill) | Per shard 11 § 3.2 item 6, back-fill tracks per-channel `last_success`, NOT per-digest                                 |
| Timezone surprise (EC-A)           | "I'll send your digest at 08:00 UTC — that's about 16:00 (4 PM) where you are."                                      | `envoy digest schedule --help` exposes caveat; Phase 02 ships Option B per `journal/0003`                              |

---

## 8. Cross-references

- `workspaces/phase-01-mvp/01-analysis/11-daily-digest-implementation.md` § 3 (Envoy-new-code surface), § 4 (class structure), § 5 (integration points)
- `workspaces/phase-01-mvp/01-analysis/06-envoy-ledger-implementation.md` § 4 (`EnvoyLedger.query` interface)
- `workspaces/phase-01-mvp/01-analysis/13-model-adapter-implementation.md` § 5.2 (digest model preset)
- `workspaces/phase-01-mvp/01-analysis/16-channel-adapters-implementation.md` § 3.2 (per-channel `send_digest`)
- `workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md` § 4 (`digest_schedule`, primary-channel binding, pause-state, last-success state)
- `workspaces/phase-01-mvp/journal/0003-GAP-budget-ceiling-timezone.md` (timezone disposition; HIGH escalation candidate per shard 11 § 7)
- `workspaces/phase-01-mvp/03-user-flows/03-grant-moment-flow.md` (the digest surfaces missed Grant Moments + cascade-revoke entry points)
- `workspaces/phase-01-mvp/03-user-flows/05-channel-onboarding-flow.md` (initial digest_channel selection happens during channel setup)
- `specs/daily-digest.md` § Schedule, § Content template, § Interaction, § Low-engagement fallback, § Channel-adaptive rendering, § Shadow-segment post-duress surface, § Schema, § Error taxonomy
- `specs/ledger.md` § Entry type `ritual_completion` (per-channel digest delivery confirmation)
- `specs/trust-lineage.md` line 136 (shadow segment local-only / never-synced)
- `rules/communication.md` (plain-language framing throughout)
- `rules/event-payload-classification.md` Rule 1 (single-point filter at the aggregator)
