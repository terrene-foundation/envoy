---
type: DECISION
date: 2026-06-01
created_at: 2026-06-01T00:00:00Z
author: co-authored
session_id: envoy-2026-06-01
session_turn: post-PR66
project: phase-01-mvp
topic: F5.2 closed at 6/10 — `init`/`chat`/`ledger`/`grant` share one Phase-01 CLI-substrate blocker; "all subcommands functional" re-scoped to Phase 02
phase: implement
tags:
  [
    F5.2,
    envoy-grant,
    buildability,
    phase-01-ceiling,
    cli-substrate,
    rescope,
    value-prioritization,
    user-gated-closure,
  ]
---

# 0048 — DECISION: F5.2 closes at 6/10; remaining 4 subcommands share one Phase-02 substrate blocker

## Context

Prior sessions shipped 4 of the Wave-5 canonical CLI subcommands (`version`

- `posture` PR #63, canonical-surface fix PR #64, `connection` PR #65,
  `model` PR #66) on top of the 2 that landed with their primitives (`shamir`,
  `digest`) — **6 of 10 canonical subcommands** registered in
  `envoy/cli/main.py`. The `.session-notes` named `envoy grant` as the next
  target AND carried an explicit trap: _"grant may be blocked like ledger/chat —
  VERIFY the backing primitive's persistence + missing prod glue BEFORE
  committing."_

This session ran that verification before writing any `grant` code. Four
parallel deep-dive investigations (persistence model, shipped-sibling data
sources, canonical CLI contract, runtime/session instantiation), each
returning file:line evidence, were reconciled into one disposition. Every
load-bearing claim was then independently re-confirmed against live code by
the orchestrator (not trusted as agent grep output) per
`rules/verify-resource-existence.md` MUST-2.

## Decision

**F5.2 is CLOSED at 6/10.** `envoy grant` is **BLOCKED** in Phase 01, and the
block is a forest-level finding: the four unbuilt subcommands
(`init`, `chat`, `ledger`, `grant`) share ONE blocker class. The success
criterion "all subcommands functional" is RE-SCOPED to Phase 02 (user-gated
this session — Option A of a presented A/B/C choice).

## Why `grant` is blocked (verified evidence)

A Phase-01 "Grant Moment" exists only as live in-memory state on a running
runtime, with no process-independent projection a fresh CLI process could
reach:

- Pending grants live in `EnvoyGrantMomentRuntime._inflight: dict[str,
_PendingGrant]` (`envoy/grant_moment/runtime.py:402-403`) plus an
  event-loop-bound `asyncio.Future` (`runtime.py:305-306`, created at
  `709-716`, resolved at `739-743`). The Phase-01 scope comment is explicit:
  _"per-runtime-instance lifetime, not persisted across restarts; Phase 02
  lifts this into a TrustVault sub-store"_ (`runtime.py:392-401`).
- No file/sqlite/socket/FIFO/daemon/IPC persistence anywhere in the
  `grant_moment` package (imports are asyncio/hashlib/uuid only,
  `runtime.py:100-108`). The only durable writes are ledger rows recording
  intent (Phase A) and terminal decision (Phase B) — never a queryable
  `state="pending"` projection.
- The runtime is **never instantiated outside tests** (all 6
  `EnvoyGrantMomentRuntime(` sites are under `tests/`). The engine that would
  own a runtime + registered adapters — `envoy.runtime.session.SessionRouter`
  — does **not exist** (`envoy/runtime/` has no `session.py`). The production
  runtime adapter raises `Phase02SubstrateNotWiredError` for grant substrate
  (`envoy/runtime/adapters/kailash_py.py`). The web push path raises
  `PhaseDeferredError` (`envoy/channels/web.py`).
- `envoy grant` is not a registered command (only `shamir`/`digest`/`posture`/
  `version`/`connection`/`model` at `main.py:63-68`) and has **no canonical
  CLI contract**: it is a bare name in `specs/mvp-build-sequence.md:128` /
  `02-plans/01-build-sequence.md:264`, ABSENT from the cited-canonical shard-19
  §3.4 table, and the only handler shape is an empty Click sketch
  (`02-plans/03-package-skeleton.md:449-450`).

## Forest-level finding (the load-bearing conclusion)

The 6 shipped subcommands are exactly the 6 whose backing state lives on disk
independent of any running process: `posture` → SQLite posture store; `model`
→ `.env` + OS keychain; `connection` → OS keychain;
`shamir`/`digest`/`version`. The 4 remaining are exactly the 4 that depend on
substrate Phase 01 deliberately deferred:

- `ledger export` — needs the **T-01-21 file-backed audit store**. The only
  production `EnvoyLedger` wiring (`envoy/daily_digest/bootstrap.py:78`) uses
  in-memory `InMemoryAuditStore`, lost on exit. The file-backed
  `SqliteAuditStore` **already exists upstream** (`kailash/trust/audit_store.py:668`),
  unwired.
- `grant` — needs a durable pending-grant projection AND a long-running
  session model (both above).
- `init` / `chat` — additionally need the Boundary-Conversation bootstrap +
  production `CommitmentBinder` (F21).

**Nearest single unblock across all four:** wire the existing upstream
`SqliteAuditStore` into `EnvoyLedger`. That alone makes `ledger export`
buildable as a one-shot CLI and is the foundation the other three also need.

## Alternatives considered

- **Build a narrow `grant` surface now** — REJECTED. Every candidate surface
  (respond-to-pending, list-pending, list-history) reads a store that does not
  exist on disk in Phase 01; shipping it would wire a command to a
  non-existent store — the fake-store stub blocked by `rules/zero-tolerance.md`
  Rule 2 + `rules/verify-resource-existence.md` MUST-3.
- **Authorize the Phase-02 substrate now (Option B)** — DEFERRED. The full
  surface (file-backed store → pending-grant TrustVault sub-store →
  SessionRouter/session model) is multi-shard Phase-02 scope, not a CLI
  wrapper; it expands the phase boundary. Recorded as the next workstream with
  `ledger`-via-existing-`SqliteAuditStore` named as the first slice.

## Value-anchor (per `rules/value-prioritization.md` MUST-6)

The re-scoped success criterion is user-authored — `workspaces/phase-01-mvp/02-plans/01-build-sequence.md`
line 334 (mirrored in `specs/mvp-build-sequence.md:190`), verbatim:
**"All 11 CLI subcommands functional."** This conflicts with the Phase-01
boundary because 4 of the canonical subcommands depend on deferred substrate.
Resolving a success-criterion-vs-phase-boundary conflict is a structural
(human-gated) decision; the user chose Option A (close at 6/10, re-scope to
Phase 02). User gate satisfies `value-prioritization.md` MUST-4 (closure of
value-bearing deferred work requires explicit user approval in-session).

## Consequences & follow-up

- `specs/mvp-build-sequence.md:190` + `02-plans/01-build-sequence.md:334`
  Milestone-5 criterion re-scoped to "6 of 10 functional in Phase 01;
  remaining 4 → Phase 02".
- New Phase-02 hooks item 9 added to `specs/mvp-build-sequence.md` recording
  the shared blocker + first-unblock path.
- `.session-notes` forest ledger: F5.2 → CLOSED-at-6/10; the 4-share-one-
  blocker finding recorded.
- Next-workstream candidate (NOT auto-started): wire upstream
  `SqliteAuditStore` into `EnvoyLedger` → unblock `ledger export`.

## For Discussion

1. **Counterfactual:** if Phase 01 had wired `SqliteAuditStore` from the start
   (instead of `InMemoryAuditStore`), would `ledger export` AND a
   read-only-`grant`-history surface both have become buildable as one-shot
   CLIs — collapsing the "4 remaining" to "2 remaining" (only `init`/`chat`,
   which additionally need the BC bootstrap)? Is the in-memory ledger choice
   the true critical-path bottleneck for Phase-01 CLI completeness?
2. **Data-referencing:** the shard-19 §3.4 table (cited everywhere as
   canonical) has no `grant`/`model`/`connection`/`version` rows yet
   `specs/mvp-build-sequence.md:128` lists all four — the canonical anchor and
   its consumer have drifted. Does closing F5.2 warrant reconciling that drift
   now (a fifth edit), or is it a separate R1-M-01-class cleanup?
3. Does "Phase 01 ships" (Milestone-5 convergence) still hold with 6/10
   subcommands, or does re-scoping the criterion mean Phase-01 release should
   wait until the `ledger`-via-`SqliteAuditStore` slice lands and brings the
   count to 7/10?
