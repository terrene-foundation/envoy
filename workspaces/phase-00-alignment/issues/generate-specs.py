#!/usr/bin/env python3
"""Generate the 26 remaining spec files as focused extracts from their source analysis docs."""

from pathlib import Path

SPECS_DIR = Path("/Users/esperie/repos/dev/envoy/specs")

SPECS = {
    "runtime-abstraction.md": {
        "purpose": "Abstract `kailash-runtime` interface that Envoy programs against. Two shipped implementations (kailash-py + kailash-rs-bindings); byte-identical contract for spec-driven outputs, semantically-equivalent for LLM-composed outputs.",
        "source": "05-runtime-abstraction.md v2",
        "threats": "T-004 two-phase signing, T-015 envelope re-read checkpoint, T-050a/b binary threats, T-060 binary poisoning, T-105 subset-proof verifier",
        "bets": "BET-6 contract parity, BET-3 sovereignty (runtime pluggability)",
        "body": """## Abstract interface
`KailashRuntime` (ABC) with: `startup/shutdown`, `runtime_identity`, `trust_sign/verify_chain/cascade_revoke/verify_subset_proof`, `envelope_canonical_form/intersect/check/re_read_checkpoint`, `phase_a_sign_intent/phase_b_sign_outcome/phase_a_orphan_resolve`, `ledger_append/query/verify_chain/head_commitment`, `classifier_invoke/ensemble_aggregate`, `budget_reserve/record/snapshot/velocity_check`, `runtime_sign/verify`, `prompt_assemble`, `tool_output_sanitize`, `classifier_registry_resolve`, `first_time_action_gate`, `grant_moment_surface`.

## `RuntimeIdentity`
`{runtime_family, version, binary_hash, device_bound_pubkey_hex, algorithm_identifier}`.

## Runtime device key (§4)
Distinct from user Genesis. Lives in Secure Enclave / TPM / software-fallback. Signs Phase B, SubsetProof re-verification, HALTED records, head commitments. Rotation via `RuntimeKeyRotationRecord` dual-signed (old + new runtime keys) + user-Genesis co-signature (F-02 fix — prevents self-rotation under runtime compromise).

## Two-phase signing (doc 00 v3 §8 Test-2)
Phase A intent pre-execution (delegation-key-signed); Phase B outcome post-execution (runtime-device-key-signed); orphan resolution at next session start with Grant Moment.

## Contract partition (BET-6)
**Byte-identical:** `envelope_canonical_form`, `trust_sign`, `delegation_id` hashing, ledger hash chain, `cascade_revoke` SET equality, `envelope_intersect`, subset-proof runtime_verification_signature, head_commitment.

**Semantically-equivalent:** agent LLM responses, Grant Moment prompt text, tool-call timing metadata.

## Conformance vectors N1–N6 decoded
- **N1** Knowledge Filter (pre-retrieval gate).
- **N2** Envelope Cache (5-property invalidation).
- **N3** Reserved placeholder.
- **N4** Verdict rendering.
- **N5** Posture ceiling.
- **N6** Sixth pattern placeholder.

## Envoy-specific conformance E1–E7
- **E1** Envelope canonical JSON (67 vectors).
- **E2** Delegation Record signing (20 vectors).
- **E3** Cascade revocation BFS/DFS set-equality (15 vectors).
- **E4** Cycle detection (15 vectors).
- **E5** Subset-proof verification (20 adversarial vectors).
- **E6** Two-phase signing orphan resolution.
- **E7** Ledger head-commitment monotonicity.

## Runtime picker (§8 Phase 02)
First-run picker: kailash-rs-bindings default vs kailash-py opt-in. Switch via `envoy runtime switch` — requires (a) passphrase unlock (not warm), (b) Genesis-signed `RuntimeSwitchRecord`, (c) runtime-attestation verification of target.

## Security gates per phase
- **Phase 00:** abstract interface spec published + binding-gap GH issues tracked.
- **Phase 01:** kailash-py impl; E1–E7 vectors pass; two-phase + envelope re-read functional; algorithm-identifier schema landed.
- **Phase 02:** kailash-rs-bindings impl; BET-6 contract parity; N1–N6 Python runner (kailash-py#605); binary hash verification; N=3 mirrors; reproducible-build stream.
- **Phase 03:** semantic-equivalence harness; multi-device runtime switch.
- **Phase 04:** multi-provider verification; PQ migration planning.

## Error taxonomy
`RuntimeNotReadyError`, `RuntimeShutdownError`, `AlgorithmIdentifierMismatchError`, `PhaseAIntentSigningFailedError`, `PhaseBOrphanError`, `LedgerRollbackDetectedError`, `LedgerVerificationFailedError`, `ClassifierUnavailableError`, `RuntimeSignatureVerificationFailedError`, `BudgetExhaustedError`, `BudgetVelocityExceededError`.

## Cross-references
All other specs. Runtime is the composition layer.""",
    },
    "threat-model.md": {
        "purpose": "50 enumerated threats + mitigation-to-primitive matrix + residual risk register + per-phase security-review gates.",
        "source": "09-threat-model.md v3 FROZEN",
        "threats": "ALL 50 threats catalogued here",
        "bets": "Tests every doc 00 BET's defense primitives",
        "body": """## Threat categories
STRIDE (S/T/R/I/D/E) + Envoy-specific (PI/GOV/UX/SC/CTX).

## Threats (50 total)
See doc 09 v3 §3 for full detail. Summary:
- **T-001–T-007** carry-forwards from doc 00 §13 (clock-skew, household-adversarial, ledger retention, streaming LLM pre-sign, semantic envelope, Shamir social-graph, credential storage).
- **T-008** Grant Moment replay.
- **T-010–T-017** prompt injection + context-window + feedback-loop + goal drift + training-data extraction.
- **T-018–T-019** Grant Moment spoofing + habituation.
- **T-020–T-024** skill/envelope supply-chain + authorship gaming + enterprise delegation-upward.
- **T-030** compromised model provider.
- **T-040–T-042** device threats.
- **T-050a/T-050b** Foundation binary mirror vs signing-key.
- **T-051–T-054** Foundation infra + Heartbeat covert channel.
- **T-060–T-061** runtime binary poisoning.
- **T-070–T-071** side channels.
- **T-080** network MITM.
- **T-090–T-094** DoS variants.
- **T-100–T-107** Ledger + trust-lineage crypto + sub-agent forgery + A2A collusion + recursive spawn DoS.

## Mitigation-to-primitive matrix
50 threats × {primary mitigation, spec location, test location, phase}. Full matrix in doc 09 v3 §4.

## Residual risks
Explicitly enumerated per doc 09 v3 §6 (13 residuals). Includes: clock-forward spoofing during write window, kernel-level keylog, sophisticated duress-latency detection, jurisdictional compulsion, all-3-mirrors compromised, 2-of-N Foundation colluding, relay+aggregator colluding, sync metadata patterns, classifier arms race, Phase-A-to-B window, platform accessibility misuse, device-wide exhaustion outside Envoy, PQ migration timing.

## Out of scope
Nation-state full-spectrum, device-level kernel/hypervisor/firmware compromise, physical TEMPEST, hardware keylogger, regulated-industry compliance (deployment concern), adversarial unrelated-user multi-tenant, legal-process jurisdictional edge cases.

## Phase gates
- **Phase 00:** crypto library audit, Shamir lib selection, OHTTP lib selection, abuse-survivor advisory engagement, legal counsel 7 items.
- **Phase 01:** threat-model test suite green, binding-gap security fixes closed (kailash-rs#520 SQLi), algorithm-identifier live, Ledger content_trust_level + signature-scope review, Grant Moment visual-secret UX review, trust-lineage cycle-detect corpus, envelope-version binding conformance, T-093 budget-velocity test, algorithm-identifier Phase 01 exit gate.
- **Phase 02:** full binding security audit, OHTTP/STAR review, FV tier signing ceremony, CRDT-merge external review, reproducible-build stream.
- **Phase 03:** Shared Household abuse-survivor review, sub-agent derivation proof external review, enterprise-mode cryptographic attestation review, Envelope Library Sybil defense review.
- **Phase 04:** WASM sandbox audit, multi-provider verification review, hidden-envelope deniability review.
- **Ongoing:** regression tests, CVE scans, reproducible-build verification, classifier-ensemble quarterly update review.

## Cross-references
Every spec file in this directory. threat-model.md is the integration point — each primitive elsewhere references back here for the threats it mitigates.""",
    },
    "data-model.md": {
        "purpose": "Every persisted entity's schema + storage location + retention + serialization + export format.",
        "source": "10-data-model.md v1",
        "threats": "T-003 retention, T-012 content_trust_level, T-040 lost device, T-053 sync compromise",
        "bets": "BET-3 sovereignty (local-first), BET-9b binding compatibility",
        "body": """## Four physical containers
1. **Trust Vault** — Envoy's keys + envelope + posture + Shamir commitments + ritual state + Ledger head + Heartbeat client state. Encrypted AES-256-GCM; master key from Argon2id passphrase + Secure Enclave XOR. Opt-in sync (ciphertext).
2. **Connection Vault** — third-party credentials in OS keychain. Per-principal isolated (Phase 03). NEVER synced.
3. **Ledger** — hash-chained append-only; per-entry encryption; opt-in sync.
4. **Shadow segment** — local-only, never-synced. Duress events, clock-skew history, runtime internal signals. Encrypted with real-passphrase-only key.

## Trust Vault regions
Envelope / Posture history / Shamir commitments / Ritual state / Chain head commitment / Enterprise deployment cache / First-time-action fingerprints / Hidden envelope region (Phase 04 + padded dummy Phase 01–03).

Padding buckets: 1 MiB, 4 MiB, 16 MiB, 64 MiB — vault lands in a bucket; file size does not distinguish hidden-envelope presence.

## Connection Vault per-entry schema
`{entry_id, principal_genesis_id, credential_type, service_identifier, entry_envelope_scope, ciphertext, created_at, last_used_at, expires_at, usage_counter, rotation_policy}`.

Platforms: macOS Keychain / Windows Credential Manager / Linux Secret Service / iOS Secure Enclave / Android Keystore.

## Ledger materialized indexes
Rebuilt from Ledger replay at startup; cached in Trust Vault:
- Envelope history (version → entry_id).
- Authorship Score history (cumulative events).
- Heartbeat counters (since-last-send).

## Retention
- Trust Vault: forever (until key destruction).
- Connection Vault: until user removes OR credential expires.
- Ledger: user-declared policy per envelope; tombstone + per-entry key destruction supported.
- Shadow segment: forever locally; never syncs.

## Sync
- Trust Vault + Ledger: opt-in via native Foundation node + third-party (iCloud/Dropbox/Keybase/WebDAV/S3/git).
- Protocol: versioned 256 KiB chunks; constant-write-rate; dual head-commitments.
- Connection Vault: NEVER.
- Shadow segment: NEVER.

## Export
`envoy vault export` (Shamir-protected); `envoy ledger export --format json|pdf`.

## Cross-references
All specs. data-model.md is the persistence layer for every primitive.""",
    },
    "grant-moment.md": {
        "purpose": "Per-action consent state machine; Delegation Record production; visual-secret binding; novelty-aware friction.",
        "source": "01-ux-rituals.md v2 §4",
        "threats": "T-018 dialog spoofing, T-019 habituation, T-093 velocity ratchet",
        "bets": "BET-1 authorship, BET-12 governance-primary-surface",
        "body": """## State machine
M0 construct → M1 render (all active channels) → M2 await decision (5min default timeout; per-envelope override) → M3 sign or decline → M4 complete.

## Rendering
Every dialog shows:
- Visible secret (icon + color + phrase, stored in Trust Vault).
- Proposed action (tool + args summary).
- Why asking (envelope violation / composition rule / first-time / velocity).
- Consequence preview (budget, reversibility, recipient, data).
- Options: Approve once / Approve+author / Deny / Modify.

## Novelty-aware friction (T-019)
- **Novel pattern** (unseen recipient, new dollar range outside ±25% of 30-day P50, tool unseen in last 7 days, new N-gram sequence) → 5s read-delay + double-tap + cross-channel confirm for high-stakes.
- **Familiar repeat** → batch-to-envelope conversion offer at Weekly Posture Review.
- Primary-channel binding — high-stakes Grant Moments render ONLY on user's designated primary channel.

## Velocity-raise ratchet (T-093 R2-H4)
Raising velocity limits CANNOT be approved inline. Requires Weekly Posture Review OR cross-channel Grant Moment with 24h cooling-off.

## Cross-principal (Phase 03)
Dual-signed if affects both principals. First principal's dialog → second principal's dialog on their channel. Action executes only after both signed. 24h cooling-off for high-stakes.

## Timeout
Default 5min. Identical behavior between real + honeypot paths (prevents duress latency distinguisher). Queue back-pressure after N parallel Grant Moments.

## Produced artifact
Signed `DelegationRecord` per specs/trust-lineage.md + Phase A intent per specs/ledger.md §two-phase signing.

## Cross-references
- specs/envelope-model.md — composition rules + first-time-action gate trigger.
- specs/trust-lineage.md — Delegation Record signing.
- specs/ledger.md — Grant Moment Ledger entries.
- specs/channel-adapters.md — per-channel rendering.
- specs/boundary-conversation.md — visible secret setup.""",
    },
    "boundary-conversation.md": {
        "purpose": "First-run onboarding dialogue that compiles EnvelopeConfig.",
        "source": "01-ux-rituals.md v2 §3",
        "threats": "T-018 visible secret setup, T-023 Authorship Score seeding",
        "bets": "BET-1 authorship, BET-12 palatability",
        "body": """## State machine
S0 greet → S1 money → S2 people → S3 topics → S4 hours → S5 first task → S6 template offer → S7 visible secret setup → S8 Shamir ritual → S9 review & sign → S10 complete.

## Questions
S1: monthly ceiling USD.
S2: blocked contacts.
S3: blocked topics (semantic rules).
S4: operating hours.
S5: first-task intent.
S6: template import (Foundation-Verified only in Phase 01 local cache) OR from-scratch.
S7: visible secret (icon + color + phrase).
S8: Shamir 3-of-5 default; 5-in-safes alternative; custom.
S9: plain-language envelope summary + sign.

## Duration
~15min target. 8min minimum-path (template + visible secret + Shamir).

## Persistence + resume
Every answer transition persists state to Trust Vault. `envoy init --resume <ritual_id>` rehydrates.

## Novelty feedback (T-023)
If user-authored answer compiles to near-duplicate (Jaccard > 0.85 or adversarial-wording classifier > 0.8) of template constraint, UX prompts user to rephrase or re-choose.

## Post-duress review step (§3.5a — V2 C-02 fix)
After first-run real unlock, if shadow segment contains unread duress event, a banner surfaces above Boundary Conversation with visible-secret-bound Modal detailing duress time + recommended immediate actions.

## Cross-references
- specs/envelope-model.md — EnvelopeConfig compile target.
- specs/authorship-score.md — novelty + minimum-impact algorithms.
- specs/shamir-recovery.md — ritual flow.
- specs/trust-vault.md — visible secret + ritual state storage.""",
    },
    "daily-digest.md": {
        "purpose": "Morning ritual delivering 2-min action/refusal/spend summary + pending Grant Moments.",
        "source": "01-ux-rituals.md v2 §5",
        "threats": "T-019 habituation defense via low-engagement fallback",
        "bets": "BET-8 habit formation",
        "body": """## Schedule
User-configured delivery time (default 8am local). User-chosen channel (default first-connected).

## Content template
Actions (with outbox items), refusals, spend (of monthly ceiling), pending Grant Moments, today's planned actions, reply prompt.

## Interaction
- Reply "no"/no-reply: proceed with planned actions.
- Reply "yes"/modify: extract user changes + apply.
- Reply "skip digest": temporarily disable.

## Low-engagement fallback
<2 Digest opens/week for 3 weeks → offer 3-line compact form or event-driven-only delivery (fires on Grant Moment pending or budget > 80%).

## Channel-adaptive rendering
Email/Web: rich format + attachments. Telegram/Slack/Discord: inline buttons. SMS/WhatsApp: compact 10-line. CLI: on `envoy digest today`.

## Shadow-segment post-duress surface (V2 C-02 fix)
If unread duress event in shadow segment at Digest time, Digest renders with priority banner + `[Review duress event]` button.

## Cross-references
- specs/channel-adapters.md — per-channel rendering.
- specs/ledger.md — action summary source.
- specs/trust-lineage.md — shadow segment access.""",
    },
    "weekly-posture-review.md": {
        "purpose": "Sunday 90-second ritual for posture + envelope recalibration; batch-to-envelope conversion; authorship nudge.",
        "source": "01-ux-rituals.md v2 §6",
        "threats": "T-019 rubber-stamp via batch-to-envelope conversion",
        "bets": "BET-8 habit, BET-12 authorship",
        "body": """## Phase 03 deliverable.

## State machine
W0 intro → W1 summary → W2 posture recommendation → W3 velocity requests → W4 authorship nudge → W5 sign changes → W6 complete.

## Content
- Last-week summary (actions/refusals/spend/Grant Moments).
- Posture recommendation (up/down based on behavior).
- Pending velocity-raise requests (requires 24h cooling-off per H-05 fix).
- Authorship nudge (if score stagnant).

## Discipline
- Skippable; 3-weeks-skipped → cadence re-evaluation prompt.
- All posture RAISES: 5s read-delay before approve.
- Velocity-raise confirmation: 24h cool-off from Sunday sign to Monday effect.

## Cross-references
- specs/envelope-model.md — posture ratchet + velocity rules.
- specs/grant-moment.md — batch-to-envelope conversion.
- specs/authorship-score.md — score calculations.""",
    },
    "monthly-trust-report.md": {
        "purpose": "Month-end PDF + JSON export; shareable delegation graph + budget + posture trajectory.",
        "source": "01-ux-rituals.md v2 §7",
        "threats": "T-054 covert channel via sharing → redaction per classification-policy",
        "bets": "BET-8 habit, BET-4 credibility",
        "body": """## Phase 03 deliverable.

## Content
- Full delegation graph (Sankey).
- Budget history (line chart).
- Actions/refusals/escalations.
- Envelope violation attempts.
- Posture trajectory.
- Skill inventory + provenance + force_install flags.
- Classifier-version history.
- Cryptographic receipt hash.

## Delivery
- Archived in `~/envoy/reports/YYYY-MM.{pdf,json}`.
- Signed by user's Genesis key.
- Shareable via `envoy report YYYY-MM share --section X --public` — publicly-shared sections route classified identifiers through `format_record_id_for_event` (sha256-8hex prefix) per classification-policy.

## Cross-references
- specs/ledger.md — data source.
- specs/classification-policy.md — redaction rules for shared sections.
- specs/trust-lineage.md — delegation graph.""",
    },
    "shamir-recovery.md": {
        "purpose": "SLIP-0039 Shamir 3-of-5 default ritual; shard generation, distribution, recovery, rotation.",
        "source": "01-ux-rituals.md v2 §8 + 03-trust-lineage.md v2 §2",
        "threats": "T-006 shard social-graph defense (default-to-safes)",
        "bets": "BET-3 sovereignty (Trust Vault backup)",
        "body": """## Algorithm
SLIP-0039 via audited libraries: Rust `sharks` / `vsss-rs`; Python `slip39` / `python-shamir-mnemonic`. Phase 00 crypto audit required.

## Default threshold
3-of-5. User-configurable 2-of-3 to 5-of-9.

## Distribution guidance (T-006 defense)
Default: 3 cards in user's own safes, 2 with trusted humans.
Alternative: 5 in user's own safes (no human holders) — recommended for high-OPSEC users.

## Card format
24 BIP-39 words; Trezor-compatible.
NO "Envoy" label; NO name. Distribution checklist persists only opaque slot labels in Trust Vault; real names optional + in hidden envelope (Phase 04) only (H-06 fix).

## Recovery flow
Enter words from any 3 cards (any order). Per-card checksum validation at entry (L-03 fix). Reconstruction; vault unlock.

## Rotation ritual
When shard-holder becomes unreachable (death, estrangement, relocation): `envoy shamir rotate`. New 5 cards; 4 non-rotated old cards remain valid for 30-day grace period, then deprecated.

## Shard public commitments
Per specs/trust-lineage.md — Genesis Record carries `shard_public_commitments: [algo:hash]` array for recovery verification without shard exposure.

## Cross-references
- specs/trust-lineage.md — Genesis Record integration.
- specs/trust-vault.md — master key splitting.
- specs/boundary-conversation.md — S8 ritual step.""",
    },
    "trust-vault.md": {
        "purpose": "Encrypted local storage of Envoy's own keys + envelope + posture + ritual state.",
        "source": "10-data-model.md v1 §2",
        "threats": "T-040 lost/stolen device, T-041 duress, T-042 key destruction, T-071 memory disclosure",
        "bets": "BET-3 sovereignty",
        "body": """## File format
Binary with magic-bytes header, algorithm_identifier, padding-bucket size, encrypted master key (Shamir-wrapped), encrypted regions (envelope / posture / Shamir commitments / ritual state / chain head / enterprise cache / first-time fingerprints / hidden envelope), padding, MAC tag.

## Encryption
- Outer: AES-256-GCM.
- Master key: Argon2id from passphrase (m=2^17, t=3, p=1) XOR with Secure Enclave/TPM-bound secret.
- Per-region keys: HKDF-SHA-256 with region info-strings.

## Padding buckets
{1 MiB, 4 MiB, 16 MiB, 64 MiB}. Hidden envelope indistinguishable by size.

## Memory hygiene (T-071)
- Vault decrypted only for operation duration.
- Explicit zeroing via `zeroize` (Rust) or `ctypes.memset` (Python).
- Auto-lock after 15min idle (configurable).
- Lock-during-idle clears all in-memory secrets.

## Duress support (T-041)
Dual passphrase: real vs duress. Duress unlocks honeypot Genesis + honeypot Trust Lineage (distinct, per specs/trust-lineage.md §10). Shadow segment (§data-model.md §10) encrypted with real-passphrase-only key; never synced.

## Key destruction (T-042)
`envoy vault destroy-keys` CLI. Platform API eviction + overwrite + `KeyDestructionEvent` Ledger record. Irreversible.

## Hidden envelope (Phase 04)
Two passphrases, two Shamir sets, file-size padding, constant-write-rate, decryption-timing uniformity.

## Cross-references
- specs/trust-lineage.md — Genesis Record + Shamir commitments.
- specs/ledger.md — head commitments + per-entry keys.
- specs/connection-vault.md — distinct container.
- specs/shamir-recovery.md — master key splitting.""",
    },
    "connection-vault.md": {
        "purpose": "Third-party credential storage (API keys, channel tokens, OAuth refresh) — OS keychain wrapper, per-principal isolated.",
        "source": "10-data-model.md v1 §3",
        "threats": "T-007 credential storage; never-synced by design",
        "bets": "BET-3 sovereignty",
        "body": """## Distinct from Trust Vault
- Trust Vault: Envoy's own keys + envelope.
- Connection Vault: third-party credentials (API keys, channel bot tokens, OAuth refresh).

## Platforms
- macOS: Keychain access group specific to Envoy.
- Windows: Credential Manager.
- Linux: Secret Service (GNOME Keyring / KWallet).
- iOS: Secure Enclave.
- Android: Keystore.

## Per-entry schema
`{entry_id, principal_genesis_id, credential_type, service_identifier, entry_envelope_scope, ciphertext, created_at, last_used_at, expires_at, usage_counter, rotation_policy}`.

## Per-principal isolation (Phase 03)
Entries keyed by `principal_genesis_id`. Cross-principal access requires Grant Moment.

## Never synced
OS keychain is device-local by design. After Shamir recovery, user re-authenticates each channel/model via fresh Grant Moments.

## Clipboard hygiene
Grant Moment dialogs that capture credentials use secure-text-field inputs (bypass clipboard on iOS; Secret.Filled on Android). Auto-clear clipboard after N seconds (30 default).

## Cross-references
- specs/trust-vault.md — separate container; Shamir doesn't cover Connection Vault.
- specs/grant-moment.md — credential Grant Moment flow.
- specs/channel-adapters.md — channel credentials.
- specs/threat-model.md — T-007.""",
    },
    "foundation-health-heartbeat.md": {
        "purpose": "Opt-in anonymous aggregate telemetry via STAR/Prio + differential privacy + OHTTP + signed-consent Grant Moment.",
        "source": "00-thesis-and-scope.md v3 §5.0",
        "threats": "T-052 OHTTP compromise, T-054 covert channel, T-023/T-024 falsifiability measurement",
        "bets": "BET-1, BET-3, BET-4, BET-8, BET-12 measurement substrate",
        "body": """## Purpose
Narrow §4.1 item 7a carveout from no-phone-home posture. Enables BET falsifiability measurement under doc 00 §5.0 methodology.

## Design stack
1. **STAR (Signer-Anonymous Reporting Telemetry) or Prio** — client splits each report into encrypted shares; collector aggregates without individual values; k-anonymity k≥100.
2. **Differential privacy** — bounded noise on each counter; ε per-metric published.
3. **OHTTP (RFC 9458)** — Foundation Key Configuration Server; Relay (optionally third-party) strips source IPs.
4. **Signed consent** — opt-in Grant Moment producing signed Delegation Record; cascade-revocable.

## Payload
Per-install random ID (rotated quarterly; debounced per specs/ux-rituals L-01 fix), Envoy version, ~20 boolean flags, aggregated via STAR.

**Flags include:**
`completed_boundary_conversation`, `opened_daily_digest_this_week`, `completed_weekly_posture_review`, `opened_monthly_trust_report`, `grant_moment_novelty_approved`, `grant_moment_novelty_denied`, `force_install_used_skill`, `authorship_score_reached_3`, `authorship_score_reached_5`, `posture_delegating_active`, `posture_autonomous_active`, `budget_monthly_exceeded_50pct`, `budget_monthly_exceeded_80pct`, `channel_telegram_active`, `channel_slack_active`, `channel_discord_active`, `channel_whatsapp_active`, `channel_signal_active`, `channel_imessage_active`, `runtime_kailash_rs_active`.

**Flags NEVER reported:** `duress_unlock_detected` (T-041 privacy preservation).

## Cadence
Weekly heartbeat. Counters reset on successful send.

## Consent layer
First-run Grant Moment with explicit text naming cryptographic properties. Default: opt-OUT. Revocation: cascade-revocable; no further heartbeats.

## Covert-channel defense (T-054)
- Reproducible builds detect compromised client.
- Differential privacy on flag entropy.
- Foundation-side periodic aggregate-payload audit.
- Fixed payload schema (client cannot add arbitrary fields).

## Cross-references
- specs/grant-moment.md — consent flow.
- specs/trust-lineage.md — signed consent Delegation Record.
- specs/acceptance-metrics.md — BET falsifiability consumer.
- specs/ledger.md — `FoundationHealthHeartbeatConsent` entry.""",
    },
    "sub-agent-delegation.md": {
        "purpose": "SubsetProof schema + runtime-independent verifier; sub-agent spawning contract.",
        "source": "02-envelope-model.md v3 §14.4 + 03-trust-lineage.md v2 §7",
        "threats": "T-105 sub-agent forgery, T-107 recursive spawn DoS",
        "bets": "BET-9a upstream primitives, BET-12 structural authorship enforcement",
        "body": """## SubsetProof schema
```json
{
  "type": "SubsetProof", "schema_version": "subset-proof/1.0",
  "parent_envelope_hash": "sha256:...", "sub_envelope_hash": "sha256:...",
  "dimension_witnesses": {
    "financial": {"per_call_ceiling": {"type": "INT_LEQ", "sub_value": <int>, "parent_value": <int>}, ...},
    "operational": {"tool_allowlist_subset": {"type": "SET_SUBSET", ...}, "tool_denylist_superset": {"type": "SET_SUPERSET", ...}, ...},
    "temporal": {"allowed_windows_subset": {...}, "blackout_windows_superset": {...}},
    "data_access": {"classification_clearance_leq": {"type": "ENUM_LEQ", ...}, "field_allowlist_subset_per_model": {...}, ...},
    "communication": {"recipient_allowlist_subset": {...}, "content_rules_superset_union": {"type": "SET_SUPERSET", "inversion_reason": "more restrictive = fewer content types allowed"}}
  },
  "signature_by_parent": "ed25519:...",
  "runtime_verification_signature": "ed25519:...",
  "algorithm_identifier": {...}
}
```

**Direction-inversion explicit:** `content_rules` direction is SUPERSET (sub ⊇ parent), NOT SUBSET. Documented inline per witness. Linter BLOCKS incorrect direction.

## Independent verification (R2-H2 fix)
Parent agent computes proof as hint. **Envoy runtime re-computes from scratch** on every sub-agent invocation using `is_subset_envelope(sub, parent)`. Runtime's `runtime_verification_signature` is authoritative.

## `is_subset_envelope` algorithm
```python
def verify_subset_proof_independently(parent, sub):
    assert sub.sub_agent_derivation is not None
    proof = sub.sub_agent_derivation
    if proof.parent_envelope_hash != sha256_canonical(parent.effective_envelope): raise ...
    if proof.sub_envelope_hash != sha256_canonical(sub.effective_envelope): raise ...
    if parent.algorithm_identifier != sub.algorithm_identifier: raise AlgorithmMismatchError
    for dim in FIVE_DIMENSIONS:
        result = verify_dimension_subset(parent.effective_envelope[dim], sub.effective_envelope[dim])
        if not result.ok: raise SubsetProofFailedError(dim, result.witness_detail)
    if not composition_rules_are_superset(parent, sub): raise ...
    if not classifier_ensemble_is_superset(parent, sub): raise ...
    runtime_sig = runtime_sign(canonical_form(proof + parent + sub))
    return VerificationResult(ok=True, runtime_signature=runtime_sig)
```

## Cross-migration sub-agent spawn (H-07 fix)
parent.algorithm_identifier and sub.algorithm_identifier MUST match OR both in migration-compatible list.

## Sub-agent spawn budget (T-107)
Posture-dependent depth limits: PSEUDO/TOOL 0, SUPERVISED 1, DELEGATING 2, AUTONOMOUS envelope-declared (default 3). Bounded by operational.sub_agent_spawn_limit.

## Conformance vectors
20 adversarial — 5 direction-inverted, 10 edge (empty/identity), 5 authored-cover-adversarial.

## Cross-references
- specs/envelope-model.md — parent/sub envelope schemas.
- specs/trust-lineage.md — sub_agent_derivation field in DelegationRecord.
- specs/runtime-abstraction.md — `trust_verify_subset_proof()`.
- specs/threat-model.md — T-105, T-107.""",
    },
    "ledger-merge.md": {
        "purpose": "CRDT-style merge protocol for offline multi-device Ledger reconciliation (T-101).",
        "source": "04-ledger.md v1 §7",
        "threats": "T-101 fork reconciliation + conflict-flood defense",
        "bets": "BET-6 contract parity under multi-device",
        "body": """## Algorithm
```python
def merge(branches):
    all_entries = union(branch.entries for branch in branches)
    sorted_entries = sort(all_entries, key=lambda e: (e.lamport_clock.lamport_time, e.lamport_clock.device_id, e.lamport_clock.local_seq))
    conflicts = []
    for entry in sorted_entries:
        if entry.nonce seen before: conflicts.append(NonceConflict(...))
        if entry.type == "PhaseARecord" and intent_id seen: conflicts.append(IntentIdConflict(...))
        if entry.type == "RevocationRecord" and later-entry-references-revoked-delegation: conflicts.append(RevocationRaceConflict(...))
    # Re-link parent_hash in merged order
    for i, entry in enumerate(sorted_entries[1:], start=1):
        entry.merged_parent_hash = sorted_entries[i-1].entry_id
        entry.original_parent_hash = entry.parent_hash  # signed
    for conflict in conflicts:
        ledger.append(LedgerConflictEntry(conflict))
    return merged_ledger
```

Each entry carries `original_parent_hash` (signed) + `merged_parent_hash` (derived).

## Conflict types
- **NonceConflict** — same nonce on different devices.
- **IntentIdConflict** — same intent_id Phase A on different devices.
- **RevocationRaceConflict** — revocation + later-descendant-signing race.

## Conflict-flood rate-limit (R2-H1 fix)
- Per-principal cap: 20 unresolved.
- Semantic batching by similarity.
- Principal exceeding cap: sync suspended until existing conflicts resolved.

## Resolution UX
Each conflict surfaces options:
- NonceConflict: user picks which to keep; other tombstoned.
- IntentIdConflict: both Phase A's visible; user picks canonical or cancels both.
- RevocationRaceConflict: revocation wins automatically; notify user.

## Device-binding
Each device has distinct sub-key from Genesis + device attestation. Entries include device-key-id. Attacker cannot forge entries as a device they don't control.

## Cross-references
- specs/ledger.md — merge consumer.
- specs/trust-lineage.md — chain-level merge interaction.
- specs/runtime-abstraction.md — runtime invokes merge at sync.
- specs/threat-model.md — T-101.""",
    },
    "a2a-messaging.md": {
        "purpose": "Agent-to-agent messaging in Shared Household; cross-principal dual-signed actions.",
        "source": "02-envelope-model.md v3 + 07-channels-and-adapters.md v1",
        "threats": "T-106 A2A adversarial cooperation",
        "bets": "BET-3 sovereignty across multi-principal",
        "body": """## Phase 03 deliverable.

## A2A message schema
```json
{
  "type": "A2AMessage",
  "sender_principal_genesis_id": "sha256:...",
  "recipient_principal_genesis_id": "sha256:...",
  "sender_envelope_hash": "sha256:...",
  "recipient_envelope_hash_expected": "sha256:...",
  "action_type": "<enum>",
  "composed_intent_hash": "sha256:<hash of proposed collective outcome>",
  "timestamp": <iso8601>, "nonce": <hex>,
  "signature_by_sender_hex": <ed25519>
}
```

## Envelope-binding
Every A2A message covers `(sender_envelope_hash, recipient_envelope_hash, action_type, composed_intent_hash)`. Recipient verifies its envelope allows receiving this message type from this sender AND contributing to this composed_intent.

## Cross-principal dual-signed action
For actions affecting BOTH principals (shared calendar, shared budget): requires signed Grant Moment from BOTH principals. 24h cooling-off for high-stakes (matches specs/enterprise-deployment.md pattern).

## Composition-aware
`composed_intent_hash` evaluated against both principals' envelopes before delivery. Composition rules (per specs/envelope-model.md §5.3) apply cross-principal.

## T-106 defense
Composed intent must pass both principals' envelope checks INDEPENDENTLY; neither single envelope allows the composed action alone.

## Cross-references
- specs/envelope-model.md — composition_rules cross-principal.
- specs/grant-moment.md — dual-signed flow.
- specs/trust-lineage.md — cross-principal delegation.
- specs/threat-model.md — T-106.""",
    },
    "authorship-score.md": {
        "purpose": "BET-12 structural enforcement primitive. Semantic de-dup + minimum-impact + posture-ratchet gate.",
        "source": "02-envelope-model.md v3 §8 + §14.7 + §14.8",
        "threats": "T-023 score inflation, T-024 enterprise delegation-upward",
        "bets": "BET-12 governance-primary-surface, BET-1 authorship",
        "body": """## Score computation
```
AuthorshipScore = count of envelope.*.authored_constraints where:
  - authored: true
  - novelty_check_passed: true (Jaccard < 0.85 on AST canonical form + adversarial-wording classifier < 0.8)
  - minimum_impact_check_passed: true (dry-run corpus + user's 30-day Ledger history)
```

## Novelty de-duplication algorithm
1. Canonicalize proposed constraint AST (tree-normalize: sort sibling terms lexicographically, constant-fold).
2. Tree-Jaccard similarity against each existing constraint's canonicalized AST. Threshold 0.85.
3. `envoy-registry:novelty.adversarial-wording:v1` classifier check (catches LLM-assisted gaming). Threshold 0.8.
4. Distinct iff both checks pass.
5. Quarterly retrain of adversarial-wording classifier on user-submitted attempts.

## Minimum-impact check algorithm
1. Dry-run corpus: Foundation-curated `standard_action_corpus_v1` (10k actions across 5 dimensions) + user's 30-day Ledger history.
2. For each action: evaluate under current envelope vs current + proposed. Distinct decision on ≥1 action → proposed has behavioral impact.
3. No decision change → `MinimumImpactCheckFailedError`; UX surfaces "here's what would narrow me."

## Cold-start
If user history <30 days, synthetic corpus only. Implicit "trust user intent" with warning.

## Posture-ratchet gate
- **Personal mode:** N=3 for DELEGATING; N=5 for AUTONOMOUS.
- **Enterprise mode (cryptographically attested):** N=5 DELEGATING; AUTONOMOUS NOT reachable on shared templates.
- **Shared Household:** per-principal scores; household-wide actions require composition.
- **Annual revalidation:** posture decays 1 level at 12mo; user re-authors ≥1 to restore.

## Stored vs recomputed (M-05 fix from doc 02 R1)
`metadata.authorship_score.authored_count` signed at sign time. Runtime recomputes at verify. Mismatch → `AuthorshipScoreDivergenceError` audit alert.

## Cross-references
- specs/envelope-model.md — authored_constraints storage.
- specs/grant-moment.md — Approve+author path gates via this spec.
- specs/boundary-conversation.md — authorship nudge at novelty-failed constraint.
- specs/weekly-posture-review.md — score progression ritual.
- specs/threat-model.md — T-023, T-024.""",
    },
    "budget-tracker.md": {
        "purpose": "Financial-dimension ceilings + velocity + session scope + threshold callbacks.",
        "source": "02-envelope-model.md v3 §3.1 + 05-runtime-abstraction.md v2 §2.1",
        "threats": "T-093 budget-exhaustion fraud, T-019 velocity-ratchet rubber-stamp",
        "bets": "BET-2 performance through structural governance",
        "body": """## Data unit
Integer microdollars (1 dollar = 1,000,000 microdollars). No float accumulation.

## Ceilings (doc 02 §3.1 + C-02 v3 fix)
- `per_call_ceiling_microdollars`
- `per_session_ceiling_microdollars` (added per reviewer F-13)
- `per_hour_velocity_microdollars`
- `per_day_ceiling_microdollars`
- `per_month_ceiling_microdollars`

## Check shape
100% structural. O(1) to O(log n) sliding-window sum. <5ms target.

## Reserve/record pattern
`budget_reserve(amount)` before call; `budget_record(reservation, actual)` after. Concurrent reservations sum against ceilings.

## Threshold callbacks
`BudgetTracker.set_threshold_callback(threshold_pct, callback)` — invoke when (committed + reserved) / allocated ≥ threshold. Used for Grant Moment surfacing. kailash-rs#518 + kailash-py#603.

## Velocity-raise ratchet (T-093 R2-H4)
RAISING any velocity limit CANNOT be inline. Requires Weekly Posture Review OR cross-channel Grant Moment with 24h cooling-off. Lowering allowed inline.

## Budget-exhaustion fraud defense (T-093)
- Per-call ceiling + velocity-limit + session-scope.
- Anomaly detection: single call > 50% of session budget → pause for confirmation.
- High-velocity pattern detection (5 calls at ceiling in 1min → Grant Moment).

## Cross-references
- specs/envelope-model.md — Financial dimension schema.
- specs/runtime-abstraction.md — `budget_reserve/record/snapshot/velocity_check`.
- specs/grant-moment.md — velocity-raise ratchet Grant Moment flow.
- specs/weekly-posture-review.md — velocity-raise approval ritual.""",
    },
    "remote-time-anchor.md": {
        "purpose": "Optional quorum time-anchor for Temporal dimension enforcement. Opt-in per doc 00 v3 §4.1 item 7b.",
        "source": "00-thesis-and-scope.md v3 §4.1 item 7b + 09-threat-model.md v3 T-001",
        "threats": "T-001 clock-skew bypass of Temporal dimension",
        "bets": "BET-3 sovereignty under Temporal envelope strength",
        "body": """## Phase 02 deliverable.

## Design
Quorum of public time-stamp authorities (TSAs): FreeTSA + DigiCert + Apple trust roots. ≥ 2 of 3 required for anchor to be accepted.

## Query cadence
Hourly default. User-configurable.

## Anchor record (Ledger entry type `time_anchor`)
```json
{
  "type": "time_anchor",
  "tsa_responses": [
    {"tsa_id": "freetsa", "timestamp": "...", "signature_hex": "..."},
    {"tsa_id": "digicert", "timestamp": "...", "signature_hex": "..."}
  ],
  "quorum_achieved": 2,
  "envoy_local_time_at_query": "...",
  "anchor_time_at_quorum": "...",
  "skew_ms": <int>,
  "signed_by_runtime_device_key": "..."
}
```

## Consent
Opt-in via distinct Grant Moment — separate from Foundation Health Heartbeat (§7a). Both consents separately cascade-revocable.

## Privacy
- OHTTP relay for TSA queries (IP unlinkability).
- Rate-limited (hourly).
- No user-identifying payload; request contains only Envoy version + standard TSA protocol RFC 3161.

## Consumption by Temporal dimension
envelope.temporal checks use `max(Ledger monotonic clock, most_recent_anchor.anchor_time)` when user has opted in. Strong enforcement if anchor recent; degrades gracefully if anchor stale beyond user-declared window.

## Residual risk
Per doc 09 v3 T-001: clock-forward spoofing during narrow attack window still possible; user receives no positive assurance that their Temporal envelope is absolutely enforced against clock attackers with device control.

## Cross-references
- specs/envelope-model.md — Temporal dimension.
- specs/ledger.md — `time_anchor` entries.
- specs/foundation-health-heartbeat.md — sibling opt-in Grant Moment pattern.
- specs/threat-model.md — T-001.""",
    },
    "foundation-ops.md": {
        "purpose": "Foundation operational infrastructure: Envelope Library registry, moderator queue, sync node, OHTTP relay, classifier registry, migration allowlist registry.",
        "source": "06-distribution.md + 08-skills.md + 00-thesis §4.1 item 15",
        "threats": "T-050a/b, T-051, T-052, T-091, T-092",
        "bets": "BET-4 Foundation stewardship, BET-10 legal posture",
        "body": """## Infrastructure inventory

1. **Envelope Library registry** — Nexus-backed HTTP/CLI/MCP; Foundation-Verified / Community / Organization tiers. Ed25519 publisher signatures. Content-addressed storage.
2. **Foundation sync node** — optional native Trust Vault sync. Ciphertext-only. User holds decryption key.
3. **OHTTP Key Configuration Server** — for Foundation Health Heartbeat + remote time anchor.
4. **OHTTP Relay** — Foundation or third-party. Strips source IPs.
5. **STAR/Prio aggregator** — Foundation-operated.
6. **Classifier registry** — `envoy-registry:*` namespace; Foundation-Verified classifiers signed 2-of-N; Community tier with same trust model as Envelope Library.
7. **Migration-allowlist registry** — `envoy-registry:migration-allowlist:v1`; signed 2-of-N Foundation stewards; prevents algorithm downgrade attacks.
8. **Public-email-provider registry** — `specs/public-email-providers.yml`; linter data for envelope-model linter.
9. **Permission-to-PACT-dimension registry** — `envoy-registry:permission-to-pact-dimension:v1`; SKILL.md → ENVELOPE.md translation table.
10. **Cross-domain-flow registry** — `envoy-registry:cross-domain-flows:v1`; safety-default cross-domain rules.
11. **Prompt-injection-patterns registry** — `envoy-registry:prompt-injection-patterns:v1`; tool-output sanitization patterns.
12. **N=3 mirror coordination** — Foundation GitHub + IPFS pinned + community redistributor; quarterly key rotation.
13. **Reproducible-build verification stream** — third-party reproduction publishing.

## Signing ceremonies
Foundation-Verified signatures require 2-of-N Foundation stewards. Ceremony:
- Air-gapped environment.
- Per-release key generation OR long-lived stewardship key rotation.
- Published revocation list; client-cached + periodic refresh with revocation check.

## Spam flood defense (T-092)
Envelope Library publish rate-limit per publisher key; spam auto-classifier; reviewer queue priority by publisher identity-proof tier.

## Sync node availability
SLA target: 99.5% uptime. `kailash-py` client-side fallback if sync node unreachable (local-only mode).

## Budget
Foundation budget line-items: reviewer headcount, infrastructure hosting, trademark maintenance (USPTO+EUIPO+UK IPO), crypto audit, legal retainer. NOT in Envoy product scope (doc 00 v3 §5.11 BET-11 WITHDRAWN).

## Cross-references
- All specs reference one or more Foundation-ops registries.
- specs/distribution.md — N=3 mirror coordination.
- specs/skill-ingest.md — permission/classifier registries.
- specs/threat-model.md — T-050a/b, T-051, T-052, T-091, T-092.""",
    },
    "channel-adapters.md": {
        "purpose": "8 Phase-01 surface (CLI + Web + 6 messaging channels) and 17 Phase-04 channels. Adapter contract + per-channel specs + compliance.",
        "source": "07-channels-and-adapters.md v1",
        "threats": "T-018 visible secret propagation, T-070 side channels, T-080 network MITM, T-023 Signal legal gate",
        "bets": "BET-6 contract parity across channels, BET-12 channel-native UX",
        "body": """## Adapter contract
`ChannelAdapter` (ABC): `channel_id`, `startup`, `shutdown`, `receive_message`, `send_message`, `send_grant_moment`, `send_digest`, `capabilities`, `rate_limit_status`.

## `ChannelCapabilities`
`{supports_buttons, supports_attachments, supports_markdown, supports_voice, supports_reactions, max_message_length}`.

## Message envelope
`{channel_id, session_id, principal_genesis_id, direction, content_trust_level, payload, visible_secret_rendered, timestamp}`.

## Phase 01 surfaces (8)

| Channel | Credentials | Compliance | Phase 01 ship |
|---|---|---|---|
| CLI | none | N/A | Yes |
| Web | localhost bind | N/A | Yes |
| Telegram | bot token | Clean (official bot API) | Yes |
| Slack | bot token + OAuth | Clean (App Directory) | Yes |
| Discord | bot token | Clean (Dev Terms) | Yes |
| WhatsApp | WhatsApp Business API | Paid tier; Foundation gateway OR user-own | Yes (caveat) |
| Signal | signal-cli OR Group Link | Phase 01 legal gate (Path B default) | Yes (Path B) |
| iMessage (BlueBubbles) | user-owned Mac | Apple ToS grey; user responsibility | Yes (caveat) |

## Phase 04 surfaces (17+)
Matrix, Feishu, LINE, Mattermost, WeChat, QQ, Teams, Google Chat, IRC, Nostr, Twitch, Tlon, Zalo, Nextcloud Talk, Synology Chat, Apple Shortcuts, Calendar, browser extension, IDE extensions, voice (Whisper), RCS/SMS (Twilio).

## Cross-channel session continuity
Single session across all active channels for a principal. Visible secret rendered in every channel. Grant Moment approval on any channel resolves session globally; other channels see "resolved elsewhere."

## Primary-channel binding (H-03 doc 01 fix)
High-stakes Grant Moments (above Financial/Communication threshold) render + approvable ONLY on user's designated primary channel.

## Side-channel hygiene (T-070)
- Clipboard auto-clear after 30s.
- Screen recording detection (Flutter mobile Phase 02).
- Accessibility API hardening per platform.
- E2E encryption per-channel (WhatsApp/Signal/iMessage = yes; Telegram secret-chats-only; Slack/Discord admin-visible).

## Network security (T-080)
TLS 1.3 minimum. Certificate pinning for Foundation endpoints. Standard OS trust store for third-party channels.

## Cross-references
- specs/grant-moment.md — adapter.send_grant_moment.
- specs/daily-digest.md — adapter.send_digest.
- specs/network-security.md — TLS + cert pinning.
- specs/ui-platform.md — per-platform accessibility + clipboard.
- specs/threat-model.md — T-018, T-070, T-080.""",
    },
    "distribution.md": {
        "purpose": "Per-OS install paths, first-run picker, N=3 mirrors + binary verification, upgrade/rollback/uninstall, jurisdictional advisories.",
        "source": "06-distribution.md v1",
        "threats": "T-050a mirror, T-050b signing-key, T-060 binary poisoning",
        "bets": "BET-3 sovereignty (N=3 mirror + kailash-py escape), BET-4 Foundation infra",
        "body": """## Phase 01 distribution
- **Surface:** `pipx install envoy-agent` (PyPI). kailash-py sole runtime.
- **Installer:** `envoy init` bootstraps Trust Vault + Genesis + Boundary Conversation.
- **Offline first-run:** local model bundled (Ollama/llama.cpp/MLX).

## Phase 02 distribution
- **macOS:** `curl -sSf https://get.envoy.ai | sh`, `brew install envoy-agent`.
- **Linux:** same curl, `apt`/`dnf` Phase 04.
- **Windows:** `winget install envoy-agent`; MSI Phase 04.
- **Rust:** `cargo install envoy-agent`.
- **Mobile:** App Store + Play Store (Flutter).

## N=3 mirror verification
1. Foundation GitHub (primary).
2. IPFS-pinned (secondary).
3. Community redistributor (Foundation-endorsed list).

Installer fetches binary + manifest from all 3; hash match across ≥ 2 required.

## Binary signing key rotation
Quarterly scheduled + on-demand on suspected compromise. Installer refuses revoked-key binaries. Compromise-response runbook published; target response <72h.

## Reproducible-build verification stream
Rust source for `kailash-rs-bindings` Python glue published; build instructions documented; third-party reproduction + published attestations; installer cross-checks.

## First-run flow (Phase 02)
Runtime picker → Model picker → Boundary Conversation → Shamir ritual → Visible secret setup.

## Upgrade / Rollback / Uninstall
- `envoy upgrade` with hash verification.
- Rollback preserved 30 days.
- `envoy uninstall --destroy-vault` for permanent key destruction.

## Jurisdictional advisories
- EU/UK: GDPR right-to-erasure note.
- US: export-control note (Ed25519+SHA-256 are EAR 742.15(b)(1) exportable).
- Hostile jurisdictions: recommend disabling sync + hidden-envelope (Phase 04).

## Installer security
Signed installer (bash/PowerShell). Platform verification (Gatekeeper/SmartScreen). AppArmor/SELinux profiles (Phase 03). Refuses install if Trust Vault dir world-readable.

## Cross-references
- specs/runtime-abstraction.md — runtime picker consumer.
- specs/trust-vault.md — Trust Vault initialization.
- specs/shamir-recovery.md — first-run Shamir.
- specs/boundary-conversation.md — first-run ritual.
- specs/foundation-ops.md — N=3 mirror coordination.
- specs/threat-model.md — T-050a/b, T-060.""",
    },
    "skill-ingest.md": {
        "purpose": "SKILL.md parser, ENVELOPE.md companion generator, CO validator, permission-to-PACT-dimension translator, force_install flag, Envelope Library tiers.",
        "source": "08-skills-and-envelope-companion.md v1",
        "threats": "T-020 malicious skill author, T-021 envelope publisher, T-022 Sybil, T-092 spam flood, T-090 sandbox DoS",
        "bets": "BET-7 SKILL.md compat, BET-12 authorship-gated posture",
        "body": """## SKILL.md parser
Parses external ecosystem's canonical format: name, version, description, permissions array, inline code blocks.

## ENVELOPE.md generator
Produces YAML companion declaring `{skill_id, skill_source_hash, publisher{genesis_id, signature}, requested_permissions{financial, operational, temporal, data_access, communication}, co_validator_result{passed, score, warnings, errors}}`.

## Permission → PACT dimension mapping
Foundation-curated registry `envoy-registry:permission-to-pact-dimension:v1`. Maps:
- `bash:*` → Operational + Data Access (Confidential clearance).
- `file-read:*` → Data Access.
- `file-write:*` → Operational.
- `http-post:<domain>` → Communication.
- `mcp:<server>` → Operational + Communication (+ MCP governance middleware).
- `oauth:<service>` → Connection Vault.
- `exec:<pattern>` → Operational (HIGH severity).

Unknown → `UnknownPermissionPatternError`.

## CO validator
Checks at install:
1. SKILL.md schema valid.
2. Permission patterns recognized.
3. Declared = inferred (code analysis; Phase 02 automated).
4. Over-privilege warning.
5. Adversarial-pattern detection (quarterly-retrained `envoy-registry:adversarial-skill-patterns:v1`).
6. Publisher signature verifies.

Score thresholds: ≥0.8 pass; 0.5–0.8 pass with warnings; <0.5 fail (requires `force_install=True`).

## `force_install=True` (doc 00 v3 §4.1 item 16)
- Visible Ledger flag `force_install_used`.
- Visible envelope flag.
- Visible skill inventory marker.
- User waives governance promise for that skill.
- Monthly Trust Report surfaces count.

## Envelope Library tiers
- **Foundation-Verified:** Reviewed; 2-of-N Foundation signatures; featured default.
- **Community:** Open publishing; Ed25519 publisher keys; ranked adoption × (1 − revocation); anti-Sybil per T-022 (identity-proofing + fork-tracking + adoption-rate cap); anti-spam per T-092 (publish rate-limit + spam classifier + reviewer priority).
- **Organization:** Private per-org registries (Phase 04).

## Skill sandbox
- **Phase 01–03:** Python subprocess + PACT enforcement. CPU + memory + wall-clock limits.
- **Phase 04+:** WASM sandbox via `kailash-plugin-guest` (open-source per doc 00 v3 §4.1).

## Install flow
`envoy skill install @author/skill-name@version` → fetch → parse → generate ENVELOPE.md → CO validator → Grant Moment user review → sign → inventory + Ledger.

## Cross-references
- specs/envelope-model.md — envelope schema; permission-to-dimension compile.
- specs/grant-moment.md — install-time Grant Moment.
- specs/runtime-abstraction.md — skill invocation contract.
- specs/foundation-ops.md — Envelope Library registry.
- specs/threat-model.md — T-020, T-021, T-022, T-090, T-092.""",
    },
    "acceptance-metrics.md": {
        "purpose": "Per-phase exit criteria + instrumentation + BET-falsification thresholds + kill-criteria operationalization.",
        "source": "11-acceptance-metrics.md v1",
        "threats": "Measures defense against every BET's attack surface",
        "bets": "ALL (this spec is the measurement substrate for every BET)",
        "body": """## Measurement substrate (doc 00 v3 §5.0)
- **[Heartbeat]** STAR k-anonymous opt-in.
- **[Public]** HN/X/blog/forum.
- **[Library]** Envelope Library fetch/publish.
- **[GitHub]** stars/forks/issues/downloads.
- **[Legal]** counsel-confirmed.
- **[Ops]** Foundation-internal.

## Phase 00 exit criteria
Trademark sweep cleared; namespaces reserved; Foundation board endorsement; 7 ADR-0009 items resolved; 39 GH issues filed + tracked; algorithm-identifier schema landed (mint#6 + kailash-py#604 + kailash-rs#519); deep audits published; PACT N4/N5 runner (kailash-py#605); DataFlow SQLi fix (kailash-rs#520); 12 analysis docs converged 0 CRIT + ≤2 HIGH; specs/ redteamed 0 HIGH across 2 consecutive full-sibling rounds.

## Phase 01 exit criteria
1 user completes Boundary Conversation E2E; 3 Grant Moments resolved; Daily Digest scheduled delivery; Ledger export verifier green; Shamir 3-of-5 reconstruct; redteam 0 CRIT/HIGH; 6 messaging channels E2E; algorithm-identifier tagged signatures; Authorship Score posture-ratchet enforced.

## Phase 02 exit criteria
Binary builds 5 targets; binary <50 MB; runtime picker E2E; cross-runtime conformance vectors (N1–N6 + E1–E7); 6 channels pass; mobile QR-pair <30s; CO validator accepts 100 benign + rejects 3 adversarial; Foundation Health Heartbeat functional; N=3 mirrors signed; reproducible-build stream; install-to-first-value <10min mobile.

## Phase 03 exit criteria
P50 latency <10ms Rust / <80ms Python; Community tier accepting publishes; 5-person Shared Household E2E; per-dimension posture slider; Weekly+Monthly rituals; cross-SDK byte-identity; annual posture-revalidation.

## Phase 04 exit criteria
23+ channels active; 3 Rust skills in FV tier; 2 enterprise pilots; hidden-envelope primitive; multi-provider verification; WASM sandbox audited.

## Un-phased regulated-industry readiness
SOC2 Type 1 readiness (NOT certification); HIPAA-ready deployment template (Foundation not BAA party); GDPR DPIA tooling; Federated Trust Mesh spec.

## BET-falsification thresholds
Full catalog in doc 11 v1 §8; 10 BETs × per-metric disconfirmation thresholds.

## Kill criteria operationalized
- **[Heartbeat] + [Library] dual-signal:** <1000 WAU AND <500 FV fetches/week at 18mo.
- **≥3 BETs disconfirmed** → 6mo targeted-experiment countdown.
- **Foundation board declines runtime-pluggability.**
- **Categorically-better alternative:** all 5 §8 tests + 4 non-commercial properties + 3× within-niche adoption 24mo + 2 independent stewards confirm.
- **Legal categorical blocker** — unresolvable composite license / export / charter.

## Cross-references
- specs/foundation-health-heartbeat.md — Heartbeat flags + collection.
- specs/envelope-model.md — Authorship Score thresholds.
- specs/threat-model.md — test location per threat.
- specs/runtime-abstraction.md — per-phase gates.""",
    },
    "network-security.md": {
        "purpose": "TLS 1.3 + certificate pinning for Foundation endpoints + strict SNI + HSTS + Tor option.",
        "source": "09-threat-model.md v3 T-080 + 06-distribution.md",
        "threats": "T-080 network MITM + TLS downgrade",
        "bets": "BET-3 sovereignty under network transit",
        "body": """## TLS
- Minimum TLS 1.3 for all outbound connections.
- Cipher suites per RFC 9325 + Envoy allowlist.

## Certificate pinning
- Foundation-operated endpoints (Envelope Library, OHTTP relay, sync node, migration-allowlist registry): pinned certificates shipped with Envoy binary.
- Updates delivered via signed binary release (not via live update).
- User-added CAs for Foundation endpoints REFUSED — prevents corporate MITM.

## Strict SNI + HSTS for all outbound HTTPS.

## Third-party endpoints
Standard OS trust store for cloud model providers + channel transports. Per-provider certificate pinning optional (user-configurable in envelope.communication).

## Tor option (Phase 02+)
Optional route-through-Tor for privacy-sensitive traffic (Foundation Health Heartbeat, time anchor).

## Residual risk
State-actor MITM with stolen CA keys — out of §1.2 scope.

## Cross-references
- specs/foundation-health-heartbeat.md — OHTTP relay uses pinned certs.
- specs/remote-time-anchor.md — same.
- specs/distribution.md — installer-level binary signature verification.
- specs/channel-adapters.md — third-party channel TLS.
- specs/threat-model.md — T-080.""",
    },
    "ui-platform.md": {
        "purpose": "Per-platform side-channel hygiene (clipboard, screen, accessibility) + secure input fields + platform-specific rendering.",
        "source": "09-threat-model.md v3 T-070 + 01-ux-rituals.md v2 §11",
        "threats": "T-070 clipboard/screen/accessibility, T-071 memory disclosure",
        "bets": "BET-3 sovereignty under platform attack surface",
        "body": """## Clipboard
- Grant Moment credential capture: secure-text-field (bypass clipboard on iOS).
- Auto-clear after 30s (configurable).
- No Envoy content auto-copied.

## Screen recording
- Flutter mobile (Phase 02): detect active recording; warn before sensitive Grant Moment renders.
- Macro: no countermeasure — detection + advisory only.

## Accessibility API hardening
- **macOS:** accessibility tree includes visible Envoy content; sensitive fields (credentials, Shamir shards, ledger entries) excluded from accessibility tree unless user opts in.
- **Android:** accessibility hint system; sensitive fields excluded.
- **iOS:** VoiceOver support with redacted content for sensitive fields.

## Memory hygiene (T-071)
See specs/trust-vault.md §memory-hygiene. Zeroize on release.

## Localization
- Phase 01: en-US.
- Phase 02: en-GB, es-ES, de-DE, fr-FR, zh-CN, ja-JP.
- Phase 04: community-contributed.
- Translation keys: `envoy-i18n/<lang>/<ritual>.json`.
- User-authored content preserved verbatim (user's language); Envoy signed records carry exact text.

## Accessibility
- Screen readers: all prompts have alt text; visible secret has text description.
- High-contrast mode: color channel adapts.
- Keyboard-only: Tab navigation.
- Audio cue: accessible chime on Grant Moment (Web).
- Chunked content: long Ledger entries split for cognitive accessibility.

## Bidi / RTL
HTML bidi standard. User-authored content preserves RTL marks.

## Cross-references
- specs/trust-vault.md — memory hygiene.
- specs/grant-moment.md — secure input fields.
- specs/channel-adapters.md — per-channel accessibility.
- specs/threat-model.md — T-070, T-071.""",
    },
    "classification-policy.md": {
        "purpose": "PACT classification clearance enum + `@classify` decorator + `apply_read_classification()` + `format_record_id_for_event()` integration.",
        "source": "02-envelope-model.md v3 §3.4 + 09-threat-model.md v3 T-005",
        "threats": "T-005 semantic envelope bypass, T-012 feedback-loop poisoning (record_id hashing)",
        "bets": "BET-2 semantic check substrate",
        "body": """## Classification enum (canonical per PACT)
`Public | Internal | Confidential | Restricted | HighlyConfidential`.

## `@classify` decorator (kailash-py; kailash-rs uses attribute-based)
Field-level classification marking at model definition time:
```python
@classify(email=PII)
class User:
    email: str
```

kailash-rs equivalent: `#[classification(PII)]` attribute.

## `apply_read_classification(value, field_classification, caller_clearance)`
Returns masked value based on policy:
- caller_clearance ≥ field_classification → return plain.
- caller_clearance < field_classification → redact per MaskingStrategy (Redact / LastFour / Hash / NullOut).

kailash-py ✅ functional (internal API; public exposure kailash-py#601).
kailash-rs: `apply_read_classification()` at `crates/kailash-dataflow/src/classification.rs:76` (binding kailash-rs#514).

## `format_record_id_for_event(policy, model_name, record_id, pk_field)`
Hashes classified-PK values before emission:
- Input types: None → None; integer/float → str; unclassified string → str; classified string → `f"sha256:{sha256(value)[:8]}"`.

kailash-py ✅ at `packages/kailash-dataflow/src/dataflow/classification/event_payload.py`.
kailash-rs: 2026-04-19 fix per `rules/event-payload-classification.md`; cross-SDK prefix stable.

## Envelope integration
Data Access dimension references classification per-model via `field_allowlist_per_model` + `semantic_rules` with classifier ensemble per classification type.

## Semantic classifier ensemble defense (T-005)
Minimum 2 classifiers per semantic check. Weighted vote. Disagreement fails CLOSED. Classifier-version tracked in Ledger for retrospective flagging.

## Cross-references
- specs/envelope-model.md — Data Access dimension semantic rules.
- specs/ledger.md — `format_record_id_for_event` at event emission.
- specs/monthly-trust-report.md — redaction for public sharing.
- specs/threat-model.md — T-005, T-012.""",
    },
    "enterprise-deployment.md": {
        "purpose": "EnterpriseDeploymentRecord schema + verifier + disablement flow with cryptographic attestation.",
        "source": "02-envelope-model.md v3 §14.3 + 03-trust-lineage.md v2 §9",
        "threats": "T-024 enterprise delegation-upward + flip-off attack",
        "bets": "BET-12 enterprise-mode variant of authorship thesis",
        "body": """## Phase 03 deliverable.

## EnterpriseDeploymentRecord schema
```json
{
  "type": "EnterpriseDeploymentRecord", "schema_version": "edr/1.0",
  "org_genesis_hash": "sha256:...",
  "org_id": <str>,
  "deploying_principal": {"address": <PACT>, "public_key_hex": <str>},
  "affected_employee_principal": {"address": <PACT>, "public_key_hex": <str>},
  "template_envelope_hash": "sha256:...",
  "template_envelope_ref": "@org/enterprise-default-v1",
  "enabled_at": <iso8601>,
  "scope": "employee-personal-envelope-overlay | household-member-envelope-overlay | agent-fleet-envelope-overlay",
  "verification_algorithm": "ed25519",
  "signatures": {
    "org_admin_signature_hex": <str>,
    "affected_employee_signature_hex": <str>  // REQUIRED dual-signed
  }
}
```

**Scope closed enum** — any other value rejected.

## Verification (at envelope-import time)
1. org_genesis_hash resolves to known org Trust Lineage root.
2. `deploying_principal.signature` valid against org Trust Lineage.
3. `affected_employee_signature` valid against employee's Genesis.
4. `scope` in closed enum.
5. `enabled_at` within 365 days (annual re-attestation).
6. `verification_algorithm` current-session-compatible OR migration-compatible.

## Disablement (T-024 R2-H5)
`EnterpriseDeploymentDisablementRecord` with scope=disabled. Requires:
- Employee signature.
- **Cross-channel confirmation** (employee's designated second channel from Boundary Conversation).
- **24h cooling-off window** — disablement not effective until 24h after employee signature AND second-channel confirm.
- **Fail-secure auto-cancel** — if 24h elapses without second-channel confirm, disablement cancels.

Prevents abuser-IT-disables-protections-for-victim attack.

## Posture-ratchet under enterprise mode
- Employees start at SUPERVISED on enterprise template.
- DELEGATING requires N=5 employee-personal authored constraints (not N=3).
- AUTONOMOUS NOT reachable on shared templates (requires per-employee envelope).

## BET-12 enterprise falsifier
<20% of employees have personal authored constraints beyond template at 90 days → thesis falsified in enterprise context.

## Cross-references
- specs/envelope-model.md — enterprise_mode metadata field consumer.
- specs/trust-lineage.md — §9 verifier.
- specs/authorship-score.md — N=5 enterprise threshold.
- specs/grant-moment.md — cross-channel confirmation flow.
- specs/threat-model.md — T-024.""",
    },
}


def make_spec(name, info):
    out = [f"# {name.replace('.md', '')}", ""]
    out.append("## Purpose")
    out.append(info["purpose"])
    out.append("")
    out.append("## Provenance")
    out.append(f"- **Source:** `workspaces/phase-00-alignment/01-analysis/{info['source']}`.")
    out.append(f"- **Threats mitigated:** {info['threats']}.")
    out.append(f"- **BETs tested:** {info['bets']}.")
    out.append("")
    out.append(info["body"].strip())
    return "\n".join(out) + "\n"


for name, info in SPECS.items():
    path = SPECS_DIR / name
    if not path.exists():
        path.write_text(make_spec(name, info))
        print(f"Created {name}")
    else:
        print(f"Skipping {name} (exists)")

print("Done.")
