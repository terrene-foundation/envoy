# Phase 02 — Todos Index

**Document role:** Lean manifest for every Phase-02 todo. `/implement` reads this first, then the milestone file for the current todo, then the per-todo section. Per `rules/specs-authority.md` MUST Rule 1: this is a manifest; the work lives in the linked files.

**Date:** 2026-06-08 (`/todos` opening, after `/analyze` convergence — `journal/0006`).
**Status:** IN IMPLEMENT — `/todos` gate cleared 2026-06-08 (`journal/0008`). **Wave 1 COMPLETE** (2026-06-09, `journal/0010`): S1 (WS-1 conformance harness) ✅ · S4s (WS-6 store substrate) ✅ · S8 (WS-4 steward quorum + FV registry) ✅. **Wave 2 batch-1 COMPLETE** (2026-06-09, `journal/0011`, PR #88 merged): S2a (rs-bindings adapter) ✅ · S4r (store-poll rendezvous) ✅ · S10 (WS-5 OHTTP key-config server + relay) ✅ — reviewer + security-reviewer both APPROVE (one HIGH H1 found+fixed in-session: cross-process grant resolution now Ed25519-authenticated, fail-closed); full suite 1864 passed, coverage 91.24%, mypy+pyright clean. **Wave 2 batch-2 COMPLETE** (2026-06-10, `feat/wave2-batch2`): S8e (EDR schema + 6-step verifier + dual-sign gate) ✅ · S9a (SKILL translator + CO validator 1-4,6 — 100/100 benign accept, 3/3 adversarial reject incl. AST-visible dynamic dispatch) ✅ · S4i (`envoy init` — 8th of 10 CLI commands; write-once genesis + trust-anchor.json) ✅ — full suite 2035 passed, mypy+pyright clean. **Next: Wave 2 batch-3** — the M1 conformance families S2b/S2c/S3a/S3b (unblocked by S2a ✅) and the WS-6 serial chain (S4g-1 → S5b → S5o → S6\* → S6c). S7v (Rust verifier, isolatable) unblocks once S3b lands. S9b stays substrate-gated on S6a.
**Source authority:**

- `briefs/00-phase-02-scope.md` — what Phase-02 must ship (6 workstreams + 10 exit criteria).
- `02-plans/01-architecture.md` — dependency graph + legal-gate-aware build sequence + the 31-shard map (THIS index expands those shards into todos).
- `journal/0001`–`0006` — brief corrections + 5 red-team rounds + convergence verdict.
- `ROADMAP.md:74-108` — Phase-02 scope + exit criteria.

---

## Capacity discipline

Per `rules/autonomous-execution.md` § Per-Session Capacity Budget, every todo MUST stay within: ≤500 LOC load-bearing logic, ≤5–10 simultaneous invariants, ≤3–4 call-graph hops, describable in 3 sentences. Each todo carries a `## Capacity check`. The 31-shard map was sized at `/analyze` against this budget (5 red-team rounds); `/todos` confirms and adds build/wire + spec-ref + value-anchor + acceptance per shard.

## Build vs Wire discipline

Per the `/todos` contract, every component that consumes/produces data carries a **Build** todo (structure + logic) AND a **Wire** todo (connect to real sources, zero mock data). The shards already separate most of these (e.g. S2a adapter _wiring_, S4g-1 `grant` _wiring_ to the store); where a shard bundles build+wire, the todo's acceptance criteria list both gates explicitly.

**Global wire-gate (binding on every Wire / Build+Wire todo, whether or not its per-shard text restates it):** the Wire half is complete only when `grep -rn 'MOCK_\|FAKE_\|DUMMY_\|in-memory dict\|placeholder\|Phase02SubstrateNotWiredError' <shard-module>` returns zero hits in non-test code AND every method returns data from the real source (`rules/zero-tolerance.md` Rule 2). "Stops raising `Phase02SubstrateNotWiredError`" is necessary but NOT sufficient — a method can stop raising while returning a hardcoded placeholder; the grep gate closes that.

**Mechanical-sweep backing (per `rules/agents.md` § Reviewer Prompts Include Mechanical AST/Grep Sweep):** wherever a todo's acceptance relies on a reviewer/LLM-judgment sweep (e.g. "no semantic probe fires on N4 rendered text in Phase-02"), it MUST be backed by a mechanical gate — for the N4 case, `grep -rn 'probe\|llm_judge\|semantic_scor' tests/conformance/` returns zero hits in any `n4`/`N4` test path. The reviewer sweep is the semantic backstop, not the sole gate.

---

## Value-ranking (per `rules/value-prioritization.md` MUST-1 — ordered by user value, anchored)

Milestones are ordered by user value with the build sequence's legal-gate awareness. Track A (buildable now) front-loads; Track B (WS-2 release) is the legal tail.

| #      | Milestone                                   | Value                         | Primary anchor (user-anchored source)                                                                                                                                                                                                                                                                | Shards                                                             |
| ------ | ------------------------------------------- | ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| **M1** | WS-1 Runtime pluggability                   | **HIGH**                      | `briefs/00-phase-02-scope.md` §WS-1 + `ROADMAP.md:76-80` ("Runtime pluggability — ADR-0001+0009 delivery"). Headline phase capability AND critical path (gates WS-3 + verifier) AND the BET-6 byte-identity correctness core (hardest invariant).                                                    | S1, S2a, S2b, S2c, S3a, S3b, S3p, S3t                              |
| **M2** | WS-6 Durable substrate                      | **HIGH**                      | `briefs/...` §WS-6 + `workspaces/phase-01-mvp/journal/0048` (forest F5.2) + `mvp-build-sequence.md:209`. Unblocks `init`/`chat`/`grant` — the last 3 of 10 CLI commands (visible product completion) — AND the mandatory Rust verifier (resolves Phase-01 forest F2/F4). The long pole; start early. | S4s, S4r, S4i, S4g-1, S4g-2, S5b, S5o, S5o-enc, S6a, S6b, S6c, S7v |
| **M3** | WS-4 Envelope Library + SKILL ingest        | **HIGH**                      | `ROADMAP.md:96-98` + `briefs/...` §WS-4. Envelope Library FV tier live + SKILL.md→envelope translator (EC-02.7, a headline deliverable). Independent → parallelizable with M1/M2.                                                                                                                    | S8, S8e, S9a, S9b                                                  |
| **M4** | WS-5 Foundation Health Heartbeat            | **MED-HIGH**                  | `briefs/...` §WS-5 + `mvp-build-sequence.md:75-84`. The single largest de-scoped Phase-01 item; EC-02.8. Independent.                                                                                                                                                                                | S10, S11, S12                                                      |
| **M5** | WS-3 Mobile + 3 deferred channels           | **MED-HIGH**                  | `ROADMAP.md:92-94` + `briefs/...` §WS-3. Full 6 channels + Flutter mobile (EC-02.5, EC-02.6). Depends on WS-1.                                                                                                                                                                                       | S13a, S13b, S14 (S13 split at /todos)                              |
| **M6** | WS-2 Distribution (Track B — release-gated) | **HIGH value, release-gated** | `ROADMAP.md:74` (headline "single static binary") + `briefs/...` §WS-2. EC-02.1/2/9/10. Buildable now under codename; public _release_ waits on the open legal gates.                                                                                                                                | S15, S15m, S16, S17                                                |

**Trade-off named (MUST-1):** WS-2's "single binary" is arguably the highest-value _headline_ deliverable, but its release is legally gated, so start-order front-loads WS-1/WS-6 (buildable + unblocking) and builds WS-2 in parallel for a release tail. This is the legal-gate-aware sequencing from `02-plans/01-architecture.md` § Build Sequence — value preserved, not deferred.

---

## Milestone files

| File                                | Milestone     | Todos                                              |
| ----------------------------------- | ------------- | -------------------------------------------------- |
| `01-m1-ws1-runtime-pluggability.md` | M1            | S1, S2a–c, S3a/b/p/t (8)                           |
| `02-m2-ws6-durable-substrate.md`    | M2            | S4s/r/i/g-1/g-2, S5b/o, S5o-enc, S6a/b/c, S7v (12) |
| `03-m3-ws4-library-skill-ingest.md` | M3            | S8, S8e, S9a, S9b (4)                              |
| `04-m4-ws5-heartbeat.md`            | M4            | S10, S11, S12 (3)                                  |
| `05-m5-ws3-mobile-channels.md`      | M5            | S13a, S13b, S14 (3 — S13 split)                    |
| `06-m6-ws2-distribution.md`         | M6            | S15, S15m, S16, S17 (4)                            |
| `07-tests-and-acceptance.md`        | cross-cutting | Per-EC acceptance batteries + 3-tier test todos    |

**33 implementation shards** (S13→S13a/S13b and S4g→S4g-1/S4g-2 split at `/todos`) **+ 14 cross-cutting test/acceptance todos = 47 todos.** Dependency waves + critical path (depth-4, 6–9 sessions) per `02-plans/01-architecture.md`.

---

## Dependency waves (from the architecture DAG)

- **Wave 1 (roots, dependency-free):** S1 (WS-1), S4s (WS-6), S8 (WS-4), S10 (WS-5).
- **Wave 2+:** expand per each shard's `Depends` column. WS-6 is SAME-class serialized (most shards touch `runtime.py`/the store) — cannot worktree-parallelize within itself.
- **Critical path:** S1 → S2a → S3b → S7v (depth-4).
- **Queued follow-up (owned, value-anchored):** **S5o-enc** — encrypt the Region-1/Region-2 payload columns with vault-derived key material; lands WITH S5o (depends on S5o + the vault-unlock key lifecycle). Closes the session-store encryption-at-rest residual recorded in `specs/threat-model.md` § Residual risks (the shipped store is signed-not-encrypted-at-rest). Full spec in `02-m2-ws6-durable-substrate.md` § S5o-enc.

## Flagged `/todos` open questions (decide before/at `/implement`)

1. N4 rendered-text semantic-equivalence **scoring metric** (`runtime-abstraction.md:239`) — placement is settled Phase-03.
2. SPAKE2 vs Noise-XX for QR pairing (couples S13 FFI + S1 AKE vectors — decide early).
3. PyO3 compile-time vs uv-managed embedding (recommended PyO3; size-validate at S15).
4. Store-poll interval/backoff numeric value (S4r).
5. ADR-0006 degraded-mode runtime scope (S17 — app-logic, not just bundling).
