"""Foundation Key Configuration Server registry handshake — Phase 02 entry.

Per shard 17 § 7.3 mandatory Phase 01 stub #5 (R2-H-02 partition). Every
constructor and module-level helper raises ``PhaseDeferredError`` on call.
Phase 01 production code MUST NEVER reach a raise site; the regression grep
at ``tests/regression/test_r2_h_02_heartbeat_stub_partition.py`` enforces
zero non-test imports of this module.

Phase 02 entry replaces these raise sites with a real registry-handshake
client per ``specs/foundation-ops.md`` § "Infrastructure inventory" row 3
(Foundation OHTTP Key Configuration Server registry — published key schema,
operator-signed configuration, expiry/rotation cadence).

Foundation-side infrastructure dependency that Phase 02 entry MUST stand up
first: the Foundation Key Configuration Server itself (per shard 17 § 3.2:
no deployment plan, no operator, no published key registry as of the shard
DECISION).
"""

from __future__ import annotations

from envoy.heartbeat.errors import PhaseDeferredError

_PHASE_DEFERRED_MSG = (
    "envoy.heartbeat.registry is a Phase 02 entry deliverable per shard 17 "
    "DECISION; Phase 01 production code MUST NEVER instantiate or call into "
    "this module. See specs/foundation-ops.md § 'Infrastructure inventory' "
    "row 3 for the Phase 02 Foundation-ops dependency."
)


class HeartbeatRegistryClient:
    """Placeholder for the Phase 02 Foundation registry-handshake client.

    Raises ``PhaseDeferredError`` on any instantiation attempt — this is the
    intended Phase 01 behavior per shard 17 § 7.3.
    """

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise PhaseDeferredError(_PHASE_DEFERRED_MSG)


def fetch_aggregator_endpoint(*_args: object, **_kwargs: object) -> None:
    """Placeholder for the Phase 02 STAR/Prio aggregator endpoint discovery.

    Raises ``PhaseDeferredError`` on call.
    """
    raise PhaseDeferredError(_PHASE_DEFERRED_MSG)


def verify_operator_signature(*_args: object, **_kwargs: object) -> None:
    """Placeholder for the Phase 02 operator-signed configuration verifier.

    Raises ``PhaseDeferredError`` on call.
    """
    raise PhaseDeferredError(_PHASE_DEFERRED_MSG)


__all__ = [
    "HeartbeatRegistryClient",
    "fetch_aggregator_endpoint",
    "verify_operator_signature",
]
