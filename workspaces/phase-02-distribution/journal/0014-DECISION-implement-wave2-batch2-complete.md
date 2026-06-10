---
type: DECISION
date: 2026-06-10
created_at: 2026-06-10T16:20:00Z
author: co-authored
session_id: continue-from-upgrade
project: phase-02-distribution
topic: /implement Wave 2 batch-2 (S8e + S9a + S4i) complete and merged
phase: implement
tags:
  [
    implement,
    wave-2,
    S8e,
    S9a,
    S4i,
    enterprise,
    skill-ingest,
    init-cli,
    parallel-worktree,
    security-fix,
  ]
---

# Wave 2 batch-2 COMPLETE — S8e + S9a + S4i merged (PR #93)

## What landed

Three dependency-satisfied shards across two milestones, built as a parallel
worktree wave of 3 (disjoint file sets: `envoy/enterprise/` vs
`envoy/skill_ingest/` vs `envoy/cli/` + `envoy/boundary_conversation/`),
integrated onto `feat/wave2-batch2`, merged to `main` (`d0d5bf4`, PR #93, CI
green py3.11 + py3.13):

- **S8e (M3 / WS-4)** — `envoy/enterprise/`: EnterpriseDeploymentRecord schema
  (closed scope enum, parse-time enforcement), 6-step import-time verifier,
  REQUIRED dual-sign gate (`EnterpriseDualSignMissingError` at parse time —
  the T-024 abuser-IT vector fails before any signature math). Signature
  checks route through the shared S8 `verify_steward_quorum` as 1-of-1
  (single-helper AST gate stays green). Step-2 verifies against the RESOLVED
  org-root key from injected `known_org_roots`, NOT the record-supplied key.

- **S9a (M3 / WS-4)** — `envoy/skill_ingest/` (~1,760 LOC): SKILL.md parser,
  ENVELOPE.md companion generator, conservative AST permission-inference walk
  (literal-call-only; static `ast.parse`, never executes skill code;
  unparseable → fail-closed), asymmetric score routing (literal undeclared →
  0.3 reject; import-graph-only → 0.65 warn; over-declare → 0.85 +
  `OverPrivilegeWarning`, NOT a reject), CO validator steps 1/2/4/6 + typed
  `AdversarialCheckPending` step-5 surface (S9b flips it live). Corpus
  deliverable: 103 checked-in fixtures. **Exit-criterion gate: 100/100 benign
  accepted (zero false-reject), 3/3 adversarial refused** — including the
  AST-visible dynamic-dispatch sample, so the milestone does not depend on
  S9b for any AST-visible case (ROADMAP §108 accountability split honored).

- **S4i (M2 / WS-6)** — `envoy init` (8th of 10 canonical CLI commands):
  Boundary-Conversation bootstrap drives S1..S9 → durable write-once genesis
  `SessionObservedState` keyed `genesis:<principal_id>` in the S4s store;
  `trust-anchor.json` (`envoy-trust-anchor/1.0`, public material only,
  0o600-at-create) co-emitted per independent-verifier channel #1; idempotent
  re-init (`VaultAlreadyInitializedError` → clean exit 30). The strict-xfail
  CLI tripwire flipped as designed; `init` registered in
  `REGISTERED_AS_OF_F5` in the same PR. User-flow walk receipts in the PR
  description.

## Security findings fixed in-PR (fix-immediately discipline)

- **E-1 (MEDIUM, security-reviewer)** — EDR signatures originally covered
  only `template_envelope_hash`, allowing signature TRANSPLANT across EDRs
  (same hash, mutated scope/employee/org). Fixed: both signatures now bind
  the full canonical record via `EnterpriseDeploymentRecord.signing_payload()`
  (sha256 over RFC-8785 canonical bytes of every field except `signatures`,
  reusing `envoy/envelope/canonical_bytes.py` — no parallel canonicalizer).
  Regression: `TestT024SignatureTransplant` (3 tests).
- **MED (reviewer)** — future-dated `enabled_at` bypassed the step-5 365-day
  window (negative age passes a one-sided check). Fixed: two-sided window
  with documented 5-minute `FUTURE_DATED_SKEW_TOLERANCE`; future-dated →
  `EnterpriseDeploymentRecordInvalidError` (never validly attested ≠ revoked).
- LOW fixes: init CLI exit/error log lines + correlation id; base64 import
  hoist. Security LOWs S-1/S-2/I-1 dispositioned in the PR (justified /
  acceptable / bounded by `TrustVault.create` — I-1 needs a transactional
  write-once at the store layer IF multi-device ever relaxes the vault gate).

## Gate receipts

- Full suite post-merge: **2040 passed, 9 skipped (infra-conditional),
  2 xfailed (chat/grant tripwires)**; `mypy envoy` + `pyright envoy/` clean.
- reviewer: APPROVE (6/6 mechanical sweeps); security-reviewer: APPROVE.
- Follow-up PR #94 (`395e4a9`): repo-wide ruff debt swept — `ruff check .`
  is now clean repo-wide (195 pre-existing errors fixed; 6 justified
  `# noqa: E402`), making it usable as a session gate.

## Decisions flagged for spec authority (all reconciled in PR #93)

1. EDR step-2 anchor = resolved org-root pubkey (injected `known_org_roots`).
2. EDR signed payload = full canonical record digest (E-1).
3. CO score anchors 0.3/0.65/0.85/1.0; `http-get:<domain>` recognized;
   `oauth:` under `operational` axis; financial/temporal never populated by
   SKILL.md ingest.
4. Genesis key convention `genesis:<principal_id>`, write-once, blob
   `session-state/1.0` (posture PSEUDO, envelope version 1) —
   `specs/session-runtime.md` § Genesis write.

## Interrupted-wave recovery note

The wave was interrupted mid-flight by an account session limit (2 of 3
agents stalled; S4i had ZERO commits — all work uncommitted in its worktree).
Recovery: account swap → resume-with-context + explicit commit-first
instruction. Lesson reinforced: worktree commit-per-milestone discipline is
what makes an interrupted wave recoverable; S4i's zero-commit state was one
worktree-prune away from total loss. Secondary trap hit twice: the
orchestrator shell's persistent cwd drifted into agent worktrees after
background-agent completions — verify `pwd`/`git rev-parse --show-toplevel`
before any branch operation in the main checkout.

## Next

Wave-2 batch-3: M1 conformance families S2b/S2c/S3a/S3b (unblocked by S2a ✅)
and the WS-6 serial chain (S4g-1 → S5b → S5o → S6a/b → S6c). S9b stays
substrate-gated on S6a. S7v unblocks at S3b.
