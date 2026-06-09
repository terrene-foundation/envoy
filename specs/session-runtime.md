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
the empty-but-durable store + the raw region read/write surface. It does NOT
yet contain the cross-process decision rendezvous (poll), the `grant` read
surface, the `init` genesis write, or the SessionObservedState gate
semantics — those land in their own shards (S4r / S4g / S4i / S5o) and extend
this spec as they ship.

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

| Column            | Type    | Notes                                                                        |
| ----------------- | ------- | ---------------------------------------------------------------------------- |
| `request_id`      | TEXT PK | key shape — the `GrantMomentRequest.request_id` (uuid-v7)                     |
| `principal_id`    | TEXT    | owning principal                                                             |
| `session_id`      | TEXT    | issuing session                                                              |
| `state`           | TEXT    | enum `pending` / `resolved` / `expired`, enforced by a SQLite CHECK          |
| `request_json`    | TEXT    | canonical-JSON `GrantMomentRequest`, stored verbatim (S4s does not parse it) |
| `resolution_json` | TEXT    | nullable; the resolution row S4r writes; NULL while pending                  |
| `version`         | INTEGER | monotonic; bumped on every re-put — the lost-update primitive S4r polls      |
| `ttl_expires_at`  | TEXT    | ISO-8601 TTL bounding queue growth (S4g back-pressure)                       |
| `created_at`      | TEXT    | ISO-8601; preserved across re-puts                                           |
| `updated_at`      | TEXT    | ISO-8601                                                                     |

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
  read-back (returns `version` for the S4r poll re-check); None if absent.
- `count_pending_grants() -> int` — count of `state=pending` rows for the
  principal (the primitive S4g's back-pressure ceiling reads).

`request_json` MUST be a parseable JSON object — a malformed blob raises at the
write boundary (fail-loud per `rules/zero-tolerance.md` Rule 2). S4s does NOT
interpret the wire format's fields; the semantic surface (nonce dedup, the
cross-process poll rendezvous, sign-resolution) is S4r / S4g.

### Region 2 — SessionObservedState (`session_observed_state` table)

The durable snapshot home for `specs/session-state.md` § Persistence
("snapshot to Trust Vault encrypted at every Ledger append, so a crash
mid-session preserves orphan-phase-A tracking", `session-state.md:182`).

| Column         | Type    | Notes                                                                 |
| -------------- | ------- | --------------------------------------------------------------------- |
| `session_id`   | TEXT PK | key shape — the `SessionObservedState.session_id` (uuid-v7)           |
| `principal_id` | TEXT    | owning principal                                                      |
| `state_json`   | TEXT    | canonical-JSON `SessionObservedState`, stored verbatim                |
| `version`      | INTEGER | monotonic; bumped on every snapshot                                   |
| `updated_at`   | TEXT    | ISO-8601                                                              |

Raw store surface shipped in S4s:

- `snapshot_observed_state(*, session_id, state_json)` — upsert the blob; re-snapshot
  bumps `version`. `state_json` MUST be a parseable JSON object (fail-loud).
- `load_observed_state(session_id) -> str | None` — cross-process re-hydration
  read-back; None if no snapshot exists.

S4s stores + returns the `state_json` verbatim. The fingerprint /
first-time-action gate / goal-reconfirmation semantics that DERIVE the blob are
owned by S5o (`specs/session-state.md` § Algorithm), which consumes this region.

## Public surface

`envoy.runtime.session` exports (also re-exported from `envoy.runtime`):
`SessionRouter`, `PendingGrantRow`, `PENDING_GRANT_STATES`,
`SESSION_SIGNING_KEY_ID`, `session_db_path`.

## Test location

- `tests/tier2/test_session_router_wiring.py` — Tier-2 cross-process
  state-persistence: write via one `SessionRouter`, read back via a fresh
  instance over the same vault path (the new-process model). Covers both regions
  surviving restart, the monotonic `version` bump, the `0o600` sibling-db layout,
  the real SQLite CHECK constraint (store is real, not a dict), and fail-loud
  boundary validation. Real file-backed SQLite + real Ed25519 keychain key via
  an injected dict backend; no mocking.

## Cross-references

- **specs/session-state.md** — SessionObservedState schema + § Persistence
  (Region 2 stores this blob; S5o owns its semantics).
- **specs/grant-moment.md** — `GrantMomentRequest` / `GrantMomentResult` wire
  formats (Region 1 stores the request verbatim; S4r / S4g own the rendezvous
  + resolution).
- **specs/data-model.md** — Trust Vault persisted entities; the
  rebuild-from-replay generalization of these regions (Phase-02 multi-device).
- **specs/runtime-abstraction.md** — the abstract runtime the `SessionRouter`
  composes with (Phase-02 substrate-gated adapter methods).

## Out of scope (this shard — separate shards extend this spec)

- Cross-process decision rendezvous — `await_decision` store-poll-with-monotonic-version
  re-check, replacing the in-process `asyncio.Future` (S4r).
- `grant` read surface + sign-resolution flow + nonce dedup (S4g).
- `init` / Boundary-Conversation genesis write (S4i).
- SessionObservedState first-time-action gate + reset-on-boundary writes (S5o).
- Multi-device materialized-index rebuild-from-replay (`specs/data-model.md:99`,
  Phase-02+).
