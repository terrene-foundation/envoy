# Phase 02 — Milestone 2 — WS-6 Durable Substrate

**Document role:** The 10 WS-6 todos `/implement` executes for the persistent-session substrate. Expands shards S4s, S4r, S4i, S4g, S5b, S5o, S6a, S6b, S6c, S7v from `02-plans/01-architecture.md` § Sharding plan (the WS-6 rows). Read `todos/active/_index.md` first, then this file, then the per-shard section.

**Milestone value (per `rules/value-prioritization.md` MUST-1):** HIGH. Anchor — `_index.md` M2 row + `ROADMAP.md` (Phase-02 scope) + the WS-6 deep-dive `01-analysis/01-research/06-ws6-durable-substrate.md`. This milestone unblocks the **last 3 of 10 canonical CLI commands** (`init`, `chat`, `grant` — visible product completion) AND ships the **mandatory Rust verifier** that closes Phase-01 forest **F2** and unblocks **F4** (per the forest ledger in `workspaces/phase-01-mvp/.session-notes`). It is the phase **long pole** — start early; it cannot be compressed by parallelization (see the serialization header below).

---

## ⚠️ SAME-CLASS SERIALIZATION — DO NOT WORKTREE-PARALLELIZE THIS MILESTONE

Per `02-plans/01-architecture.md` § "Cross-workstream dependency graph" and `rules/multi-operator-coordination.md` §3 (SAME-class) + `rules/worktree-isolation.md`: the genuine WS-6 constraint is **NOT dependency depth** but **SAME-class merge contention**. Almost every shard below edits `envoy/grant_moment/runtime.py` and/or the new store module (`envoy/runtime/session.py` + the TrustVault sub-store). Two agents editing `runtime.py` in parallel worktrees produce a 3-way merge that silently discards one shard's edits to the load-bearing `await_decision` / `post_decision` rendezvous path (`runtime.py:688-743`).

**`/implement` MUST run these shards serially (one session each, one branch each, merge-before-next).** The DAG below shows which shards are _logically_ parallel; that parallelism is **suppressed** because the file-touch set overlaps. The ONE genuinely-isolatable shard is **S7v** (separate Rust crate, separate repo `terrene-foundation/envoy-ledger-verifier`, zero `runtime.py`/store touch) — it MAY run concurrently with any S4*/S5*/S6\* shard.

**Dependency DAG (logical — serialize anyway except S7v):**

```
S4s (store) ──┬─► S4r (rendezvous) ──► S4g (grant)
              ├─► S4i (init, store-only)
              ├─► S5b (boundary signal) ──► S5o (observed-state)
              ├─► S6a (classification Tier-2)
              └─► S6b (envelope-intersection)
                              S4r,S5b,S5o ──► S6c (chat, LAST)
S3b (WS-1 E7 vectors) ─────────────────────► S7v (Rust verifier — ISOLATABLE)
```

**File-touch ownership (the SAME-class evidence):**

| Shard | `runtime.py`                | new store (`runtime/session.py` + sub-store) | other                                               |
| ----- | --------------------------- | -------------------------------------------- | --------------------------------------------------- |
| S4s   | read                        | **OWNS** (creates)                           | `runtime/adapters/kailash_py.py`                    |
| S4r   | **OWNS** `:688-743` rewrite | read/write poll                              | —                                                   |
| S4i   | —                           | read                                         | `boundary_conversation/runtime.py`, `cli/main.py`   |
| S4g   | read (post_decision path)   | read/write (pending queue)                   | `cli/` grant group                                  |
| S5b   | —                           | write (boundary signal)                      | `session-state` emitter                             |
| S5o   | —                           | **OWNS** observed-state region               | first-time-action gate                              |
| S6a   | —                           | read (clearance ctx)                         | `ledger/facade.py`, adapter classifier methods      |
| S6b   | —                           | read                                         | `envelope/compiler.py:296-308`, `envelope/scope.py` |
| S6c   | read (drives rendezvous)    | read/write                                   | `channels/{web,telegram,discord}.py` `send_message` |
| S7v   | —                           | —                                            | **separate repo** — ISOLATABLE                      |

---

## Build vs Wire discipline

Per the `/todos` contract every data-consuming/producing component carries a **Build** (structure + logic) and a **Wire** (connect to real source, zero mock) obligation. WS-6 shards mostly bundle both (the store IS the real source they wire to), so each section's `## Acceptance criteria` lists the build gate AND the wire gate explicitly. `Loop` column from the architecture map: **base** = no live loop until the substrate dependency lands; **live** = deterministic loop within the shard.

---

## S4s — Store-backed `SessionRouter` + durable projections

**Type:** Build+Wire.
**Value-anchor:** WS-6 deep-dive `06-ws6-durable-substrate.md` Q1 Option A (RECOMMENDED) — "a `SessionRouter` that opens a durable pending-grant TrustVault sub-store + a durable SessionObservedState region on each invocation, exactly as `daily_digest/bootstrap.py` re-opens the ledger." This is the root that gates the entire milestone; "that single drawer is what makes `init`, `chat`, and `grant` all work" (deep-dive § plain-terms).
**Implements:** `specs/session-state.md` § Persistence (Trust Vault region snapshot at every Ledger append) + the SessionObservedState schema region (`session-state.md:24-59`); `specs/grant-moment.md:104` + `runtime.py:393-394` "Phase 02 lifts this into a TrustVault sub-store" (pending-grant sub-store). No spec-of-record for `SessionRouter` exists yet (deep-dive spec-gap #1) — land `specs/session-runtime.md` as the code lands (code-first per `rules/specs-authority.md` Rule 5 + `rules/spec-accuracy.md` Rule 5), NOT ahead.
**Depends:** — (Wave-1 root).
**Scope:** Create `envoy/runtime/session.py::SessionRouter` that, per process invocation, re-opens (a) a durable **pending-grant TrustVault sub-store** and (b) a durable **SessionObservedState region**, mirroring the proven cross-process re-open pattern at `envoy/daily_digest/bootstrap.py:51,108,116` + `envoy/ledger/bootstrap.py:100`. Both projections are derived views over the append-only chain (replay-native per deep-dive Q4), keyed for fast lookup; the router is short-lived (no daemon, no socket/PID lifecycle). This shard delivers the empty-but-openable store + the router skeleton ONLY — the rendezvous rewrite (S4r), pending-grant read surface (S4g), and observed-state writes (S5o) are separate shards.
**Acceptance criteria:**

- Build: `SessionRouter()` opens both regions; a fresh process re-opens the SAME on-disk projection and re-hydrates from the persisted tail (Tier-2 test: write in process A, read in fresh process B — `rules/testing.md` § State Persistence read-back).
- Wire: store is the real keychain-gated TrustVault sub-store (`kailash.trust` SqliteAuditStore-class durable backing), NOT an in-memory dict; zero mock data per `rules/zero-tolerance.md` Rule 2.
- The pending-grant sub-store schema is pinned (deep-dive spec-gap #2 + open-question #2): key shape, `state` enum (`pending`/`resolved`/`expired`), TTL, index columns — decide (b) materialized-index-over-ledger vs (a) new sub-store at `/implement` per the flagged open question; record the decision in `specs/session-runtime.md`.
- `envoy/runtime/adapters/kailash_py.py` substrate-gated methods that only need store existence stop raising `Phase02SubstrateNotWiredError` where the store now backs them; others stay typed-raising until their shard lands.
- Crash-safety: a snapshot lands at every Ledger append (`session-state.md:182`) so a mid-session crash preserves pending grants + orphan-phase-A tracking.
  **Capacity check:** Invariants ≤6 (cross-process re-openability, append-only-projection discipline, keychain-key lifecycle, snapshot-at-append atomicity, sub-store key/TTL shape, no-daemon constraint). Call-graph hops ≤3 (`bootstrap → SqliteAuditStore → keystore`). ~350 LOC load-bearing (store + router skeleton; excludes generated schema boilerplate). Loop: **live**.

---

## S4r — Decision rendezvous: replace `asyncio.Future` with store-poll (PRIMARY)

**Type:** Build+Wire.
**Value-anchor:** WS-6 deep-dive **Round-1 red-team correction (R1-HIGH-1)** at `06-ws6-durable-substrate.md:324-326` + `journal/0002`: "The STORE alone does NOT unblock `grant` (or `chat`) — the cross-process rendezvous needs a mechanism change." This is the load-bearing redesign without which `grant` does not function even after S4s ships.
**Implements:** `specs/grant-moment.md` § State machine (M2 await decision) + § Timeout (default 5min) + the `GrantMomentExpiredError` row in the Error taxonomy (`grant-moment.md:140`). The timeout-audit-row contract at `runtime.py:720-726` MUST be preserved byte-for-byte (the M2→M3 transition is recorded so the timeout's audit row matches a successful path's).
**Depends:** S4s.
**Scope:** Replace the in-process `decision_future: asyncio.Future` rendezvous (`envoy/grant_moment/runtime.py:305`, set via `post_decision` `:733-743`, awaited via `await_decision` `:688-726`) with a **store-poll-with-monotonic-version-re-check as the PRIMARY mechanism** — a future cannot be `set_result`-ed across two OS processes, which is exactly the `grant` flow (request in one CLI invocation, answer in another). The requesting process polls the pending-grant sub-store for a resolution row, re-checking a monotonic version on each poll so a concurrent writer's decision is observed without lost-update; local IPC-signal is a **per-platform optimization layered on top, NOT an OR** (local IPC breaks on musl-static — architecture verdict WS-6). Preserve the `GrantMomentExpiredError` timeout audit row exactly: on poll-timeout, still drive the `next_state(..., TIMEOUT_EXPIRED)` M2→M3 transition (`runtime.py:719-726`) so the audit trail is identical to today.
**Acceptance criteria:**

- Build: `await_decision` resumes from a **store-written** resolution (process A issues + polls, process B writes the resolution to the sub-store) — Tier-2 cross-process test, NOT same-event-loop `set_result`.
- The `asyncio.Future` rendezvous is removed from the cross-process path; any remaining in-process fast-path is a cache over the store (store is authority), never the sole rendezvous.
- Wire: poll reads the real S4s sub-store; the monotonic-version re-check rejects a stale read (regression test: writer bumps version mid-poll, reader observes the new value).
- **`GrantMomentExpiredError` audit row preserved**: a poll-timeout emits the identical M2→M3 timeout Ledger row as the Phase-01 `asyncio.TimeoutError` path (byte-identity regression test against the Phase-01 row; `rules/zero-tolerance.md` Rule 1 — no behavioral regression).
- Poll interval/backoff numeric value decided at `/implement` (`_index.md` open question #4) and recorded in `specs/session-runtime.md`.
  **Capacity check:** Invariants ≤7 (cross-process resume, monotonic-version lost-update defense, timeout-audit-row byte-identity, M2→M3 transition preservation, IPC-as-optimization-not-OR, musl-static compatibility, no-lost-decision). Call-graph hops ≤4 (`await_decision → poll → sub-store → version-check`). ~400 LOC load-bearing (the `:688-745` rewrite is the densest shard). Loop: **live**. **HIGHEST-RISK shard — audit-emitting, load-bearing; serialize alone.**

---

## S4i — `init` / Boundary-Conversation bootstrap (write-once genesis; store-only)

**Type:** Build+Wire.
**Value-anchor:** WS-6 deep-dive R1 correction — "`init` (write-once genesis) is genuinely store-unblockable" (`06-ws6-durable-substrate.md:326`). **S4i is one of the two shards that unblock the last CLI commands** (`_index.md` M2 row): it ships the `init` subcommand, which is store-only and does NOT need the rendezvous change.
**Implements:** `specs/session-state.md` § Session definition (Start: user unlock ceremony / `envoy session start`) + the durable session genesis write; Boundary-Conversation bootstrap per `envoy/boundary_conversation/runtime.py` (S1..S9 transitions emitting `ReasoningCommit` + `session_boundary_crossed`, `session-state.md:209`).
**Depends:** S4s (store only — explicitly NOT S4r).
**Scope:** Wire the `init` CLI subcommand to write its durable session genesis into the S4s store (write-once: the Boundary-Conversation S1..S9 ritual produces the genesis SessionObservedState + trust-anchor emission). Register the `init` group in `envoy/cli/main.py` (currently 7 of 10 groups registered, `main.py:65-71`). Because `init` is write-once and read-later (not a cross-process rendezvous), it ships on the store alone — no dependency on S4r.
**Acceptance criteria:**

- Build: `envoy init` runs the Boundary-Conversation bootstrap end-to-end and writes a durable session genesis a fresh process can read (Tier-3 full-path test per `tests/tier3/test_boundary_conversation_full_path.py` pattern).
- Wire: genesis written to the real S4s store; trust-anchor.json emitted alongside the Shamir ceremony (`specs/independent-verifier.md:120` channel #1).
- `cli/main.py` registers the `init` group; `envoy --help` lists it (user-flow walk per `rules/user-flow-validation.md` — verbatim receipt in the PR).
- Idempotency: re-running `init` on an initialized vault surfaces a typed "already initialized" path, not a silent overwrite.
  **Capacity check:** Invariants ≤5 (write-once genesis, BC ritual ordering, trust-anchor co-emission, store-only independence from S4r, idempotent re-init). Call-graph hops ≤3. ~300 LOC load-bearing. Loop: **live**.

**Status: ✅ COMPLETE** (2026-06-10, `feat/wave2-batch2`).

## Verification (S4i)

- Plan reference re-checked: `specs/session-state.md` § Session definition + `specs/independent-verifier.md` channel #1 + the S4s store surface — all match; genesis convention recorded at `specs/session-runtime.md` § Genesis write (same branch).
- Build ✅ Tier-3 full-path test (`tests/tier3/test_init_bootstrap_full_path.py`): S1..S9 ritual → durable genesis; FRESH SessionRouter instance reads it back (read-back assert). Wire ✅ real sqlite-backed S4s store; wire-gate grep zero hits in `envoy/cli/` + `envoy/boundary_conversation/` non-test code.
- trust-anchor.json ✅ `envoy-trust-anchor/1.0` — public material only (test asserts: 32-byte hex ed25519 pubkey matching `trust_store.genesis_public_key_hex`; no private/secret/passphrase substrings; mode 0o600 with no world-readable window). `envoy/trust/store.py::genesis_public_key_hex` accessor added (read-only, public half only — load-bearing, kept).
- Idempotency ✅ second run → `VaultAlreadyInitializedError` → clean exit 30; genesis bytes unchanged (byte-identity assert); ritual never re-driven.
- CLI ✅ `init` registered in `envoy/cli/main.py` (8th of 10); user-flow walk receipt captured (verbatim `envoy --help` lists init with plain-language one-liner; no-principal path → plain-language error, exit 1, no stack trace). Strict-xfail tripwire flipped → `init` added to `REGISTERED_AS_OF_F5` same branch.
- Journal constraint honored: did NOT touch `envoy/grant_moment/runtime.py` (S4r ownership); store-only independence from S4r preserved.
- Environment discovery: kailash 2.29.3 Signature breaks on Python 3.14.3 (`__annotate_func__` PEP-749 rename vs `__annotate__` lookup) — `.python-version` pinned to 3.13 same branch; upstream filing recommendation pending human gate.

---

## S4g-1 — `grant` interactive answer-in-later-command (core cross-process flow)

**Type:** Build+Wire.
**Value-anchor:** WS-6 deep-dive — the CLI-completing shard (`_index.md` M2 row); `grant` is the canonical "request in one CLI invocation, answer in another" flow the rendezvous redesign (S4r) exists to enable. Plain-terms (deep-dive Q1): "you can't start a permission request in one command and answer it in the next" → S4g-1 makes that work.
**Implements:** `specs/grant-moment.md` full state machine (M0→M4) across two processes; JCS-signed resolution (`grant-moment.md:49-70`).
**Depends:** S4r (consumes the store-poll rendezvous), S4s (transitively).
**Scope:** Ship the `grant` CLI subcommand: a first invocation issues a Grant Moment (M0/M1, writes a pending row to the sub-store); a later, separate invocation lists pending grants and signs a resolution (M3) that the original requester's poll (S4r) picks up. Resolution rows are JCS-signed `GrantMomentResult`; cross-process replay is deduped by nonce.
**Acceptance criteria:**

- Build: `envoy grant list` shows pending grants from the durable queue; `envoy grant approve/deny <id>` writes a resolution the requester's S4r poll resumes on (two-process Tier-2/Tier-3 test).
- Wire: real sub-store, real signing keys; resolution rows are JCS-signed `GrantMomentResult` (`grant-moment.md:49-70`); zero-mock-data grep gate (`_index.md` § Build vs Wire).
- `GrantMomentReplayError` nonce dedup holds across two processes (a replayed resolution is rejected).
- Queue back-pressure: the pending-grant sub-store bounds growth; a full queue surfaces a typed error, not silent drop.
- `cli/main.py` registers the `grant` group; user-flow walk receipt in the PR.
  **Capacity check:** Invariants ≤5 (cross-process M0→M4, pending-queue read surface, JCS-signed resolution, cross-process replay-nonce dedup, queue back-pressure). Call-graph hops ≤4. ~280 LOC load-bearing. Loop: **live**.

---

## S4g-2 — `grant` velocity-raise skew defense + 3-deep delegation-tree persistence

**Type:** Build+Wire.
**Value-anchor:** WS-6 deep-dive — the security-hardening half of `grant`, closing two Phase-01 limitations the spec explicitly defers to Phase-02 (`grant-moment.md:103-105,237-238`).
**Implements:** velocity-raise monotonic-skew defense (`grant-moment.md:103-105` — "Phase 02 persists the last-approved timestamp into the TrustVault alongside a monotonic baseline so forward-skew becomes detectable") + 3-deep delegation-tree persistence (`grant-moment.md:237-238`).
**Depends:** S4g-1 (extends the persisted grant rows).
**Scope:** Persist the last-approved timestamp + a **monotonic baseline** alongside the pending-grant rows so forward clock-skew on the 24h velocity-raise cooling-off becomes detectable. Persist the delegation tree to **3-deep** in the sub-store so the cascade-revoke test lifts from the Phase-01 verify-half to a literal root + 3 descendants.
**Acceptance criteria:**

- Monotonic-skew: a forward wall-clock jump is detected against the persisted monotonic baseline; the 24h velocity-raise gate is no longer shortenable (regression test moving the clock forward — `grant-moment.md:106-109` user-impact closes).
- 3-deep delegation-tree persisted; the cascade-revoke e2e (`tests/e2e/test_grant_moment_3_resolution_shapes_with_cascade.py`) exercises a literal root + 3 descendants, not just the verification half.
- Cooling-off ratchet: a denied high-velocity raise cannot be re-requested below the cooling-off window.
  **Capacity check:** Invariants ≤3 (monotonic-baseline skew defense, 3-deep tree persistence, cooling-off ratchet). Call-graph hops ≤3. ~180 LOC load-bearing. Loop: **live**.

---

## S5b — Session-boundary signal contract + T-013 reset invariant test (SHARED OWNER)

**Type:** Build+Wire.
**Value-anchor:** WS-6 deep-dive Q2 surface #2 + R1 sub-finding ("SessionObservedState reset semantics couple to a session-lifecycle signal the store alone doesn't pin", `06-ws6-durable-substrate.md:326`). **S5b is the shared owner** of the boundary signal that S5o AND S6c both consume — owning it once prevents two shards from independently re-deriving the reset semantics (a divergence failure per `rules/specs-authority.md` 5b).
**Implements:** `specs/session-state.md` § session_boundary_crossed (`session-state.md:67-83`) — the `session_boundary_crossed` Ledger entry emission on all triggers (`unlock | cli_start | cli_end | idle_timeout | user_lock | channel_disconnect`); the **T-013 cache-reset invariant** (`session-state.md:65`) — "`tool_calls_made` and `goal_reconfirmation.tool_calls_since_reconfirm` reset at session end ... per-session fingerprint scope prevents cross-session state injection from amortizing the first-time-action gate." Phase-01 ships only the S8 ritual-suspend trigger (`session-state.md:223`); this shard lands the remaining triggers under the multi-process model (deep-dive spec-gap re `session_boundary_crossed` under-specified for multi-process).
**Depends:** S4s.
**Scope:** Define + implement the `session_boundary_crossed` emission contract so EVERY trigger (not just S8 ritual-suspend) emits the signed Ledger entry, AND the SessionObservedState reset fires on that signal. Author the **T-013 reset invariant test** as the shared contract test: assert that crossing a session boundary clears `tool_calls_made` + `tool_calls_since_reconfirm`, so the first tool call in the new session is first-time-action even if an identical call happened minutes earlier in the prior session. This shard owns the SIGNAL + the invariant test only; S5o consumes the signal to drive the observed-state region, S6c proves a real `chat` boundary fires it.
**Acceptance criteria:**

- Build: all 6 triggers emit a signed `session_boundary_crossed` entry with the correct `trigger` enum + `tool_call_count_observed` / `orphan_phase_a_count` / `unresolved_grants_deferred` fields (`session-state.md:75-82`).
- The T-013 reset invariant test passes: boundary crossing resets the fingerprint cache (behavioral test calling the gate before/after a boundary — `rules/testing.md` § Behavioral Regression).
- Wire: signal written to the real Ledger via the runtime device key (`session-state.md:81` `signed_by: runtime_device_key`); zero mock.
- The reset-invariant test is exported/importable as the SHARED contract S5o and S6c reuse (no re-derivation per shard).
  **Capacity check:** Invariants ≤6 (6-trigger emission completeness, signed-entry field shape, T-013 per-session-scope reset, runtime-device-key signing, shared-contract single-ownership, multi-process trigger semantics). Call-graph hops ≤3. ~300 LOC load-bearing. Loop: **live**.

---

## S5o — SessionObservedState region (fingerprints + first-time-action gate + goal-reconfirm)

**Type:** Build+Wire.
**Value-anchor:** WS-6 deep-dive Q2 surface #2 — the deferred SessionObservedState cache (`session-state.md:218-225`): tool-call fingerprints, first-time-action gate recognition + reset on session boundary, goal-reconfirmation counter, T-013 composition-aware fingerprint clearing — "ALL need somewhere to persist observed-state across the tool-call sequence, which is the store's second region."
**Implements:** `specs/session-state.md` § Algorithm `first_time_action_gate` (`session-state.md:110-137`) + § `pre_authorized_patterns` semantics (`session-state.md:61`) + goal-reconfirmation counter (`session-state.md:42-46`). Lifts `KailashRuntime.first_time_action_gate` from the typed Phase-02 stub on both adapters (`envoy/runtime/adapters/kailash_py.py:526,533`; `kailash_rs_bindings.py:226,233`) to functional.
**Depends:** S5b (consumes the boundary signal for reset).
**Scope:** Implement the durable SessionObservedState region's read/write surface over the S4s store: tool-call fingerprint cache (`sha256(tool_name || canonicalize_args(args))`, `session-state.md:63`), the `first_time_action_gate` algorithm (RECOGNIZED on fingerprint-match or pre-authorized-pattern AST-match; else FIRST_TIME_REQUIRES_GRANT → dispatches `specs/grant-moment.md`), and the goal-reconfirmation counter. Wire the reset to **S5b's boundary signal** (do NOT re-derive the reset trigger — consume the shared S5b contract).
**Acceptance criteria:**

- Build: `first_time_action_gate` returns RECOGNIZED for a repeated fingerprint within a session, FIRST_TIME_REQUIRES_GRANT for a novel one; pre-authorized-pattern AST-match path works (`session-state.md:123-135`).
- Both adapter stubs (`kailash_py.py:526,533` + `kailash_rs_bindings.py:226,233`) stop raising and return real gate results.
- Wire: fingerprints persisted to the real S4s observed-state region; survive a process restart within a session (read-back test).
- Reset consumes S5b's signal: post-boundary, an identical fingerprint is first-time-action again (uses the S5b shared invariant test — no duplicate reset logic).
- Goal-reconfirmation counter increments per tool call and gates at threshold (`GoalReconfirmationThresholdExceededError`, `session-state.md:196`).
  **Capacity check:** Invariants ≤7 (fingerprint canonicalization, gate recognition logic, pre-authorized AST-match, goal-reconfirm threshold gating, reset-on-S5b-signal, cross-restart persistence, dual-adapter parity). Call-graph hops ≤4. ~400 LOC load-bearing. Loop: **base→live** (no live loop until S4s+S5b land; live once they do).

---

## S6a — ClassificationPolicy Tier-2 (`@classify`, clearance, MaskingStrategy, T-005 fail-closed)

**Type:** Build+Wire.
**Value-anchor:** WS-6 deep-dive Q2 surface #3 — "needs a live runtime with the classifier wired, which is the `SessionRouter`"; the full PACT `ClassificationPolicy` surface "deferred to T-01-21 Tier 2 wiring" per `envoy/ledger/facade.py:399`.
**Implements:** `specs/classification-policy.md` § "Out of scope (this phase)" deferrals (`classification-policy.md:106-111`): `@classify` 5-enum canonical-only acceptance (`Public | Internal | Confidential | Restricted | HighlyConfidential`, reject `PII`/`SECRET`); `apply_read_classification` clearance comparison (`classification-policy.md:49-57`); MaskingStrategy round-trip (Redact/LastFour/Hash/NullOut, `classification-policy.md:36-47`); **T-005 semantic classifier-ensemble fail-closed** on disagreement (`classification-policy.md:72-74` — "Minimum 2 classifiers, weighted vote, disagreement fails CLOSED"); classifier-version pinning at replay. Closes the F23 T-005/T-012 full-matrix coverage gate (`classification-policy.md:111`).
**Depends:** S4s (the instantiated runtime/store the classifier methods need; the `classifier_invoke`/`ensemble_aggregate` adapter methods at `kailash_py.py:395,401` fire only once a runtime exists).
**Scope:** Wire a real `ClassificationPolicy` from kailash-dataflow into the ledger emitter (replacing the Phase-01 no-policy passthrough at `ledger/facade.py`), enabling `@classify` canonical-enum enforcement, clearance-gated `apply_read_classification` masking, the T-005 ensemble fail-closed defense, and classifier-version pinning. Per `rules/dataflow-classification.md`: every mutation return-path routes through `apply_read_classification`. Fail-closed default clearance is `Public` (`classification-policy.md:81` + `rules/security.md` § Rust fail-closed defaults).
**Acceptance criteria:**

- Build: `@classify` rejects off-enum labels (`OffEnumClassificationError`, `classification-policy.md:80`); `apply_read_classification` returns plain when clearance ≥ field-classification, else applies MaskingStrategy (Tier-2 test per masking strategy).
- T-005 fail-closed: ensemble disagreement raises `ClassifierEnsembleDisagreementError` and fails closed (`classification-policy.md:83`); a 2-classifier split does NOT pass.
- Wire: real `ClassificationPolicy` wired into `ledger/facade.py` (no-policy passthrough removed); `classifier_invoke`/`ensemble_aggregate` adapter methods (`kailash_py.py:395,401`) stop raising `Phase02SubstrateNotWiredError`.
- Classifier-version pinned in Ledger; retrospective replay raises `ClassifierVersionMismatchError` on version drift (`classification-policy.md:84`).
- F23 gate: T-005/T-012 full-matrix threat tests present (`rules/testing.md` § Audit Mode — grep `test_t005`/`test_t012`).
  **Capacity check:** Invariants ≤8 (canonical-enum-only, clearance comparison, 4 MaskingStrategy round-trips, T-005 ensemble fail-closed, version-pinning, fail-closed-default-Public, mutation-return-path redaction, no-policy-passthrough removal). Call-graph hops ≤4. ~450 LOC load-bearing. Loop: **base→live**.

---

## S6b — Full envelope-intersection (T-01-10) + clearance-level mapping layer

**Type:** Build+Wire.
**Value-anchor:** WS-6 deep-dive Q2 surface #4 — "needs the live runtime's `envelope_intersect`"; the full `kailash.trust.pact.envelopes.intersect_envelopes` wrap is "intentionally NOT shipped in T-01-10" (`envoy/envelope/compiler.py:296-308`) pending a clearance-mapping translation layer that the Grant-Moment consumer surfaces.
**Implements:** `specs/connection-vault.md` § "Envelope-scope membership semantics" (`connection-vault.md:42-51`) — lifts Phase-01 narrow set-membership with deny-veto to **full envelope-intersection** (`intersect_envelopes` rule: "denylists UNION; allowlists INTERSECTION", `connection-vault.md:51`) + the clearance-level mapping layer (kailash-py `public/…/top_secret` ↔ envoy `Public/…/HighlyConfidential`, deep-dive Q2 #4). The adapter's `envelope_intersect` is the substrate-gated method at `kailash_py.py:267`.
**Depends:** S4s.
**Scope:** Wire the full `kailash.trust.pact.envelopes.intersect_envelopes` semantics behind `envoy/envelope/compiler.py:296-308` (replacing the Phase-01 narrow `envelope_contains_scope` set-membership at `envoy/envelope/scope.py`), adding the clearance-level translation layer that maps kailash-py's classification labels to envoy's canonical 5-enum. The 4-condition fail-closed predicate (`connection-vault.md:44-49`: tool_denylist veto + tool_allowlist + channel_denylist veto + channel_allowlist) generalizes to full intersection; explicit deny still dominates implicit allow.
**Acceptance criteria:**

- Build: `envelope_intersect` performs full denylist-UNION / allowlist-INTERSECTION (Tier-2 test against `intersect_envelopes` truth table); explicit deny dominates even on template-import re-allow (`connection-vault.md:51`).
- Clearance mapping: kailash-py `public/…/top_secret` ↔ envoy `Public/…/HighlyConfidential` round-trips losslessly (`EnvelopeScopeMismatchError` on mismatch, `connection-vault.md:72`).
- Wire: `kailash_py.py:267` `envelope_intersect` stops raising `Phase02SubstrateNotWiredError`; real `kailash.trust.pact.envelopes` consumed (no re-implementation per `rules/zero-tolerance.md` Rule 4).
- Fail-closed: a denylisted service/channel is refused even when re-allowed via override (regression test).
  **Capacity check:** Invariants ≤6 (denylist-UNION, allowlist-INTERSECTION, deny-dominance, clearance-label bijection, fail-closed, no-SDK-reimplementation). Call-graph hops ≤4. ~350 LOC load-bearing. Loop: **base→live**.

---

## S6c — `chat` resident receive-loop (LAST) + real-boundary-fires-reset integration test

**Type:** Build+Wire.
**Value-anchor:** WS-6 deep-dive Q1 — "Layer a minimal resident receive-loop for `chat` only on top of the same store later (the store is the source of truth; the resident loop is a cache/transport, not the authority)." This is the **last** WS-6 shard (deep-dive open-question #1 sequencing: store-first, `chat` resident loop later); it completes the 10th-of-10 CLI command and unblocks the deferred `send_message` legs.
**Implements:** `specs/session-state.md` § Session definition (Start: first message in a channel-adapter session; End: channel-adapter disconnect) + the channel `send_message` legs currently deferred (`envoy/channels/web.py:54`, `telegram.py:356`, `discord.py:416` raise `PhaseDeferredError`). The store-vs-resident-loop authority boundary needs `specs/session-runtime.md` § chat-loop contract (deep-dive spec-gap #3 — crash-mid-conversation recovery is defined: store is authority, loop is transport).
**Depends:** S4r (drives the rendezvous), S5b (boundary signal), S5o (observed-state).
**Scope:** Build the minimal `chat` resident receive-loop (daemon-shaped, but the STORE is authoritative — the loop is a transport/cache, so a crash never loses a pending grant): a process that stays alive to receive a channel message, drive the Grant Moment via the S4r store-poll rendezvous, and emit a reply through the now-undeferred `send_message` legs. Author the **integration test that a real `chat` session boundary (channel-disconnect / first-message) fires the S5b reset** — proving the boundary signal is wired end-to-end through the live loop, not just unit-tested in isolation.
**Acceptance criteria:**

- Build: `envoy chat` receives a real channel message, drives a Grant Moment, and emits a reply; `send_message` on web/telegram/discord no longer raises `PhaseDeferredError`.
- Authority: a crash mid-conversation loses NO pending grant (store is authority — kill the loop process mid-grant, restart, the pending grant is still answerable via S4g). Crash-recovery contract pinned in `specs/session-runtime.md`.
- **Integration test: a real `chat` boundary fires the S5b reset** — open a chat session, make a tool call, cross the boundary (disconnect), assert the S5o fingerprint cache cleared (consumes the S5b shared invariant — `rules/user-flow-validation.md` literal walk + verbatim receipt).
- `cli/main.py` registers the `chat` group (10th of 10 commands); user-flow walk receipt in the PR.
  **Capacity check:** Invariants ≤8 (resident-loop-as-transport-not-authority, store-authoritative crash recovery, S4r rendezvous integration, S5b boundary-fires-reset, undeferred send_message legs, channel-disconnect end-trigger, first-message start-trigger, reply emission). Call-graph hops ≤4. ~450 LOC load-bearing. Loop: **live**. **LAST WS-6 shard — depends on S4r+S5b+S5o.**

---

## S7v — Mandatory Rust verifier crate (`cargo install`) — closes EC-9, resolves forest F2→F4

**Type:** Build+Wire.
**Value-anchor:** WS-6 deep-dive Q3 — **"S7v resolves forest F2/F4"** (per this prompt + `06-ws6-durable-substrate.md:158,194-209`). F2 = "Independent ledger verifier (separate repo)" (gates EC-9); F4 = "Full-Phase-01 EC-6 (full-surface, 2 rounds)" (BLOCKED on F2). Standing the verifier up as a shipped installable artifact **closes F2**, which **unblocks F4** (the full-surface EC-6 convergence can include the verifier leg it was missing). The mandatory-Rust elevation makes F2's closure durable (cross-language source-isolation is the non-degradable EC-9 acceptance).
**Implements:** `specs/independent-verifier.md` — elevates Rust from Phase-01 OPTIONAL to **Phase-02 MANDATORY** (`independent-verifier.md:16,274`); the cross-language byte-identity proof `tests/e2e/test_verifier_python_vs_rust_byte_identity.py` ("THIS is the strongest EC-9 source-isolation proof", `independent-verifier.md:241`); the EC-4 5-class mutation battery (`independent-verifier.md:143-159`); JCS-RFC8785 + NFC canonical-JSON independent re-implementation (`independent-verifier.md:162-171`); source-isolation CI checks (`independent-verifier.md:174-196`).
**Depends:** S3b (reuses WS-1's E7 head-commitment-monotonicity byte-identical vectors verbatim — `independent-verifier.md:198-200,262`), S4s (transitively — verifies the durable export bundle).
**Scope:** Build the `envoy-ledger-verifier` Rust crate in the **separate repo** `terrene-foundation/envoy-ledger-verifier` (`independent-verifier.md:17`), installable via `cargo install envoy-ledger-verifier` (`independent-verifier.md:261`), re-implementing canonical-JSON parsing + hash-chain walking + Ed25519 verification independently (NO `envoy.ledger.*` / `envoy_ledger` import — source-isolation is load-bearing per EC-9). Reuse WS-1's E7 conformance vectors verbatim (`tests/fixtures/conformance/e7/`) so the same byte-identity invariant that proves `kailash-py == kailash-rs-bindings` also proves `envoy-producer == envoy-verifier`. **This is the one WS-6 shard that is worktree-isolatable** (separate repo, zero `runtime.py`/store touch) per `rules/worktree-isolation.md` — it MAY run concurrently with any S4*/S5*/S6\* shard.
**Acceptance criteria:**

- Build: the Rust crate verifies a real `envoy ledger export --format json` bundle; all 9 bundle invariants asserted (`independent-verifier.md:78-90`).
- EC-9 byte-identity: Python verifier output == Rust verifier output for the same bundle (`test_verifier_python_vs_rust_byte_identity.py` passes — the strongest source-isolation proof).
- EC-4: 5 mutation classes × 5 entry-index buckets = 25 sub-tests all detect tampering AND identify the failing entry index (`independent-verifier.md:159,239`).
- Source-isolation CI: zero matches for `use envoy_ledger` / path-deps on producer crates (`cargo tree` excludes any `envoy-*` crate, `independent-verifier.md:177`); license-header check passes.
- Wire: E7 vectors pinned from S3b's source (git-submodule-pin vs versioned-fixture-package decided at `/implement` per `independent-verifier.md:275` + `_index.md` — depends on WS-1 vector-format stability).
- **F2 closed** (verifier installable + running EC-4/EC-9 against real bundles); record the F2→F4 unblock in the forest ledger (`workspaces/phase-01-mvp/.session-notes`).
  **Capacity check:** Invariants ≤8 (9 bundle invariants as a cluster, EC-9 byte-identity, EC-4 5-class battery, JCS/NFC independent re-impl, source-isolation zero-import, E7-vector reuse, cross-OS byte-identity, separate-repo isolation). Call-graph hops ≤3. ~500 LOC load-bearing (separate crate; at the shard ceiling — if the mutation battery + canonical-JSON re-impl exceeds budget, split the battery into a sibling shard at `/implement`). Loop: **live**. **ISOLATABLE — separate repo; may run concurrent with S4*/S5*/S6\*.**

---

## Milestone exit gate

WS-6 is complete when: all 10 shards merged serially (S7v may have landed concurrently); `envoy --help` lists all 10 CLI commands (`init`/`chat`/`grant` added, user-flow walk receipts in each PR); the T-013 reset invariant (S5b) holds end-to-end through a real `chat` boundary (S6c); the `GrantMomentExpiredError` audit row is byte-identical pre/post the S4r rendezvous rewrite; and **forest F2 is closed / F4 unblocked** (S7v installable + EC-4/EC-9 green against real bundles). Per `rules/specs-authority.md` Rule 5, `specs/session-runtime.md` lands as each shard lands (code-first, never ahead).
