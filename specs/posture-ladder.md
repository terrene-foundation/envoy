# posture-ladder

## Purpose

Canonical 5-tier autonomy ladder owned by this spec. Every spec that reads or writes a posture level imports the enum + state-transition contract from here. Load-bearing for Authorship Score gating, Grant Moment dispatch, Delegation cascade semantics, and per-channel rendering.

## Provenance

- **Source analysis:** `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md v3 §4.2` + `02-envelope-model.md v3 §8` (posture-ratchet gate) + `03-trust-lineage.md v2 §Posture semantics`.
- **Threats mitigated:** T-019 velocity-raise ratchet, T-023 score inflation via posture escalation, T-024 enterprise-mode posture coupling.
- **BETs tested:** BET-12 governance-primary-surface, BET-2 structural/semantic partition.
- **Cross-SDK:** mirrors kailash-py `PostureStore` / `PostureEvidence` / `SQLitePostureStore` primitives (filed mint#4 + kailash-py#597 for spec parity).

## Canonical enum

```python
class PostureLevel(IntEnum):
    PSEUDO      = 0   # Non-executing; read-only exploration; no Delegation Records produced.
    TOOL        = 1   # Single-step human-confirmed tool calls; Grant Moment per tool call.
    SUPERVISED  = 2   # Multi-step plans; human confirms the plan; tools execute without per-call Grant.
    DELEGATING  = 3   # Standing Delegation within declared envelope; Grant Moment only on boundary violations.
    AUTONOMOUS  = 4   # Maximally wide standing Delegation; goal-reconfirmation every N tool calls.
```

Integer ordering is load-bearing — `AUTONOMOUS > DELEGATING > SUPERVISED > TOOL > PSEUDO`. `>=` comparisons appear in composition rules and posture-ratchet gates.

**Wire format:** string name in JSON (e.g. `"DELEGATING"`); integer value in internal comparisons. JCS canonical form uses the string name (per specs/envelope-model.md §Canonical JSON).

## State-transition contract

### Ratchet-up (promotion)

Promotion to a higher level requires ALL of:

1. **Authorship Score threshold met** per specs/authorship-score.md:
   - `PSEUDO → TOOL`: N=0 (no authorship required; default entry).
   - `TOOL → SUPERVISED`: N=1 (one constraint with `authored=true`; the count-only gate per specs/authorship-score.md § Re-derivation from the Ledger).
   - `SUPERVISED → DELEGATING`: N=3 (personal mode) or N=5 (enterprise mode).
   - `DELEGATING → AUTONOMOUS`: N=5 (personal mode only — enterprise AUTONOMOUS forbidden on shared templates per specs/enterprise-deployment.md).
2. **Grant Moment co-signature** by user's Genesis key. Ratchet-up IS a first-class `posture_change` Ledger entry signed by Genesis, not by the runtime.
3. **Envelope version bump** (specs/envelope-model.md) — new posture is part of the envelope schema; any posture change is an `envelope_edit`.
4. **Cooling-off window not active** — see §Annual decay below.

### Ratchet-down (demotion)

Demotion may happen:

- **User-initiated** via Weekly Posture Review (specs/weekly-posture-review.md) or direct `envoy posture --set TOOL`. Signed by Genesis like ratchet-up.
- **Automatic on kill-criterion hit** — see specs/acceptance-metrics.md §Kill criteria. System demotes to `TOOL` and surfaces a rationale receipt.
- **Automatic on annual decay** — 12 months of no authored-constraint activity → decay by 1 level; user re-authors ≥1 to restore.

Demotion NEVER requires authorship; it is always permitted, always Genesis-signed, always a `posture_change` entry.

### Shared Household semantics

Per specs/shared-household.md, each principal carries an independent posture level. Household-wide actions require composition of participating principals' envelopes under `intersect_envelopes` (specs/envelope-model.md §Algorithms); the effective posture for the composed action is MIN of participants' postures.

## Per-tier semantics (what each tier does)

### PSEUDO

- Read-only tools only (e.g. `search`, `read_document`, `list_files`).
- No Ledger `PhaseARecord` emitted — intents are simulated and discarded.
- Outputs labeled `content_trust_level: llm-authored`; never becomes `user-authored`.
- Default tier at first Boundary Conversation entry.

### TOOL

- Each tool call surfaces a Grant Moment (specs/grant-moment.md M0-M4 state machine).
- Grant scope: single tool call with bound arguments (canonical args hash).
- No standing Delegation; `DelegationRecord` issued per-grant with `valid_until = now() + 5min`.

### SUPERVISED

- Plans are surfaced whole at a Grant Moment; user approves the plan (set of `PhaseARecord` intents) as a unit.
- Individual tools inside an approved plan execute without per-tool Grant (they re-use the plan-level Delegation).
- Plan-level Delegation `valid_until` = plan deadline or 24h max.

### DELEGATING

- Standing Delegation issued at ratchet-up ceremony; `valid_until` = envelope expiry (typically 30 days).
- Tool calls execute against the Delegation without Grant Moments AS LONG AS the envelope is not crossed.
- Envelope-crossing (budget, tool, recipient, temporal, data access) surfaces a Grant Moment + Ledger entry.
- Goal-reconfirmation per `envelope.metadata.goal_reconfirmation.N_tool_calls` (default 5 per specs/envelope-model.md).

### AUTONOMOUS

- Same substrate as DELEGATING with wider envelope ceilings.
- `goal_reconfirmation.N_tool_calls` defaults to higher (e.g. 20); user sets.
- Forbidden on shared Enterprise templates (specs/enterprise-deployment.md §Posture-ratchet under enterprise mode).
- Posture survives session boundary unless decayed.

## Algorithm

### `posture_change(current, target, evidence) → PostureChangeResult`

```python
def posture_change(current: PostureLevel, target: PostureLevel, evidence: PostureEvidence) -> PostureChangeResult:
    if target > current:  # ratchet-up
        N_required = posture_up_authorship_threshold(current, target, evidence.mode)  # table above
        if evidence.authorship_score < N_required:
            raise PostureAuthorshipInsufficientError(
                current=current.name, target=target.name,
                have=evidence.authorship_score, need=N_required,
            )
        if not evidence.genesis_signed_grant:
            raise PostureGenesisGrantMissingError(...)
        if evidence.cooling_off_active:
            raise PostureCoolingOffActiveError(...)
    elif target < current:  # ratchet-down
        pass  # always permitted
    elif target == current:
        raise PostureNoopError(...)
    # Write posture_change Ledger entry, envelope_edit bump, notify channel adapters.
    entry = Ledger.append_posture_change(
        from_level=current, to_level=target,
        genesis_signed=evidence.genesis_signed_grant,
        authorship_at_promotion=evidence.authorship_score,
    )
    return PostureChangeResult(new_level=target, ledger_entry=entry)
```

### `effective_posture_for_composition(principals, action) → PostureLevel`

```python
def effective_posture_for_composition(principals: list[Principal], action: Action) -> PostureLevel:
    # Shared Household composition; specs/shared-household.md consumer.
    # `p.posture_level` here is the PRINCIPAL'S current effective posture
    # (derived per principal by walking that principal's Ledger
    # `posture_change` entries — the audit-chain authority). It is NOT the
    # envelope's `metadata.posture_level` field, which is the mint-time
    # annotation per specs/envelope-model.md § metadata.posture_level.
    return min(p.posture_level for p in principals if p in action.consenting_principals)
```

## Error taxonomy

| Error                                  | Trigger                                                          | User action                                                      |
| -------------------------------------- | ---------------------------------------------------------------- | ---------------------------------------------------------------- |
| `PostureAuthorshipInsufficientError`   | Ratchet-up requested but AuthorshipScore below threshold.        | Author ≥1 additional constraint via Grant Moment approve+author. |
| `PostureGenesisGrantMissingError`      | Ratchet-up ceremony not co-signed by Genesis.                    | Re-run Weekly Posture Review ritual with passphrase unlock.      |
| `PostureCoolingOffActiveError`         | Ratchet-up within cooling-off (24h after demotion).              | Wait for cooling-off; window surfaces in Daily Digest.           |
| `PostureNoopError`                     | Target == current; no-op rejected.                               | None; silent on CLI, suppress on surface.                        |
| `PostureAnnualDecayPendingError`       | Session start with ≥12mo no authorship on DELEGATING/AUTONOMOUS. | Author ≥1 constraint or accept demotion at next session.         |
| `PostureEnterpriseAutonomousForbidden` | Ratchet to AUTONOMOUS under enterprise-shared template.          | None; enterprise policy forbids shared-template AUTONOMOUS.      |

All errors become Ledger entries `content_trust_level: system`. Error messages MUST NOT echo posture-dependent content.

## Cross-references

- **specs/envelope-model.md** — envelope schema carries effective posture; ratchet triggers envelope version bump.
- **specs/authorship-score.md** — ratchet gate consumes authorship score.
- **specs/grant-moment.md** — ratchet ceremony IS a Grant Moment.
- **specs/weekly-posture-review.md** — ritual surface for ratchet.
- **specs/shared-household.md** — composition semantics.
- **specs/enterprise-deployment.md** — AUTONOMOUS carveout on shared templates.
- **specs/ledger.md** — `posture_change` entry type.
- **specs/boundary-conversation.md** — initial posture selection at onboarding.
- **specs/sub-agent-delegation.md** — sub-agents inherit posture ≤ parent.
- **specs/threat-model.md** — T-019, T-023, T-024.

## Out of scope (this phase)

Per `rules/spec-accuracy.md` Exception 1 (bounded out-of-scope sections) +
`rules/specs-authority.md` Rule 6 (deviation acknowledgment). The Phase-01
PostureGate (T-02-31, `envoy/authorship/posture_gate.py`) implements the
5-step fail-closed gate against the spec's algorithm at § Algorithm. T-02-33
(Tier 2 wiring) closed the prior envelope_edit pairing deferral; ratchet-up
now emits paired `posture_change` + `envelope_edit` Ledger entries per spec
§ Ratchet-up #3. The following surfaces from the spec's other sections are
explicitly NOT implemented in Phase 01 — each is named to a successor shard
or phase:

- **Cooling-off TIMER + window calculation** (spec § Ratchet-up #4 +
  `cooling_off_active` boolean) — scheduled in Phase 03 Weekly Posture
  Review ritual. PostureGate Phase 01 ENFORCES `cooling_off_active=True`
  by raising `PostureCoolingOffActiveError`; the WPR ritual owns the timer.
- **Annual decay scheduler** (spec § Ratchet-down "Automatic on annual
  decay") — scheduled in Phase 03. PostureGate accepts `trigger="annual_decay"`
  in the wire-form taxonomy; the SCHEDULER that emits it is Phase 03.
- **Per-dimension scope transitions** (spec § Ratchet-up #1 thresholds
  per-dim) — Phase 03. T-02-31 ships `dimension_scope="global"` only.
- **Shared Household composition** (`effective_posture_for_composition`,
  spec § Shared Household semantics) — Phase 03+ separate function.
- **`PostureAnnualDecayPendingError`** (spec § Error taxonomy) — Phase 03;
  raised by the Phase-03 decay scheduler at session start, not by
  PostureGate itself.

## Test location

- Ratchet-up insufficient authorship (all four transitions).
- Ratchet-up Genesis-missing.
- Ratchet-down always permitted.
- Annual decay.
- Enterprise AUTONOMOUS refusal.
- Shared-household MIN composition.
- `tests/tier2/test_posture_gate_wiring.py` — Tier 2 wiring (T-02-33):
  PostureGate against real `EnvoyLedger` + real Ed25519. Pins the
  paired `posture_change` + `envelope_edit` Ledger emission on
  ratchet-up (3 positive cases — PSEUDO→TOOL, TOOL→SUPERVISED,
  multi-step PSEUDO→DELEGATING) AND the asymmetric pairing on
  ratchet-down (1 case — demotion emits ONLY `posture_change`) AND
  the fail-closed pairing invariant (1 case — failed ratchet-up
  emits NEITHER entry).
- `tests/tier1/test_posture_gate_5_step_fail_closed.py` — Tier 1
  unit coverage for the 5-step gate including Step 3e
  (`PostureRatchetEnvelopeMissingError` on ratchet-up with
  `envelope=None`) and the once-only `mutate_for_posture_level()`
  consumption contract.

Threat traceability — T-019/T-023/T-024 mitigation tests live here, per specs/threat-model.md §Test location.

## Open questions

1. Cooling-off duration — 24h default; Phase 03 user research.
2. Annual decay semantics under account dormancy — no-ops or trigger on next session start?
3. Posture-as-cryptographic-attribute vs posture-as-envelope-metadata — current choice: envelope-metadata (re-derivable from Ledger). Phase 04 may cryptographically attest.
