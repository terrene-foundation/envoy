# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 — the pure structural envelope-check engine (WS-6 S6a structural slice).

Direct-call coverage of `envoy.runtime.envelope_check`: the partition predicate
`is_semantic_action`, the six N3 structural-reject classes, the N1 knowledge-filter
gate (allow / deny / partial), the N2 5-property cache-key invalidation, and the N5
posture-ceiling floor. The cross-runtime byte-identity of these verdicts is proven
at Tier 2 by tests/conformance/test_n1_n3.py + test_n4_n6.py (both adapters delegate
here); this module pins the engine's contract in isolation, fast + offline.
"""

from __future__ import annotations

from envoy.runtime.envelope_check import (
    VERDICT_SCHEMA,
    envelope_check_structural,
    is_semantic_action,
)

_WELL_FORMED = {"schema": "envelope/1.0", "field_allowlist_per_model": {"User": ["name", "email"]}}


class TestSemanticPartition:
    def test_action_with_content_bytes_is_semantic(self) -> None:
        assert is_semantic_action({"model": "Doc", "content": b"payload"}) is True

    def test_action_without_content_is_structural(self) -> None:
        assert is_semantic_action({"model": "User", "requested_fields": ["name"]}) is False

    def test_non_dict_action_is_structural(self) -> None:
        assert is_semantic_action(None) is False
        assert is_semantic_action(object()) is False

    def test_content_must_be_bytes_not_str(self) -> None:
        # A str `content` is not the classify-this-payload semantic signal.
        assert is_semantic_action({"content": "not-bytes"}) is False


class TestStructuralRejects:
    def _reason(self, envelope: object, action: object) -> object:
        verdict = envelope_check_structural(envelope, action)
        assert verdict["outcome"] == "structural_reject"
        assert verdict["verdict_class"] == "structural"
        return verdict["reject_reason"]

    def test_missing_schema(self) -> None:
        assert self._reason({"envelope_version": 3}, {"model": "User"}) == "missing_schema"

    def test_malformed_schema(self) -> None:
        assert self._reason({"schema": "envelope/0.0-INVALID"}, {"model": "User"}) == "malformed_schema"

    def test_type_mismatch_version(self) -> None:
        assert self._reason(
            {"schema": "envelope/1.0", "envelope_version": "three"}, {"model": "User"}
        ) == "type_mismatch"

    def test_allowlist_shape(self) -> None:
        assert self._reason(
            {"schema": "envelope/1.0", "field_allowlist_per_model": ["name"]}, {"model": "User"}
        ) == "allowlist_shape"

    def test_dimension_out_of_range(self) -> None:
        assert self._reason(
            {"schema": "envelope/1.0", "dims": {"max_depth": 999}}, {"model": "User"}
        ) == "dimension_out_of_range"

    def test_unknown_action_verb(self) -> None:
        assert self._reason(
            {"schema": "envelope/1.0"}, {"model": "User", "verb": "TELEPORT"}
        ) == "unknown_action_verb"

    def test_non_dict_envelope(self) -> None:
        assert self._reason(None, None) == "malformed_envelope"

    def test_content_wrong_type_fails_closed(self) -> None:
        # Security MED-1: a `content` key that is NOT bytes (the adapters route
        # bytes-content to the S6c classifier gate) must fail closed in the
        # structural engine, NOT receive a free structural allow.
        assert self._reason(
            {"schema": "envelope/1.0"}, {"model": "User", "content": "text-not-bytes"}
        ) == "content_type_mismatch"
        assert self._reason(
            {"schema": "envelope/1.0"}, {"model": "User", "content": {"nested": "obj"}}
        ) == "content_type_mismatch"


class TestKnowledgeFilterGate:
    def test_all_allowed(self) -> None:
        v = envelope_check_structural(_WELL_FORMED, {"model": "User", "requested_fields": ["name"]})
        assert v["outcome"] == "allow"
        assert v["allowed_fields"] == ["name"] and v["denied_fields"] == []

    def test_all_denied(self) -> None:
        v = envelope_check_structural(_WELL_FORMED, {"model": "User", "requested_fields": ["ssn"]})
        assert v["outcome"] == "deny"
        assert v["allowed_fields"] == [] and v["denied_fields"] == ["ssn"]

    def test_partial_deny_sorted(self) -> None:
        v = envelope_check_structural(
            _WELL_FORMED, {"model": "User", "requested_fields": ["ssn", "name", "email"]}
        )
        assert v["outcome"] == "partial_deny"
        # field lists are sorted → deterministic byte-identical verdict
        assert v["allowed_fields"] == ["email", "name"] and v["denied_fields"] == ["ssn"]

    def test_model_absent_denies_all(self) -> None:
        v = envelope_check_structural(_WELL_FORMED, {"model": "Other", "requested_fields": ["name"]})
        assert v["outcome"] == "deny"

    def test_empty_request_allows_vacuously(self) -> None:
        v = envelope_check_structural(_WELL_FORMED, {"model": "User", "requested_fields": []})
        assert v["outcome"] == "allow"
        assert v["schema"] == VERDICT_SCHEMA


class TestCacheKeyInvalidation:
    def _base(self) -> dict[str, object]:
        return {
            "schema": "envelope/1.0",
            "envelope_version": 3,
            "algorithm_identifier": {"sig": "ed25519"},
            "classifier_ensemble_versions": {"clf-a": "1.0.0"},
            "posture_level": "SUPERVISED",
            "principal_genesis_id": "genesis:root",
        }

    def test_each_property_change_flips_cache_key(self) -> None:
        action = {"model": "User", "requested_fields": ["name"]}
        base_key = envelope_check_structural(self._base(), action)["cache_key"]
        for prop, mutated in [
            ("envelope_version", 4),
            ("algorithm_identifier", {"sig": "ed448"}),
            ("classifier_ensemble_versions", {"clf-a": "1.0.1"}),
            ("posture_level", "AUTONOMOUS"),
            ("principal_genesis_id", "genesis:other"),
        ]:
            env = self._base()
            env[prop] = mutated
            key = envelope_check_structural(env, action)["cache_key"]
            assert key != base_key, f"changing {prop} did not invalidate the cache key"

    def test_unrelated_change_does_not_flip_cache_key(self) -> None:
        action = {"model": "User", "requested_fields": ["name"]}
        base_key = envelope_check_structural(self._base(), action)["cache_key"]
        env = self._base()
        env["unrelated_field"] = "noise"
        assert envelope_check_structural(env, action)["cache_key"] == base_key


class TestPostureCeiling:
    def _eff(self, declared: str, principal: str) -> object:
        envelope = {"schema": "envelope/1.0", "metadata": {"posture_level": declared}}
        action = {"principal_posture": principal, "kind": "check"}
        return envelope_check_structural(envelope, action)["effective_posture"]

    def test_envelope_binds_more_restrictive(self) -> None:
        assert self._eff("SUPERVISED", "AUTONOMOUS") == "SUPERVISED"

    def test_principal_binds_more_restrictive(self) -> None:
        assert self._eff("AUTONOMOUS", "OBSERVED") == "OBSERVED"

    def test_equal_postures_identity(self) -> None:
        assert self._eff("TRUSTED", "TRUSTED") == "TRUSTED"

    def test_absent_postures_yield_none(self) -> None:
        v = envelope_check_structural(_WELL_FORMED, {"model": "User", "requested_fields": ["name"]})
        assert v["effective_posture"] is None

    def test_off_ladder_posture_yields_none(self) -> None:
        # N2's top-level posture vocabulary (RESTRICTED/PUBLIC) is NOT the N5
        # ceiling ladder — an off-ladder value cannot floor, so effective is None.
        assert self._eff("RESTRICTED", "PUBLIC") is None
