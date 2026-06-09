# WS-6 — Durable Substrate + Deferred Product Surface (Phase-02 `/analyze` deep-dive)

**Workstream role:** LOAD-BEARING. The persistent-session substrate built here unblocks the last 3
canonical CLI subcommands (`init`, `chat`, `grant`) and a cluster of deferred enforcement surfaces
(SessionObservedState, ClassificationPolicy Tier-2, full envelope-intersection, grant-moment
persistence). Every design claim below is grounded against shipped Phase-01 code with file:line
citations; brief/spec corrections are flagged in their own section.

---

## Q1 — The persistent-session substrate: what it concretely means, and the analogous unblock

### What Phase-01 actually has (grounded)

Phase-01 closed `ledger export` (7th of 10 canonical subcommands) by giving ONE primitive a
process-independent durable backing:

- `envoy/ledger/bootstrap.py:100` `open_durable_ledger(...)` opens the kailash **file-backed
  `SqliteAuditStore`** (upstream `kailash.trust.audit_store.SqliteAuditStore`, confirmed at
  `…/kailash/trust/audit_store.py:668`) over a signing key from
  `envoy/ledger/keystore.py:147` `load_or_create_ledger_key_manager(...)` (OS-keychain-durable
  Ed25519).
- `envoy/daily_digest/bootstrap.py:51,108,116` is the production call site: it opens the durable
  ledger + loads/creates the keychain key. A fresh CLI process re-opens the SAME on-disk SQLite
  chain and re-hydrates from the persisted tail — that cross-process re-openability is exactly why
  `envoy ledger export` became buildable as a one-shot CLI.

The structural lesson: **a subcommand is buildable as a one-shot CLI iff its backing state lives on
disk independent of any running process.** The 6 originally-shipped subcommands
(`version`/`posture`/`connection`/`model`/`shamir`/`digest`) all satisfied this natively (SQLite
posture store, OS keychain, `.env`); `ledger export` was lifted into the set by wiring the durable
store. (CLI registration confirmed: `envoy/cli/main.py:65-71` registers exactly 7 groups —
`shamir`, `digest`, `posture`, `version`, `connection`, `model`, `ledger`.)

### Why `init`/`chat`/`grant` are NOT one-shot-buildable

These three need state that is _inherently long-lived across the conversation_, not a
write-once/read-later artifact:

- **`grant`** — a Grant Moment exists in Phase-01 ONLY as live in-memory runtime state. Pending
  grants live in `EnvoyGrantMomentRuntime._inflight: dict[str, _PendingGrant]`
  (`envoy/grant_moment/runtime.py:403`) plus an event-loop-bound
  `decision_future: asyncio.Future` (`runtime.py:305`). The scope comment is explicit:
  _"narrow scope — per-runtime-instance lifetime, not persisted across restarts. Phase 02 lifts
  this into a TrustVault sub-store."_ (`envoy/grant_moment/runtime.py:393-394`). There is no
  queryable `state="pending"` projection on disk — the only durable writes are ledger rows
  recording intent + terminal decision, never an answerable pending queue.
- **`init`/`chat`** — additionally need the Boundary-Conversation bootstrap + a long-running
  request/response loop. `chat` requires a process that _stays alive_ to receive a message, drive
  the Grant Moment, and emit a reply; `send_message` on the deferred channels is the symptom
  (`envoy/channels/web.py:54` raises `PhaseDeferredError`; `telegram.py:356` / `discord.py:416`
  `send_message` are the deferred legs).
- **All three** need a runtime that is **instantiated outside tests**. The engine that would own a
  live runtime + registered adapters — `envoy.runtime.session.SessionRouter` — **does not exist**.
  `envoy/runtime/` contains `__init__.py`, `errors.py`, `feature_flags.py`, `protocol.py`,
  `selection.py`, `adapters/` — but **no `session.py`**. The only reference is a docstring pointer
  at `envoy/channels/cli.py:12` ("the Engine layer `envoy.runtime.session.SessionRouter`…"). The
  production adapter `envoy/runtime/adapters/kailash_py.py` raises `Phase02SubstrateNotWiredError`
  for every substrate-dependent method (e.g. `:184`, `:286`, `:333`).

### The substrate design — recommendation: **persistent session STORE, not a daemon**

The analogous unblock to "wire `SqliteAuditStore` into the ledger" is **two new durable
projections + a thin session runtime that re-opens them per process** — NOT a long-running daemon.

**Recommendation (with implications, pros/cons):**

| Option                                         | What it is                                                                                                                                                                                                                                                                                                                                                                                                           | Pros                                                                                                                                                                                                                                                                                                                   | Cons                                                                                                                                                                                                                                                    |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A — Persistent session store (RECOMMENDED)** | A `SessionRouter` that opens a durable **pending-grant TrustVault sub-store** (per the `runtime.py:393` comment) + a durable **SessionObservedState region** (per `specs/data-model.md` §"SessionObservedState region") on each invocation, exactly as `daily_digest/bootstrap.py` re-opens the ledger. Each CLI process is still short-lived; continuity comes from the on-disk projection, not a resident process. | Mirrors the proven `ledger export` pattern (re-openable on-disk chain). No new process-supervision surface, no socket/PID/lockfile lifecycle, no daemon security surface. Fits the device-local, keychain-gated trust model. Composes with multi-device (Q4) because the projection IS the rebuild-from-replay target. | `chat` (a genuinely long-running receive loop) needs a resident process eventually; a pure store does not by itself host a live `receive_message` loop.                                                                                                 |
| **B — Resident daemon**                        | A always-on `envoyd` owning the runtime + in-memory `_inflight` + channel receive loops; CLI subcommands become IPC clients.                                                                                                                                                                                                                                                                                         | Natural home for `chat`'s receive loop + push channels.                                                                                                                                                                                                                                                                | Large new surface: process supervision, IPC auth, crash-recovery, socket/PID hygiene, a second trust boundary the threat model never reviewed. Re-introduces the "state lost on exit" failure for anything kept in daemon memory unless ALSO persisted. |

**Recommended path:** build **Option A first** (store-backed `SessionRouter` + pending-grant
sub-store + SessionObservedState region) — this alone unblocks `grant` (durable pending queue a
fresh `grant` process can read) and `init` (BC bootstrap writes its durable session genesis). Layer
a **minimal resident receive-loop for `chat` only** on top of the same store later (the store is the
source of truth; the resident loop is a cache/transport, not the authority). This keeps the durable
authority in the store (so a crash never loses a pending grant) while giving `chat` its live loop —
and it means `grant`/`init` ship without waiting on daemon infrastructure.

**In plain terms for the user:** today the assistant "forgets" any in-progress permission request
the moment the command finishes — so you can't start a permission request in one command and answer
it in the next. Phase-02 writes those in-progress requests to an encrypted on-disk drawer (the same
kind of drawer the audit log already uses), so a brand-new command can open the drawer, see the
pending request, and let you answer it. That single drawer is what makes `init`, `chat`, and `grant`
all work.

---

## Q2 — The unblocked cluster: how four deferred surfaces hang off the same substrate

All four deferrals share the root cause "no durable cross-process session/grant region." Mapping the
dependency (each grounded against the spec's own "Out of scope (this phase)" note + the shipped
stub):

```
            ┌──────────────────────────────────────────────┐
            │  Persistent session STORE (Q1 Option A)       │
            │  • pending-grant TrustVault sub-store          │
            │  • SessionObservedState durable region         │
            │  • SessionRouter re-opens both per process     │
            └───────┬───────────┬───────────┬───────────┬───┘
                    │           │           │           │
       ┌────────────▼──┐  ┌─────▼──────┐ ┌──▼─────────┐ ┌▼──────────────┐
       │ grant-moment  │  │ Session-   │ │ Classifi-  │ │ full envelope-│
       │ persistence   │  │ ObservedSt.│ │ cationPol. │ │ intersection  │
       │ (T-03-50)     │  │ Tier-2     │ │ Tier-2     │ │ (T-01-10)     │
       └───────────────┘  └────────────┘ └────────────┘ └───────────────┘
```

1. **Grant-moment persistence** — directly consumes the pending-grant sub-store. Phase-01 keeps
   pending grants in `_inflight` + `asyncio.Future` (`runtime.py:403,305`); Phase-02 lifts them into
   the TrustVault sub-store (`runtime.py:393-394`). Two sub-deferrals ride along:
   - **Monotonic-baseline clock-skew detection** (`specs/grant-moment.md:103-105`): Phase-01
     cooling-off uses `time.time()` wall-clock; forward skew shortens the 24h gate. Phase-02
     persists the last-approved timestamp **into the TrustVault alongside a monotonic baseline** —
     i.e. it needs the durable sub-store to exist. The store unblocks the skew defense.
   - **3-deep delegation-tree persistence** (`specs/grant-moment.md:237-238`): Phase-01 ships only
     the runtime's verify-half of cascade revocation (`envoy/grant_moment/cascade_orchestrator.py:105,135`
     — the BFS itself lives upstream in `kailash.trust.cascade_revoke`); the literal 3-deep tree test
     lands "once Trust Vault container persistence lands." Same dependency.

2. **SessionObservedState Tier-2** — needs the durable SessionObservedState region. Phase-01:
   `KailashRuntime.first_time_action_gate` is a typed stub on BOTH adapters
   (`envoy/runtime/adapters/kailash_py.py:526,533` "requires Wave-2 session state + Grant";
   `kailash_rs_bindings.py:226,233`); `SessionObservedState` is referenced only as future scope at
   `envoy/model/errors.py:100`. The deferred surfaces (`specs/session-state.md:218-225`) — tool-call
   fingerprints, first-time-action gate recognition + reset on session boundary,
   goal-reconfirmation counter, T-013 composition-aware fingerprint clearing — ALL need somewhere to
   persist observed-state across the tool-call sequence, which is the store's second region.

3. **ClassificationPolicy Tier-2** — needs a live runtime with the classifier wired, which is the
   `SessionRouter`. Phase-01 ships the `format_record_id_for_event` PK-hashing primitive +
   no-policy passthrough at the ledger emitter; the full PACT `ClassificationPolicy` surface is
   "deferred to T-01-21 Tier 2 wiring" per `envoy/ledger/facade.py:399`
   (`specs/classification-policy.md:106-111`). Deferred: `@classify` 5-enum acceptance,
   `apply_read_classification` clearance comparison, MaskingStrategy round-trip
   (Redact/LastFour/Hash/NullOut), **T-005 ensemble fail-closed** on classifier disagreement,
   classifier-version pinning at replay. The `classifier_invoke` / `ensemble_aggregate` adapter
   methods already raise `Phase02SubstrateNotWiredError` (`kailash_py.py:395,401`) — they fire only
   once a runtime is instantiated, which is the substrate.

4. **Full envelope-intersection (T-01-10)** — needs the live runtime's `envelope_intersect`. Phase-01
   ships narrow set-membership with deny-veto (`envoy/envelope/scope.py::envelope_contains_scope`,
   `specs/connection-vault.md:51`); the full `kailash.trust.pact.envelopes.intersect_envelopes`
   wrap is "intentionally NOT shipped in T-01-10" (`envoy/envelope/compiler.py:296-308`) pending a
   clearance-mapping translation layer (kailash-py `public/…/top_secret` ↔ envoy
   `Public/…/HighlyConfidential`) that the Grant-Moment consumer (T-03-50) surfaces. The adapter's
   `envelope_intersect` is a substrate-gated method (`kailash_py.py:267`).

**The dependency in one sentence:** grant-moment persistence consumes the pending-grant sub-store
directly; SessionObservedState consumes the observed-state region directly; ClassificationPolicy and
envelope-intersection consume the _instantiated `SessionRouter`_ (their adapter methods are inert
until a runtime exists outside tests). Build the store + router once → all four become wireable.

---

## Q3 — Mandatory Rust verifier (`cargo install envoy-ledger-verifier`); resolves forest F2/F4

### Phase-01 disposition (grounded)

- Phase-01 ships the **Python verifier REQUIRED, Rust OPTIONAL** (`specs/independent-verifier.md:16`,
  open-question 3 at `:274`). The verifier is a **separately-codebased CLI** authored without
  reference to producer source — it is the structural defense for **EC-4** (mutation-detection
  battery) and **EC-9** (separately-codebased verifier), both NON-DEGRADABLE / release-blocking
  (`specs/independent-verifier.md:5,15`).
- Distribution: Python via `pip install envoy-ledger-verify`; **Phase-02 Rust crate via
  `cargo install envoy-ledger-verifier`** (`specs/independent-verifier.md:261`).

### Phase-02 makes Rust MANDATORY — the cross-language source-isolation proof (EC-9)

EC-9's strongest form is **byte-identity across two independently-authored codebases in two
languages**. `specs/independent-verifier.md:241` names the gate:
`tests/e2e/test_verifier_python_vs_rust_byte_identity.py` — "Python verifier and Rust verifier
produce byte-identical output. THIS is the strongest EC-9 source-isolation proof." A single-language
(Python-only) verifier can still share latent assumptions with the Python producer; a Rust verifier
that re-implements the JCS-RFC8785 + NFC canonical-JSON contract
(`specs/independent-verifier.md:258`) and reaches the same bytes proves the invariant lives in the
_spec_, not in shared Python idiom. That is why Phase-02 elevates Rust from OPTIONAL to MANDATORY.

### Conformance-vector reuse (WS-1)

The verifier reuses WS-1's cross-runtime conformance vectors **verbatim**
(`specs/independent-verifier.md:198-200,262`): the **E7 row** (Ledger head-commitment monotonicity,
≥10 byte-identical vectors) from
`workspaces/phase-00-alignment/02-plans/conformance/01-runtime-swap-contract.md §4.2`. The same
vectors that prove `kailash-py == kailash-rs-bindings` (the WS-1 BET-6 cross-runtime gate) ALSO prove
`envoy-producer == envoy-verifier` — "the same byte-identity invariant tested through two different
lenses." So the Rust verifier does not invent a fixture corpus; it pins WS-1's E7 vectors
(`tests/fixtures/conformance/e7/`), and WS-1's Phase-02 cross-runtime work and WS-6's verifier work
share one vector source.

### How this resolves Phase-01 forest F2/F4

From `workspaces/phase-01-mvp/.session-notes` (forest ledger):

- **F2** = "Independent ledger verifier (separate repo)" — gates EC-9, status "SEPARATE repo (out of
  in-repo scope); gates full EC-6".
- **F4** = "Full-Phase-01 EC-6 (full-surface, 2 rounds)" — status "BLOCKED on F2; in-repo half
  re-converged (PR #84)".

F4 (the 2-consecutive-clean-rounds release gate, EC-6) cannot fully close while F2 (the verifier)
lives in a separate repo that Phase-01 declared out-of-in-repo-scope. Phase-02 standing the verifier
up as a shipped, installable artifact (`cargo install envoy-ledger-verifier` + the Python
`envoy-ledger-verify`) **closes F2** — the verifier exists, is installable, and runs the EC-4
mutation battery + EC-9 byte-identity proof against real export bundles. With F2 closed, **F4
unblocks**: the full-surface EC-6 convergence can include the verifier leg it was missing. The
mandatory-Rust elevation is what makes F2's closure _durable_ (the cross-language proof is the
non-degradable EC-9 acceptance), not merely a Python re-run of producer logic.

---

## Q4 — Multi-device substrate: ledger materialized-index rebuild-from-replay

**Spec anchor:** `specs/data-model.md:99` lists "Ledger materialized-index rebuild-from-replay" under
**"Out of scope (this phase) — Phase 02 (multi-device substrate)"**, alongside ":101" "256 KiB
chunked constant-write-rate sync — Phase 02 (`specs/ledger-merge.md` multi-device sync)" and ":53-56"
(Trust Vault + Ledger opt-in sync; Connection Vault / Shadow segment NEVER sync). Grounding check:
**no `rebuild_from_replay` / `materialized_index` symbol exists anywhere in `envoy/`** (grep empty) —
confirming this is genuinely unbuilt Phase-02 scope, not a phantom citation.

**How it relates to the persistent substrate (Q1):** the rebuild-from-replay is the same store
viewed across devices. A materialized index is a _projection_ of the append-only ledger chain — the
fast-lookup view (e.g. "give me pending grants" / "give me the latest SessionObservedState") that the
`SessionRouter` reads instead of replaying the whole chain. On a single device the index is built
once and kept warm. On **multiple devices**, each device receives the other's appended chain segments
via the 256 KiB chunked sync (`specs/data-model.md:54`, dual head-commitments) and **must rebuild its
local materialized index by replaying the merged chain** — because the index is a derived view, not a
synced artifact (you sync the authoritative append-only chain, then each device re-derives its own
index deterministically). This is exactly the property that makes Q1's store design correct: because
the durable session state is a _projection of an append-only chain_, it is reconstructable from
replay, which is what multi-device merge requires. A daemon holding authoritative state in memory
(Q1 Option B) would have nothing to replay from; the store-as-projection (Option A) is replay-native.

The dependency direction: **Q1's store is the single-device case; Q4's rebuild-from-replay is the
multi-device generalization of the same projection.** Build the projection-from-chain discipline in
Q1 (single device) and the multi-device rebuild is the same code path fed a merged chain. This also
explains why the verifier (Q3) matters for multi-device: the verifier's mutation battery + head-
commitment monotonicity (E7 vectors) is what lets a device trust a _merged_ chain from another device
before rebuilding its index from it.

---

## Spec gaps identified (ADDITIONS ONLY — no spec edits performed)

1. **`SessionRouter` has no spec-of-record.** It is named in `specs/mvp-build-sequence.md:209`
   (Phase-02 hooks #9) and `envoy/channels/cli.py:12` (docstring) but no spec describes its
   contract (which regions it opens, its re-open lifecycle, its relationship to the runtime
   adapters). Phase-02 should add a `specs/session-runtime.md` describing the store-backed router
   BEFORE `/implement` (per `specs-authority.md` — code-first then spec describes what shipped; so
   the spec lands as each shard lands, not ahead).
2. **Pending-grant sub-store schema is unspecified.** `specs/grant-moment.md:104` + `runtime.py:393`
   name "a TrustVault sub-store" but no schema (key shape, `state` enum, TTL, index columns). Needs
   pinning so the `grant`-history read surface and the rebuild-from-replay index agree on shape.
3. **`chat` long-running-loop contract is unspecified.** The store-vs-resident-loop boundary (Q1)
   has no spec. Which part of `chat` is authoritative (store) vs transport (resident receive loop)
   needs a written contract so a crash mid-conversation has defined recovery.
4. **Multi-device index-rebuild determinism is unspecified.** `specs/data-model.md:99` names the
   feature but `specs/ledger-merge.md` (cited, Phase-03 per `independent-verifier.md:257`) owns the
   merge protocol — the _index_-rebuild determinism contract (same merged chain → byte-identical
   index on every device) is not pinned. This is verifier-adjacent (it's a byte-identity claim) and
   should reuse the E7-vector discipline.

## Brief / spec corrections (phantom-citation findings per `spec-accuracy.md`)

1. **CORRECTION — `runtime.py:392-401` line citation is off by ~10 lines.** Both
   `specs/mvp-build-sequence.md:209` and `journal/0048:60-65` cite the
   "not persisted across restarts / Phase 02 lifts this into a TrustVault sub-store" comment at
   `runtime.py:392-401` and `_inflight` at `:402-403`. Actual shipped lines: the comment is at
   **`runtime.py:393-394`** and `_inflight` is at **`runtime.py:403`** (`decision_future` at `:305`).
   The symbols are REAL (not phantom) — only the line anchors drifted. Flag: low-severity citation
   drift, fix the line refs when these are next edited; the claim itself grounds.
2. **CONFIRMED (not a phantom) — `Phase02SubstrateNotWiredError` exists.** Wave-1 flagged a phantom
   `RuntimeBackendNotWired` (named in `specs/mvp-build-sequence.md:202` for the WS-1 runtime adapter).
   For WS-6, the analogous symbol the journal/spec cite IS real:
   `envoy/runtime/errors.py:91` defines `Phase02SubstrateNotWiredError`, raised throughout
   `kailash_py.py` (e.g. `:184,286,333`) and `kailash_rs_bindings.py`. The journal/0048:77 claim
   "production runtime adapter raises `Phase02SubstrateNotWiredError` for grant substrate" grounds.
   (Separately confirming Wave-1's finding: a grep for `RuntimeBackendNotWired` across `envoy/`
   returns EMPTY — it is indeed a phantom in `mvp-build-sequence.md:202`; flagged here for WS-1's
   benefit, not WS-6's.)
3. **CONFIRMED — `SessionRouter` / `envoy/runtime/session.py` does not exist.** `journal/0048:73-74`
   claim grounds: `envoy/runtime/` has no `session.py` (only `__init__/errors/feature_flags/
protocol/selection` + `adapters/`); sole reference is the `channels/cli.py:12` docstring.
4. **CONFIRMED — 7 (not 6) CLI groups registered.** `journal/0048:48` says "6 of 10" because it was
   written BEFORE `ledger` landed (its `main.py:63-68` citation predates the `ledger` row). Current
   `envoy/cli/main.py:65-71` registers **7** groups — consistent with the spec's "7 of 10"
   (`mvp-build-sequence.md:190`). No correction to the live spec needed; flagging that journal/0048's
   "6/10" is a point-in-time snapshot superseded by journal/0049 (7/10).
5. **NOTE (out-of-WS-6-scope, flagged for WS-4) — channel surfaces.** Wave-1's "Phase-01 shipped 5 of
   8 channel surfaces not 8": only **4 channel modules exist** (`envoy/channels/{slack,telegram,
discord,web}.py`); `sms`/`whatsapp`/`signal`/`imessage` modules are ABSENT. Of the 4, `slack`+`cli`
   ship without `PhaseDeferredError`; `telegram`/`discord`/`web` defer their `send_message` leg
   (`web.py:54`, `telegram.py:356`, `discord.py:416`). The substrate-relevant fact: the deferred
   `send_message` legs are downstream of the missing long-running session model — they unblock with
   WS-6's substrate. Exact channel-count reconciliation is WS-4's; flagged not owned here.

## Open questions for `/todos`

1. **Store-first vs daemon-eventually sequencing.** Recommend Q1 Option A (store) ships first
   (unblocks `grant`+`init`), with the `chat` resident receive-loop as a later shard on the same
   store. Confirm this sharding at `/todos` — or does the user want `chat` parity with `grant`/`init`
   in the same wave (forces the resident-loop surface earlier)?
2. **Pending-grant sub-store: new TrustVault region vs reuse ledger chain.** The grant pending-queue
   could be (a) a new TrustVault sub-store (per the `runtime.py:393` comment) or (b) a materialized
   index over existing ledger intent/decision rows. Option (b) reuses the rebuild-from-replay
   machinery (Q4) directly. Recommend (b) — it makes pending-grant persistence and multi-device index
   ONE mechanism. Needs a `/todos` decision because it changes the sub-store schema gap (#2 above).
3. **Capacity sharding.** This workstream spans ≥4 invariant clusters (durable-store atomicity +
   keychain key lifecycle + pending-grant TTL/skew + SessionObservedState fingerprint clearing +
   envelope clearance-mapping). Per `autonomous-execution.md` Per-Session Capacity Budget this MUST
   shard at `/todos`: candidate shards — (S1) store + `SessionRouter` re-open; (S2) pending-grant
   sub-store + `grant` CLI; (S3) SessionObservedState region + first-time-action gate; (S4)
   ClassificationPolicy Tier-2 wiring; (S5) envelope-intersection + clearance mapping; (S6)
   `init`/BC bootstrap; (S7) `chat` resident loop; (S8) Rust verifier crate + EC-9 byte-identity;
   (S9) multi-device index rebuild-from-replay. S8 is parallelizable with S1-S7 (separate repo).
4. **Rust verifier repo bootstrap timing.** Reuses WS-1's E7 vectors — does the verifier crate
   bootstrap in parallel with WS-1's Phase-02 cross-runtime work (shared vector source) or wait for
   WS-1 to stabilize the vector format? (`independent-verifier.md` open-question 4 at `:275` defers
   E7 versioning — git-submodule-pin vs versioned-fixture-package — to Phase-02 entry.)

---

## Round-1 red-team correction (R1-HIGH-1) — applied 2026-06-08

**The STORE alone does NOT unblock `grant` (or `chat`) — the cross-process rendezvous needs a mechanism change.** The "store-first unblocks grant+init" claim is half-true. The Grant Moment decision rendezvous is an in-process `asyncio.Future` (`envoy/grant_moment/runtime.py:305,710,743`): `await_decision` blocks a coroutine; `submit_resolution` calls `set_result` from another task in the SAME event loop. A future cannot be `set_result`-ed across two OS processes, so the `grant` flow (request in one CLI invocation, answer in another) is exactly the cross-process rendezvous the store does not provide. Disposition: `init` (write-once genesis) is genuinely store-unblockable; **`grant`/`chat` need a rendezvous-mechanism change** — replace `asyncio.Future` with a store-polled or IPC-signalled wakeup (a load-bearing redesign of `runtime.py:688-745`). Reflected in the shard map as S4r (rendezvous) split from S4s (store) / S4i (init) / S4g (grant). Sub-finding: SessionObservedState reset semantics couple to a session-lifecycle signal the store alone doesn't pin (folded into S5o). See `journal/0002` R1-HIGH-1.
