# 19 — pipx Distribution Architecture (Phase 01 MVP)

**Document role:** Wave-E final aggregation shard for /analyze. Audits the `pipx install envoy-agent` install dependency tree across all 16 wave-A/B/C/D primitive shards, confirms the Phase 01 install closure structurally excludes `kailash-ml` (per `journal/0002-DISCOVERY-upstream-readiness-improved.md` + `03-kailash-py-mvp-readiness.md` § 2.3 row #752 lightning quarantine), documents the Envoy `pyproject.toml` shape + CLI entry-point, identifies cross-OS install caveats for the OS-keychain-backed primitives (macOS Keychain / Linux Secret Service / Windows Credential Locker), and stubs the Phase 02 distribution-migration plan. Cites frozen specs and ADR-0001; never paraphrases.

**Date:** 2026-05-03 (shard 19 of /analyze; Wave E).
**Status:** DRAFT — load-bearing for shard 20 (`02-plans/03-package-skeleton.md`) and shards 23–24 (red team rounds — verifying that `pipx install envoy-agent` from a clean macOS / Linux / Windows produces a working `envoy init` first-run).
**Owning shard:** 19 (per `01-shard-plan.md` § 2 row 19 + § 5 wave E).
**Exit criteria served:** Cross-cutting structural prerequisite per `02-mvp-objectives.md` § 3 row 1 ("`pipx install envoy-agent` distribution — EC-1 requires installation; pipx is the Phase 01 distribution per ADR-0001 phase-migration"). Indirectly serves EC-1 (first-time-user onboarding requires a working install) and EC-7 (8-channel onboarding requires the per-channel transport extras propagate through this shard's audit).
**Discipline:** Cite, do not paraphrase frozen specs. Per `journal/0001`, the question is "given these primitives are deep-dived, what is the install-closure surface?" — NOT "should we re-evaluate distribution strategy?". Per `rules/specs-authority.md` Rule 4 + Rule 5b (no spec edits at this shard).

**Capacity check:** 1 deliverable (`pyproject.toml` shape for `envoy-agent`), 16 primitive shards aggregated for transitive-dep enumeration, ~6 invariants tracked (Apache 2.0 / MIT / BSD-3-Clause license compatibility; `kailash-ml` exclusion; cross-OS keyring backend availability; first-run `envoy init` bootstrap; license / NOTICES file aggregation; `kailash-ml` re-introduction risk via future opt-in extras). Within `rules/autonomous-execution.md` budget — most of the work is enumeration over already-completed shards 4–18, not novel reasoning.

---

## 1. Source spec citation

Frozen specs the Phase 01 distribution implements against (cited; not edited):

- **`specs/distribution.md` § Phase 01 distribution (lines 13–18)** — verbatim:
  - "**Surface:** `pipx install envoy-agent` (PyPI). kailash-py sole runtime."
  - "**Installer:** `envoy init` bootstraps Trust Vault + Genesis + Boundary Conversation."
  - "**Offline first-run:** local model bundled (Ollama/llama.cpp/MLX)."
- **`specs/distribution.md` § Phase 02 distribution (lines 20–25)** — Phase 02 migration targets cited only for the stub in § 8 below: macOS `curl|sh` + `brew install envoy-agent`; Linux same curl + `apt`/`dnf` Phase 04; Windows `winget install envoy-agent`; MSI Phase 04; Rust `cargo install envoy-agent`; Mobile App Store + Play Store (Flutter).
- **`specs/distribution.md` § Installer security (lines 87–88)** — "Refuses install if Trust Vault dir world-readable." Phase 01 enforcement at `envoy init` first-run; not a `pip` / `pipx` concern but a post-install bootstrap concern.
- **`specs/distribution.md` § Error taxonomy (lines 91–104)** — 11 typed errors. Phase 01 surfaces these only at `envoy init` time and at runtime; pipx itself does not surface most of them (pipx is a thin install dispatcher; the Foundation N=3 mirror + signing-key + reproducible-build + revocation-list machinery is Phase 02 distribution, NOT Phase 01).
- **`specs/distribution.md` § Test location (lines 117–128)** — Phase 01-relevant entry: `tests/integration/test_pipx_install_phase01.py` (Tier 2). Other rows are Phase 02 / Phase 03.
- **`specs/distribution.md` § Cross-references (lines 106–114)** — `runtime-abstraction.md` (runtime picker — Phase 02), `trust-vault.md` (Trust Vault initialization), `shamir-recovery.md` (first-run Shamir), `boundary-conversation.md` (first-run ritual), `foundation-ops.md` (mirror coordination — Phase 02), `network-security.md`, `threat-model.md`.
- **`DECISIONS.md` § ADR-0001 — Phase migration table row "01 MVP" (line 64)** — verbatim: "`kailash-py` runtime only; abstract interface defined but Rust binding not yet wired (lands Phase 02)" — distribution: "`pipx install envoy-agent`" — notes: "Prove the UX; Rust binding integration lands in Phase 02".

Cross-spec citations (read-only at this shard, per shard-2/3 deps from §3 of `01-shard-plan.md`):

- `02-mvp-objectives.md` § 3 (lines 130–142) — 7 cross-cutting deliverables; row 1 is `pipx install envoy-agent` and binds this shard.
- `03-kailash-py-mvp-readiness.md` § 2.3 row #752 — "`lightning` package QUARANTINED on PyPI — kailash-ml installs broken. Phase 01 install path (`pipx install envoy-agent`, shard 19) MUST NOT transitively depend on `kailash-ml` until quarantine resolved."
- `03-kailash-py-mvp-readiness.md` § 3 row 16 — "pipx distribution: VERIFY: shard 19 must confirm `kailash-ml` is not in transitive deps (or excluded if pulled in)."
- `journal/0002-DISCOVERY-upstream-readiness-improved.md` "What it does NOT change" item 3 — closed-status ≠ landed-feature; this shard re-snapshots the upstream `pyproject.toml` directly (per § 5 protocol of the readiness doc).

---

## 2. Verified upstream state — `pip install kailash` Phase 01 baseline

Per `03-kailash-py-mvp-readiness.md` § 5 verification protocol: this shard executed direct file inspection of the upstream `~/repos/loom/kailash-py/pyproject.toml` (the canonical source for the `kailash` PyPI package's dep tree). Citation by line number, not paraphrase.

### 2.1 `kailash` core dependencies (`pyproject.toml` lines 25–76)

The `[project] dependencies` array (29 packages; all required for `pip install kailash`):

| Package                                 | Min version      | Phase 01 consumer (which primitive)                                                                                          | License                               |
| --------------------------------------- | ---------------- | ---------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| `jsonschema`                            | ≥4.24.0          | Envelope compiler (shard 4); Trust store record schemas (shard 5); Ledger schema validation (shard 6)                        | MIT                                   |
| `networkx`                              | ≥2.7             | Workflow graph primitives consumed by Boundary Conversation L3 plan-DAG (shard 8)                                            | BSD-3-Clause                          |
| `pydantic`                              | ≥2.6             | Frozen dataclasses across every shard (4–18); the canonical model surface                                                    | MIT                                   |
| `pyyaml`                                | ≥6.0             | Conformance vector loaders (Phase 02 concern); Phase 01 indirect dep                                                         | MIT                                   |
| `filelock`                              | ≥3.0             | SQLite-backed Trust store / Ledger / Posture store concurrency primitive                                                     | Public Domain (Unlicense)             |
| `pynacl`                                | ≥1.5             | Trust store Ed25519 signing (shard 5); Genesis Record signing                                                                | Apache 2.0                            |
| `cryptography`                          | ≥41.0            | AES-GCM Trust Vault encryption (shard 5); Connection Vault has no direct dep but the primitive uses OS keychain (shard 14)   | Apache 2.0 OR BSD-3-Clause            |
| `PyJWT`                                 | ≥2.8             | Trust store / Connection Vault JWT iss-claim hardening (per #635/#636/#625 closures, `03-kailash-py-mvp-readiness.md` § 2.2) | MIT                                   |
| `aiohttp`, `aiohttp-cors`               | ≥3.12.4 / ≥0.7.0 | Channel adapters (shard 16) — Web channel + webhook receive paths via Nexus                                                  | Apache 2.0                            |
| `fastapi`                               | ≥0.115.12        | Nexus core (shard 16 web channel + Daily Digest preview SSE per shard 11)                                                    | MIT                                   |
| `httpx`                                 | ≥0.25.0          | Model adapter outbound HTTP (shard 13) — Anthropic, OpenAI, DeepSeek, custom OpenAI-compatible endpoints                     | BSD-3-Clause                          |
| `uvicorn[standard]`                     | ≥0.31.0          | Nexus ASGI server (shard 16 web channel)                                                                                     | BSD-3-Clause                          |
| `click`                                 | ≥8.0             | CLI primitives (shard 16 CLI channel + every `envoy <subcommand>` entry point)                                               | BSD-3-Clause                          |
| `requests`                              | ≥2.32.3          | Sync HTTP — webhook signers (shard 16 Telegram/Slack/Discord/WhatsApp signers per #687)                                      | Apache 2.0                            |
| `aiosqlite`                             | ≥0.19.0          | Trust store + Ledger + Posture store + Budget store (shards 5, 6, 9, 12) — Phase 01 single-machine SQLite                    | BSD-3-Clause-style                    |
| `sqlalchemy`                            | ≥2.0.0           | DataFlow ORM (Phase 01 transaction context per #707/#711); SQLite-only                                                       | MIT                                   |
| `asyncpg`, `aiomysql`                   | (latest)         | DataFlow Postgres / MySQL drivers — Phase 01 NOT used (SQLite only); ship as transitive but unused                           | Apache 2.0 / MIT                      |
| `aiofiles`                              | ≥24.1.0          | Boundary Conversation transcript / Ledger export I/O                                                                         | Apache 2.0                            |
| `bcrypt`, `pyotp`, `qrcode`, `msal`     | (latest)         | Auth primitives — Phase 01 indirect (channel SSO not in MVP scope)                                                           | Apache 2.0 / MIT / BSD-3-Clause / MIT |
| `prometheus-client`                     | ≥0.22.1          | Observability counters (shard 11 Daily Digest delivery counters; shard 12 Budget tracker threshold-fired counters)           | Apache 2.0                            |
| `psutil`                                | ≥7.0.0           | Runtime introspection (shard 18 abstract interface stub)                                                                     | BSD-3-Clause                          |
| `redis`                                 | ≥6.2.0           | Distributed cache — Phase 01 NOT used (single-machine); transitive but unused                                                | MIT                                   |
| `mcp[cli]`                              | ≥1.23.0,<2.0     | MCP channel surface — Phase 01 NOT shipped (per `00-inheritance-from-phase-00.md` § 6); transitive                           | MIT                                   |
| `apscheduler`                           | ≥3.10            | Daily Digest scheduling (shard 11 § 3.1 — `DailyDigestService` composes `apscheduler.AsyncIOScheduler`)                      | MIT                                   |
| `opentelemetry-{api,sdk,exporter-otlp}` | ≥1.20            | Tracing primitives across shards 5/6/8/10/11/12                                                                              | Apache 2.0                            |
| `numpy`, `pandas`                       | ≥1.24 / ≥2.0     | Authorship Score numeric (shard 9) — pandas is overkill for Phase 01 N=1 cohort but ships transitively                       | BSD-3-Clause                          |

**Net:** 29 transitive packages from `kailash` core. **All licenses are Apache 2.0 / MIT / BSD-3-Clause / Unlicense — fully compatible with each other, with the Foundation's CC BY 4.0 spec licensing, and with the Envoy Apache 2.0 application-layer license per ADR-0001 § "What each shipped package contains" line 53.**

### 2.2 `kailash[shamir]` extra (`pyproject.toml` lines 102–108)

Verbatim (lines 106–108):

```toml
shamir = [
    "shamir-mnemonic>=0.3",
]
```

Phase 01 propagation: shard 15 § 2.2 disposition (b) confirmed Envoy bypasses the gated `back_up_vault_key` and calls `kailash.trust.vault.shamir.generate(...)` directly with master-key from shard 5. The wrapper's lazy-import (`_require_shamir_mnemonic` per `~/repos/loom/kailash-py/src/kailash/trust/vault/shamir.py` lines 122–136) raises `RuntimeError` with install-hint if `shamir-mnemonic` is absent. Therefore Envoy's Phase 01 install MUST pull `shamir-mnemonic` — by declaring `kailash[shamir]>=2.13.4` instead of bare `kailash>=2.13.4` in Envoy's `pyproject.toml` (per § 3 below).

`shamir-mnemonic` license: MIT (per PyPI metadata + `02-mvp-objectives.md` EC-5 acceptance gate (c) — cross-tool interop with `python-shamir-mnemonic`). Foundation crypto-audit caveat noted in shard 15 § 2.3 — release-gate concern at `specs/shamir-recovery.md` line 15 "Phase 00 crypto audit required" + line 54 `CryptoLibAuditMissingError`. The audit gate does NOT change the install-closure shape; it gates production release, not pipx install.

### 2.3 **`kailash-ml` exclusion — VERIFIED ABSENT from Phase 01 install closure**

The `journal/0002-DISCOVERY-upstream-readiness-improved.md` "What it does NOT change" item 3 + `03-kailash-py-mvp-readiness.md` § 2.3 row #752 mandate verification that `kailash-ml` is NOT pulled transitively by `pip install kailash` or `pip install kailash[shamir]`.

**Verification by direct file read:**

The `~/repos/loom/kailash-py/pyproject.toml` `[project] dependencies` array (lines 25–76, 29 packages) does NOT contain `kailash-ml`. `kailash-ml` appears only in TWO locations:

1. `pyproject.toml` lines 95–97 (`[project.optional-dependencies] ml`):
   ```toml
   ml = [
       "kailash-ml>=1.1.0",
   ]
   ```
2. `pyproject.toml` lines 170–179 (`[project.optional-dependencies] all`):
   ```toml
   all = [
       ...
       "kailash-ml[all]>=0.11.1",
       ...
   ]
   ```

**Both are opt-in extras**, NOT core dependencies. Therefore:

- `pip install kailash` → does NOT pull `kailash-ml`. Confirmed.
- `pip install kailash[shamir]` → pulls `shamir-mnemonic>=0.3` only. Does NOT pull `kailash-ml`. Confirmed.
- `pip install kailash[ml]` → would pull `kailash-ml`. **Phase 01 envoy-agent MUST NOT use this extra.**
- `pip install kailash[all]` → would pull `kailash-ml[all]`. **Phase 01 envoy-agent MUST NOT use this extra.**

**Structural defense:** Envoy's `pyproject.toml` (per § 3 below) declares `"kailash[shamir]>=2.13.4"` — the closed extra set. The choice of declaring `kailash[shamir]` and NOT `kailash[all]` is the single-line defense against accidental `kailash-ml` re-introduction. The shard-19 audit confirms this is sufficient at the 2026-05-03 baseline; future Envoy `pyproject.toml` edits MUST re-verify against this same protocol.

**Re-introduction risk register (LOW — for shard 20 plan reference):** If a future Envoy primitive (Phase 02+) needs ML inference (e.g. on-device embedding for goal-drift classifier per `specs/model-adapter.md` § Response filter line 39 item 3), and the implementing shard reaches for `kailash[ml]`, the `lightning` quarantine (#752) MUST be re-checked. Until quarantine resolves, on-device ML belongs to a separate non-`kailash-ml`-rooted dependency (e.g. direct `sentence-transformers` or `onnxruntime`) routed via shard 13 model adapter, NOT via `kailash[ml]`. This is not a Phase 01 concern (no on-device ML in MVP).

### 2.4 Future sub-package extras NOT used in Phase 01

Per `pyproject.toml` lines 78–122, these extras exist upstream but are NOT pulled by Phase 01:

| Extra                          | Pulls                                           | Phase 01 disposition                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------ | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dataflow`                     | `kailash-dataflow>=2.0.12`                      | NOT pulled — Phase 01 SQLite primitives use `aiosqlite` directly via the upstream `kailash` core (DataFlow primitives appear via `kailash.dataflow` namespace already; the optional extra would add `psycopg2`-backed Postgres which Phase 01 does not need per `03-kailash-py-mvp-readiness.md` § 2.3 row #753)                                                                                                                                                              |
| `nexus`                        | `kailash-nexus>=2.1.1`                          | **MAY be pulled** depending on whether Nexus webhook/websocket transport packages are vendored as part of `kailash` core or split off. Per shard 16 § 2.1, `nexus.transports.webhook.WebhookTransport` lives at `~/repos/loom/kailash-py/packages/kailash-nexus/src/...` — this is the kailash-nexus sub-package. Envoy MUST declare `kailash[nexus]>=2.13.4` to ensure the webhook + websocket primitives propagate. **Update to § 3 dep table required** — see § 3.2 below. |
| `kaizen`                       | `kailash-kaizen>=2.7.5`, `kaizen-agents>=0.9.3` | **MUST be pulled** — shard 13 model adapter consumes `kaizen.llm.deployment.LlmDeployment`; shard 8 Boundary Conversation consumes `kaizen.BaseAgent` + L3 plan-DAG. Declare `kailash[kaizen]>=2.13.4`.                                                                                                                                                                                                                                                                       |
| `pact`                         | `kailash-pact>=0.8.2`                           | NOT pulled — Phase 01 does not ship PACT MCP governance per `00-inheritance-from-phase-00.md` § 6 (MCP governance is a Phase 02 concern; ISS-19/ISS-21 closures track it).                                                                                                                                                                                                                                                                                                    |
| `align`                        | `kailash-align>=0.3.2`                          | NOT pulled — LLM fine-tuning / LoRA is post-Phase-04.                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `vault`                        | `hvac>=2.1.0`                                   | NOT pulled — Phase 01 Connection Vault uses OS keychain ONLY per shard 14 § 2.2. HashiCorp Vault is enterprise / cloud secret backend, deferred.                                                                                                                                                                                                                                                                                                                              |
| `aws-secrets`, `azure-secrets` | (cloud SDKs)                                    | NOT pulled — same reasoning as `vault`.                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `ldap`                         | `ldap3>=2.9`                                    | NOT pulled — Phase 01 single-principal; SSO/LDAP is multi-principal Phase 03.                                                                                                                                                                                                                                                                                                                                                                                                 |

**Net Phase 01 declaration (preliminary):** `kailash[shamir,nexus,kaizen]>=2.13.4`. The full transitive closure under this declaration is the union of (§ 2.1 core 29 packages) + `shamir-mnemonic` + the kailash-nexus / kailash-kaizen sub-packages and their own deps.

---

## 3. Envoy-new install layout

### 3.1 `envoy-agent` PyPI package shape

The Phase 01 Envoy-new code ships as ONE PyPI package: `envoy-agent`. Internal Python module name: `envoy` (avoiding the `envoy-agent` hyphen at the import line; per Python packaging convention).

**Provisional `pyproject.toml`** (the spec-bound shape; concrete values land at shard 20 `02-plans/03-package-skeleton.md`):

```toml
[build-system]
requires = ["setuptools>=42", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "envoy-agent"
version = "0.1.0"  # Phase 01 MVP
description = "Foundation-stewarded pure-Python pip-install agent implementing Terrene Foundation's open standards (CARE / EATP / CO / PACT)."
authors = [
    {name = "Terrene Foundation", email = "info@terrene.foundation"},
]
readme = "README.md"
license = {text = "Apache-2.0"}
requires-python = ">=3.11"  # matches kailash-py upstream floor
classifiers = [
    "Development Status :: 4 - Beta",  # Phase 01 MVP
    "Intended Audience :: End Users/Desktop",
    "License :: OSI Approved :: Apache Software License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Communications",
    "Topic :: Security :: Cryptography",
]
dependencies = [
    # Foundation runtime — Phase 01 wires kailash-py only per ADR-0001 phase
    # migration table row "01 MVP" (DECISIONS.md line 64).
    # Closed-extra set: shamir (shard 15), nexus (shard 16 webhook/websocket
    # transports), kaizen (shards 8 + 13).
    # CRITICALLY: NOT kailash[ml] — see shard 19 § 2.3 (lightning quarantine,
    # journal/0002, readiness § 2.3 row #752).
    "kailash[shamir,nexus,kaizen]>=2.13.4",

    # OS keychain wrapper — shard 14 § 2.2.
    # MIT license; cross-platform (macOS Keychain, Windows Credential Locker,
    # Linux Secret Service via SecretStorage / D-Bus).
    "keyring>=24.0",

    # .env file loader — rules/env-models.md Absolute Directive 2.
    "python-dotenv>=1.0",

    # Phase 01 channel-adapter SDKs — shard 16 § 2.3 item 1 enumerates 6
    # social adapters. Per-vendor SDKs per § 3.3 below.
    "python-telegram-bot>=21.0",     # Telegram (shard 16)
    "slack-sdk>=3.27",               # Slack (shard 16)
    "discord.py>=2.3",               # Discord (shard 16)
    # WhatsApp: NO official Python SDK; Phase 01 uses raw HTTP via httpx
    #   (already pulled transitively by kailash[nexus]).
    # iMessage / BlueBubbles: HTTP REST against user-owned Mac BlueBubbles
    #   server; uses httpx — no per-vendor SDK.
    # Signal Path B: signal-cli REST wrapper; uses httpx — no per-vendor SDK
    #   per shard 16 § 2.3.
]

[project.optional-dependencies]
# Reserved Phase 02+ extras; declared shape only, NOT pulled in Phase 01.
rust = [
    # Phase 02: kailash-rs-bindings; first-run picker per ADR-0001.
    # "kailash-rs-bindings>=X.Y.Z",
]
mobile = [
    # Phase 04 mobile clients (Flutter — out of scope for Python pyproject).
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=1.0",
    "pytest-xdist>=3.6",
    "pytest-timeout>=2.3",
    "ruff>=0.11",
    "black>=25.1",
    "mypy>=1.0",
]

[project.scripts]
# Single CLI entry point — see § 3.4 for subcommand structure.
envoy = "envoy.cli:main"

[project.urls]
"Homepage" = "https://terrene.foundation/envoy"
"Repository" = "https://github.com/terrene-foundation/envoy-agent"
"Bug Tracker" = "https://github.com/terrene-foundation/envoy-agent/issues"
"Documentation" = "https://terrene.dev/envoy"
"License" = "https://github.com/terrene-foundation/envoy-agent/blob/main/LICENSE"

[tool.setuptools]
package-dir = {"" = "src"}
```

**Notes on the shape (each justified by a shard, not invented here):**

- **`name = "envoy-agent"`** — per `specs/distribution.md` line 17 ("`pipx install envoy-agent`") + ADR-0001 phase-migration row "01 MVP" line 64. Codename per `00-inheritance-from-phase-00.md` § 6 ("Phase 01 ships under codename `envoy` / `envoy-agent`").
- **`license = {text = "Apache-2.0"}`** — per ADR-0001 "What each shipped package contains" line 53 ("`envoy` (Apache 2.0)") and the Foundation independence rule at `rules/independence.md` § "License Accuracy". Envoy is OSS itself — distinct from the proprietary-product framing in the GLOBAL `independence.md` (which applies to a hypothetical proprietary commercial product, not Envoy).
- **`requires-python = ">=3.11"`** — matches `~/repos/loom/kailash-py/pyproject.toml` line 14 floor.
- **No `kailash[all]`** — § 2.3 above; the closed-extra set defends against `kailash-ml` re-introduction.
- **`keyring>=24.0`** — shard 14 § 2.2 is the canonical citation; license MIT; cross-platform per § 4 below.
- **`python-dotenv>=1.0`** — `rules/env-models.md` Absolute Directive 2 mandates `.env` is the single source of truth; `dotenv` loads it. Shard 14 § 3.1 item 9 ("`.env` first-run import path") is the integration point.
- **Channel SDKs as direct deps, NOT extras** — per shard 16 § 3.1 the 6 social-channel adapters are Phase 01 EC-7 critical path. Declaring them as direct deps (not as `envoy-agent[channels]` extra) ensures the install closure is single-command (`pipx install envoy-agent`) per `specs/distribution.md` line 17. The de-scope #1 disposition (shard 16: ship 8, fall back to 5) is a runtime / cohort-driven concern, not an install-time concern.

### 3.2 Aggregated Phase 01 transitive dependency table

This is the single normative table; shard 20 `02-plans/03-package-skeleton.md` MUST consume this directly without re-derivation.

| Source                                                                              | Provider primitive (shard)                                                                           | License                                                                             | Phase 01 install requirement        |
| ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ----------------------------------- |
| `kailash` (core 29 deps per § 2.1)                                                  | All shards via the core                                                                              | Apache 2.0 (umbrella) — transitive deps Apache 2.0 / MIT / BSD-3-Clause / Unlicense | required                            |
| `shamir-mnemonic>=0.3` (via `kailash[shamir]`)                                      | Shamir 3-of-5 (shard 15)                                                                             | MIT                                                                                 | required                            |
| `kailash-nexus>=2.1.1` (via `kailash[nexus]`)                                       | Channel adapters webhook / websocket transport (shard 16)                                            | Apache 2.0                                                                          | required                            |
| `kailash-kaizen>=2.7.5` + `kaizen-agents>=0.9.3` (via `kailash[kaizen]`)            | Boundary Conversation (shard 8); Model adapter (shard 13); Daily Digest L3 plan-DAG (shard 11)       | Apache 2.0                                                                          | required                            |
| `keyring>=24.0`                                                                     | Connection Vault (shard 14)                                                                          | MIT                                                                                 | required                            |
| `python-dotenv>=1.0`                                                                | Connection Vault `.env` import (shard 14 § 3.1 item 9); root `conftest.py` per `rules/env-models.md` | BSD-3-Clause                                                                        | required                            |
| `python-telegram-bot>=21.0`                                                         | Channel adapters Telegram (shard 16)                                                                 | LGPL-3.0-OR-LATER                                                                   | required (see § 3.3 license caveat) |
| `slack-sdk>=3.27`                                                                   | Channel adapters Slack (shard 16)                                                                    | MIT                                                                                 | required                            |
| `discord.py>=2.3`                                                                   | Channel adapters Discord (shard 16)                                                                  | MIT                                                                                 | required                            |
| (no per-vendor SDK)                                                                 | Channel adapters WhatsApp / iMessage / Signal — uses transitive `httpx`                              | n/a                                                                                 | required (transitive only)          |
| `kailash-ml`                                                                        | (none — Phase 01 EXCLUDED)                                                                           | n/a                                                                                 | **NOT pulled — see § 2.3**          |
| `kailash-pact`, `kailash-align`, `hvac`, `boto3`, `azure-keyvault-secrets`, `ldap3` | (Phase 02+ extras)                                                                                   | (various)                                                                           | NOT pulled                          |

### 3.3 License compatibility audit

Apache 2.0 + MIT + BSD-3-Clause + Unlicense are mutually compatible with Apache 2.0 application code. **Anomaly: `python-telegram-bot` is LGPL-3.0-or-later** (verify: PyPI `python-telegram-bot` reports `Lesser General Public License v3 or later (LGPLv3+)`). LGPL-3.0+ is compatible with Apache 2.0 application use as long as Envoy:

1. Dynamically links (Python imports satisfy this automatically — no static linkage).
2. Permits the user to relink against a modified `python-telegram-bot` (a re-pip-install satisfies this — pipx is the relink mechanism).
3. Includes the LGPL-3.0+ license text in the Envoy `NOTICES` file shipped alongside `LICENSE`.

**Action item for shard 20:** the Envoy `NOTICES` aggregation (per `00-inheritance-from-phase-00.md` § 4 row "legal/03-license-compatibility-statement.md" inheritance) MUST list:

- `python-telegram-bot` (LGPL-3.0+)
- `keyring` (MIT)
- `shamir-mnemonic` (MIT)
- `python-dotenv` (BSD-3-Clause)
- `slack-sdk` (MIT)
- `discord.py` (MIT)
- All 29 transitive `kailash` core packages with their respective licenses

LGPL-3.0+ is the only non-trivial license in the closure. **Disposition recommendation:** keep `python-telegram-bot` as the Telegram SDK because (a) it is the canonical Python Telegram client (largest community, longest maintenance history), (b) the LGPL constraints are satisfied by pipx's dynamic-link semantics, (c) the alternative — `pyTelegramBotAPI` (MIT) — is also viable but has smaller community; the LGPL compatibility check is a one-time NOTICES aggregation cost, not a recurring constraint. Shard 20 may revisit this trade-off; this shard's recommendation is to ship LGPL `python-telegram-bot` with full NOTICES disclosure.

### 3.4 CLI entry-point structure

Single `envoy` console-script per `[project.scripts]` line. Subcommand structure (defined in `envoy.cli` module; the shard does NOT re-derive subcommand semantics — those are bound by the per-primitive shards):

| Subcommand                               | Owning shard                                                                            | What it does                                                                                                                                                                                                                                                                                      |
| ---------------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- | --------------------------------------------------------------------------------------------------- |
| `envoy init`                             | 19 (this shard's bootstrap concern); 5 (Trust store seed); 8 (Boundary Conversation S0) | First-run bootstrap. Per `specs/distribution.md` line 17 ("`envoy init` bootstraps Trust Vault + Genesis + Boundary Conversation").                                                                                                                                                               |
| `envoy chat`                             | 8 (Boundary Conversation)                                                               | Resume / start interactive Boundary Conversation.                                                                                                                                                                                                                                                 |
| `envoy ledger export`                    | 6 (Envoy Ledger)                                                                        | Export hash-chained Ledger to a portable file (EC-4 acceptance gate).                                                                                                                                                                                                                             |
| `envoy ledger verify`                    | 7 (Independent verifier)                                                                | **NOT shipped in `envoy-agent`** — verifier is in separate repo per shard 7 + EC-9 acceptance gate ("source-isolated by design"). The `envoy ledger export` output is consumed by the separate `envoy-ledger-verifier` repo's CLI.                                                                |
| `envoy shamir backup`                    | 15 (Shamir 3-of-5)                                                                      | Run the 3-of-5 backup ritual (EC-5 acceptance gate (b) — Boundary Conversation pauses for backup at least once).                                                                                                                                                                                  |
| `envoy shamir recover`                   | 15 (Shamir 3-of-5)                                                                      | Reconstruct from any 3 of 5 cards (EC-5 acceptance gate (a)).                                                                                                                                                                                                                                     |
| `envoy digest today`                     | 11 (Daily Digest)                                                                       | On-demand digest for current local-day — per `specs/daily-digest.md` § Channel-adaptive rendering line 33 ("CLI on `envoy digest today`").                                                                                                                                                        |
| `envoy budget status`                    | 12 (Budget tracker)                                                                     | Microdollar spend across the 5 ceiling windows.                                                                                                                                                                                                                                                   |
| `envoy channel <add                      | list                                                                                    | remove>`                                                                                                                                                                                                                                                                                          | 16 (Channel adapters) | Per-channel onboarding subcommands (Telegram bot token registration; Slack OAuth completion; etc.). |
| `envoy posture`                          | 9 (Authorship Score)                                                                    | Display current posture + Authorship Score (BET-12 measurement hook).                                                                                                                                                                                                                             |
| `envoy upgrade` (stub)                   | (Phase 02)                                                                              | Per `specs/distribution.md` § Upgrade / Rollback / Uninstall (Phase 02). Phase 01 stub raises `NotImplementedError("Phase 02 distribution surface; use `pipx upgrade envoy-agent` for now.")` per `rules/zero-tolerance.md` Rule 2 (one stub permitted with issue link — file as Phase 02 issue). |
| `envoy uninstall --destroy-vault` (stub) | (Phase 02)                                                                              | Same disposition.                                                                                                                                                                                                                                                                                 |
| `envoy heartbeat` (DE-SCOPED)            | 17 (DE-SCOPED to Phase 02)                                                              | Foundation Health Heartbeat — per shard 17 disposition `00-inheritance-from-phase-00.md` § 6 invariant; ~100 LOC stubs only in Phase 01.                                                                                                                                                          |

Per `rules/orphan-detection.md` MUST Rule 1, every advertised CLI subcommand MUST have at least one Tier 2 wiring test that exercises it through `envoy` (not through internal Python imports). This is enforced at shard 6 / Tier 2 surface for Ledger; shard 16 for channel adapters; etc. — each owning shard inherits the Tier 2 wiring obligation.

---

## 4. Class structure sketch — n/a

This shard is install-architecture, not class-architecture. The class structures live at:

- `pyproject.toml` shape — § 3.1 above.
- `envoy.cli` subcommand registry — Click groups; one module per subcommand domain (`envoy.cli.init`, `envoy.cli.chat`, `envoy.cli.ledger`, `envoy.cli.shamir`, `envoy.cli.digest`, `envoy.cli.budget`, `envoy.cli.channel`, `envoy.cli.posture`).
- The `envoy init` bootstrap class composition is delegated to shard 8 § 3 (Boundary Conversation S0 entry) + shard 5 § 3 (Trust store seed) + shard 14 § 3 (`.env` import to Connection Vault).

No new class surface is introduced at shard 19; the shard's contribution is the install closure + the entry-point manifest.

---

## 5. Integration points

### 5.1 Every primitive's third-party dep flows through this shard's audit

This shard is the aggregation point for shards 4–18. Each per-primitive shard cited a specific third-party dependency or a `kailash`-extra; shard 19 enumerated them in § 3.2 above. Forward integration:

- Shard 20 (`02-plans/03-package-skeleton.md`) — consumes § 3.1 (`pyproject.toml` shape) + § 3.2 (transitive dep table) directly. No re-derivation.
- Shards 23–24 (red team rounds) — verify that the install closure produces a working `pipx install envoy-agent` on macOS, Linux, Windows AND that `pip show envoy-agent` does NOT list `kailash-ml` in its dep tree. Mechanical grep — `pip show -f envoy-agent | grep -i ml` — is the structural defense per `rules/agents.md` § "MUST: Reviewer Prompts Include Mechanical AST/Grep Sweep".
- Shard 25 (closure) — `01-analysis/_index.md` + `02-plans/_index.md` indexes this shard as the install-architecture authority.

### 5.2 Install-time `.env` scaffolding (per `rules/env-models.md` Absolute Directive 2)

`envoy init` first-run creates an `.env` file at the user's Envoy data directory (per `specs/trust-vault.md` § Storage location — `~/.envoy/` on macOS/Linux, `%APPDATA%\envoy\` on Windows). The `.env` template includes commented placeholders for:

```dotenv
# Model adapter (shard 13) — pick at install via `envoy init` per ADR-0006.
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=
# DEEPSEEK_API_KEY=
# OPENAI_COMPATIBLE_BASE_URL=

# Channel adapters (shard 16) — populated by `envoy channel add` subcommand.
# TELEGRAM_BOT_TOKEN=
# SLACK_BOT_TOKEN=
# DISCORD_BOT_TOKEN=

# Foundation Health Heartbeat (shard 17 — DE-SCOPED in Phase 01).
# FOUNDATION_HEARTBEAT_ENDPOINT=
```

Per `rules/security.md` § "No Hardcoded Secrets" + § "No .env in Git", the `.env` file MUST be created with mode `0600` (user-read-only) and `~/.envoy/.gitignore` MUST include `.env` automatically. The `envoy init` post-create check enforces this (per `specs/distribution.md` § Installer security line 88: "Refuses install if Trust Vault dir world-readable" — adapted to `.env` permission check).

After first-run, `.env` migrates into the Connection Vault per shard 14 § 3.1 item 9. The post-migration `.env` is left in place for compatibility (some users prefer file-based config) but the Connection Vault becomes the source of truth; if both differ, the Connection Vault wins.

### 5.3 First-run CLI bootstrap (`envoy init`)

The bootstrap sequence (shard 19's normative shape; per-step semantics owned by upstream shards):

1. **Prerequisite check** — `python --version >= 3.11`; `pipx --version` available; `~/.envoy/` writable; OS keychain backend available (`keyring.get_keyring()` returns a non-`Null` backend per shard 14 § 2.2). Failures surface plain-language errors per `rules/communication.md`.
2. **Trust Vault seed** — shard 5 § 3 (`TrustStoreAdapter.seed_genesis(...)` produces the Genesis Record).
3. **`.env` scaffolding** — § 5.2 above.
4. **Model picker** — shard 13 + ADR-0006. Phase 01 ships local-default available (`Ollama`/`llama.cpp`/`MLX` per `specs/distribution.md` line 18 "Offline first-run: local model bundled"). User picks at install. **Phase 01 caveat:** the local model is NOT bundled in the `pipx` wheel (pipx wheels exclude binary artifacts >100 MB by default; the local model bundle is downloaded on first `envoy init` if user picks local — adding ~4 GB for a Llama-3 8B GGUF on first-run; this is consistent with `specs/distribution.md` § Phase 02 first-run flow line 45 but Phase 01's offline-first claim weakens to "offline-CAPABLE if local model already present, online-required for fresh first-run" — see § 7 ambiguity).
5. **Boundary Conversation S0** — shard 8 § 3 enters interactive S0→S10 ritual on the user's primary channel (CLI default for first-run; user can switch primary later per shard 16 H-03 binding).
6. **Shamir backup ritual** — shard 15 § 3.1; pauses at S8 of the Boundary Conversation (per EC-5 acceptance gate (b)).
7. **Channel onboarding** — shard 16 + EC-7. User is offered to wire up to 8 channels (CLI is already wired by virtue of `envoy init` being a CLI command; the other 7 are opt-in).
8. **Posture seed** — shard 9 § 3 sets initial posture to `PSEUDO` and Authorship Score to 0.

### 5.4 `pipx` semantics — what's free, what's earned

`pipx` provides per-application virtual environments and isolated dependency closures. For Phase 01 this gets:

- **Free** (no Envoy work): isolated venv per Envoy install; no system Python pollution; clean uninstall via `pipx uninstall envoy-agent`; per-user install (no root); upgrade via `pipx upgrade envoy-agent`.
- **Earned** (Envoy must implement at `envoy init`): Trust Vault initialization; first-run model bundle download; channel adapter onboarding; Shamir backup ritual; `.env` scaffolding.
- **Phase 02 (NOT in pipx scope)**: `specs/distribution.md` § N=3 mirror verification (lines 28–34); § Binary signing key rotation (line 36); § Reproducible-build verification stream (line 40); § Jurisdictional advisories (lines 53–57). These are all curl|sh / brew / winget / cargo install installer concerns, not pipx concerns. Phase 01 is intentionally limited to the PyPI surface. **The N=3 mirror promise + signing-key rotation + reproducible-build are Phase 02 distribution security primitives, not Phase 01.**

---

## 6. Tier 2 / Tier 3 test surface

### 6.1 Tier 2 — clean-system pipx install (per `specs/distribution.md` line 118)

`tests/integration/test_pipx_install_phase01.py` is named in `specs/distribution.md` line 118; this shard binds its scope:

1. **Per-OS install matrix** — clean macOS arm64 + macOS x86_64 + Linux x86_64 (Ubuntu 22.04 + Fedora 38 minimum) + Windows 11 x86_64. CI runners with no prior Envoy install. `pipx install envoy-agent` exits 0; `envoy --version` reports `0.1.0` (or whatever Phase 01 version ships).
2. **Dependency exclusion verification** — `pip show -f envoy-agent | grep -i 'kailash-ml\|lightning'` returns empty (per § 2.3 verification protocol). This is mechanically asserted in CI per `rules/agents.md` mechanical-sweep MUST rule.
3. **First-run `envoy init` bootstrap** — § 5.3 above; full S0 entry within 2 minutes of `envoy init` on a clean system per `02-mvp-objectives.md` EC-1 acceptance gate (≤25 minutes total Boundary Conversation; first ≤2 min covers init + S0 greet).
4. **Cross-OS keyring backend** — § 7 below enumerates per-OS caveats. Tier 2 asserts `keyring.get_keyring()` returns a non-Null backend on each OS; failures surface `KeychainUnavailableError` per `specs/connection-vault.md` § Error taxonomy.
5. **`.env` permissions** — § 5.2; mode `0600` on Unix; equivalent ACL on Windows.
6. **`pipx uninstall envoy-agent` cleanup** — venv removed; `~/.envoy/` preserved (per `specs/distribution.md` § Upgrade/Rollback/Uninstall — `--destroy-vault` is opt-in for vault destruction). Asserts `~/.envoy/trust-vault.bin` still exists post-uninstall.

### 6.2 Tier 2 — `--no-deps` audit (per `rules/orphan-detection.md` MUST Rule 1)

`pipx install envoy-agent --no-deps` and verify the install fails fast with a clear ImportError naming `kailash` (the canonical missing dep). This is the structural defense against accidental shipping of an incomplete dep declaration.

Per `rules/orphan-detection.md` MUST Rule 1, every advertised CLI subcommand has a Tier 2 wiring test:

- `envoy init` → § 6.1 item 3.
- `envoy chat` → shard 8 § 6 Tier 2 surface.
- `envoy ledger export` → shard 6 § 6 Tier 2 surface.
- `envoy shamir backup` / `envoy shamir recover` → shard 15 § 5 Tier 2 surface.
- `envoy digest today` → shard 11 § 6 Tier 2 surface.
- `envoy budget status` → shard 12 § 6 Tier 2 surface.
- `envoy channel <add|list|remove>` → shard 16 § 6 Tier 2 surface.
- `envoy posture` → shard 9 § 6 Tier 2 surface.

The shard 19 contribution is the **per-OS clean-install Tier 2 + `--no-deps` audit**; the per-subcommand wiring tests live in their owning shards.

### 6.3 Tier 3 — first-run + EC-1 onboarding from a fresh install

Per `02-mvp-objectives.md` EC-1 acceptance gate: ≥3 distinct first-time-user sessions complete BoundaryConversation in ≤25 minutes from a CLEAN INSTALL — not from a pre-warmed dev environment. This means the Tier 3 EC-1 harness MUST start from `pipx install envoy-agent` on a fresh system, not from `pip install -e .` in a developer repo. Shard 19 binds the test fixture: `tests/e2e/test_ec1_clean_install_first_user_completion.py` MUST invoke the install step inside its setup phase.

Per `rules/testing.md` Tier 3, real everything: real macOS / Linux / Windows VM; real Anthropic Claude / OpenAI GPT / DeepSeek API call (or real local Ollama); real `keyring` write to OS keychain; real Boundary Conversation completion; real Trust Vault file persisted to disk; read-back verification per `rules/testing.md` Tier 3 "every write MUST be verified with a read-back".

---

## 7. Frozen-spec ambiguity (escalate HIGH per `01-shard-plan.md` §4)

This shard surfaces ZERO HIGH-severity frozen-spec ambiguities. Two LOW-severity / non-blocking notes are logged:

### 7.1 LOW — "Offline first-run" claim (`specs/distribution.md` line 18)

`specs/distribution.md` line 18 reads: "**Offline first-run:** local model bundled (Ollama/llama.cpp/MLX)." The plain reading is "the install closure includes a local model bundle, so the first run works offline." But pipx wheels typically exclude binary artifacts >100 MB; a useful local LLM is 2–8 GB. The literal reading would require either (a) a pipx wheel with a 4 GB LLM blob (non-feasible), (b) post-install download (which is online, not offline), or (c) `envoy init` checks for an already-installed Ollama on the system and reuses it (which is offline IF the user has Ollama already, online otherwise).

**Disposition:** Disposition (c) is the operational reading — `envoy init` detects existing Ollama / llama.cpp / MLX installations on `PATH` (on macOS, also check `~/.ollama/`); if found, uses local; if not, prompts user to install Ollama OR pick a cloud provider. The "offline first-run" promise is preserved IF the user has the tool already — which is consistent with the Foundation's sovereignty thesis (BET-3) target audience (developer-leaning users likely to have Ollama already).

This is a LOW-severity ambiguity because: (i) the spec wording is not literally false under disposition (c); (ii) the ambiguity surfaces a UX detail, not an architectural primitive; (iii) Phase 02 distribution (curl|sh / brew / winget) has different bundling economics where the local model COULD be bundled (per `specs/distribution.md` § Phase 02 first-run flow line 45 explicitly lists "Model picker"). Phase 01 disposition (c) is acceptable; shard 22 spec-gap analysis MAY surface a `specs/distribution.md` clarifying note (additive prose, not load-bearing edit) but it is NOT REQUIRED.

**No MUST Rule 5b sweep triggered.**

### 7.2 LOW — Phase 01 Foundation N=3 mirror coverage

`specs/distribution.md` § N=3 mirror verification (lines 28–34) describes Phase 02+ binary distribution. Phase 01 ships only via PyPI (one mirror — pypi.org with its CDN). The Phase 01 install therefore has ZERO of the N=3 mirror security primitive that the spec mandates for Phase 02+. This is intentional per `specs/distribution.md` § Phase 01 distribution (lines 13–18) which makes no N=3 promise; the Phase 01 promise is "PyPI only." But a careless reader of `specs/distribution.md` could expect N=3 in Phase 01.

**Disposition:** This is a documentation clarity concern, not an architectural ambiguity. Phase 01 ships under the PyPI trust model (which the Python ecosystem inherits from PyPI's own signing + 2FA + maintainer key infrastructure); Phase 02+ adds the Foundation N=3 mirror layer on top. The spec already separates the Phase 01 / Phase 02 sections; a reader who reads only § Phase 01 distribution gets the right picture.

**No MUST Rule 5b sweep triggered.**

---

## 8. Phase 02 distribution-migration plan stub

Per `specs/distribution.md` § Phase 02 distribution (lines 20–25) the Phase 02 surface adds:

- macOS: `curl -sSf https://get.envoy.ai | sh`, `brew install envoy-agent`.
- Linux: same curl, `apt`/`dnf` Phase 04.
- Windows: `winget install envoy-agent`; MSI Phase 04.
- Rust: `cargo install envoy-agent`.
- Mobile: App Store + Play Store (Flutter).

Phase 02 distribution adds the security primitives that Phase 01 intentionally omits:

- N=3 mirror verification (Foundation GitHub primary + IPFS-pinned secondary + community redistributor) per `specs/distribution.md` lines 28–34.
- Quarterly signing-key rotation + on-demand <72h compromise response per line 36.
- Reproducible-build verification stream per line 40.
- First-run picker (Rust runtime vs pure-Python kailash-py) per ADR-0001 phase migration row "02".
- Jurisdictional advisories (GDPR + EAR 742.15) per lines 53–57.
- Upgrade / rollback / uninstall machinery per lines 47–51 (Phase 02 stubs in Phase 01 per § 3.4 above).

**Phase 02 distribution-migration entry-point:** the `envoy-agent` PyPI package will continue to exist in Phase 02 (as the pure-Python install path); the curl|sh / brew / winget paths become the recommended path for end-users while developers / CI / ops continue to use pipx. The Rust runtime opt-in is binary-bundled in the curl|sh path; pipx users who want Rust speed install `kailash-rs-bindings` as an extra (`pipx install envoy-agent[rust]`).

**Phase 02 acceptance gates** (per `specs/distribution.md`):

- "Install-to-first-value <10min mobile / <5min desktop" (lines 60–68; MED-R5-1 closure).
- "Mobile QR-pair <30s" (lines 70–76; MED-R5-1 closure).
- "Binary <50 MB" (lines 78–84; MED-R5-1 closure).

Phase 01 does NOT measure these gates (mobile is Phase 02; desktop binary size is Phase 02 since Phase 01 ships PyPI-only with no binary).

---

## 9. Cross-references — to all 16 wave-A/B/C/D primitive shards

This shard is the aggregation point. Forward links from each primitive shard to this shard's dep table (§ 3.2):

- Shard 4 (Envelope compiler) — `pydantic`, `kailash` core (already in § 2.1).
- Shard 5 (Trust store + lineage) — `pynacl`, `cryptography`, `aiosqlite` (§ 2.1).
- Shard 6 (Envoy Ledger) — `aiosqlite`, `kailash` core (§ 2.1); does NOT add a Phase 01 dep.
- Shard 7 (Independent verifier) — **NOT in `envoy-agent` install closure**; ships as a separate repo per shard 7 + EC-9 acceptance gate. Phase 01 does NOT pip-install it as part of envoy-agent.
- Shard 8 (Boundary Conversation) — `kailash[kaizen]` (§ 2.4 + § 3.1).
- Shard 9 (Authorship Score + posture gate) — `numpy`, `pandas` (§ 2.1); already covered.
- Shard 10 (Grant Moment) — `kailash` core; does NOT add a Phase 01 dep.
- Shard 11 (Daily Digest) — `apscheduler` (§ 2.1) — already in `kailash` core; verified via shard 11 § 3.1 ("DailyDigestService composes apscheduler.AsyncIOScheduler").
- Shard 12 (Budget tracker) — `kailash` core; does NOT add a Phase 01 dep.
- Shard 13 (Model adapter) — `kailash[kaizen]` (§ 2.4 + § 3.1) provides `LlmDeployment`; per-provider extras (`OPENAI_API_KEY` etc.) flow through `.env` per § 5.2.
- Shard 14 (Connection Vault) — `keyring` (§ 3.1 + § 3.2).
- Shard 15 (Shamir 3-of-5) — `shamir-mnemonic` via `kailash[shamir]` (§ 2.2 + § 3.1).
- Shard 16 (Channel adapters) — `kailash[nexus]` for transport primitives (§ 2.4 + § 3.1); per-vendor SDKs (`python-telegram-bot`, `slack-sdk`, `discord.py`) per § 3.1.
- Shard 17 (Foundation Health Heartbeat) — DE-SCOPED to Phase 02; ~100 LOC stubs only in Phase 01 per `00-inheritance-from-phase-00.md` § 6 invariant; does NOT add a Phase 01 dep beyond what's already in `kailash` core.
- Shard 18 (Runtime abstraction stub) — pure Envoy code; does NOT add a Phase 01 third-party dep. Phase 02 wires `kailash-rs-bindings` (per ADR-0001 phase migration); declared in `[project.optional-dependencies] rust` per § 3.1 but NOT pulled in Phase 01.

Other cross-references:

- Spec `specs/distribution.md` (frozen) — primary source.
- `DECISIONS.md` § ADR-0001 lines 64–67 — phase migration table.
- `02-mvp-objectives.md` § 3 row 1 — cross-cutting deliverable binding.
- `03-kailash-py-mvp-readiness.md` § 2.3 row #752 — `kailash-ml` exclusion mandate.
- `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` — citation discipline.
- `journal/0002-DISCOVERY-upstream-readiness-improved.md` "What it does NOT change" item 3 — upstream-velocity caveat.
- `rules/security.md` § "No Hardcoded Secrets" + § "No .env in Git" — `.env` permissions.
- `rules/env-models.md` Absolute Directive 2 — `.env` is the single source of truth.
- `rules/orphan-detection.md` MUST Rule 1 — per-CLI-subcommand Tier 2 wiring tests.
- `rules/testing.md` Tier 2 + Tier 3 — clean-install + EC-1 surface.
- `rules/agents.md` § "MUST: Reviewer Prompts Include Mechanical AST/Grep Sweep" — `pip show -f envoy-agent | grep -i ml` mechanical defense.
- `rules/communication.md` § "Plain Language Communication" — `envoy init` plain-language error surface.
- `rules/independence.md` § "License Accuracy" — Apache 2.0 declaration; this is OS variant of independence rule (Envoy IS the open-source Foundation product, distinct from the proprietary-product framing in the global rule).
- Forward → shard 20 `02-plans/03-package-skeleton.md` consumes § 3.1 + § 3.2 directly.
- Forward → shards 23–24 red team rounds verify `pipx install envoy-agent` clean-install on macOS/Linux/Windows + `kailash-ml` exclusion mechanically.
