# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""F5 Wave-5 CLI packaging acceptance test (Tier 3 in-process subprocess).

Acceptance gate: the ``envoy`` console-script entry-point declared in
``pyproject.toml [project.scripts]`` resolves to ``envoy.cli:cli`` cleanly,
and each canonical Milestone-5 subcommand's ``--help`` invocation succeeds
at exit 0 with a non-empty help body.

Canonical CLI surface authority:

- ``specs/mvp-build-sequence.md`` line 128 (shard 19 § 3.4, reconciled in
  Round 4 per R1-M-01): ``init / chat / ledger / shamir / digest / grant /
  posture / connection / model / version`` (+ Phase-02 stubs ``upgrade`` /
  ``uninstall``). This SUPERSEDES the pre-reconciliation draft list in
  ``02-plans/01-build-sequence.md`` line 264 (``init / up / boundaries /
  ...``) — ``up`` and ``boundaries`` were never canonical; the onboarding
  command is ``chat`` (start/resume the Boundary Conversation, shard 8).

- ``02-plans/01-build-sequence.md`` Milestone 5 line 333:
  ``pipx install envoy-agent works on macOS / Linux desktop-env /
  Windows x86_64. All CLI subcommands functional.``

- ``workspaces/phase-01-mvp/briefs/00-phase-01-mvp-scope.md`` § Surfaces
  line 21: ``pipx install envoy-agent (interim distribution; Phase 02
  moves to single static binary)``.

Scope-out (explicit, per the gate-review pattern established in shard 13
PR #47 + shard 14 PR #48):

- This battery exercises only the CLI packaging-path invariant: the
  ``envoy`` console-script entry-point resolves to ``envoy.cli:cli`` and
  each Milestone-5 subcommand's ``--help`` returns exit 0 with non-empty
  help output. It does NOT exercise subcommand BEHAVIOR — that lives in
  per-subcommand integration tests landed by the shards that build each
  subcommand (``shamir`` in T-02-36; ``digest`` in the Wave-4 daily-
  digest shard; the remaining 9 in shard 19 per Wave 5 build sequence).

- The not-yet-registered subcommands (``init`` / ``chat`` / ``ledger`` /
  ``grant`` / ``connection`` / ``model``) are marked ``xfail(strict=True)``
  per ``rules/test-skip-discipline.md`` BORDERLINE tier — each xfail flips
  to XPASS as a shard wires the corresponding subcommand. The xfail
  transition list IS the Milestone-5 progress signal.

- This is the in-process subprocess shape (Option A per F5 session-start
  scope choice 2026-05-28): runs ``.venv/bin/envoy <subcommand> --help``
  as a real child process via ``subprocess.run``, asserts exit 0 + non-
  empty stdout. The release-time real-deployment-shape variant
  (Option B — ``pipx install -e .`` then run from the pipx-installed
  location) is a release smoke check, not a per-PR gate; landing it
  requires every CI runner to have ``pipx`` available.

- Platform coverage: this battery resolves the Unix ``.venv/bin/envoy``
  entry-point only and therefore runs on macOS and Linux. Milestone 5
  (``02-plans/01-build-sequence.md`` line 333) cites Windows x86_64 as
  a packaging target; Windows packaging-shape verification lives in the
  Option-B release smoke check (which exercises the ``.venv/Scripts/
  envoy.exe`` layout on a real Windows runner), not this per-PR gate.

Per ``rules/testing.md`` § Tier 3: real entry-point. Per
``rules/probe-driven-verification.md`` MUST-3: structural probes only
(exit codes + presence-of-subcommand-name in top-level help text); no
LLM-as-judge and no regex against semantic claims.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# Canonical CLI surface per ``specs/mvp-build-sequence.md`` line 128
# (shard 19 § 3.4, reconciled in Round 4 per the R1-M-01 disposition). This
# SUPERSEDES the pre-reconciliation draft list in
# ``02-plans/01-build-sequence.md`` line 264, which read
# ``init / up / boundaries / ...`` — ``up`` and ``boundaries`` were never
# canonical; the onboarding command is ``chat`` (start/resume the Boundary
# Conversation, shard 8). The spec's "11 subcommands" label is an off-by-one
# against its own 10-item list; the list membership below is authoritative.
CANONICAL_SUBCOMMANDS: tuple[str, ...] = (
    "init",
    "chat",
    "ledger",
    "shamir",
    "digest",
    "grant",
    "posture",
    "connection",
    "model",
    "version",
)

# Subcommands wired in ``envoy/cli/main.py``:
#   - ``shamir`` — T-02-36 (Wave-2 trust vault recovery)
#   - ``digest`` — Wave-4 daily-digest shard
#   - ``posture`` / ``version`` — F5.2 Shard 1 (PR #63)
#   - ``connection`` — F5.2 Shard 2 (Connection Vault CLI, PR #65)
#   - ``model`` — F5.2 Shard 3 (BYOM picker, PR #66)
#   - ``ledger`` — EC-4/EC-9 durable-export shard C (`envoy ledger export`)
#   - ``init`` — Phase-02 WS-6 shard S4i (Boundary-Conversation bootstrap)
#   - ``grant`` — Phase-02 WS-6 shard S4g-1 (cross-process Grant Moment answer)
# ``chat`` was wired by Phase-02 WS-6 shard S6c (the resident receive-loop, LAST)
# — the full canonical surface (10 of 10) is now registered. When a shard wires a
# subcommand, append it here — the strict xfail in the parametrized test flips to
# XPASS and CI fails loudly, forcing this update in the SAME PR that wires it.
REGISTERED_AS_OF_F5: frozenset[str] = frozenset(
    {
        "shamir",
        "digest",
        "posture",
        "version",
        "connection",
        "model",
        "ledger",
        "init",
        "grant",
        "chat",
    }
)


def _repo_root() -> Path:
    """Path of the repo root (parent of ``tests/``)."""
    return Path(__file__).resolve().parent.parent.parent


def _venv_envoy() -> Path:
    """Resolve the ``.venv``-installed ``envoy`` entry-point.

    Per ``rules/python-environment.md`` MUST Rule 1: bare ``envoy``
    resolves through the shell's PATH which may be a pyenv shim. The
    test MUST address the ``.venv``-installed binary explicitly so the
    assertion runs against THIS checkout's ``envoy.cli:cli``, not a
    globally-installed sibling.
    """
    return _repo_root() / ".venv" / "bin" / "envoy"


@pytest.fixture(scope="module")
def envoy_bin() -> Path:
    """Locate ``.venv/bin/envoy``; skip the suite if absent (uv sync hasn't run).

    Per ``rules/test-skip-discipline.md`` ACCEPTABLE tier: the skip
    reason names the constraint (the ``.venv`` is not present) and the
    operator's action (``uv sync``).
    """
    bin_path = _venv_envoy()
    if not bin_path.exists():
        pytest.skip(
            f"`.venv/bin/envoy` not found at {bin_path}; run `uv sync` to "
            f"install the editable entry-point before running this battery."
        )
    return bin_path


def _run_help(envoy_bin: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run ``<envoy_bin> *args`` with a 30 s timeout; return CompletedProcess.

    Tier-3 invocation: real subprocess against the real entry-point.
    """
    return subprocess.run(
        [str(envoy_bin), *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_envoy_top_level_help_exits_clean(envoy_bin: Path) -> None:
    """``envoy --help`` exits 0 with a non-empty help body listing wired subs.

    Structural probe (per ``rules/probe-driven-verification.md`` MUST-3):
    exit code + stdout non-empty + every CURRENTLY-REGISTERED subcommand
    name appears in the Click-generated subcommand listing.
    """
    proc = _run_help(envoy_bin, "--help")

    assert proc.returncode == 0, (
        f"`envoy --help` exited {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert proc.stdout.strip(), "`envoy --help` produced empty stdout"
    for registered in sorted(REGISTERED_AS_OF_F5):
        assert registered in proc.stdout, (
            f"Currently-registered subcommand {registered!r} missing from "
            f"`envoy --help` output. Stdout:\n{proc.stdout}"
        )


@pytest.mark.parametrize("subcommand", CANONICAL_SUBCOMMANDS)
def test_envoy_subcommand_help_per_milestone_5(
    envoy_bin: Path,
    subcommand: str,
    request: pytest.FixtureRequest,
) -> None:
    """``envoy <subcommand> --help`` exits 0 for each Milestone-5 subcommand.

    Currently-registered subcommands MUST pass; not-yet-wired ones are
    expected to fail (Click exits non-zero for an unknown subcommand)
    until shard 19 lands them. The xfail markers flip to PASSED as
    each subcommand lands, per ``rules/test-skip-discipline.md``
    BORDERLINE tier — the per-subcommand transition IS the
    Milestone-5 progress signal.
    """
    if subcommand not in REGISTERED_AS_OF_F5:
        request.applymarker(
            pytest.mark.xfail(
                strict=True,
                reason=(
                    f"`envoy {subcommand}` not yet wired in "
                    f"`envoy/cli/main.py`; canonical per "
                    f"`specs/mvp-build-sequence.md` line 128 (shard 19 § 3.4). "
                    f"strict=True per `rules/test-skip-discipline.md` "
                    f"+ Round-4 F1 disposition — when a shard registers "
                    f"{subcommand!r}, this xfail flips to XPASS and CI fails "
                    f"loudly, forcing the implementer to append "
                    f"{subcommand!r} to REGISTERED_AS_OF_F5 in the same PR. "
                    f"The XPASS→assertion-flip IS the Milestone-5 progress signal."
                ),
            )
        )

    proc = _run_help(envoy_bin, subcommand, "--help")
    assert proc.returncode == 0, (
        f"`envoy {subcommand} --help` exited {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert proc.stdout.strip(), f"`envoy {subcommand} --help` produced empty stdout"
