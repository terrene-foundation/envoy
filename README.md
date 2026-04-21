# Envoy

> Autonomous AI where you set the boundaries.

**Status:** pre-MVP concept (Phase 00 alignment). Working codename; trademark sweep pending.
**Steward:** Terrene Foundation (Singapore CLG).
**Methodology:** CARE / EATP / CO / COC (CC BY 4.0). Envoy code: Apache 2.0 (planned).

## What is the human for?

In a world of autonomous AI: **setting the boundaries.** Research, drafting, scheduling, coding, summarising — agents can do these quickly and at scale. The irreducible human contribution is the judgement about what the agent should not do, what it should pause for, what it should decline, and what it should escalate. Envoy makes that judgement the primary surface of the product.

An *envoy* is an agent that carries delegated authority from a sovereign. In Envoy's architecture this is literally true — every action is backed by a cryptographically signed EATP Delegation Record rooted in a named human's Genesis Record. No grant, no action.

## What Envoy offers

| Capability | How Envoy delivers it |
|---|---|
| **Trust model** | PACT envelopes + EATP Trust Lineage + cascade revocation built into the core distribution |
| **Audit trail** | Hash-chained Envoy Ledger; every grant, action, and refusal signed; one-tap revocation |
| **Tool policy** | Default-deny; capabilities granted through signed Grant Moments; frozen envelopes |
| **First-launch UX** | Boundary Conversation — a 15-minute guided setup that teaches Envoy your limits |
| **Runtime** | Pluggable — `kailash-rs-bindings` (Rust-accelerated, free) or `kailash-py` (pure Python, Apache 2.0 + CC BY 4.0). First-run picker. |
| **Sovereignty** | Self-hosted, multi-principal, Shamir 3-of-5 recoverable |
| **Governance** | Primary product surface, not an add-on |
| **Cost to user** | Free forever — every path ($0 code, $0 infra, $0 runtime, $0 methodology) |
| **Forkability** | Apache 2.0 Envoy code + fully-FOSS `kailash-py` runtime always available |
| **Skill ecosystem** | Full OpenClaw `SKILL.md` compatibility with a generated `ENVELOPE.md` companion — skills you already have keep working |

## Runtime — two free paths, your choice

At first run, Envoy asks one question:

> "Run Envoy with Rust acceleration (free, faster, via a compiled binary distributed through Terrene's open GitHub) or with the pure-Python Foundation runtime (free, fully open-source, forkable, somewhat slower)?"

Both are $0. Both are hosted openly. Neither requires registration, payment, or a commercial ToS. See [DECISIONS §ADR-0001](DECISIONS.md) for the full architecture and [§ADR-0009](DECISIONS.md) for licensing posture.

## The three pillars

1. **Responsibility and safety, together.** The user holds responsibility through Grant Moments; the runtime guarantees safety through frozen envelopes, cascade revocation, and default-deny tool policy.
2. **Governance as the source of performance.** Pre-compiled envelope checks become O(1) hot-path lookups. Typed plan DAGs parallelise safely because every branch is envelope-verified at compile time. Declared envelopes mean no mid-stream permission prompts. Rust hot path by default. Governance *is* the source of speed.
3. **Features, first-class and seamless.** 23+ channels, `SKILL.md` compatibility, local-first model option, one-command install, mobile-first onboarding, Shamir recovery.

## The new habit

Using autonomous AI becomes a daily, ritualised relationship.

- **Morning (2 min):** Daily Digest — what Envoy did, declined, spent.
- **Throughout:** Grant Moments — signed consent events for new capabilities.
- **Sunday 90 sec:** Weekly Posture Review — adjust trust sliders.
- **Monthly 5 min:** Trust Report — shareable one-pager of delegation graph + budget.

Trust postures ratchet up over time (PSEUDO → TOOL → SUPERVISED → DELEGATING → AUTONOMOUS). Envelopes deepen. The user develops an extension of themselves with structural integrity by design.

## Where we are

Pre-Phase-01. Working concept approved 2026-04-21. See [`CHARTER.md`](CHARTER.md), [`DECISIONS.md`](DECISIONS.md), [`ROADMAP.md`](ROADMAP.md).

## Next

1. Phase 00 alignment items — trademark sweep, legal-counsel engagement on runtime licensing, namespace reservation, Foundation sign-off.
2. `/analyze` for Phase 01 MVP scope.

## License

Apache 2.0 for Envoy code (planned). Content and methodology: CC BY 4.0, Terrene Foundation. Runtime bindings: see DECISIONS §ADR-0009 for the full license posture.

## Contact

Foundation: Terrene Foundation, Singapore CLG.
Session owner: jack@terrene.foundation.
