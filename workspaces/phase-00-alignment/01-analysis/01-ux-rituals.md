# 01 — UX Rituals

**Document status:** **FROZEN v2** — post Round 1 (3 CRIT + 6 HIGH resolved inline)
**v2 fixes:** **C-01** escape-phrase recovery path removed from §13; accidental-duress recovery relies on waiting out coercion + real-passphrase re-unlock → shadow-segment notification surfaces at next real unlock. **C-02** new §3.5a post-duress review ritual specified; surfaces as priority Daily Digest row + modal banner with visible-secret binding at next real unlock. **C-03** visible-secret rotation cadence — quarterly scheduled rotation + event-driven re-prompt; cross-channel secret verification for high-stakes actions. **H-01** channel list reconciled to doc 00 v3 (6 messaging + CLI + Web = 8 surfaces); §5.6 "channel-adaptive" section corrected; doc 07 authoritative. **H-02** Grant Moment timeout behavior identical between real + honeypot paths; queue back-pressure after N parallel Grant Moments; timeout configurable per envelope per-tool. **H-03** primary-channel binding added — high-stakes Grant Moments render + approvable ONLY on user's designated primary channel. **H-04** novelty-scoring function concrete: recipient novel if not in 7-day recency cache; dollar range outside ±25% of 30-day P50; tool unseen in last 7 days; compositional novelty per new N-gram of tool-call sequences. **H-05** "Approve + author" path rejects any constraint whose compiled effect widens any velocity dimension — redirects to Weekly Posture Review + 24h cool-off. **H-06** Shamir distribution checklist persists only opaque slot labels; real names optional + stored in hidden-envelope (Phase 04) only.
**Date:** 2026-04-21
**Scope:** The user-visible UX flows that operationalize the envelope + Trust Lineage + Ledger primitives. Boundary Conversation (onboarding), Grant Moment (per-action consent), Daily Digest, Weekly Posture Review, Monthly Trust Report, Duress passphrase UX, Shamir 3-of-5 ritual UX, Posture slider, channel-native vs CLI/Web surfaces. Load-bearing for the thesis's "rituals form daily habit" claim (BET-8, BET-12).
**Sources:** doc 00 v3 FROZEN (canonical rituals, 5-level posture, Authorship Score), doc 02 v3 FROZEN (envelope schema, composition rules, turn-N goal-reconfirmation), doc 03 v1 (Trust Lineage, duress + key destruction), doc 09 v3 FROZEN (T-018 visual secret, T-019 habituation, T-040 coerced unlock, T-041 duress, T-093 velocity ratchet), internal brief (`workspaces/internal/openclaw-analysis/02-plans/superior-product-concept-2026-04-21.md` §5 ritual examples).

---

## 1. Purpose

The thesis (doc 00 §2.4): _"Products that ritualize authorship of envelopes earn primary-surface loyalty that tool-frame AI products cannot."_ This doc specifies the ritual UX — the state machines, text templates, channel-adaptive rendering, and escape hatches — that make the thesis experientially real.

Every ritual must:

1. **Complete under user control** — user can skip, pause, resume at any step.
2. **Produce a signed Ledger entry** — rituals that don't land in the Ledger are meaningless.
3. **Render in any active channel** — channel-native from Phase 01 (not CLI+Web-only).
4. **Respect the habituation defense** — novelty-aware friction prevents rubber-stamp collapse (doc 09 T-019).
5. **Be inspectable in Monthly Trust Report** — ritual engagement metrics surfaced to user.

### In scope

- Boundary Conversation (first-run onboarding)
- Grant Moment (per-action consent)
- Daily Digest (morning ritual)
- Weekly Posture Review (Sunday 90s)
- Monthly Trust Report (month-end PDF+JSON)
- Posture slider (user-visible UI)
- Duress passphrase UX
- Shamir 3-of-5 ritual UX (shard generation, distribution, recovery, rotation)
- Channel-native rendering contracts
- Localization + accessibility
- Ritual state-machine definitions
- Ritual-engagement telemetry (opt-in via Foundation Health Heartbeat)

### Out of scope

- Envelope schema (doc 02).
- Delegation Record signing (doc 03).
- Ledger entry format (doc 04).
- Runtime two-phase signing (doc 05).
- Channel adapter contracts (doc 07 — this doc says WHAT the UX should do; doc 07 says HOW adapters render).
- Distribution / installer flow (doc 06).

---

## 2. Ritual state machines — shared conventions

Every ritual is a state machine with explicit states, transitions, escape hatches, and persistence points. States are persisted to Trust Vault so interruption (process crash, channel disconnect, user pause) resumes cleanly.

### 2.1 Common state machine shape

```text
state RitualInstance {
  ritual_id: uuid                 # unique per instance
  ritual_type: enum               # boundary_conversation | grant_moment | daily_digest | ...
  started_at: iso8601
  current_state: string           # ritual-specific
  persisted_answers: map<step_id, structured_answer>
  channel_origin: string          # which channel initiated
  principal: Address              # who's interacting
  pause_count: int
  escape_requested: bool
}
```

**Transitions:**

- `user_answer(step_id, answer)` — append to `persisted_answers`.
- `user_pause()` — set `pause_count += 1`; state preserved.
- `user_resume()` — rehydrate; last step surfaces.
- `user_escape()` — set `escape_requested`; ritual terminates with partial state; Ledger entry records.
- `timeout()` — auto-pause after ritual-specific timeout.

### 2.2 Channel-adaptive rendering

Every ritual's prompts + responses + controls adapt to the active channel:

- **CLI** — plain text with `>>>` answer prompt; colors + Unicode box-drawing.
- **Web** — HTML with modal dialogs; visible secret (doc 09 T-018) rendered as icon+color+phrase.
- **Telegram** — inline keyboards, button callbacks.
- **Slack** — block-kit messages.
- **Discord** — button components + slash commands.
- **WhatsApp** — numeric quick-reply (1/2/3) + media attachments.
- **Signal** — markdown text; reply-based state machine.
- **iMessage (BlueBubbles)** — rich text + iMessage reactions.

Adapter contract: every ritual prompt must be expressible in ALL supported channels. If a channel can't render a prompt (e.g. Signal without rich buttons), fallback to text + numeric quick-reply.

### 2.3 Visible-secret binding (doc 09 T-018)

Every ritual dialog that prompts for consent OR displays Ledger content MUST render the user's visible secret (chosen at install: icon + color + short phrase). Absence = user should reject as spoofed.

Visible secret rendered:

- **Top-right corner** in Web modal.
- **Above-prompt banner** in CLI.
- **Message header** in channel messages.
- **Inline keyboard title** in Telegram.

Secret is stored in Trust Vault. Only Envoy (reading from Trust Vault) can render it. A malicious app on the same device cannot predict the secret without Trust Vault compromise.

### 2.4 Telemetry via Foundation Health Heartbeat

If user opted into Heartbeat (doc 00 v3 §4.1 item 7a), ritual engagement flags are reported as per-install random-ID-keyed boolean counters aggregated via STAR/Prio. Flags include:

- `completed_boundary_conversation` (once per install)
- `opened_daily_digest_this_week` (per-week)
- `completed_weekly_posture_review` (per-week, Phase 03+)
- `opened_monthly_trust_report` (per-month, Phase 03+)
- `grant_moment_novelty_approved` (rolled up)
- `grant_moment_novelty_denied` (rolled up)
- `force_install_used_skill` (any Phase 02+)
- `duress_unlock_detected` (NEVER reported — privacy preservation)

---

## 3. Boundary Conversation — onboarding ritual

### 3.1 Purpose

First-run dialogue that compiles the user's answers into an `EnvelopeConfig`. Per doc 00 v3 §8 Test-1: onboarding cannot skip boundary declaration. Template import is a legal starting point; the Boundary Conversation personalizes and adds novel-authored constraints.

### 3.2 State machine

```text
states:
  S0_greet → S1_money → S2_people → S3_topics → S4_hours → S5_first_task
  → S6_template_offer → S7_visible_secret_setup → S8_shamir_ritual
  → S9_review_and_sign → S10_complete

transitions (normal path):
  S0_greet -- user_begin → S1_money
  S1_money -- answer_money → S2_people
  S2_people -- answer_people → S3_topics
  S3_topics -- answer_topics → S4_hours
  S4_hours -- answer_hours → S5_first_task
  S5_first_task -- answer_first_task → S6_template_offer
  S6_template_offer -- import_template → S7_visible_secret_setup
  S6_template_offer -- skip_template → S7_visible_secret_setup
  S7_visible_secret_setup -- secret_chosen → S8_shamir_ritual
  S8_shamir_ritual -- shards_printed → S9_review_and_sign
  S9_review_and_sign -- user_sign → S10_complete

escape transitions (any state):
  *_state -- user_skip → next_state (answer stored as null)
  *_state -- user_pause → paused
  paused -- user_resume → last_state
  *_state -- user_escape → S_partial_exit (persisted partial answers; user can re-enter)
```

### 3.3 Step-by-step with prompts

**S0 — greet**

```
Envoy (CLI):
  ┌──────────────────────────────────────────────┐
  │ 🫖  [your visible secret will appear here]   │
  │ Welcome to Envoy.                             │
  │                                               │
  │ I'm going to ask you 4 questions to         │
  │ understand your boundaries. Then I'll         │
  │ set up your visible secret and back up       │
  │ your trust vault. ~15 minutes.                │
  │                                               │
  │ Begin? [y/n]                                  │
  └──────────────────────────────────────────────┘
```

**S1 — money**

```
What's a fair monthly ceiling for what I can spend on tools and API calls?
Enter a dollar amount (e.g. 50, 100, 500), or SKIP.

>>>
```

Extraction: `monthly_ceiling_usd: int | null`. Compiled into `envelope.financial.per_month_ceiling_microdollars`.

**S2 — people**

```
Who should I never contact without asking you first?
Names, emails, or phone numbers. Separate with commas. Or SKIP.

>>>
```

Extraction: `blocked_contacts: list[str]`. Compiled into `envelope.communication.recipient_denylist`.

**S3 — topics**

```
What topics are off-limits for me to act on without your explicit okay?
Examples: "finances beyond groceries", "medical decisions", "communications with family".
Or SKIP.

>>>
```

Extraction: `blocked_topics: list[str]`. Compiled into `envelope.data_access.semantic_rules` (with classifier rules from `envoy-registry:data_access.*`).

**S4 — hours**

```
When am I *not* allowed to act on your behalf?
Examples: "after 8pm", "weekends", "during work meetings".
Or SKIP.

>>>
```

Extraction: `operating_hours: list[{day, from, to, tz}]`. Compiled into `envelope.temporal.blackout_windows` (and inferred allowed_windows).

**S5 — first task**

```
What's the first thing you'd love me to just *do* for you this week?
This is optional — it helps me calibrate my first Grant Moment to something you actually want.

>>>
```

Extraction: `first_task_intent: str | null`. Stored in Ledger as user's opening intent.

**S6 — template offer**

```
I can start from a template:
  [1] @terrene-foundation/freelancer-v3
  [2] @terrene-foundation/solo-founder-v2
  [3] @terrene-foundation/parent-household-v1
  [4] None — I'll author from scratch.

A template is a starting point; you can add your own constraints on top.
(Note: to reach DELEGATING posture, you need at least 3 of your own authored constraints.)
```

Extraction: `template_import: str | null`. Loaded from Foundation-Verified Envelope Library (local cache Phase 01; remote registry Phase 02+).

**S7 — visible secret setup** (per doc 09 T-018)

```
Let's pick your visible secret. Every Grant Moment and Ledger entry will show this.
If you see a dialog that's missing it, it's fake.

Choose an icon (random options):
  [1] 🫖    [2] 🦊    [3] 🌿    [4] 🧭    [5] 🐚
  [6] 🕯️   [7] 🪐    [8] 🍉    [9] 🎐    [10] custom

And a color:
  [1] teal  [2] amber  [3] violet  [4] forest  [5] custom

And a short phrase (max 16 chars, used as verification text):
  (e.g. "tea at dawn", "hello sovereign", "my own agent")

>>>
```

Stored in Trust Vault. Never leaves device. Rendered on every ritual dialog.

**S8 — Shamir ritual** — see §8 for the full ritual flow.

**S9 — review and sign**

```
Here's your envelope in plain language:

  Financial:
    - Monthly ceiling: $100
    - Per-call maximum: $5
  Temporal:
    - Allowed: weekdays 8am–8pm America/New_York
    - Blackout: weekends, nights after 8pm
  Communication:
    - Contacts allowed: jamie@work.com, family@home
    - Blocked: ex@former-partner.com
  Data access:
    - Clearance: Internal
    - Blocked topics: tax info, medical decisions
  Operational:
    - Tools allowed: read_email, send_email, read_calendar, web_search
    - Tools blocked: exec_code, shell

Authorship score: 5 (template imported, 5 novel constraints added — you can reach DELEGATING posture).

Sign + activate? [y/n]
```

**S10 — complete**
Envelope signed as `RoleEnvelope` (doc 03 §3.2); stored in Trust Vault. Ledger entry `envelope_created` written. User proceeds to normal operation in posture `SUPERVISED` (default for fresh envelope).

### 3.4 Duration budget

Target: 15 minutes. Breakdown:

- S0–S5: ~5 minutes (question answering).
- S6 (template): ~1 minute.
- S7 (visible secret): ~1 minute.
- S8 (Shamir): ~6 minutes (print 5 cards; user distributes later).
- S9 (review): ~2 minutes.

Users may skip non-essential prompts; minimum-path (template import + visible secret + Shamir) is ~8 minutes.

### 3.5 Persistence + resume

At every `user_answer` transition, state is persisted to Trust Vault. User can close the client; resume later with `envoy init --resume <ritual_id>`. Auto-resume suggested on next launch if a paused ritual exists.

### 3.6 Minimum-impact novelty feedback

Per doc 02 §14.7 + §14.8: if a user types an answer that compiles to a constraint semantically near-duplicate of a template constraint, the ritual surfaces:

```
That looks similar to an existing template constraint (~0.88 similarity).
It won't count toward your Authorship Score.

Want to phrase it differently?
  [1] "send_email blocked unless subject contains 'personal'"
  [2] Try again yourself.
  [3] Keep as-is (won't count; you can author more later).
```

---

## 4. Grant Moment — per-action consent

### 4.1 Purpose

A Grant Moment is a structured consent event for an out-of-envelope action OR for a first-time-action (doc 02 §19) OR for a velocity-limit breach OR for a composition-rule fire. Produces a signed Delegation Record.

### 4.2 State machine

```text
states: M0_construct → M1_render → M2_await_decision → M3_sign_or_decline → M4_complete

M0: runtime constructs ToolCallIntent + envelope check runs; if a Grant Moment is required (composition rule fires, first-time-action, velocity, etc.), proceed.
M1: render dialog in all active channels where principal is connected.
M2: wait for user decision on any channel; timeout 5 minutes default (configurable per envelope).
M3: if approve → sign Delegation Record + Phase A intent (doc 05 §6.1); if deny → Ledger entry `grant_moment_denied`; if modify → re-prompt with user-modified constraints.
M4: append Ledger entry; resume or halt action.
```

### 4.3 Dialog rendering

Every Grant Moment shows:

1. Visible secret (spoofing defense).
2. Proposed action (tool + argument summary).
3. Why it's asking (structural envelope violation? composition rule? first-time pattern? velocity raise?).
4. Consequence preview (budget impact, reversibility, recipient, data accessed).
5. Options:
   - **Approve once** — grants just this instance.
   - **Approve + author** — grants + adds to envelope as authored constraint (increments Authorship Score if novel+impactful).
   - **Deny** — records reason; optionally triggers envelope-tightening ritual.
   - **Modify** — user edits constraint inline.

Example dialog (Telegram):

```
🫖 [your teal / "tea at dawn" visible secret]

Envoy wants to:
  SEND EMAIL to jamie@work.com
  Subject: "weekly update — can we reschedule?"
  Body length: 320 chars
  Budget impact: $0.02 (Claude tokens)
  Reversible: YES (I'll hold in outbox for 60s)

Why asking: first-time action. I've never emailed jamie@work.com before.

  [Approve once]  [Approve + author "always OK to email jamie"]  [Deny]  [Modify]
```

### 4.4 Novelty-aware friction (doc 09 T-019)

Repeat patterns within envelope session → can batch:

```
I've already approved 3 send_email calls to jamie@work.com this week.

Would you like to pre-authorize this pattern in your envelope so I don't ask again?
  [Yes — add "send_email to jamie@work.com" allowed]  [Keep asking each time]
```

Novel patterns (unseen recipient, new dollar range, new tool) → require:

- 5-second read-delay before approve button enables.
- Double-tap approve.
- Cross-channel confirmation for high-stakes (>$X or > classification threshold).

### 4.5 Velocity-raise Grant Moment (doc 02 §3.1 velocity ratchet defense)

If the agent wants to RAISE a velocity limit (e.g. day ceiling from $50 → $100), it CANNOT be an inline Grant Moment. It is deferred to Weekly Posture Review (§6) OR to a cross-channel Grant Moment with a 24-hour cooling-off window:

```
I'd like to raise your daily spending ceiling from $50 to $100.

This is a velocity ratchet — I can't approve it inline. Instead:
  • If you agree, I'll schedule it for Sunday's Weekly Posture Review.
  • OR you can approve via a separate channel (your declared second channel: email).
  • Cool-off: 24 hours after second-channel confirm before it takes effect.

  [Schedule for Weekly Review]  [Send cross-channel confirm]  [Cancel]
```

### 4.6 Grant Moment timeout

Default: 5 minutes. If user doesn't respond, the Grant Moment times out and the action is refused (Ledger entry `grant_moment_timeout`). Agent reports: _"I waited 5 minutes; you were unavailable. I've noted this and will retry tomorrow if still relevant."_

### 4.7 Cross-principal Grant Moments (Phase 03 Shared Household)

If a proposed action affects BOTH principals (shared calendar, shared budget spend), Grant Moment requires BOTH principals' approvals:

- Primary principal's dialog fires first.
- On approve, secondary principal's dialog fires on their channel.
- Action executes only after BOTH signed.
- If second principal denies or times out → action refused.

Cooling-off for cross-principal high-stakes: 24 hours per doc 03 §9.2.

---

## 5. Daily Digest — morning ritual

### 5.1 Purpose

Every morning at user-chosen time, deliver a 2-minute summary of what Envoy did, declined, spent, and plans to do.

### 5.2 Schedule

User configures in Boundary Conversation (skippable — default 8am local time). Channel: user-chosen (default: first-connected channel).

### 5.3 Content template

```
🫖 Good morning. Here's yesterday (2026-04-21):

ACTIONS
  ✓ Drafted 3 emails (in outbox; reply to send):
    — jamie@work.com: rescheduling Monday's meeting
    — sam@contractor.io: invoice for April
    — family: grocery list reminder
  ✓ Booked Wed 2pm coffee w/ Alex
  ✓ Completed weekly expense rollup (attached)

REFUSALS
  ✗ Declined request to email ex@former-partner.com (out of envelope)

SPEND
  $0.46 of $50 monthly ceiling (1% used; 29 days remain)

PENDING
  → Grant Moment waiting: "share vacation dates with Alex?" (novel recipient)

TODAY
  → Following up on GitHub PR review backlog (within envelope; no approval needed)
  → Sunday: Weekly Posture Review scheduled

Anything to add?  [Reply yes/no/modify]
```

### 5.4 Interaction

- **Reply "no"** or don't reply → Envoy proceeds with planned actions.
- **Reply "yes" or modify** → extract user's modifications, apply.
- **Reply "skip digest"** → tomorrow skipped, user re-enables via `envoy digest on`.

### 5.5 Simplified form for low-engagement users

If user opens < 2 Digests/week for 3 weeks: Envoy offers to collapse Digest into a minimal "3-line summary" form or switch to event-driven (only fires on Grant Moment pending or budget > 80%).

### 5.6 Channel-adaptive

- **Email/Web** — full rich format with attachments.
- **Telegram/Slack/Discord** — message with inline quick-reply buttons.
- **SMS/WhatsApp** — compact 10-line form; replies via numeric quick-reply.
- **CLI** — full text on `envoy digest today`.

---

## 6. Weekly Posture Review — Sunday 90-second ritual

### 6.1 Purpose (Phase 03)

A ~90-second Sunday (or user-chosen day) ritual to:

- Review last week's action summary.
- Surface posture-recommendation (up or down based on behavior).
- Schedule pending velocity-raise Grant Moments (§4.5).
- Nudge authorship (T-023 mitigation): if Authorship Score is stagnant, prompt for new constraint.

### 6.2 State machine

```text
W0_intro → W1_summary → W2_posture_recommendation → W3_velocity_requests → W4_authorship_nudge → W5_sign_changes → W6_complete
```

### 6.3 Content template

```
🫖 Sunday Posture Review — week of 2026-04-15 to 2026-04-21

SUMMARY
  - 23 actions taken (3 declined, 0 escalated, 0 halted by rollback)
  - $1.20 spent of $50 monthly ceiling (2.4% used)
  - 4 Grant Moments approved; 1 denied
  - 0 envelope violations

POSTURE RECOMMENDATION
  Based on last week:
    → I'd raise email-drafting authority from SUPERVISED to DELEGATING
      (you approved all 12 Grant Moments for email this week anyway)
    → I'd lower calendar-booking authority back to TOOL
      (you modified 3 of 4 bookings I made)

VELOCITY REQUESTS
  → Raise daily spending from $50 to $100 (scheduled Mon; confirm?)

AUTHORSHIP
  Your Authorship Score is 5 (3 in first session + 2 added this week).
  Want to add more constraints? Some patterns I noticed:
    → You denied 4 web-fetch requests to known ad domains.
      I could add: "block http_fetch to *.ad-domain.com"

SIGN CHANGES?  [y/n]
```

### 6.4 Ritual discipline

- Skippable: user can `envoy review skip this-week`; Envoy defers by 1 week.
- If user skips 3 weeks in a row, Envoy suggests re-evaluating ritual cadence or disabling.
- Posture-rate-up Grant Moments are signed here, not inline.
- Auto-rubber-stamp defense: all posture RAISES require a 5-second read delay before approve button enables.

---

## 7. Monthly Trust Report — one-pager

### 7.1 Purpose (Phase 03)

End-of-month PDF + JSON export. Shareable artifact ("fitbit for your AI agent"). Contains:

- Full delegation graph (Sankey).
- Budget history (line chart).
- Actions taken / declined / escalated.
- Envelope violation attempts + attacker origin.
- Posture trajectory (slider history).
- Skill inventory + provenance + force_install flags.
- Classifier-version history (so user sees what changed).
- Cryptographic receipt hash.

### 7.2 Delivery

- User receives via chosen primary channel at month-end.
- Archived in `~/envoy/reports/2026-04.pdf`.
- JSON at `~/envoy/reports/2026-04.json`.
- Signed by user's Genesis key so the report is a verifiable artifact.

### 7.3 Shareability

User can share specific sections publicly (e.g. "delegation graph" for social transparency):

```
$ envoy report 2026-04 share --section delegation-graph --public

Output: https://pub.foundation-sync-node/alice-laptop-2026-04/delegation-graph.svg
         (public-key-verifiable receipt hash: sha256:...)
```

---

## 8. Shamir 3-of-5 ritual UX

### 8.1 Shard generation (during Boundary Conversation S8)

```
🫖 Let's back up your Trust Vault.

I'll split your private key into 5 paper cards using Shamir's algorithm.
You'll need any 3 to recover if your device is lost.

I recommend:
  → 3 cards in your own safes (home safe, bank safe-deposit box, parent's home)
  → 2 cards with trusted humans who'll keep them long-term

Anyone holding your cards can see you have an Envoy install.
Only choose "trusted humans" you trust with that knowledge.

Alternative: all 5 in your own safes (no trusted humans; more OPSEC).

  [1] Recommended (3 safes + 2 humans)
  [2] All 5 safes (no humans)
  [3] Custom (4-of-7, 2-of-3, etc)

>>>
```

On selection, Envoy generates 5 SLIP-0039 shards + commits hashes to Genesis Record (doc 03 §2.2 `shamir_threshold.shard_public_commitments`).

Envoy then presents each card to print:

```
═══════════════════════════════════════════════════
 CARD 1 of 5 — Shamir Recovery Card
 (Any 3 cards reconstruct your Trust Vault)
═══════════════════════════════════════════════════

 [24 BIP-39 words here]

 DO NOT write "Envoy" on this card.
 DO NOT write your name on this card.

 If you lose 3 or more cards, your vault is irrecoverable.
═══════════════════════════════════════════════════
```

Each card printed separately; user confirms each is printed before moving to next.

### 8.2 Shard distribution guidance

After printing, Envoy shows a distribution checklist:

```
Now distribute your 5 cards:

  □ Card 1 → home safe
  □ Card 2 → bank safe-deposit box
  □ Card 3 → parent's home safe
  □ Card 4 → trusted human #1 (name: _________)
  □ Card 5 → trusted human #2 (name: _________)

Tick each box as you complete. You can close this dialog and come back.
```

State persists. User can log distribution over days.

### 8.3 Recovery ritual

On new device, user runs `envoy recover`:

```
🫖 Recovering your Trust Vault.

Please enter the Shamir words from any 3 of your 5 cards.
(Cards can be entered in any order.)

Card #1:
>>> [24 words]

Card #2:
>>> [24 words]

Card #3:
>>> [24 words]

Reconstructing... ✓
Trust Vault restored.

Next: re-connect your channels (credentials live on the old device's OS keychain;
Shamir doesn't cover Connection Vault per §Credentials design).
```

### 8.4 Shard rotation ritual

When a shard-holder becomes unreachable (death, estrangement, relocation):

```
$ envoy shamir rotate

🫖 Rotating Shamir shards.

Current shards (as recorded):
  [1] home safe           [2] bank       [3] parent's home
  [4] trusted-human-alice [5] trusted-human-bob

Which card(s) do you want to rotate?
  [1] alice's card (she moved; I can't reach her)
  [2] bob's card

Selected: alice's.

Generating new 5-shard split (existing threshold: 3-of-5).
You'll print 5 NEW cards. The 4 non-alice old cards will remain valid for
another 30 days (grace period), then deprecated.

  [Continue]  [Cancel]
```

---

## 9. Posture slider UX

### 9.1 Surface

User-visible control in Web UI + `envoy posture` CLI + channel command `/posture` in bots.

```
Current posture: SUPERVISED

  PSEUDO       Read-only; explains what I would do.
  TOOL         Executes only what you ask, one action at a time.
  SUPERVISED   Plans multi-step; Grant Moment for each step.
  DELEGATING   Executes within envelope; reports in Daily Digest.  (requires Authorship Score ≥ 3)
  AUTONOMOUS   Full envelope authority; spawn sub-agents.         (requires Authorship Score ≥ 5)

Your Authorship Score: 5 → DELEGATING is unlocked; AUTONOMOUS unlocked.

  [Raise to DELEGATING]  [Raise to AUTONOMOUS]  [Lower]
```

### 9.2 Raising = Grant Moment

Raising posture requires a Grant Moment with 5-second read delay (habituation defense). Lowering is instant.

### 9.3 Annual revalidation (Phase 03)

Every 12 months, posture auto-decays one level; user re-authors ≥ 1 new constraint during Weekly Posture Review to restore.

---

## 10. Duress passphrase UX

Per doc 09 T-041 + doc 03 §10.

On unlock, user enters passphrase. Three possible paths:

- **Real passphrase** → real Trust Vault.
- **Duress passphrase** → honeypot Trust Vault (indistinguishable to attacker).
- **Wrong passphrase** → retry counter (after 10 wrong → panic-wipe if configured).

No user-facing error message reveals "duress mode active" — attacker sees what appears to be a normal unlock.

Duress passphrase is set during Boundary Conversation S7 optional step or later via `envoy vault set-duress`.

---

## 11. Localization + accessibility

### 11.1 Localization

All ritual prompts are stored as message templates keyed by ritual + step. Supported locales:

- Phase 01: en-US.
- Phase 02: en-GB, es-ES, de-DE, fr-FR, zh-CN, ja-JP.
- Phase 04: community-contributed additional locales.

Translation keys are stored in `envoy-i18n/<lang>/<ritual>.json`. User-authored content (envelope constraints in user's own words) remains in user's language; Envoy preserves exact text for signed records.

### 11.2 Accessibility

- **Screen readers** — all prompts have alt text; visible secret rendered as text description for blind users.
- **High-contrast mode** — color channel of visible secret adapts.
- **Keyboard-only navigation** — every interactive element reachable via Tab.
- **Audio cue** — Grant Moment in Web emits accessible chime.
- **Chunked content** — long Ledger entries split into readable segments for cognitive accessibility.

### 11.3 Channel-specific accessibility

- WhatsApp voice notes → transcription available in fallback text form.
- Telegram voice → same.
- SMS: strictly text; no media reliance.

---

## 12. Ritual engagement metrics + Monthly Trust Report

Metrics tracked (opt-in Heartbeat only):

- Completion rate of Boundary Conversation.
- Daily Digest open rate per week.
- Grant Moment response latency distribution.
- Weekly Posture Review completion rate.
- Monthly Trust Report open rate.
- Authorship Score trajectory.
- Posture trajectory.

Surfaced in Monthly Trust Report for user self-reflection. Aggregate-via-STAR to Foundation for BET-8 / BET-12 falsification.

**Kill-criterion trigger thresholds** (per doc 00 v3 §7):

- Daily Digest < 20% open rate for active users → signal for BET-8 refinement.
- Authorship Score median = 0 at 30 days post-install → signal for BET-12 refinement.
- Grant Moment approve-always rate > 80% → rubber-stamp signal.

---

## 13. Error + recovery

| Ritual state error                                            | Recovery                                                                                 |
| ------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Ritual state lost (vault corruption)                          | User re-runs ritual from beginning; old ritual_id archived                               |
| Channel disconnected mid-ritual                               | State persists; user resumes from any connected channel                                  |
| Timeout on Grant Moment                                       | Action refused; Ledger entry records; user can retry                                     |
| Shamir shard lost after distribution                          | Via `envoy shamir rotate`                                                                |
| Duress unlock accidentally entered by user (not under duress) | User exits honeypot via distinct escape phrase; real unlock on retry                     |
| Visible secret forgotten                                      | User runs `envoy vault reset-visible-secret` (requires real passphrase); sets new secret |

---

## 14. Cross-references

- **doc 00 v3** — canonical rituals, 5-level posture, Authorship Score thresholds.
- **doc 02 v3** — envelope compile pipeline (consumer of Boundary Conversation output), composition rules, first-time-action gate (trigger for Grant Moments), velocity-raise ratchet defense.
- **doc 03 v1** — Trust Lineage signing for RoleEnvelope + Delegation Records produced by rituals, Shamir commitments, duress + key destruction paths.
- **doc 04** — Ledger entry format for ritual events (envelope*created, grant_moment*\*, posture_change, etc.).
- **doc 05** — runtime operations invoked by rituals (trust_sign, phase_a_sign_intent, etc.).
- **doc 07** — channel adapter contracts (per-channel rendering of ritual prompts).
- **doc 09 v3** — T-018 visible secret, T-019 habituation defense, T-040 coerced unlock, T-041 duress, T-093 velocity ratchet.
- **doc 11** — acceptance metrics (ritual completion rates).

---

## 15. Open questions for `/redteam`

1. **Boundary Conversation in non-English / non-Latin scripts** — state machine works, but some ritual nuances (e.g. "ratchet" metaphor) don't translate. Phase 02 localization pass with native-speaker user testing.
2. **Daily Digest attachment format** — PDF? Markdown? HTML? Per-channel preference?
3. **Monthly Trust Report public sharing format** — SVG + JSON? Include full action list or only aggregate? Privacy-layer per user preference.
4. **Grant Moment timeout 5 min** — too long for time-sensitive actions (e.g. stock trade) or too short for deliberation (e.g. major financial). Envelope-per-tool override.
5. **Duress escape for accidentally-entered duress** — §13 recovery implies a distinct escape phrase. Does revealing the escape phrase to an attacker compromise the duress defense? Decision needed.
6. **Shamir shard-holder death notification** — if shard-holder dies and user doesn't know, stale shard sits indefinitely. Proposal: periodic ritual (annually) reminds user to verify shard-holder contactability.
7. **Visible secret compromise** — if Trust Vault is compromised, visible secret leaks. Recovery: user rotates visible secret via `envoy vault reset-visible-secret`. Is there a way to detect compromise before user sees spoofed dialog?
8. **Channel-first accessibility** — WhatsApp / iMessage voice reliance for some users; what about blind users on voice-only channels?

---

**End of doc 01 v1. `/redteam` Round 1 next.**
