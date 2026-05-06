# Phase 01 MVP — Todos Index

**Document role:** Lean lookup table for every Phase 01 todo. /implement reads this manifest first, then reads the topical file for the current todo, then reads the per-todo section. Per `rules/specs-authority.md` MUST Rule 1: this is a manifest, not the work itself; the work lives in the linked files.

**Date:** 2026-05-05 (/todos opening; produced after /analyze closure at 1cfd78f).
**Status:** DRAFT — awaiting human approval at the /todos structural gate before /implement opens.
**Source authority:**

- `briefs/00-phase-01-mvp-scope.md` — what Phase 01 must ship (15 primitives + 8 channels + 9 ECs)
- `02-plans/01-build-sequence.md` — topological build order across 5 waves + side-channel
- `02-plans/02-test-strategy.md` — 3-tier test surface + per-EC acceptance batteries
- `02-plans/03-package-skeleton.md` — `envoy-agent/` repo layout + module enumeration
- `02-plans/04-redteam-cycle-plan.md` — /redteam round structure + 9 mechanical sweeps
- `04-validate/round-{1..4}-implementation-comprehensive.md` — 12 MED carry-forward
- `journal/0005-DECISION-todos-opening-dispositions.md` — 4 human dispositions

---

## Capacity discipline

Per `rules/autonomous-execution.md` § Per-Session Capacity Budget. Every todo MUST stay within:

- ≤500 LOC load-bearing logic
- ≤5–10 simultaneous invariants
- ≤3–4 call-graph hops
- Describable in 3 sentences

If a todo's `## Capacity check` section indicates >1 wave-position of dependencies or >500 LOC, it MUST be sharded BEFORE /implement opens. Sharding mid-/implement is BLOCKED.

---

## Todo files (consumed in dependency order)

| File                                                                               | Group | Description                                                                                                                     |
| ---------------------------------------------------------------------------------- | ----- | ------------------------------------------------------------------------------------------------------------------------------- |
| [00-pre-implement-clarifications.md](00-pre-implement-clarifications.md)           | 0     | 12 MED carry-forward + 4 human-disposition baselines; doc edits applied at /todos opening                                       |
| [01-wave-1-foundation.md](01-wave-1-foundation.md)                                 | 1     | 7 foundation primitives (envelope, trust, ledger, model, connection-vault, runtime, heartbeat); parallelizable across worktrees |
| [02-wave-2-authorship-shamir-boundary.md](02-wave-2-authorship-shamir-boundary.md) | 2     | Authorship Score + Shamir 3-of-5 + Boundary Conversation (most-integrated primitive; 6 modules)                                 |
| [03-wave-3-grant-moment-budget.md](03-wave-3-grant-moment-budget.md)               | 3     | Grant Moment 8-module + Budget multi-window; gates EC-2                                                                         |
| [04-wave-4-channels-digest.md](04-wave-4-channels-digest.md)                       | 4     | 8 channel adapters + Daily Digest; gates EC-3 + EC-7 + EC-8                                                                     |
| [05-wave-5-cli-packaging.md](05-wave-5-cli-packaging.md)                           | 5     | CLI 11 subcommands + pipx + NOTICES + observability + cross-OS install; gates Phase 01 release                                  |
| [06-side-channel-verifier.md](06-side-channel-verifier.md)                         | 6     | `envoy-ledger-verifier` separate-repo bootstrap (Python required + Rust stretch); gates EC-4 + EC-9                             |
| [07-tests-tier1.md](07-tests-tier1.md)                                             | 7     | Tier 1 unit tests (mocking allowed; <1s); pure-function and dataclass surfaces                                                  |
| [08-tests-tier3-acceptance.md](08-tests-tier3-acceptance.md)                       | 8     | Tier 3 EC acceptance tests not bundled in waves 2–4 (EC-5 Shamir 10-combo + EC-6 redteam convergence)                           |
| [09-tests-regression.md](09-tests-regression.md)                                   | 9     | Permanent regression tests for T-018 / T-019 / T-023 / T-070 / T-080                                                            |
| [10-docs-and-release.md](10-docs-and-release.md)                                   | 10    | README + CHANGELOG + NOTICES content + release-readiness checklist                                                              |
| [11-phase-02-handoff.md](11-phase-02-handoff.md)                                   | 11    | Phase 02 entry checklist (timezone Option B + heartbeat full impl + OAuth + Rust binding adapter)                               |

---

## Build-order summary (per `02-plans/01-build-sequence.md` § 1)

```
Wave 1 (parallelizable; group 1):
  envelope, trust-store, ledger, model-router, connection-vault, runtime-stub, heartbeat-stubs
Wave 2 (group 2; depends on Wave 1):
  authorship → shamir → boundary-conversation
Wave 3 (group 3; depends on Wave 1+2):
  grant-moment, budget
Wave 4 (group 4; depends on Wave 1+2+3):
  channels (8 adapters) + daily-digest
Wave 5 (group 5; depends on every primitive):
  cli + pyproject + notices + observability
Side-channel (group 6; parallel to waves 1–3):
  envoy-ledger-verifier (Python required + Rust stretch)
```

---

## EC acceptance map (per `01-analysis/02-mvp-objectives.md`)

| EC   | Acceptance gate                                                           | Owning todo group(s) |
| ---- | ------------------------------------------------------------------------- | -------------------- |
| EC-1 | Boundary Conversation N=3 ≤25min produce parseable EnvelopeConfig         | 2 (boundary) + 8     |
| EC-2 | Grant Moment 3 resolution shapes E2E with cascade revocation              | 3 (grant-moment) + 8 |
| EC-3 | Daily Digest 7 consecutive scheduled fires across configured channels     | 4 (digest) + 8       |
| EC-4 | Ledger tampering battery — verifier detects every form                    | 6 (verifier) + 8     |
| EC-5 | Shamir C(5,3)=10 combinations reconstruct + cross-tool interop            | 8                    |
| EC-6 | /redteam 2 consecutive rounds 0 CRIT + 0 HIGH                             | 8 + 11               |
| EC-7 | 8-channel × N=3 first-time-user onboardings (24 sessions)                 | 4 (channels) + 8     |
| EC-8 | 7-day operating window; cross-channel state coherence; cascade revocation | 4 (channels) + 8     |
| EC-9 | Independent verifier source-isolation gate (separate codebase)            | 6 (verifier) + 8     |

---

## 12 MED carry-forward map

| MED ID  | Disposition file/section            | Owning todo                                                                 |
| ------- | ----------------------------------- | --------------------------------------------------------------------------- |
| R1-M-01 | `specs/mvp-build-sequence.md` L128  | `00` (doc edit applied; consumed by `05` CLI subcommand impl)               |
| R1-M-02 | `02-plans/02-test-strategy.md`      | `00` + `01` (envoy-model-router wiring includes chat_async route test)      |
| R1-M-03 | `02-plans/03-package-skeleton.md`   | `00` (doc edit applied; consumed by every primitive's `errors.py` impl)     |
| R1-M-04 | `02-plans/03-package-skeleton.md`   | `00` (doc edit) + `01..04` (every primitive constructor takes principal_id) |
| R1-M-05 | `02-plans/03-package-skeleton.md`   | `00` + `05` (build envoy-observability)                                     |
| R2-M-01 | `01-analysis/17-foundation-...`     | `00` (factual correction in shard 17; no impl impact)                       |
| R2-M-02 | `01-analysis/05-trust-store-...`    | `01` (build envoy-trust-vault includes lifecycle)                           |
| R2-M-03 | `01-analysis/04-envelope-...`       | `01` (build envoy-envelope sorts authored_constraints at construction)      |
| R2-M-04 | `01-analysis/05-trust-store-...`    | `01` (cascade routes through TrustOperations.delegate)                      |
| R2-M-05 | `01-analysis/04-envelope-...`       | `01` (intersect propagates IntersectConflictError to caller)                |
| R3-M-01 | `02-plans/02-test-strategy.md`      | `06` (verifier non-adjacent reorder mutation case)                          |
| R3-M-02 | `specs/independent-verifier.md` L35 | `01` (ledger segment-boundary serializer extension)                         |

---

## Cross-references

- Phase 01 brief: `briefs/00-phase-01-mvp-scope.md`
- /analyze closure: `01-analysis/_index.md` (commit `1cfd78f`)
- Plans manifest: `02-plans/_index.md`
- /redteam history: `04-validate/round-{1..4}-implementation-comprehensive.md`
- Journal: `journal/000{1,2,3,4,5}-*.md`
- Frozen specs: `specs/_index.md` (37 frozen-v1 + 2 additive Phase 01)
- Capacity rule: `.claude/rules/autonomous-execution.md`
- Spec authority: `.claude/rules/specs-authority.md`
- Orphan/facade rules: `.claude/rules/orphan-detection.md` + `.claude/rules/facade-manager-detection.md`
- Tenant isolation rule: `.claude/rules/tenant-isolation.md`

---

## Approval gate

This /todos plan is awaiting human approval before /implement opens. Per the COC structural gate model:

- Approving the plan = approving WHAT is built and WHY (scope + sequence + acceptance gates)
- /implement executes autonomously thereafter under `rules/autonomous-execution.md`
- Material scope changes during /implement (new primitives, dropped acceptance gates, EC reframing) re-trigger the structural gate

The 4 human dispositions captured in `journal/0005-DECISION-todos-opening-dispositions.md` are integrated into this plan; no further human input is required at /todos opening.
