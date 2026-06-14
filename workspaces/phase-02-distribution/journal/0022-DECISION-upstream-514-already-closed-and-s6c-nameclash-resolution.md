---
type: DECISION
date: 2026-06-14
author: co-authored
project: phase-02-distribution
topic: user-authorized upstream filing → verified kailash-rs#514 already CLOSED (did NOT file); S6c name-clash resolution (S6c=chat, S6d=deferred classifier/trust surface)
phase: implement
verified_id: 548F2C562EB4246D025FA80A70552B124755B685
cross-repo-authorized: esperie-enterprise/kailash-rs
tags:
  [
    decision,
    cross-repo-authorized,
    verify-resource-existence,
    upstream,
    name-clash,
    s6c,
    s6d,
  ]
relates_to: 0021-GAP-s6a-classification-sdk-surface-absent
---

# DECISION — upstream #514 already closed (no file); S6c name-clash resolved

Two follow-ups after the S6a structural engine landed (PR #107). Receipt-first per
`rules/repo-scope-discipline.md` § User-Authorized Exception + `rules/artifact-flow.md`
§ Co-Owner-Directed Origination.

## 1. Cross-repo filing authorization + verify-finding (did NOT file)

**Verbatim user instruction (2026-06-14):** "files it. clean the name clash, then
/wrapup for fresh session to proceed." (Following the agent's offer to draft the
upstream `kailash-rs#514` binding-gap issue for approval.)

**Authorized action:** file an issue against the kailash-rs SDK repo for the
absent `apply_read_classification` / masking binding surface (the S6a-deferred
classifier/masking half, `journal/0021`).

**Verify-existence-first (`rules/verify-resource-existence.md` MUST-1/2 — existence
check precedes the action):**

- `terrene-foundation/kailash-rs` does NOT resolve. The real SDK repo is
  **`esperie-enterprise/kailash-rs`** (PRIVATE; per the operator-local CI config).
- `esperie-enterprise/kailash-rs#514` **ALREADY EXISTS and is CLOSED** (closedAt
  2026-04-24), title _"[binding] Expose `apply_read_classification()` +
  event-payload helper for DataFlow"_ — a complete spec for the PyO3 wrapper. It
  was filed during Envoy phase-00 scope analysis (its body already cross-references
  Envoy audit sources — a pre-existing entry, NOT edited here).

**Decision: did NOT file.** Filing a duplicate of a closed, well-specified tracking
issue is wrong (verify-existence-first; `verify-resource-existence.md` MUST-3 —
don't blindly proceed when the resource situation differs from the premise). The
cross-repo actions performed under the authorization were READ-ONLY existence
checks (`gh repo view`, `gh issue view 514`); NO cross-repo write occurred (the
`cross-repo-authorized` marker above records the grant + the read-only outcome).

**Corrected disposition (for the user / fresh session — NOT acted on unilaterally):**
the masking shard's blocker is NOT an unfiled issue but a binding-VERSION gap —
#514 is closed yet `apply_read_classification` is absent from the installed
`kailash` 2.29.3. Resolve by either (a) verifying which binding version shipped
#514's fix and upgrading the pin, or (b) if #514 was closed-without-shipping,
reopening / commenting on #514 (a user-gated cross-repo WRITE needing its own
explicit grant). A fresh decision the user owns.

## 2. S6c name-clash resolution (canonical id assignment)

`journal/0021` flagged "S6c" overloaded. Confirmed worse — it appears in CODE three
ways: the `chat` resident loop (`session_boundary.py`, the milestone S6c shard, the
architecture, prior journals), the classifier ensemble + semantic envelope-check
slice (`envelope_check.py`, the adapters, the conformance corpus), and the
sub-agent-delegation subset-proof verifier (`kailash_rs_bindings.py`).

**Decision — canonical assignment (historically honest):**

- **S6c = the `chat` resident receive-loop** (UNCHANGED). The architecture- and
  milestone-defined shard with a real section, DAG node, exit-gate, and the
  S5b↔S6c boundary-signal coupling already coded in `session_boundary.py`. Prior
  journals + `02-plans/01-architecture.md` lock S6c=chat (immutable history per
  `rules/journal.md`).
- **S6d = the deferred classifier / trust-verification surface** (NEW id): the
  classifier ensemble (`classifier_invoke` / `ensemble_aggregate` /
  `classifier_registry_resolve`), the `@classify` / `apply_read_classification` /
  MaskingStrategy masking, the T-005 ensemble, the N3-semantic envelope-check
  slice, and the sub-agent-delegation subset-proof verifier — all the unbuilt
  trust/classifier verifiers with no own milestone shard, gated on the rs binding
  (#514 surface). To be split into real shards at the next `/todos` re-rank.

The classifier-meaning "S6c" was the ERRONEOUS later mis-tag (the classifier was
bundled into the original S6a); renaming it → S6d aligns the code with the
architecture's S6c=chat. `_VALID_SHARD_TOKENS` becomes `{S5o, S6a, S6c, S6d}`.

## Consequences

- No upstream issue filed; the masking-shard blocker reframed as a binding-version
  question for the user.
- The classifier/semantic/subset-proof "S6c" references across active code + tests
  - specs renamed → "S6d"; `chat` stays S6c. The S6a todo amendment's "UNRESOLVED
    collision" note flips to RESOLVED.
- Immutable history (journals, `02-plans/01-architecture.md`) keeps S6c=chat — no
  retroactive rewrite; the rename touches only active code/tests/specs/todos +
  `.session-notes`.
