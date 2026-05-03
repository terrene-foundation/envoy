# 04 — Phase 01 Redteam Cycle Plan

**Document role:** Pre-declare the Phase 01 `/redteam` round structure (shards 23–24 of /analyze; the gate to shard 25 closure). Defines the convergence gate (0 CRIT + 0 HIGH × 2 consecutive rounds per `rules/specs-authority.md` MUST Rule 5b inherited convergence semantics), the round-1 audit checklist (mechanical sweeps over every primitive shard 4–19 + every plan + every flow + the spec gap analysis 22), the adversarial framing trigger when round 1 returns "too clean," the round-2 closure gate, and the spec-compliance verification protocol per `skills/spec-compliance/SKILL.md`. This plan is consumed by the analyst agent at `/redteam` time as the round-1 prompt scaffold; `/redteam` MUST NOT trust prior round outputs (per `rules/testing.md` § Audit Mode Rules — re-derive each round from scratch).

**Date:** 2026-05-03 (shard 20 of /analyze, plan 4 of 4).
**Status:** DRAFT — load-bearing for shards 23–24 (the actual /redteam rounds) and shard 25 (closure decision). The round-1 prompt scaffold below is consumed verbatim by the analyst agent.
**Discipline:** Re-derive every check from scratch each round (per `skills/spec-compliance/SKILL.md`); never trust `.spec-coverage` or `convergence-verify.py` self-reports; cite specs by path; cite primitive shards by shard NN.

**Capacity check:** 1 deliverable. ~6 simultaneous invariants tracked (convergence threshold; AST/grep verification protocol per `skills/spec-compliance/SKILL.md`; orphan-detection per `rules/orphan-detection.md` MUST Rule 1; facade-manager-detection per `rules/facade-manager-detection.md` MUST Rule 1+2+3; mechanical sweep per `rules/agents.md`; adversarial-trigger per `01-shard-plan.md` § 4). Within `rules/autonomous-execution.md` § Per-Session Capacity Budget.

---

## 1. Convergence gate

### 1.1 The threshold

Phase 01 ships when EC-6 is met: **0 CRITICAL findings + 0 HIGH findings × 2 consecutive `/redteam` rounds**. Per `02-mvp-objectives.md` EC-6 line 91 verbatim:

> A staged red team session against the running Envoy MUST surface zero CRITICAL or HIGH findings × 2 consecutive rounds (the redteam audit cadence inherited from `rules/specs-authority.md` MUST Rule 5b sibling-spec re-derivation discipline applied to implementation).

The convergence semantics are inherited from `rules/specs-authority.md` MUST Rule 5b: in spec authoring, an edit is considered settled only when the full-sibling sweep produces 0 HIGH cross-spec drift over two rounds. Phase 01 implementation applies the same semantics — implementation is settled only when the full-codebase audit (every primitive's wiring + every facade's call site + every spec acceptance assertion) produces 0 HIGH × 2 rounds.

### 1.2 Why two rounds (and not one)

The first 0-HIGH round may be a coincidence — a particular auditor's blind spot, a particular grep that happened to miss a sibling site, a particular check ordering that surfaced one finding before the related sibling. The second round, run with re-derivation discipline (`rules/testing.md` § Audit Mode Rules — never trust prior outputs; never trust `.spec-coverage`; re-derive AST/grep), is the structural defense against the single-round coincidence.

Evidence for the rule: Phase 00 `specs/_index.md` § "Spec freeze discipline" records the 6-round redteam convergence on `specs/envelope-model.md` (7 CRIT initially → 0 CRIT/0 HIGH after 6 rounds, with the second 0/0 round catching one drift the first 0/0 round missed). Phase 01 inherits this discipline; the cost projection is 2 rounds minimum, more if HIGH findings surface.

### 1.3 What "round" means

A round is one full pass by the analyst-agent (this agent's role at `/redteam` time) over the entire Phase 01 deliverable surface (every shard 4–19 doc + every plan 20 doc + every flow 21 doc + spec gap analysis 22 + the implemented codebase by AST/grep). A round produces a findings table classified into CRIT / HIGH / MED / LOW. CRIT and HIGH findings MUST be fixed (or formally accepted with a written deviation per `rules/specs-authority.md` MUST Rule 6) before the next round starts.

If any round produces ≥1 CRIT or ≥1 HIGH, the round counter resets — only consecutive 0/0 rounds count toward the convergence gate.

### 1.4 What "consecutive" means

Round N+1 follows round N with NO intervening implementation work — only the fixes for findings surfaced in round N. If new feature implementation lands between rounds, the consecutive counter resets (the new feature may have introduced a new HIGH that round N+1 hasn't yet surfaced).

The exception: between a 0/0 round N and a 0/0 round N+1, fixes for MED or LOW findings ARE allowed without resetting the counter (MED / LOW are not blocking). HIGH or CRIT fixes between rounds DO reset the counter.

---

## 2. Round 1 audit checklist

The analyst agent runs round 1 with the following sweep, in the order listed. Each step produces findings; findings are classified at the end of the round.

### 2.1 Inputs the auditor reads (in order)

1. **Every primitive shard 4–19 doc.** Cite specs the shard cited; verify the citation lines still hold against the FROZEN spec at HEAD; verify the shard's § 7 ambiguity disposition is consistent with the implementation choice landed in the codebase.
   - `01-analysis/04-envelope-compiler-implementation.md`
   - `01-analysis/05-trust-store-implementation.md`
   - `01-analysis/06-envoy-ledger-implementation.md`
   - `01-analysis/07-independent-verifier-design.md`
   - `01-analysis/08-boundary-conversation-implementation.md`
   - `01-analysis/09-authorship-score-implementation.md`
   - `01-analysis/10-grant-moment-implementation.md`
   - `01-analysis/11-daily-digest-implementation.md`
   - `01-analysis/12-budget-tracker-implementation.md`
   - `01-analysis/13-model-adapter-implementation.md`
   - `01-analysis/14-connection-vault-implementation.md`
   - `01-analysis/15-shamir-recovery-implementation.md`
   - `01-analysis/16-channel-adapters-implementation.md`
   - `01-analysis/17-foundation-health-heartbeat-decision.md`
   - `01-analysis/18-runtime-abstraction-stub.md`
   - `01-analysis/19-pipx-distribution-architecture.md`
2. **All four plan 20 docs.**
   - `02-plans/01-build-sequence.md`
   - `02-plans/02-test-strategy.md`
   - `02-plans/03-package-skeleton.md`
   - `02-plans/04-redteam-cycle-plan.md` (this doc; reflexive — auditor verifies the plan is internally consistent)
3. **Every flow 21 doc.** Per `01-shard-plan.md` § 2 wave-F shard 21 (cross-primitive flows), the flow docs synthesize multi-primitive control paths (e.g., onboarding flow across shards 8 + 14 + 15; Grant Moment flow across shards 4 + 8 + 10 + 16). The auditor checks each flow doc's primitives against the corresponding primitive shard's § 5 ("Integration points") for consistency.
4. **Spec gap analysis 22.** `01-analysis/22-spec-gap-analysis.md` — full findings table. Verify every MED / HIGH / HIGH-candidate-HELD finding has the disposition the analyst-agent claimed at shard 22.
5. **The implemented codebase at HEAD** (assuming `/implement` has run for at least the wave being audited — Phase 01 redteam may run after each wave or once at the end of wave 5). The auditor reads the actual `envoy/` Python source, not the plan's claimed source.

### 2.2 Sweep #1 — Spec compliance verification (per `skills/spec-compliance/SKILL.md`)

The analyst MUST load `skills/spec-compliance/SKILL.md` BEFORE running this sweep. The protocol replaces file-existence checking with AST/grep verification. Re-derive every check from scratch — never trust `.spec-coverage` or `convergence-verify.py` self-reports.

For each frozen spec under `specs/`:

1. Enumerate every literal acceptance assertion (signatures, fields, decorators, MOVE shims, security tests).
2. For each assertion, run AST/grep against the codebase to verify it's present.
3. Produce `workspaces/phase-01-mvp/.spec-coverage-v2.md` (assertion table per spec section).

Assertion classes the analyst MUST sweep:

- **Class signatures.** For each spec-mandated public class (e.g., `EnvelopeCompiler`, `EnvoyLedger`, `BoundaryConversationRuntime`, `GrantMomentOrchestrator`, `DailyDigestService`, `EnvoyBudgetOrchestrator`, `ShamirRitualCoordinator`, `ConnectionVaultAdapter`, `EnvoyModelRouter`, `TrustStoreAdapter`, `PostureGate`, `KailashRuntime`), grep `envoy/` for the class definition AND the `__init__.py` re-export per `02-plans/03-package-skeleton.md` § 2.2.
- **Method signatures.** For each spec-mandated method (e.g., `EnvelopeCompiler.compile(EnvelopeConfigInput) -> EnvelopeConfig`, `EnvoyLedger.append(EntryEnvelope) -> EntryReceipt`, `PostureGate.request_transition(...)`), grep for the def + parameter shape.
- **Typed errors.** For each spec § Error taxonomy, grep `envoy/<primitive>/errors.py` for the typed class. Phase 01 ships exactly the spec's error names; new error names introduced by the implementer ARE a finding.
- **Schema fields.** For each dataclass field listed in a spec (e.g., `EnvelopeConfig.metadata.algorithm_identifier.cross_domain_rules: str`, `DigestPayload.<11 fields per schema/1.0>`, `EntryEnvelope.<35 fields per specs/ledger.md lines 47–91>`), grep the dataclass definition.
- **Decorators / Protocol markers.** `KailashRuntime` is a `Protocol`; the implementation MUST inherit from `Protocol` per shard 18 § 3 step 1.
- **Security tests.** Per `rules/testing.md` § Audit Mode Rules (verify security mitigations have tests), every spec § Threats subsection MUST have a corresponding `test_<threat>` function. T-018 (visible secret), T-019 (habituation), T-023 (Authorship Score seeding), T-070 (clipboard auto-clear), T-080 (TLS 1.3 pin), H-03 (primary-channel binding) — each MUST grep to a regression test under `tests/regression/`.

### 2.3 Sweep #2 — Orphan detection per `rules/orphan-detection.md` MUST Rule 1

For every facade-shape attribute (the 12 listed in `02-plans/03-package-skeleton.md` § 2.2), run:

```bash
# DO — for each facade name F at envoy/__init__.py:
grep -rn "from envoy import $F\|envoy.$F" envoy/cli.py envoy/<other facades>/
# Result MUST be ≥1 production call site under envoy/ that is NOT a test file.
```

The expected production call site for each facade in Phase 01 is `envoy/cli.py`. Per `rules/orphan-detection.md` MUST Rule 1, every facade MUST have a hot-path call site within 5 commits of the facade landing. Auditing at /redteam time means: if a facade has zero `envoy/` (non-test) call sites, that's a HIGH finding regardless of "tests pass."

For every manager-shape class on a facade per `rules/facade-manager-detection.md` MUST Rule 1, verify the Tier 2 wiring test exists at `tests/tier2/test_<lowercase>_wiring.py`. Missing wiring file = HIGH finding.

For every crypto-pair (per `rules/orphan-detection.md` MUST Rule 2a — `encrypt`/`decrypt`, `sign`/`verify`, `seed_genesis`/`verify_chain`, `record_delegation`/`revoke`, `export_master_key_for_shamir`/`import_master_key_from_shamir`, `wrap_key`/`unwrap_key`), verify a Tier 2 round-trip test through the facade. Missing round-trip = HIGH finding.

### 2.4 Sweep #3 — Mechanical AST/grep per `rules/agents.md` § "Reviewer Prompts Include Mechanical AST/Grep Sweep"

For every primitive's named upstream module cited in its shard § 2 ("Verified provider citation"):

```bash
# DO — for each upstream symbol citation, verify it still exists at HEAD
# Example: shard 5 cites kailash.trust.signing.crypto.sign() — grep upstream:
grep -rn "def sign" ~/repos/loom/kailash-py/src/kailash/trust/signing/
# (Or via Python AST: python -c "import ast; import kailash.trust.signing.crypto as m; ...")
```

For every "closed ISS" referenced in any shard:

```bash
# DO — verify each closed ISS is STILL closed (no surprise re-open)
gh issue view <N> --repo terrene-foundation/kailash-py --json state
```

For every "Tier 2 wiring test" claim (per § 2.3 above), verify the test path makes sense given the package skeleton at `02-plans/03-package-skeleton.md` § 3 — i.e., the test file exists OR is named in a /implement todo NOT-YET-DONE.

### 2.5 Sweep #4 — Spec gap analysis 22 dispositions

For the **1 unique HIGH** (consolidated timezone basis, shards 11 + 12; `01-analysis/22-spec-gap-analysis.md` § 4):

- If the human selected **Option A** at shard 25, verify the codebase ships UTC-only (no `digest_schedule_timezone` field on per-principal schedules; no `per_day_ceiling_timezone` on `EffectiveEnvelope.financial`; CronTrigger registered with `timezone="UTC"` in `envoy/daily_digest/service.py`; per-day reset in `envoy/budget/reset_scheduler.py` uses UTC midnight).
- If the human selected **Option B**, verify the spec edits landed (`specs/envelope-model.md` § Financial dimension has `per_day_ceiling_timezone: str` field; `specs/daily-digest.md` § Schedule has `digest_schedule_timezone: str` field) AND the codebase consumes them (Boundary Conversation S6 collects IANA timezone; CronTrigger registered with `timezone=<user IANA>`; per-day reset uses `zoneinfo.ZoneInfo(user_tz)`).
- Whichever option is selected, the OPPOSITE option's pattern in the codebase is a HIGH finding.

For the **1 HIGH-candidate HELD** (shard 13 chat-completion substrate; `01-analysis/22-spec-gap-analysis.md` § 2 row "Shard 13 Model adapter HIGH-candidate HELD"):

- Verify the HELD rationale is sound: legacy `kaizen.providers.llm.<provider>.chat_async()` IS the supported pattern, NOT a workaround per `rules/zero-tolerance.md` Rule 4.
- Verify the codebase does NOT silently degrade to a Phase 01 implementer's own re-implementation; if the implementer wired a custom `chat_async()` instead of consuming the legacy provider's, that's a HIGH (Rule 4 violation: "no workarounds for SDK bugs").
- The HOLD must NOT slip silently — auditor verifies the disposition note in shard 13's § 7 is reflected in the codebase comment AND the Phase 02+ tracker item is recorded in `02-plans/01-build-sequence.md` § "Phase 02 entry checklist" (or wherever the carry-forward lives).

For each MED finding in `01-analysis/22-spec-gap-analysis.md` § 3 (the 8 additive-prose dispositions), verify the codebase's implementation matches the disposition. E.g., shard 4 MED-2 ("Authorship Score AFTER template imports") — auditor reads `envoy/envelope/compiler.py` + greps for the order in which `metadata.authorship_score` is computed; if BEFORE template import fold-in, that's a HIGH (spec-gap drift).

### 2.6 Sweep #5 — Tenant isolation per `rules/tenant-isolation.md`

For every persistence call site (Trust store, Ledger, Budget store, Posture store, Connection Vault):

- Cache key includes `principal_id` (Rule 1)
- Multi-tenant strict mode raises `PrincipalRequiredError` on missing `principal_id` (Rule 2)
- Invalidation accepts optional `principal_id` (Rule 3); version-wildcard sweep `v*` per Rule 3a
- Audit rows persist `principal_id` indexed (Rule 5)

### 2.7 Sweep #6 — Event-payload classification per `rules/event-payload-classification.md`

For every Ledger row that references classified PKs (e.g., `account_id` keyed by email per `specs/data-model.md`), verify `envoy/ledger/facade.py` routes `record_id` through `format_record_id_for_event` at the SINGLE EMISSION POINT, not at call sites (Rule 1). Verify the classified-name partition for `fields_changed` is in place (Rule 3) IF the implementation introduces such a field.

### 2.8 Sweep #7 — Security-rules per `rules/security.md`

- No hardcoded secrets — grep for `sk-`, `xoxb-`, `xoxp-`, `Bearer `, etc., in `envoy/` (excluding `tests/` and `.env.example`).
- Parameterized queries — grep for `f"SELECT`, `f"INSERT`, `f"UPDATE`, `f"DELETE`, `'%s'%` patterns; verify all DB interactions go through `aiosqlite` parameter binding.
- DataFlow identifier safety per `rules/dataflow-identifier-safety.md` — every dynamic DDL identifier routes through `dialect.quote_identifier()`. Phase 01 SQLite-only does this through DataFlow's upstream helper; new schema migrations introduced by Envoy MUST also route through.
- Constant-time comparison for credential / token / API key (rules/security.md § "Rust: Credential Comparison" applies to the upstream Rust binding; for Phase 01 Python, verify any token-comparison code uses `hmac.compare_digest`).

### 2.9 Sweep #8 — Per-tier collect-only gate per `rules/orphan-detection.md` MUST Rule 5a + `02-plans/03-package-skeleton.md` § 3.1

```bash
for tier in tests/tier1 tests/tier2 tests/tier3 tests/regression; do
    pytest --collect-only -q "$tier" --continue-on-collection-errors
done
```

Each tier MUST exit 0. Any collection error = HIGH (per `rules/orphan-detection.md` MUST Rule 5: collection errors are blockers in the same class as test failures).

### 2.10 Sweep #9 — Pipx clean-install closure per shard 19

```bash
# DO — verify pipx install closure does NOT pull kailash-ml
# (run inside a fresh venv simulating clean pipx install)
pipx install envoy-agent
pip show -f envoy-agent | grep -i 'kailash-ml\|lightning'
# Expected: empty.
```

Empty output = PASS. Non-empty = HIGH (regression of shard 19 § 2.3 mandate; lightning quarantine #752 still blocks Phase 01 install).

---

## 3. Round-1-too-clean adversarial trigger

Per `01-shard-plan.md` § 4 row 5: **if round 1 returns 0 CRIT + 0 HIGH, the auditor MUST run round 2 with adversarial framing on the shard outputs that look "too clean."**

### 3.1 Why this trigger exists

Shards 4 (Envelope compiler), 5 (Trust store + lineage), and 17 (Foundation Health Heartbeat — DECISION shard) each surfaced **0 ambiguities** in their § 7. A clean § 7 is normal when the spec is rigorous and the upstream provider is A-grade — but it can also be a signal that the analyst-agent missed a class of finding (insufficient adversarial framing during analysis).

The adversarial trigger applies when round 1 mechanical sweeps surface 0 HIGH AND the "clean" shards above weren't independently stress-tested. Round 2 specifically targets these shards with adversarial prompts.

### 3.2 Round-2 adversarial prompts

For shards with "too clean" § 7, the round-2 auditor runs:

**Shard 4 — Envelope compiler:**

- "Find a sequence of `compile()` calls where the second call's input is byte-identical to the first call's input but the resulting `EnvelopeConfig.content_hash` differs. (If you can construct one, that's a HIGH determinism violation.)"
- "Find an attacker-controlled `EnvelopeConfigInput` field that, when fed through NFC + JCS, produces a `canonical_bytes` that fails `intersect_envelopes` round-trip with byte-equality. (If yes, HIGH.)"
- "If a Foundation cross-domain-rules registry version bump is published, does ANY existing `EnvelopeConfig`'s evaluation behavior change? (If yes, HIGH per shard 22 § 3.1 disposition — Foundation infrastructure changes MUST NOT cascade-revoke envelopes.)"

**Shard 5 — Trust store + lineage:**

- "Construct a sequence of `record_delegation` + `cascade_revoke` calls where `verify_cascade_complete` returns True but at least one descendant is NOT in `revoked_agents`. (If yes, HIGH — cascade is broken.)"
- "Find a code path where `principal_id` is silently defaulted to a placeholder (`'default'`, `'global'`, `''`). (If yes, HIGH per `rules/tenant-isolation.md` Rule 2.)"
- "Argon2id timing — is the parameter set fast enough on a 2020-class laptop that an attacker-side brute force is feasible? (If timing < 0.5s on a baseline laptop, MED → escalate to HIGH if combined with Trust Vault file-permission lapse.)"

**Shard 17 — Foundation Health Heartbeat (DECISION shard):**

- "The de-scope decision ships ~100 LOC of stubs only. Verify ZERO production code path in `envoy/` calls `envoy.heartbeat.*` modules in Phase 01. If ANY call site invokes the stubs, the de-scope is leaky and the stubs raising `PhaseDeferredError` will crash production."
- "Verify the 21-flag schema validator stub at `envoy/heartbeat/registry.py` does NOT silently accept arbitrary flag schemas (a stub that accepts any input is fake-implementation per `rules/zero-tolerance.md` Rule 2)."
- "Verify the `consent_ledger` entry type stub at `envoy/heartbeat/signed_consent.py` does NOT register the entry type in the Ledger taxonomy in Phase 01 (premature registration would let production code emit Heartbeat consent rows before OHTTP infrastructure exists, creating fake-implementation per Rule 2)."

### 3.3 Trigger discipline

The adversarial trigger is NOT optional when round 1 returns 0/0. The analyst MUST run the round-2 prompts above; if any prompt surfaces a HIGH, the convergence counter resets. Only when round 2 ALSO returns 0/0 (with the adversarial sweep applied) does the consecutive convergence start counting.

This is the structural defense against "the analysis was too clean because the analyst was too aligned with the implementer." Cross-SDK evidence: kailash-py 2026-04-19 — a code reviewer APPROVED a release, the subsequent /redteam mechanical sweep caught 2 of 7 return sites missing a required field that the reviewer never parity-grepped (cited in `rules/agents.md` § "Reviewer Prompts Include Mechanical AST/Grep Sweep" Origin paragraph).

---

## 4. Round 2 closure

### 4.1 What round 2 does

Round 2 is functionally identical to round 1 (same 9 sweeps in § 2; same adversarial prompts in § 3 if round 1 was 0/0) but run with two structural differences:

1. **Re-derivation discipline.** The analyst MUST NOT load `.spec-coverage-v2.md` from round 1; MUST re-derive every assertion sweep from scratch. Per `rules/testing.md` § Audit Mode Rules: never trust prior round outputs.
2. **Fix-introduction surface.** The analyst checks every fix landed between round 1 and round 2 for new HIGHs introduced by the fix itself (a fix that resolves one HIGH but introduces a different HIGH = round-counter reset).

### 4.2 What round 2 produces

Round 2 produces a findings table identical in shape to round 1. The analyst writes the table to a fresh `workspaces/phase-01-mvp/.spec-coverage-v2.md` (overwriting round 1's; the round-1 file is archived to `.spec-coverage-v2.round-1.md` for audit history).

### 4.3 Convergence verdict

If round 2 produces 0 CRIT + 0 HIGH AND round 1 produced 0 CRIT + 0 HIGH AND no implementation work landed between rounds (only fixes), the convergence gate is met. EC-6 is satisfied. Phase 01 ships pending the other 8 EC gates.

If round 2 produces ≥1 CRIT or ≥1 HIGH, the counter resets to 0. Round 3 is launched; the cycle continues.

### 4.4 What "no new implementation between rounds" means in practice

Between round 1 and round 2 the only allowed changes are:

- HIGH or CRIT fixes from round 1 findings.
- MED / LOW finding fixes (do NOT reset the counter).
- Documentation updates that do NOT change behavior (typo fixes, comment improvements).

NEW feature implementation, refactors of HOT-PATH code, package-skeleton changes — any of these reset the counter. The reason: a refactor between 0/0 round 1 and 0/0 round 2 may have introduced a HIGH that round 2 missed (round 2's sweeps cover the new code, but the auditor's mental model may still be primed by round 1's clean output). Per `rules/specs-authority.md` MUST Rule 5b, this is the same drift surface that motivated the full-sibling re-derivation rule.

---

## 5. Spec compliance verification per `skills/spec-compliance/SKILL.md`

The analyst-agent MUST load `skills/spec-compliance/SKILL.md` BEFORE running the audit. The skill defines the AST/grep verification protocol that replaces file-existence checking.

### 5.1 Why AST/grep, not file-existence

A test file `tests/tier2/test_envoy_ledger_wiring.py` may exist, contain `def test_*`, and pass — but if the test asserts on a `MagicMock` of the Ledger rather than the real facade, it does NOT verify the wiring. File existence is a weak signal; AST/grep verification (the test imports through the facade per `rules/orphan-detection.md` MUST Rule 1; the test asserts an externally-observable effect per `rules/testing.md` § Tier 2) is the structural signal.

### 5.2 The 9 verification checks

Per `skills/spec-compliance/SKILL.md` (the analyst loads this file at /redteam time; the 9 checks are NOT re-derived here — the skill is authoritative):

1. Class signatures match spec.
2. Method signatures match spec.
3. Typed errors match spec § Error taxonomy.
4. Schema fields match spec dataclass.
5. Decorators / Protocol markers match spec.
6. Security-mitigation tests exist for every spec § Threats subsection.
7. MOVE shims (Phase 02 entry items) are stubbed but not yet active.
8. Imports through the facade, not the implementation submodule.
9. Re-export at `__init__.py` for every facade per `02-plans/03-package-skeleton.md` § 2.2.

### 5.3 The output

The analyst writes `workspaces/phase-01-mvp/.spec-coverage-v2.md` as an assertion table per spec section. The format:

```markdown
| Spec §                                           | Assertion                                                              | Codebase location             | Status |
| ------------------------------------------------ | ---------------------------------------------------------------------- | ----------------------------- | ------ |
| `specs/envelope-model.md` § Schema (lines 14–84) | `EnvelopeConfig.metadata.algorithm_identifier.cross_domain_rules: str` | `envoy/envelope/types.py:42`  | PASS   |
| `specs/envelope-model.md` § Error taxonomy       | `MonotonicTighteningError`                                             | `envoy/envelope/errors.py:18` | PASS   |
| `specs/ledger.md` lines 47–91                    | 35 dataclasses transcribed                                             | `envoy/ledger/types.py:1-580` | PASS   |
| ...                                              | ...                                                                    | ...                           | ...    |
```

Any row with status FAIL = HIGH finding (spec assertion present in spec, missing from codebase). Per `skills/spec-compliance/SKILL.md`, this table is re-derived from scratch each round; the analyst MUST NOT copy from the prior round's table.

---

## 6. Round-1 prompt scaffold (analyst-agent consumes verbatim)

This block IS the prompt the analyst-agent receives at `/redteam` shard 23 entry. Reproduced here so the prompt is auditable and pre-declared.

```
You are running Phase 01 /redteam round 1.

Your role: re-derive coverage from scratch (do NOT trust .spec-coverage,
.spec-coverage-v2, or any prior session's audit output). Apply the
verification protocol from skills/spec-compliance/SKILL.md.

Inputs (read in this order):
1. skills/spec-compliance/SKILL.md (verification protocol)
2. workspaces/phase-01-mvp/02-plans/04-redteam-cycle-plan.md (this plan)
3. workspaces/phase-01-mvp/02-plans/01-build-sequence.md (build order)
4. workspaces/phase-01-mvp/02-plans/02-test-strategy.md (Tier 2/3 surface)
5. workspaces/phase-01-mvp/02-plans/03-package-skeleton.md (canonical layout)
6. workspaces/phase-01-mvp/01-analysis/22-spec-gap-analysis.md (HIGH/MED dispositions)
7. Every primitive shard 4–19 doc.
8. Every flow 21 doc.
9. The HEAD codebase under envoy/ + tests/.
10. Every frozen spec under specs/.

Run sweeps 1–9 from § 2 of the redteam plan. For each sweep:
- Use AST/grep, not file-existence.
- Cite spec by path; cite primitive shards by shard NN.
- Classify findings: CRIT / HIGH / MED / LOW.

If sweeps surface ≥1 CRIT or ≥1 HIGH, write the findings table to
.spec-coverage-v2.md and STOP — implementer fixes findings before round 2.

If sweeps surface 0 CRIT + 0 HIGH, run the round-1-too-clean adversarial
prompts from § 3.2 of the redteam plan against shards 4, 5, 17. Re-classify;
re-write the findings table.

Always write the table to:
  workspaces/phase-01-mvp/.spec-coverage-v2.md

Discipline:
- rules/orphan-detection.md MUST Rule 1, Rule 2, Rule 2a (orphan + crypto round-trip)
- rules/facade-manager-detection.md MUST Rule 1, 2, 3 (manager-shape discipline)
- rules/testing.md 3-tier + § Audit Mode Rules (no mocking; re-derive)
- rules/agents.md § Reviewer Prompts Include Mechanical AST/Grep Sweep
- rules/specs-authority.md MUST Rule 5b (full-sibling re-derivation)
- rules/autonomous-execution.md (estimate in sessions, not human-days)
```

The round-2 prompt is identical except (a) the input list adds round-1's findings table for cross-reference; (b) the re-derivation discipline is RE-emphasized (the analyst MUST NOT load round 1's `.spec-coverage-v2.md` at the start; only after producing round 2's may it cross-reference for the convergence verdict).

---

## 7. NO MOCKING discipline (per `rules/testing.md` § Tier 2 + § Tier 3)

Every sweep that exercises code MUST run against real infrastructure:

- Real SQLite (Trust store + Ledger + Posture store + Budget store).
- Real Ed25519 keypair (signing + verification).
- Real `keyring` against the active OS keychain.
- Real channel-vendor sandbox (Telegram test bot, Slack ngrok, Discord test guild).
- Real `apscheduler.AsyncIOScheduler` firing on real wall clock (with `freezegun` shim ONLY for 7-day compression).
- Real local LLM (Ollama for CI; real Claude/GPT for staging Tier 3).
- Real cross-OS matrix (macOS / Linux / Windows x86_64) for portability sweeps.

Mocking is BLOCKED at Tier 2 + Tier 3 per `rules/testing.md`. If any sweep claims "this would work but mocking required," that's a HIGH finding (the test does not actually verify the wiring). The auditor MUST re-classify as a Tier 1 unit test and demand a real Tier 2 wiring test land alongside.

---

## 8. Findings table format

Per `01-shard-plan.md` § 4 (failure-mode protocol). The analyst writes findings to `workspaces/phase-01-mvp/.spec-coverage-v2.md` with columns:

| ID    | Sev  | Surface  | Finding                                                 | Evidence                                            | Disposition                                     |
| ----- | ---- | -------- | ------------------------------------------------------- | --------------------------------------------------- | ----------------------------------------------- |
| F-001 | HIGH | Shard 4  | `compile()` non-deterministic between calls             | `tests/tier3/test_envelope_determinism.py:47 fails` | implementer fixes; round counter resets         |
| F-002 | MED  | Shard 12 | `BudgetReservation.timeout` default 60s lacks rationale | `envoy/budget/types.py:33`; spec is silent          | spec gap analysis 22 § 3 disposition acceptable |
| F-003 | LOW  | Shard 5  | `principal_id` vs `agent_id` terminology drift          | `envoy/trust/store.py` mixed naming                 | LOW; not blocking; track for Phase 03           |

CRIT and HIGH findings reset the convergence counter per § 4.3. MED / LOW findings do NOT reset.

---

## 9. Cross-references

### Plan 1, 2, 3

- `workspaces/phase-01-mvp/02-plans/01-build-sequence.md`
- `workspaces/phase-01-mvp/02-plans/02-test-strategy.md`
- `workspaces/phase-01-mvp/02-plans/03-package-skeleton.md`

### Spec gap analysis 22

- `workspaces/phase-01-mvp/01-analysis/22-spec-gap-analysis.md` — the consolidated HIGH (timezone) + HIGH-candidate HELD (chat-completion substrate) + 11 MED dispositions.

### Per-primitive shards 4–19

- All 16 primitive deep-dive docs at `workspaces/phase-01-mvp/01-analysis/{04..19}-*-implementation.md`.

### Skills

- `.claude/skills/spec-compliance/SKILL.md` — the AST/grep verification protocol; loaded at /redteam time by the analyst.

### Rules

- `.claude/rules/specs-authority.md` MUST Rule 5b — inherited convergence semantics.
- `.claude/rules/testing.md` § Audit Mode Rules + § 3-Tier — re-derivation + no mocking.
- `.claude/rules/orphan-detection.md` MUST Rules 1, 2, 2a, 4, 4a, 4b, 5, 5a, 6, 7.
- `.claude/rules/facade-manager-detection.md` MUST Rules 1, 2, 3.
- `.claude/rules/tenant-isolation.md` Rules 1–5.
- `.claude/rules/event-payload-classification.md` Rules 1–4.
- `.claude/rules/security.md` § "No Hardcoded Secrets", § "Parameterized Queries", § "Multi-Site Kwarg Plumbing".
- `.claude/rules/agents.md` § "MUST: Reviewer Prompts Include Mechanical AST/Grep Sweep".
- `.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget.
- `.claude/rules/zero-tolerance.md` Rules 1–6 (every CRIT/HIGH finding the auditor surfaces becomes a Rule-1 mandatory fix).

### MVP objectives

- `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` EC-6 line 91 — convergence gate verbatim.

### Forward references

- Shard 23 — round 1 (this plan's prompt scaffold consumed verbatim).
- Shard 24 — round 2 (re-derivation; convergence verdict).
- Shard 25 — closure decision (consumes the 0/0 × 2 verdict + the human's Option A vs Option B selection from shard 22 § 4).
