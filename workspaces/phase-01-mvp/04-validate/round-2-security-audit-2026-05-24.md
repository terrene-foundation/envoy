# Round 2 — Security Audit: closure verification of Round 1 findings + new attack-surface review

**Audited:** 2026-05-24
**Scope:** `git diff 641dd2d..e89914b` — Round 1 origin merge (`641dd2d`) → current main (`e89914b`).
**Round 1 source:** `workspaces/phase-01-mvp/04-validate/round-1-security-audit-2026-05-24.md` (committed at SHA `7598578`).
**Auditor mode:** Round 2 security re-audit. Probe-driven; every closure verdict cites mechanical command output, not Shard 1 / Shard 2 PR descriptions.
**Probe discipline:** Every closure verdict carries a structural probe (grep + AST walk + file read) per `rules/probe-driven-verification.md` MUST-3 (structural probes; no LLM-judge surface).

---

## Executive verdict

**Convergence verdict:** NOT CLEAN — one new HIGH finding surfaced.

Round 1's three HIGH findings (F-2, F-4, F-5) and three MEDIUM findings (F-1, F-3, F-6) all show CLOSED disposition on the production code AND have regression-pinning tests in `tests/tier1/` + `tests/tier2/`. However, the Shard 1 F-2 mutation-invariant raises are positioned **AFTER** Step 5a's `posture_change` Ledger append, leaving an **orphan `posture_change`** entry without its paired `envelope_edit` on every F-2 invariant violation. This is structurally the SAME failure mode Round 1 F-3 named (defensive guard fires after Step 5a), now reintroduced through Shard 1's F-2 closure path.

| Round 1 ID | Severity | Round 2 verdict         | Probe evidence                                                                                                                                                                |
| ---------- | -------- | ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F-2        | HIGH     | **PARTIAL CLOSURE**     | Invariant raises wired (3 sites) AND comprehensive Tier 1 coverage (7 cases). But raises land between Step 5a and 5b → orphan `posture_change` on violation. See R2-F1 below. |
| F-4        | HIGH     | CLOSED                  | Mint-state spec edit landed (`envelope-model.md` §96), Tier 2 mint-immutability assertion present, journal/0022 documents disposition.                                        |
| F-5        | HIGH     | CLOSED (false-positive) | Threat target absent (no deserializer), 6-test regression pin landed at `tests/tier2/test_envelope_hash_mint_time_cached.py`, journal/0023 documents determination.           |
| F-1        | MEDIUM   | CLOSED                  | `_is_posture_carrying_envelope` helper at line 619; runtime check at line 852; 5 Tier 1 negative tests.                                                                       |
| F-3        | MEDIUM   | CLOSED                  | Defensive guard removed at line 1011-1022; Step 3e at line 932 is now the structural defense (raises BEFORE Step 5a).                                                         |
| F-6        | MEDIUM   | CLOSED                  | `TestPostureLevelMintStateRead` at `tests/tier1/test_posture_gate_5_step_fail_closed.py:1943` exercises the read path with 3 tests.                                           |

**Net Round 2 findings:**

- HIGH: 1 (R2-F1 — orphan `posture_change` on F-2 invariant violation; same structural failure mode as Round 1 F-3 reintroduced at a new site)
- MEDIUM: 1 (R2-F2 — `_is_posture_carrying_envelope` invokes `hasattr` on attacker-supplied objects; side-effect surface)
- LOW: 1 (R2-F3 — cross-spec drift: `specs/posture-ladder.md` line 41 absolute language "any posture change is an `envelope_edit`" still reads cleanly inside the Ratchet-up section but no longer mirrors the mint-state interpretation literally)

---

## Step 1 — Per-finding closure verification

### F-2 (HIGH) — mutation invariant verification — PARTIAL CLOSURE

#### Probe 1: invariant raise sites exist

**Command:**

```
grep -n "PostureEnvelopeMutationInvariantError" envoy/authorship/posture_gate.py
```

**Output:**

```
152:    "PostureEnvelopeMutationInvariantError",
423:class PostureEnvelopeMutationInvariantError(PostureGateError):
445:        super().__init__(f"PostureEnvelopeMutationInvariantError: {reason}")
1033:                raise PostureEnvelopeMutationInvariantError(
1041:                raise PostureEnvelopeMutationInvariantError(
1049:                raise PostureEnvelopeMutationInvariantError(
```

Three raise sites covering: (a) `envelope_id` mismatch (1033), (b) `new_version != prior_version + 1` (1041), (c) `diff_hash` not `sha256:<64-hex>` (1049). PASS for raise-site presence.

#### Probe 2: AST-walked ordering — invariant checks vs Ledger append

**AST walk method**: read `envoy/authorship/posture_gate.py:956-1068`, locate Step 5a `_ledger.append(entry_type="posture_change", ...)` and Step 5b `_ledger.append(entry_type="envelope_edit", ...)`. Map line ordering against the F-2 invariant raises.

**Output (sequence by line number):**

```
Line 932  — Step 3e: raise PostureRatchetEnvelopeMissingError (BEFORE Step 5a)
Line 979  — Step 5a: await self._ledger.append(entry_type="posture_change", ...)
Line 1023 — mutation = envelope.mutate_for_posture_level(target)
Line 1032 — if mutation.envelope_id != envelope.envelope_id: raise (F-2 INVARIANT)
Line 1040 — if mutation.new_version != envelope.prior_version + 1: raise (F-2 INVARIANT)
Line 1048 — if not _SHA256_HEX_PATTERN.fullmatch(mutation.diff_hash): raise (F-2 INVARIANT)
Line 1065 — Step 5b: await self._ledger.append(entry_type="envelope_edit", ...)
```

**Finding:** The F-2 invariant raises at lines 1032/1040/1048 fire AFTER Step 5a's `posture_change` append at line 979 but BEFORE Step 5b's `envelope_edit` append at line 1065. On any F-2 invariant violation, `posture_change` is COMMITTED to the Ledger but `envelope_edit` is NEVER appended — leaving an orphan `posture_change` entry per `specs/posture-ladder.md` § Ratchet-up #3 ("Envelope version bump … new posture is part of the envelope schema; any posture change is an `envelope_edit`"). See R2-F1 below.

#### Probe 3: structural confirmation via the Tier 1 test assertions

**Command:**

```
grep -n "types == \[\"posture_change\"\]" tests/tier1/test_posture_gate_5_step_fail_closed.py
```

**Output:**

```
1667:        assert types == ["posture_change"]
1693:        assert types == ["posture_change"]
1722:        assert types == ["posture_change"]
1748:        assert types == ["posture_change"]
```

The Tier 1 tests STRUCTURALLY confirm the orphan: after F-2 invariant raises, the Ledger contains ONLY `posture_change` (length 1), not the spec-mandated paired entry. The tests pin this as deliberate behavior — but the spec invariant is broken.

**Disposition:** F-2 invariant raises are wired (PASS) but the position in the call sequence reintroduces the F-3 failure mode (FAIL). See R2-F1 below.

### F-4 (HIGH) — inverse-paired-emission ratchet-down gap — CLOSED

#### Probe 1: spec edit landed

**Command:**

```
grep -n "Mint-state semantics\|Audit-only role" specs/envelope-model.md
```

**Output:** Line 96 in `specs/envelope-model.md` contains both `**Mint-state semantics:**` and `**Audit-only role:**` paragraphs documenting the disposition.

The spec field-semantics block reads (verbatim, line 96, excerpted): "`metadata.posture_level` reflects the envelope's mint-time posture and is immutable after the `envelope_edit` emission … Ratchet-down does NOT mutate this field … the field stays at the mint-time value … Audit-only role: `metadata.posture_level` is a mint-state audit annotation; the effective-posture derivation walks the Ledger's `posture_change` entries — no production read consumer dispatches on the envelope field's value." PASS.

#### Probe 2: Tier 2 mint-immutability assertion landed

**Command:**

```
grep -n "test_ratchet_down_does_not_mutate_envelope_posture_level\|envelope.metadata.posture_level == mint_state_value" tests/tier2/test_posture_gate_wiring.py
```

**Output:**

```
669:    async def test_ratchet_down_does_not_mutate_envelope_posture_level(
708:        assert envelope.metadata.posture_level == mint_state_value
709:        assert envelope.metadata.posture_level == "DELEGATING"
```

The test asserts BOTH (a) no `envelope_edit` Ledger emission AND (b) `envelope.metadata.posture_level` UNCHANGED at the mint-time value on demotion. PASS.

#### Probe 3: production code does NOT mutate `posture_level` on demotion

**Command:**

```
grep -n "mutate_for_posture_level\|posture_level" envoy/authorship/posture_gate.py | grep -v "^.*:.*#"
```

**Result:** `mutate_for_posture_level(target)` is invoked ONLY inside the `if target > current:` branch at line 1023 (Step 5b). The `if target < current:` branch (line 944) iterates `revoke_on_demotion` but does NOT invoke `mutate_for_posture_level`. The envelope is structurally untouched on ratchet-down. PASS.

**Disposition:** CLOSED. Spec authority + production code + Tier 2 test all aligned on mint-state interpretation. Journal `0022-DECISION-posture-level-mint-state-interpretation.md` documents the disposition with cross-references.

### F-5 (HIGH) — JCS canonical-bytes break — CLOSED (FALSE-POSITIVE disposition)

#### Probe 1: re-verify the threat-target absence

**Command:**

```
grep -rn "from_json\|from_dict.*Envelope\|loads.*Envelope" envoy/envelope/
```

**Output:** (exit 1 — no matches)

The threat model F-5 names (re-canonicalization of a deserialized envelope producing a different `content_hash`) requires a deserializer that does not exist. PASS.

#### Probe 2: `canonical_bytes` and `content_hash` are stored frozen fields

**Command:**

```
grep -n "^    canonical_bytes\|^    content_hash" envoy/envelope/types.py
```

**Output:** Per probe-walk in `tests/tier2/test_envelope_hash_mint_time_cached.py::test_canonical_bytes_is_a_stored_frozen_field` + sibling test (lines 123-174), both fields are `AnnAssign` nodes on a `@dataclass(frozen=True)` class. PASS.

#### Probe 3: 6-test regression pin covers the invariants

**Command:**

```
grep -n "def test_" tests/tier2/test_envelope_hash_mint_time_cached.py
```

**Output:**

```
123:    def test_canonical_bytes_is_a_stored_frozen_field(self) -> None:
152:    def test_content_hash_is_a_stored_frozen_field(self) -> None:
176:    def test_no_envelope_deserializer_exists(self) -> None:
234:    def test_canonical_bytes_module_documents_single_point_hash_design(self) -> None:
264:    def test_compiler_computes_canonical_bytes_and_content_hash_exactly_once(
320:    def test_posture_gate_consumes_prior_content_hash_as_stored_attribute(self) -> None:
```

Six tests pin:

1. `canonical_bytes` is a stored frozen field (AST probe).
2. `content_hash` is a stored frozen field (AST probe).
3. No deserializer exists in `envoy/envelope/` (AST walk over all `*.py`).
4. The design-intent docstring at `envoy/envelope/canonical_bytes.py:73-83` is present (file-read probe).
5. The compiler's `canonical_bytes` + `content_hash` are mint-time-cached via `is`-identity (real `EnvelopeCompiler` invocation).
6. PostureGate consumes `envelope.prior_content_hash` as `ast.Attribute` reads, NOT as `ast.Call` invocations (AST probe).

PASS — all six are structural probes per `rules/probe-driven-verification.md` MUST-3.

#### Probe 4: journal disposition documents determination

**Command:**

```
ls -la workspaces/phase-01-mvp/journal/0023-DISCOVERY-envelope-hashes-mint-time-cached-f5-false-positive.md
```

**Output:** File exists; 157 lines; documents the five investigation receipts (frozen-field, single-point hash, design-intent docstring, no deserializer, stored-attribute consumption) per `rules/verify-resource-existence.md` MUST-3 (delete-or-stub when threat target absent). PASS.

**Disposition:** CLOSED with FALSE-POSITIVE determination. Six-test regression pin defends against any future PR that introduces a deserializer — at which point F-5's threat model becomes applicable AGAIN and the regression test fails loudly.

### F-1 (MEDIUM) — kwarg type/shape check — CLOSED

#### Probe 1: helper exists with attribute enumeration

**Command:**

```
grep -n "_is_posture_carrying_envelope" envoy/authorship/posture_gate.py
```

**Output:**

```
619:def _is_posture_carrying_envelope(obj: object) -> bool:
852:        if envelope is not None and not _is_posture_carrying_envelope(envelope):
```

Function defined at line 619; runtime check applied at line 852 BEFORE Step 1 (line 860). PASS.

#### Probe 2: helper enumerates the full Protocol surface

**Command:** Read lines 638-644.

**Output:**

```python
return (
    hasattr(obj, "envelope_id")
    and hasattr(obj, "prior_version")
    and hasattr(obj, "prior_content_hash")
    and hasattr(obj, "prior_posture_level")
    and callable(getattr(obj, "mutate_for_posture_level", None))
)
```

All four `_PostureCarryingEnvelope` Protocol attributes (`envelope_id`, `prior_version`, `prior_content_hash`, `prior_posture_level`) are checked, plus `mutate_for_posture_level` callability. PASS for attribute completeness.

**Side-effect surface note (see R2-F2):** `hasattr` invokes `__getattr__` / `__getattribute__` which a malicious adapter could implement with side effects (logging, lock acquisition, network I/O). Threat is bounded because the only call sites of `request_transition` are internal to envoy (Tier 2 wiring + Phase 03 ritual surface, both code-reviewed). Surface noted for future hardening (potentially upgrade to `isinstance(obj, type)` check + named-method introspection); not severity-elevating in Phase 01.

#### Probe 3: Tier 1 negative tests cover the rejection paths

**Command:**

```
grep -n "test_.*envelope.*raises\|test_envelope_with_non_callable" tests/tier1/test_posture_gate_5_step_fail_closed.py
```

**Output:**

```
1833:    def test_string_envelope_raises_type_error(self):
1846:    def test_dict_envelope_raises_type_error(self):
1860:    def test_partial_envelope_raises_type_error(self):
1880:    def test_envelope_with_non_callable_mutate_raises_type_error(self):
1903:    def test_envelope_none_accepted_on_ratchet_down(self):
1920:    def test_fail_closed_on_kwarg_check(self):
```

Six Tier 1 cases covering: string, dict, partial-shape dataclass, non-callable `mutate_for_posture_level`, legitimate `envelope=None` on demotion, fail-closed-no-side-effects on shape rejection. PASS.

**Disposition:** CLOSED. Helper position, attribute completeness, and negative-test coverage all aligned. See R2-F2 for the bounded side-effect surface note.

### F-3 (MEDIUM) — defensive guard ordering — CLOSED

#### Probe 1: defensive guard removed; Step 3e is the only raise

**Command:**

```
grep -n "raise PostureRatchetEnvelopeMissingError" envoy/authorship/posture_gate.py
```

**Output:**

```
933:                raise PostureRatchetEnvelopeMissingError(current=current, target=target)
```

ONE raise site, at line 933 (Step 3e), inside the `if target > current:` branch at line 896 — fires BEFORE any Ledger append (Step 5a is at line 979). The previously-orphan-causing defensive guard at line 939 is removed. PASS.

#### Probe 2: MyPy narrowing assertion is in place

**Command:** Read line 1022.

**Output:**

```python
assert envelope is not None  # nosec — narrowing assertion, Step 3e enforces
```

Static-narrowing assert replaces the runtime guard; if a future refactor accidentally drops Step 3e, this `assert` fails LOUDLY before `envelope.mutate_for_posture_level(target)` at line 1023 (rather than landing an orphan `posture_change`). PASS.

#### Probe 3: documentation of the closure rationale

**Command:** Read lines 1011-1020 (in-code comment).

**Output:** The block explicitly documents the F-3 closure rationale: "The correct structural defense is Step 3e raising before ANY Ledger write — moved earlier in this function. Removing the redundant guard here ALSO closes the orphan-posture_change risk per `rules/zero-tolerance.md` Rule 3." PASS.

**Disposition:** CLOSED. F-3's specific orphan-posture_change variant is eliminated by removing the defensive guard. BUT — the same structural failure mode (`posture_change` writes before a downstream raise) has been reintroduced at the F-2 invariant raise sites. See R2-F1.

### F-6 (MEDIUM) — write-only field — CLOSED with audit-only doc + read test

#### Probe 1: spec field-semantics block documents audit-only role

**Command:** (already verified in F-4 Probe 1) — `specs/envelope-model.md:96` contains "**Audit-only role:** `metadata.posture_level` is a mint-state audit annotation; the effective-posture derivation walks the Ledger's `posture_change` entries — no production read consumer dispatches on the envelope field's value." PASS.

#### Probe 2: Tier 1 read tests exist

**Command:**

```
grep -n "class TestPostureLevelMintStateRead\|def test_" tests/tier1/test_posture_gate_5_step_fail_closed.py | grep -A 5 "MintStateRead"
```

**Output:**

```
1943:class TestPostureLevelMintStateRead:
1968:    def test_default_posture_level_is_pseudo(self):
1976:    def test_mint_state_round_trips(self):
1987:    def test_mint_state_matches_canonical_posture_level_enum(self):
```

Three tests exercise the `metadata.posture_level` read path against `EnvelopeMetadata` — pinning the field as structurally non-orphan per `rules/orphan-detection.md` Rule 1. PASS.

**Disposition:** CLOSED. Spec documents audit-only role; Tier 1 tests pin the read path. The field is structurally non-orphan.

---

## Step 2 — New attack surfaces introduced by Shard 1 + Shard 2

### A. `PostureEnvelopeMutationInvariantError` user_message redaction audit

**Command:** Read lines 438-445.

**Output:**

```python
def __init__(self, *, reason: str) -> None:
    self.reason = reason
    self.user_message = (
        "There was a problem confirming the envelope update for this "
        "posture change. The change has not been recorded — please "
        "re-open Weekly Posture Review and try again."
    )
    super().__init__(f"PostureEnvelopeMutationInvariantError: {reason}")
```

The `user_message` is a **fixed string** that does NOT interpolate the attacker-controllable `reason`. It contains NO `envelope_id`, NO `principal_id`, NO `diff_hash`, NO `posture_level`. The `reason` lives ONLY on the internal `__cause__` chain (the `super().__init__()` argument) which is logged at ERROR but NOT surfaced to the channel adapter.

#### Probe: Tier 1 test pins the redaction invariant

**Command:**

```
grep -A 8 "test_invariant_error_carries_user_message" tests/tier1/test_posture_gate_5_step_fail_closed.py
```

**Output:**

```python
def test_invariant_error_carries_user_message(self):
    err = PostureEnvelopeMutationInvariantError(reason="test reason")
    assert hasattr(err, "user_message")
    assert isinstance(err.user_message, str)
    assert len(err.user_message) > 0
    # No internal jargon should leak into the user-facing string.
    assert "envelope_id" not in err.user_message
    assert "diff_hash" not in err.user_message
    assert "sha256" not in err.user_message
```

The test STRUCTURALLY pins the redaction — `envelope_id`, `diff_hash`, `sha256` MUST NOT appear in `user_message`. PASS.

**Verdict:** A. PASS per `rules/observability.md` Rule 8 — no schema-revealing identifier surfaces.

### B. `reason` field as attacker-controllable log payload

The `reason` parameter to `PostureEnvelopeMutationInvariantError.__init__` is interpolated into the `super().__init__()` message at line 445. The three production raise sites (lines 1033, 1041, 1049) interpolate attacker-controllable values into `reason`:

- Line 1033: `f"mutation.envelope_id mismatch: expected {envelope.envelope_id!r}, got {mutation.envelope_id!r}"` — both `envelope.envelope_id` (caller-supplied) and `mutation.envelope_id` (adapter-supplied) land in the exception message.
- Line 1041: `f"mutation.new_version must be prior_version+1: prior={envelope.prior_version}, new={mutation.new_version}"` — integers; bounded.
- Line 1049: `f"mutation.diff_hash must match 'sha256:<64-hex>' per specs/ledger.md § envelope_edit, got {mutation.diff_hash!r}"` — `mutation.diff_hash` is adapter-supplied.

**Threat shape:** A malicious adapter could supply an arbitrarily-large `mutation.envelope_id` / `mutation.diff_hash` string with control characters, ANSI escapes, or null bytes, polluting downstream logs / aggregator output via the exception's `__str__` representation.

**Mitigation in current code:** None at the exception-construction site. However:

- `envelope.envelope_id` flows through the gate from a caller-supplied object that should already be bounded (the canonical hash shape `sha256:<hex>` is enforced by upstream `EnvelopeCompiler`).
- `mutation.envelope_id` / `mutation.diff_hash` are adapter-supplied and currently NOT length-bounded or charset-checked at the exception construction site.
- The exception only leaves the gate as a raised Python object; the `extra=` keys on the structured logger (which DO have charset bounds per `_ENVELOPE_ID_HASH_PATTERN`) are not the surface used.

**Verdict:** B. LOW. The threat assumes an exception-string-aggregator pipeline; bounded by repo-internal callers in Phase 01. Out-of-scope finding for Round 2 disposition; logged for awareness.

### C. `_is_posture_carrying_envelope` side-effect surface

**Command:** Read lines 638-644.

**Output:** Five `hasattr(obj, ...)` / `getattr(obj, ...)` calls on a caller-supplied object. `hasattr` invokes the descriptor protocol via `__getattribute__` / `__getattr__`, which a malicious adapter can implement with arbitrary side effects (logging, network I/O, lock acquisition).

**Threat shape:** Caller supplies an envelope object whose `__getattr__` performs network I/O or holds a lock indefinitely. Each `hasattr` call triggers the side effect. Five attribute checks → five side-effect invocations.

**Mitigation in current code:** None at the helper site. The helper is positioned before Step 1 (line 852, before line 860) — failing the side-effect-laden adapter at the kwarg boundary, BUT the side effects fire DURING the `hasattr` enumeration regardless of the boolean outcome.

**Verdict:** C. MEDIUM (R2-F2 below). Bounded by trusted internal callers in Phase 01, but the helper is the documented stable surface and any future caller wiring an externally-supplied envelope (e.g., a future API ingress) inherits this surface.

### D. Tier 2 regression test `test_canonical_bytes_module_documents_single_point_hash_design` resilience

The test at `tests/tier2/test_envelope_hash_mint_time_cached.py:234-262` reads the `canonical_bytes.py` source as text and asserts two specific phrases are present. If a refactor drops the design-intent docstring, the test FAILS — forcing the author to re-state the contract OR explicitly remove it.

**Probe verification:**

```
Required phrases checked:
  "single-point hash production at compile time"
  "no drift surface between consumers"

Current docstring at envoy/envelope/canonical_bytes.py:73-83 contains both phrases (verified in journal/0023 §3).
```

The test will FAIL the moment the docstring is dropped, OR the moment the canonical phrases are reworded. Structural contract preserved at the test level. PASS.

### E. Tier 2 mint-time cache test uses `is`-identity correctly

The test at lines 264-318 uses `compiled.canonical_bytes is first_canonical` (NOT `==`). This catches the failure mode F-5's threat model assumes (on-access re-derivation → fresh bytes object → equal value, different `id()`). A property-based recomputation would return a new bytes object on each access, failing the `is`-check, while passing an `==`-check. Structural defense correct. PASS.

---

## Step 3 — Cross-spec invariant sweep (per `rules/specs-authority.md` Rule 5b)

Shard 1 edited `specs/envelope-model.md` § field-semantics. Required sibling re-derivation across every spec referencing `posture_level`, `envelope_edit`, or `posture_change`.

### Command

```
grep -rn "posture_level\|envelope_edit\|posture_change" specs/
```

### Findings per sibling

#### `specs/posture-ladder.md`

- **Line 41:** "**Envelope version bump** (specs/envelope-model.md) — new posture is part of the envelope schema; any posture change is an `envelope_edit`."

  Context: this line is in the **Ratchet-up section** (`### Ratchet-up (promotion)`). "Any posture change" here refers contextually to "any RATCHET-UP posture change," which the mint-state interpretation honors. Acceptable within the section's scope.

- **Line 52:** "Demotion NEVER requires authorship; it is always permitted, always Genesis-signed, always a `posture_change` entry."

  Implicit asymmetry — does NOT mention `envelope_edit` on demotion, consistent with the mint-state interpretation. PASS.

- **Line 128:** `return min(p.posture_level for p in principals if p in action.consenting_principals)` — Shared Household composition reads `posture_level` from each principal. Under the mint-state interpretation, this reads the envelope's MINT-time posture, not the effective posture. **Potential LOW finding:** Shared Household composition may incorrectly use mint-state instead of effective posture from Ledger walk. This is Phase 03+ scope (per `specs/posture-ladder.md` line 178 "Shared Household composition" deferred), but the spec hint at line 128 is now misleading.

- **Line 203:** `(envelope=None) and the once-only mutate_for_posture_level()` — refers to ratchet-up path; aligned with current code. PASS.

#### `specs/ledger.md`

- **Line 60:** `posture_change` entry type. Schema documented at lines 239-253. Owner: `specs/posture-ladder.md`. No mint-state contradiction. PASS.
- **Line 52:** `envelope_edit` entry type. Schema documented at lines 107-114. No contradiction. PASS.

#### `specs/cross-domain-flows.md`

- No matches for `posture_level`. PASS.

#### `specs/shared-household.md`

- **Line 60:** `posture_level` enum form documented. PASS.
- **Line 102:** `composed.effective_posture = min(p.posture_level for p in principals)` — same mint-state-vs-effective-posture ambiguity as `specs/posture-ladder.md:128`. Same disposition: Phase 03+ scope; sibling-drift LOW finding (R2-F3).

#### `specs/runtime-abstraction.md`

- **Line 212:** "Posture-as-cryptographic-attribute vs posture-as-envelope-metadata — current choice: envelope-metadata (re-derivable from Ledger). Phase 04 may cryptographically attest." — Aligned with mint-state interpretation ("re-derivable from Ledger" IS the audit-walk path). PASS.

### Cross-spec disposition

- Two sibling specs (`posture-ladder.md` Shared Household line 128, `shared-household.md` line 102) read `posture_level` for composition without specifying that the value is mint-state. Under the new mint-state interpretation, this could route to incorrect effective-posture composition.
- Phase 03+ scope (Shared Household composition is deferred). Surfaced as R2-F3 LOW.

---

## Findings table — Round 2

| ID    | Severity | Surface                                                                                              | File:line                                                                                                | Disposition                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ----- | -------- | ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R2-F1 | HIGH     | F-2 invariant raises produce orphan `posture_change` Ledger entry — F-3 failure mode reintroduced    | `envoy/authorship/posture_gate.py:979` (Step 5a append), lines `1033, 1041, 1049` (F-2 invariant raises) | The Shard 1 F-2 invariant checks fire BETWEEN Step 5a's `posture_change` append (line 979) AND Step 5b's `envelope_edit` append (line 1065). On any F-2 invariant violation (envelope_id mismatch / version regression / malformed diff_hash), the `posture_change` is COMMITTED but `envelope_edit` is never appended. Per `specs/posture-ladder.md` § Ratchet-up #3 ("any posture change is an `envelope_edit`") AND `rules/zero-tolerance.md` Rule 3, a ratchet-up that emits `posture_change` WITHOUT `envelope_edit` violates the spec's pairing invariant. The Tier 1 tests at `test_posture_gate_5_step_fail_closed.py:1667/1693/1722/1748` STRUCTURALLY pin this orphan behavior as deliberate (`assert types == ["posture_change"]`) — but the assertion shape is the failure mode F-3 was meant to close. Disposition options: (a) move F-2 invariant checks BEFORE Step 5a's append (call `mutate_for_posture_level()` and validate invariants, THEN append both entries atomically); (b) wrap Steps 5a + 5b in a transactional boundary so a Step 5b raise rolls back Step 5a; (c) update the spec to explicitly permit orphan `posture_change` on Step 5b validation failure (least defensible — institutionalizes the failure mode). **Recommended:** (a) — restructure as: validate first, append posture_change, append envelope_edit. The mutation invariants are PRECONDITIONS to the entire paired emission, not POSTCONDITIONS of Step 5a. |
| R2-F2 | MEDIUM   | `_is_posture_carrying_envelope` invokes `hasattr` on attacker-supplied objects — side-effect surface | `envoy/authorship/posture_gate.py:619-644`                                                               | The structural Protocol check performs 5 attribute lookups via `hasattr` / `getattr` on a caller-supplied object. `hasattr` triggers `__getattribute__` / `__getattr__`, which a malicious adapter can implement with side effects (network I/O, lock acquisition, log emission). Each `hasattr` triggers the descriptor protocol regardless of the boolean outcome. Threat is bounded in Phase 01 (only internal callers; Tier 2 wiring + future Phase 03 ritual). Future caller wiring an externally-supplied envelope (e.g., API ingress) inherits this surface. Disposition options: (a) accept threat in Phase 01 (bounded); (b) replace `hasattr` enumeration with a `isinstance(obj, _PostureCarryingEnvelopeBaseClass)` nominal check — requires converting the Protocol to a `@runtime_checkable` Protocol AND requires every adapter to nominally inherit; (c) add a type-aware guard (`type(obj).__module__ == "envoy."` or similar) before the `hasattr` enumeration. **Recommended:** (a) — accept in Phase 01 with a code-comment Phase 02 hardening todo + a `_PostureCarryingEnvelope` docstring note documenting the side-effect surface.                                                                                                                                                                                                                                                                                                     |
| R2-F3 | LOW      | Cross-spec drift — Shared Household composition reads `posture_level` without mint-state framing     | `specs/posture-ladder.md:128`, `specs/shared-household.md:102`                                           | Both spec sites compute `min(p.posture_level for p in principals)` for Shared Household composition. Under the new mint-state interpretation (journal/0022), `posture_level` is the mint-time annotation, not the effective posture. Composition over mint-state values produces incorrect MIN when one principal has demoted (Ledger shows lower; envelope shows mint-time higher). Phase 03+ scope (Shared Household composition is deferred per `specs/posture-ladder.md:178`), but the spec hints at line 128 / line 102 are now misleading for future implementers. Disposition: add a one-line note at each composition site clarifying that the effective posture for composition derives from the Ledger walk, not the envelope field; OR defer to Phase 03 implementer alongside the composition algorithm itself. **Recommended:** add the clarifying note now (minimal spec edit) so future implementers do not silently bake mint-state into composition.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |

**Summary by severity:**

- CRITICAL: 0
- HIGH: 1 (R2-F1 — same-class regression of Round 1 F-3)
- MEDIUM: 1 (R2-F2 — side-effect surface, Phase-02 hardening candidate)
- LOW: 1 (R2-F3 — cross-spec drift, Phase-03 implementer hazard)
- PASS: 6 surfaces (F-2 invariant wiring + AST coverage, F-4 closure full, F-5 false-positive determination, F-1 helper completeness, F-3 defensive-guard removal, F-6 read-test landing)

---

## Receipts

- Source files read with line citations: `envoy/authorship/posture_gate.py`, `envoy/envelope/types.py`, `tests/tier1/test_posture_gate_5_step_fail_closed.py`, `tests/tier2/test_posture_gate_wiring.py`, `tests/tier2/test_envelope_hash_mint_time_cached.py`, `specs/envelope-model.md`, `specs/posture-ladder.md`, `specs/ledger.md`, `specs/shared-household.md`, `specs/runtime-abstraction.md`, `envoy/authorship/__init__.py`.
- Greps executed: `PostureEnvelopeMutationInvariantError`, `posture_level`, `mutate_for_posture_level`, `raise PostureEnvelopeMutationInvariantError`, `_ledger.append`, `from_json|from_dict.*Envelope|loads.*Envelope`, `_is_posture_carrying_envelope`, `test_.*invariant`, `Mint-state semantics|Audit-only role`, `posture_change|envelope_edit`.
- AST-walked: `request_transition` body line ordering (Step 3e raise → Step 5a append → mutation invariants → Step 5b append).
- Journal entries read: `journal/0021-DECISION-t-02-33-envelope-edit-pairing-design.md`, `journal/0022-DECISION-posture-level-mint-state-interpretation.md`, `journal/0023-DISCOVERY-envelope-hashes-mint-time-cached-f5-false-positive.md`.
- Test-assertion shape verified: Tier 1 `test_envelope_id_mismatch_raises` (line 1643), `test_new_version_regression_raises` (1671), `test_malformed_diff_hash_raises` (1726) — all assert `types == ["posture_change"]` (orphan structural pin).

---

## Same-class fix-immediately candidate (per `rules/autonomous-execution.md` Rule 4)

R2-F1 is structurally the same class as Round 1 F-3 (orphan `posture_change` from a Step-5b-side failure landing after Step 5a). The fix is mechanical: move the `mutate_for_posture_level()` invocation + invariant checks to BEFORE the Step 5a `await self._ledger.append(entry_type="posture_change", ...)` call. The shard scope is ~30 LOC + 3 Tier 1 test updates (the orphan-pin assertions flip to no-Ledger-entry-on-violation).

Per Rule 4 ("Fix-Immediately When Review Surfaces A Same-Class Gap Within Shard Budget"): this fits well within the shard budget (≤500 LOC load-bearing, ≤5 invariants). **Recommendation:** spawn the fix shard in the same session.

R2-F3 is a 2-line spec edit per site; also fits within the same-class shard budget if the orchestrator picks it up.

---

## Auditor notes for orchestrator

- The HIGH count is 1 (R2-F1). It is structurally identical to Round 1 F-3 but at a NEW site — the Shard 1 F-2 closure introduced the very failure mode F-3 was meant to close, at the F-2 invariant check sites instead of the defensive-guard site. The structural pattern ("validate AFTER half the paired write") repeats across the surface; the fix is to make ALL Step 5 invariant validation precede ALL Step 5 writes.
- Shard 1 PR description and Shard 2 PR description claim "F-2 closed" and "F-3 closed" — and they ARE individually closed AT their original sites. The R2-F1 regression is a NEW instance of the SAME failure class, not a re-emergence of Round 1 F-3. The disposition is a follow-up shard, not a rollback of Shard 1 / 2.
- R2-F2 is a documented design tradeoff (structural Protocol vs nominal check). Phase 02 hardening candidate; surface noted with no severity-elevation.
- R2-F3 is sibling-spec drift surfaced by `rules/specs-authority.md` Rule 5b's full-sibling re-derivation. The two-site spec note is minimal and prevents Phase 03 implementer from silently baking mint-state into composition.
- The Round 1 audit at SHA `7598578` is durably citable as the receipt for Round 2's closure-verification claims; per `rules/verify-resource-existence.md` MUST-4 this is the external-receipt grounding the convergence verdict cites.
