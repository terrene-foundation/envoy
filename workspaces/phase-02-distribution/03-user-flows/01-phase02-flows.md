# Phase 02 — User Flows

**Role:** The Phase-02-specific user-facing flows `/analyze` must validate. Each flow is the literal walk a user takes (per `rules/user-flow-validation.md`) — the composition the unit tests don't cover. Grounded in the 6 deep-dives (`01-analysis/01-research/`). These flows become the acceptance-walk receipts at `/implement`.

**Date:** 2026-06-08. **Status:** DRAFT (analysis phase).

---

## Flow 1 — First-run runtime picker (WS-1 / WS-2)

**Actor:** new user installing the Phase-02 binary.

```
$ curl -sSf https://get.envoy.ai | sh        # (Track B: gated on trademark close; codename until then)
  → installs single static binary (<50 MB, embedded CPython via PyO3)
$ envoy init
  → First-run runtime picker:
      "Envoy can run on two engines:
        [1] Rust (default) — fastest, recommended
        [2] Pure-Python — maximum compatibility, slower
       Both behave identically (verified by conformance vectors)."
  → user picks [1]
  → attestation-on-switch: binary hash verified against signed manifest (T-060 fail-closed)
  → proceeds into Boundary Conversation (Phase-01 ritual, unchanged)
```

**Disposition checks:** picker legible to a non-technical user; the "behave identically" claim is backed by EC-02.4 conformance vectors; opt-out to pure-Python is one keystroke; a poisoned binary halts here (T-060), it does not silently proceed.

**Risk surfaced:** the picker copy must not imply the user is choosing a _trust_ level — both runtimes are equally trusted; the choice is performance/compatibility only.

---

## Flow 2 — Mobile QR-pairing (WS-3)

**Actor:** existing desktop Envoy user adding their phone.

```
desktop:  $ envoy pair
            → renders a QR code (screen-recording detection active; warns if recording)
            → QR encodes an SAS/AKE handshake init (SPAKE2 or Noise-XX), single-use, ≤30s expiry
mobile:   open Envoy app → scan QR
            → SAS short-string is derived from the HANDSHAKE TRANSCRIPT (truncated hash of the
              Noise-XX/SPAKE2 transcript), shown on BOTH devices; user confirms they match.
              A MITM produces a different transcript → different SAS → mismatch (anti-MITM, T-080).
              The Trust-Vault visible secret MAY be shown additionally as familiar-UX framing,
              but it is NOT the authenticating value (it is fixed/known and a relay could forward it).
            → phone enrolled as RENDER-ONLY terminal (NO delegation key on device)
            → pairing emitted as a signed Ledger event
  → total: <30s cold start (EC-02.6)
```

**Disposition checks:** the transcript-derived SAS match is the user-verifiable MITM defense; if the short-strings differ, the user aborts. The phone cannot _authorize_ actions (render-only) — it surfaces Grant Moments that the user approves on the desktop. Pairing is auditable (Ledger event).

**Risk surfaced:** this is a NEW trust boundary (device pairing under active-network adversary) — `threat-model.md` needs a device-pairing entry that pins the **transcript-binding** requirement (spec gap, additions-only). Round-1 red team (R1-CRIT-1) caught an earlier draft that bound the SAS to the static visible secret instead of the transcript — that draft was MITM-unsafe; corrected here.

---

## Flow 3 — Envelope Library: publish + install (WS-4)

**Actor (producer):** Foundation steward publishing a Foundation-Verified envelope.
**Actor (consumer):** user importing it.

```
producer: (air-gapped) 2-of-N steward Ed25519 sign over content_hash
          → publish to envoy-registry:envelope-library:v1 (Nexus HTTP/CLI/MCP)
          → content-addressed by sha256(canonical_bytes())
consumer: $ envoy envelope import foundation-verified:<name>
          → fetch from registry (transport untrusted)
          → client re-verifies 2-of-N steward signatures against PINNED keys locally
          → on verify: envelope available to compile into the user's config
          → on sig-fail: hard refuse (never trust the Nexus transport)
```

**Disposition checks:** the consumer's trust comes from local signature verification against pinned steward keys, NOT from the registry being "official." Community tier is frozen (Phase-03) — only `foundation-verified:` resolves this phase. Quarterly key rotation = additive enrollment; revocation = subtractive hard-fail.

---

## Flow 4 — SKILL.md ingest (WS-4)

**Actor:** user installing a third-party SKILL.md-format skill.

```
$ envoy skill ingest ./some-skill/
  → lint SKILL.md + parse ENVELOPE.md companion
  → CO-compliance validator:
      • declared permissions vs INFERRED permissions (AST static walk)
      • declared ⊋ inferred → OverPrivilegeWarning (surface at Grant Moment; user downscopes or accepts)
      • literal undeclared-capability call → REJECT (score <0.5)
      • import-graph-only signal → WARNING band (never auto-reject)
  → generates a CO-compliant envelope
  → user reviews + approves at a Grant Moment
```

**Disposition checks:** acceptance gate is 0 false-reject on 100 benign skills + 0 false-negative on 3 adversarial (escalation/exfiltration/overreach) per EC-02.7. A single benign false-reject is the net-noise death (trains reflexive `force_install`) — the validator must be conservative on rejection, generous on warning.

---

## Flow 5 — Foundation Health Heartbeat opt-in (WS-5)

**Actor:** user deciding whether to share anonymous aggregate telemetry.

```
  → (during onboarding OR later) Heartbeat consent Grant Moment:
      "Share anonymous health metrics to help improve Envoy?
       • Your individual values are never visible (k≥100 aggregation)
       • Network traffic is IP-stripped (OHTTP relay)
       • You can revoke anytime; revocation cascades and stops all telemetry"
  → user opts IN → signed, cascade-revocable Delegation Record produced
  → client splits each report into encrypted shares (STAR), adds client-side DP noise
    (per-counter, before share-split), routes through OHTTP relay
  → Foundation aggregator sees only the k≥100 aggregate, never an individual report
revoke: $ envoy heartbeat revoke
  → cascade-revoke stops the telemetry Delegation Record; no further reports emitted
```

**Disposition checks:** consent is explicit + signed + revocable (not a buried setting); the privacy claims (k-anonymity, IP-stripping, DP) are structural, not policy promises; revocation actually stops emission (cascade-revoke wired to the no-op `maybe_record_flag` hot-path seam — C3).

---

## Cross-flow notes

- Flows 1–2 are gated on Track B legal approvals for _public_ surfacing (trademarked name, app-store identity) but are fully buildable/walkable under a codename now.
- Flow 5's consent path consumes WS-6's Grant Moment substrate (S4) — it cannot be walked end-to-end until the durable substrate lands.
- Every flow ends in a Ledger event or a Grant Moment — Phase-02 adds surfaces but does NOT bypass the Phase-01 consent+audit spine.
