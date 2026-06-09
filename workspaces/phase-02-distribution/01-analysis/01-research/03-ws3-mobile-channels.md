# WS-3 — Mobile + 3 Deferred Channels (Implementation Architecture Deep-Dive)

**Phase:** 02-distribution / 01-analysis / 01-research
**Workstream:** WS-3 (Flutter mobile clients + restore the 3 deferred messaging channels → full 6)
**Authority read:** `specs/channel-adapters.md`, `specs/grant-moment.md`, `specs/connection-vault.md`, `specs/ui-platform.md`, `specs/runtime-abstraction.md`, `DECISIONS.md` ADR-0008, `specs/mvp-build-sequence.md`. Source grounded against `envoy/channels/{adapter,telegram,web,slack,discord,cli}.py`.

> Scope note: this is IMPLEMENTATION architecture for `/analyze`. It identifies spec gaps (additions only — no spec edits per `rules/spec-accuracy.md` + `rules/specs-authority.md` MUST-5) and open questions for `/todos`.

---

## 0. Ground-truth: what Phase-01 actually shipped (verified against source)

A claim in the brief and in `specs/mvp-build-sequence.md:121` (shard 16) needs correction before any WS-3 plan is built on it. The build-sequence text lists `WhatsAppChannelAdapter + IMessageChannelAdapter + SignalChannelAdapter` as Phase-01 shard-16 deliverables (item 4, "caveated; cohort-driven de-scope #1 candidate"), and `specs/channel-adapters.md:211-213` marks all three "Yes (caveat)" / "Yes (Path B)" in the Phase-01 ship column.

**Source reality** (`ls envoy/channels/`, grep for the adapter classes):

| Adapter class            | File on disk?    | Class defined anywhere?                                 |
| ------------------------ | ---------------- | ------------------------------------------------------- |
| `CLIChannelAdapter`      | `cli.py` ✅      | ✅                                                      |
| `WebChannelAdapter`      | `web.py` ✅      | ✅                                                      |
| `TelegramChannelAdapter` | `telegram.py` ✅ | ✅                                                      |
| `SlackChannelAdapter`    | `slack.py` ✅    | ✅                                                      |
| `DiscordChannelAdapter`  | `discord.py` ✅  | ✅                                                      |
| `WhatsAppChannelAdapter` | — ❌             | **none** (`grep -rln` empty across `envoy/` + `tests/`) |
| `SignalChannelAdapter`   | — ❌             | **none**                                                |
| `IMessageChannelAdapter` | — ❌             | **none**                                                |

So Phase-01 shipped **5 of 8 surfaces** (CLI + Web + 3 bot-API-clean messaging channels), not 8. The 3 messaging channels that the brief calls "deferred" (iMessage / WhatsApp / Signal) were **never implemented in code at all** — they are net-new build for WS-3, not "restore/override of a shipped adapter". This matters for `/todos` sizing: WS-3 is _three greenfield adapters_ against a frozen contract, not _three caveated adapters getting their caveats lifted_. (See Spec gap #1.)

The contract they must satisfy is the frozen `ChannelAdapter` ABC at `envoy/channels/adapter.py:42-244` — 9 abstract methods + 2 Phase-02 ritual surfaces that currently raise `PhaseDeferredError` (`adapter.py:209,224`).

---

## 1. Flutter client architecture + QR-pairing protocol

### 1.1 What the specs authorize

ADR-0008 (`DECISIONS.md:254-273`) is the entire authorization surface for mobile:

- iOS + Android native apps from Phase 02, built in Flutter (`DECISIONS.md:261`).
- "QR-code pairing with local Envoy instance" (`:261`) — the pairing is between the **phone app** and a **local Envoy instance** (desktop/laptop running the Envoy runtime).
- "Flutter → Rust FFI for envelope compiler / Trust store access (uses `kailash-rs-bindings` Ruby/Node/WASM binding patterns)" (`:272`).
- App Store / Play Store compliance: privacy labels, on-device model policies (`:273`).

ADR-0008 says **nothing** about the pairing _handshake_ — no protocol, no threat class, no cold-start budget. Those are the deliverables of this deep-dive and are Spec gap #2.

### 1.2 The trust boundary is new — and it is the most security-sensitive surface in WS-3

Every Phase-01 surface is either (a) local-only (CLI is in-process; Web binds `127.0.0.1` with an Origin/Host allowlist — `envoy/channels/web.py:9-10,70,81,489`) or (b) a third-party bot API where the transport is the vendor's TLS. The mobile app introduces the **first device-to-device trust boundary Envoy owns end-to-end**: a phone (untrusted until paired) talking to the user's local Envoy instance over the LAN (or a relay).

**Threat class.** This is a **device-pairing / authenticated-key-exchange problem under an active-network adversary** — the same class as Signal's safety-number verification, WhatsApp Web's QR linking, and Matrix's cross-signing. The concrete threats that map onto Envoy's existing model (`specs/threat-model.md` is referenced but does not yet enumerate a pairing threat — Spec gap #3):

- **T-080 network MITM** (already in `channel-adapters.md:10,234`) — an adversary on the LAN/relay intercepts the pairing exchange and substitutes its own key, becoming a silent relay for every future Grant Moment.
- **QR-shoulder-surf / screenshot-exfil** — the QR is rendered on the local-instance screen; a camera or screen-recorder captures it. This is exactly the T-070 side-channel class (`ui-platform.md:21` screen-recording detection) but applied to the _pairing_ render, not the _Grant Moment_ render.
- **Visible-secret spoofing (T-018)** — once paired, the phone becomes a Grant Moment render surface; a spoofed pairing means a spoofed visible secret. The visible secret (`grant-moment.md:82`, icon+color+phrase from Trust Vault) is the anti-spoof primitive that MUST bind into the pairing result.
- **Replay (T-008)** — a captured QR re-scanned later must not re-pair. The Grant Moment nonce discipline (`grant-moment.md:29,145` `GrantMomentReplayError`) is the precedent; pairing needs its own nonce.

### 1.3 Recommended pairing handshake (SPAKE2-class, channel-binding to the visible secret)

I recommend a **short-authenticated-string (SAS) handshake bootstrapped by the QR**, not a bare "QR carries a bearer token" scheme. Plain-language framing for the user: _the QR is not a password — it's a one-time secret that both devices use to prove to each other that nobody in the middle swapped their keys. After scanning, the phone shows a colored icon-and-phrase that must match what your computer shows; if it doesn't, someone is intercepting._

Handshake (each step cites the precedent it reuses):

1. **Local instance generates a pairing offer.** A fresh ephemeral X25519 keypair + a high-entropy `pairing_nonce` (reuse the nonce discipline from `grant-moment.md:29`). The QR encodes: the local instance's `principal_genesis_id` (sha256, `connection-vault.md:31`), the ephemeral public key, the `pairing_nonce`, a `pairing_offer_expiry` (≤30s — see budget), and the LAN endpoint(s) / relay rendezvous id. **The QR carries no long-term secret and no bearer token** — capturing it after expiry is worthless.
2. **Phone scans, runs the AKE.** SPAKE2 (or Noise `XX` with the QR-delivered pre-shared nonce as the channel-binding salt) derives a shared session key. An on-LAN MITM cannot complete the exchange without the nonce; an off-LAN relay never sees the nonce.
3. **SAS confirmation = the visible secret.** Both devices derive a short authenticated string from the session-key transcript and render it **as the Trust-Vault visible secret** (icon + color + phrase, `grant-moment.md:82`). The user confirms they match. This binds the new device into the _same_ T-018 anti-spoof primitive every Grant Moment already uses — no second mental model for the user.
4. **Phone enrolls as a render surface, NOT a key holder.** The phone receives a _device-scoped_ credential stored in the iOS/Android keychain (`connection-vault.md:23-24`), keyed by `principal_genesis_id`. The local instance remains the signing authority (`runtime-abstraction.md:77` "Runtime device-key signing"). The phone renders Grant Moments and posts decisions back; it does **not** hold the delegation key. This keeps the phone a thin authenticated terminal, so a stolen/unpaired-but-not-revoked phone cannot sign.
5. **Pairing is a Ledger event.** Emit a signed pairing record (model on `runtime-abstraction.md:156` `RuntimeAttestation` / `KeyRotationRecord` with `key_scope` discipline at `:133`) so pairing is auditable and revocable. Connection Vault is device-local and never synced (`connection-vault.md:57-59`), so each device pairs independently — consistent with `connection-vault.md:113` "multi-device pairing requires deliberate re-issue, not transparent sync".

**QR-pairing security verdict (for the return summary):** _Acceptable ONLY as an SAS/AKE handshake channel-bound to the Trust-Vault visible secret, with a ≤30s single-use expiring nonce and the phone enrolled as a render-only terminal (no delegation key on device)._ A bare bearer-token-in-QR scheme is **rejected** — it collapses to T-080 MITM + T-008 replay with no user-verifiable defense. The SAS step reuses the existing T-018 visible-secret primitive, so the security model adds a _new transport_ but **no new trust primitive** — which is the right shape.

### 1.4 The <30s cold-start budget

The brief sets a <30s cold-start budget. Two distinct "30s" numbers exist in the specs and MUST NOT be conflated (Spec gap #4):

- **Clipboard auto-clear ≤30s** (`connection-vault.md:63`, `ui-platform.md:16`) — unrelated to cold-start; it's the credential-capture hygiene window.
- **Cold-start budget <30s** (brief) — wall-clock from app-launch to a usable paired session.

Cold-start decomposition and where the time goes:

| Stage                                                                        | Budget              | Risk                                                                                                         |
| ---------------------------------------------------------------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------ |
| Flutter app boot + FFI init (`kailash-rs-bindings` load, `DECISIONS.md:272`) | ~3-5s               | Rust binary hash verification (`runtime-abstraction.md:21`) on first launch can dominate; cache the verdict. |
| QR render on local instance + scan                                           | user-paced          | Set `pairing_offer_expiry` to bound this; re-render on expiry.                                               |
| AKE round-trip (SPAKE2/Noise over LAN)                                       | <1s LAN, 2-4s relay | Relay path is the long pole; prefer mDNS/LAN discovery, fall back to relay.                                  |
| Keychain enroll + first session-state hydrate (`specs/session-state.md`)     | ~2-3s               | Secure Enclave (`connection-vault.md:23`) key-gen is the cost; pre-warm at app boot.                         |

The budget is achievable on the LAN path; the **relay path is the at-risk one** and should be flagged for `/todos` as a measured acceptance gate (sibling of EC-7's per-channel onboarding gate, `mvp-build-sequence.md:180`).

---

## 2. The 3 deferred channel adapters

All three extend the frozen `ChannelAdapter` ABC (`adapter.py:42`). Each MUST implement: `channel_id`, `startup`, `shutdown`, `receive_message`, `send_message`, `send_grant_moment`, `render_grant_moment`, `send_digest`, `capabilities`, `rate_limit_status` — and MAY override the two Phase-02 ritual surfaces (`send_posture_review`, `send_monthly_report`) which Phase-02 wires (`channel-adapters.md:73-75`). The gate-ordering invariant INV-4 (`channel-adapters.md:158-166`: lifecycle → principal → rate-limit) and the pending-decision isolation discipline (`adapter.py` `_register_pending` / `PendingDecisionsCeilingError`, seen in `telegram.py:458-472`) are non-negotiable for all three.

### 2.1 iMessage — BlueBubbles bridge (needs user-owned Mac)

- **Compliance posture:** Apple ToS grey; user responsibility (`channel-adapters.md:213`). Requires a user-owned Mac running the BlueBubbles server. This is **not** a clean bot API — it's a bridge to a private, unsanctioned surface.
- **Contract mapping:**
  - `startup()`: authenticate to the user's BlueBubbles server (URL + password → Connection Vault `webhook_secret`/`basic_auth`, `connection-vault.md:32`). 10s fail-closed timeout (`adapter.py:69`). SSRF-guard the BlueBubbles URL exactly as Discord guards its webhook (`channel-adapters.md:238`, `_validate_webhook_url_ssrf`) — the BlueBubbles host is user-supplied and could point at loopback/IMDS.
  - `receive_message()`: BlueBubbles emits via socket.io / webhook; map to `InboundMessage` (`channel-adapters.md:190-200`). Bounded queue 100, overflow→Ledger (`adapter.py:94`).
  - `capabilities`: `supports_buttons=False` (iMessage has no inline buttons — Grant Moment options render as numbered text replies, like the Telegram queue-based fallback), `supports_reactions=True` (tapbacks), `supports_attachments=True`, E2E encryption = yes (`channel-adapters.md:232`).
  - `render_grant_moment()` must render the visible secret as text+emoji (no rich card).
- **De-scope flag:** iMessage **native** is explicitly OPTIONAL per `mvp-build-sequence.md:204` ("Phase-02+ adds iMessage native"). The BlueBubbles _bridge_ is the Phase-02 surface; iMessage-native is a later, separate effort. **iMessage (BlueBubbles) is a de-scope candidate** — it requires user-owned hardware (Mac), carries the highest compliance risk (Apple ToS grey), and serves the narrowest cohort.

### 2.2 WhatsApp — Business API

- **Compliance posture:** Paid tier; Foundation gateway OR user-own (`channel-adapters.md:211`). This is the **launch-blocker open question** already flagged at `channel-adapters.md:292` (Foundation gateway vs user-own pricing/SLA).
- **Contract mapping:**
  - `startup()`: WhatsApp Business API credentials (`bot_token`/`oauth_refresh` in Connection Vault). The pricing/SLA model is an envelope decision, not an adapter decision.
  - `capabilities`: `supports_buttons=True` (WhatsApp interactive messages / list-replies — Grant Moment options map cleanly), `supports_markdown` limited, E2E encryption = yes (`channel-adapters.md:232`).
  - Rate-limit: WhatsApp imposes tiered messaging limits; `rate_limit_status()` (`adapter.py:238`) must reflect the Business-API quota, and the soft-quota warning at 80% (`adapter.py:241`).
- **De-scope flag:** **NOT** an OPTIONAL de-scope candidate per `mvp-build-sequence.md` (only iMessage-native + Signal-Path-A are named OPTIONAL at `:204`). WhatsApp is a **launch-blocker pending the gateway/pricing decision** (`channel-adapters.md:292`), which is a _business_ gate, not an engineering de-scope. Recommend it stays in WS-3 scope but is sequenced **after** the Foundation-gateway-vs-user-own decision lands (that decision is a `/todos` prerequisite, not WS-3 work).

### 2.3 Signal — Path A vs Path B

- **Phase-01 default:** Path B (Group Link only), under the Phase-01 legal gate (`channel-adapters.md:212` "Phase 01 legal gate (Path B default)"). Note §0 above: Path B was _specified_ as shipped but the `SignalChannelAdapter` class does not exist in code — so even Path B is net-new build for WS-3.
- **Path A vs Path B (the two paths, plain-language):**
  - **Path A — `signal-cli`:** Envoy drives a full Signal account via the `signal-cli` daemon. Best UX (direct 1:1 messages, full Grant Moment rendering) but requires a dedicated Signal-registered number and carries the heaviest legal/ToS exposure — this is why it's gated.
  - **Path B — Group Link:** the user joins an Envoy-managed Signal group via an invite link; weaker UX (group-mediated, `channel-adapters.md:293` "Group Link only UX impact"). Lower legal exposure, which is why Phase-01 defaults to it.
- **Contract mapping:** identical ABC surface; the difference is the transport binding in `startup()` (signal-cli socket vs group-link webhook) and `capabilities` (Path A supports richer 1:1 rendering; Path B is group-constrained). E2E encryption = yes for both (`channel-adapters.md:232`).
- **De-scope flag:** Signal **Path A** is explicitly OPTIONAL per `mvp-build-sequence.md:204`. **Path B (Group Link) is the in-scope WS-3 deliverable** (the actual adapter, finally implemented); **Path A (signal-cli) is a de-scope candidate** — it's the OPTIONAL upgrade, carries the heaviest legal exposure, and the Path-B→Path-A adoption metric (`channel-adapters.md:293`) is the data that should drive whether Path A is built at all.

### 2.4 De-scope recommendation (consolidated)

| Channel / path                 | In-scope for WS-3?           | De-scope candidate?                   | Rationale                                                      |
| ------------------------------ | ---------------------------- | ------------------------------------- | -------------------------------------------------------------- |
| WhatsApp Business API          | Yes (after gateway decision) | No (business gate, not de-scope)      | Launch-blocker pending pricing/SLA (`channel-adapters.md:292`) |
| Signal **Path B** (Group Link) | **Yes**                      | No                                    | The actual Phase-01-promised-but-unbuilt adapter               |
| Signal **Path A** (signal-cli) | Optional                     | **YES** (`mvp-build-sequence.md:204`) | OPTIONAL upgrade; heaviest legal exposure; metric-driven       |
| iMessage (BlueBubbles bridge)  | Optional                     | **YES** (highest compliance risk)     | User-owned Mac; Apple ToS grey; narrowest cohort               |
| iMessage native                | Out of scope (Phase-02+)     | n/a                                   | `mvp-build-sequence.md:204` explicitly Phase-02+               |

**Recommended de-scope candidates: iMessage (BlueBubbles) and Signal Path A** — exactly the two `mvp-build-sequence.md:204` names OPTIONAL, plus iMessage's compliance/hardware burden. The MUST-build core of WS-3 is therefore **WhatsApp + Signal Path B + the Flutter client**, with iMessage-bridge and Signal-Path-A as cohort-/metric-gated stretch.

---

## 3. tokio async adapter layer (ties to WS-1 runtime pluggability)

### 3.1 How the contract holds across asyncio and tokio

The adapter contract is **runtime-family-agnostic by design**. `channel-adapters.md:15` states it explicitly: _"All methods are async (Phase 01 Python uses `asyncio`; Phase 02 Rust uses `tokio`)."_ The ABC (`adapter.py`) defines the contract in terms of `async def` method signatures, return types, timeout semantics, and error taxonomy — none of which name a specific event loop. The same contract document is the authority for both runtimes.

The binding mechanism is the **runtime abstraction layer (WS-1)**. `runtime-abstraction.md:15` defines `KailashRuntime` (ABC) and requires _"Every method below MUST be implemented by both `kailash-py` and `kailash-rs-bindings` runtimes"_ under BET-6 byte-identity / semantic-equivalence. Phase-01 wires **only** `kailash-py` (`runtime-abstraction.md:220`); Phase-02 wires `kailash-rs-bindings` (`:206`, `:231` `envoy runtime switch`). The adapters run **under whichever runtime is selected** — they call the `KailashRuntime` surface (Phase-A/B signing at `runtime-abstraction.md:48`, classifier cache at `:21`), not a specific event loop.

So the contract holds because:

1. **The async surface is abstract.** `async def send_grant_moment(...)` is satisfied by an asyncio coroutine _or_ a tokio future wrapped by `kailash-rs-bindings` (`DECISIONS.md:272` "Flutter → Rust FFI ... binding patterns"). The caller (`InboundRouter` fan-in, `ChannelHandoff.dispatch` at `adapter.py:147`) awaits the contract, not the loop.
2. **Pending-decision isolation is loop-agnostic in contract, loop-specific in impl.** `channel-adapters.md:170` says one `asyncio.Future`/`asyncio.Queue` per `request_id` for the Python impl; the tokio impl uses a `tokio::sync::oneshot`/`mpsc` per `request_id`. The **contract** (fresh isolation per `request_id`, `finally`-removal) is identical; the **primitive** differs. This is Spec gap #5 — the spec names `asyncio.Future` concretely at `:170`, which is correct for Phase-01 but reads as runtime-specific; Phase-02 needs the contract stated in runtime-neutral terms with per-runtime primitive notes.
3. **Timeout semantics are wall-clock, not loop-specific.** `StartupTimeoutError` at 10s (`adapter.py:69`), `SendTimeoutError`, `GrantMomentExpiredError` at 30s (`adapter.py:135`) — these are contract obligations both `asyncio.wait_for` and `tokio::time::timeout` satisfy identically.

### 3.2 The WS-1 dependency

WS-3 adapters do **not** themselves choose the runtime — they consume it. The dependency is: **WS-1 must land the `kailash-rs-bindings` `KailashRuntime` impl before any tokio-backed adapter can run under it.** A Phase-02 adapter written in Python-binding-over-Rust still presents an `async def` surface to the router; the tokio loop is _underneath the FFI boundary_ (`DECISIONS.md:272`). The cross-runtime conformance harness (N1–N6, `runtime-abstraction.md:206,229`) is the gate that proves an adapter behaves identically under both runtimes — that harness is WS-1's deliverable, and WS-3's adapters are among its test subjects.

**Recommendation:** WS-3 adapters are authored against the **abstract `ChannelAdapter` + abstract `KailashRuntime`** surfaces only. They MUST NOT import `asyncio` primitives directly for grant-moment isolation (use a small runtime-provided pending-decision primitive) so the same adapter source runs under both runtimes. This is the structural defense that makes BET-6 contract-parity (`channel-adapters.md:11`) achievable for the channel layer.

---

## 4. Native keychain + side-channel hygiene

### 4.1 iOS/Android keychain bindings (Connection Vault Phase-02)

`connection-vault.md:104` lists _"iOS / Android keychain (`Keystore` / native bindings)"_ as explicitly **Phase-02, out-of-scope-in-Phase-01**, pointing at `mvp-build-sequence.md` Phase-02 hooks item 3. The platform map (`connection-vault.md:19-24`):

- **iOS: Secure Enclave** (`:23`) — credential `ciphertext` (`connection-vault.md:35`) wrapped by a Secure-Enclave-resident key; the per-entry schema is unchanged (the Phase-01 dataclass at `tests/tier1/test_connection_vault_adapter.py` already exists), only the _backing store_ binding is new.
- **Android: Keystore** (`:24`) — hardware-backed Keystore key wraps the ciphertext.
- Both honor the **never-synced (T-007)** guarantee (`connection-vault.md:57-59`): OS keychain is device-local; after Shamir recovery the user re-authenticates each channel via fresh Grant Moments. **Pairing a phone is exactly a "fresh Grant Moment per channel" event** — which is why §1.3 step 4 enrolls the phone independently rather than syncing the desktop vault.
- Error surface reuses the existing taxonomy: `KeychainUnavailableError` (`connection-vault.md:69`, Touch ID / device-unlock gate), `SecureTextFieldUnavailableError` (`ui-platform.md:61`).

### 4.2 Flutter screen-recording detection

`ui-platform.md:21` (and the brief): _"Flutter mobile (Phase 02): detect active recording; warn before sensitive Grant Moment renders."_ The contract surface already exists — `ScreenRecordingDetectedError` (`ui-platform.md:58`): refuse the render, surface a "stop recording to continue" banner. The detection points:

- iOS: `UIScreen.isCaptured` / capture-did-change notification.
- Android: `MediaProjection` active-detection + `FLAG_SECURE` on sensitive surfaces.
- This MUST also gate the **QR-pairing render** (§1.2), not only Grant Moments — the QR is a sensitive surface (Spec gap #3). The macOS/Linux side remains advisory-only (`ui-platform.md:22,91` "no API parity ... advisory-only").

### 4.3 Clipboard auto-clear ≤30s

`connection-vault.md:63,106` + `ui-platform.md:16` — auto-clear after 30s (configurable), **Phase-02** for credential capture. iOS uses secure-text-field (bypass clipboard entirely, `ui-platform.md:15`); Android uses `Secret.Filled` (`connection-vault.md:63`). Error surface exists: `ClipboardAutoclearFailedError` (`ui-platform.md:60`). Open question already logged: should high-OPSEC users get 5s, low-OPSEC 5min (`ui-platform.md:94`).

### 4.4 6-language localization

`ui-platform.md:36-39`: Phase-01 ships en-US only; **Phase-02 adds en-GB, es-ES, de-DE, fr-FR, zh-CN, ja-JP** (6 locales). Keys at `envoy-i18n/<lang>/<ritual>.json` (`:39`). User-authored content preserved verbatim in the user's language; Envoy signed records carry exact text (`:40`). Fallback to en-US on missing key with `LocalizationKeyMissingError` advisory (`ui-platform.md:63`). The Flutter client is the primary consumer of these locale bundles; the `/todos` sizing should treat the 6-locale bundle as a translation-content deliverable distinct from the Flutter-rendering deliverable.

### 4.5 Accessibility-tree hardening (mobile)

`ui-platform.md:26-28`: Android accessibility-hint system excludes sensitive fields; iOS VoiceOver renders redacted content for sensitive fields. Enforced by `AccessibilityAPIBypassError` (`ui-platform.md:59`) — sensitive field (credential / Shamir shard / ledger entry) detected in the accessibility tree without user opt-in → refuse render. This is a WS-3 Flutter deliverable (the Phase-01 surface is desktop macOS only).

---

## Spec gaps identified (additions only — do NOT edit specs)

1. **Phase-01 ship-status overstated for 3 channels.** `channel-adapters.md:211-213` and `mvp-build-sequence.md:121` (shard 16 item 4) state WhatsApp/iMessage/Signal shipped in Phase-01 ("Yes (caveat)" / "Yes (Path B)"), but **no adapter class exists in source** (`grep -rln` empty). Per `rules/spec-accuracy.md` MUST-1 (every citation resolves against working code), these are phantom-citation ship-status claims. WS-3 should record that these three are net-new builds; the spec ship-column needs a change-log correction at the first WS-3 spec edit (per `specs-authority.md` MUST-5 first-instance update) — **flagged here, not edited.**
2. **QR-pairing handshake unspecified.** ADR-0008 (`DECISIONS.md:254-273`) authorizes QR-pairing but specifies no handshake protocol, threat class, or trust-boundary model. A new `specs/mobile-pairing.md` (or a § in `channel-adapters.md`) is needed once WS-3 implementation pins the AKE choice.
3. **Pairing is not in the threat model.** `specs/threat-model.md` (referenced by `channel-adapters.md:277`) enumerates T-008/T-018/T-070/T-080 but no device-pairing threat (`T-PAIR-*`). Screen-recording detection (`ui-platform.md:21`) is scoped to Grant Moment renders, not the QR render — the QR is an unlisted sensitive surface.
4. **Two distinct "30s" budgets risk conflation.** Clipboard auto-clear ≤30s (`connection-vault.md:63`) vs mobile cold-start <30s (brief) are unrelated; no spec states the cold-start budget at all.
5. **Pending-decision isolation primitive is named asyncio-specifically.** `channel-adapters.md:170` names `asyncio.Future`/`asyncio.Queue`; the tokio impl needs `tokio::sync::oneshot`/`mpsc`. Contract should be stated runtime-neutrally with per-runtime primitive notes for BET-6 parity.
6. **`render_grant_moment` button-less rendering unspecified for text channels.** iMessage (no inline buttons) and Group-Link Signal need a numbered-text-reply rendering of the 4 Grant Moment options (`grant-moment.md:86`); the ABC (`adapter.py:156`) assumes a render surface but the text-fallback contract isn't pinned.

---

## Open questions for /todos

1. **De-scope decision gate.** Confirm iMessage (BlueBubbles) and Signal Path A as de-scope candidates per `mvp-build-sequence.md:204`. Is the cohort/metric data (`channel-adapters.md:293` Path-B→Path-A adoption) available, or do we ship Path B + WhatsApp + Flutter first and gate the optional two on telemetry (mirroring EC-7 cohort-driven de-scope #1, `mvp-build-sequence.md:213`)?
2. **WhatsApp gateway decision is a `/todos` prerequisite.** Foundation gateway vs user-own pricing/SLA (`channel-adapters.md:292`) is a business gate that blocks WhatsApp sequencing. Resolve before WhatsApp todos are sized.
3. **AKE primitive choice.** SPAKE2 vs Noise-XX-with-QR-nonce for the pairing handshake (§1.3). Drives the FFI surface (`DECISIONS.md:272`) and the conformance-harness vectors.
4. **Relay-path cold-start budget.** The LAN path meets <30s; the relay path (2-4s AKE) is at risk. Add a measured cold-start acceptance gate (sibling of EC-7) — LAN and relay separately?
5. **WS-1 sequencing dependency.** WS-3 tokio-backed adapters cannot run under `kailash-rs-bindings` until WS-1 lands that runtime (`runtime-abstraction.md:206,231`). Sequence WS-3 adapter authoring against the _abstract_ surfaces in parallel with WS-1, integrate at the conformance harness (N1–N6) gate.
6. **Mobile screen-recording gate scope.** Extend `ScreenRecordingDetectedError` (`ui-platform.md:58`) to cover the QR-pairing render, not only Grant Moment renders (Spec gap #3).
7. **6-locale translation as a distinct deliverable.** Size the `envoy-i18n/<lang>/<ritual>.json` 6-bundle (`ui-platform.md:36-39`) separately from Flutter rendering; translation content is not engineering throughput.
8. **Phone-as-render-terminal vs primary-channel binding.** Does a paired phone become the user's _primary_ channel for H-03 high-stakes Grant Moments (`channel-adapters.md:223-225`)? If yes, the pairing flow must set `primary_only` eligibility; if no, high-stakes grants still route to the desktop.

---

## Round-1 red-team correction (R1-CRIT-1) — applied 2026-06-08

**The QR-pairing SAS MUST be derived from the handshake TRANSCRIPT, not the Trust-Vault visible secret.** An earlier framing described the SAS as "channel-bound to the visible secret." The visible secret is a FIXED, user-chosen anti-spoof token known before pairing — a MITM relay can forward it, so comparing it is decorative, not authenticating. A sound SAS is a truncated hash of the Noise-XX/SPAKE2 transcript, rendered on BOTH screens: a MITM produces a different transcript → different SAS → the user sees a mismatch and aborts. The visible secret MAY appear additionally as familiar-UX framing, but it is NOT the authenticating value. The `threat-model.md` device-pairing addition (spec gap) MUST pin the transcript-binding requirement. See `journal/0002` R1-CRIT-1 + corrected Flow 2.
