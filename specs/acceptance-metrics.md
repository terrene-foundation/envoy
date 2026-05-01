# acceptance-metrics

## Purpose

Per-phase exit criteria + instrumentation + BET-falsification thresholds + kill-criteria operationalization.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/11-acceptance-metrics.md v1`.
- **Threats mitigated:** Measures defense against every BET's attack surface.
- **BETs tested:** ALL (this spec is the measurement substrate for every BET).

## Measurement substrate (doc 00 v3 §5.0)

- **[Heartbeat]** STAR k-anonymous opt-in.
- **[Public]** HN/X/blog/forum.
- **[Library]** Envelope Library fetch/publish.
- **[GitHub]** stars/forks/issues/downloads.
- **[Legal]** counsel-confirmed.
- **[Ops]** Foundation-internal.

## Phase 00 exit criteria

Trademark sweep cleared; namespaces reserved; Foundation board endorsement; 7 ADR-0009 items resolved; 39 GH issues filed + tracked; algorithm-identifier schema landed (mint#6 + kailash-py#604 + kailash-rs#519); deep audits published; PACT N4/N5 runner (kailash-py#605); DataFlow SQLi fix (kailash-rs#520); 12 analysis docs converged 0 CRIT + ≤2 HIGH; specs/ redteamed 0 HIGH across 2 consecutive full-sibling rounds.

## Phase 01 exit criteria

1 user completes Boundary Conversation E2E; 3 Grant Moments resolved; Daily Digest scheduled delivery; Ledger export verifier green; Shamir 3-of-5 reconstruct; redteam 0 CRIT/HIGH; 6 messaging channels E2E; algorithm-identifier tagged signatures; Authorship Score posture-ratchet enforced.

## Phase 02 exit criteria

Binary builds 5 targets; binary <50 MB; runtime picker E2E; cross-runtime conformance vectors (N1–N6 + E1–E7); 6 channels pass; mobile QR-pair <30s; CO validator accepts 100 benign + rejects 3 adversarial; Foundation Health Heartbeat functional; N=3 mirrors signed; reproducible-build stream; install-to-first-value <10min mobile.

## Phase 03 exit criteria

P50 latency <10ms Rust / <80ms Python; Community tier accepting publishes; 5-person Shared Household E2E; per-dimension posture slider; Weekly+Monthly rituals; cross-SDK byte-identity; annual posture-revalidation.

## Phase 04 exit criteria

23+ channels active; 3 Rust skills in FV tier; 2 enterprise pilots; hidden-envelope primitive; multi-provider verification; WASM sandbox audited.

## Un-phased regulated-industry readiness

SOC2 Type 1 readiness (NOT certification); HIPAA-ready deployment template (Foundation not BAA party); GDPR DPIA tooling; Federated Trust Mesh spec.

## BET-falsification thresholds

Full catalog in doc 11 v1 §8; 10 BETs × per-metric disconfirmation thresholds.

## Kill criteria operationalized

- **[Heartbeat] + [Library] dual-signal:** <1000 WAU AND <500 FV fetches/week at 18mo.
- **≥3 BETs disconfirmed** → 6mo targeted-experiment countdown.
- **Foundation board declines runtime-pluggability.**
- **Categorically-better alternative:** all 5 §8 tests + 4 non-commercial properties + 3× within-niche adoption 24mo + 2 independent stewards confirm.
- **Legal categorical blocker** — unresolvable composite license / export / charter.

## Error taxonomy

This spec is a passive measurement-substrate declaration; it owns no runtime errors. Phase-gate verification produces gate-pass / gate-fail outcomes and ledger annotations rather than exceptions:

| Outcome                                          | Trigger                                                                                                                          | Operator action                                                                                                |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `PhaseGateFail` (operational marker, not raised) | Any one Phase exit criterion fails verification at gate                                                                          | Stop sprint; remediate failing criterion; re-run gate                                                          |
| `BETDisconfirmedAnnotation`                      | Per-BET threshold from §BET-falsification crossed in Heartbeat / Library / Public substrate                                      | Foundation board reviews; if ≥3 BETs disconfirmed, trigger 6mo targeted-experiment countdown per Kill criteria |
| `KillCriterionTriggered`                         | Any Kill-criterion crossed (low WAU+FV, ≥3 BETs disconfirmed, board declines pluggability, alternative confirmed, legal blocker) | Sunset announcement per Foundation governance; 18mo grace period to migrate users                              |

## Cross-references

- specs/foundation-health-heartbeat.md — Heartbeat flags + collection.
- specs/envelope-model.md — Authorship Score thresholds.
- specs/threat-model.md — test location per threat.
- specs/runtime-abstraction.md — per-phase gates.

## Test location

- `tests/acceptance/phase_00/test_phase_00_exit_criteria.py` — analysis-doc convergence + GH-issue manifest + algorithm-identifier schema landed (Tier 3).
- `tests/acceptance/phase_01/test_phase_01_e2e.py` — 1-user Boundary Conversation, 3 Grant Moments, Daily Digest delivery, Shamir reconstruct, 6-channel E2E.
- `tests/acceptance/phase_02/test_runtime_conformance_vectors.py` — N1-N6 + E1-E7 vectors green cross-runtime.
- `tests/acceptance/phase_03/test_5_person_shared_household.py` — 5-person Shared Household E2E (per specs/shared-household.md).
- `tests/acceptance/phase_04/test_enterprise_pilot.py` — 2 enterprise pilot integration (per specs/enterprise-deployment.md).
- `tests/acceptance/bet_falsification/test_bet_<N>_threshold.py` — per-BET disconfirmation threshold from doc 11 v1 §8.
- `tests/acceptance/kill_criteria/test_kill_criteria_operationalization.py` — wau+fv/3-BET/board-decline/alternative/legal blocker triggers.

## Open questions

1. BET-5 absent from any spec (per Round 1 LOW finding) — withdrawn / merged / drift; Foundation board confirmation needed.
2. Phase 04 "23+ channels" specific subset selection — telemetry-driven prioritization Phase 03 close.
3. Kill-criteria "categorically-better alternative" — definition of "categorically better" needs board-published rubric.
4. Annual posture-revalidation cadence — Phase 03 deliverable; ritual UX TBD.
5. Heartbeat opt-in rate target for §Measurement-substrate validity — what % opt-in is statistically sufficient.
