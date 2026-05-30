---
type: DISCOVERY
date: 2026-05-29
created_at: 2026-05-29T00:00:00Z
author: co-authored
session_id: envoy-2026-05-29
session_turn: post-F14
project: phase-01-mvp
topic: security hard-constraint real-infra audit (stub-masking sweep across 5 constraints)
phase: redteam
tags:
  [
    F15,
    F16,
    F17,
    F18,
    F19,
    EC-4,
    EC-8,
    stub-masking,
    real-infra,
    security-hard-constraint,
  ]
---

# 0044 — DISCOVERY: security hard-constraint real-infra audit

## Context

The cascade chain (F10 → F12-a → F14) exposed a systemic pattern: a security
hard-constraint passing all tests while the REAL engine was never exercised
(every test wired a stub). This audit swept the OTHER security hard-constraints
for the same stub-masking gap, via 5 parallel read-only deep-dives.

## Verdicts (5 clusters)

| Constraint                      | Anchor                                          | Stub-masked like F14?        | Severity | Gap                                                                                                                                                                                                                            |
| ------------------------------- | ----------------------------------------------- | ---------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Visible-secret anti-spoofing    | `specs/boundary-conversation.md` (defends EC-1) | **YES**                      | **HIGH** | No test renders the user's REAL stored secret; all render tests feed a hardcoded stub phrase. Likely impl gap: Phase-01 `DuressBanner` payload carries no icon/color/phrase at all.                                            |
| Ledger tamper-detection         | EC-4 line 66 verbatim                           | NO (bit-flip real, tier1)    | **MED**  | insert / delete / reorder — named verbatim in the gate — untested entirely; only bit-flip is exercised.                                                                                                                        |
| Classification / read-redaction | (Wave-3 deferred by spec)                       | partial                      | **HIGH** | Production read path does ZERO redaction (thin pass-through); tier2 test monkeypatches a spy + asserts pass-through-unredacted. Green tests imply coverage that isn't there — but capability is intentionally Wave-3-deferred. |
| Budget no-double-billing        | EC-8 line 116(b)                                | NO (real engine)             | REFUTED  | See § EC-8b below.                                                                                                                                                                                                             |
| Posture/clearance gate          | Thesis §2.3 (BET-12)                            | **NO** (real gate exercised) | MED      | Solid. Minor: no ledger-replay projection test for "no silent downgrade"; no fail-closed test for collaborator-raises-mid-sequence (deferred to issue #24).                                                                    |

## EC-8b budget double-billing — REFUTED (not a bug)

The suspected dedup-key bug (dedup on per-reserve `reservation_id`, not
`intent_id`, so two independent channel reserves both bill) is NOT a current
bug. Per `01-analysis/12-budget-tracker-implementation.md` line 460 the intended
Phase-01 contract is a SHARED reservation: "same `intent_id` reserved on
Telegram, action-confirmed on Slack, **recorded on the original tracker**" —
the sibling channel records the ORIGINAL handle, so dedup-on-`reservation_id`
is correct and `tests/tier2/test_budget_no_double_billing_multi_channel.py`
exercises it against the real engine.

**Latent Wave-2 risk (recorded, not a Phase-01 bug):** the guarantee holds only
if the (unbuilt) cross-channel wiring routes a sibling channel to the ORIGINAL
reservation rather than calling `BudgetRuntimeAdapter.budget_reserve` again (which
mints a fresh `intent_id`+`reservation_id` per call → would double-bill). This is
a Wave-2 wiring acceptance criterion, sibling to F12-c.

## Resulting backlog (value-anchored shards)

- **F15 (HIGH)** — real persist→render→assert test for the visible secret: set a
  unique phrase via the real `TrustStoreAdapter`, wire that adapter into
  `EnvoyGrantMomentRuntime` (no stub), issue a Grant Moment, assert the rendered
  output contains the REAL phrase (+ divergent phrase raises). Confirm whether
  `specs/boundary-conversation.md` requires the duress surface to render the
  secret in Phase-01; if so the `DuressBanner` payload omission is an impl gap.
  Anchor: `specs/boundary-conversation.md` § visible secret (anti-spoofing,
  defends EC-1 onboarding trust).
- **F16 (MED)** — tier2 ledger tamper-detection test covering insert / delete /
  reorder (the three EC-4 vectors with zero coverage). Anchor: EC-4 line 66
  verbatim ("insertion / deletion / reorder of any entry").
- **F17 (HIGH, red-gate)** — tier2 test asserting `[REDACTED]` through the real
  `ledger_query` read path; will FAIL today, converting the Wave-3 read-classification
  deferral from an unverified claim into a tracked red gate (`orphan-detection.md`
  Rule 2 + `dataflow-classification.md` Rule 1). Anchor: EC-4/EC-8 read-classification
  (Wave-3 deferred — surface, don't silently carry).
- **F18 (Wave-2 deferral)** — cross-channel budget wiring MUST route the sibling
  channel to the original reservation OR dedup MUST key on `intent_id`. Anchor:
  EC-8 line 116(b). Sibling of F12-c (Wave-2 Grant Moment / channel dispatch).
- **F19 (MED)** — posture: ledger-replay projection test ("no silent downgrade"
  at the projection layer) + fail-closed-on-collaborator-error test (issue #24
  orphan-entry window). Anchor: Thesis §2.3 (BET-12).

## For Discussion

1. **Counterfactual:** 4 of 5 audited constraints had a real-infra gap of some
   kind (2 HIGH stub-masked, 2 MED), and the cascade chain added 3 more. Should
   the EC-6 ship gate add a standing rule: every security hard-constraint MUST
   have ≥1 real-infra test that exercises the actual engine before any
   stub-based test counts toward its coverage?
2. **Data-referencing:** the visible-secret render path (F15) and the cascade
   path (F14) share the identical failure shape — a `Stub*` returning a hardcoded
   value short-circuits the real persist→use path. Is `tests/helpers/`
   stub-injection the common root cause, and should stub helpers be banned from
   the tier2/tier3 trees entirely (forcing real adapters)?
3. **Deferral honesty:** F17 (classification) is Wave-3-deferred by spec but the
   green tier2 test implies coverage. Is a deliberately-failing red-gate test the
   right way to make a deferral honest, or does it just add CI noise until Wave-3?
