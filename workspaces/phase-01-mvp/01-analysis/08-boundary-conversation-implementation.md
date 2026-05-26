# 08 — Boundary Conversation — Phase 01 implementation deep-dive

**Document role:** Per the per-shard structure in `01-shard-plan.md` § 2 ("Per-shard structure"), this is the implementation deep-dive for the Boundary Conversation primitive (shard 8 of /analyze, wave-C). It cites frozen specs by path + section per `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` ("citation by path + section is mandatory; paraphrase is forbidden"). It does NOT re-derive frozen specs.

**Date:** 2026-05-03 (shard 8).
**Status:** DRAFT — load-bearing for shards 10 (Grant Moment), 16 (channel adapters); consumes wave-A outputs from shards 4, 5, 6, 13, 14, 15.
**Owning primitive:** Boundary Conversation — THE primary surface for Envoy. Per thesis §2.3 + BET-1 + BET-12, this primitive IS what makes Envoy distinct from Little Snitch class.

**Capacity check:** one primitive, three source specs (`boundary-conversation.md`, `envelope-model.md` for output contract, `shamir-recovery.md` for the S8 pause), ~6 simultaneous invariants tracked (state-machine S0→S10 fidelity; EnvelopeConfig output is envelope-compiler-parseable; pause-resume across S7/S8 mid-conversation pauses; per-state Trust Vault persistence for `envoy init --resume <ritual_id>`; novelty-feedback gate at S3/S5; post-duress banner gate before S0 advance), ≤6 cross-primitive references (Envelope compiler, Trust store, Ledger, Shamir, Connection Vault, Model adapter — at the upper edge of `rules/autonomous-execution.md` budget; the conversation primitive is the most-integrated primitive in Phase 01 by design). Within budget.

**Phase 00 framing reminder:** This shard does NOT re-derive `specs/boundary-conversation.md`. Per `journal/0001`, the spec is frozen — Phase 01's question is "given this spec is frozen, how do we wire `kailash-py` to deliver it?" not "is this spec right?" If a HIGH ambiguity surfaces it triggers `01-shard-plan.md` §4 escalation; §7 below records the (one MED-candidate, no HIGH) result.

---

## 1. Source spec citation (frozen — DO NOT EDIT)

The Boundary Conversation primitive is governed by:

- **`specs/boundary-conversation.md` § Purpose (lines 3–5)** — "First-run onboarding dialogue that compiles EnvelopeConfig."
- **`specs/boundary-conversation.md` § Provenance (lines 7–11)** — Source `01-ux-rituals.md v2 §3`; threats T-018 (visible secret setup), T-023 (Authorship Score seeding); BETs BET-1 (authorship), BET-12 (palatability).
- **`specs/boundary-conversation.md` § State machine (line 15)** — `S0 greet → S1 money → S2 people → S3 topics → S4 hours → S5 first task → S6 template offer → S7 visible secret setup → S8 Shamir ritual → S9 review & sign → S10 complete`. The 11-state DAG is the canonical structure.
- **`specs/boundary-conversation.md` § Questions (lines 17–27)** — per-state input contract: S1 monthly ceiling USD; S2 blocked contacts; S3 blocked topics (semantic rules); S4 operating hours; S5 first-task intent; S6 template import (Foundation-Verified only in Phase 01 local cache) OR from-scratch; S7 visible secret (icon + color + phrase); S8 Shamir 3-of-5 default + 5-in-safes alternative + custom; S9 plain-language envelope summary + sign.
- **`specs/boundary-conversation.md` § Duration (lines 29–31)** — "~15min target. 8min minimum-path (template + visible secret + Shamir)." This is the EC-1 acceptance gate (per `02-mvp-objectives.md` EC-1: ≤25min for first-time users with N=3).
- **`specs/boundary-conversation.md` § Persistence + resume (lines 33–35)** — "Every answer transition persists state to Trust Vault. `envoy init --resume <ritual_id>` rehydrates." This is the per-state durability contract; it answers Key design question 5 directly.
- **`specs/boundary-conversation.md` § Novelty feedback (T-023) (lines 37–39)** — "If user-authored answer compiles to near-duplicate (Jaccard > 0.85 or adversarial-wording classifier > 0.8) of template constraint, UX prompts user to rephrase or re-choose." This is the inline gate that prevents Authorship Score gaming at authoring time.
- **`specs/boundary-conversation.md` § Post-duress review step (§3.5a — V2 C-02 fix) (lines 41–43)** — banner above the conversation if shadow segment contains unread duress event; visible-secret-bound modal MUST be acknowledged before S0 advance.
- **`specs/boundary-conversation.md` § Error taxonomy (lines 45–55)** — 7 typed errors: `RitualResumeStateMissingError`, `InvalidStateTransitionError`, `TemplateNotInLocalCacheError`, `ShamirRitualIncompleteError`, `NoveltyFeedbackBlockError`, `VisibleSecretMissingError`, `DuressBannerUnacknowledgedError`.
- **`specs/boundary-conversation.md` § Cross-references (lines 57–64)** — envelope-model (compile target), authorship-score (novelty + minimum-impact algorithms), shamir-recovery (ritual flow), trust-vault (visible secret + ritual state storage), data-model (shadow segment for duress), threat-model (T-018, T-023).
- **`specs/boundary-conversation.md` § Test location (lines 66–73)** — `tests/e2e/test_boundary_conversation_full_path.py` (Tier 3 ~15min budget), `tests/e2e/test_boundary_conversation_minimum_path.py` (8min), `tests/integration/test_resume_from_each_state.py` (Tier 2), `tests/regression/test_t018_*.py`, `tests/regression/test_t023_*.py`, `tests/integration/test_post_duress_banner.py`.

**Cross-spec contracts the conversation must satisfy:**

- **`specs/envelope-model.md` § Schema (lines 14–84)** — output of S9 sign-step MUST be a parseable `EnvelopeConfig` per the canonical 5-dimension wire format (Financial, Operational, Temporal, Data Access, Communication + metadata + composition_rules + cross_domain_rules_authored + tool_output_budget_bytes + semantic_checks). Per `04-envelope-compiler-implementation.md` § 4 (`EnvelopeConfigInput` interface), the conversation emits an `EnvelopeConfigInput` — a structured envelope-authoring outcome — which the Envelope Compiler validates, normalizes (NFC), canonicalizes (JCS), and signs.
- **`specs/envelope-model.md` § Field semantics for late-added fields** — `cross_domain_rules_authored` is a top-level array; `tool_output_budget_bytes` is a top-level int; `semantic_checks.tool_output_classifier_ensemble` is mandatory. Phase 01 conversation does NOT prompt the user for these directly (they default from Foundation-Verified template defaults at S6 OR fall to spec-mandated minima); the conversation MUST emit them populated regardless.
- **`specs/shamir-recovery.md` § Algorithm (lines 13–15)** — SLIP-0039 via audited libraries; Phase 00 crypto audit required. Per `15-shamir-recovery-implementation.md` (wave-B output), the S8 ritual is a `kailash.shamir`-or-`slip39` wrapped pause-for-backup that the conversation invokes mid-flow.
- **`specs/grant-moment.md` § State machine (line 76)** — `M0 construct → M1 render → M2 await decision → M3 sign or decline → M4 complete`. Boundary Conversation does NOT issue Grant Moments during normal first-run flow (the user is authoring the envelope from scratch, not asking permission to violate it). However, post-EC-1, subsequent envelope edits via re-running the conversation MAY produce Grant-Moment-like consent moments at S9 sign-step (per shard 4 § 5 row 2 — "every Grant Moment that authors an exception triggers a child-envelope compile"). Phase 01 ships with this as documentation, not as a wired flow.

These artifacts are frozen per Phase 00 closure. Per `journal/0001` and `rules/specs-authority.md` MUST Rule 5b, this shard MUST NOT propose edits to `specs/boundary-conversation.md`. If a HIGH-severity gap surfaces, escalate via `01-shard-plan.md` § 4 failure-mode protocol (§ 7 below).

---

## 2. Verified provider citation — Kaizen `BaseAgent` + scripted `Signature` + L3 `Plan` + `PlanSuspension`

### 2.1 Verification protocol (per `03-kailash-py-mvp-readiness.md` § 5)

The Phase 00 survey (2026-04-21) graded the Boundary Conversation row A/A — `kailash.kaizen.BaseAgent` + scripted `Signature` are functional. The `03-kailash-py-mvp-readiness.md` § 3 row 5 freshness delta names ISS-13 (#598 PlanSuspension) closed Apr 25 + #735 (ThreadPoolExecutor contextvars) closed Apr 30 + #736 (None prompt_tokens) closed Apr 30 as the relevant post-survey closures. Per § 5 verification protocol, this shard fetched issue-close metadata and inspected upstream code at `~/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/`.

Issue closure verification (state + closed-at, queried 2026-05-03):

| GH#  | Title                                                                                      | Closed at  | Upstream landing point                                                                                                                                       |
| ---- | ------------------------------------------------------------------------------------------ | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| #598 | parity: Implement `PlanSuspension` (Rust has `SuspensionReason` + `SuspensionRecord`)      | 2026-04-25 | `kaizen/l3/plan/suspension.py` (336 LOC) — 5 `*Reason` dataclasses + Union alias + `SuspensionRecord` + `to_dict`/`from_dict`; re-exported via `__init__.py` |
| #735 | bug(kaizen): \_execute_strategy ThreadPoolExecutor drops contextvars                       | 2026-04-30 | contextvars propagation fix on the LLM strategy executor                                                                                                     |
| #736 | bug(kaizen): \_calculate_usage_metrics crashes on None prompt_tokens from custom providers | 2026-04-30 | usage-metrics defensive null-handling fix                                                                                                                    |

3/3 verified closed. Per `03-kailash-py-mvp-readiness.md` § 2.1 ("closed-status ≠ landed-feature"), each closure was treated as a "look here" pointer; the corresponding code landing point is named above.

### 2.2 `BaseAgent` — the conversational substrate

**Module path:** `kaizen.core.base_agent` (`packages/kailash-kaizen/src/kaizen/core/base_agent.py`, line 49).

`class BaseAgent(MCPMixin, A2AMixin, Node)` is the upstream-provided conversational agent. It composes MCPMixin (tool-protocol surface), A2AMixin (agent-to-agent surface), and `Node` (Kailash workflow primitive). For Boundary Conversation, neither MCPMixin nor A2AMixin is consumed in Phase 01 (no MCP server in P01 per `01-shard-plan.md` §2; A2A is Phase 03 cross-principal). The Node base provides `execute()`-shaped invocation and lifecycle hooks that the conversation runtime drives.

The shard does NOT subclass `BaseAgent` directly. Per `rules/orphan-detection.md` Rule 1 + `facade-manager-detection.md` Rule 3, Envoy composes upstream by name — `BoundaryConversationRuntime` (§ 4) holds a `BaseAgent` instance and routes per-state `Signature`-shaped prompts through it.

### 2.3 `Signature` — structured input/output contract

**Module path:** `kaizen.signatures.core` (`packages/kailash-kaizen/src/kaizen/signatures/core.py`, line 249).

`class Signature(metaclass=SignatureMeta)` is the structured-output contract. For Boundary Conversation, each state S1–S9 has a state-specific `Signature` subclass declaring input fields (the user's reply) + output fields (the structured extraction). The `SignatureCompiler` (line 1015) compiles the schema to a JSON-schema-shaped contract that the LLM provider's structured-output mode honors. This is the answer to Key design question 2: **EnvelopeConfig extraction uses structured-output Signature pattern, NOT post-hoc LLM extraction**. The structured-output path produces a parseable extraction at the LLM-call boundary; failure-to-parse triggers `InvalidStateTransitionError` and re-prompts the same state. Post-hoc extraction would double the LLM call count and put parseable-EnvelopeConfig at risk for the EC-1 acceptance gate.

### 2.4 L3 `Plan` + `PlanSuspension` — the conversation-as-DAG substrate

**Module path:** `kaizen.l3.plan.types` (`packages/kailash-kaizen/src/kaizen/l3/plan/types.py`).

Verified upstream surface:

- `class PlanState(str, Enum)` line 178 — state-machine enum carrier.
- `class PlanNode` line 218 — node primitive carrying gradient classification + held-action semantics + suspension hooks.
- `class Plan` line 303 — top-level container; `suspension: Any = None` field at line 327 carrying a `SuspensionRecord | None` (cross-SDK parity with Rust `Plan.suspension`); `to_dict()` / `from_dict()` round-trip at lines 349–391.

**Module path:** `kaizen.l3.plan.suspension` (`packages/kailash-kaizen/src/kaizen/l3/plan/suspension.py`, 336 LOC, landed via #598).

5 `*Reason` dataclasses mirroring Rust:

- `class HumanApprovalGateReason` line 69 — `kind: "human_approval_gate"`; `held_node`, `reason`. Cross-SDK parity per the issue body's "Phase 01 load-bearing (Envoy Grant Moment is structurally a `HumanApprovalGate`)".
- `class CircuitBreakerTrippedReason` line 81 — `kind: "circuit_breaker_tripped"`.
- `class BudgetExceededReason` line 94 — `kind: "budget_exceeded"`; `dimension`, `consumed`, `limit`.
- `class EnvelopeViolationReason` line 110 — `kind: "envelope_violation"`. Module docstring lines 120–122: "four variants today; cross-SDK parity for `EnvelopeViolation` is hand-rolled here. Fields kept symmetric with Rust counterpart so the wire-format `kind` tag MUST remain `envelope_violation`."
- `class ExplicitCancellationReason` line 132 — `kind: "explicit_cancellation"`; `reason`, `cancelled_at`.

Union alias `SuspensionReason` line 147; `SuspensionRecord` `@dataclass` line 278 with `reason: SuspensionReason` (line 309) + `__init__` constructor with reason payload (line 319). Both ship `to_dict()` / `from_dict()` so a serialized SuspensionRecord round-trips between Python and Rust SDKs (per the suspension.py module docstring lines 12–14).

This answers Key design question 3 directly: **mid-conversation pauses (S8 Shamir, S7 visible secret + Connection Vault writes) compose with `PlanSuspension` semantics by emitting a `Plan.suspension = SuspensionRecord(reason=ExplicitCancellationReason(...))` for non-error pauses and `Plan.suspension = SuspensionRecord(reason=HumanApprovalGateReason(...))` if the conversation is paused for explicit user attention.** Resume rehydrates the suspension and clears the field on continuation, per the Plan.suspension docstring lines 308–312 ("The field is cleared on successful resume.").

### 2.5 `_execute_strategy` ThreadPoolExecutor contextvars fix (#735)

The bug pre-fix: when `BaseAgent`'s LLM invocation strategy spawned a ThreadPoolExecutor task, Python `contextvars` did NOT propagate to the worker thread. For Boundary Conversation, the load-bearing context that needs to propagate is (a) the active `principal_id`, (b) the conversation `ritual_id`, (c) the model-router primitive-key (per `13-model-adapter-implementation.md` § 3.2 — `EnvoyModelRouter.for_primitive("boundary_conversation")`). Without #735's fix, the worker thread would see empty contextvars; the per-primitive model override would silently drop to the global default; the Ledger entry's `principal_id`/`ritual_id` would be unset. Closed Apr 30; Phase 01 inherits the fix.

### 2.6 `_calculate_usage_metrics None prompt_tokens` fix (#736)

For BYOM `openai_compatible` / `anthropic_compatible` paths (per `13-model-adapter-implementation.md` § 2.6) where the user's chosen provider may return usage metrics without `prompt_tokens` populated, the pre-fix code crashed in `_calculate_usage_metrics`. Boundary Conversation makes ~9 LLM calls minimum (S1–S9); a single None-`prompt_tokens` response would crash the entire conversation. Closed Apr 30; Phase 01 inherits the fix.

### 2.7 What `kailash-py` does NOT provide (Envoy-new-code surface)

The conversation script — the per-state DAG, the per-state Signature subclasses, the resumption coordinator, the EnvelopeConfig assembler, the BET-1 measurement hook — is NOT in upstream. `BaseAgent` is the conversational atom; `Signature` is the per-call I/O contract; `Plan` is the suspension-aware container. The conversation-shaped composition above them is Envoy-new-code per § 3 below.

---

## 3. Envoy-new-code surface

### 3.1 Conversation-script-as-DAG (answers Key design question 1)

**Choice: structured DAG of conversation states (Kaizen L3 `Plan`), NOT literal text in code.**

Rationale (cited, not paraphrased):

1. **Pause-resume coordination requires DAG semantics.** Per `specs/boundary-conversation.md` § Persistence + resume (lines 33–35), every answer transition persists state to Trust Vault and `envoy init --resume <ritual_id>` rehydrates. A literal-text-script (e.g. an imperative `for state in [S0, S1, ...]:` loop with embedded `input()` calls) cannot serialize the in-flight state cleanly because the loop's local variables are not persistable. A `Plan` with `PlanNode` per state IS persistable — `Plan.to_dict()` round-trips through Trust Vault.
2. **Mid-conversation pauses (S8 Shamir, S7 Connection Vault writes) need typed suspensions.** Per § 2.4, `Plan.suspension = SuspensionRecord(reason=...)` is the typed-pause primitive. A literal-text script would have to reinvent typed pauses; the L3 Plan substrate gives them for free with cross-SDK serialization parity.
3. **Per-state Signature compilation requires per-node binding.** Each S1–S9 has a distinct `Signature` subclass. Binding the Signature to a `PlanNode` (rather than to a string identifier in a script) gives the model adapter (per `13-model-adapter-implementation.md` § 3.2) a structural place to attach per-state configuration (e.g. S5 first-task intent may want a tool-capable model; S2/S4 are simple constraint extraction).
4. **EC-1 acceptance gate requires per-state telemetry.** Per `02-mvp-objectives.md` EC-1 acceptance gate ("≥3 distinct first-time-user sessions complete BoundaryConversation in ≤25 minutes" + BET-12 falsifiability), the conversation MUST emit per-state latency + per-state retry-count Ledger entries to support the BET-12 measurement hook (per § 5.4 below). PlanNode-per-state gives a structural attachment point for this telemetry.

The Plan DAG shape:

```
S0_greet ──→ S1_money ──→ S2_people ──→ S3_topics ──→ S4_hours ──→ S5_first_task
                                                  ↑                       │
                                  (NoveltyFeedbackBlockError → re-prompt) │
                                                                          ▼
S10_complete ←── S9_review_sign ←── S8_shamir ←── S7_visible_secret ←── S6_template_offer
        ↑              ↑                ↑                ↑
        │              │      ShamirRitualIncomplete   VisibleSecretMissing
        │      DuressBannerUnacknowledged  (force back to S8)  (force back to S7)
        │
ShamirRitualIncomplete cannot reach S9 (force back to S8)
VisibleSecretMissing cannot reach S9 (force back to S7)
```

S8 (Shamir) and S7 (Connection Vault writes) are pause-points that suspend the Plan with `ExplicitCancellationReason` while the user completes the ritual; resumption clears `Plan.suspension` and advances. The DAG is mostly linear with two backward edges (novelty re-prompt at S3/S5; gate-back-edges if S7/S8 not completed before S9).

### 3.2 EnvelopeConfig extraction (answers Key design question 2)

**Choice: structured-output `Signature` pattern, NOT post-hoc LLM extraction.**

Per `specs/envelope-model.md` § Schema (lines 16–84), the output is a 5-dimension constrained schema. A structured-output Signature compiles to JSON-schema; the LLM call returns a parseable JSON object validated against the schema at the SDK boundary. The conversation runtime accumulates per-state extractions into an `EnvelopeConfigInput` (per `04-envelope-compiler-implementation.md` § 4), which is the documented input to `EnvelopeCompiler.compile(...)`.

The cross-shard invariant from shard 9 (Authorship Score) — "Envelope compiler MUST sort `authored_constraints` in JCS canonical order at construction time" — has a parallel obligation here: **Boundary Conversation MUST emit `authored_constraints[]` arrays in lexicographic-ascending `constraint_id` order (the JCS canonical order the compiler expects)**. This is upstream-of-the-compiler defensive hygiene; the compiler will re-sort at JCS canonicalization, but emitting in canonical order at the source means the compiler's pre-canonicalization-equality assertion (per `04-envelope-compiler-implementation.md` § 4 step 7) does not need to handle reorder-by-the-compiler-only cases. This answers Key design question 6 directly.

### 3.3 Pause-resume coordinator (answers Key design questions 3 + 5)

**Resumption on session loss (Key design question 5): persistent state in Trust Vault, NOT single-session ephemeral.**

Per `specs/boundary-conversation.md` § Persistence + resume (lines 33–35), every answer transition persists state to Trust Vault. The `RitualResumeStateMissingError` (line 49) covers the case where the user references a `ritual_id` absent from Trust Vault (Trust Vault corruption OR user typed wrong id) — disposition is "Restart from S0; OR Shamir-recover Trust Vault" (line 49). Phase 01 implements per-state Trust-Vault persistence:

- After each state transition `Sn → Sn+1`, Envoy writes `(ritual_id, current_state, accumulated_envelope_input, timestamp)` to Trust Vault under a dedicated `boundary_conversation_state` table.
- `envoy init --resume <ritual_id>` reads the row, rehydrates an in-memory `Plan` whose current node matches `current_state` and whose `Plan.metadata` carries `accumulated_envelope_input`, and resumes from the next prompt.
- If the user closes the terminal mid-S5 (after answering S1-S4), reopening with `envoy init --resume <ritual_id>` brings them back at S5 with S1-S4 answers intact.

**Mid-conversation pauses (Key design question 3) compose with `PlanSuspension` semantics:**

- **S7 visible-secret setup → Connection Vault write.** Per `15-connection-vault-implementation.md` (wave-A), the user's visible secret (icon + color + phrase) is stored in the Trust Vault, NOT the Connection Vault — Connection Vault holds API credentials, not user-secret material. Phase 01 corrected interpretation: S7 writes the visible secret to Trust Vault via `TrustStoreAdapter.set_visible_secret(...)` (per `05-trust-store-implementation.md`); subsequent post-S7 channel-adapter setup MAY write API credentials to Connection Vault (per `14-connection-vault-implementation.md`) but this is post-EC-1, NOT during the 15-minute conversation. The shard treats S7 as Trust Vault write only.
- **S8 Shamir ritual.** Per `15-shamir-recovery-implementation.md` (wave-B), S8 invokes `ShamirRitualCoordinator.run_first_time_ritual(*, threshold=3, total_shards=5)` which is a pause-for-physical-action ritual: the user prints/writes 5 cards, distributes 3 to safes / 2 to humans, and confirms completion. The conversation suspends with `Plan.suspension = SuspensionRecord(reason=ExplicitCancellationReason(reason="shamir_ritual_in_progress", cancelled_at=...))` while the user completes the physical ritual. On user-confirmed completion via `envoy boundary resume <ritual_id>`, the suspension is cleared and S8 advances to S9. If the user attempts to advance to S9 without completing S8, `ShamirRitualIncompleteError` (per spec line 52) raises and forces back to S8.
- **Grant Moment mid-conversation? Not in Phase 01.** Per § 1 above, Boundary Conversation does NOT issue Grant Moments during normal first-run flow. The user is authoring the envelope from scratch; there is no envelope to violate yet. Subsequent conversation re-runs (Phase 02+ envelope edit flows) MAY surface Grant-Moment-like consent at S9 sign-step for child-envelope compiles (per `04-envelope-compiler-implementation.md` § 4 frozen-context default), but Phase 01 ships the first-time-author path only.

### 3.4 15-minute pacing + per-step latency budget (answers Key design question 4)

Per `specs/boundary-conversation.md` § Duration (lines 29–31): "~15min target. 8min minimum-path." Per `02-mvp-objectives.md` EC-1 acceptance gate: ≤25min for first-time users (15min target + 66% buffer).

**Per-state user-facing latency budget (plain-language framing per `rules/communication.md`):**

- State greeting + question render: ≤1s. The model adapter MAY stream the question; the user reads while it streams.
- LLM extraction of user reply: ≤8s (per `kailash.kaizen.providers.llm.<provider>.chat_async` typical p95 against Anthropic Claude or OpenAI GPT-4-class model; local Ollama may run higher but is BYOM choice). The user MUST see a "thinking..." indicator if the extraction takes > 2s — per `rules/communication.md` MUST NOT "Present raw error messages — translate to impact": empty silence is anxiety-inducing, an indicator is the impact translation.
- State transition write to Trust Vault: ≤200ms (real SQLite write, single row, indexed).
- Pause-resume rehydration on `envoy init --resume <ritual_id>`: ≤2s (read 1 row from Trust Vault; reconstruct Plan from `accumulated_envelope_input`; render the next prompt).

Total per-state user-facing time budget: ~10s computational (1s render + 8s LLM extraction + 1s margin) + N-seconds of human reading/typing. For 9 LLM-driven states (S1-S9): 9 × 10s = 90s of computational time + 9 × ~80s of human time (~12min of conversation). This fits the 15min target for engaged users; the 25min EC-1 acceptance gate accommodates first-time users who pause to think.

**For the model adapter, this constrains the per-primitive model choice.** Per `13-model-adapter-implementation.md` § 3.2, `EnvoyModelRouter.for_primitive("boundary_conversation")` reads `ENVOY_BOUNDARY_MODEL` from `.env`. The default (per ADR-0006 BYOM) is the user's chosen provider's chosen model; the conversation does NOT override unless the user explicitly sets `ENVOY_BOUNDARY_MODEL`. For local-Ollama deployments where the local model is slow (e.g. unquantized 70B on 24GB VRAM), the conversation MAY exceed the 8s p95 — the user is BYOM-responsible for choosing a model fast enough; per `rules/zero-tolerance.md` Rule 4 we do NOT work around the user's BYOM choice.

### 3.5 Novelty feedback gate at S3/S5 (T-023)

Per `specs/boundary-conversation.md` § Novelty feedback (lines 37–39): if user-authored answer compiles to near-duplicate (Jaccard > 0.85 or adversarial-wording classifier > 0.8) of template constraint, UX prompts user to rephrase or re-choose. Per `09-authorship-score-implementation.md` (wave-B), the novelty algorithm is owned by `envoy.authorship.NoveltyChecker`. Boundary Conversation invokes `NoveltyChecker.check_against_templates(...)` at S3 (blocked topics) and S5 (first-task intent) before persisting the state-Sn extraction. Failure raises `NoveltyFeedbackBlockError` (per spec line 53) and re-prompts at the same state. Manual retry per spec table.

**Phase 01 caveat:** the adversarial-wording classifier (Jaccard > 0.85 OR classifier > 0.8) is a Phase 04 ensemble per `model-adapter.md` open question 2 (leak-canary corpus governance — Foundation publishes corpus in P04). Phase 01 ships the **Jaccard portion only** (lexical near-duplicate detection against local-cache template constraints); the classifier portion is a Phase 04 deferral with a sunset clause per `rules/zero-tolerance.md` Rule 4. This is consistent with the spec NOT naming the classifier as Phase 01 mandatory — the spec OR is permissive.

### 3.6 Post-duress banner gate (§3.5a)

Per `specs/boundary-conversation.md` § Post-duress review step (lines 41–43), if shadow segment contains unread duress event, a banner surfaces above the conversation. Phase 01 implementation: at S0 entry (greet), the runtime queries `TrustStoreAdapter.shadow_segment_unread_duress_events(...)`; if non-empty, render the visible-secret-bound modal first; advance to S0 prompt only after `acknowledged=True` per `DuressBannerUnacknowledgedError` semantics (spec line 55). The duress event detail (time + recommended immediate actions) is rendered with the user's visible secret as the structural anti-spoofing defense per `specs/trust-vault.md` cross-reference.

Phase 01 caveat: the `shadow_segment` and duress-event detection mechanism is `specs/data-model.md` shadow-segment-owned. Per `05-trust-store-implementation.md`, the trust-store adapter exposes `shadow_segment_unread_duress_events()` as a stub returning `[]` in Phase 01 (no duress-detection wired in P01); Phase 02+ wires the real detection. The conversation correctly invokes the banner gate; the gate will remain inert until shadow segment populates.

### 3.7 Net Envoy-new-code surface (Phase 01)

Six modules under `envoy-agent/src/envoy/boundary_conversation/`:

1. `envoy.boundary_conversation.runtime.BoundaryConversationRuntime` — facade; composes `BaseAgent` + per-state `Signature`s + `Plan` + Trust Vault + Ledger writer + model router; ~250 LOC.
2. `envoy.boundary_conversation.script.BoundaryConversationScript` — per-state Plan-DAG construction; per-state Signature subclass declarations; ~200 LOC.
3. `envoy.boundary_conversation.signatures` — 9 `Signature` subclasses (one per S1-S9); per-state JSON-schema for structured-output; ~300 LOC.
4. `envoy.boundary_conversation.envelope_assembler.EnvelopeConfigInputAssembler` — accumulates per-state extractions into an `EnvelopeConfigInput` for the Envelope Compiler; emits in JCS-canonical-order constraints (§ 3.2); ~150 LOC.
5. `envoy.boundary_conversation.resume.RitualResumeCoordinator` — Trust-Vault-backed per-state persistence + `envoy init --resume <ritual_id>` rehydration; ~200 LOC.
6. `envoy.boundary_conversation.bet12_telemetry.BET12TelemetryHook` — per-state latency + per-state retry-count Ledger emission; surfaces EC-1 acceptance-gate measurements; ~80 LOC.

Total Envoy-new-code: ~1180 LOC (within shard load-bearing-logic budget per `rules/autonomous-execution.md` § Per-Session Capacity Budget — much of the 1180 is per-state Signature declarations, which are pattern-stamping rather than load-bearing logic; the load-bearing logic is the Plan-DAG composition + resume coordinator + envelope assembler ≈ 600 LOC).

---

## 4. Class structure sketch (interfaces only — no implementation)

```python
# envoy/boundary_conversation/runtime.py
class BoundaryConversationRuntime:
    """Facade composing BaseAgent + Signature + Plan + Trust Vault + Ledger.

    Per rules/facade-manager-detection.md Rule 3: takes dependencies explicitly,
    no global lookup, no self-construction.
    """

    def __init__(self,
                 *,
                 model_router: "envoy.model.router.EnvoyModelRouter",
                 trust_store: "envoy.trust.store.TrustStoreAdapter",
                 ledger: "envoy.ledger.facade.EnvoyLedger",
                 envelope_compiler: "envoy.envelope.compiler.EnvelopeCompiler",
                 shamir_coordinator: "envoy.shamir.ShamirRitualCoordinator",
                 novelty_checker: "envoy.authorship.NoveltyChecker") -> None: ...

    async def start(self, *, principal_id: str) -> str:
        """Begin a fresh conversation. Returns ritual_id.
        Persists initial state to Trust Vault. Emits Ledger entry of type
        ReasoningCommit (per shard 6 § 5.1) marking S0 entry.
        """

    async def resume(self, ritual_id: str) -> None:
        """Rehydrate from Trust Vault. Raises RitualResumeStateMissingError
        if ritual_id absent. Continues from the persisted current_state.
        """

    async def advance(self, ritual_id: str, user_input: str) -> "ConversationOutcome":
        """Process the user's reply at the current state. Runs the per-state
        Signature against the model router. On extraction success, persists
        new state to Trust Vault, emits Ledger ReasoningCommit, advances.
        On extraction failure, raises InvalidStateTransitionError.
        At S3/S5, applies novelty check; raises NoveltyFeedbackBlockError on
        near-duplicate.
        At S8, invokes shamir_coordinator and suspends (PlanSuspension);
        returns ConversationOutcome.PAUSED.
        At S9, builds EnvelopeConfigInput, invokes envelope_compiler.compile(),
        signs the resulting EnvelopeConfig, writes Genesis Trust record.
        At S10, returns ConversationOutcome.COMPLETE.
        """

    def current_plan(self, ritual_id: str) -> "Plan": ...

# envoy/boundary_conversation/script.py
class BoundaryConversationScript:
    """Builds the Plan DAG: S0..S10 PlanNodes with state-to-state edges."""

    def build_plan(self) -> "Plan": ...

    def signature_for_state(self, state: "PlanState") -> "Signature": ...
    # Returns per-state Signature subclass:
    #   S1 → S1MoneySignature
    #   S2 → S2PeopleSignature
    #   S3 → S3TopicsSignature  (with novelty check)
    #   S4 → S4HoursSignature
    #   S5 → S5FirstTaskSignature  (with novelty check)
    #   S6 → S6TemplateSignature
    #   S7 → S7VisibleSecretSignature
    #   S8 → S8ShamirSignature  (suspend-aware)
    #   S9 → S9ReviewSignSignature

# envoy/boundary_conversation/signatures/__init__.py
class S1MoneySignature(Signature):
    """Input: user reply; output: monthly_ceiling_microdollars: int."""
    pass  # ~40 LOC × 9 states

# envoy/boundary_conversation/envelope_assembler.py
class EnvelopeConfigInputAssembler:
    """Accumulates per-state extractions. Emits constraints in JCS-canonical
    (lexicographic constraint_id ascending) order — answers Key Design Q6.
    """

    def feed(self, state: "PlanState", extraction: dict) -> None: ...

    def assemble(self) -> "EnvelopeConfigInput": ...
        # Build the EnvelopeConfigInput per envelope-model.md § Schema.
        # Emit financial.authored_constraints[] sorted by constraint_id asc.
        # Emit operational/temporal/data_access/communication similarly.
        # Default tool_output_budget_bytes per spec minimum.
        # Default semantic_checks.tool_output_classifier_ensemble per spec.
        # cross_domain_rules_authored: [] in Phase 01 first-time-author path.

# envoy/boundary_conversation/resume.py
class RitualResumeCoordinator:
    """Trust-Vault-backed per-state persistence."""

    def persist_state(self, ritual_id: str, plan: "Plan",
                      assembler_state: dict) -> None: ...

    def load_state(self, ritual_id: str) -> tuple["Plan", dict]: ...
        # Raises RitualResumeStateMissingError if ritual_id absent.

    def list_pending_rituals(self, principal_id: str) -> list[str]: ...

# envoy/boundary_conversation/bet12_telemetry.py
class BET12TelemetryHook:
    """Per-state latency + per-state retry-count Ledger emission for EC-1."""

    def state_entered(self, ritual_id: str, state: "PlanState") -> None: ...
    def state_completed(self, ritual_id: str, state: "PlanState",
                        latency_ms: int, retry_count: int) -> None: ...
    def conversation_completed(self, ritual_id: str,
                                total_duration_seconds: int) -> None: ...
        # Final emit. EC-1 acceptance gate: total_duration_seconds <= 25*60.

@dataclass
class ConversationOutcome:
    state: Literal["IN_PROGRESS", "PAUSED", "COMPLETE", "ERROR"]
    paused_for: Optional[Literal["shamir_ritual"]] = None
    envelope_id: Optional[str] = None  # set on COMPLETE
    error: Optional[Exception] = None
```

Interfaces only. No production logic in this shard.

---

## 5. Integration points

### 5.1 With Envelope Compiler (shard 4)

Per `04-envelope-compiler-implementation.md` § 5 row 1, "the Conversation's Kaizen `BaseAgent` Signature emits an `EnvelopeConfigInput`; the compiler validates and emits `EnvelopeConfig`." Boundary Conversation's `EnvelopeConfigInputAssembler.assemble()` (§ 4 above) is the producer; `EnvelopeCompiler.compile(input, parent=None)` is the consumer at S9 sign-step. The compiler's first-time-author path (`parent=None`) is THE EC-1 acceptance gate per `04-envelope-compiler-implementation.md` § 4 frozen-context default.

The cross-shard invariant from shard 9 (Authorship Score) — `authored_constraints` MUST be emitted in JCS canonical order (lexicographic `constraint_id` ascending) — is satisfied by `EnvelopeConfigInputAssembler` per § 3.2.

### 5.2 With Trust Store (shard 5)

Per `05-trust-store-implementation.md`, the Trust Vault (master-key-encrypted SQLite) holds: (a) the user's visible secret (set at S7), (b) the Genesis trust record (signed at S9 completion), (c) Boundary-Conversation per-state persistence rows for `envoy init --resume`. The Boundary Conversation runtime invokes `TrustStoreAdapter`:

- S7 → `TrustStoreAdapter.set_visible_secret(principal_id, icon, color, phrase)`.
- S9 → `TrustStoreAdapter.seed_genesis(principal_id, envelope_id, posture="PSEUDO")`.
- After every state transition → `TrustStoreAdapter.persist_boundary_conversation_state(ritual_id, plan_dict, assembler_dict)`.
- At `envoy init --resume <ritual_id>` → `TrustStoreAdapter.load_boundary_conversation_state(ritual_id)`.

### 5.3 With Envoy Ledger (shard 6)

Per `06-envoy-ledger-implementation.md` § 5.1 row 3, Boundary Conversation appends `ReasoningCommit` and `session_boundary_crossed` Ledger entries. Phase 01 detail:

- `S0 entered → ReasoningCommit{state: "S0", ritual_id, principal_id}`.
- After each state extraction → `ReasoningCommit{state: "Sn", extraction_summary_hash, latency_ms, retry_count}`. The extraction is hashed (NOT stored verbatim — privacy per `specs/event-payload-classification.md` Rule 3 + § 3.6 here for shadow segment).
- S8 pause → `session_boundary_crossed{ritual_id, suspended_for: "shamir_ritual", suspension_record_hash}`.
- S8 resume → `session_boundary_crossed{ritual_id, resumed_from: "shamir_ritual"}`.
- S9 sign → `RoleEnvelopeCreated{envelope_id, principal_id, content_hash}` (delegated to envelope compiler per shard 4 § 5 row 4) + `posture_change{principal_id, from: "GENESIS_BARE", to: "PSEUDO", basis: "boundary_conversation_completed"}` (delegated to authorship score per shard 9 § 5).

### 5.4 With Authorship Score + Posture Gate (shard 9)

Per `09-authorship-score-implementation.md`, the initial PSEUDO posture is recorded at S9 completion as `posture_change{from: "GENESIS_BARE", to: "PSEUDO"}`. Boundary Conversation invokes `AuthorshipScore.record_initial_authorship(principal_id, envelope, novelty_metrics)` after the Envelope Compiler returns. The novelty metrics are accumulated by `NoveltyChecker` invocations at S3/S5 (per § 3.5).

The BET-12 measurement hook (`BET12TelemetryHook`) emits a single Ledger entry on `S10 complete` summarizing total duration + per-state breakdown. The EC-1 acceptance gate is `total_duration_seconds <= 25*60` for ≥3 distinct first-time-user sessions (per `02-mvp-objectives.md` EC-1).

### 5.5 With Shamir 3-of-5 Recovery (shard 15)

Per `15-shamir-recovery-implementation.md`, the S8 ritual is owned by `envoy.shamir.ShamirRitualCoordinator`. Boundary Conversation invokes `ShamirRitualCoordinator.run_first_time_ritual(*, threshold=3, total_shards=5)` at S8 entry; this yields the 5 BIP-39-word cards for printing/distribution. The conversation suspends with `Plan.suspension = SuspensionRecord(reason=ExplicitCancellationReason(reason="shamir_ritual_in_progress", cancelled_at=now))`. The user invokes `envoy boundary resume <ritual_id>` after physical card distribution; the resume flow checks `ShamirRitualCoordinator.is_complete(session_id)` AND verifies `shard_public_commitments` against the Trust Vault Genesis Record per `specs/shamir-recovery.md` § Shard public commitments. Incomplete → `ShamirRitualIncompleteError` (spec line 52) → forced back to S8.

### 5.6 With Connection Vault (shard 14) — minimal Phase 01 wiring

Per `14-connection-vault-implementation.md`, the Connection Vault wraps OS keychain for API credentials (channel adapter API keys, model adapter API keys). Boundary Conversation does NOT directly write to Connection Vault during the 15-minute first-run flow — channel adapter setup (which writes API keys) is a POST-EC-1 ritual. Phase 01 caveat: the conversation MAY surface a "channels to enable" prompt at S2 (people) or S5 (first-task) that triggers a downstream channel-adapter onboarding flow, but the API-credential write is downstream of the conversation, not within it. The integration is structural-namespace (the conversation knows about Connection Vault as a sibling primitive) but not wire-flow (no synchronous Connection Vault call inside the 15min budget).

### 5.7 With Model Adapter (shard 13)

Per `13-model-adapter-implementation.md` § 3.2 + § 5.1, Boundary Conversation generates conversational turns via `EnvoyModelRouter.for_primitive("boundary_conversation").chat_async(messages)`. This routes through the legacy `kaizen.providers.llm.<provider>.chat_async()` path (per shard 13 § 2.6 — `LlmClient.complete()` is deferred upstream per #740 spec-correction). Per-turn `model_invoke` Ledger entries carry the `ProviderRisk` annotation per `specs/model-adapter.md` § Provider-risk annotation.

The EC-1 acceptance gate depends on this adapter delivering reliable conversational quality — `ENVOY_BOUNDARY_MODEL` env override per shard 13 § 3.2 lets the user select a higher-capability model for this primitive specifically.

---

## 6. Tier 2 / Tier 3 test surface

Per `rules/orphan-detection.md` MUST Rule 1 (every facade has a production call site + Tier 2 wiring test in same PR) + MUST Rule 2 (Tier 2 imports through framework facade, not manager class) + `rules/facade-manager-detection.md` Rule 1 + Rule 2 (manager-shape classes have Tier 2 wiring test with predictable naming).

### 6.1 Tier 2 wiring tests (real Ollama LLM, real SQLite Trust Vault, real Ed25519, no mocking per `rules/testing.md` § Tier 2)

| Test file                                                                         | What it exercises                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/integration/test_boundary_conversation_runtime_wiring.py`                  | Per `rules/facade-manager-detection.md` Rule 2 naming convention: imports `from envoy.boundary_conversation.runtime import BoundaryConversationRuntime`, constructs against real-Ollama (Ollama at `localhost:11434`, no API key required per `13-model-adapter-implementation.md` § 6.3) + real SQLite Trust Vault + real Ed25519, calls `.start()` then `.advance()` for each S1-S9 in turn, asserts S10 completion produces a Trust Vault Genesis row + a parseable EnvelopeConfig at S9 sign. |
| `tests/integration/test_resume_from_each_state.py`                                | Per spec `Test location` line 70: `envoy init --resume` from S1..S9 each. For each state, run conversation up to that state, kill the process, re-construct `BoundaryConversationRuntime`, call `.resume(ritual_id)`, advance one more state, assert the rehydrated `accumulated_envelope_input` matches the pre-kill state.                                                                                                                                                                      |
| `tests/integration/test_boundary_conversation_pause_resume_shamir.py`             | At S8, conversation suspends with `Plan.suspension = SuspensionRecord(...)`; assert `Plan.to_dict()["suspension"]["reason"]["kind"] == "explicit_cancellation"`; assert `Plan.to_dict()["suspension"]["reason"]["reason"] == "shamir_ritual_in_progress"`; complete the ritual; resume; assert suspension cleared.                                                                                                                                                                                |
| `tests/integration/test_boundary_conversation_envelope_config_input_canonical.py` | Run conversation; assert assembled `EnvelopeConfigInput.financial.authored_constraints[]` is sorted lexicographically by `constraint_id` ascending; assert `EnvelopeCompiler.compile(input)` accepts without raising; assert resulting `EnvelopeConfig.canonical_bytes` is byte-stable across two runs of the same input.                                                                                                                                                                         |
| `tests/integration/test_boundary_conversation_per_state_ledger_entries.py`        | Per `rules/orphan-detection.md` Rule 1: assert each S1-S9 transition emits a `ReasoningCommit` Ledger entry; assert S10 emits a `posture_change` entry from GENESIS_BARE to PSEUDO; assert total Ledger entry count is ≥ 11 (1 per state + 1 sign + 1 posture).                                                                                                                                                                                                                                   |
| `tests/integration/test_boundary_conversation_bet12_latency_telemetry.py`         | Run conversation; assert `BET12TelemetryHook` emitted per-state latency entries; assert `total_duration_seconds <= 25*60` (the EC-1 acceptance gate boundary). Use a low-latency model preset (smallest local Ollama) to keep CI test time bounded.                                                                                                                                                                                                                                               |
| `tests/regression/test_t018_visible_secret_setup.py`                              | Per spec line 71 + threat T-018: visible secret rendered correctly post-S7; the rendered modal byte-binding to Trust Vault stored secret matches.                                                                                                                                                                                                                                                                                                                                                 |
| `tests/regression/test_t023_novelty_feedback_at_authoring.py`                     | Per spec line 72 + threat T-023: at S3 with a near-duplicate template-cached blocked-topic, raises `NoveltyFeedbackBlockError`; user re-prompts; second answer accepted.                                                                                                                                                                                                                                                                                                                          |
| `tests/integration/test_post_duress_banner.py`                                    | Per spec line 73: shadow_segment unread duress event surfaces banner; advance to S0 raises `DuressBannerUnacknowledgedError` until banner acknowledged.                                                                                                                                                                                                                                                                                                                                           |
| `tests/integration/test_boundary_conversation_resume_state_missing.py`            | Per spec line 49: `envoy init --resume <bogus_ritual_id>` raises `RitualResumeStateMissingError`; user disposition is "Restart from S0; OR Shamir-recover Trust Vault" — assert error message matches plain-language guidance per `rules/communication.md`.                                                                                                                                                                                                                                       |
| `tests/integration/test_boundary_conversation_pytest_xdist_safe.py`               | Per `rules/testing.md` § Env-Var Test Isolation: tests that mutate `ENVOY_BOUNDARY_MODEL` hold a module-scoped `threading.Lock`; verify under `pytest-xdist -n auto` no race-condition flakes.                                                                                                                                                                                                                                                                                                    |

Each test loads `.env` via root `conftest.py` per `rules/env-models.md`. Each test reads its model name from the env key — never hardcoded. Per `rules/orphan-detection.md` Rule 2a (crypto-pair round-trip THROUGH the facade): the conversation's S9 sign-step + Genesis-record-verify pair MUST be exercised end-to-end through `BoundaryConversationRuntime`, NOT through the upstream `Ed25519Signer` directly.

### 6.2 Tier 3 tests (full first-time-user-style sessions, EC-1 acceptance gate)

| Test file                                                        | What it exercises                                                                                                                                                                                                                                                                                                                                                                                          |
| ---------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/e2e/test_boundary_conversation_full_path.py`              | Per spec line 68: S0→S10 happy-path under ~15min budget against real Ollama. EC-1 partial: assert `total_duration_seconds <= 25*60`; assert S9 EnvelopeConfig is parseable; assert Genesis trust record signed.                                                                                                                                                                                            |
| `tests/e2e/test_boundary_conversation_minimum_path.py`           | Per spec line 69: 8-minute minimum-path (template + visible secret + Shamir, skip non-essential states); assert `total_duration_seconds <= 8*60 + 25%`.                                                                                                                                                                                                                                                    |
| `tests/e2e/test_boundary_conversation_n3_first_time_users.py`    | EC-1 acceptance gate per `02-mvp-objectives.md`. THREE distinct first-time-user-style sessions (different fixture personas; different envelope intentions); assert all 3 complete in ≤25 minutes; assert all 3 produce parseable EnvelopeConfigs; assert all 3 Genesis records sign cleanly. **This is THE EC-1 gate test.**                                                                               |
| `tests/e2e/test_boundary_conversation_pause_resume_all_three.py` | Pause-resume coverage: (a) close terminal mid-S5, resume, complete; (b) pause at S8 Shamir, complete physical ritual offline, resume, complete; (c) suspend at S7 (visible secret) IF ANY explicit-cancellation pause is wired in P01 — note: per § 3.3 above, S7 in P01 is Trust Vault write only (no Connection Vault sync mid-conversation), so this leg is `xfail` if no S7 suspension surface exists. |

### 6.3 Local-Ollama tier (no API key required) is the load-bearing CI tier

Per `13-model-adapter-implementation.md` § 6.3, the Ollama Tier 2 path is the ONLY one that runs unconditionally in CI without secret-key provisioning. For Boundary Conversation Tier 2 + Tier 3 tests, **Ollama is the chosen substrate** because:

1. EC-1 reproducibility — N=3 sessions need to run without per-session API spend in CI.
2. BYOM degraded-mode path — EC-1 must work for local-only users; the Tier 2 + Tier 3 suite IS the proof.
3. Cassette-recordability for cloud providers (per `13-model-adapter-implementation.md` § 6.2) is acceptable for Tier 3 cassette tests but NOT for the EC-1 N=3 acceptance gate; the gate requires real-time conversation flow against a live model.

### 6.4 Test-skip discipline

Per `rules/testing.md` § Test-Skip Triage Decision Tree:

- `pytest.mark.skipif(not OLLAMA_AVAILABLE)` is **ACCEPTABLE** per the rule's Tier-1 row — infra-conditional skip, reason names the constraint.
- Cloud-provider Tier 3 cassettes (Anthropic / OpenAI / DeepSeek) are recorded once via `vcrpy` and replayed; `pytest.mark.skipif(not <PROVIDER>_API_KEY)` for the recording session is acceptable.
- Any test with `pytest.mark.skip(reason="TODO")` or empty body is BLOCKED per the rule's BLOCKED row.

---

## 7. Frozen-spec ambiguity (escalation candidates)

Per `01-shard-plan.md` § 4: HIGH-severity gaps trigger "STOP the deep-dive; convene MUST-Rule-5b sweep before continuing; spec edit goes through full-sibling redteam economics." The shard surfaces ONE MED-candidate (HOLD, not escalate) and TWO LOWs (spec-acknowledged open questions).

### 7.1 MED candidate — 15-minute pacing target vs EC-1 25-minute acceptance gate vs first-time-user empirical reality

**Status:** MED candidate. Discussed below; recommendation is **HOLD**, not escalate.

**Observation:** `specs/boundary-conversation.md` § Duration (lines 29–31) names "~15min target. 8min minimum-path." `specs/boundary-conversation.md` § Open questions line 77 acknowledges: "15min target — empirical Phase 01 telemetry; if median exceeds 22min, simplify." The EC-1 acceptance gate (per `02-mvp-objectives.md`) is "≤25 minutes for first-time users with N=3" — derived as 15min target + 66% buffer.

The ambiguity: WHICH metric is load-bearing for Phase 01 ship? Three interpretations are possible:

- (a) **15min median across all sessions** — the spec's plain reading.
- (b) **25min ceiling per first-time-user session** — the EC-1 acceptance gate's plain reading.
- (c) **Both** — sessions that median 15min AND every individual session under 25min.

Phase 01 disposition: **(c) Both**, with EC-1 as the ship gate and 15min median as a Phase 02 telemetry-driven target. This is consistent with `specs/boundary-conversation.md` open question 1 (telemetry-informed Phase 01 → Phase 02 simplification) and with EC-1's pre-declared ≥3 sessions ≤25 minutes acceptance.

**Why not escalate:** the spec does NOT mandate 15min as a hard ceiling — it explicitly names empirical telemetry as the calibration mechanism, and EC-1 already pre-declares the 25min ship gate. Phase 01 implementation is unambiguous given EC-1 as the ship gate; the 15min target is a quality-of-life target informed by Phase 01 telemetry that informs Phase 02 simplification work.

**Disposition:** Note in `02-plans/02-test-strategy.md` (shard 20) that the Tier 3 telemetry test asserts the 25min ceiling per session; the 15min median is a release-summary observation, not a ship-blocking assertion. No spec edit; no MUST-Rule-5b sweep.

### 7.2 LOW — state-resume across machine boundary (open question 2)

`specs/boundary-conversation.md` § Open questions line 78: "State-resume across machine boundary (laptop ↔ phone) — Phase 02 multi-device pairing concern." This is the spec's own open question; Phase 01 ships single-device-only resume per `06-envoy-ledger-implementation.md` § 1.2 single-principal-single-device scope. No escalation.

### 7.3 LOW — S5 first-task corpus diversity (open question 3)

`specs/boundary-conversation.md` § Open questions line 79: "S5 first-task corpus diversity — should Foundation curate per-domain examples to seed authorship." This is the spec's own open question; Phase 01 ships with a small Foundation-bundled local-cache template set per `04-envelope-compiler-implementation.md` § 3.3 (Phase 01 ships local-template-resolver stub). No escalation.

---

## 8. Cross-references

### Frozen spec sources (DO NOT EDIT — `journal/0001` discipline)

- `specs/boundary-conversation.md` (lines 1–82) — primary spec
- `specs/envelope-model.md` § Schema (lines 14–84) — output contract
- `specs/envelope-model.md` § Field semantics for late-added fields — `cross_domain_rules_authored`, `tool_output_budget_bytes`, `semantic_checks.tool_output_classifier_ensemble`
- `specs/grant-moment.md` § State machine (line 76) — adjacent ritual; not wired in Phase 01 first-run flow
- `specs/shamir-recovery.md` § Algorithm (lines 13–15) + § Default threshold (lines 17–19) + § Recovery flow (lines 31–33) — S8 ritual contract
- `specs/trust-vault.md` — visible secret + ritual state storage (cross-reference)
- `specs/data-model.md` — shadow segment for duress (cross-reference)
- `specs/threat-model.md` — T-018, T-023 (cross-reference)
- `specs/authorship-score.md` — novelty + minimum-impact algorithms (cross-reference, consumed at S3/S5)
- `DECISIONS.md` § ADR-0006 — Model choice: BYOM at install, local default available

### Phase 00 inheritance

- `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` item 13 (BaseAgent A grade) — verified provider citation
- `workspaces/phase-00-alignment/01-analysis/03-primitive-reconciliation.md` row 13 — Boundary Conversation reconciliation
- `workspaces/phase-00-alignment/issues/manifest.md` — Phase 00 ISS manifest (#598 PlanSuspension; #735, #736 post-survey closures)

### Phase 01 sibling shards

- `workspaces/phase-01-mvp/01-analysis/01-shard-plan.md` § 2 (shard 8 placement) + § 4 (failure-mode protocol) + § 5 (sequencing — wave-C; depends on shards 4, 5, 6, 13, 14, 15)
- `workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md` § EC-1 (Boundary Conversation acceptance gate) + § EC-7 (8-channel onboarding)
- `workspaces/phase-01-mvp/01-analysis/03-kailash-py-mvp-readiness.md` § 3 row 5 (Boundary Conversation A/A) + § 5 verification protocol
- `workspaces/phase-01-mvp/01-analysis/04-envelope-compiler-implementation.md` § 4 + § 5 row 1 — `EnvelopeConfigInput` consumer contract
- `workspaces/phase-01-mvp/01-analysis/05-trust-store-implementation.md` — Trust Vault adapter (S7 visible secret, S9 Genesis seed, ritual-state persistence)
- `workspaces/phase-01-mvp/01-analysis/06-envoy-ledger-implementation.md` § 5.1 row 3 — Boundary Conversation ledger writes (`ReasoningCommit`, `session_boundary_crossed`)
- `workspaces/phase-01-mvp/01-analysis/09-authorship-score-implementation.md` — initial PSEUDO posture transition at S9
- `workspaces/phase-01-mvp/01-analysis/13-model-adapter-implementation.md` § 3.2 + § 5.1 + § 6.3 — `EnvoyModelRouter.for_primitive("boundary_conversation").chat_async()` substrate; Ollama Tier 2 + Tier 3 substrate
- `workspaces/phase-01-mvp/01-analysis/14-connection-vault-implementation.md` — Connection Vault NOT directly written during 15min flow (post-EC-1 channel adapter setup)
- `workspaces/phase-01-mvp/01-analysis/15-shamir-recovery-implementation.md` — `ShamirRitualCoordinator.run_first_time_ritual(*, threshold=3, total_shards=5)` invoked at S8
- `workspaces/phase-01-mvp/journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` — re-derivation discipline

### Verified upstream code (`~/repos/loom/kailash-py/`, 2026-05-03)

- `packages/kailash-kaizen/src/kaizen/core/base_agent.py` line 49 — `class BaseAgent(MCPMixin, A2AMixin, Node)`
- `packages/kailash-kaizen/src/kaizen/signatures/core.py` line 249 — `class Signature(metaclass=SignatureMeta)`; line 1015 — `class SignatureCompiler` (JSON-schema compiler for structured-output)
- `packages/kailash-kaizen/src/kaizen/l3/plan/types.py` line 178 — `class PlanState(str, Enum)`; line 218 — `class PlanNode`; line 303 — `class Plan` with `suspension: Any = None` at line 327
- `packages/kailash-kaizen/src/kaizen/l3/plan/suspension.py` (336 LOC) — 5 `*Reason` dataclasses (`HumanApprovalGateReason` line 69, `CircuitBreakerTrippedReason` line 81, `BudgetExceededReason` line 94, `EnvelopeViolationReason` line 110, `ExplicitCancellationReason` line 132); Union alias `SuspensionReason` line 147; `class SuspensionRecord` line 278 with `to_dict`/`from_dict` round-trip
- `packages/kailash-kaizen/src/kaizen/l3/plan/__init__.py` lines 21–22 + 72–73 — `SuspensionReason` + `SuspensionRecord` re-exported
- `packages/kailash-kaizen/src/kaizen/providers/llm/{ollama,anthropic,openai,deepseek}.py` — legacy chat substrate per `13-model-adapter-implementation.md` § 2.6 (load-bearing for `chat_async()` at each conversation turn)

### Closed upstream issues (verified 2026-05-03 via `gh issue view --json closedAt,state,title,body`)

- terrene-foundation/kailash-py #598 — `PlanSuspension` parity; closed 2026-04-25; landing point `kaizen.l3.plan.suspension` 5-variant `SuspensionReason` + `SuspensionRecord`
- terrene-foundation/kailash-py #735 — `_execute_strategy` ThreadPoolExecutor contextvars fix; closed 2026-04-30
- terrene-foundation/kailash-py #736 — `_calculate_usage_metrics` None prompt_tokens fix; closed 2026-04-30

### Rule citations

- `.claude/rules/communication.md` — plain-language framing for the 15min UX latency budget; "thinking..." indicator MUST NOT present empty silence
- `.claude/rules/agent-reasoning.md` — LLM does ALL reasoning (the per-state Signature is the structured-output extraction; no if-else routing on user intent)
- `.claude/rules/orphan-detection.md` MUST Rule 1 + Rule 2 + Rule 2a — every facade has a production call site + Tier 2 wiring test; manager-shape classes import through framework facade in tests
- `.claude/rules/facade-manager-detection.md` MUST Rule 1 + Rule 2 + Rule 3 — Tier 2 test naming `test_<lowercase_manager>_wiring.py`; explicit framework dependency in `__init__`
- `.claude/rules/zero-tolerance.md` Rule 4 — Phase 04 deferrals (adversarial classifier, multi-provider verification) are NOT workarounds because spec defers them; Rule 6 — implement fully (no stubbed S1-S9 states)
- `.claude/rules/testing.md` § Tier 2 + § Tier 3 + § Test-Skip Triage + § Env-Var Test Isolation
- `.claude/rules/specs-authority.md` MUST Rule 4 (read specs before acting; this shard reads three specs by path + section); MUST Rule 5b (no spec edits at this shard)
- `.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget — 6 invariants; ≤6 cross-primitive references; within budget at the upper edge by design (Boundary Conversation IS the most-integrated Phase 01 primitive)
- `.claude/rules/env-models.md` — `.env` is single source of truth for `ENVOY_BOUNDARY_MODEL` and per-provider API keys (Connection Vault for the latter)
- `.claude/rules/journal.md` — observed: this is an analysis doc, not a journal entry; if a CONNECTION/DISCOVERY surfaces during shard 8 it lives in `journal/`, not in this analysis doc
- `.claude/rules/independence.md` — Boundary Conversation is the BET-12 primary surface ("governance-primary-surface palatability") that distinguishes Foundation-stewarded Envoy from Little Snitch class

### Forward references

- shard 10 (Grant Moment) — composes with PlanSuspension `HumanApprovalGateReason`; subsequent envelope-edit conversations may surface Grant-Moment-like consent at S9 sign-step (Phase 02+)
- shard 16 (Channel adapters) — EC-7 acceptance gate (8 channels × N=3 = 24 successful onboardings); Boundary Conversation is the post-channel-entry primary flow
- shard 19 (pipx distribution) — `envoy init --resume <ritual_id>` CLI entry point; `envoy boundary resume <ritual_id>` for post-Shamir resume
- shard 20 (build sequence) — Boundary Conversation depends on wave-A (4, 5, 6, 13, 14, 17, 18) + wave-B (7, 9, 15) before integration tests can run; sequenced in wave-C

---

**Shard 8 closure:** This deep-dive identifies ~1180 LOC of Envoy-new-code (runtime facade + script DAG + 9 per-state Signatures + envelope assembler + resume coordinator + BET-12 telemetry hook) implementing the EC-1 acceptance gate (≥3 first-time-user sessions ≤25 minutes, parseable EnvelopeConfig). Phase 01 implementation depends on `kaizen.core.base_agent.BaseAgent` + `kaizen.signatures.core.Signature` + `kaizen.l3.plan.types.Plan` + `kaizen.l3.plan.suspension.SuspensionRecord` (all verified post-#598 closure 2026-04-25); legacy `kaizen.providers.llm.<provider>.chat_async()` for the conversation turn substrate (per shard 13). No upstream blockers. Conversation-script-as-DAG choice is structurally required by pause-resume + persistent-state semantics; structured-output Signature pattern is structurally required by parseable-EnvelopeConfig acceptance gate; mid-conversation pauses compose with `Plan.suspension = SuspensionRecord(reason=ExplicitCancellationReason(...))`; resumption is persistent in Trust Vault, not single-session ephemeral. One MED-candidate spec ambiguity HELD (15min target vs 25min EC-1 gate), two LOW spec-acknowledged open questions deferred. BETs falsified by EC-1 outcome: BET-1 (authorship — primary surface palatable enough for first-time users to author from scratch), BET-12 (governance-primary-surface — the §2.3 category-move thesis succeeds iff users complete the ritual at all).
