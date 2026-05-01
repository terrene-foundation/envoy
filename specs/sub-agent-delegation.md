# sub-agent-delegation

## Purpose

SubsetProof schema + runtime-independent verifier; sub-agent spawning contract.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/02-envelope-model.md v3 §14.4 + 03-trust-lineage.md v2 §7`.
- **Threats mitigated:** T-105 sub-agent forgery, T-107 recursive spawn DoS.
- **BETs tested:** BET-9a upstream primitives, BET-12 structural authorship enforcement.

## SubsetProof schema

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

Parent agent computes proof as hint. **Envoy runtime re-computes from scratch** on every sub-agent invocation using `is_subset_envelope(parent, sub)` (canonical name; `verify_subset_proof_independently` is the implementation alias defined below). Runtime's `runtime_verification_signature` is authoritative.

## `is_subset_envelope` algorithm

```python
def is_subset_envelope(parent: EnvelopeConfig, sub: EnvelopeConfig) -> VerificationResult:
    """Canonical name; cross-runtime ABC method per specs/runtime-abstraction.md.
    `verify_subset_proof_independently` is a synonym used by some implementations."""
    """
    Verifier inputs:
      - parent: full parent EnvelopeConfig (dataclass).
      - sub:    full sub-envelope EnvelopeConfig with sub.sub_agent_derivation: SubsetProof.
    The proof itself carries only hashes of parent + sub; the verifier re-hashes and re-verifies.
    """
    assert sub.sub_agent_derivation is not None
    proof = sub.sub_agent_derivation

    # Step 1 — re-hash and compare.
    parent_hash = sha256_canonical_form(parent)  # specs/envelope-model.md §Canonical JSON (JCS + NFC)
    sub_hash    = sha256_canonical_form(sub)
    if proof.parent_envelope_hash != parent_hash:
        raise SubsetProofHashMismatchError(which="parent", proof=proof.parent_envelope_hash, recomputed=parent_hash)
    if proof.sub_envelope_hash != sub_hash:
        raise SubsetProofHashMismatchError(which="sub", proof=proof.sub_envelope_hash, recomputed=sub_hash)

    # Step 2 — algorithm identifier must match (or cross-migration allowlist).
    if parent.metadata.algorithm_identifier != sub.metadata.algorithm_identifier:
        raise AlgorithmMismatchError(parent=parent.metadata.algorithm_identifier, sub=sub.metadata.algorithm_identifier)

    # Step 3 — per-dimension subset verification.
    for dim in ("financial", "operational", "temporal", "data_access", "communication"):
        result = verify_dimension_subset(dim, getattr(parent, dim), getattr(sub, dim), proof.dimension_witnesses[dim])
        if not result.ok:
            raise SubsetProofFailedError(dim=dim, witness_detail=result.witness_detail)

    # Step 4 — composition rules of sub MUST be a superset of parent (more restrictive).
    if not composition_rules_are_superset(parent.composition_rules, sub.composition_rules):
        raise SubsetProofCompositionRulesNotSupersetError(...)

    # Step 5 — classifier ensemble of sub MUST be a superset of parent (more-or-equal classifiers).
    if not classifier_ensemble_is_superset(parent.semantic_checks, sub.semantic_checks):
        raise SubsetProofClassifierEnsembleNotSupersetError(...)

    # Step 6 — runtime signs the canonical form of (proof, parent, sub) as attestation.
    runtime_sig = runtime_sign(canonical_form_triple(proof, parent, sub))
    return VerificationResult(ok=True, runtime_signature=runtime_sig)
```

### Helper functions (referenced in algorithm)

- **`sha256_canonical_form(envelope)`** — per specs/envelope-model.md §Canonical JSON; JCS + NFC normalization. Same helper produces the hash stored in `DelegationRecord.effective_envelope_hash` + the `parent_envelope_hash` / `sub_envelope_hash` in this proof.
- **`verify_dimension_subset(dim, parent_dim, sub_dim, witness)`** — evaluates the type-tagged witness (`INT_LEQ` / `SET_SUBSET` / `SET_SUPERSET` / `ENUM_LEQ`) against the actual values; returns `DimensionVerifyResult(ok, witness_detail)`. Witness validation MUST check both that the claimed relation holds AND that the witness type matches the dimension (e.g. `financial.per_call_ceiling` requires `INT_LEQ`, not `SET_SUBSET`).
- **`composition_rules_are_superset(parent_rules, sub_rules)`** — sub's rule set MUST include every parent rule (by canonical rule_id) plus optionally add more restrictive rules. `order` ties break lexicographically on rule_id.
- **`classifier_ensemble_is_superset(parent_checks, sub_checks)`** — for every classifier in parent.semantic_checks, sub.semantic_checks MUST include the same classifier at ≥ the parent's weight. Sub MAY add more classifiers.

**Naming parity (V-06 fix):** this spec's algorithm reads the FULL `EnvelopeConfig` dataclass passed in; the on-chain representation is `effective_envelope_hash` (SHA-256 of canonical form) as stored in `DelegationRecord` per specs/trust-lineage.md §DelegationRecord. The verifier re-derives the hash from the full envelope to match the stored hash, closing the naming drift.

## Cross-migration sub-agent spawn (H-07 fix)

parent.algorithm_identifier and sub.algorithm_identifier MUST match OR both in migration-compatible list.

## Sub-agent spawn budget (T-107)

Posture-dependent depth limits: PSEUDO/TOOL 0, SUPERVISED 1, DELEGATING 2, AUTONOMOUS envelope-declared (default 3). Bounded by operational.sub_agent_spawn_limit.

## Conformance vectors

20 adversarial — 5 direction-inverted, 10 edge (empty/identity), 5 authored-cover-adversarial.

## Error taxonomy

| Error                                           | Trigger                                                                                                       | User action                                                                         | Retry                  |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ---------------------- |
| `SubsetProofHashMismatchError`                  | Step 1: `parent_envelope_hash` or `sub_envelope_hash` does not match recomputed canonical-form hash           | Refuse spawn; suspected envelope tamper between proof construction and verification | Never                  |
| `AlgorithmMismatchError`                        | Step 2: parent and sub `algorithm_identifier` differ AND not in migration-allowlist                           | Refuse spawn; align algorithms or use cross-migration spawn (H-07)                  | Manual after migration |
| `SubsetProofFailedError`                        | Step 3: per-dimension `verify_dimension_subset` reports `ok=False` for any of the 5 dimensions                | Refuse spawn; surface failing dimension + witness_detail                            | Never                  |
| `SubsetProofWitnessTypeMismatchError`           | `verify_dimension_subset` finds witness type does not match dimension shape (e.g. `SET_SUBSET` for `INT_LEQ`) | Refuse spawn; treat as proof-construction bug or hostile witness                    | Never                  |
| `SubsetProofCompositionRulesNotSupersetError`   | Step 4: `composition_rules_are_superset` finds parent rule absent from sub                                    | Refuse spawn; sub MUST inherit every parent composition rule                        | Never                  |
| `SubsetProofClassifierEnsembleNotSupersetError` | Step 5: `classifier_ensemble_is_superset` finds parent classifier absent or weight insufficient in sub        | Refuse spawn; sub ensemble MUST cover parent at ≥ parent weight                     | Never                  |
| `SubsetProofRuntimeSignatureFailedError`        | Step 6: runtime cannot produce attestation signature (device key unavailable, runtime degraded)               | Defer spawn until runtime signing path recovers                                     | Auto on recovery       |
| `SubsetProofParentSignatureInvalidError`        | `signature_by_parent` fails verification against parent envelope's signing key                                | Refuse spawn; suspected parent-side proof forgery                                   | Never                  |
| `SubAgentSpawnDepthExceededError`               | Spawn depth exceeds posture-dependent limit (PSEUDO/TOOL 0, SUPERVISED 1, DELEGATING 2, AUTONOMOUS envelope)  | Refuse spawn; T-107 recursive-spawn DoS defense                                     | Manual after escalate  |
| `SubAgentSpawnLimitExceededError`               | Spawn count exceeds `operational.sub_agent_spawn_limit` for current session                                   | Refuse spawn; user raises limit via Weekly Posture Review (velocity-raise ratchet)  | Manual after raise     |
| `ContentRulesDirectionInversionError`           | Linter blocks proof construction when `content_rules` witness uses SUBSET instead of SUPERSET direction       | Fix proof construction; documented as direction-inversion explicit                  | Never                  |

All errors persisted to Ledger as `system_error` per specs/ledger.md §System error.

## Cross-references

- specs/envelope-model.md — parent/sub envelope schemas.
- specs/trust-lineage.md — sub_agent_derivation field in DelegationRecord.
- specs/runtime-abstraction.md — `trust_verify_subset_proof()`.
- specs/budget-tracker.md — velocity-raise ratchet for `sub_agent_spawn_limit` raises.
- specs/posture-ladder.md — depth limits per posture level.
- specs/threat-model.md — T-105, T-107.

## Test location

- `tests/conformance/test_subset_proof_20_adversarial_vectors.py` — 5 direction-inverted, 10 edge (empty/identity), 5 authored-cover-adversarial per §Conformance vectors.
- `tests/integration/test_verify_dimension_subset_per_dimension.py` — `verify_dimension_subset` exercised across financial / operational / temporal / data_access / communication.
- `tests/integration/test_witness_type_validation.py` — `INT_LEQ` / `SET_SUBSET` / `SET_SUPERSET` / `ENUM_LEQ` per dimension; mismatched type rejected.
- `tests/integration/test_composition_rules_are_superset.py` — sub rule set ⊇ parent rule set; lexicographic tie-break on `rule_id`.
- `tests/integration/test_classifier_ensemble_is_superset.py` — sub ensemble covers every parent classifier at ≥ parent weight.
- `tests/integration/test_runtime_independent_re_verification.py` — runtime re-computes from scratch on every spawn; parent-supplied proof treated as hint only.
- `tests/integration/test_cross_migration_spawn.py` — H-07 cross-algorithm spawn against migration-allowlist.
- `tests/integration/test_sub_agent_spawn_depth_per_posture.py` — depth limits 0/1/2/envelope across PSEUDO, SUPERVISED, DELEGATING, AUTONOMOUS.
- `tests/integration/test_content_rules_direction_inversion_linter.py` — linter blocks SUBSET direction on content_rules.
- `tests/regression/test_t105_sub_agent_forgery.py` — T-105 parent-supplied proof tamper detected by runtime re-derivation.
- `tests/regression/test_t107_recursive_spawn_dos.py` — T-107 spawn depth + spawn limit defense.

## Open questions

1. Three helper-algorithm definitions — `verify_dimension_subset`, `composition_rules_are_superset`, `classifier_ensemble_is_superset` are referenced inline in §`is_subset_envelope` algorithm but their full pseudocode is summarized rather than enumerated. Should these be promoted to dedicated `## Algorithm` sub-sections (per Round 1 R1-HIGH orphan finding), or do their summary descriptions plus the conformance-vector corpus serve as the definitive specification?
2. Authored-cover adversarial vector definition — the 5 "authored-cover-adversarial" vectors in §Conformance vectors need explicit construction recipes; what attack pattern do they target (camouflage by authored constraints? Witness-construction by adversarial author)?
3. Spawn-budget velocity-raise interaction — when `operational.sub_agent_spawn_limit` is raised mid-session, does the new ceiling apply retroactively to sub-agents already in flight, or only to subsequent spawns?
4. Cross-runtime SubsetProof verifier byte-identity — `runtime_verification_signature` is per-runtime; what is the byte-identity contract for the canonical form that gets signed (so two runtimes signing the same triple produce comparable signatures over identical bytes)?
5. Sub-agent revocation cascade — when a parent's `DelegationRecord` is revoked, do all its sub-agents' SubsetProofs cascade-revoke, or do they require independent revocation? Round 1 left this as a downstream-refinement question.
