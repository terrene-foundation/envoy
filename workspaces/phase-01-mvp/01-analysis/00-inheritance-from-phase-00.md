# 00 — Inheritance from Phase 00

**Document role:** Map exactly what Phase 01 inherits from Phase 00 and what Phase 01 must produce on top. This is the bridge document — every later Phase 01 analysis doc cites this for "where does X come from."

**Date:** 2026-05-03 (shard 1 of /analyze).
**Status:** DRAFT — load-bearing for the rest of /analyze.

---

## 1. Why this document exists

Phase 00 produced 13 analysis docs, 9 ADRs, 37 frozen specs, 6 redteam rounds, 39 upstream issues. Re-deriving any of that in Phase 01 is wasted work _and_ drift risk (a re-derivation might disagree with the frozen spec, silently). The structural defense: Phase 01 analysis cites Phase 00 artifacts by path + section, never paraphrases them.

This document lists every inheritable artifact, where it lives, and what Phase 01 may NOT change.

## 2. Frozen contract surface (DO NOT EDIT in Phase 01)

### 2.1 Frozen specs (37 files at `specs/`)

All under `MUST Rule 5b` lock — any spec edit re-triggers full-sibling redteam (37-spec sweep, 6-round historical convergence cost). Phase 01 may ADD new spec files (e.g. `specs/mvp-build-sequence.md`); editing existing files is a HIGH-cost operation that must be justified by a HIGH-severity gap surfaced in red team.

| Spec family                      | Files                                                                                                                                                 | Phase 01 dependency                                                                                      |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| **Envelope**                     | `envelope-model.md`, `envelope-library.md`, `cross-domain-flows.md`, `sub-agent-delegation.md`, `tool-output-sanitization.md`                         | Envelope compiler primitive                                                                              |
| **Trust + lineage**              | `trust-lineage.md`, `trust-vault.md`, `connection-vault.md`, `posture-ladder.md`, `authorship-score.md`, `shamir-recovery.md`                         | Trust store, Authorship Score gate, Shamir backup                                                        |
| **Ledger**                       | `ledger.md`, `ledger-merge.md`, `remote-time-anchor.md`                                                                                               | Envoy Ledger primitive + independent verifier                                                            |
| **Conversation + UX**            | `boundary-conversation.md`, `grant-moment.md`, `daily-digest.md`, `weekly-posture-review.md` (P03), `monthly-trust-report.md` (P03), `ui-platform.md` | Boundary Conversation, Grant Moment, Daily Digest                                                        |
| **Channels + adapters**          | `channel-adapters.md`, `model-adapter.md`, `a2a-messaging.md`                                                                                         | 6-channel + CLI + Web adapter set; model adapter                                                         |
| **Runtime + distribution**       | `runtime-abstraction.md`, `distribution.md`, `session-state.md`                                                                                       | Phase 01 wires `kailash-py` only; abstract interface defined                                             |
| **Budget + classification**      | `budget-tracker.md`, `classification-policy.md`, `data-model.md`                                                                                      | Budget tracker primitive                                                                                 |
| **Skills**                       | `skill-ingest.md`                                                                                                                                     | Phase 02 (SKILL.md translator) — Phase 01 only validates spec hooks exist                                |
| **Multi-principal + enterprise** | `shared-household.md` (P03), `enterprise-deployment.md`                                                                                               | Phase 01 builds the single-principal happy path; multi-principal data-model affordances must NOT regress |
| **Foundation infrastructure**    | `foundation-ops.md`, `foundation-health-heartbeat.md`, `network-security.md`, `threat-model.md`                                                       | Foundation Health Heartbeat = Phase 01 component (de-scope candidate #2)                                 |

### 2.2 Frozen ADRs (`DECISIONS.md` ADR-0001 through ADR-0009)

| ADR                                            | Phase 01 binding                                                                                                                                |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **ADR-0001** Runtime architecture              | Phase 01 wires `kailash-py` only; `kailash-runtime` abstract interface MUST exist (stub on Rust side); first-run picker is Phase 02 deliverable |
| **ADR-0002** Naming + legal mark               | Phase 01 ships under codename `envoy` / `envoy-agent`; trademark close gates Phase 02 distribution surfaces only                                |
| **ADR-0003** Shamir recovery via SLIP-0039     | Phase 01 launch requirement; `slip39` Python package                                                                                            |
| **ADR-0004** Envelope Library tiers            | Phase 01 does NOT ship the registry; envelope-import-from-file path only                                                                        |
| **ADR-0005** SKILL.md compatibility            | Phase 02 translator; Phase 01 wires the spec hooks but does not implement the translator                                                        |
| **ADR-0006** Model choice (BYOM)               | Phase 01 ships the Kaizen `Delegate` provider abstraction with Ollama / Claude / GPT / DeepSeek / custom OpenAI-compatible adapters             |
| **ADR-0007** Trust Vault sync                  | Phase 01 ships local-only; sync deferred to Phase 03                                                                                            |
| **ADR-0008** Mobile onboarding                 | Phase 02 deliverable; Phase 01 ships CLI + Web only                                                                                             |
| **ADR-0009** Licensing + Foundation compliance | Phase 01 ships under existing Apache 2.0 + CC BY 4.0 framing; composite LICENSE + counsel sign-off + board endorsement gate Phase 02            |

### 2.3 Frozen vocabulary (`terrene-naming.md` + thesis-and-scope §2)

- **5 constraint dimensions** (canonical, no synonyms, no reordering): Financial, Operational, Temporal, Data Access, Communication
- **5 trust postures** (canonical 5-step ladder): PSEUDO → TOOL → SUPERVISED → DELEGATING → AUTONOMOUS
- **4 spec families** (CC BY 4.0 Foundation-owned): CARE (philosophy), EATP (protocol), CO (methodology), PACT (governance)
- **Foundation entity name**: Terrene Foundation (Singapore CLG)

### 2.4 Frozen BETs (thesis-and-scope §5)

12 falsifiable Bet/Test pairs. Phase 01 must surface enough product to test BETs that are testable at MVP scale:

| BET                                              | Falsifiability at Phase 01?                                      |
| ------------------------------------------------ | ---------------------------------------------------------------- |
| BET-1 (Boundary Conversation completion rate)    | YES — Phase 01 exit criterion #1 directly tests                  |
| BET-2 (Envelope-check P50 latency budgets)       | PARTIAL — Phase 01 measures pure-Python; Phase 02 cross-runtime  |
| BET-3 (Authorship-as-agency adoption)            | PARTIAL — Phase 01 first-week cohort signal                      |
| BET-4 (Cross-channel coherence)                  | YES — 6-channel + CLI + Web exit criterion                       |
| BET-5 (Ledger as daily artifact)                 | YES — Phase 01 exit criterion #4 + independent verifier          |
| BET-6 (Cross-runtime contract partition)         | NO — needs both runtimes (Phase 02)                              |
| BET-7 (Posture ratchet observed)                 | PARTIAL — needs Phase 03 Weekly Posture Review for full signal   |
| BET-8 (Foundation Health uptake)                 | YES if Heartbeat ships in Phase 01; NO if de-scoped              |
| BET-9a (Shamir recovery learnable)               | YES — Phase 01 exit criterion #5                                 |
| BET-9b (Vault portability)                       | YES — Phase 01 cross-OS test                                     |
| BET-10 (Default-deny experienced as agency)      | PARTIAL — Phase 01 first-week signal                             |
| BET-11 (Channel-as-UI thesis)                    | YES — Phase 01 6-channel set                                     |
| BET-12 (Governance-primary-surface palatability) | PARTIAL — needs 18mo TAM data; Phase 01 captures cohort baseline |

8 of 12 BETs are at-least-partially testable in Phase 01. This is the structural justification for the 8–12-session scope.

## 3. Inheritable analysis docs (`workspaces/phase-00-alignment/01-analysis/*`)

These remain authoritative reference; Phase 01 cites them, never paraphrases:

| File                                  | Phase 01 use                                                                          |
| ------------------------------------- | ------------------------------------------------------------------------------------- |
| `00-thesis-and-scope.md` (FROZEN v3)  | Single source for thesis, scope, BETs, phase scope, de-scope candidates               |
| `01-kailash-rs-deep-audit.md`         | Background; not load-bearing for Phase 01 (Rust binding deferred)                     |
| `01-ux-rituals.md`                    | Source for ritual UX design                                                           |
| `02-envelope-model.md`                | Source for envelope-compiler implementation; cite when wiring `intersect_envelopes()` |
| `02-kailash-py-survey.md`             | **CRITICAL for Phase 01** — what `kailash-py` provides today; gaps = Envoy-new-code   |
| `03-primitive-reconciliation.md`      | Maps spec primitives to source crate / package providers                              |
| `03-trust-lineage.md`                 | Source for Trust store + lineage primitive wiring                                     |
| `04-ledger.md`                        | Source for ledger + independent verifier                                              |
| `05-runtime-abstraction.md`           | Phase 01 abstract-interface contract                                                  |
| `06-distribution.md`                  | Phase 01 `pipx install envoy-agent` packaging                                         |
| `07-channels-and-adapters.md`         | 6-channel + CLI + Web wiring                                                          |
| `08-skills-and-envelope-companion.md` | Phase 01 spec-hook validation                                                         |
| `09-threat-model.md`                  | Phase 01 security gate                                                                |
| `10-data-model.md`                    | Phase 01 SQLite schema; multi-principal-ready                                         |
| `11-acceptance-metrics.md`            | Phase 01 measurement targets (P50 <80ms Python pre-Rust)                              |

## 4. Inheritable plans (`workspaces/phase-00-alignment/02-plans/*`)

| Plan                                                  | Phase 01 inheritance                          |
| ----------------------------------------------------- | --------------------------------------------- |
| `phase-00-plan.md`                                    | Phase 00 closeout reference                   |
| `claim-verification/01-sweep.md`                      | Pattern for Phase 01 doc-claim discipline     |
| `legal/01-LICENSE-draft.md`                           | Composite LICENSE draft (Phase 02 gate)       |
| `legal/02-SPDX-draft.md`                              | SPDX expression (Phase 02 gate)               |
| `legal/03-license-compatibility-statement.md`         | Apache+CC+MIT compat (Phase 02 gate)          |
| `conformance/01-runtime-swap-contract.md`             | Cross-runtime contract (Phase 02 gate)        |
| `user-disclosure/01-installer-readme-runtime-copy.md` | First-run picker copy (Phase 02 gate)         |
| `board-package/01-envoy-concept-one-pager.md`         | Foundation board ask (Phase 00 external gate) |

## 5. What Phase 01 /analyze produces NEW

Per the brief at `workspaces/phase-01-mvp/briefs/00-phase-01-mvp-scope.md` § "What Phase 01 /analyze must produce":

### 5.1 New analysis docs (`01-analysis/`)

| File                                               | Content                                                                                                                              | Source it inherits from                                     |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------- |
| `00-inheritance-from-phase-00.md`                  | This file                                                                                                                            | All of Phase 00                                             |
| `01-shard-plan.md`                                 | The /analyze sharding map for the rest of Phase 01                                                                                   | Brief + this inheritance map                                |
| `02-mvp-objectives.md`                             | Phase 01 exit criteria mapped to deliverables + USP refinement                                                                       | ROADMAP §35–65 + thesis §3.1                                |
| `03-boundary-conversation-implementation.md`       | How to actually wire Kaizen `BaseAgent` + scripted `Signature` to deliver Boundary Conversation per `specs/boundary-conversation.md` | Spec + `kailash-py` survey                                  |
| `04-grant-moment-implementation.md`                | CLI prompt + Web modal implementation; signed-consent record format                                                                  | `specs/grant-moment.md` + `specs/ledger.md`                 |
| `05-daily-digest-implementation.md`                | Kaizen scheduled-agent wiring + per-channel rendering                                                                                | `specs/daily-digest.md` + channel adapters                  |
| `06-envoy-ledger-implementation.md`                | EATP `TieredAuditDispatcher` + SQLite + export CLI + hash-chain semantics                                                            | `specs/ledger.md` + `specs/ledger-merge.md`                 |
| `07-envelope-compiler-implementation.md`           | PACT `RoleEnvelope` + `TaskEnvelope` + `intersect_envelopes()` wiring                                                                | `specs/envelope-model.md` + `specs/sub-agent-delegation.md` |
| `08-trust-store-implementation.md`                 | EATP `SQLiteTrustStore` or `FilesystemStore` selection + lineage wiring                                                              | `specs/trust-vault.md` + `specs/trust-lineage.md`           |
| `09-budget-tracker-implementation.md`              | EATP `BudgetTracker` + `SQLiteBudgetStore` + threshold-callback API                                                                  | `specs/budget-tracker.md`                                   |
| `10-model-adapter-implementation.md`               | Kaizen `Delegate` → 5 provider adapters                                                                                              | `specs/model-adapter.md` + ADR-0006                         |
| `11-shamir-recovery-implementation.md`             | `slip39` Python package wiring + paper-shard format                                                                                  | `specs/shamir-recovery.md` + ADR-0003                       |
| `12-authorship-score-implementation.md`            | Score computation + posture-gate enforcement                                                                                         | `specs/authorship-score.md` + `specs/posture-ladder.md`     |
| `13-foundation-health-heartbeat-implementation.md` | STAR/Prio + OHTTP + signed-consent telemetry (or de-scope decision)                                                                  | `specs/foundation-health-heartbeat.md`                      |
| `14-channel-adapters-implementation.md`            | 6 messaging + CLI + Web wiring                                                                                                       | `specs/channel-adapters.md`                                 |
| `15-independent-ledger-verifier-design.md`         | Separately-codebased verifier; language + repo decision                                                                              | `specs/ledger.md`                                           |
| `16-pipx-distribution-architecture.md`             | `pipx install envoy-agent` packaging                                                                                                 | `specs/distribution.md`                                     |
| `17-runtime-abstraction-stub.md`                   | Phase 01 abstract `kailash-runtime` interface contract                                                                               | `specs/runtime-abstraction.md`                              |

17 analysis docs. Each is one shard.

### 5.2 New plans (`02-plans/`)

| File                       | Content                                                                       |
| -------------------------- | ----------------------------------------------------------------------------- |
| `01-build-sequence.md`     | Order of primitive implementation; integration-test sequence                  |
| `02-test-strategy.md`      | 3-tier testing per `rules/testing.md`; real-infrastructure gates for Tier 2/3 |
| `03-package-skeleton.md`   | Repo layout for `envoy-agent` Python package                                  |
| `04-redteam-cycle-plan.md` | Phase 01 redteam round structure; convergence gate                            |

### 5.3 New user flows (`03-user-flows/`)

| File                               | Flow                                                     |
| ---------------------------------- | -------------------------------------------------------- |
| `01-install-flow.md`               | `pipx install envoy-agent` → `envoy init` → first launch |
| `02-boundary-conversation-flow.md` | First-time onboarding (target 15 min)                    |
| `03-grant-moment-flow.md`          | Out-of-envelope action → Grant Moment → resolution       |
| `04-daily-digest-flow.md`          | Morning ritual                                           |
| `05-channel-onboarding-flow.md`    | Adding a 7th channel mid-week                            |
| `06-shamir-backup-flow.md`         | 3-of-5 paper-card ritual                                 |
| `07-ledger-export-flow.md`         | Export + independent verification                        |
| `08-posture-ratchet-flow.md`       | Authorship Score → DELEGATING posture gate               |

### 5.4 Spec additions (NOT edits)

Identified via gap analysis in shard 12:

- `specs/mvp-build-sequence.md` (probable) — captures Phase 01 build order as authoritative reference
- `specs/independent-verifier.md` (probable) — captures the separately-codebased verifier contract since the verifier itself is Phase-01-specific

NEW spec files do NOT trigger MUST Rule 5b re-derivation (the rule fires on EDITS to existing siblings). New files are additive.

## 6. Frozen interface contracts Phase 01 must respect

These are the cross-spec invariants that Phase 01 implementation must hold; surfaced from the 6-round Phase 00 redteam:

1. **Tenant isolation dimension on every key** (`rules/tenant-isolation.md` Rule 1) — every cache key, audit row, metric label includes the multi-principal dimension even though Phase 01 ships single-principal (Phase 03 Shared Household relies on this hook existing in Phase 01)
2. **Classification fields filtered at every emission boundary** (`rules/event-payload-classification.md`) — event payloads route through `format_record_id_for_event` equivalent
3. **Envelope-check latency partitions** (`specs/envelope-model.md` §80) — structural ≤5ms, semantic-cached ≤50ms, semantic-uncached ≤500ms
4. **Cross-runtime contract partition** (`specs/runtime-abstraction.md` §Contract partition (BET-6)) — even though Phase 01 ships only `kailash-py`, the abstract interface MUST distinguish byte-identical-spec methods from semantically-equivalent-LLM methods so Phase 02 wiring is mechanical
5. **Hash-chain integrity** (`specs/ledger.md`) — independent verifier requires the hash-chain shape to be stable at Phase 01 release; verifier is not "trust the producer"
6. **Authorship Score gate enforcement** (`specs/authorship-score.md` + `specs/posture-ladder.md`) — DELEGATING / AUTONOMOUS posture transitions blocked until score ≥ N; this is BET-12's structural enforcement
7. **No-orphan rule** (`rules/orphan-detection.md` + `rules/facade-manager-detection.md`) — every primitive Envoy ships in Phase 01 must have at least one production call site AND a Tier 2 integration test in the same PR

## 7. Inheritance audit for shard 1

Verifying every Phase 00 artifact named in §3-§5 actually exists:

```bash
# Run at next session start, expected exit 0:
test -f workspaces/phase-00-alignment/01-analysis/00-thesis-and-scope.md && \
test -f workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md && \
test -f workspaces/phase-00-alignment/01-analysis/05-runtime-abstraction.md && \
test -f workspaces/phase-00-alignment/02-plans/conformance/01-runtime-swap-contract.md && \
test -d specs && \
[ "$(ls specs/*.md | wc -l)" -eq 38 ]   # 37 specs + _index.md
```

Inheritance audit MUST pass before shard 2 begins.

## 8. Cross-references

- Brief: `workspaces/phase-01-mvp/briefs/00-phase-01-mvp-scope.md`
- Phase 00 closure: `workspaces/phase-00-alignment/.session-notes` (gitignored runtime state)
- ROADMAP: `ROADMAP.md` §35–65
- Specs index: `specs/_index.md`
- Sharding plan: `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` (next shard-1 deliverable)
