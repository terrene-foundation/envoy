# Phase 02 follow-up — deep-freeze (MappingProxyType / tuple-of-tuples)

> **STATUS 2026-05-06**: Created at PR #12 close (L-03 shard B step 2). Tracks
> the inner-container mutation vectors that L-03 left explicitly deferred to
> Phase 02. PR #11 + PR #12 closed every FIELD-REASSIGNMENT vector; this todo
> closes the INNER-CONTENT mutation vector.

## Origin

PR #12 security review L-1 (2026-05-06): "Phase 02 deferred vectors documented
inline only, not in a single tracker." This todo is the structural defense
against silent ratcheting — the next-phase agent has one greppable artifact
listing every Phase 02 deep-freeze closure.

## Problem

Per `rules/trust-plane-security.md` MUST NOT Rule 4: every constraint
dataclass MUST be `@dataclass(frozen=True)`. PR #11 + PR #12 made the field
reassignment vector raise `FrozenInstanceError`, but the INNER content of
mutable container fields is still in-place mutable:

```python
# Foreclosed by L-03 shards A + B (raises FrozenInstanceError):
compiled.financial.per_call_ceiling_microdollars = 999_999  # ❌ frozen
compiled.financial.authored_constraints += (extra,)         # ❌ frozen
compiled.metadata.envelope_id = "evil"                      # ❌ frozen

# Still possible after L-03 (Phase 02 closes via deep-freeze):
compiled.metadata.authorship_score["authored_count"] = 999          # ⚠️
compiled.metadata.enterprise_mode["is_enterprise"] = True            # ⚠️
compiled.metadata.goal_reconfirmation["enabled"] = False             # ⚠️
compiled.operational.tool_allowlist.append("evil")                   # ⚠️
compiled.operational.tool_denylist.append("required-tool")           # ⚠️
compiled.operational.rate_limits["http"] = {"req_per_sec": 9999}     # ⚠️
compiled.operational.sub_agent_spawn_limit["agent"] = 9999           # ⚠️
compiled.temporal.allowed_windows.append({"start": "...", ...})      # ⚠️
compiled.temporal.blackout_windows.clear()                           # ⚠️
compiled.data_access.field_allowlist_per_model.setdefault(           # ⚠️
    "User", []).append("ssn")
compiled.data_access.field_denylist.append("required-field")         # ⚠️
compiled.data_access.semantic_rules.append({...})                    # ⚠️
compiled.communication.recipient_allowlist.append("evil@x.com")      # ⚠️
compiled.communication.recipient_denylist.clear()                    # ⚠️
compiled.communication.domain_allowlist.append("evil.com")           # ⚠️
compiled.communication.channel_allowlist.append("evil-channel")      # ⚠️
compiled.communication.content_rules.append({...})                   # ⚠️
compiled.semantic_checks.latency_budget_ms["semantic_cached"] = 0    # ⚠️
```

These are the threat-model vectors the next phase MUST close.

## Why deferred from L-03

L-03 shard B's budget covered the field-reassignment vector (~600 LOC, two
landings). Deep-freeze of every inner container is a separate invariant set:

1. Convert mutable `dict`/`list` defaults to `MappingProxyType` /
   `tuple[tuple, ...]` / `frozenset` equivalents.
2. Refactor every read site that depends on the mutable-container shape
   (e.g. `dim.tool_allowlist.append(...)` in test fixtures) to use the
   immutable surface (e.g. construct via `dataclasses.replace`).
3. Refactor the boundary-conversation builder (Wave 2) to mint frozen
   containers at construction.
4. Update content_hash invariant tests — the canonical bytes for a
   `MappingProxyType` and a `dict` with the same content are identical
   under JCS, but the PYTHON OBJECT comparison may differ.

Each is a separate shard's worth of invariants — exceeds L-03's budget.

## Action (Phase 02 entry)

**Capacity check**: ~150 LOC type changes (MappingProxyType wrapping in
`__post_init__` via `object.__setattr__`) + ~100 LOC test rewrites + ~50 LOC
fixture updates + ~30 LOC content_hash invariant tests; 4 invariants
(MappingProxyType wrap; tuple-of-tuples for nested lists; round-trip
content_hash; defensive copy at construction). Within Phase 02 entry
shard budget.

**Steps**:

1. In `envoy/envelope/types.py`, wrap every mutable container field's
   default factory output in the appropriate immutable type:
   - `dict[str, X]` → `MappingProxyType({...})` via `__post_init__` `object.__setattr__`
   - `list[X]` → `tuple[X, ...]`
   - `dict[str, list[X]]` → `MappingProxyType({k: tuple(v) for k, v in d.items()})`

2. Audit every read site for the mutable-container shape. Sites to grep:
   - `tool_allowlist.append`
   - `rate_limits[`
   - `field_allowlist_per_model.setdefault`
   - `recipient_allowlist.append`
   - `authorship_score["`
   - `enterprise_mode["`
   - `goal_reconfirmation["`
   - `latency_budget_ms[`

3. Update the SHARD_B_TRIGGER markers in
   `tests/regression/test_l03_constraint_lists_immutable.py` to flip from
   "asserts inner mutation succeeds" to `pytest.raises(TypeError)` (since
   `MappingProxyType` is not assignable; tuples have no `.append`).

4. Add a new invariant test:
   `test_compiled_envelope_inner_container_mutation_raises.py` — round-trip
   of (compile → attempt every inner mutation listed above → assert raise).

5. Verify content_hash byte-identity: compile two equivalent inputs and
   assert `canonical_bytes` and `content_hash` are unchanged after the
   MappingProxyType conversion (the JCS layer should not care about the
   Python wrapper type).

**Tests added**:

- `tests/regression/test_phase02_inner_container_immutability.py` — ~25 cases
  parameterized over (dim_class, field_name, mutation_call, expected_error).
- Updated `tests/regression/test_l03_constraint_lists_immutable.py`
  TestShardBFollowupTracking class — flip the inner-dict mutation
  acknowledgements to assert raises.

**Blocks on**: nothing (L-03 shard B is complete).

**Blocks**: nothing critical. Lands ahead of T-02-31 (PostureGate consumes
`EnvelopeConfig` — must not be able to silently widen its own envelope at
runtime via inner-container mutation).

**Estimate**: 0.5 session.

## Verification (when shipped)

- `.venv/bin/python -m pytest tests/regression/test_phase02_inner_container_immutability.py`
  — 25/25 green.
- Full Tier 1 + regression suite green.
- Mechanical sweep:
  `grep -rEn '(tool_allowlist|rate_limits|field_allowlist_per_model|recipient_allowlist|authorship_score|enterprise_mode|goal_reconfirmation|latency_budget_ms)\[' envoy/ tests/`
  — only sites inside `pytest.raises` blocks or canonical replace-builder
  patterns.
- `EnvelopeConfig` round-trip: compile → mutation attempt on any nested
  container → `TypeError` (or equivalent for tuples).
- `content_hash` byte-identity unchanged from L-03 baseline.

## Cross-references

- Rule: `rules/trust-plane-security.md` MUST NOT Rule 4 (frozen constraint
  dataclasses, full closure including inner containers).
- Spec: `specs/envelope-model.md` § content_hash byte-identity invariant.
- Predecessors: L-03 shard A (PR #10), shard B step 1 (PR #11), shard B
  step 2 (PR #12).
- Origin: PR #12 security review L-1 (2026-05-06).
