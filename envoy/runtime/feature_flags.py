# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.runtime.feature_flags — Phase-gated runtime selection.

Per shard 18 § 3.3 + § 7 (frozen-spec ambiguity disposition 3): the
kailash_rs_bindings adapter MUST exist as a structurally-present module in
Phase 01, but instantiation MUST be gated behind a feature flag whose default
is False. The flag flip + per-method body fill is the entirety of the Phase 02
runtime-substitution work.

This module deliberately exposes ONE module-level constant and nothing else;
the constant is read-only at import time. Phase 02 entry flips
`RS_BINDINGS_ENABLED = True` in this file and re-runs the conformance corpus.
"""

from __future__ import annotations

# Phase 01: kailash_py is the sole production runtime. Setting True here
# without filling kailash_rs_bindings adapter method bodies will surface
# `Phase02SubstrateNotWiredError` from every Protocol method — by design.
RS_BINDINGS_ENABLED: bool = False

__all__ = ["RS_BINDINGS_ENABLED"]
