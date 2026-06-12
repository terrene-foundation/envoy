# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""envoy.boundary_conversation.init_runtime — the ``envoy init`` bootstrap (S4i).

The store-only half of ``envoy init``: it drives the Boundary Conversation
S0→S10 ritual to completion (producing the signed Genesis Record + the
GENESIS_BARE→PSEUDO posture ratchet) and then lands TWO durable, write-once
artifacts so a FRESH process can read the session genesis back:

1. **Durable session genesis** — a ``session-state/1.0`` SessionObservedState
   blob (per `specs/session-state.md` § Schema) written to the S4s
   ``SessionRouter`` store under a deterministic genesis key
   (``genesis:<principal_id>``). This is the cross-process "the same Envoy
   instance set up during the Boundary Conversation" anchor: a fresh process
   opening the same vault re-opens the SAME store and reads the SAME genesis.

2. **trust-anchor.json** — the out-of-band verification anchor per
   `specs/independent-verifier.md` § "Trust anchor file format"
   (``envoy-trust-anchor/1.0``). Emitted ALONGSIDE the Shamir 3-of-5 paper
   shard ritual so the user stores it in the same cold-storage location as
   their paper shards. Carries ONLY public verification material (the genesis
   record hash + the genesis verification public key in hex) — NEVER private
   key bytes (`rules/security.md`). 0o600 on the emitted file.

Scope boundary (S4i — STORE ONLY): this shard does NOT touch the grant
rendezvous (`envoy.grant_moment.runtime`) and does NOT depend on S4r. It
consumes the S4s store the same way `envoy.daily_digest.bootstrap` consumes
the durable ledger — re-opening a durable projection per process.

Write-once idempotency: re-running ``init`` on an initialized vault is detected
by a single read of the genesis key. If a genesis blob is already present the
runtime raises the typed ``VaultAlreadyInitializedError`` carrying the existing
genesis — it NEVER overwrites the durable genesis (`rules/zero-tolerance.md`
Rule 3; a silent overwrite of the session-genesis anchor would orphan every
trust-anchor.json the user already cold-stored).

Per `rules/facade-manager-detection.md` Rule 3 every collaborator is injected
explicitly; per `rules/agent-reasoning.md` the BC runtime (not this bootstrap)
owns the LLM-first per-state extraction — this module only orchestrates the
ritual + the durable writes.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from envoy.boundary_conversation.errors import VaultAlreadyInitializedError
from envoy.boundary_conversation.runtime import (
    BoundaryConversationRuntime,
    ConversationOutcome,
)

__all__ = [
    "BoundaryConversationInitRuntime",
    "InitResult",
    "TRUST_ANCHOR_SCHEMA_VERSION",
    "SESSION_STATE_SCHEMA_VERSION",
    "genesis_session_key",
    "build_genesis_session_state",
    "build_trust_anchor",
]

logger = logging.getLogger(__name__)

# Schema-version pins per the owning specs.
TRUST_ANCHOR_SCHEMA_VERSION = "envoy-trust-anchor/1.0"  # specs/independent-verifier.md
SESSION_STATE_SCHEMA_VERSION = "session-state/1.0"  # specs/session-state.md

# The genesis SessionObservedState lives under a deterministic, principal-scoped
# key in the S4s store so a FRESH process reads it back with one lookup, and so
# the write-once idempotency check is a single keyed read. The prefix keeps the
# genesis blob in a namespace distinct from per-session snapshots (uuid-v7 ids,
# which never start with "genesis:").
_GENESIS_KEY_PREFIX = "genesis:"

# Phase-01 install posture: the Boundary Conversation ratchets GENESIS_BARE →
# PSEUDO at S9 (per envoy.boundary_conversation.runtime § S9 + specs/posture-ladder.md).
_POSTURE_AT_GENESIS = "PSEUDO"


def genesis_session_key(principal_id: str) -> str:
    """The deterministic S4s store key the durable session genesis lands under.

    Principal-scoped so the genesis is read-back-able by a fresh process with a
    single ``load_observed_state(genesis_session_key(principal_id))`` call, and
    so the write-once idempotency check is a single keyed read (per-principal,
    no cross-principal bleed — `rules/tenant-isolation.md` Rule 1).
    """
    if not principal_id:
        raise ValueError("principal_id is required for genesis_session_key")
    return f"{_GENESIS_KEY_PREFIX}{principal_id}"


def _now_iso() -> str:
    """ISO-8601 UTC timestamp, ALWAYS microsecond-padded (6 digits).

    `datetime.isoformat()` DROPS the fractional-seconds component when the
    microseconds happen to be 0, yielding e.g. `2026-06-11T09:53:00+00:00`
    instead of `2026-06-11T09:53:00.000000+00:00`. `specs/independent-verifier.md`
    mandates `anchor_minted_at` be `<iso8601 microsecond-padded>` (ENVOY-P2-W2G-010),
    and the durable session-state timestamps share this helper, so
    `timespec="microseconds"` pins the 6-digit fraction unconditionally — the
    output is stable-width regardless of the wall-clock's sub-second value.
    """
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def _uuid7_like() -> str:
    """Return a time-ordered uuid-v7-shaped session id (string).

    Python 3.13 has no ``uuid.uuid7``; this matches the sortable shape used by
    ``envoy.budget.types.new_reservation_id`` — a 48-bit ms timestamp prefix +
    80 random bits, rendered in the canonical 8-4-4-4-12 hex grouping so the id
    reads as a UUID. Only uniqueness + sortability are load-bearing.
    """
    ms = int(time.time() * 1000)
    rand = os.urandom(10).hex()  # 20 hex chars
    raw = f"{ms:012x}{rand}"  # 32 hex chars total
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


def build_genesis_session_state(
    *,
    session_id: str,
    principal_genesis_id: str,
    envelope_version_at_session_start: int,
    posture_at_session_start: str = _POSTURE_AT_GENESIS,
    started_at: str | None = None,
) -> dict[str, Any]:
    """Construct the genesis ``session-state/1.0`` SessionObservedState blob.

    Per `specs/session-state.md` § Schema. A genesis session is the very first
    session a principal ever has — it carries no tool calls yet, no reasoning
    commits, no pending orphans, and no pre-authorized patterns; those fields
    are present-but-empty so the fresh-process read-back sees the canonical
    schema shape (S5o fills them at runtime). ``principal_genesis_id`` is the
    sha256 hash of the trust chain (the same value the trust-anchor pins), so a
    later session re-anchors to the genesis it was born from.
    """
    now = started_at or _now_iso()
    return {
        "schema_version": SESSION_STATE_SCHEMA_VERSION,
        "session_id": session_id,
        "principal_genesis_id": principal_genesis_id,
        "started_at": now,
        "last_activity_at": now,
        "tool_calls_made": {},
        "goal_reconfirmation": {
            "last_reconfirmed_at": now,
            "tool_calls_since_reconfirm": 0,
            "threshold": 0,
        },
        "reasoning_commits": [],
        "pending_phase_a_orphans": [],
        "pre_authorized_patterns": [],
        "envelope_version_at_session_start": int(envelope_version_at_session_start),
        "posture_at_session_start": posture_at_session_start,
    }


def build_trust_anchor(
    *,
    principal_genesis_id: str,
    principal_genesis_pubkey_hex: str,
    anchor_minted_at: str | None = None,
) -> dict[str, Any]:
    """Construct the ``envoy-trust-anchor/1.0`` trust-anchor payload.

    Per `specs/independent-verifier.md` § "Trust anchor file format". Carries
    ONLY public verification material — the genesis record hash
    (``principal_genesis_id``) and the genesis verification PUBLIC key
    (``principal_genesis_pubkey_hex``). NEVER any private key bytes
    (`rules/security.md` — no secrets in artifacts).

    Phase-01 ships option C with channel #1 (self-derived at install): the
    ``device_attestation_chain`` is empty at install (Phase 01 single-device;
    the genesis key IS the device key), and the verifier resolves the
    ``genesis_key`` directly via ``principal_genesis_pubkey_hex`` per the spec's
    trust-anchor key-resolution algorithm.
    """
    if not principal_genesis_id:
        raise ValueError("principal_genesis_id is required for the trust anchor")
    if not principal_genesis_pubkey_hex:
        raise ValueError("principal_genesis_pubkey_hex is required for the trust anchor")
    # Reject anything that looks like base64/PEM/raw key MATERIAL leaking in —
    # the anchor pubkey field MUST be hex (the verifier decodes it as hex per
    # specs/independent-verifier.md). A non-hex value is a programming error
    # (e.g. forwarding the base64 form straight through) and is caught loud.
    try:
        bytes.fromhex(principal_genesis_pubkey_hex)
    except ValueError as exc:
        raise ValueError(
            "principal_genesis_pubkey_hex must be hex-encoded ed25519 public-key "
            f"bytes (got a non-hex value): {exc}"
        ) from exc
    return {
        "schema_version": TRUST_ANCHOR_SCHEMA_VERSION,
        "principal_genesis_id": principal_genesis_id,
        "principal_genesis_pubkey_hex": principal_genesis_pubkey_hex,
        "device_attestation_chain": [],
        "anchor_minted_at": anchor_minted_at or _now_iso(),
    }


def _bc_gate_error(outcome: ConversationOutcome, context: str) -> Exception:
    """The outcome's typed gate error, or a loud RuntimeError when absent.

    ``ConversationOutcome.error`` is ``Exception | None``; an ERROR outcome
    always carries one in practice, but the type system cannot prove it —
    raising ``None`` would mask the gate failure with a TypeError.
    """
    if outcome.error is None:
        return RuntimeError(f"BC outcome ERROR at {context} carried no error object")
    return outcome.error


@dataclass(frozen=True, slots=True)
class InitResult:
    """The outcome of one ``envoy init`` bootstrap.

    ``envelope_id`` is the parseable EnvelopeConfig id the S9 sign step
    produced; ``genesis_session_id`` is the uuid-v7 session id of the durable
    genesis blob; ``genesis_store_key`` is the deterministic S4s key it landed
    under (so a fresh process reads it back); ``trust_anchor_path`` is the
    emitted ``trust-anchor.json`` file; ``principal_genesis_id`` is the sha256
    chain hash both artifacts pin.
    """

    principal_id: str
    envelope_id: str
    genesis_session_id: str
    genesis_store_key: str
    trust_anchor_path: Path
    principal_genesis_id: str


class BoundaryConversationInitRuntime:
    """Orchestrates ``envoy init``: drive the BC ritual, then land the durable
    genesis + trust-anchor.

    Construct synchronously (no I/O). The collaborators are injected:

    - ``bc_runtime`` — a fully-wired ``BoundaryConversationRuntime`` (the LLM
      extraction surface; this module never reasons about user content).
    - ``session_router`` — an OPENED S4s ``SessionRouter`` (the durable store
      the genesis lands in; caller owns its lifecycle).
    - ``trust_store`` — the ``TrustStoreAdapter`` (read the seeded Genesis chain
      back to derive the trust-anchor's public material).
    - ``trust_anchor_dir`` — where ``trust-anchor.json`` is emitted (the user's
      out-of-band Shamir-shard location in production).

    ``run_first_time_bootstrap`` is the single entry point a one-shot ``envoy
    init`` process calls. ``drive_ritual`` (the reply-pump) is overridable for
    tests that supply scripted answers without an Ollama daemon.
    """

    def __init__(
        self,
        *,
        bc_runtime: BoundaryConversationRuntime,
        session_router: Any,
        trust_store: Any,
        trust_anchor_dir: Path | str,
    ) -> None:
        self._bc = bc_runtime
        self._router = session_router
        self._trust_store = trust_store
        self._trust_anchor_dir = Path(trust_anchor_dir)

    async def run_first_time_bootstrap(
        self,
        *,
        principal_id: str,
        replies: dict[str, str],
    ) -> InitResult:
        """Drive the BC ritual to S10, then land the durable genesis + anchor.

        Write-once: if a durable genesis already exists for ``principal_id``,
        raises ``VaultAlreadyInitializedError`` BEFORE driving the ritual — so a
        re-run on an initialized vault never re-runs the Shamir ceremony and
        never overwrites the genesis (the existing genesis bytes are unchanged).

        ``replies`` maps each S1..S9 state-id to the user's free-form answer the
        BC runtime's LLM extracts from (the production CLI prompts the user
        interactively; tests pass a fixed dict).
        """
        if not principal_id:
            raise ValueError("principal_id is required for envoy init")
        genesis_key = genesis_session_key(principal_id)

        # Write-once idempotency gate (Rule 3): a single keyed read against the
        # durable store. If genesis already landed, refuse loudly — never
        # re-drive the ritual, never overwrite the cold-stored anchor's source.
        existing = await self._router.load_observed_state(genesis_key)
        if existing is not None:
            raise VaultAlreadyInitializedError(
                principal_id=principal_id,
                genesis_store_key=genesis_key,
            )

        # Drive the Boundary Conversation S0→S10 (LLM-first per the BC runtime).
        envelope_id = await self.drive_ritual(principal_id=principal_id, replies=replies)

        # Read the seeded Genesis chain back to derive the trust-anchor's public
        # material (the chain hash + the genesis verification public key). The
        # BC runtime's S9 seeded it via trust_store.seed_genesis; here we read
        # the PUBLIC surface only.
        chain = await self._trust_store.get_chain(principal_id)
        principal_genesis_id = f"sha256:{chain.hash()}"
        pubkey_hex = await self._trust_store.genesis_public_key_hex(principal_id)

        # Land the durable session genesis (write-once — the gate above proved
        # absence; snapshot lands it). A fresh process reads this back.
        genesis_session_id = _uuid7_like()
        genesis_state = build_genesis_session_state(
            session_id=genesis_session_id,
            principal_genesis_id=principal_genesis_id,
            envelope_version_at_session_start=1,  # first envelope is version 1
        )
        await self._router.snapshot_observed_state(
            session_id=genesis_key,
            state_json=json.dumps(genesis_state, separators=(",", ":")),
        )

        # Emit trust-anchor.json alongside the Shamir paper-shard ritual.
        anchor = build_trust_anchor(
            principal_genesis_id=principal_genesis_id,
            principal_genesis_pubkey_hex=pubkey_hex,
        )
        trust_anchor_path = self._emit_trust_anchor(principal_id, anchor)

        logger.info(
            "envoy.init.bootstrap.complete",
            extra={
                "principal_id_prefix": principal_id[:8],
                "envelope_id": envelope_id,
                "genesis_store_key": genesis_key,
                "trust_anchor": str(trust_anchor_path),
            },
        )
        return InitResult(
            principal_id=principal_id,
            envelope_id=envelope_id,
            genesis_session_id=genesis_session_id,
            genesis_store_key=genesis_key,
            trust_anchor_path=trust_anchor_path,
            principal_genesis_id=principal_genesis_id,
        )

    async def drive_ritual(self, *, principal_id: str, replies: dict[str, str]) -> str:
        """Drive the BC S0→S10 ritual and return the signed ``envelope_id``.

        Walks S0 greet → S1..S7 forward transitions → S8 Shamir suspend →
        offline-completion resume → S9 sign → S10 complete. Each S1..S9 reply is
        pumped through ``bc_runtime.advance`` which runs the per-state LLM
        extraction. Phase-01 treats the explicit ``resume_from_shamir`` call as
        the user's offline-card-distribution completion confirmation (per the BC
        runtime § resume_from_shamir).

        A re-promptable gate error (parse miss / novelty block / missing visible
        secret) raises ``InvalidStateTransitionError`` from the BC runtime path
        — surfaced loudly, never silently retried here (the CLI re-prompts the
        user; tests supply conforming answers).
        """
        ritual_id = await self._bc.start(principal_id=principal_id)
        # S0 greet advance (no answer).
        await self._bc.advance(ritual_id, "let's begin")

        forward_states = (
            "S1_money",
            "S2_people",
            "S3_topics",
            "S4_hours",
            "S5_first_task",
            "S6_template_offer",
            "S7_visible_secret",
        )
        for state in forward_states:
            outcome = await self._bc.advance(ritual_id, replies[state])
            if outcome.state == "ERROR":
                raise _bc_gate_error(outcome, state)  # surface the BC gate error loudly
            if outcome.state != "IN_PROGRESS":
                raise RuntimeError(
                    f"unexpected BC outcome at {state}: {outcome.state} "
                    f"(envoy init expects forward progress through S1..S7)"
                )

        # S8 Shamir — suspends the Plan; the user completes physical card
        # distribution offline, then resume clears the suspension.
        paused = await self._bc.advance(ritual_id, replies["S8_shamir"])
        if paused.state == "ERROR":
            raise _bc_gate_error(paused, "S8_shamir")
        if paused.state != "PAUSED" or paused.paused_for != "shamir_ritual":
            raise RuntimeError(
                f"envoy init expected the S8 Shamir suspension, got {paused.state}/"
                f"{paused.paused_for}"
            )
        await self._bc.resume_from_shamir(ritual_id)

        # S9 sign → S10 complete.
        done = await self._bc.advance(ritual_id, replies["S9_review_sign"])
        if done.state == "ERROR":
            raise _bc_gate_error(done, "S9_review_sign")
        if done.state != "COMPLETE" or not done.envelope_id:
            raise RuntimeError(
                f"envoy init expected S9 sign to complete with an envelope_id, "
                f"got {done.state}/{done.envelope_id!r}"
            )
        return done.envelope_id

    def _emit_trust_anchor(self, principal_id: str, anchor: dict[str, Any]) -> Path:
        """Write ``trust-anchor.json`` 0o600 into the trust-anchor dir.

        0o600 per `rules/security.md` + `rules/trust-plane-security.md` MUST
        Rule 6 — the anchor is the user's cold-storage verification material;
        a world-readable anchor would let any local user read (and substitute)
        it. The file holds ONLY public material, but tightening perms matches
        the ledger/vault sibling-file discipline.
        """
        self._trust_anchor_dir.mkdir(parents=True, exist_ok=True)
        path = self._trust_anchor_dir / "trust-anchor.json"
        # Create with restrictive perms BEFORE writing content (so the window
        # where the file exists world-readable never opens).
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(anchor, fh, indent=2, sort_keys=True)
                fh.write("\n")
        except BaseException:
            # os.fdopen took ownership of fd on success; on a pre-fdopen failure
            # the fd is closed here. (BaseException so a KeyboardInterrupt mid-
            # write still releases the descriptor — cleanup, not error-hiding.)
            raise
        # Tighten again in case a permissive umask widened the create mode.
        os.chmod(str(path), 0o600)
        return path
