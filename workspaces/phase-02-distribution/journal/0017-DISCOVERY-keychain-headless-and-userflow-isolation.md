---
type: DISCOVERY
date: 2026-06-12
author: agent
project: phase-02-distribution
topic: Three reusable patterns from Wave-2 redteam — OS-keychain headless override, user-flow-walk keychain isolation, partial-construction resource-leak class
phase: codify
tags:
  [
    discovery,
    keychain,
    headless,
    user-flow-validation,
    redteam-isolation,
    resource-leak,
    bootstrap,
  ]
relates_to: 0016-DECISION-wave2-redteam-convergence
---

# Patterns the next session inherits (Wave-2 redteam)

Three cross-cutting lessons that generalize beyond the specific fixes in
journal/0016 — each will recur as Phase-02 adds the remaining CLI verbs
(`chat`, `grant`) and bootstrap paths.

## Pattern 1 — A CLI command that touches the OS keychain needs a headless backend override

`envoy init` stored signing keys in the real OS keychain (`keyring`) with no
override, so it could not run headless / in CI / under a non-interactive agent —
it errored "keychain cannot be found." The tests never hit this because they
inject a pure-dict `keyring_backend` via DI; the **CLI path had no equivalent
seam**.

**Fix shape (reuse for every keychain-touching CLI verb):** a fail-closed env
selector — `envoy/ledger/keystore.py::resolve_keyring_backend()` — closed
allowlist: unset → real OS keychain (secure default); `ENVOY_KEYRING=memory` →
in-process ephemeral backend with a loud `logger.warning`; any other value →
typed refusal. Wire it at the CLI entry, exit cleanly (code 32) on a bad
selector. The real keychain stays the default; the override is explicit opt-in.

**Generalization:** `chat` and `grant` (the remaining WS-6 CLI verbs) will also
read the session/ledger signing keys → they MUST thread the same
`resolve_keyring_backend()` seam, or they inherit the same headless foot-gun.
The connection-vault + model CLIs already use DI-injectable backends in tests
but likewise lack the CLI env override — a candidate consistency sweep.

## Pattern 2 — User-flow red-team walks must isolate the keychain, not just HOME

The Wave-2 user-flow-walk agent was told to isolate via `HOME=$(mktemp -d)`.
That is **insufficient** on macOS: the login Keychain is NOT under HOME, so
`envoy init` reached the operator's real Keychain from a background subprocess
(this is what surfaced the keychain error the co-owner saw live). The walk both
(a) risked side effects on the real Keychain and (b) errored where a real user
with an unlocked GUI Keychain would not.

**Rule for future walks (a redteam-isolation invariant):** when the walked
command touches an OS-global resource (keychain, system keyring, launchd/cron,
global config), HOME-redirection alone does not isolate it. The walk MUST either
(a) use the command's own backend-override seam (here `ENVOY_KEYRING=memory`), or
(b) read-only inspect + report the un-redirectable surface as a testability
finding — NEVER run the mutating command against the operator's real OS state.
This is the concrete instance of `rules/user-flow-validation.md` MUST-1's "walk
in an isolated environment" — "isolated" means every resource the command
touches, not just the filesystem HOME.

## Pattern 3 — Bootstrap acquisitions belong INSIDE the cleanup try (partial-construction leak class)

`build_init_runtime` acquired `vault.unlock()` + `trust_store.initialize()` +
`session_router.open()` OUTSIDE the reverse-order cleanup `try`. A failure in
any of them propagated without cleanup — leaving the `TrustVault` UNLOCKED with
the live master key resident in memory, and the SQLite handles orphaned (the CLI
caller never receives the bootstrap object, so its own `finally` cannot run).

**Fix shape (reuse for every multi-resource bootstrap):** initialize each
resource handle to `None` BEFORE the try; acquire ALL of them inside one try;
None-guard each cleanup step in reverse acquisition order; put the most
security-critical release (here `vault.lock()`) in the INNERMOST `finally` so it
runs even if an earlier `close()` raises. The sibling
`envoy/daily_digest/bootstrap.py` already had this shape + a leak-path test;
`init_bootstrap` diverged. **Audit hint:** any `build_*` / bootstrap function
that returns a multi-resource handle is a candidate — grep for acquisitions
(`unlock`/`initialize`/`open`/`connect`) that sit before the `try:` whose
`except` does the teardown.

## For Discussion

1. **Counterfactual:** if the co-owner had NOT been watching live, the keychain
   error would have surfaced only as a failed user-flow-walk agent (or silent
   real-Keychain writes). Should `rules/user-flow-validation.md` gain an explicit
   "OS-global resource isolation" clause (Pattern 2), or is that better as a
   redteam-skill checklist item? The pattern is loom-managed COC territory —
   filing it upstream would let every consumer's walks inherit the isolation
   invariant.
2. **Data-referenced:** Pattern 1 + Pattern 3 both trace to the SAME root —
   `init_bootstrap` was built without the DI/cleanup discipline its sibling
   `daily_digest/bootstrap.py` already had. Is there a structural way (a shared
   `build_service` helper, or a bootstrap-shape lint) to make the next bootstrap
   inherit both the keyring-seam and the cleanup-try shape by construction,
   rather than re-deriving them per shard at redteam time?
3. Which of `chat` / `grant` (WS-6 batch-3) should adopt the `resolve_keyring_backend`
   seam FIRST — and should that be a batch-3 acceptance criterion now, so the
   foot-gun is closed at implement time rather than re-found at the next redteam?
