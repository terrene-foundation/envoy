# 06 — Envoy Ledger + ledger-merge implementation

**Document role:** Implementation deep-dive for the Phase 01 Envoy Ledger primitive (and its `ledger-merge` companion). Cites the frozen spec by path + section, identifies what `kailash-py` provides today, names the Envoy-new-code surface, sketches class structure, lists integration points, names Tier 2 / Tier 3 test surfaces, and surfaces any frozen-spec ambiguity.

**Date:** 2026-05-03 (shard 6 of /analyze).
**Status:** DRAFT — load-bearing for shards 7 (independent verifier), 10 (Grant Moment), 11 (Daily Digest), 16 (channel adapters); also referenced by shards 5 (Trust store), 9 (Authorship Score), 12 (Budget tracker).

**Capacity check:** one primitive, three source specs (ledger.md, ledger-merge.md, remote-time-anchor.md), ~5 invariants tracked (hash-chain shape stability; canonical-JSON byte determinism; timestamp microsecond determinism; tenant_id persistence; classified-PK redaction at emit), ≤4 cross-primitive references (Trust store, Grant Moment, Daily Digest, Channel adapters). Within `rules/autonomous-execution.md` budget.

**Phase 00 framing reminder:** This shard does NOT re-derive `specs/ledger.md`. Per `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md`, the ledger spec is frozen — Phase 01's question is "given this spec is frozen, how do we wire `kailash-py` to deliver it?" not "is this spec right?" If a HIGH ambiguity surfaces it triggers `01-shard-plan.md` §4 escalation; §7 below records the (none-found) result.

---

## 1. Source spec citation

### 1.1 `specs/ledger.md` — the contract Phase 01 must deliver

The Ledger primitive is owned by `specs/ledger.md` (frozen Phase 00 artifact, authority per `rules/specs-authority.md`). Phase 01 implementation MUST conform; deviation is governed by MUST Rule 6.

**Hash-chain shape (load-bearing for EC-4 + EC-9):** `specs/ledger.md` § "Entry envelope schema" lines 14–34 fixes the canonical envelope. The independent verifier in EC-9 cannot share source with the producer; the chain shape IS the contract that crosses the source-isolation boundary. Single load-bearing fields:

- `entry_id = "sha256:<content_hash>"` — content-addressed identity (line 17)
- `parent_hash = "sha256:<prev_entry_id>"` — chain link (line 17)
- `sequence: <int>` — monotonic per-device sequence (line 18)
- `lamport_clock = {lamport_time, device_id, local_seq}` — three-tuple CRDT ordering key (lines 19–23, 38–40); `lamport_time` is primary, `device_id` (= SHA-256 of device binding pubkey) is secondary, `local_seq` tertiary
- `timestamp: <iso8601>` — wall-clock at append (line 24)
- `type: <EntryType>` — one of the 35 entry types in lines 47–91
- `intent_id` — present-non-null on `PhaseARecord`/`PhaseBRecord`, null on `GenesisRecord`/`KeyRotationRecord`/`posture_change` etc. (line 41 explicit semantics)
- `content` — type-specific payload (line 25)
- `content_trust_level` — one of 8 enum values (line 27)
- `description_content_hash + algorithm` — auxiliary integrity field (line 28)
- `signed_by` — `device_key | genesis_key` (line 29)
- `signature_hex` — Ed25519 signature over canonicalized envelope (line 30)
- `algorithm_identifier` — versioned tag enabling Phase 04 PQ migration (line 31; consumer in `MigrationAnnouncement` at lines 169–179)
- `schema_version: "ledger-entry/1.0"` — wire-format version (line 32)

**Cite-but-do-not-paraphrase discipline:** the per-type schemas at `specs/ledger.md` lines 98–518 (35 entry types × ~5 fields each) are the implementation contract. The implementation in §3 below imports them by reference; it does not re-state them.

**Two-phase signing (`specs/ledger.md` § "Two-phase signing (T-004)" lines 519–523):** `PhaseARecord` (intent, delegation-key-signed, pre-execution) → `PhaseBRecord` (outcome, runtime-device-key-signed, post-execution) linked by `intent_id`; orphan resolution via `PhaseAOrphanResolution` at next session start with 30-day TTL.

**Head commitment (`specs/ledger.md` § "Head commitment (T-100)" lines 525–548):** runtime-device-key-signed `HeadCommitment` at every sync; monotonic non-decreasing `head_sequence`; rollback decrease → `LedgerRollbackDetectedError`; pre-halt `HaltedByRollback` entry preserves last-known-good + detected-inconsistent heads. Phase 01 MUST emit this halt record before refusing further writes.

**System error records (`specs/ledger.md` § "System error" lines 552–569):** uncaught runtime exceptions become `system_error` Ledger entries; content fingerprint MUST NOT echo PII / secrets / envelope internals (cross-references `rules/dataflow-classification.md` + `rules/event-payload-classification.md`).

**Retention + GDPR (`specs/ledger.md` § "Retention + GDPR (T-003)" lines 577–582):** default forever; tombstoning preserves metadata, replaces content with commitment; per-entry key destruction strongest form via `EntryKeyDestruction`; user retention policy in envelope.

**Segment boundary (`specs/ledger.md` § "Segment boundary on MigrationAnnouncement" lines 584–586):** Ledger partitioned into algorithm-identifier-tagged segments at each `MigrationAnnouncement`; chain verification dispatches per segment.

**Export (`specs/ledger.md` § "Export + independent verifier" lines 588–592):** `envoy ledger export --format json` produces a signed export bundle; PDF form carries `receipt_hash` pointing to JSON; the reference-verifier `envoy-ledger-verify` ships as a separate Python package. Phase 01 EC-4 + EC-9 acceptance gate.

**Error taxonomy (`specs/ledger.md` § "Error taxonomy" lines 595–607):** 8 typed error classes — `LedgerRollbackDetectedError`, `LedgerVerificationFailedError`, `LedgerSyncConflictError`, `EntryKeyDestroyedError`, `PhaseAOrphanDetectedError`, `LedgerConflictFloodError`, `LedgerHaltedError`, `LedgerAlgorithmMismatchError`. All emitted as `system_error` Ledger entries when originating inside the runtime.

### 1.2 `specs/ledger-merge.md` — CRDT merge protocol (T-101)

`specs/ledger-merge.md` § "Algorithm" lines 14–31 fixes the merge sort key as `(lamport_time, device_id, local_seq)` and mandates that each entry carry both `original_parent_hash` (signed, immutable) and `merged_parent_hash` (derived after merge). `LedgerConflictEntry` is appended for each detected conflict.

**Conflict types (`specs/ledger-merge.md` § "Conflict types" lines 35–39):** `NonceConflict`, `IntentIdConflict`, `RevocationRaceConflict`. Plus `LamportTie`, `DuplicateNonce` per `specs/ledger.md` line 439.

**Conflict-flood rate-limit (`specs/ledger-merge.md` § "Conflict-flood rate-limit (R2-H1 fix)" lines 41–45):** per-principal cap of 20 unresolved conflicts; semantic batching by similarity; sync suspended on overflow.

**Resolution UX (`specs/ledger-merge.md` § "Resolution UX" lines 47–53):** NonceConflict — user picks; IntentIdConflict — user picks canonical or cancels both; RevocationRaceConflict — revocation wins automatically with notify.

**Phase 01 scope note:** `ledger-merge` is a multi-device primitive. Phase 01's exit criteria (EC-1 through EC-9) explicitly target a SINGLE-PRINCIPAL, SINGLE-DEVICE deployment (per `02-mvp-objectives.md` EC-7's "single user onboards via any of 8 channels" — channels are entry surfaces, not separate devices). The merge algorithm therefore ships as **architectural contract** in Phase 01 (interfaces, type definitions, `LedgerConflictEntry` schema, three-tuple Lamport ordering field) but the `merge(branches)` orchestration is exercised only by Tier 2 tests in shard 6's harness — no production multi-device path runs in Phase 01. Phase 03 (multi-device) wires the merge call into the sync runtime. This is consistent with `specs/ledger-merge.md` § "Open questions" #5 ("Phase 02+ N-device merge performance"). Recording this disposition explicitly so shard 7's verifier can skip merge-replay verification in MVP and so shard 23/24 redteam knows the deferral is intentional, not orphaned.

### 1.3 `specs/remote-time-anchor.md` — Phase 02 deliverable

`specs/remote-time-anchor.md` is explicit at line 14: **"Phase 02 deliverable."** Phase 01 MUST NOT ship the TSA quorum, OHTTP relay, or `time_anchor` Ledger entry production path. However:

1. The `time_anchor` entry type IS listed in `specs/ledger.md` line 83 as an entry type Phase 01 schemas must accept (forward-compatible parsing).
2. The Temporal-dimension envelope check in Phase 01 falls back to `Ledger monotonic clock` only (per `specs/remote-time-anchor.md` line 52: `max(Ledger monotonic clock, most_recent_anchor.anchor_time)` collapses to the first term when no anchor exists).
3. The `ClockSkewEvent` entry type IS in Phase 01 (line 82) — even without TSA quorum, the runtime detects local-clock anomalies via Lamport-clock divergence and emits this record.

**Phase 01 disposition:** ship Lamport-clock determinism + `ClockSkewEvent` detection logic; defer TSA quorum + `time_anchor` entry production to Phase 02.

---

## 2. Verified provider citation — what `kailash-py` provides

Per `03-kailash-py-mvp-readiness.md` § 5 verification protocol, this section names the verified upstream symbols + indirect-closure PR refs that materially affect hash-chain determinism for EC-4 / EC-9.

### 2.1 What `kailash-py` provides today (verified at 2026-04-21 survey, indirect-closure deltas through 2026-05-03)

| Surface needed by Ledger      | `kailash-py` provider                                                                             | Verified citation                                                                                                                                              |
| ----------------------------- | ------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Append-only audit base        | `AuditStore` (referenced in `02-kailash-py-survey.md` item 4 line 119: "AuditStore exists")       | `02-kailash-py-survey.md` § item 4 line 119: "`AuditStore` (append-only ledger) exists but no tiered-dispatch wrapper"                                         |
| Ed25519 signing               | `kailash.trust.signing.crypto`                                                                    | `02-kailash-py-survey.md` § item 17 line 537: "All Ed25519 signing implemented in `src/kailash/trust/signing/crypto.py`"                                       |
| Trust chain primitives        | `kailash.trust.chain.TrustLineageChain`, `GenesisRecord`, `DelegationRecord`, `RevocationRecord`  | `02-kailash-py-survey.md` § item 17 lines 514–535                                                                                                              |
| Cascade revocation            | `kailash.trust.revocation.cascade.cascade_revoke()`                                               | `02-kailash-py-survey.md` § item 3 lines 91–104; ISS-05 (#595) closed Apr 25 — docstring cross-ref improvement                                                 |
| `format_record_id_for_event`  | `dataflow.classification.event_payload.format_record_id_for_event(policy, model_name, record_id)` | `02-kailash-py-survey.md` § item 12 lines 354–376: location `packages/kailash-dataflow/src/dataflow/classification/event_payload.py:51–99`; A grade            |
| `@classify` field decorator   | `dataflow.classification.policy.classify(field_name, classification, retention, masking)`         | `02-kailash-py-survey.md` § item 10 lines 287–312                                                                                                              |
| `ClassificationPolicy` lookup | `dataflow.classification.policy.ClassificationPolicy.classify() / .get_field()`                   | `02-kailash-py-survey.md` § item 11 lines 320–338; ISS-23 (#601) closed Apr 25 — public API surface for `apply_read_classification` (no Phase 01 wrapper need) |

### 2.2 Indirect-closure PR refs that improve hash-chain determinism

Per `03-kailash-py-mvp-readiness.md` § 2.2, four upstream closures since 2026-04-21 directly affect Ledger determinism. Citing each:

1. **#757 + #756 — Unicode byte-vector pinning for audit-chain canonical-input + TraceEvent canonical-JSON.** Effect: the byte-vector canonicalization for audit-chain SHA-256 input is now pinned cross-SDK. The Ledger's `entry_id = sha256(canonical_json(envelope))` step inherits this pin, which is the structural reason a separately-codebased verifier (EC-9, kailash-rs or different-language Python) can match byte-for-byte. Without the pin, Unicode normalization differences (NFC vs NFD vs raw UTF-8) silently produce different hashes for the same logical envelope.
2. **#731 — TraceEvent timestamp microsecond padding (cross-SDK).** Effect: the `timestamp: <iso8601>` field in every Ledger entry padded to microsecond precision identically in Python and Rust. Without this, a Python emitter and a Rust verifier of the same wall-clock instant would produce different canonical bytes (`2026-05-03T10:00:00.123Z` vs `2026-05-03T10:00:00.123000Z` vs `2026-05-03T10:00:00.123000000Z`).
3. **#707 + #711 — `df.transaction()` + `db.transactions_sync.begin()` context manager.** Effect: Ledger appends can wrap in a real `BEGIN/COMMIT` boundary so the (a) write to the SQLite `audit_store` table, (b) update of the `head_commitment` state, (c) emission of any sibling event-bus entry are atomic. Without this, a power-loss between (a) and (b) lets the audit row persist while head_commitment lags, producing a chain-verification false positive (`HeadCommitment.head_sequence` < actual max sequence in store).
4. **#672 — Python `format_record_id_for_event` cross-SDK with kailash-rs BP-048.** Effect: every Ledger entry's `content.record_id` field (when the entry references a classified-PK model — e.g. an `Account` keyed by `email`) routes through the helper. The 8-hex SHA-256 prefix shape is identical Python ↔ Rust, satisfying `rules/event-payload-classification.md` Rule 1 + Rule 2 with cross-SDK forensic correlation.

### 2.3 The CRITICAL fix: #750 SQLite update/delete silent no-op

**#750 — DataFlow Express update/delete silently no-op on SQLite.** Effect: Envoy uses SQLite as the Phase 01 backing store (per `02-kailash-py-survey.md` items 5, 16 SQLite-backed stores; `pipx install envoy-agent` Phase 01 distribution per ADR-0001). Pre-#750-fix, an `UPDATE` against an `audit_store` row (e.g. tombstoning per `specs/ledger.md` line 581) silently returned success while NOT modifying the row. Cross-references: `rules/zero-tolerance.md` Rule 4 — Envoy MUST verify #750's fix shipped before depending on the update path; the readiness doc § 2.2 lists #750 as closed.

### 2.4 What `kailash-py` does NOT provide (Phase 01 OPEN gap)

**#596 — `TieredAuditDispatcher` STILL OPEN.** Per `02-kailash-py-survey.md` item 4 line 116: "Not found in codebase" — the tier-based dispatch (DEBUG/INFO/WARN/CRITICAL routing), the hash-chained Audit Anchor structure (separate from `AuditStore`'s flat append), and the SIEM export glue do not exist upstream. The `AuditStore` provides the append-only base; everything tier-based or chain-anchored is missing.

**Phase 01 disposition (per `rules/zero-tolerance.md` Rule 4 + `03-kailash-py-mvp-readiness.md` § 4 row 1):** Envoy implements the hash-chain Ledger writer locally as `envoy-new-code`; cross-files an upstream PR proposing the `TieredAuditDispatcher` for adoption; documents the local implementation with a sunset clause that retires Envoy's code when upstream lands.

---

## 3. Envoy-new-code surface

### 3.1 Module shape: `envoy.ledger` composing upstream pieces

The Phase 01 Envoy-new-code surface is a single Python package `envoy.ledger` exposing the facade `EnvoyLedger`. The package composes:

- `kailash.trust.signing.crypto.Ed25519Signer` (verified provider, §2.1) — for `signed_by` + `signature_hex` field generation
- `kailash.trust.audit.AuditStore` or equivalent append-only base (verified, §2.1) — wrapped, NOT extended; Envoy adds the hash-chain layer above the append-only layer
- `dataflow.classification.event_payload.format_record_id_for_event` (verified, §2.1) — applied at every entry-emission site that touches a classified-PK model
- `dataflow.transactions.df.transaction()` context manager (verified via #707/#711 closure, §2.2) — wraps the (audit_row + head_commitment + event_bus) tuple atomically

Composition philosophy: Envoy `import`s upstream symbols by name; Envoy does not subclass `AuditStore` (orphan-detection-safe; the hot-path facade `EnvoyLedger.append()` is the one production call site). Per `rules/orphan-detection.md` Rule 1 + Rule 3, the `AuditStore` instance is owned by `EnvoyLedger`, accessed via composition.

### 3.2 Surface to be built (Envoy-new-code)

1. **`envoy.ledger.EnvoyLedger`** — facade with `.append(entry)`, `.query(filter)`, `.verify_chain(start, end)`, `.head_commitment()`, `.export(format)` (CLI-callable). Composes upstream `AuditStore` + `Ed25519Signer`.
2. **`envoy.ledger.canonical.CanonicalJsonEncoder`** — deterministic JSON serializer producing the byte-vector that feeds SHA-256 for `entry_id`. MUST match the Unicode pinning landed in #757/#756. Field ordering: alphabetical key sort; UTF-8 NFC normalization; no insignificant whitespace; ISO 8601 timestamp microsecond-padded per #731. The canonical-JSON contract IS the cross-SDK byte-identity contract; per `specs/ledger.md` BET-6 (line 12) it is the load-bearing claim.
3. **`envoy.ledger.HashChainBuilder`** — given (envelope_dict, prev_entry_id, signing_key) produces (entry_id, parent_hash, signature_hex). Pure function; deterministic; testable in Tier 1.
4. **`envoy.ledger.HeadCommitment`** — `{head_sequence, head_entry_id, signed_at, runtime_attestation, signature_hex}` issued at every sync (Phase 01: at every successful `append()`, since "sync" in single-device-Phase-01 is a per-write event). Monotonic non-decreasing invariant per `specs/ledger.md` line 528 enforced at append time; rollback emits `HaltedByRollback` per lines 532–548.
5. **`envoy.ledger.Lamport`** — `Lamport(lamport_time, device_id, local_seq)` dataclass with `.next(observed_max)` returning `(max(observed_max, self.lamport_time) + 1, self.device_id, self.local_seq + 1)` per `specs/ledger.md` line 38 semantics. Phase 01 single-device uses `device_id = sha256(local_genesis_pubkey)` (set once at Genesis ritual).
6. **`envoy.ledger.export.cli`** — `envoy ledger export --format json|pdf` Click/argparse entry point. JSON form produces the signed bundle per `specs/ledger.md` line 590; PDF form embeds `receipt_hash`. Output is the artifact the EC-9 verifier (shard 7) consumes.
7. **`envoy.ledger.errors`** — the 8 typed errors per `specs/ledger.md` lines 595–607 + the 8 ledger-merge errors per `specs/ledger-merge.md` lines 61–70. Each `system_error`-mapped error subclasses a base `LedgerError`.
8. **`envoy.ledger.merge`** — interfaces only in Phase 01 per §1.2 scope note. `LedgerConflictEntry` schema, three-tuple Lamport sort comparator, `merge(branches)` signature. Production wiring in Phase 03.
9. **`envoy.ledger.entry_types`** — TypedDict / pydantic dataclass per type from `specs/ledger.md` lines 47–91. 35 types. Each carries `schema_version` per the spec. NOT re-derived; transcribed from the spec field-by-field.
10. **`envoy.ledger.event_emitter`** — single-point filter at the emitter (per `rules/event-payload-classification.md` Rule 1) routing every Ledger entry that surfaces on the `DomainEvent` bus through `format_record_id_for_event` and the partition helper for `fields_changed`. Phase 01 minimal Ledger does NOT emit `fields_changed` (only `{model, operation, record_id}`); the partition helper is forward-compatible per `rules/event-payload-classification.md` Rule 3 scope note.

### 3.3 Sunset clause for #596

Per `rules/zero-tolerance.md` Rule 4: workarounds for SDK gaps are BLOCKED; the upstream issue MUST be filed and the local implementation MUST have a sunset trigger.

**Sunset clause (proposed wire-format in code comment + `envoy.ledger.__init__.py` docstring):**

```
# SUNSET: this module replicates a subset of #596 TieredAuditDispatcher locally.
# Retire when:
#   1. terrene-foundation/kailash-py#596 closes with PR
#   2. The upstream surface implements: tiered dispatch (DEBUG/INFO/WARN/CRITICAL),
#      hash-chained Audit Anchors, SIEM export
#   3. The hash-chain shape is byte-identical to envoy.ledger.HashChainBuilder
#      (cross-verify with envoy-ledger-verify on a fresh Ledger; bytes must match)
# Migration: replace envoy.ledger.HashChainBuilder + HeadCommitment with
# kailash.trust.audit.TieredAuditDispatcher; keep envoy.ledger.canonical and
# envoy.ledger.export as Envoy-side adapters until Phase 04.
```

The sunset clause is structural per `rules/orphan-detection.md` Rule 3 ("Removed = Deleted, Not Deprecated"): when #596 lands, Envoy's local implementation is DELETED, not deprecated. This avoids the orphan-class failure where two implementations coexist and silently drift.

### 3.4 What is explicitly NOT Envoy-new-code

- **`AuditStore` extension or subclassing** — composition only; rules out cascading orphan-class risk.
- **A custom canonical-JSON library** — Envoy uses Python's `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":"))` plus `unicodedata.normalize("NFC", ...)` plus the timestamp-microsecond padding helper. No new C extension, no new library. The pinned byte-vector specification per #757/#756 IS the spec; Envoy follows it.
- **A custom Ed25519 implementation** — `kailash.trust.signing.crypto` only. Per `rules/independence.md` and standard practice, Envoy MUST NOT roll crypto.
- **An MCP / A2A / nexus integration in Phase 01** — out of EC-1 through EC-9 scope (per `02-mvp-objectives.md`); deferred to Phase 02+.
- **The independent verifier** — EC-9 deliverable; built in shard 7 in a separate codebase. By design, shard 6 must NOT share any source with shard 7.

---

## 4. Class structure sketch (interfaces only — no implementation)

```python
# envoy/ledger/__init__.py
from envoy.ledger.facade import EnvoyLedger, EnvoyLedgerError
from envoy.ledger.canonical import CanonicalJsonEncoder, canonical_dumps
from envoy.ledger.hash_chain import HashChainBuilder, EntryEnvelope
from envoy.ledger.head import HeadCommitment, HaltedByRollbackRecord
from envoy.ledger.lamport import LamportClock
from envoy.ledger.errors import (
    LedgerRollbackDetectedError, LedgerVerificationFailedError,
    LedgerSyncConflictError, EntryKeyDestroyedError,
    PhaseAOrphanDetectedError, LedgerConflictFloodError,
    LedgerHaltedError, LedgerAlgorithmMismatchError,
)

# envoy/ledger/facade.py
class EnvoyLedger:
    def __init__(self,
                 audit_store: "kailash.trust.audit.AuditStore",
                 signer: "kailash.trust.signing.crypto.Ed25519Signer",
                 classification_policy: "Optional[ClassificationPolicy]",
                 device_id: str,                   # sha256(genesis_pubkey)
                 tenant_id: Optional[str] = None) # rules/tenant-isolation.md Rule 5
                 -> None: ...

    def append(self, entry_type: str, content: dict, *,
               intent_id: Optional[str] = None,
               content_trust_level: str = "system",
               schema_version: str = "ledger-entry/1.0") -> str: ...
        # Returns entry_id. Wraps signing + canonical-JSON + audit_store.append +
        # head_commitment.update inside a df.transaction() boundary.
        # Filters record_id (if any) through format_record_id_for_event.
        # tenant_id persisted per rules/tenant-isolation.md Rule 5.

    def query(self, filter: dict, *,
              tenant_id: Optional[str] = None,
              limit: int = 1000) -> list[dict]: ...
        # tenant_id required for multi-principal Phase 03; default to instance tenant
        # for single-principal Phase 01.

    def verify_chain(self, *, start: int = 0,
                     end: Optional[int] = None) -> "VerificationReport": ...
        # Walks parent_hash chain; verifies each Ed25519 signature; segments per
        # MigrationAnnouncement boundary (specs/ledger.md §584-586). Raises
        # LedgerVerificationFailedError on first failure.

    def head_commitment(self) -> HeadCommitment: ...

    def export(self, format: Literal["json", "pdf"], *,
               output_path: str) -> str: ...
        # Writes the signed export bundle. Returns the bundle's receipt_hash.
        # Phase 01 EC-4 path; consumed by shard 7 verifier.

# envoy/ledger/canonical.py
def canonical_dumps(obj: dict) -> bytes: ...
    # NFC-normalize all strings; sort keys; UTF-8 encode with separators=(",", ":");
    # ensure_ascii=False; timestamp microsecond-padded per #731.

class CanonicalJsonEncoder: ...  # for streaming use

# envoy/ledger/hash_chain.py
@dataclass(frozen=True)
class EntryEnvelope:
    entry_id: str
    parent_hash: str
    sequence: int
    lamport_clock: dict        # {lamport_time, device_id, local_seq}
    timestamp: str             # ISO 8601 microsecond-padded
    type: str
    intent_id: Optional[str]
    content: dict
    content_trust_level: str
    description_content_hash: str
    description_content_hash_algorithm: str   # "sha256"
    signed_by: str
    signature_hex: str
    algorithm_identifier: dict
    # Wire shape per shard 5 fix R2-H-01 — 3-key spec form
    # `{sig, hash, shamir}` (`specs/trust-lineage.md` L24,
    # `specs/independent-verifier.md` L35); upstream's
    # `AlgorithmIdentifier().to_dict()` 1-key form is translated by
    # `TrustStoreAdapter._to_spec_wire_form()` at the single emission
    # point in shard 5. Ledger entries inherit the resolved 3-key form
    # transitively via the Trust Store adapter; no Ledger-side translation
    # is needed.
    schema_version: str        # "ledger-entry/1.0"

class HashChainBuilder:
    def build(self, *, prev_entry_id: str, sequence: int,
              lamport: LamportClock, content: dict, type: str,
              signing_key, ...) -> EntryEnvelope: ...

# envoy/ledger/head.py
@dataclass(frozen=True)
class HeadCommitment:
    head_sequence: int
    head_entry_id: str
    signed_at: str
    runtime_attestation: dict
    signature_hex: str

@dataclass(frozen=True)
class HaltedByRollbackRecord:                    # specs/ledger.md §HaltedByRollback
    last_known_good_head: dict                   # {sequence, entry_id}
    detected_head: dict
    detection_reason: Literal["sequence_decrease", "head_signature_mismatch",
                              "algorithm_identifier_downgrade"]
    runtime_identity: dict
    halted_at: str
    signed_by: str                               # "runtime_device_key"
    signature_hex: str

# envoy/ledger/lamport.py
@dataclass(frozen=True)
class LamportClock:
    lamport_time: int
    device_id: str           # sha256(device_pubkey)
    local_seq: int

    @classmethod
    def initial(cls, device_id: str) -> "LamportClock": ...

    def next(self, observed_max: int) -> "LamportClock": ...
        # lamport_time = max(observed_max, self.lamport_time) + 1
        # local_seq = self.local_seq + 1

    @staticmethod
    def sort_key(entry: EntryEnvelope) -> tuple:
        return (entry.lamport_clock["lamport_time"],
                entry.lamport_clock["device_id"],
                entry.lamport_clock["local_seq"])

# envoy/ledger/merge.py — Phase 01 INTERFACES ONLY (Phase 03 wires production)
def merge(branches: list[list[EntryEnvelope]]) -> tuple[list[EntryEnvelope],
                                                        list["LedgerConflictEntry"]]: ...

# envoy/ledger/export/cli.py
def export_main(argv: list[str]) -> int: ...    # argparse / Click entry point
```

Per `rules/facade-manager-detection.md` Rule 3, `EnvoyLedger.__init__` takes its dependencies (audit_store, signer, classification_policy) explicitly — no global lookup, no self-construction. This avoids the parallel-framework-instance hazard.

Per `rules/orphan-detection.md` Rule 1, the only production attribute exposed on a top-level facade is `EnvoyLedger`; every other class in the module is reached through it. Tier 2 wiring tests (§6) verify the facade is on the production hot path.

---

## 5. Integration points — every primitive writes to Ledger

The Ledger is the single primitive every other Phase 01 primitive depends on. This section names the integration shape per writer. Each writer's deep-dive shard (4, 5, 8, 9, 10, 11, 12, 16) imports `EnvoyLedger.append(...)` and is the production call site that satisfies the orphan-detection contract.

### 5.1 Phase 01 writers (in order of shard execution)

| Writer                                   | Owning shard | Entry types appended                                                                                          | Trigger                                                                                                                           |
| ---------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Envelope compiler                        | 4            | `RoleEnvelopeCreated`, `envelope_edit`                                                                        | First-time envelope creation; subsequent edits                                                                                    |
| Trust store                              | 5            | `GenesisRecord`, `DelegationRecord`, `RevocationRecord`, `KeyRotationRecord`, `KeyDestructionEvent`           | Genesis ritual at install; delegations created via Grant Moment; revocations via cascade; key rotations on schedule or compromise |
| Boundary Conversation                    | 8            | `ReasoningCommit`, `session_boundary_crossed`                                                                 | Each commit to a stable reasoning state during the 15-minute conversation                                                         |
| Authorship Score / posture gate          | 9            | `posture_change`                                                                                              | DELEGATING / AUTONOMOUS transition (BET-12 enforcement); annual decay; weekly review cycle                                        |
| Grant Moment                             | 10           | `grant_moment`, `PhaseARecord`, `PhaseBRecord`, `PhaseAOrphanResolution`                                      | User decision on out-of-envelope action; Phase A pre-execution; Phase B post-execution; orphan resolution at next session start   |
| Daily Digest                             | 11           | `ritual_completion`                                                                                           | Each completed digest delivery                                                                                                    |
| Budget tracker                           | 12           | `system_error` (on budget exhaustion before Grant Moment fires); ALSO drives Grant Moment threshold callbacks | Threshold callback (per #603 closure) → Grant Moment → standard `grant_moment` entry                                              |
| Channel adapters (CLI/Web + 6 messaging) | 16           | `channel_connected`, `channel_disconnected`                                                                   | Adapter lifecycle methods; OAuth grant or revoke; quota exhaustion; auth revocation                                               |

### 5.2 Cross-primitive read consumers

- **Daily Digest** (shard 11) is the dominant READER — `EnvoyLedger.query(filter={types: ["grant_moment", "channel_connected", ...], since: yesterday_morning})`. Digest aggregation logic + back-fill semantics (per EC-3 acceptance gate) live in shard 11; shard 6 only guarantees the query primitive returns deterministic ordering on `(sequence, lamport_time)`.
- **Independent verifier** (shard 7, EC-9) reads `EnvoyLedger.export(format="json")` output. The export bundle is the only artifact the verifier ever touches; the verifier MUST NOT import `envoy.ledger.*`.
- **Authorship Score** (shard 9) reads posture transition history + grant approval/decline history to compute the score per `specs/authorship-score.md`. The query is read-only against the Ledger.
- **Grant Moment cascade revocation** (shard 10) reads delegation lineage from the Ledger (via Trust store's `cascade_revoke`) to determine descendant grants needing revocation.

### 5.3 The 'every primitive' invariant — what makes the Ledger structurally hardest

Every other Phase 01 primitive depends on `EnvoyLedger.append()`. A change to the canonical-JSON shape, the entry-envelope schema, or the signing routine cascades to every writer's serialization assumption AND to the verifier's deserialization assumption. Per `rules/autonomous-execution.md` § Per-Session Capacity Budget, the Ledger's invariants (canonical-JSON byte determinism; timestamp microsecond determinism; tenant_id persistence; classified-PK redaction at emit; chain-shape stability) are the structural reason this shard exceeds the per-session capacity for any combined-with-another-primitive shard. They MUST be locked at Phase 01 release: every downstream primitive's Tier 2 test asserts byte-equality against fixtures generated against the locked shape.

---

## 6. Tier 2 / Tier 3 test surface

Per `rules/testing.md` § 3-Tier Testing + § Audit Mode Rules (no mocking at Tier 2; real infrastructure recommended at Tier 2/3), the Ledger primitive's test surface MUST exercise real SQLite + real Ed25519 + real time anchors (where Phase 02-deferred surface is exercised at all in P01).

Per `rules/orphan-detection.md` Rule 2 + Rule 2a + `rules/facade-manager-detection.md` Rule 1 + Rule 2: every wired manager + crypto-pair surface MUST have a Tier 2 wiring test that imports through the facade and asserts an externally-observable effect.

### 6.1 Tier 2 wiring tests (real SQLite + real Ed25519)

| Test file                                                               | What it exercises                                                                                                                                                                                                                                                                                                                                                                               |
| ----------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/integration/test_envoy_ledger_wiring.py`                         | Per `rules/facade-manager-detection.md` Rule 2 naming convention: imports `from envoy.ledger import EnvoyLedger`, constructs against a real SQLite DB + real keypair, calls `.append(...)` for one of each major entry type, asserts the audit_store table contains the row, the row's `entry_id` round-trips canonical-JSON, and the chain `verify_chain()` returns success.                   |
| `tests/integration/test_envoy_ledger_crypto_round_trip.py`              | Per `rules/orphan-detection.md` Rule 2a (crypto-pair round-trip THROUGH the facade): `EnvoyLedger.append(content)` followed by `EnvoyLedger.verify_chain()` succeeds; modifying the stored content byte-by-byte fails verification. This is the structural defense against the "encrypt uses GCM, decrypt uses CBC drift" failure mode adapted to "append uses Ed25519, verify uses RSA drift." |
| `tests/integration/test_envoy_ledger_canonical_json_byte_identity.py`   | Two Python processes (different OS, different timezone, different locale, different Python minor version) emit the same logical entry; the bytes coming out of `canonical_dumps(envelope)` MUST be identical. This is the EC-9 cross-implementation invariant tested as the more-tractable cross-process invariant.                                                                             |
| `tests/integration/test_envoy_ledger_classified_record_id_redaction.py` | Per `rules/event-payload-classification.md` Rule 4: append a Ledger entry whose content references a classified-PK model (e.g. `Account` keyed by classified `email`); subscribe to the DomainEvent bus; assert the captured event's `record_id` is `sha256:XXXXXXXX`-prefixed; assert the raw email does NOT appear anywhere in `repr(payload)`.                                               |
| `tests/integration/test_envoy_ledger_tenant_id_persisted.py`            | Per `rules/tenant-isolation.md` Rule 5: append entries with `tenant_id="t1"` and `tenant_id="t2"` interleaved; query with `tenant_id="t1"` returns only t1 entries; the `tenant_id` column is indexed (verify via `EXPLAIN QUERY PLAN`). Forensic-query test.                                                                                                                                   |
| `tests/integration/test_envoy_ledger_atomic_append_under_failure.py`    | Per #707/#711: kill the process between the audit_row write and the head_commitment update; on restart, `verify_chain()` correctly identifies the (no entry written, head consistent) state. The transaction context manager IS the durable guarantee.                                                                                                                                          |
| `tests/integration/test_envoy_ledger_head_commitment_monotonic.py`      | Append N entries; head_sequence rises monotonically; force a stale head_commitment write; `LedgerRollbackDetectedError` raises; `HaltedByRollbackRecord` is appended BEFORE further writes refuse; subsequent `.append()` raises `LedgerHaltedError`.                                                                                                                                           |
| `tests/integration/test_envoy_ledger_phase_a_b_intent_id_link.py`       | `PhaseARecord` then `PhaseBRecord` linked by same `intent_id`; query by `intent_id` returns both; orphaned Phase A (no Phase B within 30d) surfaces at next session start as `PhaseAOrphanResolution`.                                                                                                                                                                                          |
| `tests/integration/test_envoy_ledger_segment_boundary.py`               | Append a `MigrationAnnouncement`; subsequent entries carry the new `algorithm_identifier`; chain verification dispatches per segment; entry with mismatched algorithm raises `LedgerAlgorithmMismatchError`.                                                                                                                                                                                    |
| `tests/integration/test_envoy_ledger_export_round_trip.py`              | `envoy ledger export --format json` writes a bundle; reading the bundle via `json.loads` produces a list whose entries match the Ledger's in-memory entries by `entry_id`; the bundle's `receipt_hash` verifies. Phase 01 EC-4 acceptance test.                                                                                                                                                 |
| `tests/integration/test_envoy_ledger_lamport_three_field_sort.py`       | (Phase 01 covers single-device; multi-device is Phase 03) Construct synthetic two-device entries; `merge(branches)` sorts on `(lamport_time, device_id, local_seq)`; assert the merged order matches the spec example.                                                                                                                                                                          |
| `tests/integration/test_envoy_ledger_pytest_xdist_safe.py`              | Per `rules/testing.md` § Env-Var Test Isolation: any test in the suite that mutates `ENVOY_LEDGER_*` env vars holds the module-scope lock; verifies the lock is honored under `pytest-xdist -n auto`.                                                                                                                                                                                           |

### 6.2 Tier 3 tests (cross-OS portability, full tampering battery, EC-9 gate)

| Test file                                                    | What it exercises                                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `tests/e2e/test_envoy_ledger_cross_os_byte_identity.py`      | Run the same `EnvoyLedger.append(...)` sequence on macOS + Linux + Windows (CI matrix); export each; the JSON exports MUST be byte-identical (modulo `signed_by` device_id which is per-device). The chain hash sequence MUST be identical. EC-9 cross-implementation invariant tested at OS granularity in P01.                           |
| `tests/e2e/test_envoy_ledger_tampering_battery.py`           | EC-4 acceptance gate. For an N=1000-entry export bundle, run the verifier (shard 7) over (a) untampered bundle, (b) single-bit flip in entry K's `content`, (c) entry K removed entirely, (d) entry K duplicated, (e) entries K and K+1 swapped. The verifier MUST detect every tampering form and identify the failing entry index.       |
| `tests/e2e/test_envoy_ledger_independent_verifier_ec9.py`    | EC-9 acceptance gate. Spawn the shard-7 verifier (separate codebase, ideally separate language; minimum a different-agent Python package per `02-mvp-objectives.md` EC-9 acceptance gate) against an Envoy-produced export. Verifier passes; tampering battery from the previous test still detects all forms via the verifier's own code. |
| `tests/e2e/test_envoy_ledger_pdf_receipt_hash_links_json.py` | Export PDF; PDF embeds `receipt_hash`; the receipt_hash equals the SHA-256 of the JSON bundle. Non-Envoy PDF reader (`pypdf` or similar minimal lib) extracts the receipt_hash without executing Envoy code.                                                                                                                               |

### 6.3 Test surface NOT in Phase 01 (deferred to later phases)

- Multi-device merge integration (`tests/e2e/test_offline_multi_device_reconciliation.py` per `specs/ledger-merge.md` line 89) — Phase 03 deliverable.
- Remote time-anchor quorum (`tests/integration/test_remote_time_anchor_quorum_reached.py` per `specs/remote-time-anchor.md`) — Phase 02 deliverable per `specs/remote-time-anchor.md` line 14.
- Post-quantum migration (`tests/integration/test_post_quantum_migration_path.py` per `specs/ledger.md` line 631) — Phase 04 deliverable.

---

## 7. Frozen-spec ambiguity check

Per `01-shard-plan.md` § 4 failure-mode protocol: if a primitive deep-dive surfaces a HIGH gap in the frozen spec, STOP the deep-dive; convene MUST-Rule-5b sweep before continuing.

This shard surfaced **NO HIGH-severity ambiguity** in `specs/ledger.md`, `specs/ledger-merge.md`, or `specs/remote-time-anchor.md` that the Phase 00 redteam did not already close.

The following items were considered and dispositioned:

| Item                                                                                                                             | Severity (this shard's assessment) | Disposition                                                                                                                                                                                                                                                                                             |
| -------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `specs/ledger.md` § "Open questions" line 642: "CRDT canonical ordering (Lamport vs VClock) — Lamport chosen; revisit Phase 03." | LOW                                | Spec is explicit: Lamport in P01, VClock revisit in P03. No ambiguity to resolve at MVP scale.                                                                                                                                                                                                          |
| `specs/ledger.md` line 643: "Per-entry key destruction under master_key leak — documented residual; Phase 04 per-segment keys."  | LOW                                | Residual risk is documented; Phase 04 mitigation. Nothing to resolve in P01.                                                                                                                                                                                                                            |
| `specs/ledger.md` line 644: "Verifier language — Python community default; Rust variant Phase 04."                               | LOW                                | EC-9 explicitly accepts "Python (different agent / different package) or Rust" per `02-mvp-objectives.md` EC-9 acceptance gate. Spec aligns with EC.                                                                                                                                                    |
| `specs/ledger-merge.md` open questions 1–5                                                                                       | LOW                                | All five are Phase 03+ refinements (conflict-flood ceiling tuning, semantic batching threshold, cross-device key rotation, N-device perf). No P01 implementation decision blocked.                                                                                                                      |
| Lamport `device_id` derivation                                                                                                   | LOW                                | `specs/ledger.md` line 39 specifies `sha256(device binding pubkey)`. The "device binding pubkey" is the Genesis-attested device key per `specs/trust-lineage.md` (referenced via `GenesisDeviceTransferRecord` in `specs/ledger.md` line 50). Single-device P01 derives once at install; no ambiguity.  |
| `system_error` fault_fingerprint stability                                                                                       | LOW                                | `specs/ledger.md` line 561 says "stable hash of fault_class+caller_site". Implementation: `sha256(fault_class + ":" + module_qualname + ":" + line)`. The exact fingerprint formula is implementation latitude; the key stability invariant is "same fault clusters under same fingerprint" (line 569). |
| Phase 01 single-device interaction with `ledger-merge`                                                                           | LOW                                | Recorded explicitly in §1.2 above as a Phase 03 wiring with Phase 01 architectural-contract-only ship. This is a scoping decision not a spec ambiguity.                                                                                                                                                 |

**Conclusion:** zero HIGH findings; zero MED findings that block implementation. Phase 01 implementation can proceed against `specs/ledger.md` as frozen. No `01-shard-plan.md` § 4 escalation needed; no MUST-Rule-5b sweep needed.

The audit-trail shape closure (#757 / #756 / #731 / #707 / #711 / #672 / #750) materially improved Phase 01's structural position relative to the Phase 00 survey baseline. Six of seven indirect closures shipped between 2026-04-21 and 2026-05-03; the only OPEN issue affecting this primitive (#596 TieredAuditDispatcher) is structurally addressable as Envoy-new-code with sunset clause per `rules/zero-tolerance.md` Rule 4.

---

## 8. Cross-references

- **Frozen specs (DO NOT EDIT):**
  - `specs/ledger.md` § "Entry envelope schema" lines 14–34 (chain shape contract)
  - `specs/ledger.md` § "Entry types" lines 47–91 (35 type producer manifest)
  - `specs/ledger.md` § "Two-phase signing (T-004)" lines 519–523
  - `specs/ledger.md` § "Head commitment (T-100)" lines 525–548
  - `specs/ledger.md` § "Retention + GDPR (T-003)" lines 577–582
  - `specs/ledger.md` § "Segment boundary on MigrationAnnouncement" lines 584–586
  - `specs/ledger.md` § "Export + independent verifier" lines 588–592
  - `specs/ledger.md` § "Error taxonomy" lines 595–607
  - `specs/ledger-merge.md` § "Algorithm" lines 14–31 + § "Conflict-flood rate-limit" lines 41–45
  - `specs/remote-time-anchor.md` line 14 (Phase 02 deferral)
- **Phase 01 analysis:**
  - `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 2 (sharding) + § 4 (failure-mode protocol)
  - `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` EC-3 (Daily Digest reads), EC-4 (verifiable export), EC-9 (independent verifier separately codebased)
  - `workspaces/phase-01-mvp/01-analysis/03-kailash-py-mvp-readiness.md` § 3 row 3 + § 4 row 1 (Envoy-new-code commitment) + § 5 (verification protocol)
  - `workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` (re-derivation prohibition)
- **Phase 00 verified citations:**
  - `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` § item 4 lines 113–129 (TieredAuditDispatcher absent — #596)
  - `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` § item 12 lines 352–376 (`format_record_id_for_event` present)
  - `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` § item 17 lines 498–537 (Trust Lineage primitives + Ed25519 signing)
  - `workspaces/phase-00-alignment/01-analysis/03-primitive-reconciliation.md` § 2 row 4 (TieredAuditDispatcher absent on BOTH SDK sides; ISS-06/07/08)
- **Indirect-closure issue refs (verified through readiness doc § 2.2):**
  - #757, #756 — Unicode byte-vector pinning for audit-chain canonical-input + TraceEvent canonical-JSON
  - #731 — TraceEvent timestamp microsecond padding cross-SDK
  - #707, #711 — `df.transaction()` + `db.transactions_sync.begin()` context manager
  - #672 — Python `format_record_id_for_event` cross-SDK with kailash-rs BP-048
  - #750 — DataFlow Express update/delete silently no-op on SQLite (CRITICAL — Envoy uses SQLite)
- **OPEN upstream:** #596 — TieredAuditDispatcher (Envoy-new-code with sunset clause per `rules/zero-tolerance.md` Rule 4)
- **Rules cited:**
  - `rules/zero-tolerance.md` Rule 4 (no workarounds for SDK gaps; file upstream + implement to spec)
  - `rules/orphan-detection.md` Rule 1 + Rule 2 + Rule 2a + Rule 3 (facade hot-path; Tier 2 wiring; crypto-pair round-trip; deletion not deprecation)
  - `rules/facade-manager-detection.md` Rule 1 + Rule 2 + Rule 3 (Tier 2 test naming; explicit framework dependency)
  - `rules/event-payload-classification.md` Rule 1 + Rule 2 + Rule 4 (single-point filter at emitter; classified-PK hash; end-to-end test)
  - `rules/tenant-isolation.md` Rule 5 (audit rows persist tenant_id, indexed)
  - `rules/dataflow-identifier-safety.md` Rule 1 (every dynamic DDL identifier through `quote_identifier`; relevant if Ledger SQLite schema is dynamically constructed)
  - `rules/specs-authority.md` Rule 4 (phase commands read specs before acting; this shard reads three specs by path + section)
  - `rules/autonomous-execution.md` § Per-Session Capacity Budget (5 invariants; 4 cross-primitive references; within budget)
  - `rules/testing.md` § 3-Tier Testing + § Env-Var Test Isolation + § Audit Mode Rules (real infra at Tier 2/3; xdist-safe; re-derive coverage in audit)
- **Forward references (next shards):**
  - shard 7 — independent verifier (consumes the export bundle this shard produces)
  - shard 9 — Authorship Score (reads posture_change history via Ledger query)
  - shard 10 — Grant Moment (writes grant_moment, PhaseARecord, PhaseBRecord, PhaseAOrphanResolution)
  - shard 11 — Daily Digest (reads via Ledger query; back-fill semantics)
  - shard 16 — Channel adapters (write channel_connected / channel_disconnected)
  - shard 19 — pipx distribution (the `envoy ledger export` CLI entry point)
