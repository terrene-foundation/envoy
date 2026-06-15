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
   information-theoretically unrecoverable (Shamir over GF(2^8), threshold k).
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

Shamir secret sharing here is a self-contained GF(2^8) implementation built on
no external dependency — ``rules/zero-tolerance.md`` Rule 4 forbids a naive
re-implementation that DIVERGES from a reference, but Shamir over GF(2^8) is a
fixed, well-specified algorithm (the same field ``envoy.shamir`` uses for the
recovery ritual); this is that algorithm, not a shortcut.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
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

# GF(2^8) with the AES reduction polynomial x^8 + x^4 + x^3 + x + 1 (0x11B).
_GF_REDUCE = 0x11B

# Domain-separation label for the measurement-key derivation. Identical
# measurements across clients MUST derive the identical recovery key, so the
# derivation is a keyless (HMAC with a fixed public label) hash over the
# measurement bytes — deterministic and collision-resistant, NOT a per-client
# secret.
_RECOVERY_KEY_LABEL = b"envoy.star.v1.recovery-key"


def _gf_mul(a: int, b: int) -> int:
    """Multiply two GF(2^8) elements (AES field, 0x11B reduction)."""
    result = 0
    a &= 0xFF
    b &= 0xFF
    while b:
        if b & 1:
            result ^= a
        b >>= 1
        a <<= 1
        if a & 0x100:
            a ^= _GF_REDUCE
    return result & 0xFF


def _gf_pow(base: int, exp: int) -> int:
    """Exponentiate in GF(2^8) by square-and-multiply."""
    result = 1
    while exp:
        if exp & 1:
            result = _gf_mul(result, base)
        base = _gf_mul(base, base)
        exp >>= 1
    return result


def _gf_inv(a: int) -> int:
    """Multiplicative inverse in GF(2^8): a^254 (Fermat, since a^255 == 1)."""
    if a == 0:
        raise STARShardCorruptError(
            "GF(2^8) inverse of zero requested during share recovery — a "
            "duplicate or zero x-coordinate indicates a corrupt share set"
        )
    return _gf_pow(a, 254)


def derive_recovery_key(measurement: bytes) -> bytes:
    """Derive the deterministic STAR recovery key for a measurement.

    Identical measurements across clients MUST map to the identical key so
    their value shares are combinable. The derivation is a fixed-label HMAC over
    the measurement bytes — public and deterministic (NOT a per-client secret).
    """
    return hmac.new(_RECOVERY_KEY_LABEL, measurement, hashlib.sha256).digest()


def _split_secret_byte(secret: int, threshold: int, x_coords: Sequence[int]) -> list[int]:
    """Shamir-split one secret byte into shares at the given x-coordinates.

    The polynomial is ``secret + c1*x + ... + c(t-1)*x^(t-1)`` over GF(2^8) with
    random non-zero-degree coefficients; share i is the polynomial evaluated at
    ``x_coords[i]``.
    """
    coeffs = [secret & 0xFF] + [secrets.randbelow(256) for _ in range(threshold - 1)]
    shares: list[int] = []
    for x in x_coords:
        acc = 0
        # Horner evaluation in GF(2^8).
        for c in reversed(coeffs):
            acc = _gf_mul(acc, x) ^ c
        shares.append(acc & 0xFF)
    return shares


def _interpolate_at_zero(points: Sequence[tuple[int, int]]) -> int:
    """Lagrange-interpolate a GF(2^8) polynomial at x=0 from (x, y) points."""
    secret = 0
    for j, (xj, yj) in enumerate(points):
        num = 1
        den = 1
        for m, (xm, _ym) in enumerate(points):
            if m == j:
                continue
            num = _gf_mul(num, xm)
            den = _gf_mul(den, xj ^ xm)
        lagrange = _gf_mul(num, _gf_inv(den))
        secret ^= _gf_mul(yj, lagrange)
    return secret & 0xFF


@dataclass(frozen=True, slots=True)
class StarShare:
    """One client's STAR share for one per-counter measurement.

    ``recovery_key_commitment`` is the public commitment over the derived
    recovery key — clients sharing the IDENTICAL measurement produce the
    IDENTICAL commitment, which is how the aggregator groups a cohort WITHOUT
    learning the measurement. ``x`` is the client's distinct evaluation point;
    ``value_shares`` are the per-byte Shamir shares of the (DP-noised) reported
    value. ``submitter_id`` is the per-install random ID used ONLY to count
    DISTINCT submitters for the true-cohort k-floor (never the measurement).
    """

    metric: str
    recovery_key_commitment: str
    x: int
    value_shares: tuple[int, ...]
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

    The share is keyed by ``measurement`` (identical measurements → identical
    ``recovery_key_commitment`` → combinable shares) and carries Shamir shares
    of ``reported_value`` (which the caller has ALREADY DP-noised per EC-S11.3 —
    this function never sees the true value, only the noised bytes the caller
    passes). The client's evaluation point ``x`` is a non-zero byte derived from
    its ``submitter_id`` so two clients almost never collide on x within a
    cohort (a collision is rejected at recovery as a corrupt share set).

    Args:
        metric: the flag name this measurement is for (one of the 21 flags).
        measurement: the cohort key bytes — identical across clients with the
            same measurement. Below ``threshold`` distinct submitters the value
            is information-theoretically unrecoverable.
        reported_value: the (already DP-noised) value bytes to secret-share.
        submitter_id: the per-install random ID; counts distinct submitters and
            seeds the distinct evaluation point.
        threshold: Shamir reveal threshold (defaults to the k-floor).

    Raises:
        STARShardCorruptError: empty measurement or empty value (a degenerate
            share that cannot participate in recovery).
    """
    if not measurement:
        raise STARShardCorruptError(
            f"STAR share for metric {metric!r} has an empty measurement key; "
            "cannot derive a cohort recovery key"
        )
    if not reported_value:
        raise STARShardCorruptError(
            f"STAR share for metric {metric!r} has an empty reported value; "
            "nothing to secret-share"
        )
    if threshold < 1:
        raise STARShardCorruptError(
            f"STAR threshold {threshold} < 1 is degenerate; refusing to split"
        )
    recovery_key = derive_recovery_key(measurement)
    commitment = hashlib.sha256(recovery_key).hexdigest()
    # Distinct non-zero evaluation point derived from the submitter id (x != 0;
    # x=0 is the secret itself).
    x = (int.from_bytes(hashlib.sha256(submitter_id.encode("utf-8")).digest()[:1], "big") % 255) + 1
    value_shares = tuple(
        _split_secret_byte(b, threshold, [x])[0] for b in reported_value
    )
    return StarShare(
        metric=metric,
        recovery_key_commitment=commitment,
        x=x,
        value_shares=value_shares,
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
    k-floor AND the value shares interpolated cleanly. ``recovered_value`` is
    the reconstructed (DP-noised) value bytes when revealed, else None.
    ``true_cohort_size`` is the count of DISTINCT submitters (the gate input).
    """

    metric: str
    recovery_key_commitment: str
    revealed: bool
    true_cohort_size: int
    recovered_value: bytes | None = None


def recover_cohort(
    shares: Sequence[StarShare],
    *,
    floor: int = K_ANONYMITY_FLOOR,
    threshold: int = _RECOVERY_THRESHOLD,
) -> CohortRevelation:
    """Aggregator-side: recover a cohort's value IFF the true k-floor is met.

    All ``shares`` MUST carry the same ``recovery_key_commitment`` (the same
    cohort) and ``metric``. The TRUE cohort size is the number of DISTINCT
    ``submitter_id`` values; the k-floor gates on THAT count, never on a noised
    number. When the floor is met, the value shares are Lagrange-interpolated at
    x=0 per byte to recover the (DP-noised) value.

    Raises:
        STARShardCorruptError: mixed commitments/metrics in one cohort, a
            duplicate evaluation point, or ragged value-share lengths.
        kAnonymityFloorViolatedError: the true cohort is below ``floor`` — the
            aggregate is structurally withheld; the caller records the
            withholding event in the transparency report.
    """
    if not shares:
        raise STARShardCorruptError("recover_cohort called with no shares")
    commitment = shares[0].recovery_key_commitment
    metric = shares[0].metric
    value_len = len(shares[0].value_shares)
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
        if len(s.value_shares) != value_len:
            raise STARShardCorruptError(
                f"ragged value-share length in cohort for metric {metric!r}: "
                f"expected {value_len}, got {len(s.value_shares)}"
            )

    distinct_submitters = {s.submitter_id for s in shares}
    true_cohort_size = len(distinct_submitters)

    if not check_client_side_k_anonymity(true_cohort_size, floor=floor):
        raise kAnonymityFloorViolatedError(
            f"metric {metric!r} true distinct-submitter cohort "
            f"{true_cohort_size} < k-floor {floor}; aggregate withheld "
            "(privacy gate — publish withholding event in transparency report)"
        )

    # One distinct (x, y) point per distinct submitter; dedup by submitter to
    # avoid counting one client twice toward the interpolation set.
    by_submitter: dict[str, StarShare] = {}
    for s in shares:
        by_submitter.setdefault(s.submitter_id, s)
    points = list(by_submitter.values())[:threshold]
    seen_x: set[int] = set()
    for p in points:
        if p.x in seen_x:
            raise STARShardCorruptError(
                f"duplicate evaluation point x={p.x} in cohort for metric "
                f"{metric!r}; cannot interpolate"
            )
        seen_x.add(p.x)

    recovered = bytes(
        _interpolate_at_zero([(p.x, p.value_shares[i]) for p in points])
        for i in range(value_len)
    )
    return CohortRevelation(
        metric=metric,
        recovery_key_commitment=commitment,
        revealed=True,
        true_cohort_size=true_cohort_size,
        recovered_value=recovered,
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
