# foundation-ops

## Purpose

Foundation operational infrastructure: Envelope Library registry, moderator queue, sync node, OHTTP relay, classifier registry, migration allowlist registry.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/06-distribution.md + 08-skills.md + 00-thesis §4.1 item 15`.
- **Threats mitigated:** T-050a/b, T-051, T-052, T-091, T-092.
- **BETs tested:** BET-4 Foundation stewardship, BET-10 legal posture.

## Infrastructure inventory

Every registry MUST have a published `## Schema` (below §Registry schemas) + signing ceremony + cadence per specs/foundation-ops.md §Signing ceremonies. No registry is load-bearing without its schema.

1. **Envelope Library registry** (`envoy-registry:envelope-library:v1`) — Nexus-backed HTTP/CLI/MCP; Foundation-Verified / Community / Organization tiers. Ed25519 publisher signatures. Content-addressed storage. Consumer: specs/envelope-model.md §authored/imported constraints.
2. **Foundation sync node** — optional native Trust Vault sync. Ciphertext-only. User holds decryption key. Consumer: specs/data-model.md §Sync + specs/ledger.md.
3. **OHTTP Key Configuration Server** — for Foundation Health Heartbeat + remote time anchor. Consumer: specs/foundation-health-heartbeat.md + specs/remote-time-anchor.md.
4. **OHTTP Relay** — Foundation or third-party. Strips source IPs. Consumer: same as #3.
5. **STAR/Prio aggregator** — Foundation-operated. Consumer: specs/foundation-health-heartbeat.md.
6. **Classifier registry** (`envoy-registry:*` namespace) — Foundation-Verified classifiers signed 2-of-N; Community tier same trust model as Envelope Library. Scope: any classifier named `envoy-registry:<domain>:<name>:v<N>` (including but not limited to #10, #11, #16 below). Consumer: specs/envelope-model.md §Semantic classifier ensemble + specs/classification-policy.md.
7. **Migration-allowlist registry** (`envoy-registry:migration-allowlist:v1`) — signed 2-of-N Foundation stewards; prevents algorithm downgrade attacks. Consumer: specs/trust-lineage.md §Algorithm migration.
8. **Public-email-provider registry** (`envoy-registry:public-email-providers:v1`) — YAML data file published under the registry namespace, distributed with each Envoy release and refreshable over OHTTP; linter data for envelope-model linter. Consumer: specs/envelope-model.md + specs/cross-domain-flows.md (source-domain inference).
9. **Permission-to-PACT-dimension registry** (`envoy-registry:permission-to-pact-dimension:v1`) — SKILL.md permission → ENVELOPE.md translation table. Consumer: specs/skill-ingest.md.
10. **Cross-domain-flow registry** (`envoy-registry:cross-domain-flows:v1`) — safety-default cross-domain rules. Consumer: specs/cross-domain-flows.md (owning spec).
11. **Prompt-injection-patterns registry** (`envoy-registry:prompt-injection-patterns:v1`) — tool-output sanitization classifier ensemble members. Consumer: specs/tool-output-sanitization.md.
12. **N=3 mirror coordination** — Foundation GitHub + IPFS pinned + community redistributor; quarterly key rotation. Consumer: specs/distribution.md.
13. **Reproducible-build verification stream** — third-party reproduction publishing. Consumer: specs/distribution.md + specs/runtime-abstraction.md §Runtime attestation.
14. **Standard-action-corpus registry** (`envoy-registry:standard-action-corpus:v1`) — 10k synthetic actions across 5 dimensions used by specs/authorship-score.md §Minimum-impact check. V-08 fix per round-1-specs-comprehensive.md: made explicit as a Foundation-curated registry entry.
15. **Structural-prompt-injection registry** (`envoy-registry:structural-prompt-injection:v1`) — syntactic pattern corpus for specs/tool-output-sanitization.md §Structural pattern corpus (fast-path regex).
16. **Novelty-adversarial-wording registry** (`envoy-registry:novelty.adversarial-wording:v1`) — classifier catching LLM-assisted gaming of authorship novelty. Consumer: specs/authorship-score.md.
17. **Adversarial-skill-patterns registry** (`envoy-registry:adversarial-skill-patterns:v1`) — skill-ingest.md CO validator consumer.
18. **Channel-capability registry** (`envoy-registry:channel-capabilities:v1`) — Phase 01 capabilities matrix per channel: `ChannelCapabilities` struct (supports_buttons, supports_attachments, supports_markdown, supports_voice, supports_reactions, max_message_length) signed Foundation key. Consumer: specs/channel-adapters.md §`ChannelCapabilities`. Refresh cadence: per Envoy release; out-of-band OHTTP refresh for emergent channel-API changes.

## Registry schemas

Every classifier / corpus / YAML-data registry entry carries:

```json
{
  "registry_id": "envoy-registry:<domain>:<name>:v<N>",
  "schema_version": "registry/1.0",
  "artifact_hash": "sha256:<content_hash>",
  "steward_signatures": [
    {"steward_pubkey_hex": "<str>", "signature_hex": "<ed25519>"}
  ],
  "signing_threshold_met": <bool>,
  "published_at": "<iso8601>",
  "expires_at": "<iso8601>",
  "revocation_list_ref": "<url>",
  "content_type": "classifier | corpus | yaml_data | rule_set | allowlist | template",
  "content_ref": "<url | ipfs://<cid> | envoy-registry:<inline>>"
}
```

Consumers resolve a registry ID via `classifier_registry_resolve` (specs/runtime-abstraction.md §Abstract interface) which (a) fetches the entry, (b) verifies `signing_threshold_met` is true + `steward_signatures` match Foundation stewardship keys + `expires_at` not passed, (c) fetches `content_ref`, (d) hashes and compares to `artifact_hash`, (e) returns the resolved artifact.

## Allowlist override (FoundationAllowlistOverrideRecord)

In rare operational cases, a user may need to override a Foundation-published allowlist (e.g., a Foundation migration allowlist excludes an algorithm the user needs for regulatory reasons). The override MUST be dual-signed by (a) the user's Genesis key AND (b) an explicit acknowledgement payload hash. This produces a `FoundationAllowlistOverrideRecord` Ledger entry (specs/ledger.md §Entry types). Overrides expire after 90 days unless renewed.

```json
{
  "type": "FoundationAllowlistOverrideRecord",
  "schema_version": "foundation-override/1.0",
  "target_registry_id": "envoy-registry:migration-allowlist:v1",
  "override_payload_hash": "sha256:<acknowledgement_bytes>",
  "override_payload_content_trust_level": "user-authored",
  "reason": "<str>",
  "reason_content_hash": "sha256:...",
  "expires_at": "<iso8601>",
  "genesis_signature_hex": "<ed25519>"
}
```

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

## Error taxonomy

| Error                                      | Trigger                                                                                     | User action                                                                        | Retry                     |
| ------------------------------------------ | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------- |
| `RegistryEntryNotFoundError`               | `classifier_registry_resolve(registry_id)` against unknown registry_id                      | Verify registry_id spelling; check Foundation registry for retirement              | Manual after correct      |
| `RegistrySignatureMismatchError`           | Resolved registry entry's `steward_signatures` fail Foundation stewardship-key verification | Refuse content; possible compromise — surface to user as Foundation-trust degraded | Never (audit needed)      |
| `RegistryThresholdNotMetError`             | Registry entry's `signing_threshold_met` is false (fewer than 2-of-N stewards)              | Refuse; wait for Foundation re-publication                                         | Auto on next refresh      |
| `RegistryArtifactHashMismatchError`        | `content_ref` fetched bytes do not match `artifact_hash`                                    | Refuse; treat as mirror compromise (T-050a) or transit corruption                  | Auto with mirror fallback |
| `RegistryEntryExpiredError`                | Resolved entry's `expires_at` in the past                                                   | Refresh from Foundation; if no fresher version, surface as Foundation-stale        | Auto with TTL refresh     |
| `ModeratorQuorumLostError`                 | Foundation moderator queue drops below 2-of-N active stewards                               | Foundation-side incident; client surfaces degraded review-tier                     | Auto with backoff         |
| `SyncNodeUnreachableError`                 | Foundation sync node + every configured fallback unreachable                                | Continue local-only mode; alert on prolonged unavailability (>SLA)                 | Auto with backoff         |
| `OHTTPRelayDownError`                      | OHTTP relay unreachable; Heartbeat / remote-time-anchor cannot deliver                      | Pause Heartbeat send; queue locally up to retention bound                          | Auto with backoff         |
| `TemplateHashMismatchError`                | Envelope Library imported template's hash does not match registry's `artifact_hash`         | Refuse import; suspected supply-chain tamper                                       | Never                     |
| `SpamFloodRateLimitError`                  | Publisher exceeds Envelope Library publish rate-limit (T-092)                               | Publisher contacts Foundation moderator for tier review                            | Auto after window         |
| `AllowlistOverrideExpiredError`            | `FoundationAllowlistOverrideRecord` past 90-day expiry                                      | Re-author override with fresh acknowledgement; re-sign Genesis                     | Manual after re-sign      |
| `ReproducibleBuildVerificationFailedError` | Reproducible-build stream's verification hash does not match runtime's `binary_hash`        | Refuse runtime binary; suspected mirror tamper                                     | Never (audit needed)      |

All errors persisted to Ledger as `system_error` with `record_id` redacted via `format_record_id_for_event` per specs/classification-policy.md.

## Cross-references

- All specs reference one or more Foundation-ops registries.
- specs/distribution.md — N=3 mirror coordination.
- specs/skill-ingest.md — permission/classifier registries.
- specs/cross-domain-flows.md — registry #10 consumer.
- specs/tool-output-sanitization.md — registry #11 + registry #15 consumer.
- specs/envelope-model.md — registries #1, #6, #8, #9.
- specs/authorship-score.md — registries #14, #16.
- specs/foundation-health-heartbeat.md — registries #3, #4, #5.
- specs/remote-time-anchor.md — registry #3.
- specs/runtime-abstraction.md — registry resolution + reproducible-build verification.
- specs/threat-model.md — T-050a/b, T-051, T-052, T-091, T-092.

## Test location

- `tests/integration/test_registry_resolve_signature_threshold.py` — 2-of-N steward verification + threshold rejection (Tier 2).
- `tests/integration/test_registry_artifact_hash_match.py` — `content_ref` bytes hash to `artifact_hash`; tamper rejected.
- `tests/integration/test_registry_expiry_refresh.py` — expired entry rejected; refresh from Foundation succeeds.
- `tests/integration/test_envelope_library_publish_rate_limit.py` — per-publisher publish quota.
- `tests/integration/test_moderator_queue_priority.py` — queue priority by publisher identity-proof tier.
- `tests/integration/test_sync_node_99_5_uptime.py` — local-only fallback on sync-node unreachability (Tier 2).
- `tests/integration/test_ohttp_relay_strips_source_ip.py` — relay strips source IPs end-to-end (Tier 2 against test relay).
- `tests/integration/test_foundation_allowlist_override_90d_expiry.py` — override expires; user re-signs to renew.
- `tests/integration/test_reproducible_build_verification_stream.py` — third-party verification matches runtime binary_hash.
- `tests/regression/test_t050a_binary_mirror_compromise.py` — T-050a mirror-side tamper detected at hash compare.
- `tests/regression/test_t050b_signing_key_compromise.py` — T-050b signing-key revocation list refresh.
- `tests/regression/test_t091_envelope_library_spam.py` — T-091 spam classifier + reviewer queue priority.
- `tests/regression/test_t092_publish_rate_limit.py` — T-092 publish rate-limit + reviewer priority.

## Open questions

1. `specs/public-email-providers.yml` data-shape ownership — does this YAML data file's schema live in foundation-ops.md, in envelope-model.md (the consumer), or in a dedicated schema spec? R3-LOW finding from Round 1 deferred to a downstream-refinement decision.
2. Quarterly key rotation cadence vs continuous rotation — N=3 mirror coordination key rotation is currently quarterly; should it move to continuous (per-release) under increased threat posture?
3. Steward stewardship-key revocation under M-of-N compromise — when the N=2 threshold itself is suspected compromised, what is the user-side fallback (refuse all registry resolution? Trust last-known-good cached entries with what TTL)?
4. Cross-Foundation registry interop — if a regional Foundation publishes its own registry namespace, what is the trust-bridge protocol (cross-signed bridge attestation? Independent Foundation roots)?
5. Allowlist override audit trail — should `FoundationAllowlistOverrideRecord` be visible at Monthly Trust Report tier or remain Ledger-only, given that override use is a deliberate user-acknowledged deviation?
