---
type: DECISION
date: 2026-05-07
created_at: 2026-05-07T03:30:00Z
author: agent
session_id: phase-01-mvp-redteam-r1
session_turn: 1
project: envoy
topic: spec-vs-code reconciliation — `EnvoyLabelOnCardWarning (advisory)` renamed to `EnvoyLabelOnCardError` (hard rejection) because shipped code is the structural intent that ships
phase: redteam
tags:
  [
    spec-deviation,
    h06-hardening,
    shamir-recovery,
    spec-accuracy,
    redteam-round-1,
    autonomize-rule-2-root-cause,
  ]
---

# DEVIATION — `EnvoyLabelOnCardWarning` (advisory) → `EnvoyLabelOnCardError` (hard rejection)

## Context

`/redteam` round 1 (/implement cycle) found that `specs/shamir-recovery.md:53` declared a class `EnvoyLabelOnCardWarning (advisory)` whose user-action column read "UX advisory; user re-prints clean card per format spec". This class did not exist in shipped code: `envoy/shamir/errors.py:64` defines `EnvoyLabelOnCardError` (hard rejection), raised by 13 sites across `envoy/shamir/paper.py`, `envoy/shamir/distribution_checklist.py`, and `envoy/shamir/types.py:__post_init__`.

The shipped behavior is a three-layer structural defense per the T-02-35 H-06 fix:

1. Whitelist regex `^slot-\d+$`
2. ASCII-only check (rejects Unicode confusables like Cyrillic `s` U+0455 in `slot-0`)
3. Substring blacklist `("envoy",)` (case-insensitive)

A label that fails any layer raises the typed error and the print is refused. The intentional duplication at all three sites (no cross-module coupling on a single check) was driven by security review M-1 + M-2 dispositions during T-02-35.

## Decision

Update the spec to match shipped code rather than soften code to match spec.

- `specs/shamir-recovery.md:53` error-taxonomy entry renamed `EnvoyLabelOnCardWarning (advisory)` → `EnvoyLabelOnCardError`. User-action column updated: "Refuse to render; user re-supplies a canonical `slot-N` label".
- New § Slot label whitelist subsection documents the three-layer defense.

## Rationale

`rules/spec-accuracy.md` MUST Rule 1 (citations grep-resolve against working code) + Rule 5 (specs describe shipped behavior on `main`) explicitly direct that specs follow code, not the inverse. The spec citation `EnvoyLabelOnCardWarning` failed `grep` (the symbol doesn't exist anywhere in `envoy/`); the shipped code is the source of truth.

The alternative — softening code to match the spec's "advisory warning" framing — would require:

- Removing the renderer/persister/`__post_init__` whitelist enforcement
- Switching to `warnings.warn(...)` at one (where?) site
- Permitting print of cards with `Envoy`-substring labels under the user's "advisory acknowledgement"

This would erase the H-06 hardening that T-02-35's PR explicitly chose, contradict the security review M-1 + M-2 dispositions, and reduce the OPSEC posture for shard-distribution UX. Per `rules/autonomize` Rule 2 root-cause + Rule 3 long-term: the harder enforcement IS the right behavior; spec is the artifact that should adjust.

## Consequences

- Future spec readers see the contract the shipped code performs.
- Phase 02+ extensions (e.g. multi-language slot label support) inherit the whitelist contract.
- The wire-form `EnvoyLabelOnCardError` typed error is the only label-failure surface for callers.

## Follow-up

- None — fix landed in PR #16 (commit `513d35d`); merged to main at `74a7e1f`.
- The /codify upstream candidate per session-notes (8-of-8 inspect.signature sweep streak) carries forward independently; this deviation is a one-off spec-vs-code reconciliation.

## For Discussion

1. **Counterfactual** — If the spec's "advisory warning" framing had been the intended behavior, would T-02-35 have rejected the security review's M-1 + M-2 hardening as scope creep? The PR #15 commit history shows the gate-fix commit `b6a5904` deliberately added the three-layer whitelist; the security review never proposed an "advisory" downgrade. This suggests the spec's advisory framing predated T-02-35's H-06 hardening and was never updated when the harder enforcement landed — a structural-failure pattern that `rules/spec-accuracy.md` Rule 5 (incremental spec extension) is designed to prevent.

2. **Specific data** — `specs/shamir-recovery.md` was edited 7 times across Phase 01 per `git log`. Of those edits, how many reconciled spec-vs-code drift surfaced by /redteam vs proactive spec-first updates? If the dominant pattern is reactive (drift surfaces in /redteam → spec follows), the structural defense is to add a /implement-side check ("on every shipped fix, update the spec section if any field changed"). If proactive, the failure mode is rarer and the existing /redteam-side check suffices.

3. **Counterfactual** — Would a Tier-2 contract test asserting `EnvoyLabelOnCardError` IS in the public error surface (and `EnvoyLabelOnCardWarning` is NOT) have caught this deviation at /implement time rather than /redteam time? Such a test would lock the public taxonomy against spec drift in either direction; cost is one test file (~30 LOC) per typed-error surface.
