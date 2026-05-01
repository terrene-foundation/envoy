# Round 2 Review — Doc 09 Threat Model v2

**Date:** 2026-04-21
**Reviewer role:** Quality reviewer — verification, not discovery.
**Input:** `/Users/esperie/repos/dev/envoy/workspaces/phase-00-alignment/01-analysis/09-threat-model.md` (v2, 866 lines).
**Scope of review:** Round 1 CRITICAL + HIGH disposition check, internal consistency (catalog↔matrix), doc-00-v3 cross-reference accuracy, regressions introduced by v2, spec-sketch adequacy for the new threats.

---

## Summary

| Severity     | Count | Items                                                                                      |
| ------------ | ----- | ------------------------------------------------------------------------------------------ |
| **CRITICAL** | **0** | —                                                                                          |
| **HIGH**     | **2** | R2H-1 threat-count arithmetic wrong; R2H-2 T-013 ReasoningCommit structurally insufficient |
| **MEDIUM**   | **8** | R2M-1 … R2M-8                                                                              |
| **LOW**      | **3** | R2L-1 … R2L-3                                                                              |

**Exit criterion:** 0 CRITICAL + ≤ 2 HIGH → **CONVERGED** (within the 2-HIGH allowance for doc 09's inherent complexity).

**Disposition recommendation:**

- **Before doc 02 entry:** R2H-1 (arithmetic) must be fixed — trivial. R2H-2 (ReasoningCommit adversary-model gap) should be acknowledged explicitly in the residual-risk register even if design stands.
- **Track for v3 / future rounds:** R2M-1 through R2M-8 as named, non-blocking.

All seven Round 1 CRITICAL findings (F-01, F-02, F-03, F-04, C-1, C-2, C-3) are RESOLVED. All Round 1 HIGH findings are addressed, deferred with acknowledgement, or explicitly out of the user-approved Cluster A–F scope.

---

## Section A — Round 1 CRITICAL disposition (7 of 7)

| R1 CRIT  | Topic                                 | Disposition in v2                                                                                                                                                                | Status                     |
| -------- | ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| **F-01** | T-050/T-060 boundary                  | Split into T-050a (mirror compromise, valid signature) + T-050b (signing-key compromise); T-060 footer explicitly notes defeat-by-T-050b + cross-references.                     | **RESOLVED**               |
| **F-02** | Feedback-loop Ledger poisoning        | New T-012 at §3.2. `content_trust_level` field, signature-scope limitation, entry-sanitization wrapping, required-kwarg enforcement via `rules/orphan-detection.md` grep.        | **RESOLVED**               |
| **F-03** | Trust-lineage cycle / cascade DoS     | New T-103 at §3.5. DAG-only invariant + cycle detection at record-creation + forward-walk-only cascade. Explicit 15+ cycle-construction test corpus in §7 gates.                 | **RESOLVED**               |
| **F-04** | Budget-exhaustion fraud               | New T-093 at §3.9. Per-call + aggregate velocity + session-vs-month budget separation + high-velocity Grant Moment trigger.                                                      | **RESOLVED**               |
| **C-1**  | Sub-agent envelope-scope forgery      | New T-105 at §3.5 + new `specs/sub-agent-delegation.md`. Subset-proof format covering 5 constraint dimensions + cascade-revocation.                                              | **RESOLVED**               |
| **C-2**  | Chain-of-thought compositional bypass | New T-013 + ReasoningCommit record type + composition-aware envelope + turn-N goal-reconfirmation. (See R2H-2 for gap in adversarial adequacy.)                                  | **RESOLVED (with caveat)** |
| **C-3**  | Offline fork reconciliation           | New T-101 + new `specs/ledger-merge.md` with CRDT merge sketch (Lamport clocks, `merged_from` records, deterministic merge). §9 open question flags LWW-vs-causality unresolved. | **RESOLVED (with caveat)** |

---

## Section B — Round 1 HIGH disposition (walk-through)

| R1 HIGH | Topic                                 | v2 disposition                                                          | Status                  |
| ------- | ------------------------------------- | ----------------------------------------------------------------------- | ----------------------- |
| F-05    | Multi-turn accumulated injection      | T-014 + per-turn prompt reset + structured trusted/untrusted framing    | RESOLVED                |
| F-06    | Context-window exhaustion             | T-015 + system-prompt pinning + prompt-size budget + re-read checkpoint | RESOLVED                |
| F-07    | Authorship Score bypass               | T-023 + semantic de-dup + minimum-impact + annual revalidation          | RESOLVED                |
| F-08    | Envelope Library Sybil                | T-022 + identity proofing + fork tracking + adoption cap                | RESOLVED                |
| F-09    | Rollback / fork attack                | T-100 (rollback) + T-101 (fork) distinct                                | RESOLVED                |
| F-10    | Delegation/Grant-Moment replay        | T-008 (Grant Moment replay) + T-102 (Delegation Record replay) distinct | RESOLVED                |
| F-11    | Heartbeat covert channel              | T-054 + DP entropy bound + fixed schema + aggregate audit               | RESOLVED                |
| F-12    | Time-anchor / doc-00 §4.1 item 7      | Doc 00 v3 §4.1 item 7b formalizes; T-001 row cites 7b correctly         | RESOLVED                |
| F-13    | Test-2 two-phase signing              | Doc 00 v3 §8 Test-2 rewritten; T-004 row cites correctly                | RESOLVED                |
| F-14    | Hidden-envelope ethics-audit gate     | **NOT addressed**; Cluster G non-blocking per consolidated pack         | DEFERRED (Cluster G)    |
| F-15    | Recursive + A2A amplification DoS     | T-107 covers recursive self-invocation; A2A amplification NOT covered   | **PARTIAL — see R2M-2** |
| F-16    | Goal-drift                            | T-016 + turn-N goal-reconfirmation + ReasoningCommit                    | RESOLVED                |
| F-17    | Training-data extraction              | T-017 + response filter + provider-risk annotations                     | RESOLVED                |
| F-18    | 20+ primitive spec references         | **NOT addressed**; Cluster G non-blocking                               | DEFERRED (Cluster G)    |
| F-19    | R category under-represented          | New §3.5 subsection explicitly addresses STRIDE R via T-100–T-104       | RESOLVED                |
| F-20    | Phase 02 binding-audit scope          | **NOT addressed**; Cluster G non-blocking                               | DEFERRED (Cluster G)    |
| F-21    | Memory-disclosure / heap-dump         | T-071 added                                                             | RESOLVED                |
| F-22    | Post-quantum trigger                  | **NOT addressed**; Cluster G non-blocking                               | DEFERRED (Cluster G)    |
| F-23    | k-anonymity k=100 justification       | **NOT addressed**; Cluster G non-blocking                               | DEFERRED (Cluster G)    |
| F-24    | Envelope linter gmail.com             | **NOT addressed**; Cluster G non-blocking                               | DEFERRED (Cluster G)    |
| H-1     | Grant Moment dialog spoofing          | T-018 + visual secret + signed dialog + cross-channel confirm           | RESOLVED (see R2M-5)    |
| H-2     | Authorship Score gaming               | (same as F-07)                                                          | RESOLVED                |
| H-3     | Enterprise delegation-upward          | T-024 + enterprise mode + template-vs-authored visibility               | RESOLVED (see R2M-6)    |
| H-4     | Grant Moment replay                   | T-008 + nonce + context binding + replay window                         | RESOLVED                |
| H-5     | Heartbeat covert channel              | (same as F-11)                                                          | RESOLVED                |
| H-6     | Grant Moment habituation              | T-019 + novelty-aware friction + batch-to-envelope + time-delay         | RESOLVED                |
| H-7     | Multi-turn goal drift                 | (same as F-16)                                                          | RESOLVED                |
| H-8     | Sybil on Community tier               | (same as F-08)                                                          | RESOLVED                |
| H-9     | First-time-action gate load-bearing   | **NOT explicitly addressed as a threat entry**; implicit in T-010/T-011 | PARTIAL — see R2M-8     |
| H-10    | Algorithm-identifier schema vaporware | Doc 00 v3 §4.1 item 9 gate + §7 Phase 02 gate reference                 | RESOLVED                |
| H-11    | Panic-wipe as DoS for coerced user    | **NOT addressed**; not in approved Cluster A–F                          | DEFERRED (out-of-scope) |

**Summary:** Every user-approved (Cluster A–F) HIGH is resolved. Remaining HIGHs (F-14/18/20/22/23/24, H-11) are Cluster G / out-of-approved-scope and acceptably deferred per the consolidated pack.

---

## Section C — Internal consistency

### R2H-1 — Threat-count arithmetic wrong (HIGH)

**Claim in doc:** Line 5 v2 change summary: "17 new threats added… 23 → 40 threats." Line 735: "40 threats total." Line 790: "**Total: 40 threats, 40 mitigation rows, 1:1 parity.**"

**Actual catalog counts:**

- §3 enumerated threat IDs: T-001..T-007 (7), T-008 (1), T-010..T-017 (8), T-018..T-019 (2), T-020..T-024 (5), T-030 (1), T-040..T-042 (3), T-050a/b/T-051..T-054 (6), T-060/T-070/T-071/T-080 (4; T-061 reserved), T-090..T-094 (5), T-100..T-107 (8) = **50 threats** (49 active + 1 "reserved").
- §4 matrix rows (grep of `| T-` or `| **T-`): **50 rows**.

**Catalog and matrix are 1:1 at 50, not at 40.** New-threat count is also off: new IDs are T-008, T-012, T-013, T-014, T-015, T-016, T-017 (7) + T-018, T-019 (2) + T-022, T-023, T-024 (3) + T-054 (1) + T-071 (1) + T-091, T-092, T-093, T-094 (4) + T-100..T-107 (8) + T-050b (1 from split) = **27 new**, not 17. The v1 baseline was 23; 23 + 27 = 50 matches the catalog.

**Fix (trivial):** s/23 → 40 threats/23 → 50 threats/ and s/17 new threats/27 new threats/ in the change summary; s/40 threats, 40 mitigation rows/50 threats, 50 mitigation rows/ in §4.

**Why HIGH:** The "40 threats, 1:1 parity" claim is load-bearing as a completeness assertion. A reader verifying parity manually will observe 50 rows, believe either the catalog or the matrix has drifted, and open an issue. For a doc that explicitly positions itself as "mechanically parity-checked," a count mismatch of this scale undermines confidence. It's also trivially fixable in one edit. Leaving it through a Round 2 review is the exact drift the mechanical sweep exists to catch.

### R2H-2 — T-013 ReasoningCommit record is structurally insufficient against its stated attacker (HIGH)

**Setup:** T-013 (§3.2, lines 121–143) names the attacker model as "**Compromised model provider (T-030) or a user-input crafted to manipulate the LLM's internal reasoning.**" The primary mitigation is the `ReasoningCommit` record: `{intent_summary, considered_alternatives, chosen_tool, envelope_verification_result, composition_context}`.

**Gap:** When the attacker model is a compromised provider, the LLM is the adversary. Every field in `ReasoningCommit` that is self-reported by the LLM — `intent_summary`, `considered_alternatives`, `composition_context` — can be forged by the same attacker. Only `envelope_verification_result` is produced by structural machinery external to the LLM, and that check is already performed by the envelope layer independent of `ReasoningCommit`.

The residual-risk register (§6) says only: "Subtle compositional attacks below semantic-check thresholds … BET-2 honest framing + quarterly classifier review." This does not acknowledge that **the ReasoningCommit fields on which post-hoc review depends are themselves attacker-forgeable under T-013's own attacker model.**

The `shared with T-013` claim for T-016 goal-drift (line 205 "ReasoningCommit entries — post-hoc review catches drift") inherits the same limitation: post-hoc review of self-reported reasoning from a compromised model doesn't catch drift the model is hiding.

**Options for disposition:**

1. **Narrow T-013's attacker model** to "user-input crafted to manipulate reasoning" only, and redirect provider-compromise to T-030 (whose mitigation is multi-provider verification). This makes ReasoningCommit meaningful against its remaining attacker.
2. **Add an explicit residual-risk entry**: "Under a compromised-provider attacker (T-030 overlap with T-013), `ReasoningCommit` self-report fields are forgeable; only `envelope_verification_result` is authoritative. Post-hoc drift detection requires multi-provider cross-checking (T-030 mitigation) or out-of-band reasoning validation."
3. **Require T-013 mitigation to include multi-provider reasoning cross-check as MUST, not SHOULD.** Currently line 138 lists local-model/multi-provider as "(T-030 mitigations) reduce provider-side manipulation risk" — not a hard requirement for T-013 itself.

**Why HIGH:** The ReasoningCommit structure is new to v2 and is cited as primary mitigation for two threats (T-013, T-016) and referenced by a third (T-014, via "shared Turn-N goal-reconfirmation"). If the primary structure doesn't hold against its own stated attacker, three mitigations inherit the gap. Fixable with a paragraph in §6 OR a narrower attacker model in T-013 — not a design re-do.

### R2M-1 — Matrix row count claim drift (MEDIUM)

§8 line 852: "Total distinct spec files referenced from doc 09 v2: **22** (up from 16)." Grep of the doc finds **25 distinct `specs/*.md` references**:

```
specs/a2a-messaging.md, specs/authorship-score.md, specs/budget-tracker.md,
specs/connection-vault.md, specs/distribution.md, specs/envelope-library.md,
specs/envelope-model.md, specs/foundation-health-heartbeat.md,
specs/foundation-ops.md, specs/grant-moment.md, specs/ledger-merge.md,
specs/ledger-sync.md, specs/ledger.md, specs/model-adapter.md,
specs/network-security.md, specs/remote-time-anchor.md,
specs/runtime-abstraction.md, specs/shamir-recovery.md,
specs/shared-household.md, specs/skill-ingest.md,
specs/sub-agent-delegation.md, specs/trust-lineage.md, specs/trust-vault.md,
specs/ui-platform.md, specs/weekly-posture-review.md
```

The "16 → 22" count is off. 7 new files explicitly named in the change summary (sub-agent-delegation, ledger-merge, a2a-messaging, authorship-score, budget-tracker, remote-time-anchor, foundation-ops) — plus `specs/ledger-sync.md` appears in the T-100 row but isn't in the "new forward references" list of §8. Fix: update the count to 25 and add `specs/ledger-sync.md` to the explicit new-references list.

### R2M-2 — A2A amplification DoS not distinctly addressed (MEDIUM)

Round 1 F-15 bundled two threats: "Recursive self-invocation / sub-agent A2A amplification DoS." v2 addresses the first via T-107 (single-agent recursive spawn bounded by depth + budget). The second — **agent A's A2A messages to agent B cause B to A2A-message C, causing cascading A2A traffic across a Shared Household** — has no dedicated threat. T-106 covers A2A collusion (adversarial cooperation bypassing envelopes) but not amplification. This is a gap. Possible disposition: add a note to T-107 that A2A message traffic per session is bounded per envelope, OR add T-108 for A2A-amplification-DoS. Non-blocking for Phase 01 (sub-agents don't exist yet), but should be named before Phase 03 A2A launch.

### R2M-3 — Sub-agent posture inheritance not covered by T-105 subset-proof (MEDIUM)

The Cluster C consolidated pack item §4 (line 97) required "Sub-agent posture inheritance (MUST, Phase 02): sub-agent's posture is MIN(parent's posture, user's declared sub-agent posture ceiling). Cannot escalate." This does not appear in v2. T-105's subset-proof format covers the 5 envelope constraint dimensions (Financial, Operational, Temporal, Data Access, Communication) but posture is a scalar orthogonal to those dimensions (PSEUDO/TOOL/SUPERVISED/DELEGATING/AUTONOMOUS). A parent at DELEGATING could technically spawn a sub-agent claiming AUTONOMOUS under the current subset-proof — the proof would verify dimensional subsets without checking posture. Fix: `specs/sub-agent-delegation.md` MUST include posture-inheritance as a sixth constraint dimension OR as an explicit separate check.

### R2M-4 — Content-constraint subset direction inverted vs other dimensions (MEDIUM)

T-105 lines 516–521:

> - Operational: sub-tool-allowlist ⊆ parent-tool-allowlist.
> - …
> - Communication: sub-recipient-allowlist ⊆ parent-recipient-allowlist; **sub-content-constraints ⊇ parent-content-constraints (more restrictive = fewer content-types allowed)**.

Four of the five dimensions express "sub ⊆ parent" as the subset direction. The Communication dimension's `sub-content-constraints ⊇ parent-content-constraints` inverts this because it treats "constraints" as restrictions (deny-list semantics) while the others treat allowlists (permit-list semantics). Mathematically consistent but implementation-hazardous: a verifier written against the four allowlist dimensions will get the Communication direction wrong by default. Fix: rewrite Communication as `sub-allowed-content ⊆ parent-allowed-content` (same allowlist semantics as the other four) OR add an explicit note in `specs/sub-agent-delegation.md` that the Communication subset check reverses direction and why.

### R2M-5 — Grant Moment visual secret vulnerable to screen-recording (MEDIUM)

T-018 residual risk (line 251): "user who ignores secret-missing warning; user whose device is fully compromised (out of scope per §1.2)." The threat model under §1.2 out-of-scope line 37 excludes "Device-level attacks (kernel, hypervisor, firmware)" — but **screen-recording is NOT a kernel/hypervisor attack.** On iOS/Android/macOS, a number of legitimate apps request screen-capture permission and can obtain it. A malicious app with screen-capture permission could:

1. Observe a legitimate Grant Moment the first time the user unlocks Envoy
2. Extract the visual secret (icon + color + short phrase)
3. Later render a spoofed Grant Moment containing the captured secret

The "signed dialog rendering" mitigation (Phase 02) is the structural defense — but it's only MUST at Phase 02, leaving Phase 01 reliant on the visual secret alone. The screen-recording threat falls in a capability band (above basic app, below kernel compromise) that the current residual-risk framing papers over.

Fix: acknowledge screen-recording explicitly in T-018 residual risk OR upgrade "signed dialog rendering" to Phase 01 MUST (at the cost of requiring native-UI-only Grant Moments from the start).

### R2M-6 — Enterprise-mode creates an IT-trust attack surface not named in T-024 (MEDIUM)

T-024 detection (line 344): "enterprise mode explicit (MUST, Phase 03): if `Envoy.install_mode == "enterprise"` (detected via **MDM profile, install-parameter, or enterprise-origin envelope signature**), DIFFERENT posture-ratchet rules apply." The residual risk (line 354) acknowledges: "IT can configure enterprise-mode off via install-parameter."

Deeper gap not named: A malicious or coerced IT could **install Envoy with `enterprise-mode=false` AND push an enterprise-origin envelope** — the employees get the template-defined posture under personal rules (N=3, not N=5), reaching DELEGATING / AUTONOMOUS with template-authored constraints. This is the exact failure mode T-024 was meant to close; a single boolean flag with IT-controllable default reopens it.

Fix options:

1. Enterprise-origin envelope signature alone MUST flip `enterprise-mode=true`, regardless of install-parameter (signature cannot be bypassed by install-parameter).
2. Add explicit threat `T-024b: Enterprise-mode disable circumvention` — or explicit residual-risk entry naming "IT-controlled disable of enterprise-mode is a known bypass; mitigated only by enterprise-origin envelope signature override (MUST, Phase 03)."

### R2M-7 — T-101 CRDT merge spec-sketch is adequate but §9 acknowledges unresolved LWW-vs-causality (MEDIUM)

The CRDT merge spec-sketch (§3.5 T-101) names Lamport clocks, `merged_from` records, deterministic merge, and explicit conflict surfacing via `LedgerConflictEntry`. This is sufficient for a threat model (WHAT the protection does). §9 open question: "T-101 CRDT merge: LWW (last-write-wins) vs causality-preserving? Accept trade-off in design doc." LWW vs causality-preserving has material security implications — LWW lets the attacker who gets the latest write always win a conflict, which in the threat-model scenario is exactly what an attacker controlling one device in a fork would want. "Accept trade-off in design doc" is acceptable disposition IF `specs/ledger-merge.md` is authored before Phase 02 mobile ship. Fix: §7 Phase 02 gate line 834 should explicitly name "LWW-vs-causality decision landed in `specs/ledger-merge.md`" as a sub-bullet, not leave it to "external review" alone.

### R2M-8 — T-101 phase assignment ambiguity preserved in matrix (MEDIUM)

§3.5 T-101 line 421: "CRDT-style merge protocol (MUST, Phase 02 when mobile launches — **or Phase 01 if we support `pipx` multi-machine use**)." Matrix row line 782: Phase "**01, 02**". The matrix commits to both phases, but §3.5 text says "or". Actual Phase 01 decision:

- Does `pipx install envoy-agent` on two machines (user's laptop + desktop) constitute multi-device use under Phase 01?
- If yes → CRDT merge is Phase 01 MUST → substantial scope addition.
- If no → Phase 02 MUST.

This matters because CRDT merge is load-bearing for T-100 (rollback detection under multi-device) AND T-103 (cycle-detection race in merge). Without a clear phase commitment, implementors default to "ship Phase 01 without CRDT, add later" — which means T-100/T-103 defenses are incomplete under the `pipx`-multi-machine scenario the doc itself raises.

Fix: §3.5 T-101 should commit to one phase (and matching matrix column). Same text should appear in `specs/ledger-merge.md` when authored.

### R2M-9 — §3.10 "Legacy" footer references T-050 (pre-split identifier) (MEDIUM)

Line 729: "### 3.10 _Legacy: Prompt injection T-010/T-011 in §3.2; all other v1 threats (T-030, T-040 – T-042, T-050, T-051 – T-053, T-060, T-070, T-080, T-090) unchanged._"

T-050 no longer exists as a top-level threat — it was split into T-050a/T-050b. T-054 (new in v2) is not listed. Footer text is stale relative to the actual §3 content. Trivial fix.

---

## Section D — Low-severity findings

### R2L-1 — "17 new threats" claim (line 5) wrong (LOW)

Covered under R2H-1; line 5 change summary says "17 new threats" but actually 27 new IDs landed. Fix with R2H-1.

### R2L-2 — §1.4 attacker taxonomy refers to "v1 §1.4" (LOW)

Line 46: "Unchanged from v1. See v1 §1.4 for the full table." Normal draft progression but a new reader landing in v2 has to open v1 to see the taxonomy table. Consider inlining the taxonomy table in v2 at the next major revision.

### R2L-3 — Attacker model for T-018 Grant Moment spoofing doesn't distinguish screen-recording capability (LOW)

See R2M-5. The attacker in T-018 is generically "malicious app on the same device rendering a fake Grant Moment dialog." Refine to name the capability bands (screen-draw, screen-capture, accessibility-service) so mitigations can be mapped to each. Non-blocking.

---

## Section E — Doc-00-v3 cross-reference verification

All three Cluster F doc-00 references in doc 09 v2 resolve correctly:

| Ref                        | Claim                                                                                                                | Doc 00 v3 verification                                                                                                                                                                               |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| T-001 mitigation + §7 gate | "remote time anchor (opt-in per doc 00 §4.1 item 7b)"                                                                | Doc 00 line 229 explicitly names §4.1 item 7b — remote time anchor, TSA quorum, opt-in default, separately-signed Grant Moment. **MATCH**                                                            |
| T-004 mitigation           | "Two-phase signing (per doc 00 v3 §8 Test-2)"                                                                        | Doc 00 line 581 §8 Test-2 explicitly rewritten with Phase A / Phase B semantics + repudiable-side-effect incident framing. **MATCH**                                                                 |
| §7 Phase 02 gate           | "Algorithm-identifier schema landing — kailash-py#604 + kailash-rs#519 + mint#6 closed OR Envoy-local impl in place" | Doc 00 line 232 §4.1 item 9 gates Phase 01 exit on same three issues OR Envoy-local with sunset. **MATCH (but doc 09 §7 places gate at Phase 02, doc 00 places it at Phase 01 exit — inconsistent)** |

**R2M-10 (sub-finding, MEDIUM):** Algorithm-identifier gate phase mismatch. Doc 00 v3 §4.1 item 9 says "Phase 01 exit gates" (line 232). Doc 09 v2 §7 lists the algorithm-identifier landing under "**Phase 02 gates (new sub-items)**" (line 836). Doc 00 is authoritative on Phase gates. Fix: move the §7 bullet to Phase 01 gates in doc 09, OR update doc 00 to defer to Phase 02. The two docs must not disagree on the phase boundary.

Also: T-001 references `specs/remote-time-anchor.md` which is a new forward reference not in the §8 new-file list (R2M-1 sub-case).

---

## Section F — Regressions introduced by v2 (standalone fresh review)

No genuinely new CRITICAL or HIGH introduced. The caveats around R2H-2 (ReasoningCommit attacker model) and R2M-3/R2M-4 (sub-agent subset-proof completeness) are gaps in the new mitigations, not regressions against v1.

Everything else is existing Round-1 disposition.

---

## Section G — Spec-sketch adequacy for new threats (fresh eye)

| Threat | Spec sketch                                        | Adequate for threat-model level?                                                      |
| ------ | -------------------------------------------------- | ------------------------------------------------------------------------------------- |
| T-012  | content_trust_level enum + entry-sanitization      | YES — enum + grep enforcement is concrete                                             |
| T-013  | ReasoningCommit record type                        | **INSUFFICIENT against own attacker model** — see R2H-2                               |
| T-014  | per-turn prompt reset + structured framing         | YES                                                                                   |
| T-015  | system-prompt pinning + size budget                | YES                                                                                   |
| T-018  | visual secret + signed dialog                      | YES but screen-recording gap — see R2M-5                                              |
| T-019  | novelty-aware friction + batch-to-envelope         | YES                                                                                   |
| T-022  | publisher identity-proofing tier                   | YES — names POW / POS / vouching                                                      |
| T-023  | semantic de-dup + minimum-impact                   | YES                                                                                   |
| T-024  | enterprise-mode posture gate                       | YES but IT-disable gap — see R2M-6                                                    |
| T-050b | key-rotation + reproducible builds                 | YES                                                                                   |
| T-054  | DP on flag entropy                                 | YES but threshold empirical (§9 open question)                                        |
| T-093  | velocity limit + per-call tracking                 | YES                                                                                   |
| T-100  | sealed head-commitment + monotonic length          | YES                                                                                   |
| T-101  | CRDT merge sketch                                  | YES at threat-model level; LWW-vs-causality open (R2M-7) + phase ambiguity (R2M-8)    |
| T-102  | delegation chain head-check                        | YES                                                                                   |
| T-103  | DAG invariant + cycle detection at creation        | YES                                                                                   |
| T-104  | envelope-version binding + capability-existence    | YES                                                                                   |
| T-105  | subset-proof across 5 dimensions                   | YES but posture-inheritance missing (R2M-3), Communication direction inverted (R2M-4) |
| T-106  | A2A envelope-binding + dual-signed cross-principal | YES                                                                                   |
| T-107  | spawn depth + budget                               | YES but A2A amplification not covered (R2M-2)                                         |

---

## Section H — Cluster F doc-00 re-alignment (verification-only)

Doc 00 v3 (frozen 2026-04-21 per `round-v3-verify-00-thesis-and-scope.md`) contains all three Cluster F changes:

- §4.1 item 7 split into 7a (Heartbeat, reaffirmed) + 7b (time anchor, new) — verified at doc 00 lines 227–230.
- §8 Test-2 rewritten with Phase A / Phase B framing — verified at doc 00 line 581.
- §4.1 item 9 algorithm-identifier Phase 01 exit gate — verified at doc 00 line 232.

All three re-alignments are reachable from doc 09 v2; R2M-10 above flags the single remaining discrepancy (algorithm-identifier gate placed at Phase 02 in doc 09 vs Phase 01 in doc 00).

---

## Section I — Recommendation

**CONVERGED** at 0 CRITICAL + 2 HIGH.

**Actions before doc 02 entry:**

1. **Fix R2H-1 (trivial)** — update "40 threats" → "50 threats" + "17 new threats" → "27 new threats" in line 5 change summary and line 735/790 parity claims.
2. **Address R2H-2 (narrow OR acknowledge)** — pick one: narrow T-013 attacker model to exclude compromised-provider, OR add explicit residual-risk entry "ReasoningCommit self-report fields forgeable under T-030 attacker; multi-provider cross-check required." One-paragraph edit either way.

**Track as follow-ups (not blocking doc 02):**

- R2M-1 through R2M-10 named in this report.
- R2L-1 through R2L-3 as named.

**Does not require Round 3 redteam** — the 2 HIGHs are both editable-in-place without structural change, and the M findings are all within the user's "AT ANY COSTS" directive's expected polish-cost envelope. Apply R2H-1 + R2H-2 fixes inline in doc 09 v2.1, note R2M items as known follow-ups in `specs/_index.md` or equivalent tracker, and move to doc 02.
