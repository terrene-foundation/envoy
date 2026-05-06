"""Envelope-compiler typed errors.

Per `specs/envelope-model.md` § Error taxonomy: every error is Ledger-recorded
with `content_trust_level: system`; error messages MUST NOT echo raw envelope
content (PII / secret leakage defense).

Phase 01 ships the load-bearing subset:
- EnvelopeCompilationError (parent)
- EnvelopeValidationError (input validation)
- SchemaVersionMismatchError
- IntersectConflictError (R2-M-05 — propagate, never silently fall back)
- MonotonicTighteningError (parent-vs-child compile gate)
- TemplateResolutionError (template imports)

The full 24-error taxonomy from `specs/envelope-model.md` lands as discrete
subclasses as Wave 1+ consumers surface them. The hierarchy is the structural
defense — `except EnvelopeError` catches the whole class.
"""

from __future__ import annotations


class EnvelopeError(Exception):
    """Base class for every envelope-compiler error.

    All subclasses are Ledger-recorded with `content_trust_level: system`.
    """

    def __init__(self, message: str, *, envelope_id: str | None = None) -> None:
        super().__init__(message)
        self.envelope_id = envelope_id


class EnvelopeCompilationError(EnvelopeError):
    """Raised when the compile pipeline fails for any non-validation reason."""


class EnvelopeValidationError(EnvelopeError):
    """Raised when an `EnvelopeConfigInput` fails structural validation.

    Used by Boundary Conversation re-prompt logic per shard 4 § 5 integration
    point #1 — the caller catches this, surfaces the offending field in plain
    language, and re-prompts.
    """

    def __init__(
        self, message: str, *, field: str | None = None, envelope_id: str | None = None
    ) -> None:
        super().__init__(message, envelope_id=envelope_id)
        self.field = field


class SchemaVersionMismatchError(EnvelopeValidationError):
    """Input's `schema_version` does not match this compiler's pinned version."""


class IntersectConflictError(EnvelopeError):
    """Raised when intersect() cannot produce a non-degenerate envelope.

    Carry-forward R2-M-05 disposition (per
    `workspaces/phase-01-mvp/04-validate/round-4-implementation-comprehensive.md` § 4):
    this error MUST propagate to the caller. The compiler's contract is to
    raise on conflict, period — never silently widen one side, never substitute
    a partial result, never return a "best-effort" intersection. The caller
    (Grant Moment, Boundary Conversation) is responsible for surfacing the
    conflict to the user in plain language.
    """


class MonotonicTighteningError(EnvelopeError):
    """Raised when a child-envelope compile would widen a parent dimension.

    Wraps `kailash.trust.pact.envelopes.MonotonicTighteningError` so envoy
    callers catch the envoy-side hierarchy.
    """


class TemplateResolutionError(EnvelopeError):
    """Raised when a template reference cannot be resolved.

    Phase 01 surfaces this for local-only template paths that don't exist
    or fail signature validation. Foundation Library registry is Phase 02.
    """
