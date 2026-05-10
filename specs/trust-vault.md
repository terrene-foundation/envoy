# trust-vault

## Purpose

Encrypted local storage of Envoy's own keys + envelope + posture + ritual state.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/10-data-model.md v1 §2`.
- **Threats mitigated:** T-040 lost/stolen device, T-041 duress, T-042 key destruction, T-071 memory disclosure.
- **BETs tested:** BET-3 sovereignty.

## File format

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

Dual passphrase: real vs duress. Duress unlocks honeypot Genesis + honeypot Trust Lineage (distinct Genesis per specs/trust-lineage.md §Duress honeypot). Shadow segment (specs/data-model.md §Four physical containers #4) encrypted with real-passphrase-only key; never synced.

## Key destruction (T-042)

`envoy vault destroy-keys` CLI. Platform API eviction + overwrite + `KeyDestructionEvent` Ledger record. Irreversible.

## Hidden envelope (Phase 04)

Two passphrases, two Shamir sets, file-size padding, constant-write-rate, decryption-timing uniformity.

## Error taxonomy

| Error                                  | Trigger                                                                                           | User action                                                                              | Retry                  |
| -------------------------------------- | ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- | ---------------------- |
| `VaultUnlockFailedError`               | Passphrase Argon2id derivation + Secure Enclave XOR fails to produce valid AES-256-GCM master key | Re-enter passphrase; if persistent, run Shamir recovery                                  | Manual after re-enter  |
| `Argon2ParameterMismatchError`         | Stored vault parameters (m, t, p) differ from binary's expected (m=2^17, t=3, p=1)                | Run vault migration; backup before                                                       | Manual after migrate   |
| `DuressUnlockTriggered`                | Duress passphrase entered (internal runtime signal; NEVER user-surfaced)                          | None — honeypot Genesis activates; shadow segment inaccessible (CRIT-03)                 | N/A (silent)           |
| `VaultMACVerificationFailedError`      | Outer AES-256-GCM tag verification fails (file-level tamper or corruption)                        | Refuse unlock; restore from backup or run Shamir recovery                                | Never (audit needed)   |
| `RegionDecryptionFailedError`          | Per-region HKDF-SHA-256 derived key cannot decrypt region (inner integrity failure)               | Refuse region read; treat as targeted region tamper                                      | Never                  |
| `ShadowSegmentEncryptionError`         | Shadow segment write fails because the real-passphrase-only key is unavailable (duress mode)      | Silent refuse; shadow segment writes only under real-passphrase context                  | N/A                    |
| `KeyDestructionEventUnloggedError`     | `envoy vault destroy-keys` ran without writing `KeyDestructionEvent` to Ledger                    | Audit Ledger; if event missing, surface as integrity violation (last-act signing failed) | Never                  |
| `BackupRestoreVerificationFailedError` | Restored vault's MAC tag or region keys do not match expected binding                             | Restore from a different backup or invoke Shamir recovery                                | Manual after re-fetch  |
| `MemoryHygieneZeroizationFailedError`  | Explicit `zeroize` / `ctypes.memset` call returns failure during shutdown / lock                  | Treat as critical; force-exit process; do not write further entries                      | Never                  |
| `AutoLockIdleTimeoutError`             | Vault auto-locked after 15min idle; subsequent operation requires re-unlock                       | Re-enter passphrase                                                                      | Manual after re-unlock |
| `HiddenEnvelopePaddingBucketError`     | Phase 04 hidden-envelope write would push file size past largest padding bucket                   | Prune ritual on hidden envelope or hidden-envelope split                                 | Manual after prune     |

All errors persisted to Ledger as `system_error` per specs/ledger.md §System error EXCEPT `DuressUnlockTriggered` (NEVER written to synced Ledger; CRIT-03) and `ShadowSegmentEncryptionError` (shadow segment is local-only).

## Cross-references

- specs/trust-lineage.md — Genesis Record + Shamir commitments.
- specs/ledger.md — head commitments + per-entry keys.
- specs/connection-vault.md — distinct container.
- specs/shamir-recovery.md — master key splitting.
- specs/data-model.md — region layout + shadow segment placement.
- specs/threat-model.md — T-040, T-041, T-042, T-071.

## Test location

- `tests/tier1/test_trust_vault_lifecycle.py::TestArgon2ParameterStrictMatch` — Argon2id m=2^17, t=3, p=1; non-canonical params rejected (Tier 1, shipped T-01-13).
- `tests/tier1/test_trust_vault_lifecycle.py::TestFileFormatIntegrity` — AES-256-GCM outer encryption + MAC; truncation, magic-byte corruption, ciphertext byte-flip all rejected (Tier 1, shipped T-01-13).
- `tests/tier1/test_trust_vault_lifecycle.py::TestIdleLock` — auto-lock fires after `idle_ttl_seconds` (default 15min); activity resets timer; post-timeout access raises `AutoLockIdleTimeoutError` (Tier 1, shipped T-01-13).
- `tests/tier1/test_trust_vault_lifecycle.py::TestLock` — master-key zeroize on lock; idempotent (Tier 1, shipped T-01-13).
- `tests/tier1/test_trust_vault_lifecycle.py` — vault metadata slot `read_metadata` / `write_metadata` round-trip across lock/unlock cycles; `O_EXCL | O_NOFOLLOW` atomic-write hardening (Tier 1, shipped T-02-35).

## Out of scope (this phase)

Tests scheduled to land in named successor shards. Per `rules/spec-accuracy.md` Rule 4, the workstream lives in `workspaces/phase-01-mvp/todos/active/`; this section names ONLY the test-file path each shard will create. Citations move into `## Test location` above as the shards land.

- 3-of-5 default reconstruction round-trip (Tier 2 vault ⇄ Shamir wiring) — scheduled in T-02-37 (`02-wave-2-authorship-shamir-boundary.md`).

Phase-02+ hardening is out of Phase 01 scope: HKDF per-region key isolation, padding-bucket size obfuscation `{1, 4, 16, 64} MiB`, full memory-hygiene zeroize under cold-boot scenarios, `envoy vault destroy-keys` CLI for T-042 mitigation. Phase-04+ work is out of Phase 01 scope: duress passphrase + honeypot Genesis distinct-from-real, hidden envelope dual-passphrase + dual-Shamir + constant-write-rate, shadow-segment real-only-key separation, `DuressUnlockEvent` write-without-Ledger-sync, regressions T-002 / T-019 / T-040 / T-041 / T-042 / T-071. All Phase-04+ items tracked at `specs/threat-model.md`.

## Open questions

1. Cross-platform shadow-segment binding parity — Linux Secret Service does not always provide secure-enclave-equivalent binding; is the real-passphrase-only encryption sufficient on Linux, or does the segment require a degraded-mode tag indicating reduced-trust binding?
2. Auto-lock 15min default — empirical calibration. Some workflows have legitimate idle periods (deep reading, multi-channel waiting); should the default lengthen, and should the user-configurable bound have a hard ceiling (e.g. 4h max)?
3. Argon2id parameter migration — when Foundation publishes a stronger parameter set (e.g. m=2^18), what is the user-side migration UX (re-derive on next unlock? Explicit ritual? Background re-derivation)?
4. Hidden-envelope decoy traffic — constant-write-rate is documented but the decoy-traffic generator's source-of-randomness needs specification (CSPRNG seed lifecycle, replay resistance) so the decoy is itself indistinguishable from real ciphertext.
5. Duress-mode operation budget — under duress passphrase, the honeypot Genesis still operates; what budgets apply (default-conservative? Configured at duress-passphrase setup?), and how does the runtime ensure the duress session does not perform actions the real session would refuse?
