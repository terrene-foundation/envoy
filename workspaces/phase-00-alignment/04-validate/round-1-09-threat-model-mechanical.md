# Round 1 Mechanical Sweep — Doc 09 Threat Model

**Date:** 2026-04-21
**Scope:** Mechanical sweeps — threat-enumeration completeness vs doc 00 carry-forwards, STRIDE category coverage, primitive cross-reference integrity, phase-tag alignment with doc 00, threat-to-mitigation matrix 1:1 parity.
**Input:** `workspaces/phase-00-alignment/01-analysis/09-threat-model.md` + `00-thesis-and-scope.md` (v2 converged) + `03-primitive-reconciliation.md`.

## Summary

| ID   | Severity | One-liner                                                                                                                                                                                                                                                                  |
| ---- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M-01 | **HIGH** | R (Repudiation) STRIDE category under-represented — no Ledger rollback / fork / replay threat catalogued. Envoy's Ledger is hash-chained append-only, which means repudiation defense is structural, but the threats that stress that defense deserve explicit enumeration |
| M-02 | MEDIUM   | D (Denial of service) has only T-090 as the sole entry; budget-exhaustion-fraud-style DoS + Envelope Library DoS + Heartbeat-OHTTP DoS not enumerated                                                                                                                      |
| M-03 | MEDIUM   | Agent-specific "goal drift" threat not catalogued — multi-turn agent may re-interpret user intent; Envoy's Ledger doesn't structurally prevent it                                                                                                                          |
| M-04 | MEDIUM   | Covert channel via Heartbeat boolean-flag pattern not named; STAR k-anonymity bounds but does not eliminate                                                                                                                                                                |
| M-05 | MEDIUM   | Sybil attack on Envelope Library Community tier not catalogued — reputation ranking assumes distinct publishers                                                                                                                                                            |
| M-06 | MEDIUM   | Replay attack on signed Grant Moments not catalogued — signed record without context-binding nonce is replayable                                                                                                                                                           |
| M-07 | LOW      | 16 distinct `specs/*.md` primitive files referenced; only 4 currently exist as target docs (none yet written); the rest require forward-references during specs/ build                                                                                                     |
| M-08 | LOW      | `specs/threat-model.md` self-reference in T-002 should point to this doc's canonical T-002 section not a future spec — or deferred to when `specs/threat-model.md` is derived                                                                                              |
| M-09 | LOW      | Residual risk register entry for "post-quantum migration timing" points at a future date but is not tied to a specific doc-level trigger                                                                                                                                   |
| M-10 | LOW      | Phase gating §7 says "Every release" cadence for regression tests + dependency CVE scan — not tied to concrete release criteria (pre-commit vs CI vs tagged-release)                                                                                                       |

## Verification results

### ✅ Doc 00 §13 carry-forwards complete

All 7 named threats present as T-001 through T-007:

- Clock-trust → T-001
- Household-adversarial → T-002
- Ledger retention + GDPR → T-003
- Streaming LLM pre-sign → T-004
- Semantic envelope checks → T-005
- Shamir social-graph → T-006
- Credential storage → T-007

### ✅ Threat catalog parity with mitigation matrix

23 threats in §3 → 23 rows in §4 mitigation-to-primitive matrix. One-to-one. Verified via grep.

### ✅ Threat IDs consistent (T-00X, T-01X, T-02X … series)

No duplicates. Grouping by category (00X carry-forwards, 01X prompt injection, 02X supply chain, 03X provider, 04X device, 05X Foundation infra, 06X runtime, 07X side channel, 08X network, 09X DoS) is meaningful.

### ✅ Phase tagging aligns with doc 00

Every threat's "phase when mitigation lands" column in §4 is consistent with doc 00 §3.1 phase scopes:

- Phase 01 tags match what doc 00 lists as Phase 01 primitives.
- Phase 02 tags match what doc 00 lists as Phase 02 primitives (binary distribution, Foundation Health Heartbeat, mobile, runtime picker, Envelope Library FV tier, SKILL.md translator).
- Phase 03 tags match Shared Household + ritual cadence + per-dimension posture.
- Phase 04 tags match wasm sandbox, multi-provider verification, hidden envelope, Organization tier.

### ✅ STRIDE coverage (partial)

- S (Spoofing): T-002 ✓, T-021 ✓, T-030 ✓, T-080 ✓
- T (Tampering): T-001 ✓, T-004 ✓, T-030 ✓, T-080 ✓
- **R (Repudiation): UNDER-REPRESENTED — see M-01**
- I (Information disclosure): T-003 ✓, T-006 ✓, T-007 ✓, T-040 ✓, T-042 ✓, T-052 ✓, T-053 ✓, T-070 ✓, T-080 ✓
- D (Denial of service): T-090 ✓ (only one — see M-02)
- E (Elevation of privilege): T-002 ✓, T-007 ✓, T-020 ✓, T-040 ✓, T-041 ✓, T-042 ✓, T-060 ✓

Envoy-specific categories:

- PI (Prompt injection): T-010, T-011 ✓
- GOV (Governance bypass): T-001, T-004, T-005 ✓
- UX (User-experience threat): T-002 (partial), T-041 ✓
- SC (Supply chain): T-020, T-021, T-050, T-051, T-060 ✓

### Distinct spec-file references (16 files — forward-references for specs/ build)

`specs/ledger.md`, `specs/remote-time-anchor.md`, `specs/shared-household.md`, `specs/threat-model.md`, `specs/runtime-abstraction.md`, `specs/envelope-model.md`, `specs/shamir-recovery.md`, `specs/connection-vault.md`, `specs/grant-moment.md`, `specs/skill-ingest.md`, `specs/envelope-library.md`, `specs/model-adapter.md`, `specs/trust-vault.md`, `specs/distribution.md`, `specs/foundation-health-heartbeat.md`, `specs/ui-platform.md`, `specs/network-security.md`.

**Note:** When specs/ is built (task 6 in Envoy pipeline), these 16 files become the primitive-inheritance substrate for threat tests. Each mitigation test must land before the corresponding threat is declared mitigated.

---

## Detail on HIGH findings

### M-01 — R (Repudiation) category under-represented

**Gap:** Envoy's Ledger is hash-chained append-only — structurally excellent for non-repudiation. But the threats that stress this property are not enumerated. An auditor reviewing the threat model who is a crypto-protocol specialist will flag: "What about rollback attack? Fork attack? Replay?"

**Missing threats (each should be in T-100 series):**

- **T-100 — Ledger rollback attack.** Attacker replaces current Ledger with an older, smaller version. In multi-device scenarios, device A's current Ledger can be overwritten during sync by device B's stale Ledger. T-053 mentions "versioning + integrity log" but as a sync-integrity primitive, not a named threat.
- **T-101 — Ledger fork attack.** User operates Envoy offline on device A and device B; they reconnect; how is conflict resolved? Attacker may exploit reconciliation logic. Need explicit fork-resolution primitive.
- **T-102 — Grant Moment replay.** A previously-signed Grant Moment is intercepted, held, replayed later in a different context. Without nonce + context-binding, signature is valid but intent is forged. Envelope-compile-time nonce required.
- **T-103 — Delegation cycle attack on cascade revocation.** If the delegation graph contains a cycle (A delegates to B, B delegates to A, via an envelope-bug or adversarial construction), cascade revocation may loop or fail. Rust source has `verify_chain()` at `crates/eatp/src/delegation.rs` that walks ancestors for cycles — but cascade revocation semantics on cyclic chains are untested.
- **T-104 — Signed-record non-binding to envelope version.** If Envelope Config is mutable and a Grant Moment references a capability declared in Envelope v3 but Envelope has rolled back to v2, is the signature still valid? Should fail.

**Why HIGH:** Non-repudiation is a structural claim in the Ledger design. A gap here undermines the primary-surface test (§8 Test-2 "every action emits a signed record before execution"). These threats test the promise's robustness.

**Recommended action:** Add a §3.5 "Ledger + trust-chain integrity threats" subsection with T-100 through T-104. Each needs attacker-model / attack-path / mitigation / primitive / test / residual.

### M-02 — D (Denial of service) underrepresented

**Gap:** Only T-090 (local DoS on runtime) catalogued. Foundation-infra DoS, Envelope Library flood, Heartbeat resource exhaustion, budget-exhaustion-fraud-via-malicious-skill all missing.

**Missing threats:**

- **T-091 — Foundation infrastructure DoS.** Envelope Library, OHTTP relay, sync node flood. Users unable to fetch FV envelopes or submit Heartbeat.
- **T-092 — Envelope Library spam flood.** Malicious actor publishes 1000s of envelopes to overwhelm reviewers / gameify ranking.
- **T-093 — Budget exhaustion fraud.** Malicious skill induces expensive actions (high-cost LLM calls, rate-limit-triggering API calls) that deplete user's budget.
- **T-094 — LLM context-window exhaustion attack.** Adversarial input inflates context such that critical instructions / envelope-context are pushed out before tool-call decision.

**Why MEDIUM (not HIGH):** DoS is typically medium-impact — annoying but not catastrophic. However, T-093 (budget exhaustion fraud) crosses into financial harm.

**Recommended action:** Add T-091 through T-094.

### M-03 — Goal drift not catalogued

**Gap:** In multi-turn agent sessions, the user's original intent can be re-interpreted by the model over time. A user who said "find me flights" in turn 1 may end up with an agent that in turn 10 is booking hotels, rental cars, and inventing itinerary extensions — because the model's "helpful" instincts extrapolate.

Not a malicious threat per se, but a **class of GOV failure** unique to agents. Envoy's Authorship Score + posture-ratchet + envelope are structural defenses, but explicit goal-tracking is missing.

**Missing threat:**

- **T-012 — Goal drift.** Agent in multi-turn operation re-interprets user intent, performs actions user never authorized (not a prompt injection — just over-interpretation).

**Why MEDIUM:** The thesis's authorship claim requires that what the agent does still be traceable to user intent. Goal drift is the non-malicious version of the thesis failing.

**Recommended action:** Add T-012. Mitigation likely involves: explicit intent-scoping Grant Moment at turn N (every N turns re-confirm); Ledger entry captures "goal state" as a distinct record type; Weekly Posture Review surfaces drift.

### M-04 — Covert channel via Heartbeat

**Gap:** Foundation Health Heartbeat has ~20 boolean flags aggregated via STAR. A compromised Envoy instance could:

- Encode info in which flags it sets.
- Rotate per-install ID in a pattern that leaks info.
- Time submissions to create a low-bandwidth covert channel despite k-anonymity.

STAR k-anonymity bounds _individual_ identification but does not prevent a compromised population from collectively signaling.

**Missing threat:**

- **T-054 — Heartbeat covert channel.** Compromised Envoy client encodes info in flag patterns / ID rotation / submission timing; aggregator sees a structured signal.

**Why MEDIUM:** Requires attacker control of Envoy client-side. If attacker has that, Heartbeat is a small leak relative to full device compromise. But structural covert-channel defense is worth naming.

**Recommended action:** Add T-054. Mitigation: client-side code signing + reproducible builds (already mitigations for T-060); plus differential privacy on flag-set entropy.

### M-05 — Sybil on Envelope Library Community tier

**Gap:** Community-tier reputation (adoption × (1 − revocation rate)) assumes distinct publishers. A single attacker can:

- Create N publisher keys.
- Cross-install each publisher's envelopes from the attacker-owned "users" to inflate adoption count.
- Gain high rank via Sybil inflation.

**Missing threat:**

- **T-021b — Envelope Library Sybil attack** (or new T-022).

**Why MEDIUM:** Community tier is a Phase 03 primitive. Ranking is not the only defense — Foundation-Verified tier is the high-trust path; Community is explicitly "unreviewed." But ranking being gamed lets low-reputation envelopes climb.

**Recommended action:** Add T-022. Mitigation: identity-proofing at publisher signing (proof-of-work or proof-of-stake or real-world identity via Foundation vouch); publisher-fork tracking (new publisher whose envelopes are forks of existing ones scored with lower weight).

### M-06 — Grant Moment replay

**Gap:** Grant Moments are signed Delegation Records. A signed record without a binding nonce (content + timestamp + envelope-version + intent hash) can be replayed. The doc does not explicitly specify the nonce field.

**Missing threat:**

- **T-008 — Grant Moment replay.** A captured signed Grant Moment is replayed to authorize a different action in a different context.

**Why MEDIUM:** Standard crypto pitfall; likely caught in implementation. But naming it in the threat model means the Ledger format spec (doc 04) carries the binding-nonce requirement from the start.

**Recommended action:** Add T-008. Mitigation: Grant Moment record includes (action-intent-hash, envelope-version, timestamp, random-nonce, signer-Genesis-Record-hash); signature covers all of these; replay detected by envelope-version + timestamp drift.

---

## Resolution summary

- **1 HIGH** (M-01 — R category gap). Add T-100 through T-104 subsection.
- **5 MEDIUM** (M-02 DoS gaps, M-03 goal drift, M-04 covert channel, M-05 Sybil, M-06 replay). Add T-008, T-012, T-022, T-054, T-091–T-094.
- **4 LOW** (M-07 spec-file forward-refs, M-08 self-reference, M-09 PQ-migration trigger, M-10 release cadence). Defer to `specs/` build time + doc-level polish.

Total new threats to enumerate in Round 2 fix pass: **10 additional threats** (T-008, T-012, T-022, T-054, T-091, T-092, T-093, T-094, T-100, T-101, T-102, T-103, T-104 — 13 if we count them all, but T-100 series is a new subsection with 5 entries).

Final doc 09 threat count after R2 integration: **23 → 33+ threats**, still manageable.
