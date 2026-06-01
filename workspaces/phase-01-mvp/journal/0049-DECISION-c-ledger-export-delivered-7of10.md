---
type: DECISION
date: 2026-06-01
created_at: 2026-06-01T13:00:00Z
author: co-authored
session_id: envoy-2026-06-01
session_turn: post-PR70-shardC
project: phase-01-mvp
topic: "F5.2-ledger shard C — `envoy ledger export` delivered; canonical CLI count re-scoped 6/10 → 7/10 (ledger Phase-02 → Phase-01)"
phase: implement
tags:
  [
    F5.2-ledger,
    EC-4,
    EC-9,
    envoy-ledger-export,
    durable-ledger,
    cli-substrate,
    rescope,
    value-prioritization,
    user-gated-closure,
  ]
---

# 0049 — DECISION: `envoy ledger export` delivered; canonical CLI count 6/10 → 7/10

## Context

`journal/0048` closed F5.2 at **6/10** canonical CLI subcommands and re-scoped
the remaining 4 (`init`, `chat`, `ledger`, `grant`) to Phase 02, all sharing one
blocker class: no process-independent persistent substrate. That entry named the
**first unblock** explicitly: _"wire the existing upstream `SqliteAuditStore`
into `EnvoyLedger` — that alone makes `ledger export` buildable as a one-shot
CLI and is the foundation the other three also depend on."_ Its "For Discussion"
#1 asked the counterfactual: would wiring the durable store collapse the
"4 remaining" to "2 remaining" by making `ledger export` buildable?

This session executed exactly that unblock as the **durable-ledger-export
workstream** (decomposed A → B1 → B2 → B3 → C):

- **Shard A** (`#67`, merged earlier): durable cross-process audit store
  (`open_durable_ledger` over file-backed `SqliteAuditStore`) + chain
  rehydration.
- **Shard B1** (`#68`): OS-keychain-durable Ed25519 signing key
  (`load_or_create_ledger_key_manager`) — the SAME key across process restarts.
- **Shard B2** (`#69`): re-mint the signed head on rehydrate so a fresh process
  can `export()` a populated ledger.
- **Shard B3** (`#70`): wire A + B1 + B2 into the production digest bootstrap
  (the writer) + a partial-construction resource-leak guard surfaced by the
  gate review.
- **Shard C** (this PR): the `envoy ledger export` CLI (the reader) +
  this re-scope.

## Decision

**`envoy ledger export` ships in Phase 01. The canonical CLI count is re-scoped
6/10 → 7/10**, moving `ledger {export}` from the Phase-02 deferred set into the
Phase-01 shipped set. The remaining deferred set is **3** (`init`, `chat`,
`grant`). User-gated this session (the user approved "go to C", which the
recommendation explicitly described as "build `envoy ledger export` + un-rescope
the held specs"), satisfying `value-prioritization.md` MUST-4 (re-scope of
value-bearing deferred work requires explicit in-session user approval).

The counterfactual in 0048 "For Discussion" #1 is **answered YES for `ledger`**:
wiring the durable store + durable key made `ledger export` buildable as a
one-shot CLI. It did NOT collapse `grant` (which additionally needs a durable
pending-grant projection + a long-running `SessionRouter` session model, neither
built) — so the count moved 6 → 7, not 6 → 8.

## What shipped (verified)

- `envoy/cli/ledger.py` — `envoy ledger export [--format json] [--output PATH]`:
  opens the principal's durable ledger through the shared identity constants,
  `export()`s the signed bundle, writes to a file or stdout (logs to stderr so
  `envoy ledger export > bundle.json` is clean JSON). Empty ledger → clean
  `ClickException` ("nothing to export…"), never a traceback.
- `envoy/ledger/bootstrap.py` — the durable-ledger **identity** (signing-key id
  / device id / algorithm identifier) hoisted to a single source of truth
  (`LEDGER_SIGNING_KEY_ID` / `LEDGER_DEVICE_ID` / `LEDGER_ALGORITHM_IDENTIFIER`).
  String VALUES retained verbatim from the digest's original wiring so existing
  on-disk ledgers + keychain entries stay readable. The writer
  (`daily_digest/bootstrap.py`) and the reader (`cli/ledger.py`) now resolve the
  SAME constants — a drift would silently open a different/empty ledger.
- `envoy/cli/main.py` — registers `ledger`; root docstring updated to 7/10.
- `tests/tier2/test_ledger_cli_export.py` — canonical-surface lock
  (`ledger {export}`), JSON-only format gate, empty-ledger clean error, the
  round-trip (writer appends → CLI exports → bundle entries present +
  `receipt_hash` self-verifies, the verifier's invariant-8 check recomputed
  independently), and stdout cleanliness.

Gates: `mypy envoy/` (128 files) + `pyright envoy/` clean; tier1+tier2+regression
**1342 passed, 9 skipped**. CLI walk: a fresh `envoy ledger export` process
reloaded the durable key (`ledger.keystore.loaded`), reopened the SAME ledger,
and wrote a 2-entry `envoy-ledger-export/1.0` bundle with a valid `receipt_hash`;
stdout form parsed clean; empty-vault form failed loud + clean.

## Alternatives considered

- **Leave `ledger` deferred at 6/10** — REJECTED. 0048's first-unblock was a
  named, low-cost slice; deferring it would have left the highest-value Phase-01
  ship gate (EC-4 `envoy ledger export` / EC-9 independent verifier) unbuilt
  while the substrate it needed was already merged (A/B1/B2). Per
  `value-prioritization.md`, the EC-4/EC-9 capability is the user-anchored
  value; deferring it to pick smaller work would be streetlight selection.
- **Also un-defer `grant` now** — DEFERRED. `grant` needs substrate this
  workstream did NOT build (durable pending-grant projection + `SessionRouter`).
  Un-deferring it would over-claim; it stays in Phase 02 hooks item 9.

## Value-anchor (`value-prioritization.md` MUST-6)

`specs/mvp-build-sequence.md` line 128 (canonical shard-19 § 3.4) lists
`ledger {export}` as a Phase-01 canonical subcommand, VERBATIM:
**"11 subcommands per shard 19 § 3.4 (canonical): `init`, `chat`,
`ledger {export}`, …"**. EC-4 (line 67) + EC-9 require the export bundle a
separately-codebased verifier consumes. Delivering `ledger export` serves that
user-authored success criterion directly.

## Consequences & follow-up

- `specs/mvp-build-sequence.md` line 190 (Milestone-5 criterion) + item 9 +
  `02-plans/01-build-sequence.md` line 334 re-scoped 6/10 → 7/10; item 9 now
  covers the 3 remaining (`init`/`chat`/`grant`) and records the first-unblock
  as DELIVERED.
- `journal/0048` is immutable and stands as the 6/10-ceiling record; this entry
  supersedes its disposition for `ledger` only.
- Next-workstream candidate (NOT auto-started): the EC-9 independent verifier
  (`envoy-ledger-verifier`) consumes the bundle `envoy ledger export` now
  produces — a SEPARATE repo (out of this repo's scope); and the
  pending-grant/session substrate for `grant` (Phase 02).

## For Discussion

1. **Counterfactual:** with `ledger export` now shipping, is the Phase-01
   release gate (Milestone-5 convergence) met at 7/10 — or does
   `02-mvp-objectives.md` EC-4/EC-9 require the separately-codebased
   `envoy-ledger-verifier` to actually CONSUME a real `envoy ledger export`
   bundle before Phase 01 can be declared shipped? (The producer is done; the
   consumer is a different repo.)
2. **Data-referencing:** the shard-19 § 3.4 canonical table (cited at
   `specs/mvp-build-sequence.md:128`) still lacks explicit `model` / `connection`
   / `version` rows even though line 128 lists them — the canonical anchor and
   its consumer drifted (0048 "For Discussion" #2 flagged this). Does landing C
   warrant reconciling that table drift now, or is it a separate cleanup?
3. **Interface coordination:** the export bundle shape (`envoy-ledger-export/1.0`)
   is the contract the parallel F2 `envoy-ledger-verifier` session consumes. Is
   the bundle's `to_dict()` wire form frozen enough to hand to the verifier, or
   should a conformance fixture be committed (producer-side) before the verifier
   builds against it?
