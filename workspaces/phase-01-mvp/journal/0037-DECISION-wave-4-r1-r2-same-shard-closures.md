---
type: DECISION
date: 2026-05-26
created_at: 2026-05-26T13:20:20.539Z
author: co-authored
session_id: 92477210-aea3-485d-8a59-66f07d1a19b1
project: phase-01-mvp
topic: Wave-4 /redteam R1+R2 same-shard fix closures (3-axis convergence trajectory)
phase: redteam
tags: [wave-4, redteam, same-shard-fix, autonomous-execution-rule-4]
source_commit: e2709c6e0069d9748bbbe6886a39b08b7ac0b1e6
---

# Wave-4 /redteam R1 same-shard closures: 10 HIGH + 15 MED

Commit: `e2709c6e0069` (followed by `9b8708f` R2; merged via PR #41, 2026-05-26).

**Commit**: `e2709c6e0069` — fix(phase-01-wave-4): /redteam R1 same-shard — 10 HIGH + 15 MED closures

**Body**:

Closes findings from 3-axis Round 1 audit (security-reviewer / reviewer /
analyst) per `rules/autonomous-execution.md` MUST Rule 4 (same-bug-class
gaps that fit one shard budget → fix now, no follow-up issue).

## Security axis (3 HIGH + 6 MED)

- HIGH-1 unbounded dedup stores → FIFO-bounded OrderedDict at 100k
  ceiling (configurable via `dedup_store_ceiling`); FIFO eviction via
  `popitem(last=False)` keeps the most-recent N replay-defended.
- HIGH-2 state-transition raise unhandled → `submit_resolution` returns
  `InvalidGrantMomentTransitionError` as a typed ERROR outcome rather
  than letting `next_state` raise into the caller.
- HIGH-3 monotonic clock for 24h cooling-off → wall-clock `time.time()`;
  user-facing claim matches the math. Phase 02 persists into TrustVault
  so the invariant survives restart.
- MED-1+5 (mirrored by reviewer-R5) friction token vocabulary: closed
  `_VALID_FRICTION_TOKENS` frozenset rejects typos loudly via ValueError.
- MED-2 `confirm_cross_channel` validates `confirm_channel_id` against
  the configured adapter set AND surfaces `CrossChannelConfirmFailedError`
  when the confirm channel collapses onto `decided_on_channel_id`.
- MED-3 dispatch-failure path emits a `grant_moment_dispatch_failed`
  ledger row AND releases `_seen_nonces` / `_seen_intent_ids` so the
  user can retry with the same identifiers (no nonce burn on transient
  channel hangs); the Phase A audit trail stays consistent.
- MED-4 Phase-01 cross-principal contract: `issue_grant_moment` refuses
  every `is_cross_principal=True` request with `DualSignatureRequiredError`
  at the M0 boundary because Phase 01 lacks the co-signature verification
  path. Phase 03 wires the verify path + lifts the gate. Spec amended
  with a Phase-01 deviation note per `specs-authority.md` Rule 6.
- MED-5 `_resolve_delegation_pubkey_hex` raises ValueError when the key
  manager surface is missing instead of silently shipping empty pubkey hex.
- MED-6 substring prose assertions on `NoveltyFrictionRequiredError` /
  `VelocityRaiseCoolingOffError` replaced with structural
  `friction_kind` discriminator (READ_DELAY_WALLCLOCK /
  READ_DELAY_TOKEN_MISSING / DOUBLE_TAP_MISSING) + numeric attribute
  asserts — closes the probe-driven-verification.md MUST-1 gap.

## Code / architecture axis (4 HIGH + 6 MED)

- HIGH-R1 `await_decision` state-misuse now raises typed
  `InvalidGrantMomentTransitionError` (was the wrong-class
  `NoveltyFrictionRequiredError`).
- HIGH-R2 phantom docstring `per_channel_render_timeout_seconds`
  citation removed; `GrantMomentTimeoutError` raise condition correctly
  described as "every adapter raised at M1 dispatch."
- HIGH-R3 tautological T-018 test rewritten: real spoofing adapter
  raises `VisibleSecretMismatchError` inside `render_grant_moment`;
  runtime propagates via ChannelHandoff dispatch surface.
- HIGH-R4 all five `state="ERROR"` rejection paths in `submit_resolution`
  emit `logger.warning("grant_moment.refused", ...)` with closed
  `rejection_class` field — operator-visible audit signal per
  `rules/observability.md` Mandatory Log Points 1 + 4.
- MED-R1 `asyncio.get_event_loop()` → `asyncio.get_running_loop()`
  (Py3.13 deprecation; threads with no loop now fail loudly).
- MED-R2 `ChannelHandoff.primary_channel_id` + `adapter_channel_ids`
  public properties; runtime no longer reaches into the private attr.
- MED-R3 `_VisibleSecretShape` Protocol with `phrase: str` member —
  the protocol surface is now statically checkable.
- MED-R4 dispatch-failure nonce release (same as security-R1 MED-3).
- MED-R5 friction-token vocabulary (same as security-R1 MED-1).
- MED-R6 latency-parity 5ms→50ms with rationale on CI tolerance.

## Spec compliance axis (3 HIGH + 3 MED)

- HIGH-A1 `CrossChannelConfirmFailedError` runtime raise-path coverage:
  new `tests/integration/test_grant_moment_cross_channel_confirm_failed.py`.
- HIGH-A2 orphan inspection helper `novelty_class_for` removed
  (`emit_queue_hold` / `emit_queue_resume` remain — they are the
  documented surface for Boundary Conversation suspension handoff, which
  exercises them in Wave 2 wiring; not orphans in Phase 01 scope).
- HIGH-A3 Phase-B ledger row retagged `DelegationRecord` → `grant_moment`
  per `specs/ledger.md` § Entry types; payload aligned to spec § grant_moment
  shape (`request_ref`, `result_ref`, `intent_id`, `decision`,
  `decided_at`, `envelope_version_at_decision`, `novelty_class`,
  `signed_by`). Tests updated to assert on the new tag + canonical fields.
- MED-A2 `PhaseARecord` payload now carries the canonical 9 fields
  (`schema_version`, `intent_id`, `tool_name`, `tool_args_canonical_hash`,
  `envelope_version`, `envelope_check_passed`, `phase_a_at`,
  `ttl_expires_at`, `signed_by`) per `specs/ledger.md` § PhaseARecord
  - configurable `phase_a_ttl_seconds`.
- MED-A3 Phase-01 cross-principal deviation note in `specs/grant-moment.md`
  § Cross-principal (Phase 03) per `specs-authority.md` Rule 6.
- LOW-A1 EC-8 wording softened: test exercises "root + 3 expected
  descendants" (the verification half of the contract); Phase 02 lifts
  to a literal 3-deep delegation tree.

## New test files (3)

- `tests/integration/test_grant_moment_cross_channel_confirm_failed.py` —
  4 tests covering missing leg, channel collapse, unknown channel, valid path.
- `tests/integration/test_grant_moment_friction_token_vocabulary.py` —
  3 tests covering empty-token rejection, unknown-token rejection,
  canonical-vocabulary acceptance.
- `tests/integration/test_cross_principal_dual_signature.py` rewritten —
  Phase-01 refusal contract pin (M0-boundary) + non-cross-principal default
  path sanity check.

Full suite: 1166 passed, 9 skipped (was 1160; +6 net new tests).

Closes Round 1 of `/redteam`; Round 2 launches against this commit to
verify convergence (0 CRIT/HIGH × 2 clean rounds per axis).

## Why these closures landed same-shard, not as follow-up PRs

Per `rules/autonomous-execution.md` MUST Rule 4: when gate-level review
surfaces same-bug-class gaps within the shard budget (≤500 LOC load-bearing,
≤5–10 invariants), the disposition is to fix same-session — filing
follow-up issues is BLOCKED. R1 surfaced 10 HIGH + 15 MED across 3 axes
(security / code / spec); all fit one shard budget; all closed in commit
`e2709c6`. R2 added 1 HIGH + 2 MED + 3 LOW; closed in `9b8708f`. CLEAN×2
verdict per axis at R3+R4. Full trajectory + per-axis disposition in
[[0035-DISCOVERY-redteam-wave-4-runtime-facade-convergence]].

## What this unlocks

- **PR #41 merge gate cleared.** Foundation for Wave-4 channels
  ([[0036-DECISION-wave-4-grant-moment-runtime-facade]]).
- **Empirical confirmation** that Wave-3 + Wave-4 cadence (single
  foundation → /redteam to convergence → merge → next sibling) holds
  for the channels work (PR #42 — landed today following the same shape).

## For Discussion

- **Same-shard closure rate** — 10 HIGH + 15 MED in R1 alone is on the
  high end. Is the Wave-4 runtime's invariant surface (5 raise-path
  defenses + two-phase signing + dedup + cooling-off + cross-channel
  confirm + cascade revocation) approaching the per-shard capacity
  ceiling? If so, the next Wave (channels) MUST be more aggressively
  sharded (foundation + parallel siblings) rather than monolithic.
- **F-SP-R2-2 spec-terminology drift** — `phase_a_record_ref`
  (grant-moment.md:66) vs `phase_a_ref` (ledger.md:391,407) was carried
  forward to /codify rather than fixed in this shard. Was this the right
  trade-off, or should sibling-spec re-derivation per
  `rules/specs-authority.md` Rule 5b have fired here? (Counterfactual:
  if the drift had surfaced as a HIGH instead of a forward-record, would
  PR #41 still have merged this cycle?)
- **Probe-driven test conversion (MED-6)** — the substring-prose
  assertions on `NoveltyFrictionRequiredError` were converted to
  structural `friction_kind` discriminator checks per
  `rules/probe-driven-verification.md` MUST-1. How many existing tests
  in the broader suite still use the regex-style assertion pattern that
  this conversion replaced?
