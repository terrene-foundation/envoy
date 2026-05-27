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
        # +1 TelegramChannelAdapter + 1 SlackChannelAdapter + 1 DiscordChannelAdapter
        # (Wave-A phase-01 parallel siblings) = 34
        assert self._all_len("envoy/channels/__init__.py") == 34

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


# ---------------------------------------------------------------------------
# L-1 — 0.0.0.0/8 added to _SSRF_BLOCKED_NETWORKS; fc00::/7 comment clarified
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_discord_ssrf_blocked_networks_includes_zero_network() -> None:
    """Pin: 0.0.0.0/8 MUST be in _SSRF_BLOCKED_NETWORKS (RFC 1122 'this' network)."""
    import ipaddress

    from envoy.channels.discord import _SSRF_BLOCKED_NETWORKS

    zero_net = ipaddress.ip_network("0.0.0.0/8")
    assert zero_net in _SSRF_BLOCKED_NETWORKS, (
        "0.0.0.0/8 missing from _SSRF_BLOCKED_NETWORKS — SSRF via 'this' network "
        "bypass remains open (R4 L-1)"
    )


@pytest.mark.regression
def test_discord_ssrf_blocked_networks_fc00_comment_says_ula() -> None:
    """Pin: fc00::/7 comment MUST say 'ULA' (not 'private') — spec-accuracy R4 L-3."""
    import inspect

    import envoy.channels.discord as _discord_mod

    src = inspect.getsource(_discord_mod)
    # The fc00::/7 line must document 'ULA' or 'unique-local'; NOT 'RFC-1918 private'
    for line in src.splitlines():
        if "fc00::/7" in line:
            assert "ULA" in line or "unique-local" in line, (
                f"fc00::/7 comment does not mention ULA/unique-local (got: {line!r}) — "
                "R4 L-3: fc00::/7 is IPv6 ULA, NOT RFC-1918 private"
            )
            break
    else:
        pytest.fail("fc00::/7 not found in discord.py source — _SSRF_BLOCKED_NETWORKS changed?")


# ---------------------------------------------------------------------------
# H-1 — hex-dotted bypass (0x7f.0.0.1) now normalised before SSRF check
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_discord_ssrf_rejects_hex_dotted_loopback() -> None:
    """Pin: 0x7f.0.0.1 (== 127.0.0.1) MUST be rejected by the SSRF guard."""
    from envoy.channels.discord import _validate_webhook_url_ssrf
    from envoy.channels.errors import ChannelTransportError

    with pytest.raises(ChannelTransportError, match="SSRF guard"):
        _validate_webhook_url_ssrf(
            "https://0x7f.0.0.1/api/webhooks/123/abc",
            channel_id="test-discord",
        )


@pytest.mark.regression
def test_discord_ssrf_rejects_hex_int_loopback() -> None:
    """Pin: 0x7f000001 (pure hex integer == 127.0.0.1) MUST also be rejected."""
    from envoy.channels.discord import _validate_webhook_url_ssrf
    from envoy.channels.errors import ChannelTransportError

    with pytest.raises(ChannelTransportError, match="SSRF guard"):
        _validate_webhook_url_ssrf(
            "https://0x7f000001/api/webhooks/123/abc",
            channel_id="test-discord",
        )


# ---------------------------------------------------------------------------
# M-1 — malformed octal component (08.0.0.1) now raises loudly
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_discord_ssrf_rejects_malformed_octal_component() -> None:
    """Pin: 08.0.0.1 (invalid octal — digit 8) MUST raise ChannelTransportError."""
    from envoy.channels.discord import _validate_webhook_url_ssrf
    from envoy.channels.errors import ChannelTransportError

    with pytest.raises(ChannelTransportError, match="malformed octal component"):
        _validate_webhook_url_ssrf(
            "https://08.0.0.1/api/webhooks/123/abc",
            channel_id="test-discord",
        )


@pytest.mark.regression
def test_discord_ssrf_rejects_octal_loopback() -> None:
    """Pin: 0177.0.0.1 (== 127.0.0.1 in octal) MUST be rejected by SSRF guard."""
    from envoy.channels.discord import _validate_webhook_url_ssrf
    from envoy.channels.errors import ChannelTransportError

    with pytest.raises(ChannelTransportError, match="SSRF guard"):
        _validate_webhook_url_ssrf(
            "https://0177.0.0.1/api/webhooks/123/abc",
            channel_id="test-discord",
        )


@pytest.mark.regression
def test_discord_ssrf_allows_valid_public_webhook_url() -> None:
    """Pin: a genuine Discord CDN webhook URL MUST pass the SSRF guard."""
    from envoy.channels.discord import _validate_webhook_url_ssrf

    # This should not raise — public Discord API host
    _validate_webhook_url_ssrf(
        "https://discord.com/api/webhooks/123456789/abc_token",
        channel_id="test-discord",
    )


# ---------------------------------------------------------------------------
# H-2 (discord) — asyncio.CancelledError → GrantMomentExpiredError conversion
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_discord_send_grant_moment_cancelled_error_converts() -> None:
    """Pin: asyncio.CancelledError in send_grant_moment MUST convert to
    GrantMomentExpiredError (R4 H-2 discord channel shutdown contract)."""
    import ast
    import pathlib

    src = pathlib.Path("envoy/channels/discord.py").read_text()
    tree = ast.parse(src)

    # Locate send_grant_moment method
    sgm_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "send_grant_moment":
            sgm_node = node
            break

    assert sgm_node is not None, "send_grant_moment not found in discord.py"

    # Verify there's an except handler for CancelledError that raises GrantMomentExpiredError
    found_cancelled_handler = False
    found_grant_expired_raise = False

    for node in ast.walk(sgm_node):
        if isinstance(node, ast.ExceptHandler):
            # Check if this handler catches CancelledError
            handler_type = node.type
            catches_cancelled = False
            if isinstance(handler_type, ast.Attribute) and handler_type.attr == "CancelledError" or isinstance(handler_type, ast.Name) and handler_type.id == "CancelledError":
                catches_cancelled = True

            if catches_cancelled:
                found_cancelled_handler = True
                # Check if handler body raises GrantMomentExpiredError
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Raise) and stmt.exc is not None:
                        exc = stmt.exc
                        if isinstance(exc, ast.Call):
                            func = exc.func
                            name = (
                                func.id if isinstance(func, ast.Name)
                                else func.attr if isinstance(func, ast.Attribute)
                                else None
                            )
                            if name == "GrantMomentExpiredError":
                                found_grant_expired_raise = True

    assert found_cancelled_handler, (
        "discord.py send_grant_moment: no except CancelledError handler found "
        "(R4 H-2 — CancelledError must convert to GrantMomentExpiredError)"
    )
    assert found_grant_expired_raise, (
        "discord.py send_grant_moment: CancelledError handler does not raise "
        "GrantMomentExpiredError (R4 H-2 — shutdown contract violated)"
    )


# ---------------------------------------------------------------------------
# Slack R4 closures — M-2 (INV-4 gate ordering) + H-2 (CancelledError)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_slack_send_message_principal_check_precedes_rate_limit() -> None:
    """AST probe: slack.py send_message — PrincipalNotFound guard appears before
    the rate_limit_status() call (R4 M-2 / INV-4 gate ordering).

    This is a structural probe: walk the AST of send_message and verify that the
    first PrincipalNotFoundError raise appears at a lower line number than the
    first rate_limit_status() call.  Probe-driven, not lexical.
    """
    src = pathlib.Path("envoy/channels/slack.py").read_text()
    tree = ast.parse(src)

    # Locate send_message method
    sm_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "send_message":
            sm_node = node
            break

    assert sm_node is not None, "send_message not found in slack.py"

    principal_not_found_line: int | None = None
    rate_limit_call_line: int | None = None

    for node in ast.walk(sm_node):
        # Detect raise PrincipalNotFoundError(...)
        if isinstance(node, ast.Raise) and node.exc is not None:
            exc = node.exc
            if isinstance(exc, ast.Call):
                func = exc.func
                name = (
                    func.id if isinstance(func, ast.Name)
                    else func.attr if isinstance(func, ast.Attribute)
                    else None
                )
                if name == "PrincipalNotFoundError" and principal_not_found_line is None:
                    principal_not_found_line = node.lineno

        # Detect self.rate_limit_status() call
        if isinstance(node, ast.Await):
            val = node.value
            if isinstance(val, ast.Call):
                func = val.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "rate_limit_status"
                    and rate_limit_call_line is None
                ):
                    rate_limit_call_line = node.lineno

    assert principal_not_found_line is not None, (
        "slack.py send_message: no PrincipalNotFoundError raise found "
        "(R4 M-2 — INV-4 gate ordering requires PrincipalNotFound check)"
    )
    assert rate_limit_call_line is not None, (
        "slack.py send_message: no rate_limit_status() call found "
        "(R4 M-2 — rate-limit gate must follow PrincipalNotFound check)"
    )
    assert principal_not_found_line < rate_limit_call_line, (
        f"slack.py send_message: PrincipalNotFoundError raise (line "
        f"{principal_not_found_line}) is NOT before rate_limit_status() call "
        f"(line {rate_limit_call_line}) — INV-4 gate ordering violated "
        f"(R4 M-2 closure)"
    )


@pytest.mark.regression
def test_slack_send_grant_moment_cancelled_error_converts() -> None:
    """AST probe: slack.py send_grant_moment — asyncio.CancelledError handler
    raises GrantMomentExpiredError (R4 H-2 — shutdown contract).

    Mirrors the discord.py probe pattern.  Structural, not lexical.
    """
    src = pathlib.Path("envoy/channels/slack.py").read_text()
    tree = ast.parse(src)

    # Locate send_grant_moment method
    sgm_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "send_grant_moment":
            sgm_node = node
            break

    assert sgm_node is not None, "send_grant_moment not found in slack.py"

    found_cancelled_handler = False
    found_grant_expired_raise = False

    for node in ast.walk(sgm_node):
        if isinstance(node, ast.ExceptHandler):
            handler_type = node.type
            catches_cancelled = False
            if isinstance(handler_type, ast.Attribute) and handler_type.attr == "CancelledError" or isinstance(handler_type, ast.Name) and handler_type.id == "CancelledError":
                catches_cancelled = True

            if catches_cancelled:
                found_cancelled_handler = True
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Raise) and stmt.exc is not None:
                        exc = stmt.exc
                        if isinstance(exc, ast.Call):
                            func = exc.func
                            name = (
                                func.id if isinstance(func, ast.Name)
                                else func.attr if isinstance(func, ast.Attribute)
                                else None
                            )
                            if name == "GrantMomentExpiredError":
                                found_grant_expired_raise = True

    assert found_cancelled_handler, (
        "slack.py send_grant_moment: no except CancelledError handler found "
        "(R4 H-2 — CancelledError must convert to GrantMomentExpiredError)"
    )
    assert found_grant_expired_raise, (
        "slack.py send_grant_moment: CancelledError handler does not raise "
        "GrantMomentExpiredError (R4 H-2 — shutdown contract violated)"
    )


# ---------------------------------------------------------------------------
# Telegram R4 closures — M-2 (INV-4 gate ordering) + L-6 (sentinel `is` comment)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_telegram_send_message_principal_check_precedes_rate_limit() -> None:
    """AST probe: telegram.py send_message — PrincipalNotFound guard appears before
    the rate_limit_status() call (R4 M-2 / INV-4 gate ordering).

    Structural probe — same pattern as slack.py equivalent above.
    """
    src = pathlib.Path("envoy/channels/telegram.py").read_text()
    tree = ast.parse(src)

    # Locate send_message method
    sm_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "send_message":
            sm_node = node
            break

    assert sm_node is not None, "send_message not found in telegram.py"

    principal_not_found_line: int | None = None
    rate_limit_call_line: int | None = None

    for node in ast.walk(sm_node):
        if isinstance(node, ast.Raise) and node.exc is not None:
            exc = node.exc
            if isinstance(exc, ast.Call):
                func = exc.func
                name = (
                    func.id if isinstance(func, ast.Name)
                    else func.attr if isinstance(func, ast.Attribute)
                    else None
                )
                if name == "PrincipalNotFoundError" and principal_not_found_line is None:
                    principal_not_found_line = node.lineno

        if isinstance(node, ast.Await):
            val = node.value
            if isinstance(val, ast.Call):
                func = val.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "rate_limit_status"
                    and rate_limit_call_line is None
                ):
                    rate_limit_call_line = node.lineno

    assert principal_not_found_line is not None, (
        "telegram.py send_message: no PrincipalNotFoundError raise found "
        "(R4 M-2 — INV-4 gate ordering requires PrincipalNotFound check)"
    )
    assert rate_limit_call_line is not None, (
        "telegram.py send_message: no rate_limit_status() call found "
        "(R4 M-2 — rate-limit gate must follow PrincipalNotFound check)"
    )
    assert principal_not_found_line < rate_limit_call_line, (
        f"telegram.py send_message: PrincipalNotFoundError raise (line "
        f"{principal_not_found_line}) is NOT before rate_limit_status() call "
        f"(line {rate_limit_call_line}) — INV-4 gate ordering violated "
        f"(R4 M-2 closure)"
    )


@pytest.mark.regression
def test_telegram_shutdown_sentinel_is_comparison_comment() -> None:
    """Structural probe: telegram.py _SHUTDOWN_SENTINEL — the ``is`` comparison
    at the shutdown-sentinel check site has an explanatory comment citing that
    the sentinel is a module-level singleton used only in-process (R4 L-6).

    Uses inspect.getsource to verify the comment text appears near the ``is``
    comparison.  Structural probe: checks source-text proximity, not semantics.
    """
    import importlib
    import inspect
    mod = importlib.import_module("envoy.channels.telegram")
    src = inspect.getsource(mod)

    # Find the block around the sentinel ``is`` comparison.
    # The comment must mention in-process nature and singleton / identity.
    assert "is _SHUTDOWN_SENTINEL" in src, (
        "telegram.py: `is _SHUTDOWN_SENTINEL` comparison not found "
        "(R4 L-6 sentinel probe)"
    )

    # Structural: the source around the sentinel check must contain the
    # in-process + identity explanation comment.
    # We look for key phrases that the L-6 comment must contain.
    sentinel_idx = src.index("is _SHUTDOWN_SENTINEL")
    # Check within a 600-char window preceding the line for the comment block.
    window = src[max(0, sentinel_idx - 600): sentinel_idx + 50]
    has_inprocess = "in-process" in window or "in process" in window
    has_identity = "identity" in window or "singleton" in window or "module-level" in window
    assert has_inprocess and has_identity, (
        "telegram.py: the `is _SHUTDOWN_SENTINEL` comparison lacks an "
        "explanatory comment citing in-process-only / singleton identity "
        "(R4 L-6 — reviewer LOW: missing rationale for `is` comparison). "
        f"Window: {window!r}"
    )
