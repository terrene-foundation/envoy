---
type: DECISION
date: 2026-06-14
author: co-authored
project: phase-02-distribution
topic: S5o-enc — encrypt session-store payload columns at rest (AES-256-GCM), keychain-gated key source instead of the planned vault-passphrase gating
phase: implement
verified_id: 548F2C562EB4246D025FA80A70552B124755B685
source_commit: a1d705242abb440332a590c86c030ab77be388b5
tags:
  [
    decision,
    security,
    encryption-at-rest,
    keychain,
    session-store,
    s5o-enc,
    threat-model-residual,
  ]
relates_to: 0019-DISCOVERY-batch3-reusable-patterns-codify
---

# DECISION — S5o-enc: session-store payload encrypted at rest, keychain-gated

Promoted from the SessionEnd pending stub for commit `a1d705242abb` (PR #110).
Review-fix follow-ups are in `0024`. Closes the `specs/threat-model.md`
§ Residual "session-store local-file-read residual".

## Problem

The vault-sibling session store persisted `request_json` / `resolution_json`
(`pending_grant`) and `state_json` (`session_observed_state`) as canonical-JSON
**plaintext** — protected only by `0o600` perms + a `resolution_sig` tamper
anchor, i.e. integrity but **not confidentiality**. A local-file read (malicious
same-user process, or an unencrypted-disk forensic read) recovered a user's
session-observation state, pending-grant wire payloads, and resolution answers
in the clear. Those columns are now AES-256-GCM ciphertext on disk.

## Decision — keychain-gating over vault-passphrase-gating (the deviation)

The plan anticipated "vault-unlock key material", but the SessionRouter opens
short-lived **one-shot CLI processes** (`grant approve` runs in a fresh process)
that hold no passphrase; a passphrase-gated key would force a vault-unlock
prompt on **every** grant/chat invocation. A dedicated keychain key
(`SESSION_ENCRYPTION_KEY_ID`, namespaced distinctly from the Ed25519 signing
key) closes the same threat without that UX cost, matching the `resolution_sig`
signing key's existing trust model.

**Alternative considered & rejected:** passphrase-gated key derived at
vault-unlock. Rejected because the one-shot CLI process model has no passphrase
to derive from → would have prompted on every invocation. **Co-owner chose
keychain-gating in-session.** The deviation is recorded in
`specs/session-runtime.md` § "Region encryption-at-rest (S5o-enc)" and
`specs/session-state.md`.

## Implementation

- `keystore.py`: `load_or_create_session_encryption_key` — keychain-persisted
  32-byte AES-256 key, same fail-loud taxonomy as the ledger signing key (never
  a silent ephemeral fallback, which would orphan every encrypted row). `_get` /
  `_set` gained a back-compatible `service` param so the session-enc namespace
  is distinct from the signing namespace.
- `session.py`: `enc:v1:` token (nonce ‖ ciphertext ‖ tag, base64), AAD bound to
  `(table, row-key, column)` so a ciphertext cannot be shuffled across
  rows/columns. Encrypt-on-write / decrypt-on-read is transparent at the public
  API; index/key columns stay cleartext so lookups, the CHECK constraint, and
  the lost-update version re-check keep working. `resolution_sig` is signed over
  plaintext **then** the column encrypted — signing + encryption layered, not
  swapped.
- Two read failure modes: `get_pending_grant` (poll/security path) RAISES
  fail-closed; `list_pending_grants` (grant list UI) surfaces a single
  undecryptable row as malformed without aborting the listing.
- `runtime.py`: the `await_decision` poll maps a resolution decrypt failure to
  `GrantMomentResolutionUnauthenticatedError` — a forged direct-sqlite row
  (written without the key) is now rejected at decrypt, strictly earlier than
  sig-verify.

## What it unlocks / blocks

- **Unlocks:** removes the session-store confidentiality residual from the
  threat model; establishes the `enc:v1:` + AAD-binding pattern any future
  at-rest column reuses (see `0019` reusable-patterns trail).
- **Residual (documented, P16):** same-user + keychain-readable decrypt is a
  device-compromise class, out of the local-file-read scope this shard closed
  (`threat-model.md` § Residual).
- **Operational invariant for every consumer:** thread ONE keychain backend into
  EVERY consumer — SessionRouter now loads TWO keychain keys (signing +
  encryption). Cross-process CLI tests MUST share one backend (see the
  `headless-keychain-ci-parity` auto-memory + the `.session-notes` Traps).

## Verification

8 encryption Tier-2 tests (ciphertext-on-disk, cross-process round-trip,
keychain-gated no-decrypt, signing-over-encryption, ciphertext-tamper, AAD
binding) + keystore loader fail-loud coverage. Full suite 2441 passed; mypy
clean. User-flow walk: `envoy grant list` decrypts a seeded grant cross-process
via the shared OS keychain; raw db read shows `enc:v1:` ciphertext, no plaintext.
Reviewer + security-reviewer approved (MEDIUM findings fixed in-shard → `0024`).
