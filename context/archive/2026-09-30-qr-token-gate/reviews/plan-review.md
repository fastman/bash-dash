<!-- PLAN-REVIEW-REPORT -->
# Plan Review: QR Token Gate Implementation Plan

- **Plan**: context/changes/qr-token-gate/plan.md
- **Mode**: Deep
- **Date**: 2026-09-30
- **Verdict**: SOUND
- **Findings**: 0 critical, 1 warning, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | PASS (1 observation) |
| Plan Completeness | WARNING |

## Grounding

- **Paths:** 12/12 ✓. This covers `game/views.py`, `services.py`, `staff_views.py`, `urls.py`, `home.html`, `_board.html`, `hall.html`, `moderate.html`, `game.css`, `hall.js`, the test files and `bench_game.py`. The next migration number is 0006 ✓.
- **Symbols:** 7/7 ✓. This covers `_session_game`, `_redirect_existing`, `_board_context`, `hall_board` (403 contract), `{% block qr %}`, `HALL_REFRESH_S` and `start_game`. The `start_game` line reference was stale (73, actually 76) and is corrected.
- **Plan brief:** matches the plan ✓.
- **PRD:** FR-001, FR-017 and the Access Control rules are all covered ✓.
- **Baseline:** 196 tests OK ✓.
- **Dependencies:** Django 6.1.1 ✓. segno `svg_inline(omitsize=True, border=2, dark, light)` was verified: it emits a `viewBox`-only SVG, and a realistic URL encodes at version 5-M ✓.
- **Progress section:** matches the phases (2/2 phases, 8 + 8 rows) ✓.

## Notes

This is a strong plan. It follows the PRD closely, and the key decisions are sound and fit the house patterns:
- The gate runs after the resume redirect.
- The token is stateless and signed, and bucketed by rotation period.
- The QR rides inside the polled board.
- The TTL form on `/staff/moderate` uses the PRG pattern.

This ran as a background job, so triage was done on best judgment without the user. Decisions are recorded below and can be overridden.

## Findings

### F1 — Six existing tests break under the gate, but the plan names only two

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 1 — §6 Tests
- **Detail**: The plan updates only the `ViewTestCase.start` helper and `test_home_renders_rules_and_nick_form`. These other tests also reach the gate without a token:
  - `test_views.py:75-76` (`test_play_without_game_redirects_home`) and `:397` (`test_done_redirects_still_hold`) call `assertRedirects` to `/`. That fetches the target and expects 200, but it now gets 403.
  - `:368-370` (`test_home_duration_follows_setting`) checks `assertContains` on tokenless `/`.
  - `:224` (`DockerDownTests.setUp`) posts `/start` directly, bypassing the helper.
  - `:252` (`NoAnswerLinksTests`) still passes, but silently checks the gate page instead of the home page.
  - `test_staff_views.py:284` posts `/start` directly.
- **Fix**: List these tests in the Phase 1 Tests contract with the concrete adjustment for each:
  - redirects: `fetch_redirect_response=False`;
  - home content: GET with `?t=`;
  - direct posts: add `t`.
- **Decision**: FIXED. A bullet was added to Phase 1 §6 Tests.

### F2 — A frozen QR can go stale on screen while polling fails

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 2 — §3 Board fragment ("keep last board on failure")
- **Detail**: When `/staff/hall/board` returns 403 (staff session gone) or the server is unreachable, `hall.js` keeps the last board. The QR stays on screen, and after the TTL passes it produces only "That code has expired" refusals. The only hint is the small corner badge. The risk is low:
  - The default `SESSION_COOKIE_AGE` is 2 weeks.
  - A server outage blocks play anyway.
  - The badge already says "Session expired" or "Reconnecting…".
- **Fix**: Optionally, in `hall.js`, hide `.hall-qr` whenever the status badge shows an error. The plan keeps `hall.js` unchanged on purpose.
- **Decision**: ACCEPTED. This is low probability, and the plan's "no JS change" goal is worth keeping. Staff can watch the badge during manual step 5.

### F3 — Implementer forks left open, and the token clock is unspecified

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 — §2 and §3; Critical Implementation Details
- **Detail**: Two choices were left to the implementer:
  - whether the QR helpers go in `services.py` or `game/qr.py` (but the tests reference `services.start_url`);
  - whether `moderate` gets a flag or only the hall views build the QR.

  Also, `now_epoch` is not tied to a clock. The view test "mock `timezone.now`" only works if the services use `timezone.now()`, which is the existing convention in `services.py`, and not `time.time()`.
- **Fix**: Pin the choices:
  - the QR helpers go in `services.py`;
  - a new `_hall_context(request)` wraps `_board_context()`, which `moderate` keeps using unchanged;
  - `now_epoch = int((now or timezone.now()).timestamp())`.
- **Decision**: FIXED. The plan's §2 and §3 and the Critical Implementation Details were edited.
