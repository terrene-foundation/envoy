---
type: DECISION
date: 2026-05-29
created_at: 2026-05-29T00:00:00Z
author: co-authored
session_id: envoy-2026-05-29
session_turn: post-F15a
project: phase-01-mvp
topic: F15-b — wire runtime-resolved visible secret into Grant-Moment render (CLI / high-stakes)
phase: redteam
tags:
  [
    F15,
    F15-b,
    T-018,
    anti-spoofing,
    grant-moment,
    visible-secret,
    phrase-out-of-ledger,
  ]
---

# 0046 — DECISION: F15-b wires the visible secret into the Grant-Moment render

## Context

F15-a (journal/0045) red-gated the confirmed gap: a production Grant Moment
never renders the visible secret (T-018 anti-spoofing). F15-b is the fix,
scoped + user-gated per the breakdown in this session.

## What landed (F15-b.1 — core + CLI)

The runtime resolves the `VisibleSecret` at dispatch time — AFTER the Phase-A
ledger append — and passes it as a SEPARATE argument through
`ChannelHandoff.dispatch(…, visible_secret=)` →
`ChannelAdapterProtocol.render_grant_moment(request, *, visible_secret=None)`.
The CLI adapter renders it FIRST (`Safety phrase: {icon} {phrase}`) per
`specs/grant-moment.md` § Rendering. The phrase is NEVER serialized into the
signed `GrantMomentRequest` / Phase-A ledger row (R1-HIGH-1b preserved).

Design choice (per the scoping gate): **resolve-at-dispatch + separate render
arg**, NOT a trust-store handle injected into each adapter — keeps the phrase
out of every adapter's long-lived state and out of the ledger by construction.

The 4 sibling adapters (web/slack/telegram/discord) accept the new param
(backwards-compatible default) but do NOT yet render it — high-stakes Grant
Moments render ONLY on the primary channel (`specs/grant-moment.md:92`), so
F15-b.1 closes the THREAT-RELEVANT (high-stakes) anti-spoofing case on the
primary (CLI). Low-stakes sibling parity is F15-b.2.

Walk receipt (rendered Grant Moment the user now sees):

```
--- Grant Moment (gm-…) ---
Safety phrase: lantern tide-pool-lantern-quartz-2026
Proposed action: send_email
Why asking: envelope_violation
Estimated spend: $0.0010
Reversibility: reversible
Recipient: test@example.com
Data sensitivity: Internal
```

## Scope adjustment (transparency)

The scoping gate said F15-b.1 would "add xfail red-gates for the 4 sibling
adapters." On building, faithful sibling render-capture (web uses Futures;
slack/telegram/discord render to API clients) IS F15-b.2's actual per-channel
harness work — stubbing 4 low-quality red-gates in b.1 would be worse than a
clean tracked shard. Decision: track the 4 siblings as F15-b.2 in the ledger;
F15-a (CLI) flipping green is the proof the core works.

## Test changes

- F15-a (`test_grant_moment_renders_visible_secret_real_infra.py`) flipped
  xfail→pass (xfail marker removed per `orphan-detection.md` Rule 4a — implement
  - sweep the deferral marker in the same change).
- Added a phrase-never-in-ledger regression test (R1-HIGH-1b lock): the phrase
  renders to the user AND is absent from every ledger entry.
- 3 test stubs (`grant_moment_harness.RecordingChannelAdapter`, the tier1
  handoff stub, the T-018 spoofing stub) updated to accept the new Protocol
  param (accept-and-ignore).

Receipt: full suite 1628 passed / 9 skipped / 9 xfailed; changed files add no
new mypy errors (the 2 at runtime.py:906/923 are pre-existing
`CrossChannelConfirmFailedError` backlog, unrelated method). Branch
`fix/phase-01-f15b-visible-secret-render-cli`.

## Remaining (tracked)

- **F15-b.2** — render the secret on web/slack/telegram/discord + per-channel
  render assertions (low-stakes parity). Anchor: `specs/grant-moment.md` 80-82.
- **F15-c** — duress-surface visible-secret rendering (`DuressBanner` payload
  carries no icon/color/phrase; spec requires "visible-secret-bound Modal" at
  `daily-digest.md:42` + `boundary-conversation.md:43`). Distinct surface.

## For Discussion

1. **Counterfactual:** F15-b.1 closes the high-stakes case (primary-only render)
   but low-stakes grants on siblings still omit the secret until F15-b.2. Is the
   high-stakes/primary-only case sufficient for the EC-6 ship gate's T-018
   mitigation claim, or must F15-b.2 + F15-c land before T-018 is "closed"?
2. **Data-referencing:** the T-018 spoofing test (`test_t018_dialog_spoofing…`)
   asserts hash-mismatch detection but ignores the new runtime-passed
   `visible_secret`. Should F15-b.2 make the adapter render the passed secret AND
   compare it against `visible_secret_hash_for` (defense-in-depth for a future
   multi-source render), or is single-source resolution sufficient?
3. **Pre-existing mypy backlog:** runtime.py:906/923 + ~33 other mypy errors
   predate this work. Should a dedicated cleanup shard (F13-adjacent) clear the
   mypy backlog before EC-6, since `git.md` pre-flight expects `mypy --strict`?
