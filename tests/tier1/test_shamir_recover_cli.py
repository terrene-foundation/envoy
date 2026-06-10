"""Tier 1 tests for T-02-36 `envoy shamir recover`.

Pins the 3 invariants per
`workspaces/phase-01-mvp/todos/active/02-wave-2-authorship-shamir-boundary.md`
§ T-02-36 capacity check:

1. **Commitment verification** — every presented shard's commitment MUST
   appear in `Genesis.shard_public_commitments`; counterfeit shards
   raise `CommitmentVerificationFailedError`.
2. **Threshold reconstruction** — `len(presented) < threshold` raises
   `InsufficientSharesError` BEFORE any other check.
3. **CLI surface stability** — the click group + command names + option
   names + `recover_master_key` signature are AST-locked here.

Tier 1 scope: real SLIP-0039 library (pure crypto, no infrastructure) +
real `compute_commitment` + click `CliRunner` (in-process). No vault, no
disk I/O. Tier 2 wiring across real `kailash.trust.vault.shamir` end-to-end
lives in T-02-37 (`tests/tier2/test_shamir_recover_wiring.py`).
"""

from __future__ import annotations

import ast
import inspect
import json
import pathlib

import pytest
import shamir_mnemonic
from click.testing import CliRunner

from envoy.cli.main import cli
from envoy.cli.shamir import (
    EXIT_COMMITMENT_MISSING,
    EXIT_COMMITMENT_VERIFICATION_FAILED,
    EXIT_INSUFFICIENT_SHARES,
    EXIT_OK,
    EXIT_SHARD_CHECKSUM_FAILED,
    EXIT_SLOT_LABEL_MISMATCH,
    EXIT_TOO_MANY_SHARES,
)
from envoy.shamir.commitments import compute_commitment
from envoy.shamir.errors import (
    CommitmentVerificationFailedError,
    InsufficientSharesError,
    ShardChecksumFailedError,
    ShardPublicCommitmentMissingError,
    ShardSlotLabelMismatchError,
    TooManySharesError,
)
from envoy.shamir.recover import (
    DEFAULT_THRESHOLD,
    PresentedShard,
    recover_master_key,
)

# ---------------------------------------------------------------------------
# Fixtures — real SLIP-0039 3-of-5 ritual outputs
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_ritual() -> dict:
    """Generate a real 3-of-5 SLIP-0039 ritual for the tests.

    Returns a dict with:
    - `secret`: the 16-byte master secret the ritual splits
    - `shards`: list of 5 word-lists (each ~20 words for 128-bit secret)
    - `commitments`: tuple of `sha256:hex` per shard (canonical Genesis form)
    - `slot_labels`: tuple ("slot-0", ..., "slot-4")
    """
    secret = bytes(range(16))  # deterministic test secret
    groups = shamir_mnemonic.generate_mnemonics(1, [(3, 5)], secret)
    shards = [m.split() for m in groups[0]]
    commitments = tuple(compute_commitment(shard) for shard in shards)
    slot_labels = tuple(f"slot-{i}" for i in range(len(shards)))
    return {
        "secret": secret,
        "shards": shards,
        "commitments": commitments,
        "slot_labels": slot_labels,
    }


def _present(real_ritual: dict, indices: list[int]) -> list[PresentedShard]:
    """Build PresentedShard list from real ritual fixture for indices."""
    return [
        PresentedShard(
            slot_label=real_ritual["slot_labels"][share_idx],
            words=list(real_ritual["shards"][share_idx]),
            card_index=card_idx,
        )
        for card_idx, share_idx in enumerate(indices)
    ]


# ---------------------------------------------------------------------------
# Invariant 1 — Commitment verification gate
# ---------------------------------------------------------------------------


class TestCommitmentVerificationGate:
    """Counterfeit shards (not in Genesis commitments) are rejected."""

    def test_happy_path_all_commitments_match(self, real_ritual: dict) -> None:
        presented = _present(real_ritual, [0, 1, 2])
        recovered = recover_master_key(
            presented,
            commitments=real_ritual["commitments"],
            checklist_labels=real_ritual["slot_labels"],
        )
        assert recovered == real_ritual["secret"]

    def test_counterfeit_shard_raises_commitment_verification_failed(
        self, real_ritual: dict
    ) -> None:
        """A shard generated from a DIFFERENT secret fails commitment check."""
        # Counterfeit ritual — same shape (3-of-5), different secret
        counterfeit_secret = bytes(range(16, 32))
        counterfeit_groups = shamir_mnemonic.generate_mnemonics(1, [(3, 5)], counterfeit_secret)
        counterfeit_shard = counterfeit_groups[0][0].split()

        presented = [
            PresentedShard(slot_label="slot-0", words=list(counterfeit_shard), card_index=0),
            PresentedShard(
                slot_label="slot-1",
                words=list(real_ritual["shards"][1]),
                card_index=1,
            ),
            PresentedShard(
                slot_label="slot-2",
                words=list(real_ritual["shards"][2]),
                card_index=2,
            ),
        ]
        with pytest.raises(CommitmentVerificationFailedError) as exc_info:
            recover_master_key(
                presented,
                commitments=real_ritual["commitments"],
                checklist_labels=real_ritual["slot_labels"],
            )
        assert exc_info.value.failing_card_index == 0
        assert exc_info.value.failing_slot_label == "slot-0"
        # Plain-language user_message must NOT include the raw exception
        assert "spell-check" in exc_info.value.user_message
        assert "fingerprint" in exc_info.value.user_message

    def test_missing_commitments_raises_pre_phase_01_error(self, real_ritual: dict) -> None:
        presented = _present(real_ritual, [0, 1, 2])
        with pytest.raises(ShardPublicCommitmentMissingError) as exc_info:
            recover_master_key(
                presented,
                commitments=(),  # pre-Phase-01 vault
                checklist_labels=real_ritual["slot_labels"],
            )
        assert "envoy vault migrate" in exc_info.value.user_message


# ---------------------------------------------------------------------------
# Invariant 2 — Threshold reconstruction
# ---------------------------------------------------------------------------


class TestInsufficientShares:
    """`len(presented) < threshold` raises before any other check."""

    def test_below_threshold_raises_insufficient_shares(self, real_ritual: dict) -> None:
        presented = _present(real_ritual, [0, 1])  # 2 < 3
        with pytest.raises(InsufficientSharesError) as exc_info:
            recover_master_key(
                presented,
                commitments=real_ritual["commitments"],
                checklist_labels=real_ritual["slot_labels"],
            )
        assert exc_info.value.presented == 2
        assert exc_info.value.threshold == DEFAULT_THRESHOLD
        assert "2" in exc_info.value.user_message
        assert "3 cards" in exc_info.value.user_message

    def test_at_threshold_succeeds(self, real_ritual: dict) -> None:
        presented = _present(real_ritual, [0, 1, 2])  # exactly 3
        recovered = recover_master_key(
            presented,
            commitments=real_ritual["commitments"],
            checklist_labels=real_ritual["slot_labels"],
        )
        assert recovered == real_ritual["secret"]

    def test_above_threshold_raises_too_many_shares(self, real_ritual: dict) -> None:
        """SLIP-0039 requires exactly threshold; >threshold is library-rejected.

        Per primitive contract: validate at entry rather than letting the
        library raise an opaque MnemonicError. Typed envoy error carries
        plain-language `.user_message` directing the user to pick exactly
        threshold cards.
        """
        presented = _present(real_ritual, [0, 1, 2, 3])  # 4 > 3
        with pytest.raises(TooManySharesError) as exc_info:
            recover_master_key(
                presented,
                commitments=real_ritual["commitments"],
                checklist_labels=real_ritual["slot_labels"],
            )
        assert exc_info.value.presented == 4
        assert exc_info.value.threshold == DEFAULT_THRESHOLD
        assert "4 cards" in exc_info.value.user_message
        assert "Pick exactly 3" in exc_info.value.user_message

    def test_insufficient_fires_before_commitment_check(self, real_ritual: dict) -> None:
        """Insufficient-shares is the cheapest precondition — fires first."""
        # 2 cards, EMPTY commitments. Insufficient should win, not "missing".
        presented = _present(real_ritual, [0, 1])
        with pytest.raises(InsufficientSharesError):
            recover_master_key(
                presented,
                commitments=(),
                checklist_labels=real_ritual["slot_labels"],
            )


# ---------------------------------------------------------------------------
# Invariant 3 — CLI surface stability (AST lock)
# ---------------------------------------------------------------------------


class TestRecoverMasterKeySignature:
    """`recover_master_key()` signature is AST-locked.

    Any signature change MUST be intentional — landing here pins the
    public contract that the CLI shell, Boundary Conversation S8, and
    future channel-adapter recovery flows all depend on.
    """

    def test_signature_is_locked(self) -> None:
        sig = inspect.signature(recover_master_key)
        params = sig.parameters

        # Positional: presented
        assert "presented" in params
        assert params["presented"].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD

        # Keyword-only: commitments, checklist_labels, threshold, passphrase
        for name in ("commitments", "checklist_labels", "threshold", "passphrase"):
            assert name in params, f"missing keyword arg: {name}"
            assert (
                params[name].kind == inspect.Parameter.KEYWORD_ONLY
            ), f"{name} must be keyword-only"

        # Defaults that the spec / brief pin
        assert params["threshold"].default == DEFAULT_THRESHOLD
        assert params["passphrase"].default == b""


class TestRecoverCliSurface:
    """The click group + command + option names are AST-locked."""

    def test_envoy_group_has_shamir_subgroup(self) -> None:
        assert "shamir" in cli.commands
        shamir_cmd = cli.commands["shamir"]
        assert "recover" in shamir_cmd.commands

    def test_recover_command_options(self) -> None:
        recover_cmd = cli.commands["shamir"].commands["recover"]
        param_names = {p.name for p in recover_cmd.params}
        # Spec-bound option surface — adding options is OK; removing is not
        assert {"genesis_path", "shards_from", "threshold", "passphrase"} <= param_names


# ---------------------------------------------------------------------------
# Per-card SLIP-0039 checksum (L-03 fix) — fires before commitment check
# ---------------------------------------------------------------------------


class TestPerCardChecksumValidation:
    """Per-card BIP-39 checksum validation at entry (L-03 carry-forward)."""

    def test_bad_word_in_card_raises_with_card_index(self, real_ritual: dict) -> None:
        bad = list(real_ritual["shards"][0])
        bad[5] = "fryingpan"  # not in BIP-39 wordlist; bad checksum guaranteed
        presented = [
            PresentedShard(slot_label="slot-0", words=bad, card_index=0),
            PresentedShard(
                slot_label="slot-1",
                words=list(real_ritual["shards"][1]),
                card_index=1,
            ),
            PresentedShard(
                slot_label="slot-2",
                words=list(real_ritual["shards"][2]),
                card_index=2,
            ),
        ]
        with pytest.raises(ShardChecksumFailedError) as exc_info:
            recover_master_key(
                presented,
                commitments=real_ritual["commitments"],
                checklist_labels=real_ritual["slot_labels"],
            )
        assert exc_info.value.card_index == 0
        assert exc_info.value.slot_label == "slot-0"
        assert "card slot-0" in exc_info.value.user_message
        assert "spell-check" in exc_info.value.user_message

    def test_empty_card_raises_with_card_index(self, real_ritual: dict) -> None:
        presented = [
            PresentedShard(slot_label="slot-0", words=[], card_index=0),
            PresentedShard(
                slot_label="slot-1",
                words=list(real_ritual["shards"][1]),
                card_index=1,
            ),
            PresentedShard(
                slot_label="slot-2",
                words=list(real_ritual["shards"][2]),
                card_index=2,
            ),
        ]
        with pytest.raises(ShardChecksumFailedError) as exc_info:
            recover_master_key(
                presented,
                commitments=real_ritual["commitments"],
                checklist_labels=real_ritual["slot_labels"],
            )
        assert exc_info.value.card_index == 0
        assert "no words" in exc_info.value.user_message


# ---------------------------------------------------------------------------
# Slot-label whitelist (paired with DistributionChecklist whitelist)
# ---------------------------------------------------------------------------


class TestSlotLabelMismatch:
    """Presented slot label MUST appear in DistributionChecklist labels."""

    def test_unknown_slot_label_raises(self, real_ritual: dict) -> None:
        presented = [
            PresentedShard(
                slot_label="slot-99",  # not in checklist
                words=list(real_ritual["shards"][0]),
                card_index=0,
            ),
            PresentedShard(
                slot_label="slot-1",
                words=list(real_ritual["shards"][1]),
                card_index=1,
            ),
            PresentedShard(
                slot_label="slot-2",
                words=list(real_ritual["shards"][2]),
                card_index=2,
            ),
        ]
        with pytest.raises(ShardSlotLabelMismatchError) as exc_info:
            recover_master_key(
                presented,
                commitments=real_ritual["commitments"],
                checklist_labels=real_ritual["slot_labels"],
            )
        assert exc_info.value.presented_label == "slot-99"
        assert "wrong card" in exc_info.value.user_message


# ---------------------------------------------------------------------------
# CLI integration tests — click CliRunner end-to-end
# ---------------------------------------------------------------------------


def _write_genesis(
    tmp_path: pathlib.Path, commitments: tuple[str, ...], slot_labels: tuple[str, ...]
) -> pathlib.Path:
    path = tmp_path / "genesis.json"
    path.write_text(
        json.dumps(
            {
                "principal_id": "test-principal",
                "shard_public_commitments": list(commitments),
                "shamir_distribution_checklist": {
                    "ritual_id": "test-ritual",
                    "slot_labels": list(slot_labels),
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_shards(
    tmp_path: pathlib.Path,
    real_ritual: dict,
    indices: list[int],
    *,
    override: dict[int, dict] | None = None,
) -> pathlib.Path:
    """Write a shards-from JSON file; `override` patches per-card-index entries."""
    override = override or {}
    entries = []
    for card_idx, share_idx in enumerate(indices):
        entry = {
            "slot_label": real_ritual["slot_labels"][share_idx],
            "words": list(real_ritual["shards"][share_idx]),
        }
        if card_idx in override:
            entry.update(override[card_idx])
        entries.append(entry)
    path = tmp_path / "shards.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


class TestRecoverCliEndToEnd:
    """Click CliRunner exercises the recover command end-to-end (in-process)."""

    def test_happy_path_exits_ok(self, tmp_path: pathlib.Path, real_ritual: dict) -> None:
        genesis = _write_genesis(tmp_path, real_ritual["commitments"], real_ritual["slot_labels"])
        shards = _write_shards(tmp_path, real_ritual, [0, 1, 2])
        result = CliRunner().invoke(
            cli,
            [
                "shamir",
                "recover",
                "--genesis",
                str(genesis),
                "--shards-from",
                str(shards),
            ],
        )
        assert result.exit_code == EXIT_OK, result.output
        assert "Recovery succeeded" in result.output
        assert "T-02-37" in result.output

    def test_insufficient_shares_exit_code(self, tmp_path: pathlib.Path, real_ritual: dict) -> None:
        genesis = _write_genesis(tmp_path, real_ritual["commitments"], real_ritual["slot_labels"])
        shards = _write_shards(tmp_path, real_ritual, [0, 1])  # < threshold
        result = CliRunner().invoke(
            cli,
            [
                "shamir",
                "recover",
                "--genesis",
                str(genesis),
                "--shards-from",
                str(shards),
            ],
        )
        assert result.exit_code == EXIT_INSUFFICIENT_SHARES, result.output

    def test_commitment_verification_failed_exit_code(
        self, tmp_path: pathlib.Path, real_ritual: dict
    ) -> None:
        # Counterfeit shard 0 via override
        counterfeit_groups = shamir_mnemonic.generate_mnemonics(1, [(3, 5)], bytes(range(16, 32)))
        counterfeit_words = counterfeit_groups[0][0].split()
        genesis = _write_genesis(tmp_path, real_ritual["commitments"], real_ritual["slot_labels"])
        shards = _write_shards(
            tmp_path,
            real_ritual,
            [0, 1, 2],
            override={0: {"words": list(counterfeit_words)}},
        )
        result = CliRunner().invoke(
            cli,
            [
                "shamir",
                "recover",
                "--genesis",
                str(genesis),
                "--shards-from",
                str(shards),
            ],
        )
        assert result.exit_code == EXIT_COMMITMENT_VERIFICATION_FAILED, result.output
        assert "CommitmentVerificationFailedError" in result.output

    def test_missing_commitments_exit_code(self, tmp_path: pathlib.Path, real_ritual: dict) -> None:
        genesis = _write_genesis(tmp_path, (), real_ritual["slot_labels"])
        shards = _write_shards(tmp_path, real_ritual, [0, 1, 2])
        result = CliRunner().invoke(
            cli,
            [
                "shamir",
                "recover",
                "--genesis",
                str(genesis),
                "--shards-from",
                str(shards),
            ],
        )
        assert result.exit_code == EXIT_COMMITMENT_MISSING, result.output

    def test_slot_label_mismatch_exit_code(self, tmp_path: pathlib.Path, real_ritual: dict) -> None:
        genesis = _write_genesis(tmp_path, real_ritual["commitments"], real_ritual["slot_labels"])
        shards = _write_shards(
            tmp_path,
            real_ritual,
            [0, 1, 2],
            override={0: {"slot_label": "slot-99"}},
        )
        result = CliRunner().invoke(
            cli,
            [
                "shamir",
                "recover",
                "--genesis",
                str(genesis),
                "--shards-from",
                str(shards),
            ],
        )
        assert result.exit_code == EXIT_SLOT_LABEL_MISMATCH, result.output

    def test_too_many_shares_exit_code(self, tmp_path: pathlib.Path, real_ritual: dict) -> None:
        genesis = _write_genesis(tmp_path, real_ritual["commitments"], real_ritual["slot_labels"])
        shards = _write_shards(tmp_path, real_ritual, [0, 1, 2, 3])  # 4 > 3
        result = CliRunner().invoke(
            cli,
            [
                "shamir",
                "recover",
                "--genesis",
                str(genesis),
                "--shards-from",
                str(shards),
            ],
        )
        assert result.exit_code == EXIT_TOO_MANY_SHARES, result.output
        assert "TooManySharesError" in result.output

    def test_bad_checksum_exit_code(self, tmp_path: pathlib.Path, real_ritual: dict) -> None:
        bad = list(real_ritual["shards"][0])
        bad[5] = "fryingpan"
        genesis = _write_genesis(tmp_path, real_ritual["commitments"], real_ritual["slot_labels"])
        shards = _write_shards(
            tmp_path,
            real_ritual,
            [0, 1, 2],
            override={0: {"words": bad}},
        )
        result = CliRunner().invoke(
            cli,
            [
                "shamir",
                "recover",
                "--genesis",
                str(genesis),
                "--shards-from",
                str(shards),
            ],
        )
        assert result.exit_code == EXIT_SHARD_CHECKSUM_FAILED, result.output

    def test_missing_genesis_file_is_usage_error(self, tmp_path: pathlib.Path) -> None:
        result = CliRunner().invoke(
            cli,
            [
                "shamir",
                "recover",
                "--genesis",
                str(tmp_path / "does-not-exist.json"),
            ],
        )
        assert result.exit_code == 2  # click usage error
        assert "not found" in result.output

    def test_malformed_genesis_json_is_usage_error(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "genesis.json"
        path.write_text("{ not valid json", encoding="utf-8")
        result = CliRunner().invoke(cli, ["shamir", "recover", "--genesis", str(path)])
        assert result.exit_code == 2

    def test_help_renders_without_error(self) -> None:
        result = CliRunner().invoke(cli, ["shamir", "recover", "--help"])
        assert result.exit_code == 0
        assert "Recover the vault master key" in result.output


# ---------------------------------------------------------------------------
# Memory hygiene — `del recovered` is structurally present
# ---------------------------------------------------------------------------


class TestMemoryHygiene:
    """AST check: the `recover` CLI body contains `del recovered` in finally.

    Per rules/trust-plane-security.md MUST NOT Rule 3 — the structural
    defense is `del`. The AST check refuses a future refactor that drops
    the finally clause.
    """

    def test_default_threshold_canonical_source(self) -> None:
        """Regression /redteam Round 1 F-1: DEFAULT_THRESHOLD MUST be a single
        source of truth — `envoy.shamir.recover.DEFAULT_THRESHOLD` is re-exported
        from `envoy.shamir.ritual.DEFAULT_THRESHOLD`, not a parallel constant.
        Catches a future refactor that re-introduces the duplicate.
        """
        import envoy.shamir.recover as recover_mod
        import envoy.shamir.ritual as ritual_mod

        assert recover_mod.DEFAULT_THRESHOLD is ritual_mod.DEFAULT_THRESHOLD, (
            "DEFAULT_THRESHOLD MUST be the same object in both modules — "
            "duplicate constants drift; ritual.DEFAULT_THRESHOLD is canonical"
        )

    def test_slot_label_mismatch_base_message_excludes_checklist_tuple(
        self, real_ritual: dict
    ) -> None:
        """Regression security review F-1: the Exception base message MUST NOT
        embed the full `checklist_labels` tuple — `str(error)` flows to
        logger.exception() and stack traces, leaking the whitelist to log
        aggregators. Per rules/observability.md MUST Rule 8.
        """
        presented = [
            PresentedShard(
                slot_label="slot-99",
                words=list(real_ritual["shards"][0]),
                card_index=0,
            ),
            PresentedShard(
                slot_label="slot-1",
                words=list(real_ritual["shards"][1]),
                card_index=1,
            ),
            PresentedShard(
                slot_label="slot-2",
                words=list(real_ritual["shards"][2]),
                card_index=2,
            ),
        ]
        with pytest.raises(ShardSlotLabelMismatchError) as exc_info:
            recover_master_key(
                presented,
                commitments=real_ritual["commitments"],
                checklist_labels=real_ritual["slot_labels"],
            )
        # Instance attribute is the programmatic access path — must still carry
        # the full tuple.
        assert exc_info.value.checklist_labels == real_ritual["slot_labels"]
        # But the Exception message (what `str(error)` / repr(error) surface)
        # MUST NOT embed the tuple. Each slot label is the leak signal.
        base_message = str(exc_info.value)
        for label in real_ritual["slot_labels"]:
            assert label not in base_message, (
                f"Exception base message leaks slot label {label!r} via "
                f"checklist_labels embedding — flows to logger.exception() / "
                f"stack traces"
            )

    def test_recover_master_key_logs_error_path(
        self, real_ritual: dict, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Regression reviewer F-2: recover_master_key MUST log a
        `shamir.recover.error` line on every typed-error path. Per
        rules/observability.md MUST Rule 1 (Entry, exit, AND error each log).
        Pre-fix, only `.start` and `.ok` fired; precondition failures
        produced ZERO log line.
        """
        import logging

        caplog.set_level(logging.DEBUG, logger="envoy.shamir.recover")
        presented = _present(real_ritual, [0, 1])  # < threshold → InsufficientSharesError

        with pytest.raises(InsufficientSharesError):
            recover_master_key(
                presented,
                commitments=real_ritual["commitments"],
                checklist_labels=real_ritual["slot_labels"],
            )

        # MUST observe both: start (entry log) + error (typed-error path log)
        log_messages = [r.message for r in caplog.records]
        assert (
            "shamir.recover.start" in log_messages
        ), "missing start log — entry MUST be logged per observability.md Rule 1"
        assert "shamir.recover.error" in log_messages, (
            "missing error log — typed-error path MUST be logged per "
            "observability.md Rule 1 (reviewer F-2 regression)"
        )
        # Schema-safe per observability.md Rule 8 — the error record carries
        # the class name + counts, never the slot labels / words / hashes.
        error_records = [r for r in caplog.records if r.message == "shamir.recover.error"]
        assert error_records, "no error-class record found"
        assert error_records[0].error_class == "InsufficientSharesError"

    def test_render_error_raises_on_missing_user_message(self) -> None:
        """Regression security review F-3: `_render_error` MUST assert the
        typed error carries a `user_message`. A future ShamirRecoveryError
        subclass that forgets to populate `user_message` would otherwise leak
        the technical `str(error)` (card_index, paths, sizes) to stderr.
        """
        from envoy.cli.shamir import _render_error
        from envoy.shamir.errors import ShamirRecoveryError

        class _OrphanRecoveryError(ShamirRecoveryError):
            """Future-drift subclass that forgets user_message — MUST fail loudly."""

        # No user_message set — `_render_error` MUST refuse rather than
        # silently leak `str(error)`.
        orphan = _OrphanRecoveryError("technical-only message")
        with pytest.raises(AssertionError, match="user_message"):
            _render_error(orphan)

    def test_recover_command_dels_recovered_bytes(self) -> None:
        import envoy.cli.shamir as shamir_mod

        source = pathlib.Path(shamir_mod.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        # Find the `recover` function (decorated with @shamir.command(...))
        recover_func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "recover":
                recover_func = node
                break
        assert recover_func is not None, "recover function not found in CLI"

        # Walk the function body; assert a `del recovered` lives inside a
        # Try.finalbody.
        found_del_in_finally = False
        for node in ast.walk(recover_func):
            if isinstance(node, ast.Try):
                for finally_stmt in node.finalbody:
                    for child in ast.walk(finally_stmt):
                        if isinstance(child, ast.Delete):
                            for target in child.targets:
                                if isinstance(target, ast.Name) and target.id == "recovered":
                                    found_del_in_finally = True
        assert found_del_in_finally, (
            "recover() MUST contain `del recovered` inside a finally clause "
            "per rules/trust-plane-security.md MUST NOT Rule 3"
        )
