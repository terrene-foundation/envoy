# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.skill_ingest — typed error taxonomy for the SKILL.md ingest pipeline.

`specs/skill-ingest.md` § Error taxonomy. Every failure surface of the SKILL.md
parser, the ENVELOPE.md companion generator, the permission→PACT-dimension
translator, the conservative AST permission-inference walk, and the CO validator
raises ONE of these typed classes — never a bare ``ValueError`` and never a
silent default (`rules/zero-tolerance.md` Rule 3).

`OverPrivilegeWarning` is the lone *non-reject* surface: CO validator step 4
detects ``declared ⊋ inferred`` (the author declared MORE capability than the
code reaches) and surfaces a warning at the Grant Moment — the user may
downscope or accept; the install is NOT refused. It is a typed ``Warning``
subclass carried in the validator result, never raised.

`ForceInstallWaiverRequiredError` + the `force_install` flag are the spec's
waiver surface (`specs/skill-ingest.md` § ``force_install=True``): a score < 0.5
refuses with `COValidatorRefusedError` UNLESS the user passes ``force_install``
with an explicit acknowledgement payload — a bare ``force_install=True`` with no
waiver payload raises `ForceInstallWaiverRequiredError`.
"""

from __future__ import annotations


class SkillIngestError(Exception):
    """Base class for every SKILL.md-ingest failure surface.

    Catching this base catches every typed skill-ingest error; consumers SHOULD
    catch the specific subclass for actionable handling.
    """


class SkillManifestParseError(SkillIngestError):
    """SKILL.md fails schema validation.

    `specs/skill-ingest.md`: missing required fields (name/version/description),
    a malformed permissions array, or unparseable frontmatter. User action: the
    skill author fixes the manifest; the user retries the install.
    """


class EnvelopeCompanionMissingError(SkillIngestError):
    """A SKILL.md was processed without ENVELOPE.md generation completing.

    `specs/skill-ingest.md`: parser crash / IO failure left the companion
    un-generated. The install flow requires the companion to exist before the
    CO validator runs.
    """


class UnknownPermissionPatternError(SkillIngestError):
    """A declared permission pattern is absent from the permission→PACT registry.

    `specs/skill-ingest.md` § Permission → PACT dimension mapping: the registry
    `envoy-registry:permission-to-pact-dimension:v1` has no entry for the
    pattern. NOT a silent skip — a declared permission the registry cannot map
    is a hard refusal (fail-closed). Carries the offending `pattern`.
    """

    def __init__(self, message: str, *, pattern: str) -> None:
        super().__init__(message)
        self.pattern = pattern


class COValidatorRefusedError(SkillIngestError):
    """CO validator score < 0.5 AND ``force_install`` not honored.

    `specs/skill-ingest.md` § Score thresholds: < 0.5 fail. The AST walk proved
    a LITERAL undeclared-capability call (or a literal dynamic-dispatch reach),
    driving the score below 0.5. Carries the computed `score` and the structured
    `warnings`/`errors` the validator accumulated so the Grant Moment can render
    why the install was refused.
    """

    def __init__(
        self,
        message: str,
        *,
        score: float,
        errors: tuple[str, ...] = (),
        warnings: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.score = score
        self.errors = errors
        self.warnings = warnings


class PublisherSignatureInvalidError(SkillIngestError):
    """CO validator step 6: the publisher Ed25519 signature fails to verify.

    `specs/skill-ingest.md` § Error taxonomy: refuse install; surface possible
    publisher-key-rotation OR supply-chain tamper. Never auto-retry.

    Distinct from `envoy.registry.errors.PublisherSignatureInvalidError` (the
    Envelope-Library FV-steward verifier) — this is the SKILL.md publisher
    (ENVELOPE.md ``publisher.signature``) verification surface. Both reuse the
    same Ed25519 verify primitive; the taxonomy is per-domain.
    """


class SkillSourceHashMismatchError(SkillIngestError):
    """Fetched skill source bytes do not match the declared `skill_source_hash`.

    `specs/skill-ingest.md` § Error taxonomy: suspected mirror tamper or
    bit-rot. Refuse install; never auto-retry. Carries `declared` and `computed`
    hashes so the Grant Moment can surface the divergence.
    """

    def __init__(self, message: str, *, declared: str, computed: str) -> None:
        super().__init__(message)
        self.declared = declared
        self.computed = computed


class ForceInstallWaiverRequiredError(SkillIngestError):
    """``force_install=True`` attempted without an explicit acknowledgement payload.

    `specs/skill-ingest.md` § ``force_install=True``: the user MUST sign a waiver
    payload (visible Ledger flag + envelope flag) — a bare ``force_install=True``
    with no waiver payload is refused with this typed error rather than silently
    installing a sub-0.5 skill.
    """


class SkillCodeUnparseableError(SkillIngestError):
    """A SKILL.md inline code block cannot be parsed by the Python ``ast`` walk.

    Fail-closed (`rules/security.md`): unparseable code is treated
    conservatively — the inference walk cannot prove the declared permissions
    cover the (unanalyzable) code, so the validator surfaces this rather than
    silently passing un-analyzed code. The validator NEVER ``eval``s fixture
    code; this is raised purely from a static `ast.parse` failure.
    """


class OverPrivilegeWarning(Warning):
    """``declared ⊋ inferred`` — the author declared more than the code reaches.

    `specs/skill-ingest.md` § Error taxonomy: surfaced at the Grant Moment, NOT
    a reject (CO validator step 4). The user may downscope the manifest or accept
    the over-declaration. Carried as a structured warning string in the
    validator result; this class exists so the over-declaration surface is a
    distinct, greppable type rather than a bare string.

    Subclasses ``Warning`` (not ``Exception``) precisely because it is never
    raised — it documents an advisory finding.
    """

    def __init__(self, message: str, *, excess: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.excess = excess


__all__ = [
    "COValidatorRefusedError",
    "EnvelopeCompanionMissingError",
    "ForceInstallWaiverRequiredError",
    "OverPrivilegeWarning",
    "PublisherSignatureInvalidError",
    "SkillCodeUnparseableError",
    "SkillIngestError",
    "SkillManifestParseError",
    "SkillSourceHashMismatchError",
    "UnknownPermissionPatternError",
]
