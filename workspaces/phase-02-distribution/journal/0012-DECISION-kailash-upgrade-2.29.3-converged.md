# 0012 — DECISION — kailash upgrade 2.13.4 → 2.29.3 complete + /redteam converged (P8)

**Date:** 2026-06-10 · **Phase:** P8 (the APPROVED-next-action from `.session-notes`, executed BEFORE Wave-2 batch-2) · **Posture:** L5_DELEGATED.
**Source PR:** #90 (`chore/kailash-upgrade`, commits `a9519d0` + `e10e443`). **Convergence record:** `workspaces/kailash-upgrade/04-validate/redteam-convergence.md`. **Spec coverage:** `workspaces/kailash-upgrade/.spec-coverage-v2.md`.

## What landed

Whole kailash family → latest: kailash **2.29.3**, dataflow **2.11.3**, nexus **2.9.0**, kaizen **2.24.5**, pact **0.12.0**, mcp **0.2.14**. Import-compatible as scoped; three behavioral deltas surfaced via the full suite, each fixed at root.

1. **`[trust]` extra (415 errors → 0).** 2.29.3 carved `pynacl`+`cryptography` out of the default install into `[trust]` (default in 2.13.4). envoy is built on `kailash.trust.*` → add `trust` to the extra set; `[trust]` is the declared `pynacl` provider (`dependencies.md` § Declared=Imported). `cryptography` stays direct-declared (OHTTP/vault HPKE import).
2. **dataflow 2.7.7 → 2.11.3 (collection blocked → green).** The `[dataflow]` open floor left dataflow at 2.7.7, which has a duplicate `AggregateNode` registration that 2.29.3's now-fatal collision check rejects at import. Held-back package = root cause; family→latest per "Latest Versions Always".
3. **`TrustStoreAdapter._posture_store` lazy-init (23 ResourceWarnings → 0).** 2.29.3's `SQLitePostureStore.__init__` opens a persistent SQLite conn eagerly. Defer construction to `initialize()`, close+reset in `close()`, typed guard per `zero-tolerance.md` Rule 3a. Restores the documented "no I/O until `initialize()`" contract.

Suppression dispositions: **F3 DROPPED** (`Instance-based API usage` UserWarning — fixed upstream, verified 0 occurrences). **F4 KEPT** (`Unclosed AsyncLocalRuntime` ResourceWarning — still fires on 2.29.3, verified; genuine upstream leak).

## Verification + convergence

Full suite **1864 passed, 0 warnings, coverage 91%**; mypy+pyright clean; user-flow walk clean (`envoy posture` lifecycle; `build_library_nexus` register+close). /redteam L5: 3 parallel agents (reviewer + security-reviewer + spec-compliance), **0 CRITICAL / 0 HIGH**; two LOW fixed (typed guard, comment); 1 pre-existing LOW out-of-scope (`sqlite_perms.py` WAL/SHM window); **2 consecutive clean rounds → converged**.

## Cross-repo authorization receipt (repo-scope-discipline.md User-Authorized Exception)

`cross-repo-authorized: terrene-foundation/kailash-py`

- **Requester:** jack@kailash.ai (co-owner, this session).
- **Verbatim instruction:** "please submit, then /codify and resolve pre-existing ruff lint, then /wrapup for next session" — authorizing submission of the drafted F4 upstream issue (the agent had presented the full scrubbed draft + recommended filing; user selected "Draft it for my review" then directed "please submit").
- **Target repo:** `terrene-foundation/kailash-py` (the `kailash` package's canonical Repository + Bug Tracker per dist METADATA; `AsyncLocalRuntime` lives in `kailash/runtime/async_local.py`).
- **Bounded action:** `gh issue create` ONE issue — "`Nexus.close()` does not cascade-close the internal `AsyncLocalRuntime` (ResourceWarning at GC)" — body scrubbed of all downstream context per `upstream-issue-hygiene.md` Rules 2+3 (pure-`nexus` minimal repro, 5 sections only, no envoy/workspace/finding-tag references). No incidental reads or writes against the target repo.
- **Timestamp:** 2026-06-10.
- **Scope:** filing only; the agent does NOT commit/push to kailash-py (BUILD repo — `/autonomize` Prudence).

## Forest impact

- **P8 CLOSED** — upgrade landed + converged; de-risks Phase-02 shards on the trust/Nexus surface (S8e/S9a/S10).
- **P6 advanced** — F3 resolved upstream (suppression dropped); F4 verified still-current → filed upstream (issue link to be appended on submission).
- **Next** (human gate): Wave-2 batch-2 value-rank — WS-4 S8e/S9a vs M1 conformance families (S2b/c/S3a/b) vs `init` S4i.

## Codify scope note

envoy is a `coc-project` (downstream consumer) → `/codify` Step 7 SKIP (no upstream COC proposal; artifacts stay local). No new rules authored → no Trust Posture Wiring required. Knowledge captured = this DECISION + `learning-codified.json` bookkeeping. The upgrade learnings are envoy-app-specific (not reusable COC artifacts), so they live here, not in a shared skill/agent.
