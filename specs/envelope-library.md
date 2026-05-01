# envelope-library

## Purpose

The Envelope Library is the Foundation-curated + Community publishing surface for envelope templates. Owns Sybil defense, FV-tier identity-proofing, fork-tracking, publisher reputation. The runtime-side registry endpoint is defined in `specs/foundation-ops.md` §Envelope Library registry #1; the install-side governance is defined in `specs/skill-ingest.md`. This spec is the integration owner for the publisher-side primitives that anchor doc 09 v3 §3 references as `specs/envelope-library.md`.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/09-threat-model.md v3 §3 T-020 / T-021 / T-022 / T-024 / T-051 / T-092` + `workspaces/phase-00-alignment/01-analysis/06-distribution.md v1 §Library`.
- **Threats mitigated:** T-020 envelope-template supply chain, T-021 envelope-template publisher impersonation, T-022 Envelope Library Sybil, T-024 enterprise template delegation-upward (publisher-side; user-side mitigation lives in specs/enterprise-deployment.md), T-051 Foundation infra compromise of Library, T-092 Library spam.
- **BETs tested:** BET-1 sovereignty (user can refuse Library), BET-4 credibility (FV publisher reputation), BET-12 governance-primary (envelope authoring as the primary social surface).

## Trust tiers

| Tier                         | Identity proof                                                                         | Signing                                                     | Force-install                                    | Sybil defense                                    |
| ---------------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------ |
| **Foundation-Verified (FV)** | Foundation 2-of-N steward signing ceremony; legal-counsel-confirmed publisher identity | Foundation steward Ed25519, key-rotation quarterly          | Default-allowed; user opts out                   | N/A — controlled set                             |
| **Community**                | Publisher Ed25519 self-issued; web-of-trust attestation by ≥3 prior publishers         | Publisher self-signed; Foundation key-distribution endpoint | Default-blocked; explicit force_install required | Web-of-trust depth ≥ 3; rate-limit per publisher |
| **Organization**             | Tenant-private; org-key-bound                                                          | Org-key Ed25519                                             | Default per org policy                           | Out of scope (tenant-internal)                   |

## Sybil defense (T-022)

- **FV tier:** structural — only Foundation-stewarded publishers are FV; T-022 mitigated by FV's bounded membership.
- **Community tier:** web-of-trust depth ≥ 3 (publisher attestations); rate-limit 5 envelopes per publisher per week to slow Sybil network growth; classifier-ensemble fingerprint check vs `envoy-registry:adversarial-skill-patterns:v1` (foundation-ops.md registry #17) to catch LLM-assisted Sybil-template generation.
- **Identity-proofing escalation:** Foundation may require additional identity proof (DNSSEC-anchored `.well-known`, GitHub org binding, KYC for FV migration) for publishers crossing Sybil-suspicion thresholds.

## Fork-tracking

Each Community-tier envelope template SHOULD declare its `parent_template_hash` if forked. The Library renders fork-graph at the publisher reputation page; downstream importers see "this template forks `X`'s `family-starter:v3` — original publisher's reputation: 4.2 / 5".

## Publisher reputation

Per-publisher signed reputation record:

```json
{
  "publisher_id": "ed25519-pubkey-hex",
  "tier": "FV | Community | Organization",
  "verified_email": "<sha256-hash>",
  "first_published_at": "<iso8601>",
  "templates_published": <int>,
  "templates_force_installed_count": <int>,
  "abuse_flags": <int>,
  "abuse_resolved_count": <int>,
  "reputation_score": <float 0..5>
}
```

Reputation degrades on abuse-flag confirmations (specs/skill-ingest.md uninstall path + specs/foundation-ops.md §Spam flood defense (T-092) for moderation throttling).

## Cross-domain consumer mapping

This spec's primitives are consumed by:

- specs/foundation-ops.md §Envelope Library registry #1 — registry endpoint + Nexus serving.
- specs/skill-ingest.md — install-time governance + force_install + ENVELOPE.md companion validation.
- specs/envelope-model.md — `template_provenance` consumer; envelope.metadata.authorship_score binding.
- specs/authorship-score.md §Stored counters — `imported_count` accounting.

## Error taxonomy

| Error                                  | Trigger                                                                                         | User action                                                                                     | Retry                           |
| -------------------------------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------- |
| `LibraryUnreachableError`              | Foundation Nexus endpoint unreachable AND no local cache entry                                  | Surface offline notice; user retries when network returns                                       | Auto after network              |
| `PublisherSignatureInvalidError`       | Template signature does not verify against publisher's pinned Ed25519                           | Refuse install; surface publisher-key-rotation possibility OR potential supply-chain compromise | Manual after key refresh        |
| `SybilSuspicionThresholdExceededError` | Publisher rate-limit exceeded OR web-of-trust depth < 3 OR adversarial-pattern classifier match | Refuse Community-tier publish; publisher escalates to FV identity-proof                         | Manual after escalation         |
| `ParentTemplateHashMismatchError`      | `parent_template_hash` declared but parent template's hash differs in registry                  | Refuse import OR force the user to re-attest to the new parent version                          | Manual                          |
| `ReputationFloorViolationError`        | Publisher reputation < 2.0 / 5 AND no force_install attestation                                 | Refuse default install; force_install allowed with explicit acknowledgment                      | Manual after force_install      |
| `LibrarySpamRateLimitError`            | Library publish rate-limit hit (T-092 defense)                                                  | Wait for window reset (default 1 week per publisher)                                            | Auto after window               |
| `FVTierMembershipNotProvenError`       | Template claims FV tier but Foundation steward signing chain incomplete                         | Refuse FV-tier rendering; treat as Community tier with explicit warning                         | Manual after Foundation re-sign |

## Cross-references

- specs/foundation-ops.md — registry #1 (Envelope Library Nexus endpoint) + #17 (adversarial-skill-patterns classifier).
- specs/skill-ingest.md — install-time CO validator + ENVELOPE.md companion.
- specs/envelope-model.md — `metadata.authorship_score.template_provenance` consumer.
- specs/authorship-score.md — `imported_count` accounting.
- specs/enterprise-deployment.md — T-024 enterprise-side mitigation (per-employee envelope ceiling).
- specs/threat-model.md — T-020, T-021, T-022, T-024, T-051, T-092.

## Test location

- `tests/integration/test_envelope_library_publisher_sign_verify.py` — publisher Ed25519 sign/verify round-trip.
- `tests/integration/test_envelope_library_fork_graph.py` — parent_template_hash binding.
- `tests/regression/test_t020_envelope_template_supply_chain.py` — T-020 publisher signature defense.
- `tests/regression/test_t021_publisher_impersonation.py` — T-021 web-of-trust attestation depth ≥ 3.
- `tests/regression/test_t022_envelope_library_sybil.py` — T-022 Sybil defense; rate-limit + classifier-ensemble.
- `tests/regression/test_t024_publisher_side_enterprise_delegation.py` — T-024 publisher-side mitigation.
- `tests/regression/test_t051_foundation_infra_compromise_library.py` — T-051 N-of-M steward signing failure modes.
- `tests/regression/test_t092_library_spam.py` — T-092 rate-limit enforcement.
- `tests/integration/test_publisher_reputation_record.py` — reputation_score updates on abuse_flag resolution.

## Open questions

1. Web-of-trust depth ≥ 3 — is depth-3 sufficient against motivated Sybil networks, or should depth be tier-dependent (4 for high-stakes templates, 2 for low-stakes)?
2. FV → Community → blocked promotion/demotion process — what is the public audit trail when Foundation revokes FV status from a publisher?
3. Reputation score formula — public, signed-source rubric vs Foundation-internal weighted formula. Trade-off: transparency vs gaming-resistance.
4. Fork-graph privacy — does forking expose the original publisher to reputation harvesting; should fork-graph be opt-in for Community tier?
5. Cross-Foundation interop — if a regional Foundation publishes its own Envelope Library, what is the cross-Foundation-Library import protocol (cross-signed bridge attestation? Independent Foundation roots)?
