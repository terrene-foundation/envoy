# Wave-4 channels — forward-declared regression test surface

**Origin:** Extracted from `specs/channel-adapters.md` § Test location during /redteam R4 same-shard closures (commit `<R4-closure-SHA>`). Per `rules/spec-accuracy.md` Rule 4 (work trackers live outside specs), the 5 forward-declared regression test files moved out of the spec text — the channels foundation shard (PR #42) does NOT yet ship these tests, so citing them in the authoritative spec violated `rules/spec-accuracy.md` MUST Rule 1 (citation MUST resolve against working code).

**Wave-A/B forward-declared tests** — each lands in the sibling channel shard that exercises the corresponding threat path:

| Test file                                                  | Threat                                      | Owner shard                                |
| ---------------------------------------------------------- | ------------------------------------------- | ------------------------------------------ |
| `tests/regression/test_t018_visible_secret_per_channel.py` | T-018 visible-secret rendered every channel | Wave-A (per-channel renderer)              |
| `tests/regression/test_t070_clipboard_autoclear.py`        | T-070 30s clipboard auto-clear              | Wave-B (UI hardening)                      |
| `tests/regression/test_t080_tls13_pin.py`                  | T-080 TLS 1.3 + Foundation cert pin         | Wave-B (network security)                  |
| `tests/regression/test_t023_signal_path_b.py`              | T-023 Signal Path B legal gate enforcement  | Wave-B (Signal adapter)                    |
| `tests/e2e/test_session_continuity_8_channels.py`          | Cross-channel session continuity (EC-7)     | Wave-A/B integration (per all-channels-up) |

**Value-anchor per `rules/value-prioritization.md` MUST-2:** brief `briefs/00-phase-01-mvp-scope.md` § Exit criteria EC-7 + EC-8 — cross-channel coherence + per-channel onboarding. Each test surface gates a specific EC; the spec section `specs/channel-adapters.md` § Test location now lists ONLY the test files that ship in the channels foundation (PR #42).

**Re-pickup gate per `rules/value-prioritization.md` MUST-3:** before resuming any of these tests, re-validate the EC-7 / EC-8 anchor still applies in the user's current brief — Phase 01 may have de-scoped 6 of 8 channels per de-scope #1 fallback.

**Status:** deferred to Wave-A/B sibling shards.
