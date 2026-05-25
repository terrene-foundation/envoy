"""envoy.model.response_filter — Stage 1 (token-budget) of the spec's
4-stage response-filter pipeline.

Per `specs/model-adapter.md` § Response filter (lines 39-47) + shard 13
§ 3.4 (`workspaces/phase-01-mvp/01-analysis/13-model-adapter-
implementation.md`).

The spec mandates 4 stages on every model response: (1) token-budget
check, (2) leak-canary scan, (3) goal-drift classifier, (4) multi-turn
accumulation check. Per shard 13 § 3.4 Phase 01 partition, this module
ships Stage 1 ONLY — Stages 2-4 are spec-acknowledged Phase 04 deferrals
(canary corpus governance, classifier calibration, session-state). The
Phase 04 typed errors (:class:`TrainingDataLeakCanaryHitError`,
:class:`GoalDriftDetectedError`,
:class:`AccumulatedInjectionDetectedError`) are defined in
:mod:`envoy.model.errors` for ``except`` taxonomy stability but are
never raised by this module in Phase 01.

Stage 1 (T-094 defense per spec line 41): the response's byte length
MUST be ≤ ``envelope.tool_output_budget_bytes``. On exceed:

* :meth:`TokenBudgetFilter.check` emits a ``model_response_filter_token_
  budget`` Ledger entry per spec § Cross-domain consumer mapping line 60
  + shard 13 § 5.6.
* When ``downstream_consumption_allowed`` is False (the caller has
  determined the envelope forbids feeding truncated output forward),
  it raises :class:`ResponseTokenBudgetExceededError` per spec line 68.
* When ``downstream_consumption_allowed`` is True, it returns the bytes
  truncated to the budget with an explicit sentinel suffix so downstream
  consumers can detect the truncation.

The sentinel format is documented as part of the spec contract — it MUST
be grep-able in audit logs per ``rules/observability.md`` Rule 6.2
(uniform mask form).
"""

from __future__ import annotations

import logging
from typing import Final

from envoy.ledger.facade import EnvoyLedger
from envoy.model.errors import ResponseTokenBudgetExceededError

logger = logging.getLogger("envoy.model.response_filter")

#: Public sentinel marking a truncation. Grep-able per
#: ``rules/observability.md`` Rule 6.2 (uniform mask form). Operators
#: searching ``audit.log`` for ``ENVOY_TRUNCATED_T094`` find every Stage
#: 1 truncation in one query.
TRUNCATION_SENTINEL: Final[bytes] = b"\n<!-- ENVOY_TRUNCATED_T094 -->"


class TokenBudgetFilter:
    """Stage 1 of the spec's 4-stage response filter pipeline.

    Per spec line 41 + § Error taxonomy line 68 + shard 13 § 3.4 row 1.

    Args:
        ledger: The Envoy Ledger facade (shard 6 T-01-18). Used to emit
            the ``model_response_filter_token_budget`` audit entry on
            every truncation.
    """

    def __init__(self, ledger: EnvoyLedger) -> None:
        self._ledger = ledger

    async def check(
        self,
        response_bytes: bytes,
        *,
        tool_output_budget_bytes: int,
        action_id: str,
        downstream_consumption_allowed: bool = True,
    ) -> bytes:
        """Apply the token-budget check; truncate + Ledger-emit on
        exceed.

        Per spec § Response filter line 41 + § Error taxonomy line 68.

        Args:
            response_bytes: The raw model-response bytes (already
                serialized — the filter does not inspect JSON/text shape,
                only length per the T-094 byte-count defense).
            tool_output_budget_bytes: The envelope's
                ``tool_output_budget_bytes`` ceiling per
                :mod:`specs/envelope-model.md`. MUST be > 0; the filter
                raises ``ValueError`` on non-positive budgets (fail-loud
                per ``rules/zero-tolerance.md`` Rule 3a).
            action_id: Correlation id linking this filter call to the
                originating action's Ledger entries per
                ``rules/observability.md`` Rule 2.
            downstream_consumption_allowed: When False, an over-budget
                response raises :class:`ResponseTokenBudgetExceededError`
                per spec line 68 ("refuse downstream feed"). When True
                (default), the filter truncates with
                :data:`TRUNCATION_SENTINEL` and returns the truncated
                bytes; the Ledger entry is emitted either way.

        Returns:
            ``response_bytes`` unchanged when ``len(response_bytes) <=
            tool_output_budget_bytes``; otherwise the truncated payload
            (when downstream consumption is allowed).

        Raises:
            ValueError: ``tool_output_budget_bytes <= 0``.
            ResponseTokenBudgetExceededError: response exceeded budget
                AND ``downstream_consumption_allowed`` is False.
        """
        if tool_output_budget_bytes <= 0:
            raise ValueError(
                f"tool_output_budget_bytes must be > 0 (got "
                f"{tool_output_budget_bytes}) — non-positive budgets are a "
                f"misconfiguration per specs/envelope-model.md § Schema. "
                f"Fail-loud per rules/zero-tolerance.md Rule 3a rather "
                f"than silently truncate every response to zero bytes."
            )

        response_len = len(response_bytes)
        if response_len <= tool_output_budget_bytes:
            logger.debug(
                "model.token_budget_filter.ok",
                extra={
                    "action_id": action_id,
                    "response_bytes": response_len,
                    "budget_bytes": tool_output_budget_bytes,
                },
            )
            return response_bytes

        # Over budget. Emit the Ledger entry first so the audit trail
        # exists even if downstream-consumption-blocked path raises.
        logger.warning(
            "model.token_budget_filter.exceeded",
            extra={
                "action_id": action_id,
                "response_bytes": response_len,
                "budget_bytes": tool_output_budget_bytes,
                "downstream_consumption_allowed": downstream_consumption_allowed,
            },
        )
        await self._ledger.append(
            entry_type="model_response_filter_token_budget",
            content={
                "action_id": action_id,
                "response_bytes": response_len,
                "budget_bytes": tool_output_budget_bytes,
                "downstream_consumption_allowed": downstream_consumption_allowed,
                "truncation_sentinel": TRUNCATION_SENTINEL.decode("ascii"),
            },
            intent_id=action_id,
        )

        if not downstream_consumption_allowed:
            raise ResponseTokenBudgetExceededError(
                f"response_bytes={response_len} exceeded "
                f"tool_output_budget_bytes={tool_output_budget_bytes} AND "
                f"downstream_consumption_allowed=False (envelope forbids "
                f"feeding the truncated payload forward per "
                f"specs/model-adapter.md line 68). action_id={action_id!r}."
            )

        # Truncate so the SENTINEL fits within the budget. The sentinel
        # length is fixed and short; for any reasonable budget the
        # head-truncation + sentinel concatenation produces a payload
        # ≤ budget. Defensive guard against a budget smaller than the
        # sentinel itself: in that pathological case, the returned
        # payload is exactly the budget-prefix with no sentinel (the
        # Ledger entry remains the audit signal).
        sentinel_len = len(TRUNCATION_SENTINEL)
        if tool_output_budget_bytes > sentinel_len:
            head_keep = tool_output_budget_bytes - sentinel_len
            truncated = response_bytes[:head_keep] + TRUNCATION_SENTINEL
        else:
            truncated = response_bytes[:tool_output_budget_bytes]
        return truncated


__all__ = ["TRUNCATION_SENTINEL", "TokenBudgetFilter"]
