# Phase 01 MVP — Analysis Index

**Document role:** Lean lookup table for every Phase 01 `/analyze` artifact under `01-analysis/`. Per `rules/specs-authority.md` MUST Rule 1, this manifest is one-line descriptions only — the actual analysis lives in the linked files. Phase commands (`/todos`, `/implement`, `/redteam`, `/codify`) read this index first, then read only the rows relevant to the current work.

**Date:** 2026-05-03 (shard 25 of /analyze; closure).
**Status:** Closed for /analyze; load-bearing for /todos.

---

## How to use this index

- `/todos` reads rows tagged "Synthesis" + "Plan" + "Spec gap" first; then drills into specific primitives whose ECs the planner is sequencing.
- `/implement` reads ONE primitive row at a time (the row matching the current todo) plus shards 03 + 18 + 19 for the kailash-py / runtime-abstraction / packaging surface.
- `/redteam` re-reads ALL rows under "Primitive deep-dive" in audit mode (per `rules/testing.md` § Audit Mode Rules — re-derive each round).
- `/codify` extracts patterns from rows tagged "Synthesis" + "Spec gap" + the journal entries.

| File                                         | Domain              | Description                                                                                                                                                                                                                                    |
| -------------------------------------------- | ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `00-inheritance-from-phase-00.md`            | Inheritance         | Frozen-contract surface map; what Phase 01 inherits (37 specs / 9 ADRs / 12 BETs) and what it must produce on top                                                                                                                              |
| `01-shard-plan.md`                           | Plan                | The 25-shard /analyze sequence with wave-by-wave completion summaries (waves A–G) and the topological dependency graph                                                                                                                         |
| `02-mvp-objectives.md`                       | Objectives          | 9 effective Phase 01 exit criteria (EC-1..EC-9) mapped to the primitive that owns each, the BET each falsifies, the structural deliverable, and the pre-declared acceptance gate                                                               |
| `02b-mvp-usps.md`                            | Objectives          | Phase 01-specific USPs distilled from CHARTER §47–59; 4 demonstrable in MVP (U2 Boundary Conversation, U3 Envoy Ledger, U4 Foundation stewardship, U6 no-orphan guarantee); 3 partial-or-Phase-02                                              |
| `03-kailash-py-mvp-readiness.md`             | Upstream            | Per-primitive `kailash-py` provider map; post-baseline closures (12 of 13 ISS closed Apr 24–26); only #596 OPEN; per-primitive verification protocol                                                                                           |
| `04-envelope-compiler-implementation.md`     | Primitive deep-dive | Envelope compiler (shard 4); A-grade upstream `kailash.trust.pact.envelopes`; thin Envoy `EnvelopeCompiler` materializer; gates EC-1                                                                                                           |
| `05-trust-store-implementation.md`           | Primitive deep-dive | Trust store + lineage (shard 5); 4 trust modules A-grade; `TrustStoreAdapter` wraps `SqliteTrustStore` with `principal_id` keying for Phase 03 multi-principal                                                                                 |
| `06-envoy-ledger-implementation.md`          | Primitive deep-dive | Envoy Ledger + ledger-merge (shard 6); composes upstream pieces with deterministic `CanonicalJsonEncoder`; sunset clause for #596; gates EC-4                                                                                                  |
| `07-independent-verifier-design.md`          | Primitive deep-dive | Independent ledger verifier (shard 7); separate `terrene-foundation/envoy-ledger-verifier` repo; Python first as Phase 01 EC-9 minimum + Rust sibling stretch                                                                                  |
| `08-boundary-conversation-implementation.md` | Primitive deep-dive | Boundary Conversation (shard 8); Kaizen L3 Plan-DAG over S0→S10 with structured-output `Signature`; persistent resume; gates EC-1                                                                                                              |
| `09-authorship-score-implementation.md`      | Primitive deep-dive | Authorship Score + Posture Gate (shard 9); stateless pure function over Ledger slice with JCS-sorted byte-deterministic recompute; cross-shard JCS-canonical-order invariant for shard 4                                                       |
| `10-grant-moment-implementation.md`          | Primitive deep-dive | Grant Moment (shard 10); M0→M4 state machine with M3 branching by `ResolutionShape`; `OutOfEnvelopeDetector` interceptor; signed-consent 3-artifact wire format; gates EC-2 + EC-8                                                             |
| `11-daily-digest-implementation.md`          | Primitive deep-dive | Daily Digest (shard 11); `DailyDigestService` facade composing `apscheduler.AsyncIOScheduler` + `LedgerAggregator` + `DigestRenderer` + `PerChannelFanout`; gates EC-3 + BET-8                                                                 |
| `12-budget-tracker-implementation.md`        | Primitive deep-dive | Budget tracker (shard 12); `EnvoyBudgetOrchestrator` over 5 trackers per ceiling window with `tenant_id` keying; first HIGH spec ambiguity (timezone basis) escalated to shard 22                                                              |
| `13-model-adapter-implementation.md`         | Primitive deep-dive | Model adapter (shard 13); ~330 LOC Envoy glue (router + risk annotator + token-budget filter) over upstream LlmDeployment; 1 HIGH-candidate held                                                                                               |
| `14-connection-vault-implementation.md`      | Primitive deep-dive | Connection Vault Phase 01 minimal (shard 14); MIT-licensed `keyring` OS-keychain wrapper; principal-distinct from Trust Vault; full third-party OAuth deferred to Phase 02                                                                     |
| `15-shamir-recovery-implementation.md`       | Primitive deep-dive | Shamir 3-of-5 recovery (shard 15); `kailash 2.11.0` ships `kailash.trust.vault.shamir` wrapper around `shamir-mnemonic` (PyPI); 5 Envoy modules; gates EC-5                                                                                    |
| `16-channel-adapters-implementation.md`      | Primitive deep-dive | Channel adapters (shard 16); 6 messaging + CLI + Web; ~150 LOC each over shared `WebhookTransport` + per-vendor `WebhookSigner`; cross-channel coherence delegated to Trust store + Ledger; gates EC-7 + EC-8                                  |
| `17-foundation-health-heartbeat-decision.md` | DECISION shard      | Foundation Health Heartbeat (shard 17); RECOMMENDATION: DE-SCOPE to Phase 02 entry; ~100 LOC stubs in Phase 01; k≥100 anonymity floor unclearable at Phase 01 cohort                                                                           |
| `18-runtime-abstraction-stub.md`             | Primitive deep-dive | Runtime abstraction stub (shard 18); 24 byte-identical / 5 semantically-equivalent partition; feature-flagged `kailash_rs_bindings` adapter slot; import-discipline IS the Phase 02 mechanicality guarantee                                    |
| `19-pipx-distribution-architecture.md`       | Synthesis           | pipx distribution (shard 19); confirms `kailash-ml` OUT of dep tree; `kailash[shamir,nexus,kaizen]>=2.13.4` + `keyring` + 3 channel SDKs; LGPL-3.0+ via dynamic-link; cross-OS caveats catalogued                                              |
| `22-spec-gap-analysis.md`                    | Spec gap            | Aggregation of every primitive shard's §7 frozen-spec ambiguity; 1 unique HIGH (timezone, Option A vs B framed); 11 MED (3 closed by additive `specs/independent-verifier.md`); 39 LOW; 2 additive new specs drafted; ZERO existing-spec edits |

---

## Cross-references

- Plans: `02-plans/_index.md`
- User flows: `03-user-flows/_index.md`
- Redteam rounds: `04-validate/round-{1,2,3,4}-implementation-comprehensive.md`
- Journal: `journal/000{1,2,3,4}-*.md`
- Brief: `briefs/00-phase-01-mvp-scope.md`
- Frozen specs: `specs/_index.md` (38 files, frozen-v1; 2 additive Phase 01 drafts at `specs/independent-verifier.md` + `specs/mvp-build-sequence.md`)
