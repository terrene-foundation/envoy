# 00 — Thesis and Scope

**Document status:** **FROZEN v3 — cleared verification 2026-04-21** (0 CRIT + 0 HIGH across verification pass)
**v3 change summary:** Three targeted edits triggered by doc 09 Round 1 Cluster F: (1) §4.1 item 7 extended to include a second opt-in carveout — remote time anchor via quorum of public TSAs — to accommodate T-001 mitigation in doc 09 without breaking no-phone-home framing; (2) §4.1 item 9 gates Phase 01 exit explicitly on algorithm-identifier issue closure (mint#6 + kailash-py#604 + kailash-rs#519) OR Envoy-local implementation with sunset; (3) §8 Test-2 rewritten as two-phase signing (Phase A intent + Phase B outcome) to honestly model the tool-call pre-execution / post-execution window without weakening the "signed before execution" promise for intent.
**Date:** 2026-04-21
**Scope:** Foundational. Every sibling analysis doc inherits the thesis, vocabulary, and scope boundaries declared here.
**v2 change summary:** Cluster A–H from Round 1 consolidated pack applied inline. Primitive-inheritance table re-shaped as three-column parity status (pending deep audits). BET-9 split 9a/9b. New BET-12 (governance-primary-surface palatability). STAR/Prio/OHTTP aggregate telemetry with signed-consent Grant Moment added as narrow §4.1 carveout. Phase 01 expanded to 6 channels. Authorship Score + posture-ratchet gate landed as a structural primitive. §2.5 prior-art added. Phase 05 un-phased. Foundation/financial/GTM findings from adversarial review rejected as out-of-scope for a product thesis.
**Sources:** `CHARTER.md`, `DECISIONS.md`, `ROADMAP.md`, Round 1 consolidated pack at `workspaces/phase-00-alignment/04-validate/round-1-00-consolidated-pack.md`, the internal strategic brief at `workspaces/internal/openclaw-analysis/02-plans/superior-product-concept-2026-04-21.md`, internal red-team critique at `workspaces/internal/openclaw-analysis/04-validate/redteam-critique-2026-04-21.md`, and the kailash-rs binding survey at `workspaces/internal/kailash-rs-survey-2026-04-21.md`. Deep audits in progress at `01-kailash-rs-deep-audit.md` and `02-kailash-py-survey.md`.

---

## 1. Purpose of this document

This document is the single load-bearing artifact for _what Envoy is, why, and what it is not_. Every downstream analysis doc, spec, plan, and test fixture pulls its vocabulary, boundary conditions, and acceptance criteria from here.

A product with 23+ channels, a pluggable runtime, a federated registry, mobile apps, a recovery protocol, an audit ledger, and a skills ecosystem has a near-infinite scope attack surface. The only structural defense against scope creep is a thesis that is sharp enough to _refuse_ things — and a set of strategic bets whose _falsifiability_ is stated up-front so we know when to stop.

This doc is adversarially opinionated. It names concrete out-of-scope decisions (§4), names the bets we are making (§5), and names the conditions under which we abandon those bets (§6–§7).

## 2. The thesis, formalized

### 2.1 The question

> **What is the human for** in a world of autonomous AI?

This is not rhetorical. It is an engineering question whose answer determines the product surface. If the answer is _"prompting and reviewing outputs,"_ the product is a chat UI. If the answer is _"writing skills,"_ the product is a filesystem-native IDE. If the answer is _"approving actions one at a time,"_ the product is a workflow queue.

### 2.2 The answer

> **The irreducible human contribution is the authorship of boundaries — judgement about what the agent should not do, what it should pause for, what it should decline, and what it should escalate.**

Research, drafting, scheduling, coding, summarising, communicating — agents can perform these quickly, at scale, and increasingly better than the average human. The category of work that remains irreducibly human is _normative_: deciding what is acceptable, what is risky, what crosses a line, what requires a second pair of eyes.

This normative work has a specific mechanical form that Envoy gives first-class structure across five constraint dimensions — **Financial, Operational, Temporal, Data Access, Communication** (the canonical five, no synonyms, no reordering, per `rules/terrene-naming.md`):

- **A boundary** — a declared envelope of what the agent may do, under what conditions, at what cost, during what hours, with what data, with whom.
- **A grant** — a signed authorisation for an action the envelope does not already permit.
- **A posture** — a level of autonomy the user explicitly hands over, along a fixed 5-step posture slider.
- **A ledger** — a hash-chained record of every grant, action, refusal, and posture change.
- **A revocation** — a one-tap cascade that invalidates a grant and every descendant of it.

**Defense against delegation-upward collapse.** A common objection: "authorship can be delegated — enterprise IT authors one envelope for 500 employees; parents author for children; users import Foundation-Verified templates." If authorship is readily delegable, the irreducibility claim reduces to _consent to an envelope_, which is a fundamentally weaker claim.

Envoy addresses this **structurally**, not rhetorically: **the user cannot reach posture DELEGATING or AUTONOMOUS without personal authorship** (see §2.3, §3.3 Authorship Score primitive, §8 Test-5, BET-12). Template import is a starting point; the Boundary Conversation customizes it; the posture ratchet gates higher autonomy on personally-authored constraints. An enterprise bulk-licensing Envoy cannot skip each employee's authorship; each employee operates at TOOL posture until they author. A parent cannot bulk-grant a household envelope that keeps children at AUTONOMOUS; each child reaches DELEGATING only on their own authorship. The irreducibility is enforced by the product's posture gate, not asserted by copy.

### 2.3 The category move

Most "AI safety" products treat governance as an _additive layer_ — a bolt-on that runs after the model produces output. Envoy inverts this: **authorship of governance is the primary surface of the product, and everything else composes against it**.

Concretely:

1. **The first-run UX is not a settings page.** It is a Boundary Conversation that compiles an `EnvelopeConfig`. The user cannot complete onboarding without declaring boundaries. Template import is permitted but reframed as a _starting point_ — the conversation personalizes.
2. **Capability acquisition is not implicit.** Every new capability — install a skill, connect a channel, spend above the ceiling, contact a new person — goes through a Grant Moment with a signed record. Default-deny.
3. **Posture is gated on authorship.** To reach DELEGATING or AUTONOMOUS, the user's Authorship Score must be ≥ N (default N=3; configurable). PSEUDO / TOOL / SUPERVISED operate indefinitely on a pure-template envelope; higher autonomy requires personal authorship. This is the primary mechanical enforcement of the §2.2 claim.
4. **The audit log is not a compliance artifact.** It is the Envoy Ledger, a daily-use personal record the user inspects, diffs, commits, shares as receipts. Auditability serves the user first, then regulators second.
5. **Performance is a side-effect of structural governance.** Envelope membership checks (does this tool belong to the allowed set?) compile to O(1) hot-path lookups; semantic governance (does this action body fit the envelope?) is O(k) with per-LLM-call cost modeled explicitly (see BET-2, doc 05). Typed plan DAGs parallelise safely because every branch is envelope-verified at compile time.

### 2.4 Thesis statement (canonical, falsifiable)

> **The durable, defensible role of the human in autonomous AI is the authorship of envelopes. Products that ritualize this authorship — and structurally gate agent autonomy on it — will earn primary-surface loyalty that tool-frame AI products cannot. Envoy refuses to grant higher posture without authored constraints; this refusal is the thesis.**

This is a claim about users and the market, not about Envoy's architecture. It is falsifiable: if users prefer frictionless autonomy (Devin-class, fire-and-forget agent), or if template-import + one-click posture-max-out is preferred over authored-posture-ratchet, the thesis breaks. BET-1 and BET-12 make these falsifications explicit.

(The earlier draft's architectural sentence — _"the human holds a signed, revocable authority that every agent action traces to"_ — is true by construction and is retained as a _positioning statement_ in §8 rather than as canonical thesis.)

## 2.5 Prior art — what Envoy does structurally differently

Products that attempted to make governance the primary consumer surface are named here, with the mechanism by which each failed and what Envoy does differently. This section defends BET-12 (§5.12) and the §2.3 category-move claim.

| Product                                                   | Pattern                                                                                | Result                                                                                     | Envoy's difference                                                                                                                                                                                                                                    |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Little Snitch / LuLu** (macOS firewall per-app prompts) | Per-action approval prompts                                                            | ~0.5–2% of Mac users over 15 years; power-user tool                                        | Envoy declares envelope _once_ via Boundary Conversation; per-action prompts only for out-of-envelope events. Grant Moments are designed around authored envelope completeness, not per-call nagging.                                                 |
| **iOS App Tracking Transparency**                         | OS-gated per-app tracking prompts                                                      | Users decline ~95%+ when prompted; product shipped only because Apple made it non-optional | ATT succeeded because the OS forced the prompt. Envoy is a user-chosen product; we cannot force prompts. We instead **gate autonomy on authorship** — the user chooses to reach higher posture by authoring; unauthored users stay at TOOL by design. |
| **DuckDuckGo Privacy / Ghostery / Disconnect**            | Privacy-as-feature, governance invisible by default                                    | DuckDuckGo survived as a search engine, not a governance product. Ghostery niche.          | Envoy surfaces governance as the _primary_ UX but makes it _authoring_, not _approving_. Authoring is felt as agency; approving is felt as friction.                                                                                                  |
| **1Password / Bitwarden "auto-fill"**                     | Initial design was "approve every password use"; users toggle on auto-fill within days | Governance collapsed to zero-friction after the first week                                 | Envoy's Authorship Score is designed to persist — the ratchet to higher posture _requires_ continued authorship over the first 30 days, not a one-time event. Daily Digest + Weekly Posture Review (Phase 03) ritualize the re-authoring.             |
| **Google Account Security Dashboard**                     | Governance surface buried in settings                                                  | Used only when forced; ignored otherwise                                                   | Envoy's daily rituals (Digest, Grant Moment stream) pull governance forward. It is the surface you interact with, not one you navigate to.                                                                                                            |
| **Chrome extensions — uBlock Origin / AdBlock Plus**      | Governance _invisible_ by default; blocklist does the work; user never approves        | Huge adoption (~200M users) — but this IS the "governance invisible" pattern               | Envoy is deliberately _not_ governance-invisible. The thesis bets users are willing to pay the authorship cost for the authority dividend. BET-12 falsifies explicitly if authorship engagement is low.                                               |

**Envoy's three structural inversions:**

1. **Authorship-gated posture.** Unlike Little Snitch's per-action governance, Envoy's governance is _declarative + one-shot-but-recurring_ — declared in Boundary Conversation, re-examined in Weekly Posture Review, extended via Grant Moments. Each authorship event is ritualized.
2. **Template import is a starting point, not a shortcut.** Unlike 1Password's auto-fill collapse, Envoy's posture ratchet does not accept import as evidence of authorship. Users who only import stay at TOOL; DELEGATING requires authored constraints.
3. **The surface is inseparable from the substance.** Governance is not in a settings pane; every Grant Moment, every Daily Digest, every Posture Review is governance. The user never stops interacting with it.

**BET-12** (§5.12) falsifies the category-move on this prior-art pattern: if Envoy adoption rates fall into the Little Snitch band (≤2% of TAM) at 18 months, the structural inversions did not, in fact, invert the pattern. The thesis is niche-acceptable but not category-moving.

## 3. What Envoy IS (in-scope)

### 3.1 In-scope by phase (from `ROADMAP.md`, formalized for v2)

| Phase                                        | Goal                                                                                                                                         | Delivered primitives                                                                                                                                                                                                                                                                                                                                                                          | Exit is a product that…                                                                                                                                                                                    |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **00 Alignment**                             | concept locked, names verified, Foundation sign-off, legal counsel engaged on 7 ADR-0009 items, binding-gap GH issues closed or Envoy-scoped | deep audits + GH issue closure tracking; kailash-py + kailash-rs + mint sync                                                                                                                                                                                                                                                                                                                  | …passes every gate in `workspaces/phase-00-alignment/todos/phase-00.md` with no pending HIGH, every cited binding gap either closed upstream or explicitly scoped into Envoy-new-code                      |
| **01 MVP**                                   | prove the ritual loop on 6 channels end-to-end via pure-Python runtime; Authorship Score posture-gate live                                   | Boundary Conversation, Grant Moments, Daily Digest, Envoy Ledger (hash-chained), Envelope compiler, Trust store, Connection Vault, Budget tracker, model adapter, Shamir 3-of-5, Authorship Score + posture gate, Foundation Health Heartbeat (STAR/Prio + OHTTP + signed consent), **6 channel adapters (iMessage via BlueBubbles, Telegram, Slack, Discord, WhatsApp, Signal)** + CLI + Web | …a single user onboards via any of 8 channels, operates for a week across them, backs up the vault on paper, exports a ledger, and verifies it independently via a separately-codebased reference verifier |
| **02 Distribution**                          | single static binary, runtime picker, mobile onboarding, Envelope Library Foundation-Verified tier, SKILL.md translator                      | `kailash-runtime` abstraction, `kailash-rs-bindings` integration, conformance vectors (contract-parity), Flutter clients, SKILL.md → ENVELOPE.md translator, CO-compliance validator                                                                                                                                                                                                          | …a non-technical user completes install-to-first-value in <10 minutes on their phone (see §5.4 re first-value vs full-authorship distinction)                                                              |
| **03 Hot-path + rituals + multi-principal**  | Weekly Posture Review, Monthly Trust Report, Shared Household, Envelope Library Community tier                                               | Community tier publisher signatures, Weekly Posture Review ritual, Monthly Trust Report generator, Shared Household multi-principal data model, per-dimension posture slider (5 postures × 5 dimensions)                                                                                                                                                                                      | …a family of 5 operates a single Envoy with distinct envelopes per member, distinct Authorship Scores, and shared channels                                                                                 |
| **04 Channel breadth + Rust skills SDK**     | 15+ additional channels, Envelope Library Organization tier, Rust skills SDK (wasm sandbox)                                                  | 17 additional channel adapters, Apple Shortcuts, Calendar, browser extension, IDE extensions, voice, wasm skill sandbox, enterprise private registries                                                                                                                                                                                                                                        | …covers the messaging-channel surface most users care about + an enterprise-ready private registry                                                                                                         |
| **un-phased — Regulated-industry readiness** | Conditional on a third-party commercial operator taking on managed-Envoy deployment. Not on Envoy's own roadmap.                             | SOC2 Type 1 readiness (not certification — the operator's deployment certifies, not Envoy itself), HIPAA-ready architecture (Foundation is not a BAA party), GDPR DPIA tooling, Federated Trust Mesh spec                                                                                                                                                                                     | (N/A — Envoy core does not target regulated-industry certification; third-party operators may achieve it on their deployments)                                                                             |

**Phase-level clarifications:**

- **Phase 01 ≠ 3–5 sessions anymore.** The scope expansion to 6 channels, Authorship Score primitive, Foundation Health Heartbeat, Connection Vault, algorithm-identifier schema, and independent ledger verifier raises the Phase 01 estimate to **8–12 autonomous execution sessions**. User accepted "AT ANY COSTS" in exchange for shipping a thesis-demonstrable product at MVP.
- **Phase 01 re-scoping protocol (if the 8–12 session budget is exceeded).** If Phase 01 exceeds 15 sessions, re-enter §3.1 scope review. Pre-declared de-scope candidates, in order of preference: (1) reduce channel count from 6 to 3 (keep Telegram + Slack + Discord — bot-API clean; defer iMessage/WhatsApp/Signal legal-risk channels to Phase 02); (2) defer Foundation Health Heartbeat to Phase 02 entry (Phase 01 bets fall back to Public + Library substrates per §5.0); (3) defer Connection Vault third-party-OAuth integrations to Phase 02 (Phase 01 supports direct API-key paste via OS-keychain wrapper only). These de-scopes are sequenced to preserve the thesis-demonstrable MVP while relaxing the most legally-risky or infrastructure-heavy surfaces first.
- **Phase 05 is un-phased.** The Round 1 adversarial review correctly observed that Phase 05 bundled SOC2 + HIPAA + GDPR + SSO/SAML + Federated Trust Mesh into one phase at a month-9 target. That is unrealistic for a Foundation-stewarded project without a commercial operator, AND SSO/SAML/SCIM directly contradicts §4.1 item 8 (no hosted identity). Resolution: Envoy core does not target regulated-industry certification. Third parties may operate managed-Envoy and achieve certification on their own deployments; the Foundation is not a BAA/HIPAA party.
- **Phase 02 "first-value <10 minutes" vs §5 Boundary Conversation 15-minute.** These are distinct events and the doc must name both. **First value** = template import + one task through any channel, <10 minutes. **Full authorship** = Boundary Conversation + first 3 authored constraints + Shamir backup, multi-day progressive disclosure. Users are incented to complete full authorship by the posture-ratchet gate (§3.3 Authorship Score), not by an onboarding wizard gate.

### 3.2 In-scope by user-visible capability, phased

The product surface across Phases 01 through 03 offers exactly these capabilities. Anything outside is out of scope unless promoted via ADR. Each capability is tagged with its first shipping phase.

| #   | Capability                                                                                                                                                    | First phase                                                   |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| 1   | Onboarding — Boundary Conversation on first run (template import optional starting point)                                                                     | 01                                                            |
| 2   | Grant Moments — inline signed consent for out-of-envelope actions                                                                                             | 01                                                            |
| 3   | Daily Digest — morning summary per channel                                                                                                                    | 01                                                            |
| 4   | Weekly Posture Review — Sunday 90-second ritual                                                                                                               | 03                                                            |
| 5   | Monthly Trust Report — shareable one-pager                                                                                                                    | 03                                                            |
| 6   | Envelope editing — direct edit via any channel                                                                                                                | 01                                                            |
| 7   | Trust posture slider — 5-level (PSEUDO → TOOL → SUPERVISED → DELEGATING → AUTONOMOUS); whole-agent in Phase 01; per-dimension (5 × 5) in Phase 03+            | 01 (single); 03 (per-dimension)                               |
| 8   | Cascade revocation — one-tap revoke with transitive downstream invalidation                                                                                   | 01                                                            |
| 9   | Ledger inspection / export — grep, diff, git-commit, export PDF/JSON, independent-verifier run                                                                | 01                                                            |
| 10  | Trust Vault backup — Shamir 3-of-5 paper shards (SLIP-0039)                                                                                                   | 01                                                            |
| 11  | Trust Vault sync — opt-in, local-first; iCloud/Dropbox/Keybase/git/WebDAV/S3/native Foundation sync node (ciphertext at rest; user holds only decryption key) | 02 (sync node + sync protocol); 03 (third-party integrations) |
| 12  | Channel connection — CLI + Web + 6 messaging channels in Phase 01; 17 more in Phase 04                                                                        | 01 (8); 04 (23+)                                              |
| 13  | Skill install — SKILL.md ingest + ENVELOPE.md generation + CO validator + `force_install=True` override                                                       | 02                                                            |
| 14  | Envelope Library browse / publish — Foundation-Verified / Community / Organization tiers                                                                      | 02 (FV); 03 (Community); 04 (Org)                             |
| 15  | Runtime picker — `kailash-rs-bindings` (default) vs `kailash-py` (opt-in), first-run + post-install switchable                                                | 02                                                            |
| 16  | Model picker — local (Ollama/llama.cpp/MLX) + cloud (Claude/GPT/DeepSeek/custom OpenAI-compat)                                                                | 01                                                            |
| 17  | Multi-principal Shared Household                                                                                                                              | 03                                                            |
| 18  | **Authorship Score + posture-ratchet gate** — structural primitive enforcing §2.2 irreducibility claim                                                        | 01                                                            |
| 19  | **Foundation Health Heartbeat** — opt-in STAR/Prio + OHTTP + signed-consent anonymous aggregate telemetry                                                     | 02                                                            |
| 20  | **Connection Vault** — OS-keychain + Secure-Enclave wrapper for third-party credentials, per-principal isolated                                               | 01                                                            |
| 21  | **Algorithm-identifier schema** — versioned signed-artifact format + legacy-verification resolver                                                             | 01                                                            |
| 22  | **Independent reference-verifier tool** — ledger verifier in a separate codebase than the writer                                                              | 01                                                            |

**22 total capabilities** (up from 17 in v1; capabilities 18–22 are structural primitives the thesis requires that were not in the v1 list). Every downstream doc's schemas, state machines, and tests trace back to exactly these 22 capabilities.

### 3.3 In-scope by upstream primitive dependency — three-column parity status

**Status codes:**

- **✅ Confirmed** — present and functional; verified in deep audit.
- **⚠️ Unconfirmed** — referenced in survey; deep audit pending or inconclusive.
- **❌ Absent** — verified missing; GH issue filed.
- **🔧 Broken** — declared but non-functional (stub, wrong .pyi, SQLi surface, etc); GH issue filed.

**Deep audits concluded 2026-04-21.** Results synthesized at `workspaces/phase-00-alignment/01-analysis/03-primitive-reconciliation.md`. 39 GitHub issues filed at manifest `workspaces/phase-00-alignment/issues/manifest.md` — 19 on `esperie-enterprise/kailash-rs` (#503–#521), 13 on `terrene-foundation/kailash-py` (#594–#606), 7 on `terrene-foundation/mint` (#2–#8). Every issue cross-references its sibling(s) per the Foundation parity posture.

| Primitive                                                            | Source crate                   | `kailash-py` status                                                                                                                                           | `kailash-rs-bindings` status                                                                                                                                                                  | Envoy consumer                                             |
| -------------------------------------------------------------------- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `RoleEnvelope` / `TaskEnvelope`                                      | kailash-pact                   | ✅ `src/kailash/trust/pact/envelopes.py`                                                                                                                      | 🔧 Unbound — Rust source at `crates/kailash-governance/src/envelopes.rs:186` — kailash-rs#504                                                                                                 | Envelope compiler (doc 02)                                 |
| `intersect_envelopes()`                                              | kailash-pact                   | ✅ functional                                                                                                                                                 | 🔀 Different-name `ConstraintEnvelope::intersect()` at `crates/eatp/src/constraints/mod.rs:356` — kailash-rs#503; parity test kailash-py#594                                                  | Envelope compiler (doc 02)                                 |
| Trust Lineage: `TrustOperations`, Genesis, Delegation, Ed25519       | kailash / eatp                 | ✅ `src/kailash/trust/{chain,operations,signing}/`                                                                                                            | ✅ `EatpTrustOperations`, `EatpDelegationChain`, `EatpOrganizationalAuthority`, `EatpSignature`, `TrustKeyPair`                                                                               | Trust Lineage (doc 03)                                     |
| Cascade revocation                                                   | kailash / eatp                 | ✅ `src/kailash/trust/revocation/cascade.py` (BFS + atomic rollback)                                                                                          | ✅ `DelegationChain::revoke()` + `cascade_revoke()` at `crates/eatp/src/delegation.rs:807` (DFS); binding docs pending — kailash-rs#505, kailash-py#595                                       | Revocation primitive (doc 03)                              |
| Posture: `PostureStore`, `SQLitePostureStore`, `PostureEvidence`     | eatp                           | ✅ `src/kailash/trust/posture/`                                                                                                                               | ❌ Absent in Rust — kailash-rs#507; spec formalization mint#3                                                                                                                                 | Trust Posture (doc 01 §5.3, doc 10)                        |
| `EatpPosture` + Phase-13 type bundle (8 types)                       | eatp                           | ⚠️ partial — Phase-13 bundle completeness pending — kailash-py#597                                                                                            | 🔧 `.pyi` missing 8 types (BINDING-AUDIT B1) — kailash-rs#508                                                                                                                                 | Trust Posture                                              |
| `BudgetTracker` + microdollars + SQLiteBudgetStore                   | eatp                           | ✅ `src/kailash/trust/constraints/budget_tracker.py`                                                                                                          | ✅ `crates/kailash-kaizen/src/cost/budget.rs:80`; threshold callbacks missing — kailash-rs#518, kailash-py#603                                                                                | Budget primitive (doc 10)                                  |
| Audit: `TieredAuditDispatcher` + hash-chained anchors + SIEM export  | kailash-enterprise / eatp      | ❌ Absent — only `AuditLogger` — kailash-py#596                                                                                                               | ❌ Absent — only `AuditLogger` + `eatp::audit::AuditEvent/Filter` — kailash-rs#506; spec mint#2                                                                                               | Envoy Ledger (doc 04)                                      |
| DataFlow classification: `@classify` + `apply_read_classification()` | kailash-dataflow               | ✅ functional (internal API) — public-API exposure kailash-py#601                                                                                             | 🔀 `apply_read_classification()` at `crates/kailash-dataflow/src/classification.rs:76`; not bound — kailash-rs#514                                                                            | Classification surface (doc 09)                            |
| Nexus multi-channel + HMAC + Kaizen A2A                              | kailash-nexus / kailash-kaizen | ✅ A2A functional at `src/kailash/trust/a2a/service.py`; core channels (API/CLI/MCP) in `src/kailash/channels/`; social-messaging adapters absent (Envoy-new) | ⚠️ A2A methods declared but ⚠️ not implemented in binding (C6) — kailash-rs#517                                                                                                               | Channel adapters (doc 07)                                  |
| Kaizen `BaseAgent` + `LlmClient` + TAOD                              | kailash-kaizen                 | ✅ `packages/kailash-kaizen/src/kaizen/core/base_agent.py` — FULLY FUNCTIONAL                                                                                 | 🔧 `BaseAgent.execute()` raises `NotImplementedError`; 3/7 pre-built agents crash — kailash-rs#515                                                                                            | Boundary Conversation agent (doc 01)                       |
| Kaizen `OrchestrationRuntime`                                        | kailash-kaizen                 | ❌ Absent as specific class — kailash-py#602                                                                                                                  | 🔧 `.run()` returns static dict stub; Rust engine functional — kailash-rs#516                                                                                                                 | Scheduled rituals (doc 01)                                 |
| L3 Plan DAG + `PlanSuspension`                                       | kailash-kaizen/l3              | ✅ Plan DAG at `packages/kailash-kaizen/src/kaizen/l3/plan/`; ❌ `PlanSuspension` absent — kailash-py#598                                                     | ✅ Plan DAG at `crates/kailash-kaizen/src/l3/core/plan/types.rs`; `PlanSuspension` as `SuspensionReason`/`SuspensionRecord` — binding exposure kailash-rs#509; `.pyi` coverage kailash-rs#510 | Plan DAG (doc 01, 05)                                      |
| `Delegate` provider abstraction (LlmDeployment 4-axis, 18 presets)   | kailash-kaizen                 | ✅ Ollama/Claude/GPT/DeepSeek providers                                                                                                                       | ⚠️ Rust has 18 presets; binding surface pending — kailash-rs#511                                                                                                                              | Model picker (doc 06)                                      |
| MCP governance: `McpGovernanceEnforcer` + `McpGovernanceMiddleware`  | kailash-pact / kailash-mcp     | ❌ Absent — kailash-py#599                                                                                                                                    | ❌ Absent — kailash-rs#512; spec mint#4                                                                                                                                                       | Skill runtime (doc 08)                                     |
| MCP transports (stdio/SSE/HTTP) from Python                          | kailash-mcp                    | ⚠️ partial — `MCPChannel` only — kailash-py#600                                                                                                               | 🔧 Not bound (C4) — kailash-rs#513; spec extension mint#5                                                                                                                                     | Skill runtime / external MCP (doc 08)                      |
| DataFlow `execute_raw(params)`                                       | kailash-dataflow               | ✅ params pass through correctly                                                                                                                              | 🔧 **SECURITY: params silently dropped — SQLi surface (H4)** — kailash-rs#520 — **Envoy consumption of Rust binding BLOCKED until closed**                                                    | Raw SQL (doc 10)                                           |
| SessionMemory / SharedMemory / PersistentMemory                      | kailash-kaizen                 | ✅ functional                                                                                                                                                 | 🔧 `.pyi` method names wrong (`set/get/delete` vs actual `store/recall/remove`) — rolled into kailash-rs#521 .pyi regen                                                                       | Agent memory (doc 01)                                      |
| `.pyi` type stubs overall accuracy                                   | bindings/kailash-python        | (N/A — kailash-py is pure Python)                                                                                                                             | 🔧 ~55% accurate; 26 inaccuracies; 8 types missing — kailash-rs#521                                                                                                                           | Developer experience                                       |
| **Algorithm-identifier schema + versioned signed-artifact format**   | eatp (new)                     | ❌ Absent — kailash-py#604                                                                                                                                    | ❌ Absent — kailash-rs#519; spec mint#6                                                                                                                                                       | Crypto agility (doc 03, doc 04) — §4.1 item 9 load-bearing |
| **PACT N4/N5 conformance vector Python runner**                      | kailash-pact                   | ❌ Absent — **PHASE 02 BLOCKER** — kailash-py#605                                                                                                             | ✅ Rust runs `crates/kailash-pact/tests/conformance_vectors.rs`                                                                                                                               | Cross-SDK contract parity (doc 05)                         |
| **SLIP-0039 Shamir integration**                                     | (new)                          | ❌ Absent — kailash-py#606                                                                                                                                    | ❌ Absent — Envoy uses audited library directly                                                                                                                                               | Trust Vault backup (doc 03, doc 10) — spec mint#8          |
| **SKILL.md parser + ENVELOPE.md schema + CO validator**              | (new — Envoy owns impl)        | ❌ Absent                                                                                                                                                     | ❌ Absent — spec mint#7                                                                                                                                                                       | Skill ingest (doc 08) — Envoy Phase 02 scope               |

**Aggregate parity (23 primitive rows; counts exclude the single `.pyi`-stubs N/A row):**

- ✅ **Green on BOTH sides — 4:** Trust Lineage (row 3), Cascade revocation (row 4, binding docs pending on Rust side but functional), BudgetTracker (row 7, threshold-callback gap on both), L3 Plan DAG (row 13, `PlanSuspension` partial on both sides).
- ✅ **Green on kailash-py, needs work on kailash-rs — 9:** `RoleEnvelope`/`TaskEnvelope` (1), `intersect_envelopes` (2), PostureStore (5), DataFlow classification (9), Nexus multi-channel core (10), Kaizen `BaseAgent` (11), `Delegate` provider abstraction (14), `execute_raw` params (17, Rust-side SECURITY fix), SessionMemory (18). **Phase 01 is viable on kailash-py today.**
- ⚠️ **Partial on one or both sides — 2:** `EatpPosture` + Phase-13 type bundle (6), MCP transports (16).
- ❌ **Absent on BOTH sides — 5:** `TieredAuditDispatcher` (8), MCP governance (15), algorithm-identifier schema (20), SLIP-0039 Shamir (22), SKILL.md parser (23).
- ❌ **Absent kailash-py, stub on kailash-rs — 1:** `OrchestrationRuntime` (12).
- ✅ **Rust ahead of Python — 1:** PACT N4/N5 Python conformance runner (21). **Phase 02 BLOCKER.**
- (Excluded: `.pyi` stubs — N/A row for kailash-py; applies only to the Rust binding.)

**Phase 02 blockers (must close before Phase 02 opens):** kailash-py#605 (N4/N5 runner — otherwise BET-6 non-falsifiable) + kailash-rs#520 (SECURITY: `execute_raw` SQLi — otherwise Rust binding DataFlow is blocked from Envoy consumption).

**Composition claim (post-audit):** Phase 01 composes on kailash-py for the 12 fully-green + 1 partial rows (13/23 primitives). The 5 primitives absent on BOTH sides are Envoy-new or mint-spec + impl work, with GH issues filed (see above). The Rust-binding parity surface has 16 issues filed; Phase 02 entry depends on closing at least the Phase-02-critical subset (kailash-rs#520 + kailash-py#605 strictly; kailash-rs#504/505/507/509/515 for the Phase-02 pluggability claim).

**Envoy-contributed new code (distinct from upstream primitives):**

| Primitive                                                                                              | Rationale                                                                                                                                                                                                                                      | Phase                             |
| ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| **Boundary Conversation agent** (scripted Kaizen BaseAgent with Signature)                             | Onboarding ritual that compiles `EnvelopeConfig`; core of §8 Test-1                                                                                                                                                                            | 01                                |
| **Authorship Score primitive + posture-ratchet gate**                                                  | Structural enforcement of §2.2 irreducibility claim; prevents delegation-upward collapse                                                                                                                                                       | 01                                |
| **Connection Vault**                                                                                   | OS-keychain + Secure-Enclave wrapper; per-principal isolated; stores third-party credentials (API keys, channel tokens) separately from Trust Vault                                                                                            | 01                                |
| **Algorithm-identifier schema + versioned signed-artifact format + legacy-verification resolver**      | Realizes §4.1 item 9 crypto-agility claim; signed records carry algorithm tags; legacy records remain verifiable under their original algorithm tag                                                                                            | 01                                |
| **Independent reference-verifier tool**                                                                | Separate codebase from ledger writer; verifies hash chain + signatures; Ledger format published at `specs/ledger.md` under CC BY 4.0                                                                                                           | 01                                |
| **SKILL.md parser + ENVELOPE.md generator + CO-compliance validator**                                  | Phase 02 skill ingest                                                                                                                                                                                                                          | 02                                |
| **`force_install=True` UX + skill-inventory flagging**                                                 | Sovereignty-respect opt-out; force-installed skills visibly flagged in Ledger + envelope + skill inventory                                                                                                                                     | 02                                |
| **Channel adapters — 23+ total**                                                                       | Phase 01: 6 messaging channels (iMessage via BlueBubbles + Telegram + Slack + Discord + WhatsApp + Signal) plus CLI + Web = **8 total surfaces**. Phase 04: 17 more messaging channels (→ 23+ messaging total; 25+ surfaces counting CLI/Web). | 01, 04                            |
| **Cross-channel session continuity**                                                                   | User talks to Envoy in iMessage, continues in Telegram; same envelope, ledger, posture                                                                                                                                                         | 01                                |
| **`kailash-runtime` abstract interface crate** (Apache 2.0)                                            | Envoy's pluggability substrate                                                                                                                                                                                                                 | 02                                |
| **Runtime picker UX + first-run flow**                                                                 | Default `kailash-rs-bindings`; opt-out to `kailash-py`; switchable post-install                                                                                                                                                                | 02                                |
| **Shamir 3-of-5 ritual + CLI/Web UX + shard-rotation ritual**                                          | SLIP-0039 via audited library; Phase 01 shard-holder onboarding + shard-rotation for life-event changes                                                                                                                                        | 01                                |
| **Trust Vault sync adapters**                                                                          | Native Foundation sync node + 5 third-party integrations (iCloud, Dropbox, Keybase, git, WebDAV, S3); ciphertext at rest; user holds only decryption key                                                                                       | 02 (native); 03 (third-party)     |
| **Foundation Health Heartbeat client + STAR/Prio aggregator + OHTTP relay + DP-budget publisher**      | Opt-in anonymous aggregate telemetry via signed-consent Grant Moment; structural sovereignty preservation (§4.1 item 7 narrow carveout)                                                                                                        | 02                                |
| **Daily / Weekly / Monthly ritual schedulers**                                                         | Kaizen scheduled agents (or Envoy-scheduler if OrchestrationRuntime remains a stub)                                                                                                                                                            | 01 (daily); 03 (weekly/monthly)   |
| **Envoy Ledger CLI** (export, verify, grep, diff, cascade-revoke)                                      | Primary user-facing ledger affordance                                                                                                                                                                                                          | 01                                |
| **Mobile clients (Flutter)**                                                                           | iOS + Android; QR-code pairing with local Envoy instance                                                                                                                                                                                       | 02                                |
| **Single-binary installer** (`curl \| sh`, `brew`, `winget`, `cargo install`)                          | Phase 02 distribution surface                                                                                                                                                                                                                  | 02                                |
| **Envelope Library registry backend** (Foundation-Verified → Community → Organization tiers)           | Nexus-backed HTTP/CLI/MCP surfaces + Ed25519 publisher signatures + content-addressed storage                                                                                                                                                  | 02 (FV); 03 (Community); 04 (Org) |
| **Shared Household data model + per-principal envelope + per-action consenting-principal attribution** | Phase 03 multi-principal                                                                                                                                                                                                                       | 03                                |
| **Foundation binary distribution mirrors + binary-signing key rotation plan** (per §4.1 item 15)       | Sovereignty-grade structural mitigation against single-point-of-failure on Foundation GitHub                                                                                                                                                   | 02                                |

**Provenance note:** The v1 "~70% of Envoy's functionality composes on shipped Foundation primitives" ratio is superseded by the concrete three-column parity grid above. Post-audit count is given in the aggregate-parity bullets immediately above the Envoy-new-code table. Phase 01 composability claim is operationalized as "13 of 23 primitive rows are green or partial on kailash-py and usable without upstream repair." GH issue closure on `esperie-enterprise/kailash-rs` determines the composable share on the Rust runtime path; Phase 01 does not depend on that closure (kailash-py sole runtime).

## 4. What Envoy is NOT (non-goals)

### 4.1 Hard non-goals (never in any phase)

1. **Envoy is not a model.** We do not train, fine-tune, or host an LLM. Envoy composes over provider-agnostic Kaizen `Delegate` / `LlmDeployment`. Bundled model weights per-release are a shipping decision, not a product category.
2. **Envoy is not a chat UI.** The channels are the UI. CLI + Web are onboarding and admin affordances from Phase 01; channel-native daily use is the intended surface.
3. **Envoy is not a workflow canvas.** Kaizen L3 Plan DAGs are declarative artifacts emitted in response to intent; inspectable in the Ledger; not a drag-and-drop surface. Users declare _intent_, not steps.
4. **Envoy is not an agent marketplace.** Skills and envelopes are shareable; agents-as-products are not. The _agent_ is Envoy itself, one per user (or household).
5. **Envoy is not a commercial SaaS with a subscription.** Foundation-stewarded Apache 2.0 code + CC BY 4.0 methodology. Third parties may run managed Envoy offerings; the Foundation will not operate a hosted consumer product.
6. **Envoy is not an ops / SRE tool.** We do not compete with CNCF Envoy Proxy, monitoring platforms, or incident-response systems. Legal disambiguator per ADR-0002.
7. **Envoy does not phone home — except for two opt-in, cryptographically-scoped carveouts, each consented via a signed Grant Moment.** No telemetry, no crash-report pipeline, no install analytics as default behavior. Two narrowly-scoped exceptions, each a separately-signed Grant Moment (cascade-revocable):
   - **7a. Foundation Health Heartbeat** (§3.3 new-code, §5.0 measurement methodology, forthcoming ADR). STAR/Prio encrypted reports + differential-privacy noise + Oblivious HTTP relay to guarantee k-anonymity and IP-level unlinkability. First-run default: opt-out.
   - **7b. Remote time anchor for Temporal envelope enforcement** (Phase 02, T-001 in doc 09). Queries a quorum of public time-stamp authorities (FreeTSA + DigiCert + Apple trust roots, ≥ 2 of 3 required). Signed timestamp becomes a Ledger anchor record. No user-identifying payload sent; request is Envoy-version + quorum-request only. Rate-limited (hourly cadence default). First-run default: opt-out; user enables via a distinct Grant Moment after opt-in to Heartbeat (the two are not bundled).
     Both carveouts are structurally scoped: each has a distinct, auditable cryptographic property. Revoking either is cascade-revocable without affecting the other. Users who decline both have Envoy run fully offline from first-run onward.
8. **Envoy does not require registration.** No user account, no email, no signup, no waitlist, no hosted identity. Identity is the user's Genesis Record, generated locally, owned locally.
9. **Envoy does not lock in a crypto algorithm.** Ed25519 for signing, SHA-256 for hashing, SLIP-0039 for Shamir are current. Every signed artifact carries an explicit algorithm identifier; legacy records remain verifiable under their original algorithm tag (implemented via §3.3 "Algorithm-identifier schema" new-code). **Phase 01 exit gates** on either (a) closure of `terrene-foundation/mint#6` (spec) + `terrene-foundation/kailash-py#604` (impl) + `esperie-enterprise/kailash-rs#519` (impl), OR (b) Envoy-local algorithm-identifier implementation with a documented upstream-merge sunset. Phase 01 CANNOT ship hard-coded Ed25519+SHA-256 without algorithm tags — all legacy records under that shortcut would become un-migrateable and the claim collapses retroactively. Status tracked in `workspaces/phase-00-alignment/issues/manifest.md`.
10. **Envoy does not persist anything outside the user's control** — ciphertext-at-rest carveout. Every storage location is local by default. Sync, when enabled, is end-to-end encrypted with keys the user holds. Ciphertext on a third-party store (iCloud, Dropbox, Keybase, S3, WebDAV, git) is a permissible configuration _only_ when: (a) explicitly opt-in, (b) user holds the sole decryption key, (c) the ciphertext format does not leak action-informing metadata.
11. **Envoy does not support untrusted multi-tenant operation by design.** Shared Household is a _cooperative_ multi-principal; every principal is named in the Genesis chain. Adversarial multi-tenant (one user attempting to compromise another) is **in scope for doc 09** (household-adversarial threat class: divorce, elder-abuse, teen-rebellion, DV, coerced unlock, death-of-principal). Doc 09 owns mitigations.
12. **Envoy is not a password manager.** Third-party credentials (API keys, channel tokens, OAuth refresh tokens) live in the **Connection Vault** (§3.3 new-code) — OS keychain wrapper on desktop, Secure Enclave wrapper on mobile, per-principal isolated. Envoy's Trust Vault stores _only_ Envoy's own keys and envelope state; the Connection Vault is a separate primitive.
13. **Envoy is not a general-purpose code executor.** Skills run sandboxed (Python-subprocess + PACT enforcement Phase 01–03; wasm Phase 04). Arbitrary host-system code execution from a skill is structurally blocked.
14. **Envoy core does not ship SSO/SAML/SCIM.** §4.1 item 8 (no hosted identity) wins. Third-party commercial operators of managed-Envoy offerings may add hosted-identity connectors; Envoy-core does not. The consequence: Envoy core is not directly consumed by enterprises that require SSO at the individual-device level; individual adoption works, org-wide enterprise rollout requires a managed-Envoy operator.
15. **Envoy's default binary distribution is not single-point-of-failure.** The Foundation-hosted `kailash-rs-bindings` binary is one source; Envoy releases are structurally required to ship with at least N=3 independent mirrors (e.g., IPFS pinned nodes + community redistributors + secondary package registries), a published binary-signing-key rotation cadence, and a binary-compromise response plan. The `kailash-py` opt-in is the additional structural mitigation. Until these are in place (Phase 02 exit), Envoy does not claim sovereignty-grade runtime independence for the default Rust path — only for the `kailash-py` opt-in.
16. **`force_install=True` is sovereignty-respect, not a safety feature.** The flag allows CO-validator bypass on skill install with explicit warning. Users who use it have waived the product's governance promise for that skill. Force-installed skills are visibly flagged in the Ledger, in the envelope, and in the skill inventory. Envoy does NOT claim protection against skills installed with `force_install=True`.

### 4.2 Deferrals (not Phase 01; defined phase home)

| Deferred item                                                                                                                                                                                                                 | Earliest phase | Reason                                                                                         |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- | ---------------------------------------------------------------------------------------------- |
| Rust binary distribution (single `curl \| sh`)                                                                                                                                                                                | 02             | Phase 01 ships `pipx install envoy-agent` to validate UX loop on all 8 channels first          |
| Runtime pluggability (runtime picker + `kailash-runtime` abstraction)                                                                                                                                                         | 02             | `kailash-runtime` crate lands in Phase 02                                                      |
| Mobile clients (Flutter)                                                                                                                                                                                                      | 02             | Desktop + 6 channels in Phase 01; mobile adds QR-pairing and native clients                    |
| Envelope Library Foundation-Verified tier                                                                                                                                                                                     | 02             | Phase 02                                                                                       |
| SKILL.md ingest + ENVELOPE.md translator + CO validator                                                                                                                                                                       | 02             | Phase 02                                                                                       |
| Envelope Library Community tier                                                                                                                                                                                               | 03             | Requires publisher signing infrastructure matured in FV tier                                   |
| Shared Household / multi-principal                                                                                                                                                                                            | 03             | Single-principal must be solid first                                                           |
| Per-dimension posture slider (5 × 5)                                                                                                                                                                                          | 03             | Phase 01 ships whole-agent slider                                                              |
| Weekly Posture Review ritual                                                                                                                                                                                                  | 03             | Needs weeks of ledger history to be meaningful                                                 |
| Monthly Trust Report ritual                                                                                                                                                                                                   | 03             | Needs a month of ledger history                                                                |
| Trust Vault third-party sync integrations (iCloud, Dropbox, Keybase, WebDAV, S3)                                                                                                                                              | 03             | Phase 02 ships native Foundation sync node + sync protocol; Phase 03 adds third-party adapters |
| 17 additional channels (Matrix, Feishu, LINE, Mattermost, WeChat, QQ, Teams, Google Chat, IRC, Nostr, Twitch, Tlon, Zalo, Nextcloud Talk, Synology Chat, Apple Shortcuts, Calendar, browser extension, IDE extensions, voice) | 04             | Breadth is Phase 04                                                                            |
| Rust skills SDK (wasm sandbox)                                                                                                                                                                                                | 04             | Python-subprocess + PACT enforcement suffices through Phase 03                                 |
| Envelope Library Organization tier                                                                                                                                                                                            | 04             | Enterprise private registries                                                                  |
| Federated Trust Mesh (cross-org delegation)                                                                                                                                                                                   | un-phased      | Conditional on commercial operator                                                             |
| SOC2 Type 1, HIPAA, GDPR DPIA, SSO/SAML/SCIM                                                                                                                                                                                  | un-phased      | Envoy core does not certify; third-party managed-Envoy operators may                           |

### 4.3 Adjacent-product demarcation — what Envoy is NOT mistaken for

| Adjacent                              | Pattern-match                                 | Envoy's categorical difference                                                                                                                                                                                             |
| ------------------------------------- | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AutoGPT / BabyAGI / Smol Developer    | Autonomous agent loops on a goal              | Envoy does not accept a goal without an envelope. The envelope precedes the agent.                                                                                                                                         |
| Devin / Cognition / OpenDevin         | Coding agent writes code for you              | Envoy is not a coding agent; coding skills compose but are not the primary surface.                                                                                                                                        |
| ChatGPT / Claude Desktop / Perplexity | Chat UI for an LLM                            | Envoy is channel-native; primary surface is Grant Moment, not chat thread.                                                                                                                                                 |
| Zapier / Make / n8n                   | Workflow automation                           | Envoy is agent-driven (declared intent), not flow-driven (drawn connections).                                                                                                                                              |
| Langchain / LlamaIndex                | LLM-app framework                             | Envoy is a shipped product, not a framework.                                                                                                                                                                               |
| 1Password / Bitwarden                 | Vault for secrets                             | Envoy Trust Vault stores Envoy's own keys + envelope state. Third-party credentials live in Connection Vault (§3.3) — a different primitive with Shamir-separate recovery.                                                 |
| Tailscale / Headscale                 | Zero-config overlay network                   | Trust Vault sync is orthogonal; Envoy is not networking.                                                                                                                                                                   |
| HashiCorp Vault / AWS IAM             | Enterprise secret/access management           | Envoy is individual-first. Shared Household = family, not 10k employees. Enterprise = managed-Envoy operator, not Envoy core.                                                                                              |
| Signal / Matrix                       | E2E encrypted messaging                       | Envoy is the _sender_; it composes over messaging apps that provide transport. Phase 01 Signal channel adapter depends on signal-cli or the Signal Group Link + webhook path; adapter feasibility per Phase 01 legal gate. |
| iPhone Shortcuts / Tasker             | Local automation on device                    | Envoy's locality is a _consequence_ of sovereignty, not the product.                                                                                                                                                       |
| **CNCF Envoy Proxy**                  | Network-layer proxy / service-mesh data-plane | Envoy Agent is application+identity layer, not network+service-mesh. Legal mark disambiguation (ADR-0002).                                                                                                                 |

## 5. Strategic bets and falsifiability

### 5.0 Measurement methodology under §4.1 (new in v2)

§4.1 item 7 forbids phone-home telemetry by default; §4.1 item 8 forbids hosted identity. Under v1, BET-1/3/4/8 and §7 kill criteria required user-behavior signals these non-goals forbid the team from collecting. v2 resolves this via the **Foundation Health Heartbeat** — an opt-in anonymous aggregate-telemetry mechanism described below, which becomes the measurable substrate for the bets. Bets that do not rely on the Heartbeat use public-discourse proxies. The substrate choices are named here so every bet's falsifying evidence is grounded in an actually-collectible signal.

**Foundation Health Heartbeat design (adopted in v2, to be detailed in its own ADR):**

1. **Report-encoding layer — STAR (Signer-Anonymous Reporting Telemetry) or Prio.** Client splits each report into encrypted shares; collector(s) aggregate without ever seeing individual values. Enforces **k-anonymity** (k ≥ 100) at protocol level — reports that would be globally unique are discarded client-side before transmission.
2. **Differential-privacy noise** on each counter; ε selected per-metric; budget published.
3. **Transport — Oblivious HTTP (OHTTP, RFC 9458).** Foundation operates a Key Configuration Server; a separate (optionally third-party) Relay strips source IPs before forwarding to the Foundation aggregator. IP-level unlinkability is structural.
4. **Consent layer — signed Grant Moment.** User's opt-in to Heartbeat is a signed Delegation Record in the Ledger. Cascade-revocable. Grant Moment text names the cryptographic properties explicitly. First-run default: **opt-out**.
5. **Payload.** Per-install random ID (rotated quarterly), Envoy version, ~20 boolean flags (completed Boundary Conversation / opened Daily Digest this week / ≥1 Grant Moment approved / force-installed a skill / reached posture X / Authorship Score bucket / etc). All aggregated via STAR before reaching the Foundation.

**Signals the team CAN collect** (no violation of §4.1):

- STAR-aggregated Heartbeat counters (opt-in, k-anonymous, DP-noised).
- GitHub stars / forks (public).
- Envelope Library Foundation-Verified fetch counts (Foundation-operated; counts only, no identity).
- Envelope Library publish counts (signed publisher keys; pseudonymous).
- Public discourse: HN / X / blog posts / forum mentions (manual or RSS-aggregated).
- Opt-in user interviews recruited through Foundation Discord / forum.
- GitHub issue volume and themes.

**Signals the team CANNOT collect** (would violate §4.1):

- Individual-user WAU (only aggregate-via-STAR).
- Per-install retention curves (only aggregate cohort buckets).
- Per-user behavior sequences.
- IP addresses, device identifiers, demographic inference.

**Consequence for §5 bets:** every falsifying-evidence bullet below specifies which measurement substrate it uses. Bullets tagged `[Heartbeat]` require Phase 02 Heartbeat availability. Bullets tagged `[Public]` use public-discourse proxies. Bullets tagged `[Library]` use Envelope Library fetch/publish data. Kill criteria in §7 use the same tagging.

### 5.1 BET-1 — The authorship thesis holds

**Claim:** Enough users value _authoring_ envelopes (not merely consenting to imported templates) that the Authorship Score posture-gate is a felt authority, not a barrier.

**Falsifying evidence:**

- [Heartbeat] At Phase 02 cohort evaluation, <20% of active users have Authorship Score ≥ 3 at 30 days post-install. Template-only retention indicates import collapses the thesis.
- [Heartbeat] Median Authorship Score across active cohort remains <1 for >60 days.
- [Library] Foundation-Verified template fetch count ≫ publish count on Community tier: users consume, never author.
- [Public] Qualitative: HN / forum thread sentiment clusters around "I just imported the default, it's fine" rather than "the authorship ritual made me feel X."

**Mitigation path:**

- **Minor:** Soften the ratchet — lower default N from 3 to 1 or 2. Measure whether Authorship Score > 0 at 30 days rises.
- **Major:** Re-scope from "authorship gate on DELEGATING" to "authorship gate on AUTONOMOUS only." Allow DELEGATING on template-only. The thesis softens but survives.
- **Kill:** See §7.

### 5.2 BET-2 — Structural governance compiles to performance; semantic governance has a per-call budget

**Claim:** Pre-compiled envelope membership checks (is this tool in the allowed-tools set? is this recipient in the contact allowlist?) compile to O(1) hash-set lookups on the hot path. Semantic envelope checks (does this action body fit the Data Access dimension? does this email's content cross the "no tax info" line?) are NOT O(1) — they require per-call LLM classification. v2 explicitly partitions these and assigns separate latency budgets.

**Latency budgets (targets, to be validated in Phase 02):**

| Check class                                       | Example                                               | P50 target                                      |
| ------------------------------------------------- | ----------------------------------------------------- | ----------------------------------------------- |
| Structural (hash-set membership)                  | Tool-in-envelope, recipient-in-allowlist, posture ≥ X | <5ms                                            |
| Arithmetic (Financial dimension)                  | Is this spend within budget?                          | <5ms                                            |
| Comparison (Temporal dimension)                   | Is current-time in allowed-hours?                     | <1ms                                            |
| Semantic (Data Access dimension)                  | Does body contain tax info / classified field?        | <500ms (LLM classification, cached per-session) |
| Semantic (Communication dimension, content-aware) | Does message body include PII about person X?         | <500ms                                          |

**Falsifying evidence:**

- Phase 02 benchmark: structural-check P50 > 20ms on standard Grant-Moment workflow.
- Phase 02 benchmark: semantic-check P50 > 1000ms even after per-session caching.
- Implementation experience: semantic checks cannot be cached because of per-call dynamic inputs, forcing LLM classification on every action.

**Mitigation path:**

- **Minor:** Publish honest numbers; demote "governance as source of speed" from USP to engineering note; keep the thesis.
- **Major:** Envelope compiler becomes batch-aware (pre-classify common message templates, action patterns, contact lists at compile time); per-action cost drops.
- **Kill:** If pure-Python runtime is >500ms P50 on structural-check workloads, the cross-runtime parity claim breaks because users cannot meaningfully opt out.

### 5.3 BET-3 — Sovereignty is a durable emotional moat (trajectory-aware)

**Claim:** "MY agent, MY keys, MY infra" identity statement is durable — it survives the next 3–5 years of the AI market and supports a Foundation-scale product.

**Trajectory awareness (v2 addition):** Cloud-convenience gravity is not static. LLM inference cost fell ~30–100× between 2023 and 2025; OS-integrated agent primitives (Apple Intelligence, Gemini-in-Android, Copilot-in-Windows) are shipping. The sovereignty cohort's relative weight is a moving target.

**Falsifying evidence:**

- [Heartbeat] Phase 02 opt-in install-survey Grant Moment: <30% of respondents cite sovereignty-language reasons for choosing Envoy.
- [Public] Phase 03 trajectory check: if OS-integrated agent products ship envelope-equivalent governance (user-declared constraints + signed action records + cascade revocation) within 24 months of Phase 01, the differentiator narrows to "users who distrust their OS vendor" — a cohort smaller than the sovereignty-product base rate.
- [Library] Envelope Library Community tier publish velocity stalls below 10 new envelopes/month at 18 months.

**Mitigation path:**

- **Minor:** Accept niche-product reality; pursue the serviceable cohort; do not attempt to convert cloud-native mainstream.
- **Major:** Re-frame product thesis from "sovereignty-first" to "authorship-first"; the authorship story may survive even when sovereignty narrative narrows. Authorship is orthogonal to cloud vs local.
- **Kill:** If OS-integrated products ship full envelope + cascade-revocable delegation + authored posture-gate, Envoy has no structural differentiator. See §7.

### 5.4 BET-4 — Foundation stewardship is a credibility asset (product level, not financial)

**Claim:** Terrene Foundation's Apache 2.0 + CC BY 4.0 + independent-entity posture is a _net credibility asset_ for the prosumer/indie cohort at Phase 01–04 and for managed-Envoy operators at un-phased enterprise readiness.

**Note:** Financial viability of the Foundation and distribution motion are Foundation-strategy concerns, not Envoy-product-thesis concerns. They are tracked at Foundation level, not as Envoy bets.

**Falsifying evidence:**

- [Public] Envoy-mentioning HN / X / blog threads over a rolling 12-month window: share of mentions invoking "Foundation" pejoratively (e.g. "typical nonprofit bureaucracy", "too corporate") exceeds 15%.
- [Heartbeat] Opt-in install-survey: respondents rate Foundation posture as "neutral" or "unclear" at >70%, indicating it is not salient.
- Third-party commercial ecosystem around Envoy fails to emerge at Phase 04+ (managed-Envoy operators do not materialize despite Envoy's technical readiness), blocking un-phased enterprise readiness pathway indefinitely.

**Mitigation path:**

- **Minor:** Adjust messaging emphasis — Foundation is _how the product stays un-owned_, not _the product's identity_. Users experience Envoy, not the Foundation.
- **Major:** Support a third-party commercial ecosystem explicitly (managed offerings, support contracts, enterprise deployments) without compromising Foundation-stewarded core; the boundary is `rules/independence.md`.

### 5.5 BET-5 — Prosumer-first adoption is achievable and measurable

**Claim:** The prosumer-first go-to-market thesis works for Envoy (versus convenience-first competitors). Adoption reaches meaningful-niche levels (~0.5–2% of autonomous-AI-curious TAM) sustainably.

**Falsifying evidence:**

- [Heartbeat] At Phase 03, <5% of Phase 02-cohort installs have added a second principal to Shared Household; multi-principal primitive sees no organic demand.
- [Heartbeat] Phase 03 post-Shared-Household launch: <5% of new installs use multi-principal mode in first 3 months.
- [Public] Enterprise security reviews block adoption at the individual-device level at notable rates (HN threads + forum reports mention blocking at >5% of enterprise contexts).

**Mitigation path:**

- **Minor:** Lean harder into prosumer subculture; accept that enterprise-managed path is gated on third-party operators.
- **Major:** Re-frame Shared Household as optional advanced feature, not a prosumer→enterprise bridge.

### 5.6 BET-6 — Contract parity is byte-identical; behavioral parity is semantic-equivalent

**v2 split:** v1 conflated two claim types. v2 names them:

- **Contract parity (byte-identical, achievable):** Signing, hashing, canonical serialization, envelope compile output (given identical input), ledger hash chain over a canonical event stream. Verified via PACT N1–N6 conformance vectors + EATP D6 canonical-form tests.
- **Behavioral parity (semantic-equivalent, NOT byte-identical):** LLM-composed outputs (Boundary Conversation agent responses, Grant Moment prompt generation, Daily Digest text). Two LLM providers never byte-match; Rust async scheduler ≠ Python asyncio scheduler.

**Claim:** Contract parity is feasible AND worth the cost. Behavioral parity is not claimed; it is out of scope.

**Falsifying evidence (contract parity):**

- Phase 02 conformance vectors reveal >20 contract-surface divergences that cannot be closed by either side without architectural change.
- Phase 02 cross-SDK test: Ledger hash chain written by `kailash-py` cannot be verified by `kailash-rs-bindings` or vice versa, for a single canonical event stream.
- Phase 02 cross-SDK test: EATP D6 signature produced by one side fails verification on the other.

**Falsifying evidence (engineering cost):**

- Maintenance cost: >30% of Phase 02–03 engineering goes to parity maintenance, crowding out feature work.

**Cross-SDK prerequisite:** The **Python runner for PACT N4/N5 conformance vectors** does not exist at draft time (per kailash-rs survey). Filing a GH issue on `terrene-foundation/kailash-py` and `esperie-enterprise/kailash-rs` (cross-filed) to implement the runner is a Phase 01 exit OR Phase 02 entry criterion. Without it, BET-6 is structurally non-falsifiable.

**Mitigation path:**

- **Minor:** Publish the parity-gap catalog as a known-divergences doc; operate with declared deltas.
- **Major:** Freeze `kailash-py` at a Phase-02-compatible snapshot; stop investing in ongoing parity; promote as "minimal Foundation reference implementation" rather than "first-class alternative runtime."
- **Kill:** If `kailash-py` is structurally incapable of Envoy's surface, the pluggability claim (§ADR-0001, §ADR-0009) breaks and must be re-announced.

### 5.7 BET-7 — `SKILL.md` compatibility does not poison the Envelope Library

**Claim:** Ingesting external-format skills with install-time CO-compliance validation + `force_install=True` opt-out keeps the skill ecosystem safe without stranding users from existing skill libraries.

**Continuous-tuning note (v2 addition):** The CO validator is a continuous-tuning problem, not a binary gate. Fidelity iterates across Phase 02, 03, 04. The §10 dependency graph reflects this.

**Falsifying evidence:**

- Phase 02 CO validator: rejects >50% of a test corpus of real-world SKILL.md skills — too strict.
- Accepts skills later shown adversarial (permission-escalation, exfiltration) — too loose.
- Skill authors respond by gaming the validator or by distributing via `force_install=True`, making the validator theater.
- [Heartbeat] Force-install rate exceeds 30% of total skill installs; the validator is routinely bypassed.

**Mitigation path:**

- **Minor:** Iterate validator; curate a Foundation-Verified subset; gate Community tier on validator compliance at publish time.
- **Major:** Drop bulk ingest; ship only Foundation-curated skills; re-frame skill compatibility as technical-interop claim, not adoption claim.

### 5.8 BET-8 — The new habit forms (measurable via Heartbeat)

**Claim:** The daily / weekly / monthly ritual cadence forms a durable user habit; rituals are _anticipated_ and _shared_, not ignored.

**Falsifying evidence:**

- [Heartbeat] Phase 02 post-launch: <20% of active users open the Daily Digest twice in any 7-day window.
- [Heartbeat] Phase 03 post-Weekly-Posture-Review launch: <10% engagement week-over-week.
- [Heartbeat] Phase 04 post-Monthly-Trust-Report launch: <5% open within 7 days of delivery.
- [Public] Qualitative: users describe rituals as "spam" in >10% of public mentions.

**Mitigation path:**

- **Minor:** Simplify Digest UX; collapse rituals into a single weekly touchpoint.
- **Major:** Rituals become event-driven pop-ups (fire on Grant Moment pending or budget threshold) rather than scheduled.

### 5.9a BET-9a — Upstream Kailash crates are sufficient

**Claim:** The upstream Rust crates (PACT, EATP, kailash-kaizen, kailash-dataflow, kailash-nexus) contain the primitive substrate Envoy requires. Even when a primitive is not yet _bound_ to Python, the _underlying capability_ exists and can be wrapped.

**Falsifying evidence:**

- Deep audit at `01-kailash-rs-deep-audit.md` reveals N primitives classified **C (genuinely absent from Rust)** — these require new upstream work, not wrapping.
- New upstream work exceeds Foundation engineering capacity at Phase 01 cadence.

**Mitigation path (if 9a disconfirms):**

- **Minor:** Envoy contributes upstream in the standard COC codify flow.
- **Major:** Envoy temporarily reimplements specific primitives locally (explicitly against `rules/zero-tolerance.md` rule 4, documented as time-bounded workaround with sunset condition).
- **Kill:** If multiple (≥3) primitives are genuinely absent from upstream Rust, Envoy becomes a Kailash upstream-maintenance project, which is not the thesis. Re-scope as Kailash meta-project.

### 5.9b BET-9b — Python binding surface exposes usable versions of the primitives by Phase 01 exit

**Claim:** All GH issues filed on `terrene-foundation/kailash-py` and `esperie-enterprise/kailash-rs` (per §3.3 table) are closed OR explicitly scoped into Envoy-new-code before Phase 01 opens.

**Status at draft time:** Already partially disconfirmed. Deep audit in progress. Pre-existing evidence (per `workspaces/internal/kailash-rs-survey-2026-04-21.md`):

- Kaizen `BaseAgent.execute()` raises `NotImplementedError` in Python binding.
- `OrchestrationRuntime.run()` returns static-dict stub.
- `A2AProtocol.send_message / receive_message` declared in `.pyi` but do not exist.
- `DataFlow.execute_raw(params)` silently drops params (SQLi surface).
- MCP transports (stdio/SSE/HTTP) not bound from Python.
- `.pyi` overall ~55% accurate.

**Mitigation path:**

- **Minor:** Every gap has a filed issue; Foundation engineering closes upstream; Envoy tracks closure in Phase 00 workspace todos.
- **Major:** Gaps not closed upstream by Phase 01 entry get scoped into Envoy-new-code with explicit sunset (Envoy commits to upstreaming when feasible).
- **Kill:** If >N primitives remain broken AND upstream declines to fix AND Envoy-local reimplementation exceeds Phase 01 budget by >2×, Phase 01 is re-scoped or the thesis is rewritten.

### 5.10 BET-10 — Legal/regulatory posture holds (with Phase-02 scanner pre-flight)

**Claim:** The composite license stack (Apache 2.0 code + CC BY 4.0 methodology + freely-redistributable compiled binary + MIT-licensed `SKILL.md` ingest) is legally sound and compliance-scannable.

**Falsifying evidence:**

- Legal counsel identifies unresolvable conflict (CC BY 4.0 attribution pipelines, export-control classification, Foundation charter compatibility).
- **Phase 02 pre-flight:** FOSSA / Snyk / Sonatype flag the composite license expression at release-candidate time with CRITICAL findings on a test pipeline.
- Foundation board declines to endorse runtime-pluggability on charter-compatibility grounds.

**Mitigation path:**

- **Minor:** Re-license specific friction points.
- **Major:** If Rust binary is legally untenable, `kailash-py` becomes sole default AND **BET-3 sovereignty narrative must be adjusted for the performance regression AND BET-6 contract parity must be re-verified under single-runtime assumption**. The major mitigation is not a cheap pivot; its cascades are named.
- **Kill:** If the composite stack cannot be made compliance-scanner-clean, the Foundation openness posture is compromised. See §7.

### 5.11 BET-11 — (withdrawn) Foundation financial viability

**Status:** Withdrawn from Envoy thesis doc.

**Rationale:** Financial viability of Terrene Foundation is a Foundation-level strategic concern, tracked at Foundation governance rather than in Envoy's product thesis. Envoy composes on Foundation primitives; Foundation viability is a prerequisite Envoy depends on but does not own.

### 5.12 BET-12 — Governance-primary-surface palatability (new in v2)

**Claim:** Users accept a product whose primary conscious surface is _authoring_ governance (not approving), at adoption rates comparable to authorship-centric niche-power-user tools (Obsidian class, 2–8% of TAM) rather than per-action governance tools (Little Snitch class, 0.5–2%). The structural inversions in §2.5 convert per-action friction into authorship authority.

**Falsifying evidence:**

- [Heartbeat] Phase 02–03 active-user share of autonomous-AI-curious TAM (estimated from public discourse + Library fetch proxies) is ≤1%, putting Envoy in Little Snitch band rather than Obsidian band.
- [Heartbeat] Median Authorship Score across active users stays at 0 or 1 for >60 days: users import templates, never author.
- [Heartbeat] Proportion of active users at DELEGATING + AUTONOMOUS postures <10% at 90 days: users do not complete the authorship work; posture gate blocks autonomy indefinitely.
- [Public] Qualitative: feedback themes around "too much ritual", "I just want it to work", "why can't I just grant everything" exceed 20% of public mentions.

**Mitigation path:**

- **Minor:** Lower authorship threshold (N=1 instead of N=3); make posture ratchet faster.
- **Major:** Retract the authorship-gate thesis; allow template-only users to reach DELEGATING. The product becomes governance-via-audit, not governance-via-authorship. Back to §2.4 consent-claim fallback.
- **Kill:** See §7.

---

## 6. Counterfactuals — if bets break

| ID    | If                                                             | Then (within 1–2 sessions)                                                                                                                                                                                                                                                                                                           |
| ----- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| CF-1  | BET-1 disconfirmed (authorship thesis breaks)                  | Re-scope per BET-12 major — allow template-only at DELEGATING; Boundary Conversation becomes opt-in                                                                                                                                                                                                                                  |
| CF-2  | BET-2 disconfirmed (governance-as-speed claim)                 | Demote from USP to engineering note; keep thesis; publish honest numbers                                                                                                                                                                                                                                                             |
| CF-3  | BET-3 disconfirmed (sovereignty not durable)                   | Re-frame as authorship-first; sovereignty narrows to subculture                                                                                                                                                                                                                                                                      |
| CF-4  | BET-4 disconfirmed (Foundation a credibility tax)              | Messaging adjustment; Foundation structural not surfaced                                                                                                                                                                                                                                                                             |
| CF-5  | BET-5 disconfirmed (prosumer-first doesn't land)               | Shared Household becomes advanced feature not bridge; defer enterprise to un-phased commercial operators                                                                                                                                                                                                                             |
| CF-6  | BET-6 disconfirmed (contract parity infeasible)                | Freeze kailash-py at snapshot; stop parity investment; publish divergence catalog                                                                                                                                                                                                                                                    |
| CF-7  | BET-7 disconfirmed (SKILL.md poisons library)                  | Drop bulk ingest; curated-only Envelope Library                                                                                                                                                                                                                                                                                      |
| CF-8  | BET-8 disconfirmed (rituals don't form habit)                  | Rituals event-driven pop-ups; scheduled cadence removed                                                                                                                                                                                                                                                                              |
| CF-9a | BET-9a disconfirmed (upstream primitives insufficient)         | Envoy fixes upstream; if pattern recurs for ≥3 primitives, re-scope as Kailash meta-project                                                                                                                                                                                                                                          |
| CF-9b | BET-9b disconfirmed (binding exposure incomplete at Phase 01)  | Scope missing primitives into Envoy-new-code with explicit sunset back to upstream                                                                                                                                                                                                                                                   |
| CF-10 | BET-10 disconfirmed (legal stack unsound)                      | Drop friction layer. If Rust binary is the issue, permanent freeze on `kailash-py` as sole default; runtime picker removed; BET-6 withdrawn; Rust hot path becomes un-phased optional accelerator. This CASCADES into BET-3 (sovereignty narrative adjusted) and BET-12 (palatability re-evaluated under single-runtime assumption). |
| CF-12 | BET-12 disconfirmed (governance-primary-surface not palatable) | Authorship threshold lowered; posture ratchet accelerated; if still disconfirmed, retract authorship thesis (§2.4 consent-claim fallback)                                                                                                                                                                                            |

---

## 7. Thesis kill criteria — when Envoy abandons

Operationalized against §5.0 measurement methodology.

1. **18 months post-Phase-01 with [Heartbeat] <1,000 STAR-aggregated weekly-active users AND [Library] <500 Envelope Library Foundation-Verified fetches/week.** Two-signal floor to avoid single-signal false alarms.
2. **≥3 bets disconfirmed simultaneously with a 6-month targeted-experiment countdown.** No "shared root cause" escape hatch. If 3 bets are disconfirmed, the team may publish a named variable they believe would flip each to green; this triggers a 6-month experiment window. After 6 months, if no bet flips, kill proceeds.
3. **Foundation board declines to endorse the runtime-pluggability model AND a replacement posture cannot be negotiated.** Breaks BET-4 and BET-6 structurally.
4. **A categorically-better alternative emerges** — operationalized as (all must hold):
   - The alternative passes all five §8 primary-surface tests (Tests 1–5).
   - The alternative is Foundation-grade or equivalent (non-commercial, local-first, user-owned-keys, envelope-required-at-onboarding).
   - The alternative sustains **3× within-niche adoption** (in the sovereignty-plus-authorship TAM, not the mainstream AI-curious TAM) for ≥24 months.
   - At least 2 independent Foundation-unaffiliated stewards confirm the alternative satisfies the thesis before sunset proceeds.
5. **Legal counsel identifies a categorical blocker to the composite license stack that cannot be engineered around.** Export control, CC BY 4.0 pipeline preservation, Foundation charter compatibility.

---

## 8. The "primary surface" claim operationalized

Five tests. All five must be true. If any fails during implementation, the claim must be either restored or retracted.

**Test-1 — Onboarding cannot skip boundary declaration.** `envoy init` cannot produce an operational Envoy without an `EnvelopeConfig`. Template import is a legal starting point; the Boundary Conversation personalizes and authors beyond it. Users who skip both (no-op envelope) cannot start the agent.

**Test-2 — Every action's INTENT is signed before execution (Phase A); its OUTCOME is signed after execution (Phase B).** Structural envelope membership is checked pre-action at O(1) in Phase A; semantic envelope compliance is checked pre-action with O(k) LLM classification in Phase A (budget per BET-2). **No action executes without a prior Phase A signature.** "Log after the fact" unconditionally is out-of-spec; the Ledger signs the _intent_ on the pre-action edge and the _outcome_ on the post-action edge. An intent signed in Phase A without a matching Phase B completion record within N seconds (default 30s for synchronous tool-calls; longer for known-async) is a **repudiable-side-effect incident** — the Ledger records the orphaned intent, the incident surfaces as a Grant Moment on next session start, and the user explicitly acknowledges or revokes the orphan. This two-phase structure is doc 09 T-004's mitigation; it preserves the "signed before execution" promise for intent while honestly modeling the small post-commit window where side-effects become observable. For streaming user-channel output (distinct from tool-calls), the message is signed as a single `Message` record at stream-end, not per-chunk; user visibility precedes signature by milliseconds, which is acceptable because user-channel streaming is not an envelope-consumed action.

**Test-3 — Revocation is first-class in the UI.** "Revoke" is on the user's primary surface (Ledger inspection, Grant Moment dialog, Daily Digest). Cascade effect is explicit — "revoking this grant will also revoke 3 downstream delegations" — never silent.

**Test-4 — The envelope is editable through the same channel the user uses to interact.** A user who lives in Telegram can update their envelope via Telegram. Envelope editing inherits channel-native philosophy from day 1 (Phase 01 ships channel edits).

**Test-5 — Envoy cannot reach posture DELEGATING or AUTONOMOUS without Authorship Score ≥ N.** (v2 new; enforces §2.2 irreducibility structurally.) Default N=3 in Phase 01. Template-only users remain at TOOL indefinitely; DELEGATING requires personally-authored constraints beyond any imported template. Any product claiming category-peer without this gate is a tool-frame product masquerading as agent-frame.

If all five tests hold, the "primary surface" claim is structurally honored. If any fails, we are shipping an audit product with a chat interface, which is a valid product but a different thesis.

---

## 9. The meta-USP: "AI as personal extension of self"

### 9.1 Through the Responsibility-and-safety pillar

Extension-of-self means: _the agent's actions are credibly traceable to me, not to a vendor, not to a service, not to a platform._ Honored via the Genesis Record — locally-generated, Ed25519-signed anchor; cannot be issued or transferred; not a service account.

### 9.2 Through the Governance-as-performance pillar

Extension-of-self means: _my judgment is present in every agent action, not as a constraint but as a shape._ Honored via envelope compilation — the envelope is the user's declared judgment; the agent cannot act outside it structurally.

### 9.3 Through the Channel-native pillar

Extension-of-self means: _the agent reaches me where I already am; I don't go to it._ Honored via Phase 01 channel-native operation on 6 channels + CLI + Web; Phase 02–04 extends to 23+.

### 9.4 Anti-patterns that break the meta-USP

The meta-USP is broken if any of:

1. **Envoy requires registration / signup / email verification / hosted account.**
2. **Envoy has a primary UI separate from the user's existing channels for daily use.** (Phase 01 ships 6 channels; admin operations via CLI/Web are onboarding + management affordances only. Daily ritual UX is channel-native from day 1.)
3. **Envoy's default behavior is permissive ("just do the thing") with opt-in safety.** (Envoy's ratchet is the inverse — default-deny + posture-gated-autonomy.)
4. **Envoy's credentials or action-authorizing state are stored in a form the user does not solely control.** Ciphertext on a third-party store where the user holds the only decryption key AND the ciphertext format does not leak action-informing metadata is a permissible configuration when opt-in. Plaintext on any third party is always a violation. Credentials are stored in Connection Vault (local OS keychain / Secure Enclave), not in any Envoy-provided sync target.

Every downstream doc must test its design against these anti-patterns.

---

## 10. Scope decisions as a dependency graph

```
Foundation board endorsement of runtime-pluggability (ADR-0009 §3)
├── Composite LICENSE drafted (ADR-0009 §1)
├── SPDX metadata finalized (ADR-0009 §2)
├── Charter-compatibility statement (ADR-0009 §3)
└── gates → Phase 01 `/analyze` opening

Trademark resolution (ADR-0002)
├── USPTO + EUIPO + UK IPO sweep
├── Final mark decision
├── GitHub org reservation
└── gates → public namespace publication (PyPI, crates, npm)

Binding + spec audit and GH-issue closure (v2 new)
├── Deep kailash-rs audit (01-kailash-rs-deep-audit.md)
├── Deep kailash-py audit (02-kailash-py-survey.md)
├── Primitive reconciliation (03-primitive-reconciliation.md)
├── GH issues filed on kailash-py + kailash-rs (cross-filed for parity)
├── GH issues filed on mint for any spec-level changes (cross-filed to kailash-py + kailash-rs + loom)
├── Closure or explicit Envoy-new-code scoping
└── gates → Phase 01 opening

Crypto audit
├── SLIP-0039 library choice (audited Rust: sharks / vsss-rs; audited Python: slip39)
├── Ed25519 library choice
├── Algorithm-identifier schema + versioned artifact format + legacy-verification resolver
├── Export-control assessment (ADR-0009 §5)
└── gates → Phase 01 exit (Shamir 3-of-5 is a Phase 01 exit criterion)

Runtime abstraction
├── `kailash-runtime` interface crate (Apache 2.0)
├── `kailash-rs-bindings` integration
├── `kailash-py` integration
├── Python conformance-vector runner (PACT N1–N6)
├── Cross-SDK contract-parity vectors
└── gates → Phase 02 exit

Foundation Health Heartbeat
├── STAR/Prio client implementation
├── OHTTP relay (Foundation or third-party)
├── OHTTP Key Configuration Server (Foundation)
├── Aggregator (Foundation)
├── DP-budget publisher
├── Signed-consent Grant Moment UX
└── gates → Phase 02 entry for Heartbeat-dependent bet measurement

Skill ecosystem (continuous tuning, not single gate)
├── SKILL.md parser + ENVELOPE.md schema
├── Permission-to-PACT-dimension translator
├── CO validator (fidelity iterates across Phase 02, 03, 04)
├── `force_install=True` UX + inventory flagging
├── Envelope Library Foundation-Verified tier
└── Phase 02 exit (library) + Phase 03 exit (Community) + Phase 04 exit (Organization)

Channel breadth (Phase 01 6-channel foundation)
├── Adapter contract (internal API)
├── Per-channel compliance check — BlueBubbles (Mac + Apple ID), Signal (signal-cli vs Group Link webhook), WhatsApp (Business API only), Slack (bot API), Discord (bot API), Telegram (bot API)
├── Cross-channel session continuity
├── Per-channel Grant Moment for connection
└── gates → Phase 01 exit (8 channels including CLI + Web) + Phase 04 exit (23+ total)

Multi-principal
├── Shared Household data model
├── Per-principal envelope + per-principal Authorship Score + per-principal posture
├── Consenting-principal attribution per action
├── Kids / adult / guest role templates with posture ceilings
├── Per-dimension posture slider (5 × 5)
├── Household-adversarial threat mitigations (doc 09)
└── gates → Phase 03 exit

Authorship-gate primitive (v2 new)
├── Authorship Score counter (authored vs imported constraints)
├── Posture ratchet (DELEGATING/AUTONOMOUS gated on score ≥ N)
├── Ritual nudges (Weekly Posture Review prompts authorship when score = 0)
└── gates → Phase 01 exit (single slider); Phase 03 exit (per-dimension)

Binary distribution hardening (v2 new)
├── N=3 independent mirrors for `kailash-rs-bindings`
├── Binary-signing key rotation cadence (published)
├── Binary-compromise response plan (published)
└── gates → Phase 02 exit (structural sovereignty claim preserved for Rust default path)
```

## 11. Glossary — canonical vocabulary

Every sibling doc, spec, and test uses these terms with these meanings. Marketing/user-copy synonyms are permitted in the final column; code / specs / logs / agents use the canonical form.

| Canonical term                                | Meaning                                                                                                                                                                                                                  | Source                           | User-copy synonym        |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------- | ------------------------ |
| **Envoy**                                     | The product                                                                                                                                                                                                              | (subject to trademark; ADR-0002) | —                        |
| **Envelope**                                  | Compiled `EnvelopeConfig`; declarative statement of permitted actions across 5 constraint dimensions                                                                                                                     | PACT + Envoy                     | "boundaries" (marketing) |
| **Constraint dimension**                      | One of **Financial, Operational, Temporal, Data Access, Communication**. Exact names, no synonyms.                                                                                                                       | PACT (`rules/terrene-naming.md`) | —                        |
| **Boundary Conversation**                     | Onboarding dialogue that compiles `EnvelopeConfig`; starts from template optionally, ends with ≥1 authored constraint                                                                                                    | Envoy-new (doc 01)               | "first-run setup"        |
| **Grant Moment**                              | Structured consent event for out-of-envelope action; produces signed Delegation Record                                                                                                                                   | Envoy-new (doc 01)               | "permission request"     |
| **Delegation Record**                         | Ed25519-signed entry in EATP Trust Lineage attesting capability grant from principal to agent/sub-agent                                                                                                                  | EATP                             | "authorization receipt"  |
| **Genesis Record**                            | Root of user's Trust Lineage; locally generated; unforgeable; not transferable                                                                                                                                           | EATP                             | "identity anchor"        |
| **Trust Posture**                             | One of five: PSEUDO / TOOL / SUPERVISED / DELEGATING / AUTONOMOUS                                                                                                                                                        | EATP Decision 007                | "autonomy level"         |
| **Posture slider**                            | User-visible UI element for adjusting Trust Posture. Bidirectional (trust oscillates, not monotone-ratchet). Single-slider in Phase 01; per-dimension (5 postures × 5 constraint dimensions) in Phase 03+.               | Envoy-new                        | "trust dial"             |
| **Authorship Score**                          | Count of envelope constraints the user personally authored (not imported). Gates posture-ratchet to DELEGATING / AUTONOMOUS. Default threshold N=3.                                                                      | Envoy-new (v2)                   | — (internal)             |
| **Posture ratchet** (or posture-ratchet gate) | The structural enforcement that Authorship Score ≥ N is required before posture reaches DELEGATING / AUTONOMOUS                                                                                                          | Envoy-new (v2)                   | — (internal)             |
| **Envoy Ledger**                              | User-local hash-chained record of every grant, action, refusal, posture change, delegation                                                                                                                               | EATP + Envoy-new                 | "activity log"           |
| **Trust Vault**                               | Encrypted local store of Envoy's own signing keys + envelope state + posture history + budget state. Recoverable via Shamir 3-of-5.                                                                                      | Envoy-new                        | "vault"                  |
| **Connection Vault**                          | Separate encrypted store for third-party credentials (API keys, channel tokens, OAuth refresh tokens). OS keychain / Secure Enclave wrapper. Per-principal isolated.                                                     | Envoy-new (v2)                   | "credential vault"       |
| **Daily Digest**                              | Morning ritual delivered per user's chosen channel                                                                                                                                                                       | Envoy-new                        | "daily brief"            |
| **Weekly Posture Review**                     | Sunday 90-second ritual for posture + envelope adjustment                                                                                                                                                                | Envoy-new                        | "weekly check-in"        |
| **Monthly Trust Report**                      | Monthly one-pager; delegation graph, budget, posture trajectory, skill inventory                                                                                                                                         | Envoy-new                        | "monthly report"         |
| **Envelope Library**                          | Federated registry of envelope templates; three tiers                                                                                                                                                                    | Envoy-new                        | "template library"       |
| **Foundation-Verified tier**                  | Envelopes reviewed by Terrene Foundation, signed by Foundation key                                                                                                                                                       | Envelope Library                 | "verified"               |
| **Community tier**                            | Open-publishing envelopes signed by publisher key; ranked by adoption × (1 − revocation rate)                                                                                                                            | Envelope Library                 | "community"              |
| **Organization tier**                         | Private envelopes scoped to org Trust Lineage root                                                                                                                                                                       | Envelope Library                 | "private"                |
| **kailash-runtime**                           | Abstract runtime interface (Apache 2.0, Foundation-owned) Envoy programs against                                                                                                                                         | Envoy-new                        | —                        |
| **kailash-rs-bindings**                       | Rust-accelerated runtime; Python glue open-source; compiled binary freely redistributable. Default runtime from Phase 02.                                                                                                | Terrene Foundation               | —                        |
| **kailash-py**                                | Terrene Foundation's pure-Python implementation of the CARE/EATP/CO/PACT specs. Apache 2.0 + CC BY 4.0. In Envoy, Phase 01 sole runtime; Phase 02+ opt-in alternative.                                                   | Terrene Foundation               | —                        |
| **SKILL.md**                                  | External-ecosystem skill-definition format; Envoy ingests unchanged. Compatibility substrate only.                                                                                                                       | External                         | —                        |
| **ENVELOPE.md**                               | CO-native companion format declaring a skill's permission needs in PACT dimensions. Generated by Envoy on `SKILL.md` ingest.                                                                                             | Envoy-new                        | —                        |
| **CO validator**                              | Install-time check that a skill's declared permissions are CO/PACT-compliant. Continuous-tuning not single-gate.                                                                                                         | CO / Envoy-new                   | —                        |
| **Shamir 3-of-5**                             | SLIP-0039 Shamir mnemonic recovery with default 3-of-5 threshold; user-configurable 2-of-3 to 5-of-9                                                                                                                     | SLIP-0039                        | "backup shards"          |
| **Cascade revocation**                        | Revoking a grant at any point invalidates all downstream grants derived from it, transitively. Implemented at Envoy level if upstream binding does not expose (see §3.3).                                                | EATP + Envoy-new                 | "revoke all"             |
| **Conformance vector**                        | Cross-SDK test fixture asserting byte-identical contract-surface behavior between `kailash-rs-bindings` and `kailash-py`. N1 / N2 / N3 / N4 / N5 / N6 per PACT nomenclature. Python runner is a Phase 01 exit criterion. | PACT                             | —                        |
| **Shared Household**                          | Multi-principal configuration where one Envoy instance serves multiple named humans. Per-principal envelope + Authorship Score + posture.                                                                                | Envoy-new                        | "family mode"            |
| **Force-install**                             | `force_install=True` flag on `envoy skill install` — bypasses CO validator with explicit warning. Sovereignty-respect, not safety feature.                                                                               | Envoy-new                        | —                        |
| **Foundation Health Heartbeat**               | Opt-in anonymous aggregate telemetry via STAR/Prio + differential privacy + Oblivious HTTP + signed-consent Grant Moment                                                                                                 | Envoy-new (v2)                   | "Foundation telemetry"   |
| **Algorithm identifier**                      | Versioned tag on every signed artifact naming the signing algorithm, hash algorithm, and Shamir scheme. Enables migration without invalidating legacy records.                                                           | Envoy-new (v2)                   | —                        |
| **Reference verifier**                        | Separate-codebase tool that verifies the Envoy Ledger hash chain + signatures. Ledger format published at `specs/ledger.md` under CC BY 4.0.                                                                             | Envoy-new (v2)                   | "ledger verifier"        |

---

## 12. References

- `CHARTER.md` — product thesis, three pillars, openness posture.
- `DECISIONS.md` — 9 ADRs (runtime, naming, Shamir, Envelope Library, SKILL.md, model, vault sync, mobile, licensing).
- `ROADMAP.md` — Phase 00 through un-phased regulated readiness.
- Round 1 consolidated findings pack — `workspaces/phase-00-alignment/04-validate/round-1-00-consolidated-pack.md`
- kailash-rs deep audit — `01-analysis/01-kailash-rs-deep-audit.md` (in progress)
- kailash-py survey — `01-analysis/02-kailash-py-survey.md` (in progress)
- Primitive reconciliation — `01-analysis/03-primitive-reconciliation.md` (pending audits)
- `rules/independence.md` — Foundation independence / commercial-coupling boundary.

---

## 13. Open questions for downstream docs

### Open for `/redteam` Round 2 debate on this doc

1. Is Authorship Score threshold N=3 the right default? What's the implementation evidence that higher (or lower) N affects user flow?
2. Does `.gitignore` for `workspaces/internal/` provide sufficient leak protection given we pulled the brief back for working speed?
3. What's the measurement substrate for "at least 2 independent Foundation-unaffiliated stewards" in §7 item 4 — how are they identified?

### Carry-forwards to doc 09 (threat model)

1. **Clock-trust for Temporal dimension.** Device-clock manipulation bypasses `no actions after 7pm` type constraints. Doc 09 owns mitigations: monotonic ledger-time invariant, optional remote time anchor with §4.1 item 7 opt-in.
2. **Household-adversarial threat class.** Divorce, elder-abuse, teen-rebellion, DV, coerced unlock, death-of-principal. Doc 09 owns: time-delayed revocation, flee-mode, shard-rotation, per-principal isolation.
3. **Ledger retention + GDPR right-to-erasure** on append-only hash chain. Options: merkle-proof-of-deletion, encrypted-then-key-destroy, jurisdiction carveout. Doc 09 + doc 10 own.
4. **Streaming LLM pre-action signing.** Test-2 says "sign before execution." Streaming output makes this hard. Doc 09 owns atomic-chunk-vs-per-chunk signing decision.
5. **Semantic envelope checks vs O(k) performance claim.** BET-2 partitions static/semantic; doc 09 owns attack surface of semantic-check bypass (adversarial inputs that defeat LLM classification).
6. **Shamir shard social-graph exposure.** Shard-holders learn you use Envoy; death/estrangement of shard-holders; shard-rotation ritual. Doc 09 owns.
7. **Credential storage in Grant Moments.** Connection Vault design; cross-principal leakage in Shared Household; Shamir-recovery behavior for Connection Vault entries.

### Carry-forwards to doc 05 (runtime abstraction)

1. Detailed `kailash-runtime` abstract interface surface; conformance-vector shape (N1–N6 decoded); contract-parity definition; Phase 01 writes-against-kailash-py-directly vs writes-against-abstraction strategy.

### Carry-forwards to doc 02 (envelope model)

1. EnvelopeConfig schema — JSON format, versioning, migration between Authorship Score updates.
2. 5 constraint dimensions' operational semantics — Financial (integer microdollars), Operational (tool allowlist + rate limits), Temporal (monotonic-clock-safe time windows), Data Access (classification labels + semantic checks), Communication (allowlist + content-gating).
3. Intersect / union / inheritance semantics (`intersect_envelopes`).
4. Template → authored-constraint diff algorithm (for Authorship Score counting).

### Carry-forwards to doc 01 (UX rituals)

1. Boundary Conversation state machine — each question, branching, skip behavior, interruption recovery, re-entry.
2. Grant Moment state machine.
3. Daily Digest / Weekly Posture Review / Monthly Trust Report — delivery per-channel, localisation, accessibility.

### Carry-forwards to doc 10 (data model)

1. Ledger schema — per-entry fields, retention, indexing, scale to 400k entries.
2. Trust Vault schema — encryption-at-rest format, key derivation.
3. Connection Vault schema — per-credential structure, per-principal isolation.
4. Algorithm-identifier schema — how versioned tags appear in every record.

---

**End of doc 00 v2. Next: Round 2 redteam convergence; once complete, move to doc 09 (threat model).**
