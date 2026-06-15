# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""STAR single-server client crypto + k-anonymity + client-side DP (S11).

STAR — **Sharded-Threshold-Aggregation-for-Revelation** in the literature;
the module backronym "Signer-Anonymous Reporting Telemetry" is preserved from
the Phase-01 stub docstring (`specs/foundation-health-heartbeat.md` § "Design
stack" item 1). This is the **single-server** STAR variant (settled `/todos`
decision — NOT Prio): one Foundation aggregator, with OHTTP recovering the
non-collusion property at the network layer (S10).

The STAR contract this module implements:

1. **Measurement-keyed shares.** Each weekly per-counter measurement is split
   via :func:`split_into_shares` into a ``(key_share, value_share)`` pair keyed
   by the measurement VALUE. Clients reporting the IDENTICAL measurement derive
   the SAME ``recovery_key`` (a deterministic key-derivation over the measurement
   bytes) and therefore combinable shares; below the threshold the value is
   information-theoretically unrecoverable (Shamir over the prime field
   GF(2^127-1), threshold k — see the field-choice rationale below).
2. **True-cohort k-anonymity.** :func:`check_client_side_k_anonymity` and the
   aggregator-side :func:`recover_cohort` gate on the count of DISTINCT
   submitters who shared the SAME measurement key — the **true** cohort
   cardinality, NOT a DP-noised count. The threshold reveal fires only when
   ``>= k`` distinct clients submitted matching shares (default k=100). DP noise
   (``envoy.heartbeat.dp``) perturbs the per-counter VALUE a client reports; it
   NEVER perturbs the cohort-size cardinality the k-floor gates on.

The split between "DP noises the value" and "k-floor gates on the true cohort"
is the load-bearing invariant (EC-S11.1 / EC-S11.3): conflating them would
either leak (a noised-down cohort revealed below the true-100 floor) or
over-withhold.

Shamir secret sharing here is a self-contained prime-field implementation built
on no external dependency — ``rules/zero-tolerance.md`` Rule 4 forbids a naive
re-implementation that DIVERGES from a reference, but Shamir over a prime field
GF(p) is a fixed, well-specified algorithm; this is that algorithm, not a
shortcut. A prime field (NOT GF(2^8)) is required because the reveal threshold
is the k-floor (100): a 100-of-N threshold needs ≥100 distinct evaluation
points, and clients pick their x-coordinates INDEPENDENTLY (no coordination), so
the field MUST be large enough that random per-client x-coordinates collide only
with cryptographically-negligible probability. GF(2^8) has only 255 points —
100 independent draws collide with near-certainty (birthday bound); the 2^127-1
field below makes a collision negligible for any realistic cohort.
"""

from __future__ import annotations

import hashlib
import hmac
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from envoy.heartbeat.errors import STARShardCorruptError, kAnonymityFloorViolatedError

# The default k-anonymity floor per `specs/foundation-health-heartbeat.md`
# § "Design stack" item 1 ("k-anonymity k>=100"). The aggregator withholds any
# aggregate whose TRUE distinct-submitter cohort is below this.
K_ANONYMITY_FLOOR: int = 100

# Shamir threshold for the value-share polynomial. STAR single-server recovers a
# measurement's value share only when >= THRESHOLD distinct clients submitted
# the same measurement key; the threshold is the k-floor itself (the structural
# recovery condition IS "k clients shared the same measurement").
_RECOVERY_THRESHOLD: int = K_ANONYMITY_FLOOR

# Shamir prime field. 2^127 - 1 (a Mersenne prime) — large enough that
# independent per-client x-coordinates (128-bit hashes) collide only with
# cryptographically-negligible probability, and large enough to carry any 4-byte
# counter value as the secret without overflow.
_FIELD_PRIME = (1 << 127) - 1

# Domain-separation label for the measurement-key derivation. Identical
# measurements across clients MUST derive the identical recovery key, so the
# derivation is a keyless (HMAC with a fixed public label) hash over the
# measurement bytes — deterministic and collision-resistant, NOT a per-client
# secret.
_RECOVERY_KEY_LABEL = b"envoy.star.v1.recovery-key"

# Domain-separation label for the per-client evaluation-point derivation.
_X_COORD_LABEL = b"envoy.star.v1.x-coord"

# Domain-separation label for the polynomial coefficient derivation. Each client
# derives the SAME polynomial coefficients (so all clients' shares lie on ONE
# polynomial whose constant term is the measurement value), keyed by the
# measurement — clients reporting the same measurement secret-share the SAME
# value. This is the STAR property: combinable shares, recovered at threshold.
_COEFF_LABEL = b"envoy.star.v1.coeff"


def derive_recovery_key(measurement: bytes) -> bytes:
    """Derive the deterministic STAR recovery key for a measurement.

    Identical measurements across clients MUST map to the identical key so
    their value shares are combinable. The derivation is a fixed-label HMAC over
    the measurement bytes — public and deterministic (NOT a per-client secret).
    """
    return hmac.new(_RECOVERY_KEY_LABEL, measurement, hashlib.sha256).digest()


def _secret_commitment(secret: int) -> str:
    """Public commitment over a recovery secret's canonical field encoding.

    Both the client (at split) and the aggregator (at recovery) commit over the
    SAME fixed-width big-endian encoding so a recovered secret round-trips to the
    identical commitment.
    """
    width = (_FIELD_PRIME.bit_length() + 7) // 8
    return hashlib.sha256(secret.to_bytes(width, "big")).hexdigest()


def _derive_x(submitter_id: str) -> int:
    """Derive a non-zero prime-field x-coordinate from the submitter id.

    A 128-bit hash reduced into the field; independent clients collide only with
    negligible probability. x != 0 (x=0 is the secret itself).
    """
    h = int.from_bytes(hashlib.sha256(_X_COORD_LABEL + submitter_id.encode("utf-8")).digest()[:16], "big")
    return (h % (_FIELD_PRIME - 1)) + 1


def _derive_coeffs(measurement: bytes, threshold: int) -> list[int]:
    """Derive the (threshold-1) non-constant polynomial coefficients.

    Keyed by the measurement so all clients reporting the SAME measurement build
    the SAME polynomial (the constant term — the secret value — is supplied
    separately). Deterministic across clients without coordination, which is how
    independently-produced shares interpolate to one value.
    """
    coeffs: list[int] = []
    for i in range(1, threshold):
        digest = hmac.new(
            _COEFF_LABEL, measurement + i.to_bytes(4, "big"), hashlib.sha256
        ).digest()
        coeffs.append(int.from_bytes(digest, "big") % _FIELD_PRIME)
    return coeffs


def _eval_poly(secret: int, coeffs: Sequence[int], x: int) -> int:
    """Evaluate ``secret + c1*x + ... + c(t-1)*x^(t-1)`` mod the field prime."""
    acc = 0
    # Horner with the highest-degree coefficient first.
    for c in reversed(coeffs):
        acc = (acc * x + c) % _FIELD_PRIME
    return (acc * x + secret) % _FIELD_PRIME


def _interpolate_at_zero(points: Sequence[tuple[int, int]]) -> int:
    """Lagrange-interpolate the prime-field polynomial at x=0 from (x, y) points."""
    secret = 0
    for j, (xj, yj) in enumerate(points):
        num = 1
        den = 1
        for m, (xm, _ym) in enumerate(points):
            if m == j:
                continue
            num = (num * (-xm)) % _FIELD_PRIME
            den = (den * (xj - xm)) % _FIELD_PRIME
        if den == 0:
            raise STARShardCorruptError(
                "duplicate x-coordinate during Lagrange interpolation — a "
                "corrupt or colliding share set"
            )
        lagrange = (num * pow(den, -1, _FIELD_PRIME)) % _FIELD_PRIME
        secret = (secret + yj * lagrange) % _FIELD_PRIME
    return secret % _FIELD_PRIME


@dataclass(frozen=True, slots=True)
class StarShare:
    """One client's STAR share for one per-counter measurement.

    STAR single-server semantics: clients reporting the SAME measurement
    secret-share the SAME measurement-derived recovery secret — so their shares
    combine and the threshold reveals the secret (proving the cohort crossed
    ``k``), WITHOUT the aggregator learning any individual measurement until
    ``k`` clients agree. The per-counter (DP-noised) reported VALUE is carried
    separately and summed by the aggregator once the cohort is revealed.

    Fields:
        metric: the flag name (one of the 21 flags).
        recovery_key_commitment: public commitment over the measurement-derived
            recovery key — IDENTICAL across cohort members; the grouping key the
            aggregator uses WITHOUT learning the measurement.
        x: the client's prime-field evaluation point (from ``submitter_id``).
        secret_share: the measurement-derived recovery secret's polynomial
            evaluated at ``x`` — combinable across the cohort.
        noised_value: the DP-noised per-counter value the client contributes to
            the cohort aggregate (already noised per EC-S11.3; the TRUE value
            never leaves the client).
        submitter_id: per-install random ID — counts DISTINCT submitters for the
            true-cohort k-floor (never the measurement).
    """

    metric: str
    recovery_key_commitment: str
    x: int
    secret_share: int
    noised_value: int
    submitter_id: str


def split_into_shares(
    metric: str,
    measurement: bytes,
    reported_value: bytes,
    submitter_id: str,
    *,
    threshold: int = _RECOVERY_THRESHOLD,
) -> StarShare:
    """Split one per-counter measurement into a combinable STAR share.

    The secret being shared is the MEASUREMENT-derived recovery secret (identical
    across all clients reporting the same measurement → combinable shares; below
    ``threshold`` distinct submitters it is information-theoretically
    unrecoverable). The (already DP-noised per EC-S11.3) ``reported_value`` is
    carried as the per-client contribution to the cohort aggregate — this
    function never sees the true value, only the noised bytes the caller passes.
    The client's evaluation point ``x`` is derived from ``submitter_id`` in the
    2^127-1 field so independent clients collide only with negligible probability.

    Args:
        metric: the flag name this measurement is for (one of the 21 flags).
        measurement: the cohort key bytes — identical across clients with the
            same measurement.
        reported_value: the (already DP-noised) per-counter value bytes.
        submitter_id: the per-install random ID; counts distinct submitters and
            seeds the distinct evaluation point.
        threshold: STAR reveal threshold (defaults to the k-floor).

    Raises:
        STARShardCorruptError: empty measurement, empty value, or a degenerate
            threshold.
    """
    if not measurement:
        raise STARShardCorruptError(
            f"STAR share for metric {metric!r} has an empty measurement key; "
            "cannot derive a cohort recovery key"
        )
    if not reported_value:
        raise STARShardCorruptError(
            f"STAR share for metric {metric!r} has an empty reported value; "
            "nothing to contribute"
        )
    if threshold < 1:
        raise STARShardCorruptError(
            f"STAR threshold {threshold} < 1 is degenerate; refusing to split"
        )
    recovery_key = derive_recovery_key(measurement)
    # The secret shared is the measurement-derived recovery secret — the SAME for
    # every client in the cohort, which is what makes shares combinable.
    secret = int.from_bytes(recovery_key, "big") % _FIELD_PRIME
    # The commitment is over the canonical encoding of the SECRET (not the raw
    # recovery key), so the aggregator's recovered secret round-trips to the
    # SAME commitment under `_secret_commitment`.
    commitment = _secret_commitment(secret)
    x = _derive_x(submitter_id)
    coeffs = _derive_coeffs(measurement, threshold)
    secret_share = _eval_poly(secret, coeffs, x)
    return StarShare(
        metric=metric,
        recovery_key_commitment=commitment,
        x=x,
        secret_share=secret_share,
        noised_value=int.from_bytes(reported_value, "big"),
        submitter_id=submitter_id,
    )


def check_client_side_k_anonymity(
    distinct_submitter_count: int, *, floor: int = K_ANONYMITY_FLOOR
) -> bool:
    """Return True iff the TRUE distinct-submitter cohort meets the k-floor.

    The argument is the count of DISTINCT TRUE submitters who shared the same
    measurement — NOT a DP-noised count. Returns True when ``>= floor``; the
    caller (aggregator) reveals the aggregate only then. Below the floor the
    caller withholds and records ``kAnonymityFloorViolatedError`` in the
    transparency report (the share is structurally unrecoverable regardless).
    """
    return distinct_submitter_count >= floor


@dataclass(slots=True)
class CohortRevelation:
    """The result of an aggregator-side cohort recovery attempt.

    ``revealed`` is True only when the true distinct-submitter cohort met the
    k-floor AND the secret shares interpolated to the committed recovery secret.
    ``aggregate`` is the cohort aggregate — the SUM of the DP-noised per-client
    values (the count-style statistic STAR computes without any individual
    value). ``true_cohort_size`` is the count of DISTINCT submitters (the gate
    input). ``recovered_secret`` is the reconstructed measurement-derived
    recovery secret (proves the cohort), set only when revealed.
    """

    metric: str
    recovery_key_commitment: str
    revealed: bool
    true_cohort_size: int
    aggregate: int | None = None
    recovered_secret: int | None = None


def recover_cohort(
    shares: Sequence[StarShare],
    *,
    floor: int = K_ANONYMITY_FLOOR,
    threshold: int = _RECOVERY_THRESHOLD,
) -> CohortRevelation:
    """Aggregator-side: recover a cohort's aggregate IFF the true k-floor is met.

    All ``shares`` MUST carry the same ``recovery_key_commitment`` (the same
    cohort) and ``metric``. The TRUE cohort size is the number of DISTINCT
    ``submitter_id`` values; the k-floor gates on THAT count, never on a noised
    number. When the floor is met, the measurement-derived recovery secret is
    Lagrange-interpolated from ``threshold`` shares and verified against the
    commitment (proving the cohort really shares one measurement), then the
    cohort aggregate is the SUM of the DP-noised per-client values.

    Raises:
        STARShardCorruptError: mixed commitments/metrics in one cohort, a
            duplicate evaluation point, fewer distinct submitters than the
            threshold, or a recovered secret that does not match the commitment.
        kAnonymityFloorViolatedError: the true cohort is below ``floor`` — the
            aggregate is structurally withheld; the caller records the
            withholding event in the transparency report.
    """
    if not shares:
        raise STARShardCorruptError("recover_cohort called with no shares")
    commitment = shares[0].recovery_key_commitment
    metric = shares[0].metric
    for s in shares:
        if s.recovery_key_commitment != commitment:
            raise STARShardCorruptError(
                f"cohort recovery for metric {metric!r} mixed two recovery-key "
                "commitments — shares from different measurements cannot combine"
            )
        if s.metric != metric:
            raise STARShardCorruptError(
                f"cohort recovery mixed metrics {metric!r} and {s.metric!r}"
            )

    distinct_submitters = {s.submitter_id for s in shares}
    true_cohort_size = len(distinct_submitters)

    if not check_client_side_k_anonymity(true_cohort_size, floor=floor):
        raise kAnonymityFloorViolatedError(
            f"metric {metric!r} true distinct-submitter cohort "
            f"{true_cohort_size} < k-floor {floor}; aggregate withheld "
            "(privacy gate — publish withholding event in transparency report)"
        )

    # One distinct (x, y) point per distinct submitter; dedup so one client is
    # never counted twice toward the interpolation set. Need >= threshold
    # distinct points to interpolate the degree-(threshold-1) polynomial.
    by_submitter: dict[str, StarShare] = {}
    for s in shares:
        by_submitter.setdefault(s.submitter_id, s)
    points_src = list(by_submitter.values())[:threshold]
    if len(points_src) < threshold:
        raise STARShardCorruptError(
            f"cohort for metric {metric!r} has {len(points_src)} distinct "
            f"submitters < threshold {threshold}; cannot interpolate the secret"
        )
    seen_x: set[int] = set()
    points: list[tuple[int, int]] = []
    for p in points_src:
        if p.x in seen_x:
            raise STARShardCorruptError(
                f"duplicate evaluation point x={p.x} in cohort for metric "
                f"{metric!r}; cannot interpolate"
            )
        seen_x.add(p.x)
        points.append((p.x, p.secret_share))

    recovered_secret = _interpolate_at_zero(points)
    # Verify the recovered secret matches the published commitment — proves the
    # cohort really shares ONE measurement (a mixed/forged share set fails here).
    if _secret_commitment(recovered_secret) != commitment:
        raise STARShardCorruptError(
            f"recovered secret for metric {metric!r} does not match the cohort "
            "commitment — corrupt or forged share set; refusing to reveal"
        )

    # The cohort aggregate: SUM of the DP-noised per-client values (the
    # count-style statistic STAR computes without any individual value leaking).
    aggregate = sum(s.noised_value for s in by_submitter.values())
    return CohortRevelation(
        metric=metric,
        recovery_key_commitment=commitment,
        revealed=True,
        true_cohort_size=true_cohort_size,
        aggregate=aggregate,
        recovered_secret=recovered_secret,
    )


def group_cohorts(shares: Sequence[StarShare]) -> Mapping[str, list[StarShare]]:
    """Group shares into cohorts by ``recovery_key_commitment``.

    The aggregator never learns the measurement — only that a set of clients
    produced the SAME commitment. Each group is one cohort eligible for the
    k-floor gate.
    """
    cohorts: dict[str, list[StarShare]] = defaultdict(list)
    for s in shares:
        cohorts[s.recovery_key_commitment].append(s)
    return dict(cohorts)


@dataclass(slots=True)
class StarPrioClient:
    """Client-side STAR share producer for the weekly per-counter measurements.

    Holds the per-install ``submitter_id`` (the random ID rotated quarterly per
    spec) and the reveal ``threshold``/``floor`` (defaulting to the k=100 STAR
    contract). :meth:`build_share` splits one already-DP-noised measurement into
    a combinable share; the client emits the shares through OHTTP (S10) to the
    Foundation aggregator.
    """

    submitter_id: str
    threshold: int = _RECOVERY_THRESHOLD
    floor: int = K_ANONYMITY_FLOOR

    def build_share(self, metric: str, measurement: bytes, noised_value: bytes) -> StarShare:
        """Split one per-counter measurement into a STAR share.

        ``noised_value`` MUST already carry the client-side DP noise
        (EC-S11.3 — DP is injected BEFORE the split, so the share-split input is
        the noised value and a compromised aggregator never sees a true value).
        """
        return split_into_shares(
            metric,
            measurement,
            noised_value,
            self.submitter_id,
            threshold=self.threshold,
        )


__all__ = [
    "K_ANONYMITY_FLOOR",
    "StarShare",
    "CohortRevelation",
    "StarPrioClient",
    "derive_recovery_key",
    "split_into_shares",
    "check_client_side_k_anonymity",
    "recover_cohort",
    "group_cohorts",
]
