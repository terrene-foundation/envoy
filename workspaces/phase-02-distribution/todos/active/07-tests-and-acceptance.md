# 07 — Cross-cutting tests + per-EC acceptance batteries

**Document role.** The per-shard acceptance criteria already live in the milestone files (`01..06-m*.md`). THIS file adds the two cross-cutting surfaces that span all 6 milestones: (1) one **per-exit-criterion acceptance battery** per EC-02.1…EC-02.10 (the measurable gate that proves the phase met the user's brief), and (2) the **3-tier test architecture** (Tier 1 offline-unit / Tier 2 real-infra-integration / Tier 3 real-binary-E2E) with a per-workstream coverage map. The single most important artifact here is the **BET-6 cross-runtime conformance harness** (T-07-204) — it is the phase's hardest correctness gate and feeds the mandatory verifier (S7v) and EC-02.4/EC-9.

**Date:** 2026-06-08 (`/todos`, cross-cutting test/acceptance file; companion to the 6 milestone files).
**Status:** DRAFT — awaiting the human `/todos` structural-approval gate.
**Source authority:**

- `01-analysis/00-objectives-to-deliverables.md` — the EC-02.1…EC-02.10 → shard mapping (each EC's owning workstream, deliverable, central risk, legal-gate status). Every EC below cites its row.
- `02-plans/01-architecture.md` — the 31-shard map + conformance-harness centrality (§ critical path S1 → S2a → S3b → S7v).
- `specs/acceptance-metrics.md:32` — the canonical Phase-02 exit-criteria line (5 targets; <50 MB; picker E2E; conformance vectors N1–N6 + E1–E7; 6 channels; QR-pair <30s; CO validator 100 benign + 3 adversarial; Heartbeat functional; N=3 mirrors signed; reproducible-build stream; install-to-first-value <10min mobile).
- `ROADMAP.md:101-107` (EC-02.1…02.7) + `specs/acceptance-metrics.md:31-32` (EC-02.8…02.10).
- `workspaces/phase-01-mvp/02-plans/02-test-strategy.md` + `workspaces/phase-01-mvp/todos/active/{07,08}-*.md` — 3-tier convention precedent (Tier 2/3 real infra, NO mocking; per-EC Tier-3 battery; wiring-test naming).
- `.claude/rules/testing.md` — 3-tier discipline (Tier 2/3 real infra, no `@patch`/`MagicMock`/`unittest.mock`); probe-driven semantic checks; E2E pipeline regression; state-persistence read-back.

---

## The legal-gate carve-out for acceptance (read first)

Per `00-objectives-to-deliverables.md` § Legal-gate dependency map: Phase-00 external gates (trademark, composite LICENSE, export-control, ADR-0009 board, app-store identity) gate **release**, not **build** — and not **acceptance**. **EC-02.1 (5-target build), EC-02.2 (<50 MB), and EC-02.9 (N=3 mirrors signed + reproducible) acceptance batteries can run NOW under a codename** — building crypto-bearing binaries is not export-controlled; only cross-border _redistribution_ under a trademarked name is. The acceptance gates here use a codename binary + a codename signing key. Only the final **release-signing ceremony** (publish under the trademarked name, attach the composite LICENSE, cross-border redistribution) waits on the legal gates. No acceptance battery below is blocked by an open legal gate; the legal tail blocks only the public release CI step inside S16.

Per `rules/testing.md` § Tier 2/3: every battery below that touches Tier 2 or Tier 3 uses **real infrastructure, NO mocking** (`@patch`/`MagicMock`/`unittest.mock` BLOCKED at Tier 2/3). Every state-mutating assertion is **read-back-verified** (write, then read, assert the value). Every **semantic** verdict (the N4 rendered-text slice — Phase-03 only; CO-validator false-positive judgments) is **probe-driven** per `rules/probe-driven-verification.md`, never regex/keyword.

---

## Per-EC acceptance map (the gate index)

| EC       | Acceptance todo | Owning workstream / shards (gates)             | Tier     | Real-infra requirement                                         | Legal-gate status (for acceptance) |
| -------- | --------------- | ---------------------------------------------- | -------- | -------------------------------------------------------------- | ---------------------------------- |
| EC-02.1  | T-07-220        | WS-2 / S15 (+S15m musl)                        | Tier 3   | Real CI cross-compile runners (5 targets + musl)               | **runnable NOW (codename)**        |
| EC-02.2  | T-07-221        | WS-2 / S15 (embed) + WS-1 S2a (embed decision) | Tier 3   | Real built binary, real `strip`, real size measurement         | **runnable NOW (codename)**        |
| EC-02.3  | T-07-222        | WS-1 / S3p (+S3t attestation)                  | Tier 3   | Real binary, real Vault cold-unlock, both runtimes wired       | no                                 |
| EC-02.4  | T-07-223        | WS-1 / S1, S2a–c, S3a, S3b (harness T-07-204)  | Tier 2/3 | Both real runtimes (`kailash-py` + `kailash-rs-bindings`)      | no                                 |
| EC-02.5  | T-07-224        | WS-3 / S14 (+ Phase-01 5 surfaces) + WS-6 S4g  | Tier 3   | Real channel sandboxes (6) + real grant-moment store path      | partial (no acceptance block)      |
| EC-02.6  | T-07-225        | WS-3 / S13a (SAS) + S13b (Flutter)             | Tier 3   | Real Flutter app on real iOS+Android, real QR camera path      | partial (app-store; no acc. block) |
| EC-02.7  | T-07-226        | WS-4 / S9a (2 AST) + S9b (1 dynamic) + S8      | Tier 2/3 | Real Nexus registry + real classifier ensemble (S9b)           | no                                 |
| EC-02.8  | T-07-227        | WS-5 / S10, S11, S12 + WS-6 S4g                | Tier 2/3 | Real OHTTP relay + real STAR aggregator + real grant path      | no                                 |
| EC-02.9  | T-07-228        | WS-2 / S16 (+ WS-1 S3t attestation)            | Tier 3   | Real N=3 mirrors, real signing keys, real reproducible rebuild | **runnable NOW (codename)**        |
| EC-02.10 | T-07-229        | WS-2/3 / S17 (+ S13b mobile, S15 desktop)      | Tier 3   | Real install path (App/Play store sandbox + `curl\|sh`)        | partial (no acceptance block)      |

**Coverage confirmation:** all 10 ECs (EC-02.1 … EC-02.10) carry exactly one acceptance-battery todo (T-07-220 … T-07-229). No EC is uncovered.

---

# Part 1 — Per-EC acceptance batteries

## T-07-220 — EC-02.1 acceptance: Rust binary builds on 5 targets

- **Type:** Test
- **Value-anchor:** `specs/acceptance-metrics.md:32` ("Binary builds 5 targets") + `ROADMAP.md:101` + `00-objectives-to-deliverables.md` EC-02.1 row ("CI cross-compile matrix: macOS arm64/x86_64, Linux x86_64/arm64/musl, Windows x86_64"). This is the headline "single static binary" deliverable (`ROADMAP.md:74`).
- **Implements:** EC-02.1; `specs/distribution.md` § build-target matrix.
- **Depends:** S15 (5 routine targets) + S15m (musl mostly-static + Alpine import-smoke). Acceptance runs after both land.
- **Scope:** Tier-3 acceptance that the codename binary builds + boots on every target. For each of the 5 targets (macOS arm64, macOS x86_64, Linux x86_64-gnu, Linux arm64-gnu, Windows x86_64) plus the musl mostly-static target: build via the real CI cross-compile matrix; run a boot-smoke (`envoy --version` exits 0 + an embedded-interpreter import-smoke). The musl cell runs its Alpine import-smoke Tier-3 gate (S15m) and honors the defer-to-gnu-only fallback valve if the full-static `dlopen` path is infeasible.
- **Acceptance criteria (the measurable gate):**
  - All 5 routine targets build green in real CI and each produced binary boots (`envoy --version` exit 0) on its native OS/arch runner.
  - The musl target either (a) passes the Alpine import-smoke, OR (b) the S15m defer-to-gnu-only fallback valve is exercised with a recorded value-anchored disposition (not a silent skip per `rules/test-skip-discipline.md`).
  - Tier: **Tier 3** (real CI runners, real binaries). Real-infra requirement: the actual cross-compile matrix, not a single-host emulation claim.
  - **Legal-gate:** runs NOW under a codename. No publish-under-trademark step in this battery.
- **Capacity check:** invariants ≈ 3 (5-target build-green, per-target boot-smoke, musl fallback-valve disposition); call-graph hops ≈ 2 (CI matrix → built artifact → smoke); LOC ≈ 200 (matrix wiring + smoke harness; data-heavy). Live loop (CI exit codes). **Within budget.**

---

## T-07-221 — EC-02.2 acceptance: binary <50 MB with embedded Python

- **Type:** Test
- **Value-anchor:** `specs/acceptance-metrics.md:32` ("binary <50 MB") + `ROADMAP.md:102` + `00-objectives-to-deliverables.md` EC-02.2 row ("strip + size CI gate `test_binary_size_under_50mb`"). Central risk named there: "50 MB ceiling with CPython + deps is tight."
- **Implements:** EC-02.2; `specs/distribution.md:78-82` (<50 MB embed cap).
- **Depends:** S15 (embed strategy + strip + size gate) + WS-1 S2a (the PyO3-compile-time-embed decision that fixes the interpreter footprint).
- **Scope:** Tier-3 size CI gate. Build the stripped codename binary on each target; measure the on-disk size of the embedded-interpreter binary (the offline-model bundle is a SEPARATE artifact per `02-plans/01-architecture.md` WS-2 verdict and is NOT counted here). Assert < 50 MB on the worst-case target.
- **Acceptance criteria (the measurable gate):**
  - The stripped binary measures **< 50 MB** on the largest target; the size is produced by a verifying command at gate time (`rules/testing.md` § Verified Numerical Claims — no hand-typed size).
  - The offline-model bundle is confirmed to be a distinct artifact (not folded into the 50 MB figure); a separate assertion records its size against the EC-02.10 install budget (cross-ref T-07-229).
  - Tier: **Tier 3** (real built + stripped binary). Real-infra requirement: actual `strip` output measured, not an estimate.
  - **Legal-gate:** runs NOW under a codename.
- **Capacity check:** invariants ≈ 2 (size-under-cap, model-bundle-excluded); call-graph hops ≈ 2 (build → strip → measure); LOC ≈ 120. Live loop (size assertion). **Within budget.**

---

## T-07-222 — EC-02.3 acceptance: runtime picker; pure-Python opt-out E2E

- **Type:** Test
- **Value-anchor:** `specs/acceptance-metrics.md:32` ("runtime picker E2E") + `ROADMAP.md:103` ("Runtime picker works; opt-out to pure-Python mode tested end-to-end") + `00-objectives-to-deliverables.md` EC-02.3 row ("First-run picker + `envoy runtime switch` + attestation-on-switch"; central risk: "clean opt-out path through a Rust-default binary"). EC-02.3 is **ADR-0009-board legal-gated for release** but the acceptance battery itself is buildable/runnable now.
- **Implements:** EC-02.3; `specs/runtime-abstraction.md` § Runtime picker (`:198-200`).
- **Depends:** S3p (picker + `envoy runtime switch` state machine) + S3t (attestation-on-switch). Both must land first.
- **Scope:** Tier-3 E2E of the picker + opt-out walk against the real binary. First-run picker presents the default (`kailash-rs-bindings`) + the one-keystroke opt-out to `kailash-py`; choosing opt-out routes ALL subsequent execution through the pure-Python runtime; `envoy runtime show` reports the active runtime; `envoy runtime switch` runs the full cold-unlock → attest → re-read-checkpoint → Genesis-signed `runtime_switch` Ledger entry sequence. Read-back-verify the `runtime-choice` config + the `runtime_switch` Ledger entry persist across a process restart.
- **Acceptance criteria (the measurable gate):**
  - A first-time user opts out to pure-Python in one keystroke; a subsequent `envoy` action runs end-to-end on `kailash-py` with NO `kailash-rs-bindings` dispatch (verified via the S1 dispatch-observation hook, not by inspecting prose).
  - `envoy runtime switch` back to rs succeeds only after attestation; a fixture-poisoned target REFUSES the switch fail-closed with NO `runtime_switch` record written (read-back: ledger has no orphan record).
  - The choice persists across restart (read-back-verified config + ledger entry).
  - Tier: **Tier 3** (real binary, real Vault cold-unlock, both runtimes wired).
- **Capacity check:** invariants ≈ 4 (opt-out routes all dispatch, switch-after-attest ordering, fail-closed-no-record, persistence-across-restart); call-graph hops ≈ 3; LOC ≈ 250. Live loop (CLI exercisable). **Within budget.**

---

## T-07-223 — EC-02.4 acceptance: cross-runtime conformance vectors pass

- **Type:** Test
- **Value-anchor:** `specs/acceptance-metrics.md:32` ("cross-runtime conformance vectors (N1–N6 + E1–E7)") + `ROADMAP.md:104` ("both runtimes behave identically") + `00-objectives-to-deliverables.md` EC-02.4 row, flagged there as **"highest correctness risk in the phase."** This is the BET-6 proof that "same behavior, only slower" is verifiable for opt-out users.
- **Implements:** EC-02.4; `specs/runtime-abstraction.md` § Conformance vectors (N1–N6 `:149-154`, E1–E7 `:190-196`). Consumes the BET-6 harness (T-07-204).
- **Depends:** S1 (harness skeleton + tier metadata) → S2a (rs adapter wired) → S2b (N1–N3) + S2c (N4–N6 structured) + S3a (E1–E4) + S3b (E5–E7). The full corpus must be green on BOTH runtimes.
- **Scope:** Tier-2/3 acceptance that the ENTIRE byte-identity corpus passes across both real runtimes. Run the parametrized harness over `["kailash-py","kailash-rs-bindings"]` × every vector family. Phase-02 conformance = **byte-identity across every family (N1–N6 structured + E1–E7)** via hash-equality. The ONE semantic slice — **N4's rendered verdict TEXT** — is **Phase-03** (`runtime-abstraction.md:152,207`); its scoring metric is an open Phase-03 spec question (`:239`). This battery asserts N4 **structured-payload** byte-identity ONLY and confirms no probe/semantic-scorer fires on N4 rendered text in Phase-02 (demoting any byte-identical method to semantic is BLOCKED per `zero-tolerance.md` Rule 4 / `journal/0004` R3-HIGH).
- **Acceptance criteria (the measurable gate):**
  - Every N1–N6-structured + E1–E7 vector produces **hash-equal** canonical output across both runtimes; the `RS_BINDINGS_ENABLED` flag-flip gate is satisfied (full corpus green on both).
  - The byte-identity slice runs green on the full OS matrix (macos-14, ubuntu-22.04/24.04, windows-2022) — cross-language NFC drift (a truncated combining character on one OS) is a silent BET-6 falsifier a single-OS run never catches.
  - N4 rendered-text equivalence is recorded as **Phase-03 deferred** (not collected as a Phase-02 gate); a reviewer sweep confirms no semantic scorer fires on N4 text this phase.
  - E7 head-commitment-monotonicity vectors come from the SINGLE shared corpus S7v also consumes (one truth, not two).
  - Tier: **Tier 2** (both real runtimes) graduating to **Tier 3** on the real binary. Real-infra: both runtimes; NO mocked runtime.
- **Capacity check:** invariants ≈ 5 (full-corpus byte-identity, OS-matrix green, N4-structured-only, single-E7-corpus, flag-flip gate); call-graph hops ≈ 3; LOC ≈ 200 (acceptance is corpus-orchestration over T-07-204; vectors live in the shards). Live loop. **Within budget — depends on every M1 conformance shard landing.**

---

## T-07-224 — EC-02.5 acceptance: 6 channels pass E2E Grant Moment → action → audit

- **Type:** Test
- **Value-anchor:** `specs/acceptance-metrics.md:32` ("6 channels pass") + `ROADMAP.md:105` ("6 channels pass end-to-end Grant Moment → action → audit") + `00-objectives-to-deliverables.md` EC-02.5 row. Per `02-plans/01-architecture.md` brief-correction C2/§19: the EC-02.5 "6" = {CLI, Web, Telegram, Slack, Discord} (Phase-01) + WhatsApp + Signal Path B — excluding de-scoped iMessage + Signal Path A.
- **Implements:** EC-02.5; `specs/ui-platform.md` § channel adapters.
- **Depends:** S14 (WhatsApp + Signal Path B adapters + tokio layer) + the 5 Phase-01 surfaces + WS-6 S4g (the grant-moment store-poll rendezvous path that lets a grant answered later resume).
- **Scope:** Tier-3 E2E "Grant Moment" walk per channel against real vendor sandboxes. For each of the 6 channels: trigger an out-of-envelope action → Grant Moment renders on that channel → user resolves (Approve) → the action executes → a `grant_moment` Ledger row is written. Read-back-verify the audit row per channel.
- **Acceptance criteria (the measurable gate):**
  - All **6 channels** complete the full Grant Moment → action → audit loop end-to-end against real sandboxes (WhatsApp Business sandbox, signal-cli REST for Path B, real Telegram/Slack/Discord, CLI, Web).
  - Each channel's resolution writes a verifiable `grant_moment` Ledger entry (read-back-verified; the grant answered on one channel resumes via the S4g store-poll path, not an in-process Future).
  - Tier: **Tier 3** (real channel sandboxes + real grant store path). Real-infra: NO mocked channel transport (mocks bypass the FFI/transport path).
  - **Legal-gate:** acceptance runs now; WhatsApp's business-pricing gate blocks public _launch_, not the sandbox acceptance walk.
- **Capacity check:** invariants ≈ 3 (6-channel E2E loop, per-channel audit read-back, cross-channel grant resume); call-graph hops ≈ 3 (channel → grant orchestrator → store → ledger); LOC ≈ 280 (6 channel walks, pattern-stamped). Substrate-gated→live once S4g lands. **Within budget.**

---

## T-07-225 — EC-02.6 acceptance: mobile QR-pair <30s cold start

- **Type:** Test
- **Value-anchor:** `specs/acceptance-metrics.md:32` ("mobile QR-pair <30s") + `ROADMAP.md:106` ("Mobile QR-pairing works in <30s from cold start") + `00-objectives-to-deliverables.md` EC-02.6 row (central risk: "pairing-protocol security (T-class) + cold-start budget"). The QR pairing is ADR-0008's "magical onboarding moment."
- **Implements:** EC-02.6; `specs/threat-model.md` § device-pairing addition (transcript-SAS strength floor); `specs/ui-platform.md` § mobile.
- **Depends:** S13a (QR transcript-SAS handshake + threat-model addition) + S13b (Flutter client-shell). Both halves of the split S13 must land.
- **Scope:** Tier-3 E2E on a real Flutter app (real iOS + real Android device/emulator). Cold-start the app, scan the QR, complete the transcript-SAS handshake (the SAS is a truncated hash of the handshake **transcript**, NOT the static visible secret — a MITM relay yields a different transcript → SAS mismatch → abort), confirm the matching SAS on both screens, land a signed `device_pairing` Ledger event. Measure wall-clock from cold app launch to paired state.
- **Acceptance criteria (the measurable gate):**
  - Cold-start-to-paired completes in **< 30 s** on both real iOS and real Android (measured by a verifying timestamp delta, not hand-typed).
  - The SAS is transcript-derived: a fixture MITM-relay run yields a DIFFERENT SAS on the two screens and the pairing aborts (security gate, not just timing). SAS strength floor ≤ 2⁻²⁰ residual blind-relay MITM probability per the threat-model addition.
  - The successful pairing writes a signed Ledger event (read-back-verified).
  - Tier: **Tier 3** (real Flutter app, real camera/QR path, real devices). Real-infra: actual mobile runtime, not a unit-level protocol stub.
  - **Legal-gate:** acceptance runs now; the app-store identity gate blocks public _listing_, not the device-pairing acceptance walk.
- **Capacity check:** invariants ≈ 4 (sub-30s cold-start, transcript-SAS-not-visible-secret, MITM-abort, signed-event read-back); call-graph hops ≈ 3; LOC ≈ 220 (Flutter integration_test + harness). Live loop on device. **Within budget.**

---

## T-07-226 — EC-02.7 acceptance: CO validator rejects 3 adversarial + accepts 100 benign

- **Type:** Test
- **Value-anchor:** `specs/acceptance-metrics.md:32` ("CO validator accepts 100 benign + rejects 3 adversarial") + `ROADMAP.md:107` ("rejects 3 constructed adversarial skill samples (permission-escalation, exfiltration, privilege-overreach) and accepts 100 benign ones") + `00-objectives-to-deliverables.md` EC-02.7 row (central risk: "false-positive budget on inferred-permission analysis").
- **Implements:** EC-02.7; `specs/foundation-ops.md` § CO-compliance validator; declared-vs-inferred code analysis.
- **Depends:** S9a (translator + CO validator steps 1-4,6 via AST — accountable for the **2 AST-catchable** adversarial samples) + S9b (CO validator step-5 classifier ensemble — accountable for the **1 dynamic-dispatch** adversarial sample; substrate-gated on S6a) + S8 (Nexus registry).
- **Scope:** Tier-2/3 acceptance of the asymmetric validator against the fixed corpus. The 3 adversarial samples (permission-escalation, exfiltration, privilege-overreach) MUST all be REJECTED; the 100 benign samples MUST all be ACCEPTED (0 false-negative on adversarial AND 0 false-positive on benign, corpus-specific 100/3). Per `02-plans/01-architecture.md` WS-4 verdict: the 0-false-negative-on-3 split is **2 via AST (S9a) + 1 dynamic-dispatch via ensemble (S9b)** — stated so neither shard ships a gate it structurally can't meet. False-positive/false-negative judgments on inferred permissions are **probe-driven** per `rules/probe-driven-verification.md` (LLM-judge with a JSON-schema verdict where the call is semantic), never regex/keyword.
- **Acceptance criteria (the measurable gate):**
  - All **3** adversarial samples rejected: 2 caught by S9a's AST path, 1 (dynamic-dispatch) caught by S9b's classifier ensemble. Zero false-negatives on the adversarial set.
  - All **100** benign samples accepted: zero false-positives on the benign set.
  - The validator runs against the real Nexus registry (S8) and, for the dynamic-dispatch sample, the real classifier ensemble (S9b) — NOT a mocked classifier (Tier 2 NO mocking).
  - Where the accept/reject verdict is a semantic judgment of inferred permissions, it is probe-driven with a schema'd verdict (no regex over validator prose).
  - Tier: **Tier 2** (real registry + real ensemble) graduating to **Tier 3** end-to-end via the binary.
- **Capacity check:** invariants ≈ 4 (3-adversarial-rejected split AST/ensemble, 100-benign-accepted, real-ensemble-no-mock, probe-driven-semantic-verdict); call-graph hops ≈ 3; LOC ≈ 240 (corpus orchestration; the 103 samples are data). Substrate-gated→live once S9b lands. **Within budget.**

---

## T-07-227 — EC-02.8 acceptance: Foundation Health Heartbeat functional

- **Type:** Test
- **Value-anchor:** `specs/acceptance-metrics.md:31-32` ("Foundation Health Heartbeat functional") + `00-objectives-to-deliverables.md` EC-02.8 row ("OHTTP server+relay + STAR/Prio aggregator + DP + signed consent"; central risk: "k-anonymity k≥100 + DP ε calibration"). This is the single largest de-scoped Phase-01 item now landing.
- **Implements:** EC-02.8; `specs/foundation-health-heartbeat.md` § STAR k-anonymous opt-in (`acceptance-metrics.md:15`).
- **Depends:** S10 (OHTTP key-config server + relay) + S11 (STAR client crypto + k-anonymity + client-side DP with total-ε-over-window accounting) + S12 (signed-consent Grant Moment, consumes WS-6 S4g grant path).
- **Scope:** Tier-2/3 functional acceptance of the end-to-end heartbeat flow against real infrastructure. A signed-consent Grant Moment opts the user in; a flag (`HeartbeatClient.maybe_record_flag`, the real hot-path seam per brief-correction C3) routes through the real STAR client → real OHTTP relay → real STAR aggregator; the aggregate respects the k≥100 floor and the DP total-ε-over-window bound. Read-back-verify the signed consent record and that NO raw per-user value is recoverable from the relay (privacy gate). Pin whether the k≥100 floor reads the noised or true cohort count (the architecture's open WS-5 question — resolve at this gate).
- **Acceptance criteria (the measurable gate):**
  - The full opt-in → flag → relay → aggregate path runs end-to-end against the **real OHTTP relay + real STAR aggregator** (NO mocked relay/aggregator — Tier 2 NO mocking).
  - The aggregator enforces k≥100 (inert-below-threshold is a signal gap, not a leak) and the total-ε-over-window DP bound; the per-counter-does-not-compose property holds.
  - Signed consent is read-back-verified; a relay-side inspection confirms no raw per-user counter is recoverable (privacy claim is the TOTAL ε over the stated window).
  - Tier: **Tier 2** (real relay + aggregator + grant path) graduating to **Tier 3**.
- **Capacity check:** invariants ≈ 4 (real-relay/aggregator-no-mock, k≥100 floor, total-ε bound, signed-consent read-back + no-raw-value); call-graph hops ≈ 3 (flag → STAR client → relay → aggregator); LOC ≈ 240. Substrate-gated→live once S12 lands. **Within budget.**

---

## T-07-228 — EC-02.9 acceptance: N=3 mirrors signed + reproducible-build stream

- **Type:** Test
- **Value-anchor:** `specs/acceptance-metrics.md:31-32` ("N=3 mirrors signed; reproducible-build stream") + `00-objectives-to-deliverables.md` EC-02.9 row (central risk: "reproducible-build determinism across 5 targets"; legal-gated for **release**).
- **Implements:** EC-02.9; `specs/distribution.md:33` (N=3 mirror cross-check) + § signing-key rotation + reproducible builds; consumed by WS-1 S3t attestation (binary_hash vs manifest).
- **Depends:** S16 (N=3 mirror + reproducible-build + key-rotation + release CI checks) + WS-1 S3t (the attestation that cross-checks binary_hash against the N=3 mirror manifest).
- **Scope:** Tier-3 acceptance of mirror signing + build reproducibility under a codename signing key. Build each target twice from the pinned sources and assert byte-identical reproducible output; publish to N=3 real mirrors; assert each mirror's artifact carries a valid signature; a fixture signature-mismatch or revoked key REFUSES (mirrors `MirrorSignatureMismatchError`/`ReproducibleBuildFailedError`/`RevokedSigningKeyError`, `distribution.md:94-95`).
- **Acceptance criteria (the measurable gate):**
  - Each of the 5 targets rebuilds **byte-identically** from pinned sources (reproducible-build determinism); the build-hash is produced by a verifying command, not hand-typed.
  - All **N=3 mirrors** serve a validly-signed artifact; the S3t attestation path cross-checks binary_hash against the N=3 manifest and a poisoned mirror is REFUSED fail-closed.
  - Key-rotation: a rotated-out signing key is rejected; a current key verifies.
  - Tier: **Tier 3** (real mirrors, real signing keys, real reproducible rebuild). Real-infra: actual N=3 mirror endpoints + actual double-build, not a determinism claim on one build.
  - **Legal-gate:** the reproducibility + signing + mirror acceptance runs NOW under a codename signing key; only the public release-signing ceremony (trademarked name, composite LICENSE, cross-border redistribution) waits on the legal gates inside S16.
- **Capacity check:** invariants ≈ 4 (byte-identical-rebuild, N=3-signed, key-rotation-reject, attestation-cross-check-fail-closed); call-graph hops ≈ 3; LOC ≈ 240. Live loop (build-hash + signature exit codes). **Within budget.**

---

## T-07-229 — EC-02.10 acceptance: install-to-first-value <10min mobile

- **Type:** Test
- **Value-anchor:** `specs/acceptance-metrics.md:32` ("install-to-first-value <10min mobile") + `specs/distribution.md:59` + `00-objectives-to-deliverables.md` EC-02.10 row (central risk: "offline-model bundle size vs the 50 MB ceiling"; ADR-0006 degraded-mode zero-network path).
- **Implements:** EC-02.10; `specs/distribution.md` § Install-to-first-value (Phase-02 acceptance gate); the mobile + desktop measurement substrate already named there (`integration_test/test_install_to_first_value_mobile.dart` → `tests/acceptance/phase_02/test_install_to_first_value_mobile.py`; desktop `..._desktop.py` shelling `curl|sh` + `envoy init`).
- **Depends:** S17 (first-run onboarding + offline-model bundle / ADR-0006 degraded-mode zero-network path + the install-to-first-value measured gate) + S13b (mobile shell) + S15 (desktop binary).
- **Scope:** Tier-3 acceptance measuring wall-clock from install-tap to first user-observable Envoy action (typically the Boundary Conversation S0 greet rendered in the primary channel). The clock starts at install-complete and stops at S0 render. Run the median across 10 sample installs (mobile via App/Play store sandbox; desktop via `curl|sh`). The offline-model bundle (the ADR-0006 zero-network path) must let the first value render WITHOUT a network round-trip, and its size must not violate the 50 MB binary cap interplay (cross-ref T-07-221).
- **Acceptance criteria (the measurable gate):**
  - Median across **10 sample installs** is **< 10 min mobile** (and < 5 min desktop per `distribution.md`); Phase-02 exit is blocked if the median exceeds the budget.
  - First value renders via the ADR-0006 zero-network offline path (no network dependency for first value); the offline-model bundle size is recorded against the install budget.
  - Tier: **Tier 3** (real install path — store sandbox + `curl|sh`). Real-infra: actual install, not a simulated timing claim.
  - **Legal-gate:** acceptance runs now; the app-store listing gate blocks public _availability_, not the sandbox install-timing walk.
- **Capacity check:** invariants ≈ 3 (sub-10min-median-mobile, zero-network-first-value, bundle-size-vs-cap); call-graph hops ≈ 2 (install → first-launch → S0 render); LOC ≈ 200 (the aggregator + Flutter/desktop harnesses). Live loop (timestamp deltas). **Within budget.**

---

# Part 2 — 3-tier test architecture (per-workstream coverage map)

Per `rules/testing.md` § 3-Tier Testing + the Phase-01 precedent (`workspaces/phase-01-mvp/02-plans/02-test-strategy.md`). Tier 2/3 use **real infrastructure, NO mocking**. Every wiring test imports through the framework facade and asserts an externally-observable effect; every paired crypto/variant operation has a round-trip THROUGH the facade.

## T-07-200 — Tier 1: offline unit suite (fast, mocking-allowed) per workstream

- **Type:** Test
- **Value-anchor:** `rules/testing.md` § Tier 1 (mocking allowed; <1s/test) — the offline fast-feedback floor that lets every shard run a live loop. Each shard already seeds its own Tier-1 tests; this todo consolidates the surface into one manifest so the `/redteam` round-1 mechanical sweep can audit per-module coverage (`rules/testing.md` § Audit Mode — grep every NEW module for ≥1 importing test; empty = HIGH).
- **Implements:** the Tier-1 row of the 3-tier contract across all 6 workstreams.
- **Depends:** seeded inside each shard (S1…S17); this manifest lands as shards land.
- **Scope (per-workstream Tier-1 coverage map):**
  - **WS-1 (runtime):** pure functions — contract-tier decorator resolution, `get_runtime()` family resolution, byte-identity scorer field-diff localization, dispatch-observation hook determinism, picker config schema validation. Mocks of the rs binding PERMITTED at Tier 1 (Tier 2 round-trip proves the real call).
  - **WS-6 (substrate):** store-poll monotonic-version re-check logic, `session_boundary_crossed` content-hash purity, `GrantMomentExpiredError` timeout arithmetic, ClassificationPolicy `@classify`/clearance pure checks, `init` genesis write-once validation.
  - **WS-4 (library/skill):** `canonical_bytes()` byte-pinning, score-band routing thresholds, SKILL→envelope translator field mapping, `verify_steward_quorum` 2-of-N arithmetic, EnterpriseDeploymentRecord schema validation.
  - **WS-5 (heartbeat):** STAR share-split math, client-side DP noise injection, total-ε-over-window accounting, k≥100 floor predicate.
  - **WS-3 (mobile/channels):** transcript-SAS truncation/strength-floor math, locale-string resolution, adapter message-shape formatting (WhatsApp/Signal Path B), tokio-layer pure adapters.
  - **WS-2 (distribution):** size-gate arithmetic, reproducible-build hash comparison, mirror-manifest schema, install-to-first-value timestamp-delta computation.
- **Acceptance criteria:**
  - Every NEW Python (or Rust binding-consumer) module a shard creates has ≥1 importing Tier-1 test (`/redteam` grep, empty = HIGH).
  - Tier-1 suite is offline + <1s/test; conftest stubs for newly-side-effecting internal methods do NOT leak to Tier 2/3 (conftest-scope per `rules/testing.md`).
- **Capacity check:** manifest-only (no new logic); aggregates per-shard seeds. **Within budget.**

---

## T-07-201 — Tier 2: real-infra integration suite (NO mocking) per workstream

- **Type:** Test
- **Value-anchor:** `rules/testing.md` § Tier 2 (real infrastructure; `@patch`/`MagicMock`/`unittest.mock` BLOCKED) + `00-objectives-to-deliverables.md` deliverables — the wiring layer that proves each facade actually connects to its real source. Mocks at the binding boundary hide FFI/connection/serialization failures that only surface against real infra.
- **Implements:** the Tier-2 row of the 3-tier contract across all 6 workstreams.
- **Depends:** the owning shard for each wiring test (per the map below).
- **Scope (per-workstream Tier-2 real-infra requirement + wiring tests):**
  - **WS-1 (runtime):** **both real runtimes** (`kailash-py` + `kailash-rs-bindings`) — no mocked runtime. `test_kailash_rs_bindings_runtime_wiring` (all 30 methods forward to the real Rust core; sync/async shape per method); `test_runtime_switch_attestation_wiring` (real Vault cold-unlock + real binary_hash vs manifest). The BET-6 harness (T-07-204) is the centerpiece Tier-2 surface.
  - **WS-6 (substrate):** **real SQLite store + real `apscheduler` wall-clock.** `test_session_router_store_wiring` (durable projections persist + read-back across restart); `test_grant_moment_store_poll_rendezvous_wiring` (grant answered in a later process resumes via store-poll, NOT in-process Future); `test_classification_policy_tier2_wiring` (T-005 fail-closed). State-persistence read-back MANDATORY.
  - **WS-4 (library/skill):** **real Nexus registry + real classifier ensemble.** `test_nexus_registry_handlers_wiring` (HTTP/CLI/MCP tier-aware handlers, content-addressed by `canonical_bytes()`); `test_co_validator_ensemble_wiring` (the S9b dynamic-dispatch path against the REAL ensemble, not a mocked classifier).
  - **WS-5 (heartbeat):** **real OHTTP relay + real STAR aggregator.** `test_ohttp_relay_wiring` + `test_star_aggregator_k_anonymity_wiring` (k≥100 floor against the real aggregator); `test_signed_consent_grant_wiring` (consumes the real S4g grant path).
  - **WS-3 (mobile/channels):** **real channel sandboxes** (WhatsApp Business sandbox, signal-cli REST) + **real Flutter runtime.** `test_whatsapp_adapter_lifecycle`, `test_signal_path_b_adapter_lifecycle`, `test_qr_pairing_transcript_sas_wiring` (transcript-SAS against a real handshake, MITM-relay fixture yields mismatch).
  - **WS-2 (distribution):** **real built binary + real `strip` + real mirror endpoints.** `test_binary_size_gate_wiring` (real stripped binary measured); `test_reproducible_build_wiring` (real double-build byte-identity); `test_mirror_signature_wiring` (real N=3 mirror artifacts).
- **Acceptance criteria:**
  - Every facade (`*Runtime`, `*Router`, `*Registry`, `*Client`, `*Adapter`, `*Aggregator`) has a `test_<lowercase>_wiring` test importing through the facade and asserting an externally-observable effect.
  - Zero `@patch`/`MagicMock`/`unittest.mock` in any Tier-2 test (`/redteam` grep sweep); zero mocked runtime/relay/registry/channel.
  - Every paired crypto operation (sign/verify, seal/unseal, record_delegation/revoke, reproducible-build/attest) has a round-trip test THROUGH the facade.
  - Every state-mutating write is read-back-verified.
- **Capacity check:** manifest + wiring-test orchestration; logic lives in shards. **Within budget.**

---

## T-07-202 — Tier 3: real-binary E2E suite (read-back verified) per workstream

- **Type:** Test
- **Value-anchor:** `rules/testing.md` § Tier 3 (real everything; every write read-back-verified) + `rules/user-flow-validation.md` (the literal user walk caps each deliverable). Tier 3 is where the 10 per-EC acceptance batteries (Part 1) live; this todo is the cross-cutting E2E manifest + the cross-OS portability matrix.
- **Implements:** the Tier-3 row of the 3-tier contract; hosts T-07-220…T-07-229.
- **Depends:** the full shard set per EC (Part 1 dependency rows).
- **Scope (per-workstream Tier-3 E2E + cross-OS matrix):**
  - **WS-1:** runtime picker opt-out E2E (T-07-222) + the full BET-6 corpus on the real binary across the OS matrix (T-07-223). Cross-OS: macos-14, ubuntu-22.04/24.04, windows-2022 — byte-identity slice green on all.
  - **WS-6:** `init`/`grant`/`chat` end-to-end on the real binary against the real store; grant resumes across a real process restart (read-back).
  - **WS-4:** the 100-benign/3-adversarial CO-validator E2E against the real registry (T-07-226).
  - **WS-5:** the full opt-in → relay → aggregate heartbeat E2E (T-07-227).
  - **WS-3:** the 6-channel Grant Moment E2E (T-07-224) + the <30s mobile QR-pair on real iOS+Android (T-07-225).
  - **WS-2:** the 5-target build + boot (T-07-220), <50 MB size (T-07-221), N=3 reproducible+signed (T-07-228), install-to-first-value <10min (T-07-229).
- **Acceptance criteria:**
  - Every Tier-3 battery runs against the REAL codename binary (not a Python-process emulation) where the EC names a binary deliverable.
  - Every state-mutating E2E step is read-back-verified (write, then read, assert).
  - The cross-OS portability matrix is green for every byte-identity-bearing surface (conformance, ledger canonical JSON, reproducible builds).
  - Each Tier-3 battery embeds a user-flow walk receipt per `rules/user-flow-validation.md` MUST-2 (verbatim command + output + disposition), scrubbed per MUST-6.
- **Capacity check:** manifest hosting the 10 EC batteries; orchestration only. **Within budget.**

---

## T-07-204 — BET-6 cross-runtime conformance harness (the load-bearing artifact)

- **Type:** Test
- **Value-anchor:** `00-objectives-to-deliverables.md` EC-02.4 row — flagged **"the highest correctness risk in the phase"** — and `02-plans/01-architecture.md` § critical path (S1 → S2a → S3b → S7v): the conformance harness is the spine the whole phase's correctness claim hangs on, and the SINGLE most important test artifact in Phase-02. It is what makes "the pure-Python opt-out behaves identically, only slower" a verifiable claim (BET-6) rather than a promise, and it feeds the mandatory Rust verifier (S7v / EC-9).
- **Implements:** EC-02.4; `specs/runtime-abstraction.md` § Conformance vectors (N1–N6 `:149-154`, E1–E7 `:190-196`); contract-tier metadata (`:139-143`). The harness skeleton is S1; this todo is the harness as a cross-cutting artifact consumed by T-07-223 (EC-02.4 acceptance) and reused by S3b/S7v (shared E7 corpus).
- **Depends:** S1 (skeleton + tier metadata + dispatch-observation hook). The vector families are authored in S2b/S2c/S3a/S3b; this todo is the harness machinery + scorer + corpus contract that those shards populate.
- **Scope:** The parametrized harness over `get_runtime(family=...)` (the ONE seam, `selection.py`) running `["kailash-py","kailash-rs-bindings"]` × every vector. **Phase-02 conformance = byte-identity (hash-equality) across N1–N6-structured + E1–E7.** Two pluggable scorers: (a) the byte-identity scorer (canonical-JSON hash-equality with field-level diff localization — first differing byte offset + JSON path, NOT bare `assert a == b`); (b) the dispatch-observation scorer for N3's structural-vs-semantic partition (deterministic "did the classifier dispatch" check, NOT a probe). **N4's rendered verdict TEXT is the ONE semantic-equivalence slice and is explicitly Phase-03** (`runtime-abstraction.md:152,207`); its scoring metric is an open Phase-03 spec question (`:239`). This harness asserts N4 **structured-payload** byte-identity only and MUST NOT author a probe/semantic-scorer for N4 rendered text in Phase-02. E7 head-commitment-monotonicity vectors are sourced from the SINGLE shared corpus (git-submodule-pin or vendored versioned fixture) so S3b's harness and S7v's verifier consume ONE E7 truth.
- **Acceptance criteria (the measurable gate):**
  - The harness collects under `tests/conformance/`, parametrizes both runtimes × every vector, and emits test IDs of the form `test_<family>[<runtime>-<vector_id>]` (the runtime axis is visible in the failure line for localization).
  - Byte-identity scorer: on mismatch, emits both canonical-JSON sides + first differing byte offset + JSON path; a bare `assert a == b` is BLOCKED.
  - N3 dispatch-observation: structural-class checks record ZERO classifier dispatch; semantic-class checks record dispatch-occurred — both deterministic, NOT probe-judged.
  - N4 **structured-payload** byte-identity asserted; a reviewer sweep confirms NO semantic scorer fires on N4 rendered text this phase (rendered-text equivalence = Phase-03 deferred row).
  - E7 vectors come from the single shared corpus S7v consumes (one truth, not two) — verified at authoring time.
  - The harness is the gate `RS_BINDINGS_ENABLED` flips on: the flag flips ONLY after the FULL byte-identity corpus is green on both runtimes.
  - Tier: **Tier 2** (both real runtimes; NO mocked runtime) graduating to **Tier 3** on the real binary; byte-identity slice green on the full OS matrix.
- **Capacity check:** invariants ≈ 5 (byte-identity scorer + field-diff, N3 dispatch-observation determinism, N4-structured-only / no-rendered-probe, single-E7-corpus source, flag-flip gate); call-graph hops ≈ 3 (corpus loader → scorer → `get_runtime` seam → adapter); LOC ≈ 350 (harness machinery + 2 scorers; the vectors are data authored in S2b–S3b). Live loop (hash-equality). **Within budget. This is the phase's load-bearing test artifact — the shared-E7-corpus decision is the coordination point with S3b + S7v.**

---

## Cross-references

- Per-EC mapping: `01-analysis/00-objectives-to-deliverables.md` (EC-02.1…02.10 → workstream/deliverable/risk/legal-gate).
- Shard map + conformance centrality: `02-plans/01-architecture.md` (31 shards; critical path S1 → S2a → S3b → S7v).
- Canonical exit-criteria line: `specs/acceptance-metrics.md:32`.
- 3-tier convention precedent: `workspaces/phase-01-mvp/02-plans/02-test-strategy.md` + `workspaces/phase-01-mvp/todos/active/{07,08}-*.md`.
- Tier discipline: `.claude/rules/testing.md` (Tier 2/3 real infra, NO mocking; E2E pipeline regression; state-persistence read-back).
- Probe-driven semantic checks: `.claude/rules/probe-driven-verification.md` (N4 rendered-text Phase-03; CO-validator inferred-permission verdicts).
- User-flow walk: `.claude/rules/user-flow-validation.md` (Tier-3 batteries embed verbatim receipts, scrubbed).
- Milestone files (per-shard acceptance): `01..06-m*.md`.
