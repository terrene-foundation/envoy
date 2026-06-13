# session-runtime

## Purpose

Spec-of-record for the store-backed **`SessionRouter`** — the persistent-session
substrate (`envoy/runtime/session.py`) that re-opens two durable projections per
process invocation. This is the durability layer that makes the long-lived
session commands (`init`, `grant`, `chat`) buildable: state that must survive
between two separate CLI invocations lives on disk, re-openable by any fresh
process, rather than in process memory.

Code-first per `rules/specs-authority.md` Rule 5 + `rules/spec-accuracy.md`
Rule 5: this spec describes ONLY what is shipped on the branch. The router opens
the empty-but-durable store + the raw region read/write surface, AND (S4r) the
cross-process decision rendezvous — the store-poll-with-monotonic-version-re-check
that replaces the in-process `asyncio.Future`. It does NOT yet contain the
`grant` read surface, the `init` genesis write, or the SessionObservedState gate
semantics — those land in their own shards (S4g / S4i / S5o) and extend this
spec as they ship.

## Provenance

- **Source analysis:** `workspaces/phase-02-distribution/01-analysis/01-research/06-ws6-durable-substrate.md`
  Q1 Option A (RECOMMENDED) + its spec-gap #1 ("`SessionRouter` has no
  spec-of-record") + spec-gap #2 ("pending-grant sub-store schema is
  unspecified").
- **Implements:** `specs/session-state.md` § Persistence (SessionObservedState
  snapshot at every Ledger append) + `specs/grant-moment.md:104` /
  `envoy/grant_moment/runtime.py:393-394` ("Phase 02 lifts this into a
  TrustVault sub-store").
- **Pattern precedent:** `envoy/ledger/bootstrap.py:100` (`open_durable_ledger`),
  `envoy/daily_digest/bootstrap.py:108,116` (re-open per process),
  `envoy/trust/store.py` (`TrustStoreAdapter` sibling-DB layout),
  `envoy/ledger/keystore.py:147` (`load_or_create_ledger_key_manager`,
  OS-keychain Ed25519).

## SessionRouter

`envoy.runtime.session.SessionRouter` is a short-lived (NOT daemon) session
substrate. Construction takes no I/O; `await router.open()` re-opens the durable
store and re-loads the OS-keychain signing key; `await router.close()` zeroizes
the in-memory key material. A fresh process constructing a new `SessionRouter`
over the same `vault_path` re-opens the SAME on-disk projections and the SAME
keychain key — the cross-process re-openability `ledger export` already proves.

Constructor (explicit dependencies per `rules/facade-manager-detection.md`
Rule 3):

```python
SessionRouter(
    *,
    vault_path: Path | str,
    principal_id: str,           # keys the keychain signing key
    keyring_backend: Any = None, # dependency-injectable for tests; None = OS keychain
)
```

### Store layout

The session store is a vault **sibling** SQLite file resolved by
`session_db_path(vault_path)` → `<stem>.session.db`, matching the
`.chain.db` / `.posture.db` / `.bc.db` / `.digest.db` / `.audit.db` layout the
Trust store + durable ledger already establish. Every writer and reader
resolves the path through `session_db_path` so they open the SAME file. The db
family is `0o600` per `rules/trust-plane-security.md` MUST Rule 6; WAL mode;
fresh connection per operation under `asyncio.to_thread` (the public surface is
async per `rules/patterns.md` § Paired Public Surface); parameterized queries
throughout (MUST Rule 5); every identifier reaching a primary key is validated
against path-traversal / null-byte / control-char shapes (MUST Rule 2).

### Keychain key lifecycle

`open()` re-loads an OS-keychain Ed25519 key via
`load_or_create_ledger_key_manager(principal_id=..., signing_key_id=
SESSION_SIGNING_KEY_ID)` BEFORE touching the store (fail-loud: a keychain-down
or corrupt-record condition raises the keystore's typed error, never a silent
ephemeral key). `SESSION_SIGNING_KEY_ID` (`"envoy-session-signing-key"`) is a
FIXED constant namespaced DISTINCTLY from the ledger signing key so the two
never collide in the keychain. The key is the trust anchor the resolution
signatures (S4r) and snapshot signatures (S5o) will use; S4s opens it and proves
it survives restart.

## Sub-store schema decision (deep-dive spec-gap #2 / open-question #2)

The WS-6 deep-dive flagged a decision between **(a)** a new TrustVault sub-store
versus **(b)** a materialized index over the existing ledger intent/decision
rows. **Decision: (a) — a dedicated keychain-gated sub-store.**

Rationale: option (a) is the cleaner store-only delivery and mirrors the proven
`TrustStoreAdapter` sibling-DB + `open_durable_ledger` re-open pattern exactly
(a fresh process opens the same sibling file). Option (b)'s reuse of the
rebuild-from-replay machinery (deep-dive Q4) is a Phase-02 multi-device concern
that depends on the ledger-merge protocol (`specs/data-model.md:99`, Phase-03
per `independent-verifier.md:257`) not yet shipped; coupling the single-device
pending queue to that unshipped machinery would block S4s on a downstream
dependency. The sub-store's rows ARE derived views over the append-only chain
(replay-native), so the option-(b) rebuild remains a future generalization, not
a foreclosed path.

### Region 1 — pending-grant sub-store (`pending_grant` table)

The durable form of `runtime.py:403`'s in-memory `_inflight` queue.

| Column            | Type    | Notes                                                                                                                                                                  |
| ----------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `request_id`      | TEXT PK | key shape — the `GrantMomentRequest.request_id` (uuid-v7)                                                                                                              |
| `principal_id`    | TEXT    | owning principal                                                                                                                                                       |
| `session_id`      | TEXT    | issuing session                                                                                                                                                        |
| `state`           | TEXT    | enum `pending` / `resolved` / `expired`, enforced by a SQLite CHECK                                                                                                    |
| `request_json`    | TEXT    | canonical-JSON `GrantMomentRequest`, stored verbatim (S4s does not parse it)                                                                                           |
| `resolution_json` | TEXT    | nullable; the resolution row S4r writes; NULL while pending                                                                                                            |
| `resolution_sig`  | TEXT    | nullable; hex Ed25519 signature over `resolution_signing_payload(request_id, resolution_json)`, keychain-signed by S4r (§ Resolution authenticity); NULL while pending |
| `version`         | INTEGER | monotonic; bumped on every re-put — the lost-update primitive S4r polls                                                                                                |
| `ttl_expires_at`  | TEXT    | ISO-8601 TTL bounding queue growth (S4g back-pressure)                                                                                                                 |
| `created_at`      | TEXT    | ISO-8601; preserved across re-puts                                                                                                                                     |
| `updated_at`      | TEXT    | ISO-8601                                                                                                                                                               |

Index columns: `(principal_id, state, updated_at)` for the
"pending rows for this principal, newest first" lookup the `grant list` read
surface (S4g) and the S4r poll need.

`state` enum constant: `PENDING_GRANT_STATES = {"pending", "resolved",
"expired"}`. `pending` is the live queue entry; `resolved` carries the answer
S4r's poll resumes on; `expired` is the timeout terminal driven by S4r's M2→M3
transition.

Raw store surface shipped in S4s:

- `put_pending_grant(*, request_id, session_id, request_json, ttl_expires_at)` —
  enqueue (state=pending, version=1); re-put bumps `version`, keeps `created_at`.
- `get_pending_grant(request_id) -> PendingGrantRow | None` — cross-process
  read-back (returns `version` + `resolution_json` for the S4r poll re-check);
  None if absent.
- `count_pending_grants() -> int` — count of `state=pending` rows for the
  principal (the primitive S4g's back-pressure ceiling reads).

Resolution-write surface shipped in S4r:

- `resolve_pending_grant(*, request_id, resolution_json, state="resolved") -> int` —
  the cross-process WRITE half. Flips a `pending` row to `resolved` (or
  `expired`), persists `resolution_json`, bumps `version`, and returns the new
  version. The UPDATE is gated on `state='pending'` as a cross-process
  compare-and-set: a double-resolve or an absent row raises `KeyError` (lost-update
  / double-resolve guard) rather than silently no-op'ing. `resolution_json` MUST
  be a parseable JSON object (fail-loud). `PendingGrantRow` carries
  `resolution_json` so the poller reconstructs the answer.

`request_json` MUST be a parseable JSON object — a malformed blob raises at the
write boundary (fail-loud per `rules/zero-tolerance.md` Rule 2). S4s does NOT
interpret the wire format's fields; the semantic surface (nonce dedup, the
cross-process poll rendezvous, sign-resolution) is S4r / S4g.

### Region 2 — SessionObservedState (`session_observed_state` table)

The durable snapshot home for `specs/session-state.md` § Persistence
("snapshot to a 0o600 vault-sibling SQLite store at every Ledger append, so a
crash mid-session preserves orphan-phase-A tracking", `session-state.md` § Persistence).
The `state_json` blob is stored as canonical JSON; the `pending_grant`
resolution rows the same store holds carry a keychain-signed `resolution_sig`
(§ Resolution authenticity), so this store is signed-not-encrypted-at-rest.

| Column         | Type    | Notes                                                       |
| -------------- | ------- | ----------------------------------------------------------- |
| `session_id`   | TEXT PK | key shape — the `SessionObservedState.session_id` (uuid-v7) |
| `principal_id` | TEXT    | owning principal                                            |
| `state_json`   | TEXT    | canonical-JSON `SessionObservedState`, stored verbatim      |
| `version`      | INTEGER | monotonic; bumped on every snapshot                         |
| `updated_at`   | TEXT    | ISO-8601                                                    |

Raw store surface shipped in S4s:

- `snapshot_observed_state(*, session_id, state_json)` — upsert the blob; re-snapshot
  bumps `version`. `state_json` MUST be a parseable JSON object (fail-loud).
- `load_observed_state(session_id) -> str | None` — cross-process re-hydration
  read-back; None if no snapshot exists.

S4s stores + returns the `state_json` verbatim. The fingerprint /
first-time-action gate / goal-reconfirmation semantics that DERIVE the blob are
owned by S5o (`specs/session-state.md` § Algorithm), which consumes this region.

### Genesis write (`envoy init` — S4i)

The install-time genesis ceremony (`envoy init run`,
`envoy/boundary_conversation/init_runtime.py::BoundaryConversationInitRuntime`)
writes a write-once genesis `SessionObservedState` into this region:

- **Key convention:** the genesis row is keyed `genesis:<principal_id>` in
  `session_observed_state.session_id` — deterministic, principal-scoped, no
  cross-principal bleed. Downstream shards (S4r/S4g/S5o) read the genesis row
  through the same `load_observed_state("genesis:<principal_id>")` call.
- **Write-once contract:** a keyed read BEFORE driving the ritual detects an
  initialized vault; present → `VaultAlreadyInitializedError`
  (`envoy/boundary_conversation/errors.py`), mapped by the CLI to a clean
  exit code 30 with a plain-language message. The genesis row is never
  overwritten; re-running `init` never re-drives the ritual.
- **Genesis blob:** `session-state/1.0` `SessionObservedState` with
  `envelope_version_at_session_start: 1` and
  `posture_at_session_start: "PSEUDO"`.
- **Trust-anchor co-emission:** the ceremony emits `trust-anchor.json`
  (`envoy-trust-anchor/1.0`: `principal_genesis_id`,
  `principal_genesis_pubkey_hex` via
  `envoy/trust/store.py::genesis_public_key_hex`, empty
  `device_attestation_chain`, `anchor_minted_at`) per
  `specs/independent-verifier.md` § Trust-anchor resolution channel #1 —
  public material only, file mode owner-only (0o600).

## Cross-process decision rendezvous (S4r)

The `grant` flow issues a Grant Moment in one CLI invocation and answers it in
another, separate OS process. An in-process `decision_future: asyncio.Future`
cannot be `set_result`-ed across that boundary; S4r replaces it with a
**store-poll-with-monotonic-version-re-check as the PRIMARY mechanism**, wired
through `envoy/grant_moment/runtime.py::EnvoyGrantMomentRuntime`.

When a `SessionRouter` is injected (`session_router=` constructor kwarg), the
durable pending-grant sub-store is the rendezvous AUTHORITY:

1. **Issue (M0/M1)** — the runtime writes the signed `GrantMomentRequest` to the
   sub-store via `put_pending_grant` and records the `version` observed at issue
   (`store_version_at_issue`).
2. **Answer (cross-process)** — a SEPARATE process writes the resolution via
   `resolve_pending_grant(request_id, resolution_json, state="resolved")`, which
   flips `pending → resolved` and bumps `version`. The resolution wire form is
   produced by the `resolution_to_json` / `resolution_from_json` codec
   (`envoy/grant_moment/resolution.py`), which preserves the concrete
   `ResolutionShape` subclass across the boundary.
3. **Resume (M2 poll)** — `await_decision` polls `get_pending_grant`, treating
   `state in {resolved, expired} AND version > store_version_at_issue` as the
   resolution signal. The version-re-check is the lost-update guard: comparing
   against the issue-time version (not the prior poll's) means a writer that
   resolves between issue and the first poll is still observed. Each poll opens
   a fresh SQLite connection (WAL), so a concurrent committed write is visible
   on the next tick — no stale snapshot.

**Resolution authenticity (fail-closed).** A resolution row crosses an OS-process
boundary, so before `await_decision` treats it as the user's decision the row's
detached signature MUST verify. `resolve_pending_grant` signs the resolution at
the write boundary: the answering process signs `resolution_signing_payload(
request_id, resolution_json)` — a sorted-key JSON envelope binding the
`request_id` to the canonical resolution — with the session signing key
(`SESSION_SIGNING_KEY_ID`), persisting the hex signature in the `resolution_sig`
column alongside `resolution_json` in the same atomic UPDATE. On read,
`_poll_store_for_resolution` calls `SessionRouter.verify_resolution_signature`
and raises `GrantMomentResolutionUnauthenticatedError` (fail-closed) on a
missing, malformed, invalid, or tampered signature, or one whose `request_id`
binding does not match — so a resolution written by direct sqlite tampering or
by a process lacking the session key is REFUSED, never executed. The `request_id`
binding defeats replay of a captured signature onto a different pending row. The
same-process fast-path (a `post_decision` that sets the in-process future) needs
no verification: it was produced in-process by the adapter and is trusted by
construction. The signature authenticates that the resolution came from a holder
of the session signing key; distinguishing a distinct _answerer principal_ by a
separate co-signing key is out of this spec's scope (the cross-principal
dual-signature surface is owned by `specs/grant-moment.md`).

The in-process `asyncio.Future` survives ONLY as a same-process fast-path cache
OVER the store (a same-process `post_decision` short-circuits the poll), never
as the cross-process rendezvous. Local IPC-signal is a per-platform optimization
layered on the store, NOT an OR — the store is authority regardless (local IPC
breaks on musl-static per the WS-6 architecture verdict). When NO router is
wired (legacy single-process callers, Tier-1 unit tests), the future is the
same-process-only rendezvous (Phase-01 fallback).

**Timeout-audit-row preservation (zero-tolerance Rule 1):** on poll-timeout the
runtime drives the SAME `next_state(.., TIMEOUT_EXPIRED)` M2→M3 transition and
raises the SAME `GrantMomentExpiredError(request_id, timeout_seconds)` as the
Phase-01 `asyncio.TimeoutError` path. The timeout path appends NO ledger row in
either configuration; the only durable audit row a timed-out grant emits is the
Phase-A row written at issue, which is byte-identical across both paths
(`specs/grant-moment.md` § Timeout + § State machine).

### Poll interval / backoff (open-question #4 — DECIDED)

**Decision: bounded exponential backoff, 50ms start → 500ms cap, ×2 per idle
poll.** Constants `_DEFAULT_POLL_INTERVAL_START_SECONDS = 0.05`,
`_DEFAULT_POLL_INTERVAL_CAP_SECONDS = 0.5`, `_POLL_INTERVAL_BACKOFF_FACTOR = 2.0`
in `envoy/grant_moment/runtime.py`; overridable via the constructor for tests.

Rationale: a `grant` is answered by a human at a CLI prompt, so the latency is
seconds-to-minutes. The 50ms first interval makes a fast local answer resume
near-instantly; the ×2 backoff to a 500ms ceiling means a 5-minute deliberation
costs ≈ (5 × 60 / 0.5) ≈ 600 idle reads of a small WAL SQLite file — negligible
disk load — rather than 6000+ at a flat 50ms. The interval is a per-platform
OPTIMIZATION of the poll cadence, NOT a correctness parameter: the store is
authority and the monotonic-version guard holds at any cadence, so tuning the
interval cannot change which resolution is observed, only how soon.

## `grant` CLI answer surface (S4g-1)

`envoy grant` (`envoy/cli/grant.py`) is the human-answering half of the
cross-process Grant Moment flow: Envoy issues a Grant Moment in one process
(writing a `state=pending` row), and the user answers it in a SEPARATE `envoy
grant` invocation. Three subcommands, all resolving identity + vault + keyring
the same way `envoy init` does (`--principal` / `ENVOY_PRINCIPAL_ID`, `--vault` /
`ENVOY_VAULT_PATH`, the `ENVOY_KEYRING` selector — unset → OS keychain, `memory`
→ in-process ephemeral, any other value → exit 32):

- **`envoy grant list`** — reads `SessionRouter.list_pending_grants()` and renders
  each pending request (request_id, tool_name, why_asking, novelty_class,
  issued_at) with its one-line `approve` / `deny` command. Exits 0 with a
  friendly note when nothing is pending.
- **`envoy grant approve <request-id>`** — records an `ApproveResolution`.
- **`envoy grant deny <request-id> [--reason ...]`** — records a
  `DeclineResolution` (optional plain-language reason).

Division of labor: the answering CLI ONLY records WHICH `ResolutionShape` the
user chose — it calls `SessionRouter.resolve_pending_grant`, which signs the
resolution with the session key. It NEVER produces the delegation-key-signed
`GrantMomentResult`; that is the requesting process's M3 job, which reconstructs
the shape from the poll (S4r) and finalizes the signed Ledger entry.

Cross-process double-resolve defense is the store's `state='pending'`
compare-and-set: `approve`/`deny` first read the row (to recover the requesting
principal's `principal_genesis_id` for the resolution AND to give a precise
not-pending message), then write; a request that is absent or already terminal
(`resolved` / `expired`) is REFUSED with exit 40, never re-flipping a settled
decision. A row that races to terminal between the read and the write surfaces
the same refusal (the `resolve_pending_grant` `KeyError` from the CAS).

## `SessionRouter.list_pending_grants` (S4g-1 read surface)

`list_pending_grants() -> list[PendingGrantRow]` returns every `state='pending'`
row for this principal, newest first (`updated_at DESC, request_id ASC`), via the
`ix_pending_grant_principal_state` index. Resolved / expired rows are excluded —
only requests actually awaiting a decision surface. A fresh process over the same
vault sees the durable tail a prior (requesting) process wrote (the cross-process
read-back the `grant list` CLI consumes).

## Public surface

`envoy.runtime.session` exports (also re-exported from `envoy.runtime`):
`SessionRouter`, `PendingGrantRow`, `PENDING_GRANT_STATES`,
`SESSION_SIGNING_KEY_ID`, `session_db_path`. `SessionRouter` now also exposes
`resolve_pending_grant` (S4r write half) and `list_pending_grants` (S4g-1 read
half); `PendingGrantRow` carries `resolution_json` + `resolution_sig`. The
`grant` CLI group is exported from `envoy.cli.grant` and registered on the root
group in `envoy/cli/main.py`.

The cross-process resolution codec `resolution_to_json` / `resolution_from_json`
is exported from `envoy.grant_moment` (it owns the `ResolutionShape` types). The
runtime wiring is `EnvoyGrantMomentRuntime(session_router=...)` —
`envoy/grant_moment/runtime.py`.

## Test location

- `tests/tier2/test_session_router_wiring.py` — Tier-2 cross-process
  state-persistence: write via one `SessionRouter`, read back via a fresh
  instance over the same vault path (the new-process model). Covers both regions
  surviving restart, the monotonic `version` bump, the `0o600` sibling-db layout,
  the real SQLite CHECK constraint (store is real, not a dict), and fail-loud
  boundary validation. Real file-backed SQLite + real Ed25519 keychain key via
  an injected dict backend; no mocking.
- `tests/tier2/test_grant_moment_store_poll_rendezvous.py` — Tier-2 S4r
  cross-process rendezvous: process A's runtime issues + polls; a SEPARATE
  `SessionRouter` instance (fresh-process model) writes the resolution to the
  sub-store via `resolve_pending_grant`; A's `await_decision` poll resumes — NOT
  a same-event-loop `set_result`. Covers the monotonic-version lost-update guard
  (a version bump on a still-pending row is NOT a resolution; a resolved row
  written mid-poll IS observed) and the timeout-audit-row byte-identity (a
  poll-timeout emits the byte-identical Phase-A row + `GrantMomentExpiredError`
  and NO extra ledger row vs the Phase-01 future path). Real file-backed SQLite +
  real codec; no mocking.
- `tests/tier2/test_grant_cli_answer_flow.py` — Tier-2 S4g-1 `grant` CLI answer
  surface: `SessionRouter.list_pending_grants` (pending-only, newest-first,
  cross-process read-back); the `grant list` / `approve` / `deny` CLI against a
  real file-backed store with the `ENVOY_KEYRING=memory` headless seam (list
  renders pending requests with their answer commands; approve/deny flip the
  durable row to `resolved` carrying the correct `ResolutionShape`; an unknown or
  already-answered request is refused with exit 40); and the end-to-end resume
  through `grant`'s `_answer_pending_grant` helper (a session-key-signed
  resolution is picked up + verified fail-closed by the requesting runtime's S4r
  poll). All-sync `asyncio.run` (matching `test_ledger_cli_export.py`) so the
  CliRunner-invoked command's internal `asyncio.run` never nests.
- `tests/e2e/test_envoy_cli_packaging_acceptance.py` — `grant` added to
  `REGISTERED_AS_OF_F5` (9 of 10 subcommands wired; the strict-xfail for `grant`
  flipped to PASS).

## Cross-references

- **specs/session-state.md** — SessionObservedState schema + § Persistence
  (Region 2 stores this blob; S5o owns its semantics).
- **specs/grant-moment.md** — `GrantMomentRequest` / `GrantMomentResult` wire
  formats (Region 1 stores the request verbatim; S4r / S4g own the rendezvous
  - resolution).
- **specs/data-model.md** — Trust Vault persisted entities; the
  rebuild-from-replay generalization of these regions (Phase-02 multi-device).
- **specs/runtime-abstraction.md** — the abstract runtime the `SessionRouter`
  composes with (Phase-02 substrate-gated adapter methods).

## Out of scope (separate shards extend this spec)

- `grant` velocity-raise monotonic-skew defense + 3-deep delegation-tree
  persistence (S4g-2). S4g-1 ships the `grant list` / `approve` / `deny` answer
  surface + `list_pending_grants`; the persisted last-approved-timestamp +
  monotonic baseline (forward-skew detection) and the 3-deep delegation-tree
  persistence are the security-hardening half, in S4g-2.
- SessionObservedState first-time-action gate + reset-on-boundary writes (S5o).
- Multi-device materialized-index rebuild-from-replay (`specs/data-model.md:99`,
  Phase-02+).
