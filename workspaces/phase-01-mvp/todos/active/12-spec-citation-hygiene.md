# Wave-\* — Spec Citation Hygiene (R2-H-3 deferral)

**Severity**: HIGH per `rules/spec-accuracy.md` Rule 1 (phantom citations against `main` = CRITICAL classification).
**Origin**: /redteam Round 2 (`workspaces/phase-01-mvp/04-validate/round-2-implement-redteam.md` § 2.3).
**Decision context**: `journal/0015-DECISION-spec-citation-hygiene-deferred-to-todos.md`.
**Bounded-budget rationale**: ~50 citations × 3 specs > 1 shard threshold; deferred per `rules/autonomous-execution.md` MUST Rule 4 bounded-budget clause.

## Scope

Audit + remediate every spec § Test location citation that does not grep-resolve against `main`:

| Spec                       | Lines   | Citations | Resolved on main          |
| -------------------------- | ------- | --------- | ------------------------- |
| `specs/shamir-recovery.md` | 77-84   | 8         | 0                         |
| `specs/trust-vault.md`     | 75-92   | 18        | 0                         |
| `specs/ledger.md`          | 620-637 | 17        | 1 (HaltedByRollback only) |

**Total**: ~50 phantom citations. **Allowed at convergence**: 0.

## Acceptance criteria

- [ ] Every `tests/...` citation in `specs/{shamir-recovery,trust-vault,ledger}.md` resolves to a file present on `main` AT MERGE TIME of the closing PR. The bash audit:
  ```bash
  grep -hoE 'tests/[a-z0-9_/]+\.py' specs/shamir-recovery.md specs/trust-vault.md specs/ledger.md \
    | sort -u \
    | while read p; do [ -f "$p" ] || echo "MISSING: $p"; done
  ```
  Exit 0 with no `MISSING:` output.
- [ ] Per-citation disposition recorded inline (delete | reword to `(scheduled in T-NN-NN)` per Exception 3 reserved-for-future-work | keep-because-test-lands-this-shard).
- [ ] Sibling-spec re-derivation per `rules/specs-authority.md` Rule 5b: any spec edit triggers a sweep of every other spec referencing the affected tests; cross-spec drift findings recorded in journal.
- [ ] No new split-state / phase-1-vs-phase-2 framings introduced (`rules/spec-accuracy.md` Rule 2).
- [ ] `commands/redteam` Round-1 mechanical sweep `rg -i 'phase-?1.*phase-?2|...'` returns 0 hits.

## Disposition policy (default — refine in this shard if cases dictate)

Per the three candidate policies in `journal/0015-DECISION-...md` § For Discussion question 3:

- **(a) Default delete**: any cited test path NOT mapped to an open `todos/active/` workstream → DELETE the citation line.
- **(b) Reword for scheduled work**: any cited test path mapped to a specific open todo → REWORD to "`(scheduled in T-NN-NN)`" plus the citation, classified under `## Out of scope (this phase)` per `rules/spec-accuracy.md` Exception 1 / 3.
- **(c) Keep**: any cited test path that lands as part of THIS shard's coverage gap remediation → land the test, keep the citation.

The shard MAY refine the policy if the actual citations dictate a different rule (e.g., a 4th category surfaces). Refinement is recorded at the policy doc OR via /codify proposal upstream.

## Out of scope (this todo)

- Renaming `tests/integration/` → `tests/tier2/` to align directory naming with `rules/testing.md` § 3-Tier Testing (separate hygiene workstream).
- Adding the `commands/redteam` Round-1 spec-citation grep prepend (separate /codify proposal — see `journal/0015-...md` For Discussion question 2).

## Verification

```bash
# Citation grep audit (must return 0 MISSING lines)
grep -hoE 'tests/[a-z0-9_/]+\.py' specs/shamir-recovery.md specs/trust-vault.md specs/ledger.md \
  | sort -u \
  | while read p; do [ -f "$p" ] || echo "MISSING: $p"; done

# Split-state framings audit (must return 0 hits)
grep -iE 'phase-?1.*phase-?2|target.state|promised.*current|scaffold.*later|TBD|backend.follow-?up|FE.follow-?up|pending.accessor|to.be.wired|accessor.pending' specs/

# Sibling re-derivation: the analyst-or-equivalent agent walks every cross-reference
.venv/bin/python -m pytest tests/ -q   # MUST be green; suite is the load-bearing acceptance
```

## Cross-references

- `rules/spec-accuracy.md` Rules 1 / 2 / 4 / 5 / Audit Protocol.
- `rules/specs-authority.md` Rule 5b (sibling-spec re-derivation), Rule 6 (deviation acknowledgment).
- `rules/autonomous-execution.md` MUST Rule 4 (bounded-budget clause).
- `rules/zero-tolerance.md` Rule 1b (legitimate-deferral protocol — this todo IS the tracking issue).
- Round 2 redteam report: `04-validate/round-2-implement-redteam.md` § 2.3.
