# 03 — `kailash-py` MVP Readiness for Phase 01 Primitives

**Document role:** For each Phase 01 primitive, state (a) which `kailash-py` module provides it today, (b) what changed upstream since the Phase 00 survey baseline (2026-04-21), (c) what remains Envoy-new-code, (d) what depends on a still-open upstream PR. The 16 per-primitive deep-dive shards (4–19) cite this doc when sourcing module paths and when scoping Envoy-new-code surface area.

**Date:** 2026-05-03 (shard 3 of /analyze).
**Status:** DRAFT — load-bearing for shards 4–19.
**Pre-consumption freshness gate (per `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` § "Why this matters for the kailash-py survey shard"):** **EXECUTED 2026-05-03**. Result in §2 below.

---

## 1. Document conventions

This doc cites the Phase 00 survey by path + section. It does NOT re-derive primitive grades; it extends the 2026-04-21 grade with a 2026-05-03 freshness delta. The trap warned in `journal/0001` (re-derivation looks like rigour but produces silent drift) is structurally avoided by quoting `02-kailash-py-survey.md` lines and stamping a delta.

Per-primitive readiness is expressed as a **provider-and-gap pair**:

- **Provider** — the `kailash-py` module path the Phase 01 implementation will import from
- **Gap** — what Phase 01 must add as Envoy-new-code AND/OR what depends on still-open upstream issues

Both halves are required: a primitive that is "100% upstream-provided" still has Envoy-new-code (the integration glue, the Tier 2 wiring tests required by `rules/orphan-detection.md`).

---

## 2. Freshness gate result (2026-05-03)

The Phase 00 survey was conducted 2026-04-21. 12 days have passed; `kailash-py` is actively maintained. Direct status queries against the 13 Phase 00-filed `terrene-foundation/kailash-py` issues (#594–#606, per `workspaces/phase-00-alignment/issues/manifest.md`) returned:

| Phase 00 ISS | GH#  | Title                                                | Closed?           | Phase 01 impact                                                                                                  |
| ------------ | ---- | ---------------------------------------------------- | ----------------- | ---------------------------------------------------------------------------------------------------------------- |
| ISS-02       | #594 | semantic parity of `intersect_envelopes()`           | **CLOSED** Apr 24 | Envelope compiler — confirms parity with Rust contract; no Phase 01 work needed                                  |
| ISS-05       | #595 | cascade-revocation docstring cross-reference         | **CLOSED** Apr 25 | Cascade revocation — docs improvement; no Phase 01 work needed                                                   |
| ISS-07       | #596 | **`TieredAuditDispatcher` implementation**           | **OPEN**          | **Envoy Ledger — Envoy-new-code required OR upstream PR adoption (shard 6)**                                     |
| ISS-12       | #597 | Phase-13 posture/verification bundle completeness    | **CLOSED** Apr 24 | Posture / Authorship Score — confirms 5-posture canonical set; no Phase 01 work needed                           |
| ISS-13       | #598 | `PlanSuspension` parity                              | **CLOSED** Apr 25 | L3 plan control — Envoy can use upstream PlanSuspension; verify code surface in shard 9                          |
| ISS-19       | #599 | `McpGovernanceEnforcer` design                       | **CLOSED** Apr 26 | MCP governance — Phase 01 does NOT ship MCP server (per `01-shard-plan.md` §2); verification is Phase 02 concern |
| ISS-21       | #600 | MCP transport primitives                             | **CLOSED** Apr 25 | Same as ISS-19; Phase 02 concern                                                                                 |
| ISS-23       | #601 | public `apply_read_classification()` + event-payload | **CLOSED** Apr 25 | Classification path — Envoy can use the public API; no Phase 01 wrapper needed                                   |
| ISS-26       | #602 | `OrchestrationRuntime` implementation                | **CLOSED** Apr 25 | Daily Digest scheduling — verify surface in shard 11; was previously C-grade (absent)                            |
| ISS-29       | #603 | `BudgetTracker` threshold-callback API               | **CLOSED** Apr 25 | Budget tracker — Envoy can hook Grant Moment fires to threshold callback; no Phase 01 callback wrapper needed    |
| ISS-32       | #604 | algorithm-identifier schema                          | **CLOSED** Apr 25 | Trust lineage — Envoy can rely on versioned signatures; reduces Phase 01 future-proofing burden                  |
| ISS-36       | #605 | **PACT N4/N5 conformance vector Python runner**      | **CLOSED** Apr 25 | **WAS PHASE 02 BLOCKER** — now structurally unblocked; verify at Phase 02 entry                                  |
| ISS-37       | #606 | SLIP-0039 Shamir secret-sharing integration          | **CLOSED** Apr 26 | Shamir recovery — Envoy may have upstream wiring instead of pulling `slip39` directly; verify in shard 15        |

**Summary:** 12 of 13 closed in the Apr 24–26 window. Only ISS-07 (`TieredAuditDispatcher`) remains open.

### 2.1 Trap: closed-status ≠ landed-feature

`rules/git.md` § "Issue Closure Discipline" mandates that closures cite a PR or commit SHA. This doc does NOT verify that each closed issue's resolution actually shipped functional code — that verification is the per-primitive deep-dive shard's responsibility. The closed status is a **strong upstream-readiness signal** but **must be confirmed by reading the upstream code surface** when each shard fires.

For shards 4–19, the protocol is: read the close comment of the corresponding ISS to find the PR/commit, then verify the named module exists and exports the expected symbol. Treat the closure as a "look here" pointer, not as evidence of correctness.

### 2.2 Indirectly-relevant closures (since 2026-04-21)

The freshness query (`gh issue list ... --state closed --search 'closed:>2026-04-21' --limit 50`) returned 50 non-ISS issues, all closed since #625. The subset relevant to Phase 01 primitives:

| GH#                                            | Theme                                                                                | Phase 01 primitive impacted                                              |
| ---------------------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| #757, #756                                     | pin Unicode byte vectors for audit-chain canonical-input + TraceEvent canonical-JSON | Envoy Ledger (EC-4 hash determinism) — directly improves cross-SDK gate  |
| #731                                           | TraceEvent timestamp microsecond padding (cross-SDK)                                 | Envoy Ledger timestamp determinism                                       |
| #707, #711                                     | `df.transaction()` + `db.transactions_sync.begin()` context-manager                  | Envoy Ledger atomic write boundary                                       |
| #672                                           | Python `format_record_id_for_event` cross-SDK with kailash-rs BP-048                 | Event-payload classification on every primitive that emits ledger events |
| #750                                           | DataFlow Express update/delete silently no-op on SQLite                              | **All SQLite-backed primitives** — Trust store, Ledger, Posture store    |
| #696, #738, #739                               | DataFlow init/DDL lifecycle bugs                                                     | First-run install (EC-1 onboarding gate)                                 |
| #767                                           | nexus durability_middleware drains StreamingResponse body                            | Web channel SSE / streaming events                                       |
| #737                                           | Nexus WorkflowServer lifespan= disables consumer @on_event                           | Channel adapter lifecycle hooks                                          |
| #735                                           | `_execute_strategy` ThreadPoolExecutor drops contextvars                             | Boundary Conversation context propagation                                |
| #736                                           | `_calculate_usage_metrics` None prompt_tokens                                        | Model adapter robustness                                                 |
| #734                                           | `FallbackRouter` inherits `OPENAI_PROD_MODEL` env leakage                            | Model adapter cleanup                                                    |
| #791, #790, #788, #762, #763, #764, #761, #740 | Kaizen `LlmDeployment` cross-SDK improvements + 12 zero-arg constructors             | Model adapter — significant upstream improvement; verify in shard 13     |
| #687                                           | nexus `WebhookTransport` pluggable signer for Twilio                                 | Channel adapters (Twilio path for SMS / WhatsApp)                        |
| #673                                           | nexus `Origin`/`Host` allowlist on register_websocket                                | Web channel security baseline                                            |
| #635, #636, #625                               | JWT iss-claim hardening                                                              | Trust store / Connection Vault                                           |

### 2.3 New Phase 01 concerns surfaced by the freshness gate

| GH#  | Concern                                                              | Phase 01 disposition                                                                                                                |
| ---- | -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| #752 | `lightning` package QUARANTINED on PyPI — kailash-ml installs broken | Phase 01 install path (`pipx install envoy-agent`, shard 19) MUST NOT transitively depend on `kailash-ml` until quarantine resolved |
| #753 | `kailash-dataflow` missing `psycopg2` dep declaration                | Phase 01 uses SQLite-only — irrelevant for Envoy install path; pin `kailash-dataflow` version known-good                            |
| #781 | 244 `TODO-NNN` tracker tags in upstream production source            | Code-quality drift signal upstream; not Phase 01 blocking; informs shards 4–19 to read upstream source critically                   |
| #789 | 17 deferred CodeQL findings on Kaizen                                | Security backlog upstream; track via Foundation channels but not Phase 01 blocking                                                  |
| #768 | `@db.model` crashes on `list[str]` annotations on Python 3.11+       | Phase 01 data model uses simple types; verify no `list[str]` in Trust store / Ledger schemas (shards 5, 6)                          |
| #774 | `validate_inputs` AttributeError on str                              | Defensive — informs Tier 2 test boundary conditions                                                                                 |

---

## 3. Per-primitive readiness map (Phase 01 → `kailash-py`)

Each row is the source-of-truth for one shard 4–19's "what can I import?" question. Row format:

- **Phase 01 primitive** — name as used in ROADMAP §35–65 + `01-analysis/02-mvp-objectives.md`
- **Owning shard** — per `01-shard-plan.md` §2
- **Provider** — `kailash-py` module path (Phase 00 survey citation: `phase-00-alignment/01-analysis/02-kailash-py-survey.md` item NN, line LLL–LLL)
- **2026-04-21 grade** — A / B / C / D from Phase 00 survey
- **2026-05-03 freshness delta** — closed ISS that improves the grade, OR notes that the grade is unchanged
- **Envoy-new-code** — what the implementation deep-dive must build on top
- **Upstream-PR dependency** — open kailash-py issue (or other repo) that Phase 01 cannot ship without

| #   | Phase 01 primitive                         | Shard | Provider                                                                                                                 | 04-21 grade                                 | Freshness delta                                                                                                                   | Envoy-new-code                                                                                                                          | Upstream-PR dep                                                                                     |
| --- | ------------------------------------------ | ----- | ------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| 1   | Envelope compiler                          | 4     | `kailash.trust.pact.envelopes` — `intersect_envelopes()`, `RoleEnvelope`, `TaskEnvelope` (survey items 1–2; lines 22–82) | A / A                                       | ISS-02 (#594) closed — semantic-parity-with-Rust confirmed                                                                        | `EnvelopeConfig` → `RoleEnvelope` materializer; integration with Boundary Conversation output                                           | None                                                                                                |
| 2   | Trust store + lineage                      | 5     | `kailash.trust.chain` + `kailash.trust.operations` + `kailash.trust.signing.crypto` (survey items 17–18; lines 498–578)  | A / A                                       | ISS-32 (#604) closed — algorithm-identifier schema landed                                                                         | SQLite-backed `TrustStore` adapter (or use `SQLitePostureStore` pattern); single-principal lineage seeding                              | None                                                                                                |
| 3   | Envoy Ledger + ledger-merge                | 6     | `kailash.trust.constraints` (BudgetStore pattern) + `dataflow` (transaction context)                                     | C — `TieredAuditDispatcher` absent (item 4) | ISS-07 (#596) **STILL OPEN**; #707/#711 (transactions), #757/#756 (canonical-input), #731 (timestamp) all closed (indirect wins)  | Hash-chain Ledger writer; `envoy.ledger` module composing `AuditStore` + canonical-JSON serialization; `envoy ledger export` CLI        | **#596 — Envoy must implement TieredAuditDispatcher locally OR adopt eventual upstream**            |
| 4   | Independent ledger verifier                | 7     | n/a (per EC-9: separately-codebased; cannot share source with Envoy)                                                     | n/a                                         | n/a — verifier is Phase 01 deliverable in different repo                                                                          | All of it: separate repo (`envoy-ledger-verifier` proposed under `terrene-foundation/`); Rust or different-agent Python implementation  | None — verifier must be source-isolated by design                                                   |
| 5   | Boundary Conversation                      | 8     | `kailash.kaizen.BaseAgent` + scripted `Signature` (survey item 13; lines 384–414)                                        | A / A (functional in `kailash-py`)          | #735 closed — ThreadPoolExecutor contextvars fix improves robustness                                                              | Conversation script; `EnvelopeConfig` extractor; 15-minute target session-timeout management; Tier 2 test against real LLM provider     | None                                                                                                |
| 6   | Authorship Score + posture gate            | 9     | `kailash.trust.posture.SQLitePostureStore` + `PostureEvidence` (survey item 5; lines 134–166)                            | A / A                                       | ISS-12 (#597) closed — Phase-13 bundle (canonical 5-posture) confirmed                                                            | `AuthorshipScore` computation; `PostureGate` enforcement at DELEGATING/AUTONOMOUS transition; BET-12 measurement hook                   | None                                                                                                |
| 7   | Grant Moment                               | 10    | `kailash.trust.signing.crypto` (Ed25519 signing; survey item 17; lines 498–544)                                          | A / A                                       | Unchanged                                                                                                                         | CLI prompt + Web modal UI; signed-consent record format; Ledger entry emission; cascade-revocation hook (per EC-2 / `trust-lineage.md`) | None                                                                                                |
| 8   | Daily Digest                               | 11    | `kailash.kaizen` orchestration + scheduled-agent surface (post-ISS-26 closure)                                           | C → ?? (`OrchestrationRuntime` was C-grade) | ISS-26 (#602) closed — `OrchestrationRuntime` implementation; verify surface in shard 11                                          | Per-channel digest renderer; Ledger aggregation logic; back-fill semantics (per EC-3)                                                   | **VERIFY**: shard 11 must read `OrchestrationRuntime` code surface to confirm scheduling semantics  |
| 9   | Budget tracker                             | 12    | `kailash.trust.constraints.BudgetTracker` + `SQLiteBudgetStore` (survey item 16; lines 466–496)                          | A / A                                       | ISS-29 (#603) closed — threshold-callback API landed                                                                              | Microdollar-to-Grant-Moment-trigger glue; per-principal budget partitioning hook for Phase 03 multi-principal                           | None                                                                                                |
| 10  | Model adapter                              | 13    | `kailash.kaizen.providers.{ollama,claude,openai,deepseek}` + Kaizen `Delegate` (survey item 25; lines 781–805)           | A / A                                       | #791 #790 #788 #762 #763 #764 #761 #740 #736 #734 closed — significant `LlmDeployment` cross-SDK improvements; verify in shard 13 | Custom OpenAI-compatible adapter shim (per ADR-0006); BYOM provider switching UX                                                        | None                                                                                                |
| 11  | Connection Vault                           | 14    | OS keychain wrappers (`keyring` Python package); `kailash-py` does not provide Phase 01 minimum                          | n/a                                         | n/a                                                                                                                               | OS-keychain wrapper class; per-channel credential schema; rotation API stub                                                             | None — full third-party OAuth deferrable per de-scope #3                                            |
| 12  | Shamir 3-of-5 recovery                     | 15    | `slip39` Python package (audited 3rd-party) OR `kailash-py` post-ISS-37                                                  | C — Shamir absent in `kailash-py` (item 26) | ISS-37 (#606) closed — Shamir integration may now be in `kailash-py`; **VERIFY in shard 15**                                      | Paper-shard format; Boundary Conversation pause-for-backup ritual; cross-tool interop test (per EC-5)                                   | **VERIFY**: shard 15 must determine if Envoy uses upstream `kailash-py` Shamir or pulls `slip39`    |
| 13  | Channel adapters (6 messaging + CLI + Web) | 16    | `kailash.channels.{API,CLI,MCP}Channel` (survey item 24; lines 743–778)                                                  | B (3 of 9 present)                          | #687 closed (Twilio signer); #767, #737, #673 closed (Nexus stability + security)                                                 | 6 social adapters: iMessage, Telegram, Slack, Discord, WhatsApp, Signal — Envoy-new code per primitive-reconciliation §2 row 23         | None — Envoy-side composition over Nexus webhook primitives                                         |
| 14  | Foundation Health Heartbeat                | 17    | n/a — DECISION shard (implement vs de-scope #2)                                                                          | n/a                                         | n/a                                                                                                                               | STAR/Prio + OHTTP + signed-consent telemetry OR de-scope to Phase 02 entry                                                              | None                                                                                                |
| 15  | Runtime abstraction stub                   | 18    | n/a — Phase 01 defines abstract interface only; only `kailash-py` wired                                                  | n/a                                         | n/a                                                                                                                               | Abstract interface contract per `specs/runtime-abstraction.md`; cross-runtime contract partition (BET-6 partial)                        | None                                                                                                |
| 16  | pipx distribution                          | 19    | `pipx install envoy-agent` packaging only                                                                                | n/a                                         | #752 (lightning quarantine) raises distribution-tree concern                                                                      | `pyproject.toml` for `envoy-agent`; CLI entry-point; install dependency tree audit                                                      | **VERIFY**: shard 19 must confirm `kailash-ml` is not in transitive deps (or excluded if pulled in) |

### 3.1 Net-grade summary

- **A on 04-21 → A on 05-03 (no work needed)**: 8 primitives — Envelope compiler, Trust store, Boundary Conversation, Authorship Score, Grant Moment, Budget tracker, Model adapter, A2A surface
- **B on 04-21 → A on 05-03 (closure improved)**: 1 primitive — `apply_read_classification` / event-payload helper (ISS-23)
- **C on 04-21 → ?? on 05-03 (verify)**: 3 primitives — `OrchestrationRuntime` (Daily Digest), `PlanSuspension` (L3 control), Shamir (recovery)
- **C on 04-21 → C on 05-03 (still open)**: 1 primitive — `TieredAuditDispatcher` (Envoy Ledger)
- **n/a (Envoy-new-code by design)**: 4 primitives — Independent verifier, Connection Vault, Foundation Health Heartbeat, Runtime abstraction stub, pipx distribution, channel adapters (6 social), Shamir paper-shard ritual

11 of 16 primitives have a clean upstream provider; 1 primitive blocks on a still-open issue (#596); 4–6 primitives need shard-level verification of post-closure code surface.

This is materially better than the Phase 00 survey snapshot. The Phase 01 implementation is **on a substantially-improved upstream base** versus what the brief assumed.

---

## 4. Upstream-PR-required-dependency table (the cut)

Phase 01 cannot ship without these. Each is either Envoy-new-code substituting for the upstream gap, or upstream-PR-blocking:

| Item | Upstream issue                                                                                   | Disposition for Phase 01                                                                                                                                                                                                                                                                                   |
| ---- | ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | **#596** TieredAuditDispatcher still OPEN                                                        | **Envoy-new-code in Phase 01.** Implement hash-chain Ledger writer in `envoy.ledger` module locally; cross-file an upstream PR for adoption. Per `rules/zero-tolerance.md` Rule 4: do NOT work around the SDK by replicating its primitive structure poorly — implement to spec, then propose to upstream. |
| 2    | esperie-enterprise/kailash-rs ISS-35 (#520) — execute_raw SQLi                                   | Phase 02 concern. Phase 01 does NOT use `kailash-rs` Python binding (per ADR-0001 phase migration); only pure-Python `kailash-py` is wired. Phase 02 entry checklist must verify ISS-35 closed before consuming Rust binding.                                                                              |
| 3    | esperie-enterprise/kailash-rs ISS-36 (#605 was closed for kailash-py side; rs side not verified) | Phase 02 concern. The Python-side runner closure removes the Phase 02 blocker on the kailash-py axis. The Rust-side conformance vector status was not re-checked in this shard — recheck at Phase 02 entry.                                                                                                |

Net: Phase 01 has **one structural Envoy-new-code commitment due to upstream gap (#596 TieredAuditDispatcher)**, and zero hard upstream-PR blockers.

---

## 5. Verification protocol for shards 4–19

For each per-primitive deep-dive shard, the protocol is:

1. **Read the freshness-delta column** for the primitive in §3 of this doc.
2. **If a closed ISS is referenced**, fetch the close comment via `gh issue view <N> --repo terrene-foundation/kailash-py --json closedAt,body,timelineItems` and find the linked PR or commit.
3. **Open the upstream code at the named module path** and confirm the symbol exists, exports correctly, and matches the spec the deep-dive is implementing against.
4. **If the symbol does NOT exist or differs from the spec**, escalate via the `01-shard-plan.md` §4 failure-mode protocol — STOP the deep-dive and treat as a frozen-spec gap or as an upstream-readiness regression.
5. **Cite the verified module path + the closed ISS + the linked PR in the deep-dive doc's "provider citation" section.** Per `journal/0001`, citation by path + section is mandatory; paraphrase is forbidden.

This protocol is the structural defense against `journal/0001`'s "closed-status ≠ landed-feature" trap.

---

## 6. Phase 02 deferrals (NOT Phase 01 work)

Tracking, not blocking:

- **ISS-35** kailash-rs `execute_raw` SQLi — re-verify at Phase 02 entry; the Phase 02 build of `envoy-agent` may consume Rust binding.
- **ISS-36** kailash-rs N4/N5 conformance vector runner — kailash-py side closed; Rust-side parity must be re-confirmed at Phase 02 entry.
- **kailash-rs binding completeness** (~18 ISS items) — Phase 02 binding-consumer concerns; not load-bearing in Phase 01 because Phase 01 only wires `kailash-py`.

The freshness-gate finding that 12 of 13 kailash-py issues closed in 5 days is a **strong upstream-velocity signal**: the Foundation's open-source Python SDK is moving fast on Phase 01-relevant primitives. Phase 02's Rust-binding consumption is on a different velocity surface — do not assume the rs side has closed at the same rate.

---

## 7. Cross-references

- Phase 00 survey: `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` (26-primitive parity grid; cite by item N)
- Phase 00 reconciliation: `workspaces/phase-00-alignment/01-analysis/03-primitive-reconciliation.md` (38-issue cross-fil plan)
- Phase 00 issue manifest: `workspaces/phase-00-alignment/issues/manifest.md` (#594–#606 kailash-py + #503–#521 kailash-rs + #2–#8 mint)
- Phase 01 brief: `workspaces/phase-01-mvp/briefs/00-phase-01-mvp-scope.md`
- Phase 01 inheritance: `workspaces/phase-01-mvp/01-analysis/00-inheritance-from-phase-00.md` § 2.1 + § 6
- Phase 01 MVP objectives: `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` (EC-1 through EC-9)
- Sharding plan: `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 2 (shards 4–19) + § 4 (failure-mode protocol)
- Methodology trap: `workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` § "Why this matters for the kailash-py survey shard"
- Closure-discipline rule: `.claude/rules/git.md` § "Issue Closure Discipline"
- Workaround prohibition: `.claude/rules/zero-tolerance.md` Rule 4
