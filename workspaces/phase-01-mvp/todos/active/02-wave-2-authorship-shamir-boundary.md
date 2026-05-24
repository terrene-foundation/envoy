# 02 — Wave 2: Authorship + Shamir + Boundary Conversation

**Purpose:** Build the 3 Wave-2 primitives in dependency order. Authorship and Shamir are independent within the wave; Boundary Conversation depends on Shamir's S8 backup-pause integration. Wave 2 converges on the EC-1 acceptance gate (Boundary Conversation N=3 ≤25min).

**Source authority:** `02-plans/01-build-sequence.md` § Wave 2 + shards 8 / 9 / 15.

**Depends on:** Wave 1 (`01-wave-1-foundation.md`) fully converged.

---

## T-02-30 — Build envoy/authorship/score (pure function) ✅ CLOSED 2026-05-07 (PR #14)

**Status:** Shipped. `recompute_authorship_counters()` + `AuthorshipCounters` frozen dataclass + `AuthorshipScoreDivergenceError` (commits cd75810b + 9ecbcb2 + merge 024ad8d). Per /autonomize Rule 1 optimal pick: count-only recompute on `c.authored is True` only; spec edit per `spec-accuracy.md` Rule 5 removed Phase-04 algorithm content. Sibling-spec sweep (per `specs-authority.md` Rule 5b) edited `posture-ladder.md` + `envelope-model.md`. 20/20 Tier 1 tests; full suite 403/403 pass.

**Gate-review surfaced findings (all resolved in same PR per autonomous-execution.md Rule 4):** H-01 (`getattr(_, _, True)` silent inflation), H-02 (truthy coercion), M-1 (cross-spec drift — envelope-model.md + posture-ladder.md still cited Phase-04 errors), M-01 (template_hash None/"" collapse), M-02 (from_dict type validation).

**Deferred to T-02-31 PostureGate (next-shard consumer):** L-02 log emission (PostureGate emits authorship.recompute / authorship.divergence at DEBUG / WARN per observability.md Rule 8). Phase-04 novelty + minimum-impact + classifier registry + cold-start corpus stay Phase 04 territory.

**Implements:** `specs/authorship-score.md` § Score recompute

**Source:** Shard `01-analysis/09-authorship-score-implementation.md` § 3 step 1.

**Action:** `AuthorshipScore.recompute(envelope, ledger_slice) -> int` — pure deterministic re-derivation; 5-dimension canonical iteration order. Cross-shard JCS-canonical-order invariant for shard 4 (Envelope compiler) — surfaced in /analyze wave-B.

**Tests added:** `tests/tier1/test_authorship_score_recompute_pure.py` — deterministic replay across same envelope+slice.

**Capacity check:** ~120 LOC pure function; 3 invariants (5-dim canonical order; JCS sort discipline; deterministic replay); 1 call-graph hop.

**Estimate:** 0.25 session.

---

## T-02-31 — Build envoy/authorship/posture_gate ✅ CLOSED 2026-05-10 (PR #19)

**Status:** Shipped. `PostureGate.request_transition()` 5-step fail-closed gate (commits `74d66d0` feat + `84c1d0f` fix + merge `694ceb2`). Public surface: `PostureLevel`, `PostureMode`, `PostureEvidence`, `PostureChangeResult`, `PostureGate`, `PostureGateError` + 5 typed subclasses. 80/80 Tier 1 tests green; full suite 542/542 pass.

**Gate-review surfaced findings (all resolved in same PR per autonomous-execution.md Rule 4):** security-reviewer M-1 (revoke*on_demotion agent_id needs gate-boundary `_validate_agent_id` defense — added local helper mirroring `envoy/trust/store.py:_validate_id_safety` contract), security-reviewer M-2 (envelope_id_hash needs length+charset bounds — added 128-char cap + `[a-zA-Z0-9:*-]+`regex on`PostureEvidence.**post_init**`), security-reviewer L-3 (revoke_on_demotion idempotency-on-retry docstring), security-reviewer L-4 (`\_required_authorship`defensive raise test), security-reviewer L-5 (hoist`AuthorshipScoreDivergenceError` from local-import to module scope), reviewer M-1 (envelope_edit deferral — see below).

**Deferred to T-02-33 (per `journal/0020-DECISION-envelope-edit-deferred-to-tier-2.md`):** `envelope_edit` Ledger entry pairing on ratchet-up (spec line 41 mandate). PostureGate Phase 01 emits ONLY `posture_change`; the paired `envelope_edit` requires `_EnvelopeProtocol` DI surface + envelope-mutation contract that is out of T-02-31's primitive substrate. T-02-33 acceptance bullet now binds Tier 2 wiring to add the pairing.

**Implements:** `specs/posture-ladder.md` + `specs/authorship-score.md` § Posture gate

**Source:** Shard 9 § 3 step 2.

**Action:** `PostureGate.request_transition()` — 5-step fail-closed enforcement; cascade-revoke hook on demotion (calls into envoy/trust/cascade T-01-14).

**Tests added:** `tests/tier1/test_posture_gate_5_step_fail_closed.py` (80 cases, 19 test classes).

**Capacity check:** ~190 LOC load-bearing logic (within ≤500 LOC threshold per `rules/autonomous-execution.md` MUST Rule 1); 5 invariants (5-step gate sequence; fail-closed default; cascade-on-demotion; signed posture_change Ledger entry; posture-ratchet enforcement); 3 call-graph hops (PostureGate → `_LedgerProtocol.append` OR PostureGate → `_RevokeHook` → kailash cascade_revoke).

---

## T-02-32 — Build envoy/authorship/bet12_emitter ✅ CLOSED 2026-05-11

**Status:** Shipped. `BET12CadenceEmitter` primitive + `BET12Sink` Protocol + `BET12CadencePayload` frozen dataclass landed at `envoy/authorship/bet12_emitter.py` (~150 LOC); wired as required DI surface on `PostureGate.__init__` and emitted at Step 5+ post-Ledger in `request_transition` per `rules/orphan-detection.md` Rule 1 production-call-site contract. 17 new Tier 1 tests in `tests/tier1/test_bet12_cadence_emitter.py` + 6 new wiring tests in `tests/tier1/test_posture_gate_5_step_fail_closed.py::TestStep5PlusBET12Emission` + 1 new `test_bet12_emitter_required` (construction discipline). Full suite 566/566 pass.

**Privacy contract enforced (per `rules/event-payload-classification.md` Rules 2 + 3):** `principal_id` hashed via `f"sha256:{sha256(pid)[:8]}"` byte-identity with kailash-py `format_record_id_for_event`; payload schema is exactly `{bet_id, principal_id_hash, from_level, to_level, days_at_current_posture, authored_count_at_transition}` — no envelope hash, no authored_constraints names, no field names. Defense-in-depth: `TestPrivacyContract::test_payload_fields_are_only_cohort_safe` AST-locks the dataclass field set; `test_emit_signature_only_accepts_cohort_safe_kwargs` AST-locks the `emit()` signature against Rule-3-blocked kwargs (`envelope_hash`, `authored_constraints`, `field_name`, etc.).

**Deferred to T-02-33 (Tier 2 wiring), out of T-02-32 scope:**

- The concrete Phase-01 default sink writing ritual-style Ledger entries with `bet_id="BET-12"` requires `specs/ledger.md` schema disposition (extend `ritual_completion` `ritual_kind` enum vs introduce `posture_transition_cadence` entry type) — that decision lives at Tier 2 wiring time per `rules/specs-authority.md` MUST Rule 5. T-02-32 ships the Protocol-typed sink; T-02-33 ships the concrete `LocalLedgerBET12Sink` + the spec edit.
- `days_at_current_posture` Phase 01 default is 0.0 (callers may omit); Phase 03 Weekly Posture Review ritual computes from PostureStore history. T-02-33 wires the WPR ritual call site; until then the BET dataset honestly records 0.0 entries rather than fabricating values.

**Implements:** BET-12 falsifiability per `briefs/00-phase-01-mvp-scope.md` § Phase 01 invariants #3.

**Source:** Shard 9 § 3 step 3 (`01-analysis/09-authorship-score-implementation.md` § 3.3).

**Action:** `BET12CadenceEmitter` — cohort-level posture-transition emitter; sink Protocol-typed for Phase 02 Foundation Health Heartbeat aggregation per `specs/foundation-health-heartbeat.md`.

**Capacity check:** ~150 LOC load-bearing logic (within ≤500 LOC threshold); 2 invariants (`bet_id` tag canonical via module constant `_BET_ID_CANONICAL` + AST-lock on `emit()` signature; emit on every posture-transition the gate accepts via Step 5+ wiring + `test_failed_gate_does_not_emit_bet12` regression); 1 call-graph hop (PostureGate.request_transition → BET12CadenceEmitter.emit → BET12Sink.write).

**Blocks on:** T-02-31. ✓

**Estimate:** 0.25 session. Actual: ~0.3 session including signature-change patches (41 `request_transition` call sites + `_make_gate` factory).

---

## T-02-33 — Wire envoy/authorship/ (Tier 2) ✅ CLOSED 2026-05-24 (RT-1 + RT-2 convergent)

**Status:** Shipped through 4 merged PRs + 2 consecutive clean /redteam rounds. Wave-2 PostureGate surface (T-02-30/31/32/33) is convergence-clean at `2264ae2`.

**Convergence chain:**

- **PR #23 (origin, merge `641dd2d`)** — Tier 2 wiring + envelope_edit pairing on ratchet-up. 5 commits, 579/579 tests, 8 Tier 2 cases at `tests/tier2/test_posture_gate_wiring.py::TestEnvelopeEditPairingOnRatchetUp`.
- **PR #25 (Shard 1, merge `ebf01f4`)** — closes Round 1 F-1 (MED kwarg type/shape) + F-2 (HIGH mutation invariants) + F-3 (MED defensive guard) + F-4 (HIGH mint-state interpretation) + F-6 (MED audit-only field) + F-002 (LOW unreachable guard). 599/599 tests. Spec edit: `specs/envelope-model.md` § Schema mint-state field-semantics for `metadata.posture_level`.
- **PR #26 (Shard 2, merge `e89914b`)** — F-5 (HIGH) determined FALSE-POSITIVE per `rules/verify-resource-existence.md` MUST-3 (threat target — re-canonicalization path — does not exist in codebase). Ships journal/0023-DISCOVERY + `tests/tier2/test_envelope_hash_mint_time_cached.py` (6 probe-driven tests pinning the single-point-mint-time-hash invariant). 605/605 tests.
- **PR #27 (Shard 3, merge `2264ae2`)** — closes Round 2 R2-F1 (HIGH same-class regression of Round 1 F-3 reintroduced by Shard 1's invariant raises) + R2-F2 (MED Protocol side-effect contract) + R2-F3 (LOW cross-spec drift). 609/609 tests. The R2-F1 fix promotes F-2 mutation invariants from postconditions-of-Step-5a to PRECONDITIONS — on any invariant violation, ZERO Ledger entries land (application-level atomic fail-closed).

**/redteam round-by-round trajectory:**

| Round | HIGH | MED | LOW | Verdict   | Closure                               |
| ----- | ---: | --: | --: | --------- | ------------------------------------- |
| 1     |    3 |   4 |   2 | NOT CLEAN | Shard 1 + Shard 2 + issue #24 (F-001) |
| 2     |    1 |   1 |   1 | NOT CLEAN | Shard 3                               |
| 3     |    0 |   0 |   0 | CLEAN     | (first of 2 consecutive)              |
| 4     |    0 |   0 |   0 | CLEAN     | (convergence MET)                     |

Round 1 audit artifacts committed at `7598578`; Round 2-4 audit artifacts committed at `d780f89`.

**Open follow-up:** GH issue #24 — Phase 03 Ledger transactional / compensating-entry primitive for F-001 transient-failure class (distinct bug class from R2-F1 which was closed in Shard 3 as application-level).

**Original test counts (PR #23):** `tests/tier2/test_posture_gate_wiring.py` 8 cases exercising `PostureGate` against real `EnvoyLedger` + real Ed25519 + real `EnvelopeCompiler` canonical-bytes pipeline. NO mocking. Plus paired envelope_edit pairing on ratchet-up.

**DI design choice (per `journal/0021-DECISION-t-02-33-envelope-edit-pairing-design.md`):** picked option (b) — `envelope` kwarg on `request_transition()` over `_EnvelopeProtocol` DI surface. Keeps PostureGate stateless; envelope is per-transition data; avoids inventing a `_RoleEnvelopeStore` primitive; updates zero existing Tier 1 fixtures structurally (only the 13 ratchet-up tests gain `envelope=_FakePostureCarryingEnvelope()`). Runtime-contract weakness closed by typed `PostureRatchetEnvelopeMissingError` raised at Step 3e when `target > current` and `envelope is None`.

**Acceptance gates per the carry-forward block, all green:**

- (a) Every ratchet-up emits BOTH `posture_change` (Step 5a) AND `envelope_edit` (Step 5b) in append order. Verified at `tests/tier2/test_posture_gate_wiring.py::TestEnvelopeEditPairingOnRatchetUp` × 3 transitions (PSEUDO→TOOL, TOOL→SUPERVISED, multi-step PSEUDO→DELEGATING).
- (b) `envelope_edit` wire shape matches `specs/ledger.md` § envelope_edit lines 107-114 — `schema_version`, `envelope_id`, `prior_version`, `new_version` (= prior_version + 1), `diff_hash` (spec-named, NOT content_hash), `rollback_grace_window_seconds` (24h default), `signed_by="delegation_key"`. Pinned in both Tier 1 (`TestStep5LedgerEntrySchema::test_ledger_content_matches_spec_schema`) and Tier 2 wire-shape assertions.
- (c) Mutated envelope's `metadata.posture_level` reflects new level. Verified via the `_EnvelopeConfigPostureCarrier` adapter's `mutate_for_posture_level()` return value at `tests/tier2/test_posture_gate_wiring.py::TestEnvelopeEditPairingOnRatchetUp::test_envelope_edit_content_hash_changes_on_mutation`.

**Same-shard fix-immediately findings per `rules/autonomous-execution.md` Rule 4 (5 closed in the GREEN BAR commit `fe1b982`):**

1. The new `envelope` kwarg invalidated 13 existing Tier 1 ratchet-up tests (same bug class — all needed the new contract). Fixed all 13 in the same commit (rather than filing follow-up).
2. The `PostureRatchetEnvelopeMissingError` typed-error contract needed Tier 1 coverage too — added `TestStep3eEnvelopeMissingOnRatchetUp` (5 cases) in the same commit.
3. The `TestErrorHierarchy` class needed to enumerate the new error — done in the same commit.
4. The asymmetric pairing on demotion (spec § Ratchet-down) needed a pin — added `TestPostureChangeOnRatchetDownNoEnvelopeEdit` (Tier 2) to lock the asymmetry against future "symmetrize" refactors.
5. The Step 5b code guards `envelope is None` defensively even though Step 3e already raises — closes the typed-delegate-guards-for-None pattern per `rules/zero-tolerance.md` Rule 3a against a future refactor that drops Step 3e.

**Spec deviations acknowledged + closed (per `rules/specs-authority.md` Rule 6):**

- `specs/posture-ladder.md` § Out of scope — envelope_edit deferral bullet REMOVED. Section intro updated to name T-02-33 as the closure. Tier 2 wiring + Tier 1 Step 3e citations added to § Test location.
- `specs/envelope-model.md` § Schema — `metadata.posture_level` field added with canonical PostureLevel enum NAME wire form. Field-semantics block explains cross-runtime byte-identity contract + ratchet-up envelope_edit pairing + asymmetric pairing on demotion.

**Implements:** `specs/posture-ladder.md` § Ratchet-up requirement #3 + `specs/ledger.md` § envelope_edit lines 107-114 + `specs/envelope-model.md` § metadata.posture_level.

**Blocks on:** T-02-30 ✓ (PR #14, recompute_authorship_counters), T-02-31 ✓ (PR #19, PostureGate 5-step gate), T-02-32 ✓ (PR ??, BET12CadenceEmitter). All satisfied.

**Capacity check:** ~110 LOC load-bearing logic added to posture_gate.py (within ≤500 LOC threshold per `rules/autonomous-execution.md` MUST Rule 1); 8 invariants total on PostureGate (was 5; added envelope-version monotonic bump + envelope.metadata.posture_level reflects new level + envelope_edit appended in order AFTER posture_change); 3 call-graph hops unchanged (PostureGate → `_LedgerProtocol.append` × 2 OR PostureGate → `_RevokeHook`; new hop is PostureGate → `_PostureCarryingEnvelope.mutate_for_posture_level` which is a Protocol method, not a new chain).

---

## T-02-34 — Build envoy/shamir/ritual ✅ CLOSED 2026-05-07 (PR #13)

**Status:** Shipped. Coordinator + 5 collaborator Protocols + RitualResult + DistributionChecklist + typed errors landed at PR #13 (commits 573757e + 8cfd5ff + merge 594196f). 38/38 Tier 1 tests green; full suite 383/383 pass.

**Gate-review surfaced findings (resolved in same PR per autonomous-execution.md Rule 4):** C-1 master-key residency (passed `bytearray` directly to kailash, eliminating the `bytes()` boundary copy); H-1 atomic slice-assignment overwrite; H-2 deterministic zero-fill BEFORE entropy-dependent random fill; H-3 `principal_id` hashed at INFO per observability.md Rule 8; rev-2/3 Protocol structural conformance tests; rev-4 ritual-id salt against same-microsecond collision; rev-5 threshold==total_shards edge cases; L-1 test fake uses `secrets.token_bytes(32)`; rev-6 `collections.abc.Awaitable`.

**Deferred to named successor shards (out of T-02-34 scope, documented in PR #13 commit body):**

- H-4 master-key fingerprint binding → T-02-43 (Boundary Conversation S8 wiring) where fingerprint verification is the natural fit
- M-1 channel-adapter user_message encoding → T-02-43
- L-2 binder MUST NOT compute commitments (coordinator should re-derive locally) → T-02-35 prerequisite (see below)
- rev-1 generator returning duplicate shards silently accepted → T-02-37 (real generator wiring)

**Implements:** `specs/shamir-recovery.md`

**Source:** Shard `01-analysis/15-shamir-recovery-implementation.md` § 3 step 1.

**Action:** `ShamirRitualCoordinator` — wraps `kailash.trust.vault.shamir.generate(...)` with the 6-step Phase 01 ritual; **zeroizes master key** after share generation.

**Capacity check:** ~200 LOC; 4 invariants (6-step ritual sequence; share count = 5; threshold = 3; master-key zeroization); 2 call-graph hops.

**Blocks on:** T-01-14 (algorithm_id + Shamir export hooks).

**Estimate:** 0.5 session.

---

## T-02-35 — Build envoy/shamir/paper + commitments + distribution_checklist ✅ CLOSED 2026-05-07 (PR #15)

**Status:** Shipped. `commitments.py` (compute/verify) + `paper.py` (PaperShardCard + PaperShardRenderer) + `distribution_checklist.py` (TrustVaultChecklistPersister) + new `envoy/trust/vault.py` `read_metadata()` / `write_metadata()` API (commits 6ec5fde + b6a5904 + merge f862b29). L-2 Protocol re-architecture landed: `CommitmentBinder.bind_to_genesis(principal_id, commitments) -> Awaitable[None]` — coordinator computes commitments locally; binder is storage-only. 47 new Tier 1 tests; full suite 431/431 pass on shard branch, 451/451 on merged main.

**Gate-review surfaced findings (all resolved in same PR per autonomous-execution.md Rule 4):** H-2 (vault tmpfile bare `open()` bypassed `O_NOFOLLOW` per trust-plane-security MUST Rule 1 — fixed via `os.open(..., O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW, 0o600)` + best-effort orphan-tmp unlink), M-1/M-2 (Unicode confusable + control-char H-06 bypass — three-layer defense added: whitelist regex `^slot-\d+$` + ASCII-only check + substring blacklist; applied at renderer + persister + DistributionChecklist `__post_init__`), M-3 (read_metadata raises documented), L-1 (read_metadata returns deepcopy), reviewer M-1 (DistributionChecklist `__post_init__` validation closes in-memory construction gap).

**H-1 race window (deferred, doc-only fix):** `read_metadata → mutate → write_metadata` cycle has no compare-and-swap; concurrent async tasks can clobber each other's mutations. Phase 02 hardening adds vault-level `update_metadata(callable)` primitive. Phase 01 supported topology: single-process single-task. Documented in `write_metadata` docstring.

**Source:** Shard 15 § 3 steps 2 + 4 + 5.

**Steps:**

1. `envoy/shamir/paper.py` — 24-word paper-card renderer per `specs/shamir-recovery.md` § Card format.
2. `envoy/shamir/commitments.py` — bind shard public commitments to Genesis Record at backup time.
3. `envoy/shamir/distribution_checklist.py` — opaque slot labels in Trust Vault (NOT real names; H-06 fix).

**Capacity check:** ~250 LOC; 4 invariants (24-word format; commitment binding to Genesis; opaque labels; distribution-checklist Phase-01 minimum); 2 call-graph hops.

**Blocks on:** T-02-34.

**Estimate:** 0.5 session.

---

## T-02-36 — Build envoy/shamir/reconstruct (CLI) ✅ CLOSED 2026-05-24 (PR #28)

**Status:** Shipped. `envoy shamir recover` CLI + `envoy.shamir.recover.recover_master_key` primitive + 7 typed recovery errors (`ShamirRecoveryError` base + `ShardChecksumFailedError`, `InsufficientSharesError`, `TooManySharesError`, `CommitmentVerificationFailedError`, `ShardSlotLabelMismatchError`, `ShardPublicCommitmentMissingError`) at merge `9c7c306`. 28 new Tier 1 tests at `tests/tier1/test_shamir_recover_cli.py`. Full suite 637/637 pass.

**Convergence chain:**

- **PR #28 (origin commit `35019b5`, merge `9c7c306`)** — CLI + primitive + 24 Tier 1 tests + spec citation upgrade.
- **Fix commit `47123ae`** — same-shard sweep closing 9 findings from parallel gate-review (reviewer + security-reviewer) + /redteam Round 1: dependency declaration (shamir-mnemonic), error-path observability, Exception base-message hygiene (whitelist tuple leak), `_render_error` assert, DEFAULT_THRESHOLD consolidation, lazy-import reordering, spec accuracy (3 pre-existing unimplemented errors moved to § Out of scope), docstring past-tense fix. 4 new regression tests pin every fix.
- **Doc commit `cba2556`** — Round 2 LOW (docstring drift introduced by `47123ae`'s public/private split): impl docstring now correctly describes the start+error/ok split per `rules/observability.md` MUST Rule 1.

**/redteam round-by-round trajectory:**

| Round | CRIT | HIGH | MED | LOW | Verdict | Closure                                  |
| ----- | ---: | ---: | --: | --: | ------- | ---------------------------------------- |
| 1     |    0 |    0 |   0 |   2 | CLEAN   | F-1 + F-2 closed in fix commit `47123ae` |
| 2     |    0 |    0 |   0 |   1 | CLEAN   | F-1 docstring closed in `cba2556`        |

Convergence MET per `briefs/00-phase-01-mvp-scope.md` § Exit criteria (2 consecutive clean rounds: R1 + R2 both 0 CRIT/HIGH/MED).

**Spec edits acknowledged + closed (per `rules/specs-authority.md` Rule 6):**

- `specs/shamir-recovery.md` § Out of scope — L-03 carry-forward bullet REMOVED (closed by this shard). Added `tests/tier1/test_shamir_recover_cli.py` citation under § Test location.
- `specs/shamir-recovery.md` § Error taxonomy — added `TooManySharesError` row (T-02-36 implementation discovered SLIP-0039's strict-count contract; typed envoy error translates the opaque library `MnemonicError` per `rules/communication.md`).
- `specs/shamir-recovery.md` § Error taxonomy — REMOVED 3 pre-existing rows (`RecoveryRateLimitedError`, `RotationGracePeriodElapsedError`, `CryptoLibAuditMissingError`) per `rules/spec-accuracy.md` MUST Rule 5 + `rules/zero-tolerance.md` Rule 1a (scanner-surface symmetry). Tracked in § Out of scope for Phase-04 hardening.

**Implements:** `specs/shamir-recovery.md` § Recovery flow + L-03 fix (per-card BIP-39 checksum at entry) + counterfeit-shard defense via commitment verification against `Genesis.shard_public_commitments`.

**Blocks on:** T-02-34 ✓ (PR #13, ritual coordinator) + T-02-35 ✓ (PR #15, paper/commitments/distribution_checklist). All satisfied.

**Source:** Shard 15 § 3 step 3.

**Capacity check (actual):** ~470 LOC across recover.py (~340) + cli/{**init**,**main**,main,shamir}.py (~310) + errors.py extension (~110); 3 invariants pinned (commitment verification; threshold reconstruction; CLI surface stability); 2 call-graph hops (CLI → recover_master_key → kailash reconstruct + verify_commitment). Slightly above the 150-LOC estimate due to recovery-side error taxonomy + click group infrastructure, but within shard budget (≤500 LOC) per `rules/autonomous-execution.md` MUST Rule 1.

**Memory hygiene per `rules/trust-plane-security.md` MUST NOT Rule 3:** recovered master-key bytes dropped via `del recovered` in CLI `finally` clause. AST-locked by `TestMemoryHygiene::test_recover_command_dels_recovered_bytes` walking `ast.Try.finalbody` for `ast.Delete` naming `recovered` — refuses a future refactor that drops the `finally`.

**Open follow-up:** T-02-37 (Tier 2 cross-tool interop wiring) — next-in-chain, exercises real `kailash.trust.vault.shamir` + real `python-shamir-mnemonic` end-to-end via the primitive shipped here.

---

## T-02-37 — Wire envoy/shamir/ (Tier 2 + cross-tool interop)

**Action:**

- `tests/tier2/test_shamir_ritual_coordinator_wiring.py` — exercises ritual end-to-end.
- `tests/tier2/test_shamir_paper_renderer.py`.
- `tests/tier2/test_shamir_commitments_bound_to_genesis.py`.
- `tests/tier2/test_trust_store_shamir_master_key_export_import_round_trip.py` — crypto round-trip per `rules/orphan-detection.md` Rule 2a.

**Acceptance:** Green against real `kailash.trust.vault.shamir` + real `python-shamir-mnemonic`. NO mocking.

**Blocks on:** T-02-34 through T-02-36.

**Estimate:** 0.5 session.

**Phase B citation upgrade (per `12-spec-citation-hygiene.md`):** Three `(scheduled in T-02-37)` entries close at this shard's merge:

- `specs/shamir-recovery.md` § Out of scope: 3-of-5 SLIP-0039 reconstruct + vault unlock → upgrade to the Tier-2 wiring test path under § Test location.
- `specs/shamir-recovery.md` § Out of scope: Genesis-Record commitment defeats counterfeit shards → upgrade to the commitments-bound-to-genesis test path.
- `specs/trust-vault.md` § Out of scope: 3-of-5 default reconstruction round-trip → upgrade to the master-key export/import round-trip test path.
  The citation audit `grep -hoE 'tests/[a-z0-9_/]+\.py' specs/shamir-recovery.md specs/trust-vault.md | while read p; do [ -f "$p" ] || echo MISSING; done` MUST exit 0 at this shard's PR merge.

---

## T-02-40 — Build envoy/boundary_conversation/runtime + plan-DAG

**Implements:** `specs/boundary-conversation.md`

**Source:** Shard `01-analysis/08-boundary-conversation-implementation.md` § 3 steps 1-2.

**Action:**

1. `BoundaryConversationRuntime` + Plan DAG — Kaizen L3 `Plan` over S0 → S10; per-state `PlanNode` with attached `Signature`.
2. 9 `Signature` subclasses — one per S1-S9 (structured-output JSON schema).

**Capacity check:** ~400 LOC; 6 invariants (S0→S10 state graph; per-state Signature schema; Plan DAG topology; structured-output JSON validity; Kaizen L3 contract; resume-aware state transitions); 3 call-graph hops.

**Blocks on:** T-01-22 (model router) + T-01-12 (trust store) + T-01-18 (ledger).

**Estimate:** 1 session.

---

## T-02-41 — Build envoy/boundary_conversation/envelope_input_assembler

**Source:** Shard 8 § 3 step 3.

**Action:** `EnvelopeConfigInputAssembler` — accumulates per-state extractions; emits in JCS-canonical-order. Cross-shard with shard 4 (Envelope compiler T-01-10).

**Capacity check:** ~150 LOC; 3 invariants (per-state extraction integrity; JCS-canonical-order; assembler is append-only); 2 call-graph hops.

**Blocks on:** T-02-40 + T-01-10.

**Estimate:** 0.25 session.

---

## T-02-42 — Build envoy/boundary_conversation/ritual_resume

**Source:** Shard 8 § 3 step 4.

**Action:** `RitualResumeCoordinator` — Trust-Vault-backed per-state persistence; `envoy init --resume <ritual_id>`.

**Capacity check:** ~200 LOC; 4 invariants (Trust-Vault encryption per checkpoint; resume from any S0–S10 state; ritual_id stability across restart; Plan DAG resume contract); 3 call-graph hops.

**Blocks on:** T-02-40 + T-01-13 (vault).

**Estimate:** 0.5 session.

---

## T-02-43 — Build envoy/boundary_conversation/{novelty_feedback, post_duress_banner, S7+S8 pause}

**Source:** Shard 8 § 3 steps 5-7.

**Steps:**

1. S7 visible-secret + S8 Shamir pause — `Plan.suspension = SuspensionRecord(reason=ExplicitCancellationReason(...))`. S8 hands off to `ShamirRitualCoordinator` (T-02-34).
2. Novelty feedback gate at S3/S5 — Jaccard portion only (Phase 01); classifier deferred Phase 04.
3. Post-duress banner gate — at S0 entry, query shadow segment; render banner if unread duress event.

**Capacity check:** ~280 LOC; 5 invariants (Plan-suspension contract; Shamir handoff atomic; Jaccard threshold deterministic; shadow-segment read; banner rendered before any S0 user input); 3 call-graph hops.

**Blocks on:** T-02-40 + T-02-34 (Shamir).

**Estimate:** 0.75 session.

---

## T-02-44 — Wire envoy/boundary_conversation/ (Tier 2)

**Action:**

- `tests/tier2/test_boundary_conversation_runtime_wiring.py`.
- `tests/tier2/test_resume_from_each_state.py` — every S0–S10 state resumable.
- `tests/tier2/test_envelope_compiler_monotonic_tightening_at_compile.py`.
- `tests/tier2/test_post_duress_banner.py`.
- `tests/tier2/test_visible_secret_render_check.py`.

**Acceptance:** Green against real model-router + Trust + Ledger. NO mocking.

**Blocks on:** T-02-40 through T-02-43.

**Estimate:** 0.75 session.

---

## T-02-45 — Acceptance EC-1 Tier 3: Boundary Conversation N=3 ≤25min

**Implements:** EC-1 acceptance gate per `02-plans/02-test-strategy.md`; disposition #3 (25min ship gate, 15min target) per `journal/0005`.

**Action:**

- `tests/tier3/test_boundary_conversation_full_path.py` — N=3 first-time-user sessions ≤25min produce parseable EnvelopeConfig.
- `tests/tier3/test_boundary_conversation_minimum_path.py` — 8min minimum-path.
- Surface 15min target outcome in /codify (UX evaluation, not /redteam pass-fail).

**Acceptance:** All N=3 sessions complete ≤25min wall-clock; produce parseable EnvelopeConfig; Ledger entries signed correctly.

**Blocks on:** T-02-40 through T-02-44 + every Wave 1 todo.

**Estimate:** 0.5 session (test suite; not the impl).

---

## Wave 2 milestone gate

Per `02-plans/01-build-sequence.md` § 3 Milestone 2:

- Boundary Conversation EC-1 acceptance green.
- Resume-from-each-state green.
- Shamir 10-combo reconstruct test passes (EC-5 partial; full coverage in `08-tests-tier3-acceptance.md`).

**Wall-clock estimate:** ~3 sessions (sequenced inside wave: Authorship 0.75 || Shamir 1.5 → Boundary 2.5).

---

## Cross-references

- Build sequence: `02-plans/01-build-sequence.md` § Wave 2
- Primitive shards: `01-analysis/{08,09,15}-*-implementation.md`
- Boundary timing disposition: `journal/0005-DECISION-todos-opening-dispositions.md` § Disposition #3
- Wave 1 dependencies: `01-wave-1-foundation.md`
