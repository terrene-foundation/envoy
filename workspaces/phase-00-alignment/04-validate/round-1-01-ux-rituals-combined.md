# Round 1 Combined Review — Doc 01 UX Rituals

**Date:** 2026-04-21
**Severity:** 3 CRITICAL + 6 HIGH + 6 MED + 3 LOW = 18 findings.

## CRITICAL

- **C-01** Escape-phrase recovery path (§13) leaks duress state — remove; rely on doc 03 v2 §10.2 shadow-segment surface at next real unlock.
- **C-02** Shadow-segment surface (post-duress review notification) absent from Boundary Conversation onboarding + Daily Digest + post-unlock banner; defense is orphaned without a UX surface.
- **C-03** Visible-secret compromise scenario underspecified — §2.3 states the residual but provides no Phase 01 detection/rotation primitive. Open Q7 parks without resolving.

## HIGH

- **H-01** Channel list inconsistency: §2.2 lists 8 (incl. iMessage + Signal) but §5.6 mentions email/SMS instead. Reconcile with doc 00 v3 + doc 07.
- **H-02** 5-min Grant Moment timeout = DoS-by-absence + duress latency distinguisher. Queue behavior undefined.
- **H-03** Channel-switching evasion — no primary-channel binding for high-stakes actions; approval on low-friction channel wins.
- **H-04** "Novel" pattern undefined — no scoring function for recipient/dollar-range/tool novelty; T-019 defense unverifiable.
- **H-05** Velocity-raise ratchet bypassable via "Approve + author" (semantic-equivalent widening via authored constraint).
- **H-06** Shamir distribution checklist persists real human names in Trust Vault — T-006 reopening.

## MED

- M-01 Authorship Score threshold language inconsistent; AUTONOMOUS threshold not shown.
- M-02 Weekly Posture Review velocity-raise confirmation lacks 24h cool-off.
- M-03 S9 review preview missing visible-secret banner.
- M-04 Signal state machine underspecified (no ritual_id prefix for replies).
- M-05 Monthly Trust Report sharing lacks redaction schema.
- M-06 Grant Moment "Modify" option has no defined state machine.

## LOW

- L-01 `completed_boundary_conversation` flag timing correlation risk; debounce.
- L-02 Mixed-locale Ledger rendering unspecified (RTL/bidi).
- L-03 Shamir recovery UX doesn't validate per-card checksum.

## Verdict: NOT CONVERGED — 3 CRIT + 6 HIGH block Round 1 close.
