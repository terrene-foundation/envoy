# 0001 — CONNECTION — Phase 00 to Phase 01 bridge

**Type:** CONNECTION (non-obvious relationship between requirements / components / findings)
**Phase:** Phase 01 MVP — /analyze shard 1
**Date:** 2026-05-03
**Status:** Active

---

## The connection

Phase 00 produced a **complete frozen architecture** (37 specs + 9 ADRs + 12 BETs). Phase 01 produces an **implementation architecture**. These are different work products — and the non-obvious connection is that Phase 01 /analyze should NOT re-derive any frozen artifact.

The trap is that "the analysis phase" naturally invites re-derivation: an agent reads `boundary-conversation.md` and starts to question whether the 15-minute target is right. Re-derivation looks like rigour, but it costs:

1. **Direct cost** — re-deriving 37 specs is multi-session work that produces no new architectural value
2. **Drift cost** — re-derivation may disagree with the frozen spec, producing silent contradiction
3. **Re-redteam cost** — any spec edit triggers MUST Rule 5b (37-sibling re-derivation, 6 historical rounds to converge)

The structural defense: Phase 01 /analyze docs MUST cite Phase 00 artifacts by path + section, never paraphrase. The mantra is: "Phase 00 said X (cite); Phase 01 implementation must wire X via Y."

## Why this matters for shards 4–19

Each primitive deep-dive shard targets one frozen spec. The temptation, on opening (e.g.) `specs/envelope-model.md`, is to re-evaluate the envelope model. Resist this. The shard's question is NEVER "is this spec right?"; it is ALWAYS "given this spec is frozen, how do I wire `kailash-py` to deliver it?"

If a primitive deep-dive surfaces a HIGH gap in the frozen spec, that triggers the failure-mode protocol in `01-shard-plan.md` §4 — STOP the deep-dive, convene a MUST-Rule-5b sweep, edit the spec under full-sibling redteam economics. Continuing the deep-dive against a contested spec produces an implementation that may need to be redone.

## Why this matters for the kailash-py survey shard

Shard 3 re-reads `02-kailash-py-survey.md` from Phase 00. The Phase 00 survey was conducted on 2026-04-21; eight days earlier than this entry. `kailash-py` is an actively-developed upstream — the 12 issues filed in Phase 00 may have closed (which improves Phase 01 surface) or new gaps may have surfaced.

**Action item for shard 3:** before consuming the Phase 00 survey, run `gh issue list --repo terrene-foundation/kailash-py --state closed --search 'is:closed closed:>2026-04-21'` (or equivalent) to identify what's changed upstream. The 2026-04-21 survey is a STARTING POINT, not the canonical state for Phase 01.

This is a recurring pattern: any analysis that depends on external upstream state has a freshness gate before consumption. Phase 01 /analyze should treat the kailash-py survey, the issue manifest, and the upstream-PR state as _snapshots_ and re-snapshot them at the consuming shard.

## Why this is journal-worthy and not in the inheritance map

The inheritance map (`00-inheritance-from-phase-00.md`) lists **what** is inherited. This journal entry captures **how the inheritance must be consumed** — a process pattern that doesn't fit a manifest. Future shards / sessions need this guidance because the failure mode (re-derivation drift, surveyed-state staleness) is a methodology error, not a content one.

## Cross-references

- Inheritance map: `workspaces/phase-01-mvp/01-analysis/00-inheritance-from-phase-00.md`
- Sharding plan: `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 4 + § 5
- MUST Rule 5b: `.claude/rules/specs-authority.md`
- Phase 00 issue manifest: `workspaces/phase-00-alignment/issues/manifest.md`
- Phase 00 kailash-py survey: `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md`
