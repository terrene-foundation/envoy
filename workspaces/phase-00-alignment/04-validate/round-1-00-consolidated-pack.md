# Round 1 Consolidated Findings Pack — Doc 00

**Date:** 2026-04-21
**Inputs:** 3 sweeps of `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md`:

- `round-1-00-thesis-and-scope-mechanical.md` — 14 findings (0 CRITICAL / 5 HIGH / 3 MEDIUM / 6 LOW)
- `round-1-00-thesis-and-scope-reviewer.md` — 28 findings (5 CRITICAL / 11 HIGH / 9 MEDIUM / 3 LOW)
- `round-1-00-thesis-and-scope-adversarial.md` — 26 findings (3 CRITICAL / 11 HIGH / 9 MEDIUM / 3 LOW)

**Total raw:** 68 findings. Deduplicated + clustered below.
**Purpose:** debate artifact before any fix lands. The user explicitly asked for depth.

---

## Severity overview (deduped)

| Cluster             | Title                                       | CRIT  | HIGH   | MED    | LOW   | Convergence cost estimate                                                  |
| ------------------- | ------------------------------------------- | ----- | ------ | ------ | ----- | -------------------------------------------------------------------------- |
| A                   | Upstream primitive reality                  | 3     | 5      | 3      | 0     | HIGH — cross-cutting rewrite of §3.3, BET-9, +1 new workspace artifact     |
| B                   | Measurement / falsification incompatibility | 1     | 3      | 2      | 0     | MEDIUM — new §5.0 subsection, rewrite falsifying-evidence across 5 bets    |
| C                   | Meta-USP self-contradictions                | 1     | 3      | 1      | 0     | MEDIUM — §9.4 reconciliation + §4.1 sub-non-goal + Phase 01 scope decision |
| D                   | Thesis coherence                            | 1     | 4      | 0      | 0     | HIGH — §2.4 rewrite, §2.2 rewrite, §8 new Test-5, new BET-12               |
| E                   | New-scope code not listed                   | 0     | 3      | 2      | 0     | LOW — phase-column addition + 3 new §3.3 new-code rows                     |
| F                   | Threat-model gaps (to doc 09)               | 0     | 2      | 5      | 0     | LOW for doc 00 — pointer; full work is doc 09                              |
| G                   | GTM / financial / legal realism             | 1     | 6      | 1      | 1     | HIGH — new BET-11, Phase 05 split, base-rate section                       |
| H                   | Design escape-hatches + other               | 0     | 0      | 7      | 7     | LOW — cleanup pass                                                         |
| **Total (deduped)** |                                             | **6** | **26** | **21** | **8** | 61 unique findings                                                         |

**Convergence verdict:** Round 1 surfaces structural issues large enough that **doc 00 cannot be declared converged** without at least clusters A, B, C, D resolved. Clusters E, F, G, H are applicable but not uniquely blocking.

**Recommended path to convergence:**

1. User debates this pack; we agree on directions for A–D.
2. Apply fixes across A–D inline (one pass each).
3. Re-run Round 2 (all three sweeps) — if <2 HIGH, doc 00 converged.
4. Apply E + G in same pass (structural but not thesis-breaking).
5. F becomes doc 09 input; no further doc 00 action.
6. H cleanup pass.

---

## Cluster A — Upstream primitive reality (6 CRITICAL findings on one root cause)

**Root cause:** §3.3's primitive-inheritance table claims the Python binding (or `kailash-py`) ships ~10 specific primitives whose reality in `workspaces/internal/kailash-rs-survey-2026-04-21.md` is: either not in the binding surface, declared-but-non-functional (`BaseAgent.execute()` NotImplementedError, `OrchestrationRuntime.run()` stub, A2A methods absent), or with name-divergence (`AuditLogger` vs `TieredAuditDispatcher`). The `.pyi` is 55% accurate overall. BET-9 treats this as _"Phase 01 implementation discovers..."_ — but the evidence exists pre-flight.

**Findings contributing:** Mech M-01 through M-07, M-11, M-14 | Rev F-03 (CRIT), F-04 (CRIT), F-05 (CRIT), F-11 (HIGH), F-12 (HIGH) | Adv F-01 (CRIT)

**Specific gaps named:**

- `cascade revocation` — per survey: "NOT explicitly surfaced in the binding — must verify behavior against Rust source or implement at Envoy level."
- `@classify` / `apply_read_classification()` / `format_record_id_for_event()` — kailash-py idioms, not on Rust-binding surface.
- `McpGovernanceEnforcer` / `McpGovernanceMiddleware` — not named in survey; MCP stdio/SSE/HTTP transports not bound from Python (C4).
- `PostureStore` / `SQLitePostureStore` / `PostureEvidence` / `EatpPosture` (Phase-13 types) — .pyi missing 8 Phase-13 types.
- `PlanSuspension` — not in binding surface.
- `intersect_envelopes()` — not enumerated on `PactGovernanceEngine` (73+ methods listed).
- `TieredAuditDispatcher` — binding has `AuditLogger` (Enterprise); dispatcher by that name missing.
- Kaizen `BaseAgent.execute()` raises `NotImplementedError`; 3/7 pre-built agents crash.
- `OrchestrationRuntime.run()` returns static dict stub `{"agents": {"name": "configured"}}`.
- `A2AProtocol.send_message / receive_message` declared in `.pyi` but don't exist.
- `DataFlow.execute_raw()` silently drops params — active SQLi surface.
- `SessionMemory` / `SharedMemory` .pyi wrong (`.set/.get/.delete` vs actual `.store/.recall/.remove`).

**Phase 01 exposure:** The Boundary Conversation agent is declared in ROADMAP Phase 01 as "Kaizen `BaseAgent` with scripted Signature." If `BaseAgent.execute()` raises, Phase 01 cannot ship without upstream binding fixes or an Envoy-level reimplementation. Doc 00 does not model this.

**Proposed fix (for debate):**

1. Rewrite §3.3 primitive-inheritance table with three columns: _primitive_ × _kailash-py status_ × _kailash-rs-bindings status_ (each of: Confirmed / Unconfirmed / Absent / Broken + survey-evidence citation).
2. Demote `§3.3`'s 70/30 ratio claim to a post-survey open question.
3. Split BET-9 into:
   - **BET-9a — Upstream Kailash crates are sufficient** (mostly on-track per EATP D6 / PACT N1–N6 verified).
   - **BET-9b — Python-binding surface exposes usable versions of those primitives by Phase 01 exit** (already partially disconfirmed; mitigation path active).
4. Add Phase 00 gate item: "Kailash binding repair (BINDING-AUDIT B1, B3, C4–C6) must close OR Envoy-level reimplementations must be scoped as Phase 01 work before Phase 01 opens."
5. Create new workspace artifact: `workspaces/phase-00-alignment/01-analysis/01-kailash-py-survey-2026-04-21.md` (mirror of kailash-rs survey; Phase 01 runs on kailash-py, no audit yet exists).
6. Create new workspace artifact: `workspaces/phase-00-alignment/01-analysis/02-primitive-reconciliation.md` (per-primitive cross-reference of doc 00 §3.3 claims vs both surveys).

**Alternative directions to debate:**

- Accept binding reality and re-home Phase 01 on kailash-py exclusively, deferring all Rust-binding decisions to Phase 02 entry. This is already true per ROADMAP, but doc 00 should stop pretending primitives exist on the binding.
- Narrow Envoy's primitive surface to only those primitives verified in kailash-py (pending survey). Phase 01 scope collapses; re-estimate.

---

## Cluster B — Measurement / falsification incompatibility (1 CRITICAL)

**Root cause:** §4.1 items 7 + 8 + 11 forbid phone-home telemetry, registration, and hosted identity. §5 bets and §7 kill criteria rely on metrics that require exactly those mechanisms: WAU, completion rate, week-2 retention, per-install behavior, cohort sentiment, install-survey responses. The doc makes its own kill criteria structurally non-firing.

**Findings contributing:** Mech M-12 (trivial) | Rev F-02 (CRIT), F-08 (HIGH), F-20 (MED), F-22 (MED) | Adv F-23 (MED)

**Specific failures:**

- §7 kill criterion #1 — "<1,000 WAU at 18 months." No WAU measurement mechanism consistent with §4.1.
- BET-1 — "<20% complete the Boundary Conversation." Completion is a local event; cannot be reported without phone-home.
- BET-1 — "Week-2 retention <30%." Requires per-install tracking.
- BET-3 — "Install-survey responses show <30% sovereignty reasons." Requires opt-in survey at install, which crosses the phone-home line for most implementations.
- BET-4 — "Indie cohort feedback: 'Foundation' reads bureaucratic." Qualitative signal with no methodology.
- BET-8 — "<20% of active users open the Daily Digest twice in 7 days." Requires per-install telemetry.

**Proposed fix (for debate):**

1. Add new subsection **§5.0 "Measurement methodology under §4.1 non-goals"** that enumerates:
   - **Signals the team CAN collect without phone-home**: GitHub stars, Envelope Library Foundation-Verified template fetch counts, public-discourse mentions (HN/X/blog), opt-in survey responses via Foundation Discord/forum, third-party blog post reports, GitHub issue volume, Envelope Library publish counts.
   - **Signals the team CANNOT collect**: WAU, retention, per-user behavior, completion rates, conversion rates.
   - **Which bets rely on which signals** and therefore which bets are structurally unmeasurable without a new opt-in telemetry mechanism.
2. Decide one of:
   - **(B1) Accept indirect measurement.** Rewrite all affected falsifying evidence in terms of public-discourse + Envelope Library proxies. Kill criteria become slower but survive §4.1.
   - **(B2) Design an opt-in anonymous aggregate-telemetry Grant Moment** (Apple-ODM / DuckDuckGo-style). The installer asks once; default is Yes with one-keystroke No; payload is a weekly heartbeat containing a random install-ID + version + a small set of boolean flags (opened Digest this week, completed Boundary Conversation) aggregated cryptographically to preserve anonymity. Adds a new ADR; weakens §4.1 item 7 narrowly with full disclosure.
3. Rewrite §7 kill criterion #1 under whichever path is chosen.

**Open question for debate:** Does the user prefer path (B1) or (B2)? (B1) preserves the sovereignty purity but makes kill criteria fire slowly or not at all; (B2) measures real usage at modest sovereignty cost (the user chose to share; Grant Moments are the consent mechanism so this is actually on-thesis).

---

## Cluster C — Meta-USP self-contradictions (1 CRITICAL)

**Root cause:** §9.4 declares four anti-patterns that break "AI as personal extension of self." §4.1 + §4.2 + §3.2 specify Phase 01 and capability decisions that violate those anti-patterns.

**Findings contributing:** Rev F-07 (HIGH), F-10 (HIGH), F-21 (MED) | Adv F-02 (CRIT)

**Specific contradictions:**

1. **Phase 01 CLI+Web-only violates §9.4 anti-pattern 2** ("Envoy has a primary UI separate from the user's existing channels"). Phase 01 (per ROADMAP) ships CLI + Web. A user running `envoy init`, completing Boundary Conversation in terminal or browser, then using `envoy boundaries` is _going to_ the product. This is the exact anti-pattern. The doc's first shipped surface is structurally off-thesis.

2. **Foundation-hosted `kailash-rs-bindings` binary is de facto centralization** — breaks BET-3 sovereignty. If the Foundation GitHub org is delisted, PyPI has an outage, or binary-signing key is compromised, every default Envoy install is affected. Opt-out to `kailash-py` is the structural mitigation but its safety is not audited (→ cluster A).

3. **§9.4 anti-pattern 4** ("credentials for action live anywhere other than on the user's own device") vs **§3.2 capability 11** (Trust Vault sync via iCloud/Dropbox/Keybase/etc). iCloud is not the user's own device. §4.1 item 10 softens with "end-to-end encrypted"; §9.4 is absolute. Ciphertext on third-party is a grey area that the thesis must address explicitly.

**Proposed fix (for debate):**

1. **Phase 01 anti-pattern violation.** Three resolution options:
   - **(C1a) Promote one channel to Phase 01.** Telegram is the cheapest (bot API, webhook into Nexus). Adds 1–2 sessions; Phase 01 UX becomes CLI + Web + Telegram. Acknowledges that the CLI+Web is admin-only.
   - **(C1b) Narrow §9.4 anti-pattern 2.** Distinguish "onboarding UI" from "daily-use UI." The anti-pattern applies only to daily-use UI — first-run setup is allowed to be a separate surface. This is a concession but honest.
   - **(C1c) Accept Phase 01 as cohort-limited.** Explicit note: Phase 01 is for CLI-comfortable prosumers; BET-1 evidence from Phase 01 is not representative of the Phase 02+ cohort. This path must be named in doc 00 and inherited by all downstream docs.

2. **Foundation binary centralization.** Add §4.1 sub-non-goal: _"Envoy does not claim sovereignty-grade runtime independence until the Foundation binary distribution has at least N=3 independent mirrors AND a published key-rotation + binary-compromise response plan. Until then, the `kailash-py` opt-in is the structural mitigation; its audited equivalence is required."_ Cross-reference to cluster A.

3. **§9.4 anti-pattern 4 vs vault sync.** Rewrite anti-pattern 4: _"Credentials or action-authorizing state are stored in any form — ciphertext or plaintext — by a third party in a manner that deprives the user of sole control. Ciphertext at rest on a third-party store where the user holds the only decryption key is a permissible configuration only when explicitly opt-in (per §4.1 item 10) and where the ciphertext format does not leak action-informing metadata."_

**Open question:** Does the user pick C1a (promote channel), C1b (narrow anti-pattern), or C1c (accept cohort limitation)? The thesis answer depends heavily on this.

---

## Cluster D — Thesis coherence (1 CRITICAL, 4 HIGH)

**Root cause:** The canonical thesis statement in §2.4 is tautological (describes product mechanics); the "primary surface" test in §8 is passable by a hardened-adjacent fork (feature parity, not category); the irreducibility claim in §2.2 ignores delegation-upward; the doc does not engage with the prior-art graveyard for governance-as-primary-surface products.

**Findings contributing:** Rev F-01 (CRIT), F-06 (HIGH), F-16 (HIGH) | Adv F-14 (HIGH), F-15 (HIGH)

**Specific issues:**

1. **§2.4 canonical thesis is tautological.**
   - Quoted: _"Envoy is autonomous AI where the human holds a signed, revocable authority that every agent action traces to."_
   - This is true by construction for any envelope-signing product; it is not a claim about the world that could be wrong. Reviewer proposes a load-bearing alternative: _"The durable, defensible role of the human in autonomous AI is the authorship of envelopes; products that ritualize this authorship will earn primary-surface loyalty that tool-frame AI products cannot."_ This IS falsifiable (users may prefer frictionless autonomy; authorship may be delegable).

2. **§8 "primary surface" test is feature-parity with audit-heavy alternatives.** A hardened fork of any autonomous-AI product with first-run envelope import, pre-action signing, revoke button, and channel-editable config passes all 4 tests without implementing the Envoy thesis. Fifth test needed: authorship itself (you cannot pass by importing a template).

3. **§2.2 "irreducible human contribution" ignores delegation-upward collapse.** An enterprise buys 500 Envoy licenses; IT authors one envelope; employees accept. The envelope is "signed by the user" but not _authored_ by them. Same pattern in Shared Household (parent authors, children accept) and in Foundation-Verified template import (one author, many signers). The "irreducibility" claim reduces to "consent to an envelope" — a weaker claim than "authorship of judgment."

4. **Governance-as-primary-surface has a prior-art graveyard the doc doesn't study.** Little Snitch / Ghostery / DuckDuckGo Privacy / Tripwire / 1Password (pre-auto-fill) / iOS App Tracking Transparency — most mainstream products either make governance invisible (adblockers) or niche-power-user (Little Snitch). Products that make governance the primary conscious surface do not break into mainstream. The doc asserts Envoy will invert this without engagement.

5. **Cloud-convenience is an accelerating force, not static.** LLM inference cost fell 30–100× in 2023–2025; OS-integrated agent primitives (Apple Intelligence, Gemini-in-Android, Copilot-in-Windows) are shipping. BET-3 treats sovereignty as a static bet; it should be trajectory-aware.

**Proposed fix (for debate):**

1. **Rewrite §2.4** as falsifiable market claim. Keep the mechanical description as §8 positioning but demote from canonical.
2. **Rewrite §2.2** with either:
   - **(D2a) Defend authorship:** require every Envoy user produce ≥1 _novel_ envelope constraint beyond template within 30 days. Measurable against template-fork counts.
   - **(D2b) Retract irreducibility:** replace with a weaker canonical claim: _"The minimum load-bearing human contribution is informed consent to an envelope. Envoy's thesis depends on making that consent dense enough to be meaningful — via the Boundary Conversation, Daily Digest review, and Weekly Posture Review — even when the envelope itself is imported."_
3. **Add Test-5** to §8: _"The product cannot execute an action for which the user cannot produce a human-readable narrative of why they authorized it."_ Tests authorship, not audit.
4. **Add §2.5 "Prior art"** — cite Little Snitch (0.5–2% Mac adoption over 15 years), DuckDuckGo (invisible governance = adoption; visible = niche), 1Password (auto-fill is the "remember forever" toggle users move to), iOS ATT (OS-gated, not user-chosen). Name what Envoy does differently: structural pre-authorization + envelope as authored artifact, not per-action approval.
5. **Add BET-12** (governance-primary-surface palatability): _"Users accept a product whose primary conscious surface is governance, at adoption rates comparable to niche-power-user tools (Little Snitch class, 0.5–2% of TAM)."_ Falsifies explicitly on small cohort size.
6. **Make BET-3 trajectory-aware** — add falsifying evidence: _"If OS-integrated agent products ship envelope-equivalent governance within 24 months of Phase 01, the differentiator collapses and Envoy competes on sovereignty-narrative-only."_

**Open question:** D2a (authorship-defense, higher thesis bar) or D2b (consent-claim, humbler thesis)?

---

## Cluster E — New-scope code not listed in §3.3 (3 HIGH, 2 MEDIUM)

**Root cause:** Several capabilities advertised in §3.2 or asserted in §4.1 require Envoy-new-code that §3.3 does not list. Downstream docs will inherit scope gaps.

**Findings contributing:** Rev F-14 (Trust Vault sync), F-17 (capabilities unphased), F-18 (algorithm-identifier schema), F-25 (independent ledger verifier) | Adv F-10 (credential storage / Connection Vault) | Mech M-08/M-09/M-10

**Specific gaps:**

- Trust Vault sync (capability 11) — no phase exit.
- Trust posture slider (capability 7) — no Phase 01 primitive.
- Cascade revocation (capability 8) — not on binding + not in new-code list.
- Algorithm-identifier schema (implied by §4.1 item 9 crypto-agility claim) — not listed.
- Independent ledger verifier (required by §3.1 Phase 01 exit "verify it independently") — not listed.
- Connection Vault for third-party credentials (Grant Moments take API keys) — not addressed.

**Proposed fix:**

1. Add a "First phase" column to §3.2 capabilities table.
2. Add the following to §3.3 Envoy-new-code list:
   - Connection Vault — OS-keychain + mobile-Secure-Enclave wrapper; per-principal isolation.
   - Algorithm-identifier schema + versioned signed-artifact format + legacy-verification resolver.
   - Independent reference-verifier tool (different codebase than writer) for the Ledger.
   - Cascade-revocation implementation (if upstream binding does not expose it; cross-reference cluster A).
3. Phase-tag all 17 capabilities; reconcile any Phase-01 primitive gaps to ROADMAP.

---

## Cluster F — Threat-model gaps (doc 09 inputs)

**Root cause:** Multiple threats surface in adversarial review; doc 00 is not the place to resolve them but must name them for doc 09.

**Findings contributing:** Adv F-07 (household-adversarial), F-08 (clock-skew bypass Temporal), F-09 (ledger scale/retention/GDPR), F-16 (streaming LLM pre-sign), F-18 (semantic envelope checks), F-22 (Shamir shard social-graph)

**Proposed fix:** Add to doc 00 §13 (open questions) a pointer: _"The following threats are sized in doc 09: clock-trust for Temporal dimension; household-adversarial scenarios (divorce, elder-abuse, teen-rebellion, DV); ledger retention + GDPR right-to-erasure on append-only hash chain; streaming LLM pre-action signing; semantic envelope checks vs O(1) performance claim; Shamir shard social-graph exposure; credential storage in Grant Moments."_ No further doc 00 work.

---

## Cluster G — GTM / financial / legal realism (1 CRITICAL, 6 HIGH)

**Root cause:** Doc 00 names a Foundation-stewardship model without a financial viability story; asserts the Slack/Figma/Notion playbook with no distribution engine; bundles SOC2 + HIPAA + GDPR + SSO into a single Phase 05 with a 9-month target; treats 7 ADR-0009 legal items as procedural rather than blocking.

**Findings contributing:** Adv F-03 (CRIT), F-04, F-05, F-06, F-12, F-13, F-24 | Rev F-15 (HIGH), F-19 (MED)

**Specific issues:**

- **Financial viability not modeled.** Envelope Library moderation, Foundation sync node hosting, trademark maintenance (USPTO+EUIPO+UK IPO), cross-SDK parity engineering, legal retainer — unfunded. Base rate: Mastodon (stagnant), GPG (burnout), OpenSSL (pre-Heartbleed unpaid maintainers). Positive counter-cases (Kubernetes, Linux) have full-time commercial sponsors.
- **No distribution engine.** Slack/Figma/Notion all had VC-funded sales + marketing. Envoy has a Foundation. Prosumer-first lands in enterprise motion fails without capital.
- **15-min Boundary Conversation vs 10-min Phase 02 install-to-first-value** — contradictory. Plus Shamir 3-of-5 paper-shard ritual cannot be shortcut (wall-clock physical event).
- **Ritual-adherence base rates are devastating.** Fitbit 30–40% daily engagement (unworn within 6mo for 50–70%); Mint/YNAB weekly review 15–25%; Headspace 30-day retention 5–10%. BET-8 falsification threshold at <20% is lower than these products achieve.
- **Sovereignty cohort base rates are brutal.** Gmail→Proton: ~0.1%. iCloud→Nextcloud: ~2% (mostly corporate). WhatsApp→Signal: ~2%. Mastodon: ~0.3%. Bitwarden self-hosted vs cloud: ~5%. PGP historical: <0.1%.
- **Byte-identical parity ambiguous for LLM-composing runtimes.** Contract parity (signing, envelope, ledger formats) is byte-identical and achievable. Behavioral parity (same user input → same output) is not achievable because LLMs are non-deterministic.
- **Legal counsel under-modeled.** Export control (EAR 734.3 tightening), CC BY 4.0 attribution through dist pipelines, Foundation charter compatibility (board members can block), trademark discretion (USPTO §2(d) likelihood-of-confusion), SPDX scanner false-positives, SLIP-0039 library license mixing, user-facing disclosure length.
- **Phase 05 timeline unrealistic.** SOC2 Type 1 = 4–6mo for funded team (18mo for Foundation). HIPAA = BAA architecture + PHI controls (Foundation cannot be BAA party). GDPR DPIA = DPO + right-to-erasure on append-only ledger. SSO/SAML/SCIM directly conflicts with §4.1 item 8 (no hosted identity).

**Proposed fix (for debate):**

1. **Add BET-11 — Financial viability of Foundation stewardship.** Falsifying evidence: Foundation enters Year 2 with <N months runway and no committed sponsor pipeline. Mitigation paths: membership dues, grants, sponsored development. Counter-factual: if unfunded, a commercial entity emerges to operate the ecosystem.
2. **Distinguish contract parity (byte-identical) from behavioral parity (semantic-equivalent).** Rewrite BET-6 accordingly. Conformance vectors test the contract surface; LLM-composed paths are out of scope for byte-identity.
3. **Split Phase 05 into 05a/b/c.** 05a = SOC2 readiness (operational history 12mo). 05b = HIPAA-readiness via third-party BAA operator (Foundation not a BAA party). 05c = GDPR DPIA via scoped jurisdiction or right-to-erasure design.
4. **Reconcile 15-min Boundary Conversation vs 10-min install-to-first-value.** Separate "first value" from "full onboarding." First value = template import + one action, <10min. Full onboarding = Boundary Conversation + Shamir, multi-session, progressive disclosure. Explicit note in §5.1 + Phase 02 exit criteria.
5. **Add base-rate section.** §2.5 or appendix. Cite Fitbit / Mint / Headspace / Proton / Nextcloud / Signal / Mastodon / Bitwarden / PGP. Name how Envoy's structural differences change (or don't change) the base rates.
6. **Add a non-goal.** _"Envoy does NOT target the convenience cohort. The TAM is the sovereignty-plus-agency cohort, which is <2% of the mainstream market."_
7. **Resolve SSO/SAML thesis contradiction.** Either Envoy has no hosted identity (stays true to §4.1 item 8 and skips SAML) or ships an optional hosted-identity connector for enterprises.
8. **Name the distribution engine explicitly** — or name the non-goal ("Envoy does not target enterprise adoption in Phase 05; enterprise adoption is a third-party commercial ecosystem motion, and the Foundation does not invest in it").

**Open question:** Does the user want an explicit BET-11 (financial) and a Phase 05 split? This is significant scope work in doc 00.

---

## Cluster H — Design escape-hatches + cleanup (7 MEDIUM, 7 LOW)

Individually minor; collectively erode the thesis. Fix in a single cleanup pass after A–G land.

**Sub-findings:**

- **H1** — Adv F-17: Template import shortcut undermines §8 Test-1.
- **H2** — Adv F-19: `force_install=True` is a permanent weakness (iOS untrusted-dev, npm --force patterns show routine bypass).
- **H3** — Adv F-21: Posture "ratchet" is actually sawtooth; single-slider vs per-dimension unresolved.
- **H4** — Adv F-22: Shamir "trusted humans" social-graph exposure unaddressed.
- **H5** — Rev F-09: §7 panic trigger ("categorically-better alternative + 10×") miscalibrated for niche (any mainstream AI company launching governed-agents hits 10× trivially).
- **H6** — Rev F-13: §7.2 "shared root cause" escape hatch is subjective; enables sunk-cost capture.
- **H7** — Rev F-23: Signal channel Phase 02 may be legally infeasible (Signal third-party client posture).
- **H8** — Rev F-24: §10 skill-ecosystem gates treat CO-validator tuning as linear; it's continuous.
- **H9** — Rev F-26: §6 CF-10 ambiguous (already Phase 01 state).
- **H10** — Rev F-27: Phase 01 model adapter vs runtime adapter subtle gap.
- **H11** — Rev F-28: Glossary kailash-py wording ambiguous.
- **H12** — Mech M-13: CNCF Envoy Proxy missing from adjacent-products table (name collision not discussed in §4.3).
- **H13** — Adv F-25: §7 #4 10× adoption miscalibrated for niche TAM.
- **H14** — Adv F-26: §12 references `rules/autonomous-execution.md` — internal methodology surfaced to external readers.
- **H15** — Adv F-20: Glossary rigidity vs marketing elasticity.
- **H16** — Mech M-12: 5 constraint dimensions not named at first reference (§2.2 should name them).

---

## Summary — what the user is being asked to debate

**Structural decisions (cluster lead):**

1. **[A]** Rewrite §3.3 as a three-column primitive-status table. Split BET-9 → BET-9a + BET-9b. Add Phase-00 gates for binding repair + kailash-py survey + primitive reconciliation. **Agree?**
2. **[B]** Accept indirect measurement (B1) or design opt-in Grant-Moment-gated telemetry (B2)? **Pick one.**
3. **[C]** For Phase 01 CLI+Web-only vs §9.4 anti-pattern 2: promote Telegram to Phase 01 (C1a) / narrow anti-pattern to exclude onboarding (C1b) / accept cohort limitation (C1c)? **Pick one.**
4. **[D]** Rewrite §2.4 canonical thesis as falsifiable claim, rewrite §2.2 as authorship-defense (D2a) or consent-claim (D2b), add §2.5 prior-art, add BET-12 (governance-primary-surface palatability), make BET-3 trajectory-aware. **Agree + pick D2a/D2b?**
5. **[G]** Add BET-11 (financial viability), split Phase 05 into 05a/b/c, distinguish contract parity from behavioral parity, add base-rate section, resolve SSO/SAML contradiction. **Agree?**

**Non-structural fixes (apply without further debate):**

6. **[E]** Phase-tag §3.2 capabilities; add Connection Vault, algorithm-identifier schema, independent verifier, cascade-revocation impl to §3.3 new-code list.
7. **[F]** Add §13 doc-09 pointer for 6 named threats.
8. **[H]** Cleanup pass on 16 escape-hatch / consistency / external-reference items.

Once A–D (and G) have direction, I apply, re-run Round 2 (reviewer + adversarial + mechanical), and converge when <2 HIGH across two rounds.
