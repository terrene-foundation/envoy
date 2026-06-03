# /redteam — Fresh full-surface round + convergence (2026-06-03)

**Status:** CONVERGES at 0 CRITICAL + 0 HIGH across 2 consecutive clean post-fix rounds.
**Posture:** L5_DELEGATED (fresh repo; `posture.json` absent → default trust).
**HEAD scanned:** `70eea1a` (round) → fixes landed at `600d182` (PR #80, merged `563a74a`).
**Scope:** FULL Phase-01 surface (all 37 specs + `envoy/` 14 modules + `tests/` 1709 collected). This is the first fresh full-surface sweep since R4+R5 (2026-05-28), which converged only the EC-7+EC-8+F5.1 subscope. Delta since R5: CI gate + vault ResourceWarning fix (PR #76) + journals 0050–0052.

---

## Method

Round 1 used an 8-dimension multi-agent finder→adversarial-verify workflow (`.claude/workflows/redteam-round.mjs`, task `w512qpoar`). 3 of 8 dimensions emitted (spec-A, testing, zero-tol → 8 confirmed findings); 5 dimensions (spec-B/C, security, code-review, value) failed to emit StructuredOutput (over-broad scope → budget exhaustion). Those 5 dimensions were covered by **direct mechanical sweeps** (security patterns, orphans, version, CLI walk, stub/mock scrub) + the Round-2/3 verification below — labeled as direct sweeps per `rules/sweep-completeness.md` MUST-2, NOT relabeled as the agent dimensions.

---

## Convergence criteria

| Criterion                            | Status                                                                                                   |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| 1. 0 CRITICAL                        | ✓ 0 across all rounds                                                                                    |
| 2. 0 HIGH                            | ✓ 3 HIGH found in R1, all fixed (PR #80); R2+R3 show 0                                                   |
| 3. ≥2 consecutive clean rounds       | ✓ R2 (mechanical + 7 load-bearing invariants) + R3 (2 adversarial agents), both 0 CRIT/0 HIGH            |
| 4. Spec compliance AST/grep verified | ✓ literal command+output cited per assertion (R1 spec-A agent + R3 spec agent + direct invariant checks) |
| 5. New code has new tests            | ✓ the one new-module gap (`sqlite_perms.py`) closed — `tests/tier1/test_sqlite_perms.py` (4 tests)       |
| 6. Frontend integration 0 mock       | ✓ N/A (CLI/library); 0 `MOCK_/FAKE_/DUMMY_` in production `envoy/`                                       |

> Full-Phase-01 EC-6 closure remains gated on **F2** (independent ledger verifier in the separate repo `terrene-foundation/envoy-ledger-verifier`) per `rules/repo-scope-discipline.md` — unchanged from R5. This round converges the in-repo Phase-01 surface.

---

## Round 1 — confirmed findings + disposition

| ID      | Sev  | Finding                                                                                                                               | Disposition                                                                                                                                                                                                                                                                |
| ------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TEST-01 | HIGH | `envoy/trust/sqlite_perms.py::chmod_sqlite_family` (0o600 on WAL `-wal`/`-shm`; wired into ledger bootstrap) had ZERO importing tests | **FIXED** `tests/tier1/test_sqlite_perms.py` (WAL-family chmod, idempotency, absent-sibling, log-not-raise) — `600d182`                                                                                                                                                    |
| SCA-01  | HIGH | `specs/boundary-conversation.md` § Test location: 6/6 phantom citations (tests moved `e2e/integration/regression` → `tier2/tier3`)    | **FIXED** re-pointed to real paths — `600d182`                                                                                                                                                                                                                             |
| SCA-02  | HIGH | `specs/trust-lineage.md` § Test location: 22/22 phantom citations (primitives upstream per § Provenance)                              | **FIXED** Test-location → real in-repo consumer tests; upstream → `## Out of scope (this phase)` (ledger.md Phase-A precedent) — `600d182`                                                                                                                                 |
| ZT-1    | MED  | `kailash_py.py` `_TODO_WAVE_2/3` anchors cited renamed todo files (carve-out needs resolvable anchors)                                | **FIXED** re-pointed — `600d182`                                                                                                                                                                                                                                           |
| SCA-04  | LOW  | `trust-lineage.md:209` bare `TBD` token (spec-accuracy Rule 2)                                                                        | **FIXED** reworded — `600d182`                                                                                                                                                                                                                                             |
| ZT-2    | LOW  | `shamir/commitments.py:15` docstring `.pending/...` journal glob                                                                      | **FIXED** → `journal/0018` — `600d182`                                                                                                                                                                                                                                     |
| TEST-02 | MED  | spec-promised `tests/coverage/test_*.py` threat-coverage meta-gate doesn't exist                                                      | **DEFERRED (value-anchored)** — Phase-01 threats DO have tests (T-008/018/019/093 + structural mitigations in owning specs); the 50-threat meta-gate is frozen-full-product-spec infra that completes across phases. See journal/0053. **Surfaced to user for direction.** |
| TEST-03 | LOW  | 30 specs cite nonexistent test paths                                                                                                  | **BY-DESIGN** — frozen full-product specs span all 4 phases; the 2 Phase-01 in-scope (SCA-01/02) fixed; the other 28 are future-phase specs legitimately citing future paths. Not a Phase-01 blocker.                                                                      |

**Refuted in R1:** SCA-03 (`ledger-merge.md` 9 citations — severity did not survive: repo-wide convention, not a ledger-merge bug). The 6 `except Exception:` sites — all verified clean (re-raise or log+proceed), NOT error-hiding.

---

## Round 2 — mechanical sweeps + load-bearing invariants (post-fix; 0 new CRIT/HIGH)

- stubs/mocks/fakes in `envoy/`: **0** · hardcoded secrets / `eval`/`exec`/`shell=True`: **0** · version consistency `pyproject 0.1.0 == __init__ 0.1.0`: ✓ · new bare-except: **0**
- 7 load-bearing spec invariants verified: classification fail-closed (`ConfidentialityLevel.PUBLIC` default); abstract runtime Protocol exists (`runtime/protocol.py`, brief inv #2); authorship gate (`PostureGate.request_transition` 5-step fail-closed); envelope `IntersectConflictError` propagates; Shamir 3-of-5 threshold; channels = Telegram/Slack/Discord (brief-authorized de-scope-to-3); budget five-window ceiling.
- **DDL outside migrations (11 hits):** confirmed = the known **F11** value-anchored deferred LOW (`CREATE TABLE IF NOT EXISTS` schema-bootstrap; embedded-sqlite local-first app, no migration framework). Re-validated anchor EC-5(d); remains deferred.
- **5 further bare `TBD`** in `shared-household.md`/`acceptance-metrics.md`/`independent-verifier.md`(×2)/`tool-output-sanitization.md` — all future-phase / separate-repo open-questions (out of Phase-01 scope; same class as TEST-03).

## Round 3 — independent adversarial agents (0 CRITICAL, 0 HIGH)

| Agent             | Surface                                                          | Verdict                                                                                 | Receipt                   |
| ----------------- | ---------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ------------------------- |
| security-reviewer | trust-vault + connection-vault + shamir                          | **0 CRIT, 0 HIGH** (9 attack classes traced closed; T-02-35 binder-substitution closed) | agent `ac850565fabdebe8c` |
| general-purpose   | grant-moment + classification + authorship + budget spec-vs-code | **0 CRIT, 0 HIGH** (literal command+output per assertion)                               | agent `a290b61e78729b541` |

3 LOW informational from the security agent (passphrase-vs-tamper sentinel, `_payload` immutable-bytes drop, slot-label-vs-commitment) — all already disclosed in code comments / spec `## Out of scope` as Phase-02 items.

---

## Log-triage gate (Step 7)

Full suite: **1697 passed / 9 skipped / 3 xfailed**, 61–76 warnings. Every WARN+ entry is one class: `ResourceWarning: unclosed database` (sqlite, `threading.py:303`/`pathlib`) + one Ollama transport socket. **Disposition: Upstream** — kailash thread-local connections, GC-timed (not allocation-site), tracked `kailash-py#1245` + `journal/0051`/`0052`. `-W error::ResourceWarning` deliberately NOT enabled (blocked on the upstream fix). No other WARN+ entries.

---

## Receipts

- R1 workflow task: `w512qpoar` (output `/private/tmp/.../tasks/w512qpoar.output`).
- R3 adversarial agents: `ac850565fabdebe8c` (security), `a290b61e78729b541` (spec-compliance).
- Fix commit: `600d182`; PR #80 (CI green: test py3.11 + py3.13 + tests-gate all pass); merge `563a74a`.
- Suite: `uv run pytest` → 1697 passed / 9 skipped / 3 xfailed (1709 collected).
