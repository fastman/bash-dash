<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: QR Token Gate Implementation Plan

- **Plan**: context/changes/qr-token-gate/plan.md
- **Scope**: Full plan (Phases 1–2 of 2)
- **Date**: 2026-09-30
- **Verdict**: APPROVED
- **Findings**: 0 critical, 1 warning, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

## Evidence

- Plan drift: every "Changes Required" item has a MATCH. This covers the settings block, the `GateSettings` singleton + `0006` migration, the token services (bucketed `Signer`, `timezone.now` clock, future-token and TTL checks), the gate after `_session_game()` in `home`/`start`, and `gate.html` plus the hidden `t` field. It also covers `segno`, `start_url`/`qr_svg`, `_hall_context` in the polled board, removal of the `{% block qr %}` slot, `set_token_ttl` (staff + POST + PRG + messages) and the "Start QR" section with the TTL-0 warning. No unplanned files. `hall.js` is untouched, as planned.
- Test contract: every service and view test listed in the plan exists. This includes the ttl/ttl+1 boundaries, retroactive TTL, expiry between GET and POST, resume to `/play` and `/done` without a token, CSRF 403, GET 405, `PUBLIC_BASE_URL`, per-period QR stability, and the gate page in the no-external-links check.
- Automated checks (run 2026-09-30): `uv run python manage.py test game challenges` → 222 tests OK (223 after the F2 fix). `check` found no issues. `makemigrations --check --dry-run` found no changes. `uv lock --check` is in sync. `showmigrations` shows `0006_gatesettings` applied.

## Findings

### F1 — Manual verification not yet performed

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/qr-token-gate/plan.md (Progress 1.5, 1.6, 2.5–2.8)
- **Detail**: All six Manual rows are still `[ ]`, so none were rubber-stamped. This includes the ones only a human can do: phone-camera scan at ~1.5 m on Android and iOS, and a hall layout at 1366×768 with no scrolling. change.md said `implemented` before any of them were done.
- **Fix**: A human should run the plan's Manual Testing Steps 1–5 before merging and tick 1.5–2.8.
- **Decision**: ACCEPTED — left for the human (background run; cannot be done by the reviewer).

### F2 — Env TTL seed bypasses the staff bounds

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: game/services.py:339 (`gate_settings`)
- **Detail**: `BASHDASH_START_TOKEN_TTL_S` seeded the row unchecked. A value like 30 is shorter than the 60 s rotation, so a freshly shown QR could already be expired and the gate would be closed for everyone. A value like 90 would show as "1 min" on `/staff/moderate`, and saving that value would be rejected. Staff input enforces 0 or 120–86400 s, but the seed did not.
- **Fix**: Clamp a non-zero seed to `[TOKEN_TTL_MIN_S, TOKEN_TTL_MAX_S]` in `gate_settings()`, and add a test.
- **Decision**: FIXED. `gate_settings()` now clamps the seed. The new test is `test_gate_settings_seed_is_clamped_to_staff_bounds` in game/tests/test_services.py (0→0, 30→120, 10^6→86400).

### F3 — QR tile loses its square shape and is left-aligned below 900 px

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: game/static/game/game.css:169, 183
- **Detail**: Under the 900 px breakpoint, `.qr-tile` has `max-width: 20rem` but keeps `height: 35vh`, so on tall narrow viewports it stops being square. The SVG still scales and stays scannable. The block is also not centred (`text-align: center` on `.hall-qr` does not centre a block div). This only affects a narrow hall view, not the booth big screen.
- **Fix**: Add `margin-inline: auto` and swap `height` for `width` in the breakpoint rule, if a narrow hall view ever matters.
- **Decision**: SKIPPED — cosmetic; the hall page is for the big screen only.
