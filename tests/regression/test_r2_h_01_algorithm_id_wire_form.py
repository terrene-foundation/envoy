"""Regression: R2-H-01 — algorithm_identifier wire-form is the spec's 3-key form.

Source: `04-validate/round-2-implementation-comprehensive.md` § R2-H-01 +
`workspaces/phase-01-mvp/journal/0004-DECISION-r2-h-01-disposition.md` Pattern 3.

Failure mode being guarded: every persisted DelegationRecord / GenesisRecord /
RevocationRecord on the trust-lineage path MUST carry the 3-key `{sig, hash,
shamir}` form per `specs/trust-lineage.md` line 24. Upstream
`kailash.trust.signing.algorithm_id` (post-#604, pre-mint-ISS-31) emits the
1-key scaffold form `{"algorithm": "ed25519+sha256"}`. Without producer-side
translation, every on-disk record carries the wrong wire form and the
Independent Verifier (shard 7) rejects every entry.

Note: `specs/independent-verifier.md` line 35 documents a strict-superset
4-key segment-boundary form (R3-M-02 carry-forward, adds `canonical_json`)
used at Ledger-export segment boundaries only. The 3-key trust-lineage form
verified here is NOT the segment-boundary form — that 4-key form lands via a
separate serializer extension at T-03-50 ledger export.

Defense: the SINGLE bottleneck `TrustStoreAdapter._with_algorithm_id` routes
every record-dict construction through `_to_spec_wire_form` before write,
returning a NEW dict (immutability contract — input is not mutated). This
test asserts the bottleneck behaves as the spec mandates, including the
forward-path safety property (when upstream's value space changes, only the
translator updates — every caller stays unchanged).

Per `rules/refactor-invariants.md`: the test is a permanent regression marker;
deletion / silent skip is BLOCKED per `rules/testing.md` § Test-Skip Triage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from envoy.trust.store import TrustStoreAdapter


@pytest.fixture
def adapter(tmp_path: Path) -> TrustStoreAdapter:
    """Construct an unitialized adapter — no I/O until `await initialize()`.

    The wire-form translator is a pure helper (no async, no SQLite reads) so
    Tier 1 regression coverage exercises it directly without an event loop.
    """
    return TrustStoreAdapter(
        vault_path=tmp_path / "vault.dat",
        principal_id="test-principal-r2-h-01",
    )


# ---------------------------------------------------------------------------
# _to_spec_wire_form — pure translator
# ---------------------------------------------------------------------------


class TestToSpecWireForm:
    """Coverage of `_to_spec_wire_form` — the single bottleneck."""

    def test_canonical_upstream_form_translates_to_3_key_spec_form(
        self, adapter: TrustStoreAdapter
    ) -> None:
        """The post-#604 scaffold's canonical `{"algorithm": "ed25519+sha256"}`
        translates to the spec's 3-key form per `specs/trust-lineage.md` L24."""
        upstream = {"algorithm": "ed25519+sha256"}

        result = adapter._to_spec_wire_form(upstream)

        assert result == {
            "sig": "ed25519",
            "hash": "sha256",
            "shamir": "slip39",
        }

    def test_output_has_exactly_3_keys(self, adapter: TrustStoreAdapter) -> None:
        """Spec-mandated wire form has exactly 3 keys — no more, no less.
        Independent Verifier (shard 7) rejects any record with extra or missing
        keys per `specs/independent-verifier.md` § verification steps."""
        result = adapter._to_spec_wire_form({"algorithm": "ed25519+sha256"})

        assert set(result.keys()) == {
            "sig",
            "hash",
            "shamir",
        }, f"R2-H-01 wire form MUST be exactly 3 keys; got {sorted(result.keys())}"

    def test_shamir_dimension_pinned_to_slip39(self, adapter: TrustStoreAdapter) -> None:
        """Phase 01 Shamir scheme is SLIP-0039 per `specs/shamir-recovery.md` +
        `specs/trust-lineage.md` L24. The shamir dimension MUST always be
        `"slip39"` regardless of upstream's input — there is no Phase 01 path
        that emits any other Shamir scheme on the wire."""
        # Even with empty upstream, slip39 still emits.
        result = adapter._to_spec_wire_form({})
        assert result["shamir"] == "slip39"

    def test_missing_algorithm_key_falls_back_to_canonical_defaults(
        self, adapter: TrustStoreAdapter
    ) -> None:
        """Defensive: missing `algorithm` key MUST emit canonical defaults
        rather than empty strings — empty `sig` / `hash` would produce a record
        that fails verifier hash-step parity per `specs/trust-lineage.md` § Algorithms."""
        result = adapter._to_spec_wire_form({})

        assert result == {
            "sig": "ed25519",
            "hash": "sha256",
            "shamir": "slip39",
        }

    def test_compound_form_splits_on_plus_delimiter(self, adapter: TrustStoreAdapter) -> None:
        """Translator parses upstream's `<sig>+<hash>` compound exactly per
        the kailash-py 2.13.4 algorithm_id.py contract (post-#604 line 105)."""
        result = adapter._to_spec_wire_form({"algorithm": "ed448+sha512"})

        assert result == {
            "sig": "ed448",
            "hash": "sha512",
            "shamir": "slip39",
        }

    def test_translator_does_not_mutate_input(self, adapter: TrustStoreAdapter) -> None:
        """Pure-function discipline: the input dict MUST NOT be mutated.
        Aliasing the upstream dict into the output would be a contract leak."""
        upstream = {"algorithm": "ed25519+sha256"}
        before = dict(upstream)

        result = adapter._to_spec_wire_form(upstream)

        assert upstream == before
        assert result is not upstream


# ---------------------------------------------------------------------------
# _with_algorithm_id — the single bottleneck routed by every record-construction path
# ---------------------------------------------------------------------------


class TestWithAlgorithmId:
    """Coverage of `_with_algorithm_id` — every record-construction call site
    MUST route through this helper before write."""

    def test_embeds_canonical_3_key_form_on_empty_record(self, adapter: TrustStoreAdapter) -> None:
        """Empty record dict: helper injects exactly the canonical 3-key
        `algorithm_identifier` field, nothing else. Verifies the helper does
        not silently inject other fields."""
        record: dict = {}

        result = adapter._with_algorithm_id(record)

        assert result == {
            "algorithm_identifier": {
                "sig": "ed25519",
                "hash": "sha256",
                "shamir": "slip39",
            },
        }

    def test_preserves_existing_record_fields(self, adapter: TrustStoreAdapter) -> None:
        """Helper MUST NOT discard caller-provided fields (delegation_id,
        signature_by_delegator_hex, etc. — the record dict carries the
        full record before write)."""
        record = {
            "type": "DelegationRecord",
            "delegation_id": "sha256:abc123",
            "nonce": "deadbeef",
        }

        result = adapter._with_algorithm_id(record)

        assert result["type"] == "DelegationRecord"
        assert result["delegation_id"] == "sha256:abc123"
        assert result["nonce"] == "deadbeef"

    def test_helper_does_not_mutate_caller_record(self, adapter: TrustStoreAdapter) -> None:
        """Immutability contract — input dict MUST NOT be mutated. A Ledger
        producer that constructs a record dict and reuses it for both audit
        log + persistence relies on this so the algorithm_identifier doesn't
        bleed across record contexts. Mirrors `_to_spec_wire_form`'s purity
        contract at the wrapper layer."""
        before = {"type": "DelegationRecord", "delegation_id": "sha256:abc123"}
        snapshot = dict(before)

        result = adapter._with_algorithm_id(before)

        assert before == snapshot, (
            "_with_algorithm_id mutated caller's input dict; "
            "Ledger producer's audit-log surface would carry leaked algorithm_identifier"
        )
        assert result is not before
        assert "algorithm_identifier" not in before

    def test_overwrites_pre_existing_algorithm_identifier(self, adapter: TrustStoreAdapter) -> None:
        """Helper is the SINGLE point of truth — even if a caller pre-populates
        `algorithm_identifier`, the helper MUST overwrite with the canonical
        form per `rules/zero-tolerance.md` Rule 4 (BLOCK hardcoded `Ed25519`
        strings drifting in from legacy code paths)."""
        record = {"algorithm_identifier": {"algorithm": "Ed25519"}}

        result = adapter._with_algorithm_id(record)

        assert result["algorithm_identifier"] == {
            "sig": "ed25519",
            "hash": "sha256",
            "shamir": "slip39",
        }

    def test_idempotent_under_repeat_invocation(self, adapter: TrustStoreAdapter) -> None:
        """Helper is idempotent: applying it twice yields the same record.
        Defends against re-entry from upper layers (e.g. retry on transient
        SQLite locking) producing different wire shapes on retry."""
        record = {"type": "DelegationRecord"}

        once = adapter._with_algorithm_id(dict(record))
        twice = adapter._with_algorithm_id(dict(once))

        assert once == twice


# ---------------------------------------------------------------------------
# Producer/verifier round-trip — wire-shape parity
# ---------------------------------------------------------------------------


class TestProducerVerifierRoundTrip:
    """The 3-key form on disk is the contract between producer (this adapter)
    and consumer (Independent Verifier, shard 7). The round-trip property is
    that what the producer writes matches exactly what the verifier expects."""

    # Spec-mandated form per specs/trust-lineage.md L24 (3-key trust-lineage on-wire form).
    # specs/independent-verifier.md L35 documents a strict-superset 4-key segment-boundary
    # form (R3-M-02 carry-forward); that form is wired by a separate serializer extension
    # at T-03-50 ledger export, NOT by this helper.
    SPEC_WIRE_FORM = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}

    def test_producer_emits_exact_spec_wire_form(self, adapter: TrustStoreAdapter) -> None:
        """Independent Verifier (shard 7) checks `algorithm_identifier == X`;
        producer MUST emit byte-identical-when-canonicalized `X`."""
        record = adapter._with_algorithm_id({})

        assert record["algorithm_identifier"] == self.SPEC_WIRE_FORM

    def test_verifier_form_is_dict_not_string(self, adapter: TrustStoreAdapter) -> None:
        """Per `specs/trust-lineage.md` L24 the `algorithm_identifier` is a
        JSON object, not a string. Catches a regression where a refactor
        flattens the field to `"ed25519+sha256"` (upstream's compound form)."""
        record = adapter._with_algorithm_id({})

        assert isinstance(record["algorithm_identifier"], dict)
        assert not isinstance(record["algorithm_identifier"], str)

    def test_no_legacy_algorithm_key_leaks_through(self, adapter: TrustStoreAdapter) -> None:
        """Upstream's 1-key `algorithm` field MUST NOT appear on the wire.
        The verifier expects the 3-key form; an extra `algorithm` key indicates
        producer-side leakage of the upstream scaffold."""
        record = adapter._with_algorithm_id({})

        assert "algorithm" not in record["algorithm_identifier"]
