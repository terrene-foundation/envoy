---
type: DISCOVERY
date: 2026-05-29
created_at: 2026-05-29T00:00:00Z
author: co-authored
session_id: envoy-2026-05-29
session_turn: post-audit-F15a
project: phase-01-mvp
topic: visible secret never renders on a production Grant Moment (T-018 anti-spoofing gap)
phase: redteam
tags:
  [
    F15,
    T-018,
    anti-spoofing,
    grant-moment,
    visible-secret,
    spec-accuracy,
    xfail-redgate,
  ]
---

# 0045 — DISCOVERY: visible secret never renders on a production Grant Moment

## Context

Building F15-a (the audit's recommended real persist→render test, journal/0044)
CONFIRMED a gap larger than the audit estimated: the visible secret is not
rendered on the production Grant-Moment dispatch path at all — not merely
untested.

## The gap (airtight, code path traced)

`specs/grant-moment.md` § Rendering lines 80-82 mandate, verbatim: "Every dialog
shows: Visible secret (icon + color + phrase, stored in Trust Vault)." This is
the T-018 anti-spoofing defense (`specs/grant-moment.md` § 10) — no Phase-02
carve-out.

Production path: `EnvoyGrantMomentRuntime.issue_grant_moment` →
`ChannelHandoff.dispatch` → `channel_handoff.py:241 adapter.render_grant_moment(request)`
→ `CLIChannelAdapter._render_grant_moment_request_prose` (`cli.py:433`). That
renderer emits action / why / novelty but NOT the visible secret — its own
comment (`cli.py:442-444`) states "the M1 dispatch surface does not carry it."
The only renderer that emits the phrase (`_render_grant_moment_prose`, consuming
`GrantMomentPayload`) is ORPHANED: `GrantMomentPayload(` is never constructed
anywhere in `envoy/`. The runtime exposes `visible_secret_hash_for` (a hash,
never the phrase) but nothing renders it. Every prior render test passed because
it asserted against a hardcoded STUB secret through the dead path.

Two violations: (1) security — T-018 anti-spoofing surface absent in production;
(2) spec-accuracy — `grant-moment.md:80-82` over-claims vs shipped code. The
correct fix is code-matches-spec (render it), not weakening the spec —
anti-spoofing is load-bearing.

## F15-a — landed (confirming red-gate)

`tests/tier2/test_grant_moment_renders_visible_secret_real_infra.py` drives the
REAL dispatch path (real `TrustStoreAdapter` with a set secret, real
`CLIChannelAdapter` capturing output, real runtime dispatch) and asserts the
rendered Grant Moment contains the user's real phrase. It FAILS today; marked
`xfail(strict=True)` so F15-b's fix flips it to xpass and strict-mode forces
removal of the marker. Receipt: `1 xfailed`; tier2 278 passed / 9 skipped /
1 xfailed; mypy clean for the file (two documented `# type: ignore[arg-type]`
for the real-object-as-structural-protocol nominal mismatch, same pattern the
sibling test routes around via a loosely-typed helper).

## F15-b — filed (the fix shard)

Wire the runtime-resolved `VisibleSecret` into `render_grant_moment` across every
channel adapter at dispatch time, with the phrase kept OUT of the signed
`GrantMomentRequest` / Phase-A ledger row (the R1-HIGH-1b "phrase never in the
ledger" contract). Design intent already present (`visible_secret_hash_for` +
the render-all-channels test's note "visible_secret hash lookup is the adapter's
job") — but the adapter's `render_grant_moment(request)` has no path to the
secret today. Cross-cutting across ~5-8 adapters (CLI/Web/Slack/Telegram/…) →
its own shard, NOT folded into F15-a. Anchor: `specs/grant-moment.md` lines
80-82 + § 10 T-018.

## For Discussion

1. **Counterfactual:** F15-b must give the adapter a path to the secret without
   leaking the phrase into the ledger. Two designs: (a) the dispatch resolves the
   phrase and passes it to `render_grant_moment(request, visible_secret=...)`;
   (b) each adapter is injected with a secret-resolver. (a) keeps the secret out
   of the adapter's long-lived state but widens the dispatch signature across all
   adapters; (b) is more local but puts a trust-store handle in every adapter.
   Which better preserves the phrase-out-of-ledger invariant under future change?
2. **Data-referencing:** the render-all-channels test (`:42-44`) explicitly punts
   ("channel adapters surface the actual render under their own per-channel test
   surface") yet no per-channel test asserts the real secret renders. Is the
   per-channel-test boundary where this gap hid, and should F15-b add a real
   render assertion to every channel adapter's lifecycle test?
3. **Severity timing:** F15-a documents the gap as a red-gate but the
   anti-spoofing defense stays absent until F15-b ships. Is carrying a known-absent
   T-018 defense acceptable for the EC-6 ship gate, or does F15-b block ship?
