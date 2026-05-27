---
type: DISCOVERY
date: 2026-05-27
created_at: 2026-05-27T00:00:00Z
author: co-authored
session_id: 8d16380b-9f76-422c-aef7-8d805d4d19e3
session_turn: convergence
project: phase-01-mvp
topic: Wave-A channels (Telegram + Slack + Discord) /redteam R1-R5 closure + R6 verification
phase: redteam
tags:
  [
    wave-a,
    channels,
    telegram,
    slack,
    discord,
    redteam,
    convergence,
    ssrf,
    sibling-bypass,
    foundation-pattern,
  ]
---

# DISCOVERY — Wave-A channels /redteam reaches CLEAN×3-axis convergence at R6

## What converged

PR #43 (`feat/phase-01-wave-a-channels`, HEAD `9045cc8`) shipped TelegramChannelAdapter + SlackChannelAdapter + DiscordChannelAdapter built in 3 parallel worktrees from the Wave-4 channels foundation (PR #42, journal-0038). After 5 rounds of /redteam closure + 1 verification round, all 3 axes (security-reviewer, reviewer, spec-compliance) returned **CLEAN — zero CRIT / HIGH / MEDIUM / LOW** at R6 against HEAD.

- Tests: 261/261 channel tests pass; 1431 total + 9 skipped (acceptable infra-conditional)
- Ruff: clean across `envoy/channels/` + `tests/integration/channels/`
- Split-state scan empty on `specs/channel-adapters.md` (zero matches for forward-looking/scaffold/TBD framings)
- All 11 spec-taxonomy errors raised by ≥1 adapter
- `__all__` count = 34, matches pin-test assertions
- ABC contract: all abstract methods implemented on all 3 new adapters; Phase-02 ritual surfaces inherit `PhaseDeferredError`

## Per-round trajectory

| Round |    Security |      Reviewer |      Spec | Closure SHA                               |
| ----: | ----------: | ------------: | --------: | ----------------------------------------- |
|    R1 |     0/3/4/3 |       0/3/3/3 |   1/4/5/3 | `817c881`                                 |
|    R2 |     0/2/5/2 |       0/2/3/3 |     2/5/3 | `0d49405` (merge) + closure agent commits |
|    R3 |     0/3/3/2 |       0/2/3/3 |     1/3/2 | `829f2a6`                                 |
|    R4 |     0/1/2/2 |       0/0/1/2 |     1/2/3 | `9a234c1`                                 |
|    R5 | 0/0/0/2 LOW | 0/0/0/1 LOW\* |   0/0/2/1 | `9045cc8` (R5 polish)                     |
|    R6 |   **CLEAN** |     **CLEAN** | **CLEAN** | —                                         |

\*R5 reviewer LOW was a verified false-positive (Discord `send_message` DOES raise `PrincipalNotFoundError` at `discord.py:422`); security R3 + R6 both confirmed.

Cumulative density: 4 CRIT/HIGH closed (1 CRIT @ R1: Discord shared inbound-queue race; 3 HIGH @ R3-R4: Telegram idempotent register, dotted-hex SSRF, shutdown contract), ~26 MEDIUM closed, ~25 LOW closed across the 5 closure rounds.

## Receipts (per `rules/verify-resource-existence.md` MUST-4)

R6 axis reports (external receipts — orchestrator did NOT self-attest convergence):

- Security R6 agent ID `a3d4360788fde2706` — verdict CLEAN, R1-R5 cumulative regression PASS, probe matrix CLEAN at HEAD `9045cc8`
- Reviewer R6 agent ID `aba39b4e358a81c59` — verdict CLEAN, 261/261 tests pass + 119 closure pins, sibling-site sweep CLEAN, 0 forbidden file edits
- Spec R6 agent ID `a9b5ef689292d5837` — verdict CLEAN, 6 mechanical sweeps PASS, citation resolution exact match (5 hostname-blocklist entries in code = 5 in spec)

## 7 invariants from journal-0038 inherited + sibling-verified

The Wave-A siblings inherited and structurally satisfied all 7 foundation invariants:

1. **Canonical discriminators** — `send_grant_moment` reads `grant.high_stakes` (Payload bool); `render_grant_moment` reads `novelty_class == "high_stakes"` (Request string).
2. **Derived vocabulary canonicalisation** — `frozenset(typing.get_args(GrantMomentDecision))` everywhere; no hand-mirrored lists.
3. **Single write-site `_register_pending`** — idempotent (returns existing Future/Queue on duplicate `request_id`); ceiling enforced before write.
4. **High_stakes auto-gate** — `must_be_primary = primary_only or grant.high_stakes`; defense-in-depth on every send_grant_moment.
5. **PII hash** — sha256[:8] on principal IDs / session IDs in every INFO/WARN log line.
6. **`_register_pending` discipline** — entry removed in `finally` block regardless of outcome (timeout, cancellation, decision) on all 3 adapters.
7. **Phase-02 ritual surfaces inherit `PhaseDeferredError`** — `send_posture_review` / `send_monthly_report` not overridden.

## Sibling-bypass pattern discovered (R2-R4)

The single most important recurring failure mode across R2-R4 was **"Telegram is the structural odd-one-out"**: R2's closures (idempotent `_register_pending`, rate-limit gating, config dataclass, shutdown cleanup) landed cleanly on Discord + Slack (which share Future-based pending-dict + dataclass config) but Telegram (Queue-based pending, plain-attr config, independent `send_digest` that doesn't delegate to `send_message`) systematically MISSED each sibling fix. The pattern surfaced as:

- R2 closure → R3 finds Telegram-variant missing
- R3 closure → R4 finds the sibling extension (e.g. `send_message` gate ordering: R3 fixed `send_grant_moment` only)
- R4 closure → R5 finds the spec-text drift introduced by the prior round's documentation
- R5 closure → R6 verifies (CLEAN)

The orchestrator caught one mid-round bug independently (telegram.py `.done()`/`.cancel()` called on `asyncio.Queue` — R2 agent copied Discord/Slack Future-cancel pattern; the M-2 test masked it by planting a Future into the Queue dict; pyright surfaced the type error at merge time). Re-wrote the test to exercise the real production cancel-then-shutdown path.

## Process discoveries

1. **Orphan-recovery protocol fired once.** R3 closure agent terminated mid-task with 5 modified files + 1 new test file but ZERO commits (per `worktree-isolation.md` MUST Rule 3, the worktree auto-cleans without commits — work would have been lost). The orchestrator manually committed the agent's work in-place before the auto-clean, then resumed.
2. **Spec-edit accuracy is hard.** My own R3 spec edit asserted a contract Slack+Discord didn't satisfy (`GrantMomentExpiredError` on shutdown) — R4 spec axis caught it. My R4 closure agent's spec edits then over-promised hostname blocklist coverage — R5 spec axis caught it. Both forced same-shard polish closures.
3. **Probe-driven verification matters.** The R2 M-2 test "passed" only because it planted the wrong-type object into the dict. The rewrite to exercise the actual production path makes regression to the old buggy code fail loudly via runtime `AttributeError`, not via a silent type-mismatched green.

## Deferred-to-Phase-02 (recorded in workspace todos)

`workspaces/phase-01-mvp/todos/active/wave-4-channels-regression-tests.md` records 3 deferred items per `rules/value-prioritization.md` MUST-2:

- L-2-R3: extract `TelegramChannelConfig(frozen=True, slots=True)` for parity with Discord/Slack configs (cosmetic; no active leak)
- LOW-R3-L-02: hash `PrincipalNotFoundError.target_principal_id` in errors.py (foundation-frozen this shard; in-adapter WARN paths already hash)
- MED-R3-3: align Discord + Slack delivery to Telegram's injected-`send_fn` pattern so all 3 share one delivery contract (Phase-02 with real bot tokens)

Plus the 5 Wave-A/B forward-declared regression tests (T-018, T-070, T-080, T-023, EC-7 session continuity) that own the sibling Wave-B + cross-channel acceptance criteria.

## Unlocks

Wave-A delivers 3 of 8 EC-7 channels with zero legal-tier caveats (bot-API clean per `specs/channel-adapters.md` § Phase 01 surfaces). The brief value-anchor (`workspaces/phase-01-mvp/.session-notes` § Forest vs trees) is met.

Next pickable forest items per `02-plans/01-build-sequence.md`:

- **Wave-B** caveated channels (WhatsApp + iMessage + Signal) — paid-tier + Apple-ToS-grey + Path-B legal-gate; de-scope #1 fallback retained
- **`envoy.daily_digest` scheduler** (sibling shard 11) — `apscheduler.AsyncIOScheduler` + per-principal CronTrigger; gates EC-3 (≥7 consecutive days digest fire)
- **EC-7 cross-channel session continuity** end-to-end test (24 onboardings: 8 channels × N=3 first-time-user sessions)

## For Discussion

1. **Was the 5-round (+R6 verification) closure trajectory necessary?** The foundation (PR #42) converged in 5 rounds with similar density. Wave-A's 4 HIGH + 4 HIGH (across R1-R4) + 2 HIGH (R4) sibling-bypass pattern suggests the 3-parallel-worktree pattern systematically replicates structural divergence (Future vs Queue, dataclass-config vs plain-attr) that compounds at /redteam. **Counterfactual**: would a single-author serial Wave-A have produced fewer sibling bypasses (because the author sees each sibling's pattern), at the cost of 3× wall-clock? Evidence point: the orchestrator's mid-round Telegram shutdown bug catch (Queue vs Future `.cancel()`) was a sibling-bypass that even the closure agent missed — the structural divergence is durable across agents.
2. **Should the spec assert behavioral parity across siblings explicitly?** Currently `specs/channel-adapters.md` describes the ABC contract once; the per-adapter divergence (different cleanup primitives, different delivery shapes) is invisible to a spec reader. A `## Per-adapter implementation matrix` table noting "Discord+Slack: Future / Telegram: Queue" with the consequence ("cancellation cleanup pattern differs") would surface the divergence at design time, not at /redteam round 4.
3. **`/redteam` round budget vs sibling-bypass density** — for future N-parallel-sibling shards, should `/todos` pre-shard a "sibling-parity sweep" as a mandatory step BEFORE /redteam? Evidence: every round's sibling-bypass finding was structurally predictable once the divergence was named (Telegram = odd-one-out). A pre-/redteam parity audit (1 cycle) could collapse R2-R4's 3 sibling-bypass rounds into 1.

## Cross-references

- Foundation convergence pattern: [[0038-DISCOVERY-redteam-wave-4-channels-foundation-convergence]]
- Foundation runtime convergence: [[0035-DISCOVERY-redteam-wave-4-runtime-facade-convergence]]
- Build sequence anchor: `workspaces/phase-01-mvp/02-plans/01-build-sequence.md:232` § Wave 4 step 3
- PR: https://github.com/terrene-foundation/envoy/pull/43
