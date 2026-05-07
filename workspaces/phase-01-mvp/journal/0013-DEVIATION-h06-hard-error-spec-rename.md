---
type: DEVIATION
slug: h06-hard-error-spec-rename
date: 2026-05-07
phase: 01
relates: [T-02-35, redteam-round-1-implement]
---

# DEVIATION — `EnvoyLabelOnCardWarning` (advisory) → `EnvoyLabelOnCardError` (hard rejection)

## What changed

`specs/shamir-recovery.md` § Error taxonomy line 53 previously declared:

> `EnvoyLabelOnCardWarning` (advisory) | UX advisory; user re-prints clean card per format spec | Manual after re-print

This was renamed to `EnvoyLabelOnCardError` and the user-action column updated:

> `EnvoyLabelOnCardError` | Refuse to render; user re-supplies a canonical `slot-N` label | Manual after re-supply

A new § Slot label whitelist subsection documents the three-layer structural defense the shipped T-02-35 code already enforces (whitelist regex `^slot-\d+$` + ASCII-only + substring blacklist `("envoy",)` at renderer + persister + dataclass `__post_init__`).

## Why the spec was the side that moved (not the code)

T-02-35's H-06 fix (PR #15) shipped the harder enforcement intentionally per security review M-1+M-2 dispositions:

- Unicode confusable bypass (Cyrillic `s` U+0455 in `slot-0`) and control-char bypass (`slot-\x000`) are blocked by the whitelist regex + ASCII-only check.
- Substring `envoy` (case-insensitive) blacklisted at all three sites so no construction path bypasses the whitelist.

Per `rules/spec-accuracy.md` MUST Rule 5 (Incremental Spec Extension): specs describe shipped behavior on `main`. The spec promised an "advisory" warning that never shipped — the shipped code is the hard rejection. Per Rule 1, the spec citation `EnvoyLabelOnCardWarning` failed `grep` (the symbol doesn't exist; `envoy/shamir/errors.py:64` defines `EnvoyLabelOnCardError`).

## Per `rules/specs-authority.md` MUST Rule 6 acknowledgment

This deviation is logged so a future reader of the spec can trace the rename to the security review that drove it. The shipped code is the source of truth; the spec now reflects the contract the code performs.

## Cross-references

- T-02-35 closure annotations: `todos/active/02-wave-2-authorship-shamir-boundary.md:108-110`
- Three-layer defense sites: `envoy/shamir/paper.py:158-206`, `envoy/shamir/distribution_checklist.py:83-153`, `envoy/shamir/types.py:189-210`
- Round-1 redteam verdict: `04-validate/round-1-implement-redteam.md` § HIGH-3
- Rules consulted: `rules/specs-authority.md` Rule 6, `rules/spec-accuracy.md` Rule 1 + Rule 5
