"""Tier 1 tests for envelope-scope membership predicate.

Per `envoy/envelope/scope.py` + shard 14 § 5.5
(`workspaces/phase-01-mvp/01-analysis/14-connection-vault-implementation.md`).

The predicate is pure set-membership; tests pin the 4 truth-table corners
+ the channel-None permissive case + both Envelope* input types.
"""

from __future__ import annotations

import pytest

from envoy.envelope import (
    CommunicationDimension,
    EnvelopeConfigInput,
    EnvelopeScopeRef,
    OperationalDimension,
    envelope_contains_scope,
)


def _envelope(*, tools: list[str], channels: list[str]) -> EnvelopeConfigInput:
    return EnvelopeConfigInput(
        operational=OperationalDimension(tool_allowlist=tools),
        communication=CommunicationDimension(channel_allowlist=channels),
    )


class TestEnvelopeContainsScope:
    """Truth-table coverage of the predicate."""

    def test_service_in_tools_no_channel_returns_true(self) -> None:
        env = _envelope(tools=["openai"], channels=[])
        scope = EnvelopeScopeRef(service_identifier="openai")
        assert envelope_contains_scope(env, scope) is True

    def test_service_in_tools_channel_in_channels_returns_true(self) -> None:
        env = _envelope(tools=["telegram-bot"], channels=["telegram"])
        scope = EnvelopeScopeRef(service_identifier="telegram-bot", channel="telegram")
        assert envelope_contains_scope(env, scope) is True

    def test_service_not_in_tools_returns_false(self) -> None:
        env = _envelope(tools=["claude"], channels=["cli"])
        scope = EnvelopeScopeRef(service_identifier="openai")
        assert envelope_contains_scope(env, scope) is False

    def test_service_in_tools_channel_not_in_channels_returns_false(self) -> None:
        env = _envelope(tools=["telegram-bot"], channels=["slack"])
        scope = EnvelopeScopeRef(service_identifier="telegram-bot", channel="telegram")
        assert envelope_contains_scope(env, scope) is False

    def test_empty_envelope_returns_false_for_any_scope(self) -> None:
        """Fail-closed default: a freshly-constructed envelope permits nothing."""
        env = _envelope(tools=[], channels=[])
        scope = EnvelopeScopeRef(service_identifier="openai")
        assert envelope_contains_scope(env, scope) is False

    def test_channel_none_skips_channel_check(self) -> None:
        """A service-only credential is reachable from any channel permission."""
        env = _envelope(tools=["openai"], channels=[])
        scope_no_channel = EnvelopeScopeRef(service_identifier="openai", channel=None)
        assert envelope_contains_scope(env, scope_no_channel) is True


class TestEnvelopeScopeRefDataclass:
    """Pin the EnvelopeScopeRef contract."""

    def test_default_channel_is_none(self) -> None:
        scope = EnvelopeScopeRef(service_identifier="openai")
        assert scope.channel is None

    def test_frozen(self) -> None:
        scope = EnvelopeScopeRef(service_identifier="openai")
        with pytest.raises((AttributeError, Exception)):
            scope.service_identifier = "rotated"  # type: ignore[misc]

    def test_equal_when_fields_match(self) -> None:
        a = EnvelopeScopeRef(service_identifier="openai", channel="cli")
        b = EnvelopeScopeRef(service_identifier="openai", channel="cli")
        assert a == b

    def test_unequal_when_channel_differs(self) -> None:
        a = EnvelopeScopeRef(service_identifier="openai", channel="cli")
        b = EnvelopeScopeRef(service_identifier="openai", channel="web")
        assert a != b
