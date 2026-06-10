#!/usr/bin/env python3
"""
File 38 GitHub issues across 3 repos derived from Envoy's primitive reconciliation
(workspaces/phase-00-alignment/01-analysis/03-primitive-reconciliation.md).

Cross-files between terrene-foundation/kailash-py, esperie-enterprise/kailash-rs,
and terrene-foundation/mint per the Foundation parity posture stated in
`rules/independence.md` + the user's direct filing directive.

Output: workspaces/phase-00-alignment/issues/manifest.md (ISS-XX -> repo#N)
"""

import subprocess
from pathlib import Path
from textwrap import dedent

WORKSPACE = Path("/Users/esperie/repos/dev/envoy/workspaces/phase-00-alignment")
MANIFEST = WORKSPACE / "issues" / "manifest.md"

# Common footer for every issue body
FOOTER = dedent(
    """
    ---

    **Context:** This issue was filed by the Envoy (Terrene Foundation agent product) scope analysis.
    It implements the Foundation parity posture: gaps verified via deep audit on both SDK sides,
    then cross-filed on both implementations (and on `mint` when a spec change is involved).

    **Audit sources (tracked in Envoy repo):**
    - `workspaces/phase-00-alignment/01-analysis/01-kailash-rs-deep-audit.md` — Rust source audit (Envoy)
    - `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` — Python source audit (Envoy)
    - `workspaces/phase-00-alignment/01-analysis/03-primitive-reconciliation.md` — synthesis

    **Filed as part of:** Envoy Phase 00 alignment. Closure of this issue (or equivalent Envoy-scoped implementation) is a Phase 01 / Phase 02 gate per the analysis doc.
"""
).strip()


def body(sections: dict) -> str:
    out = []
    for h, c in sections.items():
        out.append(f"## {h}\n\n{c.strip()}\n")
    out.append(FOOTER)
    return "\n".join(out)


# ----- Issue definitions -----
ISSUES = [
    # ======== esperie-enterprise/kailash-rs (18 issues) ========
    dict(
        iss="ISS-01",
        repo="esperie-enterprise/kailash-rs",
        title="[binding] Expose `ConstraintEnvelope::intersect()` via PyO3 as `intersect_envelopes()`",
        labels=["binding", "pact", "phase-1-binding-repair"],
        body=body(
            {
                "Summary": "Expose the envelope-intersection primitive in the Python binding. Either as a module-level `intersect_envelopes()` function (matching the kailash-py idiom) or by surfacing `ConstraintEnvelope::intersect()` as a PyO3 method on the Python class.",
                "Rust source": (
                    "`crates/eatp/src/constraints/mod.rs:356–366`:\n\n"
                    "```rust\n"
                    "impl ConstraintEnvelope {\n"
                    "    pub fn intersect(&self, other: &Self) -> Self {\n"
                    "        // Intersect all 5 dimensions (financial, operational, temporal,\n"
                    "        // data_access, communication), taking the MIN of each constraint.\n"
                    "    }\n"
                    "}\n"
                    "```\n\n"
                    "`PactGovernanceEngine` does NOT enumerate `intersect_envelopes()` in its public surface today; the binding survey flagged this as unconfirmed."
                ),
                "Proposed change": (
                    "- Add `#[pymethods] impl PyConstraintEnvelope { fn intersect(&self, other: &Self) -> Self { ... } }` (or equivalent).\n"
                    "- Add module-level `pact.intersect_envelopes(a, b) -> ConstraintEnvelope` that accepts `RoleEnvelope`/`TaskEnvelope` (see sibling issue for type exposure) and returns the effective envelope.\n"
                    "- Update `.pyi` stubs."
                ),
                "Phase impact": "Envoy Phase 01 uses `kailash-py` which has a functional `intersect_envelopes()` — this issue is not a Phase 01 blocker. For Phase 02 cross-runtime parity, binding exposure IS required.",
                "Cross-files": "Sibling: `terrene-foundation/kailash-py` (confirm semantic parity).",
            }
        ),
    ),
    dict(
        iss="ISS-03",
        repo="esperie-enterprise/kailash-rs",
        title="[binding] Expose `RoleEnvelope` and `TaskEnvelope` types for PACT governance queries",
        labels=["binding", "pact"],
        body=body(
            {
                "Summary": "PACT's `RoleEnvelope` and `TaskEnvelope` structs are fully functional in Rust at `crates/kailash-governance/src/envelopes.rs:186–237` but NOT exposed in the Python binding. Also expose `EffectiveEnvelopeSnapshot` (result of intersection).",
                "Rust source": (
                    "```rust\n"
                    "pub struct RoleEnvelope {\n"
                    "    pub role_address: Address,\n"
                    "    pub envelope: ConstraintEnvelope,\n"
                    "    pub set_by: Address,\n"
                    "    pub version: u64,\n"
                    "    pub created_at: DateTime<Utc>,\n"
                    "    pub modified_at: DateTime<Utc>,\n"
                    "    pub allow_bridge: bool,\n"
                    "}\n\n"
                    "pub struct TaskEnvelope {\n"
                    "    pub task_id: String,\n"
                    "    pub role_address: Address,\n"
                    "    pub envelope: ConstraintEnvelope,\n"
                    "    pub expires_at: DateTime<Utc>,\n"
                    "    pub created_by: Address,\n"
                    "}\n"
                    "```"
                ),
                "Proposed change": "PyO3 `#[pyclass]` wrappers for both types + `EffectiveEnvelopeSnapshot`. Expose all fields via `#[getter]`. Update `.pyi`.",
                "Phase impact": "Phase 02 cross-runtime parity for PACT envelope queries. Envoy Phase 01 uses kailash-py directly.",
                "Cross-files": "Sibling: `terrene-foundation/kailash-py` confirm types match.",
            }
        ),
    ),
    dict(
        iss="ISS-04",
        repo="esperie-enterprise/kailash-rs",
        title="[binding] Document cascade revocation + expose explicit cascade API on `EatpDelegationChain.revoke()`",
        labels=["binding", "eatp", "docs"],
        body=body(
            {
                "Summary": (
                    "`DelegationChain::revoke()` at `crates/eatp/src/delegation.rs:807–844` already implements cascade revocation via recursive `cascade_revoke()` that walks `parent_delegation_id` links. The behavior is deterministic but undocumented. The Python binding surfaces `revoke()` without naming the cascade semantics."
                ),
                "Rust source": (
                    "```rust\n"
                    "pub fn revoke(&mut self, delegation_id: Uuid) -> Result<Vec<Uuid>, EatpError> {\n"
                    "    // ... walks parent_delegation_id recursively, returns all revoked ids\n"
                    "    self.cascade_revoke(delegation_id, &mut revoked_ids);\n"
                    "    Ok(revoked_ids)\n"
                    "}\n"
                    "```"
                ),
                "Proposed change": (
                    "1. Comprehensive docstring on `revoke()` explaining cascade walk (parent_delegation_id DFS).\n"
                    "2. Return value documentation: `Vec<Uuid>` = all revoked IDs including descendants.\n"
                    "3. Optional explicit API: `revoke_cascade(uuid) -> Vec<Uuid>` as an alias that makes the cascade behavior unmistakable.\n"
                    "4. Conformance test demonstrating multi-level revocation (3+ levels deep).\n"
                    "5. Reference EATP D3 cascade semantics."
                ),
                "Phase impact": "Load-bearing for Envoy doc 03 (trust lineage) and Envoy capability #8 (cascade revocation) in Phase 01.",
                "Cross-files": "Sibling: `terrene-foundation/kailash-py` — verify kailash-py's `src/kailash/trust/revocation/cascade.py` BFS implementation matches Rust DFS semantically.",
            }
        ),
    ),
    dict(
        iss="ISS-08",
        repo="esperie-enterprise/kailash-rs",
        title="[new-primitive] Implement `TieredAuditDispatcher` for hash-chained tier-based audit retention",
        labels=["eatp", "enterprise", "new-primitive"],
        body=body(
            {
                "Summary": (
                    "Envoy's Ledger primitive (hash-chained, tier-routed, SIEM-exportable audit stream) requires a `TieredAuditDispatcher`. The current Rust surface has `AuditLogger` (Enterprise) and `eatp::audit::{AuditEvent, AuditFilter}` but NO tiered-dispatch primitive. Both SDK sides lack this."
                ),
                "Proposed design (seed — spec finalization at mint ISS-06)": (
                    "- Trait `AuditDispatcher` with methods `dispatch(event, tier)`, `rotate(tier)`, `seal(tier)`.\n"
                    "- `TieredAuditDispatcher` routes events into hash-chained anchors per tier with per-tier retention policy.\n"
                    "- SIEM export adapter via `AuditStore` trait (compose, don't couple).\n"
                    "- Conformance test vectors for hash-chain validity + tier isolation."
                ),
                "Phase impact": "Load-bearing for Envoy doc 04 (ledger and audit). Without it, Envoy implements the dispatcher locally and cross-files for upstream adoption.",
                "Cross-files": (
                    "- **Spec (design first):** `terrene-foundation/mint` — see ISS-06 filed concurrently.\n"
                    "- **Python sibling:** `terrene-foundation/kailash-py` — see ISS-07 filed concurrently."
                ),
            }
        ),
    ),
    dict(
        iss="ISS-09",
        repo="esperie-enterprise/kailash-rs",
        title="[new-primitive] Implement `PostureStore`/`SQLitePostureStore`/`PostureEvidence` for persistent posture tracking",
        labels=["eatp", "new-primitive"],
        body=body(
            {
                "Summary": (
                    "Rust has `PostureLevel` enum + `PostureSystem` state machine but NO persistence layer. `kailash-py` ships `src/kailash/trust/posture/` (`PostureStore` + `SQLitePostureStore` + `PostureEvidence`). Rust needs the same to maintain cross-SDK parity."
                ),
                "Rust source — what exists": (
                    "- `eatp::types::PostureLevel` — enum (Pseudo/Tool/Supervised/Delegating/Autonomous)\n"
                    "- `eatp::posture::PostureSystem` — in-memory state machine\n"
                    "- `kailash_kaizen::types::AgentPosture` — parallel posture enum\n\n"
                    "Missing: persistent store with evidence capture."
                ),
                "Proposed design (seed — spec formalization at mint ISS-10)": (
                    "- `PostureStore` trait with `put(principal, posture, evidence)` / `get(principal)` / `history(principal, window)`.\n"
                    "- `SQLitePostureStore` backend.\n"
                    "- `PostureEvidence` struct with `(reason, delegation_record_id, timestamp, hash_anchor)`.\n"
                    "- Integration with `EatpTrustOperations` for audit trail."
                ),
                "Phase impact": "Phase 03 per-dimension posture slider (5 postures × 5 constraint dimensions) requires persistent per-principal per-dimension state. Phase 01 uses kailash-py directly.",
                "Cross-files": "Spec: `terrene-foundation/mint` ISS-10 (already Python-functional; needs spec formalization).",
            }
        ),
    ),
    dict(
        iss="ISS-11",
        repo="esperie-enterprise/kailash-rs",
        title="[binding] Add missing Phase-13 type stubs to `kailash.pyi` + expose via PyO3",
        labels=["binding", ".pyi"],
        body=body(
            {
                "Summary": "BINDING-AUDIT B1 found `.pyi` missing 8 Phase-13 types. Enumerate + add wrappers + regen stubs.",
                "Details": (
                    "Types suspected missing (verify during implementation):\n"
                    "- `EatpPosture` (alias or distinct from `PostureLevel`?)\n"
                    "- `VerificationConfig`\n"
                    "- Constraint-related types from eatp\n"
                    "- Gradient / verdict types from PACT\n"
                    "- Envelope types from kailash-governance (see ISS-03)"
                ),
                "Proposed change": "1. Enumerate ALL Phase-13 types in Rust source. 2. For each: `#[pyclass]` wrapper + `#[pymethods]`. 3. Run `pyo3-stub-gen` or hand-sync `.pyi`.",
                "Phase impact": "Phase 01 IDE/typing quality; phase-13 types relate to v3.X posture + verification work.",
                "Cross-files": "Sibling: `terrene-foundation/kailash-py` ISS-12 — confirm Phase-13 bundle completeness on Python side.",
            }
        ),
    ),
    dict(
        iss="ISS-14",
        repo="esperie-enterprise/kailash-rs",
        title="[binding] Expose `SuspensionReason` + `SuspensionRecord` + `Plan.suspension` for L3 plan control",
        labels=["binding", "kaizen", "l3"],
        body=body(
            {
                "Summary": "L3 Plan DAG has full suspension support in Rust (`crates/kailash-kaizen/src/l3/core/plan/types.rs:267–340`) — 5 reason variants (HumanApprovalGate/CircuitBreakerTripped/BudgetExceeded/EnvelopeViolation/ExplicitCancellation). Not bound.",
                "Rust source": (
                    "```rust\n"
                    "pub enum SuspensionReason {\n"
                    "    HumanApprovalGate { held_node: PlanNodeId, reason: String },\n"
                    "    CircuitBreakerTripped { trigger: String, cool_down_secs: u64 },\n"
                    "    BudgetExceeded { dimension: String, threshold_pct: u32 },\n"
                    "    EnvelopeViolation { dimension: String, detail: String },\n"
                    "    ExplicitCancellation { resume_hint: Option<String> },\n"
                    "}\n"
                    "pub struct SuspensionRecord {\n"
                    "    pub reason: SuspensionReason,\n"
                    "    pub suspended_at: DateTime<Utc>,\n"
                    "    pub suspended_node_id: PlanNodeId,\n"
                    "    pub context: serde_json::Value,\n"
                    "}\n"
                    "```"
                ),
                "Proposed change": "PyO3 enum wrapper for `SuspensionReason`; `#[pyclass]` for `SuspensionRecord`; expose `Plan.suspension -> Option[SuspensionRecord]`.",
                "Phase impact": "Load-bearing for Envoy Grant Moment semantics — a pending Grant Moment is structurally a `HumanApprovalGate` suspension.",
                "Cross-files": "Sibling: `terrene-foundation/kailash-py` ISS-13 — implement on Python side (absent there).",
            }
        ),
    ),
    dict(
        iss="ISS-15",
        repo="esperie-enterprise/kailash-rs",
        title="[binding] Verify complete L3 Plan DAG `.pyi` coverage (PlanEdge, EdgeType, PlanEvent)",
        labels=["binding", "kaizen", "l3", ".pyi"],
        body=body(
            {
                "Summary": "Verify all L3 Plan DAG types are exposed: `PlanEdge` (from/to/edge_type), `EdgeType` enum (DataDependency/CompletionDependency/CoStart), `PlanEvent` variants (NodeReady/NodeStarted/NodeCompleted/NodeFailed/NodeHeld/etc), `PlanState`, `PlanNodeState`.",
                "Rust source": "`crates/kailash-kaizen/src/l3/core/plan/types.rs:1–250`",
                "Proposed change": "Audit binding coverage; add missing `#[pyclass]` wrappers; regen `.pyi`; document Plan state machine lifecycle in docstrings.",
                "Phase impact": "Phase 02 (runtime pluggability).",
                "Cross-files": "Sibling kailash-py surface already green (item 8 in audit); no cross-issue needed.",
            }
        ),
    ),
    dict(
        iss="ISS-16",
        repo="esperie-enterprise/kailash-rs",
        title="[binding] Expose complete `LlmDeployment` surface (4-axis abstraction + 18 presets)",
        labels=["binding", "kaizen", "llm"],
        body=body(
            {
                "Summary": "Rust side has `LlmDeployment` 4-axis (wire × auth × endpoint × model_grammar) with 18 presets. Full surface not exposed in Python binding.",
                "Proposed change": "PyO3 wrappers for `LlmDeployment`, preset factories, env-auto-detect logic. Include SSRF/DNS defense behavior.",
                "Phase impact": "Phase 02 model picker cross-runtime parity.",
                "Cross-files": "Sibling: `terrene-foundation/kailash-py` (Ollama/Claude/GPT/DeepSeek providers exist but `LlmDeployment` 4-axis abstraction surface parity pending).",
            }
        ),
    ),
    dict(
        iss="ISS-18",
        repo="esperie-enterprise/kailash-rs",
        title="[new-primitive] Design `McpGovernanceEnforcer` / `McpGovernanceMiddleware` (PACT-constrained MCP)",
        labels=["new-primitive", "pact", "mcp"],
        body=body(
            {
                "Summary": "Both SDKs lack PACT-enforced MCP middleware. Absent in kailash-pact and kailash-mcp.",
                "Proposed design (seed — spec at mint ISS-17)": (
                    "- `McpGovernanceMiddleware` intercepts tool invocation, evaluates PACT envelope (`RoleEnvelope` + `TaskEnvelope`), returns allow/deny/flag.\n"
                    "- `McpGovernanceEnforcer` composes with `McpServer` to apply middleware to every tool-call.\n"
                    "- Integrates with `PactGovernanceEngine.evaluate()`."
                ),
                "Phase impact": "Phase 02 SKILL.md CO validator runtime enforcement relies on this.",
                "Cross-files": "Spec: `terrene-foundation/mint` ISS-17. Sibling: `terrene-foundation/kailash-py` ISS-19.",
            }
        ),
    ),
    dict(
        iss="ISS-20",
        repo="esperie-enterprise/kailash-rs",
        title="[binding] MCP transport bindings (stdio / SSE / HTTP) for Python-side MCP client/server",
        labels=["binding", "mcp", "transport"],
        body=body(
            {
                "Summary": "BINDING-AUDIT C4: stdio/SSE/HTTP MCP transports not bound from Python. Rust has `kailash-mcp::primitives` + `kailash-nexus::mcp::McpServer` (axum) but no exposed transport abstraction.",
                "Proposed change": "Transport trait in `kailash-mcp` (if not present); PyO3 wrappers for stdio/SSE/HTTP clients; usable from Python.",
                "Phase impact": "Phase 02 MCP-server and client work requires transports.",
                "Cross-files": "Sibling: `terrene-foundation/kailash-py` ISS-21.",
            }
        ),
    ),
    dict(
        iss="ISS-24",
        repo="esperie-enterprise/kailash-rs",
        title="[binding] Expose `apply_read_classification()` + event-payload helper for DataFlow",
        labels=["binding", "dataflow", "classification"],
        body=body(
            {
                "Summary": "`apply_read_classification()` exists in Rust at `crates/kailash-dataflow/src/classification.rs:76–98` but is not exposed via PyO3. `format_record_id_for_event()` is a Python idiom — verify whether an equivalent event-payload helper should land on the Rust side.",
                "Rust source": (
                    "```rust\n"
                    "pub fn apply_read_classification(\n"
                    "    value: &Value,\n"
                    "    field_classification: DataClassification,\n"
                    "    caller_clearance: DataClassification,\n"
                    ") -> Value { ... }\n"
                    "```"
                ),
                "Proposed change": (
                    "1. PyO3 wrapper for `apply_read_classification()` accepting + returning JSON-serializable Value.\n"
                    "2. Decide on `format_record_id_for_event()` — port from kailash-py or close as Python-only helper.\n"
                    "3. Document masking strategies."
                ),
                "Phase impact": "Phase 02 cross-runtime parity for DataFlow classification.",
                "Cross-files": "Sibling: `terrene-foundation/kailash-py` ISS-23.",
            }
        ),
    ),
    dict(
        iss="ISS-25",
        repo="esperie-enterprise/kailash-rs",
        title="[binding] Replace `BaseAgent.execute()` stub with trait-based agent composition",
        labels=["binding", "kaizen", "agents"],
        body=body(
            {
                "Summary": "BINDING-AUDIT B1: `BaseAgent.execute()` raises `NotImplementedError`; 3/7 pre-built agents crash. Rust side uses trait composition (`Agent` trait) — no `BaseAgent` class. The binding's stub is a design mismatch.",
                "Proposed change": (
                    "1. Replace `BaseAgent.execute()` stub with factory functions returning `WorkerAgent` or `SupervisorAgent`.\n"
                    "2. Or expose `Agent` trait as a Python protocol.\n"
                    "3. Fix the 3 pre-built agents that currently crash."
                ),
                "Phase impact": "Envoy's Boundary Conversation agent SHOULD use kailash-py directly (functional there). Rust binding is not blocked but the agent layer needs redesign for Phase 02 parity.",
                "Cross-files": "Not needed on kailash-py — functional there.",
            }
        ),
    ),
    dict(
        iss="ISS-27",
        repo="esperie-enterprise/kailash-rs",
        title="[binding] Implement `OrchestrationRuntime.run()` — currently returns static stub",
        labels=["binding", "kaizen", "orchestration"],
        body=body(
            {
                "Summary": 'BINDING-AUDIT B3: `.run()` returns `{"agents": {"name": "configured"}}` stub. Rust side has full `OrchestrationEngine` at `crates/kaizen-agents/src/orchestration/`.',
                "Proposed change": "Connect Python `.run()` to Rust engine via pyo3-asyncio bridge. Implement agent lifecycle, scheduling, state transitions.",
                "Phase impact": "Phase 03 scheduled rituals (Weekly Posture Review, Monthly Trust Report). Phase 01 can use kailash-py directly.",
                "Cross-files": "Sibling: `terrene-foundation/kailash-py` ISS-26.",
            }
        ),
    ),
    dict(
        iss="ISS-28",
        repo="esperie-enterprise/kailash-rs",
        title="[binding] Implement `A2AProtocol.send_message()` + `receive_message()` in PyO3 binding",
        labels=["binding", "kaizen", "a2a"],
        body=body(
            {
                "Summary": "BINDING-AUDIT C6: methods declared in `.pyi` but PyO3 binding does not implement them. Rust has `A2AMessage` + `InMemoryMessageBus` at `crates/kailash-kaizen/src/a2a/messaging.rs`.",
                "Proposed change": "Add PyO3 methods to `PyA2AProtocol` for send/receive. Bridge async to Python via pyo3-asyncio.",
                "Phase impact": "Phase 03 Shared Household (multi-principal A2A coordination).",
                "Cross-files": "Not needed on kailash-py — functional at `src/kailash/trust/a2a/service.py`.",
            }
        ),
    ),
    dict(
        iss="ISS-30",
        repo="esperie-enterprise/kailash-rs",
        title="[binding] Expose `BudgetTracker` threshold-callback API",
        labels=["binding", "kaizen", "budget"],
        body=body(
            {
                "Summary": "Rust `BudgetTracker` at `crates/kailash-kaizen/src/cost/budget.rs:80–160` does not expose a threshold-callback hook. The tracker is passive; thresholds are checked by caller. The binding needs a notification hook for Envoy's budget-breach Grant Moment.",
                "Proposed change": "Add `set_threshold_callback(threshold_pct, callback)` API to BudgetTracker; invoke when `(committed + reserved) / allocated >= threshold`. PyO3 exposure.",
                "Phase impact": "Envoy doc 01 Grant Moment triggering.",
                "Cross-files": "Sibling: `terrene-foundation/kailash-py` ISS-29.",
            }
        ),
    ),
    dict(
        iss="ISS-33",
        repo="esperie-enterprise/kailash-rs",
        title="[new-primitive] Algorithm-identifier schema + versioned signed-artifact format",
        labels=["new-primitive", "eatp", "crypto"],
        body=body(
            {
                "Summary": "EATP signed records hard-code Ed25519 + SHA-256 (`crates/eatp/src/canonical.rs` + `kailash-audit-vectors`). No versioned algorithm tag in wire format. Algorithm swap requires breaking change.",
                "Rationale": "Envoy CHARTER §4.1 item 9 claim: 'Envoy does not lock in a crypto algorithm ... If NIST deprecates SHA-256 tomorrow, we migrate; legacy records remain verifiable under their original algorithm tag.' Requires implementation.",
                "Proposed design (seed — spec at mint ISS-31)": (
                    "- `AlgorithmIdentifier` enum tagging signing/hashing/Shamir schemes per signed record.\n"
                    "- Canonical format includes `alg_id` field in every signed artifact.\n"
                    "- Legacy-verification resolver dispatches on `alg_id`.\n"
                    "- Conformance vectors for mixed-algorithm chains."
                ),
                "Phase impact": "Phase 01 exit criterion (§4.1 item 9 load-bearing).",
                "Cross-files": "Spec: `terrene-foundation/mint` ISS-31. Sibling: `terrene-foundation/kailash-py` ISS-32.",
            }
        ),
    ),
    dict(
        iss="ISS-35",
        repo="esperie-enterprise/kailash-rs",
        title="SECURITY: Fix `DataFlow.execute_raw()` param-drop (SQL injection surface)",
        labels=["security", "binding", "dataflow", "CRITICAL"],
        body=body(
            {
                "Summary": "BINDING-AUDIT H4: The Python binding's compat layer for `DataFlow.execute_raw()` silently drops `params` instead of forwarding them to Rust. User-supplied values flow into SQL via string interpolation. **Active SQL injection surface.**",
                "Rust source": "`crates/kailash-dataflow/src/` accepts `execute_raw(sql: &str, params: &[Value])`. Binding at `bindings/kailash-python/src/dataflow/` drops params in the compat layer.",
                "Proposed change": (
                    "1. Remove the param-drop in compat layer.\n"
                    "2. Forward params to Rust `execute_raw()`.\n"
                    "3. Add regression test with known-injection payload (`'; DROP TABLE...`) asserting param is parameterized, not interpolated.\n"
                    "4. Verify the regression across PostgreSQL + SQLite + MySQL adapters."
                ),
                "Severity": "CRITICAL. Envoy BLOCKS consumption of `kailash-rs-bindings` DataFlow `execute_raw` until this ships.",
                "Phase impact": "Phase 02 BLOCKER for any Envoy use of Rust-binding DataFlow raw SQL.",
                "Cross-files": "Sibling: verify kailash-py side does not carry the same bug (audit indicates it does NOT).",
            }
        ),
    ),
    dict(
        iss="ISS-38",
        repo="esperie-enterprise/kailash-rs",
        title="[binding] `.pyi` type stub regeneration (~55% accurate → target ≥95%)",
        labels=["binding", ".pyi"],
        body=body(
            {
                "Summary": "BINDING-AUDIT B2: `.pyi` stubs are ~55% accurate, 26 inaccuracies, 8 types missing. Dev experience suffers — IDE completion is unreliable, type checkers trust stubs over reality.",
                "Known issues (non-exhaustive)": (
                    "- `AgentCheckpoint` ctor wrong (`.pyi` says `agent_id + step`; actual is `agent_name + model + stored_step`).\n"
                    "- `SessionMemory` / `SharedMemory` methods wrong (`.pyi` says `set/get/delete`; actual is `store/recall/remove`).\n"
                    "- `A2AProtocol.send_message` / `receive_message` declared but not implemented (see ISS-28).\n"
                    "- `FilterCondition` missing 5 methods (gt/gte/lt/lte/in_list — see related issue).\n"
                    "- `DataFlow` missing 7 methods (health_check/is_connected/pool_status/transaction/transaction_with_tenant/register_nodes/create_tables).\n"
                    "- `QueryInterceptor` signature wrong (`.pyi` `(tenant_column)`; actual `(TenantContext)`)."
                ),
                "Proposed change": "Use `pyo3-stub-gen` (or hand-sync); run in CI to prevent regression; gate release on stub accuracy.",
                "Phase impact": "Dev velocity + correctness across Phase 02+.",
                "Cross-files": "Not applicable on kailash-py (pure Python, no .pyi).",
            }
        ),
    ),
    # ======== terrene-foundation/kailash-py (13 issues) ========
    dict(
        iss="ISS-02",
        repo="terrene-foundation/kailash-py",
        title="[parity] Confirm semantic parity of `intersect_envelopes()` with Rust `ConstraintEnvelope::intersect()`",
        labels=["parity", "pact"],
        body=body(
            {
                "Summary": "kailash-py exposes `intersect_envelopes()` at `src/kailash/trust/pact/envelopes.py`; Rust has `ConstraintEnvelope::intersect()` at `crates/eatp/src/constraints/mod.rs:356`. Confirm byte-for-byte semantic parity across 5 constraint dimensions (Financial / Operational / Temporal / Data Access / Communication).",
                "Proposed change": "Cross-SDK test fixture: identical EnvelopeConfig on both sides, assert intersect() output byte-identical after canonical serialization.",
                "Phase impact": "Phase 02 cross-runtime parity (BET-6 contract-parity in Envoy doc 00).",
                "Cross-files": "Sibling: `esperie-enterprise/kailash-rs` ISS-01.",
            }
        ),
    ),
    dict(
        iss="ISS-05",
        repo="terrene-foundation/kailash-py",
        title="[docs] Cascade revocation docstring cross-reference with Rust DFS semantics",
        labels=["docs", "eatp", "revocation"],
        body=body(
            {
                "Summary": "kailash-py implements cascade revocation at `src/kailash/trust/revocation/cascade.py` using BFS. Rust implements at `crates/eatp/src/delegation.rs:807` using DFS recursion. Confirm semantics are identical regardless of traversal order.",
                "Proposed change": "Docstring + test: identical delegation tree on both sides, revoke same node, assert identical set of revoked descendants.",
                "Phase impact": "Phase 01 load-bearing (Envoy capability #8).",
                "Cross-files": "Sibling: `esperie-enterprise/kailash-rs` ISS-04.",
            }
        ),
    ),
    dict(
        iss="ISS-07",
        repo="terrene-foundation/kailash-py",
        title="[new-primitive] Implement `TieredAuditDispatcher` for hash-chained tier-based audit retention",
        labels=["eatp", "new-primitive"],
        body=body(
            {
                "Summary": "kailash-py has `AuditLogger` but no tiered-dispatch primitive. Both SDK sides lack this. Implementation gated on mint spec (ISS-06).",
                "Proposed design": "See ISS-06 on mint for spec seed. Python implementation once spec finalizes.",
                "Phase impact": "Load-bearing for Envoy doc 04 (ledger and audit).",
                "Cross-files": "Spec: `terrene-foundation/mint` ISS-06. Rust sibling: `esperie-enterprise/kailash-rs` ISS-08.",
            }
        ),
    ),
    dict(
        iss="ISS-12",
        repo="terrene-foundation/kailash-py",
        title="[parity] Confirm Phase-13 posture/verification type bundle completeness",
        labels=["parity", "eatp"],
        body=body(
            {
                "Summary": "Rust binding is missing 8 Phase-13 types in its `.pyi`. Verify kailash-py has a parallel bundle present and exported.",
                "Proposed change": "Enumerate Phase-13 types (EatpPosture/VerificationConfig/related); confirm kailash-py exports match; publish type-mapping table as cross-SDK reference.",
                "Phase impact": "Phase 03 posture per-dimension + verification work.",
                "Cross-files": "Sibling: `esperie-enterprise/kailash-rs` ISS-11.",
            }
        ),
    ),
    dict(
        iss="ISS-13",
        repo="terrene-foundation/kailash-py",
        title="[parity] Implement `PlanSuspension` (Rust has `SuspensionReason` + `SuspensionRecord`)",
        labels=["parity", "kaizen", "l3"],
        body=body(
            {
                "Summary": "Rust has 5-variant `SuspensionReason` enum + `SuspensionRecord` + `Plan.suspension` at `crates/kailash-kaizen/src/l3/core/plan/types.rs:267–340`. kailash-py L3 executor lacks this.",
                "Proposed change": (
                    "1. Implement `SuspensionReason` (HumanApprovalGate/CircuitBreakerTripped/BudgetExceeded/EnvelopeViolation/ExplicitCancellation).\n"
                    "2. Implement `SuspensionRecord` + `Plan.suspension: Optional[SuspensionRecord]`.\n"
                    "3. Update L3 executor to emit suspensions on trigger conditions.\n"
                    "4. Conformance parity with Rust."
                ),
                "Phase impact": "Phase 01 load-bearing (Envoy Grant Moment is structurally a `HumanApprovalGate`).",
                "Cross-files": "Sibling: `esperie-enterprise/kailash-rs` ISS-14.",
            }
        ),
    ),
    dict(
        iss="ISS-19",
        repo="terrene-foundation/kailash-py",
        title="[new-primitive] Design `McpGovernanceEnforcer` / `McpGovernanceMiddleware`",
        labels=["new-primitive", "pact", "mcp"],
        body=body(
            {
                "Summary": "Both SDKs lack PACT-enforced MCP middleware. Implementation gated on mint spec (ISS-17).",
                "Proposed design": "See ISS-17 on mint. Python implementation once spec finalizes.",
                "Phase impact": "Phase 02 SKILL.md CO validator runtime enforcement.",
                "Cross-files": "Spec: `terrene-foundation/mint` ISS-17. Rust sibling: `esperie-enterprise/kailash-rs` ISS-18.",
            }
        ),
    ),
    dict(
        iss="ISS-21",
        repo="terrene-foundation/kailash-py",
        title="[parity] MCP transport primitives (stdio / SSE / HTTP)",
        labels=["parity", "mcp", "transport"],
        body=body(
            {
                "Summary": "kailash-py has `src/kailash/channels/MCPChannel` but not full stdio/SSE/HTTP transport abstractions. Rust binding also missing (C4).",
                "Proposed change": "Implement stdio/SSE/HTTP transport primitives. Align API with Rust counterpart (ISS-20).",
                "Phase impact": "Phase 02.",
                "Cross-files": "Sibling: `esperie-enterprise/kailash-rs` ISS-20. Spec: `terrene-foundation/mint` ISS-22 (if protocol spec needs extension).",
            }
        ),
    ),
    dict(
        iss="ISS-23",
        repo="terrene-foundation/kailash-py",
        title="[api] Expose `apply_read_classification()` + `format_record_id_for_event()` on public API",
        labels=["api", "dataflow", "classification"],
        body=body(
            {
                "Summary": "kailash-py has `apply_read_classification()` internally at `packages/kailash-dataflow/src/dataflow/classification/` but not on public API surface. `format_record_id_for_event()` exists as internal helper.",
                "Proposed change": "Export both from the top-level `dataflow.classification` module. Document contract. Add cross-SDK conformance tests (see ISS-24).",
                "Phase impact": "Phase 02 cross-runtime parity for DataFlow classification.",
                "Cross-files": "Sibling: `esperie-enterprise/kailash-rs` ISS-24.",
            }
        ),
    ),
    dict(
        iss="ISS-26",
        repo="terrene-foundation/kailash-py",
        title="[parity] Implement `OrchestrationRuntime` class + `.run()` method",
        labels=["parity", "kaizen", "orchestration"],
        body=body(
            {
                "Summary": "kailash-py has Kaizen orchestration primitives but not a class named `OrchestrationRuntime` with a `.run()` method matching the Rust-side shape. Create the API alignment for cross-SDK parity.",
                "Proposed change": "Implement `OrchestrationRuntime(strategy, coordinator).run(input)`; align with Rust-side `OrchestrationEngine` at `crates/kaizen-agents/src/orchestration/`.",
                "Phase impact": "Phase 03 scheduled rituals.",
                "Cross-files": "Sibling: `esperie-enterprise/kailash-rs` ISS-27.",
            }
        ),
    ),
    dict(
        iss="ISS-29",
        repo="terrene-foundation/kailash-py",
        title="[api] BudgetTracker threshold-callback API",
        labels=["api", "kaizen", "budget"],
        body=body(
            {
                "Summary": "`BudgetTracker` is passive — no threshold-breach callback hook. Envoy requires notification to trigger a Grant Moment when spend crosses a threshold.",
                "Proposed change": "`set_threshold_callback(threshold_pct, callback)`; invoke when committed+reserved/allocated crosses threshold.",
                "Phase impact": "Phase 01 (Envoy Grant Moment triggering).",
                "Cross-files": "Sibling: `esperie-enterprise/kailash-rs` ISS-30.",
            }
        ),
    ),
    dict(
        iss="ISS-32",
        repo="terrene-foundation/kailash-py",
        title="[new-primitive] Algorithm-identifier schema implementation",
        labels=["new-primitive", "eatp", "crypto"],
        body=body(
            {
                "Summary": "Implementation side of mint spec ISS-31. EATP signed records currently hard-code Ed25519 + SHA-256; Envoy charter requires algorithm-agility. Implement versioned `AlgorithmIdentifier` tags in canonical form, legacy-verification resolver.",
                "Proposed change": "Add `alg_id` field to every signed record. Implement resolver. Mixed-algorithm-chain conformance tests. Align wire format with Rust (ISS-33) and spec (mint ISS-31).",
                "Phase impact": "Phase 01 exit criterion (Envoy §4.1 item 9).",
                "Cross-files": "Spec: `terrene-foundation/mint` ISS-31. Rust sibling: `esperie-enterprise/kailash-rs` ISS-33.",
            }
        ),
    ),
    dict(
        iss="ISS-36",
        repo="terrene-foundation/kailash-py",
        title="[HIGH — Phase 02 blocker] Implement PACT N4/N5 conformance vector Python runner",
        labels=["HIGH", "pact", "conformance"],
        body=body(
            {
                "Summary": "Rust side has `crates/kailash-pact/tests/conformance_vectors.rs` running PACT N4/N5 JSON vectors at `crates/kailash-pact/tests/conformance/vectors/*.json` with byte-for-byte canonical equality assertions. kailash-py has N6 tests but NO N4/N5 runner.",
                "Impact": "Without the Python runner, cross-SDK byte-identical contract-parity claims (BET-6 in Envoy doc 00) are structurally non-falsifiable. Any Foundation parity statement is unverified.",
                "Proposed change": (
                    "1. Implement loader for the same JSON vectors used by Rust side.\n"
                    "2. Reconstruct domain objects.\n"
                    "3. Assert canonical JSON byte-for-byte equality.\n"
                    "4. Wire into CI.\n"
                    "5. Cross-reference esperie-enterprise/kailash-rs#317."
                ),
                "Phase impact": "**Phase 02 BLOCKER for Envoy.** BET-6 (contract parity) non-falsifiable without this runner.",
                "Cross-files": "Existing cross-SDK follow-up: `esperie-enterprise/kailash-rs#317`.",
            }
        ),
    ),
    dict(
        iss="ISS-37",
        repo="terrene-foundation/kailash-py",
        title="[api] SLIP-0039 Shamir secret-sharing integration for Trust Vault backup",
        labels=["api", "eatp", "crypto", "shamir"],
        body=body(
            {
                "Summary": "Both SDKs lack SLIP-0039 Shamir support today. Envoy Phase 01 requires Shamir 3-of-5 default for Trust Vault backup. Implementation can pull audited library (`slip39` / `python-shamir-mnemonic`) but needs SDK-integrated ritual primitives (shard-generation, paper-print format, reconstruct, rotate).",
                "Proposed change": (
                    "1. Wrapper API over audited SLIP-0039 library.\n"
                    "2. Shamir ritual helpers: generate(m,n), serialize-to-wordlist, reconstruct-from-shards, rotate-shard-holders.\n"
                    "3. Trust Vault integration: vault-key → Shamir shards."
                ),
                "Phase impact": "Envoy Phase 01 exit criterion (§ROADMAP Phase 01 exit).",
                "Cross-files": "Spec: `terrene-foundation/mint` ISS-37 (Shamir ritual formalization).",
            }
        ),
    ),
    # ======== terrene-foundation/mint (7 issues) ========
    dict(
        iss="ISS-06",
        repo="terrene-foundation/mint",
        title="[new-spec] `TieredAuditDispatcher` — hash-chained tier-based audit retention",
        labels=["new-spec", "eatp"],
        body=body(
            {
                "Summary": "Formalize the `TieredAuditDispatcher` primitive Envoy requires for the Ledger surface. Neither kailash-py nor kailash-rs has this primitive.",
                "Proposed workspace": (
                    "- `workspaces/tiered-audit-dispatcher/` with brief, draft, conformance vectors.\n"
                    "- Finalize into `foundation/docs/02-standards/` once stabilized.\n"
                    "- Publish in `publications/`."
                ),
                "Scope seed": (
                    "- Trait `AuditDispatcher` with `dispatch/rotate/seal` lifecycle.\n"
                    "- Tier isolation (tiers cannot bleed into each other).\n"
                    "- Hash-chain integrity per tier + global anchor.\n"
                    "- Retention policy per tier.\n"
                    "- SIEM export adapter.\n"
                    "- Conformance vectors for hash-chain validity, tier isolation, retention semantics."
                ),
                "Phase impact": "Envoy Phase 01 Ledger depends on this. Interim: Envoy implements locally, cross-files upstream adoption.",
                "Cross-files": "Implementation: `terrene-foundation/kailash-py` ISS-07. Implementation: `esperie-enterprise/kailash-rs` ISS-08.",
            }
        ),
    ),
    dict(
        iss="ISS-10",
        repo="terrene-foundation/mint",
        title="[new-spec] `PostureStore` + `PostureEvidence` — persistent posture tracking primitive",
        labels=["new-spec", "eatp"],
        body=body(
            {
                "Summary": "Formalize the posture-persistence primitive. kailash-py ships `PostureStore` + `SQLitePostureStore` + `PostureEvidence` at `src/kailash/trust/posture/`. kailash-rs has only `PostureLevel` + `PostureSystem` state machine — no persistence. A mint spec is needed to codify the contract for cross-SDK parity.",
                "Scope seed": (
                    "- `PostureStore` trait — put(principal, posture, evidence) / get(principal) / history(principal, window).\n"
                    "- `PostureEvidence` — (reason, delegation_record_id, timestamp, hash_anchor).\n"
                    "- Integration with `EatpTrustOperations` for audit trail.\n"
                    "- Per-principal per-dimension support (5 postures × 5 constraint dimensions for Phase 03+)."
                ),
                "Phase impact": "Phase 03 per-dimension posture slider.",
                "Cross-files": "Rust implementation: `esperie-enterprise/kailash-rs` ISS-09. Python reference implementation exists; cross-file to align.",
            }
        ),
    ),
    dict(
        iss="ISS-17",
        repo="terrene-foundation/mint",
        title="[new-spec] `McpGovernanceEnforcer` / `McpGovernanceMiddleware` — PACT-constrained MCP tool invocation",
        labels=["new-spec", "pact", "mcp"],
        body=body(
            {
                "Summary": "Both SDKs lack this primitive. Formalize the spec for PACT-enforced MCP middleware that intercepts tool invocation and evaluates `RoleEnvelope` + `TaskEnvelope` constraints.",
                "Scope seed": (
                    "- Middleware contract — dispatch lifecycle, envelope lookup, evaluate via `PactGovernanceEngine`, return allow/deny/flag.\n"
                    "- Middleware composition with MCP server (axum / FastAPI / stdio transports).\n"
                    "- Performance target — O(1) envelope-membership checks, O(k) semantic checks (consistent with Envoy BET-2).\n"
                    "- Conformance vectors — malicious-skill / privilege-escalation scenarios blocked; benign scenarios allowed."
                ),
                "Phase impact": "Envoy Phase 02 skill runtime.",
                "Cross-files": "`terrene-foundation/kailash-py` ISS-19. `esperie-enterprise/kailash-rs` ISS-18.",
            }
        ),
    ),
    dict(
        iss="ISS-22",
        repo="terrene-foundation/mint",
        title="[spec-extension] MCP transport protocol extension (if current spec does not cover transports)",
        labels=["spec-extension", "mcp", "transport"],
        body=body(
            {
                "Summary": "Neither SDK exposes stdio/SSE/HTTP MCP transports (BINDING-AUDIT C4 on Rust side; kailash-py has `MCPChannel` but no full transport abstraction). If the current MCP spec in mint does not prescribe the transport surface, extend it.",
                "Scope seed": (
                    "- Transport trait surface.\n"
                    "- stdio (for CLI).\n"
                    "- SSE (for browser clients).\n"
                    "- HTTP (for REST clients).\n"
                    "- Integration points with MCP server/client.\n"
                    "- Conformance tests across transports."
                ),
                "Phase impact": "Phase 02 MCP work.",
                "Cross-files": "Implementations: ISS-20 (rs), ISS-21 (py).",
            }
        ),
    ),
    dict(
        iss="ISS-31",
        repo="terrene-foundation/mint",
        title="[new-spec] Algorithm-identifier versioning in EATP signed artifacts",
        labels=["new-spec", "eatp", "crypto"],
        body=body(
            {
                "Summary": "EATP signed records hard-code Ed25519 + SHA-256 (SLIP-0039 for Shamir) with no algorithm tag in wire format. Algorithm migration is a breaking change. Envoy §4.1 item 9 requires algorithm-agility with legacy-verification. Formalize the versioning scheme.",
                "Scope seed": (
                    "- `AlgorithmIdentifier` enum — Ed25519+SHA256 (v1); reserved encodings for future schemes.\n"
                    "- Canonical form — `alg_id` field appears FIRST in every signed record (determines parsing).\n"
                    "- Legacy-verification resolver dispatches on `alg_id`.\n"
                    "- Mixed-algorithm chains — a single Delegation Chain may contain records under different algorithms; `verify()` dispatches per record.\n"
                    "- Conformance vectors — round-trip sign/verify under each supported algorithm; legacy record remains verifiable after new algorithm lands."
                ),
                "Phase impact": "Envoy Phase 01 exit criterion. Without this, algorithm migration is structurally impossible.",
                "Cross-files": "Implementations: `terrene-foundation/kailash-py` ISS-32, `esperie-enterprise/kailash-rs` ISS-33.",
            }
        ),
    ),
    dict(
        iss="ISS-34",
        repo="terrene-foundation/mint",
        title="[new-spec] `ENVELOPE.md` schema + permission-to-PACT-dimension mapping for SKILL.md interop",
        labels=["new-spec", "pact", "skills"],
        body=body(
            {
                "Summary": "Envoy ingests external-ecosystem SKILL.md skills unchanged, then generates a companion ENVELOPE.md declaring the skill's permission needs in PACT terms. Formalize the ENVELOPE.md schema + the permission-to-PACT-dimension mapping (e.g. `bash:*` → Operational + Data Access constraints).",
                "Scope seed": (
                    "- ENVELOPE.md schema — sections for each PACT dimension, declared constraint types, per-skill metadata.\n"
                    "- Permission mapping table — external permission strings → PACT dimension + constraint shape.\n"
                    "- CO-compliance validator contract — install-time checks against the mapping.\n"
                    "- `force_install=True` UX contract — what the warning text says, what the Ledger records.\n"
                    "- Conformance vectors — sample SKILL.md files yielding known ENVELOPE.md outputs."
                ),
                "Phase impact": "Envoy Phase 02 SKILL.md ingest.",
                "Cross-files": "Implementation will live in Envoy repo + reference mint spec.",
            }
        ),
    ),
    dict(
        iss="ISS-37-mint",
        repo="terrene-foundation/mint",
        title="[new-spec] Shamir 3-of-5 recovery ritual — SLIP-0039 integration pattern for Trust Vault",
        labels=["new-spec", "eatp", "crypto", "shamir"],
        body=body(
            {
                "Summary": "Formalize the SLIP-0039 Shamir recovery ritual Envoy requires for Trust Vault backup. Both SDKs currently lack integrated Shamir primitives. The spec should cover ritual UX, paper-shard format, reconstruct flow, and shard-holder rotation for life-event changes.",
                "Scope seed": (
                    "- Default threshold — 3-of-5; configurable 2-of-3 to 5-of-9.\n"
                    "- Paper format — Trezor-compatible wordlist for interop.\n"
                    "- Ritual UX — shard generation, printed-card template, distribution guidance.\n"
                    "- Reconstruct flow — user collects k shards, enters words, vault unlocks.\n"
                    "- Shard-holder rotation — replace unreachable shard-holder without invalidating unrotated shards.\n"
                    "- Social-graph exposure caveat — shard-holders learn the user runs Envoy; document and mitigate."
                ),
                "Phase impact": "Envoy Phase 01 exit criterion (Shamir 3-of-5 default is a Phase 01 primitive).",
                "Cross-files": "Implementations: `terrene-foundation/kailash-py` ISS-37.",
            }
        ),
    ),
]


def run():
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# GitHub Issues Manifest — Envoy Phase 00 Filing",
        "",
        "**Filed:** 2026-04-21 (direct via `gh issue create`)",
        f"**Total:** {len(ISSUES)} issues across 3 repos",
        "",
        "| ISS | Repo | Number | Title |",
        "|---|---|---|---|",
    ]
    results = []
    for i, issue in enumerate(ISSUES, 1):
        print(f"[{i}/{len(ISSUES)}] Filing {issue['iss']} on {issue['repo']}...")
        cmd = [
            "gh",
            "issue",
            "create",
            "--repo",
            issue["repo"],
            "--title",
            issue["title"],
            "--body",
            issue["body"],
        ]
        for lab in issue.get("labels", []):
            cmd += ["--label", lab]
        try:
            res = subprocess.run(cmd, check=True, capture_output=True, text=True)
            url = res.stdout.strip().splitlines()[-1]
            # URL format: https://github.com/owner/repo/issues/NNN
            number = url.rsplit("/", 1)[-1]
            print(f"  -> {url}")
            lines.append(f"| {issue['iss']} | {issue['repo']} | #{number} | {issue['title']} |")
            results.append((issue["iss"], issue["repo"], number, url))
        except subprocess.CalledProcessError as e:
            err = (e.stderr or "").strip()
            print(f"  !! FAIL: {err[:200]}")
            # Try without labels in case of label not found
            if "label" in err.lower() or "could not add" in err.lower():
                cmd_nolabels = [
                    "gh",
                    "issue",
                    "create",
                    "--repo",
                    issue["repo"],
                    "--title",
                    issue["title"],
                    "--body",
                    issue["body"],
                ]
                try:
                    res = subprocess.run(cmd_nolabels, check=True, capture_output=True, text=True)
                    url = res.stdout.strip().splitlines()[-1]
                    number = url.rsplit("/", 1)[-1]
                    print(f"  -> (no labels) {url}")
                    lines.append(
                        f"| {issue['iss']} | {issue['repo']} | #{number} | {issue['title']} |"
                    )
                    results.append((issue["iss"], issue["repo"], number, url))
                    continue
                except subprocess.CalledProcessError as e2:
                    err2 = (e2.stderr or "").strip()
                    print(f"  !! RETRY FAIL: {err2[:200]}")
                    lines.append(f"| {issue['iss']} | {issue['repo']} | ERROR | {err2[:80]} |")
                    continue
            lines.append(f"| {issue['iss']} | {issue['repo']} | ERROR | {err[:80]} |")
    MANIFEST.write_text("\n".join(lines) + "\n")
    print(f"\nWrote manifest: {MANIFEST}")
    print(f"Success: {len(results)}/{len(ISSUES)}")


if __name__ == "__main__":
    run()
