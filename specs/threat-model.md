# threat-model

## Purpose

50 enumerated threats + mitigation-to-primitive matrix + residual risk register + per-phase security-review gates.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/09-threat-model.md v3 FROZEN`.
- **Threats mitigated:** ALL 50 threats catalogued here.
- **BETs tested:** Tests every doc 00 BET's defense primitives.

## Threat categories

STRIDE (S/T/R/I/D/E) + Envoy-specific (PI/GOV/UX/SC/CTX).

## Threats (50 total)

See doc 09 v3 §3 for full detail. Summary:

- **T-001–T-007** carry-forwards from doc 00 §13 (clock-skew, household-adversarial, ledger retention, streaming LLM pre-sign, semantic envelope, Shamir social-graph, credential storage).
- **T-008** Grant Moment replay.
- **T-010–T-017** prompt injection + context-window + feedback-loop + goal drift + training-data extraction.
- **T-018–T-019** Grant Moment spoofing + habituation.
- **T-020–T-024** skill/envelope supply-chain + authorship gaming + enterprise delegation-upward.
- **T-030** compromised model provider.
- **T-040–T-042** device threats.
- **T-050a/T-050b** Foundation binary mirror vs signing-key.
- **T-051–T-054** Foundation infra + Heartbeat covert channel.
- **T-060–T-061** runtime binary poisoning.
- **T-070–T-071** side channels.
- **T-080** network MITM.
- **T-090–T-094** DoS variants.
- **T-100–T-107** Ledger + trust-lineage crypto + sub-agent forgery + A2A collusion + recursive spawn DoS.

## Mitigation-to-primitive matrix

50 threats × {primary mitigation, spec location, test location, phase}. Full matrix in doc 09 v3 §4.

## Residual risks

Explicitly enumerated per doc 09 v3 §6 (13 residuals). Includes: clock-forward spoofing during write window, kernel-level keylog, sophisticated duress-latency detection, jurisdictional compulsion, all-3-mirrors compromised, 2-of-N Foundation colluding, relay+aggregator colluding, sync metadata patterns, classifier arms race, Phase-A-to-B window, platform accessibility misuse, device-wide exhaustion outside Envoy, PQ migration timing.

## Out of scope

Nation-state full-spectrum, device-level kernel/hypervisor/firmware compromise, physical TEMPEST, hardware keylogger, regulated-industry compliance (deployment concern), adversarial unrelated-user multi-tenant, legal-process jurisdictional edge cases.

## Phase gates

- **Phase 00:** crypto library audit, Shamir lib selection, OHTTP lib selection, abuse-survivor advisory engagement, legal counsel 7 items.
- **Phase 01:** threat-model test suite green, binding-gap security fixes closed (kailash-rs#520 SQLi), algorithm-identifier live, Ledger content_trust_level + signature-scope review, Grant Moment visual-secret UX review, trust-lineage cycle-detect corpus, envelope-version binding conformance, T-093 budget-velocity test, algorithm-identifier Phase 01 exit gate.
- **Phase 02:** full binding security audit, OHTTP/STAR review, FV tier signing ceremony, CRDT-merge external review, reproducible-build stream.
- **Phase 03:** Shared Household abuse-survivor review, sub-agent derivation proof external review, enterprise-mode cryptographic attestation review, Envelope Library Sybil defense review.
- **Phase 04:** WASM sandbox audit, multi-provider verification review, hidden-envelope deniability review.
- **Ongoing:** regression tests, CVE scans, reproducible-build verification, classifier-ensemble quarterly update review.

## Error taxonomy

This spec is a passive threat-matrix declaration; it does NOT own any runtime primitive and therefore does NOT raise any errors directly. Threats themselves are listed in `workspaces/phase-00-alignment/01-analysis/09-threat-model.md v3 §3` (50 threats total); each threat's mitigation primitive, error taxonomy entry, and regression test live in the OWNING consumer spec per `## Cross-references`. The mitigation-to-primitive matrix in §Mitigation-to-primitive matrix is the lookup index from threat ID → owning spec.

For example: T-093 budget-exhaustion fraud's error taxonomy lives in specs/budget-tracker.md (`BudgetExhaustedError`, `VelocityRaiseInlineBlockError`, `AnomalyDetectedError`, `HighVelocityPatternError`); T-105 sub-agent forgery's lives in specs/sub-agent-delegation.md; T-100 rollback's lives in specs/ledger.md.

## Cross-references

Every spec file in this directory. threat-model.md is the integration point — each primitive elsewhere references back here for the threats it mitigates.

## Test location

Each threat's regression test lives in the OWNING spec's `## Test location` section (cross-spec assertion). The threat-matrix as a whole is exercised by:

- `tests/coverage/test_every_threat_has_test.py` — coverage gate: enumerate all 50 threats from doc 09 v3 §3; assert every threat T-NNN has at least one matching `tests/regression/test_t<NNN>_*.py` regression test in the test tree. Failing assertion lists threats missing regression coverage.
- `tests/coverage/test_every_threat_has_owning_spec.py` — every threat T-NNN appears in at least one spec's `## Provenance` § `Threats mitigated:` line.
- `tests/coverage/test_residual_risks_documented.py` — every residual risk in §Residual risks has a corresponding `workspaces/phase-00-alignment/01-analysis/09-threat-model.md v3 §6` reference.
- `tests/coverage/test_phase_gates_have_test_evidence.py` — every Phase 00–04 gate item in §Phase gates has corresponding test evidence (regression test, conformance corpus, or audit artifact).
- Each individual T-NNN regression test lives in the consumer spec's test tree per the matrix; this spec's test location is the COVERAGE assertion that all 50 are present.

## Open questions

1. T-094 mapping — RESOLVED in Round 2 R4-HIGH closure: T-094 is documented as a variant of T-015 (shared mitigations) and is now claimed by `specs/envelope-model.md` `## Provenance` `Threats mitigated:` and additionally by `specs/model-adapter.md` (model-response DoS path). Both share the underlying T-015 system-prompt-pinning + prompt-size-budget structural defense.
2. T-014 / T-016 / T-017 mapping — RESOLVED in Round 2 R4-HIGH closure via `specs/model-adapter.md`. T-014 (multi-turn accumulated injection) → `model-adapter.md` §Response filter §multi-turn accumulation check. T-016 (goal drift across provider switches) → `model-adapter.md` §Response filter §goal-drift classifier. T-017 (training-data extraction) → `model-adapter.md` §Response filter §leak-canary scan + `envoy-registry:training-leak-canaries:v1` (registered next freeze). All three carry regression test paths in `specs/model-adapter.md` `## Test location`.
3. Residual-risk tracking cadence — the 13 residual risks per §Residual risks are documented but not under continuous re-evaluation; what process re-visits each residual at Phase boundary (per-phase risk re-rating?) vs leaves them as static documentation?
4. Out-of-scope drift — §Out of scope items (nation-state, kernel/firmware, TEMPEST, hardware keylogger) are project-scope decisions, not technical limitations. What process re-evaluates the out-of-scope boundary if user demand or threat landscape shifts (e.g. regulated-industry compliance moving in-scope for Phase 04+)?
5. Phase-gate ownership — every gate item in §Phase gates has an implicit owner; is there a gate-tracking artifact (issue tracker label? Workspace todo file?) that maps each gate item to a responsible reviewer + due date for its phase exit?
