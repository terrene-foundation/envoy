"""envoy.model.risk — ProviderRisk annotation + fail-closed envelope check.

Implements `specs/model-adapter.md` § Provider-risk annotation (lines 14-36)
and shard 13 § 3.3 (`workspaces/phase-01-mvp/01-analysis/13-model-adapter-
implementation.md`).

The :class:`ProviderRisk` dataclass mirrors the 9-field schema (provider_id,
model_family, model_version, risk_class, training_data_leak_class,
jurisdiction, data_retention_policy_url, annotated_at,
foundation_attestation_signature_hex). :class:`EnvoyProviderRiskAnnotator`
maps an :class:`LlmDeployment` to its :class:`ProviderRisk` using the
preset→annotation table per shard 13 § 3.3:

* ``ollama`` / ``llama_cpp`` / ``lm_studio`` / ``docker_model_runner`` →
  ``Self-hosted``
* ``openai_compatible`` / ``anthropic_compatible`` → ``Community``
* ``anthropic`` / ``openai`` / ``deepseek`` / etc. → ``Provider-bound``
  until Foundation publishes FV attestations (Phase 02+)

The annotator persists each invocation's annotation into the Envoy Ledger
via :meth:`emit_ledger_entry`, satisfying spec line 16 ("the runtime
persists this in the assembled-prompt's response Ledger entry").

The fail-closed semantics live in :meth:`fail_closed_check`: Provider-bound
risk requires an explicit ``provider_bound: true`` opt-in on the envelope's
operational dimension; absence raises
:class:`ProviderRiskAnnotationMissingError` per spec line 36 + line 67.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, ClassVar, Literal, Optional

from kaizen.llm.deployment import LlmDeployment

from envoy.envelope.types import EnvelopeConfig
from envoy.ledger.facade import EnvoyLedger
from envoy.model.errors import ProviderRiskAnnotationMissingError

logger = logging.getLogger("envoy.model.risk")

#: Risk-class literal union per spec line 22 + lines 31-36.
RiskClass = Literal["FV", "Community", "Self-hosted", "Provider-bound"]

#: Training-data-leak-class literal union per spec line 23.
TrainingDataLeakClass = Literal["high", "medium", "low", "unknown"]


@dataclass(frozen=True, slots=True)
class ProviderRisk:
    """The 9-field ProviderRisk annotation per spec lines 17-29.

    Frozen + slots per `rules/orphan-detection.md` Rule 1 — every field is
    part of the on-wire Ledger contract; mutation would invalidate the
    canonical-bytes hash chain.

    Field semantics (spec lines 17-29):

    * ``provider_id`` — canonical provider identifier (``"openai"``,
      ``"anthropic"``, ``"local-ollama"``, …). Drives downstream telemetry
      grouping; MUST be lowercase ASCII.
    * ``model_family`` — provider's model family identifier
      (``"gpt-4-turbo"``, ``"claude-3-5-sonnet"``, ``"llama3.2"``, …).
    * ``model_version`` — provider's version string (``"2024-04-09"``,
      ``"20241022"``, ``"latest"``, …).
    * ``risk_class`` — one of the four spec values per line 22.
    * ``training_data_leak_class`` — provider's stated leak posture
      (``"high"`` / ``"medium"`` / ``"low"`` / ``"unknown"``).
    * ``jurisdiction`` — ISO 3166-1 alpha-2 country code OR ``"mixed"``
      for multi-region operators.
    * ``data_retention_policy_url`` — public URL of the provider's
      retention policy (or self-hosted equivalent).
    * ``annotated_at`` — ISO-8601 UTC timestamp; emitted at annotation
      time by :meth:`EnvoyProviderRiskAnnotator.annotate`.
    * ``foundation_attestation_signature_hex`` — Ed25519 hex signature
      from Foundation registry (Phase 02+); ``None`` for self-hosted and
      Phase 01 Provider-bound presets.
    """

    provider_id: str
    model_family: str
    model_version: str
    risk_class: RiskClass
    training_data_leak_class: TrainingDataLeakClass
    jurisdiction: str
    data_retention_policy_url: str
    annotated_at: str
    foundation_attestation_signature_hex: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the spec § Provider-risk annotation wire form.

        Used by :meth:`EnvoyProviderRiskAnnotator.emit_ledger_entry` to
        package the annotation into the ``model_invoke`` Ledger entry's
        ``content`` field.
        """
        return {
            "provider_id": self.provider_id,
            "model_family": self.model_family,
            "model_version": self.model_version,
            "risk_class": self.risk_class,
            "training_data_leak_class": self.training_data_leak_class,
            "jurisdiction": self.jurisdiction,
            "data_retention_policy_url": self.data_retention_policy_url,
            "annotated_at": self.annotated_at,
            "foundation_attestation_signature_hex": (self.foundation_attestation_signature_hex),
        }


# Sentinel for unknown / preset-not-yet-FV-attested data retention URLs.
# Self-hosted presets have no provider-side policy URL; Provider-bound
# presets without FV attestation in Phase 01 use the provider's public
# policy page. Phase 02+ Foundation registry will replace these with
# attested URLs.
_UNKNOWN_RETENTION_URL = "https://envoy.example.invalid/no-attestation"

# Provider-bound public-page retention URLs per shard 13 § 3.3. These are
# placeholders pending Foundation registry attestation; Phase 02 replaces
# them with Foundation-signed URLs from `specs/foundation-ops.md`.
_PROVIDER_RETENTION_URLS: dict[str, str] = {
    "openai": "https://openai.com/policies/row-privacy-policy",
    "anthropic": "https://www.anthropic.com/legal/privacy",
    "deepseek": "https://www.deepseek.com/privacy",
    "google": "https://policies.google.com/privacy",
    "cohere": "https://cohere.com/privacy",
    "mistral": "https://mistral.ai/terms#privacy-policy",
    "perplexity": "https://www.perplexity.ai/hub/legal/privacy-policy",
    "groq": "https://groq.com/privacy-policy/",
    "together": "https://www.together.ai/privacy",
    "fireworks": "https://fireworks.ai/privacy-policy",
    "openrouter": "https://openrouter.ai/privacy",
    "huggingface": "https://huggingface.co/privacy",
}


class EnvoyProviderRiskAnnotator:
    """Maps :class:`LlmDeployment` instances to :class:`ProviderRisk`
    annotations and persists them into the Envoy Ledger.

    Per shard 13 § 3.3 + spec § Provider-risk annotation lines 14-36.

    Phase 01 deliverables:

    * :meth:`annotate` — preset→annotation lookup; raises ``ValueError`` for
      deployments lacking a ``preset_name`` (fail-loud per
      ``rules/zero-tolerance.md`` Rule 3).
    * :meth:`emit_ledger_entry` — writes the ``model_invoke`` Ledger entry
      carrying the annotation per spec line 16.
    * :meth:`fail_closed_check` — Provider-bound risk requires
      ``envelope.operational`` to opt in via a ``provider_bound: true``
      ImportedConstraint or AuthoredConstraint key. Phase 01 envelope-
      compiler (shard 4) does NOT yet surface this as a dataclass field;
      see :meth:`fail_closed_check` docstring for the lookup contract.
    """

    #: Self-hosted preset names (local model runtime — no cloud egress
    #: from the user's perspective).
    _SELF_HOSTED_PRESETS: ClassVar[frozenset[str]] = frozenset(
        {"ollama", "llama_cpp", "lm_studio", "docker_model_runner"}
    )

    #: Community preset names (user-declared escape hatches with no
    #: Foundation attestation — user assumes the risk per spec line 34).
    _COMMUNITY_PRESETS: ClassVar[frozenset[str]] = frozenset(
        {"openai_compatible", "anthropic_compatible"}
    )

    #: Provider-bound preset names per shard 13 § 3.3 — proprietary
    #: endpoints without FV attestation in Phase 01; fail-closed unless
    #: envelope allows ``provider_bound: true``.
    _PROVIDER_BOUND_PRESETS: ClassVar[frozenset[str]] = frozenset(
        {
            "openai",
            "anthropic",
            "deepseek",
            "google",
            "cohere",
            "mistral",
            "perplexity",
            "groq",
            "together",
            "fireworks",
            "openrouter",
            "huggingface",
            "azure_openai",
            "azure_entra",
            "bedrock_claude",
            "bedrock_llama",
            "bedrock_titan",
            "bedrock_mistral",
            "bedrock_cohere",
            "vertex_claude",
            "vertex_gemini",
        }
    )

    #: Provider-id mapping per spec line 19 enumeration. Self-hosted
    #: presets normalize to ``local-<runtime>`` per the spec example
    #: ``local-llama`` / ``local-ollama``.
    _PROVIDER_ID_MAP: ClassVar[dict[str, str]] = {
        "ollama": "local-ollama",
        "llama_cpp": "local-llama",
        "lm_studio": "local-lm-studio",
        "docker_model_runner": "local-docker-model-runner",
        # Community escape hatches keep the user's provider-id intent
        # under a ``community-<base>`` prefix so audit grep can find them
        # without conflating with FV-attested namespakes.
        "openai_compatible": "community-openai-compatible",
        "anthropic_compatible": "community-anthropic-compatible",
    }

    def annotate(self, deployment: LlmDeployment) -> ProviderRisk:
        """Map an :class:`LlmDeployment` to its :class:`ProviderRisk`.

        Reads ``deployment.preset_name`` and ``deployment.default_model``;
        emits ``annotated_at`` as the current UTC ISO-8601 timestamp.

        Raises:
            ValueError: ``deployment.preset_name`` is ``None`` (manual
                construction per kaizen.llm.deployment ``frozen=True``
                semantics — manual builds are not preset-attestable).
                Per ``rules/zero-tolerance.md`` Rule 3, this is fail-loud
                rather than a silent ``unknown`` annotation.
        """
        preset = deployment.preset_name
        if preset is None:
            raise ValueError(
                "ProviderRisk annotation requires a preset-built LlmDeployment "
                "(deployment.preset_name is None — manual construction has no "
                "attestable provider identity). Pick a preset from "
                "kaizen.llm.presets or use an escape-hatch preset "
                "(openai_compatible / anthropic_compatible) per spec line 35."
            )

        # Resolve risk_class via the three preset-set frozensets. Unknown
        # presets default to Provider-bound (fail-closed) per spec line 36.
        if preset in self._SELF_HOSTED_PRESETS:
            risk_class: RiskClass = "Self-hosted"
            leak_class: TrainingDataLeakClass = "low"
            retention_url = _UNKNOWN_RETENTION_URL
        elif preset in self._COMMUNITY_PRESETS:
            risk_class = "Community"
            leak_class = "unknown"
            retention_url = _UNKNOWN_RETENTION_URL
        elif preset in self._PROVIDER_BOUND_PRESETS:
            risk_class = "Provider-bound"
            leak_class = "unknown"
            retention_url = _PROVIDER_RETENTION_URLS.get(preset, _UNKNOWN_RETENTION_URL)
        else:
            # Unknown preset — fail closed by classifying as Provider-bound
            # per spec line 36 ("runtime fails closed unless envelope
            # explicitly allows provider_bound: true").
            risk_class = "Provider-bound"
            leak_class = "unknown"
            retention_url = _UNKNOWN_RETENTION_URL

        provider_id = self._PROVIDER_ID_MAP.get(preset, preset)
        # default_model is Optional[str] on LlmDeployment; fall back to
        # the preset name when None (manual override path).
        model_family = deployment.default_model or preset
        # Phase 01 has no version-tag tracking — record the model name
        # itself; Phase 02+ Foundation registry adds provider-declared
        # version semantics.
        model_version = deployment.default_model or "unknown"
        annotated_at = datetime.now(timezone.utc).isoformat()

        return ProviderRisk(
            provider_id=provider_id,
            model_family=model_family,
            model_version=model_version,
            risk_class=risk_class,
            training_data_leak_class=leak_class,
            jurisdiction="mixed",  # Phase 01: no per-region attestation.
            data_retention_policy_url=retention_url,
            annotated_at=annotated_at,
            # Phase 01: no Foundation attestation surface yet (Phase 02+
            # via `specs/foundation-ops.md` FV registry). Self-hosted
            # entries are explicitly None per spec line 27.
            foundation_attestation_signature_hex=None,
        )

    async def emit_ledger_entry(
        self,
        ledger: EnvoyLedger,
        risk: ProviderRisk,
        action_id: str,
    ) -> str:
        """Write a ``model_invoke`` Ledger entry carrying ``risk``.

        Per spec line 16 + § Cross-domain consumer mapping line 60 (the
        ``model_switch`` family). Returns the new entry_id from
        :meth:`EnvoyLedger.append`.

        Args:
            ledger: The Envoy Ledger facade (shard 6 T-01-18).
            risk: The annotation to persist.
            action_id: The runtime action correlation id (joins
                ``model_invoke`` to the originating action's Ledger entries
                per ``rules/observability.md`` Rule 2 correlation contract).
        """
        # INFO→DEBUG per `rules/observability.md` Rule 8: `provider_id` +
        # `risk_class` are schema-revealing identifiers (deployment-topology
        # leakage to log aggregators). /redteam Round 1 MEDIUM-1.
        logger.debug(
            "model.risk_annotation.emit.start",
            extra={
                "action_id": action_id,
                "provider_id": risk.provider_id,
                "risk_class": risk.risk_class,
            },
        )
        entry_id = await ledger.append(
            entry_type="model_invoke",
            content={
                "action_id": action_id,
                "provider_risk": risk.to_dict(),
            },
            intent_id=action_id,
        )
        # INFO→DEBUG per `rules/observability.md` Rule 8: `provider_id` is
        # schema-revealing. `entry_id_hint` is already an 8-char hash prefix
        # (Rule 8 hash form, safe). Demoting whole line keeps contract uniform
        # with .start. /redteam Round 1 MEDIUM-1.
        logger.debug(
            "model.risk_annotation.emit.ok",
            extra={
                "action_id": action_id,
                "entry_id_hint": entry_id[:8],
                "provider_id": risk.provider_id,
            },
        )
        return entry_id

    def fail_closed_check(self, risk: ProviderRisk, envelope: EnvelopeConfig) -> None:
        """Raise :class:`ProviderRiskAnnotationMissingError` if
        ``risk_class == "Provider-bound"`` AND the envelope does not opt in.

        Per spec line 36 + line 67 + shard 13 § 3.3 fail-closed default.

        **Phase 01 lookup contract.** The envelope-compiler (shard 4) does
        NOT yet surface ``provider_bound`` as a typed dataclass field on
        :class:`OperationalDimension` (its fields are ``tool_allowlist``,
        ``tool_denylist``, ``rate_limits``, ``sub_agent_spawn_limit``,
        ``authored_constraints``, ``imported_constraints``). Until that
        wiring lands, the opt-in lives inside the envelope's
        ``authored_constraints`` and ``imported_constraints`` tuples as a
        constraint with ``constraint_id == "provider_bound"`` whose
        ``rule_ast`` carries ``{"allowed": True}``. Authored constraints
        (user-declared) win over imported (parent-envelope-imported) per
        the compiler's intersection rules, but EITHER suffices to opt in.

        Returns:
            None on success (risk is FV / Community / Self-hosted, OR
            Provider-bound + envelope opted in).

        Raises:
            ProviderRiskAnnotationMissingError: Provider-bound risk AND
                no opt-in. The runtime MUST surface this fail-closed
                refusal to the user per spec line 67.
        """
        if risk.risk_class != "Provider-bound":
            return

        # Phase 01 opt-in lookup: scan the envelope's authored +
        # imported constraint tuples for a name-keyed entry. This is the
        # spec-acknowledged transitional shape per shard 13 § 3.3 — the
        # Phase 02 envelope-compiler upgrade replaces this with a typed
        # ``operational.provider_bound: bool`` field.
        if _envelope_allows_provider_bound(envelope):
            return

        raise ProviderRiskAnnotationMissingError(
            f"Provider-bound endpoint (preset={risk.provider_id}, "
            f"model={risk.model_family}) requires the active envelope to "
            f"opt in via an operational constraint with "
            f"constraint_id='provider_bound' and rule_ast={{'allowed': True}} "
            f"(authored or imported). Without this opt-in, the runtime "
            f"fails closed per specs/model-adapter.md line 36."
        )


def _envelope_allows_provider_bound(envelope: EnvelopeConfig) -> bool:
    """Return True if any operational constraint with
    ``constraint_id == "provider_bound"`` opts in.

    Tuple-iterating lookup per shard 13 § 3.3 — Phase 01 transitional
    shape. Centralized so the test suite can pin the lookup contract
    against a single helper rather than re-implementing the scan per
    test.
    """
    operational = envelope.operational
    for constraint in operational.authored_constraints:
        if _constraint_is_provider_bound_opt_in(constraint):
            return True
    for constraint in operational.imported_constraints:
        if _constraint_is_provider_bound_opt_in(constraint):
            return True
    return False


def _constraint_is_provider_bound_opt_in(constraint: Any) -> bool:
    """Inspect a single AuthoredConstraint / ImportedConstraint for the
    provider_bound opt-in shape.

    AuthoredConstraint / ImportedConstraint are dataclasses defined in
    :mod:`envoy.envelope.types`. Both share ``constraint_id: str`` and
    ``rule_ast: dict[str, Any]``. Phase 01 looks for ``constraint_id ==
    "provider_bound"`` AND ``rule_ast.get("allowed") is True``. The
    AST-keyed shape mirrors how other operational constraints are encoded
    by the shard 4 envelope compiler.
    """
    cid = getattr(constraint, "constraint_id", None)
    if cid != "provider_bound":
        return False
    rule_ast = getattr(constraint, "rule_ast", None)
    if not isinstance(rule_ast, dict):
        return False
    return rule_ast.get("allowed") is True


__all__ = [
    "EnvoyProviderRiskAnnotator",
    "ProviderRisk",
    "RiskClass",
    "TrainingDataLeakClass",
]
