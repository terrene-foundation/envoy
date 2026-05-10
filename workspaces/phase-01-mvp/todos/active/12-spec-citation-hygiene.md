# 12 — Spec Citation Hygiene (R2-H-3 deferral)

**Severity**: HIGH per `rules/spec-accuracy.md` Rule 1 (phantom citations against `main` = CRITICAL classification).
**Origin**: /redteam Round 2 (`workspaces/phase-01-mvp/04-validate/round-2-implement-redteam.md` § 2.3).
**Decision context**: `journal/0015-DECISION-spec-citation-hygiene-deferred-to-todos.md`.
**Bounded-budget rationale**: Originally ~45 citations × 3 specs > 1 shard threshold; split into Phase A (this todo's primary scope, completed 2026-05-10) + Phase B (embedded acceptance bullets in named successor shards) per `rules/autonomous-execution.md` MUST Rule 4 + `rules/specs-authority.md` Rule 5b.

---

## Status

**Phase A — DONE 2026-05-10** (commit pending). 45 phantom citations across 3 specs cleared:

| Spec                       | Phantom (before) | Resolves on main (after) | Phase B deferrals (under § Out of scope) |
| -------------------------- | ---------------- | ------------------------ | ---------------------------------------- |
| `specs/shamir-recovery.md` | 9                | 4 tier1 paths            | 4 (T-02-36 / T-02-37 / T-08-130)         |
| `specs/trust-vault.md`     | 18               | 5 tier1 paths            | 1 (T-02-37)                              |
| `specs/ledger.md`          | 18               | 4 tier1+regression paths | 4 (T-03-50 / T-06-104 / T-08-131)        |
| **Total**                  | **45**           | **13** (all resolve)     | **9** (scheduled, not phantom)           |

Phantom-citation audit returns 0 MISSING. Split-state framing audit returns 0 hits. The remaining 13 citations are real test paths on `main`; the 9 scheduled-shard items are documented as `(scheduled in T-NN-NN)` under each spec's new `## Out of scope (this phase)` section per `rules/spec-accuracy.md` Exception 1 (bounded out-of-scope sections). Phase 04+ items (T-002, T-003, T-013, T-019/visible-secret, T-040, T-041, T-042, T-071, T-101, T-104, configurable-thresholds, padding-bucket, hidden-envelope, key-destruction-irreversible, lamport-merge, segment-boundary, PQ-migration, etc.) deleted entirely from spec content per `rules/spec-accuracy.md` Rule 4 — workstreams live in `specs/threat-model.md` for the future-phase audit.

**Phase B — embedded in 4 successor shards.** Each shard's acceptance bullet binds it to upgrade the relevant `(scheduled in T-NN-NN)` line to a concrete test-file citation when the test lands:

| Successor shard                           | Wave todo                                                      | Spec § Out of scope item upgraded                                                                                   | When              |
| ----------------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ----------------- |
| T-02-36 (Shamir recovery CLI)             | `02-wave-2-...md`                                              | shamir-recovery.md: per-card BIP-39 checksum (L-03)                                                                 | At T-02-36 close  |
| T-02-37 (Shamir Tier 2 wiring)            | `02-wave-2-...md`                                              | shamir-recovery.md: 3-of-5 reconstruct + Genesis-Record commitment binding; trust-vault.md: 3-of-5 vault round-trip | At T-02-37 close  |
| T-03-50 (Grant Moment)                    | `03-wave-3-...md`                                              | ledger.md: two-phase signing intent_id + T-004 + T-008                                                              | At T-03-50 close  |
| T-06-104 / T-08-131 (envoy-ledger-verify) | `06-side-channel-verifier.md` + `08-tests-tier3-acceptance.md` | ledger.md: hash-chain verifier exit gate                                                                            | At T-06-104 close |
| T-08-130 (EC-5 Tier 3)                    | `08-tests-tier3-acceptance.md`                                 | shamir-recovery.md: full S8 ritual via Boundary Conversation                                                        | At T-08-130 close |

Each successor shard's acceptance criteria gain the bullet:

> Per `12-spec-citation-hygiene.md` Phase B, upgrade the `(scheduled in T-NN-NN)` entry in `specs/<spec>.md` § Out of scope to a concrete `tests/...` citation under § Test location, OR delete the line if scope was cut. The citation grep `grep -hoE 'tests/[a-z0-9_/]+\.py' specs/{shamir-recovery,trust-vault,ledger}.md | while read p; do [ -f "$p" ] || echo MISSING; done` MUST exit 0 with no output at this shard's PR merge time.

---

## Phase A scope (completed)

Apply policy in this order to every cited test path:

- **(a) DELETE outright** — Phase 04+ work, or Phase 02-only hardening with no Phase 01 active todo. Removed from `## Test location` AND no entry created in `## Out of scope (this phase)` (the workstream lives in `specs/threat-model.md` per Rule 4).
- **(b) MOVE to § Out of scope (this phase) with `(scheduled in T-NN-NN)`** — citation maps to a specific Phase 01 active todo. The successor shard's acceptance bullet (Phase B) closes the scheduled item.
- **(c) REWORD to existing path in § Test location** — citation maps to a tier1 test that already shipped (often under a different name from the spec's original wording).

## Acceptance criteria

- [x] Phase A: every `tests/...` citation in `specs/{shamir-recovery,trust-vault,ledger}.md` § Test location resolves to a file present on `main`. Audit:
  ```bash
  grep -hoE 'tests/[a-z0-9_/]+\.py' specs/shamir-recovery.md specs/trust-vault.md specs/ledger.md \
    | sort -u \
    | while read p; do [ -f "$p" ] || echo "MISSING: $p"; done
  ```
  Exits 0 with no `MISSING:` output. **Verified 2026-05-10.**
- [x] Phase A: split-state framing audit returns 0 hits per `rules/spec-accuracy.md` audit protocol:
  ```bash
  grep -iE 'phase-?1.*phase-?2|target.state|promised.*current|scaffold.*later|TBD|backend.follow-?up|FE.follow-?up|pending.accessor|to.be.wired|accessor.pending' specs/shamir-recovery.md specs/trust-vault.md specs/ledger.md
  ```
  Returns no matches. **Verified 2026-05-10.**
- [x] Phase A: Phase 04+ items REMOVED from spec content (not parked in spec § Out of scope). The 9 `(scheduled in T-NN-NN)` items in spec § Out of scope ALL map to active Phase 01 todos. **Verified 2026-05-10.**
- [x] Phase B: 5 successor wave todos (T-02-36 / T-02-37 / T-03-50 / T-06-104 / T-08-130) gain the citation-upgrade acceptance bullet. **Done 2026-05-10.**
- [ ] Phase B per shard: as each successor shard merges, its specific `(scheduled in T-NN-NN)` entry is upgraded to a real `tests/...` citation OR deleted (if scope cut). Tracked in the shard's own acceptance, not here.
- [ ] Phase B convergence: at /redteam Round 1 of EC-6 sweep (T-08-131), the citation grep + split-state grep MUST both exit 0. This is THE gate that closes this todo permanently.

## Out of scope (this todo)

- Renaming `tests/integration/` → `tests/tier2/` to align directory naming with `rules/testing.md` § 3-Tier Testing (separate hygiene workstream).
- Adding the `commands/redteam` Round-1 spec-citation grep prepend (separate /codify proposal — see `journal/0015-...md` For Discussion question 2).
- Adding § Out of scope sections to specs OTHER than the 3 in scope here (any future spec that picks up phantom citations gets the same treatment via /redteam Round 1).

## Verification (Phase A close)

```bash
# Citation grep audit (passes)
grep -hoE 'tests/[a-z0-9_/]+\.py' specs/shamir-recovery.md specs/trust-vault.md specs/ledger.md \
  | sort -u \
  | while read p; do [ -f "$p" ] || echo "MISSING: $p"; done
# (zero MISSING lines)

# Split-state framings audit (passes)
grep -iE 'phase-?1.*phase-?2|target.state|promised.*current|scaffold.*later|TBD|backend.follow-?up|FE.follow-?up|pending.accessor|to.be.wired|accessor.pending' specs/shamir-recovery.md specs/trust-vault.md specs/ledger.md
# (no matches)

# Sibling-spec re-derivation per rules/specs-authority.md Rule 5b — checked: posture-ladder.md, envelope-model.md, threat-model.md, classification-policy.md reference these 3 specs but do NOT contain phantom citations against them. The cross-spec drift surface added in this PR is bounded to the 3 specs in scope.

# Test suite: green (no behavioral change; spec edits + todo edits + journal entries only).
.venv/bin/python -m pytest tests/ -q
```

## Cross-references

- `rules/spec-accuracy.md` Rules 1 / 2 / 4 / 5 / Audit Protocol.
- `rules/specs-authority.md` Rule 5b (sibling-spec re-derivation).
- `rules/autonomous-execution.md` MUST Rule 4 (bounded-budget clause + same-bug-class fix-immediately).
- `rules/zero-tolerance.md` Rule 1b (legitimate-deferral protocol — this todo IS the tracking issue).
- Round 2 redteam report: `04-validate/round-2-implement-redteam.md` § 2.3.
- Decision: `journal/0015-DECISION-spec-citation-hygiene-deferred-to-todos.md`.
