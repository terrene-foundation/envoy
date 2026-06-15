# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EC-S11.3 — DP noise is added to the counter BEFORE split_into_shares.

Tier-2 per `rules/testing.md`: verified structurally — the share-split input is
the NOISED value, so a fully-compromised aggregator (one that recovers the
cohort value) never observes a true per-client value. No mocks: the noise
function is an injected DETERMINISTIC adapter and the share producer is a real
`StarPrioClient` subclass that records its inputs (Protocol-adapter carve-out,
`rules/testing.md` § Protocol Adapters).
"""

from __future__ import annotations

from envoy.heartbeat.client import HeartbeatClient, OptOutConsentGate, add_laplace_noise
from envoy.heartbeat.star_prio import (
    K_ANONYMITY_FLOOR,
    StarPrioClient,
    StarShare,
    recover_cohort,
)


class _RecordingStarClient(StarPrioClient):
    """Real StarPrioClient that records the value bytes it was asked to split.

    Not a mock — it performs the REAL share-split via ``super().build_share`` and
    additionally records the ``noised_value`` argument so the test can assert the
    share-split input was the noised value, not the true count.
    """

    recorded_values: list[bytes]

    def __init__(self, submitter_id: str) -> None:
        super().__init__(submitter_id=submitter_id)
        object.__setattr__(self, "recorded_values", [])

    def build_share(self, metric: str, measurement: bytes, noised_value: bytes) -> StarShare:
        self.recorded_values.append(noised_value)
        return super().build_share(metric, measurement, noised_value)


class TestDPBeforeSplit:
    def test_laplace_noise_is_nonnegative_int(self) -> None:
        for _ in range(50):
            noised = add_laplace_noise(5, epsilon=1.0)
            assert isinstance(noised, int)
            assert noised >= 0

    def test_emit_noises_before_building_share(self) -> None:
        """The value fed to build_share is the noised value, not the truth.

        A deterministic noise adapter maps any count to a fixed sentinel; the
        recording share client confirms the share-split input equals the
        sentinel, never the true counter.
        """
        SENTINEL_NOISED = 999
        recorder = _RecordingStarClient(submitter_id="install-dp-order")
        client = HeartbeatClient(
            consent_gate=OptOutConsentGate(granted=True),
            star_client=recorder,
            # Deterministic noise adapter (NOT a mock): always returns SENTINEL.
            noise_fn=lambda value, epsilon: SENTINEL_NOISED,
        )
        # Accrue a true count of 7.
        for _ in range(7):
            client.maybe_record_flag("authorship_score_reached_5")

        client.emit_weekly()

        # The share-split input was the NOISED sentinel, NOT the true count 7.
        assert recorder.recorded_values == [SENTINEL_NOISED.to_bytes(4, "big")]
        assert recorder.recorded_values[0] != (7).to_bytes(4, "big")

    def test_compromised_aggregator_recovers_only_noised_aggregate(self) -> None:
        """A k-met cohort recovers only the NOISED aggregate — no true value leaks.

        100 clients each report a value already DP-noised to a fixed sentinel.
        The aggregator recovers the cohort and computes the aggregate as the SUM
        of the noised contributions — it never observes any individual TRUE
        value; the share carries only the noised contribution.
        """
        measurement = b"runtime_kailash_rs_active"
        SENTINEL = (42).to_bytes(4, "big")
        shares = []
        for i in range(K_ANONYMITY_FLOOR):
            client = StarPrioClient(submitter_id=f"agg-{i:04d}")
            # The client already noised its value to SENTINEL before splitting.
            shares.append(client.build_share("runtime_kailash_rs_active", measurement, SENTINEL))
        revelation = recover_cohort(shares)
        assert revelation.revealed is True
        # The aggregate is the SUM of the noised contributions (100 × 42); no
        # individual true value is ever reconstructable.
        assert revelation.aggregate == 100 * 42
