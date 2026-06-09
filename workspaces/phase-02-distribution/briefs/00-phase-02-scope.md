# Phase 02 — Distribution + Channels + Runtime Pluggability — Scope Brief

**Document role:** This file is the user-input surface for Phase 02 `/analyze`. Like the Phase-01 brief, it is a _consolidation_ of authoritative sources already frozen in Phase 00 / Phase 01 — NOT a greenfield ask. Envoy is a Foundation-stewarded product whose Phase-02 scope is locked in `ROADMAP.md` §74–108, `DECISIONS.md` ADR-0001/0005/0008/0009, the 37 frozen-v1 specs at `specs/`, and the Phase-01 "forest" deferral ledger (`workspaces/phase-01-mvp/.session-notes` + journals 0043/0046/0047/0048/0053).

If the human disagrees with any consolidation here, Phase-02 `/analyze` should NOT proceed until the disagreement is resolved.

**Author:** synthesised from a 4-agent parallel harvest of every `Phase 02` commitment across the spec corpus + ADRs + Phase-01 journals (per `rules/agents.md` § Parallel Brief-Claim Verification). Every commitment below carries a `file:line` citation.
**Date:** 2026-06-08.
**Status:** BLESSED 2026-06-08 — `/analyze` proceeding.

> **⚠️ Corrections applied post-blessing:** the 6-agent deep-dive sweep found that several spec citations this brief faithfully consolidated are stale (phantom). Most material: Phase-01 shipped **5 of 8** channel surfaces (NOT 8 — WhatsApp/iMessage/Signal are greenfield), and `RuntimeBackendNotWired` does not exist (real: `Phase02SubstrateNotWiredError`). Read `journal/0001-DISCOVERY-brief-corrections-from-parallel-deepdive.md` + `02-plans/01-architecture.md` § "Brief corrections" before acting on any "Phase-01 ships X" claim below.

---

## What Phase 02 must ship

Per `ROADMAP.md:74`:

> **Phase 02 — Distribution + channels + runtime pluggability** (target: 5–8 sessions). Goal: single static binary. Runtime picker on first run. Top-6 channels. Mobile onboarding.

Phase-02 is the phase that takes the Phase-01 pure-Python pipx MVP and turns it into a **distributable product**: a Rust-default static binary with a pluggable runtime, the full 6-channel surface plus mobile, the Foundation Envelope Library, and the Foundation Health Heartbeat infrastructure that Phase-01 stubbed.

### The six workstreams

| WS       | Theme                                        | Lead specs                                                    | Release-gated on legal?              |
| -------- | -------------------------------------------- | ------------------------------------------------------------- | ------------------------------------ |
| **WS-1** | Runtime pluggability                         | `runtime-abstraction.md`, ADR-0001/0009                       | partial (ADR-0009 board endorsement) |
| **WS-2** | Distribution surfaces (binary, mirrors)      | `distribution.md`, ADR-0001                                   | **YES — fully blocked**              |
| **WS-3** | Mobile + the 3 deferred channels             | `channel-adapters.md`, ADR-0008                               | partial (public app-store listing)   |
| **WS-4** | Envelope Library + SKILL ingest              | `envelope-library.md`, `skill-ingest.md`, `foundation-ops.md` | no (internal registry)               |
| **WS-5** | Foundation Health Heartbeat infra            | `foundation-health-heartbeat.md`, `mvp-build-sequence.md`     | no                                   |
| **WS-6** | Durable substrate + deferred product surface | `mvp-build-sequence.md`, Phase-01 forest                      | no                                   |

---

### WS-1 — Runtime pluggability (ADR-0001 + ADR-0009 delivery)

The Phase-01 MVP wired only `kailash-py` behind an abstract interface. Phase-02 wires the second runtime and the picker.

- `kailash-runtime` abstract interface crate (Apache 2.0) — ADR-0001 phase table `DECISIONS.md:64-65`.
- `kailash-rs-bindings` integration as **default** runtime — fills the `RuntimeBackendNotWired` feature-flagged stub (`mvp-build-sequence.md:202`).
- `kailash-py` integration as opt-in alternative runtime (`ROADMAP.md:80`).
- First-run runtime picker + `envoy runtime switch` + attestation-on-switch (`runtime-abstraction.md:231`).
- **Cross-runtime conformance**: N1–N6 byte-identical + E1–E7 semantic-equivalence vectors run against BOTH runtimes — BET-6 two-runtime harness (`runtime-abstraction.md:206,229,230`).
- Embedding strategy (PyO3 compile-time vs uv-managed subprocess) is an explicit Phase-02 `/analyze` decision (`DECISIONS.md:96`).
- Phase-02 threat gates: T-015 envelope re-read checkpoint, T-060 runtime-binary-poisoning (`runtime-abstraction.md:232`).

### WS-2 — Distribution surfaces ⚠️ LEGALLY GATED

- Single static Rust binary: `curl -sSf https://get.envoy.ai | sh` (kailash-rs core, embedded Python interpreter) — `distribution.md:19-25`.
- `brew install envoy-agent` / `winget install envoy-agent` / `cargo install envoy-agent` — `ROADMAP.md:90-92`.
- Binary builds on 5 targets (macOS arm64+x86_64, Linux x86_64+arm64+musl, Windows x86_64); **<50 MB** with embedded interpreter; CI gate `tests/acceptance/phase_02/test_binary_size_under_50mb.py` (`distribution.md:82`); strip-debug-symbols required (`distribution.md:84`).
- N=3 mirror layer + reproducible-build verification stream + signing-key rotation; T-050a/b mirror-signature + revoked-key refusal, T-060 (`distribution.md:125-131`, `runtime-abstraction.md:232`).
- First-run offline-model bundle, upgrade/rollback 30-day window, `--destroy-vault` double-confirm uninstall, jurisdictional (GDPR/EAR) install advisories (`distribution.md:125-131`).
- Install-to-first-value <10 min on mobile — MED-R5-1 acceptance gate (`distribution.md:59`).

### WS-3 — Mobile + the 3 deferred channels

- Flutter iOS + Android clients with QR-code pairing <30 s from cold start (`ROADMAP.md:93`, `DECISIONS.md:261,271`).
- Restore the channels Phase-01 de-scoped (kept Telegram/Slack/Discord) → full **6**: add iMessage (BlueBubbles), WhatsApp, Signal. iMessage native + Signal Path A are Phase-02+ (`mvp-build-sequence.md:204` — **OPTIONAL / cohort-driven**).
- Channel adapter contract: Rust `tokio` async layer (`channel-adapters.md:15`); Phase-02 ritual surfaces (`send_posture_review`/`send_monthly_report`) override the `PhaseDeferredError` default (`channel-adapters.md:73,75,267,286`).
- iOS/Android Connection-Vault native keychain bindings (`connection-vault.md:104` — **OPTIONAL** per `mvp-build-sequence.md:203`).
- Flutter screen-recording detection (`ui-platform.md:21`); clipboard auto-clear ≤30 s (`connection-vault.md:106`).
- 6-language localization: en-GB, es-ES, de-DE, fr-FR, zh-CN, ja-JP (`ui-platform.md:37`).

### WS-4 — Envelope Library v1 + SKILL.md translator

- Envelope Library registry `envoy-registry:envelope-library:v1` — Nexus-backed HTTP/CLI/MCP, content-addressed, Ed25519 publisher signatures (`foundation-ops.md:17`).
- **Foundation-Verified tier LIVE**; Community tier frozen until Phase-03 (`ROADMAP.md:96`, `envelope-library.md:17`). 2-of-N Foundation steward signing ceremony, quarterly key rotation.
- SKILL.md translator: lint + CO-compliance validator + automated envelope generator (ADR-0005 `DECISIONS.md:182,204`). CO validator step-3 (declared = inferred) code-analysis automation (`skill-ingest.md:41,81`).
- Acceptance: CO validator **rejects 3 constructed adversarial samples** (permission-escalation, exfiltration, privilege-overreach) and **accepts 100 benign** (`ROADMAP.md:107`).
- Classifier registry `envoy-registry:*` — FV classifiers 2-of-N signed (`foundation-ops.md:22`).
- EnterpriseDeploymentRecord schema + verifier + dual-sign gate ship WITH cross-runtime conformance (`enterprise-deployment.md:15`). NOTE: disablement flow is Phase-03, pilot acceptance is Phase-04 — do NOT over-scope.

### WS-5 — Foundation Health Heartbeat infrastructure

The single largest de-scoped Phase-01 item. Phase-01 ships ~100 LOC of stubs (4 modules raising `PhaseDeferredError`); Phase-02 stands up the real infrastructure (`mvp-build-sequence.md:75-84,201`). **Cost: 2–3 sessions.**

- OHTTP (RFC 9458) Key Configuration Server + Relay (strips source IPs) (`foundation-health-heartbeat.md:19-21`).
- STAR/Prio aggregator (encrypted-share split; k-anonymity k≥100) + differential privacy (bounded per-counter noise, published ε).
- Signed-consent opt-in Grant Moment producing a cascade-revocable Delegation Record.
- Fills the 4 deferred modules: STAR/Prio, OHTTP, signed-consent, registry handshake.

### WS-6 — Durable substrate + deferred product surface (the Phase-01 "forest")

Phase-01 shipped 7/10 canonical CLI subcommands. The remaining 3 (`init`, `chat`, `grant`) share ONE blocker class: **no process-independent persistent substrate + no long-running runtime/session model in Phase 01** (`mvp-build-sequence.md:209`, `journal/0048`). Phase-02 builds that substrate, which unblocks:

- `envoy init` / `chat` / `grant` CLI (forest F5.2 / F21) — `journal/0048:49-106`.
- Full `SessionObservedState` cache surface: tool-call fingerprints, first-time-action gate, goal-reconfirmation counter (`session-state.md:216-225`).
- Full PACT `ClassificationPolicy` enforcement + Tier-2 wiring: `@classify` canonical-only, `apply_read_classification` clearance, MaskingStrategy round-trip, T-005 ensemble fail-closed, classifier-version pinning (`classification-policy.md:106-111`).
- Full envelope-intersection semantics (`intersect_envelopes`), deferred at T-01-10 (`connection-vault.md:51,84`).
- Grant Moment: monotonic-baseline clock-skew detection (`grant-moment.md:103-109`); literal 3-deep delegation-tree persistence (`grant-moment.md:237`).
- Web/channel **visible-secret render** + duress modal (forest F20 / F15-c), landing WITH the shadow-segment duress-detection substrate (`journal/0047:40-58`, `journal/0046:89-95` — render parity is **OPTIONAL/low-stakes**).
- Ledger materialized-index rebuild-from-replay — multi-device substrate (`data-model.md:53,99-104`).
- **Verifier Rust crate MANDATORY** — `cargo install envoy-ledger-verifier`; closes EC-9 cross-language source-isolation using the SAME conformance vectors as the cross-runtime gate (`independent-verifier.md:261,274`, `mvp-build-sequence.md:207`). This is where Phase-01 forest items **F2/F4** (independent verifier, full EC-6) resolve — though the verifier stays separately-codebased.

---

## Exit criteria (per `ROADMAP.md:100-108`, verbatim)

- Rust binary builds on macOS (arm64 + x86_64), Linux (arm64 + x86_64 + musl), Windows (x86_64)
- Binary size <50 MB with embedded Python interpreter
- Runtime picker works; opt-out to pure-Python mode tested end-to-end
- Cross-runtime conformance vectors pass (both runtimes behave identically)
- 6 channels pass end-to-end Grant Moment → action → audit
- Mobile QR-pairing works in <30 s from cold start
- CO validator rejects 3 constructed adversarial skill samples and accepts 100 benign ones

Plus, per `acceptance-metrics.md:30-32`: Foundation Health Heartbeat functional; N=3 mirrors signed; reproducible-build stream; install-to-first-value <10 min mobile.

---

## ⚠️ External-gate blocker — READ BEFORE SEQUENCING

Phase-02's distribution surface is **release-blocked on Phase-00 external legal/governance gates that are still OPEN** (`ROADMAP.md:11-37`, nearly all `[ ]`):

| Gate                                                          | Status                     | What it blocks                                                              |
| ------------------------------------------------------------- | -------------------------- | --------------------------------------------------------------------------- |
| USPTO + EUIPO + UK IPO trademark sweep + final mark           | ❌ OPEN                    | Public install surfaces (`brew`/`winget`/`get.envoy.ai`), app-store listing |
| Namespace reservation (`envoy-agent`)                         | ❌ pending trademark close | Published package names                                                     |
| Composite LICENSE + SPDX + export-control assessment          | ❌ OPEN                    | Rust binary redistribution (crypto/dual-use)                                |
| Foundation board endorsement of ADR-0009 runtime-pluggability | ❌ OPEN                    | The runtime-pluggability legal model itself                                 |

**These are human-authority / calendar-bound gates the agent CANNOT clear** (per `rules/autonomous-execution.md` — the 10× multiplier explicitly excludes external approvals).

**Implication for sequencing:** WS-2 (distribution) and the public-facing half of WS-3 cannot _ship_ until legal clears. But **WS-1, WS-4, WS-5, WS-6 and the engineering half of WS-3 can be fully built and validated now** — they're internal substrate, release-gated only at the very end. The recommended sequencing (for `/analyze` → `/todos` to confirm) is to front-load the legally-unblocked engineering and treat WS-2 release as a legal-gated tail.

---

## What Phase 02 inherits / must hold

1. **All 37 frozen specs remain authoritative** — spec EDITS trigger `specs-authority.md` MUST Rule 5b (full-sibling re-derivation). Phase-02 adds implementation detail; it does not re-open Phase-00 architecture.
2. **Abstract `kailash-runtime` interface already exists** (Phase-01 built it with one impl) — Phase-02 wires the second; the interface contract is frozen.
3. **Cross-runtime byte-identity is the load-bearing BET-6 claim** — both runtimes MUST pass identical conformance vectors; this is the hardest correctness invariant in the phase.
4. **Independent verifier stays separately-codebased** (EC-9) — Phase-02 makes its Rust impl mandatory but does NOT fold it into the main tree.

## Pre-declared Phase-02 de-scope candidates (if shard budget exceeded)

In rough order of preference, drawn from the OPTIONAL-tagged harvest items:

1. iMessage native + Signal Path A → keep Path B / defer to Phase-04 (`mvp-build-sequence.md:204`).
2. iOS/Android native keychain bindings → desktop keychains only this phase (`mvp-build-sequence.md:203`).
3. macOS/Linux screen-recording countermeasures → advisory-only (`ui-platform.md:91`).
4. ECH (Encrypted Client Hello) / Tor routing → Phase-02+ optional (`network-security.md:30,75`).

## Cross-cutting carryover (non-blocking, tracked)

- **F22** ResourceWarning → CI `-W error`: BLOCKED-UPSTREAM on kailash-py#1245.
- **F23 / threat-coverage meta-gate** for T-005/T-012: lands in Phase-02 (`classification-policy.md:111`, `journal/0053`).
- Phase-02 security review: full binding security audit, OHTTP/STAR review, FV signing ceremony, CRDT-merge external review, reproducible-build stream (`threat-model.md:52`).

---

## What Phase 02 `/analyze` must produce

Like Phase-01, this is _implementation architecture_, not re-derivation. `/analyze` must produce:

- A workstream-by-workstream implementation plan mapping each exit criterion to concrete deliverables.
- A **legal-gate-aware build sequence** that front-loads WS-1/4/5/6 (buildable now) and isolates WS-2 release behind the external gates.
- Cross-runtime conformance-harness design (the BET-6 two-runtime vectors) — the phase's central correctness risk.
- Embedding-strategy decision (PyO3 vs uv-managed) per `DECISIONS.md:96`.
- Sharding plan (per `autonomous-execution.md` capacity budget) — at 5–8 sessions this WILL require decomposition at `/todos`.
- Any Phase-02 spec gaps (additions, not edits).

## Out of scope for Phase 02 (do NOT pull forward)

- Envelope Library **Community** tier open publishing → Phase 03 (`envelope-library.md:17`).
- Weekly Posture Review + Monthly Trust Report rituals → Phase 03 (`ROADMAP.md:110`).
- Shared Household / multi-principal / A2A cross-principal → Phase 03 (`mvp-build-sequence.md:205`, `a2a-messaging.md:13`).
- Enterprise disablement flow + pilot acceptance → Phase 03/04 (`enterprise-deployment.md:16,17`).
- Hot-path P50 <10 ms latency target → Phase 03 (`ROADMAP.md:118`).
- Channel breadth beyond 6 (Matrix, Feishu, voice, Shortcuts) → Phase 04.
