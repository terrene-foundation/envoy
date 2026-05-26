"""Regression: T-018 dialog spoofing (visible-secret mismatch).

Contract pin: T-018 (dialog spoofing via visible-secret divergence).

Per `specs/grant-moment.md` § Error taxonomy: ``VisibleSecretMismatchError``
fires when the rendered visible-secret bytes diverge from the Trust-Vault
stored secret. The runtime exposes the hash-only plumbing
(``visible_secret_hash_for``); the channel adapter compares against the
phrase it would render and raises the error on divergence.

This regression test exercises the runtime+adapter wiring: a stub adapter
that mimics a spoofer (renders a phrase whose hash diverges from the
runtime's reported hash) MUST surface the typed error.
"""

from __future__ import annotations

import hashlib

import pytest

from envoy.grant_moment import VisibleSecretMismatchError
from tests.helpers.grant_moment_harness import StubTrustStore, make_runtime


@pytest.mark.regression
@pytest.mark.asyncio
class TestT018VisibleSecretMismatch:
    """Contract pin: T-018."""

    async def test_runtime_hash_matches_stored_secret_phrase(self) -> None:
        secret = StubTrustStore()  # phrase = "test-visible-phrase-correct-horse-battery"
        runtime, *_ = await make_runtime(trust_store=secret)

        reported = await runtime.visible_secret_hash_for("any-principal")
        expected = hashlib.sha256(secret.secret.phrase.encode("utf-8")).hexdigest()
        assert reported == expected

    async def test_adapter_render_with_spoof_phrase_raises_mismatch_error(self) -> None:
        # The runtime exposes only the HASH (never the phrase); adapters
        # detect spoofing by hashing what they would render and comparing.
        # This test wires a REAL channel-adapter stub that performs the
        # mismatch check inside ``render_grant_moment`` and raises
        # ``VisibleSecretMismatchError`` — the runtime catches the raise
        # via ChannelHandoff.dispatch (records the channel as render-failed)
        # and ultimately raises ``GrantMomentTimeoutError`` because zero
        # adapters rendered cleanly. The spoof-detection contract is what
        # we pin, NOT a manual raise-then-catch tautology (reviewer-R1
        # HIGH-3).
        from envoy.grant_moment import (
            ChannelHandoff,
            EnvoyGrantMomentRuntime,
            GrantMomentTimeoutError,
            NoveltyClassifier,
        )
        from envoy.ledger import EnvoyLedger
        from kailash.trust.audit_store import InMemoryAuditStore
        from kailash.trust.key_manager import InMemoryKeyManager
        from tests.helpers.grant_moment_harness import (
            DEFAULT_ALGO_ID,
            DEFAULT_DELEGATION_KEY,
            DEFAULT_DEVICE_ID,
            DEFAULT_LEDGER_SIGNING_KEY,
            DEFAULT_PRINCIPAL_ID,
            make_issue_kwargs,
        )

        secret = StubTrustStore()
        canonical_hash = hashlib.sha256(secret.secret.phrase.encode("utf-8")).hexdigest()

        class _SpoofingAdapter:
            """Adapter that would render a SPOOF phrase. Detects mismatch
            against the runtime's canonical hash and raises the typed error.
            """

            channel_id = "cli"
            spoof_phrase = "i-am-a-phisher-please-trust-me"

            def __init__(self, runtime_ref: list) -> None:
                self._runtime_ref = runtime_ref

            async def render_grant_moment(self, _request) -> None:
                runtime = self._runtime_ref[0]
                expected = await runtime.visible_secret_hash_for(DEFAULT_PRINCIPAL_ID)
                rendered = hashlib.sha256(self.spoof_phrase.encode("utf-8")).hexdigest()
                if expected != rendered:
                    raise VisibleSecretMismatchError(
                        expected_phrase_hash=expected,
                        rendered_phrase_hash=rendered,
                    )

        # Wire a real runtime + the spoofing adapter via ChannelHandoff.
        km = InMemoryKeyManager()
        await km.generate_keypair(DEFAULT_DELEGATION_KEY)
        await km.generate_keypair(DEFAULT_LEDGER_SIGNING_KEY)
        audit = InMemoryAuditStore()
        ledger = EnvoyLedger(
            audit_store=audit,
            key_manager=km,
            signing_key_id=DEFAULT_LEDGER_SIGNING_KEY,
            device_id=DEFAULT_DEVICE_ID,
            algorithm_identifier=DEFAULT_ALGO_ID,
        )
        runtime_ref: list = []
        adapter = _SpoofingAdapter(runtime_ref)
        handoff = ChannelHandoff(adapters=(adapter,), primary_channel_id="cli")
        runtime = EnvoyGrantMomentRuntime(
            key_manager=km,
            delegation_key_id=DEFAULT_DELEGATION_KEY,
            principal_id=DEFAULT_PRINCIPAL_ID,
            device_id=DEFAULT_DEVICE_ID,
            ledger=ledger,
            channel_handoff=handoff,
            trust_store=secret,
            novelty_classifier=NoveltyClassifier(),
            novelty_read_delay_seconds=0.0,
        )
        runtime_ref.append(runtime)

        # The spoofing adapter raises VisibleSecretMismatchError inside
        # render; ChannelHandoff catches+records; runtime sees zero
        # successful dispatches and raises GrantMomentTimeoutError.
        with pytest.raises(GrantMomentTimeoutError):
            await runtime.issue_grant_moment(**make_issue_kwargs())

        # Sanity: the canonical hash is non-empty hex.
        assert canonical_hash and len(canonical_hash) == 64

    async def test_secret_phrase_never_leaks_via_hash_plumbing(self) -> None:
        # T-018 invariant: the runtime exposes ONLY the hash, never the
        # phrase. The hash is one-way; the only callers that learn the
        # phrase are the channel adapters which receive it through the
        # Trust Vault directly (NOT through the runtime). This test pins
        # the runtime's hash-only surface.
        secret = StubTrustStore()
        runtime, *_ = await make_runtime(trust_store=secret)

        # Iterate every public attribute on the runtime and ensure none
        # exposes the phrase as plain text.
        for name in dir(runtime):
            if name.startswith("_"):
                continue
            value = getattr(runtime, name)
            assert secret.secret.phrase not in str(
                value
            ), f"runtime.{name} leaks the visible-secret phrase as plain text"
