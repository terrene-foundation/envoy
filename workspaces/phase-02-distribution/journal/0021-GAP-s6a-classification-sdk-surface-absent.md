---
type: GAP
date: 2026-06-14
author: agent
project: phase-02-distribution
topic: S6a blocker — ClassificationPolicy/masking SDK surface absent from kailash 2.29.3 binding + todo↔adapter drift on classifier-ensemble shard ownership
phase: implement
verified_id: 548F2C562EB4246D025FA80A70552B124755B685
tags:
  [
    gap,
    s6a,
    classification,
    sdk-surface,
    verify-resource-existence,
    spec-accuracy,
    framework-first,
    blocker,
  ]
relates_to: 0019-DISCOVERY-batch3-reusable-patterns-codify
---

# GAP — S6a's named SDK surface is absent from the installed binding

Recorded during the session that picked up S6a as the next serial WS-6 shard.
Empirical verification (the `journal/0019` Pattern 2 discipline applied to the
S6a seam) surfaced a blocker and a shard-ownership drift that the resumed S6a
decision MUST inherit. **No S6a code was written; the disposition is pending a
user decision** (this session was directed to `/codify` first).

## What S6a's todo + spec assume

`todos/active/02-m2-ws6-durable-substrate.md` § S6a and `specs/classification-policy.md`
both center on **"a real `ClassificationPolicy` from kailash-dataflow"**: the
`@classify` decorator, `apply_read_classification` masking
(Redact/LastFour/Hash/NullOut), the canonical 5-enum
(`Public|Internal|Confidential|Restricted|HighlyConfidential`), and the T-005
classifier-ensemble fail-closed defense. The S6a acceptance criteria say
`classifier_invoke`/`ensemble_aggregate` (`kailash_py.py:395,401`) "stop raising
`Phase02SubstrateNotWiredError`."

## What is actually true in the installed SDK (verified live, not from docs)

Verified by `import kailash` + a full-package grep, per
`verify-resource-existence.md` MUST-2 (cite the live surface, not the spec's
claim):

- Installed binding is **`kailash` 2.29.3** (`.venv/.../kailash/__init__.py`).
- **Absent:** `ClassificationPolicy`, `MaskingStrategy`, `apply_read_classification`,
  a `Classification` 5-enum, the `HighlyConfidential` literal, and any
  `kailash.dataflow` / `kailash.classification` module. Full-package grep =
  zero hits.
- **Present:** the PACT envelope/clearance surface under `kailash.trust.pact` —
  `intersect_envelopes`, `ClearanceSpec`, `ClearanceStore`, `effective_clearance`,
  `can_access`, `compute_effective_envelope`, `RoleClearance`. So the
  **structural** half of `envelope_check` is buildable on a surface that exists;
  the **classification-masking** half is not.
- The spec's "kailash-py ✅ functional `apply_read_classification`" line
  (`classification-policy.md:56-57`) refers to the _pure-Python_ `kailash-py`
  package and tracks rs-binding exposure at `kailash-rs#514` — which has **not
  shipped to this binding**. This is the two-package confusion: envoy consumes
  the Rust-backed `kailash` binding, not the py SDK.

This is the absent-resource / phantom-citation failure mode
(`spec-accuracy.md` MUST-1, `verify-resource-existence.md` MUST-1/2). Building
S6a as written would require reimplementing a framework concern inside envoy,
which `framework-first.md` + `zero-tolerance.md` Rule 4 forbid.

## Shard-ownership drift (three sources disagree)

- **S6a todo** says S6a wires `classifier_invoke`/`ensemble_aggregate`.
- **Both adapters' docstrings** say those wire in **S6c**:
  `kailash_rs_bindings.py:444-465` (`_substrate_not_ready("classifier_invoke",
"S6c", ...)`); `kailash_py.py` ties them to `_TODO_WAVE_3`. `envelope_check`'s
  own docstring (`kailash_py.py:282-286`) calls the ensemble "Wave 3".
- **Conformance xfails:** 75 cite S6a (the `envelope_check` engine —
  `tests/conformance/n1_n3_vectors.py`, `e5_e7_vectors.py`); 41 cite S6c.

So S6a's value (unblocking 75 conformance xfails) is the **structural
`envelope_check`** half, which the present PACT surface can back; the
**classification-masking + T-005 ensemble** half the todo bundles into S6a is
both absent from the binding AND attributed to S6c by the code.

## Disposition (PENDING — do not action without the user)

The session surfaced three options to the user (split S6a / file upstream first
/ pick a different shard) and the user chose **"`/codify` first"** — i.e. capture
this finding before resolving S6a. The recommendation on the table when the S6a
decision resumes:

- **Split S6a along the line the SDK already draws:** build the structural
  `envelope_check` engine now on the present PACT surface (`intersect_envelopes`
  - clearance) → unblocks the bulk of the 75 xfails; **realign** the
    classification-masking + T-005 ensemble half to S6c (where the adapters
    already place it), gated on the upstream binding `kailash-rs#514`; correct
    `classification-policy.md:56-57`'s misleading "kailash-py ✅" claim for this
    binding.
- Filing an upstream `kailash-rs` issue for the missing binding surface is
  **human-gated** (`upstream-issue-hygiene.md` + `repo-scope-discipline.md` —
  envoy is a downstream consumer; cross-repo filing needs an explicit
  user-authorized, journaled grant).

## For Discussion

1. The split realigns S6a to "structural `envelope_check` only" and moves
   masking/T-005 to S6c. Does that leave a subset of the 75 S6a-cited xfails
   (the masking-specific N4 rendered-text or clearance-masking vectors) stuck at
   xfail until `kailash-rs#514` ships — and if so, is the conformance corpus's
   S6a-vs-S6c xfail tagging granular enough to flip only the structural lanes,
   or does it conflate both halves under one `S6a` reason string?
2. `classification-policy.md` asserts an SDK surface (`apply_read_classification`,
   the 5-enum) that the installed binding does not expose. Per
   `spec-accuracy.md` MUST-1 a spec MUST describe what ships today. Should the
   spec be corrected to describe the PACT clearance surface that IS present
   (with masking marked out-of-scope-this-binding), or does correcting it
   require first confirming whether `kailash-rs#514` is imminent (changing the
   correction from "remove" to "describe-as-pending-binding")?
3. The drift (todo says S6a, adapters say S6c) means the `/todos` plan and the
   landed adapter code disagree on shard ownership. Per `specs-authority.md`
   Rule 5c the orchestrator amends the todo at launch when the code has moved —
   but here the divergence is a genuine scope question, not a stale version
   string. Is the right fix to amend the S6a/S6c todo boundary in the milestone
   file as part of the resumed decision, so the next launch reads a todo that
   matches the code?
