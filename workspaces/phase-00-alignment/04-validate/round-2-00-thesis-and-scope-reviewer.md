# Round 2 Reviewer Sweep — Doc 00 (Thesis and Scope v2)

**Date:** 2026-04-21
**Reviewer role:** Quality reviewer — Round 2 convergence verification
**Input doc:** `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` v2 (796 lines)
**Round 1 baseline:** `workspaces/phase-00-alignment/04-validate/round-1-00-consolidated-pack.md` (6 CRIT / 26 HIGH / 21 MED / 8 LOW, 61 deduped)
**Exit criterion:** 0 CRIT + ≤1 HIGH → doc marked CONVERGED

---

## Summary table

| ID    | Severity | One-line                                                                                              | Status           |
| ----- | -------- | ----------------------------------------------------------------------------------------------------- | ---------------- |
| R2-01 | —        | R1-F-01 (tautological canonical thesis) closed by §2.4 rewrite                                        | RESOLVED         |
| R2-02 | —        | R1-F-02 (WAU unmeasurable) closed by §5.0 Foundation Health Heartbeat + §7.1 two-signal floor         | RESOLVED         |
| R2-03 | —        | R1-F-03 (BET-9 hand-waves binding) closed by BET-9a/9b split + §3.3 concrete GH issues                | RESOLVED         |
| R2-04 | —        | R1-F-04 (phantom primitives) closed by three-column status table in §3.3                              | RESOLVED         |
| R2-05 | —        | R1-F-05 (Phase 01 safety on kailash-py) closed by §3.1 + cited audit docs                             | RESOLVED         |
| R2-06 | —        | R1-Adv-F-01 (BET-9 pre-falsified) closed by BET-9b explicit partial-disconfirmation text              | RESOLVED         |
| R2-07 | —        | R1-Adv-F-02 (Phase 01 CLI+Web violates anti-pattern 2) closed by 6-channel Phase 01                   | RESOLVED         |
| R2-08 | —        | R1-Adv-F-03 (Foundation financial viability) closed by BET-11 WITHDRAWN rationale                     | RESOLVED         |
| R2-09 | HIGH     | §3.3 summary numbers inconsistent with §3.3 table rows (26 vs 23; "14 green" unverifiable)            | NEW (REGRESSION) |
| R2-10 | MEDIUM   | §3.2 capability count self-contradiction (**21 total** vs **exactly these 22**) in same sentence      | NEW (REGRESSION) |
| R2-11 | MEDIUM   | §3.3 `75/30` withdrawal prose contradicts audit-concluded status published 6 lines above              | NEW (REGRESSION) |
| R2-12 | MEDIUM   | Channel-count rhetoric drift — "6 channels" row enumerates 8 entities in parenthetical                | NEW (REGRESSION) |
| R2-13 | MEDIUM   | Aggregate-parity summary refers to primitives ("Chain verify", "Nexus extractor") not in §3.3 table   | NEW (REGRESSION) |
| R2-14 | LOW      | Phase 01 resource realism — "8–12 sessions" is load-bearing but grounded only in user "AT ANY COSTS"  | NEW              |
| R2-15 | LOW      | Authorship Score N=3 threshold defensibility flagged as open question in §13; no evidence basis given | ACCEPTED-AS-OPEN |
| R2-16 | LOW      | §7 kill criterion 4 "2 independent Foundation-unaffiliated stewards" unoperationalized                | ACCEPTED-AS-OPEN |
| R2-17 | LOW      | §5.0 "~20 boolean flags" payload specification is approximate, not enumerated                         | MINOR            |

**Totals:**

- CRITICAL: 0 (down from 6)
- HIGH: 1 (down from 26) — R2-09
- MEDIUM: 4 (down from 21) — R2-10, R2-11, R2-12, R2-13
- LOW: 4

**Exit status:** 0 CRITICAL + 1 HIGH → **CONVERGED, pending R2-09 fix in final pass.** The one HIGH is a numerical consistency finding that does not require structural rework; a 10-line edit to either recount or restate the §3.3 summary bullets resolves it. Recommend user authorize the fix before freezing doc 00 v2.

---

## Detail per finding

### R2-01 — R1-F-01 RESOLVED (tautological canonical thesis)

**Round 1 claim:** §2.4's canonical thesis (`"the human holds a signed, revocable authority that every agent action traces to"`) is tautological — true by construction for any envelope-signing product, not a claim about the world that could be wrong.

**v2 resolution (§2.4, lines 57–63):**

- New canonical thesis is a falsifiable market claim: _"The durable, defensible role of the human in autonomous AI is the authorship of envelopes. Products that ritualize this authorship — and structurally gate agent autonomy on it — will earn primary-surface loyalty that tool-frame AI products cannot."_
- Explicit falsifiability stated: "if users prefer frictionless autonomy (Devin-class), or if template-import + one-click posture-max-out is preferred over authored-posture-ratchet, the thesis breaks."
- BET-1 + BET-12 named as the mechanical falsifications.
- Earlier architectural sentence demoted to "positioning statement in §8" per R1 proposal (`D-1`).

**Verdict:** RESOLVED. The rewrite is load-bearing and falsifiable.

---

### R2-02 — R1-F-02 RESOLVED (WAU unmeasurable under §4.1)

**Round 1 claim:** §4.1 items 7+8+11 forbid phone-home telemetry, registration, hosted identity. §5 + §7 rely on WAU / completion / retention / survey — metrics that require exactly those mechanisms. Doc made its own kill criteria non-firing.

**v2 resolution:**

- §5.0 (lines 272–299) introduces Foundation Health Heartbeat: STAR/Prio + k-anonymity (k ≥ 100) + DP + OHTTP relay + signed Grant-Moment consent. First-run default: opt-out (line 279).
- §4.1 item 7 (line 220) rewritten to explicitly carve out Heartbeat as the "sole exception" with full property naming.
- §7.1 kill criterion rewritten (line 553) as two-signal floor: `[Heartbeat] <1,000 STAR-aggregated WAU AND [Library] <500 FV fetches/week`. Both signals are §4.1-compliant.
- Every §5 bet's falsifying evidence tagged with `[Heartbeat]` / `[Public]` / `[Library]` substrate.
- ADR placeholder explicitly acknowledged ("to be detailed in its own ADR", line 274).

**Verdict:** RESOLVED. The Heartbeat design is self-consistent on cryptographic properties (STAR ≈ Prio-style secret-sharing, OHTTP ≈ RFC 9458, DP over aggregated counters). Payload scope (line 280) is reasonable; approximation noted in R2-17.

---

### R2-03 — R1-F-03 RESOLVED (BET-9 hand-waves binding reality)

**Round 1 claim:** BET-9 treated binding reality as "Phase 01 implementation discovers..." when evidence was already in kailash-rs survey pre-flight.

**v2 resolution:**

- BET-9 split into **BET-9a (upstream crates sufficient)** lines 455–468 and **BET-9b (Python binding surface usable)** lines 470–487.
- BET-9b explicitly flags "Already partially disconfirmed" (line 474) and enumerates the pre-existing evidence (BaseAgent, OrchestrationRuntime, A2A, execute_raw, MCP transports, .pyi accuracy).
- §3.3 three-column table names each binding gap with a filed GH issue number (kailash-rs #503–#521, kailash-py #594–#606, mint #2–#8).
- Mitigation-path Minor/Major/Kill laid out for each.

**Verdict:** RESOLVED. BET-9b is now falsifiable with named test conditions and a concrete repair surface.

---

### R2-04 — R1-F-04 RESOLVED (phantom primitives)

**Round 1 claim:** §3.3 claimed ~10 specific primitives ship on the binding without evidence.

**v2 resolution:**

- §3.3 rewritten as three-column parity status table (lines 147–171), 23 primitive rows with statuses ✅ / ⚠️ / ❌ / 🔧 / 🔀 per runtime.
- Status codes defined (lines 138–143).
- Deep audits cited: `01-kailash-rs-deep-audit.md`, `02-kailash-py-survey.md`, `03-primitive-reconciliation.md` (line 145). All three files exist in `01-analysis/`.
- 39 GH issues filed across three repos, cross-referenced in manifest at `workspaces/phase-00-alignment/issues/manifest.md` (verified exists).
- Line 165 names DataFlow `execute_raw()` SQLi surface as **"Envoy consumption of Rust binding BLOCKED until closed"** — operationally load-bearing.

**Verdict:** RESOLVED on the structural claim. However, the aggregate-parity summary bullets (lines 173–180) have numerical inconsistencies with the table itself — see R2-09 / R2-11 / R2-13.

---

### R2-05 — R1-F-05 RESOLVED (Phase 01 safety unaudited on kailash-py)

**Round 1 claim:** Phase 01 shipped on kailash-py but safety surface unaudited.

**v2 resolution:**

- §3.1 Phase 01 row (line 93) names runtime as "pure-Python runtime."
- Phase 00 row (line 92) explicit about "deep audits + GH issue closure tracking; kailash-py + kailash-rs + mint sync."
- `02-kailash-py-survey.md` exists and is cited.
- §3.3 line 180 states: "Phase 01 composes on kailash-py confidently."
- The execute_raw SQLi issue (kailash-rs#520) blocks Rust binding consumption but does not block kailash-py path.

**Verdict:** RESOLVED. Phase 01 runtime choice is now explicit and audited.

---

### R2-06 — R1-Adv-F-01 RESOLVED (BET-9 already falsified)

**Round 1 claim:** Survey evidence already proved BET-9 partially wrong before Phase 01 started.

**v2 resolution:** BET-9b (line 474) opens with: _"Status at draft time: Already partially disconfirmed."_ Followed by enumerated evidence. This is the correct disposition — name the pre-existing disconfirmation rather than pretend the bet is undetermined.

**Verdict:** RESOLVED.

---

### R2-07 — R1-Adv-F-02 RESOLVED (Phase 01 CLI+Web-only violates §9.4 anti-pattern 2)

**Round 1 claim:** Phase 01 = CLI + Web is the exact anti-pattern the doc forbids elsewhere.

**v2 resolution:**

- §3.1 Phase 01 row (line 93) now ships **6 messaging channels** (iMessage via BlueBubbles, Telegram, Slack, Discord, WhatsApp, Signal) plus CLI + Web = 8 surfaces.
- §9.4 anti-pattern 2 (line 602) reconciled: _"Phase 01 ships 6 channels; admin operations via CLI/Web are onboarding + management affordances only. Daily ritual UX is channel-native from day 1."_
- §9.3 (line 595) names "channel-native operation on 6 channels + CLI + Web."
- §3.1 phase-level clarifications (line 101) acknowledge the session-budget increase ("8–12 autonomous execution sessions") with the user's "AT ANY COSTS" instruction as justification.

**Verdict:** RESOLVED. The anti-pattern self-contradiction is eliminated by the Phase 01 scope expansion. Session-budget realism is noted separately as R2-14 (LOW).

---

### R2-08 — R1-Adv-F-03 RESOLVED (Foundation financial viability)

**Round 1 claim:** Foundation financial viability was missing, causing BET-4 to assert credibility without a runway model.

**v2 resolution:** BET-11 withdrawn (§5.11, lines 505–509) with explicit rationale: _"Financial viability of Terrene Foundation is a Foundation-level strategic concern, tracked at Foundation governance rather than in Envoy's product thesis. Envoy composes on Foundation primitives; Foundation viability is a prerequisite Envoy depends on but does not own."_ BET-4 retained but narrowed to product-level credibility (line 364: "product level, not financial").

**Verdict:** RESOLVED. The scope boundary is defensible: product-thesis doc should not contract the Foundation's financial solvency. The choice to withdraw rather than fabricate a runway model is the honest disposition.

---

### R2-09 — HIGH (NEW, REGRESSION) — §3.3 summary-bullet numerics inconsistent with table rows

**Location:** §3.3 lines 173–180 (aggregate parity summary + composition claim) vs lines 147–171 (primitive table rows).

**Evidence:**

1. **Line 173:** Summary announces "Aggregate parity (**26 primitives**)." Table at lines 149–171 contains **23 primitive rows** (verified by row-counting the markdown table).
2. **Line 175:** Summary claims "✅ Green on BOTH sides: **3** (Trust Lineage, **Chain verify**, **Nexus extractor** — confirmed parity)." Neither "Chain verify" nor "Nexus extractor" is a row in the table. Closest match: "Trust Lineage" (row 3, green both sides) and "Nexus multi-channel + HMAC + Kaizen A2A" (row 10, green Python, ⚠️ Rust). Neither "Chain verify" nor "Nexus extractor" appears as a distinct primitive.
3. **Line 180:** Composition claim: "Of 26 primitives audited, **14 are green on kailash-py (54%)**." Actual count of ✅ rows on the kailash-py column: at most 12 unambiguously green (rows 1, 2, 3, 4, 5, 7, 9, 10, 11, 14, 17, 18). Row 13 (Plan DAG) is partially green (Plan DAG ✅ but PlanSuspension ❌); row 6 is ⚠️ partial. So the count is between 12 and 13, not 14. 14/26 = 54% computes arithmetically but the underlying 14 and 26 do not both correspond to the actual table.

**Why HIGH:** §3.3 is the load-bearing evidence basis for BET-9a/9b and for Phase 01 viability claim ("Phase 01 composes on kailash-py confidently"). The aggregate numbers are how the downstream docs (and a future third-party reader) will internalize the primitive-readiness story. A discrepancy between the table (ground truth per audit) and the summary (aggregate claim) weakens the entire §3.3 argument because a reader who recounts cannot reconcile the numbers. Either the summary is correct and the table is missing 3 rows, or the table is correct and the summary is over-counting — either case is a factual error in the load-bearing section that needs reconciliation before convergence.

**Suggested fix (one of):**

- **Option A (recount summary to match table):** Update lines 173–180 to say "23 primitives audited", recount the Green/Yellow/Red buckets against the actual table, rewrite the composition claim with the corrected counts.
- **Option B (add missing primitives to table):** If the intent was 26 primitives, add the 3 missing rows ("Chain verify" and "Nexus extractor" called out in line 175 — plus one more) with their status codes.
- **Option C (collapse summary buckets to match table):** Remove the "14 green / 54%" specific number and replace with ranges or a qualitative claim ("majority of audited primitives are green on kailash-py") until the audit docs can be cross-checked.

**Recommendation:** Option A. The three-column table is the ground truth; the summary is derivable and should match mechanically.

---

### R2-10 — MEDIUM (NEW, REGRESSION) — Capability count self-contradiction in same sentence

**Location:** §3.2 line 134.

**Evidence:** _"**21 total capabilities** (up from 17 in v1; capabilities 18–22 are structural primitives the thesis requires that were not in the v1 list). Every downstream doc's schemas, state machines, and tests trace back to exactly these **22 capabilities**."_

The sentence asserts "21" in bold and "22" in bold-equivalent emphasis. The table contains rows 1 through 22, so 22 is the actual count. "21" is the typo.

**Why MEDIUM:** Immediate self-contradiction in the same sentence erodes credibility of the whole §3.2 claim. Downstream docs will cite this sentence; whichever number is picked propagates the error.

**Suggested fix:** Replace "21 total capabilities" with "22 total capabilities" — verified by row count (rows 1–22 inclusive).

---

### R2-11 — MEDIUM (NEW, REGRESSION) — 70/30 withdrawal contradicts audit-concluded publication

**Location:** §3.3 line 208 vs line 145.

**Evidence:**

- Line 145: _"**Deep audits concluded 2026-04-21.** Results synthesized at `03-primitive-reconciliation.md`. 39 GitHub issues filed..."_ — positions the audit as completed, with concrete deliverables.
- Line 208: _"**The 70/30 composition ratio** from v1 is withdrawn **until both deep audits complete** and `03-primitive-reconciliation.md` publishes the three-column parity grid. Claim to be replaced with a specific count: \_N primitives green / M yellow / K red across both runtimes_. **Until then**: Envoy Phase 01 is the _upper bound_..."\_

Line 208's "until both deep audits complete" and "until then" prose treats the audits as still pending, but line 145 says they concluded. And line 180 already publishes a specific count ("14 green / 54%") — which is exactly what line 208 said would replace the 70/30 claim. Yet line 208 still describes the 70/30 as "withdrawn."

**Why MEDIUM:** The prose drift suggests §3.3 was written in two passes — the table + summary were added after line 208's cautionary note was written, and the note was not updated. A reader reaches line 208 expecting the next step is replacement-with-specific-count, then realizes that replacement already happened 30 lines above. Confusing, not load-bearing for the thesis, but erodes the section's internal coherence.

**Suggested fix:** Rewrite line 208 to reflect post-audit state, e.g.: _"The v1 70/30 composition ratio is replaced (above) with the three-column parity grid. Phase 01 composability claim is reframed as 'N primitives green on kailash-py' per the summary bullets. Phase 01 is the upper bound of composable-from-upstream work; GH issue closure determines how much of that is preserved."_

---

### R2-12 — MEDIUM (NEW, REGRESSION) — Channel-count parenthetical enumerates 8 under "6 in Phase 01"

**Location:** §3.3 Envoy-contributed new-code table, line 193.

**Evidence:** _"**23 channel adapters** | 6 in Phase 01 (CLI + Web + iMessage-via-BlueBubbles + Telegram + Slack + Discord + WhatsApp + Signal); 17 more in Phase 04"_

The parenthetical lists 8 items (CLI, Web, iMessage, Telegram, Slack, Discord, WhatsApp, Signal) but the sentence says "6." Elsewhere the doc resolves this by distinguishing **6 messaging channels** vs **8 total surfaces** (line 595, line 671). Line 193 collapses the distinction.

**Why MEDIUM:** The 8-total vs 6-messaging distinction is load-bearing for §9.4 anti-pattern 2 reconciliation. A reader who counts the parenthetical and gets 8 then sees "6" will conclude one of: (a) the doc can't count, (b) CLI + Web aren't channels, or (c) there's a subtle distinction that isn't explained here. The inconsistency is a clarity drift, not a factual error — the underlying facts match elsewhere in the doc.

**Suggested fix:** Rewrite as: _"6 messaging channels in Phase 01 (iMessage-via-BlueBubbles + Telegram + Slack + Discord + WhatsApp + Signal) + CLI + Web = 8 total surfaces; 17 more messaging channels in Phase 04 → 23+ total."_

---

### R2-13 — MEDIUM (NEW, REGRESSION) — Summary bullets name primitives not present in §3.3 table

**Location:** §3.3 line 175.

**Evidence:** _"- ✅ Green on BOTH sides: 3 (Trust Lineage, **Chain verify**, **Nexus extractor** — confirmed parity)"_

Neither "Chain verify" nor "Nexus extractor" is a row label in the §3.3 table. Candidates:

- "Chain verify" — possibly conflated with "Trust Lineage" row 3 (covers chain verify) or with cascade-revocation row 4.
- "Nexus extractor" — no plausible match; the Nexus row is "Nexus multi-channel + HMAC + Kaizen A2A" which is only green on kailash-py, not both sides.

**Why MEDIUM:** This is the same root cause as R2-09 (summary doesn't match table) but in a different spot. Combined, they suggest the summary was written from a different primitive list than the table. A reader tracing "Nexus extractor" through the doc will not find it anywhere else — dead reference.

**Suggested fix:** Replace the parenthetical primitive names with actual row labels from the table. For the "green on both sides" bucket, the table shows row 3 (Trust Lineage) and row 4 (Cascade revocation) as ✅ both sides — that's 2, not 3. Recount and name accurately. (Resolving R2-09 mechanically resolves R2-13 in the same edit.)

---

### R2-14 — LOW (NEW) — Phase 01 "8–12 sessions" resource realism unspecified

**Location:** §3.1 phase-level clarifications, line 101.

**Evidence:** _"**Phase 01 ≠ 3–5 sessions anymore.** The scope expansion to 6 channels, Authorship Score primitive, Foundation Health Heartbeat, Connection Vault, algorithm-identifier schema, and independent ledger verifier raises the Phase 01 estimate to **8–12 autonomous execution sessions**. User accepted 'AT ANY COSTS' in exchange for shipping a thesis-demonstrable product at MVP."_

The estimate is a number, not a derivation. The scope doubled (3–5 → 8–12) for a list of roughly 6 new primitives; the per-primitive session cost is not named; the dependency on upstream binding closure (BET-9b) is not factored in. If binding repairs do not close before Phase 01 entry, the 8–12 estimate likely inflates further.

**Why LOW:** `autonomous-execution.md` estimates in sessions are explicitly imprecise; the doc acknowledges the user accepted the expanded budget. This is a realism flag, not a structural flaw. A downstream doc 02-plans will re-estimate per-todo. But "AT ANY COSTS" is a commitment without a fallback — if Phase 01 blocks at session 15 on an unforeseen primitive, the doc provides no pre-declared re-scoping protocol.

**Suggested fix (optional):** Add one sentence after line 103: _"If Phase 01 exceeds 15 sessions, re-enter §3.1 scope review; candidate de-scopes are channel count (cut to 3 messaging channels), Foundation Health Heartbeat (defer to Phase 02), or Connection Vault (defer third-party OAuth tokens)."_

---

### R2-15 — LOW (ACCEPTED-AS-OPEN) — Authorship Score N=3 threshold defensibility

**Location:** §3.3 primitive row 18, §8 Test-5, §13 Open question #1.

**Evidence:** N=3 default appears in §2.3 item 3 (line 53), §8 Test-5 (line 577), and §13 is explicit: _"Is Authorship Score threshold N=3 the right default? What's the implementation evidence that higher (or lower) N affects user flow?"_ (line 756).

**Why LOW:** The doc acknowledges this is an open question. N=3 is named as "default" and "configurable" — not asserted as load-bearing. BET-1 minor-mitigation (line 314) proposes lowering to 1 or 2 as a first tuning response. The defensibility of N=3 is exactly what BET-1 + BET-12 are structured to test. An open question in §13 is the correct disposition for a Phase 01 implementation parameter.

**Verdict:** ACCEPTED-AS-OPEN — no action required. Phase 01 implementation will produce the evidence base; v2 correctly flags the uncertainty rather than fabricating a defense.

---

### R2-16 — LOW (ACCEPTED-AS-OPEN) — §7 "2 independent Foundation-unaffiliated stewards" unoperationalized

**Location:** §7 kill criterion 4 bullet 4 (line 560).

**Evidence:** _"At least 2 independent Foundation-unaffiliated stewards confirm the alternative satisfies the thesis before sunset proceeds."_

§13 open question #3 explicitly asks: _"What's the measurement substrate for 'at least 2 independent Foundation-unaffiliated stewards' in §7 item 4 — how are they identified?"_

**Why LOW:** The kill criterion is well-motivated (prevents single-champion capture of "we found a better alternative"). The operationalization is explicitly deferred. Acceptable for a Phase 00 thesis doc.

**Verdict:** ACCEPTED-AS-OPEN. Downstream governance doc owns the steward-identification protocol.

---

### R2-17 — LOW (MINOR) — §5.0 payload "~20 boolean flags" approximate

**Location:** §5.0 Foundation Health Heartbeat design point 5, line 280.

**Evidence:** _"Payload. Per-install random ID (rotated quarterly), Envoy version, **~20 boolean flags** (completed Boundary Conversation / opened Daily Digest this week / ≥1 Grant Moment approved / force-installed a skill / reached posture X / Authorship Score bucket / etc). All aggregated via STAR before reaching the Foundation."_

"~20" is approximate. The downstream ADR (mentioned at line 274) is where the exact flag set should be enumerated. For the thesis doc this level of precision is appropriate — enumerating 20 flags would bloat §5.0. The example flags given cover the key bets (BET-1 Boundary Conversation completion, BET-8 Digest engagement, BET-12 authorship progress).

**Verdict:** MINOR — acceptable as-is. Exact flag set should land in the forthcoming ADR.

---

## Deferred / checked: not surfaced in Round 2

The following Round 1 items were checked and found adequately resolved in v2 (not enumerated as findings):

- **R1 Cluster E (new-scope code):** Capabilities 18–22 added, phase tags added, Connection Vault + algorithm-identifier + independent verifier all landed.
- **R1 Cluster F (threat-model pointers):** §13 Carry-forwards to doc 09 enumerate 7 threats — clock-trust, household-adversarial, ledger retention / GDPR, streaming LLM pre-sign, semantic check attack surface, Shamir shard social-graph, credential storage in Grant Moments. Matches R1 proposed pointer list.
- **R1 Cluster H1 (template import undermines Test-1):** §8 Test-1 explicitly states "Template import is a legal starting point; the Boundary Conversation personalizes and authors beyond it. Users who skip both (no-op envelope) cannot start the agent." Test-5 is the structural defense against template-only posture-maxout.
- **R1 H2 (`force_install=True` weakness):** §4.1 item 16 explicitly names as sovereignty-respect not safety; inventory flagging and ledger visibility mandated.
- **R1 H3 (sawtooth vs ratchet):** Glossary line 709 distinguishes posture slider (bidirectional) from posture ratchet (Authorship-Score gate). Resolved by terminology bifurcation.
- **R1 H4 (Shamir social-graph):** Flagged in §13 carry-forwards #6 for doc 09.
- **R1 H5, H13 (10× calibration):** Replaced with "3× within-niche adoption in sovereignty-plus-authorship TAM" per R1 proposal.
- **R1 H6 ("shared root cause" escape hatch):** §7.2 rewritten with 6-month targeted-experiment countdown replacing escape hatch.
- **R1 H7 (Signal Phase 02 legal):** §10 dependency graph line 668 explicitly names Signal compliance check among per-channel compliance gates.
- **R1 H8 (CO validator continuous tuning):** §5.7 note (line 425) and §10 (line 661) both state "continuous-tuning, not single gate."
- **R1 H9 (CF-10 ambiguous):** §6 CF-10 rewritten with explicit cascade into BET-3 + BET-6.
- **R1 H10 (model adapter vs runtime adapter):** §3.2 capability 15 names runtime picker (kailash-rs-bindings vs kailash-py); capability 16 separately names model picker.
- **R1 H11 (kailash-py glossary wording):** Glossary line 724 rewritten — "In Envoy, Phase 01 sole runtime; Phase 02+ opt-in alternative."
- **R1 H12 (CNCF Envoy Proxy):** §4.1 item 6 and §4.3 table row added.
- **R1 H14 (internal methodology surfaced):** `rules/autonomous-execution.md` reference removed from doc 00.
- **R1 H15 (glossary vs marketing elasticity):** Glossary now includes "User-copy synonym" column (line 699).
- **R1 H16 (5 constraint dimensions unnamed at first reference):** §2.2 line 33 names all five dimensions at first use.

---

## Recommendation

**Doc 00 v2 is CONVERGED, pending R2-09 fix.**

Of the original 61 Round 1 deduped findings, 57+ are resolved. The 4 remaining NEW findings are:

- **1 HIGH (R2-09)** — §3.3 summary numerics inconsistent with table; mechanical 10-line edit resolves it.
- **3 MEDIUM (R2-10, R2-11, R2-12, R2-13)** — each is a single-location prose edit. R2-13 overlaps with R2-09 and is fixed in the same pass.

Per the Round 2 exit criterion (0 CRIT + ≤1 HIGH), doc 00 is at the convergence threshold. Recommend:

1. User authorizes the R2-09 / R2-10 / R2-11 / R2-12 / R2-13 edits (single pass, probably 15 lines total).
2. Re-run a final mechanical sweep to confirm the edits resolved cleanly.
3. Mark doc 00 v2 frozen; proceed to doc 09 (threat model).

No CRITICAL regressions introduced by v1 → v2. The thesis is now falsifiable at the canonical level (§2.4), measurement-substrate-grounded at the bet level (§5.0), and supported by concrete primitive evidence at the scope level (§3.3) — all three were CRITICAL gaps in Round 1.

**End of Round 2 reviewer sweep.**
