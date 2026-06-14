---
type: RISK
date: 2026-06-14
author: co-authored
project: phase-02-distribution
topic: S5o-enc security-reviewer MEDIUM fixes — honest zeroization caveat + request_json authenticity trust-boundary note (documentation-clarity, no behavior change)
phase: implement
verified_id: 548F2C562EB4246D025FA80A70552B124755B685
source_commit: 078ff15d41fdade4717b06682ee887ef7b9b5b90
tags: [risk, security, encryption-at-rest, zeroization, trust-boundary, s5o-enc]
relates_to: 0023-DECISION-s5o-enc-session-store-encryption-keychain-gated
---

# RISK — S5o-enc review fixes: zeroization is best-effort; request_json is confidential, not authentic

Promoted from the SessionEnd pending stub for commit `078ff15d41fd`. Two
security-reviewer MEDIUM findings on the S5o-enc shard (`0023`), both
documentation-clarity — **no behavior change**. Fixed in-shard per
`autonomous-execution.md` Rule 4 (same-bug-class gap within budget, context warm).

## M1 — zeroization is best-effort, not a hard guarantee (honest caveat)

`_require_enc_key` returns an immutable `bytes` copy and AESGCM copies the key
into the OpenSSL context; **neither can be zeroized**. The original phrasing
implied `close()`'s `bytearray` zeroize wiped the key material. Corrected: the
zeroize is **best-effort residency minimisation** (matching the vault's
master-key handling), NOT a hard guarantee. A heap-reading attacker is **out of
scope** per `threat-model.md` § Out of scope; this key closes the local-**FILE**
read class, not in-process memory disclosure.

**Residual (named, accepted):** an attacker with live-process heap read recovers
the key. Device-compromise / same-process class — the same boundary as P16. Not
a regression; the shard's stated scope was always local-file-read.

## M2 — displayed request_json is confidential but NOT authenticity-protected

`list_pending_grants` now documents that the displayed `request_json` is
**confidentiality-** but **NOT authenticity**-protected against a key-holding
writer (only `resolution_json` is signed). The AAD prevents **intra-store
shuffling**, not **forgery by a key holder**. The listing is **advisory**; the
actual decision is gated on the signed `resolution` verified on the strict poll
path (`get_pending_grant`, which RAISES fail-closed on decrypt failure).

**Trust-boundary statement (for the next session):** anyone who can write the
encrypted store also holds the encryption key, so encryption alone cannot make
the _displayed_ request trustworthy — only the signed resolution on the poll
path is load-bearing for the security decision. This is why the grant-list UI is
explicitly advisory and the poll path is the authority.

## Why journal-worthy

Both are trust-boundary clarifications a future reader of the S5o-enc surface
must not re-derive: the encryption closes file-read confidentiality, NOT
in-memory disclosure (M1) and NOT displayed-payload authenticity (M2). Pairs
with the P13 fingerprint `name‖args` seam and the keychain residual (P16).
