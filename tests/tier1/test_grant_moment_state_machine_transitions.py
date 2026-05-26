"""Tier 1 unit tests for envoy.grant_moment state machine + signed consent.

Per `rules/testing.md` § Tier 1: mocking allowed; <1s per test. Pure-function
+ pure-dataclass surface — no infrastructure dependency. The KeyManager is a
real ``kailash.trust.key_manager.InMemoryKeyManager`` per `rules/testing.md`
§ "No mocking against real upstream primitives".

Covers `specs/grant-moment.md` invariants for T-03-50:
- M0→M4 transition table (the 5 allowed pairs).
- Forbidden transitions raise InvalidGrantMomentTransitionError.
- JCS+NFC canonicalization round-trips byte-identically.
- Signed Request reproducible: same key + same payload → same signature.
- Signed Result discriminators: 4 spec decisions from 3 ResolutionShapes.
- Deny path emits unsigned Result with sentinel marker (signed only via Ledger).
- 10-error taxonomy carries spec-promised structured attributes.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from kailash.trust.key_manager import InMemoryKeyManager

from envoy.envelope.canonical_bytes import canonical_bytes
from envoy.grant_moment.errors import (
    BackPressureQueueFullError,
    CrossChannelConfirmFailedError,
    DualSignatureRequiredError,
    GrantMomentError,
    GrantMomentExpiredError,
    GrantMomentReplayError,
    GrantMomentTimeoutError,
    InvalidGrantMomentTransitionError,
    NotPrimaryChannelError,
    NoveltyFrictionRequiredError,
    VelocityRaiseCoolingOffError,
    VisibleSecretMismatchError,
)
from envoy.grant_moment.resolution import (
    ApproveResolution,
    ApproveWithModificationResolution,
    DeclineResolution,
)
from envoy.grant_moment.signed_consent import (
    ConsequencePreview,
    GrantMomentRequest,
    SignedConsentBuilder,
)
from envoy.grant_moment.state_machine import (
    GRANT_MOMENT_TRANSITIONS,
    GrantMomentEvent,
    GrantMomentState,
    next_state,
)


# ---------------------------------------------------------------------------
# State machine transitions
# ---------------------------------------------------------------------------


class TestGrantMomentTransitions:
    """The M0→M4 spine + the M2 dual-entry (decision OR timeout) into M3."""

    def test_m0_to_m1_on_dispatch_to_channels(self) -> None:
        assert (
            next_state(GrantMomentState.M0_CONSTRUCT, GrantMomentEvent.DISPATCH_TO_CHANNELS)
            == GrantMomentState.M1_RENDER
        )

    def test_m1_to_m2_on_rendered_and_awaiting(self) -> None:
        assert (
            next_state(GrantMomentState.M1_RENDER, GrantMomentEvent.RENDERED_AND_AWAITING)
            == GrantMomentState.M2_AWAIT
        )

    def test_m2_to_m3_on_decision_received(self) -> None:
        assert (
            next_state(GrantMomentState.M2_AWAIT, GrantMomentEvent.DECISION_RECEIVED)
            == GrantMomentState.M3_SIGN
        )

    def test_m2_to_m3_on_timeout_expired(self) -> None:
        # Spec § State machine: M2 default 5min; expiry routes to M3 with
        # auto-deny disposition. The state machine itself takes both paths
        # into M3 — the runtime decides the disposition.
        assert (
            next_state(GrantMomentState.M2_AWAIT, GrantMomentEvent.TIMEOUT_EXPIRED)
            == GrantMomentState.M3_SIGN
        )

    def test_m3_to_m4_on_signature_finalized(self) -> None:
        assert (
            next_state(GrantMomentState.M3_SIGN, GrantMomentEvent.SIGNATURE_FINALIZED)
            == GrantMomentState.M4_COMPLETE
        )

    def test_transition_table_is_exactly_five_entries(self) -> None:
        # Strict-table design: any new transition requires an explicit entry,
        # not a fallthrough. Five entries = M0→M1, M1→M2, M2→M3 (×2), M3→M4.
        assert len(GRANT_MOMENT_TRANSITIONS) == 5


class TestGrantMomentForbiddenTransitions:
    """The state machine is strict — bypass paths raise."""

    def test_m0_skip_to_m3_raises(self) -> None:
        with pytest.raises(InvalidGrantMomentTransitionError) as exc:
            next_state(GrantMomentState.M0_CONSTRUCT, GrantMomentEvent.DECISION_RECEIVED)
        assert exc.value.current_state == "M0_construct"
        assert exc.value.attempted_event == "decision_received"

    def test_m4_complete_to_anything_raises(self) -> None:
        # M4 is terminal — no event re-opens a completed Grant Moment.
        for event in GrantMomentEvent:
            with pytest.raises(InvalidGrantMomentTransitionError):
                next_state(GrantMomentState.M4_COMPLETE, event)

    def test_m2_signature_finalized_raises(self) -> None:
        # SIGNATURE_FINALIZED arrives only after M3 signs; M2 hasn't signed.
        with pytest.raises(InvalidGrantMomentTransitionError):
            next_state(GrantMomentState.M2_AWAIT, GrantMomentEvent.SIGNATURE_FINALIZED)


# ---------------------------------------------------------------------------
# Resolution shapes — three classes, four spec decisions
# ---------------------------------------------------------------------------


class TestResolutionShapes:
    """ApproveResolution + DeclineResolution + ApproveWithModificationResolution
    map to the four spec `decision` discriminator values."""

    def test_approve_without_author_payload_is_approve_once(self) -> None:
        res = ApproveResolution(decided_by_principal_genesis_id="sha256:abc")
        assert res.to_decision() == "approve_once"

    def test_approve_with_author_payload_is_approve_and_author(self) -> None:
        res = ApproveResolution(
            decided_by_principal_genesis_id="sha256:abc",
            author_payload={
                "new_constraint": {"name": "spend_cap"},
                "novelty_check_passed": True,
                "minimum_impact_passed": True,
            },
        )
        assert res.to_decision() == "approve_and_author"

    def test_decline_is_deny(self) -> None:
        res = DeclineResolution(
            decided_by_principal_genesis_id="sha256:abc",
            reason="not now",
        )
        assert res.to_decision() == "deny"

    def test_modify_is_modify(self) -> None:
        res = ApproveWithModificationResolution(
            decided_by_principal_genesis_id="sha256:abc",
            modify_payload={
                "new_args_canonical": {"amount_microdollars": 5_000_000},
                "new_args_canonical_hash": "sha256:xyz",
            },
        )
        assert res.to_decision() == "modify"


# ---------------------------------------------------------------------------
# Signed-consent builder — real InMemoryKeyManager, no mocks
# ---------------------------------------------------------------------------


@pytest.fixture
def real_key_manager() -> tuple[InMemoryKeyManager, str]:
    """A real kailash-py InMemoryKeyManager with one Ed25519 keypair pre-seeded."""
    km = InMemoryKeyManager()
    # kailash 2.13.4 InMemoryKeyManager.generate_keypair is async and returns
    # (public_key_b64, signing_key_b64). We register one delegation key for the
    # suite under the id "delegation-key-test"; subsequent sign_with_key calls
    # use that id.
    public_key_b64, _signing_key_b64 = asyncio.run(km.generate_keypair("delegation-key-test"))
    assert isinstance(public_key_b64, str) and len(public_key_b64) > 0
    return km, "delegation-key-test"


@pytest.fixture
def sample_request_unsigned() -> GrantMomentRequest:
    return GrantMomentRequest(
        request_id="01HXYZ-request",
        session_id="01HXYZ-session",
        principal_genesis_id="sha256:principal",
        envelope_id="01HXYZ-envelope",
        envelope_version=1,
        envelope_hash="sha256:envhash",
        intent_id="sha256:intenthash",
        nonce="abcd1234",
        tool_name="send_message",
        tool_args_canonical={"to": "alice", "body": "hi"},
        tool_args_canonical_hash="sha256:argshash",
        why_asking="first_time",
        consequence_preview=ConsequencePreview(
            budget_microdollars=1_000_000,
            reversibility="reversible",
            recipient="alice",
            data_classification="Public",
        ),
        novelty_class="novel",
        primary_only=False,
        timeout_seconds=300,
        issued_at="2026-05-26T10:00:00Z",
        delegation_key_pubkey_hex="abcd",
        # signature_by_delegator_hex left at default ""
    )


class TestSignedConsentBuilderRequest:
    """SignedConsentBuilder.build_signed_request produces deterministic signatures."""

    def test_request_signature_is_populated_and_nonempty(
        self,
        real_key_manager: tuple[InMemoryKeyManager, str],
        sample_request_unsigned: GrantMomentRequest,
    ) -> None:
        km, key_id = real_key_manager
        builder = SignedConsentBuilder(key_manager=km)
        signed = builder.build_signed_request(
            request=sample_request_unsigned, delegation_key_id=key_id
        )
        assert signed.signature_by_delegator_hex != ""
        # Original request is frozen → builder returned a fresh instance.
        assert sample_request_unsigned.signature_by_delegator_hex == ""

    def test_same_request_signs_to_same_signature(
        self,
        real_key_manager: tuple[InMemoryKeyManager, str],
        sample_request_unsigned: GrantMomentRequest,
    ) -> None:
        km, key_id = real_key_manager
        builder = SignedConsentBuilder(key_manager=km)
        first = builder.build_signed_request(
            request=sample_request_unsigned, delegation_key_id=key_id
        )
        second = builder.build_signed_request(
            request=sample_request_unsigned, delegation_key_id=key_id
        )
        # Ed25519 is deterministic per RFC 8032 — same key + same bytes = same sig.
        assert first.signature_by_delegator_hex == second.signature_by_delegator_hex

    def test_request_canonical_hash_is_signature_independent(
        self,
        real_key_manager: tuple[InMemoryKeyManager, str],
        sample_request_unsigned: GrantMomentRequest,
    ) -> None:
        km, key_id = real_key_manager
        builder = SignedConsentBuilder(key_manager=km)
        signed = builder.build_signed_request(
            request=sample_request_unsigned, delegation_key_id=key_id
        )
        # Canonical hash MUST match between signed and unsigned (signature field
        # is forced to "" before hashing per spec § Canonical JSON).
        assert SignedConsentBuilder.request_canonical_hash(
            sample_request_unsigned
        ) == SignedConsentBuilder.request_canonical_hash(signed)

    def test_unknown_delegation_key_raises(
        self,
        real_key_manager: tuple[InMemoryKeyManager, str],
        sample_request_unsigned: GrantMomentRequest,
    ) -> None:
        km, _ = real_key_manager
        builder = SignedConsentBuilder(key_manager=km)
        with pytest.raises(ValueError, match="not in key_manager"):
            builder.build_signed_request(
                request=sample_request_unsigned, delegation_key_id="missing"
            )

    def test_canonical_input_is_jcs_nfc_normalized(
        self,
        sample_request_unsigned: GrantMomentRequest,
    ) -> None:
        # NFC normalization: composed vs decomposed string in tool_name MUST
        # produce identical canonical bytes — guards macOS HFS+ NFD storage.
        # Construct NFD form programmatically so the test does not depend on
        # source-file encoding (editors normalize to NFC by default).
        import unicodedata

        nfc_tool_name = unicodedata.normalize("NFC", "send_message_café")
        nfd_tool_name = unicodedata.normalize("NFD", nfc_tool_name)
        nfc_req = GrantMomentRequest(
            request_id=sample_request_unsigned.request_id,
            session_id=sample_request_unsigned.session_id,
            principal_genesis_id=sample_request_unsigned.principal_genesis_id,
            envelope_id=sample_request_unsigned.envelope_id,
            envelope_version=sample_request_unsigned.envelope_version,
            envelope_hash=sample_request_unsigned.envelope_hash,
            intent_id=sample_request_unsigned.intent_id,
            nonce=sample_request_unsigned.nonce,
            tool_name=nfc_tool_name,  # NFC (composed)
            tool_args_canonical=sample_request_unsigned.tool_args_canonical,
            tool_args_canonical_hash=sample_request_unsigned.tool_args_canonical_hash,
            why_asking=sample_request_unsigned.why_asking,
            consequence_preview=sample_request_unsigned.consequence_preview,
            novelty_class=sample_request_unsigned.novelty_class,
            primary_only=sample_request_unsigned.primary_only,
            timeout_seconds=sample_request_unsigned.timeout_seconds,
            issued_at=sample_request_unsigned.issued_at,
            delegation_key_pubkey_hex=sample_request_unsigned.delegation_key_pubkey_hex,
        )
        nfd_req = GrantMomentRequest(
            request_id=nfc_req.request_id,
            session_id=nfc_req.session_id,
            principal_genesis_id=nfc_req.principal_genesis_id,
            envelope_id=nfc_req.envelope_id,
            envelope_version=nfc_req.envelope_version,
            envelope_hash=nfc_req.envelope_hash,
            intent_id=nfc_req.intent_id,
            nonce=nfc_req.nonce,
            tool_name=nfd_tool_name,  # NFD (decomposed)
            tool_args_canonical=nfc_req.tool_args_canonical,
            tool_args_canonical_hash=nfc_req.tool_args_canonical_hash,
            why_asking=nfc_req.why_asking,
            consequence_preview=nfc_req.consequence_preview,
            novelty_class=nfc_req.novelty_class,
            primary_only=nfc_req.primary_only,
            timeout_seconds=nfc_req.timeout_seconds,
            issued_at=nfc_req.issued_at,
            delegation_key_pubkey_hex=nfc_req.delegation_key_pubkey_hex,
        )
        # Verify they really are different unicode forms before the assert.
        assert nfc_req.tool_name != nfd_req.tool_name
        # But canonical hashes match per JCS+NFC.
        assert SignedConsentBuilder.request_canonical_hash(
            nfc_req
        ) == SignedConsentBuilder.request_canonical_hash(nfd_req)


class TestSignedConsentBuilderResult:
    """build_signed_result handles all 3 ResolutionShapes correctly."""

    def _builder(self) -> tuple[SignedConsentBuilder, str]:
        km = InMemoryKeyManager()
        asyncio.run(km.generate_keypair("dk"))
        return SignedConsentBuilder(key_manager=km), "dk"

    def test_approve_once_result_is_signed(self) -> None:
        builder, key_id = self._builder()
        res = builder.build_signed_result(
            request_id="rq",
            result_id="rs",
            decided_at="2026-05-26T10:01:00Z",
            decided_on_channel_id="cli",
            delegation_record_ref="dr1",
            phase_a_record_ref="pa1",
            resolution=ApproveResolution(decided_by_principal_genesis_id="sha256:p"),
            delegation_key_id=key_id,
        )
        assert res.decision == "approve_once"
        assert res.signature_by_delegator_hex not in ("", "DENY_SIGNED_BY_LEDGER_ONLY")

    def test_approve_and_author_result_carries_payload(self) -> None:
        builder, key_id = self._builder()
        author_payload = {
            "new_constraint": {"name": "spend_cap"},
            "novelty_check_passed": True,
            "minimum_impact_passed": True,
        }
        res = builder.build_signed_result(
            request_id="rq",
            result_id="rs",
            decided_at="2026-05-26T10:01:00Z",
            decided_on_channel_id="cli",
            delegation_record_ref="dr1",
            phase_a_record_ref="pa1",
            resolution=ApproveResolution(
                decided_by_principal_genesis_id="sha256:p",
                author_payload=author_payload,
            ),
            delegation_key_id=key_id,
        )
        assert res.decision == "approve_and_author"
        assert res.author_payload == author_payload

    def test_deny_result_is_unsigned_with_sentinel(self) -> None:
        builder, _ = self._builder()
        # Deny path takes no delegation_key (Ledger signs the entry, not the Result).
        res = builder.build_signed_result(
            request_id="rq",
            result_id="rs",
            decided_at="2026-05-26T10:01:00Z",
            decided_on_channel_id="cli",
            delegation_record_ref="dr1",
            phase_a_record_ref="pa1",
            resolution=DeclineResolution(
                decided_by_principal_genesis_id="sha256:p", reason="not now"
            ),
        )
        assert res.decision == "deny"
        assert res.signature_by_delegator_hex == "DENY_SIGNED_BY_LEDGER_ONLY"

    def test_modify_result_carries_payload_and_signs(self) -> None:
        builder, key_id = self._builder()
        modify_payload = {
            "new_args_canonical": {"amount_microdollars": 5_000_000},
            "new_args_canonical_hash": "sha256:xyz",
        }
        res = builder.build_signed_result(
            request_id="rq",
            result_id="rs",
            decided_at="2026-05-26T10:01:00Z",
            decided_on_channel_id="cli",
            delegation_record_ref="dr1",
            phase_a_record_ref="pa1",
            resolution=ApproveWithModificationResolution(
                decided_by_principal_genesis_id="sha256:p",
                modify_payload=modify_payload,
            ),
            delegation_key_id=key_id,
        )
        assert res.decision == "modify"
        assert res.modify_payload == modify_payload
        assert res.signature_by_delegator_hex not in ("", "DENY_SIGNED_BY_LEDGER_ONLY")

    def test_approve_without_key_id_raises(self) -> None:
        builder, _ = self._builder()
        with pytest.raises(ValueError, match="required for Approve"):
            builder.build_signed_result(
                request_id="rq",
                result_id="rs",
                decided_at="2026-05-26T10:01:00Z",
                decided_on_channel_id="cli",
                delegation_record_ref="dr1",
                phase_a_record_ref="pa1",
                resolution=ApproveResolution(decided_by_principal_genesis_id="sha256:p"),
                delegation_key_id=None,
            )


# ---------------------------------------------------------------------------
# Wire-form canonicalization — JCS RFC 8785 invariants
# ---------------------------------------------------------------------------


class TestWireFormCanonicalization:
    def test_request_canonical_bytes_lex_ordered(
        self,
        sample_request_unsigned: GrantMomentRequest,
    ) -> None:
        # Two dicts of identical content but different key insertion order MUST
        # produce identical canonical bytes per JCS RFC 8785.
        b1 = SignedConsentBuilder._request_canonical_input(sample_request_unsigned)
        # Round-trip via JSON; the keys come out lex-sorted.
        decoded = json.loads(b1.decode("utf-8"))
        # Compare to re-canonicalization to prove lex-sort invariance.
        re_canonical = canonical_bytes(decoded)
        assert b1 == re_canonical


# ---------------------------------------------------------------------------
# Error taxonomy — 10 spec entries + state-machine plumbing
# ---------------------------------------------------------------------------


class TestErrorTaxonomy:
    """Each spec § Error taxonomy class carries the spec-promised attributes.

    These tests cover the contract-shape of the 10 spec error entries —
    they verify each error class's structural surface (attribute names +
    types + plain-language message + GrantMomentError base). The runtime
    RAISE-path tests for each threat live with the future
    EnvoyGrantMomentRuntime facade (see envoy/grant_moment/errors.py
    Layer attribution). Marking with @pytest.mark.regression pins the
    contract for the threat-mitigation surface so it cannot silently
    regress; pytest -m regression selects them alongside other regression
    tests for the threat coverage sweep per rules/testing.md MUST
    "Verify security mitigations have tests".
    """

    @pytest.mark.regression
    def test_grant_moment_expired_carries_request_and_timeout(self) -> None:
        """Contract pin: GrantMomentExpiredError surface (M2 timeout path)."""
        err = GrantMomentExpiredError(request_id="r1", timeout_seconds=300)
        assert err.request_id == "r1"
        assert err.timeout_seconds == 300
        assert isinstance(err, GrantMomentError)

    @pytest.mark.regression
    def test_grant_moment_timeout_carries_channel(self) -> None:
        """Contract pin: GrantMomentTimeoutError surface (channel render hang)."""
        err = GrantMomentTimeoutError(request_id="r1", channel_id="telegram")
        assert err.channel_id == "telegram"

    @pytest.mark.regression
    def test_dual_signature_required_carries_co_signer(self) -> None:
        """Contract pin: DualSignatureRequiredError surface (Phase-03 cross-principal)."""
        err = DualSignatureRequiredError(request_id="r1", awaiting_co_signer="bob")
        assert err.awaiting_co_signer == "bob"

    @pytest.mark.regression
    def test_not_primary_channel_carries_both_channels(self) -> None:
        """Contract pin: H-03 primary-channel binding for NotPrimaryChannelError.

        Threat mitigation: high-stakes Grant Moments approved from a
        non-primary channel MUST raise this typed error at M3
        sign-or-decline (NOT at M1 dispatch — ChannelHandoff records
        refusals structurally; see envoy/grant_moment/channel_handoff.py
        Layer split). The error names both the routed-to channel and the
        principal's primary channel so UX can surface the corrective path.
        """
        err = NotPrimaryChannelError(channel_id="slack", primary_channel_id="signal")
        assert err.channel_id == "slack"
        assert err.primary_channel_id == "signal"

    @pytest.mark.regression
    def test_velocity_raise_cooling_off_carries_24h_default(self) -> None:
        """Contract pin: T-093 R2-H4 velocity-raise 24h cooling-off ratchet."""
        err = VelocityRaiseCoolingOffError(elapsed_seconds=3600)
        # 24h cooling off per T-093 R2-H4
        assert err.required_seconds == 24 * 60 * 60
        assert err.elapsed_seconds == 3600

    @pytest.mark.regression
    def test_grant_moment_replay_carries_nonce_kind_and_prior_id(self) -> None:
        """Contract pin: T-008 nonce-replay defense surface.

        Threat mitigation: GrantMomentReplayError carries the duplicate
        value, its kind (nonce | intent_id), and the prior request_id so
        the runtime dedup store surfaces structural collision per spec
        T-008 nonce defense.
        """
        err = GrantMomentReplayError(
            duplicate_value="abcd1234",
            duplicate_kind="nonce",
            prior_request_id="r_prior",
        )
        assert err.duplicate_value == "abcd1234"
        assert err.duplicate_kind == "nonce"
        assert err.prior_request_id == "r_prior"

    @pytest.mark.regression
    def test_visible_secret_mismatch_carries_hashes_not_phrase(self) -> None:
        """Contract pin: T-018 dialog-spoofing defense — phrase MUST NOT leak.

        Threat mitigation: VisibleSecretMismatchError structurally cannot
        carry the visible-secret phrase content (only hashes) per spec
        T-018 + rules/security.md "No secrets in logs".
        """
        # Spec-aligned: error MUST NOT carry the phrase content (leak surface).
        err = VisibleSecretMismatchError(
            expected_phrase_hash="sha256:exp",
            rendered_phrase_hash="sha256:got",
        )
        assert err.expected_phrase_hash == "sha256:exp"
        assert "exp" in repr(err.expected_phrase_hash)
        # No phrase attribute exists — only hashes.
        assert not hasattr(err, "phrase")

    @pytest.mark.regression
    def test_novelty_friction_required_carries_friction_description(self) -> None:
        """Contract pin: T-019 habituation defense — 5s+double-tap friction."""
        err = NoveltyFrictionRequiredError(
            request_id="r1", required_friction="5s read-delay + double-tap"
        )
        assert err.required_friction == "5s read-delay + double-tap"

    @pytest.mark.regression
    def test_back_pressure_queue_full_carries_depth_and_ceiling(self) -> None:
        """Contract pin: back-pressure ceiling surface (concurrent grants)."""
        err = BackPressureQueueFullError(queue_ceiling=5, queue_depth=5)
        assert err.queue_ceiling == 5
        assert err.queue_depth == 5

    @pytest.mark.regression
    def test_cross_channel_confirm_failed_carries_confirm_channel(self) -> None:
        """Contract pin: cross-channel confirm leg failure surface (high-stakes)."""
        err = CrossChannelConfirmFailedError(request_id="r1", confirm_channel_id="signal")
        assert err.confirm_channel_id == "signal"

    def test_invalid_transition_error_is_internal_plumbing(self) -> None:
        # NOT in spec § Error taxonomy; surfaces state-machine misuse.
        err = InvalidGrantMomentTransitionError(
            current_state="M0_construct", attempted_event="decision_received"
        )
        assert err.current_state == "M0_construct"
        assert err.attempted_event == "decision_received"
        assert isinstance(err, GrantMomentError)

    def test_all_taxonomy_errors_subclass_grant_moment_error(self) -> None:
        # Catching GrantMomentError MUST cover the entire taxonomy per
        # `envoy/grant_moment/errors.py` design.
        all_classes = [
            GrantMomentExpiredError,
            GrantMomentTimeoutError,
            DualSignatureRequiredError,
            NotPrimaryChannelError,
            VelocityRaiseCoolingOffError,
            GrantMomentReplayError,
            VisibleSecretMismatchError,
            NoveltyFrictionRequiredError,
            BackPressureQueueFullError,
            CrossChannelConfirmFailedError,
            InvalidGrantMomentTransitionError,
        ]
        for cls in all_classes:
            assert issubclass(cls, GrantMomentError), f"{cls.__name__} not in taxonomy"
