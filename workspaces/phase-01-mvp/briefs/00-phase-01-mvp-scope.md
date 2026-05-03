# Phase 01 MVP — Scope Brief

**Document role:** This file is the user-input surface for Phase 01 `/analyze`. Without a `briefs/` file, agents have no anchor for what the user is asking for. The brief is _derived_ from authoritative sources frozen in Phase 00 because no greenfield user prompt exists — Envoy is a Foundation-stewarded product whose Phase 01 scope is already locked in `ROADMAP.md` §35–65, `CHARTER.md`, `DECISIONS.md` ADR-0001 + ADR-0009, the Phase 00 thesis at `workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md` §3.1, and the 37 frozen-v1 spec files at `specs/`.

This brief is therefore a _consolidation_, not a new ask. If the human disagrees with any consolidation here, Phase 01 /analyze should not proceed until the disagreement is resolved.

**Author:** synthesised by /analyze shard 1 from authoritative sources cited inline.
**Date:** 2026-05-03.
**Status:** DRAFT — single source the rest of /analyze chases against.

---

## What Phase 01 must ship

Per ROADMAP §35–65 + Phase-00-thesis §3.1:

> **Phase 01 MVP goal:** prove the ritual loop on 6 messaging channels end-to-end via the pure-Python runtime (`kailash-py`); Authorship Score posture-gate live. A single user onboards via any of 8 channels (CLI + Web + 6 messaging), operates for a week across them, backs up the vault on paper, exports a ledger, and verifies it independently via a separately-codebased reference verifier.

### Surfaces

- `pipx install envoy-agent` (interim distribution; Phase 02 moves to single static binary)
- `envoy init` — runs Boundary Conversation
- `envoy up` — starts the gateway
- `envoy boundaries` — opens the envelope for review/edit
- CLI channel (TUI chat)
- Web channel (local HTTP on `localhost`)
- 6 messaging channel adapters: iMessage (BlueBubbles), Telegram, Slack, Discord, WhatsApp, Signal

### Components (Python first, via `kailash-py`)

| Primitive                       | Source spec                                                 | Phase-00-frozen contract                                                                          |
| ------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Boundary Conversation agent     | `specs/boundary-conversation.md`                            | Kaizen `BaseAgent` with scripted `Signature`; outputs `EnvelopeConfig`                            |
| Grant Moment UI                 | `specs/grant-moment.md`                                     | CLI prompt + Web modal; signed-consent event                                                      |
| Daily Digest scheduler          | `specs/daily-digest.md`                                     | Kaizen scheduled agent; morning rendering                                                         |
| Envoy Ledger                    | `specs/ledger.md` + `specs/ledger-merge.md`                 | EATP `TieredAuditDispatcher` + SQLite + export CLI; hash-chained                                  |
| Envelope compiler               | `specs/envelope-model.md` + `specs/sub-agent-delegation.md` | PACT `RoleEnvelope` + `TaskEnvelope` + `intersect_envelopes()`                                    |
| Trust store                     | `specs/trust-vault.md` + `specs/trust-lineage.md`           | EATP `SQLiteTrustStore` or `FilesystemStore`                                                      |
| Connection Vault                | `specs/connection-vault.md`                                 | OS-keychain wrapper; direct API-key paste in Phase 01 (third-party OAuth deferrable per de-scope) |
| Budget tracker                  | `specs/budget-tracker.md`                                   | EATP `BudgetTracker` + `SQLiteBudgetStore`                                                        |
| Model adapter layer             | `specs/model-adapter.md`                                    | Kaizen `Delegate` → local Ollama / Claude / GPT / DeepSeek / custom OpenAI-compatible             |
| Shamir 3-of-5 recovery          | `specs/shamir-recovery.md`                                  | SLIP-0039 via `slip39` Python package                                                             |
| Authorship Score + posture gate | `specs/authorship-score.md` + `specs/posture-ladder.md`     | Score ≥ N (default N=3) gates DELEGATING / AUTONOMOUS posture                                     |
| Foundation Health Heartbeat     | `specs/foundation-health-heartbeat.md`                      | STAR/Prio + OHTTP + signed-consent telemetry                                                      |
| Independent ledger verifier     | derived from `specs/ledger.md`                              | Separately-codebased CLI tool that re-verifies a ledger hash chain                                |
| 6 channel adapters              | `specs/channel-adapters.md`                                 | iMessage (BlueBubbles), Telegram, Slack, Discord, WhatsApp, Signal                                |

### Exit criteria (per ROADMAP §59–65)

- 1 first-time user completes Boundary Conversation end-to-end
- 3 Grant Moments triggered and resolved correctly
- Daily Digest renders at scheduled time with real data
- Envoy Ledger exports a verifiable hash-chained log
- Trust Vault backup via SLIP-0039 Shamir works (3-of-5 reconstruct test)
- `/redteam` passes: spec-compliance AST/grep verified, 0 CRITICAL/HIGH findings, 2 clean rounds

---

## What Phase 01 inherits from Phase 00

**Frozen architecture:**

- 9 ADRs in `DECISIONS.md` (ADR-0001 through ADR-0009)
- 37 spec files in `specs/` (frozen-v1 after 6 redteam rounds)
- 12 BETs (Bet/Test pairs) in thesis-and-scope §5
- 5 product pillars in CHARTER

**Frozen vocabulary:**

- 5 constraint dimensions: Financial, Operational, Temporal, Data Access, Communication (canonical, no synonyms, per `terrene-naming.md`)
- 5 trust postures: PSEUDO → TOOL → SUPERVISED → DELEGATING → AUTONOMOUS
- 4 spec families: CARE / EATP / CO / PACT (CC BY 4.0 Foundation-owned)

**Pre-declared Phase 01 de-scope candidates** (per thesis §3.1, in order of preference if shard budget exceeded):

1. Reduce channel count from 6 to 3 (keep Telegram + Slack + Discord — bot-API clean; defer iMessage/WhatsApp/Signal legal-risk channels to Phase 02)
2. Defer Foundation Health Heartbeat to Phase 02 entry (Phase 01 falls back to Public + Library substrates per thesis §5.0)
3. Defer Connection Vault third-party-OAuth integrations to Phase 02 (Phase 01 supports direct API-key paste via OS-keychain wrapper only)

---

## What Phase 01 /analyze must produce

Phase 01 /analyze is NOT a re-derivation of architecture (Phase 00 froze that). It is _implementation architecture_ — how to actually wire the frozen specs into a shippable Python package.

The /analyze workflow steps re-interpreted for Phase 01:

| /analyze step                | Phase 00 status            | Phase 01 /analyze must produce                                                                                                            |
| ---------------------------- | -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Be explicit about objectives | DONE (thesis-and-scope)    | Map Phase 01 exit criteria to specific deliverables                                                                                       |
| Deep research                | DONE for architecture      | Implementation-level deep-dives per primitive (how to wire each spec to working code)                                                     |
| Strong product focus (USPs)  | DONE (BETs in thesis)      | Identify Phase 01-specific USPs (what's testable in MVP that proves the BETs)                                                             |
| Platform model thinking      | DONE (thesis-and-scope §6) | N/A — already covered                                                                                                                     |
| AAA framework                | DONE                       | N/A — already covered                                                                                                                     |
| Network behaviour features   | DONE                       | N/A — already covered                                                                                                                     |
| User flows                   | partially                  | Phase 01-specific flows: install, init, first Boundary Conversation, first Grant Moment, first Daily Digest, ledger export, Shamir backup |
| Plans                        | partial                    | Implementation plan per primitive; build sequence; integration test plan                                                                  |
| specs/                       | EXISTS, frozen             | Identify any Phase 01-implementation gaps in the frozen specs (additions, not edits — edits trigger MUST Rule 5b)                         |
| Red team                     | 6 rounds done in Phase 00  | New Phase-01-implementation redteam rounds against the new analysis                                                                       |

---

## Out of scope for Phase 01

Per ROADMAP §57 + thesis §3.1:

- Non-CLI/Web channels beyond the 6 listed (Matrix, Feishu, etc → Phase 04)
- Rust binary distribution (→ Phase 02)
- Mobile clients / Flutter (→ Phase 02)
- Multi-principal / Shared Household (→ Phase 03)
- Envelope Library registry (→ Phase 02 Foundation-Verified, Phase 03 Community)
- SKILL.md bulk ingest (→ Phase 02)
- Per-dimension posture slider (→ Phase 03)
- Weekly Posture Review + Monthly Trust Report (→ Phase 03)
- Voice channel + Apple Shortcuts + Calendar + browser/IDE extensions (→ Phase 04)

---

## Constraints + invariants Phase 01 must hold

1. **Pure-Python runtime only** (no `kailash-rs-bindings` integration in Phase 01; Rust binding integration is Phase 02 per ADR-0001 phase migration table)
2. **Abstract `kailash-runtime` interface MUST exist** even though only one implementation is wired (Phase 02 will wire the second)
3. **Authorship Score gate MUST be enforceable** before any Phase 01 release — DELEGATING / AUTONOMOUS unreachable without authored constraints (per BET-12 falsifiability — see thesis §5.12)
4. **Envoy Ledger MUST be independently verifiable** — separately-codebased reference verifier is a Phase 01 deliverable, not a Phase 02 one (per ROADMAP §63 exit criterion)
5. **Foundation Health Heartbeat MUST land** unless de-scoped per pre-declared sequence (per thesis §3.1 Phase 01 components list)
6. **Composite LICENSE / SPDX / counsel sign-off NOT required for Phase 01** — those gate Phase 02 distribution (Rust binary), not Phase 01 pipx distribution
7. **Trademark close NOT required for Phase 01** — `pipx install envoy-agent` works under codename through Phase 01 internal testing; trademark close required before Phase 02 public install surfaces
8. **All 37 frozen specs are authoritative** — no spec edits in Phase 01 unless a HIGH gap surfaces (which triggers MUST Rule 5b 37-sibling re-derivation; bundle if multiple)

---

## External-gate carryover from Phase 00

Phase 01 /analyze proceeds in PARALLEL with these external gates (none block analysis itself; all block Phase 02 release):

1. Foundation board endorsement of ADR-0009 runtime-pluggability model
2. USPTO + EUIPO + UK IPO trademark sweep close → final mark
3. Counsel sign-off on composite LICENSE + SPDX + export-control + compatibility statement
4. Launch-time §B re-runs (mailbox verify, CoC link, kailash-py PyPI name, namespace re-snapshot)

If any external gate fails (e.g. board declines, trademark blocks `Envoy*` family), Phase 01 analysis remains valid for the architecture but downstream Phase 02 distribution must re-plan.
