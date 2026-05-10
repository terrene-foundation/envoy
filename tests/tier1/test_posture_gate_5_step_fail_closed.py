"""Tier 1 unit tests for envoy.authorship.posture_gate (T-02-31).

Per `rules/testing.md` § Tier 1 (mocking allowed; <1s per test).

Covers the 5 invariants from `02-wave-2-...md` § T-02-31 capacity check:

1. **5-step gate sequence** — every step has a dedicated test class that
   pins fail-closed behavior independent of the others.
2. **Fail-closed default** — every step's failure mode raises a typed error
   AND the Ledger.append is never called on the failure path.
3. **Cascade-on-demotion** — demotion path invokes the revoke hook per
   agent_id with the correct reason+revoked_by; ratchet-up path never calls.
4. **Signed posture_change Ledger entry** — happy path writes a posture_change
   entry whose content matches `specs/ledger.md` § posture_change schema
   (lines 243-253) byte-for-byte.
5. **Posture-ratchet enforcement** — the threshold table per spec lines 35-39
   is locked via `_required_authorship` directly + via end-to-end gate calls.

Plus structural tests: `PostureLevel` IntEnum ordering, `PostureMode` Enum,
`PostureEvidence.__post_init__` type validation, multi-step transition
path-independence.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from envoy.authorship.posture_gate import (
    PostureAuthorshipInsufficientError,
    PostureChangeResult,
    PostureCoolingOffActiveError,
    PostureEnterpriseAutonomousForbidden,
    PostureEvidence,
    PostureGate,
    PostureGateError,
    PostureGenesisGrantMissingError,
    PostureLevel,
    PostureMode,
    PostureNoopError,
    _required_authorship,
)
from envoy.authorship.score import AuthorshipScoreDivergenceError


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _FakeLedger:
    """In-memory Ledger fake. Records every append call for assertion."""

    appends: list[dict] = field(default_factory=list)
    next_entry_id: str = "sha256:fake-entry-id-0001"
    raise_on_append: BaseException | None = None

    async def append(
        self,
        *,
        entry_type: str,
        content: dict,
        intent_id: str | None = None,
        content_trust_level: str = "system",
    ) -> str:
        if self.raise_on_append is not None:
            raise self.raise_on_append
        self.appends.append(
            {
                "entry_type": entry_type,
                "content": content,
                "intent_id": intent_id,
                "content_trust_level": content_trust_level,
            }
        )
        return self.next_entry_id


@dataclass
class _FakeRevokeHook:
    """In-memory cascade-revoke fake. Records every call."""

    calls: list[dict] = field(default_factory=list)
    raise_on_call: BaseException | None = None

    async def __call__(
        self,
        *,
        agent_id: str,
        reason: str,
        revoked_by: str,
    ) -> object:
        if self.raise_on_call is not None:
            raise self.raise_on_call
        self.calls.append({"agent_id": agent_id, "reason": reason, "revoked_by": revoked_by})
        return object()


def _make_gate(
    *,
    ledger: _FakeLedger | None = None,
    revoke_hook: _FakeRevokeHook | None = None,
) -> tuple[PostureGate, _FakeLedger, _FakeRevokeHook]:
    led = ledger or _FakeLedger()
    rev = revoke_hook or _FakeRevokeHook()
    gate = PostureGate(ledger=led, revoke_hook=rev)
    return gate, led, rev


def _evidence(
    *,
    recomputed: int = 1,
    stored: int | None = None,  # None → defaults to `recomputed` so divergence is opt-in
    mode: PostureMode = PostureMode.PERSONAL,
    genesis_signed_grant: bool = True,
    cooling_off_active: bool = False,
    envelope_id_hash: str = "sha256:envelope-test",
) -> PostureEvidence:
    """Helper: stored defaults to recomputed (no divergence). Set stored
    explicitly to opt into divergence-test territory."""
    return PostureEvidence(
        authorship_score_recomputed=recomputed,
        authorship_score_stored=recomputed if stored is None else stored,
        mode=mode,
        genesis_signed_grant=genesis_signed_grant,
        cooling_off_active=cooling_off_active,
        envelope_id_hash=envelope_id_hash,
    )


def _run(coro):
    """Tier-1 helper: run async code without pytest-asyncio (which requires
    a plugin declaration we don't currently ship per `rules/testing.md`
    § Pytest Plugin + Marker Declaration Pair)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# PostureLevel + PostureMode + PostureEvidence structural tests
# ---------------------------------------------------------------------------


class TestPostureLevelOrdering:
    """Spec line 25: integer ordering is load-bearing for `>=` comparisons."""

    def test_canonical_order(self):
        assert PostureLevel.PSEUDO < PostureLevel.TOOL
        assert PostureLevel.TOOL < PostureLevel.SUPERVISED
        assert PostureLevel.SUPERVISED < PostureLevel.DELEGATING
        assert PostureLevel.DELEGATING < PostureLevel.AUTONOMOUS

    def test_int_values_pinned(self):
        # Wire-form invariant: integer values MUST be 0..4 in canonical order.
        # Changing these breaks any consumer that pickled / persisted a
        # PostureLevel as an int.
        assert int(PostureLevel.PSEUDO) == 0
        assert int(PostureLevel.TOOL) == 1
        assert int(PostureLevel.SUPERVISED) == 2
        assert int(PostureLevel.DELEGATING) == 3
        assert int(PostureLevel.AUTONOMOUS) == 4

    def test_string_names_match_spec(self):
        # Wire-form is the .name (uppercase) per spec line 27.
        for level in PostureLevel:
            assert level.name == level.name.upper()
        # Exact set check (no extras / no renames).
        names = {p.name for p in PostureLevel}
        assert names == {"PSEUDO", "TOOL", "SUPERVISED", "DELEGATING", "AUTONOMOUS"}


class TestPostureModeEnum:
    def test_two_modes(self):
        modes = {m.value for m in PostureMode}
        assert modes == {"personal", "enterprise"}

    def test_str_backed_for_json(self):
        # `rules/eatp.md` § Module Structure: str-backed Enum for
        # JSON-friendly serialization.
        assert PostureMode.PERSONAL.value == "personal"
        assert PostureMode.ENTERPRISE.value == "enterprise"


class TestPostureEvidencePostInit:
    """`PostureEvidence.__post_init__` rejects type-confused inputs at the
    boundary per `rules/security.md` § Multi-Site Kwarg Plumbing."""

    def test_recomputed_must_be_int(self):
        with pytest.raises(TypeError, match="authorship_score_recomputed must be int"):
            PostureEvidence(
                authorship_score_recomputed="3",  # type: ignore[arg-type]
                authorship_score_stored=3,
            )

    def test_stored_must_be_int(self):
        with pytest.raises(TypeError, match="authorship_score_stored must be int"):
            PostureEvidence(
                authorship_score_recomputed=3,
                authorship_score_stored="3",  # type: ignore[arg-type]
            )

    def test_recomputed_rejects_bool(self):
        # bool is a subclass of int — strict-identity check rejects.
        with pytest.raises(TypeError, match="authorship_score_recomputed must be int"):
            PostureEvidence(
                authorship_score_recomputed=True,  # type: ignore[arg-type]
                authorship_score_stored=1,
            )

    def test_stored_rejects_bool(self):
        with pytest.raises(TypeError, match="authorship_score_stored must be int"):
            PostureEvidence(
                authorship_score_recomputed=1,
                authorship_score_stored=False,  # type: ignore[arg-type]
            )

    def test_recomputed_negative_rejected(self):
        with pytest.raises(ValueError, match="authorship_score_recomputed must be non-negative"):
            PostureEvidence(authorship_score_recomputed=-1, authorship_score_stored=0)

    def test_stored_negative_rejected(self):
        with pytest.raises(ValueError, match="authorship_score_stored must be non-negative"):
            PostureEvidence(authorship_score_recomputed=0, authorship_score_stored=-1)

    def test_mode_must_be_posture_mode(self):
        with pytest.raises(TypeError, match="mode must be PostureMode"):
            PostureEvidence(
                authorship_score_recomputed=0,
                authorship_score_stored=0,
                mode="personal",  # type: ignore[arg-type]
            )

    def test_genesis_grant_must_be_bool(self):
        with pytest.raises(TypeError, match="genesis_signed_grant must be bool"):
            PostureEvidence(
                authorship_score_recomputed=0,
                authorship_score_stored=0,
                genesis_signed_grant=1,  # type: ignore[arg-type]
            )

    def test_cooling_off_must_be_bool(self):
        with pytest.raises(TypeError, match="cooling_off_active must be bool"):
            PostureEvidence(
                authorship_score_recomputed=0,
                authorship_score_stored=0,
                cooling_off_active="true",  # type: ignore[arg-type]
            )

    def test_envelope_id_hash_must_be_str(self):
        with pytest.raises(TypeError, match="envelope_id_hash must be str"):
            PostureEvidence(
                authorship_score_recomputed=0,
                authorship_score_stored=0,
                envelope_id_hash=None,  # type: ignore[arg-type]
            )

    def test_evidence_is_frozen(self):
        from dataclasses import FrozenInstanceError

        ev = _evidence()
        with pytest.raises(FrozenInstanceError):
            ev.authorship_score_recomputed = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Threshold table tests (spec lines 35-39)
# ---------------------------------------------------------------------------


class TestThresholdTablePersonal:
    def test_pseudo_to_tool_zero(self):
        assert (
            _required_authorship(PostureLevel.PSEUDO, PostureLevel.TOOL, PostureMode.PERSONAL) == 0
        )

    def test_tool_to_supervised_one(self):
        assert (
            _required_authorship(PostureLevel.TOOL, PostureLevel.SUPERVISED, PostureMode.PERSONAL)
            == 1
        )

    def test_supervised_to_delegating_three(self):
        assert (
            _required_authorship(
                PostureLevel.SUPERVISED, PostureLevel.DELEGATING, PostureMode.PERSONAL
            )
            == 3
        )

    def test_delegating_to_autonomous_five(self):
        assert (
            _required_authorship(
                PostureLevel.DELEGATING, PostureLevel.AUTONOMOUS, PostureMode.PERSONAL
            )
            == 5
        )


class TestThresholdTableEnterprise:
    def test_supervised_to_delegating_five(self):
        assert (
            _required_authorship(
                PostureLevel.SUPERVISED, PostureLevel.DELEGATING, PostureMode.ENTERPRISE
            )
            == 5
        )

    def test_pseudo_to_tool_zero_either_mode(self):
        # Phase 01 pseudo→tool transition has no mode-dependent threshold.
        assert (
            _required_authorship(PostureLevel.PSEUDO, PostureLevel.TOOL, PostureMode.ENTERPRISE)
            == 0
        )


class TestThresholdMultiStepPathIndependence:
    """Multi-step transitions use the highest single-step threshold along the
    path. Same target produces the same requirement regardless of starting
    level (path-independence invariant)."""

    def test_pseudo_to_delegating_personal_equals_supervised_to_delegating(self):
        assert _required_authorship(
            PostureLevel.PSEUDO, PostureLevel.DELEGATING, PostureMode.PERSONAL
        ) == _required_authorship(
            PostureLevel.SUPERVISED, PostureLevel.DELEGATING, PostureMode.PERSONAL
        )

    def test_pseudo_to_autonomous_personal_five(self):
        assert (
            _required_authorship(PostureLevel.PSEUDO, PostureLevel.AUTONOMOUS, PostureMode.PERSONAL)
            == 5
        )

    def test_pseudo_to_delegating_enterprise_five(self):
        assert (
            _required_authorship(
                PostureLevel.PSEUDO, PostureLevel.DELEGATING, PostureMode.ENTERPRISE
            )
            == 5
        )


# ---------------------------------------------------------------------------
# Step 1: divergence check
# ---------------------------------------------------------------------------


class TestStep1DivergenceCheck:
    def test_divergence_raises_first_short_circuiting_other_steps(self):
        gate, led, rev = _make_gate()
        ev = _evidence(recomputed=2, stored=1)  # divergent
        with pytest.raises(AuthorshipScoreDivergenceError) as exc:
            _run(
                gate.request_transition(
                    current=PostureLevel.TOOL,
                    target=PostureLevel.SUPERVISED,
                    evidence=ev,
                )
            )
        assert exc.value.stored == 1
        assert exc.value.recomputed == 2
        # Fail-closed: Ledger never written, revoke hook never called.
        assert led.appends == []
        assert rev.calls == []

    def test_divergence_takes_priority_over_noop(self):
        # Divergence MUST be checked before the noop check — otherwise a
        # divergent envelope with target == current would skip the audit alert.
        gate, led, _rev = _make_gate()
        ev = _evidence(recomputed=5, stored=3)
        with pytest.raises(AuthorshipScoreDivergenceError):
            _run(
                gate.request_transition(
                    current=PostureLevel.TOOL,
                    target=PostureLevel.TOOL,  # noop target
                    evidence=ev,
                )
            )
        assert led.appends == []

    def test_divergence_takes_priority_over_demotion(self):
        # Demotion is "always permitted" — but divergence is the audit alert
        # and MUST fire first regardless of direction.
        gate, led, rev = _make_gate()
        ev = _evidence(recomputed=0, stored=10)
        with pytest.raises(AuthorshipScoreDivergenceError):
            _run(
                gate.request_transition(
                    current=PostureLevel.DELEGATING,
                    target=PostureLevel.TOOL,
                    evidence=ev,
                    revoke_on_demotion=("agent-1",),
                )
            )
        assert led.appends == []
        assert rev.calls == []  # cascade-revoke ALSO short-circuits

    def test_matching_counts_pass_step_1(self):
        gate, led, _rev = _make_gate()
        ev = _evidence(recomputed=1, stored=1)
        result = _run(
            gate.request_transition(
                current=PostureLevel.TOOL,
                target=PostureLevel.SUPERVISED,
                evidence=ev,
            )
        )
        assert result.new_level is PostureLevel.SUPERVISED
        assert len(led.appends) == 1


# ---------------------------------------------------------------------------
# Step 2: noop check
# ---------------------------------------------------------------------------


class TestStep2NoopCheck:
    def test_noop_target_equals_current(self):
        gate, led, _rev = _make_gate()
        with pytest.raises(PostureNoopError) as exc:
            _run(
                gate.request_transition(
                    current=PostureLevel.SUPERVISED,
                    target=PostureLevel.SUPERVISED,
                    evidence=_evidence(),
                )
            )
        assert exc.value.level is PostureLevel.SUPERVISED
        assert "already at" in exc.value.user_message
        assert led.appends == []

    def test_noop_at_pseudo(self):
        gate, _led, _rev = _make_gate()
        with pytest.raises(PostureNoopError):
            _run(
                gate.request_transition(
                    current=PostureLevel.PSEUDO,
                    target=PostureLevel.PSEUDO,
                    evidence=_evidence(recomputed=0, stored=0),
                )
            )


# ---------------------------------------------------------------------------
# Step 3a: enterprise AUTONOMOUS forbidden
# ---------------------------------------------------------------------------


class TestStep3aEnterpriseAutonomousForbidden:
    def test_enterprise_autonomous_blocked_from_delegating(self):
        gate, led, _rev = _make_gate()
        with pytest.raises(PostureEnterpriseAutonomousForbidden):
            _run(
                gate.request_transition(
                    current=PostureLevel.DELEGATING,
                    target=PostureLevel.AUTONOMOUS,
                    evidence=_evidence(recomputed=10, mode=PostureMode.ENTERPRISE),
                )
            )
        assert led.appends == []

    def test_enterprise_autonomous_blocked_from_pseudo(self):
        # Multi-step path: PSEUDO → AUTONOMOUS via enterprise mode also blocked.
        gate, _led, _rev = _make_gate()
        with pytest.raises(PostureEnterpriseAutonomousForbidden):
            _run(
                gate.request_transition(
                    current=PostureLevel.PSEUDO,
                    target=PostureLevel.AUTONOMOUS,
                    evidence=_evidence(recomputed=10, stored=10, mode=PostureMode.ENTERPRISE),
                )
            )

    def test_personal_autonomous_NOT_blocked_by_3a(self):
        gate, led, _rev = _make_gate()
        result = _run(
            gate.request_transition(
                current=PostureLevel.DELEGATING,
                target=PostureLevel.AUTONOMOUS,
                evidence=_evidence(recomputed=5, stored=5, mode=PostureMode.PERSONAL),
            )
        )
        assert result.new_level is PostureLevel.AUTONOMOUS
        assert len(led.appends) == 1


# ---------------------------------------------------------------------------
# Step 3b: cooling-off check
# ---------------------------------------------------------------------------


class TestStep3bCoolingOff:
    def test_cooling_off_blocks_ratchet_up(self):
        gate, led, _rev = _make_gate()
        with pytest.raises(PostureCoolingOffActiveError) as exc:
            _run(
                gate.request_transition(
                    current=PostureLevel.TOOL,
                    target=PostureLevel.SUPERVISED,
                    evidence=_evidence(cooling_off_active=True),
                )
            )
        assert exc.value.current is PostureLevel.TOOL
        assert exc.value.target is PostureLevel.SUPERVISED
        assert led.appends == []

    def test_cooling_off_does_NOT_block_demotion(self):
        # Spec line 51: "Demotion NEVER requires authorship; it is always
        # permitted, always Genesis-signed". Cooling-off is a ratchet-UP gate.
        gate, led, _rev = _make_gate()
        result = _run(
            gate.request_transition(
                current=PostureLevel.DELEGATING,
                target=PostureLevel.TOOL,
                evidence=_evidence(cooling_off_active=True, genesis_signed_grant=False),
            )
        )
        assert result.new_level is PostureLevel.TOOL
        assert led.appends[0]["content"]["from_posture"] == "DELEGATING"
        assert led.appends[0]["content"]["to_posture"] == "TOOL"


# ---------------------------------------------------------------------------
# Step 3c: genesis-signed grant
# ---------------------------------------------------------------------------


class TestStep3cGenesisGrantMissing:
    def test_promotion_without_genesis_grant_blocked(self):
        gate, led, _rev = _make_gate()
        with pytest.raises(PostureGenesisGrantMissingError) as exc:
            _run(
                gate.request_transition(
                    current=PostureLevel.TOOL,
                    target=PostureLevel.SUPERVISED,
                    evidence=_evidence(genesis_signed_grant=False),
                )
            )
        assert exc.value.current is PostureLevel.TOOL
        assert exc.value.target is PostureLevel.SUPERVISED
        assert led.appends == []

    def test_promotion_with_genesis_grant_passes_step_3c(self):
        gate, led, _rev = _make_gate()
        _run(
            gate.request_transition(
                current=PostureLevel.TOOL,
                target=PostureLevel.SUPERVISED,
                evidence=_evidence(recomputed=1, stored=1, genesis_signed_grant=True),
            )
        )
        assert len(led.appends) == 1


# ---------------------------------------------------------------------------
# Step 3d: authorship-score threshold
# ---------------------------------------------------------------------------


class TestStep3dAuthorshipThreshold:
    def test_tool_to_supervised_requires_one(self):
        gate, _led, _rev = _make_gate()
        with pytest.raises(PostureAuthorshipInsufficientError) as exc:
            _run(
                gate.request_transition(
                    current=PostureLevel.TOOL,
                    target=PostureLevel.SUPERVISED,
                    evidence=_evidence(recomputed=0, stored=0),
                )
            )
        assert exc.value.have == 0
        assert exc.value.need == 1

    def test_supervised_to_delegating_personal_requires_three(self):
        gate, _led, _rev = _make_gate()
        with pytest.raises(PostureAuthorshipInsufficientError) as exc:
            _run(
                gate.request_transition(
                    current=PostureLevel.SUPERVISED,
                    target=PostureLevel.DELEGATING,
                    evidence=_evidence(recomputed=2, stored=2),
                )
            )
        assert exc.value.need == 3
        assert exc.value.have == 2

    def test_supervised_to_delegating_enterprise_requires_five(self):
        gate, _led, _rev = _make_gate()
        with pytest.raises(PostureAuthorshipInsufficientError) as exc:
            _run(
                gate.request_transition(
                    current=PostureLevel.SUPERVISED,
                    target=PostureLevel.DELEGATING,
                    evidence=_evidence(recomputed=4, stored=4, mode=PostureMode.ENTERPRISE),
                )
            )
        assert exc.value.need == 5
        assert exc.value.have == 4

    def test_delegating_to_autonomous_personal_requires_five(self):
        gate, _led, _rev = _make_gate()
        with pytest.raises(PostureAuthorshipInsufficientError) as exc:
            _run(
                gate.request_transition(
                    current=PostureLevel.DELEGATING,
                    target=PostureLevel.AUTONOMOUS,
                    evidence=_evidence(recomputed=4, stored=4),
                )
            )
        assert exc.value.need == 5

    def test_pseudo_to_tool_passes_with_zero_authorship(self):
        # Spec: PSEUDO → TOOL N=0 (default entry).
        gate, led, _rev = _make_gate()
        result = _run(
            gate.request_transition(
                current=PostureLevel.PSEUDO,
                target=PostureLevel.TOOL,
                evidence=_evidence(recomputed=0, stored=0),
            )
        )
        assert result.new_level is PostureLevel.TOOL
        assert len(led.appends) == 1


# ---------------------------------------------------------------------------
# Step 3 ordering: enterprise-AUTONOMOUS check fires BEFORE threshold lookup
# ---------------------------------------------------------------------------


class TestStep3OrderingEnterpriseFirst:
    def test_enterprise_autonomous_fires_before_authorship_check(self):
        # An enterprise caller requesting AUTONOMOUS with high authorship
        # MUST hit `PostureEnterpriseAutonomousForbidden` (3a), NOT
        # `PostureAuthorshipInsufficientError` (3d). The 3a check is BEFORE
        # the threshold lookup so the spec's "AUTONOMOUS forbidden under
        # enterprise" is unconditional.
        gate, _led, _rev = _make_gate()
        with pytest.raises(PostureEnterpriseAutonomousForbidden):
            _run(
                gate.request_transition(
                    current=PostureLevel.DELEGATING,
                    target=PostureLevel.AUTONOMOUS,
                    evidence=_evidence(recomputed=100, stored=100, mode=PostureMode.ENTERPRISE),
                )
            )

    def test_cooling_off_fires_before_genesis_check(self):
        # If both cooling-off active AND genesis grant missing, the
        # cooling-off error fires (the gate evaluates 3b before 3c).
        gate, _led, _rev = _make_gate()
        with pytest.raises(PostureCoolingOffActiveError):
            _run(
                gate.request_transition(
                    current=PostureLevel.TOOL,
                    target=PostureLevel.SUPERVISED,
                    evidence=_evidence(cooling_off_active=True, genesis_signed_grant=False),
                )
            )

    def test_genesis_check_fires_before_authorship_check(self):
        # If genesis grant missing AND authorship insufficient, genesis
        # missing fires first.
        gate, _led, _rev = _make_gate()
        with pytest.raises(PostureGenesisGrantMissingError):
            _run(
                gate.request_transition(
                    current=PostureLevel.SUPERVISED,
                    target=PostureLevel.DELEGATING,
                    evidence=_evidence(recomputed=0, stored=0, genesis_signed_grant=False),
                )
            )


# ---------------------------------------------------------------------------
# Step 4: cascade-revoke on demotion
# ---------------------------------------------------------------------------


class TestStep4CascadeRevoke:
    def test_demotion_calls_revoke_per_agent_id(self):
        gate, _led, rev = _make_gate()
        result = _run(
            gate.request_transition(
                current=PostureLevel.DELEGATING,
                target=PostureLevel.TOOL,
                evidence=_evidence(),
                revoke_on_demotion=("agent-1", "agent-2", "agent-3"),
            )
        )
        assert result.new_level is PostureLevel.TOOL
        assert len(rev.calls) == 3
        assert rev.calls[0]["agent_id"] == "agent-1"
        assert rev.calls[1]["agent_id"] == "agent-2"
        assert rev.calls[2]["agent_id"] == "agent-3"
        # Reason includes the from→to context.
        for call in rev.calls:
            assert call["reason"] == "posture_demotion:DELEGATING->TOOL"
            assert call["revoked_by"] == "posture_gate"

    def test_demotion_with_empty_revoke_list_succeeds(self):
        # Annual decay path: posture demotes but no standing delegations
        # to revoke (e.g. user was on TOOL anyway).
        gate, led, rev = _make_gate()
        result = _run(
            gate.request_transition(
                current=PostureLevel.SUPERVISED,
                target=PostureLevel.PSEUDO,
                evidence=_evidence(),
                revoke_on_demotion=(),
            )
        )
        assert result.new_level is PostureLevel.PSEUDO
        assert rev.calls == []
        assert len(led.appends) == 1

    def test_promotion_path_NEVER_calls_revoke(self):
        gate, _led, rev = _make_gate()
        _run(
            gate.request_transition(
                current=PostureLevel.TOOL,
                target=PostureLevel.SUPERVISED,
                evidence=_evidence(recomputed=1, stored=1),
                # Caller passing a list is irrelevant on promotion path.
                revoke_on_demotion=("agent-X",),
            )
        )
        assert rev.calls == []

    def test_revoke_hook_failure_propagates_before_ledger(self):
        # Per `rules/zero-tolerance.md` Rule 3 (no silent fallbacks): if the
        # revoke hook raises, the Ledger entry MUST NOT write — the demotion
        # is structurally incomplete.
        gate, led, rev = _make_gate(
            revoke_hook=_FakeRevokeHook(raise_on_call=RuntimeError("revoke failed"))
        )
        with pytest.raises(RuntimeError, match="revoke failed"):
            _run(
                gate.request_transition(
                    current=PostureLevel.DELEGATING,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(),
                    revoke_on_demotion=("agent-1",),
                )
            )
        assert led.appends == []

    def test_revoke_invalid_agent_id_rejected(self):
        gate, led, rev = _make_gate()
        with pytest.raises(ValueError, match="non-empty str"):
            _run(
                gate.request_transition(
                    current=PostureLevel.DELEGATING,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(),
                    revoke_on_demotion=("",),  # empty string
                )
            )
        assert rev.calls == []
        assert led.appends == []


# ---------------------------------------------------------------------------
# Ratchet-down structural invariant (spec lines 47-52)
# ---------------------------------------------------------------------------


class TestRatchetDownAlwaysPermitted:
    """Spec line 51: 'Demotion NEVER requires authorship; it is always permitted'.

    Demotion succeeds with zero authorship, no genesis grant, cooling-off
    active — the only requirement is non-divergent stored vs recomputed
    (Step 1 audit alert is universal).
    """

    def test_demotion_with_zero_authorship_succeeds(self):
        gate, led, _rev = _make_gate()
        result = _run(
            gate.request_transition(
                current=PostureLevel.DELEGATING,
                target=PostureLevel.PSEUDO,
                evidence=_evidence(recomputed=0, stored=0),
            )
        )
        assert result.new_level is PostureLevel.PSEUDO
        assert led.appends[0]["content"]["from_posture"] == "DELEGATING"

    def test_demotion_without_genesis_grant_succeeds(self):
        gate, led, _rev = _make_gate()
        result = _run(
            gate.request_transition(
                current=PostureLevel.AUTONOMOUS,
                target=PostureLevel.SUPERVISED,
                evidence=_evidence(recomputed=10, stored=10, genesis_signed_grant=False),
            )
        )
        assert result.new_level is PostureLevel.SUPERVISED
        assert len(led.appends) == 1

    def test_demotion_during_cooling_off_succeeds(self):
        gate, led, _rev = _make_gate()
        result = _run(
            gate.request_transition(
                current=PostureLevel.DELEGATING,
                target=PostureLevel.TOOL,
                evidence=_evidence(cooling_off_active=True),
            )
        )
        assert result.new_level is PostureLevel.TOOL
        assert len(led.appends) == 1


# ---------------------------------------------------------------------------
# Step 5: Ledger entry shape (spec lines 243-253)
# ---------------------------------------------------------------------------


class TestStep5LedgerEntrySchema:
    """Wire shape per `specs/ledger.md` § posture_change schema."""

    def test_happy_path_writes_posture_change_entry(self):
        gate, led, _rev = _make_gate()
        result = _run(
            gate.request_transition(
                current=PostureLevel.TOOL,
                target=PostureLevel.SUPERVISED,
                evidence=_evidence(recomputed=1, stored=1),
                trigger="weekly_review",
            )
        )
        assert result.ledger_entry_id == led.next_entry_id
        assert len(led.appends) == 1
        call = led.appends[0]
        assert call["entry_type"] == "posture_change"
        assert call["intent_id"] is None  # Phase 01 single-phase
        assert call["content_trust_level"] == "system"

    def test_ledger_content_matches_spec_schema(self):
        # Exact-key check against spec lines 243-253.
        gate, led, _rev = _make_gate()
        _run(
            gate.request_transition(
                current=PostureLevel.SUPERVISED,
                target=PostureLevel.DELEGATING,
                evidence=_evidence(recomputed=3, stored=3),
                trigger="authorship_threshold",
            )
        )
        content = led.appends[0]["content"]
        assert set(content.keys()) == {
            "schema_version",
            "from_posture",
            "to_posture",
            "dimension_scope",
            "trigger",
            "evidence_ref",
            "signed_by",
        }
        assert content["schema_version"] == "1.0"
        assert content["from_posture"] == "SUPERVISED"
        assert content["to_posture"] == "DELEGATING"
        assert content["dimension_scope"] == "global"
        assert content["trigger"] == "authorship_threshold"
        assert content["evidence_ref"] is None
        assert content["signed_by"] == "genesis_key"

    def test_demotion_emits_posture_change_with_correct_direction(self):
        gate, led, _rev = _make_gate()
        _run(
            gate.request_transition(
                current=PostureLevel.AUTONOMOUS,
                target=PostureLevel.TOOL,
                evidence=_evidence(),
                trigger="weekly_review",
            )
        )
        content = led.appends[0]["content"]
        assert content["from_posture"] == "AUTONOMOUS"
        assert content["to_posture"] == "TOOL"
        assert content["trigger"] == "weekly_review"

    def test_invalid_trigger_rejected_at_input(self):
        gate, led, _rev = _make_gate()
        with pytest.raises(ValueError, match="trigger must be one of"):
            _run(
                gate.request_transition(
                    current=PostureLevel.TOOL,
                    target=PostureLevel.SUPERVISED,
                    evidence=_evidence(),
                    trigger="user_action",  # NOT in spec's enum
                )
            )
        assert led.appends == []

    def test_all_spec_triggers_accepted(self):
        # Every value in spec line 250 MUST be accepted.
        for trigger in (
            "user_request",
            "annual_decay",
            "enterprise_attestation",
            "weekly_review",
            "authorship_threshold",
        ):
            gate, led, _rev = _make_gate()
            _run(
                gate.request_transition(
                    current=PostureLevel.SUPERVISED,
                    target=PostureLevel.TOOL,  # demotion path (no auth gates)
                    evidence=_evidence(),
                    trigger=trigger,
                )
            )
            assert led.appends[0]["content"]["trigger"] == trigger


# ---------------------------------------------------------------------------
# PostureGate construction discipline
# ---------------------------------------------------------------------------


class TestConstructionDiscipline:
    def test_ledger_required(self):
        with pytest.raises(ValueError, match="ledger is required"):
            PostureGate(ledger=None, revoke_hook=_FakeRevokeHook())  # type: ignore[arg-type]

    def test_revoke_hook_required(self):
        with pytest.raises(ValueError, match="revoke_hook is required"):
            PostureGate(ledger=_FakeLedger(), revoke_hook=None)  # type: ignore[arg-type]

    def test_request_transition_rejects_non_postureLevel_current(self):
        gate, _led, _rev = _make_gate()
        with pytest.raises(TypeError, match="current must be PostureLevel"):
            _run(
                gate.request_transition(
                    current=2,  # type: ignore[arg-type]
                    target=PostureLevel.DELEGATING,
                    evidence=_evidence(),
                )
            )

    def test_request_transition_rejects_non_postureLevel_target(self):
        gate, _led, _rev = _make_gate()
        with pytest.raises(TypeError, match="target must be PostureLevel"):
            _run(
                gate.request_transition(
                    current=PostureLevel.TOOL,
                    target="SUPERVISED",  # type: ignore[arg-type]
                    evidence=_evidence(),
                )
            )

    def test_request_transition_rejects_non_evidence(self):
        gate, _led, _rev = _make_gate()
        with pytest.raises(TypeError, match="evidence must be PostureEvidence"):
            _run(
                gate.request_transition(
                    current=PostureLevel.TOOL,
                    target=PostureLevel.SUPERVISED,
                    evidence={"authorship_score_recomputed": 1},  # type: ignore[arg-type]
                )
            )

    def test_request_transition_rejects_non_tuple_revoke_list(self):
        gate, _led, _rev = _make_gate()
        # Deliberately pass a list to verify runtime rejection — bypass static
        # type-check via cast so the runtime guard is exercised.
        from typing import cast

        list_arg = cast(tuple, ["agent-1"])
        with pytest.raises(TypeError, match="revoke_on_demotion must be tuple"):
            _run(
                gate.request_transition(
                    current=PostureLevel.DELEGATING,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(),
                    revoke_on_demotion=list_arg,
                )
            )


# ---------------------------------------------------------------------------
# PostureChangeResult shape
# ---------------------------------------------------------------------------


class TestPostureChangeResult:
    def test_result_carries_new_level_and_entry_id(self):
        gate, led, _rev = _make_gate()
        led.next_entry_id = "sha256:specific-id"
        result = _run(
            gate.request_transition(
                current=PostureLevel.TOOL,
                target=PostureLevel.SUPERVISED,
                evidence=_evidence(recomputed=1, stored=1),
            )
        )
        assert isinstance(result, PostureChangeResult)
        assert result.new_level is PostureLevel.SUPERVISED
        assert result.ledger_entry_id == "sha256:specific-id"

    def test_result_is_frozen(self):
        from dataclasses import FrozenInstanceError

        gate, _led, _rev = _make_gate()
        result = _run(
            gate.request_transition(
                current=PostureLevel.TOOL,
                target=PostureLevel.SUPERVISED,
                evidence=_evidence(recomputed=1, stored=1),
            )
        )
        with pytest.raises(FrozenInstanceError):
            result.new_level = PostureLevel.PSEUDO  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Error class hierarchy
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    def test_all_errors_inherit_from_PostureGateError(self):
        for cls in (
            PostureNoopError,
            PostureAuthorshipInsufficientError,
            PostureGenesisGrantMissingError,
            PostureCoolingOffActiveError,
            PostureEnterpriseAutonomousForbidden,
        ):
            assert issubclass(cls, PostureGateError)

    def test_all_errors_carry_user_message(self):
        # Plain-language user_message per `rules/communication.md`.
        errors = [
            PostureNoopError(PostureLevel.TOOL),
            PostureAuthorshipInsufficientError(
                current=PostureLevel.TOOL,
                target=PostureLevel.SUPERVISED,
                have=0,
                need=1,
            ),
            PostureGenesisGrantMissingError(
                current=PostureLevel.TOOL, target=PostureLevel.SUPERVISED
            ),
            PostureCoolingOffActiveError(current=PostureLevel.TOOL, target=PostureLevel.SUPERVISED),
            PostureEnterpriseAutonomousForbidden(),
        ]
        for err in errors:
            assert hasattr(err, "user_message")
            assert isinstance(err.user_message, str)
            assert len(err.user_message) > 0
            # No SLIP-0039 / cryptographic jargon should leak to user surfaces.
            assert "SLIP" not in err.user_message
            assert "Argon2" not in err.user_message
