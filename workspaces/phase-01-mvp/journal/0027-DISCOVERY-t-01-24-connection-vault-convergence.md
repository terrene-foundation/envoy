---
type: DISCOVERY
date: 2026-05-25
created_at: 2026-05-25T00:00:00Z
author: agent
session_id: 986c684c-2308-444d-93e9-c373676e0ca7
session_turn: convergence
project: phase-01-mvp
topic: T-01-24 Connection Vault — /redteam convergence receipt
phase: redteam
tags: [connection-vault, redteam, convergence, T-01-24, wave-1, durable-receipt]
---

# T-01-24 Connection Vault — /redteam convergence receipt

Durable external receipt for the T-01-24 Connection Vault `/redteam`
convergence, per `rules/verify-resource-existence.md` MUST-4 ("Convergence /
Round-Verdict Claims MUST Cite Durable Receipts"). Without this entry the
"2 consecutive clean rounds" claim is self-attestation; this entry + the
commit trail are the external receipt the next session (or `/sweep`) can
verify by inspection.

## What converged

T-01-24 (`envoy/connection_vault/` — OS-keychain credential adapter) was
picked this session as the deepest unblocker on the EC-1 critical path
(T-01-24 → T-01-22 model router → T-02-40 Boundary Conversation runtime →
EC-1 acceptance gate). The forest pick T-02-40 was structurally blocked
because T-01-22 (model router) was unbuilt and T-01-22 itself blocks on
T-01-24 (secret routing: "NEVER `.env` plaintext" per its line 601).

## Round-by-round trajectory

All rounds audited via independent background agents (general-purpose,
full tool inventory) per `rules/agents.md` § "Audit/Closure-Parity
Verification Specialist Has Bash + Read".

| Round  | HEAD SHA  | CRIT | HIGH | MED | LOW | NIT | Verdict   | Closure                                                                           |
| ------ | --------- | ---: | ---: | --: | --: | --: | --------- | --------------------------------------------------------------------------------- |
| gate   | `1e3c0df` |    0 |    1 |   8 |   8 |   2 | NOT CLEAN | sweep → `b334dce` (sec M2/M3/L3 + rev HIGH-1/MED-1/4/5)                           |
| R1     | `b334dce` |    0 |    0 |   2 |   3 |   2 | NOT CLEAN | sweep → `1095a32` (F2/F5/F4/F1/F7/F6)                                             |
| R2     | `1095a32` |    0 |    2 |   0 |   1 |   2 | NOT CLEAN | sweep → `4f7ad5d` (H1 channel_denylist + H2 spec + N1/N2)                         |
| R3     | `4f7ad5d` |    0 |    2 |   1 |   0 |   0 | NOT CLEAN | sweep → `6425f81` (H1 envelope-model spec + H2 phantom citation + M1 parametrize) |
| R4     | `6425f81` |    0 |    1 |   1 |   0 |   0 | NOT CLEAN | sweep → `f3d73d0` (H1 phantom-chain sweep + M1 citation-load)                     |
| **R5** | `f3d73d0` |    0 |    0 |   0 |   0 |   0 | **CLEAN** | (first of 2 consecutive)                                                          |
| **R6** | `f3d73d0` |    0 |    0 |   0 |   0 |   0 | **CLEAN** | (convergence MET — independent re-derivation)                                     |

**Convergence MET** per `briefs/00-phase-01-mvp-scope.md` § Exit criteria
("/redteam passes: spec-compliance AST/grep verified, 0 CRITICAL/HIGH
findings, 2 clean rounds"): Round 5 + Round 6 are 2 consecutive clean
rounds at the same HEAD `f3d73d0`. Round 6 was an independent
re-derivation (NOT a re-scan of Round 5's notes) per
`journal/0026` convergence discipline.

## Meta-pattern: every NOT-CLEAN round was same-bug-class continuation

`journal/0026` Pattern 1 ("Round-N+1 scans the FIX SITE") fired on every
round. The notable chain was the phantom-citation lifecycle:

- R1-F4 (my own fix) introduced `rules/security.md § "Fail-Closed Security
Defaults"` — a citation to a section that never existed.
- R3-H2 caught it in the SPEC layer (`specs/connection-vault.md`) and fixed
  only that site.
- R4-H1 caught the SAME phantom still present in the SOURCE comment
  (`scope.py:54`) AND a TEST comment (`test_envelope_config_dataclass_post_init.py:61`)
  — the spec fix had not swept the call-graph siblings.
- R4-M1 then caught that the R3-H2 replacement citation
  (`rules/pact-governance.md § "Fail-Closed Decisions"`) grep-resolved but
  carried a NARROWER claim than the deny-priority semantic; the true
  load-bearing lemma is `specs/envelope-model.md:119` ("denylists UNION;
  allowlists INTERSECTION").

**Lesson for next session:** a phantom-citation fix MUST sweep the full
identity chain (spec → source comment → test comment) in ONE pass, and the
replacement citation MUST be load-bearing-verified (does the cited section
carry the claim?), not merely grep-resolve-verified. This is a tightening
candidate for `rules/spec-accuracy.md` MUST Rule 1 at `/codify`.

## Same-class fix discipline held

Every NOT-CLEAN round was closed by same-shard fix-immediately per
`rules/autonomous-execution.md` MUST Rule 4 — zero follow-up issues filed
for same-bug-class gaps within shard budget. Two items were legitimately
deferred (not same-class / exceed Phase-01 scope):

- R2-L1 → Phase-02 todo `T-11-XX` (partial-write keychain rollback) in
  `todos/active/11-phase-02-handoff.md`. Value-anchor: atomic-fail-closed
  set() vs current partial-orphan-on-index-failure; not EC-blocking.
- R4-R1-F3 → deferred NIT spec-heading wording polish (cosmetic).

## What T-01-24 unlocks

- **T-01-22** (model router) — now buildable; routes LLM provider secrets
  to the Connection Vault per its "NEVER `.env` plaintext" contract.
- **T-02-40** (Boundary Conversation runtime) — the forest pick; writes
  credentials on onboarding per shard 14 § 5.2 via
  `import_credentials_from_env`.
- **Wave 4 channel adapters** (T-04-\*) — read bot tokens / API keys on
  adapter init per shard 14 § 5.1.

## Open follow-up (out of T-01-24 scope)

- **T-01-25** — Tier 2 wire-up against real OS keychain (macOS Keychain /
  Linux Secret Service / Windows Credential Manager) on the CI matrix.
  T-01-24 ships the primitive with `keyring_backend=` DI so Tier 1 stays
  backend-agnostic; T-01-25 closes the real-keychain coverage. This is the
  reason the T-01-24 PR has 0 Tier 2 tests — intentional per shard 14 § 6.1.

## For Discussion

1. **Counterfactual:** if the gate-review reviewer + security-reviewer had
   run the mechanical phantom-citation grep (`grep -rn "§ \"" specs/ envoy/`
   cross-checked against `.claude/rules/`), would R1-F4's phantom have been
   caught at gate time instead of surviving to R4? The citation was
   introduced in the R1 _fix_, so gate-review (which ran against the origin
   commit `1e3c0df`) could not have seen it — but a citation-resolution
   sweep in EVERY round's protocol (not just spec-accuracy rounds) would
   have caught it at R2 instead of R4. Should the per-round protocol always
   include a `.claude/rules/` citation-resolution grep?

2. **Data point:** the convergence took 6 rounds + a gate-review = 7 audit
   passes for a ~780-LOC primitive. Of the 7, 5 were NOT-CLEAN, and 4 of
   those 5 were same-bug-class continuations of a prior round's own fix
   (the phantom-citation chain alone consumed R3-H2 → R4-H1 → R4-M1). Is
   the high round-count a signal that the gate-review prompt should have
   included the citation-load-bearing check up front, collapsing 3 rounds
   into 1? Or is the round-count the expected cost of the FIX-SITE-scan
   discipline working as designed?

3. **Counterfactual:** had the agent filed the R1/R2/R3 findings as
   follow-up issues instead of same-shard fixes, how many sessions would
   T-01-24 have taken to reach the same converged state? The MUST-Rule-4
   evidence says 2–5× the marginal cost per deferred round; with 5
   NOT-CLEAN rounds that is a 10–25× multiplier avoided by staying in-shard.
