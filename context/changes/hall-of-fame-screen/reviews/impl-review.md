<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Hall of Fame Screen with Nick Hiding

- **Plan**: context/changes/hall-of-fame-screen/plan.md
- **Scope**: Full plan (Phases 1–3 of 3)
- **Date**: 2026-09-30
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 4 warnings, 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | WARNING |
| Pattern Consistency | WARNING |
| Success Criteria | WARNING |

## Evidence summary

- Every file named in the plan is in `git diff main...HEAD`, and every change in the diff is in the plan. `base.html` is changed through the planned `main_class` block.
- None of the "What We're NOT Doing" items were built. The only QR-related code is the empty `{% block qr %}` slot that the plan reserves for S-06.
- The critical details were checked against the code:
  - `hall_of_fame` computes places in one pass. The tie key is `(solved, attempts, elapsed)`, which gives the same places as `rank_of`, and the parity test covers ties and zero-solve games.
  - The recent list is built from the same ranked rows.
  - `hall_board` returns 403 and is `never_cache`.
  - `hall.js` uses a single `setTimeout` chain.
  - The prize code never reaches `_board.html`, and there is no `|safe`.
  - hide and unhide use guarded UPDATEs, and a malformed id is treated as `DoesNotExist`.
- Automated criteria:
  - `test game challenges`: OK. There are 202 tests, but 6 of them run twice (see F2).
  - `check`: clean.
  - `makemigrations --check --dry-run`: no changes.
  - `migrate`: nothing to apply.
- Possible flaky test: a sub-agent saw one failed suite run, but the suite passed in 9 of my own reruns. That run most likely overlapped with a parallel suite run from this review. It is not raised as a finding.

## Findings

### F1 — Hall screen polling can freeze silently on a hung request

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: game/static/game/hall.js:16
- **Detail**: `fetch()` has no timeout, and the next `setTimeout(tick)` is only scheduled once the promise settles. A request that never completes (a half-open TCP connection on the booth Wi-Fi, a stalled proxy) therefore stops polling for good. No "Reconnecting…" badge appears, and the public screen keeps showing a stale board. `play.js:6,115-116` already guards against this with `AbortController` and `FETCH_TIMEOUT_MS`.
- **Fix**: Wrap the fetch in an `AbortController` with a timeout of about `Math.max(delay, 10000)` ms. The abort then reaches the existing `.catch`, which shows "Reconnecting…" and keeps polling.
- **Decision**: PENDING

### F2 — HiddenAndHallTests subclasses RankingTests, so 6 tests run twice

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: game/tests/test_services.py:147
- **Detail**: `class HiddenAndHallTests(RankingTests)` inherits from a concrete TestCase just to reuse the `make`/`place` helpers, so every `RankingTests.test_*` runs again under the new class. That makes the count 170 + 26 new + 6 duplicates = 202. Every other test class in the file subclasses `ServiceTestCase`.
- **Fix**: Move `make` and `place` into a helper base `RankingTestCase(ServiceTestCase)` that has no tests. Make both `RankingTests` and `HiddenAndHallTests` subclass it. The expected count after the fix is 196.
- **Decision**: PENDING

### F3 — Display laptop's staff session still reaches the prize desk and moderation

- **Severity**: ⚠️ WARNING
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Architecture
- **Location**: game/staff_views.py (all views use `staff_member_required` / `is_staff`); plan.md "Migration Notes"
- **Detail**: The public big screen needs a permanently logged-in `is_staff` session. The plan's mitigation (plan review F2) is a non-superuser account with no model permissions, in kiosk mode. It claims this keeps `/staff/moderate` away from passers-by. It does not: `staff_member_required` checks only `is_staff`. Anyone who reaches the keyboard (address bar, a kiosk-mode escape) can open `/staff` (look up codes, mark prizes as given) and `/staff/moderate` (hide players). Missing model permissions only protects `/admin`. The plan itself is wrong here, not just the code.
- **Fix A ⭐ Recommended**: Correct the plan's Migration Notes to say kiosk mode and physical control of the display are the only protections. Queue a follow-up that splits permissions, for example a "display" account that can only reach `/staff/hall[/board]`.
  - Strength: No code churn this late in the slice. It gets the operator's runbook right before the event, which is what actually protects the booth now.
  - Tradeoff: The exposure stays in code until the follow-up lands.
  - Confidence: HIGH — the gap is only exploitable with physical access to a kiosk-mode browser.
  - Blind spot: Whether the booth display will really be supervised and locked down.
- **Fix B**: Split access now. Keep `hall`/`hall_board` on `is_staff`, and require an extra permission for lookup, prize, moderate, hide and unhide (for example `game.change_gamesession`, or a custom `game.staff_desk`). Give that permission to the desk accounts only.
  - Strength: The display account can then show only the board, which removes the risk in code.
  - Tradeoff: It changes S-04's access model, needs a data migration or group setup for the existing staff accounts, and touches every staff test.
  - Confidence: MED — the design is straightforward, but the scope is wider than this slice.
  - Blind spot: How staff accounts are provisioned before the event.
- **Decision**: PENDING

### F4 — Manual verification for Phases 2–3 is still open while change.md says "implemented"

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: plan.md Progress 2.4–2.7, 3.4–3.6
- **Detail**: Seven manual rows are unchecked:
  - wide-screen fit and stacking below 900 px;
  - no flash when the board refreshes;
  - "Reconnecting…" when the server is down, and "Session expired" after logout;
  - hide/unhide showing up on the screen within one refresh;
  - the moderation page fitting at 320–360 px;
  - hidden player's `/done` and the lookup page.

  None of these can be verified by the automated tests (layout, timing, network behaviour). Phase 1 manual rows 1.5 and 1.6 are checked. 1.6 is backed by tests, and 1.5 (the admin column and filter) is a trivial diff, so they are not rubber-stamped.
- **Fix**: Run the plan's Manual Testing Steps 1–7 before merging. Re-check 2.6 after F1 is fixed. Tick the rows.
- **Decision**: PENDING

### F5 — HALL_* settings are not bounds-checked

- **Severity**: 🔎 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: config/settings.py:155-157
- **Detail**:
  - A negative `BASHDASH_HALL_REFRESH_S` gives a negative `refresh_ms`. That value is truthy in `hall.js`, so polling runs back to back and hammers the server, including the `expire_overdue` UPDATE.
  - A negative `HALL_TOP_N` or `HALL_RECENT_N` produces odd slices (`rows[:-1]`).
  - A non-integer value failing fast is consistent with `GAME_DURATION_S`.
- **Fix**: Clamp with `max(1, int(...))` for all three settings.
- **Decision**: PENDING

### F6 — Planned test assertions that are only implicit or missing

- **Severity**: 🔎 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: game/tests/test_services.py:147-220, game/tests/test_staff_views.py:140-299
- **Detail**: The plan lists these checks, but they are only implied or not asserted:
  - `hall_of_fame` "zero-solve ranked last" and "unfinished absent" are covered only indirectly, by the parity test and by `ranked_total == 6`.
  - "Top N order" asserts the place numbers but not which game is in each row.
  - A non-staff (not anonymous) GET of `/staff/hall` has no test.
  - After a hide, no test checks that the nick shows up in the moderation "Hidden" section.
  - The second-hide test checks the message text but not its `warning` level.
- **Fix**: Add the missing assertions to the existing tests. No new fixtures are needed.
- **Decision**: PENDING

### F7 — Each poll loads every ranked row, and the plan's performance note is out of date

- **Severity**: 🔎 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: game/services.py:169-178; plan.md "Performance Considerations"
- **Detail**: On every poll (every 5 s per open screen) and every moderation page load, `hall_of_fame` runs the `expire_overdue` UPDATE and then loads every finished, non-hidden `GameSession` with all columns. That is fine at booth scale, a few hundred rows. The plan still mentions "one small SELECT for recent games", but that query was dropped in plan review F3.
- **Fix**: Add `.only('id', 'nick', 'solved', 'attempts', 'started_at', 'last_solved_at', 'finished_at')` to the iteration in `hall_of_fame`, and fix the plan's performance paragraph.
- **Decision**: PENDING
