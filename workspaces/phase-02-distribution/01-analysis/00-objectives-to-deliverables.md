# Phase 02 — Objectives → Deliverables Mapping

**Role:** The spine of Phase-02 `/analyze`. Maps every Phase-02 exit criterion (`ROADMAP.md:100-108` + `acceptance-metrics.md:30-32`) to the concrete deliverable that satisfies it, the workstream that owns it, the central risk, and the legal-gate status. Phase-02 `/analyze` is _implementation architecture_, not architecture re-derivation (Phase-00 froze the architecture; Phase-01 established the implementation patterns). This doc re-interprets the generic `/analyze` workflow for an already-frozen-architecture phase, exactly as the Phase-01 brief did.

**Date:** 2026-06-08. **Status:** DRAFT (analysis in progress).

---

## `/analyze` step re-interpretation for Phase-02

| Generic `/analyze` step                | Phase-00/01 status                     | Phase-02 `/analyze` produces                                                                                                        |
| -------------------------------------- | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Objectives                             | DONE (ROADMAP §74)                     | This mapping doc                                                                                                                    |
| Deep research                          | DONE for architecture                  | Implementation deep-dives per workstream (`01-research/`)                                                                           |
| Product focus / USPs                   | DONE (Phase-00 thesis BETs)            | N/A — frozen                                                                                                                        |
| Platform-model / AAA / network-effects | DONE (Phase-00)                        | N/A — frozen                                                                                                                        |
| User flows                             | partial                                | Phase-02-specific flows (`03-user-flows/`): runtime picker, mobile QR-pair, library publish/install, SKILL ingest, heartbeat opt-in |
| Plans                                  | partial                                | Legal-gate-aware build sequence + sharding + conformance-harness design (`02-plans/`)                                               |
| specs/                                 | EXISTS, frozen (37 files)              | Identify Phase-02 implementation GAPS — additions only; edits trigger `specs-authority.md` 5b                                       |
| Red team                               | Phase-00 6 rounds + Phase-01 converged | New Phase-02-implementation red-team rounds                                                                                         |

---

## Exit criterion → deliverable mapping

| #        | Exit criterion (source)                                                           | Workstream | Deliverable                                                                                                                                                                          | Central risk                                                         | Legal-gated?                                                                                                                              |
| -------- | --------------------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| EC-02.1  | Rust binary builds on 5 targets (`ROADMAP.md:101`)                                | WS-2       | CI cross-compile matrix (macOS arm64/x86_64, Linux x86_64/arm64/musl, Windows x86_64)                                                                                                | musl + Windows embedded-interpreter packaging                        | partial (redistribution only — building crypto binaries is NOT export-controlled; cross-border _redistribution_ is, per EAR 742.15(b)(1)) |
| EC-02.2  | Binary <50 MB with embedded Python (`ROADMAP.md:102`)                             | WS-2       | Embedding strategy (PyO3 vs uv-managed) + strip + size CI gate `test_binary_size_under_50mb.py`                                                                                      | 50 MB ceiling with CPython + deps is tight                           | partial                                                                                                                                   |
| EC-02.3  | Runtime picker; pure-Python opt-out E2E (`ROADMAP.md:103`)                        | WS-1       | First-run picker + `envoy runtime switch` + attestation-on-switch                                                                                                                    | clean opt-out path through a Rust-default binary                     | **YES** (ADR-0009 board)                                                                                                                  |
| EC-02.4  | Cross-runtime conformance vectors pass (`ROADMAP.md:104`)                         | WS-1       | N1–N6 + E1–E7 **byte-identical** two-runtime harness (BET-6); N4 rendered-text semantic-equivalence is Phase-03 (`runtime-abstraction.md:152,207`) — corrected per `journal/0004` R3 | **highest correctness risk in the phase**                            | no                                                                                                                                        |
| EC-02.5  | 6 channels pass E2E Grant Moment → action → audit (`ROADMAP.md:105`)              | WS-3       | WhatsApp + Signal **Path B** adapters + tokio async layer (iMessage native + Signal Path A de-scoped to Phase-04)                                                                    | WhatsApp launch blocked on a business pricing gate (not engineering) | partial                                                                                                                                   |
| EC-02.6  | Mobile QR-pair <30 s cold start (`ROADMAP.md:106`)                                | WS-3       | Flutter iOS+Android + QR-pairing protocol                                                                                                                                            | pairing-protocol security (T-class) + cold-start budget              | partial (app-store)                                                                                                                       |
| EC-02.7  | CO validator rejects 3 adversarial + accepts 100 benign skills (`ROADMAP.md:107`) | WS-4       | SKILL.md translator + CO-compliance validator + declared-vs-inferred code analysis                                                                                                   | false-positive budget on inferred-permission analysis                | no                                                                                                                                        |
| EC-02.8  | Foundation Health Heartbeat functional (`acceptance-metrics.md:31`)               | WS-5       | OHTTP server+relay + STAR/Prio aggregator + DP + signed consent                                                                                                                      | k-anonymity k≥100 + DP ε calibration                                 | no                                                                                                                                        |
| EC-02.9  | N=3 mirrors signed + reproducible-build stream (`acceptance-metrics.md:31`)       | WS-2       | Mirror layer + signing-key rotation + reproducible builds                                                                                                                            | reproducible-build determinism across 5 targets                      | **YES**                                                                                                                                   |
| EC-02.10 | Install-to-first-value <10 min mobile (`distribution.md:59`)                      | WS-2/3     | First-run offline-model bundle + onboarding flow → **shard S17** (`distribution.md:66`; ADR-0006 degraded-mode zero-network path)                                                    | offline-model bundle size vs the 50 MB ceiling                       | partial                                                                                                                                   |

**Enabling (not exit-gated but load-bearing):**

| Item                                                                  | Workstream | Why it's load-bearing                                                                                                                                                               |
| --------------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Durable persistent substrate + long-running session model             | WS-6       | Single shared blocker for `init`/`chat`/`grant` (the last 3 of 10 CLI commands) — `mvp-build-sequence.md:209`, `journal/0048`                                                       |
| Verifier Rust crate MANDATORY (`cargo install envoy-ledger-verifier`) | WS-6       | Closes EC-9 cross-language source-isolation; resolves Phase-01 forest F2/F4; reuses the WS-1 conformance vectors                                                                    |
| Full `ClassificationPolicy` Tier-2 wiring                             | WS-6       | T-01-21 deferral; `@classify` + clearance + masking + T-005 fail-closed (`classification-policy.md:106-111`)                                                                        |
| Envelope Library registry (Foundation-Verified tier)                  | WS-4       | Hosts the CO-validated skills WS-4 produces; `foundation-ops.md:17`                                                                                                                 |
| EnterpriseDeploymentRecord schema + verifier + dual-sign gate         | WS-4       | Phase-02 deliverable (`enterprise-deployment.md:15`); shares `verify_steward_quorum`; ships WITH cross-runtime conformance. Disablement=Phase-03, pilots=Phase-04 (out) — R1-HIGH-2 |
| 6-language localization (en-GB/es-ES/de-DE/fr-FR/zh-CN/ja-JP)         | WS-3       | Brief WS-3 (`ui-platform.md:37`); was dropped from the round-1 shard map — folded into S13 — R1-HIGH-3                                                                              |

---

## Legal-gate dependency map (the sequencing constraint)

Phase-00 external gates are still OPEN (`ROADMAP.md:11-37`, nearly all `[ ]`). They gate **release**, not **build**:

```
                          ┌─────────────────────────────────────────┐
 BUILDABLE NOW            │  RELEASE-GATED ON OPEN LEGAL APPROVALS    │
 (no external gate)       │                                           │
 ─────────────────       │  trademark close ──► public install names │
 WS-1 runtime code        │  composite LICENSE + export-control ──►   │
 WS-4 library + skill     │                       Rust binary redist  │
 WS-5 heartbeat infra     │  ADR-0009 board endorse ──► runtime model │
 WS-6 durable substrate   │                                           │
 WS-3 engineering         │  app-store identity ──► mobile listing    │
 ─────────────────       └─────────────────────────────────────────┘
        │                              ▲
        └──── front-load these ────────┘ (release tail waits on human gates)
```

**Recommended sequencing (for `/todos` to confirm):** build WS-1/4/5/6 + WS-3 engineering in parallel waves now; isolate WS-2 release + public-facing WS-3 listing behind the legal gates as a tail. ADR-0009 board endorsement is the one gate that could force WS-1 _rework_ (low risk — Phase-00 froze the architecture around it) rather than merely delaying release.

---

## Research deep-dive index (`01-research/`)

| Doc                                     | Workstream | Hard questions the deep-dive must answer                                                                                            |
| --------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `01-ws1-runtime-pluggability.md`        | WS-1       | Conformance-harness design (byte-identity + semantic); PyO3 vs uv embedding; second-impl wiring; attestation-on-switch              |
| `02-ws2-distribution.md`                | WS-2       | 5-target build matrix; <50 MB embedding; N=3 mirror + reproducible-build + key rotation; legal-gate isolation                       |
| `03-ws3-mobile-channels.md`             | WS-3       | Flutter client + QR-pairing protocol/security; 3 deferred adapters; tokio async layer; native keychain                              |
| `04-ws4-library-skill-ingest.md`        | WS-4       | Nexus-backed registry; FV 2-of-N signing ceremony; SKILL→envelope translator; declared-vs-inferred CO validator                     |
| `05-ws5-foundation-health-heartbeat.md` | WS-5       | OHTTP server+relay; STAR/Prio aggregator; DP ε calibration; signed-consent flow; the 4 deferred modules                             |
| `06-ws6-durable-substrate.md`           | WS-6       | The persistent-session model unblocking init/chat/grant; SessionObservedState; ClassificationPolicy Tier-2; mandatory Rust verifier |
