# Round v3 Verification Sweep — Doc 00 (Thesis and Scope v3)

**Date:** 2026-04-21
**Reviewer role:** Quality reviewer — narrow v3 verification pass
**Input doc:** `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` v3 (806 lines)
**v3 baseline:** Doc 00 v2 converged in `round-2-00-thesis-and-scope-reviewer.md` (0 CRIT / 1 HIGH — R2-09 since fixed); re-opened per Cluster F findings in `round-1-09-consolidated-pack.md` (F-12, F-13, H-10).
**Exit criterion:** 0 CRITICAL + 0 HIGH → doc 00 v3 **FROZEN**.
**Scope:** Narrow verification of three Cluster F fixes plus sanity on cross-references.

---

## Summary table

| ID    | Sev | One-liner                                                                                                                                   | Status                           |
| ----- | --- | ------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| V3-01 | —   | F-12 remote time anchor carveout landed cleanly in §4.1 item 7 (split 7a / 7b; distinct Grant Moments; doc 09 T-001 mitigation satisfiable) | RESOLVED                         |
| V3-02 | —   | F-13 §8 Test-2 rewritten as Phase A intent + Phase B outcome; repudiable-incident semantics match doc 09 T-004                              | RESOLVED                         |
| V3-03 | —   | H-10 §4.1 item 9 now gates Phase 01 exit on mint#6 + kailash-py#604 + kailash-rs#519 OR Envoy-local impl with sunset                        | RESOLVED                         |
| V3-04 | —   | v3 change summary present at line 4; v2 change summary preserved at line 7                                                                  | RESOLVED                         |
| V3-05 | LOW | §13 carry-forward item 4 ("Test-2 says 'sign before execution'. Streaming output makes this hard") slightly stale after Test-2 v3 rewrite   | NEW (non-blocking polish)        |
| V3-06 | LOW | §5.0 opening prose does not mention the 7b remote-time-anchor carveout; reader could infer Heartbeat is sole §4.1 item 7 exception          | NEW (non-blocking clarity)       |
| V3-07 | LOW | Doc-status line 3 says "awaiting quick verification pass" — will need to flip to FROZEN after this pass                                     | NEW (expected housekeeping edit) |

**Totals:**

- CRITICAL: 0
- HIGH: 0
- MEDIUM: 0
- LOW: 3 (all non-blocking polish)

**Exit status:** 0 CRITICAL + 0 HIGH → **doc 00 v3 FROZEN.** The three Cluster F contradictions are resolved. The three LOW findings are minor polish items that can be applied in passing or deferred; none block freeze. Recommend the author flip line 3 status marker from "awaiting quick verification pass" to "frozen v3 — cleared verification 2026-04-21" as the single housekeeping edit before declaring frozen.

---

## Detail per finding

### V3-01 — F-12 RESOLVED (remote time anchor carveout)

**Cluster F claim:** §4.1 item 7 (v2) said Heartbeat is the SOLE phone-home exception. Doc 09 T-001 proposes a remote time anchor. The two are structurally incompatible under v2 framing.

**v3 resolution (lines 227–230):**

- Item 7 rewritten: _"Envoy does not phone home — except for two opt-in, cryptographically-scoped carveouts, each consented via a signed Grant Moment."_
- **7a. Foundation Health Heartbeat** preserved with all previous cryptographic properties (STAR/Prio, DP, OHTTP, signed consent, first-run opt-out).
- **7b. Remote time anchor for Temporal envelope enforcement** added: quorum of ≥2-of-3 public TSAs (FreeTSA + DigiCert + Apple trust roots), signed timestamp as Ledger anchor record, version + quorum-request payload only (no user-identifying data), hourly cadence default, first-run opt-out, distinct Grant Moment from Heartbeat (explicitly "the two are not bundled").
- Closing line: _"Users who decline both have Envoy run fully offline from first-run onward."_ — preserves the thesis's offline-default promise.

**Cross-consistency with doc 09:** Line 147 of doc 09 T-001 names `FreeTSA + DigiCert + Apple trust roots`; doc 00 line 229 matches. The "quorum ≥ 2 of 3" constraint is named in doc 00; doc 09 T-001 leaves quorum arithmetic implicit — no contradiction, doc 00 is the canonical source.

**Carry-forward §13 item 1** (line 772) still says _"optional remote time anchor with §4.1 item 7 opt-in"_ — this reads sensibly under the 7b split because the cross-reference is to the whole item 7, not to any specific clause.

**Doc 09 Q-1** (line 796) asks whether the remote-time-anchor option violates "no phone home" default. The doc 00 v3 item 7 rewrite is the answer — it is the structural carveout that Q-1 was asking for.

**Verdict:** RESOLVED. The carveout is cleanly scoped; both halves are cryptographically distinct; each is separately cascade-revocable; offline-default is preserved for users who opt into neither.

---

### V3-02 — F-13 RESOLVED (§8 Test-2 two-phase signing)

**Cluster F claim:** §8 Test-2 (v2) said _"Every action emits a signed record BEFORE execution."_ Doc 09 T-004 proposes two-phase signing (Phase A intent, Phase B outcome) because LLM tool-calls are not atomic. The strict v2 reading of Test-2 cannot accommodate the Phase A → side-effect → Phase B window.

**v3 resolution (line 581):**

- Test-2 rewritten: _"Every action's INTENT is signed before execution (Phase A); its OUTCOME is signed after execution (Phase B)."_
- Structural envelope membership check at O(1) in Phase A; semantic envelope compliance at O(k) LLM classification in Phase A — both before execution.
- Bold preserved: _"No action executes without a prior Phase A signature."_ — retains the "signed before execution" promise for intent.
- Repudiable-incident semantics added: orphan intent (Phase A without matching Phase B within N seconds, default 30s sync / longer async) → Ledger records orphan → surfaces as Grant Moment on next session start → user explicitly acknowledges or revokes.
- Explicit cross-reference: _"This two-phase structure is doc 09 T-004's mitigation."_
- Streaming user-channel output handled in Test-2 itself: stream-end `Message` record signing, millisecond user-visibility gap acknowledged, narrowed scope ("not an envelope-consumed action").

**Cross-consistency with doc 09 T-004 (lines 199–221):**

- Doc 09 line 216: `ToolCallIntent` at Phase A; line 217: `ToolCallResult` at Phase B linked by `intent_id`. Doc 00 v3 does not name these record types but the two-phase sequence matches exactly.
- Doc 09 line 219: semantic envelope checks enforced on intent signing. Doc 00 v3 line 581: _"semantic envelope compliance is checked pre-action with O(k) LLM classification in Phase A"_ — exact match.
- Doc 09 line 220: orphaned intent auto-tombstoned on restart. Doc 00 v3 line 581: orphan surfaces as Grant Moment on next session start; user acknowledges or revokes. Semantic-equivalent — doc 09 says "auto-tombstone with 'Phase B missing' marker" (system side), doc 00 says "Grant Moment on next session start" (user side). Both can be true simultaneously; no contradiction.

**BET-2 consistency:** Test-2 references "budget per BET-2" for O(k) semantic-check cost. §5.2 BET-2 partitions structural vs semantic checks with per-class latency budgets — consistent.

**§9.4 anti-patterns:** Anti-pattern 3 ("default permissive") is not affected by Test-2 two-phase split. Anti-pattern 4 (storage sovereignty) is not affected. No regression.

**Carry-forward §13 item 4** (line 775) says _"Test-2 says 'sign before execution'. Streaming output makes this hard. Doc 09 owns atomic-chunk-vs-per-chunk signing decision."_ — see V3-05 below for the minor staleness.

**Verdict:** RESOLVED. The two-phase semantics read honestly; the repudiable-incident path gives the user agency over the orphan case; streaming-output is addressed in-text (last sentence).

---

### V3-03 — H-10 RESOLVED (§4.1 item 9 algorithm-identifier gate)

**Cluster F claim:** §4.1 item 9 (v2) claimed crypto-agility via algorithm identifiers, but the schema was vaporware — tracked only as mint#6 / kailash-py#604 / kailash-rs#519 with no doc-level gate.

**v3 resolution (line 232):**

- Item 9 now explicitly gates Phase 01 exit on **either** (a) closure of mint#6 + kailash-py#604 + kailash-rs#519, **OR** (b) Envoy-local algorithm-identifier implementation with documented upstream-merge sunset.
- Consequence stated: _"Phase 01 CANNOT ship hard-coded Ed25519+SHA-256 without algorithm tags — all legacy records under that shortcut would become un-migrateable and the claim collapses retroactively."_
- Status pointer: `workspaces/phase-00-alignment/issues/manifest.md` (line 147 of doc 00 confirms manifest location and GH issue span).

**Cross-consistency with §3.3 row 20** (line 170): row lists "Algorithm-identifier schema + versioned signed-artifact format" as **❌ Absent on BOTH sides** with kailash-py#604 + kailash-rs#519 + mint#6 — exact same three issues referenced in item 9. Consistent.

**§3.3 aggregate parity bullet** (line 180) correctly counts row 20 as one of the 5 "absent on BOTH sides" primitives. Consistent.

**§3.3 Envoy-contributed new code table** (line 196) has the algorithm-identifier row tagged Phase 01 with rationale "Realizes §4.1 item 9 crypto-agility claim." Consistent.

**§10 dependency graph** (line 647) has "Algorithm-identifier schema + versioned artifact format + legacy-verification resolver" under "Crypto audit" which gates Phase 01 exit (line 649). Consistent.

**Glossary "Algorithm identifier"** (line 744) describes the primitive as "Envoy-new (v2)" and names enabling purpose. Unchanged from v2 — still accurate.

**Doc 09 cross-reference** (line 704): _"Algorithm-identifier schema (doc 00 §4.1 item 9) enables migration when post-quantum standards mature."_ — reads consistent with v3 gated framing.

**Verdict:** RESOLVED. The gate is load-bearing, the consequence is named, the sunset condition is explicit, and all sibling references to the schema (§3.3 row, Envoy-new-code table, §10 dependency graph) are mutually consistent.

---

### V3-04 — Document status + change-summary hygiene RESOLVED

**Concern:** Does the v3 change summary adequately describe the three fixes, AND is the v2 context still preserved for a reader who did not see Round 1?

**v3 line 3:** `**Document status:** draft v3 — post doc-09-Round-1 Cluster F contradictions resolved (awaiting quick verification pass)` — status clearly marks v3.

**v3 line 4:** One-paragraph change summary naming all three fixes (item 7 split, item 9 gate, Test-2 rewrite) with brief reason for each.

**v3 line 7:** Full v2 change summary **preserved verbatim** from the v2 draft — a reader arriving cold at v3 has full context on both v3 deltas AND v2 substrate. Good document hygiene.

**Verdict:** RESOLVED. V2 context is preserved; V3 changes are named with enough specificity that the reader can orient without reading Round 1 or Round 2 artifacts. See V3-07 for the expected one-line status flip on freeze.

---

### V3-05 — LOW: §13 carry-forward item 4 slightly stale post-Test-2 rewrite

**Location:** Line 775 — _"4. **Streaming LLM pre-action signing.** Test-2 says 'sign before execution.' Streaming output makes this hard. Doc 09 owns atomic-chunk-vs-per-chunk signing decision."_

**Issue:** After the v3 Test-2 rewrite, two parts of this carry-forward are slightly stale:

1. "Test-2 says 'sign before execution'" — accurate for Phase A intent (which IS signed before execution) but the v3 Test-2 is explicitly two-phase. The sentence reads as if the v3 complication is unknown to §13.
2. "Streaming output makes this hard. Doc 09 owns atomic-chunk-vs-per-chunk signing decision." — v3 Test-2's final sentence already resolves the user-channel streaming case in-text ("message signed as a single `Message` record at stream-end, not per-chunk"). So the doc 09 carry-forward is now narrower than it reads — only the tool-call streaming component remains with doc 09.

**Recommended fix (non-blocking):** rewrite as _"4. **Streaming LLM Phase A record granularity.** Test-2 commits to Phase A intent signing before tool-call execution; for tool-calls whose arguments are built up mid-stream, doc 09 T-004 owns the 'when does the stream count as complete enough to sign' decision (complete tool-call structure, arg-level commits, checkpoint frequency)."_

**Severity justification:** LOW because the text is not wrong, only slightly dated; a reader reaching §13 from §8 will already have read the more-precise Test-2 language and infer the narrower scope. No cross-reference breakage.

**Verdict:** NEW (non-blocking polish).

---

### V3-06 — LOW: §5.0 opening prose does not mention the 7b remote-time-anchor carveout

**Location:** Lines 280–282 — §5.0 opening paragraph.

**Issue:** §5.0 says _"§4.1 item 7 forbids phone-home telemetry by default."_ This is still accurate under v3, but a reader who arrives at §5.0 before §4.1 might infer the Heartbeat is the SOLE carveout (which was true in v2 but no longer in v3). The section then describes Heartbeat in detail without mentioning 7b.

This does not actually contradict anything — §5.0 is specifically about bet-measurement substrates, and the remote time anchor (7b) is not a bet-measurement substrate. So §5.0 legitimately does not need to discuss 7b. But a conservative reader might question whether §5.0 is aware of 7b's existence.

**Recommended fix (non-blocking):** Add a one-sentence aside in §5.0 opening: _"(A second item-7 carveout — the remote time anchor for Temporal envelope enforcement — is not a measurement substrate and is not used by any bet in §5; see §4.1 item 7b for its scope.)"_

**Severity justification:** LOW because §5.0's scope is measurement substrates, and 7b is not one. No bet-falsification reasoning breaks. Pure clarity polish.

**Verdict:** NEW (non-blocking clarity).

---

### V3-07 — LOW: Status-line housekeeping before freeze

**Location:** Line 3 — `**Document status:** draft v3 — post doc-09-Round-1 Cluster F contradictions resolved (awaiting quick verification pass)`

**Issue:** The status marker currently says "awaiting quick verification pass" — which was true when the verifier started reading. After this verification pass confirms 0 CRITICAL + 0 HIGH, the marker should flip to reflect frozen status.

**Recommended fix (housekeeping):** Replace line 3 with: _"**Document status:** frozen v3 — cleared verification 2026-04-21 (Round v3 verify findings: 0 CRIT + 0 HIGH)."_

**Severity justification:** LOW — this is an expected housekeeping edit the author will make upon confirming freeze. Not a finding against doc content.

**Verdict:** NEW (expected housekeeping).

---

## Convergence verdict

**0 CRITICAL + 0 HIGH** → doc 00 v3 is **FROZEN** pending the one-line status-marker flip.

The three Cluster F contradictions are cleanly resolved:

- **F-12** (remote time anchor) — §4.1 item 7 extended to 7a + 7b with distinct cryptographic properties and distinct Grant Moments.
- **F-13** (two-phase signing) — §8 Test-2 rewritten with Phase A / Phase B / repudiable-incident semantics that match doc 09 T-004 exactly.
- **H-10** (algorithm-identifier vaporware) — §4.1 item 9 gates Phase 01 exit on the three GH issues OR Envoy-local implementation with sunset.

The three LOW findings (V3-05, V3-06, V3-07) are non-blocking polish:

- V3-05: §13 item 4 prose slightly dated, can be tightened but not wrong.
- V3-06: §5.0 could mention 7b for reader clarity; not required.
- V3-07: status-line flip on freeze (author housekeeping).

No new CRITICAL or HIGH issues introduced by v3. No regressions against the Round 2 convergence.

**Recommendation:** Author flips line 3 to "frozen v3"; doc 00 is cleared; proceed to Cluster A–E of doc 09 rewrite per Round 1 consolidated pack recommended path step 4.

---

**Relevant file paths:**

- `/Users/esperie/repos/dev/envoy/workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` (v3, verified)
- `/Users/esperie/repos/dev/envoy/workspaces/phase-00-alignment/01-analysis/09-threat-model.md` (v1, cross-referenced for T-001 / T-004 consistency)
- `/Users/esperie/repos/dev/envoy/workspaces/phase-00-alignment/04-validate/round-1-09-consolidated-pack.md` (Cluster F source)
- `/Users/esperie/repos/dev/envoy/workspaces/phase-00-alignment/04-validate/round-2-00-thesis-and-scope-reviewer.md` (v2 convergence baseline)
