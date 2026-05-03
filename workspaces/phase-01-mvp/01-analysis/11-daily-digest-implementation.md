# 11 — Daily Digest implementation deep-dive

**Document role:** Phase 01 implementation deep-dive for the Daily Digest primitive (shard 11 of /analyze; Group D per `01-shard-plan.md` § 5; depends on shards 5 Trust store, 6 Envoy Ledger, 13 Model adapter, 16 Channel adapters; queued behind shard 16 per task graph). Establishes the verified upstream provider state (`OrchestrationRuntime` is multi-agent strategy-coordination, NOT scheduling — disposition (b)), the Envoy-new-code surface (scheduler + Ledger aggregator + content renderer + per-channel fan-out + skipped-day back-fill state + pause-disable persistence), the class structure, the integration points, the Tier 2 / Tier 3 test surface, and the EC-3 + BET-8 acceptance gates.

**Date:** 2026-05-03 (shard 11 of /analyze).
**Status:** DRAFT — load-bearing for shard 19 (pipx distribution dependency tree must include `apscheduler`) and shard 20 (build-sequence places shard 11 after the wave-A+B+C+D dependencies).
**Owning shard:** 11 (per `01-shard-plan.md` § 2).
**Exit criteria served:** EC-3 (Daily Digest renders at scheduled time with real data — `02-mvp-objectives.md` lines 44–55), BET-8 (the new habit forms — Daily Digest is the most-frequent ritual).
**Discipline:** Cite, do not paraphrase frozen specs. Per `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`, the shard's question is "given this spec is frozen, how do I wire `kailash-py` to deliver it?" Per `rules/specs-authority.md` Rule 4 + Rule 5b (no spec edits at this shard).

**Capacity check:** 1 primitive, 1 source spec (`daily-digest.md`), ~6 invariants tracked (scheduler fires at user-local-morning-hour; back-fill MUST work not "usually"; per-channel fan-out fault-isolated; pause-disable persists across restart; primary-channel duress banner; cross-channel ritual_completion Ledger emit), ≤5 cross-primitive references (Ledger, Channel adapters, Model adapter, Trust store, Connection Vault NOT involved — channel adapters resolve their own creds). Within `rules/autonomous-execution.md` budget.

---

## 1. Source spec citation

Frozen specs the Daily Digest implements against (cited; not edited):

- `specs/daily-digest.md` § Purpose (lines 3–5) — "Morning ritual delivering 2-min action/refusal/spend summary + pending Grant Moments."
- `specs/daily-digest.md` § Provenance (lines 7–11) — Source `phase-00-alignment/01-analysis/01-ux-rituals.md v2 §5`; T-019 habituation defense via low-engagement fallback; BET-8 habit formation tested.
- `specs/daily-digest.md` § Schedule (lines 13–15) — "User-configured delivery time (default 8am local). User-chosen channel (default first-connected)."
- `specs/daily-digest.md` § Content template (lines 17–19) — "Actions (with outbox items), refusals, spend (of monthly ceiling), pending Grant Moments, today's planned actions, reply prompt."
- `specs/daily-digest.md` § Interaction (lines 21–25) — Reply "no" / no-reply (proceed); reply "yes" / modify (extract user changes + apply); reply "skip digest" (temporarily disable).
- `specs/daily-digest.md` § Low-engagement fallback (lines 27–29) — `<2 Digest opens/week for 3 weeks → offer 3-line compact form or event-driven-only delivery (fires on Grant Moment pending or budget > 80%)`.
- `specs/daily-digest.md` § Channel-adaptive rendering (lines 31–33) — Email/Web rich + attachments; Telegram/Slack/Discord inline buttons; SMS/WhatsApp compact 10-line; CLI on `envoy digest today`.
- `specs/daily-digest.md` § Shadow-segment post-duress surface (lines 35–37; V2 C-02 fix) — "If unread duress event in shadow segment at Digest time, Digest renders with priority banner + `[Review duress event]` button."
- `specs/daily-digest.md` § Schema (digest payload) (lines 39–64) — frozen 11-field JSON schema with `schema_version: "digest/1.0"`, `digest_id` (uuid-v7), `principal_genesis_id` (sha256), `scheduled_for` / `delivered_at` (iso8601), `channel_id`, `form` (rich | compact | event_only), `duress_banner` (present + shadow_event_ref), `summary` (actions/refusals/spend/pending_grants/planned_today), `user_reply` (inline | null), `receipt_hash` (sha256). Classified `record_id` and `principal_genesis_id` values routed through `format_record_id_for_event` per `specs/classification-policy.md` (line 66).
- `specs/daily-digest.md` § Error taxonomy (lines 68–76) — 5 typed errors: `DigestDeliveryFailedError` (all configured channels timeout/transport-error → next-day "X missed deliveries" banner); `DuressBannerSuppressedError` (shadow-segment duress unread but caller is non-primary channel → primary-only banner; T-018 defense); `RedactedFieldRenderError` (channel cannot render redacted markers, e.g. SMS → drop classified rows + summary count "N classified entries hidden"); `LowEngagementFallbackTriggered` (advisory; <2 opens/week × 3 weeks); `DigestSkippedTooLongWarning` (skip-digest >30 days → re-engagement prompt).
- `specs/daily-digest.md` § Cross-references (lines 78–84) — explicit forward to `specs/channel-adapters.md` (per-channel rendering + `send_digest`), `specs/ledger.md` (action summary source), `specs/trust-lineage.md` (shadow segment access), `specs/classification-policy.md` (record_id redaction in summary), `specs/threat-model.md` (T-019).
- `specs/daily-digest.md` § Test location (lines 86–93) — 6 test files: `tests/e2e/test_daily_digest_morning_delivery.py` (Tier 3 scheduled delivery on each channel); `tests/integration/test_digest_form_per_channel.py` (rich vs compact vs SMS); `tests/integration/test_low_engagement_fallback.py`; `tests/integration/test_duress_banner_primary_only.py` (V2 C-02); `tests/regression/test_t019_habituation_low_engagement_fallback.py`; `tests/integration/test_digest_reply_no_yes_skip.py`.
- `specs/daily-digest.md` § Open questions (lines 95–101) — 5 open questions: timezone basis (default 8am local — across timezones in Shared Household, which household member's tz wins); compact 10-line SMS budget sufficiency; "skip digest" duration default; reply-parsing extensibility (NL vs structured); receipt_hash content + cross-channel byte-identity.

Cross-spec citations (read-only at this shard):

- `specs/channel-adapters.md` § Adapter contract / § Ritual delivery — `adapter.send_digest(target_principal_id, digest, *, timeout_seconds=10)` is the outbound substrate per shard 16 § 3.2 item 1; the per-channel `form` translation (rich / compact / event_only) is owned by each `ChannelAdapter` subclass per shard 16 § 3.2 items 4–11.
- `specs/ledger.md` § Entry types lines 47–91 — Daily Digest READS via `EnvoyLedger.query(filter)` for the previous-24h window AND WRITES `ritual_completion` entries on each delivery per shard 6 § 5.1 row "Daily Digest".
- `specs/trust-lineage.md` lines 136–137 — `DuressUnlockEvent → local-only shadow segment (NEVER synced; CRIT-03 fix); generic unlock_event written to synced Ledger`. The Digest's duress-banner read crosses the shadow-segment boundary (local-only); the spec mandates this is a primary-channel-only render.
- `specs/budget-tracker.md` (cross-shard 12) — Digest summary's `spend.current_microdollars` / `spend.monthly_ceiling_microdollars` come from `BudgetTracker` per shard 12. The timezone-basis open question (shard 12 § 7 + `journal/0003-GAP-budget-ceiling-timezone.md`) is the SAME ambiguity surface as `daily-digest.md` § Open question 1.

---

## 2. Verified provider citation — `OrchestrationRuntime` is disposition (b)

Per `03-kailash-py-mvp-readiness.md` § 5 verification protocol: ISS-26 (#602) was C-grade at 2026-04-21 (`OrchestrationRuntime` absent). The freshness gate (`03-kailash-py-mvp-readiness.md` § 2 row ISS-26) recorded #602 closed 2026-04-25 with the disposition "verify surface in shard 11 — was previously C-grade (absent)." This shard executed the verification.

### 2.1 Issue closure verification

`gh issue view 602 --repo terrene-foundation/kailash-py --json closedAt,state,title,body` (queried 2026-05-03):

```text
title: "[parity] Implement OrchestrationRuntime class + .run() method"
state: CLOSED
closedAt: 2026-04-25T09:56:01Z
body summary: "kailash-py has Kaizen orchestration primitives but not a class
named OrchestrationRuntime with a .run() method matching the Rust-side shape.
Create the API alignment for cross-SDK parity."
"Phase impact: Phase 03 scheduled rituals."
```

Two findings:

1. The issue body explicitly scopes the closure to **"Phase 03 scheduled rituals"** — the OrchestrationRuntime delivers cross-SDK _parity for the strategy-driven coordination shape_, NOT scheduling.
2. `closedByPullRequestsReferences` returned the empty list at `gh` query time (likely `gh` API limitation rather than evidence of no PR); the linked PR can be located by code citation below.

### 2.2 Verified upstream code surface

**Module path:** `~/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/orchestration/runtime.py` (1002 LOC, verified present 2026-05-03).
**Public re-exports:** `~/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/orchestration/__init__.py` (72 LOC, verified) — exports `OrchestrationRuntime`, `OrchestrationStrategy`, `OrchestrationStrategyKind`, `OrchestrationConfig`, `OrchestrationResult`, `OrchestrationError`, `Coordinator`, `SharedMemoryCoordinator`, `AgentLike`, `PipelineInputSource`, `PipelineStep`. `__all__` matches imports per `rules/orphan-detection.md` Rule 6 (no missing exports).

**Verified surface shape** (citing `runtime.py` lines 4–75 module docstring):

- Constructor: `OrchestrationRuntime(strategy, coordinator=None, config=None)` + builder-style `.add_agent(name, agent)`, `.strategy(s)`, `.config(c)`, `.coordinator(c)`.
- Execution: `await runtime.run(input)` returns `OrchestrationResult` (sync convenience: `runtime.run_sync(input)`).
- Strategies: 4 enum members — `Sequential` / `Parallel` / `Hierarchical` / `Pipeline` constructed via `OrchestrationStrategy.<name>(...)` factories.
- Result fields: `agent_results` (dict by name), `final_output` (str), `total_iterations` (int), `total_tokens` (int), `duration_ms` (int).
- Errors: empty-runtime / unknown-coordinator / pipeline-step-references-unknown-agent / max-agent-calls all raise `OrchestrationError`.

**Cross-grep for scheduling primitives** (run 2026-05-03):

```text
grep "scheduled_agent|cron|class Scheduler|class Schedule\b|apscheduler"
   /Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/
→ ZERO matches in source code.

grep "schedule|Scheduler" .../kaizen/orchestration/ .../kaizen/agents/
→ ZERO matches.
```

**Apscheduler IS available transitively** (verified via `.venv/lib/python3.13/site-packages/apscheduler/`) — `kailash-kaizen`'s `[dev]` or runtime deps already pull it in (commonly via `dataflow` integration). Envoy can compose `apscheduler` without a new third-party-dep audit.

**Adjacent surface — `BudgetResetService`** (`~/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/trust/governance/budget_reset.py`, line 38): docstring "typically scheduled via cron/APScheduler" — explicitly delegates scheduling to the caller. This is the _idiomatic upstream pattern_: kaizen provides the work-doing primitive; the caller (Envoy) composes the scheduling substrate.

### 2.3 Verified disposition: (b) partial implementation

Mapping the three dispositions from the shard prompt:

| Disposition                                                                              | Match? | Evidence                                                                                                                                                                                                                                                                                                |
| ---------------------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| (a) Full `OrchestrationRuntime` with scheduled-agent surface — Envoy uses upstream       | NO     | No `scheduled_agent` / `Schedule` / `cron` symbol anywhere in `kaizen.orchestration`; the issue body explicitly scopes #602 to Phase 03 scheduled rituals. The closed issue delivers parity for the multi-agent coordination shape, not scheduling.                                                     |
| (b) Partial implementation (e.g., orchestration without scheduling) — Envoy adds glue    | YES    | `OrchestrationRuntime` exists and works for Sequential / Parallel / Hierarchical / Pipeline coordination; agents are registered and dispatched via strategy; `apscheduler` is present in the dep tree. Envoy's job is to **wire `apscheduler` to fire `OrchestrationRuntime.run(...)` at digest time**. |
| (c) Just docs / interface design with no executable code — Envoy implements full locally | NO     | The 1002-LOC implementation is fully exercised; this is not a stub.                                                                                                                                                                                                                                     |

**Disposition (b) is the verified state.** Envoy ships the scheduler glue; the orchestration substrate (multi-agent coordination, if needed for the digest's content-aggregation / rendering / fan-out pipeline) is upstream. Phase 01 Daily Digest does NOT require multi-agent coordination — the digest is a single-actor flow (aggregate → render → fan-out) — so `OrchestrationRuntime`'s strategy machinery is OPTIONAL. The Envoy scheduler invokes a plain async function; the function may use `OrchestrationRuntime.sequential()` internally if Phase 02 grows the digest into a multi-agent pipeline (e.g. researcher + writer + reviewer per the `OrchestrationRuntime` docstring example).

**Phase 01 implementation choice (sized to EC-3, not Phase 03):** Use `apscheduler.AsyncIOScheduler` with a `CronTrigger` directly. Single async coroutine handles aggregate + render + fan-out. `OrchestrationRuntime` is referenced as the future-compatible substrate but not exercised in Phase 01. Per `rules/zero-tolerance.md` Rule 6 (Implement Fully), the scheduling glue MUST work end-to-end, not "scheduled-agent surface coming in Phase 03."

### 2.4 Indirect-closure PR refs improving the Daily Digest surface (since 2026-04-21)

Per `03-kailash-py-mvp-readiness.md` § 2.2, three closures touch the Digest hot path:

1. **#735 — `_execute_strategy` ThreadPoolExecutor drops contextvars** (closed 2026-04-30; cited via shard 13 § 2.1 row #735). Effect: when the digest scheduler dispatches concurrent per-channel `send_digest()` fan-out, contextvars (e.g. `principal_id`, `tenant_id`, `request_id`) propagate correctly across the ThreadPoolExecutor boundary. Without this fix the per-channel send paths would lose tenancy context, breaking `rules/tenant-isolation.md` Rule 1 cache-key construction in the channel adapters.
2. **#767 — nexus `durability_middleware` drains StreamingResponse body** (closed via shard 16 § 2.2). Effect: the Web channel's SSE-rendered Digest preview no longer leaves connections half-drained; load-bearing for `WebChannelAdapter.send_digest()` rendering.
3. **#737 — Nexus WorkflowServer `lifespan=` disables consumer `@on_event`** (closed via shard 16 § 2.2). Effect: channel-adapter lifecycle hooks fire correctly so the Digest scheduler can read each adapter's "ready" state before scheduling fan-out.

### 2.5 What `kailash-py` does NOT provide — Envoy-new-code surface preview

`kailash-py` does NOT provide:

1. **A scheduler primitive that fires at user-local-morning-hour.** `apscheduler` is the dependency; `kaizen.orchestration` is the orchestration runtime; neither composes them.
2. **A Ledger-aggregation digest-content builder.** `EnvoyLedger.query(filter)` from shard 6 returns raw entries; the digest spec § Content template requires actions+refusals+spend+pending_grants+planned_today+reply_prompt aggregation. Envoy-new-code.
3. **A digest-payload renderer per spec § Schema.** The 11-field `digest/1.0` schema is Envoy-spec-defined.
4. **A skipped-day back-fill state store.** The "next-day digest as a back-fill, not silently dropped" requirement (EC-3 acceptance gate per `02-mvp-objectives.md` line 54) requires per-channel last-success state.
5. **A pause-disable persistence layer.** The "skip digest" reply (spec § Interaction line 25) requires durable state.
6. **Per-channel fan-out orchestration.** Sequential vs parallel vs fault-isolated emission (key design question #5 from prompt).
7. **A low-engagement-fallback tracker.** The `<2 opens/week × 3 weeks` heuristic (spec § Low-engagement fallback) requires per-principal open-count state.
8. **A duress-banner reader for the local-only shadow segment.** Per `specs/trust-lineage.md` line 136, the shadow segment is local-only / never-synced; the Digest's read crosses the shadow-segment boundary.

These eight items are Envoy-new-code surface; § 3 itemises them.

---

## 3. Envoy-new-code surface

### 3.1 Module shape: `envoy.daily_digest` composing upstream pieces

The Phase 01 Envoy-new-code surface is a Python package `envoy.daily_digest` exposing the facade `DailyDigestService`. The package composes:

- `apscheduler.schedulers.asyncio.AsyncIOScheduler` + `apscheduler.triggers.cron.CronTrigger` (verified present in dep tree, § 2.2) — the scheduling substrate.
- `envoy.ledger.EnvoyLedger.query(filter, since, until)` (shard 6 § 4) — the content source for actions / refusals / spend / pending_grants / planned_today.
- `envoy.model.router.EnvoyModelRouter.for_primitive("daily_digest")` (shard 13 § 3.2) — text generation for the digest's natural-language summary; uses a fast/cheap preset by default per shard 13 § 5.2.
- `envoy.channels.{cli,web,telegram,slack,discord,whatsapp,imessage,signal}.send_digest(target_principal_id, digest, *, timeout_seconds=10)` (shard 16 § 3.2) — the per-channel outbound substrate; each adapter renders the unified `DigestPayload` into channel-native form (rich / compact / event_only).
- `envoy.trust.TrustStoreAdapter` (shard 5) — the source for per-principal `digest_schedule` (timezone, hour, channel preferences, primary-channel binding, pause-state). The Trust store IS the persistence layer; Envoy does NOT introduce a parallel store per shard 16 § 3.2 item 16 cross-channel-coherence delegation pattern.
- `envoy.trust.lineage.read_shadow_segment(principal_id, since)` (shard 5) — local-only shadow-segment read for the duress banner (per `specs/trust-lineage.md` line 136 + `specs/daily-digest.md` § Shadow-segment post-duress surface).

Composition philosophy: per `rules/orphan-detection.md` Rule 1 + `rules/facade-manager-detection.md` Rule 1 + Rule 3, `DailyDigestService.__init__` takes its dependencies (Ledger, ModelRouter, registered ChannelAdapters dict, TrustStoreAdapter, classification policy) explicitly — no global lookup, no self-construction.

Per `rules/orphan-detection.md` Rule 1, the `DailyDigestService` facade has at least one production call site within 5 commits — the call site is `envoy.runtime.bootstrap.start_daily_digest_scheduler(service)` invoked from `envoy.runtime.session.SessionRouter` startup hook (alongside the InboundRouter hook from shard 16 § 3.2 item 12).

### 3.2 Surface to be built (Envoy-new-code)

1. **`envoy.daily_digest.service.DailyDigestService`** — facade. Methods: `start()` (starts the apscheduler), `stop(drain_timeout_seconds=5)`, `trigger_now(principal_id)` (CLI-callable for `envoy digest today` per spec § Channel-adaptive rendering line 33), `pause(principal_id, *, duration_days=7)`, `resume(principal_id)`. Composes upstream `AsyncIOScheduler` + Envoy primitives.

2. **`envoy.daily_digest.scheduler.DigestScheduler`** — wraps `apscheduler.AsyncIOScheduler`. Per principal, registers a `CronTrigger(hour=<user_hour>, timezone=<user_tz>)` job that fires the digest pipeline. **Per shard 12 + `journal/0003-GAP-budget-ceiling-timezone.md`, the timezone basis is the SAME ambiguity surface — `specs/daily-digest.md` § Open question 1 names it explicitly. Phase 01 disposition: Option A (UTC + user-side display)** for consistency with shard 12's recommended Option A, deferring Option B (user-local IANA timezone) to shard 22's spec-gap analysis. **Crucially, however, the digest UX visibility of the timezone choice is HIGHER than the budget-tracker's** (the user actively sees "morning ritual at 8am" — a UTC-only fire would visibly fire at 4pm Singapore, which is BET-8-falsifying). § 7 below escalates this to HIGH per `01-shard-plan.md` § 4 with a recommendation to coordinate the Option A/B choice with shard 22 across both shards 11 and 12.

3. **`envoy.daily_digest.aggregator.LedgerAggregator`** — given a `(principal_id, window_start, window_end)`, queries `EnvoyLedger.query(filter, since, until)` for each summary section. Returns a `DigestSummary` dataclass with the 5 `summary` fields (`actions`, `refusals`, `spend`, `pending_grants`, `planned_today`). Per spec § Content template line 19. Per `rules/event-payload-classification.md` Rule 1 + `specs/daily-digest.md` line 66, every `record_id` and `principal_genesis_id` MUST be routed through `format_record_id_for_event` BEFORE being placed into the `DigestPayload`. The aggregator is the single-point filter site.

4. **`envoy.daily_digest.renderer.DigestRenderer`** — converts `DigestSummary` + back-fill state + duress-banner state into a unified `DigestPayload` matching `specs/daily-digest.md` § Schema (lines 39–64) verbatim. The renderer:
   - Constructs `digest_id` as uuid-v7 (time-ordered for forensic correlation).
   - Sets `schema_version: "digest/1.0"`.
   - Computes `receipt_hash = sha256(canonical_dumps(payload_minus_receipt_hash))` per `envoy.ledger.canonical.canonical_dumps` (shard 6 § 3.2). This satisfies `specs/daily-digest.md` § Open question 5 (cross-channel byte-identity) by reusing the Ledger's canonical-JSON contract.
   - Optionally invokes `EnvoyModelRouter.for_primitive("daily_digest").chat_async([...])` (shard 13 § 5.2) to generate the natural-language `summary` text. Per shard 13, the legacy `kaizen.providers.llm.<provider>.chat_async()` substrate handles the wire send; the model router selects the per-primitive override (`ENVOY_DIGEST_MODEL`) for cost discipline.

5. **`envoy.daily_digest.fanout.PerChannelFanout`** — per key design question #5 (multi-channel emission). **Phase 01 disposition: parallel fan-out with fault isolation, NOT sequential.** `asyncio.gather(*[adapter.send_digest(target_principal_id, digest, timeout_seconds=10) for adapter in active_channels], return_exceptions=True)` — each channel send is independent; one channel's `SendTimeoutError` does NOT block siblings. Per spec § Error taxonomy `DigestDeliveryFailedError` line 71, the error fires only when ALL configured channels fail; partial-failure is the common case and surfaces in the next-day digest as a "X missed deliveries" banner. The fanout writes one `ritual_completion` Ledger entry per successful channel send AND one `system_error` entry per failed channel (per `rules/event-payload-classification.md` Rule 1 single-point filter at the emitter; `format_record_id_for_event` applied to `target_principal_id`).

6. **`envoy.daily_digest.backfill.BackfillTracker`** — per key design question #4. Per-channel last-successful-emission state stored in the **Trust store** (NOT a parallel digest-side store, per shard 16 § 3.2 item 16 delegation pattern):
   - On every successful `adapter.send_digest()` returning `SendReceipt`, the BackfillTracker writes `TrustStoreAdapter.set_kv("digest:last_success", principal_id=p, channel_id=c, value={delivered_at, digest_id})`.
   - On scheduler fire, the tracker queries the per-channel last-success timestamp; if `now - last_success > 24h + tolerance`, the missed days are itemized and the digest's `summary` includes the back-fill payload.
   - Ledger query window for back-fill: `since = max(last_successful_delivered_at, scheduled_for - 7d)` (cap at 7 days to prevent unbounded growth on chronic-offline principals).
   - Per `rules/zero-tolerance.md` Rule 6 (Implement Fully), the back-fill MUST work — not "usually." Tier 2 wiring tests (§ 6.1 below) MUST simulate skipped-day scenarios and assert the next-day digest's actions array contains the missed-day Ledger entries.

7. **`envoy.daily_digest.pause.PauseDisableState`** — per key design question #6. Pause state stored in the Trust store as `digest:pause:{principal_id}` with `{paused_at, resume_at, reason}` fields. Default pause duration: 7 days (per spec § Open question 3 — explicit Phase 01 disposition resolving the open-question default). Resume happens via:
   - Time-based: scheduler checks `resume_at <= now` before each fire.
   - User-initiated: `envoy digest resume` CLI command writes `resume_at = now` to Trust store.
   - Spec § Error taxonomy `DigestSkippedTooLongWarning` (line 75): if `now - paused_at > 30 days`, the next scheduler fire surfaces a re-engagement prompt regardless of `resume_at`.
   - Pause-state SURVIVES process restart (Trust-store backed); the scheduler's `start()` reads pause state on initialization and skips paused principals' job registration until `resume_at`.

8. **`envoy.daily_digest.engagement.LowEngagementTracker`** — per spec § Low-engagement fallback. Tracks per-principal "digest opened" events (an "open" is an inbound message from the user containing a Digest reply OR a click on the Digest's reply prompt). State stored in Trust store as `digest:opens:{principal_id}` with rolling 3-week window. When `<2 opens/week × 3 consecutive weeks`, the renderer's `form` field flips from `rich` to either `compact` (3-line) or `event_only` (fires only on Grant Moment pending OR budget > 80%). The flip emits an advisory `LowEngagementFallbackTriggered` Ledger entry (spec § Error taxonomy line 75; advisory not blocking).

9. **`envoy.daily_digest.duress.DuressBannerReader`** — per spec § Shadow-segment post-duress surface. Reads the local-only shadow segment via shard 5's `TrustLineageAdapter.read_shadow_segment(principal_id, since)`. If unread `DuressUnlockEvent` exists at digest time, the renderer:
   - Sets `duress_banner.present = True` and `duress_banner.shadow_event_ref = <ledger-entry-id>`.
   - **Routes the duress banner to PRIMARY CHANNEL ONLY** (per spec § Error taxonomy `DuressBannerSuppressedError` line 73 — T-018 defense). Non-primary channels get the standard digest WITHOUT the banner.
   - The primary-channel determination uses `TrustStoreAdapter.get_primary_channel(principal_id)` (shard 5; cross-references shard 16 § 3.2 H-03 primary-channel binding line 183-185).
   - Per `rules/event-payload-classification.md` Rule 1, the `shadow_event_ref` is routed through `format_record_id_for_event` before emission.

10. **`envoy.daily_digest.payload.DigestPayload`** — frozen dataclass matching `specs/daily-digest.md` § Schema lines 39–64 verbatim. 11 fields exactly. Per `rules/event-payload-classification.md` Rule 1, classified `record_id` + `principal_genesis_id` filtered at construction time.

11. **`envoy.daily_digest.errors`** — 5 typed errors per `specs/daily-digest.md` § Error taxonomy lines 68–76. Each subclasses `DailyDigestError`. Each error's emission path writes a `system_error` Ledger entry.

12. **`envoy.daily_digest.cli`** — `envoy digest today` (trigger now), `envoy digest pause [--days N]`, `envoy digest resume`, `envoy digest schedule --hour H [--tz IANA_TZ]`. Click/argparse entry point per shard 19 (pipx distribution).

### 3.3 Boundary the content schema (key design question #3)

Per the prompt: "The Daily Digest produces a unified content payload that adapters render channel-natively. Boundary the content schema."

The boundary IS the spec § Schema (digest/1.0) — 11 fields. Adapters render but do NOT mutate. Specifically:

- `DigestRenderer` produces a `DigestPayload` instance.
- `PerChannelFanout` calls `adapter.send_digest(target_principal_id=p, digest=payload, timeout_seconds=10)` — the SAME `payload` instance per channel.
- Each `ChannelAdapter.send_digest()` reads the payload's `summary` and renders into its channel-native form per `specs/channel-adapters.md` § Capabilities + the digest spec § Channel-adaptive rendering line 33:
  - Email/Web (rich form): full `summary` rendering with attachments + inline buttons via Web Block-Kit-equivalent.
  - Telegram/Slack/Discord (rich form): full `summary` + inline keyboard / Block Kit / Components for `pending_grants` quick-actions.
  - SMS/WhatsApp (compact 10-line form): compressed `summary` per `RedactedFieldRenderError` discipline (drop classified rows + summary count).
  - CLI (compact form on `envoy digest today`).

The adapter does NOT modify payload fields; it only adapts rendering. The `form` field of the payload is an _advisory hint_ (`rich` / `compact` / `event_only`) the renderer set based on engagement state; the adapter is free to downgrade further (e.g. SMS adapter forces `compact` regardless).

### 3.4 Skipped-day back-fill (key design question #4, EC-3-load-bearing)

Per EC-3 acceptance gate: "Skipped days (e.g. user offline) MUST appear in the next-day digest as a back-fill, not be silently dropped." Per `rules/zero-tolerance.md` Rule 6 (Implement Fully): MUST work, not "usually."

The structural mechanism is the `BackfillTracker` (§ 3.2 item 6) plus the Ledger query window expansion. The contract:

1. Per principal-channel pair, the Trust store records `digest:last_success` = `(delivered_at, digest_id)` after every successful `send_digest()`.
2. On scheduler fire at time `T`, the tracker reads `last_success.delivered_at = T0` and queries the Ledger with `since = T0` (capped at `T - 7d` to bound query growth).
3. If `T - T0 > 24h + tolerance` (e.g. user offline yesterday), the digest's `summary.actions` / `refusals` / `pending_grants` arrays include entries from `[T0, T]` — i.e., the back-filled days' content is naturally aggregated into today's digest.
4. The digest's `summary` carries an explicit `back_fill_days: int` advisory field on the payload's metadata (NOT in the canonical `digest/1.0` schema; transmitted as a meta-hint to the renderer for UX purposes — "Welcome back! Here's what happened over the last N days." preamble).
5. The Tier 2 wiring test asserts the back-filled action entries appear in the next-day digest's `summary.actions` (§ 6.1 below).

**Critical: back-fill is NOT a separate pipeline; it is a query-window adjustment.** The same digest pipeline runs every day; on offline-recovery days the query window expands. This avoids parallel-pipeline drift.

### 3.5 Per-channel emission strategy (key design question #5)

**Phase 01: parallel fan-out with fault isolation.**

Sequential is rejected because:

- A single channel's 10s timeout would block all subsequent channels (worst case: 8 channels × 10s = 80s digest delivery window).
- A single channel's transient failure would prevent siblings from delivering, propagating one channel's outage into all others.

Pure parallel without fault isolation is rejected because:

- An exception in one fan-out task should NOT propagate up the scheduler's `await` and crash the digest job.

Parallel with fault isolation (`return_exceptions=True`):

- Each `adapter.send_digest()` runs concurrently via `asyncio.gather`.
- Exceptions are returned as values, not raised.
- The fanout iterates results: for each `SendReceipt`, write a `ritual_completion` Ledger entry; for each `Exception`, write a `system_error` Ledger entry; if ALL channels exception, raise `DigestDeliveryFailedError` per spec § Error taxonomy line 71.
- The next-day digest's "X missed deliveries" banner is computed from the Ledger query of yesterday's `system_error` entries scoped to digest delivery.

### 3.6 Pause / disable persistence (key design question #6)

Per § 3.2 item 7: pause state IS persisted in the Trust store (NOT in a parallel store; consistent with `rules/orphan-detection.md` Rule 1 hot-path discipline). Specifically:

- The Trust store key namespace `digest:pause:{principal_id}` with `{paused_at, resume_at, reason}`.
- Default pause duration: 7 days (Phase 01 disposition resolving spec § Open question 3).
- Pause survives process restart because the scheduler's `start()` calls `TrustStoreAdapter.list_kv(prefix="digest:pause:")` and skips paused principals' job registration.
- Resume happens automatically at `resume_at` (next scheduler fire after that timestamp picks up the principal); `envoy digest resume` writes `resume_at = now`.

### 3.7 What is explicitly NOT Envoy-new-code

- **The chat-completion wire-send** — `kaizen.providers.llm.<provider>.chat_async()` per shard 13 § 2.6. Envoy invokes via `EnvoyModelRouter.for_primitive("daily_digest")`.
- **The Ledger query primitive** — `EnvoyLedger.query()` per shard 6 § 4.
- **The per-channel rendering** — owned by each `ChannelAdapter.send_digest()` per shard 16 § 3.2.
- **The connection vault** — channel adapters resolve their own credentials at startup per shard 16 § 3.2 item 15. **Daily Digest does NOT directly involve `ConnectionVault`** (per the prompt's explicit note "Connection Vault (14) NOT directly involved (channel adapters handle their own creds)").
- **The pause-disable storage primitive** — `TrustStoreAdapter.set_kv / get_kv / list_kv` per shard 5; Envoy is a consumer, not a maintainer of a parallel KV store.
- **The shadow-segment read primitive** — `TrustLineageAdapter.read_shadow_segment` per shard 5; consumed read-only.
- **`OrchestrationRuntime` strategy machinery** — verified disposition (b) per § 2.3; Phase 01 digest is a single-actor flow, no strategy needed. Phase 02+ may opt into `OrchestrationRuntime.sequential()` if the digest grows multi-agent.
- **Multi-device merge / sync** — per `00-inheritance-from-phase-00.md` § 6 invariant #1 single-device Phase 01.

---

## 4. Class structure sketch (interfaces only — no implementation)

Module path (Envoy-side, proposed): `envoy.daily_digest`.

```python
# envoy/daily_digest/__init__.py
from envoy.daily_digest.service import DailyDigestService
from envoy.daily_digest.payload import DigestPayload, DigestSummary, DuressBanner
from envoy.daily_digest.scheduler import DigestScheduler
from envoy.daily_digest.aggregator import LedgerAggregator
from envoy.daily_digest.renderer import DigestRenderer
from envoy.daily_digest.fanout import PerChannelFanout
from envoy.daily_digest.backfill import BackfillTracker
from envoy.daily_digest.pause import PauseDisableState
from envoy.daily_digest.engagement import LowEngagementTracker
from envoy.daily_digest.duress import DuressBannerReader
from envoy.daily_digest.errors import (
    DailyDigestError,
    DigestDeliveryFailedError,
    DuressBannerSuppressedError,
    RedactedFieldRenderError,
    LowEngagementFallbackTriggered,
    DigestSkippedTooLongWarning,
)

__all__ = [
    "DailyDigestService",
    "DigestPayload", "DigestSummary", "DuressBanner",
    "DigestScheduler", "LedgerAggregator", "DigestRenderer",
    "PerChannelFanout", "BackfillTracker", "PauseDisableState",
    "LowEngagementTracker", "DuressBannerReader",
    "DailyDigestError",
    "DigestDeliveryFailedError",
    "DuressBannerSuppressedError",
    "RedactedFieldRenderError",
    "LowEngagementFallbackTriggered",
    "DigestSkippedTooLongWarning",
]
```

```python
# envoy/daily_digest/payload.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

@dataclass(frozen=True)
class DuressBanner:
    """Per specs/daily-digest.md § Schema lines 50-53."""
    present: bool
    shadow_event_ref: Optional[str]  # ledger-entry-id; None if no duress event

@dataclass(frozen=True)
class DigestSummary:
    """Per specs/daily-digest.md § Schema lines 54-60. 5 fields."""
    actions: tuple              # tuple[dict] with ledger_id, summary, outbox_items
    refusals: tuple             # tuple[dict] with ledger_id, reason_code
    spend: dict                 # current_microdollars, monthly_ceiling_microdollars
    pending_grants: tuple       # tuple[dict] with grant_id, summary
    planned_today: tuple        # tuple[dict] with intent_id, summary

@dataclass(frozen=True)
class DigestPayload:
    """Per specs/daily-digest.md § Schema lines 39-64. 11 fields exactly."""
    schema_version: str  # "digest/1.0"
    digest_id: str       # uuid-v7
    principal_genesis_id: str  # sha256:... routed through format_record_id_for_event
    scheduled_for: str   # iso8601
    delivered_at: Optional[str]  # iso8601 | None
    channel_id: str
    form: Literal["rich", "compact", "event_only"]
    duress_banner: DuressBanner
    summary: DigestSummary
    user_reply: Optional[str]
    receipt_hash: str    # sha256:... canonical-JSON over payload-minus-receipt_hash

# envoy/daily_digest/service.py
class DailyDigestService:
    """Facade. Per rules/orphan-detection.md Rule 1 + facade-manager-detection.md Rule 3:
    explicit dependencies; production call site in envoy.runtime.bootstrap.start_daily_digest_scheduler."""

    def __init__(
        self, *,
        ledger: "EnvoyLedger",
        model_router: "EnvoyModelRouter",
        channel_adapters: dict[str, "ChannelAdapter"],
        trust_store: "TrustStoreAdapter",
        trust_lineage: "TrustLineageAdapter",
        classification_policy: Optional[object] = None,
    ) -> None: ...

    async def start(self) -> None:
        """Initialize scheduler. Reads pause state from trust_store, registers
        cron jobs for non-paused principals, starts apscheduler.AsyncIOScheduler."""

    async def stop(self, drain_timeout_seconds: int = 5) -> None: ...

    async def trigger_now(self, principal_id: str) -> "DigestPayload":
        """CLI-callable for `envoy digest today`. Bypasses cron; runs the
        aggregate→render→fanout pipeline immediately."""

    async def pause(self, principal_id: str, *, duration_days: int = 7,
                    reason: str = "user_requested") -> None: ...
    async def resume(self, principal_id: str) -> None: ...

    async def schedule(self, principal_id: str, *, hour: int,
                       timezone: str = "UTC") -> None:
        """Update the principal's digest schedule. Default tz=UTC per § 7
        Phase 01 Option A; Option B (user-local IANA) is shard 22 disposition."""

# envoy/daily_digest/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

class DigestScheduler:
    """Wraps apscheduler.AsyncIOScheduler. Per principal, registers a
    CronTrigger(hour=user_hour, timezone=user_tz)."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._jobs: dict[str, "Job"] = {}  # principal_id → Job

    def register(self, principal_id: str, *, hour: int, timezone: str,
                 callback: "Callable[[], Awaitable[None]]") -> None: ...
    def unregister(self, principal_id: str) -> None: ...
    def start(self) -> None: ...
    async def stop(self, drain_timeout_seconds: int = 5) -> None: ...

# envoy/daily_digest/aggregator.py
class LedgerAggregator:
    """Queries EnvoyLedger for the digest's content sections."""

    def __init__(self, *, ledger: "EnvoyLedger",
                 classification_policy: Optional[object] = None) -> None: ...

    async def aggregate(self, *, principal_id: str, since: datetime,
                        until: datetime) -> "DigestSummary":
        """Returns DigestSummary with actions / refusals / spend /
        pending_grants / planned_today. Per rules/event-payload-
        classification.md Rule 1, every record_id is routed through
        format_record_id_for_event before placement."""

# envoy/daily_digest/renderer.py
class DigestRenderer:
    """Constructs DigestPayload from DigestSummary + back-fill state +
    duress-banner state. Computes receipt_hash via shared canonical-JSON."""

    def __init__(self, *, model_router: "EnvoyModelRouter",
                 ledger: "EnvoyLedger") -> None: ...

    async def render(self, *, principal_id: str, channel_id: str,
                     summary: "DigestSummary",
                     duress_banner: "DuressBanner",
                     form: Literal["rich", "compact", "event_only"],
                     scheduled_for: datetime,
                     back_fill_days: int) -> "DigestPayload": ...

# envoy/daily_digest/fanout.py
class PerChannelFanout:
    """Parallel fan-out with fault isolation. asyncio.gather(*[...],
    return_exceptions=True). One ritual_completion Ledger entry per success;
    one system_error per failure; DigestDeliveryFailedError if all fail."""

    def __init__(self, *, channel_adapters: dict[str, "ChannelAdapter"],
                 ledger: "EnvoyLedger") -> None: ...

    async def emit(self, *, principal_id: str, payload: "DigestPayload",
                   active_channel_ids: list[str],
                   timeout_seconds: int = 10) -> dict[str, "SendReceipt | Exception"]: ...

# envoy/daily_digest/backfill.py
class BackfillTracker:
    """Per-channel last-successful-emission state in Trust store. Bounds
    Ledger query at 7d to prevent unbounded growth on chronic-offline
    principals. Implements EC-3 acceptance gate: skipped days appear in
    next-day digest as back-fill, not silently dropped."""

    BACKFILL_HORIZON_DAYS: ClassVar[int] = 7

    def __init__(self, *, trust_store: "TrustStoreAdapter") -> None: ...

    async def record_success(self, *, principal_id: str, channel_id: str,
                             receipt: "SendReceipt", digest_id: str) -> None: ...

    async def query_window(self, *, principal_id: str, channel_id: str,
                           scheduled_for: datetime) -> tuple[datetime, int]:
        """Returns (since, back_fill_days). since = max(last_success,
        scheduled_for - BACKFILL_HORIZON_DAYS)."""

# envoy/daily_digest/pause.py
class PauseDisableState:
    """Trust-store-backed pause state. Survives process restart."""

    DEFAULT_PAUSE_DAYS: ClassVar[int] = 7
    SKIP_TOO_LONG_THRESHOLD_DAYS: ClassVar[int] = 30

    def __init__(self, *, trust_store: "TrustStoreAdapter") -> None: ...

    async def pause(self, principal_id: str, *, duration_days: int = 7,
                    reason: str = "user_requested") -> None: ...
    async def resume(self, principal_id: str) -> None: ...
    async def is_paused(self, principal_id: str, *, now: datetime) -> bool: ...
    async def list_paused(self) -> list[str]: ...
    async def is_skip_too_long(self, principal_id: str, *,
                               now: datetime) -> bool: ...

# envoy/daily_digest/engagement.py
class LowEngagementTracker:
    """Per-principal opens-per-week rolling 3-week window. Trust-store-
    backed. Triggers form downgrade rich → compact / event_only."""

    LOW_OPEN_THRESHOLD_PER_WEEK: ClassVar[int] = 2
    LOW_ENGAGEMENT_WEEKS: ClassVar[int] = 3

    def __init__(self, *, trust_store: "TrustStoreAdapter",
                 ledger: "EnvoyLedger") -> None: ...

    async def record_open(self, principal_id: str, *, opened_at: datetime) -> None: ...
    async def select_form(self, principal_id: str, *,
                          now: datetime) -> Literal["rich", "compact", "event_only"]: ...

# envoy/daily_digest/duress.py
class DuressBannerReader:
    """Reads local-only shadow segment via TrustLineageAdapter. Routes the
    duress banner to PRIMARY CHANNEL ONLY per spec § Error taxonomy
    DuressBannerSuppressedError + T-018 defense."""

    def __init__(self, *, trust_lineage: "TrustLineageAdapter",
                 trust_store: "TrustStoreAdapter") -> None: ...

    async def check(self, *, principal_id: str, channel_id: str,
                    since: datetime) -> "DuressBanner":
        """If unread DuressUnlockEvent exists AND channel_id matches the
        principal's primary channel, return DuressBanner(present=True,
        shadow_event_ref=<id>). Otherwise DuressBanner(present=False, ...)."""

# envoy/daily_digest/errors.py
class DailyDigestError(RuntimeError): ...
class DigestDeliveryFailedError(DailyDigestError): ...        # spec line 71
class DuressBannerSuppressedError(DailyDigestError): ...      # spec line 73; T-018
class RedactedFieldRenderError(DailyDigestError): ...         # spec line 74
class LowEngagementFallbackTriggered(DailyDigestError): ...   # spec line 75; advisory
class DigestSkippedTooLongWarning(DailyDigestError): ...      # spec line 76

# envoy/daily_digest/cli.py
def digest_main(argv: list[str]) -> int:
    """argparse / Click entry point.
    Subcommands:
      envoy digest today          # trigger_now
      envoy digest pause [--days N]
      envoy digest resume
      envoy digest schedule --hour H [--tz IANA_TZ]
    """
```

Per `rules/facade-manager-detection.md` Rule 3, every constructor takes its dependencies explicitly — no global lookup, no self-construction. Per `rules/orphan-detection.md` Rule 1, the facade `DailyDigestService` is the only top-level production attribute exposed; every other class is reached through it.

---

## 5. Integration points

### 5.1 With Envoy Ledger (shard 6) — content source AND ritual_completion writer

The Daily Digest is the **dominant Ledger reader** per shard 6 § 5.2 ("Daily Digest is the dominant READER — `EnvoyLedger.query(filter={types: [grant_moment, channel_connected, ...], since: yesterday_morning})`").

Read pattern: `LedgerAggregator.aggregate(principal_id, since, until)` calls `EnvoyLedger.query(filter, since, until)` for each summary section:

- `actions` ← entries of types `PhaseBRecord` (post-execution outcomes per shard 6 § 5.1 + `specs/ledger.md` § Two-phase signing) within the window.
- `refusals` ← entries of type `posture_change` with `decision: deny` OR `system_error` with refusal-class fault codes.
- `spend` ← Budget tracker live counter (shard 12) + `BudgetSnapshot` Ledger entries for monthly ceiling.
- `pending_grants` ← `grant_moment` entries with state `pending`.
- `planned_today` ← upcoming envelope-edits / scheduled-actions; Phase 01 minimum is empty list (planned_today populator is shard 19 / Phase 02; the field exists per spec for forward-compatibility).

Write pattern: `PerChannelFanout` writes one `ritual_completion` entry per successful channel send (per shard 6 § 5.1 "Daily Digest" row "ritual_completion"). The entry's content carries `digest_id`, `channel_id`, `form`, `delivered_at`, `receipt_hash` — sufficient for the EC-3 acceptance test ("scheduled Daily Digest fires at the user's local morning hour for ≥7 consecutive days") to verify consecutive emission via Ledger query.

The shard 6 § 5.3 invariant ("every Tier 2 test asserts byte-equality against fixtures generated against the locked shape") applies: the Daily Digest's `digest/1.0` schema is locked at Phase 01 release; deserialization in the EC-3 test asserts byte-stable canonical JSON.

### 5.2 With Channel adapters (shard 16) — outbound substrate

The unified `ChannelAdapter` ABC's `send_digest(target_principal_id, digest, *, timeout_seconds=10)` method per shard 16 § 3.2 item 1 is the outbound contract. Per shard 16 § 3.4 ("What is explicitly NOT Envoy-new-code"), the per-channel rendering is owned by each adapter; the Digest service produces a unified `DigestPayload` (the spec's `digest/1.0` schema) and each adapter translates to channel-native form.

Active-channel discovery: `TrustStoreAdapter.list_active_channels(principal_id)` returns the per-principal connected channel IDs. The `PerChannelFanout` iterates this list at fire time (NOT pre-computed at scheduler-register time, so dynamically-added channels participate in the next fire).

Capability-aware skipping: per shard 13 § 3.2's `EnvoyModelRouter.required_capabilities` pattern, the fanout MAY skip channels whose `ChannelCapabilities` cannot render any of the digest's content (e.g. the `event_only` form on a CLI channel that has no asynchronous push surface — Phase 02 concern; Phase 01 ships all 8 channel adapters render `compact` at minimum).

### 5.3 With Model adapter (shard 13) — text generation

`DigestRenderer` invokes `EnvoyModelRouter.for_primitive("daily_digest").chat_async([...])` for the natural-language portion of the digest's `summary`. Per shard 13 § 3.2 ("per-primitive default-model override"), `ENVOY_DIGEST_MODEL` env key selects a fast/cheap model (e.g. local Ollama `qwen2.5:7b` or DeepSeek `deepseek-chat`) since the digest is high-frequency.

Per shard 13 § 5.2 ("Daily Digest"), cost discipline is critical: cost per digest × 7 days × N channels is the cost-control surface. The Phase 01 `PRIMITIVE_MODEL_ENV_KEYS` map already includes `daily_digest` (shard 13 § 4 class structure). Per `rules/env-models.md` Absolute Directive 2, model name comes from `.env`, never hardcoded.

Per shard 13 § 3.4 stage 1 ("Token-budget check (T-094) — Phase 01"), the model response passes through `TokenBudgetFilter` against the envelope's `tool_output_budget_bytes`; truncation emits a Ledger entry. The digest's natural-language summary MUST fit within the envelope budget.

Fallback: if the LLM call fails (e.g. local Ollama not running, network outage on cloud provider), the renderer falls back to a deterministic template that pulls the structured `summary` fields directly into the digest payload without LLM-generated prose. Per `rules/zero-tolerance.md` Rule 3, the fallback is logged at WARN level (not silent), and a `system_error` Ledger entry is written.

### 5.4 With Trust store (shard 5) — schedule preferences AND state persistence

Trust store is the persistence layer for:

- **Per-principal digest schedule:** `digest:schedule:{principal_id}` = `{hour: int, timezone: str, primary_channel_id: str, channel_preferences: dict}`.
- **Pause state:** `digest:pause:{principal_id}` = `{paused_at, resume_at, reason}` (§ 3.2 item 7).
- **Back-fill state:** `digest:last_success:{principal_id}:{channel_id}` = `{delivered_at, digest_id}` (§ 3.2 item 6).
- **Engagement state:** `digest:opens:{principal_id}` = rolling 3-week opens count (§ 3.2 item 8).
- **Primary-channel binding:** `digest:primary_channel:{principal_id}` = channel_id (read by `DuressBannerReader`; cross-references shard 16 H-03 binding).

This is consistent with the shard 16 § 3.2 item 16 "STATE-STORE delegation" pattern: cross-channel state lives in Trust store; per-primitive services are clients.

### 5.5 With Connection Vault (shard 14) — NOT directly involved

Per the shard prompt explicit note: "Connection Vault (14) NOT directly involved (channel adapters handle their own creds)." The Daily Digest never resolves credentials directly; it dispatches `send_digest()` to channel adapters, which resolve their own bot tokens / API keys at adapter `startup()` per shard 16 § 3.2 item 15 `CredentialResolver`.

This is the structurally cleanest decomposition: the Digest service knows nothing about Telegram bot tokens; the Channel adapter knows nothing about ledger aggregation.

### 5.6 With Boundary Conversation (shard 8) — reply parsing

The user's inline reply to a digest ("no", "yes", "modify", "skip digest") arrives via the channel adapter's `receive_message()` AsyncIterator (shard 16 § 3.2 item 12 `InboundRouter`). The InboundRouter routes inbound messages based on the active session's state-machine position; when an inbound message correlates with a recently-delivered Digest (via `digest_id` / `session_id` linking), the message routes to the Daily Digest reply parser, NOT to the Boundary Conversation flow.

Phase 01 reply-parsing: structured-keyword matching (per spec § Open question 4 "natural-language reply vs structured commands; risk of misinterpretation"). Phase 01 disposition: keyword match `^(no|yes|modify|skip digest)\b` (case-insensitive); anything else routes to Boundary Conversation as a normal conversational turn. The natural-language extension is Phase 02.

### 5.7 With Authorship Score (shard 9) — read-only via Ledger

The digest's `posture_change` entries (when present) reference the principal's authorship-score state. Phase 01 read-only: Authorship Score (shard 9) emits `posture_change` entries; Daily Digest aggregates them via Ledger query. No bidirectional dependency.

### 5.8 With Grant Moment (shard 10) — read-only via Ledger; reply-route

The digest's `pending_grants` field aggregates `grant_moment` entries with state `pending` (per shard 6 § 5.1 row Grant Moment). User clicks on a digest's pending-grant button route via the InboundRouter into the Grant Moment orchestrator's M0→M4 state machine (shard 10 § 4) — the digest is the surfacing UI, not the resolver.

---

## 6. Tier 2 / Tier 3 test surface

Per `rules/orphan-detection.md` MUST Rule 1 + `rules/facade-manager-detection.md` MUST Rule 1 + Rule 2: every wired manager MUST have a Tier 2 wiring test that imports through the facade, constructs against real infrastructure, triggers a code path that calls a method on the manager, and asserts an externally-observable effect.

Per `rules/zero-tolerance.md` Rule 6 (Implement Fully): back-fill MUST work, not "usually." Per `rules/testing.md` § "Tier 2 (Integration): Real infrastructure recommended", no mocking at Tier 2.

### 6.1 Tier 2 wiring tests (real SQLite + real apscheduler + real channel adapters)

| Test file                                                                            | What it exercises                                                                                                                                                                                                                                                                                                                                                                                |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `tests/integration/test_daily_digest_service_wiring.py`                              | Per `rules/facade-manager-detection.md` Rule 2 naming: imports `from envoy.daily_digest import DailyDigestService`, constructs against real SQLite Trust store + real EnvoyLedger + real CLIChannelAdapter, calls `.start()` then `.trigger_now(principal_id)`, asserts a `ritual_completion` Ledger entry exists AND the CLI channel produced output. EC-3 minimum acceptance.                  |
| `tests/integration/test_digest_form_per_channel.py`                                  | Per `specs/daily-digest.md` § Test location line 89: trigger digest with each of CLI / Web / Telegram / Slack / Discord / WhatsApp / iMessage / Signal as the active channel; assert the per-channel `form` selection (rich / compact) renders correctly via the channel adapter's `send_digest()` Tier 2 fixture. Per shard 16 § 6.1's pattern.                                                 |
| `tests/integration/test_daily_digest_backfill_skipped_day.py`                        | **EC-3 LOAD-BEARING.** Construct service; mark `last_success.delivered_at = T-2d`; advance simulated time to `T0` (today); trigger digest; assert the resulting `DigestPayload.summary.actions` includes Ledger entries from the skipped day `[T-2d, T-1d]`. Asserts the back-fill MUST work (per `rules/zero-tolerance.md` Rule 6) — this is the structural defense against silent drop.        |
| `tests/integration/test_daily_digest_backfill_horizon_caps_at_7d.py`                 | Mark `last_success.delivered_at = T-30d`; trigger; assert query window is capped at `T-7d` (BACKFILL_HORIZON_DAYS); assert `back_fill_days` advisory metadata = 7 (not 30); assert `DigestSkippedTooLongWarning` fires per spec line 76 + `PauseDisableState.is_skip_too_long`.                                                                                                                  |
| `tests/integration/test_daily_digest_pause_resume_persists_restart.py`               | Pause principal; stop service; create new service instance against same Trust store; start; trigger cron-fire-time; assert digest does NOT fire for paused principal; advance time past `resume_at`; assert digest fires.                                                                                                                                                                        |
| `tests/integration/test_daily_digest_seven_consecutive_days.py`                      | **EC-3 LOAD-BEARING.** Per `02-mvp-objectives.md` line 54 ("≥7 consecutive days"). Use `apscheduler.virtual_clock` (or `freezegun`) to advance simulated time 7 days; assert 7 distinct `digest_id` values produced; assert 7 `ritual_completion` Ledger entries with monotonically increasing `delivered_at`; assert no day silently skipped.                                                   |
| `tests/integration/test_daily_digest_fanout_fault_isolation.py`                      | Configure 3 channels; force one to raise `SendTimeoutError`; assert siblings still deliver; assert one `system_error` Ledger entry per failed channel + one `ritual_completion` per successful channel; assert `DigestDeliveryFailedError` does NOT fire (only fires when ALL channels fail).                                                                                                    |
| `tests/integration/test_daily_digest_fanout_all_fail_raises.py`                      | Configure 3 channels; force ALL to raise transport errors; assert `DigestDeliveryFailedError` raises per spec line 71; assert next-day digest's payload includes "X missed deliveries" advisory.                                                                                                                                                                                                 |
| `tests/integration/test_daily_digest_duress_banner_primary_only.py`                  | Per `specs/daily-digest.md` § Test location line 91 + spec § Shadow-segment post-duress surface lines 35-37. Write a `DuressUnlockEvent` to shadow segment; trigger digest; assert primary channel's `DigestPayload.duress_banner.present == True`; assert non-primary channels' payloads have `duress_banner.present == False` (per spec § Error taxonomy `DuressBannerSuppressedError` T-018). |
| `tests/integration/test_daily_digest_low_engagement_fallback.py`                     | Per spec line 90 + § Low-engagement fallback. Simulate `<2 opens/week × 3 weeks` of engagement state; trigger digest; assert `form == "compact"` OR `form == "event_only"`; assert `LowEngagementFallbackTriggered` advisory Ledger entry written.                                                                                                                                               |
| `tests/integration/test_daily_digest_reply_parsing_no_yes_skip.py`                   | Per spec line 93 + § Interaction. Deliver digest; simulate user reply "no" (proceed); reply "yes" (apply); reply "skip digest" (pause); assert each parses correctly and routes through the InboundRouter (shard 16 § 3.2 item 12) to the digest reply handler.                                                                                                                                  |
| `tests/integration/test_daily_digest_classified_record_id_redaction.py`              | Per `rules/event-payload-classification.md` Rule 4: aggregate digest containing classified-PK entries; assert `DigestPayload.summary.actions[N].ledger_id` is `sha256:`-prefixed; assert raw classified value does NOT appear in `repr(payload)`.                                                                                                                                                |
| `tests/integration/test_daily_digest_tenant_id_persisted.py`                         | Per `rules/tenant-isolation.md` Rule 5: trigger digests for two principals across different tenants; assert each `ritual_completion` Ledger row carries `tenant_id` indexed.                                                                                                                                                                                                                     |
| `tests/integration/test_daily_digest_receipt_hash_canonical_json.py`                 | Per spec § Open question 5 (cross-channel byte-identity). Construct same `DigestPayload` from two processes; assert `receipt_hash` is identical; reuses the shard 6 canonical-JSON byte-identity discipline.                                                                                                                                                                                     |
| `tests/integration/test_daily_digest_apscheduler_cron_trigger_at_user_local_hour.py` | Per § 7 below + `journal/0003-GAP-budget-ceiling-timezone.md`. Phase 01 Option A: register CronTrigger with `timezone="UTC"`; assert fire happens at UTC hour. (Option B test — `timezone=<IANA>`; assert fire at user-local hour — added in Phase 02 if shard 22 selects Option B.)                                                                                                             |
| `tests/integration/test_daily_digest_pytest_xdist_safe.py`                           | Per `rules/testing.md` § Env-Var Test Isolation: env vars `ENVOY_DIGEST_MODEL`, `ENVOY_DIGEST_HOUR`, `ENVOY_DIGEST_TZ` mutated under module-scope `threading.Lock` per the `_env_serialized` fixture pattern. xdist-safe.                                                                                                                                                                        |

### 6.2 Tier 3 tests (cross-OS, real-LLM, real-channel)

| Test file                                                          | What it exercises                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/e2e/test_daily_digest_morning_delivery.py`                  | Per `specs/daily-digest.md` § Test location line 88 (Tier 3). Real apscheduler scheduled at fire-time; real channel adapter (CLI minimum; cloud channels gated by `pytest.mark.skipif` on credentials per shard 13's test discipline + `rules/testing.md` § "Test-Skip Triage Decision Tree" ACCEPTABLE infra-conditional skip). 7-day operating window simulated; asserts EC-3 acceptance gate.                       |
| `tests/regression/test_t019_habituation_low_engagement.py`         | Per spec line 92 + `specs/threat-model.md` T-019. Adversarial scenario: digest delivered 21 days; assert if user engagement <2/week × 3 weeks, fallback fires and reduces digest visual prominence (compact / event_only).                                                                                                                                                                                             |
| `tests/e2e/test_daily_digest_cross_channel_seven_day_coherence.py` | Per EC-3 acceptance gate ("rendering across all configured channels with content sourced from the Ledger"). Configure 4 channels; run 7-day simulation; assert every day's digest delivered to every channel; assert content coherence (same `digest_id`, same canonical-JSON `receipt_hash` per channel; per-channel `form` differs but `summary` content equivalent modulo `RedactedFieldRenderError` SMS dropping). |

### 6.3 Test surface NOT in Phase 01 (deferred)

- Multi-device digest reconciliation (a digest sent on Device A is not re-sent on Device B) — Phase 03 multi-device.
- Real-LLM digest summary quality benchmark (cassette-based per shard 13 § 6.2; Phase 02 cohort).
- Foundation Verified provider attestation enforcement on the digest's LLM call — Phase 02+ per shard 13 § 3.5.
- A2A messaging cross-principal digest (a household digest aggregating multiple principals) — Phase 03 per `specs/a2a-messaging.md` line 13.

---

## 7. Frozen-spec ambiguity check

Per `01-shard-plan.md` § 4 failure-mode protocol: if a primitive deep-dive surfaces a HIGH gap in the frozen spec, STOP the deep-dive; convene MUST-Rule-5b sweep before continuing.

This shard surfaces **ONE HIGH-severity ambiguity that cross-references journal/0003** (the timezone-basis gap from shard 12) and **THREE LOW-severity items resolved by Phase 01 disposition without spec edit**.

### 7.1 HIGH — timezone basis for "user's local morning hour" — CROSS-REFERENCES journal/0003

**Status:** HIGH (escalated). Phase 01 disposition: Option A (UTC + user-side display) for consistency with shard 12; **shard 22 to make the consolidated cross-shard decision.**

**Observation:** `specs/daily-digest.md` § Schedule (line 15) names "User-configured delivery time (default 8am local)." `specs/daily-digest.md` § Open question 1 (line 97) names "Default 8am local — across timezones in Shared Household, which household member's tz wins." But the spec is silent on the timezone basis for the single-principal case at the _implementation level_: is "8am local" stored as `(hour=8, tz="UTC")` and rendered in the user's browser locally, OR as `(hour=8, tz="Asia/Singapore")` driving the apscheduler cron directly?

**Cross-reference to `journal/0003`:** This is the SAME ambiguity surface as shard 12's `per_day_ceiling_microdollars` timezone basis. The two primitives have the same architectural choice:

- **Option A (UTC-only)** — Phase 01 minimum. Schedules fire at UTC hour regardless of user location. For a Singapore user with `hour=8` in their schedule, the digest fires at 8am UTC = 4pm Singapore — **visibly wrong UX**. Phase 02 ticket carries the user-local-time fix.
- **Option B (user-local IANA timezone)** — Phase 01 ideal. Adds `digest_schedule_timezone: str` field to the per-principal Trust-store key. CronTrigger uses the user's IANA timezone directly; fire happens at the user's local 8am.

**Why this is HIGHER UX impact than shard 12's budget ceiling:**

- Shard 12 budget ceiling is invisible most of the time; only the moment of ceiling-hit surfaces it.
- Daily Digest IS the visible morning ritual (BET-8 — "the new habit forms"). A digest that fires at 4pm local for a Singapore user is BET-8-falsifying — the user explicitly experiences the wrong-timezone UX every single day.

**Why this is HIGH not blocking:** EC-3's pre-declared acceptance gate ("scheduled Daily Digest fires at the user's local morning hour for ≥7 consecutive days") is technically satisfied by Option A IF the test cohort happens to be in UTC or near-UTC timezones. But `02-mvp-objectives.md` line 54's natural-language phrasing reads "user's local morning hour" — Option A satisfies the literal-spec cron-firing-at-scheduled-hour, NOT the natural-language EC-3 phrasing.

**Disposition (consistent with shard 12 + journal/0003):**

1. Phase 01 ships **Option A** as the zero-cost default; the apscheduler `CronTrigger` accepts `timezone="UTC"` and the principal's schedule stores `(hour=8, timezone="UTC")`. Tier 2 wiring tests assert UTC-basis behavior.
2. **Phase 01 acceptance gate softened** — the EC-3 7-day test runs in the test cohort's timezone; if cohort is non-UTC, the test asserts "scheduled hour fires for 7 consecutive days" (drops the "local morning" qualifier).
3. **Shard 22 escalation:** the timezone basis decision is shared with shard 12 + this shard. Shard 22 weighs the consolidated cost (Option B requires editing `specs/envelope-model.md` — `journal/0003` — AND `specs/daily-digest.md` per-principal schedule field) against the cost of the multi-session MUST Rule 5b sibling-redteam sweep.
4. **If the human selects Option B at shard 22:** the consolidated edit lands in one MUST Rule 5b sweep across both `specs/envelope-model.md` (financial dimension timezone field) AND `specs/daily-digest.md` (schedule timezone field). The 37-sibling re-derivation cost amortizes across both edits — total estimated cost ~3 sessions per `journal/0003` item 2 (one MUST Rule 5b sweep, not two).
5. **If the human selects Option A:** Phase 02 ticket carries both timezone fixes simultaneously.

**Consistency commitment with shard 12:** This shard's Option A recommendation MUST track shard 12's recommendation. If shard 22 selects Option B for budget tracking, this shard's disposition flips to Option B; if Option A, this shard's disposition stays Option A. Per `journal/0003` item 3, the "complete-and-escalate-to-shard-22" methodology is correct because Option A is Phase 01-acceptable.

**Per `01-shard-plan.md` § 4 strict reading:** this is HIGH-severity but the shard does NOT halt; instead, the disposition is recorded here AND the journal/0003 entry's existence is leveraged to avoid duplicating the gap entry. A new journal entry would be redundant with `journal/0003`; this section IS the cross-reference.

### 7.2 LOW — Shared Household timezone tie-break (spec § Open question 1)

`specs/daily-digest.md` § Open question 1 (line 97): "across timezones in Shared Household, which household member's tz wins." Phase 01 single-principal scope (per `00-inheritance-from-phase-00.md` § 6 invariant #1) makes Shared Household out of scope. Phase 03 multi-principal disposition. No escalation in Phase 01.

### 7.3 LOW — compact 10-line SMS budget sufficiency (spec § Open question 2)

`specs/daily-digest.md` § Open question 2 (line 98): "Compact 10-line SMS budget — sufficient for 80% of users vs information density." Phase 01 ships compact form at 10-line budget; sufficiency is empirically falsifiable in Phase 02 cohort (N>3 sessions). Phase 01 disposition: ship the 10-line budget; Phase 02 cohort feedback informs the next iteration. No spec edit needed; this is a calibration question.

### 7.4 LOW — "skip digest" duration default (spec § Open question 3)

`specs/daily-digest.md` § Open question 3 (line 99): "'skip digest' duration — temporary (1 week default?) vs indefinite." Phase 01 disposition: 7 days default (per § 3.2 item 7 PauseDisableState `DEFAULT_PAUSE_DAYS = 7`). 30-day threshold for `DigestSkippedTooLongWarning`. The 1-week default matches the spec's parenthetical hint. No spec edit needed; this is a Phase 01 implementation default that's spec-compatible.

### 7.5 LOW — reply parsing extensibility (spec § Open question 4)

`specs/daily-digest.md` § Open question 4 (line 100): "Reply parsing extensibility — natural-language reply vs structured commands; risk of misinterpretation." Phase 01 disposition: structured-keyword matching (per § 5.6 above). NL extension is Phase 02 (requires intent-vector classifier — same surface as shard 13's goal-drift Phase 04 deferral). No spec edit needed.

### 7.6 LOW — receipt_hash content (spec § Open question 5)

`specs/daily-digest.md` § Open question 5 (line 101): "Receipt_hash content — what bytes exactly; cross-channel byte-identity guarantee." Phase 01 disposition (§ 3.2 item 4): `receipt_hash = sha256(canonical_dumps(payload_minus_receipt_hash))` where `canonical_dumps` is shard 6's `envoy.ledger.canonical.canonical_dumps`. This satisfies cross-channel byte-identity by reusing the Ledger's canonical-JSON contract. No spec edit needed; this is a structural choice that's spec-compatible and reuses an existing primitive.

### 7.7 Conclusion

One HIGH-severity ambiguity; cross-references existing `journal/0003` rather than creating a new journal entry. Five LOW-severity items resolved via Phase 01 disposition without spec edit. The shard does NOT halt per `01-shard-plan.md` § 4 (Option A is a Phase 01-acceptable disposition; halting would block wave D for no benefit).

Per `journal/0003` item 3: methodology is "complete-and-escalate-to-shard-22." Shard 22 owns the consolidated cross-shard timezone-basis decision spanning shards 11 + 12.

---

## 8. Cross-references

### Frozen spec sources (DO NOT EDIT — `journal/0001` discipline)

- `specs/daily-digest.md` (lines 1–101) — primary spec
- `specs/channel-adapters.md` § Adapter contract / § Ritual delivery — `send_digest` outbound substrate (consumer)
- `specs/ledger.md` § Entry types lines 47–91 — content source AND `ritual_completion` writer
- `specs/trust-lineage.md` lines 136–137 — local-only shadow segment for duress banner
- `specs/budget-tracker.md` — spend / monthly_ceiling source (shard 12)
- `specs/threat-model.md` T-019 (habituation defense) + T-018 (duress banner primary-only)
- `specs/classification-policy.md` — `format_record_id_for_event` redaction discipline
- `specs/envelope-model.md` — `tool_output_budget_bytes` (used by TokenBudgetFilter on the digest's LLM call)

### Phase 00 inheritance

- `workspaces/phase-00-alignment/01-analysis/01-ux-rituals.md v2 §5` — daily-digest provenance source per `specs/daily-digest.md` line 9
- `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` item 22 (`OrchestrationRuntime` C-grade absent at 2026-04-21)
- `workspaces/phase-00-alignment/01-analysis/03-primitive-reconciliation.md` row 14 (OrchestrationRuntime cross-SDK reconciliation)
- `workspaces/phase-00-alignment/issues/manifest.md` ISS-26 (#602) — closure tracked per `03-kailash-py-mvp-readiness.md` § 2 row ISS-26

### Phase 01 sibling shards

- `workspaces/phase-01-mvp/01-analysis/03-kailash-py-mvp-readiness.md` § 3 row 8 (Daily Digest C → ?? verify) + § 5 verification protocol
- `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` § EC-3 (Daily Digest acceptance gate) + § BET-8 (habit formation)
- `workspaces/phase-01-mvp/01-analysis/06-envoy-ledger-implementation.md` § 5.1 (Daily Digest is dominant Ledger reader; writes ritual_completion) + § 5.2 (cross-primitive read consumers)
- `workspaces/phase-01-mvp/01-analysis/13-model-adapter-implementation.md` § 3.2 (per-primitive override — `ENVOY_DIGEST_MODEL`) + § 5.2 (Daily Digest cost discipline)
- `workspaces/phase-01-mvp/01-analysis/16-channel-adapters-implementation.md` § 3.2 item 1 (`send_digest` ABC method) + § 3.2 item 16 (cross-channel coherence delegation pattern) + § 5 integration map row Daily Digest
- `workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md` (shard 5; Trust store is the persistence substrate for digest schedule + pause + back-fill + engagement state)
- `workspaces/phase-01-mvp/01-analysis/12-budget-tracker-implementation.md` § 7 (timezone-basis ambiguity — same surface as this shard § 7.1)
- `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 2 (shard 11 placement) + § 4 (failure-mode protocol) + § 5 (Group D parallelization)
- `workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` — re-derivation discipline
- `workspaces/phase-01-mvp/journal/0003-GAP-budget-ceiling-timezone.md` — cross-referenced by § 7.1 for the timezone-basis ambiguity

### Verified upstream code (`~/repos/loom/kailash-py/`, 2026-05-03)

- `packages/kailash-kaizen/src/kaizen/orchestration/runtime.py` (1002 LOC) — OrchestrationRuntime strategy-driven multi-agent runtime; NO scheduling primitive
- `packages/kailash-kaizen/src/kaizen/orchestration/__init__.py` (72 LOC) — public re-exports per orphan-detection Rule 6
- `packages/kailash-kaizen/src/kaizen/trust/governance/budget_reset.py` line 38 docstring — "typically scheduled via cron/APScheduler" idiomatic upstream pattern (caller composes scheduling)
- `apscheduler` PyPI package (BSD-3-Clause, audited; transitively present in `kailash-kaizen` `.venv`) — Phase 01 scheduling substrate

### Closed upstream issues (verified 2026-05-03)

- terrene-foundation/kailash-py #602 — `OrchestrationRuntime` parity (closed 2026-04-25; **disposition (b) — partial; Envoy adds scheduling glue**)
- terrene-foundation/kailash-py #735 — `_execute_strategy` ThreadPoolExecutor contextvars fix (improves digest fan-out tenancy propagation)
- terrene-foundation/kailash-py #767 — nexus durability_middleware StreamingResponse drain (improves Web channel digest preview SSE)
- terrene-foundation/kailash-py #737 — Nexus WorkflowServer lifespan (improves channel adapter lifecycle hooks digest scheduler depends on)

### Rule citations

- `.claude/rules/specs-authority.md` Rule 4 (phase commands read specs before acting; this shard reads `specs/daily-digest.md` + 5 cross-spec dependencies by path + section) + Rule 5b (no spec edits at this shard)
- `.claude/rules/orphan-detection.md` Rule 1 (every facade has a production call site within 5 commits — `envoy.runtime.bootstrap.start_daily_digest_scheduler`) + Rule 2 (Tier 2 wiring tests) + Rule 6 (`__all__` exports)
- `.claude/rules/facade-manager-detection.md` Rule 1 (Tier 2 test naming convention `test_<lowercase_manager_name>_wiring.py`) + Rule 2 (test file naming) + Rule 3 (explicit framework dependency in `__init__`)
- `.claude/rules/zero-tolerance.md` Rule 4 (no workarounds; `apscheduler` is the supported scheduling substrate, not a workaround) + Rule 6 (Implement Fully — back-fill MUST work, not "usually")
- `.claude/rules/event-payload-classification.md` Rule 1 (single-point filter at the emitter — `LedgerAggregator` filters every `record_id` through `format_record_id_for_event` before placement) + Rule 4 (end-to-end test in `test_daily_digest_classified_record_id_redaction.py`)
- `.claude/rules/tenant-isolation.md` Rule 5 (audit rows persist `tenant_id`; ritual_completion entries inherit per shard 6)
- `.claude/rules/env-models.md` Absolute Directive 2 (`ENVOY_DIGEST_MODEL` from `.env`, never hardcoded; `OLLAMA_BASE_URL` etc. resolved through `LlmClient.from_env()` per shard 13)
- `.claude/rules/testing.md` § 3-Tier Testing (Tier 2 real infrastructure recommended; Tier 3 cassette-based for cost-bearing) + § Test-Skip Triage Decision Tree (cloud-channel skip is ACCEPTABLE infra-conditional) + § Env-Var Test Isolation (xdist-safe via module-scope `threading.Lock`)
- `.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget (6 invariants; 5 cross-primitive references; within budget)

### Forward references (next shards / ECs)

- shard 19 — pipx distribution: dependency tree audit MUST include `apscheduler` (already transitive via `kailash-kaizen`); no new external dep audit needed
- shard 20 — build-sequence: shard 11 sits in Group D after Group A+B+C; consumes Ledger (6), Channel adapters (16), Model adapter (13), Trust store (5)
- shard 22 — spec gap analysis: timezone-basis ambiguity (§ 7.1) co-located with shard 12's same gap; consolidated decision belongs here
- shard 23/24 — redteam: assert no orphan facade (the `DailyDigestService` has a verified production call site per shard 19's `envoy.runtime.bootstrap`); assert per-channel fanout fault-isolation; assert back-fill works per `rules/zero-tolerance.md` Rule 6
- EC-3 (Daily Digest 7-day cadence + back-fill) — directly served by this shard
- BET-8 (the new habit forms — Daily Digest is the most-frequent ritual) — directly falsifiable via this shard's primitive

---

**Shard 11 closure:** This deep-dive identifies ~700 LOC of Envoy-new-code (scheduler glue + Ledger aggregator + content renderer + per-channel fan-out + back-fill state + pause-disable persistence + low-engagement tracker + duress banner reader + 5 typed errors + CLI). Phase 01 implementation depends on `apscheduler` (transitively present) + `kaizen.orchestration.OrchestrationRuntime` (verified disposition (b); not exercised in Phase 01) + shard 6 Ledger + shard 13 Model adapter + shard 16 Channel adapters + shard 5 Trust store. One HIGH spec ambiguity surfaced (timezone basis) that cross-references `journal/0003` — consolidated shard-22 decision recommended; Phase 01 ships Option A consistently with shard 12. EC-3 + BET-8 directly served.
