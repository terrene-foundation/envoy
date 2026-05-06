# 09 — Permanent regression tests

**Purpose:** Regression tests for past failure modes; permanent (NEVER deleted per `rules/testing.md` § Regression Testing). One file per documented threat or finding.

**Source authority:** `specs/threat-model.md` (50 threats); `rules/testing.md` § Regression.

---

## T-09-140 — Regression T-018 visible-secret render check

**Implements:** Threat T-018 (visible-secret rendered out of envelope) per `specs/threat-model.md`.

**Action:** `tests/regression/test_t018_visible_secret.py` — Boundary Conversation S7 visible-secret pause; assert visible-secret never written to Ledger plaintext; assert Trust Vault encryption applied before persistence.

**Marker:** `@pytest.mark.regression`.

**Estimate:** 0.25 session.

---

## T-09-141 — Regression T-019 habituation low-engagement fallback

**Implements:** Threat T-019 (habituation form-flip).

**Action:** `tests/regression/test_t019_habituation_low_engagement_fallback.py` — Daily Digest engagement counter; form-flip on low-engagement signal.

**Marker:** `@pytest.mark.regression`.

**Estimate:** 0.25 session.

---

## T-09-142 — Regression T-023 authorship score seeding + signal Path B

**Implements:** Threat T-023.

**Action:**

- `tests/regression/test_t023_authorship_score_seeding.py` — Genesis Record seed asserts canonical AuthorshipScore = 0.
- `tests/regression/test_t023_signal_path_b.py` — Signal channel Path-B legal disposition documented.

**Marker:** `@pytest.mark.regression`.

**Estimate:** 0.25 session.

---

## T-09-143 — Regression T-070 clipboard autoclear (UI side-channel)

**Implements:** Threat T-070 (clipboard residue) per `specs/ui-platform.md`.

**Action:** `tests/regression/test_t070_clipboard_autoclear.py` — clipboard auto-clear after Shamir share copy / API key paste.

**Marker:** `@pytest.mark.regression`.

**Estimate:** 0.25 session.

---

## T-09-144 — Regression T-080 TLS 1.3 + cert pin

**Implements:** Threat T-080 (network) per `specs/network-security.md`.

**Action:** `tests/regression/test_t080_tls13_pin.py` — outbound TLS handshake pinned to TLS 1.3; cert pinning enforced for Foundation Health Heartbeat (if not de-scoped).

**Marker:** `@pytest.mark.regression`.

**Estimate:** 0.25 session.

---

## T-09-145 — Regression R2-H-01 algorithm_id wire form

**Implements:** R2-H-01 carry-forward fix (already covered in T-01-15, restated here for auditability).

**Action:** `tests/regression/test_r2_h_01_algorithm_id_wire_form.py` — producer-verifier wire-shape round-trip; 3-key form on disk per `specs/trust-lineage.md` L24.

**Marker:** `@pytest.mark.regression`.

**Note:** This test is created as part of T-01-15 LOAD-BEARING fix. Listed here for the regression suite manifest.

---

## T-09-146 — Regression R2-H-02 heartbeat stub partition

**Implements:** R2-H-02 carry-forward fix (already covered in T-01-27, restated here for auditability).

**Action:** `tests/regression/test_r2_h_02_heartbeat_stub_partition.py` — asserts client.maybe_record_flag invoked by ≥21 emit sites; zero production imports of 4 PhaseDeferredError modules.

**Marker:** `@pytest.mark.regression`.

**Note:** Test created as part of T-01-27.

---

## Cross-references

- Threat model: `specs/threat-model.md`
- Regression rule: `.claude/rules/testing.md` § Regression Testing
- Test directory: `02-plans/03-package-skeleton.md` § 3 `tests/regression/`
