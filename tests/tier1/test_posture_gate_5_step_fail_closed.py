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

from envoy.authorship.bet12_emitter import (
    BET12CadenceEmitter,
    BET12CadencePayload,
)
from envoy.authorship.posture_gate import (
    PostureAuthorshipInsufficientError,
    PostureChangeResult,
    PostureCoolingOffActiveError,
    PostureEnterpriseAutonomousForbidden,
    PostureEnvelopeMutationInvariantError,
    PostureEvidence,
    PostureGate,
    PostureGateError,
    PostureGenesisGrantMissingError,
    PostureLevel,
    PostureMode,
    PostureNoopError,
    PostureRatchetEnvelopeMissingError,
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


@dataclass
class _FakeBET12Sink:
    """In-memory BET-12 sink fake. Records every cadence payload written."""

    writes: list[BET12CadencePayload] = field(default_factory=list)
    raise_on_write: BaseException | None = None

    async def write(self, payload: BET12CadencePayload) -> None:
        if self.raise_on_write is not None:
            raise self.raise_on_write
        self.writes.append(payload)


@dataclass
class _FakePostureMutationResult:
    """Mirror of `envoy.authorship.posture_gate._PostureMutationResult` Protocol.

    Tier 1 fakes don't import the Protocol directly because Protocols are
    structural — any same-shaped object satisfies them. Fields match the
    Tier 2 adapter's `_PostureMutationOutcome` for cross-tier consistency.
    """

    envelope_id: str
    new_version: int
    new_content_hash: str
    diff_hash: str
    new_posture_level: str
    new_envelope: object


@dataclass
class _FakePostureCarryingEnvelope:
    """In-memory envelope fake satisfying the `_PostureCarryingEnvelope` Protocol.

    Records every `mutate_for_posture_level()` call so tests can assert
    the gate consumed the envelope exactly once on ratchet-up and zero
    times on ratchet-down / noop / Step-1-divergence paths.
    """

    envelope_id: str = "sha256:fake-envelope-0001"
    prior_version: int = 1
    prior_content_hash: str = "sha256:fake-prior-content"
    prior_posture_level: str = "PSEUDO"
    mutate_calls: list[PostureLevel] = field(default_factory=list)

    def mutate_for_posture_level(self, new_level: PostureLevel) -> _FakePostureMutationResult:
        self.mutate_calls.append(new_level)
        # diff_hash MUST match `sha256:<64-hex>` per F-2 invariant — produce a
        # spec-shaped synthetic hex; tests that need to exercise the malformed
        # branch construct the mutation result inline with a bad value.
        synthetic_hex = (new_level.name.encode("utf-8").hex() + "0" * 64)[:64]
        return _FakePostureMutationResult(
            envelope_id=self.envelope_id,
            new_version=self.prior_version + 1,
            new_content_hash=f"sha256:fake-new-content-{new_level.name}",
            diff_hash=f"sha256:{synthetic_hex}",
            new_posture_level=new_level.name,
            new_envelope=object(),
        )


def _make_gate(
    *,
    ledger: _FakeLedger | None = None,
    revoke_hook: _FakeRevokeHook | None = None,
    bet12_sink: _FakeBET12Sink | None = None,
) -> tuple[PostureGate, _FakeLedger, _FakeRevokeHook, _FakeBET12Sink]:
    led = ledger or _FakeLedger()
    rev = revoke_hook or _FakeRevokeHook()
    sink = bet12_sink or _FakeBET12Sink()
    emitter = BET12CadenceEmitter(sink=sink)
    gate = PostureGate(ledger=led, revoke_hook=rev, bet12_emitter=emitter)
    return gate, led, rev, sink


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

    def test_envelope_id_hash_length_capped(self):
        # security-reviewer F-2: defends against log-volume amplification
        # via attacker-controlled extra= keys.
        with pytest.raises(ValueError, match="envelope_id_hash length"):
            PostureEvidence(
                authorship_score_recomputed=0,
                authorship_score_stored=0,
                envelope_id_hash="x" * 129,
            )

    def test_envelope_id_hash_charset_enforced(self):
        # security-reviewer F-2: defends against log-injection via
        # control-character / whitespace in structured-log extra= keys.
        for bad in (
            "sha256:abc def",  # space
            "sha256:abc\nlog-injection",  # newline
            "sha256:abc;DROP",  # semicolon
            "sha256:abc<script>",  # angle brackets
            "sha256:abc\x00null",  # null byte
        ):
            with pytest.raises(ValueError, match="envelope_id_hash must match"):
                PostureEvidence(
                    authorship_score_recomputed=0,
                    authorship_score_stored=0,
                    envelope_id_hash=bad,
                )

    def test_envelope_id_hash_canonical_shape_accepted(self):
        # Canonical sha256 + base64-style + alphanumeric all pass.
        for ok in (
            "sha256:abc123",
            "sha256:" + "f" * 64,
            "envelope_v1-12345",
            "x" * 128,  # exactly at the cap
            "",  # explicitly permitted (callers without envelope context)
        ):
            ev = PostureEvidence(
                authorship_score_recomputed=0,
                authorship_score_stored=0,
                envelope_id_hash=ok,
            )
            assert ev.envelope_id_hash == ok

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


class TestThresholdDefensiveUnreachableGuard:
    """security-reviewer F-4: the `_required_authorship` defensive raise on
    structurally-unreachable inputs (target <= current invariant) MUST fire
    when the precondition is violated. Without this test, a future refactor
    that accidentally widens the precondition silently swallows the assertion."""

    def test_target_pseudo_unreachable_raises(self):
        # target=PSEUDO is impossible under the `target > current` precondition
        # because PSEUDO is integer-value 0 (the lowest level). Calling the
        # helper directly with target=PSEUDO bypasses the precondition; the
        # defensive raise MUST fire.
        with pytest.raises(ValueError, match="unreachable"):
            _required_authorship(PostureLevel.PSEUDO, PostureLevel.PSEUDO, PostureMode.PERSONAL)

    def test_target_tool_multistep_unreachable_raises(self):
        # target=TOOL via a multi-step path is impossible — only PSEUDO->TOOL
        # reaches TOOL, and that's a single-step branch handled at the top.
        # Calling with (TOOL, TOOL) (target == current) is not >=current, but
        # the helper has no precondition guard; the defensive raise fires.
        with pytest.raises(ValueError, match="unreachable"):
            _required_authorship(PostureLevel.TOOL, PostureLevel.TOOL, PostureMode.PERSONAL)


# ---------------------------------------------------------------------------
# Step 1: divergence check
# ---------------------------------------------------------------------------


class TestStep1DivergenceCheck:
    def test_divergence_raises_first_short_circuiting_other_steps(self):
        gate, led, rev, _sink = _make_gate()
        ev = _evidence(recomputed=2, stored=1)  # divergent
        with pytest.raises(AuthorshipScoreDivergenceError) as exc:
            _run(
                gate.request_transition(
                    principal_id="agent-test",
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
        gate, led, _rev, _sink = _make_gate()
        ev = _evidence(recomputed=5, stored=3)
        with pytest.raises(AuthorshipScoreDivergenceError):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.TOOL,
                    target=PostureLevel.TOOL,  # noop target
                    evidence=ev,
                )
            )
        assert led.appends == []

    def test_divergence_takes_priority_over_demotion(self):
        # Demotion is "always permitted" — but divergence is the audit alert
        # and MUST fire first regardless of direction.
        gate, led, rev, _sink = _make_gate()
        ev = _evidence(recomputed=0, stored=10)
        with pytest.raises(AuthorshipScoreDivergenceError):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.DELEGATING,
                    target=PostureLevel.TOOL,
                    evidence=ev,
                    revoke_on_demotion=("agent-1",),
                )
            )
        assert led.appends == []
        assert rev.calls == []  # cascade-revoke ALSO short-circuits

    def test_matching_counts_pass_step_1(self):
        gate, led, _rev, _sink = _make_gate()
        ev = _evidence(recomputed=1, stored=1)
        result = _run(
            gate.request_transition(
                principal_id="agent-test",
                current=PostureLevel.TOOL,
                target=PostureLevel.SUPERVISED,
                evidence=ev,
                envelope=_FakePostureCarryingEnvelope(),
            )
        )
        assert result.new_level is PostureLevel.SUPERVISED
        # T-02-33: ratchet-up now emits BOTH posture_change AND envelope_edit.
        assert len(led.appends) == 2
        assert led.appends[0]["entry_type"] == "posture_change"
        assert led.appends[1]["entry_type"] == "envelope_edit"


# ---------------------------------------------------------------------------
# Step 2: noop check
# ---------------------------------------------------------------------------


class TestStep2NoopCheck:
    def test_noop_target_equals_current(self):
        gate, led, _rev, _sink = _make_gate()
        with pytest.raises(PostureNoopError) as exc:
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.SUPERVISED,
                    target=PostureLevel.SUPERVISED,
                    evidence=_evidence(),
                )
            )
        assert exc.value.level is PostureLevel.SUPERVISED
        assert "already at" in exc.value.user_message
        assert led.appends == []

    def test_noop_at_pseudo(self):
        gate, _led, _rev, _sink = _make_gate()
        with pytest.raises(PostureNoopError):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
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
        gate, led, _rev, _sink = _make_gate()
        with pytest.raises(PostureEnterpriseAutonomousForbidden):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.DELEGATING,
                    target=PostureLevel.AUTONOMOUS,
                    evidence=_evidence(recomputed=10, mode=PostureMode.ENTERPRISE),
                )
            )
        assert led.appends == []

    def test_enterprise_autonomous_blocked_from_pseudo(self):
        # Multi-step path: PSEUDO → AUTONOMOUS via enterprise mode also blocked.
        gate, _led, _rev, _sink = _make_gate()
        with pytest.raises(PostureEnterpriseAutonomousForbidden):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.PSEUDO,
                    target=PostureLevel.AUTONOMOUS,
                    evidence=_evidence(recomputed=10, stored=10, mode=PostureMode.ENTERPRISE),
                )
            )

    def test_personal_autonomous_NOT_blocked_by_3a(self):
        gate, led, _rev, _sink = _make_gate()
        result = _run(
            gate.request_transition(
                principal_id="agent-test",
                current=PostureLevel.DELEGATING,
                target=PostureLevel.AUTONOMOUS,
                evidence=_evidence(recomputed=5, stored=5, mode=PostureMode.PERSONAL),
                envelope=_FakePostureCarryingEnvelope(),
            )
        )
        assert result.new_level is PostureLevel.AUTONOMOUS
        # T-02-33: ratchet-up now emits paired posture_change + envelope_edit.
        assert len(led.appends) == 2


# ---------------------------------------------------------------------------
# Step 3b: cooling-off check
# ---------------------------------------------------------------------------


class TestStep3bCoolingOff:
    def test_cooling_off_blocks_ratchet_up(self):
        gate, led, _rev, _sink = _make_gate()
        with pytest.raises(PostureCoolingOffActiveError) as exc:
            _run(
                gate.request_transition(
                    principal_id="agent-test",
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
        gate, led, _rev, _sink = _make_gate()
        result = _run(
            gate.request_transition(
                principal_id="agent-test",
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
        gate, led, _rev, _sink = _make_gate()
        with pytest.raises(PostureGenesisGrantMissingError) as exc:
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.TOOL,
                    target=PostureLevel.SUPERVISED,
                    evidence=_evidence(genesis_signed_grant=False),
                )
            )
        assert exc.value.current is PostureLevel.TOOL
        assert exc.value.target is PostureLevel.SUPERVISED
        assert led.appends == []

    def test_promotion_with_genesis_grant_passes_step_3c(self):
        gate, led, _rev, _sink = _make_gate()
        _run(
            gate.request_transition(
                principal_id="agent-test",
                current=PostureLevel.TOOL,
                target=PostureLevel.SUPERVISED,
                evidence=_evidence(recomputed=1, stored=1, genesis_signed_grant=True),
                envelope=_FakePostureCarryingEnvelope(),
            )
        )
        # T-02-33: ratchet-up emits paired posture_change + envelope_edit.
        assert len(led.appends) == 2


# ---------------------------------------------------------------------------
# Step 3d: authorship-score threshold
# ---------------------------------------------------------------------------


class TestStep3dAuthorshipThreshold:
    def test_tool_to_supervised_requires_one(self):
        gate, _led, _rev, _sink = _make_gate()
        with pytest.raises(PostureAuthorshipInsufficientError) as exc:
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.TOOL,
                    target=PostureLevel.SUPERVISED,
                    evidence=_evidence(recomputed=0, stored=0),
                )
            )
        assert exc.value.have == 0
        assert exc.value.need == 1

    def test_supervised_to_delegating_personal_requires_three(self):
        gate, _led, _rev, _sink = _make_gate()
        with pytest.raises(PostureAuthorshipInsufficientError) as exc:
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.SUPERVISED,
                    target=PostureLevel.DELEGATING,
                    evidence=_evidence(recomputed=2, stored=2),
                )
            )
        assert exc.value.need == 3
        assert exc.value.have == 2

    def test_supervised_to_delegating_enterprise_requires_five(self):
        gate, _led, _rev, _sink = _make_gate()
        with pytest.raises(PostureAuthorshipInsufficientError) as exc:
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.SUPERVISED,
                    target=PostureLevel.DELEGATING,
                    evidence=_evidence(recomputed=4, stored=4, mode=PostureMode.ENTERPRISE),
                )
            )
        assert exc.value.need == 5
        assert exc.value.have == 4

    def test_delegating_to_autonomous_personal_requires_five(self):
        gate, _led, _rev, _sink = _make_gate()
        with pytest.raises(PostureAuthorshipInsufficientError) as exc:
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.DELEGATING,
                    target=PostureLevel.AUTONOMOUS,
                    evidence=_evidence(recomputed=4, stored=4),
                )
            )
        assert exc.value.need == 5

    def test_pseudo_to_tool_passes_with_zero_authorship(self):
        # Spec: PSEUDO → TOOL N=0 (default entry).
        gate, led, _rev, _sink = _make_gate()
        result = _run(
            gate.request_transition(
                principal_id="agent-test",
                current=PostureLevel.PSEUDO,
                target=PostureLevel.TOOL,
                evidence=_evidence(recomputed=0, stored=0),
                envelope=_FakePostureCarryingEnvelope(),
            )
        )
        assert result.new_level is PostureLevel.TOOL
        # T-02-33: ratchet-up emits paired posture_change + envelope_edit.
        assert len(led.appends) == 2


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
        gate, _led, _rev, _sink = _make_gate()
        with pytest.raises(PostureEnterpriseAutonomousForbidden):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.DELEGATING,
                    target=PostureLevel.AUTONOMOUS,
                    evidence=_evidence(recomputed=100, stored=100, mode=PostureMode.ENTERPRISE),
                )
            )

    def test_cooling_off_fires_before_genesis_check(self):
        # If both cooling-off active AND genesis grant missing, the
        # cooling-off error fires (the gate evaluates 3b before 3c).
        gate, _led, _rev, _sink = _make_gate()
        with pytest.raises(PostureCoolingOffActiveError):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.TOOL,
                    target=PostureLevel.SUPERVISED,
                    evidence=_evidence(cooling_off_active=True, genesis_signed_grant=False),
                )
            )

    def test_genesis_check_fires_before_authorship_check(self):
        # If genesis grant missing AND authorship insufficient, genesis
        # missing fires first.
        gate, _led, _rev, _sink = _make_gate()
        with pytest.raises(PostureGenesisGrantMissingError):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
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
        gate, _led, rev, _sink = _make_gate()
        result = _run(
            gate.request_transition(
                principal_id="agent-test",
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
        gate, led, rev, _sink = _make_gate()
        result = _run(
            gate.request_transition(
                principal_id="agent-test",
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
        gate, _led, rev, _sink = _make_gate()
        _run(
            gate.request_transition(
                principal_id="agent-test",
                current=PostureLevel.TOOL,
                target=PostureLevel.SUPERVISED,
                evidence=_evidence(recomputed=1, stored=1),
                # Caller passing a list is irrelevant on promotion path.
                revoke_on_demotion=("agent-X",),
                envelope=_FakePostureCarryingEnvelope(),
            )
        )
        assert rev.calls == []

    def test_revoke_hook_failure_propagates_before_ledger(self):
        # Per `rules/zero-tolerance.md` Rule 3 (no silent fallbacks): if the
        # revoke hook raises, the Ledger entry MUST NOT write — the demotion
        # is structurally incomplete.
        gate, led, rev, _sink = _make_gate(
            revoke_hook=_FakeRevokeHook(raise_on_call=RuntimeError("revoke failed"))
        )
        with pytest.raises(RuntimeError, match="revoke failed"):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.DELEGATING,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(),
                    revoke_on_demotion=("agent-1",),
                )
            )
        assert led.appends == []

    def test_revoke_invalid_agent_id_rejected(self):
        gate, led, rev, _sink = _make_gate()
        with pytest.raises(ValueError, match="non-empty str"):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.DELEGATING,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(),
                    revoke_on_demotion=("",),  # empty string
                )
            )
        assert rev.calls == []
        assert led.appends == []

    def _attempt_revoke(self, gate, agent_id):
        """Helper: invoke a demotion with a single agent_id; return the
        raise context for subsequent assertions."""
        return _run(
            gate.request_transition(
                principal_id="agent-test",
                current=PostureLevel.DELEGATING,
                target=PostureLevel.TOOL,
                evidence=_evidence(),
                revoke_on_demotion=(agent_id,),
            )
        )

    def test_revoke_agent_id_too_long_rejected(self):
        # security-reviewer F-1: defense-in-depth at the gate boundary
        # (do not rely on TrustStoreAdapter.revoke as the sole guard).
        gate, led, rev, _sink = _make_gate()
        with pytest.raises(ValueError, match="length .* exceeds"):
            self._attempt_revoke(gate, "x" * 257)
        assert rev.calls == []
        assert led.appends == []

    def test_revoke_agent_id_null_byte_rejected(self):
        gate, led, rev, _sink = _make_gate()
        with pytest.raises(ValueError, match="null byte"):
            self._attempt_revoke(gate, "agent\x00bypass")
        assert rev.calls == []
        assert led.appends == []

    def test_revoke_agent_id_control_char_rejected(self):
        gate, led, rev, _sink = _make_gate()
        with pytest.raises(ValueError, match="control character"):
            self._attempt_revoke(gate, "agent\nlog-injection")
        assert rev.calls == []
        assert led.appends == []

    def test_revoke_agent_id_path_separator_rejected(self):
        gate, led, rev, _sink = _make_gate()
        for bad in ("agent/../etc/passwd", "agent\\windows", "../escape"):
            rev.calls.clear()
            led.appends.clear()
            with pytest.raises(ValueError):
                self._attempt_revoke(gate, bad)
            assert rev.calls == []
            assert led.appends == []

    def test_revoke_agent_id_leading_dot_rejected(self):
        gate, led, rev, _sink = _make_gate()
        with pytest.raises(ValueError, match="hidden-file shape"):
            self._attempt_revoke(gate, ".hidden-agent")
        assert rev.calls == []
        assert led.appends == []

    def test_revoke_agent_id_legitimate_pseudonym_accepted(self):
        # Mirrors envoy/trust/store.py::_validate_id_safety contract:
        # pseudonyms can contain @, ., +, -, _ — not slug-only.
        gate, led, rev, _sink = _make_gate()
        for ok in ("alice@example", "agent.42+ci", "agent_42-prod", "a"):
            rev.calls.clear()
            led.appends.clear()
            self._attempt_revoke(gate, ok)
            assert rev.calls == [
                {
                    "agent_id": ok,
                    "reason": "posture_demotion:DELEGATING->TOOL",
                    "revoked_by": "posture_gate",
                }
            ]
            assert len(led.appends) == 1


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
        gate, led, _rev, _sink = _make_gate()
        result = _run(
            gate.request_transition(
                principal_id="agent-test",
                current=PostureLevel.DELEGATING,
                target=PostureLevel.PSEUDO,
                evidence=_evidence(recomputed=0, stored=0),
            )
        )
        assert result.new_level is PostureLevel.PSEUDO
        assert led.appends[0]["content"]["from_posture"] == "DELEGATING"

    def test_demotion_without_genesis_grant_succeeds(self):
        gate, led, _rev, _sink = _make_gate()
        result = _run(
            gate.request_transition(
                principal_id="agent-test",
                current=PostureLevel.AUTONOMOUS,
                target=PostureLevel.SUPERVISED,
                evidence=_evidence(recomputed=10, stored=10, genesis_signed_grant=False),
            )
        )
        assert result.new_level is PostureLevel.SUPERVISED
        assert len(led.appends) == 1

    def test_demotion_during_cooling_off_succeeds(self):
        gate, led, _rev, _sink = _make_gate()
        result = _run(
            gate.request_transition(
                principal_id="agent-test",
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
        gate, led, _rev, _sink = _make_gate()
        result = _run(
            gate.request_transition(
                principal_id="agent-test",
                current=PostureLevel.TOOL,
                target=PostureLevel.SUPERVISED,
                evidence=_evidence(recomputed=1, stored=1),
                trigger="weekly_review",
                envelope=_FakePostureCarryingEnvelope(),
            )
        )
        # T-02-33: result.ledger_entry_id is the posture_change entry id
        # (Step 5a). The envelope_edit entry (Step 5b) lands second; the
        # _FakeLedger returns the same `next_entry_id` for both appends in
        # this test, so result.ledger_entry_id equals next_entry_id.
        assert result.ledger_entry_id == led.next_entry_id
        # T-02-33: ratchet-up emits paired posture_change + envelope_edit.
        assert len(led.appends) == 2
        posture_call = led.appends[0]
        assert posture_call["entry_type"] == "posture_change"
        assert posture_call["intent_id"] is None  # Phase 01 single-phase
        assert posture_call["content_trust_level"] == "system"
        envelope_call = led.appends[1]
        assert envelope_call["entry_type"] == "envelope_edit"
        assert envelope_call["content_trust_level"] == "system"

    def test_ledger_content_matches_spec_schema(self):
        # Exact-key check against spec lines 243-253.
        gate, led, _rev, _sink = _make_gate()
        _run(
            gate.request_transition(
                principal_id="agent-test",
                current=PostureLevel.SUPERVISED,
                target=PostureLevel.DELEGATING,
                evidence=_evidence(recomputed=3, stored=3),
                trigger="authorship_threshold",
                envelope=_FakePostureCarryingEnvelope(),
            )
        )
        # Step 5a posture_change content per spec lines 243-253
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
        # T-02-33: Step 5b envelope_edit content per spec lines 107-114
        env_content = led.appends[1]["content"]
        assert set(env_content.keys()) == {
            "schema_version",
            "envelope_id",
            "prior_version",
            "new_version",
            "diff_hash",
            "rollback_grace_window_seconds",
            "signed_by",
        }
        assert env_content["schema_version"] == "1.0"
        assert env_content["new_version"] == env_content["prior_version"] + 1
        assert env_content["signed_by"] == "delegation_key"
        assert env_content["diff_hash"].startswith("sha256:")

    def test_demotion_emits_posture_change_with_correct_direction(self):
        gate, led, _rev, _sink = _make_gate()
        _run(
            gate.request_transition(
                principal_id="agent-test",
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
        gate, led, _rev, _sink = _make_gate()
        with pytest.raises(ValueError, match="trigger must be one of"):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
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
            gate, led, _rev, _sink = _make_gate()
            _run(
                gate.request_transition(
                    principal_id="agent-test",
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
            PostureGate(
                ledger=None,  # type: ignore[arg-type]
                revoke_hook=_FakeRevokeHook(),
                bet12_emitter=BET12CadenceEmitter(sink=_FakeBET12Sink()),
            )

    def test_revoke_hook_required(self):
        with pytest.raises(ValueError, match="revoke_hook is required"):
            PostureGate(
                ledger=_FakeLedger(),
                revoke_hook=None,  # type: ignore[arg-type]
                bet12_emitter=BET12CadenceEmitter(sink=_FakeBET12Sink()),
            )

    def test_bet12_emitter_required(self):
        with pytest.raises(ValueError, match="bet12_emitter is required"):
            PostureGate(
                ledger=_FakeLedger(),
                revoke_hook=_FakeRevokeHook(),
                bet12_emitter=None,  # type: ignore[arg-type]
            )

    def test_request_transition_rejects_non_postureLevel_current(self):
        gate, _led, _rev, _sink = _make_gate()
        with pytest.raises(TypeError, match="current must be PostureLevel"):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=2,  # type: ignore[arg-type]
                    target=PostureLevel.DELEGATING,
                    evidence=_evidence(),
                )
            )

    def test_request_transition_rejects_non_postureLevel_target(self):
        gate, _led, _rev, _sink = _make_gate()
        with pytest.raises(TypeError, match="target must be PostureLevel"):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.TOOL,
                    target="SUPERVISED",  # type: ignore[arg-type]
                    evidence=_evidence(),
                )
            )

    def test_request_transition_rejects_non_evidence(self):
        gate, _led, _rev, _sink = _make_gate()
        with pytest.raises(TypeError, match="evidence must be PostureEvidence"):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.TOOL,
                    target=PostureLevel.SUPERVISED,
                    evidence={"authorship_score_recomputed": 1},  # type: ignore[arg-type]
                )
            )

    def test_request_transition_rejects_non_tuple_revoke_list(self):
        gate, _led, _rev, _sink = _make_gate()
        # Deliberately pass a list to verify runtime rejection — bypass static
        # type-check via cast so the runtime guard is exercised.
        from typing import cast

        list_arg = cast(tuple, ["agent-1"])
        with pytest.raises(TypeError, match="revoke_on_demotion must be tuple"):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.DELEGATING,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(),
                    revoke_on_demotion=list_arg,
                )
            )


# ---------------------------------------------------------------------------
# Step 5+ BET-12 cadence emission (T-02-32 wiring invariant)
# ---------------------------------------------------------------------------


class TestStep5PlusBET12Emission:
    """Per `01-analysis/09-...md` § 3.3 + T-02-32 capacity check invariant 2:
    BET-12 emit fires on every posture-transition the gate accepts. This is
    the production call site that prevents `BET12CadenceEmitter` from being
    an orphan facade per `rules/orphan-detection.md` Rule 1."""

    def test_ratchet_up_emits_bet12_after_ledger(self):
        gate, led, _rev, sink = _make_gate()
        _run(
            gate.request_transition(
                principal_id="agent-A",
                current=PostureLevel.TOOL,
                target=PostureLevel.SUPERVISED,
                evidence=_evidence(recomputed=1, stored=1),
                days_at_current_posture=4.5,
                envelope=_FakePostureCarryingEnvelope(),
            )
        )
        # T-02-33: Ledger fires Step 5a (posture_change) + Step 5b
        # (envelope_edit) in order; emitter fires Step 5+.
        assert len(led.appends) == 2
        assert led.appends[0]["entry_type"] == "posture_change"
        assert led.appends[1]["entry_type"] == "envelope_edit"
        assert len(sink.writes) == 1
        payload = sink.writes[0]
        assert payload.bet_id == "BET-12"
        assert payload.from_level is PostureLevel.TOOL
        assert payload.to_level is PostureLevel.SUPERVISED
        assert payload.days_at_current_posture == 4.5
        assert payload.authored_count_at_transition == 1

    def test_ratchet_down_emits_bet12(self):
        # Ratchet-down (annual decay / user-initiated demotion) MUST also
        # emit: the cohort-cadence dataset needs demotion data to falsify
        # BET-12. Trigger `annual_decay` is the canonical demotion trigger.
        gate, _led, _rev, sink = _make_gate()
        _run(
            gate.request_transition(
                principal_id="agent-A",
                current=PostureLevel.DELEGATING,
                target=PostureLevel.TOOL,
                evidence=_evidence(recomputed=5, stored=5),
                trigger="annual_decay",
                days_at_current_posture=14.0,
            )
        )
        assert len(sink.writes) == 1
        assert sink.writes[0].from_level is PostureLevel.DELEGATING
        assert sink.writes[0].to_level is PostureLevel.TOOL

    def test_failed_gate_does_not_emit_bet12(self):
        # Fail-closed default: every step's failure mode MUST short-circuit
        # before Ledger AND before BET-12 emission. The cohort-cadence
        # dataset records ACCEPTED transitions only.
        gate, led, _rev, sink = _make_gate()
        with pytest.raises(PostureAuthorshipInsufficientError):
            _run(
                gate.request_transition(
                    principal_id="agent-A",
                    current=PostureLevel.SUPERVISED,
                    target=PostureLevel.DELEGATING,
                    evidence=_evidence(recomputed=2, stored=2),  # below N=3
                )
            )
        assert led.appends == []  # Step 5 never wrote
        assert sink.writes == []  # Step 5+ never wrote

    def test_principal_id_hashed_in_bet12_payload(self):
        # The PostureGate principal_id flows through to the emitter; the
        # emitter hashes it. Verify byte-identity: principal_id never
        # appears raw in the cadence payload.
        gate, _led, _rev, sink = _make_gate()
        principal = "user-secret-001"
        _run(
            gate.request_transition(
                principal_id=principal,
                current=PostureLevel.PSEUDO,
                target=PostureLevel.TOOL,
                evidence=_evidence(recomputed=0, stored=0),
                envelope=_FakePostureCarryingEnvelope(),
            )
        )
        assert len(sink.writes) == 1
        h = sink.writes[0].principal_id_hash
        assert h.startswith("sha256:")
        assert principal not in repr(sink.writes[0])

    def test_authored_count_pulled_from_evidence_recomputed(self):
        # The wiring takes `evidence.authorship_score_recomputed` for the
        # cadence payload's `authored_count_at_transition` field — Phase 01
        # narrow scope (the recomputed-vs-stored divergence at Step 1 has
        # already raised if they diverge).
        gate, _led, _rev, sink = _make_gate()
        _run(
            gate.request_transition(
                principal_id="agent-A",
                current=PostureLevel.SUPERVISED,
                target=PostureLevel.DELEGATING,
                evidence=_evidence(recomputed=3, stored=3),
                envelope=_FakePostureCarryingEnvelope(),
            )
        )
        assert sink.writes[0].authored_count_at_transition == 3

    def test_default_days_zero_when_caller_omits(self):
        # Phase 01 callers that don't yet track days-at-current-posture
        # may omit the kwarg; the gate's default is 0.0. This is honest:
        # the BET dataset will have many 0.0 entries until Phase 03 WPR
        # ritual computes actual days from PostureStore history.
        gate, _led, _rev, sink = _make_gate()
        _run(
            gate.request_transition(
                principal_id="agent-A",
                current=PostureLevel.PSEUDO,
                target=PostureLevel.TOOL,
                evidence=_evidence(recomputed=0, stored=0),
                envelope=_FakePostureCarryingEnvelope(),
            )
        )
        assert sink.writes[0].days_at_current_posture == 0.0


# ---------------------------------------------------------------------------
# PostureChangeResult shape
# ---------------------------------------------------------------------------


class TestPostureChangeResult:
    def test_result_carries_new_level_and_entry_id(self):
        gate, led, _rev, _sink = _make_gate()
        led.next_entry_id = "sha256:specific-id"
        result = _run(
            gate.request_transition(
                principal_id="agent-test",
                current=PostureLevel.TOOL,
                target=PostureLevel.SUPERVISED,
                evidence=_evidence(recomputed=1, stored=1),
                envelope=_FakePostureCarryingEnvelope(),
            )
        )
        assert isinstance(result, PostureChangeResult)
        assert result.new_level is PostureLevel.SUPERVISED
        # T-02-33: result.ledger_entry_id is the posture_change entry id
        # (Step 5a). The _FakeLedger returns next_entry_id for every
        # append; both Step 5a and Step 5b appends see the same id here.
        assert result.ledger_entry_id == "sha256:specific-id"

    def test_result_is_frozen(self):
        from dataclasses import FrozenInstanceError

        gate, _led, _rev, _sink = _make_gate()
        result = _run(
            gate.request_transition(
                principal_id="agent-test",
                current=PostureLevel.TOOL,
                target=PostureLevel.SUPERVISED,
                evidence=_evidence(recomputed=1, stored=1),
                envelope=_FakePostureCarryingEnvelope(),
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
            PostureRatchetEnvelopeMissingError,  # T-02-33
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
            # T-02-33 — PostureRatchetEnvelopeMissingError carries the same
            # plain-language contract.
            PostureRatchetEnvelopeMissingError(
                current=PostureLevel.PSEUDO, target=PostureLevel.TOOL
            ),
        ]
        for err in errors:
            assert hasattr(err, "user_message")
            assert isinstance(err.user_message, str)
            assert len(err.user_message) > 0
            # No SLIP-0039 / cryptographic jargon should leak to user surfaces.
            assert "SLIP" not in err.user_message
            assert "Argon2" not in err.user_message


# ---------------------------------------------------------------------------
# Step 3e: envelope-present check on ratchet-up (T-02-33)
# ---------------------------------------------------------------------------


class TestStep3eEnvelopeMissingOnRatchetUp:
    """Per `journal/0021-DECISION-t-02-33-envelope-edit-pairing-design.md` +
    `specs/posture-ladder.md` § Ratchet-up #3: ratchet-up MUST emit a
    paired envelope_edit; calling without `envelope=` raises the typed
    error and writes ZERO Ledger entries (no orphan posture_change)."""

    def test_ratchet_up_without_envelope_raises(self):
        gate, led, _rev, sink = _make_gate()
        with pytest.raises(PostureRatchetEnvelopeMissingError) as exc:
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.PSEUDO,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(recomputed=0, stored=0),
                    # envelope omitted — ratchet-up MUST raise
                )
            )
        assert exc.value.current is PostureLevel.PSEUDO
        assert exc.value.target is PostureLevel.TOOL
        # Fail-closed: zero Ledger appends, zero BET-12 emissions.
        assert led.appends == []
        assert sink.writes == []

    def test_ratchet_up_with_envelope_none_raises(self):
        # Same as above but explicitly passing envelope=None — exercises
        # the kwarg-was-passed-but-None path distinctly from kwarg-omitted.
        gate, led, _rev, sink = _make_gate()
        with pytest.raises(PostureRatchetEnvelopeMissingError):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.TOOL,
                    target=PostureLevel.SUPERVISED,
                    evidence=_evidence(recomputed=1, stored=1),
                    envelope=None,
                )
            )
        assert led.appends == []
        assert sink.writes == []

    def test_ratchet_down_with_envelope_none_succeeds(self):
        # Demotion path: envelope=None is legitimate per spec § Ratchet-
        # down lines 47-52. The gate skips Step 5b cleanly.
        gate, led, _rev, sink = _make_gate()
        result = _run(
            gate.request_transition(
                principal_id="agent-test",
                current=PostureLevel.DELEGATING,
                target=PostureLevel.TOOL,
                evidence=_evidence(recomputed=5, stored=5),
                envelope=None,
            )
        )
        assert result.new_level is PostureLevel.TOOL
        # Exactly one Ledger entry — posture_change. No envelope_edit.
        assert len(led.appends) == 1
        assert led.appends[0]["entry_type"] == "posture_change"
        # BET-12 emits on every accepted transition (demotion included).
        assert len(sink.writes) == 1

    def test_ratchet_up_consumes_envelope_exactly_once(self):
        # The gate calls mutate_for_posture_level() ONCE per accepted
        # ratchet-up. Pin the count so a future refactor that
        # accidentally double-mutates fails loudly.
        gate, _led, _rev, _sink = _make_gate()
        envelope = _FakePostureCarryingEnvelope()
        _run(
            gate.request_transition(
                principal_id="agent-test",
                current=PostureLevel.TOOL,
                target=PostureLevel.SUPERVISED,
                evidence=_evidence(recomputed=1, stored=1),
                envelope=envelope,
            )
        )
        assert envelope.mutate_calls == [PostureLevel.SUPERVISED]

    def test_failed_ratchet_up_does_not_consume_envelope(self):
        # Step 1-3 failure on a ratchet-up MUST short-circuit BEFORE
        # mutate_for_posture_level() is called — no envelope mutation
        # on a rejected transition.
        gate, _led, _rev, _sink = _make_gate()
        envelope = _FakePostureCarryingEnvelope()
        with pytest.raises(PostureAuthorshipInsufficientError):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.SUPERVISED,
                    target=PostureLevel.DELEGATING,
                    evidence=_evidence(recomputed=2, stored=2),  # below N=3
                    envelope=envelope,
                )
            )
        # Envelope untouched.
        assert envelope.mutate_calls == []


# ---------------------------------------------------------------------------
# Step 5b trust-boundary invariants (Round 1 /redteam F-2)
# ---------------------------------------------------------------------------


@dataclass
class _MutationOverrideEnvelope:
    """Envelope fake that returns a caller-controlled mutation result.

    Used to exercise the Step 5b trust-boundary invariants: the gate
    consumes mutation fields verbatim into the device-signed Ledger
    entry, so a malicious adapter could try to inject forged values.
    Each test constructs the mutation to violate one invariant and
    asserts the gate raises `PostureEnvelopeMutationInvariantError`.
    """

    envelope_id: str = "sha256:fake-envelope-0001"
    prior_version: int = 1
    prior_content_hash: str = "sha256:fake-prior-content"
    prior_posture_level: str = "PSEUDO"
    forced_mutation: _FakePostureMutationResult | None = None

    def mutate_for_posture_level(self, new_level: PostureLevel) -> _FakePostureMutationResult:
        assert self.forced_mutation is not None, "test must set forced_mutation"
        return self.forced_mutation


class TestStep5bMutationInvariantChecks:
    """Per Round 1 /redteam F-2 (HIGH): Step 5b validates the mutation
    result BEFORE the gate signs the envelope_edit Ledger entry. Without
    these checks, a buggy or malicious `_PostureCarryingEnvelope` adapter
    could inject a swapped envelope_id, a regressed/skipped version, or
    a malformed diff_hash into the device-signed audit trail.

    Each test exercises ONE invariant violation and confirms:
    - `PostureEnvelopeMutationInvariantError` raised with a descriptive
      reason
    - posture_change was already appended at Step 5a (the failure is
      detected BEFORE Step 5b's append — invariant check is the gate
      between mutate and append)
    - envelope_edit is NOT appended
    - BET-12 is NOT emitted (Step 5+ never reached)
    """

    def test_envelope_id_mismatch_raises(self):
        gate, led, _rev, sink = _make_gate()
        envelope = _MutationOverrideEnvelope(envelope_id="sha256:expected-id")
        envelope.forced_mutation = _FakePostureMutationResult(
            envelope_id="sha256:swapped-id",  # different from envelope.envelope_id
            new_version=envelope.prior_version + 1,
            new_content_hash="sha256:fake-new-content",
            diff_hash="sha256:" + ("a" * 64),
            new_posture_level="TOOL",
            new_envelope=object(),
        )
        with pytest.raises(PostureEnvelopeMutationInvariantError) as exc:
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.PSEUDO,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(recomputed=0, stored=0),
                    envelope=envelope,
                )
            )
        assert "envelope_id mismatch" in exc.value.reason
        # posture_change was appended at Step 5a; envelope_edit MUST NOT have landed.
        types = [a["entry_type"] for a in led.appends]
        assert types == ["posture_change"]
        # BET-12 emission is Step 5+ (after envelope_edit); MUST NOT fire.
        assert sink.writes == []

    def test_new_version_regression_raises(self):
        gate, led, _rev, sink = _make_gate()
        envelope = _MutationOverrideEnvelope(prior_version=3)
        envelope.forced_mutation = _FakePostureMutationResult(
            envelope_id=envelope.envelope_id,
            new_version=3,  # equal to prior — version did NOT advance
            new_content_hash="sha256:fake-new-content",
            diff_hash="sha256:" + ("b" * 64),
            new_posture_level="TOOL",
            new_envelope=object(),
        )
        with pytest.raises(PostureEnvelopeMutationInvariantError) as exc:
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.PSEUDO,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(recomputed=0, stored=0),
                    envelope=envelope,
                )
            )
        assert "new_version must be prior_version+1" in exc.value.reason
        types = [a["entry_type"] for a in led.appends]
        assert types == ["posture_change"]
        assert sink.writes == []

    def test_new_version_skip_raises(self):
        gate, led, _rev, sink = _make_gate()
        envelope = _MutationOverrideEnvelope(prior_version=3)
        envelope.forced_mutation = _FakePostureMutationResult(
            envelope_id=envelope.envelope_id,
            new_version=5,  # skipped version 4
            new_content_hash="sha256:fake-new-content",
            diff_hash="sha256:" + ("c" * 64),
            new_posture_level="TOOL",
            new_envelope=object(),
        )
        with pytest.raises(PostureEnvelopeMutationInvariantError) as exc:
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.PSEUDO,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(recomputed=0, stored=0),
                    envelope=envelope,
                )
            )
        assert "new_version must be prior_version+1" in exc.value.reason
        # Confirm the descriptive reason carries both prior and new for triage
        assert "prior=3" in exc.value.reason
        assert "new=5" in exc.value.reason
        types = [a["entry_type"] for a in led.appends]
        assert types == ["posture_change"]
        assert sink.writes == []

    def test_malformed_diff_hash_raises(self):
        gate, led, _rev, sink = _make_gate()
        envelope = _MutationOverrideEnvelope()
        envelope.forced_mutation = _FakePostureMutationResult(
            envelope_id=envelope.envelope_id,
            new_version=envelope.prior_version + 1,
            new_content_hash="sha256:fake-new-content",
            diff_hash="not-a-sha256-hex",  # bypasses canonical shape
            new_posture_level="TOOL",
            new_envelope=object(),
        )
        with pytest.raises(PostureEnvelopeMutationInvariantError) as exc:
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.PSEUDO,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(recomputed=0, stored=0),
                    envelope=envelope,
                )
            )
        assert "diff_hash must match 'sha256:<64-hex>'" in exc.value.reason
        types = [a["entry_type"] for a in led.appends]
        assert types == ["posture_change"]
        assert sink.writes == []

    def test_diff_hash_wrong_prefix_raises(self):
        # `md5:...` / `sha1:...` / unprefixed hex MUST all reject.
        gate, _led, _rev, _sink = _make_gate()
        envelope = _MutationOverrideEnvelope()
        envelope.forced_mutation = _FakePostureMutationResult(
            envelope_id=envelope.envelope_id,
            new_version=envelope.prior_version + 1,
            new_content_hash="sha256:fake-new-content",
            diff_hash="sha1:" + ("d" * 40),  # SHA-1 not accepted
            new_posture_level="TOOL",
            new_envelope=object(),
        )
        with pytest.raises(PostureEnvelopeMutationInvariantError):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.PSEUDO,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(recomputed=0, stored=0),
                    envelope=envelope,
                )
            )

    def test_diff_hash_uppercase_hex_rejected(self):
        # Spec form is lowercase hex; uppercase fails the strict pattern.
        gate, _led, _rev, _sink = _make_gate()
        envelope = _MutationOverrideEnvelope()
        envelope.forced_mutation = _FakePostureMutationResult(
            envelope_id=envelope.envelope_id,
            new_version=envelope.prior_version + 1,
            new_content_hash="sha256:fake-new-content",
            diff_hash="sha256:" + ("A" * 64),  # uppercase rejected
            new_posture_level="TOOL",
            new_envelope=object(),
        )
        with pytest.raises(PostureEnvelopeMutationInvariantError):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.PSEUDO,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(recomputed=0, stored=0),
                    envelope=envelope,
                )
            )

    def test_invariant_error_carries_user_message(self):
        # Plain-language user_message per `rules/communication.md`.
        err = PostureEnvelopeMutationInvariantError(reason="test reason")
        assert hasattr(err, "user_message")
        assert isinstance(err.user_message, str)
        assert len(err.user_message) > 0
        # No internal jargon should leak into the user-facing string.
        assert "envelope_id" not in err.user_message
        assert "diff_hash" not in err.user_message
        assert "sha256" not in err.user_message

    def test_invariant_error_is_posture_gate_error_subclass(self):
        # All gate errors share the base class for surface-side polymorphism.
        from envoy.authorship.posture_gate import PostureGateError

        assert issubclass(PostureEnvelopeMutationInvariantError, PostureGateError)


# ---------------------------------------------------------------------------
# Envelope kwarg structural Protocol check (Round 1 /redteam F-1)
# ---------------------------------------------------------------------------


class TestEnvelopeKwargProtocolCheck:
    """Per Round 1 /redteam F-1 (MED): _PostureCarryingEnvelope is a
    structural Protocol; Python doesn't enforce it at runtime. A caller
    passing a wrong-shape object (string, dict, arbitrary value) would
    otherwise produce a deep AttributeError at Step 5b's mutate call
    site. The kwarg-boundary check converts that into a loud TypeError.

    The check is opt-in for `envelope=None` (legitimate on ratchet-
    down per spec § Ratchet-down lines 47-52). It fires only when a
    non-None value is supplied that doesn't satisfy the Protocol shape.
    """

    def test_string_envelope_raises_type_error(self):
        gate, _led, _rev, _sink = _make_gate()
        with pytest.raises(TypeError, match="envelope must conform"):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.PSEUDO,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(recomputed=0, stored=0),
                    envelope="not-an-envelope",  # type: ignore[arg-type]
                )
            )

    def test_dict_envelope_raises_type_error(self):
        gate, _led, _rev, _sink = _make_gate()
        # A dict has neither attributes nor a callable mutate method.
        with pytest.raises(TypeError, match="envelope must conform"):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.PSEUDO,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(recomputed=0, stored=0),
                    envelope={"envelope_id": "x"},  # type: ignore[arg-type]
                )
            )

    def test_partial_envelope_raises_type_error(self):
        # Object with SOME but not all required attributes still rejects.
        @dataclass
        class _Partial:
            envelope_id: str = "sha256:partial"
            prior_version: int = 1
            # Missing prior_content_hash, prior_posture_level, mutate_*

        gate, _led, _rev, _sink = _make_gate()
        with pytest.raises(TypeError, match="envelope must conform"):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.PSEUDO,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(recomputed=0, stored=0),
                    envelope=_Partial(),  # type: ignore[arg-type]
                )
            )

    def test_envelope_with_non_callable_mutate_raises_type_error(self):
        # Object with mutate_for_posture_level as a non-callable attribute
        # (e.g., a string) MUST be rejected — the gate calls it at Step 5b.
        @dataclass
        class _NonCallableMutate:
            envelope_id: str = "sha256:fake"
            prior_version: int = 1
            prior_content_hash: str = "sha256:prior"
            prior_posture_level: str = "PSEUDO"
            mutate_for_posture_level: str = "not-callable"  # type: ignore[assignment]

        gate, _led, _rev, _sink = _make_gate()
        with pytest.raises(TypeError, match="envelope must conform"):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.PSEUDO,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(recomputed=0, stored=0),
                    envelope=_NonCallableMutate(),  # type: ignore[arg-type]
                )
            )

    def test_envelope_none_accepted_on_ratchet_down(self):
        # envelope=None remains legitimate on demotion paths — the kwarg
        # check skips the Protocol-conformance branch entirely when None.
        gate, led, _rev, _sink = _make_gate()
        result = _run(
            gate.request_transition(
                principal_id="agent-test",
                current=PostureLevel.DELEGATING,
                target=PostureLevel.TOOL,
                evidence=_evidence(recomputed=5, stored=5),
                envelope=None,
            )
        )
        assert result.new_level is PostureLevel.TOOL
        assert len(led.appends) == 1
        assert led.appends[0]["entry_type"] == "posture_change"

    def test_fail_closed_on_kwarg_check(self):
        # Type-check failure fires at the kwarg boundary BEFORE Step 1.
        # No Ledger writes, no BET-12 emissions, no envelope mutation.
        gate, led, _rev, sink = _make_gate()
        with pytest.raises(TypeError, match="envelope must conform"):
            _run(
                gate.request_transition(
                    principal_id="agent-test",
                    current=PostureLevel.PSEUDO,
                    target=PostureLevel.TOOL,
                    evidence=_evidence(recomputed=0, stored=0),
                    envelope=12345,  # type: ignore[arg-type]
                )
            )
        assert led.appends == []
        assert sink.writes == []


# ---------------------------------------------------------------------------
# F-6 closure: metadata.posture_level mint-state read path (audit-only role)
# ---------------------------------------------------------------------------


class TestPostureLevelMintStateRead:
    """F-6 closure: per `specs/envelope-model.md` § Schema field semantics
    for metadata.posture_level, the field is the envelope's mint-time
    audit annotation. No production read consumer dispatches on its value
    (effective-posture derivation walks the Ledger's posture_change
    entries instead). Per `rules/orphan-detection.md` Rule 1, the field
    is structurally non-orphan only if at least one test reads it.

    These tests exercise the read path against the canonical
    `EnvelopeMetadata` shape:

    1. Default mint-state at first envelope is "PSEUDO" per
       `specs/envelope-model.md` § Schema field semantics.
    2. Mint-state minted via `EnvelopeMetadata(posture_level=...)`
       round-trips byte-stably (the spec value IS the stored value).
    3. The field is part of the metadata.posture_level wire form per
       `specs/envelope-model.md` line 34 ("PSEUDO | TOOL | SUPERVISED
       | DELEGATING | AUTONOMOUS").

    The tests do NOT exercise any production dispatch logic against the
    field (because none exists per the documented audit-only role); they
    exercise the read access so the field is reachable from at least one
    test and is therefore not structurally orphan.
    """

    def test_default_posture_level_is_pseudo(self):
        from envoy.envelope import EnvelopeMetadata

        metadata = EnvelopeMetadata()
        # Default mint-state per `specs/envelope-model.md` field semantics
        # — Boundary Conversation first entry is PSEUDO.
        assert metadata.posture_level == "PSEUDO"

    def test_mint_state_round_trips(self):
        from envoy.envelope import EnvelopeMetadata

        # Each canonical posture level can be set as a mint-state value
        # and read back unchanged. The dataclass is frozen — the read
        # path is what audit consumers (Tier 03+ verifiers per spec
        # field-semantics) use to cross-check against Ledger entries.
        for name in ("PSEUDO", "TOOL", "SUPERVISED", "DELEGATING", "AUTONOMOUS"):
            metadata = EnvelopeMetadata(posture_level=name)
            assert metadata.posture_level == name

    def test_mint_state_matches_canonical_posture_level_enum(self):
        # The field's wire form per `specs/envelope-model.md` line 34
        # MUST match the canonical `PostureLevel` enum names — pinning
        # this cross-checks the spec wire form against the Python enum
        # and surfaces drift if either side renames.
        from envoy.envelope import EnvelopeMetadata

        canonical_names = {p.name for p in PostureLevel}
        for level in PostureLevel:
            metadata = EnvelopeMetadata(posture_level=level.name)
            assert metadata.posture_level in canonical_names
            assert metadata.posture_level == level.name
