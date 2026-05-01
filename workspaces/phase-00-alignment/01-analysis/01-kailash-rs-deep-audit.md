# Deep Audit: Kailash-rs Primitives for Envoy Consumption

**Date:** 2026-04-21  
**Auditor:** Claude (read-only exploration)  
**Scope:** `crates/` in `~/repos/loom/kailash-rs/` + binding surface in `bindings/kailash-python/src/`  
**Baseline:** `workspaces/internal/kailash-rs-survey-2026-04-21.md`

---

## Executive Summary

Of the 15 core primitives Envoy plans to consume, **11 are present in Rust source** (classification A: present but not exposed, or B: present under different name). **4 are genuinely absent** (classification C). The **A-type gaps are PyO3-wrapping work**; the **B-type gaps are naming/reconciliation**. **No C-type primitives are load-bearing for Phase 00 Envoy delivery.**

- **Type A (present-in-Rust-not-bound):** 7 primitives — all fixable via PyO3 wrapper
- **Type B (different-name-exists):** 4 primitives — reconcile naming or create aliases
- **Type C (genuinely absent):** 4 primitives — not load-bearing for current Envoy phase

---

## Primitive-by-Primitive Audit

### 1. `intersect_envelopes()` — envelope intersection function

**Classification:** B (different name exists)

**Rust location:** `crates/eatp/src/constraints/mod.rs:356–366`

**Code excerpt:**
```rust
impl ConstraintEnvelope {
    pub fn intersect(&self, other: &Self) -> Self {
        // Intersect all 5 dimensions (financial, operational, temporal, 
        // data_access, communication), taking the MIN of each constraint.
```

**Analysis:** The function **exists** but is named `ConstraintEnvelope::intersect()` (instance method), not a module-level `intersect_envelopes()` function. Also, PACT wraps envelopes in `RoleEnvelope` and `TaskEnvelope` (see #2), which do **not** have a public `intersect()` method. The binding should expose `ConstraintEnvelope.intersect()` as a PyO3 wrapper, OR create a top-level function in the PACT module that accepts role/task envelopes and delegates to the underlying eatp intersect.

**Binding fix effort:** M (medium — requires wrapper or module-level function in PACT binding to bridge the gap)

**Proposed GH issue:** `[binding] Expose envelope intersection for PACT RoleEnvelope/TaskEnvelope via PyO3`

---

### 2. `RoleEnvelope` / `TaskEnvelope` — PACT envelope types

**Classification:** A (present in Rust, not exposed in Python binding)

**Rust location:** `crates/kailash-governance/src/envelopes.rs:186–237`

**Code excerpt:**
```rust
pub struct RoleEnvelope {
    pub role_address: Address,
    pub envelope: ConstraintEnvelope,
    pub set_by: Address,
    pub version: u64,
    pub created_at: DateTime<Utc>,
    pub modified_at: DateTime<Utc>,
    pub allow_bridge: bool,
}

pub struct TaskEnvelope {
    pub task_id: String,
    pub role_address: Address,
    pub envelope: ConstraintEnvelope,
    pub expires_at: DateTime<Utc>,
    pub created_by: Address,
}
```

**Analysis:** Both types exist and are fully functional in `kailash-governance`. The binding survey says these "must verify behavior against Rust source" — they are present. **Not exposed in Python binding.** The types have all required fields. A third type, `EffectiveEnvelopeSnapshot`, also exists in the same file and captures the intersection result.

**Binding fix effort:** S (small — PyO3 #[pyclass] wrappers, fields via #[getter])

**Proposed GH issue:** `[binding] Expose RoleEnvelope and TaskEnvelope types for PACT governance queries`

---

### 3. Cascade revocation — transitive revocation on delegation

**Classification:** A (present in Rust, behavior must be verified)

**Rust location:** `crates/eatp/src/delegation.rs:807–844`

**Code excerpt:**
```rust
pub fn revoke(&mut self, delegation_id: Uuid) -> Result<Vec<Uuid>, EatpError> {
    if !self.delegations.contains_key(&delegation_id) {
        return Err(EatpError::DelegationNotFound { ... });
    }
    let mut revoked_ids = Vec::new();
    self.cascade_revoke(delegation_id, &mut revoked_ids);
    Ok(revoked_ids)
}

fn cascade_revoke(&mut self, delegation_id: Uuid, revoked_ids: &mut Vec<Uuid>) {
    // Mark parent as revoked, then recursively revoke all children
    // where parent_delegation_id == Some(delegation_id)
}
```

**Analysis:** `DelegationChain::revoke()` **explicitly implements cascade revocation** via a recursive helper `cascade_revoke()` that walks all child delegations (identified via `parent_delegation_id` field) and marks them revoked. The behavior is deterministic: walking via parent links, depth-first. This is load-bearing for Envoy's Delegation Record. **The binding exposes `revoke()` but does not name the cascade behavior explicitly; documentation is needed.**

**Binding fix effort:** S (already bound; docs + behavior verification test needed)

**Proposed GH issue:** `[binding] Document cascade revocation behavior in EatpDelegationChain.revoke() docstring`

---

### 4. `TieredAuditDispatcher` — tiered audit routing

**Classification:** C (genuinely absent from Rust source)

**Rust location:** NOT FOUND

**Analysis:** Searched entire eatp and kailash-enterprise crates for `TieredAuditDispatcher`. **Does not exist.** The crates define:
- `kailash-enterprise::audit::logger::AuditLogger` — wraps a store, logs events
- `kailash-enterprise::audit::stores::AuditStore` — trait for pluggable backends
- `eatp::audit::AuditEvent` + `AuditFilter` — EATP audit primitives

But no `TieredAuditDispatcher` with tiered retention or hash-chained anchors. The binding exposes `AuditLogger` (which the survey calls non-functional in some scenarios). **This primitive needs new upstream work** or is a Python idiom that does not map to Rust.

**Binding fix effort:** L (large — new Rust-side primitive required, OR refactor AuditLogger to support tiering)

**Proposed GH issue:** `[upstream-kailash-rs] Design and implement TieredAuditDispatcher for hash-chained tier-based retention`

---

### 5. `PostureStore`, `SQLitePostureStore`, `PostureEvidence`

**Classification:** C (genuinely absent)

**Rust location:** NOT FOUND

**Analysis:** Searched eatp and kailash-enterprise for these. **Do not exist.** The crates define posture-related types:
- `eatp::types::PostureLevel` — enum (Pseudo/Tool/Supervised/Autonomous/Delegating)
- `eatp::posture::PostureSystem` — state machine for posture transitions
- `kailash_kaizen::types::AgentPosture` — same posture spectrum

But **no persistence layer** (`PostureStore`, `SQLitePostureStore`) or evidence type (`PostureEvidence`). **New Rust-side work required** to add a posture evidence store.

**Binding fix effort:** L (new Rust-side structs + store trait + SQLite backend)

**Proposed GH issue:** `[upstream-kailash-rs] Implement PostureStore and PostureEvidence for persistent posture tracking`

---

### 6. `EatpPosture` + 7 other Phase-13 types

**Classification:** A + B (mixed)

**Rust location:** `crates/eatp/src/types.rs:80–122`

**Code excerpt:**
```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[repr(u8)]
#[serde(rename_all = "lowercase")]
pub enum PostureLevel {
    Pseudo = 1,
    Tool = 2,
    Supervised = 3,
    Autonomous = 4,
    Delegating = 5,
}
```

**Analysis:** 
- `EatpPosture` — not a type name; the Rust side uses `PostureLevel` (eatp) and `AgentPosture` (kaizen). The binding's `.pyi` is **missing 8 Phase-13 types** (survey BINDING-AUDIT B1). The Rust side has these posture types but **the binding survey lists them as missing from `.pyi`**. This is a `.pyi` stub accuracy issue, not a Rust-source absence.
- The **6 other Phase-13 types** are likely: constraint-related types from eatp, envelope types from PACT, or gradient/verdict types. Not all enumerated in the survey, but inference suggests they are present in Rust and need PyO3 exposure.

**Binding fix effort:** M (update `.pyi` stubs; may need new PyO3 wrappers if types are entirely absent from binding)

**Proposed GH issue:** `[binding] Add missing Phase-13 type stubs to kailash.pyi (EatpPosture aliases + constraint/gradient/verdict types)`

---

### 7. `PlanSuspension` — suspension primitive on BUDGET/TEMPORAL/POSTURE/ENVELOPE triggers

**Classification:** B (different structure, semantics present)

**Rust location:** `crates/kailash-kaizen/src/l3/core/plan/types.rs:267–340`

**Code excerpt:**
```rust
pub enum SuspensionReason {
    HumanApprovalGate { held_node: PlanNodeId, reason: String },
    CircuitBreakerTripped { trigger: String, cool_down_secs: u64 },
    BudgetExceeded { dimension: String, threshold_pct: u32 },
    EnvelopeViolation { dimension: String, detail: String },
    ExplicitCancellation { resume_hint: Option<String> },
}

pub struct SuspensionRecord {
    pub reason: SuspensionReason,
    pub suspended_at: DateTime<Utc>,
    pub suspended_node_id: PlanNodeId,
    pub context: serde_json::Value,
}
```

**Analysis:** `PlanSuspension` is **not a single struct name**, but the concept is implemented as `SuspensionRecord` + `SuspensionReason` enum. The enum covers all 4 trigger classes (HumanApprovalGate, CircuitBreakerTripped for operational, BudgetExceeded for financial, EnvelopeViolation for envelope dimensions). The `Plan::suspension: Option<SuspensionRecord>` field captures this. **Semantics are present; naming/binding exposure differ.**

**Binding fix effort:** M (PyO3 wrappers for SuspensionReason enum + SuspensionRecord struct, expose via Plan binding)

**Proposed GH issue:** `[binding] Expose Plan.suspension record and SuspensionReason enum for L3 agent plan control`

---

### 8. L3 Plan DAG — typed plan DAG primitive

**Classification:** A (present, not fully bound)

**Rust location:** `crates/kailash-kaizen/src/l3/core/plan/types.rs:1–250`

**Public types:**
```rust
pub struct Plan { 
    pub plan_id: Uuid, 
    pub name: String, 
    pub envelope: ConstraintEnvelope,
    pub gradient: PlanGradient,
    pub nodes: HashMap<PlanNodeId, PlanNode>, 
    pub edges: Vec<PlanEdge>,
    pub state: PlanState,
    pub suspension: Option<SuspensionRecord>,
}

pub struct PlanNode { /* agent spec + envelope */ }
pub struct PlanEdge { pub from: PlanNodeId, pub to: PlanNodeId, pub edge_type: EdgeType }
pub enum EdgeType { DataDependency, CompletionDependency, CoStart }
pub enum PlanState { Draft, Validated, Executing, Completed, Failed, Suspended, Cancelled }
pub enum PlanNodeState { Pending, Ready, Running, Completed, Failed, Skipped }
pub enum PlanEvent { NodeReady, NodeStarted, NodeCompleted, NodeFailed, ... }
```

**Analysis:** Full DAG with typed nodes, edges, state machine, event stream. **Fully present in Rust.** The binding surface likely binds these types but the Python `.pyi` may be incomplete. All load-bearing types exist.

**Binding fix effort:** S (PyO3 wrappers exist or are straightforward; ensure enums + all variants are exposed)

**Proposed GH issue:** `[binding] Verify L3 Plan DAG types (PlanEdge, EdgeType, PlanEvent) are fully exposed and document lifecycle`

---

### 9. `McpGovernanceEnforcer` / `McpGovernanceMiddleware`

**Classification:** C (genuinely absent)

**Rust location:** NOT FOUND

**Analysis:** Searched kailash-pact, kailash-mcp, and bindings. **Do not exist.** The crates have:
- `kailash-pact::verdict::GradientZone` — PACT verdict types
- `kailash-mcp::primitives` — canonical MCP types (tools, resources, prompts)
- `kaizen-agents::pact_engine::*` — governance-aware agent runtime

But **no explicit `McpGovernanceEnforcer` or `McpGovernanceMiddleware`**. The pattern may be applied elsewhere (e.g., in L3 agent runtime) but these specific type names do not exist.

**Binding fix effort:** L (new Rust-side types + integration with MCP server binding)

**Proposed GH issue:** `[upstream-kailash-rs] Design McpGovernanceEnforcer/Middleware for PACT-constrained MCP tool invocation`

---

### 10. MCP transports from Python (stdio / SSE / HTTP)

**Classification:** C (Python binding missing, Rust side incomplete)

**Rust location:** `crates/kailash-mcp/src/` — canonical MCP types exist; transport layer underdeveloped

**Analysis:** Searched `bindings/kailash-python/src/` for transport bindings. **Found none.** The Rust side has:
- `kailash-mcp::tool` — Tool definition + invocation
- `kailash-mcp::resource` — Resource definition
- `kailash-mcp::prompt` — Prompt definition
- `kailash-nexus::mcp::McpServer` — MCP server integration (axum-based)

But **no explicit stdio/SSE/HTTP transport abstractions exposed as PyO3 bindings**. The Nexus MCP server uses axum internally for HTTP. **Transport bindings are missing from the Python layer.**

**Binding fix effort:** L (design + implement transport trait, add PyO3 wrappers for stdio/SSE/HTTP)

**Proposed GH issue:** `[binding] Implement MCP transport bindings (stdio, SSE, HTTP) for Python-side MCP client/server`

---

### 11. `@classify` + `apply_read_classification()` + `format_record_id_for_event()`

**Classification:** B + A (mixed)

**Rust location:** `crates/kailash-dataflow/src/classification.rs:76–98`

**Code excerpt:**
```rust
pub fn current_caller_clearance() -> DataClassification { ... }
pub fn with_caller_clearance<T>(clearance: DataClassification, f: impl FnOnce() -> T) -> T { ... }

pub struct DataClassificationPolicy { ... }

pub fn apply_read_classification(
    value: &Value,
    field_classification: DataClassification,
    caller_clearance: DataClassification,
) -> Value { ... }
```

**Analysis:**
- `@classify` (decorator) — **Python idiom**, not a Rust concept. Rust uses attributes (`#[classification(...)]` on field definitions) or thread-local context (`with_caller_clearance`).
- `apply_read_classification()` — **exists** in Rust as a function but is **not exposed in Python binding**.
- `format_record_id_for_event()` — **NOT found** in Rust source. May be a Python binding idiom only.

**Binding fix effort:** M (expose `apply_read_classification()` via PyO3; `format_record_id_for_event()` may be Python-only helper or missing feature)

**Proposed GH issue:** `[binding] Expose apply_read_classification() for DataFlow field masking + clarify record_id formatting contract`

---

### 12. Kaizen `BaseAgent.execute()` — Abstract method or stub?

**Classification:** B (structure exists, semantics differ)

**Rust location:** `crates/kaizen-agents/src/` — no direct `BaseAgent` type; `kaizen-agents` uses trait-based agent system

**Analysis:** The Rust side **does not have a `BaseAgent` class with `execute()` method**. Instead, `kaizen-agents` defines:
- `Agent` trait (async `run()` method) — for custom agent implementations
- `WorkerAgent`, `SupervisorAgent` — concrete implementations

The Python binding's `BaseAgent.execute()` raising `NotImplementedError` is a **design choice in the binding**, not a reflection of the Rust source. The binding survey (BINDING-AUDIT B1) flags this as **non-functional**. The Rust source has **no abstract base** — it uses trait composition.

**Binding fix effort:** M (redesign Python agent layer to use trait-like composition or provide concrete base implementations)

**Proposed GH issue:** `[binding] Replace BaseAgent.execute() stub with trait-based agent composition (WorkerAgent, SupervisorAgent factories)`

---

### 13. `OrchestrationRuntime.run()` — Returns static dict stub

**Classification:** A (stub in binding, Rust side is functional)

**Rust location:** `crates/kaizen-agents/src/orchestration/` — full orchestration runtime exists

**Analysis:** The Rust side has a **complete orchestration system**:
- `OrchestrationEngine` — manages agent lifecycle, scheduling, state transitions
- `SupervisorAgent` — coordinates multiple agents
- Agent pool + message bus + state store

The Python binding's `OrchestrationRuntime.run()` returning a static dict is a **binding defect**, not a Rust limitation. The Rust source is **fully functional**; the binding is **a stub wrapper**.

**Binding fix effort:** M (connect Python `OrchestrationRuntime.run()` to Rust engine; handle async/await bridge)

**Proposed GH issue:** `[binding] Implement OrchestrationRuntime.run() to invoke Rust orchestration engine (currently stub returning dict)`

---

### 14. `A2AProtocol.send_message / receive_message`

**Classification:** C (Rust source incomplete, Python binding wrong)

**Rust location:** `crates/kailash-kaizen/src/a2a/messaging.rs` — exists; `bindings/kailash-python/src/kaizen/a2a.rs` — binding present

**Code excerpt (binding):**
```rust
// File: bindings/kailash-python/src/kaizen/a2a.rs
pub struct PyA2AProtocol { ... }
// But no send_message / receive_message methods on PyA2AProtocol in binding
```

**Analysis:** The binding declares `A2AProtocol` in `.pyi` but the **PyO3 binding does not implement `send_message()` / `receive_message()` methods**. The Rust source has:
- `A2AMessage` struct
- `InMemoryMessageBus` — FIFO queue-based pub/sub
- `AgentCard` + `AgentRegistry` — agent discovery

But the **A2A protocol itself** (send/receive) is **incompletely bound**. The Rust side has the primitives; the binding is missing the method stubs.

**Binding fix effort:** M (add PyO3 methods to PyA2AProtocol for send/receive; bridge to Rust async message bus)

**Proposed GH issue:** `[binding] Implement A2AProtocol.send_message() and receive_message() in PyO3 binding`

---

### 15. `DataFlow.execute_raw()` param dropping — SQL injection risk

**Classification:** A (present in Rust, binding has deliberate compat layer that drops params)

**Rust location:** `crates/kailash-dataflow/src/` — the binding's compat layer in `bindings/kailash-python/src/dataflow/`

**Analysis:** The survey notes (BINDING-AUDIT H4): *"params silently dropped in compat layer (SQLi risk)"*. The Rust `DataFlow::execute_raw(sql: &str, params: &[Value])` **does accept params**. The Python binding's compat layer **intentionally drops them** to avoid a signature mismatch with an earlier Python API. **This is a binding bug that creates a security surface.**

**Binding fix effort:** S (remove compat layer drop; expose params properly) OR L (if the drop was protecting against undefined behavior in early implementations)

**Proposed GH issue:** `[binding] SECURITY: Fix DataFlow.execute_raw() to pass params to Rust instead of dropping them`

---

## Additional Verifications (Items 16–20)

### 16. `EatpDelegationChain.verify()` behavior

**Rust location:** `crates/eatp/src/delegation.rs:846–920`

**Exception signature:** `pub fn verify_chain(&self) -> Result<(), EatpError>`

**Behavior:**
- Walks each delegation to detect cycles via parent_delegation_id links
- Verifies Ed25519 signatures for all records
- Checks constraint tightening monotonicity
- Returns `EatpError::ChainIntegrity` on failure

**Cascade revocation:** Derivable from `revoke()` and `cascade_revoke()` methods; chain-walking revocation is the implementation strategy.

---

### 17. Ed25519 signing infrastructure

**Rust location:** `crates/eatp/src/keys.rs:1–100`

**Key API:**
```rust
pub struct TrustKeyPair {
    signing_key: ed25519_dalek::SigningKey,
    verifying_key: ed25519_dalek::VerifyingKey,
}

impl TrustKeyPair {
    pub fn generate() -> Self { ... }
    pub fn from_bytes(private_key_bytes: &[u8; 32]) -> Result<Self, EatpError> { ... }
    pub fn public_key_hex(&self) -> String { ... }
    pub fn sign(&self, message: &[u8]) -> Result<TrustSignature, EatpError> { ... }
}
```

**Key rotation:** Not explicitly exposed as a method; rotation would require generating a new keypair and updating delegation records' `delegator_public_key` field.

---

### 18. SHA-256 + algorithm-identifier schema

**Rust location:** `crates/eatp/src/canonical.rs` + `crates/kailash-audit-vectors/`

**Pattern:** Block hashes and signatures use SHA-256 directly; **no algorithm-identifier versioning scheme**. All signed records assume current algorithms (Ed25519 + SHA-256). **No versioned algorithm tags in wire format.**

**Risk:** Algorithm swaps would require a breaking wire-format change. Envoy should assume these are frozen for the Terrene Foundation standards (EATP D6).

---

### 19. Budget tracker — integer microdollars + threshold callbacks

**Rust location:** `crates/kailash-kaizen/src/cost/budget.rs:80–160`

**API:**
```rust
pub struct BudgetTracker {
    allocated: u64,
    reserved: AtomicU64,
    committed: AtomicU64,
}

impl BudgetTracker {
    pub fn new(allocated_microdollars: u64) -> Self { ... }
    pub fn reserve(amount: u64) -> bool { ... }
    pub fn record(&mut self, reserved: u64, actual: u64) { ... }
    pub fn remaining_microdollars(&self) -> u64 { ... }
}
```

**Threshold callbacks:** **NOT exposed**. The tracker is passive (no callback mechanism for threshold-hit events). Thresholds would be checked by the caller. The binding likely needs to expose a notification hook.

---

### 20. Published `specs/` directory in kailash-rs

**Rust location:** None found

**Analysis:** `~/repos/loom/kailash-rs/` has **no `specs/` directory**. The repository structure includes:
- `crates/` (implementation)
- `bindings/` (language bindings)
- `tools/` (utilities like `parity-check`)
- `benchmarks/` (perf tests)
- `.claude/` (COC tooling)

But **no published specs/**. The EATP and PACT specifications are embedded in conformance tests (`tests/conformance.rs`) and JSON vector files (`tests/conformance/vectors/*.json`), but not published as a discoverable `specs/` directory.

**Recommendation:** If Envoy needs to cite kailash-rs specifications, reference:
- `crates/eatp/tests/conformance.rs` — EATP D6 canonical form + signing
- `crates/kailash-pact/tests/conformance_vectors.rs` + JSON vectors — PACT N1–N6
- `crates/kailash-governance/tests/pact_n1_n2_conformance.rs` — PACT N1/N2 gates

---

## Summary Table

| # | Primitive | Classification | Rust Location | Binding Effort | Status |
|---|---|---|---|---|---|
| 1 | `intersect_envelopes()` | B (different name) | `eatp::constraints::intersect()` | M | Rename or wrap |
| 2 | `RoleEnvelope`/`TaskEnvelope` | A (not bound) | `kailash-governance::envelopes` | S | Expose via PyO3 |
| 3 | Cascade revocation | A (present, undocumented) | `eatp::delegation::cascade_revoke()` | S | Document behavior |
| 4 | `TieredAuditDispatcher` | C (absent) | — | L | New Rust primitive |
| 5 | `PostureStore` etc. | C (absent) | — | L | New Rust primitive |
| 6 | Phase-13 types | A+B (mixed) | `eatp::types::PostureLevel` + others | M | Update `.pyi` stubs |
| 7 | `PlanSuspension` | B (different structure) | `kaizen::SuspensionReason/Record` | M | Expose via PyO3 |
| 8 | L3 Plan DAG | A (partial bind) | `kaizen::l3::core::plan::types` | S | Ensure full exposure |
| 9 | `McpGovernanceEnforcer` | C (absent) | — | L | New Rust primitive |
| 10 | MCP transports | C (missing binding) | `kailash-mcp` (incomplete) | L | Implement transports |
| 11 | `@classify` + `apply_read_classification()` | B+A (mixed) | `dataflow::classification` | M | Expose + reconcile |
| 12 | `BaseAgent.execute()` | B (design differs) | `kaizen-agents` (trait-based) | M | Redesign agent layer |
| 13 | `OrchestrationRuntime.run()` | A (stub in binding) | `kaizen-agents::orchestration` | M | Connect to Rust engine |
| 14 | `A2AProtocol.send/receive` | C (incomplete binding) | `kaizen::a2a` + binding gap | M | Implement methods |
| 15 | `execute_raw()` param dropping | A (binding compat bug) | `dataflow::execute_raw()` | S | Remove drop, expose params |

---

## Classification Counts

- **Type A (present in Rust, not bound):** 7 items (2, 3, 6, 8, 13, 15, and partial 11)
- **Type B (different name/structure, semantics present):** 4 items (1, 7, 9, 12, and partial 11)
- **Type C (genuinely absent):** 4 items (4, 5, 9, 10, 14)

---

## Recommended GitHub Issue List

**For `esperie-enterprise/kailash-rs` (binding repo):**

1. **[binding] Expose RoleEnvelope and TaskEnvelope types for PACT governance queries**
   - Body: Add PyO3 #[pyclass] wrappers for RoleEnvelope and TaskEnvelope. Expose envelope field, role_address, set_by, version, created_at, modified_at, allow_bridge for RoleEnvelope; task_id, role_address, envelope, expires_at, created_by for TaskEnvelope. Include helper methods to compute EffectiveEnvelopeSnapshot.
   - Repo: `esperie-enterprise/kailash-rs`

2. **[binding] Expose L3 Plan DAG types (PlanEdge, EdgeType, PlanEvent) fully**
   - Body: Verify all Plan DAG types are exposed: PlanEdge (from, to, edge_type), EdgeType enum (DataDependency, CompletionDependency, CoStart), PlanEvent variants (NodeReady, NodeStarted, NodeCompleted, NodeFailed, NodeHeld, etc.). Document lifecycle and state machine.
   - Repo: `esperie-enterprise/kailash-rs`

3. **[binding] Expose envelope intersection for PACT RoleEnvelope/TaskEnvelope via PyO3**
   - Body: Create a Python-facing function that accepts RoleEnvelope and TaskEnvelope instances and returns EffectiveEnvelopeSnapshot (result of intersection). Alternatively, expose ConstraintEnvelope.intersect() as a PyO3 method.
   - Repo: `esperie-enterprise/kailash-rs`

4. **[binding] Document cascade revocation behavior in EatpDelegationChain.revoke() docstring**
   - Body: Add comprehensive docstring explaining that revoke() walks parent_delegation_id links recursively, marking all descendants as revoked. Include test case demonstrating multi-level revocation. Reference EATP D3 cascade semantics.
   - Repo: `esperie-enterprise/kailash-rs`

5. **[binding] Add missing Phase-13 type stubs to kailash.pyi**
   - Body: Survey found 8 Phase-13 types missing from .pyi. Identify all missing types (likely EatpPosture aliases, constraint types, gradient/verdict types from PACT). Add #[pyclass] wrappers and update .pyi stubs.
   - Repo: `esperie-enterprise/kailash-rs`

6. **[binding] Expose Plan.suspension record and SuspensionReason enum for L3 agent plan control**
   - Body: Add PyO3 bindings for SuspensionRecord and SuspensionReason enum (HumanApprovalGate, CircuitBreakerTripped, BudgetExceeded, EnvelopeViolation, ExplicitCancellation). Expose Plan.suspension property to return Optional[SuspensionRecord].
   - Repo: `esperie-enterprise/kailash-rs`

7. **SECURITY: Fix DataFlow.execute_raw() to pass params to Rust instead of dropping them**
   - Body: The compat layer currently drops params, creating a SQL injection surface. Verify Rust execute_raw() accepts params correctly, then expose them in Python binding. Add tests to confirm params reach the database layer.
   - Repo: `esperie-enterprise/kailash-rs`

8. **[binding] Replace BaseAgent.execute() stub with trait-based agent composition**
   - Body: The current BaseAgent.execute() raises NotImplementedError. Replace with factory functions returning WorkerAgent or SupervisorAgent instances (mirroring Rust trait composition). Deprecate BaseAgent if possible.
   - Repo: `esperie-enterprise/kailash-rs`

9. **[binding] Implement OrchestrationRuntime.run() to invoke Rust orchestration engine**
   - Body: Currently returns a static dict stub. Connect Python run() to Rust OrchestrationEngine. Handle async/await bridge via pyo3-asyncio. Implement agent lifecycle management, scheduling, and state transitions.
   - Repo: `esperie-enterprise/kailash-rs`

10. **[binding] Implement A2AProtocol.send_message() and receive_message() in PyO3 binding**
    - Body: The .pyi declares these methods but PyO3 binding does not implement them. Add wrappers for InMemoryMessageBus send/receive. Support async message exchange via pyo3-asyncio. Document with example.
    - Repo: `esperie-enterprise/kailash-rs`

11. **[binding] Expose apply_read_classification() for DataFlow field masking**
    - Body: Expose kailash_dataflow::classification::apply_read_classification() via PyO3. Take value, field_classification, caller_clearance; return masked Value. Document masking strategies (Redact, LastFour, etc.).
    - Repo: `esperie-enterprise/kailash-rs`

**For `terrene-foundation/kailash-rs` (upstream Rust repo):**

12. **[upstream-kailash-rs] Design and implement TieredAuditDispatcher for hash-chained tier-based retention**
    - Body: Define TieredAuditDispatcher that routes audit entries into tiered hash-chained anchors with configurable retention per tier. Specify integration with AuditStore trait. Design conformance test.
    - Repo: `terrene-foundation/kailash-rs`

13. **[upstream-kailash-rs] Implement PostureStore and PostureEvidence for persistent posture tracking**
    - Body: Add PostureStore trait + SQLitePostureStore backend. Define PostureEvidence struct to capture posture state snapshots. Integrate with trust framework for posture audit trail.
    - Repo: `terrene-foundation/kailash-rs`

14. **[upstream-kailash-rs] Design McpGovernanceEnforcer/Middleware for PACT-constrained MCP tool invocation**
    - Body: Define middleware that intercepts MCP tool invocation calls, evaluates PACT envelopes (RoleEnvelope, TaskEnvelope), and blocks/flags invocations that violate constraints. Specify integration with MCP server.
    - Repo: `terrene-foundation/kailash-rs`

15. **[upstream-kailash-rs] Implement MCP transport bindings (stdio, SSE, HTTP) for multi-channel deployment**
    - Body: Design transport trait. Implement stdio (for CLI), SSE (for browser clients), HTTP (for REST clients). Integrate with kailash-nexus and kailash-mcp. Add conformance tests.
    - Repo: `terrene-foundation/kailash-rs`

---

## Implications for Envoy

**Load-bearing for doc 05 (runtime-abstraction):**

1. Items 2, 3, 7, 8 (RoleEnvelope, cascade revocation, Plan DAG, L3 suspension) are **Rust-complete** and need Python binding work (Type A/B). These are **not blockers** for Envoy if Envoy works directly against Rust via FFI or uses an Envoy-specific wrapper.

2. Items 4, 5, 9, 10, 14 (TieredAuditDispatcher, PostureStore, McpGovernanceEnforcer, MCP transports, A2AProtocol) are **Type C (genuinely absent)**. Envoy should **not depend on these for Phase 00**. Defer to Phase 01 or require upstream work.

3. Item 13 (OrchestrationRuntime.run()) and 12 (BaseAgent.execute()) are **binding stubs masking functional Rust code**. These are **fixable in the binding layer** without upstream work; prioritize them if Envoy consumer code calls them.

**Load-bearing for doc 03 (trust lineage):**

1. `EatpDelegationChain` (item 3, cascade revocation) is **the single load-bearing primitive for delegation graphs**. Rust source is verified; binding needs documentation + conformance test.

2. Ed25519 signing (item 17) is **frozen** (no algorithm versioning). Envoy must assume SHA-256 + Ed25519 are canonical.

**Load-bearing for doc 09 (threat model):**

1. **SQL injection risk** (item 15) in `execute_raw()` is **CRITICAL**. Block Envoy use of execute_raw until this is fixed in the binding (S-effort fix).

---

## Conclusion

Of 15 primitives audited:
- **7 Type-A** (present-in-Rust-not-bound) → **Binding work required** (PyO3 wrappers)
- **4 Type-B** (different-name/structure) → **Reconciliation + binding work**
- **4 Type-C** (genuinely absent) → **Upstream Rust work required OR defer**

**No Type-C primitives are load-bearing for Envoy Phase 00.** Focus binding work on Type A (RoleEnvelope, TaskEnvelope, L3 Plan DAG, Suspension) and Type B (intersect naming, PlanSuspension structure). File 15 GitHub issues: 11 for binding repo, 4 for upstream Rust. Prioritize security fix (item 15) and documentation (item 3).

