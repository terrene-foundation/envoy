"""Tier 1 — T-04-81 — DigestRenderer.

Source: T-04-81 per `workspaces/phase-01-mvp/todos/active/04-wave-4-channels-
digest.md` § T-04-81 + shard 11 § 3 step 3 + § 3.2 item 4.

Coverage:
1. render() returns a DigestPayload with all 11 fields populated.
2. schema_version == "digest/1.0".
3. receipt_hash is deterministic — _compute_receipt_hash with identical inputs
   yields byte-identical output (the cross-channel byte-identity guarantee,
   open question 5).
4. principal_genesis_id is the redacted form (not the raw input).
5. delivered_at is None at render time (set by fanout/receipt, not the payload).
6. event_only form still carries the full summary section tuples.

Per `rules/probe-driven-verification.md`: structural probes only — field
presence, equality, hash determinism, type identity. No regex over prose.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from kailash.trust.audit_store import InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.daily_digest.payload import (
    DIGEST_SCHEMA_VERSION,
    DigestPayload,
    DigestSummary,
    DuressBanner,
)
from envoy.daily_digest.renderer import DigestRenderer
from envoy.ledger import EnvoyLedger
from envoy.model.router import EnvoyModelRouter

_ALGO = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}
_SIGNING_KEY = "envoy-signing-key"
_PID = "principal-rendertest-01"


@pytest.fixture
async def ledger() -> EnvoyLedger:
    mgr = InMemoryKeyManager()
    await mgr.generate_keypair(_SIGNING_KEY)
    return EnvoyLedger(
        audit_store=InMemoryAuditStore(),
        key_manager=mgr,
        signing_key_id=_SIGNING_KEY,
        device_id="device-rendertest",
        algorithm_identifier=_ALGO,
    )


@pytest.fixture
def renderer(ledger: EnvoyLedger) -> DigestRenderer:
    return DigestRenderer(model_router=EnvoyModelRouter(), ledger=ledger)


def _summary() -> DigestSummary:
    return DigestSummary(
        actions=({"ledger_id": "e1", "summary": "did a thing", "outbox_items": ()},),
        refusals=(),
        spend={"current_microdollars": 2000, "monthly_ceiling_microdollars": 1_000_000},
        pending_grants=(),
        planned_today=(),
    )


def _scheduled() -> datetime:
    return datetime(2026, 5, 27, 8, 0, tzinfo=timezone.utc)


class TestRenderShape:
    @pytest.mark.asyncio
    async def test_returns_full_payload(self, renderer: DigestRenderer) -> None:
        payload = await renderer.render(
            principal_id=_PID,
            channel_id="cli",
            summary=_summary(),
            duress_banner=DuressBanner(present=False, shadow_event_ref=None),
            form="rich",
            scheduled_for=_scheduled(),
            back_fill_days=0,
        )
        assert isinstance(payload, DigestPayload)
        # All 11 fields populated (only delivered_at + user_reply are None).
        assert payload.schema_version == DIGEST_SCHEMA_VERSION
        assert payload.digest_id
        assert payload.principal_genesis_id
        assert payload.scheduled_for == _scheduled().isoformat()
        assert payload.delivered_at is None
        assert payload.channel_id == "cli"
        assert payload.form == "rich"
        assert isinstance(payload.duress_banner, DuressBanner)
        assert isinstance(payload.summary, DigestSummary)
        assert payload.user_reply is None
        assert payload.receipt_hash.startswith("sha256:")

    @pytest.mark.asyncio
    async def test_event_only_keeps_summary(self, renderer: DigestRenderer) -> None:
        payload = await renderer.render(
            principal_id=_PID,
            channel_id="cli",
            summary=_summary(),
            duress_banner=DuressBanner(present=False, shadow_event_ref=None),
            form="event_only",
            scheduled_for=_scheduled(),
            back_fill_days=0,
        )
        # Rendering form is a channel-adapter concern; the renderer never
        # truncates the section tuples.
        assert len(payload.summary.actions) == 1
        assert payload.form == "event_only"


class TestReceiptHashByteIdentity:
    def test_receipt_hash_deterministic(self, renderer: DigestRenderer) -> None:
        """Identical content → byte-identical receipt_hash (open question 5).

        Calls the pure _compute_receipt_hash with fixed inputs twice and
        asserts equality. (render() generates a fresh digest_id per call, so
        the determinism lives in _compute_receipt_hash with a fixed digest_id —
        which is exactly the single-render-then-fanout production path.)
        """
        kwargs = dict(
            schema_version=DIGEST_SCHEMA_VERSION,
            digest_id="018e7b00-0000-7000-0000-000000000001",
            principal_genesis_id="sha256:" + "a" * 64,
            scheduled_for=_scheduled().isoformat(),
            channel_id="cli",
            form="rich",
            duress_banner=DuressBanner(present=False, shadow_event_ref=None),
            summary=_summary(),
        )
        h1 = renderer._compute_receipt_hash(**kwargs)
        h2 = renderer._compute_receipt_hash(**kwargs)
        assert h1 == h2
        assert h1.startswith("sha256:")

    def test_receipt_hash_changes_with_content(self, renderer: DigestRenderer) -> None:
        """Different content → different receipt_hash (the hash is load-bearing)."""
        base = dict(
            schema_version=DIGEST_SCHEMA_VERSION,
            digest_id="018e7b00-0000-7000-0000-000000000001",
            principal_genesis_id="sha256:" + "a" * 64,
            scheduled_for=_scheduled().isoformat(),
            channel_id="cli",
            form="rich",
            duress_banner=DuressBanner(present=False, shadow_event_ref=None),
            summary=_summary(),
        )
        h1 = renderer._compute_receipt_hash(**base)

        other = DigestSummary(
            actions=(),
            refusals=(),
            spend={"current_microdollars": 999, "monthly_ceiling_microdollars": 1},
            pending_grants=(),
            planned_today=(),
        )
        h2 = renderer._compute_receipt_hash(**{**base, "summary": other})
        assert h1 != h2


class TestGenesisRedaction:
    @pytest.mark.asyncio
    async def test_genesis_id_redacted_with_policy(self) -> None:
        """With a classifying policy, principal_genesis_id is the hashed form.

        Wrap the module redactor so the test does not depend on a live
        ClassificationPolicy — proves the renderer routes the id through the
        single-point filter."""
        import envoy.daily_digest.renderer as rend_mod

        mgr = InMemoryKeyManager()
        await mgr.generate_keypair(_SIGNING_KEY)
        ledger = EnvoyLedger(
            audit_store=InMemoryAuditStore(),
            key_manager=mgr,
            signing_key_id=_SIGNING_KEY,
            device_id="device-redact",
            algorithm_identifier=_ALGO,
        )
        renderer = DigestRenderer(model_router=EnvoyModelRouter(), ledger=ledger)

        original = rend_mod.format_record_id_for_event
        seen: list[str] = []

        def _spy(policy, model_name, record_id, *a, **k):
            seen.append(record_id)
            return "sha256:redacted8"  # simulate classification

        rend_mod.format_record_id_for_event = _spy
        try:
            payload = await renderer.render(
                principal_id="raw-genesis-id",
                channel_id="cli",
                summary=_summary(),
                duress_banner=DuressBanner(present=False, shadow_event_ref=None),
                form="rich",
                scheduled_for=_scheduled(),
                back_fill_days=0,
            )
        finally:
            rend_mod.format_record_id_for_event = original

        assert "raw-genesis-id" in seen  # routed through the redactor
        assert payload.principal_genesis_id == "sha256:redacted8"
        assert payload.principal_genesis_id != "raw-genesis-id"
