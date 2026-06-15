# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.runtime_picker — first-run runtime selection (S3p Build half).

Implements `specs/runtime-abstraction.md` § Runtime picker (`:198-200`) +
ADR-0001 ("Run with Rust acceleration or pure-Python, default Rust, opt-out
one keystroke" — `DECISIONS.md:47`) + ADR-0009 item 4 (transparent disclosure,
no hidden defaults — `DECISIONS.md:300`).

This module is the Build half: the durable **runtime-choice config** + its
wire schema (Spec-gap-6) + the resolution `selection.get_runtime` reads. The
Wire half (the `envoy runtime show / switch` CLI + the cold-unlock → attest →
re-read → signed-`runtime_switch` state machine) lives in `envoy/cli/runtime.py`.

Precedent: this mirrors `envoy/model/byom_picker.py` — a fail-loud picker
function + a frozen result dataclass + a `_DEFAULT_*` config-path convention
under `~/.envoy/`. Unlike the BYOM picker (which writes plaintext `.env`
selectors), the runtime choice is **signed** by the Genesis/device Ed25519 key
so a tampered choice is detectable at `envoy runtime show` / switch time.

## Config wire schema (Spec-gap-6 — `runtime-choice/1.0`)

```json
{
  "schema_version": "runtime-choice/1.0",
  "runtime_family": "kailash-rs-bindings | kailash-py",
  "chosen_at": "<iso8601 microsecond-padded UTC>",
  "chosen_by_genesis_id": "<principal_genesis_id — 64-hex sha256>",
  "signature_hex": "<ed25519 over canonical(payload minus signature_hex)>"
}
```

## Availability gate (the load-bearing decision)

ADR-0001 makes `kailash-rs-bindings` the runtime the picker *presents as the
default*. But `kailash-rs-bindings` is only a *selectable* runtime once the
byte-identical conformance slice (S2b/S2c/S3a/S3b) is green on BOTH runtimes —
the `RS_BINDINGS_ENABLED` flag (`01-m1-ws1-runtime-pluggability.md:147`). While
that flag is `False`, the rs adapter is structurally present but not
conformance-green, so the picker MUST NOT persist it: choosing a runtime
`get_runtime` would then refuse is a silent dead-end. `write_runtime_choice`
therefore raises `RsBindingsNotAvailableInPhase01Error` (fail-loud per
`rules/zero-tolerance.md` Rule 3) when asked to write rs-bindings while the flag
is `False`, and `presented_default_family()` falls back to `kailash-py`. When
the flag flips, rs-bindings becomes both the presented default AND writable —
no code change here.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final, Protocol

from envoy.ledger.canonical import canonical_dumps
from envoy.runtime import feature_flags
from envoy.runtime.errors import RsBindingsNotAvailableInPhase01Error

logger = logging.getLogger(__name__)

#: Pinned wire-schema version for the runtime-choice config.
RUNTIME_CHOICE_SCHEMA_VERSION: Final[str] = "runtime-choice/1.0"

#: The two runtime families a choice may name. Mirrors the families
#: `selection.get_runtime` dispatches on; adding a third requires a new ADR.
KNOWN_FAMILIES: Final[frozenset[str]] = frozenset(
    {"kailash-py", "kailash-rs-bindings"}
)

#: Env-var override for the runtime-choice config path (mirrors the
#: ENVOY_TRUST_ANCHOR_DIR / ENVOY_VAULT_PATH convention in envoy/cli/init.py).
ENV_RUNTIME_CHOICE_PATH: Final[str] = "ENVOY_RUNTIME_CHOICE_PATH"

#: Default config location, under the same ~/.envoy home the trust anchor uses.
_DEFAULT_RUNTIME_CHOICE_PATH: Final[str] = "~/.envoy/runtime-choice.json"


class _KeyManagerProtocol(Protocol):
    """The signing surface this module needs — the same protocol the ledger
    facade declares (`envoy/ledger/facade.py:108`). `sign_with_key` is sync and
    returns the hex signature; `verify` is async; `get_public_key` is sync."""

    def sign_with_key(self, key_id: str, payload: Any) -> str: ...

    async def verify(self, payload: Any, signature: str, public_key: str) -> bool: ...

    def get_public_key(self, key_id: str) -> str | None: ...


class RuntimeChoiceCorruptError(ValueError):
    """The on-disk runtime-choice config is unparseable, wrong-schema, or names
    an unknown runtime family. Raised loud (NOT a silent fallback to a default
    family) per `rules/zero-tolerance.md` Rule 3 — a corrupt choice file is an
    integrity event, not a missing-config event."""


class RuntimeChoiceSignatureError(ValueError):
    """The runtime-choice config's signature does not verify against the
    expected Genesis/device public key — the choice was tampered after signing
    (T-060-adjacent). Fail-closed: callers MUST refuse to act on the choice."""


def _require_nonempty_str(data: dict[str, Any], key: str) -> str:
    """Return ``data[key]`` as a non-empty str, else raise
    :class:`RuntimeChoiceCorruptError` (fail-loud, narrows the type)."""
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeChoiceCorruptError(
            f"runtime-choice {key} must be a non-empty str (got {value!r})"
        )
    return value


@dataclass(frozen=True, slots=True)
class RuntimeChoice:
    """A durable, signed first-run runtime selection (`runtime-choice/1.0`)."""

    runtime_family: str
    chosen_at: str
    chosen_by_genesis_id: str
    signature_hex: str
    schema_version: str = RUNTIME_CHOICE_SCHEMA_VERSION

    def signing_payload(self) -> dict[str, str]:
        """The canonical-signed payload — every field EXCEPT `signature_hex`.

        Both `write_runtime_choice` (sign) and `verify_runtime_choice`
        (verify) canonical-encode exactly this dict, so the signed bytes are
        identical on both sides of the contract.
        """
        return {
            "schema_version": self.schema_version,
            "runtime_family": self.runtime_family,
            "chosen_at": self.chosen_at,
            "chosen_by_genesis_id": self.chosen_by_genesis_id,
        }

    def to_wire(self) -> dict[str, str]:
        """Full wire dict (signing payload + `signature_hex`)."""
        return {**self.signing_payload(), "signature_hex": self.signature_hex}

    @classmethod
    def from_wire(cls, data: Any) -> RuntimeChoice:
        """Parse + validate a wire dict. Raises `RuntimeChoiceCorruptError` on
        any shape/schema/family violation (fail-loud)."""
        if not isinstance(data, dict):
            raise RuntimeChoiceCorruptError(
                f"runtime-choice config must be a JSON object (got "
                f"{type(data).__name__!r})"
            )
        schema_version = _require_nonempty_str(data, "schema_version")
        if schema_version != RUNTIME_CHOICE_SCHEMA_VERSION:
            raise RuntimeChoiceCorruptError(
                f"runtime-choice schema_version must be "
                f"{RUNTIME_CHOICE_SCHEMA_VERSION!r} (got {schema_version!r})"
            )
        family = _require_nonempty_str(data, "runtime_family")
        if family not in KNOWN_FAMILIES:
            raise RuntimeChoiceCorruptError(
                f"runtime_family={family!r} not in {sorted(KNOWN_FAMILIES)} — "
                f"a runtime-choice config naming an unknown family is corrupt, "
                f"not a missing-config event."
            )
        return cls(
            runtime_family=family,
            chosen_at=_require_nonempty_str(data, "chosen_at"),
            chosen_by_genesis_id=_require_nonempty_str(data, "chosen_by_genesis_id"),
            signature_hex=_require_nonempty_str(data, "signature_hex"),
            schema_version=schema_version,
        )


def resolve_runtime_choice_path(path: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the runtime-choice config path: explicit arg, else
    `ENVOY_RUNTIME_CHOICE_PATH`, else `~/.envoy/runtime-choice.json`."""
    raw = (
        os.fspath(path)
        if path is not None
        else os.environ.get(ENV_RUNTIME_CHOICE_PATH) or _DEFAULT_RUNTIME_CHOICE_PATH
    )
    return Path(raw).expanduser()


def presented_default_family() -> str:
    """The runtime family the picker presents as the one-keystroke default.

    ADR-0001 default is `kailash-rs-bindings`, but only once the rs adapter is
    conformance-green (`RS_BINDINGS_ENABLED`). Until then the presented default
    is `kailash-py` — the picker never offers a runtime it cannot honor.
    """
    return (
        "kailash-rs-bindings"
        if feature_flags.RS_BINDINGS_ENABLED
        else "kailash-py"
    )


def _validate_genesis_id(genesis_id: str) -> None:
    if not isinstance(genesis_id, str) or len(genesis_id) != 64:
        raise ValueError(
            f"chosen_by_genesis_id must be a 64-hex principal_genesis_id "
            f"(got {genesis_id!r}) — see "
            f"envoy.ledger.keystore.principal_genesis_id."
        )
    try:
        int(genesis_id, 16)
    except ValueError as exc:
        raise ValueError(
            f"chosen_by_genesis_id={genesis_id!r} is not hex — "
            f"principal_genesis_id is sha256-hex."
        ) from exc


def write_runtime_choice(
    *,
    family: str,
    genesis_id: str,
    key_manager: _KeyManagerProtocol,
    signing_key_id: str,
    path: str | os.PathLike[str] | None = None,
    now: datetime | None = None,
) -> RuntimeChoice:
    """Sign + persist a runtime-choice config (0o600). Returns the choice.

    Args:
        family: One of :data:`KNOWN_FAMILIES`. Choosing
            ``"kailash-rs-bindings"`` while ``RS_BINDINGS_ENABLED`` is False
            raises :class:`RsBindingsNotAvailableInPhase01Error` (fail-loud —
            the picker never persists a runtime ``get_runtime`` would refuse).
        genesis_id: The chooser's 64-hex ``principal_genesis_id``.
        key_manager: The Genesis/device signing surface (ledger key manager).
        signing_key_id: The key id under which to sign (the ledger signing key).
        path: Config path (default resolution via
            :func:`resolve_runtime_choice_path`).
        now: Injectable timestamp for deterministic tests; defaults to
            ``datetime.now(tz=timezone.utc)``.

    Raises:
        ValueError: ``family`` unknown, or ``genesis_id`` malformed.
        RsBindingsNotAvailableInPhase01Error: rs-bindings chosen while the
            conformance flag is False.
    """
    if family not in KNOWN_FAMILIES:
        raise ValueError(
            f"family={family!r} not in {sorted(KNOWN_FAMILIES)} — the picker "
            f"writes one of the two known runtime families."
        )
    if family == "kailash-rs-bindings" and not feature_flags.RS_BINDINGS_ENABLED:
        raise RsBindingsNotAvailableInPhase01Error(
            "write_runtime_choice(family='kailash-rs-bindings') refused while "
            "envoy.runtime.feature_flags.RS_BINDINGS_ENABLED == False — the rs "
            "adapter is structurally present but not yet conformance-green "
            "(byte-identical slice S2b/S2c/S3a/S3b must pass on BOTH runtimes "
            "first). Persisting it now would record a choice get_runtime cannot "
            "honor. Pick 'kailash-py' until the flag flips."
        )
    _validate_genesis_id(genesis_id)

    chosen_at = _format_canonical_now(now)
    # Build the choice with an empty signature, then sign its signing_payload.
    unsigned = RuntimeChoice(
        runtime_family=family,
        chosen_at=chosen_at,
        chosen_by_genesis_id=genesis_id,
        signature_hex="",
    )
    signature_hex = key_manager.sign_with_key(
        signing_key_id, canonical_dumps(unsigned.signing_payload())
    )
    if not signature_hex:
        raise ValueError(
            f"key_manager.sign_with_key({signing_key_id!r}) returned an empty "
            f"signature — refusing to write an unsigned runtime choice."
        )
    choice = RuntimeChoice(
        runtime_family=family,
        chosen_at=chosen_at,
        chosen_by_genesis_id=genesis_id,
        signature_hex=signature_hex,
    )
    target = resolve_runtime_choice_path(path)
    _write_json_0600(target, choice.to_wire())
    logger.info(
        "runtime.picker.write",
        extra={
            "runtime_family": family,
            "chosen_by_genesis_id": genesis_id,
            "path": str(target),
        },
    )
    return choice


def read_runtime_choice(
    path: str | os.PathLike[str] | None = None,
) -> RuntimeChoice | None:
    """Read + parse the runtime-choice config WITHOUT verifying its signature.

    This is the hot-path read `selection.get_runtime` uses on every primitive
    call — signature verification (which needs the key manager + public key) is
    the CLI `envoy runtime show` / switch surface's job, not the per-call
    factory's. Returns ``None`` when the config is absent (picker never ran);
    raises :class:`RuntimeChoiceCorruptError` when the file exists but is
    malformed (loud, never a silent fallback).
    """
    target = resolve_runtime_choice_path(path)
    if not target.exists():
        return None
    try:
        raw = target.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeChoiceCorruptError(
            f"runtime-choice config at {target} could not be read/parsed: {exc}"
        ) from exc
    return RuntimeChoice.from_wire(data)


async def verify_runtime_choice(
    choice: RuntimeChoice,
    *,
    key_manager: _KeyManagerProtocol,
    expected_pubkey: str,
) -> None:
    """Verify a choice's signature against the expected Genesis/device pubkey.

    Raises :class:`RuntimeChoiceSignatureError` on mismatch (fail-closed). The
    CLI surfaces (`envoy runtime show`, `envoy runtime switch`) call this before
    acting on a choice so a tampered config is rejected, not honored.
    """
    ok = await key_manager.verify(
        canonical_dumps(choice.signing_payload()),
        choice.signature_hex,
        expected_pubkey,
    )
    if not ok:
        raise RuntimeChoiceSignatureError(
            f"runtime-choice signature for family={choice.runtime_family!r} "
            f"chosen_by={choice.chosen_by_genesis_id} does NOT verify against "
            f"the expected Genesis public key — the config was tampered after "
            f"signing. Refusing to honor it (fail-closed)."
        )


def _format_canonical_now(now: datetime | None) -> str:
    """Canonical microsecond-padded UTC timestamp string (the same form the
    ledger uses via `_format_timestamp`)."""
    from envoy.ledger.canonical import _format_timestamp  # noqa: PLC0415

    return _format_timestamp(now or datetime.now(tz=timezone.utc))


def _write_json_0600(path: Path, payload: dict[str, Any]) -> None:
    """Write `payload` as pretty JSON with 0o600 perms, creating the parent dir.

    Mirrors `envoy/boundary_conversation/init_runtime.py:_emit_trust_anchor`:
    create with restrictive perms BEFORE writing content so a world-readable
    window never opens, then re-chmod in case a permissive umask widened it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
    except BaseException:
        raise
    os.chmod(str(path), 0o600)


__all__ = [
    "ENV_RUNTIME_CHOICE_PATH",
    "KNOWN_FAMILIES",
    "RUNTIME_CHOICE_SCHEMA_VERSION",
    "RuntimeChoice",
    "RuntimeChoiceCorruptError",
    "RuntimeChoiceSignatureError",
    "presented_default_family",
    "read_runtime_choice",
    "resolve_runtime_choice_path",
    "verify_runtime_choice",
    "write_runtime_choice",
]
