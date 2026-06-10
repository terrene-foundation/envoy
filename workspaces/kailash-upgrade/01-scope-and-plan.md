# kailash Upgrade — Scope & Plan (2.13.4 → latest)

**Status:** SCOPING (plan only — not applied). Authored 2026-06-10.
**Trigger:** envoy pins `kailash[nexus,kaizen,dataflow,pact,shamir]>=2.13.4`; installed = **2.13.4**; latest on PyPI = **2.29.3** (16 minor versions behind). Surfaced during the P6 upstream-advisory investigation (two suppressed warnings; one already fixed upstream).

---

## Executive summary

**The upgrade is import-compatible — not an API rewrite.** Every one of envoy's 17 kailash/nexus import lines resolves cleanly against 2.29.3 **with envoy's actual extras installed** (`kailash[nexus,kaizen,dataflow,pact,shamir]`). The earlier "Nexus API restructured / top-level `nexus` import gone" concern was a **false alarm** — an artifact of probing against a bare `kailash` install without the `[nexus]` extra. With the extra, `from nexus import Nexus` still works (now served by a separate `kailash-nexus` distribution that the extra pulls in transitively).

The real risk is **behavioral**, not structural: 16 versions of semantic changes to the heavily-used `kailash.trust.*` substrate (signing, audit, posture, revocation, chain, vault). Those surface only by running envoy's full test suite against 2.29.3. **Sizing: ~1–2 sessions** — most of the cost is running the suite, triaging any behavioral regressions in the trust substrate, and regenerating `uv.lock` + CI on py3.11/py3.13.

**Recommendation:** proceed as a dedicated single workstream (do NOT fold into a Phase-02 wave). Bump → `uv sync` → full suite → triage behavioral deltas → drop the now-fixed `@app.handler` suppression → re-verify. Gate it behind the normal `/implement` review + CI.

---

## Findings (evidence, probed against kailash 2.29.3)

### F1 — Import surface is fully compatible

All 17 envoy import lines resolve on 2.29.3 with the project extras. The 3 that appeared to "break" in a bare-venv probe (`kailash.core.pool.sqlite_pool`, `kailash.trust.authority`, `kailash.trust.chain`) all resolve once `kailash[nexus,kaizen,dataflow,pact,shamir]` + `requests` are installed — they were transitive-dep failures of the probe venv, not API removals. Every symbol envoy imports (`AuthorityType`, `CapabilityType`, `DelegationRecord`, `AsyncSQLitePool`, `SQLitePoolConfig`, `InMemoryKeyManager`, `SqliteAuditStore`, `TrustLineageChain`, `TrustPosture`, `cascade_revoke`, `serialize_shard`, …) is present at its current import path on 2.29.3.

### F2 — Blast radius is narrow for code, wide for behavior

- **17 files** import `kailash`/`nexus`. The dominant surface is `kailash.trust.*` (the trust substrate envoy is built on).
- **Nexus is used in only 2 files**: `envoy/foundation_ops/ohttp_server.py` (S10) and `envoy/registry/library_app.py` (S8) — both `from nexus import Nexus` + `@app.handler`. Both keep working as-is.
- No import-path rewrites are strictly required. The behavioral surface (trust signing/audit/posture semantics) is what the test suite must re-validate.

### F3 — `@app.handler` UserWarning is FIXED upstream

The "Instance-based API usage detected" `UserWarning` (kailash-py #1071/#1012, closed COMPLETED) is **gone on 2.29.3** — confirmed by probe. After the upgrade, the scoped suppression in `pyproject.toml` (`"ignore:Instance-based API usage detected:UserWarning"`) MUST be removed (zero-tolerance Rule 1 — don't carry a suppression for a fixed upstream issue).

### F4 — AsyncLocalRuntime ResourceWarning is STILL PRESENT

`nexus.Nexus.close()` still does **not** cascade-close the internal `AsyncLocalRuntime` on 2.29.3 — the `__del__` "Unclosed AsyncLocalRuntime" ResourceWarning still fires at GC. The upgrade does **not** fix this. Disposition: keep the `"ignore:Unclosed AsyncLocalRuntime:ResourceWarning"` suppression OR file the upstream issue (it's a genuine current bug — verified against latest, so it is fileable without staleness). Tracked as P6 / a separate decision.

---

## Migration plan

1. **Branch + bump** (`release/`-style is not applicable — this is a dependency bump, use `chore/kailash-upgrade`):
   - `pyproject.toml`: `kailash[nexus,kaizen,dataflow,pact,shamir]>=2.13.4` → `>=2.29.3` (or uncapped `>=2.29` per `dependencies.md` "latest versions"). ~~Keep the extras set unchanged.~~ **EXECUTION OUTCOME (2026-06-10): the `trust` extra WAS added** — `kailash[nexus,kaizen,dataflow,pact,shamir,trust]>=2.29.3`. 2.29.3 carved `pynacl`/`cryptography` out of the default install into `[trust]` (they shipped by default in 2.13.4); without it every `kailash.trust.*` signing path raises `ImportError: PyNaCl is required` (415 test errors). `[trust]` is the declared `pynacl` provider per `dependencies.md` § Declared=Imported. See `04-validate/redteam-convergence.md`.
2. **Resolve + sync**: `uv lock --upgrade-package kailash` then `uv sync`. Confirm `kailash-nexus` (the now-separate dist) resolves via the `[nexus]` extra. `uv pip check` clean.
3. **Collection gate**: `uv run pytest --collect-only -q` exits 0 (the 1864-test corpus collects against 2.29.3).
4. **Full suite** (the load-bearing step): `uv run pytest tests/ --cov=envoy --cov-fail-under=90`. Triage every failure — these are the behavioral deltas across 16 versions. Highest-risk areas (by envoy's dependency depth): trust signing (`InMemoryKeyManager.sign_with_key`/`verify` byte-format), audit store (`SqliteAuditStore` row shape), posture (`SQLitePostureStore`), cascade-revoke (`cascade_revoke` result shape), Shamir (`serialize_shard`), chain (`TrustLineageChain`). Fix behavioral regressions in envoy adapters, NOT by pinning back (zero-tolerance Rule 4).
5. **Type gates**: `uv run mypy envoy/` + `uv run pyright envoy/` clean against the new stubs (the kailash type surface may have shifted).
6. **Drop the fixed suppression**: remove the `@app.handler` `UserWarning` filterwarnings entry from `pyproject.toml` (F3). Re-run the suite to confirm no new `UserWarning` surfaces.
7. **AsyncLocalRuntime disposition** (F4): keep the suppression (still-current bug) OR file upstream + keep suppression with the issue link — decide at execution.
8. **Walk + gates**: user-flow walk on the 2 Nexus surfaces (S8 library_app + S10 ohttp_server) — build the apps, confirm handlers register, close cleanly. Reviewer + security-reviewer at the `/implement` gate. CI on py3.11 + py3.13 (the `changes` filter WILL fire — `pyproject.toml` + `uv.lock` are code-paths — so the full test matrix runs as the merge gate).

---

## Risk & mitigation

| Risk                                                                                                                                        | Likelihood                         | Mitigation                                                                                                                                          |
| ------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Behavioral delta in `kailash.trust.*` signing/audit/posture breaks envoy's trust substrate                                                  | MED — 16 versions, deep dependency | Full suite is the detector; envoy's own trust tests (`tests/**/trust*`, `tests/**/grant*`, `tests/**/ledger*`) are dense. Triage + fix in adapters. |
| `uv.lock` resolution conflict among the 5 extras at 2.29.3                                                                                  | LOW                                | `uv lock --upgrade` re-solves; `dependencies.md` § phantom-transitive protocol if a conflict surfaces.                                              |
| Type-stub drift (mypy/pyright)                                                                                                              | LOW-MED                            | Both are CI gates; fix at upgrade time.                                                                                                             |
| The S4r H1 fix depends on `InMemoryKeyManager.sign_with_key`/`verify` semantics; a byte-format change would break the new authenticity gate | MED — security-critical            | The S4r authenticity tests (`TestResolutionAuthenticity`) are the detector; they assert real sign→verify round-trips. A break fails loudly.         |

---

## Sizing

- **Import/code migration: ~0** (import-compatible). Possibly a few import-path modernizations (optional, e.g. `sqlite_pool` → `nodes.data.async_sql`) — cosmetic, not required.
- **Behavioral triage: the variable** — 0 to ~1 session depending on how many of the 1864 tests surface deltas. Plausibly low (envoy uses stable trust primitives), but unbounded until the suite runs against 2.29.3.
- **Total: 1–2 sessions**, single shard if behavioral deltas are few; split into "bump+green" then "drop-suppressions+walk" if the suite triage is heavy.

---

## Open decisions (for execution time)

1. **Pin form**: `>=2.29.3` exact-floor vs `>=2.29` minor-floor vs uncapped. Recommend minor-floor `>=2.29.3` (concrete floor for the features/fixes envoy now depends on; `dependencies.md` discourages caps).
2. **AsyncLocalRuntime (F4)**: file the upstream issue now (verified current) OR keep suppression silently. Pairs with the P6 decision.
3. **Scope vs Phase-02**: run this BEFORE resuming Phase-02 Wave-2 batch-2 (cleaner — batch-2's S8e/S9a touch the same trust + Nexus surface, so upgrading first avoids re-validating twice) OR AFTER (defer churn). Recommend BEFORE — the upgrade de-risks every subsequent Phase-02 shard and drops the @app.handler suppression the WS-4/WS-5 Nexus shards keep tripping.

---

## Provenance

Scoped 2026-06-10 from the P6 upstream-advisory investigation. Evidence probed against kailash 2.29.3 in throwaway venvs (cleaned). Reframes the earlier "16 versions behind = big migration / Nexus restructured" concern: the restructure is transparent to consumers using the `[nexus]` extra. The genuine deltas are (a) the fixed `@app.handler` warning and (b) the still-open AsyncLocalRuntime leak — neither blocks the upgrade.
