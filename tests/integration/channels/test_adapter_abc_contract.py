"""Tier-2 wiring: `ChannelAdapter` ABC contract assertions.

Per `specs/channel-adapters.md` § Adapter contract (lines 14-130). Verifies
every Phase-01 concrete adapter implements every abstract method, that the
Phase-02 ritual surfaces inherit the typed `PhaseDeferredError` default, and
that the ABC cannot be instantiated directly.

Per `rules/probe-driven-verification.md` MUST-1: every assertion targets a
structural property (method presence, exception class, attribute value) —
no substring matches on prose.
"""

from __future__ import annotations

import inspect

import pytest

from envoy.channels import (
    ChannelAdapter,
    CLIChannelAdapter,
    PhaseDeferredError,
    WebChannelAdapter,
)
from envoy.channels.cli import CLIChannelConfig
from envoy.channels.envelope import (
    MonthlyTrustReportPayload,
    WeeklyPostureReviewPayload,
)
from envoy.channels.web import WebChannelConfig

PHASE_01_ADAPTERS = [CLIChannelAdapter, WebChannelAdapter]
ABSTRACT_METHODS = {
    "channel_id",
    "startup",
    "shutdown",
    "receive_message",
    "send_message",
    "send_grant_moment",
    "send_digest",
    "capabilities",
    "rate_limit_status",
}
PHASE_02_RITUAL_METHODS = {"send_posture_review", "send_monthly_report"}


@pytest.mark.regression
class TestChannelAdapterABC:
    """Contract pin: spec § Adapter contract (lines 14-130)."""

    def test_abc_cannot_be_instantiated_directly(self) -> None:
        """`ChannelAdapter()` MUST raise — the ABC is not constructable."""
        with pytest.raises(TypeError):
            ChannelAdapter()  # type: ignore[abstract]

    @pytest.mark.parametrize("adapter_cls", PHASE_01_ADAPTERS)
    def test_every_abstract_method_is_implemented(self, adapter_cls: type) -> None:
        """Every Phase-01 adapter MUST implement every abstract method."""
        adapter_abstracts = getattr(adapter_cls, "__abstractmethods__", frozenset())
        assert (
            adapter_abstracts == frozenset()
        ), f"{adapter_cls.__name__} has unimplemented abstract methods: {adapter_abstracts}"

    @pytest.mark.parametrize("adapter_cls", PHASE_01_ADAPTERS)
    def test_abstract_surface_matches_spec(self, adapter_cls: type) -> None:
        """Every method named in the spec MUST be present on the adapter class."""
        for name in ABSTRACT_METHODS | PHASE_02_RITUAL_METHODS:
            assert hasattr(adapter_cls, name), f"{adapter_cls.__name__} missing {name!r}"

    @pytest.mark.parametrize("adapter_cls", PHASE_01_ADAPTERS)
    def test_phase_02_ritual_methods_inherited_from_abc(self, adapter_cls: type) -> None:
        """`send_posture_review` + `send_monthly_report` MUST inherit the
        Phase-02 default (NOT override Phase 01) — otherwise the Phase-defer
        contract leaks into production code."""
        for name in PHASE_02_RITUAL_METHODS:
            method = adapter_cls.__dict__.get(name)
            assert method is None, (
                f"{adapter_cls.__name__} overrides {name!r}; Phase 01 MUST "
                "inherit the PhaseDeferredError default per "
                "rules/zero-tolerance.md Rule 2."
            )


@pytest.mark.regression
class TestPhaseDeferredContract:
    """Phase-02 ritual surfaces raise typed `PhaseDeferredError`."""

    @pytest.mark.asyncio
    async def test_cli_send_posture_review_raises_phase_deferred(self) -> None:
        adapter = CLIChannelAdapter(CLIChannelConfig(primary_channel_id="cli"))
        await adapter.startup()
        try:
            review = WeeklyPostureReviewPayload(
                review_id="r1",
                week_starts="2026-05-26",
                state="W0",
                summary_body="weekly summary",
            )
            with pytest.raises(PhaseDeferredError) as excinfo:
                await adapter.send_posture_review("principal-a", review)
            assert excinfo.value.method_name == ("CLIChannelAdapter.send_posture_review")
            assert excinfo.value.deferred_to_phase == "Phase 02"
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_web_send_monthly_report_raises_phase_deferred(self) -> None:
        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        await adapter.startup()
        try:
            report = MonthlyTrustReportPayload(
                report_id="m1",
                month="2026-05",
                pdf_url="file:///tmp/report.pdf",
                json_url="file:///tmp/report.json",
                summary_body="monthly summary",
            )
            with pytest.raises(PhaseDeferredError) as excinfo:
                await adapter.send_monthly_report("principal-a", report)
            assert excinfo.value.method_name == ("WebChannelAdapter.send_monthly_report")
        finally:
            await adapter.shutdown()


def test_send_grant_moment_signatures_match_spec() -> None:
    """`send_grant_moment` MUST carry `primary_only` + `timeout_seconds` kwargs.

    Spec line 70-72:
      ``async def send_grant_moment(self, target_principal_id, grant, *,
      primary_only=False, timeout_seconds=30)``.
    """
    sig = inspect.signature(ChannelAdapter.send_grant_moment)
    params = sig.parameters
    assert "target_principal_id" in params
    assert "grant" in params
    assert "primary_only" in params
    assert params["primary_only"].default is False
    assert "timeout_seconds" in params
    assert params["timeout_seconds"].default == 30
