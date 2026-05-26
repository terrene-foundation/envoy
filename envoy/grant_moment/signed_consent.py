"""envoy.grant_moment.signed_consent — GrantMomentRequest + GrantMomentResult.

Implements the two wire shapes frozen in `specs/grant-moment.md` § Schema:

- ``GrantMomentRequest`` — what the runtime constructs at M0 and dispatches
  to channel adapters at M1. JCS+NFC-canonicalized + signed by the
  delegation_key over the entire request minus ``signature_by_delegator_hex``.

- ``GrantMomentResult`` — what the channel adapter returns at M3. JCS+NFC-
  canonicalized + signed by the delegation_key on Approve / Approve+author /
  Modify, or unsigned on Deny (the Deny path produces only a signed Ledger
  entry per spec § Schema "Deny — signed Ledger entry only").

The ``SignedConsentBuilder`` composes a ``_KeyManagerProtocol`` (the same
shape used by ``envoy.ledger.facade.EnvoyLedger``) so the runtime can sign
without owning private key material — kailash-py's ``InMemoryKeyManager``
satisfies the protocol for Phase 01; Trust Vault containers wrap it in
Phase 02.

Per spec § "Canonical JSON (§14.1)" and `envoy/envelope/canonical_bytes.py`:
canonical bytes pass through JCS RFC 8785 + Unicode NFC. Cross-runtime
byte-identity per BET-6.

This module is pure Python; ZERO dependencies on other envoy packages
besides ``envoy.envelope.canonical_bytes`` (JCS+NFC) and
``envoy.grant_moment.resolution`` (decision discriminators).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from envoy.envelope.canonical_bytes import canonical_bytes, content_hash
from envoy.grant_moment.resolution import (
    ApproveResolution,
    ApproveWithModificationResolution,
    DeclineResolution,
    ResolutionShape,
)

__all__ = [
    "ConsequencePreview",
    "GrantMomentRequest",
    "GrantMomentResult",
    "SignedConsentBuilder",
]

# Wire-form schema version per spec § Schema. Both Request and Result carry
# this identical string so verifiers can pin the layout they understand.
_SCHEMA_VERSION = "grant-moment/1.0"

# The "Deny — signed Ledger entry only" sentinel per spec § ``GrantMomentResult``.
# DeclineResolution paths set the result's signature_by_delegator_hex to this
# value so verifiers can distinguish "Deny (unsigned by delegation_key, by
# spec)" from "missing signature (programming error)".
_DENY_SIGNATURE_SENTINEL = "DENY_SIGNED_BY_LEDGER_ONLY"


@dataclass(frozen=True, slots=True)
class ConsequencePreview:
    """Per spec § ``GrantMomentRequest.consequence_preview`` — the rendered preview.

    Every field is shown to the user before the M3 sign step. Microdollars
    is integer (no floating-point rounding). Reversibility + data
    classification take a closed vocabulary the user UX maps to plain
    language per `rules/communication.md`.
    """

    budget_microdollars: int
    reversibility: str  # "reversible" | "reversible_with_cost" | "irreversible"
    recipient: str
    data_classification: str
    # "Public" | "Internal" | "Confidential" | "Restricted" | "HighlyConfidential"


@dataclass(frozen=True, slots=True)
class GrantMomentRequest:
    """The M0-constructed → M1-dispatched wire shape.

    Per spec § ``GrantMomentRequest``. ``signature_by_delegator_hex`` is the
    Ed25519 signature over the canonical bytes of this dataclass with the
    signature field itself excluded — the ``SignedConsentBuilder`` handles
    the exclusion when producing the canonical-input bytes.
    """

    request_id: str
    session_id: str
    principal_genesis_id: str
    envelope_id: str
    envelope_version: int
    envelope_hash: str
    intent_id: str
    nonce: str
    tool_name: str
    tool_args_canonical: dict[str, Any]
    tool_args_canonical_hash: str
    why_asking: str
    consequence_preview: ConsequencePreview
    novelty_class: str  # "novel" | "familiar_repeat" | "high_stakes"
    primary_only: bool
    timeout_seconds: int
    issued_at: str  # ISO-8601
    delegation_key_pubkey_hex: str
    signature_by_delegator_hex: str = ""
    schema_version: str = _SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class GrantMomentResult:
    """The M3 sign-or-decline wire shape.

    Per spec § ``GrantMomentResult``. ``signature_by_delegator_hex`` is the
    Ed25519 signature on Approve / Approve+author / Modify paths; on Deny
    it is set to ``_DENY_SIGNATURE_SENTINEL`` to mark the deliberately-
    unsigned wire form (spec mandates a signed Ledger entry for Deny, not a
    delegation_key signature on the Result itself).
    """

    result_id: str
    request_id: str
    decision: str  # "approve_once" | "approve_and_author" | "deny" | "modify"
    decided_at: str  # ISO-8601
    decided_on_channel_id: str
    decided_by_principal_genesis_id: str
    delegation_record_ref: str
    phase_a_record_ref: str
    signature_by_delegator_hex: str
    modify_payload: dict[str, Any] = field(default_factory=dict)
    author_payload: dict[str, Any] = field(default_factory=dict)
    co_signer_principal_genesis_id: str | None = None
    co_signature_hex: str | None = None
    schema_version: str = _SCHEMA_VERSION


class _KeyManagerProtocol(Protocol):
    """Subset of ``kailash.trust.key_manager.InMemoryKeyManager`` we depend on.

    Identical-shape to ``envoy.ledger.facade._KeyManagerProtocol`` — the
    Phase 01 keys live behind the same KeyManager surface in both ledger
    and grant_moment, so Trust Vault containers (Phase 02) wrap the same
    surface in both consumers without per-module adaptation.
    """

    def sign_with_key(self, key_id: str, payload: Any) -> str: ...

    def has_key(self, key_id: str) -> bool: ...


class SignedConsentBuilder:
    """Builds JCS+NFC-canonicalized + delegation_key-signed Request/Result pairs.

    Constructor takes a key_manager (kailash ``InMemoryKeyManager`` satisfies
    the protocol). ``build_signed_request`` populates an unsigned Request,
    canonicalizes it (excluding the signature field), signs the bytes via
    the key_manager, and returns the Request with the signature attached.

    ``build_signed_result`` performs the same flow for ``GrantMomentResult``
    on Approve / Approve+author / Modify; on Deny it produces an unsigned
    Result with the ``_DENY_SIGNATURE_SENTINEL`` marker per spec.

    Per spec § "Canonical JSON" — the canonical-input bytes the signature
    covers are JCS+NFC of the dataclass with the signature-carrying field
    set to the empty string (NOT removed — RFC 8785 requires every key
    present at serialization time so signers and verifiers agree byte-for-byte).
    """

    def __init__(self, *, key_manager: _KeyManagerProtocol) -> None:
        self._key_manager = key_manager

    # ------------------------------------------------------------------
    # Request
    # ------------------------------------------------------------------

    def build_signed_request(
        self,
        *,
        request: GrantMomentRequest,
        delegation_key_id: str,
    ) -> GrantMomentRequest:
        """Sign ``request`` via the named delegation key; return signed copy.

        The input ``request`` may carry any value (commonly the empty default)
        in ``signature_by_delegator_hex``; that field is forced to ``""`` for
        canonicalization so signer and verifier produce identical bytes,
        then the signature replaces it in the returned copy.
        """
        if not self._key_manager.has_key(delegation_key_id):
            raise ValueError(f"delegation_key_id {delegation_key_id!r} not in key_manager")
        canonical_input = self._request_canonical_input(request)
        signature_hex = self._key_manager.sign_with_key(delegation_key_id, canonical_input)
        # Replace the signature field; frozen dataclass requires a fresh instance.
        return GrantMomentRequest(
            request_id=request.request_id,
            session_id=request.session_id,
            principal_genesis_id=request.principal_genesis_id,
            envelope_id=request.envelope_id,
            envelope_version=request.envelope_version,
            envelope_hash=request.envelope_hash,
            intent_id=request.intent_id,
            nonce=request.nonce,
            tool_name=request.tool_name,
            tool_args_canonical=request.tool_args_canonical,
            tool_args_canonical_hash=request.tool_args_canonical_hash,
            why_asking=request.why_asking,
            consequence_preview=request.consequence_preview,
            novelty_class=request.novelty_class,
            primary_only=request.primary_only,
            timeout_seconds=request.timeout_seconds,
            issued_at=request.issued_at,
            delegation_key_pubkey_hex=request.delegation_key_pubkey_hex,
            signature_by_delegator_hex=signature_hex,
            schema_version=request.schema_version,
        )

    @staticmethod
    def _request_canonical_input(request: GrantMomentRequest) -> bytes:
        """Produce JCS+NFC canonical bytes with the signature field empty."""
        payload = asdict(request)
        payload["signature_by_delegator_hex"] = ""
        return canonical_bytes(payload)

    @staticmethod
    def request_canonical_hash(request: GrantMomentRequest) -> str:
        """SHA-256 hex digest of the canonical bytes (signature field empty).

        Exposed for verifiers + ledger entries; mirrors
        ``envoy.envelope.canonical_bytes.content_hash`` shape.
        """
        return content_hash(SignedConsentBuilder._request_canonical_input(request))

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------

    def build_signed_result(
        self,
        *,
        request_id: str,
        result_id: str,
        decided_at: str,
        decided_on_channel_id: str,
        delegation_record_ref: str,
        phase_a_record_ref: str,
        resolution: ResolutionShape,
        delegation_key_id: str | None = None,
    ) -> GrantMomentResult:
        """Build the Result; sign on Approve / Modify; mark Deny per spec.

        ``delegation_key_id`` is required for Approve / Approve+author / Modify;
        ignored for Decline (the Deny path is signed only via the Ledger).
        """
        decision = resolution.to_decision()
        # Build the unsigned shape; signature field set below per decision.
        unsigned = GrantMomentResult(
            result_id=result_id,
            request_id=request_id,
            decision=decision,
            decided_at=decided_at,
            decided_on_channel_id=decided_on_channel_id,
            decided_by_principal_genesis_id=resolution.decided_by_principal_genesis_id,
            delegation_record_ref=delegation_record_ref,
            phase_a_record_ref=phase_a_record_ref,
            signature_by_delegator_hex="",
            modify_payload=(
                resolution.modify_payload
                if isinstance(resolution, ApproveWithModificationResolution)
                else {}
            ),
            author_payload=(
                resolution.author_payload
                if isinstance(resolution, ApproveResolution)
                and resolution.author_payload is not None
                else {}
            ),
            co_signer_principal_genesis_id=resolution.co_signer_principal_genesis_id,
            co_signature_hex=None,
        )

        if isinstance(resolution, DeclineResolution):
            return GrantMomentResult(
                result_id=unsigned.result_id,
                request_id=unsigned.request_id,
                decision=unsigned.decision,
                decided_at=unsigned.decided_at,
                decided_on_channel_id=unsigned.decided_on_channel_id,
                decided_by_principal_genesis_id=unsigned.decided_by_principal_genesis_id,
                delegation_record_ref=unsigned.delegation_record_ref,
                phase_a_record_ref=unsigned.phase_a_record_ref,
                signature_by_delegator_hex=_DENY_SIGNATURE_SENTINEL,
                modify_payload=unsigned.modify_payload,
                author_payload=unsigned.author_payload,
                co_signer_principal_genesis_id=unsigned.co_signer_principal_genesis_id,
                co_signature_hex=None,
                schema_version=unsigned.schema_version,
            )

        # Approve / Approve+author / Modify — sign via delegation_key.
        if delegation_key_id is None:
            raise ValueError(
                "delegation_key_id is required for Approve / Modify decisions "
                f"(got resolution decision={decision!r})"
            )
        if not self._key_manager.has_key(delegation_key_id):
            raise ValueError(f"delegation_key_id {delegation_key_id!r} not in key_manager")
        canonical_input = self._result_canonical_input(unsigned)
        signature_hex = self._key_manager.sign_with_key(delegation_key_id, canonical_input)
        return GrantMomentResult(
            result_id=unsigned.result_id,
            request_id=unsigned.request_id,
            decision=unsigned.decision,
            decided_at=unsigned.decided_at,
            decided_on_channel_id=unsigned.decided_on_channel_id,
            decided_by_principal_genesis_id=unsigned.decided_by_principal_genesis_id,
            delegation_record_ref=unsigned.delegation_record_ref,
            phase_a_record_ref=unsigned.phase_a_record_ref,
            signature_by_delegator_hex=signature_hex,
            modify_payload=unsigned.modify_payload,
            author_payload=unsigned.author_payload,
            co_signer_principal_genesis_id=unsigned.co_signer_principal_genesis_id,
            co_signature_hex=None,
            schema_version=unsigned.schema_version,
        )

    @staticmethod
    def _result_canonical_input(result: GrantMomentResult) -> bytes:
        """Produce JCS+NFC canonical bytes with the signature fields empty."""
        payload = asdict(result)
        payload["signature_by_delegator_hex"] = ""
        # co_signature_hex is independently set for Phase 03 dual-signed; the
        # primary signer's bytes treat it as null (per spec § "null when single").
        payload["co_signature_hex"] = None
        return canonical_bytes(payload)

    @staticmethod
    def result_canonical_hash(result: GrantMomentResult) -> str:
        """SHA-256 hex digest of the canonical bytes (signature fields empty)."""
        return content_hash(SignedConsentBuilder._result_canonical_input(result))
