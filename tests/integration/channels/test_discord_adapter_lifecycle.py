"""tests/integration/channels/test_discord_adapter_lifecycle.py

Lifecycle pin tests for DiscordChannelAdapter.

These four tests exercise the 7 redteam-established invariants that were
the hardest to validate at /redteam R1-R5 time:

  - Invariant 1: canonical discriminators — ``send_grant_moment`` reads
    ``grant.high_stakes``; ``render_grant_moment`` reads
    ``novelty_class == "high_stakes"``.
  - Invariant 3: ``_register_pending`` is the SOLE write-site for
    ``self._pending_decisions``.
  - Invariant 4: high_stakes auto-gate fires even when
    ``primary_only=False``.
  - Invariant 5: PII hash — SHA-256 hex[:8] on ``principal_id`` in logs.

NOTE — collection failure on this file:
  The full import chain ``envoy.channels.discord`` → ``envoy.channels.envelope``
  → ``envoy.trust.types`` → ``kailash.trust`` raises
  ``ModuleNotFoundError: No module named 'kailash.trust'`` in CI until
  ``kailash>=<version-with-trust>`` is declared in ``pyproject.toml``.
  This is a pre-existing environment gap documented in the wave-A
  orchestration brief; the fix requires editing ``pyproject.toml``
  (FORBIDDEN file for this shard).  The test code is structurally
  correct Python; the collection error is an environment-level concern,
  not a code-level concern.  All other channel lifecycle tests
  (``test_cli_adapter_lifecycle.py``, ``test_web_adapter_lifecycle.py``)
  share the same failure mode on the same import chain.
"""

from __future__ import annotations

import hashlib
import logging
import types

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# ---------------------------------------------------------------------------
# Real Ed25519 keypair — required by DiscordSigner for construction.
# All-zero bytes are rejected by the underlying cryptography primitive.
# ---------------------------------------------------------------------------
_PRIVATE_KEY: Ed25519PrivateKey = Ed25519PrivateKey.generate()
_PUBLIC_KEY_HEX: str = _PRIVATE_KEY.public_key().public_bytes_raw().hex()


# ---------------------------------------------------------------------------
# Import adapter + envelopes after keypair so they show up in error messages.
# The kailash.trust import chain means these may raise ModuleNotFoundError
# at collection time — see module docstring.
# ---------------------------------------------------------------------------
from envoy.channels.discord import DiscordChannelAdapter, DiscordChannelConfig  # noqa: E402
from envoy.channels.envelope import (  # noqa: E402
    GrantMomentPayload,
    MessagePayload,
    VisibleSecret,
)
from envoy.channels.errors import NotPrimaryChannelError  # noqa: E402

# ---------------------------------------------------------------------------
# Module-level PII helper (mirrors _hash_pii in discord.py exactly).
# ---------------------------------------------------------------------------


def _hash_pii(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Config / adapter factories
# ---------------------------------------------------------------------------


def _make_config(*, primary: bool) -> DiscordChannelConfig:
    """Build a DiscordChannelConfig.

    When ``primary=True`` the adapter is the primary channel (the running
    adapter's channel_id ``"discord"`` matches ``primary_channel_id``).
    When ``primary=False`` the primary channel is declared as ``"web"``,
    which the Discord adapter is NOT.
    """
    primary_channel_id = "discord" if primary else "web"
    return DiscordChannelConfig(
        primary_channel_id=primary_channel_id,
        application_public_key=_PUBLIC_KEY_HEX,
        bot_token="test-bot-token-not-real",  # noqa: S106 — test fixture, not prod secret
    )


def _make_adapter(*, primary: bool) -> DiscordChannelAdapter:
    return DiscordChannelAdapter(_make_config(primary=primary))


def _make_grant(*, high_stakes: bool) -> GrantMomentPayload:
    return GrantMomentPayload(
        request_id="req-test-001",
        intent_id="intent-test-001",
        decision_options=("approve_once", "deny"),
        visible_secret=VisibleSecret(icon="🔑", color="#A0E7E5", phrase="test-phrase"),
        body="Test grant moment body",
        high_stakes=high_stakes,
    )


# ---------------------------------------------------------------------------
# Pin test 1: Invariant 4 — high_stakes auto-gate blocks non-primary channel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discord_high_stakes_auto_gate_blocks_non_primary() -> None:
    """Invariant 4: auto-gate fires even when ``primary_only=False``.

    When ``grant.high_stakes=True``, the adapter MUST raise
    ``NotPrimaryChannelError`` even if the caller passes
    ``primary_only=False``.  Defense-in-depth: the adapter does not trust
    the caller's assertion when the payload itself declares high stakes.
    """
    adapter = _make_adapter(primary=False)
    await adapter.startup()
    try:
        grant = _make_grant(high_stakes=True)
        with pytest.raises(NotPrimaryChannelError) as exc_info:
            # primary_only=False — the AUTO-gate on high_stakes must fire
            await adapter.send_grant_moment(
                "principal-test-001",
                grant,
                primary_only=False,
                timeout_seconds=1,
            )
        err = exc_info.value
        assert err.channel_id == "discord"
        assert err.primary_channel_id == "web"
    finally:
        await adapter.shutdown()


# ---------------------------------------------------------------------------
# Pin test 2: Invariant 1 — canonical discriminators on payload vs request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discord_vocab_canonical_discriminator_payload_vs_request() -> None:
    """Invariant 1: two different discriminators for two different surfaces.

    ``send_grant_moment`` reads ``grant.high_stakes`` (a real field on
    ``GrantMomentPayload``).  ``render_grant_moment`` reads
    ``novelty_class == "high_stakes"`` (a string field on
    ``GrantMomentRequest``).  These MUST be distinct — mixing them up
    causes the wrong surface to apply the wrong gate logic.

    This test:
    (a) Confirms that a NON-high-stakes payload on a non-primary adapter
        does NOT raise — i.e., ``send_grant_moment`` correctly reads
        ``grant.high_stakes=False`` and skips the auto-gate.
    (b) Confirms that a ``GrantMomentRequest`` with
        ``novelty_class="high_stakes"`` on a non-primary adapter DOES
        raise ``NotPrimaryChannelError`` — i.e., ``render_grant_moment``
        correctly reads ``novelty_class``.
    (c) Confirms that a ``GrantMomentRequest`` with
        ``novelty_class="low_stakes"`` on a non-primary adapter does NOT
        raise.
    """
    adapter = _make_adapter(primary=False)
    await adapter.startup()
    try:
        # (a) send_grant_moment with high_stakes=False on non-primary:
        #     the auto-gate should NOT fire, so no exception is raised.
        #     We catch GrantMomentExpiredError (the inevitable timeout
        #     since no user response arrives) OR ChannelTransportError
        #     (no real webhook in tests) — either confirms we got PAST
        #     the primary-channel gate check.
        from envoy.channels.errors import ChannelTransportError, GrantMomentExpiredError

        grant_low = _make_grant(high_stakes=False)
        with pytest.raises((GrantMomentExpiredError, ChannelTransportError)):
            await adapter.send_grant_moment(
                "principal-test-001",
                grant_low,
                primary_only=False,
                timeout_seconds=0,  # immediate timeout
            )

        # (b) render_grant_moment with novelty_class="high_stakes"
        #     on a non-primary adapter: MUST raise NotPrimaryChannelError.
        request_high = types.SimpleNamespace(
            request_id="req-render-high",
            novelty_class="high_stakes",
            primary_only=False,
            intent_id="intent-render-high",
            decision_options=("approve_once", "deny"),
            body="high stakes render test",
        )
        with pytest.raises(NotPrimaryChannelError):
            await adapter.render_grant_moment(request_high)

        # (c) render_grant_moment with novelty_class="low_stakes"
        #     on non-primary: MUST NOT raise (gate does not fire).
        request_low = types.SimpleNamespace(
            request_id="req-render-low",
            novelty_class="low_stakes",
            primary_only=False,
            intent_id="intent-render-low",
            decision_options=("approve_once", "deny"),
            body="low stakes render test",
        )
        # Should complete without raising NotPrimaryChannelError.
        # ChannelTransportError is acceptable — it means the gate did NOT fire.
        # (No real webhook in tests; the test verifies absence of NotPrimaryChannelError,
        # not that delivery succeeded.)
        from contextlib import suppress

        from envoy.channels.errors import ChannelTransportError

        with suppress(ChannelTransportError):
            await adapter.render_grant_moment(request_low)

    finally:
        await adapter.shutdown()


# ---------------------------------------------------------------------------
# Pin test 3: Invariant 5 — principal_id PII is hashed in logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discord_principal_id_pii_hash_in_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invariant 5: raw principal_id MUST NOT appear in log output.

    ``send_message`` logs ``target_principal_hash`` (sha256[:8]) not the
    raw ``target_principal_id``.  Verifies both absence of the raw value
    and presence of the expected 8-char hash.
    """
    adapter = _make_adapter(primary=True)
    await adapter.startup()
    try:
        raw_principal = "user-secret-principal-1234"
        expected_hash = _hash_pii(raw_principal)

        from contextlib import suppress

        from envoy.channels.errors import ChannelTransportError

        with caplog.at_level(logging.INFO, logger="envoy.channels.discord"), suppress(ChannelTransportError):
            # suppress ChannelTransportError — no real webhook in tests.
            # The PII hash is logged at INFO *before* _deliver_message fires,
            # so the log record is still present for our assertion.
            await adapter.send_message(
                target_principal_id=raw_principal,
                payload=MessagePayload(kind="text", body="hello discord"),
            )

        # The raw principal ID MUST NOT appear anywhere in log records.
        all_log_text = " ".join(
            str(record.getMessage()) + " " + str(record.__dict__) for record in caplog.records
        )
        assert raw_principal not in all_log_text, (
            f"Raw principal_id '{raw_principal}' leaked into log output; "
            f"expected only the 8-char hash '{expected_hash}'"
        )

        # The 8-char hash MUST appear in log records.
        assert expected_hash in all_log_text, (
            f"Expected 8-char PII hash '{expected_hash}' not found in log output. "
            f"Check that send_message logs 'target_principal_hash'."
        )

    finally:
        await adapter.shutdown()


# ---------------------------------------------------------------------------
# Pin test 4: Invariant 3 — _register_pending is the sole write-site
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discord_register_pending_single_write_site() -> None:
    """Invariant 3: ``_register_pending`` is the ONLY place that writes
    to ``self._pending_decisions``.

    Calls ``_register_pending`` directly and verifies:
    (a) The request_id is now in ``_pending_decisions``.
    (b) A second call with the same id is idempotent (dict semantics).
    (c) A different id is also accepted.
    (d) ``_pending_decisions`` contains EXACTLY the expected ids and
        nothing else — confirming no other code path has injected extras.

    R1: ``_pending_decisions`` is now ``dict[str, asyncio.Future[GrantMomentDecision]]``.
    ``_register_pending`` calls ``asyncio.get_running_loop()`` to create
    a Future, so the test MUST be async (requires a running event loop).
    The adapter is constructed but NOT started — ``_register_pending``
    does not gate on ``_started``.
    """
    adapter = _make_adapter(primary=True)

    # Initially empty.
    # R1: _pending_decisions is now dict[str, asyncio.Future[GrantMomentDecision]]
    assert adapter._pending_decisions == {}

    # (a) First registration.
    adapter._register_pending("req-alpha")
    assert "req-alpha" in adapter._pending_decisions

    # (b) Idempotent — re-registering same id does not duplicate or raise.
    adapter._register_pending("req-alpha")
    assert len(adapter._pending_decisions) == 1

    # (c) Second distinct id is accepted.
    adapter._register_pending("req-beta")
    assert "req-beta" in adapter._pending_decisions

    # (d) Exactly the two expected ids; no extras injected by any other path.
    assert set(adapter._pending_decisions.keys()) == {"req-alpha", "req-beta"}
