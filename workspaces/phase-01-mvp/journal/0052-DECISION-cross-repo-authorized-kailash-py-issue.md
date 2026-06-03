---
type: DECISION
date: 2026-06-03
created_at: 2026-06-03T00:00:00Z
author: human
session_id: envoy-2026-06-03
session_turn: upstream-issue-filing-authorization
project: phase-01-mvp
topic: "Cross-repo authorization: file the SQLitePostureStore.close() thread-local-leak issue against kailash-py (per journal/0051)"
phase: implement
tags:
  [
    cross-repo,
    upstream,
    kailash,
    upstream-issue-hygiene,
    repo-scope-discipline,
    F22,
  ]
---

# 0052 — DECISION: cross-repo authorized — file kailash-py issue for the posture-store connection leak

Receipt-first authorization per `rules/repo-scope-discipline.md` § User-Authorized
Exception (all five conditions) + `rules/upstream-issue-hygiene.md` MUST-1 human gate.
This entry lands BEFORE the `gh issue create` command runs.

cross-repo-authorized: terrene-foundation/kailash-py

- **Requester:** repo owner (this session's user; jack@kailash.ai).
- **Verbatim instruction:** "file please" (in reply to the agent's presented,
  scrubbed upstream-issue draft + the explicit question "whether to file the
  kailash issue (and confirm the repo, e.g. `terrene-foundation/kailash-py`)").
- **Target repo:** `terrene-foundation/kailash-py` — determined authoritatively
  from the installed kailash packages' `Project-URL: Issues =
https://github.com/terrene-foundation/kailash-py/issues` (NOT guessed).
- **Bounded action (scoped exactly):** ONE `gh issue create --repo
terrene-foundation/kailash-py` with the scrubbed body below. No other
  cross-repo reads/writes; no source edits to kailash-py.
- **Confirmed:** agent proposed the target + action; user confirmed via "file
  please". Yes/no gate satisfied before execution.

## Filed

**`terrene-foundation/kailash-py#1245`** (2026-06-03) — scrubbed body, kailash
API surface only, zero envoy/consumer identifiers.

## What is being filed (scrubbed per upstream-issue-hygiene MUST-2/3 — kailash API surface only)

- **Affected API:** `kailash.trust.posture.posture_store.SQLitePostureStore`.
- **Bug:** `_get_connection()` caches a per-thread connection
  (`self._local.conn`); `close()` releases ONLY the calling thread's connection
  (its own docstring: "Close the calling thread's database connection"). Used
  across threads (e.g. `asyncio.to_thread`), connections opened on other threads
  leak → `ResourceWarning: unclosed database` at GC.
- **Severity:** LOW–MEDIUM (FD leak; accumulates in long-running async services).
- **Acceptance:** `close()` closes all opened connections (or a shared/pooled
  conn with close-all); no warning after cross-thread use; audit
  `SqliteTrustStore.close()` for the same pattern.

The issue body carries NO envoy / consumer identifiers, workspace paths, finding
tags, or "discovered during" provenance (provenance stays here, in this repo's
journal — journal/0051 is the full local diagnosis).

## Consequences

- F22's `-W error::ResourceWarning` enablement remains blocked until the upstream
  fix lands; tracked in `.session-notes` F22 + journal/0051.
- The filed issue number is appended to this entry's follow-up after creation.

## For Discussion

1. Should `SqliteTrustStore` (chain_store/sqlite.py) be filed as a separate
   issue or folded into this one as a sibling acceptance-criterion?
2. Once upstream fixes + a new kailash release ships, does envoy pin the minimum
   kailash version that includes the fix before enabling `-W error`?
