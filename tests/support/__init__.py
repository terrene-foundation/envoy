# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""tests.support — importable cross-shard test contracts (not a test module).

Houses shared invariant assertions that multiple shards reuse without
re-deriving them. Currently: the T-013 session-boundary reset invariant
(`tests.support.t013`), owned by WS-6 S5b and reused by S5o + S6c.
"""
