# enterprise-deployment

## Purpose

EnterpriseDeploymentRecord schema + verifier + disablement flow with cryptographic attestation.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/02-envelope-model.md v3 §14.3 + 03-trust-lineage.md v2 §9`.
- **Threats mitigated:** T-024 enterprise delegation-upward + flip-off attack.
- **BETs tested:** BET-12 enterprise-mode variant of authorship thesis.

## Phase delivery (V-07 fix per round-1-specs-comprehensive.md)

- **Phase 02** — EnterpriseDeploymentRecord schema + verifier + dual-sign gate shipped as part of runtime cross-runtime-conformance landing.
- **Phase 03** — Disablement flow + 24h cooling-off + cross-channel confirm + N=5 enterprise posture ratchet live; single-org pilot onboarded.
- **Phase 04** — 2-pilot acceptance gate per specs/acceptance-metrics.md Phase 04 (`2 enterprise pilots`). Earlier versions of this spec said "Phase 03 deliverable" — that was the SCHEMA + verifier landing; the 2-pilot acceptance is explicitly Phase 04 per `acceptance-metrics.md`.

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

1. org_genesis_hash resolves to known org Trust Lineage root (injected `known_org_roots` map: `org_genesis_hash → org_trust_lineage_root_pubkey_hex`).
2. `org_admin_signature_hex` (the deploying principal's signature) valid against the RESOLVED org Trust Lineage root public key from step 1 — NOT against the record-supplied `deploying_principal.public_key_hex` (verifying against a record-supplied key would let any principal claim org authority).
3. `affected_employee_signature_hex` valid against the employee's Genesis key (`affected_employee_principal.public_key_hex` — the Genesis key identifies the principal; employee consent is anchored by the dual-sign gate).
4. `scope` in closed enum (enforced at parse time, before any signature math — a malformed scope surfaces as `EnterpriseScopeMismatchError`, never a signature error; the dual-sign gate is likewise a parse-time structural check).
5. `enabled_at` within 365 days (annual re-attestation; clock injected for determinism). The window is TWO-SIDED: a future-dated `enabled_at` (beyond the documented 5-minute `FUTURE_DATED_SKEW_TOLERANCE`) raises `EnterpriseDeploymentRecordInvalidError` — a future-dated record was never validly attested.
6. `verification_algorithm` current-session-compatible OR migration-compatible (defaults: current = `{ed25519}`, migration set injected).

Both signatures are Ed25519 over the record's **canonical signing payload** (`EnterpriseDeploymentRecord.signing_payload()`): sha256 over the RFC-8785 canonical bytes (via the shared `envoy/envelope/canonical_bytes.py` pipeline) of the FULL security-relevant field set — type, schema_version, org_genesis_hash, org_id, both principals (address + public_key_hex), template_envelope_hash, template_envelope_ref, enabled_at, scope, verification_algorithm — everything except the `signatures` block. Binding the full record (not `template_envelope_hash` alone) closes the signature-transplant vector: a signature pair from one EDR cannot be replayed onto a record with a mutated scope, employee, or org (regression: `tests/regression/test_t024_enterprise_delegation_upward.py::TestT024SignatureTransplant`). Signature verification routes through the shared `envoy/registry/steward_quorum.py::verify_steward_quorum` primitive (1-of-1 quorum per key) — no parallel verifier.

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

## Error taxonomy

| Error                                       | Trigger                                                                                                             | User action                                                                             | Retry                       |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | --------------------------- |
| `EnterpriseDeploymentRecordInvalidError`    | EDR fails any verifier step (org_genesis_hash unknown, signature invalid, scope outside enum, schema_version drift) | Surface failure detail; user contacts org admin to re-issue EDR                         | Never                       |
| `EnterpriseDualSignMissingError`            | EDR carries org admin signature but no employee signature (or vice versa)                                           | Both parties must sign; refused until dual-signed                                       | Manual after dual-sign      |
| `EnterpriseDisableFlowFailedError`          | Disablement record submitted without cross-channel confirmation OR before 24h cooling-off window completes          | Wait for second-channel confirm; auto-cancel if 24h elapses without confirm             | Manual after second-channel |
| `EnterpriseDisableAutoCancelledError`       | 24h cooling-off elapsed without second-channel confirm; disablement cancelled (fail-secure)                         | Re-initiate disablement and complete second-channel confirm within 24h                  | Manual                      |
| `PerEmployeeEnvelopeRequiredError`          | Employee attempts AUTONOMOUS posture on shared template without per-employee envelope                               | Author per-employee envelope (N=5 personal authored constraints) before raising posture | Manual                      |
| `EnterpriseModeRevokedError`                | Action attempted under EDR whose `enabled_at` is older than 365 days (annual re-attestation expired)                | Org admin re-issues EDR with current `enabled_at`                                       | Manual after re-issue       |
| `EnterpriseAlgorithmMigrationRequiredError` | EDR `verification_algorithm` not in current-session-compatible OR migration-compatible set                          | Org admin re-issues under migration-allowlisted algorithm                               | Manual after re-issue       |
| `EnterpriseScopeMismatchError`              | Action requests scope outside EDR's declared `scope` closed enum value                                              | Refuse action; org admin issues new EDR with correct scope                              | Never                       |

All errors persisted to Ledger as `system_error` per specs/ledger.md §System error.

## Cross-references

- specs/envelope-model.md — enterprise_mode metadata field consumer.
- specs/trust-lineage.md — §9 verifier.
- specs/authorship-score.md — N=5 enterprise threshold.
- specs/grant-moment.md — cross-channel confirmation flow.
- specs/foundation-ops.md — migration-allowlist registry consumer.
- specs/ledger.md — `EnterpriseDeploymentRecord` + `EnterpriseDeploymentDisablementRecord` entry types.
- specs/threat-model.md — T-024.

## Test location

- `tests/integration/test_edr_verifier_six_steps.py` — every verifier step (org_genesis_hash, signatures, scope, enabled_at window, algorithm) under green path + targeted failure (Tier 2).
- `tests/integration/test_edr_dual_sign_required.py` — single-signed EDR refused; dual-signed accepted.
- `tests/integration/test_edr_disablement_24h_cooling_off.py` — submit disablement, advance clock 24h, verify auto-cancel without confirm; verify success with confirm.
- `tests/integration/test_edr_cross_channel_confirmation.py` — second-channel confirm gate per Boundary Conversation.
- `tests/integration/test_enterprise_n5_posture_ratchet.py` — N=5 employee-personal authored constraints required for DELEGATING under enterprise template.
- `tests/integration/test_enterprise_autonomous_blocked_on_shared_template.py` — AUTONOMOUS refused without per-employee envelope.
- `tests/regression/test_t024_enterprise_delegation_upward.py` — T-024 abuser-IT-disables-protections-for-victim attack defense.
- `tests/e2e/test_enterprise_2_pilot_acceptance.py` — Phase 04 acceptance gate (specs/acceptance-metrics.md `2 enterprise pilots`).

## Open questions

1. Cross-channel confirmation — which channels qualify as "second channel" for a given employee, and how is that designation captured (Boundary Conversation default vs explicit user pick)?
2. 365-day re-attestation cadence — is the 365-day window calendar-aligned (annual) or rolling, and how is the user notified of impending expiry?
3. Annual re-attestation friction — does the user re-sign every EDR for every employee, or does a per-org "still valid" attestation cover all active EDRs at once?
4. Per-employee envelope authoring under enterprise mode — is N=5 strictly counted from constraints AUTHORED post-enterprise-enable, or does pre-existing personal envelope content count?
5. Cross-org employee (contractor with two enterprise EDRs simultaneously) — composition semantics under intersect_envelopes when two enterprise overlays apply to the same principal.
