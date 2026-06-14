---
type: DECISION
date: 2026-06-14
created_at: 2026-06-14T00:00:00Z
author: co-authored
session_id: continue-batch3-s5o
project: phase-02-distribution
topic: cross-repo authorization — file P10 upstream kailash-py Python-3.14 issue
phase: codify
tags:
  [
    cross-repo-authorized,
    upstream-issue,
    kailash-py,
    python-3.14,
    p10,
    repo-scope-discipline,
  ]
relates_to: 0015-DISCOVERY-kailash-py314-annotate-func-incompat
---

# DECISION — cross-repo authorization to file P10 (kailash-py Python-3.14 issue)

Receipt-before-acting per `rules/repo-scope-discipline.md` § User-Authorized
Exception (all five conditions) + `rules/upstream-issue-hygiene.md` MUST-1
(human gate, same session). This entry lands BEFORE the `gh issue create`
command runs.

cross-repo-authorized: terrene-foundation/kailash-py

## Authorization record

- **Requester (human):** the co-owner (git user Jack Hong), this session.
- **Target repo:** `terrene-foundation/kailash-py` (PUBLIC — existence-checked
  via `gh repo view` before acting, per `verify-resource-existence.md` MUST-1).
- **Action (bounded, exact):** ONE `gh issue create` filing the
  Python-3.14 `get_namespace_annotations` defect (P10). No other cross-repo
  action is authorized by this receipt — no edits, no comments, no sibling
  cross-filing (`upstream-issue-hygiene.md` MUST NOT auto-cross-file).
- **Confirmed:** the agent restated the action + target AND presented the exact
  scrubbed issue body; the co-owner confirmed the body clean before submission.

## Verbatim instructions

1. To the question "approve the upstream kailash-py Python-3.14 filing?":
   > approved
2. To the question "Is this body clean to file? (yes / edit)" (the full scrubbed
   body having been presented inline):
   > yes

## Scrub compliance (`upstream-issue-hygiene.md` Rule 2 + Rule 3)

The filed body carries ONLY the kailash public-API surface:
`kailash.utils.annotations.get_namespace_annotations` (root) +
`kaizen.signatures.core.Signature` (consumer). It contains NO downstream
context — no project name, no `envoy/` or `workspaces/` paths, no finding tags,
no shard IDs, no journal references, no PR numbers. Five Rule-3 sections only
(Affected API / Minimal repro / Expected vs actual / Severity / Acceptance
criteria). Severity is rated on SDK-API-surface impact (HIGH on 3.14, none
≤3.13), not consumer-business impact.

## Technical substance (verified)

Root cause confirmed against installed source
(`kailash/utils/annotations.py:67-73`): the helper reads
`namespace.get("__annotations__")` then `namespace.get("__annotate__")`; PEP 749
(Python 3.14 final) renamed the class-namespace lazy annotate callable to
`__annotate_func__` (eager cache → `__annotations_cache__`), so both lookups
miss and the helper falls through to `return {}`. The sibling
`get_class_annotations` (wraps `inspect.get_annotations`) is already 3.14-robust.
Repro's expected-half verified live on Python 3.13.7
(`get_namespace_annotations` returns `{'x': int, 'y': str}`); the 3.14 actual
(`{}`) is carried from the `journal/0015` discovery (the regression canary
failed on the 3.14.3 worktree venv) + the source analysis above.

The downstream fix already shipped (PR #93: `.python-version` pin to 3.13 + CI
`UV_PYTHON` per matrix leg); the upstream defect is kailash's to fix. P10 moves
from "AWAITING USER APPROVAL" to "FILED" once the `gh issue create` lands; the
filed issue URL is appended to the ledger.
