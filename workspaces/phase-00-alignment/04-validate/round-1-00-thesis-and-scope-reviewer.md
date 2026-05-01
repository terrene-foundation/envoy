# Round 1 Review — `00-thesis-and-scope.md`

**Reviewer:** quality-reviewer agent
**Date:** 2026-04-21
**Target:** `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` (draft v1)
**Scope:** Thesis coherence, bet falsifiability, scope-creep defense, upstream primitive sufficiency, internal consistency, meta-USP integrity, kill-criterion realism, vocabulary-vs-upstream reality, openness-posture integrity.
**References consulted:**

- `workspaces/internal/openclaw-analysis/02-plans/superior-product-concept-2026-04-21.md`
- `workspaces/internal/openclaw-analysis/04-validate/redteam-critique-2026-04-21.md`
- `workspaces/internal/kailash-rs-survey-2026-04-21.md`
- `CHARTER.md`, `DECISIONS.md`, `ROADMAP.md`
- `.claude/rules/{orphan-detection,zero-tolerance,terrene-naming,independence,specs-authority,testing}.md`

---

## Summary table

| ID   | Severity | One-line                                                                                                                                                                                                                                                                                                                                                                                                       |
| ---- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F-01 | CRITICAL | The canonical thesis statement in §2.4 is tautological — it restates product mechanics, not a falsifiable claim about the world.                                                                                                                                                                                                                                                                               |
| F-02 | CRITICAL | §7 item 1 kill criterion ("<1,000 WAU at 18 months") is structurally unmeasurable given §4.1 item 7 ("no phone-home") and item 8 ("no registration").                                                                                                                                                                                                                                                          |
| F-03 | CRITICAL | BET-9 "Kailash primitives are sufficient" fails to engage with the kailash-rs survey's documented non-functional bindings (Kaizen `BaseAgent.execute()` raises, `OrchestrationRuntime.run()` stub, A2A methods don't exist, `execute_raw()` SQLi). Mitigation path is hand-waving.                                                                                                                             |
| F-04 | CRITICAL | §3.3 primitive-inheritance table names `SQLitePostureStore`, `SQLiteBudgetStore`, `TieredAuditDispatcher`, `intersect_envelopes`, `PlanSuspension`, `McpGovernanceEnforcer`, `McpGovernanceMiddleware`, `cascade revocation`, `apply_read_classification`, `format_record_id_for_event` — NONE of these are confirmed present in the Python binding by the kailash-rs survey. The "~70%" ratio is unsupported. |
| F-05 | CRITICAL | §2.4 claims "safety is delivered by the runtime" but the Phase 01 runtime (`kailash-py`, per ROADMAP) is NOT the runtime the kailash-rs survey verified. Phase 01's safety guarantees are asserted, not audited.                                                                                                                                                                                               |
| F-06 | HIGH     | §8 "primary surface" test — all four sub-tests are also satisfied by an audit-heavy alternative (e.g. a hardened OpenClaw fork with pre-authorization + before-action logging + revoke button + channel-editable config). Test does not categorically distinguish Envoy.                                                                                                                                       |
| F-07 | HIGH     | §4.2 defers mobile clients to Phase 02 AND runtime pluggability to Phase 02. §9.4 anti-pattern 2 says "primary UI separate from the user's existing channels" breaks the meta-USP. Phase 01 ships CLI + Web only — a desktop-only product where users cannot use their phone IS the "go to the product" anti-pattern for the ~70% of the target cohort whose primary channel is mobile. Self-contradiction.    |
| F-08 | HIGH     | BET-1 falsifying evidence ("<20% of Phase 01 users complete the Boundary Conversation") has no Phase 01 instrumentation path. §13 Q1 acknowledges this; §5.1 does not close it. The bet is structurally non-falsifiable in Phase 01.                                                                                                                                                                           |
| F-09 | HIGH     | §7 item 4 ("categorically-better alternative emerges") is a panicky-abandonment trigger with no noise filter. "Feature parity + >10× our adoption in 12 months" is not a categorical-superiority test — adoption leads feature quality in AI products. Needs sharper definition anchored in capability gaps, not traffic.                                                                                      |
| F-10 | HIGH     | §4.1 item 5 claims "no subscription ever" but the openness stack depends on Foundation-hosted `kailash-rs-bindings` binary on a GitHub org the Foundation controls. If the Foundation delists or goes offline, default Envoy installs stop working. This is de facto centralization that BET-3 (sovereignty) does not account for.                                                                             |
| F-11 | HIGH     | §11 glossary defines "Cascade revocation", "Trust Vault", "Conformance vector N1–N6" but the kailash-rs survey (Implications §457, §453) says cascade revocation is "NOT explicitly surfaced in the binding — must verify behavior against Rust source or implement at Envoy level." Glossary vocabulary drift.                                                                                                |
| F-12 | HIGH     | §5.6 BET-6 (cross-runtime parity) falsifying evidence does not model what the kailash-rs survey already flagged: `kailash-py` conformance-vector runner NOT YET IMPLEMENTED for PACT N4/N5. Phase 02 cannot measure parity without the runner; the bet is unmeasurable at its checkpoint.                                                                                                                      |
| F-13 | HIGH     | Kill criterion §7.2 ("≥3 bets disconfirmed simultaneously with no shared root cause") is loose — "shared root cause" is a subjective judgement that absorbs any number of simultaneous bet failures. Operationalize.                                                                                                                                                                                           |
| F-14 | HIGH     | §3.2 capability 11 ("Trust Vault sync — iCloud/Dropbox/Keybase/git/WebDAV/S3 + native Foundation sync node") is not traceable to any phase exit. §3.1 Phase 01 row does not list vault sync; §3.1 Phase 02 row does not list it either. Capability-to-phase-exit graph is incomplete.                                                                                                                          |
| F-15 | HIGH     | §5.10 BET-10 falsifying evidence says "FOSSA/Snyk/Sonatype flag the composite license expression" — but there is no counterfactual action for "scanner flags the binary component as proprietary and enterprise procurement blocks adoption at PR time." The Phase 05 enterprise pivot depends on scanners not flagging. Gap.                                                                                  |
| F-16 | HIGH     | §2.2 — the "irreducible human contribution" claim elides a structural counter-example: boundary-setting can be delegated (to lawyers, HR, compliance teams). If users delegate envelope authorship upward, Envoy becomes a workflow engine for pre-authored envelopes, not a personal agent. The thesis does not guard against this collapse.                                                                  |
| F-17 | MEDIUM   | §3.2 "17 capabilities" is advertised as "the full product" but capabilities are unordered, ungrouped, and unscoped by phase. A Phase 01 PM asking "which of these lands in Phase 01?" has to cross-read §3.1. Inline the phase ownership.                                                                                                                                                                      |
| F-18 | MEDIUM   | §3.3 Envoy-contributed new code list includes "Shamir 3-of-5 ritual + CLI/Web UX" but §4.1 item 9 says "Ed25519 for signing, SHA-256 for hashing, SLIP-0039 for Shamir — but the algorithm choices are architecturally separable." The algorithm-separation claim implies versioned algorithm-identifiers in signed artifacts; this is NEW scope not listed as new code.                                       |
| F-19 | MEDIUM   | §5.5 BET-5 falsifying evidence "Phase 03 Shared Household feature: <5% of single-user Phase 02 installers convert" — but §4.2 puts Shared Household at Phase 03, so the evidence-window is Phase 03+, not testable in Phase 02. Inconsistent with the timeline.                                                                                                                                                |
| F-20 | MEDIUM   | §5.4 BET-4 falsifying evidence line 3 ("Foundation language reads as bureaucratic") is an indirect emotional signal with no operational measurement. Needs either a specific instrument (e.g. install-survey NPS on "Foundation" framing) or to be demoted.                                                                                                                                                    |
| F-21 | MEDIUM   | §9.4 anti-pattern 4 ("credentials for action live anywhere other than on the user's own device") conflicts with §3.2 capability 11 ("Trust Vault sync via iCloud/Dropbox/Keybase") — iCloud/Dropbox are not "user's own device". Needs reconciliation (the "end-to-end encrypted" caveat in §4.1 item 10 partially covers but §9.4 is absolute).                                                               |
| F-22 | MEDIUM   | §5.8 BET-8 falsifying evidence "Weekly Posture Review engagement < 10% week-over-week" — but Weekly Posture Review is deferred to Phase 03 per §4.2. No Phase 01 or Phase 02 data will exist. Bet is structurally deferred but labeled as though it falsifies continuously.                                                                                                                                    |
| F-23 | MEDIUM   | §4.3 table row "Signal / Matrix" says Envoy composes "over" the transport — but Signal's protocol does not allow third-party clients per its terms. A channel adapter for Signal may be legally infeasible. Non-goal does not pre-refuse this Phase 02 gotcha.                                                                                                                                                 |
| F-24 | MEDIUM   | §10 dependency graph omits `SKILL.md` ingest's relationship to the CO validator threshold (BET-7). The graph treats them as sequential but BET-7's falsifying evidence ("validator too strict" vs "too loose") is a continuous tuning problem, not a gate.                                                                                                                                                     |
| F-25 | MEDIUM   | §3.1 Phase 01 exit criterion includes "verify [ledger] independently" but §3.3 does not list an independent verifier tool as new code. Who verifies the hash chain independently — user-written code? A shipped tool? Unstated.                                                                                                                                                                                |
| F-26 | LOW      | §6 counterfactuals table CF-10 says "if Rust binary is the issue, kailash-py becomes sole default" — but ROADMAP Phase 01 already uses kailash-py as sole default. The counterfactual is already the state in Phase 01, making it confusingly worded.                                                                                                                                                          |
| F-27 | LOW      | §4.2 deferred table row for "Runtime pluggability" is at Phase 02, but ROADMAP Phase 01 description says "pure-Python runtime" explicitly — agrees. However §3.1 Phase 01 primitives row lists "model adapter" but not "runtime adapter" — subtle consistency gap.                                                                                                                                             |
| F-28 | LOW      | §11 glossary row for `kailash-py` says "Pure-Python Foundation runtime" but per `independence.md` and upstream convention the runtime is specifically the Foundation's Apache-2.0 implementation — the wording "Foundation runtime" is ambiguous (could read as "the canonical runtime").                                                                                                                      |

---

## Detail section

### F-01 — CRITICAL — Canonical thesis statement is tautological

**Quoted claim** (§2.4, lines 53–55):

> **Envoy is autonomous AI where the human holds a signed, revocable authority that every agent action traces to.**
> Responsibility belongs to the human; safety is delivered by the runtime; the envelope is the surface where they meet.

**Why this is a problem:** A thesis is a claim about the world that could be wrong. This sentence is a claim about Envoy's architecture — it describes the product's mechanics, not a proposition that reality could refute. "The human holds a signed, revocable authority" is true by construction for any product that implements envelope signing. The thesis collapses into "Envoy is what it is."

The task document asks: _"is the product's thesis actually a thesis (a claim about the world that could be wrong), or is it a tautology / a re-statement of features?"_ The §2.4 statement fails this test.

Contrast: the §2.1 question ("What is the human for?") + §2.2 answer ("Setting boundaries") IS a falsifiable claim — it could be wrong if users do not value boundary-setting, and BET-1 makes that falsification explicit. The §2.4 canonical statement should match that structure.

**What the doc should say instead:**
A load-bearing thesis sentence of the form:

> _"The durable, defensible role of the human in autonomous AI is the authorship of envelopes; products that ritualize this authorship will earn primary-surface loyalty that tool-frame AI products cannot."_

This is a claim about users + the market. It is falsifiable: if users prefer frictionless autonomy (Devin-style), or if envelope authorship is readily delegable (to compliance teams, to templates, to the vendor), the thesis breaks. F-16 names the second collapse mode explicitly.

**Recommended action:** Rewrite §2.4. Keep the architectural sentence as a _positioning statement_ (§8 or §9), but demote it from "canonical thesis." Elevate a user-model + market claim to canonical status.

---

### F-02 — CRITICAL — WAU kill criterion is structurally unmeasurable

**Quoted claim:**

- §7 item 1 (line 389): _"18 months post-Phase-01 with <1,000 weekly-active users."_
- §4.1 item 7 (line 147): _"Envoy does not phone home. No telemetry. No crash-report pipeline that leaves the device without explicit Grant Moment approval. No install analytics."_
- §4.1 item 8 (line 148): _"Envoy does not require registration. No user account, no email, no signup, no waitlist, no hosted identity."_

**Why this is a problem:** These three claims are internally contradictory.

A WAU (weekly-active-user) metric requires either (a) telemetry that reports an activity signal, OR (b) a centrally-visible account model. §4.1 item 7 forbids (a) and item 8 forbids (b). Under the non-goals as written, the team literally cannot count users — let alone measure activity — so the kill criterion can never fire. This is not a kill criterion; it is decorative.

**Possible signals the team might fall back on:**

- GitHub star / fork count (weak, measures curiosity not usage)
- PyPI download count (weak, measures install not retention)
- Foundation-Verified Envelope Library fetch count (weak, measures envelope import not agent usage)
- Envelope Library publish counts (weak, measures author activity, a small subset)
- Channel-adapter-specific webhook traffic (requires phone-home — forbidden)

None of these are WAU.

**What the doc should say instead:**
Either (a) retract the WAU threshold and state an alternate kill metric that respects the non-goals (e.g. "<X Envelope Library fetches / week among Foundation-Verified envelopes at 18 months"), OR (b) introduce an explicit "opt-in anonymous heartbeat" mechanism with a Grant Moment that is the ONLY exception to item 7, carefully scoped. Option (b) requires a new ADR and visibly weakens the sovereignty narrative.

**Recommended action:** Add a §7 subsection titled "Measurement compatibility with §4.1" that enumerates the four non-measurable axes (WAU, retention, NPS, cohort persistence) and declares which measurable proxies substitute.

---

### F-03 — CRITICAL — BET-9 hand-waves the binding reality

**Quoted claim** (§5.9, lines 329–342):

> **Claim:** The ~70% of Envoy functionality that composes on shipped Kailash primitives is actually shippable as-composed — no primitive we plan to consume is subtly broken, orphaned, or incomplete in a way that forces Envoy to rebuild it.
>
> **Falsifying evidence:** Phase 01 implementation discovers a primitive (e.g. `TieredAuditDispatcher`, `PostureStore`, `intersect_envelopes`) that looks shipped but has an orphan pattern...

**Why this is a problem:** The bet is written as if primitive-sufficiency is a Phase 01 _discovery risk_ — something we might find. But the kailash-rs survey (`workspaces/internal/kailash-rs-survey-2026-04-21.md`) has already discovered the pattern, and it is not a discovery question — it is a documented reality at draft-time:

From the survey §4:

- Kaizen `BaseAgent.execute()` **raises `NotImplementedError`** in the Python binding (BINDING-AUDIT B1). 3 of 7 pre-built agents crash.
- `OrchestrationRuntime.run()` returns a **static dict stub** (BINDING-AUDIT B3) — non-functional.
- `SessionMemory` / `SharedMemory` methods: `.pyi` declares `.set() / .get() / .delete()`; ACTUAL API is `.store() / .recall() / .remove()` (C5).
- `A2A.send_message / receive_message` **declared in `.pyi` but DO NOT EXIST** (C6).
- `DataFlow.execute_raw()` **silently drops params** — active SQL-injection risk (H4).
- MCP stdio / SSE / HTTP transports **not bound from Python** (C4).
- `.pyi` type stubs are **55% accurate** overall.

Of these:

- Kaizen `BaseAgent` is directly named in §3.3 as the substrate for the Boundary Conversation agent.
- `OrchestrationRuntime` is the binding equivalent of what §3.3 calls "Kaizen governed agents + L3 Plan DAG + PlanSuspension" for scheduled rituals.
- A2A is how multi-principal agents coordinate — implicated in Shared Household (Phase 03).
- MCP transports are implicated in §3.3's "McpGovernanceEnforcer + McpGovernanceMiddleware" claim.

The "~70%" ratio in §3.3 is computed against a primitive inventory that is >50% non-functional in the Python binding at draft time. BET-9's mitigation path ("Envoy fixes upstream and contributes back") is a heroic engineering claim (likely a full session per primitive for 4+ primitives = 4+ sessions). That blows through Phase 01's 3–5 session budget.

**What the doc should say instead:**

- BET-9 must name each specific broken primitive (from the survey) as pre-existing falsifying evidence, not hypothetical future evidence.
- The mitigation path MUST include a Phase 01 decision gate: for each broken primitive, either (a) Envoy fixes the binding before Phase 01 starts (an explicit pre-phase dependency), (b) Envoy reimplements in pure Python (scope inflation), or (c) Envoy defers the capability that needed it (scope cut).
- The §3.3 "~70% composes on primitives" claim must be restated with a confidence band and a dependency on the survey-remediation work landing.

**Recommended action:** Rewrite BET-9 as "Phase 01 starts with a frozen list of 6–8 pre-audited, confirmed-functional primitives; every other Kailash primitive is treated as Envoy-new-code until the binding audit closes." Add a new workspace artifact — `workspaces/phase-00-alignment/01-analysis/01-binding-sufficiency.md` — that rebuts the survey per-primitive.

---

### F-04 — CRITICAL — §3.3 primitive inheritance table cites names not verified in binding

**Quoted claim** (§3.3, lines 104–115):

| Primitive                                                                                     | Source              | Envoy consumer                                            |
| --------------------------------------------------------------------------------------------- | ------------------- | --------------------------------------------------------- |
| `RoleEnvelope` / `TaskEnvelope` / `intersect_envelopes()` + 5 constraint dimensions           | `kailash-pact`      | Envelope compiler (doc 02)                                |
| `TrustOperations` / Genesis Record / Delegation Record / cascade revocation / Ed25519 signing | `kailash` core EATP | Trust Lineage (doc 03)                                    |
| `PostureStore` / `SQLitePostureStore` / `PostureEvidence` / 5 canonical postures              | `kailash` core EATP | Trust Posture (doc 01 §5.3, doc 10)                       |
| `BudgetTracker` + integer microdollars + threshold callbacks + `SQLiteBudgetStore`            | `kailash` core EATP | Budget primitive (doc 10)                                 |
| `TieredAuditDispatcher` + hash-chained Audit Anchors + SIEM export                            | `kailash` core EATP | Envoy Ledger (doc 04)                                     |
| `@classify` + `apply_read_classification()` + `format_record_id_for_event()`                  | `kailash-dataflow`  | Channel message privacy + ledger surface hygiene (doc 09) |
| Kaizen governed agents + L3 Plan DAG + PlanSuspension                                         | `kailash-kaizen`    | Boundary Conversation agent + scheduled rituals (doc 01)  |
| `McpGovernanceEnforcer` + `McpGovernanceMiddleware`                                           | `kailash-pact`      | Skill-runtime guarantees + third-party MCP (doc 08)       |

**Why this is a problem:** Cross-referencing with the kailash-rs survey line-by-line:

- **`RoleEnvelope` / `TaskEnvelope` / `intersect_envelopes()`** — survey §2 (PACT subsection) lists `PactOrgNode`, `PactGovernanceVerdict`, `PactKnowledgeItem`, `PactEffectiveEnvelopeSnapshot`, `PactGovernanceEngine`, `PactRoleSummary`. **Does NOT list `RoleEnvelope`, `TaskEnvelope`, or `intersect_envelopes()`** in the Python binding surface. These may exist in Rust crates but are not confirmed bound.
- **`cascade revocation`** — survey §7 "Load-bearing for doc 03": _"Cascade revocation is NOT explicitly surfaced in the binding — must verify behavior against Rust source or implement at Envoy level."_ Direct contradiction.
- **`SQLitePostureStore`, `SQLiteBudgetStore`** — survey mentions "SQLite-backed stores" only in the Implications section (§448) as an aspirational inheritance. Survey Python-binding surface lists `BudgetTracker` methods but NO `SQLiteBudgetStore`, NO `SQLitePostureStore`.
- **`PostureEvidence`** — not in survey.
- **`TieredAuditDispatcher`** — survey Python binding surface lists `AuditLogger`, `AuditFilter`, `AccessDecision`. **Does NOT list `TieredAuditDispatcher`**.
- **`apply_read_classification()` + `format_record_id_for_event()`** — neither appears in the survey's Python binding surface. They may be Rust-side only (the `format_record_id_for_event` function is referenced in `.claude/rules/event-payload-classification.md` as a kailash-py helper, but Envoy's Phase 01 uses kailash-py; the survey covers the Rust binding, not kailash-py directly).
- **`L3 Plan DAG + PlanSuspension`** — survey §252 mentions "L3 planning: 6 files in `src/l3/`" — Rust-side. Python binding surface has no entry for L3. `PlanSuspension` is NOT in the survey.
- **`McpGovernanceEnforcer` + `McpGovernanceMiddleware`** — survey §2 Nexus subsection lists `McpServer.register_tool` etc., AND survey §255 notes "MCP canonical primitives (32KB); stdio / SSE / HTTP transport bindings needed (currently missing — BINDING-AUDIT C4)." `McpGovernanceEnforcer` / `Middleware` names do NOT appear in the survey.

This means of the 10 primitive rows in §3.3, at least 7 reference names that the kailash-rs survey cannot confirm exist in the Python binding. The "~70%" ratio claim in line 131 ("~70% of Envoy's functionality composes on shipped Foundation primitives") is computed against a phantom primitive inventory.

**Important clarification:** These primitives may all exist in `kailash-py` (which Phase 01 uses) rather than `kailash-rs-bindings` (which Phase 02 uses). The survey covers only the Rust binding. But the §3.3 table does NOT specify which runtime each primitive lives in, and Envoy's Phase 01 / Phase 02 split depends critically on parity between them (BET-6). A primitive that exists in kailash-py and does NOT exist in kailash-rs-bindings is a parity gap, which is falsifying for BET-6 at Phase 02.

**What the doc should say instead:**
Rewrite §3.3 as three columns: _primitive name_ × _kailash-py status (confirmed / unconfirmed / absent)_ × _kailash-rs-bindings status (confirmed / unconfirmed / absent / broken)_. The source-of-truth is:

- For kailash-py: a matching kailash-py survey artifact (does not yet exist — must be produced before §3.3 can be trusted).
- For kailash-rs-bindings: `workspaces/internal/kailash-rs-survey-2026-04-21.md`.

Until both columns are filled, the "~70% composes" ratio in line 131 should be replaced with "_to be computed after both-runtime surveys land_."

**Recommended action:** Block §3.3 from acceptance until a kailash-py survey mirror exists. Downgrade line 131's ratio claim from assertion to open question.

---

### F-05 — CRITICAL — Phase 01 "safety delivered by the runtime" claim is unaudited

**Quoted claim** (§2.4, line 55):

> Responsibility belongs to the human; safety is delivered by the runtime; the envelope is the surface where they meet.

**Why this is a problem:** The thesis statement rests on "safety is delivered by the runtime." Phase 01 (per `ROADMAP.md` line 37 and §3.1) ships on `kailash-py` as the sole runtime. The kailash-rs survey audits `kailash-rs-bindings`, NOT `kailash-py`. No audit of `kailash-py`'s safety primitives exists in the workspace at the time of this draft.

If `kailash-py` has analogous binding gaps to what the survey found in `kailash-rs-bindings` (orphaned primitives, missing-in-Python, stub implementations), then Phase 01's runtime does NOT "deliver safety" — it asserts safety without audit.

The rules `.claude/rules/orphan-detection.md` and `.claude/rules/facade-manager-detection.md` were written precisely because the kailash ecosystem has a history of shipping beautifully-implemented orphans with no call sites. BET-9 acknowledges this as a possibility for Envoy's consumption; §2.4 does not.

**What the doc should say instead:**
§2.4 should condition the "safety is delivered by the runtime" claim on runtime audit status:

> "Safety is delivered by the runtime — conditional on the runtime passing the Envoy audit gate (§X). In Phase 01, the audit of `kailash-py`'s PACT / EATP / Kaizen safety primitives is a Phase 00 deliverable (see `workspaces/phase-00-alignment/01-analysis/XX-kailash-py-safety-audit.md`). If the audit finds orphans or stubs in the safety primitives, Phase 01 is blocked."

**Recommended action:** Add a Phase 00 gate item: `kailash-py` safety primitive audit (mirror of the kailash-rs survey, focused on PACT envelope compilation, EATP signing, EATP audit dispatcher, Kaizen agent execution). Thesis cannot be claimed valid until that audit is green.

---

### F-06 — HIGH — §8 "primary surface" test is feature-parity with audit-heavy alternatives

**Quoted claim** (§8, lines 401–413):

> The test has four parts. All four must be true.
> **Test-1 — Onboarding cannot skip boundary declaration.** ...
> **Test-2 — Every action emits a signed record before execution.** ...
> **Test-3 — Revocation is first-class in the UI.** ...
> **Test-4 — The envelope is editable through the same channel the user uses to interact.** ...

**Why this is a problem:** Each of the four tests describes a _product capability_, not a categorical differentiator. Consider a thought experiment: a hardened OpenClaw fork with

1. A "first-run envelope import" that refuses to start without an envelope selection → passes Test-1.
2. A pre-action logger with Ed25519 signing → passes Test-2.
3. A "revoke" button prominent in the chat UI → passes Test-3.
4. An `openclaw env edit` command in every channel → passes Test-4.

This fork is structurally feasible and would satisfy the §8 tests without implementing anything distinctively Envoy-shaped. Envoy's _actual_ categorical difference lives in §2.2 (judgement-as-product-surface) and §9 (meta-USP) — not in §8.

The task document asks: _"does the 'primary surface' test in §8 actually distinguish Envoy from adjacent products or is feature-parity with audit-heavy alternatives?"_ Current answer: feature-parity.

**What the doc should say instead:**
The §8 tests should include at least one claim that _cannot_ be ported to an audit-heavy competitor without rebuilding from the thesis:

- **Test-5 (proposed):** _The product cannot execute an action for which the user cannot produce a human-readable narrative of why they authorized it._ This tests that envelopes are authored by users, not imported from templates alone. An audit-heavy fork that ships with a permissive default envelope and retroactive audit fails this test.
- Alternative **Test-5:** _The onboarding Boundary Conversation MUST be a conversation, not a template import._ A user who only imports a Foundation-Verified envelope without answering any of the 4–5 boundary questions is NOT a correctly onboarded Envoy user. (This conflicts with §8 Test-1's current wording "Users may import a reputable Foundation-Verified envelope with one command" — that escape hatch is exactly the mechanism by which an audit-heavy fork could claim parity.)

**Recommended action:** Add a 5th test that operationalizes the _authorship_ claim, not the audit claim. Consider tightening Test-1 to require at least N minutes of Boundary Conversation even when a template is imported (e.g. "the template becomes a starting point; the conversation customizes it"). This also addresses F-16 below.

---

### F-07 — HIGH — §4.2 phase deferrals create §9.4 anti-pattern violations

**Quoted claim** (§9.4, lines 441–447):

> The meta-USP is broken if any of:
>
> - Envoy requires registration / signup / email verification / hosted account
> - **Envoy has a primary UI separate from the user's existing channels (→ requires the user to "go to" the product).**
>   ...

**Cross-referenced claim** (§4.2, lines 161–165):

> | Rust binary distribution (single `curl \| sh`) | 02 | Phase 01 ships `pipx install envoy-agent` to validate UX loop first |
> | Channels beyond CLI + Web | 02 | Ritual loop must be validated on one ergonomic + one programmatic channel first |
> | Mobile clients (Flutter) | 02 | Desktop-first for MVP UX; phone is a feature-complete Phase 02 deliverable |

**Why this is a problem:** Phase 01 ships only CLI + Web (per `ROADMAP.md` line 44) and a pip-installable Python package. For a user whose primary life-channel is iMessage / WhatsApp / Telegram (the §3 Pillar 3 premise and §9.3 operationalization of the meta-USP), Phase 01 IS the anti-pattern §9.4 names:

- The user "goes to" the terminal (Web is technically a browser) to interact with Envoy.
- There is no channel-native operation in Phase 01.
- A user installing envoy-agent on their Mac to onboard their iMessage life is exactly the "extension of self" contradiction the meta-USP forbids.

The task document identifies this correctly: _"A Phase 01 where the user cannot run on their phone is arguably a 'go to the product' violation."_

**Possible resolutions:**

1. Accept that Phase 01 is for a specific cohort (CLI-comfortable prosumers) and explicitly name the cohort mismatch vs the long-term thesis. This is honest but weakens Phase 01's market-learning value (the cohort that shows up to CLI-only product is not the cohort the product ultimately serves).
2. Re-scope Phase 01 to include one programmatic non-CLI channel (e.g. Telegram bot) as the "ritual loop validation" channel. Adds 1–2 sessions.
3. Re-scope Phase 01 to defer the Boundary Conversation until Phase 02 (when a channel-native client exists) and have Phase 01 ship "audit-heavy preview" only.

**What the doc should say instead:**
§4.2 should add an explicit note: _"Phase 01's CLI + Web delivery is an acknowledged temporary violation of the §9.4 anti-pattern. The cohort that self-selects into Phase 01 will be CLI-comfortable prosumers; insights from Phase 01 about ritual-loop effectiveness are therefore not representative of the Phase 02+ target cohort. This is tracked as a Phase-01-specific threat to BET-1's evidence quality."_

**Recommended action:** Add the caveat above, AND add a Phase 01 exit criterion that extends §3.1's row: _"Exit with an explicit cohort-mismatch threat-model note feeding Phase 02 /analyze."_

---

### F-08 — HIGH — BET-1 falsifying evidence requires instrumentation §13 admits we don't have

**Quoted claim** (§5.1, lines 202–208):

> **Falsifying evidence:**
>
> - <20% of Phase 01 users complete the Boundary Conversation to envelope-compile state. (Tracked via `specs/acceptance-metrics.md`.)
> - Week-2 retention <30% because users find the boundary interactions burdensome after novelty.
> - > 50% of Grant Moments produce a "grant always" response — indicates users treat them as speed bumps, not moments of agency.
> - Qualitative: interview cohort reports "I just want it to do the thing" as dominant sentiment.

**Cross-referenced claim** (§13 Q1, line 562):

> 1. **Is the thesis actually falsifiable?** BET-1 says "<20% of Phase 01 users complete the Boundary Conversation" is a disconfirmation. But Phase 01 may not have enough users to statistically evaluate this. Need a sharper early-signal criterion.

**Why this is a problem:** The §5.1 falsifying evidence is circularly dependent on instrumentation that the §4.1 non-goals forbid (item 7 "no phone-home", item 8 "no registration"). Even if Phase 01 has 10,000 installs:

- "<20% complete the Boundary Conversation" requires phoning home completion events. Forbidden.
- "Week-2 retention <30%" requires either (a) phoning home or (b) tying installs to accounts. Both forbidden.
- "50% of Grant Moments produce 'grant always'" requires per-install telemetry. Forbidden.
- "Interview cohort" requires the team knowing who the users are. No registration → users are anonymous.

§13 acknowledges this Q1 as an unresolved question. The doc punts the resolution to /redteam. But the bet as currently written is non-falsifiable, which means it is not a bet — it is aspiration.

Compare with F-02 (WAU kill criterion has the same structural problem at higher-scope level).

**What the doc should say instead:**
Either (a) explicitly carve out BET-1 evidence channels as opt-in Grant Moments (e.g. "On first Boundary Conversation completion, Envoy asks a Grant Moment: 'May I share anonymized ritual-completion telemetry with the Foundation for thesis validation?' with defaults to Yes + one-keystroke No"), accepting the scope-creep cost; OR (b) rewrite BET-1 falsifying evidence in terms of indirect signals the team CAN measure without phone-home:

- Envelope Library Foundation-Verified template download counts (users import templates → they exist).
- GitHub issues opened about Boundary Conversation UX (qualitative).
- Third-party blog posts, HN threads, social-media screenshots mentioning "too many questions" or "skipped onboarding" (qualitative).
- Solicited user interviews recruited through the Foundation Discord / forum (opt-in, not demanded).

Both paths are work; (a) requires a small instrumentation scope-add, (b) requires explicit acceptance that falsification is indirect and slower.

**Recommended action:** Rewrite BET-1 falsifying evidence against whichever instrumentation path §4.1 item 7 allows. If neither works, demote BET-1 from "falsifiable bet" to "hypothesis, validation deferred to Phase 03+ when enough opt-in Foundation-connected users exist to interview."

---

### F-09 — HIGH — §7 item 4 panic trigger has no noise filter

**Quoted claim** (§7 item 4, line 392):

> **A categorically-better alternative emerges that satisfies the meta-USP more completely.** If another Foundation-grade, non-commercial, local-first, envelope-verified product reaches feature parity and >10× our adoption within a 12-month window, the thesis has been decisively solved by someone else. The correct move is contribute upstream and sunset Envoy.

**Why this is a problem:** Three structural issues:

1. **"Feature parity"** is asserted but undefined. Feature parity on §3.2's 17 capabilities is a high bar but the bar itself is the _what_, not the _how_. A competitor could achieve parity on features while missing the thesis (e.g. cosplay envelope authoring — permissive default envelopes, signed but un-reviewed grants). Envoy should not sunset for a competitor that has Envoy's shape but not its substance.
2. **">10× our adoption"** — the doc previously (§7 item 1) committed to not measuring adoption because of §4.1. The panic trigger uses a metric the kill criterion set acknowledges is unmeasurable.
3. **"12-month window"** is an arbitrary short horizon. The field evolves quickly; 12 months captures noise. AutoGPT's peak-to-obsolescence was <12 months; if Envoy launched during AutoGPT's peak it would have panic-abandoned into AutoGPT, which then collapsed.

The task document identifies this: _"what prevents a panicky abandonment on a false alarm? Need sharper definition."_

**What the doc should say instead:**

- "Categorically-better" should be operationalized: the alternative must exceed Envoy on _all four_ of the §8 primary-surface tests AND match Envoy's §4.1 non-goals (non-commercial, local-first, envelope-required-at-onboarding).
- Adoption metric should be demoted; replace with "sustained Foundation-Verified Envelope Library adoption" (cross-product, measures ecosystem lift).
- 12-month window should be replaced with "sustained 24 months OR a commitment to contribute back that Envoy can join."
- Add a "panic filter": at least 2 independent Foundation-unaffiliated stewards must confirm the alternative satisfies the thesis before sunset proceeds.

**Recommended action:** Rewrite §7 item 4 with a 5-test checklist the alternative must pass, a longer horizon, and a multi-steward confirmation gate.

---

### F-10 — HIGH — Foundation-hosted binary is de facto centralization risk to BET-3

**Quoted claim** (DECISIONS `ADR-0001`, which §3.3 and §4.1 item 5 inherit):

> `kailash-rs-bindings` (PyPI + Terrene open GitHub) — Python glue open; Rust core closed. Compiled `.so`/`.dylib`/`.pyd` freely redistributable. ... Hosted on Terrene open GitHub.

**Quoted claim** (§4.1 item 5, line 145):

> Envoy is not a commercial SaaS with a subscription. Foundation-stewarded open-source, Apache 2.0 code, CC BY 4.0 methodology. Third parties may run managed Envoy offerings; the Foundation will not operate a hosted consumer product.

**Cross-referenced claim** (BET-3, §5.3, lines 235–242):

> **Claim:** The "MY agent, MY keys, MY infra" identity statement is durable...

**Why this is a problem:** The task document frames this correctly: _"Phase 02 ships compiled Rust binaries from a Foundation-hosted repo. Is the 'Foundation-hosted open GitHub' dependency a de facto centralization risk that compromises BET-3 (sovereignty)?"_

Five structural risks the doc does not address:

1. **Foundation GitHub org delisting.** GitHub can delist an org for DMCA, ToS, export-control, government takedown. At that moment every Envoy installer that fetches from PyPI+Foundation hash breaks.
2. **PyPI registry failures.** Envoy distribution depends on PyPI being up and serving the binary. PyPI has had multi-hour outages.
3. **Binary signing key compromise.** If the Foundation's binary-signing key (the one the installer trusts for `kailash-rs-bindings` integrity verification) is compromised, every installed Envoy could be targeted by a supply-chain attack. There is no stated key-rotation / revocation mechanism for the binary (the Envelope Library has publisher-key rotation — the binding binary does not).
4. **Foundation reorganization.** The Foundation is a Singapore CLG. Organizational transitions (member resignation, member capture, charter amendment under duress) can happen. A hypothetical "Foundation 2.0" that inherits the GitHub org but has different priorities can change the binary distribution.
5. **Rust source lock-in.** Per ADR-0001, kailash-rs Rust source is held closed. Users cannot rebuild the binary independently. This makes the Foundation's binary-hosting the ONLY path to the default Envoy runtime. Opt-out to `kailash-py` exists, but F-05 and F-04 suggest kailash-py's primitive coverage is not audited.

"MY infra" per BET-3 rings hollow if MY-infra depends on THEIR-hosted-binary to run with the performance that made the sovereignty promise credible. The task document's phrasing is exact: _"a de facto centralization risk that compromises BET-3."_

**What the doc should say instead:**
§4.1 item 5 (or a new §4.1 item 14) should explicitly state:

- The Foundation's GitHub org hosting IS a single point of failure for the default runtime path.
- The `kailash-py` opt-in is the structural mitigation, BUT that mitigation is only credible when `kailash-py` is audited to equivalent safety + functional parity (see F-05 and F-04).
- A further mitigation (IPFS mirror / signed-binary torrent / third-party redistributor permitted by ADR-0001) may be required for true sovereignty.

**Recommended action:** Add a §4.1 sub-non-goal: "Envoy does not claim sovereignty-grade runtime independence until the Foundation binary distribution has at least N=3 independent mirrors AND a published key-rotation + binary-compromise response plan." This is an honesty move; it avoids the BET-3 disconfirmation firing unexpectedly at Phase 05 enterprise-buyer scrutiny time.

---

### F-11 — HIGH — Glossary terms drift from upstream reality

**Quoted claim** (§11, lines 523, 538, 539):

- **Trust Vault** — "The encrypted local store of signing keys, envelope state, posture history, and budget state. Recoverable via Shamir 3-of-5."
- **Cascade revocation** — "Revoking a grant at any point invalidates all downstream grants that derive from it, transitively."
- **Conformance vector** — "A cross-SDK test fixture asserting byte-identical behavior between `kailash-rs-bindings` and `kailash-py` for a single operation. Referenced as N1 / N2 / N3 / N4 / N5 / N6 per the PACT test-pattern nomenclature."

**Why this is a problem:**

1. **"Trust Vault"** — the kailash-rs survey has no entry for "Trust Vault" in the Python binding surface. There is a "trust-plane" module (§249: `trust_plane/mod.rs`, 126KB binding source — "file-backed trust projects, holds, bundles, shadow mode, conformance tests"). The term "Trust Vault" appears to be Envoy-new-scope. This should be named as new code in §3.3, and its storage format should not silently inherit unspecified EATP/PACT conventions.

2. **"Cascade revocation"** — per survey §457: _"Cascade revocation is NOT explicitly surfaced in the binding — must verify behavior against Rust source or implement at Envoy level."_ Glossary asserts a semantic (transitive downstream invalidation) that is NOT verified to exist in the binding. If Envoy must implement cascade revocation itself, it is new code per §3.3 that is not listed.

3. **"Conformance vector N1–N6"** — per survey §12: _"Python runner NOT YET IMPLEMENTED (esperie-enterprise/kailash-rs#317)."_ Only N1, N2 are landed per-language; N4, N5 are JSON vector format, N3 and N6 are not enumerated in the survey. "Conformance vector N1–N6" is an aspiration, not an extant substrate.

The rule `.claude/rules/terrene-naming.md` says: _"Inconsistent terminology across repos fragments institutional knowledge and makes cross-document search unreliable."_ The glossary should not introduce terms that bind to phantom upstream entities.

The rule `.claude/rules/specs-authority.md` MUST Rule 5 says: _"When domain truth changes during any phase, the relevant spec file MUST be updated immediately."_ The thesis doc is pre-spec, but this principle applies: glossary entries should be grounded in confirmed upstream reality.

**What the doc should say instead:**
Glossary entries should carry a "source" column with one of:

- _Shipped (Rust binding + Python binding confirmed)_ — use as-is.
- _Shipped (Rust only; Python runner pending)_ — flag.
- _Envoy-new-scope_ — flag as Envoy-contributed, list in §3.3 new-code.

Entries currently in the third category but not flagged: Trust Vault, Envoy Ledger (the name), Cascade revocation (the behavior), Boundary Conversation (the implementation), Grant Moment (the structure), Shared Household (the model), ENVELOPE.md, CO validator, Shamir 3-of-5, Daily Digest, Weekly Posture Review, Monthly Trust Report, Envelope Library. These are all new Envoy scope. The glossary should explicitly say so.

**Recommended action:** Add a "source" column to the §11 table. Run a reconciliation sweep with the kailash-rs survey + a new kailash-py survey (per F-05) before accepting the glossary.

---

### F-12 — HIGH — BET-6 falsifying evidence is unmeasurable at its own checkpoint

**Quoted claim** (§5.6, lines 286–289):

> **Falsifying evidence:**
>
> - Phase 02 conformance vectors reveal >20 semantic divergences between runtimes that cannot be closed by either side without architectural change.
> - Maintenance cost: >30% of Phase 02–03 engineering effort goes to parity maintenance, crowding out feature work.
> - User survey (indirect): <10% of users care that `kailash-py` is available; runtime picker is an irrelevant UX surface for most.

**Why this is a problem:** The kailash-rs survey directly states:

- Survey §270: _"PACT N4/N5 governance vectors — load JSON → reconstruct → canonical JSON equality assertions. Python runner NOT YET IMPLEMENTED."_
- Survey §321: _"Cross-SDK parity requires running conformance vectors on both — currently only Rust runs them."_

If the Python runner for the conformance vectors does not exist at Phase 02 start, BET-6's first falsifying-evidence bullet ("Phase 02 conformance vectors reveal >20 semantic divergences") cannot fire — there is no runner that can produce divergences to count.

BET-6's mitigation path says: _"Minor: publish the parity-gap catalog as a known-divergences doc..."_ — but this presupposes a catalog-producing mechanism exists. It does not.

Additionally, the third falsifying-evidence bullet ("<10% of users care that kailash-py is available") requires a user survey that F-08 already flagged is structurally hard under §4.1 item 7.

**What the doc should say instead:**
BET-6 mitigation path should include an explicit Phase 02 pre-gate: _"Implement the Python runner for PACT N1–N6 conformance vectors as a Phase 01 exit criterion OR a Phase 02 entry criterion. Without it, BET-6 is structurally non-falsifiable and Phase 02 cannot claim cross-runtime parity."_ This should be added to `ROADMAP.md` Phase 01 exit OR Phase 02 entry checklist.

**Recommended action:** Cross-reference this finding with BET-9 (F-03). Both bets share the same root cause: the upstream binding reality is not what the doc assumes. Add a Phase 00 or Phase 01 dependency task: "Python conformance-vector runner lands (closes kailash-rs#317)."

---

### F-13 — HIGH — Kill criterion §7.2 has a subjective escape hatch

**Quoted claim** (§7 item 2, line 390):

> **Multiple bets (≥3) in §5 disconfirmed simultaneously with no shared root cause.** Indicates the thesis misreads the market, not one variable.

**Why this is a problem:** "No shared root cause" is not an operational test. A Phase 03 team staring at disconfirmation evidence for BET-1 + BET-5 + BET-8 can always construct a plausible shared root cause ("prosumer adoption is seasonal", "ritual-formation needs more channels", "Grant Moment UX drifts with cloud model choice"). The shared-root-cause clause inverts the kill criterion: _any_ set of simultaneous disconfirmations can be narrative-collapsed into a single story that defers the kill.

This is a sunk-cost-capture pattern the doc otherwise critiques (§7 preamble: _"The point of naming these explicitly is to prevent sunk-cost capture."_).

**What the doc should say instead:**

- Drop the "shared root cause" escape hatch entirely. If 3 bets are disconfirmed at once, the thesis is abandoned — period. Team may construct a shared-root-cause narrative but it is a _post-mortem_ product, not a reprieve.
- Alternatively, tighten: "shared root cause" must be published as a specific named variable that, when fixed, would flip each disconfirmed bet to green. Filing that named variable blocks the kill for 6 months of targeted experimentation. After 6 months without flip, kill proceeds.

**Recommended action:** Replace §7 item 2's current wording with a hardened form. Consider also: the simultaneous-disconfirmation threshold (≥3) is itself arbitrary — 2 may be enough if they are BET-1 and BET-9, because those are the thesis-core and the primitive-sufficiency bets.

---

### F-14 — HIGH — §3.2 capability 11 (Trust Vault sync) is untraceable to phase exit

**Quoted claim** (§3.2 item 11, line 90):

> **Trust Vault sync** — opt-in, local-first; iCloud/Dropbox/Keybase/git/WebDAV/S3 integrations + native Foundation sync node.

**Cross-referenced:**

- §3.1 Phase 01 primitives do NOT list vault sync (only "Trust store" + "Shamir 3-of-5").
- §3.1 Phase 02 primitives do NOT list vault sync (lists `kailash-runtime` abstraction, bindings integration, conformance vectors, channel adapters, Flutter clients, SKILL.md translator).
- §3.1 Phase 03 primitives do NOT list vault sync.
- §3.1 Phase 04 primitives do NOT list vault sync.
- ROADMAP.md similarly does not name vault sync in any phase.
- ADR-0007 says "Envoy ships native Trust Vault sync..." but does not gate to a phase.

**Why this is a problem:** Per `.claude/rules/specs-authority.md` MUST Rule 3 (comprehensive truth), every advertised capability must have a phase-exit trace. Capability 11 is a feature claim with no phase home. A user reading §3.2 expects this to be in-scope; a PM reading §3.1 cannot find when it ships. This is the exact alignment-drift failure mode §1 says the thesis exists to prevent.

§3.2 closes with: _"That is the full product. Every downstream doc's schemas, state machines, and tests trace back to exactly these 17 capabilities."_ If a capability in the 17 has no phase home, the guarantee fails at the first downstream doc that asks "when?"

The task document's check item 5 asks: _"Every capability should trace to a phase exit. Every phase exit should trace to capabilities."_

**What the doc should say instead:**
Either (a) add a new column to §3.2 specifying the phase where each capability first ships, OR (b) expand the §3.1 primitives column per phase to cover every capability in §3.2.

Similar audits should be run for all 17 capabilities. A quick pass suggests capability 14 (Envelope Library browse / publish — mapped to Phase 02 Foundation-Verified tier + Phase 03 Community tier per §4.2) and capability 17 (Multi-principal / Shared Household — Phase 03 per §4.2) are mostly traced but the others need explicit check.

**Recommended action:** Add §3.2 "first ships in" column. Cross-verify all 17 rows against §3.1 and §4.2. Update `ROADMAP.md` if any row reveals a missing phase primitive.

---

### F-15 — HIGH — BET-10 lacks a failing-scanner counterfactual

**Quoted claim** (§5.10 falsifying evidence, lines 350–352):

> - Legal counsel identifies an unresolvable conflict (e.g. CC BY 4.0 attribution cannot be preserved through a specific distribution channel; export-control classification of the Rust binary crosses an ITAR boundary).
> - FOSSA / Snyk / Sonatype flag the composite license expression and Enterprise security teams block adoption on scanner output.
> - Foundation board declines to endorse runtime-pluggability on charter-compatibility grounds.

**Cross-referenced:**

- §5.10 mitigation minor: _"re-license the friction point..."_
- §5.10 mitigation major: _"drop the problematic layer — e.g. if the Rust compiled binary turns out to be legally untenable, Envoy ships `kailash-py` as default and the Rust hot path becomes a Phase 05 optional accelerator."_

**Why this is a problem:** The second falsifying bullet is a Phase 05 enterprise risk, not a Phase 02 signal. Enterprise procurement scanner checks happen when a specific enterprise evaluates; before Phase 05+ there is no enterprise evaluation. But BET-10 is structured as though the evidence accumulates continuously.

The mitigation major bullet — _"Envoy ships `kailash-py` as default"_ — conflicts with:

- F-05 (kailash-py safety audit pending)
- F-04 (kailash-py primitive coverage unverified)
- F-10 (kailash-py is the sovereignty fallback, not a performance path)

Switching defaults to kailash-py at Phase 02+ materially changes the product (slower hot path, missing primitives if audit reveals gaps). This is not a "minor" pivot; it is re-opening BET-6 (parity) and BET-3 (sovereignty) simultaneously.

**What the doc should say instead:**

- Add a falsifying-evidence bullet: _"By Phase 02 exit, the composite LICENSE + SPDX expression has not been validated against FOSSA/Snyk/Sonatype with zero critical findings on a test pipeline."_ This is measurable pre-enterprise-adoption.
- Expand the major mitigation to explicitly note the cross-bet interactions it triggers (BET-6 parity claim must be re-verified; BET-3 sovereignty narrative must be adjusted for the performance regression).

**Recommended action:** Tighten BET-10 with a Phase 02-measurable pre-flight test on composite license scanner cleanliness. Annotate the mitigation major as "reopens BET-3 and BET-6" so the team sees the cascade.

---

### F-16 — HIGH — §2.2 irreducibility claim ignores delegation-upward collapse

**Quoted claim** (§2.2, line 28):

> The irreducible human contribution is judgement about what the agent should not do, what it should pause for, what it should decline, and what it should escalate.

**Why this is a problem:** The claim asserts irreducibility without defending against the most obvious collapse mode: envelope authorship itself can be delegated. Consider:

- An enterprise buys Envoy licenses for 500 employees. IT authors one envelope. Employees accept. The envelope is now "signed by the user" but not _authored_ by the user. The irreducible-judgment claim reduces to "signed acceptance," which is one-click and does not represent user judgment.
- A family buys Envoy. Parent authors a household envelope. Children accept. Same collapse.
- A Foundation-Verified envelope template becomes so popular that 80% of users import it unchanged. The "envelope" is authored once, used by many — the authorship irreducibility dissolves into template-selection.

The §8 Test-1 allows imported templates as a legal onboarding path: _"Users may import a reputable Foundation-Verified envelope with one command."_ This IS the collapse mechanism.

If envelope authorship is delegable, then BET-1 ("boundary-setting is the irreducible human contribution") is actually wrong in a way the doc does not anticipate. The irreducible contribution is at most _consent to an envelope_, which is a fundamentally weaker claim because consent-to-template is just another form of agent-use, not agent-authorship.

**What the doc should say instead:**
§2.2 should address the delegation-upward collapse:

- Either defend authorship: require that every Envoy user personally produce at least one _novel_ envelope constraint beyond what the template provides, within the first 30 days of install (this would be measurable against template-fork counts).
- Or retract the irreducibility claim and replace it with a weaker claim: _"The minimum load-bearing human contribution is informed consent to an envelope. Envoy's thesis depends on making that consent dense enough to be meaningful — via the Boundary Conversation, Daily Digest review, and Weekly Posture Review — even when the envelope itself is imported."_

The weaker claim is still interesting; it just isn't "irreducibility of authorship."

**Recommended action:** Rewrite §2.2 with a precise statement about what is irreducible (authorship vs consent vs review), and address the enterprise/family delegation-upward case directly. This is arguably the #1 most-defensible-in-debate finding in this review.

---

### F-17 — MEDIUM — §3.2 capabilities list is unordered and unscoped by phase

**Quoted claim** (§3.2 opening, line 78):

> The product surface, once all three phases are complete, offers exactly these user-visible capabilities.

**Why this is a problem:** §3.2 presents capabilities 1–17 with no explicit phase tagging. A reader (and a future /todos session) has to cross-read §3.1 (phase primitives) and §4.2 (deferrals) to reconstruct which capability ships when. This is the lossy-compression failure mode `.claude/rules/specs-authority.md` Origin calls out (FM-1).

F-14 is a specific instance of this failure (Trust Vault sync capability with no phase trace). The general fix addresses both.

**What the doc should say instead:**
Add a "first phase" column:

| #   | Capability                         | First phase                                |
| --- | ---------------------------------- | ------------------------------------------ |
| 1   | Onboarding (Boundary Conversation) | 01                                         |
| 2   | Grant Moments                      | 01                                         |
| ... |                                    |                                            |
| 11  | Trust Vault sync                   | (TBD per F-14)                             |
| 12  | Channel connection                 | CLI/Web in 01; iMessage+5 in 02; +15 in 04 |
| ... |                                    |                                            |

**Recommended action:** Add the column. The act of filling it in will surface any additional F-14-class gaps.

---

### F-18 — MEDIUM — §3.3 new-code list omits algorithm-identifier scaffolding

**Quoted claim** (§4.1 item 9, line 149):

> **Envoy does not lock in a crypto algorithm.** Ed25519 for signing, SHA-256 for hashing, SLIP-0039 for Shamir — but the algorithm choices are architecturally separable, with algorithm identifiers in every signed artifact. If NIST deprecates SHA-256 tomorrow, we migrate; legacy records remain verifiable under their original algorithm tag.

**Cross-referenced** (§3.3 new code list, lines 117–129): no item for algorithm-identifier schema.

**Why this is a problem:** Algorithm-separable signed artifacts require:

- A versioned algorithm-identifier field in every signed record (Delegation, Posture, Audit, Grant).
- A resolver that can verify records signed under legacy algorithms.
- A migration path for in-flight Trust Vault state (re-sign all records? keep legacy signatures and sign the new log segment?).

This is non-trivial Phase 01 scope (especially if Phase 01 is the one setting the initial algorithm identifiers, since all Phase 01 records become "legacy" after any migration). It is not listed as new code in §3.3.

If Phase 01 skips the algorithm-identifier scaffolding and ships hard-coded Ed25519+SHA-256+SLIP-0039, the §4.1 item 9 claim is retroactively falsified — Phase 01 users have un-versioned signed artifacts that cannot be migrated cleanly.

**What the doc should say instead:**
Add to §3.3 new-code list: _"Algorithm-identifier schema + versioned signed-artifact format + legacy-verification resolver."_ This is Phase 01 scope if the §4.1 item 9 claim is to hold from day 1.

**Recommended action:** Add the new-code row. Verify Phase 01 exit criteria cover algorithm-identifier roundtrip (sign → migrate → verify both legacy and new).

---

### F-19 — MEDIUM — BET-5 falsifying evidence timeline conflicts with Phase 03 Shared Household

**Quoted claim** (§5.5, lines 272–275):

> **Falsifying evidence:**
>
> - Phase 02 adoption data: >80% of installs are single-user, never scale to multi-principal; no organic team-formation pattern.
> - Phase 03 Shared Household feature: <5% of single-user Phase 02 installers convert to multi-principal Shared Household use.
> - Enterprise security reviews block adoption at the individual level...

**Cross-referenced** (§4.2, line 166): _"Shared Household / multi-principal — Earliest phase 03 — Reason: Single-principal flow must be rock-solid before multi-principal semantics land."_

**Why this is a problem:** The second bullet requires evidence from the Phase 03 → Phase 02-installer conversion cohort. But at Phase 03 launch, the "single-user Phase 02 installers" are the users from the prior phase, a subset of whom may have moved on. The measurement window overlap is thin.

Additionally, the first bullet's ">80% single-user at Phase 02" is basically tautological — Phase 02 does not ship Shared Household (per §4.2), so ALL Phase 02 installs are single-user by construction. The falsifier is unfalsifiable because the feature literally doesn't exist yet.

**What the doc should say instead:**

- Bullet 1: retime to Phase 03 post-Shared-Household-launch. "Phase 03 post-launch: >80% of new installs use single-user mode, <5% convert to Shared Household in the first 3 months."
- Bullet 2: move timeline to Phase 04 or refine cohort measurement. "By Phase 04, <5% of Phase 02-cohort installers (who are still active) have added a second principal to their Shared Household."

**Recommended action:** Retime the falsifying evidence. Acknowledge that BET-5 is structurally measurable only Phase 03+.

---

### F-20 — MEDIUM — BET-4 "Foundation language reads bureaucratic" lacks instrument

**Quoted claim** (§5.4 item 3, line 257):

> Indie cohort feedback: "Foundation" language reads as bureaucratic / corporate / enterprise-y and alienates the vibe-aligned cohort.

**Why this is a problem:** The falsifying signal requires (a) knowing who the indie cohort is, (b) soliciting feedback, (c) coding that feedback along the "bureaucratic vs not" axis. Under §4.1 item 7 (no phone-home) and item 8 (no registration), (a) is impossible and (b) is opt-in slow. (c) is a research coding task with no proposed methodology.

This joins F-02 and F-08: multiple bets depend on user-feedback signals that the non-goals forbid the team from collecting.

**What the doc should say instead:**
Either demote the bullet (remove it from the falsifying-evidence list) or replace with an instrumentable proxy: _"Analysis of Envoy-mentioning HN/X threads over a rolling 12-month window: share of mentions that invoke 'Foundation' pejoratively (e.g. 'typical nonprofit bureaucracy', 'too corporate') exceeds 15%."_ This is measurable against public discourse without phone-home.

**Recommended action:** Replace subjective-cohort-feedback bullets across BETs 1, 3, 4, 5 with public-discourse proxies where possible.

---

### F-21 — MEDIUM — §9.4 anti-pattern 4 vs §3.2 capability 11 (Trust Vault sync)

**Quoted claims:**

- §9.4 anti-pattern 4 (line 447): _"Envoy's credentials for action live anywhere other than on the user's own device (→ trust is in the vendor, not in the user)."_
- §3.2 capability 11 (line 90): _"Trust Vault sync — opt-in, local-first; iCloud/Dropbox/Keybase/git/WebDAV/S3 integrations + native Foundation sync node."_
- §4.1 item 10 (line 150): _"Envoy does not persist anything outside the user's control. Every storage location is local by default. Sync, when enabled, is end-to-end encrypted with keys the user holds."_

**Why this is a problem:** §9.4's anti-pattern says absolute "anywhere other than the user's own device." §4.1 item 10 softens this with "local by default; sync is end-to-end encrypted." §3.2 capability 11 names four third-party sync targets (iCloud, Dropbox, Keybase, WebDAV, S3) — none of which is "the user's own device."

The reconciliation is supposed to be "keys the user holds" — if the keys never leave the device, encrypted ciphertext on iCloud is still user-sovereign. But §9.4 does not say "ciphertext"; it says "credentials for action." Unencrypted envelope state + encrypted signing keys is a grey area: the signing capability lives in the user's key, but the envelope + state blob are action-informing. An attacker who compromises iCloud + observes the envelope can plan an attack even if they can't sign.

The three sections are consistent but only if the reader carefully threads them. The thesis doc should state the reconciliation explicitly.

**What the doc should say instead:**
§9.4 anti-pattern 4 should be rephrased: _"Credentials or action-authorizing state are stored in any form — ciphertext or plaintext — by a third party in a manner that deprives the user of sole control. Ciphertext on a third party that the user could decrypt independently but the third party could not is a permissible configuration only when explicitly opt-in (per §4.1 item 10)."_

**Recommended action:** Tighten §9.4 anti-pattern 4 with the ciphertext carveout that §4.1 item 10 implies.

---

### F-22 — MEDIUM — BET-8 falsifying evidence requires deferred-phase features

**Quoted claim** (§5.8, lines 318–321):

> - Phase 02 instrumentation: <20% of active users open the Daily Digest twice in any 7-day window.
> - Weekly Posture Review engagement < 10% week-over-week.
> - Qualitative: users describe the rituals as "spam" or "another thing to check".

**Cross-referenced:**

- §4.2 puts Weekly Posture Review + Monthly Trust Report at Phase 03.
- §3.1 Phase 02 row does list Daily Digest (Phase 01 exit) but NOT Weekly Posture Review.

**Why this is a problem:** "Weekly Posture Review engagement < 10%" is a Phase 03+ signal, not Phase 02. And bullet 1 requires phone-home instrumentation (F-02 / F-08 family).

**What the doc should say instead:**

- Bullet 1: restate as an opt-in Grant Moment based telemetry signal OR a qualitative proxy (GitHub issue volume mentioning digest cadence, for example).
- Bullet 2: retime to Phase 03 post-launch.

**Recommended action:** Same pattern as F-08, F-19, F-20. Bets need to be retimed to phases where their measurement is possible.

---

### F-23 — MEDIUM — §4.3 Signal row may be legally-infeasible as Phase 02 channel

**Quoted claim** (§4.3 Signal row, line 189):

> | Signal / Matrix | "End-to-end encrypted messaging" | Envoy is the _sender_, not the transport. It composes over messaging apps that provide the transport. |

**Cross-referenced:**

- `ROADMAP.md` Phase 02 channels: "iMessage (BlueBubbles), Telegram, Slack, Discord, WhatsApp, Signal (plus CLI + Web from Phase 01)."

**Why this is a problem:** Signal's Terms of Service + signal-cli's license history mean third-party Signal clients are perennially fragile:

- Signal does not offer an official API for third-party clients.
- `signal-cli` (community tool) exists but Signal has been inconsistent about whether unofficial clients are acceptable.
- WhatsApp shares this problem at larger scale (Meta has sent cease-and-desist to multiple third-party-bot projects).
- iMessage requires BlueBubbles, which requires a Mac + a real Apple ID — not a broadly deployable Phase 02 path.

The §4.3 table entry is accurate as positioning (Envoy is sender, not transport) but does NOT address whether shipping the channel adapter is legally + technically feasible. This is a gotcha that §4 (non-goals) should pre-refuse OR §3.1 (phase primitives) should explicitly claim done pre-flight work on.

**What the doc should say instead:**
Add a §4.1 non-goal (or §4.3 footnote): _"Envoy's channel adapter availability is constrained by each platform's third-party-client policy. Channels where third-party adapters violate ToS or lack a stable technical path (currently: Signal, WhatsApp, iMessage non-BlueBubbles) are not guaranteed. The §3.1 Phase 02 channel list reflects technical intent; actual Phase 02 exit may ship a subset, with the remainder deferred pending platform developments."_

**Recommended action:** Add the caveat. Run an explicit Phase 02 feasibility check as a Phase 00 sub-gate.

---

### F-24 — MEDIUM — §10 dependency graph treats skill-ecosystem gates linearly

**Quoted claim** (§10 skill-ecosystem block, lines 482–488):

> ```
> Skill ecosystem
> ├── `SKILL.md` parser + `ENVELOPE.md` schema
> ├── CO validator
> ├── Permission-to-PACT-dimension translator
> ├── `force_install=True` UX
> ├── Envelope Library Foundation-Verified tier
> └── gates → Phase 02 exit (library) + Phase 03 exit (Community)
> ```

**Why this is a problem:** BET-7 explicitly names two failure modes for the CO validator: _too strict_ (rejects >50% of real skills) and _too loose_ (accepts adversarial). These are continuous tuning problems, not gates. The graph treats "CO validator" as a single box that either is or is not done. In reality, Phase 02 ships a validator that passes some threshold, and Phase 03 / 04 iterates.

The graph also does not capture the interaction between the validator and the Foundation-Verified tier (validator strictness tunes Foundation-Verified tier size) or the Community tier (Community tier stability depends on validator reliability, adversarial-skill immunity).

**What the doc should say instead:**
Add a §10 note: _"Skill ecosystem gates are continuous-tuning problems (BET-7). The graph shows the initial launch dependencies; CO-validator fidelity is an ongoing Phase 02+ workstream, not a single gate."_

**Recommended action:** Add the note. Consider a separate "tuning surface" diagram for validator fidelity.

---

### F-25 — MEDIUM — §3.1 Phase 01 exit requires independent ledger verification without tooling

**Quoted claim** (§3.1 Phase 01 exit, line 68):

> …a single user can onboard, operate for a week, back up the vault on paper, export a ledger, and verify it independently

**Cross-referenced** (§3.3 new code, lines 117–129): Envoy Ledger CLI is listed ("export, verify, grep, diff") but "independent verification" could mean: (a) a tool Envoy ships that uses a different code path than the writer, or (b) a tool a third party writes against the ledger format, or (c) the user visually inspects.

**Why this is a problem:** "Independent verification" without a shipped third-party-compatible verifier is just "verification by the product that made the ledger." For sovereignty-grade claims, this is circular. A ledger the Foundation can sign-off on is not the same as a ledger that is independently verifiable, and the thesis's sovereignty narrative (BET-3) is stronger if the latter is shown.

If Envoy wants "independent verification" to mean something, it needs to ship a separate minimal verifier tool (different codebase / repo / implementation language) OR specify the ledger format so well that third parties can write their own.

**What the doc should say instead:**
§3.1 Phase 01 exit should be one of:

- "...a minimal reference-verifier tool (different codebase than the writer) successfully verifies the exported ledger" — requires new code per §3.3.
- "...the ledger format is published (specs/ledger-format.md, CC BY 4.0) and Phase 01 exit includes at least one third-party-authored verifier having run against a real user's ledger" — requires external engagement.
- "...the user can visually inspect a human-readable ledger entry and confirm the hash chain by hand" — weakest, but a legitimate Phase 01 stepping stone.

**Recommended action:** Pick one and add to §3.1 Phase 01 exit. Add the verifier tool to §3.3 new code if the first option is chosen.

---

### F-26 — LOW — §6 CF-10 is already the Phase 01 state

**Quoted claim** (§6 CF-10, row 10):

> CF-10 | BET-10 disconfirmed (legal stack unsound) | Drop the friction layer; if Rust binary is the issue, `kailash-py` becomes sole default; Phase 02 ADR

**Cross-referenced:** `ROADMAP.md` Phase 01 line 37 — _"Ship as Python package (interim distribution, `kailash-py` runtime only)."_

**Why this is a problem:** Phase 01 already uses `kailash-py` as sole runtime. The counterfactual statement "kailash-py becomes sole default" could mean (a) Phase 01 state is preserved (already the case), or (b) Phase 02+ reverts to kailash-py-only (a real change from the planned pluggable-runtime path).

The ambiguity makes CF-10 hard to act on: if BET-10 disconfirms at Phase 02 entry, is the action "continue as Phase 01 was" or "make it permanent"?

**What the doc should say instead:**
CF-10 should specify the Phase 02+ behavior explicitly: _"CF-10: freeze on kailash-py as sole default for all phases. The runtime picker (§4.2 deferred item) is permanently removed. BET-6 (cross-runtime parity) is retroactively withdrawn. The Rust hot path becomes a Phase 05+ optional accelerator subject to separate licensing review."_

**Recommended action:** Rewrite CF-10 with explicit phase-level consequences.

---

### F-27 — LOW — §3.1 Phase 01 model adapter vs runtime adapter subtle gap

**Quoted claim** (§3.1 Phase 01 primitives, line 68):

> …Boundary Conversation, Grant Moments, Daily Digest, Envoy Ledger (hash-chained), Envelope compiler, Trust store, Budget tracker, **model adapter**, Shamir 3-of-5

**Cross-referenced:**

- §4.2 defers "Runtime pluggability (runtime picker)" to Phase 02.
- §3.2 capability 15: _"Runtime picker — first-run choice between `kailash-rs-bindings` (default) and `kailash-py` (opt-in); switchable post-install."_
- §3.2 capability 16: _"Model picker — local (Ollama/llama.cpp/MLX) or cloud (Claude/GPT/DeepSeek/custom OpenAI-compatible); switchable."_

**Why this is a problem:** "Model adapter" in the Phase 01 primitives list is the substrate for capability 16 (model picker). There is no "runtime adapter" in Phase 01 — correct, because runtime picker is Phase 02. But the primitive layer between Phase 01's hard-coded kailash-py and Phase 02's abstract kailash-runtime does need to be designed: either Phase 01 code writes directly to kailash-py and gets refactored at Phase 02 (adds Phase 02 scope), or Phase 01 pre-emptively writes against a simple one-runtime abstract interface (adds Phase 01 scope + some risk of wrong abstraction).

The doc doesn't name the choice. This is a Phase 00 decision that should surface.

**What the doc should say instead:**
Add to §3.1 Phase 01 primitives: _"(Phase 01 writes against kailash-py directly; the kailash-runtime abstraction lands in Phase 02. Phase 01 exit includes a refactor-risk note for Phase 02 entry.)"_ OR _"(Phase 01 writes against a minimal abstract runtime interface that makes Phase 02's pluggability drop-in.)"_

**Recommended action:** Choose one, document. The doc is not wrong without this; it is incomplete.

---

### F-28 — LOW — §11 glossary wording for `kailash-py` is ambiguous

**Quoted claim** (§11, line 533):

> **kailash-py** — Pure-Python Foundation runtime; Apache 2.0 + CC BY 4.0; fully forkable. Opt-in.

**Why this is a problem:** "Pure-Python Foundation runtime" could be read as _the_ runtime from the Foundation, which under ADR-0001 is wrong — `kailash-rs-bindings` is the default, also Foundation-hosted. The article "the" is not used, which avoids the error, but the phrasing is loose.

**What the doc should say instead:**

> **kailash-py** — The Terrene Foundation's pure-Python implementation of the CARE/EATP/CO/PACT specs. Apache 2.0 + CC BY 4.0; fully forkable. In Envoy, available as an opt-in alternative to the default `kailash-rs-bindings` runtime (from Phase 02).

**Recommended action:** Tighten the glossary entry with explicit scope + default-vs-opt-in framing.

---

## Cross-cutting observations (not individual findings)

### Recurring pattern: falsifying evidence depends on phone-home instrumentation the non-goals forbid

F-02, F-08, F-10, F-20, F-22 all flag the same pattern. The doc asks bets to fire on signals like "WAU", "retention", "%-of-users-doing-X", "cohort feedback" — and §4.1 items 7, 8, 11 explicitly forbid the infrastructure to collect those signals. This is a structural issue across §5 and §7.

Suggested remedy: add a dedicated §5.0 subsection _"Measurement methodology under §4.1"_ that enumerates:

- Signals the team CAN collect without phone-home (GitHub stars, envelope-library fetch counts, Discord mentions, HN thread sentiment, third-party blog mentions, opt-in survey responses).
- Signals the team CANNOT collect (WAU, retention, per-user behavior, conversion rates).
- Which bets rely on which signals — and which bets therefore become structurally unmeasurable without a new opt-in telemetry mechanism.

This subsection would anchor every bet's falsifying-evidence list.

### Recurring pattern: new-scope code not listed in §3.3 new-code list

F-11 (Trust Vault, Cascade revocation, etc. — glossary-named new code), F-14 (Trust Vault sync), F-18 (algorithm-identifier schema), F-25 (independent ledger verifier) all involve capabilities or concepts that require new Envoy code but are not listed in §3.3's new-code section.

Suggested remedy: a full audit of §3.2 capabilities against §3.3 new-code, with a per-capability "new code required" row.

### Recurring pattern: Kailash-rs survey contradicts primitive-sufficiency claims

F-03, F-04, F-05, F-11, F-12 all flag the same pattern. The doc consistently overstates what is already shipped in the Python binding. This makes the entire "~70% composed on primitives" ratio unreliable.

Suggested remedy: a Phase 00 gate adding two artifacts:

- `workspaces/phase-00-alignment/01-analysis/01-kailash-rs-survey-reconciliation.md` — for each primitive named in §3.3, cite the survey evidence that it is present/absent/stub in the Python binding.
- `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` — mirror survey of kailash-py (the Phase 01 runtime). Until this exists, §3.3 claims about kailash-py primitive availability are assertions, not audited facts.

Neither artifact is blocked by Phase 00 Foundation sign-off; both are probably 1 session each of careful reading.

---

## Suggested disposition

**Critical findings (F-01, F-02, F-03, F-04, F-05)** — MUST be addressed before the thesis doc is accepted as Phase 00 foundation. Three of the five (F-03, F-04, F-05) share a common root (upstream primitive reality diverges from thesis assumptions) and may be resolvable with one cross-cutting edit pass + the two new survey artifacts above.

**High findings (F-06 through F-16)** — SHOULD be addressed in the current Phase 00 cycle. F-06 (primary-surface test) and F-16 (authorship delegation) are the two that most deserve a debate-document treatment — they may generate substantive thesis changes.

**Medium / Low findings (F-17 through F-28)** — MAY be addressed inline as edits or deferred to a second review round. None is individually blocking, but several (F-14, F-17, F-18) reveal scope gaps that will compound if left.

**Overall status:** **Blocked**. The thesis as drafted cannot survive first-contact with either (a) user feedback on F-16 or (b) an engineering sprint that hits the F-03/F-04/F-05 primitive reality. These need resolution before sibling analysis docs start inheriting from this one.
