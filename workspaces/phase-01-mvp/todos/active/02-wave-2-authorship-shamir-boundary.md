# 02 — Wave 2: Authorship + Shamir + Boundary Conversation

**Purpose:** Build the 3 Wave-2 primitives in dependency order. Authorship and Shamir are independent within the wave; Boundary Conversation depends on Shamir's S8 backup-pause integration. Wave 2 converges on the EC-1 acceptance gate (Boundary Conversation N=3 ≤25min).

**Source authority:** `02-plans/01-build-sequence.md` § Wave 2 + shards 8 / 9 / 15.

**Depends on:** Wave 1 (`01-wave-1-foundation.md`) fully converged.

---

## T-02-30 — Build envoy/authorship/score (pure function)

**Implements:** `specs/authorship-score.md` § Score recompute

**Source:** Shard `01-analysis/09-authorship-score-implementation.md` § 3 step 1.

**Action:** `AuthorshipScore.recompute(envelope, ledger_slice) -> int` — pure deterministic re-derivation; 5-dimension canonical iteration order. Cross-shard JCS-canonical-order invariant for shard 4 (Envelope compiler) — surfaced in /analyze wave-B.

**Tests added:** `tests/tier1/test_authorship_score_recompute_pure.py` — deterministic replay across same envelope+slice.

**Capacity check:** ~120 LOC pure function; 3 invariants (5-dim canonical order; JCS sort discipline; deterministic replay); 1 call-graph hop.

**Estimate:** 0.25 session.

---

## T-02-31 — Build envoy/authorship/posture_gate

**Implements:** `specs/posture-ladder.md` + `specs/authorship-score.md` § Posture gate

**Source:** Shard 9 § 3 step 2.

**Action:** `PostureGate.request_transition()` — 5-step fail-closed enforcement; cascade-revoke hook on demotion (calls into envoy/trust/cascade T-01-14).

**Tests added:** `tests/tier1/test_posture_gate_5_step_fail_closed.py`.

**Capacity check:** ~150 LOC; 5 invariants (5-step gate sequence; fail-closed default; cascade-on-demotion; signed posture_change Ledger entry; posture-ratchet enforcement); 3 call-graph hops.

**Blocks on:** T-02-30 + T-01-14 + T-01-18 (Ledger).

**Estimate:** 0.5 session.

---

## T-02-32 — Build envoy/authorship/bet12_emitter

**Implements:** BET-12 falsifiability per `briefs/00-phase-01-mvp-scope.md` § Phase 01 invariants #3.

**Source:** Shard 9 § 3 step 3.

**Action:** `BET12CadenceEmitter` — cohort-level posture-transition Ledger emit (Phase 01 sink: local-only `ritual_completion` entries with `bet_id="BET-12"`).

**Capacity check:** ~80 LOC; 2 invariants (bet_id tag canonical; emit on every posture-transition); 1 call-graph hop.

**Blocks on:** T-02-31.

**Estimate:** 0.25 session.

---

## T-02-33 — Wire envoy/authorship/ (Tier 2)

**Action:** `tests/tier2/test_posture_gate_wiring.py` — exercises `PostureGate` against real Trust store + Ledger; asserts `posture_change` entry signed by Genesis key.

**Acceptance:** Green against real SQLite + real Ed25519. NO mocking.

**Blocks on:** T-02-30 through T-02-32.

**Estimate:** 0.25 session.

---

## T-02-34 — Build envoy/shamir/ritual

**Implements:** `specs/shamir-recovery.md`

**Source:** Shard `01-analysis/15-shamir-recovery-implementation.md` § 3 step 1.

**Action:** `ShamirRitualCoordinator` — wraps `kailash.trust.vault.shamir.generate(...)` with the 6-step Phase 01 ritual; **zeroizes master key** after share generation.

**Capacity check:** ~200 LOC; 4 invariants (6-step ritual sequence; share count = 5; threshold = 3; master-key zeroization); 2 call-graph hops.

**Blocks on:** T-01-14 (algorithm_id + Shamir export hooks).

**Estimate:** 0.5 session.

---

## T-02-35 — Build envoy/shamir/paper + commitments + distribution_checklist

**Source:** Shard 15 § 3 steps 2 + 4 + 5.

**Steps:**

1. `envoy/shamir/paper.py` — 24-word paper-card renderer per `specs/shamir-recovery.md` § Card format.
2. `envoy/shamir/commitments.py` — bind shard public commitments to Genesis Record at backup time.
3. `envoy/shamir/distribution_checklist.py` — opaque slot labels in Trust Vault (NOT real names; H-06 fix).

**Capacity check:** ~250 LOC; 4 invariants (24-word format; commitment binding to Genesis; opaque labels; distribution-checklist Phase-01 minimum); 2 call-graph hops.

**Blocks on:** T-02-34.

**Estimate:** 0.5 session.

---

## T-02-36 — Build envoy/shamir/reconstruct (CLI)

**Source:** Shard 15 § 3 step 3.

**Action:** `envoy shamir recover` CLI; commitment-verify against `Genesis.shard_public_commitments`.

**Capacity check:** ~150 LOC; 3 invariants (commitment verification; threshold reconstruction; CLI surface stability); 2 call-graph hops.

**Blocks on:** T-02-34 + T-02-35.

**Estimate:** 0.5 session.

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
