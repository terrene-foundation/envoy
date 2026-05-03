# Envoy Specs — Index

**Purpose:** Per `rules/specs-authority.md`, this is the lean lookup table for every domain spec. Phase commands read `_index.md` at start, identify relevant files, read only those files.

**Spec authority:** this directory is domain-organized (NOT process-organized — process lives in `workspaces/`). Every primitive Envoy consumes or produces has its spec here. Specs are detailed (not summary) per `rules/specs-authority.md` MUST Rule 3.

**Derived from:** `workspaces/phase-00-alignment/01-analysis/` (all 12 analysis docs FROZEN). Every spec traces back to its source analysis doc + relevant doc 09 threat mitigations + frozen-doc-00 v3 BETs.

**Provenance:** every spec carries a `## Provenance` section naming the source analysis doc, doc 09 threats mitigated, doc 00 BETs tested, and GH issues in the manifest that gate its implementation.

---

## Index

| File                                                             | Domain                                                                    | Source analysis                | One-liner                                                                                            |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------- | ------------------------------ | ---------------------------------------------------------------------------------------------------- |
| [envelope-model.md](envelope-model.md)                           | Envelope schema + compile + intersect + composition                       | doc 02 v3                      | Canonical envelope primitive — 5 dimensions, JCS canonical form, composition rules, Authorship Score |
| [trust-lineage.md](trust-lineage.md)                             | Genesis, Delegation, cascade revoke, key rotation                         | doc 03 v2                      | Trust Lineage spine — cryptographic authority chain                                                  |
| [ledger.md](ledger.md)                                           | Hash chain, two-phase signing, per-entry encryption, CRDT merge           | doc 04 v1                      | User-local audit record; append-only; tombstone + key destruction                                    |
| [runtime-abstraction.md](runtime-abstraction.md)                 | `kailash-runtime` interface + conformance vectors N1-N6 + E1-E7           | doc 05 v2                      | Abstract runtime contract; byte-identical spec paths, semantically-equivalent LLM paths              |
| [boundary-conversation.md](boundary-conversation.md)             | Onboarding state machine                                                  | doc 01 v2 §3                   | First-run ritual compiling EnvelopeConfig                                                            |
| [grant-moment.md](grant-moment.md)                               | Per-action consent state machine                                          | doc 01 v2 §4                   | Signed Delegation Record production                                                                  |
| [daily-digest.md](daily-digest.md)                               | Morning ritual                                                            | doc 01 v2 §5                   | Summary of actions / refusals / spend / pending grants                                               |
| [weekly-posture-review.md](weekly-posture-review.md)             | Sunday 90s ritual                                                         | doc 01 v2 §6                   | Posture + envelope recalibration; batch-to-envelope conversion                                       |
| [monthly-trust-report.md](monthly-trust-report.md)               | Month-end PDF/JSON                                                        | doc 01 v2 §7                   | Delegation graph, budget, posture trajectory                                                         |
| [shamir-recovery.md](shamir-recovery.md)                         | SLIP-0039 Shamir 3-of-5 ritual                                            | doc 01 v2 §8 + doc 03 v2 §2    | Trust Vault backup + recovery + rotation                                                             |
| [trust-vault.md](trust-vault.md)                                 | Encrypted local storage                                                   | doc 10 v1 §2                   | Envoy keys + envelope + posture + Shamir commitments                                                 |
| [connection-vault.md](connection-vault.md)                       | Third-party credential storage                                            | doc 10 v1 §3                   | OS keychain wrapper; per-principal isolated                                                          |
| [foundation-health-heartbeat.md](foundation-health-heartbeat.md) | STAR/Prio + DP + OHTTP                                                    | doc 00 v3 §5.0                 | Opt-in aggregate telemetry with k-anonymity                                                          |
| [sub-agent-delegation.md](sub-agent-delegation.md)               | SubsetProof schema + verifier                                             | doc 02 v3 §14.4 + doc 03 v2 §7 | Sub-agent envelope derivation proof                                                                  |
| [ledger-merge.md](ledger-merge.md)                               | CRDT merge protocol (T-101)                                               | doc 04 v1 §7                   | Lamport-clock ordering + conflict-flood rate-limit                                                   |
| [a2a-messaging.md](a2a-messaging.md)                             | Agent-to-agent messaging + Shared Household                               | doc 02 v3 + doc 07 v1          | Cross-principal dual-signed actions                                                                  |
| [authorship-score.md](authorship-score.md)                       | Semantic de-dup + minimum-impact + posture ratchet gate                   | doc 02 v3 §8 + §14.7 + §14.8   | BET-12 structural enforcement                                                                        |
| [budget-tracker.md](budget-tracker.md)                           | Financial-dimension velocity + session scope                              | doc 02 v3 §3.1 + doc 05 v2     | Integer microdollars, threshold callbacks                                                            |
| [remote-time-anchor.md](remote-time-anchor.md)                   | Quorum-TSA time anchor                                                    | doc 00 v3 §4.1 item 7b         | Optional Temporal-dimension anchor                                                                   |
| [foundation-ops.md](foundation-ops.md)                           | Foundation operational infra                                              | doc 06 + doc 08                | Registry + moderator queue + sync node + OHTTP relay                                                 |
| [channel-adapters.md](channel-adapters.md)                       | 8 Phase-01 surface + 17 Phase-04                                          | doc 07 v1                      | Adapter contract + per-channel spec + compliance                                                     |
| [threat-model.md](threat-model.md)                               | 50 threats + mitigation matrix                                            | doc 09 v3                      | Load-bearing for every defense primitive's test location                                             |
| [data-model.md](data-model.md)                                   | All persisted entities + schemas                                          | doc 10 v1                      | Trust Vault + Connection Vault + Ledger + shadow segment                                             |
| [distribution.md](distribution.md)                               | Per-OS install + N=3 mirrors + jurisdictional                             | doc 06 v1                      | Phase 01 pipx + Phase 02 static binary                                                               |
| [skill-ingest.md](skill-ingest.md)                               | SKILL.md parser + ENVELOPE.md companion + CO validator                    | doc 08 v1                      | Skill install-time governance                                                                        |
| [acceptance-metrics.md](acceptance-metrics.md)                   | Per-phase exit criteria operationalized                                   | doc 11 v1                      | Measurement substrate + BET falsification thresholds                                                 |
| [network-security.md](network-security.md)                       | TLS + cert pinning + SNI                                                  | doc 09 v3 T-080 + doc 06       | Network-layer defenses                                                                               |
| [ui-platform.md](ui-platform.md)                                 | Clipboard / screen / accessibility                                        | doc 09 v3 T-070 + doc 01       | Side-channel hygiene per platform                                                                    |
| [classification-policy.md](classification-policy.md)             | PACT classification clearance + `@classify` + `apply_read_classification` | doc 02 v3 §3.4                 | Data Access dimension enforcement                                                                    |
| [enterprise-deployment.md](enterprise-deployment.md)             | EnterpriseDeploymentRecord verifier + disablement flow                    | doc 02 v3 §14.3 + doc 03 v2 §9 | T-024 enterprise-mode cryptographic attestation                                                      |
| [posture-ladder.md](posture-ladder.md)                           | Canonical 5-tier autonomy enum + ratchet semantics                        | doc 00 v3 §4.2 + doc 02 v3 §8  | PSEUDO / TOOL / SUPERVISED / DELEGATING / AUTONOMOUS owner                                           |
| [shared-household.md](shared-household.md)                       | Multi-principal invite / exit / abuse-flag / co-presence                  | doc 00 v3 §4.2 item 14         | Phase 03 5-person E2E gate; T-002 household-adversarial defense                                      |
| [session-state.md](session-state.md)                             | SessionObservedState + session-boundary + ReasoningCommit                 | doc 02 v3 §14.9 + §16 + §19    | Ephemeral session cache owner; T-013 defense                                                         |
| [tool-output-sanitization.md](tool-output-sanitization.md)       | `tool_output_sanitize` runtime boundary                                   | doc 02 v3 §3.4.3               | T-010/T-011 prompt-injection structural defense at tool-return                                       |
| [cross-domain-flows.md](cross-domain-flows.md)                   | Cross-domain rule engine (work↔personal / classification↔public)          | doc 02 v3 §3.4.4               | `envoy-registry:cross-domain-flows:v1` consumer + specs/tool-output-sanitization.md dependency       |
| [envelope-library.md](envelope-library.md)                       | Foundation + Community publisher surface; Sybil + reputation              | doc 09 v3 §3 T-020-T-022       | Publisher-side primitives for T-020/T-021/T-022/T-024/T-051/T-092                                    |
| [model-adapter.md](model-adapter.md)                             | Per-LLM-provider abstraction; response filter + provider-risk             | doc 05 v2 + doc 09 v3 §3 T-014 | T-014/T-016/T-017/T-030/T-094 mitigation primitives                                                  |
| [independent-verifier.md](independent-verifier.md)               | Separately-codebased Ledger verifier CLI                                  | phase-01 shard 7               | EC-4 mutation battery + EC-9 source-isolation gate; Python P01 / Rust P02                            |
| [mvp-build-sequence.md](mvp-build-sequence.md)                   | Phase 01 build order + integration milestones + Phase 02 hooks            | phase-01 shard 20 + 22         | Authoritative reference for Phase 01 implementation planning across sessions                         |

---

## Spec file conventions

Every spec file MUST include (in order):

- **`## Purpose`** — one-paragraph scope.
- **`## Provenance`** — source analysis doc + threats mitigated + BETs tested + GH issues.
- **`## Schema`** — canonical JSON or dataclass, if the spec owns a schema.
- **`## Algorithm`** — concrete pseudocode per doc 02 §14 pattern, if the spec owns an algorithm.
- **`## Error taxonomy`** — structured errors with trigger + user action (table form preferred).
- **`## Cross-references`** — to other specs + analysis docs.
- **`## Test location`** — the `tests/<tier>/...` path that exercises this spec + every threat it claims to mitigate; see `rules/testing.md` §Audit Mode Rules.
- **`## Open questions`** — for downstream refinement.

Every reference to a shipped Foundation primitive (kailash-py / kailash-rs / mint) cites GH issue # where applicable (see `workspaces/phase-00-alignment/issues/manifest.md`).

Every Ledger entry type listed in specs/ledger.md §Entry types MUST have a named producer spec owning its schema (per `rules/orphan-detection.md`).

---

## Spec freeze discipline

Per `rules/specs-authority.md` MUST Rule 5 + 5b:

- Spec updated at first instance of domain-truth change.
- Sibling specs re-derived when edits affect shared vocabulary / fields / dependencies.
- Specs carry `FROZEN v{N}` status after redteam convergence.

Current spec freeze state: **37 specs FROZEN v1** (30 original + 5 minted 2026-04-21 per R3-HIGH orphan-primitive findings: posture-ladder, shared-household, session-state, tool-output-sanitization, cross-domain-flows; + 2 minted 2026-04-29 per Round 2 R3-HIGH anchor-doc-referenced-but-missing findings: envelope-library, model-adapter).

**Convergence achieved 2026-04-29:** 0 CRIT + 0 HIGH across 2 consecutive full-sibling redteam rounds (Round 5 + Round 6) per specs-authority.md §5b. Round-by-round trajectory:

| Round | CRIT | HIGH | MED | LOW | Verdict       |
| ----- | ---- | ---- | --- | --- | ------------- |
| R1    | 7    | 23   | 27  | 9   | NOT CONVERGED |
| R2    | 4    | 11   | 14  | 6   | NOT CONVERGED |
| R3    | 2    | 9    | 13  | 6   | NOT CONVERGED |
| R4    | 0    | 1    | 12  | 4   | NOT CONVERGED |
| R5    | 0    | 0    | 13  | 4   | first 0-HIGH  |
| R6    | 0    | 0    | 3   | 4   | **CONVERGED** |

Findings docs: `workspaces/phase-00-alignment/04-validate/round-{1..6}-specs-comprehensive.md`. Residual 3 MED + 4 LOW are recorded in round-6 doc as Phase 01+ refinement candidates; none block Phase 00 exit.
