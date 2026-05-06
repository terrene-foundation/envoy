---
type: DISCOVERY
date: 2026-05-06
created_at: 2026-05-06T00:00:00Z
author: agent
session_id: phase-01-mvp-implement-t-01-12
session_turn: 1
project: envoy
topic: shard 5 cited sync TrustOperations API; kailash 2.13.4 ships async + 3-dep constructor — T-01-12 scope expansion required
phase: implement
tags:
  [
    trust-store,
    async-migration,
    shard-5-deviation,
    kailash-py-2.13.4,
    authority-registry,
    key-manager,
    capacity-budget,
  ]
---

# 0009 — DISCOVERY — Trust store async migration required + missing dependency declarations

## What was discovered

T-01-12 (Build envoy/trust/store + types) opened against shard 5 § 4 steps 1-2. Context anchoring + kailash-py 2.13.4 inspection surfaced multiple deviations between shard 5's cited API and the actual kailash-py surface:

| Shard 5 said                                             | kailash-py 2.13.4 actually exposes                                                                         |
| -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `SqliteTrustStore` from `kailash.trust`                  | `kailash.trust.chain_store.sqlite.SqliteTrustStore` (correct path; just nested deeper)                     |
| Sync `TrustOperations.delegate()` / `.establish()`       | **Async** `TrustOperations.delegate()` / `.establish()` (coroutines)                                       |
| Sync `SqliteTrustStore.initialize/get_chain/store_chain` | **Async** all three                                                                                        |
| `TrustOperations(trust_store)` 1-arg constructor         | `TrustOperations(authority_registry, key_manager, trust_store, max_delegation_depth=10)` 3-arg constructor |
| `CapabilityRequest(name=cap)` field                      | `CapabilityRequest(capability, capability_type, constraints=[], scope={})` — `name` does not exist         |

## Why this is journal-worthy

This is the third deviation surfaced during /implement (journal 0007 pyproject pin, journal 0008 intersect deferral, this one). All three share the same root cause: shard authoring at /analyze time cited specific kailash-py symbols + signatures without verifying them at HEAD against the running env. Per journal/0001's freshness-gate methodology, the shards should have re-derived against `gh issue view` + the upstream source at HEAD — but for SDK-method signatures (not just issue closure), the freshness check needs to extend to `inspect.signature(...)` of the cited symbol.

## Concrete impacts on T-01-12

1. **TrustStoreAdapter MUST be async.** Per `rules/patterns.md` § "Paired Public Surface — Consistent Async-ness", you cannot wrap async kailash-py in a sync envoy facade via `asyncio.run()` — the event-loop-already-running RuntimeError lights up in every async caller (Boundary Conversation Kaizen agents, Daily Digest scheduler, etc.). The envoy facade MUST be async.

2. **TrustStoreAdapter constructor needs 2 more dependencies:**
   - `AuthorityRegistry` — kailash-py ships `OrganizationalAuthorityRegistry` (Phase 01 may stub a degenerate single-authority instance from envoy's Genesis seed).
   - `KeyManager` — kailash-py ships `InMemoryKeyManager()` (no-arg constructor; in-process keypair generation; satisfies Phase 01 single-process Trust Vault).

3. **CapabilityRequest field rename:** envoy `DelegationRequest.capabilities: tuple[str, ...]` projects to `CapabilityRequest(capability=cap, capability_type=CapabilityType.ACTION)` — Phase 01 disposition is `CapabilityType.ACTION` for every authored capability (per `specs/posture-ladder.md` mapping; ACCESS + DELEGATION are Phase-2 entry).

4. **Tier 1 tests use pytest-asyncio.** `pyproject.toml` has `asyncio_mode = "auto"`; tests just need `async def test_...`.

5. **Capacity budget:** ~500 LOC instead of ~250. Authority registry + key manager bootstrap (~100 LOC); async adapter (~250 LOC); async tests (~150 LOC). Right at the budget edge per `rules/autonomous-execution.md`. Still within 1 session if the work is focused.

## Disposition options

### Option A — Async migration (CHOSEN if user approves)

Pros: matches kailash-py upstream; matches `rules/patterns.md` § Paired Public Surface; structurally forced by Boundary Conversation + Grant Moment async needs anyway.

Cons: T-01-12 LOC 2× shard 5's estimate; downstream T-01-16 wiring tests use pytest-asyncio; envelope compiler stays sync (it doesn't touch trust persistence) which is a mixed-async-ness package — but the boundary is clean (envelope is pure-function; trust is I/O).

### Option B — Bootstrap kailash-py issue + stub envoy.trust until upstream-sync

Pros: matches shard 5 exactly.

Cons: requires an issue + upstream PR to add a sync facade; blocks T-01-12 indefinitely; envoy.trust as a stub until then is a Rule-2 violation per zero-tolerance.

### Option C — Stop and re-derive shard 5 against current kailash-py

Pros: closes the freshness-gate methodology gap at its source.

Cons: re-deriving 16 primitive shards (4-19) for signature accuracy is N sessions of work. The signature mismatches are mechanical — only the ones that surface during /implement need re-derivation, not the whole shard tree.

## Recommendation

**Option A.** The async migration is structurally forced by the upstream API and the `rules/patterns.md` § Paired Public Surface rule. Capture-as-deviation pattern (matching journal/0007 + 0008) is consistent with the user's "go A" approval flow. Mid-/implement freshness-gate (Option C lite) — apply to each shard only as the corresponding /implement turn opens.

If approved, T-01-12 turn-2 ships:

- envoy/trust/{**init**, types, errors, store}.py (async; ~500 LOC; 6 invariants)
- AuthorityRegistry + KeyManager bootstrap inside TrustStoreAdapter constructor
- Genesis seeding via async `TrustOperations.establish`
- Delegation routing via async `TrustOperations.delegate` (R2-M-04)
- Tier 1 tests using pytest-asyncio (~6-8 tests; principal_id discipline + Genesis seeding + delegation routing)

## Mid-cleanup state

Partial T-01-12 work exists at `envoy/trust/{__init__, types, errors, store}.py` with sync signatures that don't compile against kailash-py. Pyright flags 8 type errors. Tests have not been written.

Two paths from here:

1. **Continue Option A** — rewrite store.py to async; finish T-01-12 in the same /implement turn.
2. **Roll back partial** — `rm -rf envoy/trust/`, leave T-01-12 for a fresh turn with full async context loaded.

## For Discussion

1. **Counterfactual**: If shard 5's kailash-py freshness gate had included `inspect.signature(SqliteTrustStore.initialize)`, the async-ness would have surfaced at /analyze time. /todos planning would have allocated 2 sessions for T-01-12 instead of 1. Net cost is the same (the work doesn't disappear) but the surprise lands at planning, not implementation. Recommend amending shard authoring to require `inspect.signature` of every cited method.

2. **Specific data**: shards 6 (Ledger), 9 (Authorship), 10 (Grant Moment), 11 (Daily Digest), 12 (Budget) all interact with kailash-py persistence layers. Each is likely to surface the same async-vs-sync deviation. Should the wave-1 todos pre-emptively flip to async OR re-derive against `inspect.signature` per shard?

3. **Methodology**: This is the 3rd /implement-time DISCOVERY in 2 turns. Recommend adding a "kailash-py signature freshness gate" mechanical sweep to every /implement turn's Step 2 context-anchoring: `inspect.signature(...)` every cited public symbol; flag deviations before writing code.

## Cross-references

- T-01-12 todo: `workspaces/phase-01-mvp/todos/active/01-wave-1-foundation.md` § T-01-12
- Shard 5: `workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md` § 4 + § 2
- Prior deviations: `journal/0007-DISCOVERY-pyproject-stale-kailash-pin.md`, `journal/0008-DECISION-intersect-deferred-to-wave-3.md`
- Async-ness rule: `.claude/rules/patterns.md` § "Paired Public Surface — Consistent Async-ness"
- Freshness gate methodology: `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`
- Capacity rule: `.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget
