"""envoy.boundary_conversation.runtime — the BoundaryConversationRuntime facade.

``BoundaryConversationRuntime`` composes the Boundary Conversation: the Plan-DAG
script, the per-state Kaizen ``Signature``s, the model router (LLM extraction),
the Trust Vault (visible secret + per-state resume persistence), the Envoy
Ledger (ReasoningCommit + posture_change), the Envelope Compiler (S9 compile),
the Shamir coordinator (S8 backup ritual), and the novelty checker (S3/S5 gate).

Per `rules/facade-manager-detection.md` Rule 3: every dependency is injected
explicitly (no global lookup, no self-construction).

State machine (per `specs/boundary-conversation.md` § State machine +
`workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md`
§ 3.1):

    S0 greet → S1 money → S2 people → S3 topics → S4 hours → S5 first task →
    S6 template offer → S7 visible secret → S8 Shamir → S9 review&sign →
    S10 complete

with novelty re-prompt self-edges at S3/S5 (``NoveltyFeedbackBlockError``) and
gate-back self-edges at S7/S8 (``VisibleSecretMissingError`` /
``ShamirRitualIncompleteError``).

LLM-first (per `rules/agent-reasoning.md`): per-state extraction is performed by
the model via the state's ``Signature`` — the runtime does NOT keyword-route or
classify user input in code. The structural state machine (which state is next,
whether a gate is satisfied) is permitted deterministic plumbing.
"""

from __future__ import annotations

import importlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

from kaizen.l3.plan.suspension import ExplicitCancellationReason, SuspensionRecord
from kaizen.l3.plan.types import Plan, PlanNodeState, PlanState
from kaizen.signatures.core import Signature

from envoy.boundary_conversation.bet12_telemetry import BET12TelemetryHook
from envoy.boundary_conversation.envelope_assembler import EnvelopeConfigInputAssembler
from envoy.boundary_conversation.errors import (
    DuressBannerUnacknowledgedError,
    InvalidStateTransitionError,
    NoveltyFeedbackBlockError,
    ShamirRitualIncompleteError,
    VisibleSecretMissingError,
)
from envoy.boundary_conversation.resume import RitualResumeCoordinator
from envoy.boundary_conversation.script import (
    BOUNDARY_CONVERSATION_STATES,
    BoundaryConversationScript,
)

__all__ = ["BoundaryConversationRuntime", "ConversationOutcome"]

logger = logging.getLogger(__name__)

# Ledger entry types per `specs/ledger.md` § Entry types (per analysis § 5.3).
_ENTRY_REASONING_COMMIT = "ReasoningCommit"
_ENTRY_SESSION_BOUNDARY = "session_boundary_crossed"
_ENTRY_POSTURE_CHANGE = "posture_change"

# Genesis authority id for the first-time-author Genesis seed (Phase 01
# single-principal; Phase 02 swaps to the Foundation registry).
_GENESIS_AUTHORITY_ID = "envoy-genesis-authority"

# States whose authored answer is novelty-checked (S3 topics, S5 first task).
_NOVELTY_STATES = frozenset({"S3_topics", "S5_first_task"})

# preset_name → (legacy provider module, provider class) per analysis § 5.7 +
# the chat substrate pinned in tests/tier2/test_envoy_model_router_chat_async_routing.py.
# The runtime drives chat through the legacy provider surface until upstream
# LlmClient.complete() lands (#740, deferred to P02+).
_PRESET_PROVIDER = {
    "ollama": ("kaizen.providers.llm.ollama", "OllamaProvider"),
    "openai": ("kaizen.providers.llm.openai", "OpenAIProvider"),
    "openai_compatible": ("kaizen.providers.llm.openai", "OpenAIProvider"),
    "anthropic": ("kaizen.providers.llm.anthropic", "AnthropicProvider"),
    "anthropic_compatible": ("kaizen.providers.llm.anthropic", "AnthropicProvider"),
}


@dataclass
class ConversationOutcome:
    """The result of one ``advance()`` call.

    ``state`` is one of IN_PROGRESS / PAUSED / COMPLETE / ERROR. ``paused_for``
    is set when PAUSED (Phase 01: only ``"shamir_ritual"``). ``envelope_id`` is
    set on COMPLETE. ``error`` carries the typed re-prompt error on ERROR.
    ``current_state`` is the node-id the conversation now sits at (so a caller
    re-prompting after an ERROR knows which state to re-ask).
    """

    state: str
    current_state: str
    paused_for: str | None = None
    envelope_id: str | None = None
    error: Exception | None = None


class BoundaryConversationRuntime:
    """Facade orchestrating the S0→S10 Boundary Conversation."""

    def __init__(
        self,
        *,
        model_router: Any,
        trust_store: Any,
        ledger: Any,
        envelope_compiler: Any,
        shamir_coordinator: Any,
        novelty_checker: Any,
    ) -> None:
        self._model_router = model_router
        self._trust_store = trust_store
        self._ledger = ledger
        self._envelope_compiler = envelope_compiler
        self._shamir_coordinator = shamir_coordinator
        self._novelty_checker = novelty_checker

        self._script = BoundaryConversationScript()
        self._resume = RitualResumeCoordinator(trust_store=trust_store)
        self._telemetry = BET12TelemetryHook(ledger=ledger)

        # Per-ritual in-flight state (this session). Keyed by ritual_id.
        self._plans: dict[str, Plan] = {}
        self._assemblers: dict[str, EnvelopeConfigInputAssembler] = {}
        self._principals: dict[str, str] = {}
        self._current_state: dict[str, str] = {}
        self._started_at: dict[str, float] = {}
        self._duress_acknowledged: dict[str, bool] = {}
        # Local cache of Foundation-Verified template constraint texts the
        # novelty checker compares against (Phase 01: empty until a template is
        # imported at S6; the conversation supplies the cache it knows about).
        self._template_texts: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, *, principal_id: str) -> str:
        """Begin a fresh conversation; return the ritual_id.

        Persists the initial S0 state, emits a ReasoningCommit Ledger entry for
        S0 entry, and runs the post-duress banner gate: if the shadow segment
        carries an unread duress event, advancing past S0 raises
        ``DuressBannerUnacknowledgedError`` until ``acknowledge_duress`` is
        called (Phase 01: the gate is inert — the shadow segment returns [] —
        but the gate is correctly wired per § 3.6).
        """
        if not principal_id:
            raise ValueError("principal_id is required to start a Boundary Conversation")
        ritual_id = f"bc-{uuid.uuid4()}"
        plan = self._script.build_plan()
        assembler = EnvelopeConfigInputAssembler()

        self._plans[ritual_id] = plan
        self._assemblers[ritual_id] = assembler
        self._principals[ritual_id] = principal_id
        self._current_state[ritual_id] = "S0_greet"
        self._started_at[ritual_id] = time.monotonic()
        self._template_texts[ritual_id] = []

        # Post-duress banner gate (§ 3.6). Phase 01 shadow segment returns [];
        # the gate is wired so it activates the moment P02 populates duress.
        unread = await self._trust_store.shadow_segment_unread_duress_events(principal_id)
        self._duress_acknowledged[ritual_id] = not unread
        if unread:
            logger.warning(
                "boundary_conversation.duress_banner.pending",
                extra={"ritual_id": ritual_id, "unread_count": len(unread)},
            )

        await self._telemetry.state_entered(ritual_id, "S0_greet")
        await self._ledger.append(
            entry_type=_ENTRY_REASONING_COMMIT,
            content={"ritual_id": ritual_id, "state": "S0_greet", "principal_id": principal_id},
        )
        await self._persist(ritual_id)
        logger.info(
            "boundary_conversation.started",
            extra={"ritual_id": ritual_id, "principal_id": principal_id},
        )
        return ritual_id

    async def resume(self, ritual_id: str) -> None:
        """Rehydrate an in-flight conversation from the Trust Vault.

        Raises ``RitualResumeStateMissingError`` (from the resume coordinator)
        if the ritual_id is absent. After resume, the conversation continues
        from the persisted ``current_state``.
        """
        resumed = await self._resume.load_state(ritual_id)
        self._plans[ritual_id] = resumed.plan
        self._assemblers[ritual_id] = resumed.assembler
        self._principals[ritual_id] = resumed.principal_id
        self._current_state[ritual_id] = resumed.current_state
        self._started_at.setdefault(ritual_id, time.monotonic())
        self._duress_acknowledged.setdefault(ritual_id, True)
        self._template_texts.setdefault(ritual_id, [])
        logger.info(
            "boundary_conversation.resumed",
            extra={"ritual_id": ritual_id, "current_state": resumed.current_state},
        )

    def acknowledge_duress(self, ritual_id: str) -> None:
        """Acknowledge the post-duress banner so the conversation may advance."""
        self._duress_acknowledged[ritual_id] = True

    def current_plan(self, ritual_id: str) -> Plan:
        """Return the in-flight Plan for ``ritual_id``."""
        return self._plans[self._require_known(ritual_id)]

    def current_state(self, ritual_id: str) -> str:
        """Return the conversation-state node-id ``ritual_id`` currently sits at."""
        return self._current_state[self._require_known(ritual_id)]

    # ------------------------------------------------------------------
    # advance — the per-state transition
    # ------------------------------------------------------------------

    async def advance(self, ritual_id: str, user_input: str) -> ConversationOutcome:
        """Process the user's reply at the current state and advance the DAG.

        Per analysis § 4: runs the per-state Signature against the model router;
        a parse failure raises ``InvalidStateTransitionError`` (caller re-prompts
        the same state); S3/S5 apply the novelty gate; S7 stores the visible
        secret; S8 runs the Shamir ritual and suspends the Plan; S9 assembles +
        compiles the envelope, seeds Genesis, and ratchets posture; S10
        completes.
        """
        self._require_known(ritual_id)
        state = self._current_state[ritual_id]

        # Post-duress banner gate (§ 3.6): cannot advance past S0 until ack.
        if state == "S0_greet" and not self._duress_acknowledged.get(ritual_id, True):
            raise DuressBannerUnacknowledgedError(duress_event_id="pending")

        logger.info(
            "boundary_conversation.advance.start",
            extra={"ritual_id": ritual_id, "state": state},
        )
        await self._telemetry.state_entered(ritual_id, state)
        t0 = time.monotonic()

        try:
            outcome = await self._dispatch_state(ritual_id, state, user_input)
        except (
            InvalidStateTransitionError,
            NoveltyFeedbackBlockError,
            VisibleSecretMissingError,
            ShamirRitualIncompleteError,
        ) as exc:
            # Re-promptable error: telemetry records the retry; the caller
            # re-asks the SAME state. The outcome carries the error.
            latency_ms = int((time.monotonic() - t0) * 1000)
            await self._telemetry.state_completed(
                ritual_id, state, latency_ms=latency_ms, retry_count=1
            )
            logger.info(
                "boundary_conversation.advance.reprompt",
                extra={"ritual_id": ritual_id, "state": state, "error": type(exc).__name__},
            )
            return ConversationOutcome(state="ERROR", current_state=state, error=exc)

        latency_ms = int((time.monotonic() - t0) * 1000)
        await self._telemetry.state_completed(
            ritual_id, state, latency_ms=latency_ms, retry_count=0
        )
        await self._persist(ritual_id)
        logger.info(
            "boundary_conversation.advance.ok",
            extra={
                "ritual_id": ritual_id,
                "from_state": state,
                "to_state": outcome.current_state,
                "outcome": outcome.state,
            },
        )
        return outcome

    # ------------------------------------------------------------------
    # Per-state dispatch (structural state machine — NOT input routing)
    # ------------------------------------------------------------------

    async def _dispatch_state(
        self, ritual_id: str, state: str, user_input: str
    ) -> ConversationOutcome:
        """Handle one state and return the outcome (advancing current_state)."""
        if state in self._script_states_with_signature:
            extraction = await self._extract(ritual_id, state, user_input)
            # Per-state side effects on the extraction.
            if state in _NOVELTY_STATES:
                self._apply_novelty_gate(ritual_id, state, extraction)
            if state == "S7_visible_secret":
                await self._handle_visible_secret(ritual_id, extraction)
            self._assemblers[ritual_id].feed(state, extraction)

            if state == "S8_shamir":
                return await self._handle_shamir(ritual_id)
            if state == "S9_review_sign":
                return await self._handle_review_sign(ritual_id, extraction)

            # Ordinary forward transition (S1..S7).
            return await self._advance_to_next(ritual_id, state)

        # S0 greet (no answer) → S1. S10 complete is terminal.
        if state == "S0_greet":
            return await self._advance_to_next(ritual_id, state)
        if state == "S10_complete":
            return ConversationOutcome(state="COMPLETE", current_state="S10_complete")

        raise InvalidStateTransitionError(state, f"unknown conversation state {state!r}")

    @property
    def _script_states_with_signature(self) -> frozenset[str]:
        # S1..S9 have a Signature (S0 greet, S10 complete do not).
        return frozenset(BOUNDARY_CONVERSATION_STATES[1:10])

    async def _advance_to_next(self, ritual_id: str, state: str) -> ConversationOutcome:
        """Mark ``state`` complete, advance current_state to the next node, emit
        a ReasoningCommit, and return an IN_PROGRESS outcome."""
        next_state = self._next_state(state)
        self._mark_completed(ritual_id, state)
        self._current_state[ritual_id] = next_state
        await self._ledger.append(
            entry_type=_ENTRY_REASONING_COMMIT,
            content={"ritual_id": ritual_id, "from_state": state, "to_state": next_state},
        )
        if next_state == "S10_complete":
            return ConversationOutcome(state="COMPLETE", current_state="S10_complete")
        return ConversationOutcome(state="IN_PROGRESS", current_state=next_state)

    # ------------------------------------------------------------------
    # LLM extraction (LLM-first — the model reasons; runtime does NOT route)
    # ------------------------------------------------------------------

    async def _extract(self, ritual_id: str, state: str, user_input: str) -> dict[str, Any]:
        """Run the state's Signature against the model and parse the structured
        output. Raises ``InvalidStateTransitionError`` if the model returns
        unparseable / incomplete JSON (the caller re-prompts the same state)."""
        signature = self._script.signature_for_state(state)
        client = self._model_router.for_primitive("boundary_conversation")
        prompt = _build_structured_prompt(signature, user_input)

        raw = await self._chat(client, prompt)
        try:
            extraction = _parse_structured_output(signature, raw)
        except ValueError as exc:
            raise InvalidStateTransitionError(state, str(exc)) from exc
        extraction["reply"] = user_input
        return extraction

    async def _chat(self, client: Any, prompt: str) -> str:
        """Send a single-turn chat through the legacy provider surface.

        The router returns an ``LlmClient``; its ``deployment.preset_name`` picks
        the legacy provider (Ollama sync ``chat`` / OpenAI+Anthropic async
        ``chat_async``) per the chat substrate pinned in the Tier 2 routing test.
        The model name is read from the deployment (router resolves it from env
        per `rules/env-models.md` — NEVER hardcoded here).
        """
        deployment = client.deployment
        preset = getattr(deployment, "preset_name", None)
        model = getattr(deployment, "default_model", None)
        if preset not in _PRESET_PROVIDER:
            raise InvalidStateTransitionError(
                "chat",
                f"no legacy chat provider mapped for preset {preset!r}",
            )
        module_path, class_name = _PRESET_PROVIDER[preset]
        provider_cls = getattr(importlib.import_module(module_path), class_name)
        provider = provider_cls()
        messages = [{"role": "user", "content": prompt}]

        # Ollama exposes sync chat; OpenAI/Anthropic expose async chat_async
        # (per tests/tier2/test_envoy_model_router_chat_async_routing.py).
        if hasattr(provider, "chat_async"):
            result = await provider.chat_async(messages=messages, model=model)
        else:
            result = provider.chat(messages=messages, model=model)
        return _extract_chat_content(result)

    # ------------------------------------------------------------------
    # Per-state side effects
    # ------------------------------------------------------------------

    def _apply_novelty_gate(self, ritual_id: str, state: str, extraction: dict[str, Any]) -> None:
        """S3/S5 novelty gate: assert the authored text is not a near-duplicate
        of a cached template constraint. Raises ``NoveltyFeedbackBlockError`` via
        the novelty checker (re-prompts the same state)."""
        authored_text = " ".join(str(v) for k, v in extraction.items() if k != "reply").strip()
        templates = self._template_texts.get(ritual_id, [])
        try:
            self._novelty_checker.assert_novel(authored_text, templates)
        except Exception as exc:
            # The authorship NoveltyFeedbackBlockError carries jaccard/threshold;
            # re-raise as the boundary_conversation taxonomy error carrying the
            # state so the caller re-prompts S3/S5.
            jaccard = getattr(exc, "max_jaccard", 0.0)
            raise NoveltyFeedbackBlockError(state, jaccard=jaccard, adversarial=0.0) from exc

    async def _handle_visible_secret(self, ritual_id: str, extraction: dict[str, Any]) -> None:
        """S7: persist the user's visible secret (icon + color + phrase) to the
        Trust Vault. All three components are required."""
        icon = str(extraction.get("icon", "")).strip()
        color = str(extraction.get("color", "")).strip()
        phrase = str(extraction.get("phrase", "")).strip()
        if not (icon and color and phrase):
            raise VisibleSecretMissingError()
        principal_id = self._principals[ritual_id]
        await self._trust_store.set_visible_secret(
            principal_id, icon=icon, color=color, phrase=phrase
        )
        # NEVER log the phrase (PII / anti-spoofing secret) per § 5.3.
        logger.info(
            "boundary_conversation.visible_secret.stored",
            extra={"ritual_id": ritual_id, "icon": icon, "color": color},
        )

    async def _handle_shamir(self, ritual_id: str) -> ConversationOutcome:
        """S8: run the first-time Shamir ritual and suspend the Plan.

        Per analysis § 5.5 (corrected: ``run_first_time_ritual``, NOT the stale
        ``start_3_of_5``): the coordinator produces the 5 shards; the Plan
        suspends with an ExplicitCancellationReason while the user completes the
        physical card distribution. Resume clears the suspension and advances to
        S9.
        """
        result = await self._shamir_coordinator.run_first_time_ritual()
        plan = self._plans[ritual_id]
        plan.suspension = SuspensionRecord(
            reason=ExplicitCancellationReason(
                reason="shamir_ritual_in_progress",
                resume_hint="Complete the physical card distribution, then resume.",
            )
        )
        plan.state = PlanState.SUSPENDED
        self._mark_completed(ritual_id, "S8_shamir")
        self._current_state[ritual_id] = "S9_review_sign"
        await self._ledger.append(
            entry_type=_ENTRY_SESSION_BOUNDARY,
            content={
                "ritual_id": ritual_id,
                "suspended_for": "shamir_ritual",
                "ritual_ref": result.ritual_id,
                "total_shards": result.total_shards,
            },
        )
        logger.info(
            "boundary_conversation.shamir.suspended",
            extra={"ritual_id": ritual_id, "shamir_ritual_id": result.ritual_id},
        )
        return ConversationOutcome(
            state="PAUSED", current_state="S9_review_sign", paused_for="shamir_ritual"
        )

    async def _handle_review_sign(
        self, ritual_id: str, extraction: dict[str, Any]
    ) -> ConversationOutcome:
        """S9: gate (visible secret present, Shamir complete), assemble + compile
        the envelope, seed Genesis, ratchet posture GENESIS_BARE→PSEUDO, and
        complete the suspension. Returns a COMPLETE outcome with the envelope_id.
        """
        principal_id = self._principals[ritual_id]

        # Gate 1: visible secret MUST exist (set at S7).
        visible_secret = await self._trust_store.get_visible_secret(principal_id)
        if visible_secret is None:
            self._current_state[ritual_id] = "S7_visible_secret"
            raise VisibleSecretMissingError()

        # Gate 2: Shamir ritual MUST be complete (the Plan suspension must be
        # cleared by a resume). A still-suspended Plan means the user reached S9
        # without finishing S8.
        plan = self._plans[ritual_id]
        if plan.suspension is not None:
            self._current_state[ritual_id] = "S8_shamir"
            raise ShamirRitualIncompleteError(distributed=0, required=self._shamir_total_shards())

        if not extraction.get("signed"):
            raise InvalidStateTransitionError(
                "S9_review_sign", "the envelope was not signed; please confirm to sign"
            )

        # Assemble + compile the envelope (first-time author: parent=None).
        envelope_input = self._assemblers[ritual_id].assemble()
        compiled = self._envelope_compiler.compile(envelope_input, principal_id=principal_id)
        envelope_id = compiled.metadata.envelope_id

        # Seed the Genesis trust record (PSEUDO posture).
        await self._seed_genesis(principal_id, envelope_id)

        # Ledger: posture_change GENESIS_BARE → PSEUDO.
        await self._ledger.append(
            entry_type=_ENTRY_POSTURE_CHANGE,
            content={
                "ritual_id": ritual_id,
                "principal_id": principal_id,
                "from": "GENESIS_BARE",
                "to": "PSEUDO",
                "basis": "boundary_conversation_completed",
                "envelope_id": envelope_id,
                "content_hash": compiled.content_hash,
            },
        )

        # Advance to S10 complete.
        self._mark_completed(ritual_id, "S9_review_sign")
        self._mark_completed(ritual_id, "S10_complete")
        self._current_state[ritual_id] = "S10_complete"
        plan.state = PlanState.COMPLETED

        # Final BET-12 conversation-duration telemetry (EC-1).
        duration = int(time.monotonic() - self._started_at.get(ritual_id, time.monotonic()))
        await self._telemetry.conversation_completed(ritual_id, total_duration_seconds=duration)

        logger.info(
            "boundary_conversation.completed",
            extra={"ritual_id": ritual_id, "envelope_id": envelope_id},
        )
        return ConversationOutcome(
            state="COMPLETE", current_state="S10_complete", envelope_id=envelope_id
        )

    async def _seed_genesis(self, principal_id: str, envelope_id: str) -> None:
        """Seed the Genesis Record via the trust store (idempotent across a
        re-run is the store's concern; the runtime seeds once at S9)."""
        from envoy.trust.types import GenesisSeed

        seed = GenesisSeed(
            principal_id=principal_id,
            authority_id=_GENESIS_AUTHORITY_ID,
            capabilities=("boundary_conversation_authored",),
            metadata={
                "authority_name": "Envoy Genesis Authority",
                "envelope_id": envelope_id,
                "posture": "PSEUDO",
            },
        )
        await self._trust_store.seed_genesis(seed)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _shamir_total_shards(self) -> int:
        return int(getattr(self._shamir_coordinator, "total_shards", 5) or 5)

    def _next_state(self, state: str) -> str:
        idx = BOUNDARY_CONVERSATION_STATES.index(state)
        return BOUNDARY_CONVERSATION_STATES[idx + 1]

    def _mark_completed(self, ritual_id: str, state: str) -> None:
        node = self._plans[ritual_id].nodes.get(state)
        if node is not None:
            node.state = PlanNodeState.COMPLETED

    async def _persist(self, ritual_id: str) -> None:
        await self._resume.persist_state(
            ritual_id,
            plan=self._plans[ritual_id],
            assembler=self._assemblers[ritual_id],
            principal_id=self._principals[ritual_id],
            current_state=self._current_state[ritual_id],
        )

    def _require_known(self, ritual_id: str) -> str:
        if ritual_id not in self._current_state:
            raise InvalidStateTransitionError(
                "unknown",
                f"ritual_id {ritual_id!r} is not active in this runtime; "
                "call start() or resume() first",
            )
        return ritual_id


# ---------------------------------------------------------------------------
# Structured-output prompt + parse helpers (LLM-first extraction)
# ---------------------------------------------------------------------------


def _build_structured_prompt(signature: Signature, user_input: str) -> str:
    """Render the Signature's output schema into a JSON-extraction instruction.

    The LLM is asked to reason about the user's reply and emit a JSON object
    with exactly the Signature's output fields. The runtime does NOT keyword-
    route — the model performs the extraction (per `rules/agent-reasoning.md`).
    """
    output_fields = signature.output_fields
    field_lines = []
    for name, spec in output_fields.items():
        type_name = getattr(spec.get("type"), "__name__", "string")
        desc = spec.get("desc", "")
        field_lines.append(f'  "{name}": <{type_name}>  // {desc}')
    schema = "{\n" + ",\n".join(field_lines) + "\n}"
    intent = getattr(signature, "intent", "") or getattr(signature, "description", "")
    return (
        f"{intent}\n\n"
        "Read the user's reply and extract the structured values below. "
        "Respond with ONLY a single JSON object matching this schema "
        "(no prose, no markdown fences):\n"
        f"{schema}\n\n"
        f"User reply: {user_input}\n\n"
        "JSON object:"
    )


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_structured_output(signature: Signature, raw: str) -> dict[str, Any]:
    """Parse the model's response into the Signature's output fields.

    Tolerates surrounding prose / markdown fences by extracting the first
    balanced-looking JSON object. Coerces each field to its declared type.
    Raises ``ValueError`` if no JSON object is found or a required field is
    missing — the caller maps this to ``InvalidStateTransitionError``.
    """
    match = _JSON_OBJECT_RE.search(raw or "")
    if not match:
        raise ValueError(f"model response contained no JSON object: {raw[:200]!r}")
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"model response was not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"model response JSON was not an object: {type(parsed).__name__}")

    result: dict[str, Any] = {}
    for name, spec in signature.output_fields.items():
        if name not in parsed:
            raise ValueError(f"model response missing required field {name!r}")
        result[name] = _coerce(parsed[name], spec.get("type"))
    return result


def _coerce(value: Any, declared_type: Any) -> Any:
    """Best-effort coercion of a parsed JSON value to the declared Python type.

    int/float/bool/str scalars are coerced; list/dict pass through. A coercion
    failure raises ``ValueError`` (mapped to InvalidStateTransitionError) rather
    than silently dropping the value.
    """
    if declared_type is None:
        return value
    try:
        if declared_type is int:
            return int(value)
        if declared_type is float:
            return float(value)
        if declared_type is bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in ("true", "yes", "1")
            return bool(value)
        if declared_type is str:
            return str(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"could not coerce {value!r} to {getattr(declared_type, '__name__', declared_type)}"
        ) from exc
    # list / dict / other — pass through unchanged.
    return value


def _extract_chat_content(result: Any) -> str:
    """Pull the assistant text out of a legacy provider chat result.

    Handles the Ollama native shape (``{"message": {"content": ...}}``), the
    OpenAI-style ``{"content": ...}`` / ``{"text": ...}``, and a bare string.
    """
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        message = result.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
        for key in ("content", "text", "response"):
            value = result.get(key)
            if isinstance(value, str):
                return value
    return str(result)
