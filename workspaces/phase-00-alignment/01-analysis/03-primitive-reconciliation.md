# 03 — Primitive Reconciliation

**Date:** 2026-04-21
**Purpose:** Synthesize the kailash-rs deep audit (`01-kailash-rs-deep-audit.md`) + kailash-py survey (`02-kailash-py-survey.md`) into a per-primitive three-column parity grid Envoy's thesis (doc 00 §3.3) depends on. Also produces the master GH issue list for cross-filing on `terrene-foundation/kailash-py` and `esperie-enterprise/kailash-rs` + `terrene-foundation/mint`.

**Authority:** Foundation-voice factual synthesis. Tracked. Citeable from GH issues.

---

## 1. Classification framework

Each primitive carries **two status codes** (one per runtime side) using:

- **✅ Functional** — present and usable by an Envoy consumer today.
- **⚠️ Bound-but-stubbed** — method/class exists in the Python surface but fails at runtime (raises, returns stub, drops params).
- **🔧 Unbound** — present in the implementation language but not exposed in the Python surface (kailash-rs: in Rust, not in PyO3 binding / kailash-py: only in internal module, not on public API).
- **❌ Absent** — not present in the implementation at all.
- **🔀 Different-name** — present under a different name or structure; reconciliation needed.

---

## 2. Per-primitive parity grid

| #   | Primitive                                                                        | kailash-py status                                                                                                                                                | kailash-rs-bindings status                                                                                                                                                                                                                                 | Envoy-side decision                                                                                                                                                                        | GH issues                                                                                  |
| --- | -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| 1   | **`intersect_envelopes()`**                                                      | ✅ Functional — `src/kailash/trust/pact/envelopes.py`                                                                                                            | 🔀 Different-name `ConstraintEnvelope::intersect()` at `crates/eatp/src/constraints/mod.rs:356` — not on Python binding                                                                                                                                    | **Use kailash-py directly in Phase 01. File issue on kailash-rs to expose via PyO3**                                                                                                       | ISS-01 (kailash-rs), ISS-02 (parity audit kailash-py to confirm semantic identity)         |
| 2   | **`RoleEnvelope` / `TaskEnvelope`**                                              | ✅ Functional — `src/kailash/trust/pact/envelopes.py`                                                                                                            | 🔧 Unbound — `crates/kailash-governance/src/envelopes.rs:186` exists, not exposed in binding                                                                                                                                                               | **Use kailash-py in Phase 01. Issue on kailash-rs for binding exposure**                                                                                                                   | ISS-03 (kailash-rs binding)                                                                |
| 3   | **Cascade revocation**                                                           | ✅ Functional — `src/kailash/trust/revocation/cascade.py` (BFS walking with atomic rollback)                                                                     | 🔧 Unbound — Rust has `DelegationChain::revoke()` + `cascade_revoke()` at `crates/eatp/src/delegation.rs:807` walking parent_delegation_id; not exposed as explicit Python cascade API                                                                     | **Use kailash-py in Phase 01. Issue on kailash-rs binding for explicit cascade API + docstring**                                                                                           | ISS-04 (kailash-rs binding docs), ISS-05 (kailash-py doc cross-reference)                  |
| 4   | **`TieredAuditDispatcher` + hash-chained Audit Anchors + SIEM export**           | ❌ Absent — only `AuditLogger`                                                                                                                                   | ❌ Absent — only `AuditLogger` (Enterprise) + `eatp::audit::AuditEvent/Filter`                                                                                                                                                                             | **New primitive needed on BOTH sides. File on mint (spec design) + kailash-py + kailash-rs for implementation**                                                                            | ISS-06 (mint), ISS-07 (kailash-py), ISS-08 (kailash-rs)                                    |
| 5   | **`PostureStore` / `SQLitePostureStore` / `PostureEvidence`**                    | ✅ Functional — `src/kailash/trust/posture/` directory present                                                                                                   | ❌ Absent in Rust                                                                                                                                                                                                                                          | **Use kailash-py in Phase 01. File on kailash-rs + mint for parity implementation**                                                                                                        | ISS-09 (kailash-rs new primitive), ISS-10 (mint spec)                                      |
| 6   | **`EatpPosture` + 7 other Phase-13 types**                                       | ⚠️ partial — `PostureLevel` present but Phase-13 bundle (VerificationConfig, etc.) status partial                                                                | 🔧 Unbound in .pyi (8 types missing per BINDING-AUDIT B1); Rust source has `PostureLevel` + `AgentPosture`                                                                                                                                                 | **Verify Phase-13 completeness on both sides. File on kailash-rs for .pyi regeneration + kailash-py for Phase-13 bundle**                                                                  | ISS-11 (kailash-rs .pyi), ISS-12 (kailash-py Phase-13 bundle)                              |
| 7   | **`PlanSuspension` (on BUDGET/TEMPORAL/POSTURE/ENVELOPE triggers)**              | ❌ Absent — `PlanSuspension` not in Python L3 executor                                                                                                           | 🔀 Different-structure — `SuspensionReason` enum + `SuspensionRecord` at `crates/kailash-kaizen/src/l3/core/plan/types.rs:267`; all 5 triggers present (HumanApprovalGate, CircuitBreakerTripped, BudgetExceeded, EnvelopeViolation, ExplicitCancellation) | **Rust has it; kailash-py needs it. File on kailash-py to implement; kailash-rs to expose via PyO3**                                                                                       | ISS-13 (kailash-py implement), ISS-14 (kailash-rs expose)                                  |
| 8   | **L3 Plan DAG**                                                                  | ✅ Functional — `packages/kailash-kaizen/src/kaizen/l3/plan/types.py` (PlanNode, PlanEdge, Plan) + executor                                                      | ✅ Functional in Rust — `crates/kailash-kaizen/src/l3/core/plan/types.rs:1–250` full DAG + state machine + event stream; binding exposure may be incomplete                                                                                                | **Both sides usable. File on kailash-rs to verify complete .pyi exposure**                                                                                                                 | ISS-15 (kailash-rs .pyi verification)                                                      |
| 9   | **`Delegate` provider abstraction (LlmDeployment 4-axis, 18 presets)**           | ✅ Functional — Ollama/Claude/GPT/DeepSeek providers present in kailash-py                                                                                       | ⚠️ binding-partial — 18 presets in Rust side per prior survey; exact Python surface pending                                                                                                                                                                | **Use kailash-py for Phase 01. Issue on kailash-rs for full surface exposure**                                                                                                             | ISS-16 (kailash-rs LlmDeployment binding)                                                  |
| 10  | **`McpGovernanceEnforcer` + `McpGovernanceMiddleware`**                          | ❌ Absent                                                                                                                                                        | ❌ Absent — neither in kailash-pact nor kailash-mcp                                                                                                                                                                                                        | **New primitive on BOTH sides. Design first at mint, implement at both SDKs**                                                                                                              | ISS-17 (mint), ISS-18 (kailash-rs), ISS-19 (kailash-py)                                    |
| 11  | **MCP transports from Python (stdio / SSE / HTTP)**                              | ⚠️ partial — `src/kailash/channels/` has MCPChannel but not full stdio/SSE/HTTP transports                                                                       | ❌ Absent in Python binding (C4 in survey); Rust has primitives at `crates/kailash-mcp/` but no transport abstraction exposed                                                                                                                              | **File on both sides for transport binding + abstractions**                                                                                                                                | ISS-20 (kailash-rs), ISS-21 (kailash-py), ISS-22 (mint if protocol spec needs extension)   |
| 12  | **`@classify` + `apply_read_classification()` + `format_record_id_for_event()`** | ✅ Functional — `packages/kailash-dataflow/src/dataflow/classification/` has `@classify` + `apply_read_classification` (internal) + `format_record_id_for_event` | 🔀 Different — `apply_read_classification()` exists at `crates/kailash-dataflow/src/classification.rs:76`; no `@classify` decorator (Rust uses `#[classification(...)]`); `format_record_id_for_event()` not found in Rust                                 | **Use kailash-py in Phase 01. Issue on kailash-py to expose public API + kailash-rs to add event-payload helper**                                                                          | ISS-23 (kailash-py public API), ISS-24 (kailash-rs event-payload helper)                   |
| 13  | **Kaizen `BaseAgent.execute()`**                                                 | ✅ Functional in kailash-py — `packages/kailash-kaizen/src/kaizen/core/base_agent.py` has working `.run()` + `.execute()`                                        | ⚠️ Stub in binding — raises `NotImplementedError`; 3/7 pre-built agents crash (BINDING-AUDIT B1). Rust uses trait composition (`Agent` trait with async `run()`), not a `BaseAgent` class — so the binding's stub is a design mismatch                     | **Use kailash-py directly for Boundary Conversation agent in Phase 01. File on kailash-rs to redesign agent layer (factories returning WorkerAgent/SupervisorAgent)**                      | ISS-25 (kailash-rs redesign)                                                               |
| 14  | **`OrchestrationRuntime.run()`**                                                 | ❌ Absent as specific class — kailash-py has Kaizen orchestration but not this specific API                                                                      | ⚠️ Stub — returns static dict `{"agents": {"name": "configured"}}` (BINDING-AUDIT B3). Rust side has full `OrchestrationEngine` at `crates/kaizen-agents/src/orchestration/`                                                                               | **Phase 01 schedulers live at Envoy level using kailash-py scheduled agents directly. File on kailash-py to add OrchestrationRuntime; on kailash-rs to connect binding to engine**         | ISS-26 (kailash-py), ISS-27 (kailash-rs)                                                   |
| 15  | **`A2AProtocol.send_message / receive_message`**                                 | ✅ Functional — `src/kailash/trust/a2a/service.py` has A2A HTTP service with JSON-RPC                                                                            | ⚠️ Stub in binding — methods declared in .pyi but not implemented (C6); Rust has `A2AMessage` struct + `InMemoryMessageBus` at `crates/kailash-kaizen/src/a2a/messaging.rs`                                                                                | **Use kailash-py in Phase 01. File on kailash-rs to implement binding methods**                                                                                                            | ISS-28 (kailash-rs binding)                                                                |
| 16  | **`BudgetTracker` + microdollars + SQLiteBudgetStore**                           | ✅ Functional — `src/kailash/trust/constraints/budget_tracker.py`                                                                                                | ✅ Functional — `crates/kailash-kaizen/src/cost/budget.rs:80`; binding exposes `reserve/try_reserve/record/remaining_microdollars/snapshot`. Threshold callbacks NOT exposed                                                                               | **Both sides usable. Phase 01 via kailash-py. File on both for threshold callbacks**                                                                                                       | ISS-29 (kailash-py threshold callbacks), ISS-30 (kailash-rs threshold callbacks binding)   |
| 17  | **Trust Lineage / Genesis Record / Delegation Record / Ed25519**                 | ✅ Functional — `src/kailash/trust/chain.py` + `src/kailash/trust/operations/` + `src/kailash/trust/signing/crypto.py`                                           | ✅ Functional — `EatpTrustOperations`, `EatpDelegationChain`, `EatpOrganizationalAuthority`, `EatpSignature`; `TrustKeyPair` at `crates/eatp/src/keys.rs:1`                                                                                                | **Both sides solid. Load-bearing foundation for doc 03.**                                                                                                                                  | — (no issues)                                                                              |
| 18  | **`EatpDelegationChain.verify()`**                                               | ✅ Functional                                                                                                                                                    | ✅ Functional — `verify_chain()` walks cycles via parent_delegation_id, verifies Ed25519 sigs, checks constraint tightening monotonicity, raises `EatpError::ChainIntegrity`                                                                               | **Both sides solid.**                                                                                                                                                                      | —                                                                                          |
| 19  | **Algorithm-identifier schema + versioned signed-artifact format**               | ❌ Absent — signed records assume current algorithms (Ed25519 + SHA-256)                                                                                         | ❌ Absent — `crates/eatp/src/canonical.rs` + `kailash-audit-vectors` use SHA-256 + Ed25519 directly; **no versioned algorithm tags in wire format**                                                                                                        | **New spec + implementation on BOTH sides. Mint first, then implement**                                                                                                                    | ISS-31 (mint spec for EATP algorithm versioning), ISS-32 (kailash-py), ISS-33 (kailash-rs) |
| 20  | **SKILL.md parser + ENVELOPE.md schema + CO validator**                          | ❌ Absent — no SKILL.md parsing code                                                                                                                             | ❌ Absent                                                                                                                                                                                                                                                  | **Envoy-new code; no spec yet. File mint issue for ENVELOPE.md schema + permission-to-PACT-dimension mapping. Implementation is Envoy's own (Phase 02)**                                   | ISS-34 (mint ENVELOPE.md spec)                                                             |
| 21  | **`DataFlow.execute_raw()` param handling**                                      | ✅ Functional — params passed through in kailash-py                                                                                                              | ⚠️ **SECURITY: params silently dropped in compat layer (H4)** — SQLi surface. Rust source accepts params correctly; the drop is a binding compat-layer bug                                                                                                 | **CRITICAL. Envoy BLOCKS use of kailash-rs-bindings execute_raw until fixed. File SECURITY issue on kailash-rs**                                                                           | **ISS-35 (kailash-rs SECURITY) — BLOCKS Envoy consumption of Rust binding execute_raw**    |
| 22  | **PACT N4/N5 conformance vector Python runner**                                  | ❌ Absent — N6 tests exist but N4/N5 JSON vector runner not implemented                                                                                          | ✅ Functional — `crates/kailash-pact/tests/conformance_vectors.rs` runs N4/N5 JSON vectors with byte-for-byte canonical equality                                                                                                                           | **PHASE 02 BLOCKER for BET-6 cross-runtime parity claim. File HIGH-priority issue on kailash-py**                                                                                          | **ISS-36 (kailash-py) — PHASE 02 BLOCKER**                                                 |
| 23  | **Channel adapters — iMessage/Telegram/Slack/Discord/WhatsApp/Signal**           | ❌ Absent — kailash-py has `APIChannel`, `CLIChannel`, `MCPChannel` but not social-messaging adapters                                                            | ❌ Absent                                                                                                                                                                                                                                                  | **Envoy-new code (Phase 01). No spec issue needed; these are Envoy adapters composing over Nexus webhook primitives. File issues only if adapter contracts surface upstream requirements** | (deferred — Envoy Phase 01 work)                                                           |
| 24  | **SLIP-0039 Shamir library integration**                                         | ❌ Absent                                                                                                                                                        | ❌ Absent                                                                                                                                                                                                                                                  | **Envoy-new code. Use audited 3rd-party libs (Rust: `sharks`/`vsss-rs`; Python: `slip39`/`python-shamir-mnemonic`). File mint issue if Shamir ritual needs spec formalization**            | ISS-37 (mint spec for Shamir ritual)                                                       |
| 25  | **`.pyi` type stubs overall accuracy**                                           | (N/A — kailash-py is pure Python; no .pyi stubs)                                                                                                                 | ⚠️ ~55% accurate; 26 inaccuracies; 8 types missing (BINDING-AUDIT B2)                                                                                                                                                                                      | **File on kailash-rs for .pyi regeneration.**                                                                                                                                              | ISS-38 (kailash-rs .pyi regen)                                                             |
| 26  | **Nexus extractor architecture (S8+)**                                           | ⚠️ Python-side parity pending (terrene-foundation/kailash-py#497)                                                                                                | ✅ Functional — Rust `NexusExtract<S>` trait                                                                                                                                                                                                               | **Existing cross-SDK issue; track and cite**                                                                                                                                               | (existing #497; add cross-ref)                                                             |

---

## 3. Aggregate counts

**kailash-py status (26 primitives):**

- ✅ Functional: 14
- ⚠️ Partial / Stub: 2
- 🔧 Unbound: 0
- ❌ Absent: 9
- 🔀 Different-name: 1

**kailash-rs-bindings status (26 primitives):**

- ✅ Functional: 6
- ⚠️ Partial / Stub: 5
- 🔧 Unbound: 6
- ❌ Absent: 6
- 🔀 Different-name: 3

**Green on BOTH sides (17, 18, 26):** 3 primitives.
**Green on kailash-py, needs work on kailash-rs (1, 2, 3, 5, 15):** 5 primitives — **Phase 01 is viable on kailash-py**.
**Absent on BOTH sides (4, 10, 19, 20, 24):** 5 primitives — Envoy-new or mint-new work.
**Phase 02 blockers:** #22 (N4/N5 Python runner).
**Security-critical:** #21 (execute_raw SQLi in Rust binding).

---

## 4. Phase 01 go / no-go

**Phase 01 GREEN on kailash-py for:**

- Boundary Conversation (via functional Kaizen `BaseAgent`) ✅
- Envelope compile (via `intersect_envelopes()` in `src/kailash/trust/pact/envelopes.py`) ✅
- Delegation + Genesis + cascade revocation ✅
- Budget tracking (via `BudgetTracker`) ✅
- Posture management (via `src/kailash/trust/posture/`) ✅
- L3 Plan DAG ✅
- A2A messaging ✅
- Model providers (Ollama/Claude/GPT/DeepSeek) ✅
- Classification (internal API; Envoy exposes publicly) ✅

**Phase 01 YELLOW (Envoy implements, upstream issues filed):**

- `PlanSuspension` — kailash-py lacks; Envoy can add locally or wait on ISS-13
- `TieredAuditDispatcher` — new; Envoy implements its own hash-chained Ledger dispatcher, cross-files for upstream adoption
- Algorithm-identifier schema — Envoy implements; cross-files mint spec
- 6 channel adapters — Envoy-new code (iMessage/Telegram/Slack/Discord/WhatsApp/Signal)
- SLIP-0039 integration — Envoy pulls audited libs
- Independent reference verifier — Envoy-new

**Phase 02 BLOCKERS (must close before Phase 02 opens):**

- **ISS-36 — N4/N5 Python conformance runner** (otherwise BET-6 is non-falsifiable)
- **ISS-35 — Rust binding execute_raw SQLi fix** (otherwise Envoy cannot consume Rust binding for DataFlow)

**Upstream-only work (deferred until needed):**

- Phase-13 bundle completeness on Rust binding (ISS-11, -12)
- OrchestrationRuntime binding (ISS-26, -27)
- A2A binding methods (ISS-28)
- MCP transports + governance enforcer (ISS-17, -20, -21)
- `@classify` + event-payload helpers on Rust binding (ISS-24)
- `.pyi` regen (ISS-38)

---

## 5. Master GH issue list (direct filing)

Total **38 issues** across 3 repos. Cross-filed per Foundation parity posture — each Rust-binding issue has a matching kailash-py issue (or is explicitly kailash-rs-only if the gap is binding-specific).

### Cross-filing pattern

Every issue body includes:

- **Reference to audit doc:** `workspaces/phase-00-alignment/01-analysis/01-kailash-rs-deep-audit.md` or `02-kailash-py-survey.md`.
- **Sibling issue reference** on the other repo (added after filing both).
- **Severity + phase impact** — Phase 01 blocker / Phase 02 blocker / upstream-only.

### List

**`esperie-enterprise/kailash-rs` (18 issues):**

- ISS-01 Expose `ConstraintEnvelope.intersect()` via PyO3 as `intersect_envelopes()`
- ISS-03 Expose `RoleEnvelope` and `TaskEnvelope` types for PACT governance queries
- ISS-04 Document cascade revocation behavior + explicit cascade API in `EatpDelegationChain.revoke()`
- ISS-08 **New primitive:** `TieredAuditDispatcher` implementation (mirror mint spec ISS-06)
- ISS-09 **New primitive:** `PostureStore` / `SQLitePostureStore` / `PostureEvidence` (Rust source has only posture types, not stores)
- ISS-11 Phase-13 type bundle exposure + .pyi regeneration
- ISS-14 Expose `SuspensionReason` + `SuspensionRecord` + `Plan.suspension` via PyO3
- ISS-15 Verify complete L3 Plan DAG .pyi coverage
- ISS-16 Expose complete `LlmDeployment` surface (4-axis + 18 presets)
- ISS-18 **New primitive:** `McpGovernanceEnforcer` / `McpGovernanceMiddleware`
- ISS-20 MCP transport bindings (stdio / SSE / HTTP) for Python
- ISS-24 `apply_read_classification()` + `format_record_id_for_event()` event-payload helper exposure
- ISS-25 Replace `BaseAgent.execute()` stub with trait-based factories
- ISS-27 `OrchestrationRuntime.run()` binding to connect to Rust engine
- ISS-28 `A2AProtocol.send_message` + `receive_message` PyO3 implementation
- ISS-30 `BudgetTracker.set_threshold_callback()` binding
- ISS-33 Algorithm-identifier schema + versioned signed-artifact format (mirror mint ISS-31)
- **ISS-35 SECURITY: Fix `DataFlow.execute_raw()` param-drop (SQL injection surface)**
- ISS-38 `.pyi` type stub regeneration (~55% accurate → target ≥95%)

**`terrene-foundation/kailash-py` (13 issues):**

- ISS-02 Confirm semantic parity of `intersect_envelopes()` with Rust `ConstraintEnvelope.intersect()`
- ISS-05 Cascade revocation docstring cross-reference with Rust
- ISS-07 **New primitive:** `TieredAuditDispatcher` implementation (mirror ISS-06/08)
- ISS-12 Phase-13 bundle completeness (confirm all 8 types present)
- ISS-13 Implement `PlanSuspension` (present in Rust as `SuspensionReason`/`Record`)
- ISS-19 **New primitive:** `McpGovernanceEnforcer` (mirror ISS-17/18)
- ISS-21 MCP transport primitives (stdio / SSE / HTTP)
- ISS-23 Expose `apply_read_classification()` + `format_record_id_for_event()` on public API
- ISS-26 Implement `OrchestrationRuntime` class + `.run()` method
- ISS-29 `BudgetTracker` threshold callback API
- ISS-32 Algorithm-identifier schema implementation (mirror mint ISS-31)
- **ISS-36 HIGH: Implement PACT N4/N5 conformance vector Python runner** — Phase 02 BLOCKER
- (ISS-37 if kailash-py needs to host a reference Shamir integration — optional)

**`terrene-foundation/mint` (7 issues):**

- ISS-06 **New spec:** `TieredAuditDispatcher` — hash-chained tier-based audit retention
- ISS-10 **New spec:** `PostureStore` / `PostureEvidence` — formalize the posture-persistence primitive across EATP/PACT
- ISS-17 **New spec:** `McpGovernanceEnforcer` / `McpGovernanceMiddleware` — PACT-constrained MCP tool invocation
- ISS-22 MCP transport protocol extension (if current spec does not cover transport abstractions)
- ISS-31 **New spec:** Algorithm-identifier versioning in EATP signed artifacts — addresses `rules/terrene-naming.md` requirement
- ISS-34 **New spec:** `ENVELOPE.md` schema + permission-to-PACT-dimension mapping — formalizes SKILL.md interop
- ISS-37 **New spec:** Shamir 3-of-5 recovery ritual — formalizes SLIP-0039 integration patterns for Trust Vault

---

## 6. Envoy doc 00 §3.3 rewrite source-of-truth

This table directly feeds the v2 doc 00 §3.3. Every row in doc 00 §3.3 resolves to a row in this grid. Issue numbers `#TBD` in doc 00 become concrete once filing concludes.

**Updated 70/30 ratio:** Of 26 primitives, **17 are green on kailash-py** (65%), **3 are green on both sides** (12%). Envoy Phase 01 composes on kailash-py confidently; Phase 02 cross-runtime parity depends on closing ISS-35 + ISS-36 + at least 12 binding issues upstream.

---

## 7. Consequences for doc 00 v2

Already captured in doc 00 v2:

- §3.3 three-column table structure — this reconciliation provides the definitive rows.
- BET-9a (upstream sufficient) — confirmed at high confidence: only 5 primitives genuinely absent on BOTH sides; all of them are Envoy-scopable.
- BET-9b (binding exposure) — confirmed as a real but scoped concern: 18 issues on kailash-rs; Phase 01 on kailash-py sidesteps most.
- BET-6 (contract parity) — ISS-36 (N4/N5 Python runner) is the single Phase 02 gate.

**New finding surfaced:**

- **kailash-py has `specs/` directory with 55 spec files** — cite `specs/trust-plane-core.md`, `specs/pact-governance.md`, `specs/kaizen-agents-core.md` from Envoy's own specs/. This strengthens doc 10 (data model) and doc 03 (trust lineage).
- **Algorithm-identifier versioning is absent on BOTH sides** (item 19). Envoy's §4.1 item 9 claim requires a mint spec AND implementations. This is the single most ambitious cross-cutting scope add surfaced by the audits.

---

**Next action:** File the 38 GH issues in batches, then update doc 00 §3.3 with concrete issue references, then run Round 2 redteam.
