---
type: DISCOVERY
date: 2026-05-29
created_at: 2026-05-29T00:00:00Z
author: co-authored
session_id: envoy-2026-05-29
session_turn: post-F15b
project: phase-01-mvp
topic: F16 ledger tamper vectors covered (verifier robust) + F15-c verified Phase-02
phase: redteam
tags: [F16, F15-c, EC-4, T-018, tamper-detection, phase-02-deferral]
---

# 0047 — DISCOVERY: F16 tamper vectors covered (no bug) + F15-c is Phase-02

## F16 — ledger tamper insert/delete/reorder: COVERED, verifier robust

EC-4 line 66 names four tamper vectors verbatim ("single-bit flip … insertion /
deletion / reorder of any entry"). Bit-flip was covered (tier1); insert / delete /
reorder had ZERO coverage (journal/0044 F16).

Added `tests/tier2/test_envoy_ledger_tamper_detection.py` (real EnvoyLedger +
real InMemoryAuditStore, no mock) exercising all three against the real
`verify_chain`. **Outcome: the verifier DETECTS all three** — this is a
confirm-it-works closure, NOT a bug (unlike F14). How each is caught:

- **delete** a middle entry → successor's parent_hash no longer matches the
  running prev entry_id → parent_hash mismatch.
- **insert** a duplicate mid-chain → the second copy's parent_hash != running
  prev entry_id → parent_hash mismatch.
- **reorder** → verify_chain canonicalizes physical order by sorting on the
  `sequence` field, so a physical reshuffle is a no-op; the only way to reorder
  the verified walk is to tamper `sequence`, which is in the canonical bytes →
  recomputed entry_id mismatch. The test swaps two entries' `sequence` values
  and confirms detection.

Receipt: 4 passed; tier2 284 passed / 9 skipped; mypy clean for the file. EC-4's
three previously-uncovered vectors now have a real-infra regression lock.

## F15-c — visible-secret duress modal: VERIFIED Phase-02, deferred

Investigating F15-c (the duress-surface visible-secret render) found it is NOT
a Phase-01 gap. `TrustStoreAdapter.shadow_segment_unread_duress_events` returns
`[]` in Phase-01 by design (verbatim docstring: "COMPLETE Phase-01 behavior,
NOT a stub. No duress-detection mechanism is wired in Phase 01 … the detection
path lands in Phase 02+"). So:

- Duress events never exist in Phase-01; the post-duress banner never fires
  (`boundary_conversation/runtime.py:173` gate is wired-but-inert by design).
- The "visible-secret-bound Modal" (`boundary-conversation.md:43`) has nothing
  to render — building it now = rendering for data that cannot exist in
  Phase-01 (speculative, against `verify-resource-existence.md` +
  `orphan-detection.md`).

**Disposition: F15-c deferred to Phase-02**, landing WITH the shadow-segment
duress-detection substrate. Distinct from F15-b (Grant Moments fire in Phase-01,
so F15-b was a real Phase-01 gap, now fixed). Anchor preserved:
`specs/boundary-conversation.md:43` + `daily-digest.md:42` + T-018.

Note the boundary-conversation post-duress gate also surfaces NO modal content
(only a presence/acknowledged boolean) — when Phase-02 wires duress detection,
F15-c must build the modal content (visible secret + duress time + recommended
actions per spec), not just flip the gate.

## For Discussion

1. **Counterfactual:** F16 confirmed the verifier is robust against all four
   EC-4 vectors. Should the independent verifier (F2, EC-9) reuse this exact
   tamper battery as its acceptance suite, so producer + independent verifier
   are proven against the identical vectors?
2. **Phase-boundary honesty:** F15-c and F18 (budget cross-channel) and F12-b/c
   are all "verified Phase-02, not a Phase-01 gap." Is the EC-6 ship gate's
   scope-boundary explicit enough that these deferrals are auditable as
   intentional, not forgotten?
