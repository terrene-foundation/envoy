# 02 — Phase 01 MVP Objectives

**Document role:** Map every Phase 01 exit criterion to (a) the primitive it tests, (b) the BET it falsifies, (c) the structural deliverable that proves it, (d) the pre-declared acceptance gate. The rest of /analyze (shards 4–19) cites this doc for "what does this primitive's deep-dive earn against Phase 01 exit?"

**Date:** 2026-05-03 (shard 2 of /analyze).
**Status:** DRAFT — load-bearing for the per-primitive deep-dives.

---

## 1. Why exit criteria need re-grounding

ROADMAP §59–65 lists 6 exit criteria. Thesis §3.1 (Phase 01 row) expands these to 9 effective criteria. The expanded list is the operative one — ROADMAP is the contract, thesis is the elaboration, and shards 4–19 implementation deep-dives must serve all 9 because the thesis-level expansion is what the human accepted "AT ANY COSTS" (per thesis §3.1 phase-level clarifications).

The 6→9 expansion is not scope creep. Each thesis-row addition is an _operational_ unpacking of a ROADMAP exit criterion (e.g. ROADMAP §65 "Envoy Ledger exports a verifiable hash-chained log" implies _some_ verifier; thesis names that the verifier MUST be separately-codebased to be meaningful per BET-5).

## 2. The 9 effective Phase 01 exit criteria

### EC-1 — A first-time user completes Boundary Conversation end-to-end

**Source:** ROADMAP §60.

**What this structurally tests:** The Boundary Conversation primitive (Kaizen `BaseAgent` + scripted `Signature` → `EnvelopeConfig`) actually compiles a usable envelope from a 15-minute conversational interaction. If the primitive ships but no first-time user can complete it, the Phase 01 thesis is dead — the primary surface failed.

**BET falsified by failure here:** BET-12 (governance-primary-surface palatability). If users cannot complete the authoring ritual on the first try, the §2.3 category-move claim collapses to Little Snitch class.

**Primitive owned by:** Boundary Conversation (shard 8).

**Acceptance gate (pre-declared):** ≥3 distinct first-time-user sessions complete BoundaryConversation in ≤25 minutes (15min target +66% buffer for first-time users) with the conversation producing a parseable, envelope-compiler-accepted `EnvelopeConfig` AND the user reports "I understand what just happened" on a single-question post-session prompt.

**Why 3 sessions, not 1:** N=1 is anecdotal; N=3 establishes reproducibility while staying within Phase 01 budget. Larger N is Phase 02 cohort signal.

### EC-2 — 3 Grant Moments triggered and resolved correctly

**Source:** ROADMAP §61.

**What this structurally tests:** The Grant Moment primitive correctly intercepts an out-of-envelope action; surfaces a signed-consent UI in a channel; records the signed event in the Ledger; updates the envelope to reflect the grant. The 3 covers (a) approve, (b) decline, (c) approve-with-modification — the three meaningful resolution shapes.

**BET falsified by failure here:** BET-1 (authorship thesis) and BET-10 (default-deny experienced as agency). If Grant Moments don't fire reliably, default-deny is _theory only_; if they fire but resolution is broken, the authorship loop has no closure.

**Primitive owned by:** Grant Moment (shard 10) + Envelope compiler (shard 4) + Envoy Ledger (shard 6).

**Acceptance gate:** All three resolution shapes execute end-to-end with (a) ledger entries written and verifiable via independent verifier, (b) envelope state mutated correctly, (c) cascade-revocation of any descendant grant when the originating grant is revoked. Cascade revocation is a hard constraint per CHARTER §41 + `specs/trust-lineage.md`.

### EC-3 — Daily Digest renders at scheduled time with real data

**Source:** ROADMAP §62.

**What this structurally tests:** The Kaizen scheduled-agent infrastructure works in a Python `kailash-py` runtime; per-channel rendering aggregates the Ledger; delivery happens to at least one channel.

**BET falsified by failure here:** BET-8 (the new habit forms). The Daily Digest is the most-frequent ritual; if it doesn't fire reliably, the cadence story falls apart and the §3.2 capability table promise breaks.

**Primitive owned by:** Daily Digest (shard 11) + Envoy Ledger (shard 6) + Channel adapters (shard 16).

**Acceptance gate:** A scheduled Daily Digest fires at the user's local morning hour for ≥7 consecutive days, rendering across all configured channels with content sourced from the Ledger. Skipped days (e.g. user offline) MUST appear in the next-day digest as a back-fill, not be silently dropped.

### EC-4 — Envoy Ledger exports a verifiable hash-chained log

**Source:** ROADMAP §63.

**What this structurally tests:** The Ledger's hash chain is well-formed; export produces a canonical, parsable artifact; the chain is not "trust the producer" — a separately-codebased verifier can re-verify it.

**BET falsified by failure here:** BET-5 (Ledger as daily artifact) AND BET-1 (authorship as agency) — if the user cannot independently verify the Ledger, the audit-trail claim is theatre.

**Primitive owned by:** Envoy Ledger (shard 6) + Independent verifier (shard 7).

**Acceptance gate:** A Ledger exported by `envoy ledger export` is verified by a CLI tool that (a) lives in a different repo / package, (b) shares zero source code with the Envoy codebase, (c) is implemented in a different language OR by a different agent without reference to the producer's source. The verifier MUST detect any tampering attempt (single-bit flip in any payload field; insertion / deletion / reorder of any entry).

This is the strongest Phase 01 acceptance gate — it is the only one that proves the security primitive (hash chain) works under adversarial assumption rather than developer assumption.

### EC-5 — Trust Vault backup via SLIP-0039 Shamir works (3-of-5 reconstruct test)

**Source:** ROADMAP §64.

**What this structurally tests:** The `slip39` Python package wiring produces 5 shares; any 3 of the 5 reconstruct the original; the paper-shard format is human-usable; cross-tool interop works (a SLIP-0039 share generated by Envoy is reconstructable by `python-shamir-mnemonic` or by a Trezor device).

**BET falsified by failure here:** BET-9a (Shamir recovery learnable) AND BET-9b (vault portability). The sovereignty narrative depends on this; if Shamir doesn't work, "MY keys" is hollow.

**Primitive owned by:** Shamir 3-of-5 recovery (shard 15) + Trust store (shard 5).

**Acceptance gate:** (a) The 3-of-5 reconstruct test passes for all C(5,3)=10 share combinations, (b) The Boundary Conversation pauses for the backup ritual at least once, (c) An Envoy-generated SLIP-0039 share reconstructs successfully via a non-Envoy tool (`python-shamir-mnemonic` minimum; Trezor SDK if accessible), (d) Reconstruction failure produces a clear-language error message, not a binary-data dump.

### EC-6 — `/redteam` passes: spec-compliance AST/grep verified, 0 CRITICAL/HIGH findings, 2 clean rounds

**Source:** ROADMAP §65.

**What this structurally tests:** The implementation does not drift from frozen specs (per `skills/spec-compliance/SKILL.md` AST/grep protocol); no orphan primitives (per `rules/orphan-detection.md`); no stub mocks where production code is required.

**BET falsified by failure here:** indirectly all BETs — uncaught CRIT/HIGH findings mean some primitive's behaviour is undefined under stress, which makes BET measurements meaningless.

**Primitive owned by:** Every primitive deep-dive shard contributes; redteam is shards 23–24.

**Acceptance gate:** 2 consecutive `/redteam` rounds with 0 CRITICAL + 0 HIGH (per Phase 00 convergence pattern at `rules/specs-authority.md` MUST Rule 5b inherited semantics). MEDIUM and LOW findings disposed (fix or document defer).

### EC-7 — Single user onboards via any of 8 channels (CLI + Web + 6 messaging)

**Source:** Thesis §3.1 (expansion of ROADMAP §60).

**What this structurally tests:** The 8 channel adapters are wired symmetrically — onboarding is initiated from any of CLI, Web, iMessage, Telegram, Slack, Discord, WhatsApp, Signal and produces equivalent onboarding state (first-time user lands in Boundary Conversation regardless of entry channel).

**BET falsified by failure here:** BET-11 (channel-as-UI thesis). If onboarding works only on CLI, the channel-native thesis is unfalsified-because-not-attempted at MVP.

**Primitive owned by:** Channel adapters (shard 16) + Boundary Conversation (shard 8).

**Acceptance gate:** A first-time user completes EC-1 successfully starting from each of the 8 channels (8 × N=3 sessions = 24 successful onboardings). Per-channel deviation from CLI baseline (in completion time, in message count) MUST stay within 2× — channels are not equivalent perfectly, but they must be functionally interchangeable.

### EC-8 — User operates for a week across channels

**Source:** Thesis §3.1.

**What this structurally tests:** Cross-channel coherence. A grant approved on Telegram is honoured by an action initiated from Slack 3 days later. The Ledger spans channels coherently. No state drift between channel adapters.

**BET falsified by failure here:** BET-11 directly; BET-4 (cross-channel coherence) which is part of BET-11.

**Primitive owned by:** Trust store (shard 5) + Ledger (shard 6) + Envelope compiler (shard 4) + Channel adapters (shard 16).

**Acceptance gate:** A 7-day operating window across ≥4 of the 8 channels produces (a) zero state-drift findings (per a cross-channel state-equivalence test that runs daily), (b) no double-billing in Budget tracker against multi-channel actions, (c) cascade revocation of a Day-1 grant correctly revokes a Day-6 child grant initiated from a different channel.

### EC-9 — Independent ledger verifier ships separately-codebased

**Source:** Thesis §3.1 (operational unpacking of ROADMAP §63).

**What this structurally tests:** Same as EC-4 but the _verifier itself_ is a Phase 01 deliverable — it cannot be deferred. The verifier's existence is the Phase 01 acceptance proof of the security primitive.

**BET falsified by failure here:** BET-5; redundantly BET-10 (default-deny as agency — if no one can verify, the audit trail isn't proof).

**Primitive owned by:** Independent verifier (shard 7).

**Acceptance gate:** A verifier CLI tool ships in a separate repo (proposed: `envoy-ledger-verifier` under `terrene-foundation/`), implemented without reference to Envoy producer source, in either Python (different agent / different package) or Rust (different language entirely — preferred per `rules/testing.md` Tier 3 logic of cross-implementation verification). Verifier passes EC-4's tampering-detection battery.

## 3. Cross-cutting non-exit-criterion deliverables

These are NOT exit criteria but Phase 01 ships them because they are structural prerequisites for _operating_ the MVP, not for _proving_ it works:

| Deliverable                                   | Why structural                                                                                                                                                         | Source                    |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| `pipx install envoy-agent` distribution       | EC-1 requires installation; pipx is the Phase 01 distribution per ADR-0001 phase-migration                                                                             | shard 19                  |
| `kailash-runtime` abstract interface stub     | ADR-0001 + ADR-0009 require the abstract interface even though only `kailash-py` is wired in Phase 01; Phase 02 wiring is mechanical iff this is correctly defined now | shard 18                  |
| Authorship Score primitive + posture gate     | Thesis §2.3 + §3.3 + BET-12; without this, DELEGATING / AUTONOMOUS posture transitions have no enforcement and the §2.2 thesis collapses to "consent to envelope"      | shard 9                   |
| Foundation Health Heartbeat                   | Most BETs require Heartbeat measurement to be falsifiable; if Heartbeat ships in P02, several BETs are non-falsifiable until then                                      | shard 17 (DECISION shard) |
| Connection Vault (minimal — keychain wrapper) | Channel adapters need API keys to function; without Connection Vault, channel adapters store secrets ad-hoc                                                            | shard 14                  |
| Budget tracker                                | Financial constraint dimension enforcement; threshold callbacks fire Grant Moments                                                                                     | shard 12                  |
| Model adapter                                 | Boundary Conversation LLM calls + Daily Digest text generation; without model adapter, no LLM-backed primitive functions                                               | shard 13                  |

## 4. The Phase 01 ship predicate

**We ship Phase 01 when:**

```
   EC-1 ∧ EC-2 ∧ EC-3 ∧ EC-4 ∧ EC-5 ∧ EC-6 ∧ EC-7 ∧ EC-8 ∧ EC-9
∧ all 7 cross-cutting deliverables present
∧ EC-6 specifically achieves 2 consecutive /redteam rounds at 0 CRIT + 0 HIGH
∧ Phase 00 external gates have NOT regressed (the Foundation board has not declined ADR-0009; trademark sweep has not blocked Envoy* family)
```

The conjunction is strict — partial completion is NOT a ship event. Per `rules/zero-tolerance.md` Rule 1 + Rule 6: if EC-N fails, EC-N gets fixed before ship; "good enough across 8 of 9" is not a release.

The external-gate clause is a non-regression check, not a positive-completion check — Phase 01 internal release does not require board endorsement (codename `envoy-agent` is acceptable for internal distribution). Phase 02 distribution requires the gates closed.

## 5. Failure-mode disposition

If by shard 24 (final redteam round) any EC has not passed:

| EC failed | Disposition                                                                                                                     |
| --------- | ------------------------------------------------------------------------------------------------------------------------------- |
| EC-1      | BLOCKING — re-design Boundary Conversation; re-shard 8                                                                          |
| EC-2      | BLOCKING — surface the broken primitive (Grant Moment vs Envelope vs Ledger); re-shard owning primitive                         |
| EC-3      | BLOCKING — Kaizen scheduled-agent gap; either fix `kailash-py` upstream or implement Envoy-new-code                             |
| EC-4      | BLOCKING — Ledger or Verifier broken; re-shard 6 or 7                                                                           |
| EC-5      | BLOCKING — `slip39` integration; usually Envoy-side, rarely upstream                                                            |
| EC-6      | BLOCKING — implementation drift from spec; per `rules/zero-tolerance.md` Rule 1, fix before ship                                |
| EC-7      | DEGRADE-ACCEPTABLE — execute pre-declared de-scope #1 (reduce 6 messaging channels to 3); EC-7 acceptance becomes 5-channel set |
| EC-8      | BLOCKING — cross-channel coherence is the channel-as-UI thesis; if broken, the thesis is at risk                                |
| EC-9      | BLOCKING — required by the security primitive; defer is not acceptable                                                          |

## 6. Cross-references

- Phase 01 brief: `workspaces/phase-01-mvp/briefs/00-phase-01-mvp-scope.md`
- Inheritance: `workspaces/phase-01-mvp/01-analysis/00-inheritance-from-phase-00.md`
- Sharding: `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 5
- ROADMAP: `ROADMAP.md` §59–65
- Thesis: `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` §3.1 + §5
