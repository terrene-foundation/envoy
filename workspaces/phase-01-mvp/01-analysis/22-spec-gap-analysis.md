# 22 — Spec Gap Analysis + Additive Spec Drafts

**Document role:** Aggregation point for every primitive deep-dive shard's §7 frozen-spec ambiguity finding (shards 4–19). Catalogs all HIGH / MED / LOW findings; pre-declares disposition (Phase 01 acceptable, Phase 02 deferral, additive new spec, or spec edit triggering MUST Rule 5b 37-sibling sweep); recommends two additive spec drafts (`specs/independent-verifier.md` + `specs/mvp-build-sequence.md`); escalates the one consolidated HIGH (timezone basis, shards 11+12) to the human at /analyze closure (shard 25).

**Date:** 2026-05-03 (shard 22 of /analyze; aggregation/synthesis wave F).
**Status:** DRAFT — load-bearing for shard 25 closure decision and any Phase 02 entry-checklist items.
**Discipline:** Every finding cites the source shard's §7 by path. Per `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`, Phase 01 cites Phase 00 (and Phase 01 sibling shards) by path + section; never paraphrase the underlying finding. Per `rules/specs-authority.md` MUST Rule 5b, this shard adds NEW additive spec files only — it does NOT edit any existing frozen spec. The single HIGH finding is presented to the human with two evidence-based options.

**Capacity check:** 1 aggregation doc + 2 additive spec drafts. No load-bearing logic invariants — all input is already produced by shards 4–19. Within `rules/autonomous-execution.md` § Per-Session Capacity Budget.

---

## 1. Method and discipline

### 1.1 What this shard does

For each of the 16 per-primitive deep-dive shards (4–19), this shard:

1. Reads the §7 "Frozen-spec ambiguity" section of the implementation deep-dive doc.
2. Records each finding (HIGH / MED / LOW) in the master table in §2 below with severity, affected spec, finding summary, and Phase 01 disposition.
3. For HIGH findings — frames Option A vs Option B with the falsifiability cost of each, and escalates to the human at shard 25.
4. For MED findings — picks one of three dispositions: (a) drafted as an ADDITIVE new spec file (this shard authors it; does NOT trigger MUST Rule 5b), (b) recorded as additive prose in this very document, or (c) Phase 02 deferral ticket.
5. For LOW findings — aggregates into a tracking list at the bottom of the doc; no action required for ship.

### 1.2 What this shard explicitly does NOT do

- **Does NOT edit any existing frozen `specs/*.md` file.** Edits trigger MUST Rule 5b: full 37-sibling re-derivation sweep across all FROZEN v1 specs. Phase 00's redteam took 6 rounds to converge from 7-CRIT to 0-CRIT/0-HIGH (per `specs/_index.md` § "Spec freeze discipline"). A spec edit is therefore at least 2–3 sessions of additional work; mandating it without the human's approval at shard 25 is BLOCKED.
- **Does NOT re-derive any primitive shard's analysis.** The primitive shard's §7 is the authoritative finding; this shard aggregates and dispositions, not re-analyzes.
- **Does NOT make the Option A vs Option B decision for the consolidated timezone HIGH.** That decision is the human's at shard 25. This shard surfaces the trade-off with concrete falsifiability evidence.

### 1.3 The MUST Rule 5b cost framing

Per `journal/0003-GAP-budget-ceiling-timezone.md` item 2 ("Specific data"):

> The 6-round Phase 00 redteam convergence on `specs/envelope-model.md` cost ~6 sessions. Adding a timezone field is a small addition, but the sweep cost is bounded by the spec's surface area, not by the size of the addition. A reasonable estimate is 2–3 sessions for the additive edit; if any sibling spec surfaces a HIGH cross-reference (e.g., `specs/ledger.md` audit-row timestamp encoding), that adds another round.

Per `rules/specs-authority.md` MUST Rule 5b origin paragraph: a previous narrow-scope sweep produced "14/14 green" APPROVE on edited specs; the subsequent full-sibling sweep found 9 HIGH cross-spec drift findings in specs the edit never touched. The full-sibling sweep is therefore not theoretical overhead — it is the structural defense against silent cross-spec drift.

The cost framing for any spec EDIT is therefore: **base 2 sessions for the edit's redteam → 0–3 additional rounds depending on what cross-spec drift the full-sibling sweep surfaces → 2–5 sessions total**. Additive spec FILES (this shard's preferred disposition) cost zero sibling re-derivation per Rule 5b explicitly.

---

## 2. Master findings table — every primitive shard's §7

Format: shard / primitive / severity / spec affected / finding summary (1-line; full text lives in the source shard) / Phase 01 disposition / Phase 02+ track.

| Shard | Primitive                   | Sev                   | Spec affected                                                                | Finding (1-line)                                                                                                                                                                                                                                  | Phase 01 disposition                                                                                                                                                                                    | Phase 02+ track                                                                                                                     |
| ----- | --------------------------- | --------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 4     | Envelope compiler           | MED                   | `specs/envelope-model.md` § Field semantics                                  | `metadata.algorithm_identifier.cross_domain_rules` registry-version pin lifecycle: bump retroactive vs. envelope-pinned unspecified                                                                                                               | (b) recorded in §3 below as additive prose; Phase 01 implements envelope-pinned (matches `envelope_version` binding semantics)                                                                          | Phase 04 spec clarification — `## Open question` extension on `specs/envelope-model.md`                                             |
| 4     | Envelope compiler           | MED                   | `specs/envelope-model.md` § Algorithms § Authorship Score                    | Authorship Score computation timing: BEFORE or AFTER template imports fold in `imported_constraints[]` is unstated                                                                                                                                | (b) recorded in §3 below; Phase 01 implements AFTER (only authored constraints count toward score per `specs/authorship-score.md`)                                                                      | Phase 02 — `## Open question` extension on `specs/authorship-score.md`                                                              |
| 5     | Trust store                 | LOW                   | `specs/trust-lineage.md` § Algorithms                                        | `principal_id` vs `agent_id` terminology drift across `trust-lineage.md`, kailash-py `SqliteTrustStore.agent_id`, `posture-ladder.md` "principal"                                                                                                 | LOW; not blocking; Envoy adapter handles mapping                                                                                                                                                        | Phase 03 multi-principal redesign — natural opportunity to clean up                                                                 |
| 5     | Trust store                 | LOW                   | `specs/trust-lineage.md` § Schema                                            | algorithm_identifier wire shape during mint ISS-31 transition: `{"sig":..., "hash":..., "shamir":...}` (3-key) vs kailash-py `{"algorithm": "..."}` (1-key)                                                                                       | LOW; both forms valid until mint ISS-31; Envoy adapter wraps `_with_algorithm_id()` helper                                                                                                              | Phase 02 — track mint ISS-31 closure; update `_with_algorithm_id` to resolved wire shape                                            |
| 6     | Envoy Ledger                | LOW×7                 | `specs/ledger.md` + `specs/ledger-merge.md`                                  | 7 spec open-questions catalogued (Lamport vs VClock; per-segment keys Phase 04; verifier language; CRDT thresholds; device_id derivation; etc.)                                                                                                   | All LOW; spec already explicit on Phase 03/04 timing; no Phase 01 action                                                                                                                                | Phase 03+ as spec already pre-declares                                                                                              |
| 7     | Independent verifier        | MED×3                 | `specs/ledger.md` lines 588–599                                              | (a) bundle wire format unspecified; (b) trust-anchor protocol unspecified; (c) verifier-internal error taxonomy not enumerated                                                                                                                    | (a) **NEW additive spec `specs/independent-verifier.md` — drafted in this shard's deliverable §5**                                                                                                      | Spec lives forward; Phase 02 may add Foundation key registry forward-references                                                     |
| 8     | Boundary Conversation       | MED                   | `specs/boundary-conversation.md` § Duration + EC-1                           | 15-minute pacing target vs EC-1 25-minute acceptance gate vs first-time-user empirical reality — which metric is load-bearing?                                                                                                                    | (b) recorded in §3 below; Phase 01 ships (c) BOTH — 25min ceiling per session as ship gate, 15min median as Phase 02 telemetry-driven target                                                            | Phase 02 — telemetry informs whether `specs/boundary-conversation.md` § Duration needs sharpening                                   |
| 8     | Boundary Conversation       | LOW×2                 | `specs/boundary-conversation.md` § Open questions                            | State-resume across machine boundary (line 78); S5 first-task corpus diversity (line 79)                                                                                                                                                          | Both are spec-acknowledged open questions; Phase 02/03 disposition                                                                                                                                      | Phase 02 (corpus); Phase 03 (multi-device pairing)                                                                                  |
| 9     | Authorship Score            | LOW                   | `specs/posture-ladder.md` § Canonical enum                                   | `PostureLevel(IntEnum)` (spec) vs `TrustPosture(str, Enum)` (kailash-py provider) — wire-format aligned but integer values divergent                                                                                                              | LOW; wire format is load-bearing for BET-6, integer values are internal-comparison-only; Envoy uses provider class with `autonomy_level` dunder                                                         | Future spec annotation — integer values are illustrative-of-ordering-not-of-implementation                                          |
| 9     | Authorship Score            | LOW                   | `specs/posture-ladder.md` § Algorithm                                        | `PostureEvidence` shape divergence: spec ceremony-evidence shape vs kailash-py operational-evidence shape — same name, two concepts                                                                                                               | LOW; resolved at Envoy adapter layer by separating ceremony-evidence kwargs from operational-evidence dataclass                                                                                         | No spec action required; documentation polish only                                                                                  |
| 9     | Authorship Score            | LOW                   | kailash-py packaging                                                         | `SQLitePostureStore` not re-exported at package level — submodule import path required                                                                                                                                                            | LOW; Envoy uses submodule import; file as upstream convenience PR (gated per `rules/upstream-issue-hygiene.md`)                                                                                         | Upstream convenience PR; not Phase 01-blocking                                                                                      |
| 10    | Grant Moment                | MED×3                 | `specs/grant-moment.md` + cross-specs                                        | (1) violation-detection point unspecified across primitives; (2) signed-consent format clarification; (3) BC↔GM PlanSuspension composition                                                                                                        | All three are implementation latitude, not spec gaps; Phase 01 ships `OutOfEnvelopeDetector` + 3-artifact signed-consent + `PlanSuspensionBridge`                                                       | None — clean implementation contract, no spec edit                                                                                  |
| 11    | Daily Digest                | **HIGH**              | `specs/daily-digest.md` § Schedule + EC-3                                    | timezone basis for "user's local morning hour" unspecified — same ambiguity surface as shard 12 budget                                                                                                                                            | **CONSOLIDATED with shard 12; see §4 below — Option A (UTC, 0 sessions) is recommended Phase 01 disposition; Option B requires 3-session edit**                                                         | Phase 02 ticket carries Option B if human selects Option A at shard 25                                                              |
| 11    | Daily Digest                | LOW×5                 | `specs/daily-digest.md` § Open questions                                     | (1) Shared Household timezone tie-break; (2) compact 10-line SMS budget sufficiency; (3) "skip digest" duration; (4) reply parsing extensibility; (5) receipt_hash content                                                                        | All spec-acknowledged; Phase 01 picks defaults that match spec hints                                                                                                                                    | Phase 02 cohort feedback / Phase 03 multi-principal disposition                                                                     |
| 12    | Budget tracker              | **HIGH**              | `specs/budget-tracker.md` § Ceilings (lines 17–23)                           | timezone basis for `per_day_ceiling_microdollars` and `per_month_ceiling_microdollars` reset boundaries unspecified — `journal/0003` HIGH                                                                                                         | **CONSOLIDATED with shard 11; see §4 below**                                                                                                                                                            | Same as shard 11 row above                                                                                                          |
| 12    | Budget tracker              | MED                   | `specs/budget-tracker.md` § Open question 4                                  | Reservation TTL default (60s vs 5min) — spec lists candidates but does not pick                                                                                                                                                                   | Phase 01 picks 60s (consistent with typical LLM tool-call latency); configurable                                                                                                                        | None — spec offers two defaults, picking one is implementation latitude                                                             |
| 12    | Budget tracker              | LOW×2                 | `specs/budget-tracker.md` § Open questions 1+2+3                             | Anomaly threshold calibration; high-velocity 5-calls/1min; non-USD microdollars Phase 02 i18n                                                                                                                                                     | Spec defaults shipped; telemetry will inform Phase 02 tuning                                                                                                                                            | Phase 02 calibration / i18n                                                                                                         |
| 13    | Model adapter               | HIGH-candidate (HELD) | `specs/model-adapter.md` § Purpose                                           | Chat-completion wire-send substrate not on `LlmClient` (deferred upstream per #740 spec-correction); legacy `kaizen.providers.llm.<provider>.chat_async()` is Phase 01 substrate                                                                  | HOLD, not escalated — spec does not name `LlmClient.complete()` specifically; legacy substrate IS the supported pattern, not a workaround                                                               | Phase 02+ — when upstream lands `LlmClient.complete()`, migrate; until then, two-surface wiring (Deployment+legacy chat) is correct |
| 13    | Model adapter               | LOW×2                 | `specs/model-adapter.md` § Open questions 2+3                                | Leak-canary corpus governance; self-hosted provider risk classification                                                                                                                                                                           | Both spec-acknowledged; Phase 04 + Phase 01-implementation-pre-declared                                                                                                                                 | Phase 04                                                                                                                            |
| 14    | Connection Vault            | LOW×5                 | `specs/connection-vault.md` § Open questions                                 | (1) Linux Secret Service availability fallback; (2) `service_identifier` registry strictness; (3) rotation_policy enforcement strength; (4) cross-device migration UX; (5) per-credential clearance vs envelope-scope expressiveness              | All Phase-01-acceptable defaults; nothing blocks ship                                                                                                                                                   | Phase 02 mobile / phase-02 service-identifier registry                                                                              |
| 15    | Shamir 3-of-5               | LOW×3                 | `specs/shamir-recovery.md` + kailash-py wrapper                              | (1) "Phase 00 crypto audit" scope ambiguity (which layer audited); (2) "24 BIP-39 words" terminology imprecision (should be "24 SLIP-0039 dictionary words"); (3) `back_up_vault_key` gate uncertainty pending mint ISS-37                        | (1) release gate at /redteam round 2 / /codify; (2) wording polish at /codify (no behavior change); (3) Phase 02 entry checklist                                                                        | Phase 02 entry checklist (mint ISS-31 / ISS-37 follow-on)                                                                           |
| 16    | Channel adapters            | MED×2                 | `specs/channel-adapters.md` lines 172–173 + `specs/a2a-messaging.md` line 13 | (1) iMessage / Signal feasibility (de-scope #1 candidate); (2) A2A messaging Phase 03 boundary cross-spec consequence                                                                                                                             | (1) ship 8-channel attempt; cohort-driven de-scope to 5 channels; (2) Phase 01 single-principal binding check, Phase 03 dual-signed verify                                                              | (1) Phase 02+ iMessage native + Signal Path A; (2) Phase 03 A2A primitives                                                          |
| 16    | Channel adapters            | LOW×5                 | `specs/channel-adapters.md` § Open questions                                 | (1) WhatsApp Foundation gateway pricing; (2) Signal Path B vs A; (3) cross-channel session continuity merge semantics; (4) Phase 04 17-channel matrix; (5) voice-channel transcription provenance                                                 | All Phase-01-acceptable defaults / spec-pre-declared                                                                                                                                                    | Phase 02+ as spec already pre-declares                                                                                              |
| 17    | Foundation Health Heartbeat | (DECISION)            | n/a                                                                          | DE-SCOPE decision (not a spec ambiguity) — implement vs defer to Phase 02 entry                                                                                                                                                                   | DE-SCOPED to Phase 02 entry; Phase 01 ships ~100 LOC stubs only (consent ledger entry type + DuressFlagLeakageRefusedError + 21-flag schema validator + 21 no-op emit hooks)                            | Phase 02 entry — stand up OHTTP KCS + Relay + STAR aggregator before consuming Heartbeat measurements                               |
| 18    | Runtime abstraction         | LOW×5                 | `specs/runtime-abstraction.md` § Open questions                              | (1) Protocol-vs-ABC encoding; (2) `AssembledPrompt.rendered_bytes` field-by-field tier classification; (3) feature-flag for kailash-rs-bindings adapter slot; (4) tool-call timing metadata promotion candidacy; (5) N3+N6 corpus filling cadence | All implementation-discipline questions, NOT spec-contract gaps; Phase 01 build chooses Protocol + canonical-form-excludes-`assembled_at` + feature-flag + spec-current-partition + corpus-as-published | Phase 02+ — N-vector corpus and tool-call timing are already Foundation Phase-02 cadence                                            |
| 19    | pipx distribution           | LOW×2                 | `specs/distribution.md` lines 18 + 28–34                                     | (1) "Offline first-run" claim semantics — no LLM bundled in pipx wheel; disposition (c) is "detect existing Ollama/llama.cpp/MLX on PATH"; (2) Phase 01 N=3 mirror coverage zero (PyPI only)                                                      | Disposition (c) preserves spec promise IF user has tool already; Phase 02 binary distribution adds N=3 mirror layer                                                                                     | Phase 02 distribution security primitives (N=3 mirror, key rotation, reproducible builds)                                           |

**Findings counts (across all 16 primitive shards):**

- **HIGH: 1 unique** — timezone basis (consolidated across shards 11 + 12; same architectural choice surface).
- **HIGH-candidate HELD: 1** — chat-completion substrate (shard 13; HELD with rationale, not escalated).
- **MED: 11** distributed across shards 4 (×2), 7 (×3), 8 (×1), 10 (×3), 12 (×1), 16 (×2). Of these, 3 (shard 7) become NEW additive spec `specs/independent-verifier.md`; the rest are recorded as additive prose in §3 below or are implementation latitude.
- **LOW: 39** distributed across most shards. All aggregated in §6 tracking list; no Phase 01 action required for any of them.

---

## 3. MED-severity dispositions — additive prose to this document

Per §1.1 disposition (b), MED findings whose disposition is "additive prose" are recorded here. Each is a spec-implementation contract pin that does NOT change the frozen spec but DOES capture the Phase 01 implementation choice for downstream agents (Phase 02 entry, future spec readers).

### 3.1 Envelope-pinned `metadata.algorithm_identifier.cross_domain_rules` registry version (shard 4 MED-1)

**Source:** `01-analysis/04-envelope-compiler-implementation.md` § 7 MED-1.

**Implementation contract:** when the Foundation publishes a new cross-domain-rules registry version, existing compiled `EnvelopeConfig` artifacts continue to evaluate against the version pinned at compile time (their `metadata.algorithm_identifier.cross_domain_rules: "envoy-registry:cross-domain-flows:v1"` field). Registry version BUMPS do NOT retroactively invalidate envelopes; do NOT trigger re-compile of existing DelegationRecords; do NOT trigger cascade revocation.

**Why this is the only structurally-coherent choice:** the alternative (retroactive invalidation on registry bump) would let Foundation infrastructure changes cascade-revoke user envelopes — directly contradicting `specs/envelope-library.md` § "Trust tiers" anti-Foundation-capture posture and the Foundation independence stance per `rules/independence.md`. Pinning at compile time is the only choice consistent with cascade-revocation NOT being triggered by Foundation infrastructure changes.

### 3.2 Authorship Score computation AFTER template imports (shard 4 MED-2)

**Source:** `01-analysis/04-envelope-compiler-implementation.md` § 7 MED-2.

**Implementation contract:** the `EnvelopeCompiler.compile(...)` pipeline computes `metadata.authorship_score` AFTER template imports fold in their `imported_constraints[]` lists, NOT before.

**Why this is the only choice consistent with BET-12:** per `specs/authorship-score.md`, only authored constraints count toward the score (template-imported constraints carry `authored=false`). If the compiler computed the score BEFORE template-import fold-in, a user could pad their score by importing many templates after their initial authoring — directly defeating BET-12 (governance-primary-surface palatability requires authorship-density to actually mean authorship-density). Computing AFTER ensures `authored_count / (authored_count + imported_count)` is the honest ratio.

### 3.3 Boundary Conversation 15min target vs 25min EC-1 ship gate (shard 8 MED)

**Source:** `01-analysis/08-boundary-conversation-implementation.md` § 7.1.

**Implementation contract:** Phase 01 ships interpretation **(c) Both** — 25min ceiling per session is the EC-1 ship gate (acceptance test asserts each first-time-user session ≤ 25min); 15min median is a release-summary observation informed by Phase 01 telemetry, NOT a ship-blocking assertion.

**Why this is consistent with frozen specs:** `specs/boundary-conversation.md` § Open questions item 1 explicitly names "empirical Phase 01 telemetry; if median exceeds 22min, simplify" — making the 15min target a Phase-02 simplification driver, not a Phase-01 hard ceiling. EC-1 is the operative ship gate per `02-mvp-objectives.md`.

**Phase 02 hook:** if Phase 01 telemetry shows the median consistently exceeds 22min across cohort sessions, Phase 02 invokes `specs/boundary-conversation.md` § Open questions item 1 simplification path — likely targeting S5 first-task corpus diversity (LOW) and S2 people-step compression.

### 3.4 Grant Moment 6-trigger detection point (shard 10 MED-1)

**Source:** `01-analysis/10-grant-moment-implementation.md` § 7.1.

**Implementation contract:** the `OutOfEnvelopeDetector` is the runtime-side interceptor that consolidates 5 of the 6 `why_asking` triggers (`envelope_violation`, `composition_rule`, `first_time`, `cross_principal`, `data_access_classifier`); the 6th (`velocity_raise`) is fired by the Budget tracker's threshold-callback per ISS-29 / kailash-py#603.

**Why this is the only structurally-coherent answer:** putting violation detection in the Envelope compiler couples authoring to evaluation; putting it in the Kaizen runtime couples agent execution to envelope semantics; the dedicated detector module mediates. The detector wraps the Kaizen `BaseAgent`'s tool-dispatch hot path. Per `rules/orphan-detection.md` Rule 1, the detector's call site lives inside the Kaizen tool-dispatch interceptor (Boundary Conversation runtime + every subsequent agent loop).

### 3.5 Grant Moment signed-consent as 3 wire artifacts (shard 10 MED-2)

**Source:** `01-analysis/10-grant-moment-implementation.md` § 7.2.

**Implementation contract:** the "signed-consent record" comprises THREE artifacts (NOT one):

1. Canonical-JCS-NFC-encoded `GrantMomentRequest` bytes signed by `delegation_key`.
2. Canonical-JCS-NFC-encoded `GrantMomentResult` bytes signed by `delegation_key` for approve / approve_and_author / modify; UNSIGNED for deny per `specs/grant-moment.md` line 51.
3. The `grant_moment` Ledger row referencing the above by `request_ref` + `result_ref`.

The signing key is `delegation_key` (the agent's per-session signing key), NOT Genesis. Genesis is Trust-Vault-backed; `delegation_key` is established at Boundary Conversation seeding via Genesis-signed `DelegationRecord`.

### 3.6 Grant Moment ↔ Boundary Conversation pause-resume bridge (shard 10 MED-3)

**Source:** `01-analysis/10-grant-moment-implementation.md` § 7.3.

**Implementation contract:** when a Grant Moment fires DURING Boundary Conversation, the `PlanSuspensionBridge` typed-event channel between BC's PlanSuspension state machine and GM's M0→M4 state machine is the composition primitive. Neither primitive reaches into the other's internals; the bridge IS the contract. Shard 8 ships the BC side; shard 10 ships the GM side.

### 3.7 Channel adapters de-scope #1 — cohort-driven, not architecture-time (shard 16 MED-1)

**Source:** `01-analysis/16-channel-adapters-implementation.md` § 7.1.

**Implementation contract:** Phase 01 ships ALL 8 adapter classes (CLI + Web + Telegram + Slack + Discord + WhatsApp + iMessage + Signal). The pre-declared de-scope #1 (drop iMessage + Signal) is a **runtime cohort-driven decision** triggered if EC-7 cohort fails (N=3 first-time-user sessions on iMessage and on Signal each fail to complete EC-1 within 25 minutes). It is NOT a Phase 01 architecture-time decision.

**Disposition rationale:** the four "clean" channels (Telegram, Slack, Discord, WhatsApp) have public APIs and ~150 LOC of Envoy-new-code each over a shared `WebhookTransport` + `WebhookSigner` shape; including them is essentially free. iMessage requires user-owned Mac + BlueBubbles bridge; Signal Phase 01 ships Path B (Group Link, weaker UX than 1:1). If cohort feedback shows these two channels break the EC-7 25-minute budget, dropping them is pre-declared per `02-mvp-objectives.md` § 5 row "EC-7" DEGRADE-ACCEPTABLE. The remaining 5-channel set still demonstrates BET-11 (channel-as-UI thesis) credibly.

### 3.8 Channel adapters Phase 01 single-principal binding check (shard 16 MED-2)

**Source:** `01-analysis/16-channel-adapters-implementation.md` § 7.2.

**Implementation contract:** Phase 01 channel adapters verify `InboundMessage.principal_genesis_id` matches the bot's known principal mapping (raise `PrincipalNotFoundError` on mismatch). Phase 01 does NOT invoke any A2A primitive (`specs/a2a-messaging.md` line 13: Phase 03 deliverable). Phase 03 will extend the adapter to invoke `kailash.eatp.A2A.verify(message)` before routing to recipient principal's runtime.

**Phase 01 test discipline:** `tests/integration/test_a2a_envelope_binding.py` and sibling A2A regression tests per `specs/a2a-messaging.md` § Test location lines 68–71 ship as `pytest.skip` placeholders with `reason="Phase 03 deliverable per specs/a2a-messaging.md line 13"`. Per `rules/testing.md` § Test-Skip Triage, these are ACCEPTABLE skips (Phase-deferred, named constraint).

---

## 4. The HIGH disposition — timezone basis (shards 11 + 12 consolidated)

### 4.1 The finding

**Source:** `01-analysis/12-budget-tracker-implementation.md` § 7.1 + `01-analysis/11-daily-digest-implementation.md` § 7.1; consolidated journal entry `journal/0003-GAP-budget-ceiling-timezone.md`.

**Spec gap:** `specs/budget-tracker.md` § Ceilings (lines 17–23) names `per_day_ceiling_microdollars` and `per_month_ceiling_microdollars` but does NOT specify the timezone basis for the day / month boundary. `specs/daily-digest.md` § Schedule (line 15) names "User-configured delivery time (default 8am local)" without specifying whether "local" means `(hour=8, tz="UTC")` rendered locally vs `(hour=8, tz="<IANA>")` driving the cron directly.

**Why HIGH and consolidated:** the two primitives surface the SAME architectural choice. A user in Singapore experiences:

- **Budget tracker (shard 12) impact:** the per-day ceiling resets at UTC midnight = 8 AM Singapore local. The user sees their daily budget reset mid-morning, observable but invisible most of the time (only the moment of ceiling-hit surfaces it).
- **Daily Digest (shard 11) impact:** the digest fires at UTC 8 AM = 4 PM Singapore local. The user explicitly observes the wrong-time digest **every single day** — directly affecting BET-8 ("the new habit forms"; the morning ritual is the highest-frequency Phase 01 ritual).

The two findings are the same root cause; consolidating them lets the human make ONE decision that resolves both.

### 4.2 The two options framed

#### Option A — UTC-only, Phase 01-acceptable, 0 sessions

**What ships in Phase 01:**

- Budget tracker stores `(hour=N, timezone="UTC")` schedules; per-day reset at UTC midnight regardless of user location.
- Daily Digest schedules its CronTrigger with `timezone="UTC"`; digest fires at UTC hour.
- EC-3 acceptance gate softened: "scheduled hour fires for 7 consecutive days" (drops the "user's local morning" qualifier from `02-mvp-objectives.md` line 54). The literal-spec assertion ("CronTrigger fires at the scheduled hour for 7 days") is satisfied; the natural-language EC-3 phrasing ("local morning hour") is accepted as Phase-02-deferred.
- Phase 02 ticket carries the user-local-time fix.

**Cost:** 0 sessions of additional analysis work. Ships on time.

**Pros:**

- Zero Phase 01 schedule impact. Every other shard 4–19 deep-dive is unaffected.
- Tier 2 / Tier 3 tests are simpler (UTC fixed; no DST handling; no IANA lookup).
- Budget tracker tests are deterministic (UTC boundary computations are cleaner than IANA + DST).

**Cons (the falsifiability cost):**

- **BET-8 directly affected.** The morning ritual is the highest-frequency Phase 01 ritual. A Singapore user (or any non-UTC cohort participant) sees the digest at 4 PM their local time every day — a visible, daily, "this thing doesn't understand me" UX surprise. EC-3's natural-language phrasing "user's local morning hour" is not satisfied for non-UTC cohort.
- **Cohort generalizability for EC-3 is degraded.** If the test cohort happens to be UTC or near-UTC, Option A passes EC-3 cleanly. But Phase 01 cohort is small (N=3 per channel × 8 channels = 24 onboardings per `02-mvp-objectives.md` EC-7) and may include non-UTC participants. The acceptance gate becomes "passes for UTC participants; defers for non-UTC" — a soft acceptance that obscures the actual UX failure.
- **Budget UX is also affected, but invisibly most of the time.** The Singapore user only notices their per-day ceiling reset at 8 AM local when they hit the ceiling at 9 AM and discover the budget already reset (and another reset is coming at 8 AM tomorrow). For most users this is indirect; for the ones who hit it, it's confusing.
- **Phase 02 carry-cost.** Phase 02 entry must include "fix timezone basis on both `specs/envelope-model.md` § Financial dimension and `specs/daily-digest.md` § Schedule" — at THAT future point the MUST Rule 5b sweep STILL costs ~3 sessions because the spec edits are still required at Phase 02. Option A defers, does not eliminate, the cost.

#### Option B — IANA timezone field, Phase 01 ideal, ~3 sessions of MUST Rule 5b sweep

**What ships in Phase 01:**

- `specs/envelope-model.md` § Financial dimension adds `per_day_ceiling_timezone: str` field (IANA timezone identifier, e.g. `"Asia/Singapore"`).
- `specs/daily-digest.md` § Schedule adds `digest_schedule_timezone: str` field on the per-principal schedule.
- Boundary Conversation collects user's IANA timezone at S6 (or alongside an existing question — "what time zone are you in?") and stores it in `EffectiveEnvelope.financial.per_day_ceiling_timezone` AND `digest:schedule:{principal_id}.timezone`.
- Budget tracker reads `EffectiveEnvelope.financial.per_day_ceiling_timezone` and computes per-day boundary in user-local time.
- Daily Digest registers CronTrigger with `timezone=<user IANA>`; fire happens at user's local 8am.
- EC-3 acceptance gate satisfied by literal natural-language phrasing.

**Cost:** ~3 sessions of analysis + redteam work, distributed as:

- Session 1: spec edits to `specs/envelope-model.md` + `specs/daily-digest.md`; cross-spec consumer updates (`specs/budget-tracker.md` may need a mention; `specs/data-model.md` per-principal schedule schema may need a field).
- Session 2: full-sibling redteam sweep across all 37 frozen specs per MUST Rule 5b. Anticipated cross-references that may surface as HIGH or MED:
  - `specs/ledger.md` audit-row timestamp encoding — does the timezone field affect canonical-JSON byte-identity of audit entries? (Likely no — timestamps are still UTC-encoded ISO 8601 microsecond-padded; the timezone field is metadata, not part of the timestamp.)
  - `specs/data-model.md` Trust Vault per-principal schedule schema — needs the field added.
  - `specs/runtime-abstraction.md` E1–E7 conformance vectors — does any vector exercise per-day ceiling computation that needs an IANA tz? (Likely no for E1–E7; possibly yes for any future per-day-budget vector.)
  - `specs/foundation-health-heartbeat.md` 21-flag schema — `opened_daily_digest_this_week` flag's "this week" semantics — does it depend on user-local week boundary? (Possibly; if so, this is a small clarification, not a redesign.)
- Session 3: redteam round 2 if round 1 surfaces any HIGH; Phase 02-entry-checklist drafting.

If the round-1 redteam surfaces 0 HIGH cross-spec drift, Session 3 is unnecessary and total cost is ~2 sessions.

**Pros:**

- BET-8 falsifiability preserved. The Singapore user sees their morning digest at 8am Singapore — the morning ritual works.
- EC-3's natural-language acceptance gate is satisfied directly.
- Budget tracker UX matches user mental models (per-day ceiling resets at user-local midnight).
- Phase 02 builds on a consistent base; no future timezone-basis redesign needed.
- Implements the "user authors the timezone explicitly during Boundary Conversation" pattern from shard 12 § 7.1 Option C — natural extension of the existing authoring ritual.

**Cons:**

- 3 sessions of session-cost spent on a single architectural choice. Phase 01 ship date slips by ~2–3 sessions.
- Sibling specs may surface unexpected cross-references; there is non-zero risk a HIGH finding emerges that requires more rounds.
- Two specs change atomically (`specs/envelope-model.md` + `specs/daily-digest.md`) — partial changes are NOT acceptable; the redteam must validate both edits together or neither.
- DST handling complicates Tier 2 tests slightly (the 25-hour day in spring-forward; the 23-hour day in fall-back). Mitigated by `apscheduler` + `zoneinfo` (Python 3.11+ stdlib) handling DST natively.

### 4.3 The recommendation

This shard recommends **Option B**, with the 3-session cost amortized across both spec edits in a single MUST Rule 5b sweep. The evidence:

1. **BET-8 is the highest-frequency Phase 01 ritual.** Per `02-mvp-objectives.md` EC-3, the digest fires every day for 7 consecutive days; per `specs/daily-digest.md`, this is the morning ritual. Wrong-timezone behavior surfaces every single day.
2. **EC-3's natural-language phrasing matters.** `02-mvp-objectives.md` line 54: "scheduled Daily Digest fires at the user's local morning hour for ≥7 consecutive days." Option A redefines "user's local morning hour" to "scheduled hour in UTC" — a stretching of the operational definition that erodes the acceptance gate's structural meaning.
3. **The Phase 02 carry-cost is non-zero under Option A.** Per §4.2 Option A Cons, Phase 02 entry STILL requires the timezone-basis fix and STILL incurs the ~3-session MUST Rule 5b cost. Option A does not eliminate the cost; it defers it. Doing the work in Phase 01 amortizes cleanly; deferring incurs a Phase 02-entry-checklist item that displaces other Phase 02 work.
4. **Cohort generalizability for EC-3 is preserved.** Option B works for Singapore, San Francisco, London, Auckland — every cohort participant sees their morning digest at their local morning. The acceptance gate is straightforwardly met.
5. **Implementation cost is bounded.** Two field additions (one per spec). `apscheduler` + `zoneinfo` handle DST. Tier 2 tests parameterize on tz. Tier 3 tests can be tz-agnostic (wall-clock fire-at-scheduled-hour).
6. **Sibling-spec drift risk is bounded.** The timezone field is metadata; canonical-JSON byte-identity is preserved (timestamps remain UTC-encoded ISO 8601). The most likely cross-spec surface is `specs/data-model.md` (per-principal schedule schema field addition) and a possible `specs/foundation-health-heartbeat.md` clarification of "this week" semantics. Both are small additions, not redesigns.

**However:** the recommendation is NOT a decision. The decision is the human's at shard 25 closure. This shard surfaces the trade-off; the human owns the Phase 01 schedule budget and the recommendation accept/reject.

If the human selects **Option A**, a Phase 02 entry-checklist item is recorded and shipped per §6 below. The Phase 01 implementation proceeds on the UTC-default; per-shard Tier 2 tests use UTC fixtures; EC-3 acceptance is asserted as "scheduled hour fires for 7 consecutive days" without the local-morning qualifier.

If the human selects **Option B**, this shard's deliverable spawns a follow-up "spec-edit shard" as the next /analyze action — which is the MUST Rule 5b sweep itself, 2–3 sessions of work. Per `01-shard-plan.md` § 4 failure-mode protocol, the spec edit goes through full-sibling redteam economics; this shard does NOT ship the edit inline.

### 4.4 Cross-shard consistency commitment

If the human selects Option B, the consolidated edit lands in ONE MUST Rule 5b sweep across both `specs/envelope-model.md` (financial dimension timezone field) AND `specs/daily-digest.md` (schedule timezone field). The 37-sibling re-derivation cost amortizes; total estimated cost remains ~3 sessions per `journal/0003` item 2. Two parallel single-spec sweeps would NOT amortize (each would trigger its own full-sibling re-derivation).

If the human selects Option A, both shards 11 and 12 implementation deep-dives are already written assuming Option A as the Phase 01 default; no shard rewrite is needed.

---

## 5. Additive new spec — `specs/independent-verifier.md` (shard 7 MED ×3)

**Source:** `01-analysis/07-independent-verifier-design.md` § 7.2 (formal recommendation to draft at this shard).

**Per `rules/specs-authority.md` MUST Rule 5b:** NEW spec files do NOT trigger 37-sibling re-derivation. The draft is additive only, low-cost, no convergence risk. This shard's deliverable Doc 2 (the spec file itself, written to `specs/independent-verifier.md` outside this analysis doc) closes shard 7 § 7.2's three MED ambiguities (bundle wire format, trust-anchor protocol, verifier-internal error taxonomy) without editing `specs/ledger.md`.

The draft is at `specs/independent-verifier.md`. See that file for the canonical spec content. Cross-references from `specs/_index.md` and `specs/ledger.md` (both load-bearing for the verifier) are NOT edited at this shard — `specs/_index.md` is the manifest and Phase 02 may add the row entry through `/codify` proposal flow per `rules/artifact-flow.md`. Adding the row at this shard would constitute an EDIT to `specs/_index.md` and trigger Rule 5b. This is a deliberate scoping choice; the shard 25 closure may surface it as a tracked Phase 02 item.

---

## 6. Additive new spec — `specs/mvp-build-sequence.md` (recommended per inheritance map § 5.4)

**Source:** `00-inheritance-from-phase-00.md` § 5.4: "Identified via gap analysis in shard 12 ... `specs/mvp-build-sequence.md` (probable) — captures Phase 01 build order as authoritative reference."

**Per MUST Rule 5b:** additive only; does not trigger sibling re-derivation.

**Why this is shard 22's responsibility, not shard 20's:** shard 20 produces `02-plans/01-build-sequence.md` (a workspace plan, in `workspaces/phase-01-mvp/02-plans/`). That document is process-side per `rules/specs-authority.md` MUST Rule 2 ("Spec Files Are Organized by Domain Ontology, Not Process"). The build sequence as **enduring domain truth** (the Phase 01 implementation order other agents will read in future sessions) belongs in `specs/`. The two are different artifacts: the workspace plan is the actionable plan for Phase 01 implementation; the spec is the durable record of "this is what Phase 01 implementation looked like."

The draft is at `specs/mvp-build-sequence.md`. See that file for the canonical spec content.

---

## 7. LOW findings — tracking list (no Phase 01 action)

These are recorded for completeness; none block Phase 01 ship; none require any action at this shard.

### 7.1 Spec-acknowledged open questions (fall through to Phase 02+ as spec already pre-declares)

- `specs/ledger.md` § Open questions (4 items): Lamport vs VClock (P03); per-segment keys (P04); verifier language (P01 acceptable); CRDT thresholds (P03+).
- `specs/ledger-merge.md` open questions (5 items): conflict-flood ceiling tuning, semantic batching threshold, cross-device key rotation, N-device perf — all P03+.
- `specs/boundary-conversation.md` § Open questions (3 items): state-resume cross-machine (P03 multi-device); S5 first-task corpus diversity (P02 corpus); novelty-feedback empirical calibration (P02 telemetry).
- `specs/grant-moment.md` § Open questions: cross-principal resolution (P03 A2A); auto-approve threshold (P02 calibration).
- `specs/daily-digest.md` § Open questions (5 items): Shared Household tz tie-break (P03 multi-principal); compact 10-line SMS budget sufficiency (P02 cohort); skip-digest duration (P01 7d default); reply parsing extensibility (P02 NL classifier); receipt_hash content (P01 canonical-JSON over payload-minus-receipt_hash).
- `specs/budget-tracker.md` § Open questions 1+2+3: anomaly thresholds, high-velocity calibration, non-USD i18n — P02.
- `specs/connection-vault.md` § Open questions (5 items): Linux Secret Service fallback, service-id registry strictness, rotation policy strength, cross-device migration, per-credential clearance — P02 mobile + service-id registry concerns.
- `specs/model-adapter.md` § Open questions 2+3: leak-canary corpus governance (P04); self-hosted provider risk classification (P01 disposition pre-declared).
- `specs/channel-adapters.md` § Open questions (5 items): all P02+ as spec pre-declares.
- `specs/runtime-abstraction.md` § Open questions (5 items): all implementation-discipline questions; Phase 01 build chooses; spec is correctly silent on encoding choices.
- `specs/distribution.md` lines 18 + 28–34: offline first-run claim (P01 disposition (c) — detect existing Ollama on PATH); N=3 mirror coverage (P01 PyPI only; P02 binary distribution).

### 7.2 Cross-spec terminology drift (LOW)

- `principal_id` vs `agent_id` vs "principal" — Phase 01 single-principal allows mapping at adapter layer; Phase 03 multi-principal redesign opportunity.
- `algorithm_identifier` 3-key (`{"sig":..., "hash":..., "shamir":...}`) vs 1-key (`{"algorithm": "ed25519+sha256"}`) — both forms valid until mint ISS-31; Envoy `_with_algorithm_id()` helper wraps; track ISS-31 closure.
- `PostureLevel(IntEnum)` vs `TrustPosture(str, Enum)` — wire format aligned, integer values divergent; Envoy uses provider class with `autonomy_level` dunder; spec annotation suggested.
- `PostureEvidence` shape divergence (ceremony vs operational) — same name, two concepts; resolved at Envoy adapter layer.
- "24 BIP-39 words" wording in `specs/shamir-recovery.md` line 29 should be "24 SLIP-0039 dictionary words"; behavior unchanged; polish at /codify.

### 7.3 Upstream packaging concerns (LOW; track for upstream PR)

- `SQLitePostureStore` not re-exported at `kailash.trust.posture.__init__.py` package level — submodule import works; file as upstream convenience PR per `rules/upstream-issue-hygiene.md`.

### 7.4 Phase-deferred audit items (track for /redteam round 2 / /codify)

- `specs/shamir-recovery.md` § Algorithm "Phase 00 crypto audit required" scope — surface at /redteam round 2; release-gate concern.
- `back_up_vault_key` gate — track mint ISS-37 closure; Phase 02 entry checklist.

---

## 8. Recommended Phase 02 entry-checklist items surfaced by this shard

These are NOT Phase 01 work; they are documented here as carry-forward for Phase 02 entry per `rules/specs-authority.md` MUST Rule 6 (deviations from spec require explicit acknowledgment) and `rules/journal.md` (DECISION entries require alternatives + rationale).

1. **(Conditional on human selecting Option A at shard 25)** Stand up the timezone basis fix on both `specs/envelope-model.md` § Financial dimension AND `specs/daily-digest.md` § Schedule. Cost: ~3 sessions of MUST Rule 5b sweep. Owner: Phase 02 entry shard (TBD).
2. **Stand up Foundation Health Heartbeat infrastructure** (per shard 17 disposition): OHTTP Key Configuration Server + Relay + STAR/Prio aggregator BEFORE consuming Heartbeat measurements for BET-8 / BET-3 / BET-12. Cost: 2–3 sessions of pure Foundation-ops work.
3. **Track mint ISS-31 closure** — when ISS-31 stabilizes the algorithm_identifier wire shape, update Envoy `_with_algorithm_id()` helper; verify backward-compat for any pre-ISS-31 records.
4. **Track mint ISS-37 closure** — when ISS-37 stabilizes the Trust Vault binding, decide whether Envoy migrates Shamir backup ritual to use `kailash.trust.vault.backup.back_up_vault_key` OR retains direct `shamir.generate(...)` path (per shard 15 § 7.3 disposition).
5. **Re-verify kailash-rs ISS-35 + ISS-36 closure** at Phase 02 entry before consuming Rust binding (per `03-kailash-py-mvp-readiness.md` § 4 Phase 02 deferrals).
6. **Run cross-runtime conformance gate** (per `specs/runtime-abstraction.md` § Security gates per phase row "Phase 02"): N1–N6 byte-identical + E1–E7 vectors pass on BOTH `kailash-py` AND `kailash-rs-bindings` runtimes. This is the BET-6 acceptance.
7. **Add `specs/independent-verifier.md` row to `specs/_index.md`** via `/codify` proposal flow (this shard authored the spec but did NOT edit `_index.md` to avoid Rule 5b sibling re-derivation).
8. **Add `specs/mvp-build-sequence.md` row to `specs/_index.md`** via `/codify` proposal flow.

---

## 9. Cross-references

### Phase 01 sibling shards (the source-of-truth for every finding aggregated above)

- `workspaces/phase-01-mvp/01-analysis/04-envelope-compiler-implementation.md` § 7
- `workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md` § 7
- `workspaces/phase-01-mvp/01-analysis/06-envoy-ledger-implementation.md` § 7
- `workspaces/phase-01-mvp/01-analysis/07-independent-verifier-design.md` § 7
- `workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md` § 7
- `workspaces/phase-01-mvp/01-analysis/09-authorship-score-implementation.md` § 7
- `workspaces/phase-01-mvp/01-analysis/10-grant-moment-implementation.md` § 7
- `workspaces/phase-01-mvp/01-analysis/11-daily-digest-implementation.md` § 7
- `workspaces/phase-01-mvp/01-analysis/12-budget-tracker-implementation.md` § 7
- `workspaces/phase-01-mvp/01-analysis/13-model-adapter-implementation.md` § 7
- `workspaces/phase-01-mvp/01-analysis/14-connection-vault-implementation.md` § 7
- `workspaces/phase-01-mvp/01-analysis/15-shamir-recovery-implementation.md` § 7
- `workspaces/phase-01-mvp/01-analysis/16-channel-adapters-implementation.md` § 7
- `workspaces/phase-01-mvp/01-analysis/17-foundation-health-heartbeat-decision.md` § 7
- `workspaces/phase-01-mvp/01-analysis/18-runtime-abstraction-stub.md` § 7
- `workspaces/phase-01-mvp/01-analysis/19-pipx-distribution-architecture.md` § 7

### Phase 01 governance and methodology

- `workspaces/phase-01-mvp/briefs/00-phase-01-mvp-scope.md`
- `workspaces/phase-01-mvp/01-analysis/00-inheritance-from-phase-00.md` § 5.4 (additive spec recommendations)
- `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 4 (failure-mode protocol)
- `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` (EC-1..EC-9 ship predicate)
- `workspaces/phase-01-mvp/01-analysis/03-kailash-py-mvp-readiness.md`
- `workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`
- `workspaces/phase-01-mvp/journal/0002-DISCOVERY-upstream-readiness-improved.md`
- `workspaces/phase-01-mvp/journal/0003-GAP-budget-ceiling-timezone.md` (the consolidated HIGH escalation)

### Phase 00 inherited (cited; not re-derived)

- `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` § 6 (Phase 00 spec convergence history; 6 rounds)
- `specs/_index.md` § "Spec freeze discipline" (37 specs FROZEN v1 status)

### Frozen specs touched by aggregated findings

- `specs/envelope-model.md` (shard 4 MED-1, MED-2; shard 12 HIGH if Option B)
- `specs/trust-lineage.md` (shard 5 LOW)
- `specs/posture-ladder.md` (shard 9 LOW ×2)
- `specs/ledger.md` (shard 6 LOW ×7; shard 7 MED ×3 → addressed in additive `specs/independent-verifier.md`)
- `specs/ledger-merge.md` (shard 6 LOW ×5)
- `specs/grant-moment.md` (shard 10 MED ×3 — all dispositioned as implementation latitude)
- `specs/budget-tracker.md` (shard 12 HIGH; MED ×1; LOW ×3)
- `specs/daily-digest.md` (shard 11 HIGH; LOW ×5)
- `specs/connection-vault.md` (shard 14 LOW ×5)
- `specs/shamir-recovery.md` (shard 15 LOW ×3)
- `specs/model-adapter.md` (shard 13 HIGH-candidate HELD; LOW ×2)
- `specs/channel-adapters.md` (shard 16 MED ×2; LOW ×5)
- `specs/a2a-messaging.md` (shard 16 MED-2 — Phase 03 boundary, no edit)
- `specs/runtime-abstraction.md` (shard 18 LOW ×5 — all implementation-discipline)
- `specs/distribution.md` (shard 19 LOW ×2)
- `specs/foundation-health-heartbeat.md` (shard 17 DECISION — DE-SCOPED to Phase 02; ~100 LOC stubs only in Phase 01)

### Rules consulted

- `.claude/rules/specs-authority.md` MUST Rule 4 (read specs before acting), MUST Rule 5b (additive only at this shard), MUST Rule 6 (deviation acknowledgment for the Phase 02 carry-forward items).
- `.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget (this shard within budget — aggregation work, not analysis).
- `.claude/rules/communication.md` § "Frame Decisions as Impact" (the Option A vs Option B framing per §4 above).
- `.claude/rules/journal.md` (cross-reference to `journal/0003` for the consolidated HIGH).
- `.claude/rules/orphan-detection.md` (no orphans introduced at this shard — the additive specs draft only).
- `.claude/rules/upstream-issue-hygiene.md` (one LOW finding at shard 9 § 7.3 dispositioned for upstream PR).
- `.claude/rules/independence.md` (background for shard 4 MED-1 disposition rationale).

### Forward references

- shard 23 + 24 (red team rounds): consume this aggregation as pre-declared spec-gap baseline; verify no NEW HIGH ambiguity surfaces during /redteam round; spec-compliance AST/grep verification per `skills/spec-compliance/SKILL.md`.
- shard 25 (closure): present the Option A vs Option B decision to the human; record DECISION journal entry capturing the human's choice + rationale.
- Phase 02 entry checklist: §8 above provides the structural carry-forward.

---

**Shard 22 closure:** This aggregation surfaces **1 unique HIGH** (consolidated timezone basis across shards 11 + 12; recommendation: Option B, decision: human's at shard 25), **1 HIGH-candidate HELD** (shard 13 chat-completion substrate; not escalated), **11 MED** (3 closed by additive `specs/independent-verifier.md`; 8 dispositioned as additive prose in §3), **39 LOW** (no Phase 01 action; aggregated in §7). Two additive new specs drafted as deliverables (`specs/independent-verifier.md` + `specs/mvp-build-sequence.md`); zero edits to existing frozen specs; zero MUST Rule 5b sibling re-derivation triggered. The 8 Phase 02 carry-forward items are recorded in §8 for /codify proposal flow.
