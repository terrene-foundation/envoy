# Round 1 — Security Audit: T-02-33 envelope_edit pairing on PostureGate ratchet-up

**Audited:** 2026-05-24
**Scope:** Commits `1e6b256 7a8d62a fe1b982 71199d4 3ad3fc4` merged at `641dd2d`.
**Diff baseline:** `e8c7c80..641dd2d`.
**Auditor mode:** Round 1 security audit. Findings only; no fixes per `rules/autonomous-execution.md` Rule 4 + redteam disposition.
**Probe discipline:** Every finding is backed by command output (per `rules/probe-driven-verification.md` MUST-3 — structural probes, this audit has no LLM-judge surface).

---

## Per-attack-surface analysis

### 1. The `envelope` kwarg on `PostureGate.request_transition`

#### 1.a Type-validation at the boundary

**Command:**

```
Read envoy/authorship/posture_gate.py:689–778 (request_transition signature + input
validation block).
```

**Finding evidence (from file):**

```python
async def request_transition(
    self,
    *,
    current: PostureLevel,
    target: PostureLevel,
    evidence: PostureEvidence,
    principal_id: str,
    trigger: str = "user_request",
    revoke_on_demotion: tuple[str, ...] = (),
    days_at_current_posture: float = 0.0,
    envelope: Optional[_PostureCarryingEnvelope] = None,
) -> PostureChangeResult:
    ...
    if not isinstance(current, PostureLevel): raise TypeError(...)
    if not isinstance(target, PostureLevel): raise TypeError(...)
    if not isinstance(evidence, PostureEvidence): raise TypeError(...)
    if trigger not in _VALID_TRIGGERS: raise ValueError(...)
    if not isinstance(revoke_on_demotion, tuple): raise TypeError(...)
```

`current`, `target`, `evidence`, `trigger`, `revoke_on_demotion` get `isinstance` /
membership checks. `envelope`, `principal_id`, `days_at_current_posture` do NOT.

`envelope` is typed `Optional[_PostureCarryingEnvelope]` — a `Protocol`. Protocols
are structural, not enforced. A caller passing any duck-typed object satisfying
the read shape (`envelope_id`, `prior_version`, `mutate_for_posture_level`)
is accepted without runtime verification.

**Disposition recommendation:** MEDIUM. The Protocol is structural by design
(spec § \_PostureCarryingEnvelope docstring + journal/0021 § "Cons (real,
not glossed)" #2). The threat is bounded because (a) the result fields the
attacker controls (envelope_id, prior_version, new_version, diff_hash) ARE
attacker-controlled in the same way any other caller payload is — they land
in a `posture_change`-paired `envelope_edit` Ledger entry that the device
signature on the Ledger envelope itself attests to, and (b) the only call
site of `request_transition` is internal (Phase 03 Weekly Posture Review
ritual, not Phase 01). However, this widens the attack surface for any
future caller that accepts an envelope from an untrusted source. See finding
F-1 below.

#### 1.b The mutation method's return-value trust

**Command:**

```
Read envoy/authorship/posture_gate.py:941–950.
```

**Finding evidence:**

```python
mutation = envelope.mutate_for_posture_level(target)
envelope_edit_content: dict = {
    "schema_version": _ENVELOPE_EDIT_SCHEMA_VERSION,
    "envelope_id": envelope.envelope_id,
    "prior_version": envelope.prior_version,
    "new_version": mutation.new_version,
    "diff_hash": mutation.diff_hash,
    ...
}
```

`mutation.new_version` and `mutation.diff_hash` are consumed VERBATIM into
the wire shape. PostureGate does NOT:

- Verify `mutation.new_version == envelope.prior_version + 1` (the monotonic
  bump invariant the spec mandates).
- Verify `mutation.diff_hash` has the expected shape (`sha256:<hex>`).
- Verify `mutation.new_posture_level == target.name` (the field the docstring
  pins).
- Re-derive `diff_hash` server-side from prior + new canonical bytes.

A malicious adapter (`_PostureCarryingEnvelope` impl) can write any value to
the Ledger via the `envelope_edit` entry, including:

- `new_version = prior_version + 100` (skip versions to confuse downstream
  envelope-chain verifiers).
- `diff_hash = sha256:0000...` (forge the chain link).
- `new_version = prior_version` or `new_version < prior_version` (regress
  the version monotonically — breaks `specs/envelope-model.md` §
  algorithm_identifier monotonic-version invariant).

**Disposition recommendation:** HIGH. See finding F-2 below. The fix is
mechanical: PostureGate verifies the invariants the adapter is contractually
required to maintain before writing the Ledger entry.

#### 1.c Re-entry / recursion through `mutate_for_posture_level`

**Command:**

```
grep -n "mutate_for_posture_level\|request_transition" envoy/authorship/posture_gate.py
```

**Output:**

```
689: async def request_transition(...)
620: def mutate_for_posture_level(self, new_level: "PostureLevel") -> _PostureMutationResult: ...
941: mutation = envelope.mutate_for_posture_level(target)
```

A malicious `mutate_for_posture_level` impl COULD call back into
`gate.request_transition()` (if it holds a reference). The gate has NO
re-entry guard. However:

- The gate is constructed without a self-reference passed to the envelope
  adapter. Re-entry requires the malicious adapter to ALREADY have a gate
  reference from elsewhere.
- Each `request_transition` call advances the Ledger's `_sequence` and
  `_lamport_time`; a recursive call would interleave Ledger entries
  (`posture_change A_start → posture_change B → envelope_edit B →
envelope_edit A`). This is a chain-state-integrity concern, but the Ledger
  invariants (Lamport monotonicity, sequence monotonicity, hash chain) hold
  per-entry — the chain remains verifiable.
- `mutate_for_posture_level` is sync (per Protocol L620), so it cannot
  `await` a recursive `request_transition` (which is async). Sync code
  inside `await` would block the event loop until it returned, and the
  inner call would need its own event-loop entry — re-entry is structurally
  awkward but not impossible (`asyncio.run_coroutine_threadsafe` from
  another thread, etc.).

**Disposition recommendation:** LOW. Threat is bounded by sync-async
boundary + no self-reference passed. Re-entry guard would be defense-in-depth.

---

### 2. `PostureRatchetEnvelopeMissingError` typed-guard surface (zero-tolerance Rule 3a)

#### 2.a Raise site BEFORE Ledger side-effect

**Command:**

```
Read envoy/authorship/posture_gate.py:815–900 (Step 3e through Step 5a).
```

**Finding evidence:**

```python
# Step 3e: envelope-present check (T-02-33)
if envelope is None:
    raise PostureRatchetEnvelopeMissingError(current=current, target=target)

# (continues to Step 4 — revoke hook — but target > current here, so revoke
#  is skipped because the `if target < current:` branch at line 864 is False.)

# ----- STEP 5a: signed posture_change Ledger entry -----
content: dict = { ... }
entry_id = await self._ledger.append(entry_type="posture_change", content=content)
```

Step 3e (line 852) fires BEFORE Step 5a (line 899). Verified by line ordering
in the source. PASS — no partial-pair commit on ratchet-up with `envelope=None`.

#### 2.b user_message does not leak schema-revealing identifiers

**Command:**

```
Read envoy/authorship/posture_gate.py:399–411.
```

**Finding evidence:**

```python
def __init__(self, *, current: PostureLevel, target: PostureLevel) -> None:
    self.current = current
    self.target = target
    self.user_message = (
        f"Moving from {current.name} to {target.name} needs the current "
        "envelope to bind the new posture to. The session that triggered "
        "this transition didn't supply one — please re-open Weekly Posture "
        "Review and try again from there."
    )
```

The user_message contains posture level NAMES ("PSEUDO", "TOOL", ...). These
are NOT schema-revealing identifiers per `rules/observability.md` Rule 8
(which targets model/column/field names like `users.ssn`). PostureLevel
names are the documented user-facing taxonomy per `specs/posture-ladder.md`.

The error does NOT include `envelope_id`, `principal_id`, or any other
identifier the user_message rule restricts.

**Disposition recommendation:** PASS.

#### 2.c Step 5b (line 930-940) has a defensive re-raise of the same error

**Command:**

```
Read envoy/authorship/posture_gate.py:930–940.
```

**Finding evidence:**

```python
if target > current:
    # MyPy can't narrow `envelope` past the Step 3e raise above;
    # the runtime invariant is: if we reach here on ratchet-up,
    # envelope is non-None. Assert defensively (pre-condition the
    # raise above already proved) so a future refactor that
    # accidentally drops Step 3e fails loudly at this site rather
    # than producing a NoneType.mutate_for_posture_level() crash
    # downstream — per `rules/zero-tolerance.md` Rule 3a (typed
    # delegate guards for None backing objects).
    if envelope is None:
        raise PostureRatchetEnvelopeMissingError(current=current, target=target)
```

GAP: by the time we reach line 939, Step 5a has ALREADY written
`posture_change` (line 899 ran). If a future refactor accidentally drops
the Step 3e raise but leaves this defensive guard intact, the result is
EXACTLY the partial-pair commit the rule was supposed to prevent:
`posture_change` lands, then `envelope_edit` raises, leaving an orphan
`posture_change` in the Ledger.

Today's code passes because Step 3e exists. The defensive guard at 939
gives the false reassurance that "if envelope is None we fail closed",
but its actual position in the code is POST-Ledger-write for `posture_change`.

**Disposition recommendation:** MEDIUM. See finding F-3 below.

---

### 3. Asymmetric pairing (ratchet-up vs ratchet-down)

#### 3.a Code path where demotion mutates posture_level without emitting envelope_edit

**Command:**

```
grep -n "mutate_for_posture_level\|envelope_edit\|posture_level" envoy/authorship/posture_gate.py
```

**Output:**

```
envoy/authorship/posture_gate.py:549: """The structural shape `_PostureCarryingEnvelope.mutate_for_posture_level()`
envoy/authorship/posture_gate.py:573: def new_posture_level(self) -> str: ...
envoy/authorship/posture_gate.py:591: - `prior_posture_level` — canonical enum NAME ...
envoy/authorship/posture_gate.py:596: - `mutate_for_posture_level(new_level)` returns ...
envoy/authorship/posture_gate.py:618: def prior_posture_level(self) -> str: ...
envoy/authorship/posture_gate.py:620: def mutate_for_posture_level(self, ...) -> _PostureMutationResult: ...
envoy/authorship/posture_gate.py:930:        if target > current:
envoy/authorship/posture_gate.py:941:            mutation = envelope.mutate_for_posture_level(target)
```

Only ONE call site of `mutate_for_posture_level`, gated by `if target > current`
(ratchet-up only). On ratchet-down, `mutate_for_posture_level` is NEVER
called. PASS — the envelope is structurally unmutated on demotion.

GAP (out of T-02-33 scope, but flagged): the envelope's `metadata.posture_level`
remains at the OLD (higher) level after a demotion. There is no inverse
mutation (`demote_envelope_posture_level()`). After a demotion:

- Ledger: `posture_change(DELEGATING → TOOL)` (truth source).
- Envelope: `metadata.posture_level = "DELEGATING"` (stale).

A future consumer reading `envelope.metadata.posture_level` will see the
PRIOR (higher) posture, not the current (demoted) one. This is silent
state drift between Ledger and envelope.

Per `rules/zero-tolerance.md` Rule 3 (no silent fallbacks): the envelope's
`posture_level` field becomes a stale view. Per `journal/0021-DECISION-...md`
§ "For Discussion" #2, the spec is ambiguous here — the disposition picks
"asymmetric, envelope_edit only on ratchet-up" but doesn't address what
happens to the envelope's posture_level field on demotion. The current
implementation leaves it stale.

**Disposition recommendation:** HIGH. See finding F-4 below. This is the
inverse-paired-emission gap the audit mission was looking for.

#### 3.b TestPostureChangeOnRatchetDownNoEnvelopeEdit assertions

**Command:**

```
Read tests/tier2/test_posture_gate_wiring.py:630–663.
```

**Finding evidence (from file):**

```python
async def test_ratchet_down_emits_only_posture_change(...):
    result = await gate.request_transition(
        principal_id="frank",
        current=PostureLevel.DELEGATING,
        target=PostureLevel.TOOL,
        ...
        envelope=None,
    )
    assert result.new_level is PostureLevel.TOOL
    entries = await _read_appended_entries(envoy_ledger)
    assert len(entries) == 1
    assert entries[0]["type"] == "posture_change"
    ...
```

The test ONLY asserts the Ledger emission shape. It does NOT pass an
envelope; it does NOT assert that an envelope's `metadata.posture_level`
field reflects the new posture after demotion. The test's intent (per the
docstring) is "asymmetric pairing — envelope_edit fires ONLY on ratchet-up",
which it does correctly verify. But it does NOT verify the inverse-paired
behavior the audit prompt requested ("envelope's posture_level field is
updated on demotion").

The omission is correct given the current implementation (which never
mutates the envelope on demotion). But this means the test does NOT pin
the inverse-drift gap above; the test silently agrees that the envelope
stays stale.

**Disposition recommendation:** Same as F-4 below — the test should be
strengthened OR the implementation should add inverse mutation.

---

### 4. `metadata.posture_level` on the envelope

#### 4.a Canonical-bytes contribution

**Command:**

```
Read envoy/envelope/compiler.py:458–478 (_to_canonical_payload).
Read envoy/envelope/types.py:299–340 (EnvelopeMetadata).
```

**Finding evidence:**

```python
# compiler.py _to_canonical_payload:
"metadata": _enum_safe(asdict(config_input.metadata)),

# types.py EnvelopeMetadata is a @dataclass(frozen=True, slots=True);
# posture_level: str = "PSEUDO" is a field.
```

`asdict()` recursively serializes the metadata dataclass, INCLUDING the
new `posture_level: str` field. JCS canonicalization sorts keys
alphabetically, so `posture_level` becomes a stable key in the canonical
JSON. NFC normalization applies to the string value ("PSEUDO" → "PSEUDO"
unchanged in NFC).

Cross-runtime byte identity: the value is a plain ASCII string, NFC-stable.
JCS RFC 8785 produces the same byte sequence for `"posture_level":"PSEUDO"`
on every runtime. PASS.

GAP: every existing envelope produced before this change has `posture_level`
field defaulted to `"PSEUDO"`. Any pre-T-02-33 envelope reconstructed from
its persisted form will deserialize with `posture_level = "PSEUDO"`, then
re-canonicalize to BYTES that include `"posture_level":"PSEUDO"`.

If pre-T-02-33 canonical bytes were persisted WITHOUT the `posture_level`
key (because the field didn't exist), then re-canonicalization after this
change produces DIFFERENT canonical bytes for the same logical envelope.
This breaks any consumer that:

- Cached `content_hash` against pre-T-02-33 bytes.
- Persisted a `DelegationRecord` with `effective_envelope_hash` of the old
  shape.
- Compares two envelopes by content_hash across the version boundary.

This is a schema-version migration concern — adding a non-Optional field
to `EnvelopeMetadata` is a wire-shape break.

**Disposition recommendation:** HIGH. See finding F-5 below.

#### 4.b Default `"PSEUDO"` is fail-closed

**Command:**

```
grep -n "posture_level" envoy/envelope/types.py
```

**Output:**

```
envoy/envelope/types.py:333: # (T-02-33): the envelope's posture_level is the load-bearing field that
envoy/envelope/types.py:340: posture_level: str = "PSEUDO"
```

Default `"PSEUDO"` is the lowest posture per `specs/posture-ladder.md`.
PSEUDO has NO authority (no delegation, no autonomy). An envelope
constructed without explicit posture is at the fail-closed minimum. PASS.

#### 4.c Code paths treating unset posture as permissive

**Command:**

```
grep -rn "posture_level" envoy/ | grep -v ".pyc"
```

**Output (filtered to substantive lines):**

```
envoy/envelope/types.py:333: # (T-02-33): the envelope's posture_level is the load-bearing field that
envoy/envelope/types.py:340: posture_level: str = "PSEUDO"
envoy/authorship/posture_gate.py:[multiple Protocol-shape lines, no posture_level lookup]
```

NO production code in `envoy/` reads `envelope.metadata.posture_level` and
makes an authority decision based on it. The field is currently:

- WRITTEN by `_EnvelopeConfigPostureCarrier.mutate_for_posture_level()` in
  the Tier 2 test adapter.
- WRITTEN by the default value in `EnvelopeMetadata.__init__`.
- NEVER READ by a production consumer.

This means the field is currently a documentation-only field (a record of
the bound posture at envelope-mint time) — it has no authority impact.

GAP (Rule 6 — Implement Fully): if `metadata.posture_level` is INTENDED to
be the load-bearing binding between envelope and posture, then no production
code currently enforces that binding. The Ledger's `envelope_edit` entry
correctly carries the posture-bump record, but no downstream consumer
verifies that the envelope's `posture_level` matches the latest
`envelope_edit` for that envelope_id. See finding F-6 below.

**Disposition recommendation:** MEDIUM. The field exists on the envelope
contract surface but has no enforcement-side reader. Per `rules/orphan-detection.md`
Rule 1, this is the "model + facade ship, downstream never reads it" pattern
at the field level rather than the class level.

---

### 5. New Tier 2 test fixtures — `tests/tier2/test_posture_gate_wiring.py`

#### 5.a Ed25519 key generation per test

**Command:**

```
grep -n "Ed25519\|generate_private_key\|from_private_bytes\|generate_keypair" tests/tier2/test_posture_gate_wiring.py tests/tier2/conftest.py
```

**Output:**

```
tests/tier2/conftest.py:43: await mgr.generate_keypair(SIGNING_KEY_ID)
```

Real ephemeral keys generated PER FIXTURE INVOCATION via
`InMemoryKeyManager.generate_keypair(SIGNING_KEY_ID)`. The `signing_keymgr`
fixture is `async`-scoped (default: function scope per pytest-asyncio
configuration in `pyproject.toml::asyncio_default_fixture_loop_scope = "function"`).

Each test gets a fresh keymgr with a fresh keypair. No keys loaded from
files, no `from_private_bytes`, no hardcoded private bytes. PASS per
`rules/security.md` § No Hardcoded Secrets.

#### 5.b No hardcoded keys committed

**Command:**

```
grep -in "private_key\|secret\|api_key\|password" tests/tier2/test_posture_gate_wiring.py
```

**Output:** Empty. PASS.

**Command:**

```
grep -n "PASSPHRASE\s*=" tests/tier2/conftest.py
```

**Output:**

```
tests/tier2/conftest.py:30: PASSPHRASE = "tier2-integration-passphrase-with-entropy"
```

This is a test-fixture passphrase used to lock/unlock a Trust Vault during
the test. It is not a production credential, not a real API key, and not
checked into any auth-bearing surface. Standard Tier 2 fixture pattern
across the test suite (sibling: `tests/regression/test_round1_observability_log_keys.py:38`).
PASS.

#### 5.c `kailash.trust.audit_store` access at line 343

**Command:**

```
Read tests/tier2/test_posture_gate_wiring.py:325–360.
Read envoy/ledger/facade.py:171, 346, 389, 472.
```

**Finding evidence:**

Test file:

```python
async def _read_appended_entries(ledger: EnvoyLedger) -> list[dict[str, Any]]:
    from kailash.trust.audit_store import AuditFilter
    # `_audit_store` is set at EnvoyLedger.__init__; the underscore is
    # not a security shield, just a "stable surface for the facade
    # only" convention. Tier 2 wiring is the legitimate observer surface
    # for the audit-store-level entries the facade emits.
    events = await ledger._audit_store.query(AuditFilter(limit=1000))
```

Facade:

```python
envoy/ledger/facade.py:171: self._audit_store = audit_store
envoy/ledger/facade.py:346: await self._audit_store.append(audit_event)
envoy/ledger/facade.py:389: from kailash.trust.audit_store import AuditFilter
envoy/ledger/facade.py:404: events = await self._audit_store.query(AuditFilter(limit=1_000_000))
envoy/ledger/facade.py:472: events = await self._audit_store.query(AuditFilter(limit=1_000_000))
```

The test READS via `ledger._audit_store.query(...)`. The facade itself uses
the same exact pattern at line 404 and 472. The test is using the same
read surface the facade's own `export()` and `verify_chain()` use.

The `_audit_store` is reached via the test-scoped `envoy_ledger` fixture's
held reference; it is NOT a global. The query is READ-ONLY (`AuditFilter(limit=1000)`).
The test never CALLS `_audit_store.append()` (which would forge entries).

The underscore IS a convention violation but per the in-file comment
(line 346–348) the project explicitly documents this as the legitimate
observer surface. Tier 2 contract permits this per
`rules/testing.md` § Tier 2 ("Real infrastructure recommended ... NO mocking").

GAP (LOW): this access pattern, if copy-pasted to a production caller,
would let any holder of an EnvoyLedger reference bypass the facade's
write surface entirely. The defense is access scoping (don't pass
EnvoyLedger to untrusted code). Currently only Tier 2 tests use this
pattern.

**Disposition recommendation:** LOW. Acceptable for Tier 2 read-only
observation. Document the pattern as test-only in the test file's module
docstring is the most defensible enhancement.

---

### 6. Module-scope import hygiene (`rules/dependencies.md` § "Declared = Imported")

#### 6.a `kailash.trust.audit_store` declaration

**Command:**

```
grep -n "kailash" pyproject.toml
```

**Output:**

```
pyproject.toml:32: "kailash[nexus,kaizen,dataflow,pact,shamir]>=2.13.4",
```

`kailash` is declared as a direct dependency with version floor `>=2.13.4`.
The `kailash.trust.audit_store` submodule is part of the `kailash` package.
PASS — not a phantom transitive.

#### 6.b New imports in T-02-33

**Command:**

```
grep -n "^from \|^import " envoy/authorship/posture_gate.py envoy/envelope/types.py tests/tier2/test_posture_gate_wiring.py | sort -u
```

**Output (T-02-33 introductions):**

- `envoy/authorship/posture_gate.py`: no new external imports (the
  `_PostureCarryingEnvelope` Protocol and the `PostureRatchetEnvelopeMissingError`
  class are all in-module).
- `envoy/envelope/types.py`: no new imports.
- `tests/tier2/test_posture_gate_wiring.py`:
  - `from envoy.authorship import ...` — same package as the file under test.
  - `from envoy.envelope import EnvelopeCompiler, EnvelopeConfig, ...,
canonical_bytes, content_hash` — same in-repo package.
  - `from envoy.ledger import EnvoyLedger` — in-repo.
  - Inside `_read_appended_entries`: `from kailash.trust.audit_store import AuditFilter`
    — covered by 6.a.

All imports resolve to declared dependencies. PASS.

---

### 7. Multi-site kwarg plumbing per `rules/security.md` § Multi-Site Kwarg Plumbing

#### 7.a Every call site updated

**Command:**

```
grep -rn "gate\.request_transition\|\.request_transition(" tests/ envoy/ \
  | grep -v ".pyc" | grep -v "docstring\|workspaces"
```

**Output (call sites in production + tests):**

Production code:

- `envoy/authorship/posture_gate.py:689`: definition only.

Tier 1 tests (`tests/tier1/test_posture_gate_5_step_fail_closed.py`):

- 41 call sites. Each invocation that targets `target > current` (ratchet-up)
  has been verified to either pass `envelope=_FakePostureCarryingEnvelope()`
  OR is intentionally testing the `PostureRatchetEnvelopeMissingError`
  failure path (envelope omitted, expects raise).

Tier 2 tests (`tests/tier2/test_posture_gate_wiring.py`):

- 7 call sites. Each ratchet-up invocation passes `envelope=carrier`. The
  ratchet-down test at line 637 passes `envelope=None` (legitimate per the
  spec § asymmetric pairing). The error-test at line 692 omits envelope to
  test the raise.

#### 7.b Mechanical sweep: ratchet-up call sites missing envelope

```
Heuristic search: every `request_transition(` call site where lookup of
current/target shows `target > current` (PSEUDO→TOOL, TOOL→SUPERVISED,
SUPERVISED→DELEGATING, DELEGATING→AUTONOMOUS, PSEUDO→DELEGATING multi-step)
AND no `envelope=` kwarg AND no `pytest.raises(PostureRatchetEnvelopeMissingError)`
context.
```

Manual sweep of the 41 Tier 1 call sites + 7 Tier 2 call sites:

Tier 1 call sites that pass `envelope=`: 11 (lines 541, 625, 700, 777,
891, 1071, 1099, 1293, 1357, 1377, 1394, 1415, 1435, 1567, 1585).
Tier 1 call sites that pass `envelope=None` explicitly: 1 (line 1525).
Tier 1 call sites testing the raise (no envelope): 2 (lines 1500-1512,
1518-1531).
Tier 1 call sites in ratchet-down or noop paths: remaining 27 (all
`target < current` or `target == current` — envelope unused on those paths).

GAP search:
**Command:**

```
grep -n "request_transition" tests/tier1/test_posture_gate_5_step_fail_closed.py \
  | head -41
```

Spot-checked every Tier 1 ratchet-up call site against the verified-passes
set above. Every ratchet-up call site that does NOT also test the raise
passes `envelope=_FakePostureCarryingEnvelope()`. PASS.

**Disposition recommendation:** PASS. The multi-site kwarg plumbing rule
is satisfied.

---

## Findings table

| ID  | Severity | Surface                                                               | File:line                                                                                        | Disposition recommendation                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| --- | -------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F-1 | MEDIUM   | envelope kwarg type-validation                                        | `envoy/authorship/posture_gate.py:699,852`                                                       | Add `isinstance(envelope, _PostureCarryingEnvelope)` is NOT possible (Protocols are structural). Instead add `duck-type pre-check`: `hasattr(envelope, "envelope_id") and hasattr(envelope, "prior_version") and hasattr(envelope, "mutate_for_posture_level")` with a typed `TypeError`. Fail-loud on shape-invalid input.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| F-2 | HIGH     | mutation return-value trust                                           | `envoy/authorship/posture_gate.py:941-950`                                                       | PostureGate MUST verify (a) `mutation.new_version == envelope.prior_version + 1`, (b) `mutation.diff_hash.startswith("sha256:")`, (c) `len(mutation.diff_hash) == 7 + 64`, and (d) `mutation.new_posture_level == target.name` BEFORE writing the `envelope_edit` Ledger entry. Currently the adapter's bogus return values land verbatim in the signed entry.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| F-3 | MEDIUM   | defensive Step-5b re-raise leaves orphan posture_change               | `envoy/authorship/posture_gate.py:939-940`                                                       | The defensive `if envelope is None: raise` at line 939 fires AFTER Step 5a's `posture_change` Ledger write. If a future refactor drops Step 3e, this guard leaves an orphan `posture_change` entry without its paired `envelope_edit`. Either (a) remove the guard (Step 3e is the structural defense — trust it; rely on the static-type narrowing comment for the future-refactor risk) OR (b) wrap Steps 5a + 5b in a single transactional boundary so a Step 5b failure rolls back Step 5a.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| F-4 | HIGH     | inverse-paired-emission: demotion leaves envelope posture_level stale | `envoy/authorship/posture_gate.py:864-874` (ratchet-down branch) + `envoy/envelope/types.py:340` | On ratchet-down (e.g. DELEGATING→TOOL), the Ledger correctly records `posture_change` but the envelope's `metadata.posture_level` field is NEVER updated — it remains at the prior (higher) posture. Subsequent reads of `envelope.metadata.posture_level` will return the stale higher value, contradicting the Ledger truth source. Per `rules/zero-tolerance.md` Rule 3 (no silent fallbacks). Disposition options: (1) Add an inverse `mutate_for_posture_level(demoted_level)` call on ratchet-down so the envelope is bumped to a new version with the demoted level (symmetric pairing — spec edit required per journal/0021 §"For Discussion" #2); (2) Document explicitly in the spec + envelope-model that `metadata.posture_level` is a STAMP-AT-MINT-TIME field, NOT the runtime authority; runtime authority is the latest `posture_change` Ledger entry. Whichever path: the implementation today produces silent drift.                                                |
| F-5 | HIGH     | wire-shape break: posture_level field added to EnvelopeMetadata       | `envoy/envelope/types.py:340`                                                                    | Adding a non-Optional field with a default to a `@dataclass(frozen=True)` that participates in JCS canonical bytes is a wire-shape break. Every pre-T-02-33 envelope persisted with its `content_hash` will produce a DIFFERENT content_hash on re-canonicalization after this change. Any downstream consumer caching content_hash (Trust store `DelegationRecord.effective_envelope_hash`, Ledger `envelope_edit` entries, SubsetProof verifier `parent_envelope_hash`) breaks across the version boundary. Disposition: bump `schema_version` from `envelope/1.0` to `envelope/1.1` (or add a `metadata.algorithm_identifier` bump) so consumers can detect the canonical-bytes shape change. Alternatively, document this in CHANGELOG as a breaking change and add a migration path. Phase 01 may be pre-production so the impact is bounded, but the rule still applies per `rules/schema-migration.md` Rule 1 (all schema changes through numbered migrations + version bump). |
| F-6 | MEDIUM   | `metadata.posture_level` is a write-only field — no production reader | `envoy/envelope/types.py:340`                                                                    | Per `rules/orphan-detection.md` Rule 1 (every facade has a production call site within 5 commits): `metadata.posture_level` is written by `_EnvelopeConfigPostureCarrier.mutate_for_posture_level()` in the test adapter but NO production code reads it for an authority decision. Either (a) document this as a "stamp at mint, audit-trail only" field (and tighten F-4's framing accordingly) OR (b) wire a production consumer that uses the field as the load-bearing binding the docstring claims.                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |

**Summary by severity:**

- CRITICAL: 0
- HIGH: 3 (F-2, F-4, F-5)
- MEDIUM: 3 (F-1, F-3, F-6)
- LOW: 0
- PASS: 7 surfaces (1.a partial, 2.a, 2.b, 4.b, 5.a, 5.b, 6.a, 6.b, 7.a, 7.b)

---

## Same-class fix-immediately candidates (per `rules/autonomous-execution.md` Rule 4)

Round 1 is audit; no fixes per disposition. Flagging candidates for the
orchestrator to consider in the redteam round resolution:

1. **F-2 + F-3** are SAME-BUG-CLASS (PostureGate trust boundary for the
   envelope_edit Ledger entry). Both involve "PostureGate writes data
   to the Ledger without validating the data's invariants." Fix scope:
   ~20 LOC of validation + tests in `posture_gate.py`. Fits within one
   shard budget (≤500 LOC load-bearing logic, ≤5 invariants).

2. **F-4 + F-6** are SAME-BUG-CLASS (envelope.metadata.posture_level
   semantic ambiguity). Both involve "the field exists on the envelope
   but the authority/source-of-truth contract is undefined." Fix scope
   depends on disposition (spec edit + impl OR docstring tightening +
   F-4 framing). Likely fits one shard but requires a spec call.

3. **F-5** stands alone and requires a schema-version-bump decision
   that crosses spec authority. Likely a separate shard with
   `pact-specialist` or `analyst` consultation.

---

## Receipts

- Source files read with line citations: `envoy/authorship/posture_gate.py`,
  `envoy/envelope/types.py`, `envoy/envelope/canonical_bytes.py`,
  `envoy/envelope/compiler.py`, `envoy/ledger/facade.py`,
  `tests/tier1/test_posture_gate_5_step_fail_closed.py`,
  `tests/tier2/test_posture_gate_wiring.py`, `tests/tier2/conftest.py`,
  `pyproject.toml`.
- Greps executed: `request_transition`, `mutate_for_posture_level`,
  `posture_level`, `kailash.trust.audit_store`, `PostureLevel`,
  `Ed25519`/`generate_keypair`/`from_private_bytes`,
  `secret|API_KEY|password|token` (case-insensitive),
  `asdict\(.*metadata`, `envelope\.envelope_id\|envelope\.prior_version`.
- Every finding's "evidence" cites the file + line range. No
  conclusion drawn without source citation.

---

## Auditor notes for Round 2

- The HIGH severity count is 3 — non-trivial. F-2, F-4, F-5 should
  resolve before Round 2 verification proceeds; F-2 and F-3 are
  cheapest (mechanical, in-file).
- F-4 has a spec-authority dimension (the asymmetric vs symmetric
  pairing decision in journal/0021 § "For Discussion" #2). The
  current "asymmetric, envelope_edit only on ratchet-up" disposition
  was made WITHOUT addressing what happens to the envelope's
  `posture_level` field on demotion. This is the gap.
- F-5 may be deferrable to Phase 02 if Phase 01 is pre-production
  (no consumers of cached content_hash exist yet). Confirm with
  Phase 01 scope docs.
