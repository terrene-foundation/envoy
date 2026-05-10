---
type: RISK
date: 2026-05-07
created_at: 2026-05-10T00:00:00Z
author: agent
session_id: phase-01-wave-2-implement
session_turn: 4
project: phase-01-mvp
topic: T-02-35 H-06 Unicode-confusable bypass + O_NOFOLLOW symlink-redirect closure
phase: implement
tags:
  [
    shamir,
    h-06,
    unicode-confusable,
    three-layer-defense,
    o-nofollow,
    symlink-redirect,
    security-review,
    autonomous-execution-rule-4,
    wave-2,
  ]
---

# RISK: H-06 Unicode-confusable bypass + atomic-write symlink-redirect fixed in T-02-35 gate review (commit `b6a59048`)

The shipped T-02-35 implementation (commit `6ec5fde5`) enforced H-06 (no "envoy" substring on cards) via a single-layer substring blacklist:

```python
_FORBIDDEN_LABEL_TOKENS = ("envoy",)
def _validate_slot_label(label: str) -> None:
    if any(tok in label.lower() for tok in _FORBIDDEN_LABEL_TOKENS):
        raise EnvoyLabelOnCardError(...)
```

Security review on PR #15 found the substring-blacklist approach trivially bypassable. Three classes of attack:

| Attack class                   | Example payload                            | Why bypass works                                                                                |
| ------------------------------ | ------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| Unicode confusable (fullwidth) | `slot_label="ＥＮＶＯＹ"` (U+FF25 etc.)    | `.lower()` of fullwidth letters returns fullwidth letters — does NOT normalize to ASCII "envoy" |
| Unicode confusable (Cyrillic)  | `slot_label="еnvoy"` (Cyrillic `е` U+0435) | visually identical to ASCII "envoy", but `.lower()` keeps Cyrillic as Cyrillic                  |
| Zero-width space injection     | `slot_label="env​oy"`                      | invisible to user; substring "envoy" contains the ZWS, doesn't match raw "envoy"                |
| Control-char injection         | `slot_label="slot-1\nEnvoy"`               | depending on render context, the newline may hide the suffix in display                         |

Two HIGH (H-2 atomic-write symlink-redirect) and two MEDIUM (M-1 + M-2 confusables) findings consolidated into one shard per `rules/autonomous-execution.md` Rule 4.

## H-2: atomic-write symlink-redirect

The T-02-35 vault `write_metadata` used a bare `open(tmp_path, "wb")` for the atomic-rename tmp file:

```python
# T-02-35 atomic-write (the shape that shipped)
with open(tmp_path, "wb") as f:
    f.write(ciphertext)
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp_path, target_path)
```

Per `rules/trust-plane-security.md` MUST Rule 1, `open()` does NOT pass `O_NOFOLLOW`. An attacker with write access to the vault's parent directory can pre-create `tmp_path` as a symlink to `/etc/shadow` (or any privileged file the user can write). The next `write_metadata`:

1. Opens the symlink (resolves to `/etc/shadow`).
2. `f.write(ciphertext)` writes the encrypted vault payload into `/etc/shadow`.
3. `os.fsync` commits the corruption.
4. `os.replace(tmp_path, target_path)` moves the symlink (NOT the symlink target) to `target_path`.

Net: `/etc/shadow` is corrupted; the vault target is now a broken symlink. The attacker has destroyed system credentials AND leaked the vault ciphertext into a privileged file.

## Three-layer defense (M-1 + M-2 fix)

Replaced the substring blacklist with three ordered layers per `rules/trust-plane-security.md` MUST Rule 1 (every record-files write goes through a hardened validator):

```python
SLOT_LABEL_PATTERN = re.compile(r"^slot-\d+$")  # primary: whitelist regex

def _validate_slot_label(label: str) -> None:
    # Layer 3: ASCII-only check (defense-in-depth; explicit guard)
    if not label.isascii():
        raise ValueError("slot_label must be ASCII")
    # Layer 1: whitelist — primary defense
    if not SLOT_LABEL_PATTERN.fullmatch(label):
        raise ValueError("slot_label must match ^slot-\\d+$")
    # Layer 2: substring blacklist — belt-and-suspenders
    for tok in _FORBIDDEN_LABEL_TOKENS:
        if tok in label.lower():
            raise EnvoyLabelOnCardError(...)
```

Layer ordering:

1. **Whitelist regex `^slot-\d+$`** — primary defense. Only canonical ASCII `slot-N` shape passes. Defeats Unicode confusables (fullwidth/Cyrillic both fail `[a-z]` after `\d+`), control chars (`\n` doesn't match `\d`), zero-width spaces (don't match `\d`).
2. **ASCII-only check** — explicit redundant guard. Kept so a future regex relaxation cannot silently re-open the Unicode bypass.
3. **Substring blacklist** — defense-in-depth, redundant with the whitelist but kept as belt-and-suspenders.

Applied at THREE sites (every H-06 gate):

- `envoy/shamir/paper.py::_validate_slot_label` (renderer's gate).
- `envoy/shamir/distribution_checklist.py::_validate_checklist_slot_labels` (persister's gate).
- `envoy/shamir/types.py::DistributionChecklist.__post_init__` (NEW — construction-layer gate per reviewer M-1).

The coordinator's `_opaque_slot_labels()` always produces canonical `slot-N` strings, so legitimate Phase-01 callers are never affected. Phase-02 / Phase-04 schema extension wanting richer labels MUST relax the whitelist explicitly AND re-derive the H-06 enforcement surface — failing existing tests serves as the structural alarm.

## H-2 fix: `O_EXCL | O_NOFOLLOW`

```python
# T-02-35 fix: hardened atomic-write
fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
try:
    with os.fdopen(fd, "wb") as f:
        f.write(ciphertext)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, target_path)
except Exception:
    try: os.unlink(tmp_path)
    except FileNotFoundError: pass
    raise
```

- `O_EXCL`: rejects any existing file (defends against parallel-write collision; the attacker cannot pre-create the tmp file).
- `O_NOFOLLOW`: rejects existing symlinks at the tmp path (defends against the redirect attack — even if the attacker pre-creates a symlink, the open fails with `ELOOP`).
- mode `0o600`: matches the post-replace `chmod` so file permissions are correct from creation (no race between create-mode-0o644 and chmod-0o600).
- Best-effort cleanup of orphaned tmp from prior crash unlinks the path before `O_EXCL` would refuse the create.
- On any write error, the tmp file is unlinked before propagating so retries do not collide with `O_EXCL`.

## H-1 (doc-only fix per security-reviewer disposition)

`read_metadata → mutate → write_metadata` cycle has no compare-and-swap; concurrent async tasks can clobber each other's mutations. Documented in `write_metadata` docstring as a Phase-01 limitation; Phase-02 hardening adds vault-level `update_metadata(callable)` primitive. Single-process single-task is the supported topology for Phase 01 (documented in spec § Trust Vault concurrency model).

## Tests added (regression locks)

Test count: 427 → 431 (+4 H-06 hardening tests).

Renderer tests:

- `test_render_rejects_unicode_confusable` (ＥＮＶＯＹ fullwidth + Cyrillic).
- `test_render_rejects_control_char_injection` (newline / null / CR).
- `test_render_accepts_canonical_slot_label` (whitelist accepts `slot-N`).
- `test_render_rejects_custom_label_form` (whitelist rejects `Slot-1` / `slot-A1` / `slot-` / `1` / etc.).

Persister test (RE-ARCHITECTED):

- `test_persist_rejects_envoy_slot_label` — now asserts the construction-layer gate fires FIRST (`ValueError` from `__post_init__`), then bypasses via `object.__setattr__` to verify the persister-layer defense-in-depth gate also fires (`EnvoyLabelOnCardError` from `_validate_checklist_slot_labels`).

Existing tests (`test_render_rejects_envoy_label`, `test_render_rejects_envoy_label_case_insensitive`) updated to expect the new "opaque pattern" error message — the whitelist check fires BEFORE the substring blacklist for any non-canonical label.

## Risk that surfaces this entry

Two latent risks this entry pins:

1. **Single-layer substring blacklists are structurally weak**. Any "must not contain X" check on a string that crosses a security boundary is bypassable via Unicode confusables, zero-width spaces, control chars, or normalization-form drift. The structural defense is **whitelist-first** — describe the canonical shape and reject everything else. Substring-blacklist is acceptable only as defense-in-depth layer 2 or 3, never as the primary gate.

2. **Bare `open()` for atomic-rename tmp files is a symlink-redirect vector**. Per `rules/trust-plane-security.md` MUST Rule 1, every record-files write MUST use `os.open(..., O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW, 0o600)` for the tmp file. Any future caller that bypasses this contract (e.g., a Phase-02 vault extension that adds a new write path) is one open() away from re-introducing the redirect attack.

## For Discussion

1. The H-06 substring-blacklist approach was the explicit design choice in `specs/shamir-recovery.md` § H-06 enforcement — the spec said "reject any label containing 'envoy' (case-insensitive)". The Unicode bypass shows the spec WAS wrong (or at least insufficient). The spec was edited in this PR to specify the three-layer defense. But the original spec wording was reviewed and accepted multiple times before reaching `main`. Should `commands/redteam` Round 1 add a mechanical sweep "every spec containing the phrase 'reject X containing Y' triggers a Unicode-confusable adversarial pass" — to catch the next instance of this design pattern before it ships?

2. The three-layer defense (whitelist + ASCII + blacklist) is more rigorous than the spec-mandated "reject envoy substring" but generates a maintenance burden: any Phase-02 / Phase-04 schema extension wanting richer slot labels MUST relax the whitelist AND re-derive the test surface AND keep the ASCII layer aware of the new shape. Is this maintenance burden documented loudly enough? Should the whitelist regex live in `specs/shamir-recovery.md` § Card format with a "Phase-N+ extension contract" sub-section that names the test files that lock the shape, so a Phase-04 contributor cannot relax the whitelist without re-deriving the test surface?

3. The `O_NOFOLLOW` fix is correct on POSIX but the flag is a no-op on Windows (Windows has no symlinks in the POSIX sense; junctions are different). The vault is meant to be cross-OS portable per BET-9b (`tests/tier3/test_trust_store_cross_os_portability.py` in `08-tests-tier3-acceptance.md`). What is the equivalent defense on Windows — does the atomic-write path use a different primitive, or does the symlink-redirect threat-model not apply because Windows ACLs handle the equivalent attack class? (Counterfactual: had the vault been Windows-only, the fix would have been wrong — `O_NOFOLLOW` is silently ignored, AND Windows DOES support reparse points that some attack classes can leverage.)
