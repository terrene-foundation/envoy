# Phase 02 — Implementation Architecture & Build Sequence

**Role:** The `/analyze` synthesis that `/todos` consumes. Integrates the 6 workstream deep-dives (`01-analysis/01-research/0{1..6}-ws*.md`) into: the brief-corrections gate, the cross-workstream dependency graph, the legal-gate-aware build sequence, and the sharding plan (per `rules/autonomous-execution.md` capacity budget).

**Date:** 2026-06-08. **Status:** CONVERGED (substantive) — red-team rounds 1–5 (`journal/0002`–`0006`); R5 clean (0 CRIT/0 HIGH × 3 lenses). `/todos`-ready. (R6 optional to formally close the EC-6 2-consecutive-clean bar.)

---

## Brief corrections (THE GATE — per `rules/agents.md`)

Full detail + receipts in `journal/0001` (re-verified accurate by the round-1 + round-2 closure agents). Summary:

1. **C1 (HIGH) — `RuntimeBackendNotWired` is phantom.** Real Phase-01 stub: `Phase02SubstrateNotWiredError` (`envoy/runtime/errors.py:91`).
2. **C2 (HIGH) — Phase-01 shipped 5 of 8 surfaces, not 8.** WhatsApp/iMessage/Signal are **greenfield** adapter builds.
3. **C3 (MED) — heartbeat is a 5-stub partition** (the 5th, `HeartbeatClient.maybe_record_flag`, is the real hot-path seam).
4. **C4 (MED) — `SessionRouter` is greenfield** (no `session.py`).
5. **C5 (LOW) — citation drift** (`OhttpClient` casing; `journal/0048` "6/10" is a stale pre-ledger snapshot; live is 7/10).

These correct the _starting state_, not the _scope_. SMS is NOT a target channel (Phase-04) — the EC-02.5 "6" = {CLI, Web, Telegram, Slack, Discord} + WhatsApp + Signal (Path B), excluding de-scoped iMessage + Signal Path A.

---

## Cross-workstream dependency graph (round-2 corrected — acyclic; critical path depth-4)

```
WS-1 (runtime) ──┬──► WS-3 channels+QR (AKE vectors feed S1 harness)
  S1 harness     ├──► WS-6 verifier S7v (reuses byte-identity vectors → EC-9)
  S2a/b/c N-vec  ├──► WS-2 S15 (embedding decision blocks the <50MB size-gate)
  S3a/b E-vec    │
  S3p/S3t picker │
WS-6 substrate ──┼──► init/grant/chat + deferred cluster
  S4s store      │     (grant/chat need a rendezvous-mechanism change — store-poll PRIMARY — NOT the store alone)
WS-4 quorum ─────┼──► Envelope Library FV + classifier registry + EnterpriseDeploymentRecord verifier
  S8 quorum      │     CO-validator step-5 (S9b) ──► depends on WS-6 ClassificationPolicy (S6a)
WS-5 heartbeat ──┴──► consumes WS-6 grant-moment path (S4g) for signed consent
WS-2 distribution ──► packages WS-1 binary; RELEASE gated on legal (Track B)
```

**Critical path = depth-4: S1 → S2a → S3b → S7v** (the WS-1 byte-identical conformance chain feeding the verifier is the real long pole; E7 monotonicity lives in S3b, which S7v consumes). **WS-6 off S4s is depth-3, not a serial chain:** S4s (store) gates a _parallelizable level-2 wave_ {S4i, S4r, S5b, S6a, S6b}; level-3 = {S4g (←S4r), S5o (←S5b)}; level-4 = {S6c (←S4r,S5b,S5o)}. (S7v sits on the WS-1 critical path via S3b, not the S4s wave.) The genuine WS-6 serialization constraint is NOT dependency depth but **SAME-class merge contention** — most WS-6 shards touch `runtime.py`/the store, so they cannot be worktree-parallelized safely even though the DAG permits it (per `rules/worktree-isolation.md` + `multi-operator-coordination.md` SAME-class).

---

## Key design verdicts (round-2 corrected)

| WS   | Verdict                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | Cons / risk (honest)                                                                                                                                                                                                                               |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| WS-1 | **PyO3 compile-time embed**; land contract-tier Protocol metadata + a cross-runtime **dispatch-observation hook** FIRST, then ONE parametrized harness over both runtimes via `get_runtime()`. Keep `kailash-py` default until the corpus is green.                                                                                                                                                                                                                                                   | Couples binary to a CPython ABI; 30-method adapter + large vector corpus → shard by conformance family. 50 MB cap is tight.                                                                                                                        |
| WS-2 | Mostly-static + `python-build-standalone` musl artifact + Alpine import-smoke Tier-3 gate; offline model is a SEPARATE artifact. **musl gets its own shard (S15m)** — the single HIGH-risk cell must not poison the routine-5 size-gate.                                                                                                                                                                                                                                                              | musl-static + embedded CPython (`dlopen` breaks under full-static) is the HIGH-risk cell; S15m carries a defer-to-linux-gnu-only fallback valve.                                                                                                   |
| WS-3 | QR-pairing as SAS/AKE; **the SAS is a truncated hash of the handshake TRANSCRIPT** (not the visible secret) rendered on both screens — MITM → different transcript → mismatch. **SAS strength floor: ≤2⁻²⁰ residual blind-relay MITM probability (≥ ~7 numeric digits / equivalent), rendering format pinned in the threat-model addition.** Phone render-only; pairing = signed Ledger event. De-scope iMessage + Signal Path A.                                                                     | New trust boundary → threat-model device-pairing addition REQUIRED (transcript-binding + strength floor). SPAKE2-vs-Noise-XX is an early-`/todos` decision (couples S13 FFI + S1 AKE vectors). WhatsApp launch blocked on a business pricing gate. |
| WS-4 | ONE tier-aware Nexus handler set; content-addressed by `canonical_bytes()`; consumer re-verifies sigs locally. CO validator: asymmetric comparison + score-band routing. Build `verify_steward_quorum` ONCE (shared: library + classifier registry + EnterpriseDeploymentRecord verifier).                                                                                                                                                                                                            | EC-02.7 "0 false-neg on 3 adversarial" is split: **2 via AST (S9a) + 1 dynamic-dispatch via ensemble (S9b)** — stated per-shard so S9a doesn't ship a gate it structurally can't meet. 0%/0% is corpus-specific (100/3).                           |
| WS-5 | **STAR (single-server)**; client-side local DP per-counter injected before share-split. **Privacy claim is a TOTAL ε over a stated window** (per-counter ε does NOT compose across N counters × M heartbeats); pin whether the k≥100 floor reads the noised or true cohort count.                                                                                                                                                                                                                     | STAR can't compute arbitrary stats (Phase-04 → Prio). k≥100 makes telemetry inert at <100 total users (signal gap, not a leak).                                                                                                                    |
| WS-6 | **STORE for durability; `grant`/`chat` ALSO need a rendezvous-mechanism change.** The in-process `asyncio.Future` (`grant_moment/runtime.py:305,743`) can't resume across processes → **store-poll with a monotonic-version re-check (PRIMARY; IPC-signal a per-platform optimization, NOT an OR — local IPC breaks on musl-static).** The rewrite MUST preserve the `GrantMomentExpiredError` timeout audit-row contract (`runtime.py:720-726`). `init` (write-once) is genuinely store-unblockable. | Rendezvous redesign touches `runtime.py:688-745` (load-bearing, audit-emitting). Session-boundary-reset invariant needs a shared owning shard (S5b).                                                                                               |

---

## Legal-gate-aware build sequence

Phase-00 external gates (trademark, composite LICENSE, export-control, ADR-0009 board) gate **release**, not **build**. Building crypto-bearing binaries is NOT export-controlled — only cross-border _redistribution_ is (EAR 742.15(b)(1), notification-email-satisfiable). EC-02.1 (binary build) is **buildable now**; only publish-under-trademarked-name + attach-composite-LICENSE + cross-border-redistribution are gated.

**Track A — buildable NOW, front-loaded (parallel worktree waves ≤3, SAME-class WS-6 shards serialized):**

1. **WS-1** — metadata + dispatch hook → harness → rs-adapter → conformance families → picker + attestation.
2. **WS-6** — store → rendezvous → init/BC → boundary-signal → observed-state → classification → envelope → chat → verifier.
3. **WS-4** — quorum → registry → FV + EnterpriseDeploymentRecord verify → CO validator + translator.
4. **WS-5** — OHTTP server → STAR client + DP → signed-consent (consumes WS-6 grant path).
5. **WS-3 engineering** — Flutter + QR transcript-SAS → WhatsApp + Signal Path B + tokio + localization → onboarding/offline-model.

**Track B — release tail (human legal gates):** WS-2 _release_ (publish-name / LICENSE / redistribution) + public WS-3 app-store listing.

**Roots (dependency-free, wave 1):** S1, S4s, S8, S10.

---

## Sharding plan (round-2 re-sharded — 31 shards — for `/todos` to finalize)

Per `rules/autonomous-execution.md` capacity budget. Loop column: **base** = no live loop until a substrate dependency lands (substrate-gated); **live** = deterministic loop within the shard. **Conformance-vector tiers (exact):** N1, N2, N5, N6 + N3 (structural-partition byte-identity on classification-only fixtures + deterministic dispatch-observation) + **N4 structured-payload** + **E1–E7** are all byte-identical / hash-equality → `live`. The ONE semantic-equivalence slice is **N4's rendered verdict TEXT** (structured payload byte-identical; rendered text semantically-equivalent across runtimes — `runtime-abstraction.md:152`). Its **placement is settled Phase-03** (the semantic-equivalence harness, `:207`); only its **scoring metric** is an OPEN spec question (`:239`). So Phase-02 conformance = byte-identity across every family (N1–N6 structured + E1–E7); the N4 rendered-text equivalence lands with the Phase-03 semantic harness.

| Shard | WS     | Scope (≤3 sentences)                                                                                                                                                                                         | Loop      | Depends     |
| ----- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------- | ----------- |
| S1    | WS-1   | Contract-tier Protocol metadata + cross-runtime dispatch-observation hook + harness skeleton over `get_runtime()`.                                                                                           | live      | —           |
| S2a   | WS-1   | rs-bindings adapter wiring behind the frozen interface (30 methods, 9 groups).                                                                                                                               | live      | S1          |
| S2b   | WS-1   | N1–N3 byte-identity vector families green (both runtimes).                                                                                                                                                   | live      | S2a         |
| S2c   | WS-1   | N4–N6 families: N5/N6 + N4 **structured-payload** byte-identity (N4's rendered verdict-TEXT semantic-equivalence is Phase-03 per `runtime-abstraction.md:152,207`; only its scoring metric is open, `:239`). | live      | S2a         |
| S3a   | WS-1   | E1–E4 **byte-identical** vectors (canonical JSON 67, Delegation signing 20, cascade-revoke set-equality 15, cycle detection 15) — hash-equality.                                                             | live      | S2a         |
| S3b   | WS-1   | E5–E7 **byte-identical** vectors (subset-proof verify 20, two-phase orphan resolution, head-commitment monotonicity ≥10) — hash-equality.                                                                    | live      | S2a         |
| S3p   | WS-1   | First-run runtime picker + `envoy runtime switch` UX state machine.                                                                                                                                          | live      | S2a         |
| S3t   | WS-1   | Attestation-on-switch (T-015 envelope re-read + T-060 binary-poisoning fail-closed).                                                                                                                         | live      | S3p         |
| S4s   | WS-6   | Store-backed `SessionRouter` + durable projections (pending-grant sub-store + observed-state region).                                                                                                        | live      | —           |
| S4r   | WS-6   | Decision-rendezvous: store-poll w/ monotonic-version re-check (PRIMARY); preserve `GrantMomentExpiredError` audit row; IPC a per-platform optimization.                                                      | live      | S4s         |
| S4i   | WS-6   | `init` / Boundary-Conversation bootstrap (write-once genesis; store-only).                                                                                                                                   | live      | S4s         |
| S4g   | WS-6   | `grant` interactive answer-in-later-command (consumes S4r; grant-moment persistence: monotonic-skew, 3-deep tree).                                                                                           | live      | S4r         |
| S5b   | WS-6   | **Session-boundary signal contract** (`session_boundary_crossed` emission on all triggers) + the T-013 reset invariant test. Shared owner.                                                                   | live      | S4s         |
| S5o   | WS-6   | SessionObservedState region (fingerprints, first-time-action gate, goal-reconfirm) consuming S5b's signal.                                                                                                   | base→live | S5b         |
| S6a   | WS-6   | ClassificationPolicy Tier-2 (`@classify`, clearance, MaskingStrategy, T-005 fail-closed, version-pinning) + F23 T-005/T-012 coverage gate.                                                                   | base→live | S4s         |
| S6b   | WS-6   | Full envelope-intersection (T-01-10) + clearance-level mapping layer.                                                                                                                                        | base→live | S4s         |
| S6c   | WS-6   | `chat` resident receive-loop (daemon-shaped; last) + integration test that a real chat boundary fires the S5b reset.                                                                                         | live      | S4r,S5b,S5o |
| S7v   | WS-6   | Mandatory Rust verifier crate (`cargo install`); reuses E7 head-commitment-monotonicity vectors (byte-identical, in S3b); closes EC-9 / F2→F4.                                                               | live      | S3b,S4s     |
| S8    | WS-4   | `verify_steward_quorum` + Nexus registry handlers (HTTP/CLI/MCP) + FV verify path.                                                                                                                           | live      | —           |
| S8e   | WS-4   | EnterpriseDeploymentRecord schema + verifier + dual-sign gate (shares quorum; ships with conformance).                                                                                                       | live      | S8          |
| S9a   | WS-4   | SKILL→envelope translator + CO validator steps 1-4,6 (AST + score-band); accountable for the **2 AST-catchable** adversarial samples.                                                                        | live      | S8          |
| S9b   | WS-4   | CO validator step-5 (classifier ensemble) — substrate-gated; accountable for the **1 dynamic-dispatch** adversarial sample.                                                                                  | base      | S8,S6a      |
| S10   | WS-5   | OHTTP key-config server + relay standup.                                                                                                                                                                     | live      | —           |
| S11   | WS-5   | STAR client crypto + k-anonymity (pin noised-vs-true floor) + client-side DP w/ total-ε-over-window accounting.                                                                                              | live      | S10         |
| S12   | WS-5   | Signed-consent Grant Moment + cascade-revoke (consumes S4g).                                                                                                                                                 | live      | S4g,S11     |
| S13   | WS-3   | Flutter client + QR transcript-SAS (strength floor) + threat-model device-pairing addition + 6-locale i18n + mobile screen-rec-detect + clipboard auto-clear.                                                | medium    | S1,S2a      |
| S14   | WS-3   | WhatsApp + Signal Path B adapters + tokio layer.                                                                                                                                                             | live      | S2a,S13     |
| S15   | WS-2   | 5 routine build targets (macOS arm64/x86_64, Linux x86_64/arm64, Windows x86_64) + <50MB embed (consumes WS-1 embedding decision) + size CI gate (codename).                                                 | live      | S2a         |
| S15m  | WS-2   | **musl** mostly-static + `python-build-standalone` + Alpine import-smoke Tier-3 gate; defer-to-gnu-only fallback valve.                                                                                      | live      | S15         |
| S16   | WS-2   | N=3 mirror + reproducible-build + key-rotation + install/upgrade/rollback/`--destroy-vault`/jurisdictional-advisory surface + legal-gate release CI checks.                                                  | live      | S15         |
| S17   | WS-2/3 | **First-run onboarding flow + offline-model bundle / ADR-0006 degraded-mode zero-network path + install-to-first-value <10min measured gate (EC-02.10).**                                                    | medium    | S13,S15     |

**31 shards.** Critical-path depth-4 + WS-6 SAME-class serialization → realistic **6–9 sessions** at waves of 3 (the long pole is WS-1's conformance chain + WS-6's serialized store-touching shards, not raw shard count). De-scope valve (NOT in the map, value-anchor required at `/todos` if pulled): iMessage native, Signal Path A, mobile native keychain, ECH/Tor, multi-device rebuild-from-replay (`data-model.md:99` Phase-02-optional).

---

## Spec gaps consolidated (additions only — NO edits this phase)

- Conformance contract-tier metadata + dispatch-observation hook absent from the runtime Protocol (`protocol.py:13`). (WS-1)
- Two `RuntimeIdentity` shapes (5-field vs 3-field). (WS-1)
- QR-pairing device trust boundary + transcript-SAS binding + **SAS strength floor** absent from `threat-model.md`. (WS-3)
- musl missing from the binary-size-gate enumeration. (WS-2)
- `runtime_switch` entry schema + picker config wire format undefined. (WS-1)
- N4 rendered verdict-text semantic-equivalence: placement settled Phase-03 (`runtime-abstraction.md:207`); only the scoring metric is an OPEN spec question (`:239`). (WS-1)
- Session-boundary signal contract (`session_boundary_crossed` triggers) under-specified for the multi-process model. (WS-6)
- Phantom citations C1/C2/C3 — a real spec edit triggers `specs-authority.md` 5b full-sibling re-derivation → bundle at a dedicated step.

---

## Remaining `/analyze` work (before phase-complete)

- [x] `01-analysis/` deep-dives + objectives spine; `02-plans/` architecture (rounds 1–5 corrected); `03-user-flows/`
- [x] `/redteam` rounds 1–5 — R5 clean (0 CRIT/0 HIGH × 3 lenses); design confirmed; `/todos`-ready
- [x] Journal: 0001 (corrections) + 0002–0006 (rounds 1–5 dispositions + convergence verdict)
- [ ] (optional) `/redteam` round 6 — formally close the EC-6 2-consecutive-clean bar
- [ ] **`/todos`** — human plan-approval gate: size + sequence the 31-shard map; confirm de-scope valve + the flagged `/todos` open questions (N4 scoring metric, SPAKE2-vs-Noise, store-poll interval, etc.)
