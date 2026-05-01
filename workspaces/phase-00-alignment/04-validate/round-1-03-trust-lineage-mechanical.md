# Round 1 Mechanical Sweep — Doc 03 Trust Lineage

**Date:** 2026-04-21
**Scope:** Threat-mitigation coverage, cross-doc consistency, primitive-reference integrity.

## Summary

| ID   | Severity | One-liner                                                                                                                                                                                                                                                                   |
| ---- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M-01 | MEDIUM   | §3.2 schema references `capability_id: send_email` but capabilities are declared in envelope not delegation — what is the delegation-layer form of the PACT capability D/T/R address?                                                                                       |
| M-02 | MEDIUM   | §5.2 parity claim "BFS vs DFS produce same SET" — `tests/conformance/trust_lineage/cascade/` enumerated as 15 test vectors but not categorized (topology shapes)                                                                                                            |
| M-03 | MEDIUM   | §6.1 60-second replay window for synchronous grants — doc 02 v3 §14.2 composition-rule budget is 10ms; 60s vs 10ms is inconsistent framing for synchronous grant latency envelope                                                                                           |
| M-04 | MEDIUM   | §8.3 Trust Vault re-encryption during algorithm migration: "per-entry keys derived from master are RE-DERIVED LAZILY" — lazy derivation with legacy entries readable under old per-entry keys means Trust Vault has mixed-algorithm interior. How does decryption dispatch? |
| M-05 | LOW      | §7.2 runtime `runtime_verification_signature` — the runtime's key is device-bound per §11.2 but the signing key lifecycle under device-transition is unspecified                                                                                                            |
| M-06 | LOW      | §12 error taxonomy covers 15 errors; §3.4 chain verification lists 10 failure modes but not all have distinct errors (e.g. items 5 and 9 both general DelegationChainInvalidError)                                                                                          |
| M-07 | LOW      | §8.4 claims "both kailash-py and kailash-rs must support migration" but algorithm-identifier schema is ❌ NOT YET per §4.2 — cross-reference to Phase 01 exit gate is correct but implementation path not detailed                                                          |

## Verifications (passed)

### ✅ Threat mitigation coverage

All 8 doc-09-v3 threats naming `specs/trust-lineage.md`:

- T-002 household-adversarial — §9.2 disablement protocol ✓
- T-024 enterprise-attestation — §9 consumer ✓
- T-041 duress — §10 honeypot ✓
- T-042 key destruction + hidden envelope — §11 ✓
- T-100 rollback — §6.3 chain-level head-commitment ✓
- T-102 replay — §6.1 nonce + head-check ✓
- T-103 cycle — §6.2 creation-time + verify-time ✓
- T-104 envelope-version binding — §3.3 sig scope ✓
- T-105 sub-agent subset-proof verifier — §7 runtime re-verification ✓

### ✅ Doc 02 v3 cross-references

- SubsetProof (doc 02 §14.4) → doc 03 §7 verifier consumer
- EnterpriseDeploymentRecord (doc 02 §14.3) → doc 03 §9 verifier consumer
- algorithm_identifier format (doc 02 §2.2 metadata) → doc 03 §3.2 Delegation Record field
- envelope canonical form (doc 02 §14.1 JCS + NFC) → doc 03 §3.3 signing scope

### ✅ Cross-SDK parity references

- kailash-py `src/kailash/trust/` modules named correctly (chain.py, operations/, signing/crypto.py, revocation/cascade.py)
- kailash-rs `crates/eatp/src/` modules named correctly (delegation.rs, keys.rs, canonical.rs)
- Algorithm-identifier Phase 01 exit gate cross-referenced to mint#6 + kailash-py#604 + kailash-rs#519
- Cascade revocation BFS/DFS parity set-equality claim stated; test corpus named

### ✅ Chain-integrity defenses

- Cycle detection at BOTH creation + verify time (§6.2)
- DAG invariant explicit (`chain_parent_id` references earlier-sequenced record)
- Chain depth bounded (MAX_CHAIN_DEPTH = 16)
- Nonce-uniqueness table sliding window (90 days, 10^6 entries, oldest evicted)
- Replay window 60s synchronous grants (configurable longer for async)

### ✅ Schema completeness

- Genesis: genesis_id (content-hash), self-signature, Shamir commitments, device attestation, algorithm_identifier — all present.
- Delegation: delegation_id, chain_parent_id, delegator, delegatee, capabilities, envelope_version, effective_envelope_hash, time window, nonce, sub_agent_derivation, enterprise_context, signature — all present.
- RevocationRecord: cascade_target_count + cascade_target_ids + revoker + reason + nonce + signature — all present.
- KeyRotationRecord: dual-signed (old + new) ✓.
- MigrationAnnouncement: algorithm_identifier transition + effective_at + signature ✓.

### ✅ Error taxonomy

15 trust-lineage-specific errors; covers replay / cycle / chain-depth / time-window / capability-dead / SubsetProof / enterprise / algorithm / rotation / duress.

## Resolution summary

- **0 CRITICAL**, **0 HIGH**, 4 MEDIUM, 3 LOW.
- All findings addressable inline without structural rewrite.
- Doc 03 v1 is in good shape pre-agent-verdict.

Waiting for reviewer + security-reviewer agents to identify structural issues beyond mechanical sweeps.
