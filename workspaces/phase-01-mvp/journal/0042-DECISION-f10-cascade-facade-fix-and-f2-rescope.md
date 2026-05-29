# 0042 — DECISION: F10 cascade-facade fix + F2 verifier re-scope (EC-9 contamination)

Date: 2026-05-29
Type: DECISION
Session: post-PR-#51-merge (R4+R5 convergence landed on main)

## Context

After PR #51 merged (R4+R5 rolling-subscope convergence), the user authorized
two pieces of work this session: (1) F2 — the independent ledger verifier
(cross-repo `terrene-foundation/envoy-ledger-verifier`), and (2) on re-scope,
F10 — the cascade-revoke facade Tier-2 test.

## DECISION 1 — F2 re-scoped to a FRESH session (EC-9 producer-contamination)

`01-analysis/02-mvp-objectives.md` EC-9 line 128 (verbatim): _"A verifier CLI
tool ships in a separate repo (proposed: `envoy-ledger-verifier` under
`terrene-foundation/`), implemented **without reference to Envoy producer
source**, in either Python (**different agent / different package**) or Rust
(**different language entirely**)."_

This session has read producer source extensively (EC anchors, PR #51 merge,
`07-independent-verifier-design.md` which cites producer file:line). It is
therefore **not** "a different agent without reference to producer source."
Authoring the Python verifier from this session would structurally fail EC-9.

**Disposition (user-approved):** the Python `envoy-ledger-verify` variant (the
REQUIRED EC-9 deliverable per `07-independent-verifier-design.md` §3.2 lines
103–106) MUST be authored by a FRESH session (clean context = "different
agent"). The Rust variant uses "different language entirely" as its isolation
surface and would be EC-9-compliant from any session, but it is the OPTIONAL
(not REQUIRED) Phase-01 deliverable.

**Handoff for the fresh session:**

- Bounded scope: bootstrap `terrene-foundation/envoy-ledger-verifier` per
  `07-independent-verifier-design.md` §3.1 (separate repo) + §3.2 (Python
  reference variant first) + §3.5 (mutation battery = EC-4 acceptance gate).
- Cross-repo gate: the fresh session MUST satisfy `rules/repo-scope-discipline.md`
  User-Authorized Exception (all five conditions) and write its OWN
  pre-action journal receipt + `cross-repo-authorized: terrene-foundation/envoy-ledger-verifier`
  marker BEFORE the first cross-repo command.
- Do NOT read envoy producer source in that session (EC-9 isolation).

## DECISION 2 — F10 fixed Option A (honest typed-error defer) + Tier-2 test

`KailashPyRuntime.trust_cascade_revoke` (sync per `specs/runtime-abstraction.md:31`)
called the only real backing store `TrustStoreAdapter.revoke` (`async def`)
without await, then `getattr(result, "revoked_agents", [])` → silently returned
`set()` + leaked an unawaited-coroutine RuntimeWarning. A silent empty cascade
invisibly violates the EC-2 line 42 + EC-8 line 116(c) cascade hard-constraint.

**Disposition (user-approved Option A):** detect the coroutine, close it, raise
typed `Phase02SubstrateNotWiredError` naming the sync↔async bridge as the
Phase-02 substrate. Sync-store branch unpacks `RevocationResult` with no silent
default. F10 Tier-2 facade test (`tests/tier2/test_trust_cascade_revoke_facade_wiring.py`)
pins no-store guard + async-store honest-defer (+ coroutine-leak regression
guard) + EC-8(c)-shaped sync-store forwarding. Closes R4 reviewer MED-2.

Receipt: 5/5 F10 tests pass; 275 tier2 passed / 9 pre-existing skips; 1641
tests collect clean. Branch `fix/phase-01-f10-cascade-revoke-facade`.

## New findings surfaced this session (recorded for the F4/EC-6 sweep)

- **F12 (NEW) — cascade-revoke production WIRING orphan.** No Phase-01
  production path wires real store → `KailashPyRuntime` → `CascadeRevocationOrchestrator`.
  Every cascade test wires `StubTrustRuntime`; the async `TrustStoreAdapter.revoke`
  - orchestrator each work in isolation, but the end-to-end production cascade
    path is unwired. EC-8(c) ("Day-1 grant revokes Day-6 cross-channel child")
    is therefore demonstrated only via stubs. Value-anchor: `01-analysis/02-mvp-objectives.md`
    EC-8 line 116(c). Disposition: F4/EC-6-level orphan-wiring concern, its own
    shard — NOT folded into F10 (would exceed shard budget + spec-deviation gate).
- **F13 (NEW) — pre-existing pyright type-narrowing in `kailash_py.py`.**
  `runtime_verify` (line ~490) passes `str | bytearray | memoryview` to
  `verify_signature(signature: str, public_key: str)`. Pre-existing (untouched
  by F10); surfaced via line-shift re-scan. Different bug class. Queued cleanup.
