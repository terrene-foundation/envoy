"""envoy.envelope — envelope compiler + canonical-bytes pipeline.

Implements `specs/envelope-model.md` § Schema + § Algorithms § "Canonical JSON".
Per shard 4 (`workspaces/phase-01-mvp/01-analysis/04-envelope-compiler-implementation.md`),
this module is the integration boundary between Boundary Conversation output
(`EnvelopeConfigInput`) and the rest of the system (`EnvelopeConfig` with
canonical bytes + content hash).

Public facade per `rules/orphan-detection.md` Rule 6.
"""

from envoy.envelope.canonical_bytes import canonical_bytes, content_hash
from envoy.envelope.compiler import EnvelopeCompiler
from envoy.envelope.errors import (
    EnvelopeCompilationError,
    EnvelopeError,
    EnvelopeValidationError,
    IntersectConflictError,
    MonotonicTighteningError,
    SchemaVersionMismatchError,
    TemplateResolutionError,
)
from envoy.envelope.template_resolver import (
    EnvelopeTemplate,
    EnvelopeTemplateResolver,
    LocalTemplateResolver,
    TemplateRef,
)
from envoy.envelope.types import (
    AlgorithmIdentifier,
    AuthoredConstraint,
    CommunicationDimension,
    CompositionRule,
    CrossDomainRule,
    DataAccessDimension,
    EnvelopeConfig,
    EnvelopeConfigInput,
    EnvelopeMetadata,
    FinancialDimension,
    ImportedConstraint,
    OperationalDimension,
    SemanticChecks,
    TemporalDimension,
)

__all__ = [
    # Compiler facade
    "EnvelopeCompiler",
    # Canonical bytes pipeline
    "canonical_bytes",
    "content_hash",
    # Errors (re-exported per package skeleton § 2.2 typed-error import contract)
    "EnvelopeError",
    "EnvelopeCompilationError",
    "EnvelopeValidationError",
    "IntersectConflictError",
    "MonotonicTighteningError",
    "SchemaVersionMismatchError",
    "TemplateResolutionError",
    # Template resolver
    "EnvelopeTemplate",
    "EnvelopeTemplateResolver",
    "LocalTemplateResolver",
    "TemplateRef",
    # Types
    "AlgorithmIdentifier",
    "AuthoredConstraint",
    "CommunicationDimension",
    "CompositionRule",
    "CrossDomainRule",
    "DataAccessDimension",
    "EnvelopeConfig",
    "EnvelopeConfigInput",
    "EnvelopeMetadata",
    "FinancialDimension",
    "ImportedConstraint",
    "OperationalDimension",
    "SemanticChecks",
    "TemporalDimension",
]
