# Round 2 — Phase 01 MVP Red Team Comprehensive Audit (ADVERSARIAL)

**Document role:** Shard 24 of /analyze. Round-2 redteam audit of the same 16 primitive deep-dive shards (4–19), 4 plan docs, 8 user-flow docs, spec-gap analysis (shard 22), the 2 additive new specs, and the 3 journal entries — with **adversarial framing applied to shards 4 + 5 + 17** per `02-plans/04-redteam-cycle-plan.md` § 3 (round-1-too-clean trigger fired because Round 1 returned 0 CRIT + 0 HIGH).

**Date:** 2026-05-03 (shard 24 of /analyze; round 2 of N).
**Status:** DRAFT — convergence verdict for EC-6 (the redteam cycle gate per `02-mvp-objectives.md` line 91).
**Discipline:** Re-derive from scratch. AST/grep verification per `skills/spec-compliance/SKILL.md`. Cite by path + line. Do NOT modify any analysis/plan/flow doc; the audit OUTPUT is the only deliverable. Per `rules/testing.md` § Audit Mode Rules, never trust round 1's findings table at face value — re-classify everything.

---

## 1. Round 2 scope + adversarial framing applied

### 1.1 Audited surface (identical to round 1)

- 16 primitive deep-dive docs: `01-analysis/{04..19}-*-implementation.md` and `01-analysis/{07,17,18}-*-decision/design.md`
- 4 plan docs: `02-plans/01-build-sequence.md`, `02-plans/02-test-strategy.md`, `02-plans/03-package-skeleton.md`, `02-plans/04-redteam-cycle-plan.md`
- 8 user-flow docs: `03-user-flows/{01..08}-*.md`
- Spec-gap analysis: `01-analysis/22-spec-gap-analysis.md`
- 2 additive specs: `specs/independent-verifier.md`, `specs/mvp-build-sequence.md`
- 3 journal entries

### 1.2 Adversarial framing applied to shards 4 + 5 + 17

Per `02-plans/04-redteam-cycle-plan.md` § 3.2, round 2 added the adversarial prompts named in § 3.2 above mechanical sweeps. The hostile-reviewer prompts surfaced 2 HIGH findings the round-1 mechanical-only sweep did not flag. Round 1's `0 CRIT + 0 HIGH` result is now **partially refuted** by adversarial framing — exactly the scenario `02-plans/04-redteam-cycle-plan.md` § 3.3 names ("the structural defense against 'the analysis was too clean because the analyst was too aligned with the implementer'").

### 1.3 Mechanical sweeps re-run (per § 6 of redteam-cycle plan)

All 9 sweeps re-run from scratch:

1. Spec compliance verification (`skills/spec-compliance/SKILL.md`) — re-derived
2. Orphan-detection sweep — re-derived
3. Closed-ISS still-closed verification — live `gh` queries (24 issues)
4. Upstream module symbol verification at HEAD — re-grepped
5. Gap-analysis 22 disposition consistency (timezone Option A) — re-checked
6. HIGH-candidate HELD verification (shard 13) — re-checked
7. Tenant-isolation Rule 1 sweep — re-checked
8. Event-payload classification sweep — re-checked
9. `kailash-ml` exclusion verification — re-checked

---

## 2. Findings classified by severity

### 2.1 CRIT — 0

### 2.2 HIGH — 2

### 2.3 MED — 5

### 2.4 LOW — 3

Total: **10 findings**. Two HIGH findings reset the convergence counter (per `02-plans/04-redteam-cycle-plan.md` § 4.3). Round 3 required after fixes.

---

## 3. Findings detail

### 3.1 R2-H-01 — Algorithm-identifier wire-shape MISMATCH between producer (shard 5) and Independent Verifier (shard 7 / `specs/independent-verifier.md`) — **EC-9 acceptance gate would fail**

- **Severity: HIGH**
- **Surface:**
  - Producer side: `01-analysis/05-trust-store-implementation.md` § 4 line 246 (`record_dict["algorithm_identifier"] = AlgorithmIdentifier().to_dict()`); upstream `~/repos/loom/kailash-py/src/kailash/trust/signing/algorithm_id.py` line 102–108 (`to_dict()` returns `{"algorithm": "ed25519+sha256"}` — 1-KEY FORM).
  - Verifier side: `specs/independent-verifier.md` lines 35–36 (`"algorithm_identifier": {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}` — 3-KEY FORM); shard 7 `01-analysis/07-independent-verifier-design.md` § 3.3 line 124 (proposes `"algorithm_identifier": {...}` underspecified, but shard 7 § 1.1 references `specs/ledger.md` lines 588–592 which the verifier spec then formalizes as the 3-key form).
  - Source spec: `specs/trust-lineage.md` line 24 (`"algorithm_identifier": {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}`); `specs/ledger.md` line 31 (`"algorithm_identifier": {...}` per cross-reference, format as in `specs/trust-lineage.md`).

- **Adversarial framing finding:** Shard 5 § 7.2 logged this mismatch as **LOW** in round 1 ("the Envoy adapter MUST track the resolved wire shape after mint ISS-31 lands and update `_with_algorithm_id()` accordingly; this is a tracked technical-debt item, not a Phase 01 blocker"). Round 1's mechanical sweep DID NOT catch the cross-shard implication: **shard 7 (Independent Verifier) consumes the 3-key form per the verifier spec; shard 5 (Trust Store) writes the 1-key form per the upstream scaffold.** A producer-verifier wire-shape divergence is the EXACT failure mode EC-9 ("Independent verifier passes EC-4 tampering battery against Envoy-produced bundles") guards against — and `02-mvp-objectives.md` line 128 makes EC-9 a **non-degradable** Phase 01 ship predicate.

- **Why a HIGH finding (re-classification from round 1 LOW):**
  1. **EC-9 ship-predicate impact.** Per `02-mvp-objectives.md` § 4, Phase 01 ships when `EC-1 ∧ EC-2 ∧ ... ∧ EC-9`. EC-9 is `02-plans/02-test-strategy.md` § "EC-9 — Independent ledger verifier ships separately-codebased" lines 281–301. The verifier consumes the bundle byte-stream; the bundle's `algorithm_identifier` is the 1-key upstream form on the producer side and the 3-key form on the verifier side. **At verification time, the verifier will reject every Envoy-produced record OR (worse) silently default to the spec's 3-key form during parsing, producing a hash mismatch on the chain head.** Either failure mode breaks EC-9.
  2. **Specs-authority Rule 6 violation.** Per `rules/specs-authority.md` MUST Rule 6, "deviations from spec require explicit acknowledgment." `specs/trust-lineage.md` line 24 + `specs/independent-verifier.md` line 35 mandate the 3-key form. Shard 5 § 4 line 246 silently uses upstream's 1-key form via `AlgorithmIdentifier().to_dict()`. The deviation is NOT logged as a Rule 6 acknowledgment in the spec; it is logged as a "tracked technical-debt item" in shard 5 § 7.2 — which is exactly the silent-deviation failure pattern Rule 6 BLOCKED rationalizations name.
  3. **Cross-shard sibling re-derivation gap.** Per `rules/specs-authority.md` MUST Rule 5b, every spec edit triggers full-sibling re-derivation. The additive spec `specs/independent-verifier.md` was drafted from shard 7's design; the verifier spec mandates 3-key wire shape. Shard 5 was not re-derived against `specs/independent-verifier.md`'s consumer contract — neither was shard 6 (Ledger), which also uses upstream's `AlgorithmIdentifier` per shard 6 § 4 line 248 (`algorithm_identifier: dict`). The 1-key vs 3-key drift is invisible to per-shard sweeps; only the cross-shard sibling sweep catches it.
  4. **Zero-tolerance Rule 4 violation.** Per `rules/zero-tolerance.md` Rule 4, "no workarounds for core SDK issues." The Envoy adapter MUST emit the spec-mandated 3-key wire form OR — if the upstream SDK genuinely cannot — file a kailash-py issue and pin the issue + minimal repro per Rule 4. The current disposition (silently use upstream's 1-key form, log as "track later") is the BLOCKED rationalization "we'll work around the SDK" the rule explicitly names.
  5. **Round-1 sweep #4 would have caught it with cross-shard discipline.** The round-1 audit's sweep #4 ("Upstream module symbol verification") confirmed `algorithm_id.py` at HEAD; it did not check whether the upstream's wire format matches the spec's wire format. A more rigorous round-1 sweep would have grepped both `specs/trust-lineage.md` and `~/repos/loom/kailash-py/.../algorithm_id.py` for the actual key shape — which is what round 2's adversarial framing made explicit.

- **Recommended fix (BLOCKING for Phase 01 ship):**
  Two acceptable resolutions:
  - **Option A (preferred — preserve spec authority):** Envoy emits the 3-key spec form. The Envoy `_with_algorithm_id()` helper (shard 5 § 4 line 240–247) MUST translate `AlgorithmIdentifier().to_dict()`'s 1-key form into the spec's 3-key form before persistence. Add a `to_spec_form()` helper alongside in shard 5; the helper is the single point of translation. This is structural defense per `rules/specs-authority.md` Rule 4 (read-then-act) — Envoy's wire shape matches the spec, full stop.
  - **Option B (preserve upstream / amend spec):** File a `specs/trust-lineage.md` edit that names BOTH wire forms as valid, with a Phase 01 default of 1-key form, Phase 02 migration to 3-key form pinned via mint ISS-31. This requires `rules/specs-authority.md` MUST Rule 5b sibling sweep across specs/{trust-lineage,ledger,independent-verifier,boundary-conversation,grant-moment,sub-agent-delegation,foundation-health-heartbeat}.md — 7 sibling specs at minimum. **Spec edit cost > Option A code cost.**

  Option A is recommended. The Phase 01 build-sequence plan (`02-plans/01-build-sequence.md`) MUST add a sub-step "Wire-shape translation helper at TrustStoreAdapter.\_with_algorithm_id() → 3-key spec form" before the Trust Store wave-A primitive lands.

  Per `rules/orphan-detection.md` MUST Rule 1, the producer-verifier wire-shape conformance MUST be exercised by a Tier 2 wiring test: `tests/integration/test_producer_verifier_wire_shape_round_trip.py` — produces a record via the Envoy adapter, parses it via the Independent Verifier's bundle parser, asserts byte-identical `algorithm_identifier` dict structure. Plan 02 § "EC-9" battery MUST add this test name.

---

### 3.2 R2-H-02 — Foundation Health Heartbeat de-scope structurally inconsistent: shard 17 §7.3 mandates 21 NO-OP `maybe_record_flag()` hooks across 8 emit primitives; package skeleton + build sequence design 4 modules that RAISE `PhaseDeferredError` on every call — **calling the stub from any production primitive crashes Phase 01**

- **Severity: HIGH**
- **Surface:**
  - Shard 17 specification: `01-analysis/17-foundation-health-heartbeat-decision.md` § 7.3 lines 211–219 ("4 mandatory Phase 01 stubs"), specifically item 4: "Integration-point no-op hooks — at each of the 21 emit sites (Boundary Conversation completion, Daily Digest open, Grant Moment approve/deny, etc.), a single line `self._heartbeat.maybe_record_flag(...)` that calls the stub `HeartbeatClient.maybe_record_flag()` which is a **no-op in Phase 01**. Cost: ~21 lines + a stub class with one method." — emphasis added.
  - Shard 17 § 7.6 lines 236–243 enumerates 8 cross-shard implications: shard 8 (BC) `completed_boundary_conversation` flag; shard 11 (DD) `opened_daily_digest_this_week` flag; shard 10 (GM) 3 flags; shard 9 (AS) 4 flags; shard 12 (BT) 2 flags; shard 16 (Channels) 6 flags; shard 18 (Runtime) 1 flag.
  - Build-sequence plan: `02-plans/01-build-sequence.md` line 144: "**4 module stubs** — `envoy/heartbeat/{star_prio,ohttp,signed_consent,registry}.py` each raising `PhaseDeferredError(\"Heartbeat deferred to Phase 02 entry per de-scope #2\")`."
  - Package skeleton: `02-plans/03-package-skeleton.md` lines 405–409: same 4 modules, each labeled `# PhaseDeferredError stub`.
  - Test strategy: `02-plans/02-test-strategy.md` — `grep -in "heartbeat" 02-plans/02-test-strategy.md` returns ZERO matches. **No wiring test exists for the 4 stub modules; no test exercises the 21 emit-site no-op hooks.**

- **Adversarial framing finding (round-2 plan §3.2 prompt verbatim):** "The de-scope decision ships ~100 LOC of stubs only. Verify ZERO production code path in `envoy/` calls `envoy.heartbeat.*` modules in Phase 01. If ANY call site invokes the stubs, the de-scope is leaky and the stubs raising `PhaseDeferredError` will crash production." Round 2 verifies:
  - Shard 17 § 7.3 line 218 EXPLICITLY mandates 21 production call sites: every emit primitive calls `self._heartbeat.maybe_record_flag(...)`. Per the cross-shard implications (§ 7.6), 8 primitives include this call.
  - The 4 modules in build-sequence + package skeleton ALL raise `PhaseDeferredError` on import or invocation. There is NO Phase 01 stub `HeartbeatClient` class with a `maybe_record_flag()` method that no-ops; the design is "module raises on call."
  - Therefore: if any of the 21 emit sites lands per shard 17 § 7.6 (which cross-shard implications mandate), and the stub modules raise `PhaseDeferredError`, **every emit primitive crashes in Phase 01 production runs**. Boundary Conversation completion → crash. Daily Digest open → crash. Grant Moment approve → crash. Channel adapter activation → crash. The de-scope leaks.

- **Why a HIGH finding (NEW in round 2; not surfaced in round 1):**
  1. **Zero-tolerance Rule 2 violation.** Per `rules/zero-tolerance.md` Rule 2, "fake encryption (stores key, never encrypts), fake transaction (context manager with no BEGIN/COMMIT), fake health (always returns 200), fake classification (decorator that never enforces on read)" are BLOCKED. A stub module that raises `PhaseDeferredError` on every call when production code is supposed to call it as a no-op IS the fake-implementation pattern at the extreme — every call crashes, but the `__init__.py` import succeeds, so it looks present.
  2. **Orphan-detection Rule 1 + Rule 4a violation.** Per `rules/orphan-detection.md` MUST Rule 1, every facade-shape attribute requires a production call site within 5 commits. The 21 production call sites SHOULD exist (per shard 17 § 7.6). Per Rule 4a, "any PR that implements a previously-deferred stub — replacing `NotImplementedError` / empty-body placeholder with a real impl — MUST delete or rewrite every test that asserts the deferred behavior in the same commit." The reverse case is also implicit: a PR that ships a stub that production code MUST CALL must ship a Tier 2 test that exercises the no-op (otherwise the stub's no-op shape is unverified). `02-plans/02-test-strategy.md` has zero coverage of the heartbeat stubs OR the 21 emit sites. **The stub IS the orphan-detection failure mode — present, advertised, with no Tier 2 wiring exercise to prove it actually no-ops.**
  3. **Internal contradiction in the design.** Shard 17 itself (line 218) says "stub class with one method" (the `HeartbeatClient` class with `maybe_record_flag()` no-op). Build-sequence + package skeleton ship 4 modules with `PhaseDeferredError`-raising bodies. These are not the same design. /implement-time agents reading shard 17 will write no-op call sites; /implement-time agents reading the package skeleton will write `PhaseDeferredError`-raising modules. **The 21 call sites land + the 4 modules land + they are incompatible = production crashes on first emit.**
  4. **Specs-authority Rule 6 violation.** Per `rules/specs-authority.md` MUST Rule 6, "Deviations from spec require explicit acknowledgment." The cross-shard inconsistency between shard 17 § 7.3 (no-op hooks) and the 4 stub modules (`PhaseDeferredError`) is not acknowledged anywhere. /implement is given two contradictory designs.
  5. **Round-1 sweep #2 missed it because the orphan-detection sweep grepped for `envoy.heartbeat` re-export at the package facade and found none — but the integration-point design at shard 17 § 7.3 lives at the EMIT-PRIMITIVE side, not the facade side.** Cross-shard orphan detection requires reading the consumer-shards' designs (BC, DD, GM, AS, BT, Channels, Runtime) and verifying the producer-shard's stub matches. Round 1's sweep did not perform that cross-shard check.

- **Recommended fix (BLOCKING for Phase 01 ship):**
  Two acceptable resolutions:
  - **Option A (preferred — match shard 17 § 7.3 design):** Replace the 4 `PhaseDeferredError`-raising modules with a single Phase 01 stub `HeartbeatClient` class at `envoy/heartbeat/client.py` that exposes `maybe_record_flag(flag_name: str) -> None: pass` (genuinely no-op). The other 3 modules (`star_prio.py`, `ohttp.py`, `signed_consent.py`, `registry.py`) raise `PhaseDeferredError` ONLY for the network-layer + cryptographic primitives (which Phase 01 production code MUST NEVER call). The 21 emit-site hooks call ONLY `client.maybe_record_flag(...)`. Wiring test: `tests/integration/test_heartbeat_stub_no_op_wiring.py` — invokes `client.maybe_record_flag("completed_boundary_conversation")` from a real `BoundaryConversationRuntime` completion path, asserts no exception, no Ledger entry, no network call.
  - **Option B (drop the 21 emit-site hooks entirely from Phase 01):** Re-scope shard 17 § 7.6 to "Phase 02 entry MUST add the 21 emit-site hooks at the same time the real `HeartbeatClient` lands." Phase 01 ships ZERO production call sites into `envoy.heartbeat.*`. Build-sequence + package-skeleton's 4-module-`PhaseDeferredError`-stub design becomes correct — the modules exist but no production code touches them, and `tests/regression/test_no_envoy_heartbeat_call_sites.py` greps `envoy/` for `import envoy.heartbeat\|from envoy.heartbeat\|self._heartbeat` and asserts ZERO matches in non-test code. Phase 02 entry adds the real client + the 21 emit-site wiring at the same atomic step.

  Option A is recommended (it preserves shard 17's "Phase 02 entry is mechanical" benefit). Plan 02 must add the wiring test name; plan 01 + plan 03 must update the heartbeat-stub design to a single `HeartbeatClient` class with `maybe_record_flag()` no-op alongside the 3 `PhaseDeferredError` modules for the network/crypto primitives.

  Per `rules/specs-authority.md` Rule 5b, this fix triggers a sibling re-derivation across shards 8, 9, 10, 11, 12, 16, 18 — each must explicitly add the `_heartbeat: HeartbeatClient` constructor parameter + the per-flag emit call. Round 1 R1-M-04 (tenant-isolation consolidation) is a sibling — both reflect the same per-shard-consolidation deficit that round 1 surfaced as MED. Round 2 elevates the heartbeat case to HIGH because the failure mode is "production crash" not "documentation drift."

---

### 3.3 R2-M-01 — Shard 17 § 7.2 Criterion 2 contains a factual error in the BET-tagging claim about the thesis (BET-3 / BET-12 falsifying bullets are NOT all `[Heartbeat]`-tagged) and misnames BET-5

- **Severity: MED**
- **Surface:** `01-analysis/17-foundation-health-heartbeat-decision.md` § 7.2 lines 196 (Criterion 2):
  > "BET-3 (sovereignty durability), BET-5 (Ledger as daily artifact), and BET-12 (governance-primary-surface palatability) lose their `[Heartbeat]`-tagged falsifying-evidence bullets per thesis § 5.0 ... However — and this is the load-bearing observation — the thesis itself **already tags every BET-3 / BET-12 falsifying bullet as `[Heartbeat]`**, which means thesis § 5.0 already presumes Heartbeat is a Phase 02 measurement substrate."
- **Verification (re-derived from `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` directly):**
  - **BET-3 § 5.3 lines 360–365:** has THREE falsifying bullets — `[Heartbeat]` (line 362) + `[Public]` (line 363) + `[Library]` (line 364). NOT every bullet is `[Heartbeat]`-tagged. The `[Public]` bullet ("OS-integrated agent products ship envelope-equivalent governance within 24 months") is observable WITHOUT Heartbeat infrastructure.
  - **BET-12 § 5.12 lines 525–530:** has FOUR falsifying bullets — three `[Heartbeat]` (lines 527, 528, 529) + one `[Public]` (line 530, "feedback themes around 'too much ritual'... exceed 20% of public mentions"). The `[Public]` bullet is observable WITHOUT Heartbeat.
  - **BET-5 misnaming.** Thesis § 5.5 line 389: "**BET-5 — Prosumer-first adoption is achievable and measurable**." Shard 17 § 7.2 line 196 calls it "BET-5 (Ledger as daily artifact)" — that is NOT BET-5. There is no thesis bet labeled "Ledger as daily artifact." (BET-8 § 5.8 is "The new habit forms (measurable via Heartbeat)" which is closer to the daily-artifact theme but still not the same.) The naming error suggests shard 17 § 7.2 was written from imperfect recall of the thesis, not direct re-citation.
- **Why a MED finding:** The Criterion-2 weight rests on a claim that overstates the thesis's `[Heartbeat]` reliance. BET-3 and BET-12 retain `[Public]` falsifying bullets that ARE measurable in Phase 01 cohort even without Heartbeat. The de-scope decision is still SOUND (other criteria 1, 3, 4, 5 carry the weight; the substrate cost + cohort-floor problem remain decisive), but the rationale's load-bearing claim that "the thesis itself already tags every BET-3 / BET-12 falsifying bullet as `[Heartbeat]`" is materially false. Per `rules/specs-authority.md` MUST Rule 4 (read-then-act, not paraphrase from memory), the analysis MUST cite the thesis directly. Round 1 sweep #1 (spec compliance) did not flag this because the misnaming + overclaiming is internal to a primitive shard's rationale, not a spec assertion.
- **Recommended fix:** Edit `01-analysis/17-foundation-health-heartbeat-decision.md` § 7.2 Criterion 2 to:
  - Correct BET-5 misnaming (it's "Prosumer-first adoption" not "Ledger as daily artifact").
  - Soften the "every bullet is `[Heartbeat]`" claim to "the majority of BET-3 / BET-12 / BET-8 falsifying bullets carry `[Heartbeat]` tags; the `[Public]` and `[Library]` bullets are observable without Heartbeat substrate at Phase 01 cohort scale, but the substrate cost (Criterion 1) and cohort-floor problem (§ 3.3 of this shard) carry the load-bearing decision weight."
  - The de-scope decision itself is preserved — only the rationale is corrected. This is a documentation-clarity MED, not a structural HIGH.

---

### 3.4 R2-M-02 — Shard 5 design omits Trust Vault key lifecycle (load, auto-lock, destroy at shutdown) despite `specs/trust-vault.md` § Memory hygiene T-071 mandate

- **Severity: MED**
- **Surface:**
  - Spec mandate: `specs/trust-vault.md` § Memory hygiene (T-071) cited at `01-analysis/05-trust-store-implementation.md` § 1 line 18: "Auto-lock after 15min idle (configurable). Lock-during-idle clears all in-memory secrets."
  - Shard 5 § 4 pseudocode (lines 145–256): `TrustStoreAdapter` constructor takes `vault_path` + `principal_id`. NO `close()`, `__aexit__`, `lock()`, `unlock()`, `_idle_timer_reset()`, `_destroy_in_memory_secrets()` methods. The 15-min auto-lock cycle is mandated by spec but not surfaced in design.
  - Per `rules/security.md` § "Rust: Fail-Closed Security Defaults" + `specs/trust-vault.md` § "Default to most restrictive": the default state of the Trust Vault is LOCKED. Every read site MUST verify the vault is unlocked before serving the request. Shard 5 § 4's `get_chain()` / `get_posture()` / etc. methods do NOT show a "vault unlocked" precondition check.
- **Adversarial framing finding (round-2 plan §3.2 prompt verbatim):** "Does the design name (a) where the AES key lives, (b) when it's loaded, (c) how it's destroyed at shutdown? Per `rules/security.md` § Fail-Closed Defaults, the default must be most restrictive — is the Trust Vault's default-locked posture verified at every read site?"
  - (a) WHERE the AES key lives: not specified in shard 5 § 4. By spec § Encryption it derives from Argon2id(passphrase) XOR Secure Enclave/TPM-bound secret; the in-memory residency lifetime is not stated.
  - (b) WHEN loaded: implicitly at `__init__`-time per pseudocode, but no explicit `_unlock(passphrase)` method.
  - (c) HOW destroyed: no destruction surface. The pseudocode has no `close()` or `__aexit__`.
- **Why a MED finding:** Spec mandate exists; design surface for it does not. /implement-time agents must invent the lifecycle methods. The risk is a partial implementation: the auto-lock fires, the vault locks, but the in-memory chain cache is not cleared — T-071 silent leak. This IS a HIGH-CANDIDATE under `rules/zero-tolerance.md` Rule 6 (implement fully) and `rules/security.md` § Fail-Closed Defaults — but Round 2 holds at MED because:
  - The spec mandate is unambiguous (the 15-min auto-lock is named); /implement-time discovery is mechanical.
  - The upstream `kailash.trust.vault.shamir` module (per shard 15 § 6.1 cited symbol map) provides primitives for key wrapping; the Envoy adapter's job is integration, not crypto re-implementation.
  - A Tier 2 wiring test surfaces the gap before ship: `tests/integration/test_trust_store_adapter_auto_lock_timer.py` would assert the vault locks after 15min idle and clears in-memory secrets. Round 1 R1-M-04 (tenant-isolation consolidation) is the sibling pattern — both reflect "spec mandate exists; design did not enumerate the surface."
- **Recommended fix:** Edit `01-analysis/05-trust-store-implementation.md` § 4 (or § 3.1) to add the lifecycle methods:
  - `unlock(passphrase: str)` — Argon2id derive; load AES key into memory; reset idle timer.
  - `lock()` / `__aexit__` — destroy in-memory AES key; clear chain cache; clear posture cache; clear ritual-state cache.
  - `_idle_timer_reset()` — invoked on every adapter call; resets the 15-min countdown.
  - Default state = LOCKED. Every adapter method (`get_chain`, `record_delegation`, etc.) MUST `assert self._unlocked` before proceeding; raise `VaultLockedError` if not.
  - Cross-reference `rules/security.md` § Fail-Closed Defaults inline.
  - Add Tier 2 test name to `02-plans/02-test-strategy.md` § EC-5 battery: `test_trust_store_adapter_auto_lock_timer.py`.

---

### 3.5 R2-M-03 — Shard 4 design does NOT explicitly enforce the cross-shard invariant (from shard 9 § 7 line 520) that `authored_constraints` MUST be sorted in JCS canonical order at envelope construction time

- **Severity: MED**
- **Surface:**
  - Shard 9 cross-shard claim: `01-analysis/09-authorship-score-implementation.md` § 7 line 520 (verbatim): "the `authored_constraints` list MUST be sorted at envelope construction time. This is a requirement Envoy MUST honor in the envelope compiler (shard 4) — it's not a frozen-spec ambiguity, it's an implementation contract that crosses shards. Logged here as a cross-shard invariant for shard 4 to verify."
  - Shard 4 § 4 pseudocode lines 130–139: lists 9 compile steps (validate, resolve template imports, NFC normalize, validate finite, validate tightening, compute authorship score, JCS canonicalize, emit Ledger, return). Does NOT list "sort `authored_constraints` in JCS canonical order" as an explicit step. JCS canonicalization at step 7 is the byte-level encoding; the LIST-LEVEL ordering invariant (shard 9 mandates) is not separately enforced in the design.
- **Adversarial framing finding (round-2 plan §3.2 prompt verbatim):** "Does the compiler honor `RoleEnvelope.validate_tightening` AT EVERY child-envelope construction site (not just the obvious one)? Cross-shard invariant from shard 9: must sort `authored_constraints` in JCS canonical order at construction time — is this actually enforced in the compiler design, or only assumed?"
  - Round 2 verdict: "only assumed." Shard 4's design does not explicitly call out the sort-at-construction invariant. Shard 9 § 7 is explicit that it MUST be honored. The cross-shard contract is logged but not closed.
- **Why a MED finding:** The `authored_constraints` list iteration order determines `AuthorshipScore.recompute()` determinism (shard 9 § 3 line 98). If the compiler emits an unsorted list, `recompute()` re-sorts at re-derivation time — defeating the cross-OS byte-identity invariant under BET-6 (shard 9 § 6 test `test_posture_gate_cross_os_score_byte_identity.py`). The risk is a Tier-3 cross-OS test failure surfaced at /redteam round 3+. The fix is one line in shard 4's design (add "sort `authored_constraints` in JCS canonical order before step 7 JCS canonicalization") + a Tier 2 wiring test. Per `rules/specs-authority.md` MUST Rule 5b, cross-shard invariants logged in one shard MUST be re-derived in the consumer shard; round 1 did not enforce this discipline.
- **Recommended fix:** Edit `01-analysis/04-envelope-compiler-implementation.md` § 4 line 137 to add an explicit step 6.5: "Sort `authored_constraints` lists in JCS canonical order (per shard 9 § 7 cross-shard invariant) BEFORE JCS canonicalization. Sort key: per `specs/envelope-model.md` § Canonical JSON lexicographic ordering on the constraint dict's canonical form." Add Tier 2 test name to `02-plans/02-test-strategy.md` § EC-1 battery: `test_envelope_compiler_authored_constraints_sorted.py`.

---

### 3.6 R2-M-04 — Shard 5 design's `record_delegation()` does NOT explicitly enumerate cycle-detection invocation despite `specs/trust-lineage.md` line 89 mandate ("At record creation: walk ancestors for cycle detection before accepting")

- **Severity: MED**
- **Surface:**
  - Spec mandate: `specs/trust-lineage.md` line 89: "At record creation: walk ancestors for cycle detection before accepting." Cited at shard 5 § 1 lines 20–24 (full algorithms cite).
  - Shard 5 § 4 line 199–209: `record_delegation()` pseudocode does not list a cycle-detection step. The upstream `TrustOperations.delegate(...)` (shard 5 § 2.2 line 55) likely performs the verification per `specs/trust-lineage.md` line 78 ("10 verification steps … cycle-free, depth ≤ 16, transitive authority"), but the Envoy-side design does not make this composition explicit.
- **Adversarial framing finding:** "Cascade revocation BFS reaches every descendant — is the BFS termination correct? What happens on a cyclic delegation chain (which the spec forbids but a corrupt chain might present)? Is there a defense?"
  - Round 2 verdict: defense exists upstream (per `specs/trust-lineage.md` line 78–92, including 15-vector test corpus per line 92), but Envoy-side composition is implicit. /implement-time agents may construct `DelegationRecord` directly bypassing `TrustOperations.delegate(...)`, silently skipping the cycle check.
- **Why a MED finding:** The kailash-py upstream's `TrustOperations.delegate(...)` does the cycle detection per spec mandate; Envoy is a thin adapter. The risk is /implement constructs `DelegationRecord` via `_with_algorithm_id()` + direct insertion (per shard 5 § 4 line 240–247) bypassing the verification path. Per `rules/orphan-detection.md` MUST Rule 1, the verifier (cycle-check) must have a production call site — the design must explicitly say "every `record_delegation()` invokes `TrustOperations.delegate(...)` (which performs the 10-step verification including cycle-free)." The single-line addition closes the orphan surface.
- **Recommended fix:** Edit `01-analysis/05-trust-store-implementation.md` § 3.3 OR § 4 `record_delegation()` to add: "implementation MUST route through `kailash.trust.operations.TrustOperations.delegate(...)` which performs the spec-mandated 10-step verification (delegation_id hash, signature verify, algorithm_identifier match, time window, chain_parent_id validity + non-revoked + capability-superset, nonce-uniqueness, cycle-free, depth ≤ 16, transitive authority, capability-existence at current envelope version per `specs/trust-lineage.md` line 78). Direct `DelegationRecord` construction bypassing `TrustOperations.delegate(...)` is BLOCKED per `rules/zero-tolerance.md` Rule 4." Add Tier 2 wiring test: `tests/integration/test_trust_store_adapter_cycle_detection_at_record_delegation.py`.

---

### 3.7 R2-M-05 — Shard 4 design omits explicit error-handling for `intersect_envelopes` returning `IntersectConflictError` (incompatible parents)

- **Severity: MED**
- **Surface:**
  - Spec mandate: `specs/envelope-model.md` § Algorithms § "`intersect_envelopes(a, b)`" (cited at `01-analysis/04-envelope-compiler-implementation.md` § 1 line 17): "raises `AlgorithmMismatchError`, `SchemaVersionMismatchError`, `IntersectConflictError` per § Error taxonomy."
  - Shard 4 § 4 pseudocode `EnvelopeCompiler.intersect()` (lines 155–167) wraps `kailash.trust.pact.envelopes.intersect_envelopes` but does NOT enumerate the error-handling disposition. What does the compiler do if upstream raises `IntersectConflictError`? The design is silent.
- **Adversarial framing finding (round-2 plan §3.2 prompt + adversarial elaboration):** "The `intersect_envelopes` provider returns the tighter envelope — the compiler is the consumer. Does the compiler design address what happens when intersect returns `None` (incompatible parents)? What's the user-visible failure mode?"
  - Round 2 verdict: design is silent on the error path. Likely intended disposition: let the typed error propagate to the caller (Boundary Conversation S6 / Grant Moment Approve+author / sub-agent SubsetProof construction). But "let it propagate" is not stated, AND the user-visible failure mode (does Boundary Conversation re-prompt? does Grant Moment refuse to execute?) is not designed.
- **Why a MED finding:** Without explicit error-handling disposition, /implement may default to one of three paths: (a) propagate (acceptable; Boundary Conversation handles), (b) catch + transform to `EnvelopeValidationError` (acceptable but masks the upstream-typed error class), (c) catch + fallback to a default envelope (BLOCKED — would be a silent fallback per `rules/zero-tolerance.md` Rule 3). Risk: /implement chooses (c) "to avoid breaking the conversation flow." The design must pin (a) or (b) explicitly.
- **Recommended fix:** Edit `01-analysis/04-envelope-compiler-implementation.md` § 4 `EnvelopeCompiler.intersect()` to add: "On upstream `IntersectConflictError`, propagate unchanged (the caller — Boundary Conversation S6 re-prompt, Grant Moment Approve+author refusal, or sub-agent SubsetProof construction failure — handles per its own state machine). Silent fallback to a default envelope is BLOCKED per `rules/zero-tolerance.md` Rule 3."

---

### 3.8 R2-L-01 — `02-plans/02-test-strategy.md` does NOT name a wiring test for the heartbeat stubs (related to but distinct from R2-H-02)

- **Severity: LOW (subsumed by R2-H-02)**
- **Surface:** `02-plans/02-test-strategy.md` — `grep -in "heartbeat" 02-plans/02-test-strategy.md` returns ZERO matches.
- **Why a LOW finding:** Independently, the absence of a heartbeat wiring test is a Tier 2 coverage gap. Bundled into R2-H-02 fix (one or the other Option A/B requires adding the test). Logged separately for transparency.
- **Recommended fix:** Subsumed under R2-H-02 fix.

---

### 3.9 R2-L-02 — Shard 6 (Ledger) `algorithm_identifier: dict` field type is correct but inherits the same wire-shape ambiguity as shard 5 (related to R2-H-01)

- **Severity: LOW (subsumed by R2-H-01)**
- **Surface:** `01-analysis/06-envoy-ledger-implementation.md` § 4 line 248: `algorithm_identifier: dict` — type-only declaration; wire-shape (1-key vs 3-key) is implicit through composition with Trust Store adapter.
- **Why a LOW finding:** Shard 6 inherits shard 5's wire-shape choice transitively. R2-H-01 fix (Option A: 3-key shape via `to_spec_form()` helper) propagates here automatically. Logged separately for transparency.
- **Recommended fix:** Subsumed under R2-H-01 fix.

---

### 3.10 R2-L-03 — Audit-mode discipline confirmation (re-derivation per `rules/testing.md` § Audit Mode Rules)

- **Severity: LOW (process)**
- **Surface:** This audit doc.
- **Finding:** Per `rules/testing.md` § Audit Mode Rules, this audit re-derived every claim from scratch — re-read every primitive shard, re-grep'd upstream symbols, re-queried every cited issue via `gh`, re-checked the thesis § 5.0 BET tagging directly (catching R2-M-01), re-checked the verifier-spec wire shape directly (catching R2-H-01), and re-checked the cross-shard implications between shard 17 and shards 8/9/10/11/12/16/18 (catching R2-H-02). The re-derivation is the structural defense against round 1's "0 CRIT + 0 HIGH" being a coincidence.
- **Recommended fix:** None. Process-discipline transparency.

---

## 4. Mechanical sweep results (round 2)

### Sweep #1 — Spec compliance verification

PASS at the assertion level (every primitive shard's cited spec section still exists at HEAD; every dataclass field still cited correctly). NEW FINDING at the cross-shard wire-shape consistency level — see R2-H-01.

### Sweep #2 — Orphan detection

PASS at the package-skeleton facade level (12 facades enumerated in plan 03 § 2.2; each has Tier 2 wiring test name in plan 02 § 2 EC-1..EC-9 batteries). NEW FINDING at the cross-shard emit-site coverage level — see R2-H-02 (heartbeat stub orphan failure).

### Sweep #3 — Closed-ISS still-closed verification

PASS — re-verified live at audit time (2026-05-03):

| ISS                                          | State  | Round 1 | Round 2 | Drift                             |
| -------------------------------------------- | ------ | ------- | ------- | --------------------------------- |
| #594                                         | CLOSED | CLOSED  | CLOSED  | —                                 |
| #595                                         | CLOSED | CLOSED  | CLOSED  | —                                 |
| #596                                         | OPEN   | OPEN    | OPEN    | — (matches journal/0002 baseline) |
| #597                                         | CLOSED | CLOSED  | CLOSED  | —                                 |
| #602                                         | CLOSED | CLOSED  | CLOSED  | —                                 |
| #603                                         | CLOSED | CLOSED  | CLOSED  | —                                 |
| #604                                         | CLOSED | CLOSED  | CLOSED  | —                                 |
| #605                                         | CLOSED | CLOSED  | CLOSED  | —                                 |
| #606                                         | CLOSED | CLOSED  | CLOSED  | —                                 |
| #673                                         | CLOSED | CLOSED  | CLOSED  | —                                 |
| #707 / #711                                  | CLOSED | CLOSED  | CLOSED  | —                                 |
| #731                                         | CLOSED | CLOSED  | CLOSED  | —                                 |
| #736 / #740 / #761–#764 / #788 / #790 / #791 | CLOSED | CLOSED  | CLOSED  | —                                 |
| #756 / #757                                  | CLOSED | CLOSED  | CLOSED  | —                                 |
| #752                                         | CLOSED | CLOSED  | CLOSED  | —                                 |

NO surprise re-opens. NO drift between round 1 and round 2. Round 1 baseline holds.

### Sweep #4 — Upstream module symbol verification at HEAD

PASS — re-grepped at audit time:

- `~/repos/loom/kailash-py/src/kailash/trust/pact/envelopes.py`: `intersect_envelopes` line 336 ✓; `RoleEnvelope` line 419 ✓; `validate_tightening` line 438 ✓; `TaskEnvelope` line 690 ✓; `compute_effective_envelope` line 716 ✓; `compute_effective_envelope_with_version` line 794 ✓.
- `~/repos/loom/kailash-py/src/kailash/trust/signing/algorithm_id.py`: `ALGORITHM_DEFAULT = "ed25519+sha256"` line 45 ✓; `class AlgorithmIdentifier` line 49 ✓; `to_dict()` line 102 returns `{"algorithm": self.algorithm}` line 108 ✓ (1-KEY FORM — surfaces R2-H-01).
- All other Phase 00 / Phase 01 cited symbols: STILL AT HEAD.

NO upstream symbol drift between round 1 and round 2.

NEW finding at the wire-shape level — see R2-H-01.

### Sweep #5 — Gap-analysis 22 timezone Option A consistency

PASS — re-checked across shards 11, 12, flow 04, flow 08, gap-22; all four consumers consistent on Option A as Phase 01 default. No drift.

### Sweep #6 — HIGH-candidate HELD verification (shard 13 chat-completion substrate)

PASS — re-checked. Round 1 R1-M-02 (Tier 2 chat_async wiring test missing in plan 02) carries forward as MED; the structural HOLD remains valid (legacy `kaizen.providers.llm.<provider>.chat_async()` exists at HEAD per upstream `~/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/providers/llm/{anthropic,openai}.py`).

### Sweep #7 — Tenant-isolation Rule 1 sweep

PASS at the explicit-keying level for shards 5, 6, 11, 12, 14. R1-M-04 carries forward (consolidation gap). Round 2 adversarial framing for shard 5 verified `_key()` helper (line 249–255) raises `PrincipalRequiredError` on missing dimension — Rule 2 satisfied. The adversarial check on cascade-revocation BFS termination (cyclic chain defense) surfaced R2-M-04.

### Sweep #8 — Event-payload classification

PASS — shard 6 plan 02 § 3.4 enforces `format_record_id_for_event` at the SINGLE EMISSION POINT; shard 11 cross-references; shard 16 cites Rule 1 + Rule 2 explicitly. NO drift.

### Sweep #9 — `kailash-ml` exclusion verification

PASS — re-checked at HEAD. `pip install kailash[shamir,nexus,kaizen]>=2.13.4` transitive closure does NOT pull `kailash-ml`. Round 1 baseline holds; #752 closure does not change disposition.

---

## 5. Round 1 + Round 2 cross-comparison

### 5.1 Round 1 MED findings — disposition status in round 2

| ID            | Sev (R1) | Sev (R2) | Drift | Notes                                                                             |
| ------------- | -------- | -------- | ----- | --------------------------------------------------------------------------------- |
| R1-M-01       | MED      | MED      | —     | Carries forward; not adversarially escalated                                      |
| R1-M-02       | MED      | MED      | —     | Carries forward; chat_async test name still missing in plan 02                    |
| R1-M-03       | MED      | MED      | —     | Carries forward; typed-error import pattern still ambiguous                       |
| R1-M-04       | MED      | MED      | —     | Carries forward; tenant-isolation consolidation rule still missing in plan 03 § 5 |
| R1-M-05       | MED      | MED      | —     | Carries forward; `envoy/observability/` module still absent from plan 03 § 2      |
| R1-M-06       | MED      | MED      | —     | False-candidate; closed                                                           |
| R1-L-01..L-04 | LOW      | LOW      | —     | Carry forward (none blocking)                                                     |

### 5.2 Round 1 MED finding RECLASSIFIED to HIGH in round 2

**R1-L-03 (algorithm_id wire-shape track-later) is RECLASSIFIED to R2-H-01 (HIGH).**

Round 1 logged shard 5 § 7.2 wire-shape ambiguity as LOW with disposition "tracked technical-debt item." Round 2 adversarial framing on shard 5 cross-referenced shard 7 (Independent Verifier) and `specs/independent-verifier.md` and discovered the wire-shape MISMATCH would fail EC-9 ship predicate. The round 1 mechanical sweep #4 verified `algorithm_id.py` at HEAD but did not check whether upstream's wire format matches the spec's wire format. Round 2's cross-shard sibling-spec check (per `rules/specs-authority.md` MUST Rule 5b discipline applied at audit time) caught it.

This is the canonical "round-1-too-clean" failure mode that `02-plans/04-redteam-cycle-plan.md` § 3.3 names as the structural justification for the adversarial trigger. Round 1 would NOT have surfaced R2-H-01 without round 2's adversarial framing. **Convergence-counter discipline is vindicated.**

### 5.3 NEW round-2 finding NOT present in round 1

**R2-H-02 (heartbeat stub design inconsistency) is entirely NEW.** Round 1 surveyed shard 17 § 7.3 stubs (~100 LOC) and the package-skeleton 4 modules separately; the cross-shard inconsistency between them (shard 17 § 7.3 line 218 mandates no-op `maybe_record_flag()`; package skeleton + build sequence ship `PhaseDeferredError`-raising modules) was invisible to per-shard mechanical sweeps. Round 2's adversarial-prompt-driven cross-shard read caught it.

This is the second canonical "round-1-too-clean" failure mode — round 1's mechanical sweep cannot catch cross-shard design inconsistencies because each shard's `§ 7` ambiguity disposition only surveys its own internal consistency.

### 5.4 NEW round-2 MED findings (R2-M-01..M-05)

Five new MED findings emerged from the adversarial framing:

- **R2-M-01:** thesis-tag factual error in shard 17 (BET-3 / BET-12 are NOT all `[Heartbeat]`-tagged; BET-5 misnamed)
- **R2-M-02:** Trust Vault key lifecycle absent from shard 5 design (T-071 mandate exists; design surface for it does not)
- **R2-M-03:** `authored_constraints` JCS sort-at-construction invariant from shard 9 § 7 not enforced in shard 4 design
- **R2-M-04:** cycle-detection invocation not explicit in shard 5 `record_delegation()` design
- **R2-M-05:** intersect-conflict error handling not explicit in shard 4 design

These are documentation-clarity MEDs (per `rules/specs-authority.md` MUST Rule 4 read-then-act discipline). All five flow from cross-shard reading round 1 did not perform.

---

## 6. Convergence gate status

### 6.1 Round-2 verdict

- **Round 2 result:** 0 CRIT + **2 HIGH** + 5 MED + 3 LOW.
- **Round 1 baseline:** 0 CRIT + 0 HIGH + 6 MED + 4 LOW.

### 6.2 Convergence counter

- **CONVERGENCE GATE NOT MET.** Per `02-plans/04-redteam-cycle-plan.md` § 4.3: "If round 2 produces ≥1 CRIT or ≥1 HIGH, the counter resets to 0. Round 3 is launched; the cycle continues."
- The HIGH count is 2 (R2-H-01 algorithm_id wire-shape, R2-H-02 heartbeat stub leak). Both reset the convergence counter.
- Per `02-mvp-objectives.md` line 91 EC-6: "0 CRITICAL findings + 0 HIGH findings × 2 consecutive `/redteam` rounds." Round 1 was 0/0; round 2 is 0/2; consecutive count is 0.

### 6.3 Required next steps before round 3

Per `02-plans/04-redteam-cycle-plan.md` § 1.3 + § 4.4:

1. **R2-H-01 fix:** Edit shard 5 § 4 + shard 6 § 4 to translate upstream's 1-key wire form into the spec's 3-key form via a `to_spec_form()` helper at the single emission point. Add Tier 2 wiring test name to plan 02 § EC-9 battery.
2. **R2-H-02 fix:** Reconcile shard 17 § 7.3 (no-op `maybe_record_flag()`) with package skeleton 03 + build sequence 01 (`PhaseDeferredError` modules). Recommended Option A: add a single Phase 01 `HeartbeatClient` class with `maybe_record_flag()` no-op alongside the 3 `PhaseDeferredError` network/crypto stub modules. Add Tier 2 wiring test name + sweep tests across shards 8/9/10/11/12/16/18.
3. **MED fixes (R2-M-01..M-05):** all are documentation-clarity edits to shards 4, 5, 17 + plan 02 (test names). Per `02-plans/04-redteam-cycle-plan.md` § 4.4, MED fixes do NOT reset the counter — but they should be addressed in the same fix cycle as the HIGHs.
4. **Round 3:** re-run the same 9 mechanical sweeps + the same shard-4/5/17 adversarial prompts + a NEW adversarial sweep for shards 6 (Ledger), 7 (Verifier), 16 (Channels) — these are now "potentially-clean" shards on the same prior-art logic that fired the round-2 trigger.

Convergence counter resumes at 0; round 3 must return 0/0 AND round 4 must also return 0/0 before EC-6 is met.

### 6.4 Phase 01 release predicate impact

Per `02-mvp-objectives.md` § 4, Phase 01 ships when all 9 ECs hold. EC-6 is the redteam cycle gate. The other 8 ECs are downstream of /implement. **Round 2's HIGH findings are PRE-IMPLEMENT findings (the design is internally inconsistent / mis-aligned with the spec); they MUST be fixed at the analysis layer before /implement starts**, otherwise /implement will commit the inconsistency and round 3+ will catch it post-hoc at higher fix cost.

This is exactly the ROI the redteam cycle is designed to capture: pre-implement adversarial discovery prevents a wire-shape mismatch from shipping into production code; pre-implement orphan-detection on cross-shard hooks prevents production crashes on first emit.

---

## 7. Per-finding tracker (carry-forward at /todos)

| ID          | Sev      | Surface                                                    | Disposition                                                                               | Owner          |
| ----------- | -------- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------------- | -------------- |
| **R2-H-01** | **HIGH** | Shard 5 § 4 + shard 6 § 4 + spec/independent-verifier      | **/todos: BLOCKING — wire-shape translation helper at producer single emission point**    | /todos planner |
| **R2-H-02** | **HIGH** | Shard 17 § 7.3 vs plan 01 line 144 + plan 03 lines 405–409 | **/todos: BLOCKING — reconcile 21-emit-site no-op stubs vs `PhaseDeferredError` modules** | /todos planner |
| R2-M-01     | MED      | Shard 17 § 7.2 Criterion 2                                 | /todos: factual correction (BET-3/12 tagging + BET-5 misnaming)                           | /todos planner |
| R2-M-02     | MED      | Shard 5 § 4 (lifecycle absent)                             | /todos: add `unlock`/`lock`/`__aexit__`/idle-timer surface; add Tier 2 test               | /todos planner |
| R2-M-03     | MED      | Shard 4 § 4 (auth_constraints sort)                        | /todos: explicit "sort at construction" step; add Tier 2 test                             | /todos planner |
| R2-M-04     | MED      | Shard 5 § 4 (cycle detection routing)                      | /todos: explicit "route through `TrustOperations.delegate()`" + Tier 2 test               | /todos planner |
| R2-M-05     | MED      | Shard 4 § 4 (intersect error handling)                     | /todos: explicit "propagate IntersectConflictError" disposition                           | /todos planner |
| R2-L-01     | LOW      | Plan 02 (heartbeat tests absent)                           | Subsumed under R2-H-02 fix                                                                | (closed)       |
| R2-L-02     | LOW      | Shard 6 § 4 (algorithm_id type)                            | Subsumed under R2-H-01 fix                                                                | (closed)       |
| R2-L-03     | LOW      | This audit doc                                             | Process-discipline confirmation                                                           | (closed)       |

Round 1 carry-forward (R1-M-01..M-05, R1-L-01..L-04): unchanged dispositions. R1-L-03 (algorithm_id technical-debt) is RECLASSIFIED to R2-H-01.

---

## 8. Cross-references

### Source docs audited (round 2 — re-derived from scratch)

Same 26 source docs as round 1 (per round-1 § 8); plus:

- Re-read of `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` § 5.0 + § 5.3 + § 5.5 + § 5.8 + § 5.12 (R2-M-01 BET-tag verification)
- Re-read of `~/repos/loom/kailash-py/src/kailash/trust/signing/algorithm_id.py` lines 102–108 (R2-H-01 wire-shape verification)
- Re-read of `specs/independent-verifier.md` lines 23–40 (R2-H-01 verifier-side wire shape)
- Re-read of `specs/trust-lineage.md` lines 22–30 + line 89 (R2-H-01 spec-side wire shape; R2-M-04 cycle-detection mandate)
- Re-read of `specs/trust-vault.md` § Memory hygiene (R2-M-02)

### Rules consulted (round 2)

Same 10 rules as round 1; plus:

- `rules/zero-tolerance.md` Rule 4 (no SDK workarounds; surfaces R2-H-01)
- `rules/zero-tolerance.md` Rule 2 (no fake stubs; surfaces R2-H-02)
- `rules/security.md` § Fail-Closed Defaults (surfaces R2-M-02)

### Forward references

- Round 3 (post-fix) — re-derive again per `rules/testing.md` § Audit Mode Rules; targets the FIX surfaces of R2-H-01 + R2-H-02 plus expanded adversarial framing on shards 6 + 7 + 16.
- Shard 25 — closure (consumes round 2's verdict + the human's Option A vs Option B selection from gap-analysis 22 § 4 timezone disposition).

---

## 9. Round-2 closure

**N CRIT = 0; N HIGH = 2; N MED = 5; N LOW = 3.** **Convergence gate NOT met.** Round 1 + Round 2 cross-comparison surfaced 1 reclassification (R1-L-03 → R2-H-01) and 1 new HIGH (R2-H-02). Both HIGH findings are PRE-IMPLEMENT design-layer issues; fixing at the analysis layer prevents downstream /implement waste. Round 3 follows after R2-H-01 + R2-H-02 fixes land in shards 4, 5, 6, 7, 17 + plans 01, 02, 03 (and the cross-shard sibling sweep across shards 8, 9, 10, 11, 12, 16, 18 for the heartbeat-stub reconciliation).

The round-2-too-clean prevention discipline of `02-plans/04-redteam-cycle-plan.md` § 3 is vindicated: round 1's "0 CRIT + 0 HIGH" was a clean baseline but contained 2 HIGH findings invisible to per-shard mechanical sweeps. Cross-shard adversarial framing is the structural defense.
