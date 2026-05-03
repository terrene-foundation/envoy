# Envoy — Architectural Decision Records

## ADR-0001 — Runtime architecture: pluggable, kailash-rs-bindings default, kailash-py fallback

**Date:** 2026-04-21 (revised from initial entry)
**Status:** Accepted

### Context

Kailash has two implementations of the same CARE / EATP / CO / PACT specs:

- **kailash-rs** — Rust workspace monorepo. Core crates (eatp, kailash-core, kailash-dataflow, kailash-governance, kailash-kaizen, kailash-mcp, kailash-ml, kailash-auth, kailash-marketplace, kailash-enterprise, kailash-capi, kailash-cli) ship as a compiled artifact (Rust source held as trade secret, not on crates.io). The `bindings/` subtree (`kailash-python`, `kailash-node`, `kailash-rails`, `kailash-ruby`, `kailash-wasm`) is published openly; the Python binding ships on PyPI, hosted on Terrene Foundation's open GitHub org. **Free to use, zero cost, no gating, no registration.**
- **kailash-py** — Terrene Foundation's **fully open-source Python implementation** of the same specs. Apache 2.0 code + CC BY 4.0 methodology. Fully forkable.

Envoy is a Foundation-stewarded product. Its USPs depend on:

- Performant Rust hot path (sovereignty + single-binary + speed-through-governance).
- Absolute openness (nothing forced on any user; no gating; fully open-source alternative always available).

Envoy's openness posture is therefore simple: application code is Apache 2.0, methodology is CC BY 4.0, a fully-open-source runtime is always available, and no proprietary hosted service is required.

### Decision

**Envoy programs against an abstract `kailash-runtime` interface. Two shipped implementations:**

```
┌──────────────────────────────────────────────────────┐
│ Envoy                                                │  ← Apache 2.0, Foundation
│   application, channel adapters, UI, ledger,         │     100% open-source
│   Boundary Conversation, Grant Moments, Digest       │
│                     │                                │
│                     ▼                                │
│   kailash-runtime (abstract interface)               │  ← Apache 2.0, Foundation
│                     │                                │
│   ┌─────────────────┴─────────────────┐              │
│   ▼                                   ▼              │
│ kailash-rs-bindings (PyPI)       kailash-py (PyPI)  │
│ Python glue = open-source        Pure Python         │
│ Compiled .so = closed source     Apache 2.0 + CC BY  │
│ Hosted on Terrene open GitHub    Fully forkable      │
│ Zero cost, free to all           Zero cost, free     │
│                                                      │
│ DEFAULT (performance)            OPT-IN (purity)     │
└──────────────────────────────────────────────────────┘
```

**First-run picker asks one question:** _"Run Envoy with Rust acceleration (free, faster, via a compiled binary from PyPI), or with the pure-Python Foundation runtime (free, fully open-source, forkable, somewhat slower)?"_ Default is Rust-accelerated. Opt-out is one keystroke.

**What each shipped package contains:**

| Package                                            | Source                             | Binary                                                | License                                                     | Cost |
| -------------------------------------------------- | ---------------------------------- | ----------------------------------------------------- | ----------------------------------------------------------- | ---- |
| `envoy` (Apache 2.0)                               | Open (Foundation GitHub)           | N/A                                                   | Apache 2.0                                                  | Free |
| `kailash-runtime` (Apache 2.0)                     | Open (Foundation GitHub)           | N/A                                                   | Apache 2.0                                                  | Free |
| `kailash-rs-bindings` (PyPI + Terrene open GitHub) | Python glue open; Rust core closed | Compiled `.so`/`.dylib`/`.pyd` freely redistributable | Composite — Apache 2.0 glue + freely-redistributable binary | Free |
| `kailash-py` (PyPI + Terrene open GitHub)          | Fully open                         | Pure Python                                           | Apache 2.0                                                  | Free |

**Nothing in Envoy's distribution requires payment, registration, commercial license acceptance, or a hosted service.**

### Phase migration

| Phase  | Runtime default                                                                                       | Distribution                                                                                                            | Notes                                                                                                 |
| ------ | ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| 01 MVP | `kailash-py` runtime only; abstract interface defined but Rust binding not yet wired (lands Phase 02) | `pipx install envoy-agent`                                                                                              | Prove the UX; Rust binding integration lands in Phase 02                                              |
| 02     | `kailash-rs-bindings` default, `kailash-py` opt-out                                                   | `curl \| sh` single-binary launcher; `brew install envoy-agent`; `winget`; `cargo install`                              | Runtime picker in first-run; static binary bundles Python interpreter via uv-managed or PyO3 embedded |
| 03     | Same, with cross-SDK conformance test vectors validating feature parity between both runtimes         | Same                                                                                                                    | Conformance vectors (PACT N1–N6 pattern) ensure opt-out users get identical behavior, only slower     |
| 04+    | Same                                                                                                  | Mobile clients (Flutter) bundle `kailash-rs-bindings` for device performance; pure-Python fallback available on desktop |                                                                                                       |

### Rationale

1. **Foundation mandate fully satisfied.** Envoy source is Apache 2.0. A fully-open-source runtime (kailash-py) is a one-flag install. No user is required to touch a closed artifact.
2. **Performance-first default.** Most users get Rust speed from day one without thinking about it.
3. **Sovereignty narrative preserved.** Single static binary (Rust); no system Python dependency; no npm supply chain; user-owned keys, user-owned infra.
4. **Forkability preserved.** Anyone can fork Envoy + kailash-py and run a fully open-source stack indefinitely.
5. **Independence.** Nothing binds Envoy to a commercial vendor. If `kailash-rs-bindings` ever became unavailable, `kailash-py` continues to work.

### Precedents for the mixed-wheel pattern

- **PyTorch + CUDA.** PyTorch is BSD-3; CUDA libraries are freely redistributable in wheels.
- **`ring` (Rust).** Permissive license; binary freely distributable; widely used in Rust ecosystem cryptographic stacks.
- **SQLite.** Public-domain source for the library.
- **NVIDIA CUDA Python.** Free pip install combining an open binding with vendor libraries.

All are legally sound and widely accepted in production open-source distribution.

### Consequences

- Two toolchains to maintain conformance test vectors for (Rust binding + Python).
- Runtime abstraction must be feature-identical on both impls — enforced by conformance vectors at every release gate.
- SPDX metadata on PyPI must cleanly declare the composite license of `kailash-rs-bindings` so automated scanners (FOSSA, Snyk, Sonatype) do not mis-flag.
- Envoy installer must surface the runtime choice transparently; hidden defaults = credibility damage.
- Legal counsel engagement is a Phase 00 gate item (ADR-0009).

### Open sub-decisions

- **Embedding strategy** — PyO3 compile-time vs uv-managed subprocess at runtime. Lean: uv-style for flexibility. Revisit Phase 02 `/analyze`.
- **Binary size tradeoffs** — Does Rust binary ship with Python interpreter embedded or fetch on first launch? Target: embedded (atomic install, offline-capable). Cost: +30–40 MB binary size. Accept.
- **Cross-compilation matrix** — macOS (arm64, x86_64), Linux (arm64, x86_64, musl), Windows (x86_64). Phase 02 decision.

---

## ADR-0002 — Naming: Envoy (with legal disambiguator)

**Date:** 2026-04-21
**Status:** Accepted (pending trademark sweep)

### Decision

**Envoy**, with a legal mark that disambiguates from CNCF Envoy Proxy. Candidates: "Envoy Agent", "Envoy AI", "Envoy.ai", "Terrene Envoy". Final mark after USPTO + EUIPO + namespace sweep.

### Rationale

1. **Thematic fit.** An envoy carries delegated authority from a sovereign — which is literally what every Envoy action does (signed EATP Delegation Record rooted in a named human Genesis Record).
2. **Verb + noun scalability.** "Send an envoy to draft 3 emails." "Your envoy declined Jamie's request." "Envoy up."
3. **Audience separation.** CNCF Envoy Proxy occupies the infrastructure-tier project space; the legal disambiguator (e.g. "Envoy Agent") makes Envoy's product context explicit at first contact, independent of any other project's positioning.
4. **The metaphor names the product accurately.** An envoy carries delegated authority; the product's architecture is delegated authority. The name and the substance match.

### Consequences

- Legal sweep mandatory before public launch (Phase 00 gate).
- `envoy-agent` namespace confirmed available on npm, PyPI, crates.io as of 2026-04-21 (rechecked 2026-05-03 — still all 404 / available).
- GitHub org `envoy-agent` confirmed available 2026-05-03 (`gh api orgs/envoy-agent` → 404; `users/envoy-agent` also 404, no user-account collision).

---

## ADR-0003 — Shamir recovery: SLIP-0039 from day 1

**Date:** 2026-04-21
**Status:** Accepted

### Decision

**SLIP-0039 Shamir-split mnemonic recovery with 3-of-5 default** as a Phase 01 launch requirement. User-configurable from 2-of-3 (minimum) to 5-of-9 (maximum).

### Rationale

1. Sovereignty narrative depends on it. "MY keys, MY infra" is not sovereignty if a hard-drive failure kills the Trust Vault.
2. SLIP-0039 is the SatoshiLabs industry standard; BIP39-compatible wordlists; audited libraries in both Rust (`shamirs`, `sharks`, `vsss-rs`) and Python (`slip39`, `python-shamir-mnemonic`).
3. Interop with hardware-wallet recovery ecosystem (Trezor, Keystone, KeepKey). Users can recover from any SLIP-0039 tool.
4. Deferring it undermines the pitch. Single-machine risk is a legitimate concern users will raise.

### Consequences

- Crypto audit required before public release. Use audited libraries; never roll our own.
- Boundary Conversation pauses for the 3-of-5 backup ritual (print five cards, three in safe, two with trusted humans).
- Paper-shard format is Trezor-compatible for interop.

---

## ADR-0004 — Envelope Library: federated registry, Foundation-verified tier

**Date:** 2026-04-21
**Status:** Accepted

### Decision

**Three-tier federated Envelope Registry.**

- **Tier 1 — Foundation-Verified.** Reviewed by Terrene Foundation, cryptographically signed by the Foundation key, featured in default registry view. Examples: `@terrene/freelancer-v1`, `@terrene/parent-household-v1`, `@terrene/solo-founder-v2`, `@terrene/attorney-client-privilege-v1`. Bar: CO/EATP spec-compliance, red-teamed, 2-of-N Foundation signatures.
- **Tier 2 — Community.** Open publishing. Envelopes signed by publisher key. Ranked by adoption × (1 − revocation rate) so envelopes users revoke often rate lower — built-in trust signal.
- **Tier 3 — Organization.** Private registries for enterprise teams. Envelopes deployable only within an organization's Trust Lineage root.

### Rationale

1. Foundation project mandate — non-commercial, open federation aligns with the Foundation's stewardship model.
2. Tiering solves the quality-floor vs velocity dilemma. Foundation-Verified is the discovery default; Community stays open but self-sorts by adoption and revocation signal.
3. Signed envelopes enable cryptographic supply-chain verification — integrates with EATP Trust Lineage.
4. CO methodology as authoritative superset. Every envelope validated at publish time. `SKILL.md` ingest is a compatibility substrate translated to CO-compliant envelopes so the broader skill ecosystem carries across.

### Infrastructure

- Registry API → Kailash Nexus (HTTP + CLI + MCP surfaces).
- Publisher signing → Ed25519 via EATP `TrustKeyManager`.
- Spec validation → CO/EATP conformance test vectors (N1–N6).
- Search → installs count × inverse-revocation-rate ranking + tag filtering.
- Storage → content-addressed via hash; IPFS or git-mirror optional replication.

### Consequences

- Foundation infrastructure cost (small, covered by Foundation budget).
- Signed publishing raises the supply-chain-security floor; publishers accept a signing step in exchange.
- `SKILL.md` → CO-compliant envelope translator is a Phase 02 deliverable.

---

## ADR-0005 — `SKILL.md` compatibility — full ingest, with CO as superset authority

**Date:** 2026-04-21
**Status:** Accepted

### Decision

Envoy accepts any `SKILL.md`-formatted skill unchanged, wrapped with a generated `ENVELOPE.md` declaring permission needs. **CO methodology is the authoritative superset.** Skills pass a CO-compliance validator at install time; declared tool uses (`bash:*`, `file-read:*`, `http-post:*`, `mcp:*`) translate to PACT constraint dimensions. Skills that do not meet CO compliance at install-time checks require `force_install=True` with an explicit warning.

### Rationale

1. Full compatibility = zero migration tax for users coming from `SKILL.md`-based ecosystems. Existing skill libraries carry across on day 1.
2. CO superset preserves governance integrity. The validator catches skill definitions that request permissions inconsistent with their declared intent, at install time rather than at runtime.
3. Install-time validation beats runtime validation (too late) and manual review (doesn't scale).
4. `force_install=True` opt-out respects user sovereignty. The user stays sovereign; loud warnings make the choice explicit.

### Consequences

- CO ↔ `SKILL.md` ↔ PACT envelope translator is a Phase 02 deliverable.
- Skill-compatibility linter runs as part of `envoy skill install`.
- Foundation-Verified tier will include a curated subset of popular `SKILL.md` skills with certified CO-compliant envelopes.

---

## ADR-0006 — Model choice: BYOM at install, local default available

**Date:** 2026-04-21
**Status:** Accepted

### Decision

User picks at install. Options: local (Ollama / llama.cpp / MLX), Anthropic Claude, OpenAI GPT, DeepSeek, custom OpenAI-compatible endpoint. Routed through Kaizen `Delegate` provider abstraction. No lock-in.

### Rationale

- **Model neutrality** is a first principle for Envoy — no provider lock-in.
- Sovereignty is compatible with cloud models: the agent runs on the user's infrastructure; only inference is delegated to the chosen provider.
- A local default option ensures offline first-launch is always possible.

### Consequences

- Installer model-picker UX in first-launch flow.
- Degraded mode for users who decline cloud AND skip local download: minimal prompt-template runtime can drive Boundary Conversation without full LLM.

---

## ADR-0007 — Trust Vault sync: native Foundation + third-party integrations

**Date:** 2026-04-21
**Status:** Accepted

### Decision

Envoy ships native Trust Vault sync (Foundation-operated optional node, zero-knowledge) AND integrates with iCloud Drive, Dropbox, Keybase, personal git repo, WebDAV, S3-compatible. Default: **local-only** (opt-in sync).

### Rationale

- Native sync maintains sovereignty (no third-party required).
- Integrations respect existing user workflows.
- Local-only default = minimum-surprise posture.

### Consequences

- Sync protocol spec + cross-SDK implementation (Rust binding + Python).
- Foundation sync node operation is a Foundation infrastructure item.

---

## ADR-0008 — Mobile onboarding: first-class

**Date:** 2026-04-21
**Status:** Accepted

### Decision

iOS + Android native apps from Phase 02. Flutter (Kailash `flutter-specialist` agent exists in COC). QR-code pairing with local Envoy instance.

### Rationale

- Channel-native thesis implies phone-first life. iMessage / Telegram / Signal / WhatsApp are phone-first.
- Boundary Conversation + Grant Moments + Daily Digest rituals are phone-optimal.
- QR-pairing is a magical onboarding moment.

### Consequences

- Flutter workstream from Phase 02.
- Flutter → Rust FFI for envelope compiler / Trust store access (uses `kailash-rs-bindings` Ruby/Node/WASM binding patterns).
- App Store / Play Store compliance items (privacy labels, on-device model policies).

---

## ADR-0009 — Licensing, runtime pluggability, Foundation compliance protocol

**Date:** 2026-04-21
**Status:** Accepted (with pending legal-counsel items)

### Decision

Envoy's openness posture is composite and Foundation-compliant:

| Layer                               | License                                           | Open-source                            | Free to user | Foundation artifact |
| ----------------------------------- | ------------------------------------------------- | -------------------------------------- | ------------ | ------------------- |
| Envoy application                   | Apache 2.0                                        | Yes — source on Foundation GitHub      | Yes          | Yes                 |
| `kailash-runtime` interface         | Apache 2.0                                        | Yes — source on Foundation GitHub      | Yes          | Yes                 |
| CARE/EATP/CO/PACT specs             | CC BY 4.0                                         | Yes                                    | Yes          | Yes                 |
| `kailash-rs-bindings` Python glue   | Open license (Apache 2.0 or BSD, TBD)             | Yes — source on Terrene open GitHub    | Yes          | Terrene-hosted      |
| `kailash-rs-bindings` compiled core | Freely redistributable binary; source held closed | Source: no; binary: freely distributed | Yes          | Terrene-distributed |
| `kailash-py`                        | Apache 2.0 (code; references CC BY 4.0 specs)     | Yes — source on Foundation GitHub      | Yes          | Yes                 |

**Key Foundation-compliance properties:**

1. **Every user path is free.** No payment, no registration, no commercial ToS, no gating.
2. **A fully open-source runtime is always available** (`kailash-py`). Envoy's runtime abstraction makes the swap a one-flag install.
3. **Envoy's own source is Apache 2.0.** Users can fork Envoy and modify it freely.
4. **Installer discloses transparently** which runtime is active and how to switch. No hidden defaults.
5. **No commercial-vendor dependency.** If `kailash-rs-bindings` ever became unavailable, `kailash-py` continues to work.

### Legal-counsel engagement items (Phase 00 gate)

The architecture is sound; professional drafting required for:

1. **Composite LICENSE file in `kailash-rs-bindings` wheel.** Delineate Apache 2.0 Python glue + freely-redistributable compiled binary, with explicit end-user grants (use, redistribute as part of Python applications, reverse-engineering terms on binary).
2. **SPDX metadata on PyPI.** Choose a composite expression that reads cleanly under automated scanners (FOSSA, Snyk, Sonatype). Candidates: `Apache-2.0 AND LicenseRef-kailash-rs-bindings-binary-grant` with a clear `License-File` reference.
3. **Terrene Foundation charter compatibility statement.** Foundation board/counsel to confirm that Foundation projects (Envoy) may transitively depend on a Terrene-hosted binary-closed-source PyPI package by default, with an open-source alternative available. Precedent patterns: distributions that ship open code alongside vendor-distributed compiled firmware or numerical libraries; Python projects that depend on PyTorch-with-CUDA.
4. **User-facing disclosure.** Installer screen + README + runtime-picker copy explicitly name the closed-binary component and the fully open-source alternative.
5. **Export control.** Rust binary redistribution may intersect US / Singapore dual-use / crypto export regulations depending on what crypto primitives ship. Scope: what EATP cryptography (Ed25519, SHA-256, Shamir libs) is compiled into the binary.
6. **Trademark.** "Envoy Agent" / "Envoy AI" / alternative — USPTO Class 9 + 42, EUIPO, UK IPO sweep.
7. **Runtime-swap conformance contract.** Both runtime implementations must be feature-identical per cross-SDK conformance test vectors. Enforcement: every release gate.

### Licensing audit sub-task (delegated 2026-04-21)

A reviewer agent audited the Foundation's Python and Rust-bindings COC template repositories and the `loom/` orchestration layer for licensing-claim accuracy against the ground-truth locked above. Fixes applied inline; findings filed with the workspace record.

### Consequences

- Phase 00 cannot close until the 7 legal-counsel items above are either resolved or explicitly parked with disclosure.
- Every release must pass an automated composite-license-metadata check (`pip-licenses --with-license-file --format=json` output diffed against expected).
- Foundation board must endorse the runtime-pluggability model in writing before public launch.

---

## Pending / placeholder ADRs

- ADR-0010 — Scheduler / HEARTBEAT.md equivalent (Phase 02)
- ADR-0011 — Multi-principal / Shared Household architecture (Phase 03)
- ADR-0012 — Rust skills SDK (Phase 04)
- ADR-0013 — Foundation charter amendment for runtime-pluggability model (if required)
