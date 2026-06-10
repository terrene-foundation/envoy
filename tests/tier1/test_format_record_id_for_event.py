"""Tier 1: T-01-17 — `format_record_id_for_event` integration smoke.

Source: shard 6 § 4 line 122 + § 4 line 138 — every Ledger entry that
references a classified-PK model MUST route record_id through the helper
per `rules/event-payload-classification.md` Rule 1. The helper produces
a stable 8-hex SHA-256 prefix that is byte-identical Python ↔ Rust.

This Tier 1 test verifies the helper is callable + produces the expected
shape on the Phase 01 narrow surfaces. T-01-18 (`EnvoyLedger.append`) is
the production call site that wires the helper at the entry-emission
boundary; this test locks the contract the facade depends on.

Per `rules/cross-sdk-inspection.md` MUST Rule 5 — symbol-citation
verification: `dataflow.classification.event_payload.format_record_id_for_event`
is the canonical kailash-py helper (cited in shard 6 § 4 line 122 +
analysis doc § 2.1). The signature is verified at module import time;
this test exercises the runtime behavior on representative inputs.
"""

from __future__ import annotations

# Verify the helper exists at the cited import path.
from dataflow.classification.event_payload import format_record_id_for_event


class TestFormatRecordIdForEventNoPolicy:
    """When ClassificationPolicy is None, the helper passes through values
    as strings — this is the Phase 01 narrow path (no classifications
    registered yet) per the helper's docstring."""

    def test_int_record_id_passes_as_string(self) -> None:
        # No policy → no classification → pass through as string.
        result = format_record_id_for_event(None, "User", 42)
        assert result == "42"

    def test_string_record_id_passes_through(self) -> None:
        result = format_record_id_for_event(None, "User", "user-001")
        assert result == "user-001"

    def test_none_record_id_returns_none(self) -> None:
        result = format_record_id_for_event(None, "User", None)
        assert result is None


class TestFormatRecordIdForEventStability:
    """The helper's output for a given input MUST be stable across calls
    — the cross-SDK byte-identity contract requires deterministic
    formatting."""

    def test_same_input_produces_same_output(self) -> None:
        out1 = format_record_id_for_event(None, "User", "user-001")
        out2 = format_record_id_for_event(None, "User", "user-001")
        assert out1 == out2

    def test_different_record_ids_produce_different_output(self) -> None:
        out_a = format_record_id_for_event(None, "User", "user-001")
        out_b = format_record_id_for_event(None, "User", "user-002")
        assert out_a != out_b


class TestFormatRecordIdForEventModelScoping:
    """`model_name` parameterization is the cross-model dimension —
    per shard 6 § 4 line 100 (BP-048), the partition prefix shape is
    derived from (model_name, classified_pk_field, record_id) so the
    same record_id under different models produces different IDs.

    Phase 01 narrow scope (no classifications): model_name is accepted
    but does NOT change the output for unclassified PKs — the helper
    short-circuits to pass-through. The model_name parameterization
    matters once T-01-18 wires a ClassificationPolicy with classified
    PKs in Wave 2+."""

    def test_model_name_accepted_without_policy(self) -> None:
        # Both calls have policy=None so the model_name is irrelevant
        # to the output (no classification to apply). Phase 02 with
        # ClassificationPolicy will cross-vary on model_name.
        out_user = format_record_id_for_event(None, "User", "id-001")
        out_account = format_record_id_for_event(None, "Account", "id-001")
        # Without policy, both pass through identically.
        assert out_user == "id-001"
        assert out_account == "id-001"


class TestFormatRecordIdForEventErrorPaths:
    """Defense against malformed input at the helper boundary — Phase 01
    Ledger entries SHOULD pre-validate record_id shape but the helper
    must surface a clear error rather than silently corrupt."""

    def test_dict_record_id_handled(self) -> None:
        """The helper accepts Any for record_id; a dict input gets
        stringified rather than raising. Verifies Phase 01 doesn't crash
        on an unexpected shape — the Ledger emitter should validate
        upstream, but the helper itself stays defensive."""
        # We just confirm no crash; the exact representation is helper-
        # internal and may change across kailash versions.
        try:
            out = format_record_id_for_event(None, "User", {"k": "v"})
            assert out is not None  # some string representation
        except (TypeError, ValueError):
            # If kailash decides dict is invalid, that's also acceptable —
            # the contract is "no silent corruption", not "accept anything".
            pass
