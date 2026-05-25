"""envoy.model.errors — typed error taxonomy for the model adapter.

Per `specs/model-adapter.md` § Error taxonomy (lines 62-73) — 8 typed errors
plus a shared base. The Phase 01 implementation raises:

* :class:`ProviderUnreachableError` — provider endpoint 5xx / network failure
  (raised by chat-completion call sites in T-02-40 Boundary Conversation; the
  router itself does not invoke the network).
* :class:`ProviderRiskAnnotationMissingError` — fail-closed check in
  :class:`envoy.model.risk.EnvoyProviderRiskAnnotator.fail_closed_check` when
  ``risk_class == "Provider-bound"`` and the active envelope does not allow
  ``provider_bound: true`` (per spec line 36).
* :class:`ResponseTokenBudgetExceededError` — raised by
  :class:`envoy.model.response_filter.TokenBudgetFilter.check` when the
  response exceeds ``tool_output_budget_bytes`` AND the caller flagged the
  excess as forbidden by the envelope (per spec line 68).
* :class:`ProviderSwitchRefusedByEnvelopeError` — raised by
  :class:`envoy.model.router.EnvoyModelRouter.for_primitive` when the picked
  deployment's :meth:`LlmDeployment.supports` capability matrix does not
  satisfy the primitive's required capabilities (per shard 13 § 3.2).

The remaining four errors — :class:`TrainingDataLeakCanaryHitError`,
:class:`GoalDriftDetectedError`, :class:`AccumulatedInjectionDetectedError`,
:class:`MultiProviderConsensusFailedError` — correspond to Phase 04 response
filter stages 2-4 + multi-provider verification (shard 13 § 3.4 + § 3.5).
They are defined here in the canonical taxonomy module so downstream
``except`` handlers can name them at import time without a Phase 04 forward
reference; their first ``raise`` sites land with the Phase 04
implementations. This is NOT a stub per `rules/zero-tolerance.md` Rule 2 —
typed exception classes are part of the spec contract, and their import-only
presence in Phase 01 is what Phase 04 wires raise into.
"""

from __future__ import annotations


class ModelAdapterError(Exception):
    """Base for every typed error in :mod:`envoy.model`.

    Callers MAY ``except ModelAdapterError`` to catch the taxonomy as a whole;
    operators reading logs SHOULD pin against the leaf class per
    ``rules/observability.md`` Rule 3 (distinct log levels per intent).
    """


class ProviderUnreachableError(ModelAdapterError):
    """Provider endpoint unreachable / 5xx.

    Per spec § Error taxonomy line 66 — the runtime SHOULD switch to a
    fallback provider or pause the action. Auto-retry permitted (with
    exponential backoff per ``rules/observability.md`` Rule 7).
    """


class ProviderRiskAnnotationMissingError(ModelAdapterError):
    """Model invocation against a Provider-bound endpoint that the envelope
    does not opt into.

    Per spec § Error taxonomy line 67. Phase 01 fail-closed default per
    shard 13 § 3.3: provider-bound endpoints lacking Foundation attestation
    require an explicit ``provider_bound: true`` flag in the envelope's
    operational dimension; the runtime fails closed without it.
    """


class ResponseTokenBudgetExceededError(ModelAdapterError):
    """Response bytes exceed ``tool_output_budget_bytes``.

    Per spec § Error taxonomy line 68 + § Response filter line 41 (T-094
    defense). Phase 01 :class:`TokenBudgetFilter` truncates with a sentinel
    AND emits a Ledger entry; this error is raised when downstream
    consumption of the oversized response is forbidden by the envelope.
    """


class TrainingDataLeakCanaryHitError(ModelAdapterError):
    """Leak-canary substring match in the response (T-017 defense).

    Per spec § Error taxonomy line 69. **Phase 04 implementation** — the
    Foundation-published canary corpus (``envoy-registry:training-leak-
    canaries:v1``) is registered via :mod:`specs/foundation-ops.md` by spec
    freeze N+1. Defined here so Phase 01 callers can ``except`` against the
    typed contract.
    """


class GoalDriftDetectedError(ModelAdapterError):
    """Goal-drift classifier cosine drift > 0.4 (T-016 defense).

    Per spec § Error taxonomy line 70. **Phase 04 implementation** —
    requires intent-vector embedding + empirical cosine-threshold
    calibration (open question per spec line 99).
    """


class AccumulatedInjectionDetectedError(ModelAdapterError):
    """Session multi-turn overlap threshold breached (T-014 defense).

    Per spec § Error taxonomy line 71. **Phase 04 implementation** —
    requires the SessionObservedState wiring from
    :mod:`specs/session-state.md` which is out of Phase 01 scope.
    """


class MultiProviderConsensusFailedError(ModelAdapterError):
    """High-stakes verification: provider intent-vector cosine < 0.85
    (T-030 defense).

    Per spec § Error taxonomy line 72 + § Multi-provider verification
    line 49. **Phase 04 implementation** — Phase 01 does NOT invoke
    multi-provider verification per shard 13 § 3.5.
    """


class ProviderSwitchRefusedByEnvelopeError(ModelAdapterError):
    """Runtime ``model_switch`` blocked because the deployment's capability
    matrix does not satisfy the primitive's required capabilities.

    Per spec § Error taxonomy line 73 + shard 13 § 3.2 ("if the user picked
    a non-tools-capable cheap preset for Daily Digest but the digest wants
    to call a tool, ``EnvoyModelRouter.for_primitive`` raises
    ``ProviderSwitchRefusedByEnvelopeError``").

    User-action: update ``envelope.operational.tool_allowlist`` OR pick a
    different preset whose ``deployment.supports()`` matrix matches the
    primitive's capability requirement.
    """


__all__ = [
    "AccumulatedInjectionDetectedError",
    "GoalDriftDetectedError",
    "ModelAdapterError",
    "MultiProviderConsensusFailedError",
    "ProviderRiskAnnotationMissingError",
    "ProviderSwitchRefusedByEnvelopeError",
    "ProviderUnreachableError",
    "ResponseTokenBudgetExceededError",
    "TrainingDataLeakCanaryHitError",
]
