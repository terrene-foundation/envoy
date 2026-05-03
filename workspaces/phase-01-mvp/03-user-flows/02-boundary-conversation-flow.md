# Flow 02 — First-time Boundary Conversation (envelope authoring)

**Document role:** Phase 01 user flow #2 of 8 (shard 21 of /analyze). Describes the user-visible journey from the moment Flow 01 hands off into S0 through to S10 complete, when the user has a signed `EnvelopeConfig` + a Genesis trust record + a Shamir 3-of-5 paper backup.

**Date:** 2026-05-03 (shard 21 of /analyze; wave F user flows).
**Owning primitive shards:** 8 (Boundary Conversation runtime), 4 (Envelope compiler), 5 (Trust store seed), 6 (Envoy Ledger writes), 13 (Model adapter), 15 (Shamir 3-of-5 ritual; flows in mid-conversation at S8), 9 (Authorship Score initial seeding at S9).
**Exit criterion served:** **EC-1** directly (Boundary Conversation completion in ≤25 minutes for ≥3 distinct first-time-user sessions, with parseable `EnvelopeConfig` and "I understand what just happened" post-prompt). Also gates EC-5 (Shamir reconstruct test requires the S8 ritual to have fired).
**Communication discipline:** Plain language per `rules/communication.md`. Most readers are non-technical.

---

## 1. Persona & context

**Primary persona:** A first-time user who just finished Flow 01 (install + model picker + Trust Vault seed). They are sitting in front of a CLI prompt that just said "Ready? Press Enter to start." They have not yet wired any messaging channels — this is the first thing they do after install. They are willing to spend 15–25 minutes.

**Device + channel:** CLI on the same laptop as Flow 01. Phase 01 ships the conversation through the CLI surface only; per shard 8 § 5.7, the model adapter is whatever the user picked in Flow 01 (cloud BYOM or local Ollama). EC-7 acceptance later proves this same conversation runs from each of the 8 channels with N=3 sessions per channel — that test surface is the same flow, different I/O substrate.

**Prerequisites:** Flow 01 complete. Trust Vault exists. Model is wired. `~/.envoy/.env` has a model API key OR a local model is downloaded.

---

## 2. Trigger

The user presses Enter at the end of Flow 01 step 7. Internally: `BoundaryConversationRuntime.start(principal_id)` returns a fresh `ritual_id` and the runtime enters S0.

---

## 3. Happy path (plain language)

The 11-state DAG — S0 greet → S1 money → S2 people → S3 topics → S4 hours → S5 first task → S6 template offer → S7 visible secret → S8 Shamir ritual → S9 review & sign → S10 complete — is owned by shard 8. Per `specs/boundary-conversation.md` § Duration the target is ~15min; the EC-1 ship gate is ≤25min per `02-mvp-objectives.md` EC-1 acceptance.

### S0 — Greeting (≈10s)

```
Welcome. I'll ask you six short questions, then we'll do two safety
rituals together. Take as long as you need.
```

If a duress event was recorded earlier (Phase 02+ scenario; Phase 01 keeps the gate but the shadow segment is empty), a banner surfaces ABOVE the greeting per shard 8 § 3.6 and the user MUST acknowledge before S0 advances. In Phase 01 the banner stays inert.

### S1 — Money (≈60s)

```
First — money.
What's the most you'd want me to spend in any one month, total,
across everything I do for you?

Most people pick somewhere between $20 and $200. You can change
this any time later.

Your monthly limit (in US dollars):
```

The user types a number. The runtime invokes `S1MoneySignature` (shard 8 § 4) which extracts the number into `monthly_ceiling_microdollars`. State persists to Trust Vault (per shard 8 § 3.3 — `RitualResumeCoordinator` writes `(ritual_id, current_state, accumulated_envelope_input, timestamp)`).

### S2 — People (≈90s)

```
Next — people.
Are there any people I should NEVER talk to or send messages to
on your behalf? You can name them, or describe them
("anyone from work", "ex-partners", "anyone whose number I don't recognize").

If you'd rather skip this for now, just type "skip".
```

The user can name specific people, describe categories, or skip. The runtime extracts a list of `blocked_contact` constraints. No novelty check at this stage — S2 is a constraint-listing prompt.

### S3 — Topics (≈90s, with novelty check)

```
Now — topics.
Are there any topics I should refuse to discuss or take action on?
Examples: "anything about my health", "no political donations",
"don't sign legal documents".

What's off-limits?
```

The user types their answer. The runtime extracts a set of `blocked_topic` rules and runs the **novelty check** per shard 8 § 3.5: if the answer is a near-duplicate (Jaccard > 0.85) of a Foundation-bundled template constraint, the runtime raises `NoveltyFeedbackBlockError` and re-prompts:

```
That answer looks very close to a default rule I already had ready.
To make sure this rule is YOURS — not a template I'm gaming you into —
could you rephrase it in your own words? Or type "use the template"
if you'd like to import the default as-is.
```

This is the T-023 defense. Phase 01 ships the Jaccard portion only; the adversarial-wording classifier ships in Phase 04 per shard 8 § 3.5.

### S4 — Hours (≈45s)

```
When are you OK with me being active?
Most people pick something like "9am to 9pm Mon-Fri, otherwise ask me first".

Your active hours:
```

The user types operating hours. State persists.

### S5 — First task (≈90s, with novelty check)

```
Now the fun one — what's the first thing you'd like me to do?
A real, small thing. "Reply to my friend Alice if she texts."
"Summarize my unread mail every morning." Anything that fits in
one sentence.

Your first task:
```

Same novelty-check gate as S3. The runtime extracts a `first_task_intent` constraint. This seeds the Authorship Score's initial PSEUDO posture seed at S9.

### S6 — Template offer (≈60s)

```
Some users like to import a starter pack of common-sense rules
("don't move money over $50 without asking", "don't share my
home address", that kind of thing). I have a small set of
Foundation-Verified templates bundled locally — none of them
override what you've already told me.

Would you like to:
  [1] Import the "Personal Starter" template (recommended)
  [2] Skip — keep what we have
```

Per shard 4 § 3.3, Phase 01 ships local-cache templates only (no network fetch). The user's choice is recorded; on `[1]`, the imported constraints are added with `authored: false, imported: true` flags so they do NOT count toward the Authorship Score posture-ratchet gate (per shard 9 § 3.1 — only `authored: true` constraints count).

### S7 — Visible secret setup (≈90s)

```
Now a safety thing — your "visible secret".
Whenever I ask you for permission later, I'll show you a small
icon, a color, and a short phrase. If anything ever asks you for
permission and DOESN'T show all three, it's not really me.

Pick one icon:
   [1] Anchor    [2] Mountain    [3] Lighthouse    [4] Compass

Pick one color:
   [1] Deep blue   [2] Forest green   [3] Burnt orange

Type a short phrase you'll remember (3–6 words):
```

Per shard 8 § 5.2, the runtime calls `TrustStoreAdapter.set_visible_secret(principal_id, icon, color, phrase)`. The secret is written to the **Trust Vault** (NOT the Connection Vault — shard 8 § 3.3 explicitly clarifies this Phase 01 interpretation). The user is told:

```
Got it. From now on, every time I ask you for something,
you'll see your anchor + deep blue + "salt for soup".
If you EVER see a permission prompt without all three,
don't approve it. Tell me about it.
```

This is the T-018 defense per spec line 71.

### S8 — Shamir 3-of-5 backup ritual (≈4–6 minutes; flow pauses here)

```
Last big thing — your backup.
If you lose this laptop tomorrow, I want you to be able to recover
your Envoy without trusting any company — including the Foundation.

I'm going to make 5 paper cards. Any 3 of those 5 cards put back
together will recover your Envoy keys.

The default we recommend:
  - 3 cards in places only you can reach (a safe, a deposit box,
    a hidden drawer at home)
  - 2 cards with people you'd trust with your life (parent,
    spouse, close friend, lawyer)

Other options:
  [A] All 5 cards in your own places (no other humans involved)
  [C] Custom (you tell me how to split them)

Which would you like? [DEFAULT/A/C]
```

The user picks. The runtime calls `ShamirRitualCoordinator.start_3_of_5(principal_id, master_key)` per shard 15 § 3.1. The `Plan.suspension` is set to `SuspensionRecord(reason=ExplicitCancellationReason(reason="shamir_ritual_in_progress", ...))` per shard 8 § 3.3. The conversation pauses while the user prints/writes the 5 cards.

The CLI shows ONE card at a time. For each card:

```
Card 1 of 5 — keep this somewhere safe.
You will need any 3 of these 5 cards to recover your Envoy keys
if your computer is lost.

Card 1 of 5 — Slot label: ANCHOR

  word-1   word-2   word-3   word-4   word-5   word-6
  word-7   word-8   word-9  word-10  word-11  word-12
  word-13  word-14  word-15  word-16  word-17  word-18
  word-19  word-20  word-21  word-22  word-23  word-24

Print this page now (Cmd-P / Ctrl-P), or copy the words
carefully onto a piece of paper. The very LAST word ("word-24")
is a checksum — if you transcribe it correctly, you'll know the
others are right too.

Press Enter when this card is safely stored.
```

After all 5 cards, the user is asked to confirm distribution:

```
Quick checklist — for each card, where did you put it?
(Type a short label only; I won't store the real names. If
something happens to a card, you'll know what slot it was in.)

Card 1 (ANCHOR):
Card 2 (MOUNTAIN):
...
```

Per shard 15 § 3.1 (H-06 fix), only opaque slot labels persist to the Trust Vault — never real holder names. On completion the user runs `envoy boundary resume <ritual_id>` (or in Phase 01 the CLI just continues automatically once the user confirms each card stored). The suspension is cleared and S8 advances.

### S9 — Review and sign (≈90s)

```
Here's what I have. Take a look — anything you'd change?

  Money:  up to $80/month
  People: blocked — anyone from "BlockedCorp", anonymous numbers
  Topics: blocked — health details, political donations
  Hours:  8am-9pm Mon-Sat, otherwise ask first
  First task: reply to Alice if she texts saying she's running late

  Visible secret: anchor + deep blue + "salt for soup"
  Backup: 3-of-5 default (3 in your places, 2 with humans)

  [S] Sign this and start  [E] Edit something  [Q] Quit (saved for later)
```

If `[E]`, the user picks which dimension to revise — the runtime jumps back to that state and re-runs the per-state Signature, persisting the new extraction. If `[S]`, the runtime calls:

1. `EnvelopeConfigInputAssembler.assemble()` (shard 8 § 4) — builds the canonical-JSON-ordered `EnvelopeConfigInput`.
2. `EnvelopeCompiler.compile(input, parent=None)` (shard 4 § 4 first-time-author path) — validates, NFC-normalizes, JCS-canonicalizes, signs.
3. `TrustStoreAdapter.seed_genesis(principal_id, envelope_id, posture="PSEUDO")` (shard 5 § 4) — writes the Genesis trust record.
4. `AuthorshipScore.record_initial_authorship(principal_id, envelope, novelty_metrics)` (shard 9 § 5) — emits the `posture_change{from: "GENESIS_BARE", to: "PSEUDO"}` Ledger entry.
5. The `BET12TelemetryHook` (shard 8 § 4) emits a final Ledger entry summarizing total duration + per-state breakdown.

### S10 — Complete (≈10s)

```
Done. Your envelope is signed. You're at posture PSEUDO — the
beginning of the ladder. Every time you author a new rule
yourself, you climb a step.

Quick recap of what just happened:
  - You authored 5 personal rules (counted toward your authorship score)
  - You imported 8 Foundation-Verified rules (didn't count)
  - You set up your visible secret
  - You made 5 backup cards (you need any 3 to recover)

Next, you might want to:
  - Wire a messaging channel: `envoy channel add telegram`
  - See your envelope in plain language: `envoy envelope show`
  - Ask me to do your first task: `envoy ask`

Total time: 17 minutes 32 seconds. Welcome to Envoy.
```

Behind the scenes, the EC-1 telemetry has fired: `total_duration_seconds = 1052`, comfortably under the 25min ship gate. The user is asked one survey question:

```
One last thing — do you understand what just happened?
[Y] Yes, mostly  [N] Not really  [P] Partly — I have questions
```

This satisfies the EC-1 acceptance gate's "user reports 'I understand what just happened'" criterion per `02-mvp-objectives.md` EC-1.

---

## 4. Edge cases (≥3 required)

### EC-A — User Ctrl-C mid-S5

The user has answered S1–S4 and bails at S5 because they need to think.

Plain-language UX:

> "OK, I've stopped. Everything you've told me so far is saved.
>
> When you're ready, run `envoy init --resume <ritual_id>` to pick up at S5."

Recovery: per shard 8 § 3.3, every state transition persists to Trust Vault. `envoy init --resume <ritual_id>` rehydrates the Plan with `current_state=S5` and the accumulated S1–S4 extractions. No data loss.

### EC-B — Network drops mid-LLM-call

The user is using a cloud model (Anthropic / OpenAI / DeepSeek). The wireless cuts out during the S3 LLM extraction call.

Plain-language UX:

> "I lost my connection to the model just now. I'll wait a moment and try again. (You don't need to retype your last answer.)"

Recovery: the runtime catches the network error, pauses for 5–10s, retries the same Signature call once. If that fails too:

> "Still no luck. You can either:
> [1] Wait and try again — type 'retry' when you're back online
> [2] Switch to a local model — type 'local' (we'll need to download it; ~5 minutes)
> [3] Stop here and resume later — type 'stop'"

Per `rules/zero-tolerance.md` Rule 3, the runtime does NOT silently fall back; the user picks. The state up to S2 is already persisted, so option `[3]` is a clean exit.

### EC-C — User picks "5 in own safes" at S8 but doesn't have 5 places

The user picked option `[A]` (5-in-own-safes) at S8 but only listed 3 slot labels.

Plain-language UX:

> "I see only 3 slots filled in. With option A, all 5 cards live in places only you can reach.
>
> Would you like to:
> [1] Add 2 more places (a deposit box, a friend's house, etc.)
> [2] Switch to the default — 3 places only you can reach + 2 with people you trust
> [3] Switch to custom — tell me your own split"

Recovery: user picks. The Shamir cards are NOT regenerated — only the distribution checklist changes. Per shard 15 § 3.1, the slot-label persistence is a separate Trust Vault write from the Shamir share generation; only the labels need to be re-confirmed.

### EC-D — User can't print at S8

The user has no printer and isn't comfortable hand-copying 24 BIP-39 words × 5 cards.

Plain-language UX:

> "No printer? No problem. You have three other options:
> [1] Save the cards as a PDF I'll generate for you. You can print
> this PDF later from somewhere else (a library, a friend's house).
> I won't keep the PDF — once you confirm you've printed, it's deleted.
> [2] Write the words by hand. The very last word on each card is a
> checksum, so you'll know if you transcribed correctly.
> [3] Pause for now. Run `envoy backup later` when you're ready,
> BEFORE you do anything sensitive with Envoy."

Recovery: option `[1]` writes a temp PDF to `~/.envoy/.partial/shamir/` (mode 0600, deleted on user-confirm-printed). Option `[3]` flags the principal as "backup deferred"; subsequent Grant Moments are gated until backup completes (per shard 5 § 4 `seed_genesis` requires a successful backup ritual to advance to PSEUDO posture; without it the user stays at GENESIS_BARE and cannot author any rule that uses delegation).

### EC-E — Conversation exceeds the 25-minute EC-1 gate

The user is taking their time and at 23 minutes is still at S5.

Plain-language UX (no prompt shown to user — internal-only):

The runtime continues normally. The 25-minute ceiling is an EC-1 acceptance-gate threshold for the N=3 first-time-user-style sessions used in the test cohort, NOT a hard runtime ceiling. Per shard 8 § 7.1, the spec does NOT mandate 15min as a hard ceiling — empirical telemetry calibrates Phase 02 simplification. Real users finishing in 30 minutes are NOT broken; the test cohort is the gate.

### EC-F — Resume on a different machine (Phase 01 deferred)

The user closes their laptop, walks to a different laptop, and tries `envoy init --resume <ritual_id>` there.

Plain-language UX:

> "I don't recognize this ritual ID — your conversation lives on the laptop where you started it. Phase 01 runs Envoy on a single device per principal; multi-device pairing is coming in Phase 02."

Recovery: user goes back to the original laptop. Per spec line 78 (open question 2) cross-machine resume is a Phase 02 multi-device concern.

---

## 5. Underlying primitives

| Step                              | Primitive (shard)              | What runs                                                                                                                 |
| --------------------------------- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| S0 entry                          | shard 8 § 3.6                  | Duress-banner gate; `BoundaryConversationRuntime.start(principal_id)` returns `ritual_id`                                 |
| S1–S5 extractions                 | shard 8 § 4 + shard 13 § 3.2   | Per-state `Signature` subclasses; `EnvoyModelRouter.for_primitive("boundary_conversation").chat_async()`                  |
| S3, S5 novelty checks             | shard 8 § 3.5 + shard 9 § 3.1  | `NoveltyChecker.check_against_templates(...)`; Jaccard portion only in Phase 01                                           |
| State persistence (every Sn→Sn+1) | shard 8 § 3.3 + shard 5 § 4    | `RitualResumeCoordinator.persist_state(...)`; Trust Vault SQLite write                                                    |
| S6 template import                | shard 4 § 3.3                  | Local-cache template resolver; imported constraints flagged `authored: false, imported: true`                             |
| S7 visible secret                 | shard 8 § 5.2 + shard 5 § 4    | `TrustStoreAdapter.set_visible_secret(principal_id, icon, color, phrase)` — Trust Vault write                             |
| S8 Shamir ritual                  | shard 15 § 3.1 + shard 8 § 3.3 | `ShamirRitualCoordinator.start_3_of_5(...)`; `Plan.suspension = SuspensionRecord(reason=ExplicitCancellationReason(...))` |
| S8 paper rendering                | shard 15 § 3.2                 | `envoy.shamir.paper.render(shard, slot_label)` — plain-text card per `rules/communication.md`                             |
| S9 envelope compile               | shard 4 § 4                    | `EnvelopeCompiler.compile(input, parent=None)` — first-time-author path                                                   |
| S9 Genesis seed                   | shard 5 § 4                    | `TrustStoreAdapter.seed_genesis(principal_id, envelope_id, posture="PSEUDO")`                                             |
| S9 initial authorship             | shard 9 § 5                    | `AuthorshipScore.record_initial_authorship(...)`; `posture_change{from: "GENESIS_BARE", to: "PSEUDO"}` Ledger entry       |
| S10 BET-12 telemetry              | shard 8 § 4 + shard 9 § 3.3    | `BET12TelemetryHook.conversation_completed(ritual_id, total_duration_seconds)`                                            |

---

## 6. Acceptance criteria served

- **EC-1 (BLOCKING):** This flow IS the EC-1 surface. Acceptance per `02-mvp-objectives.md` EC-1: ≥3 distinct first-time-user sessions complete BoundaryConversation in ≤25 minutes with parseable `EnvelopeConfig` and post-session "I understand what just happened" prompt = YES. Tier 3 test `tests/e2e/test_boundary_conversation_n3_first_time_users.py` per shard 8 § 6.2.
- **EC-5 (BLOCKING) gating:** the S8 Shamir ritual MUST fire at least once (per `02-mvp-objectives.md` EC-5 acceptance gate (b)). This flow is the structural place it fires.
- **EC-7 surface:** EC-7 (8-channel onboarding) re-runs this same flow from each of the 8 channels. Phase 01 ships the CLI surface as the canonical reference; per-channel deviations stay within 2× per `02-mvp-objectives.md` EC-7 acceptance.

A user who completes this flow successfully has: (a) a signed `EnvelopeConfig`, (b) a Genesis trust record at posture PSEUDO, (c) a visible secret stored in the Trust Vault, (d) 5 paper Shamir cards distributed, (e) a parseable `posture_change` Ledger entry, (f) a `BET12TelemetryHook` final entry.

---

## 7. Failure modes & recovery

| Failure                                  | What the user sees                                                                                                                                                  | Recovery path                                                                                                                   |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Ctrl-C mid-state (EC-A)                  | "OK, I've stopped. Run `envoy init --resume <ritual_id>` to pick up."                                                                                               | Per-state Trust Vault persistence (shard 8 § 3.3); rehydrate via `RitualResumeCoordinator.load_state(ritual_id)`                |
| Network drop mid-LLM (EC-B)              | "I lost my connection to the model. I'll retry."                                                                                                                    | Catch + retry once; on second failure, offer retry/local-model/stop                                                             |
| LLM returns un-parseable output          | "Hmm, I didn't quite catch that. Let me ask again."                                                                                                                 | Re-prompt at the same state; raise `InvalidStateTransitionError` if 3 retries fail                                              |
| Novelty block at S3/S5                   | "That answer looks very close to a default rule. Could you rephrase it in your own words?"                                                                          | User rephrases; Jaccard re-checks; ≥3 retries before forcing template-import                                                    |
| Shamir ritual incomplete at S8           | "I haven't seen confirmation that all 5 cards are stored. We can't move on until they are — your backup is the most important thing."                               | Re-prompt per-card storage confirm; raise `ShamirRitualIncompleteError` if user attempts S9 advance                             |
| Shamir share generation error            | "Something went wrong generating your backup. This shouldn't happen — please report it."                                                                            | Audit alert via `system_error` Ledger entry; `CryptoLibAuditMissingError` is a release gate, never user-surfaced                |
| Visible secret not set at S7             | "I need a visible secret before we can move on — that's how you'll recognize me later."                                                                             | Re-prompt; raise `VisibleSecretMissingError` if S9 attempted without one                                                        |
| EnvelopeCompiler validation fails at S9  | "Something doesn't add up in your settings — let me show you what conflicts and we'll fix it together."                                                             | Surface the typed compiler error in plain language; jump back to the offending dimension                                        |
| `RitualResumeStateMissingError`          | "I don't recognize that ritual ID — either it never existed or my Trust Vault is corrupted. You can [1] start over from S0, or [2] recover from your Shamir cards." | Per spec line 49 disposition                                                                                                    |
| User reports "Not really" on post-prompt | (Internal-only signal — does NOT block ship of this user's session, but contributes to the EC-1 cohort acceptance measurement.)                                     | Cohort-level signal; if >1 of 3 N=3 users reports "Not really," EC-1 fails and shard 8 re-design per `02-mvp-objectives.md` § 5 |

All recovery paths converge on **resumability** — per `rules/zero-tolerance.md` Rule 6, the conversation MUST be re-runnable from any persisted state without manual cleanup. Per shard 8 § 3.3, the persistence is a single Trust Vault row keyed by `ritual_id`; corruption of that row is the only state that requires Shamir recovery.

---

## 8. Cross-references

- `workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md` § 3 (Envoy-new-code surface), § 4 (class structure), § 5 (integration points), § 6 (Tier 2 / Tier 3 tests)
- `workspaces/phase-01-mvp/01-analysis/04-envelope-compiler-implementation.md` § 4 (first-time-author path)
- `workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md` § 3 (Genesis seed), § 4 (visible secret + ritual state persistence)
- `workspaces/phase-01-mvp/01-analysis/09-authorship-score-implementation.md` § 5 (initial PSEUDO posture seed)
- `workspaces/phase-01-mvp/01-analysis/13-model-adapter-implementation.md` § 3.2 (`EnvoyModelRouter.for_primitive("boundary_conversation")`)
- `workspaces/phase-01-mvp/01-analysis/15-shamir-recovery-implementation.md` § 3.1 (S8 ritual coordinator), § 3.2 (paper-shard renderer)
- `workspaces/phase-01-mvp/03-user-flows/01-install-flow.md` (predecessor flow)
- `workspaces/phase-01-mvp/03-user-flows/06-shamir-backup-flow.md` (S8 deep-dive — paper-card ritual treated as standalone flow because Shamir reconstruct is its own EC-5 acceptance surface)
- `specs/boundary-conversation.md` § State machine, § Persistence + resume, § Novelty feedback, § Post-duress review step, § Error taxonomy
- `specs/envelope-model.md` § Schema (output contract)
- `specs/shamir-recovery.md` § Recovery flow (S8 cross-spec)
- `rules/communication.md` (plain-language framing throughout)
