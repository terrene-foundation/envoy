# 10 — Documentation + release readiness

**Purpose:** Documentation and release-readiness deliverables for Phase 01 ship. Most documentation work is already absorbed into primitive shards (per-spec docstrings + module-level READMEs); this file covers the repo-level surface.

**Source authority:** `02-plans/03-package-skeleton.md` § 1.5 + § 1.6 + shard 19 § 7.

---

## T-10-150 — Build README.md (repo root)

**Action:** README at repo root describing envoy-agent at high level for non-technical users per `rules/communication.md` (one-paragraph plain-language summary; followed by sovereignty-thesis pointer to BET-1 / BET-3 / BET-12 from brief).

**Sections:**

- One-paragraph summary (plain language).
- Quick start: `pipx install envoy-agent` → `envoy init` → `envoy up`.
- Architecture pointer: links to `specs/_index.md` for the 37 frozen specs.
- License: Apache-2.0 (per `rules/independence.md` variant — Envoy is open-source product).
- Independent verifier link: `terrene-foundation/envoy-ledger-verifier`.

**Capacity check:** ~150 lines markdown; 0 invariants of code; out of `rules/autonomous-execution.md` capacity scope.

**Estimate:** 0.25 session.

---

## T-10-151 — Build CHANGELOG.md (Phase 01 0.1.0 entry)

**Action:** Keep-a-Changelog format. Phase 01 opens with 0.1.0 entry: every primitive shipped, every EC met, every external gate cleared.

**Sections (0.1.0):**

- Added: 16 primitives + 8 channel adapters + independent verifier.
- Changed: N/A (initial release).
- Deprecated: N/A.
- Removed: N/A.
- Fixed: All 12 MED carry-forwards (R1-M-01..M-05, R2-M-01..M-05, R3-M-01, R3-M-02). Plus R2-H-01 + R2-H-02 LOAD-BEARING fixes.
- Security: Threat mitigations T-018 / T-019 / T-023 / T-070 / T-080 in regression suite.

**Estimate:** 0.25 session.

---

## T-10-152 — Verify NOTICES license aggregation

**Action:** Already drafted in T-05-91; this todo verifies the ACTUAL upstream package licenses match the aggregated text in `NOTICES`. License-text generator MUST run against `pip show <pkg>` for every dependency.

**Acceptance:** No upstream package's license diverges from the text reproduced in NOTICES. Spot-check `python-telegram-bot` LGPL-3.0+ full text reproduced.

**Estimate:** 0.25 session.

---

## T-10-153 — Phase 01 release-readiness checklist

**Action:** Compose `workspaces/phase-01-mvp/release-readiness.md` capturing the ship predicate per `01-analysis/02-mvp-objectives.md` § 5:

- [ ] All 9 ECs green (EC-1 through EC-9).
- [ ] /redteam 2 consecutive rounds 0 CRIT + 0 HIGH (EC-6).
- [ ] Cross-OS pipx install works (T-05-94).
- [ ] NOTICES license aggregation verified (T-10-152).
- [ ] CHANGELOG 0.1.0 entry present.
- [ ] All 12 MED carry-forwards resolved.
- [ ] R2-H-01 + R2-H-02 LOAD-BEARING fixes regression-tested.
- [ ] Phase 02 entry checklist captured (T-11-01 through T-11-05).
- [ ] No stubs / placeholders / `NotImplementedError` outside the 2 documented Phase 02 stubs (`envoy upgrade`, `envoy uninstall --destroy-vault`) per `rules/zero-tolerance.md` Rule 2.
- [ ] Spec-compliance verified: every spec primitive has at least one production call site within 5 commits per `rules/orphan-detection.md` Rule 1.

**Acceptance:** All 10 checkboxes signed off; ship.

**Blocks on:** Every Wave's milestone gate.

**Estimate:** 0.25 session.

---

## Cross-references

- Communication rule: `.claude/rules/communication.md`
- License variant: `.claude/rules/independence.md`
- Ship predicate: `01-analysis/02-mvp-objectives.md` § 5
- Phase 02 handoff: `11-phase-02-handoff.md`
