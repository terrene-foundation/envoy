# Envoy — Concept One-Pager for Foundation Board Review

**Status:** DRAFT for Terrene Foundation board endorsement (Phase-00 exit gate item).
**Audience:** Terrene Foundation board.
**Decision asked:** Endorse Envoy as a Foundation project, including the runtime-pluggability model that ships a Terrene-hosted closed-source-binary runtime as the default with a fully open-source runtime as a one-flag opt-in.
**Working title:** Envoy. (Final mark pending USPTO/EUIPO/UK IPO sweep — ADR-0002.)

---

## What Envoy is

> **Autonomous AI where you set the boundaries.**

A consumer agent product whose primary surface is **the envelope** — the user's declared boundaries on what an agent may do, refuse, escalate, or pause. Every agent action is backed by a cryptographically signed Delegation Record rooted in a named human's Genesis Record. No grant, no action.

Envoy answers the question "**what is the human for** in a world of autonomous AI?" with the answer "setting the boundaries" — and then makes that the product, not a settings page.

## Why this is a Foundation project, not a commercial product

| Property                             | Envoy                                                                                |
| ------------------------------------ | ------------------------------------------------------------------------------------ |
| Source                               | Apache 2.0, Foundation-owned                                                         |
| Specifications consumed              | CARE / EATP / CO / PACT (CC BY 4.0, Foundation-owned)                                |
| User cost                            | Zero — no payment, no registration, no commercial ToS, no gating                     |
| Open-source runtime always available | Yes — `kailash-py` (Apache 2.0 code; references CC BY 4.0 specs), one-flag opt-in    |
| Forkable                             | Yes — Envoy itself, the spec family, and the open runtime                            |
| Commercial-vendor dependency         | None — if the Rust runtime were ever unavailable, the open runtime continues to work |

Envoy is the Foundation's flagship implementation of CARE / EATP / CO / PACT for end-user agents. It demonstrates that the spec family, methodology, and primitive surface are sufficient to ship a real product, end-to-end, without commercial coupling.

## What we are asking the Board to endorse

**One decision:** the runtime-pluggability model in `DECISIONS.md §ADR-0009`.

| Layer                               | License                                       | Open-source                            | Free to user |
| ----------------------------------- | --------------------------------------------- | -------------------------------------- | ------------ |
| Envoy application                   | Apache 2.0                                    | Yes                                    | Yes          |
| `kailash-runtime` interface         | Apache 2.0                                    | Yes                                    | Yes          |
| CARE/EATP/CO/PACT specs             | CC BY 4.0                                     | Yes                                    | Yes          |
| `kailash-rs-bindings` Python glue   | Apache 2.0                                    | Yes                                    | Yes          |
| `kailash-rs-bindings` compiled core | Freely-redistributable binary; source closed  | Source: no; binary: freely distributed | Yes          |
| `kailash-py` (alternative runtime)  | Apache 2.0 (code; references CC BY 4.0 specs) | Yes                                    | Yes          |

**The structural compromise:** envoy ships fast (Rust default) AND fully open (Python alternative, one-flag swap). Nobody is locked out of a free, open path; performance-first users get a Terrene-hosted compiled binary at no cost, no registration, no terms.

**Precedent patterns the board should weigh:**

- PyTorch ships with CUDA-compiled binaries from NVIDIA (closed source) as the default backend; pure-CPU OSS path is the alternative. Many open-source projects in scientific computing already depend on this pattern transitively.
- Linux kernel distributions ship freely-redistributable firmware blobs alongside the GPL kernel. The blobs are closed-source; the kernel is not.
- Mozilla Firefox ships Widevine (closed-source DRM) for streaming media as an opt-in. Firefox itself is fully open.

In all three precedents, the open-source project endorses a closed-binary dependency where (a) the binary is freely redistributable, (b) an open-source alternative exists for users who want pure-OSS, (c) the open-source project itself remains fully open and forkable. Envoy proposes the same structure.

## What's at stake if the Board declines

- **Default to Python-only runtime.** Envoy ships, but with measurably slower hot-path performance on every grant-check, envelope-intersect, and ledger-append. Per `acceptance-metrics.md`, hot-path P50 latency targets are <10ms (Rust) vs <80ms (Python) — an 8× spread. Whether the gap is user-perceptible at scale is part of Phase-03 measurement.
- **No structural blocker.** Envoy can ship under either decision. The Board's call is which performance/openness posture is the public default.

## Phase-00 status (this is the readiness check)

Phase 00 alignment work is substantively complete on the spec/contract side:

- ✅ **Specs** — 37 frozen-v1 domain specs covering envelope, trust lineage, ledger, runtime abstraction, all five rituals (Boundary Conversation, Grant Moment, Daily Digest, Weekly Posture Review, Monthly Trust Report), 23 channel adapters, model adapters, distribution, foundation-ops. Converged after 6 redteam rounds with 0 CRIT + 0 HIGH × 2 consecutive (2026-04-29).
- ✅ **GH issues filed** — 39 issues across kailash-rs (19), kailash-py (12), mint (8) tracking primitive gaps and binding parity that envoy depends on.
- ✅ **Architecture decisions captured** — 9 ADRs in `DECISIONS.md`.
- ✅ **Roadmap published** — Phases 00 through 05 with exit criteria.
- ✅ **Composite licensing approach** — designed; legal-counsel drafts in `02-plans/legal/`.

External items still in flight:

- 🔲 **Trademark sweep** — USPTO + EUIPO + UK IPO Class 9/42 (in progress with counsel).
- 🔲 **Composite LICENSE legal-counsel review** — drafted, pending counsel approval (this board ask is upstream of that — counsel adopts whatever the board endorses).
- 🔲 **Export-control assessment** — Rust binary redistribution + crypto primitives (Ed25519 / SHA-256 / Shamir).
- 🔲 **Foundation charter compatibility statement** — the deliverable this board ask produces if endorsed.

## What we'd publish if endorsed

1. A board minute recording the endorsement of the runtime-pluggability model (paragraph form, citing ADR-0009).
2. A `CHARTER.md` paragraph in this repo making the endorsement public-readable.
3. A FAQ entry under `docs/foundation/runtime-pluggability.md` answering the predictable questions: "Why isn't the Rust binary open-source?", "Will the open Python runtime always work?", "Who controls the binary distribution channel?", "What happens to the binary path if the Foundation can no longer host it?"

## What the endorsement is NOT

- Not an endorsement of any specific commercial entity. The Foundation is independent (Singapore CLG, anti-capture provisions in constitution). No commercial entity has special status.
- Not an endorsement of trademark "Envoy" — that is independent legal-counsel work tracked under ADR-0002.
- Not an endorsement of the Rust binary's source-closed status as a permanent architecture. ADR-0013 (placeholder) anticipates a charter amendment if the runtime-pluggability model proves insufficient.
- Not a constraint on any commercial implementation of the same specs. Anyone may implement CARE/EATP/CO/PACT in any language under any license. Envoy is the Foundation's reference implementation.

## Recommended decision text for the board minute

> The Board endorses the runtime-pluggability model described in
> Envoy `DECISIONS.md §ADR-0009`, dated 2026-04-21, including the
> distribution of `kailash-rs-bindings` as a freely-redistributable
> compiled binary by default, alongside the always-available
> fully-open-source `kailash-py` runtime as a one-flag opt-in. The
> Board confirms this composite arrangement is consistent with the
> Foundation's charter and the anti-capture provisions of its
> constitution, on the basis that (a) every user path is free of
> charge with no registration, (b) a fully-open-source runtime is
> always available, (c) Envoy's own source remains Apache 2.0 and
> forkable, (d) no commercial entity holds a structural advantage
> in either the binary distribution channel or the spec family.

## Appendix — what users see

First launch:

```
$ envoy init

Welcome to Envoy. Two runtime options:

  [1] Fast (default) — Rust binary from Terrene Foundation.
      Free, no registration, freely redistributable.
      ~10x faster on the hot path. Source closed.

  [2] Open — Pure Python from Terrene Foundation.
      Free, fully open-source, fully forkable.
      Apache 2.0 (code; references CC BY 4.0 specs).

  Choose [1/2/?] >
```

A user pressing `?` sees a one-screen explanation of the difference and a link to the FAQ. A user pressing `2` gets envoy with `kailash-py` and never touches the binary. A user pressing `1` gets the binary and can switch later with `envoy runtime swap`.

---

**Action requested from the Board:** endorse, decline, or request specific revisions.

**Drafted:** 2026-05-01 by envoy Phase-00 work.
**Review owner:** Terrene Foundation Secretary (to circulate with the meeting agenda).
**Cross-references:** `DECISIONS.md §ADR-0009`, `CHARTER.md §Openness Posture`, `ROADMAP.md §Phase 00`, `workspaces/phase-00-alignment/02-plans/legal/01-kailash-rs-bindings-LICENSE-draft.md`, `workspaces/phase-00-alignment/02-plans/legal/02-kailash-rs-bindings-SPDX-draft.md`.
