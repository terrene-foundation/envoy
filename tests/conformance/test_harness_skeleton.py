# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""tests/conformance/test_harness_skeleton.py — S1 skeleton unit tests.

Tier 1 (offline, deterministic, <1s). Proves the conformance-harness SKELETON
delivered by Phase-02 S1
(`workspaces/phase-02-distribution/todos/active/01-m1-ws1-runtime-pluggability.md`
§ S1) before any vector corpus exists:

1. Contract-tier metadata: every Protocol method carries a tier; an untagged
   method fails `assert_all_methods_tagged` loudly (acceptance criterion 1).
2. Per-field tier schema: a `ConformanceVector` can carry mixed-tier
   `field_tiers` so N3/N4 are expressible (acceptance criterion 2).
3. Harness parametrizes over `get_runtime(family=...)` — the single seam — and
   emits IDs of the form ``<runtime>-<vector_id>`` (acceptance criterion 3).
4. Byte-identity scorer asserts hash-equality AND produces a field-localized
   diff on mismatch (the scorer is NOT a bare ``assert a == b``).
5. Dispatch-observation hook records structural→no-dispatch and
   semantic→dispatch deterministically (acceptance criterion 4).
"""

from __future__ import annotations

import pytest

from envoy.runtime import get_runtime
from envoy.runtime.conformance import (
    ConformanceVector,
    FieldTier,
    canonical_hash,
    score_byte_identity,
)
from envoy.runtime.contract_tier import (
    ContractTier,
    MissingContractTierError,
    assert_all_methods_tagged,
    byte_identical,
    semantically_equivalent,
    tier_of,
)
from envoy.runtime.dispatch_observation import observe, record_dispatch
from envoy.runtime.errors import RsBindingsNotAvailableInPhase01Error
from envoy.runtime.protocol import KailashRuntime
from tests.conformance import harness

# ---------------------------------------------------------------------------
# 1. Contract-tier metadata — every method tagged; untagged fails loudly.
# ---------------------------------------------------------------------------


def test_every_protocol_method_carries_a_contract_tier() -> None:
    tiers = assert_all_methods_tagged(KailashRuntime)
    # 31 methods on the Protocol; all tagged.
    assert len(tiers) == 31
    assert all(isinstance(t, ContractTier) for t in tiers.values())


def test_contract_partition_matches_spec_bet6() -> None:
    tiers = assert_all_methods_tagged(KailashRuntime)
    # The ONLY two semantic-slice methods per specs/runtime-abstraction.md
    # § Contract partition: classifier_invoke (LLM verdict) and
    # grant_moment_surface (rendered verdict text, the N4 Phase-03 slice).
    semantic = {name for name, t in tiers.items() if t is ContractTier.SEMANTICALLY_EQUIVALENT}
    assert semantic == {"classifier_invoke", "grant_moment_surface"}
    # The crypto/canonical/ledger surface is byte-identical.
    assert tiers["envelope_canonical_form"] is ContractTier.BYTE_IDENTICAL
    assert tiers["trust_sign"] is ContractTier.BYTE_IDENTICAL
    assert tiers["head_commitment"] is ContractTier.BYTE_IDENTICAL
    assert tiers["trust_cascade_revoke"] is ContractTier.BYTE_IDENTICAL


def test_untagged_method_fails_authoring_assertion() -> None:
    class _NoTier:
        def some_method(self) -> None: ...  # no decorator

    with pytest.raises(MissingContractTierError, match="some_method"):
        assert_all_methods_tagged(_NoTier)


def test_tier_decorators_stamp_and_read_back() -> None:
    @byte_identical
    def bi() -> None: ...

    @semantically_equivalent
    def se() -> None: ...

    def bare() -> None: ...

    assert tier_of(bi) is ContractTier.BYTE_IDENTICAL
    assert tier_of(se) is ContractTier.SEMANTICALLY_EQUIVALENT
    with pytest.raises(MissingContractTierError, match="bare"):
        tier_of(bare)


# ---------------------------------------------------------------------------
# 2. Per-field tier schema — N3/N4 mixed-tier expressible (Spec-gap-3).
# ---------------------------------------------------------------------------


def test_vector_carries_mixed_field_tiers() -> None:
    vector = ConformanceVector(
        family="N4",
        vector_id="N4-001",
        method="grant_moment_surface",
        inputs={"request": {"verdict": "ALLOW"}},
        field_tiers={
            "verdict.structured": FieldTier.BYTE_IDENTICAL,
            "verdict.rendered_text": FieldTier.SEMANTICALLY_EQUIVALENT,
        },
    )
    assert vector.field_tiers["verdict.structured"] is ContractTier.BYTE_IDENTICAL
    assert vector.field_tiers["verdict.rendered_text"] is ContractTier.SEMANTICALLY_EQUIVALENT
    assert vector.test_id == "N4-001"


def test_vector_rejects_empty_identity_fields() -> None:
    with pytest.raises(ValueError):
        ConformanceVector(family="", vector_id="x", method="m")
    with pytest.raises(ValueError):
        ConformanceVector(family="N1", vector_id="", method="m")
    with pytest.raises(ValueError):
        ConformanceVector(family="N1", vector_id="N1-001", method="")


# ---------------------------------------------------------------------------
# 3. Harness parametrizes over the single get_runtime() seam.
# ---------------------------------------------------------------------------


def test_harness_resolves_runtime_through_get_runtime_seam() -> None:
    # The reference family always resolves to the same object get_runtime() gives.
    resolved = harness.resolve_runtime("kailash-py")
    assert resolved is not None
    assert type(resolved).__name__ == type(get_runtime(family="kailash-py")).__name__


def test_harness_rs_lane_constructs_adapter_without_flipping_production_flag() -> None:
    # S3a wired the test-only rs seam: resolve_runtime("kailash-rs-bindings")
    # now constructs the rs adapter DIRECTLY (bypassing the production
    # get_runtime flag-gate) so the conformance harness can exercise the rs
    # adapter's wired methods cross-runtime. Crucially, the seam does NOT flip
    # the PRODUCTION feature flag — production gating stays False; the harness
    # is the gate that must pass before that flip.
    from envoy.runtime.adapters.kailash_rs_bindings import KailashRsBindingsRuntime
    from envoy.runtime.feature_flags import RS_BINDINGS_ENABLED

    rs = harness.resolve_runtime("kailash-rs-bindings")
    assert isinstance(rs, KailashRsBindingsRuntime)
    # The production flag is untouched by the test-only seam.
    assert RS_BINDINGS_ENABLED is False
    # And the production selection seam still refuses the rs family.
    with pytest.raises(RsBindingsNotAvailableInPhase01Error):
        get_runtime(family="kailash-rs-bindings")


def test_parametrize_emits_runtime_prefixed_ids() -> None:
    vectors = [
        ConformanceVector(family="N2", vector_id="N2-007", method="head_commitment"),
    ]
    marker = harness.parametrize_runtime_x_vectors(vectors)
    # The parametrize args carry IDs of the form "<runtime>-<vector_id>" and
    # exclude the reference family from the runtime-under-test axis.
    ids = [p.id for p in marker.args[1]]
    assert ids == ["kailash-rs-bindings-N2-007"]


def test_load_vectors_is_empty_skeleton() -> None:
    # S1 ships the skeleton with no corpus; the families author vectors later.
    assert list(harness.load_vectors()) == []


# ---------------------------------------------------------------------------
# 4. Byte-identity scorer — hash-equality + field-localized diff.
# ---------------------------------------------------------------------------


def test_scorer_passes_on_identical_output() -> None:
    left = {"entry_id": "abc", "seq": 3, "ts": "2026-06-09T00:00:00.000000Z"}
    right = {"seq": 3, "entry_id": "abc", "ts": "2026-06-09T00:00:00.000000Z"}
    result = score_byte_identity(left, right)
    assert result.passed
    assert result.left_hash == result.right_hash
    assert result.mismatch is None
    # canonical_hash is order-insensitive on dict keys.
    assert canonical_hash(left) == canonical_hash(right)


def test_scorer_localizes_field_on_mismatch() -> None:
    left = {"entries": [{"ts": "2026-06-09T00:00:00.000000Z"}]}
    right = {"entries": [{"ts": "2026-06-09T00:00:00Z"}]}  # truncated microseconds
    result = score_byte_identity(left, right)
    assert not result.passed
    assert result.left_hash != result.right_hash
    assert result.mismatch is not None
    # The diff names the exact field, NOT a bare a==b failure.
    assert result.mismatch.json_path == "entries[0].ts"
    assert result.mismatch.byte_offset >= 0


def test_scorer_bytes_pass_through_and_hash() -> None:
    # E1-style: runtimes return already-canonical bytes; scorer hashes directly.
    assert score_byte_identity(b"canonical-form-bytes", b"canonical-form-bytes").passed
    assert not score_byte_identity(b"left", b"right").passed


def test_scorer_set_equality_is_order_insensitive() -> None:
    # E3 cascade-revoke: SET equality, ordering may differ (BFS vs DFS).
    assert score_byte_identity({"a", "b", "c"}, {"c", "b", "a"}).passed
    assert not score_byte_identity({"a", "b"}, {"a", "b", "c"}).passed


# ---------------------------------------------------------------------------
# 5. Dispatch-observation hook — structural→no-dispatch, semantic→dispatch.
# ---------------------------------------------------------------------------


def test_structural_check_records_no_dispatch() -> None:
    with observe() as handle:
        # A structural-class check never invokes the classifier ensemble.
        pass
    obs = handle.result()
    assert obs.dispatched is False
    assert obs.dispatch_count == 0
    assert obs.refs == ()


def test_semantic_check_records_dispatch() -> None:
    with observe() as handle:
        # A semantic-class check dispatches the classifier ensemble.
        record_dispatch("classifier://ensemble/toxicity")
    obs = handle.result()
    assert obs.dispatched is True
    assert obs.dispatch_count == 1
    assert obs.refs == ("classifier://ensemble/toxicity",)


def test_dispatch_outside_context_is_noop() -> None:
    # The production hot path dispatches without the harness watching; no error.
    record_dispatch("classifier://ensemble/whatever")  # no active context
    with observe() as handle:
        pass
    assert handle.result().dispatch_count == 0


def test_nested_observations_do_not_cross_contaminate() -> None:
    with observe() as outer:
        record_dispatch("outer-ref")
        with observe() as inner:
            record_dispatch("inner-ref-1")
            record_dispatch("inner-ref-2")
        assert inner.result().dispatch_count == 2
        assert inner.result().refs == ("inner-ref-1", "inner-ref-2")
    # The outer context only saw its own dispatch, not the inner ones.
    assert outer.result().dispatch_count == 1
    assert outer.result().refs == ("outer-ref",)
