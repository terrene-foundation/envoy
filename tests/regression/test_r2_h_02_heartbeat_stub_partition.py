"""Regression: R2-H-02 — Foundation Health Heartbeat 5-stub partition.

Source: shard `workspaces/phase-01-mvp/01-analysis/17-foundation-health-heartbeat-decision.md`
§ 7.3 (the four mandatory Phase 01 stubs) + § 7.6 (cross-shard implications,
21 emit-site map).

Failure mode being guarded: per Round 2 R2-H-02 disposition, the original
single-stub framing conflated two structurally distinct categories — the
no-op consumer (which Phase 01 production code DOES call from 21 emit sites)
and the Phase-02-entry network/crypto primitives (which Phase 01 production
code MUST NEVER call). Conflating them meant every emit-site primitive
(Boundary Conversation completion, Daily Digest open, Grant Moment approve)
would crash on first emit if the stub raised ``PhaseDeferredError``. The
fix partitions the stubs into two modules categories:

1. ``envoy.heartbeat.client.HeartbeatClient.maybe_record_flag`` — GENUINE
   no-op; production hot path consumer; method body is literal ``pass``.
2. ``envoy.heartbeat.{star_prio,ohttp,signed_consent,registry}`` — RAISE
   ``PhaseDeferredError`` on instantiation OR helper call; Phase 01
   production code MUST NEVER import these from any non-test path.

Structural defense (orphan-detection Rule 4a): a grep over ``envoy/`` for
non-test imports of the four deferred modules MUST return zero matches.
When Phase 02 entry replaces the ``PhaseDeferredError`` bodies with real
implementations, the regression grep flips green automatically; any
premature Phase 01 caller surfaces as a HIGH finding BEFORE the swap lands.

Additional Phase 01 structural defenses verified here (per shard 17 § 7.3):
- ``HeartbeatPayload`` is a frozen 21-flag dataclass with the exact spec
  flag set (verified against ``specs/foundation-health-heartbeat.md`` § "Payload").
- ``_validate_payload_schema`` raises ``PayloadSchemaDriftError`` on any
  flag outside the 21-flag whitelist (T-054 covert-channel defense).
- ``_validate_payload_schema`` raises ``DuressFlagLeakageRefusedError``
  when ``duress_unlock_detected`` appears as a flag key (T-041 defense).

DEFERRED: the >=21 emit-site assertion ships when emit-site primitives
ship in Wave 2+/4. As of Phase 01 Wave 1 baseline, the emit-site primitives
(Boundary Conversation T-02-40, Daily Digest, Grant Moment, Authorship
Score, Posture ladder, Budget tracker, Channel adapters, Runtime stub) do
NOT exist on main yet — verified by ``git ls-tree -r main | grep -E
"envoy/(boundary_conversation|daily_digest|grant_moment|authorship/score|
posture|budget|channels)"`` returning matches only for primitives that
HAVE shipped. Asserting >=21 today would assert against modules that don't
exist; the assertion lands when the emit-site primitives ship per shard 17
§ 7.6 cross-shard implications.

Per ``rules/refactor-invariants.md``: this is a permanent regression
marker; deletion / silent skip is BLOCKED per ``rules/testing.md`` §
Test-Skip Triage.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

import envoy.heartbeat as hb
import envoy.heartbeat.ohttp as hb_ohttp
import envoy.heartbeat.registry as hb_registry
import envoy.heartbeat.signed_consent as hb_signed_consent
import envoy.heartbeat.star_prio as hb_star_prio
from envoy.heartbeat.errors import (
    DuressFlagLeakageRefusedError,
    PayloadSchemaDriftError,
    PhaseDeferredError,
)
from envoy.heartbeat.payload import (
    ALLOWED_FLAGS,
    DURESS_FLAG_NEVER_REPORTED,
    HeartbeatPayload,
    _validate_payload_schema,
)

# Repository root resolved from this file's path; the test runs from any cwd
# (per ``rules/python-environment.md`` MUST Rule 1 the test resolves cwd
# through ``Path(__file__)``, not ``process.cwd()`` or relative paths).
_REPO_ROOT = Path(__file__).resolve().parents[2]


# Canonical 21-flag set per spec line 29. Verbatim from the spec; if this
# list ever drifts from ``ALLOWED_FLAGS`` the test surfaces the divergence.
_SPEC_21_FLAGS: frozenset[str] = frozenset(
    {
        "completed_boundary_conversation",
        "opened_daily_digest_this_week",
        "completed_weekly_posture_review",
        "opened_monthly_trust_report",
        "grant_moment_novelty_approved",
        "grant_moment_novelty_denied",
        "force_install_used_skill",
        "authorship_score_reached_3",
        "authorship_score_reached_5",
        "posture_delegating_active",
        "posture_autonomous_active",
        "budget_monthly_exceeded_50pct",
        "budget_monthly_exceeded_80pct",
        "channel_telegram_active",
        "channel_slack_active",
        "channel_discord_active",
        "channel_whatsapp_active",
        "channel_signal_active",
        "channel_imessage_active",
        "runtime_kailash_rs_active",
        "enterprise_mode_active",
    }
)


class TestR2H02StubPartition:
    """5-stub partition shape (R2-H-02 fix per shard 17 § 7.3)."""

    def test_heartbeat_package_exposes_no_op_client(self) -> None:
        """``HeartbeatClient`` is the hot-path consumer (genuine no-op)."""
        assert hasattr(hb, "HeartbeatClient"), (
            "envoy.heartbeat.HeartbeatClient MUST be exposed on the public "
            "facade — it is the Phase 01 hot-path consumer for the 21 "
            "emit-site primitives (shard 17 § 7.3 stub #1)."
        )

    def test_maybe_record_flag_is_genuine_no_op(self) -> None:
        """``maybe_record_flag`` returns ``None`` on any string input.

        This is the load-bearing Phase 01 contract: production code calls
        this on the hot path; the body MUST be a literal ``pass`` so the
        21 emit-site primitives do not crash on first emit. NO exception,
        NO ledger entry, NO network call.
        """
        client = hb.HeartbeatClient()
        # Cover a representative sample of spec flags AND a free-form string
        # (Phase 01 does not validate flag names — Phase 02 entry tightens).
        for flag in (
            "completed_boundary_conversation",
            "opened_daily_digest_this_week",
            "channel_telegram_active",
            "arbitrary_flag_string_phase_01_does_not_validate",
        ):
            result = client.maybe_record_flag(flag)
            assert result is None, (
                f"HeartbeatClient.maybe_record_flag({flag!r}) returned "
                f"{result!r}; Phase 01 contract requires None (no-op). See "
                f"shard 17 § 7.3 stub #1."
            )


class TestR2H02DeferredModulesRaise:
    """The four ``PhaseDeferredError`` modules — Phase 01 MUST NEVER call."""

    @pytest.mark.parametrize(
        "module,class_name",
        [
            (hb_star_prio, "StarPrioClient"),
            (hb_ohttp, "OhttpClient"),
            (hb_signed_consent, "SignedConsentRecorder"),
            (hb_registry, "HeartbeatRegistryClient"),
        ],
    )
    def test_deferred_class_constructor_raises(self, module: object, class_name: str) -> None:
        """Each deferred class raises ``PhaseDeferredError`` on instantiation."""
        cls = getattr(module, class_name)
        with pytest.raises(PhaseDeferredError):
            cls()

    @pytest.mark.parametrize(
        "module,helper_name",
        [
            (hb_star_prio, "split_into_shares"),
            (hb_star_prio, "check_client_side_k_anonymity"),
            (hb_ohttp, "fetch_key_configuration"),
            (hb_ohttp, "encapsulate_request"),
            (hb_signed_consent, "record_grant_moment"),
            (hb_signed_consent, "record_cascade_revoke"),
            (hb_registry, "fetch_aggregator_endpoint"),
            (hb_registry, "verify_operator_signature"),
        ],
    )
    def test_deferred_module_helper_raises(self, module: object, helper_name: str) -> None:
        """Module-level helpers on each deferred module raise ``PhaseDeferredError``."""
        helper = getattr(module, helper_name)
        with pytest.raises(PhaseDeferredError):
            helper()


class TestR2H02RegressionGrep:
    """Structural defense per ``rules/orphan-detection.md`` Rule 4a.

    Phase 01 production code (anything under ``envoy/`` that is NOT a test)
    MUST NOT import any of the four ``PhaseDeferredError`` modules. The
    grep is the mechanical defense — when Phase 02 entry replaces the
    raise sites, this test continues to pass (the import surface is
    deferred-module-name-stable). When a premature Phase 01 caller lands,
    this test fails with the exact file path and line.
    """

    def test_no_production_imports_of_deferred_modules(self) -> None:
        """Grep ``envoy/`` for any non-test import of the 4 deferred modules.

        Asserts the regression-grep output is empty. Uses
        ``subprocess.run`` against ``grep -rln`` per the test brief —
        identical to the grep an operator would run manually.
        """
        envoy_dir = _REPO_ROOT / "envoy"
        assert envoy_dir.is_dir(), (
            f"envoy package directory not found at {envoy_dir!r}; the "
            f"regression grep cannot run without the source tree."
        )

        # Equivalent to:
        # grep -rln "from envoy.heartbeat.(star_prio|ohttp|signed_consent|
        #            registry)\|import envoy.heartbeat.(star_prio|ohttp|
        #            signed_consent|registry)" envoy/ | grep -v __pycache__
        # but executed via subprocess so the test's evidence matches what
        # an operator would run by hand.
        pattern = (
            r"from envoy\.heartbeat\.\(star_prio\|ohttp\|signed_consent\|registry\)"
            r"\|"
            r"import envoy\.heartbeat\.\(star_prio\|ohttp\|signed_consent\|registry\)"
        )
        result = subprocess.run(
            ["grep", "-rln", pattern, str(envoy_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        # grep exits 0 with output when matches found, 1 when no matches,
        # 2+ on error. Per Rule 4a, ANY non-test match is a violation; the
        # only acceptable outcome is exit 1 with empty stdout.
        matches = [
            line
            for line in result.stdout.splitlines()
            if line.strip() and "__pycache__" not in line
        ]
        assert matches == [], (
            "Phase 01 production code imports a Phase-02-deferred "
            "heartbeat module — see shard 17 § 7.3 and orphan-detection "
            f"Rule 4a. Offending lines:\n{result.stdout}"
        )


class TestR2H02PayloadSchemaDefense:
    """Phase 01 structural defenses ship even when emit pipeline is stubbed."""

    def test_allowed_flags_matches_spec_21_flag_set(self) -> None:
        """``ALLOWED_FLAGS`` is the verbatim 21-flag set from spec line 29."""
        assert len(_SPEC_21_FLAGS) == 21, (
            "Spec-derived flag set declared in this test file is not 21 "
            "elements; the test fixture has drifted from "
            "specs/foundation-health-heartbeat.md line 29."
        )
        assert len(ALLOWED_FLAGS) == 21, (
            f"envoy.heartbeat.payload.ALLOWED_FLAGS has "
            f"{len(ALLOWED_FLAGS)} entries; spec mandates 21."
        )
        assert ALLOWED_FLAGS == _SPEC_21_FLAGS, (
            "ALLOWED_FLAGS diverges from the spec 21-flag set. Diff: "
            f"spec - source = {_SPEC_21_FLAGS - ALLOWED_FLAGS!r}; "
            f"source - spec = {ALLOWED_FLAGS - _SPEC_21_FLAGS!r}"
        )

    def test_payload_dataclass_is_frozen(self) -> None:
        """``HeartbeatPayload`` is frozen — attribute assignment MUST raise."""
        payload = HeartbeatPayload(
            install_id="install-001",
            envoy_version="0.1.0",
            flags={"completed_boundary_conversation": True},
        )
        with pytest.raises((AttributeError, Exception)):
            payload.install_id = "tampered"  # type: ignore[misc]

    def test_validate_payload_accepts_full_21_flag_set(self) -> None:
        """A payload carrying ALL 21 spec flags validates clean."""
        all_flags = {flag: False for flag in ALLOWED_FLAGS}
        payload = HeartbeatPayload(
            install_id="install-002",
            envoy_version="0.1.0",
            flags=all_flags,
        )
        # No exception => clean validation.
        _validate_payload_schema(payload)

    def test_validate_payload_accepts_empty_flag_dict(self) -> None:
        """A payload with no flags validates clean — Phase 01 default state."""
        payload = HeartbeatPayload(
            install_id="install-003",
            envoy_version="0.1.0",
            flags={},
        )
        _validate_payload_schema(payload)

    def test_validate_payload_rejects_unknown_flag_t054(self) -> None:
        """T-054 covert-channel defense: any flag outside the 21-flag set is refused."""
        payload = HeartbeatPayload(
            install_id="install-004",
            envoy_version="0.1.0",
            flags={"completed_boundary_conversation": True, "covert_field": True},
        )
        with pytest.raises(PayloadSchemaDriftError) as exc_info:
            _validate_payload_schema(payload)
        assert "covert_field" in str(exc_info.value), (
            "PayloadSchemaDriftError MUST cite the offending flag key in "
            "its message for triage; the helper is the audit trail per "
            "rules/observability.md."
        )

    def test_validate_payload_rejects_duress_flag_t041(self) -> None:
        """T-041 defense: ``duress_unlock_detected`` MUST NEVER appear in payload.

        Defense fires even when the value is ``False``; the leak is the
        KEY's presence, not its value. Per spec § "Flags NEVER reported".
        """
        payload = HeartbeatPayload(
            install_id="install-005",
            envoy_version="0.1.0",
            flags={DURESS_FLAG_NEVER_REPORTED: False},
        )
        with pytest.raises(DuressFlagLeakageRefusedError) as exc_info:
            _validate_payload_schema(payload)
        assert DURESS_FLAG_NEVER_REPORTED in str(exc_info.value), (
            "DuressFlagLeakageRefusedError MUST cite the duress flag name " "for triage clarity."
        )

    def test_duress_flag_name_matches_spec(self) -> None:
        """The duress flag constant matches the spec verbatim."""
        assert DURESS_FLAG_NEVER_REPORTED == "duress_unlock_detected", (
            "DURESS_FLAG_NEVER_REPORTED diverged from spec line 31 "
            "(``duress_unlock_detected``); T-041 defense will silently "
            "miss the actual covert key."
        )


class TestR2H02PublicFacadeContract:
    """``__all__`` for envoy.heartbeat lists every eagerly-imported public symbol.

    Per ``rules/orphan-detection.md`` Rule 6: module-scope imports MUST
    appear in ``__all__`` so the public API contract matches what
    ``from envoy.heartbeat import *`` exposes.
    """

    def test_all_eagerly_imported_public_symbols_in_all(self) -> None:
        """Every non-underscore module-scope import is enumerated in ``__all__``."""
        init_path = _REPO_ROOT / "envoy" / "heartbeat" / "__init__.py"
        tree = ast.parse(init_path.read_text(encoding="utf-8"))

        eager_imports: set[str] = set()
        declared_all: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                # Skip `from __future__ import ...` — pseudo-imports that
                # never bind real public symbols on the module.
                if node.module == "__future__":
                    continue
                for alias in node.names:
                    name = alias.asname or alias.name
                    # Skip private symbols (leading underscore) per Rule 6
                    # carve-out, but treat _validate_payload_schema as public
                    # because shard 17 § 7.3 makes it a structural-defense
                    # entrypoint exposed on the facade.
                    if name.startswith("_") and not name.startswith("_validate_payload_schema"):
                        continue
                    eager_imports.add(name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, ast.List):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    declared_all.add(elt.value)

        missing = eager_imports - declared_all
        assert not missing, (
            f"Public symbols imported at module scope but absent from "
            f"__all__: {sorted(missing)!r}. Per orphan-detection Rule 6, "
            f"every eagerly-imported public symbol MUST appear in __all__."
        )
