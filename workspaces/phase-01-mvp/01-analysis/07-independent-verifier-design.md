# 07 — Independent Ledger Verifier design

**Document role:** Implementation deep-dive for the Phase 01 Independent Ledger Verifier — the separately-codebased CLI tool that consumes an Envoy Ledger export bundle and independently re-verifies the hash chain, every Ed25519 signature, and the absence of tampering. This is the EC-4 + EC-9 acceptance gate; the strongest Phase 01 acceptance gate, the only one that proves the security primitive (hash chain) works under adversarial assumption rather than developer assumption.

**Date:** 2026-05-03 (shard 7 of /analyze).
**Status:** DRAFT — load-bearing for Phase 01 release predicate per `02-mvp-objectives.md` § 4 (EC-4 ∧ EC-9 are non-degradable; failure is BLOCKING). Surfaces ONE additive-spec recommendation for shard 22.

**Capacity check:** one primitive (the verifier), one source spec by reference (`specs/ledger.md` § Export + independent verifier lines 588–592), 6 invariants tracked (chain shape stability; canonical-JSON byte determinism; signature verification; trust-anchor key resolution; mutation detection across 5 classes; source-isolation enforcement), ≤3 cross-shard references (shard 6 producer; shard 16 channel adapters as bundle-delivery surface; shard 19 pipx distribution metadata cross-link). Within `rules/autonomous-execution.md` budget.

**Phase 00 framing reminder:** This shard does NOT re-derive `specs/ledger.md`. Per `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`, the spec is frozen — the question is "given this contract is frozen, how do we deliver an independent verifier whose existence proves the contract held?" not "is this contract right?" The verifier's design IS Phase 01-new work because the verifier is itself a Phase 01 deliverable per EC-9; the Ledger producer is shard 6's domain.

---

## 1. Source spec citation + the gap

### 1.1 What `specs/ledger.md` says about the verifier

`specs/ledger.md` § "Export + independent verifier" lines 588–592 (frozen, DO NOT EDIT) fixes the verifier-relevant contract surface:

- `envoy ledger export --format json` produces a signed export bundle (line 590)
- PDF form carries `receipt_hash` pointing to JSON (line 591)
- "Independent reference-verifier (`envoy-ledger-verify`) separate Python package; Phase 01 exit gate per doc 00 v3" (line 592)

`specs/ledger.md` § "Open questions" line 643 adds: "Verifier language — Python community default; Rust variant Phase 04." The spec is permissive on language; it pins Python as the Phase 01 default with a Phase 04 Rust variant. Per `02-mvp-objectives.md` EC-9 acceptance gate, both are accepted, with Rust **preferred** per `rules/testing.md` Tier 3 cross-implementation logic of cross-language verification.

`specs/ledger.md` § "Error taxonomy" line 599: `LedgerVerificationFailedError` is the typed error the verifier raises on chain failure. The verifier shares this error CLASS (the typed name) with the producer per `rules/orphan-detection.md` Rule 1, but does NOT share the error class IMPLEMENTATION — the typed name is part of the wire contract that crosses the source-isolation boundary; the implementation is independent.

Cross-references in `specs/ledger.md` § "Test location" line 621: `tests/integration/test_hash_chain_verifier_python.py — envoy-ledger-verify independent verifier Phase 01 exit gate`. The producer-side Tier 2 test references the verifier as the verification authority — the verifier is the artifact the producer's test invokes externally.

### 1.2 What `specs/ledger-merge.md` says

`specs/ledger-merge.md` is the multi-device CRDT merge spec. Per shard 6 § 1.2, multi-device merge is **architectural-contract-only** in Phase 01 — the verifier's MVP scope therefore EXCLUDES merge-replay verification. The verifier consumes single-device export bundles; multi-device divergence is Phase 03 wiring. This shard records the deferral explicitly so shard 23/24 redteam knows the deferral is intentional, not orphaned.

The merge-replay determinism error (`MergeReplayDivergenceError` per `specs/ledger-merge.md` line 68) is Phase 03 verifier scope; Phase 01 verifier MUST surface a typed `UnsupportedExportFormatError` if presented with a merged-bundle export to make the deferral explicit rather than silent.

### 1.3 The gap — no `specs/independent-verifier.md` exists

The frozen specs treat the verifier as a thin appendix to `specs/ledger.md` (one paragraph at lines 588–592). What is NOT in the specs:

- **Public-key trust-anchor resolution protocol.** How does the verifier KNOW the legitimate signing public key? `specs/ledger.md` line 29 names `signed_by` (`device_key | genesis_key`) but the verifier cannot trust the bundle's own self-declaration of its key — that's circular. This is the structural gap.
- **Export bundle wire format.** What concrete JSON shape does `envoy ledger export --format json` emit? `specs/ledger.md` line 590 says "signed export bundle" — the format is implementation latitude per shard 6 § 3.2 item 6.
- **Mutation battery.** What tampering forms MUST the verifier detect (single-bit flip, insertion, deletion, reorder, duplication)? `02-mvp-objectives.md` EC-4 enumerates these but no spec does.
- **Source-isolation enforcement.** What CI mechanism prevents the verifier from accidentally depending on producer source? Implementation latitude.
- **Cross-runtime conformance vector reuse.** Per `workspaces/phase-00-alignment/02-plans/conformance/01-runtime-swap-contract.md` § 4.2 row E7 (Ledger head-commitment monotonicity, ≥10 vectors), the same vectors that exercise cross-runtime conformance should also exercise the verifier. This shard names the linkage; it does not duplicate the corpus.

**Disposition:** This shard recommends drafting `specs/independent-verifier.md` as additive at shard 22 (per the inheritance map § 5.4 and the brief). Per `rules/specs-authority.md` MUST Rule 5b, NEW spec files do NOT trigger 37-sibling re-derivation — additive only. The draft captures all five gaps above.

---

## 2. Verified provider state — n/a (Envoy-new by design)

This row of the readiness map (`03-kailash-py-mvp-readiness.md` § 3 row 4) is explicit: **n/a; verifier is Phase 01 deliverable in different repo, separately-codebased even within Envoy ecosystem.** No `kailash-py` symbol is consumable here without violating the source-isolation contract — by design.

The single LEGITIMATE upstream-consumable surface is the export bundle's wire format, which the verifier reads as a black-box parser. Even there, the verifier MUST NOT import `envoy.ledger.canonical.canonical_dumps` (or any helper from shard 6); it MUST re-implement canonical-JSON parsing from the spec. The bytes are the contract; the implementation is independent.

This is the structural defense against the failure mode where producer and verifier silently agree because they share a serialization library. If both call the same `canonical_dumps`, a bug in that library produces hashes both treat as correct — verification succeeds while reality is broken. Independent re-implementation is the only way the verifier proves the bytes ARE the contract.

---

## 3. Envoy-new-code surface

### 3.1 Repo location recommendation

**Recommendation: `terrene-foundation/envoy-ledger-verifier`** (separate GitHub repository under the Foundation org, distinct codebase, distinct license header, distinct contributor list, distinct commit history).

**Rationale:**

1. **Foundation-stewarded boundary.** The Ledger producer (Envoy) ships under `terrene-foundation/envoy` (Apache 2.0 per `rules/independence.md` Foundation-track framing). The verifier benefits from Foundation stewardship for the same reason the producer does — both are open standards implementations (CC BY 4.0 specs in `specs/ledger.md`, Apache 2.0 implementations). Hosting the verifier in the same org under a separate repo signals "same authority, independent codebase" — exactly the structural promise EC-9 requires.

2. **Source-isolation by repo boundary.** A separate repo is the most mechanical form of source-isolation: GitHub's repo structure is the enforcement surface. The verifier's `Cargo.toml` / `pyproject.toml` cannot accidentally `path-dep` on Envoy; cross-repo deps must be declared explicitly via crates.io / PyPI version pin, which is auditable and reviewable.

3. **Independent versioning.** The verifier ships its own SemVer; a producer release does NOT force a verifier release. This avoids the coupling failure mode where a non-functional change in the producer (a docstring, a refactor) requires a verifier re-release just to maintain version parity.

4. **Independent CI.** A separate repo gets its own CI pipeline. The verifier's CI runs the mutation battery against producer-generated fixtures (committed in the verifier repo, not pulled at CI time from the producer) without any producer code on the runner.

5. **Contributor isolation.** Future contributors to the verifier are separate from contributors to Envoy. Per `02-mvp-objectives.md` EC-9 acceptance gate: "implemented without reference to Envoy producer source, in either Python (different agent / different package) or Rust (different language entirely)." A separate repo enforces this organizationally — a contributor cannot meaningfully claim "without reference to producer source" while a single-repo PR sits adjacent to the producer.

**Alternative considered and rejected:** monorepo at `terrene-foundation/envoy/verifier/` as a sibling subdirectory. Rejected because (a) shared `pyproject.toml` workspace makes accidental imports trivial, (b) shared CI runs producer code on the verifier matrix, (c) contributor reviewers naturally cross-reference adjacent files. The boundary becomes social, not structural.

**Alternative considered and rejected:** third-party repo (`esperie/envoy-ledger-verifier`). Rejected per `rules/independence.md` Foundation independence — the Foundation owns the Ledger spec; a non-Foundation verifier creates ambiguous endorsement claims. The verifier MUST be hostable by anyone, but the **reference verifier** (shipped as the Phase 01 EC-9 deliverable) is Foundation-stewarded.

### 3.2 Implementation language recommendation

**Recommendation: Rust** (with Python `envoy-ledger-verify` reference variant landing first as the Phase 01 acceptance gate; Rust ships as second variant by Phase 01 release per `specs/ledger.md` open question line 643).

**Rationale per `rules/testing.md` Tier 3 cross-implementation discipline:**

1. **Different language is the strongest source-isolation form.** Python verifier vs Python producer share runtime, packaging conventions, idioms. A Rust verifier shares zero of these — the only thing it shares with the producer is the wire format. If both produce the same hash for a given canonical-JSON envelope, the wire format IS the contract; the implementations cannot collude on a shared bug.

2. **Cross-language byte-identity stress.** Rust's `serde_json` + `chrono` (or `time`) crate produces a different code path for canonical-JSON serialization than Python's `json.dumps + unicodedata.normalize`. If both produce byte-identical output for the same input, the Unicode pinning in #757/#756 + microsecond-padding in #731 (cross-references shard 6 § 2.2) is structurally proven, not assumed.

3. **Future-state alignment with cross-runtime conformance.** Per the conformance contract in `workspaces/phase-00-alignment/02-plans/conformance/01-runtime-swap-contract.md` § 4.2 row E7 + § 7.2, the kailash-rs-bindings runtime is the Phase 02 deliverable; a Rust verifier shares Cargo + crate ecosystem with that runtime, naturally exercising the same byte-identity invariants. The verifier becomes a downstream consumer of the same conformance corpus the cross-runtime gate uses.

4. **Distribution model.** Rust verifier ships as a single statically-linked binary via `cargo install envoy-ledger-verifier` OR via release-page binary download. No Python interpreter dependency — a user with a 10-year-old Python install can still verify their own Ledger. This matches the sovereignty narrative (BET-3) — the verifier survives even if Python tooling drifts.

**Why Python ships first as Phase 01 reference:**

1. **`specs/ledger.md` line 644 names Python as community default.** Phase 01 honors the spec's explicit guidance.
2. **Reference implementation.** A Python verifier is the easier target to read, audit, and re-implement. A second-party who wants to write a third verifier reads the Python first.
3. **Faster Phase 01 ship.** A Python verifier can plausibly land in 1–2 sessions; Rust is 2–3 sessions due to crate selection + canonical-form re-implementation.
4. **EC-9 gate accepts EITHER language.** Per `02-mvp-objectives.md` EC-9 acceptance gate: Python (different agent / different package) is acceptable. The acceptance gate does NOT require Rust.

**Phase 01 ship disposition:**

- **REQUIRED for EC-9 acceptance:** `envoy-ledger-verify` Python package, separate repo (`terrene-foundation/envoy-ledger-verifier`), authored by a different agent than the producer (per EC-9: "by a different agent without reference to producer source").
- **OPTIONAL but RECOMMENDED for Phase 01 release:** Rust variant `envoy-ledger-verify-rs`, in the same repo as a sibling crate. Provides the cross-language source-isolation proof and aligns with `rules/testing.md` Tier 3 cross-implementation invariant.

### 3.3 Export bundle wire format (consumed by the verifier)

The verifier consumes the artifact `envoy ledger export --format json` produces. Per shard 6 § 3.2 item 6 + `specs/ledger.md` line 590 (signed export bundle), the wire format is implementation latitude — but the verifier CANNOT consume a format the producer hasn't pinned. This shard names the format contract the verifier expects; shard 22 formalizes it in `specs/independent-verifier.md`.

**Bundle wire format (proposed for shard 22 spec draft):**

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
      "algorithm_identifier": {...}
    }
  ],
  "entries": [
    { /* full EntryEnvelope per specs/ledger.md lines 14-34 */ },
    ...
  ],
  "head_commitment": {
    "head_sequence": <int>,
    "head_entry_id": "sha256:...",
    "signed_at": "<iso8601>",
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

**Key invariants the verifier asserts on this bundle:**

1. `entries[]` is non-empty AND ordered ascending by `sequence`.
2. `entries[0].type == "GenesisRecord"` for full-Ledger exports OR `entries[0].sequence > 0` with explicit `start_after_sequence` declaration for partial exports.
3. For every `entries[i]` where `i > 0`: `entries[i].parent_hash == "sha256:" + entries[i-1].entry_id` (chain integrity).
4. For every `entries[i]`: `entries[i].entry_id == "sha256:" + sha256(canonical_json(entries[i] minus entry_id+signature_hex))` (content addressing).
5. For every `entries[i]`: `Ed25519.verify(public_key_for(entries[i].signed_by, trust_anchor_key_set), canonical_json(entries[i] minus signature_hex), entries[i].signature_hex)` succeeds (signature integrity).
6. `head_commitment.head_sequence == entries[-1].sequence` AND `head_commitment.head_entry_id == entries[-1].entry_id`.
7. `Ed25519.verify(runtime_device_key from trust_anchor_key_set, canonical_json(head_commitment minus signature_hex), head_commitment.signature_hex)` succeeds.
8. `receipt_hash == "sha256:" + sha256(canonical_json(bundle minus receipt_hash))` (bundle self-integrity).

The verifier MUST detect a violation of ANY of (1)–(8) and emit a typed error with the failing entry index.

### 3.4 Public-key trust-anchor resolution (the critical Phase 01 design decision)

The trust-anchor problem is: how does the verifier KNOW the `entries[*].signed_by` keys are legitimate?

The bundle includes `trust_anchor_key_set[]`, but trusting the bundle to declare its own keys is circular — a tampering attacker who can modify entries can also modify the key set. The verifier MUST resolve the trust anchor independently.

**Phase 01 disposition: user-supplied trust-anchor file (option C).**

The verifier accepts a `--trust-anchor` flag pointing to a file the user supplies out-of-band. The file format is:

```json
{
  "schema_version": "envoy-trust-anchor/1.0",
  "principal_genesis_id": "sha256:<hex>",
  "principal_genesis_pubkey_hex": "<ed25519 pubkey>",
  "device_attestation_chain": [...],
  "anchor_minted_at": "<iso8601>"
}
```

The user obtains this file from one of two channels (Phase 01 minimum):

1. **Self-derived from a known-good Ledger backup.** During the Boundary Conversation (per shard 8) at install, Envoy emits a `trust-anchor.json` file alongside the user's Shamir 3-of-5 paper-shard ritual (shard 15). The user stores this file in the same out-of-band location as their paper shards. To verify a future export, the user supplies this anchor file. The trust model is: "I am verifying that the Ledger I exported today was produced by the same Envoy instance I set up during my Boundary Conversation."
2. **Self-extracted from the bundle's Genesis Record at first verification.** The user runs `envoy-ledger-verify --emit-trust-anchor first-export.json > trust-anchor.json` once, stores `trust-anchor.json` securely, and uses it on subsequent verifications. The trust model is: "I am verifying that future Ledgers are continuous with the first Ledger I ever exported."

Both channels collapse to the same structural property: the trust anchor is **out-of-band relative to the bundle being verified**. An attacker who modifies the bundle cannot modify the trust anchor (which lives on the user's machine, in the user's vault, alongside their Shamir shards).

**Phase 01 minimum (acceptance for EC-9):** option C with channel #2 — emit-on-first-verification self-anchoring. This is the simplest user-facing model: zero ceremony at producer time, one extra command at verifier time.

**Phase 02 extension (deferred):** option (a) static-published Foundation key registry. The Foundation publishes a registry of known principal-Genesis-public-keys at `terrene.foundation/registry/<principal_id>.json` (out of scope for Phase 01 because it requires Foundation registry infrastructure). The verifier accepts `--trust-anchor https://terrene.foundation/registry/...`. This is the Phase 02+ direction; Phase 01 ships option C only.

**Phase 02 extension (deferred):** option (b) export bundle includes a signed certificate from a known authority (CA-style chain). Rejected for Phase 01 because the Foundation does not issue certificates as a Phase 01 deliverable; this is Phase 04+ infrastructure.

**Why option C is acceptable for Phase 01:** the Phase 01 user is operating in single-principal, single-device mode (per `02-mvp-objectives.md` EC-7 + EC-8 scope). The trust model "the Ledger I'm verifying continues from the first Ledger I exported" is exactly the user's mental model — they want to detect tampering by an attacker who got hold of the bundle, NOT to verify identity claims about who produced the bundle. Option C's out-of-band anchor file solves the former without committing to Foundation registry infrastructure that does not exist yet.

**Documented residual risk:** option C does not protect against an attacker who can modify both the bundle AND the user's local trust-anchor file simultaneously. Phase 01 mitigates by recommending the trust-anchor file be stored in the same location as Shamir shards (per shard 15) — a paper-cold-storage location an online attacker cannot reach. Phase 02+ Foundation registry closes this residual.

### 3.5 Mutation battery (the EC-4 acceptance gate)

The verifier MUST detect every mutation class in the EC-4 acceptance gate. Per `02-mvp-objectives.md` EC-4: "single-bit flip in any payload field; insertion / deletion / reorder of any entry."

The mutation battery enumerates 5 classes; each MUST be detectable by the verifier:

1. **Single-bit flip.** Any single bit in any `entries[i].content`, `entries[i].timestamp`, `entries[i].sequence`, `entries[i].parent_hash`, `entries[i].entry_id`, `entries[i].signature_hex`, or any other envelope field. Detected by: signature verification failure on entry i (because the canonical-JSON-then-Ed25519 step fails) OR content-addressing failure on entry i (entry_id no longer matches sha256(content)) OR chain-link failure on entry i+1 (parent_hash mismatch).
2. **Entry insertion.** A novel entry `E_new` inserted between `entries[i]` and `entries[i+1]`. The attacker cannot forge a valid Ed25519 signature without the signing key, so `E_new.signature_hex` will be invalid. Even if the attacker has stolen a key, `entries[i+1].parent_hash` still references `entries[i].entry_id`, not `E_new.entry_id` — chain-link verification fails at entry i+1 OR at the new entry. To "successfully" insert, the attacker must also modify `entries[i+1].parent_hash`, which fails (i+1)'s signature verification.
3. **Entry deletion.** `entries[i]` removed. Then `entries[i+1].parent_hash` references `entries[i].entry_id` which no longer exists in the bundle — but the verifier walks the chain by index AND re-checks parent_hash, so it observes "entries[i+1].parent_hash points to an entry_id not equal to entries[i].entry_id" (where entries[i] is now what was originally entries[i+1] before deletion). Chain-link failure at the new entry i.
4. **Entry reorder.** `entries[i]` and `entries[j]` swapped. `parent_hash` references break at multiple points; sequence numbers go non-monotonic. Detected by: parent_hash mismatch + sequence non-monotonicity.
5. **Entry duplication.** `entries[i]` appears twice. The duplicate has the same `entry_id`; the verifier detects "two entries with the same entry_id" as a structural error (entry_id collision is content-addressing-impossible without identical content) AND sequence non-monotonicity (the duplicate's sequence is either equal to or out of order with the original's).

A 6th class is implicitly covered: **head_commitment tampering.** Modifying `head_commitment.head_sequence` or `head_commitment.head_entry_id` to lie about the chain's true head fails the head_commitment signature verification (invariant 7 in § 3.3) — except in the case where the attacker also re-signs head_commitment with their own key. This is where the trust-anchor resolution of § 3.4 closes the loop: the verifier knows the legitimate runtime_device_key from the out-of-band trust-anchor file, NOT from the bundle's self-declaration, so a re-signed head_commitment with an attacker key is rejected because the public key isn't in the trust-anchor key set.

**Mutation-battery test (Tier 3, runs against real producer + real verifier):**

```python
# tests/e2e/test_envoy_ledger_tampering_battery.py (in producer repo, exercises verifier)
@pytest.mark.parametrize("mutation_class", ["bit_flip", "insert", "delete", "reorder", "duplicate"])
def test_verifier_detects_tampering(envoy_producer, verifier_binary, mutation_class):
    # 1. Produce a 1000-entry Ledger via real producer
    bundle_path = envoy_producer.export_ledger_with_n_entries(1000)
    trust_anchor_path = envoy_producer.emit_trust_anchor()

    # 2. Verify clean bundle passes
    result = subprocess.run([verifier_binary, "verify", bundle_path,
                             "--trust-anchor", trust_anchor_path],
                            capture_output=True)
    assert result.returncode == 0

    # 3. Apply mutation at entry index 500
    mutated_path = apply_mutation(bundle_path, mutation_class, entry_index=500)

    # 4. Verifier MUST detect and exit non-zero with typed error
    result = subprocess.run([verifier_binary, "verify", mutated_path,
                             "--trust-anchor", trust_anchor_path],
                            capture_output=True)
    assert result.returncode != 0
    assert b"LedgerVerificationFailedError" in result.stderr
    assert b"entry_index=500" in result.stderr  # exact failing index reported
```

Per `rules/orphan-detection.md` § 2a crypto-pair round-trip MUST be tested through the facade: this Tier 3 test exercises producer.export() → verifier.verify() → mutation detection as a single round-trip, satisfying the structural defense against "producer signs with GCM, verifier validates with CBC drift" failure mode adapted to "producer canonical-form drifts from verifier canonical-form parsing."

### 3.6 Source-isolation enforcement

The verifier's CI MUST verify that no commit in the verifier's git history shares producer source. Two mechanical checks:

1. **Import-path check.** The verifier's `pyproject.toml` MUST NOT declare a dep on `envoy-agent`, `envoy-ledger`, or any sibling Envoy package. The CI runs `pip-audit --strict` against the lockfile and asserts the dep tree has no Envoy producer package. For Rust: `cargo tree --workspace` MUST NOT include any `envoy-*` crate. A grep of the source for `import envoy.ledger`, `from envoy.ledger`, `use envoy_ledger` is part of CI.

2. **License-header check.** Every source file in the verifier repo carries a header declaring its independence:

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

   A CI pre-commit hook checks the header is present on every source file. Drift from the header (someone removes it) is a CI failure.

3. **Producer-fixture provenance check.** The mutation-battery test fixtures (`tests/fixtures/clean_bundle_*.json`) are produced by the producer and committed to the verifier repo as static artifacts — NOT pulled at CI time from a producer image, NOT generated on the verifier CI runner. This ensures CI does not run any producer code. The fixture's provenance is documented in a per-fixture comment block.

### 3.7 Cross-runtime conformance vector reuse

The conformance contract in `workspaces/phase-00-alignment/02-plans/conformance/01-runtime-swap-contract.md` § 4.2 row E7 (Ledger head-commitment monotonicity) defines ≥10 byte-identical conformance vectors that exercise `head_commitment` and `ledger_append`. These vectors are minted at Phase 01 cadence per § 4.2 row E7 ("TBD ≥10 ... filled at Phase-01 mint cadence").

**Reuse linkage:** the verifier's mutation-battery test fixtures SHOULD include the E7 conformance vectors verbatim. When the cross-runtime gate ships in Phase 02 (per § 10 of the conformance contract), the same vectors that prove kailash-py == kailash-rs-bindings ALSO prove envoy-producer == envoy-verifier. This is the same byte-identity invariant tested through two different lenses.

**Phase 01 disposition:** the verifier repo's `tests/fixtures/conformance/e7/` is a verbatim subdirectory of the Phase 01 conformance corpus. Updates to E7 vectors at Phase 02 propagate to the verifier via a git submodule pin OR a versioned-fixture-package dep (TBD; shard 22 spec draft to formalize).

---

## 4. Class structure sketch (interfaces only — no implementation)

```python
# envoy_ledger_verifier/__init__.py
from envoy_ledger_verifier.facade import Verifier, VerificationResult
from envoy_ledger_verifier.trust_anchor import TrustAnchor, TrustAnchorError
from envoy_ledger_verifier.mutation_battery import MutationBattery, MutationClass
from envoy_ledger_verifier.errors import (
    LedgerVerificationFailedError,
    UnsupportedExportFormatError,
    TrustAnchorMismatchError,
    BundleSelfIntegrityError,
    SignatureVerificationError,
    ChainLinkBrokenError,
    SequenceNonMonotonicError,
    EntryIdContentMismatchError,
)

# envoy_ledger_verifier/facade.py
class Verifier:
    def __init__(self, *, trust_anchor: TrustAnchor) -> None: ...
        # Constructed with an out-of-band-resolved TrustAnchor.
        # No producer dependency; trust_anchor is supplied by the caller.

    def verify_bundle(self, bundle_path: str) -> VerificationResult: ...
        # Walks the chain end-to-end; returns VerificationResult with per-entry
        # verdict + first-failing-index + failure class. Does NOT raise on
        # tampering; tampering is a returned VerificationResult, not an exception.
        # Raises only on structurally-malformed bundles (cannot parse).

    def emit_trust_anchor(self, bundle_path: str) -> TrustAnchor: ...
        # First-export self-anchoring path (§ 3.4 channel #2).
        # Reads the bundle's GenesisRecord; emits a TrustAnchor file the user
        # stores out-of-band for subsequent verifications.

@dataclass(frozen=True)
class VerificationResult:
    verdict: Literal["PASS", "FAIL"]
    failing_entry_index: Optional[int]
    failure_class: Optional[str]   # one of the typed error class names
    failure_detail: Optional[str]  # human-readable; not a stack trace
    entries_verified: int
    chain_head_sequence: int

# envoy_ledger_verifier/trust_anchor.py
@dataclass(frozen=True)
class TrustAnchor:
    schema_version: str   # "envoy-trust-anchor/1.0"
    principal_genesis_id: str
    principal_genesis_pubkey_hex: str
    device_attestation_chain: list[dict]
    anchor_minted_at: str

    @classmethod
    def from_file(cls, path: str) -> "TrustAnchor": ...
        # Parses the trust-anchor file; validates schema_version.
        # Raises TrustAnchorError on malformed file.

    @classmethod
    def from_genesis_record(cls, genesis_entry: dict) -> "TrustAnchor": ...
        # First-export self-anchoring; user is asserting the Genesis they see
        # IS their genuine Genesis.

    def resolve_signing_key(self, signed_by: str, key_class: str) -> bytes: ...
        # Looks up the public key for a given signed_by identifier within this
        # anchor's attestation chain. Raises TrustAnchorMismatchError if the
        # bundle's signed_by does not match a key in this anchor.

# envoy_ledger_verifier/mutation_battery.py
class MutationClass(str, Enum):
    BIT_FLIP = "bit_flip"
    INSERT = "insert"
    DELETE = "delete"
    REORDER = "reorder"
    DUPLICATE = "duplicate"

class MutationBattery:
    """Test-time helper. Lives in tests/, not in the verifier's runtime code."""
    @staticmethod
    def apply(bundle_path: str, mutation_class: MutationClass,
              entry_index: int) -> str: ...

    @staticmethod
    def all_classes() -> list[MutationClass]: ...
        # Used in pytest parametrize for the EC-4 acceptance test.

# envoy_ledger_verifier/canonical.py
def canonical_dumps(obj: dict) -> bytes: ...
    # IMPORTANT: independently re-implemented from the spec.
    # NOT imported from envoy.ledger.canonical — that's a producer module.
    # NFC normalization, alphabetical key sort, ISO 8601 microsecond-padding.

# envoy_ledger_verifier/cli.py
def main(argv: list[str]) -> int: ...
    # Entry point: `envoy-ledger-verify verify <bundle.json>
    #                 --trust-anchor <anchor.json>`
    # Returns 0 on PASS, non-zero with typed-error name in stderr on FAIL.
```

**Per `rules/facade-manager-detection.md` Rule 3:** `Verifier.__init__` takes its `TrustAnchor` dependency explicitly; no global lookup, no self-construction, no implicit "the bundle's own key set" fallback. This is the structural defense against the trust-anchor circularity.

**Per `rules/orphan-detection.md` Rule 1:** the only attribute exposed on the package's top-level facade is `Verifier`. No `VerifierManager`, no `TrustAnchorRegistry` exposed; everything is reached through `Verifier`. Tier 2 wiring tests verify the facade is on the production hot path (the CLI's `main()`).

**Rust class structure (Phase 01 optional, Phase 02 mandatory):** mirrors the Python interfaces above with idiomatic Rust naming (`Verifier`, `TrustAnchor`, `VerificationResult`, `MutationClass`). Crate dependencies: `serde_json`, `ed25519-dalek`, `sha2`, `unicode-normalization`, `clap` (CLI). NO dep on `kailash-rs-bindings`, `envoy-*`, or any producer-side crate.

---

## 5. Integration points

### 5.1 Producer (shard 6) — the export contract

The verifier consumes ONLY the artifact `envoy ledger export --format json` produces (per shard 6 § 3.2 item 6). The interface is unidirectional: producer writes a file; verifier reads the file. There is no IPC, no API call, no shared library, no shared process.

**Bundle delivery channel (Phase 01):**

- User runs `envoy ledger export --format json --output ledger.json` in their Envoy CLI.
- User supplies `ledger.json` to the verifier however they like — copy via USB stick, share via email, upload to cloud storage.
- User runs `envoy-ledger-verify verify ledger.json --trust-anchor anchor.json`.

The bundle delivery channel itself is NOT in scope for the verifier — the verifier accepts a file path on its CLI and that's it.

### 5.2 Channel adapters (shard 16) — bundle delivery surface

A natural extension (Phase 02+) is for channel adapters to support `envoy ledger export-via-channel slack` etc., where the export bundle is delivered through a configured channel. Phase 01 does NOT ship this — the user uses out-of-band file transfer. Recording this as Phase 02 forward reference for shard 16 to consume.

### 5.3 Foundation key registry (Phase 02+)

Per § 3.4, Phase 02 extends the trust-anchor resolution with a Foundation-published registry. The verifier accepts `--trust-anchor https://terrene.foundation/registry/<principal_id>.json` and validates the registry's response is signed by a known Foundation steward key. Phase 01 ships option C (file-based) only.

### 5.4 Cross-runtime conformance gate (Phase 02+)

Per § 3.7, the verifier's mutation-battery fixtures include the E7 conformance vectors from `workspaces/phase-00-alignment/02-plans/conformance/01-runtime-swap-contract.md` § 4.2. When Phase 02 ships kailash-rs-bindings, the same vectors that prove cross-runtime byte-identity ALSO prove producer-vs-verifier byte-identity. The verifier becomes a downstream consumer of the conformance corpus.

---

## 6. Tier 3 test surface

Per `rules/testing.md` § 3-Tier Testing + § Audit Mode Rules: real infrastructure recommended at Tier 2/3; cross-implementation discipline at Tier 3. The verifier's test surface MUST exercise real producer → real verifier across mutation classes AND across operating systems.

### 6.1 Tier 2 wiring tests (in the verifier repo)

| Test file                                                       | What it exercises                                                                                                                                                                                                                             |
| --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/integration/test_verifier_wiring.py`                     | Per `rules/facade-manager-detection.md` Rule 2: imports `from envoy_ledger_verifier import Verifier`, constructs against a static fixture bundle (committed to repo), asserts `verify_bundle(...)` returns PASS. The facade-on-hot-path test. |
| `tests/integration/test_verifier_trust_anchor_resolution.py`    | Construct a Verifier with a TrustAnchor whose key set excludes a key the bundle uses; verify_bundle returns FAIL with `TrustAnchorMismatchError`. The structural defense against trust-anchor circularity.                                    |
| `tests/integration/test_verifier_canonical_json_independent.py` | Re-implement canonical-JSON parsing per the spec; encode a known fixture; assert the verifier's canonical_dumps matches. Tests that the verifier's canonical-JSON is INDEPENDENTLY correct, not collusion-with-producer correct.              |
| `tests/integration/test_verifier_emit_trust_anchor.py`          | First-export self-anchoring path: verifier reads bundle, emits trust-anchor file, reads back the file, uses it to verify the same bundle. Round-trip success.                                                                                 |
| `tests/integration/test_verifier_unsupported_format_error.py`   | Construct a multi-device merged bundle (Phase 01 architectural-contract-only — see § 1.2); verifier MUST raise `UnsupportedExportFormatError` rather than silently accept. Phase 01 Phase 03-deferral structural defense.                     |

### 6.2 Tier 3 tests (in the verifier repo, run on cross-OS CI matrix)

| Test file                                                   | What it exercises                                                                                                                                                                                                                      |
| ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/e2e/test_verifier_real_producer_clean_path.py`       | Spawn a real Envoy producer (via `pipx install envoy-agent` in a sandbox); produce a 1000-entry Ledger; export bundle; verify; assert PASS.                                                                                            |
| `tests/e2e/test_verifier_mutation_battery.py`               | THE EC-4 ACCEPTANCE GATE. For 5 mutation classes × 5 entry-index buckets (start, 25%, 50%, 75%, end), apply the mutation; verifier MUST detect every mutation and report the failing entry index. 25 sub-tests; all MUST pass.         |
| `tests/e2e/test_verifier_cross_os_byte_identity.py`         | Run verifier on macOS + Linux + Windows over the same bundle; outputs MUST be byte-identical. Cross-OS canonical-JSON parsing determinism.                                                                                             |
| `tests/e2e/test_verifier_python_vs_rust_byte_identity.py`   | (If Rust variant ships in Phase 01.) Run Python verifier and Rust verifier over the same bundle; outputs MUST be byte-identical. Cross-language canonical-JSON parsing determinism. THIS is the strongest EC-9 source-isolation proof. |
| `tests/e2e/test_verifier_independent_codebase_assertion.py` | CI-only: grep the verifier's source tree for `import envoy.ledger` / `from envoy.ledger` / `use envoy_ledger` / path deps on producer packages. Assert zero matches. Source-isolation mechanical enforcement.                          |
| `tests/e2e/test_verifier_e7_conformance_vector_passes.py`   | Run the verifier over the E7 conformance corpus (≥10 vectors per `01-runtime-swap-contract.md` § 4.2 row E7). All vectors PASS. The producer-vs-verifier byte-identity proof aligns with the cross-runtime byte-identity proof.        |
| `tests/e2e/test_verifier_pdf_receipt_hash_links_json.py`    | (If Phase 01 ships PDF export per `specs/ledger.md` line 591.) Verifier extracts PDF's `receipt_hash` via a non-Envoy PDF library (`pypdf`); verifies receipt_hash equals SHA-256 of the JSON bundle.                                  |

### 6.3 Cross-OS portability (the EC-9 strongest form)

CI matrix MUST run the Tier 3 tests on at least:

- macOS (latest stable + LTS): `macos-14` GitHub Actions
- Linux (Ubuntu LTS + Debian stable): `ubuntu-22.04` + `ubuntu-24.04`
- Windows (latest stable): `windows-2022`

Per `rules/testing.md`, the cross-OS test catches Unicode normalization drift (NFC behaves differently on macOS HFS+ vs Linux ext4 vs Windows NTFS at the filesystem level — which can affect canonical-JSON byte-identity if the verifier reads files in a way that depends on filesystem normalization), timestamp formatting drift, and locale-dependent string handling.

### 6.4 The orphan-detection compliance test

Per `rules/orphan-detection.md` Rule 1, the verifier's facade `Verifier` MUST be on the production hot path. The CLI's `main()` is the production hot path. The Tier 2 test `test_verifier_wiring.py` imports through the facade and exercises it; the Tier 3 test `test_verifier_real_producer_clean_path.py` invokes `main()` as a subprocess. Both forms covered.

---

## 7. Frozen-spec ambiguity check + recommendation on `specs/independent-verifier.md`

### 7.1 Frozen-spec ambiguities surfaced

This shard surfaced **three MEDIUM-severity ambiguities** in `specs/ledger.md` regarding the verifier — all dispositioned as "draft additive `specs/independent-verifier.md` at shard 22" rather than "edit `specs/ledger.md`" (the latter would trigger MUST Rule 5b 37-sibling re-derivation).

| Ambiguity                                                                                                                          | Severity | Disposition                                                                                                                                                                |
| ---------------------------------------------------------------------------------------------------------------------------------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `specs/ledger.md` line 590: "signed export bundle" — exact wire format unspecified.                                                | MED      | Document the wire format (§ 3.3 of this shard) in additive `specs/independent-verifier.md`. Phase 01 ships against the proposed format; spec draft formalizes at shard 22. |
| `specs/ledger.md` line 592: verifier ships as separate Python package — does NOT specify trust-anchor protocol.                    | MED      | Document trust-anchor option C protocol (§ 3.4) in additive spec. Phase 01 minimum is option C; Phase 02+ extensions documented as forward references.                     |
| `specs/ledger.md` line 599: `LedgerVerificationFailedError` is a single typed error — does NOT enumerate verifier-internal errors. | MED      | Document the verifier's typed error classes (§ 4 in this shard) in additive spec. Producer-side error class stays as `specs/ledger.md` declares.                           |

None of these rise to HIGH severity per `01-shard-plan.md` § 4 failure-mode protocol — none of them block implementation, all of them are "spec gaps" rather than "spec contradictions." Implementation can proceed against the proposed contracts in this shard while shard 22 formalizes them in `specs/independent-verifier.md`.

### 7.2 Recommendation on `specs/independent-verifier.md`

**RECOMMEND: Draft `specs/independent-verifier.md` as additive at shard 22.**

Per the inheritance map (`00-inheritance-from-phase-00.md` § 5.4): "Identified via gap analysis in shard 12 ... `specs/independent-verifier.md` (probable) — captures the separately-codebased verifier contract since the verifier itself is Phase-01-specific." This shard is the formal recommendation.

**Per `rules/specs-authority.md` MUST Rule 5b:** NEW spec files do NOT trigger 37-sibling re-derivation. The draft is additive only, low-cost, no convergence risk.

**Proposed `specs/independent-verifier.md` structure (for shard 22 to author):**

1. **§ Purpose** — verifier as Phase 01 EC-9 deliverable; structurally separated from producer.
2. **§ Bundle wire format** — §3.3 of this shard, transcribed; key invariants enumerated.
3. **§ Trust-anchor resolution** — §3.4 of this shard; Phase 01 option C minimum; Phase 02+ extensions.
4. **§ Mutation battery contract** — §3.5 of this shard; 5 mutation classes; per-class detection requirement.
5. **§ Source-isolation enforcement** — §3.6 of this shard; CI checks; license-header contract.
6. **§ Cross-runtime conformance vector reuse** — §3.7 of this shard; E7 vector linkage.
7. **§ Error taxonomy** — §4 of this shard; typed errors enumerated; alignment with `specs/ledger.md` § Error taxonomy.
8. **§ Test location** — §6 of this shard; Tier 2 + Tier 3 test files transcribed.
9. **§ Cross-references** — back to `specs/ledger.md`, forward to `specs/independent-verifier.md` consumers.

The draft does not edit `specs/ledger.md`; it ADDS detail at the verifier level that the producer-level spec naturally elided.

---

## 8. Cross-references

- **Frozen specs (DO NOT EDIT):**
  - `specs/ledger.md` § "Export + independent verifier" lines 588–592 (verifier mandate)
  - `specs/ledger.md` § "Error taxonomy" line 599 (`LedgerVerificationFailedError`)
  - `specs/ledger.md` § "Open questions" lines 642–644 (verifier language; Python community default; Rust Phase 04)
  - `specs/ledger.md` § "Entry envelope schema" lines 14–34 (the envelope shape the verifier walks)
  - `specs/ledger-merge.md` (Phase 01 architectural-contract-only; verifier rejects merged bundles)
- **Phase 01 analysis:**
  - `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 2 (sharding) + § 4 (failure-mode protocol)
  - `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` EC-4 (verifiable export tampering battery), EC-9 (separately-codebased verifier)
  - `workspaces/phase-01-mvp/01-analysis/03-kailash-py-mvp-readiness.md` § 3 row 4 (Independent verifier — Envoy-new) + § 5 verification protocol
  - `workspaces/phase-01-mvp/01-analysis/06-envoy-ledger-implementation.md` § 3.4 (sunset clause for #596) + § 6.2 (Tier 3 test_envoy_ledger_independent_verifier_ec9)
  - `workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` (re-derivation prohibition)
- **Phase 00 inheritance:**
  - `workspaces/phase-00-alignment/02-plans/conformance/01-runtime-swap-contract.md` § 4.2 row E7 (Ledger head-commitment monotonicity ≥10 vectors) + § 7.2 (kailash-py runner pattern) — cross-implementation conformance pattern; verifier is the same pattern at single-runtime scale
  - `workspaces/phase-01-mvp/01-analysis/00-inheritance-from-phase-00.md` § 5.4 (additive `specs/independent-verifier.md` recommendation)
- **Forward references (next shards):**
  - shard 16 — channel adapters (Phase 02+ bundle delivery via channel)
  - shard 19 — pipx distribution (verifier ships as separate `pip install envoy-ledger-verify` package; producer ships as `pipx install envoy-agent`)
  - shard 22 — additive spec drafts (`specs/independent-verifier.md` per § 7.2 above)
  - shards 23–24 — redteam (mutation-battery test fixture authoring; cross-OS portability matrix; source-isolation CI checks)
- **Rules cited:**
  - `rules/zero-tolerance.md` Rule 6 (implement fully — verifier MUST detect EVERY mutation class, not just some)
  - `rules/orphan-detection.md` Rule 1 + Rule 2a (facade hot-path; crypto-pair round-trip through facade)
  - `rules/facade-manager-detection.md` Rule 1 + Rule 2 + Rule 3 (Tier 2 wiring; naming convention; explicit dependency)
  - `rules/testing.md` § 3-Tier Testing + § Tier 3 cross-implementation discipline
  - `rules/specs-authority.md` MUST Rule 5b (new spec files additive; do not trigger re-derivation)
  - `rules/independence.md` (Foundation track framing for repo location)
  - `rules/autonomous-execution.md` § Per-Session Capacity Budget (6 invariants tracked; within budget)
- **Repos / packages referenced:**
  - **Producer:** `terrene-foundation/envoy` (Apache 2.0); package `envoy-agent` (PyPI); CLI `envoy ledger export`
  - **Verifier (RECOMMENDED location):** `terrene-foundation/envoy-ledger-verifier` (Apache 2.0); Python package `envoy-ledger-verify` (PyPI); Rust crate `envoy-ledger-verifier` (crates.io, Phase 01 optional / Phase 02 mandatory); CLI `envoy-ledger-verify`
