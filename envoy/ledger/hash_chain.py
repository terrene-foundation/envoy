"""EntryEnvelope + HashChainBuilder — the Ledger's hash-chain shape.

Per `specs/ledger.md` § Entry envelope schema (lines 14-34) — every entry
shares a common 14-field envelope; the per-type variation lives entirely
inside `content: dict`. The envelope is signed in its entirety; the
`entry_id` is `sha256(canonical_dumps(envelope_dict_without_signature))`
and the `signature_hex` is `Ed25519(signing_key, entry_id)`.

Phase 01 narrow scope (T-01-17): the foundation lands EntryEnvelope as a
frozen dataclass + HashChainBuilder.build() as a pure function. T-01-18
EnvoyLedger.append() wraps build() inside `df.transaction()` to wire
audit_store.append + head.update + format_record_id_for_event filter.

Per `rules/trust-plane-security.md` MUST NOT Rule 4 (frozen constraint
dataclasses) the EntryEnvelope is `@dataclass(frozen=True)` — once minted,
the chain entry cannot be silently re-numbered or content-mutated.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

from envoy.ledger.canonical import canonical_dumps
from envoy.ledger.lamport import LamportClock


@dataclass(frozen=True, slots=True)
class EntryEnvelope:
    """Common envelope shared by every Ledger entry type.

    Per specs/ledger.md § Entry envelope schema:

        entry_id        sha256:<content_hash>
        parent_hash     sha256:<prev_entry_id>
        sequence        int (monotonic non-decreasing)
        lamport_clock   {lamport_time, device_id, local_seq}
        timestamp       ISO 8601 microsecond-padded UTC (#731)
        type            EntryType (string-typed, see specs/ledger.md table)
        intent_id       sha256:<phase_a_hash> | None
        content         {... type-specific ...}
        content_trust_level  user-authored | tool-output | channel-message
                             | derived-external | heartbeat | system
                             | sub-agent | llm-authored
        description_content_hash         sha256:<...>
        description_content_hash_algorithm  "sha256" (Phase 01 fixed)
        signed_by       device_key | genesis_key (string identifier)
        signature_hex   ed25519 signature of canonical_dumps(envelope_without_signature)
        algorithm_identifier  {sig, hash, shamir} 3-key spec form per
                              specs/trust-lineage.md L24 + R2-H-01 wire-form
                              translator (T-01-15)
        schema_version  "ledger-entry/1.0" (Phase 01 fixed)

    Per shard 6 § 4 (line 248-256): the algorithm_identifier 3-key form is
    inherited transitively from the Trust Store adapter — the Ledger does
    NOT translate it locally; entries arriving at the Ledger already carry
    the 3-key form per T-01-15's single-bottleneck enforcement.
    """

    entry_id: str
    parent_hash: str
    sequence: int
    lamport_clock: LamportClock
    timestamp: str
    type: str
    intent_id: str | None
    content: dict[str, Any]
    content_trust_level: str
    description_content_hash: str
    description_content_hash_algorithm: str
    signed_by: str
    signature_hex: str
    algorithm_identifier: dict[str, str]
    schema_version: str

    def __post_init__(self) -> None:
        # Defensive shape checks at construction. Frozen + slots prevents
        # post-construction mutation; these checks ensure invalid envelopes
        # cannot land at all.
        if not self.entry_id.startswith("sha256:"):
            raise ValueError(f"entry_id must be 'sha256:<hex>' (got {self.entry_id!r})")
        if not self.parent_hash.startswith("sha256:"):
            raise ValueError(f"parent_hash must be 'sha256:<hex>' (got {self.parent_hash!r})")
        if not isinstance(self.sequence, int) or self.sequence < 0:
            raise ValueError(f"sequence must be non-negative int (got {self.sequence!r})")
        if self.description_content_hash_algorithm != "sha256":
            raise ValueError(
                "Phase 01 description_content_hash_algorithm pinned to 'sha256' "
                f"(got {self.description_content_hash_algorithm!r})"
            )
        if self.schema_version != "ledger-entry/1.0":
            raise ValueError(
                "Phase 01 schema_version pinned to 'ledger-entry/1.0' "
                f"(got {self.schema_version!r})"
            )
        # 3-key algorithm_identifier per T-01-15 R2-H-01 wire form
        expected_keys = {"sig", "hash", "shamir"}
        if set(self.algorithm_identifier.keys()) != expected_keys:
            raise ValueError(
                f"algorithm_identifier MUST be the 3-key {{sig, hash, shamir}} "
                f"wire form (got keys {sorted(self.algorithm_identifier.keys())}); "
                "see specs/trust-lineage.md L24 + T-01-15 wire-form translator"
            )

    def to_dict(self) -> dict[str, Any]:
        """Wire shape per specs/ledger.md § Entry envelope schema."""
        d = asdict(self)
        d["lamport_clock"] = self.lamport_clock.to_dict()
        return d


class HashChainBuilder:
    """Pure-function builder that mints an EntryEnvelope from inputs.

    Phase 01 narrow scope (T-01-17): the builder produces the envelope's
    unsigned bytes (the input to the Ed25519 signer) AND the entry_id
    (the SHA-256 of those bytes). The actual signing — calling
    `kailash.trust.signing.crypto.Ed25519Signer.sign(...)` — lives in
    T-01-18 `EnvoyLedger.append()` so the signing step can run inside a
    `df.transaction()` boundary alongside `audit_store.append` and
    `head.update`.

    Pure: deterministic; no I/O; no clock reads. Caller threads
    `prev_entry_id` from the previous head and `lamport` from the runtime
    clock.

    Per shard 6 § 4 line 259-262 contract.
    """

    def build_unsigned(
        self,
        *,
        prev_entry_id: str,
        sequence: int,
        lamport: LamportClock,
        timestamp: str,
        type_: str,
        content: dict[str, Any],
        intent_id: str | None,
        content_trust_level: str,
        description_content_hash: str,
        signed_by: str,
        algorithm_identifier: dict[str, str],
    ) -> tuple[bytes, str]:
        """Compute the unsigned canonical-bytes vector AND derived entry_id.

        Returns `(canonical_bytes, entry_id)`. The caller signs
        `canonical_bytes` with the runtime device key OR the Genesis key
        per the `signed_by` field's declared semantics, then constructs
        the final EntryEnvelope via `seal(...)`.

        The unsigned envelope dict carries every envelope field EXCEPT
        `signature_hex` AND `entry_id` itself; including the signature in
        the hash input would create a chicken-and-egg dependency. The hash
        input is the canonical-JSON of {parent_hash, sequence, lamport,
        timestamp, type, intent_id, content, content_trust_level,
        description_content_hash, description_content_hash_algorithm,
        signed_by, algorithm_identifier, schema_version}.
        """
        unsigned = {
            "parent_hash": prev_entry_id,
            "sequence": sequence,
            "lamport_clock": lamport.to_dict(),
            "timestamp": timestamp,
            "type": type_,
            "intent_id": intent_id,
            "content": content,
            "content_trust_level": content_trust_level,
            "description_content_hash": description_content_hash,
            "description_content_hash_algorithm": "sha256",
            "signed_by": signed_by,
            "algorithm_identifier": algorithm_identifier,
            "schema_version": "ledger-entry/1.0",
        }
        canonical_bytes = canonical_dumps(unsigned)
        entry_id = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
        return canonical_bytes, entry_id

    def seal(
        self,
        *,
        entry_id: str,
        signature_hex: str,
        prev_entry_id: str,
        sequence: int,
        lamport: LamportClock,
        timestamp: str,
        type_: str,
        content: dict[str, Any],
        intent_id: str | None,
        content_trust_level: str,
        description_content_hash: str,
        signed_by: str,
        algorithm_identifier: dict[str, str],
    ) -> EntryEnvelope:
        """Assemble the final EntryEnvelope after the caller has signed.

        Caller-side flow:
            canonical_bytes, entry_id = builder.build_unsigned(...)
            signature_hex = signer.sign(canonical_bytes)
            envelope = builder.seal(entry_id=entry_id, signature_hex=signature_hex, ...)
        """
        return EntryEnvelope(
            entry_id=entry_id,
            parent_hash=prev_entry_id,
            sequence=sequence,
            lamport_clock=lamport,
            timestamp=timestamp,
            type=type_,
            intent_id=intent_id,
            content=content,
            content_trust_level=content_trust_level,
            description_content_hash=description_content_hash,
            description_content_hash_algorithm="sha256",
            signed_by=signed_by,
            signature_hex=signature_hex,
            algorithm_identifier=algorithm_identifier,
            schema_version="ledger-entry/1.0",
        )


__all__ = ["EntryEnvelope", "HashChainBuilder"]
