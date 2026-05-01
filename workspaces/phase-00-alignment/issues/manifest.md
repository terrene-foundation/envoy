# GitHub Issues Manifest — Envoy Phase 00 Filing

**Filed:** 2026-04-21 (direct via `gh issue create`)
**Total:** 39 issues across 3 repos

| ISS | Repo | Number | Title |
|---|---|---|---|
| ISS-01 | esperie-enterprise/kailash-rs | #503 | [binding] Expose `ConstraintEnvelope::intersect()` via PyO3 as `intersect_envelopes()` |
| ISS-03 | esperie-enterprise/kailash-rs | #504 | [binding] Expose `RoleEnvelope` and `TaskEnvelope` types for PACT governance queries |
| ISS-04 | esperie-enterprise/kailash-rs | #505 | [binding] Document cascade revocation + expose explicit cascade API on `EatpDelegationChain.revoke()` |
| ISS-08 | esperie-enterprise/kailash-rs | #506 | [new-primitive] Implement `TieredAuditDispatcher` for hash-chained tier-based audit retention |
| ISS-09 | esperie-enterprise/kailash-rs | #507 | [new-primitive] Implement `PostureStore`/`SQLitePostureStore`/`PostureEvidence` for persistent posture tracking |
| ISS-11 | esperie-enterprise/kailash-rs | #508 | [binding] Add missing Phase-13 type stubs to `kailash.pyi` + expose via PyO3 |
| ISS-14 | esperie-enterprise/kailash-rs | #509 | [binding] Expose `SuspensionReason` + `SuspensionRecord` + `Plan.suspension` for L3 plan control |
| ISS-15 | esperie-enterprise/kailash-rs | #510 | [binding] Verify complete L3 Plan DAG `.pyi` coverage (PlanEdge, EdgeType, PlanEvent) |
| ISS-16 | esperie-enterprise/kailash-rs | #511 | [binding] Expose complete `LlmDeployment` surface (4-axis abstraction + 18 presets) |
| ISS-18 | esperie-enterprise/kailash-rs | #512 | [new-primitive] Design `McpGovernanceEnforcer` / `McpGovernanceMiddleware` (PACT-constrained MCP) |
| ISS-20 | esperie-enterprise/kailash-rs | #513 | [binding] MCP transport bindings (stdio / SSE / HTTP) for Python-side MCP client/server |
| ISS-24 | esperie-enterprise/kailash-rs | #514 | [binding] Expose `apply_read_classification()` + event-payload helper for DataFlow |
| ISS-25 | esperie-enterprise/kailash-rs | #515 | [binding] Replace `BaseAgent.execute()` stub with trait-based agent composition |
| ISS-27 | esperie-enterprise/kailash-rs | #516 | [binding] Implement `OrchestrationRuntime.run()` — currently returns static stub |
| ISS-28 | esperie-enterprise/kailash-rs | #517 | [binding] Implement `A2AProtocol.send_message()` + `receive_message()` in PyO3 binding |
| ISS-30 | esperie-enterprise/kailash-rs | #518 | [binding] Expose `BudgetTracker` threshold-callback API |
| ISS-33 | esperie-enterprise/kailash-rs | #519 | [new-primitive] Algorithm-identifier schema + versioned signed-artifact format |
| ISS-35 | esperie-enterprise/kailash-rs | #520 | SECURITY: Fix `DataFlow.execute_raw()` param-drop (SQL injection surface) |
| ISS-38 | esperie-enterprise/kailash-rs | #521 | [binding] `.pyi` type stub regeneration (~55% accurate → target ≥95%) |
| ISS-02 | terrene-foundation/kailash-py | #594 | [parity] Confirm semantic parity of `intersect_envelopes()` with Rust `ConstraintEnvelope::intersect()` |
| ISS-05 | terrene-foundation/kailash-py | #595 | [docs] Cascade revocation docstring cross-reference with Rust DFS semantics |
| ISS-07 | terrene-foundation/kailash-py | #596 | [new-primitive] Implement `TieredAuditDispatcher` for hash-chained tier-based audit retention |
| ISS-12 | terrene-foundation/kailash-py | #597 | [parity] Confirm Phase-13 posture/verification type bundle completeness |
| ISS-13 | terrene-foundation/kailash-py | #598 | [parity] Implement `PlanSuspension` (Rust has `SuspensionReason` + `SuspensionRecord`) |
| ISS-19 | terrene-foundation/kailash-py | #599 | [new-primitive] Design `McpGovernanceEnforcer` / `McpGovernanceMiddleware` |
| ISS-21 | terrene-foundation/kailash-py | #600 | [parity] MCP transport primitives (stdio / SSE / HTTP) |
| ISS-23 | terrene-foundation/kailash-py | #601 | [api] Expose `apply_read_classification()` + `format_record_id_for_event()` on public API |
| ISS-26 | terrene-foundation/kailash-py | #602 | [parity] Implement `OrchestrationRuntime` class + `.run()` method |
| ISS-29 | terrene-foundation/kailash-py | #603 | [api] BudgetTracker threshold-callback API |
| ISS-32 | terrene-foundation/kailash-py | #604 | [new-primitive] Algorithm-identifier schema implementation |
| ISS-36 | terrene-foundation/kailash-py | #605 | [HIGH — Phase 02 blocker] Implement PACT N4/N5 conformance vector Python runner |
| ISS-37 | terrene-foundation/kailash-py | #606 | [api] SLIP-0039 Shamir secret-sharing integration for Trust Vault backup |
| ISS-06 | terrene-foundation/mint | #2 | [new-spec] `TieredAuditDispatcher` — hash-chained tier-based audit retention |
| ISS-10 | terrene-foundation/mint | #3 | [new-spec] `PostureStore` + `PostureEvidence` — persistent posture tracking primitive |
| ISS-17 | terrene-foundation/mint | #4 | [new-spec] `McpGovernanceEnforcer` / `McpGovernanceMiddleware` — PACT-constrained MCP tool invocation |
| ISS-22 | terrene-foundation/mint | #5 | [spec-extension] MCP transport protocol extension (if current spec does not cover transports) |
| ISS-31 | terrene-foundation/mint | #6 | [new-spec] Algorithm-identifier versioning in EATP signed artifacts |
| ISS-34 | terrene-foundation/mint | #7 | [new-spec] `ENVELOPE.md` schema + permission-to-PACT-dimension mapping for SKILL.md interop |
| ISS-37-mint | terrene-foundation/mint | #8 | [new-spec] Shamir 3-of-5 recovery ritual — SLIP-0039 integration pattern for Trust Vault |
