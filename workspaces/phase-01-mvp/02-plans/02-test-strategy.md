# 02 — Phase 01 Test Strategy

**Document role:** Aggregate the per-primitive Tier 2 / Tier 3 test surfaces from shards 4–19 into a unified 3-tier strategy per `.claude/rules/testing.md`. For each Phase 01 exit criterion (EC-1 through EC-9), enumerate the wiring tests required, the Tier 3 end-to-end battery, the acceptance gate, and any cross-OS portability test. Designs the EC-4/EC-9 tampering battery, the EC-5 Shamir 10-combinations + cross-tool interop, the EC-7 8-channel × N=3 onboarding battery, and the EC-8 7-day cross-channel coherence test.

**Date:** 2026-05-03 (shard 20 of /analyze, plan 2 of 4).
**Status:** DRAFT — load-bearing for `/implement` test discipline and `/redteam` audit checks.
**Discipline:** Tier 2/3 use REAL infrastructure, NO mocking per `rules/testing.md` § Tier 2 / § Tier 3. Every Tier 2 wiring test asserts an externally-observable effect per `rules/orphan-detection.md` Rule 2 + `rules/facade-manager-detection.md` Rule 1.

---

## 1. The 3-tier framework applied to Envoy

### Tier 1 — Unit (mocking allowed; <1s per test)

Per `rules/testing.md` § Tier 1: mocking allowed; fast feedback. In Envoy:

- Pure functions: `AuthorshipScore.recompute()`, `LamportClock.next()`, `canonical_dumps()`, `format_record_id_for_event()`, `current_period_key()`.
- Type-construction validation: dataclass `__post_init__` finite-checks, schema-version field validation.
- Single-method behavior of upstream-already-tested primitives wrapped by Envoy (e.g., the wave-A finding that kailash-py ships 190 unit tests on `intersect_envelopes` proper means Envoy adds 0 Tier 1 coverage there; only the Envoy-new-code surface gets Tier 1).

**Mock policy at Tier 1**: PERMITTED only when the dependency is a pure-function helper that has its own Tier 1 + Tier 2 coverage upstream. Mocks of `kailash.trust.signing.crypto.sign()` are PERMITTED at Tier 1 because Tier 2 round-trip tests prove the framework calls the real signer.

### Tier 2 — Integration (real infrastructure; NO mocking)

Per `rules/testing.md` § Tier 2 + `rules/orphan-detection.md` MUST Rule 2: real SQLite, real Ed25519 keys, real `keyring` against the active OS keychain, real channel-vendor sandbox endpoints (Telegram test bot; Slack ngrok-tunneled webhook; Discord test guild), real Ollama for local-LLM scenarios, real `apscheduler` firing on real wall clock with shortened intervals.

**`@patch`, `MagicMock`, `unittest.mock` BLOCKED**. Per `rules/testing.md` § Tier 2: "Mocks at the binding boundary hide failures (connection handling, value serialization, lifetime management) that only surface with the real Python bindings."

Naming convention per `rules/facade-manager-detection.md` Rule 2: `test_<lowercase_facade>_wiring.py`. `/redteam` automatically detects missing wiring tests by checking for the expected file name.

### Tier 3 — End-to-end (real everything)

Per `rules/testing.md` § Tier 3: real LLM (Ollama for CI, real Claude/GPT for staging), real cross-OS keychain, full ritual flows. Includes state-persistence read-back verification per `rules/testing.md` § Tier 3: "every write MUST be verified with a read-back."

Tier 3 staging matrix (cross-OS portability):

- **macOS** — primary developer platform; full keychain support; full BlueBubbles iMessage path.
- **Linux** — secondary; requires desktop env (GNOME / KDE) for `keyring` Secret Service backend; `KeychainUnavailableError` fallback to Phase 02 HashiCorp Vault per shard 19 disposition.
- **Windows x86_64** — Phase 01 supported; ARM64 deferred Phase 02.

---

## 2. Per-EC test battery

For each of the 9 ECs from `02-mvp-objectives.md`, the table below names: (a) Tier 2 wiring tests required, (b) Tier 3 end-to-end battery, (c) acceptance gate, (d) cross-OS portability test if applicable.

### EC-1 — First-time user completes Boundary Conversation end-to-end

**Owning primitive**: shard 8 (Boundary Conversation) + shard 4 (Envelope compiler) + shard 6 (Ledger).

#### Tier 2 wiring (per `rules/orphan-detection.md` Rule 1)

- `tests/integration/test_boundary_conversation_runtime_wiring.py` — imports `BoundaryConversationRuntime` through facade; asserts `EnvelopeConfigInput` → `EnvelopeConfig` → Trust Vault write + Ledger entry.
- `tests/integration/test_resume_from_each_state.py` — every S0–S10 state resumable via `envoy init --resume <ritual_id>`.
- `tests/integration/test_envelope_compiler_wiring.py` — compile produces `canonical_bytes` byte-equal to JCS-NFC fixture; Ledger row written.
- `tests/integration/test_envelope_compiler_monotonic_tightening_at_compile.py` — child compile with widened dimension raises `MonotonicTighteningError`.
- `tests/integration/test_envoy_model_router_chat_async_routing.py` (carry-forward R1-M-02 disposition per `workspaces/phase-01-mvp/04-validate/round-4-implementation-comprehensive.md` § 4) — imports `EnvoyModelRouter` through facade; asserts `chat()` routes through `LlmDeployment.chat_async()` per shard 13 § 7.1 HOLD rationale (async-routing wiring contract). Tier 2 against real Ollama; verifies the facade calls the underlying async chat method, not a sync shim.
- `tests/regression/test_t018_*.py` (visible-secret), `test_t023_*.py` (Authorship Score seeding).

#### Tier 3 end-to-end battery

- `tests/e2e/test_boundary_conversation_full_path.py` — N=3 first-time-user sessions, each ≤25 minutes, against real LLM (Ollama `qwen2.5:7b` for CI; real Claude for staging). Asserts: (a) parseable EnvelopeConfig produced, (b) "I understand what just happened" post-prompt acknowledgment captured.
- `tests/e2e/test_boundary_conversation_minimum_path.py` — 8-min minimum-path (template + visible secret + Shamir).
- `tests/integration/test_post_duress_banner.py` — banner blocks S0 advance until acknowledged.

#### Acceptance gate (per `02-mvp-objectives.md` EC-1)

≥3 distinct first-time-user sessions complete in ≤25 minutes (15min target + 66% buffer) with (a) parseable, envelope-compiler-accepted `EnvelopeConfig`, (b) "I understand what just happened" post-session acknowledgment.

#### Cross-OS portability

Run the full path on macOS / Linux / Windows; envelope `content_hash` MUST be byte-identical for the same `EnvelopeConfigInput` regardless of OS.

---

### EC-2 — 3 Grant Moments triggered and resolved correctly

**Owning primitive**: shard 10 (Grant Moment) + shard 4 (Envelope compiler) + shard 6 (Ledger) + shard 5 (Trust store cascade).

#### Tier 2 wiring

- `tests/integration/test_grant_moment_orchestrator_wiring.py` — imports `GrantMomentOrchestrator` through facade; tests all 4 spec decisions × 3 EC-2 resolution shapes.
- `tests/integration/test_out_of_envelope_detector_wiring.py` — detector intercepts Kaizen tool dispatch; surfaces `EnvelopeViolation` on out-of-envelope action.
- `tests/integration/test_signed_consent_builder_byte_identity.py` — JCS+NFC canonicalization byte-equal to upstream fixture.
- `tests/integration/test_cascade_revocation_orchestrator_wiring.py` — wraps `cascade_revoke`; build 3-deep delegation tree; revoke root; assert all descendants in `revoked_agents` set; `verify_cascade_complete` returns True.
- `tests/integration/test_plan_suspension_bridge_wiring.py` — Boundary Conversation pauses with `PlanSuspension`; resumes with `ResolutionShape` outcome.
- `tests/integration/test_visible_secret_render_check.py` — visible-secret bytes from channel match Trust Vault stored secret; mismatch raises `VisibleSecretMismatchError`.

#### Tier 3 end-to-end battery

- `tests/e2e/test_grant_moment_three_resolution_shapes.py` — execute `Approve`, `Decline`, `ApproveWithModification` end-to-end across 3 different sessions; each produces correct Ledger entries and (where applicable) DelegationRecord + envelope mutation.
- `tests/e2e/test_grant_moment_cascade_revocation_cross_channel.py` — Day-1 grant approved on Telegram; Day-3 child action initiated from Slack; Day-3 revoke-via-Daily-Digest cascades back through every descendant.

#### Acceptance gate

All 3 resolution shapes execute end-to-end with: (a) ledger entries written + verifiable, (b) envelope state mutated correctly, (c) cascade-revocation of any descendant grant when originating grant is revoked.

---

### EC-3 — Daily Digest renders at scheduled time with real data

**Owning primitive**: shard 11 (Daily Digest) + shard 6 (Ledger) + shard 16 (Channel adapters).

#### Tier 2 wiring

- `tests/integration/test_daily_digest_service_wiring.py` — imports `DailyDigestService` through facade; constructs against real `apscheduler.AsyncIOScheduler` + real SQLite Ledger; asserts scheduled job fires.
- `tests/integration/test_digest_form_per_channel.py` — same `DigestPayload` rendered as rich (Email/Web), inline-button (Telegram/Slack/Discord), compact 10-line (SMS/WhatsApp).
- `tests/integration/test_low_engagement_fallback.py` — `<2 opens/week × 3 weeks` → flips form to `compact` or `event_only`.
- `tests/integration/test_duress_banner_primary_only.py` — banner renders ONLY on primary channel; non-primary gets standard digest.
- `tests/regression/test_t019_habituation_low_engagement_fallback.py`.
- `tests/integration/test_digest_reply_no_yes_skip.py` — three reply paths handled.
- `tests/integration/test_backfill_skipped_days.py` — simulate skipped day; next-day digest's `actions` array contains the missed-day Ledger entries.
- `tests/integration/test_pause_disable_persists_across_restart.py` — pause; restart process; pause state survives; `resume_at` honored.

#### Tier 3 end-to-end battery

- `tests/e2e/test_daily_digest_morning_delivery.py` — scheduled fire on each configured channel; 7 consecutive days observed in CI (with a time-acceleration shim to compress wall-clock); back-fill semantics verified across simulated offline days.

#### Acceptance gate

Scheduled Daily Digest fires at user's local-morning hour for ≥7 consecutive days, rendering across all configured channels with content sourced from the Ledger. Skipped days appear in next-day digest as back-fill, not silently dropped.

---

### EC-4 — Envoy Ledger exports a verifiable hash-chained log

**Owning primitive**: shard 6 (Envoy Ledger) + shard 7 (Independent verifier).

#### Tier 2 wiring

- `tests/integration/test_envoy_ledger_wiring.py` — imports `EnvoyLedger` through facade; constructs against real SQLite + real Ed25519 keypair; calls `.append(...)` for each major entry type; asserts audit_store row + `entry_id` round-trip + `verify_chain()` success.
- `tests/integration/test_envoy_ledger_crypto_round_trip.py` — append → verify_chain succeeds; modifying stored content byte-by-byte fails verification (per `rules/orphan-detection.md` Rule 2a crypto-pair round-trip THROUGH the facade).
- `tests/integration/test_envoy_ledger_canonical_json_byte_identity.py` — two Python processes (different OS, locale, timezone) emit byte-identical canonical JSON.
- `tests/integration/test_envoy_ledger_atomic_append_under_failure.py` — kill process between audit_row write and head_commitment update; on restart, `verify_chain()` correctly identifies state.
- `tests/integration/test_envoy_ledger_head_commitment_monotonic.py` — `LedgerRollbackDetectedError` + `HaltedByRollbackRecord` on stale head; subsequent `.append()` raises `LedgerHaltedError`.
- `tests/integration/test_envoy_ledger_phase_a_b_intent_id_link.py` — PhaseA → PhaseB linked; orphan resolved at next session start.
- `tests/integration/test_envoy_ledger_segment_boundary.py` — `MigrationAnnouncement` partitions chain; segment-mismatch raises `LedgerAlgorithmMismatchError`.
- `tests/integration/test_envoy_ledger_export_round_trip.py` — `envoy ledger export --format json` writes bundle; reading bundle produces entries matching in-memory by `entry_id`; `receipt_hash` verifies.

#### Tier 3 end-to-end battery — the EC-4 + EC-9 tampering battery

`tests/e2e/test_envoy_ledger_tampering_battery.py` — for an N=1000-entry export bundle:

| #   | Tampering form                                                                                                                                                       | Expected verifier verdict                                                                                    |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| 1   | Untampered bundle                                                                                                                                                    | PASS                                                                                                         |
| 2   | Single-bit flip in entry K's `content`                                                                                                                               | FAIL at entry K                                                                                              |
| 3   | Single-bit flip in entry K's `signature_hex`                                                                                                                         | FAIL at entry K                                                                                              |
| 4   | Entry K removed entirely                                                                                                                                             | FAIL at chain-link gap                                                                                       |
| 5   | Entry K duplicated (inserted as K+1 with same content)                                                                                                               | FAIL at entry_id collision                                                                                   |
| 6   | Entries K and K+1 swapped (adjacent reorder)                                                                                                                         | FAIL at K's parent_hash mismatch                                                                             |
| 6b  | Entries K and K+M swapped, M ≥ 5 (non-adjacent reorder; carry-forward R3-M-01 per `workspaces/phase-01-mvp/04-validate/round-4-implementation-comprehensive.md` § 4) | FAIL at K's parent_hash mismatch — verifier MUST detect non-adjacent (i, j) reorder, not only adjacent swaps |
| 7   | Entry K's `lamport_clock.lamport_time` decreased                                                                                                                     | FAIL at Lamport monotonicity                                                                                 |
| 8   | Entry K's `algorithm_identifier` mismatches segment                                                                                                                  | FAIL with `LedgerAlgorithmMismatchError`                                                                     |

Verifier MUST detect every form and identify the failing entry index. Per `rules/orphan-detection.md` Rule 2a, the round-trip is THROUGH the facade — `envoy ledger export` produces the bundle; the separately-codebased `envoy-ledger-verify` consumes it.

#### Acceptance gate

Per `02-mvp-objectives.md` EC-4 line 67: ledger export verified by separately-codebased CLI tool (a) different repo, (b) zero source share, (c) different language OR different agent. Tampering battery detects every form.

#### Cross-OS portability

`tests/e2e/test_envoy_ledger_cross_os_byte_identity.py` — same `EnvoyLedger.append(...)` sequence on macOS / Linux / Windows; JSON exports byte-identical (modulo per-device `device_id`); chain hash sequence identical.

---

### EC-5 — Trust Vault backup via SLIP-0039 Shamir 3-of-5 reconstruct

**Owning primitive**: shard 15 (Shamir) + shard 5 (Trust store).

#### Tier 2 wiring

- `tests/integration/test_shamir_ritual_coordinator_wiring.py` — imports `ShamirRitualCoordinator` through facade; runs full 6-step ritual; asserts master-key zeroization post-call.
- `tests/integration/test_shamir_paper_renderer.py` — 24-word card format; opaque slot label only; NO "Envoy" label, NO real holder name.
- `tests/integration/test_shamir_commitments_bound_to_genesis.py` — `Genesis.shard_public_commitments` populated; mismatched shard at recovery raises `CommitmentVerificationFailedError`.
- `tests/integration/test_trust_store_shamir_master_key_export_import_round_trip.py` — `export_master_key_for_shamir()` → `shamir.generate(...)` → `shamir.reconstruct(...)` → `import_master_key_from_shamir()` restores original.

#### Tier 3 end-to-end battery — the EC-5 10-combinations + cross-tool interop

`tests/e2e/test_shamir_all_10_combinations.py` — for a generated 5-card set, exhaustively test all C(5,3) = 10 share combinations:

```
combinations = [(c1,c2,c3), (c1,c2,c4), (c1,c2,c5), (c1,c3,c4), (c1,c3,c5),
                (c1,c4,c5), (c2,c3,c4), (c2,c3,c5), (c2,c4,c5), (c3,c4,c5)]
```

Each MUST reconstruct the original master key bytes byte-identical.

`tests/e2e/test_shamir_cross_tool_interop.py` — Envoy-generated SLIP-0039 share reconstructed by `python-shamir-mnemonic` (audited reference impl) WITHOUT calling Envoy code. Bidirectional: a `python-shamir-mnemonic`-generated share also reconstructs via Envoy.

`tests/e2e/test_shamir_plain_language_errors.py` — for each of the 9 typed errors (`InsufficientSharesError`, `ShardChecksumFailedError`, etc.), the surfaced message is plain-language English per `rules/communication.md`, NOT a binary-data dump.

#### Acceptance gate

Per `02-mvp-objectives.md` EC-5 lines 78–80: (a) all C(5,3)=10 combinations reconstruct successfully, (b) Boundary Conversation pauses for backup ritual at least once, (c) Envoy-generated share reconstructable via `python-shamir-mnemonic` minimum (Trezor SDK if accessible), (d) reconstruction failures produce plain-language errors.

#### Cross-OS portability (BET-9b)

`tests/e2e/test_trust_store_cross_os_portability.py` — Trust Vault + Trust Store SQLite created on macOS unlocks correctly on Linux + Windows (and vice versa). Shamir cards generated on one OS reconstruct on another.

---

### EC-6 — `/redteam` passes: 0 CRITICAL/HIGH × 2 consecutive rounds

**Owning primitive**: every primitive shard contributes; redteam is shards 23–24.

Detail in `02-plans/04-redteam-cycle-plan.md`. Acceptance gate: 2 consecutive `/redteam` rounds with 0 CRIT + 0 HIGH per `rules/specs-authority.md` MUST Rule 5b inherited convergence semantics.

---

### EC-7 — Single user onboards via any of 8 channels (CLI + Web + 6 messaging)

**Owning primitive**: shard 16 (Channel adapters) + shard 8 (Boundary Conversation) + shard 14 (Connection Vault).

#### Tier 2 wiring

- `tests/integration/channels/test_<channel>_adapter_lifecycle.py` × 8 channels — `startup` + `shutdown` per channel against real vendor sandbox (Telegram test bot, Slack ngrok-tunneled webhook, Discord test guild, WhatsApp Business sandbox, BlueBubbles local server, signal-cli REST, CLI stdin, Web localhost).
- `tests/integration/channels/test_<channel>_send_message.py` × 8 — `send_message` returns `SendReceipt`.
- `tests/integration/channels/test_<channel>_ritual_delivery.py` × 8 — `send_grant_moment` + `send_digest` per channel.
- `tests/integration/test_inbound_router_wiring.py` — `asyncio.gather` over every adapter routes to active session.
- `tests/integration/test_credential_resolver_wiring.py` — each adapter's `startup(config)` resolves entry from Connection Vault.
- `tests/integration/test_h03_primary_channel_binding.py` — high-stakes Grant Moment refused on non-primary channel with `NotPrimaryChannelError`.
- `tests/regression/test_t018_visible_secret_per_channel.py`, `test_t070_clipboard_autoclear.py`, `test_t080_tls13_pin.py`, `test_t023_signal_path_b.py`.

#### Tier 3 end-to-end battery — the EC-7 8-channel × N=3 onboarding battery

`tests/e2e/test_session_continuity_8_channels.py` — for each of 8 channels, run N=3 first-time-user sessions starting from that channel:

```
8 channels × 3 sessions = 24 successful onboardings
```

Per channel × per session: completes Boundary Conversation, produces parseable `EnvelopeConfig`, lands credentials in Connection Vault, registers session in Trust store. Per-channel deviation from CLI baseline (in completion time, message count) MUST stay within 2×.

#### Acceptance gate

Per `02-mvp-objectives.md` EC-7 line 104: 24 successful onboardings (8 channels × N=3); per-channel deviation ≤2× CLI baseline.

#### De-scope #1 fallback

If iMessage + Signal fail Tier 3 onboarding (per `01-shard-plan.md` § 5 wave-D row "iMessage/Signal feasibility — already encoded in spec lines 172–173"), execute pre-declared de-scope #1 (`02-mvp-objectives.md` line 171): reduce to 5 channels (CLI + Web + Telegram + Slack + Discord). EC-7 acceptance becomes 15 onboardings (5 × N=3).

---

### EC-8 — User operates for a week across channels

**Owning primitive**: shard 5 (Trust store) + shard 6 (Ledger) + shard 4 (Envelope compiler) + shard 16 (Channel adapters).

#### Tier 2 wiring

- `tests/integration/test_trust_store_cross_channel_session_id_resolution.py` — `session_id` resolved via Trust store; same `session_id` returned for the same principal across every adapter.
- `tests/integration/test_envoy_ledger_query_filter_principal_id.py` — per-principal Ledger query is tenant-isolated (`rules/tenant-isolation.md` Rule 1).
- `tests/tier2/test_envelope_compiler_session_envelope_byte_identity.py` — Day-1 envelope compiled on CLI; Day-6 action initiating from Slack reads the SAME `content_hash` byte-identical.
- `tests/tier2/test_grant_moment_cascade_cross_channel.py` — Day-1 grant on Telegram → Day-6 child grant on Slack → revoke Day-1 → cascade reaches Day-6 grant.
- `tests/tier2/test_budget_no_double_billing_multi_channel.py` — same intent_id across two channels does NOT double-charge the budget.

#### Tier 3 end-to-end battery — the EC-8 7-day cross-channel coherence

`tests/e2e/test_envoy_7_day_cross_channel_coherence.py` — 7-day operating window across ≥4 of 8 channels, with daily cross-channel state-equivalence test:

| Day | Action                                          | Channel        | Asserts                                                              |
| --- | ----------------------------------------------- | -------------- | -------------------------------------------------------------------- |
| 1   | Onboarding completes; envelope compiled         | CLI            | `EnvelopeConfig` written; first Grant Moment fires                   |
| 1   | Grant Moment approve_once                       | Telegram       | `DelegationRecord` written; `grant_moment` Ledger row                |
| 2   | Daily Digest fires                              | All configured | Day-1 actions visible in digest                                      |
| 3   | Out-of-envelope action triggers Grant Moment    | Slack          | New Grant Moment fires; resolved Approve+author                      |
| 4   | (offline day; user does not interact)           | —              | Next-day digest back-fills                                           |
| 5   | Daily Digest fires with back-fill               | All configured | Day-4 missed delivery banner present                                 |
| 6   | Child grant initiated under Day-3 grant         | Discord        | Cascades correctly through Day-3 → Day-6                             |
| 7   | User revokes Day-1 grant via Daily Digest reply | Telegram       | Cascade revocation reaches Day-3 + Day-6 grants from Slack + Discord |

Cross-channel state-equivalence test runs daily: query Trust store for active grants; query Ledger for grant_moment entries; assert sets agree across channels (no drift).

Per-channel non-double-billing test: a tool call that touches 2 channels (e.g., a Telegram-initiated send through Slack) charges Budget once, not twice.

#### Acceptance gate

Per `02-mvp-objectives.md` EC-8 line 116: (a) zero state-drift findings, (b) no double-billing, (c) cascade revocation of Day-1 grant correctly revokes Day-6 child grant from a different channel.

---

### EC-9 — Independent ledger verifier ships separately-codebased

**Owning primitive**: shard 7 (Independent verifier).

#### Tier 2 wiring (in the verifier's own repo, NOT Envoy's)

- `tests/integration/test_verifier_consumes_envoy_export.py` — verifier reads `envoy ledger export` JSON output; verifies chain.
- `tests/integration/test_verifier_trust_anchor_self_anchoring.py` — first-verification self-anchoring; subsequent verifications honor the anchor.
- `tests/integration/test_producer_verifier_wire_shape_round_trip.py` (R2-H-01 regression) — produces a `DelegationRecord` via `TrustStoreAdapter`, parses it via Independent Verifier's bundle parser, asserts the `algorithm_identifier` dict has 3 keys (`sig`, `hash`, `shamir`) matching `specs/trust-lineage.md` line 24. Verifies the producer-side single-point translation helper `TrustStoreAdapter._to_spec_wire_form()` (shard 5 § 4) produces the spec-mandated 3-key wire form that the Independent Verifier consumes per `specs/independent-verifier.md` line 35.

#### Tier 3 end-to-end battery — the EC-9 source-isolation gate

`tests/e2e/test_envoy_ledger_independent_verifier_ec9.py` (in Envoy's repo, runs the verifier as a subprocess):

1. Spawn shard-7 verifier (separate codebase) against an Envoy-produced export.
2. Verifier MUST NOT have ANY Envoy import statement (`grep -rln 'import envoy' verifier/` returns empty).
3. Verifier passes all 8 tampering forms from EC-4's tampering battery.
4. Verifier accepts ZERO Envoy fixtures — only the export bundle's bytes.

#### Acceptance gate

Per `02-mvp-objectives.md` EC-9 line 128: verifier ships in separate repo (`envoy-ledger-verifier` under `terrene-foundation/`); implemented without reference to Envoy producer source; in either Python (different agent / different package) or Rust (different language). Passes EC-4 tampering battery.

---

## 3. Cross-cutting test patterns (apply to every primitive)

### 3.1 Wiring tests per `rules/orphan-detection.md` MUST Rule 2

For every primitive that exposes a manager-shape facade (`*Service`, `*Orchestrator`, `*Manager`, `*Adapter`, `*Coordinator`):

- Test file MUST be named `test_<lowercase>_wiring.py`.
- Test MUST import through the framework facade (e.g., `from envoy.ledger import EnvoyLedger`), NOT the underlying class directly.
- Test MUST construct a real Envoy instance against real infrastructure.
- Test MUST trigger a code path ending in at least one method on the facade.
- Test MUST assert externally-observable effect (a row in SQLite; a redacted field in a read result; a record in the metrics counter).

### 3.2 Crypto-pair round-trip per `rules/orphan-detection.md` MUST Rule 2a

Every paired crypto operation (`encrypt`/`decrypt`, `sign`/`verify`, `seal`/`unseal`, `wrap_key`/`unwrap_key`, `seed_genesis`/`verify_chain`, `record_delegation`/`revoke`) MUST have at least one Tier 2 round-trip test THROUGH the facade. Two unit tests that mock each other's halves are BLOCKED.

### 3.3 Tenant-isolation per `rules/tenant-isolation.md`

Every primitive's persistence MUST include `principal_id` as a key dimension from day 1. Tier 2 test asserts:

- Missing `principal_id` raises `PrincipalRequiredError` (Rule 2 strict mode).
- Cache key shape contains `principal_id` (Rule 1).
- Invalidation accepts optional `principal_id` (Rule 3); version-wildcard sweep (`v*`) per Rule 3a.

### 3.4 Event-payload classification per `rules/event-payload-classification.md`

Every primitive that emits a `DomainEvent` (or equivalent Ledger row referencing classified PKs) MUST route through `format_record_id_for_event` at the SINGLE EMISSION POINT, not at call sites. Tier 2 test:

```python
received = []
db.on_model_change("Account", lambda evt: received.append(evt))
await db.express.create("Account", {"id": "alice@tenant.example", ...})
assert received[0].payload["record_id"].startswith("sha256:")
assert "alice@tenant.example" not in repr(received[0].payload)
```

### 3.5 Spec-compliance verification per `skills/spec-compliance/SKILL.md`

For every spec acceptance assertion (signatures, fields, decorators, MOVE shims, security tests), `/redteam` runs AST/grep verification, NOT file-existence checking. Per `rules/testing.md` § Audit Mode Rules, re-derive coverage from scratch each round.

### 3.6 Pytest-xdist safety

Per `rules/testing.md` § Env-Var Test Isolation: any Tier 2 test that mutates `ENVOY_*` env vars MUST hold the module-scope lock; verified under `pytest-xdist -n auto`.

### 3.6a Heartbeat stub no-op wiring + Phase 02 module non-call regression (R2-H-02)

Per `rules/zero-tolerance.md` Rule 2 + `rules/orphan-detection.md` Rule 1 + Rule 4a, the heartbeat 5-stub partition (shard 17 § 7.3 fix) requires two distinct test surfaces:

- `tests/integration/test_heartbeat_stub_no_op_wiring.py` (R2-H-02 regression) — invokes `HeartbeatClient.maybe_record_flag('completed_boundary_conversation')` from a real `BoundaryConversationRuntime` completion path, asserts NO exception, NO Ledger entry, NO network call. Verifies the 21 emit-site primitives (across shards 8/9/10/11/12/16/18) call into the genuine no-op `HeartbeatClient` — never into any of the four `PhaseDeferredError` network/crypto modules.

- `tests/regression/test_no_envoy_heartbeat_phase02_module_call_sites.py` (R2-H-02 regression) — greps `envoy/` (excluding tests) for imports of `envoy.heartbeat.{star_prio,ohttp,signed_consent,registry}`; asserts zero matches. The grep is the structural defense per `rules/orphan-detection.md` Rule 4a — when Phase 02 entry replaces the `PhaseDeferredError` body with a real implementation, this regression flips green automatically and any premature Phase 01 caller surfaces as a HIGH finding.

### 3.7 Per-package collect-only gate per `rules/orphan-detection.md` MUST Rule 5a

`pytest --collect-only -q` MUST return exit 0 per-package (NOT combined root invocation):

```bash
for pkg in tests/tier{1,2,3} packages/*/tests; do
    pytest --collect-only -q "$pkg" --continue-on-collection-errors
done
```

---

## 4. Test infrastructure stack

| Layer                  | Component                                                                                                              | Phase 01 source                      | Notes                        |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------ | ---------------------------- |
| Unit runner            | `pytest` + `pytest-asyncio`                                                                                            | dev dep                              | Tier 1                       |
| Integration runner     | `pytest` + real SQLite + real `keyring`                                                                                | dev dep                              | Tier 2                       |
| Real LLM (CI)          | Ollama with `qwen2.5:7b`                                                                                               | docker-compose                       | Tier 2 + Tier 3 CI           |
| Real LLM (staging)     | real Anthropic Claude / OpenAI GPT                                                                                     | `.env` API keys via Connection Vault | Tier 3 staging               |
| Real keychain          | macOS Keychain / Linux Secret Service / Windows Credential Manager                                                     | OS native                            | Tier 2 + Tier 3              |
| Real channel sandboxes | Telegram test bot / Slack ngrok / Discord test guild / WhatsApp Business sandbox / BlueBubbles local / signal-cli REST | per-channel                          | Tier 2 channel adapters      |
| Real scheduler         | `apscheduler.AsyncIOScheduler` with shortened intervals                                                                | upstream dep                         | Tier 2 Daily Digest          |
| Cross-OS matrix        | macOS + Linux + Windows x86_64                                                                                         | GitHub Actions                       | Tier 3 portability           |
| Time acceleration      | freezegun / pytest-freezer                                                                                             | dev dep                              | Compress 7-day windows in CI |
| Tampering battery      | byte-level fixture mutation harness                                                                                    | Envoy-new test util                  | EC-4 / EC-9                  |

---

## 5. Cross-references

- Tier definitions: `.claude/rules/testing.md` § 3-Tier Testing.
- Wiring discipline: `.claude/rules/orphan-detection.md` MUST Rule 1, Rule 2, Rule 2a.
- Facade detection: `.claude/rules/facade-manager-detection.md` Rule 1, Rule 2, Rule 3.
- Tenant isolation: `.claude/rules/tenant-isolation.md`.
- Event classification: `.claude/rules/event-payload-classification.md`.
- Spec compliance: `.claude/skills/spec-compliance/SKILL.md`.
- Per-primitive test surfaces: `workspaces/phase-01-mvp/01-analysis/{04..19}-*-implementation.md` § 6.
- Build sequence: `workspaces/phase-01-mvp/02-plans/01-build-sequence.md`.
- Package skeleton: `workspaces/phase-01-mvp/02-plans/03-package-skeleton.md`.
- Redteam cycle: `workspaces/phase-01-mvp/02-plans/04-redteam-cycle-plan.md`.
- MVP objectives: `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` (9 ECs + acceptance gates).
