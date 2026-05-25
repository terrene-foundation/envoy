"""Foundation Health Heartbeat error taxonomy.

The ten typed errors below are the canonical taxonomy from
`specs/foundation-health-heartbeat.md` § "Error taxonomy".

Phase 01 status (per shard 17 § 7.3 DECISION — DE-SCOPED to Phase 02 entry):
- ``PhaseDeferredError`` (Envoy-internal) is raised on every constructor /
  helper of the four deferred network/crypto modules (``star_prio``,
  ``ohttp``, ``signed_consent``, ``registry``). Phase 01 production code MUST
  NEVER call those modules; the regression grep at
  ``tests/regression/test_r2_h_02_heartbeat_stub_partition.py`` is the
  structural defense.
- ``PayloadSchemaDriftError`` and ``DuressFlagLeakageRefusedError`` ARE raised
  in Phase 01 — they are programming-error / hostile-patch traps that live
  next to the (currently stub) emit hook. See ``payload.py``.
- The other eight errors are defined but never raised in Phase 01; they
  preserve the Phase 02 re-entry contract so the real ``HeartbeatClient``
  implementation can wire them without touching any emit-site primitive.

Cross-reference: shard 17 § 7.3 mandatory Phase 01 stubs; spec §
"Error taxonomy".
"""

from __future__ import annotations


class HeartbeatError(Exception):
    """Base for every Foundation Health Heartbeat error.

    Defined so consumers can ``except HeartbeatError`` without enumerating the
    full taxonomy; matches the convention in sibling envoy packages
    (``envoy.envelope``, ``envoy.trust``).
    """


# --- The 10 spec errors (Phase 02 entry will wire the raise sites) ----------


class OHTTPRelayUnavailableError(HeartbeatError):
    """Foundation OHTTP relay unreachable; outbound IP would not be stripped.

    Spec § "Error taxonomy" row 1. Phase 02 wiring: raised by
    ``HeartbeatClient._send_via_ohttp`` when the relay refuses connection.
    """


class STARShardCorruptError(HeartbeatError):
    """STAR/Prio share split failed at client OR collector aggregation rejected malformed share."""


class DPBudgetExceededError(HeartbeatError):
    """Differential-privacy epsilon budget for a metric exhausted within reporting window."""


class kAnonymityFloorViolatedError(HeartbeatError):  # noqa: N801 — spec name preserved
    """Aggregate cohort size for a flag below k=100 floor at collector.

    Spec name retained verbatim (lowercase ``k``) to match
    ``specs/foundation-health-heartbeat.md`` § "Error taxonomy" row 4.
    """


class RitualCouplingDebounceTriggered(HeartbeatError):
    """Heartbeat send window overlaps with ritual within 24h (L-01 fix)."""


class ConsentRevokedError(HeartbeatError):
    """User cascade-revoked Foundation Health Heartbeat consent; runtime attempted send."""


class PayloadSchemaDriftError(HeartbeatError):
    """Client attempted to add field outside fixed payload schema (T-054 defense).

    PHASE 01 STATUS: ACTIVELY RAISED by
    ``envoy.heartbeat.payload._validate_payload_schema`` — this is a
    structural defense per shard 17 § 7.3 that ships in Phase 01 even though
    the emit pipeline is stubbed.
    """


class ReproducibleBuildAttestationMissingError(HeartbeatError):
    """Client cannot present reproducible-build attestation when Foundation requests verification."""


class DuressFlagLeakageRefusedError(HeartbeatError):
    """Internal attempt to add ``duress_unlock_detected`` to payload (T-041 defense).

    PHASE 01 STATUS: ACTIVELY RAISED by
    ``envoy.heartbeat.payload._validate_payload_schema`` — this is a
    structural defense per shard 17 § 7.3 that ships in Phase 01 even though
    the emit pipeline is stubbed. The defense MUST live close to the (future)
    emit hooks; raising at the payload boundary catches programming errors
    AND hostile patches before any network code runs.
    """


class RandomIdRotationOverdueWarning(Warning):
    """Per-install random ID > quarterly rotation window. Advisory only.

    Subclasses ``Warning`` (not ``HeartbeatError``) per spec table — advisory
    severity, not a send-blocking failure.
    """


# --- Envoy-internal: Phase deferral guard ----------------------------------


class PhaseDeferredError(HeartbeatError):
    """Raised by Phase-02-deferred Heartbeat modules when invoked in Phase 01.

    Per shard 17 § 7.3, the four network/crypto modules (``star_prio``,
    ``ohttp``, ``signed_consent``, ``registry``) raise this on any
    instantiation or helper call. Phase 01 production code MUST NEVER reach a
    raise site; the regression grep at
    ``tests/regression/test_r2_h_02_heartbeat_stub_partition.py`` enforces
    that mechanically (zero non-test imports of the four deferred modules).

    Phase 02 entry replaces the raise sites with real STAR/Prio + OHTTP +
    signed-consent + registry implementations; the regression grep flips green
    automatically and any premature Phase 01 caller surfaces as a HIGH finding
    BEFORE the swap lands.
    """


__all__ = [
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
