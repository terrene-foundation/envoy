---
type: DISCOVERY
date: 2026-06-08
project: phase-02-distribution
phase: analyze
topic: Parallel deep-dive sweep surfaced brief/spec phantom citations — the gate before /todos
tags:
  [
    analyze,
    brief-correction,
    spec-accuracy,
    phantom-citation,
    parallel-verification,
  ]
---

# 0001 — DISCOVERY: Brief/spec corrections from the 6-agent parallel deep-dive

Per `rules/agents.md` § "Parallel Brief-Claim Verification When Issue Count ≥ 3", the Phase-02 brief (≥3 workstreams) was analyzed by 6 parallel implementation deep-dives, each re-verifying its workstream's brief claims against shipped `envoy/` source. The sweep surfaced the corrections below. **Recording them here + in the architecture plan's "Brief corrections" section IS THE GATE before `/todos`** (single-agent framing-inheritance is the failure mode this prevents).

## Corrections (factual claims in the brief/specs that do NOT ground to shipped code)

| #   | Claim (source)                                                                                                                                                         | Reality (grounded)                                                                                                                                                                                                                                      | Severity                                             | Found by                  | Disposition                                                                                                                                        |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- | ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| C1  | `RuntimeBackendNotWired` is the Phase-01 runtime stub (`mvp-build-sequence.md:202`, repeated in brief WS-1)                                                            | **Symbol does not exist.** Real: `Phase02SubstrateNotWiredError` (`envoy/runtime/errors.py:91`) + `RsBindingsNotAvailableInPhase01Error`                                                                                                                | phantom-citation (HIGH-class per `spec-accuracy.md`) | WS-1 + WS-6 (independent) | Correct the brief + flag `mvp-build-sequence.md:202` as a spec gap (NO spec edit yet — additions-only this phase; bundle if a real edit is needed) |
| C2  | Phase-01 shipped 8 channel surfaces; WhatsApp/iMessage/Signal are "caveated shipped" adapters (`channel-adapters.md:211-213`, `mvp-build-sequence.md:121`, brief WS-3) | **Phase-01 shipped 5 of 8 surfaces** (CLI, Web, Telegram, Slack, Discord). WhatsApp/iMessage/Signal/SMS adapter classes are **absent from source** (`grep -rln` empty). WS-3 is THREE greenfield adapters, not caveat-lifting                           | phantom-citation (HIGH-class)                        | WS-3 + WS-6 (independent) | **Reshapes `/todos` sizing** — greenfield adapter build, not a caveat pass. Correct brief WS-3                                                     |
| C3  | Heartbeat ships "4 stub modules" (brief WS-5)                                                                                                                          | **5-stub partition**: 4 `PhaseDeferredError` modules + `HeartbeatClient.maybe_record_flag` (a genuine no-op that production hot-paths actually call — the most load-bearing seam, omitted)                                                              | undercount (MED)                                     | WS-5                      | Correct brief WS-5; the no-op is the real wiring seam                                                                                              |
| C4  | (implied) the persistent-session substrate has a partial Phase-01 scaffold                                                                                             | **`envoy.runtime.session.SessionRouter` does not exist** — no `session.py`; only a `channels/cli.py:12` docstring. The WS-6 substrate is genuinely greenfield; the production adapter raises `Phase02SubstrateNotWiredError` for every substrate method | clarification (MED)                                  | WS-6                      | WS-6 is greenfield substrate design, not extension                                                                                                 |
| C5  | spec implies `OHTTPClient`; brief cites generic symbols                                                                                                                | Real symbol is `OhttpClient` (casing); `runtime.py` `_inflight` comment at `:393-394,403` not the cited `:392-401`; `journal/0048` "6/10" is a stale pre-`ledger` snapshot (live CLI registers 7 groups, matches the "7/10" spec)                       | low (citation drift)                                 | WS-5 + WS-6               | No action beyond accurate citation in plans                                                                                                        |

## NON-corrections (claims that DID ground — verified accurate)

- WS-4: **all 9 brief line-citations resolve verbatim** against `main` (resolver Protocol `template_resolver.py:49-56`, `foundation-verified:`/`community:` URI schemes line 27-28, `classifier_registry_resolve` Protocol method `protocol.py:170`). WS-4 is "implement behind frozen Phase-01 typed-error seams" — correct Phase-01 state.
- WS-2: the entire `distribution.md` Phase-02 section grounds; the legal-gate map is accurate.
- The `Phase02SubstrateNotWiredError` seam (`runtime/errors.py:91`) is real and is the actual Phase-01→Phase-02 substrate boundary across WS-1, WS-4, WS-6.

## Why this matters

C1 and C2 are the same class as the Phase-01 `/redteam` ships-claim↔real-impl finding (`journal/0056` §codified). A "Phase-01 ships X" claim that doesn't grep to a non-stub impl is a HIGH over-claim. Two independent agents found C1 and two found C2 — the parallel sweep did exactly what `agents.md` designed it to do: a single-agent `/analyze` would have inherited the brief's "8 channels shipped / RuntimeBackendNotWired" framing and sized `/todos` against phantom code.

## Receipts

- Research docs (durable): `01-analysis/01-research/0{1..6}-ws*.md`, each with a "Brief/spec corrections" section.
- Agent task IDs: WS-1 `a5b9169b`, WS-2 `a190d22d`, WS-3 `ac7a12b1`, WS-4 `a6210ded`, WS-5 `a674545d`, WS-6 `ae670158`.
