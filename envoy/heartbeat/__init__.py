"""envoy.heartbeat — Foundation Health Heartbeat 5-stub partition (R2-H-02).

Phase 01 status (per shard 17 § 7.3 DECISION — DE-SCOPED to Phase 02 entry):

Two structurally distinct categories of stub live here. Conflating them was
the failure mode Round 2 R2-H-02 caught; the partition is the structural
defense.

1. ``HeartbeatClient`` (``client.py``) — GENUINE NO-OP. Production code
   CALLS this on the hot path (the 21 emit-site primitives invoke
   ``maybe_record_flag(flag_name)`` as a one-line counter increment when
   they ship in Wave 2/3/4). The method body is a literal ``pass``; no
   exception, no Ledger entry, no network call.

2. ``StarPrioClient`` / ``OhttpClient`` / ``SignedConsentRecorder`` /
   ``HeartbeatRegistryClient`` (``star_prio.py`` / ``ohttp.py`` /
   ``signed_consent.py`` / ``registry.py``) — RAISE ``PhaseDeferredError``
   on instantiation OR helper call. Phase 01 production code MUST NEVER
   call these. The regression grep at
   ``tests/regression/test_r2_h_02_heartbeat_stub_partition.py`` enforces
   zero non-test imports of the four deferred modules.

Structural defenses that DO ship in Phase 01 (per shard 17 § 7.3):

- ``HeartbeatPayload`` (``payload.py``) — frozen 21-flag dataclass.
- ``_validate_payload_schema`` (``payload.py``) — T-054 covert-channel
  defense (rejects any flag outside the 21-flag whitelist) AND T-041 duress-
  flag-leakage defense (rejects ``duress_unlock_detected`` even when
  present). Both raise their typed errors from ``errors.py``.
- The full 10-error taxonomy (``errors.py``) — defined Phase 01 so Phase 02
  entry can wire raise sites without adding new exception classes.

Per ``rules/orphan-detection.md`` Rule 6, every name re-exported in
``__all__`` is imported at module scope so the public-facade contract is
auditable by ``ast.parse``.
"""

from __future__ import annotations

from envoy.heartbeat.client import HeartbeatClient
from envoy.heartbeat.errors import (
    ConsentRevokedError,
    DPBudgetExceededError,
    DuressFlagLeakageRefusedError,
    HeartbeatError,
    OHTTPRelayUnavailableError,
    PayloadSchemaDriftError,
    PhaseDeferredError,
    RandomIdRotationOverdueWarning,
    ReproducibleBuildAttestationMissingError,
    RitualCouplingDebounceTriggered,
    STARShardCorruptError,
    kAnonymityFloorViolatedError,
)
from envoy.heartbeat.payload import (
    ALLOWED_FLAGS,
    DURESS_FLAG_NEVER_REPORTED,
    HeartbeatPayload,
    _validate_payload_schema,
)

__all__ = [
    # Phase 01 hot-path no-op consumer.
    "HeartbeatClient",
    # Phase 01 structural defenses (T-054, T-041).
    "HeartbeatPayload",
    "ALLOWED_FLAGS",
    "DURESS_FLAG_NEVER_REPORTED",
    "_validate_payload_schema",
    # Error taxonomy.
    "HeartbeatError",
    "OHTTPRelayUnavailableError",
    "STARShardCorruptError",
    "DPBudgetExceededError",
    "kAnonymityFloorViolatedError",
    "RitualCouplingDebounceTriggered",
    "ConsentRevokedError",
    "PayloadSchemaDriftError",
    "ReproducibleBuildAttestationMissingError",
    "DuressFlagLeakageRefusedError",
    "RandomIdRotationOverdueWarning",
    "PhaseDeferredError",
]
