"""Signed-consent Delegation Record recorder — Phase 02 entry deliverable.

Per shard 17 § 7.3 mandatory Phase 01 stub #4 (R2-H-02 partition). Every
constructor and module-level helper raises ``PhaseDeferredError`` on call.
Phase 01 production code MUST NEVER reach a raise site; the regression grep
at ``tests/regression/test_r2_h_02_heartbeat_stub_partition.py`` enforces
zero non-test imports of this module.

Phase 02 entry replaces these raise sites with a real signed-consent
recorder per ``specs/foundation-health-heartbeat.md`` § "Consent layer"
(first-run Grant Moment producing signed Delegation Record; cascade-
revocable; default opt-OUT).

Note: the ``FoundationHealthHeartbeatConsent`` ledger entry type IS
reserved in Phase 01 (per shard 17 § 7.3 stub #1 wiring through the existing
Ledger writer). This module covers the heartbeat-side consent emission path
that the Foundation aggregator consumes — NOT the ledger entry type itself.
"""

from __future__ import annotations

from envoy.heartbeat.errors import PhaseDeferredError

_PHASE_DEFERRED_MSG = (
    "envoy.heartbeat.signed_consent is a Phase 02 entry deliverable per "
    "shard 17 DECISION; Phase 01 production code MUST NEVER instantiate or "
    "call into this module. See specs/foundation-health-heartbeat.md § "
    "'Consent layer' for the Phase 02 contract."
)


class SignedConsentRecorder:
    """Placeholder for the Phase 02 signed-consent recorder.

    Raises ``PhaseDeferredError`` on any instantiation attempt — this is the
    intended Phase 01 behavior per shard 17 § 7.3.
    """

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise PhaseDeferredError(_PHASE_DEFERRED_MSG)


def record_grant_moment(*_args: object, **_kwargs: object) -> None:
    """Placeholder for the Phase 02 Grant Moment signed-consent emitter.

    Raises ``PhaseDeferredError`` on call.
    """
    raise PhaseDeferredError(_PHASE_DEFERRED_MSG)


def record_cascade_revoke(*_args: object, **_kwargs: object) -> None:
    """Placeholder for the Phase 02 cascade-revoke emitter.

    Raises ``PhaseDeferredError`` on call.
    """
    raise PhaseDeferredError(_PHASE_DEFERRED_MSG)


__all__ = [
    "SignedConsentRecorder",
    "record_grant_moment",
    "record_cascade_revoke",
]
