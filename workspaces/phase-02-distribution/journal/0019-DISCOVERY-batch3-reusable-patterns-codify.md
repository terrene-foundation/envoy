---
type: DISCOVERY
date: 2026-06-14
created_at: 2026-06-14T00:30:00Z
author: co-authored
session_id: continue-batch3-s5o
project: phase-02-distribution
topic: codify — reusable patterns from Wave-2 batch-3 (S5o + conformance wave)
phase: codify
tags:
  [
    codify,
    byte-identity,
    agent-delegation,
    worktree-orchestration,
    conformance,
    xfail-discipline,
  ]
relates_to: 0016-DECISION-wave2-redteam-convergence
---

# DISCOVERY — reusable patterns from Wave-2 batch-3

Five patterns surfaced executing batch-3 (S5o inline + the S2b/S2c/S3b
conformance wave). Captured for reuse across the remaining WS-6 / WS-1 shards
(S6a/S6b/S6c, S7v) and future cross-runtime work.

## 1. Cross-runtime byte-identity via shared pure delegation (NOT parallel re-impl)

Both runtime adapters' `first_time_action_gate` delegate to ONE pure function
(`envoy.runtime.observed_state.first_time_action_gate`) rather than each
re-implementing the gate. Byte-identity (`@byte_identical`) then becomes a
STRUCTURAL guarantee — the two runtimes execute the same code path — instead of
a property that must be tested into existence across two independent
implementations. The anti-pattern this avoids: parallel adapter implementations
that "should" match and silently drift. **Generalizes to every `@byte_identical`
Protocol method that does not genuinely need runtime-specific code** (the gate
needs no Rust binding — it is pure dict/JCS logic — so both adapters delegate).
Where a method DOES need runtime-specific behavior (device-key signing), the
conformance harness is the backstop; where it does not, shared delegation makes
the harness's job trivially green.

## 2. Empirical wired-surface verification beats a planning-time "buildable" claim

The prior `.session-notes` asserted N1/N2 were "buildable now". The S2b agent —
instructed to verify the wired surface EMPIRICALLY (construct the rs adapter via
`harness.resolve_runtime`, check each method for `RuntimeNotReadyError`) rather
than trust the claim — found N1/N2 route through `envelope_check`, which is
S6a-gated on BOTH adapters. They were authored-and-ready behind xfail, not built
as live loops that would have errored. **Lesson: a delegation prompt of the form
"build X on the landed seam" MUST instruct the agent to verify the wired surface
itself** (the verify-resource-existence discipline applied to agent delegation).
Planning-time buildability estimates decay as the substrate evolves; the agent
holds the live tools to check.

## 3. Parallel-serial-head orchestration (dense inline + mechanical to a worktree wave)

The session ran the densest, load-bearing, SAME-class-serialized shard (S5o —
the gate + store wiring) INLINE with full attention, while the mechanical,
independent, pattern-stamped work (3 conformance families on disjoint
`tests/conformance/` files) ran as a background 3-agent worktree wave. The
division of labor: **load-bearing logic stays inline; pattern-repetition work
goes to agents.** This captures the throughput multiplier (3 families in one
wall-clock unit) WITHOUT splitting attention on the hard part. The conformance
files being disjoint from the WS-6 source meant zero SAME-class contention
between the inline shard and the wave — the orchestration precondition.

## 4. xfail-with-gating-shard + wired-set guard (corpus ready, never fake-green)

Each conformance family authored the FULL corpus, with the substrate-gated lanes
marked `@pytest.mark.xfail(strict=False, reason="<gating shard: S6a/S6c>")` and a
companion guard test pinning that the gating method still raises today. When the
engine lands, the guard flips (the gated method stops raising) and surfaces
loudly → the signal to drop the xfail markers. This keeps a large corpus
authored-and-ready without shipping fake-green tests for unbuilt substrate, and
without losing the work to a "defer the whole family" decision. 87 xfails on
merged main are the ready-corpus; they convert to live as S6a/S6c land.

## 5. TYPE_CHECKING decoupling keeps the byte-identical path import-light

`session_boundary.py`'s `SessionRouter` import (annotation-only under
`from __future__ import annotations`) moved under `TYPE_CHECKING`. Importing the
PURE contracts (`is_recognized_fingerprint`, `reset_session_observed_state`) — as
the gate + both adapters do — therefore no longer drags the store + keystore
machinery into the byte-identical adapter path. A small move with a real payoff:
the cross-runtime gate path stays I/O-import-free, matching the "pure layer must
not transitively import the store" architecture S5o split into two modules to
preserve.

## For Discussion

1. Pattern 1 (shared pure delegation) makes the conformance harness trivially
   green for delegated methods — does that WEAKEN the harness's value for those
   methods (it can no longer catch a divergence that cannot exist), and should
   the harness instead focus its budget on the genuinely runtime-specific
   methods (device-key crypto, ledger) where drift is possible?
2. Pattern 2 caught a stale buildability claim THIS time because the agent was
   told to verify. What is the cost of making "verify the wired surface
   empirically" a STANDING clause in every conformance/seam-consumer delegation
   prompt (`rules/agents.md` § Specs-Context-in-Delegation), vs leaving it
   per-session — and would a generalized version belong as a COC proposal to
   loom rather than a project-local note?
3. Pattern 4's 87 xfails are a large standing "ready but not live" surface. At
   what count does an authored-but-xfail corpus stop being an asset and start
   being a maintenance liability (e.g. a spec edit that should invalidate a
   vector passes unnoticed because the lane is xfail)? Is a periodic
   "xfail-corpus drift" sweep warranted as S6a/S6c land?
