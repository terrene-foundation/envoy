# Flow 07 — Ledger export + independent verification

**Document role:** Phase 01 user flow #7 of 8 (shard 21 of /analyze). Describes both halves of the user-visible Ledger verification ritual: (a) the **export** half — running `envoy ledger export` to produce a signed bundle, and (b) the **independent verification** half — installing a separately-codebased verifier (`terrene-foundation/envoy-ledger-verifier`) and running it against the bundle. EC-4 + EC-9 are the strongest Phase 01 acceptance gates because the verifier proves the security primitive (hash chain) works under adversarial assumption rather than developer assumption.

**Date:** 2026-05-03 (shard 21 of /analyze; wave F user flows).
**Owning primitive shards:** 6 (Envoy Ledger: hash chain, canonical-JSON pipeline, `envoy ledger export --format json` producer), 7 (Independent Verifier: separate repo, separate codebase, separate language preferred; trust-anchor resolution; mutation battery; source-isolation enforcement), 5 (Trust store: Genesis Record + signing keys backing the bundle's `trust_anchor_key_set`), 15 (Shamir 3-of-5: trust-anchor file recommended to be stored with paper cards).
**Exit criteria served:** **EC-4 (BLOCKING)** + **EC-9 (BLOCKING)** — the strongest Phase 01 gate. Per `02-mvp-objectives.md` § 4 ship predicate, both are NON-DEGRADABLE; failure blocks ship.
**Communication discipline:** Plain language per `rules/communication.md`.

---

## 1. Persona & context

**Primary persona (export half):** A user 1–4 weeks into using Envoy who has accumulated a real Ledger — at least one signed envelope, several Grant Moments, a few Daily Digest deliveries, channel connect/disconnect events. They want to keep a personal copy AND/OR they want to verify the ledger is intact (paranoid about whether their Envoy install is being tampered with, or doing routine sovereignty hygiene).

**Primary persona (verify half):** Same user OR a different agent on the user's behalf — e.g., a friend who is technical, a family member helping out, a professional auditor the user has retained, or simply the user themselves on a different machine with no Envoy installed.

**Device + channel:** CLI on the user's laptop for export. The verifier MAY run on the same laptop OR on a different machine entirely — the structural promise of EC-9 is that the verifier shares zero source with the producer, so even running on the same laptop is meaningful (different process, different binary, different codebase).

**Trigger:**

- Export: explicit user command `envoy ledger export --format json`. Phase 01 ships export as a CLI command per `specs/ledger.md` § Export + independent verifier line 590.
- Verify: explicit user command `envoy-ledger-verify verify <bundle.json> --trust-anchor <anchor.json>`. Per shard 7 § 3.

---

## 2. Trigger

**Export half:**

1. User runs `envoy ledger export --format json --output ~/envoy-ledger-2026-05-03.json`.
2. Internally, the `EnvoyLedger` reads every entry in chain order, normalizes via the canonical-JSON pipeline (shard 6 § 3.2), bundles per the wire format defined in shard 7 § 3.3, attaches the `trust_anchor_key_set`, computes the `receipt_hash`, and writes to disk.

**Verify half:**

1. User installs the verifier: `pip install envoy-ledger-verifier` (separate package per shard 7 § 3.1) OR `cargo install envoy-ledger-verifier` for the Rust variant (Phase 01 stretch per shard 7 § 3.2).
2. User obtains the trust-anchor file out-of-band — Phase 01 minimum is **option C self-anchoring** per shard 7 § 3.4 (run the verifier once with `--emit-trust-anchor` to extract the anchor, store it securely with the Shamir paper cards).
3. User runs `envoy-ledger-verify verify <bundle.json> --trust-anchor <anchor.json>`.
4. Verifier walks the chain, validates every signature, runs the mutation-detection battery, exits 0 on clean OR non-zero with typed error.

---

## 3. Happy path (plain language)

### 3A — Export half

#### Step 1 — Initial command + confirmation

```
$ envoy ledger export --format json --output ~/envoy-ledger-2026-05-03.json

   I'll export your Ledger to ~/envoy-ledger-2026-05-03.json.

   Your Ledger has:
     - 1,247 entries
     - 3 Grant Moments (1 approved, 1 declined, 1 modified)
     - 12 Daily Digest deliveries
     - 4 channel connect/disconnect events

   The export will be about 1.8 MB. It includes the public keys
   needed to verify it (so anyone you give the file to can check it
   was really produced by your Envoy install, without needing access
   to your private keys).

   Press Enter to continue, or Ctrl-C to cancel.
```

Per shard 6 § 3.2 + shard 7 § 3.3, the bundle includes the `trust_anchor_key_set` so a downstream verifier can resolve `signed_by` references — though the user should NOT rely on the bundle's self-declared keys (that's circular per shard 7 § 3.4); the trust-anchor file is the structural defense.

#### Step 2 — Canonicalization + signature collection (≈800ms-3s for ~1k entries)

```
   Reading your Ledger...
   Canonicalizing entries (this is what makes the export verifiable)...
   Computing receipt hash...
   Done.

   Wrote ~/envoy-ledger-2026-05-03.json (1.83 MB).

   What to do next:
     1. Keep this file somewhere safe (an encrypted backup, a USB
        stick, a cloud drive — your choice; the file is signed, so
        tampering will be detected).
     2. To verify it independently, install the verifier:

           pip install envoy-ledger-verifier

        Then run:

           envoy-ledger-verify verify ~/envoy-ledger-2026-05-03.json

        See `envoy ledger verify-help` for the full guide.
```

Per shard 6 § 3.2, the canonical-JSON serialization (NFC normalization + RFC 8785 JCS + microsecond-padded timestamps per #731 + Unicode pinning per #757/#756) IS what makes the export byte-stable — a re-canonicalization in any language produces the same bytes for the same logical content.

#### Step 3 — Optional PDF receipt (≈1–2s)

```
$ envoy ledger export --format pdf --output ~/envoy-ledger-2026-05-03.pdf

   I made a one-page PDF receipt instead of the full JSON.

   The PDF is a human-readable summary of your Ledger:
     1,247 entries
     SHA-256 receipt hash: sha256:9a8b7c6d5e4f3a2b...
     Date range: 2026-04-15 → 2026-05-03

   The receipt hash points to the JSON form. To verify, you'll
   still need the JSON — keep them together.

   Wrote ~/envoy-ledger-2026-05-03.pdf (38 KB).
```

Per `specs/ledger.md` line 591, the PDF carries `receipt_hash` pointing to JSON. The PDF is not standalone — it is a human-readable handle for the JSON.

### 3B — Verify half (independent)

#### Step 1 — Install separate package

```
$ pip install envoy-ledger-verifier

   Successfully installed envoy-ledger-verifier-0.1.0
```

Per shard 7 § 3.1, the package lives in a SEPARATE repo (`terrene-foundation/envoy-ledger-verifier`) with separate codebase, separate license headers per § 3.6, separate CI, separate contributors. Per shard 7 § 2, the verifier MUST NOT import any `envoy.ledger.*` symbol — it re-implements canonical-JSON parsing from the spec. Source-isolation is the structural defense against "producer and verifier silently agree because they share a serialization library" failure mode.

#### Step 2 — First verification (self-anchoring; option C per shard 7 § 3.4)

If the user has never verified before, they need a trust-anchor file. Phase 01's simplest path is the self-anchoring command:

```
$ envoy-ledger-verify --emit-trust-anchor ~/envoy-ledger-2026-05-03.json > ~/envoy-trust-anchor.json

   I've extracted the trust anchor from this bundle. The trust
   anchor is the public key that proves your Envoy install made
   this Ledger.

   Store ~/envoy-trust-anchor.json somewhere safe — ideally with
   your Shamir backup cards (the cold-storage location an online
   attacker can't reach).

   For all FUTURE verifications, use this same anchor file:
     envoy-ledger-verify verify <new-bundle.json> --trust-anchor ~/envoy-trust-anchor.json

   Wrote 0.4 KB.
```

Per shard 7 § 3.4 channel #2 (emit-on-first-verification self-anchoring): the trust model is "I am verifying that future Ledgers are continuous with the first Ledger I ever exported." An attacker who modifies a future bundle cannot modify the local anchor file (which lives on the user's machine). Phase 01 minimum.

#### Step 3 — Run the verifier

```
$ envoy-ledger-verify verify ~/envoy-ledger-2026-05-03.json --trust-anchor ~/envoy-trust-anchor.json

   Verifying ~/envoy-ledger-2026-05-03.json...

     Reading bundle...                                           OK
     Re-canonicalizing entries (independent of producer code)... OK
     Walking chain (1,247 entries)...                            OK
     Verifying signatures (1,247 entries)...                     OK
     Verifying head commitment...                                OK
     Verifying receipt hash...                                   OK
     Trust anchor matches Genesis principal...                   OK

   1,247 entries — all valid.
   Date range: 2026-04-15 → 2026-05-03.
   No tampering detected.

$ echo $?
0
```

Per shard 7 § 3.3, the verifier asserts 8 invariants:

1. Entries non-empty AND ordered by sequence.
2. Genesis at index 0 (or explicit `start_after_sequence`).
3. Chain integrity (`parent_hash == sha256(prev entry_id)` for all i>0).
4. Content addressing (`entry_id == sha256(canonical(entry minus entry_id+sig))`).
5. Signature integrity (Ed25519 verifies against trust-anchor key set).
6. Head commitment matches last entry.
7. Head commitment signature verifies.
8. `receipt_hash` self-integrity.

Plus the 5-class mutation battery per shard 7 § 3.5: bit-flip, insertion, deletion, reorder, duplication. ALL must be detectable.

The user sees a simple success message + exit 0. The cryptographic detail is rendered in plain language.

#### Step 4 — Tampering detection (illustrative, NOT a happy-path step but the EC-4 acceptance test)

If an attacker has modified the bundle (e.g., flipped a single bit in the financial dimension of an envelope edit entry), the verifier fails:

```
$ envoy-ledger-verify verify ~/envoy-ledger-2026-05-03.tampered.json --trust-anchor ~/envoy-trust-anchor.json

   Verifying...

     Reading bundle...                                           OK
     Re-canonicalizing entries...                                OK
     Walking chain (1,247 entries)...                          FAIL

   ✗ Tampering detected at entry 873.

     The signature on entry 873 doesn't match the entry's contents.
     This means either (a) the bundle was modified after your Envoy
     install signed it, or (b) the signing key on this entry is
     different from the trust anchor you supplied.

     Entry 873 — type: envelope_edit
     Entry 873 — timestamp: 2026-04-28T14:32:11.473821Z

     If you're running this against a trust-anchor you just
     emitted from this same bundle (`--emit-trust-anchor`), this
     should NEVER happen. If it does, your Envoy install or your
     anchor file may be compromised. Contact support / re-shard
     your Trust Vault from your Shamir paper cards.

$ echo $?
3
```

Per shard 7 § 3.3 invariant 5 + § 3.5 class 1 (bit-flip detection). The verifier exits non-zero with `LedgerVerificationFailedError` and a typed payload naming the failing entry index. Tier 3 test `tests/e2e/test_envoy_ledger_tampering_battery.py` per shard 7 § 3.5 is the EC-4 structural test.

---

## 4. Edge cases (≥3 required)

### EC-A — User has no trust-anchor file yet (first verification)

Scenario: User runs `envoy-ledger-verify verify <bundle>` without `--trust-anchor`.

Plain-language UX:

```
   I need a trust-anchor file to verify this bundle. The trust
   anchor is the public key that proves your Envoy install made
   this Ledger; I can't trust the bundle's self-declared key
   because that would be circular.

   Two options:
     [1] Self-anchor from THIS bundle (the easy path):
            envoy-ledger-verify --emit-trust-anchor <bundle> > anchor.json
         Then run verify again with --trust-anchor anchor.json.
         Store the anchor.json somewhere safe — ideally with your
         Shamir paper cards.

     [2] Use a previously-extracted anchor file (the better path
         for repeated verification): supply --trust-anchor
         path/to/your/anchor.json.

   For Phase 01, option [1] is the recommended starting point.
```

Recovery: per shard 7 § 3.4, Phase 01 minimum is option C with channel #2 (emit-on-first-verification self-anchoring). User runs the emit command and re-tries.

### EC-B — Trust-anchor file doesn't match the bundle's `trust_anchor_key_set`

Scenario: User supplies an old `anchor.json` from a different Envoy install (e.g., they restored from Shamir cards but accidentally grabbed the wrong anchor file).

Plain-language UX:

```
   Verifying...

     Reading bundle...                                           OK
     Trust anchor matches Genesis principal...                 FAIL

   ✗ The trust anchor file you supplied doesn't match this bundle.

     This means one of:
       (a) The anchor is from a different Envoy install (did you
           grab the wrong file?)
       (b) The bundle was produced by a different Envoy install
           than the one your anchor came from
       (c) Either the anchor or the bundle has been tampered with

     If you have multiple anchor files (e.g., from different
     installs), make sure you're using the one that matches the
     install whose Ledger you're verifying.
```

Recovery: per shard 7 § 3.4, the trust-anchor file is the structural defense against tampering — mismatch is by design a refusal. User finds the correct anchor (likely with their Shamir cards) and re-runs.

### EC-C — Bundle is large (10k+ entries) — performance question

Scenario: User has been operating Envoy for a year. Their Ledger is now 50,000 entries. Export and verify both run.

Plain-language UX (export):

```
$ envoy ledger export --format json --output ~/envoy-ledger-2027-05-03.json

   Reading your Ledger (50,247 entries)...
   This will take about 30 seconds.
   Progress: ▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░ 65%
```

Plain-language UX (verify):

```
$ envoy-ledger-verify verify ~/envoy-ledger-2027-05-03.json --trust-anchor ~/envoy-trust-anchor.json

   Verifying...
     Walking chain (50,247 entries)...
     Verifying signatures (this is the slow part)...
     Progress: ▓▓▓▓▓▓▓▓░░░░░░░░░░░░ 40%   ETA 1m 30s
```

Recovery: structural — Phase 01 sizing assumes typical user produces O(1k-10k) entries per quarter; 50k is at the edge of "reasonable laptop runtime." Per shard 6, the chain walk is O(N); signature verify is O(N) Ed25519 ops (~50µs each on a 2020-era laptop); 50k × 50µs = 2.5s. The progress bar exists per `rules/communication.md` MUST NOT empty silence.

### EC-D — Verifier on a fresh laptop with no Envoy install

Scenario: User wants to verify a bundle on their friend's laptop (perhaps the friend is technical and the user wants a second pair of eyes).

Plain-language UX:

```
(on friend's laptop)
$ pip install envoy-ledger-verifier
$ envoy-ledger-verify verify <bundle> --trust-anchor <anchor>
```

The friend doesn't need Envoy installed — only the verifier. Per shard 7 § 3.1, the verifier is a SEPARATE package with no Envoy dependencies. This is the structural-isolation promise.

Recovery: structural — works as designed. The verifier ships as `pip install envoy-ledger-verifier` (separate package) AND optionally as `cargo install envoy-ledger-verifier-rs` for the Rust variant. Per shard 7 § 3.2, Rust is preferred for source-isolation strength; Python is the Phase 01 minimum.

### EC-E — Bundle contains a `MigrationAnnouncement` entry (algorithm rotation)

Scenario: A Phase 04+ bundle contains a `MigrationAnnouncement` segmenting the chain into pre-PQ and post-PQ algorithm-identifier segments per `specs/ledger.md` § Segment boundary on MigrationAnnouncement.

Plain-language UX (Phase 01 verifier — DEFERRED):

```
   Verifying...

   ! This bundle has multiple algorithm segments.

     Phase 01 verifies single-algorithm bundles. Multi-algorithm
     bundles (post-quantum migration) are Phase 04. The current
     bundle has 1,247 entries before the algorithm change and
     12 entries after.

     I'll verify the first 1,247 entries (single-algorithm) and
     stop at the boundary. To verify the post-migration entries,
     use the Phase 04 verifier (envoy-ledger-verify >= 2.0).
```

Recovery: per shard 6 § 1.3 + `specs/remote-time-anchor.md` deferral, multi-algorithm-segment verification is Phase 04+. Phase 01 MUST surface a typed `UnsupportedExportFormatError` per shard 7 § 1.2 when presented with a merged-bundle export. Phase 01 export bundles are ALWAYS single-segment because the migration ritual hasn't fired.

### EC-F — Bundle is from a multi-device install (Phase 03+)

Scenario: A future Phase 03+ user has a multi-device install where the Ledger has been merged via the `ledger-merge` CRDT protocol per `specs/ledger-merge.md`.

Plain-language UX (Phase 01 verifier):

```
   ! This bundle was produced by a multi-device Envoy install.

     Phase 01 verifies single-device bundles. Multi-device bundles
     (where the Ledger has been merged across machines) are Phase
     03. Use the Phase 03 verifier (envoy-ledger-verify >= 3.0)
     for these bundles.
```

Recovery: per shard 7 § 1.2, Phase 01 verifier raises `UnsupportedExportFormatError` on merged bundles. Phase 03 verifier wires merge-replay verification.

### EC-G — Trust-anchor file lives WITH the Shamir paper cards

Scenario: User stored their `envoy-trust-anchor.json` on a USB stick in their bank deposit box, alongside 3 of their 5 Shamir paper cards (Flow 06).

Plain-language UX (when accessed during catastrophe recovery):

User retrieves the USB stick + 3 cards from the deposit box. They run Flow 06 reconstruct → recovered Trust Vault. They run `envoy ledger export` on the new install → bundle. They run the verifier with `--trust-anchor <USB stick path>` → if everything matches, the recovery is end-to-end verified.

Recovery: structural — the two flows compose. Per shard 7 § 3.4 + `02-mvp-objectives.md` EC-9 acceptance: "trust-anchor file is out-of-band relative to the bundle being verified." Storing it with the Shamir cards means the SAME catastrophe-recovery ritual that gives the user back their Trust Vault ALSO gives them back their verifier anchor.

---

## 5. Underlying primitives

| Step                         | Primitive (shard)                           | What runs                                                                                                                                                 |
| ---------------------------- | ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `envoy ledger export`        | shard 6 § 4 + shard 6 § 3.2                 | `EnvoyLedger` reads chain in order; `envoy.ledger.canonical.canonical_dumps` re-emits each entry; `trust_anchor_key_set` collected                        |
| Bundle wire format           | shard 7 § 3.3                               | JSON shape with `schema_version: "envoy-ledger-export/1.0"`, `segment_boundaries`, `entries[]`, `head_commitment`, `trust_anchor_key_set`, `receipt_hash` |
| `receipt_hash` computation   | shard 7 § 3.3 invariant 8 + shard 6 § 3.2   | `sha256(canonical_json(bundle minus receipt_hash))` for self-integrity                                                                                    |
| Optional PDF receipt         | shard 6 § 3.2 (PDF surface stretch)         | One-page summary; carries `receipt_hash` pointing to JSON                                                                                                 |
| Verifier install             | shard 7 § 3.1 + § 3.2                       | `pip install envoy-ledger-verifier` (Phase 01 minimum) OR `cargo install envoy-ledger-verifier-rs` (Phase 01 stretch)                                     |
| Trust-anchor emit            | shard 7 § 3.4 channel #2                    | `envoy-ledger-verify --emit-trust-anchor <bundle> > anchor.json` extracts Genesis principal pubkey                                                        |
| Chain walk                   | shard 7 § 3.3 invariants 1–4                | Verifier walks `entries[]`; checks order, parent_hash chain, content addressing                                                                           |
| Signature verify             | shard 7 § 3.3 invariant 5 + Ed25519 re-impl | Verifier verifies each entry's `signature_hex` against trust-anchor public key (re-implemented Ed25519, NOT shared with producer)                         |
| Head commitment verify       | shard 7 § 3.3 invariants 6–7                | `head_sequence == entries[-1].sequence` AND head commit signature verifies                                                                                |
| Receipt hash self-verify     | shard 7 § 3.3 invariant 8                   | Recomputed `sha256(canonical(bundle minus receipt_hash))` matches embedded `receipt_hash`                                                                 |
| Mutation battery             | shard 7 § 3.5                               | 5-class detection: bit-flip / insert / delete / reorder / duplicate; each detectable via invariant violation                                              |
| Source-isolation enforcement | shard 7 § 3.6                               | CI: import-path check (no `envoy.*` deps); license-header per source file; producer-fixture provenance check                                              |

---

## 6. Acceptance criteria served

- **EC-4 (BLOCKING):** This flow IS the EC-4 surface end-to-end. Acceptance per `02-mvp-objectives.md` EC-4: a Ledger exported by `envoy ledger export` is verified by a CLI tool that (a) lives in a different repo / package, (b) shares zero source code with the Envoy codebase, (c) is implemented in a different language OR by a different agent without reference to the producer's source. The verifier MUST detect any tampering attempt (single-bit flip in any payload field; insertion / deletion / reorder of any entry).
- **EC-9 (BLOCKING):** The verifier itself is a Phase 01 deliverable per `02-mvp-objectives.md` EC-9. Acceptance: separate repo (`terrene-foundation/envoy-ledger-verifier`), Python implementation by a different agent OR Rust (preferred per `rules/testing.md` Tier 3 cross-implementation discipline). Per `02-mvp-objectives.md` § 4 Phase 01 ship predicate, BOTH EC-4 AND EC-9 are required; per § 5 failure-mode disposition both are BLOCKING (no degrade-acceptable).
- **EC-9 strongest gate:** per `02-mvp-objectives.md` EC-4 framing, this is "the only one that proves the security primitive (hash chain) works under adversarial assumption rather than developer assumption." If a separately-codebased verifier in a different language / by a different agent verifies a tamper-free bundle AND detects every mutation in a tamper battery, the security primitive holds. If it doesn't, the audit-trail claim is theatre.

---

## 7. Failure modes & recovery

| Failure                                    | What the user sees                                                                                                                | Recovery path                                                                               |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| No trust-anchor (EC-A)                     | "I need a trust-anchor file. Self-anchor from this bundle, or supply a previously-extracted one."                                 | Self-anchor with `--emit-trust-anchor`; store securely with Shamir cards                    |
| Anchor mismatch (EC-B)                     | "The trust anchor file doesn't match this bundle. Different install, different bundle, or tampering."                             | User finds correct anchor (likely with Shamir cards); re-run                                |
| Tampering detected                         | "Tampering detected at entry N. Signature mismatch. Either the bundle was modified after signing, or your trust anchor is wrong." | `LedgerVerificationFailedError`; exit non-zero; user investigates / re-installs / re-shards |
| Multi-algorithm bundle (EC-E)              | "This bundle has multiple algorithm segments. Phase 01 verifies single-algorithm only. Use Phase 04 verifier."                    | `UnsupportedExportFormatError`; partial verify of single-segment portion                    |
| Multi-device merged bundle (EC-F)          | "This bundle was produced by a multi-device install. Use Phase 03 verifier for merged bundles."                                   | `UnsupportedExportFormatError`; user installs Phase 03 verifier                             |
| Bundle file corrupt / not JSON             | "I couldn't read this file as a Ledger bundle — the JSON looks corrupted or truncated."                                           | User re-exports from producer; if export itself fails, audit Trust Vault                    |
| Verifier package name typo                 | "There's no package called `envoy-ledger-verify` — did you mean `envoy-ledger-verifier`?"                                         | User corrects typo                                                                          |
| Source-isolation CI fails (developer-side) | (NOT user-facing — surfaces in verifier repo CI)                                                                                  | Per shard 7 § 3.6, CI rejects PR with `envoy.*` import or missing license header            |
| Performance on large bundle (EC-C)         | Progress bar; ETA visible; never empty silence                                                                                    | Per `rules/communication.md` MUST NOT empty silence                                         |

All recovery paths are user-driven AND recoverable. The only NON-recoverable case is "tampering detected AND user has no clean copy" — at which point the user must restore from Shamir cards (Flow 06) and treat the install as compromised. This is the structural promise: detection IS the recovery start.

---

## 8. Cross-references

- `workspaces/phase-01-mvp/01-analysis/06-envoy-ledger-implementation.md` § 3 (Envoy-new-code surface), § 3.2 (canonical-JSON pipeline), § 4 (`EnvoyLedger.append`)
- `workspaces/phase-01-mvp/01-analysis/07-independent-verifier-design.md` § 3.1 (separate repo recommendation), § 3.2 (language), § 3.3 (bundle wire format), § 3.4 (trust-anchor resolution), § 3.5 (mutation battery), § 3.6 (source-isolation CI)
- `workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md` § 4 (Genesis Record + signing keys backing `trust_anchor_key_set`)
- `workspaces/phase-01-mvp/01-analysis/15-shamir-recovery-implementation.md` § 3.1 (the trust-anchor file is recommended cold-storage WITH the Shamir paper cards)
- `workspaces/phase-01-mvp/03-user-flows/06-shamir-backup-flow.md` (the trust-anchor file rides with the Shamir cards; the two flows compose for catastrophe-recovery)
- `workspaces/phase-01-mvp/03-user-flows/04-daily-digest-flow.md` (the digest mentions Ledger entries that the verifier can confirm)
- `specs/ledger.md` § Entry envelope schema, § Two-phase signing, § Head commitment, § Segment boundary on MigrationAnnouncement, § Export + independent verifier, § Error taxonomy `LedgerVerificationFailedError`
- `specs/ledger-merge.md` (deferred to Phase 03 verifier; Phase 01 verifier raises `UnsupportedExportFormatError` on merged bundles)
- `02-mvp-objectives.md` EC-4 (mutation-detection battery), EC-9 (separately-codebased verifier acceptance)
- `rules/testing.md` Tier 3 (cross-implementation logic; Rust preferred for source-isolation strength)
- `rules/communication.md` (plain-language framing; never empty silence)
