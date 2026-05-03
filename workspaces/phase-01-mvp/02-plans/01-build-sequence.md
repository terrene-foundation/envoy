# 01 — Phase 01 Build Sequence

**Document role:** Aggregate the 16 primitive deep-dive shards (4–19) into a topologically-sorted build order, per-primitive scaffold step list, integration-test milestones, critical-path identification, and per-shard implementation-cycle estimates. Cites the source shards by path; never paraphrases.

**Date:** 2026-05-03 (shard 20 of /analyze, plan 1 of 4).
**Status:** DRAFT — load-bearing for `/todos` and `/implement`. Per `rules/specs-authority.md` MUST Rule 4, `/implement` reads this plan before each todo.
**Discipline:** Estimates in autonomous-execution sessions per `rules/autonomous-execution.md`, NEVER human-days.

---

## 1. Build-order topological sort

The dependency graph from `01-shard-plan.md` § 5 collapsed onto IMPLEMENTATION order (analysis ordered the shards; implementation orders the modules):

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
                                        ^ blocks on Wave 2's Shamir; sequencing inside wave

Wave 3 (depends on Wave 1 + 2):
  ├── envoy.grant_moment              [shard 10 — needs Envelope + Ledger + Trust + Boundary pause]
  └── envoy.budget                    [shard 12 — needs Grant Moment dispatch + Ledger + Envelope]

Wave 4 (depends on Wave 1 + 2 + 3):
  ├── envoy.channels                  [shard 16 — needs Connection Vault + Boundary + Grant Moment + Ledger + Trust]
  └── envoy.daily_digest              [shard 11 — needs Ledger + Channels + Model + Trust]

Wave 5 (depends on every primitive):
  ├── envoy.cli                       [shard 19 — 11 subcommands route every primitive]
  └── pipx packaging + NOTICES        [shard 19]

Side-channel (Wave 1 onward, separate repo):
  └── envoy-ledger-verifier           [shard 7 — separate codebase per EC-9; MUST NOT share source]
```

### 1.1 The critical path (single longest dependency chain)

**Trust store → Boundary Conversation → Grant Moment → Channel adapters → Daily Digest → CLI → pipx**

Length: 7 sequential wave-positions. Every other primitive sits on a shorter chain or in parallel with this one. The critical path is the EC-1 + EC-2 + EC-3 + EC-7 + EC-8 acceptance-gate spine — failure to ship any link delays Phase 01 release.

`envoy-ledger-verifier` (shard 7) runs in a parallel separate-codebase track and gates EC-4 + EC-9; it is NOT on the critical path because its codebase can develop concurrently with the producer. However, it gates Phase 01 release (EC-4 + EC-9 are BLOCKING per `02-mvp-objectives.md` § 5).

### 1.2 Why this order is forced

Per `rules/orphan-detection.md` MUST Rule 1, every facade-shape attribute MUST have a hot-path call site within 5 commits. This rules out the historical "build the chassis then the engine" pattern — every primitive must land WITH at least one consumer's wiring test in the same PR. The wave structure exists to satisfy this: a Wave-N primitive's PR includes the Tier 2 wiring test from Wave-N-or-later consumer.

---

## 2. Per-primitive scaffold step list

Each primitive is sharded into ~3-5 steps. Step-counts kept under the per-shard capacity budget (`rules/autonomous-execution.md` § Per-Session Capacity Budget: ≤500 LOC load-bearing, ≤5–10 invariants, ≤3–4 call-graph hops). Boilerplate (dataclasses, error taxonomy stubs) folded into the first step where it accompanies a single-purpose primitive.

### Wave 1

#### envoy.envelope.compiler (shard 4)

Source: `01-analysis/04-envelope-compiler-implementation.md` § 4.

1. **Skeleton + types** — `envoy/envelope/__init__.py`, `types.py` (`EnvelopeConfigInput`, `EnvelopeConfig`, 24 typed errors per `specs/envelope-model.md` § Error taxonomy), `compiler.py` empty class shell. Tier 1 unit tests for type construction.
2. **Canonical-bytes pipeline** — JCS+NFC `canonical_bytes` + `content_hash` emission (matches the Ledger's pipeline per shard 6 § 3.2). Tier 1 fixture tests against `specs/envelope-model.md` § Test location T-005 / T-013 / T-023 / T-094 / T-104 / T-105.
3. **`compile()` against `kailash.trust.pact.envelopes`** — wraps `intersect_envelopes`, `RoleEnvelope.validate_tightening`, `compute_effective_envelope`. Implements Envoy-superset fold-back (composition_rules UNION; cross_domain_rules_authored UNION).
4. **Template-resolver stub** — local-only Phase 01 path; Foundation Library registry deferred Phase 02.
5. **Tier 2 wiring** — `tests/integration/test_envelope_compiler_wiring.py` per shard 4 § 6. Asserts Ledger row appended after `compile()`.

Estimate: **1 session** (high feedback loop — JCS round-trip tests fire fast).

#### envoy.trust.store (shard 5)

Source: `01-analysis/05-trust-store-implementation.md` § 4.

1. **Adapter shell + principal-id key shape** — `envoy/trust/store.py` constructor takes `vault_path` + `principal_id` (no defaults; `PrincipalRequiredError` per `rules/tenant-isolation.md` Rule 2).
2. **`SqliteTrustStore` + `SQLitePostureStore` composition** — Genesis seeding ritual (`seed_genesis`); `record_delegation`; `get_chain` / `store_chain`.
3. **AES-256-GCM Trust Vault container** — wrap SQLite file in vault per `specs/trust-vault.md` § File format. Argon2id + Secure-Enclave/TPM-bound secret.
4. **Cascade revocation glue** — wraps `kailash.trust.revocation.cascade.cascade_revoke`; `verify_cascade_complete` for EC-8.
5. **Algorithm-identifier helper + Shamir export hooks** — `_with_algorithm_id` single-point; `export_master_key_for_shamir` / `import_master_key_from_shamir`.
   - **Step 5a (R2-H-01):** Implement `TrustStoreAdapter._to_spec_wire_form(algorithm_dict)` translation helper. Land BEFORE any record persistence path lights up. Verifies producer-verifier wire-shape round-trip per `specs/independent-verifier.md` L35. The helper sits as a sibling to `_with_algorithm_id()`; every record-construction path routes through `_with_algorithm_id()` which routes through `_to_spec_wire_form()` before write, translating upstream's 1-key `{"algorithm": "ed25519+sha256"}` form into the spec-mandated 3-key `{"sig", "hash", "shamir"}` form per `specs/trust-lineage.md` L24.
6. **Tier 2 wiring** — 8 tests per shard 5 § 6.1 + the R2-H-01 producer-verifier wire-shape round-trip regression test.

Estimate: **2 sessions** (vault crypto work has lower feedback loop; need real Argon2id timing).

#### envoy.ledger (shard 6)

Source: `01-analysis/06-envoy-ledger-implementation.md` § 4.

1. **Skeleton + entry types** — 35 dataclasses transcribed from `specs/ledger.md` lines 47–91. 8 typed errors. `EntryEnvelope` frozen dataclass.
2. **Canonical JSON + hash chain** — `canonical_dumps()` matching `#757`/`#756`/`#731` byte pinning. `HashChainBuilder.build()` pure function.
3. **`EnvoyLedger.append()` facade + atomic transaction** — wraps upstream `AuditStore` inside `df.transaction()` (post-#707/#711). Single-point filter at emitter routes `record_id` through `format_record_id_for_event`.
4. **HeadCommitment monotonic guard + HaltedByRollback** — rollback emits halt entry BEFORE refusing further writes.
5. **Two-phase signing + orphan resolution** — `PhaseARecord` / `PhaseBRecord` linked by `intent_id`; 30-day TTL orphan sweep at session start.
6. **Export CLI** — `envoy ledger export --format json|pdf` produces signed bundle for shard 7 verifier.
7. **Tier 2 wiring** — 11 tests per shard 6 § 6.1.

Estimate: **2 sessions** (the chain-shape must lock at Phase 01 release; Tier 2 byte-identity tests across OS need real cross-OS CI).

#### envoy.model.router (shard 13)

Source: `01-analysis/13-model-adapter-implementation.md` § 3.

1. **BYOM picker + .env writer** — first-launch CLI that writes `KAILASH_LLM_PROVIDER` + `KAILASH_LLM_DEPLOYMENT` env keys; secrets routed to Connection Vault (NEVER `.env` plaintext).
2. **EnvoyModelRouter** — wraps `LlmClient.from_env()`; per-primitive override map (`ENVOY_BOUNDARY_MODEL`, `ENVOY_DIGEST_MODEL`, `ENVOY_GRANT_MOMENT_SUMMARY_MODEL`, `ENVOY_DEFAULT_MODEL`).
3. **EnvoyProviderRiskAnnotator** — preset-name → `ProviderRisk` annotation per `specs/model-adapter.md` lines 17–29.
4. **Response-filter pipeline (Phase 01 minimum)** — token-budget check; leak-canary stub (Phase 04 corpus); goal-drift classifier stub.
5. **Tier 2 wiring** — verify per-primitive model override exercised in real LLM call (Ollama for CI; real Claude/GPT for staging).

Estimate: **1 session** (thin glue layer over upstream A-grade `LlmDeployment`).

#### envoy.connection_vault (shard 14)

Source: `01-analysis/14-connection-vault-implementation.md` § 3.

1. **Adapter + 11-field schema** — `envoy/connection_vault/adapter.py`; serializes 11 fields into `keyring.set_password()` 3-tuple via canonical-JSON.
2. **Per-principal isolation + envelope-scope enforcement** — `principal_genesis_id` keyed; `EnvelopeScopeMismatchError` on get without active scope.
3. **`expires_at` + `usage_counter` enforcement** — fail-closed defaults; 7 typed errors.
4. **`.env` first-run import path** — Boundary Conversation reads `.env` and writes Vault; post-onboarding `.env` no longer source of truth.
5. **Tier 2 wiring** — real `keyring` against macOS Keychain / Linux Secret Service / Windows Credential Manager.

Estimate: **1 session** (Envoy-new-code by design but minimal — `keyring` MIT package handles platform glue).

#### envoy.runtime (shard 18 — abstract stub only)

Source: `01-analysis/18-runtime-abstraction-stub-implementation.md` (referenced in shard plan summary).

1. **Abstract interface contract** — Python ABC matching `specs/runtime-abstraction.md`; ALL methods declared as abstract.
2. **`kailash_py` adapter (sole Phase 01 backend)** — implements every ABC method by composing the relevant Envoy primitive.
3. **Feature-flagged `kailash_rs_bindings` slot** — empty module raising `RuntimeBackendNotWired` until Phase 02.

Estimate: **0.5 session** (tiny shim; gates Phase 02 mechanicality).

#### envoy.heartbeat (shard 17 — de-scoped to 4 stubs)

Source: `01-analysis/17-foundation-health-heartbeat-decision-implementation.md` (referenced in shard plan summary; DECISION shard = de-scope).

1. **5 stubs** (R2-H-02 fix): (1) `envoy/heartbeat/client.py` — `HeartbeatClient.maybe_record_flag()` **no-op** invoked by 21 emit-site primitives; (2–5) `envoy/heartbeat/{star_prio,ohttp,signed_consent,registry}.py` raising `PhaseDeferredError` (Phase 02 only). The first stub is the genuine Phase 01 hot-path consumer (the 21 emit-site primitives at Boundary Conversation completion, Daily Digest open, Grant Moment approve/deny, etc., all invoke `client.maybe_record_flag(...)` as a literal `pass` no-op); the latter four cover deferred network/crypto primitives (STAR/Prio, OHTTP, signed-consent, registry handshake) that Phase 01 production code MUST NEVER call. Per `rules/zero-tolerance.md` Rule 2 + `rules/orphan-detection.md` Rule 4a — a regression grep MUST verify zero non-test imports of the four `PhaseDeferredError` modules.

Estimate: **0.25 session** (pure boilerplate; Phase 02 trigger).

### Wave 2

#### envoy.authorship (shard 9)

Source: `01-analysis/09-authorship-score-implementation.md` § 3.

1. **`AuthorshipScore.recompute(envelope, ledger_slice)`** — pure-function deterministic re-derivation; 5-dimension canonical iteration order.
2. **`PostureGate.request_transition()`** — 5-step fail-closed enforcement; cascade-revoke hook on demotion.
3. **`BET12CadenceEmitter`** — cohort-level posture-transition Ledger emit (Phase 01 sink: local-only `ritual_completion` entries with `bet_id="BET-12"`).
4. **Tier 2 wiring** — exercise PostureGate against real Trust store + Ledger; assert `posture_change` Ledger entry signed by Genesis key.

Estimate: **1 session** (pure function + 5-step gate; high feedback loop).

#### envoy.shamir (shard 15)

Source: `01-analysis/15-shamir-recovery-implementation.md` § 3.

1. **`envoy.shamir.ritual.ShamirRitualCoordinator`** — wraps `kailash.trust.vault.shamir.generate(...)` with the 6-step Phase 01 ritual; zeroizes master key.
2. **`envoy.shamir.paper`** — 24-word paper-card renderer per `specs/shamir-recovery.md` § Card format.
3. **`envoy.shamir.reconstruct`** — `envoy shamir recover` CLI; commitment-verify against `Genesis.shard_public_commitments`.
4. **`envoy.shamir.commitments`** — bind shard public commitments to Genesis Record at backup.
5. **`envoy.shamir.distribution_checklist`** — opaque slot labels in Trust Vault (NOT real names; H-06 fix).
6. **Tier 2 wiring** — all C(5,3)=10 share combinations reconstruct-test; cross-tool interop with `python-shamir-mnemonic`.

Estimate: **1 session** (upstream `kailash 2.11.0` ships the wrapper; Envoy is paper-shard + ritual + plain-language errors).

#### envoy.boundary_conversation (shard 8)

Source: `01-analysis/08-boundary-conversation-implementation.md` § 3.

1. **`BoundaryConversationRuntime` + Plan DAG** — Kaizen L3 `Plan` over S0→S10; per-state `PlanNode` with attached `Signature`.
2. **9 `Signature` subclasses** — one per S1-S9 (structured-output JSON schema).
3. **`EnvelopeConfigInputAssembler`** — accumulates per-state extractions; emits in JCS-canonical-order.
4. **`RitualResumeCoordinator`** — Trust-Vault-backed per-state persistence; `envoy init --resume <ritual_id>`.
5. **S7 visible-secret + S8 Shamir pause** — `Plan.suspension = SuspensionRecord(reason=ExplicitCancellationReason(...))`.
6. **Novelty feedback gate at S3/S5** — Jaccard portion only (Phase 01); classifier deferred Phase 04.
7. **Post-duress banner gate** — at S0 entry, query shadow segment; render banner if unread duress event.
8. **Tier 2 wiring + Tier 3 EC-1 acceptance** — `tests/integration/test_resume_from_each_state.py`; `tests/e2e/test_boundary_conversation_full_path.py` (~15min budget).

Estimate: **3 sessions** (most-integrated primitive; 6 module split per shard 8 § 3.7; ~1180 LOC across modules).

### Wave 3

#### envoy.grant_moment (shard 10)

Source: `01-analysis/10-grant-moment-implementation.md` § 3.

1. **State machine M0→M4** — `GrantMomentState` enum + transition table per `specs/grant-moment.md` § State machine.
2. **`SignedConsentBuilder`** — `GrantMomentRequest` + `GrantMomentResult` JCS+NFC canonicalization; signing via `delegation_key`.
3. **`ResolutionShape` (3 shapes for EC-2)** — Approve / Decline / ApproveWithModification mapping to spec's 4 decisions.
4. **`OutOfEnvelopeDetector`** — interceptor wrapping every Kaizen tool-call dispatch.
5. **`ChannelHandoff.dispatch()`** — function-call contract to channel adapters; primary-channel binding check.
6. **`CascadeRevocationOrchestrator`** — wraps upstream `cascade_revoke`; verifies `verify_cascade_complete`.
7. **`PlanSuspensionBridge`** — typed-event channel between Boundary Conversation + Grant Moment.
8. **`NoveltyClassifier`** — novel / familiar_repeat / high_stakes classification.
9. **10 typed errors** per `specs/grant-moment.md` § Error taxonomy.
10. **Tier 2 wiring + Tier 3 EC-2 acceptance** — all 3 resolution shapes execute end-to-end with cascade revocation working.

Estimate: **2 sessions** (8 modules; cascade BFS verification needs real Trust store fixtures).

#### envoy.budget (shard 12)

Source: `01-analysis/12-budget-tracker-implementation.md` § 3.

1. **`MultiWindowBudget`** — 5 `BudgetTracker` instances per ceiling window with `principal_id` keying.
2. **`EnvoyBudgetOrchestrator` facade** — `reserve_for_call` / `record_for_call` / `check` / `lower_velocity_limit` / `raise_velocity_limit` (refused inline).
3. **`ThresholdDispatcher`** — async task queue; collects under upstream lock, dispatches outside lock; routes through Grant Moment.
4. **`BudgetResetScheduler`** — pure-function `current_period_key(window, at_time)`; per-call/session/hour/day/month reset semantics.
5. **`AnomalyDetector`** — single-call > 50% session; 5-calls-at-ceiling-in-1-min.
6. **`LedgerEmitter`** — single-point filter for `budget_threshold_crossed` + `budget_reservation_record` entries.
7. **7 typed errors**.
8. **Tier 2 wiring** — exercise threshold-fire → Grant Moment → resolution → budget mutation chain end-to-end.

Estimate: **1.5 sessions** (upstream `BudgetTracker` is A-grade; Envoy is composition + multi-window + reset scheduler).

### Wave 4

#### envoy.channels (shard 16)

Source: `01-analysis/16-channel-adapters-implementation.md` § 3.

1. **`ChannelAdapter` ABC + `InboundMessage` envelope + 11 typed errors** — unified contract per `specs/channel-adapters.md`.
2. **`CLIChannelAdapter` + `WebChannelAdapter`** — wrap upstream `kailash.channels.{cli,api}_channel`; localhost bind for Web with Origin/Host allowlist (post-#673).
3. **`TelegramChannelAdapter` + `SlackChannelAdapter` + `DiscordChannelAdapter`** — clean bot-API channels; wrap `nexus.transports.webhook.WebhookTransport` with per-vendor `WebhookSigner`.
4. **`WhatsAppChannelAdapter` + `IMessageChannelAdapter` + `SignalChannelAdapter`** — caveated channels (paid-tier / Apple-ToS-grey / Path-B legal-gate); ship per `specs/channel-adapters.md` lines 171–173 disposition.
5. **`InboundRouter`** — concurrent `asyncio.gather` over every adapter's `receive_message()`; routes to active session.
6. **`GrantMomentRenderer` per channel** — channel-native UI; numbered-options text fallback for iMessage/Signal.
7. **`PerChannelRateLimiter`** — per-channel quota translation.
8. **`CredentialResolver`** — startup-time Connection Vault entry resolution.
9. **Tier 2 wiring per channel** — 9 test files per `specs/channel-adapters.md` § Test location.
10. **Tier 3 EC-7 acceptance** — `tests/e2e/test_session_continuity_8_channels.py` × N=3 onboarding sessions per channel.

Estimate: **3 sessions** (8 adapters but ~150 LOC each over shared ABC; iMessage + Signal feasibility risk surfaced in shard 16 § 7 may force de-scope #1 fallback to 5 channels).

#### envoy.daily_digest (shard 11)

Source: `01-analysis/11-daily-digest-implementation.md` § 3.

1. **`DailyDigestService` facade + `DigestScheduler`** — `apscheduler.AsyncIOScheduler` + `CronTrigger`; per-principal job registration.
2. **`LedgerAggregator`** — queries `EnvoyLedger.query()` for actions/refusals/spend/pending_grants/planned_today.
3. **`DigestRenderer`** — produces `DigestPayload` (11-field schema/1.0 verbatim); optional `EnvoyModelRouter.for_primitive("daily_digest")` for natural-language summary.
4. **`PerChannelFanout`** — `asyncio.gather(...,  return_exceptions=True)` parallel fan-out with fault isolation.
5. **`BackfillTracker` + `PauseDisableState` + `LowEngagementTracker`** — Trust-store-backed state.
6. **`DuressBannerReader`** — local-only shadow-segment read; primary-channel-only.
7. **5 typed errors + CLI** — `envoy digest today / pause / resume / schedule`.
8. **Tier 2 wiring + Tier 3 EC-3 acceptance** — 7 consecutive days scheduled fire across configured channels.

Estimate: **2 sessions** (scheduler + aggregator + renderer + fanout; relatively independent of EC-1/EC-2).

### Wave 5

#### envoy.cli + pipx packaging (shard 19)

Source: `01-analysis/19-pipx-distribution-architecture-implementation.md` (referenced in shard plan summary).

1. **`envoy/cli.py` 11 subcommands** — `init` / `up` / `boundaries` / `ledger` / `shamir` / `digest` / `grant` / `posture` / `connection` / `model` / `version`. Phase 02 stubs: `mobile-pair`, `enterprise-deploy`.
2. **`pyproject.toml`** — `kailash[shamir,nexus,kaizen]>=2.13.4`, `keyring>=24.0`, `python-dotenv>=1.0`, `python-telegram-bot` (LGPL-3.0+), `slack-sdk`, `discord.py`, `apscheduler`.
3. **`NOTICES`** — LGPL-3.0+ python-telegram-bot disclosure; MIT keyring; Apache 2.0 kailash family.
4. **Cross-OS packaging tests** — macOS full / Linux desktop-env-required / Windows x86_64; ARM64 Phase 02.

Estimate: **1 session** (final integration; depends on every primitive landing).

### Side-channel: envoy-ledger-verifier (shard 7)

Source: shard plan § 2 wave-B summary (separate `terrene-foundation/envoy-ledger-verifier` repo per shard 7's recommendation).

1. **Repo bootstrap** — separate codebase; ZERO source shared with Envoy.
2. **Verify protocol** — re-implement chain-walk + Ed25519 verification + canonical-JSON byte-comparison. Different agent (or different language Rust sibling stretch) per `02-mvp-objectives.md` EC-9.
3. **Trust-anchor with first-verification self-anchoring** — user-supplied trust anchor; verifier remembers on first use.
4. **Tier 2 + Tier 3** — tampering battery (single-bit flip / insertion / deletion / reorder).

Estimate: **2 sessions** (parallel track; gates Phase 01 release).

---

## 3. Integration-test milestones

These milestones are global checkpoints; each binds the cumulative wave's wiring tests AND adds a cross-primitive end-to-end gate.

### Milestone 1 — Wave 1 lands (foundation primitives wired)

Trigger: every Wave 1 primitive's Tier 2 wiring test green. Add gate:

- `tests/e2e/test_envoy_ledger_cross_os_byte_identity.py` — 3-OS matrix produces byte-identical canonical export.
- `tests/integration/test_envelope_compiler_intersect_through_kailash_py.py` — round-trip with upstream `intersect_envelopes` byte-equal.
- `tests/integration/test_trust_store_adapter_genesis_round_trip.py` — Genesis seeded; verified by `verify_signature`.

Convergence: all green = Wave 2 may launch.

### Milestone 2 — Wave 2 lands (Boundary Conversation EC-1 gate)

Trigger: shard 8 + 9 + 15 wiring tests green.

- `tests/e2e/test_boundary_conversation_full_path.py` — N=3 first-time-user sessions ≤25 min produce parseable EnvelopeConfig (EC-1 acceptance).
- `tests/integration/test_resume_from_each_state.py` — every S0–S10 state resumable.
- Shamir 10-combo reconstruct test passes (EC-5 partial).

Convergence: EC-1 met, EC-5 partial = Wave 3 may launch.

### Milestone 3 — Wave 3 lands (Grant Moment EC-2 gate)

Trigger: shard 10 + 12 wiring tests green.

- All 3 resolution shapes (Approve / Decline / ApproveWithModification) execute end-to-end (EC-2 acceptance).
- Cascade revocation reaches every descendant in 3-deep delegation tree.
- `tests/e2e/test_envoy_ledger_tampering_battery.py` — verifier (shard 7) detects every tampering form (EC-4 acceptance).
- `tests/e2e/test_envoy_ledger_independent_verifier_ec9.py` — separate-codebase verifier passes (EC-9 acceptance).

Convergence: EC-2 + EC-4 + EC-9 met = Wave 4 may launch.

### Milestone 4 — Wave 4 lands (channel + digest EC-3, EC-7, EC-8 gates)

Trigger: shard 11 + 16 wiring tests green.

- **EC-3**: scheduled Daily Digest fires for ≥7 consecutive days across configured channels.
- **EC-7**: N=3 first-time-user sessions per channel × 8 channels = 24 successful onboardings (or 5 if de-scope #1 invoked).
- **EC-8**: 7-day operating window across ≥4 of 8 channels with cross-channel state-equivalence test running daily; cascade revocation of Day-1 grant correctly revokes Day-6 child grant initiated from a different channel.

Convergence: EC-3 + EC-7 + EC-8 met = Wave 5 may launch.

### Milestone 5 — Wave 5 lands (release-readiness)

Trigger: shard 19 packaging green.

- `pipx install envoy-agent` works on macOS / Linux desktop-env / Windows x86_64.
- All 11 CLI subcommands functional.
- `NOTICES` correct; LGPL-3.0+ python-telegram-bot disclosure present.
- All 9 ECs met.
- 2 consecutive `/redteam` rounds at 0 CRIT + 0 HIGH (EC-6 acceptance).

Convergence: Phase 01 ships.

---

## 4. Per-shard implementation-cycle estimates

Per `rules/autonomous-execution.md` § 10x Throughput Multiplier and § Per-Session Capacity Budget. Estimates in autonomous-execution sessions, NEVER human-days.

| Shard     | Primitive                       | Estimate (sessions) | Justification                                                                   |
| --------- | ------------------------------- | ------------------- | ------------------------------------------------------------------------------- |
| 4         | Envelope compiler               | 1                   | High feedback loop; thin wrapper over A-grade upstream.                         |
| 5         | Trust store + lineage           | 2                   | Vault crypto + cascade glue; lower feedback loop on Argon2id.                   |
| 6         | Envoy Ledger                    | 2                   | Chain-shape locks at release; cross-OS byte-identity tests need real CI.        |
| 7         | Independent verifier            | 2                   | Separate codebase track; parallel to producer.                                  |
| 8         | Boundary Conversation           | 3                   | Most-integrated primitive; 6 modules; ~1180 LOC; 9 LLM-driven states.           |
| 9         | Authorship Score + posture gate | 1                   | Pure function + 5-step gate; high feedback.                                     |
| 10        | Grant Moment                    | 2                   | 8 modules; cascade BFS needs real Trust store fixtures.                         |
| 11        | Daily Digest                    | 2                   | Scheduler + aggregator + renderer + fanout.                                     |
| 12        | Budget tracker                  | 1.5                 | Composition + multi-window + reset scheduler over A-grade upstream.             |
| 13        | Model adapter                   | 1                   | Thin glue over A-grade `LlmDeployment`.                                         |
| 14        | Connection Vault                | 1                   | Envoy-new-code but minimal; `keyring` MIT handles platform glue.                |
| 15        | Shamir 3-of-5 recovery          | 1                   | Upstream `kailash 2.11.0` ships wrapper; Envoy is paper-shard + plain-language. |
| 16        | Channel adapters (8)            | 3                   | 8 adapters × shared ABC pattern; iMessage/Signal feasibility risk.              |
| 17        | Foundation Health Heartbeat     | 0.25                | De-scoped to 4 stubs only.                                                      |
| 18        | Runtime abstraction stub        | 0.5                 | Tiny ABC + sole `kailash_py` adapter.                                           |
| 19        | pipx distribution               | 1                   | Final integration; depends on every primitive landing.                          |
| **Total** |                                 | **~24 sessions**    | Sequential lower bound.                                                         |

### Parallelization

With worktree isolation per `rules/agents.md` § "Worktree Isolation for Compiling Agents" and parallel ownership per `rules/agents.md` § "Parallel-Worktree Package Ownership Coordination":

- **Wave 1**: 7 primitives in parallel = ~2 wall-clock sessions (Trust store + Ledger are the bottleneck at 2 each).
- **Wave 2**: 3 primitives but Boundary Conversation depends on Shamir, so sequencing inside the wave produces ~3 wall-clock sessions.
- **Wave 3**: 2 primitives in parallel = ~2 wall-clock sessions.
- **Wave 4**: 2 primitives in parallel = ~3 wall-clock sessions (channels is bottleneck).
- **Wave 5**: 1 session.
- **Side-channel** (shard 7): 2 sessions parallel to Waves 1-3.

**Wall-clock estimate**: ~11 orchestrator sessions for Phase 01 implementation.

This is consistent with the 8–12 session Phase 01 estimate in thesis §3.1.

---

## 5. MUST-rule discipline applied

- **`rules/autonomous-execution.md` § Per-Session Capacity Budget**: every step kept within ≤500 LOC load-bearing logic / ≤5–10 invariants / ≤3–4 call-graph hops. Boundary Conversation's 8-step plan is the longest because the spec mandates 6 modules and the 9 LLM states.
- **`rules/orphan-detection.md` MUST Rule 1**: every primitive's wave-position pairs the facade landing with at least one consumer's wiring test (e.g., shard 6 lands with shard 4's Tier 2 test depending on it).
- **`rules/facade-manager-detection.md` MUST Rule 2**: test file naming follows `test_<lowercase>_wiring.py` so `/redteam` mechanically detects missing wiring.
- **`rules/specs-authority.md` MUST Rule 5b**: NO spec edits proposed by this plan — all edits deferred to shard 22.
- **`rules/agents.md` § Parallel-Worktree Package Ownership Coordination**: a Wave-1 parallel launch MUST designate ownership of `pyproject.toml` + version bumps to ONE agent.

---

## 6. Cross-references

- Shard plan: `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 5 (sequencing groups A–E).
- MVP objectives: `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` (9 ECs + ship predicate).
- kailash-py readiness: `workspaces/phase-01-mvp/01-analysis/03-kailash-py-mvp-readiness.md` § 3 row table.
- Per-primitive shards: `workspaces/phase-01-mvp/01-analysis/{04..19}-*-implementation.md`.
- Test strategy: `workspaces/phase-01-mvp/02-plans/02-test-strategy.md`.
- Package skeleton: `workspaces/phase-01-mvp/02-plans/03-package-skeleton.md`.
- Redteam cycle: `workspaces/phase-01-mvp/02-plans/04-redteam-cycle-plan.md`.
- Capacity rule: `.claude/rules/autonomous-execution.md`.
- Orphan / facade rules: `.claude/rules/orphan-detection.md`, `.claude/rules/facade-manager-detection.md`.
