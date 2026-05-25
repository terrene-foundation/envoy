---
type: DISCOVERY
status: durable
created: 2026-05-25
session: phase-01-mvp Wave-2 Boundary Conversation
---

# T-02-40 prerequisites not shipped — shard-8 collaborators absent; wave order inverted

## Finding

`.session-notes` (2026-05-25) framed T-02-40 Boundary Conversation as
"reachable now — all prerequisites shipped + redteam-clean." A launch-time
verification sweep (per `rules/specs-authority.md` MUST Rule 5c +
`rules/agents.md` § Parallel Brief-Claim Verification) against `main` HEAD
`f9be3c1` found three of the runtime's six composed collaborators absent:

| shard-8 § citation | Symbol                                                                                                                                                | Verification                                                                                       | State               |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ------------------- |
| § 3.5 / § 5.4      | `envoy.authorship.NoveltyChecker.check_against_templates()`                                                                                           | `grep -rn "class NoveltyChecker" envoy/` → 0 (only a docstring mention in `authorship/score.py:8`) | **ABSENT**          |
| § 5.2 / § 3.6      | `TrustStoreAdapter.set_visible_secret / persist_boundary_conversation_state / load_boundary_conversation_state / shadow_segment_unread_duress_events` | `grep -n "def " envoy/trust/store.py` → only `seed_genesis`, `revoke`, `initialize`, `close`       | **ABSENT**          |
| § 3.7 mods 4–6     | `EnvelopeConfigInputAssembler`, `RitualResumeCoordinator`, `BET12TelemetryHook`                                                                       | `ls envoy/boundary_conversation/` → ENOENT (package does not exist)                                | **ABSENT**          |
| § 5.5              | `ShamirRitualCoordinator.start_3_of_5(...)`                                                                                                           | `grep -n "def " envoy/shamir/ritual.py` → `run_first_time_ritual(...)`, no `start_3_of_5`          | **SIGNATURE DRIFT** |

Verified-present collaborators: `EnvoyModelRouter` (model/router.py),
`EnvoyLedger` (ledger/facade.py), `EnvelopeCompiler` (envelope/compiler.py),
`TrustStoreAdapter` (trust/store.py, base surface), `ShamirRitualCoordinator`
(shamir/ritual.py, drifted method name).

## Why the session-notes claim was inaccurate

The T-02-40 todo's `Blocks on:` line names only `T-01-22 + T-01-12 + T-01-18`
(model router + trust store base + ledger) — all shipped. But the shard-8
runtime DESIGN composes a wider collaborator set (novelty, visible-secret
persistence, assembler, resume) that the todo's blocker line never captured.
The prior session read the narrow blocker line as "prerequisites shipped";
the design's true dependency set was unbuilt.

## Disposition — wave order inverted (leaf-first)

The runtime facade is the _root_ of the call graph; its collaborators are
_leaves_. Clean construction is bottom-up, NOT the plan's stated
"T-02-40 → then 41/42/43 parallel" order. Re-sharded:

- **Wave A (parallel, disjoint packages):** A1 `NoveltyChecker` (authorship,
  Jaccard-only per P01); A2 trust-store boundary methods; A3 signatures +
  Plan-DAG script (pure Kaizen).
- **Wave B (sequential):** `envoy/boundary_conversation/` runtime facade +
  envelope assembler + resume coordinator + bet12 telemetry + `__init__`,
  wiring A1/A2/A3 + existing model_router/ledger/envelope_compiler/shamir
  (using the real `run_first_time_ritual`, not the stale `start_3_of_5`).
- **/redteam to convergence.**

Phase-01 scope notes (not stubs — correct P01 behavior per
`rules/spec-accuracy.md` + shard-8 caveats): NoveltyChecker ships Jaccard
only (classifier = P04); `shadow_segment_unread_duress_events` returns `[]`
(no duress detection wired in P01 — the banner gate is correct, inert until
shadow segment populates in P02).

## Spec-edit obligation

`workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md`
§ 5.5 carries the stale `start_3_of_5` citation. Per `rules/specs-authority.md`
MUST Rule 5/5b this analysis doc is corrected at first instance when Wave B
wires the real Shamir surface.
