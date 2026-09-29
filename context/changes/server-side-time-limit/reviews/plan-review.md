<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Server-side Time Limit Implementation Plan

- **Plan**: context/changes/server-side-time-limit/plan.md
- **Mode**: Deep
- **Date**: 2026-09-29
- **Verdict**: REVISE
- **Findings**: 1 critical, 2 warnings, 4 observations

> Background run: triage was done afterwards with the user (2026-09-29). All 7 findings were accepted with the recommended fix and applied to `plan.md`.
>
> Deep-mode verification was done directly, without a sub-agent, because the touched surface is small (`game/` is about 10 files). The riskiest claims were checked against source, and so were other callers of `start_game`, `submit_command` and `current_challenge` (`game/management/commands/bench_game.py:60,71`, tests).

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | WARNING |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | FAIL |
| Plan Completeness | PASS |

## Grounding

Grounding: 11/11 paths ✓ (`config/settings.py`, `game/models.py`, `game/services.py`, `game/views.py`, `game/admin.py`, `game/templates/game/{play,done,home}.html`, `game/static/game/{play.js,game.css}`, `game/templatetags/game_text.py`; the new migration 0002 follows the existing `0001_initial.py`). 8/8 symbols ✓ (`_record`, `submit_command`, `current_challenge`, `_session_game`, `GameSessionAdmin.list_display`, `--warn`, `.counters` mono font, the "5 minutes" assertion at `test_views.py:50`). The 53-test baseline is confirmed (18 services + 29 views + 5 bench + 1 integration). Brief↔plan ✓. Several line references are stale; see F4.

The core design holds up against the code. Specifically:
- The widened `_record` guard.
- `Coalesce` on the solve update.
- Adding the `finished_at__isnull` guard to the cut-slug finish (`services.py:92-93`).
- Checking `is_finished` first in `play()` (`views.py:106-108`).
- The existing overlap test (`test_services.py:174-185`), which sets `current_slug=None`, so it stays closed under the new guard as the plan claims.
- The `.counters strong` color, which is overridden by `#timer.low` because the ID selector is more specific.

## Findings

### F1 — `start_game` "one `now`" contract can't be implemented as written

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM (real tradeoff; pause to reason through it)
- **Dimension**: Blind Spots
- **Location**: Phase 1 §3 Services (`start_game`); Phase 1 §6 Tests (first bullet)
- **Detail**: The plan says to "Set `started_at` explicitly or derive the deadline after create, but both must come from one `now`". Neither option works with the current model:
  - `started_at` is `DateTimeField(auto_now_add=True)` (`game/models.py:11`). Django 6.1.1's `DateTimeField.pre_save` overwrites the value on insert (`.venv/lib/python3.13/site-packages/django/db/models/fields/__init__.py:1691`, `if self.auto_now or (self.auto_now_add and add): value = timezone.now()`), so an explicit `started_at` is silently replaced.
  - Deriving the deadline after create means inserting without `deadline_at`, which the plan makes NOT NULL (§2). That raises an IntegrityError.
  - The Phase 1 test `deadline_at == started_at + GAME_DURATION_S` (exact equality) would fail under the only approach that works unchanged (two separate `timezone.now()` calls).
- **Fix A ⭐ Recommended**: In migration 0002, change `started_at` to `models.DateTimeField(default=timezone.now, db_index=True)`. Then in `start_game`, set `now = timezone.now()` and call `create(..., started_at=now, deadline_at=now + timedelta(seconds=settings.GAME_DURATION_S))`.
  - Strength: A true single instant, so the exact-equality test is valid. The migration change is state-only on SQLite (no schema change) and fits the 0002 migration that is already planned.
  - Tradeoff: One more `AlterField` in 0002, and `makemigrations --check` must be re-run.
  - Confidence: HIGH (the `default=` callable is not overridden by `pre_save`, unlike `auto_now_add`).
  - Blind spot: None significant. No other code writes `started_at` (grep shows only the model and tests).
- **Fix B**: Keep `auto_now_add`. Compute `deadline_at` from a separate `timezone.now()` at create, and change the test to `abs(deadline_at - started_at - duration) < 1 s`.
  - Strength: No model or migration change to `started_at`.
  - Tradeoff: The deadline can differ from `started_at + duration` by microseconds. This is harmless in practice but contradicts the plan's stated invariant, and S-03 elapsed-time maths would inherit the fuzz.
  - Confidence: HIGH.
  - Blind spot: None significant.
- **Decision**: FIX A applied (user-approved 2026-09-29): `started_at` becomes `default=timezone.now` in migration 0002; `start_game` passes one shared `now`.

### F2 — `performance.now()` may pause while the phone sleeps, so the countdown lags after unlock

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM (real tradeoff; pause to reason through it)
- **Dimension**: Blind Spots
- **Location**: Decisions §5 and §6; Phase 2 §2 Countdown logic; Manual check 2.5
- **Detail**: The plan says the client never resyncs from the server except on command responses. The displayed value is always `deadline - performance.now()`, which it assumes lets "a suspended tab catch up". On Linux and Android, the monotonic clock behind `performance.now()` (CLOCK_MONOTONIC) does not advance while the device is suspended, and browser implementations differ. After a phone lock of about 20 s, the timer can show roughly 20 s more than the server allows. The server stays authoritative, so fairness is unaffected (the Guardrail holds). But the player gets a surprise "Time's up." while the timer still shows time left, and manual check 2.5 ("locking the phone for 20 s ... shows the timer caught up") may fail on real Android devices. `visibilitychange` recomputes from the same paused clock, so it doesn't help.
- **Fix A ⭐ Recommended**: On `visibilitychange` to visible (and on `pageshow` with `persisted`), resync from the server with a tiny `GET /play/state` that returns `{remaining_ms, finished}`. It goes through `_session_game`, so expiry applies, and it navigates to `/done` if the game is finished.
  - Strength: The server stays the single source of truth, it's immune to both clock pausing and wall-clock changes, and bfcache restores are handled too.
  - Tradeoff: One new small view, URL and test. It slightly widens Phase 2 scope.
  - Confidence: MED (the direction is certain; how often real devices pause the clock is unmeasured).
  - Blind spot: Not verified on the target phones (Chrome Android, Safari iOS).
- **Fix B**: On `visibilitychange` to visible after the tab was hidden for more than about 2 s (measured with `performance.now()`, plus a `Date.now()` hint), call `location.reload()`. The server-rendered `data-remaining-ms` then resyncs.
  - Strength: No new endpoint, and it reuses the reload-safe page the plan already builds.
  - Tradeoff: A full page reload on every return. The input draft is lost, and "hidden duration" is itself measured on a clock that may have paused (a `Date.now()` fallback is only a trigger heuristic, not a time source).
  - Confidence: MED.
  - Blind spot: Behaviour when a command is in flight while the tab is backgrounded.
- **Decision**: FIX A applied (user-approved 2026-09-29): new `GET /play/state` resync on `visibilitychange` and bfcache `pageshow`; manual check 2.5 updated.

### F3 — Entry `TIME_UP` check "before any other check" relabels all-solved games as "Time's up."

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW (quick decision; fix is obvious and narrowly scoped)
- **Dimension**: End-State Alignment
- **Location**: Phase 1 §3 (`submit_command`: "If `now >= game.deadline_at`, return `TIME_UP` before any other check"); Decisions §7
- **Detail**: Decision 7 keeps `finished` ("The game is over.") for all-solved and stale-tab races. But the entry check runs before the existing `is_finished` / `current_challenge` check (`game/services.py:99-102`). A player who solved everything and then submits from a stale tab after the deadline gets 409 `time_up`. `/done` still says "All challenges solved!", so the command response contradicts the page. No planned test covers this ordering.
- **Fix**: In `submit_command`, return `FINISHED` first when `game.is_finished and game.current_slug is None`, then apply the `now >= deadline_at` → `TIME_UP` check before empty, too-long and sandbox. Add one test covering an all-solved game past its deadline returning `finished`.
- **Decision**: APPLIED (user-approved 2026-09-29): `finished` returned first for all-solved games, then `time_up`; test added.

### F4 — Stale line references and one soon-to-be-wrong test comment

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW (quick decision; fix is obvious and narrowly scoped)
- **Dimension**: Plan Completeness
- **Location**: Current State Analysis; Key Discoveries; References
- **Detail**: Several `services.py` and `views.py` references are off by 3-8 lines against the current tree:

  | Plan reference | Actual lines |
  |---|---|
  | `submit_command` `services.py:103-136` | 98-129 |
  | `_record` `139-165` | 132-158 |
  | guarded update `147-150` | 140-141 |
  | solve update `158-164` | 152-156 |
  | cut-slug finish `95-97` | 92-93 |
  | `play()` redirect `views.py:109-111` | 106-108 |
  | "5 minutes" assertion `test_views.py:49` | 50 |

  The `play.js` references are correct. Separately, the comment on the existing test at `game/tests/test_services.py:175` ("or, later, the time limit hit") becomes false under the sent-before rule, because a timeout mid-run now counts.
- **Fix**: Refresh the line numbers, and add "update the comment at `test_services.py:175` to say only an all-solved finish closes the game to in-flight runs" to Phase 1 §6.
- **Decision**: APPLIED (user-approved 2026-09-29): line references refreshed; test comment update added to Phase 1 tests.

### F5 — "Finished by timeout" predicate is implicit and derived two different ways

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW (quick decision; fix is obvious and narrowly scoped)
- **Dimension**: Architectural Fitness
- **Location**: Critical Implementation Details (`_record` guard); Phase 2 §4 (`done` `time_up`)
- **Detail**: The `_record` guard defines a timeout finish as `finished_at == deadline_at AND current_slug IS NOT NULL`. The `done` view uses `current_slug is not None` alone. Both are correct today, but S-03 (summary, rank) and S-05 will need the same concept, and a third derivation is likely. The equality `finished_at = F('deadline_at')` also holds for a grace solve of the last challenge (capped to `deadline_at`), and only `current_slug IS NULL` tells the two cases apart. That subtlety is easy to lose.
- **Fix**: Define it once, for example `GameSession.timed_out` (property) plus a `Q` constant in `services` used by the guard, and have `done` use the property.
- **Decision**: APPLIED (user-approved 2026-09-29): `GameSession.timed_out` property plus `TIMED_OUT_Q` in services.

### F6 — `/done` says "All challenges solved!" when the catalog ran out through a cut

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW (quick decision; fix is obvious and narrowly scoped)
- **Dimension**: End-State Alignment
- **Location**: Phase 2 §4 Done page reason
- **Detail**: The plan acknowledges that "running out of playable challenges" also clears `current_slug` (`current_challenge` cut path, `game/services.py:92-93`), but maps it to the heading "All challenges solved!" even though the player did not solve everything. It's rare (a mid-event `excluded.yaml` edit), but the heading would be wrong.
- **Fix**: Use "All challenges solved!" only when `game.solved >= total`, and otherwise fall back to the existing neutral "Finished!".
- **Decision**: APPLIED (user-approved 2026-09-29): `/done` heading is "All challenges solved!" only when `solved >= total`, else "Finished!".

### F7 — Progress step titles paraphrase the Manual Success Criteria

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW (quick decision; fix is obvious and narrowly scoped)
- **Dimension**: Plan Completeness
- **Location**: `## Progress` (1.5, 2.3-2.10)
- **Detail**: The Progress structure is valid: one `## Progress` at the bottom, `### Phase N` headings match the phases, the step counts match (Phase 1: 4+1, Phase 2: 2+8), and there are no checkboxes outside Progress. But the Manual titles are condensed rather than copied:
  - 2.6 drops "and the server still ends the game on time", which is the server-side half of the clock-change check.
  - 2.3 drops the device and 60 s setup.
  - 1.5 is reworded.

  An implementer ticking Progress might skip the dropped half.
- **Fix**: Copy the Success Criteria bullets into Progress verbatim, or at least restore the server half of 2.6.
- **Decision**: APPLIED (user-approved 2026-09-29): Progress manual steps copied verbatim from Success Criteria.
