# 17 — Foundation Health Heartbeat — DECISION shard

**Document role:** This is the one pre-declared DECISION shard in the `/analyze` plan (per `01-shard-plan.md` §2 row 17). The job is to recommend **implement-in-Phase-01** OR **de-scope-to-Phase-02-entry** for the Foundation Health Heartbeat primitive, with evidence. The recommendation IS the product of this shard; everything else (call-graph sketch, class structure, test surface) is conditional context that supports the recommendation.

**Date:** 2026-05-03 (shard 17 of `/analyze`).
**Status:** DRAFT — load-bearing for shard 19 (pipx distribution — package-tree affected by decision) and for the `/todos` build-sequence.

**TL;DR — Recommendation: DE-SCOPE TO PHASE 02 ENTRY.** Phase 01 ships an integration-point STUB only (consent record schema + ledger entry type + revocation hook + payload-schema-fixed defense), no aggregator, no OHTTP relay, no Prio/STAR client. Evidence: (a) the operational substrate (Foundation OHTTP Key Configuration Server + Relay + STAR/Prio aggregator) does not exist on the kailash-py axis OR the Foundation-ops axis at 2026-05-03; (b) Heartbeat is a cross-cutting deliverable, NOT one of the 9 EC predicates that gate Phase 01 ship; (c) Phase 01 cohort is too small (N≤24 onboardings per EC-7 acceptance) to clear the spec's k=100 anonymity floor — Heartbeat would refuse to send for the entire Phase 01 window even if shipped. The cost of de-scope is BET-8 falsifiability slips to Phase 02 (and BET-3 / BET-12 lose their primary measurement substrate at Phase 02 cohort scale, not at Phase 01). The cost of NOT de-scoping is two-to-three full sessions of Foundation-ops infrastructure work that nothing in the EC-1..EC-9 predicate consumes.

---

## 1. Source spec citation

This shard cites — never paraphrases — the following frozen specs. All edits BLOCKED under `rules/specs-authority.md` MUST Rule 5b (37-sibling re-derivation cost).

- `specs/foundation-health-heartbeat.md` — owning spec; design stack, payload (21 boolean flags), cadence, consent layer, error taxonomy, test location.
- `specs/foundation-ops.md` § "Infrastructure inventory" rows 3–5 — Foundation-side dependencies: **OHTTP Key Configuration Server** (item 3), **OHTTP Relay** (item 4), **STAR/Prio aggregator** (item 5). All three are Foundation-operated infrastructure consumed BY the client; none ship as part of `kailash-py` or any pip-installable package today.
- `specs/threat-model.md` § "Phase gates" Phase 02 row — explicitly schedules "OHTTP/STAR review" at Phase 02, not Phase 01. The threat model itself anticipates Heartbeat is a Phase 02 surface.
- `specs/foundation-health-heartbeat.md` § "Cross-references" — names `specs/grant-moment.md`, `specs/trust-lineage.md`, `specs/acceptance-metrics.md`, `specs/ledger.md`, `specs/network-security.md`, `specs/foundation-ops.md`, `specs/threat-model.md` as the seven dependent specs. The cross-references make Heartbeat a cross-domain primitive; the operational substrate (`foundation-ops.md`) is the load-bearing dependency, not the Envoy-client surface.
- `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` § 5.0 + § 5.8 (BET-8) — the measurement-methodology rationale for Heartbeat existing at all. § 3.2 capability table row 19 explicitly tags Foundation Health Heartbeat as **first-phase 02**, not 01. This is a contradiction with thesis § 3.1 Phase 01 components list (which DOES list Heartbeat in Phase 01) — which is exactly why the brief at `briefs/00-phase-01-mvp-scope.md` registers Heartbeat as **de-scope candidate #2**. The frozen-spec ambiguity is itself evidence the architects expected this decision to be made downstream.

The recommendation below resolves the thesis § 3.1 vs § 3.2 contradiction in favour of § 3.2 (Phase 02), with structural Phase 01 stubs preserving § 3.1's cross-cutting-deliverable framing.

---

## 2. Verified provider state — Grade C on both axes

Per the protocol in `03-kailash-py-mvp-readiness.md` § 5 (verification protocol for shards 4–19), and the specific search list pre-declared in this shard's brief.

### 2.1 `kailash-py` axis

The 13 Phase 00-filed `terrene-foundation/kailash-py` issues (#594–#606) are catalogued at `workspaces/phase-00-alignment/issues/manifest.md`. **Zero of them name STAR, Prio, OHTTP, oblivious_http, heartbeat, or telemetry.** The Phase 00 architects did NOT file an upstream issue for Heartbeat client primitives because Heartbeat was scoped as a Foundation-ops infrastructure deliverable (see `specs/foundation-ops.md` items 3–5), not a `kailash-py` SDK primitive.

Net `kailash-py` provider state: **Grade C — absent**. There is no kailash-py module today that provides STAR/Prio share-splitting, no module that provides OHTTP client wrapping, no module that provides DP-noise injection, no module that provides k-anonymity gating. Adding any of them is greenfield Envoy-new-code OR upstream-PR work on a primitive that has no existing Foundation-side maintainer brief.

### 2.2 Foundation-ops axis

`workspaces/phase-00-alignment/issues/manifest.md` § "terrene-foundation/mint" lists 7 mint-side issues (#2–#8). **Zero of them are about Foundation-ops Heartbeat infrastructure** — none call for the OHTTP Key Configuration Server registry contract, none call for the STAR/Prio aggregator endpoint, none call for the OHTTP relay deployment plan. The mint issues cover spec-additions for new primitives consumed at the Envoy-client layer (TieredAuditDispatcher, PostureStore, McpGovernance, MCP transport extensions, algorithm-identifier, ENVELOPE.md schema, Shamir ritual). Heartbeat infrastructure is unfiled.

Net Foundation-ops provider state: **Grade C — absent**. The OHTTP Key Configuration Server is described in `specs/foundation-ops.md` § "Infrastructure inventory" row 3 but no deployment plan exists; the OHTTP Relay (row 4) is named with no operator selection; the STAR/Prio aggregator (row 5) is "Foundation-operated" but no operator schedule, no aggregator endpoint, no published key schema. All three are spec-only.

### 2.3 Net-net

Both axes are at Grade C. Phase 01 implementation of Heartbeat would require:

1. **Building a STAR/Prio share-split client primitive in pure Python** — no Foundation-blessed library exists.
2. **Building an OHTTP client wrapper in pure Python** — RFC 9458 is recent; reference implementations exist (`ohttp` Rust crate, `bhttp` parsing libraries) but a pure-Python client suitable for `pip install` is greenfield.
3. **Standing up a Foundation-side aggregator endpoint** — requires Foundation infrastructure work, signing-ceremony coordination, and a published key configuration; none exists.
4. **Standing up a Foundation OHTTP relay** — operational deployment + IP-stripping verification; none exists.
5. **Coordinating cross-client epoch synchronization** for STAR/Prio share aggregation windows — protocol-level coordination across the entire Phase 01 cohort.

This is the load-bearing evidence for the de-scope recommendation: **Heartbeat is not "wire one library", it is "stand up a privacy-preserving telemetry stack from spec to deployment"**.

---

## 3. Envoy-new-code surface — IF implemented in Phase 01

Documented for completeness. The cost surface this section enumerates is what de-scope avoids.

### 3.1 Client-side primitives Envoy would ship

| Component                      | Lines of load-bearing logic (estimated) | Invariants held                                                                                                                                                                                       |
| ------------------------------ | --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| STAR/Prio share-split client   | ~250 LOC                                | k-anonymity client-side floor; share entropy; per-metric DP ε budget tracking; share-aggregation epoch alignment                                                                                      |
| OHTTP client (RFC 9458)        | ~200 LOC                                | Foundation Key Configuration Server fetch + cache + expiry; relay-strips-source-IP verification; HPKE encapsulation; request/response binding                                                         |
| Differential-privacy noise     | ~100 LOC                                | per-metric ε; bounded-noise distribution selection; budget-exhaustion error path                                                                                                                      |
| Consent / Grant Moment hook    | ~80 LOC                                 | signed Delegation Record format; cascade-revocation triggers stop-sends; first-run opt-OUT default                                                                                                    |
| Payload schema enforcement     | ~60 LOC                                 | exactly 21 flags; `duress_unlock_detected` BLOCKED structurally; covert-channel defense (T-054); reproducible-build attestation requirement                                                           |
| Per-install random ID rotation | ~50 LOC                                 | quarterly rotation; not coupled to ritual timing (24h debounce per spec L-01 fix)                                                                                                                     |
| Counter accrual / reset        | ~100 LOC                                | weekly cadence; counters retained on send-failure; reset on send-success; consent-revoked clears pending counters                                                                                     |
| Error-taxonomy enforcement     | ~120 LOC                                | 10 typed errors per spec § "Error taxonomy" — `OHTTPRelayUnavailableError`, `STARShardCorruptError`, `DPBudgetExceededError`, `kAnonymityFloorViolatedError`, `RitualCouplingDebounceTriggered`, etc. |

**Total load-bearing LOC: ~960.** Per `rules/autonomous-execution.md` § "Per-Session Capacity Budget", a single shard MUST stay within ≤500 LOC of load-bearing logic. Heartbeat client implementation is **a 2-shard minimum** at autonomous capacity. The same rule's invariant-count test (≤5–10 simultaneous invariants) is also exceeded — the table above lists ~12 distinct invariants that must hold simultaneously.

### 3.2 Foundation-side infrastructure Envoy CANNOT ship

| Component                              | Owner                                             | Phase 01 reachable?                                                                                                  |
| -------------------------------------- | ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| OHTTP Key Configuration Server         | Foundation operations team                        | NO — no deployment plan; no operator; no published key registry                                                      |
| OHTTP Relay                            | Foundation OR third-party                         | NO — operator selection unresolved (see `foundation-ops.md` § "Open questions" item 3)                               |
| STAR/Prio aggregator                   | Foundation operations team                        | NO — no aggregator endpoint, no signing-ceremony plan, no per-metric ε budget published                              |
| Per-metric ε budget publication        | Foundation transparency UX                        | NO — see `specs/foundation-health-heartbeat.md` § "Open questions" item 1 (unresolved transparency vs analyzability) |
| Reproducible-build verification stream | Foundation distribution + third-party reproducers | NO — `specs/foundation-ops.md` row 13 lists this as a stream; no operator at 2026-05-03                              |

**These are not Envoy-side decisions.** The Envoy product cannot unilaterally stand up the Foundation OHTTP relay or the STAR/Prio aggregator. Even if Envoy were to ship a fully-correct pure-Python client today, the client would refuse to send (per `OHTTPRelayUnavailableError` error path) for the entire Phase 01 window because the relay does not exist.

### 3.3 Cohort-floor problem

The spec's k-anonymity floor is **k ≥ 100** (per `specs/foundation-health-heartbeat.md` § "Design stack" item 1 + `specs/foundation-ops.md` open question 2). Phase 01 EC-7 specifies **N=3 sessions × 8 channels = 24 onboardings** as the acceptance gate; thesis § 3.1 frames the user count as "≥3 distinct first-time users" for EC-1. Phase 01 cohort is on the order of **single-digit-to-low-tens of users**.

If Heartbeat shipped in Phase 01 with the spec's k≥100 floor, **every send would trigger `kAnonymityFloorViolatedError` (collector withholds aggregate)** — the spec's own error taxonomy gates the send. No data would flow. Heartbeat falsifiability of BET-8 / BET-3 / BET-12 only becomes possible at a cohort scale where k=100 holds, which is a Phase 02 cohort scale by definition.

This is the strongest single piece of evidence: **the spec mandates a privacy floor that Phase 01 cohort size cannot clear.** Heartbeat is not just operationally hard — it is structurally non-functional at MVP cohort scale.

---

## 4. Class structure sketch — IF implemented in Phase 01

```python
# envoy/heartbeat/client.py
class HeartbeatClient:
    def __init__(
        self,
        consent_store: TrustStore,
        ledger: Ledger,
        ohttp_kcs_url: str,
        relay_url: str,
        aggregator_url: str,
    ): ...
    def opt_in(self, grant_moment: GrantMoment) -> DelegationRecord: ...
    def opt_out(self, revocation: RevocationRecord) -> None: ...
    def emit_weekly_heartbeat(self) -> HeartbeatSendResult: ...
    def _split_into_star_shares(self, payload: HeartbeatPayload) -> list[STARShare]: ...
    def _check_k_anonymity_client_side(self, payload: HeartbeatPayload) -> bool: ...
    def _apply_dp_noise(self, counter: int, epsilon: float) -> int: ...
    def _send_via_ohttp(self, share: STARShare) -> None: ...

# envoy/heartbeat/payload.py — fixed schema, T-054 defense
@dataclass(frozen=True)
class HeartbeatPayload:
    install_id: str  # quarterly-rotated random
    envoy_version: str
    flags: dict[str, bool]  # exactly 21 keys; validated; duress_unlock_detected BLOCKED

# envoy/heartbeat/errors.py — 10 typed errors per spec
class OHTTPRelayUnavailableError(Exception): ...
class STARShardCorruptError(Exception): ...
class DPBudgetExceededError(Exception): ...
class kAnonymityFloorViolatedError(Exception): ...
class RitualCouplingDebounceTriggered(Exception): ...
class ConsentRevokedError(Exception): ...
class PayloadSchemaDriftError(Exception): ...  # T-054 defense
class ReproducibleBuildAttestationMissingError(Exception): ...
class DuressFlagLeakageRefusedError(Exception): ...  # T-041 defense
class RandomIdRotationOverdueWarning(Warning): ...
```

**The class structure compiles in isolation.** The structural test of "given this spec is frozen, how do I wire `kailash-py` to deliver it" returns: `kailash-py` provides nothing relevant here; the implementation is 100% Envoy-new-code on top of HPKE / OHTTP libraries. The only kailash-py touchpoint is `kailash.trust.signing` (Ed25519) for the signed-consent Delegation Record — which Phase 01 already wires for Grant Moment. The "STAR/Prio aggregator + OHTTP relay" half is not a code question; it is a deployment question.

---

## 5. Integration points — every primitive that emits telemetry would write to Heartbeat

If Heartbeat ships, the following Phase 01 primitives become call sites:

| Primitive (and its owning shard)    | Call-site nature                                                                                          |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Boundary Conversation (shard 8)     | `completed_boundary_conversation` flag toggle on completion                                               |
| Daily Digest (shard 11)             | `opened_daily_digest_this_week` flag toggle when user reads digest                                        |
| Grant Moment (shard 10)             | `grant_moment_novelty_approved` / `grant_moment_novelty_denied` counters; `force_install_used_skill` flag |
| Authorship Score (shard 9)          | `authorship_score_reached_3` / `authorship_score_reached_5` flags                                         |
| Posture ladder (shard 9)            | `posture_delegating_active` / `posture_autonomous_active` flags                                           |
| Budget tracker (shard 12)           | `budget_monthly_exceeded_50pct` / `budget_monthly_exceeded_80pct` flags                                   |
| Channel adapters (shard 16)         | 6 per-channel `channel_*_active` flags                                                                    |
| Runtime abstraction stub (shard 18) | `runtime_kailash_rs_active` flag (Phase 01 always FALSE; Phase 02 toggles)                                |
| Trust lineage (shard 5)             | NEVER `duress_unlock_detected` — `DuressFlagLeakageRefusedError` defense                                  |

Each integration point is a one-line counter increment / boolean toggle. **The integration cost is small; the substrate cost (§3.2) is enormous.**

This is precisely the asymmetry that justifies the Phase 02 deferral with Phase 01 stubs. Phase 01 can land the integration-point hooks (the one-line emits) wired against a no-op stub Heartbeat client; Phase 02 swaps the stub for the real client without touching any of the integration sites. The same approach is used by `specs/runtime-abstraction.md` for `kailash-runtime` (abstract interface in Phase 01, second runtime wired in Phase 02 — see ADR-0001).

---

## 6. Tier 2 / Tier 3 test surface — IF implemented in Phase 01

Per `specs/foundation-health-heartbeat.md` § "Test location", 11 test files are required:

- 7 Tier 2 integration tests (consent grant moment, cascade-revoke, 21-flag payload, L-01 ritual coupling debounce, quarterly random ID rotation, DP ε budget per metric, k=100 anonymity floor)
- 3 regression tests (T-052 OHTTP relay compromise, T-054 payload schema fixed, T-041 duress flag never reported)
- 1 Tier 3 E2E test (full weekly cycle: opt-in → 7-day accrual → OHTTP send → counter reset)

**The Tier 3 E2E test is not runnable in Phase 01.** It requires:

- A real STAR/Prio aggregator endpoint receiving real shares
- A real OHTTP relay stripping source IPs
- Real reproducible-build attestation verification

None exist. The test would have to fixture-mock the entire Foundation-ops infrastructure, which violates `rules/testing.md` § "Tier 2 (Integration): Real infrastructure recommended" + § "Tier 3 (E2E): Real everything". Mocked aggregator + mocked relay = no confidence the FFI / network / crypto path actually works. This is the same orphan-detection failure mode that `rules/orphan-detection.md` § 1 + § 2 mandates against.

The Tier 2 integration tests are partially runnable (consent record format, cascade-revoke, payload schema, ritual coupling) but the meaningful three (DP ε, k=100 floor, OHTTP send) are not — they require Foundation infrastructure that does not exist.

---

## 7. **DECISION — De-scope Foundation Health Heartbeat to Phase 02 entry**

### 7.1 The recommendation

**Phase 01 ships a Foundation Health Heartbeat STUB only.** The stub captures the integration points (single-point hooks at every primitive that would emit a counter) and the integration contract (consent record format, `FoundationHealthHeartbeatConsent` ledger entry type, `DuressFlagLeakageRefusedError` defense, exact 21-flag payload schema). The stub does NOT ship the STAR/Prio client, the OHTTP wrapper, the DP noise primitive, the aggregator coordination, or any network-layer code.

Phase 01 records, in `specs/foundation-health-heartbeat.md` (the only acceptable spec edit) OR in a fresh `specs/heartbeat-stub-phase01.md` additive spec (preferred per `rules/specs-authority.md` MUST Rule 5b), exactly which integration points exist as no-ops in Phase 01 and exactly what Phase 02 entry must wire.

### 7.2 Five-criterion evidence (per shard brief)

**Criterion 1 — Operational complexity:** the substrate (Foundation OHTTP Key Configuration Server + Relay + STAR/Prio aggregator) does not exist anywhere — not in `kailash-py`, not in `kailash-rs`, not in deployment, not in mint specs as a filed issue. Standing it up is 2–3 autonomous-execution sessions of pure Foundation-ops work that produce zero EC-1..EC-9 progress. **WEIGHT: HIGH AGAINST IMPLEMENTING IN PHASE 01.**

**Criterion 2 — BET falsifiability cost (corrected per carry-forward R2-M-01 disposition; see `workspaces/phase-01-mvp/04-validate/round-4-implementation-comprehensive.md` § 4.6):** BET-8 ("Foundation Health uptake") is the single BET that explicitly hinges on Heartbeat shipping in Phase 01 (per `00-inheritance-from-phase-00.md` § 2.4 BET table — "YES if Heartbeat ships in Phase 01; NO if de-scoped"). The earlier draft of this criterion incorrectly named BET-3 (sovereignty durability) and BET-12 (governance-primary-surface palatability) as the load-bearing falsifiability casualties. The accurate falsifiability casualty of the heartbeat de-scope is **BET-5 (cohort-floor mechanic)** — BET-5 is the bet whose falsifying evidence depends on the k=100 cohort-floor mechanic that Heartbeat itself instruments (the floor refuses to send below k=100; the floor IS the falsifiability mechanism). BET-3 and BET-12 are NOT measurable at Phase 01 cohort scale REGARDLESS of Heartbeat shipping, because the k=100 floor blocks Heartbeat from emitting at MVP cohort sizes (single-digit users); their falsifying-evidence bullets are tagged `[Heartbeat]` in thesis § 5.0 only as a Phase 02-availability marker, NOT as a Phase 01-availability claim. **The falsifiability cost of de-scope is BET-8 (direct dependency) plus BET-5 (cohort-floor mechanic).** **WEIGHT: LOW AGAINST DE-SCOPING.** Both bets were always Phase 02 measurement substrate; the de-scope formalizes what thesis § 5.0 already implies.

**Criterion 3 — Foundation pace:** the Phase 00 → 2026-05-03 freshness gate (per `journal/0002-DISCOVERY-upstream-readiness-improved.md`) found 12-of-13 `kailash-py` issues closed in 5 days — but **none of them concerned Heartbeat infrastructure**. The Foundation-side velocity is on `kailash-py` SDK primitives, not on Foundation-ops infrastructure. There is no signal that the OHTTP relay or STAR/Prio aggregator is being built upstream this quarter. **WEIGHT: HIGH AGAINST IMPLEMENTING IN PHASE 01** — the upstream-velocity argument that worked for shards 6/9/11/13/15 does NOT work for shard 17.

**Criterion 4 — Phase 01 ship-predicate impact:** per `02-mvp-objectives.md` § 4, Phase 01 ships when `EC-1 ∧ EC-2 ∧ ... ∧ EC-9 ∧ all 7 cross-cutting deliverables present`. Heartbeat is in the cross-cutting deliverables list (row 4 of § 3 cross-cutting table) but is NOT in any EC predicate. **De-scoping does NOT block ship.** The Phase 01 ship predicate is structurally agnostic to Heartbeat presence; the ship gate is the 9 EC conjunction. **WEIGHT: HIGH FOR DE-SCOPING.** Heartbeat is the only cross-cutting deliverable that is structurally optional in this sense.

**Criterion 5 — Phase-02 re-entry cost:** if Heartbeat slips, Phase 02 entry must wire the real client behind the Phase 01 stubs. The re-entry is mechanical IFF the Phase 01 stubs preserve the integration contract:

1. The 21 single-line integration hooks at every emitting primitive exist and call into a stub `HeartbeatClient` interface.
2. The `FoundationHealthHeartbeatConsent` ledger entry type is reserved (so Phase 02 first-run consent doesn't conflict with Phase 01 ledger schema).
3. The `DuressFlagLeakageRefusedError` defense ships in Phase 01 (it is a structural defense — programming error trap — not a runtime feature; it MUST live close to the flag-emit hook regardless).
4. The `_validate_payload_schema(payload)` 21-flag check ships in Phase 01 (T-054 defense; lives at the stub boundary).

If those four Phase 01 stubs ship, Phase 02 entry is "wire HeartbeatClient.send() to a real STAR client + OHTTP wrapper + Foundation aggregator endpoint, swap stub for real." That is one shard of Phase 02 work, not a multi-shard rebuild. **WEIGHT: LOW AGAINST DE-SCOPING** — the architectural carry-cost is small.

### 7.3 The four mandatory Phase 01 stubs

# Round 2 R2-H-02 fix: separates the no-op-in-production HeartbeatClient (called from 21 emit sites) from the deferred network/crypto primitives (never called from Phase 01 code paths).

These MUST ship in Phase 01 even under de-scope, because they preserve the Phase 02 re-entry contract. The stubs partition into two structurally distinct categories — one that production code DOES call (as a genuine no-op), and three that production code MUST NEVER call (because they cover network/crypto primitives Phase 02 will activate). Conflating these categories is the failure mode Round 2 R2-H-02 caught: if the 21 emit-site primitives invoke a stub that raises `PhaseDeferredError`, every emit primitive crashes in Phase 01 production runs (Boundary Conversation completion → crash; Daily Digest open → crash; Grant Moment approve → crash). The fix is to separate the two categories at the module boundary.

1. **`FoundationHealthHeartbeatConsent` ledger entry type** — reserved in `specs/ledger.md` already (per cross-references); Phase 01 ledger writer must accept and round-trip the entry type even though it never fires in Phase 01.
2. **`DuressFlagLeakageRefusedError` structural defense** — per spec § "Error taxonomy" + § "Flags NEVER reported", T-041 defense. Ships as a one-line guard at every flag-emit hook (which themselves are no-ops in Phase 01); the guard catches programming errors / hostile patches even when the emit pipeline is stubbed. Cost: ~5 LOC.
3. **21-flag payload schema validation (T-054 defense)** — `_validate_payload_schema(payload: HeartbeatPayload)` raises `PayloadSchemaDriftError` on any field outside the 21-flag set. Ships as the type-frozen `@dataclass(frozen=True) class HeartbeatPayload` with explicit field whitelist. Cost: ~30 LOC.
4. **Integration-point no-op hooks** — at each of the 21 emit sites (Boundary Conversation completion, Daily Digest open, Grant Moment approve/deny, etc.), a single line `self._heartbeat.maybe_record_flag("...")` that calls the stub `HeartbeatClient.maybe_record_flag()` which is a no-op in Phase 01. Cost: ~21 lines + a stub class with one method.

**Phase 01 stub partitioning (R2-H-02 fix per `rules/zero-tolerance.md` Rule 2 + `rules/orphan-detection.md` Rule 1 + Rule 4a):**

- **Stub 1 — `envoy/heartbeat/client.py`**: `class HeartbeatClient: def maybe_record_flag(self, flag_name: str) -> None: pass` — **genuine no-op**. THIS is what the 21 emit-site primitives invoke (per § 7.6 cross-shard implications below). The method body is a literal `pass`; no exception is raised; no Ledger entry is written; no network call is made. This stub class is the orphan-detection counterpart to the four `PhaseDeferredError` modules: it exists precisely BECAUSE production code calls it on the hot path. Without this stub, Boundary Conversation completion / Daily Digest open / Grant Moment approve / etc. would all crash on first emit.

- **Stubs 2, 3, 4, 5 — `envoy/heartbeat/{star_prio,ohttp,signed_consent,registry}.py`**: each raises `PhaseDeferredError("Phase 02 entry deliverable")`. These cover the network and cryptographic primitives that Phase 02 will activate (STAR/Prio share-splitting, OHTTP key-server + relay, signed-consent records on the Foundation aggregator side, runtime/device registry handshake). **Phase 01 production code MUST NEVER call these.** Per `rules/zero-tolerance.md` Rule 2, a stub that raises on call when production code is supposed to invoke it is the fake-implementation pattern at the extreme; per `rules/orphan-detection.md` Rule 1, every facade-shape attribute requires a production call site within 5 commits — these four stubs exist for the inverse reason: they are placeholders for Phase 02 entry, not Phase 01 hot-path consumers.

  A regression grep `grep -rln "import envoy.heartbeat.\(star_prio\|ohttp\|signed_consent\|registry\)\|from envoy.heartbeat.\(star_prio\|ohttp\|signed_consent\|registry\)" envoy/` MUST return zero matches in non-test code. The grep is the structural defense per `rules/orphan-detection.md` Rule 4a (a stub that is implemented later MUST NOT have any caller silently assuming the deferred behavior); when Phase 02 entry replaces the `PhaseDeferredError` body with a real implementation, the regression grep flips green automatically and any premature Phase 01 caller surfaces as a HIGH finding.

**Total Phase 01 stub cost: ~100 LOC, 5 invariants.** Within a single sub-shard budget. The 5-stub partition (1 no-op `HeartbeatClient` + 4 `PhaseDeferredError` network/crypto modules) preserves every Phase 02 re-entry contract while shipping zero Foundation-ops infrastructure AND zero production crashes on the 21 emit-site hot path.

### 7.4 What de-scope does NOT cost

- **Does not cost Phase 01 ship.** Heartbeat is not in the EC-1..EC-9 conjunction.
- **Does not cost BET-3 / BET-12 falsifiability.** The thesis already tagged those `[Heartbeat]` bullets as Phase 02 substrate; Phase 01 cohort size is below k=100 regardless.
- **Does not cost the cross-cutting-deliverables completeness claim.** The four Phase 01 stubs are themselves the cross-cutting-deliverable surface; the ship-predicate row stays satisfied with stubs in place.
- **Does not cost Foundation-ops upstream-PR pressure.** The Phase 02 entry checklist (which must include "stand up OHTTP KCS + Relay + STAR aggregator before Phase 02 ships") is documentation; this shard's deliverable explicitly produces that checklist as carry-forward.

### 7.5 What de-scope DOES cost

- **BET-8 falsifiability slips to Phase 02.** Per `00-inheritance-from-phase-00.md` § 2.4 BET table, BET-8 falsifiability moves from YES to NO. This is the single load-bearing measurable cost. The mitigation: BET-8 measurement was always Phase 02 cohort work anyway (k=100 floor + 18mo cohort horizon per thesis § 5.8); the YES rating was structurally optimistic.
- **One additional Phase 02 entry checklist item.** Phase 02 must stand up the Foundation-ops Heartbeat substrate before the runtime-pluggability work or the mobile work proceeds. Tracking surface: add to `workspaces/phase-01-mvp/02-plans/04-redteam-cycle-plan.md` carry-forward AND to a forthcoming `phase-02-entry-checklist.md`.
- **The Phase 01 brief's "must ship unless de-scoped per pre-declared sequence" framing in `briefs/00-phase-01-mvp-scope.md` § "Constraints + invariants" item 5 IS the de-scope itself.** This shard executes that pre-declared de-scope; no spec edit, no thesis edit, no ADR edit is required.

### 7.6 Cross-shard implications

- **Shard 8 (Boundary Conversation)** must ship the `completed_boundary_conversation` flag emit hook as a no-op call into the stub Heartbeat client.
- **Shard 11 (Daily Digest)** must ship the `opened_daily_digest_this_week` flag emit hook as a no-op call.
- **Shard 10 (Grant Moment)** must ship `grant_moment_novelty_approved` / `_denied` / `force_install_used_skill` flag emit hooks as no-op calls.
- **Shard 9 (Authorship Score / posture)** must ship the 4 score / posture flag emit hooks as no-op calls.
- **Shard 12 (Budget tracker)** must ship the 2 budget threshold flag emit hooks as no-op calls.
- **Shard 16 (Channel adapters)** must ship the 6 per-channel `channel_*_active` flag emit hooks as no-op calls.
- **Shard 18 (Runtime abstraction stub)** must ship the `runtime_kailash_rs_active` flag emit hook as a no-op call.

This is why this shard fires before shard 19 (pipx distribution) but after most peer shards in the parallelizable Group A — every emit-side primitive must know "wire to stub Heartbeat, not to real Heartbeat" at implementation time. The de-scope decision is a Phase-01 architectural fact that constrains every emit-site primitive shard.

### 7.7 Recommendation in plain language (per `rules/communication.md`)

> **What Phase 01 ships:** the consent record, the audit ledger entry type, the privacy-defense guards (so a future bug in flag emission cannot leak the duress flag), and the one-line emit hooks at every primitive that should eventually report — but every emit hook is a no-op for Phase 01.
>
> **What Phase 01 does NOT ship:** the privacy-preserving network telemetry stack (encrypted share-splitting + IP-stripping relay + Foundation aggregator). That stack requires Foundation infrastructure that does not exist today and a privacy floor (100 simultaneous users) that the Phase 01 MVP cohort (single-digit users) cannot clear even if shipped.
>
> **Trade-off:** we slip the "is anyone using Envoy?" measurement substrate from Phase 01 to Phase 02. We do not slip any Phase 01 ship-gate (the 9 acceptance criteria); we do not slip any other BET; we do not delay any cross-cutting deliverable other than the telemetry one.
>
> **Foundation-ops carry-forward:** Phase 02 entry checklist gets a new item: "stand up the Heartbeat infrastructure (OHTTP key server + relay + Prio aggregator) before consuming Heartbeat measurements for BET-8 / BET-3 / BET-12."

---

## 8. Cross-references

- Source spec (frozen, DO NOT EDIT): `specs/foundation-health-heartbeat.md`
- Foundation-ops dependency spec: `specs/foundation-ops.md` § "Infrastructure inventory" rows 3–5
- Threat-model phase scheduling: `specs/threat-model.md` § "Phase gates" Phase 02 row
- Brief de-scope candidate citation: `workspaces/phase-01-mvp/briefs/00-phase-01-mvp-scope.md` § "Pre-declared Phase 01 de-scope candidates" row 2
- BET-8 dependency: `workspaces/phase-01-mvp/01-analysis/00-inheritance-from-phase-00.md` § 2.4 BET table
- Cross-cutting (NOT EC) framing: `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` § 3 + § 4
- Thesis BET tagging: `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` § 5.0 + § 5.8 (BET-8) + § 5.3 (BET-3) + § 5.12 (BET-12)
- Capability-table contradiction (Heartbeat = Phase 02 there): `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` § 3.2 row 19
- Capacity rationale: `.claude/rules/autonomous-execution.md` § "Per-Session Capacity Budget"
- Phase 02 re-entry methodology: `.claude/rules/specs-authority.md` MUST Rule 5b (additive spec preferred over edit)
- Communication framing: `.claude/rules/communication.md` § "Frame Decisions as Impact"
- Upstream-velocity finding (does NOT cover Heartbeat axis): `workspaces/phase-01-mvp/journal/0002-DISCOVERY-upstream-readiness-improved.md`
- Issue manifest (no Heartbeat ISS filed): `workspaces/phase-00-alignment/issues/manifest.md`
- Ship-predicate framing: `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` § 4
- Sharding plan row-17 contract: `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 2 (shard 17 row)
