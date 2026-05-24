"""Envelope-scope membership predicate.

Per shard 14 § 5.5 (`workspaces/phase-01-mvp/01-analysis/14-connection-vault-implementation.md`):
"the vault asks the envelope compiler 'does this session's envelope include
this credential's scope?' before returning the credential."

Phase 01 minimum: narrow set-membership on operational tool_allowlist +
communication channel_allowlist. Phase 02 promotion is the full
`kailash.trust.pact.envelopes.intersect_envelopes` semantics (deferred at
T-01-10 per envoy/envelope/compiler.py line 296-308).
"""

from __future__ import annotations

from typing import Union

from envoy.envelope.types import EnvelopeConfig, EnvelopeConfigInput, EnvelopeScopeRef

EnvelopeForScopeCheck = Union[EnvelopeConfig, EnvelopeConfigInput]


def envelope_contains_scope(envelope: EnvelopeForScopeCheck, scope: EnvelopeScopeRef) -> bool:
    """Return True iff `envelope` permits `scope` per Phase 01 semantics.

    Both conditions MUST hold:

    1. `scope.service_identifier` ∈ `envelope.operational.tool_allowlist`
    2. If `scope.channel` is set, `scope.channel` ∈
       `envelope.communication.channel_allowlist`

    A credential with `channel=None` is service-only (e.g. an LLM API key);
    a credential with `channel` set is service+channel (e.g. a Telegram bot
    token bound to the `"telegram"` channel).

    Fail-closed by construction: returns False on any miss; the caller
    (Connection Vault adapter) translates the False into the typed
    `EnvelopeScopeMismatchError` per `specs/connection-vault.md` § Error
    taxonomy.
    """
    if scope.service_identifier not in envelope.operational.tool_allowlist:
        return False
    if scope.channel is not None and scope.channel not in envelope.communication.channel_allowlist:
        return False
    return True
