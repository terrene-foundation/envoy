# Round 1 — Phase 01 MVP Red Team Comprehensive Audit

**Document role:** Shard 23 of /analyze. Round-1 redteam audit of the 16 primitive deep-dive shards (4–19), the 4 plan docs, the 8 user flow docs, the spec gap analysis (shard 22), the 2 additive new specs (`specs/independent-verifier.md`, `specs/mvp-build-sequence.md`), and the 3 journal entries. Re-derives findings from scratch per `rules/testing.md` § Audit Mode Rules — does NOT trust prior round outputs or any primitive shard's own §7 "no HIGH" claim at face value.

**Date:** 2026-05-03 (shard 23 of /analyze; round 1 of N).
**Status:** DRAFT — defines the convergence baseline. Per `02-plans/04-redteam-cycle-plan.md` §1, Phase 01 ships only after EC-6 is met (0 CRIT + 0 HIGH × 2 consecutive rounds).
**Discipline:** AST/grep verification per `skills/spec-compliance/SKILL.md`. Re-derive every claim from scratch. Cite by path + line. Do NOT modify any analysis doc; this audit's findings are the only deliverable.

---

## 1. Round 1 scope

### 1.1 Audited surface

- 16 primitive deep-dive docs: `01-analysis/{04..19}-*-implementation.md` and `01-analysis/{07,17,18}-*-decision/design.md`
- 4 plan docs: `02-plans/01-build-sequence.md`, `02-plans/02-test-strategy.md`, `02-plans/03-package-skeleton.md`, `02-plans/04-redteam-cycle-plan.md`
- 8 user-flow docs: `03-user-flows/{01..08}-*.md`
- Spec-gap analysis: `01-analysis/22-spec-gap-analysis.md`
- 2 additive new specs: `specs/independent-verifier.md`, `specs/mvp-build-sequence.md`
- 3 journal entries: `journal/0001-CONNECTION`, `journal/0002-DISCOVERY`, `journal/0003-GAP`

### 1.2 Mechanical sweeps run (per `02-plans/04-redteam-cycle-plan.md` § 6 + `rules/agents.md`)

1. **Spec compliance (AST/grep)** — every primitive's cited spec § + symbol against the FROZEN spec at HEAD. Re-derived from scratch.
2. **Orphan-detection sweep** — every facade-shape attribute paired with a production call site + Tier 2 wiring test path; every crypto-pair paired with a round-trip test; every manager-shape class paired with a Tier 2 wiring test.
3. **Closed-ISS sweep** — `gh issue view <N> --repo terrene-foundation/kailash-py --json state` for all cited issue numbers.
4. **Upstream module symbol verification** — Read `~/repos/loom/kailash-py/src/kailash/...` for every cited symbol path; AST/grep matched.
5. **Gap-analysis 22 disposition consistency** — timezone HIGH disposition (Option A) checked across shards 11, 12, flow 04, flow 08.
6. **HIGH-candidate HELD verification** — shard 13 chat-completion substrate HOLD rationale + supported-alternative test exercise check.
7. **Tenant-isolation Rule 1 sweep** — every primitive's persistence/cache/audit/metric key shape examined for `principal_id` dimension.
8. **Event-payload classification sweep** — Ledger row classified-PK redaction at SINGLE EMISSION POINT.
9. **`kailash-ml` exclusion verification** — `pip install kailash[shamir,nexus,kaizen]` transitive closure re-verified against `~/repos/loom/kailash-py/pyproject.toml` at HEAD.

---

## 2. Findings classified by severity

### 2.1 CRIT — 0

### 2.2 HIGH — 0

### 2.3 MED — 6

### 2.4 LOW — 4

Total: **10 findings**. None blocking; all dispositionable inside current /analyze scope or deferrable to /todos / Phase 02 entry without resetting the convergence counter.

---

## 3. Findings detail

### 3.1 R1-M-01 — Cross-doc drift in `envoy/cli` 11-subcommand naming

- **Severity:** MED
- **Surface:** Plan 01 `02-plans/01-build-sequence.md` line 263 + spec `specs/mvp-build-sequence.md` line 128 vs primitive shard 19 `01-analysis/19-pipx-distribution-architecture.md` § 3.4 lines 308–309.
- **Finding:** Plan 01 + the additive new spec list the 11 subcommands as `init / up / boundaries / ledger / shamir / digest / grant / posture / connection / model / version` with Phase 02 stubs `mobile-pair, enterprise-deploy`. The primitive shard 19 (source-of-truth per `02-plans/03-package-skeleton.md` § 6 cross-references) lists `init / chat / ledger export / ledger verify / shamir backup / shamir recover / digest today / budget status / channel <add|list|remove> / posture / upgrade (stub) / uninstall --destroy-vault (stub) / heartbeat (DE-SCOPED)`. Plan 03 line 729 cross-references `upgrade / uninstall --destroy-vault` as the Phase 02 stubs (matching shard 19), but plan 03 line 414 lists subcommand names that drift slightly from shard 19 (e.g. `chat` matches; `up`, `boundaries`, `mobile-pair`, `enterprise-deploy` are introduced nowhere else in shard 19).
- **Why a finding:** Per `rules/specs-authority.md` MUST Rule 5b sibling re-derivation discipline, the additive spec `specs/mvp-build-sequence.md` MUST be re-derived against the source primitive shard. Drift between the spec and the primitive shard creates a permanent confusion surface — the next session reads `specs/mvp-build-sequence.md` and gets a subcommand list that disagrees with shard 19's own §3.4 table.
- **Recommended fix:** At /todos, before the build phase begins, reconcile the 11-subcommand list. Source-of-truth is shard 19 § 3.4. Update `02-plans/01-build-sequence.md` line 263 + `specs/mvp-build-sequence.md` line 128 to match shard 19's actual subcommand names (`chat` not `boundaries`; `budget status` exists; `mobile-pair`/`enterprise-deploy` are nowhere in shard 19 and should be replaced with `upgrade` + `uninstall --destroy-vault` per plan 03 line 729). Note: spec edit per `rules/specs-authority.md` MUST Rule 5b is required — but `specs/mvp-build-sequence.md` is itself an additive spec from this Phase 01 cycle and the only consumer is internal; the sibling-sweep cost is bounded.

---

### 3.2 R1-M-02 — `02-plans/02-test-strategy.md` does NOT explicitly exercise the legacy `chat_async()` substrate that shard 13 §7 HOLD rationale depends on

- **Severity:** MED
- **Surface:** `02-plans/02-test-strategy.md` (full doc) vs `01-analysis/13-model-adapter-implementation.md` § 7 lines 321–329.
- **Finding:** Shard 13 § 7.1 HELD the chat-completion substrate finding as MED-not-HIGH on the basis that "we are using the supported alternative pattern (legacy provider chat) that exists." The HOLD is conditional on the legacy `kaizen.providers.llm.<provider>.chat_async()` path being exercised in tests — without exercise, the implementation could silently re-implement chat instead of using the legacy substrate (a workaround per `rules/zero-tolerance.md` Rule 4). `grep -in "chat_async\|kaizen.providers" 02-plans/02-test-strategy.md` returns ZERO matches. The plan's EC-1 / EC-3 Tier 2 tests reference `EnvoyModelRouter.for_primitive(...)` but never explicitly assert routing through `chat_async()`.
- **Why a finding:** The HOLD rationale per `02-plans/04-redteam-cycle-plan.md` § 2.5 "verify the disposition note in shard 13's § 7 is reflected in the codebase comment AND the Phase 02+ tracker item is recorded" requires the supported alternative path to be exercised. Per `rules/agents.md` § "Reviewer Prompts Include Mechanical AST/Grep Sweep", a HOLD without grep-able test exercise is fragile.
- **Recommended fix:** Add a Tier 2 wiring test name to `02-plans/02-test-strategy.md` § 2 EC-1 + EC-3 batteries: `tests/integration/test_envoy_model_router_legacy_chat_async_routing.py` — asserts `EnvoyModelRouter.for_primitive("boundary_conversation").chat_async(messages)` routes through the upstream legacy provider's `chat_async()` (mock the `kaizen.providers.llm.<provider>.chat_async` to assert call signature, NOT mock the `LlmClient` abstraction). Note: this is a Tier 2 test where mocking the FFI boundary is BLOCKED per `rules/testing.md` § Tier 2; the assertion is on the routing pattern, not the response. Also reference shard 13 §6.1's table of per-provider wiring tests as the load-bearing exercise.

---

### 3.3 R1-M-03 — Plan 03 `__init__.py` re-export missing the `EnvoyLedger` typed-error class hierarchy

- **Severity:** MED
- **Surface:** `02-plans/03-package-skeleton.md` § 2.2 lines 461–491 (`__init__.py` re-exports).
- **Finding:** `02-plans/03-package-skeleton.md` § 2.2 re-exports 12 facade classes via `__all__` but does NOT re-export the typed-error classes from any primitive (the 24 envelope errors, the 8 ledger errors, the 11 channel errors, the 9 Shamir errors, etc.). Per `rules/orphan-detection.md` MUST Rule 6 ("Module-scope public imports appear in `__all__`"), if a downstream consumer (e.g. `envoy/cli.py` doing `from envoy import LedgerHaltedError`) imports a typed error at the package facade level, that error MUST be in `__all__`. Plan 03 elides this; the design implies "errors are imported through the submodule" but `envoy/cli.py` per § 2.1 does NOT import from submodules — it imports facades. Catching typed errors from inside CLI handlers therefore goes through `from envoy.ledger.errors import LedgerHaltedError` etc., which is a viable pattern but is NOT what the package skeleton § 2.2 names as the orphan-discipline contract.
- **Why a finding:** The `from envoy.<primitive>.errors import` pattern is correct, but plan 03 is ambiguous about whether typed errors are part of the public API. Per `rules/zero-tolerance.md` Rule 6 (implement fully), the catch-block pattern in `envoy/cli.py` MUST be pinned. Either: (a) typed errors are public API, all error names go into `envoy.__init__.__all__`, OR (b) typed errors are accessed via submodule, plan 03 § 2.2 explicitly notes "typed errors imported via `envoy.<primitive>.errors` submodule, NOT re-exported at package level." Without the pin, /implement may make either choice and `/redteam` round 2 surfaces the drift.
- **Recommended fix:** In `02-plans/03-package-skeleton.md` § 2.2, add a sentence: "Typed errors per primitive are imported via `from envoy.<primitive>.errors import <ErrorClass>`; they are NOT re-exported at package level. The 12 facades in `__all__` above are the package-facade contract; error class names are intentionally scoped to the submodule namespace to avoid `__all__` bloat." OR alternatively: add the typed errors to `__all__`.

---

### 3.4 R1-M-04 — Tenant-isolation Rule 1 sweep: not every primitive's plan 03 module names a `principal_id`-keyed cache/audit row (forward-compat for Phase 03)

- **Severity:** MED
- **Surface:** `02-plans/03-package-skeleton.md` § 2 (envoy/ Python package layout); cross-references shards 5 § 3.2, 6 § 3.2 #10, 11 § 3.2 #5, 12 § 3.1, 14 § 3.1 #2 — these primitive shards explicitly call out `principal_id` keying. But shards 8 (Boundary Conversation), 9 (Authorship), 10 (Grant Moment), 16 (Channel adapters), 17 (Heartbeat stubs) do NOT explicitly enumerate the `principal_id` dimension on every persistence touch in plan 03's directory tree.
- **Finding:** The skeleton is silent about whether (e.g.) `envoy/grant_moment/cascade.py`'s cascade-revocation events carry a `principal_id` dimension on the Ledger row, or whether `envoy/authorship/score.py`'s posture-state snapshot is keyed by `principal_id`. The shard-level docs handle this (shard 5 explicitly calls it out; shard 9 implies via Trust store dependency); but plan 03 as a CONSOLIDATED layout MUST surface the rule once, not push it back to each primitive shard.
- **Why a finding:** Per `rules/tenant-isolation.md` Rule 1 + Rule 2, every persistence touch MUST carry the `principal_id` dimension from day 1. The MUST is at the implementation surface — every cache key, every audit row, every metric label. A consolidated package skeleton that doesn't surface this rule once for ALL primitives forces /implement-time agents to grep across 16 primitive shards to recover the rule. Risk: a Phase 01 primitive that doesn't currently persist (e.g. `envoy/grant_moment/orchestrator.py` may have ephemeral state) ships without the dimension; Phase 03 multi-principal refactor exposes the gap.
- **Recommended fix:** Add a §5.1 "Tenant-isolation discipline applied to this skeleton" subsection to `02-plans/03-package-skeleton.md` § 5 listing each primitive's principal_id-keyed surface (drawing from per-shard §§3 already; this is consolidation, not re-derivation). Cross-reference the rule once. Consumers (/implement, /redteam round 2) read the consolidated rule, not 16 shard sections.

---

### 3.5 R1-M-05 — `02-plans/03-package-skeleton.md` § 2 omits `envoy/observability/` module path despite emit-side observability mandate

- **Severity:** MED
- **Surface:** `02-plans/03-package-skeleton.md` § 2 vs `rules/observability.md` (cited indirectly in shard 12 § 7.3 LOW disposition: "emit telemetry"; shard 16 § 3 emits `system_error` Ledger entries).
- **Finding:** Plan 03 § 2 (Python package layout) names 13 primitive sub-packages (envelope, ledger, trust, runtime, boundary_conversation, grant_moment, authorship, daily_digest, budget, shamir, connection_vault, model, channels, heartbeat). It does NOT name an `envoy/observability/` or `envoy/telemetry/` module. Yet shards 11, 12, 13 reference observability counters, telemetry emit, and metric labels. Without a designated observability module, each primitive emits its own counter format — drift surface.
- **Why a finding:** Per `rules/observability.md` Mandatory Log Points + per `rules/agents.md` Integration Hygiene checklist ("Every integration point logs intent + result with correlation ID"), Phase 01 primitives MUST emit observable telemetry. The package skeleton as-is doesn't pin where this telemetry lives. /implement-time discovery: each primitive shard mentions emit in §3 / §5 but the skeleton's directory tree has no canonical home.
- **Recommended fix:** Add `envoy/observability/` to `02-plans/03-package-skeleton.md` § 2 with `metrics.py` (counter / histogram registry) + `tracing.py` (correlation-ID propagation) modules. Cross-reference `rules/observability.md`. Phase 01 Tier 2 tests verify each primitive's observability emits (currently not in `02-plans/02-test-strategy.md`).

---

### 3.6 R1-M-06 — Plan 03 re-export list cites `EnvoyModelRouter` from `envoy.model.router` but the primitive shard 13 § 4 names module `envoy/model/router.py` consistently — verify package-name capitalization

- **Severity:** MED (terminology drift, not load-bearing)
- **Surface:** `02-plans/03-package-skeleton.md` § 2.2 line 475 (`from envoy.model.router import EnvoyModelRouter`); `01-analysis/13-model-adapter-implementation.md` § 4 (`envoy/model/router.py`).
- **Finding:** Both docs use `envoy.model` as the module name; the spec name in `specs/model-adapter.md` references "Model adapter" (the human-readable name). The package-skeleton's rendering is consistent; the user-flow docs and the build-sequence cite "Model adapter" as the primitive name. No actual drift detected on inspection — the module is `envoy.model` (lowercase singular), the human-readable primitive name is "Model adapter", the class is `EnvoyModelRouter`.
- **Why a finding:** Cross-checking surfaced this as a candidate drift, but on full re-derivation the consistency holds. Logging here as MED-but-no-action because the audit protocol per `02-plans/04-redteam-cycle-plan.md` § 8 requires false-candidate findings to be surfaced (transparency: the auditor checked X, found nothing).
- **Recommended fix:** None required. Mark as candidate-not-confirmed.

---

### 3.7 R1-L-01 — `02-plans/03-package-skeleton.md` § 1.1 toml block is descriptive-not-actionable (acknowledged)

- **Severity:** LOW
- **Surface:** `02-plans/03-package-skeleton.md` § 1.1 lines 39–112 (the `pyproject.toml` block).
- **Finding:** The block reads "the provisional shape — pin values per shard 19 § 3.1" — i.e., the plan does NOT inline shard 19's verbatim pyproject content but acknowledges it lives there. This is intentional (avoids re-derivation drift) but means /implement-time agents must read both docs.
- **Why a finding:** LOW; not blocking. Plan 03 § 1.1 line 38 is explicit ("this plan does NOT re-derive"). Acceptable.
- **Recommended fix:** None.

---

### 3.8 R1-L-02 — Journal entry 0002 cites "12-of-13 closed" but #596 was always OPEN — minor wording polish

- **Severity:** LOW
- **Surface:** `journal/0002-DISCOVERY-upstream-readiness-improved.md` line 22 ("12 of 13 CLOSED between 2026-04-24 and 2026-04-26").
- **Finding:** The journal claim "12 of 13 CLOSED" is correct counting only Phase 00 issues #594-#606 — line 24 confirms #596 is the single still-OPEN issue. The wording is consistent. No issue at all.
- **Why a finding:** LOW; non-action; surfaced as part of the closed-ISS mechanical sweep transparency.
- **Recommended fix:** None.

---

### 3.9 R1-L-03 — `specs/independent-verifier.md` cites #752 lightning quarantine indirectly but #752 was closed 2026-04-30 — disposition still holds because the EXCLUSION is from the dependency tree, not from the closure

- **Severity:** LOW
- **Surface:** `specs/independent-verifier.md` (does NOT cite #752 — the citation is in shard 19 + plan 03 + journal 0002).
- **Finding:** Mechanical sweep #9 (`kailash-ml` exclusion verification) re-confirmed: `~/repos/loom/kailash-py/pyproject.toml` at HEAD shows `kaizen = ["kailash-kaizen>=2.7.5", "kaizen-agents>=0.9.3"]` (line 88-91); `nexus = ["kailash-nexus>=2.1.1"]` (line 86); `shamir = ["shamir-mnemonic>=0.3"]` (line 106). NEITHER `kaizen` NOR `nexus` NOR `shamir` extras transitively pull `kailash-ml`. Shard 19 claim verified at HEAD. The note is that #752 (the lightning-package-quarantine-on-PyPI issue) has CLOSED at 2026-04-30T17:22:24Z (`gh` query at audit time) — this does NOT change Phase 01 disposition because `kailash-ml` is still NOT in `pip install kailash[shamir,nexus,kaizen]` regardless.
- **Why a finding:** LOW; the closure of #752 might be construed as "lightning issue resolved → Envoy can include kailash-ml" but that misreads the disposition. Phase 01 deliberately excludes `kailash-ml` regardless of #752 status (no Phase 01 ML need).
- **Recommended fix:** None. Surfaced for transparency.

---

### 3.10 R1-L-04 — Audit-mode discipline confirmation: per `rules/testing.md` § Audit Mode Rules, this audit re-derived every claim from scratch

- **Severity:** LOW (process confirmation)
- **Surface:** This audit doc.
- **Finding:** Per `rules/testing.md` § Audit Mode Rules, the auditor MUST NOT trust `.spec-coverage` or any prior round's audit output. This audit re-read every primitive shard's §7, the 4 plans, the 8 flows, the 22-spec-gap doc, the 2 additive specs, the 3 journal entries, the upstream `~/repos/loom/kailash-py/...` source for cited symbols, and ran live `gh issue view` for every cited issue number. This is the round-1 baseline; round 2 (if triggered by 0/0) MUST re-derive again per the same discipline.
- **Why a finding:** LOW; process-discipline transparency.
- **Recommended fix:** Round 2 follows the same protocol per `02-plans/04-redteam-cycle-plan.md` § 4.1.

---

## 4. Mechanical sweep results

### Sweep #1 — Spec compliance verification (per `skills/spec-compliance/SKILL.md`)

PASS. Every primitive shard cites its source spec by path + section; shard re-reads surface verified cited sections still exist at HEAD in `/Users/esperie/repos/dev/envoy/specs/` (40 spec files enumerated). No HIGH-severity drift: shard 4 cites `specs/envelope-model.md` § Schema/Algorithms/Error taxonomy (frozen, present); shard 5 cites `specs/trust-vault.md` + `specs/trust-lineage.md` (both present); shard 6 cites `specs/ledger.md` § entry envelope schema lines 14-34 + 47-91 (frozen at HEAD); shard 7 cites `specs/ledger.md` lines 588-592 + 643-644; shard 8 cites `specs/boundary-conversation.md`; shard 11 cites `specs/daily-digest.md` § Schedule/Content/Schema/Open questions; shard 12 cites `specs/budget-tracker.md` § Ceilings/Reserve/Threshold/Open questions; shard 13 cites `specs/model-adapter.md` § Purpose/Provider-risk/Response filter/Multi-provider/Cross-domain/Error; shard 14 cites `specs/connection-vault.md`; shard 15 cites `specs/shamir-recovery.md`; shard 16 cites `specs/channel-adapters.md` + `specs/a2a-messaging.md`; shard 17 cites `specs/foundation-health-heartbeat.md`; shard 18 cites `specs/runtime-abstraction.md`; shard 19 cites `specs/distribution.md`; spec-compliance Pass.

### Sweep #2 — Orphan-detection (`rules/orphan-detection.md` MUST Rules 1 + 2 + 2a; `facade-manager-detection.md` MUST Rules 1+2+3)

PASS. Plan 03 § 2.2 enumerates the 12 facade re-exports; § 5 explicitly cites `rules/orphan-detection.md` Rules 1, 2, 2a, 6 + `rules/facade-manager-detection.md` Rules 1-3 with disposition. Plan 02 § 3.1 + 3.2 ship the wiring-test naming + crypto-pair round-trip discipline. Each Tier 2 wiring test path matches `tests/tier2/test_<lowercase>_wiring.py` per Rule 2. No facade enumerated in §2.2 lacks a corresponding wiring test in plan 02 § 2 EC-1..EC-9 batteries.

### Sweep #3 — Closed-ISS still-closed verification

PASS. Live `gh issue view` queries against `terrene-foundation/kailash-py` for cited issue numbers:

- #594 (envelopes): CLOSED ✓
- #595 (cascade docstring): CLOSED ✓
- #596 (TieredAuditDispatcher): **OPEN** ✓ (matches journal/0002 baseline; shard 6 § 2.4 explicitly handles this with sunset clause)
- #597 (PostureStore): CLOSED ✓
- #602 (OrchestrationRuntime): CLOSED ✓
- #603 (BudgetTracker threshold callback): CLOSED ✓
- #604 (algorithm_id schema): CLOSED ✓
- #605 (PACT N4/N5 conformance): CLOSED ✓
- #606 (Shamir SLIP-0039): CLOSED ✓
- #673 (websocket Origin allowlist): CLOSED ✓
- #707, #711 (df.transaction): CLOSED ✓
- #731 (TraceEvent timestamp): CLOSED ✓
- #736, #740, #761, #762, #763, #764, #788, #790, #791 (Kaizen LLM): CLOSED ✓
- #752 (lightning quarantine): CLOSED 2026-04-30 — does NOT change Phase 01 `kailash-ml` exclusion (R1-L-03 above).
- #756, #757 (Unicode byte-vector pin): CLOSED ✓

NO surprise re-opens.

### Sweep #4 — Upstream module symbol verification

PASS. Read `~/repos/loom/kailash-py/src/kailash/...` at HEAD:

- `trust/pact/envelopes.py`: `intersect_envelopes` line 336 ✓; `RoleEnvelope` line 419 ✓; `validate_tightening` line 438 ✓; `TaskEnvelope` line 690 ✓; `compute_effective_envelope` line 716 ✓.
- `trust/signing/crypto.py`: EXISTS ✓
- `trust/signing/algorithm_id.py`: EXISTS ✓ (#604 scaffold, lines 1-162 per shard 5 § 2.2)
- `trust/chain_store/sqlite.py`: EXISTS ✓
- `trust/posture/posture_store.py`: EXISTS ✓
- `trust/revocation/cascade.py`: `RevocationResult` line 71 ✓; `cascade_revoke` line 154 ✓
- `trust/audit_store.py`: EXISTS ✓ (the cited `kailash.trust.audit.AuditStore` actually lives at `kailash.trust.audit_store` per inspection — minor module-path drift in shard 6's prose but not load-bearing)
- `trust/vault/shamir.py`: EXISTS ✓; `ShamirRitual` line 145, `generate` line 222, `reconstruct` line 317 (shard 15 cited)
- `trust/vault/backup.py`: EXISTS ✓ (`back_up_vault_key` line 58 — shard 15 § 7.3 disposition correct)
- `packages/kailash-kaizen/src/kaizen/llm/deployment.py`: EXISTS ✓
- `packages/kailash-kaizen/src/kaizen/orchestration/runtime.py`: EXISTS ✓
- `packages/kailash-kaizen/src/kaizen/providers/llm/anthropic.py` `chat_async` line 211 ✓; `openai.py` `chat_async` line 312 ✓ — the legacy chat substrate shard 13 §7.1 HOLD rationale depends on EXISTS at HEAD.

Minor module-path note: shard 6 § 3.1 says "wraps upstream `AuditStore` from `kailash.trust.audit`" — actual upstream path is `kailash.trust.audit_store` (single module, not a sub-package). Plan-time wiring should verify the import; this is a /implement-time correction, not an /analyze finding. Logged as part of the mechanical sweep, NOT a separate finding.

### Sweep #5 — Gap-analysis 22 timezone HIGH disposition consistency

PASS. Cross-checked Option A disposition across:

- Shard 11 (Daily Digest) § 7.1: "Phase 01 ships **Option A** as the zero-cost default; the apscheduler `CronTrigger` accepts `timezone='UTC'`." ✓
- Shard 12 (Budget tracker) § 7.1: Recommendation Option B but Phase 01 disposition Option A; deferred to shard 22. ✓
- Flow 04 (`03-user-flows/04-daily-digest-flow.md`) line 10: "Phase 01 ships **Option A (UTC fire)** for both budget reset (shard 12) AND digest schedule (shard 11)." ✓
- Flow 08 (`03-user-flows/08-posture-ratchet-flow.md`) line 10: "Phase 01 ships **Option A (UTC)** consistently across budget reset, daily digest, and posture cooling-off." ✓
- Spec gap analysis 22 § 4 (the consolidated HIGH; "Option A — UTC-only, Phase 01-acceptable, 0 sessions" + recommendation "Option B" with human decision deferred to shard 25). ✓

ALL FOUR consumers consistent. The shard 22 recommendation is Option B; the per-shard Phase 01 dispositions all default to Option A pending shard 25 human decision. No drift.

### Sweep #6 — HIGH-candidate HELD verification (shard 13 chat-completion substrate)

PASS — with R1-M-02 caveat. Shard 13 §7.1 HOLD rationale is sound: per `rules/zero-tolerance.md` Rule 4, the legacy `kaizen.providers.llm.<provider>.chat_async()` IS the supported alternative pattern, NOT a workaround. Live grep at `~/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/providers/llm/anthropic.py` line 211 + `openai.py` line 312 + `ollama.py` (verified) confirms the substrate exists at HEAD. The HOLD is structurally valid.

CAVEAT (R1-M-02): plan 02 test-strategy does NOT explicitly grep for `chat_async` in any test path. Risk is low (shard 13 §6 has 5+ Tier 2 wiring tests against real providers), but the HOLD-validation discipline per `02-plans/04-redteam-cycle-plan.md` § 2.5 should surface in plan 02 with a one-line test name.

### Sweep #7 — Tenant-isolation Rule 1 (`principal_id` dimension on every persistence touch)

PASS — with R1-M-04 caveat. Spot-check across primitives:

- Shard 5 (Trust store) § 3.2: explicit `_key(principal_id, suffix)` helper raising `PrincipalRequiredError` on missing — Rule 1 + Rule 2 satisfied at design time. ✓
- Shard 6 (Ledger) § 3.1: `tenant_id` plumbed through `EnvoyLedger.__init__`; the `format_record_id_for_event` helper applied at single-emission point. ✓
- Shard 11 (Daily Digest) § 3.2: `digest_id` keyed `principal_genesis_id` per spec § Schema; pause-state Trust-store-backed (per-principal). ✓
- Shard 12 (Budget) § 3.1: `tracker_id = f"envoy:v1:{principal_id}:{ceiling_window}:{period_key}"` — Rule 1 satisfied. ✓
- Shard 14 (Connection Vault) § 3.1 #2: `principal_genesis_id` field per shard. ✓

Where the rule is NOT explicitly named: shards 8 (Boundary Conversation), 9 (Authorship Score), 10 (Grant Moment), 16 (Channel adapters). These primitives DO inherit principal_id via composition (BC depends on Trust store; GM depends on Ledger; Channels depend on Trust store) — so the rule transitively holds. R1-M-04 surfaces this as a documentation-clarity MED, not a structural HIGH.

### Sweep #8 — Event-payload classification (`format_record_id_for_event` at single emission point)

PASS. Shard 6 § 3.1 plan 02 § 3.4: every Ledger entry that surfaces on the `DomainEvent` bus routes `record_id` through `format_record_id_for_event` at the SINGLE EMISSION POINT (`envoy/ledger/event_emitter.py` per plan 03 § 2). Shard 11 § 1 line 26 cross-references "classified `record_id` and `principal_genesis_id` values routed through `format_record_id_for_event`." Shard 16 § 3.2 #3 cites Rule 1 + Rule 2 explicitly for the channel-error emit path. NO drift.

### Sweep #9 — `kailash-ml` exclusion verification

PASS. `pip install kailash[shamir,nexus,kaizen]>=2.13.4` transitively closes to:

- `kailash` (root, 2.13.4)
- `kailash-kaizen>=2.7.5` (extras: kaizen)
- `kaizen-agents>=0.9.3` (extras: kaizen)
- `kailash-nexus>=2.1.1` (extras: nexus)
- `shamir-mnemonic>=0.3` (extras: shamir)

NONE of these declare `kailash-ml` as a transitive dep. Live verification at `~/repos/loom/kailash-py/pyproject.toml` HEAD lines 79-115 + sub-package pyproject inspections. Shard 19 § 2.3 claim VERIFIED. The lightning quarantine #752 is now closed but irrelevant (Phase 01 doesn't pull `kailash-ml` regardless).

---

## 5. Round-2 trigger assessment

Per `02-plans/04-redteam-cycle-plan.md` § 3 (round-1-too-clean adversarial trigger): if round 1 returns 0 CRIT + 0 HIGH, the auditor MUST run round 2 with adversarial framing on the shards whose §7 surfaced 0 ambiguities (shards 4, 5, 17 — "too clean").

**Round 1 result: 0 CRIT + 0 HIGH.** The convergence-baseline gate is met for round 1.

### 5.1 Round 2 MUST run with adversarial framing on shards 4 + 5 + 17

Per `02-plans/04-redteam-cycle-plan.md` § 3.2 the round-2 adversarial prompts are:

**Shard 4 — Envelope compiler:**

- "Find a sequence of `compile()` calls where the second call's input is byte-identical to the first call's input but the resulting `EnvelopeConfig.content_hash` differs."
- "Find an attacker-controlled `EnvelopeConfigInput` field that, when fed through NFC + JCS, produces a `canonical_bytes` that fails `intersect_envelopes` round-trip with byte-equality."
- "If a Foundation cross-domain-rules registry version bump is published, does ANY existing `EnvelopeConfig`'s evaluation behavior change?"

**Shard 5 — Trust store + lineage:**

- "Construct a sequence of `record_delegation` + `cascade_revoke` calls where `verify_cascade_complete` returns True but at least one descendant is NOT in `revoked_agents`."
- "Find a code path where `principal_id` is silently defaulted to a placeholder."
- "Argon2id timing — is the parameter set fast enough on a 2020-class laptop that an attacker-side brute force is feasible?"

**Shard 17 — Foundation Health Heartbeat (DECISION shard):**

- "The de-scope decision ships ~100 LOC of stubs only. Verify ZERO production code path in `envoy/` calls `envoy.heartbeat.*` modules in Phase 01."
- "Verify the 21-flag schema validator stub does NOT silently accept arbitrary flag schemas (a stub that accepts any input is fake-implementation per `rules/zero-tolerance.md` Rule 2)."
- "Verify the `consent_ledger` entry type stub does NOT register the entry type in the Ledger taxonomy in Phase 01."

Round 2 is launched after round 1's MED findings (R1-M-01 through R1-M-06) are dispositioned. Per `02-plans/04-redteam-cycle-plan.md` § 4.4: MED / LOW fixes do NOT reset the convergence counter; round 2 may proceed with R1's MEDs still open OR resolved.

### 5.2 Why the trigger holds even though round 1 surfaced MEDs

The convergence gate per `02-mvp-objectives.md` EC-6 is "0 CRITICAL findings + 0 HIGH findings × 2 consecutive `/redteam` rounds." MED findings are NOT included in the gate (per `02-plans/04-redteam-cycle-plan.md` § 1.4 + § 4.4). The 6 MED findings R1-M-01 through R1-M-06 are advisory; the convergence gate per Round 1 is met (0 CRIT + 0 HIGH).

The "too clean" trigger in § 3.1 specifically gates whether round 2 must use adversarial framing — which per § 3.3 "is NOT optional when round 1 returns 0/0." Round 2 MUST run with adversarial prompts on shards 4 + 5 + 17 regardless of MEDs surfaced in round 1.

---

## 6. Convergence gate status

- **Round 1 result:** 0 CRIT + 0 HIGH + 6 MED + 4 LOW. **CONVERGENCE-BASELINE GATE MET.**
- **Round 2 trigger:** REQUIRED — adversarial framing on shards 4 + 5 + 17 per § 5.1 above.
- **Convergence gate:** met after round 2 ALSO returns 0/0 with adversarial framing AND no implementation work between rounds (only fixes for MED/LOW).
- **Phase 01 release predicate:** the 9 EC gates (EC-1..EC-9) per `02-mvp-objectives.md` are ALL still required. EC-6 (this redteam cycle) is the gate this audit serves. The other 8 EC gates are downstream of /implement.

---

## 7. Per-finding tracker (carry-forward at /todos)

| ID      | Sev | Surface                      | Disposition                                         | Owner          |
| ------- | --- | ---------------------------- | --------------------------------------------------- | -------------- |
| R1-M-01 | MED | Plan 01 + spec, plan 03      | /todos: reconcile 11-subcommand list to shard 19    | /todos planner |
| R1-M-02 | MED | Plan 02 test-strategy        | /todos: add Tier 2 chat_async wiring test name      | /todos planner |
| R1-M-03 | MED | Plan 03 § 2.2 **all**        | /todos: pin error-import pattern                    | /todos planner |
| R1-M-04 | MED | Plan 03 § 2 layout           | /todos: add §5.1 tenant-isolation consolidated rule | /todos planner |
| R1-M-05 | MED | Plan 03 § 2 missing module   | /todos: add envoy/observability/                    | /todos planner |
| R1-M-06 | MED | Module/class naming          | NONE — false-candidate verified consistent          | (closed)       |
| R1-L-01 | LOW | Plan 03 § 1.1                | NONE — acknowledged-not-actionable                  | (closed)       |
| R1-L-02 | LOW | Journal 0002                 | NONE — wording correct                              | (closed)       |
| R1-L-03 | LOW | spec/independent-verifier.md | NONE — disposition holds                            | (closed)       |
| R1-L-04 | LOW | This audit doc               | NONE — process-discipline confirmation              | (closed)       |

---

## 8. Cross-references

### Source docs audited

- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/04-envelope-compiler-implementation.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/06-envoy-ledger-implementation.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/07-independent-verifier-design.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/09-authorship-score-implementation.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/10-grant-moment-implementation.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/11-daily-digest-implementation.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/12-budget-tracker-implementation.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/13-model-adapter-implementation.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/14-connection-vault-implementation.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/15-shamir-recovery-implementation.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/16-channel-adapters-implementation.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/17-foundation-health-heartbeat-decision.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/18-runtime-abstraction-stub.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/19-pipx-distribution-architecture.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/01-analysis/22-spec-gap-analysis.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/02-plans/01-build-sequence.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/02-plans/02-test-strategy.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/02-plans/03-package-skeleton.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/02-plans/04-redteam-cycle-plan.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/03-user-flows/01-install-flow.md` … `/08-posture-ratchet-flow.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/journal/0002-DISCOVERY-upstream-readiness-improved.md`
- `/Users/esperie/repos/dev/envoy/workspaces/phase-01-mvp/journal/0003-GAP-budget-ceiling-timezone.md`
- `/Users/esperie/repos/dev/envoy/specs/independent-verifier.md`
- `/Users/esperie/repos/dev/envoy/specs/mvp-build-sequence.md`

### Rules consulted

- `.claude/rules/specs-authority.md` MUST Rule 4 + Rule 5b (re-derivation discipline; additive specs only)
- `.claude/rules/testing.md` § Audit Mode Rules + § 3-Tier
- `.claude/rules/orphan-detection.md` MUST Rules 1, 2, 2a, 5, 5a, 6, 7
- `.claude/rules/facade-manager-detection.md` MUST Rules 1, 2, 3
- `.claude/rules/tenant-isolation.md` Rules 1-5
- `.claude/rules/event-payload-classification.md` Rules 1-4
- `.claude/rules/zero-tolerance.md` Rules 1-6
- `.claude/rules/agents.md` § "Reviewer Prompts Include Mechanical AST/Grep Sweep"
- `.claude/rules/security.md` § Multi-Site Kwarg Plumbing
- `.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget

### Forward references

- Shard 24 — round 2 (re-derivation; adversarial framing on shards 4 + 5 + 17 per § 5.1; convergence verdict)
- Shard 25 — closure (Option A vs Option B human decision; consume both rounds' verdicts)

---

## 9. Round-1 closure

**N CRIT = 0; N HIGH = 0; N MED = 6; N LOW = 4.** Round 1 establishes the convergence-baseline gate (0/0). Round 2 MUST follow with adversarial framing on shards 4, 5, 17 per `02-plans/04-redteam-cycle-plan.md` § 3 — the trigger is non-optional when round 1 returns 0 CRIT + 0 HIGH. Convergence is met when round 2 ALSO returns 0/0 with the adversarial sweep applied AND no implementation work landed between rounds (MED/LOW fixes are allowed).
