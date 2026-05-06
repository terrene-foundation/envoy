---
type: DECISION
date: 2026-05-06
created_at: 2026-05-06T00:00:00Z
author: agent
session_id: phase-01-mvp-implement-t-01-13
session_turn: 1
project: envoy
topic: T-01-13 Trust Vault Phase 01 narrow scope — what ships now vs deferred
phase: implement
tags:
  [
    trust-vault,
    aes-256-gcm,
    argon2id,
    phase-01-narrow-scope,
    secure-enclave-deferred,
    shamir-deferred,
    duress-deferred,
    padding-buckets-deferred,
    r2-m-02,
  ]
---

# T-01-13 Trust Vault Phase 01 narrow scope

## Context

`specs/trust-vault.md` describes a comprehensive vault with file format spanning {magic, algorithm_identifier, padding-bucket size, encrypted master key (Shamir-wrapped), encrypted regions for envelope / posture / Shamir commitments / ritual state / chain head / enterprise cache / first-time fingerprints / hidden envelope, padding, MAC tag}. Per § Encryption: AES-256-GCM outer + Argon2id passphrase XOR with Secure-Enclave/TPM-bound secret + per-region HKDF-SHA-256. Per § Memory hygiene: 15-minute idle auto-lock + zeroize. Per § Duress support: dual passphrase / honeypot Genesis. Per § Hidden envelope: Phase 04 indistinguishability.

Wave 1 plan T-01-13 specifies "AES-256-GCM Trust Vault container + lifecycle (R2-M-02)" with capacity ~300 LOC + 4 invariants. The spec describes ~10 sub-systems; T-01-13's budget covers ~3.

## Decision

T-01-13 ships the **minimum-viable-vault** — the cryptographic substrate that Wave 1 + 2 + 3 primitives need to keep keys + envelope at rest, deferring the Phase 02+ surface to its own shards.

### IN scope (T-01-13 ships now)

1. **AES-256-GCM single-region container** — outer encryption per spec § Encryption. Single-region = the entire payload encrypts under one key; Phase 02 splits into envelope / posture / Shamir / ritual-state regions with per-region HKDF keys.
2. **Argon2id passphrase derivation** — canonical params (m=2^17, t=3, p=1) per spec § Encryption. Non-canonical stored params raise `Argon2ParameterMismatchError`.
3. **Lifecycle (R2-M-02 carry-forward)** — `unlock(passphrase)` / `lock()` / `__aexit__` / `_idle_timer_reset` / `VaultLockedError`. The `unlocked(passphrase)` context manager is the canonical caller-side surface; `__aenter__` / `__aexit__` form the auto-lock guarantee.
4. **15-minute idle auto-lock** per spec § Memory hygiene. `AutoLockIdleTimeoutError` distinguishes auto-locked from never-unlocked.
5. **Atomic write + restrictive permissions** per `rules/trust-plane-security.md` MUST Rules 6 + 7. Temp file + fsync + `os.replace`; `chmod 0o600` (POSIX).
6. **Best-effort key zeroize** on `lock()` per `rules/trust-plane-security.md` MUST NOT Rule 3. The master key bytearray is overwritten in-place; payload reference is dropped (not zeroized — Phase 02 copies into `bytearray` for explicit cleansing).

### OUT of scope (deferred to Phase 02+ shards)

| Deferred feature                              | Earliest shard | Spec reference                                                    | Rationale for deferral                                                                                            |
| --------------------------------------------- | -------------- | ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Secure-Enclave / TPM-bound secret XOR         | Phase 02       | `specs/trust-vault.md` § Encryption                               | Platform-specific (`security` framework on macOS / `tpm2-tss` on Linux / DPAPI on Windows); each is its own shard |
| Per-region HKDF-SHA-256 keys                  | Phase 02       | `specs/trust-vault.md` § Encryption                               | Requires region-layout serialization which depends on Posture Store + Authorship Score landing                    |
| Shamir-wrapped master key                     | T-15 (Wave 2)  | `specs/trust-vault.md` § File format + `specs/shamir-recovery.md` | Shamir 3-of-5 ritual is its own primitive (T-15 ShamirRitualCoordinator)                                          |
| Padding buckets {1, 4, 16, 64} MiB            | Phase 04       | `specs/trust-vault.md` § Padding buckets                          | Hidden-envelope indistinguishability requires the full Phase 04 traffic-pattern uniformity                        |
| Duress passphrase + honeypot Genesis          | Phase 04       | `specs/trust-vault.md` § Duress support                           | Honeypot Genesis requires the full duress-distinct trust-lineage path; CRIT-03 is a Phase 04 gate                 |
| Hidden envelope + shadow segment              | Phase 04       | `specs/trust-vault.md` § Hidden envelope                          | Constant-write-rate + decoy-traffic generator is Phase 04 work                                                    |
| `envoy vault destroy-keys` CLI                | Phase 02       | `specs/trust-vault.md` § Key destruction                          | T-042 mitigation; needs the full envoy.cli surface (T-19 in Wave 5)                                               |
| TrustStoreAdapter integration (vault-wrapped) | T-01-16        | `01-analysis/05` § 4 step 3                                       | Tier 2 wiring decision — T-01-13 ships the vault primitive in isolation; T-01-16 wires SQLite path through vault  |

### Decision rationale

Phase 01 narrow scope respects three constraints:

1. **Shard budget** (`rules/autonomous-execution.md` MUST Rule 1): ≤500 LOC load-bearing + ≤5–10 invariants + ≤3 call-graph hops. Full vault would exceed all three.
2. **Wave-1 dependency closure**: T-01-13 ships the vault primitive that T-01-16 (Tier 2 wiring) integrates with TrustStoreAdapter. Wave 2 / 3 primitives import only the unlock/lock/read/write surface — every consumer's contract is satisfied.
3. **Phase 02+ shards land independently**: each deferred feature has a clean shard slot. Per-region HKDF lands when the second region (Posture Store) ships. Shamir wrap lands at T-15 with the recovery ritual. Duress / hidden envelope land at Phase 04 alongside the channel-adapter constant-write-rate work.

## Alternatives considered

### Alternative 1: Ship the full vault now (rejected)

Estimated ~1500 LOC + 12 invariants + 6 call-graph hops. Exceeds shard budget by 3×. Would force Wave 2 / 3 primitives to wait on cross-cutting concerns (Shamir, duress) that don't gate their own load-bearing logic.

### Alternative 2: Ship single-region without idle-lock (rejected)

R2-M-02 carry-forward disposition explicitly mandates the lifecycle surface as part of T-01-13. Skipping idle-lock would defer the documented `rules/trust-plane-security.md` MUST NOT Rule 3 (key residency) to a later shard with no caller-side guarantee in the meantime.

### Alternative 3: Use SQLCipher instead of bespoke AES-GCM (rejected)

SQLCipher is a fork of SQLite with built-in AES encryption. Two reasons against: (1) the vault holds more than just SQLite (envelope, ritual state, Shamir commitments — multiple regions Phase 02+); (2) SQLCipher's key-derivation is PBKDF2-HMAC-SHA1 by default with vendor-specific Argon2 support, while the spec mandates Argon2id at exact m/t/p parameters. Bespoke control of file format + KDF is strictly required for the spec contract.

## Consequences

- T-01-14 (cascade + algorithm_id helpers) and T-01-16 (Tier 2 wiring) can begin immediately with the T-01-13 surface.
- Wave 1 milestone passes the R2-M-02 lifecycle invariant; vault ships with `AutoLockIdleTimeoutError` distinguishable from `VaultLockedError`.
- 7 deferred features tracked in this journal entry's table — each gates a Phase 02+ shard. Future `/redteam` rounds can grep this entry for "deferred to" to enumerate the gap.
- Test coverage: 25-case Tier 1 battery covers all 4 invariants + 5 typed errors; production verification gate is `117 passed, zero warnings`.

## For Discussion

1. The single-region Phase 01 design loses one defense the multi-region Phase 02 design has: a per-region key compromise contains the blast radius to that region only. Phase 01's single-key compromise leaks all of envelope + posture + ritual-state. Is the Phase 01 → Phase 02 migration window (estimated Wave 2 → Phase 02 entry) tight enough to bound this risk, or should T-01-13 ship at least the region demarcation (with Phase 01 using a single key but Phase 02 swapping to per-region keys) so the file format doesn't break compatibly?

2. The 15-minute idle TTL is hard-coded as the default. The spec § Memory hygiene says "configurable" — currently it's a constructor argument. Should there be an environment variable (`ENVOY_VAULT_IDLE_TTL_SECONDS`) consumed at adapter construction time so operators can tune without code changes? And what's the floor — does a 30-second TTL violate the spec's intent (UX expectation of "I came back from making coffee, vault is still open")?

3. The `__del__` emits `ResourceWarning` but doesn't call `lock()`. Per `rules/patterns.md` § Async Resource Cleanup, calling async cleanup from a finalizer thread deadlocks. Should there be a `weakref.finalize` callback that schedules a sync zeroize (no event loop) as a defense against the user who forgets the `async with`? The trade-off is: weakref.finalize fires on GC which is non-deterministic, but at least zeros the bytearray slot earlier than waiting for process exit.
