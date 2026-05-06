# 11 — Phase 02 entry checklist (carry-forward capture)

**Purpose:** Capture Phase 02 entry-checklist items inherited from Phase 01. These are NOT Phase 01 deliverables; they are pre-conditions for Phase 02 unfreeze. The /todos planner produces this file so the Phase 02 opening session reads it instead of re-discovering scope.

**Source authority:** `journal/0005-DECISION-todos-opening-dispositions.md` § Consequences + `briefs/00-phase-01-mvp-scope.md` § "External-gate carryover".

**Status discipline:** Each item below has a `Phase 02 entry pre-condition:` line stating what unblocks it. These are NOT scheduled at Phase 01 /implement-time.

---

## T-11-01 — IANA timezone fix (Option B)

**Source:** `journal/0003-GAP-budget-ceiling-timezone.md` + disposition #1 (`journal/0005`).

**Action:** Add `per_day_ceiling_timezone: str` field (IANA timezone identifier) to `EffectiveEnvelope.financial` in `specs/envelope-model.md`. Reset fires at user's local midnight per their declared timezone.

**Cost:** ~3 sessions (MUST Rule 5b 37-sibling re-derivation cycle; 6 historical Phase 00 redteam rounds for the envelope-model.md spec confirm this is the convergence cost).

**Phase 02 entry pre-condition:** Phase 01 shipped with Option A (UTC-only). Phase 02 opens with this as the first spec-edit ticket.

**Deferred from:** /todos opening human disposition (`journal/0005`).

---

## T-11-02 — Foundation Health Heartbeat full impl

**Source:** Shard 17 + disposition #2 (`journal/0005`).

**Action:** Un-stub the 4 `PhaseDeferredError` modules:

- `envoy/heartbeat/star_prio.py` — STAR/Prio + DP cohort-floor mechanism.
- `envoy/heartbeat/ohttp.py` — OHTTP relay client.
- `envoy/heartbeat/signed_consent.py` — Signed-consent telemetry envelope.
- `envoy/heartbeat/registry.py` — Foundation registry handshake.

Plus production wiring: 21 emit-site primitives transition `client.maybe_record_flag()` from no-op to real STAR/Prio submit.

**Cost:** ~3 sessions per shard 17 § 7.4.

**Phase 02 entry pre-condition:** k≥100 anonymity floor cohort available. Per shard 17, the floor is unclearable at Phase 01 cohort size; Phase 02 cohort projection (per ROADMAP) crosses this threshold.

**Deferred from:** Shard 17 DECISION; /todos opening disposition #2 confirmed.

---

## T-11-03 — Connection Vault third-party OAuth full integration

**Source:** Shard 14 + `briefs/00-phase-01-mvp-scope.md` § Phase 01 de-scope #3.

**Action:** Add full OAuth flows to `envoy/connection_vault/`:

- OAuth 2.0 authorization code flow (per provider).
- Refresh token rotation.
- Per-provider scope negotiation.
- Revocation cascade on Trust store cascade-revoke.

**Cost:** ~2 sessions.

**Phase 02 entry pre-condition:** Phase 01 ships with direct API-key paste only (per de-scope #3). Phase 02 opens with OAuth flows.

**Deferred from:** Phase 01 de-scope #3.

---

## T-11-04 — kailash-rs-bindings adapter wiring

**Source:** ADR-0001 phase migration table + shard 18 + `briefs/00-phase-01-mvp-scope.md` § Phase 01 invariant #1 + #2.

**Action:** Wire `envoy/runtime/kailash_rs_bindings.py` from `RuntimeBackendNotWired` to active. Per ADR-0001 phase migration table:

- Implement every `KailashRuntime` ABC method via `kailash-rs-bindings` (Rust → PyO3 → Python).
- Conformance vectors N1-N6 + E1-E7 per `specs/runtime-abstraction.md`.
- Byte-identical spec paths; semantically-equivalent LLM paths.

**Cost:** ~5 sessions (binding integration + conformance battery + cross-runtime regression suite).

**Phase 02 entry pre-condition:**

1. `terrene-foundation/kailash-rs` published with N4/N5 conformance vector runner (per `journal/0002` — ISS-36 closed 2026-04-25 confirms structural readiness).
2. `kailash-rs-bindings` PyPI wheel available for macOS / Linux / Windows.

**Deferred from:** Phase 01 invariant #1 (pure-Python only) + ADR-0001.

---

## T-11-05 — External gates (board + counsel + trademark)

**Source:** `briefs/00-phase-01-mvp-scope.md` § "External-gate carryover from Phase 00".

**Action:** Phase 01 /analyze proceeded in PARALLEL with these external gates; none block analysis but all block Phase 02 release:

1. Foundation board endorsement of ADR-0009 runtime-pluggability model.
2. USPTO + EUIPO + UK IPO trademark sweep close → final mark.
3. Counsel sign-off on composite LICENSE + SPDX + export-control + compatibility statement.
4. Launch-time §B re-runs (mailbox verify, CoC link, kailash-py PyPI name, namespace re-snapshot).

**Cost:** External; not measurable in autonomous execution sessions.

**Phase 02 entry pre-condition:** All 4 gates green. If any gate fails (e.g., trademark blocks `Envoy*` family), Phase 02 distribution must re-plan; Phase 01 architecture remains valid.

**Deferred from:** Phase 00 external gates; tracked at Foundation level.

---

## T-11-06 — Mobile clients / Flutter (Phase 02 stretch)

**Source:** `briefs/00-phase-01-mvp-scope.md` § "Out of scope for Phase 01".

**Action:** Build Flutter mobile client per CHARTER pillars. Cross-platform iOS / Android / desktop.

**Phase 02 entry pre-condition:** kailash-rs-bindings stable (T-11-04 done) AND mobile UX design specs drafted.

**Deferred from:** Phase 01 explicitly out-of-scope.

---

## T-11-07 — Envelope Library Foundation-Verified registry

**Source:** Brief § "Out of scope" (Phase 02 Foundation-Verified, Phase 03 Community).

**Action:** Foundation-Verified envelope library publication surface. Per `specs/envelope-library.md`.

**Phase 02 entry pre-condition:** Foundation board signoff on registry policy + Sybil/reputation primitives.

**Deferred from:** Phase 01 explicitly out-of-scope.

---

## Phase 02 entry sequence

When Phase 02 opens (assuming Phase 01 shipped successfully):

1. Read this file (`11-phase-02-handoff.md`).
2. Read `journal/0005-DECISION-todos-opening-dispositions.md` for the dispositions that produced these items.
3. Re-run freshness gate per `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` § "Why this matters for the kailash-py survey shard" — re-check upstream `kailash-rs` (and `kailash-py` if relevant) state at HEAD.
4. Re-validate the 4 external gates (T-11-05).
5. Open `/analyze` with Phase 02 brief grounded in this carry-forward + the Phase 01 codify journal entries.

---

## Cross-references

- Decisions journal: `journal/0005-DECISION-todos-opening-dispositions.md`
- Brief out-of-scope: `briefs/00-phase-01-mvp-scope.md` § "Out of scope"
- ADR-0001 phase migration: `DECISIONS.md` ADR-0001
- Runtime abstraction spec: `specs/runtime-abstraction.md`
- Heartbeat shard: `01-analysis/17-foundation-health-heartbeat-decision.md`
- Bridge journal: `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`
