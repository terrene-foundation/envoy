---
type: DISCOVERY
date: 2026-05-03
created_at: 2026-05-03T00:00:00Z
author: agent
session_id: phase-01-mvp-shard-3
session_turn: 1
project: envoy
topic: kailash-py upstream velocity closed 12 of 13 Phase 00-filed issues in 5 days
phase: analyze
tags: [upstream-velocity, kailash-py, freshness-gate, phase-01, issues, ledger]
---

# 0002 — DISCOVERY — `kailash-py` upstream readiness materially improved since Phase 00 baseline

## What was discovered

The freshness gate executed at the start of /analyze shard 3 (per `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` § "Why this matters for the kailash-py survey shard") returned a **velocity signal that is materially stronger than the Phase 00 baseline assumed**.

Direct status queries against the 13 Phase 00-filed `terrene-foundation/kailash-py` issues (#594–#606, per `workspaces/phase-00-alignment/issues/manifest.md`):

- **12 of 13 CLOSED** between 2026-04-24 and 2026-04-26 (5 days after filing)
- **Only #596 (`TieredAuditDispatcher`) OPEN**

Notably, **ISS-36 (#605) — PACT N4/N5 conformance vector Python runner — was the single previously-identified Phase 02 blocker on the kailash-py axis**. It closed 2026-04-25.

## Why this is journal-worthy

The Phase 00 brief at `workspaces/phase-00-alignment/01-analysis/03-primitive-reconciliation.md` § 4 categorized the upstream gap into "Phase 01 YELLOW (Envoy implements, upstream issues filed)" assuming most of the 13 issues would remain open through Phase 01 build. The 12-of-13 closure inverts that assumption:

1. **`PlanSuspension`, `OrchestrationRuntime`, `apply_read_classification`, BudgetTracker threshold-callback, algorithm-identifier schema, Shamir SLIP-0039 integration** all moved from "Envoy waits or implements locally" to "Envoy uses upstream surface" — pending shard-level verification of the actual closed-PR content.
2. **The Phase 02 blocker (N4/N5 runner) closed structurally**. Phase 02 entry can begin without Phase 01 needing to file follow-up pressure.
3. **The freshness-gate methodology mandated by `journal/0001` paid off on first execution**. Without re-running the gate, the readiness doc would have anchored on a stale baseline and the per-primitive deep-dives (shards 4–19) would have over-scoped Envoy-new-code by 7–10 primitives' worth.

## What it changes for downstream shards

Per `01-analysis/03-kailash-py-mvp-readiness.md` § 5 the verification protocol for shards 4–19 is:

1. Read the freshness-delta column for the primitive
2. Fetch the close comment of the referenced ISS via `gh issue view <N> --repo terrene-foundation/kailash-py --json closedAt,body,timelineItems` to find the linked PR or commit
3. Open the upstream code at the named module path; confirm symbol existence + spec match
4. If symbol does NOT exist or differs, escalate via `01-shard-plan.md` § 4 failure-mode protocol

Shards likely affected (verification required):

- Shard 6 (Envoy Ledger) — STILL must implement `TieredAuditDispatcher` locally; #596 OPEN. Indirect benefits from #707/#711 transactions, #757/#756 canonical-input pin, #731 timestamp.
- Shard 9 (Authorship Score) — ISS-12 (#597) closed; verify Phase-13 5-posture canonical set lands as expected.
- Shard 11 (Daily Digest) — ISS-26 (#602) closed; previously C-grade `OrchestrationRuntime` may now be A-grade; **needs surface verification before sizing Envoy-new-code**.
- Shard 13 (Model adapter) — Significant upstream improvements (#791, #790, #788, #762, #763, #764, #761, #740, #736, #734); verification will likely reduce Envoy-new-code surface to a thin BYOM shim.
- Shard 15 (Shamir recovery) — ISS-37 (#606) closed; verify whether Envoy uses upstream `kailash-py` Shamir or pulls `slip39` directly.

## What it does NOT change

1. **#596 TieredAuditDispatcher remains OPEN** — Phase 01 must implement the hash-chain Ledger writer locally per `rules/zero-tolerance.md` Rule 4 (no SDK workarounds; implement to spec, propose upstream).
2. **The Rust binding side (kailash-rs ISS items #503–#521) was NOT re-checked** in this freshness gate. Phase 02 entry must run the equivalent gate against `esperie-enterprise/kailash-rs`.
3. **Closed-status ≠ landed-feature.** Per `rules/git.md` § "Issue Closure Discipline", closure should reference a PR / commit. The shard-level verification protocol is the structural defense; the closure count alone is a "look here" signal, not evidence of correctness.

## Velocity finding (use carefully)

12 issues closed in 5 days from a single Foundation contributor batch is a high-velocity signal. The Foundation's open-source Python SDK is moving fast on Phase 01-relevant primitives. This implies:

- Phase 01 shard execution (4–19) should re-check upstream **at the start of each shard**, not just at this single shard 3 gate. A primitive surveyed today may improve by next week.
- The freshness gate is a **per-shard-class methodology**, not a one-time event. Add to per-shard structure in `01-shard-plan.md` §2 (per-shard structure step list) for shards 4–19.

## For Discussion

1. **Counterfactual**: If only 4 of 13 issues had closed (instead of 12), would Phase 01 still be net-improved versus the Phase 00 baseline? At what closure-rate does the upstream-readiness signal flip from "use upstream confidently" to "verify each primitive deeply before assuming"? Concretely: if shards 4–19 each spend ~10 minutes on the upstream-code-verification step (per the §5 protocol in the readiness doc) but find that 1 in 5 closed issues did NOT actually land code, what's the cost of the verification protocol vs the cost of skipping it?

2. **Specific data**: ISS-37 (#606) Shamir SLIP-0039 closed 2026-04-26. The Phase 00 reconciliation grade was C (absent). Shard 15 must determine whether the closure landed (a) full Shamir integration in `kailash-py`, (b) a wrapper around the `slip39` Python package, or (c) just docs / interface design with no executable code. Each of (a)/(b)/(c) implies a different Envoy-new-code surface for Phase 01 backup ritual. Should shard 15 fire next (out of order) to reduce the Shamir uncertainty before shard 6 (Envoy Ledger, which depends on Trust store, which depends on Shamir backup ritual hooks)?

3. **Methodology**: `journal/0001` mandated a freshness gate at shard 3 specifically. The 12-of-13 finding suggests freshness gates should be _per-shard_ for shards 4–19, not just at shard 3. Should `01-shard-plan.md` §2 per-shard structure list be amended to add "Step 0: re-run upstream freshness query for the primitive's owning issues"? If yes, what's the right scope — only the primitive's owning ISS, or all 13 ISS items + all surrounding 04-21 → today closures?

## Cross-references

- Bridge journal entry: `workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`
- Readiness doc: `workspaces/phase-01-mvp/01-analysis/03-kailash-py-mvp-readiness.md` § 2 + § 5
- Phase 00 issue manifest: `workspaces/phase-00-alignment/issues/manifest.md`
- Sharding plan: `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 2 (shard 3 status)
- Closure-discipline rule: `.claude/rules/git.md` § "Issue Closure Discipline"
- Workaround prohibition: `.claude/rules/zero-tolerance.md` Rule 4
