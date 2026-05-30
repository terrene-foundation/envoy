---
type: DISCOVERY
date: 2026-05-29
created_at: 2026-05-29T00:00:00Z
author: co-authored
session_id: envoy-2026-05-29
session_turn: post-F10-F12a
project: phase-01-mvp
topic: real cascade engine never revoked descendants (EC-8(c) production violation)
phase: redteam
tags:
  [
    F14,
    F12,
    EC-8,
    cascade-revocation,
    trust-store,
    delegation-registry,
    hard-constraint,
  ]
---

# 0043 — DISCOVERY: real cascade engine never revoked descendants (EC-8(c))

## Context

Building **F12-a** (the real-infra EC-8(c) cascade test, journal/0042) surfaced
a **critical production bug** in the trust-store revocation path — far beyond
the F10 facade bug. The F12-a test, written to assert correct behavior, FAILED:
revoking a Day-1 root with a real delegated child returned only the root in
`revoked_agents` — the child survived. EC-2 line 42 + EC-8 line 116(c) (the
cascade hard-constraint) was violated by the REAL engine, not just the F10
sync facade.

## Root cause (confirmed by source read + two probes)

kailash's `cascade_revoke` discovers descendants through a `delegation_registry`
argument; when none is passed it falls back to a **fresh empty**
`InMemoryDelegationRegistry()` and finds zero descendants. envoy's
`TrustStoreAdapter.revoke` (`envoy/trust/store.py:614`) called `cascade_revoke`
WITHOUT that argument. envoy records delegations onto chains (via kailash's
`TrustOperations.delegate`) and its own `_snapshot_descendants` walks those
chains CORRECTLY (it saw `{bob}`), but that descendant graph was never handed
to the cascade. Two independent descendant-tracking surfaces; envoy populated
one (chains) and the cascade read the other (an empty registry).

Receipts (probes, both since removed):

- Real revoke of root with one delegated child: `revoked_agents=['alice-day1-root@example']` (child NOT revoked).
- envoy's own `_snapshot_descendants(root)` = `{bob-day6-telegram@example}` (envoy KNEW the child).
- Same `cascade_revoke` with a populated `InMemoryDelegationRegistry`: `revoked_agents=['bob…','alice…']` (child revoked — fix proven).

Why every prior test missed it: all cascade tests wired a stub
(`StubTrustRuntime` / hardcoded `cascade_responses`); the TIER-1 cascade tests
deliberately exercised only the idempotent no-op (no chain). The real engine
was never exercised with real descendants until F12-a.

## DECISION — fix (chain-derived registry at revoke time)

`TrustStoreAdapter.revoke` now builds the delegator→[delegatee] adjacency ONCE
from the persisted chains (refactored into `_build_delegation_adjacency` +
pure `_descendants_from_adjacency`, shared with `_snapshot_descendants`),
populates an `InMemoryDelegationRegistry` from it, and passes it to
`cascade_revoke`. Single source of truth (the persisted chains) → snapshot and
registry cannot drift, and the registry survives adapter restarts (it is
rebuilt each revoke; no separate persisted state).

Alternative rejected: maintain an in-memory registry populated in
`record_delegation`. Rejected because it would be empty after any process
restart for chains seeded in a prior process — silently re-introducing the bug.

`InMemoryDelegationRegistry` imported from the canonical
`kailash.trust.revocation.broadcaster` (pyright `reportPrivateImportUsage`
flagged the `…cascade` re-export).

Receipt: F12-a 5/5 (3 previously-failing now green); tier1+tier2+regression
1287 passed / 9 skipped; tier3+e2e 45 passed / 9 xfailed. Branch
`fix/phase-01-f14-cascade-registry-wiring`.

## Disposition of sibling shards

- **F12-a** — CLOSED (landed as the regression lock with this fix).
- **F12-b** (sync↔async facade bridge) — remains Phase-02 (F10's typed error points there).
- **F12-c** (production entrypoint wiring `revoke_prior_grant`) — remains Wave-2 Grant Moment.
- **F14** (this engine fix) — CLOSED.

## For Discussion

1. **Counterfactual:** three cascade findings landed this session (F10 facade
   silent-empty, F12 wiring-orphan, F14 engine-never-revoked). All three were
   masked by stub-based tests. Should the EC-6 sweep add a standing rule that
   security hard-constraints (cascade, clearance, redaction) MUST have at least
   one real-infra test before the stub-based tests count toward coverage?
2. **Data-referencing:** `_build_delegation_adjacency` is O(N×M) over all
   chains (the existing TODO names a Phase-02 `SqliteTrustStore` descendant
   query). At what chain count does the per-revoke full walk become a latency
   problem, and does that threshold arrive before Phase-02 ships the indexed
   lookup?
3. **Registry vs chains as source of truth:** the fix derives the registry
   from chains at revoke time. If a future Phase-02 path writes delegations to
   a registry but NOT to chains (or vice versa), the single-source-of-truth
   property breaks. Should the delegation-write path be asserted to populate
   exactly one canonical surface?
