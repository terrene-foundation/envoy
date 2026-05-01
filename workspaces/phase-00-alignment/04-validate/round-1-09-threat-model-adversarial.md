# Round 1 — Adversarial review of 09-threat-model.md

**Reviewer role:** Skeptical security auditor. The goal is to identify threats the model misses, mitigations that don't work, residual risks under-declared, and boundaries drawn at the wrong place. Where the doc's thesis depends on "the envelope + Ledger architecture cannot be bypassed," findings identify the bypasses.

**Date:** 2026-04-21
**Scope:** `workspaces/phase-00-alignment/01-analysis/09-threat-model.md` (draft v1, 23 enumerated threats T-001..T-090)
**Cross-read:** doc 00 thesis (v2), doc 03 primitive reconciliation, internal kailash-rs survey.

**Verdict:** The threat model is credible on STRIDE + crypto, but **under-enumerates agent-specific threats** (chain-of-thought, goal drift, sub-agents, multi-turn context), **structurally mis-scopes thesis-critical threats** (Authorship Score gaming, UX habituation, delegation-upward via copy-paste), and **omits a whole category of Foundation-infrastructure threats** (Sybil attacks on reputation, Envelope Library DoS, covert-channel in Heartbeat payload). Several "mitigations" are load-bearing primitives without a concrete mechanism (first-time-action gate, envelope linter) — they need to be specified before they can be called mitigations.

**Finding density:** 31 findings. 3 CRITICAL, 11 HIGH, 11 MEDIUM, 6 LOW.

---

## CRITICAL (thesis-bypassing; no current mitigation)

### C-1. Sub-agent posture-claim forgery is structurally un-modeled

**Attack vector:** An agent at DELEGATING posture spawns a sub-agent and the sub-agent asserts a different (weaker-to-the-user, stronger-to-the-envelope) Trust Posture in its delegation record.

**Why it works:** The threat model has no entry for sub-agent spawning. Doc 00 and doc 09 assume a single agent-loop per principal. In production (Kaizen multi-agent orchestration, `MultiAgentOrchestrator`, `A2AProtocol`), an agent will fan out to sub-agents to complete tasks. Every sub-agent is itself an `Agent` with its own envelope + posture. The delegation record from parent-agent to sub-agent MUST inherit the parent's envelope (strict tightening, EATP monotonicity). But nothing in the threat model requires a sub-agent to **prove its envelope was derived**; a jailbroken parent agent can simply forge a delegation record (the parent's key signs everything) with a loosened scope. The cascade-revocation test verifies parent→sub revocation, but does not verify scope monotonicity at spawn time. Worse: if the sub-agent runs in a different trust zone (different process, different LLM provider), the sub-agent's visible tool-calls are the ones logged — the sub-agent's _internal reasoning_ (chain-of-thought that decides which tool to call) never touches the Ledger. Combined with prompt injection through tool output (T-011), a sub-agent is the cleanest envelope-bypass vector in the system.

**What doc would add:** New threat T-100: "Sub-agent envelope-scope forgery." Mitigation: (a) every sub-agent delegation record MUST be signed with parent's key AND contain a cryptographic proof that `child.envelope ⊆ parent.envelope` (implementable via canonical envelope-intersection recomputation + signature over the hash); (b) sub-agent's tool-calls are recorded against **parent's** posture, not child's claimed posture, until the delegation record is verified; (c) a test `tests/threat/subagent_envelope/` that tries to smuggle loosened scope via spawn. Note: kailash-rs `EatpDelegationChain.verify()` DOES enforce constraint tightening monotonicity in Rust — but the Python binding (ISS-28, ISS-25 in doc 03) is stubbed. This threat is **actively live** in Phase 01 if Envoy composes A2A via the broken binding path without an Envoy-side reverify.

---

### C-2. Chain-of-thought never reaches the Ledger; visible tool-calls are not the complete authorship surface

**Attack vector:** An LLM under prompt injection emits a visible tool-call sequence that is structurally legitimate (passes envelope, passes Grant Moment patterns) but whose purpose is set by adversarial chain-of-thought the user never sees.

**Why it works:** The thesis (§2.2 of doc 00) says "every action is signed and traceable." The Ledger records tool-calls (`ToolCallIntent`, `ToolCallResult`) and text messages. It does NOT record the LLM's internal reasoning. But the LLM's reasoning is what decides _which_ of the allowed actions to take, _when_, and _with what arguments_. If the LLM is subtly biased by a compromised provider (T-030) or by a persistent prompt injection across turns (T-011, explicitly marked as residual risk "stateful LLMs may retain"), the Ledger shows a perfectly in-envelope sequence of actions whose _composition_ is adversarial.

Concrete example: envelope allows `send_email` to the user's contacts. Attacker bias: reason about each contact's timezone and subtly reorder the emails so the time of receipt correlates with the recipient's sleep cycle, enabling a delayed-detection exfiltration. Every individual action is in envelope. The Ledger records each one. User Grant-Moment-approves the pattern. Exfil succeeds. The ledger shows a legitimate sequence and the user has no structural way to audit intent.

T-005 ("semantic envelope bypass") addresses the _content_ of a single action. It does NOT address _composition_ attacks across multiple actions. T-011 ("indirect injection") mentions "stateful LLMs may retain" as residual risk — but residual risk in T-011 is actually the structural limit of the entire thesis.

**What doc would add:** T-012: "Compositional envelope bypass via chain-of-thought manipulation." Mitigation: (a) capture the LLM's reasoning trace (when exposed via the API — Anthropic extended thinking, OpenAI's reasoning tokens) and commit its hash into the Ledger entry for the associated tool-call; (b) rate-limit action sequences even within envelope (e.g., if more than N emails in a batch, Grant Moment); (c) pattern-detect "all-envelope-legitimate but novel composition" — implementable as an LLM-second-pass that reviews the sequence against declared intent. Residual risk: providers that don't expose reasoning tokens remain opaque. Document honestly. This is a **harder limit than T-005**.

---

### C-3. Ledger forking on offline multi-device operation has no stated conflict-resolution protocol

**Attack vector:** User's Envoy operates on two devices (laptop + phone) offline; they each append to their local Ledger. On reconnection, a coercive principal (or even just the sync protocol) must reconcile two valid hash chains. The reconciliation rule is un-specified and becomes an attack primitive.

**Why it works:** T-053 (Trust Vault sync) covers encryption of the vault at rest but does not define **merge semantics for the Ledger chain itself**. The Ledger is a hash chain; two chains diverging from a common ancestor are structurally incompatible. Git-style merge (both chains preserved with a merge commit) requires a new "merge" entry type the model doesn't have. Last-writer-wins loses entries. "Longer-chain-wins" lets an attacker with a pocket device that issues many low-value entries displace the legitimate chain. Without a spec for this, the developer will implement the simplest (last-writer-wins), and that's the CVE.

Related: the "versioning + integrity log" mitigation in T-053 only detects _whole-vault_ rollback — a chain fork where both branches are valid is not a rollback, so the integrity log passes.

**What doc would add:** T-100: "Offline ledger fork reconciliation." Spec required in `specs/ledger.md` §offline-merge covering: (a) deterministic merge protocol — probably using device-bound nonces and a total ordering across `(device_id, timestamp, signer_key_id)`; (b) merge entries are themselves signed and replay-protected; (c) conflicts that cannot be auto-merged (e.g., two envelope changes on the same dimension) halt sync and require Grant Moment; (d) test `tests/threat/ledger_fork_attack/` that submits two forked chains and asserts the merge is deterministic and both branches' grants are preserved (or one is explicitly superseded with a signed reason). This is a **Phase 01 gate** item because offline operation ships from day one.

---

## HIGH (load-bearing primitive missing; mitigation unclear)

### H-1. Grant Moment dialog spoofing — no authenticity binding between the OS and Envoy

**Attack vector:** A malicious app (or skill, T-020) on the same device renders a pixel-perfect imitation of a Grant Moment dialog. User approves, thinking it's Envoy's real dialog. Attacker captures the approval credential / triggers their own action.

**Why it works:** The threat model has T-070 (side-channel leakage out of Grant Moment) but not **injection into the dialog surface**. Envoy's whole thesis rests on the Grant Moment being _the_ sovereignty ritual — if the user cannot reliably distinguish a real Grant Moment from a fake one, the ritual is attackable. Mitigations like "duress passphrase" (T-041) and "secure-text-field" (T-070) assume the user is interacting with the real dialog. There is no mechanism named for the user to **verify the dialog is genuine Envoy** before approving.

Platform-native equivalents: iOS's Face ID prompt is rendered by the secure enclave UI, not the app; Android's BiometricPrompt uses TrustedUI; macOS passkeys are SE-rendered. Envoy's Grant Moment is (presumably) a regular app surface with no hardware attestation path in Phase 01.

**What doc would add:** T-071: "Grant Moment dialog spoofing." Mitigation: (a) every Grant Moment embeds a user-chosen passphrase/emoji/image chosen at install time (Trezor-style anti-spoof); (b) on platforms with trusted-UI (iOS, Android BiometricPrompt), route Grant Moment through it; (c) desktop uses a system notification with a signature visible to the user (an evolving one-line hash of the current Ledger head displayed in the dialog and verifiable out-of-band). Without this, the T-020 (malicious skill) threat has a clean in-envelope path: the skill spoofs a Grant Moment to obtain a delegation upgrade.

---

### H-2. Authorship Score gaming — the ratchet can be walked without genuine authorship

**Attack vector:** User (or attacker social-engineering the user) clicks "add constraint" 3 times with meaningless tweaks to cross the ≥3 threshold and unlock DELEGATING/AUTONOMOUS. Enterprise variant: IT writes a script that pre-fills N constraint-edits per employee, passing the ratchet mechanically.

**Why it works:** The thesis's central structural defense is "the posture-ratchet gate requires N authored constraints." Nowhere in the threat model is "authorship quality" defined, attacked, or defended. The Authorship Score is a counter. Counters can be incremented by a script. BET-12 names "template import is a starting point, not a shortcut" and BET-1 names the falsification condition ("if template-import + one-click posture-max-out is preferred..."), but **neither is defended in the threat model**.

This is a thesis-bypassing attack because the thesis's whole market argument is "authorship is a felt ritual users will pay for." If the posture-gate is trivially gamed, authorship becomes compliance theater — exactly the failure mode 1Password's auto-fill toggle represents per §4.2 of doc 00.

**What doc would add:** New category "Thesis-integrity threats." T-200: "Posture-ratchet gaming." Mitigation requires specifying (a) what counts as an authored constraint vs a no-op tweak — this is a _spec decision_, not purely a threat-model one; (b) rate-limit on constraint edits (at most M per week, N per lifetime); (c) semantic-diff requirement — edits must change the constraint's meaning, detected by an LLM-diff OR by a structural check (different dimension OR narrower scope); (d) rejected-constraint detection — constraints that are trivially wider than what they replace are rejected as not-authored; (e) Grant Moment explanation gate — on the Nth authored constraint, user is asked to explain the constraint in their own words, recorded in the Ledger (not shown to other users but shown to the user in Weekly Posture Review; low-quality explanations break the ratchet). Without these, BET-12 is non-falsifiable from a threat-model perspective.

---

### H-3. Delegation-upward collapse via enterprise "accept these envelopes" workflows

**Attack vector:** Enterprise IT publishes a set of "accepted" envelopes. Employees are required to "author" them by copying into their instance. The ratchet detects authorship. Thesis defense collapses.

**Why it works:** Related to H-2 but structurally different. Here the enterprise isn't bypassing the counter — it's using the counter against itself. Each employee genuinely authored (edited + committed) each constraint. The constraints are their IT's requirements. Envoy cannot tell the difference between "my genuine authorship" and "I am required to author what IT tells me." The thesis explicitly names this as the most important BET-12 falsification path ("enterprise IT authors one envelope for 500 employees"), but doc 09 has no structural defense.

§4.1 item 14 of doc 00 names "Envoy core does not ship SSO/SAML/SCIM," which mechanically limits enterprise rollout to third-party operators — but it does NOT prevent an ad-hoc enterprise script that runs locally on each employee's machine.

**What doc would add:** T-201: "Coordinated enterprise authorship / delegation-upward collapse via copy-paste." This is partly a market threat and partly a technical one. Technical mitigations: (a) constraint authorship requires a minimum "reflection time" between template-import and commit (e.g., 15 minutes for first constraint, 5 for subsequent); (b) constraint provenance is recorded — if the constraint-text was copied verbatim from a known public envelope (Envelope Library fingerprint match), it's flagged as template-origin and does NOT increment Authorship Score; (c) Weekly Posture Review asks the user to restate one constraint in their own words — low-quality restatement de-ratchets. Without these, BET-12's major-adjustment ("accept template-only at DELEGATING") is being forced from day one.

---

### H-4. Replay attack on signed Grant Moment approvals

**Attack vector:** A signed Grant Moment record for action A at time T is captured (via compromised sync, device backup, shoulder-surfed screenshot of Ledger) and replayed later as approval for a DIFFERENT action.

**Why it works:** The threat model does not name what a "Grant Moment record" cryptographically binds to. If the signature covers only `{action_type, approval_timestamp, user_key}`, then any tool-call matching that action_type later also has a valid approval signature — the attacker just needs a compromised component that substitutes the current attempted-action's input with the replayed signed approval. If the signature covers `{full action arguments, approval_timestamp, user_key, nonce}`, replay is harder but nonce-reuse attacks become a concern.

T-004 (streaming LLM pre-sign) hints at this with `intent_id` linking Phase A and Phase B records, but doesn't explicitly define the signature-scope. T-002 (household-adversarial) has "time-delayed revocation" which is a replay-adjacent mitigation but only for revocations, not for approvals.

**What doc would add:** T-101: "Replay attack on signed approvals." Mitigation: (a) every Grant Moment signature covers `(action_kind, args_hash, ledger_head_hash, timestamp, envelope_version, posture, nonce)`; (b) the `ledger_head_hash` inclusion means a replayed signature only verifies against the ledger state at the moment of signing — which is already in the past, so verifier rejects; (c) explicit replay-detection test `tests/threat/grant_replay/`. This must be in `specs/ledger.md` §signing-scope. The current two-phase-signing spec reference doesn't cover this.

---

### H-5. Foundation Health Heartbeat payload is a covert channel

**Attack vector:** A compromised Envoy install encodes exfiltration bits in the per-install random ID rotation cadence, the boolean flag selection pattern, or the timing of Heartbeat submission, all of which survive STAR k-anonymity aggregation because the aggregator sees submission metadata before aggregation.

**Why it works:** T-052 says "STAR k-anonymity ≥ 100" — the _payload_ is k-anonymous. But the random ID is "rotated quarterly" per doc 00 §5 bullet 5. The timing of the rotation is a side channel. A compromised install can rotate at specific intervals encoding one bit per week (~50 bits/year of covert channel), more than enough to exfiltrate the user's Authorship Score bucket or a de-anonymizing identifier. The ~20 boolean flags payload itself is a covert channel if an attacker controls one flag's mapping; STAR aggregation hides individual values but a compromised client can vary _which flag_ it marks true across submissions, encoding bits.

T-052 says the Heartbeat is opt-in, so the affected population is self-selected, but the entire point of Heartbeat is to enable Foundation to judge thesis falsifiability (§5 of doc 00) — if the data channel is attackable, the Foundation's judgments are biased.

**What doc would add:** T-054: "Covert channel via Heartbeat payload selection or timing." Mitigation: (a) rotation cadence is wall-clock deterministic (not per-install randomized) — every install rotates on the first Monday of each quarter; (b) boolean flag set is fixed per schema version; no client-side flexibility in which flags to report (missing = false); (c) submission time is bucketed to hourly windows and salted with per-schema-version hash; (d) Heartbeat schema is subjected to an independent review for covert-channel capacity before each schema version ships. Residual risk: low-bandwidth channels (Heartbeat present/absent this week) remain. Document the covert-channel-capacity bound.

---

### H-6. Grant Moment habituation — user becomes a rubber-stamp

**Attack vector:** User receives ~5 Grant Moments per week for familiar actions (daily digest approvals, routine email drafts). After week 4, user clicks "approve" without reading. Attacker introduces one novel action hidden in a batch; user rubber-stamps.

**Why it works:** T-020 says "any tool-call not seen in this envelope-scope requires a Grant Moment," which sounds like a novel-action protection, but **the mitigation is load-bearing on the user noticing the novelty**. Once the user has approved dozens of Grant Moments, the 31st one's novelty is cognitively invisible. Every consumer-sovereignty tool with this pattern (1Password toggles, Little Snitch "allow forever," UAC prompts on Windows) has habituated users to click through.

T-005 addresses _classifier_ false negatives but not _human_ false negatives. §4.2 of doc 00 identifies this as the central product risk ("Little Snitch collapsed — 0.5% adoption") and BET-1/BET-12 name it as the thesis's central falsifiable claim, but doc 09 does not name the habituation attack that operationalizes the risk.

**What doc would add:** T-060a: "Grant Moment habituation / rubber-stamp attack." Mitigation: (a) mandatory read-time delay on novel actions that scales with novelty — first-time a Grant Moment is in a new dimension/scope, the approve button is grayed out for N seconds; (b) batch-busting — Grant Moments for _compositions_ of familiar actions (email batches, multi-recipient sends) are always presented one at a time; (c) attention checks — occasional Grant Moments with a deliberate "do not approve this test" marker; approval breaks the user's ratchet temporarily; (d) ritualized review cadence — Weekly Posture Review surfaces approved-Grant-Moments for retrospective review, allowing post-hoc revocation via cascade. The mechanism must be in `specs/grant-moment.md` §habituation-defense.

---

### H-7. Multi-turn goal drift with no Ledger checkpoint

**Attack vector:** In a long-running conversation (say, a task spanning 30 turns), the agent's goal silently mutates turn-over-turn due to prompt drift. The ledger records each tool-call; none of them individually violate envelope. But the _goal state_ at turn 30 is not what the user asked for at turn 1.

**Why it works:** The threat model treats each action atomically. It does not enumerate a "goal-state checkpoint" primitive. In multi-turn interactions, the LLM re-reads previous turns + its own outputs, so drift compounds. The user who issued the original intent at turn 1 may not be paying attention at turn 25; the agent does not stop to confirm goal alignment. This is adjacent to T-011 (indirect prompt injection) and C-2 (chain-of-thought manipulation) but structurally distinct: no injection, just drift.

**What doc would add:** T-061: "Multi-turn goal drift." Mitigation: (a) every N turns (N=5 default), the Ledger records a `GoalCheckpoint` entry with the agent's summary of current goal state; (b) a goal change across turns (LLM-detected) triggers a Grant Moment; (c) Weekly Posture Review surfaces goal-drift incidents for user audit; (d) the agent's system prompt forces periodic re-statement of the original goal. Implementable today in Phase 01 via Kaizen agent framework; missing from doc 09.

---

### H-8. Sybil attack on Envelope Library Community tier reputation

**Attack vector:** One author (or coordinated group) creates many publisher Ed25519 identities, each publishing variants of the same over-permissive envelope, cross-upvoting / installing each others'. The "adoption × (1 − revocation)" ranking metric rewards them; their envelopes appear at the top of Community tier search.

**Why it works:** T-021 addresses individual malicious envelope publishers. It does NOT address coordinated ones. The proposed mitigation ("community tier ranking by adoption × (1 − revocation rate)") is structurally Sybil-attackable unless Envoy has a mechanism to de-duplicate publisher identities / adoption events. But Envoy is explicitly designed to avoid identity infrastructure (§4.1 item 8, "no hosted identity"); the federated Envelope Library has no SSO to tie a publisher to a real person. A Sybil with 50 keys and 50 install events on each skill looks identical to 50 genuine users installing from 1 publisher.

**What doc would add:** T-022: "Sybil attack on Community tier reputation." Mitigation: (a) weight adoption events by Foundation Health Heartbeat cohort-size evidence — if the reported install rate on the Community tier doesn't match the aggregated Heartbeat cohort, flag suspicious; (b) Sybil-resistant upvote via optional Github-OAuth-attested review (not full SSO, one-shot attestation); (c) rate-limit new publisher accounts behind a CAPTCHA-equivalent proof; (d) require N days of history before a publisher's envelope becomes eligible for top-ranked position. Without these, T-021's "community tier ranking" mitigation is inoperative.

---

### H-9. First-time-action gate is load-bearing but unspecified

**Attack vector:** T-010 ("direct prompt injection") mitigation requires "first-time-action gate" — but nowhere in doc 09 is "first time" defined.

**Why it works:** Is first-time per-envelope? Per-posture-session? Per-device? Per-tool? Per-tool-plus-arguments? If it's per-tool, an attacker chains through already-seen tools. If it's per-tool-plus-args, the attacker varies args trivially. If it's per-envelope-revision, then the first action after any envelope edit is gated — which creates a denial-of-service, not a security gain, if the user frequently edits. The entire cascade of T-010/T-011/T-020 mitigations cites "first-time-action gate" but the spec is not defined; this is a gap.

**What doc would add:** "First-time" needs a formal definition. Proposed: a tool call is first-time iff (tool_id, recipient_or_target_hash, envelope_version) tuple has never appeared in the Ledger. Recipient-or-target-hash is what makes `send_email@alice` distinct from `send_email@bob`. Add `specs/grant-moment.md` §first-time-definition. Add a test `tests/threat/first_time_gate/` that verifies the tuple semantics and that attackers cannot subvert by varying irrelevant arguments.

---

### H-10. Algorithm-identifier schema is vaporware in Phase 01

**Attack vector:** Doc 09 §5 out-of-scope notes "algorithm-identifier schema enables migration" for post-quantum. Doc 03 confirms this primitive is **absent on both kailash-py and kailash-rs** (item 19, "New spec + implementation on BOTH sides"). Ledger entries signed in Phase 01 have no algorithm tag. When the PQ migration happens, Phase 01 ledger signatures cannot be distinguished from PQ signatures and must all be treated as weak.

**Why it works:** The threat model claims PQ migration is "deferred" but enabled by algorithm-identifier schema. But that schema is not implemented. Every signature written in Phase 01 is unversioned Ed25519. When PQ arrives, you can't upgrade-in-place because old signatures were never tagged. The only options are (a) treat all pre-PQ ledger content as untrusted (full re-signing), or (b) keep classical signatures valid forever (PQ migration promise broken). Both options contradict the stated residual risk mitigation.

**What doc would add:** Escalate the algorithm-identifier issue to a Phase 01 gate item. Every Phase 01 signature MUST carry a version tag from day one. This is a T-042 / T-050 / T-053 cross-cutting concern. Current doc 00 §4.1 item 9 names it as a scope addition, but doc 09 §7 Phase 01 gates does NOT name it, which means Phase 01 can exit without it and the residual risk is actually active, not deferred.

---

### H-11. Panic-wipe on failed-unlock is a DoS amplifier for a coerced user

**Attack vector:** T-040 offers "panic-wipe ritual" (10 wrong passphrase attempts → Trust Vault destroyed) as defense against stolen devices. An attacker aware of this who cannot unlock performs 10 bad attempts to wipe the user's vault out of spite.

**Why it works:** Panic-wipe is a one-way operation. The user can recover from Shamir (which remains valid per the mitigation text), but this assumes the user still has their Shamir shards. If shards are with trusted humans (T-006 scenario), the user needs to physically re-collect shards — potentially days of delay. If the user's device is stolen and they have a panic-wipe threshold of 10, the thief doesn't need to unlock; they just need to try 10 times to cause maximum damage. Panic-wipe becomes a DoS primitive for the attacker, not a defense for the user.

Related: this interacts badly with T-002 household-adversarial — a coercive principal who knows their spouse's device panic-wipe threshold can force a wipe to destroy evidence.

**What doc would add:** T-040a: "Panic-wipe as DoS amplifier." Mitigation: (a) panic-wipe default is SHOULD, not MUST, and is opt-in at install time (currently "SHOULD" — clarify it's NOT the default); (b) panic-wipe after N failed attempts uses an exponential backoff on the unlock counter, so causing the wipe requires days, not seconds, of continuous attempts — giving the user time to remote-lock the device (T-040 mitigation 5); (c) post-panic-wipe, the Ledger retains a signed "wipe event" entry in a separate durable store (syncable to Foundation Trust Vault sync node) so the user can prove the wipe occurred and demand insurance/escrow recovery. Document carefully.

---

## MEDIUM (requires favorable conditions; or mitigation exists but is weak)

### M-1. Runtime picker at first-run does not verify provenance of the locally-installed package

**Attack vector:** Phase 02 first-run UX asks user to pick runtime (`kailash-py` or `kailash-rs-bindings`). A malicious installer (or a compromised package on PyPI for either package) substitutes a compromised binary. The runtime picker just asks "which?" and does not verify the selected package's signature.

**Why it works:** T-050 and T-060 cover binary distribution compromise and runtime-path binary poisoning. But the runtime picker is a _separate_ UX step where the user chooses, and the threat model does not name the provenance check as part of that step. A user may assume the UI's picker = verified runtime, but the threat model only commits to signature verification at binary load (T-060) and installer time (T-050). If the user picks a runtime that was already tampered with before Envoy ran, Envoy trusts the selection.

**What doc would add:** Cross-reference from runtime-picker UX (Phase 02 entry) to T-060 signature verification. The picker MUST complete signature verification before offering the choice. Reject the runtime from the picker if signature fails, display an error explaining the remediation.

---

### M-2. Ledger format version downgrade attack

**Attack vector:** At some phase transition (Phase 02 → 03), Ledger format migrates from v1 to v2 with new fields. An attacker with write access to the Ledger (compromised sync target, local malware) replaces a recent v2 entry with a v1 entry missing the new security field (e.g., missing tenant_id or classifier_version).

**Why it works:** T-053 addresses _rollback_ (whole-vault older version), not _per-entry format downgrade_. If Envoy accepts v1 entries indefinitely for back-compat (which it must for historical verification), then forged v1 entries are accepted as legitimate and bypass new protections. Similar attacks are well-known in TLS (TLS_FALLBACK_SCSV), JWT (alg:none), and image formats (PDF polyglots).

**What doc would add:** T-053a: "Per-entry format downgrade attack." Mitigation: (a) the Ledger records a "minimum-accepted-version" entry signed at each format-upgrade; (b) any subsequent v1 entry must have a timestamp older than the minimum-accepted-version entry; (c) Ledger verifier rejects newer-timestamp-older-format entries. Spec in `specs/ledger.md` §format-versioning.

---

### M-3. Shamir shard pre-computation attack via weak polynomial construction

**Attack vector:** If the SLIP-0039 library uses a small field or a predictable PRNG for polynomial coefficients, an attacker who has observed partial shard distribution (or obtained < m shards) may pre-compute reconstruction faster than the naive m-of-n bound.

**Why it works:** The doc names SLIP-0039 and cites `sharks`/`vsss-rs` and `slip39`/`python-shamir-mnemonic` as "audited 3rd-party libs." Audited ≠ secure against chosen adversarial models. The threat model does not name the specific adversarial assumptions (field size, PRNG source, side-channel resistance) the Shamir implementation must meet. For example, some SLIP-0039 implementations use GF(256); sufficient for secrecy but attackable via lattice reduction with auxiliary side-channel info (power traces during reconstruction).

**What doc would add:** Phase 00 gate item (currently lists "crypto library audit") must explicitly include: (a) confirm SLIP-0039 implementation uses a cryptographically-secure random polynomial coefficient derivation; (b) side-channel resistance claims of chosen implementation; (c) no shard re-use across different vaults (each vault generates new polynomial). Cite specific implementation choices.

---

### M-4. Key compromise recovery flow for primary signing key is undefined

**Attack vector:** User's Genesis Record primary signing key is compromised (device compromise, key extraction). User wants to revoke-and-re-mint. The threat model has no defined flow for this.

**Why it works:** T-040 (lost device) implies the device-bound key cannot be extracted — but "cannot" means "hard" not "impossible." The threat model has no explicit entry for "primary signing key compromised." The Shamir shards reconstruct the vault, not a fresh Genesis. There's no cascade-revocation primitive that traces back to revoke the Genesis itself because the Genesis is the root of trust — revoking it invalidates everything downstream.

**What doc would add:** T-044: "Primary key compromise and re-mint ritual." Mitigation: (a) Genesis Record includes a pre-committed "revocation key" (separate from the primary) stored in Shamir shards; (b) revocation is a separate key unveiling that triggers cascade revocation of all delegations AND declares the Ledger's new Genesis; (c) old Ledger content remains verifiable against old Genesis but signatures after revocation point must use new Genesis. Spec `specs/trust-lineage.md` §key-compromise-recovery. Without this, a compromised Genesis is irrecoverable.

---

### M-5. Correlation attack on OHTTP submissions via timing and size

**Attack vector:** Even with OHTTP relay separation from aggregator, consistent timing or size patterns from a specific install correlate with subsequent aggregated STAR output changes, enabling de-anonymization.

**Why it works:** T-052 addresses IP harvesting but only partially. STAR k-anonymity works only when submissions are indistinguishable. Envoy's Heartbeat spec has a "per-install random ID rotated quarterly" — but within a quarter, that ID is stable. A relay operator sees quarterly-stable ID + IP pattern + submission timing; aggregation hides payload but not submission metadata. An attacker correlating Heartbeat submissions with external signals (user's social media posts, public GitHub commits by the user) can narrow identity.

**What doc would add:** T-052a: "OHTTP submission metadata correlation." Mitigation: (a) random ID rotation on every submission (no quarterly stability); (b) fuzz-time submissions within a bucket (Poisson-distribution over a 24-hour window); (c) padding to canonical size. The current "quarterly rotation" is actually worse than constant rotation for correlation resistance.

---

### M-6. Emotional-override coercion is only partially mitigated by time-delays

**Attack vector:** "Your boss is waiting, just approve the email send." High-stakes actions have time-delay (T-041 mitigation), but not _all_ harmful actions are high-stakes individually — many are harmful in aggregate (exfiltration via small batched sends) or contextual (wrong recipient at wrong time).

**Why it works:** T-041 ("coerced unlock") mitigations focus on duress passphrases + high-stakes time-delay. But coercion doesn't always look like gun-to-head; it looks like social pressure. The time-delay threshold is a single scalar. A phishing call pressuring a user to approve "just this one thing" that's individually low-stakes bypasses the delay.

**What doc would add:** T-041a: "Social-pressure coercion below high-stakes threshold." Mitigation: (a) velocity-based delay — if the user has approved more than N Grant Moments in the last M minutes, additional approvals are queued; (b) anomaly detection — approval of an action unusual for the current time-of-day or location triggers a delay; (c) Weekly Posture Review flags "pressured approval" patterns (e.g., clustered approvals just before a known stressful calendar event). Implementable in Phase 03 via Heartbeat-informed baselines or local-only anomaly detection.

---

### M-7. Language-based manipulation in envelope prose

**Attack vector:** Malicious envelope publisher uses weasel-words ("restrictive, for most uses"; "typical settings") to make a permissive configuration appear restrictive to a human reader.

**Why it works:** T-021 says "envelope linter at import time flags overly broad allowlists." The linter is a structural check — it checks the envelope's computed scope, not its prose. But users read prose to decide whether to import; a permissive envelope with restrictive prose will be imported widely. The linter catches it structurally but AFTER import.

**What doc would add:** T-021a: "Language-based misrepresentation of envelope restrictiveness." Mitigation: (a) envelope prose is separated from envelope structure; (b) every envelope is displayed in a canonical structural form (tree of dimensions + scopes) before import; the prose is side-by-side not substituted; (c) a "this envelope is X percentile restrictive among Community tier" indicator based on the structural scope computation. Specify the UX mandate in `specs/envelope-library.md`.

---

### M-8. False-positive semantic-classifier erodes trust; user disables the constraint

**Attack vector:** User sets up a Data Access semantic constraint ("no tax info"). Classifier has false-positive rate ~5%. Over a week, user gets 3 false alarms. On the 4th, user disables the constraint entirely.

**Why it works:** T-005 addresses classifier failure modes but focuses on false negatives (adversarial bypass). False positives are named as "acceptable, false negatives are not," which is correct for the attacker model but wrong for the _user-abandonment_ model. A user who disables a constraint has zero protection; a constraint that rarely fires (false positives OK) that user leaves on has some.

**What doc would add:** T-005a: "User abandonment of high-false-positive semantic constraints." Mitigation: (a) classifier uncertainty visibility — each false-positive Grant Moment shows the classifier's confidence and allows the user to tag "actually safe," improving the classifier's per-user calibration; (b) a "snooze without disable" for 24 hours — user dismisses temporarily rather than deletes permanently; (c) Weekly Posture Review surfaces disabled constraints for re-activation. Spec update in `specs/envelope-model.md`.

---

### M-9. Cross-agent coordination in Shared Household — two agents pursuing a goal neither principal approved

**Attack vector:** Principal A's agent and principal B's agent coordinate via A2A (both principals have DELEGATING posture for related dimensions). Prompt injection in one agent's context causes the pair to achieve a goal neither principal individually approved.

**Why it works:** T-002 (household-adversarial) addresses the case of a _coercive principal_, not two _compromised agents_. Doc 03 item 15 notes A2A binding is stubbed in Rust; kailash-py has it functional. If Envoy composes A2A for household coordination, the cross-agent trust relation is un-modeled in the threat catalog. Each agent's individual Ledger records its tool-calls; but the coordination itself is A2A message passing, and those messages may be signed only agent-to-agent, not visible to either principal until after the fact.

**What doc would add:** T-002a: "Cross-principal agent coordination attack." Mitigation: (a) every A2A message is a Ledger entry on BOTH principals' ledgers; (b) A2A-triggered action requires both principals' envelopes to allow it, checked via recomputed intersection; (c) novel cross-principal A2A patterns trigger Grant Moments on both sides. Spec `specs/shared-household.md` §a2a-auditability.

---

### M-10. Trust Vault encryption — chosen-plaintext and ciphertext-length attacks

**Attack vector:** A partial-compromise of sync target (operator observes ciphertexts across time) plus partial knowledge of plaintext (attacker knows the user installed skill X on date Y, visible in Envelope Library access logs) enables chosen-plaintext-style analysis.

**Why it works:** T-053 specifies AES-256-GCM with user-held key. AES-256-GCM is IND-CPA secure if nonces are unique. But the threat model does not say how nonces are derived; if they're counter-based without a restart-safe counter, a crash could re-use a nonce. The threat model also doesn't address padding to hide size patterns (only "SHOULD — padding"). Without padding, the ciphertext length reveals envelope/ledger growth patterns.

**What doc would add:** T-053b: "Chosen-plaintext + length leakage on sync ciphertext." Mitigation: (a) mandate nonce scheme (e.g., random 96-bit GCM nonce with collision probability documented); (b) upgrade padding from SHOULD to MUST — padding to nearest 4KB is cheap and hides most activity-pattern leakage; (c) key-rotation on ciphertext volume or time elapsed. Spec update in `specs/trust-vault.md` §sync-encryption.

---

### M-11. Legal-process at Foundation-compelled key-destruction refusal

**Attack vector:** Legal process not against user but against Foundation: court orders Foundation to NOT honor a user's key-destruction request (because litigation is pending against that user). Foundation's technical primitive (key destruction by user) is available but the Foundation may be legally blocked from publishing a revocation.

**Why it works:** T-042 focuses on user-level legal process. It mentions "Foundation's response to legal process: Foundation holds only metadata + aggregated Heartbeat." But the Envelope Library revocation list IS Foundation-operated, and a court could compel Foundation to NOT publish a revocation OR to publish a false revocation. This would affect the cascade revocation's reliability for users downstream of the compelled revocation.

**What doc would add:** T-043: "Foundation-compelled revocation-list tampering." Mitigation: (a) revocation list is published via content-addressable storage (IPFS, Arweave); Foundation posts the CID but cannot unpublish; (b) client verifies CID inclusion proofs, not Foundation's assertion; (c) Foundation's Trust Lineage governance itself is multi-sig (2-of-N) — a single compelled steward cannot remove a revocation. Spec in `specs/envelope-library.md` §revocation-censorship-resistance.

---

## LOW (theoretical or well-mitigated elsewhere)

### L-1. Duress passphrase detection via response latency

**Attack vector:** Attacker timing the user's unlock observes latency-differential between duress and primary passphrase entry; distinguishes.

**Why it works:** Already listed as residual risk under T-041; explicit in doc 09. However, noting: the mitigation is "Unfixable; documented." A slightly stronger mitigation is constant-time passphrase processing (hash both, branch in constant-time on comparison) — this should be a MUST implementation detail, not just "document the risk."

**What doc would add:** Strengthen T-041 mitigation: passphrase processing is constant-time regardless of which passphrase is correct; keyboard-input entropy masking (random cosmetic delays). These don't defeat sophisticated observers but raise the bar.

---

### L-2. Post-quantum cryptographic attack timing

**Attack vector:** PQ cryptanalysis matures faster than expected; Ed25519 signatures on old Ledger entries become forgeable.

**Why it works:** Out-of-scope per §5. Fair, but note: the residual-risk table row "Post-quantum cryptography migration timing" says "algorithm-identifier schema enables migration." Per H-10, that schema is vaporware. The residual risk is worse than stated.

**What doc would add:** Already covered by H-10 above. Cross-reference added.

---

### L-3. Envelope Library DoS via spam submissions

**Attack vector:** Attacker floods Envelope Library registry with bad envelopes to overwhelm reviewers and/or moderation queue.

**Why it works:** T-021 covers malicious envelope authors but not bulk-spam. Mitigation likely present implicitly (registry rate-limits, publisher account required per H-8), but not named as a separate threat. Low-impact because reviewers are only load-bearing for Foundation-Verified tier, not Community.

**What doc would add:** Brief mention in T-051 or a new T-051a: standard rate-limiting + publisher-account-throttling. Known-pattern, uninteresting to specify deeply.

---

### L-4. Connection Vault clipboard hygiene on iOS

**Attack vector:** iOS clipboard retention across apps; Envoy cannot clear it.

**Why it works:** Already listed as residual risk under T-007 ("clipboard hygiene is OS-dependent. iOS clipboard history can't be cleared"). Mitigation named (Shortcut-based credential injection). Acceptable residual.

**What doc would add:** Nothing new.

---

### L-5. Foundation Health Heartbeat skipped altogether

**Attack vector:** Compromised Envoy install that simply doesn't send Heartbeat to evade detection of the compromise.

**Why it works:** Heartbeat is opt-in and has no adversarial-client detection. This is not a user-harming threat; it only degrades Foundation's ability to judge thesis falsifiability. Out of scope for a product threat model per §1.2, but worth naming for BET-9 (Foundation Health Heartbeat) failure modes.

**What doc would add:** One sentence in residual-risk table: "Compromised clients may abstain from Heartbeat to evade detection; Foundation should not rely on Heartbeat data as a security-compromise signal."

---

### L-6. TEMPEST-level emanation of signing operations

**Attack vector:** Side-channel emanation (power, EM) during signing operations leaks key material.

**Why it works:** Out of scope per §1.2. Accepted.

**What doc would add:** Nothing. Already correctly out of scope.

---

## Summary table

| ID   | Severity | Title                                                     | Missing spec / test                                      |
| ---- | -------- | --------------------------------------------------------- | -------------------------------------------------------- |
| C-1  | CRITICAL | Sub-agent envelope-scope forgery                          | specs/a2a.md §scope-monotonicity; tests/threat/subagent  |
| C-2  | CRITICAL | Chain-of-thought compositional envelope bypass            | specs/ledger.md §reasoning-hash; tests/threat/cot        |
| C-3  | CRITICAL | Offline Ledger fork reconciliation                        | specs/ledger.md §offline-merge; tests/threat/ledger_fork |
| H-1  | HIGH     | Grant Moment dialog spoofing                              | specs/ui-platform.md §trusted-ui                         |
| H-2  | HIGH     | Authorship Score gaming                                   | specs/authorship-score.md §quality-requirements          |
| H-3  | HIGH     | Delegation-upward via enterprise copy-paste               | specs/authorship-score.md §template-provenance           |
| H-4  | HIGH     | Replay attack on signed Grant Moments                     | specs/ledger.md §signing-scope                           |
| H-5  | HIGH     | Heartbeat payload covert channel                          | specs/foundation-health-heartbeat.md §covert-audit       |
| H-6  | HIGH     | Grant Moment habituation                                  | specs/grant-moment.md §habituation-defense               |
| H-7  | HIGH     | Multi-turn goal drift                                     | specs/ledger.md §goal-checkpoint                         |
| H-8  | HIGH     | Sybil on Community-tier reputation                        | specs/envelope-library.md §sybil-resistance              |
| H-9  | HIGH     | First-time-action gate unspecified                        | specs/grant-moment.md §first-time-definition             |
| H-10 | HIGH     | Algorithm-identifier schema vaporware                     | Phase 01 gate add                                        |
| H-11 | HIGH     | Panic-wipe as DoS amplifier                               | specs/trust-vault.md §panic-wipe-backoff                 |
| M-1  | MEDIUM   | Runtime picker doesn't verify provenance                  | doc 06 UX cross-ref to T-060                             |
| M-2  | MEDIUM   | Ledger format version downgrade                           | specs/ledger.md §format-versioning                       |
| M-3  | MEDIUM   | Shamir shard pre-computation / implementation assumptions | Phase 00 gate expansion                                  |
| M-4  | MEDIUM   | Primary key compromise re-mint flow                       | specs/trust-lineage.md §key-compromise                   |
| M-5  | MEDIUM   | OHTTP submission metadata correlation                     | specs/foundation-health-heartbeat.md                     |
| M-6  | MEDIUM   | Social-pressure coercion below threshold                  | specs/envelope-model.md §velocity-delay                  |
| M-7  | MEDIUM   | Envelope prose language-based misrepresentation           | specs/envelope-library.md §prose-structural-split        |
| M-8  | MEDIUM   | False-positive semantic classifier abandonment            | specs/envelope-model.md §classifier-ux                   |
| M-9  | MEDIUM   | Cross-principal agent coordination via A2A                | specs/shared-household.md §a2a-auditability              |
| M-10 | MEDIUM   | Trust Vault sync chosen-plaintext + length leakage        | specs/trust-vault.md §sync-encryption-hardening          |
| M-11 | MEDIUM   | Foundation-compelled revocation-list tampering            | specs/envelope-library.md §revocation-censorship         |
| L-1  | LOW      | Duress passphrase latency differential                    | T-041 mitigation strengthening                           |
| L-2  | LOW      | PQ residual risk stronger than stated                     | See H-10                                                 |
| L-3  | LOW      | Envelope Library spam DoS                                 | T-051a rate-limit note                                   |
| L-4  | LOW      | iOS clipboard                                             | already residual                                         |
| L-5  | LOW      | Compromised clients skip Heartbeat                        | residual note for BET-9                                  |
| L-6  | LOW      | TEMPEST                                                   | already out-of-scope                                     |

---

## Most important gaps the author should fix first

1. **C-1 sub-agent forgery** and **C-2 chain-of-thought** together invalidate the doc's implicit assumption that "one agent with signed visible tool-calls + envelope = complete surface." Multi-agent, multi-turn, multi-internal-state is the actual surface. These need threat entries before Phase 01 composes A2A or multi-turn tasks.

2. **H-2 Authorship Score gaming** + **H-3 delegation-upward via copy-paste** are the thesis's central BET-12 falsification paths. The threat model currently has no structural defense; BET-12 is at risk of being disconfirmed on day one if a demo shows the ratchet can be walked with 3 no-op edits.

3. **H-1 Grant Moment spoofing** + **H-6 habituation**: the ritual that the whole product rests on has no authenticity binding and no habituation defense. Both are well-known failure modes in consumer sovereignty products (Little Snitch, UAC, 1Password). The threat model names Little Snitch's collapse in doc 00 §4.2 but doesn't adapt the lesson here.

4. **H-10 algorithm-identifier schema**: promised as a residual-risk mitigation, but not implemented. The Phase 01 gate section must enforce tagged signatures from day one or acknowledge that PQ migration is structurally blocked.

5. **C-3 ledger forking**: offline operation ships Phase 01. Merge semantics MUST be specified before ship or the first user with a laptop + phone is a CVE.

**Relevant file paths:**

- `/Users/esperie/repos/dev/envoy/workspaces/phase-00-alignment/01-analysis/09-threat-model.md` — under review
- `/Users/esperie/repos/dev/envoy/workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` — thesis (BET-1, BET-12, §4.2 Little Snitch reference)
- `/Users/esperie/repos/dev/envoy/workspaces/phase-00-alignment/01-analysis/03-primitive-reconciliation.md` — primitive state (ISS-28 A2A stub, item 15/16; ISS-25 BaseAgent stub; item 19 algorithm-identifier absent both sides)
- `/Users/esperie/repos/dev/envoy/workspaces/internal/kailash-rs-survey-2026-04-21.md` — binding gaps (A2A C6; BaseAgent B1; MCP transport C4)
