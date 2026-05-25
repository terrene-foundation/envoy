---
type: DISCOVERY
date: 2026-05-25
created_at: 2026-05-25T01:30:00Z
author: agent
session_id: phase-01-wave-1-redteam-r1
project: phase-01-mvp
topic: /redteam Round 1 against Wave-1 BUILD ship — verdict + same-shard sweep
phase: redteam
tags:
  [redteam, wave-1, convergence-receipt, orphan-detection, observability-rule-8]
---

# /redteam Round 1 — Wave-1 BUILD ship verdict + same-shard sweep

Durable convergence receipt per `rules/verify-resource-existence.md` MUST-4. Records the Round 1 verdict against `ecc234a..a52a14d` (Wave-1 BUILD: T-01-22 model router + T-01-26 runtime abstraction + T-01-27 heartbeat 5-stub partition + T-01-23 model router Tier 2). 36 files changed, 6483 insertions across 4 merged PRs (#31 / #32 / #33 / #34 / #35).

## Round 1 verdict: NOT CLEAN (4 findings)

| Severity | Source                       | Finding                                                                                                                                                                          | Disposition                                                                      |
| -------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| HIGH-1   | testing-specialist + analyst | T-01-26 runtime is 6-module orphan; ZERO importing tests across `envoy/runtime/{protocol,errors,feature_flags,selection,adapters/kailash_py,adapters/kailash_rs_bindings}.py`    | Same-shard fix: `tests/tier2/test_envoy_runtime_wiring.py` (19 cases, all PASS)  |
| HIGH-2   | analyst                      | T-01-26 runtime has ZERO in-package production call sites — same-bug-class as HIGH-1 (Phase 5.11 orphan pattern)                                                                 | Closed by HIGH-1 fix (the wiring test IS the first in-package consumer)          |
| MEDIUM-1 | security-reviewer            | 5 INFO log lines leak schema-revealing identifiers (`default_model`, `preset_name`, `provider_id`, `risk_class`, `choice`, `vault_imported`) per `rules/observability.md` Rule 8 | INFO→DEBUG on 5 log sites in `envoy/model/{router,risk,byom_picker}.py`          |
| MEDIUM-2 | analyst                      | T-01-26 todo Step 1 says "ABC" (actual: Protocol); no Status line; no Deviations section per `rules/specs-authority.md` Rule 6                                                   | Todo amended with Status + 5 narrow-scope deviations                             |
| LOW-1    | analyst                      | T-01-23 missing consolidated `tests/tier2/test_envoy_model_router_wiring.py` per `rules/facade-manager-detection.md` Rule 2 naming convention                                    | Added thin consolidated wiring test (1 case, real `LlmClient.from_env` resolver) |
| LOW-2    | analyst                      | T-01-27 todo no Status/Actual-LOC reconciliation (~100 est vs ~666 actual)                                                                                                       | Todo amended with Status + Actual LOC                                            |

Receipts:

- analyst task ID `affe389d1036fbea4` — Round 1 spec compliance audit (37 assertions verified)
- security-reviewer task ID `a3fbcf3caeecbc42f` — Round 1 security audit (10 threat surfaces; 9 CLEAN, 1 MEDIUM)
- testing-specialist task ID `afb0c45177a7c6364` — Round 1 test verification (854 passed, 13 skipped, per-module coverage grid)

## Same-shard fix sweep per `rules/autonomous-execution.md` MUST Rule 4

All 4 findings (2 HIGH + 1 MEDIUM + 1 LOW that ships within the same shard) are same-bug-class and within shard budget (≤500 LOC load-bearing; total fix surface ~250 LOC). Fix-immediately was applied in a single shard rather than deferred per Rule 4 — the orchestrator + agent contexts are warm, the same files are in attention, and the orphan-detection grace window for T-01-26 closes in ≤5 commits.

### Surface delivered

**Production changes (5 sites, all INFO→DEBUG per Rule 8):**

- `envoy/model/router.py:175-188` — `for_primitive.override_applied` demoted (default_model schema-revealing)
- `envoy/model/router.py:201-213` — `for_primitive.ok` demoted (preset_name + default_model)
- `envoy/model/risk.py:304-314` — `risk_annotation.emit.start` demoted (provider_id + risk_class)
- `envoy/model/risk.py:320-333` — `risk_annotation.emit.ok` demoted (provider_id; entry_id_hint kept as hash form per Rule 8)
- `envoy/model/byom_picker.py:295-305` — `byom_picker.ok` demoted (choice + vault_imported)

**Tests created:**

- `tests/tier2/test_envoy_runtime_wiring.py` (19 cases) — closes HIGH-1 + HIGH-2 by exercising `get_runtime()` → wired adapter method end-to-end. Sections: factory contract (2 cases), RS bindings blocked (4), lifecycle + identity (3), runtime device-key sign/verify round-trip (3), ledger wiring through real EnvoyLedger (3), Phase02 stubs typed-raise (4).
- `tests/tier2/test_envoy_model_router_wiring.py` (1 case) — closes LOW-1 facade-naming-convention; structural pin through real `LlmClient.from_env`.

**Todo amendments:**

- T-01-26 lines 697-735 — Status + 5 narrow-scope deviations (Protocol-not-ABC, no decorators, no return wrappers, no conformance runner, no import-discipline migration)
- T-01-27 lines 715-735 — Status + Actual LOC (666 vs 100 est) + ~21-emit-site deferral citation

### Verification

Full Tier-1 + Tier-2 + regression suite on the sweep branch: **874 passed, 13 skipped, 0 failures** (was 854 pre-sweep; +20 from the 19 runtime wiring cases + 1 consolidated model router wiring case). Zero warnings, zero collection errors.

The 13 skips are all ACCEPTABLE per `rules/testing.md` § Test-Skip Triage — infra-conditional (no `ANTHROPIC_API_KEY` / `OLLAMA_DEFAULT_MODEL` / etc. in dev env), each with explicit `reason=` string. Will run live when CI / staging provides credentials.

### Round 2 readiness

After this sweep PR merges, /redteam Round 2 will re-verify against the new HEAD with the same agent team. Convergence target per `/redteam` skill criteria: 2 consecutive CLEAN rounds (0 CRIT / 0 HIGH / 0 MEDIUM / 0 LOW). The MEDIUM-1 + 2× HIGH + 2× LOW fixes here should produce CLEAN on Round 2; if Round 2 surfaces new findings, the same-shard fix-immediately discipline applies again.

## Meta-pattern: pre-flagged dispositions caught all 4 findings

Every finding in this Round 1 had been pre-flagged in the /implement integration notes or the delegation prompts:

- HIGH-1 (T-01-26 missing Tier 2 wiring) was flagged at /implement integration time: "agent did not ship the requested Tier 2 wiring test; grace window OPEN; needs to ship before grace closes".
- MEDIUM-1 (5 INFO log lines) wasn't pre-flagged but is a recurring failure mode caught by security-reviewer's mechanical Rule 8 sweep.
- MEDIUM-2 (T-01-26 todo Step 1 stale) was implicit in the orchestrator's narrow-scope decision but the todo wasn't amended at integration time.
- LOW-1 + LOW-2 are documentation-class — caught by analyst's mechanical sweep.

The lesson reinforces `rules/agents.md` MUST "Reviewer Prompts Include Mechanical AST/Grep Sweep": the testing-specialist's `grep -rln "envoy.runtime" tests/` returning empty took ~4 seconds and caught what 5 minutes of LLM-judgment review missed.

## For Discussion

1. **Counterfactual**: would Round 1 have surfaced HIGH-1 without the pre-delegation flag ("agent didn't ship Tier 2 wiring; check it")? Per testing-specialist's mechanical sweep methodology, yes — the `grep -rln "envoy.runtime" tests/ → empty` finding is mechanical and would have surfaced regardless of pre-flagging. The pre-flag accelerated triage (the agent went directly to the verification), not the detection itself. Confirms the orphan-detection mechanical sweep is the load-bearing defense, not memory of prior intent.

2. **What changes if /redteam runs at L4 instead of L5?** Posture is currently L5_DELEGATED, making Round 1 OPTIONAL per `skills/32-trust-posture/redteam-integration.md`. At L4 the same Round 1 is MANDATORY mechanical sweep — the verdict would be identical because the agent prompts already include all the mechanical sweeps. The posture flag changes the GATE, not the audit content.

3. **Should the orchestrator have launched the Tier 2 wiring test as a 2nd-tier shard at T-01-26 launch time instead of relying on the agent's prompt + grace window?** Counterargument: the prompt was explicit ("ship Tier 2 wiring test"); the agent's miss reflects a context-management failure inside its session, not an orchestrator-prompt failure. The structural fix is orchestrator post-delegation verification (per `rules/worktree-isolation.md` MUST Rule 3 — verify deliverables exist after agent exit), which DID fire at /implement integration and flagged the gap; the gap closed within the orphan-detection grace window. Process held.

## Follow-up

- Round 2 verification against the sweep PR's merged HEAD — pending after this PR merges
- Codify candidates surfaced during Round 1 (non-blocking, captured for next /codify cycle):
  - Mechanical orphan-detection sweep (per-new-module test grep) MUST run at every /implement integration as a default check, not just at /redteam
  - The "agent reports completion but didn't ship the requested test file" failure mode generalizes — orchestrator post-delegation `ls`/`grep` verification is the bounded structural defense
