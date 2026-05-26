---
type: DISCOVERY
date: 2026-05-26
created_at: 2026-05-26T22:00:00.000Z
author: co-authored
session_id: continuation-of-92477210
project: phase-01-mvp
topic: Wave-4 channels foundation /redteam convergence (5-round trajectory)
phase: redteam
tags: [wave-4, channels, redteam, convergence, autonomous-execution-rule-4]
---

# Wave-4 channels foundation /redteam convergence — PR #42

**HEAD at convergence:** commit `<R5-polish-SHA>` (channels foundation +
4 rounds of same-shard closures + 1 LOW-polish commit).

**5-round 3-axis trajectory** — channels foundation shard required 4 closure
commits to reach CLEAN at CRIT+HIGH across all 3 axes simultaneously. Each
round surfaced new sibling-site issues created by the prior round's closures
themselves — the recurring "fix one path, sibling path re-introduces the
same bug class" pattern.

## Per-round verdict matrix

| Axis      | R1                | R2                  | R3                  | R4                        | R5        |
| --------- | ----------------- | ------------------- | ------------------- | ------------------------- | --------- |
| Security  | 4H + 5M + 4L      | 3H + 5M + 2L        | **CLEAN** + 6M + 4L | 1H + 3M + 2L              | **CLEAN** |
| Reviewer  | 1C + 4H + 6M + 5L | **CLEAN** + 2M + 2L | 2H + 2M + 2L        | 2H + 1M + 1L              | **CLEAN** |
| Spec-comp | 2H + 5M + 3L      | **CLEAN** + 6L      | **CLEAN** + 3M + 2L | 1M + 1pre-existing H + 4L | **CLEAN** |

All 5 rounds dispatched via 3 parallel general-purpose / reviewer /
security-reviewer agents per `rules/agents.md` § Parallel Execution.

## Closure cycle pattern — what each round taught

**R1 → R2:** R1 surfaced 1 CRIT + 8 HIGH across 3 axes; closures landed
30 net new tests pinning the defenses. R2 then surfaced **3 new HIGH
sibling-site bypasses** — the R1 closures shipped defenses-in-depth on
`send_grant_moment` but the new `render_grant_moment` + `_resolve_pending_decision`
sibling sites carried the same bug class. Defense-in-depth at one
surface ≠ defense-in-depth at the family.

**R2 → R3:** R2 introduced its own sibling-site regressions. R3 caught
two HIGH (H-R3-1: dead H-03 check via phantom `high_stakes` attribute
on a dataclass that uses `novelty_class` discriminator; H-R3-2: typo
`approve_author` in the closed vocabulary). R2 tests passed only
because they were written against a duck-typed shim that carried the
phantom field.

**R3 → R4:** R3 closed the code-level vocabulary canonicalisation but
missed the spec-level full-sibling re-derivation per
`rules/specs-authority.md` Rule 5b — `specs/channel-adapters.md:94`
still cited the 5-member typo vocab. R4 also caught an asymmetric
`if request_id is None` guard on Web (CLI used `if not request_id`),
plus 5 pre-existing phantom test-file citations.

**R4 → R5:** R4 closures were tight; R5 verified all 3 axes CLEAN at
CRIT+HIGH. R5 surfaced 1 MED in OTHER specs (boundary-conversation,
ui-platform, data-model, network-security, envelope-model — 8 phantom
citations in main, pre-existing) + 1 LOW (stale docstring line numbers
in envelope.py, polished in this commit).

## Final delivery

- **Code surface (envoy/channels/, 6 files):** `ChannelAdapter` ABC + 8-field
  `InboundMessage` envelope + 11 spec § Error taxonomy errors + 4
  adapter-internal hygiene errors (NotStartedError, PendingDecisionsCeilingError,
  InvalidDecisionError, PhaseDeferredError) + 1 base = 16 typed errors total.
  Two concrete adapters: `CLIChannelAdapter` (terminal stdin/stdout)
  - `WebChannelAdapter` (localhost HTTP + WebSocket with Origin allowlist
  - bounded in-flight DoS defense + canonical-vocabulary enforcement).

- **Spec surface (specs/channel-adapters.md):** § Adapter contract +
  § Message envelope + § ChannelCapabilities + § Phase 01 surfaces +
  § Cross-channel session continuity + § Primary-channel binding +
  § Side-channel hygiene + § Network security + § Error taxonomy (with
  adapter-internal hygiene sub-table) + § Cross-references + § Test
  location restructured into "Shipped today" + "Forward-declared for
  Wave-A/B sibling shards" with workspace-todo pointer for the 5
  deferred regression tests.

- **Test surface (tests/integration/channels/):** 106 Tier-2 tests
  across 8 files — adapter contract pins + CLI/Web lifecycle pins +
  4 /redteam round closure pin files (R1/R2/R3/R4).

- **Full suite:** 1271+ passed, 9 skipped (was 1166 + 9 pre-Wave-4-channels).

## Key invariants this shard established

1. **Canonical discriminator usage**: `render_grant_moment` reads
   `novelty_class == "high_stakes"` + `primary_only is True` from the
   real `GrantMomentRequest` dataclass; `send_grant_moment` reads
   `grant.high_stakes` from the channels-layer `GrantMomentPayload`.
   Two distinct surfaces, two distinct discriminator paths, both
   structurally enforced.

2. **Closed-vocabulary derivation**: `_ALLOWED_DECISIONS = frozenset(typing.get_args(GrantMomentDecision))`
   eliminates the drift class entirely. Future Literal additions
   propagate to the adapter-boundary check automatically.

3. **Single write-site enforcement**: `_register_pending(request_id)`
   is the sole `_pending_decisions` mutation site; both `send_grant_moment`
   and `render_grant_moment` route through it. Ceiling-check applies
   uniformly.

4. **Constructor-side sanitization for attacker-influenced inputs**:
   `InvalidDecisionError.__init__` truncates `decision` to 32
   printable-ASCII chars at construction (CWE-117). The defense
   inherits to every future call site, not just the present one.

5. **PII hashing in log emissions**: `_hash_pii(value)` SHA-256
   truncated to 8 chars on every `session_id` + `target_principal_id`
   field per `rules/observability.md` Rule 8.

6. **Module-load assertion for default allowlist**: `assert _DEFAULT_ALLOWED_ORIGINS`
   fires loudly at import if a future maintainer empties `_DEFAULT_DEV_PORTS`.

7. **Spec deviation acknowledgement**: `GrantMomentReceipt` extends
   spec's 4-field shape with `request_id` (correlation token); the
   extension is documented inline per `rules/specs-authority.md` Rule 6.

## For Discussion

- **5-round closure depth — is this Wave-4 channels foundation more
  invariant-dense than Wave-4 runtime?** The Wave-4 runtime facade
  converged in 4 rounds (per journal-0035). Channels needed 5 — the
  extra round was driven entirely by sibling-site regressions in the
  closure commits themselves (R2 introduced render_grant_moment which
  re-opened bypasses; R3 introduced a typo while documenting the
  vocabulary). Should the Wave-A parallel shards (Telegram + Slack +
  Discord) pre-emptively sweep the canonical discriminator + closed
  vocabulary + single-write-site invariants at design time to skip the
  R2-equivalent round?

- **MED-R5-01 sibling-spec phantom citations (8 across 5 specs)** — these
  are pre-existing on main and not introduced by PR #42. Per
  `rules/zero-tolerance.md` Rule 1a (scanner-surface symmetry), they
  flag in /redteam regardless. Should the next session run a
  cross-spec sweep extracting all phantom test citations to workspace
  todos following the precedent PR #42 set, OR is the Phase-00 spec
  freeze immutability invariant authoritative? Per the existing
  `specs/_index.md` policy, spec edits trigger full-sibling
  re-derivation per Rule 5b — so the precedent supports the sweep.

- **Forward-declared workspace todo precedent** — PR #42 created
  `workspaces/phase-01-mvp/todos/active/wave-4-channels-regression-tests.md`
  as the home for the 5 deferred regression tests. Should this pattern
  generalize: spec § Test location MUST cite only tests that exist
  today; forward-declared tests live in workspace todos with
  Wave-{N}-owner annotation?

## Cross-references

- [[0035-DISCOVERY-redteam-wave-4-runtime-facade-convergence]] —
  prior Wave-4 convergence record (4 rounds; runtime facade shard).
- [[0036-DECISION-wave-4-grant-moment-runtime-facade]] — runtime
  facade landing rationale (PR #41).
- [[0037-DECISION-wave-4-r1-r2-same-shard-closures]] — Wave-4 runtime
  R1+R2 closure rationale.

## Commits in this shard

- `e3b3d37` — channels foundation (ABC + envelope + 11 errors + CLI/Web)
- `a5e9d67` — promote 2 pending DECISION journal entries
- `c701442` — /redteam R1 same-shard (1C + 8H + 15M closures)
- `235c540` — /redteam R2 same-shard (3H + 7M + 2L closures)
- `56cadbd` — /redteam R3 same-shard (2H + 6M + 4L closures)
- `2e2445f` — /redteam R4 same-shard (3H + 4M + 6L closures)
- `<R5-polish-SHA>` — R5 LOW-R5-01 polish + this convergence journal entry
