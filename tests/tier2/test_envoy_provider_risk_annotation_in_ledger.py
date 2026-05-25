"""Tier 2 wiring: ProviderRisk annotation persists into the Ledger.

T-01-23 per shard 13 § 6.1 row 7 + `specs/model-adapter.md` line 16
("the runtime persists [the ProviderRisk annotation] in the assembled-
prompt's response Ledger entry").

Per `rules/testing.md` Tier 2: NO mocking. Real EnvoyLedger over real
InMemoryAuditStore + real Ed25519 sign. Per
`rules/orphan-detection.md` Rule 1 (every facade has a hot-path call
site) — this test IS the hot-path call site for
`EnvoyProviderRiskAnnotator.emit_ledger_entry()`.

NO real LLM call — the test validates the annotation→Ledger pipeline.
Real-LLM exercises live in the per-provider Tier 2 wiring tests.
"""

from __future__ import annotations

import pytest
from kailash.trust.audit_store import AuditFilter, InMemoryAuditStore

from envoy.ledger import EnvoyLedger
from envoy.model.risk import EnvoyProviderRiskAnnotator

# Synthetic structural identifiers — these tests verify annotation→Ledger
# round-trip ONLY (no LLM call); `os.environ` model names per
# `rules/env-models.md` are exercised in the per-provider Tier 2 wiring
# tests where the model is actually invoked.
_SYNTH_OLLAMA_MODEL = "synthetic-tier2-llama"
_SYNTH_OPENAI_MODEL = "synthetic-tier2-gpt"
_SYNTH_OPENAI_KEY = "sk-tier2-structural-only"


@pytest.fixture
def annotator() -> EnvoyProviderRiskAnnotator:
    return EnvoyProviderRiskAnnotator()


class TestEmitLedgerEntryShape:
    """The Ledger entry carries the full 9-field ProviderRisk shape."""

    async def test_self_hosted_annotation_round_trips_through_ledger(
        self,
        envoy_ledger: EnvoyLedger,
        audit_store: InMemoryAuditStore,
        annotator: EnvoyProviderRiskAnnotator,
    ) -> None:
        """Self-hosted preset (ollama_default_preset) → ProviderRisk
        annotation appended to Ledger; the persisted entry's content
        contains every spec-mandated field (lines 17-29) verbatim."""
        from kaizen.llm.presets import ollama_default_preset

        deployment = ollama_default_preset(model=_SYNTH_OLLAMA_MODEL)
        risk = annotator.annotate(deployment)

        # Hot-path call site for emit_ledger_entry — the facade method
        # we are wiring per orphan-detection Rule 1.
        entry_id = await annotator.emit_ledger_entry(
            envoy_ledger, risk, action_id="boundary-conv-action-001"
        )
        assert isinstance(entry_id, str)
        assert entry_id.startswith("sha256:")

        # Probe-driven verification (rules/probe-driven-verification.md
        # MUST Rule 3 — structural probe, no LLM): every annotation
        # field reachable via the persisted audit event's payload.
        events = await audit_store.query(AuditFilter())
        assert len(events) == 1
        ev = events[0]

        # `EnvoyLedger.append()` wraps content in an envelope shape; the
        # ProviderRisk dict lives under that envelope's content.
        # Locate it via the envoy_envelope_v1 metadata marker
        # (per facade pattern in T-01-18 ledger/facade.py).
        meta = getattr(ev, "metadata", None) or {}
        envelope = meta.get("_envoy_envelope_v1", {})
        assert envelope, "Ledger entry must carry _envoy_envelope_v1 metadata"
        content = envelope.get("content", {})
        risk_payload = content.get("provider_risk", {})
        assert risk_payload, "ProviderRisk must persist under content.provider_risk"

        # Every spec-mandated field present.
        assert risk_payload["provider_id"] == risk.provider_id
        assert risk_payload["model_family"] == risk.model_family
        assert risk_payload["model_version"] == risk.model_version
        assert risk_payload["risk_class"] == "Self-hosted"
        assert risk_payload["training_data_leak_class"] == risk.training_data_leak_class
        assert risk_payload["jurisdiction"] == risk.jurisdiction
        assert risk_payload["data_retention_policy_url"] == risk.data_retention_policy_url
        assert risk_payload["annotated_at"] == risk.annotated_at
        # Self-hosted: no Foundation attestation.
        assert risk_payload["foundation_attestation_signature_hex"] is None

        # action_id surfaces in the persisted content (operator audit trail).
        assert content.get("action_id") == "boundary-conv-action-001"

    async def test_provider_bound_annotation_round_trips(
        self,
        envoy_ledger: EnvoyLedger,
        audit_store: InMemoryAuditStore,
        annotator: EnvoyProviderRiskAnnotator,
    ) -> None:
        """Provider-bound preset (openai) → annotation captures the
        Provider-bound risk_class verbatim per shard 13 § 3.3."""
        from kaizen.llm.presets import openai_preset

        deployment = openai_preset(api_key=_SYNTH_OPENAI_KEY, model=_SYNTH_OPENAI_MODEL)
        risk = annotator.annotate(deployment)
        assert risk.risk_class == "Provider-bound"

        await annotator.emit_ledger_entry(envoy_ledger, risk, action_id="grant-moment-action-002")

        events = await audit_store.query(AuditFilter())
        assert len(events) == 1
        envelope = (events[0].metadata or {}).get("_envoy_envelope_v1", {})
        content = envelope.get("content", {})
        risk_payload = content.get("provider_risk", {})
        assert risk_payload["risk_class"] == "Provider-bound"

    async def test_multiple_annotations_each_append_distinct_entries(
        self,
        envoy_ledger: EnvoyLedger,
        audit_store: InMemoryAuditStore,
        annotator: EnvoyProviderRiskAnnotator,
    ) -> None:
        """Per spec line 60 (`model_switch` entries record provider
        transitions): two distinct provider annotations append two
        Ledger entries — neither overwrites the other; the chain is
        monotonic in sequence."""
        from kaizen.llm.presets import (
            ollama_default_preset,
            openai_preset,
        )

        risk1 = annotator.annotate(ollama_default_preset(model=_SYNTH_OLLAMA_MODEL))
        risk2 = annotator.annotate(
            openai_preset(api_key=_SYNTH_OPENAI_KEY, model=_SYNTH_OPENAI_MODEL)
        )

        id1 = await annotator.emit_ledger_entry(envoy_ledger, risk1, action_id="a1")
        id2 = await annotator.emit_ledger_entry(envoy_ledger, risk2, action_id="a2")
        assert id1 != id2

        events = await audit_store.query(AuditFilter())
        assert len(events) == 2

        # Sequence monotonic per T-01-18 facade contract.
        seq1 = ((events[0].metadata or {}).get("_envoy_envelope_v1", {})).get("sequence")
        seq2 = ((events[1].metadata or {}).get("_envoy_envelope_v1", {})).get("sequence")
        assert seq1 is not None and seq2 is not None
        assert seq2 == seq1 + 1
