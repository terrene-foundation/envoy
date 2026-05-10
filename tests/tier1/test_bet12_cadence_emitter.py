"""Tier 1 unit tests for envoy.authorship.bet12_emitter (T-02-32).

Per `rules/testing.md` § Tier 1 (mocking allowed; <1s per test).

Covers the 2 invariants from `02-wave-2-...md` § T-02-32 capacity check:

1. **bet_id tag canonical** — every payload carries `bet_id="BET-12"`
   regardless of caller-supplied data; module constant has no per-call
   override surface.
2. **Emit on every posture-transition** — the production call site
   (PostureGate Step 5+) is exercised in the wiring test below; the
   emitter primitive itself is verified to deliver one payload per
   `emit()` call.

Plus:

- principal_id hashing per `rules/event-payload-classification.md` Rule 2
  (`sha256:` + 8 hex chars; raw principal_id never appears in payload).
- Privacy contract per Rule 3 — no envelope hash, no authored_constraints
  names, no classified field names in payload (structurally enforced by
  the public emit() signature).
- Boundary value-range guards — negative days / authored count fail loud.
- Sink error propagation — emitter does NOT swallow.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass, field

import pytest

from envoy.authorship.bet12_emitter import (
    BET12CadenceEmitter,
    BET12CadencePayload,
    BET12Sink,
)
from envoy.authorship.posture_gate import PostureLevel


@dataclass
class _FakeSink:
    """In-memory BET-12 sink fake. Records every cadence payload written."""

    writes: list[BET12CadencePayload] = field(default_factory=list)
    raise_on_write: BaseException | None = None

    async def write(self, payload: BET12CadencePayload) -> None:
        if self.raise_on_write is not None:
            raise self.raise_on_write
        self.writes.append(payload)


def _run(coro):
    """Tier-1 helper: run async without pytest-asyncio (which requires a
    plugin declaration we don't currently ship per `rules/testing.md`
    § Pytest Plugin + Marker Declaration Pair)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Construction discipline
# ---------------------------------------------------------------------------


class TestEmitterConstruction:
    def test_sink_required(self):
        with pytest.raises(ValueError, match="sink is required"):
            BET12CadenceEmitter(sink=None)  # type: ignore[arg-type]

    def test_sink_protocol_runtime_checkable(self):
        # `BET12Sink` is `runtime_checkable` so Tier 2 wiring can assert
        # structural conformance against fakes without inheritance coupling.
        sink = _FakeSink()
        assert isinstance(sink, BET12Sink)


# ---------------------------------------------------------------------------
# Invariant 1 — bet_id tag is canonical "BET-12" on every emit
# ---------------------------------------------------------------------------


class TestBetIdCanonical:
    def test_payload_bet_id_is_bet12(self):
        sink = _FakeSink()
        emitter = BET12CadenceEmitter(sink=sink)
        _run(
            emitter.emit(
                principal_id="agent-001",
                from_level=PostureLevel.PSEUDO,
                to_level=PostureLevel.TOOL,
                days_at_current_posture=0.0,
                authored_count_at_transition=0,
            )
        )
        assert len(sink.writes) == 1
        assert sink.writes[0].bet_id == "BET-12"

    def test_no_per_call_bet_id_override_surface(self):
        # Defense-in-depth: the public emit() signature MUST NOT accept a
        # `bet_id` kwarg. Future BET measurement emitters ship as separate
        # classes per `01-analysis/09-...md` § 3.3 disposition.
        import inspect

        params = inspect.signature(BET12CadenceEmitter.emit).parameters
        assert "bet_id" not in params, (
            "BET12CadenceEmitter.emit must NOT expose bet_id as a kwarg; the "
            "tag is module-level canonical. Future BET-N emitters ship as "
            "separate classes per analysis disposition."
        )


# ---------------------------------------------------------------------------
# principal_id hashing (rules/event-payload-classification.md Rule 2)
# ---------------------------------------------------------------------------


class TestPrincipalIdHashing:
    def test_hash_shape_sha256_8_hex(self):
        sink = _FakeSink()
        emitter = BET12CadenceEmitter(sink=sink)
        _run(
            emitter.emit(
                principal_id="agent-secret-id",
                from_level=PostureLevel.TOOL,
                to_level=PostureLevel.SUPERVISED,
                days_at_current_posture=1.0,
                authored_count_at_transition=1,
            )
        )
        h = sink.writes[0].principal_id_hash
        assert re.match(
            r"^sha256:[0-9a-f]{8}$", h
        ), f"hash shape MUST be 'sha256:' + 8 hex chars, got {h!r}"

    def test_hash_matches_sha256_first_8_hex(self):
        # Cross-SDK forensic correlation requires byte-identity with the
        # kailash-py format_record_id_for_event helper (sha256 of the
        # encoded id, first 8 hex chars).
        sink = _FakeSink()
        emitter = BET12CadenceEmitter(sink=sink)
        principal_id = "user-12345"
        expected = "sha256:" + hashlib.sha256(principal_id.encode("utf-8")).hexdigest()[:8]
        _run(
            emitter.emit(
                principal_id=principal_id,
                from_level=PostureLevel.TOOL,
                to_level=PostureLevel.SUPERVISED,
                days_at_current_posture=2.5,
                authored_count_at_transition=1,
            )
        )
        assert sink.writes[0].principal_id_hash == expected

    def test_raw_principal_id_not_in_payload_repr(self):
        # `rules/event-payload-classification.md` Rule 2 + 4: raw
        # principal_id MUST NOT appear in any string representation of
        # the payload (defends against accidental log emission).
        sink = _FakeSink()
        emitter = BET12CadenceEmitter(sink=sink)
        principal_id = "very-secret-principal-token-001"
        _run(
            emitter.emit(
                principal_id=principal_id,
                from_level=PostureLevel.SUPERVISED,
                to_level=PostureLevel.DELEGATING,
                days_at_current_posture=7.0,
                authored_count_at_transition=3,
            )
        )
        rendered = repr(sink.writes[0])
        assert (
            principal_id not in rendered
        ), f"raw principal_id leaked into payload repr: {rendered}"

    def test_empty_principal_id_rejected(self):
        sink = _FakeSink()
        emitter = BET12CadenceEmitter(sink=sink)
        with pytest.raises(ValueError, match="principal_id must be a non-empty str"):
            _run(
                emitter.emit(
                    principal_id="",
                    from_level=PostureLevel.PSEUDO,
                    to_level=PostureLevel.TOOL,
                    days_at_current_posture=0.0,
                    authored_count_at_transition=0,
                )
            )
        assert sink.writes == []

    def test_distinct_ids_produce_distinct_hashes(self):
        sink = _FakeSink()
        emitter = BET12CadenceEmitter(sink=sink)
        for pid in ("agent-A", "agent-B", "agent-C"):
            _run(
                emitter.emit(
                    principal_id=pid,
                    from_level=PostureLevel.PSEUDO,
                    to_level=PostureLevel.TOOL,
                    days_at_current_posture=0.0,
                    authored_count_at_transition=0,
                )
            )
        hashes = {w.principal_id_hash for w in sink.writes}
        assert len(hashes) == 3, "distinct principal_ids must yield distinct hashes"


# ---------------------------------------------------------------------------
# Privacy contract — Rule 3 (no schema-revealing fields)
# ---------------------------------------------------------------------------


class TestPrivacyContract:
    def test_payload_fields_are_only_cohort_safe(self):
        # Defense-in-depth: payload's __dataclass_fields__ MUST be exactly
        # the cohort-safe set per `rules/event-payload-classification.md`
        # Rule 3. Adding e.g. `envelope_hash` or `authored_constraints_names`
        # would silently widen the leakage surface; this test fails loudly.
        expected = {
            "bet_id",
            "principal_id_hash",
            "from_level",
            "to_level",
            "days_at_current_posture",
            "authored_count_at_transition",
        }
        actual = set(BET12CadencePayload.__dataclass_fields__.keys())
        assert actual == expected, (
            f"payload schema drift: expected {expected}, got {actual}. "
            f"Adding fields requires re-deriving Rule 3 leakage surface."
        )

    def test_emit_signature_only_accepts_cohort_safe_kwargs(self):
        # API-boundary defense: `emit()` MUST NOT accept `envelope_hash`,
        # `authored_constraints`, `field_name`, or any other Rule-3-blocked
        # parameter. Adding such a kwarg would let a caller leak schema
        # content into the cohort emission.
        import inspect

        params = set(inspect.signature(BET12CadenceEmitter.emit).parameters.keys())
        forbidden = {
            "envelope_hash",
            "envelope_id",
            "authored_constraints",
            "field_name",
            "field_names",
            "constraint_name",
        }
        leaked = params & forbidden
        assert not leaked, (
            f"emit() signature exposes Rule-3-blocked kwargs: {leaked}. "
            f"These are schema-revealing and must NEVER be in cohort payloads."
        )


# ---------------------------------------------------------------------------
# Value-range guards
# ---------------------------------------------------------------------------


class TestValueRangeGuards:
    def test_negative_days_rejected(self):
        sink = _FakeSink()
        emitter = BET12CadenceEmitter(sink=sink)
        with pytest.raises(ValueError, match="days_at_current_posture must be non-negative"):
            _run(
                emitter.emit(
                    principal_id="agent-A",
                    from_level=PostureLevel.PSEUDO,
                    to_level=PostureLevel.TOOL,
                    days_at_current_posture=-0.001,
                    authored_count_at_transition=0,
                )
            )
        assert sink.writes == []

    def test_negative_authored_count_rejected(self):
        sink = _FakeSink()
        emitter = BET12CadenceEmitter(sink=sink)
        with pytest.raises(ValueError, match="authored_count_at_transition must be non-negative"):
            _run(
                emitter.emit(
                    principal_id="agent-A",
                    from_level=PostureLevel.PSEUDO,
                    to_level=PostureLevel.TOOL,
                    days_at_current_posture=0.0,
                    authored_count_at_transition=-1,
                )
            )
        assert sink.writes == []

    def test_zero_values_accepted(self):
        # Boundary: 0.0 days + 0 authored at PSEUDO->TOOL (N=0 threshold) is
        # the canonical first-transition shape and MUST emit cleanly.
        sink = _FakeSink()
        emitter = BET12CadenceEmitter(sink=sink)
        _run(
            emitter.emit(
                principal_id="agent-A",
                from_level=PostureLevel.PSEUDO,
                to_level=PostureLevel.TOOL,
                days_at_current_posture=0.0,
                authored_count_at_transition=0,
            )
        )
        assert len(sink.writes) == 1
        assert sink.writes[0].days_at_current_posture == 0.0
        assert sink.writes[0].authored_count_at_transition == 0


# ---------------------------------------------------------------------------
# Posture level pass-through (from / to are PostureLevel enum members)
# ---------------------------------------------------------------------------


class TestPostureLevelPassThrough:
    def test_payload_carries_enum_members(self):
        sink = _FakeSink()
        emitter = BET12CadenceEmitter(sink=sink)
        _run(
            emitter.emit(
                principal_id="agent-A",
                from_level=PostureLevel.SUPERVISED,
                to_level=PostureLevel.DELEGATING,
                days_at_current_posture=14.0,
                authored_count_at_transition=3,
            )
        )
        p = sink.writes[0]
        assert p.from_level is PostureLevel.SUPERVISED
        assert p.to_level is PostureLevel.DELEGATING
        # Wire-form name access works (string serialization at sink layer).
        assert p.from_level.name == "SUPERVISED"
        assert p.to_level.name == "DELEGATING"

    def test_demotion_path_emits(self):
        # Demotions also emit — the spec's "every posture-transition"
        # invariant covers ratchet-down too (annual decay, kill-criterion).
        sink = _FakeSink()
        emitter = BET12CadenceEmitter(sink=sink)
        _run(
            emitter.emit(
                principal_id="agent-A",
                from_level=PostureLevel.DELEGATING,
                to_level=PostureLevel.TOOL,
                days_at_current_posture=30.0,
                authored_count_at_transition=5,
            )
        )
        assert len(sink.writes) == 1
        assert sink.writes[0].from_level is PostureLevel.DELEGATING
        assert sink.writes[0].to_level is PostureLevel.TOOL


# ---------------------------------------------------------------------------
# Sink error propagation (no swallow)
# ---------------------------------------------------------------------------


class TestSinkErrorPropagation:
    def test_sink_runtime_error_propagates(self):
        sink = _FakeSink(raise_on_write=RuntimeError("storage offline"))
        emitter = BET12CadenceEmitter(sink=sink)
        with pytest.raises(RuntimeError, match="storage offline"):
            _run(
                emitter.emit(
                    principal_id="agent-A",
                    from_level=PostureLevel.PSEUDO,
                    to_level=PostureLevel.TOOL,
                    days_at_current_posture=0.0,
                    authored_count_at_transition=0,
                )
            )
        # Sink stayed empty because the write raised before recording.
        assert sink.writes == []
