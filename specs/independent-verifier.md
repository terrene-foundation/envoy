# independent-verifier

## Purpose

Independent Ledger Verifier — separately-codebased CLI tool that re-verifies an Envoy Ledger export bundle under adversarial assumption. The verifier is the structural defense for `02-mvp-objectives.md` EC-4 (mutation-detection battery) and EC-9 (separately-codebased verifier authored without reference to producer source). It is the ONLY Phase 01 acceptance gate that proves the security primitive (hash chain + Ed25519 signature integrity + canonical-JSON byte-identity) without trusting the producer's source.

The verifier consumes the artifact `envoy ledger export --format json` produces (per `specs/ledger.md` § "Export + independent verifier" lines 588–592). The interface is unidirectional: producer writes a file; verifier reads the file. There is no IPC, no shared library, no shared process. Source-isolation is the load-bearing structural property — the verifier MUST NOT import any `envoy.ledger.*` symbol; it MUST re-implement canonical-JSON parsing, hash-chain walking, and Ed25519 verification independently.

## Provenance

- **Source analysis doc:** `workspaces/phase-01-mvp/01-analysis/07-independent-verifier-design.md` (full design including bundle wire format, trust-anchor protocol, mutation battery, source-isolation enforcement, cross-runtime conformance vector reuse, error taxonomy, Tier 2 / Tier 3 test surface).
- **Source spec citation gap:** `specs/ledger.md` lines 588–592 (verifier mandate as one-paragraph appendix), line 599 (`LedgerVerificationFailedError` typed error), lines 642–644 (open question on verifier language). This spec ADDS the verifier-level detail that the producer-level spec naturally elided; it does NOT modify `specs/ledger.md`.
- **Threats mitigated:** T-001 producer-side hash-chain integrity (verified by independent re-walk); T-100 rollback (head-commitment monotonicity verified); T-104 envelope-version binding (segment-boundary-aware signature verification); the EC-4 mutation battery exercises producer-side defenses by adversarial probing.
- **BETs tested:** BET-6 contract-parity via JCS (cross-language byte-identity is THE strongest form of source-isolation); BET-3 sovereignty (the user, not the Foundation, is the structural authority that the Ledger held).
- **Acceptance gates:** `02-mvp-objectives.md` EC-4 (mutation battery) + EC-9 (separately-codebased verifier) — both NON-DEGRADABLE per `02-mvp-objectives.md` § 5; failure is BLOCKING for Phase 01 release.
- **Cross-SDK:** Phase 01 ships Python reference (`envoy-ledger-verify` PyPI package); Rust sibling (`envoy-ledger-verifier` crate) is Phase 01 OPTIONAL / Phase 02 MANDATORY per `specs/ledger.md` line 643. Rust ships the strongest source-isolation form (different language).
- **Repo location:** `terrene-foundation/envoy-ledger-verifier` (separate Foundation-stewarded repo, distinct codebase, distinct license header, distinct contributor list, distinct CI). Per `rules/independence.md`, both producer and verifier ship under Apache 2.0 from the Foundation org; the boundary is a separate repo, not a separate license.

## Schema

### Bundle wire format (consumed by the verifier)

The artifact `envoy ledger export --format json` produces. Phase 01 wire shape:

```json
{
  "schema_version": "envoy-ledger-export/1.0",
  "exported_at": "<iso8601 microsecond-padded>",
  "device_id": "sha256:<hex>",
  "tenant_id": "<str | null>",
  "segment_boundaries": [
    {
      "from_sequence": 0,
      "to_sequence": <int>,
      "algorithm_identifier": {
        "sig": "ed25519", "hash": "sha256", "shamir": "slip39",
        "canonical_json": "jcs-rfc8785"
      }
    }
  ],
  "entries": [
    { /* full EntryEnvelope per specs/ledger.md lines 14-34 */ }
  ],
  "head_commitment": {
    "head_sequence": <int>,
    "head_entry_id": "sha256:...",
    "signed_at": "<iso8601 microsecond-padded>",
    "runtime_attestation": {...},
    "signature_hex": "<ed25519>"
  },
  "trust_anchor_key_set": [
    {
      "key_id": "sha256:<hex>",
      "public_key_hex": "<ed25519 pubkey>",
      "key_class": "genesis | device | runtime_device",
      "valid_from": "<iso8601>",
      "valid_until": "<iso8601 | null>",
      "attestation_chain": [...]
    }
  ],
  "receipt_hash": "sha256:<hash of canonical-JSON form of this bundle excluding receipt_hash itself>"
}
```

**Bundle invariants the verifier MUST assert:**

1. `entries[]` is non-empty AND ordered ascending by `sequence`.
2. `entries[0].type == "GenesisRecord"` for full-Ledger exports OR `entries[0].sequence > 0` with explicit `start_after_sequence` declaration for partial exports.
3. For every `entries[i]` where `i > 0`: `entries[i].parent_hash == "sha256:" + entries[i-1].entry_id` (chain integrity).
4. For every `entries[i]`: `entries[i].entry_id == "sha256:" + sha256(canonical_json(entries[i] minus entry_id+signature_hex))` (content addressing).
5. For every `entries[i]`: `Ed25519.verify(public_key_for(entries[i].signed_by, trust_anchor_key_set), canonical_json(entries[i] minus signature_hex), entries[i].signature_hex)` succeeds (signature integrity).
6. `head_commitment.head_sequence == entries[-1].sequence` AND `head_commitment.head_entry_id == entries[-1].entry_id`.
7. `Ed25519.verify(runtime_device_key from trust_anchor_key_set, canonical_json(head_commitment minus signature_hex), head_commitment.signature_hex)` succeeds.
8. `receipt_hash == "sha256:" + sha256(canonical_json(bundle minus receipt_hash))` (bundle self-integrity).
9. Segment-boundary dispatch: for each `entries[i]`, the `algorithm_identifier` used to verify (i)'s signature MUST be the segment whose `[from_sequence, to_sequence]` window contains `entries[i].sequence`.

The verifier MUST detect a violation of ANY of (1)–(9) and emit a typed error with the failing entry index.

### Trust anchor file format (out-of-band; user-supplied)

```json
{
  "schema_version": "envoy-trust-anchor/1.0",
  "principal_genesis_id": "sha256:<hex>",
  "principal_genesis_pubkey_hex": "<ed25519 pubkey>",
  "device_attestation_chain": [
    {
      "key_id": "sha256:<hex>",
      "public_key_hex": "<ed25519 pubkey>",
      "key_class": "device | runtime_device",
      "attested_by": "<key_id>",
      "attestation_signature_hex": "<ed25519>"
    }
  ],
  "anchor_minted_at": "<iso8601 microsecond-padded>"
}
```

The trust anchor file lives OUT OF BAND relative to the bundle being verified. An attacker who modifies the bundle cannot modify the trust anchor (which the user stores alongside Shamir paper shards per `specs/shamir-recovery.md`).

## Algorithms

### Trust-anchor resolution (Phase 01 minimum)

Phase 01 ships **option C** — user-supplied trust-anchor file with first-verification self-anchoring fallback. Two channels collapse to the same structural property:

1. **Self-derived from a known-good Ledger backup.** During the Boundary Conversation (per `specs/boundary-conversation.md`) at install, Envoy emits a `trust-anchor.json` file alongside the user's Shamir 3-of-5 paper-shard ritual. The user stores this file in the same out-of-band location as their paper shards. To verify a future export, the user supplies this anchor file. Trust model: "I am verifying that the Ledger I exported today was produced by the same Envoy instance I set up during my Boundary Conversation."

2. **Self-extracted from the bundle's Genesis Record at first verification.** The user runs `envoy-ledger-verify emit-trust-anchor first-export.json > trust-anchor.json` once, stores `trust-anchor.json` securely, and uses it on subsequent verifications. Trust model: "I am verifying that future Ledgers are continuous with the first Ledger I ever exported."

**Phase 01 minimum (acceptance for EC-9):** option C with channel #2 — emit-on-first-verification self-anchoring. This is the simplest user-facing model: zero ceremony at producer time, one extra command at verifier time.

**Documented residual risk:** option C does not protect against an attacker who can modify both the bundle AND the user's local trust-anchor file simultaneously. Phase 01 mitigates by recommending the trust-anchor file be stored in the same location as Shamir shards (per `specs/shamir-recovery.md`) — a paper-cold-storage location an online attacker cannot reach. Phase 02+ Foundation key registry closes this residual.

**Trust anchor key resolution algorithm:**

```
def resolve_signing_key(signed_by: str, key_class: str, anchor: TrustAnchor) -> bytes:
    # signed_by is one of "device_key" | "genesis_key" | "runtime_device_key"
    # Walk the anchor's attestation chain; raise TrustAnchorMismatchError
    # if the bundle's signed_by does not resolve to a key in this anchor.
    for entry in anchor.device_attestation_chain:
        if entry.key_class == key_class and matches(entry, signed_by):
            return entry.public_key_hex_decoded()
    if signed_by == "genesis_key":
        return anchor.principal_genesis_pubkey_decoded()
    raise TrustAnchorMismatchError(signed_by=signed_by, key_class=key_class)
```

### Mutation detection battery (the EC-4 acceptance gate)

The verifier MUST detect every mutation class enumerated in `02-mvp-objectives.md` EC-4. The battery is **5 mutation classes** that EVERY EC-4 acceptance run MUST exercise:

1. **Single-bit flip.** Any single bit in any `entries[i].content`, `entries[i].timestamp`, `entries[i].sequence`, `entries[i].parent_hash`, `entries[i].entry_id`, `entries[i].signature_hex`, or any other envelope field. Detected by: signature verification failure on entry i (canonical-JSON-then-Ed25519 step fails) OR content-addressing failure (entry_id no longer matches sha256(content)) OR chain-link failure on entry i+1 (parent_hash mismatch).

2. **Entry insertion.** A novel entry `E_new` inserted between `entries[i]` and `entries[i+1]`. The attacker cannot forge a valid Ed25519 signature without the signing key, so `E_new.signature_hex` is invalid. Even if the attacker has stolen a key, `entries[i+1].parent_hash` still references `entries[i].entry_id`, not `E_new.entry_id` — chain-link verification fails at entry i+1 OR at the new entry.

3. **Entry deletion.** `entries[i]` removed. Then `entries[i+1].parent_hash` references `entries[i].entry_id` which no longer exists — chain-link failure at the new entry i.

4. **Entry reorder.** `entries[i]` and `entries[j]` swapped. `parent_hash` references break at multiple points; sequence numbers go non-monotonic. Detected by: parent_hash mismatch + sequence non-monotonicity.

5. **Entry duplication.** `entries[i]` appears twice. The duplicate has the same `entry_id`; the verifier detects "two entries with the same entry_id" as a structural error AND sequence non-monotonicity (the duplicate's sequence is either equal to or out of order with the original's).

A 6th class is implicitly covered: **head_commitment tampering.** Modifying `head_commitment.head_sequence` or `head_commitment.head_entry_id` to lie about the chain's true head fails the head_commitment signature verification (invariant 7) — except in the case where the attacker also re-signs head_commitment with their own key. This is where the trust-anchor resolution closes the loop: the verifier knows the legitimate `runtime_device_key` from the OUT-OF-BAND trust-anchor file, NOT from the bundle's self-declaration.

Per `02-mvp-objectives.md` EC-4: ALL 5 classes MUST be detected in N=25 sub-tests (5 classes × 5 entry-index buckets — start, 25%, 50%, 75%, end) for the EC-4 acceptance gate to pass.

### Canonical JSON parsing (independent re-implementation)

The verifier's `canonical_dumps(obj: dict) -> bytes` MUST be re-implemented from scratch, NOT imported from `envoy.ledger.canonical`. The contract matches `specs/envelope-model.md` § "Canonical JSON":

- RFC 8785 JCS field ordering (lexicographic Unicode code-point on NFC-normalized keys).
- NFC normalization applied to all string values.
- ISO 8601 timestamps padded to microsecond precision (matching kailash-py PR #731 cross-SDK pinning).
- UTF-8 encoding with `separators=(",", ":")` and `ensure_ascii=False`.
- Integer microdollars (no float financial values).

The verifier's canonical-JSON output MUST be byte-identical to the producer's for the same logical input. This is the load-bearing BET-6 invariant tested at Tier 2 (`tests/integration/test_verifier_canonical_json_independent.py`) and Tier 3 (`tests/e2e/test_verifier_python_vs_rust_byte_identity.py`).

### Source-isolation enforcement (CI mechanical)

The verifier's CI MUST verify that no commit shares producer source. Three mechanical checks:

1. **Import-path check.** `pyproject.toml` MUST NOT declare a dep on `envoy-agent`, `envoy-ledger`, or any sibling Envoy package. CI grep of source for `import envoy.ledger`, `from envoy.ledger`, `use envoy_ledger`. Cargo equivalent: `cargo tree --workspace` MUST NOT include any `envoy-*` crate. Zero matches required.

2. **License-header check.** Every source file carries:

   ```
   // SPDX-License-Identifier: Apache-2.0
   // Copyright 2026 Terrene Foundation
   //
   // This file is part of envoy-ledger-verifier, an independent
   // verifier of the Envoy Ledger format. It does not share source,
   // libraries, or test fixtures with the Envoy producer codebase.
   //
   // The Envoy producer lives at github.com/terrene-foundation/envoy.
   // This codebase is structurally separated to provide independent
   // verification per Phase 01 EC-9.
   ```

   A CI pre-commit hook checks the header is present on every source file.

3. **Producer-fixture provenance check.** The mutation-battery test fixtures (`tests/fixtures/clean_bundle_*.json`) are produced by the producer once and committed to the verifier repo as static artifacts — NOT pulled at CI time from a producer image, NOT generated on the verifier CI runner. Each fixture's provenance is documented in a per-fixture comment block.

### Cross-runtime conformance vector reuse

The conformance contract in `workspaces/phase-00-alignment/02-plans/conformance/01-runtime-swap-contract.md` § 4.2 row E7 (Ledger head-commitment monotonicity, ≥10 byte-identical conformance vectors) defines the cross-runtime spec method. The verifier's mutation-battery test fixtures `tests/fixtures/conformance/e7/` SHOULD include the E7 conformance vectors verbatim (Phase 02: git submodule pin or versioned-fixture-package dep TBD). When the cross-runtime gate ships in Phase 02, the same vectors that prove `kailash-py` == `kailash-rs-bindings` ALSO prove `envoy-producer` == `envoy-verifier`. This is the same byte-identity invariant tested through two different lenses.

## Error taxonomy

Per `rules/zero-tolerance.md` Rule 6 — implement fully; every typed error MUST be reachable from a real code path.

| Error                           | Trigger                                                                                                                                            | User action                                                                                    | Retry                  |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ---------------------- |
| `BundleParseError`              | Bundle JSON is structurally malformed (not parseable, missing required top-level field)                                                            | Re-export the bundle from producer; if reproducible, file producer-side issue                  | Manual after re-export |
| `UnsupportedExportFormatError`  | Bundle declares a `schema_version` the verifier does not recognize OR is a multi-device merged bundle (Phase 01 single-device only)                | Use the verifier version matching the bundle's schema_version; multi-device verification = P03 | Manual                 |
| `TrustAnchorParseError`         | Trust anchor file is malformed (bad schema_version, missing required field)                                                                        | Re-emit trust-anchor file via `envoy-ledger-verify emit-trust-anchor`                          | Manual after re-emit   |
| `TrustAnchorMismatchError`      | Bundle's `signed_by` does not resolve to any key in the trust anchor's attestation chain (potential key-substitution attack)                       | Verify the trust anchor file is the legitimate one; if so, refuse the bundle as tampered       | Never (fail-closed)    |
| `ChainBreakError`               | `entries[i].parent_hash != "sha256:" + entries[i-1].entry_id` for some i > 0 (chain integrity broken)                                              | Refuse bundle; surface failing entry index; investigate producer-side                          | Never (structural)     |
| `EntryIdContentMismatchError`   | `entries[i].entry_id != "sha256:" + sha256(canonical_json(entries[i] minus entry_id+signature_hex))` (content-addressing broken)                   | Refuse bundle; surface failing entry index                                                     | Never (structural)     |
| `SignatureVerificationError`    | Ed25519 signature verification fails for some entry's `signature_hex` against the resolved public key                                              | Refuse bundle; surface failing entry index AND key_class used                                  | Never (structural)     |
| `SequenceNonMonotonicError`     | `entries[i].sequence <= entries[i-1].sequence` for some i > 0 (sequence ordering broken — also fires on duplicate-entry mutation)                  | Refuse bundle; surface the two conflicting indices                                             | Never (structural)     |
| `OrderingError`                 | `entries[]` is not sorted ascending by `sequence` at top level (reorder-class mutation)                                                            | Refuse bundle; surface the disordered indices                                                  | Never (structural)     |
| `BundleSelfIntegrityError`      | `receipt_hash` does not equal `sha256(canonical_json(bundle minus receipt_hash))` (bundle metadata tampered)                                       | Refuse bundle; bundle envelope itself is corrupted                                             | Never (structural)     |
| `HeadCommitmentMismatchError`   | `head_commitment.head_sequence != entries[-1].sequence` OR `head_commitment.head_entry_id != entries[-1].entry_id`                                 | Refuse bundle; producer-side rollback or tampering                                             | Never (structural)     |
| `SegmentBoundaryError`          | An entry's `algorithm_identifier` does not match the segment whose `[from_sequence, to_sequence]` window contains its `sequence`                   | Refuse bundle; producer-side migration boundary corrupted                                      | Never (structural)     |
| `LedgerVerificationFailedError` | Umbrella error wrapping any of the above when surfaced via the producer-side `specs/ledger.md` line 599 contract — preserved for cross-spec compat | Inspect `cause` for the specific structural error; surface failing entry index                 | Never                  |

`LedgerVerificationFailedError` is the wire-contract typed name shared with `specs/ledger.md` line 599 (the producer-side error class). The verifier-internal taxonomy above is finer-grained; the umbrella class is what callers external to the verifier (e.g. shell scripts checking exit codes via stderr substring match) MUST be able to grep.

## Test location

Per `rules/testing.md` § 3-Tier Testing + § Audit Mode Rules. Per `rules/orphan-detection.md` Rule 1, the `Verifier` facade MUST be on the production hot path (the CLI's `main()`); Tier 2 tests import through the facade.

### Tier 2 wiring tests (verifier repo)

- `tests/integration/test_verifier_wiring.py` — facade-on-hot-path test per `rules/facade-manager-detection.md` Rule 2 naming convention.
- `tests/integration/test_verifier_trust_anchor_resolution.py` — TrustAnchorMismatchError raised when bundle's signed_by is not in anchor.
- `tests/integration/test_verifier_canonical_json_independent.py` — verifier's canonical_dumps is INDEPENDENTLY correct (re-implemented from spec, not imported).
- `tests/integration/test_verifier_emit_trust_anchor.py` — first-export self-anchoring round-trip success.
- `tests/integration/test_verifier_unsupported_format_error.py` — multi-device merged bundle raises UnsupportedExportFormatError (Phase 03 deferral structural defense).

### Tier 3 tests (cross-OS CI matrix; EC-4 + EC-9 acceptance gates)

- `tests/e2e/test_verifier_real_producer_clean_path.py` — spawn real producer via `pipx install envoy-agent`; produce 1000-entry Ledger; verify; assert PASS.
- `tests/e2e/test_verifier_mutation_battery.py` — **THE EC-4 ACCEPTANCE GATE.** 5 mutation classes × 5 entry-index buckets = 25 sub-tests; ALL MUST detect tampering AND identify the failing entry index.
- `tests/e2e/test_verifier_cross_os_byte_identity.py` — macOS + Linux + Windows; outputs MUST be byte-identical.
- `tests/e2e/test_verifier_python_vs_rust_byte_identity.py` — (if Rust ships in Phase 01) Python verifier and Rust verifier produce byte-identical output. **THIS is the strongest EC-9 source-isolation proof.**
- `tests/e2e/test_verifier_independent_codebase_assertion.py` — CI-only mechanical grep; zero matches for `import envoy.ledger` / `from envoy.ledger` / `use envoy_ledger` / path deps on producer packages.
- `tests/e2e/test_verifier_e7_conformance_vector_passes.py` — verifier passes the E7 conformance corpus (≥10 vectors per `01-runtime-swap-contract.md` § 4.2).
- `tests/e2e/test_verifier_pdf_receipt_hash_links_json.py` — (if Phase 01 ships PDF export per `specs/ledger.md` line 591) PDF's receipt_hash equals SHA-256 of JSON bundle, extracted via non-Envoy PDF library.

### CI matrix (cross-OS)

- macOS: `macos-14` (latest stable + LTS).
- Linux: `ubuntu-22.04` + `ubuntu-24.04`.
- Windows: `windows-2022`.

The cross-OS test catches Unicode normalization drift (NFC behaves differently on macOS HFS+ vs Linux ext4 vs Windows NTFS at the filesystem level), timestamp formatting drift, and locale-dependent string handling.

## Cross-references

- **specs/ledger.md** — § "Export + independent verifier" lines 588–592 (verifier mandate); § "Error taxonomy" line 599 (`LedgerVerificationFailedError`); § "Open questions" lines 642–644 (verifier language).
- **specs/ledger-merge.md** — multi-device merge protocol (Phase 03); verifier rejects merged bundles with UnsupportedExportFormatError.
- **specs/envelope-model.md** — § "Canonical JSON" defines the JCS-RFC8785 + NFC contract the verifier independently re-implements.
- **specs/shamir-recovery.md** — out-of-band trust-anchor file storage co-located with paper Shamir shards.
- **specs/boundary-conversation.md** — first-install ritual emits trust-anchor.json alongside the Shamir ceremony.
- **specs/distribution.md** — verifier ships as separate `pip install envoy-ledger-verify` package; producer ships via `pipx install envoy-agent`; Phase 02 Rust crate via `cargo install envoy-ledger-verifier`.
- **specs/runtime-abstraction.md** — N1–N6 + E1–E7 conformance vectors; E7 row owns the Ledger head-commitment monotonicity vectors the verifier reuses verbatim.
- **specs/threat-model.md** — T-001 (hash-chain integrity), T-100 (rollback), T-104 (envelope-version binding) — all defended by the verifier's mutation battery.
- **workspaces/phase-01-mvp/01-analysis/07-independent-verifier-design.md** — the full Phase 01 implementation deep-dive (consumed by `/implement` for shard 7).
- **workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md** — EC-4 (mutation battery) + EC-9 (separately-codebased verifier) acceptance gates.
- **workspaces/phase-01-mvp/01-analysis/06-envoy-ledger-implementation.md** — the producer-side Ledger implementation deep-dive (the verifier's input).
- **workspaces/phase-00-alignment/02-plans/conformance/01-runtime-swap-contract.md** — § 4.2 row E7 cross-runtime conformance vectors reused by the verifier.
- **specs/mvp-build-sequence.md** — the verifier ships in a parallel side-channel track (separate repo) per Phase 01 build order; gates Phase 01 release.

## Open questions

1. **Foundation key registry (Phase 02+).** Phase 02 may extend trust-anchor resolution with a Foundation-published registry at `terrene.foundation/registry/<principal_id>.json`. The verifier accepts `--trust-anchor https://terrene.foundation/registry/...` and validates the registry's response is signed by a known Foundation steward key. Phase 01 ships option C (file-based) only.
2. **Signed CA cert in bundle (Phase 04+).** Out of scope for Phase 01 because the Foundation does not issue certificates as a Phase 01 deliverable; this is Phase 04+ infrastructure.
3. **Rust variant Phase 01 vs Phase 02 disposition.** `specs/ledger.md` line 643 names Python as the community default; Rust as Phase 04. Phase 01 ships Python REQUIRED; Rust OPTIONAL but RECOMMENDED for the strongest cross-language source-isolation proof. Phase 02 makes Rust MANDATORY.
4. **E7 conformance vector versioning.** TBD — git submodule pin OR versioned-fixture-package dep. Phase 02 entry decides; Phase 01 commits the vectors verbatim.
5. **Cross-channel bundle delivery (Phase 02+).** A natural extension: channel adapters support `envoy ledger export-via-channel slack`. Phase 01 uses out-of-band file transfer only; Phase 02 may extend.
6. **PDF export receipt_hash parser library.** Phase 01 picks one (`pypdf` recommended); the test exercises a non-Envoy library to preserve source-isolation.
