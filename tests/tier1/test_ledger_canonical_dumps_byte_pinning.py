"""Tier 1: T-01-17 — canonical_dumps byte-vector pinning + hash chain.

Source: T-01-17 per `01-wave-1-foundation.md` line 185 + spec authority
`specs/ledger.md` § Entry envelope schema + BET-6 (head-commitment byte
identity) + shard 6 § 3 invariants 1-7.

The canonical-JSON byte vector is the cross-SDK byte-identity contract
(Python emitter + kailash-rs verifier produce byte-identical entry_ids).
Per kailash-py byte-pinning closures #757 (NFC), #756 (raw UTF-8),
#731 (microsecond-padded ISO 8601). Without these pins, the same logical
envelope produces different byte vectors silently.

Capacity: 7 invariants per shard 6 § 3 — sorted keys, no whitespace,
NFC normalization, ensure_ascii=False, microsecond-padded timestamps,
numeric format pin (int-only Phase 01), no input mutation.
"""

from __future__ import annotations

import hashlib
import unicodedata
from datetime import date, datetime, timezone

import pytest

from envoy.ledger import (
    EntryEnvelope,
    HashChainBuilder,
    HeadCommitment,
    LamportClock,
    canonical_dumps,
)


VALID_ALGO_ID = {"sig": "ed25519", "hash": "sha256", "shamir": "slip39"}


# ---------------------------------------------------------------------------
# canonical_dumps — Phase 01 invariants (#757 / #756 / #731 byte pinning)
# ---------------------------------------------------------------------------


class TestCanonicalDumpsSortedKeys:
    """Invariant 1: sorted keys (lexicographic, recursive)."""

    def test_keys_emit_in_sorted_order(self) -> None:
        out = canonical_dumps({"z": 1, "a": 2, "m": 3})
        assert out == b'{"a":2,"m":3,"z":1}'

    def test_nested_dict_keys_also_sorted(self) -> None:
        out = canonical_dumps({"outer": {"z": 1, "a": 2}})
        assert out == b'{"outer":{"a":2,"z":1}}'

    def test_construction_order_irrelevant(self) -> None:
        a = canonical_dumps({"a": 1, "b": 2})
        b = canonical_dumps({"b": 2, "a": 1})
        assert a == b


class TestCanonicalDumpsNoWhitespace:
    """Invariant 2: separators=(',', ':') — no insignificant whitespace."""

    def test_no_space_after_colon_or_comma(self) -> None:
        out = canonical_dumps({"a": 1, "b": [2, 3]})
        assert b" " not in out
        assert out == b'{"a":1,"b":[2,3]}'


class TestCanonicalDumpsNFCNormalization:
    """Invariant 3 (#757): NFC-normalize every string before encoding.

    The same logical character can have two Unicode representations:
    - NFC `é` = U+00E9 (single codepoint, 2 bytes UTF-8)
    - NFD `é` = U+0065 + U+0301 (combining, 3 bytes UTF-8)

    Without NFC normalization, the same logical entry produces different
    byte vectors silently. Cross-SDK byte-identity REQUIRES NFC."""

    def test_nfc_and_nfd_produce_same_bytes(self) -> None:
        nfc = unicodedata.normalize("NFC", "café")  # composed
        nfd = unicodedata.normalize("NFD", "café")  # decomposed
        # Sanity: the inputs are different bytes pre-encode.
        assert nfc.encode("utf-8") != nfd.encode("utf-8")
        # But canonical_dumps re-normalizes both to NFC.
        out_nfc = canonical_dumps({"name": nfc})
        out_nfd = canonical_dumps({"name": nfd})
        assert out_nfc == out_nfd

    def test_nfc_string_emits_raw_utf8(self) -> None:
        out = canonical_dumps({"name": "café"})
        # raw UTF-8 — `é` = 0xC3 0xA9 (NOT \\u00e9 escape per #756)
        assert b"\xc3\xa9" in out
        assert b"\\u" not in out


class TestCanonicalDumpsRawUTF8:
    """Invariant 4 (#756): ensure_ascii=False — emit raw UTF-8 bytes."""

    def test_non_ascii_emitted_as_raw_utf8(self) -> None:
        out = canonical_dumps({"emoji": "🌍", "kanji": "日本"})
        assert b"\\u" not in out
        # Round-trip via UTF-8 preserves the original codepoints.
        text = out.decode("utf-8")
        assert "🌍" in text
        assert "日本" in text


class TestCanonicalDumpsTimestampMicrosecondPadding:
    """Invariant 5 (#731): every datetime → 27-char microsecond-padded UTC ISO 8601.

    Without padding, `datetime(2026,5,6,14,23,45)` emits
    `2026-05-06T14:23:45Z` (whole seconds) and a different `datetime`
    instance with `microsecond=123456` emits `2026-05-06T14:23:45.123456Z`
    — different bytes for what may be the same logical instant after
    truncation. Padding to microseconds is the cross-SDK byte-pin."""

    def test_whole_second_pads_to_six_zeros(self) -> None:
        ts = datetime(2026, 5, 6, 14, 23, 45, tzinfo=timezone.utc)
        out = canonical_dumps({"t": ts})
        assert out == b'{"t":"2026-05-06T14:23:45.000000Z"}'

    def test_microsecond_value_preserved(self) -> None:
        ts = datetime(2026, 5, 6, 14, 23, 45, 123456, tzinfo=timezone.utc)
        out = canonical_dumps({"t": ts})
        assert out == b'{"t":"2026-05-06T14:23:45.123456Z"}'

    def test_naive_datetime_assumed_utc(self) -> None:
        """Naive (no tzinfo) is treated as already-UTC. The encoder MUST
        NOT silently convert via local timezone — that would produce
        machine-dependent bytes."""
        naive = datetime(2026, 5, 6, 14, 23, 45)
        out = canonical_dumps({"t": naive})
        assert out == b'{"t":"2026-05-06T14:23:45.000000Z"}'

    def test_non_utc_timezone_converted_to_utc(self) -> None:
        from datetime import timedelta, timezone as tz

        plus_eight = tz(timedelta(hours=8))
        ts = datetime(2026, 5, 6, 22, 23, 45, tzinfo=plus_eight)
        out = canonical_dumps({"t": ts})
        # 22:23:45 +08:00 == 14:23:45 UTC
        assert out == b'{"t":"2026-05-06T14:23:45.000000Z"}'

    def test_timestamp_length_is_27(self) -> None:
        """27 chars: YYYY-MM-DDTHH:MM:SS.NNNNNNZ (10 + 1 + 8 + 1 + 6 + 1)."""
        ts = datetime(2026, 5, 6, 14, 23, 45, 1, tzinfo=timezone.utc)
        out = canonical_dumps({"t": ts})
        # Strip the wrapper: '{"t":"<27>"}' → 27 chars between the inner quotes.
        inner = out.decode("utf-8")
        ts_str = inner[len('{"t":"') : -len('"}')]
        assert len(ts_str) == 27, f"got {len(ts_str)}: {ts_str!r}"


class TestCanonicalDumpsNumericPin:
    """Invariant 6: int-only Phase 01 — float / NaN / Inf rejected loudly."""

    def test_float_rejected(self) -> None:
        with pytest.raises(TypeError, match="float"):
            canonical_dumps({"v": 1.5})

    def test_nan_rejected(self) -> None:
        with pytest.raises(TypeError):
            canonical_dumps({"v": float("nan")})

    def test_int_passes_through(self) -> None:
        out = canonical_dumps({"v": 42, "neg": -7})
        assert out == b'{"neg":-7,"v":42}'

    def test_bool_distinct_from_int(self) -> None:
        out = canonical_dumps({"flag": True, "off": False, "n": 1})
        assert out == b'{"flag":true,"n":1,"off":false}'


class TestCanonicalDumpsNoMutation:
    """Invariant 7: input dict MUST NOT be mutated."""

    def test_input_dict_unchanged_after_dumps(self) -> None:
        original = {"name": "café", "value": 42}
        snapshot = dict(original)
        canonical_dumps(original)
        assert original == snapshot

    def test_nested_dict_unchanged(self) -> None:
        nested = {"outer": {"inner": "café"}}
        canonical_dumps(nested)
        # The inner string was NFC-normalized by the encoder, but the
        # original input dict's reference to "café" must be untouched.
        assert nested == {"outer": {"inner": "café"}}


class TestCanonicalDumpsExtendedTypes:
    """Date, bytes, list, None — all have pinned encodings."""

    def test_date_isoformat(self) -> None:
        out = canonical_dumps({"d": date(2026, 5, 6)})
        assert out == b'{"d":"2026-05-06"}'

    def test_bytes_hex_encoded(self) -> None:
        out = canonical_dumps({"b": b"\x00\x01\xff"})
        assert out == b'{"b":"0001ff"}'

    def test_list_recursive(self) -> None:
        out = canonical_dumps({"l": [3, 1, 2]})
        # Lists preserve order (NOT sorted; only dict keys are sorted).
        assert out == b'{"l":[3,1,2]}'

    def test_none_emits_null(self) -> None:
        out = canonical_dumps({"x": None})
        assert out == b'{"x":null}'

    def test_unsupported_type_raises_loudly(self) -> None:
        with pytest.raises(TypeError, match="unsupported type"):
            canonical_dumps({"x": {1, 2, 3}})  # set


# ---------------------------------------------------------------------------
# HashChainBuilder + EntryEnvelope — chain shape + freezing
# ---------------------------------------------------------------------------


class TestHashChainBuilderBuildUnsigned:
    @pytest.fixture
    def builder(self) -> HashChainBuilder:
        return HashChainBuilder()

    @pytest.fixture
    def lamport(self) -> LamportClock:
        return LamportClock(lamport_time=1, device_id="a" * 64, local_seq=1)

    def test_entry_id_is_sha256_of_canonical_bytes(
        self, builder: HashChainBuilder, lamport: LamportClock
    ) -> None:
        canonical_bytes, entry_id = builder.build_unsigned(
            prev_entry_id="sha256:" + "0" * 64,
            sequence=1,
            lamport=lamport,
            timestamp="2026-05-06T14:23:45.000000Z",
            type_="RoleEnvelopeCreated",
            content={"envelope_version": 1},
            intent_id=None,
            content_trust_level="system",
            description_content_hash="sha256:" + "a" * 64,
            signed_by="device:abc",
            algorithm_identifier=VALID_ALGO_ID,
        )
        expected = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
        assert entry_id == expected

    def test_build_is_deterministic(self, builder: HashChainBuilder, lamport: LamportClock) -> None:
        kwargs = dict(
            prev_entry_id="sha256:" + "0" * 64,
            sequence=1,
            lamport=lamport,
            timestamp="2026-05-06T14:23:45.000000Z",
            type_="RoleEnvelopeCreated",
            content={"envelope_version": 1},
            intent_id=None,
            content_trust_level="system",
            description_content_hash="sha256:" + "a" * 64,
            signed_by="device:abc",
            algorithm_identifier=VALID_ALGO_ID,
        )
        out1 = builder.build_unsigned(**kwargs)  # type: ignore[arg-type]
        out2 = builder.build_unsigned(**kwargs)  # type: ignore[arg-type]
        assert out1 == out2

    def test_seal_produces_frozen_envelope(
        self, builder: HashChainBuilder, lamport: LamportClock
    ) -> None:
        kwargs = dict(
            prev_entry_id="sha256:" + "0" * 64,
            sequence=1,
            lamport=lamport,
            timestamp="2026-05-06T14:23:45.000000Z",
            type_="RoleEnvelopeCreated",
            content={"envelope_version": 1},
            intent_id=None,
            content_trust_level="system",
            description_content_hash="sha256:" + "a" * 64,
            signed_by="device:abc",
            algorithm_identifier=VALID_ALGO_ID,
        )
        canonical_bytes, entry_id = builder.build_unsigned(**kwargs)  # type: ignore[arg-type]
        env = builder.seal(
            entry_id=entry_id,
            signature_hex="deadbeef" * 16,
            **kwargs,  # type: ignore[arg-type]
        )
        # Frozen — assignment raises
        with pytest.raises(AttributeError):
            env.sequence = 2  # type: ignore[misc]


class TestEntryEnvelopeShapeValidation:
    @pytest.fixture
    def base_kwargs(self) -> dict:
        clock = LamportClock(lamport_time=1, device_id="a" * 64, local_seq=1)
        return dict(
            entry_id="sha256:" + "f" * 64,
            parent_hash="sha256:" + "0" * 64,
            sequence=1,
            lamport_clock=clock,
            timestamp="2026-05-06T14:23:45.000000Z",
            type="RoleEnvelopeCreated",
            intent_id=None,
            content={},
            content_trust_level="system",
            description_content_hash="sha256:" + "a" * 64,
            description_content_hash_algorithm="sha256",
            signed_by="device:abc",
            signature_hex="deadbeef" * 16,
            algorithm_identifier=VALID_ALGO_ID,
            schema_version="ledger-entry/1.0",
        )

    def test_valid_envelope_constructs(self, base_kwargs: dict) -> None:
        env = EntryEnvelope(**base_kwargs)
        assert env.entry_id == base_kwargs["entry_id"]

    def test_entry_id_must_have_sha256_prefix(self, base_kwargs: dict) -> None:
        base_kwargs["entry_id"] = "f" * 64  # no "sha256:" prefix
        with pytest.raises(ValueError, match="entry_id must be"):
            EntryEnvelope(**base_kwargs)

    def test_parent_hash_must_have_sha256_prefix(self, base_kwargs: dict) -> None:
        base_kwargs["parent_hash"] = "0" * 64
        with pytest.raises(ValueError, match="parent_hash must be"):
            EntryEnvelope(**base_kwargs)

    def test_negative_sequence_rejected(self, base_kwargs: dict) -> None:
        base_kwargs["sequence"] = -1
        with pytest.raises(ValueError, match="sequence"):
            EntryEnvelope(**base_kwargs)

    def test_non_canonical_hash_algorithm_rejected(self, base_kwargs: dict) -> None:
        base_kwargs["description_content_hash_algorithm"] = "sha512"
        with pytest.raises(ValueError, match="sha256"):
            EntryEnvelope(**base_kwargs)

    def test_non_canonical_schema_version_rejected(self, base_kwargs: dict) -> None:
        base_kwargs["schema_version"] = "ledger-entry/0.9"
        with pytest.raises(ValueError, match="ledger-entry/1.0"):
            EntryEnvelope(**base_kwargs)

    def test_one_key_algorithm_id_rejected(self, base_kwargs: dict) -> None:
        """T-01-15 R2-H-01 wire-form translator delivers the 3-key form;
        Ledger entries that arrive with the upstream 1-key form indicate
        producer-side bypass of the bottleneck."""
        base_kwargs["algorithm_identifier"] = {"algorithm": "ed25519+sha256"}
        with pytest.raises(ValueError, match="3-key"):
            EntryEnvelope(**base_kwargs)


class TestLamportClockShape:
    def test_negative_lamport_time_rejected(self) -> None:
        with pytest.raises(ValueError, match="lamport_time"):
            LamportClock(lamport_time=-1, device_id="a" * 64, local_seq=1)

    def test_empty_device_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="device_id"):
            LamportClock(lamport_time=1, device_id="", local_seq=1)

    def test_negative_local_seq_rejected(self) -> None:
        with pytest.raises(ValueError, match="local_seq"):
            LamportClock(lamport_time=1, device_id="a" * 64, local_seq=-1)

    def test_to_dict_round_trip(self) -> None:
        clock = LamportClock(lamport_time=42, device_id="b" * 64, local_seq=7)
        d = clock.to_dict()
        assert d == {"lamport_time": 42, "device_id": "b" * 64, "local_seq": 7}
        clock2 = LamportClock.from_dict(d)
        assert clock2 == clock


class TestHeadCommitmentShape:
    def test_valid_head_constructs(self) -> None:
        head = HeadCommitment(
            head_sequence=42,
            head_entry_id="sha256:" + "f" * 64,
            signed_at="2026-05-06T14:23:45.000000Z",
            signature_hex="deadbeef" * 16,
        )
        assert head.head_sequence == 42

    def test_negative_head_sequence_rejected(self) -> None:
        with pytest.raises(ValueError, match="head_sequence"):
            HeadCommitment(
                head_sequence=-1,
                head_entry_id="sha256:" + "f" * 64,
                signed_at="t",
                signature_hex="s",
            )

    def test_head_entry_id_must_have_sha256_prefix(self) -> None:
        with pytest.raises(ValueError, match="head_entry_id"):
            HeadCommitment(
                head_sequence=1,
                head_entry_id="f" * 64,
                signed_at="t",
                signature_hex="s",
            )
