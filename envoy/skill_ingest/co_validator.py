# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.skill_ingest.co_validator — the CO validator pipeline (steps 1-4, 6).

`specs/skill-ingest.md` § CO validator. Wires the SKILL.md parser, the
permission→PACT registry, the conservative AST inference walk, the asymmetric
declared-vs-inferred comparison, and the publisher-signature verifier into a
single install-time gate that returns a structured `COValidationResult` OR
raises a typed refusal.

Step ordering (`specs/skill-ingest.md`):

  1. SKILL.md schema valid           → `SkillManifestParseError`
  2. Permission patterns recognized   → `UnknownPermissionPatternError`
  3. Declared = inferred (AST walk)   → drives the score
  4. Over-privilege warning           → `OverPrivilegeWarning` in the result
  5. Adversarial-pattern detection    → S9b (classifier ensemble) — THIS shard
     emits a TYPED PENDING SURFACE at the step-5 slot, NOT a silent pass and NOT
     an implementation (`AdversarialCheckPending`).
  6. Publisher signature verifies     → `PublisherSignatureInvalidError`

Score routing (`specs/skill-ingest.md` § Score thresholds): ≥0.8 pass; 0.5–0.8
pass-with-warnings; <0.5 fail → `COValidatorRefusedError` UNLESS a valid
`force_install` waiver is provided. A bare `force_install=True` with no waiver
payload raises `ForceInstallWaiverRequiredError`.

The `skill_source_hash` integrity check (a fetched skill whose bytes do not
re-hash to the declared companion hash → `SkillSourceHashMismatchError`) runs
before step 6 when an expected hash is supplied.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from envoy.skill_ingest.comparison import compare_declared_inferred
from envoy.skill_ingest.envelope_md import (
    CoValidatorResult,
    EnvelopeCompanion,
    PublisherRef,
    compute_skill_source_hash,
    generate_envelope_companion,
)
from envoy.skill_ingest.errors import (
    COValidatorRefusedError,
    ForceInstallWaiverRequiredError,
    OverPrivilegeWarning,
    SkillSourceHashMismatchError,
)
from envoy.skill_ingest.inference import infer_permissions
from envoy.skill_ingest.permission_registry import resolve_permission
from envoy.skill_ingest.publisher_signature import verify_publisher_signature
from envoy.skill_ingest.skill_md import SkillManifest, parse_skill_md


class _VerifyKeyManager(Protocol):
    async def verify(self, payload: Any, signature: str, public_key: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class AdversarialCheckPending:
    """The CO validator step-5 TYPED PENDING SURFACE (S9b not yet shipped).

    `specs/skill-ingest.md` CO validator step 5 ("Adversarial-pattern detection,
    quarterly-retrained classifier ensemble") is a LATER shard (S9b). This shard
    MUST NOT silently pass step 5 and MUST NOT implement it. Instead the pipeline
    emits this typed marker in the result so a consumer sees a STRUCTURED
    "pending ensemble" surface — distinct from a clean step-5 pass.

    `pending` is always True for this surface; `reason` + `registry_id` name the
    S9b dependency so the Grant Moment can render "adversarial-pattern check
    pending ensemble" rather than implying step 5 ran.
    """

    pending: bool = True
    reason: str = (
        "adversarial-pattern check pending ensemble (CO validator step 5 — "
        "classifier ensemble ships in S9b)"
    )
    registry_id: str = "envoy-registry:adversarial-skill-patterns:v1"


@dataclass(frozen=True, slots=True)
class WaiverPayload:
    """The `force_install` acknowledgement payload.

    `specs/skill-ingest.md` § ``force_install=True``: the user MUST sign a waiver
    (visible Ledger flag + envelope flag + skill-inventory marker). A
    `force_install` request with no `WaiverPayload` raises
    `ForceInstallWaiverRequiredError`. `acknowledged_by` is the signing
    user/genesis id; `acknowledgement` is the explicit waiver text the user
    signed.
    """

    acknowledged_by: str
    acknowledgement: str


@dataclass(frozen=True, slots=True)
class COValidationResult:
    """The structured outcome of a CO validation that did NOT refuse.

    Carries the manifest, the computed `score`, `passed`/`clean` bands, the
    accumulated `warnings`/`errors`, the typed `over_privilege` finding (step 4),
    the step-5 `adversarial_pending` surface, the generated ENVELOPE.md
    `companion`, and the `force_install_used` flag (True only when a sub-0.5
    skill was force-installed via a valid waiver).
    """

    manifest: SkillManifest
    score: float
    passed: bool
    clean: bool
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    over_privilege: OverPrivilegeWarning | None
    adversarial_pending: AdversarialCheckPending
    companion: EnvelopeCompanion
    force_install_used: bool = False
    resolved_dimensions: tuple[str, ...] = field(default_factory=tuple)


async def validate_skill(
    skill_source: str,
    *,
    publisher: PublisherRef,
    pinned_publisher_pubkeys: Mapping[str, str],
    key_manager: _VerifyKeyManager,
    expected_skill_source_hash: str | None = None,
    force_install: bool = False,
    waiver: WaiverPayload | None = None,
) -> COValidationResult:
    """Run the CO validator (steps 1-4, 6 + typed step-5 pending surface).

    Args:
        skill_source: The raw SKILL.md source text.
        publisher: The ENVELOPE.md ``publisher`` block (genesis_id + signature).
        pinned_publisher_pubkeys: The client-pinned ``genesis_id → pubkey hex``
            map (the step-6 trust anchor).
        key_manager: The Ed25519 verify primitive (REUSED `InMemoryKeyManager`).
        expected_skill_source_hash: When supplied, the fetched source bytes are
            re-hashed and compared; a mismatch raises
            `SkillSourceHashMismatchError` (supply-chain / mirror-tamper guard).
        force_install: When True, a sub-0.5 score is waived IF `waiver` is also
            supplied; a bare True with no `waiver` raises
            `ForceInstallWaiverRequiredError`.
        waiver: The `force_install` acknowledgement payload.

    Returns:
        A `COValidationResult` when the validation passes (score ≥0.5) OR a
        sub-0.5 score is force-installed with a valid waiver.

    Raises:
        SkillManifestParseError: step 1 — malformed SKILL.md.
        UnknownPermissionPatternError: step 2 — a declared pattern's category is
            not in the registry.
        SkillCodeUnparseableError: step 3 — inline code is not parseable Python.
        SkillSourceHashMismatchError: the fetched source bytes do not match
            `expected_skill_source_hash`.
        PublisherSignatureInvalidError: step 6 — the publisher signature fails.
        COValidatorRefusedError: score < 0.5 AND no valid `force_install` waiver.
        ForceInstallWaiverRequiredError: `force_install=True` with no `waiver`.
    """
    # --- skill_source_hash integrity (mirror-tamper guard) ----------------
    computed_hash = compute_skill_source_hash(skill_source)
    if expected_skill_source_hash is not None and computed_hash != expected_skill_source_hash:
        raise SkillSourceHashMismatchError(
            f"fetched skill source re-hash {computed_hash!r} != declared "
            f"skill_source_hash {expected_skill_source_hash!r}; refuse install — "
            "suspected mirror tamper or bit-rot",
            declared=expected_skill_source_hash,
            computed=computed_hash,
        )

    # --- step 1: SKILL.md schema valid ------------------------------------
    manifest = parse_skill_md(skill_source)

    # --- step 2: permission patterns recognized (registry lookup) ---------
    # Resolve EVERY declared permission; an unknown category raises
    # UnknownPermissionPatternError here (fail-closed).
    resolved_dimensions: set[str] = set()
    declared_categories: set[str] = set()
    for pattern in manifest.declared_permissions:
        resolution = resolve_permission(pattern)
        declared_categories.add(resolution.category)
        resolved_dimensions.update(d.value for d in resolution.dimensions)

    # --- step 3: declared = inferred (conservative AST walk) --------------
    inferred = infer_permissions(manifest.joined_code)

    # --- step 4: over-privilege + asymmetric score routing ----------------
    comparison = compare_declared_inferred(declared_categories, inferred)

    # --- step 5: adversarial-pattern detection (TYPED PENDING — S9b) ------
    adversarial_pending = AdversarialCheckPending()

    # --- step 6: publisher signature verifies -----------------------------
    # Runs even on a sub-0.5 score so the refusal message can note whether the
    # publisher was authentic; a signature failure is a hard refusal regardless
    # of score.
    await verify_publisher_signature(
        computed_hash,
        publisher.genesis_id,
        publisher.signature,
        pinned_publisher_pubkeys,
        key_manager=key_manager,
    )

    co_result = CoValidatorResult(
        passed=comparison.passed,
        score=comparison.score,
        warnings=comparison.warnings,
        errors=comparison.errors,
    )
    companion = generate_envelope_companion(manifest, skill_source, publisher, co_result)

    # --- score-band routing -----------------------------------------------
    force_install_used = False
    if comparison.score < 0.5:
        # Sub-0.5 → refuse UNLESS a valid force_install waiver is present.
        if not force_install:
            raise COValidatorRefusedError(
                f"CO validator score {comparison.score} < 0.5 — refuse install; "
                "review the validator errors (AST-proven undeclared-capability "
                "reach) and opt in via force_install with a signed waiver if "
                "accepted",
                score=comparison.score,
                errors=comparison.errors,
                warnings=comparison.warnings,
            )
        if waiver is None:
            raise ForceInstallWaiverRequiredError(
                "force_install=True requires an explicit signed waiver payload "
                "(visible Ledger flag + envelope flag + skill-inventory marker); "
                "none was supplied — refusing the bare force_install"
            )
        force_install_used = True

    return COValidationResult(
        manifest=manifest,
        score=comparison.score,
        passed=comparison.passed,
        clean=comparison.clean,
        warnings=comparison.warnings,
        errors=comparison.errors,
        over_privilege=comparison.over_privilege,
        adversarial_pending=adversarial_pending,
        companion=companion,
        force_install_used=force_install_used,
        resolved_dimensions=tuple(sorted(resolved_dimensions)),
    )


__all__ = [
    "AdversarialCheckPending",
    "COValidationResult",
    "WaiverPayload",
    "validate_skill",
]
