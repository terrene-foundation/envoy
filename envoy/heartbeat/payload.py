"""Foundation Health Heartbeat payload schema (frozen, 21 flags).

Per shard 17 § 7.3 mandatory Phase 01 stub #3 ("21-flag payload schema
validation, T-054 defense"). The schema is fixed at the dataclass boundary so
a future emit-pipeline bug — or hostile patch — cannot add a covert flag.

The dataclass + validator ship in Phase 01 because the structural defense
MUST live close to the (future) emit hooks; the defense is correct even when
the emit pipeline is stubbed.

Cross-references:
- spec ``specs/foundation-health-heartbeat.md`` § "Payload" (21-flag list).
- spec § "Flags NEVER reported": ``duress_unlock_detected`` (T-041 defense).
- spec § "Covert-channel defense (T-054)": fixed payload schema.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from envoy.heartbeat.errors import (
    DuressFlagLeakageRefusedError,
    PayloadSchemaDriftError,
)

# 21 boolean flags per ``specs/foundation-health-heartbeat.md`` line 29.
# Order preserved verbatim from the spec to make any drift visible in diff.
ALLOWED_FLAGS: frozenset[str] = frozenset(
    {
        "completed_boundary_conversation",
        "opened_daily_digest_this_week",
        "completed_weekly_posture_review",
        "opened_monthly_trust_report",
        "grant_moment_novelty_approved",
        "grant_moment_novelty_denied",
        "force_install_used_skill",
        "authorship_score_reached_3",
        "authorship_score_reached_5",
        "posture_delegating_active",
        "posture_autonomous_active",
        "budget_monthly_exceeded_50pct",
        "budget_monthly_exceeded_80pct",
        "channel_telegram_active",
        "channel_slack_active",
        "channel_discord_active",
        "channel_whatsapp_active",
        "channel_signal_active",
        "channel_imessage_active",
        "runtime_kailash_rs_active",
        "enterprise_mode_active",
    }
)

# T-041 defense: this flag is NEVER reported. Documented at spec § "Flags
# NEVER reported". Held as a constant so the validator and any future audit
# tooling reference a single source of truth.
DURESS_FLAG_NEVER_REPORTED: str = "duress_unlock_detected"


@dataclass(frozen=True)
class HeartbeatPayload:
    """Frozen Heartbeat payload — exactly 21 boolean flags + identity fields.

    Fields:
        install_id: Per-install random ID. Quarterly rotation per spec §
            "Payload"; rotation cadence is enforced by the (future)
            ``HeartbeatClient``, not by this dataclass.
        envoy_version: ``envoy.__version__`` at emit time.
        flags: Mapping of the 21 spec flags to their boolean values.
            Validator (``_validate_payload_schema``) rejects any key outside
            ``ALLOWED_FLAGS`` AND rejects ``duress_unlock_detected`` even if
            it appears as a key.

    The dataclass is ``frozen=True`` so a stub or test cannot mutate the
    payload after construction; ``flags`` is a ``Mapping`` (read-only view)
    for the same reason.
    """

    install_id: str
    envoy_version: str
    flags: Mapping[str, bool] = field(default_factory=dict)


def _validate_payload_schema(payload: HeartbeatPayload) -> None:
    """Raise on any payload that violates the fixed-schema covert-channel defense.

    Two independent checks, both Phase-01-active:

    1. T-041 (``DuressFlagLeakageRefusedError``): if
       ``duress_unlock_detected`` appears as a flag key — even with value
       ``False`` — refuse. The flag MUST NEVER be reported in any form. Per
       spec § "Flags NEVER reported".
    2. T-054 (``PayloadSchemaDriftError``): any flag key outside
       ``ALLOWED_FLAGS`` is refused. The fixed schema prevents a compromised
       client from adding arbitrary fields. Per spec § "Covert-channel
       defense (T-054)".

    Order matters: the T-041 check runs FIRST so the more-specific error
    surfaces ahead of the generic schema-drift error.

    Raises:
        DuressFlagLeakageRefusedError: ``duress_unlock_detected`` key present.
        PayloadSchemaDriftError: any flag key outside the 21-flag whitelist.
    """
    # T-041 defense — surface the more-specific error first.
    if DURESS_FLAG_NEVER_REPORTED in payload.flags:
        raise DuressFlagLeakageRefusedError(
            f"flag {DURESS_FLAG_NEVER_REPORTED!r} MUST NEVER appear in payload "
            "(T-041 privacy preservation); this is a programming error or "
            "hostile patch — refusing send"
        )

    # T-054 defense — schema drift on any non-whitelist key.
    drift_keys = set(payload.flags.keys()) - ALLOWED_FLAGS
    if drift_keys:
        raise PayloadSchemaDriftError(
            f"flag keys outside fixed 21-flag schema: {sorted(drift_keys)!r}; "
            "T-054 covert-channel defense — refusing send"
        )


__all__ = [
    "ALLOWED_FLAGS",
    "DURESS_FLAG_NEVER_REPORTED",
    "HeartbeatPayload",
    "_validate_payload_schema",
]
