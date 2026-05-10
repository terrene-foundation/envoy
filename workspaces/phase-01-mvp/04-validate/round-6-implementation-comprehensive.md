# Round 6 — Phase 01 MVP Red Team Delta Audit (T-02-32 BET-12 Emitter)

**Document role:** Delta-audit of the T-02-32 shard that landed at PR #20 (merge `2517798`, 2026-05-11) AFTER Round 5's wave-2 convergence finalizer (2026-05-11, commit `62e20f4`). Re-derives the 9 mechanical sweeps from `02-plans/04-redteam-cycle-plan.md` § 6 against the new surface; verifies orphan-detection Rule 1 production call site; verifies privacy contract per `rules/event-payload-classification.md` Rules 2 + 3.

**Date:** 2026-05-11.
**Trust posture:** L5_DELEGATED. Round 1 OPTIONAL per `skills/32-trust-posture/redteam-integration.md`; full sweep run anyway because the new surface introduces a privacy-contract boundary (cohort-cadence emission with hashed-principal-id requirement).
**Status:** GREEN — 0 CRITICAL + 0 HIGH + 0 MED + 0 LOW. Counter advances Round 5 (2) → Round 6 (3).

---

## 1. Audited surface (post-Round-5 delta)

- `envoy/authorship/bet12_emitter.py` — new module (~150 LOC; 1 emitter class + 1 Protocol + 1 frozen dataclass + 1 module helper).
- `envoy/authorship/__init__.py` — `__all__` 14 → 17 (+`BET12CadenceEmitter`, `BET12CadencePayload`, `BET12Sink`).
- `envoy/authorship/posture_gate.py` — required DI surface added (`bet12_emitter` kwarg on `__init__`); Step 5+ emit at `request_transition` line 761.
- `tests/tier1/test_bet12_cadence_emitter.py` — 17 cases across 6 test classes.
- `tests/tier1/test_posture_gate_5_step_fail_closed.py` — +6 wiring cases (`TestStep5PlusBET12Emission`) + +1 construction-discipline case.

---

## 2. Mechanical sweeps — re-derived from scratch

| #   | Sweep                                                           | Result                                                                                                                                                   |
| --- | --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Stub / placeholder markers (`zero-tolerance.md` Rule 2)         | PASS — 1 docstring ref to hash format (`XXXXXXXX`)                                                                                                       |
| 2   | Silent fallback (`zero-tolerance.md` Rule 3)                    | PASS — no `except: pass` / bare-except                                                                                                                   |
| 3   | `eval` / `exec` / `shell=True` (`security.md`)                  | PASS — clean                                                                                                                                             |
| 4   | Hardcoded secrets (`security.md` § No Hardcoded Secrets)        | PASS — clean                                                                                                                                             |
| 5   | Fake / mock data (`zero-tolerance.md` Rule 2 frontend mock)     | PASS — clean                                                                                                                                             |
| 6   | DDL outside migrations (`schema-migration.md` Rule 1a)          | PASS — clean                                                                                                                                             |
| 7   | `print()` in production (`observability.md` Rule 1)             | PASS — clean                                                                                                                                             |
| 8   | `__all__` AST counts                                            | PASS — `__init__.py` 17, `bet12_emitter.py` 3                                                                                                            |
| 9   | Orphan-detection Rule 1 (production call site within 5 commits) | PASS — `posture_gate.py:761 await self._bet12_emitter.emit(...)` IS the call site, lives in the framework's hot path (Step 5+ post-Ledger), not in tests |

---

## 3. Spec / contract verification (per `skills/spec-compliance/SKILL.md`)

### 3.1 Capacity-check invariants from `02-wave-2-...md` § T-02-32

| Invariant                                            | Verification                                                                                                                                      |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1. `bet_id` tag canonical "BET-12"                   | `_BET_ID_CANONICAL` module constant; `test_no_per_call_bet_id_override_surface` AST-locks `emit()`                                                |
| 2. Emit on every posture-transition the gate accepts | `TestStep5PlusBET12Emission::test_ratchet_up_emits_bet12_after_ledger` + `test_ratchet_down_emits_bet12` + `test_failed_gate_does_not_emit_bet12` |

### 3.2 Privacy contract per `rules/event-payload-classification.md`

- **Rule 2** (principal_id hashing): `_hash_principal_id` produces `sha256:` + first 8 hex chars; verified byte-identical with `format_record_id_for_event` shape via `test_hash_matches_sha256_first_8_hex`. Empty `principal_id` rejected at the encoding boundary.
- **Rule 3** (no schema-revealing fields): `BET12CadencePayload.__dataclass_fields__` AST-locked to `{bet_id, principal_id_hash, from_level, to_level, days_at_current_posture, authored_count_at_transition}` via `test_payload_fields_are_only_cohort_safe`. `emit()` signature AST-locked against Rule-3-blocked kwargs (`envelope_hash`, `authored_constraints`, `field_name`, etc.) via `test_emit_signature_only_accepts_cohort_safe_kwargs`.

### 3.3 Wiring contract per `rules/orphan-detection.md` Rule 1

- Production call site exists at `envoy/authorship/posture_gate.py:761` inside `PostureGate.request_transition` Step 5+ (post-Ledger).
- Call site is in the framework's hot path, not in tests.
- Failed-gate paths (Step 1-3d raises) MUST NOT emit; locked by `test_failed_gate_does_not_emit_bet12`.

---

## 4. Test verification

```
$ .venv/bin/pytest tests/ --no-header -q
... 566 passed in 18.34s
```

542 baseline (Round 5) + 17 new BET-12 emitter tests + 6 new wiring tests + 1 new construction-discipline test = 566. No regressions; +24 new tests.

---

## 5. Convergence verdict

| Criterion                                    | Status                                  |
| -------------------------------------------- | --------------------------------------- |
| 0 CRITICAL findings                          | ✓ 0                                     |
| 0 HIGH findings                              | ✓ 0                                     |
| 2 consecutive clean rounds                   | ✓ Round 5 (2026-05-11) + Round 6 (this) |
| Spec compliance: 100% AST/grep verified      | ✓ §3.1–3.3                              |
| New code has new tests                       | ✓ 24 new tests across 2 test files      |
| Frontend integration: 0 mock data            | ✓ N/A (CLI/library; no FE)              |
| Privacy contract enforced                    | ✓ Rules 2 + 3 AST-locked                |
| Orphan-detection Rule 1 production call site | ✓ `posture_gate.py:761`                 |

**Final verdict: T-02-32 SHIPS CLEAN.** Wave-2 surface (T-02-30 + T-02-31 + T-02-32 + T-02-34 + T-02-35) is now closed at the primitive layer. Wave-2 milestone gate remains unblocked for T-02-33 (Tier 2 wiring; carries `LocalLedgerBET12Sink` + `specs/ledger.md` schema disposition) / T-02-36 (Shamir recovery CLI; carries Phase-B citation upgrade for `shamir-recovery.md` L-03).

---

## 6. Carry-forward to T-02-33

- Concrete Phase-01 `LocalLedgerBET12Sink` writing ritual-style Ledger entries with `bet_id="BET-12"` requires `specs/ledger.md` schema disposition: extend `ritual_completion` `ritual_kind` enum vs introduce `posture_transition_cadence` entry type. Per `rules/specs-authority.md` MUST Rule 5, this is a Tier-2-time decision.
- WPR ritual call site computing real `days_at_current_posture` from PostureStore history. T-02-33 wires the ratchet-up ceremony's day-count read; until then, Phase 01 callers may omit the kwarg (default 0.0 — honest empty value, NOT a fabricated default).
- Tier 2 acceptance (T-02-33) MUST add: real-Ledger `posture_change` + `envelope_edit` pairing per `journal/0020-DECISION-envelope-edit-deferred-to-tier-2.md`; real-Ledger `ritual_completion` (or successor) BET-12 emission round-trip; PostureStore-history-driven `days_at_current_posture` computation.
