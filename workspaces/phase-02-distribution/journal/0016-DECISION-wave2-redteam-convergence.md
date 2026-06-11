---
type: DECISION
date: 2026-06-12
author: co-authored
project: phase-02-distribution
topic: Wave-2 /redteam converged — 24 findings fixed across 4 rounds + keychain-override deliverable (PR #96)
phase: codify
tags:
  [
    redteam,
    convergence,
    wave-2,
    security,
    keychain,
    init-cli,
    ohttp-tls,
    spec-accuracy,
  ]
relates_to: 0014-DECISION-implement-wave2-batch2-complete
---

# Wave-2 `/redteam` CONVERGED — 24 findings fixed, 2 consecutive clean rounds

Receipt-class DECISION (coordination receipt; `## For Discussion` omitted per
`rules/journal.md`). Full report: `04-validate/01-wave2-redteam-convergence.md`
(lands with PR #96). This entry is the codify-phase durable record of the
redteam phase (journal writes are codify-branch-only per integrity-guard, so
this lands on `codify/jack-hong-2026-06-12`, separate from the redteam fixes on
PR #96).

## What converged

`/redteam` on the Phase-02 implemented shards (S1, S2a, S4s/S4r/S4i, S8/S8e,
S9a, S10) ran to convergence at L5_DELEGATED: **0 CRITICAL, 0 HIGH, 2 consecutive
clean rounds** (R3 delta + R4 full-scope). Fixes on PR #96
(`test/redteam-phase02-wave2-gate`, 25 commits, +1939/-333), awaiting human
merge to protected `main`.

## Rounds + dispositions

- **R1** (4 lenses: spec-compliance M1+M2 / M3+M4, test-verification, security):
  0C/8H/5M/9L → all 22 fixed in 4 disjoint worktree clusters (A runtime/grant/
  init, B foundation_ops TLS, C specs/workspaces, D test-hygiene). The R1
  code-quality + user-flow lenses were lost to a session limit and re-run in R2.
- **R2** (closure-parity + code-quality + user-flow walk + security): 0C/0H/1M/1L
  → both fixed (R2-Q-01 init partial-construction vault-unlock leak; UF-R2-L1
  `python -m envoy`).
- **R3** (closure + adversarial security, delta surface) + **R4** (full-scope
  spec/code/security; agents hit the server-side concurrency throttle so the
  deterministic sweep ran inline): 0/0/0/0 each — the two consecutive clean rounds.

## The load-bearing fixes (security-adjacent)

1. **W2G-001** — `envoy init` re-run exits 30 BEFORE prompting (was a
   post-9-question `FileExistsError` traceback); bootstrap translates it to the
   typed `VaultAlreadyInitializedError`.
2. **W2G-004** — grant-moment timeout writes the durable `expired` terminal; a
   late answerer can no longer flip a dead grant to `resolved`.
3. **F2 / F1** — `CertPinMismatchError` implemented (was raising the wrong type,
   untested); HSTS enforcement wired (was a dead config field).
4. **W2G-003** — session-store spec amended to the real signed-not-encrypted
   posture + threat-model residual + owned value-anchored S5o-enc follow-up.
5. **R2-Q-01** — `build_init_runtime` no longer leaves the TrustVault unlocked
   (master key in memory) on a partial-construction failure (acquisitions moved
   inside the cleanup try; innermost `finally` guarantees `vault.lock()`).
6. **W2G-002** — the 13 substrate-gated rs-adapter methods raise a typed
   `RuntimeNotReadyError` (was a phantom `self._trust_store.<name>` forward →
   untyped `AttributeError` under DI); workspace claim corrected to 18/31 wired.

(7 MED + 9 LOW: W2G-005/006/007/008/009/010, F3/F4/F5/F6/F7, SEC-LOW-1/2,
T-01/02/03, UF-R2-L1 — full list in the 04-validate report.)

## New deliverable: ENVOY_KEYRING headless override

The user-flow walk surfaced a keychain foot-gun — `envoy init` always hit the
real OS keychain, so it errored "keychain cannot be found" in a headless/
non-interactive context (the walk subprocess). The co-owner chose the root-cause
fix over recording-and-deferring: a fail-closed `ENVOY_KEYRING` allowlist (unset
→ real OS keychain default; `memory` → in-process ephemeral backend with a loud
warning; any other value → refuse, exit 32), wired into `envoy init`. Real
keychain stays the secure default and was verified untouched (0 entries before/
after). 7 regression tests. See journal/0017 for the reusable pattern.

## Gate receipts (PR #96 branch HEAD)

2098 passed / 9 skipped / 2 xfailed; `mypy envoy` + `pyright envoy` + `ruff
check .` clean; 0 WARN+ in the shipped pytest config; spec-accuracy scan clean
for every implemented-shard spec.

## Repo-class disposition (codify routing)

envoy is a downstream `coc-project` (`.claude/VERSION::type`), so per
`rules/artifact-flow.md` Step 7 → **no upstream COC proposal**: the findings are
envoy-application-specific, `.claude/{rules,agents,skills}` are loom-managed
(overwritten on `/sync`). The journal + workspace + specs ARE the local codify
targets. The two reusable PATTERNS (journal/0017) are candidates for a future
upstream COC proposal IF a sibling consumer hits the same class — recorded here,
not filed.

## Next

Human merge of PR #96; merge of this codify PR. Then Wave-2 batch-3
implementation (M1 conformance families S2b/S2c/S3a/S3b + the WS-6 serial chain)
per `todos/active/_index.md`. Bounded/owned items unchanged (P7/P9/P11,
S8-persist, S5o-enc; 3 pre-existing Phase-03-spec TBDs).
