# mvp-build-sequence

## Purpose

The Phase 01 MVP build order, integration-test milestones, side-channel components, per-primitive scaffold milestones, and acceptance gate progression. This spec is the authoritative reference for Phase 01 implementation planning; the analysis-time plan `workspaces/phase-01-mvp/02-plans/01-build-sequence.md` is the temporal artifact (the plan as written at /todos time), this spec is the canonical contract that survives across sessions.

The build sequence is dependency-driven, not schedule-driven. Per `rules/orphan-detection.md` MUST Rule 1, every facade-shape attribute MUST have a hot-path call site within 5 commits — every primitive lands WITH at least one consumer's wiring test in the same PR. The wave structure exists to satisfy this constraint, NOT to fit a calendar.

## Provenance

- **Source plan:** `workspaces/phase-01-mvp/02-plans/01-build-sequence.md` (shard 20 deliverable; topological sort + per-primitive scaffold + integration-test milestones + per-shard implementation-cycle estimates).
- **Source analysis docs:** `workspaces/phase-01-mvp/01-analysis/04-envelope-compiler-implementation.md` through `workspaces/phase-01-mvp/01-analysis/19-pipx-distribution-architecture.md` (16 primitive deep-dive shards).
- **Inheritance authority:** `workspaces/phase-01-mvp/01-analysis/00-inheritance-from-phase-00.md` § 5.4 ("Identified via gap analysis in shard 12 ... `specs/mvp-build-sequence.md` (probable) — captures Phase 01 build order as authoritative reference").
- **Acceptance gates:** `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` (EC-1 through EC-9 ship predicate); `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 5 (sequencing groups A–E).
- **Capacity discipline:** `rules/autonomous-execution.md` § Per-Session Capacity Budget (≤500 LOC load-bearing logic, ≤5–10 simultaneous invariants, ≤3–4 call-graph hops per shard).

## Build order

The dependency graph collapsed onto IMPLEMENTATION order. Wave assignment is forced by `rules/orphan-detection.md` MUST Rule 1; sequencing inside a wave is forced by per-primitive deps where they exist (e.g., Boundary Conversation depends on Shamir within Wave 2).

```
Wave 1 (no inter-primitive deps; parallelizable across worktrees):
  ├── envoy.envelope.compiler         [shard 4]
  ├── envoy.trust.store               [shard 5]
  ├── envoy.ledger                    [shard 6]
  ├── envoy.model.router              [shard 13]
  ├── envoy.connection_vault          [shard 14]
  ├── envoy.runtime (abstract stub)   [shard 18]
  └── envoy.heartbeat (4 stubs only)  [shard 17, de-scoped Phase 02]

Wave 2 (depends on Wave 1):
  ├── envoy.authorship                [shard 9 — needs Trust store + Ledger]
  ├── envoy.shamir                    [shard 15 — needs Trust store hooks]
  └── envoy.boundary_conversation     [shard 8 — needs Envelope + Ledger + Model + Trust + Shamir]

Wave 3 (depends on Wave 1 + 2):
  ├── envoy.grant_moment              [shard 10 — needs Envelope + Ledger + Trust + Boundary pause]
  └── envoy.budget                    [shard 12 — needs Grant Moment dispatch + Ledger + Envelope]

Wave 4 (depends on Wave 1 + 2 + 3):
  ├── envoy.channels                  [shard 16 — needs Connection Vault + Boundary + Grant Moment + Ledger + Trust]
  └── envoy.daily_digest              [shard 11 — needs Ledger + Channels + Model + Trust]

Wave 5 (depends on every primitive):
  ├── envoy.cli                       [shard 19 — 11 subcommands route every primitive]
  └── pipx packaging + NOTICES        [shard 19]

Side-channel (Wave 1 onward, separate repo per specs/independent-verifier.md):
  └── envoy-ledger-verifier           [shard 7 — separate codebase per EC-9; MUST NOT share source]
```

### Critical path

**Trust store → Boundary Conversation → Grant Moment → Channel adapters → Daily Digest → CLI → pipx**

Length: 7 sequential wave-positions. Every other primitive sits on a shorter chain or in parallel with this one. The critical path is the EC-1 + EC-2 + EC-3 + EC-7 + EC-8 acceptance-gate spine — failure to ship any link delays Phase 01 release. `envoy-ledger-verifier` (shard 7) runs in a parallel separate-codebase track and gates EC-4 + EC-9; it is NOT on the critical path because its codebase can develop concurrently with the producer.

### Wave boundary discipline

Per `rules/orphan-detection.md` MUST Rule 1, every Wave-N primitive's PR includes the Tier 2 wiring test from a Wave-N-or-later consumer. Wave-N+1 launch is gated on Wave-N's wiring tests being green per integration-test milestones below.

## Out-of-band components

### envoy-ledger-verifier (separate repo)

The Independent Ledger Verifier ships in `terrene-foundation/envoy-ledger-verifier` — a separate Foundation-stewarded repo with distinct codebase, license header, contributor list, and CI. Per `specs/independent-verifier.md` § Provenance:

- The verifier is a Phase 01 deliverable that gates EC-4 + EC-9 (NON-DEGRADABLE per `02-mvp-objectives.md` § 5).
- Source-isolation is the load-bearing structural property — the verifier MUST NOT import any `envoy.ledger.*` symbol; it MUST re-implement canonical-JSON parsing, hash-chain walking, and Ed25519 verification independently.
- Phase 01 ships Python REQUIRED (`envoy-ledger-verify` PyPI); Rust OPTIONAL but RECOMMENDED for the strongest cross-language source-isolation proof.
- The verifier's CI runs against producer-generated fixtures committed to the verifier repo as static artifacts — NOT pulled at CI time from a producer image, NOT generated on the verifier CI runner.

**Bootstrap sequence:** the verifier repo bootstraps independently of Wave 1 — it can begin development as soon as `specs/independent-verifier.md` is frozen. Estimated 2 sessions parallel to Waves 1–3. Phase 01 release is gated on the verifier's mutation battery passing against the producer's first 1000-entry Ledger export.

### Foundation Health Heartbeat (de-scoped to stubs)

Per shard 17 DECISION (recorded in `workspaces/phase-01-mvp/01-analysis/22-spec-gap-analysis.md` § 2 row 17), the Foundation Health Heartbeat infrastructure is DE-SCOPED to Phase 02 entry. Phase 01 ships ~100 LOC of stubs only:

- Consent-ledger entry type for `heartbeat_consent_granted` / `heartbeat_consent_revoked`.
- `DuressFlagLeakageRefusedError` typed error.
- 21-flag schema validator.
- 21 no-op emit hooks (each raises `PhaseDeferredError("Heartbeat deferred to Phase 02 entry per de-scope #2")`).

**Phase 02 entry trigger:** stand up OHTTP Key Configuration Server + Relay + STAR/Prio aggregator BEFORE consuming Heartbeat measurements for BET-8 / BET-3 / BET-12. Cost: 2–3 sessions of Foundation-ops work (per `22-spec-gap-analysis.md` § 8 item 2).

## Per-primitive scaffold milestone

Each primitive's scaffold step list, condensed from `02-plans/01-build-sequence.md` § 2. Estimates in autonomous-execution sessions per `rules/autonomous-execution.md` (NEVER human-days).

### Wave 1

| Primitive                             | Steps                                                                                                                                                                                                                                                                                                                                                                              | Estimate     |
| ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| **envoy.envelope.compiler** (shard 4) | (1) Skeleton + 24 typed errors. (2) JCS+NFC canonical_bytes pipeline. (3) `compile()` over `kailash.trust.pact.envelopes`; Envoy-superset fold-back. (4) Template-resolver stub (Foundation Library deferred Phase 02). (5) Tier 2 wiring `test_envelope_compiler_wiring.py`.                                                                                                      | 1 session    |
| **envoy.trust.store** (shard 5)       | (1) Adapter + principal-id keying + `PrincipalRequiredError`. (2) `SqliteTrustStore` + `SQLitePostureStore` composition; Genesis seed; record_delegation. (3) AES-256-GCM Trust Vault container; Argon2id + Secure-Enclave/TPM-bound. (4) Cascade revocation glue + `verify_cascade_complete`. (5) Algorithm-identifier helper + Shamir export hooks. (6) Tier 2 wiring (8 tests). | 2 sessions   |
| **envoy.ledger** (shard 6)            | (1) 35 dataclasses + 8 typed errors + EntryEnvelope. (2) Canonical-JSON + HashChainBuilder. (3) `EnvoyLedger.append()` facade + atomic transaction (post-#707/#711). (4) HeadCommitment monotonic guard + HaltedByRollback. (5) Two-phase signing + 30-day TTL orphan resolution. (6) Export CLI for shard 7 verifier. (7) Tier 2 wiring (11 tests).                               | 2 sessions   |
| **envoy.model.router** (shard 13)     | (1) BYOM picker + .env writer; secrets via Connection Vault. (2) `EnvoyModelRouter` over `LlmClient.from_env()`. (3) `EnvoyProviderRiskAnnotator`. (4) Phase 01 minimum response-filter pipeline. (5) Tier 2 wiring (real Ollama in CI; real Claude/GPT in staging).                                                                                                               | 1 session    |
| **envoy.connection_vault** (shard 14) | (1) Adapter + 11-field schema via `keyring.set_password()`. (2) Per-principal isolation + envelope-scope enforcement. (3) `expires_at` + `usage_counter` enforcement. (4) `.env` first-run import path. (5) Tier 2 wiring against real macOS Keychain / Linux Secret Service / Windows Credential Manager.                                                                         | 1 session    |
| **envoy.runtime** (shard 18)          | (1) Abstract Python ABC matching `specs/runtime-abstraction.md`. (2) `kailash_py` adapter (sole Phase 01 backend). (3) Feature-flagged `kailash_rs_bindings` slot raising `RuntimeBackendNotWired`.                                                                                                                                                                                | 0.5 session  |
| **envoy.heartbeat** (shard 17)        | (1) 4 module stubs each raising `PhaseDeferredError`; consent-ledger entry types; 21-flag schema validator; 21 no-op emit hooks.                                                                                                                                                                                                                                                   | 0.25 session |

### Wave 2

| Primitive                                 | Steps                                                                                                                                                                                                                                                                                                                                                                                                                      | Estimate   |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| **envoy.authorship** (shard 9)            | (1) `AuthorshipScore.recompute()` deterministic re-derivation; 5-dim canonical iteration. (2) `PostureGate.request_transition()` 5-step fail-closed enforcement; cascade-revoke on demotion. (3) `BET12CadenceEmitter` local-only Phase 01 sink. (4) Tier 2 wiring against real Trust store + Ledger.                                                                                                                      | 1 session  |
| **envoy.shamir** (shard 15)               | (1) `ShamirRitualCoordinator` over `kailash.trust.vault.shamir.generate(...)`; 6-step ritual; zeroize. (2) `envoy.shamir.paper` 24-word card renderer. (3) `envoy shamir recover` CLI; commitment-verify against Genesis. (4) Bind shard public commitments to Genesis at backup. (5) Distribution checklist with opaque slot labels (H-06 fix). (6) Tier 2 wiring: all C(5,3)=10 share combinations + cross-tool interop. | 1 session  |
| **envoy.boundary_conversation** (shard 8) | (1) `BoundaryConversationRuntime` + Plan DAG over S0→S10. (2) 9 `Signature` subclasses (S1-S9 structured-output). (3) `EnvelopeConfigInputAssembler`. (4) `RitualResumeCoordinator` Trust-Vault-backed. (5) S7 visible-secret + S8 Shamir pause via `Plan.suspension`. (6) Novelty feedback gate at S3/S5. (7) Post-duress banner gate at S0 entry. (8) Tier 2 wiring + Tier 3 EC-1 acceptance.                            | 3 sessions |

### Wave 3

| Primitive                         | Steps                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Estimate     |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| **envoy.grant_moment** (shard 10) | (1) M0→M4 state machine. (2) `SignedConsentBuilder` 3-artifact wire (per `22-spec-gap-analysis.md` § 3.5). (3) 3 `ResolutionShape` for EC-2. (4) `OutOfEnvelopeDetector` interceptor. (5) `ChannelHandoff.dispatch()` + primary-channel binding check. (6) `CascadeRevocationOrchestrator`. (7) `PlanSuspensionBridge` (typed-event channel between Boundary + Grant). (8) `NoveltyClassifier`. (9) 10 typed errors. (10) Tier 2 wiring + Tier 3 EC-2 acceptance.       | 2 sessions   |
| **envoy.budget** (shard 12)       | (1) `MultiWindowBudget` 5-window-per-ceiling. (2) `EnvoyBudgetOrchestrator` facade. (3) `ThresholdDispatcher` async queue (collect-under-lock, dispatch-outside-lock). (4) `BudgetResetScheduler` (Phase 01: UTC; Phase 02 timezone fix per `22-spec-gap-analysis.md` § 4 if Option A selected at shard 25). (5) `AnomalyDetector`. (6) `LedgerEmitter` single-point filter. (7) 7 typed errors. (8) Tier 2 wiring of threshold-fire → Grant Moment → resolution chain. | 1.5 sessions |

### Wave 4

| Primitive                         | Steps                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | Estimate   |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| **envoy.channels** (shard 16)     | (1) `ChannelAdapter` ABC + `InboundMessage` envelope + 11 typed errors. (2) `CLIChannelAdapter` + `WebChannelAdapter` (localhost + Origin/Host allowlist post-#673). (3) `TelegramChannelAdapter` + `SlackChannelAdapter` + `DiscordChannelAdapter` (clean). (4) `WhatsAppChannelAdapter` + `IMessageChannelAdapter` + `SignalChannelAdapter` (caveated; cohort-driven de-scope #1 candidate). (5) `InboundRouter` async fan-in. (6) `GrantMomentRenderer` per channel. (7) `PerChannelRateLimiter`. (8) `CredentialResolver` startup-time. (9) Tier 2 wiring per channel (9 files). (10) Tier 3 EC-7 acceptance. | 3 sessions |
| **envoy.daily_digest** (shard 11) | (1) `DailyDigestService` + `DigestScheduler` (apscheduler CronTrigger). (2) `LedgerAggregator` reads. (3) `DigestRenderer` (DigestPayload schema/1.0). (4) `PerChannelFanout` with fault isolation. (5) `BackfillTracker` + `PauseDisableState` + `LowEngagementTracker` Trust-store-backed. (6) `DuressBannerReader` primary-channel-only. (7) 5 typed errors + `envoy digest` CLI. (8) Tier 2 wiring + Tier 3 EC-3 acceptance.                                                                                                                                                                                  | 2 sessions |

### Wave 5

| Primitive                       | Steps                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | Estimate  |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| **envoy.cli + pipx** (shard 19) | (1) 11 subcommands per shard 19 § 3.4 (canonical): `init`, `chat`, `ledger {export}`, `shamir {backup,recover}`, `digest {today,pause,resume,schedule}`, `grant`, `posture`, `connection {add,list,remove}`, `model`, `version`; Phase 02 stubs (`upgrade`, `uninstall --destroy-vault`). (Carry-forward R1-M-01 disposition per `workspaces/phase-01-mvp/04-validate/round-4-implementation-comprehensive.md` § 4: shard 19 § 3.4 is canonical; this row reconciled accordingly. `envoy ledger verify` lives in the separate `envoy-ledger-verifier` repo per EC-9 — NOT shipped in `envoy-agent`.) (2) `pyproject.toml` deps (`kailash[shamir,nexus,kaizen]>=2.13.4`, `keyring>=24.0`, `python-dotenv>=1.0`, `python-telegram-bot` (LGPL-3.0+), `slack-sdk`, `discord.py`, `apscheduler`). (3) `NOTICES` (LGPL-3.0+ disclosure; MIT keyring; Apache 2.0 kailash family). (4) Cross-OS packaging tests (macOS full / Linux desktop-env / Windows x86_64; ARM64 Phase 02). | 1 session |

### Side-channel

| Primitive                           | Steps                                                                                                                                                                                                                                                                                                                                                                                                                                         | Estimate   |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| **envoy-ledger-verifier** (shard 7) | (1) Repo bootstrap (separate codebase per `specs/independent-verifier.md`). (2) Verify protocol re-implementing chain-walk + Ed25519 + canonical-JSON byte-comparison; different agent (Python first; Rust sibling stretch per `02-mvp-objectives.md` EC-9). (3) Trust-anchor option C with first-verification self-anchoring. (4) Tier 2 + Tier 3 mutation battery (5 classes × 5 buckets per `specs/independent-verifier.md` § Algorithms). | 2 sessions |

### Total budget

Sequential lower bound: ~24 sessions. With worktree isolation per `rules/agents.md` § "Worktree Isolation for Compiling Agents" and parallel ownership per `rules/agents.md` § "Parallel-Worktree Package Ownership Coordination", wall-clock estimate is ~11 orchestrator sessions. Consistent with the 8–12 session Phase 01 estimate in thesis §3.1.

## Integration-test milestones

Global checkpoints; each binds the cumulative wave's wiring tests AND adds a cross-primitive end-to-end gate. Convergence at each milestone gates the next wave's launch.

### Milestone 1 — Wave 1 lands (foundation primitives wired)

Trigger: every Wave 1 primitive's Tier 2 wiring test green. Add gate:

- `tests/e2e/test_envoy_ledger_cross_os_byte_identity.py` — 3-OS matrix produces byte-identical canonical export.
- `tests/integration/test_envelope_compiler_intersect_through_kailash_py.py` — round-trip with upstream `intersect_envelopes` byte-equal.
- `tests/integration/test_trust_store_adapter_genesis_round_trip.py` — Genesis seeded; verified by `verify_signature`.

Convergence: all green = Wave 2 may launch.

### Milestone 2 — Wave 2 lands (Boundary Conversation EC-1 gate)

Trigger: shard 8 + 9 + 15 wiring tests green.

- `tests/e2e/test_boundary_conversation_full_path.py` — N=3 first-time-user sessions ≤25 min produce parseable EnvelopeConfig (**EC-1 acceptance**).
- `tests/integration/test_resume_from_each_state.py` — every S0–S10 state resumable.
- Shamir 10-combo reconstruct test passes (**EC-5 partial**).

Convergence: EC-1 met, EC-5 partial = Wave 3 may launch.

### Milestone 3 — Wave 3 lands (Grant Moment EC-2 gate)

Trigger: shard 10 + 12 wiring tests green.

- All 3 resolution shapes (Approve / Decline / ApproveWithModification) execute end-to-end (**EC-2 acceptance**).
- Cascade revocation reaches every descendant in 3-deep delegation tree.
- `tests/e2e/test_envoy_ledger_tampering_battery.py` — verifier (shard 7) detects every tampering form (**EC-4 acceptance**).
- `tests/e2e/test_envoy_ledger_independent_verifier_ec9.py` — separate-codebase verifier passes (**EC-9 acceptance**).

Convergence: EC-2 + EC-4 + EC-9 met = Wave 4 may launch.

### Milestone 4 — Wave 4 lands (channel + digest EC-3, EC-7, EC-8 gates)

Trigger: shard 11 + 16 wiring tests green.

- **EC-3:** scheduled Daily Digest fires for ≥7 consecutive days across configured channels.
- **EC-7:** N=3 first-time-user sessions per channel × 8 channels = 24 successful onboardings (or 5 if cohort-driven de-scope #1 invoked per `22-spec-gap-analysis.md` § 3.7).
- **EC-8:** 7-day operating window across ≥4 of 8 channels with cross-channel state-equivalence test running daily; cascade revocation of Day-1 grant correctly revokes Day-6 child grant initiated from a different channel.

Convergence: EC-3 + EC-7 + EC-8 met = Wave 5 may launch.

### Milestone 5 — Wave 5 lands (release-readiness)

Trigger: shard 19 packaging green.

- `pipx install envoy-agent` works on macOS / Linux desktop-env / Windows x86_64.
- 7 of 10 canonical CLI subcommands functional in Phase 01: `version`, `posture`, `connection`, `model`, `shamir`, `digest`, and `ledger {export}` — the 6 whose backing state is process-independent, plus `ledger export`, which the durable-ledger workstream (file-backed `SqliteAuditStore` + OS-keychain signing key) made buildable as a one-shot CLI. The remaining 3 (`init`, `chat`, `grant`) stay in Phase 02; they share one blocker class (no durable pending-grant / long-running-session substrate in Phase 01) — see Phase 02 hooks item 9. (`envoy ledger verify` is the separate `envoy-ledger-verifier` repo per EC-9, not counted in the 10.) Disposition + verified evidence: `workspaces/phase-01-mvp/journal/0048-DECISION-f5.2-closed-6of10-phase01-cli-ceiling.md` (6/10 ceiling) + `workspaces/phase-01-mvp/journal/0049-DECISION-c-ledger-export-delivered-7of10.md` (ledger export delivered → 7/10).
- `NOTICES` correct; LGPL-3.0+ python-telegram-bot disclosure present.
- All 9 ECs met.
- 2 consecutive `/redteam` rounds at 0 CRIT + 0 HIGH (**EC-6 acceptance**).

Convergence: Phase 01 ships.

## Phase 02 hooks

Items that Phase 01 ships as stubs OR pre-declared deferrals; Phase 02 entry consumes these as work items.

1. **Foundation Health Heartbeat infrastructure.** Phase 01 ships ~100 LOC stubs (4 modules raising `PhaseDeferredError`); Phase 02 stands up OHTTP Key Configuration Server + Relay + STAR/Prio aggregator before consuming Heartbeat measurements. Cost: 2–3 sessions.
2. **kailash-rs-bindings runtime adapter.** Phase 01 ships feature-flagged empty module raising `RuntimeBackendNotWired` (per shard 18 step 3). Phase 02 wires the Rust binding adapter; runs N1–N6 byte-identical + E1–E7 conformance vectors against BOTH `kailash-py` AND `kailash-rs-bindings` runtimes (BET-6 acceptance per `specs/runtime-abstraction.md` § Security gates per phase row "Phase 02").
3. **iOS / Android Connection Vault.** Phase 01 ships macOS Keychain / Linux Secret Service / Windows Credential Manager only (per shard 14 step 5). Phase 02 adds mobile platforms via `keychain` / `Keystore` native bindings.
4. **iMessage native + Signal Path A.** Phase 01 ships Path B (Group Link, weaker UX) for Signal; iMessage requires user-owned Mac + BlueBubbles bridge. Cohort-driven de-scope #1 at Phase 01 EC-7 may drop both, leaving 5 channels (per `22-spec-gap-analysis.md` § 3.7). Phase 02+ adds iMessage native + Signal Path A.
5. **A2A primitives.** Phase 01 ships single-principal binding check only; channel adapters MUST raise `PrincipalNotFoundError` on mismatch (per `22-spec-gap-analysis.md` § 3.8). Phase 03 wires `kailash.eatp.A2A.verify(message)` for cross-principal dual-signed actions.
6. **Foundation key registry for verifier trust-anchor.** Phase 01 ships option C (out-of-band file). Phase 02 adds `--trust-anchor https://terrene.foundation/registry/<principal_id>.json` (per `specs/independent-verifier.md` § "Open questions" item 1).
7. **Verifier Rust variant.** Phase 01 ships Python REQUIRED + Rust OPTIONAL. Phase 02 makes Rust MANDATORY for the cross-language source-isolation proof (per `specs/independent-verifier.md` § Provenance).
8. **Phase 02 binary distribution + N=3 mirror layer.** Phase 01 ships PyPI only via `pipx install envoy-agent`; Phase 02 adds binary distribution with N=3 mirror coverage, key rotation, reproducible builds (per shard 19 row "Phase 02+ track" in `22-spec-gap-analysis.md`).
9. **Process-independent CLI substrate for `init` / `chat` / `grant`.** Phase 01 ships 7 of 10 canonical subcommands. The durable-ledger workstream (shards A–C) closed the `ledger export` blocker: it wired the file-backed `SqliteAuditStore` + an OS-keychain-durable Ed25519 signing key into the production ledger (`envoy/daily_digest/bootstrap.py` now opens the durable ledger via `open_durable_ledger` + `load_or_create_ledger_key_manager`; `envoy ledger export` reads the SAME ledger cross-process and writes the verifier bundle). The remaining 3 share ONE blocker class: no process-independent persistent substrate + no long-running runtime/session model in Phase 01. `grant` needs a durable pending-grant projection (Phase 01 keeps in-flight grants only in `EnvoyGrantMomentRuntime._inflight` + an event-loop-bound `asyncio.Future`, explicitly "not persisted across restarts" per `envoy/grant_moment/runtime.py:392-401`) AND a long-running session model (`envoy.runtime.session.SessionRouter` is unbuilt; the runtime is never instantiated outside tests). `init` / `chat` additionally need the Boundary-Conversation bootstrap + production `CommitmentBinder` (F21). **First unblock (DELIVERED): the durable `SqliteAuditStore` + keychain-key wiring that made `ledger export` buildable — the same durable substrate the pending-grant TrustVault sub-store builds on.** Remaining cost: multi-shard (pending-grant TrustVault sub-store → SessionRouter/session model → BC bootstrap). Buildability disposition + verified evidence: `workspaces/phase-01-mvp/journal/0048-DECISION-f5.2-closed-6of10-phase01-cli-ceiling.md` (6/10 ceiling) + `workspaces/phase-01-mvp/journal/0049-DECISION-c-ledger-export-delivered-7of10.md` (ledger export → 7/10).

## Open questions

1. **Cohort-driven de-scope #1 trigger criteria.** Phase 01 ships ALL 8 channel adapters; runtime cohort-driven decision drops iMessage + Signal if EC-7 cohort fails (N=3 first-time-user sessions on iMessage and on Signal each fail to complete EC-1 within 25 minutes). The decision is NOT a Phase 01 architecture-time decision per `22-spec-gap-analysis.md` § 3.7. The trigger criteria are pre-declared but not yet measured against real cohort data.
2. **Timezone basis disposition.** Per `22-spec-gap-analysis.md` § 4 — the consolidated HIGH escalation across shards 11 + 12. Decision deferred to human at /analyze closure (shard 25). If human selects **Option A** (UTC-only, 0 sessions): Phase 01 ships UTC-default; per-shard Tier 2 tests use UTC fixtures; EC-3 acceptance asserted as "scheduled hour fires for 7 consecutive days" without the local-morning qualifier; Phase 02 carries the user-local-time fix (~3 sessions of MUST Rule 5b sweep). If human selects **Option B** (IANA timezone field, ~3 sessions): adds `per_day_ceiling_timezone` to `specs/envelope-model.md` § Financial dimension AND `digest_schedule_timezone` to `specs/daily-digest.md` § Schedule; Boundary Conversation collects user's IANA timezone at S6.
3. **`specs/_index.md` sync timing for additive specs.** This spec and `specs/independent-verifier.md` are added to `specs/_index.md` as a manifest update (NOT a spec edit; per `rules/specs-authority.md` MUST Rule 5b, the `_index.md` is a manifest, not a spec, so adding rows does not trigger sibling re-derivation).
4. **Verifier repo bootstrap timing.** Side-channel work begins as soon as `specs/independent-verifier.md` is frozen. Open question: does the verifier repo bootstrap during Wave 1 (parallel) or wait until Wave 1 has produced a stable bundle wire format? Phase 01 disposition (this spec): bootstrap during Wave 1 against the bundle wire format declared in `specs/independent-verifier.md` § Schema; iterate if shard 6 produces wire-format adjustments.

## Cross-references

- **specs/independent-verifier.md** — the verifier side-channel component; gates EC-4 + EC-9.
- **specs/ledger.md** — producer side; the canonical chain shape this build sequence delivers.
- **specs/envelope-model.md** — Wave 1 envelope compiler dependency.
- **specs/trust-lineage.md** — Wave 1 trust store dependency.
- **specs/boundary-conversation.md** — Wave 2 most-integrated primitive (EC-1 gate).
- **specs/grant-moment.md** — Wave 3 EC-2 gate.
- **specs/budget-tracker.md** — Wave 3 budget primitive.
- **specs/channel-adapters.md** — Wave 4 EC-7 + EC-8 gate (8 channels).
- **specs/daily-digest.md** — Wave 4 EC-3 gate.
- **specs/distribution.md** — Wave 5 pipx packaging.
- **specs/runtime-abstraction.md** — Wave 1 abstract stub; Phase 02 cross-runtime conformance.
- **specs/foundation-health-heartbeat.md** — Phase 01 stub-only; Phase 02 entry consumer.
- **specs/shamir-recovery.md** — Wave 2 dependency for boundary conversation.
- **specs/connection-vault.md** — Wave 1 parallel; Phase 02 mobile extension.
- **specs/posture-ladder.md** — Wave 2 authorship score consumer.
- **specs/model-adapter.md** — Wave 1 model router.
- **workspaces/phase-01-mvp/02-plans/01-build-sequence.md** — the source plan (analysis-time artifact).
- **workspaces/phase-01-mvp/01-analysis/01-shard-plan.md** § 5 — sequencing groups A–E.
- **workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md** — EC-1 through EC-9 ship predicate.
- **workspaces/phase-01-mvp/01-analysis/22-spec-gap-analysis.md** — aggregated primitive shard ambiguity findings (drives this spec's open-questions section).
- **workspaces/phase-01-mvp/01-analysis/00-inheritance-from-phase-00.md** § 5.4 — additive spec mandate that motivated this file.
- **workspaces/phase-01-mvp/01-analysis/{04..19}-\*-implementation.md** — 16 primitive deep-dive shards.
- **rules/autonomous-execution.md** § Per-Session Capacity Budget — the sharding discipline applied to every primitive's step list.
- **rules/orphan-detection.md** MUST Rule 1 — the wave-boundary discipline forcing the sequence.
- **rules/facade-manager-detection.md** MUST Rule 2 — the test-naming convention used at every Tier 2 wiring milestone.
- **rules/agents.md** § Worktree Isolation + Parallel-Worktree Package Ownership Coordination — the parallelization discipline behind the wall-clock estimate.
- **rules/specs-authority.md** MUST Rule 5b — the additive-only discipline; this spec is a NEW file, not an edit, and triggers no sibling re-derivation.
