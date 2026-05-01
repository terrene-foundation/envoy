# ledger-merge

## Purpose

CRDT-style merge protocol for offline multi-device Ledger reconciliation (T-101).

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/04-ledger.md v1 §7`.
- **Threats mitigated:** T-101 fork reconciliation + conflict-flood defense.
- **BETs tested:** BET-6 contract parity under multi-device.

## Algorithm

```python
def merge(branches):
    all_entries = union(branch.entries for branch in branches)
    sorted_entries = sort(all_entries, key=lambda e: (e.lamport_clock.lamport_time, e.lamport_clock.device_id, e.lamport_clock.local_seq))
    conflicts = []
    for entry in sorted_entries:
        if entry.nonce seen before: conflicts.append(NonceConflict(...))
        if entry.type == "PhaseARecord" and intent_id seen: conflicts.append(IntentIdConflict(...))
        if entry.type == "RevocationRecord" and later-entry-references-revoked-delegation: conflicts.append(RevocationRaceConflict(...))
    # Re-link parent_hash in merged order
    for i, entry in enumerate(sorted_entries[1:], start=1):
        entry.merged_parent_hash = sorted_entries[i-1].entry_id
        entry.original_parent_hash = entry.parent_hash  # signed
    for conflict in conflicts:
        ledger.append(LedgerConflictEntry(conflict))
    return merged_ledger
```

Each entry carries `original_parent_hash` (signed) + `merged_parent_hash` (derived).

## Conflict types

- **NonceConflict** — same nonce on different devices.
- **IntentIdConflict** — same intent_id Phase A on different devices.
- **RevocationRaceConflict** — revocation + later-descendant-signing race.

## Conflict-flood rate-limit (R2-H1 fix)

- Per-principal cap: 20 unresolved.
- Semantic batching by similarity.
- Principal exceeding cap: sync suspended until existing conflicts resolved.

## Resolution UX

Each conflict surfaces options:

- NonceConflict: user picks which to keep; other tombstoned.
- IntentIdConflict: both Phase A's visible; user picks canonical or cancels both.
- RevocationRaceConflict: revocation wins automatically; notify user.

## Device-binding

Each device has distinct sub-key from Genesis + device attestation. Entries include device-key-id. Attacker cannot forge entries as a device they don't control.

## Error taxonomy

| Error                             | Trigger                                                                           | User action                                                                          | Retry                  |
| --------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | ---------------------- |
| `LamportClockMismatchError`       | Entry's Lamport clock device_id collides with a different device's prior entry    | Refuse merge; surface device-key audit; require re-attestation of conflicting device | Manual after audit     |
| `IntentIdConflictError`           | Same `intent_id` Phase A observed across branches with different action contents  | Surface both Phase A's; user picks canonical or cancels both                         | Manual after choice    |
| `NonceConflictError`              | Same nonce on different devices (T-008 replay or genuine concurrent collision)    | User picks which to keep; other tombstoned                                           | Manual after choice    |
| `RevocationRaceConflictError`     | Revocation entry races with later-descendant signing on a different branch        | Revocation wins automatically; user notified of races resolved by structural rule    | Auto                   |
| `ConflictFloodRateLimitError`     | Per-principal unresolved-conflict count exceeds 20 (R2-H1 cap)                    | Sync suspended; user resolves outstanding conflicts via merge UX before further sync | Manual after resolve   |
| `MergeReplayDivergenceError`      | Re-running merge over the same branch set produces a different merged_parent_hash | Refuse merge; investigate determinism bug or hostile branch reordering               | Never (programming)    |
| `DeviceAttestationMissingError`   | Entry references a device-key-id with no Genesis Record device attestation        | Refuse merge of entry; surface device-key provenance requirement                     | Manual after pair      |
| `OriginalParentHashTamperedError` | Signed `original_parent_hash` does not verify against signing device's key        | Refuse merge of entry; treat as hostile branch; quarantine until investigated        | Never (security event) |

## Cross-references

- specs/ledger.md — merge consumer.
- specs/trust-lineage.md — chain-level merge interaction.
- specs/runtime-abstraction.md — runtime invokes merge at sync.
- specs/threat-model.md — T-008, T-101.

## Test location

- `tests/integration/test_ledger_merge_two_device.py` — two-device fork-then-merge with non-overlapping entries (Tier 2).
- `tests/integration/test_ledger_merge_three_device.py` — three-device concurrent fork; deterministic Lamport ordering.
- `tests/regression/test_t101_conflict_flood_rate_limit.py` — T-101 R2-H1 cap; 21st conflict suspends sync.
- `tests/regression/test_t008_nonce_conflict_replay.py` — T-008 nonce conflict replay defense.
- `tests/integration/test_intent_id_conflict_resolution.py` — divergent Phase A on same intent_id; user picks canonical.
- `tests/integration/test_revocation_race_auto_resolves.py` — revocation always wins later-descendant.
- `tests/integration/test_merge_replay_determinism.py` — re-running merge yields identical merged_parent_hash chain.
- `tests/integration/test_device_attestation_required.py` — entry without device attestation refused.
- `tests/e2e/test_offline_multi_device_reconciliation.py` — three-device 7-day offline divergence + reconcile (Tier 3).

## Open questions

1. Conflict-flood ceiling 20 — Phase 01 telemetry will inform tuning; legitimate household scenarios may push higher.
2. Semantic batching similarity threshold — how aggressive vs preserving fidelity for forensic review.
3. Revocation-wins rule generality — does it cover delegation-with-time-bound revocation; coordination with trust-lineage.md.
4. Cross-device device-key rotation merge — how an entry signed by a now-rotated key merges; key-history retention.
5. Phase 02+ N-device merge performance — sort-and-replay cost at 100k+ entries per device.
