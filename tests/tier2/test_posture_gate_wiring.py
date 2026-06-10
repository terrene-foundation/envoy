"""Tier 2: T-02-33 — PostureGate facade-manager wiring + envelope_edit pairing.

Source: T-02-33 per `02-wave-2-authorship-shamir-boundary.md` line 78 +
`journal/0020-DECISION-envelope-edit-deferred-to-tier-2.md` (the deferral
this shard closes) + `journal/0021-DECISION-t-02-33-envelope-edit-pairing-design.md`
(the DI design choice this shard commits to: envelope-kwarg approach).

Phase 01 narrow scope: this file holds the Tier 2 wiring tests that
exercise PostureGate against real infrastructure — real `EnvoyLedger`
(over real `InMemoryAuditStore` + real Ed25519), real `TrustVault`
(Argon2id + AES-256-GCM, via the `unlocked_vault` fixture from
conftest.py), and a real Trust-store-aware revoke hook adapter.

Per `rules/testing.md` Tier 2 contract: real infrastructure throughout;
NO mocking (`@patch`, `MagicMock`, `unittest.mock` — BLOCKED). The
`_PostureCarryingEnvelope` adapter (`_EnvelopeConfigPostureCarrier`)
wraps the real `EnvelopeConfig` produced by the real `EnvelopeCompiler`;
the adapter's `mutate_for_posture_level()` re-uses the real canonical-bytes
pipeline so the new envelope is byte-stable through the same
canonicalization path the production envelope chain uses.

The acceptance bullets from § T-02-33 (per the carry-forward block at
line 88 of the wave-2 todo):

  (a) on every ratchet-up, BOTH a `posture_change` entry AND a paired
      `envelope_edit` entry are appended in order;
  (b) the `envelope_edit` carries the new envelope's `diff_hash` (per
      `specs/ledger.md` § envelope_edit lines 107-114 — the spec calls
      it `diff_hash`, NOT `content_hash`) AND a `new_version` that is
      exactly one greater than `prior_version`;
  (c) the envelope's `metadata.posture_level` field reflects the new
      level after the mutation.

Plus one negative case (Step 3d failure): insufficient authorship MUST
emit NEITHER `posture_change` NOR `envelope_edit` — the existing
fail-closed contract extends symmetrically to the new pairing (no orphan
envelope_edit can land without its posture_change sibling, and vice
versa).
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass, field
from typing import Any

import pytest

from envoy.authorship import (
    BET12CadenceEmitter,
    BET12CadencePayload,
    PostureAuthorshipInsufficientError,
    PostureChangeResult,
    PostureEnvelopeMutationInvariantError,
    PostureEvidence,
    PostureGate,
    PostureLevel,
    PostureMode,
)
from envoy.envelope import (
    EnvelopeCompiler,
    EnvelopeConfig,
    EnvelopeConfigInput,
    EnvelopeMetadata,
    LocalTemplateResolver,
    canonical_bytes,
    content_hash,
)
from envoy.ledger import EnvoyLedger

# ---------------------------------------------------------------------------
# Tier 2 adapters — real-collaborator shims that keep the test file
# self-contained but exercise the same code paths production will use.
# ---------------------------------------------------------------------------


class _TrustStoreRevokeHookAdapter:
    """Minimal Trust-store-revoke hook adapter for the Tier 2 wiring test.

    PostureGate's `_RevokeHook` Protocol signature is
    `async def __call__(*, agent_id, reason, revoked_by) -> object`.
    Phase 01 ratchet-up tests never exercise the demotion path so the
    adapter is a recorder, not a forwarder; ratchet-down tests in this
    file (see `TestPostureChangeOnRatchetDownNoEnvelopeEdit`) exercise it
    against the recorded calls.

    Tier 2 contract (NO mocking): this is a REAL adapter — it owns its
    own state, raises on invalid inputs, and is verified by the test's
    external assertions, not by mock.assert_called_*.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    async def __call__(self, *, agent_id: str, reason: str, revoked_by: str) -> object:
        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError("agent_id must be non-empty str")
        self.calls.append({"agent_id": agent_id, "reason": reason, "revoked_by": revoked_by})
        return object()


@dataclass
class _RecordingBET12Sink:
    """Real BET-12 sink — records cadence payloads for assertion.

    Per `tests/tier1/test_posture_gate_5_step_fail_closed.py` the BET-12
    emit fires at Step 5+ (after Ledger). Tier 2 verifies the emit lands
    AFTER both the posture_change entry AND the envelope_edit entry are
    appended (relative ordering pins).
    """

    writes: list[BET12CadencePayload] = field(default_factory=list)

    async def write(self, payload: BET12CadencePayload) -> None:
        self.writes.append(payload)


# Compiler scaffolding — real EnvelopeCompiler against a local template
# resolver. Tier 2 contract: the compiler IS real; the resolver root is
# a tmp directory the test never reads from (no templates referenced).


def _make_compiler(tmp_root) -> EnvelopeCompiler:
    """Construct a real EnvelopeCompiler with real canonical-bytes pipeline."""
    return EnvelopeCompiler(template_resolver=LocalTemplateResolver(tmp_root))


def _compile_envelope(
    compiler: EnvelopeCompiler,
    *,
    principal_id: str = "principal-test",
    initial_posture_level: PostureLevel = PostureLevel.PSEUDO,
) -> EnvelopeConfig:
    """Compile a fresh envelope at posture_level=<initial> via the real pipeline.

    The compiled envelope has a real uuid-v4 envelope_id, real canonical_bytes,
    real content_hash via SHA-256 over the JCS-RFC8785 canonical form.
    """
    metadata = EnvelopeMetadata(posture_level=initial_posture_level.name)
    config_input = EnvelopeConfigInput(metadata=metadata)
    return compiler.compile(config_input, principal_id=principal_id)


@dataclass
class _PostureMutationOutcome:
    """The shape PostureGate consumes from `mutate_for_posture_level()`.

    Mirrors the Protocol `_PostureMutationResult` PostureGate declares.
    Carried as a dataclass here for test-side readability; the production
    Protocol is structural so any same-shaped object satisfies it.

    `envelope_id` mirrors the source envelope's id; PostureGate verifies
    the match at Step 5b per Round 1 /redteam F-2 trust-boundary invariant.
    """

    envelope_id: str
    new_version: int
    new_content_hash: str
    diff_hash: str
    new_posture_level: str
    new_envelope: Any  # the mutated EnvelopeConfig


class _EnvelopeConfigPostureCarrier:
    """Adapter wrapping a real `EnvelopeConfig` to satisfy the PostureGate
    `_PostureCarryingEnvelope` Protocol.

    Per `journal/0021-DECISION-t-02-33-envelope-edit-pairing-design.md` § "What lands
    in this shard", the adapter owns the recompute math; PostureGate stays out of it.

    Mutation semantics:
    - new_version = prior_version + 1 (monotonic bump per
      `specs/envelope-model.md` § metadata.algorithm_identifier).
    - new posture_level overwrites metadata.posture_level (per
      `specs/posture-ladder.md` line 41 + the wave-2 todo § T-02-33
      acceptance bullet (c)).
    - new_content_hash = canonical_bytes pipeline over the mutated envelope
      (real pipeline; not a stub).
    - diff_hash = sha256(canonical(prior) || canonical(new)) per
      `specs/ledger.md` § envelope_edit (the spec doesn't fix the exact
      diff_hash computation; this adapter picks a content-addressable
      transition hash, which is the same shape envelope-version-chain
      verifiers consume).
    """

    def __init__(self, envelope: EnvelopeConfig, compiler: EnvelopeCompiler) -> None:
        self._envelope = envelope
        self._compiler = compiler

    @property
    def envelope_id(self) -> str:
        return self._envelope.metadata.envelope_id

    @property
    def prior_version(self) -> int:
        return self._envelope.envelope_version

    @property
    def prior_content_hash(self) -> str:
        return self._envelope.content_hash

    @property
    def prior_posture_level(self) -> str:
        return self._envelope.metadata.posture_level

    def mutate_for_posture_level(self, new_level: PostureLevel) -> _PostureMutationOutcome:
        """Mint a new EnvelopeConfig with bumped version + updated posture_level.

        Uses `dataclasses.replace` on the frozen `EnvelopeMetadata` and
        `EnvelopeConfig` (both `frozen=True` per L-03 shard B). The
        canonical_bytes pipeline is the same one the real EnvelopeCompiler
        uses (`envoy.envelope.canonical_bytes`).
        """
        if not isinstance(new_level, PostureLevel):
            raise TypeError(f"new_level must be PostureLevel, got {type(new_level).__name__}")
        new_version = self._envelope.envelope_version + 1
        new_metadata = dataclasses.replace(self._envelope.metadata, posture_level=new_level.name)
        # Recompute canonical_bytes + content_hash via the same pipeline
        # the compiler uses. Inline the payload shape from
        # envoy/envelope/compiler.py::_to_canonical_payload.
        payload = self._to_canonical_payload(
            schema_version=self._envelope.schema_version,
            envelope_version=new_version,
            metadata=new_metadata,
        )
        new_canonical = canonical_bytes(payload)
        new_content_hash = content_hash(new_canonical)
        new_envelope = dataclasses.replace(
            self._envelope,
            envelope_version=new_version,
            metadata=new_metadata,
            canonical_bytes=new_canonical,
            content_hash=new_content_hash,
        )
        # diff_hash binds prior + new canonical bytes — what an envelope-chain
        # verifier needs to walk the chain.
        diff_hash = (
            "sha256:" + hashlib.sha256(self._envelope.canonical_bytes + new_canonical).hexdigest()
        )
        return _PostureMutationOutcome(
            envelope_id=self._envelope.metadata.envelope_id,
            new_version=new_version,
            new_content_hash=new_content_hash,
            diff_hash=diff_hash,
            new_posture_level=new_level.name,
            new_envelope=new_envelope,
        )

    def _to_canonical_payload(
        self, *, schema_version: str, envelope_version: int, metadata: EnvelopeMetadata
    ) -> dict[str, Any]:
        """Build the JCS-input dict from the mutated envelope.

        Same fields as `envoy.envelope.compiler.EnvelopeCompiler._to_canonical_payload`
        so the canonical bytes are byte-identical to what the compiler would
        produce for the same logical envelope.
        """
        from dataclasses import asdict
        from enum import Enum

        def _enum_safe(value: Any) -> Any:
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, dict):
                return {k: _enum_safe(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_enum_safe(v) for v in value]
            if isinstance(value, tuple):
                return [_enum_safe(v) for v in value]
            return value

        env = self._envelope
        return {
            "schema_version": schema_version,
            "envelope_version": envelope_version,
            "metadata": _enum_safe(asdict(metadata)),
            "financial": _enum_safe(asdict(env.financial)),
            "operational": _enum_safe(asdict(env.operational)),
            "temporal": _enum_safe(asdict(env.temporal)),
            "data_access": _enum_safe(asdict(env.data_access)),
            "communication": _enum_safe(asdict(env.communication)),
            "composition_rules": [_enum_safe(asdict(r)) for r in env.composition_rules],
            "cross_domain_rules_authored": [
                _enum_safe(asdict(r)) for r in env.cross_domain_rules_authored
            ],
            "tool_output_budget_bytes": env.tool_output_budget_bytes,
            "semantic_checks": _enum_safe(asdict(env.semantic_checks)),
        }


# ---------------------------------------------------------------------------
# Test-scope helpers
# ---------------------------------------------------------------------------


def _make_gate_and_collaborators(
    envoy_ledger: EnvoyLedger,
) -> tuple[PostureGate, _TrustStoreRevokeHookAdapter, _RecordingBET12Sink, BET12CadenceEmitter]:
    """Construct a PostureGate over real collaborators.

    Tier 2 contract per `rules/testing.md`: real `EnvoyLedger`, real
    Ed25519 signing via `signing_keymgr` (already wired through
    `envoy_ledger` fixture), real BET-12 emitter wrapping a recording
    sink (the sink IS real — observes the writes, does not mock).
    """
    revoke = _TrustStoreRevokeHookAdapter()
    sink = _RecordingBET12Sink()
    emitter = BET12CadenceEmitter(sink=sink)
    gate = PostureGate(ledger=envoy_ledger, revoke_hook=revoke, bet12_emitter=emitter)
    return gate, revoke, sink, emitter


def _evidence(
    *,
    recomputed: int,
    mode: PostureMode = PostureMode.PERSONAL,
    envelope_id_hash: str = "sha256:tier2-envelope",
) -> PostureEvidence:
    return PostureEvidence(
        authorship_score_recomputed=recomputed,
        authorship_score_stored=recomputed,
        mode=mode,
        genesis_signed_grant=True,
        cooling_off_active=False,
        envelope_id_hash=envelope_id_hash,
    )


async def _read_appended_entries(ledger: EnvoyLedger) -> list[dict[str, Any]]:
    """Read every entry appended to the real Ledger.

    Real `EnvoyLedger` doesn't expose a list method directly. The path
    we take through `export()` is the canonical reader surface BUT
    `EnvoyLedger.export()` refuses on an empty ledger (`LedgerError:
    cannot export an empty ledger`). Per Tier 2 contract (no mocking,
    observe through real surfaces), we observe via the kailash
    `audit_store.query()` adapter the ledger writes through. Empty
    result = zero appends; non-empty = entries appended in order.

    The shape returned by `audit_store.query()` is the kailash
    `AuditEvent` form; we re-derive the envoy `{type, content}` shape
    a verifier would see by reading `event.metadata['_envoy_envelope_v1']`
    (the sentinel under which `EnvoyLedger.append` persists the full
    envoy envelope per `envoy/ledger/facade.py::_ENVELOPE_METADATA_KEY`).
    """
    from kailash.trust.audit_store import AuditFilter

    # `_audit_store` is set at EnvoyLedger.__init__; the underscore is
    # not a security shield, just a "stable surface for the facade
    # only" convention. Tier 2 wiring is the legitimate observer surface
    # for the audit-store-level entries the facade emits.
    events = await ledger._audit_store.query(AuditFilter(limit=1000))
    entries: list[dict[str, Any]] = []
    for ev in events:
        meta = ev.metadata or {}
        envoy_envelope = meta.get("_envoy_envelope_v1")
        if envoy_envelope is None:
            # Skip non-envoy events (kailash internal). Phase 01 narrow
            # scope: every envoy.ledger entry carries the sentinel.
            continue
        entries.append(envoy_envelope)
    return entries


# ---------------------------------------------------------------------------
# Positive cases: paired posture_change + envelope_edit on ratchet-up
# ---------------------------------------------------------------------------


class TestEnvelopeEditPairingOnRatchetUp:
    """Acceptance for T-02-33 per the wave-2 todo § T-02-33 carry-forward block.

    Every ratchet-up MUST emit BOTH a `posture_change` entry AND a paired
    `envelope_edit` entry, in that order. The envelope_edit carries
    `prior_version`, `new_version=prior+1`, `diff_hash` (per
    `specs/ledger.md` § envelope_edit lines 107-114). The mutated
    envelope's `metadata.posture_level` reflects the new level.
    """

    async def test_pseudo_to_tool_emits_paired_entries(
        self, envoy_ledger: EnvoyLedger, tmp_path
    ) -> None:
        """PSEUDO → TOOL (single-step, N=0). Lowest threshold; default
        Phase 01 entry transition."""
        gate, _revoke, sink, _emitter = _make_gate_and_collaborators(envoy_ledger)
        compiler = _make_compiler(tmp_path)
        envelope = _compile_envelope(
            compiler, principal_id="alice", initial_posture_level=PostureLevel.PSEUDO
        )
        carrier = _EnvelopeConfigPostureCarrier(envelope, compiler)
        prior_version = carrier.prior_version
        prior_content_hash = carrier.prior_content_hash
        envelope_id = carrier.envelope_id

        result = await gate.request_transition(
            principal_id="alice",
            current=PostureLevel.PSEUDO,
            target=PostureLevel.TOOL,
            evidence=_evidence(recomputed=0),
            envelope=carrier,
        )

        # Success result
        assert isinstance(result, PostureChangeResult)
        assert result.new_level is PostureLevel.TOOL
        assert isinstance(result.ledger_entry_id, str)
        assert result.ledger_entry_id.startswith("sha256:")

        # Acceptance (a): BOTH entries appended in order
        entries = await _read_appended_entries(envoy_ledger)
        assert (
            len(entries) == 2
        ), f"expected paired posture_change + envelope_edit; got {len(entries)} entries"
        posture_entry, envelope_entry = entries[0], entries[1]
        assert posture_entry["type"] == "posture_change"
        assert envelope_entry["type"] == "envelope_edit"

        # posture_change content: spec lines 243-253
        posture_content = posture_entry["content"]
        assert posture_content["from_posture"] == "PSEUDO"
        assert posture_content["to_posture"] == "TOOL"
        assert posture_content["signed_by"] == "genesis_key"

        # Acceptance (b): envelope_edit wire shape per specs/ledger.md L107-114.
        # The outer envelope `type` is already pinned to `"envelope_edit"`
        # by the entry_type=... arg at EnvoyLedger.append; the inner
        # `content` carries the spec's per-type fields (schema_version,
        # envelope_id, prior_version, new_version, diff_hash,
        # rollback_grace_window_seconds, signed_by).
        envelope_content = envelope_entry["content"]
        assert envelope_content["schema_version"] == "1.0"
        assert envelope_content["envelope_id"] == envelope_id
        assert envelope_content["prior_version"] == prior_version
        assert envelope_content["new_version"] == prior_version + 1
        assert envelope_content["new_version"] == envelope_content["prior_version"] + 1
        assert envelope_content["signed_by"] == "delegation_key"
        # diff_hash is the spec-named field (NOT content_hash); SHA-256 form
        assert "diff_hash" in envelope_content
        assert envelope_content["diff_hash"].startswith("sha256:")
        assert envelope_content["diff_hash"] != prior_content_hash
        assert "rollback_grace_window_seconds" in envelope_content
        assert isinstance(envelope_content["rollback_grace_window_seconds"], int)

        # BET-12 emitted exactly once after both entries
        assert len(sink.writes) == 1
        payload = sink.writes[0]
        assert payload.from_level is PostureLevel.PSEUDO
        assert payload.to_level is PostureLevel.TOOL

    async def test_tool_to_supervised_emits_paired_entries(
        self, envoy_ledger: EnvoyLedger, tmp_path
    ) -> None:
        """TOOL → SUPERVISED (single-step, N=1; mid-threshold transition)."""
        gate, _revoke, _sink, _emitter = _make_gate_and_collaborators(envoy_ledger)
        compiler = _make_compiler(tmp_path)
        envelope = _compile_envelope(
            compiler, principal_id="bob", initial_posture_level=PostureLevel.TOOL
        )
        carrier = _EnvelopeConfigPostureCarrier(envelope, compiler)
        prior_version = carrier.prior_version

        result = await gate.request_transition(
            principal_id="bob",
            current=PostureLevel.TOOL,
            target=PostureLevel.SUPERVISED,
            evidence=_evidence(recomputed=1),
            envelope=carrier,
        )

        assert result.new_level is PostureLevel.SUPERVISED

        entries = await _read_appended_entries(envoy_ledger)
        assert len(entries) == 2
        assert entries[0]["type"] == "posture_change"
        assert entries[1]["type"] == "envelope_edit"
        env_content = entries[1]["content"]
        assert env_content["prior_version"] == prior_version
        assert env_content["new_version"] == prior_version + 1
        # Acceptance (c): the mutated envelope carries the new posture level.
        # We verify this via the carrier — production callers consume the
        # mutated envelope via the same surface PostureGate calls.
        mutation = carrier.mutate_for_posture_level(PostureLevel.SUPERVISED)
        assert mutation.new_posture_level == "SUPERVISED"
        assert mutation.new_envelope.metadata.posture_level == "SUPERVISED"

    async def test_pseudo_to_delegating_multi_step_emits_paired_entries(
        self, envoy_ledger: EnvoyLedger, tmp_path
    ) -> None:
        """PSEUDO → DELEGATING (multi-step path; exercises highest-on-path
        threshold branch in `_required_authorship`).

        Per `envoy/authorship/posture_gate.py::_required_authorship`, the
        multi-step PSEUDO → DELEGATING transition requires the highest
        single-step threshold along the path — N=3 personal. The
        envelope_edit on this transition is the same shape as single-step
        (no per-step intermediate envelope_edits).
        """
        gate, _revoke, _sink, _emitter = _make_gate_and_collaborators(envoy_ledger)
        compiler = _make_compiler(tmp_path)
        envelope = _compile_envelope(
            compiler, principal_id="carol", initial_posture_level=PostureLevel.PSEUDO
        )
        carrier = _EnvelopeConfigPostureCarrier(envelope, compiler)
        prior_version = carrier.prior_version

        result = await gate.request_transition(
            principal_id="carol",
            current=PostureLevel.PSEUDO,
            target=PostureLevel.DELEGATING,
            evidence=_evidence(recomputed=3),  # N=3 personal multi-step threshold
            envelope=carrier,
        )

        assert result.new_level is PostureLevel.DELEGATING

        entries = await _read_appended_entries(envoy_ledger)
        assert len(entries) == 2
        # Outer envelope `type` field is the canonical pin
        assert entries[0]["type"] == "posture_change"
        assert entries[1]["type"] == "envelope_edit"
        posture_content = entries[0]["content"]
        envelope_content = entries[1]["content"]
        assert posture_content["from_posture"] == "PSEUDO"
        assert posture_content["to_posture"] == "DELEGATING"
        # Multi-step transition emits ONE envelope_edit with a single
        # version bump (NOT three intermediate edits).
        assert envelope_content["new_version"] == prior_version + 1

        # Verify the mutated envelope reflects the FINAL level (DELEGATING),
        # not an intermediate (TOOL or SUPERVISED).
        mutation = carrier.mutate_for_posture_level(PostureLevel.DELEGATING)
        assert mutation.new_posture_level == "DELEGATING"
        assert mutation.new_envelope.metadata.posture_level == "DELEGATING"

    async def test_envelope_edit_content_hash_changes_on_mutation(
        self, envoy_ledger: EnvoyLedger, tmp_path
    ) -> None:
        """The mutated envelope's content_hash differs from prior — the
        canonical bytes change because metadata.posture_level changed,
        and SHA-256 propagates that change through the chain."""
        gate, _revoke, _sink, _emitter = _make_gate_and_collaborators(envoy_ledger)
        compiler = _make_compiler(tmp_path)
        envelope = _compile_envelope(
            compiler, principal_id="dan", initial_posture_level=PostureLevel.PSEUDO
        )
        carrier = _EnvelopeConfigPostureCarrier(envelope, compiler)
        prior_content_hash = carrier.prior_content_hash

        await gate.request_transition(
            principal_id="dan",
            current=PostureLevel.PSEUDO,
            target=PostureLevel.TOOL,
            evidence=_evidence(recomputed=0),
            envelope=carrier,
        )

        # Recompute the mutation to verify new content_hash != prior.
        mutation = carrier.mutate_for_posture_level(PostureLevel.TOOL)
        assert mutation.new_content_hash != prior_content_hash
        # diff_hash is distinct from new_content_hash (different inputs).
        assert mutation.diff_hash != mutation.new_content_hash
        assert mutation.diff_hash != prior_content_hash


# ---------------------------------------------------------------------------
# Negative case: ratchet-up that fails Step 3d MUST emit NEITHER entry
# ---------------------------------------------------------------------------


class TestFailedRatchetUpEmitsNeitherEntry:
    """Fail-closed pairing invariant: if any Step 1-4 fails on a ratchet-up,
    NEITHER `posture_change` NOR `envelope_edit` lands. The pairing is
    atomic from the Ledger's perspective — no orphan envelope_edit can
    surface without its posture_change sibling, and vice versa.

    This negative case extends the existing Step 5 fail-closed contract
    (T-02-31 lines 437-487 in tier1/test_posture_gate_5_step_fail_closed.py)
    symmetrically to the new pairing.
    """

    async def test_insufficient_authorship_emits_neither_entry(
        self, envoy_ledger: EnvoyLedger, tmp_path
    ) -> None:
        """Step 3d failure (authorship below threshold) on a ratchet-up
        MUST raise the typed error AND leave the Ledger untouched —
        zero entries appended, real persistence layer untouched."""
        gate, _revoke, sink, _emitter = _make_gate_and_collaborators(envoy_ledger)
        compiler = _make_compiler(tmp_path)
        envelope = _compile_envelope(
            compiler, principal_id="erin", initial_posture_level=PostureLevel.SUPERVISED
        )
        carrier = _EnvelopeConfigPostureCarrier(envelope, compiler)

        # SUPERVISED → DELEGATING personal requires N=3; supplying 2 fails.
        with pytest.raises(PostureAuthorshipInsufficientError) as exc:
            await gate.request_transition(
                principal_id="erin",
                current=PostureLevel.SUPERVISED,
                target=PostureLevel.DELEGATING,
                evidence=_evidence(recomputed=2),
                envelope=carrier,
            )
        assert exc.value.need == 3
        assert exc.value.have == 2

        # Acceptance: NEITHER entry appended.
        entries = await _read_appended_entries(envoy_ledger)
        assert entries == [], (
            f"fail-closed broken — appended {len(entries)} entries on a failed "
            f"ratchet-up; got types {[e['type'] for e in entries]}"
        )
        # BET-12 also did not emit (Step 5+ runs only on accepted transitions).
        assert sink.writes == []


# ---------------------------------------------------------------------------
# F-2 mutation invariant violation emits NEITHER entry (R2-F1 closure)
# ---------------------------------------------------------------------------


class _ForgedMutationCarrier:
    """Adapter that satisfies `_PostureCarryingEnvelope` but returns a
    caller-controlled (forged) mutation result. Used to drive the
    F-2 trust-boundary invariants through the real Ledger end-to-end.

    Tier 2 contract per `rules/testing.md` § Tier 2 (no mocking via
    `@patch`/`MagicMock`): this is a REAL adapter — a malicious-shape
    `_PostureCarryingEnvelope` implementation purpose-built to exercise
    the precondition gate. The mutation it returns is whatever the test
    constructed; the gate's F-2 invariants reject it. The acceptance
    bullets are external (real Ledger reads), not mock-assertion-style.
    """

    def __init__(
        self,
        *,
        envelope_id: str,
        prior_version: int,
        prior_content_hash: str,
        prior_posture_level: str,
        forged_mutation: _PostureMutationOutcome,
    ) -> None:
        self._envelope_id = envelope_id
        self._prior_version = prior_version
        self._prior_content_hash = prior_content_hash
        self._prior_posture_level = prior_posture_level
        self._forged_mutation = forged_mutation

    @property
    def envelope_id(self) -> str:
        return self._envelope_id

    @property
    def prior_version(self) -> int:
        return self._prior_version

    @property
    def prior_content_hash(self) -> str:
        return self._prior_content_hash

    @property
    def prior_posture_level(self) -> str:
        return self._prior_posture_level

    def mutate_for_posture_level(self, new_level: PostureLevel) -> _PostureMutationOutcome:
        return self._forged_mutation


class TestF2InvariantViolationEmitsNeitherEntry:
    """Per Round 2 /redteam Finding R2-F1 (HIGH): the F-2 mutation
    invariants run as PRECONDITIONS, BEFORE Step 5a's posture_change
    append. On any invariant violation, ZERO Ledger entries land —
    the application-level paired-emission contract is atomic and
    fail-closed.

    This class exercises the contract end-to-end against the REAL
    `EnvoyLedger` (real device-signed entries, real audit store): a
    forged mutation that violates one of the three invariants
    (envelope_id mismatch / new_version drift / malformed diff_hash)
    MUST raise `PostureEnvelopeMutationInvariantError` AND leave the
    Ledger untouched.

    The R2-F1 regression that motivates this case shipped on PR #25
    Shard 1: the F-2 invariant raises landed BETWEEN Step 5a's append
    and Step 5b's append, so any invariant violation committed an
    orphan posture_change to the Ledger. Per
    `rules/zero-tolerance.md` Rule 3 (no silent fallbacks) the orphan
    is a contract-level failure. This Tier 2 case pins the closure
    against real persistence so the FFI/Ledger path is exercised, not
    just the in-memory Tier 1 fake.

    Note: this case addresses APPLICATION-level invariant violations.
    TRANSIENT Ledger failures BETWEEN Step 5a and Step 5b (the F-001
    follow-up at issue #24) are a distinct bug class requiring
    Ledger-level transactional support.
    """

    async def test_envelope_id_mismatch_emits_neither_entry(
        self, envoy_ledger: EnvoyLedger, tmp_path
    ) -> None:
        """F-2 invariant: mutation.envelope_id MUST match the source
        envelope's envelope_id. A swapped id fires the precondition
        check BEFORE Step 5a — zero Ledger entries land."""
        gate, _revoke, sink, _emitter = _make_gate_and_collaborators(envoy_ledger)
        # Forge a mutation whose envelope_id does NOT match the carrier's.
        forged = _PostureMutationOutcome(
            envelope_id="sha256:forged-swapped-id",
            new_version=2,
            new_content_hash="sha256:forged-new-content",
            diff_hash="sha256:" + ("a" * 64),
            new_posture_level="TOOL",
            new_envelope=object(),
        )
        carrier = _ForgedMutationCarrier(
            envelope_id="sha256:authentic-envelope",
            prior_version=1,
            prior_content_hash="sha256:authentic-prior",
            prior_posture_level="PSEUDO",
            forged_mutation=forged,
        )

        with pytest.raises(PostureEnvelopeMutationInvariantError) as exc:
            await gate.request_transition(
                principal_id="agent-r2f1-id-mismatch",
                current=PostureLevel.PSEUDO,
                target=PostureLevel.TOOL,
                evidence=_evidence(recomputed=0),
                envelope=carrier,
            )
        assert "envelope_id mismatch" in exc.value.reason

        # R2-F1 contract: zero Ledger entries landed. The orphan
        # posture_change pattern this fix closes would have shown up
        # here as `len(entries) == 1` with type == "posture_change".
        entries = await _read_appended_entries(envoy_ledger)
        assert entries == [], (
            "R2-F1 fail-closed broken on real Ledger — forged-mutation "
            f"violation appended {len(entries)} entries (types "
            f"{[e['type'] for e in entries]}); precondition gate must "
            "preempt any append on invariant violation."
        )
        assert sink.writes == []

    async def test_new_version_drift_emits_neither_entry(
        self, envoy_ledger: EnvoyLedger, tmp_path
    ) -> None:
        """F-2 invariant: mutation.new_version MUST equal prior_version
        + 1. A regression / skip fires the precondition check BEFORE
        Step 5a — zero Ledger entries land."""
        gate, _revoke, sink, _emitter = _make_gate_and_collaborators(envoy_ledger)
        # Forge a mutation that skips version 4 (prior=3, new=5).
        forged = _PostureMutationOutcome(
            envelope_id="sha256:authentic-envelope",
            new_version=5,  # skipped 4
            new_content_hash="sha256:forged-new-content",
            diff_hash="sha256:" + ("b" * 64),
            new_posture_level="TOOL",
            new_envelope=object(),
        )
        carrier = _ForgedMutationCarrier(
            envelope_id="sha256:authentic-envelope",
            prior_version=3,
            prior_content_hash="sha256:authentic-prior",
            prior_posture_level="PSEUDO",
            forged_mutation=forged,
        )

        with pytest.raises(PostureEnvelopeMutationInvariantError) as exc:
            await gate.request_transition(
                principal_id="agent-r2f1-version-drift",
                current=PostureLevel.PSEUDO,
                target=PostureLevel.TOOL,
                evidence=_evidence(recomputed=0),
                envelope=carrier,
            )
        assert "new_version must be prior_version+1" in exc.value.reason

        entries = await _read_appended_entries(envoy_ledger)
        assert entries == [], (
            "R2-F1 fail-closed broken on real Ledger — version-drift "
            f"violation appended {len(entries)} entries (types "
            f"{[e['type'] for e in entries]})."
        )
        assert sink.writes == []

    async def test_malformed_diff_hash_emits_neither_entry(
        self, envoy_ledger: EnvoyLedger, tmp_path
    ) -> None:
        """F-2 invariant: mutation.diff_hash MUST match `sha256:<64-hex>`.
        A malformed hash fires the precondition check BEFORE Step 5a —
        zero Ledger entries land."""
        gate, _revoke, sink, _emitter = _make_gate_and_collaborators(envoy_ledger)
        # Forge a mutation with a malformed diff_hash (wrong algorithm
        # prefix, invalid hex shape).
        forged = _PostureMutationOutcome(
            envelope_id="sha256:authentic-envelope",
            new_version=2,
            new_content_hash="sha256:forged-new-content",
            diff_hash="md5:not-a-canonical-sha256",
            new_posture_level="TOOL",
            new_envelope=object(),
        )
        carrier = _ForgedMutationCarrier(
            envelope_id="sha256:authentic-envelope",
            prior_version=1,
            prior_content_hash="sha256:authentic-prior",
            prior_posture_level="PSEUDO",
            forged_mutation=forged,
        )

        with pytest.raises(PostureEnvelopeMutationInvariantError) as exc:
            await gate.request_transition(
                principal_id="agent-r2f1-malformed-hash",
                current=PostureLevel.PSEUDO,
                target=PostureLevel.TOOL,
                evidence=_evidence(recomputed=0),
                envelope=carrier,
            )
        assert "diff_hash must match 'sha256:<64-hex>'" in exc.value.reason

        entries = await _read_appended_entries(envoy_ledger)
        assert entries == [], (
            "R2-F1 fail-closed broken on real Ledger — diff_hash "
            f"violation appended {len(entries)} entries (types "
            f"{[e['type'] for e in entries]})."
        )
        assert sink.writes == []


# ---------------------------------------------------------------------------
# Ratchet-down does NOT emit envelope_edit (asymmetric pairing per spec)
# ---------------------------------------------------------------------------


class TestPostureChangeOnRatchetDownNoEnvelopeEdit:
    """Per `specs/posture-ladder.md` § Ratchet-down lines 47-52: demotion
    "is always permitted, always Genesis-signed, always a `posture_change`
    entry". The spec calls out `posture_change` specifically and does NOT
    mention envelope_edit on demotion. Interpretation per
    `journal/0021-DECISION-...md` § "For Discussion" #2: the spec's pairing
    is asymmetric — envelope_edit pairs with ratchet-up only.

    This class pins the asymmetry so a future refactor that "symmetrizes"
    the pairing without a spec edit fails loudly.
    """

    async def test_ratchet_down_emits_only_posture_change(
        self, envoy_ledger: EnvoyLedger, tmp_path
    ) -> None:
        gate, revoke, sink, _emitter = _make_gate_and_collaborators(envoy_ledger)
        # Ratchet-down doesn't need envelope=... (and the gate doesn't
        # require it on demotion paths). Pass None to verify the gate
        # cleanly skips Step 5b.
        result = await gate.request_transition(
            principal_id="frank",
            current=PostureLevel.DELEGATING,
            target=PostureLevel.TOOL,
            evidence=_evidence(recomputed=5),
            revoke_on_demotion=("agent-a", "agent-b"),
            envelope=None,
        )

        assert result.new_level is PostureLevel.TOOL

        # Exactly one entry — the posture_change. No envelope_edit.
        entries = await _read_appended_entries(envoy_ledger)
        assert len(entries) == 1
        assert entries[0]["type"] == "posture_change"
        assert entries[0]["content"]["from_posture"] == "DELEGATING"
        assert entries[0]["content"]["to_posture"] == "TOOL"

        # Cascade-revoke fired per agent (Step 4 on demotion).
        assert len(revoke.calls) == 2
        assert {c["agent_id"] for c in revoke.calls} == {"agent-a", "agent-b"}

        # BET-12 emitted (every accepted transition emits, demotion included).
        assert len(sink.writes) == 1
        assert sink.writes[0].from_level is PostureLevel.DELEGATING
        assert sink.writes[0].to_level is PostureLevel.TOOL

    async def test_ratchet_down_does_not_mutate_envelope_posture_level(
        self, envoy_ledger: EnvoyLedger, tmp_path
    ) -> None:
        """F-4 mint-state pin: demotion MUST NOT mutate envelope.metadata.posture_level.

        Per `journal/0022-DECISION-posture-level-mint-state-interpretation.md`
        + `specs/envelope-model.md` § Schema field semantics for
        metadata.posture_level: the field is the mint-time annotation,
        not the current effective posture. Ratchet-down emits a
        `posture_change` entry only (no `envelope_edit`, no envelope
        mutation); the envelope's `posture_level` stays at the mint-time
        value.

        Provided demotion path: compile envelope at DELEGATING, demote to TOOL.
        Expected: envelope.metadata.posture_level remains "DELEGATING" after
        the gate accepts the demotion.
        """
        gate, _revoke, _sink, _emitter = _make_gate_and_collaborators(envoy_ledger)
        compiler = _make_compiler(tmp_path)
        envelope = _compile_envelope(
            compiler, principal_id="frank", initial_posture_level=PostureLevel.DELEGATING
        )
        mint_state_value = envelope.metadata.posture_level
        assert mint_state_value == "DELEGATING"  # baseline

        # Demote with envelope=None (the documented ratchet-down path —
        # envelope is not consumed on demotion paths).
        await gate.request_transition(
            principal_id="frank",
            current=PostureLevel.DELEGATING,
            target=PostureLevel.TOOL,
            evidence=_evidence(recomputed=5),
            envelope=None,
        )

        # Mint-immutability invariant: the envelope reference still carries
        # the mint-time posture_level. The current effective posture is
        # derived by walking the Ledger's posture_change entries, NOT by
        # reading this field.
        assert envelope.metadata.posture_level == mint_state_value
        assert envelope.metadata.posture_level == "DELEGATING"


# ---------------------------------------------------------------------------
# F-4 mint-state pin: ratchet-up mints a new envelope; original is immutable
# ---------------------------------------------------------------------------


class TestEnvelopePostureLevelIsMintStateOnRatchetUp:
    """F-4 closure: `metadata.posture_level` is the envelope's mint-time
    audit annotation. Ratchet-up mints a NEW envelope version (whose
    `posture_level` reflects the new mint state) via
    `mutate_for_posture_level()`; the ORIGINAL envelope reference's
    `posture_level` stays at the prior mint-time value (mint-immutability).

    Per `journal/0022-DECISION-posture-level-mint-state-interpretation.md`
    + `specs/envelope-model.md` § Schema field semantics for
    metadata.posture_level: this pins that the envelope's posture_level
    is NOT a current-effective-posture readout, and that ratchet-up does
    NOT in-place-mutate the source envelope.
    """

    async def test_ratchet_up_returns_new_mint_state_original_untouched(
        self, envoy_ledger: EnvoyLedger, tmp_path
    ) -> None:
        gate, _revoke, _sink, _emitter = _make_gate_and_collaborators(envoy_ledger)
        compiler = _make_compiler(tmp_path)
        envelope = _compile_envelope(
            compiler, principal_id="grace", initial_posture_level=PostureLevel.PSEUDO
        )
        original_mint_state = envelope.metadata.posture_level
        assert original_mint_state == "PSEUDO"

        carrier = _EnvelopeConfigPostureCarrier(envelope, compiler)
        await gate.request_transition(
            principal_id="grace",
            current=PostureLevel.PSEUDO,
            target=PostureLevel.TOOL,
            evidence=_evidence(recomputed=0),
            envelope=carrier,
        )

        # Mint-immutability invariant: the SOURCE envelope reference's
        # posture_level is unchanged. The new envelope version (returned
        # by mutate_for_posture_level) carries the new mint state.
        assert envelope.metadata.posture_level == original_mint_state
        assert envelope.metadata.posture_level == "PSEUDO"

        # The mutation result carries the NEW mint state.
        mutation = carrier.mutate_for_posture_level(PostureLevel.TOOL)
        assert mutation.new_posture_level == "TOOL"
        assert mutation.new_envelope.metadata.posture_level == "TOOL"
        # And the new envelope's posture_level differs from the original.
        assert mutation.new_envelope.metadata.posture_level != envelope.metadata.posture_level

    async def test_mutation_returns_new_envelope_object_not_in_place(
        self, envoy_ledger: EnvoyLedger, tmp_path
    ) -> None:
        """The mutation result's `new_envelope` MUST NOT be the same Python
        object as the source envelope. Mint-state semantics require a new
        envelope version (per `specs/envelope-model.md` § envelope_version
        monotonic bump); in-place mutation would violate the mint-time-
        immutability invariant the spec relies on."""
        _gate, _revoke, _sink, _emitter = _make_gate_and_collaborators(envoy_ledger)
        compiler = _make_compiler(tmp_path)
        envelope = _compile_envelope(
            compiler, principal_id="grace", initial_posture_level=PostureLevel.PSEUDO
        )
        carrier = _EnvelopeConfigPostureCarrier(envelope, compiler)
        mutation = carrier.mutate_for_posture_level(PostureLevel.TOOL)
        # Distinct Python object — frozen dataclass replace returns a new instance.
        assert mutation.new_envelope is not envelope
        # Distinct envelope_version — the new envelope is at the next version.
        assert mutation.new_envelope.envelope_version == envelope.envelope_version + 1
        # Same envelope_id — the new version is a continuation of the same
        # envelope chain, not a fresh envelope identity.
        assert mutation.new_envelope.metadata.envelope_id == envelope.metadata.envelope_id


# ---------------------------------------------------------------------------
# Typed-error contract: ratchet-up without envelope is BLOCKED
# ---------------------------------------------------------------------------


class TestPostureRatchetEnvelopeMissingError:
    """Per `journal/0021-DECISION-...md` § "What lands in this shard" #1:
    a ratchet-up with `envelope=None` MUST raise a typed
    `PostureRatchetEnvelopeMissingError(PostureGateError)` — never silently
    skip the envelope_edit emission (`rules/zero-tolerance.md` Rule 3).

    The runtime contract closes the kwarg-Optional weakness identified in
    journal/0021 § "Cons (real, not glossed)".
    """

    async def test_ratchet_up_without_envelope_raises_typed_error(
        self, envoy_ledger: EnvoyLedger
    ) -> None:
        # Import inside the test so the error class lookup happens after
        # the production fix lands. Until then, the import fails loudly
        # at test collection (per `rules/orphan-detection.md` Rule 5 —
        # collect-only is a merge gate).
        from envoy.authorship.posture_gate import PostureRatchetEnvelopeMissingError

        gate, _revoke, sink, _emitter = _make_gate_and_collaborators(envoy_ledger)

        with pytest.raises(PostureRatchetEnvelopeMissingError):
            await gate.request_transition(
                principal_id="grace",
                current=PostureLevel.PSEUDO,
                target=PostureLevel.TOOL,
                evidence=_evidence(recomputed=0),
                envelope=None,  # missing on a ratchet-up
            )

        # Fail-closed: zero entries appended, zero BET-12 emissions.
        entries = await _read_appended_entries(envoy_ledger)
        assert entries == []
        assert sink.writes == []

    async def test_error_has_user_message(self) -> None:
        """Plain-language user_message per `rules/communication.md` +
        the existing PostureGateError subclass contract from T-02-31."""
        from envoy.authorship.posture_gate import PostureRatchetEnvelopeMissingError

        err = PostureRatchetEnvelopeMissingError(
            current=PostureLevel.PSEUDO, target=PostureLevel.TOOL
        )
        assert hasattr(err, "user_message")
        assert isinstance(err.user_message, str)
        assert len(err.user_message) > 0
