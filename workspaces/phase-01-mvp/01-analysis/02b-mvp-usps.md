# 02b — Phase 01-Demonstrable USPs

**Document role:** CHARTER §47–59 lists 7 product USPs. Not all are demonstrable in Phase 01 — some require Rust binding (P02), mobile (P02), Foundation-Verified registry (P02), SKILL.md translator (P02), or Weekly/Monthly rituals (P03). This doc names exactly which USPs Phase 01 demonstrates, which it cannot, and what each demonstrable USP needs from the implementation deep-dives.

**Why this matters:** "USP" is the marketing-grade form of "BET" — a USP is the claim a real user can verify in their first week. If Phase 01 ships without the USP being demonstrable, the BET that USP rides on is unfalsifiable until later. Identifying the demonstrable subset NOW prevents Phase 01 marketing copy from over-claiming features that only exist in Phase 02+.

**Date:** 2026-05-03 (shard 2 of /analyze).
**Status:** DRAFT — gates Phase 01 README + landing-page copy when those land in Phase 02 distribution prep.

---

## 1. The CHARTER USP catalogue (§47–59)

| #   | USP (CHARTER §)                                            | One-line claim                                                                                          | First-shippable phase                                                  |
| --- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| U1  | Ease of install (§47–49)                                   | One-command install across macOS / Linux / Windows / cargo                                              | P02                                                                    |
| U2  | "What is the human for" = setting boundaries (§51)         | First launch IS a 15-minute Boundary Conversation, not a settings page                                  | P01                                                                    |
| U2a | Boundary Library (§51)                                     | Community-shared envelope templates                                                                     | P02 (Foundation-Verified) / P03 (Community)                            |
| U2b | Weekly Posture Review (§51)                                | 90-second Sunday ritual                                                                                 | P03                                                                    |
| U2c | Monthly Trust Report (§51)                                 | Shareable one-pager                                                                                     | P03                                                                    |
| U3  | The Envoy Ledger (§53)                                     | Hash-chained personal ledger; grep-able, diff-able, git-committable, cascade-revocable, shareable       | P01                                                                    |
| U4  | Foundation-stewardship + CC BY 4.0 methodology (§55)       | Foundation-stewarded, non-commercial, independent, forkable                                             | P01 (positionally; no feature gate)                                    |
| U5  | Python + Rust conformance via published test vectors (§57) | Both runtimes interchangeable under contract partition; users get same behaviour, different performance | P02 (needs both runtimes wired)                                        |
| U6  | Structural no-orphan guarantee (§59)                       | Build fails if a governance primitive lacks a call site                                                 | P01 (mechanical via `rules/orphan-detection.md` + Tier 2 wiring tests) |

## 2. Phase 01-demonstrable USPs

### U2 — Boundary Conversation as primary surface (P01 PRIMARY USP)

**Demonstrable how:** A new user runs `envoy init`, lands in a TUI Boundary Conversation, exits in ≤25min with a parseable `EnvelopeConfig`. The first conscious surface of the product is authoring boundaries.

**What this proves to a watcher:** Envoy is structurally different from Little Snitch (per-action approval) and from settings-page UX (governance buried). The first 15 minutes ARE governance authoring.

**Phase 01 implementation requirement:** Boundary Conversation primitive (shard 8) must:

- Run on `kailash-py` Kaizen `BaseAgent` with a scripted Signature
- Produce a parseable `EnvelopeConfig` that the Envelope compiler accepts
- Hit the 15min target P50 across the 3 acceptance-test users (per EC-1)
- Be runnable from any of CLI / Web / 6 messaging channels (per EC-7)

**BET rideshare:** BET-12 (governance-primary-surface palatability), BET-1 (authorship thesis), BET-3 (sovereignty as moat — the user authors _their_ boundaries, not consents to a vendor's).

**Risk to Phase 01 demonstration:** If Boundary Conversation shows up "too form-like" (filling in a settings-page in conversational disguise), the USP collapses to "wizard, but slower." The implementation deep-dive (shard 8) must specifically NOT design a wizard — the conversation must adapt to user input, surface trade-offs, and feel like authoring.

### U3 — The Envoy Ledger (P01 PRIMARY USP)

**Demonstrable how:** A user runs `envoy ledger export`. Output is human-readable + machine-parsable. A separately-codebased verifier (`envoy-ledger-verifier` package) reads the export and reports "verified" or names the tampered field. The user can `grep`, `diff`, `git commit` the exported ledger.

**What this proves to a watcher:** The audit trail is a first-class product surface, not a compliance afterthought. Auditability serves the user (forensics, sharing receipts), not regulators primarily.

**Phase 01 implementation requirement:**

- Envoy Ledger primitive (shard 6) writes hash-chained entries via EATP `TieredAuditDispatcher` against SQLite
- Independent verifier (shard 7) ships in a separate repo, written by a different agent in a different language ideally (Rust preferred per `rules/testing.md` Tier 3 cross-implementation logic; Python acceptable if Rust is out of scope)
- Export format is canonical, stable, documented (the verifier reads the spec, not the producer code)
- Tampering battery: any single-bit flip is detected; insertion / deletion / reorder is detected

**BET rideshare:** BET-5 (Ledger as daily artifact); part of BET-1 (authorship as agency — agency without proof is theatre).

**Risk to Phase 01 demonstration:** If the verifier shares ANY code with the producer (even a hash function constant), the demonstration is theatre — the verifier has implicit producer-trust assumption. The shard 7 deep-dive must explicitly enumerate and prove zero-shared-code.

### U4 — Foundation-stewardship + CC BY 4.0 methodology (P01 POSITIONAL USP)

**Demonstrable how:** Not a feature; a posture. Demonstrable from day 1 by:

- LICENSE file (Apache 2.0)
- NOTICE file (CC BY 4.0 spec citations)
- CHARTER prominent placement of Foundation governance
- README explicit cite of `rules/independence.md`

**What this proves to a watcher:** No single commercial entity owns or controls the product or specs. The Foundation is the stewardship body; anyone can fork, audit, re-implement.

**Phase 01 implementation requirement:** None new — this USP is positional, already shipped. Phase 01 must not regress (e.g. by accidentally introducing commercial entity references in the codebase that contradict `rules/independence.md`).

**BET rideshare:** BET-4 (Foundation stewardship as credibility asset).

**Risk to Phase 01 demonstration:** Mostly NULL — this USP rides on the existing CHARTER + NOTICE + LICENSE + independence.md framing. The risk is silent regression in the codebase: a `# Copyright Acme Corp` slipping into a source file, a third-party dependency bringing implicit commercial coupling. Mitigation: Phase 01 ship-gate includes a `gold-standards-validator` review per `rules/agents.md` § Quality Gates.

### U6 — Structural no-orphan guarantee (P01 ENGINEERING USP)

**Demonstrable how:** `/redteam` exit criterion (EC-6) verifies; CI pipeline (when added in Phase 01) runs the orphan-detection grep + Tier 2 wiring tests as a merge gate. Every primitive Envoy ships has a documented production call-site AND a Tier 2 integration test.

**What this proves to a watcher:** The "feature shipped" claim is mechanically verifiable, not "trust the changelog." The Phase 5.11 orphan failure mode is impossible by construction.

**Phase 01 implementation requirement:**

- Every shard 4–19 deep-dive identifies the Tier 2 wiring test for the primitive
- Build / test pipeline enforces orphan-detection grep at PR time
- Per `rules/facade-manager-detection.md`: every `*Manager` / `*Executor` / `*Store` / `*Registry` / `*Engine` / `*Service` exposed on a public surface has a Tier 2 test

**BET rideshare:** Indirectly all BETs — orphans make BET measurements meaningless because the surfaced primitive isn't actually exercised in production.

**Risk to Phase 01 demonstration:** The CI pipeline implementing this gate IS itself a Phase 01 deliverable that doesn't appear explicitly in the brief — adding to shard 19 (pipx distribution) or shard 20 (build-sequence plan).

## 3. Phase 01-NON-demonstrable USPs

### U1 — Ease of install (P01 PARTIAL ONLY)

**Why partial:** Phase 01 ships `pipx install envoy-agent` only. The CHARTER claim "`curl -sSf https://get.envoy.ai | sh` drops a single static binary. `brew install envoy-agent`. `winget install envoy-agent`. `cargo install envoy-agent`" is Phase 02 distribution work (per ADR-0001 phase-migration table).

**Phase 01 acceptable framing:** "Install via `pipx` for early-access; full one-command-install paths land Phase 02 distribution."

**What NOT to claim in Phase 01 marketing:** "Single static binary," "brew/winget/cargo," "zero-config first launch" (the runtime picker is P02).

### U2a — Boundary Library (P02 / P03)

**Why deferred:** Per ADR-0004, the Envelope Library tiers ship Phase 02 (Foundation-Verified) and Phase 03 (Community). Phase 01 supports envelope import-from-file only.

**Phase 01 acceptable framing:** "Phase 01 supports envelope authoring + import from local file; the Envelope Library opens Phase 02 (Foundation-Verified) and Phase 03 (Community)."

### U2b / U2c — Weekly Posture Review + Monthly Trust Report (P03)

**Why deferred:** Per ROADMAP §100–113, Phase 03. The weekly + monthly cadence rituals are part of the ritual layer that depends on multi-week Ledger data + multi-principal data model affordances.

**Phase 01 acceptable framing:** "Daily Digest ships Phase 01; Weekly Posture Review + Monthly Trust Report land Phase 03 once the Ledger has accumulated multi-week corpus."

### U5 — Python + Rust conformance (P02)

**Why deferred:** Phase 01 wires `kailash-py` only. `kailash-rs-bindings` integration is Phase 02 (per ADR-0001 phase-migration table). Without both runtimes wired, the conformance claim has nothing to compare.

**Phase 01 acceptable framing:** "Phase 01 ships the abstract `kailash-runtime` interface against which both runtimes will be tested in Phase 02; conformance vectors land at Phase 02 release gate."

**What MUST NOT be claimed in Phase 01:** "Both runtimes work today," "swap with one keystroke" (the swap CLI is Phase 02), "byte-identical parity verified" (no parity to verify with one runtime).

## 4. The Phase 01 USP demonstration strategy

Phase 01 ships **4 demonstrable USPs** (U2, U3, U4, U6) and **0 fully-non-demonstrable USPs** — every CHARTER USP is at least _positionally_ in scope, but only 4 are testable end-to-end at MVP scale.

Per `rules/communication.md` (plain-language outcome framing) and `rules/security.md` § "User-facing disclosure" sibling pattern: Phase 01 marketing copy MUST distinguish "shipping today" from "Phase N target." The CHARTER USP claims are aspirational across the full phase ladder; Phase 01 README + landing-page copy must cite the demonstrable subset honestly.

**Recommended Phase 01 USP marketing line** (for use in shard 19 packaging deliverables and any Phase 01 README updates):

> Envoy Phase 01 ships the four primary surfaces: Boundary Conversation (15-minute first-launch authoring ritual), the Envoy Ledger (hash-chained personal audit trail with independent verifier), Foundation stewardship (Apache 2.0 code + CC BY 4.0 methodology, fully forkable), and the structural no-orphan guarantee (every primitive has a hot-path call site and a Tier 2 wiring test). Single-binary distribution, the Envelope Library, the Weekly + Monthly rituals, and Python ⇄ Rust runtime swap arrive Phase 02–03.

This line is what shards 19–20 cite when producing Phase 01 packaging artifacts.

## 5. The "USP-not-tested" risk

A USP that ships but can't be verified at Phase 01 cohort scale is a USP whose underlying BET stays unfalsifiable. The 4 demonstrable USPs are the structural defence: each has a clear EC (Phase 01 exit criterion) that tests it, which falsifies a specific BET.

USPs U1, U2a, U2b, U2c, U5 stay aspirational through Phase 01. Their BETs (BET-3 trajectory awareness, BET-7 SKILL.md compatibility, BET-8 ritual cadence at week+month scale, BET-6 byte-identical parity) wait for the deferred phases.

## 6. Cross-references

- CHARTER USP source: `CHARTER.md` §47–59
- Phase 01 EC source: `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md`
- BET source: `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` §5
- Independence rule (U4 risk mitigation): `.claude/rules/independence.md`
- Orphan-detection rule (U6 mechanism): `.claude/rules/orphan-detection.md` + `.claude/rules/facade-manager-detection.md`
- Communication style (USP framing discipline): `.claude/rules/communication.md`
