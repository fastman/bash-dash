<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Server-side Time Limit

- **Plan**: context/changes/server-side-time-limit/plan.md
- **Scope**: Full plan (Phases 1-2 of 2; commits 834b6eb, e88a071)
- **Date**: 2026-09-29
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 2 warnings, 2 observations
- **Triage**: done with the user after the background run (2026-09-29). F1, F3 and F4 were fixed; F2 (manual verification) is deferred to Phase 9.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | WARNING |

## Success criteria run

| Command | Result |
|---|---|
| `uv run python manage.py test game challenges` | PASS: 135 tests, OK |
| `uv run python manage.py check` | PASS: no issues |
| `uv run python manage.py makemigrations --check --dry-run` | PASS: "No changes detected" |
| Migration on a DB with S-01 rows | PASS on a scratch SQLite copy (the dev DB was not touched). I migrated to 0001, inserted one in-progress row and one all-solved row, then migrated forward. `deadline_at = started_at + 300 s` (microseconds preserved). `expire_overdue()` finished only the in-progress row at its deadline (`timed_out=True`). The all-solved row kept its `finished_at` (`timed_out=False`). Reversing to 0001 drops the column cleanly. |

Manual rows 1.5 and 2.3-2.10 are all still `[ ]` (see F2).

## Plan-flagged risks: verified, no finding

- **`_record` counting guard** (`game/services.py:175`): `Q(finished_at__isnull=True) | TIMED_OUT_Q`, as planned. `TIMED_OUT_Q` (`services.py:29`) matches `GameSession.timed_out` (`models.py:34-36`). A timed-out game can only reach `_record` through a sent-before request, because every later request hits the entry `TIME_UP` check. `_record` does not re-check the deadline. Covered by `test_expired_by_another_request_mid_run_still_counts_and_stays_finished` and `test_sent_before_recorded_after_is_counted_and_solve_advances`.
- **The solve update never clears `finished_at`** (`services.py:188-194`): non-last solve writes `finished_at=F('finished_at')`, last solve writes `Coalesce(F('finished_at'), Least(now, deadline_at))`, and `last_solved_at` is capped with `Least`. Both are correct. The cut-path finish gained the `finished_at__isnull=True` guard (`services.py:117`, test `test_cut_finish_does_not_overwrite_timeout_stamp`).
- **`submit_command` check order** (`services.py:124-130`): expire, then `FINISHED` for finished-and-not-timed-out, then `TIME_UP` when `now >= deadline_at`, then everything else. This matches the plan. `test_all_solved_game_after_deadline_says_finished` and `test_submit_after_deadline_is_time_up_and_not_counted` pin it. `expire_overdue(game.pk)` runs after `_record` and before `refresh_from_db` (`services.py:159-160`).
- **Migration backfill** (`game/migrations/0002_gamesession_deadline_at.py`): it performs the four planned operations, the reverse is a no-op, and the migration check is clean. Verified empirically (above).
- **play.js resync/lock**: resync on `visibilitychange` and on `pageshow` with `persisted` works. The monotonic `performance.now()` is used throughout and `Date.now()` never is. The `locked` flag is kept separate from `busy`, and `setBusy` respects it. One gap in the lock logic remains (F1).

## Findings

### F1 — Input stays locked with no navigation when an in-flight response arrives with `finished: false` after the local timer hits 0

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality (reliability)
- **Location**: game/static/game/play.js:53-60, play.js:102, play.js:136-140
- **Detail**: When `tick()` hits 0 it sets `locked = true` and schedules a single `setTimeout(() => { if (!busy) goDone(); }, 1000)`. If a command is in flight, the page relies on that command's response carrying `finished: true` (plan Decision 6). But the response can carry `finished: false`:
  - (a) The client clock runs slightly ahead of the server's. The in-flight command is recorded before the server deadline, so the response has `finished: false` and `remaining_ms` > 0.
  - (b) The response is a non-counted status for a game that has not expired yet (`busy` 503, `unavailable`, `internal`).

  In either case `render()` does not navigate. `setBusy(false)` keeps the input disabled because `locked` is set. The one-shot timeout has already fired and done nothing (`busy` was true then). `tick()` never re-arms because of `!locked`. The player is stuck on a disabled page until they reload manually. The server still enforces the limit, so this is a UX dead end rather than an integrity problem. In case (a) the player is also locked out of their last few hundred ms. No automated test covers it (there is no JS test infrastructure), and manual row 2.7 is unchecked.
- **Fix A ⭐ Recommended**: In the final `.then` of the submit chain (after `setBusy(false)`), add `if (locked) setTimeout(goDone, 1000);`. `/done` redirects back to `/play` when the server has not finished the game yet (`views.py:180-181`), and `/play` re-renders with the authoritative `remaining_ms`.
  - Strength: 1-2 lines. It reuses the existing server-side redirect as the source of truth, and the "navigate anyway on network error" path already follows this pattern (`play.js:131`).
  - Tradeoff: in case (a), one extra `/done` → `/play` bounce, a sub-second flash.
  - Confidence: HIGH, because `done` already redirects unfinished games to `play`.
  - Blind spot: not exercised in a real browser.
- **Fix B**: When a response arrives while `locked` and `remaining_ms > 0` and not `finished`, clear `locked` and re-enable the input so `tick()` locks again at the new 0.
  - Strength: the player keeps every server-granted millisecond and there is no page bounce.
  - Tradeoff: adds an unlock path to the state machine (the plan wanted the lock to be permanent), and the input briefly re-enables for a few hundred ms, which is confusing.
  - Confidence: MED. More states to get wrong without JS tests.
  - Blind spot: interaction with a resync firing at the same moment.
- **Decision**: FIX A applied (user-approved 2026-09-29): the submit chain's final `.then` schedules `goDone` after 1 s when `locked`. Not exercised in a real browser; covered by manual check 2.8.

### F2 — All manual verification is pending, including the only coverage of the countdown and lock JS

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/server-side-time-limit/plan.md:312, plan.md:323-330
- **Detail**: Rows 1.5 and 2.3-2.10 are `[ ]`. This is honest: nothing was rubber-stamped. But Phase 2 landed without the Phase 1 manual confirmation that the plan's Implementation Note calls for. The client timer, resync and lock behaviour are verified only manually (plan Decision 9), so they are currently unverified, and F1 lives in exactly that code.
- **Fix**: Run the Manual Testing Steps with `BASHDASH_GAME_DURATION_S=30`/`60` before moving the change to `implemented`. Also exercise "command in flight when the local timer hits 0" (for example `sleep 3; ls` sent at about 0:01) to confirm the F1 behaviour, before and after the fix.
- **Decision**: DEFERRED to Phase 9 of /10x-ship (user-approved 2026-09-29): the manual checks stay open in plan.md until run by a human.

### F3 — Local `timer` variable in the submit handler shadows the timer element

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: game/static/game/play.js:116 (shadows play.js:19)
- **Detail**: Phase 2 added the outer `var timer = document.getElementById('timer')`, but the pre-existing `var timer = setTimeout(...)` inside the submit handler shadows it. Behaviour is correct today: `tick()` and `render()` close over the outer element, and `clearTimeout(timer)` uses the local. But any future edit that touches the timer element inside the handler would silently get a timeout id instead.
- **Fix**: Rename the local to `fetchTimer` (lines 116 and 137).
- **Decision**: APPLIED (user-approved 2026-09-29): renamed to `fetchTimer`.

### F4 — `bench_game` runs longer than `GAME_DURATION_S` mix instant `time_up` samples into the latency stats

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality (tooling reliability)
- **Location**: game/management/commands/bench_game.py:60-82
- **Detail**: `bench_game` drives `services.start_game` and `submit_command` directly, so its games now expire after `GAME_DURATION_S` (300 s by default). A long run (many `--commands`, or `--mix with-abuse` under a saturated queue) would get `time_up` outcomes that return in microseconds without touching the sandbox. Those samples are appended to the p50/p95 samples, which would make the benchmark look faster than it is. `time_up` is shown in the `statuses:` line but is not treated as a failure. The default run (15 players x 10 commands) finishes well within 300 s, so this is latent.
- **Fix**: Only append latency samples for statuses that reached the sandbox (or skip `TIME_UP`), or have `bench_game` warn or fail when any `time_up` is seen.
- **Decision**: APPLIED (user-approved 2026-09-29): `time_up` outcomes are kept out of the latency samples and added to `FAILING_STATUSES`, so an over-long run fails instead of skewing the numbers.

## Notes

- The benign unplanned additions are all within the plan's intent: the `NO_GAME` constant shared by `command` and `state`, the `duration_text` filter for the home rules text, `test_state_endpoint_is_get_only`, and `test_cut_finish_does_not_overwrite_timeout_stamp`. They are recorded here instead of as a Scope finding.
- Every test listed in plan §6 (both phases) has a matching test. The existing overlap-test comment was updated as planned.
