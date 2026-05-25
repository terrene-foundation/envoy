"""STAR/Prio share-split client — Phase 02 entry deliverable.

Per shard 17 § 7.3 mandatory Phase 01 stub #2 (R2-H-02 partition). Every
constructor and module-level helper here raises ``PhaseDeferredError`` on
call. Phase 01 production code MUST NEVER reach a raise site; the regression
grep at ``tests/regression/test_r2_h_02_heartbeat_stub_partition.py``
enforces zero non-test imports of this module.

Phase 02 entry replaces these raise sites with a real STAR (Signer-Anonymous
Reporting Telemetry) / Prio share-split client per
``specs/foundation-health-heartbeat.md`` § "Design stack" item 1
(k-anonymity k>=100; share entropy; per-metric DP epsilon budget tracking;
share-aggregation epoch alignment).

This module exists to preserve the Phase 02 re-entry contract: when Phase 02
swaps the body for the real implementation, the import surface is already
declared and downstream wiring code does not need to add new module paths.
"""

from __future__ import annotations

from envoy.heartbeat.errors import PhaseDeferredError

_PHASE_DEFERRED_MSG = (
    "envoy.heartbeat.star_prio is a Phase 02 entry deliverable per shard 17 "
    "DECISION; Phase 01 production code MUST NEVER instantiate or call into "
    "this module. See specs/foundation-health-heartbeat.md § 'Design stack' "
    "item 1 for the Phase 02 contract."
)


class StarPrioClient:
    """Placeholder for the Phase 02 STAR/Prio share-split client.

    Raises ``PhaseDeferredError`` on any instantiation attempt — this is the
    intended Phase 01 behavior per shard 17 § 7.3.
    """

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise PhaseDeferredError(_PHASE_DEFERRED_MSG)


def split_into_shares(*_args: object, **_kwargs: object) -> None:
    """Placeholder for the Phase 02 share-split helper.

    Raises ``PhaseDeferredError`` on call.
    """
    raise PhaseDeferredError(_PHASE_DEFERRED_MSG)


def check_client_side_k_anonymity(*_args: object, **_kwargs: object) -> None:
    """Placeholder for the Phase 02 client-side k-anonymity floor check.

    Raises ``PhaseDeferredError`` on call.
    """
    raise PhaseDeferredError(_PHASE_DEFERRED_MSG)


__all__ = [
    "StarPrioClient",
    "split_into_shares",
    "check_client_side_k_anonymity",
]
