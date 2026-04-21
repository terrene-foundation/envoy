# Envoy — Roadmap

**Status:** pre-Phase-01 (concept approved 2026-04-21)
**Execution model:** Autonomous. Effort below is in **sessions**, not human-days.

## Phase 00 — Alignment (NOW)

Goal: land the concept; verify names, registries, licensing; Foundation sign-off.

**Naming + namespace:**
- [ ] USPTO + EUIPO + UK IPO trademark sweep, Class 9 (software) + Class 42 (SaaS)
- [ ] Final legal mark — "Envoy Agent" vs "Envoy AI" vs alternatives
- [ ] GitHub org + namespace reservation (`envoy-agent` confirmed available on npm/PyPI/crates 2026-04-21)

**Envoy-claim verification:**
- [ ] Cross-check every factual claim destined for public Envoy collateral (Charter, README, website copy) for accuracy and supporting citation
- [ ] Remove any comparative claims about other projects from public-facing documents; retain only neutral references where required for interoperability context (e.g. `SKILL.md` format)

**Licensing + legal counsel (per ADR-0009):**
- [ ] Draft composite LICENSE file for `kailash-rs-bindings` PyPI wheel (Apache 2.0 glue + freely-redistributable binary)
- [ ] Finalise SPDX metadata for PyPI (composite expression that reads cleanly under FOSSA / Snyk / Sonatype)
- [ ] Terrene Foundation charter compatibility statement — Foundation board approval of runtime-pluggability model
- [ ] Draft user-facing disclosure text (installer screen, README, runtime-picker copy)
- [ ] Export-control assessment of Rust binary redistribution (crypto primitives, dual-use regulations)
- [ ] Runtime-swap conformance contract drafted (both implementations feature-identical per test vectors)
- [ ] Licensing audit of Foundation COC template repositories and `loom/` orchestration layer (completed 2026-04-21; findings on file)

**Foundation sign-off:**
- [ ] Terrene Foundation board endorses Envoy as Foundation project
- [ ] Apache 2.0 code + CC BY 4.0 methodology + ingesting MIT-licensed `SKILL.md`-formatted skills = compatible
- [ ] Publish working concept one-pager for Foundation board review

**Exit criteria:** all items ✅. Then `/analyze` Phase 01.

## Phase 01 — MVP (target: 3–5 sessions)

Goal: prove the Boundary Conversation + Grant Moments + Daily Digest loop works. 1 channel (CLI + Web). Ship as Python package (interim distribution, `kailash-py` runtime only).

**Surface:**
- `pipx install envoy-agent` (interim; Phase 02 moves to single static binary)
- `envoy init` runs Boundary Conversation
- `envoy up` starts the gateway
- `envoy boundaries` opens the envelope for review/edit
- CLI channel (TUI chat) + Web channel (local HTTP on localhost)

**Components (Python first, via `kailash-py`):**
- Boundary Conversation agent (Kaizen `BaseAgent` with scripted Signature; outputs `EnvelopeConfig`)
- Grant Moment UI (CLI prompt + Web modal)
- Daily Digest scheduler (Kaizen scheduled agent)
- Envoy Ledger (EATP `TieredAuditDispatcher` + SQLite + export CLI)
- Envelope compiler (PACT `RoleEnvelope` + `TaskEnvelope` + `intersect_envelopes()`)
- Trust store (EATP `SQLiteTrustStore` or `FilesystemStore`)
- Budget tracker (EATP `BudgetTracker` + `SQLiteBudgetStore`)
- Model adapter layer (Kaizen `Delegate` → local Ollama / Claude / GPT / DeepSeek)
- Shamir 3-of-5 recovery (SLIP-0039 via `slip39` Python package)

**Deferred to Phase 02+:** non-CLI/Web channels, Rust binary distribution, mobile clients, multi-principal, Envelope Library registry, `SKILL.md` bulk ingest.

**Exit criteria:**
- 1 first-time user completes Boundary Conversation end-to-end
- 3 Grant Moments triggered and resolved correctly
- Daily Digest renders at scheduled time with real data
- Envoy Ledger exports a verifiable hash-chained log
- Trust Vault backup via SLIP-0039 Shamir works (3-of-5 reconstruct test)
- `/redteam` passes: spec-compliance AST/grep verified, 0 CRITICAL/HIGH findings, 2 clean rounds

## Phase 02 — Distribution + channels + runtime pluggability (target: 5–8 sessions)

Goal: single static binary. Runtime picker on first run. Top-6 channels. Mobile onboarding.

**Runtime pluggability (ADR-0001 + ADR-0009 delivery):**
- `kailash-runtime` abstract interface crate (Apache 2.0)
- `kailash-rs-bindings` integration (default runtime)
- `kailash-py` integration (opt-in alternative runtime)
- First-run runtime picker
- Cross-SDK conformance test vectors validating feature parity between both runtimes

**Distribution surfaces:**
- `curl -sSf https://get.envoy.ai | sh` → single Rust binary (kailash-rs core embedded Python interpreter)
- `brew install envoy-agent`
- `winget install envoy-agent`
- `cargo install envoy-agent`
- Flutter iOS + Android clients, QR-code pairing

**Channels:** 6 channels — iMessage (BlueBubbles), Telegram, Slack, Discord, WhatsApp, Signal (plus CLI + Web from Phase 01).

**Envelope Library v1:** Foundation-Verified tier live; Community tier frozen.

**`SKILL.md` translator:** lint + CO-compliance validator + automated envelope generator. A curated set of popular `SKILL.md`-format skills certified as CO-compliant for the Foundation-Verified tier.

**Exit criteria:**
- Rust binary builds on macOS (arm64 + x86_64), Linux (arm64 + x86_64 + musl), Windows (x86_64)
- Binary size <50 MB with embedded Python interpreter
- Runtime picker works; opt-out to pure-Python mode tested end-to-end
- Cross-runtime conformance vectors pass (both runtimes behave identically)
- 6 channels pass end-to-end Grant Moment → action → audit
- Mobile QR-pairing works in <30s from cold start
- CO validator rejects 3 constructed adversarial skill samples (permission-escalation, exfiltration, privilege-overreach) and accepts 100 benign ones

## Phase 03 — Hot-path migration + Envelope Library open (target: 5–8 sessions)

Goal: Envelope Library Community tier opens. Weekly Posture Review + Monthly Trust Report rituals ship. Shared Household / multi-principal.

**Components:**
- Envelope Library Community tier — open publishing with publisher Ed25519 signatures, spam/abuse guardrails
- Weekly Posture Review ritual
- Monthly Trust Report (PDF + JSON export)
- Shared Household: 5-person family with 5 envelopes + shared channel

**Exit criteria:**
- Hot-path P50 latency <10ms (default Rust runtime) vs <80ms (pure-Python opt-out)
- Envelope Library Community tier accepting publishes with signature verification
- Shared Household end-to-end works for 5-person family scenario
- Cross-SDK conformance vectors pass on both runtimes

## Phase 04 — Channel breadth + Rust skills SDK (target: 8–12 sessions)

Goal: broad channel coverage + Envoy-native channels. Rust skills SDK.

**Channels:**
- 15 additional messaging channels (Matrix, Feishu, LINE, Mattermost, WeChat, QQ, Teams, Google Chat, IRC, Nostr, Twitch, Tlon, Zalo, Nextcloud Talk, Synology Chat)
- Apple Shortcuts native
- Calendar-as-channel (iCal subscription + bidirectional)
- Browser extension (right-click → delegate)
- IDE extensions (VS Code, JetBrains, Zed, Cursor)
- RCS + SMS (Twilio / MessageBird)
- Voice channel (Whisper → Envoy → TTS)

**Components:**
- Rust skills SDK — skills compiled to wasm sandbox
- Envelope Library Organization tier for enterprise private registries

**Exit criteria:**
- 23+ messaging channels active, including 5 Envoy-native channels (Apple Shortcuts, Calendar, browser extension, IDE extensions, voice)
- 3 production Rust skills published to Foundation-Verified tier
- 2 enterprise pilot customers on Organization-tier registries

## Phase 05+ — Regulated industries + SSO/SAML/SCIM + SOC2

Goal: enterprise credibility for finance / healthcare / public sector.

- SSO / SAML / SCIM integration pack
- SOC2 Type 1 audit (target: month 9 post-Phase-01)
- HIPAA compliance pack
- GDPR DPIA tooling
- Managed Envoy deployment templates (customer-hosted Kubernetes operator)
- Federated Trust Mesh (cross-org delegation) with real anchor customer

## Parallel workstreams (ongoing)

- **Documentation** — user guide, developer guide, CO/EATP spec references, envelope authoring tutorial
- **Security** — quarterly red team, crypto audit of Shamir + EATP, prompt-injection defense testing
- **Community** — forum, Discord, Envelope Library moderation
- **Foundation governance** — Terrene charter updates, steward election, financial transparency
- **Trademark + legal** — monitoring, maintenance filings, international expansion

## Cross-cutting principles (enforced every phase)

- Zero-tolerance for pre-existing failures/warnings (Foundation COC rule family)
- Orphan-detection + facade-manager-detection (every governance primitive has a hot-path call site in the same PR)
- Real-infrastructure testing for Tier 2 (no mocks)
- Cross-runtime conformance vectors at every release gate (kailash-rs-bindings ≡ kailash-py behaviour)
- Cross-SDK parity via BP-series commits
- Commit-message claim accuracy
- Scanner-surface symmetry — findings on PR scan fixed regardless of main-branch state
