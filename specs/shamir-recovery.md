# shamir-recovery

## Purpose

SLIP-0039 Shamir 3-of-5 default ritual; shard generation, distribution, recovery, rotation.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/01-ux-rituals.md v2 §8 + 03-trust-lineage.md v2 §2`.
- **Threats mitigated:** T-006 shard social-graph defense (default-to-safes).
- **BETs tested:** BET-3 sovereignty (Trust Vault backup).

## Algorithm

SLIP-0039 via audited libraries: Rust `sharks` / `vsss-rs`; Python `slip39` / `python-shamir-mnemonic`. Phase 00 crypto audit required.

## Default threshold

3-of-5. User-configurable 2-of-3 to 5-of-9.

## Distribution guidance (T-006 defense)

Default: 3 cards in user's own safes, 2 with trusted humans.
Alternative: 5 in user's own safes (no human holders) — recommended for high-OPSEC users.

## Card format

24 BIP-39 words; Trezor-compatible.
NO "Envoy" label; NO name. Distribution checklist persists only opaque slot labels in Trust Vault; real names optional + in hidden envelope (Phase 04) only (H-06 fix).

### Slot label whitelist

The renderer, persister, and `DistributionChecklist.__post_init__` each enforce a structural three-layer defense:

1. Whitelist regex `^slot-\d+$` — labels MUST match the canonical opaque form `slot-0`..`slot-N`.
2. ASCII-only — Unicode confusables (e.g. Cyrillic `s` U+0455) are rejected.
3. Substring blacklist — `envoy` (case-insensitive) is forbidden anywhere in the label.

A label that fails any layer raises `EnvoyLabelOnCardError` and the print is refused. The check is intentionally duplicated at all three sites so no construction path bypasses the whitelist (no cross-module coupling on a single check).

## Recovery flow

Enter words from any 3 cards (any order). Per-card checksum validation at entry (L-03 fix). Reconstruction; vault unlock.

## Rotation ritual

When shard-holder becomes unreachable (death, estrangement, relocation): `envoy shamir rotate`. New 5 cards; 4 non-rotated old cards remain valid for 30-day grace period, then deprecated.

## Shard public commitments

Per specs/trust-lineage.md — Genesis Record carries `shard_public_commitments: [algo:hash]` array for recovery verification without shard exposure.

## Error taxonomy

| Error                               | Trigger                                                                                                                                                                              | User action                                                                         | Retry                   |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------- | ----------------------- |
| `InsufficientSharesError`           | Recovery attempted with fewer than threshold (default 3) valid shards                                                                                                                | User retrieves additional shards from holders/safes; resume recovery                | Manual after retrieval  |
| `ShardChecksumFailedError`          | Per-card BIP-39 checksum invalid at entry (L-03 fix)                                                                                                                                 | Re-enter card carefully; if persistent, card may be transcription-corrupted         | Manual after re-entry   |
| `CommitmentVerificationFailedError` | Reconstructed master key does not match `shard_public_commitments` in Genesis Record                                                                                                 | Refuse unlock; investigate counterfeit-shard or social-engineering attack           | Never (security event)  |
| `RecoveryRateLimitedError`          | Recovery attempts exceed rate ceiling (T-002 household-adversarial defense)                                                                                                          | Wait for rate-limit window expiry; consult lockout UX                               | Auto after window       |
| `ShardSlotLabelMismatchError`       | Card-slot label entered does not match Distribution Checklist opaque slot label                                                                                                      | Surface as wrong-card; user retrieves correct slot OR investigates checklist drift  | Manual after correction |
| `RotationGracePeriodElapsedError`   | Pre-rotation card presented after 30-day grace period                                                                                                                                | Refuse card; user uses post-rotation card from refreshed 5-set                      | Never                   |
| `EnvoyLabelOnCardError`             | User-supplied slot label fails the opaque-label whitelist (`^slot-\d+$`, ASCII-only, no `envoy` substring) — H-06 hard rejection at renderer + persister + dataclass `__post_init__` | Refuse to render; user re-supplies a canonical `slot-N` label (N=0..total_shards-1) | Manual after re-supply  |
| `CryptoLibAuditMissingError`        | Phase 00 crypto audit not landed for selected SLIP-0039 implementation                                                                                                               | Block recovery feature in production; complete audit before ship                    | Never (release gate)    |
| `ShardPublicCommitmentMissingError` | Genesis Record lacks `shard_public_commitments` (pre-Phase-01 vault)                                                                                                                 | Migrate vault to current Genesis Record schema; re-shard if necessary               | Manual after migration  |

## Cross-references

- specs/trust-lineage.md — Genesis Record integration + `shard_public_commitments`.
- specs/trust-vault.md — master key splitting.
- specs/boundary-conversation.md — S8 ritual step.
- specs/connection-vault.md — re-pair after recovery (Connection Vault not Shamir-covered).
- specs/threat-model.md — T-002, T-006.

## Test location

- `tests/integration/test_shamir_3_of_5_reconstruct.py` — 3-of-5 SLIP-0039 reconstruct + vault unlock (Tier 2).
- `tests/integration/test_shamir_threshold_configurable.py` — 2-of-3 to 5-of-9 user-configurable thresholds.
- `tests/regression/test_t002_household_adversarial_recovery.py` — T-002 defense; rate-limit + commitment verify.
- `tests/regression/test_t006_shard_social_graph_default_safes.py` — T-006 defense; default-to-safes guidance + checklist.
- `tests/integration/test_shard_per_card_checksum_l03.py` — L-03 fix; per-card BIP-39 checksum at entry.
- `tests/integration/test_shamir_rotation_30_day_grace.py` — pre-rotation cards valid 30 days post-rotation.
- `tests/integration/test_shard_distribution_checklist_h06.py` — H-06 fix; opaque slot labels; no real names in non-hidden envelope.
- `tests/integration/test_shard_public_commitment_verify.py` — Genesis-Record commitment defeats counterfeit shards.
- `tests/e2e/test_shamir_recovery_full_ritual.py` — full S8 ritual via Boundary Conversation (Tier 3).

## Open questions

1. Default 3-of-5 threshold tuning — Phase 01 telemetry on user threshold preferences (lower for ease-of-recovery vs higher for resilience).
2. 30-day rotation grace period — sufficient for shard-holder unreachability discovery; coordination with weekly-posture-review.md cadence.
3. Phase 00 crypto audit scope — SLIP-0039 reference impl audit + Envoy integration audit; cross-language (Rust + Python) parity.
4. Shard-holder revocation — proactive holder-removal flow without full rotation; UX vs security trade-off.
5. Post-recovery state — whether Connection Vault re-pair is opt-in fresh start vs partial restore from offline backup; coordination with connection-vault.md.
