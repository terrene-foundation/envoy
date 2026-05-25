"""envoy.boundary_conversation.bet12_telemetry — per-state EC-1 telemetry hook.

``BET12TelemetryHook`` emits per-state latency + retry-count Ledger entries plus
a final conversation-duration summary, supporting the EC-1 acceptance gate
measurement (BET-12 palatability falsifiability).

Per `workspaces/phase-01-mvp/01-analysis/08-boundary-conversation-implementation.md`
§ 3.4 + § 5.4 + § 6.1 row "test_boundary_conversation_bet12_latency_telemetry":

* ``state_entered(ritual_id, state)`` — marks state entry.
* ``state_completed(ritual_id, state, latency_ms, retry_count)`` — per-state
  measurement appended to the Ledger.
* ``conversation_completed(ritual_id, total_duration_seconds)`` — final summary;
  EC-1 boundary is ``total_duration_seconds <= 25 * 60``.

Every emission is an ``EnvoyLedger.append`` call carrying the ritual_id as
correlation id. NEVER logs the visible-secret phrase or any PII — the telemetry
content is latency / retry counts / state ids only (§ 5.3 extraction-summary
privacy).

Composes the Ledger explicitly (no global lookup) per
`rules/facade-manager-detection.md` Rule 3.
"""

from __future__ import annotations

import logging

from envoy.ledger.facade import EnvoyLedger

__all__ = ["BET12TelemetryHook", "EC1_MAX_DURATION_SECONDS"]

logger = logging.getLogger(__name__)

# EC-1 acceptance-gate boundary per `02-mvp-objectives.md` EC-1: a first-time
# user MUST complete the Boundary Conversation in <= 25 minutes.
EC1_MAX_DURATION_SECONDS = 25 * 60

# Ledger entry types for the BET-12 telemetry stream (per spec § Ledger entry
# types; these are conversation-telemetry rows distinct from the per-transition
# ReasoningCommit rows the runtime emits).
_ENTRY_STATE_ENTERED = "boundary_conversation_state_entered"
_ENTRY_STATE_COMPLETED = "boundary_conversation_state_completed"
_ENTRY_CONVERSATION_COMPLETED = "boundary_conversation_completed"


class BET12TelemetryHook:
    """Emit per-state EC-1 telemetry through the Envoy Ledger.

    Stateless apart from the injected Ledger. The runtime calls
    ``state_entered`` / ``state_completed`` around each per-state turn and
    ``conversation_completed`` once at S10.
    """

    def __init__(self, *, ledger: EnvoyLedger) -> None:
        self._ledger = ledger

    async def state_entered(self, ritual_id: str, state: str) -> str:
        """Emit a state-entered telemetry row. Returns the Ledger entry_id."""
        logger.info(
            "bet12.state_entered",
            extra={"ritual_id": ritual_id, "state": state},
        )
        return await self._ledger.append(
            entry_type=_ENTRY_STATE_ENTERED,
            content={"ritual_id": ritual_id, "state": state},
        )

    async def state_completed(
        self,
        ritual_id: str,
        state: str,
        latency_ms: int,
        retry_count: int,
    ) -> str:
        """Emit a per-state completion measurement (latency + retries).

        ``latency_ms`` and ``retry_count`` MUST be non-negative integers. The
        content carries ONLY latency / retry / state-id — never the user's
        answer or any extracted PII (§ 5.3 extraction-summary privacy).
        Returns the Ledger entry_id.
        """
        if not isinstance(latency_ms, int) or latency_ms < 0:
            raise ValueError(f"latency_ms must be a non-negative int (got {latency_ms!r})")
        if not isinstance(retry_count, int) or retry_count < 0:
            raise ValueError(f"retry_count must be a non-negative int (got {retry_count!r})")
        logger.info(
            "bet12.state_completed",
            extra={
                "ritual_id": ritual_id,
                "state": state,
                "latency_ms": latency_ms,
                "retry_count": retry_count,
            },
        )
        return await self._ledger.append(
            entry_type=_ENTRY_STATE_COMPLETED,
            content={
                "ritual_id": ritual_id,
                "state": state,
                "latency_ms": latency_ms,
                "retry_count": retry_count,
            },
        )

    async def conversation_completed(self, ritual_id: str, total_duration_seconds: int) -> str:
        """Emit the final conversation-duration summary (EC-1 measurement).

        ``total_duration_seconds`` MUST be a non-negative int. The content
        carries a ``within_ec1_budget`` boolean (``<= EC1_MAX_DURATION_SECONDS``)
        so a downstream EC-1 acceptance-gate query reads the verdict directly
        rather than re-deriving the boundary. A breach is logged at WARN per
        `rules/observability.md` Rule 3 (degraded path) but does NOT raise — the
        telemetry records reality; the acceptance gate adjudicates. Returns the
        Ledger entry_id.
        """
        if not isinstance(total_duration_seconds, int) or total_duration_seconds < 0:
            raise ValueError(
                f"total_duration_seconds must be a non-negative int (got "
                f"{total_duration_seconds!r})"
            )
        within_budget = total_duration_seconds <= EC1_MAX_DURATION_SECONDS
        if not within_budget:
            logger.warning(
                "bet12.conversation_completed.ec1_budget_exceeded",
                extra={
                    "ritual_id": ritual_id,
                    "total_duration_seconds": total_duration_seconds,
                    "ec1_budget_seconds": EC1_MAX_DURATION_SECONDS,
                },
            )
        else:
            logger.info(
                "bet12.conversation_completed",
                extra={
                    "ritual_id": ritual_id,
                    "total_duration_seconds": total_duration_seconds,
                },
            )
        return await self._ledger.append(
            entry_type=_ENTRY_CONVERSATION_COMPLETED,
            content={
                "ritual_id": ritual_id,
                "total_duration_seconds": total_duration_seconds,
                "within_ec1_budget": within_budget,
            },
        )
