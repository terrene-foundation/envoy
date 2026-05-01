# Round 1 Consolidated Findings Pack — Doc 09 Threat Model

**Date:** 2026-04-21
**Inputs:** 3 sweeps of `workspaces/phase-00-alignment/01-analysis/09-threat-model.md`:

- `round-1-09-threat-model-mechanical.md` — 10 findings (0 CRIT / 1 HIGH / 5 MED / 4 LOW)
- `round-1-09-threat-model-reviewer.md` — 27 findings (4 CRIT / 11 HIGH / 9 MED / 3 LOW)
- `round-1-09-threat-model-adversarial.md` — 31 findings (3 CRIT / 11 HIGH / 11 MED / 6 LOW)

**Total raw:** 68 findings. Deduplicated and clustered below.

## Severity overview (deduped)

| Cluster             | Title                                                     | CRIT  | HIGH   | MED    | LOW   | Disposition cost                                                                                               |
| ------------------- | --------------------------------------------------------- | ----- | ------ | ------ | ----- | -------------------------------------------------------------------------------------------------------------- |
| A                   | Feedback loop + chain-of-thought + context attacks        | 2     | 3      | 2      | 0     | **Structural — new T-012/T-013/T-014 threats + `Ledger content_trust_level` + `reasoning-commit` record type** |
| B                   | Ledger integrity + trust-lineage crypto                   | 2     | 4      | 2      | 0     | **Structural — new T-100–T-105 subsection + fork protocol spec**                                               |
| C                   | Sub-agent + A2A + multi-principal forgery                 | 1     | 2      | 1      | 0     | **Structural — new `specs/sub-agent-delegation.md` + T-105 derivation proof**                                  |
| D                   | Thesis-structural attacks (authorship, posture, Grant UX) | 1     | 4      | 1      | 0     | **Doc 00 v3 — authorship-score semantic de-dup + Grant Moment authenticity binding + rubber-stamp defense**    |
| E                   | Foundation-infra + Sybil + covert channel                 | 1     | 2      | 2      | 0     | **Doc-level — T-050/T-060 boundary clean + T-022 Sybil + T-054 covert channel**                                |
| F                   | Doc 00 contradictions (must re-open doc 00)               | 0     | 3      | 0      | 0     | **Doc 00 v3 — §4.1 item 7 time-anchor carveout + §8 Test-2 phrasing + algorithm-id Phase-01 gate**             |
| G                   | Extensions (DoS variants, ethics, spec TODOs)             | 0     | 2      | 7      | 9     | **Doc-level polish + spec-TODO list**                                                                          |
| **Total (deduped)** |                                                           | **7** | **20** | **15** | **9** | **51 unique findings**                                                                                         |

**Convergence verdict:** Doc 09 v1 is **BLOCKED** until at least Cluster A + B + C + D + F are addressed. Cluster E/G are non-blocking.

---

## Cluster A — Feedback loop + chain-of-thought attacks (2 CRIT)

**Root:** Envoy's thesis puts the Ledger on the primary surface (doc 00 §2.3 item 4). Grant Moment text, action descriptions, skill-authored summaries all flow back into future LLM context. An attacker who lands text into the Ledger has a read-write channel into the agent's reasoning. Compounds with indirect prompt injection (T-011) but is NOT mitigated by T-011's "untrusted context" flag — Ledger entries carry user signatures and aren't flagged as untrusted.

**Contributing findings:** F-02 CRIT (reviewer), C-2 CRIT (adversarial), F-05 HIGH (reviewer multi-turn injection), F-06 HIGH (reviewer context-window attack), F-16/M-03 MED (goal drift), F-17 MED (training-data extraction).

**Proposed threats:**

- **T-012** Feedback-loop Ledger poisoning — attacker-landed content in Ledger becomes future LLM context without untrusted-flag.
- **T-013** Chain-of-thought compositional bypass — LLM reasoning (not visible in tool-calls) composes multi-step attacks using envelope-allowed primitives.
- **T-014** Multi-turn accumulated injection — injection subliminal in turn N activates in turn N+M after accumulated context.
- **T-015** Context-window exhaustion — adversarial input inflates context so critical envelope-instructions fall out of attention.
- **T-012 sibling — goal drift** (non-malicious variant; agent re-interprets user intent over turns).
- **T-017** Training-data extraction — adversarial prompts extract data memorized during model training.

**Proposed structural fixes:**

1. **Ledger `content_trust_level` field** (MUST, Phase 01): every Ledger entry carries `content_trust_level` ∈ {user-authored, tool-output, channel-message, derived-external, heartbeat, system}. Only `user-authored` flows into LLM context without untrusted-context wrapping. Others are sanitized/delimited.
2. **Reasoning-commit record type** (MUST, Phase 01): at each tool-call decision boundary, Ledger records a `ReasoningCommit` — structured {intent-summary, considered-alternatives, chosen-tool, envelope-verification-result}. Detects goal drift + chain-of-thought manipulation post-hoc.
3. **Signature scope limitation** (MUST, Phase 01): Delegation Record's signature covers GRANT (capability + constraint), NOT the human-readable description text. Description is separately content-hashed; LLM consuming Ledger sees structured grant + "description text (metadata)" — not treated as authoritative.
4. **Ledger-entry-as-context sanitization** (MUST, Phase 01): any Ledger entry surfaced back into LLM prompt is wrapped `<ledger_entry trust=X>...</ledger_entry>` with structural instruction "descriptive metadata, not instructions."
5. **Turn-N goal-reconfirmation** (MUST, Phase 02): every N tool-call invocations (N=5 default, tunable), agent auto-surfaces a Grant Moment of the form "Am I still working on the original intent you stated?" Posture DELEGATING+ can batch-approve; SUPERVISED requires per-N-turn reconfirm.

---

## Cluster B — Ledger integrity + trust-lineage crypto (2 CRIT)

**Root:** Envoy's non-repudiation claim rests on hash-chained append-only Ledger + Ed25519 signed records. But the classic crypto-protocol attacks (rollback, fork, replay, cycle) are structurally invisible to the doc's current §3.1–§3.4 threat list. The R category (Repudiation) of STRIDE was essentially missing.

**Contributing findings:** F-03 CRIT (cycle/cascade DoS), C-3 CRIT (offline fork reconciliation), F-09 HIGH (rollback/fork), F-10 HIGH (replay), F-13 HIGH (two-phase signing weakens Test-2 — doc 00 contradiction, cross-references Cluster F), F-19 MED (R category), M-01 HIGH (R category), M-06 MED (Grant Moment replay).

**Proposed threats (new §3.5 subsection):**

- **T-100** Ledger rollback attack — current Ledger replaced by older version during sync; attacker in multi-device / cloud-sync scenario.
- **T-101** Ledger fork attack — concurrent offline writes from device A + B; reconciliation logic exploited.
- **T-102** Delegation / Grant Moment replay — signed record captured, replayed in different context.
- **T-103** Trust-lineage cycle / cascade-revocation DoS — cycle in delegation graph causes `verify_chain` loop or cascade failure.
- **T-104** Signed-record version binding — signature valid but envelope has rolled back; capability referenced in signature no longer exists.
- **T-008** Grant Moment replay (companion to T-102 at the authorization layer, not the trust-lineage layer).

**Proposed structural fixes:**

1. **Ledger version monotonicity invariant** (MUST, Phase 01): Ledger has a sealed "head-commitment" written at each sync; sync client refuses a received Ledger whose head-commitment is strictly less than known. Defeats rollback.
2. **CRDT-style offline merge protocol** (MUST, Phase 02): Lamport-clock-style per-device causal ordering; on reconciliation, Ledger entries from both devices are merged into a single chain with explicit `merged_from` records. Conflicts (same Grant Moment signed twice) detected and surfaced as Ledger conflict entries requiring user resolution. New `specs/ledger-merge.md`.
3. **Grant Moment nonce + context binding** (MUST, Phase 01): every Grant Moment signature covers `(action-intent-hash, envelope-version, timestamp, random-nonce, signer-Genesis-hash)`. Replay requires all five to match; envelope version change OR nonce reuse invalidates.
4. **Delegation cycle detection** (MUST, Phase 01): before accepting a new Delegation Record, `verify_chain` walks ancestors. Any cycle causes rejection. Cascade revocation paths are verified acyclic at record-creation time; cascade traversal is cycle-free by construction.
5. **Version-bound signatures** (MUST, Phase 01): signatures include envelope-version-hash. If envelope is re-versioned before a signature's validity window closes, signature is still valid for its original envelope-version — but `verify_capability_exists()` checks current envelope. Missing capability = refuse to act.
6. **Envelope-version pinning** (MUST, Phase 01): actions authorized under envelope vN cannot execute under envelope vM if M > N without explicit re-authorization.

---

## Cluster C — Sub-agent + A2A forgery (1 CRIT)

**Root:** Envoy's A2A binding is stubbed in Rust per ISS-28 (`kailash-rs#517`). An agent at posture DELEGATING may spawn sub-agents. The sub-agent needs an envelope that is a subset of the parent's, but there is no cryptographic proof of derivation — a compromised parent can forge scope. Compounds in Shared Household (Phase 03): one principal's agent colludes with another principal's agent.

**Contributing findings:** C-1 CRIT (adversarial), F-15 HIGH (A2A amplification DoS), adversarial #3 (A2A-Shared-Household collusion), adversarial #4 (sub-agent posture inheritance).

**Proposed threats:**

- **T-105** Sub-agent envelope-scope forgery — parent spawns sub-agent with forged envelope (not a subset of parent's).
- **T-106** A2A adversarial cooperation (Shared Household) — principal A's agent coordinates with principal B's agent to achieve a goal neither human approved.
- **T-107** Recursive self-invocation DoS — agent spawns unbounded sub-agents until resource exhaustion.

**Proposed structural fixes:**

1. **Sub-agent derivation proof** (MUST, Phase 02 when A2A binding lands): a `SubAgentDelegation` record signs `(parent_envelope_hash, sub_envelope_hash, subset_proof)`. The `subset_proof` is a compact zero-knowledge-ish or explicit-membership proof that the sub-envelope's 5-dimension constraints are strictly ≤ parent's. Verifier rejects non-subset derivations.
2. **A2A message envelope-binding** (MUST, Phase 03): A2A messages between principals require both principals' envelopes to explicitly allow the message type. Cross-principal action requires dual-signed Grant Moment.
3. **Sub-agent spawn budget** (MUST, Phase 01): agent at posture DELEGATING can spawn sub-agents only within Operational-dimension limit (N sub-agents concurrent, M total per envelope-version). AUTONOMOUS allows higher; PSEUDO/TOOL cannot spawn at all.
4. **Sub-agent posture inheritance** (MUST, Phase 02): sub-agent's posture is MIN(parent's posture, user's declared sub-agent posture ceiling). Cannot escalate.
5. **New `specs/sub-agent-delegation.md`** — derivation proof format, verification algorithm, revocation cascade to sub-agents.

---

## Cluster D — Thesis-structural attacks (1 CRIT)

**Root:** The thesis primitives (Authorship Score, Grant Moment, posture-ratchet) are themselves attackable. If an attacker can game them trivially, the thesis collapses. The adversarial + reviewer agents converged on four distinct attacks on the thesis's load-bearing primitives.

**Contributing findings:** F-04 CRIT (budget-exhaustion fraud), F-07 HIGH (Authorship Score inflation), H-2 HIGH (score gaming), H-3 HIGH (delegation-upward enterprise copy-paste), H-1 HIGH (Grant Moment dialog spoofing), H-6 HIGH (Grant Moment habituation / rubber-stamp).

**Proposed threats:**

- **T-018** Grant Moment dialog spoofing — malicious app renders fake Grant Moment UI.
- **T-019** Grant Moment habituation / rubber-stamp — user clicks-approve daily; ritual collapses to zero-friction.
- **T-093** Budget-exhaustion fraud — malicious skill induces expensive calls; aggregate-velocity defense missing (CRITICAL per F-04).
- **T-023** Authorship Score inflation — user or script walks the counter with meaningless tweaks to unlock DELEGATING posture.
- **T-024** Enterprise delegation-upward via template — IT authors one envelope; 500 employees "author" by copying; BET-12 falsification path with no structural defense.

**Proposed structural fixes:**

1. **Authorship Score semantic de-duplication** (MUST, Phase 01): a new "authored" constraint must be semantically distinct from existing constraints AND from imported-template constraints. LLM-classifier at authoring time checks novelty; near-duplicates don't increment score. Publishes classifier criteria so users can see why a constraint "doesn't count."
2. **Enterprise mode (explicit)** (MUST, Phase 03): if `Envoy.install_mode == "enterprise"` (detected via MDM profile / install-parameter), employees get a SEPARATE Authorship Score gate — template-based posture starts at SUPERVISED, never TOOL/autonomy. DELEGATING requires employee-authored constraints beyond the IT template, with stricter novelty threshold (N=5 vs N=3 personal).
3. **Grant Moment authenticity binding** (MUST, Phase 01): at setup, user chooses a Grant-Moment visual secret (icon + color + short phrase); every legitimate Grant Moment dialog renders with it. Spoofed dialog can't predict the secret. User trained to reject any Grant Moment missing it.
4. **Grant Moment novelty scoring** (MUST, Phase 01): Grant Moments for novel patterns (unseen recipient, new dollar range, new tool-call sequence) get additional friction — longer delay, required-read-text, or explicit double-confirm. Familiar repeat patterns can batch within an envelope session. Prevents rubber-stamp collapse.
5. **Budget-velocity defense** (MUST, Phase 01): Financial dimension in envelope has both per-call ceilings AND aggregate-velocity limits (e.g. "no more than $X/hour of agent-initiated spend"). Per-call enforcement is structural O(1); velocity enforcement is a sliding-window sum check.
6. **Rubber-stamp mitigations** (MUST, Phase 02 Weekly Posture Review): Weekly ritual surfaces "you approved N Grant Moments this week — here are the 3 most similar patterns, should any be pre-authorized in the envelope to reduce daily friction?" Converts rubber-stamp signal into envelope-authoring opportunity.

---

## Cluster E — Foundation-infra + Sybil + covert channel (1 CRIT)

**Contributing findings:** F-01 CRIT (T-050/T-060 boundary), F-08 HIGH (Sybil on Community tier), F-11 HIGH (Heartbeat covert channel), M-04/M-05 MED.

**Proposed structural fixes:**

1. **Split T-050 → T-050a/T-050b** — T-050a (supply-chain: compromised binary from mirror with valid signature) vs T-050b (signing-key compromise, which defeats T-060 load-time verification). Make the chained-dependency explicit in the matrix. Add residual: "signing-key compromise defeats N-mirror verification; only `kailash-py` escape + reproducible-build verification help."
2. **Add T-022** Envelope Library Sybil — reputation ranking requires anti-Sybil. Mitigation: publisher-identity-proofing (Foundation vouch OR proof-of-stake OR verified domain); publisher-fork tracking (envelopes that are near-duplicates of existing ones scored with lower weight); adoption cap per-publisher-week to prevent rapid Sybil inflation.
3. **Add T-054** Heartbeat covert channel — compromised Envoy encodes info in flag patterns / ID rotation / timing despite STAR k-anonymity. Mitigation: reproducible-builds catch client compromise; differential privacy on flag-set entropy; periodic audit of aggregate-payload entropy vs expected.

---

## Cluster F — Doc 00 contradictions (requires doc 00 v3)

**Root:** Three doc-09 mitigations contradict doc 00 v2 as frozen:

**F-12 — Remote time anchor (T-001) contradicts §4.1 item 7 (no phone home except Heartbeat).** The remote-time-anchor option is a second phone-home path. Doc 00 §4.1 item 7 names Heartbeat as the SOLE exception. Needs either (a) time anchor added to the exception list via explicit Grant Moment carveout (same cryptographic property framing as Heartbeat), OR (b) time anchor demoted to out-of-scope with Temporal-dimension documented as "best-effort against clock attacks."

**F-13 — Two-phase signing (T-004) admits pre-execution window; weakens §8 Test-2 ("every action emits a signed record BEFORE execution").** Phase A signs the intent before execution; Phase B signs the outcome after. Test-2's strict reading requires signed-before-execution to be a hard guarantee. Two-phase achieves that at intent-layer; the tool-call's actual side effect happens between Phase A and Phase B. Needs Test-2 phrasing update: "every action's INTENT is signed before execution; the outcome is signed after. An intent without a matching completion record is a repudiable-side-effect incident."

**H-10 — Algorithm-identifier schema vaporware.** Filed as mint#6, kailash-py#604, kailash-rs#519. Doc 00 lists as Phase 01 exit criterion (§4.1 item 9). Needs either confirmation that Phase 01 exit gates on closure of these three issues OR doc 00 softens item 9 to "best-effort algorithm agility with Ed25519+SHA-256 hard-coded initial baseline; migration path added in Phase 02."

**Proposed doc 00 v3 changes:**

1. **§4.1 item 7** — extend carveout to include "remote time anchor (opt-in Grant Moment, same cryptographic properties — k-anonymous via quorum of public time-stamp authorities, signed response)."
2. **§8 Test-2** rewrite: _"Every action's intent is signed before execution (Phase A). The outcome is signed after execution (Phase B). An intent without a matching Phase B completion within N seconds is a repudiable-side-effect Ledger incident and surfaces as a Grant Moment on next startup. No action executes without a prior Phase A signature."_
3. **§4.1 item 9** — add a gate reference: "Algorithm identifier schema is load-bearing for this claim; Phase 01 exit gates on mint#6 + kailash-py#604 + kailash-rs#519 closure OR Envoy-local implementation with a documented sunset for upstream merge."
4. **§3.2 capability 21** (Algorithm-identifier schema) add a status row referencing the three issues.

---

## Cluster G — Extensions + polish (non-structural)

- **F-14** hidden-envelope ethics-audit gate (HIGH): jurisdictional advisory + explicit documentation that hidden envelopes may increase legal-liability in jurisdictions that criminalize obstruction.
- **F-18** 20+ primitive references need spec-TODO owner list (MED): cross-reference to Cluster F2 forward.
- **F-20** Phase 02 binding-security-audit scope (MED): add auditor selection, budget, cadence, deliverable format to §7 Phase 02 gates.
- **F-21** memory-disclosure / heap-dump threat (MED): add T-071 as sibling to T-070.
- **F-22** post-quantum migration trigger (MED): add to §7 ongoing-gates: "when NIST publishes PQC Kyber/Dilithium finalist + 2 audited libraries land, promote PQ migration from un-phased to ADR-planning."
- **F-23** k=100 justification (MED): link to Foundation Health Heartbeat ADR (forthcoming) for the threshold derivation.
- **F-24** envelope linter weak for gmail.com (MED): strengthen linter with "public email provider" detection + explicit warning about attacker-controllable sub-addresses.
- Plus additional DoS (T-091 Foundation infra, T-092 Envelope Library spam flood), T-094 context-window exhaustion.
- Plus LOW fixes: numbered-list vs bullets consistency (F-25), T-007 indentation (F-26), doc 10 cross-ref accuracy (F-27).

---

## Summary — what the user is being asked to debate

**Structural decisions needed (cluster lead):**

1. **[A]** Add Ledger `content_trust_level` field + `ReasoningCommit` record type + signature-scope limitation + turn-N goal-reconfirmation. **6 new threats T-012–T-017.** Meaningful Phase 01 scope addition. **Agree?**
2. **[B]** Add §3.5 Ledger-integrity subsection with T-100–T-105 + Grant-Moment replay T-008. Adopt monotonicity invariant + CRDT-style merge protocol + nonce+context binding + cycle detection + version-bound signatures + envelope-version pinning. **Agree + prioritize which are Phase 01 vs deferred?**
3. **[C]** Add T-105/T-106/T-107 sub-agent threats + new `specs/sub-agent-delegation.md` with derivation-proof format. **Agree? Is sub-agent spawning a Phase 01 or Phase 03 capability?** (If Phase 03, threats are Phase 03 gated; if Phase 01, Phase 01 exit needs the derivation proof.)
4. **[D]** Add T-018/T-019/T-023/T-024 thesis-structural threats + Authorship Score semantic de-dup + Enterprise-mode separate posture gate + Grant Moment authenticity binding + novelty scoring + Budget-velocity defense + rubber-stamp mitigations. **This is substantial Phase 01 scope; agree?**
5. **[E]** Split T-050a/T-050b, add T-022 Sybil, add T-054 covert channel. **Agree?**
6. **[F]** **Doc 00 v3 — re-open frozen doc:** §4.1 item 7 extended carveout for time anchor, §8 Test-2 rewrite for two-phase semantics, §4.1 item 9 gate on algorithm-id issues. **Agree? This triggers a Round 2 redteam on doc 00 v3 before continuing.**

**Non-structural (apply without further debate unless you object):**

7. **[E additional]** all DoS expansions (T-091–T-094), T-071 memory-disclosure, T-022 Sybil tuning, linter strengthening.
8. **[F2]** spec-TODO owner list pointing to 16+ forthcoming spec files; F-22 post-quantum trigger; F-23 k-anonymity justification; F-20 Phase 02 audit scope.
9. **[G]** LOW doc-level polish (F-25/26/27, consistent numbering, cross-ref cleanup).

**Session math:** applying all of Cluster A–F adds ~17 new threats to doc 09 (23 → ~40 threats) AND triggers doc 00 v3. Scope is consistent with the user's "AT ANY COSTS" directive; does not fit in a single doc 09 rewrite + single doc 00 patch without significant new text.

**Recommended path:**

1. User confirms directions A–F (or adjusts).
2. Apply Cluster F (doc 00 v3) first — smaller patch, unblocks doc 09.
3. Run Round 2 redteam on doc 00 v3 (quick pass — just verify the three fixes land cleanly).
4. Apply Cluster A–E to doc 09 (major rewrite — v2).
5. Run Round 2 redteam on doc 09 v2.
6. Converge when 0 CRIT + ≤1 HIGH across two rounds.
7. Move to doc 02 (envelope model).

**Estimated session budget for this cluster:** 3–4 more sessions to converge doc 09. User "AT ANY COSTS" accepts.

---

**Await user direction on clusters A–F before applying fixes.**
