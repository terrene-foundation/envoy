# 04 — Wave 4: Channel adapters + Daily Digest

**Purpose:** Build 8 channel adapters (CLI + Web + 6 messaging) and Daily Digest. Wave 4 converges on EC-3 (digest 7-day fire), EC-7 (8 channels × N=3 onboarding = 24 sessions), and EC-8 (7-day cross-channel coherence with cascade revocation).

**Source authority:** `02-plans/01-build-sequence.md` § Wave 4 + shards 11 / 16.

**Depends on:** Waves 1 + 2 + 3.

---

## T-04-70 — Build envoy/channels/base (ABC + InboundMessage + 11 typed errors)

**Implements:** `specs/channel-adapters.md`

**Source:** Shard `01-analysis/16-channel-adapters-implementation.md` § 3 step 1.

**Action:** `ChannelAdapter` ABC + `InboundMessage` envelope + 11 typed errors — unified contract per spec.

**Capacity check:** ~150 LOC; 3 invariants (ABC method declarations; InboundMessage schema; 11-error taxonomy); 1 call-graph hop.

**Estimate:** 0.25 session.

---

## T-04-71 — Build envoy/channels/cli + envoy/channels/web

**Source:** Shard 16 § 3 step 2.

**Action:**

1. `CLIChannelAdapter` — wraps `kailash.channels.cli_channel`.
2. `WebChannelAdapter` — wraps `kailash.channels.api_channel`; **localhost bind with Origin/Host allowlist** (post-#673 + per `rules/security.md` § "Network Transport Hardening"). DNS rebinding defense.

**Capacity check:** ~200 LOC; 4 invariants (TUI conversation contract; localhost bind; Origin/Host allowlist; signed-event surface); 2 call-graph hops.

**Blocks on:** T-04-70.

**Estimate:** 0.5 session.

---

## T-04-72 — Build envoy/channels/{telegram, slack, discord} (clean bot-API trio)

**Source:** Shard 16 § 3 step 3.

**Action:** Wrap `nexus.transports.webhook.WebhookTransport` with per-vendor `WebhookSigner`:

- `TelegramChannelAdapter` (python-telegram-bot ≥ 21.0; LGPL-3.0+ — see NOTICES T-05-91).
- `SlackChannelAdapter` (slack-sdk).
- `DiscordChannelAdapter` (discord.py).

**Capacity check:** ~450 LOC (~150 each); 4 invariants (per-vendor webhook signature; bot-API contract per vendor; rate-limit awareness; Connection Vault credential binding); 2 call-graph hops.

**Blocks on:** T-04-70 + T-01-24 (Connection Vault).

**Estimate:** 0.75 session.

---

## T-04-73 — Build envoy/channels/{whatsapp, imessage, signal} (caveated trio)

**Source:** Shard 16 § 3 step 4.

**Action:** Per `specs/channel-adapters.md` lines 171-173 disposition (paid-tier / Apple-ToS-grey / Path-B legal-gate):

- `WhatsAppChannelAdapter` — paid-tier (WhatsApp Business API).
- `IMessageChannelAdapter` — BlueBubbles bridge (Apple-ToS-grey).
- `SignalChannelAdapter` — signal-cli REST (Path-B legal-gate).

**Note:** Runtime cohort-driven de-scope #1 (drop iMessage + Signal to 5 channels) is a /implement-time decision per shard 16, NOT an architecture-time decision. /implement ships all 8 adapters; runtime cohort decides which 5–8 are included in EC-7.

**Capacity check:** ~450 LOC (~150 each); 5 invariants (paid-tier feature gate; BlueBubbles bridge contract; signal-cli REST contract; legal-disposition documentation; cohort-driven de-scope flag); 2 call-graph hops.

**Blocks on:** T-04-70 + T-01-24.

**Estimate:** 0.75 session.

---

## T-04-74 — Build envoy/channels/inbound_router + grant_moment_renderer

**Source:** Shard 16 § 3 steps 5-6.

**Steps:**

1. `InboundRouter` — concurrent `asyncio.gather` over every adapter's `receive_message()`; routes to active session.
2. `GrantMomentRenderer` per channel — channel-native UI; numbered-options text fallback for iMessage/Signal.

**Capacity check:** ~350 LOC; 5 invariants (concurrent gather; session routing; per-channel UI map; numbered-options fallback; primary-channel binding check); 3 call-graph hops.

**Blocks on:** T-04-71 through T-04-73 + T-03-50 (Grant Moment).

**Estimate:** 0.75 session.

---

## T-04-75 — Build envoy/channels/{rate_limiter, credential_resolver}

**Source:** Shard 16 § 3 steps 7-8.

**Steps:**

1. `PerChannelRateLimiter` — per-channel quota translation.
2. `CredentialResolver` — startup-time Connection Vault entry resolution.

**Capacity check:** ~150 LOC; 3 invariants (per-channel quota table; Connection Vault resolution timing; credential refresh on rotation); 2 call-graph hops.

**Blocks on:** T-04-71 through T-04-73 + T-01-24.

**Estimate:** 0.25 session.

---

## T-04-76 — Wire envoy/channels/ (Tier 2 — per-channel lifecycle)

**Action:** Per `02-plans/03-package-skeleton.md` § 3 `tests/tier2/channels/`:

- 8 lifecycle tests (`test_<channel>_adapter_lifecycle.py`).
- 8 send-message tests.
- 8 ritual-delivery tests.
- `test_inbound_router_wiring.py`.
- `test_credential_resolver_wiring.py`.
- `test_h03_primary_channel_binding.py`.

**Acceptance:** Green against vendor-sandbox fixtures (Telegram test bot, Slack ngrok, Discord guild). NO mocking.

**Blocks on:** T-04-71 through T-04-75.

**Estimate:** 1 session (8 channels × 3 wiring patterns).

---

## T-04-77 — Acceptance EC-7 Tier 3: 8 channels × N=3 onboarding (24 sessions)

**Implements:** EC-7 acceptance gate per `02-plans/02-test-strategy.md`.

**Action:** `tests/tier3/test_session_continuity_8_channels.py` — N=3 first-time-user sessions per channel × 8 channels = 24 successful onboardings (or 5 channels × N=3 = 15 if cohort-driven de-scope #1 invoked).

**Acceptance:** ≥ 5 channels (de-scope floor) successfully onboard N=3 sessions each. Channel cohort decision documented in /codify.

**Blocks on:** T-04-76 + T-02-44 (boundary conversation wiring).

**Estimate:** 0.5 session.

---

## T-04-78 — Acceptance EC-8 Tier 3: 7-day cross-channel coherence

**Implements:** EC-8 acceptance gate per `02-plans/02-test-strategy.md`.

**Action:** `tests/tier3/test_envoy_7_day_cross_channel_coherence.py` — 7-day operating window across ≥ 4 of 8 channels with cross-channel state-equivalence test running daily; cascade revocation of Day-1 grant correctly revokes Day-6 child grant initiated from a different channel.

**Acceptance:** State-equivalence holds Day 1 through Day 7. Cascade revocation reaches Day-6 child.

**Blocks on:** T-04-76 + T-03-52 (cascade orchestrator) + T-04-84 (digest 7-day).

**Estimate:** 0.5 session.

---

## T-04-80 — Build envoy/daily_digest/service + scheduler

**Implements:** `specs/daily-digest.md`

**Source:** Shard `01-analysis/11-daily-digest-implementation.md` § 3 step 1.

**Action:** `DailyDigestService` facade + `DigestScheduler` — `apscheduler.AsyncIOScheduler` + `CronTrigger`; per-principal job registration.

**Capacity check:** ~200 LOC; 3 invariants (per-principal job registration; cron scheduler restart-safe; UTC-only schedule per disposition #1); 2 call-graph hops.

**Estimate:** 0.5 session.

---

## T-04-81 — Build envoy/daily_digest/aggregator + renderer

**Source:** Shard 11 § 3 steps 2-3.

**Steps:**

1. `LedgerAggregator` — queries `EnvoyLedger.query()` for actions / refusals / spend / pending_grants / planned_today.
2. `DigestRenderer` — produces `DigestPayload` (11-field schema/1.0 verbatim per spec); optional `EnvoyModelRouter.for_primitive("daily_digest")` for natural-language summary.

**Capacity check:** ~280 LOC; 4 invariants (Ledger query semantics; 11-field DigestPayload schema; optional NL summary; principal_id propagation); 3 call-graph hops.

**Blocks on:** T-04-80 + T-01-18 (Ledger query) + T-01-22 (model router).

**Estimate:** 0.5 session.

---

## T-04-82 — Build envoy/daily_digest/{fanout, backfill, pause_disable, low_engagement}

**Source:** Shard 11 § 3 steps 4-5.

**Steps:**

1. `PerChannelFanout` — `asyncio.gather(..., return_exceptions=True)` parallel fan-out with fault isolation.
2. `BackfillTracker` — Trust-store-backed missed-day catch-up.
3. `PauseDisableState` — pause/resume persistence.
4. `LowEngagementTracker` — habituation form-flip (T-019 regression scope).

**Capacity check:** ~250 LOC; 5 invariants (fault-isolated fanout; backfill correctness; pause persists across restart; engagement-flip threshold; per-channel exception capture); 3 call-graph hops.

**Blocks on:** T-04-80 + T-04-71 through T-04-73 (channels for fanout target) + T-01-12 (Trust).

**Estimate:** 0.5 session.

---

## T-04-83 — Build envoy/daily_digest/{duress_reader, errors, CLI}

**Source:** Shard 11 § 3 steps 6-7.

**Steps:**

1. `DuressBannerReader` — local-only shadow-segment read; primary-channel-only.
2. 5 typed errors.
3. CLI: `envoy digest today / pause / resume / schedule`.

**Capacity check:** ~150 LOC; 3 invariants (shadow-segment local-only; primary-channel-only render; 5-error taxonomy); 2 call-graph hops.

**Blocks on:** T-04-80 + T-04-82.

**Estimate:** 0.25 session.

---

## T-04-84 — Wire envoy/daily_digest/ + Acceptance EC-3 Tier 3

**Action:**

- Tier 2: `tests/tier2/test_daily_digest_service_wiring.py`, `test_digest_form_per_channel.py`, `test_low_engagement_fallback.py`, `test_duress_banner_primary_only.py`, `test_digest_reply_no_yes_skip.py`, `test_backfill_skipped_days.py`, `test_pause_disable_persists_across_restart.py`.
- Tier 3 EC-3: `tests/tier3/test_daily_digest_morning_delivery.py` — 7-day fire battery using `freezegun` for compression.

**Acceptance:** All Tier 2 green; Tier 3 7-day fire across configured channels.

**Blocks on:** T-04-80 through T-04-83.

**Estimate:** 0.75 session.

---

## Wave 4 milestone gate

Per `02-plans/01-build-sequence.md` § 3 Milestone 4:

- EC-3 (digest 7-day) green.
- EC-7 (8-channel × N=3 onboarding ≥ de-scope floor) green.
- EC-8 (7-day cross-channel coherence with cascade revocation) green.

**Wall-clock estimate:** ~3 sessions (channels 4 || digest 2 in worktrees).

---

## Cross-references

- Build sequence: `02-plans/01-build-sequence.md` § Wave 4
- Primitive shards: `01-analysis/{11,16}-*-implementation.md`
- Channel cohort de-scope: `specs/channel-adapters.md` lines 171-173
- Network security: `.claude/rules/security.md` § "Network Transport Hardening"
- Cross-channel cascade: shard 16 § 7.2 + shard 22 § 3.8
