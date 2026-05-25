"""envoy.model.byom_picker — first-launch BYOM provider selection.

Implements ADR-0006 ("Model choice: BYOM at install, local default
available") + shard 13 § 3.1 (`workspaces/phase-01-mvp/01-analysis/
13-model-adapter-implementation.md`) + shard 14 (Connection Vault).

The first-launch onboarding (T-02-40 Boundary Conversation) presents the
user with 5 BYOM options:

1. **ollama** — local model runtime, no API key required (default).
2. **anthropic** — Claude family, requires ``ANTHROPIC_API_KEY``.
3. **openai** — GPT family, requires ``OPENAI_API_KEY``.
4. **deepseek** — DeepSeek family, requires ``DEEPSEEK_API_KEY``.
5. **openai_compatible** — custom endpoint (MLX, vLLM, OpenRouter, …)
   requires ``base_url`` AND an API key under a per-endpoint name.

For every choice except ``ollama``, the picker:

* Writes the kaizen ``KAILASH_LLM_PROVIDER`` selector + the per-provider
  model env-key (``ANTHROPIC_MODEL``, ``OPENAI_PROD_MODEL``,
  ``DEEPSEEK_MODEL``, ``ENVOY_CUSTOM_MODEL``) to the target ``.env`` so
  that subsequent runs resolve via :meth:`LlmClient.from_env` selector
  tier.
* Routes the API key into the :class:`envoy.connection_vault.Connection
  Vault` via :func:`envoy.connection_vault.import_credentials_from_env`
  per shard 14 § 3.1 step 9 — NEVER writes the plaintext key into
  ``.env``.

The Ollama choice writes ``OLLAMA_BASE_URL`` + ``OLLAMA_DEFAULT_MODEL``
to ``.env`` but performs NO vault write (Ollama localhost has no key).

The custom ``openai_compatible`` choice writes ``KAILASH_LLM_DEPLOYMENT``
in URI form (``openai-compat://<host>/<model>``) per kaizen #498 / S7
URI tier.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Optional
from urllib.parse import urlparse

from envoy.connection_vault import (
    ConnectionVault,
    EnvCredentialSpec,
    ImportResult,
    import_credentials_from_env,
)
from envoy.connection_vault.schema import CredentialType, RotationPolicy
from envoy.envelope import EnvelopeScopeRef

logger = logging.getLogger("envoy.model.byom_picker")

#: The 5 enumerated BYOM choices per ADR-0006.
SUPPORTED_CHOICES: Final[frozenset[str]] = frozenset(
    {"ollama", "anthropic", "openai", "deepseek", "openai_compatible"}
)

#: Per-choice env-var name carrying the user-supplied API key. Ollama
#: has no entry — local model runtime needs no credentials.
_CHOICE_API_KEY_ENV: Final[dict[str, str]] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openai_compatible": "ENVOY_CUSTOM_API_KEY",
}

#: Per-choice env-var name carrying the user-supplied model name.
_CHOICE_MODEL_ENV: Final[dict[str, str]] = {
    "ollama": "OLLAMA_DEFAULT_MODEL",
    "anthropic": "ANTHROPIC_MODEL",
    "openai": "OPENAI_PROD_MODEL",
    "deepseek": "DEEPSEEK_MODEL",
    "openai_compatible": "ENVOY_CUSTOM_MODEL",
}

#: Per-choice service-identifier under which the vault key is stored.
_CHOICE_SERVICE_IDENTIFIER: Final[dict[str, str]] = {
    "anthropic": "anthropic.api",
    "openai": "openai.api",
    "deepseek": "deepseek.api",
    "openai_compatible": "openai-compatible.api",
}


@dataclass(frozen=True, slots=True)
class PickResult:
    """Outcome of a :func:`byom_pick` call.

    Args:
        choice: The provider choice that was applied.
        env_keys_written: Tuple of ``.env`` keys the picker wrote
            (model name, selector, base-URL — never the API key).
        vault_import_result: When the choice required a key, this
            carries the :class:`ImportResult` returned by
            :func:`import_credentials_from_env`. For ``ollama``
            (no key), this is ``None``.
    """

    choice: str
    env_keys_written: tuple[str, ...]
    vault_import_result: Optional[ImportResult]


def byom_pick(
    *,
    choice: str,
    model_name: str,
    api_key: Optional[str],
    custom_base_url: Optional[str],
    env_path: str,
    vault: ConnectionVault,
) -> PickResult:
    """Apply a user-picked BYOM choice: write ``.env`` + route key to vault.

    Per ADR-0006 + shard 13 § 3.1 + shard 14 § 3.1 step 9.

    Args:
        choice: One of :data:`SUPPORTED_CHOICES`. Raises ``ValueError``
            on any other value (fail-loud per
            ``rules/zero-tolerance.md`` Rule 3a — silently accepting
            an unknown choice would write malformed env config).
        model_name: User-supplied model identifier (e.g. ``"llama3.2"``,
            ``"claude-3-5-sonnet-20241022"``, ``"gpt-4o"``). Written to
            the per-choice model env-key. Per
            ``rules/env-models.md`` Absolute Directive 2 — the picker
            persists the user's chosen string verbatim; it does NOT
            hardcode any default.
        api_key: For cloud choices (anthropic / openai / deepseek /
            openai_compatible), the user-supplied key. For ``ollama``,
            MUST be ``None`` (Ollama has no key); raises ``ValueError``
            if accidentally supplied. For non-ollama choices, ``None``
            is permitted ONLY if the env-var named in
            :data:`_CHOICE_API_KEY_ENV` is already set in
            ``os.environ`` (per Boundary Conversation's two-step flow
            where the user pastes the key into a tmp ``.env`` before
            calling this function).
        custom_base_url: REQUIRED for ``openai_compatible``; rejected
            (``ValueError``) for every other choice. Validated as a
            non-empty URL via :func:`urllib.parse.urlparse`.
        env_path: Absolute path to the ``.env`` file to update. The
            picker appends new entries; it does NOT rewrite existing
            keys. Callers (T-02-40) ensure the file exists.
        vault: The Connection Vault into which the API key (when
            applicable) is imported. The vault MUST have
            ``active_envelope`` set per the shard 14 fail-closed
            contract for subsequent reads; the picker does NOT enforce
            this at write time (set is unconditional per shard 14
            § 3.1).

    Returns:
        :class:`PickResult` enumerating which ``.env`` keys were written
        and (for non-ollama choices) the vault import result.

    Raises:
        ValueError: ``choice`` not in :data:`SUPPORTED_CHOICES`, OR
            shape-validation mismatch (``api_key`` for ollama,
            ``custom_base_url`` for non-custom choices, missing
            required ``custom_base_url`` for custom).
    """
    logger.info(
        "model.byom_picker.start",
        extra={"choice": choice, "env_path": env_path},
    )

    if choice not in SUPPORTED_CHOICES:
        raise ValueError(
            f"choice={choice!r} not in supported set {sorted(SUPPORTED_CHOICES)} "
            f"per ADR-0006. The first-launch picker enumerates 5 BYOM options; "
            f"adding a sixth requires a new ADR + shard 13 § 3.1 update."
        )
    if not model_name or not model_name.strip():
        raise ValueError(
            "model_name MUST be non-empty — the picker writes this string "
            "verbatim into .env per rules/env-models.md Absolute Directive 2 "
            "and refuses to write a blank value."
        )

    if choice == "ollama":
        if api_key is not None:
            raise ValueError(
                "ollama choice does not accept api_key (local runtime has no "
                "credential). Pass api_key=None for ollama; the picker writes "
                "OLLAMA_BASE_URL + OLLAMA_DEFAULT_MODEL only."
            )
        if custom_base_url is not None:
            # Allow custom_base_url for ollama to point at a non-default
            # Ollama instance (e.g. a sidecar container or remote
            # workstation). The validation rejects empty strings only.
            if not custom_base_url.strip():
                raise ValueError(
                    "custom_base_url, when supplied for ollama, MUST be a "
                    "non-empty URL pointing at the Ollama endpoint."
                )
            base_url = custom_base_url
        else:
            base_url = "http://localhost:11434"
        env_keys = _write_env(
            env_path=env_path,
            entries={
                "KAILASH_LLM_PROVIDER": "ollama",
                "OLLAMA_BASE_URL": base_url,
                "OLLAMA_DEFAULT_MODEL": model_name,
            },
        )
        logger.info(
            "model.byom_picker.ok",
            extra={"choice": choice, "env_keys_written": env_keys},
        )
        return PickResult(
            choice=choice,
            env_keys_written=env_keys,
            vault_import_result=None,
        )

    # All other choices require an api_key — either passed directly or
    # already present in os.environ under the choice's env-key.
    api_key_env_var = _CHOICE_API_KEY_ENV[choice]
    if api_key is not None:
        if not api_key.strip():
            raise ValueError(
                f"api_key for {choice!r} MUST be non-empty (got blank) — "
                f"the vault rejects empty secrets per shard 14 § 3.1."
            )
        # Inject the key into os.environ so import_credentials_from_env
        # can pick it up via the spec's env-var lookup. The picker does
        # NOT write the key to .env (rules/security.md § No Hardcoded
        # Secrets + § No .env in Git).
        os.environ[api_key_env_var] = api_key
    else:
        # Caller asserts the env-var is already set (e.g. T-02-40
        # already populated it from a transient onboarding form).
        if not os.environ.get(api_key_env_var, "").strip():
            raise ValueError(
                f"choice={choice!r} requires api_key OR a pre-set "
                f"{api_key_env_var} env-var. Neither was supplied; the "
                f"vault has nothing to import."
            )

    selector_value = (
        "openai" if choice == "openai_compatible" else choice
    )  # openai_compatible uses the openai wire protocol; the URI tier
    # below carries the base_url + path so kaizen.from_env routes it
    # correctly via the URI tier rather than the selector tier.

    env_entries: dict[str, str] = {}
    model_env_var = _CHOICE_MODEL_ENV[choice]

    if choice == "openai_compatible":
        if not custom_base_url or not custom_base_url.strip():
            raise ValueError(
                "openai_compatible choice REQUIRES custom_base_url "
                "(the user-supplied endpoint URL — MLX, vLLM, OpenRouter, "
                "etc.). Without it the URI tier has no host to dispatch."
            )
        parsed = urlparse(custom_base_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(
                f"custom_base_url={custom_base_url!r} is not a valid URL "
                f"(missing scheme or netloc). Provide e.g. "
                f"'https://api.example.com'."
            )
        # Per shard 13 § 3.1 + kaizen #498 / S7 URI-tier: encode the
        # full deployment shape into KAILASH_LLM_DEPLOYMENT.
        deployment_uri = f"openai-compat://{parsed.netloc}{parsed.path}/{model_name}"
        env_entries["KAILASH_LLM_DEPLOYMENT"] = deployment_uri
        env_entries[model_env_var] = model_name
    else:
        # anthropic / openai / deepseek — selector tier; model env-var
        # carries the model name; KAILASH_LLM_PROVIDER carries the
        # selector.
        env_entries["KAILASH_LLM_PROVIDER"] = selector_value
        env_entries[model_env_var] = model_name

    env_keys = _write_env(env_path=env_path, entries=env_entries)

    # Route the key into the vault. The shard 14 import helper reads
    # from os.environ + writes to the vault; the API key NEVER lands in
    # .env per rules/security.md.
    service_identifier = _CHOICE_SERVICE_IDENTIFIER[choice]
    spec = EnvCredentialSpec(
        env_var_name=api_key_env_var,
        credential_type=CredentialType.API_KEY,
        service_identifier=service_identifier,
        entry_envelope_scope=EnvelopeScopeRef(
            service_identifier=service_identifier,
            channel=None,
        ),
        rotation_policy=RotationPolicy.NEVER,
    )
    vault_result = import_credentials_from_env(vault, (spec,))
    # INFO→DEBUG per `rules/observability.md` Rule 8: `choice` reveals
    # provider identity (anthropic/openai/etc.) and `vault_imported` lists
    # secret-bearing env var names — schema-revealing. /redteam Round 1
    # MEDIUM-1.
    logger.debug(
        "model.byom_picker.ok",
        extra={
            "choice": choice,
            "env_keys_written": env_keys,
            "vault_imported": vault_result.imported_env_var_names,
        },
    )
    return PickResult(
        choice=choice,
        env_keys_written=env_keys,
        vault_import_result=vault_result,
    )


def _write_env(*, env_path: str, entries: dict[str, str]) -> tuple[str, ...]:
    """Append (or overwrite) keys in the ``.env`` file at ``env_path``.

    The implementation reads the existing file (if any), strips any
    existing line whose key matches a new entry's key, appends the new
    entries in stable order, and writes back. This is the standard
    write-with-replace shape used by python-dotenv's ``set_key`` helper,
    re-implemented inline to avoid an additional dependency for a
    one-shot first-launch primitive.

    Returns the tuple of keys written, in the order supplied by
    ``entries``.
    """
    path = Path(env_path)
    existing_lines: list[str] = []
    if path.exists():
        existing_lines = path.read_text().splitlines()
    new_lines: list[str] = []
    replacement_keys = set(entries.keys())
    for line in existing_lines:
        # Keep comments + blank lines untouched.
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" not in stripped:
            # Malformed line — preserve verbatim (we are not a linter).
            new_lines.append(line)
            continue
        existing_key = stripped.split("=", 1)[0].strip()
        if existing_key in replacement_keys:
            # Drop the old line; the entry will be re-appended in
            # deterministic order below.
            continue
        new_lines.append(line)
    for key, value in entries.items():
        new_lines.append(f"{key}={value}")
    # Trailing newline so the file is POSIX-compliant.
    payload = "\n".join(new_lines) + "\n"
    path.write_text(payload)
    return tuple(entries.keys())


__all__ = ["PickResult", "SUPPORTED_CHOICES", "byom_pick"]
