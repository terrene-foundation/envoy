# 07 — Tier 1 unit tests (consolidated suite)

**Purpose:** Tier 1 unit tests are seeded inside each primitive's build todo (per the wave files). This file consolidates Tier 1 surface in one manifest so /redteam round 1 mechanical sweep can audit per-module coverage per `rules/testing.md` § "Verify NEW modules have NEW tests".

**Source authority:** `02-plans/02-test-strategy.md` § Tier 1 + `02-plans/03-package-skeleton.md` § 3.

**Mocking allowed; <1s per test.**

---

## T-07-110 — Tier 1 canonical-bytes + hash-chain pure-function suite

**Files:** `tests/tier1/test_envelope_canonical_bytes_pure.py`, `test_ledger_canonical_dumps_byte_pinning.py`, `test_lamport_clock_next_pure.py`.

**Source:** Seeded by T-01-10, T-01-17.

**Acceptance:** ≥10 byte-pinned fixtures per file. Cross-OS byte-identity verified via fixture hash.

---

## T-07-111 — Tier 1 pure-functions: authorship + budget

**Files:** `tests/tier1/test_authorship_score_recompute_pure.py`, `test_budget_current_period_key_pure.py`.

**Source:** Seeded by T-02-30, T-03-60.

**Acceptance:** Deterministic replay; UTC-only reset semantics verified.

---

## T-07-112 — Tier 1 state machines: grant + boundary

**Files:** `tests/tier1/test_grant_moment_state_machine_transitions.py`, `test_envelope_config_dataclass_post_init.py`.

**Source:** Seeded by T-03-50, T-01-10.

**Acceptance:** All M0→M4 transitions covered; dataclass `__post_init__` invariants asserted.

---

## T-07-113 — Tier 1 emitter filters + format helpers

**Files:** `tests/tier1/test_format_record_id_for_event.py`, `test_posture_gate_5_step_fail_closed.py`.

**Source:** Seeded by T-01-17, T-02-31.

**Acceptance:** classification-PK redaction per `rules/event-payload-classification.md`; 5-step fail-closed gate behavior verified.

---

## Tier 1 audit gate

Per `rules/testing.md` § Audit Mode Rules, /redteam round 1 grep for every NEW Python module a primitive shard creates and verify ≥1 importing Tier 1 test exists. Empty grep = HIGH finding.

---

## Cross-references

- Test strategy: `02-plans/02-test-strategy.md`
- Tier 1 rule: `.claude/rules/testing.md` § Tier 1
- Per-primitive seeds: T-01-10, T-01-17, T-02-30, T-03-50, T-03-60, T-02-31
