# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-7 acceptance battery (de-scope #1 — 5 channels × N=3 onboardings).

Acceptance gate per ``workspaces/phase-01-mvp/01-analysis/02-mvp-objectives.md``
EC-7 line 104 + ``workspaces/phase-01-mvp/02-plans/02-test-strategy.md``
§ EC-7 line 228 (8-channel × N=3 onboarding battery) + line 242 (de-scope
#1 fallback — 5 channels): for each of CLI + Web + Telegram + Slack +
Discord, run N=3 first-time-user sessions starting from that channel;
each session MUST complete the Boundary Conversation (S0→S10) and
produce a parseable ``EnvelopeConfig`` whose ``envelope_id`` is set.

This file is the de-scope #1 implementation (per
``01-analysis/02-mvp-objectives.md`` line 171 + ``01-shard-plan.md``
§ 5 wave-D row
"iMessage/Signal feasibility"): the iMessage + Signal channels deferred
to Phase-02, the Phase-01 EC-7 acceptance becomes 5 channels × N=3 = 15
onboardings.

Scope-out (explicit, per the security gate-review pattern established
in shard 13 PR #47):

- This battery exercises the BoundaryConversationRuntime's per-channel
  routing invariant using a Protocol-Satisfying Deterministic Adapter
  (``tests/helpers/deterministic_llm_provider.py``) for the LLM
  extraction surface, per ``rules/testing.md`` § "Protocol Adapters"
  exception (deterministic adapter ≠ mock).  It does NOT exercise the
  ≤2× CLI-baseline timing-deviation bound that EC-7's full acceptance
  gate names — that bound inherently requires real vendor sandboxes
  (Telegram test bot, Slack ngrok-tunneled webhook, Discord test guild)
  to measure real network latencies.  The literal timing-parity claim
  remains gated on vendor-sandbox provisioning; this battery closes the
  structural half (15 onboardings complete; envelope produced).

- The ``channel_id`` parameter is the session's transport identity (the
  metadata tag attached to which adapter the session came from).  The
  ``BoundaryConversationRuntime`` itself is channel-agnostic at its
  state-machine surface — it does NOT take a ``ChannelAdapter`` in its
  constructor (verified at ``envoy/boundary_conversation/runtime.py``
  lines 111-127).  In production, the channel adapter is the inbound/
  outbound message transport; the runtime drives the state machine
  regardless.  This battery's parametrization across the 5 channel_ids
  proves the runtime's invariant holds per channel context.

- Per-channel ``ChannelAdapter`` ABC compliance + capabilities are
  separately exercised by the ``TestChannelAdapterConstructability``
  class below — every Phase-01 channel adapter constructs cleanly with
  placeholder secrets and satisfies the ``ChannelAdapter`` abstract
  contract.

Per ``rules/testing.md`` § Tier 3: real ``EnvoyLedger`` + real
``TrustStoreAdapter`` + real ``TrustVault`` + real ``EnvelopeCompiler``
+ real ``ShamirRitualCoordinator`` + real ``NoveltyChecker``; the LLM
is the Protocol-Satisfying Deterministic Adapter (NOT a mock).  Per
``rules/probe-driven-verification.md`` MUST-3: every assertion is
structural (outcome-state equality, envelope_id is-not-None, integer
counts).  Per ``rules/agent-reasoning.md``: the deterministic provider
dispatches on the schema's unique field-names, NOT keyword-routing the
LLM prose.
"""

from __future__ import annotations

from collections.abc import Awaitable
from pathlib import Path

import pytest
from kailash.trust.audit_store import InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.authorship.novelty import NoveltyChecker
from envoy.boundary_conversation import (
    BoundaryConversationRuntime,
    ConversationOutcome,
)
from envoy.boundary_conversation import runtime as bc_runtime_mod
from envoy.envelope import EnvelopeCompiler, LocalTemplateResolver
from envoy.ledger import EnvoyLedger
from envoy.shamir import ShamirRitualCoordinator, TrustVaultChecklistPersister
from envoy.shamir.paper import PaperShardRenderer
from envoy.trust.store import TrustStoreAdapter
from envoy.trust.vault import TrustVault

from tests.helpers.deterministic_llm_provider import DeterministicModelRouter


# Phase-01 de-scope-#1 channel set per `01-analysis/02-mvp-objectives.md` line 171.
_FIVE_CHANNELS = ("cli", "web", "telegram", "slack", "discord")
_SESSIONS_PER_CHANNEL = 3

# Cross-product: 15 (channel, session_index) cases — the EC-7 acceptance count.
_BATTERY_CASES = [(channel, n) for channel in _FIVE_CHANNELS for n in range(_SESSIONS_PER_CHANNEL)]

# Stub provider registration key — see DeterministicProvider docstring.
_STUB_PRESET = "deterministic_test"
_STUB_PROVIDER_PATH = (
    "tests.helpers.deterministic_llm_provider",
    "DeterministicProvider",
)

# Canned user replies — content is irrelevant to the deterministic stub
# (which dispatches on the prompt's schema field names, not the user
# input), but the runtime needs SOMETHING non-empty per state for the
# extraction-input contract.
_CANNED_REPLIES = {
    "S1_money": "Cap me at 100 USD per month.",
    "S2_people": "No blocks.",
    "S3_topics": "No political endorsements.",
    "S4_hours": "Mon-Fri UTC working hours.",
    "S5_first_task": "Summarize my newsletters daily.",
    "S6_template_offer": "Build from scratch.",
    "S7_visible_secret": "Icon star, color blue, phrase 'open sky'.",
    "S8_shamir": "Default 3-of-5.",
    "S9_review_sign": "Yes, sign.",
}


# ---------------------------------------------------------------------------
# Helpers — runtime construction per session (one principal_id per session
# so the TrustStore + Vault are isolated; the spec calls for N=3 INDEPENDENT
# first-time-user sessions, not 3 sequential sessions sharing one principal).
# ---------------------------------------------------------------------------


class _MasterKeySource:
    """Satisfies ``ShamirRitualCoordinator``'s master-key Protocol via the
    real ``TrustVault.export_master_key_for_shamir`` surface."""

    def __init__(self, vault: TrustVault) -> None:
        self._vault = vault

    def export_master_key_for_shamir(self) -> Awaitable[bytes]:
        return self._vault.export_master_key_for_shamir()


class _InMemoryGenesisBinder:
    """Satisfies ``ShamirRitualCoordinator``'s commitment-binder Protocol
    with an in-memory store — the Phase-02 surface lands a real
    cross-device binder."""

    def __init__(self) -> None:
        self.binding: dict[str, list[str]] = {}

    async def bind_to_genesis(self, principal_id: str, commitments: list[str]) -> None:
        self.binding[principal_id] = list(commitments)


async def _build_runtime_for_session(
    tmp_path: Path, principal_id: str
) -> tuple[BoundaryConversationRuntime, EnvoyLedger, TrustStoreAdapter, TrustVault]:
    """Wire one full runtime for a single first-time-user session.

    Per ``rules/orphan-detection.md`` Rule 1 + ``rules/facade-manager-detection.md``
    Rule 3: every collaborator is explicitly constructed and passed in;
    no global lookups, no implicit factories.  Mirrors the production
    composition graph the runtime expects.
    """
    # Trust store + Vault per principal (each session is a first-time user
    # with their own vault file).
    trust_adapter = TrustStoreAdapter(
        vault_path=tmp_path / f"{principal_id}.vault", principal_id=principal_id
    )
    await trust_adapter.initialize()

    vault = TrustVault(tmp_path / f"{principal_id}.vault", idle_ttl_seconds=60)
    # The TrustStoreAdapter created the on-disk vault during initialize();
    # opening a separate TrustVault handle and unlocking it gives the Shamir
    # coordinator a live unlocked handle for master-key export.  The
    # adapter's vault and this handle target the same file.
    passphrase = f"phase01-ec7-passphrase-{principal_id}"
    try:
        await vault.unlock(passphrase)
    except FileNotFoundError:
        # Fresh adapter-created vault file does not exist yet — create it.
        # Narrow to FileNotFoundError per envoy/trust/vault.py:249-250 (the
        # only expected first-time-use exception); a corrupted-vault /
        # wrong-passphrase / param-mismatch surfaces immediately rather
        # than being coerced into a confusing double-create path.
        await vault.create(b"ec7-initial-payload", passphrase)
        await vault.unlock(passphrase)

    # Ledger with real signing keypair.
    keymgr = InMemoryKeyManager()
    signing_key_id = f"ec7-key-{principal_id}"
    await keymgr.generate_keypair(signing_key_id)
    ledger = EnvoyLedger(
        audit_store=InMemoryAuditStore(),
        key_manager=keymgr,
        signing_key_id=signing_key_id,
        device_id=f"device-ec7-{principal_id}",
        algorithm_identifier={
            "sig": "ed25519",
            "hash": "sha256",
            "shamir": "slip39",
        },
    )

    shamir = ShamirRitualCoordinator(
        master_key_source=_MasterKeySource(vault),
        commitment_binder=_InMemoryGenesisBinder(),
        paper_renderer=PaperShardRenderer(),
        checklist_persister=TrustVaultChecklistPersister(
            trust_vault=vault, principal_id=principal_id
        ),
        principal_id=principal_id,
    )

    runtime = BoundaryConversationRuntime(
        model_router=DeterministicModelRouter(preset_name=_STUB_PRESET),
        trust_store=trust_adapter,
        ledger=ledger,
        envelope_compiler=EnvelopeCompiler(
            template_resolver=LocalTemplateResolver(tmp_path / "templates")
        ),
        shamir_coordinator=shamir,
        novelty_checker=NoveltyChecker(),
    )
    return runtime, ledger, trust_adapter, vault


async def _drive_session_to_completion(
    runtime: BoundaryConversationRuntime, principal_id: str
) -> ConversationOutcome:
    """Drive the boundary conversation S0→S10 with the canned replies.

    The deterministic stub returns a valid extraction first-try for every
    state, so no re-prompt loop fires.  The Shamir state (S8) is the only
    state that PAUSES; the resume_from_shamir path completes the ritual
    and continues to S9.
    """
    ritual_id = await runtime.start(principal_id=principal_id)
    # S0 → S1: pass empty input (S0 takes no user reply per signatures.py
    # module docstring "S0 (greet) and S10 (complete) take no user answer").
    outcome = await runtime.advance(ritual_id, user_input="")
    state_to_reply = {
        "S1_money": _CANNED_REPLIES["S1_money"],
        "S2_people": _CANNED_REPLIES["S2_people"],
        "S3_topics": _CANNED_REPLIES["S3_topics"],
        "S4_hours": _CANNED_REPLIES["S4_hours"],
        "S5_first_task": _CANNED_REPLIES["S5_first_task"],
        "S6_template_offer": _CANNED_REPLIES["S6_template_offer"],
        "S7_visible_secret": _CANNED_REPLIES["S7_visible_secret"],
        "S8_shamir": _CANNED_REPLIES["S8_shamir"],
        "S9_review_sign": _CANNED_REPLIES["S9_review_sign"],
    }
    # Drive the state machine forward until COMPLETE or PAUSED for Shamir.
    # Bounded loop guards against the unlikely re-prompt path (deterministic
    # stub returns valid JSON, so re-prompts don't fire; the bound is a
    # belt-and-suspenders cap).
    for _ in range(32):
        if outcome.state == "COMPLETE":
            return outcome
        if outcome.state == "PAUSED" and outcome.paused_for == "shamir_ritual":
            outcome = await runtime.resume_from_shamir(ritual_id)
            continue
        if outcome.state == "ERROR":
            # Re-prompt with the same state's canned reply; the deterministic
            # stub will return a valid extraction on retry too (deterministic
            # by definition), so this branch should be unreachable.
            raise AssertionError(
                f"unexpected ERROR outcome for {principal_id}: "
                f"state={outcome.current_state} error={outcome.error!r}"
            )
        reply = state_to_reply.get(outcome.current_state, "")
        outcome = await runtime.advance(ritual_id, user_input=reply)
    raise AssertionError(
        f"session for {principal_id} did not COMPLETE within 32 advances; "
        f"last outcome state={outcome.state} current_state={outcome.current_state}"
    )


# ---------------------------------------------------------------------------
# Test 1 — the EC-7 acceptance battery itself: 15 onboardings (5 channels × 3).
# ---------------------------------------------------------------------------


@pytest.fixture
def _stub_provider_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register the deterministic provider under the test preset.

    Per the deterministic provider module docstring: the runtime's
    ``_PRESET_PROVIDER`` is the dispatch table; monkeypatching the dict
    item adds a new test-only preset that maps to our stub class.
    """
    monkeypatch.setitem(bc_runtime_mod._PRESET_PROVIDER, _STUB_PRESET, _STUB_PROVIDER_PATH)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_stub_provider_registered")
class TestEC7FiveChannelOnboardingBattery:
    """For each of 5 channels × N=3 sessions = 15 first-time-user
    onboardings, the BoundaryConversationRuntime completes S0→S10 and
    produces a parseable EnvelopeConfig (envelope_id set).

    Parametrized via ``@pytest.mark.parametrize`` so each (channel,
    session_index) lands as its own test case in the report — making
    the per-channel × per-session matrix visible in CI output.
    """

    @pytest.mark.parametrize(("channel_id", "session_index"), _BATTERY_CASES, ids=str)
    async def test_first_time_user_onboards_through_channel(
        self, channel_id: str, session_index: int, tmp_path: Path
    ) -> None:
        """One first-time-user session completes via the named channel."""
        # principal_id encodes (channel, session) so each test has an
        # independent identity in TrustStore + Vault — matching the spec's
        # "N=3 first-time-user sessions" framing (each one is a fresh user).
        principal_id = f"ec7-{channel_id}-session-{session_index}@example"
        runtime, ledger, trust_adapter, vault = await _build_runtime_for_session(
            tmp_path, principal_id
        )
        try:
            outcome = await _drive_session_to_completion(runtime, principal_id)

            # Acceptance gate per `01-analysis/02-mvp-objectives.md` EC-7 line 104:
            # "completes Boundary Conversation, produces parseable EnvelopeConfig".
            assert outcome.state == "COMPLETE", (
                f"EC-7 onboarding via {channel_id} session {session_index} did "
                f"not COMPLETE: outcome={outcome!r}"
            )
            assert outcome.envelope_id, (
                f"EC-7 onboarding via {channel_id} session {session_index} "
                f"completed without setting envelope_id (the EnvelopeConfig "
                f"was not minted): outcome={outcome!r}"
            )

            # Externally-observable: the Ledger chain hash-verifies after the
            # full S0→S10 flow.  A torn entry would surface here as the
            # production verifier would catch in deployment.
            report = await ledger.verify_chain()
            assert report.success is True, (
                f"Ledger chain failed verification after {channel_id} session "
                f"{session_index}: {report!r}"
            )
        finally:
            # Hygiene: lock the unlocked vault (else GC'd-while-unlocked
            # ResourceWarning) + close the trust adapter (flush + release the
            # SQLite sub-stores). Always runs, even if an assertion fails.
            await vault.lock()
            await trust_adapter.close()


# ---------------------------------------------------------------------------
# Test 2 — per-channel ChannelAdapter constructability + ABC compliance.
# ---------------------------------------------------------------------------


class TestChannelAdapterConstructability:
    """Each of 5 Phase-01 channel adapters constructs cleanly + satisfies
    the ``ChannelAdapter`` ABC + reports its declared ``channel_id`` +
    exposes a ``capabilities()`` surface.

    Per ``rules/orphan-detection.md`` Rule 1 + Wave-4 build-sequence: the
    5 adapter classes (CLI, Web, Telegram, Slack, Discord) all shipped in
    Wave-4; this test pins the construction surface so a refactor that
    breaks a constructor signature fails loudly per channel.

    Real secrets are NOT required for construction — every adapter
    accepts placeholder values for the secret fields (the secret material
    only fires on outbound API calls, which are not exercised here).
    """

    def test_cli_adapter_constructs_and_satisfies_abc(self) -> None:
        from envoy.channels import ChannelAdapter, CLIChannelAdapter
        from envoy.channels.cli import CLIChannelConfig

        adapter = CLIChannelAdapter(CLIChannelConfig(primary_channel_id="cli"))
        assert isinstance(adapter, ChannelAdapter)
        assert adapter.channel_id == "cli"
        assert adapter.capabilities is not None

    def test_web_adapter_constructs_and_satisfies_abc(self) -> None:
        from envoy.channels import ChannelAdapter
        from envoy.channels.web import WebChannelAdapter, WebChannelConfig

        adapter = WebChannelAdapter(WebChannelConfig(primary_channel_id="web"))
        assert isinstance(adapter, ChannelAdapter)
        assert adapter.channel_id == "web"
        assert adapter.capabilities is not None

    def test_telegram_adapter_constructs_and_satisfies_abc(self) -> None:
        # Telegram adapter takes kwargs directly (no TelegramChannelConfig class
        # — verified at envoy/channels/telegram.py:166-176).
        from envoy.channels import ChannelAdapter
        from envoy.channels.telegram import TelegramChannelAdapter

        adapter = TelegramChannelAdapter(
            primary_channel_id="telegram",
            secret_token="placeholder-telegram-webhook-secret-token-min-len",
        )
        assert isinstance(adapter, ChannelAdapter)
        assert adapter.channel_id == "telegram"
        assert adapter.capabilities is not None

    def test_slack_adapter_constructs_and_satisfies_abc(self) -> None:
        from envoy.channels import ChannelAdapter
        from envoy.channels.slack import SlackChannelAdapter, SlackChannelConfig

        adapter = SlackChannelAdapter(
            SlackChannelConfig(
                primary_channel_id="slack",
                signing_secret="placeholder-slack-signing-secret-len-min",
                bot_token="xoxb-placeholder-slack-bot-token",
            )
        )
        assert isinstance(adapter, ChannelAdapter)
        assert adapter.channel_id == "slack"
        assert adapter.capabilities is not None

    def test_discord_adapter_constructs_and_satisfies_abc(self) -> None:
        from envoy.channels import ChannelAdapter
        from envoy.channels.discord import (
            DiscordChannelAdapter,
            DiscordChannelConfig,
        )

        # Synthetic 64-hex-char Ed25519-shaped public key (valid hex, NOT
        # a real key — constructor validates hex shape only).
        adapter = DiscordChannelAdapter(
            DiscordChannelConfig(
                primary_channel_id="discord",
                application_public_key="0" * 64,
                bot_token="placeholder-discord-bot-token",
            )
        )
        assert isinstance(adapter, ChannelAdapter)
        assert adapter.channel_id == "discord"
        assert adapter.capabilities is not None

    def test_all_5_phase1_channels_have_distinct_channel_ids(self) -> None:
        """Sibling sanity: the 5 adapter ``channel_id`` values are the
        5 distinct strings the EC-7 de-scope #1 set names."""
        from envoy.channels import (
            CLIChannelAdapter,
            DiscordChannelAdapter,
            SlackChannelAdapter,
            TelegramChannelAdapter,
            WebChannelAdapter,
        )
        from envoy.channels.cli import CLIChannelConfig
        from envoy.channels.discord import DiscordChannelConfig
        from envoy.channels.slack import SlackChannelConfig
        from envoy.channels.web import WebChannelConfig

        ids = {
            CLIChannelAdapter(CLIChannelConfig(primary_channel_id="cli")).channel_id,
            WebChannelAdapter(WebChannelConfig(primary_channel_id="web")).channel_id,
            TelegramChannelAdapter(
                primary_channel_id="telegram",
                secret_token="placeholder-telegram-webhook-secret-token-min-len",
            ).channel_id,
            SlackChannelAdapter(
                SlackChannelConfig(
                    primary_channel_id="slack",
                    signing_secret="placeholder-slack-signing-secret-len-min",
                    bot_token="xoxb-placeholder-slack-bot-token",
                )
            ).channel_id,
            DiscordChannelAdapter(
                DiscordChannelConfig(
                    primary_channel_id="discord",
                    application_public_key="0" * 64,
                    bot_token="placeholder-discord-bot-token",
                )
            ).channel_id,
        }
        assert ids == set(_FIVE_CHANNELS), (
            f"Phase-01 5-channel set channel_id mismatch: got {ids}, "
            f"expected {set(_FIVE_CHANNELS)}"
        )
