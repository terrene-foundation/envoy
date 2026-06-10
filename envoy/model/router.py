"""envoy.model.router — per-primitive LlmClient factory.

Implements shard 13 § 3.2 + § 4 (`workspaces/phase-01-mvp/01-analysis/
13-model-adapter-implementation.md`).

The :class:`EnvoyModelRouter` is a thin wrapper over kaizen's
:meth:`LlmClient.from_env` (`kaizen.llm.client.LlmClient`, line 164) that
adds two pieces of Envoy-specific behavior:

1. **Per-primitive model override.** Each Envoy LLM primitive (Boundary
   Conversation, Daily Digest, Grant Moment Summary) may want a different
   model than the global :envvar:`KAILASH_LLM_PROVIDER` default — e.g.
   Daily Digest typically picks a cheap/fast model since it runs daily,
   while Boundary Conversation may want a higher-capability model for the
   first-launch onboarding flow. The router reads a per-primitive env-key
   from :attr:`PRIMITIVE_MODEL_ENV_KEYS`; when set, it constructs a copy
   of the deployment with ``default_model`` flipped to the override.

2. **Capability-aware refusal.** Each primitive has a minimum capability
   contract (e.g. Boundary Conversation needs ``tools=True``). The router
   consults :meth:`LlmDeployment.supports` (the per-preset capability
   matrix landed in kailash-py #790 / #763) and raises
   :class:`ProviderSwitchRefusedByEnvelopeError` per spec line 73 if the
   active deployment does not meet the primitive's contract.

Phase 01 chat-completion invocation runs through the legacy provider
surface (``kaizen.providers.llm.<provider>.chat_async``) per shard 13
§ 2.6 (load-bearing finding); the upstream :meth:`LlmClient.complete`
wire-send path is deliberately deferred (kailash-py #740 spec-correction).
The router is the substrate; the chat invocation is the consumer's job
in T-02-40 Boundary Conversation + T-04-XX Daily Digest.
"""

from __future__ import annotations

import logging
import os
from typing import ClassVar

from kaizen.llm.client import LlmClient

from envoy.model.errors import ProviderSwitchRefusedByEnvelopeError

logger = logging.getLogger("envoy.model.router")


class EnvoyModelRouter:
    """Per-primitive :class:`LlmClient` factory with capability-aware
    refusal.

    Per shard 13 § 3.2 (Envoy-new-code surface) + § 4 (class structure
    sketch). The router is constructed once per Envoy session and called
    by each primitive that needs LLM access.

    Args:
        classification_policy: Optional classification-policy object
            forwarded to :meth:`LlmClient.from_env` per the upstream
            kaizen contract (line 164). Phase 01 callers pass ``None`` —
            shard 11 (response classification) wires the real policy in
            Phase 02+.

    Example:
        >>> router = EnvoyModelRouter()
        >>> client = router.for_primitive("boundary_conversation")
        >>> # client.deployment.default_model reflects either
        >>> # ENVOY_BOUNDARY_MODEL (override) OR the global default.
    """

    #: Map from primitive-name to the env-key carrying that primitive's
    #: model override per shard 13 § 3.2. The four canonical primitives
    #: are Boundary Conversation, Daily Digest, Grant Moment Summary, and
    #: the catch-all default.
    PRIMITIVE_MODEL_ENV_KEYS: ClassVar[dict[str, str]] = {
        "boundary_conversation": "ENVOY_BOUNDARY_MODEL",
        "daily_digest": "ENVOY_DIGEST_MODEL",
        "grant_moment_summary": "ENVOY_GRANT_MOMENT_MODEL",
        "default": "ENVOY_DEFAULT_MODEL",
    }

    #: Per-primitive capability requirements. Keys are primitive names;
    #: values are the subset of :meth:`LlmDeployment.supports` keys that
    #: MUST be True for the picked deployment.
    #:
    #: * ``boundary_conversation`` — needs ``tools=True`` because the
    #:   onboarding flow may invoke envelope-builder tool calls per
    #:   shard 8 § 5.1.
    #: * ``daily_digest`` — no tools required; the digest is a pure
    #:   render-from-Ledger render per shard 11 § 5.2.
    #: * ``grant_moment_summary`` — no tools required; pure text
    #:   summarization per shard 10 § 5.3.
    #: * ``default`` — no requirements (general-purpose fallback).
    _PRIMITIVE_REQUIRED_CAPS: ClassVar[dict[str, dict[str, bool]]] = {
        "boundary_conversation": {"tools": True},
        "daily_digest": {},
        "grant_moment_summary": {},
        "default": {},
    }

    def __init__(self, *, classification_policy: object | None = None) -> None:
        self._classification_policy = classification_policy

    def required_capabilities(self, primitive: str) -> dict[str, bool]:
        """Return the capability-requirement vector for ``primitive``.

        Returns the matching entry from :attr:`_PRIMITIVE_REQUIRED_CAPS`,
        or an empty dict for unknown primitives (no requirements →
        always passes the capability gate).

        Tier 1 tests use this method to introspect the contract per
        ``rules/zero-tolerance.md`` Rule 3c (every documented kwarg /
        contract MUST be observable).
        """
        return dict(self._PRIMITIVE_REQUIRED_CAPS.get(primitive, {}))

    def for_primitive(self, primitive: str) -> LlmClient:
        """Return an :class:`LlmClient` configured for ``primitive``.

        Resolution order per shard 13 § 3.2:

        1. Build the base client via :meth:`LlmClient.from_env` (three-
           tier precedence per kaizen #498 / S7: URI tier →
           selector tier → legacy-API-key autoselect).
        2. If the primitive's env-key (e.g. ``ENVOY_BOUNDARY_MODEL``)
           is set, flip ``deployment.default_model`` to the override
           via :meth:`LlmDeployment.model_copy` + :meth:`LlmClient.
           with_deployment`.
        3. Check the resulting deployment's :meth:`supports` matrix
           against the primitive's :attr:`_PRIMITIVE_REQUIRED_CAPS`
           contract. Raise :class:`ProviderSwitchRefusedByEnvelopeError`
           per spec line 73 on mismatch.

        Args:
            primitive: One of the keys in :attr:`PRIMITIVE_MODEL_ENV_KEYS`
                (``"boundary_conversation"``, ``"daily_digest"``,
                ``"grant_moment_summary"``, ``"default"``). Unknown
                primitives fall through to ``"default"`` (no override,
                no capability requirements).

        Raises:
            ProviderSwitchRefusedByEnvelopeError: The active deployment's
                capability matrix does not satisfy ``primitive``'s
                required capabilities.
        """
        logger.info(
            "model.router.for_primitive.start",
            extra={"primitive": primitive},
        )
        client = LlmClient.from_env(classification_policy=self._classification_policy)
        deployment = client.deployment
        if deployment is None:
            # LlmClient.from_env should always produce a deployment per
            # the three-tier precedence contract; defensive guard per
            # `rules/zero-tolerance.md` Rule 3a (typed delegate guard
            # against None backing object — surface a typed error rather
            # than allow AttributeError on the next attribute access).
            raise RuntimeError(
                "LlmClient.from_env() returned a client with no deployment — "
                "set KAILASH_LLM_DEPLOYMENT, KAILASH_LLM_PROVIDER, or a "
                "supported legacy API key (OPENAI_API_KEY / ANTHROPIC_API_KEY "
                "/ GOOGLE_API_KEY) per kaizen.llm.from_env three-tier "
                "precedence (shard 13 § 2.5)."
            )

        override_env_key = self.PRIMITIVE_MODEL_ENV_KEYS.get(
            primitive, self.PRIMITIVE_MODEL_ENV_KEYS["default"]
        )
        override_model = os.environ.get(override_env_key)
        if override_model:
            # Flip the deployment's default_model to the override. The
            # deployment is `frozen=True, extra="forbid"` per pydantic v2
            # — model_copy(update={...}) is the canonical mutator.
            deployment = deployment.model_copy(update={"default_model": override_model})
            client = client.with_deployment(deployment)
            # INFO→DEBUG per `rules/observability.md` Rule 8: `default_model`
            # is a schema-revealing identifier that bleeds to log aggregators.
            # /redteam Round 1 MEDIUM-1 (commit a52a14d audit).
            logger.debug(
                "model.router.for_primitive.override_applied",
                extra={
                    "primitive": primitive,
                    "override_env_key": override_env_key,
                    "default_model": override_model,
                },
            )

        # Capability gate per shard 13 § 3.2 + spec line 73.
        required = self.required_capabilities(primitive)
        if required:
            supports = deployment.supports()
            for cap, required_value in required.items():
                if supports.get(cap) is not required_value:
                    raise ProviderSwitchRefusedByEnvelopeError(
                        f"primitive={primitive!r} requires capability "
                        f"{cap}={required_value} but the active deployment "
                        f"(preset={deployment.preset_name!r}, "
                        f"default_model={deployment.default_model!r}) reports "
                        f"{cap}={supports.get(cap)!r}. Pick a preset whose "
                        f"supports() matrix satisfies the contract, or relax "
                        f"the primitive's capability requirement in the "
                        f"envelope's operational dimension."
                    )

        # INFO→DEBUG per `rules/observability.md` Rule 8: `preset_name` +
        # `default_model` are schema-revealing identifiers that bleed to log
        # aggregators. /redteam Round 1 MEDIUM-1.
        logger.debug(
            "model.router.for_primitive.ok",
            extra={
                "primitive": primitive,
                "preset_name": deployment.preset_name,
                "default_model": deployment.default_model,
            },
        )
        return client


__all__ = ["EnvoyModelRouter"]
