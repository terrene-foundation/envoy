# 03 — Phase 01 Package Skeleton

**Document role:** Aggregate the per-primitive module names enumerated in shards 4–19 (and pinned in `02-plans/01-build-sequence.md` § 2) into a single canonical `envoy-agent/` repo + `envoy/` Python package layout. Pins the `pyproject.toml` shape per shard 19, names the `NOTICES` aggregation per shard 19 § 3.3, names the `.env.example` template per shard 19 § 5.2 and `rules/env-models.md` Absolute Directive 2, and pins the `tests/` 3-tier directory layout per `02-plans/02-test-strategy.md`. Cites primitive shards by shard NN; never paraphrases.

**Date:** 2026-05-03 (shard 20 of /analyze, plan 3 of 4).
**Status:** DRAFT — load-bearing for `/implement` (each todo creates one of these files); `/redteam` cycle plan (`02-plans/04-redteam-cycle-plan.md`) consumes this layout to grep for missing wiring tests per `rules/orphan-detection.md` MUST Rule 1.
**Discipline:** Every module name traces to a specific primitive shard's § 3 ("Class structure sketch") or § 4 ("Implementation"). The per-primitive shard is the source of truth for what lives inside each module; this plan only fixes the directory tree. Per `rules/specs-authority.md` MUST Rule 2 ("Spec Files Are Organized by Domain Ontology, Not Process") this is a workspace plan — it does NOT live in `specs/` and does NOT trigger MUST Rule 5b sibling re-derivation.

**Capacity check:** 1 deliverable (this plan). 16 primitive shards aggregated for module enumeration. ~5 simultaneous invariants tracked (Apache 2.0 license shape per `rules/independence.md`; `kailash[ml]` exclusion from `pyproject.toml`; LGPL-3.0+ disclosure in `NOTICES`; `.env.example` template that mirrors shard 19 § 5.2 placeholders without leaking secrets per `rules/security.md`; per-primitive Python module names that match the build-sequence step lists). Within `rules/autonomous-execution.md` § Per-Session Capacity Budget — most of the work is enumeration, not novel reasoning.

---

## 1. Top-level repo structure (`envoy-agent/`)

The repo is a single Python package at PyPI name `envoy-agent`, internal import name `envoy`, per shard 19 § 3.1.

```
envoy-agent/
├── pyproject.toml                      # shard 19 § 3.1 verbatim
├── LICENSE                             # Apache-2.0; per ADR-0001 + rules/independence.md (variant)
├── NOTICES                             # shard 19 § 3.3 — LGPL-3.0+ python-telegram-bot disclosure + MIT/BSD/Apache aggregation
├── README.md                           # high-level overview; references specs/ + workspaces/ + briefs/
├── CHANGELOG.md                        # SemVer; Phase 01 ships 0.1.0 per shard 19 § 3.1
├── .env.example                        # template per rules/env-models.md Absolute Directive 2; shard 19 § 5.2
├── .gitignore                          # MUST include `.env` per rules/security.md
├── conftest.py                         # repo-root pytest hook; loads .env per CLAUDE.md Absolute Directive 2
├── envoy/                              # the Python package (single import root)
│   └── ...                             # § 2 below
├── tests/
│   └── ...                             # § 3 below
├── docs/                               # optional; Phase 01 minimal — the briefs/ + specs/ + workspaces/ are primary docs
└── scripts/                            # repo dev scripts ONLY; NOT COC artifacts (per rules/cross-repo.md Rule 3)
```

### 1.1 `pyproject.toml` (verbatim from shard 19 § 3.1)

The provisional shape — pin values per shard 19 § 3.1; this plan does NOT re-derive:

```toml
[build-system]
requires = ["setuptools>=42", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "envoy-agent"
version = "0.1.0"
description = "Foundation-stewarded pure-Python pip-install agent implementing Terrene Foundation's open standards (CARE / EATP / CO / PACT)."
authors = [{name = "Terrene Foundation", email = "info@terrene.foundation"}]
readme = "README.md"
license = {text = "Apache-2.0"}
requires-python = ">=3.11"
classifiers = [
    "Development Status :: 4 - Beta",
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
    # Foundation runtime — closed-extra set defends against kailash-ml re-introduction
    # (per shard 19 § 2.3, journal/0002, readiness § 2.3 row #752 lightning quarantine).
    "kailash[shamir,nexus,kaizen]>=2.13.4",
    # OS keychain wrapper (shard 14)
    "keyring>=24.0",
    # .env loader (rules/env-models.md Absolute Directive 2)
    "python-dotenv>=1.0",
    # Channel adapter SDKs (shard 16)
    "python-telegram-bot>=21.0",   # LGPL-3.0+ — see NOTICES
    "slack-sdk>=3.27",
    "discord.py>=2.3",
    # WhatsApp / iMessage / Signal use raw httpx (already transitive via kailash[nexus]).
]

[project.optional-dependencies]
rust = [
    # Phase 02 entry: wire kailash-rs-bindings via runtime adapter slot per ADR-0001 + shard 18.
    # "kailash-rs-bindings>=X.Y.Z",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=1.0",
    "pytest-xdist>=3.6",
    "pytest-timeout>=2.3",
    "freezegun>=1.4",                  # Tier 3 7-day digest compression per 02-test-strategy.md § 4
    "ruff>=0.11",
    "black>=25.1",
    "mypy>=1.0",
]

[project.scripts]
# Single CLI entry point per shard 19 § 3.4 (11 Phase 01 subcommands; see § 2.cli below)
envoy = "envoy.cli:main"

[project.urls]
"Homepage"      = "https://terrene.foundation/envoy"
"Repository"    = "https://github.com/terrene-foundation/envoy-agent"
"Bug Tracker"   = "https://github.com/terrene-foundation/envoy-agent/issues"
"Documentation" = "https://terrene.dev/envoy"
"License"       = "https://github.com/terrene-foundation/envoy-agent/blob/main/LICENSE"

[tool.pytest.ini_options]
markers = [
    "regression: permanent bug-reproduction tests (rules/testing.md § Regression)",
    "tier1: Tier 1 unit tests; mocking allowed; <1s",
    "tier2: Tier 2 integration tests; real infrastructure; NO mocking",
    "tier3: Tier 3 E2E tests; real everything",
]
```

**Note on `package-dir`:** shard 19 § 3.1 declared `package-dir = {"" = "src"}`. This plan flattens to `envoy/` at repo root for Python-3.11+ src-layout compatibility WITHOUT a `src/` indirection — both are valid; the pin is a `/implement`-time choice. The build sequence § 2 already names module paths as `envoy.<primitive>.<module>` regardless of whether the file lives at `envoy/...` or `src/envoy/...`. Per `rules/communication.md`, the choice is invisible to non-technical users; per `rules/cc-artifacts.md`, the choice is invisible to the agent's reasoning surface.

### 1.2 `LICENSE` — Apache-2.0

Per ADR-0001 ("`envoy` (Apache 2.0)") + `rules/independence.md` § 2 ("TF Specs Are CC BY 4.0 — Implementations Are Separate") in the variant rule. Envoy IS the open-source Foundation product; the proprietary-product framing in the global `independence.md` does NOT apply to Envoy. The `LICENSE` file ships the Apache 2.0 text verbatim.

### 1.3 `NOTICES` — license aggregation (shard 19 § 3.3 action item)

Per shard 19 § 3.3, the `NOTICES` file aggregates third-party license attribution. The disclosure load-bearing entry is `python-telegram-bot` (LGPL-3.0+) — pipx's dynamic-link semantics satisfy the LGPL relink-permission obligation, but the license text MUST ship in `NOTICES`. Other entries are MIT / BSD-3-Clause / Apache 2.0 — single-line attribution each.

```
# NOTICES — third-party software notices for envoy-agent

This product ships under Apache-2.0; see LICENSE for terms.

It depends on the following third-party packages, each retained
under its own license. The full text of each non-permissive license
is reproduced below.

---

## LGPL-3.0-or-later

- python-telegram-bot (https://python-telegram-bot.org)
  Used as the Telegram channel adapter SDK (envoy/channels/telegram.py per shard 16).
  Dynamic linkage via Python import; relink permitted via `pipx install envoy-agent --upgrade`.
  Full LGPL-3.0+ license text reproduced below.

  [LGPL-3.0+ text]

---

## MIT

- keyring                  (envoy/connection_vault per shard 14)
- shamir-mnemonic          (envoy/shamir per shard 15)
- slack-sdk                (envoy/channels/slack per shard 16)
- discord.py               (envoy/channels/discord per shard 16)
- jsonschema, pydantic, pyyaml, PyJWT, fastapi, sqlalchemy,
  aiomysql, msal, prometheus-client, redis, mcp[cli], apscheduler
                           (transitive via kailash[shamir,nexus,kaizen])

## BSD-3-Clause

- python-dotenv            (envoy/* via repo-root conftest.py per rules/env-models.md)
- networkx, httpx, uvicorn, click, aiosqlite, psutil, numpy, pandas,
  qrcode                   (transitive via kailash[shamir,nexus,kaizen])

## Apache-2.0

- pynacl, cryptography, aiohttp, aiohttp-cors, requests,
  aiofiles, asyncpg, bcrypt, opentelemetry-{api,sdk,exporter-otlp}
                           (transitive via kailash[shamir,nexus,kaizen])

## Public Domain (Unlicense)

- filelock                 (transitive via kailash[shamir,nexus,kaizen])

## Other (PyPI-stated)

- pyotp                    (MIT — transitive)
```

The full enumeration matches shard 19 § 2.1 + § 3.2 verbatim; this plan ships the SHAPE, `/implement` ships the canonical attribution text per the upstream package metadata at install time.

### 1.4 `.env.example` — per `rules/env-models.md` Absolute Directive 2

Per shard 19 § 5.2 (the placeholder list). The file is committed as a template; the live `.env` is excluded from git per `rules/security.md` § "No .env in Git" + `.gitignore` line. Plain commented-out keys; NEVER seeded with real values:

```dotenv
# .env.example — copy to .env before first run, then run `envoy init`.
# rules/env-models.md mandates this file is the single source of truth.
# rules/security.md forbids committing .env (only .env.example).

# ----------------------------------------------------------------------
# Model adapter (shard 13) — pick at install via `envoy init` per ADR-0006.
# Set ONE of the following families:

# OpenAI / OpenAI-compatible (DeepSeek, Together, OpenRouter, etc.)
# OPENAI_API_KEY=
# OPENAI_COMPATIBLE_BASE_URL=

# Anthropic Claude
# ANTHROPIC_API_KEY=

# DeepSeek (also OpenAI-compatible — set OPENAI_COMPATIBLE_BASE_URL)
# DEEPSEEK_API_KEY=

# Local-first (Ollama / llama.cpp / MLX) — no API key needed; envoy init detects PATH
# (per shard 19 § 7.1 disposition (c) — "offline first-run if user has tool already")

# Per-primitive overrides (optional; default falls back to KAILASH_LLM_DEPLOYMENT)
# ENVOY_BOUNDARY_MODEL=
# ENVOY_DIGEST_MODEL=
# ENVOY_GRANT_MOMENT_SUMMARY_MODEL=
# ENVOY_DEFAULT_MODEL=

# ----------------------------------------------------------------------
# Channel adapters (shard 16) — populated by `envoy channel add <vendor>`.
# These keys are migrated to the Connection Vault (shard 14) on first run;
# after migration the .env values are no longer load-bearing.

# TELEGRAM_BOT_TOKEN=
# SLACK_BOT_TOKEN=
# SLACK_SIGNING_SECRET=
# DISCORD_BOT_TOKEN=
# WHATSAPP_BUSINESS_PHONE_NUMBER_ID=
# WHATSAPP_BUSINESS_TOKEN=
# BLUEBUBBLES_SERVER_URL=
# BLUEBUBBLES_PASSWORD=
# SIGNAL_CLI_REST_URL=

# ----------------------------------------------------------------------
# Foundation Health Heartbeat (shard 17 — DE-SCOPED to Phase 02; stubs only)
# FOUNDATION_HEARTBEAT_ENDPOINT=
```

### 1.5 `README.md` and `CHANGELOG.md`

Standard repo files. `README.md` describes envoy-agent at a high level (one paragraph for non-technical users per `rules/communication.md`; followed by the sovereignty-thesis pointer to BET-1 / BET-3 / BET-12 from `briefs/00-phase-01-mvp-scope.md`). `CHANGELOG.md` follows Keep-a-Changelog; Phase 01 opens with the `0.1.0` entry; per `rules/git.md`, every release-changing PR appends here.

### 1.6 `conftest.py` (repo-root)

Per CLAUDE.md Absolute Directive 2 ("Root `conftest.py` auto-loads `.env` for pytest"):

```python
# conftest.py — repo-root pytest hook.
# Auto-loads .env per CLAUDE.md Absolute Directive 2 + rules/env-models.md.
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent
ENV_FILE = REPO_ROOT / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
```

This is invariant across every primitive's tests; it does NOT need to be re-declared per-tier `conftest.py`.

---

## 2. `envoy/` Python package layout — one module per primitive

The structure mirrors `02-plans/01-build-sequence.md` § 2 step lists, one directory per primitive shard's owning surface. Inside each directory: dataclasses (`types.py`), errors (`errors.py`), and the primitive's facade or composer module(s). The primitive shard's § 3 / § 4 is the canonical source for what lives inside each module; this plan only fixes the directory tree.

```
envoy/
├── __init__.py                        # version = "0.1.0"; re-exports facade classes per shard 19
├── cli.py                             # 11 Phase 01 subcommands (shard 19 § 3.4)
│
├── runtime/                           # shard 18 — KailashRuntime Protocol + adapters
│   ├── __init__.py
│   ├── protocol.py                    # the abstract Protocol per shard 18 § 3 step 1 (every method abstract)
│   ├── kailash_py_adapter.py          # the SOLE Phase 01 backend; composes Envoy primitives per shard 18 § 3 step 2
│   └── kailash_rs_bindings.py         # feature-flagged stub per shard 18 § 3 step 3; raises RuntimeBackendNotWired in Phase 01
│
├── boundary_conversation/             # shard 8 — 6 modules per shard 8 § 3.7 (~1180 LOC)
│   ├── __init__.py
│   ├── runtime.py                     # BoundaryConversationRuntime + Plan DAG over S0→S10 (shard 8 § 3 step 1)
│   ├── signatures.py                  # 9 per-state Signature subclasses S1–S9 (shard 8 § 3 step 2)
│   ├── envelope_input_assembler.py    # EnvelopeConfigInputAssembler — JCS-canonical-order accumulator (step 3)
│   ├── ritual_resume.py               # RitualResumeCoordinator — Trust-Vault-backed per-state persistence (step 4)
│   ├── novelty_feedback.py            # S3/S5 Jaccard-portion gate per shard 8 § 3 step 6 (Phase 01)
│   ├── post_duress_banner.py          # S0 entry banner gate (T-018 / V2 C-02 fix) per shard 8 § 3 step 7
│   ├── types.py                       # EnvelopeConfigInput, ConversationState, ResumeRecord, etc.
│   └── errors.py                      # 7 typed errors per specs/boundary-conversation.md § Error taxonomy
│
├── envelope/                          # shard 4 — EnvelopeCompiler + materializer
│   ├── __init__.py
│   ├── compiler.py                    # EnvelopeCompiler — wraps kailash.trust.pact.envelopes (shard 4 § 4 step 3)
│   ├── canonical_bytes.py             # JCS+NFC canonical_bytes + content_hash pipeline (step 2)
│   ├── template_resolver.py           # local-only template registry — Foundation Library deferred Phase 02 (step 4)
│   ├── types.py                       # EnvelopeConfigInput, EnvelopeConfig (step 1)
│   └── errors.py                      # 24 typed errors per specs/envelope-model.md § Error taxonomy
│
├── ledger/                            # shard 6 — HashChainBuilder + CanonicalJsonEncoder + sunset clause
│   ├── __init__.py
│   ├── facade.py                      # EnvoyLedger — wraps upstream AuditStore inside df.transaction() (shard 6 § 3 step 3)
│   ├── canonical_json.py              # canonical_dumps() — #757/#756/#731 byte pinning (step 2)
│   ├── hash_chain.py                  # HashChainBuilder.build() pure function (step 2)
│   ├── head_commitment.py             # monotonic guard + HaltedByRollback (step 4)
│   ├── two_phase.py                   # PhaseARecord / PhaseBRecord linked by intent_id; 30-day TTL orphan sweep (step 5)
│   ├── export.py                      # `envoy ledger export --format json|pdf` bundle (step 6); consumed by shard 7 verifier
│   ├── types.py                       # 35 dataclasses transcribed from specs/ledger.md lines 47–91 (step 1)
│   └── errors.py                      # 8 typed errors (step 1)
│
├── trust/                             # shard 5 — TrustStoreAdapter (single composition class)
│   ├── __init__.py
│   ├── store.py                       # TrustStoreAdapter — composes SqliteTrustStore + SQLitePostureStore (shard 5 § 3 step 1+2)
│   ├── vault.py                       # AES-256-GCM Trust Vault container; Argon2id+Secure-Enclave-bound (step 3)
│   ├── cascade.py                     # wraps kailash.trust.revocation.cascade.cascade_revoke + verify_cascade_complete (step 4)
│   ├── algorithm_id.py                # _with_algorithm_id single-point helper (step 5)
│   ├── shamir_hooks.py                # export_master_key_for_shamir / import_master_key_from_shamir (step 5)
│   ├── types.py                       # PrincipalId, GenesisRecord, DelegationRecord, etc.
│   └── errors.py                      # PrincipalRequiredError + cascade typed errors
│
├── grant_moment/                      # shard 10 — GrantMomentOrchestrator + state machine (8 modules per shard 10 § 3)
│   ├── __init__.py
│   ├── orchestrator.py                # GrantMomentOrchestrator facade — drives M0→M4 (shard 10 § 3)
│   ├── state_machine.py               # GrantMomentState enum + transition table (step 1)
│   ├── signed_consent.py              # SignedConsentBuilder — JCS+NFC + delegation_key signing (step 2)
│   ├── resolution.py                  # ResolutionShape × 3 (Approve / Decline / ApproveWithModification) (step 3)
│   ├── out_of_envelope.py             # OutOfEnvelopeDetector wraps Kaizen tool-dispatch (step 4)
│   ├── channel_handoff.py             # ChannelHandoff.dispatch() — primary-channel binding check (step 5)
│   ├── cascade.py                     # CascadeRevocationOrchestrator — wraps cascade_revoke + verify_cascade_complete (step 6)
│   ├── plan_suspension_bridge.py      # typed-event bridge to Boundary Conversation (step 7)
│   ├── novelty.py                     # NoveltyClassifier — novel / familiar_repeat / high_stakes (step 8)
│   ├── types.py                       # GrantMomentRequest, GrantMomentResult, DelegationRecord
│   └── errors.py                      # 10 typed errors per specs/grant-moment.md
│
├── authorship/                        # shard 9 — stateless score + PostureGate
│   ├── __init__.py
│   ├── score.py                       # AuthorshipScore.recompute(envelope, ledger_slice) — pure function (shard 9 § 3 step 1)
│   ├── posture_gate.py                # PostureGate.request_transition() — 5-step fail-closed (step 2)
│   ├── bet12_emitter.py               # BET12CadenceEmitter — local-only ritual_completion entries with bet_id="BET-12" (step 3)
│   ├── types.py                       # AuthorshipScoreResult, PostureLevel mapping
│   └── errors.py                      # PostureTransitionRefusedError + 5-step gate errors
│
├── daily_digest/                      # shard 11 — DailyDigestService composing apscheduler
│   ├── __init__.py
│   ├── service.py                     # DailyDigestService facade + DigestScheduler (shard 11 § 3 step 1)
│   ├── aggregator.py                  # LedgerAggregator — queries EnvoyLedger.query() (step 2)
│   ├── renderer.py                    # DigestRenderer — 11-field schema/1.0 + optional EnvoyModelRouter summary (step 3)
│   ├── fanout.py                      # PerChannelFanout — asyncio.gather + return_exceptions fault isolation (step 4)
│   ├── backfill.py                    # BackfillTracker — Trust-store-backed missed-day catch-up (step 5)
│   ├── pause_disable.py               # PauseDisableState (step 5)
│   ├── low_engagement.py              # LowEngagementTracker — habituation form-flip (step 5)
│   ├── duress_reader.py               # DuressBannerReader — local-only shadow-segment, primary-channel only (step 6)
│   ├── types.py                       # DigestPayload (11-field schema/1.0 verbatim per specs/daily-digest.md)
│   └── errors.py                      # 5 typed errors per shard 11 § 3 step 7
│
├── budget/                            # shard 12 — EnvoyBudgetOrchestrator + ThresholdDispatcher
│   ├── __init__.py
│   ├── orchestrator.py                # EnvoyBudgetOrchestrator — reserve_for_call / record_for_call / check / lower_velocity_limit / raise_velocity_limit-refused (shard 12 § 3 step 2)
│   ├── multi_window.py                # MultiWindowBudget — 5 BudgetTracker instances per ceiling window (step 1)
│   ├── threshold_dispatcher.py        # ThresholdDispatcher — async queue; collect-under-lock, dispatch-outside-lock (step 3)
│   ├── reset_scheduler.py             # BudgetResetScheduler — pure-function current_period_key(window, at_time) (step 4)
│   ├── anomaly.py                     # AnomalyDetector — single-call > 50% session; 5-calls-at-ceiling-in-1-min (step 5)
│   ├── ledger_emitter.py              # single-point filter for budget_threshold_crossed + budget_reservation_record (step 6)
│   ├── types.py                       # CeilingWindow enum, BudgetReservation, ThresholdEvent
│   └── errors.py                      # 7 typed errors (step 7)
│
├── shamir/                            # shard 15 — 5 modules per shard 15 § 3
│   ├── __init__.py
│   ├── ritual.py                      # ShamirRitualCoordinator — wraps kailash.trust.vault.shamir.generate(...) with 6-step ritual (shard 15 § 3 step 1)
│   ├── paper.py                       # paper-card renderer — 24-word format (step 2)
│   ├── reconstruct.py                 # `envoy shamir recover` CLI; commitment-verify against Genesis.shard_public_commitments (step 3)
│   ├── commitments.py                 # bind shard public commitments to Genesis Record at backup (step 4)
│   ├── distribution_checklist.py      # opaque slot labels in Trust Vault (NOT real names; H-06 fix) (step 5)
│   ├── types.py                       # ShamirShard, ShardSlotLabel, ReconstructionResult
│   └── errors.py                      # 9 typed errors per specs/shamir-recovery.md § Error taxonomy
│
├── connection_vault/                  # shard 14 — keyring wrapper
│   ├── __init__.py
│   ├── adapter.py                     # ConnectionVaultAdapter — 11-field schema serialization to keyring 3-tuple (shard 14 § 3 step 1)
│   ├── isolation.py                   # per-principal isolation + envelope-scope enforcement (step 2)
│   ├── lifecycle.py                   # expires_at + usage_counter enforcement; fail-closed defaults (step 3)
│   ├── env_import.py                  # `.env` first-run import path (step 4); post-onboarding Vault is source of truth
│   ├── types.py                       # ConnectionVaultEntry (11-field schema)
│   └── errors.py                      # 7 typed errors per shard 14 § 3
│
├── model/                             # shard 13 — EnvoyModelRouter + risk annotator + token-budget filter
│   ├── __init__.py
│   ├── router.py                      # EnvoyModelRouter — wraps LlmClient.from_env(); per-primitive override map (shard 13 § 3 step 2)
│   ├── byom_picker.py                 # first-launch CLI; writes KAILASH_LLM_PROVIDER + KAILASH_LLM_DEPLOYMENT; routes secrets to Connection Vault (step 1)
│   ├── risk_annotator.py              # EnvoyProviderRiskAnnotator — preset → ProviderRisk per specs/model-adapter.md lines 17–29 (step 3)
│   ├── response_filter.py             # token-budget + leak-canary stub + goal-drift stub (step 4)
│   ├── types.py                       # ModelOverride, ProviderRisk, FilteredResponse
│   └── errors.py                      # ModelUnreachableError, TokenBudgetExceededError, etc.
│
├── channels/                          # shard 16 — 6 social adapters + InboundRouter + GrantMomentRenderer + ChannelAdapter ABC
│   ├── __init__.py
│   ├── base.py                        # ChannelAdapter ABC + InboundMessage envelope + 11 typed errors (shard 16 § 3 step 1)
│   ├── cli.py                         # CLIChannelAdapter — wraps kailash.channels.cli_channel (step 2)
│   ├── web.py                         # WebChannelAdapter — wraps kailash.channels.api_channel; localhost+Origin/Host allowlist (step 2; post-#673)
│   ├── telegram.py                    # TelegramChannelAdapter — wraps nexus.transports.webhook + per-vendor WebhookSigner (step 3)
│   ├── slack.py                       # SlackChannelAdapter (step 3)
│   ├── discord.py                     # DiscordChannelAdapter (step 3)
│   ├── whatsapp.py                    # WhatsAppChannelAdapter — caveated; paid-tier per specs/channel-adapters.md lines 171–173 (step 4)
│   ├── imessage.py                    # IMessageChannelAdapter — caveated; Apple-ToS-grey BlueBubbles bridge (step 4)
│   ├── signal.py                      # SignalChannelAdapter — caveated; Path B legal-gate (step 4)
│   ├── inbound_router.py              # InboundRouter — concurrent asyncio.gather over receive_message() (step 5)
│   ├── grant_moment_renderer.py       # per-channel UI; numbered-options text fallback (step 6)
│   ├── rate_limiter.py                # PerChannelRateLimiter (step 7)
│   ├── credential_resolver.py         # CredentialResolver — startup-time Connection Vault entry resolution (step 8)
│   ├── types.py                       # InboundMessage, SendReceipt, ChannelKind enum
│   └── errors.py                      # 11 typed errors per specs/channel-adapters.md § Error taxonomy
│
└── heartbeat/                         # shard 17 — 4 stubs only (DE-SCOPED to Phase 02 entry)
    ├── __init__.py
    ├── star_prio.py                   # PhaseDeferredError stub
    ├── ohttp.py                       # PhaseDeferredError stub
    ├── signed_consent.py              # PhaseDeferredError stub
    └── registry.py                    # PhaseDeferredError stub
```

### 2.1 `envoy/cli.py` — 11 subcommand routing

Per shard 19 § 3.4 the 11 Phase 01 subcommands are: `init`, `chat`, `ledger {export}`, `shamir {backup,recover}`, `digest {today,pause,resume,schedule}`, `grant`, `posture`, `connection {add,list,remove}`, `model`, `version`, with two stubs (`upgrade`, `uninstall --destroy-vault` raising NotImplementedError to Phase 02 issues per `rules/zero-tolerance.md` Rule 2 explicit exception). Subcommand handlers compose the primitive facades:

```python
# envoy/cli.py — sketch (canonical implementation per shard 19 § 3.4)
import click
from envoy.runtime import KailashRuntime
from envoy.boundary_conversation import BoundaryConversationRuntime
from envoy.ledger import EnvoyLedger
from envoy.shamir import ShamirRitualCoordinator
from envoy.daily_digest import DailyDigestService
from envoy.budget import EnvoyBudgetOrchestrator
from envoy.connection_vault import ConnectionVaultAdapter
from envoy.model import EnvoyModelRouter
from envoy.authorship import PostureGate
from envoy.channels import InboundRouter

@click.group()
def main(): ...

@main.command()
def init(): ...                   # shard 8 + 5 + 14 bootstrap
@main.command()
def chat(): ...                   # shard 8
@main.group()
def ledger(): ...                 # shard 6
@main.group()
def shamir(): ...                 # shard 15
@main.group()
def digest(): ...                 # shard 11
@main.command()
def grant(): ...                  # shard 10
@main.command()
def posture(): ...                # shard 9
@main.group()
def connection(): ...             # shard 14
@main.command()
def model(): ...                  # shard 13
@main.command()
def version(): ...                # version reporter
```

Each subcommand imports the primitive's facade, NOT the primitive's internal modules, per `rules/orphan-detection.md` MUST Rule 1 (every facade has a hot-path call site; `envoy/cli.py` is the canonical hot-path call site for Phase 01).

### 2.2 `envoy/__init__.py` — package re-exports

The package `__init__.py` re-exports the facade class for each primitive so downstream users do `from envoy import DailyDigestService` etc. without crawling submodule paths. Per `rules/orphan-detection.md` MUST Rule 6 (module-scope public imports appear in `__all__`):

```python
# envoy/__init__.py
__version__ = "0.1.0"

from envoy.boundary_conversation.runtime import BoundaryConversationRuntime
from envoy.envelope.compiler import EnvelopeCompiler
from envoy.ledger.facade import EnvoyLedger
from envoy.trust.store import TrustStoreAdapter
from envoy.grant_moment.orchestrator import GrantMomentOrchestrator
from envoy.authorship.posture_gate import PostureGate
from envoy.daily_digest.service import DailyDigestService
from envoy.budget.orchestrator import EnvoyBudgetOrchestrator
from envoy.shamir.ritual import ShamirRitualCoordinator
from envoy.connection_vault.adapter import ConnectionVaultAdapter
from envoy.model.router import EnvoyModelRouter
from envoy.runtime.protocol import KailashRuntime

__all__ = [
    "BoundaryConversationRuntime",
    "EnvelopeCompiler",
    "EnvoyLedger",
    "TrustStoreAdapter",
    "GrantMomentOrchestrator",
    "PostureGate",
    "DailyDigestService",
    "EnvoyBudgetOrchestrator",
    "ShamirRitualCoordinator",
    "ConnectionVaultAdapter",
    "EnvoyModelRouter",
    "KailashRuntime",
]
```

The 12 facade exports are exactly the 12 manager-shape classes listed in `rules/facade-manager-detection.md` MUST Rule 1; each has a `tests/tier2/test_<lowercase>_wiring.py` per `02-plans/02-test-strategy.md` § 3.1.

---

## 3. `tests/` layout — the 3-tier discipline

Per `02-plans/02-test-strategy.md` § 1 (3-tier framework) + `rules/testing.md` § 3-Tier. One conftest.py per tier scope; per-tier markers per § 1.1 above:

```
tests/
├── __init__.py
├── conftest.py                                # tier-agnostic fixtures: principal_id, tmp_trust_vault_path, cleanup
│
├── tier1/                                      # rules/testing.md § Tier 1: mocking allowed; <1s
│   ├── __init__.py
│   ├── conftest.py                             # tier 1 markers + monkeypatch defaults
│   ├── test_envelope_canonical_bytes_pure.py
│   ├── test_ledger_canonical_dumps_byte_pinning.py
│   ├── test_authorship_score_recompute_pure.py
│   ├── test_lamport_clock_next_pure.py
│   ├── test_format_record_id_for_event.py
│   ├── test_budget_current_period_key_pure.py
│   ├── test_envelope_config_dataclass_post_init.py
│   ├── test_grant_moment_state_machine_transitions.py
│   └── ...                                      # one file per pure-function / dataclass surface
│
├── tier2/                                      # rules/testing.md § Tier 2: real infrastructure; NO mocking
│   ├── __init__.py
│   ├── conftest.py                             # real SQLite, real keyring, real Ed25519 keypair fixtures; module-scope env-var lock
│   │
│   # ── Per-primitive WIRING tests (rules/orphan-detection.md MUST Rule 1 + facade-manager-detection.md Rule 2)
│   ├── test_boundary_conversation_runtime_wiring.py
│   ├── test_envelope_compiler_wiring.py
│   ├── test_envoy_ledger_wiring.py
│   ├── test_trust_store_adapter_wiring.py
│   ├── test_grant_moment_orchestrator_wiring.py
│   ├── test_posture_gate_wiring.py
│   ├── test_daily_digest_service_wiring.py
│   ├── test_envoy_budget_orchestrator_wiring.py
│   ├── test_shamir_ritual_coordinator_wiring.py
│   ├── test_connection_vault_adapter_wiring.py
│   ├── test_envoy_model_router_wiring.py
│   │
│   # ── Crypto-pair round-trip (rules/orphan-detection.md MUST Rule 2a)
│   ├── test_envoy_ledger_crypto_round_trip.py
│   ├── test_trust_store_shamir_master_key_export_import_round_trip.py
│   ├── test_signed_consent_builder_byte_identity.py
│   │
│   # ── Tenant isolation (rules/tenant-isolation.md)
│   ├── test_principal_required_error_strict_mode.py
│   ├── test_envoy_ledger_query_filter_principal_id.py
│   │
│   # ── Cross-cutting wirings
│   ├── test_resume_from_each_state.py
│   ├── test_envelope_compiler_monotonic_tightening_at_compile.py
│   ├── test_post_duress_banner.py
│   ├── test_out_of_envelope_detector_wiring.py
│   ├── test_cascade_revocation_orchestrator_wiring.py
│   ├── test_plan_suspension_bridge_wiring.py
│   ├── test_visible_secret_render_check.py
│   ├── test_envoy_ledger_canonical_json_byte_identity.py
│   ├── test_envoy_ledger_atomic_append_under_failure.py
│   ├── test_envoy_ledger_head_commitment_monotonic.py
│   ├── test_envoy_ledger_phase_a_b_intent_id_link.py
│   ├── test_envoy_ledger_segment_boundary.py
│   ├── test_envoy_ledger_export_round_trip.py
│   ├── test_shamir_ritual_coordinator_wiring.py
│   ├── test_shamir_paper_renderer.py
│   ├── test_shamir_commitments_bound_to_genesis.py
│   ├── test_digest_form_per_channel.py
│   ├── test_low_engagement_fallback.py
│   ├── test_duress_banner_primary_only.py
│   ├── test_digest_reply_no_yes_skip.py
│   ├── test_backfill_skipped_days.py
│   ├── test_pause_disable_persists_across_restart.py
│   │
│   # ── Channel adapters (per shard 16; one wiring file per channel)
│   └── channels/
│       ├── __init__.py
│       ├── conftest.py                         # vendor-sandbox fixtures (Telegram test bot, Slack ngrok, Discord guild)
│       ├── test_cli_adapter_lifecycle.py
│       ├── test_web_adapter_lifecycle.py
│       ├── test_telegram_adapter_lifecycle.py
│       ├── test_slack_adapter_lifecycle.py
│       ├── test_discord_adapter_lifecycle.py
│       ├── test_whatsapp_adapter_lifecycle.py
│       ├── test_imessage_adapter_lifecycle.py
│       ├── test_signal_adapter_lifecycle.py
│       ├── test_<channel>_send_message.py × 8
│       ├── test_<channel>_ritual_delivery.py × 8
│       ├── test_inbound_router_wiring.py
│       ├── test_credential_resolver_wiring.py
│       └── test_h03_primary_channel_binding.py
│
├── tier3/                                      # rules/testing.md § Tier 3: real everything (real LLM, real keychain, real channels)
│   ├── __init__.py
│   ├── conftest.py                             # cross-OS matrix fixtures; freezegun for 7-day compression
│   │
│   # ── EC-1 (Boundary Conversation)
│   ├── test_boundary_conversation_full_path.py        # N=3 sessions ≤25min
│   ├── test_boundary_conversation_minimum_path.py     # 8min minimum-path
│   │
│   # ── EC-2 (Grant Moment)
│   ├── test_grant_moment_three_resolution_shapes.py
│   ├── test_grant_moment_cascade_revocation_cross_channel.py
│   │
│   # ── EC-3 (Daily Digest)
│   ├── test_daily_digest_morning_delivery.py          # 7-day fire battery
│   │
│   # ── EC-4 (Ledger tampering battery)
│   ├── test_envoy_ledger_tampering_battery.py         # 8 tampering forms × N=1000-entry bundle
│   ├── test_envoy_ledger_cross_os_byte_identity.py    # macOS / Linux / Windows
│   │
│   # ── EC-5 (Shamir 10-combo + cross-tool interop)
│   ├── test_shamir_all_10_combinations.py             # C(5,3)=10 combos exhaustive
│   ├── test_shamir_cross_tool_interop.py              # python-shamir-mnemonic interop bidirectional
│   ├── test_shamir_plain_language_errors.py
│   ├── test_trust_store_cross_os_portability.py       # BET-9b
│   │
│   # ── EC-7 (8-channel × N=3 onboarding)
│   ├── test_session_continuity_8_channels.py          # 8 channels × N=3 = 24 onboardings
│   │
│   # ── EC-8 (7-day cross-channel coherence)
│   ├── test_envoy_7_day_cross_channel_coherence.py
│   │
│   # ── EC-9 (independent verifier source-isolation)
│   ├── test_envoy_ledger_independent_verifier_ec9.py  # spawns separately-codebased envoy-ledger-verifier as subprocess
│   │
│   # ── pipx clean-install (shard 19 § 6.1)
│   └── test_pipx_install_phase01.py                   # macOS arm64+x86_64 / Linux Ubuntu+Fedora / Windows 11
│
└── regression/                                  # rules/testing.md § Regression — permanent, never deleted
    ├── __init__.py
    ├── test_t018_visible_secret.py
    ├── test_t019_habituation_low_engagement_fallback.py
    ├── test_t023_authorship_score_seeding.py
    ├── test_t023_signal_path_b.py
    ├── test_t070_clipboard_autoclear.py
    └── test_t080_tls13_pin.py
```

Naming convention: `tests/tier2/test_<lowercase_facade>_wiring.py` per `rules/facade-manager-detection.md` Rule 2. `/redteam` mechanically detects missing wiring tests by checking for the expected file name (per `02-plans/04-redteam-cycle-plan.md` § 2 mechanical-sweep checklist).

### 3.1 Per-package `--collect-only` gate (per `rules/orphan-detection.md` MUST Rule 5a)

Phase 01 ships ONE Python package (`envoy/`), not a monorepo of sub-packages. The per-package collect-only gate degenerates to a per-tier collect-only gate:

```bash
for tier in tests/tier1 tests/tier2 tests/tier3 tests/regression; do
    pytest --collect-only -q "$tier" --continue-on-collection-errors
done
```

Each MUST exit 0 for any PR to merge. `/redteam` round 1 enforces this.

### 3.2 Pytest plugin / marker discipline (per `rules/testing.md` § Pytest Plugin + Marker Declaration Pair)

The 4 markers (`regression`, `tier1`, `tier2`, `tier3`) are declared in `pyproject.toml` `[tool.pytest.ini_options].markers` per § 1.1 above. Any new marker introduced in a PR MUST register it in `pyproject.toml` in the SAME commit; collection failure on an unregistered marker is BLOCKING per the rule.

---

## 4. Disposition of cross-cutting concerns

### 4.1 Side-channel: `envoy-ledger-verifier/` (shard 7) is a separate repo

Per `02-plans/01-build-sequence.md` § 1 Wave-side-channel + `specs/independent-verifier.md` (the additive spec drafted at shard 22 § 5) + EC-9 acceptance gate, the verifier ships in `terrene-foundation/envoy-ledger-verifier` as a SEPARATE codebase with ZERO source share with `envoy-agent`. Its layout is NOT defined here; the verifier repo's own README + `specs/independent-verifier.md` govern that codebase. `envoy-agent` calls the verifier as a subprocess in `tests/tier3/test_envoy_ledger_independent_verifier_ec9.py` only; the binary is downloaded / installed via the verifier's own distribution path (Phase 01 = a `gh release` artifact under `terrene-foundation/envoy-ledger-verifier`).

### 4.2 What this skeleton does NOT include

- **No `src/envoy-rust-bindings/`** — kailash-rs-bindings adapter is Phase 02 entry; the slot at `envoy/runtime/kailash_rs_bindings.py` raises `RuntimeBackendNotWired` per shard 18 § 3 step 3.
- **No `src/envoy/foundation_health/`** — Foundation Health Heartbeat is DE-SCOPED to Phase 02 entry per shard 17 + `00-inheritance-from-phase-00.md` § 6 invariant. Phase 01 ships ~100 LOC stubs at `envoy/heartbeat/{star_prio,ohttp,signed_consent,registry}.py` only.
- **No `src/envoy/a2a/`** — A2A messaging is Phase 03 deliverable per `specs/a2a-messaging.md` line 13. Phase 01 channel adapters do single-principal binding-checks ONLY (per shard 16 § 7.2 + shard 22 § 3.8 disposition).
- **No `src/envoy/mcp_server/`** — MCP server surface is Phase 02+ per `00-inheritance-from-phase-00.md` § 6 (MCP governance is Phase 02 ISS-19/ISS-21).
- **No `src/envoy/mobile/`** — mobile clients are Phase 04 (Flutter; cross-platform; out of pyproject scope per shard 19 § 3.1).

---

## 5. Orphan / facade discipline applied to this skeleton

Per `rules/orphan-detection.md` + `rules/facade-manager-detection.md`, every facade-shape class exposed at module top-level (the 12 in § 2.2 above) MUST satisfy:

- **MUST Rule 1 (orphan-detection.md):** every `db.X` / `app.X` facade has a production call site within 5 commits. `envoy/cli.py` is the production call site for ALL 12 in Phase 01; the wave-by-wave build order in `02-plans/01-build-sequence.md` § 1 ensures the CLI subcommand lands no later than the facade itself.
- **MUST Rule 2 (orphan-detection.md):** every wired manager has a Tier 2 integration test asserting an externally-observable effect. `tests/tier2/test_<lowercase>_wiring.py` ships per facade (12 wiring files) per `02-plans/02-test-strategy.md` § 3.1.
- **MUST Rule 2a (orphan-detection.md):** every crypto-pair round-trip is tested THROUGH the facade. Three Tier 2 round-trip files in § 3 above (`test_envoy_ledger_crypto_round_trip.py`, `test_trust_store_shamir_master_key_export_import_round_trip.py`, `test_signed_consent_builder_byte_identity.py`).
- **MUST Rule 1 (facade-manager-detection.md):** every manager-shape class has a Tier 2 test that imports through the facade (`from envoy import DailyDigestService`, NOT `from envoy.daily_digest.service import DailyDigestService`).
- **MUST Rule 2 (facade-manager-detection.md):** Tier 2 file naming `test_<lowercase>_wiring.py`. Enforced per § 3 above.
- **MUST Rule 3 (facade-manager-detection.md):** manager constructor takes the parent framework instance. Pinned per primitive shard's § 4 implementation contract; this skeleton does not redefine.

---

## 6. Cross-references

### Plan 1 — Build sequence

- `workspaces/phase-01-mvp/02-plans/01-build-sequence.md` § 2 — per-primitive scaffold step list; THIS document's directory tree mirrors that step structure verbatim.

### Plan 2 — Test strategy

- `workspaces/phase-01-mvp/02-plans/02-test-strategy.md` § 1 (3-tier), § 2 (per-EC battery), § 3 (cross-cutting test patterns), § 4 (test infrastructure stack).

### Plan 4 — Redteam cycle

- `workspaces/phase-01-mvp/02-plans/04-redteam-cycle-plan.md` consumes this skeleton as the canonical orphan-detection target; the round-1 mechanical sweep per `rules/agents.md` § "Reviewer Prompts Include Mechanical AST/Grep Sweep" verifies the directory tree exists AND each named module name is reachable from the package facade.

### Per-primitive shards (canonical source for what lives inside each module)

- Shard 4 — `01-analysis/04-envelope-compiler-implementation.md` § 4.
- Shard 5 — `01-analysis/05-trust-store-implementation.md` § 4.
- Shard 6 — `01-analysis/06-envoy-ledger-implementation.md` § 4.
- Shard 7 — `01-analysis/07-independent-verifier-design.md` (separate repo; not in this skeleton).
- Shard 8 — `01-analysis/08-boundary-conversation-implementation.md` § 3.7.
- Shard 9 — `01-analysis/09-authorship-score-implementation.md` § 3.
- Shard 10 — `01-analysis/10-grant-moment-implementation.md` § 3.
- Shard 11 — `01-analysis/11-daily-digest-implementation.md` § 3.
- Shard 12 — `01-analysis/12-budget-tracker-implementation.md` § 3.
- Shard 13 — `01-analysis/13-model-adapter-implementation.md` § 3.
- Shard 14 — `01-analysis/14-connection-vault-implementation.md` § 3.
- Shard 15 — `01-analysis/15-shamir-recovery-implementation.md` § 3.
- Shard 16 — `01-analysis/16-channel-adapters-implementation.md` § 3.
- Shard 17 — `01-analysis/17-foundation-health-heartbeat-decision.md` (4 stubs only).
- Shard 18 — `01-analysis/18-runtime-abstraction-stub.md` § 3.
- Shard 19 — `01-analysis/19-pipx-distribution-architecture.md` § 3.1, § 3.3, § 3.4, § 5.2.

### Rules consulted

- `.claude/rules/cc-artifacts.md` — invisible-to-agent layout choice between flat `envoy/` vs `src/envoy/`.
- `.claude/rules/cross-repo.md` Rule 3 — `scripts/` is repo-dev only, NOT COC; this skeleton honors that.
- `.claude/rules/env-models.md` Absolute Directive 2 — `.env.example` template + repo-root `conftest.py`.
- `.claude/rules/facade-manager-detection.md` Rules 1, 2, 3 — per-primitive facade discipline.
- `.claude/rules/git.md` — atomic commits; CHANGELOG.md per release.
- `.claude/rules/independence.md` (variant) — Apache-2.0 license shape; envoy IS the open-source product.
- `.claude/rules/orphan-detection.md` MUST Rules 1, 2, 2a, 4, 4a, 4b, 5, 5a, 6, 7 — the orphan + collection + sibling-test discipline.
- `.claude/rules/security.md` § "No .env in Git" — `.gitignore` + `.env.example` template.
- `.claude/rules/specs-authority.md` MUST Rule 2 — workspace plans are NOT specs.
- `.claude/rules/testing.md` § 3-Tier + § Pytest Plugin + § Test-Skip Triage — per-tier markers + collect-only gate.
- `.claude/rules/zero-tolerance.md` Rule 2 — `envoy upgrade` / `envoy uninstall --destroy-vault` Phase 02 stubs are explicit-issue-linked exceptions.

### Forward references

- `/implement` — each Phase 01 todo creates one of the directories / files in § 2 above; the build sequence § 2 step lists are the cycle structure.
- `/redteam` — round 1 grep sweep verifies directory tree existence + module-name reachability; round 2 verifies wiring tests cover every facade per § 5 above.
