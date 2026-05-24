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

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import keyring.errors
import pytest

from envoy.connection_vault import (
    USAGE_COUNTER_MAX,
    ConnectionVault,
    CredentialType,
    EnvCredentialSpec,
    EntryExpiredError,
    EntryNotFoundError,
    EnvelopeScopeMismatchError,
    InvalidServiceIdentifierError,
    KeychainUnavailableError,
    PrincipalRequiredError,
    RotationPolicy,
    UsageCounterOverflowError,
    import_credentials_from_env,
    validate_service_identifier,
)
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
            principal_genesis_id="abc",
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
            principal_genesis_id="abc123",
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
                principal_genesis_id="abc",
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
                principal_genesis_id="abc",
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
            principal_genesis_id="principal-A",
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        vault_b = ConnectionVault(
            principal_genesis_id="principal-B",
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
            principal_genesis_id="principal-A",
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        vault_b = ConnectionVault(
            principal_genesis_id="principal-B",
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
            principal_genesis_id="principal-A",
            active_envelope=envelope_openai_cli,
            keyring_backend=backend,
        )
        vault_b = ConnectionVault(
            principal_genesis_id="principal-B",
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
        assert all(e.principal_genesis_id == "principal-A" for e in a_entries)
        assert all(e.principal_genesis_id == "principal-B" for e in b_entries)


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
            principal_genesis_id="abc",
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
