# 0053 — DECISION: fresh full-surface /redteam converges at 0 CRIT/0 HIGH

**Date:** 2026-06-03
**Type:** DECISION
**Phase:** 04-validate (/redteam to convergence)
**Posture:** L5_DELEGATED

## Verdict

The first fresh **full-Phase-01-surface** `/redteam` since R4+R5 (which converged only the EC-7+EC-8+F5.1 subscope) **CONVERGES at 0 CRITICAL + 0 HIGH across 2 consecutive clean post-fix rounds**. Full receipts + per-round detail: `04-validate/round-1-fresh-fullsurface-convergence-2026-06-03.md`.

- Round 1 (multi-agent workflow `w512qpoar` + direct mechanical sweeps for the 5 dimensions whose agents over-ran budget): 8 confirmed in-scope findings, **0 CRIT**, 3 HIGH.
- Fixes landed: commit `600d182`, PR #80 (CI green on py3.11 + py3.13 + tests-gate), merged `563a74a`.
- Round 2 (mechanical sweeps + 7 load-bearing spec invariants): 0 new CRIT/HIGH.
- Round 3 (2 independent adversarial agents — security `ac850565fabdebe8c`, spec-compliance `a290b61e78729b541`): **0 CRIT, 0 HIGH** each.
- Suite: 1697 passed / 9 skipped / 3 xfailed (1709 collected). All warnings = upstream sqlite/socket `ResourceWarning` (kailash-py#1245).

## Findings fixed (PR #80)

- **TEST-01 (HIGH)** — `envoy/trust/sqlite_perms.py::chmod_sqlite_family` (0o600 on the WAL family; wired into ledger bootstrap) had zero importing tests → `tests/tier1/test_sqlite_perms.py` added.
- **SCA-01 (HIGH)** — `boundary-conversation.md` § Test location: 6 stale citations re-pointed to the real tier2/tier3 paths.
- **SCA-02 (HIGH)** — `trust-lineage.md` § Test location: 22 upstream-EATP citations → real in-repo consumer tests + `## Out of scope (this phase)` (ledger.md Phase-A precedent).
- **ZT-1 (MED)** — `kailash_py.py` iterative-TODO anchors re-pointed to current filenames.
- **SCA-04 / ZT-2 (LOW)** — bare `TBD` removed from `trust-lineage.md:209`; shamir docstring journal glob → `journal/0018`.

## Deferred-item dispositions (value-anchored / by-design — NOT CRIT/HIGH)

These carry forward; each re-validates its value-anchor at re-pickup per `rules/value-prioritization.md` MUST-3.

- **TEST-02 (MED)** — the spec-promised `tests/coverage/test_every_threat_has_test.py` threat-coverage **meta-gate** does not exist. Re-graded MED (not HIGH): the Phase-01 threats themselves ARE covered (T-008/018/019/093 have regression tests; the rest have structural mitigations in their owning specs). The meta-gate spans the full 50-threat matrix across all 4 phases (frozen-full-product-spec infra) and only completes when the threat-test corpus does. **Value-anchor:** threat-model.md:51 Phase-01 gate "threat-model test suite green" (brief Exit-criteria EC-6 line 55). **Surfaced to co-owner for direction** (build a Phase-01-scoped gate now vs land the full-matrix gate with the corpus in Phase-02+).
- **TEST-03 (LOW)** — 30 specs cite nonexistent test paths. By-design: the 37 frozen specs describe the FULL product across all 4 phases; the 2 Phase-01 in-scope (SCA-01/02) are fixed; the other 28 are future-phase specs legitimately citing future paths (brief: "All 37 frozen specs are authoritative — no spec edits unless a HIGH gap"). Not a Phase-01 blocker.
- **F11 (LOW)** — 11 `CREATE TABLE IF NOT EXISTS` DDL outside a migration framework (8 in `trust/store.py`, 2 ledger, 1 authorship). Confirmed = the known R4 value-anchored deferred shard (anchor EC-5(d)). Legitimate embedded-sqlite local-first bootstrap; "migrate to db/migrations/" is gold-plating deferred to when cross-version schema upgrades land (Phase-02+).
- **5 future-phase `TBD` tokens** (`shared-household`/`acceptance-metrics`/`independent-verifier`×2/`tool-output-sanitization`) — future-phase / separate-repo open-questions; same class as TEST-03.

## Why (decision rationale)

The fresh sweep found that the dominant "finding class" is **spec-citation hygiene on frozen full-product specs that span all 4 phases** — not Phase-01 implementation gaps. The genuinely actionable Phase-01 work was: one untested security function (TEST-01) and two in-scope spec citation drifts (SCA-01/02), all fixed. The systemic citation/TBD/DDL items are pre-existing characteristics of the frozen-spec model and are correctly out of the 0-CRIT/0-HIGH Phase-01 convergence bar — consistent with how R4/R5 deferred F8–F11.

Full-Phase-01 **EC-6 closure remains gated on F2** (independent ledger verifier, separate repo) per `rules/repo-scope-discipline.md` — unchanged. This round closes the in-repo Phase-01 surface.

## Receipts

- Round report: `04-validate/round-1-fresh-fullsurface-convergence-2026-06-03.md`.
- Workflow task `w512qpoar`; adversarial agents `ac850565fabdebe8c` + `a290b61e78729b541`.
- Fix commit `600d182`; PR #80; merge `563a74a`.
