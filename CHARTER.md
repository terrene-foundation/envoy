# Envoy — Charter

**Tagline:** Autonomous AI where you set the boundaries.

**Steward:** Terrene Foundation (Singapore CLG), under the CARE / EATP / CO / COC methodology family (CC BY 4.0). Envoy source code: Apache 2.0.

**Working codename:** Envoy. *(Trademark sweep required — see DECISIONS §ADR-0002.)*

## The Question Envoy Answers

> **What is the human for** in a world of autonomous AI?
> **Answer:** Setting the boundaries.

Research, drafting, scheduling, coding, communicating, summarising — agents can perform these quickly and at scale. The irreducible human contribution is **judgement about what the agent should not do, what it should pause for, what it should decline, and what it should escalate**. Envoy makes that judgement — the envelope, the delegation, the posture — the **primary surface** of the product.

An **envoy** is an agent that carries delegated authority from a sovereign. In our architecture this is literally true: every action the agent takes is backed by a cryptographically signed Delegation Record rooted in a named human's Genesis Record. No grant, no action.

## Openness Posture

Envoy's openness posture across every layer users interact with:

| Layer | License | Cost to user |
|---|---|---|
| Envoy application code | Apache 2.0 (Foundation-owned) | Free |
| `kailash-runtime` abstraction | Apache 2.0 (Foundation-owned) | Free |
| CARE / EATP / CO / PACT specifications | CC BY 4.0 (Foundation-owned) | Free |
| `kailash-rs-bindings` (Rust-accelerated runtime) | Open-source Python glue; freely-redistributable compiled binary; Terrene-hosted | Free |
| `kailash-py` (pure-Python runtime) | Apache 2.0 + CC BY 4.0, fully forkable | Free |

**Nothing in Envoy's distribution requires payment, registration, commercial license acceptance, or a hosted service.** No third-party proprietary component is required for any Envoy capability. A fully-open-source runtime (`kailash-py`) is always available as a one-flag install. See DECISIONS §ADR-0001 and §ADR-0009.

**Envoy runtime is pluggable.** Two free implementations:

1. **`kailash-rs-bindings`** — Rust-accelerated. Python glue is open-source; the compiled binary is freely redistributable; hosted on Terrene Foundation's open GitHub org; installed from PyPI; zero cost, no gating. **Default** (performance-first).
2. **`kailash-py`** — Pure Python, Apache 2.0 + CC BY 4.0, fully forkable. **Opt-in** (purity-first).

First-run picker offers the choice. Default is fast; opt-out is one keystroke.

## Three Product Pillars

**1. Responsibility and safety, together.** Responsibility is the user's — expressed through Grant Moments. Safety is the runtime's — delivered through PACT envelopes, EATP Trust Lineage, Kaizen governed agents, and cascade revocation. Every action is hash-chained to a named human. One-tap revoke on anything, anywhere, forever.

**2. Governance as the source of performance.** Pre-compiled envelope checks are O(1) hot-path lookups. Typed Kaizen L3 Plan DAGs parallelise safely because every branch is envelope-verified at compile time. No mid-stream permission prompts — the envelope is declared up front through the Boundary Conversation. Rust hot path by default (with pure-Python fallback). **Governance is the source of speed, not the tax.**

**3. Features, first-class and seamless.** 23+ channels (iMessage, Telegram, Slack, Discord, WhatsApp, Signal, Matrix, Feishu, Apple Shortcuts, Calendar, RCS, browser extension, IDE extensions, AR/VR, and more). Full OpenClaw `SKILL.md` compatibility with a CO-compliant `ENVELOPE.md` companion — users' existing skill libraries carry across. Model choice at install (local + cloud). Single static binary distribution. Trust Vault with Shamir 3-of-5 recovery. Mobile onboarding first-class.

## Extended USPs

**Ease of install.** `curl -sSf https://get.envoy.ai | sh` drops a single static binary. `brew install envoy-agent`. `winget install envoy-agent`. `cargo install envoy-agent`. Zero-config first launch. Runtime picker on first run.

**"What is the human for" = setting boundaries.** First launch IS a 15-minute Boundary Conversation — not a settings page. Boundary Library of community-shared envelope templates. Weekly Posture Review as a 90-second Sunday ritual. Monthly Trust Report as a shareable one-pager.

**The Envoy Ledger.** Every grant, action, refusal, and delegation is a signed entry in the user's personal hash-chained ledger, rooted in EATP Trust Lineage. Grep-able, diff-able, git-committable, cascade-revocable, shareable as cryptographic receipts.

**Foundation-stewardship + CC BY 4.0 methodology.** Terrene Foundation (Singapore CLG), non-commercial, independent. Envoy's specification family is forkable. Legal and Procurement can evaluate it on open, documented terms.

**Python + Rust byte-identical parity via conformance vectors.** BP-series cross-SDK commits land invariants in both runtime implementations with byte-identical semantics. Envoy's runtime abstraction contract is enforced by conformance test vectors at every release gate. Users swapping between `kailash-rs-bindings` and `kailash-py` get the same behaviour, only different performance.

**Structural no-orphan guarantee.** The build fails if a governance primitive lacks a call site (`rules/orphan-detection.md` + `rules/facade-manager-detection.md`). Every primitive Envoy ships is wired into a hot path and exercised by tests.

## The New Habit

Using autonomous AI becomes a daily, ritualised relationship. Not a tool.

- **Morning (2 min):** Daily Digest — what did Envoy do, decline, spend; approve pending Grant Moments.
- **Throughout:** Grant Moments — signed consent events for any new capability request.
- **Sunday 90 sec:** Posture Review — trust slider adjustments, envelope tweaks.
- **Monthly 5 min:** Trust Report — shareable one-pager.

Trust postures ratchet up over time (PSEUDO → TOOL → SUPERVISED → DELEGATING → AUTONOMOUS). Envelopes deepen. The user develops an extension of themselves with structural integrity by design.

## Non-Goals

- **Not an enterprise-first product.** Prosumer-first, enterprise-obvious-upgrade. Slack/Figma/Notion playbook.
- **Not a commercial SaaS with a subscription.** Foundation-stewarded open-source. Commercial Envoy offerings may emerge as third-party managed services; Foundation will not operate a hosted consumer product.
- **Not a chat UI.** The channels are the UI. No new app to learn.
- **Not a workflow canvas.** Kaizen handles plan DAGs; users declare intent, not steps.
- **Not a model.** Envoy is model-neutral; ships with local default + BYOM support.

## Positioning Sentence

> Envoy is autonomous AI where you set the boundaries. Every action traces to a grant you signed. Every tool runs within a limit you set. Every agent obeys an envelope you own.

## Spec Family References

Envoy is built on the Terrene Foundation specification family:

- **CARE** — Constraint-Aware Reasoning Envelope (governance philosophy)
- **PACT** — Permission And Constraint Tuple (envelope primitive)
- **EATP** — Enterprise Agent Trust Protocol (trust lineage, delegation records, audit)
- **Kaizen** — Agent framework (signatures, delegates, governed reasoning)

All specifications are published under CC BY 4.0 by the Terrene Foundation (`terrene.foundation`).
