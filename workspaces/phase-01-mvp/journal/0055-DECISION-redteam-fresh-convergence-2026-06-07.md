---
type: DECISION
date: 2026-06-07
created_at: 2026-06-07T00:00:00Z
author: co-authored
session_id: continue-from-0054
session_turn: 1
project: phase-01-mvp
topic: Fresh full-surface /redteam re-converges at 0 CRIT/0 HIGH after F8/F9/F19 reset the counter; systemic test-location citation drift fixed on shipped-primitive specs
phase: redteam
tags:
  [
    redteam,
    convergence,
    ec-6,
    spec-accuracy,
    test-location-citations,
    autonomize,
    rate-limit-workflow-fix,
  ]
---

# 0055 — DECISION: fresh full-surface /redteam re-converges at 0 CRIT/0 HIGH

**Posture:** L5_DELEGATED. **HEAD at start:** `5768af8`. **Suite:** 1705 passed / 9 skipped / 3 xfailed (re-derived three times this cycle; receipt).

## Verdict

The fresh full-surface `/redteam` (owed because F8/F9/F19 landed AFTER the 0053 convergence, resetting the 2-clean-round counter per `rules/specs-authority.md` Rule 5b) **CONVERGES at 0 CRITICAL + 0 HIGH across 2 consecutive clean rounds (Round 3 + Round 4)**. Full receipts + per-round agent IDs: `04-validate/rounds-1-4-fresh-convergence-2026-06-07.md`.

- Round 1: workflow spec-ledger emitted SC-01 (refuted) + SC-02 (LOW, fixed); 11 workflow dims rate-limited → covered by deterministic mechanical backbone + semantic probe agent, which surfaced A-C1/E1/F1 (HIGH-class).
- Round 2: 1 HIGH (F1-r2 — a this-session-introduced data-model.md over-claim) → fixed.
- Round 3: comprehensive independent re-derivation — **0 findings**. (1st clean.)
- Round 4: adversarial ship-readiness breaker — **0 CRIT / 0 HIGH / 1 LOW** (R4-L-01, deferred-tracked); all 5 attack surfaces SOUND. (2nd clean.)

## What was fixed (13 files; PR pending)

The dominant finding class this cycle was **`## Test location` citation drift on Phase-01-shipped specs** — the exact SCA-01/02 class 0053 graded HIGH and fixed for boundary-conversation + trust-lineage, now found in 8 more specs. A full-corpus sweep found 178 phantom Phase-01-style citations across ~24 specs; the discriminator (redteam disposition #4) splits them:

- **HIGH drift (fixed):** a cited test for a Phase-01-SHIPPED primitive whose real test exists under a different name. Fixed in 8 specs (classification-policy, session-state, envelope-model, connection-vault, data-model, model-adapter, runtime-abstraction, distribution) by re-pointing to the real tests + adding `## Out of scope (this phase)` carve-outs. **Co-owner approved (Option A)** the shipped-primitive scope expansion (it edits the frozen corpus, which the brief gates to HIGH gaps).
- **By-design LOW (left as-is):** a cited test for a genuinely-deferred future-phase feature (no test anywhere). The ~16 future-phase specs (a2a, envelope-library, enterprise, heartbeat, foundation-ops, ledger-merge, monthly-report, network-security, remote-time-anchor, shared-household, skill-ingest, sub-agent-delegation, ui-platform, weekly-review, cross-domain-flows, tool-output-sanitization) stay as-is — verified zero real tests exist (a2a/skill-ingest/shared-household/weekly confirmed empty).

Other fixes: SC-02 (`RuntimeIdentity` package re-export); F1 (3 storyboards' Phase-01 CLI-surface notes); F1-r2 (data-model duress over-claim correction). The spec edits are **citation-only** (Test-location / Out-of-scope sections; no dataclass/signature/domain-truth change), so Rule 5b full-sibling re-derivation was not triggered — cross-spec consistency was nonetheless re-verified clean in rounds 2+3 (the data-model↔trust-vault duress contradiction was the one cross-spec defect, caught + fixed).

## Tooling fix (durable)

`redteam-round.mjs` hit API 429 on all 12 concurrent finders (the `worktree-isolation.md` Rule 4 pattern: 4+ concurrent Opus agents die at 30-45s). Root-cause-fixed to **wave-batch finders + verifiers in groups of 3** and to report **`failed_to_emit`** dimensions (closing the silent-budget-overrun gap the session notes warned about). Even wave-batched, the schema-forced StructuredOutput finders stayed unreliable under the live throttle; the reliable convergence path was direct mechanical sweeps + **schema-less sequential agents** (1 at a time = no concurrency throttle) — which rounds 1-4 used.

## Deferred (value-anchored, by-design — NOT CRIT/HIGH)

- **R4-L-01 (LOW):** `vault.py:768,804` `TODO(T-15)` Sensitive[bytes] wrapper — tracked iterative-TODO (Rule 6), Phase-02 hardening; code fully implemented. Anchor: T-15 (`todos/active/01-wave-1-foundation.md:203`).
- Unchanged external/structural gates: F2 (separate-repo verifier / EC-9), F4 (full EC-6, blocked on F2), F5.2-grant + F21 (Phase-02 substrate), F20 (Wave-4 Nexus InboundRouter), F5.3 (Windows host), F22 (kailash-py#1245), F23 (threat-coverage meta-gate, Phase-02).

## Why (decision rationale)

The codebase's BEHAVIOR was already sound (0053 + 0054); this cycle's findings were almost entirely **documentation-vs-code drift** — specs/storyboards over-claiming or mis-pointing Phase-01 coverage. The genuinely-actionable work was making the frozen-spec test-location pointers accurate for the shipped-primitive specs (consistent with 0053's SCA-01/02 precedent + `rules/zero-tolerance.md` Rule 1a scanner-surface symmetry). Round 2 catching a fix that itself introduced drift (F1-r2) is the load-bearing evidence that 2 independent re-derivation rounds — not just 1 + a self-report — are required for a real convergence.

## Receipts

- Round report: `04-validate/rounds-1-4-fresh-convergence-2026-06-07.md`.
- Agents: probe `a4b11fbf3b1e727c6`; R2 `a96c66de3d01c77f6`; R3 `aa378122b3526c9d2`; R4 `aa05eecd8934d3155`. Workflow `wqvgvnvr2`.
- Suite re-derived green ×3 (1705 passed). Prior convergence: 0053; this cycle continues 0054.

## For Discussion

1. **Counterfactual:** had Round 4 used the same methodical-verifier lens as Round 3 (rather than the adversarial-breaker lens), would it have independently re-derived the hash-chain tamper-detection + all-10-C(5,3)-Shamir-combos evidence, or just re-confirmed Round 3's framing? Does the lens-diversity between consecutive clean rounds materially strengthen the convergence claim, or is it ceremony once Round 3 is clean?
2. **Data-specific:** the full-corpus sweep found 178 phantom Phase-01-style citations; only ~30 (8 shipped-primitive specs) were fixed, ~148 left as by-design future-phase. Is the frozen-full-product-spec model (specs describe all 4 phases, citing where tests WILL live) worth the recurring `/redteam` cost of re-distinguishing shipped-drift from future-by-design every cycle — or should future-phase `## Test location` sections be converted to an explicit `## Tests scheduled to land` shape (like trust-vault.md already uses) to make the discriminator mechanical?
3. F1-r2 was an error I introduced while fixing A-C1's class. Should the reviewer/mechanical sweep gain a "ships-claim ↔ real-impl" cross-check (every `Phase 01 ships X` sentence must grep to a non-stub impl) so this over-claim class is caught at author-time rather than at the next round?
