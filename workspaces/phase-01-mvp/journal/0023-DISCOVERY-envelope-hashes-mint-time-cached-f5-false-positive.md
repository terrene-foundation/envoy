---
type: DISCOVERY
date: 2026-05-24
created_at: 2026-05-24T18:00:00Z
author: agent
session_id: rt1-shard2-followup
session_turn: 1
project: phase-01-mvp
topic: F-5 false-positive — envelope hashes are mint-time-cached frozen fields; no re-canonicalization path exists in the codebase
phase: redteam
tags:
  - redteam
  - round-1
  - F-5
  - false-positive
  - envelope
  - jcs
  - mint-time-hash
  - rt1-shard2
---

# DISCOVERY: F-5 is FALSE-POSITIVE — `posture_level` schema bump is not required

Round 1 /redteam Lane C (security audit) flagged F-5 (HIGH) as a wire-shape break:

> **F-5 | HIGH | wire-shape break: posture_level field added to EnvelopeMetadata** —
> "Adding a non-Optional field with a default to a `@dataclass(frozen=True)` that
> participates in JCS canonical bytes is a wire-shape break. Every pre-T-02-33
> envelope persisted with its `content_hash` will produce a DIFFERENT
> content_hash on re-canonicalization after this change. Any downstream consumer
> caching content_hash (Trust store `DelegationRecord.effective_envelope_hash`,
> Ledger `envelope_edit` entries, SubsetProof verifier `parent_envelope_hash`)
> breaks across the version boundary. Disposition: bump `schema_version` from
> `envelope/1.0` to `envelope/1.1` … so consumers can detect the canonical-bytes
> shape change."
>
> — `workspaces/phase-01-mvp/04-validate/round-1-security-audit-2026-05-24.md` § F-5
> (committed at SHA `7598578`, line 689)

Pre-flight investigation under `rules/verify-resource-existence.md` MUST-3 (default to delete-or-stub when the threat target does not exist) determined that the threat model F-5 names — re-canonicalization of pre-T-02-33 envelopes producing a different content_hash — requires a re-canonicalization path that **does not exist anywhere in the codebase**. F-5 is therefore a FALSE-POSITIVE against the current code. The `schema_version` bump it recommends would add ceremony to defend against a wire-shape-break that the design explicitly prevents by construction.

This entry records the five receipts that established the determination, and pairs with the Tier 2 regression test that pins the underlying invariant against future refactors.

## Investigation evidence — the five receipts

### 1. `EnvelopeConfig.content_hash` is a stored frozen field, not a derived property

`envoy/envelope/types.py:395-396`:

```
    canonical_bytes: bytes
    content_hash: str  # sha256 hex over canonical_bytes
```

These are positional dataclass fields on `EnvelopeConfig`, which is declared `@dataclass(frozen=True)` (per `types.py:380` and the L-03 shard B carry-forward). The hash is **stored**, not computed-on-access. Every read of `envelope.content_hash` returns the same bytes/string object the compiler placed there at mint time; no second pass through `hashlib.sha256` ever occurs after `compile()` returns.

### 2. Hashes are computed exactly once, at compile time, by `EnvelopeCompiler.compile()`

`envoy/envelope/compiler.py:258-279`:

```
# Step 8 — JCS canonicalize → canonical_bytes + content_hash
payload = self._to_canonical_payload(config_input, envelope_version=envelope_version)
cb = _canonical_bytes(payload)
ch = _content_hash(cb)

compiled = EnvelopeConfig(
    schema_version=config_input.schema_version,
    envelope_version=envelope_version,
    metadata=config_input.metadata,
    ...
    canonical_bytes=cb,
    content_hash=ch,
    ...
)
```

`compile()` is the only constructor of canonical_bytes + content_hash in the entire `envoy/envelope/` subtree. The values are computed inside step 8, placed into the frozen `EnvelopeConfig`, and never re-derived. The compiler's docstring (`compiler.py:7-23`) lists ten pipeline steps; only step 8 produces a hash, and step 8 fires exactly once per `compile()` call.

### 3. The design intent is explicitly documented as "single-point mint-time hash"

`envoy/envelope/canonical_bytes.py:73-83` — the docstring of `content_hash(canonical: bytes)`:

```
def content_hash(canonical: bytes) -> str:
    """SHA-256 hex digest over canonical bytes.

    The single-point hash production at compile time means the Trust store
    (`DelegationRecord.effective_envelope_hash`), Ledger (`envelope_edit`
    entries), and SubsetProof verifier (`parent_envelope_hash` /
    `sub_envelope_hash`) all agree on the same canonical bytes — no drift
    surface between consumers per shard 4 § 3 step 5.
    """
```

The docstring is the **design contract** the F-5 threat model contradicts. F-5 imagines a code path that consumes a stored envelope by re-deriving its canonical bytes from in-memory metadata. The docstring documents that this path is intentionally absent: hashes are produced once, at mint, and every consumer reads the same value from storage.

### 4. No envelope deserializer exists in `envoy/envelope/`

Grep across the entire envelope module for any pattern that would re-derive an `EnvelopeConfig` from a serialized form:

```
$ grep -rn "from_json\|from_dict.*Envelope\|loads.*Envelope" envoy/envelope/
(exit 1 — no matches)
```

There is no `EnvelopeConfig.from_json()`, no `EnvelopeConfig.from_dict()`, no `json.loads(...)` followed by envelope reconstruction, and no JCS-bytes-to-EnvelopeConfig path. The class is constructible only via `EnvelopeCompiler.compile()` (or `dataclasses.replace()` of an already-compiled instance, which preserves the stored `canonical_bytes` + `content_hash` unless the caller explicitly overrides them — and the only override site is the Tier 2 PostureGate adapter at `tests/tier2/test_posture_gate_wiring.py:230-236`, which recomputes via the SAME `canonical_bytes` pipeline, not a re-canonicalization of a deserialized envelope).

### 5. PostureGate consumes envelope fields as stored attributes, never re-derives

`envoy/authorship/posture_gate.py:683` declares `prior_content_hash` as a `_PostureCarryingEnvelope` Protocol property — a stored attribute. The production consumer at `posture_gate.py:1032-1063` reads `envelope.envelope_id`, `envelope.prior_version` as plain attribute accesses on the passed-in envelope (the Tier 2 wiring test's `_EnvelopeConfigPostureCarrier` returns the underlying `EnvelopeConfig.metadata.envelope_id` / `EnvelopeConfig.envelope_version` / `EnvelopeConfig.content_hash` directly — they are NOT recomputed). When PostureGate writes the `envelope_edit` Ledger entry at `posture_gate.py:1056-1064`, it forwards `mutation.diff_hash` verbatim (which the adapter has already computed once via the same canonical_bytes pipeline at adapter `mutate_for_posture_level()` time) — not via any re-canonicalization of a stored envelope.

`DelegationRecord.effective_envelope_hash` (the Trust-store-side hash F-5 names) is set once at delegation mint time inside the kailash-py `TrustOperations.delegate(...)` flow (out of scope for this envoy session per `rules/repo-scope-discipline.md`); envoy never reconstructs it.

## Determination — F-5 is FALSE-POSITIVE per `rules/verify-resource-existence.md` MUST-3

F-5's threat model requires the existence of a re-canonicalization path — code that takes a stored envelope (or its serialized JSON), reads its post-T-02-33 `metadata.posture_level` field, re-runs the JCS canonicalization pipeline, recomputes the SHA-256 hash, and compares the new hash to a cached pre-T-02-33 hash. No such path exists in `envoy/envelope/`, in `envoy/authorship/`, or in any envoy-side consumer. The hash that ends up in the Trust store, in the Ledger, and in the SubsetProof verifier is the SAME hash the compiler produced at mint time — there is no second pass to drift from the first.

Under `rules/verify-resource-existence.md` MUST-3 ("when the existence check fails, default disposition is delete-or-stub, not provision"), the correct disposition is to NOT bump `schema_version` from `envelope/1.0` to `envelope/1.1`. A schema bump would (a) add ceremony to every consumer for a failure mode the design explicitly prevents, (b) require a migration path for in-flight Phase 01 envelopes that the codebase has no infrastructure for, and (c) institutionalize a `1.0 → 1.1` precedent that the next non-additive metadata change will be measured against — locking the schema-version axis to a defense against a phantom threat.

## Why this matters for future refactors

The F-5 finding is correct as an abstract threat model: in a system that DID round-trip envelopes through JCS at every read, adding a non-Optional field to a frozen JCS-participating dataclass would absolutely break content_hash continuity. The reason F-5 is false-positive HERE is that envoy's envelope design chose, by construction, to avoid that round-trip — the docstring at `canonical_bytes.py:73-83` is the explicit design statement.

A future refactor that introduces an envelope deserializer (e.g. for backup/restore, for cross-process envelope ingestion, for a JSON-API surface that accepts envelope payloads from clients) would re-open the F-5 failure mode. The companion regression test landed in this PR — `tests/tier2/test_envelope_hash_mint_time_cached.py::TestEnvelopeHashesAreMintTimeCached::test_no_envelope_deserializer_exists` — fails loudly the moment such a path lands, forcing the author of that refactor to update the design contract (and to introduce hash-continuity invariants per F-5's intent at the SAME time).

The regression test is the structural defense; this journal entry is the institutional memory that explains WHY the design intent matters.

## Alternatives considered (and rejected)

1. **Bump `schema_version` to `envelope/1.1` per F-5's recommendation.** Rejected: defends against a threat model that does not apply to the current code; adds migration ceremony with no consumer to migrate; institutionalizes a precedent that future non-additive changes will be measured against.

2. **Add `algorithm_identifier.metadata_version` bump per F-5's alternative.** Rejected: same reason as (1), at a narrower surface. The algorithm_identifier change would carry the same false-positive defense AND would require a Wave-2 algorithm-identifier-aware consumer that does not yet exist.

3. **Document F-5 in CHANGELOG as a breaking change without code change.** Rejected: documenting a non-breaking change as breaking is misinformation that downstream consumers act on; the CHANGELOG MUST describe what actually changed, not what an audit hypothesized.

4. **Land the Tier 2 regression test and the journal entry as the FALSE-POSITIVE disposition.** ACCEPTED. The test pins the design invariant; the journal entry records why F-5 is false-positive AND what conditions would re-open it.

## Cross-references

- Round 1 security audit (the F-5 finding being closed): `workspaces/phase-01-mvp/04-validate/round-1-security-audit-2026-05-24.md` § F-5 (committed at SHA `7598578`)
- Design-intent docstring: `envoy/envelope/canonical_bytes.py:73-83`
- Compiler single-point hash production: `envoy/envelope/compiler.py:258-279`
- Frozen stored-field declaration: `envoy/envelope/types.py:395-396`
- PostureGate stored-attribute consumption: `envoy/authorship/posture_gate.py:683` (Protocol), `posture_gate.py:1032-1064` (production write of `envelope_edit`)
- Shard 1 mint-state disposition (the sibling F-4 disposition this PR pairs with): `workspaces/phase-01-mvp/journal/0022-DECISION-posture-level-mint-state-interpretation.md`
- Origin T-02-33 pairing design: `workspaces/phase-01-mvp/journal/0021-DECISION-t-02-33-envelope-edit-pairing-design.md`
- Disposition rule applied: `rules/verify-resource-existence.md` MUST-3
- Regression test pinning the invariant: `tests/tier2/test_envelope_hash_mint_time_cached.py`

## For Discussion

1. **Counterfactual — what would change the disposition?** If a future PR introduced `EnvelopeConfig.from_json()` (or any path that re-derives canonical_bytes from a serialized envelope), would the F-5 threat model become applicable AGAIN, and what would the migration path look like? Specifically: would we add a hash-continuity invariant (the new deserializer MUST preserve the stored `content_hash` byte-identical) OR would we re-canonicalize and bump `schema_version` to `envelope/1.1` as F-5 originally recommended? The answer determines whether the regression test landed here should fail-loudly OR be replaced by a different invariant when that day comes.

2. **Data-specific — does the Trust store's `DelegationRecord.effective_envelope_hash` invariant hold across the kailash-py boundary?** The investigation receipts (#1-#5) all live in envoy; the Trust-store assertion that `effective_envelope_hash` is mint-time-set lives in kailash-py per `repo-scope-discipline.md` (out of scope for this envoy session). Should envoy's Phase 02 entry add a Tier 3 cross-repo test that constructs an envelope via `EnvelopeCompiler.compile()`, hands its `content_hash` to kailash-py's `TrustOperations.delegate(...)`, fetches the delegation back, and asserts `DelegationRecord.effective_envelope_hash == envelope.content_hash` — closing the cross-repo invariant the way envoy's Tier 2 closes the same-repo invariant?

3. **Pattern-generalizability — are there OTHER F-5-shape findings in Round 1 that share the "threat against a non-existent path" disposition?** F-5 was caught because the auditor named a specific re-derivation path that turned out to not exist; how many other Round 1 HIGH findings (F-2, F-4 are already closed by Shard 1; F-6+ remain) would benefit from a same-shape `verify-resource-existence.md` MUST-3 pre-flight before defaulting to "provision the fix"? Should `/redteam` Round 2 explicitly include a "does the threatened path actually exist?" gate before any HIGH finding is escalated to a /implement shard?
