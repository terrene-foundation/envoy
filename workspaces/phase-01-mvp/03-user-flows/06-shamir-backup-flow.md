# Flow 06 — Shamir 3-of-5 paper-card backup + reconstruct

**Document role:** Phase 01 user flow #6 of 8 (shard 21 of /analyze). Describes both halves of the Shamir 3-of-5 paper-card ritual: (a) the **backup** half — generating 5 paper cards during the S8 step of Flow 02 (Boundary Conversation), and (b) the **reconstruct** half — using any 3 of the 5 cards on a fresh laptop to recover the Trust Vault. EC-5 is the acceptance gate: 3-of-5 reconstruct test passes for ALL C(5,3)=10 share combinations; an Envoy-generated SLIP-0039 share reconstructs successfully via a non-Envoy tool (`python-shamir-mnemonic` minimum). Per `02-mvp-objectives.md` § 5, EC-5 is BLOCKING — no degrade-acceptable disposition.

**Date:** 2026-05-03 (shard 21 of /analyze; wave F user flows).
**Owning primitive shards:** 15 (Shamir 3-of-5 recovery: ritual coordinator, paper renderer, reconstruction CLI, plain-language errors), 5 (Trust store: master-key export hook, Genesis-record `shard_public_commitments` binding, recovered-key import), 8 (Boundary Conversation: hosts the backup ritual at S8 — see Flow 02 § S8 for the in-conversation surface), 14 (Connection Vault: NOT covered by Shamir per `specs/shamir-recovery.md` cross-references — channels re-pair after recovery).
**Exit criterion served:** **EC-5 (BLOCKING, no degrade-acceptable per `02-mvp-objectives.md` § 5)**. Acceptance: (a) all 10 share combinations reconstruct, (b) Boundary Conversation pauses for the ritual at least once, (c) cross-tool interop works against `python-shamir-mnemonic`, (d) reconstruction failure produces a clear-language error message — not a binary-data dump.
**Communication discipline:** Plain language per `rules/communication.md`. Reconstruction-failure messages MUST NOT surface raw `MnemonicError` traceback or byte-level dumps (per shard 15 § 3.3 — explicit `rules/communication.md` MUST NOT).

---

## 1. Persona & context

**Backup half persona:** A first-time user mid-Flow 02 at S8. They have just finished S7 (visible secret setup). They have never heard of "SLIP-0039" or "Shamir secret sharing"; they know they want their stuff to survive their laptop.

**Reconstruct half persona:** A user whose laptop was lost / stolen / died. They have a fresh laptop, just installed Envoy via `pipx install envoy-agent` (Flow 01). They have at least 3 of their 5 paper cards in front of them. They are anxious. They want this to work.

**Device + channel:** CLI on the laptop. Phase 01 ships Shamir paper rendering as plain-text + optional PDF (per shard 15 § 3.2; PDF is a Phase 01 stretch via `reportlab`/`pypdf`). No mobile / no remote / no cloud — paper IS the interop surface.

**Trigger:**

- Backup: automatic at Flow 02 S8 (mandatory step in first-run conversation per shard 8 § 5.5 — `ShamirRitualCoordinator.start_3_of_5(principal_id, master_key)`).
- Reconstruct: explicit user command `envoy shamir recover` per shard 15 § 3.3.

---

## 3. Happy path (plain language)

### 3A — Backup half (during Flow 02 S8)

This sub-flow is the user-visible surface of Flow 02 § S8. Re-stated here in standalone form because EC-5 (a) acceptance — the 10-combo reconstruct — is its own structural acceptance gate.

#### Step 1 — Distribution choice prompt

```
Last big thing — your backup.

If you lose this laptop tomorrow, I want you to be able to recover
your Envoy without trusting any company — including the Foundation.

I'm going to make 5 paper cards. Any 3 of those 5 cards put back
together will recover your Envoy keys.

The default we recommend:
  - 3 cards in places only you can reach (a safe, a deposit box,
    a hidden drawer at home)
  - 2 cards with people you'd trust with your life (parent, spouse,
    close friend, lawyer)

Other options:
  [A] All 5 cards in your own places (no other humans involved)
  [C] Custom (you tell me how to split them)

Which would you like? [DEFAULT/A/C]
```

The user picks. Per `specs/shamir-recovery.md` § Distribution guidance, default is 3-in-own-safes + 2-with-humans; option [A] is the recommended path for high-OPSEC users; option [C] is user-driven.

#### Step 2 — Card generation (≈500ms; cryptographic work)

Per shard 15 § 3.1:

1. The runtime calls `TrustStoreAdapter.export_master_key_for_shamir()` (shard 5 § 3.1 hook 6) to read master-key bytes.
2. `kailash.trust.vault.shamir.generate(secret=master_key, ritual=ShamirRitual(threshold=3, total_shards=5))` produces 5 SLIP-0039 mnemonic shards, each 24 words.
3. `shard_public_commitments = [f"sha256:{sha256(serialize_shard(s)).hexdigest()}" for s in shards]` is computed.
4. The commitments are bound to the user's Genesis Record per `specs/trust-lineage.md` line 27 + `specs/shamir-recovery.md` § Shard public commitments.
5. The in-memory master-key reference is **zeroized** per shard 15 § 3.1 step 6.

The user sees only:

```
   Generating your 5 backup cards...
```

#### Step 3 — Per-card render (≈30s of user time per card)

The CLI shows ONE card at a time. Per shard 15 § 3.2 — plain-text card with slot label, threshold reminder, mnemonic in 4 rows of 6 for transcription, checksum cue, sequence number, plain-language print/store instructions.

```
Card 1 of 5 — keep this somewhere safe.
You will need any 3 of these 5 cards to recover your Envoy keys
if your computer is lost.

Card 1 of 5 — Slot label: ANCHOR

  word-1   word-2   word-3   word-4   word-5   word-6
  word-7   word-8   word-9  word-10  word-11  word-12
  word-13  word-14  word-15  word-16  word-17  word-18
  word-19  word-20  word-21  word-22  word-23  word-24

Print this page now (Cmd-P / Ctrl-P), or copy the words carefully
onto a piece of paper. The very LAST word ("word-24") is a
checksum — if you transcribe it correctly, you'll know the
others are right too.

Press Enter when this card is safely stored.
```

Per `rules/communication.md` — plain language: "keep this somewhere safe" not "SLIP-0039 mnemonic shard, threshold=3, total=5". No "Envoy" label, no real names per H-06 fix (`specs/shamir-recovery.md` § Card format).

If the user can't print, the system offers a temp PDF (option `[1]` in Flow 02 EC-D — `~/.envoy/.partial/shamir/<ritual_id>.pdf` mode 0600, deleted on user-confirm-printed) or hand-copy.

This loops 5 times.

#### Step 4 — Distribution checklist

```
Quick checklist — for each card, where did you put it?
(Type a short label only; I won't store the real names. If
something happens to a card, you'll know what slot it was in.)

Card 1 (ANCHOR):    Home safe
Card 2 (MOUNTAIN):  Bank deposit box
Card 3 (LIGHTHOUSE):Office desk drawer
Card 4 (COMPASS):   Mom's house
Card 5 (HARBOR):    Lawyer's office
```

Per shard 15 § 3.1 (H-06 fix), only the **opaque slot labels** ("ANCHOR", "MOUNTAIN", ...) persist to Trust Vault — never the real holder names. The real-name input goes to user's local memory; the labels are what Envoy stores.

#### Step 5 — Suspension cleared, S8 → S9

`Plan.suspension` is cleared (shard 8 § 3.3); the Boundary Conversation advances to S9.

### 3B — Reconstruct half (fresh laptop, Day-N catastrophe)

User's laptop is gone. They have a fresh laptop. They have at least 3 of their 5 cards.

#### Step 1 — Fresh install + recovery start

```
$ pipx install envoy-agent
$ envoy shamir recover
```

The command surfaces:

```
   Welcome back. I'll help you recover your Envoy keys.

   You'll need any 3 of your 5 backup cards. Have them ready.

   For each card, I'll ask you to type the 24 words. The very LAST
   word on each card is a checksum — if you mistype, I'll catch it
   right away. You'll know which card it is by the slot label
   (the word in caps at the top of the card, like "ANCHOR" or
   "MOUNTAIN").

   Ready? Press Enter to start, or Ctrl-C to leave.
```

#### Step 2 — Card 1 entry (≈90–180s of careful typing)

```
   Card 1 of 3 — slot label?
   (Type the slot label from the top of the card, e.g. ANCHOR)
```

User types `ANCHOR`. Per shard 15 § 3.3 step 1.

```
   Card 1 (ANCHOR) — type the 24 words.
   You can paste a whole line, or type one word at a time. Spaces
   or line breaks both work. I'll check the checksum when you're done.

   >
```

User types 24 words separated by spaces. The CLI shows the words it heard:

```
   I heard: ability academy ... vacuum young

   Does this match what's on your card? [Y]es, [E]dit, [N]o
```

User confirms. Per shard 15 § 3.3 step 2 (the L-03 fix surfacing per-card checksum failure at entry, NOT deferred to combine-time): the CLI runs the SLIP-0039 per-card checksum validator. On checksum success, advance to Card 2. On failure:

```
   Hmm, the words on Card 1 don't quite match. The very last word
   should match a checksum from the others. Did you transcribe
   one of them slightly wrong?

   Want to:
     [1] Re-enter Card 1 carefully
     [2] Skip Card 1 and try a different card (you'll need 3 cards
         total, so any other card is fine)
```

#### Step 3 — Cards 2 + 3 entry

Same flow per card. The CLI tracks `slot_label` per card to surface `ShardSlotLabelMismatchError` if the user re-enters the same slot.

#### Step 4 — Combine + verify (≈100ms of crypto, instant feel)

```
   I have 3 cards. Combining them now...

   Verifying against this Envoy install's expected fingerprint...

   Recovered.
```

Behind the scenes, per shard 15 § 3.3 steps 3–5:

1. `kailash.trust.vault.shamir.reconstruct(shards, passphrase=...)` produces the master key.
2. `Genesis.shard_public_commitments` is verified (read from the Trust Vault that ships with the fresh install OR — for first-time recovery on a fresh laptop with no Genesis yet — the user must supply a `trust-anchor.json` file out-of-band per Flow 07's same-channel approach). On mismatch, `CommitmentVerificationFailedError` raises (rationale: "the cards belong to a different Envoy install — or someone has tampered with them").
3. `TrustStoreAdapter.import_master_key_from_shamir(reconstructed)` seals the recovered key into a fresh Trust Vault.
4. The Connection Vault is NOT recovered — per `specs/shamir-recovery.md` cross-references "Connection Vault not Shamir-covered." User re-pairs each channel adapter via fresh credentials per Flow 05.

#### Step 5 — Re-pair channels prompt

```
   Recovery complete. Here's what just happened:

     - Your Trust Vault is back: your envelope, your visible secret,
       your Ledger.
     - Your channels (Telegram, Slack) need to be re-connected
       because their credentials lived separately on the old laptop's
       OS keychain.

   Want to start with re-connecting Telegram?

      [Y] Yes, walk me through Telegram now (`envoy channel add telegram`)
      [N] Not yet — I'll do channels later
```

Per `specs/shamir-recovery.md` cross-references line 62 + shard 15 § 3.3 step 6, channel re-pair routes through Flow 05 (channel onboarding).

---

## 4. Edge cases (≥3 required)

### EC-A — User has only 2 cards (`InsufficientSharesError`)

User entered Card 1 and Card 2; tries to skip to combine.

Plain-language UX (per shard 15 § 3.3 plain-language error renderer):

> "You need at least 3 cards to recover. You entered 2. Please find the missing cards and try again."

Recovery: per `specs/shamir-recovery.md` error taxonomy `InsufficientSharesError` (line 47). User finds another card and re-enters.

### EC-B — One card is from a previous backup (`RotationGracePeriodElapsedError`)

User has rotated their backup recently (`envoy shamir rotate` in past — Phase 02 ritual). Per `specs/shamir-recovery.md` § Rotation ritual (line 37), 4 of 5 old cards remain valid for a 30-day grace period after rotation, then deprecate. User has just gone past the 30-day grace period and is using a card from the old set.

Plain-language UX:

> "Card N is from a previous backup ritual. The 30-day grace period after rotation has passed. Please use a card from your current set of 5."

Recovery: per shard 15 § 3.3 error renderer + spec error `RotationGracePeriodElapsedError` (line 51). User finds a current-set card.

### EC-C — Cards belong to a different Envoy install (`CommitmentVerificationFailedError`)

Edge case: user finds cards from someone else's Envoy install (e.g., they accidentally grabbed their roommate's printout) AND the words happen to all checksum-validate (extremely rare statistically — but possible if the cards genuinely came from a SLIP-0039 install). The cards reconstruct to a master key, but the resulting key does NOT match this install's `Genesis.shard_public_commitments`.

Plain-language UX (per shard 15 § 3.3 plain-language error renderer):

> "The cards you entered are valid SLIP-0039 cards, but they don't match this Envoy install's expected fingerprint. This may mean the cards belong to a different Envoy install — or that someone has tampered with them. Recovery is refused. Contact support if this is unexpected."

Recovery: per spec error `CommitmentVerificationFailedError` (line 49) + shard 15 § 3.3 step 4. Recovery REFUSED — defense against counterfeit shard / social-engineering attack. Disposition is "Never" (security event).

### EC-D — Cross-tool interop check (EC-5 (c) acceptance gate)

Scenario: User has 3 of 5 cards and decides to verify with `python-shamir-mnemonic` on a different machine BEFORE attempting recovery on the new Envoy laptop (a paranoid-user-friendly verification path).

Plain-language UX:

```
$ pip install shamir-mnemonic
$ python -m shamir_mnemonic.cli combine
Enter mnemonic 1: ability academy ... vacuum young
Enter mnemonic 2: abandon ability ... young zone
Enter mnemonic 3: abuse academy ... vault zone
SECRET: 9aa67238ef21...
```

The user gets back the master-key bytes (hex). On the Envoy laptop the same 3 cards via `envoy shamir recover` produce a Trust Vault sealed with the SAME master-key bytes. This is the EC-5 (c) acceptance: an Envoy-generated SLIP-0039 share reconstructs successfully via a non-Envoy tool. Per shard 15 § 3.1 + `specs/shamir-recovery.md` § Algorithm, Envoy uses the same `shamir-mnemonic` reference implementation, so this interop is structurally guaranteed (Phase 01 disposition (b) — wrapper around the audited package).

Recovery: this is the SUCCESS case for EC-5 (c). Trezor SDK interop is a stretch goal per EC-5 acceptance line 80 ("Trezor SDK if accessible"); Phase 01 minimum is `python-shamir-mnemonic`.

### EC-E — Rate-limited recovery attempts (`RecoveryRateLimitedError`)

Scenario: An attacker (e.g., an estranged household member) is trying to brute-force the backup by entering different word combinations on the user's laptop while the user is away.

Plain-language UX:

> "You've tried recovery too many times in a short window. Please wait N minutes and try again. (This is to protect your keys from someone in your household trying many guesses.)"

Recovery: per spec error `RecoveryRateLimitedError` (line 50) + shard 15 § 3.3 plain-language error renderer. Phase 01 ships a per-principal recovery rate limit; rate exceeded → wait. Disposition is structural defense, not user-fault.

### EC-F — Card has "Envoy" label or real name on it (`EnvoyLabelOnCardWarning`)

Scenario: User-side mistake — they hand-wrote "Envoy backup card 3 — Mom" on the card they gave to Mom. If the card is found by an attacker, the attacker knows what it's for AND that Mom has another.

Plain-language UX (surfaces during a `envoy shamir audit` later — Phase 02 — OR if the user shows a card to Envoy mid-recovery):

> "This card has an 'Envoy' or person's name on it. For your safety, please re-print the card without these labels — anyone who finds the card should NOT be able to identify what it's for."

Recovery: per spec error `EnvoyLabelOnCardWarning` (line 53). This is an advisory warning, not a blocker. User re-prints.

### EC-G — Genesis record missing `shard_public_commitments` (`ShardPublicCommitmentMissingError`)

Scenario: User is recovering an OLD Envoy install (Phase 00 or pre-shard 15-binding install) where the Genesis Record does NOT carry `shard_public_commitments`. Phase 01 introduces this binding per shard 15 § 3.1 step 3.

Plain-language UX:

> "This Envoy install was created before the current safety check was added. Please run `envoy shamir migrate` to upgrade — you may need to re-shard your backup cards."

Recovery: per spec error `ShardPublicCommitmentMissingError` (line 55). Phase 02 ships the migrate ritual; Phase 01 surfaces the warning and the user-side workaround is to recover via the legacy path (no commitment verify) and then re-shard.

### EC-H — Crypto-lib audit not landed (release gate, never user-surfaced)

Scenario: Phase 00 crypto audit on the SLIP-0039 implementation has not landed. Per `specs/shamir-recovery.md` line 15 mandate.

Plain-language UX: NEVER user-surfaced in production. Per shard 15 § 3.3 error mapping table, `CryptoLibAuditMissingError` is a release gate — Phase 01 ship is BLOCKED until the crypto audit completes. The user only ever sees this in a debug log; the release artifact never ships with the audit gate open.

---

## 5. Underlying primitives

| Step                              | Primitive (shard)                            | What runs                                                                                                       |
| --------------------------------- | -------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Master-key export                 | shard 5 § 3.1 hook 6 + shard 15 § 3.1 step 1 | `TrustStoreAdapter.export_master_key_for_shamir()` reads bytes from sealed Trust Vault region                   |
| Shard generation                  | shard 15 § 3.1 step 2                        | `kailash.trust.vault.shamir.generate(secret, ritual=ShamirRitual(threshold=3, total_shards=5))`                 |
| Commitment binding                | shard 15 § 3.1 step 3 + shard 5              | `shard_public_commitments = [sha256(serialize_shard(s)) for s in shards]` written to Genesis Record             |
| Paper render                      | shard 15 § 3.2                               | `envoy.shamir.paper.render(shard, slot_label)` — plain text + optional PDF                                      |
| Distribution checklist            | shard 15 § 3.1 step 5 + spec H-06 fix        | Opaque slot labels ONLY persist to Trust Vault; real holder names NEVER stored                                  |
| Master-key zeroization            | shard 15 § 3.1 step 6                        | In-memory master-key reference deleted after shard generation                                                   |
| Per-card checksum validation      | shard 15 § 3.3 step 2 + spec L-03 fix        | SLIP-0039 per-card checksum surfaced at entry time, NOT deferred to combine-time                                |
| Combine                           | shard 15 § 3.3 step 3                        | `kailash.trust.vault.shamir.reconstruct(shards, passphrase=...)`                                                |
| Commitment verify                 | shard 15 § 3.3 step 4                        | Reconstructed key sha256-prefix matched against `Genesis.shard_public_commitments`; mismatch raises typed error |
| Master-key import                 | shard 5 § 3.1 + shard 15 § 3.3 step 5        | `TrustStoreAdapter.import_master_key_from_shamir(reconstructed)` seals key into fresh Trust Vault               |
| Connection Vault re-pair guidance | shard 15 § 3.3 step 6 + Flow 05              | User-driven re-pair of channel adapter credentials; Connection Vault explicitly NOT covered by Shamir           |
| Plain-language error renderer     | shard 15 § 3.3 + `rules/communication.md`    | All 9 typed errors mapped to plain-language strings; NO raw `MnemonicError` traceback ever surfaces             |

---

## 6. Acceptance criteria served

- **EC-5 (BLOCKING, no degrade-acceptable):** This flow is the EC-5 surface end-to-end.
  - **EC-5 (a)** (10-combo reconstruct): structurally satisfied because the Phase 01 implementation uses the audited `shamir-mnemonic` reference (per shard 15 § 2.2 disposition (b)); the 10-combo coverage is asserted by Tier 2 test `tests/integration/test_shamir_round_trip_all_10_combos.py` per shard 15.
  - **EC-5 (b)** (Boundary Conversation pauses for the ritual at least once): Flow 02 § S8 IS the structural pause point. The ritual is mandatory in the first-run flow per shard 8 § 3.3 (S8 cannot be skipped to advance to S9 — `ShamirRitualIncompleteError` is enforced).
  - **EC-5 (c)** (cross-tool interop): structurally satisfied because Envoy's wrapper IS `python-shamir-mnemonic`. Tier 2 cross-tool test against fresh `python-shamir-mnemonic` install asserts the Envoy-generated shares reconstruct via the standalone tool.
  - **EC-5 (d)** (clear-language error message, not binary dump): structurally satisfied by shard 15 § 3.3 plain-language error renderer; per `rules/communication.md` MUST NOT raw `MnemonicError` traceback / byte dump.
- **EC-9 strong relationship:** the trust-anchor file for the Independent Verifier (Flow 07) is recommended to be stored in the SAME paper-cold-storage location as the Shamir cards. The two flows compose: Shamir restores the Trust Vault; the trust-anchor file lets the user verify the Ledger of THAT Trust Vault. Together they form the user's full sovereignty ritual.

---

## 7. Failure modes & recovery

| Failure                                | What the user sees                                                                                                                                                                      | Recovery path                                                                                             |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Insufficient cards (EC-A)              | "You need at least 3 cards to recover. You entered N. Please find the missing cards and try again."                                                                                     | `InsufficientSharesError`; user finds more cards                                                          |
| Card mistyped — checksum fails         | "The words on Card N don't quite match. Did you transcribe them correctly? The last word is a checksum — if that's right, the others usually are. Try re-entering this card carefully." | `ShardChecksumFailedError`; per-card retry, NOT deferred to combine                                       |
| Commitment mismatch (EC-C)             | "The cards you entered are valid SLIP-0039 cards, but they don't match this Envoy install's expected fingerprint. Recovery refused."                                                    | `CommitmentVerificationFailedError`; refuse unlock; security event                                        |
| Rate-limited (EC-E)                    | "You've tried recovery too many times in a short window. Please wait N minutes and try again."                                                                                          | `RecoveryRateLimitedError`; structural defense                                                            |
| Slot label mismatch                    | "The card you entered has slot label X, but I'm expecting slot label Y for this position. Did you grab the wrong card? Check the label on the back."                                    | `ShardSlotLabelMismatchError`; user verifies                                                              |
| Rotation grace period elapsed (EC-B)   | "Card N is from a previous backup ritual. The 30-day grace period after rotation has passed. Please use a card from your current set of 5."                                             | `RotationGracePeriodElapsedError`; user finds current-set card                                            |
| Envoy/name label on card (EC-F)        | "This card has an 'Envoy' or person's name on it. For your safety, please re-print the card without these labels."                                                                      | `EnvoyLabelOnCardWarning`; advisory; user re-prints                                                       |
| Crypto-lib audit not landed (EC-H)     | (NEVER user-surfaced; release gate)                                                                                                                                                     | `CryptoLibAuditMissingError`; Phase 01 release gate; ship blocked                                         |
| Old install missing commitments (EC-G) | "This Envoy install was created before the current safety check was added. Please run `envoy shamir migrate` to upgrade — you may need to re-shard your backup cards."                  | `ShardPublicCommitmentMissingError`; Phase 02 migrate ritual                                              |
| Backup card destroyed mid-ritual       | "I haven't seen confirmation that all 5 cards are stored. We can't move on until they are — your backup is the most important thing."                                                   | Per Flow 02 § S8 EC-D, runtime offers PDF / hand-copy / pause; backup MUST complete before S9 can advance |

All recovery paths surface plain-language messages. NEVER raw traceback. NEVER byte-level dump. Per shard 15 § 3.3 + `rules/communication.md` MUST NOT.

---

## 8. Cross-references

- `workspaces/phase-01-mvp/01-analysis/15-shamir-recovery-implementation.md` § 3.1 (ritual coordinator), § 3.2 (paper renderer), § 3.3 (reconstruction CLI + plain-language errors)
- `workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md` § 3.1 hook 6 (`export_master_key_for_shamir`, `import_master_key_from_shamir`)
- `workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md` § 3.3 + § 5.5 (S8 ritual host)
- `workspaces/phase-01-mvp/03-user-flows/02-boundary-conversation-flow.md` § S8 (the in-conversation surface of Flow 06's backup half)
- `workspaces/phase-01-mvp/03-user-flows/05-channel-onboarding-flow.md` (post-recovery channel re-pair)
- `workspaces/phase-01-mvp/03-user-flows/07-ledger-export-flow.md` (trust-anchor file recommended to ride with the Shamir cards)
- `specs/shamir-recovery.md` § Algorithm, § Default threshold, § Distribution guidance, § Card format (H-06 fix), § Recovery flow (L-03 fix), § Rotation ritual, § Shard public commitments, § Error taxonomy
- `specs/trust-vault.md` § File format (Shamir-wrapped master key region), § Cross-references
- `specs/trust-lineage.md` § Schema GenesisRecord (shard_public_commitments)
- `rules/communication.md` MUST NOT (plain-language error rendering — never raw traceback, never byte dump)
- `rules/zero-tolerance.md` Rule 6 (Implement Fully — all 10 combinations MUST work, not "usually")
