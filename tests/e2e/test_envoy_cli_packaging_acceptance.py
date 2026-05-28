# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""F5 Wave-5 CLI packaging acceptance test (Tier 3 in-process subprocess).

Acceptance gate per ``workspaces/phase-01-mvp/02-plans/01-build-sequence.md``
§ Wave 5 line 264 + § Milestone 5 line 329 + ``workspaces/phase-01-mvp/
briefs/00-phase-01-mvp-scope.md`` § Surfaces line 21: the ``envoy``
console-script entry-point declared in ``pyproject.toml [project.scripts]``
resolves to ``envoy.cli:cli`` cleanly, and each of the 11 Milestone-5
subcommands' ``--help`` invocations succeeds at exit 0 with a non-empty
help body.

Verbatim spec citations:

- ``workspaces/phase-01-mvp/02-plans/01-build-sequence.md`` Wave 5 line
  264: ``envoy/cli.py 11 subcommands — `init` / `up` / `boundaries`
  / `ledger` / `shamir` / `digest` / `grant` / `posture` / `connection`
  / `model` / `version```.

- ``workspaces/phase-01-mvp/02-plans/01-build-sequence.md`` Milestone 5
  line 333: ``pipx install envoy-agent works on macOS / Linux desktop-env
  / Windows x86_64. All 11 CLI subcommands functional.``

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

- The 9 not-yet-registered subcommands (``init`` / ``up`` /
  ``boundaries`` / ``ledger`` / ``grant`` / ``posture`` / ``connection``
  / ``model`` / ``version``) are marked ``xfail(strict=False)`` per
  ``rules/test-skip-discipline.md`` BORDERLINE tier — each xfail flips
  to passing as shard 19 wires the corresponding subcommand. The xfail
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


# Verbatim from ``workspaces/phase-01-mvp/02-plans/01-build-sequence.md``
# § Wave 5 line 264 (order preserved exactly as the spec lists them).
ELEVEN_SUBCOMMANDS: tuple[str, ...] = (
    "init",
    "up",
    "boundaries",
    "ledger",
    "shamir",
    "digest",
    "grant",
    "posture",
    "connection",
    "model",
    "version",
)

# Subcommands wired in ``envoy/cli/main.py`` as of this test's land time:
#   - ``shamir`` — T-02-36 (Wave-2 trust vault recovery)
#   - ``digest`` — Wave-4 daily-digest shard
# The remaining 9 are scheduled for shard 19 per Wave 5 of the build
# sequence (``02-plans/01-build-sequence.md`` line 264). When shard 19
# wires a subcommand, append it here — the xfail in the parametrized
# test flips to PASSED on the next run, surfacing the Milestone-5
# progress signal.
REGISTERED_AS_OF_F5: frozenset[str] = frozenset({"shamir", "digest"})


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


@pytest.mark.parametrize("subcommand", ELEVEN_SUBCOMMANDS)
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
                strict=False,
                reason=(
                    f"`envoy {subcommand}` not yet wired in "
                    f"`envoy/cli/main.py`; scheduled for shard 19 per "
                    f"`workspaces/phase-01-mvp/02-plans/01-build-sequence.md` "
                    f"§ Wave 5. xfail flips to passing once shard 19 "
                    f"registers the {subcommand!r} subcommand."
                ),
            )
        )

    proc = _run_help(envoy_bin, subcommand, "--help")
    assert proc.returncode == 0, (
        f"`envoy {subcommand} --help` exited {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert proc.stdout.strip(), f"`envoy {subcommand} --help` produced empty stdout"
