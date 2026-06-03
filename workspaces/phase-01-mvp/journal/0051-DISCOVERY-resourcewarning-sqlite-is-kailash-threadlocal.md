---
type: DISCOVERY
date: 2026-06-03
created_at: 2026-06-03T00:00:00Z
author: co-authored
session_id: envoy-2026-06-03
session_turn: resourcewarning-residual-diagnosis
project: phase-01-mvp
topic: "ResourceWarning sqlite class root cause = kailash SQLitePostureStore thread-local connections + thread-scoped close(); not fixable from envoy"
phase: implement
tags:
  [
    F22,
    resourcewarning,
    test-hygiene,
    kailash,
    third-party,
    upstream,
    observability,
  ]
---

# 0051 — DISCOVERY: the `unclosed sqlite` ResourceWarnings are a kailash thread-local-connection limitation

## Context

F22 (ResourceWarning suite cleanup). PR #76 fixed the `TrustVault GC'd while
unlocked` class (envoy test code — round1 + session-continuity). The residual
classes after #76: `unclosed sqlite connection` (CI-relevant), `unclosed socket
→ 127.0.0.1:11434` (Ollama; CI-invisible), `unclosed event loop` (1).

This entry records the root cause of the **sqlite class**, so the next session
does not repeat the multi-turn diagnosis.

## Key discoveries (each non-obvious, cost real effort)

1. **ResourceWarning attribution is GC-timed, not allocation-site.** The warning
   fires when the GC collects the leaked object — during whatever test happens
   to be running then. So "test X shows N warnings" is misleading: l03 (a pure
   dataclass test), t019 (closes its store), and bc-min (yield+close fixtures)
   all "showed" warnings but were innocent bystanders. Fixes MUST target the
   allocation site, not the warning-attributed file.

2. **The sqlite leaks are kailash-internal, not envoy test bugs.** A per-file
   audit confirmed every envoy test that `initialize()`s a `TrustStoreAdapter`
   also `close()`s it; durable ledgers are `aclose()`d. Yet sqlite connections
   leak. Root cause: `kailash.trust.posture.posture_store.SQLitePostureStore`
   (`.venv/.../kailash/trust/posture/posture_store.py`):
   - `_get_connection()` (line 287) caches a **per-thread** connection in
     `self._local.conn` (`sqlite3.connect` at line 291).
   - `close()` (line 445) docstring VERBATIM: _"Close the calling thread's
     database connection."_ — it closes only `self._local.conn` for the calling
     thread (line 451-454).
   - envoy runs sqlite ops via `asyncio.to_thread` (executor threads). Each
     executor thread that touches the posture store opens its OWN thread-local
     connection; `store.close()` (called from one thread) closes only that
     thread's connection. Every other executor thread's connection leaks →
     `ResourceWarning: unclosed database` at GC. The same shape likely applies
     to `kailash.trust.chain_store.sqlite.SqliteTrustStore`.

## Disposition

- **Not fixable from envoy.** This is a consumer/USE repo (no kailash source).
  envoy's tests already close the store correctly; the leak is kailash's
  thread-scoped `close()`. Per `rules/repo-scope-discipline.md` we do not edit
  kailash here; per `rules/zero-tolerance.md` Rule 1 (exception) an upstream
  third-party issue unresolvable in-session is dispositioned via a documented
  upstream issue, NOT a local workaround.
- **Cannot cleanly filter.** A `filterwarnings: ignore:unclosed database` would
  also mask any FUTURE envoy-side sqlite leak (e.g. a durable-ledger pool not
  aclosed) — defeating the gate. So a blanket ignore is rejected.
- **Therefore `-W error::ResourceWarning` CANNOT be safely enabled** until the
  kailash threading limitation is fixed upstream (close-all-threads, or a shared
  connection pool with a close-all). The observability-Rule-5 gate-gap stays
  open, blocked on upstream — documented, not silently dropped.
- **Socket class** (`unclosed socket → :11434`) is httpx/Ollama (the tier3 BC
  full-path real-Ollama tests). CI-invisible (no daemon in CI). Same third-party
  shape (an httpx client not closed by the model-router path); low priority.
- **Recommended action:** file an upstream kailash issue (human-gated per
  `rules/upstream-issue-hygiene.md` — scrubbed to the kailash API surface, no
  envoy identifiers): `SQLitePostureStore.close()` should release ALL
  thread-local connections (or use a pool), so cross-thread (`asyncio.to_thread`)
  usage does not leak. Until then F22's `-W error` enablement stays blocked.

## For Discussion

1. **Counterfactual:** if envoy pinned all posture-store ops to a single
   dedicated `ThreadPoolExecutor(max_workers=1)`, would `close()` (on that one
   thread) then release the only connection — making the leak fixable
   envoy-side WITHOUT touching kailash? Is that a legitimate threading-control
   fix or a `zero-tolerance.md` Rule 4 SDK-workaround we should avoid in favor
   of the upstream fix?
2. **Data-referencing:** the upstream issue should cite the exact lines
   (`posture_store.py:287` `_get_connection` thread-local + `:445` thread-scoped
   `close`). Should `SqliteTrustStore.close()` (chain_store/sqlite.py:542) be
   audited for the same pattern and bundled into one kailash issue?
3. Does Phase-01 ship-readiness care about these warnings at all, given they are
   third-party + CI-invisible (sockets) / CI-non-fatal (sqlite, no `-W error`)?
