"""envoy-agent — Foundation-stewarded pure-Python pip-install agent.

Phase 01 MVP. Implements Terrene Foundation open standards (CARE / EATP / CO / PACT)
per ADR-0001 phase-migration table: pure-Python runtime (kailash) for Phase 01;
Rust binding (kailash-rs) for Phase 02.

Public facade re-exports land here as primitives ship (Wave 1 → Wave 5).
Per `rules/orphan-detection.md` Rule 6, every module-scope import in this file
appears in `__all__`.
"""

__version__ = "0.1.0"

from envoy.envelope.compiler import EnvelopeCompiler

__all__ = [
    "EnvelopeCompiler",
]
