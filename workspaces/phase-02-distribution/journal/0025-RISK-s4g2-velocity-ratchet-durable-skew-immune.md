---
type: RISK
date: 2026-06-14
author: co-authored
project: phase-02-distribution
topic: S4g-2 velocity half — durable + forward-skew-immune velocity-raise cooling-off ratchet (closes the restart-resets-ratchet HIGH); delegation half split to S4g-2b (BLOCKED on F12-b)
phase: implement
verified_id: 548F2C562EB4246D025FA80A70552B124755B685
source_commit: d1dc42e20822ced0340b157a92bae6117e342ee7
tags:
  [
    risk,
    security,
    velocity-ratchet,
    grant-moment,
    durability,
    monotonic-clock,
    s4g-2,
    shard-split,
  ]
relates_to: 0024-RISK-s5o-enc-review-fixes-zeroization-trust-boundary
---

# RISK — S4g-2 velocity ratchet: a restart no longer buys a free velocity raise

Promoted from the SessionEnd pending stub for commit `d1dc42e20822` (PR #112;
review fail-closed follow-up `34f5cf0`). Closes two findings; splits the
delegation half to S4g-2b.

## Problem (the two findings this closes)

Phase-01 kept the velocity-raise last-approved timestamp in an **in-memory dict**
(`EnvoyGrantMomentRuntime`), so:

- **security-R1 HIGH-3** — a process restart **silently reset** the 24h
  cooling-off ratchet → a restart bought a free velocity raise.
- **security-R2 MED-2** — a forward wall-clock jump (NTP catch-up / admin clock
  change) could **shorten** the window.

This persists the record and adds a monotonic baseline.

## Implementation

- `session.py`: new `velocity_raise_ratchet` table + `record_velocity_approval` /
  `get_velocity_ratchet` + `VelocityRatchetRow`. Each row carries the wall-clock
  timestamp (calendar-time window, survives restart), a monotonic baseline, and
  the per-process `boot_id` that captured them. Operational metadata —
  **cleartext, not an S5o-enc payload column** (`0023`).
- `runtime.py`: `_velocity_elapsed_since_last_approval` /
  `_record_velocity_approval` + a per-process `_PROCESS_BOOT_ID`. Router-backed
  when wired (durable across restart); in-memory fallback when no router
  (Tier-1/legacy). **Same-boot** (boot_id matches) measures elapsed by the
  MONOTONIC delta — authoritative, immune to a forward wall-clock jump that would
  otherwise shorten the window; **cross-boot** (restart, monotonic not
  comparable) falls back to the wall-clock delta. Negative deltas clamp to 0 so
  the gate stays **closed**.

Closes the Phase-01 limitation users on managed-clock systems were told to treat
as advisory (`grant-moment.md` § Velocity-raise ratchet). **Narrower residual:**
cross-restart forward skew still uses wall-clock (documented).

## Review fail-closed follow-up (`34f5cf0`)

Reviewer surfaced non-finite timestamps (NaN/±inf) reaching the ratchet math.
Fixed fail-closed: a non-finite velocity-ratchet timestamp is **rejected**, not
silently coerced — the gate stays closed on garbage input.

## Shard split — S4g-2b (the delegation half) is BLOCKED on F12-b

The S4g-2 delegation-tree half (3-deep literal cascade via the runtime's
`revoke_prior_grant` in the EC-2/EC-8 e2e) is **SPLIT to S4g-2b** — empirically
blocked on **F12-b** (the sync↔async cascade facade bridge, deferred Phase-02 per
`journal/0042`): `revoke_prior_grant` is **sync** and the real trust-store
`revoke` is **async**, AND it needs multi-adapter Genesis orchestration
(`record_delegation` enforces delegator==principal). F12-a already proves the
real cascade engine.

**This is the P18 → P17 dependency** in the `.session-notes` ledger: F12-b (P18,
in-repo) unblocks S4g-2b (P17) + the user-reachable EC-8 cascade. The next
session's pick (F12-b) is what makes this split resolvable.

## Verification

5 Tier-2 regression (survives-fresh-runtime, no-router-fallback,
forward-wall-skew-immune-same-boot, cross-boot-wallclock-fallback-allows-after-
window, cross-boot-within-window-still-blocks). Full suite 2446 passed; mypy +
ruff clean. User-flow walk: process A approves → process B (restart) refused with
`VelocityRaiseCoolingOffError`, ratchet survived.
