# 08 — Tier 3 acceptance tests (per EC)

**Purpose:** Tier 3 EC acceptance tests not bundled inside primitive build todos. Most ECs have their Tier 3 acceptance test in the wave file that owns the primitive (T-02-45 EC-1, T-03-55 EC-2, T-04-77 EC-7, T-04-78 EC-8, T-04-84 EC-3, T-06-104 EC-4, T-06-105 EC-9). This file holds EC-5 (Shamir 10-combo + cross-tool interop) and EC-6 (redteam convergence).

**Source authority:** `02-plans/02-test-strategy.md` § Tier 3 + `02-plans/04-redteam-cycle-plan.md`.

---

## T-08-130 — Acceptance EC-5 Tier 3: Shamir 10-combinations + cross-tool interop

**Implements:** EC-5 acceptance gate.

**Action:**

- `tests/tier3/test_shamir_all_10_combinations.py` — C(5,3)=10 combos exhaustive reconstruct.
- `tests/tier3/test_shamir_cross_tool_interop.py` — `python-shamir-mnemonic` interop bidirectional (Envoy generates → external tool reconstructs; external tool generates → Envoy reconstructs).
- `tests/tier3/test_shamir_plain_language_errors.py` — error messages don't leak share contents.
- `tests/tier3/test_trust_store_cross_os_portability.py` — BET-9b (vault portable across macOS / Linux / Windows).

**Acceptance:** All 10 share combinations reconstruct master key. Cross-tool interop bidirectional. Plain-language errors. Cross-OS vault portable.

**Blocks on:** T-02-34 + T-02-35 + T-02-36 (Shamir) + T-01-13 (Trust Vault).

**Estimate:** 0.5 session.

---

## T-08-131 — Acceptance EC-6: /redteam 2 consecutive rounds 0/0

**Implements:** EC-6 acceptance gate per `02-plans/04-redteam-cycle-plan.md` § 4.

**Action:** Run `/redteam` rounds at /implement convergence. Per `02-plans/04-redteam-cycle-plan.md` § 3 adversarial trigger:

- Round 1 must run 9 mechanical sweeps from scratch.
- If round 1 returns 0/0 quickly, MANDATORY adversarial pass on the cleanest shards before convergence counter advances.
- 2 consecutive rounds at 0 CRIT + 0 HIGH = EC-6 met.
- Counter resets on any new finding or feature. New /redteam round on every commit beyond a cited "frozen for redteam" sha.

**Acceptance:** Convergence record signed off by reviewer agent + security-reviewer agent + (if release-impacting) gold-standards-validator.

**Phase 01 ship gate:** Phase 01 ships when EC-6 met AND Wave 5 milestone gate green AND every other EC green.

**Blocks on:** Every Wave's Tier 2 + Tier 3 tests green; all 12 MED carry-forwards resolved.

**Estimate:** ~2-3 sessions across 2 redteam rounds + adversarial passes.

---

## Cross-references

- Test strategy: `02-plans/02-test-strategy.md`
- Redteam cycle: `02-plans/04-redteam-cycle-plan.md`
- Per-EC test ownership: `_index.md` § "EC acceptance map"
