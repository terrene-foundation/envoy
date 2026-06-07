# Flow 08 — Posture ratchet (Authorship Score → DELEGATING posture gate)

**Document role:** Phase 01 user flow #8 of 8 (shard 21 of /analyze). Describes the user-visible journey of the posture ladder: from PSEUDO at install-time, to TOOL after first authored rule, to SUPERVISED after a few, to DELEGATING (the structurally-meaningful "I trust Envoy enough to act without per-action approval inside its envelope" rung), and the ratchet-down case (cascade revocation triggered by demotion). The posture ratchet is the structural enforcement of the §2.3 category-move thesis — without it, posture transitions are theatre and BET-12 fails.

**Date:** 2026-05-03 (shard 21 of /analyze; wave F user flows).
**Owning primitive shards:** 9 (Authorship Score deterministic re-derivation from Ledger slice, PostureGate 5-step fail-closed enforcement, BET-12 cadence emitter), 5 (Trust store: `SQLitePostureStore`, posture history, cascade revocation on demotion), 6 (Envoy Ledger: `posture_change` entries, envelope_edit slice for re-derivation), 4 (Envelope compiler: envelope-version bump on transition), 10 (Grant Moment: Genesis-co-signed grant required for ratchet-up; cooling-off enforcement on enterprise transitions).
**Exit criteria served:** **Cross-cutting structural prerequisite per `02-mvp-objectives.md` § 3 row 3** — without posture gate enforcement, BET-12 (governance-primary-surface palatability) is unfalsifiable. Specifically gates EC-2 cascade-revocation acceptance (the cascade of grants issued under a higher posture), and contributes to EC-1 cohort observability (initial PSEUDO seed at S9 of Flow 02).
**Communication discipline:** Plain language per `rules/communication.md`.

**Phase-01 CLI-surface note (added 2026-06-07 — `/redteam` F1 disposition):** `envoy posture` is a single read-only command in Phase 01 (shows the current autonomy level); **`envoy posture promote/demote` are NOT Phase-01 subcommands**. Posture transitions happen programmatically through the authorship-gated `EnvoyPostureGate` ratchet (5-step fail-closed); the interactive `promote` / `demote` CLI surface lands in Phase 02. This storyboard describes the intended ratchet UX.

**Important UX caveat — timezone disposition (per `journal/0003-GAP-budget-ceiling-timezone.md`):** The cooling-off period on enterprise-tier transitions (`PostureCoolingOffActiveError` per `specs/posture-ladder.md` § Algorithm) is timezone-dependent. Phase 01 ships **Option A (UTC)** consistently across budget reset, daily digest, and posture cooling-off. A 24-hour cooling-off period that started at "Monday 9 AM Singapore time" is checked against UTC — the user-visible "still cooling off?" question depends on UTC clock, not local. § 4 (edge cases) below documents.

---

## 1. Persona & context

**Primary persona:** A user 1–4 weeks into using Envoy. They installed (Flow 01), completed the Boundary Conversation (Flow 02), wired channels (Flow 05), accumulated a Ledger of activity, made some Grant Moments (Flow 03), seen a few Daily Digests (Flow 04). Their posture has been climbing: PSEUDO → TOOL → SUPERVISED. They are now considering ratcheting up to DELEGATING — the rung where Envoy can take action inside the envelope WITHOUT a Grant Moment per individual action.

**Device + channel:** posture transitions surface on the user's primary channel because they are structurally high-stakes (they materially change the consent boundary). Per `specs/grant-moment.md` § primary-channel binding (line 92), high-stakes Grant Moments — and posture-ratchet ceremonies are by definition high-stakes — render ONLY on the primary channel.

**Trigger:** the user explicitly asks for the transition (`envoy posture promote`) OR the system surfaces an offer when the user is eligible (e.g., the Daily Digest mentions it). Per `specs/posture-ladder.md` § State-transition contract, ratchet-up requires (1) Authorship Score threshold, (2) Grant Moment co-signature by user's Genesis key, (3) envelope version bump, (4) cooling-off window not active.

---

## 2. Trigger

**Ratchet-up:**

1. User runs `envoy posture promote` from the CLI OR taps a "promote to DELEGATING" prompt that surfaces in their Daily Digest when they pass the Authorship Score threshold.
2. The `PostureGate.request_transition(...)` runs the 5-step enforcement per shard 9 § 3.2.
3. On approval, a `posture_change` Ledger entry is written (Genesis-signed, NOT runtime-signed per `specs/ledger.md` Entry types).
4. `SQLitePostureStore.set_posture(...)` + `record_transition(...)` update the posture state.
5. The `BET12CadenceEmitter` (shard 9 § 3.3) emits a cadence event for cohort-level observability.

**Ratchet-down (demotion):**

1. User explicitly demotes via `envoy posture demote` OR the system auto-demotes via kill-criterion / annual decay (Phase 02+ for auto-demote; Phase 01 ships user-driven only).
2. Demotion is permitted UNCONDITIONALLY per `specs/posture-ladder.md` § Ratchet-down (no Authorship Score threshold needed; no cooling-off; no Genesis grant required).
3. Cascade revocation hook fires per shard 9 § 3.2 (tenant-isolation Rule 3 hook): `trust_store_adapter.revoke(principal_id=..., agent_id=..., reason="posture_demotion", revoked_by=<principal_genesis_id>)`. Every DelegationRecord whose envelope was authored under the higher posture is cascade-revoked.

---

## 3. Happy path (plain language)

### 3A — Ratchet-up: PSEUDO → TOOL (the easy step)

After Flow 02 S10 the user is at PSEUDO with `authored_count = 5` (the 5 personal rules they authored during the conversation). Per `specs/posture-ladder.md` § State-transition contract, PSEUDO→TOOL requires `authored_count >= 0` (i.e., trivially satisfied at install-time). Phase 01 auto-promotes to TOOL after the first successful action.

User sees in their first Daily Digest:

```
   Posture: TOOL (you climbed one step)
```

No ceremony. The Authorship Score recompute (per shard 9 § 3.1) over the post-S9 Ledger slice produces `authored_count = 5`; the gate's 5-step check passes; the `posture_change{from: "PSEUDO", to: "TOOL"}` Ledger entry writes; `SQLitePostureStore` updates.

### 3B — Ratchet-up: TOOL → SUPERVISED (gentle nudge after a week)

User has been operating for a week. They've authored 1 additional rule via Approve+author (a Grant Moment with `decision: "approve_and_author"` from Flow 03). `authored_count` is now 6.

Per `specs/posture-ladder.md` § Per-tier semantics + § State-transition contract, TOOL→SUPERVISED needs `authored_count >= 1` (personal mode). Already satisfied. The Daily Digest includes a one-line offer:

```
   You've authored 6 rules. Want to climb to SUPERVISED?
   At SUPERVISED I can run a planned multi-step action and
   stop to ask you only at decision points (instead of asking
   you on every single tool call).

   [Y] Yes, climb to SUPERVISED   [N] Not yet   [W] What does this mean?
```

User taps `[Y]`. Per shard 9 § 3.2, the `PostureGate.request_transition(...)` runs:

1. Recompute `AuthorshipCounters` from the Ledger slice — `authored_count = 6`.
2. Verify the signed `metadata.authorship_score.authored_count` in the active envelope matches the recomputed value. (M-05 fix per `specs/authorship-score.md` § Stored vs recomputed.)
3. `N_required = 1` for TOOL→SUPERVISED personal; check `authored_count >= 1` — pass.
4. Verify Genesis-signed grant present on ratchet-up. (Phase 01 implementation: the Daily Digest's promotion offer wraps the user's tap in a Grant Moment that requests Genesis-key co-signature; the user re-types their visible secret to confirm.)
5. Verify cooling-off NOT active. (No prior transition within cooling-off window.)

On success, `posture_change{from: "TOOL", to: "SUPERVISED"}` writes to the Ledger; `SQLitePostureStore.set_posture(...)`; envelope version bumps via Envelope compiler (shard 4); BET-12 cadence emitter fires.

### 3C — Ratchet-up: SUPERVISED → DELEGATING (the structurally-meaningful step)

This is the key Phase 01 transition because DELEGATING is the rung where Envoy gets meaningful agency: it can act without per-action Grant Moments inside the envelope. Per `specs/posture-ladder.md`, personal-mode SUPERVISED→DELEGATING requires `authored_count >= 3`; enterprise-mode requires `authored_count >= 5` AND introduces a 24h cooling-off window.

Three weeks in, user has authored 4 rules. They run `envoy posture promote`:

```
$ envoy posture promote

   You're at SUPERVISED. The next step is DELEGATING.

   What changes:
     - Right now (SUPERVISED): I check in with you at every "decision
       point" inside a multi-step task — the moments where I'm
       choosing among options.
     - At DELEGATING: I check in only when I'm about to do something
       OUTSIDE the rules you've already written. Inside your envelope,
       I just go ahead.

   Why this matters: you'll see fewer interruptions, but the
   responsibility for what's inside your envelope shifts to your
   prior authorship. You said "no calls to BlockedCorp"? I won't
   ask, I just won't call them. You said "max $80/month"? I won't
   ask if I'm at $40, I just spend it.

   You've authored 4 rules. The threshold for DELEGATING is 3.
   You're eligible.

   To promote:
     [P] Promote to DELEGATING (this asks for your visible secret)
     [N] Not yet
```

User taps `[P]`. Per shard 10 (Grant Moment) + shard 9 § 3.2 step 4, the runtime issues a **Grant Moment specifically scoped to the posture transition** — the user must approve the transition with Genesis-key co-signature. The Grant Moment renders on the primary channel:

```
   anchor + deep blue + "salt for soup"

   You're about to climb to DELEGATING.

   This means I can take any action that fits your envelope without
   asking you first. Outside your envelope, I'll still ask.

   Type your phrase to confirm:  ____
```

User types their visible-secret phrase. Per `specs/posture-ladder.md` § State-transition contract step 2 (Genesis-key co-signature), the Grant Moment's signed result IS the posture-transition co-signature. M4 of the Grant Moment writes:

1. The standard `grant_moment` Ledger row with `decision: "approve_once"` (the transition is a one-shot grant).
2. A `posture_change{from: "SUPERVISED", to: "DELEGATING"}` Ledger row signed by Genesis key per `specs/ledger.md` Entry types.
3. The `SQLitePostureStore.set_posture(principal_id, agent_id, TrustPosture.DELEGATING)` per shard 9 § 2.2.
4. `SQLitePostureStore.record_transition(TransitionResult(...))` per shard 9 § 2.2.
5. Envelope version bumps (shard 4 § 5).
6. `BET12CadenceEmitter.emit(...)` for cohort-level cadence per shard 9 § 3.3.

User sees:

```
   Done. You're at DELEGATING.

   You'll notice this immediately — actions that fit your envelope
   will just happen. You can always demote (`envoy posture demote`)
   if it feels wrong, and I'll re-ask on every action again.
```

### 3D — Ratchet-down: DELEGATING → SUPERVISED (the cascade-revocation case)

Two weeks later, user is uncomfortable. Envoy did something inside the envelope that the user didn't expect (let's say a $40 payment to a recipient that was technically on the user's "trusted" list but the user had forgotten about). The user wants to step back to SUPERVISED.

```
$ envoy posture demote

   You're at DELEGATING. Stepping down to SUPERVISED means I'll
   start asking you at every decision point again.

   IMPORTANT: stepping down ALSO revokes any sub-grants I've issued
   to my own internal sub-agents under the higher posture. Per your
   Trust Lineage spec, that's how the chain stays clean — when YOU
   step down, your descendants step down with you.

   Right now, you have:
     - 2 sub-grants issued to a sub-agent for "weekly mail summary"
     - 1 sub-grant issued to a sub-agent for "auto-reply to Alice"

   Both will be revoked. You'll need to re-issue them at SUPERVISED
   if you still want them.

      [D] Demote and revoke (the safe choice)
      [Q] Quit, don't demote
```

User taps `[D]`. Per shard 9 § 3.2 (cascade-revocation hook) + shard 5 § 3.3 (`cascade_revoke`):

1. `posture_change{from: "DELEGATING", to: "SUPERVISED"}` Ledger row signed by Genesis key (no Authorship Score threshold required for ratchet-down per `specs/posture-ladder.md` § Ratchet-down).
2. `SQLitePostureStore.set_posture(...)` updates state.
3. `trust_store_adapter.revoke(principal_id=..., agent_id=..., reason="posture_demotion", revoked_by=<principal_genesis_id>)` cascade-revokes EVERY DelegationRecord whose envelope was authored under DELEGATING.
4. `kailash.trust.revocation.cascade.cascade_revoke` BFS-walks the lineage graph atomically per `specs/trust-lineage.md` line 85.
5. ONE `RevocationRecord` Ledger entry covering the entire cascade.
6. `BET12CadenceEmitter` fires the demotion cadence event.

User sees:

```
   Done. You're back at SUPERVISED. 3 sub-grants revoked.

   I'll start asking you at decision points again. If something
   should still be automatic, just tell me — I'll re-issue the
   relevant rules at this posture.
```

### 3E — Enterprise mode: cooling-off active

Scenario: Enterprise-mode user (Phase 02 surface; documented here for completeness because it's in the Phase 01 spec). Enterprise SUPERVISED→DELEGATING requires `authored_count >= 5` AND a 24h cooling-off window after any prior posture transition.

User attempts to promote within 24h of a prior transition:

```
$ envoy posture promote

   You moved from TOOL to SUPERVISED yesterday at 14:32 UTC.
   Enterprise mode applies a 24-hour cooling-off window between
   posture changes — that gives you a chance to live with the
   new posture before climbing again.

   You can promote in 7 hours (at 14:32 UTC tomorrow).
```

Per shard 9 § 3.2 step 5, `PostureCoolingOffActiveError` raises and the transition is REFUSED. Per the timezone caveat in this doc's intro, the cooling-off check is UTC-anchored in Phase 01.

---

## 4. Edge cases (≥3 required)

### EC-A — Authorship Score divergence (`AuthorshipScoreDivergenceError`)

Scenario: The user's stored `metadata.authorship_score.authored_count` (signed at envelope-sign time) does NOT match the recomputed value from the Ledger slice. Per `specs/authorship-score.md` § Stored vs recomputed (M-05 fix), the runtime detects the divergence and raises an audit alert.

Plain-language UX:

```
   Something doesn't add up — the count of rules I have signed in
   your envelope ($AUTHORED) doesn't match what your Ledger says
   you've authored ($RECOMPUTED).

   This is a security check (it's how I catch tampering). I won't
   promote you until we figure out which is right.

   Two possibilities:
     [1] Your envelope is out of date — re-sign with `envoy envelope refresh`
     [2] Your Ledger has been modified — verify with the independent
         verifier (Flow 07: `envoy ledger export` then `envoy-ledger-verify`)
```

Recovery: per shard 9 § 3.2 step 2 + spec error `AuthorshipScoreDivergenceError`. The transition is REFUSED. User runs Flow 07 (Ledger export + verify) to rule out tampering, then re-signs envelope.

### EC-B — Genesis-signed grant missing on ratchet-up

Scenario: User attempts a ratchet-up via `envoy posture promote --no-grant-moment` (a hypothetical flag a developer might try). Per `specs/posture-ladder.md` § State-transition contract step 2, ratchet-up REQUIRES Grant Moment Genesis-key co-signature.

Plain-language UX:

```
   Posture promotions need a Grant Moment so I can confirm with
   you using your visible secret. (This is how you'd catch a
   malicious app trying to silently promote me.)

   Run `envoy posture promote` (without flags) to do it the
   right way.
```

Recovery: per shard 9 § 3.2 step 4 + spec error `PostureGenesisGrantMissingError`. Transition REFUSED. User retries through the normal Grant Moment surface.

### EC-C — Cooling-off active (EC-A above) + timezone surprise

Scenario per the timezone caveat: enterprise user in Singapore (UTC+8) demoted at "Monday 9 PM local time" (= 13:00 UTC). They wake up Tuesday at 8 AM local (= 00:00 UTC) and try to re-promote. They EXPECT the cooling-off period to feel like ~11 hours (Monday 9 PM → Tuesday 8 AM local). Phase 01 anchors cooling-off in UTC, so the actual remaining time is `13:00 + 24h = 13:00 UTC Tuesday = 21:00 SGT Tuesday` — the user has 13 hours more to wait in real-time.

Plain-language UX:

```
   You demoted yesterday at 21:00 your time (13:00 UTC). The
   cooling-off window is 24 hours, anchored to UTC, so you can
   promote again at 13:00 UTC tomorrow — that's 21:00 your time
   tomorrow. You have 13 hours left.

   (Phase 02 will anchor cooling-off to your local time so this
   is less surprising.)
```

Recovery: per `journal/0003-GAP-budget-ceiling-timezone.md` Phase 01 disposition is Option A. The user-visible explanation surfaces the UTC anchor explicitly. Phase 02 ships Option B (user-local IANA timezone) so the surprise goes away.

### EC-D — Enterprise mode + AUTONOMOUS attempt

Scenario: Enterprise user attempts SUPERVISED→AUTONOMOUS or DELEGATING→AUTONOMOUS.

Plain-language UX:

```
   AUTONOMOUS posture isn't reachable in enterprise mode. Your
   organization's shared envelope structurally caps you at
   DELEGATING — that's a deliberate design decision in the
   Posture Ladder spec.

   If your individual envelope is personal mode (separate from
   the org's), you can still climb to AUTONOMOUS there. Talk
   to your admin.
```

Recovery: per shard 9 § 3.2 step 5 + `specs/posture-ladder.md` § Per-tier semantics ("AUTONOMOUS NOT reachable on shared templates"). REFUSED with `PostureEnterpriseAutonomousForbidden`.

### EC-E — Demotion succeeds even if Authorship Score is "fresh"

Scenario: User is at DELEGATING with `authored_count = 8` (well above the threshold of 3). They want to demote to SUPERVISED. The demote does NOT need an Authorship Score check.

Plain-language UX:

```
   You're at DELEGATING with 8 authored rules — well above any
   threshold. Stepping back to SUPERVISED?

   [Y] Yes, demote   [N] No
```

Recovery: per `specs/posture-ladder.md` § Algorithm `posture_change(current, target, evidence)` — "target<current always permitted." Authorship Score is irrelevant for demotion. Cascade revocation still fires.

### EC-F — Posture-store unavailable

Scenario: SQLite database file holding the PostureStore is locked / corrupted / on a network drive that just disconnected.

Plain-language UX:

```
   I can't reach the database that tracks your current posture.
   This is unusual — it's a local SQLite file. Possibilities:

     - Disk error / file locked by another process
     - File deleted by accident

   Until I can reach the file, I'm staying at the most recent
   posture I can remember. To investigate:
     ls -la ~/.envoy/trust-vault.bin
```

Recovery: per shard 9 § 3.2 fail-closed defaults — `PostureStoreUnavailableError` raises; transition REFUSED. The runtime continues to operate at the cached posture (last known); it does NOT silently default to a more permissive posture per `rules/security.md` § Fail-Closed Security Defaults.

### EC-G — Ratchet-up offer in Daily Digest declined; user stays at SUPERVISED for months

Scenario: User receives the SUPERVISED→DELEGATING offer every day in their Daily Digest. They keep tapping `[N] Not yet`. After 30 days the offer becomes annoying.

Plain-language UX:

```
   Want to keep seeing the "promote to DELEGATING" offer in your
   morning digest? You've declined it for 30 days.

   [K] Keep showing it (in case I change my mind)
   [H] Hide it for now (I'll mention it once a quarter instead)
   [P] Promote me to DELEGATING after all
```

Recovery: per shard 9 § 3.3 (BET-12 cadence emitter) + shard 11 § 3.2 item 8 (low-engagement tracker), the Daily Digest tracks offer-decline cadence. After 30 days of declines, the offer hides; surfaces once per quarter. User can manually re-enable.

---

## 5. Underlying primitives

| Step                              | Primitive (shard)                                | What runs                                                                                                                   |
| --------------------------------- | ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| Authorship Score recompute        | shard 9 § 3.1 + shard 6 § 4                      | `AuthorshipScore.recompute(envelope, ledger_slice)` — pure function over (envelope, ledger_slice); deterministic            |
| Stored-vs-recomputed compare      | shard 9 § 3.2 step 2 + spec M-05 fix             | Verify `metadata.authorship_score.authored_count` matches recomputed; mismatch → `AuthorshipScoreDivergenceError`           |
| Threshold check                   | shard 9 § 3.2 step 3 + `specs/posture-ladder.md` | `N_required` = 0/1/3/5 per (current, target, mode); `< N_required → PostureAuthorshipInsufficientError`                     |
| Genesis-signed grant verification | shard 9 § 3.2 step 4 + shard 10 § 3.2            | Grant Moment with `decision: "approve_once"` co-signs the transition; verifies user's visible secret                        |
| Cooling-off check                 | shard 9 § 3.2 step 5 + `specs/posture-ladder.md` | Last transition timestamp + 24h (enterprise only); UTC-anchored in Phase 01 per `journal/0003`                              |
| Enterprise AUTONOMOUS gate        | shard 9 § 3.2 step 5 + spec § Per-tier semantics | `PostureEnterpriseAutonomousForbidden` if mode=enterprise AND target=AUTONOMOUS                                             |
| `posture_change` Ledger emit      | shard 6 § 4 + `specs/ledger.md` Entry types      | Genesis-signed `posture_change` row; payload `{from, to, basis: "user_request"}`                                            |
| PostureStore update               | shard 9 § 2.2 + shard 5 § 4                      | `SQLitePostureStore.set_posture(...)` + `record_transition(TransitionResult(...))`                                          |
| Envelope version bump             | shard 4 § 5                                      | `EnvelopeCompiler.compile(...)` produces new envelope version with updated `metadata.posture`                               |
| Cascade revocation on demotion    | shard 9 § 3.2 (Rule 3 hook) + shard 5 § 3.3      | `trust_store_adapter.revoke(...)` → `kailash.trust.revocation.cascade.cascade_revoke(...)` BFS-walks descendants atomically |
| BET-12 cadence emit               | shard 9 § 3.3                                    | Per-transition cadence event with (from, to, principal_id_hashed, days_at_current_posture, authored_count_at_transition)    |
| Promotion offer in digest         | shard 11 § 3.2 + shard 9 § 3.3                   | Eligibility computed per Daily Digest render; offer line emitted when threshold satisfied + cooling-off clear               |

---

## 6. Acceptance criteria served

- **Cross-cutting structural prerequisite per `02-mvp-objectives.md` § 3 row 3:** "Authorship Score primitive + posture gate — without this, DELEGATING / AUTONOMOUS posture transitions have no enforcement and the §2.2 thesis collapses to 'consent to envelope'." This flow IS that primitive's user-visible surface.
- **EC-2 cascade-revocation contribution:** the demote sub-flow (3D) cascade-revokes DelegationRecords issued under the higher posture per shard 9 § 3.2 Rule 3 hook. EC-2's "cascade-revocation of any descendant grant when the originating grant is revoked" is satisfied for posture-driven revokes.
- **EC-1 cohort observability:** the BET-12 cadence emitter fires at every transition, populating the cohort observability surface that BET-12 (governance-primary-surface palatability) is structurally measured by. Without this hook in Phase 01, BET-12 is unfalsifiable.
- **BET-12 falsifiability:** if a Phase 01 cohort run shows users never climbing past PSEUDO/TOOL, OR climbing past DELEGATING and immediately demoting, the cadence emitter's data IS the falsification signal. Without the emitter, no signal.

---

## 7. Failure modes & recovery

| Failure                                  | What the user sees                                                                                                                         | Recovery path                                                                               |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| Authorship Score divergence (EC-A)       | "Something doesn't add up — the count of rules in your envelope doesn't match your Ledger. Run the verifier or refresh your envelope."     | `AuthorshipScoreDivergenceError`; transition REFUSED; user runs Flow 07                     |
| Insufficient authorship                  | "You've authored 2 rules. The threshold for DELEGATING is 3. Author one more rule (any Approve+author Grant Moment counts) and try again." | `PostureAuthorshipInsufficientError`; surface count + threshold                             |
| Genesis grant missing (EC-B)             | "Posture promotions need a Grant Moment with your visible secret. Run `envoy posture promote` without flags."                              | `PostureGenesisGrantMissingError`; user retries through normal surface                      |
| Cooling-off active (EC-C)                | "Last transition was at HH:MM UTC. Cooling-off ends in N hours."                                                                           | `PostureCoolingOffActiveError`; user waits; UX explains UTC anchor (Phase 01 caveat)        |
| Enterprise AUTONOMOUS attempt (EC-D)     | "AUTONOMOUS isn't reachable in enterprise mode. Talk to your admin."                                                                       | `PostureEnterpriseAutonomousForbidden`; structural cap                                      |
| Posture-store unavailable (EC-F)         | "I can't reach the posture database. Stay at most recent posture; investigate disk."                                                       | `PostureStoreUnavailableError`; fail-closed; runtime continues at cached posture            |
| Visible-secret mismatch on grant         | (Real Envoy refuses to render with mismatch — user trains during Flow 02 S7 to recognize spoofs)                                           | `VisibleSecretMismatchError` (shard 10); audit alert                                        |
| Demotion when DELEGATING idle for months | "You've been at DELEGATING for 90 days. Want to keep climbing, stay here, or step back?"                                                   | Annual decay (Phase 02+; ratchet-down auto-trigger); Phase 01 ships user-driven demote only |
| Sub-agent cascade revocation fails       | "I tried to revoke 3 sub-grants but 1 of them failed (database error). I've rolled back so nothing changed; please retry."                 | Per shard 5 § 6.1 `_rollback_chains`; demote retried; consistency preserved                 |

All recovery paths are user-driven AND fail-closed. Per `rules/security.md` § Fail-Closed Security Defaults, the runtime NEVER silently advances posture on error; it stays at the cached posture and surfaces the failure.

---

## 8. Cross-references

- `workspaces/phase-01-mvp/01-analysis/09-authorship-score-implementation.md` § 3.1 (deterministic recompute), § 3.2 (PostureGate 5-step enforcement), § 3.3 (BET-12 cadence emitter), § 5 (initial PSEUDO seed at S9 of Flow 02)
- `workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md` § 4 (`SQLitePostureStore` adapter), § 3.3 (cascade revocation)
- `workspaces/phase-01-mvp/01-analysis/06-envoy-ledger-implementation.md` § 5.1 (`posture_change` Ledger entry)
- `workspaces/phase-01-mvp/01-analysis/04-envelope-compiler-implementation.md` § 5 (envelope version bump on transition)
- `workspaces/phase-01-mvp/01-analysis/10-grant-moment-implementation.md` § 3.2 (Grant Moment Genesis-key co-signature for ratchet-up)
- `workspaces/phase-01-mvp/journal/0003-GAP-budget-ceiling-timezone.md` (timezone caveat — cooling-off period UTC-anchored in Phase 01; Option B per shard 22 deferred to Phase 02)
- `workspaces/phase-01-mvp/03-user-flows/02-boundary-conversation-flow.md` (initial PSEUDO seed at S9)
- `workspaces/phase-01-mvp/03-user-flows/03-grant-moment-flow.md` (Approve+author cumulates `authored_count` toward the next threshold)
- `workspaces/phase-01-mvp/03-user-flows/04-daily-digest-flow.md` (promotion offer surfaces in the Digest when eligible)
- `workspaces/phase-01-mvp/03-user-flows/07-ledger-export-flow.md` (resolution path for `AuthorshipScoreDivergenceError`)
- `specs/authorship-score.md` § Score computation, § Stored counters, § Re-derivation from the Ledger, § Stored vs recomputed (M-05 fix), § Posture-ratchet gate, § Error taxonomy
- `specs/posture-ladder.md` § Canonical enum, § State-transition contract, § Per-tier semantics, § Algorithm, § Error taxonomy
- `specs/trust-lineage.md` § Algorithms § Cascade revocation (descendant DelegationRecords revoked on demotion)
- `rules/security.md` § Fail-Closed Security Defaults
- `rules/communication.md` (plain-language framing throughout)
