# 11 — Acceptance Metrics

**Document status:** draft v1 — ready for `/redteam`
**Scope:** Per-phase exit criteria operationalized as measurable signals. Instrumentation plan (opt-in via Foundation Health Heartbeat per doc 00 v3 §4.1 item 7a). Pass/fail criteria, blocking signals, kill-criteria thresholds.
**Sources:** doc 00 v3 (§3.1 phase exit criteria, §5 bets, §5.0 measurement methodology, §7 kill criteria), doc 02 v3 (Authorship Score), doc 09 v3 (T-019 habituation, T-020/T-022/T-092 supply-chain metrics), doc 01 v2 (ritual engagement flags).

---

## 1. Measurement substrate (doc 00 v3 §5.0)

Every metric declares its collection substrate:

- **[Heartbeat]** — STAR/Prio k-anonymous aggregated, opt-in per doc 00 §4.1 item 7a.
- **[Public]** — public-discourse signals (HN, X, forum, blog).
- **[Library]** — Envelope Library fetch/publish counts (Foundation-operated).
- **[GitHub]** — stars, forks, issues, downloads (public).
- **[Legal]** — counsel-confirmed milestones.
- **[Ops]** — Foundation-ops internal metrics (reviewer queue, incident count).

Metrics that cannot be collected under doc 00 §4.1 non-goals are **explicitly unmeasurable** and are either (a) dropped, (b) replaced by indirect proxies, or (c) gated on Heartbeat opt-in.

---

## 2. Phase 00 exit

Per doc 00 v3 §3.1 Phase 00:

| Criterion                                            | Substrate  | Pass threshold                                                                          |
| ---------------------------------------------------- | ---------- | --------------------------------------------------------------------------------------- |
| Trademark sweep passed                               | [Legal]    | USPTO + EUIPO + UK IPO cleared; final mark selected                                     |
| Namespace reservations                               | [GitHub]   | GitHub org + npm + PyPI + crates.io reserved                                            |
| Foundation board endorsement of runtime-pluggability | [Legal]    | Board-signed endorsement                                                                |
| 7 ADR-0009 legal counsel items                       | [Legal]    | Each item resolved or parked with disclosure                                            |
| 39 GH issues filed                                   | [GitHub]   | All filed + tracked to closure OR explicit Envoy-new-code scope                         |
| Algorithm-identifier schema landing                  | [GitHub]   | mint#6 + kailash-py#604 + kailash-rs#519 closed OR Envoy-local impl scoped              |
| Deep audits completed                                | [Internal] | 01-kailash-rs-deep-audit + 02-kailash-py-survey + 03-primitive-reconciliation published |
| PACT N4/N5 Python runner                             | [GitHub]   | kailash-py#605 closed                                                                   |
| `DataFlow.execute_raw()` SQLi fix                    | [GitHub]   | kailash-rs#520 closed                                                                   |
| 12 analysis docs converged                           | [Internal] | 0 CRIT + ≤ 2 HIGH across Round 2 each                                                   |
| specs/ derived + redteamed                           | [Internal] | 0 HIGH across 2 consecutive full-sibling rounds                                         |

## 3. Phase 01 exit

Per doc 00 v3 §3.1 Phase 01:

| Criterion                                                          | Substrate            | Pass threshold                                                                                      |
| ------------------------------------------------------------------ | -------------------- | --------------------------------------------------------------------------------------------------- |
| 1 first-time user completes Boundary Conversation end-to-end       | [Heartbeat / Public] | `completed_boundary_conversation` flag reported; or public demo recording                           |
| 3 Grant Moments triggered + resolved                               | [Heartbeat]          | `grant_moment_count ≥ 3` per test-install                                                           |
| Daily Digest renders at scheduled time                             | [Internal test]      | Integration test green                                                                              |
| Envoy Ledger exports verifiable hash-chained log                   | [Internal test]      | Independent reference-verifier runs green                                                           |
| Trust Vault backup via SLIP-0039 Shamir works (3-of-5 reconstruct) | [Internal test]      | Integration test green                                                                              |
| Redteam 2 clean rounds 0 CRIT/HIGH                                 | [Internal]           | Meets exit criteria                                                                                 |
| 6 messaging channels operational end-to-end                        | [Internal test]      | iMessage-BlueBubbles + Telegram + Slack + Discord + WhatsApp + Signal Grant Moment → action → audit |
| Algorithm-identifier schema live                                   | [Internal test]      | Signed records carry algorithm tags                                                                 |
| Authorship Score + posture-ratchet gate enforced                   | [Internal test]      | User at N<3 blocked from DELEGATING                                                                 |

## 4. Phase 02 exit

| Criterion                                         | Substrate                   | Pass threshold                                                |
| ------------------------------------------------- | --------------------------- | ------------------------------------------------------------- |
| Rust binary builds on 5 targets                   | [Internal]                  | macOS arm64/x86_64, Linux arm64/x86_64/musl, Windows x86_64   |
| Binary size <50 MB with embedded Python           | [Internal]                  | Binary size measurement                                       |
| Runtime picker works end-to-end                   | [Internal test]             | Switch kailash-rs ↔ kailash-py; vault compatibility preserved |
| Cross-runtime conformance vectors pass            | [Internal test]             | PACT N1–N6 + Envoy E1–E7 byte-identity                        |
| 6 channels pass E2E Grant Moment → action → audit | [Internal test]             | Per-channel tests green                                       |
| Mobile QR-pairing <30s cold start                 | [Internal test]             | Flutter integration test                                      |
| CO validator: 3 adversarial + 100 benign corpus   | [Internal test]             | 100% reject adversarial; ≥95% accept benign                   |
| Foundation Health Heartbeat ready                 | [Internal test]             | STAR + OHTTP + DP + signed-consent Grant Moment functional    |
| N=3 binary mirrors signed + active                | [Ops]                       | Three independent mirrors verified                            |
| Reproducible-build verification stream live       | [Ops]                       | Third-party reproduction published                            |
| install-to-first-value <10 min on mobile          | [Internal test + Heartbeat] | Median first-time user reaches first tool-call in <10 min     |
| Classifier ensemble v1 shipped                    | [Internal test]             | Per-classifier metrics documented + release-gate              |

## 5. Phase 03 exit

| Criterion                                            | Substrate            | Pass threshold                                                      |
| ---------------------------------------------------- | -------------------- | ------------------------------------------------------------------- |
| Hot-path P50 latency <10ms (Rust runtime)            | [Internal benchmark] | Envelope check P50 across standard workload                         |
| Pure-Python runtime P50 <80ms                        | [Internal benchmark] | Same workload                                                       |
| Envelope Library Community tier accepting publishes  | [Library]            | >100 Community-tier envelopes published with signature verification |
| Shared Household 5-person family E2E                 | [Internal test]      | Integration test green                                              |
| Per-dimension posture slider (5×5)                   | [Internal test]      | Per-principal per-dimension posture operational                     |
| Weekly Posture Review + Monthly Trust Report rituals | [Heartbeat]          | Engagement metrics collected                                        |
| Cross-SDK conformance vectors pass both runtimes     | [Internal test]      | BET-6 byte-identity                                                 |
| Annual posture-revalidation implemented              | [Internal test]      | Posture decays at 12mo; user re-authorizes                          |

## 6. Phase 04 exit

| Criterion                                           | Substrate       | Pass threshold                          |
| --------------------------------------------------- | --------------- | --------------------------------------- |
| 23+ messaging channels active                       | [Internal test] | Per-channel tests green                 |
| 3 production Rust skills published to FV tier       | [Library]       | FV tier count                           |
| 2 enterprise pilots on Organization-tier registries | [Ops]           | Pilot agreements signed + operational   |
| Hidden-envelope deniability primitive               | [Internal test] | Phase 04 Phase 11 test                  |
| Multi-provider verification for high-stakes actions | [Internal test] | Claude + OpenAI + local-Ollama ensemble |
| WASM skill sandbox audited                          | [Ops]           | External security audit passed          |

## 7. Un-phased regulated-industry readiness

Per doc 00 v3 §3.1 + doc 09 §1.2 — un-phased. Readiness (not certification) tracked:

| Criterion                            | Substrate  | Target                                                  |
| ------------------------------------ | ---------- | ------------------------------------------------------- |
| SOC2 Type 1 audit-ready architecture | [Ops]      | External auditor review                                 |
| HIPAA-ready deployment template      | [Ops]      | Third-party managed-Envoy operator can act as BAA party |
| GDPR DPIA tooling                    | [Ops]      | DPO-usable export + retention policy enforcement        |
| Federated Trust Mesh spec            | [Internal] | Cross-org delegation protocol drafted at mint           |

Enterprise certification is a DEPLOYMENT concern, not an Envoy-core concern. Third-party commercial operators certify their deployments.

---

## 8. BET-falsification thresholds (doc 00 v3 §5)

### BET-1 — Authorship thesis holds

- **[Heartbeat] fires disconfirm:** <20% of Phase 02 cohort has Authorship Score ≥ 3 at 30 days post-install.
- **[Heartbeat] fires disconfirm:** median score <1 at 60 days.
- **[Library] fires disconfirm:** FV fetch ≫ Community publish — consumption not authorship.

### BET-2 — Structural + semantic partition

- **[Benchmark] fires disconfirm:** structural P50 >20ms OR semantic P50 >1000ms cached.

### BET-3 — Sovereignty moat durable

- **[Heartbeat opt-in survey] fires disconfirm:** <30% cite sovereignty reasons.
- **[Public] fires disconfirm:** OS-integrated agent products ship envelope-equivalent governance within 24mo.

### BET-4 — Foundation stewardship asset

- **[Public] fires disconfirm:** >15% of Envoy-mentioning threads invoke "Foundation" pejoratively over 12mo rolling.

### BET-5 — Prosumer-first motion

- **[Heartbeat] fires disconfirm:** <5% of Phase 02-cohort installs add second principal in first 3mo of Phase 03.

### BET-6 — Contract parity

- **[Internal test] fires disconfirm:** >20 contract-surface divergences at Phase 02 exit.

### BET-7 — SKILL.md compat

- **[Internal test] fires disconfirm:** CO validator rejects >50% of real-world corpus OR accepts adversarial-test skills.
- **[Heartbeat] fires disconfirm:** force_install rate >30% of all skill installs.

### BET-8 — Habit formation

- **[Heartbeat] fires disconfirm:** <20% of active users open Daily Digest twice in any 7-day window after Phase 02.

### BET-9a — Upstream primitives

- **[GitHub] fires disconfirm:** Primitive reconciliation surfaces ≥3 genuinely-absent (Type C) primitives.

### BET-9b — Binding exposure

- **[GitHub] fires disconfirm:** >N binding issues remain open at Phase 01 entry.

### BET-10 — Legal/regulatory stack

- **[Legal] fires disconfirm:** Counsel identifies unresolvable composite-license conflict OR FOSSA/Snyk/Sonatype flag at CRITICAL level.

### BET-12 — Governance-primary-surface palatability

- **[Heartbeat] fires disconfirm:** Active-user share of AI-curious TAM ≤1% at Phase 02+.
- **[Heartbeat] fires disconfirm:** <10% of active users at DELEGATING+ posture at 90 days.

---

## 9. Kill-criteria operationalized (doc 00 v3 §7)

### Item 1 — 18mo post-Phase-01 WAU floor

- **[Heartbeat] + [Library] dual-signal:** <1000 STAR-aggregated WAU AND <500 FV fetches/week at 18mo → thesis-kill trigger.

### Item 2 — ≥3 bets disconfirmed simultaneously

- Any three of BET-1 through BET-12 disconfirmed in the same Monthly Trust Report window → 6mo targeted-experiment countdown begins.

### Item 3 — Foundation board declines runtime-pluggability

- Non-recoverable → thesis re-announced.

### Item 4 — Categorically-better alternative

- Triggers if alternative passes all 5 §8 primary-surface tests + all 4 §4.1 non-commercial properties + 3× within-niche adoption for 24mo + 2 independent Foundation-unaffiliated steward confirmations.

### Item 5 — Legal categorical blocker

- Unresolvable composite-license OR export-control OR charter-compatibility → thesis re-announced.

---

## 10. Instrumentation implementation notes

- Heartbeat client (doc 00 §3.3) batches counters + sends once/week via OHTTP + STAR.
- Opt-in Grant Moment at Phase 02 install; default NO per §4.1 item 7a.
- Public signal collection: manual + RSS aggregator for now (Phase 03 tooling).
- Library metrics: Foundation-operated Nexus endpoint counts fetches with k-anonymity.
- Benchmark signals: internal CI performance-regression gates; not user-visible.

---

## 11. Cross-references

- doc 00 v3 §3.1 phases + §5 bets + §7 kill criteria + §5.0 measurement.
- doc 02 v3 Authorship Score thresholds.
- doc 09 v3 threat-mitigation test locations.
- doc 01 v2 ritual engagement flags.

## 12. Open questions

1. Heartbeat opt-in rate target — what's "enough" participation for kill criteria to fire reliably? k≥100 bounded individual identification, but aggregate metrics need higher participation.
2. Bet re-evaluation cadence — quarterly vs continuous? Proposal: quarterly Foundation review.
3. Public-signal aggregation automation — Phase 03 tooling OR manual indefinitely?
4. "Standard workload" for benchmark — curated + signed by Foundation OR community-contributed?

**End of doc 11 v1.**
