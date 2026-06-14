---
type: DISCOVERY
date: 2026-06-14
author: agent
project: phase-02-distribution
topic: codify — still-owed reusable patterns from S4g-1 (cross-process grant), S5b (shared-owner boundary signal), S3a (byte-identical cross-OS conformance)
phase: codify
verified_id: 548F2C562EB4246D025FA80A70552B124755B685
tags:
  [
    codify,
    cross-process-rendezvous,
    shared-contract-ownership,
    byte-identity,
    cross-os-nfc,
    ws6,
  ]
relates_to: 0019-DISCOVERY-batch3-reusable-patterns-codify
---

# DISCOVERY — still-owed reusable patterns (S4g-1, S5b, S3a)

`journal/0019` captured the batch-3 S5o + conformance-wave patterns. This entry
closes the codify debt the `.session-notes` ledger still listed: the three
reusable patterns from **S4g-1** (cross-process `grant`), **S5b** (the
session-boundary signal), and **S3a** (E1–E4 byte-identical conformance). Each
generalizes to the remaining WS-6 shards (S6a/S6b/S6c, S7v) and to any future
cross-process / cross-runtime / cross-OS work.

## 1. Cross-process coordination — the durable store is authority, never an in-process Future

`grant` is the canonical "request in one CLI invocation, answer in another"
flow. The Phase-01 rendezvous was an in-process `asyncio.Future`
(`envoy/grant_moment/runtime.py:305`), which **cannot be `set_result`-ed across
two OS processes** — exactly the `grant` shape. S4r replaced it with a
**store-poll-with-monotonic-version-re-check as the PRIMARY mechanism**
(`runtime.py:306-308`: `await_decision` polls `get_pending_grant` for the
resolution written by a separate invocation's `resolve_pending_grant`). The
in-process `decision_future` survives ONLY as a same-process fast-path cache
(`runtime.py:377-379`) — the store is the authority.

S4g-1 layered the M0→M4 state machine over that rendezvous: JCS-signed
`GrantMomentResult` resolution rows, **cross-process replay-nonce dedup**
(`GrantMomentReplayError` holds across two OS processes, not just one event
loop), and **queue back-pressure** (a full pending-grant sub-store surfaces a
typed error, never a silent drop).

**Generalizes:** any cross-process coordination (S6c's `chat` resident loop is
next) MUST treat the durable store as the source of truth and any in-process
handle as a cache that a crash may lose. Local IPC is a per-platform
optimization layered on top, NOT an `OR` — it breaks on musl-static. The
byte-identity discipline of the timeout path matters too: a poll-timeout MUST
still drive the same `next_state(..., TIMEOUT_EXPIRED)` M2→M3 transition so the
`GrantMomentExpiredError` audit row is byte-identical to the Phase-01 path.

## 2. Shared-contract single-ownership — one shard owns the invariant + its test; consumers import

S5b is the **SHARED OWNER** of the `session_boundary_crossed` signal AND the
**T-013 cache-reset invariant test**. Two downstream shards consume it: S5o
(drives the observed-state reset off the signal) and S6c (proves a real `chat`
boundary fires it). The structural choice that matters: S5b owns the signal +
the reset-invariant test ONCE, and S5o/S6c **import** the contract rather than
each re-deriving "what resets on a boundary." This is the direct defense against
the `specs-authority.md` Rule 5b divergence failure — two shards independently
re-deriving the same reset semantics and silently drifting.

**Generalizes:** whenever ≥2 shards depend on the same invariant (reset
semantics, a fingerprint shape, a signing contract), ONE shard owns the
contract + a single exported invariant test; every consumer imports it. The
anti-pattern is "each consumer re-implements the rule it shares" — the same
class as the parallel-adapter drift `journal/0019` Pattern 1 avoids, one layer
up at the contract level instead of the implementation level.

## 3. "Byte-identical" claims need cross-OS NFC coverage; set-results assert set-equality, not order

S3a authored E1–E4 as **byte-identical** (hash-equality) vectors run across
BOTH runtimes AND the **full OS matrix** (macos-14, ubuntu-22.04/24.04,
windows-2022). Two non-obvious invariants surfaced:

- **E3 asserts SET-equality, not sequence-equality.** The cascade-revoke result
  may differ in ordering (BFS vs DFS) while the SET is byte-identical; a
  set-membership difference fails, an ordering difference does NOT. Asserting
  sequence-equality here would false-fail on a correct runtime.
- **The cross-OS run is load-bearing, not belt-and-suspenders.** A Rust runtime
  that truncates a combining character on Windows NTFS is a silent BET-6
  falsifier that a single-OS run never catches. The byte-identity is over the
  JCS-RFC8785 **+ NFC** canonical form, and NFC drift is exactly what a
  cross-OS matrix exists to surface.

**Generalizes:** every future `@byte_identical` conformance claim (S7v's
`envoy-producer == envoy-verifier` proof reuses the same E7 vectors) MUST run
the byte-identity slice across the OS matrix, and any result that is
semantically a SET MUST assert set-equality, never order.

## For Discussion

1. Pattern 1 says "store is authority, in-process handle is a cache a crash may
   lose." S6c's `chat` resident loop is the first shard where the loop process
   can crash mid-conversation. Is there a test that literally kills the loop
   process mid-grant and asserts the pending grant is still answerable via S4g —
   or is the crash-recovery contract only asserted at the unit level (which
   would not catch a loop that caches authority it should have written through)?
2. Pattern 2's shared-ownership defense works because S5b exports the
   reset-invariant test as an importable contract. At what point does the count
   of "shared invariant tests imported across shards" itself become a coupling
   surface — e.g. an S5b contract edit that should invalidate an S5o assumption
   passes because the import still type-checks? Is a "who-imports-this-contract"
   reverse-index worth maintaining as the WS-6 shard count grows?
3. Pattern 3's cross-OS matrix catches NFC truncation, but only for vectors that
   actually exercise combining characters. Does the E1–E4 corpus include a
   vector with a known-adversarial NFC sequence (combining diacritics, CJK
   compatibility ideographs), or could a runtime pass all 4 OS targets on an
   ASCII-only corpus and still truncate NFC in production?
