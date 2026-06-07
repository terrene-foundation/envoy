# session-state

## Purpose

Owning spec for ephemeral session-scoped state: `SessionObservedState` (tool-call fingerprints, first-time-action cache, goal-reconfirmation counter), session boundary semantics, and the `ReasoningCommit` Ledger entry. Load-bearing for envelope-model.md §First-time-action gate + T-013 composition-aware defense.

## Provenance

- **Source analysis:** `workspaces/phase-00-alignment/01-analysis/02-envelope-model.md v3 §14.9 + §16 + §19` + `04-ledger.md v1 §Entry types`.
- **Threats mitigated:** T-013 composition-aware feedback-loop, T-019 velocity ratchet across session boundary, T-015 goal drift at reasoning commit. (Round 2 R2-HIGH closure: T-022 was previously listed here but T-022 = Envelope Library Sybil per anchor doc 09 §3 — owned by skill-ingest.md / foundation-ops.md, not session-state. First-time-action injection is a sub-class of T-013 composition-aware defense; the SessionObservedState fingerprint cache is the structural mitigation.)
- **BETs tested:** BET-2 structural/semantic partition (reasoning commit byte-identity), BET-12 first-time-action gate audit trail.

## Session definition

A session is bounded by:

- **Start:** user unlock ceremony (specs/boundary-conversation.md §S1) OR explicit `envoy session start` CLI OR first message in a channel-adapter session (specs/channel-adapters.md).
- **End:** explicit `envoy session end` OR 24h idle timeout OR user lock (keyboard/CLI) OR channel-adapter disconnect.

Session boundary emits a `session_boundary_crossed` Ledger entry (producer-owning spec: this spec). Entry signed by runtime device key.

## Schema

### SessionObservedState (Trust Vault region — NOT synced)

```json
{
  "schema_version": "session-state/1.0",
  "session_id": "uuid-v7",
  "principal_genesis_id": "sha256:...",
  "started_at": "<iso8601>",
  "last_activity_at": "<iso8601>",
  "tool_calls_made": {
    "<fingerprint>": {
      "tool_name": "<str>",
      "args_canonical_hash": "sha256:...",
      "first_invoked_at": "<iso8601>",
      "invocation_count": <int>,
      "last_outcome": "success | failure | grant_pending"
    }
  },
  "goal_reconfirmation": {
    "last_reconfirmed_at": "<iso8601>",
    "tool_calls_since_reconfirm": <int>,
    "threshold": <int>
  },
  "reasoning_commits": [
    {"commit_id": "sha256:...", "at": "<iso8601>"}
  ],
  "pending_phase_a_orphans": [
    {"intent_id": "sha256:...", "phase_a_at": "<iso8601>", "ttl_expires_at": "<iso8601>"}
  ],
  "pre_authorized_patterns": [
    {"pattern_id": "sha256:...", "tool_name": "<str>", "args_pattern_ast": {...}, "authored_at": "<iso8601>", "scope": "session | cross_session"}
  ],
  "envelope_version_at_session_start": <int>,
  "posture_at_session_start": "PSEUDO | TOOL | SUPERVISED | DELEGATING | AUTONOMOUS"
}
```

**`pre_authorized_patterns` semantics (Round 2 R2-CRIT closure):** patterns the user authored (typically via Boundary Conversation S5 first-task or Weekly Posture Review batch-to-envelope conversion) that bypass the first-time-action Grant Moment. Lookup is structural AST-match against `args_pattern_ast` on the `tool_name + canonicalize_args(args)` fingerprint. `scope: session` patterns reset on session boundary; `scope: cross_session` patterns persist across sessions and are sourced from envelope `*.authored_constraints` rather than session-local state. Per envelope-model.md §First-time-action gate, "no fingerprint match AND no pre-authorized pattern match → Grant Moment".

**`tool_calls_made` fingerprint**: `sha256(tool_name || canonicalize_args(args))` per specs/envelope-model.md §First-time-action gate.

**Cache reset on session boundary**: `tool_calls_made` and `goal_reconfirmation.tool_calls_since_reconfirm` reset at session end — first tool call in the new session is first-time-action even if an identical call happened 5 minutes earlier in the previous session. This is intentional per the T-013 composition-aware defense (per-session fingerprint scope prevents cross-session state injection from amortizing the first-time-action gate).

### session_boundary_crossed (Ledger entry)

```json
{
  "type": "session_boundary_crossed",
  "schema_version": "session-boundary/1.0",
  "transition": "start | end",
  "session_id_prior": "uuid-v7 | null",
  "session_id_next": "uuid-v7 | null",
  "trigger": "unlock | cli_start | cli_end | idle_timeout | user_lock | channel_disconnect",
  "tool_call_count_observed": <int>,
  "orphan_phase_a_count": <int>,
  "unresolved_grants_deferred": <int>,
  "signed_by": "runtime_device_key",
  "signature_hex": "ed25519"
}
```

### ReasoningCommit (Ledger entry; T-013 defense)

Emitted by the runtime at each structural decision point where the LLM's reasoning branches a composition rule. Commits the reasoning-context hash before subsequent tool calls, so post-hoc feedback-loop injection cannot re-write the reasoning without breaking the chain.

```json
{
  "type": "ReasoningCommit",
  "schema_version": "reasoning-commit/1.0",
  "commit_id": "sha256:<content_hash>",
  "session_id": "uuid-v7",
  "preceding_tool_calls_fingerprints": ["sha256:...", ...],
  "reasoning_context_hash": "sha256:<canonical_reasoning_bytes>",
  "envelope_version_at_commit": <int>,
  "composition_rules_applied": ["<rule_id>", ...],
  "signed_by": "runtime_device_key",
  "signature_hex": "ed25519"
}
```

**`reasoning_context_hash`** is SHA-256 of the JCS-canonicalized reasoning bytes presented to the LLM at that decision point. Runtime captures this pre-commit; any later mutation of context would require breaking the SHA-256 pre-image.

**Emission frequency**: at every composition-rule-gated decision + at goal_reconfirmation trigger + at every ratchet-from-SUPERVISED-plan-step transition. Not per-tool-call (would flood Ledger).

## Algorithm

### `first_time_action_gate(session: SessionObservedState, tool_name: str, args: dict) → GateResult`

```python
def first_time_action_gate(session, tool_name, args):
    fingerprint = sha256(
        tool_name.encode("utf-8") +
        canonicalize_args(args).encode("utf-8")  # JCS per envelope-model.md
    ).hexdigest()
    fp_key = f"sha256:{fingerprint}"

    if fp_key in session.tool_calls_made:
        return GateResult.RECOGNIZED

    # AST-match against envelope-declared pre-authorized patterns
    # (per §Schema, pre_authorized_patterns is a list of dicts with args_pattern_ast).
    for pattern in session.pre_authorized_patterns:
        if pattern["tool_name"] != tool_name:
            continue
        if not match_ast(pattern["args_pattern_ast"], args):
            continue
        session.tool_calls_made[fp_key] = ToolCallObservation(
            tool_name=tool_name, args_canonical_hash=fp_key,
            first_invoked_at=now_iso(), invocation_count=1,
            last_outcome="pre_authorized",
        )
        return GateResult.RECOGNIZED

    return GateResult.FIRST_TIME_REQUIRES_GRANT  # triggers specs/grant-moment.md
```

### `session_boundary(trigger: Trigger, cur: SessionObservedState) → LedgerEntry`

```python
def session_boundary(trigger, cur):
    entry = Ledger.append(
        type="session_boundary_crossed",
        transition="end" if trigger in END_TRIGGERS else "start",
        session_id_prior=cur.session_id if trigger in END_TRIGGERS else None,
        session_id_next=None,  # populated by caller on fresh session start
        trigger=trigger.name,
        tool_call_count_observed=len(cur.tool_calls_made),
        orphan_phase_a_count=len(cur.pending_phase_a_orphans),
        unresolved_grants_deferred=count_deferred(),
        signed_by=runtime_device_key(),
    )
    # Clear session-scoped state (new SessionObservedState for next session).
    return entry
```

### `reasoning_commit(session, reasoning_context, composition_rule_ids) → LedgerEntry`

```python
def reasoning_commit(session, reasoning_context, rule_ids):
    canonical = jcs_canonicalize(reasoning_context)
    ctx_hash = sha256(canonical).hexdigest()
    preceding_fps = [fp for fp in session.tool_calls_made.keys()]
    entry = Ledger.append(
        type="ReasoningCommit",
        commit_id=sha256(canonical + ",".join(rule_ids)).hexdigest(),
        session_id=session.session_id,
        preceding_tool_calls_fingerprints=preceding_fps,
        reasoning_context_hash=f"sha256:{ctx_hash}",
        envelope_version_at_commit=session.envelope_version_at_session_start,
        composition_rules_applied=rule_ids,
        signed_by=runtime_device_key(),
    )
    session.reasoning_commits.append({"commit_id": entry.commit_id, "at": now_iso()})
    return entry
```

## Persistence

`SessionObservedState` is in-memory during session + snapshot to Trust Vault encrypted at every Ledger append (so a crash mid-session preserves orphan-phase-A tracking). Never synced to other devices (each device has its own session cache).

## Orphan Phase-A tracking

Per specs/ledger.md §Two-phase signing, Phase A intents without matching Phase B are tracked in `pending_phase_a_orphans`. TTL is 30 days. At next session start, specs/grant-moment.md surfaces orphan resolution.

## Error taxonomy

| Error                                      | Trigger                                                    | User action                                           |
| ------------------------------------------ | ---------------------------------------------------------- | ----------------------------------------------------- |
| `SessionIdleTimeoutError`                  | Session > 24h idle; next tool call rejected.               | Start new session (unlock ceremony).                  |
| `SessionBoundaryMidTransactionError`       | Session boundary triggered while Phase A pending Phase B.  | Resolve orphan at next session via Grant Moment.      |
| `ReasoningCommitPreimageMismatchError`     | Runtime observes reasoning context whose hash ≠ committed. | Halt; session marked tainted; manual audit required.  |
| `FirstTimeActionGateBypassAttemptError`    | Gate called with unsigned / unauthenticated caller.        | Runtime bug; file issue.                              |
| `GoalReconfirmationThresholdExceededError` | tool_calls_since_reconfirm ≥ threshold; next tool gated.   | User confirms goal alignment (Grant Moment dispatch). |

## Cross-references

- **specs/envelope-model.md** — §First-time-action gate consumer; §goal_reconfirmation consumer.
- **specs/ledger.md** — owns the type table; this spec is the producer for `session_boundary_crossed` + `ReasoningCommit` + `PhaseAOrphanResolution` (together with ledger.md §Two-phase signing).
- **specs/grant-moment.md** — dispatched on FIRST_TIME_REQUIRES_GRANT + orphan resolution.
- **specs/boundary-conversation.md** — session-start trigger.
- **specs/trust-vault.md** — persistence region.
- **specs/threat-model.md** — T-013, T-015, T-019.

## Test location

Phase 01 ships the `ReasoningCommit` and `session_boundary_crossed` Ledger entries (emitted by `envoy/boundary_conversation/runtime.py`: `_ENTRY_REASONING_COMMIT` per S1..S9 transition, `_ENTRY_SESSION_BOUNDARY` at S8 shamir-suspend). Both are tested in-repo:

- `tests/tier2/test_boundary_conversation_per_state_ledger_entries.py` — each S1..S9 transition emits a `ReasoningCommit` (`assert len(reasoning) >= 8`); S8 emits `session_boundary_crossed`; full chain verifies end-to-end (`test_chain_verifies_end_to_end`).
- `tests/tier3/test_boundary_conversation_full_path.py` — the full ritual path exercising the per-state Ledger schedule end-to-end.

T-019 (velocity ratchet across session boundary) has its dedicated regression test under `tests/regression/` (`test_t019*`).

## Out of scope (this phase)

The full `SessionObservedState` cache surface (tool-call fingerprints, first-time-action gate, goal-reconfirmation counter) is NOT wired in Phase 01 — `KailashRuntime.first_time_action_gate` is a typed Phase-02 stub on both adapters ("requires Wave-2 session state + Grant"; `envoy/runtime/adapters/kailash_py.py`), and `SessionObservedState` is referenced as Phase-04 scope at `envoy/model/errors.py`. The following test surfaces land with the Phase-02 session-state substrate (+ Phase-03 two-phase signing) and are NOT present in Phase 01:

- First-time-action gate recognition + reset on session boundary (Phase-02 session-state cache).
- ReasoningCommit byte-identity ACROSS runtimes (BET-6 — Phase 02 wires the second runtime; Phase 01 has the single `kailash-py` runtime path tested above).
- Orphan Phase-A TTL (Phase-03 two-phase signing).
- `session_boundary_crossed` emission on all 6 triggers (Phase 01 exercises the S8 ritual-suspend trigger; the idle-timeout / user-lock / channel-disconnect triggers land with the long-running session model, Phase-02 hooks item 9).
- ReasoningCommit preimage-mismatch detection (`ReasoningCommitPreimageMismatchError` — Phase-02 runtime reasoning-context observation).
- Dedicated T-013 / T-015 threat tests (Phase-01 carries structural mitigations in this spec; the full-matrix threat-coverage gate is the Phase-02 deferral per `workspaces/phase-01-mvp/journal/0053`).

## Open questions

1. Idle timeout duration — 24h default; user-configurable vs fixed.
2. ReasoningCommit emission cost — expected ~5/session; Phase 01 empirical tuning.
3. Cross-session fingerprint carry-over — current: cleared at session boundary per T-013 composition-aware defense; Phase 04 may offer opt-in carry for convenience trade-off (subject to specs/posture-ladder.md §Posture-ratchet gate eligibility).
4. Reasoning-context canonical form — JCS of a defined schema vs opaque-bytes; current: opaque-bytes hash. Phase 03 may formalize.
