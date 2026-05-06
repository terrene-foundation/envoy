---
type: DISCOVERY
date: 2026-05-06
created_at: 2026-05-06T00:00:00Z
author: agent
session_id: phase-01-mvp-implement-bootstrap
session_turn: 1
project: envoy
topic: pyproject.toml stale kailash pin contradicts Phase 01 brief; aligning to brief authority
phase: implement
tags:
  [
    bootstrap,
    pyproject,
    kailash-version,
    pure-python,
    rust-backed,
    discovery,
    align-to-brief,
  ]
---

# 0007 — DISCOVERY — pyproject.toml stale `kailash>=3.20.0` pin contradicts Phase 01 brief

## What was discovered

At /implement opening (2026-05-06), the first context-anchoring pass per the /implement workflow surfaced a foundational dependency mismatch:

| Source                                                    | Says                                                                                  |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `pyproject.toml` (current, line 33)                       | `kailash>=3.20.0`                                                                     |
| `briefs/00-phase-01-mvp-scope.md` § Components            | Phase 01 uses **pure-Python runtime only**; `kailash[shamir,nexus,kaizen]>=2.13.4`    |
| `DECISIONS.md` ADR-0001 phase migration                   | Phase 01 = `kailash-py` (pure-Python); Phase 02 = `kailash-rs-bindings` (Rust-backed) |
| `02-plans/01-build-sequence.md` § 2 + `T-05-91`           | Wave 5 packaging task pins `kailash[shamir,nexus,kaizen]>=2.13.4`                     |
| `.claude/rules/independence.md` (rs-variant, just synced) | "this product ships kailash-enterprise" (Rust-backed)                                 |
| Installed env (`pip list`)                                | `kailash-enterprise 3.19.0` (Rust-backed); `kailash` package NOT installed            |

## What's actually on PyPI

Verified at `https://pypi.org/pypi/kailash/json`:

- `kailash 2.13.4` (pure-Python) IS available with extras `[dataflow, kaizen, nexus, pact, ml]`.
- The brief's `[shamir]` extra is a misname — Shamir support is in base `kailash` per shard 15 (`kailash.trust.vault.shamir` module imported directly, not via extra).
- `kailash-enterprise 3.19.0` is the Rust-backed binding (separate package; conflicts with `kailash` on the import namespace).

## Why this is journal-worthy

The mismatch is foundational — every implementation choice from T-01-10 onward depends on which Python package the import `from kailash.trust.pact.envelopes import ...` resolves to. Building against `kailash-enterprise` 3.19.0 produces a Phase 02 implementation that contradicts ADR-0001's phase migration table. Building against `kailash 2.13.4` per brief produces the intended Phase 01.

## Disposition

**Align to brief authority.** The brief + ADR-0001 + the user-approved /todos plan all agree: Phase 01 uses pure-Python `kailash`. The stale `pyproject.toml` pin pre-dates the Phase 01 brief finalization (the README and ADR-0001 reference `kailash 3.x` because the project initially planned to use the Rust-backed binding directly; ADR-0001 was revised to defer Rust to Phase 02 — pyproject.toml didn't get updated when ADR-0001 was revised).

The just-synced variant rule (`rules/independence.md`) describes envoy as "a proprietary product that ships kailash-enterprise" — this is a template default from the rs-axis COC USE template. It does NOT match envoy's actual project authority (envoy is "Foundation-stewarded, fully open-source, pure-Python pip-install agent" per brief). The variant rule is consumed for general guidance; project authority overrides it for project-specific facts.

### Concrete actions

1. Update `pyproject.toml` line 33: `kailash>=3.20.0` → `kailash[nexus,kaizen,dataflow,pact]>=2.13.4` (drop misnamed `[shamir]`; add `[dataflow,pact]` per brief's actual primitive coverage).
2. Update `pyproject.toml` line 27-32 commentary: replace "Rust-accelerated Python binding" framing with "pure-Python runtime per Phase 01 ADR-0001" framing.
3. `uv pip uninstall kailash-enterprise && uv sync` to flip the import-namespace winner.
4. Verify `python -c "import kailash; ..."` resolves to pure-Python kailash.

## What this does NOT change

- ADR-0001 (already correct).
- The brief (already correct).
- The /todos plan (already pinned to brief — `T-05-91` named the right dep shape).
- The variant `independence.md` rule (template default; doesn't apply to envoy's open-source posture; we'll capture in /codify if/when the discrepancy with envoy's actual posture becomes a recurring friction point).

## For Discussion

1. **Counterfactual**: If the variant rule's "proprietary product" framing IS the project authority and the brief is wrong, then Phase 01 should use kailash-enterprise. But ADR-0001 is the architecture-decision record specifically establishing the phase-migration; ADR-0001 trumps a synced template default. The user-approved plan is consistent with ADR-0001 + the brief. If the user wants to change architecture (pure-Python → Rust-backed for Phase 01), that's a brief revision + ADR amendment + re-/analyze, not a quiet pyproject.toml flip.

2. **Specific data**: Phase 02 entry per `11-phase-02-handoff.md` T-11-04 wires `kailash-rs-bindings` to the runtime adapter slot. Phase 02 implementation will install BOTH `kailash` (Phase 01) and `kailash-rs-bindings` (or whatever the Rust binding ships as) side-by-side, with the runtime adapter selecting via `pyproject.toml` extras. This entry's correction is non-controversial against that future state.

3. **Methodology**: Should every /implement turn run a "context anchoring sanity check" that diffs `pyproject.toml` vs the most-recently-modified `02-plans/*.md` to surface this class of issue early? Cost: one greppy bash call per /implement opening. Benefit: catches stale-config issues before they propagate into wasted implementation work. Recommend including in the /implement skill's Step 2 mechanical sweeps.

## Consequences

- **Immediate**: pyproject.toml updated; `kailash 2.13.4` installed; `kailash-enterprise` uninstalled.
- **Short-term**: Wave 1 implementation T-01-10 (`envoy/envelope/`) builds against pure-Python `kailash.trust.pact.envelopes` per brief.
- **Phase 02**: kailash-rs-bindings adapter wiring (T-11-04) re-installs the Rust binding alongside; runtime selects via env flag.

## Cross-references

- Brief: `briefs/00-phase-01-mvp-scope.md` § Components + § Constraints
- ADR-0001: `DECISIONS.md` § ADR-0001 Runtime architecture
- Plan: `workspaces/phase-01-mvp/02-plans/01-build-sequence.md`
- Approval: `journal/0006-CONNECTION-todos-approved-handoff-to-implement.md`
- Variant rule: `.claude/rules/independence.md` (rs-axis template default; not project authority for envoy)
- Phase 02 binding wiring: `workspaces/phase-01-mvp/todos/active/11-phase-02-handoff.md` § T-11-04
