# ui-platform

## Purpose

Per-platform side-channel hygiene (clipboard, screen, accessibility) + secure input fields + platform-specific rendering.

## Provenance

- **Source:** `workspaces/phase-00-alignment/01-analysis/09-threat-model.md v3 T-070 + 01-ux-rituals.md v2 §11`.
- **Threats mitigated:** T-070 clipboard/screen/accessibility, T-071 memory disclosure.
- **BETs tested:** BET-3 sovereignty under platform attack surface.

## Clipboard

- Grant Moment credential capture: secure-text-field (bypass clipboard on iOS).
- Auto-clear after 30s (configurable).
- No Envoy content auto-copied.

## Screen recording

- Flutter mobile (Phase 02): detect active recording; warn before sensitive Grant Moment renders.
- Macro: no countermeasure — detection + advisory only.

## Accessibility API hardening

- **macOS:** accessibility tree includes visible Envoy content; sensitive fields (credentials, Shamir shards, ledger entries) excluded from accessibility tree unless user opts in.
- **Android:** accessibility hint system; sensitive fields excluded.
- **iOS:** VoiceOver support with redacted content for sensitive fields.

## Memory hygiene (T-071)

See specs/trust-vault.md §memory-hygiene. Zeroize on release.

## Localization

- Phase 01: en-US.
- Phase 02: en-GB, es-ES, de-DE, fr-FR, zh-CN, ja-JP.
- Phase 04: community-contributed.
- Translation keys: `envoy-i18n/<lang>/<ritual>.json`.
- User-authored content preserved verbatim (user's language); Envoy signed records carry exact text.

## Accessibility

- Screen readers: all prompts have alt text; visible secret has text description.
- High-contrast mode: color channel adapts.
- Keyboard-only: Tab navigation.
- Audio cue: accessible chime on Grant Moment (Web).
- Chunked content: long Ledger entries split for cognitive accessibility.

## Bidi / RTL

HTML bidi standard. User-authored content preserves RTL marks.

## Error taxonomy

| Error                               | Trigger                                                                                                       | User action                                                                         | Retry                  |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ---------------------- |
| `ScreenRecordingDetectedError`      | Flutter mobile detects active screen-recorder before sensitive Grant Moment render                            | Refuse render; UX surfaces "stop recording to continue" banner                      | Manual after stop      |
| `AccessibilityAPIBypassError`       | Sensitive field (credential / Shamir shard / ledger entry) detected in accessibility tree without user opt-in | Refuse field render; investigate platform accessibility-API change                  | Manual after diagnosis |
| `ClipboardAutoclearFailedError`     | OS API refused clipboard clear after 30s window (T-070 defense)                                               | Surface "clipboard not cleared" banner; user clears manually                        | Manual after clear     |
| `SecureTextFieldUnavailableError`   | Platform secure-text-field API unavailable (older OS / restricted env)                                        | Surface degraded-mode warning; user enters credential via alternative path          | Manual after upgrade   |
| `MemoryZeroizeFailedError`          | Trust-Vault memory zeroize on release returned non-zero (T-071 defense)                                       | Surface as integrity event; investigate platform memory-API change                  | Never (security event) |
| `LocalizationKeyMissingError`       | `envoy-i18n/<lang>/<ritual>.json` missing key for active locale                                               | Surface English fallback + log; user reports for next translation cycle             | Auto with fallback     |
| `BidiDirectionalityFailedError`     | RTL content rendered with stripped bidi marks (data-loss event)                                               | Surface as render event; user-authored content preserved verbatim per signed record | Manual after fix       |
| `HighContrastModeUnsupportedError`  | Channel rendering surface cannot adapt to high-contrast color channel                                         | Surface advisory; user routes to alternate channel for accessible rendering         | Manual after route     |
| `MacroRecordingAdvisory` (advisory) | Macro-style screen capture detected (no countermeasure; advisory only)                                        | UX advisory; user pauses macro before sensitive content                             | N/A                    |

## Cross-references

- specs/trust-vault.md — memory hygiene.
- specs/grant-moment.md — secure input fields.
- specs/channel-adapters.md — per-channel accessibility.
- specs/connection-vault.md — secure-text-field credential capture.
- specs/threat-model.md — T-070, T-071.

## Test location

- `tests/integration/test_clipboard_autoclear_30s_per_platform.py` — 30s auto-clear on macOS/Windows/Linux/iOS/Android (Tier 2 per OS).
- `tests/regression/test_t070_clipboard_autoclear.py` — T-070 defense; auto-clear after credential capture.
- `tests/regression/test_t070_screen_recording_detection_mobile.py` — T-070 defense; Flutter mobile recording-detect warning.
- `tests/regression/test_t070_accessibility_api_excludes_sensitive.py` — T-070 defense; sensitive fields excluded from a11y tree.
- `tests/regression/test_t071_memory_zeroize_on_release.py` — T-071 defense; Trust-Vault memory zeroized.
- `tests/integration/test_secure_text_field_per_platform.py` — iOS bypass-clipboard, Android Secret.Filled.
- `tests/integration/test_localization_fallback.py` — missing translation key falls back to en-US.
- `tests/integration/test_high_contrast_mode_render.py` — color-channel adaptation across rituals.
- `tests/integration/test_keyboard_only_navigation.py` — Tab navigation through all Phase-01 rituals.
- `tests/integration/test_bidi_rtl_user_content_preserved.py` — RTL marks preserved verbatim in signed records.

## Open questions

1. macOS / Linux screen-recording detection — no API parity with mobile; advisory-only sufficient or platform-specific countermeasure (Phase 02 work).
2. iOS VoiceOver redacted content — what's the right balance between accessibility and information-leak (full read vs partial summary).
3. Localization Phase 02 lang set sufficiency — community-contributed Phase 04 onboarding cadence.
4. Clipboard auto-clear configurability — 30s default; should high-OPSEC users get 5s, low-OPSEC users 5min.
5. Per-platform a11y opt-in flow — single global opt-in vs per-field; coordination with grant-moment.md secure-input UX.
