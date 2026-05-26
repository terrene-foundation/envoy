"""envoy.grant_moment.channel_handoff — ChannelHandoff dispatch surface.

Implements the channel-adapter dispatch contract per
`workspaces/phase-01-mvp/01-analysis/10-grant-moment-implementation.md`
§ 3 step 5 ("function-call contract to channel adapters; primary-channel
binding check") and `specs/grant-moment.md` § Rendering + § Novelty-aware
friction.

Spec invariants this module enforces:

- "Every dialog shows: visible secret, proposed action, why asking,
  consequence preview, options" — the dispatch surface relays a fully-
  populated ``GrantMomentRequest`` to each adapter; the adapter is
  responsible for rendering all five elements (the spec mandates which
  fields; the adapter chooses how to display them).

- Primary-channel binding: high-stakes Grant Moments AND requests with
  ``primary_only=True`` MUST render ONLY on the user's designated primary
  channel. Sibling adapters are recorded as refused with a structured
  reason the runtime can surface to the user.

- Sequential dispatch: ``await`` each adapter's ``render_grant_moment``
  in order (primary first, then siblings in adapter-list order). This
  matches the spec's primary-binding intent. Concurrent dispatch is a
  future optimization once render-time contention becomes load-bearing
  enough to justify the per-channel-race observability cost.

- Layer split — ``NotPrimaryChannelError`` does NOT fire here. The
  ``NotPrimaryChannelError`` in ``envoy.grant_moment.errors`` is raised
  at M3 sign-or-decline when a high-stakes ``GrantMomentResult`` arrives
  from a non-primary ``decided_on_channel_id`` (see ``errors.py`` §
  "Layer attribution"). The M1 dispatch surface implemented here uses
  structural ``HandoffPlan.refused_channels`` records instead — at M1
  no decision exists yet to check the decided-on channel against.

- Adapter failure isolation: when an adapter raises during render, the
  dispatch loop catches the exception, records the failure as a refused
  channel with reason ``"render_failed: <ExceptionType>"``, and continues
  dispatching to remaining adapters. The spec does NOT mandate a short-
  circuit on primary failure; refusal records preserve the caller's
  observability so the runtime can surface "primary channel down — try
  alternate".

- Idempotency: re-dispatching the same ``request_id`` is NOT enforced
  at this shard. The runtime tracks request_id idempotency separately
  via the nonce defense (see ``GrantMomentReplayError`` in
  ``envoy.grant_moment.errors`` and the T-03-50 spec § T-008 nonce
  defense). ``ChannelHandoff`` is the dispatch surface, not the dedup
  authority.

Per `rules/agent-reasoning.md`: structural plumbing only — list iteration
+ exception catching + ValueError on misconfiguration. ZERO LLM calls,
ZERO content-based routing.

This module is pure Python; depends only on
``envoy.grant_moment.signed_consent.GrantMomentRequest``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from envoy.grant_moment.signed_consent import GrantMomentRequest

__all__ = [
    "ChannelAdapterProtocol",
    "ChannelHandoff",
    "HandoffPlan",
]


# Refusal reasons — closed vocabulary so callers and Ledger entries can
# pattern-match without parsing prose. The render_failed reason carries
# the exception type as a suffix so the runtime can group failures by
# class without exposing the str(e) message (per `rules/security.md`
# § "No secrets in logs" — exception messages may carry adapter-internal
# state we don't want bleeding into refusal records).
_REFUSAL_NOT_PRIMARY_FOR_HIGH_STAKES = "not_primary_for_high_stakes"
_REFUSAL_NOT_PRIMARY_FOR_PRIMARY_ONLY = "not_primary_for_primary_only"
_REFUSAL_RENDER_FAILED_PREFIX = "render_failed: "


@runtime_checkable
class ChannelAdapterProtocol(Protocol):
    """The minimal channel-adapter surface ``ChannelHandoff`` dispatches against.

    Mirrors the shape of ``envoy.grant_moment.signed_consent._KeyManagerProtocol``
    — Phase 01 uses Protocol so the dispatch surface compiles against any
    channel implementation (CLI, web, Telegram, Slack, Tauri desktop)
    that satisfies the two declared members; Phase 02 may tighten the
    Protocol with capability-advertisement methods.

    Implementations MUST:
    - expose ``channel_id`` as a stable string (e.g. ``"cli"``, ``"web"``)
      so ``HandoffPlan`` rows are auditable without keeping adapter
      object references; and
    - implement ``render_grant_moment`` as an async coroutine that
      raises on any render failure (the dispatch loop catches and records).
    """

    channel_id: str

    async def render_grant_moment(self, request: GrantMomentRequest) -> None: ...


@dataclass(frozen=True, slots=True)
class HandoffPlan:
    """Outcome of a ``ChannelHandoff.dispatch`` call.

    ``channels_dispatched`` records adapters whose ``render_grant_moment``
    coroutine returned without raising — in dispatch order (primary first,
    then siblings).

    ``refused_channels`` records each adapter that was structurally
    skipped (high-stakes / primary_only → siblings) OR raised during
    render. Each entry is ``(channel_id, reason)`` where ``reason`` is
    one of the closed-vocabulary strings: ``"not_primary_for_high_stakes"``,
    ``"not_primary_for_primary_only"``, or ``"render_failed: <ExceptionType>"``.
    """

    request_id: str
    channels_dispatched: tuple[str, ...]
    refused_channels: tuple[tuple[str, str], ...]


class ChannelHandoff:
    """Sequential dispatcher with primary-channel-binding enforcement.

    Constructor validates that:
    1. ``adapters`` is non-empty (an empty adapter set cannot deliver a
       Grant Moment to anyone; that is a runtime misconfiguration).
    2. ``primary_channel_id`` is present in ``adapters`` (the primary
       channel must actually exist among the configured channels).

    ``dispatch`` walks the adapter list in primary-first order, awaiting
    each adapter's ``render_grant_moment``. Adapters that are refused by
    the primary-binding rule OR that raise during render are recorded in
    the returned ``HandoffPlan.refused_channels``; adapters that complete
    cleanly are recorded in ``channels_dispatched``.

    Per `rules/communication.md`: all ValueError messages name the
    misconfiguration in plain language so the caller can fix the setup
    without reading the dispatch code.
    """

    def __init__(
        self,
        *,
        adapters: tuple[ChannelAdapterProtocol, ...],
        primary_channel_id: str,
    ) -> None:
        if len(adapters) == 0:
            raise ValueError(
                "at least one channel adapter required: ChannelHandoff "
                "cannot deliver a Grant Moment to zero channels. Configure "
                "the runtime with at least the user's primary channel."
            )

        adapter_ids = [a.channel_id for a in adapters]
        if primary_channel_id not in adapter_ids:
            raise ValueError(
                f"primary_channel_id {primary_channel_id!r} not in adapters: "
                f"configured channel_ids are {adapter_ids!r}. The primary "
                "channel must be one of the configured channels."
            )

        self._adapters = adapters
        self._primary_channel_id = primary_channel_id
        # Pre-compute the primary-first dispatch order so dispatch() is
        # O(N) over the adapter list and the order is the same on every
        # call (deterministic for replay + audit).
        self._dispatch_order = self._build_primary_first_order(adapters, primary_channel_id)

    @property
    def primary_channel_id(self) -> str:
        """The primary channel id this handoff binds high-stakes grants to."""
        return self._primary_channel_id

    @property
    def adapter_channel_ids(self) -> tuple[str, ...]:
        """All configured adapter channel ids, in registration order.

        Exposed so the runtime can validate caller-supplied channel ids
        (e.g. ``confirm_channel_id`` on the high-stakes cross-channel
        confirm leg) against the configured channel set.
        """
        return tuple(a.channel_id for a in self._adapters)

    @staticmethod
    def _build_primary_first_order(
        adapters: tuple[ChannelAdapterProtocol, ...],
        primary_channel_id: str,
    ) -> tuple[ChannelAdapterProtocol, ...]:
        """Return adapters with the primary at index 0; siblings preserve order."""
        primary = next(a for a in adapters if a.channel_id == primary_channel_id)
        siblings = tuple(a for a in adapters if a.channel_id != primary_channel_id)
        return (primary, *siblings)

    async def dispatch(
        self,
        *,
        request: GrantMomentRequest,
        high_stakes: bool,
    ) -> HandoffPlan:
        """Dispatch the request to adapters; return the per-channel plan.

        Primary-binding rules:
        - ``high_stakes=True`` OR ``request.primary_only=True`` →
          ONLY the primary adapter is dispatched; siblings are refused
          with the corresponding reason.
        - otherwise → all adapters are dispatched in primary-first order.

        Adapter failure rules:
        - any adapter raising during ``render_grant_moment`` is recorded
          in ``refused_channels`` with reason ``f"render_failed: {type(e).__name__}"``
          and dispatch continues to remaining adapters. Primary failure
          does NOT short-circuit siblings — the spec gives no short-circuit
          rule, and the caller's observability is better served by
          attempting every channel.
        """
        primary_only_route = high_stakes or request.primary_only
        refusal_reason_for_siblings = (
            _REFUSAL_NOT_PRIMARY_FOR_HIGH_STAKES
            if high_stakes
            else _REFUSAL_NOT_PRIMARY_FOR_PRIMARY_ONLY
        )

        dispatched: list[str] = []
        refused: list[tuple[str, str]] = []

        for adapter in self._dispatch_order:
            is_primary = adapter.channel_id == self._primary_channel_id

            # Structural refusal: primary-binding for high-stakes / primary_only.
            if primary_only_route and not is_primary:
                refused.append((adapter.channel_id, refusal_reason_for_siblings))
                continue

            try:
                await adapter.render_grant_moment(request)
            except Exception as exc:
                # Per docstring + spec § Rendering: capture-and-continue so
                # the caller's HandoffPlan records every channel's outcome.
                # We log the exception TYPE name (not str(exc)) per
                # `rules/security.md` § "No secrets in logs" — adapter
                # exception messages may carry transport-internal state.
                refused.append(
                    (adapter.channel_id, _REFUSAL_RENDER_FAILED_PREFIX + type(exc).__name__)
                )
            else:
                dispatched.append(adapter.channel_id)

        return HandoffPlan(
            request_id=request.request_id,
            channels_dispatched=tuple(dispatched),
            refused_channels=tuple(refused),
        )
