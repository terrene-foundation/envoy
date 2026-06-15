# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-S11.1 — k≥100 enforced on the TRUE cohort, not the noised count.

Tier-2 per `rules/testing.md`: drives the REAL STAR share producer + the REAL
aggregator-side cohort recovery against deterministic clients (no mocks — the
clients are real `StarPrioClient` instances). The load-bearing assertion: DP
noise perturbs the per-counter VALUE clients report, while the k-floor gate
fires on the UN-NOISED distinct-submitter cardinality. A cohort of exactly 100
distinct true submitters reveals; 99 is structurally withheld.
"""

from __future__ import annotations

import pytest

from envoy.heartbeat.client import add_laplace_noise
from envoy.heartbeat.errors import kAnonymityFloorViolatedError
from envoy.heartbeat.star_prio import (
    K_ANONYMITY_FLOOR,
    StarPrioClient,
    check_client_side_k_anonymity,
    recover_cohort,
)


def _build_cohort(metric: str, measurement: bytes, n_clients: int) -> list:
    """n distinct clients each report the same measurement with a DP-noised value.

    Each client noises its true count BEFORE building the share (EC-S11.3 shape);
    the cohort SIZE is the true distinct-submitter count, independent of the
    noise applied to the per-counter values.
    """
    shares = []
    for i in range(n_clients):
        client = StarPrioClient(submitter_id=f"install-{i:04d}", threshold=K_ANONYMITY_FLOOR)
        # The reported VALUE is DP-noised; the cohort gate must ignore this noise.
        noised = add_laplace_noise(1, epsilon=1.0)
        share = client.build_share(metric, measurement, noised.to_bytes(4, "big"))
        shares.append(share)
    return shares


class TestKAnonymityFloorTrueCohort:
    def test_floor_default_is_100(self) -> None:
        assert K_ANONYMITY_FLOOR == 100

    def test_cohort_of_exactly_100_reveals(self) -> None:
        shares = _build_cohort("channel_telegram_active", b"channel_telegram_active", 100)
        revelation = recover_cohort(shares)
        # Revealed because the TRUE distinct-submitter cohort == the floor.
        assert revelation.revealed is True
        assert revelation.true_cohort_size == 100

    def test_cohort_of_99_structurally_withheld(self) -> None:
        shares = _build_cohort("channel_signal_active", b"channel_signal_active", 99)
        with pytest.raises(kAnonymityFloorViolatedError) as exc:
            recover_cohort(shares)
        # The withholding event names the TRUE cohort size — 99, NOT a noised
        # number — proving the gate read the un-noised cardinality.
        assert "99" in str(exc.value)
        assert "k-floor 100" in str(exc.value)

    def test_gate_ignores_dp_noise_on_values(self) -> None:
        """The k-floor gate fires on cohort SIZE, never on the noised VALUE.

        Pins noised-vs-true: even when DP noise drives every reported value far
        from the truth, a 100-distinct-submitter cohort still reveals because the
        gate counts DISTINCT submitters, not values.
        """
        measurement = b"posture_autonomous_active"
        shares = []
        for i in range(100):
            client = StarPrioClient(submitter_id=f"node-{i:04d}")
            # Heavily-noised value (epsilon tiny → large noise). The gate must
            # not care: it counts distinct submitters.
            noised = add_laplace_noise(1, epsilon=0.01)
            shares.append(client.build_share("posture_autonomous_active", measurement, noised.to_bytes(4, "big")))
        revelation = recover_cohort(shares)
        assert revelation.revealed is True
        assert revelation.true_cohort_size == 100

    def test_check_client_side_k_anonymity_predicate(self) -> None:
        assert check_client_side_k_anonymity(100) is True
        assert check_client_side_k_anonymity(101) is True
        assert check_client_side_k_anonymity(99) is False
        assert check_client_side_k_anonymity(0) is False
