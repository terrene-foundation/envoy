# 01 — /analyze Shard Plan

**Document role:** /analyze for Phase 01 MVP exceeds the per-session capacity budget by ~14×. This document shards it. Each shard is one session; shards run sequentially because later shards depend on earlier outputs.

**Date:** 2026-05-03 (shard 1 of /analyze, written during shard 1).
**Status:** DRAFT — execute against this plan; revise if a shard surfaces a structural-blocker that re-shapes downstream shards.

---

## 1. Why sharding is mandatory

Per `rules/autonomous-execution.md` § Per-Session Capacity Budget, a single shard MUST stay within ALL of:

- ≤500 LOC of load-bearing logic
- ≤5–10 simultaneous invariants
- ≤3–4 call-graph hops of cross-file reasoning
- ≤15k LOC of relevant surface area in working context
- Describable in 3 sentences or fewer

A full Phase 01 /analyze produces ~17 implementation-architecture analysis docs + 4 plans + 8 user flows + spec-gap drafts + multi-round redteam. Each of those exceeds the 3-sentence describability test on its own. Single-shard execution would overflow attention by an order of magnitude — empirically, the failure mode is the Phase 5.11-orphan pattern (`rules/orphan-detection.md`).

Sharding is therefore not a stylistic preference; it is the structural defense against this exact failure mode.

## 2. Shard sequence (16 shards including this one)

### Shard 1 — Inheritance + brief + sharding plan + journal seed (THIS SESSION)

**Outputs:**

- `briefs/00-phase-01-mvp-scope.md` — derived brief, single source the rest chases
- `01-analysis/00-inheritance-from-phase-00.md` — frozen-contract surface map
- `01-analysis/01-shard-plan.md` — this file
- `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` — first journal entry

**Capacity check:** 4 doc artifacts, all derivative from frozen Phase 00 sources, no cross-file invariants. Within budget.

**Exit criterion:** Phase 01 workspace seeded; next session has a clean inheritance map and the rest of the shard sequence.

**Status:** IN FLIGHT.

---

### Shard 2 — MVP objectives + USP refinement

**Outputs:**

- `01-analysis/02-mvp-objectives.md` — Phase 01 exit criteria mapped to deliverables; what each exit criterion structurally tests; pre-declared "we ship Phase 01 when X" predicate
- `01-analysis/02b-mvp-usps.md` — Phase 01-specific USPs distilled (subset of CHARTER USPs that are actually demonstrable in MVP without Rust binding / mobile / Foundation-Verified registry / SKILL.md translator)

**Source pull:** ROADMAP §59–65 + thesis §3.1 + thesis §5 (BETs) + CHARTER §47–59

**Capacity check:** 2 docs, derivative from frozen sources, distillation work. Within budget.

**Why this shard before primitive deep-dives:** the implementation deep-dives in shards 3–17 must each cite which exit criterion / which BET / which USP they serve. Without shard 2, the deep-dives have no acceptance hook.

---

### Shard 3 — `kailash-py` survey re-read + primitive-provider table — DONE

**Outputs:**

- `01-analysis/03-kailash-py-mvp-readiness.md` — what `kailash-py` provides today for each Phase 01 primitive; what's Envoy-new-code; what's `kailash-py`-PR-required-upstream
- Revised primitive-provider mapping: `Boundary Conversation → kailash.kaizen.BaseAgent`, `Envoy Ledger → kailash.eatp.TieredAuditDispatcher`, etc.

**Source pull:** Phase 00 `02-kailash-py-survey.md` + `03-primitive-reconciliation.md` + the 12 kailash-py upstream issues filed in Phase 00 (per `issues/manifest.md`)

**Capacity check:** 1 doc, surveys an existing artifact. Within budget. CRITICAL gate before any implementation deep-dive.

**Why before deep-dives:** every shard 4–14 deep-dive will say "wire X primitive via Y kailash-py module." If the kailash-py module doesn't yet exist, the deep-dive has to design Envoy-new-code OR declare an upstream PR dependency. Shard 3 surfaces this for ALL primitives at once.

**Status:** DONE 2026-05-03. Major finding: 12 of 13 Phase 00-filed kailash-py issues (#594–#606) closed Apr 24–26; only #596 (TieredAuditDispatcher) remains OPEN. ISS-36 N4/N5 conformance Python runner closure removes the previously-identified Phase 02 blocker on the kailash-py axis. Net Phase 01 has 1 structural Envoy-new-code commitment (`#596` TieredAuditDispatcher → local hash-chain Ledger writer) and zero hard upstream-PR blockers. Per-primitive verification protocol pre-declared in §5 of the readiness doc. See `journal/0002-DISCOVERY-upstream-readiness-improved.md` for the velocity-signal entry.

---

### Shards 4–14 — Per-primitive implementation deep-dives

Each shard targets one primitive. Each shard outputs one analysis doc and may surface ONE additive spec file if a frozen-spec gap is HIGH-severity.

**Sequencing constraint:** primitives that gate other primitives must shard earlier.

| Shard | Primitive                                  | Source spec                                             | Gates                                                                                     |
| ----- | ------------------------------------------ | ------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| 4     | Envelope compiler                          | `envelope-model.md`, `sub-agent-delegation.md`          | Boundary Conversation outputs `EnvelopeConfig` → must compile                             |
| 5     | Trust store + lineage                      | `trust-vault.md`, `trust-lineage.md`                    | Every primitive writes to Trust store                                                     |
| 6     | Envoy Ledger + ledger-merge                | `ledger.md`, `ledger-merge.md`, `remote-time-anchor.md` | Every primitive writes ledger entries                                                     |
| 7     | Independent ledger verifier                | derived from `ledger.md`                                | Phase 01 exit criterion #4 — verifier ships separately, must be designed alongside Ledger |
| 8     | Boundary Conversation                      | `boundary-conversation.md`                              | Must produce envelope-compilable output (gates 4) and write ledger entries (gates 6)      |
| 9     | Authorship Score + posture gate            | `authorship-score.md`, `posture-ladder.md`              | BET-12 enforcement; must compute from Trust store events (gates 5)                        |
| 10    | Grant Moment                               | `grant-moment.md`                                       | UX surface for out-of-envelope; signs ledger entries (gates 6)                            |
| 11    | Daily Digest                               | `daily-digest.md`                                       | Reads Ledger + emits per-channel; gates 6 + 14                                            |
| 12    | Budget tracker                             | `budget-tracker.md`                                     | Threshold callbacks fire Grant Moments (gates 10)                                         |
| 13    | Model adapter                              | `model-adapter.md`                                      | Provider abstraction; underpins Boundary Conversation LLM calls (gates 8)                 |
| 14    | Connection Vault                           | `connection-vault.md`                                   | Phase 01 minimal: OS-keychain wrapper (full third-party OAuth deferrable per de-scope #3) |
| 15    | Shamir 3-of-5 recovery                     | `shamir-recovery.md`                                    | Standalone; gates 5 (Trust store backup ritual)                                           |
| 16    | Channel adapters (6 messaging + CLI + Web) | `channel-adapters.md`                                   | Reads from Ledger (gates 6); emits Grant Moments (gates 10)                               |
| 17    | Foundation Health Heartbeat                | `foundation-health-heartbeat.md`                        | DECISION SHARD — implement vs. de-scope #2 to Phase 02                                    |
| 18    | Runtime abstraction stub                   | `runtime-abstraction.md`                                | Phase 02 prep; abstract interface defined but only `kailash-py` wired                     |
| 19    | pipx distribution architecture             | `distribution.md`                                       | Final packaging shard; depends on every primitive being analysed                          |

That's 19 shards if shard count is taken seriously, not 17. Adjusting from the brief's earlier estimate.

**Per-shard structure** (each of shards 4–19):

1. Re-read the source spec (one file)
2. Re-read `02-kailash-py-survey.md` for the relevant module's coverage
3. Identify Envoy-new-code surface (what the spec needs that `kailash-py` doesn't provide)
4. Sketch the primitive's class structure (interfaces, not implementation)
5. Identify integration points to neighboring primitives
6. Identify Tier 2 / Tier 3 test surface (real-infrastructure test against the primitive)
7. Identify any frozen-spec ambiguity that surfaces during implementation reasoning
8. Output: `01-analysis/NN-<primitive>-implementation.md`

**Capacity check per shard:** one primitive, one source spec re-read, ≤3 cross-spec dependencies. Within budget.

**Wave-A completion (2026-05-03):** Shards 4, 5, 6, 13, 14, 17, 18 — DONE in parallel (7 worktree-isolated agents). Net findings:

| Shard | Status | Headline                                                                                                                                                                    |
| ----- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 4     | DONE   | A-grade upstream `kailash.trust.pact.envelopes`; thin Envoy `EnvelopeCompiler` materializer; 0 HIGH                                                                         |
| 5     | DONE   | A-grade across the 4 trust modules; `TrustStoreAdapter` wraps `SqliteTrustStore`+posture+ops with `principal_id` keying ready for Phase 03 multi-principal; 0 HIGH          |
| 6     | DONE   | Only #596 OPEN; `envoy.ledger` composes upstream pieces with deterministic `CanonicalJsonEncoder`; sunset clause for #596 per zero-tolerance Rule 4; 0 HIGH                 |
| 13    | DONE   | Materially-improved upstream LlmDeployment (11 closures verified); ~330 LOC Envoy glue (router + risk annotator + token-budget filter); 1 HIGH-candidate held not escalated |
| 14    | DONE   | Fully Envoy-new keyring wrapper; MIT-licensed `keyring`; principal-distinct from Trust Vault per spec; 0 HIGH                                                               |
| 17    | DONE   | DECISION: **DE-SCOPE to Phase 02 entry**; ~100 LOC stubs in Phase 01; k≥100 anonymity floor unclearable at Phase 01 cohort; only BET-8 falsifiability flips                 |
| 18    | DONE   | 24 byte-identical / 5 semantically-equivalent partition; feature-flagged `kailash_rs_bindings` adapter slot; import-discipline IS the Phase 02 mechanicality guarantee      |

Wave A produced 0 HIGH spec ambiguities → no MUST Rule 5b sweeps → wave B safe to launch immediately.

**Wave-B completion (2026-05-03):** Shards 7, 9, 15 — DONE in parallel.

| Shard | Status | Headline                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ----- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 7     | DONE   | Recommend separate `terrene-foundation/envoy-ledger-verifier` repo; Python first as Phase 01 EC-9 minimum + Rust sibling stretch; user-supplied trust-anchor with first-verification self-anchoring; STRONGLY recommend additive `specs/independent-verifier.md` draft at shard 22; 0 HIGH                                                                                                                                     |
| 9     | DONE   | Authorship Score is stateless pure function over **Ledger slice** (not PostureStore) with JCS-sorted byte-deterministic recompute; PostureGate is 5-step fail-closed; cross-shard invariant flagged for shard 4 (envelope compiler MUST sort `authored_constraints` in JCS canonical order); BET-12 + BET-1 + BET-10 + BET-6 falsifiable; 0 HIGH                                                                               |
| 15    | DONE   | Disposition (b) verified — `kailash 2.11.0` ships `kailash.trust.vault.shamir` as wrapper around `shamir-mnemonic` (PyPI; gated `pip install kailash[shamir]`); Envoy bypasses gated `back_up_vault_key` (still NotImplementedError pending mint ISS-37) and calls `shamir.generate(...)` directly with master-key from shard 5; 5 Envoy modules (ritual + paper + reconstruct + commitments + distribution_checklist); 0 HIGH |

Wave B produced 0 HIGH ambiguities. Wave C (shards 8, 10) launched immediately in parallel.

**Wave-C completion (2026-05-03):** Shards 8, 10 — DONE in parallel.

| Shard | Status | Headline                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ----- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 8     | DONE   | Boundary Conversation as Kaizen L3 Plan-DAG over S0→S10 with structured-output `Signature` pattern (NOT post-hoc LLM extraction); persistent resume in Trust Vault per `envoy init --resume <ritual_id>`; mid-conversation pauses compose with `Plan.suspension = SuspensionRecord(reason=ExplicitCancellationReason(...))`; ~1180 LOC across 6 modules; #598 PlanSuspension + #735 contextvars + #736 None prompt_tokens all verified closed; 0 HIGH; 1 MED 15min/25min dual-target (BOTH dispositioned). EC-1 owner; BET-1 + BET-12 directly falsified.                                                                                                                                                                     |
| 10    | DONE   | Grant Moment as M0→M4 state machine with M3 branching by `ResolutionShape` (Approve/Decline/ApproveWithModification covering spec's 4 decisions); `OutOfEnvelopeDetector` interceptor wraps every Kaizen tool-call dispatch (5-of-6 `why_asking` triggers; `velocity_raise` routed through Budget tracker); signed-consent is THREE wire-format artifacts (request bytes + result bytes + Ledger pointer row) signed by `delegation_key` (NOT Genesis); `CascadeRevocationOrchestrator` wraps upstream `cascade_revoke` for EC-8 cross-channel descendant gate; orchestrator defines NO new persistence layer — composes Ledger + Trust store; 0 HIGH; 3 MED logged. EC-2 owner; BET-1 + BET-10 directly + BET-12 indirectly. |

Wave C produced 0 HIGH ambiguities. Wave D (shards 12, 16) launched in parallel; shard 11 (Daily Digest) queued behind shard 16 per task graph.

**Wave-D completion (2026-05-03):** Shards 11, 12, 16 — DONE.

| Shard | Status | Headline                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ----- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 11    | DONE   | OrchestrationRuntime upstream is disposition (b) — partial: full strategy machinery + `OrchestrationRuntime(strategy, coordinator).run(input)` shape, but NO scheduling primitive. Envoy adds `DailyDigestService` facade composing `apscheduler.AsyncIOScheduler` + `LedgerAggregator` + `DigestRenderer` + `PerChannelFanout` (~700 LOC); 1 HIGH (timezone basis — same as shard 12, dispositioned Option A consistently). EC-3 + BET-8 owner.                                                                                                                                                                                                                                                                                                                        |
| 12    | DONE   | `kailash.trust.constraints.budget_tracker.BudgetTracker` + `SQLiteBudgetStore` A-grade; ISS-29 #603 closed 2026-04-25 with `set_threshold_callback(threshold_pct, callback) → handle` rising-edge one-shot + collect-under-lock-dispatch-outside-lock discipline verified. Envoy adds `EnvoyBudgetOrchestrator` composing 5 trackers per ceiling window with `tenant_id` keying and async `ThresholdDispatcher` outside-lock. **First HIGH-severity spec ambiguity surfaced** — timezone basis for `per_day_ceiling_microdollars` reset is unspecified (`specs/budget-tracker.md` Open Question 5). Escalated to shard 22 with two options framed; see `journal/0003-GAP-budget-ceiling-timezone.md`. EC-2 + EC-4 + EC-9 + EC-8 + BET-2.                                |
| 16    | DONE   | 6 social adapters (Telegram, Slack, Discord, WhatsApp, iMessage/BlueBubbles, Signal Path B) at ~150 LOC each over shared `WebhookTransport` + per-vendor `WebhookSigner`; unified `ChannelAdapter` ABC + `InboundRouter` + `CredentialResolver` + per-channel `render_grant_moment(request)`. Cross-channel coherence delegated to Trust store + Ledger (NOT a parallel adapter store). 4 indirect closures verified (#687 #767 #737 #673). De-scope #1 disposition: ship 8, fall back to 5 if EC-7 cohort fails on iMessage + Signal (cohort-driven, not architecture-time). 0 HIGH; 2 MED (iMessage/Signal feasibility — already encoded in spec lines 172–173; A2A Phase 03 boundary — already deferred per `specs/a2a-messaging.md` line 13). EC-7 + EC-8 + BET-11. |

Wave D produced **1 HIGH-severity frozen-spec ambiguity** (shards 11 + 12 share the same timezone-basis gap; consolidated for shard 22 disposition per `journal/0003`). The HIGH does NOT block remaining shards — Phase 01-acceptable Option A is the recommended Phase 01 disposition; Option B (edit `specs/envelope-model.md` + `specs/daily-digest.md`) triggers MUST Rule 5b ~3 sessions and is shard 22's recommendation venue.

Wave E (shard 19 pipx distribution) launched immediately after wave D commits.

---

### Shard 20 — Plans (`02-plans/`)

**Outputs:**

- `02-plans/01-build-sequence.md` — order of primitive implementation; integration-test sequence
- `02-plans/02-test-strategy.md` — 3-tier testing per `rules/testing.md`
- `02-plans/03-package-skeleton.md` — repo layout for `envoy-agent` Python package
- `02-plans/04-redteam-cycle-plan.md` — Phase 01 redteam round structure

**Capacity check:** 4 plans, all aggregating from shards 4–19. Within budget.

---

### Shard 21 — User flows (`03-user-flows/`)

**Outputs:** 8 user-flow files per the brief §5.3.

**Capacity check:** 8 flows but each is short (one user journey, one happy path + edge cases). Within budget.

---

### Shard 22 — Spec gap analysis + additive drafts

**Outputs:**

- `01-analysis/22-spec-gap-analysis.md` — for each primitive deep-dive (shards 4–19), did the analysis surface a frozen-spec gap?
- Drafts of any additive spec files identified (likely `specs/mvp-build-sequence.md` + `specs/independent-verifier.md`)

**MUST Rule 5b discipline:** new spec files do NOT trigger sibling re-derivation. Edits to existing specs DO. Phase 01 should land additive specs only; spec edits must be batched if multiple HIGH gaps surface.

**Capacity check:** 1 analysis + 0–2 spec drafts. Within budget.

---

### Shards 23–24 — Red team rounds

**Outputs per round:**

- `04-validate/round-N-implementation-comprehensive.md` — every implementation-deep-dive doc (shards 4–19) audited; CRIT/HIGH/MED/LOW classified

**Convergence gate (per `rules/specs-authority.md` MUST Rule 5b inherited convergence semantics):** 0 CRIT + 0 HIGH × 2 consecutive rounds.

**Capacity check:** 1 round = 1 shard. Convergence may take 2–4 rounds depending on findings.

---

### Shard 25 — /analyze closure

**Outputs:**

- `01-analysis/_index.md` — manifest of every Phase 01 analysis doc
- `02-plans/_index.md` — manifest of plans
- `03-user-flows/_index.md` — manifest of flows
- Updated session notes
- `/journal` summary entries for the journal-worthy patterns surfaced this phase
- Pre-`/todos` readiness check

**Capacity check:** Closure work, no new analysis. Within budget.

---

## 3. Total shard count + estimate

**25 shards** (1 inheritance + 1 objectives + 1 kailash-py + 16 primitives + 1 plans + 1 flows + 1 specs + 2–4 redteam + 1 closure).

Per autonomize 10× multiplier: 25 sessions ≈ 2.5 weeks of agent work, parallelizable on independent primitives if multiple agents are spawned. (Shards 4–19 are mostly independent of each other — only the gating dependencies in §2 sequence them; otherwise they parallelize.)

**Real-time projection:** if shards 4–19 are spawned in parallel with worktree isolation (per `rules/agents.md` § "Worktree Isolation for Compiling Agents"), the 16 primitive deep-dives can complete in 4–5 sessions of orchestrator time. Net Phase 01 /analyze: 8–10 orchestrator sessions including red team convergence.

This is consistent with the 8–12 session Phase 01 estimate in thesis §3.1, despite that estimate being for full Phase 01 (not just /analyze).

## 4. Failure modes + mitigations

| Failure                                                                                                     | Mitigation                                                                                                      |
| ----------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| A primitive deep-dive surfaces a frozen-spec HIGH gap                                                       | Stop deep-dive; convene MUST-Rule-5b sweep before continuing; spec edit goes through full-sibling redteam       |
| `kailash-py` survey reveals a primitive has no upstream coverage AND building Envoy-new-code is non-trivial | File upstream issue; declare Phase 01 dependency on issue close OR Envoy-new-code with sunset clause            |
| Foundation Health Heartbeat shard surfaces operational complexity beyond Phase 01 budget                    | Execute pre-declared de-scope #2 (defer to Phase 02 entry)                                                      |
| External gate fails (board declines, trademark blocks)                                                      | Architecture analysis still valid; Phase 02 distribution re-plans; Phase 01 ships under codename                |
| Red team finds 0 CRIT + 0 HIGH on round 1                                                                   | Suspicious — likely under-audit. Run round 2 with adversarial prompt on the shard outputs that look "too clean" |

## 5. Sequencing decisions for shards 4–19

The dependency graph in §2 implies a topological order. The minimum-time sequence (sequential):

1. Envelope compiler (no upstream deps among Phase 01 primitives)
2. Trust store (no upstream deps; gates 5+)
3. Envoy Ledger (no upstream deps; gates 5+)
4. Independent verifier (depends on Ledger only)
5. Authorship Score (depends on Trust store)
6. Boundary Conversation (depends on Envelope compiler + Ledger)
7. Grant Moment (depends on Ledger + Envelope compiler)
8. Daily Digest (depends on Ledger + channel adapters)
9. Budget tracker (depends on Grant Moment for threshold callbacks)
10. Model adapter (no Phase 01 primitive deps; gates Boundary Conversation LLM calls)
11. Connection Vault (no Phase 01 primitive deps; minimal in P01)
12. Shamir recovery (depends on Trust store)
13. Channel adapters (depends on Ledger + Grant Moment)
14. Foundation Health Heartbeat (decision shard, no deps if implemented)
15. Runtime abstraction stub (no deps; Phase 02 prep)
16. pipx distribution (depends on all primitive class skeletons)

Parallelizable groups (worktree-isolated):

- Group A (no deps): Envelope, Trust store, Ledger, Model adapter, Connection Vault, Runtime abstraction, Foundation Health Heartbeat → 7 parallel shards
- Group B (depends on A): Independent verifier, Authorship Score, Shamir → 3 parallel shards
- Group C (depends on A+B): Boundary Conversation, Grant Moment → 2 parallel shards
- Group D (depends on A+B+C): Daily Digest, Budget tracker, Channel adapters → 3 parallel shards
- Group E (depends on all): pipx distribution → 1 shard

5 wave groups × parallel execution → 5 orchestrator sessions for shards 4–19.

## 6. Shard-1 deliverables checklist

- [x] `workspaces/phase-01-mvp/briefs/00-phase-01-mvp-scope.md`
- [x] `workspaces/phase-01-mvp/01-analysis/00-inheritance-from-phase-00.md`
- [x] `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` (this file)
- [ ] `workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`

## 7. Cross-references

- Brief: `workspaces/phase-01-mvp/briefs/00-phase-01-mvp-scope.md`
- Inheritance: `workspaces/phase-01-mvp/01-analysis/00-inheritance-from-phase-00.md`
- Capacity rule: `.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget
- Worktree isolation: `.claude/rules/agents.md` § "Worktree Isolation for Compiling Agents"
- MUST Rule 5b: `.claude/rules/specs-authority.md`
