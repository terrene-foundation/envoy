# Flow 03 — Grant Moment (out-of-envelope action → resolution)

**Document role:** Phase 01 user flow #3 of 8 (shard 21 of /analyze). Describes the user-visible journey from the moment Envoy detects an action that breaches the user's envelope, through the rendered consent dialog on a channel, through one of three resolution shapes, through the Ledger write, through the (optional) cascade revocation later. EC-2 is the acceptance gate: ALL THREE resolution shapes must execute end-to-end with cascade revocation working.

**Date:** 2026-05-03 (shard 21 of /analyze; wave F user flows).
**Owning primitive shards:** 10 (Grant Moment orchestrator + 3-resolution-shape state machine + cascade revocation), 4 (Envelope compiler — child-envelope compile on Approve+author and Modify), 5 (Trust store — DelegationRecord persistence + cascade BFS), 6 (Envoy Ledger — PhaseARecord, PhaseBRecord, grant_moment, envelope_edit entries), 16 (channel adapters — host the rendered dialog), 8 (Boundary Conversation — PlanSuspension bridge if a Grant fires mid-conversation; not a Phase 01 first-run scenario).
**Exit criterion served:** **EC-2 (BLOCKING)** directly — all three resolution shapes (Approve / Decline / Approve-with-Modification) execute end-to-end with cascade revocation working. Per `02-mvp-objectives.md` EC-2 acceptance gate: (a) ledger entries written + verifiable via independent verifier, (b) envelope state mutated correctly, (c) cascade-revocation of any descendant grant when the originating grant is revoked.
**Communication discipline:** Plain language per `rules/communication.md`.

---

## 1. Persona & context

**Primary persona:** A returning user who completed Flow 02 (Boundary Conversation) some hours or days ago. They have an active envelope at posture PSEUDO. They have wired at least one channel (say Telegram, from Flow 05) and possibly more. They have asked Envoy to do something — not in this flow but earlier — and Envoy is now mid-execution.

**Device + channel:** any of the 8 wired channels. The user's **primary channel** is what they designated during channel setup (Flow 05). High-stakes Grant Moments per `specs/grant-moment.md` § primary-channel binding (line 92) ONLY render on the primary channel; non-high-stakes can render on any active channel.

**Trigger not visible to user yet:** Envoy has begun executing a task and is about to call a tool that violates the active envelope (e.g., the user told Envoy "summarize my unread mail every morning" and a summary contains a $200 transfer request that would exceed the user's $80/month limit; OR Envoy received a request to message a contact on the user's blocklist; OR an action would touch a tool Envoy hasn't used before with this recipient).

---

## 2. Trigger

The `OutOfEnvelopeDetector` (shard 10 § 3.2 item 4) wraps every Kaizen tool-call dispatch. When the detector returns an `EnvelopeViolation`:

1. The Kaizen agent's tool dispatch is suspended (`PlanSuspension`-shaped).
2. The Grant Moment orchestrator is invoked: `request_grant_moment(violation, channel) → GrantMomentResolution`.
3. The orchestrator constructs `GrantMomentRequest` at M0 (canonicalized + signed by `delegation_key`).
4. M1 dispatches to the channel adapter's `render_grant_moment(request)`.
5. The user sees a dialog on the chosen channel.

The state machine `M0 construct → M1 render → M2 await decision → M3 sign or decline → M4 complete` is owned by shard 10 § 3.2 item 2.

---

## 3. Happy path (plain language) — three resolution shapes

The 4 spec decisions (`approve_once`, `approve_and_author`, `deny`, `modify`) map to the 3 EC-2 shapes per shard 10 § 3.2 mapping table. Each sub-flow below documents one shape.

### 3A — Shape: Approve (covers `approve_once` + `approve_and_author`)

**Scenario:** Envoy is about to send a $30 payment to a friend named Sam to settle a dinner bill. The user's envelope allows person-to-person payments to people on a "trusted" list, and Sam is on it — but the dinner bill ($30) would push this month's spend over $80 if combined with the $55 the user already spent. The detector flags it as a `financial` dimension violation.

The user sees on Telegram:

```
   anchor + deep blue + "salt for soup"

   Envoy wants to send $30 to Sam (dinner bill).

   This would put your monthly spend at $85, $5 over your $80 limit.

   Why I'm asking: you set the limit at $80/month. You can choose
   to allow this one, allow it AND raise your monthly limit, change
   the amount, or say no.

   [ Approve once $30 to Sam ]
   [ Approve & raise limit to $90/month ]
   [ Change amount ]
   [ No ]

   Reply within 5 minutes.
```

The visible secret line at top is the structural anti-spoofing defense (T-018). The 4 buttons map to the 4 spec decisions. Per `rules/communication.md`, plain language: "Approve once $30 to Sam" not "Approve `pay({recipient: 'sam', amount: 3000_microdollars})`".

**Approve once flow:**

1. User taps `[ Approve once $30 to Sam ]`.
2. Channel adapter constructs `GrantMomentResult{decision: "approve_once", ...}` (shard 16 § 3.2 item 13 renderer).
3. The result is canonicalized via the shared JCS+NFC pipeline (shard 10 § 3.2 item 6) and signed by the user's `delegation_key`.
4. M3 validates the signature; M4 writes:
   - `PhaseARecord` (intent envelope, pre-execution) per `specs/ledger.md` lines 366–380.
   - `DelegationRecord` via `TrustStoreAdapter.record_delegation(...)` (shard 5 § 4).
   - `grant_moment` Ledger entry with `decision: "approve_once"` per `specs/ledger.md` lines 350–364.
5. The orchestrator returns `GrantMomentResolution(shape=APPROVE, ...)`.
6. Envoy resumes and executes the payment.
7. Post-execution, the runtime writes `PhaseBRecord(outcome="success", ...)` linked by `intent_id`.
8. User sees on Telegram:
   ```
   Done — sent $30 to Sam. You're at $85 this month (over by $5).
   ```

**Approve-and-author flow:**

1. User taps `[ Approve & raise limit to $90/month ]`.
2. Channel adapter renders a confirmation:

   ```
   Just to be sure — raising your monthly limit to $90/month means
   I won't ask again next time you're a few dollars over $80. Is that OK?

      [ Yes, raise to $90 ]   [ Cancel ]
   ```

3. User confirms. The result is constructed with `decision: "approve_and_author", author_payload: {new_constraint: {...}, novelty_check_passed: true, minimum_impact_passed: true}`.
4. M4 writes the same artifacts as Approve-once PLUS an `envelope_edit` Ledger entry capturing the new constraint.
5. The Envelope compiler is invoked: `EnvelopeCompiler.compile(child_input, parent=current_envelope)`. The child envelope is monotonically tighter except along the dimension being raised — which is a controlled exception per `RoleEnvelope.validate_tightening` (shard 4 § 2).
6. The new envelope becomes active. Subsequent payments in the $80–$90 band do NOT fire a new Grant Moment.
7. User sees on Telegram:
   ```
   Done — sent $30 to Sam, and from now on your monthly limit is $90.
   ```

### 3B — Shape: Decline (covers `deny`)

**Scenario:** Same setup as 3A but the user decides not to approve.

```
   anchor + deep blue + "salt for soup"

   Envoy wants to send $30 to Sam (dinner bill).

   [ ... 4 buttons as above ... ]
```

**Decline flow:**

1. User taps `[ No ]`.
2. Channel adapter constructs `GrantMomentResult{decision: "deny", signature_by_delegator_hex: null, ...}` — **no key signing for Deny** per `specs/grant-moment.md` line 51 (the absence of a signature IS the signal).
3. M3 validates the no-signature shape; M4 writes:
   - **NO `DelegationRecord`** (per spec line 51).
   - **NO envelope mutation.**
   - ONLY a `grant_moment` Ledger entry with `decision: "deny"`.
4. The orchestrator returns `GrantMomentResolution(shape=DECLINE, delegation_record_ref=None, envelope_edit_ref=None)`.
5. Envoy abandons the action.
6. User sees on Telegram:
   ```
   Got it — I won't send that. The original message is still in your
   inbox if you want to handle it yourself.
   ```

The user can also reply with free text instead of tapping a button (e.g., "no, ignore that whole conversation with Sam for now"). Phase 01 ships button-tap as the canonical surface; free-text-reply parsing is Phase 02 reply-extension per `specs/daily-digest.md` § Open question 4 (similar question, similar Phase 02 deferral).

### 3C — Shape: ApproveWithModification (covers `modify`)

**Scenario:** Same setup as 3A but the user wants to send $20 instead of $30.

```
   anchor + deep blue + "salt for soup"

   Envoy wants to send $30 to Sam (dinner bill).

   [ ... 4 buttons as above ... ]
```

**Modify flow:**

1. User taps `[ Change amount ]`.
2. Channel adapter renders an inline input:

   ```
   How much should I send to Sam?

   $ ___ (current: $30)
   ```

3. User types `20`. Channel adapter constructs `GrantMomentResult{decision: "modify", modify_payload: {new_args_canonical: {recipient: "sam", amount: 20_dollars_in_microdollars}, new_args_canonical_hash: <sha256>}, ...}`.
4. The result is signed by `delegation_key` (Modify IS signed, unlike Deny — only Deny is unsigned per spec line 51).
5. M3 recomputes a fresh `intent_id` over the modified args (shard 10 § 3.2 item 3 — `ApproveWithModification` is the only shape that mutates the envelope structurally **without** requesting a persistent author rule).
6. M4 writes:
   - A fresh `PhaseARecord` with the new `intent_id` over modified args.
   - `DelegationRecord` via `TrustStoreAdapter.record_delegation(...)` covering the modified args (new `effective_envelope_hash`).
   - `grant_moment` Ledger entry with `decision: "modify"`.
   - `envelope_edit` Ledger entry capturing the action-scoped tightening.
7. The Envelope compiler is invoked with a tighter dimension constraint that captures the user's narrowing decision.
8. Envoy executes the modified action ($20 to Sam, not $30).
9. User sees on Telegram:
   ```
   Done — sent $20 to Sam. You're at $75 this month, $5 under your $80 limit.
   ```

### 3D — Cascade revocation (Day-N revoke of an earlier grant)

**Scenario:** A week later, the user opens the Daily Digest and sees the line:

```
You authored 3 grants this week. Tap any to review or revoke.

  • Mon: $30 to Sam (dinner) — Approved once
  • Tue: raised monthly limit to $90 — Authored rule
  • Thu: $50 to Sam (concert tickets) — Approved once  ← child of Mon's grant chain
```

The user realizes Sam isn't actually trustworthy and wants to revoke ALL grants involving Sam.

**Revoke flow:**

1. User taps the Tuesday entry (the "raised monthly limit to $90" — the rule that authored the new constraint).
2. CLI / channel surfaces:

   ```
   You're about to revoke the grant from Tuesday: "raised monthly
   limit to $90".

   This grant has 1 child grant that was made later under it:
     • Thu: $50 to Sam (concert tickets)

   If you revoke this, the child will also be revoked (the money
   already sent won't come back, but I'll mark them all as revoked
   in your Ledger so you'll see them and won't make the same mistake).

      [ Yes, revoke both ]   [ No, keep them ]   [ Show me more ]
   ```

3. User confirms. The orchestrator calls `CascadeRevocationOrchestrator.cascade_revoke(grant_id=tuesday_id, ...)` (shard 10 § 3.2 item 7).
4. The wrapper invokes `kailash.trust.revocation.cascade.cascade_revoke(...)` (shard 5 § 3.3) which BFS-walks the lineage graph and atomically marks every descendant as revoked within a single Trust Vault transaction (per `specs/trust-lineage.md` line 85).
5. ONE `RevocationRecord` Ledger entry is written covering the entire cascade (signed by Genesis key per `specs/trust-lineage.md` § Schema § RevocationRecord); payload includes `cascade_target_count`, `cascade_target_ids`.
6. `verify_cascade_complete(revocation_id)` confirms ALL descendants are in the result set.
7. User sees:
   ```
   Done. 2 grants revoked. From now on, no automatic actions
   involving Sam — I'll ask you about every one.
   ```

The cascade is **channel-agnostic** — if the Tuesday grant was approved on Telegram and the Thursday grant was approved on Slack, the BFS still reaches the Slack-originated child via `chain_parent_id` regardless of origin channel. This is exactly the EC-8 acceptance gate's "cascade revocation of a Day-1 grant correctly revokes a Day-6 child grant initiated from a different channel" structure (shard 10 § 6.2 + `tests/e2e/test_grant_moment_cross_channel_descendant_revoke_ec8.py`).

---

## 4. Edge cases (≥3 required)

### EC-A — Timeout at M2

Default timeout is 5 minutes per `specs/grant-moment.md` § Timeout (lines 102–104). The user is asleep / in a meeting / phone is dead.

Plain-language UX (next time the user opens any channel):

> "While you were away, I had a question I needed answered, but you didn't get to it in time:
>
> • Mon 11:42 — Sam asked for $30 (dinner). I waited 5 minutes and then stopped.
>
> You can review and decide what to do now, or just leave it."

Recovery: per shard 10 § 3.2 item 5 (timeout disposition), `GrantMomentExpiredError` raises and a `grant_moment` Ledger row writes with `decision: "expired"`. The action does NOT execute. The next session re-surfaces the missed prompt as a deferred decision; the user can re-trigger or dismiss. Per `specs/grant-moment.md` line 114 "Re-issue Grant Moment via runtime; cooldown applies if repeated within session".

### EC-B — High-stakes grant arrives on a non-primary channel

Scenario: User's primary channel is Telegram. A high-stakes Grant Moment arrives — say, a $5,000 payment that exceeds the user's `high_stakes_threshold_microdollars`. Per shard 10 § 3.2 item 9 (NoveltyClassifier), the request is classified `high_stakes` and `request.primary_only = true`.

The user happens to be active on Slack at the time. The Slack adapter's `render_grant_moment` checks `request.primary_only` against `self.is_primary` per shard 16 § 3.2 item 13 (renderer step 2) and finds the mismatch.

Plain-language UX on Slack:

> "Something important came up that needs your attention — but only on your primary channel (Telegram). Please check there. (This is a safety thing — for big decisions, I only ask on the channel you said you trust most.)"

Plain-language UX on Telegram (simultaneously):

```
   anchor + deep blue + "salt for soup"

   IMPORTANT — please read carefully (5 second pause)

   Envoy wants to send $5,000 to a recipient I haven't seen before.

   This is much larger than your usual transactions.

   [ ... 4 buttons appear after a 5-second read-delay ... ]
```

Recovery: per `specs/grant-moment.md` § Novelty-aware friction (T-019), high-stakes triggers the 5-second read-delay + double-tap + cross-channel confirm. The user reads carefully; if they want to approve, they tap once, then a confirmation arrives on a _second_ channel (e.g., a CLI desktop notification) asking them to confirm again. This is the cross-channel confirm step.

### EC-C — Channel hangs at M1

Scenario: User's primary channel is Telegram. Telegram's API is having an outage. The orchestrator dispatches `channel.render_grant_moment(request)` and the channel times out at the transport layer.

Plain-language UX (on whichever channel surfaces the failure):

> "I tried to ask you something on Telegram, but Telegram seems to be down right now. Should I:
> [1] Try again in 30 seconds
> [2] Try a different channel (Slack or CLI)
> [3] Drop the question and tell you next time you're online"

Recovery: per `specs/channel-adapters.md` § Error taxonomy `ChannelTransportError` (shard 16 § 3.2 item 3), the failure is logged as a `system_error` Ledger row and the orchestrator falls back per user choice. For non-high-stakes the orchestrator MAY auto-fall-back to a sibling channel; for high-stakes per primary-channel binding, the orchestrator MUST wait for the primary to recover OR surface the failure to the user via any non-primary channel as an info message ("there's a question waiting for you on your primary channel — please check there when it's back").

### EC-D — Visible secret mismatch (T-018 attack)

Scenario: A malicious app on the user's laptop spoofs a Grant Moment on the user's screen, hoping the user will approve. The spoof can't read the user's actual visible-secret bytes from the Trust Vault (sealed there at S7 of Flow 02).

Plain-language UX (the user's REAL Envoy never renders a fake; the user's vigilance is the defense):

> Whatever the spoof shows, it CANNOT show the user's real anchor + deep blue + "salt for soup" — because it can't read the Trust Vault. The user's training (from Flow 02 S7): "If you EVER see a permission prompt without all three, don't approve it."

Internal: per shard 10 § 3.2 item 6 (`SignedConsentBuilder` step 5), Envoy's REAL render path verifies the visible-secret bytes BEFORE dispatching to the channel; mismatch raises `VisibleSecretMismatchError` and refuses render. Tier 2 test `tests/integration/test_grant_moment_visible_secret_round_trip.py` (shard 10 § 6.1) is the structural defense.

### EC-E — Velocity-raise attempt within a session

Scenario: User has approved 4 small payments to Sam this morning ($5, $10, $15, $20). Now Envoy is asking about a 5th ($30), and the detector classifies the velocity as a possible "raise the per-day ceiling without thinking about it" pattern (T-093 R2-H4 per `specs/grant-moment.md` § Velocity-raise ratchet).

Plain-language UX:

> "You've approved 4 payments to Sam in the last 2 hours, totaling $50. This 5th one would push the day's total to $80.
>
> I'm not going to approve raising your day-limit inline today — that change deserves a proper conversation, not a yes/no in the moment. Two options:
>
> [1] Approve this $30 by itself (your day-limit stays the same)
> [2] Decline, and we'll talk about your overall pattern in your next Weekly Posture Review"

Recovery: per shard 10 § 3.2 item 9 (high-stakes detection) + spec § Velocity-raise ratchet, inline velocity-raise approval is REFUSED with `VelocityRaiseCoolingOffError` (per spec line 116). Only 24h-cooled-off cross-channel Grant Moment OR Weekly Posture Review path approves. Phase 01 ships the refusal; Phase 02 ships Weekly Posture Review.

### EC-F — Boundary Conversation pause: a Grant Moment fires DURING Flow 02 (not Phase 01 first-run)

Scenario: NOT Phase 01 first-run. Re-running Boundary Conversation in Phase 02+ (envelope edit) at S5 (first-task) the user describes a task that immediately needs a delegation that isn't in scope.

Plain-language UX: the conversation pauses; the Grant Moment renders on the user's primary channel; on resolution, the conversation resumes from the suspended `PlanSuspension` with the resolution as input.

Internal: shard 10 § 3.2 item 8 (`PlanSuspensionBridge`) is the typed-event channel between the two primitives. Phase 01 ships the bridge code but does NOT exercise it in the first-run flow per shard 8 § 3.3 (the Phase 01 first-run conversation does NOT issue Grant Moments — the user is authoring from scratch, no envelope to violate).

---

## 5. Underlying primitives

| Step                            | Primitive (shard)                     | What runs                                                                                                             |
| ------------------------------- | ------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Detect violation                | shard 10 § 3.2 item 4                 | `OutOfEnvelopeDetector.evaluate(...)` wraps every Kaizen tool-call dispatch; returns `EnvelopeViolation \| None`      |
| Classify novelty                | shard 10 § 3.2 item 9                 | `NoveltyClassifier` reads Ledger 7-day window; sets `novelty_class` and `primary_only`                                |
| M0 construct                    | shard 10 § 3.2 item 6                 | `SignedConsentBuilder` builds `GrantMomentRequest`; canonical-JSON; signs with `delegation_key`                       |
| M1 render                       | shard 16 § 3.2 item 13                | Per-channel `render_grant_moment(request)` translates wire format to channel-native UI                                |
| M1 primary-channel binding      | shard 10 § 3.2 item 5                 | Orchestrator checks `request.primary_only` against `channel.is_primary` pre-dispatch; raises `NotPrimaryChannelError` |
| M2 await                        | shard 10 § 3.2 item 5                 | `ChannelHandoff.dispatch(...)` awaits result_future with `request.timeout_seconds` (default 300)                      |
| M3 sign / decline               | shard 10 § 3.2 item 3                 | Validates signature shape per decision; maps to `ResolutionShape`                                                     |
| M4 (Approve_once) write         | shard 6 § 4 + shard 5 § 4             | `EnvoyLedger.append("PhaseARecord")` + `TrustStoreAdapter.record_delegation()` + `EnvoyLedger.append("grant_moment")` |
| M4 (Approve_and_author) compile | shard 4 § 4                           | `EnvelopeCompiler.compile(child_input, parent=current_envelope)`; `RoleEnvelope.validate_tightening`                  |
| M4 (Modify) recompute intent_id | shard 10 § 3.2 item 6                 | Fresh `intent_id = sha256(new_args_canonical_hash + nonce + envelope_hash)`                                           |
| M4 (Decline) write              | shard 6 § 4                           | ONLY `EnvoyLedger.append("grant_moment", decision="deny")` — NO `DelegationRecord` per spec line 51                   |
| Cascade revoke                  | shard 10 § 3.2 item 7 + shard 5 § 3.3 | `CascadeRevocationOrchestrator` wraps `kailash.trust.revocation.cascade.cascade_revoke(...)`; BFS walker; atomic      |
| Cascade Ledger emit             | shard 6 § 4                           | ONE `RevocationRecord` Ledger entry per cascade; payload has `cascade_target_count`, `cascade_target_ids`             |

---

## 6. Acceptance criteria served

- **EC-2 (BLOCKING):** This flow IS the EC-2 surface. All three resolution shapes (sub-flows 3A, 3B, 3C) MUST execute end-to-end. Cascade revocation (sub-flow 3D) is the (c) clause of the EC-2 acceptance gate.
- **EC-8 cross-channel cascade:** sub-flow 3D specifically tests the cross-channel descendant revocation scenario — a Day-1 grant on one channel revokes a Day-N grant from a different channel. Tier 3 test `tests/e2e/test_grant_moment_cross_channel_descendant_revoke_ec8.py` (shard 10 § 6.2).
- **BET-1 + BET-10 falsifiability:** if Grant Moments don't fire reliably, default-deny is theory only; if they fire but resolution is broken, the authorship loop has no closure. This flow's correct execution is the structural proof.

---

## 7. Failure modes & recovery

| Failure                                          | What the user sees                                                                                                                                    | Recovery path                                                                                                       |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Timeout at M2 (EC-A)                             | "While you were away, I had a question — you didn't get to it in time. Want to handle it now, or leave it?"                                           | `GrantMomentExpiredError`; `grant_moment` Ledger row with `decision: "expired"`; surface as deferred next session   |
| Channel hung (EC-C)                              | "Telegram seems to be down. Try a different channel, retry in 30s, or drop the question?"                                                             | `ChannelTransportError` Ledger row; user-driven fallback; no auto-fallback for primary-only requests                |
| Visible secret mismatch (EC-D)                   | (User's vigilance is the defense — REAL Envoy refuses to render with mismatch)                                                                        | `VisibleSecretMismatchError`; refuse render; audit alert via `system_error` Ledger entry                            |
| Non-primary attempt for high-stakes (EC-B)       | "Something important came up — please check your primary channel."                                                                                    | `NotPrimaryChannelError`; primary-only render only; non-primary surfaces info message                               |
| Velocity-raise inline (EC-E)                     | "I'm not going to approve raising your day-limit inline today — that deserves a proper conversation."                                                 | `VelocityRaiseCoolingOffError`; refuse inline raise; defer to Weekly Posture Review (Phase 02) or 24h cross-channel |
| Replay attack                                    | (User never sees this — orchestrator detects)                                                                                                         | `GrantMomentReplayError` per spec line 119; audit alert; ignore replay                                              |
| Back-pressure (>5 parallel grants)               | "I have a few questions waiting — please answer the older ones first."                                                                                | `BackPressureQueueFullError` per shard 10 § 3.2 item 1 (default ceiling = 5)                                        |
| Phase A orphan (no Phase B in 30d)               | At next session: "Last month I started something and never finished — can you tell me what happened? Should I retry, mark it failed, or investigate?" | `PhaseAOrphanResolution` Ledger entry per `specs/ledger.md` lines 399–414; user-driven disposition                  |
| Compiler refuses child envelope (Approve+author) | "That rule would conflict with something you set earlier — let me show you what conflicts."                                                           | `RoleEnvelope.validate_tightening` failure; surface compiler error in plain language; offer Modify path instead     |

All recovery paths converge on **a Ledger entry** — even refusal, even timeout, even error. Per `rules/zero-tolerance.md` Rule 3, no silent fallback; per shard 6 § 5.1 every Grant Moment outcome (success, decline, expire, error) is auditable.

---

## 8. Cross-references

- `workspaces/phase-01-mvp/01-analysis/10-grant-moment-implementation.md` § 3 (Envoy-new-code surface), § 4 (class structure), § 5 (integration points)
- `workspaces/phase-01-mvp/01-analysis/04-envelope-compiler-implementation.md` § 4 + § 5 row 2 (child-envelope compile on Approve+author / Modify)
- `workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md` § 3.3 (cascade revocation), § 4 (DelegationRecord persistence)
- `workspaces/phase-01-mvp/01-analysis/06-envoy-ledger-implementation.md` § 5.1 row "Grant Moment" (PhaseA/PhaseB/grant_moment/envelope_edit entry types)
- `workspaces/phase-01-mvp/01-analysis/16-channel-adapters-implementation.md` § 3.2 item 13 (per-channel Grant Moment renderer)
- `workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md` § 3.3 (Phase 01 first-run does NOT issue Grant Moments — explanation of EC-F)
- `workspaces/phase-01-mvp/03-user-flows/02-boundary-conversation-flow.md` (first-run authoring; no Grant Moments fire there)
- `workspaces/phase-01-mvp/03-user-flows/04-daily-digest-flow.md` (the Digest is where users see "your N grants this week — revoke any?")
- `specs/grant-moment.md` § Schema, § State machine, § Rendering, § Novelty-aware friction (T-019), § Velocity-raise ratchet (T-093 R2-H4), § Timeout, § Produced artifact, § Error taxonomy
- `specs/trust-lineage.md` § Schema § DelegationRecord, § Algorithms § Cascade revocation
- `specs/ledger.md` § Entry types `grant_moment` / `PhaseARecord` / `PhaseBRecord` / `PhaseAOrphanResolution`
- `rules/communication.md` (plain-language framing throughout the dialog text)
