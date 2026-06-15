# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.selection — `get_runtime()` factory.

Per shard 18 § 4.4 + § 5.1: `get_runtime()` is the SINGLE entry point every
Envoy primitive uses. Primitives never import adapter classes directly. This
is the Phase 02 mechanicality lock — the runtime substitution happens here
and nowhere else, because no primitive holds a hard reference to a specific
adapter class.

Phase 01 behavior:

- `get_runtime()` always returns `KailashPyRuntime` (the sole production
  adapter).
- Any caller that passes an explicit `family=` other than `"kailash-py"`
  while `RS_BINDINGS_ENABLED == False` gets the typed
  `RsBindingsNotAvailableInPhase01Error` — even before the adapter
  constructor runs, so the substitution boundary is loud.

Phase 02 entry:

- Reads first-run picker output per `specs/distribution.md` § First-run flow.
- Wraps the constructor with the runtime-attestation gate per
  `specs/runtime-abstraction.md` § Runtime attestation.
"""

from __future__ import annotations

from typing import Any

from envoy.runtime.adapters.kailash_py import KailashPyRuntime
from envoy.runtime.errors import RsBindingsNotAvailableInPhase01Error
from envoy.runtime.feature_flags import RS_BINDINGS_ENABLED
from envoy.runtime.protocol import KailashRuntime
from envoy.runtime.runtime_picker import read_runtime_choice


def get_runtime(family: str | None = None, **kwargs: Any) -> KailashRuntime:
    """Return a KailashRuntime-compatible adapter.

    Phase 01: `family` defaults to `"kailash-py"`. Any other value while
    `RS_BINDINGS_ENABLED == False` raises
    `RsBindingsNotAvailableInPhase01Error` — gated at the factory boundary so
    the Phase 02 substitution work has a single named site.

    Phase 02: when `family is None`, resolution reads the first-run picker's
    durable runtime-choice config (`envoy.runtime.runtime_picker`) instead of
    the hardcoded `"kailash-py"`. A malformed config raises loud
    (`RuntimeChoiceCorruptError`) rather than silently falling back; an absent
    config (picker never ran) resolves to `"kailash-py"`, the safe pre-picker
    production default. The rs-bindings flag gate below still applies, so a
    choice naming `kailash-rs-bindings` while the conformance flag is False
    raises `RsBindingsNotAvailableInPhase01Error` — defense in depth on top of
    the picker's own write-time refusal.

    `**kwargs` are forwarded to the adapter constructor (e.g.
    `device_signing_private_key_hex`, `envoy_ledger`, `trust_store`).
    """
    selected = family or _resolve_selected_family()
    if selected == "kailash-py":
        return KailashPyRuntime(**kwargs)
    if selected == "kailash-rs-bindings":
        if not RS_BINDINGS_ENABLED:
            raise RsBindingsNotAvailableInPhase01Error(
                f"get_runtime(family={selected!r}) refused while "
                "envoy.runtime.feature_flags.RS_BINDINGS_ENABLED == False. "
                "Phase 02 entry flips the flag in "
                "envoy/runtime/feature_flags.py and fills the "
                "KailashRsBindingsRuntime adapter method bodies; tracked at "
                "workspaces/phase-02-trust-plane/ (not yet authored)."
            )
        # When the flag is True, return the rs adapter. Phase 02 fills bodies.
        from envoy.runtime.adapters.kailash_rs_bindings import (  # noqa: PLC0415
            KailashRsBindingsRuntime,
        )

        return KailashRsBindingsRuntime(**kwargs)
    raise ValueError(
        f"get_runtime(family={selected!r}) — unknown family. "
        f"Phase 01 supports {{'kailash-py'}} only; Phase 02 adds "
        f"'kailash-rs-bindings'."
    )


def _resolve_selected_family() -> str:
    """Resolve the default runtime family from the first-run picker config.

    Reads the durable runtime-choice config (unsigned hot-path read — signature
    verification is the `envoy runtime show` / switch surface's job, not the
    per-call factory's). Returns the chosen family when the picker has run, else
    `"kailash-py"` (the safe pre-picker production default). A malformed config
    propagates `RuntimeChoiceCorruptError` (loud, never a silent fallback).
    """
    choice = read_runtime_choice()
    if choice is None:
        return "kailash-py"
    return choice.runtime_family


__all__ = ["get_runtime"]
