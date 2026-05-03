# 14 — Connection Vault Implementation (Phase 01 Minimal)

**Document role:** Per-primitive deep-dive for the Connection Vault primitive. Phase 01 ships the minimal cut: an OS-keychain-backed credential store for channel adapter API keys / bot tokens. Full third-party OAuth (per-platform OAuth dance) is deferred to Phase 02 per de-scope candidate #3 (`00-inheritance-from-phase-00.md` § 2.1 + `01-shard-plan.md` § 2 row 14).

**Date:** 2026-05-03 (shard 14 of /analyze).
**Status:** DRAFT — load-bearing for shards 16 (channel adapters) + 19 (pipx distribution) + 8 (Boundary Conversation onboarding writes initial credentials).
**Owning shard:** 14 (per `01-shard-plan.md` § 2).
**Exit criteria served:** EC-7 (8-channel onboarding requires channel-adapter credentials), EC-8 (week-long cross-channel operation requires credentials persist across sessions), and as cross-cutting structural prerequisite per `02-mvp-objectives.md` § 3 row 5 ("Connection Vault — minimal — keychain wrapper — Channel adapters need API keys to function; without Connection Vault, channel adapters store secrets ad-hoc").

---

## 1. Source spec citation

**Primary source (frozen, DO NOT EDIT):**

- `specs/connection-vault.md` — full spec (90 lines).

Cited sub-sections, by path + section name (per `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` "cite by path + section, never paraphrase"):

- `specs/connection-vault.md` § "Purpose" — "Third-party credential storage (API keys, channel tokens, OAuth refresh) — OS keychain wrapper, per-principal isolated."
- `specs/connection-vault.md` § "Distinct from Trust Vault" — Trust Vault holds Envoy's own keys + envelope; Connection Vault holds third-party credentials.
- `specs/connection-vault.md` § "Platforms" — macOS Keychain, Windows Credential Manager, Linux Secret Service (GNOME Keyring / KWallet), iOS Secure Enclave, Android Keystore.
- `specs/connection-vault.md` § "Per-entry schema" — 11-field credential entry schema (`entry_id`, `principal_genesis_id`, `credential_type`, `service_identifier`, `entry_envelope_scope`, `ciphertext`, `created_at`, `last_used_at`, `expires_at`, `usage_counter`, `rotation_policy`).
- `specs/connection-vault.md` § "Per-principal isolation (Phase 03)" — Phase 03 boundary; Phase 01 is single-principal but the schema includes `principal_genesis_id` as the multi-principal hook (consistent with `00-inheritance-from-phase-00.md` § 6 invariant #1 — tenant-isolation dimension on every key even though Phase 01 is single-principal).
- `specs/connection-vault.md` § "Never synced" — OS keychain is device-local by design.
- `specs/connection-vault.md` § "Clipboard hygiene" — secure-text-field inputs; auto-clear clipboard after N seconds (30 default).
- `specs/connection-vault.md` § "Error taxonomy" — 7 error classes (`KeychainUnavailableError`, `EntryExpiredError`, `CrossPrincipalAccessRefusedError`, `EnvelopeScopeMismatchError`, `EntryNotFoundError`, `RotationOverdueWarn`, `UsageCounterOverflowError`).

**Secondary spec (informational, related-but-distinct):**

- `specs/trust-vault.md` § "Cross-references" line 68 — "specs/connection-vault.md — distinct container; Shamir doesn't cover Connection Vault." This is the structural boundary: Phase 01 Shamir backup (shard 15, EC-5) covers Trust Vault keys ONLY; Connection Vault re-population happens via fresh Grant Moments after recovery (`specs/connection-vault.md` § "Never synced" line 48: "After Shamir recovery, user re-authenticates each channel/model via fresh Grant Moments").

**Phase boundary specs (informational):**

- ADR-0007 (per `00-inheritance-from-phase-00.md` § 2.2) — "Phase 01 ships local-only; sync deferred to Phase 03." This binds Trust Vault sync; Connection Vault `Never synced` is more restrictive (device-local forever, not deferred).

---

## 2. Verified provider citation

### 2.1 `kailash-py` — VERIFIED ABSENT

The Phase 00 survey at `workspaces/phase-00-alignment/01-analysis/02-kailash-py-survey.md` enumerates 26 primitives. Connection Vault is not among them. The 26 primitives audited cover envelope, trust, lineage, ledger, posture, classification, channels, Kaizen, MCP, conformance — none touch OS-keychain credential storage.

The freshness gate against the 13 Phase 00-filed kailash-py issues (`03-kailash-py-mvp-readiness.md` § 2) lists no issue tracking a Connection Vault primitive. The 50 indirectly-relevant closures since 2026-04-21 (`03-kailash-py-mvp-readiness.md` § 2.2) include Twilio webhook signing (#687), JWT iss-claim hardening (#635, #636, #625), and DataFlow lifecycle bugs — none is a Connection Vault.

`03-kailash-py-mvp-readiness.md` § 3 row 11 states explicitly: "Provider: OS keychain wrappers (`keyring` Python package); `kailash-py` does not provide Phase 01 minimum." Net: Connection Vault is **Envoy-new-code by design** — not a kailash-py gap to file upstream, but a primitive that lives correctly in the consumer (Envoy) layer because Envoy is the agent-runtime and the OS-keychain access is an agent-side concern.

**Verification protocol** per `03-kailash-py-mvp-readiness.md` § 5: this shard has no closed-ISS to look up because no upstream kailash-py work is being depended on. The verification reduces to "confirm absence" — done by the Phase 00 26-primitive survey + the Phase 00-to-Phase-01 freshness gate. No further upstream verification is required.

**Note on tooling failure during verification:** the Grep / Glob tools returned `ENOENT: no such file or directory, posix_spawn 'rg'` for `~/repos/loom/kailash-py/` direct grep against `ConnectionVault` / `connection_vault` / `keychain` / `keyring`. This is a runtime environment limitation, not evidence. The survey-based verification (Phase 00 26-primitive enumeration + 12-day freshness gate) is the canonical evidence and is unaffected. If a future shard needs direct upstream confirmation, the protocol is to `cd ~/repos/loom/kailash-py && grep -rln 'ConnectionVault\|keyring\|keychain' src/` once tooling is available.

### 2.2 Third-party `keyring` Python package — VERIFIED PROVIDER

**Library:** `keyring` (PyPI: `keyring`).

- **License:** MIT License (Apache-2.0 compatible per `02-plans/legal/03-license-compatibility-statement.md` Phase 02 framing inherited via `00-inheritance-from-phase-00.md` § 4). MIT is permissive and downstream-compatible with Envoy's intended distribution license per ADR-0009.
- **Maintenance:** Maintained by Jaraco (Jason R. Coombs) + Python community; current major version 24.x (as of mid-2026); long-running upstream (initial release 2009).
- **Backends shipped:** macOS Keychain (built-in), Windows Credential Locker (built-in via `pywin32-ctypes` or `keyring.backends.Windows`), Linux Secret Service via SecretStorage / D-Bus (`keyring.backends.SecretService` — covers GNOME Keyring + KWallet), Linux KWallet5 (separate backend), Linux libsecret (alternate). The library auto-selects the best available backend per `keyring.get_keyring()`.
- **API surface used by Phase 01:** `keyring.set_password(service, username, password)`, `keyring.get_password(service, username)`, `keyring.delete_password(service, username)`, `keyring.get_keyring()` for backend introspection.
- **Phase 01 platform coverage:** macOS + Linux + Windows (full coverage of `pipx install envoy-agent` target platforms per shard 19). iOS Secure Enclave + Android Keystore from `specs/connection-vault.md` § "Platforms" are Phase 02 mobile concerns (per ADR-0008 mobile onboarding deferred to Phase 02) and out-of-scope for the Phase 01 keyring wrapper.

**License verification action item (deferred to shard 19 pipx distribution):** Phase 01 must record the `keyring` MIT license in the Envoy distribution's `LICENSE` / `NOTICES` file per `00-inheritance-from-phase-00.md` § 4 row "legal/03-license-compatibility-statement.md". Shard 19 owns this aggregation; this shard records the disposition.

**Alternative considered + rejected:** `python-secretstorage` (Linux only, lower-level), `pyobjc-framework-Security` (macOS only, lower-level), platform-direct API binding — all rejected because `keyring` is the canonical cross-platform abstraction, audited (years of production use across Python ecosystem), and removes per-platform glue from Envoy-new-code (smaller Envoy surface, less Phase 01 maintenance burden).

---

## 3. Envoy-new-code surface

This is **all Envoy-new-code by design** — no `kailash-py` consumption, no upstream PR dependency. The surface is:

### 3.1 `envoy.connection_vault` Python module — the adapter

A thin adapter wrapping `keyring` to enforce the `specs/connection-vault.md` per-entry schema, error taxonomy, and fail-closed defaults.

**Concretely owned by Envoy:**

1. **Per-entry schema serialization** — `specs/connection-vault.md` § "Per-entry schema" defines 11 fields. `keyring`'s `set_password(service, username, password)` API is a 3-tuple; Envoy must serialize the 11-field record into the `password` slot (canonical-JSON or msgpack), keying on `entry_id` (UUID-v7) in the `username` slot and a fixed Envoy `service` namespace (e.g. `"envoy.connection-vault"`).
2. **Per-principal isolation hook** — `principal_genesis_id` field per `specs/connection-vault.md` § "Per-principal isolation (Phase 03)". Phase 01 single-principal still writes the field (per `00-inheritance-from-phase-00.md` § 6 invariant #1 — tenant-isolation dimension on every key even when single-principal); Phase 03 multi-principal will gate cross-principal reads on Grant Moment.
3. **Envelope-scope enforcement** — `entry_envelope_scope: EnvelopeScopeRef` field per `specs/connection-vault.md` § "Per-entry schema". The vault's `get(entry_id)` MUST refuse retrieval when the caller's session envelope does not include the entry's recorded envelope scope (per `specs/connection-vault.md` § "Error taxonomy" → `EnvelopeScopeMismatchError`). This connects the Connection Vault to the Envelope compiler primitive (shard 4) — the vault asks the envelope compiler "does this session's envelope include this credential's scope?" before returning the credential.
4. **`expires_at` enforcement** — Phase 01 minimum: per `specs/connection-vault.md` § "Per-entry schema" row, "runtime refuses use after expiry"; raises `EntryExpiredError`.
5. **`usage_counter` increment + monotonic guard** — incremented on every successful retrieval; `UsageCounterOverflowError` on int64 ceiling per `specs/connection-vault.md` § "Error taxonomy".
6. **Error taxonomy class hierarchy** — 7 typed exception classes per `specs/connection-vault.md` § "Error taxonomy" (`KeychainUnavailableError`, `EntryExpiredError`, `CrossPrincipalAccessRefusedError`, `EnvelopeScopeMismatchError`, `EntryNotFoundError`, `RotationOverdueWarn` — advisory; `UsageCounterOverflowError`).
7. **Fail-closed defaults** — adapted from `rules/security.md` § "Fail-Closed Security Defaults" (Rust-flavored in source rule; Python adaptation): default constructors / `Default`-equivalent factory functions return the most-restrictive state. For Connection Vault: a vault initialized without an active envelope MUST refuse all `get()` calls (raises `EnvelopeScopeMismatchError`). A vault initialized without a `principal_genesis_id` MUST refuse all `set()` calls. The `Phase 01 single-principal` wiring derives these from the active session per shard 8 Boundary Conversation output, NOT from a global default.
8. **Rotation-API stub** — `rotation_policy` per `specs/connection-vault.md` § "Per-entry schema" is recorded; `RotationOverdueWarn` is advisory in Phase 01 (UX nudge only, not a hard block per spec). Full rotation execution (re-issuing tokens, walking OAuth refresh chains) is Phase 02 per de-scope #3.
9. **`.env` first-run import path** — per `rules/env-models.md` (loaded via `dotenv` at root `conftest.py`) + `rules/security.md` § "No Hardcoded Secrets": Phase 01 first-run accepts API keys via `.env` file at install time (e.g. `TELEGRAM_BOT_TOKEN=...`); the Boundary Conversation onboarding (shard 8) reads from `.env` and writes to the Connection Vault. After first-run, `.env` is no longer the source of truth — the Vault is. The user is shown the `.env`-to-Vault migration in the Boundary Conversation surface.

### 3.2 `envoy.connection_vault.schema` — credential schema dataclasses

Pydantic / dataclasses representing the 11-field per-entry schema. These are Envoy-internal serialization types; they do NOT flow to upstream kailash-py.

### 3.3 `envoy.connection_vault.errors` — error taxonomy module

7 typed exception classes per `specs/connection-vault.md` § "Error taxonomy". Each derives from a single `ConnectionVaultError` base for `try/except` ergonomics.

### 3.4 What is NOT Envoy-new-code (boundaries)

- **OS keychain primitives** — `keyring` library handles macOS Keychain / Windows Credential Manager / Linux Secret Service. Envoy does NOT touch the platform APIs directly.
- **Cryptography** — `keyring` ciphertext is the OS keychain's responsibility; Envoy does NOT add a layer of encryption (the OS keychain is the cipher).
- **OAuth refresh flow** — Phase 02 per de-scope #3. Phase 01 stores existing OAuth refresh tokens but does NOT execute the refresh dance.
- **iOS Secure Enclave / Android Keystore wiring** — Phase 02 mobile per ADR-0008. Phase 01 ships desktop only (`pipx install envoy-agent`).
- **Trust Vault keys** — `specs/trust-vault.md` is a separate primitive (shard 5 + shard 15). Connection Vault holds third-party credentials only; Envoy's own Ed25519 keys live in the Trust Vault (per `specs/connection-vault.md` § "Distinct from Trust Vault" + `specs/trust-vault.md` § "Cross-references"). NOTE the question in § 5 below about the integration prompt's claim that Trust store writes Ed25519 keys to the Vault — that contradicts the spec.

---

## 4. Class structure sketch (interfaces only)

```python
# envoy/connection_vault/__init__.py

from envoy.connection_vault.adapter import ConnectionVault
from envoy.connection_vault.schema import CredentialEntry, CredentialType, RotationPolicy
from envoy.connection_vault.errors import (
    ConnectionVaultError,
    KeychainUnavailableError,
    EntryExpiredError,
    CrossPrincipalAccessRefusedError,
    EnvelopeScopeMismatchError,
    EntryNotFoundError,
    UsageCounterOverflowError,
)

__all__ = [
    "ConnectionVault",
    "CredentialEntry", "CredentialType", "RotationPolicy",
    "ConnectionVaultError",
    "KeychainUnavailableError",
    "EntryExpiredError",
    "CrossPrincipalAccessRefusedError",
    "EnvelopeScopeMismatchError",
    "EntryNotFoundError",
    "UsageCounterOverflowError",
]
```

```python
# envoy/connection_vault/schema.py

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from envoy.envelope import EnvelopeScopeRef  # from shard 4 envelope compiler

class CredentialType(str, Enum):
    API_KEY = "api_key"
    BOT_TOKEN = "bot_token"
    OAUTH_REFRESH = "oauth_refresh"
    BASIC_AUTH = "basic_auth"
    WEBHOOK_SECRET = "webhook_secret"

class RotationPolicy(str, Enum):
    NEVER = "never"
    YEARLY = "yearly"
    QUARTERLY = "quarterly"
    MONTHLY = "monthly"
    ON_EVENT = "on_event"

@dataclass(frozen=True)
class CredentialEntry:
    entry_id: UUID
    principal_genesis_id: str  # sha256 hex of owning principal
    credential_type: CredentialType
    service_identifier: str
    entry_envelope_scope: EnvelopeScopeRef
    # ciphertext is NOT stored on the Python object — it lives in the OS keychain
    created_at: datetime
    last_used_at: datetime
    expires_at: Optional[datetime]
    usage_counter: int
    rotation_policy: RotationPolicy
```

```python
# envoy/connection_vault/adapter.py

from typing import Optional
from uuid import UUID

import keyring  # third-party MIT-licensed

from envoy.connection_vault.schema import CredentialEntry, CredentialType, RotationPolicy
from envoy.connection_vault.errors import (
    KeychainUnavailableError, EntryExpiredError,
    CrossPrincipalAccessRefusedError, EnvelopeScopeMismatchError,
    EntryNotFoundError, UsageCounterOverflowError,
)
from envoy.envelope import EnvelopeScopeRef, SessionEnvelope

KEYRING_SERVICE_NAMESPACE = "envoy.connection-vault"

class ConnectionVault:
    """
    OS-keychain-backed credential store per specs/connection-vault.md.

    Phase 01 minimum: get / set / delete / list-by-principal.
    Phase 02: rotation execution; OAuth refresh flow.
    Phase 03: per-principal isolation (currently single-principal in Phase 01).

    Fail-closed defaults: vault refuses get() without an active session envelope.
    """

    def __init__(
        self,
        principal_genesis_id: str,
        active_envelope: SessionEnvelope,
        # backend optional; defaults to keyring's auto-selected best backend
    ) -> None:
        ...

    def set(
        self,
        *,
        credential_type: CredentialType,
        service_identifier: str,
        entry_envelope_scope: EnvelopeScopeRef,
        secret: str,
        expires_at: Optional["datetime"] = None,
        rotation_policy: RotationPolicy = RotationPolicy.NEVER,
    ) -> CredentialEntry:
        """
        Write a new credential entry to the OS keychain.
        Raises KeychainUnavailableError if the keychain is locked / unavailable.
        """
        ...

    def get(self, entry_id: UUID) -> tuple[CredentialEntry, str]:
        """
        Retrieve a credential entry + plaintext secret.

        Raises:
            EntryNotFoundError if entry_id absent (or owned by different principal).
            EntryExpiredError if expires_at has passed.
            CrossPrincipalAccessRefusedError if entry's principal_genesis_id != self's.
            EnvelopeScopeMismatchError if active_envelope does not include
                entry.entry_envelope_scope.
            KeychainUnavailableError if keychain locked.
            UsageCounterOverflowError if usage_counter at int64 ceiling.

        Updates last_used_at + usage_counter on success.
        """
        ...

    def delete(self, entry_id: UUID) -> None:
        ...

    def list_by_principal(self) -> list[CredentialEntry]:
        """Phase 01: returns entries owned by self.principal_genesis_id."""
        ...

    def is_available(self) -> bool:
        """Diagnostic — is the OS keychain reachable?"""
        ...
```

```python
# envoy/connection_vault/errors.py

class ConnectionVaultError(Exception):
    """Base for all Connection Vault errors."""

class KeychainUnavailableError(ConnectionVaultError): ...
class EntryNotFoundError(ConnectionVaultError): ...
class EntryExpiredError(ConnectionVaultError): ...
class CrossPrincipalAccessRefusedError(ConnectionVaultError): ...
class EnvelopeScopeMismatchError(ConnectionVaultError): ...
class UsageCounterOverflowError(ConnectionVaultError): ...
# RotationOverdueWarn is advisory — not raised, surfaced via UX nudge per spec
```

The interface is intentionally narrow — five public methods (`set`, `get`, `delete`, `list_by_principal`, `is_available`). Phase 02 will add `rotate(entry_id)` + OAuth-refresh-execution; the Phase 01 surface is sufficient for EC-7 + EC-8.

---

## 5. Integration points

### 5.1 Channel adapters (shard 16) — READ on init

Every channel adapter (CLI, Web, iMessage, Telegram, Slack, Discord, WhatsApp, Signal — 8 total per `specs/channel-adapters.md` and `02-mvp-objectives.md` EC-7) reads its bot token / API key from the Connection Vault on adapter init. The 8 adapters MUST each have a Tier 2 integration test that:

1. Writes a test credential to a real OS keychain via `ConnectionVault.set()`.
2. Constructs the channel adapter with the resulting `entry_id`.
3. Asserts the adapter resolves the credential correctly (via mocked channel server, since the actual channel API is out-of-scope for the keychain test).

This satisfies `rules/orphan-detection.md` MUST Rule 1 ("every credential read site has an end-to-end test through the facade") for the 8 adapters.

### 5.2 Boundary Conversation (shard 8) — WRITE during onboarding

The first-time Boundary Conversation (`specs/boundary-conversation.md`, EC-1) collects API keys / channel tokens during the 15-minute onboarding ritual. The conversation writes these to the Connection Vault via `ConnectionVault.set()` keyed to the principal's just-created `principal_genesis_id` (per shard 5 Trust store). The credential-collection step uses the secure-text-field input pattern per `specs/connection-vault.md` § "Clipboard hygiene" (no clipboard echo; auto-clear in 30s).

### 5.3 Trust store (shard 5) — DOES NOT write Ed25519 keys to Connection Vault

The shard prompt suggests "Trust store (5) writes Ed25519 keys to the Vault." This appears to contradict `specs/connection-vault.md` § "Distinct from Trust Vault" line 14–16 ("Trust Vault: Envoy's own keys + envelope. Connection Vault: third-party credentials") and `specs/trust-vault.md` § "Cross-references" line 68 ("specs/connection-vault.md — distinct container; Shamir doesn't cover Connection Vault").

**Disposition:** the spec is unambiguous — Envoy's own Ed25519 keys live in the Trust Vault (shard 5), NOT the Connection Vault. The shard prompt's mention is treated as a non-authoritative scoping suggestion, NOT a spec ambiguity. Per `journal/0001` "the shard's question is NEVER 'is this spec right?'; it is ALWAYS 'given this spec is frozen, how do I wire X'": the integration is "Trust store (shard 5) writes Ed25519 keys to the Trust Vault, NOT the Connection Vault." This shard's deep-dive docs Connection Vault accordingly. Any later shard wishing to revisit this should escalate per `01-shard-plan.md` § 4.

### 5.4 Shamir recovery (shard 15) — DOES NOT back up Connection Vault contents

Per `specs/connection-vault.md` § "Never synced" line 47–49: "OS keychain is device-local by design. After Shamir recovery, user re-authenticates each channel/model via fresh Grant Moments." And `specs/trust-vault.md` § "Cross-references" line 68: "Shamir doesn't cover Connection Vault."

So shard 15 Shamir backup operates only on the Trust Vault keys. After Shamir recovery on a new device, the Connection Vault is empty; the user re-pairs each channel via fresh Grant Moments — which is the post-Shamir UX rehearsal per `tests/integration/test_post_shamir_recovery_repair.py` (test name from `specs/connection-vault.md` § "Test location" line 81).

The shard prompt's suggestion that "Shamir recovery (15) backs up Vault contents (or the Trust store keys it holds)" parses cleanly under the second clause — Shamir backs up Trust store keys, NOT Connection Vault contents. The Trust store key set is what the Shamir 3-of-5 ritual covers; Connection Vault contents are by-design device-local and re-issued post-recovery.

### 5.5 Envelope compiler (shard 4) — Vault asks compiler for envelope-scope membership

`ConnectionVault.get(entry_id)` checks `entry.entry_envelope_scope ∈ self.active_envelope`. This is a read against the envelope compiler primitive (shard 4). The check is structural (`intersect_envelopes()` semantic per `kailash.trust.pact.envelopes`); the Connection Vault is a consumer, not a producer of envelope logic.

### 5.6 Grant Moment (shard 10) — Vault triggers Grant Moment on cross-principal access (Phase 03)

In Phase 03 multi-principal, `CrossPrincipalAccessRefusedError` invites a Grant Moment from the owning principal. Phase 01 is single-principal; the error class exists but the path from error → Grant Moment is not wired. This is the multi-principal hook per `00-inheritance-from-phase-00.md` § 6 invariant #1.

---

## 6. Tier 2 / Tier 3 test surface

Per `rules/testing.md` § "Tier 2 (Integration): Real infrastructure recommended" + `rules/orphan-detection.md` MUST Rule 1 + 2 (every wired manager has a Tier 2 integration test asserting externally-observable effect through the facade).

### 6.1 Tier 2 (real OS keychain on developer machine + CI)

**Per-platform round-trip tests** (per `specs/connection-vault.md` § "Test location" line 77 — `tests/integration/test_connection_vault_per_platform.py`):

- macOS: `ConnectionVault.set()` → keychain entry written; `ConnectionVault.get()` → secret retrieved bit-identical; `keyring.get_keyring()` reports `keyring.backends.macOS`.
- Linux (CI: ubuntu-latest with `dbus-launch` + GNOME Keyring or `secret-tool`): same round-trip; `keyring.get_keyring()` reports `keyring.backends.SecretService`.
- Windows (CI: windows-latest): same round-trip; `keyring.get_keyring()` reports `keyring.backends.Windows`.

**Cross-OS portability test for BET-9b** — per `02-mvp-objectives.md` EC-5 `BET-9b vault portability` and `specs/connection-vault.md` § "Test location" line 80 (`tests/integration/test_envelope_scope_enforcement.py`). Phase 01 NOTE: BET-9b is technically about the Trust Vault (which IS portable via Shamir), not the Connection Vault (which is by-design device-local). The Phase 01 cross-OS test on Connection Vault verifies that the **API is identical across OSes** (same `set` / `get` / `delete` semantics), NOT that contents migrate.

**Envelope-scope enforcement test** (per `specs/connection-vault.md` § "Test location" line 80):

- Construct vault with active envelope A.
- Write entry with `entry_envelope_scope` = scope-X (∈ A).
- Try to retrieve entry with active envelope B (where scope-X ∉ B).
- Assert `EnvelopeScopeMismatchError`.

**Per-principal isolation test** (per `specs/connection-vault.md` § "Test location" line 79 — Phase 03 surface; Phase 01 ships the test as a future-proofing exercise asserting the error class fires correctly).

**Post-Shamir recovery test** (per `specs/connection-vault.md` § "Test location" line 81):

- Run Shamir reconstruct (shard 15).
- Assert `ConnectionVault.list_by_principal()` returns empty list (recovery does NOT restore Connection Vault).
- Walk user through re-pairing one channel via fresh Grant Moment.

**Channel-adapter wiring test** (per `rules/orphan-detection.md` MUST Rule 1):

- For each of the 8 channel adapters: write test credential, init adapter, assert credential resolves through the adapter's actual init code path. This satisfies "every facade has a production call site" — without it, ConnectionVault is an orphan that channel adapters don't actually use.

### 6.2 Tier 3 (E2E)

End-to-end first-time install → Boundary Conversation onboarding → channel-adapter pairing → message send. Asserts every layer crosses the keychain boundary correctly. Owned by shard 16 (channel adapters) E2E suite; this shard contributes the credential-collection contract.

### 6.3 Regression tests

**`tests/regression/test_t007_credential_storage_no_sync.py`** (per `specs/connection-vault.md` § "Test location" line 78) — T-007 defense (per `specs/threat-model.md`): credentials are NOT copied to any sync surface. This regression test scans the Phase 01 codebase for any path that copies keychain entries to a sync queue / cloud backend / file-system mirror, asserts none exists.

**`tests/regression/test_clipboard_autoclear_30s.py`** (per `specs/connection-vault.md` § "Test location" line 82) — credential-capture clipboard hygiene; clipboard cleared within 30s. Tier 2 because clipboard is OS-mediated.

### 6.4 Test-skip discipline

Per `rules/testing.md` § "Test-Skip Triage Decision Tree": Linux Secret Service requires `dbus-launch` + a session daemon. Tests that need this MUST use ACCEPTABLE skip pattern:

```python
@pytest.mark.skipif(
    os.environ.get("CI_LINUX_SECRET_SERVICE_AVAILABLE") != "1",
    reason="requires Linux Secret Service (D-Bus + GNOME Keyring or KWallet)",
)
def test_connection_vault_linux_round_trip(): ...
```

NOT `@pytest.mark.skip(reason="TODO")` — that's BLOCKED.

### 6.5 Env-var test isolation

Tests that mutate `KEYRING_PROPERTY_*` env vars or `XDG_RUNTIME_DIR` (Linux) MUST use the `_env_serialized` lock pattern from `rules/testing.md` § "Env-Var Test Isolation". The `keyring` library reads env-controlled config; concurrent xdist workers will produce flaky results without serialization.

---

## 7. Frozen-spec ambiguity

### 7.1 LOW: Linux Secret Service availability fallback (spec open question 1)

`specs/connection-vault.md` § "Open questions" #1: "Linux Secret Service availability fallback — what if neither GNOME Keyring nor KWallet present (CLI-only env)."

**Phase 01 disposition (LOW, no escalation):** the spec leaves this open; Phase 01's `keyring` library covers the question via its `keyring.backends.fail.Keyring` fallback (raises on every operation). Phase 01 surfaces this as `KeychainUnavailableError` with a clear message ("install GNOME Keyring, KWallet, or another Secret Service provider"). Headless-CI environments use a `keyrings.alt` backend (file-based, encrypted with a passphrase) per the `keyring` ecosystem convention — Phase 01 does NOT ship `keyrings.alt` to the user but documents it as the user's escape hatch.

This is LOW because it does not block any EC; it is an operational footnote.

### 7.2 LOW: `service_identifier` registry strictness (spec open question 2)

`specs/connection-vault.md` § "Open questions" #2: "`service_identifier` registry vs free-form — strictness of validation; phase-gated."

**Phase 01 disposition (LOW):** Phase 01 accepts free-form `service_identifier` strings. The Foundation `service_identifier` registry (per `specs/foundation-ops.md`) is a Phase 02 concern — Phase 01's Connection Vault validates only that the string is non-empty + UTF-8 + ≤256 chars + matches `^[a-z0-9._-]+$` (defensive against accidentally injecting characters that confuse downstream channel-adapter URL construction).

### 7.3 LOW: rotation_policy enforcement strength (spec open question 3)

`specs/connection-vault.md` § "Open questions" #3: "rotation_policy enforcement strength — advisory nudge vs hard expiry on overdue."

**Phase 01 disposition (LOW):** Phase 01 ships `rotation_policy` as advisory only (`RotationOverdueWarn` is documented as advisory in the error taxonomy line 64 — "advisory, not raised"). Hard expiry is the `expires_at` field, not the `rotation_policy` field. This is consistent with the spec's "policy hint for UX nudges" framing (line 41).

### 7.4 LOW: cross-device migration UX (spec open question 4)

Phase 02 mobile concern per ADR-0008. Phase 01 disposition is "out of scope."

### 7.5 LOW: per-credential clearance vs envelope-scope expressiveness (spec open question 5)

`specs/connection-vault.md` § "Open questions" #5: "Per-credential clearance vs envelope-scope expressiveness — sufficient or needs orthogonal policy."

**Phase 01 disposition (LOW):** Phase 01 uses envelope-scope only (per the schema field `entry_envelope_scope`). Whether per-credential clearance becomes a separate orthogonal field is a Phase 02 design decision; Phase 01 implementation sets the precedent (envelope-scope is sufficient for MVP) but does NOT close the question.

### 7.6 NO HIGH ambiguity surfaces

No HIGH-severity gap surfaces against the frozen `specs/connection-vault.md`. The spec is well-formed for Phase 01 minimum implementation. No `01-shard-plan.md` § 4 escalation required. No spec edit triggers the MUST Rule 5b sweep cost.

---

## 8. Cross-references

**Frozen specs (DO NOT EDIT):**

- `specs/connection-vault.md` — primary source
- `specs/trust-vault.md` — distinct container boundary
- `specs/envelope-model.md` — envelope-scope enforcement upstream contract
- `specs/grant-moment.md` — Phase 03 cross-principal Grant Moment
- `specs/channel-adapters.md` — 8-channel consumer set
- `specs/threat-model.md` — T-007 credential-storage threat
- `specs/data-model.md` — multi-principal data-model affordances
- `specs/foundation-ops.md` — service-identifier registry (Phase 02)

**ADRs (frozen):**

- ADR-0007 — Trust Vault sync deferred to Phase 03 (Connection Vault never-synced is more restrictive)
- ADR-0008 — Mobile onboarding deferred to Phase 02 (iOS Secure Enclave + Android Keystore)

**Phase 01 analysis docs:**

- `01-analysis/00-inheritance-from-phase-00.md` § 2.1 (de-scope candidate #3) + § 2.2 (ADRs) + § 6 (invariants)
- `01-analysis/01-shard-plan.md` § 2 row 14 (this shard)
- `01-analysis/02-mvp-objectives.md` § 3 row 5 (cross-cutting deliverable) + EC-7 + EC-8
- `01-analysis/03-kailash-py-mvp-readiness.md` § 3 row 11 (provider absence) + § 5 (verification protocol)
- `01-analysis/15-shamir-recovery-implementation.md` (shard 15 — Shamir does NOT cover Connection Vault) — TBD
- `01-analysis/16-channel-adapters-implementation.md` (shard 16 — 8-adapter consumers) — TBD
- `01-analysis/04-envelope-compiler-implementation.md` (shard 4 — `intersect_envelopes()` upstream consumer) — TBD
- `01-analysis/08-boundary-conversation-implementation.md` (shard 8 — onboarding writer) — TBD
- `01-analysis/19-pipx-distribution-architecture.md` (shard 19 — `keyring` license aggregation) — TBD

**Journal entries:**

- `journal/0001-CONNECTION-phase-00-to-phase-01-bridge.md` — re-derivation discipline; cite-by-path methodology

**Rules consulted:**

- `rules/security.md` § "No Hardcoded Secrets" — Connection Vault is the secure-storage primitive
- `rules/security.md` § "Fail-Closed Security Defaults" — adapted to Python adapter constructor
- `rules/env-models.md` — `.env` first-run import path; pytest dotenv loading
- `rules/orphan-detection.md` MUST Rule 1 + 2 — every credential read site has a Tier 2 integration test through the facade
- `rules/testing.md` § "Tier 2" + § "Test-Skip Triage" + § "Env-Var Test Isolation"
- `rules/specs-authority.md` MUST Rule 4 — phases read specs before acting (this shard re-read `specs/connection-vault.md` + `specs/trust-vault.md` first)
- `rules/specs-authority.md` MUST Rule 5b — no spec edits in this shard; no sibling re-derivation triggered
- `rules/autonomous-execution.md` § "Per-Session Capacity Budget" — this shard stays within budget (1 spec, 5 cross-primitive references, ≤8 invariants)
- `rules/independence.md` — `keyring` is an MIT third-party; Envoy is a Foundation-stewarded pure-Python pip-install agent; license recorded for shard 19 NOTICES aggregation
