# 04 — Envoy Ledger

**Document status:** draft v1 — ready for `/redteam`
**Scope:** Hash chain format; two-phase signing (Phase A intent / Phase B outcome); per-entry encryption; tombstone + per-entry key destruction; CRDT merge protocol (T-101); head commitment (T-100); conflict resolution; export + independent verifier contract.
**Sources:** doc 00 v3, doc 02 v3 (envelope_edit entries + content_trust_level), doc 03 v2 (Trust Lineage entries), doc 05 v1 (runtime operations), doc 09 v3 (T-003 retention, T-004 two-phase signing, T-100 rollback, T-101 fork, T-102 replay, T-104 version binding).

---

## 1. Purpose

The Envoy Ledger is the hash-chained append-only record that the user inspects, diffs, commits, and shares. Per doc 00 v3 §2.3 item 4: _"The audit log is not a compliance artifact — it is the Envoy Ledger, a daily-use personal record."_

### In scope

- Ledger entry canonical JSON form (extends doc 02 §14.1 JCS)
- Hash-chain structure + `parent_hash` linkage
- Head commitment monotonic invariant (T-100)
- Two-phase signing lifecycle Ledger side (T-004)
- Per-entry encryption + key destruction (T-003 GDPR)
- Tombstone semantics (T-003)
- CRDT merge protocol (T-101)
- Conflict resolution UX integration
- Export + PDF/JSON + signature envelope
- Independent reference verifier contract
- Nonce tracking (T-102) cross-reference to doc 03 §6.1
- Segment boundary on MigrationAnnouncement (doc 03 §8.3)

### Out of scope

- Delegation Record / Genesis Record schemas (doc 03).
- EnvelopeConfig schema (doc 02).
- Trust Vault encryption at container level (doc 10).
- Runtime primitives that invoke ledger_append / ledger_query (doc 05).

---

## 2. Entry canonical form

Every Ledger entry follows this envelope (per doc 10 §4.3):

```json
{
  "entry_id": "sha256:<hash of canonical form excluding signature>",
  "parent_hash": "sha256:<previous entry_id>",
  "sequence": 4721,
  "lamport_clock": {"device_id": "sha256:<pubkey>", "local_seq": 523},
  "timestamp": "iso8601",
  "type": "<entry type per doc 10 §4.4>",
  "content": {<type-specific payload>},
  "content_trust_level": "user-authored | tool-output | channel-message | derived-external | heartbeat | system | sub-agent | llm-authored",
  "description_content_hash": "sha256:<hex>",
  "description_content_hash_algorithm": "sha256",
  "signed_by": "<device_key | genesis_key — type-specific>",
  "signature_hex": "<ed25519 signature over canonical form excluding signature_hex>",
  "algorithm_identifier": {<full identifier>},
  "schema_version": "ledger-entry/1.0"
}
```

**Canonical form:** JCS RFC 8785 + NFC per doc 02 §14.1. Signature covers canonical form of entry minus `signature_hex`.

**`entry_id`** content-addressed: sha256 over canonical form minus `signature_hex` minus `entry_id` itself.

---

## 3. Hash chain

### 3.1 Structure

Linear chain: every entry's `parent_hash` references the previous entry's `entry_id`. GenesisRecord is the anchor (`parent_hash = "sha256:0"`).

### 3.2 Per-device branching under offline operation

During offline multi-device operation:

- Each device maintains a local tip.
- On sync, merge via CRDT protocol (§7).
- Post-merge, the Ledger is a DAG, not a strict linear chain. Materialized view flattens via Lamport ordering.

### 3.3 Verification algorithm

```python
def verify_ledger_chain(ledger, start=GENESIS, end=HEAD):
    entry = get_entry(start)
    while entry != end:
        # 1. Parent hash check
        parent = get_entry(entry.parent_hash)
        assert parent.entry_id == entry.parent_hash

        # 2. Entry-id hash check
        recomputed = sha256(canonical_form(entry, exclude=["signature_hex", "entry_id"]))
        assert recomputed == entry.entry_id

        # 3. Signature verify
        pubkey = resolve_signer(entry.signed_by)  # device_key OR genesis_key
        verify_ed25519(pubkey, canonical_form(entry, exclude=["signature_hex"]), entry.signature_hex)

        # 4. Algorithm-identifier compatibility
        assert entry.algorithm_identifier in acceptable_algorithms(entry.timestamp)

        # 5. Content_trust_level valid enum value
        assert entry.content_trust_level in VALID_TRUST_LEVELS

        # 6. Monotonic sequence
        assert entry.sequence == parent.sequence + 1 OR entry is CRDT-merge-child

        entry = next_entry(entry)
    return VerificationOk
```

---

## 4. Head commitment (T-100 rollback defense)

### 4.1 Format

```json
{
  "type": "HeadCommitment",
  "head_entry_id": "sha256:<latest entry_id>",
  "head_sequence": 4721,
  "head_timestamp": "iso8601",
  "committed_at": "iso8601",
  "signed_by_runtime_device_key": "sha256:<pubkey>",
  "signature_hex": "<ed25519 signature>"
}
```

Signed by runtime device key (distinct from Genesis, per doc 03 §6.3 two head-commitments distinction).

### 4.2 Sync protocol

Every sync operation carries:

- Most recent `HeadCommitment` signed by this device.
- Chain-head-commitment signed by Genesis (per doc 03 §6.3).

On receive, client validates:

1. `HeadCommitment.head_sequence ≥ last_known_head_sequence`. If LESS → `LedgerRollbackDetectedError`; sync rejected.
2. `chain_head_commitment` valid per doc 03 §6.3 (Trust Lineage chain tip).
3. Device-key signature valid.

### 4.3 Recovery

On suspected rollback:

- Client alerts user via channel notification.
- User can inspect sync target manually; compare committed vs. stored head.
- Force-sync from a trusted device source.

---

## 5. Two-phase signing (T-004)

Per doc 05 §6 + doc 00 v3 §8 Test-2.

### 5.1 Phase A entry — tool-call intent

```json
{
  ...ledger envelope...,
  "type": "PhaseARecord",
  "content": {
    "intent_id": "sha256:<content hash>",
    "agent_id": "<runtime:session>",
    "tool_name": "send_email",
    "arguments_canonical": {<JCS-canonical arguments>},
    "envelope_snapshot_hash": "sha256:<effective envelope>",
    "delegation_record_hash": "sha256:<delegation that authorizes>",
    "proposed_at": "iso8601",
    "nonce": "<32 hex bytes>"
  },
  "content_trust_level": "system",
  "signed_by": "<delegation_key_pubkey_hex>",
  "signature_hex": "<signature>"
}
```

### 5.2 Phase B entry — tool-call outcome

```json
{
  ...ledger envelope...,
  "type": "PhaseBRecord",
  "content": {
    "intent_id": "<links to Phase A>",
    "outcome_type": "success | error | timeout | halted_by_rollback",
    "result_payload_hash": "sha256:<hash>",
    "completed_at": "iso8601",
    "elapsed_ms": 345
  },
  "content_trust_level": "system",
  "signed_by": "<runtime_device_key_pubkey>",
  "signature_hex": "<signature>"
}
```

**Linking:** PhaseB's `content.intent_id` references PhaseA's `content.intent_id`. Verification walks forward to find matching PhaseB.

### 5.3 Orphan resolution

Per doc 05 §6.3 — on startup, query Ledger for PhaseA entries without matching PhaseB within orphan-resolution window (30 days default). Orphans surface to user at next session start.

**PhaseA-orphan-resolution Ledger entry:**

```json
{
  "type": "PhaseAOrphanResolution",
  "content": {
    "orphaned_intent_id": "sha256:...",
    "resolution": "retry | record_as_failed | investigate",
    "user_rationale": "<user-authored text>",
    "resolved_at": "iso8601"
  },
  "content_trust_level": "user-authored",
  "signed_by": "<genesis_key>",
  "signature_hex": "..."
}
```

---

## 6. Per-entry encryption + key destruction

### 6.1 Per-entry key derivation

```text
per_entry_key = HKDF-SHA-256(master_key, info="ledger-entry:" + entry_id)
```

Master key lives in Trust Vault (doc 10 §2). Per-entry keys are derived lazily on read; stored briefly in memory; zeroed after use.

### 6.2 Encryption

Entry `content` field encrypted with per-entry key via AES-256-GCM. Other fields (entry_id, parent_hash, sequence, timestamp, type, content_trust_level, description_content_hash, signed_by, signature_hex, algorithm_identifier, schema_version) are plaintext — needed for chain verification without full decryption.

### 6.3 Key destruction (GDPR erasure — T-003)

```python
def destroy_entry_key(entry_id):
    per_entry_key = HKDF(master_key, info="ledger-entry:" + entry_id)
    key_destruction_record = LedgerEntry(
        type="EntryKeyDestruction",
        content={"destroyed_entry_id": entry_id, "destroyed_at": now()},
        signed_by=genesis_key
    )
    ledger.append(key_destruction_record)
    # The per_entry_key is NOT stored anywhere; it's always re-derived.
    # But after adding the destruction record, future derivations are BLOCKED.
    # This requires a derivation-override table: "destroyed_entries" set.
    destroyed_entries.add(entry_id)
```

**Implementation note:** since per-entry keys are derived from master_key deterministically, "destruction" is actually the addition of `entry_id` to a `destroyed_entries` set in Trust Vault. Any decryption attempt on a destroyed entry fails with `EntryKeyDestroyedError`. The chain integrity is preserved (hash chain still verifies); only content is inaccessible.

**Caveat:** master_key is still the derivation source. If master_key leaks, destroyed entries become decryptable unless the `destroyed_entries` set is also respected. Defense: destruction is ALWAYS accompanied by the signed `EntryKeyDestruction` record, which any honest reader must honor. Attacker with leaked master_key but without the Ledger's destruction record cannot distinguish destroyed from non-destroyed entries — but if they have both master and Ledger, they can bypass. This is a residual risk documented in doc 09 v3 T-003.

**Stronger variant (Phase 04):** "per-segment keys" — rotate master every N entries; destroying a segment's key permanently destroys all its content. Phase 01-03 uses the simpler destroyed_entries variant.

### 6.4 Tombstone variant

Weaker than key destruction; preserves content_trust_level + timestamp + signer but replaces `content` with:

```json
{
  "type": "TOMBSTONED",
  "original_entry_type": "<type>",
  "tombstoned_at": "iso8601",
  "tombstoned_reason": "<user-authored>",
  "tombstoned_signed_by": "<genesis>"
}
```

Tombstone chain integrity: `entry_id` remains the hash of the ORIGINAL content (pre-tombstone). Verifiers cannot distinguish tombstoned from non-tombstoned at chain level. Readers see `content.type == "TOMBSTONED"` as content reads.

---

## 7. CRDT merge protocol (T-101)

### 7.1 Problem statement

Two or more devices operate offline; each writes local entries. On sync, merge is required. Without a protocol, reconciliation is ambiguous.

### 7.2 Algorithm

```text
merge(branches: list[Ledger]) -> Ledger:
  # 1. Collect all entries across branches
  all_entries = union(branch.entries for branch in branches)

  # 2. Canonical order: Lamport clock, then device_id lexicographic, then local_seq
  sorted_entries = sort(all_entries, key=lambda e: (e.lamport_clock.lamport_time, e.lamport_clock.device_id, e.lamport_clock.local_seq))

  # 3. Detect conflicts:
  conflicts = []
  for entry in sorted_entries:
    # Same-nonce conflicts (would-be replay if on same device)
    if entry.nonce seen before in sorted_entries:
      conflicts.append(NonceConflict(entry, previous_entry_with_same_nonce))
    # Same-intent-id Phase A conflicts
    if entry.type == "PhaseARecord" and intent_id seen before:
      conflicts.append(IntentIdConflict(entry, previous))
    # Revocation-vs-descendant-signing conflicts (§5.5 doc 03)
    if entry.type == "RevocationRecord" and there's a later entry referencing the revoked delegation_id:
      conflicts.append(RevocationRaceConflict(entry, later))

  # 4. Re-link parent_hash in merged order
  for i, entry in enumerate(sorted_entries):
    if i > 0:
      merged_entry = entry.copy()
      merged_entry.parent_hash = sorted_entries[i-1].entry_id
      # Re-verify signature DOES NOT invalidate — signature covered ORIGINAL parent_hash
      # Solution: merged entries carry BOTH `original_parent_hash` (signed) and `merged_parent_hash` (derived)
      merged_entry.original_parent_hash = entry.parent_hash
      merged_entry.merged_parent_hash = sorted_entries[i-1].entry_id

  # 5. Write conflicts as LedgerConflictEntry records
  for conflict in conflicts:
    ledger.append(LedgerConflictEntry(conflict))

  # 6. Update head commitment; sign
  return merged_ledger
```

### 7.3 `LedgerConflictEntry`

```json
{
  "type": "LedgerConflictEntry",
  "content": {
    "conflict_type": "NonceConflict | IntentIdConflict | RevocationRaceConflict",
    "entry_a_id": "sha256:...",
    "entry_b_id": "sha256:...",
    "discovered_at": "iso8601",
    "resolution": "pending | auto_resolved | user_resolved",
    "resolution_detail": "<optional text>"
  },
  "content_trust_level": "system",
  "signed_by": "<runtime_device_key>"
}
```

### 7.4 Conflict-flood rate-limit (doc 09 T-101 R2-H1)

- Per-principal conflict cap: 20 unresolved; additional queued.
- UI batches by semantic similarity.
- If a principal exceeds cap, further sync from that principal's device(s) suspends until existing conflicts resolved.

### 7.5 Resolution UX

User sees conflicts at next session start. Each conflict offers resolution options:

- **NonceConflict:** the two entries are inspected; user chooses which to keep (the other tombstoned with conflict rationale).
- **IntentIdConflict:** both Phase A records visible; user chooses canonical or cancels both.
- **RevocationRaceConflict:** revocation wins automatically (descendant capability was revoked); UX notifies user.

---

## 8. Segment boundary on MigrationAnnouncement

Per doc 03 §8.3. A Ledger is partitioned into **segments** by `MigrationAnnouncement` entries:

```text
[Segment 1: algorithm_identifier = {ed25519, sha256}]
  entries using original algorithms
[MigrationAnnouncement: switch to {ed25519-v2, sha3-256}]
[Segment 2: algorithm_identifier = {ed25519-v2, sha3-256}]
  entries using new algorithms
```

**Verification dispatch:** chain verification walks through both segments. Each segment's entries verify under their segment's algorithm. Cross-segment `parent_hash` linkage uses the NEWER segment's hash algorithm (i.e. the MigrationAnnouncement entry's `entry_id` is computed under new algorithm; its `parent_hash` is under old algorithm).

---

## 9. Export + PDF/JSON

### 9.1 Export format

`envoy ledger export --format json` produces:

```json
{
  "export_version": "envoy-ledger-export/1.0",
  "principal_genesis_id": "sha256:...",
  "export_range": {"from_sequence": 0, "to_sequence": 4721},
  "exported_at": "iso8601",
  "entries": [<Ledger entries, each fully-formed>],
  "head_commitment": {...},
  "chain_head_commitment": {...},
  "export_signature": "<signed by user's Genesis key>"
}
```

**`envoy ledger export --format pdf`** — human-readable summary + cryptographic receipt hash on final page. Not verifiable directly (PDF format ≠ canonical JSON) but carries `receipt_hash` pointing to JSON export stored alongside.

### 9.2 Per-entry plaintext option

By default, export preserves per-entry encryption. User may request plaintext export with explicit Grant Moment (`envoy ledger export --decrypt`); plaintext export carries a warning header + separate signature over decrypted content.

---

## 10. Independent reference verifier

Per doc 00 v3 §3.3 new-code: "Independent reference-verifier tool (separate codebase than the writer)."

### 10.1 Tool contract

`envoy-ledger-verify` is a separate Python package (distinct from kailash-py/kailash-rs-bindings codebases). Input: Ledger export JSON. Output: verification report.

### 10.2 Verifier algorithm

```python
def verify_ledger_export(export: LedgerExport) -> VerificationReport:
    # 1. Verify export signature
    assert verify_ed25519(export.principal_genesis_id, canonical_form(export minus export_signature), export.export_signature)

    # 2. Walk chain
    assert export.entries[0].type == "GenesisRecord"
    for i in range(1, len(export.entries)):
        prev = export.entries[i-1]
        curr = export.entries[i]
        assert curr.parent_hash == prev.entry_id
        assert curr.entry_id == sha256(canonical_form(curr, exclude=["signature_hex", "entry_id"]))
        # 3. Verify each entry signature
        pubkey = resolve_signer(curr.signed_by, export)
        assert verify_ed25519(pubkey, canonical_form(curr, exclude="signature_hex"), curr.signature_hex)
        # 4. Algorithm-identifier acceptable
        assert curr.algorithm_identifier in acceptable_algorithms(curr.timestamp)

    # 5. Head commitments
    assert head_commitment.head_entry_id == export.entries[-1].entry_id

    return VerificationReport(ok=True, entry_count=len(export.entries), ...)
```

### 10.3 Release

Foundation-Verified open-source. Published to PyPI as `envoy-ledger-verify`. Phase 01 exit gate per doc 00 v3 §3.1.

---

## 11. Cross-references

- **doc 00 v3** — §3.3 independent verifier new-code, §2.3 Ledger as primary surface.
- **doc 02 v3** — canonical JSON (§14.1), envelope_edit entries, content_trust_level enum.
- **doc 03 v2** — Trust Lineage entries (GenesisRecord, DelegationRecord, RevocationRecord, KeyRotationRecord, MigrationAnnouncement, FoundationAllowlistOverrideRecord), chain_head_commitment complement.
- **doc 05** — runtime operations (ledger_append, ledger_query, ledger_verify_chain, head_commitment).
- **doc 09 v3** — T-003 retention (§6 tombstone + key destruction), T-004 two-phase signing (§5), T-100 rollback (§4 head commitment), T-101 fork (§7 CRDT merge), T-102 replay (nonce tracking — deferred to doc 03), T-104 envelope-version binding.
- **doc 10** — Trust Vault + per-entry key derivation + destroyed_entries set.

---

## 12. Open questions

1. CRDT merge canonicality — proposed Lamport-time-then-device-id ordering; alternative: VClock. Pick one.
2. Conflict flood of 20 entries — user overwhelm threshold. Calibrate via Phase 03 Shared Household pilot.
3. Independent verifier language — Python Foundation-community-standard. Alternative: Rust variant for additional assurance. Phase 04 consideration.
4. Per-entry encryption master_key leak scenario — acknowledged residual. Stronger per-segment keys in Phase 04?
5. Export format long-term stability — format drift across Envoy versions. Suggest immutable `export_version` + migration tooling.
6. Ledger size at scale — 400k entries in 10y. Pagination + chunked sync needed. Phase 02 optimization.

---

**End of doc 04 v1.**
