---
type: DISCOVERY
status: durable
created: 2026-05-25
session: phase-01-mvp Wave-2 Boundary Conversation
---

# /redteam convergence — T-02-40/41/42 Boundary Conversation (CLEAN×2 across 3 axes)

## Verdict

**CONVERGED.** 0 CRITICAL / 0 HIGH across spec + security + testing for two
consecutive clean rounds (R2, R3). Branch
`feat/phase-01-T-02-40-boundary-conversation`, convergence HEAD `a0f5fd2`.

## Scope shipped

The Boundary Conversation primitive (EC-1 acceptance unblocker, brief § Surfaces)
plus the three prerequisites that journal 0030 found unbuilt:

- `envoy/authorship/novelty.py` — `NoveltyChecker` (Jaccard-only, T-023; classifier deferred P04 per spec permissive-OR).
- `envoy/trust/store.py` + `types.py` — boundary persistence (`set/get_visible_secret`, `persist/load_boundary_conversation_state`, `shadow_segment_unread_duress_events`), `VisibleSecret`, `BoundaryConversationStateRow`.
- `envoy/boundary_conversation/` — `errors` (7-error taxonomy), `signatures` (9 S1–S9), `script` (S0→S10 Plan-DAG), `envelope_assembler`, `resume`, `bet12_telemetry`, `runtime` (`BoundaryConversationRuntime` facade).

## Round trajectory (receipt per verify-resource-existence MUST-4)

| Round | Spec                                        | Security                                      | Testing                     | Disposition                       |
| ----- | ------------------------------------------- | --------------------------------------------- | --------------------------- | --------------------------------- |
| R1    | 1 HIGH / 2 MED / 2 LOW / 1 NIT (`a85367d3`) | 2 HIGH / 2 MED / 2 LOW (`a86b623c`)           | 1 HIGH / 1 MED (`a6aba308`) | same-shard fix sweep (`ab798168`) |
| R2    | CLEAN 0/0/0 (`a448848c`)                    | CLEAN 0 CRIT/0 HIGH, 1 MED carry (`aa6fd481`) | CLEAN 163/14/0 (`a273ed6d`) | clean round #1                    |
| R3    | CLEAN 0/0/0 (`a7631ea6`)                    | CLEAN 0 CRIT/0 HIGH (`ae1ae784`)              | CLEAN 163/14/0 (`a0be8cfd`) | clean round #2 → CONVERGED        |

Build agents: A1 NoveltyChecker (`a5116001`→`99ac6b9`), A2 trust methods
(`a9c6ce5d`→`fd66c2d`), A3 signatures+script (`ace5b928`→`dc32988`), Wave-B
runtime (`a526d0be`→`fe8cbfd`/`5f36d91`/`6e6ba39`/`17cd22d`/`8cb2aa1`).

## R1 HIGH findings + fixes (all CLOSED, re-derived independently R2+R3)

1. **Shamir suspension never cleared (EC-1 dead-end).** `_handle_shamir` set
   `plan.suspension`; S9 Gate-2 refused to sign while non-None; nothing cleared
   it and the 3 tests masked it by poking `plan.suspension = None`. Fix: public
   `resume_from_shamir(ritual_id)` (`088cf89`) — the user's invocation IS the
   offline-ritual-completion confirmation (P01 cannot programmatically verify
   physical card distribution). Tests rewired to the public path.
2. **Fake-encryption docstrings.** `.bc.db` is plaintext (consistent with the
   existing plaintext `.chain.db`/`.posture.db` sub-stores) but docstrings
   claimed AES-256-GCM as current. Fix: corrected to plaintext-at-rest-until-
   T-01-13 (`759a548`). Routing through the real `vault.py` AESGCM container is
   T-01-13's master-key-flow architecture, out of this shard.
3. **Raw reply + S7 secret persisted plaintext** in `assembler_json`. Fix
   (`883e6ba`): removed `extraction["reply"]` stamp; `_FED_STATES` restricted to
   the 5 dimension states S1–S5 (S6/S7/S8/S9 no longer recorded); regression test
   asserts no reply/phrase/icon/color in the persisted row.
4. **Gate-back enforcement untested** (`VisibleSecretMissingError` T-018,
   `DuressBannerUnacknowledgedError`). Fix: deterministic-provider Tier-2 tests
   driving both gates through the public API.

Plus NIT `no-any-return` on the two bc-store `fetchone` helpers (`a0f5fd2`).

## Carry-forward dispositions (tracked, non-blocking)

- **MED-5 — BC-state row unauthenticated on rehydrate.** No posture-forge
  possible: S9 re-derives trust through `get_visible_secret` + suspension +
  `signed` gates + real `envelope_compiler.compile()` + `seed_genesis`. A forged
  `.bc.db` row cannot sign. Durable integrity (HMAC/signed row) folds into the
  T-01-17 Ledger-persistence / T-01-13 vault-container migration.
- **L1 — inline `CREATE TABLE` DDL in `store.py`.** Consistent with the existing
  chain/posture sub-stores + mirrors kailash-py's `SqliteTrustStore` idiom;
  pre-existing pattern, owned by the T-01-13 vault-container migration.
- **LOW-1/2 — spec-named E2E/regression files absent** (`test_boundary_conversation_full_path`,
  `_minimum_path`, N=3 EC-1). Owned by future shards **T-02-44** (Tier-2 wiring)
  and **T-02-45** (Tier-3 EC-1 acceptance, N=3 ≤25min). EC-1 real-LLM proof is
  NOT claimed by this PR.
- **NIT — S7 logs icon+color** (never the phrase). Insufficient alone to
  reconstruct the visible secret; pre-accepted.
- **Pre-existing — 6 mypy errors in `ledger/{canonical,facade}.py`, `vault.py`.**
  Reproduce on `main` (verified via `mypy main:envoy/ledger/facade.py`); outside
  this PR's diff + blast radius; mypy is not an enforced gate. Flag for a Wave-1
  mypy-cleanup follow-up.

## Test posture at convergence

985 collected, zero import errors. Tier-2: 163 passed / 14 skipped / 0 failed.
The Ollama full-conversation wiring test is `skipif(not OLLAMA_AVAILABLE)`
(ACCEPTABLE infra skip); the non-Ollama suite drives the FULL runtime against
real TrustStore/Ledger/EnvelopeCompiler/Shamir/Novelty with a deterministic
real-provider duck-type (BYOM-legit, no infra mocked). EC-1 N=3 real-LLM
acceptance is deferred to T-02-45.
