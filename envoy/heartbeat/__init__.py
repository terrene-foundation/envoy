"""envoy.heartbeat — Foundation Health Heartbeat client (S11 — STAR + DP + OHTTP).

Phase 02 (S11) status — the WS-5 client crypto + k-anonymity + client-side DP:

1. ``HeartbeatClient`` (``client.py``) — the hot-path consumer. ``maybe_record_flag``
   is now the REAL pipeline (was a Phase-01 ``pass``): validate flag ->
   consent-check (the S12 seam) -> increment per-week counter; the weekly
   ``emit_weekly`` cadence runs DP-noise-before-share-split + total-ε-over-window
   per-metric budgets + the k≥100 true-cohort STAR/OHTTP emit.

2. ``StarPrioClient`` (``star_prio.py``) / ``OhttpClient`` (``ohttp.py``) /
   ``HeartbeatRegistryClient`` (``registry.py``) — REAL S11 implementations.
   ``star_prio`` ships the STAR single-server threshold share-split +
   true-cohort k-anonymity; ``ohttp`` the RFC-9458 client encapsulation with the
   EC-S11.8 identity-binding ``info``; ``registry`` the operator-signature +
   aggregator-endpoint handshake against S10's Key Configuration Server.

3. ``SignedConsentRecorder`` (``signed_consent.py``) — STILL deferred to S12.
   It raises ``PhaseDeferredError`` until S12 fills the signed-consent Grant
   Moment + cascade-revoke. The regression grep at
   ``tests/regression/test_r2_h_02_heartbeat_stub_partition.py`` still enforces
   zero non-test imports of ``signed_consent`` (the lone remaining deferred
   module); ``star_prio`` / ``ohttp`` / ``registry`` are now real production
   modules the client imports.

Structural defenses that ship across phases (per shard 17 § 7.3):

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

from envoy.heartbeat.client import (
    DEFAULT_METRIC_EPSILON,
    RITUAL_DEBOUNCE,
    ConsentGate,
    DPBudget,
    HeartbeatClient,
    OptOutConsentGate,
    add_laplace_noise,
)
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
from envoy.heartbeat.ohttp import OhttpClient, build_ohttp_info
from envoy.heartbeat.payload import (
    ALLOWED_FLAGS,
    DURESS_FLAG_NEVER_REPORTED,
    HeartbeatPayload,
    _validate_payload_schema,
)
from envoy.heartbeat.registry import AggregatorEndpoint, HeartbeatRegistryClient
from envoy.heartbeat.star_prio import (
    K_ANONYMITY_FLOOR,
    CohortRevelation,
    StarPrioClient,
    StarShare,
    check_client_side_k_anonymity,
    derive_recovery_key,
    group_cohorts,
    recover_cohort,
    split_into_shares,
)

__all__ = [
    # Hot-path consumer + S11 client pipeline.
    "HeartbeatClient",
    "ConsentGate",
    "OptOutConsentGate",
    "DPBudget",
    "DEFAULT_METRIC_EPSILON",
    "RITUAL_DEBOUNCE",
    "add_laplace_noise",
    # STAR client crypto + k-anonymity.
    "StarPrioClient",
    "StarShare",
    "CohortRevelation",
    "K_ANONYMITY_FLOOR",
    "derive_recovery_key",
    "split_into_shares",
    "check_client_side_k_anonymity",
    "recover_cohort",
    "group_cohorts",
    # OHTTP client + registry handshake.
    "OhttpClient",
    "build_ohttp_info",
    "HeartbeatRegistryClient",
    "AggregatorEndpoint",
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
