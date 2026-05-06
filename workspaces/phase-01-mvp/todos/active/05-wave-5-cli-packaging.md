# 05 — Wave 5: CLI + pipx packaging + observability

**Purpose:** Final integration. Wave 5 depends on every primitive landing. Converges on Phase 01 release-readiness gate.

**Source authority:** `02-plans/01-build-sequence.md` § Wave 5 + shard 19.

**Depends on:** Waves 1 + 2 + 3 + 4.

---

## T-05-90 — Build envoy/cli.py — 11 subcommands

**Implements:** `specs/mvp-build-sequence.md` (post-R1-M-01 reconciliation) + shard 19 § 3.4.

**Action:** `envoy/cli.py` with 11 Phase 01 subcommands routing every primitive facade:

| Subcommand                                | Owns                                                      |
| ----------------------------------------- | --------------------------------------------------------- |
| `init`                                    | Boundary Conversation T-02-40 + Trust seed + Vault unlock |
| `chat`                                    | Boundary Conversation runtime live session                |
| `ledger {export}`                         | Ledger T-01-19 export                                     |
| `shamir {backup, recover}`                | Shamir T-02-34 + T-02-36                                  |
| `digest {today, pause, resume, schedule}` | Daily Digest T-04-83                                      |
| `grant`                                   | Grant Moment T-03-50 review/list                          |
| `posture`                                 | PostureGate T-02-31 transition request                    |
| `connection {add, list, remove}`          | Connection Vault T-01-24                                  |
| `model`                                   | EnvoyModelRouter T-01-22 picker                           |
| `version`                                 | Version reporter                                          |

**Phase 02 stubs:** `upgrade`, `uninstall --destroy-vault` raise `NotImplementedError` linked to Phase 02 issues per `rules/zero-tolerance.md` Rule 2 explicit exception.

**Each subcommand handler imports the primitive facade** (per `rules/orphan-detection.md` Rule 1; `envoy/cli.py` is THE Phase 01 hot-path call site).

**Capacity check:** ~400 LOC; 5 invariants (every facade imported through `from envoy import ...`; 11 subcommands surface; 2 Phase 02 stubs raise `NotImplementedError` with issue link; click.group routing; subcommand contract per shard 19 § 3.4); 2 call-graph hops.

**Blocks on:** Every Wave 1–4 facade landing.

**Estimate:** 1 session.

---

## T-05-91 — Build pyproject.toml + NOTICES + LICENSE

**Implements:** `02-plans/03-package-skeleton.md` § 1.1, § 1.2, § 1.3.

**Action:**

1. `pyproject.toml` per shard 19 § 3.1 — `kailash[shamir,nexus,kaizen]>=2.13.4` (NO `kailash[ml]` — closed-extra defends against re-introduction per `journal/0002` + readiness § 2.3 row #752); `keyring>=24.0`; `python-dotenv>=1.0`; `python-telegram-bot>=21.0` (LGPL-3.0+); `slack-sdk>=3.27`; `discord.py>=2.3`; `apscheduler`. Pytest markers: `regression`, `tier1`, `tier2`, `tier3`.
2. `NOTICES` per shard 19 § 3.3 — LGPL-3.0+ python-telegram-bot disclosure (full license text reproduced); MIT keyring + slack-sdk + discord.py + shamir-mnemonic; BSD-3-Clause python-dotenv; Apache-2.0 kailash family.
3. `LICENSE` — Apache-2.0 verbatim per ADR-0001 + `rules/independence.md` (variant — Envoy IS the open-source product).

**Capacity check:** ~200 LOC of TOML + license text aggregation; 3 invariants (closed-extra dep set; LGPL-3.0+ disclosure complete; Apache-2.0 license header); 0 call-graph hops.

**Blocks on:** All channel SDK choices stable (T-04-72 + T-04-73).

**Estimate:** 0.5 session.

---

## T-05-92 — Build .env.example + repo-root conftest.py + .gitignore

**Implements:** `rules/env-models.md` Absolute Directive 2 + `rules/security.md` § "No .env in Git" + `02-plans/03-package-skeleton.md` § 1.4 + § 1.6.

**Action:**

1. `.env.example` per shard 19 § 5.2 — commented placeholder keys for OpenAI / Anthropic / DeepSeek / per-primitive overrides / channel SDK secrets / heartbeat (DE-SCOPED).
2. `conftest.py` (repo root) — `load_dotenv(REPO_ROOT / ".env")` if file exists.
3. `.gitignore` — `.env` excluded; `.session-notes` excluded.

**Capacity check:** ~50 LOC; 2 invariants (`.env.example` template format; root conftest auto-loads); 0 call-graph hops.

**Estimate:** 0.25 session.

---

## T-05-93 — Build envoy/observability/ (R1-M-05)

**Implements:** R1-M-05 carry-forward — `envoy/observability/{metrics.py, tracing.py}`.

**Action:**

1. `envoy/observability/metrics.py` — Prometheus counters with **bounded cardinality** per `rules/tenant-isolation.md` Rule 4 (top-N tenants + `_other` bucket). Per-primitive counters: `boundary_conversations_total`, `grants_resolved_total{shape}`, `digest_fired_total{channel}`, `budget_thresholds_crossed_total`, `ledger_entries_appended_total`, etc.
2. `envoy/observability/tracing.py` — OpenTelemetry span helpers wrapping primitive entry points; `trace_id` propagation through Plan DAG (Boundary Conversation) and Grant Moment state machine.

**Capacity check:** ~250 LOC; 4 invariants (bounded cardinality; trace_id propagation; OTel sdk pattern; metric registration single-point); 2 call-graph hops.

**Estimate:** 0.5 session.

---

## T-05-94 — Acceptance Tier 3: cross-OS pipx clean install

**Implements:** Phase 01 distribution gate per `02-plans/02-test-strategy.md` § 4 + shard 19 § 6.1.

**Action:** `tests/tier3/test_pipx_install_phase01.py` — clean-install on:

- macOS arm64 + x86_64 (full)
- Linux Ubuntu + Fedora (desktop-env required for keyring)
- Windows 11 x86_64
- ARM64 Linux/Windows: Phase 02 (out of scope)

**Acceptance:** `pipx install envoy-agent` succeeds; `envoy version` returns 0.1.0; `envoy init --help` renders; one Boundary Conversation completes from clean install.

**Blocks on:** T-05-90 + T-05-91 + T-05-92 + every primitive facade.

**Estimate:** 0.5 session.

---

## Wave 5 milestone gate (Phase 01 RELEASE)

Per `02-plans/01-build-sequence.md` § 3 Milestone 5:

- pipx install works on macOS / Linux desktop-env / Windows x86_64.
- All 11 CLI subcommands functional.
- NOTICES correct; LGPL-3.0+ python-telegram-bot disclosure present.
- All 9 ECs met (EC-1 through EC-9).
- 2 consecutive `/redteam` rounds at 0 CRIT + 0 HIGH (EC-6 acceptance — see T-08-131).

**Wall-clock estimate:** ~1 session (depends on all prior waves landing).

---

## Cross-references

- Build sequence: `02-plans/01-build-sequence.md` § Wave 5
- Package skeleton: `02-plans/03-package-skeleton.md`
- Observability rule: `.claude/rules/tenant-isolation.md` Rule 4
- Distribution shard: `01-analysis/19-pipx-distribution-architecture.md`
- License rule: `.claude/rules/independence.md` (variant — Envoy is open-source product)
