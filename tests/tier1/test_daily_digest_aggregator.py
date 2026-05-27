"""Tier 1 — T-04-81 — LedgerAggregator.

Source: T-04-81 per `workspaces/phase-01-mvp/todos/active/04-wave-4-channels-
digest.md` § T-04-81 + shard 11 § 5.1.

Coverage:
1. aggregate() returns a correctly-typed DigestSummary (5 sections).
2. Section → entry-type mapping (PhaseBRecord→actions, posture_change(deny)/
   system_error(refusal)→refusals, grant_moment(pending)→pending_grants,
   PhaseARecord→planned_today).
3. Refusal predicate filters benign posture_change (decision != deny) +
   non-refusal system_error.
4. Section ordering is stable sequence-ascending.
5. `spend` shape is exactly the 2-key dict from the spec.
6. record_ids route through format_record_id_for_event (redaction site).

Per `rules/testing.md` Tier 1: real `InMemoryAuditStore` + real
`InMemoryKeyManager` (zero-dep kailash fixtures); the aggregator runs against
a real EnvoyLedger. Probe-driven structural assertions per
`rules/probe-driven-verification.md` — counts, type checks, dict-shape, and
redaction-form, never regex over prose.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from kailash.trust.audit_store import InMemoryAuditStore
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.daily_digest.aggregator import LedgerAggregator
from envoy.daily_digest.payload import DigestSummary
from envoy.ledger import EnvoyLedger

_ALGO = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}
_PID = "principal-aggtest-01"
_SIGNING_KEY = "envoy-signing-key"


@pytest.fixture
async def ledger() -> EnvoyLedger:
    mgr = InMemoryKeyManager()
    await mgr.generate_keypair(_SIGNING_KEY)
    return EnvoyLedger(
        audit_store=InMemoryAuditStore(),
        key_manager=mgr,
        signing_key_id=_SIGNING_KEY,
        device_id="device-aggtest",
        algorithm_identifier=_ALGO,
    )


async def _seed(ledger: EnvoyLedger) -> None:
    """Append a representative mix of entry types for principal _PID."""
    await ledger.append(
        entry_type="PhaseBRecord",
        content={
            "principal_id": _PID,
            "summary": "sent welcome email",
            "outbox_items": ["email-1"],
            "cost_microdollars": 1500,
            "monthly_ceiling_microdollars": 1_000_000,
        },
    )
    await ledger.append(
        entry_type="PhaseBRecord",
        content={
            "principal_id": _PID,
            "summary": "scheduled meeting",
            "cost_microdollars": 500,
        },
    )
    # Refusal: posture_change with decision=deny.
    await ledger.append(
        entry_type="posture_change",
        content={"principal_id": _PID, "decision": "deny", "reason_code": "out_of_envelope"},
    )
    # Benign posture_change (NOT a refusal — decision=allow).
    await ledger.append(
        entry_type="posture_change",
        content={"principal_id": _PID, "decision": "allow"},
    )
    # system_error with refusal_class (IS a refusal).
    await ledger.append(
        entry_type="system_error",
        content={"principal_id": _PID, "refusal_class": "rate_limited", "reason_code": "429"},
    )
    # system_error without refusal_class (NOT a refusal).
    await ledger.append(
        entry_type="system_error",
        content={"principal_id": _PID, "fault": "transient_io"},
    )
    # Pending grant.
    await ledger.append(
        entry_type="grant_moment",
        content={
            "principal_id": _PID,
            "state": "pending",
            "grant_id": "grant-1",
            "summary": "approve payment",
        },
    )
    # Resolved grant (NOT pending).
    await ledger.append(
        entry_type="grant_moment",
        content={"principal_id": _PID, "state": "approved", "grant_id": "grant-0"},
    )
    # Planned (PhaseARecord).
    await ledger.append(
        entry_type="PhaseARecord",
        content={"principal_id": _PID, "intent_id": "intent-1", "summary": "draft report"},
    )
    # Entry for a DIFFERENT principal — must be excluded.
    await ledger.append(
        entry_type="PhaseBRecord",
        content={"principal_id": "other-principal", "summary": "not mine"},
    )


def _window() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=1), now + timedelta(days=1))


class TestAggregateShape:
    @pytest.mark.asyncio
    async def test_returns_digest_summary(self, ledger: EnvoyLedger) -> None:
        await _seed(ledger)
        since, until = _window()
        agg = LedgerAggregator(ledger=ledger)
        summary = await agg.aggregate(principal_id=_PID, since=since, until=until)
        assert isinstance(summary, DigestSummary)

    @pytest.mark.asyncio
    async def test_section_counts(self, ledger: EnvoyLedger) -> None:
        await _seed(ledger)
        since, until = _window()
        summary = await LedgerAggregator(ledger=ledger).aggregate(
            principal_id=_PID,
            since=since,
            until=until,
        )
        assert len(summary.actions) == 2  # 2 PhaseBRecord for _PID
        assert len(summary.refusals) == 2  # deny posture_change + refusal_class system_error
        assert len(summary.pending_grants) == 1  # only state=pending
        assert len(summary.planned_today) == 1  # 1 PhaseARecord

    @pytest.mark.asyncio
    async def test_other_principal_excluded(self, ledger: EnvoyLedger) -> None:
        await _seed(ledger)
        since, until = _window()
        summary = await LedgerAggregator(ledger=ledger).aggregate(
            principal_id=_PID,
            since=since,
            until=until,
        )
        # The "other-principal" PhaseBRecord must NOT appear.
        for row in summary.actions:
            assert row["summary"] != "not mine"


class TestRefusalPredicate:
    @pytest.mark.asyncio
    async def test_benign_posture_change_excluded(self, ledger: EnvoyLedger) -> None:
        await _seed(ledger)
        since, until = _window()
        summary = await LedgerAggregator(ledger=ledger).aggregate(
            principal_id=_PID,
            since=since,
            until=until,
        )
        reason_codes = {r["reason_code"] for r in summary.refusals}
        # deny posture_change surfaces "out_of_envelope"; refusal system_error surfaces "429".
        assert reason_codes == {"out_of_envelope", "429"}


class TestSpendShape:
    @pytest.mark.asyncio
    async def test_spend_exact_two_keys(self, ledger: EnvoyLedger) -> None:
        await _seed(ledger)
        since, until = _window()
        summary = await LedgerAggregator(ledger=ledger).aggregate(
            principal_id=_PID,
            since=since,
            until=until,
        )
        assert set(summary.spend.keys()) == {
            "current_microdollars",
            "monthly_ceiling_microdollars",
        }

    @pytest.mark.asyncio
    async def test_spend_sums_cost(self, ledger: EnvoyLedger) -> None:
        await _seed(ledger)
        since, until = _window()
        summary = await LedgerAggregator(ledger=ledger).aggregate(
            principal_id=_PID,
            since=since,
            until=until,
        )
        # 1500 + 500 from the two PhaseBRecords.
        assert summary.spend["current_microdollars"] == 2000
        assert summary.spend["monthly_ceiling_microdollars"] == 1_000_000


class TestRedactionSite:
    @pytest.mark.asyncio
    async def test_record_ids_routed_through_redactor(self, ledger: EnvoyLedger) -> None:
        """With a classification_policy that classifies the field, ledger_ids
        become sha256:<hex>. The aggregator MUST be the single-point filter."""
        await _seed(ledger)
        since, until = _window()

        calls: list[tuple] = []

        # Wrap the module-level redactor to record invocations — proves the
        # aggregator routes every record_id through the single-point filter.
        import envoy.daily_digest.aggregator as agg_mod

        original = agg_mod.format_record_id_for_event

        def _spy(policy, model_name, record_id, *a, **k):
            calls.append((model_name, record_id))
            return original(policy, model_name, record_id, *a, **k)

        agg_mod.format_record_id_for_event = _spy
        try:
            await LedgerAggregator(ledger=ledger).aggregate(
                principal_id=_PID,
                since=since,
                until=until,
            )
        finally:
            agg_mod.format_record_id_for_event = original

        # Every action/refusal/grant/planned row routed its id through the redactor.
        # 2 actions + 2 refusals + 1 grant + 1 planned = 6 redaction calls minimum.
        assert len(calls) >= 6
        assert all(model_name == "daily_digest" for model_name, _ in calls)


class TestOrdering:
    @pytest.mark.asyncio
    async def test_actions_stable_sequence_order(self, ledger: EnvoyLedger) -> None:
        await _seed(ledger)
        since, until = _window()
        summary = await LedgerAggregator(ledger=ledger).aggregate(
            principal_id=_PID,
            since=since,
            until=until,
        )
        # Seeded order: "sent welcome email" then "scheduled meeting".
        summaries = [row["summary"] for row in summary.actions]
        assert summaries == ["sent welcome email", "scheduled meeting"]
