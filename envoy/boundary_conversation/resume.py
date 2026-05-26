"""envoy.boundary_conversation.resume — Trust-Vault-backed per-state persistence.

``RitualResumeCoordinator`` is the thin coordinator the runtime uses to (a)
persist the in-flight conversation state after every transition and (b)
rehydrate it on ``envoy init --resume <ritual_id>``.

Per `specs/boundary-conversation.md` § Persistence + resume (lines 33–35) +
`workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md`
§ 3.3 + § 5.2:

* ``persist_state`` round-trips ``Plan.to_dict()`` + the assembler's
  ``to_dict()`` through ``TrustStoreAdapter.persist_boundary_conversation_state``.
* ``load_state`` reads back via ``load_boundary_conversation_state`` and
  reconstructs ``(Plan, EnvelopeConfigInputAssembler, current_state)``; absence
  maps the store's ``None`` to the typed ``RitualResumeStateMissingError`` (the
  error lives in THIS package, not the trust store — § 5.2).
* ``list_pending_rituals`` enumerates the rituals persisted for a principal in
  this session (the store exposes no cross-session by-principal query in Phase
  01; the in-process index is the contract-complete Phase-01 answer + the P02
  query swaps in behind the same signature).

Composes the trust store explicitly (no global lookup) per
`rules/facade-manager-detection.md` Rule 3.
"""

from __future__ import annotations

import logging

from kaizen.l3.plan.types import Plan

from envoy.boundary_conversation.envelope_assembler import EnvelopeConfigInputAssembler
from envoy.boundary_conversation.errors import RitualResumeStateMissingError
from envoy.trust.store import TrustStoreAdapter

__all__ = ["RitualResumeCoordinator", "ResumedRitual"]

logger = logging.getLogger(__name__)


class ResumedRitual:
    """The reconstructed in-flight conversation state for one ritual_id.

    Carries the rehydrated ``Plan``, the rehydrated
    ``EnvelopeConfigInputAssembler``, the ``current_state`` node-id, and the
    owning ``principal_id`` so the runtime can resume from the next prompt.
    """

    __slots__ = ("ritual_id", "principal_id", "current_state", "plan", "assembler")

    def __init__(
        self,
        *,
        ritual_id: str,
        principal_id: str,
        current_state: str,
        plan: Plan,
        assembler: EnvelopeConfigInputAssembler,
    ) -> None:
        self.ritual_id = ritual_id
        self.principal_id = principal_id
        self.current_state = current_state
        self.plan = plan
        self.assembler = assembler


class RitualResumeCoordinator:
    """Persist + rehydrate Boundary Conversation per-state progress.

    Explicit-DI: takes the ``TrustStoreAdapter`` the runtime owns. Stateless
    apart from an in-process per-principal index of rituals seen this session
    (powering ``list_pending_rituals`` until the Phase-02 store query lands).
    """

    def __init__(self, *, trust_store: TrustStoreAdapter) -> None:
        self._trust_store = trust_store
        # principal_id -> set of ritual_ids persisted this session. Bounded by
        # session lifetime; cross-session enumeration is a Phase-02 store query
        # (the store exposes no by-principal ritual query in Phase 01).
        self._session_rituals: dict[str, set[str]] = {}

    async def persist_state(
        self,
        ritual_id: str,
        *,
        plan: Plan,
        assembler: EnvelopeConfigInputAssembler,
        principal_id: str,
        current_state: str,
    ) -> None:
        """Persist the in-flight conversation state after a transition.

        Round-trips ``Plan.to_dict()`` + ``assembler.to_dict()`` through the
        trust store. Upsert semantics (one row per ritual_id) live in the store.
        """
        logger.info(
            "ritual_resume.persist.start",
            extra={"ritual_id": ritual_id, "current_state": current_state},
        )
        await self._trust_store.persist_boundary_conversation_state(
            ritual_id,
            plan_dict=plan.to_dict(),
            assembler_dict=assembler.to_dict(),
            principal_id=principal_id,
            current_state=current_state,
        )
        self._session_rituals.setdefault(principal_id, set()).add(ritual_id)
        logger.info(
            "ritual_resume.persist.ok",
            extra={"ritual_id": ritual_id, "current_state": current_state},
        )

    async def load_state(self, ritual_id: str) -> ResumedRitual:
        """Rehydrate the in-flight conversation state for ``ritual_id``.

        Raises ``RitualResumeStateMissingError(ritual_id)`` when the store
        returns ``None`` (the user named a ritual_id absent from the Trust
        Vault). Reconstructs the ``Plan`` via ``Plan.from_dict`` and the
        assembler via ``EnvelopeConfigInputAssembler.from_dict``.
        """
        logger.info("ritual_resume.load.start", extra={"ritual_id": ritual_id})
        row = await self._trust_store.load_boundary_conversation_state(ritual_id)
        if row is None:
            logger.warning("ritual_resume.load.missing", extra={"ritual_id": ritual_id})
            raise RitualResumeStateMissingError(ritual_id)
        plan = Plan.from_dict(row.plan_dict)
        assembler = EnvelopeConfigInputAssembler.from_dict(row.assembler_dict)
        # Re-index so a load followed by list_pending_rituals in the same session
        # surfaces the resumed ritual.
        self._session_rituals.setdefault(row.principal_id, set()).add(ritual_id)
        logger.info(
            "ritual_resume.load.ok",
            extra={"ritual_id": ritual_id, "current_state": row.current_state},
        )
        return ResumedRitual(
            ritual_id=row.ritual_id,
            principal_id=row.principal_id,
            current_state=row.current_state,
            plan=plan,
            assembler=assembler,
        )

    def list_pending_rituals(self, principal_id: str) -> list[str]:
        """List ritual_ids persisted for ``principal_id`` in this session.

        Phase 01: the trust store exposes no cross-session by-principal ritual
        query, so the coordinator returns the rituals it persisted/loaded in the
        current session (sorted for determinism). Phase 02 swaps in a real store
        query behind this signature when the by-principal index lands.
        """
        return sorted(self._session_rituals.get(principal_id, set()))
