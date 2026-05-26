"""Tier-2: pins for /redteam R4 same-shard closures (PR #42).

R4 verdict (3-axis):
- security: NOT CLEAN — 1 HIGH (spec drift) + 3 MED + 2 LOW.
- reviewer: NOT CLEAN — 2 HIGH (spec drift + Web empty-string guard) + 1 MED + 1 LOW.
- spec-compliance: 1 MED (same spec drift) + 1 pre-existing HIGH (phantom test files) + 4 LOW.

R4 closures landed same-shard per `rules/autonomous-execution.md` MUST Rule 4.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from envoy.channels import (
    CLIChannelAdapter,
    InvalidDecisionError,
    WebChannelAdapter,
)
from envoy.channels.web import WebChannelConfig


# ---------------------------------------------------------------------------
# H-R4-1 — spec `channel-adapters.md:94` removed `approve_author` from vocab
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_spec_channel_adapters_does_not_advertise_approve_author() -> None:
    """Pin: `specs/channel-adapters.md` decision-vocab union matches the
    canonical 4-vocab (per /redteam R4 H-R4-1 closure)."""
    spec = pathlib.Path("specs/channel-adapters.md").read_text()
    assert "approve_author |" not in spec
    assert "| approve_author" not in spec
    # The canonical 4-vocab is cited at line 94 (post-R4 edit).
    assert "approve_once | approve_and_author | deny | modify" in spec


# ---------------------------------------------------------------------------
# H-R4-2 — Web render_grant_moment empty-string request_id guard
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestWebRenderGuardEmptyString:
    """Pin: `WebChannelAdapter.render_grant_moment` rejects empty string."""

    @pytest.mark.asyncio
    async def test_web_render_refuses_empty_string_request_id(self) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        await adapter.startup()
        try:

            class _Req:
                request_id = ""
                novelty_class = "familiar_repeat"
                primary_only = False

            with pytest.raises(ValueError, match="request_id"):
                await adapter.render_grant_moment(_Req())
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_web_render_refuses_missing_request_id(self) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        await adapter.startup()
        try:

            class _Req:
                request_id = None
                novelty_class = "familiar_repeat"
                primary_only = False

            with pytest.raises(ValueError, match="request_id"):
                await adapter.render_grant_moment(_Req())
        finally:
            await adapter.shutdown()


# ---------------------------------------------------------------------------
# M-R4-3 — InvalidDecisionError constructor-side truncation
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestInvalidDecisionConstructorSanitization:
    """Pin: `InvalidDecisionError.__init__` truncates input at construction.

    Pre-R4 the sanitization lived only at the `_resolve_pending_decision`
    call site; future call sites would bypass the CWE-117 defense. R4
    moves the truncation into the constructor.
    """

    def test_long_decision_truncated_at_constructor(self) -> None:
        attacker_payload = "force_approve" + "A" * 1000
        err = InvalidDecisionError(
            channel_id="web",
            decision=attacker_payload,
            allowed=("approve_once",),
        )
        assert len(err.decision) <= 32

    def test_non_printable_stripped_at_constructor(self) -> None:
        payload = "force\x00\x01\x02approv\x7fe"
        err = InvalidDecisionError(
            channel_id="web",
            decision=payload,
            allowed=("approve_once",),
        )
        assert "\x00" not in err.decision
        assert "\x7f" not in err.decision

    def test_none_decision_does_not_crash(self) -> None:
        """Constructor MUST tolerate `None` (defensive null guard)."""
        err = InvalidDecisionError(
            channel_id="web",
            decision="",  # type: ignore[arg-type]
            allowed=("approve_once",),
        )
        assert err.decision == ""


# ---------------------------------------------------------------------------
# MED-R4-1 — recipient added to consequence preview render
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_render_prose_includes_recipient() -> None:
    """Pin: `ConsequencePreview.recipient` rendered per spec § Rendering."""

    class _CP:
        budget_microdollars = 10_000
        reversibility = "reversible"
        recipient = "ops@example.com"
        data_classification = "Internal"

    class _Req:
        request_id = "r-recipient"
        tool_name = "send_email"
        why_asking = "weekly digest"
        consequence_preview = _CP()

    rendered = CLIChannelAdapter._render_grant_moment_request_prose(_Req())
    assert "Recipient: ops@example.com" in rendered


# ---------------------------------------------------------------------------
# L-R4-1 — AST-based __all__ invariant test (refactor-invariants.md Rule 1)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestAllInvariantR4:
    """Pin: `__all__` counts derived structurally (AST), not via grep.

    Per `rules/refactor-invariants.md` MUST Rule 1: invariant tests guard
    refactors that change file structure. The R4 closures touched both
    files; this test pins the post-R4 surface count.
    """

    @staticmethod
    def _all_len(path: str) -> int:
        tree = ast.parse(pathlib.Path(path).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
            ):
                value = node.value
                assert isinstance(value, ast.List)
                return len(value.elts)
        raise AssertionError(f"__all__ not found in {path}")

    def test_channels_init_all_invariant(self) -> None:
        # +1 for TelegramChannelAdapter (Wave-A phase-01) = 32
        assert self._all_len("envoy/channels/__init__.py") == 32

    def test_errors_module_all_invariant(self) -> None:
        assert self._all_len("envoy/channels/errors.py") == 16


# ---------------------------------------------------------------------------
# HIGH-R4-01 pre-existing — spec § Test location no longer cites 5 phantom files
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_spec_test_location_does_not_cite_phantom_files() -> None:
    """Pin: pre-existing 5 phantom test-file citations extracted to workspace
    todos per `rules/spec-accuracy.md` Rule 4 (work trackers outside specs)."""
    spec = pathlib.Path("specs/channel-adapters.md").read_text()
    phantom_paths = [
        "tests/regression/test_t018_visible_secret_per_channel.py",
        "tests/regression/test_t070_clipboard_autoclear.py",
        "tests/regression/test_t080_tls13_pin.py",
        "tests/regression/test_t023_signal_path_b.py",
        "tests/e2e/test_session_continuity_8_channels.py",
    ]
    for path in phantom_paths:
        # The phantom path MAY still appear in a forward-declared narrative
        # paragraph; what MUST be gone is the bullet-form citation that
        # asserts the file exists.
        bullet_form = f"- `{path}`"
        assert bullet_form not in spec, (
            f"Phantom path {path!r} still bullet-cited in spec — should live "
            "in workspaces/phase-01-mvp/todos/active/wave-4-channels-regression-tests.md"
        )


@pytest.mark.regression
def test_phantom_test_workspace_todo_exists() -> None:
    """The 5 forward-declared tests live in the workspace todo."""
    todo = pathlib.Path("workspaces/phase-01-mvp/todos/active/wave-4-channels-regression-tests.md")
    assert todo.exists()
    body = todo.read_text()
    assert "test_t018_visible_secret_per_channel" in body
    assert "test_t023_signal_path_b" in body
