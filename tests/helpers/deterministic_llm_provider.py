# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Deterministic LLM provider for boundary-conversation tests.

Per `rules/testing.md` § "Protocol Adapters" exception: a class satisfying
a `typing.Protocol` at runtime with deterministic output is NOT a mock.
This module ships three Protocol-Satisfying Deterministic Adapters that
let Boundary Conversation tests run end-to-end WITHOUT a live LLM:

- :class:`DeterministicProvider` — satisfies the legacy kaizen provider
  ``chat`` / ``chat_async`` surface the runtime invokes via
  ``envoy.boundary_conversation.runtime._PRESET_PROVIDER`` dispatch.
- :class:`_StubDeployment` / :class:`_StubLlmClient` — minimal duck-typed
  clones of ``kaizen.llm.client.LlmDeployment`` / ``LlmClient`` that the
  runtime's ``_chat`` reads via attribute access only
  (``deployment.preset_name`` + ``deployment.default_model``).
- :class:`DeterministicModelRouter` — satisfies the
  ``EnvoyModelRouter.for_primitive(name) -> LlmClient`` surface the
  runtime calls at line 382 of ``envoy/boundary_conversation/runtime.py``.

Why not real ``LlmDeployment``? It is a pydantic model with mandatory
``wire`` / ``endpoint`` / ``auth`` fields that exist to validate live
deployments — irrelevant in a deterministic test where no network call
fires. Duck-typing preserves the runtime's read-only access pattern
without the validation noise.

Dispatch
--------
``DeterministicProvider.chat(messages, model)`` inspects the prompt body
for the unique output-field-name fingerprints from
``envoy.boundary_conversation.signatures`` (e.g.
``monthly_ceiling_microdollars`` → S1) and returns a canned JSON
extraction matching that state's ``Signature.output_fields`` shape. Per
``rules/agent-reasoning.md`` and ``rules/probe-driven-verification.md``
MUST-3: the dispatch is structural (substring match on a closed-vocab
field-name set), not LLM-based.

Registration
------------
The runtime resolves provider classes via
``runtime._PRESET_PROVIDER[preset_name] -> (module_path, class_name)``.
Tests register this stub provider by monkeypatching the dict:

    monkeypatch.setitem(
        runtime._PRESET_PROVIDER,
        "deterministic_test",
        ("tests.helpers.deterministic_llm_provider", "DeterministicProvider"),
    )

Then construct the model_router as
``DeterministicModelRouter(preset_name="deterministic_test")``.

The fingerprint table below is exhaustive for the Phase-01 S1..S9
signatures (verified against
``envoy/boundary_conversation/signatures.py`` at the time of writing).
A new signature requires a new fingerprint entry here.
"""

from __future__ import annotations

import json
from typing import Any


# Fingerprint table — maps a unique output-field-name (or combination) from
# each S1..S9 signature's JSON-schema rendering to the canned extraction
# that signature expects.  The runtime's `_build_structured_prompt` emits
# every output field name into the schema text, so an exact-substring scan
# is sufficient and unambiguous.  Per `envoy/boundary_conversation/signatures.py`.
_CANNED_EXTRACTIONS: dict[str, dict[str, Any]] = {
    # S1 — monthly_ceiling_microdollars is unique to S1MoneySignature.
    "monthly_ceiling_microdollars": {
        "monthly_ceiling_microdollars": 100_000_000,  # 100 USD
    },
    # S2 — blocked_contacts is unique to S2PeopleSignature.
    "blocked_contacts": {
        "blocked_contacts": [],
    },
    # S3 — blocked_topic_rules is unique to S3TopicsSignature.
    "blocked_topic_rules": {
        "blocked_topic_rules": ["no political endorsements"],
    },
    # S4 — operating_hours is unique to S4HoursSignature.
    "operating_hours": {
        "operating_hours": {"days": ["mon", "tue", "wed", "thu", "fri"], "tz": "UTC"},
    },
    # S5 — first_task_intent is unique to S5FirstTaskSignature.
    "first_task_intent": {
        "first_task_intent": {"goal": "summarize my unread newsletters once a day"},
    },
    # S6 — use_template + template_id (use_template is the discriminator).
    "use_template": {
        "use_template": False,
        "template_id": "",
    },
    # S7 — phrase is unique to S7VisibleSecretSignature.
    "phrase": {
        "icon": "star",
        "color": "blue",
        "phrase": "open sky",
    },
    # S8 — total_shards is unique to S8ShamirSignature.
    "total_shards": {
        "threshold": 3,
        "total_shards": 5,
        "distribution_mode": "default",
    },
    # S9 — plain_language_summary is unique to S9ReviewSignSignature.
    "plain_language_summary": {
        "plain_language_summary": (
            "Monthly cap 100 USD; no blocked contacts; no political endorsements; "
            "operating Mon-Fri UTC; first task is to summarize newsletters daily; "
            "3-of-5 Shamir default backup; visible secret star/blue/'open sky'."
        ),
        "signed": True,
    },
}


def _pick_extraction(prompt: str) -> dict[str, Any]:
    """Pick the canned extraction whose discriminator appears in ``prompt``.

    Per the dispatch contract in the module docstring: each S1..S9 signature
    has a uniquely-named output field; the runtime renders that field name
    verbatim into the JSON schema portion of the prompt, so substring scan
    is sufficient.
    """
    for fingerprint, extraction in _CANNED_EXTRACTIONS.items():
        if fingerprint in prompt:
            return extraction
    raise ValueError(
        "DeterministicProvider received a prompt with no known signature "
        "fingerprint. Add the new signature's discriminating output-field "
        f"name to _CANNED_EXTRACTIONS. Prompt head: {prompt[:200]!r}"
    )


class DeterministicProvider:
    """Satisfies the legacy kaizen provider ``chat`` surface deterministically.

    Mirrors ``kaizen.providers.llm.ollama.OllamaProvider.chat(messages, **kwargs)
    -> dict[str, Any]`` shape: returns a dict the runtime's
    ``_extract_chat_content`` can read.

    Per ``envoy/boundary_conversation/runtime.py:415-424``: the runtime
    branches on ``hasattr(provider, "chat_async")``; this class exposes
    ``chat`` (sync) only — mirroring Ollama's surface — so the sync branch
    fires.
    """

    def chat(
        self, messages: list[dict[str, str]], model: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """Return ``{"message": {"content": "<json>"}}`` matching the Ollama
        native response shape per ``_extract_chat_content`` line 718-720."""
        del model, kwargs  # deterministic — no model branching, no kwargs
        if not messages:
            raise ValueError("DeterministicProvider.chat received empty messages")
        prompt = messages[-1].get("content", "")
        extraction = _pick_extraction(prompt)
        return {"message": {"content": json.dumps(extraction)}}


class _StubDeployment:
    """Duck-typed clone of ``kaizen.llm.client.LlmDeployment``.

    The runtime's ``_chat`` reads ONLY ``preset_name`` + ``default_model``
    (via ``getattr`` at line 401-402 of runtime.py), so this two-attribute
    namespace is sufficient.  Real ``LlmDeployment`` is a pydantic model
    with mandatory ``wire`` / ``endpoint`` / ``auth`` fields that exist to
    validate live deployments — irrelevant when no network call fires.
    """

    def __init__(self, *, preset_name: str, default_model: str) -> None:
        self.preset_name = preset_name
        self.default_model = default_model


class _StubLlmClient:
    """Duck-typed clone of ``kaizen.llm.client.LlmClient``.

    The runtime reads ``client.deployment`` and the deployment's
    ``preset_name`` / ``default_model``; nothing else.  Single-attribute
    namespace is sufficient.
    """

    def __init__(self, *, deployment: _StubDeployment) -> None:
        self.deployment = deployment


class DeterministicModelRouter:
    """Satisfies the ``EnvoyModelRouter.for_primitive(name) -> LlmClient``
    surface ``envoy/boundary_conversation/runtime.py:382`` calls.

    Returns the same stub client for every primitive — every boundary-
    conversation state goes through the same deterministic dispatch.
    Per ``rules/testing.md`` § "Protocol Adapters": deterministic, no
    ``unittest.mock``, no network — counts as a Protocol-Satisfying
    Adapter, NOT a mock.
    """

    def __init__(
        self, *, preset_name: str = "deterministic_test", default_model: str = "stub-model"
    ) -> None:
        self._client = _StubLlmClient(
            deployment=_StubDeployment(preset_name=preset_name, default_model=default_model)
        )

    def for_primitive(self, primitive: str) -> _StubLlmClient:
        del primitive  # router returns the same stub for every primitive
        return self._client


__all__ = [
    "DeterministicProvider",
    "DeterministicModelRouter",
]
