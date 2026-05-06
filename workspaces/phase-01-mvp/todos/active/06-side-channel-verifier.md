# 06 — Side-channel: envoy-ledger-verifier (separate repo)

**Purpose:** Build the independent ledger verifier in a SEPARATE codebase per EC-9 source-isolation gate. Phase 01 ships Python-first as the EC-9 minimum; Rust sibling is a stretch goal that strengthens BET-3 but does NOT block Phase 01 release per disposition #4 (`journal/0005`).

**Source authority:**

- `01-analysis/07-independent-verifier-design.md` (separate repo design)
- `specs/independent-verifier.md` (additive Phase 01 spec)
- `02-plans/01-build-sequence.md` § Side-channel
- `journal/0005` § Disposition #4 (Python required, Rust stretch)

**Critical constraint:** ZERO source code shared with `envoy-agent`. The verifier RE-IMPLEMENTS the chain-walk + Ed25519 verification + canonical-JSON byte-comparison. Different agent (or different language Rust sibling) per `02-mvp-objectives.md` EC-9.

**Depends on:** T-01-19 (Ledger export bundle format) + T-01-20 (segment-boundary 4-key serializer R3-M-02). Can develop in parallel with Wave 1+2+3 once T-01-19 + T-01-20 ship.

---

## T-06-100 — Bootstrap envoy-ledger-verifier-python (separate repo)

**Action:** Create `terrene-foundation/envoy-ledger-verifier` GitHub repo. Bootstrap Python project:

- Apache-2.0 LICENSE.
- `pyproject.toml` with package name `envoy-ledger-verifier`.
- Top-level CLI entry `envoy-verify` (separate from `envoy` to prevent accidental shared-import; Phase 01 distribution = `gh release` artifact, not PyPI).
- README explaining the source-isolation thesis.
- ZERO imports from `envoy-agent` (verified by lint rule).

**Acceptance:**

- Repo exists at `terrene-foundation/envoy-ledger-verifier`.
- `git log` shows no commits authored from `envoy-agent` working tree.
- `pip install -e .` in a fresh venv succeeds.

**Capacity check:** ~150 LOC scaffolding; 2 invariants (separate-codebase rule; Apache-2.0 license); 0 call-graph hops.

**Estimate:** 0.5 session.

---

## T-06-101 — Implement verifier chain-walk + Ed25519 verification (Python)

**Implements:** `specs/independent-verifier.md` § Verify protocol.

**Action:** Re-implement (do NOT copy/import from envoy-agent):

1. Canonical-JSON byte-comparison per JCS-RFC-8785.
2. Ed25519 signature verification per entry.
3. Hash-chain walk verifying every `prev_hash → entry_hash` link.
4. Segment-boundary 4-key `algorithm_identifier` validation per `specs/independent-verifier.md` L35 (the canonical 4-key form per R3-M-02).

**Capacity check:** ~400 LOC; 5 invariants (JCS canonical-json byte-pin; Ed25519 verify per entry; chain-walk completeness; 4-key segment-boundary form; trust-anchor integrity); 2 call-graph hops.

**Blocks on:** T-06-100.

**Estimate:** 1 session.

---

## T-06-102 — Implement verifier trust-anchor + first-verification self-anchoring (Python)

**Implements:** `specs/independent-verifier.md` § Trust anchor.

**Action:** User-supplied trust anchor (Genesis public key); verifier remembers on first use (TOFU — Trust On First Use). Subsequent verifications check anchor match. Re-anchor command flagged as deliberate (re-anchoring is a security event).

**Capacity check:** ~200 LOC; 3 invariants (TOFU on first verify; anchor mismatch refused; re-anchor explicit); 1 call-graph hop.

**Blocks on:** T-06-101.

**Estimate:** 0.5 session.

---

## T-06-103 — Implement verifier tampering battery (Python — includes R3-M-01)

**Implements:** EC-4 mutation forms per `02-plans/02-test-strategy.md` § EC-4 (post-R3-M-01).

**Action:** Mutation battery — verifier MUST detect every form:

1. Single-bit flip in entry payload.
2. Insertion of forged entry (chain break).
3. Deletion of entry (chain break).
4. **Adjacent reorder** of two entries.
5. **Non-adjacent reorder** of entries i and j (j ≥ i+5) — R3-M-01 carry-forward.
6. Re-sign of mutated entry with stolen key (anchor mismatch detection).
7. Truncation of chain.
8. Genesis substitution (anchor mismatch detection).

**Tests added (in verifier repo):** `tests/test_tampering_battery.py` parametrized over 8 forms × N=1000-entry bundle.

**Capacity check:** ~300 LOC; 8 invariants (one per mutation form); 2 call-graph hops.

**Blocks on:** T-06-101 + T-06-102.

**Estimate:** 0.5 session.

---

## T-06-104 — Acceptance EC-4 Tier 3 (cross-repo subprocess invocation)

**Implements:** EC-4 acceptance gate.

**Action:** `tests/tier3/test_envoy_ledger_tampering_battery.py` (in `envoy-agent` repo) — produces N=1000-entry bundles via T-01-19 export; spawns `envoy-verify` subprocess per mutation form; asserts verifier emits the correct error code on every form.

**Acceptance:** Verifier detects all 8 mutation forms. Bundle byte-identity preserved on no-mutation case.

**Blocks on:** T-06-103 + T-01-19 + T-01-20.

**Estimate:** 0.25 session.

---

## T-06-105 — Acceptance EC-9 Tier 3: source-isolation gate (Python)

**Implements:** EC-9 acceptance gate per `02-mvp-objectives.md` + `01-analysis/07-independent-verifier-design.md` § EC-9.

**Action:** `tests/tier3/test_envoy_ledger_independent_verifier_ec9.py` — programmatic check:

1. Spawn `envoy-verify` as subprocess.
2. Assert ZERO `envoy.*` Python imports in the verifier process (introspect via `sys.modules`).
3. Assert verifier git remote is `terrene-foundation/envoy-ledger-verifier` (not `envoy-agent`).
4. Run a happy-path verify; assert exit 0.

**Acceptance:** Source-isolation invariant holds programmatically. EC-9 met for Phase 01 ship.

**Blocks on:** T-06-100 through T-06-104.

**Estimate:** 0.25 session.

---

## T-06-106 — STRETCH: Bootstrap envoy-ledger-verifier-rust

**Status:** STRETCH per disposition #4 — does NOT block Phase 01 release; strengthens BET-3 (source-isolation argument as falsifiability surface).

**Action:** Create Rust sibling project in `terrene-foundation/envoy-ledger-verifier` repo (in a `rust/` subdirectory or as a co-located Cargo workspace; design choice deferred to /implement). Re-implement chain-walk + Ed25519 verification + canonical-JSON byte-comparison in Rust.

**Acceptance:**

- Rust verifier passes the same 8-form tampering battery.
- Two-language verification produces byte-identical PASS/FAIL on the same bundle.

**Capacity check:** ~600 LOC Rust; 5 invariants (parity with Python verifier; Rust idiomatic crypto via `ed25519-dalek` or equivalent; serde JSON canonical mode; cargo workspace contract; no `envoy_*` Rust crates dependency); 2 call-graph hops.

**Blocks on:** T-06-101 (Python verifier as reference impl).

**Estimate:** 1.5 sessions (Rust track; non-blocking).

---

## T-06-107 — STRETCH: Acceptance EC-9 Rust verifier strengthens BET-3

**Action:** Document in `/codify` how the Rust verifier strengthens BET-3 (no single language can subvert ledger integrity).

**Status:** STRETCH; surfaced in /codify only if T-06-106 ships in Phase 01 wall-clock.

**Estimate:** 0.25 session.

---

## Side-channel milestone gate

Phase 01 ships when:

- Python verifier (T-06-100..T-06-105) GREEN — required for EC-9.
- Rust verifier (T-06-106..T-06-107) — STRETCH, non-blocking.

**Wall-clock estimate:** ~2 sessions Python (parallel to Waves 1–3); +1.5 sessions Rust stretch.

---

## Cross-references

- Verifier design: `01-analysis/07-independent-verifier-design.md`
- Verifier spec: `specs/independent-verifier.md` (additive Phase 01)
- Verifier-language disposition: `journal/0005-DECISION-todos-opening-dispositions.md` § Disposition #4
- Ledger export: T-01-19, T-01-20
- Mutation battery R3-M-01: `04-validate/round-3-implementation-comprehensive.md`
- BET-3: `briefs/00-phase-01-mvp-scope.md` (sovereignty thesis)
