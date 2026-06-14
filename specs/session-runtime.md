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
| `request_json`    | TEXT    | canonical-JSON `GrantMomentRequest`, validated then AES-256-GCM-encrypted-at-rest (`enc:v1:` token; S5o-enc) — stored verbatim otherwise (S4s does not parse it)       |
| `resolution_json` | TEXT    | nullable; the resolution row S4r writes, AES-256-GCM-encrypted-at-rest (`enc:v1:` token; S5o-enc); NULL while pending                                                  |
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
The `state_json` blob is AES-256-GCM-encrypted-at-rest (`enc:v1:` token; S5o-enc);
the `pending_grant` resolution rows the same store holds ALSO carry a
keychain-signed `resolution_sig` (§ Resolution authenticity), so this store is
signed AND encrypted-at-rest — the two are complementary (tamper-evidence +
confidentiality), not a swap.

| Column         | Type    | Notes                                                                                                          |
| -------------- | ------- | -------------------------------------------------------------------------------------------------------------- |
| `session_id`   | TEXT PK | key shape — the `SessionObservedState.session_id` (uuid-v7)                                                    |
| `principal_id` | TEXT    | owning principal                                                                                               |
| `state_json`   | TEXT    | canonical-JSON `SessionObservedState`, validated then AES-256-GCM-encrypted-at-rest (`enc:v1:` token; S5o-enc) |
| `version`      | INTEGER | monotonic; bumped on every snapshot                                                                            |
| `updated_at`   | TEXT    | ISO-8601                                                                                                       |

Raw store surface shipped in S4s:

- `snapshot_observed_state(*, session_id, state_json)` — upsert the blob; re-snapshot
  bumps `version`. `state_json` MUST be a parseable JSON object (fail-loud).
- `load_observed_state(session_id) -> str | None` — cross-process re-hydration
  read-back; None if no snapshot exists.

S4s stores + returns the `state_json` verbatim (after the encrypt/decrypt
round-trip below). The fingerprint / first-time-action gate /
goal-reconfirmation semantics that DERIVE the blob are shipped in S5o
(§ SessionObservedState first-time-action gate below;
`specs/session-state.md` § Algorithm), which consumes this region.

### Region encryption-at-rest (S5o-enc)

The payload columns — `request_json` / `resolution_json` (Region 1) and
`state_json` (Region 2) — are AES-256-GCM ciphertext on disk, not plaintext.

- **Token format.** Each encrypted column holds `enc:v1:` + base64(`nonce ‖
ciphertext ‖ GCM tag`), a fresh 96-bit nonce per encrypt. The versioned prefix
  makes a future format migration detectable AND makes the read path REFUSE a
  non-`enc:v1:` value loudly (no silent plaintext-acceptance downgrade).
- **Key source — keychain-gated.** A dedicated 32-byte AES-256 key
  (`SESSION_ENCRYPTION_KEY_ID`) persisted in the OS keychain via
  `load_or_create_session_encryption_key`, namespaced distinctly from the
  Ed25519 session signing key (key separation; own rotation/destroy surface).
  A process without OS-keychain access cannot obtain the key → cannot decrypt.
- **AAD binding.** Each ciphertext's additional-authenticated-data binds it to
  `(table, row-key, column)`, so a ciphertext lifted from one row/column and
  pasted into another fails the GCM tag check (intra-store shuffle defense).
- **Cleartext columns.** `request_id` / `session_id` / `principal_id` / `state`
  / `version` / `ttl_expires_at` / `created_at` / `updated_at` stay cleartext so
  the lookup index, the `state` CHECK constraint, and the lost-update `version`
  re-check keep working.
- **Layered with signing.** `resolution_sig` is signed over the PLAINTEXT
  resolution, then the column is encrypted; on read the payload is decrypted
  first and the signature verifies against that plaintext. Signing
  (tamper-evidence) and encryption (confidentiality) are complementary.
- **Read failure modes.** The strict read path (`get_pending_grant`, driving the
  security-critical poll) RAISES `SessionStoreEncryptionError` on an undecryptable
  payload — fail-closed (a forged direct-sqlite row, written without the key, is
  refused; the poll maps it to `GrantMomentResolutionUnauthenticatedError`). The
  tolerant UI path (`list_pending_grants`, the `grant list` read) surfaces a
  single undecryptable row as malformed (loud marker) without aborting the
  listing — a read-only surface never executes a decision.
- **Design note — keychain, not vault-passphrase.** The durable-substrate plan
  originally anticipated "vault-unlock key material", but the `SessionRouter`
  opens short-lived one-shot CLI processes (`grant approve` in a fresh process)
  that hold no passphrase; a passphrase-gated key would force a vault-unlock
  prompt on every `grant`/`chat` invocation. Keychain-gating closes the same
  local-file-read residual (`specs/threat-model.md` § Residual risks) without
  that UX cost, matching the existing `resolution_sig` signing key's trust model.

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

## Session-lifecycle boundary signal (S5b)

`envoy.runtime.session_boundary.SessionBoundarySignal` is the lifecycle emitter
for the `session_boundary_crossed` Ledger entry, the shared signal S5o (the
observed-state gate) and S6c (the `chat` resident loop) both consume. Constructed
with an injected `EnvoyLedger` + `SessionRouter`,
`cross(trigger, session_id_prior, session_id_next=None)`:

1. Maps the trigger to its transition — `unlock` / `cli_start` → `start`;
   `cli_end` / `idle_timeout` / `user_lock` / `channel_disconnect` → `end`
   (an unknown trigger raises `ValueError`).
2. Derives the boundary counts from the prior session's observed-state blob
   (`load_observed_state`) and the store's `count_pending_grants()`, and appends
   the signed `session_boundary_crossed` entry (`session-boundary/1.0`) via the
   `EnvoyLedger` envelope.
3. On an `end` transition, applies the **T-013 reset** to the prior session's
   durable Region-2 blob — `reset_session_observed_state` clears
   `tool_calls_made` + `goal_reconfirmation.tool_calls_since_reconfirm` and drops
   `scope: session` `pre_authorized_patterns` (keeping `cross_session`), then
   `snapshot_observed_state` persists the cleared blob. The counts are captured in
   the signed entry BEFORE the reset, so the audit row keeps the end-of-session
   totals while the next session's first identical tool call is first-time-action
   again.

The reset contract + the `is_recognized_fingerprint` recognition predicate are
exported from `envoy.runtime` and the reusable invariant assertion lives at
`tests/support/t013.py`; S5o and S6c reuse them rather than re-deriving the reset
(`rules/specs-authority.md` Rule 5b). The observed-state gate semantics
themselves (fingerprint canonicalization, AST pattern match, goal-reconfirmation
threshold) are owned by S5o. The owning-spec for the entry schema + the T-013
invariant is `specs/session-state.md` § session_boundary_crossed.

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

The S5b session-lifecycle boundary surface is exported from
`envoy.runtime.session_boundary` (also re-exported from `envoy.runtime`):
`SessionBoundarySignal`, `SessionBoundaryResult`, `reset_session_observed_state`,
`is_recognized_fingerprint`, `boundary_transition`, `START_TRIGGERS`,
`END_TRIGGERS`, `ALL_TRIGGERS`, `SESSION_BOUNDARY_ENTRY_TYPE`,
`SESSION_BOUNDARY_SCHEMA_VERSION`.

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

## SessionObservedState first-time-action gate (`envoy.runtime.observed_state` — S5o)

The gate semantics that DERIVE the Region-2 blob. Two layers: a PURE,
deterministic gate (`envoy.runtime.observed_state`) both runtime adapters
delegate to, and a store-wired orchestrator
(`envoy.runtime.observed_state_gate.SessionObservedStateGate`) that loads from /
persists to Region 2.

**Fingerprint.** `fingerprint(tool_name, args)` returns
`sha256:<hex>` over `NFC(tool_name) || canonicalize_args(args)`, where
`canonicalize_args` is the envelope-model JCS+NFC pipeline
(`envoy.envelope.canonical_bytes`). The SAME pipeline both runtimes use, so the
fingerprint is byte-identical across `kailash-py` and `kailash-rs-bindings`
(the N6 conformance invariant); an NFD-authored tool name or arg value hashes
identically to its precomposed sibling.

**`first_time_action_gate(session, tool_name, args) -> GateResult`.** The pure
gate (`specs/session-state.md` § Algorithm). Returns `RECOGNIZED` on a
fingerprint cache-hit (via the S5b `is_recognized_fingerprint` membership
predicate — reused, not re-derived per `specs-authority.md` Rule 5b) or a
pre-authorized-pattern match; else `FIRST_TIME_REQUIRES_GRANT` (the caller
dispatches `specs/grant-moment.md`). Both adapters' `first_time_action_gate`
delegate to this one function, so the `GateResult` is byte-identical by
construction (`@byte_identical` per `specs/runtime-abstraction.md`).

**Pre-authorized pattern AST (fail-closed).** `match_ast(pattern_ast, args)`
matches a pre-authorized pattern (`SessionObservedState.pre_authorized_patterns`)
against tool-call args. Both MUST be dicts with the EXACT same key set — an args
key the pattern does not constrain is an unauthorized parameter, and a pattern
key absent from args is an unmet precondition; either fails the match closed
(a pattern bypasses the Grant Moment, so it MUST never over-match). Each shared
key's value is matched by node grammar: `{"match":"exact","value":x}` (equality),
`{"match":"any"}` (any value present), `{"match":"prefix","value":"<str>"}`
(string `startswith`), `{"match":"type","value":"str|int|float|bool|list|dict"}`
(`isinstance`; `int` does NOT match `bool`), a nested plain dict (recursive
match), a list (elementwise, same length), or a bare scalar (exact). An unknown
`match` directive fails closed. A pre-authorized match RECORDS the call into
`tool_calls_made` (`last_outcome="pre_authorized"`) so the next identical call is
a plain cache hit.

**Goal-reconfirmation.** `check_goal_reconfirmation(session)` raises
`GoalReconfirmationThresholdExceededError` when
`goal_reconfirmation.tool_calls_since_reconfirm ≥ threshold` (threshold `0` —
the genesis default — DISABLES the gate). `record_observation` increments the
counter per observed tool call; `reconfirm_goal` resets it to 0.

**Store-wired `SessionObservedStateGate(router=...)`** (the "Wire" half):
`evaluate(session_id, tool_name, args)` loads the Region-2 blob, enforces the
goal-reconfirmation threshold, runs the pure gate, and persists when the gate
recorded a pre-authorized match; `observe(...)` records a tool-call observation
and snapshots it (the "snapshot at every Ledger append" crash-safety write);
`reconfirm(session_id)` resets the counter. A fingerprint observed in one process
is RECOGNIZED by a gate over a fresh router opened on the same vault (cross-process
persistence). The T-013 boundary RESET is NOT re-implemented here:
`SessionBoundarySignal.cross()` (S5b) applies `reset_session_observed_state` to
the durable region on an END transition; S5o CONSUMES that signal — after a
boundary crossing, `evaluate` on a previously-recognized fingerprint returns
`FIRST_TIME_REQUIRES_GRANT` (proven via the shared `tests/support/t013.py`
invariant, no per-shard reset re-derivation).

## Structural envelope-check engine (`envoy.runtime.envelope_check` — S6a)

The byte-identical STRUCTURAL verdict for `envelope_check(envelope, action)`. A
single pure function (`envelope_check_structural`) both runtime adapters delegate
to, so the verdict is byte-identical by construction (the same shared-pure-
delegation shape as the S5o gate above), and the structural slice NEVER dispatches
the classifier ensemble.

**Structural-vs-semantic partition.** `is_semantic_action(action)` returns True iff
the action carries `content` (bytes) to be classified. The adapters route a
semantic action to the classifier ensemble (substrate-gated on S6d — raises a
typed not-ready error naming S6d); a structural (content-free) action is evaluated
here. This is the `specs/runtime-abstraction.md` § Contract-partition contract: the
N3 structural slice's "structural ⇒ no classifier dispatch" invariant holds by
construction (the structural path never reaches a dispatch site).

**Verdict shape (byte-identical).** A plain dict with stable keys + sorted field
lists, canonicalized through `envoy.envelope.canonical_bytes` (JCS-RFC8785 + NFC)
at scoring time: `schema` (`envoy.envelope-check-verdict/1.0`), `verdict_class`
(`"structural"`), `outcome`, `model`, `allowed_fields`, `denied_fields`,
`reject_reason`, `cache_key`, `effective_posture`.

**Structural validation (N3-structural).** First violation (fixed order, so the
reason is deterministic) yields `outcome="structural_reject"` with `reject_reason`
one of: `missing_schema`, `malformed_schema` (schema not `envelope/<major>.<minor>`),
`type_mismatch` (`envelope_version` non-int), `allowlist_shape`
(`field_allowlist_per_model` not a map), `dimension_out_of_range`
(`dims.max_depth` > 64), `unknown_action_verb` (a present `verb` outside the
known data-access grammar), or `malformed_envelope` (non-dict envelope).

**Knowledge-filter gate (N1).** For a well-formed envelope, the action's
`requested_fields` are partitioned against `field_allowlist_per_model[model]` into
sorted `allowed_fields` / `denied_fields`; `outcome` is `allow` (none denied),
`deny` (none allowed), or `partial_deny`. The pre-retrieval over-fetch gate: a
field absent from the model's allowlist is denied before classification.

**Cache key (N2).** `cache_key` is a `content_hash` over exactly the five
invalidation properties (`envelope_version`, `algorithm_identifier`,
`classifier_ensemble_versions`, `posture_level`, `principal_genesis_id`); a change
to ANY one flips the key (cache invalidation), an unrelated edit does not. Distinct
from the posture-ceiling input below — this `posture_level` is the top-level
cache-key property. **Cache-consumer contract (S6d — security review MED-2):**
`field_allowlist_per_model` is deliberately NOT one of the five (the set is the
N5/`runtime-abstraction.md`-mandated invalidation axes), so two envelopes differing
ONLY in their field allowlist hash to the SAME `cache_key`. Any future verdict
cache keyed on `cache_key` therefore RELIES on the envelope compiler incrementing
`envelope_version` whenever `field_allowlist_per_model` changes — otherwise a
tightened allowlist could serve a stale, over-permissive cached verdict. The S6d
cache wiring MUST verify that invariant (or key the cache on `(cache_key,
action-shape, allowlist-hash)`) before memoizing the full verdict.

**Posture ceiling (N5).** `effective_posture` is the floor (more-restrictive) of
the envelope-declared ceiling (`envelope.metadata.posture_level`) and the
principal-current posture (`action.principal_posture`) on the ladder
`OBSERVED < SUPERVISED < TRUSTED < AUTONOMOUS` (lower = more restrictive); `None`
when either posture is absent or off-ladder.

## `chat` resident loop contract (`envoy.runtime.chat` — S6c)

`ChatResidentLoop` is the resident receive-loop behind `envoy chat` (the 10th
canonical CLI command). It is a TRANSPORT/CACHE over the durable store, never the
authority: the store (Region 1 pending-grant sub-store + Region 2
SessionObservedState) is the single source of truth, so the loop holds no
authoritative state and a crash mid-conversation loses nothing.

**Lifecycle.** Constructed with an injected channel adapter + S5b boundary signal

- session id + a message `resolver`, plus the OPTIONAL grant substrate (the
  grant-moment runtime + the S5o observed-state gate). `run()` starts the adapter,
  drains `receive_message()` until the iterator ends (channel disconnect), and in
  `finally` fires the disconnect boundary THEN shuts the adapter down. The
  boundary-then-teardown order is load-bearing: the session-end T-013 reset is
  session semantics, the shutdown is transport cleanup.

**Per-turn handling.** The injected `resolver` maps each inbound message to a
`ChatActionSpec` (the message carries a tool dispatch) or `None` (plain
conversation). A plain message is acked. An action message runs the S5o
first-time-action gate: a `RECOGNIZED` verdict proceeds (the loop replies
immediately); a `FIRST_TIME_REQUIRES_GRANT` verdict drives a Grant Moment —
`issue_grant_moment` writes the durable pending row, then `await_decision` polls
the store (the S4r rendezvous, NOT an in-process future) until a SEPARATE process
(`envoy grant approve`/`deny`) resolves it. On approve the loop caches the
fingerprint via the gate (`observe`) so a same-session repeat is `RECOGNIZED`.

**Conversation-only mode.** A loop with no grant substrate wired (`runtime` /
`gate` omitted) acks plain messages with real session-boundary semantics. An
action spec produced without the substrate raises the typed
`ChatActionUnsupportedError` (`rules/zero-tolerance.md` Rule 3a) — the honest
failure, NOT a fabricated grant outcome. The bare `envoy chat` CLI ships this
conversation surface (it never synthesizes consequence/novelty signals a user did
not provide); an agent layer injects an action resolver + the grant runtime to
activate the gate/grant path.

**Crash-recovery contract.** Because the pending row is durable the instant
`issue_grant_moment` returns and the loop owns no copy of it, a loop killed while
polling `await_decision` leaves an answerable pending grant in the store: a fresh
process (`envoy grant`) sees it via `list_pending_grants` and resolves it. The
store is authority; the resident loop is recoverable transport.

The S6c public surface is exported from `envoy.runtime.chat` (also re-exported
from `envoy.runtime`): `ChatResidentLoop`, `ChatActionSpec`, `ChatTurnResult`,
`ChatMessageResolver`, `ChatActionUnsupportedError`. The `chat` CLI group is
`envoy.cli.chat`, registered on the root group in `envoy/cli/main.py`. Channel
`send_message` legs (cli / telegram / discord / slack) ship real outbound
transport; the web SSE/WS leg remains deferred to the Wave-4 Nexus InboundRouter
shard (`envoy/channels/web.py` `send_message`).

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
- Multi-device materialized-index rebuild-from-replay (`specs/data-model.md:99`,
  Phase-02+).
