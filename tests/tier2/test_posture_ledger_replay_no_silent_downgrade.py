"""Tier 2: posture ledger-replay projection — "no silent downgrade" (F19, Phase-01 half).

Posture is a PROJECTION, not stored state. The current effective posture is
derived by REPLAYING the hash-chained Ledger's `posture_change` entries — NOT by
reading `envelope.metadata.posture_level` (the mint-time annotation). This is the
invariant pinned at `tests/tier2/test_posture_gate_wiring.py:919-923`
("derived by walking the Ledger's posture_change entries, NOT by reading this
field") + `specs/posture-ladder.md:126-133` + open-question line 217
("envelope-metadata (re-derivable from Ledger)").

"No silent downgrade" at the projection layer means:

  1. Posture changes ONLY via an explicit `posture_change` Ledger entry. Demotion
     (`target < current`) is the only downgrade path and it ALWAYS writes an entry
     (`envoy/authorship/posture_gate.py:969-979`); there is no code path that
     lowers posture without a recorded entry.
  2. Chain-link continuity: each `posture_change` entry's `from_posture` equals the
     prior entry's `to_posture`. Replaying the chain reconstructs the posture
     trajectory; a dropped / reordered / silently-inserted-downgrade entry breaks
     the link and is detected at projection time.
  3. Determinism: replaying the same chain twice yields the same (non-downgraded)
     posture.

These tests build a real Ledger via the real `PostureGate` over real Ed25519
infrastructure (Tier 2 contract per `rules/testing.md` — NO mocking), then replay
the appended entries through a small projection and assert the invariants.

SCOPE FENCE (F19 Phase-01 half ONLY): the fail-closed-on-collaborator-error /
orphan-entry-window half is Phase-03 / GH issue #24 (the F-001 transient-Ledger-
failure-between-Step-5a-and-Step-5b bug class noted at posture_gate.py:998-1002).
It is NOT implemented here.
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass
from typing import Any

from envoy.authorship import (
    BET12CadenceEmitter,
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
# Tier 2 collaborators — real adapters (NOT mocks), mirroring
# tests/tier2/test_posture_gate_wiring.py.
# ---------------------------------------------------------------------------


class _RevokeRecorder:
    """Real cascade-revoke hook adapter — records calls, raises on bad input."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, *, agent_id: str, reason: str, revoked_by: str) -> object:
        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError("agent_id must be non-empty str")
        self.calls.append(agent_id)
        return object()


class _RecordingBET12Sink:
    """Real BET-12 sink — records cadence payloads (observe, do not mock)."""

    def __init__(self) -> None:
        self.writes: list[Any] = []

    async def write(self, payload: Any) -> None:
        self.writes.append(payload)


@dataclass
class _PostureMutationOutcome:
    """Mirror of PostureGate's structural `_PostureMutationResult`."""

    envelope_id: str
    new_version: int
    new_content_hash: str
    diff_hash: str
    new_posture_level: str
    new_envelope: Any


class _EnvelopeConfigPostureCarrier:
    """Adapter wrapping a real `EnvelopeConfig` to satisfy the PostureGate
    `_PostureCarryingEnvelope` Protocol — identical contract to the carrier in
    tests/tier2/test_posture_gate_wiring.py (real canonical-bytes pipeline)."""

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
        if not isinstance(new_level, PostureLevel):
            raise TypeError(f"new_level must be PostureLevel, got {type(new_level).__name__}")
        new_version = self._envelope.envelope_version + 1
        new_metadata = dataclasses.replace(self._envelope.metadata, posture_level=new_level.name)
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
        from dataclasses import asdict
        from enum import Enum

        def _enum_safe(value: Any) -> Any:
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, dict):
                return {k: _enum_safe(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
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


def _make_gate_and_collaborators(
    envoy_ledger: EnvoyLedger,
) -> tuple[PostureGate, _RevokeRecorder, _RecordingBET12Sink]:
    revoke = _RevokeRecorder()
    sink = _RecordingBET12Sink()
    emitter = BET12CadenceEmitter(sink=sink)
    gate = PostureGate(ledger=envoy_ledger, revoke_hook=revoke, bet12_emitter=emitter)
    return gate, revoke, sink


def _make_compiler(tmp_root: Any) -> EnvelopeCompiler:
    return EnvelopeCompiler(template_resolver=LocalTemplateResolver(tmp_root))


def _compile_envelope(
    compiler: EnvelopeCompiler,
    *,
    principal_id: str,
    initial_posture_level: PostureLevel,
) -> EnvelopeConfig:
    metadata = EnvelopeMetadata(posture_level=initial_posture_level.name)
    return compiler.compile(EnvelopeConfigInput(metadata=metadata), principal_id=principal_id)


def _evidence(*, recomputed: int, mode: PostureMode = PostureMode.PERSONAL) -> PostureEvidence:
    return PostureEvidence(
        authorship_score_recomputed=recomputed,
        authorship_score_stored=recomputed,
        mode=mode,
        genesis_signed_grant=True,
        cooling_off_active=False,
        envelope_id_hash="sha256:f19-replay-test",
    )


async def _read_appended_entries(ledger: EnvoyLedger) -> list[dict[str, Any]]:
    """Read every envoy entry appended to the real Ledger, ascending by sequence.

    Mirrors tests/tier2/test_posture_gate_wiring.py::_read_appended_entries —
    observes through the real `audit_store.query()` surface (no mocking), reading
    the `_envoy_envelope_v1` sentinel `EnvoyLedger.append` persists.
    """
    from kailash.trust.audit_store import AuditFilter

    events = await ledger._audit_store.query(AuditFilter(limit=1000))
    entries: list[dict[str, Any]] = []
    for ev in events:
        envoy_envelope = (ev.metadata or {}).get("_envoy_envelope_v1")
        if envoy_envelope is None:
            continue
        entries.append(envoy_envelope)
    entries.sort(key=lambda e: e["sequence"])
    return entries


def _project_posture(
    entries: list[dict[str, Any]],
    *,
    initial: PostureLevel = PostureLevel.PSEUDO,
) -> PostureLevel:
    """Replay the Ledger's posture_change entries to derive the current posture.

    This is the projection layer. Posture changes ONLY via a `posture_change`
    entry; each entry's `from_posture` MUST equal the running projected posture
    (chain-link continuity). A break (dropped / reordered / silently-inserted
    entry) raises AssertionError — this is the "no silent downgrade" structural
    guarantee: replay can never produce a posture the entries do not justify.
    """
    current = initial
    for entry in entries:
        if entry["type"] != "posture_change":
            continue
        content = entry["content"]
        from_posture = PostureLevel[content["from_posture"]]
        to_posture = PostureLevel[content["to_posture"]]
        assert from_posture == current, (
            f"posture-chain break: entry claims from_posture={from_posture.name} "
            f"but projected current is {current.name} — a silent posture change "
            f"would have to forge this link"
        )
        current = to_posture
    return current


# ---------------------------------------------------------------------------
# Replay projection — no silent downgrade
# ---------------------------------------------------------------------------


class TestLedgerReplayProjection:
    """Posture replayed from the Ledger is deterministic and never silently
    downgraded — every change is an explicit, chain-linked posture_change entry.
    """

    async def test_replay_derives_final_posture_from_explicit_entries(
        self, envoy_ledger: EnvoyLedger, tmp_path
    ) -> None:
        """Drive a real trajectory through the gate (3 ratchet-ups, 1 demotion,
        1 ratchet-up) and replay it. The projection reconstructs the posture
        purely from posture_change entries.

        Grounded in repro: 5 posture_change + 4 envelope_edit (the demotion is
        the only transition that does NOT emit a paired envelope_edit per
        posture_gate.py:748-751); final projected posture is SUPERVISED.
        """
        gate, _revoke, _sink = _make_gate_and_collaborators(envoy_ledger)
        compiler = _make_compiler(tmp_path)

        def carrier(level: PostureLevel) -> _EnvelopeConfigPostureCarrier:
            env = _compile_envelope(compiler, principal_id="alice", initial_posture_level=level)
            return _EnvelopeConfigPostureCarrier(env, compiler)

        # PSEUDO -> TOOL -> SUPERVISED -> DELEGATING (climb)
        await gate.request_transition(
            principal_id="alice",
            current=PostureLevel.PSEUDO,
            target=PostureLevel.TOOL,
            evidence=_evidence(recomputed=0),
            envelope=carrier(PostureLevel.PSEUDO),
        )
        await gate.request_transition(
            principal_id="alice",
            current=PostureLevel.TOOL,
            target=PostureLevel.SUPERVISED,
            evidence=_evidence(recomputed=1),
            envelope=carrier(PostureLevel.TOOL),
        )
        await gate.request_transition(
            principal_id="alice",
            current=PostureLevel.SUPERVISED,
            target=PostureLevel.DELEGATING,
            evidence=_evidence(recomputed=3),
            envelope=carrier(PostureLevel.SUPERVISED),
        )
        # DELEGATING -> TOOL (explicit demotion — emits ONLY posture_change)
        await gate.request_transition(
            principal_id="alice",
            current=PostureLevel.DELEGATING,
            target=PostureLevel.TOOL,
            evidence=_evidence(recomputed=3),
            revoke_on_demotion=("agent-x",),
            envelope=None,
        )
        # TOOL -> SUPERVISED (climb again)
        await gate.request_transition(
            principal_id="alice",
            current=PostureLevel.TOOL,
            target=PostureLevel.SUPERVISED,
            evidence=_evidence(recomputed=1),
            envelope=carrier(PostureLevel.TOOL),
        )

        entries = await _read_appended_entries(envoy_ledger)
        posture_changes = [e for e in entries if e["type"] == "posture_change"]
        envelope_edits = [e for e in entries if e["type"] == "envelope_edit"]

        # Grounded structural counts (repro-confirmed).
        assert len(posture_changes) == 5
        assert len(envelope_edits) == 4  # demotion emits no envelope_edit

        # The projection derives the final posture from explicit entries only.
        final = _project_posture(entries)
        assert final is PostureLevel.SUPERVISED
        assert int(final) == 2

        # The final posture equals the LAST posture_change's to_posture — posture
        # is never silently set to anything the entries do not justify.
        last_to = PostureLevel[posture_changes[-1]["content"]["to_posture"]]
        assert final is last_to

    async def test_replay_is_deterministic(self, envoy_ledger: EnvoyLedger, tmp_path) -> None:
        """Replaying the same chain twice yields the same posture — projection
        is a pure function of the (ordered) entries."""
        gate, _revoke, _sink = _make_gate_and_collaborators(envoy_ledger)
        compiler = _make_compiler(tmp_path)

        def carrier(level: PostureLevel) -> _EnvelopeConfigPostureCarrier:
            env = _compile_envelope(compiler, principal_id="bob", initial_posture_level=level)
            return _EnvelopeConfigPostureCarrier(env, compiler)

        await gate.request_transition(
            principal_id="bob",
            current=PostureLevel.PSEUDO,
            target=PostureLevel.TOOL,
            evidence=_evidence(recomputed=0),
            envelope=carrier(PostureLevel.PSEUDO),
        )
        await gate.request_transition(
            principal_id="bob",
            current=PostureLevel.TOOL,
            target=PostureLevel.SUPERVISED,
            evidence=_evidence(recomputed=1),
            envelope=carrier(PostureLevel.TOOL),
        )

        entries = await _read_appended_entries(envoy_ledger)
        first = _project_posture(entries)
        second = _project_posture(entries)
        assert first is second
        assert first is PostureLevel.SUPERVISED

    async def test_climb_only_trajectory_is_monotone_nondecreasing(
        self, envoy_ledger: EnvoyLedger, tmp_path
    ) -> None:
        """A ratchet-up-only history projects to a monotone non-decreasing
        posture trajectory — no posture_change ever records a lower to_posture
        than the prior to_posture without being an explicit demotion entry.

        This is the core "no silent downgrade" property: posture cannot drop
        between two ratchet-ups; only an explicit demotion entry lowers it.
        """
        gate, _revoke, _sink = _make_gate_and_collaborators(envoy_ledger)
        compiler = _make_compiler(tmp_path)

        def carrier(level: PostureLevel) -> _EnvelopeConfigPostureCarrier:
            env = _compile_envelope(compiler, principal_id="carol", initial_posture_level=level)
            return _EnvelopeConfigPostureCarrier(env, compiler)

        for cur, tgt, n in [
            (PostureLevel.PSEUDO, PostureLevel.TOOL, 0),
            (PostureLevel.TOOL, PostureLevel.SUPERVISED, 1),
            (PostureLevel.SUPERVISED, PostureLevel.DELEGATING, 3),
        ]:
            await gate.request_transition(
                principal_id="carol",
                current=cur,
                target=tgt,
                evidence=_evidence(recomputed=n),
                envelope=carrier(cur),
            )

        entries = await _read_appended_entries(envoy_ledger)
        posture_changes = [e for e in entries if e["type"] == "posture_change"]
        to_levels = [PostureLevel[e["content"]["to_posture"]] for e in posture_changes]

        # Climb-only history is strictly monotone non-decreasing.
        assert all(int(to_levels[i]) <= int(to_levels[i + 1]) for i in range(len(to_levels) - 1))
        # The projection equals the highest level reached — no silent regression.
        final = _project_posture(entries)
        assert final is to_levels[-1]
        assert final is PostureLevel.DELEGATING

    async def test_dropping_a_posture_change_entry_breaks_the_replay_chain(
        self, envoy_ledger: EnvoyLedger, tmp_path
    ) -> None:
        """If a posture_change entry is silently removed from the replayed set,
        the projection's from/to chain-link assertion fires — a silent downgrade
        (or any silent reorder/omission) cannot pass undetected through replay.

        Grounded in repro: dropping the SUPERVISED entry from a
        PSEUDO->TOOL->SUPERVISED->DELEGATING history breaks the link
        ("entry says from=SUPERVISED but projected cur=TOOL").
        """
        gate, _revoke, _sink = _make_gate_and_collaborators(envoy_ledger)
        compiler = _make_compiler(tmp_path)

        def carrier(level: PostureLevel) -> _EnvelopeConfigPostureCarrier:
            env = _compile_envelope(compiler, principal_id="dave", initial_posture_level=level)
            return _EnvelopeConfigPostureCarrier(env, compiler)

        for cur, tgt, n in [
            (PostureLevel.PSEUDO, PostureLevel.TOOL, 0),
            (PostureLevel.TOOL, PostureLevel.SUPERVISED, 1),
            (PostureLevel.SUPERVISED, PostureLevel.DELEGATING, 3),
        ]:
            await gate.request_transition(
                principal_id="dave",
                current=cur,
                target=tgt,
                evidence=_evidence(recomputed=n),
                envelope=carrier(cur),
            )

        entries = await _read_appended_entries(envoy_ledger)
        # Intact replay succeeds.
        assert _project_posture(entries) is PostureLevel.DELEGATING

        # Silently drop the TOOL->SUPERVISED posture_change entry.
        tampered = [
            e
            for e in entries
            if not (e["type"] == "posture_change" and e["content"]["to_posture"] == "SUPERVISED")
        ]
        import pytest

        with pytest.raises(AssertionError, match="posture-chain break"):
            _project_posture(tampered)

    async def test_ledger_chain_verifies_under_signed_replay(
        self, envoy_ledger: EnvoyLedger, tmp_path
    ) -> None:
        """The Ledger the projection replays is itself hash-chained + Ed25519
        signed: `verify_chain()` passes over the appended posture entries, so the
        replay reads from a tamper-evident substrate (parent_hash + signature per
        entry). This is the cryptographic floor under the projection invariant."""
        gate, _revoke, _sink = _make_gate_and_collaborators(envoy_ledger)
        compiler = _make_compiler(tmp_path)
        env = _compile_envelope(
            compiler, principal_id="erin", initial_posture_level=PostureLevel.PSEUDO
        )
        carrier = _EnvelopeConfigPostureCarrier(env, compiler)

        await gate.request_transition(
            principal_id="erin",
            current=PostureLevel.PSEUDO,
            target=PostureLevel.TOOL,
            evidence=_evidence(recomputed=0),
            envelope=carrier,
        )

        report = await envoy_ledger.verify_chain()
        assert report.success is True
        # 2 entries: posture_change + paired envelope_edit (ratchet-up).
        assert report.entries_verified == 2
        assert report.failed_entry_index is None
