"""OHTTP (RFC 9458) client wrapper — Phase 02 entry deliverable.

Per shard 17 § 7.3 mandatory Phase 01 stub #3 (R2-H-02 partition). Every
constructor and module-level helper raises ``PhaseDeferredError`` on call.
Phase 01 production code MUST NEVER reach a raise site; the regression grep
at ``tests/regression/test_r2_h_02_heartbeat_stub_partition.py`` enforces
zero non-test imports of this module.

Phase 02 entry replaces these raise sites with a real OHTTP client per
``specs/foundation-health-heartbeat.md`` § "Design stack" item 3
(Foundation Key Configuration Server fetch + cache + expiry; relay-strips-
source-IP verification; HPKE encapsulation; request/response binding).

Foundation-side infrastructure dependencies that Phase 02 entry MUST stand
up first (per shard 17 § 3.2):
- OHTTP Key Configuration Server.
- OHTTP Relay (Foundation or third-party operator).
"""

from __future__ import annotations

from envoy.heartbeat.errors import PhaseDeferredError

_PHASE_DEFERRED_MSG = (
    "envoy.heartbeat.ohttp is a Phase 02 entry deliverable per shard 17 "
    "DECISION; Phase 01 production code MUST NEVER instantiate or call into "
    "this module. See specs/foundation-health-heartbeat.md § 'Design stack' "
    "item 3 (RFC 9458) for the Phase 02 contract."
)


class OhttpClient:
    """Placeholder for the Phase 02 OHTTP (RFC 9458) client wrapper.

    Raises ``PhaseDeferredError`` on any instantiation attempt — this is the
    intended Phase 01 behavior per shard 17 § 7.3.
    """

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise PhaseDeferredError(_PHASE_DEFERRED_MSG)


def fetch_key_configuration(*_args: object, **_kwargs: object) -> None:
    """Placeholder for the Phase 02 OHTTP Key Configuration Server fetch.

    Raises ``PhaseDeferredError`` on call.
    """
    raise PhaseDeferredError(_PHASE_DEFERRED_MSG)


def encapsulate_request(*_args: object, **_kwargs: object) -> None:
    """Placeholder for the Phase 02 HPKE encapsulation helper.

    Raises ``PhaseDeferredError`` on call.
    """
    raise PhaseDeferredError(_PHASE_DEFERRED_MSG)


__all__ = [
    "OhttpClient",
    "fetch_key_configuration",
    "encapsulate_request",
]
