# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.adapters — concrete KailashRuntime implementations.

Phase 01 ships:

- `KailashPyRuntime` — production adapter forwarding to upstream `kailash` and
  Envoy-side primitives where the upstream gap is filled (e.g. EnvoyLedger).
- `KailashRsBindingsRuntime` — structurally-present Phase-02 slot, gated by
  `envoy.runtime.feature_flags.RS_BINDINGS_ENABLED`. Construction raises
  `RsBindingsNotAvailableInPhase01Error` while the flag is False.

Per shard 18 § 3.3 + § 7 disposition 3: the Rust-bindings slot exists as a
structural file so Phase 02 substitution is one flag flip + method-fill, not a
new-package introduction + import-graph refactor.
"""

from __future__ import annotations

from envoy.runtime.adapters.kailash_py import KailashPyRuntime
from envoy.runtime.adapters.kailash_rs_bindings import KailashRsBindingsRuntime

__all__ = [
    "KailashPyRuntime",
    "KailashRsBindingsRuntime",
]
