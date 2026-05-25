"""Foundation Health Heartbeat client — Phase 01 no-op stub (R2-H-02).

Per shard 17 § 7.3 mandatory Phase 01 stub #1: ``HeartbeatClient`` exposes
the single ``maybe_record_flag(flag_name)`` method that the 21 emit-site
primitives (Boundary Conversation, Daily Digest, Grant Moment, Authorship
Score, Posture ladder, Budget tracker, Channel adapters, Runtime stub,
Enterprise mode) will invoke as a one-line counter increment when those
primitives ship in Wave 2/3/4.

Phase 01 status: GENUINE NO-OP. Method body is a literal ``pass``. No
exception is raised; no Ledger entry is written; no network call is made.

This stub is NOT a fake implementation per ``rules/zero-tolerance.md`` Rule
2 — it is the intended Phase 01 behavior. Production code CALLS this on the
hot path, and the contract IS "do nothing in Phase 01." Phase 02 entry swaps
the body for STAR/Prio share-split + DP noise + OHTTP send via the four
sibling modules (``star_prio``, ``ohttp``, ``signed_consent``, ``registry``)
that currently raise ``PhaseDeferredError``.

The no-op contract is what prevents the emit-site primitives from crashing
when they ship: without this stub, Boundary Conversation completion / Daily
Digest open / Grant Moment approve would all crash on first emit.

Cross-references:
- shard ``01-analysis/17-foundation-health-heartbeat-decision.md`` § 7.3 stub
  partitioning; § 7.6 cross-shard implications (21 emit-site map).
- spec ``specs/foundation-health-heartbeat.md`` § "Payload" (21 flags).
"""

from __future__ import annotations


class HeartbeatClient:
    """Phase 01 no-op consumer for the 21 emit-site primitives.

    The ``maybe_record_flag`` method exists precisely BECAUSE production code
    calls it on the hot path; that distinguishes this stub from the four
    ``PhaseDeferredError`` modules (``star_prio``, ``ohttp``,
    ``signed_consent``, ``registry``) which production code MUST NEVER call.
    """

    def maybe_record_flag(self, flag_name: str) -> None:
        """No-op Phase 01 flag recorder.

        Production code calls this from emit sites (Boundary Conversation,
        Daily Digest, Grant Moment, etc.). In Phase 01 the body is a literal
        ``pass`` — by design. Phase 02 entry will:

        1. Validate ``flag_name`` against
           ``envoy.heartbeat.payload.ALLOWED_FLAGS``.
        2. Increment a per-week counter in the (future) consent-gated store.
        3. On the weekly cadence, emit via the (future) STAR/Prio + OHTTP
           pipeline using the modules currently raising
           ``PhaseDeferredError``.

        Args:
            flag_name: One of the 21 spec flags. NOT validated in Phase 01;
                emit-site primitives may pass any string. Phase 02 entry
                tightens this to ``ALLOWED_FLAGS`` membership.
        """
        pass


__all__ = ["HeartbeatClient"]
