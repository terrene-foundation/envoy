"""Tier 1 tests for `envoy.connection_vault.ConnectionVault`.

Pins the 5 invariants per
`workspaces/phase-01-mvp/todos/active/01-wave-1-foundation.md` § T-01-24:

1. 11-field schema (`CredentialEntry` shape preserved across the keychain
   serialization round-trip).
2. `principal_genesis_id` key (cross-principal access raises).
3. envelope-scope match (`get` refuses when active envelope doesn't
   contain the entry's scope).
4. Lifecycle enforcement (`expires_at`, `usage_counter` overflow guard).
5. `.env` one-time import (`import_credentials_from_env` populates from
   `os.environ` and reports skips honestly).

Per `rules/testing.md` § Tier 1: pure-Python; in-memory backend; no real OS
keychain. The Tier 2 wire-up (T-01-25) exercises real keyring backends.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import keyring.errors
import pytest

from envoy.connection_vault import (
    USAGE_COUNTER_MAX,
    ConnectionVault,
    CorruptedRecordError,
    CredentialType,
    EnvCredentialSpec,
    EntryExpiredError,
    EntryNotFoundError,
    EnvelopeScopeMismatchError,
    InvalidServiceIdentifierError,
    KeychainUnavailableError,
    PrincipalRequiredError,
    RecordSchemaVersionError,
    RotationPolicy,
    UsageCounterOverflowError,
    import_credentials_from_env,
    validate_principal_genesis_id,
    validate_service_identifier,
)


def _hex_principal(label: str) -> str:
    """Build a sha256-hex principal_genesis_id matching the spec contract.

    Per security-reviewer M3 (2026-05-24) the principal_genesis_id MUST be
    64 lowercase hex characters. Tests use this helper to derive stable
    sha256 ids from labels.
    """
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


_PRINCIPAL_ALPHA = _hex_principal("principal-alpha")
_PRINCIPAL_A = _hex_principal("principal-A")
_PRINCIPAL_B = _hex_principal("principal-B")
_PRINCIPAL_ABC = _hex_principal("abc")


# Override the global `principal_id` fixture (root tests/tier1/conftest.py)
# for this file — Connection Vault requires sha256-hex shape per spec.
@pytest.fixture
def principal_id() -> str:
    return _PRINCIPAL_ALPHA


from envoy.connection_vault.adapter import _deserialize_record, _serialize_record
from envoy.connection_vault.schema import CredentialEntry
from envoy.envelope import (
    CommunicationDimension,
    EnvelopeConfigInput,
    EnvelopeScopeRef,
    OperationalDimension,
)


# ---------------------------------------------------------------------------
# In-memory keyring backend fixture
# ---------------------------------------------------------------------------


class _MemBackend:
    """Pure-dict keyring backend for Tier 1 tests."""

    def __init__(self) -> None:
        self._d: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._d[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._d.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        key = (service, username)
        if key not in self._d:
            raise keyring.errors.PasswordDeleteError("not found")
        del self._d[key]


class _FailingBackend(_MemBackend):
    """Backend that simulates KeyringError on every operation."""

    def set_password(self, service: str, username: str, password: str) -> None:
        raise keyring.errors.KeyringError("keychain locked")

    def get_password(self, service: str, username: str) -> str | None:
        raise keyring.errors.KeyringError("keychain locked")

    def delete_password(self, service: str, username: str) -> None:
        raise keyring.errors.KeyringError("keychain locked")


@pytest.fixture
def envelope_openai_cli() -> EnvelopeConfigInput:
    return EnvelopeConfigInput(
        operational=OperationalDimension(tool_allowlist=["openai", "claude"]),
        communication=CommunicationDimension(channel_allowlist=["cli", "web"]),
    )


@pytest.fixture
def envelope_telegram() -> EnvelopeConfigInput:
    return EnvelopeConfigInput(
        operational=OperationalDimension(tool_allowlist=["telegram-bot"]),
        communication=CommunicationDimension(channel_allowlist=["telegram"]),
    )


@pytest.fixture
def vault(principal_id: str, envelope_openai_cli: EnvelopeConfigInput) -> ConnectionVault:
    return ConnectionVault(
        principal_genesis_id=principal_id,
        active_envelope=envelope_openai_cli,
        keyring_backend=_MemBackend(),
    )


# ---------------------------------------------------------------------------
# 1. 11-field schema round-trip
# ---------------------------------------------------------------------------


class TestSchemaRoundTrip:
    def test_credential_entry_dataclass_fields(self) -> None:
        """The Python entry tracks 10 of 11 spec fields; ciphertext lives in keychain."""
        # Per shard 14 § 3.1: the 11-field schema's `ciphertext` is in the OS
        # keychain, not on the Python object. The 10 Python fields are
        # enumerated below.
        expected_fields = {
            "entry_id",
            "principal_genesis_id",
            "credential_type",
            "service_identifier",
            "entry_envelope_scope",
            "created_at",
            "last_used_at",
            "expires_at",
            "usage_counter",
            "rotation_policy",
        }
        actual_fields = {f.name for f in CredentialEntry.__dataclass_fields__.values()}
        assert actual_fields == expected_fields

    def test_credential_entry_is_frozen(self) -> None:
        scope = EnvelopeScopeRef(service_identifier="openai")
        entry = CredentialEntry(
            entry_id=uuid4(),
            principal_genesis_id=_PRINCIPAL_ABC,
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            created_at=datetime.now(timezone.utc),
            last_used_at=datetime.now(timezone.utc),
            expires_at=None,
            usage_counter=0,
        )
        with pytest.raises((AttributeError, Exception)):
            entry.usage_counter = 5  # type: ignore[misc]

    def test_keychain_serialization_round_trip(self) -> None:
        scope = EnvelopeScopeRef(service_identifier="openai", channel="cli")
        original = CredentialEntry(
            entry_id=uuid4(),
            principal_genesis_id=_PRINCIPAL_ABC,
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            created_at=datetime.now(timezone.utc),
            last_used_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=90),
            usage_counter=42,
            rotation_policy=RotationPolicy.QUARTERLY,
        )
        blob = _serialize_record(original, "sk-test-value")
        restored, secret = _deserialize_record(blob)
        assert restored == original
        assert secret == "sk-test-value"

    def test_post_init_rejects_naive_datetimes(self) -> None:
        scope = EnvelopeScopeRef(service_identifier="openai")
        naive = datetime(2026, 1, 1)  # tzinfo=None
        with pytest.raises(ValueError, match="timezone-aware UTC"):
            CredentialEntry(
                entry_id=uuid4(),
                principal_genesis_id=_PRINCIPAL_ABC,
                credential_type=CredentialType.API_KEY,
                service_identifier="openai",
                entry_envelope_scope=scope,
                created_at=naive,
                last_used_at=datetime.now(timezone.utc),
                expires_at=None,
                usage_counter=0,
            )

    def test_post_init_rejects_negative_usage_counter(self) -> None:
        scope = EnvelopeScopeRef(service_identifier="openai")
        with pytest.raises(ValueError, match="usage_counter"):
            CredentialEntry(
                entry_id=uuid4(),
                principal_genesis_id=_PRINCIPAL_ABC,
                credential_type=CredentialType.API_KEY,
                service_identifier="openai",
                entry_envelope_scope=scope,
                created_at=datetime.now(timezone.utc),
                last_used_at=datetime.now(timezone.utc),
                expires_at=None,
                usage_counter=-1,
            )


# ---------------------------------------------------------------------------
# 2. principal_genesis_id key (cross-principal isolation)
# ---------------------------------------------------------------------------


class TestPrincipalIsolation:
    def test_constructor_refuses_empty_principal(
        self, envelope_openai_cli: EnvelopeConfigInput
    ) -> None:
        with pytest.raises(PrincipalRequiredError):
            ConnectionVault(principal_genesis_id="", active_envelope=envelope_openai_cli)

    def test_get_refuses_entry_owned_by_other_principal(
        self, envelope_openai_cli: EnvelopeConfigInput
    ) -> None:
        backend = _MemBackend()
        vault_a = ConnectionVault(
            principal_genesis_id=_PRINCIPAL_A,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        vault_b = ConnectionVault(
            principal_genesis_id=_PRINCIPAL_B,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        scope = EnvelopeScopeRef(service_identifier="openai")
        entry_a = vault_a.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            secret="sk-a",
        )
        from envoy.connection_vault import CrossPrincipalAccessRefusedError

        with pytest.raises(CrossPrincipalAccessRefusedError):
            vault_b.get(entry_a.entry_id)

    def test_delete_refuses_cross_principal(self, envelope_openai_cli: EnvelopeConfigInput) -> None:
        backend = _MemBackend()
        vault_a = ConnectionVault(
            principal_genesis_id=_PRINCIPAL_A,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        vault_b = ConnectionVault(
            principal_genesis_id=_PRINCIPAL_B,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        scope = EnvelopeScopeRef(service_identifier="openai")
        entry_a = vault_a.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            secret="sk-a",
        )
        from envoy.connection_vault import CrossPrincipalAccessRefusedError

        with pytest.raises(CrossPrincipalAccessRefusedError):
            vault_b.delete(entry_a.entry_id)

    def test_list_by_principal_returns_only_own_entries(
        self, envelope_openai_cli: EnvelopeConfigInput
    ) -> None:
        backend = _MemBackend()
        vault_a = ConnectionVault(
            principal_genesis_id=_PRINCIPAL_A,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        vault_b = ConnectionVault(
            principal_genesis_id=_PRINCIPAL_B,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        scope = EnvelopeScopeRef(service_identifier="openai")
        vault_a.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            secret="sk-a",
        )
        vault_a.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="claude",
            entry_envelope_scope=EnvelopeScopeRef(service_identifier="claude"),
            secret="sk-claude",
        )
        vault_b.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            secret="sk-b",
        )
        a_entries = vault_a.list_by_principal()
        b_entries = vault_b.list_by_principal()
        assert len(a_entries) == 2
        assert len(b_entries) == 1
        assert all(e.principal_genesis_id == _PRINCIPAL_A for e in a_entries)
        assert all(e.principal_genesis_id == _PRINCIPAL_B for e in b_entries)


# ---------------------------------------------------------------------------
# 3. Envelope-scope enforcement
# ---------------------------------------------------------------------------


class TestEnvelopeScopeEnforcement:
    def test_get_without_active_envelope_raises(self, principal_id: str) -> None:
        """Fail-closed: vault with no envelope refuses every get."""
        backend = _MemBackend()
        # First write with an envelope, then construct a sibling vault without one
        envelope = EnvelopeConfigInput(
            operational=OperationalDimension(tool_allowlist=["openai"]),
            communication=CommunicationDimension(),
        )
        vault_with = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=envelope,
            keyring_backend=backend,
        )
        scope = EnvelopeScopeRef(service_identifier="openai")
        entry = vault_with.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            secret="sk-test",
        )
        vault_without = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=None,
            keyring_backend=backend,
        )
        with pytest.raises(EnvelopeScopeMismatchError, match="without an active envelope"):
            vault_without.get(entry.entry_id)

    def test_get_with_mismatched_envelope_raises(
        self,
        principal_id: str,
        envelope_openai_cli: EnvelopeConfigInput,
        envelope_telegram: EnvelopeConfigInput,
    ) -> None:
        backend = _MemBackend()
        vault_openai = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        scope = EnvelopeScopeRef(service_identifier="openai")
        entry = vault_openai.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            secret="sk-test",
        )
        # Now switch to a telegram envelope — does NOT contain "openai"
        vault_tg = vault_openai.with_active_envelope(envelope_telegram)
        with pytest.raises(
            EnvelopeScopeMismatchError, match="not included in the active session envelope"
        ):
            vault_tg.get(entry.entry_id)

    def test_with_active_envelope_returns_new_instance(
        self,
        principal_id: str,
        envelope_openai_cli: EnvelopeConfigInput,
        envelope_telegram: EnvelopeConfigInput,
    ) -> None:
        original = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=envelope_openai_cli,
            keyring_backend=_MemBackend(),
        )
        replaced = original.with_active_envelope(envelope_telegram)
        assert replaced is not original
        assert original.active_envelope is envelope_openai_cli
        assert replaced.active_envelope is envelope_telegram


# ---------------------------------------------------------------------------
# 4. Lifecycle: expires_at + usage_counter overflow
# ---------------------------------------------------------------------------


class TestLifecycleEnforcement:
    def test_expired_entry_raises(self, vault: ConnectionVault) -> None:
        scope = EnvelopeScopeRef(service_identifier="openai")
        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        entry = vault.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            secret="sk-stale",
            expires_at=past,
        )
        with pytest.raises(EntryExpiredError):
            vault.get(entry.entry_id)

    def test_naive_expires_at_coerced_to_utc(self, vault: ConnectionVault) -> None:
        scope = EnvelopeScopeRef(service_identifier="openai")
        # Far-future naive datetime — adapter coerces to UTC before storage
        future_naive = datetime(2099, 1, 1)
        entry = vault.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            secret="sk-test",
            expires_at=future_naive,
        )
        assert entry.expires_at is not None
        assert entry.expires_at.tzinfo is not None

    def test_usage_counter_increments_on_each_get(self, vault: ConnectionVault) -> None:
        scope = EnvelopeScopeRef(service_identifier="openai")
        entry = vault.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            secret="sk-test",
        )
        assert entry.usage_counter == 0
        e1, _ = vault.get(entry.entry_id)
        assert e1.usage_counter == 1
        e2, _ = vault.get(entry.entry_id)
        assert e2.usage_counter == 2
        e3, _ = vault.get(entry.entry_id)
        assert e3.usage_counter == 3

    def test_usage_counter_overflow_raises(
        self, principal_id: str, envelope_openai_cli: EnvelopeConfigInput
    ) -> None:
        """Synthesize a record at the ceiling and verify the typed raise."""
        from envoy.connection_vault.adapter import KEYRING_SERVICE_NAMESPACE, _serialize_record

        backend = _MemBackend()
        vault = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        scope = EnvelopeScopeRef(service_identifier="openai")
        # Construct an at-ceiling entry directly and inject it
        entry_id = uuid4()
        ceiling_entry = CredentialEntry(
            entry_id=entry_id,
            principal_genesis_id=principal_id,
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            created_at=datetime.now(timezone.utc),
            last_used_at=datetime.now(timezone.utc),
            expires_at=None,
            usage_counter=USAGE_COUNTER_MAX,
            rotation_policy=RotationPolicy.NEVER,
        )
        backend.set_password(
            KEYRING_SERVICE_NAMESPACE,
            str(entry_id),
            _serialize_record(ceiling_entry, "sk-test"),
        )
        with pytest.raises(UsageCounterOverflowError):
            vault.get(entry_id)


# ---------------------------------------------------------------------------
# 5. Service-identifier validation
# ---------------------------------------------------------------------------


class TestServiceIdentifierValidation:
    @pytest.mark.parametrize(
        "value",
        ["openai", "telegram-bot", "stripe.webhook", "a.b_c-d", "openai-2"],
    )
    def test_accepts_canonical(self, value: str) -> None:
        validate_service_identifier(value)  # no raise

    @pytest.mark.parametrize(
        "value,reason",
        [
            ("", "non-empty"),
            ("Openai", "lower-case"),  # uppercase
            ("openai api", "lower-case"),  # space
            ("openai/key", "lower-case"),  # slash
            ("openai$", "lower-case"),  # special char
            ("a" * 257, "256 chars"),
        ],
    )
    def test_rejects_invalid(self, value: str, reason: str) -> None:
        with pytest.raises(InvalidServiceIdentifierError):
            validate_service_identifier(value)

    def test_set_rejects_invalid_service_identifier(self, vault: ConnectionVault) -> None:
        scope = EnvelopeScopeRef(service_identifier="openai")
        with pytest.raises(InvalidServiceIdentifierError):
            vault.set(
                credential_type=CredentialType.API_KEY,
                service_identifier="OPENAI",  # uppercase
                entry_envelope_scope=scope,
                secret="sk-test",
            )


# ---------------------------------------------------------------------------
# 6. Keychain availability
# ---------------------------------------------------------------------------


class TestKeychainAvailability:
    def test_is_available_returns_true_on_mem_backend(self, vault: ConnectionVault) -> None:
        assert vault.is_available() is True

    def test_is_available_returns_false_on_failing_backend(
        self, principal_id: str, envelope_openai_cli: EnvelopeConfigInput
    ) -> None:
        vault = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=envelope_openai_cli,
            keyring_backend=_FailingBackend(),
        )
        assert vault.is_available() is False

    def test_set_translates_keyring_error_to_typed(
        self, principal_id: str, envelope_openai_cli: EnvelopeConfigInput
    ) -> None:
        vault = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=envelope_openai_cli,
            keyring_backend=_FailingBackend(),
        )
        scope = EnvelopeScopeRef(service_identifier="openai")
        with pytest.raises(KeychainUnavailableError):
            vault.set(
                credential_type=CredentialType.API_KEY,
                service_identifier="openai",
                entry_envelope_scope=scope,
                secret="sk-test",
            )


# ---------------------------------------------------------------------------
# 7. delete + EntryNotFoundError
# ---------------------------------------------------------------------------


class TestDelete:
    def test_delete_removes_entry(self, vault: ConnectionVault) -> None:
        scope = EnvelopeScopeRef(service_identifier="openai")
        entry = vault.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            secret="sk-test",
        )
        vault.delete(entry.entry_id)
        with pytest.raises(EntryNotFoundError):
            vault.get(entry.entry_id)

    def test_delete_unknown_raises(self, vault: ConnectionVault) -> None:
        with pytest.raises(EntryNotFoundError):
            vault.delete(uuid4())

    def test_get_unknown_raises(self, vault: ConnectionVault) -> None:
        with pytest.raises(EntryNotFoundError):
            vault.get(uuid4())

    def test_delete_updates_index(self, vault: ConnectionVault) -> None:
        scope = EnvelopeScopeRef(service_identifier="openai")
        e1 = vault.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            secret="sk1",
        )
        e2 = vault.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="claude",
            entry_envelope_scope=EnvelopeScopeRef(service_identifier="claude"),
            secret="sk2",
        )
        assert len(vault.list_by_principal()) == 2
        vault.delete(e1.entry_id)
        listed = vault.list_by_principal()
        assert len(listed) == 1
        assert listed[0].entry_id == e2.entry_id


# ---------------------------------------------------------------------------
# 8. .env first-run import
# ---------------------------------------------------------------------------


class TestEnvImport:
    def test_import_writes_set_env_vars(
        self,
        vault: ConnectionVault,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ENVOY_TEST_OPENAI_KEY", "sk-openai-from-env")
        monkeypatch.setenv("ENVOY_TEST_CLAUDE_KEY", "sk-claude-from-env")
        scope_openai = EnvelopeScopeRef(service_identifier="openai")
        scope_claude = EnvelopeScopeRef(service_identifier="claude")
        result = import_credentials_from_env(
            vault,
            (
                EnvCredentialSpec(
                    env_var_name="ENVOY_TEST_OPENAI_KEY",
                    credential_type=CredentialType.API_KEY,
                    service_identifier="openai",
                    entry_envelope_scope=scope_openai,
                ),
                EnvCredentialSpec(
                    env_var_name="ENVOY_TEST_CLAUDE_KEY",
                    credential_type=CredentialType.API_KEY,
                    service_identifier="claude",
                    entry_envelope_scope=scope_claude,
                ),
            ),
        )
        assert result.imported_env_var_names == ("ENVOY_TEST_OPENAI_KEY", "ENVOY_TEST_CLAUDE_KEY")
        assert result.skipped_env_var_names == ()
        assert len(result.entry_ids) == 2

    def test_import_skips_unset_env_vars(
        self,
        vault: ConnectionVault,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("ENVOY_TEST_MISSING_KEY", raising=False)
        scope = EnvelopeScopeRef(service_identifier="openai")
        result = import_credentials_from_env(
            vault,
            (
                EnvCredentialSpec(
                    env_var_name="ENVOY_TEST_MISSING_KEY",
                    credential_type=CredentialType.API_KEY,
                    service_identifier="openai",
                    entry_envelope_scope=scope,
                ),
            ),
        )
        assert result.imported_env_var_names == ()
        assert result.skipped_env_var_names == ("ENVOY_TEST_MISSING_KEY",)

    def test_import_skips_empty_env_vars(
        self,
        vault: ConnectionVault,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Empty string is treated as unset per the helper contract."""
        monkeypatch.setenv("ENVOY_TEST_EMPTY_KEY", "   ")  # whitespace only
        scope = EnvelopeScopeRef(service_identifier="openai")
        result = import_credentials_from_env(
            vault,
            (
                EnvCredentialSpec(
                    env_var_name="ENVOY_TEST_EMPTY_KEY",
                    credential_type=CredentialType.API_KEY,
                    service_identifier="openai",
                    entry_envelope_scope=scope,
                ),
            ),
        )
        assert result.skipped_env_var_names == ("ENVOY_TEST_EMPTY_KEY",)

    def test_imported_credential_retrievable_via_vault(
        self,
        vault: ConnectionVault,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ENVOY_TEST_ROUND_TRIP_KEY", "sk-round-trip-value")
        scope = EnvelopeScopeRef(service_identifier="openai")
        result = import_credentials_from_env(
            vault,
            (
                EnvCredentialSpec(
                    env_var_name="ENVOY_TEST_ROUND_TRIP_KEY",
                    credential_type=CredentialType.API_KEY,
                    service_identifier="openai",
                    entry_envelope_scope=scope,
                ),
            ),
        )
        assert len(result.entry_ids) == 1
        entry_id = UUID(result.entry_ids[0])
        retrieved, secret = vault.get(entry_id)
        assert secret == "sk-round-trip-value"
        assert retrieved.service_identifier == "openai"


# ---------------------------------------------------------------------------
# 9. Secret never leaks to the entry's repr (PII-adjacency defense)
# ---------------------------------------------------------------------------


class TestSecretIsolation:
    def test_credential_entry_repr_does_not_include_secret(self) -> None:
        """The Python entry tracks 10 fields; the secret lives in keychain only."""
        scope = EnvelopeScopeRef(service_identifier="openai")
        entry = CredentialEntry(
            entry_id=uuid4(),
            principal_genesis_id=_PRINCIPAL_ABC,
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            created_at=datetime.now(timezone.utc),
            last_used_at=datetime.now(timezone.utc),
            expires_at=None,
            usage_counter=0,
        )
        # The dataclass has no `secret` field → repr can't include it.
        assert "secret" not in repr(entry).lower()
        assert "sk-" not in repr(entry).lower()


# ---------------------------------------------------------------------------
# 10. principal_genesis_id sha256-hex validation (security-reviewer M3)
# ---------------------------------------------------------------------------


class TestPrincipalGenesisIdValidation:
    """Per security-reviewer M3 (2026-05-24): principal_genesis_id MUST match
    `^[0-9a-f]{64}$` so the keychain key namespace cannot be collision-injected
    via colons / control chars / newlines."""

    def test_accepts_sha256_hex(self) -> None:
        validate_principal_genesis_id(_PRINCIPAL_ALPHA)  # no raise

    @pytest.mark.parametrize(
        "bad,reason",
        [
            ("", "empty"),
            ("principal-A", "wrong shape"),
            ("a" * 63, "too short"),
            ("a" * 65, "too long"),
            ("A" * 64, "uppercase rejected"),
            ("g" * 64, "non-hex char"),
            ("a" * 60 + ":abc", "colon injection (keychain key collision)"),
            ("a" * 60 + "\n123", "newline injection"),
            ("a" * 60 + "\x00abc", "null-byte injection"),
        ],
    )
    def test_rejects_invalid(self, bad: str, reason: str) -> None:
        with pytest.raises(PrincipalRequiredError):
            validate_principal_genesis_id(bad)

    def test_constructor_uses_full_validator(
        self, envelope_openai_cli: EnvelopeConfigInput
    ) -> None:
        """ConnectionVault __init__ delegates to validate_principal_genesis_id."""
        with pytest.raises(PrincipalRequiredError, match="sha256-hex shape"):
            ConnectionVault(
                principal_genesis_id="principal-not-hex",
                active_envelope=envelope_openai_cli,
                keyring_backend=_MemBackend(),
            )

    def test_credential_entry_post_init_uses_full_validator(self) -> None:
        """Dataclass post_init applies the same sha256-hex check."""
        scope = EnvelopeScopeRef(service_identifier="openai")
        with pytest.raises(PrincipalRequiredError, match="sha256-hex shape"):
            CredentialEntry(
                entry_id=uuid4(),
                principal_genesis_id="not-hex",
                credential_type=CredentialType.API_KEY,
                service_identifier="openai",
                entry_envelope_scope=scope,
                created_at=datetime.now(timezone.utc),
                last_used_at=datetime.now(timezone.utc),
                expires_at=None,
                usage_counter=0,
            )


# ---------------------------------------------------------------------------
# 11. Corrupted record / index typed raises (security-reviewer M2)
# ---------------------------------------------------------------------------


class TestCorruptedRecord:
    """Per security-reviewer M2 (2026-05-24): malformed JSON / missing keys /
    wrong types translate to typed CorruptedRecordError — NOT raw stdlib
    exceptions."""

    def test_malformed_json_raises_typed(self) -> None:
        from envoy.connection_vault.adapter import _deserialize_record

        with pytest.raises(CorruptedRecordError, match="JSON decode failed"):
            _deserialize_record("{not valid json")

    def test_non_object_top_level_raises_typed(self) -> None:
        from envoy.connection_vault.adapter import _deserialize_record

        with pytest.raises(CorruptedRecordError, match="top-level must be JSON object"):
            _deserialize_record('["list", "not", "object"]')

    def test_missing_required_key_raises_typed(self) -> None:
        from envoy.connection_vault.adapter import _deserialize_record

        # Missing entry_id — should raise CorruptedRecordError, not KeyError
        import json as _json

        malformed = _json.dumps(
            {
                "schema_version": 1,
                "principal_genesis_id": _PRINCIPAL_ABC,
                "credential_type": "api_key",
                "service_identifier": "openai",
                "entry_envelope_scope": {"service_identifier": "openai", "channel": None},
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_used_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": None,
                "usage_counter": 0,
                "rotation_policy": "never",
                "secret": "sk-test",
                # entry_id intentionally omitted
            }
        )
        with pytest.raises(CorruptedRecordError, match="shape invalid"):
            _deserialize_record(malformed)

    def test_secret_field_wrong_type_raises_typed(self) -> None:
        from envoy.connection_vault.adapter import _deserialize_record

        import json as _json

        malformed = _json.dumps(
            {
                "schema_version": 1,
                "entry_id": str(uuid4()),
                "principal_genesis_id": _PRINCIPAL_ABC,
                "credential_type": "api_key",
                "service_identifier": "openai",
                "entry_envelope_scope": {"service_identifier": "openai", "channel": None},
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_used_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": None,
                "usage_counter": 0,
                "rotation_policy": "never",
                "secret": 12345,  # wrong type — should be str
            }
        )
        with pytest.raises(CorruptedRecordError, match="`secret` must be str"):
            _deserialize_record(malformed)

    def test_unknown_schema_version_raises_typed(self) -> None:
        from envoy.connection_vault.adapter import _deserialize_record

        import json as _json

        malformed = _json.dumps({"schema_version": 999, "anything": "else"})
        with pytest.raises(RecordSchemaVersionError, match="unsupported"):
            _deserialize_record(malformed)

    def test_malformed_index_raises_typed(
        self, principal_id: str, envelope_openai_cli: EnvelopeConfigInput
    ) -> None:
        """A tampered index payload raises CorruptedRecordError, not raw JSONDecodeError."""
        from envoy.connection_vault.adapter import KEYRING_SERVICE_NAMESPACE

        backend = _MemBackend()
        vault = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        # Inject a malformed index entry directly
        backend.set_password(KEYRING_SERVICE_NAMESPACE, f"__index__:{principal_id}", "{not json")
        with pytest.raises(CorruptedRecordError, match="index JSON decode failed"):
            vault.list_by_principal()

    def test_non_list_index_raises_typed(
        self, principal_id: str, envelope_openai_cli: EnvelopeConfigInput
    ) -> None:
        from envoy.connection_vault.adapter import KEYRING_SERVICE_NAMESPACE

        backend = _MemBackend()
        vault = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        backend.set_password(
            KEYRING_SERVICE_NAMESPACE,
            f"__index__:{principal_id}",
            '{"not": "list"}',
        )
        with pytest.raises(CorruptedRecordError, match="index payload must be JSON list"):
            vault.list_by_principal()

    def test_index_with_non_uuid_entries_raises_typed(
        self, principal_id: str, envelope_openai_cli: EnvelopeConfigInput
    ) -> None:
        from envoy.connection_vault.adapter import KEYRING_SERVICE_NAMESPACE

        backend = _MemBackend()
        vault = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        backend.set_password(
            KEYRING_SERVICE_NAMESPACE,
            f"__index__:{principal_id}",
            '["not-a-uuid", "also-not-a-uuid"]',
        )
        with pytest.raises(CorruptedRecordError, match="non-UUID entries"):
            vault.list_by_principal()


# ---------------------------------------------------------------------------
# 12. RecordSchemaVersionError vs EntryNotFoundError (code-reviewer MED-1)
# ---------------------------------------------------------------------------


class TestSchemaVersionMismatch:
    """Per code-reviewer MED-1 (2026-05-24): a record with an unsupported
    schema_version MUST raise RecordSchemaVersionError, NOT EntryNotFoundError.
    The entry IS present — it's at a version this Envoy build can't parse."""

    def test_get_on_future_version_raises_schema_version_error(
        self, principal_id: str, envelope_openai_cli: EnvelopeConfigInput
    ) -> None:
        from envoy.connection_vault.adapter import KEYRING_SERVICE_NAMESPACE

        import json as _json

        backend = _MemBackend()
        vault = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        future_entry_id = uuid4()
        backend.set_password(
            KEYRING_SERVICE_NAMESPACE,
            str(future_entry_id),
            _json.dumps({"schema_version": 999, "future_field": "data"}),
        )
        with pytest.raises(RecordSchemaVersionError, match="upgrade Envoy"):
            vault.get(future_entry_id)

    def test_schema_version_error_is_distinct_from_entry_not_found(
        self, principal_id: str, envelope_openai_cli: EnvelopeConfigInput
    ) -> None:
        """The two errors carry distinct user-action contracts and MUST not collapse."""
        from envoy.connection_vault import (
            ConnectionVaultError,
            EntryNotFoundError as _Missing,
            RecordSchemaVersionError as _Version,
        )

        assert issubclass(_Missing, ConnectionVaultError)
        assert issubclass(_Version, ConnectionVaultError)
        assert _Missing is not _Version
        assert not issubclass(_Missing, _Version)
        assert not issubclass(_Version, _Missing)


# ---------------------------------------------------------------------------
# 13. Observability: get/delete/list_by_principal emit structured logs
#     (code-reviewer MED-4)
# ---------------------------------------------------------------------------


class TestObservability:
    """Per code-reviewer MED-4 (2026-05-24): cross-keychain-boundary ops MUST
    emit start/ok structured logs + warning on every typed-error path."""

    def test_get_emits_start_and_ok(
        self, vault: ConnectionVault, caplog: pytest.LogCaptureFixture
    ) -> None:

        scope = EnvelopeScopeRef(service_identifier="openai")
        entry = vault.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            secret="sk-observ",
        )
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="envoy.connection_vault"):
            vault.get(entry.entry_id)
        log_msgs = [r.message for r in caplog.records]
        assert any("connection_vault.get.start" in m for m in log_msgs)
        assert any("connection_vault.get.ok" in m for m in log_msgs)

    def test_get_emits_warning_on_entry_not_found(
        self, vault: ConnectionVault, caplog: pytest.LogCaptureFixture
    ) -> None:

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="envoy.connection_vault"):
            with pytest.raises(EntryNotFoundError):
                vault.get(uuid4())
        warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert any("connection_vault.get.error" in r.message for r in warning_records)
        assert any(getattr(r, "reason", None) == "entry_not_found" for r in warning_records)

    def test_delete_emits_start_and_ok(
        self, vault: ConnectionVault, caplog: pytest.LogCaptureFixture
    ) -> None:

        scope = EnvelopeScopeRef(service_identifier="openai")
        entry = vault.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            secret="sk-del-observ",
        )
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="envoy.connection_vault"):
            vault.delete(entry.entry_id)
        log_msgs = [r.message for r in caplog.records]
        assert any("connection_vault.delete.start" in m for m in log_msgs)
        assert any("connection_vault.delete.ok" in m for m in log_msgs)

    def test_list_by_principal_emits_start_and_ok(
        self, vault: ConnectionVault, caplog: pytest.LogCaptureFixture
    ) -> None:

        caplog.clear()
        with caplog.at_level(logging.INFO, logger="envoy.connection_vault"):
            vault.list_by_principal()
        log_msgs = [r.message for r in caplog.records]
        assert any("connection_vault.list_by_principal.start" in m for m in log_msgs)
        assert any("connection_vault.list_by_principal.ok" in m for m in log_msgs)

    def test_log_lines_do_not_contain_raw_principal_id(
        self, vault: ConnectionVault, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Per `rules/observability.md` Rule 8: schema-revealing identifiers
        at WARN/INFO MUST be hashed-prefix only, not raw."""

        scope = EnvelopeScopeRef(service_identifier="openai")
        with caplog.at_level(logging.INFO, logger="envoy.connection_vault"):
            vault.set(
                credential_type=CredentialType.API_KEY,
                service_identifier="openai",
                entry_envelope_scope=scope,
                secret="sk-raw-id-check",
            )
        for record in caplog.records:
            # The full 64-char principal id MUST NOT appear in any log line
            assert _PRINCIPAL_ALPHA not in record.getMessage()
            for value in record.__dict__.values():
                if isinstance(value, str):
                    assert _PRINCIPAL_ALPHA not in value


# ---------------------------------------------------------------------------
# 14. env_import skip-reason granularity (security-reviewer L3)
# ---------------------------------------------------------------------------


class TestEnvImportSkipReason:
    """Per security-reviewer L3 (2026-05-24): distinguish `unset` from
    `empty_after_strip` so operators can debug `.env` problems."""

    def test_unset_emits_unset_reason(
        self,
        vault: ConnectionVault,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:

        monkeypatch.delenv("ENVOY_TEST_GRANULAR_UNSET", raising=False)
        scope = EnvelopeScopeRef(service_identifier="openai")
        with caplog.at_level(logging.INFO, logger="envoy.connection_vault.env_import"):
            import_credentials_from_env(
                vault,
                (
                    EnvCredentialSpec(
                        env_var_name="ENVOY_TEST_GRANULAR_UNSET",
                        credential_type=CredentialType.API_KEY,
                        service_identifier="openai",
                        entry_envelope_scope=scope,
                    ),
                ),
            )
        assert any(getattr(r, "reason", None) == "unset" for r in caplog.records)

    def test_whitespace_emits_empty_after_strip_reason(
        self,
        vault: ConnectionVault,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:

        monkeypatch.setenv("ENVOY_TEST_GRANULAR_EMPTY", "   ")
        scope = EnvelopeScopeRef(service_identifier="openai")
        with caplog.at_level(logging.INFO, logger="envoy.connection_vault.env_import"):
            import_credentials_from_env(
                vault,
                (
                    EnvCredentialSpec(
                        env_var_name="ENVOY_TEST_GRANULAR_EMPTY",
                        credential_type=CredentialType.API_KEY,
                        service_identifier="openai",
                        entry_envelope_scope=scope,
                    ),
                ),
            )
        assert any(getattr(r, "reason", None) == "empty_after_strip" for r in caplog.records)


# ---------------------------------------------------------------------------
# 15. Round 1 /redteam — typed-taxonomy completeness (R1-F2 + R1-F5)
# ---------------------------------------------------------------------------


class TestCorruptedRecordValidatorLeakClosed:
    """Per R1-F2 (2026-05-24): a tampered keychain payload with a malformed
    principal_genesis_id or service_identifier triggers PrincipalRequiredError /
    InvalidServiceIdentifierError inside CredentialEntry.__post_init__.
    Without the explicit catch in _deserialize_record those validator errors
    leak past the CorruptedRecordError contract the spec § Change log
    advertises. These regressions pin the wrap.
    """

    def _make_payload(self, **overrides) -> str:
        import json as _json

        defaults = {
            "schema_version": 1,
            "entry_id": str(uuid4()),
            "principal_genesis_id": _PRINCIPAL_ABC,
            "credential_type": "api_key",
            "service_identifier": "openai",
            "entry_envelope_scope": {
                "service_identifier": "openai",
                "channel": None,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_used_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": None,
            "usage_counter": 0,
            "rotation_policy": "never",
            "secret": "sk-test",
        }
        defaults.update(overrides)
        return _json.dumps(defaults)

    def test_malformed_principal_in_payload_raises_corrupted_not_principal_required(
        self,
    ) -> None:
        from envoy.connection_vault.adapter import _deserialize_record

        blob = self._make_payload(principal_genesis_id="not-sha256-hex")
        with pytest.raises(CorruptedRecordError, match="validator-rejected"):
            _deserialize_record(blob)
        # Negative assertion: the leak path is closed
        try:
            _deserialize_record(blob)
        except PrincipalRequiredError:
            pytest.fail("PrincipalRequiredError leaked past CorruptedRecordError wrap")
        except CorruptedRecordError:
            pass

    def test_malformed_service_in_payload_raises_corrupted_not_invalid_service(
        self,
    ) -> None:
        from envoy.connection_vault.adapter import _deserialize_record

        blob = self._make_payload(service_identifier="UPPERCASE-rejected")
        with pytest.raises(CorruptedRecordError, match="validator-rejected"):
            _deserialize_record(blob)
        try:
            _deserialize_record(blob)
        except InvalidServiceIdentifierError:
            pytest.fail("InvalidServiceIdentifierError leaked past CorruptedRecordError wrap")
        except CorruptedRecordError:
            pass

    def test_scope_service_identifier_wrong_type_raises_corrupted(self) -> None:
        """Per R1-F5: tampered scope_payload['service_identifier'] must raise typed."""
        from envoy.connection_vault.adapter import _deserialize_record

        blob = self._make_payload(
            entry_envelope_scope={"service_identifier": 12345, "channel": None},
        )
        with pytest.raises(CorruptedRecordError, match="service_identifier must be str"):
            _deserialize_record(blob)

    def test_scope_channel_wrong_type_raises_corrupted(self) -> None:
        """Per R1-F5: tampered scope_payload['channel'] must raise typed."""
        from envoy.connection_vault.adapter import _deserialize_record

        blob = self._make_payload(
            entry_envelope_scope={"service_identifier": "openai", "channel": 99},
        )
        with pytest.raises(CorruptedRecordError, match="channel must be str or null"):
            _deserialize_record(blob)


# ---------------------------------------------------------------------------
# 16. Round 1 /redteam — denylist enforcement (R1-F4)
# ---------------------------------------------------------------------------


class TestEnvelopeScopeDenylistVeto:
    """Per R1-F4 (2026-05-24): `envelope_contains_scope` MUST honor
    operational.tool_denylist AND communication.channel_denylist. The
    deny axis is the structural defense against template-import override
    scenarios where a sibling envelope library re-allows a denied tool.
    Per /redteam R2-H1 (2026-05-24): channel-axis deny is `channel_denylist`,
    NOT `recipient_denylist` (which gates recipient ENTITIES, not transports).
    """

    def test_tool_denylist_vetoes_even_when_in_allowlist(self) -> None:
        from envoy.envelope import envelope_contains_scope

        env = EnvelopeConfigInput(
            operational=OperationalDimension(
                tool_allowlist=["openai", "claude"],
                tool_denylist=["openai"],  # explicit deny dominates
            ),
            communication=CommunicationDimension(channel_allowlist=["cli"]),
        )
        scope = EnvelopeScopeRef(service_identifier="openai")
        assert envelope_contains_scope(env, scope) is False

    def test_channel_denylist_vetoes_channel_even_when_in_allowlist(self) -> None:
        """Per /redteam R2-H1: channel_denylist (transport axis) is the
        correct deny-veto for the communication channel."""
        from envoy.envelope import envelope_contains_scope

        env = EnvelopeConfigInput(
            operational=OperationalDimension(tool_allowlist=["telegram-bot"]),
            communication=CommunicationDimension(
                channel_allowlist=["telegram", "slack"],
                channel_denylist=["telegram"],  # explicit deny on transport axis
            ),
        )
        scope = EnvelopeScopeRef(service_identifier="telegram-bot", channel="telegram")
        assert envelope_contains_scope(env, scope) is False

    def test_recipient_denylist_does_NOT_veto_channel(self) -> None:
        """Per /redteam R2-H1: recipient_denylist gates RECIPIENTS, NOT
        channel transports. A telegram channel allow-listed must pass even
        if a recipient name "telegram" appears in recipient_denylist —
        these are separate semantic axes."""
        from envoy.envelope import envelope_contains_scope

        env = EnvelopeConfigInput(
            operational=OperationalDimension(tool_allowlist=["telegram-bot"]),
            communication=CommunicationDimension(
                channel_allowlist=["telegram"],
                recipient_denylist=["telegram"],  # different axis; must NOT veto channel
            ),
        )
        scope = EnvelopeScopeRef(service_identifier="telegram-bot", channel="telegram")
        assert envelope_contains_scope(env, scope) is True

    def test_allow_without_deny_still_returns_true(self) -> None:
        """Sanity: the new code path must not regress the existing allow-list test."""
        from envoy.envelope import envelope_contains_scope

        env = EnvelopeConfigInput(
            operational=OperationalDimension(tool_allowlist=["openai"], tool_denylist=["claude"]),
            communication=CommunicationDimension(),
        )
        scope = EnvelopeScopeRef(service_identifier="openai")
        assert envelope_contains_scope(env, scope) is True

    def test_denylist_takes_precedence_when_both_lists_share_entry(self) -> None:
        """Deny-veto ordering test: deny check runs BEFORE allow check."""
        from envoy.envelope import envelope_contains_scope

        env = EnvelopeConfigInput(
            operational=OperationalDimension(tool_allowlist=["openai"], tool_denylist=["openai"]),
            communication=CommunicationDimension(),
        )
        scope = EnvelopeScopeRef(service_identifier="openai")
        assert envelope_contains_scope(env, scope) is False


# ---------------------------------------------------------------------------
# 17. Round 1 /redteam — symmetric set/list error logs (R1-F1 + R1-F7)
# ---------------------------------------------------------------------------


class TestSetErrorObservability:
    """Per R1-F1: every typed-error raise on the set path must emit a warning
    log symmetric with the get/delete paths. Per R1-F7: each branch needs
    explicit coverage."""

    def test_set_emits_start_and_ok(
        self, vault: ConnectionVault, caplog: pytest.LogCaptureFixture
    ) -> None:

        scope = EnvelopeScopeRef(service_identifier="openai")
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="envoy.connection_vault"):
            vault.set(
                credential_type=CredentialType.API_KEY,
                service_identifier="openai",
                entry_envelope_scope=scope,
                secret="sk-set-observ",
            )
        msgs = [r.message for r in caplog.records]
        assert any("connection_vault.set.start" in m for m in msgs)
        assert any("connection_vault.set.ok" in m for m in msgs)

    def test_set_emits_warning_on_invalid_service_identifier(
        self, vault: ConnectionVault, caplog: pytest.LogCaptureFixture
    ) -> None:

        scope = EnvelopeScopeRef(service_identifier="openai")
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="envoy.connection_vault"):
            with pytest.raises(InvalidServiceIdentifierError):
                vault.set(
                    credential_type=CredentialType.API_KEY,
                    service_identifier="UPPERCASE-rejected",
                    entry_envelope_scope=scope,
                    secret="sk-test",
                )
        warns = [r for r in caplog.records if r.levelname == "WARNING"]
        assert any(getattr(r, "reason", None) == "invalid_service_identifier" for r in warns)

    def test_set_emits_warning_on_keychain_unavailable(
        self,
        principal_id: str,
        envelope_openai_cli: EnvelopeConfigInput,
        caplog: pytest.LogCaptureFixture,
    ) -> None:

        vault = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=envelope_openai_cli,
            keyring_backend=_FailingBackend(),
        )
        scope = EnvelopeScopeRef(service_identifier="openai")
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="envoy.connection_vault"):
            with pytest.raises(KeychainUnavailableError):
                vault.set(
                    credential_type=CredentialType.API_KEY,
                    service_identifier="openai",
                    entry_envelope_scope=scope,
                    secret="sk-test",
                )
        warns = [r for r in caplog.records if r.levelname == "WARNING"]
        assert any(getattr(r, "reason", None) == "keychain_unavailable" for r in warns)


class TestListByPrincipalErrorObservability:
    """Per R1-F1: list_by_principal must emit error logs on read failures."""

    def test_list_emits_warning_on_corrupted_index(
        self,
        principal_id: str,
        envelope_openai_cli: EnvelopeConfigInput,
        caplog: pytest.LogCaptureFixture,
    ) -> None:

        from envoy.connection_vault.adapter import KEYRING_SERVICE_NAMESPACE

        backend = _MemBackend()
        vault = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        backend.set_password(KEYRING_SERVICE_NAMESPACE, f"__index__:{principal_id}", "{not json")
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="envoy.connection_vault"):
            with pytest.raises(CorruptedRecordError):
                vault.list_by_principal()
        warns = [r for r in caplog.records if r.levelname == "WARNING"]
        assert any(getattr(r, "reason", None) == "corrupted_index" for r in warns)

    def test_list_emits_warning_on_stale_index_entries(
        self,
        principal_id: str,
        envelope_openai_cli: EnvelopeConfigInput,
        caplog: pytest.LogCaptureFixture,
    ) -> None:

        from envoy.connection_vault.adapter import KEYRING_SERVICE_NAMESPACE

        backend = _MemBackend()
        vault = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        # Inject a stale entry_id into the index — the entry itself is absent
        ghost_id = uuid4()
        import json as _json

        backend.set_password(
            KEYRING_SERVICE_NAMESPACE,
            f"__index__:{principal_id}",
            _json.dumps([str(ghost_id)]),
        )
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="envoy.connection_vault"):
            result = vault.list_by_principal()
        assert result == ()
        warns = [r for r in caplog.records if r.levelname == "WARNING"]
        assert any(
            "stale_index_entries" in r.message for r in warns
        ), "expected stale_index_entries warning"


class TestGetErrorObservabilityBranches:
    """Per R1-F7: assert every reason name in the get() error taxonomy."""

    def _setup_with_entry(
        self,
        principal_id: str,
        envelope_openai_cli: EnvelopeConfigInput,
        expires_at=None,
    ):
        """Helper: build a vault, set one entry, return (vault, entry, backend)."""
        backend = _MemBackend()
        vault = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        scope = EnvelopeScopeRef(service_identifier="openai")
        entry = vault.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            secret="sk-test",
            expires_at=expires_at,
        )
        return vault, entry, backend

    def test_get_no_active_envelope_logs_reason(
        self,
        principal_id: str,
        envelope_openai_cli: EnvelopeConfigInput,
        caplog: pytest.LogCaptureFixture,
    ) -> None:

        vault, entry, _backend = self._setup_with_entry(principal_id, envelope_openai_cli)
        vault_no_env = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=None,
            keyring_backend=_backend,
        )
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="envoy.connection_vault"):
            with pytest.raises(EnvelopeScopeMismatchError):
                vault_no_env.get(entry.entry_id)
        warns = [r for r in caplog.records if r.levelname == "WARNING"]
        assert any(getattr(r, "reason", None) == "no_active_envelope" for r in warns)

    def test_get_envelope_scope_mismatch_logs_reason(
        self,
        principal_id: str,
        envelope_openai_cli: EnvelopeConfigInput,
        envelope_telegram: EnvelopeConfigInput,
        caplog: pytest.LogCaptureFixture,
    ) -> None:

        vault, entry, _backend = self._setup_with_entry(principal_id, envelope_openai_cli)
        vault_tg = vault.with_active_envelope(envelope_telegram)
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="envoy.connection_vault"):
            with pytest.raises(EnvelopeScopeMismatchError):
                vault_tg.get(entry.entry_id)
        warns = [r for r in caplog.records if r.levelname == "WARNING"]
        assert any(getattr(r, "reason", None) == "envelope_scope_mismatch" for r in warns)

    def test_get_entry_expired_logs_reason(
        self,
        principal_id: str,
        envelope_openai_cli: EnvelopeConfigInput,
        caplog: pytest.LogCaptureFixture,
    ) -> None:

        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        vault, entry, _backend = self._setup_with_entry(
            principal_id, envelope_openai_cli, expires_at=past
        )
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="envoy.connection_vault"):
            with pytest.raises(EntryExpiredError):
                vault.get(entry.entry_id)
        warns = [r for r in caplog.records if r.levelname == "WARNING"]
        assert any(getattr(r, "reason", None) == "entry_expired" for r in warns)

    def test_get_cross_principal_logs_reason(
        self,
        envelope_openai_cli: EnvelopeConfigInput,
        caplog: pytest.LogCaptureFixture,
    ) -> None:

        backend = _MemBackend()
        vault_a = ConnectionVault(
            principal_genesis_id=_PRINCIPAL_A,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        vault_b = ConnectionVault(
            principal_genesis_id=_PRINCIPAL_B,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        scope = EnvelopeScopeRef(service_identifier="openai")
        entry_a = vault_a.set(
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            secret="sk-a",
        )
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="envoy.connection_vault"):
            from envoy.connection_vault import CrossPrincipalAccessRefusedError

            with pytest.raises(CrossPrincipalAccessRefusedError):
                vault_b.get(entry_a.entry_id)
        warns = [r for r in caplog.records if r.levelname == "WARNING"]
        assert any(getattr(r, "reason", None) == "cross_principal_refused" for r in warns)

    def test_get_usage_counter_overflow_logs_reason(
        self,
        principal_id: str,
        envelope_openai_cli: EnvelopeConfigInput,
        caplog: pytest.LogCaptureFixture,
    ) -> None:

        from envoy.connection_vault.adapter import (
            KEYRING_SERVICE_NAMESPACE,
            _serialize_record,
        )

        backend = _MemBackend()
        vault = ConnectionVault(
            principal_genesis_id=principal_id,
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        scope = EnvelopeScopeRef(service_identifier="openai")
        eid = uuid4()
        ceiling_entry = CredentialEntry(
            entry_id=eid,
            principal_genesis_id=principal_id,
            credential_type=CredentialType.API_KEY,
            service_identifier="openai",
            entry_envelope_scope=scope,
            created_at=datetime.now(timezone.utc),
            last_used_at=datetime.now(timezone.utc),
            expires_at=None,
            usage_counter=USAGE_COUNTER_MAX,
            rotation_policy=RotationPolicy.NEVER,
        )
        backend.set_password(
            KEYRING_SERVICE_NAMESPACE,
            str(eid),
            _serialize_record(ceiling_entry, "sk-overflow"),
        )
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="envoy.connection_vault"):
            with pytest.raises(UsageCounterOverflowError):
                vault.get(eid)
        warns = [r for r in caplog.records if r.levelname == "WARNING"]
        assert any(getattr(r, "reason", None) == "usage_counter_overflow" for r in warns)


# ---------------------------------------------------------------------------
# 18. Round 1 /redteam — R1-F6: ActiveEnvelope facade export consistency
# ---------------------------------------------------------------------------


class TestActiveEnvelopeExportConsistency:
    def test_active_envelope_not_in_connection_vault_all(self) -> None:
        """Per R1-F6: ActiveEnvelope's canonical home is envoy.envelope, not
        envoy.connection_vault. Listing it in either module's __all__ creates
        import-path drift."""
        import envoy.connection_vault as cv
        import envoy.connection_vault.adapter as adapter

        assert "ActiveEnvelope" not in cv.__all__
        assert "ActiveEnvelope" not in adapter.__all__

    def test_active_envelope_is_in_envelope_all(self) -> None:
        import envoy.envelope as env

        assert "ActiveEnvelope" in env.__all__
