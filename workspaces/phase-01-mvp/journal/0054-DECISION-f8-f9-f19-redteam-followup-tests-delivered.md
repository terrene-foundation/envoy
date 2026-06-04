---
type: DECISION
date: 2026-06-04
created_at: 2026-06-04T00:00:00Z
author: co-authored
session_id: continue-from-0053
session_turn: 1
project: phase-01-mvp
topic: F8/F9/F19 deferred redteam-followup test shards delivered (value-anchors re-validated)
phase: redteam
tags:
  [
    redteam,
    ec-7,
    ec-8,
    observability,
    posture-ladder,
    value-prioritization,
    deferred-shard-closure,
  ]
---

# 0054 — DECISION: F8 / F9 / F19 deferred redteam-followup test shards delivered

**Posture:** L5_DELEGATED

## Verdict

The three genuinely-actionable in-repo deferred shards from the "F6" forest bucket
(`F8`, `F9`, `F19`) are **DELIVERED**. Each was a value-anchored deferred test shard
that the `0053` convergence DECISION did NOT individually re-validate (covered only by
the sweeping aside `0053:37` "consistent with how R4/R5 deferred F8–F11"), leaving them
as live deferred shards per `rules/value-prioritization.md` MUST-3. A fresh adversarial
re-verification at HEAD `d043594` confirmed their deliverables verifiably did not exist
(grep-confirmed zero hits) — so this session implemented them rather than deferring a
fourth time (`rules/autonomous-execution.md` MUST Rule 4: same-class gaps that fit the
shard budget are fixed in-session, not re-filed).

`F11` remains correctly dispositioned-deferred (LOW; legitimate embedded-sqlite
local-first bootstrap; `CREATE TABLE IF NOT EXISTS` → `db/migrations/` is gold-plating
deferred to Phase-02+ per `0053:32`). Its value-anchor is unchanged; it was NOT picked up.

## What shipped (value-anchors re-validated per MUST-3)

| Shard   | Deliverable                                                                      | Value-anchor (re-validated)                                                                                                                        | File                                                            |
| ------- | -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| **F8**  | EC-7 per-channel ≤2× CLI-baseline parity acceptance test                         | `01-analysis/02-mvp-objectives.md` EC-7:104 — "Per-channel deviation from CLI baseline (in completion time, in message count) MUST stay within 2×" | `tests/e2e/test_f8_ec7_per_channel_2x_baseline_parity.py`       |
| **F9**  | EC-7/EC-8 observability-narrative regression extension of the R1 log-key surface | `02-mvp-objectives.md` EC-7:104 + EC-8:116 (cross-channel coherence)                                                                               | `tests/regression/test_f9_ec7_ec8_observability_narrative.py`   |
| **F19** | Ledger-replay "no silent downgrade" projection test (**Phase-01 half only**)     | Thesis §2.3 (BET-12) per `0044:85`; underpins EC-8 cross-channel coherence (`02-mvp-objectives.md` EC-8:116)                                       | `tests/tier2/test_posture_ledger_replay_no_silent_downgrade.py` |

**Severity: LOW each.** All three regression-lock / formalize acceptance gates for
behavior the runtime + gates already exercise (`0044:43` rates the posture gate "Solid";
EC-7 onboarding interchangeability is structurally exercised by the existing 5-channel
battery). None is a missing capability; none contests the 0-CRIT/0-HIGH EC-6 convergence
bar from `0053`. They close the deferred queue and the MUST-3 process gap so "Phase-01
in-repo complete" is verifiable rather than asterisked.

## Scope fence (honored)

`F19`'s **fail-closed-on-collaborator-error / orphan-entry-window half** (the F-001
transient-Ledger-failure-between-Step-5a-and-Step-5b bug class, `posture_gate.py:998-1002`)
is **Phase-03 / GH issue #24** and was explicitly NOT implemented. Only the Phase-01
projection-layer "no silent downgrade" half shipped.

## Approach (verified, not inherited)

1. Re-verified Phase-01 in-repo state at HEAD via 3 parallel adversarial agents
   (2× CLEAN-CONFIRMED on ship-readiness + actionable-sweep; F6-reality returned MIXED →
   surfaced F8/F9/F19 as live deferred shards). This contradicted the implicit "all clean"
   reading and is the receipt for why these three were implemented.
2. Implemented each test grounded in the REAL API (every referenced helper/fixture/export
   verified to exist before authoring): F8 reuses the existing EC-7 battery's wiring
   helpers; F9 mirrors the R1 observability log-key idiom (`caplog`); F19 mirrors the
   tier2 posture-gate wiring fixtures (real `EnvoyLedger` + Ed25519, NO mocking).
3. F8 timing dimension hardened beyond the agent draft: the ≤2× wall-clock ratio is
   noise-robust (≤2× **OR** sub-150ms absolute excess) so a permanent test does not flake
   on ~tens-of-ms absolute times (`rules/testing.md` § Deterministic). The deterministic
   message-count parity (exact 1.0×) is the load-bearing EC-7 proxy.

## User-flow walk receipts (per `rules/user-flow-validation.md` MUST-2)

```
$ uv run python -m pytest <F8> <F9> <F19> -v
  8 passed in 6.63s
$ flake re-run ×3 (incl. F8 timing): 8 passed each (6.63s / 6.86s / 6.86s)
$ warnings scan (-W default) on the 3 files: none introduced
$ ruff check / black --check / isort --check: all clean
$ integration (tests/regression + tests/tier2 + tests/e2e): 527 passed, 9 skipped, 3 xfailed
$ full suite (pre-push parity): 1705 passed, 9 skipped, 3 xfailed in 79.31s
```

Disposition: the literal test-runner walk is green and stable; the deferred queue is
closed for the in-repo Phase-01 surface.

## Why (decision rationale)

The user chose "Close F8/F9/F19 now" over (a) declaring Phase-01 done as-is, (b) Phase-02
entry, or (c) the separate-repo verifier (EC-9 / F2). This is the highest-value work
deliverable from THIS repo without a strategic gate: the higher-value lanes are either a
different repo (F2, out of scope per `rules/repo-scope-discipline.md`) or a deliberate
phase boundary (Phase-02). Closing F8/F9/F19 makes the in-repo "Phase-01 complete at the
spec-defined 7/10 CLI ceiling" (`specs/mvp-build-sequence.md:190`) verifiable, with no
un-re-validated deferred shards lingering in the forest.

## Updated forest ledger (this session)

- **Closed:** `F8`, `F9`, `F19` (the genuinely-actionable members of the old "F6" bucket).
- **Remains deferred-by-anchor:** `F11` (LOW, Phase-02+ gold-plating; `0053:32`).
- **Unchanged external/structural gates:** `F2` (separate-repo verifier / EC-9),
  `F4` (full EC-6, blocked on F2), `F5.2-grant` + `F21` (Phase-02 substrate),
  `F20` (Wave-4 Nexus InboundRouter), `F5.3` (Windows host), `F22` (kailash-py#1245),
  `F23` (threat-coverage meta-gate, Phase-02).

## Receipts

- Re-verification workflow `wlyk994fp` (ship-readiness + actionable-sweep CLEAN-CONFIRMED;
  F6-reality MIXED → F8/F9/F19 surfaced).
- Test-investigation workflow `wl89o0k06` (3 HIGH-confidence grounded specs).
- Prior convergence DECISION: `0053`. F19 anchor source: `0044:83-85`. F11 disposition: `0053:32`.

## For Discussion

1. **Counterfactual:** had the adversarial F6-reality check NOT run, the session would
   have inherited "all clean" from `0053` and never surfaced F8/F9/F19 — they would have
   decayed in the forest indefinitely. Does this argue for a standing MUST that every
   convergence DECISION individually re-validate each deferred shard's anchor (not a
   sweeping aside), closing the `0053:37` gap structurally?
2. **Data-specific:** F8's timing dimension is structurally ~1.0× because the
   `BoundaryConversationRuntime` is channel-agnostic (takes no `ChannelAdapter`). When
   Phase-02 wires per-channel transport latency, will the ≤2× bound still hold, or does
   per-channel async I/O introduce real divergence the noise-robust form would then need
   to tighten back to strict ≤2×?
3. F19 ships a test-local `_project_posture` helper because no production
   `project_posture` exists in Phase-01 (it is Phase-03 `effective_posture_for_composition`).
   Should Phase-02/03 promote this projection into production code so the test pins a real
   function rather than formalizing the documented invariant?
