# Round 1 Mechanical Sweep — Doc 00 Thesis and Scope

**Date:** 2026-04-21
**Scope:** Mechanical / parity-grep findings only. LLM-judgment and adversarial findings are in sibling files.
**Input:** `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` + `workspaces/internal/kailash-rs-survey-2026-04-21.md`.

## Summary

| ID   | Severity   | One-liner                                                                                                                                                                                                                                                                                     |
| ---- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M-01 | **HIGH**   | §3.3 names `cascade revocation` as a shipped primitive; kailash-rs binding survey says it is NOT exposed on the binding surface                                                                                                                                                               |
| M-02 | **HIGH**   | §3.3 names `@classify` / `apply_read_classification()` / `format_record_id_for_event()` — these are **kailash-py** patterns; NOT on the Rust-binding surface                                                                                                                                  |
| M-03 | **HIGH**   | §3.3 names `McpGovernanceEnforcer` / `McpGovernanceMiddleware` — NOT on the Rust-binding surface (MCP transports per se are also missing; BINDING-AUDIT C4)                                                                                                                                   |
| M-04 | **HIGH**   | §3.3 references `PostureStore` / `SQLitePostureStore` / `PostureEvidence` as shipped; kailash-rs Phase-13 types (including `EatpPosture`) are MISSING from the .pyi — binding surface may not expose them                                                                                     |
| M-05 | **HIGH**   | §3.3 names `PlanSuspension` as a Kaizen primitive; not in the surveyed binding surface                                                                                                                                                                                                        |
| M-06 | **HIGH**   | §3.3 names `intersect_envelopes()` as shipped; not confirmed on `PactGovernanceEngine` surface (73+ methods listed; `intersect_envelopes` is not one of them)                                                                                                                                 |
| M-07 | **HIGH**   | §3.3 references `TieredAuditDispatcher`; the binding has `AuditLogger` (Enterprise) but `TieredAuditDispatcher` is not named in the survey. Either deep in namespace or missing from binding                                                                                                  |
| M-08 | **MEDIUM** | §3.2 capability #7 (Trust Posture slider) has no explicit home in ROADMAP Phase 01 exit criteria — phase placement ambiguous                                                                                                                                                                  |
| M-09 | **MEDIUM** | §3.2 capability #8 (Cascade revocation) has no explicit home in ROADMAP Phase 01 exit criteria — phase placement ambiguous; compounded with M-01                                                                                                                                              |
| M-10 | **MEDIUM** | §3.2 capability #11 (Trust Vault sync) has no explicit phase home in ROADMAP; ADR-0007 is non-committal                                                                                                                                                                                       |
| M-11 | **MEDIUM** | §5.9 (BET-9 "Kailash primitives sufficient") conflicts with the binding reality — multiple primitives either missing or non-functional. Bet needs a stronger mitigation path or needs to be split into BET-9a (upstream primitives sufficient) + BET-9b (binding surface exposes them usably) |
| M-12 | **LOW**    | §2.1 does not explicitly name the 5 constraint dimensions at first reference — they are named later in §11 glossary. Readers debate the thesis without the canonical list in view                                                                                                             |
| M-13 | **LOW**    | §4.3 "Adjacent-product demarcation" does not explicitly address CNCF Envoy Proxy even though the product name collides. ADR-0002 addresses it, but the comparison deserves a row                                                                                                              |
| M-14 | **LOW**    | §3.3 "ratio is important: ~70% composition on shipped primitives / ~30% new" is asserted without basis given the M-01 through M-07 concerns. Ratio needs re-computation after binding-audit is folded in                                                                                      |

## Detail

### M-01 — Cascade revocation not on binding surface

**Claim in doc 00:** §3.3 lists "cascade revocation" as shipped via `kailash` core EATP: _"`TrustOperations` / Genesis Record / Delegation Record / **cascade revocation** / Ed25519 signing"_.

**Evidence against:** The kailash-rs survey (see `workspaces/internal/kailash-rs-survey-2026-04-21.md` §8 Implications) explicitly notes:

> "Cascade revocation is NOT explicitly surfaced in the binding — must verify behavior against Rust source or implement at Envoy level."

The doc 00 positions cascade revocation as a free-to-consume Kailash primitive, which is the foundation of user-visible capability #8 ("Cascade revocation — one-tap revoke of any grant, posture, or delegation; cascade kills descendants"). If this primitive is not exposed, Envoy must either (a) wait for upstream to expose it, (b) implement it at Envoy level (doubling the scope of Envoy's trust-lineage code), or (c) work with the Rust crate directly through `EatpTrustOperations` / `EatpDelegationChain.verify()` and manually construct the cascade.

**Actionable fix:**

- Flag cascade-revocation as "verify upstream exposure before Phase 01 lock" in §3.3.
- Add to BET-9 mitigation path: "upstream binding gaps in posture / cascade / MCP transports must be filed + closed before Phase 02 exit, or Envoy-level implementation must be scoped into Phase 01 as additive work."
- Cross-reference from `specs/trust-lineage.md` (future) to the binding gap.

### M-02 — DataFlow classification not on Rust-binding surface

**Claim:** §3.3 lists shipped primitives: _"`@classify` / `apply_read_classification()` / `format_record_id_for_event()` → `kailash-dataflow` → channel message privacy + ledger surface hygiene (doc 09)"_.

**Evidence against:** These are **kailash-py** idioms. The Rust-binding survey does not list them in the DataFlow Python surface. The Rust binding exposes `ModelDefinition.field(...)`, `DataFlow.register_model()`, `DataFlowExpress.create/read/update/delete`, but no `@classify` decorator or classification-read helpers.

This means:

1. If Envoy runs on `kailash-py` (opt-in), the primitives exist.
2. If Envoy runs on `kailash-rs-bindings` (default), the primitives do NOT exist.
3. This is a **runtime-parity gap** — not a parity "feature-identical" state but a structural asymmetry.

**Actionable fix:**

- Remove `@classify` / `apply_read_classification` / `format_record_id_for_event` from the Rust side of the primitive-inheritance manifest in §3.3, OR move them to a separate "Rust-side TODO before runtime parity" subsection.
- Add to BET-6 (runtime parity) falsifying evidence: "primitives that exist on one runtime but not the other at Phase 02 exit."
- Cross-reference from `specs/runtime-abstraction.md` and `specs/threat-model.md` (event-payload classification is a security-model claim).

### M-03 — MCP governance primitives not on binding

**Claim:** §3.3 lists _"`McpGovernanceEnforcer` + `McpGovernanceMiddleware` → `kailash-pact` → skill-runtime guarantees + third-party MCP (doc 08)"_.

**Evidence against:** The Rust-binding survey lists `PactGovernanceEngine.evaluate(...)` / `grant_clearance` / `revoke_clearance` but NOT `McpGovernanceEnforcer` or `McpGovernanceMiddleware` by name. Compound finding: BINDING-AUDIT C4 says MCP transports (stdio/SSE/HTTP) are NOT bound from Python at all. If transports aren't bound, the middleware that wraps them is moot.

**Actionable fix:**

- Either (a) verify these are namespace-internal (the survey may have missed them) by grepping the binding source directly, or (b) restate the doc 00 §3.3 mapping to use the general-form `PactGovernanceEngine.evaluate()` as the primitive and note that MCP-specific wrapping is an Envoy-level task.
- Doc 08 (skills) must explicitly scope "MCP transport + governance" as Envoy-work, not upstream-work.

### M-04 — PostureStore / EatpPosture binding exposure

**Claim:** §3.3 lists shipped primitives: _"`PostureStore` / `SQLitePostureStore` / `PostureEvidence` / 5 canonical postures → `kailash` core EATP → Trust Posture (doc 01 §5.3, doc 10)"_.

**Evidence against:** Rust-binding survey under "Top 20 parity-critical items" #13 flags _"Kaizen Phase 13 types (EatpPosture, VerificationConfig, etc.) — .pyi missing 8 Phase 13 types (HIGH severity B1 gap)"_. If the .pyi is missing these types, the binding surface may not expose them or they are not usable with IDE assistance.

**Actionable fix:**

- Add to BET-9 mitigation: Phase-13 types exposure is a Phase 01 exit gate.
- §3.3 must footnote this primitive with "requires B1 closure" until verified.

### M-05 — PlanSuspension Kaizen primitive

**Claim:** §3.3 lists _"Kaizen governed agents + L3 Plan DAG + **PlanSuspension** → `kailash-kaizen` → Boundary Conversation agent + scheduled rituals"_.

**Evidence against:** `PlanSuspension` is not listed in the Rust-binding Kaizen surface. It may be an internal concept in the L3 Plan DAG subsystem, but it is not exposed as a binding-callable type.

**Actionable fix:** Verify whether `PlanSuspension` is user-visible via `kailash-kaizen` through the Python binding. If not, either drop from primitives list or reclassify as an Envoy-level concept built on lower-level Kaizen primitives.

### M-06 — `intersect_envelopes()` not enumerated on PactGovernanceEngine

**Claim:** §3.3 lists _"`RoleEnvelope` / `TaskEnvelope` / `intersect_envelopes()` + 5 constraint dimensions → `kailash-pact` → Envelope compiler (doc 02)"_.

**Evidence against:** The survey enumerates 73+ methods on `PactGovernanceEngine` but `intersect_envelopes` is not named in the method sample. The concept may be implicit in `evaluate(context, action, resource)` which composes the relevant envelopes internally, OR it may be an internal Rust concept not exposed to Python.

**Actionable fix:** Verify via `bindings/kailash-python/python/kailash/*.pyi` grep or Rust source grep. If `intersect_envelopes` is Rust-only, the Envelope compiler in doc 02 must use `evaluate()` at a higher level of abstraction.

### M-07 — `TieredAuditDispatcher` naming divergence

**Claim:** §3.3 lists _"`TieredAuditDispatcher` + hash-chained Audit Anchors + SIEM export → `kailash` core EATP → Envoy Ledger (doc 04)"_.

**Evidence against:** Survey lists `AuditLogger.log(action, resource, user, details)` in Enterprise but `TieredAuditDispatcher` is not named. Possible alternatives on the binding: `EatpTrustOperations.audit(tracker, action_type, details, outcome, resources)` which looks closer to the dispatcher pattern. "Hash-chained Audit Anchors" is consistent with EATP but the class name in the survey is not `TieredAuditDispatcher`.

**Actionable fix:** Correct the primitive name (likely to `EatpTrustOperations.audit` + whatever the binding exposes for hash-chaining). This is not a breaking problem — the _capability_ exists — but the _name_ is wrong in the thesis doc, which means downstream docs will copy the wrong name.

### M-08 — Trust posture slider phase placement

**Claim:** §3.2 capability #7 is "Trust posture slider — 5-level ratchet".

**Inconsistency:** ROADMAP Phase 01 exit criteria do not mention "trust posture" explicitly. ROADMAP Phase 01 "Components (Python first, via kailash-py)" lists Boundary Conversation, Grant Moment UI, Daily Digest, Ledger, Envelope compiler, Trust store, Budget tracker, Model adapter, Shamir. The slider is absent.

**Actionable fix:** Either (a) add posture slider to ROADMAP Phase 01 components, or (b) move posture slider to Phase 02 in §3.2 and note it as a Phase-02 capability. Given the thesis's central role for postures (PSEUDO → AUTONOMOUS ratchet), option (a) is preferable, but this forces a ROADMAP edit.

### M-09 — Cascade revocation phase placement

**Inconsistency:** §3.2 capability #8 is cascade revocation. ROADMAP Phase 01 exit does not mention it. Doc 00 §3.3 lists it as a shipped upstream primitive — but M-01 shows it isn't on the binding. Composite effect: a user-visible capability with no shipped substrate and no phase home.

**Actionable fix:** Phase 01 exit criteria must explicitly include "revoke a grant and observe cascade effect on downstream delegations", OR cascade revocation is deferred to Phase 02/03 and §3.2 renumbers. If cascade revocation slides to Phase 02, the "one-tap revoke on anything" pitch in CHARTER.md loses its Phase 01 teeth.

### M-10 — Trust Vault sync phase placement

**Inconsistency:** §3.2 capability #11 is Trust Vault sync (6 integrations + native). ROADMAP mentions ADR-0007 (Trust Vault sync decision) but no phase places vault sync on an exit criterion.

**Actionable fix:** Vault sync is a natural Phase 02 or 03 capability (Phase 01 is desktop-single-machine-only per the local-only default). Doc 00 §3.2 list should explicitly tag each capability with a phase number.

### M-11 — BET-9 too weak

**Issue:** BET-9 asserts "Kailash primitives are sufficient" with falsifying evidence _"Phase 01 implementation discovers a primitive… that looks shipped but has an orphan pattern, stub behavior, or a semantic gap."_ The mitigation paths are minor / major / kill.

The kailash-rs survey already discovered ≥5 such primitives (see M-01 through M-07). By doc 00's own criteria, BET-9's mitigation should already be firing, at "minor" or "major" tier. Yet the doc treats BET-9 as prospective, not already-disconfirmed.

**Actionable fix:** Split BET-9 into:

- **BET-9a — Upstream Kailash primitives are sufficient** (the abstract feasibility claim; still mostly on track per EATP D6 / PACT N1–N6 / DataFlow parity).
- **BET-9b — Kailash Python binding surface exposes usable versions of those primitives by Phase 01 exit** (this bet is in tension with the survey; needs active mitigation).

§6 counterfactuals must then distinguish CF-9a from CF-9b.

### M-12 — Constraint dimensions not named at first reference

**Claim:** §2.2 "The answer" lists boundary, grant, posture, ledger, revocation as the mechanical forms. But it does NOT enumerate the 5 constraint dimensions (Financial, Operational, Temporal, Data Access, Communication) at first reference. A debate reader coming to the doc cold has to search to find them.

**Actionable fix:** §2.2 or §2.3 should name the 5 dimensions in a single line at first reference. Example: _"A **boundary** — a declared envelope across five constraint dimensions (Financial, Operational, Temporal, Data Access, Communication) …"_. Canonical-name compliance is already enforced by `rules/terrene-naming.md`; surfacing the list early helps readers.

### M-13 — CNCF Envoy Proxy not in adjacent-product table

**Gap:** §4.3 lists 10 adjacent products. CNCF Envoy Proxy is NOT in the table, even though the product is actively named-collision-risk and ADR-0002 mandates a legal disambiguator.

**Actionable fix:** Add row: _"CNCF Envoy Proxy — the pattern-match: 'networking proxy / data-plane layer'. Envoy's categorical difference: Envoy Agent is an individual-first autonomous AI with a personal trust vault; it operates at the application+identity layer, not the network+service-mesh layer. Legal mark disambiguates."_

### M-14 — 70/30 composition ratio unfounded

**Claim:** §3.3 concludes _"The ratio is important: ~70% of Envoy's functionality composes on shipped Foundation primitives; ~30% is new UX + distribution code."_

**Issue:** Given M-01 through M-07, a material fraction of the "shipped primitives" Envoy needs are either (a) Python-only, (b) not on the Rust binding, (c) non-functional in the binding per BINDING-AUDIT, or (d) name-mismatched. The 70/30 ratio needs re-computation against the _binding reality_, not the _conceptual upstream_.

**Actionable fix:** Either drop the ratio claim, replace with a qualitative statement ("Envoy composes heavily on shipped primitives where they exist; gaps are enumerated in BET-9b"), or re-derive the ratio after a binding-audit pass.

## Resolution summary

- **5 HIGH** findings require text changes in §3.3 + BET-9 split + primitive-name corrections.
- **3 MEDIUM** findings require phase-number tagging in §3.2 capabilities list + ROADMAP cross-check.
- **3 LOW** findings are cosmetic / comprehensiveness.
- **None CRITICAL** at this sweep level.

**Recommendation:** apply HIGH fixes before Round 2. MEDIUM + LOW can go inline during the BET-9 rework since that's where the corrections cluster.
