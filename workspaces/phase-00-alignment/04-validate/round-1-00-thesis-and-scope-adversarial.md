# Round 1 — Adversarial Review of `00-thesis-and-scope.md`

**Reviewer role:** Skeptical, security-minded technical buyer + investor. Adversarial by design.
**Target:** `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` (draft v1, 2026-04-21).
**Corroborating sources read:**

- `CHARTER.md`, `DECISIONS.md`, `ROADMAP.md`, `README.md`
- `workspaces/internal/openclaw-analysis/02-plans/superior-product-concept-2026-04-21.md`
- `workspaces/internal/openclaw-analysis/04-validate/redteam-critique-2026-04-21.md`
- `workspaces/internal/kailash-rs-survey-2026-04-21.md`

**Classification policy:**

- **CRITICAL** — the finding, if true, invalidates the thesis; the doc would need a rewrite, not an edit.
- **HIGH** — a named strategic bet or capability claim is structurally unsafe; the doc ships unless mitigated in this phase.
- **MEDIUM** — a real risk that the doc should name but does not; remediation is a new section, bet, or non-goal.
- **LOW** — an inconsistency or unstated assumption that weakens the thesis but does not falsify it.

**Tally:** 26 findings — 3 CRITICAL, 11 HIGH, 9 MEDIUM, 3 LOW.

---

## F-01 — CRITICAL — BET-9 is already falsified by the kailash-rs survey; the doc does not know it

**Attack vector:** §5.9 (BET-9) claims "Kailash primitives are sufficient" as a claim whose falsification is a Phase 01 implementation event. The claim is ALREADY falsified pre-flight by evidence the same workspace already holds.

**Why it works:** The kailash-rs survey at `workspaces/internal/kailash-rs-survey-2026-04-21.md` enumerates binding-layer gaps that are not side concerns — they are the Envoy hot path:

- `Kaizen BaseAgent.execute()` raises `NotImplementedError`; 3 of 7 pre-built Kaizen agents crash through the Python binding. The **Boundary Conversation agent is declared in ROADMAP Phase 01 as a Kaizen `BaseAgent` with scripted Signature**. That is the onboarding-critical surface. It cannot execute.
- `OrchestrationRuntime.run()` returns a static dict stub `{"agents": {"name": "configured"}}`. Envoy's Daily Digest, Weekly Posture Review, Monthly Trust Report are all described as "Kaizen scheduled agents" — orchestrator-shaped.
- `A2AProtocol.send_message / receive_message` are declared in the `.pyi` but do not exist at runtime. The brief at §3.3 calls A2A "shipped" and lists it among the load-bearing primitives.
- MCP stdio/SSE/HTTP transports are not bound from Python. The PACT middleware story for third-party MCP depends on them.
- `SessionMemory` / `SharedMemory` .pyi declares `.set/.get/.delete`; actual methods are `.store/.recall/.remove`. Anyone who trusted the stubs writes broken code.
- `AgentCheckpoint` constructor signature is wrong in the stub (`(agent_name, model, stored_step)` actual vs .pyi declaration).
- `FilterCondition` missing 5 methods (gt/gte/lt/lte/in_list).
- `DataFlow.execute_raw(params)` silently drops params — SQL-injection surface in the binding itself.
- **`.pyi` overall ~55% accurate, 26 inaccuracies, 8 types missing entirely.**

The doc §5.9 frames BET-9 as if this evidence is forthcoming. The survey is sitting in the same workspace, authored two days before the thesis. The thesis treats it as if it hasn't been written.

Base rates: when a binding layer ships with ~45% of its declared type surface wrong or non-functional, and two cornerstone primitives (BaseAgent, OrchestrationRuntime) are stubs — the "compose 70% from shipped primitives" plan cannot hold. The engineering case in §3.3 ("~70% of Envoy's functionality composes on shipped Foundation primitives; ~30% is new UX + distribution code. This is the engineering case for the product being feasible at the stated phase cadence.") is load-bearing and it is built on sand.

Compounding: Phase 01 is scoped as 3-5 sessions. If Envoy must fix upstream (mitigation path "minor" in §5.9), every one of these gaps is a multi-session upstream fix plus a release plus an integration pass. Realistic Phase 01 becomes 10-20 sessions, not 3-5.

**What the doc would have to do to defend:**

1. Read the kailash-rs survey explicitly and re-author §3.3's "ratio" claim against the actual binding state. Name which primitives are SHIPPED AND FUNCTIONAL, SHIPPED BUT STUB, or DECLARED IN .pyi BUT DOES NOT EXIST.
2. Promote "Kailash binding repair" from a Phase-01 mitigation to a **Phase 00 gate item**. The Boundary Conversation agent cannot ship on Phase 01 if BaseAgent raises NotImplementedError on day 1.
3. Re-estimate Phase 01 session budget against the actual binding-repair surface. 3-5 sessions is predicated on primitives being sufficient; they are not.
4. Add a new non-goal: "Envoy does not ship if more than N primitives must be repaired upstream to hit Phase 01 exit" with N as a concrete integer.
5. Move BET-9's falsification trigger from "Phase 01 discovers X" to "Phase 00 closes out the binding-defect list or the thesis is revised."

---

## F-02 — CRITICAL — The meta-USP self-contradiction (§9.4) silently kills Phase 01

**Attack vector:** §9.4 states: "The meta-USP is broken if … Envoy has a primary UI separate from the user's existing channels (→ requires the user to 'go to' the product)." Phase 01 (per ROADMAP) ships **CLI + Web only**, with channels deferred to Phase 02. The user installs Envoy, runs `envoy init`, does the 15-minute Boundary Conversation, runs `envoy up`, and opens `envoy boundaries` in a web UI or TUI. Every one of those is "going to" the product.

**Why it works:** The doc defines its own structural anti-pattern ("requires the user to go to a primary UI separate from their existing channels") and then schedules the first product release to violate it. This is not a minor tension — §9.4 explicitly says "Every downstream doc must test its design against these anti-patterns." The thesis doc cannot test Phase 01 against its own anti-pattern list without finding Phase 01 in violation.

The doc half-acknowledges this in §4.2 ("Channels beyond CLI + Web — Phase 02 — Ritual loop must be validated on one ergonomic + one programmatic channel first") but never reconciles the contradiction. A reader who takes §9.4 seriously reads Phase 01 as a structural failure of the meta-USP and concludes Envoy cannot prove its own thesis during MVP.

There's a subtler failure: users who complete the Boundary Conversation in CLI + Web on Phase 01 and then onboard again onto channels in Phase 02 have to either re-do the boundary conversation or have their envelope silently ported. Either choice is bad — redoing burns the 15-minute trust-forming ritual; silent port undermines the "you hold signed, revocable authority" narrative because the port is a state translation the user did not sign.

Compounding: the thesis in §2.4 is "the user's felt experience that they are holding signed, revocable authority." Phase 01 is the first user experience of that thesis. If Phase 01 is structurally off-thesis, the first wave of public feedback is "this is a CLI tool for nerds, it's not the channel-native agent you promised" — which becomes the anchor for all subsequent impressions.

**What the doc would have to do to defend:**

1. Either (a) promote at least ONE channel (iMessage / Telegram / Signal) to Phase 01 and accept the slippage, or (b) weaken §9.4 so CLI/Web count as "channels the user already uses" (defensible but weakens the whole §3 capability list that says "23+ channels" is the surface).
2. Add a new non-goal: "Envoy does NOT ship a non-channel-native Phase 01 if doing so would violate the §9.4 meta-USP."
3. Name the envelope-portability guarantee explicitly: "An envelope declared in Phase 01 CLI+Web MUST port losslessly and verifiably to Phase 02 channels, with the port itself being a signed Delegation Record the user approves."
4. Re-frame §9.4 item 2 to distinguish "onboarding UI" from "daily-use UI" — the anti-pattern is only about daily-use UI separation. This is a concession but an honest one.

---

## F-03 — CRITICAL — Foundation-stewardship governance model has no financial viability story

**Attack vector:** The doc asserts throughout that Terrene Foundation (Singapore CLG) will steward the product, run infrastructure (sync node per ADR-0007, Envelope Library per ADR-0004), sign Foundation-Verified envelopes, engage legal counsel for 7 ADR-0009 items, maintain cross-SDK parity, and operate indefinitely without a commercial entity. There is no model for who pays for any of this, and §4.1 item 5 explicitly rules out Foundation-operated commercial offerings.

**Why it works:** Foundations that depend on volunteer maintenance and donation runway go through predictable phases:

1. Euphoric growth while founders are paid by day jobs or prior capital.
2. Maintainer burnout at 18-36 months.
3. Either corporate capture (a commercial fork with one primary maintainer), quiet abandonment, or hand-off to a commercial entity that "stewards" for the Foundation and eventually owns the roadmap.

Analogous patterns: OpenSSL pre-Heartbleed (3 unpaid maintainers handling Internet-scale crypto), GPG (one unpaid maintainer for a decade), log4j pre-Log4Shell (unpaid). Positive counter-examples — Kubernetes, Linux kernel — have full-time commercial sponsors (Google/RedHat/Intel) paying FTE headcount. Mastodon — one primary maintainer, essentially stagnant user growth since 2022.

For Envoy specifically:

- The Envelope Library (ADR-0004) needs moderation staff, spam/abuse processing, publisher-key management, signing infrastructure operations.
- The Foundation sync node (ADR-0007) is hosted infrastructure with running costs proportional to user base.
- Trademark maintenance (ADR-0009 §6) is an ongoing legal spend across USPTO + EUIPO + UK IPO.
- Cross-SDK parity (BET-6) requires conformance vectors maintained at every release on both Rust and Python — which per the kailash-rs survey is where the most engineering drift happens.

Base rate: most Foundation-stewarded software ecosystems either (a) incubate into Apache / Linux Foundation with paid TAB seats funded by corporate sponsors, or (b) fork a commercial entity. "Singapore CLG that never monetizes" is a rare shape, and the public record of similar structures does not include one this ambitious.

The doc treats this in §5.4 (BET-4) as a credibility asset, not a financial risk. It does not model the most-likely failure mode: Foundation cannot fund Year 3 operations, a commercial fork appears, and the "no capture" rule silently breaks because the fork is where the active development is.

**What the doc would have to do to defend:**

1. Add a new bet (BET-11 — financial viability) with an explicit funding model and falsification: "If the Foundation enters Year 2 with less than N months of runway and no committed sponsor pipeline, the thesis is at risk."
2. Name the allowable revenue streams for the Foundation (membership dues, grants, sponsored development, no consumer product) and the allowable revenue streams for third-party commercial entities (managed services, support contracts, enterprise deployments).
3. Add a new non-goal: "Foundation will not operate a commercial product, but the Foundation WILL accept sponsored development from commercial entities that agree to charter terms." Or, explicitly, the opposite.
4. Model the "commercial entity captures the ecosystem" risk as its own kill criterion in §7. This is already named in the `rules/independence.md` file but is not called out in the thesis doc's kill criteria.
5. Provide concrete comparable structures. "Blender Foundation" or "Signal Foundation" are the closest plausible analogs; name them and explain the funding difference.

---

## F-04 — HIGH — Boundary Conversation 15-minute onboarding cost is incompatible with "<10 minutes mobile install-to-first-value" Phase 02 exit criterion

**Attack vector:** ROADMAP Phase 02 exit criterion includes "a non-technical user completes install-to-first-value in <10 minutes on their phone." §5.1 says the Boundary Conversation is 15 minutes. §8 (Test-1) says onboarding **cannot** produce an EnvelopeConfig without Boundary Conversation or imported template. These are directly contradictory.

**Why it works:** Installing Envoy, picking a runtime, picking a model, signing up for any third-party required (model API keys), pairing a phone, running a 15-minute Boundary Conversation, doing the Shamir 3-of-5 paper-shard ritual (print 5 cards per ADR-0003, distribute 3 to safes, 2 to trusted humans), and receiving first value — is physically incompatible with a 10-minute wall-clock budget.

The doc partially addresses this ("Users may import a reputable Foundation-Verified envelope with one command") but:

1. Template import bypasses the 15-minute conversation that the entire thesis (§2.4, §8 Test-1) says is the product's defining moment. If 80% of users take the shortcut, the Boundary Conversation is the product's mythology, not its actual onboarding.
2. The Shamir ritual cannot be shortcut — it's a crypto requirement. And the paper-shard distribution is a wall-clock event ("walk to the safe, hand a card to your partner"), not a screen event.

Base rate from comparable sovereignty products:

- 1Password onboarding with Emergency Kit printout — well over 10 minutes and users frequently skip the print step.
- MetaMask seed phrase backup — users routinely skip. Adoption survives only because the phrase is optional-to-use-immediately.
- Keybase onboarding with paper key — users drop off at the paper-key step.

Envoy's Shamir 3-of-5 default forces a pre-deployment wall-clock event that has no comparable analogue in any product with >100k users. The closest analogue — hardware-wallet seed phrase — is accepted because the stakes ($10k+ crypto) justify the friction. For an agent that sends your emails, the stakes-to-friction ratio is upside-down.

Compounding: the "15 minutes" figure appears as a virtue in §5.1 and a bug in Phase 02 exit criteria. Neither reconciles. A reader cannot tell if the designers consider 15 minutes feature or defect.

**What the doc would have to do to defend:**

1. Pick: Boundary Conversation is 15 minutes OR install-to-first-value is <10 minutes on mobile. Both cannot be true in Phase 02. The doc must choose and update the other.
2. Separate "first value" from "full onboarding." First value could be <10 minutes (import template + one task). Full onboarding (Boundary Conversation + Shamir backup) is a multi-day journey with progressive disclosure. Say so explicitly.
3. Add a non-goal around shortcutting: "Envoy does NOT allow first agent action before Shamir backup is completed OR the user explicitly declines with a signed waiver." Decide one way.
4. Model the "users skip Shamir and lose their vault" failure mode explicitly as its own row in the kill criteria. Data loss for 1% of users is a reputation killer for a product whose whole pitch is sovereignty.

---

## F-05 — HIGH — Sunday 90-second ritual adherence is unfounded; fitness/finance/health base rates are devastating

**Attack vector:** §5.8 (BET-8) claims rituals (Daily Digest 2min, Weekly Posture Review 90sec, Monthly Trust Report 5min) form durable habit. The falsifying evidence threshold is absurdly lenient ("<20% open Daily Digest twice in 7 days"). Base rates from analogous-ritual products are far worse than this.

**Why it works:** Empirical engagement numbers from adjacent products:

- **Fitbit / Apple Watch / Garmin** — 50-70% of purchased wearables are unworn within 6 months (2016 Endeavour Partners study; Mintel 2019 corroborates). Daily engagement from active users is ~30-40% for active-minutes rings.
- **Mint / YNAB** — weekly engagement with budget review by active users is 15-25% (YNAB's own published numbers from 2019). The "Sunday morning coffee with budget" ritual this doc imagines is the YNAB founders' positioning — it does not reflect user behavior.
- **Headspace / Calm** — meditation-app 30-day retention is 5-10% per Sensor Tower 2023. The 90-second Weekly Posture Review is shorter than a meditation session and operates on a less-viscerally-rewarding loop (checking an audit log, vs. feeling calm).
- **Password managers (1Password/Bitwarden)** — vault health review is a monthly-to-never behavior. Most users interact only when a password fails.
- **Mastodon / Bluesky "Sunday review"** rituals — essentially nonexistent outside power users. The sovereignty cohort is not a ritual cohort; it is a set-and-forget cohort.

The <20% threshold in BET-8 is far higher than any of these products achieve in comparable rituals. If BET-8 is disconfirmed at <20%, most analogous products would show it disconfirmed on day one. If the threshold were set at >40% (a plausible "product is working" line), the Phase 02 evidence would almost certainly be disconfirming and the rituals would need to be scrapped.

The "Sunday 90-second ritual" specifically is the most-likely-to-fail element. It assumes:

1. Users remember Sunday is the ritual day.
2. Users find 90 seconds at a consistent time.
3. The ritual produces enough felt value to survive week 3 (by which point novelty is gone).

Base rate for "Sunday morning weekly reviews" in self-improvement productivity apps (Notion templates, Todoist reviews, OmniFocus reviews) is in the single-digit-percent range for sustained use past 90 days.

Compounding: §7 kill criterion #1 is "18 months post-Phase-01 with <1,000 weekly-active users." If rituals don't form, the product becomes "audit log with a chat interface" (the doc's own language), which doesn't serve 1,000 WAU for a product this costly to operate.

**What the doc would have to do to defend:**

1. Raise the BET-8 threshold to something that would actually kill the bet. "<40% of active users engage with Weekly Posture Review after 30 days" is closer to a real signal.
2. Add base-rate research as explicit references — cite Mint/Fitbit/Headspace numbers and either defend why Envoy will be different or accept lower thresholds.
3. Add a new non-goal: "If Daily Digest engagement is below X% in Phase 02 evaluation, rituals are event-driven only" — bake the CF-8 counterfactual into the Phase 02 exit criteria.
4. Name what makes Envoy's rituals structurally different from Fitbit's — the only plausible answer is "actions with real consequences (money, email, access) are time-gated through the ritual." If that's the answer, the design should show it; §5.4-5.6 in the superior-product brief do not show it.

---

## F-06 — HIGH — "MY keys, MY infra" cohort is far smaller than doc assumes; sovereignty base rates are brutal

**Attack vector:** §5.3 (BET-3) claims "sovereignty is a durable emotional moat" and asserts the cohort that values it is "large enough to support a Foundation-scale product." Base rates from comparable sovereignty products indicate this cohort is 3-4 orders of magnitude smaller than mainstream consumer products.

**Why it works:** Hard numbers:

- **Gmail to ProtonMail migration** — ProtonMail reports ~100M accounts (2024). Gmail has ~2B users. ProtonMail's active-paid user base is reportedly ~2M. Sovereignty-willing cohort: ~0.1% of email users.
- **iCloud to Nextcloud** — Nextcloud claims ~20M users (self-hosted and provider-hosted combined). Apple iCloud has ~1B users. Nextcloud cohort: ~2% at best, and the overwhelming majority of that is corporate/institutional, not individual.
- **WhatsApp to Signal** — Signal had a 2021 "great exodus" moment and peaked at ~40M MAU; WhatsApp has ~2B. Sovereignty cohort: ~2%. Much of Signal adoption is not sovereignty-driven (journalists, activists) and would not translate to an AI agent product.
- **Mastodon** — ~1.5M MAU at peak; X/Twitter had ~500M. Sovereignty cohort: ~0.3%.
- **Self-hosted password managers (Bitwarden self-hosted vs. Bitwarden cloud)** — Bitwarden Enterprise's own published numbers show >95% of Bitwarden users take the cloud-hosted path despite self-hosted being free. The "I want to run my own infra" cohort inside the "I care about security" cohort is ~5%.
- **PGP adoption** (the historical peak of personal-crypto sovereignty) — <0.1% of email users ever used PGP; Google's 2022 End-to-End Encrypted Email study showed the non-adoption root cause was "workflow friction," not "I don't value privacy."

The doc frames BET-3's falsifying evidence as "install survey shows <30% of users cite sovereignty reasons." This is testing inside an already-selected cohort (people who installed a sovereignty-branded product). A healthier question is: how many people in the TAM of "I want an autonomous AI agent" care about sovereignty enough to accept the ceremony? Base rate says 0.5-2%.

For a product that needs >1,000 WAU in 18 months (§7 kill criterion), a cohort of 2% of autonomous-AI-curious users is probably large enough to hit 1,000. But §3.1 Phase 05 is "enterprise credibility" — and 2% of the autonomous-AI-curious market is not a path into the enterprise. Enterprise IT has already decided cloud convenience beats sovereignty. Envoy is positioning for a cohort that is niche on the consumer side AND structurally unwelcome on the enterprise side.

Compounding: §5.5 (BET-5) asserts prosumer-first lands in enterprise (the Slack/Figma/Notion playbook). Those products were NOT sovereignty plays. Slack was cloud-hosted SaaS; Figma was cloud-hosted SaaS; Notion was cloud-hosted SaaS. The playbook they ran works for convenience-first products, not for sovereignty-first products. Using the Slack playbook with a ProtonMail cohort is a category error.

**What the doc would have to do to defend:**

1. Cite the base-rate numbers and explain why Envoy is different. "Autonomous AI raises the stakes of trust so the 2% grows to 10%" is a claim that can be tested; the doc asserts it but does not show the mechanism.
2. Revise §5.5 — the Slack/Figma/Notion analogy is wrong for a sovereignty product. Name a better analogue (Proton, Bitwarden, Obsidian) or abandon the enterprise-landing narrative.
3. Add a new non-goal: "Envoy does NOT target the convenience cohort. The TAM is the sovereignty cohort, which is <2% of the mainstream market."
4. Revise §7 kill criterion #1. 1,000 WAU at 18 months for a sovereignty product is a low bar; the interesting question is "1,000 WAU at 24 months, 10,000 WAU at 36 months." If those don't happen, the thesis is wrong, not underperforming.

---

## F-07 — HIGH — Household-adversarial case explicitly out of threat model but guaranteed to appear in reality

**Attack vector:** §4.1 item 11 declares "Envoy is not suitable for adversarial multi-tenant use" and explicitly scopes out the case of "one user attempting to compromise another." But the Shared Household primitive (Phase 03, §3.1) is a cooperative multi-principal flow — families. Families become adversarial (divorce, teen-parent conflict, elder-abuse, domestic violence). The doc has no answer when the cooperative assumption breaks.

**Why it works:** Concretely:

- A divorcing couple. Both hold Genesis Records; one holds the Shamir threshold (or holds 3 of 5 shards in the family safe); the departing spouse has a posture they cannot revoke alone. What happens? The doc has no answer.
- A teenager with a restrictive envelope who discovers they can regenerate Genesis locally and install a parallel Envoy that doesn't sync. The household's "Envoy" is no longer canonical.
- Domestic violence: a partner who controls the physical safe controls 3 of 5 Shamir shards and can lock the other partner out of their own ledger, email grants, budget.
- Elder-abuse: a caretaker granted power of attorney "as a principal" in a Shared Household cannot be revoked by the elder who no longer has phone access — but the caretaker can revoke the elder's principal.
- Teen rebellion: teen's envelope is restrictive; teen convinces parent (or spoofs parent's channel identity via an injection attack on a shared phone number) to grant out-of-envelope.

These scenarios are not edge cases in a household primitive. They are the **statistical norm over the 10-year life of a household deployment** — divorce rates in the US are ~40-50%; domestic abuse affects ~10M adults/year; elder abuse affects ~1 in 10 Americans over 60.

A product that ships a Shared Household primitive with a threat model that excludes the adversarial-household case is a product that will have a CVE-class incident within 12 months of Phase 03 ship. The harm shape is particularly bad because the audit trail — the Envoy Ledger — will record the abuser's actions as a legitimate household principal, and the product's marketing says "every action is signed, traceable to a named human." The victim then has to either prove the attacker impersonated them (hard — the Genesis Record is valid) or accept that they are on the hook for the attacker's actions.

The doc in §4.1 item 11 handles this by declaring it out of scope. That is not a safe disposition for a product that will be handed to families.

**What the doc would have to do to defend:**

1. Either (a) scope Shared Household out of Phase 03 entirely and wait for a proper threat model, or (b) explicitly name the household-adversarial threat class as in-scope for doc 09 and describe the mitigations.
2. Name specific mitigations: time-delayed revocation so a compromised principal cannot lock others out instantly; geographic/device-binding for Shamir shards; a "flee mode" for DV scenarios where one principal can exit the household and take their envelope/ledger with them.
3. Add new non-goals: "Envoy does NOT ship a Shared Household primitive without legal review for abuse-domain scenarios (family court, DV, elder protective services)." This is real legal-liability scope for a Foundation operating in multiple jurisdictions.
4. Consult abuse-survivors' technical advisory groups before Phase 03. Signal has done this work (Signal Abuse Team publication, 2021) — Envoy has not mentioned it.

---

## F-08 — HIGH — Temporal constraint dimension is trivially bypassed by device clock manipulation

**Attack vector:** The Envelope has a Temporal constraint dimension ("no actions after 7pm" per superior-product brief §5.1 example; `rules/terrene-naming.md` lists Temporal as one of the 5 canonical dimensions). An attacker who can set the device clock (which includes: an attacker with physical device access, malware with time-zone permissions, NTP poisoning, or a dual-booted OS that lies about time) bypasses the entire dimension.

**Why it works:** The doc doesn't mention clock trust anywhere. For temporal enforcement to be meaningful, at least one of:

- A remote trusted time source (defeats "no phones home" per §4.1 item 7)
- A TPM / Secure Enclave signed clock (device-specific, complex)
- A ledger-based monotonic time ("the last action was at T; any action before T+dt is rejected") — limits attack but not prevents

Concrete attack:

1. User declares envelope: "no banking actions after 9pm."
2. Attacker (or the user acting against themselves in a moment of weakness) sets device clock to 2pm.
3. Envoy hot-path check: `current_time() < 21:00` → true.
4. Action executes; Ledger records it at (spoofed) timestamp 2pm.
5. Ledger integrity doesn't detect this — the hash chain is over the signed entries, which include the spoofed timestamp.
6. Subsequent entries with correct timestamps create a non-monotonic chain; this is detectable but not preventable, and the action has already happened.

The attack isn't theoretical. "Time-gated self-control" is a common user desire (gambling apps, social media apps) and there is a substantial prior-art of users setting their device clock to bypass self-imposed limits. The doc's design puts the user in the adversary role against themselves, which the crypto cannot solve.

More aggressively: an abusive household principal with physical device access sets the clock, performs actions the envelope forbids, sets it back. Combined with F-07.

Compounding: BET-2 says "governance compiles to performance." The performance argument depends on all envelope checks being O(1) hash lookups. Adding a monotonic-clock check or a remote-anchor check raises complexity and latency.

**What the doc would have to do to defend:**

1. Explicitly scope clock trust into doc 09 (threat model). Name the threat and name the mitigation.
2. Add a non-goal if it cannot be solved: "Envoy does NOT enforce Temporal constraints against an attacker with device-clock access." This admission limits the claim to "Temporal constraints are an intent-documentation feature, not a security feature."
3. Require monotonic-time invariant in the Ledger spec — "every entry's timestamp MUST be >= max(parent.timestamp, wall-clock) OR the entry is rejected at write time." This is a cheap mitigation that at least limits the attack.
4. Note the tension with §4.1 item 7 (no phones home) explicitly — the most robust mitigation (remote time anchor) violates the "no telemetry" posture.

---

## F-09 — HIGH — Envoy Ledger scale is hand-waved; 10-year retention has no operational model

**Attack vector:** An Envoy Ledger is a hash-chained append-only record of every grant, action, refusal, and posture change. An active user performs ~100 agent actions per day (plausible for a user whose agent handles email drafts, scheduling, research). Over a year that's ~40k entries. Over 10 years, ~400k entries. The doc does not model storage, indexing, query, export, or backup implications.

**Why it works:** Operational questions the doc doesn't answer:

1. **Query.** "Show me every action Envoy took on my email between March and April 2028." Hash chain is append-only and not-by-default-indexed. Full-scan over 400k entries at 1KB each = 400MB scan. On mobile (Phase 02+), this is a multi-second UX event.
2. **Export.** Monthly Trust Report (§5.6 superior-product brief) requires summarizing 3-12k entries into a one-pager. Mobile Flutter doing this sync? Async? Export-to-PDF pipeline is unspecified.
3. **Verify.** Hash chain verification over 400k entries is fast (seconds) but not instantaneous, and on mobile it's battery-expensive.
4. **Backup.** The ledger file doubles in size every year. Shamir-recovered Trust Vault is specified at ADR-0003; the ledger itself is not covered by Shamir (Shamir is for keys, not for 400MB of ledger data). Is the ledger in sync? If yes, sync bandwidth is a concern. If no, ledger is stuck on one device.
5. **Pruning.** A 10-year ledger may contain PII (emails drafted 8 years ago, health queries). GDPR right-to-be-forgotten on a hash chain is architecturally difficult — removing an entry breaks the chain. Is there a soft-delete with merkle-proof-of-deletion? Unspecified.
6. **Multi-principal (Shared Household).** Every principal writes to the same ledger? Separate ledgers per principal with a cross-chain link? The consent-attribution story in §5.8 (superior-product brief) requires shared reference, but the data model isn't stated.
7. **Channel messages.** Grant Moments include the text of the requested action ("Send email to jamie@work.com"). Over time, the ledger contains a text index of the user's life. Classification policy per `rules/event-payload-classification.md` should redact, but then the Ledger becomes less useful for audit.

Base rate: the SQLite-backed stores mentioned in the kailash-rs survey (§10 data model implications) are fine for low-throughput, but 400k entries with hash-chain verification on every read is a specific performance shape none of the quoted primitives have been stress-tested against.

Compounding: BET-2 claims governance compiles to performance; if the Ledger becomes the bottleneck as it grows, the performance story only holds for month-1 users, not year-5 users.

**What the doc would have to do to defend:**

1. Add a new section (or defer to doc 10 with a specific pointer) on Ledger storage, indexing, pruning, retention policy, cross-device sync bandwidth, and multi-principal data model.
2. Name concrete targets: "Ledger size at 5 years is <500MB; verify latency at 400k entries is <2s on mobile; sync bandwidth is <X MB/day."
3. Handle the GDPR/CCPA right-to-erasure problem explicitly. The solution space is (a) merkle-proof-of-deletion, (b) jurisdictional exclusion ("Envoy is not available in the EU"), or (c) encryption-then-key-destroy. None are no-ops; the doc must pick.
4. Add a non-goal: "Envoy's Ledger is not designed for regulatory-grade retention (finance, healthcare) past 7 years without operator-configured sharding." This is defensible and limits scope.

---

## F-10 — HIGH — §4.1 item 11 ("not a password manager") does not cover the obvious case

§13 open question #2 asks: "does 'Envoy is not a password manager' cover the case where a user wants to paste an API key into a Grant Moment?" The doc flags this. I'll strengthen the flag.

**Attack vector:** When Envoy asks for a Grant Moment to "connect Claude" or "connect Slack" or "connect an MCP server," the user must provide an API key or a token. The user pastes it into the Grant Moment dialog. Where does the token go?

- If into OS keychain per §4.1 item 12 — the keychain is a secret store; the Grant Moment is a signed envelope entry; the linkage is: envelope references a keychain entry by opaque ID. Who holds that opaque ID? Envoy. What happens on Shamir recovery? If the keychain is device-local (macOS Keychain, Windows Credential Manager), the recovered user on a new device has no keychain entry — the Shamir-restore brings back the envelope but not the credentials. The user is locked out of all channels/models.
- If into Envoy's Trust Vault — per §4.1 item 12, Envoy's Trust Vault stores "only Envoy's own keys and envelope state." Putting third-party credentials there violates the stated scope.
- If into neither — the Grant Moment UI asks for a credential, and that credential has to go somewhere.

The doc leaves this ambiguous. The ambiguity becomes security debt at Phase 01 implementation time.

Additionally, the OS-keychain path creates cross-principal exposure in Shared Household (Phase 03) — macOS Keychain is user-level, so two principals on one Mac either share credentials (bad — breaks principal isolation) or cannot cross-sign household actions that require a shared credential (e.g. a shared Slack workspace bot token).

**What the doc would have to do to defend:**

1. Explicitly resolve §13 open question #2 in the thesis doc. Add a section to §4.1 or a new sub-section of §3 that names the credential-storage boundary.
2. Add a data model: "Envoy Trust Vault stores Envoy's own keys; Envoy Connection Vault (distinct primitive) stores third-party tokens using OS keychain on desktop and Secure Enclave on mobile; Shamir covers the Trust Vault and the Connection Vault separately or together per an explicit sub-ADR."
3. Handle the multi-principal case: in Shared Household, the Connection Vault is per-principal, not per-device. This requires Envoy to bring its own credential store rather than the OS keychain.
4. Add a non-goal: "Envoy does NOT share credentials across principals in a Shared Household; shared-access capabilities require each principal to have granted the credential independently."

---

## F-11 — HIGH — "Byte-identical parity" is technically ambiguous and probably unachievable across two LLM-composing runtimes

**Attack vector:** §5.6 (BET-6) and ADR-0001 assert "byte-identical parity" between `kailash-rs-bindings` and `kailash-py`. The doc's falsification threshold is "Phase 02 conformance vectors reveal >20 semantic divergences." But byte-identity across two runtimes that compose nondeterministic components (LLMs, timing, floating-point, async scheduling, third-party HTTP libraries) is a different problem than the doc thinks it is.

**Why it works:** What can be byte-identical:

- Signing, hashing, canonical serialization. EATP D6 is already verified per the kailash-rs survey.
- Envelope compilation output — if the input EnvelopeConfig is structurally identical and the compiler is pure.
- Ledger hash chain over a canonical event stream.

What cannot be byte-identical:

- LLM output. Two LLM providers never byte-match even with temperature=0 because token sampling has rounding-level differences. The Boundary Conversation agent is LLM-backed (per §5.1 of the superior-product brief). Its outputs are not byte-identical between runtimes.
- Any component that does network I/O. HTTP library differences, header ordering, TLS cipher selection — runtime-specific.
- Async scheduling. Rust Tokio's scheduler is not Python's asyncio scheduler. Any ordering-sensitive behavior diverges.
- Wall-clock measurements. Even if the LLM is deterministic, timing metadata (response latency fields in Ledger entries) differs.

The conformance-vector story is strong for spec-driven contracts (per the kailash-rs survey: "EATP D6 canonical verified; PACT N1-N6 tests pass"). But Envoy is not primarily a spec-contract product — it's an LLM-composing product wrapped around those contracts. The kailash-rs survey explicitly says "Python ahead on AI agent ergonomics" — i.e. the Python Kaizen agents are more complete. If the Rust binding later catches up, the LLM composition path will have **different implementations**, not byte-identical ones.

A reader who takes "byte-identical" literally will be disappointed at Phase 02 conformance time. A reader who takes it figuratively cannot evaluate BET-6's falsification: is 20 "semantic divergences" a hard threshold, or does it allow infinite LLM-output divergence and only count spec-contract divergences?

The doc implicitly conflates two claims:

- **Contract parity** — the Genesis Record, Delegation Record, envelope, and ledger formats are byte-identical across runtimes. Strong, achievable.
- **Behavioral parity** — given the same user input, both runtimes produce the same output. Unachievable for LLM-composing paths.

**What the doc would have to do to defend:**

1. Distinguish the two claim types. "Contract parity byte-identical" is defensible; "behavioral parity byte-identical" is not.
2. Add a new non-goal: "Envoy does NOT claim byte-identical behavioral parity across runtimes for LLM-composed paths. Contract-surface parity (ledger, envelope, delegation records) is byte-identical; LLM-composed paths are semantically equivalent."
3. Redefine BET-6's falsification: "Phase 02 conformance vectors reveal >N contract-surface divergences" (not behavioral).
4. Acknowledge that the Kaizen gap (per kailash-rs survey) means the Python-ahead agents will diverge from the Rust-binding-stub agents until BINDING-AUDIT B1/B3 close. Contract parity might hold; behavioral parity will not.

---

## F-12 — HIGH — Legal counsel blocking probability is understated in ADR-0009

**Attack vector:** §5.10 (BET-10) and ROADMAP Phase 00 both treat the 7 ADR-0009 legal items as "engage counsel, resolve, proceed." The actual risk is that counsel BLOCKS one or more items for reasons the engineering team cannot anticipate or engineer around.

**Why it works:** Specific legal blockers that ADR-0009 does not model:

1. **Export control (§5 of ADR-0009).** Rust binary redistribution of Ed25519 + SHA-256 + SLIP-0039 Shamir. The US EAR 734.3(b)(3) open-source exception has been tightened post-2024 for certain crypto. If counsel classifies the Rust binary as a dual-use export, Terrene Foundation (Singapore CLG) has to file a one-time notification with BIS — but the notification requires a product description that pre-commits the crypto surface, and any future crypto-algorithm change re-triggers the filing. This is operational friction that lasts forever, not a one-time cost.

2. **CC BY 4.0 attribution through distribution pipelines (§1-§4 of ADR-0009).** The composite LICENSE file must carry attribution for every Foundation spec incorporated in the product. When Envoy bundles a `SKILL.md` skill at install time, does the bundle carry `SKILL.md` format's license (MIT per README) through the chain? FOSSA/Snyk/Sonatype flag composite license expressions that don't evaluate to a clean SPDX expression. Counsel might require a LICENSE-level declaration that invalidates every CI release pipeline built against a simpler expression.

3. **Foundation charter compatibility (§3 of ADR-0009).** Foundation board has to endorse runtime-pluggability. If one board member opposes on "this enables a commercial fork to become the default" grounds, endorsement is blocked. The doc treats board endorsement as a procedural step; in practice, boards of open-source foundations block things regularly (Apache Software Foundation's handling of JPA 2.0 in 2013; Eclipse Foundation's charter-compatibility stalls on Jakarta EE).

4. **Trademark (§6 of ADR-0009).** Trademark sweep can fail. "Envoy" collides with CNCF Envoy Proxy (the doc acknowledges this). "Envoy Agent" / "Envoy AI" are on the trademark-available list as of 2026-04-21 but the USPTO examiner has discretion; Section 2(d) likelihood-of-confusion rejection on "Envoy Agent" vs a registered "Envoy" mark is plausible. Rebranding is expensive and cascades into namespace reservation.

5. **SPDX scanner false-positives (§2 of ADR-0009).** FOSSA/Snyk/Sonatype have their own composite-expression parsers. `Apache-2.0 AND LicenseRef-kailash-rs-bindings-binary` might read cleanly in one scanner and flag in another. Enterprise customers use whichever scanner their security team uses. Making every scanner happy requires iterative testing the Foundation cannot fully predict in advance.

6. **Dual-license Shamir library.** SLIP-0039 libraries in Rust (`sharks`, `vsss-rs`) are Apache 2.0 but `shamirs` is MIT. The Python `python-shamir-mnemonic` is CC0. Mixing into one binary requires license-compatibility analysis; CC0 is compatible with Apache but some counsel block CC0 over liability waiver concerns.

7. **User-facing disclosure (§4 of ADR-0009).** The installer has to name the closed-binary component and the open-source alternative. If the disclosure text is long (which it probably needs to be for legal-defensibility), it becomes a UX friction point — and the "install in under 10 minutes" Phase 02 criterion degrades.

The doc's mitigation path for BET-10 ("minor: re-license the friction point; major: drop the problematic layer") treats these as engineering toggles. In practice, they're lawyer-gated with multi-week turnaround and no guarantee of success.

Compounding: Phase 00 exit is gated on these items. If even one blocks, Phase 01 is delayed indefinitely.

**What the doc would have to do to defend:**

1. Name the most-likely-to-block items explicitly as Phase 00 risks (not just items to resolve). Export control and trademark are the top two.
2. Add an explicit "parked" mode to §7 kill criterion #5 — "if a legal item cannot be resolved within N months, Phase 00 closes with the item parked and disclosed, and the affected capability (e.g. Shamir-from-day-1 per ADR-0003) is deferred to a post-legal Phase." Rather than killing the thesis.
3. Pre-engage counsel. The doc should name that counsel has been retained / the Foundation has a lawyer on retainer; "will engage counsel" at Phase 00 is a Phase 00-extending blocker if counsel is not already lined up.
4. Add a non-goal: "Envoy does NOT distribute crypto code from a jurisdiction that triggers ITAR (US-based contributors writing crypto that wouldn't otherwise need notification)." The Singapore CLG base is a legal asset IF the contributor base is also outside US crypto-export jurisdiction — if the contributor base is US-based, Singapore status doesn't help.

---

## F-13 — HIGH — Go-to-market has no distribution engine; prosumer-first playbook fails without commercial capital

**Attack vector:** §5.5 (BET-5) asserts "prosumer-first lands in enterprise" per the Slack/Figma/Notion playbook. Every product in that playbook had a commercial entity with VC capital doing the distribution work: Slack's ground game (viral growth + targeted outbound); Figma's designer-community investment; Notion's template-creator ecosystem subsidies. Envoy has a Foundation (non-commercial) and volunteer contributors.

**Why it works:** The prosumer-to-enterprise motion requires:

1. **Acquisition surface.** Paid ads, conference sponsorships, content marketing, influencer partnerships. Slack spent $30M+/yr on marketing in its scaling years. Figma spent aggressively on the design-community. None of these are Foundation-compatible spends.
2. **Onboarding optimization.** Dedicated DX team, onboarding-funnel analysis, A/B testing of first-run. This is continuous engineering investment that volunteer contributors rarely sustain. Mastodon's onboarding is an infamous failure — no ad budget and no dedicated DX team meant first-run has been bad for 6+ years.
3. **Team-to-enterprise pipeline.** Inside sales motion to turn organic adoption into enterprise deals. Slack built a 200-person sales team to pull this off. Envoy has nobody.
4. **Enterprise POC infrastructure.** Free-for-small-team motions to get traction. Envoy cannot do "free for 10 users, paid for 11+" because §4.1 item 5 forbids commercial offerings.

Base rate for Foundation-stewarded products reaching enterprise traction WITHOUT a commercial partner: essentially zero at the stated scale. Mastodon has not landed in enterprise. Nextcloud has but only through Nextcloud GmbH (the commercial entity). Jitsi has but only through 8x8 (commercial acquisition). WireGuard has through wider adoption, but the crypto primitives are what landed, not a user-facing product.

The doc half-acknowledges this (BET-4 mitigation path "major" anticipates a third-party commercial ecosystem). But it doesn't say how that ecosystem is seeded. Commercial entities don't voluntarily build managed-offerings around a Foundation project unless:

- The Foundation already has traction (chicken-and-egg).
- There's a clear revenue model (Envoy's user base is prosumers who expect free, not enterprises who pay for managed).
- The commercial entity has an existing relationship (Red Hat for Kubernetes; Canonical for Ubuntu).

For Envoy, none of these are present pre-Phase-02.

The Phase 05 "enterprise credibility" gate at month-9 post-Phase-01 is optimistic. Salesforce took ~5 years to reach comparable enterprise credibility after being founded; Slack took ~3 years with full commercial motion. For a Foundation product, the realistic number is 5-10 years, not 9 months.

**What the doc would have to do to defend:**

1. Name the distribution engine explicitly. Who does outbound? Who writes content? Who runs conferences? "The Foundation" is not a distribution engine; it's a legal entity.
2. Explicitly permit (or forbid) commercial service-providers to brand themselves on Envoy. §4.1 item 5 forbids Foundation-operated commercial, but the boundary for third-party commercial offerings is unclear. If third parties can operate managed Envoy offerings, what's the trademark license? Revenue share? Attribution?
3. Lower Phase 05 expectations. Month-9 post-Phase-01 for SOC2 Type 1 is achievable for a well-funded commercial entity; for a Foundation with no commercial partner it's 3+ years at best.
4. Add a new non-goal if the Foundation is not going to do distribution: "Envoy does NOT target enterprise adoption in Phase 05; enterprise is a third-party service-provider motion, and the Foundation does not invest in enterprise compliance beyond SOC2 readiness."

---

## F-14 — HIGH — Governance products that try to be the primary surface have a long graveyard the doc does not study

**Attack vector:** §2.3 declares "governance is the primary surface of the product." History of products that tried this as their consumer pitch is not empty — and it's uniformly bleak.

**Why it works:** Prior-art graveyard:

1. **Ghostery / Disconnect / DuckDuckGo Privacy Essentials** (browser-surface governance). DuckDuckGo survived but as a search engine, not a governance product — the governance UI is invisible. Ghostery and Disconnect are niche.
2. **Tripwire / OSSEC / wazuh** (host-based governance, consumer tier). Adoption outside enterprise is negligible.
3. **Little Snitch / LuLu** (macOS firewall with per-app governance). Pro-user tool with sub-1% Mac user adoption despite 15 years of availability. Every new user must pass through "I approve networking for every app I launch" which is exactly the Grant-Moment friction Envoy proposes.
4. **Apple App Permissions** (iOS 14+ per-app tracking prompts). Users largely decline everything, which was the intent, BUT: Apple had to force the permission prompt via OS-level gating. It could not be a user-chosen product.
5. **Chrome extensions for ad/tracker blocking** — huge adoption (uBlock Origin), BUT governance is invisible by default — the user doesn't approve each request, the blocklist does. This is the opposite of Envoy's Grant Moment.
6. **Google Account Security Dashboard** — buried, under-used, ignored. Users only visit when forced.
7. **ChatGPT's custom-instructions** — users mostly ignore.
8. **Claude.ai's model behavior settings** — users mostly ignore.
9. **Slack's advanced admin panel** — used only by admins, never by prosumers.

The pattern: governance is either invisible-by-default (adblockers) or niche-power-user (Little Snitch). Products that make governance the primary conscious surface do not break into mainstream.

The doc at §2.3 acknowledges this implicitly — "Most 'AI safety' products treat governance as an additive layer" — and claims Envoy inverts this successfully. The inversion hypothesis is unsupported by prior art. The burden of proof is on the doc.

One adjacent positive case: **1Password and Bitwarden**. These are governance-shaped (you approve every credential use) but: users quickly toggle on "remember password for this site" / "auto-fill" to minimize the governance surface. The mental model is "governance once, then automation forever." Envoy's Grant Moments default-deny approach is the opposite — governance every time.

Compounding: the "governance is the source of performance" pillar depends on governance being a deliberate, compiled artifact. Products that make governance invisible optimize it away; products that keep it visible pay the friction cost forever.

**What the doc would have to do to defend:**

1. Study the prior-art graveyard in a new section. Name Little Snitch, DuckDuckGo, AdBlock, iOS App Tracking Transparency, 1Password's "remember" toggle. Explain what Envoy does differently.
2. Add a new bet (BET-12 — governance-primary-surface palatability): "Users accept a product whose primary conscious surface is governance, at adoption rates comparable to niche-power-user tools like Little Snitch (~0.5-2% of TAM)."
3. Acknowledge the "remember forever" toggle tension. Envoy's Grant Moments default-deny model will push users toward "grant always" for every capability (as 1Password pushed users toward auto-fill). BET-1 already partially names this but doesn't reckon with what happens when 80% of Grants become "always."
4. Add a non-goal: "Envoy does NOT target the broad consumer market. The governance-primary surface is palatable to the niche-power-user cohort; mainstream users will use a product with governance-invisible defaults."

---

## F-15 — HIGH — Cloud-convenience gravity is not a flat obstacle; it's an accelerating one

**Attack vector:** §5.3 (BET-3) treats cloud-convenience as a static force ("survives the next 3-5 years of the market"). The trajectory of LLM inference pricing and quality is not flat — it's accelerating toward frictionless cloud-consumed intelligence. The sovereignty cohort's relative weight is shrinking, not stable.

**Why it works:** Quantitatively:

- **Inference cost.** GPT-4-class inference was $30/M output tokens at 2023 launch. GPT-4-class-equivalent (GPT-4o, Claude Sonnet, Gemini Flash, DeepSeek) is now $0.30-$1/M. 30-100x improvement in ~2 years. Trajectory points to $0.01-$0.10/M at 5 years.
- **Latency.** First-token-latency improved from ~2s to ~200ms in the same window. Edge-deployed inference (Groq, Cerebras) shows <50ms.
- **Integration.** Siri-with-Apple-Intelligence + Google-Gemini-in-Android + Microsoft-Copilot-in-Windows are shipping OS-level agent primitives. The user doesn't install an agent; the OS is the agent.
- **Memory/persistence.** OpenAI Memory, Claude's project files, Google's contextual memory all ship persistent state that looks a lot like Envoy's Envelope but is managed by the vendor.

The trajectory is: cloud becomes so convenient (OS-integrated, free-at-tier-1, always available) that the marginal cost of "not sovereign" drops below the marginal friction of "sovereign with a 15-minute Boundary Conversation and a Shamir paper-shard ritual."

The doc treats this as a static bet. It should treat it as a moving target where Envoy's window is shrinking with every OS release.

Precedent: **Personal web server / self-hosted email / self-hosted photo storage.** The sovereignty-willing cohort is smaller at each iteration of the product generation because cloud convenience compounds. Self-hosted email ownership per Email Geeks/DeliverabilityMatter data has dropped from ~5% in 2010 to ~0.5% in 2024 as Gmail anti-spam reputation systems made self-hosted delivery nearly unviable (SPF, DKIM, DMARC issues). Self-hosted AI agents face a comparable tightening as cloud-hosted agents get OS integration that self-hosted cannot match.

BET-3's kill criterion is "<30% of users cite sovereignty reasons." By the time the cloud-convenience gravity is fully expressed (2028-2030), the serviceable market for sovereignty-first AI agents may be so small that <30% of it gives you 100 WAU, not 1,000.

**What the doc would have to do to defend:**

1. Model cloud-convenience as a trajectory, not a state. Name concrete checkpoints: "By Phase 03 (~18 months out), if Apple Intelligence is on-device AND integrates with Siri AND has a 'private mode' comparable to Envoy's envelope, the sovereignty moat narrows to users who actively distrust Apple — a cohort of <0.5% of Apple users."
2. Add a falsification for BET-3 that's trajectory-aware: "If OS-integrated agent products (Apple Intelligence, Gemini Assistant, Windows Copilot) ship envelope-equivalent governance within 24 months of Phase 01, the differentiator collapses and Envoy competes on sovereignty-narrative-only, not feature-uniqueness."
3. Add a new non-goal: "Envoy does NOT compete with OS-integrated agent products on convenience. The user must accept extra friction in exchange for sovereignty; the product is the friction that makes sovereignty real."
4. Name the exit ramp: if BET-3 disconfirms on trajectory grounds, Envoy's value prop collapses to "a signed audit log for agent actions" — which has a different market (compliance-adjacent, not sovereignty-adjacent).

---

## F-16 — HIGH — "Every action emits a signed record BEFORE execution" (Test-2 in §8) is structurally incompatible with streaming LLM output

**Attack vector:** §8 Test-2 states: "Every action emits a signed record before execution. Not after. An agent invocation that fails to produce a Delegation Record tied to a Grant Moment or to an already-authorized envelope entry cannot execute. 'Log after the fact' is out-of-spec; the Ledger signs on the pre-action edge."

**Why it works:** LLM tool-use doesn't work that way. In realistic agent flows:

1. User says "summarize my inbox and send a Slack update."
2. LLM begins streaming. Mid-stream it emits a tool-call: `read_email()`.
3. Hot path wants to "sign pre-action" — but the action isn't a well-formed thing yet. It's a tool-call with arguments; whether it's in-envelope depends on which emails are read and who sees the Slack update.
4. LLM streams further, produces another tool-call: `send_slack(channel, body)`.
5. Hot path signs — but the body depends on the read_email result, which the LLM is using as context.

The compilable-envelope pre-authorization model works for hash-set lookups ("is send_slack on the allowed-tools list?") but not for the "body" dimension (what you actually send). The "body" is produced by LLM composition, which is post-hoc relative to the tool-call's existence.

More concretely:

- If Envoy's envelope says "no banking actions" and the LLM emits `http_post(url="https://bank.com/...")`, the pre-action sign happens AFTER the URL is known but BEFORE the POST fires. Fine.
- If the envelope says "no sending emails to people not in my contacts" and the LLM emits `send_email(to="jamie@work.com")`, pre-action check. Fine.
- If the envelope says "cannot share my tax information" and the LLM emits `send_slack(channel, body)` where body contains tax info inferred from context — the pre-action check needs to inspect `body` semantically. That's not an O(1) hash lookup; that's an LLM-on-LLM classification that's latency-expensive and non-deterministic.

BET-2's performance claim depends on pre-action checks being cheap. Test-2's "pre-action sign" assumes checks are well-defined. Semantic envelope checks (data-access, communication) are neither cheap nor well-defined at pre-action time.

Compounding: if the check is too strict ("any send_slack body MUST be semantically classified before send"), the hot path stalls for seconds per LLM invocation. If it's too loose ("send_slack with any body is allowed if send_slack tool is in the envelope"), the Data Access dimension of the envelope is essentially unenforceable and the thesis is downgraded to tool-use gating.

Bigger problem for streaming: if the agent is streaming a response to a user channel (e.g. typing to the user in Telegram), every chunk is effectively an action. Signing each chunk is infeasible. Not signing them means the ledger records "agent sent message to Telegram at time T with content C" but the user sees the streaming output before the content is hash-chained.

**What the doc would have to do to defend:**

1. Name the distinction between structural checks (tool-in-envelope, O(1)) and semantic checks (body-within-envelope, expensive). Pick which ones Test-2 enforces.
2. Add a new non-goal or scope narrowing: "Envoy's pre-action signing is structural; semantic constraints on action bodies are advisory at emit time and enforced post-hoc via audit review." This is a significant scope revision but it's honest.
3. Revise BET-2's falsification: "Pre-action P50 latency > 20ms" is one thing; "pre-action semantic classification P50 latency > 500ms" is a different thing the user will absolutely feel.
4. Handle streaming output explicitly. Either (a) stream is atomic and signed at end (but then user sees pre-signing output), or (b) stream is broken into signed chunks (which creates enormous ledger inflation), or (c) stream is a special action class that is rate-limited rather than signed per-token. Pick.

---

## F-17 — MEDIUM — Envelope import "one command" shortcut undermines Test-1's own structural guarantee

**Attack vector:** §8 Test-1 says "A 'default permissive envelope' is NOT an acceptable shortcut. Users may import a reputable Foundation-Verified envelope with one command; they cannot skip declaration." If users can import an envelope with one command, the "cannot skip declaration" clause is nominally satisfied but structurally toothless.

**Why it works:** Most users will choose the fast path. Base rate for "first-run setup wizard" skipping is 50-80% across consumer products (iOS setup wizard skip rates, Google account setup wizard). Envoy's default path is "import envelope templates from Foundation-Verified library." Users who take this path:

1. Do not go through the Boundary Conversation.
2. Do not experience the "declaring limits felt authoritative" moment the thesis requires (§2.4).
3. Have an envelope that's generic to their persona, not personalized.
4. Have the envelope-set-by-Foundation-not-me state, which §9.4 item 4 says breaks the meta-USP ("credentials for action live anywhere other than on the user's own device" — broader read: "the declarative intent of the envelope lives anywhere other than in the user's own decision").

The doc tries to have both: "Boundary Conversation is the product's personality" (§5.1 superior-product brief) AND "you can skip it with an import." These are in tension. Either:

- Import is an escape hatch that <10% of users take (then the thesis survives), OR
- Import is the common path that 70%+ of users take (then the thesis is cosmetic).

§5.1 (BET-1) explicitly falsifies on "<20% of users complete the Boundary Conversation to envelope-compile state." If imported envelope counts as "envelope-compile state," the bet is unfalsifiable because import is one command. If it doesn't count, the doc should say so.

Compounding: Foundation-Verified envelopes are templates for personas ("freelancer-v1," "solo-founder-v2"). A user who imports one has now handed their felt-agency to the Foundation's authorship. The Foundation becomes the envelope-author-by-default, which is exactly what the meta-USP in §9 says to avoid.

**What the doc would have to do to defend:**

1. Clarify BET-1's falsification. Does an imported envelope count as completing the Boundary Conversation? Pick explicitly.
2. Either add friction to template import ("import template, then complete Boundary Conversation to personalize") or admit template import is the primary path and demote Boundary Conversation to opt-in.
3. Add to §9.4 the "Envoy's primary envelope is set by an entity other than the user" anti-pattern. Template import edges this case; you either accept it with a disclosure or block it.
4. Track import-vs-conversation ratio explicitly in Phase 02 metrics. If imports exceed 50%, trigger CF-1 (re-scope to audit-first).

---

## F-18 — MEDIUM — BET-2's "envelope compiles to O(1)" is under-specified for dynamic input

§5.2 mitigation ("Implementation experience: envelope verification cannot be safely cached across tool invocations because of per-call dynamic inputs — forcing O(k) re-evaluation at each call") names this but doesn't resolve it.

**Attack vector:** The pre-compile-to-hash-set model works for: "is tool X in the allowed-tools set?" It fails for: "is action Y in the Financial dimension ceiling?" — because Y's cost depends on runtime inputs (token count, model selection, etc). Similar for Temporal ("has the 7pm cutoff passed?"), for Data Access ("does this query touch a classified field?"), and for Communication ("is recipient in my allowlist?" — allowlist mutable during a session).

**Why it works:** The compile-to-O(1) model applies to a small subset of envelope checks — static membership in a static allowlist. The other dimensions are runtime-dynamic. The doc's performance claim is therefore quantitative-ish for a structural-check minority and qualitative-vague for a dynamic-check majority.

BET-2 mitigation says "envelope compiler becomes batch-aware" — this is an escape hatch but doesn't explain what batch-aware buys you. A tool invocation inside a scheduled ritual might be batchable; a tool invocation from a user Grant Moment is not batch-aware (user expects sub-second feedback).

The mitigation ends at "Kill condition: If the pure-Python runtime is >500ms P50 on realistic workloads, the cross-runtime parity claim breaks because users cannot meaningfully opt out." A 500ms P50 floor for dynamic checks is plausible. A 500ms floor for every Grant Moment is the kill condition. The doc should be clearer about whether the Grant Moment surface is in-scope for the P50 target.

**What the doc would have to do to defend:**

1. Partition envelope checks by static-vs-dynamic. State the P50 target for each class separately.
2. Name the dynamic-check algorithms. If the Financial dimension involves token counting + model pricing, that's a per-call computation that can be cached but only per-LLM-call. Be specific.
3. Revise the "governance compiles to performance" pillar to distinguish "structural governance is O(1)" from "semantic governance is OLlama(k)-then-cached."
4. Set separate latency budgets per dimension. Financial check: <5ms (arithmetic). Temporal check: <1ms (comparison). Data Access check: <50ms (LLM classification). Communication check: <5ms (set lookup). If total budget exceeds P50 target, the envelope has too many dimensions for the target.

---

## F-19 — MEDIUM — `force_install=True` is a permanent weakness, not an escape hatch

**Attack vector:** ADR-0005 gives users `force_install=True` to bypass CO validator when installing a SKILL.md skill. This is framed as sovereignty-respecting. In practice, it's the path of least resistance for every shared link, every community skill someone imports, every install friction.

**Why it works:** Base rate for "bypass warning" flows:

- **iOS "untrusted developer"** — users routinely take the 5-tap path to enable.
- **Android "install from unknown sources"** — users take it to install APKs.
- **Chrome "advanced → proceed unsafe"** — users routinely take it.
- **npm install --force / pip install --force-reinstall** — routine developer behavior.

Each of these is a deliberate friction point that most users bypass. `force_install=True` is the same pattern — it's a speed-bump that will see routine use.

Consequence: any skill authored to be "ClawHub-compatible but CO-non-compliant" gets distributed with `force_install=True` in the instructions. Users follow the instructions. The CO validator becomes meaningless for the long tail.

BET-7's falsification thresh ("Skill authors respond by gaming the validator or by distributing via `force_install=True`, making the validator theater") names this exact failure mode — but then the mitigation paths are "iterate the validator" or "drop bulk ingest." Neither addresses the actual dynamic: validators that can be bypassed will be bypassed.

Compounding: SKILL.md skills are broadly MIT-licensed per ROADMAP Phase 00. There's no legal enforcement — the community distributes what it distributes. `force_install` is the release valve.

**What the doc would have to do to defend:**

1. Add a non-goal: "Envoy does NOT claim protection against skills installed with `force_install=True`. The flag is sovereignty-respect; it is not a safety feature. Users who use it have waived the product's governance promise for that skill."
2. Name what happens post-force-install. Does the skill execute with the same privileges as a validated skill? If yes, force-install is a full bypass. If not, specify the reduced envelope.
3. Track force-install frequency in Phase 02+ instrumentation. If >30% of skills are force-installed, the validator is theater per BET-7.
4. Require force-installed skills to be visibly flagged in the Ledger, the envelope, and the skill inventory — so the user's future self sees which skills are on trust and which on force.

---

## F-20 — MEDIUM — Glossary rigidity vs. product marketing elasticity is a future conflict

**Attack vector:** §11 mandates canonical vocabulary with no synonyms, no reordering, no redefinition. Marketing copy, first-run UX, help docs, and user interviews will all want to say "boundary" instead of "envelope" sometimes, "permission" instead of "grant" sometimes, "level" instead of "posture" sometimes.

**Why it works:** Product teams routinely conflict with spec teams on terminology. Glossary enforcement breaks the moment a marketer says "boundaries" in a blog post. Per `rules/terrene-naming.md`, these names are canonical across the Foundation, so marketing compliance is both a hard requirement and an enforcement burden.

Compounding: "Envelope" in product-speak collides with "envelope" in email-speak ("I sent the envelope to jamie@"). Users doing the Boundary Conversation about email will encounter "envelope" twice. §11 doesn't address this.

Also: the doc's own title contains "boundaries" ("Autonomous AI where you set the boundaries") but the canonical term is "envelope." "Envelope Conversation" does not scan in marketing. The entire product's external voice uses the non-canonical term for UX reasons. The doc should acknowledge this.

**What the doc would have to do to defend:**

1. Distinguish canonical terms (code, specs, logs) from marketing terms (user-facing copy). Allow "boundary" in user copy as an alias for "envelope" in specs.
2. Add to §11 a "user-facing synonyms" column: envelope → "boundaries" (marketing) → "envelope" (code/spec). This is not a violation of `rules/terrene-naming.md` — that rule is about spec accuracy.
3. Resolve the "envelope" collision with email-envelope semantics. Add a visual distinction in UX (capital-E Envelope vs. lowercase envelope).

---

## F-21 — MEDIUM — Posture 5-level ratchet assumes monotone progression that reality doesn't deliver

**Attack vector:** §5 superior-product brief and §3.2 item 7 describe the posture slider as a "5-level ratchet" with trust deepening over time. Reality of agent failures:

**Why it works:** A ratchet progresses in one direction. Real usage:

- Week 1: PSEUDO (learning).
- Week 2-6: TOOL (comfortable).
- Week 7: agent does something user didn't expect — posture drops back to TOOL or PSEUDO.
- Week 8: user trusts again.
- Week 9: agent does something weird.

This is a sawtooth, not a ratchet. The "ratchet" framing implies trust only goes up. In practice, trust oscillates, often severely, in response to discrete incidents. The doc's positioning of the slider as a "ratchet" over-sells monotone progression.

More fundamentally: the 5-level model assumes posture is a scalar. In practice, users trust agents differently across dimensions — a user might be DELEGATING on email but TOOL on finance. The 5-level slider doesn't capture this. The superior-product brief §5.5 hints at dimension-specific sliders ("raising my email-drafting authority from SUPERVISED to DELEGATING ... lowering my calendar-booking authority back to TOOL") but the spec in the thesis doc is a single slider.

If the posture is single-slider, users will either max out (AUTONOMOUS on everything — dangerous) or under-use (TOOL on everything — unproductive). If it's per-dimension, the UI surface multiplies and the "90-second Sunday ritual" is impossible.

**What the doc would have to do to defend:**

1. Rename from "ratchet" to "slider" and acknowledge bidirectional movement. BET-3 and §5.5 rituals already assume bidirectional — make it canonical.
2. Decide: is posture single-slider or per-dimension? If per-dimension, the data model in doc 10 needs 5-10 sliders (one per constraint dimension × per agent), and rituals scale proportionally.
3. Add a non-goal if it's single-slider: "Envoy does NOT support per-dimension trust postures in Phase 01-03. Posture is whole-agent. Users who want per-dimension trust use multiple agents with distinct envelopes." This is a real scope decision.
4. Model the "posture drop on incident" flow. If agent misbehavior triggers automatic posture drop, the UX is self-correcting. If it requires user intervention, the slider is a leading indicator of disengagement.

---

## F-22 — MEDIUM — Recovery ritual's social graph is a family-secrets exposure

**Attack vector:** ADR-0003 Shamir 3-of-5 default distributes paper shards to "three in safe, two with trusted humans." The "trusted humans" social-graph is an undisclosed Envoy side-channel the doc does not model.

**Why it works:** Concretely:

- User distributes shard to their spouse and their best friend.
- Spouse and best friend now hold evidence that the user has an Envoy install.
- If user has reason to hide that (abusive relationship, investigative journalist with source contacts in Envoy, government employee with OPSEC concerns), shard-holder knowledge becomes an attack surface.
- Trusted humans may have complicated relationships — parents, siblings, employees, exes. Handing them a SLIP-0039 shard is a trust act that reshuffles the user's personal life.
- Trusted humans may die or become unreachable. 5-of-5 is impossible if 2 shards-holders die; 3-of-5 works if you chose the 3 correctly. The social-graph model is "pick 5 people you trust and will stay in contact with for 10+ years." Few users have 5 such people. The alternative (five safes, which the SLIP-0039 5-of-5 option allows) creates single-location risk.

SLIP-0039's design is agnostic about shard-holders. Envoy making "2 with trusted humans" the default implicitly tells users to involve people in their recovery. This is a socialized crypto architecture and it has been the subject of serious criticism in the Bitcoin community (multi-sig custody friction, cascade failure on life events).

**What the doc would have to do to defend:**

1. Allow a "5-of-5 in your own safes" default for users who don't want social involvement. Make the 3-of-5-with-humans a user-chosen option, not the default.
2. Document the social-graph exposure in §9.4 or a new anti-pattern list. Users need to know that shard-holders learn you use Envoy.
3. Add a non-goal: "Envoy does NOT verify the user's chosen shard-holders' identity or continued availability. Shard-holder lifecycle is the user's responsibility. Envoy offers a 'shard rotate' ritual to replace unreachable shard-holders."
4. Handle the "life-changing event" case: marriage, divorce, death, relocation. Shard-holder rotation is a known ritual in enterprise key management; consumer rituals for this don't exist.

---

## F-23 — MEDIUM — "No telemetry" hard rule forecloses essential product-health learning

**Attack vector:** §4.1 item 7 states "Envoy does not phone home. No telemetry. No crash-report pipeline that leaves the device without explicit Grant Moment approval. No install analytics." This is a strong sovereignty statement. It also makes product learning nearly impossible.

**Why it works:** Without telemetry, the doc's own falsification thresholds are unmeasurable:

- BET-1 "<20% of Phase 01 users complete the Boundary Conversation" — how do you know without telemetry? Only active users who self-report.
- BET-8 "<20% of active users open the Daily Digest twice in 7 days" — self-report only.
- BET-3 "install-survey responses show <30% sovereignty reasons" — assumes a survey mechanism. Surveying requires the product to ask, the user to answer, and the answer to go somewhere. That's telemetry.
- Phase 02 "install-to-first-value <10 minutes" — how do you measure? Local timer + user-uploaded? That's still telemetry with extra steps.

The consistent pattern in no-telemetry products:

- **Signal** publishes aggregate user counts via ad-hoc post announcements; detailed funnel is opaque. This is acceptable for Signal because the business model is donations; for Envoy pursuing the Phase 05 enterprise play, lack of metrics is acceptance-blocking.
- **DuckDuckGo** instruments aggregate search query volume per keyword but no user identifiers; still enough to understand product usage at population level.
- **Proton** publishes user counts but nothing deeper.

Envoy's "no phone home" posture is closer to Tarsnap (one-man show, no metrics). That's fine for a one-person project but breaks the "1,000 WAU at 18 months" kill criterion — without telemetry, the WAU count is an estimate, not a number.

The Grant-Moment-approved telemetry escape is stated but not designed. If Envoy asks the user at install "may I send Foundation aggregate usage data?", what's the default? Either default is problematic (default-on undermines sovereignty; default-off produces no data).

**What the doc would have to do to defend:**

1. Resolve the tension. Either: (a) accept local-only metrics that users voluntarily submit (acceptable but produces tiny sample sizes, so kill criteria become unfalsifiable), or (b) design a cryptographically-anonymous aggregate-telemetry channel (a la Apple's ODM data, or DuckDuckGo's query counts), which keeps sovereignty intact but lets the Foundation know the product is working. Pick.
2. If (a), acknowledge in §7 that WAU counts are user-self-reported estimates, not measured.
3. If (b), describe the design in a new ADR. This is non-trivial (Apple ODM is a PhD-scale design problem).
4. Add to §4.1 item 7: "Envoy may transmit a once-per-week aggregate 'weekly heartbeat' containing only a random installation ID and the current Envoy version, if the user opts in at install time. The payload is documented, the endpoint is Foundation-operated, the data retention is N days." — or explicitly decline this.

---

## F-24 — MEDIUM — §3.1 Phase 05 "regulated industries" scope includes SOC2 + HIPAA + GDPR DPIA in one phase — unrealistic

**Attack vector:** ROADMAP Phase 05 bundles SOC2 Type 1 + HIPAA + GDPR DPIA + SSO/SAML/SCIM + Federated Trust Mesh + managed deployment. These are not one phase; each is a multi-quarter project for a funded commercial team.

**Why it works:** Realistic timelines:

- **SOC2 Type 1** — 4-6 months for a funded team with a SOC2 auditor relationship and an existing observability pipeline. For a Foundation-stewarded project without a commercial entity, add 12-18 months for process creation (risk register, vendor management, access reviews that the Foundation doesn't have the organizational structure to perform).
- **HIPAA** — requires BAA (Business Associate Agreement) architecture, PHI handling controls, breach notification readiness. The Foundation as non-medical entity cannot be a BAA party in the usual sense; HIPAA compliance for Envoy means "the user's deployment of Envoy is HIPAA-compliant-if-they-configure-it-right," which is a different product from SOC2.
- **GDPR DPIA** — requires a Data Protection Officer, a documented lawful basis, a right-to-erasure implementation (which Envoy's append-only ledger makes hard per F-09), cross-border data flow docs. Foundation as controller/processor is ambiguous if Envoy is local-first.
- **SSO/SAML/SCIM** — for a consumer product whose thesis is "no registration," SAML/SCIM is a deep contradiction. Enterprise SSO typically binds to a hosted identity; Envoy declares it doesn't have one.

Phase 05's scope as written would be 5-10 years of Foundation work, not a phase. Treating it as "Phase 05" with target "month 9 post-Phase-01" per `ROADMAP.md` is inconsistent with industry timelines.

**What the doc would have to do to defend:**

1. Break Phase 05 into 05a / 05b / 05c with realistic boundaries. SOC2 first (18 months of operational history minimum), HIPAA/GDPR second (conditional on legal structure), Federated Trust Mesh third.
2. Address the SAML/SCIM thesis contradiction. Either Envoy has no hosted identity (stays true to §4.1 item 8) or it ships an optional hosted-identity connector for enterprises.
3. Rename Phase 05 from "regulated industries" to "readiness for regulated industries." A product does not pass regulated-industry review; a deployment does.
4. Add a non-goal: "Envoy does NOT target HIPAA certification until a commercial partner (third-party managed-Envoy operator) can act as BAA party. The Foundation cannot and will not."

---

## F-25 — LOW — §7 kill criterion #4 ("10x our adoption in 12 months") is miscalibrated for a niche product

**Attack vector:** §7 #4 says "A categorically-better alternative emerges that … reaches feature parity and >10× our adoption within a 12-month window" triggers thesis abandonment. For a niche product with, say, 5,000 WAU, 10× is 50,000 WAU. A mainstream AI company launching a "governed agent" feature could hit 50,000 in a week of PR release. The criterion fires trivially.

**Why it works:** The 10× metric is reasonable for mainstream products but wrong for niche products. A niche product's meaningful competitor isn't "higher adoption by a bigger company" — it's "higher adoption WITHIN THE NICHE." Signal (niche, sovereignty-aligned) doesn't consider Telegram an existential threat even though Telegram has ~10× Signal's users.

Compounding: if OpenAI ships "agents with user-specified envelopes" as a ChatGPT feature and gets 500k users in a month, does that trigger §7 #4? If yes, Envoy abandons within a year because OpenAI shipping a feature doesn't invalidate Envoy's sovereignty thesis — it validates it as a structural alternative. The kill criterion as written over-fires.

**What the doc would have to do to defend:**

1. Qualify the "10× adoption" with "in the Envoy TAM (sovereignty cohort)." OpenAI's ChatGPT reaching 500k governed-agent users doesn't invalidate Envoy; it validates the category.
2. Add a "categorically-better alternative" definition: the alternative must also be Foundation-stewarded, non-commercial, local-first, user-owned-keys. Absent those, it's not a substitute product.
3. Lower the multiplier for niche context: 3× within-niche adoption is a meaningful signal.

---

## F-26 — LOW — §12 references list cites `rules/` files that are Foundation infrastructure, not product rules

**Attack vector:** §12 references `rules/terrene-naming.md`, `rules/independence.md`, `rules/autonomous-execution.md`. These are Foundation COC infrastructure, not Envoy product rules. An external reader of the thesis doc follows the link and lands in Foundation engineering process.

**Why it works:** The thesis doc is the single load-bearing artifact for external understanding of Envoy. Linking to `rules/autonomous-execution.md` — which documents the "autonomous AI agents instead of human teams do the work" methodology — is an internal-process fact that will confuse or alienate an external reader who thought they were reading a product thesis.

`rules/autonomous-execution.md` is particularly risky — if a buyer reads "effort is measured in sessions, not human-days" without context, they may read it as "there is no engineering team; an AI writes this code unsupervised," which is either true (scary for an enterprise buyer) or false (then why is it in the thesis references?).

`rules/independence.md` is fine — it's product-boundary information an external reader benefits from.

`rules/terrene-naming.md` is process-internal; an external reader doesn't need it.

**What the doc would have to do to defend:**

1. Remove `rules/autonomous-execution.md` and `rules/terrene-naming.md` from §12. Put them in a "for contributors" sub-list or an internal doc.
2. Add product-external references: Charter, DECISIONS, ROADMAP (already present), plus a "comparable products" section if the doc wants external-reader grounding.
3. If `rules/autonomous-execution.md` must stay, annotate it: "Internal methodology doc; describes how Envoy sessions are estimated."

---

## Cross-cutting patterns

Several findings hint at the same structural weakness:

1. **F-01, F-02, F-04, F-08, F-16** — The doc's claims about Phase 01 feasibility don't reconcile with the doc's own Phase 01 scope. Something gives.
2. **F-03, F-13, F-24** — Foundation-stewardship is named as a virtue but never financed or staffed. Multiple kill-criteria-eligible failure modes downstream.
3. **F-05, F-06, F-14, F-15** — Base-rate evidence across adjacent products is consistently pessimistic for the "governance as consumer surface" and "sovereignty as durable moat" claims. The doc does not engage with the pessimistic base rates.
4. **F-07, F-09, F-22** — The adversarial threat model is under-developed for the household + long-lived ledger + social-key-recovery surface. Doc 09 has a lot to carry.
5. **F-10, F-17, F-19, F-21** — Several user-facing design decisions (template import, force_install, posture slider) have escape hatches that partially undermine the thesis. Each individually is ~LOW; collectively they erode BET-1 significantly.

## Suggested document-level responses

1. **Add a section:** "Evidence grounding" — cite base rates for fitness-app ritual adherence, sovereignty-product adoption, password-manager governance patterns. The thesis doc asserts many user-behavior claims; it should engage with the evidence.
2. **Add a bet:** BET-11 — financial viability of Foundation stewardship.
3. **Add a bet:** BET-12 — governance-primary-surface palatability.
4. **Re-scope BET-9 to Phase 00:** The Kailash primitives sufficiency question is already answered by the survey; the doc should read its own workspace.
5. **Resolve §9.4 / Phase 01 contradiction:** Either promote a channel to Phase 01 or narrow §9.4's anti-pattern.
6. **Fix Phase 05 timeline:** Break the bundle; set realistic timelines per regulation; name what a Foundation-vs-commercial-partner split looks like.
7. **Doc 09 (threat model) must carry:** Clock trust (F-08), household-adversarial (F-07), ledger retention/erasure (F-09), shard-holder social graph (F-22), streaming LLM pre-sign (F-16), semantic envelope checks (F-18).

**End of Round 1 adversarial review.** 26 findings, ready for author response or convergence protocol.
