# Server-side Time Limit Implementation Plan

## Overview

Enforce the 5-minute game limit on the server (roadmap S-02; PRD US-01, FR-006, FR-007, Guardrail "the limit cannot be extended or reset"). The player sees a countdown. Reloading returns to the same session with the same remaining time. The game ends when time runs out or every challenge is solved, and commands sent after the deadline are not counted.

## Current State Analysis

- `GameSession` (`game/models.py:6-24`) stores `started_at` (`auto_now_add`, indexed), `current_slug` (None = finished, "always together with finished_at"), `attempts`, `solved`, `last_solved_at` and `finished_at`. `is_finished` means `finished_at is not None`.
- The player's game is `request.session['game_id']` (`game/views.py:52-56`), so reload-safety and "same browser only" (FR-006 Socrates note) already work. The only thing missing is time.
- `services.submit_command` (`game/services.py:98-129`) has no time check. `_record` (`game/services.py:132-158`) runs a guarded `attempts` update (`finished_at__isnull=True`) that gates the `Attempt` insert. The S-01 plan addenda say S-02 should reuse this guard (`context/archive/2026-09-29-first-sandboxed-command/plan.md:530`).
- A solve on the last challenge sets `current_slug=None, finished_at=now`. A solve on any other challenge writes `finished_at=None` unconditionally. S-02 has to change that, because it could un-finish a game that timed out.
- There is no background worker, cron or task queue (single Django process, SQLite WAL). Expiry therefore has to be applied lazily when the game is next read.
- `play.js` already handles a non-`ran` response with `finished: true` by navigating to `/done` (`game/static/game/play.js:58-60`). The command request can take up to about 16 s on the server (10 s queue plus 6 s run, `play.js:6`).
- `home.html` already says "You have 5 minutes." (static text), and `test_views.py:50` asserts it.
- Settings: `USE_TZ=True`, `TIME_ZONE='UTC'`. Game knobs sit under `# Game sandbox concurrency (S-01)` in `config/settings.py:147-149` with `BASHDASH_*` env overrides.
- Tests: 53 game tests pass (`uv run python manage.py test game`). Races are simulated with a `run_command` side effect (`test_services.py:158-185`). There is no JS test infrastructure.

## Desired End State

- Each game has a fixed `deadline_at`, set once at start to `started_at + GAME_DURATION_S` (default 300 s). Changing the setting later never moves the deadline of a running game.
- Every read of a game (page views, command submits) first finishes it if it is overdue: `finished_at = deadline_at`. A bulk `expire_overdue()` helper exists so S-03 and S-05 can finish abandoned games before ranking.
- A command received at or after `deadline_at` gets 409 `time_up` ("Time's up."). It never reaches the sandbox and is neither stored nor counted.
- A command received before `deadline_at` counts even if its run finishes after the deadline ("sent-before" rule). That includes a solve, which is credited with `last_solved_at` capped at `deadline_at`.
- `/play` shows a countdown driven by the server's remaining milliseconds and a monotonic client clock, so the phone's wall clock doesn't matter. Each command response resyncs it. At 0 the input locks, any in-flight command is allowed to finish, and the page moves to `/done`.
- `/done` says whether time ran out or everything was solved (the full summary is S-03).

Verify: `uv run python manage.py test game challenges` is green. Then run the app with `BASHDASH_GAME_DURATION_S=30` and check that the countdown, reload, expiry, a late command and a stale tab all behave as described (see Manual Testing Steps).

### Key Discoveries:

- `_record`'s guarded counter update (`game/services.py:140-141`) is the single place that decides whether a run counts, so the time rule plugs in there.
- The non-last solve update (`game/services.py:152-156`) writes `finished_at=None if nxt else now`, which would clear a timeout finish. It must preserve an existing `finished_at`.
- `current_challenge()`'s cut-slug path (`game/services.py:92-93`) writes `finished_at=now` without a `finished_at__isnull` guard. Add the guard so it can't overwrite a timeout stamp.
- `play()` only redirects to `/done` when `current_challenge()` is None (`game/views.py:106-108`). Once a timed-out game keeps its `current_slug`, `play()` must check `is_finished` first.
- The JS already navigates on `finished: true`, so the 409 `time_up` path needs no new client logic beyond the message.

## Decisions (taken without live Q&A; defaults grounded in research)

This plan ran as a background job with no interactive question tool. Each decision below uses the ⭐ recommended option. Override any of them before `/10x-implement` if you disagree. The decisions were reviewed and accepted by the user on 2026-09-29, together with the plan-review fixes F1-F7 (`reviews/plan-review.md`), which are applied below.

1. **Deadline storage**: add a `deadline_at` column, set at start. The alternative, computing `started_at + setting` on every read, lets running games drift if the setting changes and makes the bulk update and S-03 queries clumsier.
2. **Cut-off rule**: sent-before. A command whose request arrived before the deadline counts, even if the queue plus the run push it past the deadline, which is bounded at about 16 s. The alternative, recorded-before (just reusing the `finished_at` guard), would silently drop a last-second correct answer that the player already paid for. PRD: "Komenda **wysłana** po upływie 5 minut nie jest liczona".
3. **Expiry mechanism**: finish lazily on read, plus a bulk `expire_overdue()` for later slices. No background worker or cron. `finished_at` for a timeout is `deadline_at`, not the moment someone happened to look.
4. **`current_slug` on timeout**: keep it. It lets an in-flight run on the current challenge still be credited, and it records where the player stopped. "Finished" means `finished_at IS NOT NULL`, and `current_slug IS NULL` now means only "solved everything (or the catalog ran out)".
5. **Client timer**: the server sends `remaining_ms`. The client counts down with `performance.now()` and never compares against `Date.now()` or an absolute timestamp, so changing the phone's clock can't help (Guardrail). Every command response resyncs it. Because `performance.now()` may stop advancing while a phone is suspended (Linux and Android), the client also resyncs from a small `GET /play/state` endpoint whenever the tab becomes visible again or the page is restored from the bfcache (plan review F2).
6. **At 0 on the client**: lock the input. If a command is in flight, wait for its response, which carries `finished: true`. Otherwise navigate to `/done` about 1 s after 0, which absorbs clock skew between client and server.
7. **Late command response**: a new status `time_up` returns 409 with "Time's up.", distinct from `finished` ("The game is over."), which is kept for all-solved and stale-tab races.
8. **Low-time cue**: the timer switches to the existing `--warn` colour when 30 s or less remain. A cheap CSS class, no sound or vibration.
9. **Tests**: backdate `deadline_at` directly in the DB instead of mocking time. Simulate the in-flight deadline race with a `run_command` side effect that moves `deadline_at` into the past. The countdown JS is verified manually, because there is no JS test infrastructure.

## What We're NOT Doing

- A background sweeper, cron, or Celery. Lazy expiry plus `expire_overdue()` is enough.
- The full summary page, rank, and 6-digit prize code (S-03). `/done` only gets a one-line reason.
- Resuming a game in another browser or after closing the tab and clearing cookies (accepted in the PRD, FR-006).
- Pausing or extending time, a per-player duration, or an admin "add time" action (the Guardrail forbids it).
- Refunding time lost to server latency or queueing. The PRD accepts about 1 s per command, and the sent-before rule already covers the edge at the deadline.
- A soft block on a second game (FR-016, parked).
- JS unit test infrastructure.

## Implementation Approach

Phase 1 makes the server authoritative: schema, setting, expiry, cut-off, and the JSON contract. It is fully covered by Django tests, and the UI still works unchanged because the JS already follows `finished`. Phase 2 layers on the visible countdown and the end-of-game UX, which only reads `remaining_ms`.

## Critical Implementation Details

- **State sequencing in `_record`**: the counting guard becomes "not finished, OR finished by timeout with the player still on a challenge": `Q(finished_at__isnull=True) | TIMED_OUT_Q`, where `TIMED_OUT_Q` is the query form of `GameSession.timed_out` defined once in `services`. This lets a sent-before run on a game already expired by another request (for example the countdown hitting `/done`) still count. A game finished by solving everything (`current_slug` None) stays closed. The entry check in `submit_command` (`now >= deadline_at` → `time_up`) is what enforces "sent after doesn't count", so `_record` must not re-check the deadline against the record time.
- **The solve update must never clear or move an existing `finished_at`**. Use `Coalesce(F('finished_at'), <new value>)` or an equivalent. When the last challenge is solved during the grace window, stamp `finished_at` and `last_solved_at` with `min(now, deadline_at)`, so ranking tie-breaks (S-03) never see times past the limit.
- **Expire after recording**: the command view builds its response after `submit_command` returns. `submit_command` must run `expire_overdue(game.pk)` after `_record` (and before `refresh_from_db`), so a grace run's response already says `finished: true` and the client navigates straight to `/done`.

## Phase 1: Server-side deadline and enforcement

### Overview

Add `deadline_at`, lazy expiry, the sent-before cut-off and `remaining_ms` in responses. After this phase the limit is fully enforced, even though the page shows no timer yet.

### Changes Required:

#### 1. Setting

**File**: `config/settings.py`

**Intent**: A single knob for game length, overridable for manual testing.

**Contract**: `GAME_DURATION_S = int(os.environ.get('BASHDASH_GAME_DURATION_S', 300))` in a new `# Game time limit (S-02)` block next to the S-01 game settings.

#### 2. Model and migration

**File**: `game/models.py`, `game/migrations/0002_gamesession_deadline_at.py`

**Intent**: Store each game's fixed deadline, and correct the model comment's finished invariant.

**Contract**:
- `deadline_at = models.DateTimeField(db_index=True)`, non-null. `db_index=True` because `expire_overdue()` filters on `finished_at IS NULL AND deadline_at <= now`.
- The docstring and comment say: finished ⇔ `finished_at` is set. `current_slug` None ⇔ nothing left to solve. A timed-out game keeps `current_slug`.
- `started_at` changes from `auto_now_add=True` to `default=timezone.now` (keep `db_index=True`). Django's `pre_save` silently overwrites an explicit `started_at` on insert when `auto_now_add` is set, so `start_game` could not otherwise store one shared instant in both fields. This is an `AlterField` in 0002 and is state-only on SQLite. No other code writes `started_at`.
- `GameSession.timed_out` property: `finished_at is not None and current_slug is not None`. This is the single definition of "the clock ended this game". A game finished by solving everything, or by running out of playable challenges, has `current_slug` None. A grace solve of the last challenge is also stamped `finished_at == deadline_at`, but it clears `current_slug`, so it is not `timed_out`.
- The migration does four things: alters `started_at` to `default=timezone.now`, adds `deadline_at` as nullable, backfills with a RunPython step (`started_at + 300 s` for existing rows, with a no-op reverse), then alters it to non-null. It must be generated or checked with `makemigrations`, so that `makemigrations --check` stays clean afterwards.

#### 3. Services

**File**: `game/services.py`

**Intent**: Make time a game rule, owned by the service layer, as the module docstring says ("nothing else knows the rules").

**Contract**:
- `start_game(nick)` sets `deadline_at = now + timedelta(seconds=settings.GAME_DURATION_S)`, where `now = timezone.now()` is captured once and passed to `create(..., started_at=now, deadline_at=...)`. Both fields come from the same instant, which works because `started_at` no longer uses `auto_now_add` (see Model and migration).
- New module-level `TIMED_OUT_Q = Q(finished_at=F('deadline_at'), current_slug__isnull=False)`, the query form of `GameSession.timed_out`. Used by the `_record` counting guard, and reusable by S-03 and S-05.
- New status `TIME_UP = 'time_up'`, not counted.
- New `expire_overdue(game_id=None, now=None) -> int`: a single bulk `UPDATE ... SET finished_at = deadline_at WHERE finished_at IS NULL AND deadline_at <= now` (scoped to one pk when `game_id` is given). Returns the row count. Idempotent.
- New `remaining_ms(game, now=None) -> int`: `max(0, deadline_at - now)` in whole ms. Returns 0 for a finished game.
- `submit_command`: capture `now` at entry and call `expire_overdue(game_id, now)` before loading. Then check in this order: (1) if the game is finished and not `timed_out` (all solved, or the catalog ran out), return `FINISHED`, so a stale tab on a fully solved game says "The game is over." and matches `/done`; (2) if `now >= game.deadline_at`, return `TIME_UP` before any other check (empty, too long, sandbox). Otherwise keep the existing flow, and pass the entry time where needed. After `_record`, call `expire_overdue(game.pk)` and then `refresh_from_db`.
- `_record`: counting guard, non-clearing solve update and capped timestamps as described in Critical Implementation Details.
- `current_challenge`: add `finished_at__isnull=True` to the cut-slug finish update's filter.

#### 4. Views

**File**: `game/views.py`

**Intent**: Every page and response reflects expiry. The command JSON carries the remaining time.

**Contract**:
- `_session_game` calls `services.expire_overdue(game_id)` before loading, so `home`, `start`, `play` and `done` all see an up-to-date `is_finished`.
- `play` redirects to `done` when `game.is_finished`, before calling `current_challenge`.
- `HTTP_STATUS[TIME_UP] = 409` and `MESSAGES[TIME_UP] = "Time's up."`.
- Every command response that already carries counters (every status except `no_game`, `bad_request` and 413) gains `remaining_ms: int`.
- `play` passes `remaining_ms` to the template context (used in Phase 2).

#### 5. Admin

**File**: `game/admin.py`

**Intent**: Staff can see the deadline when inspecting games.

**Contract**: add `deadline_at` to `GameSessionAdmin.list_display`, after `started_at`.

#### 6. Tests

**File**: `game/tests/test_services.py`, `game/tests/test_views.py`

**Intent**: Pin every time rule. Backdate `deadline_at` via `GameSession.objects.filter(...).update(...)` instead of mocking time.

**Contract**: new tests, at least:
- `start_game` sets `deadline_at == started_at + GAME_DURATION_S`, and honours `override_settings(GAME_DURATION_S=...)`.
- Submit after the deadline → `time_up`, sandbox not called, no Attempt, `attempts` unchanged, `finished_at == deadline_at`, `current_slug` preserved.
- Sent-before, recorded-after (a side effect moves `deadline_at` into the past mid-run): counted and stored. A correct answer advances and increments `solved`, `last_solved_at <= deadline_at`, and the game ends finished with `finished_at == deadline_at`.
- Same race, but another request expires the game mid-run (side effect sets `deadline_at` in the past and calls `expire_overdue`): still counted. A correct answer on a non-last challenge does not clear `finished_at`.
- Grace solve of the last challenge: `finished_at == last_solved_at == deadline_at`, `current_slug` None.
- The existing all-solved overlap test still returns `finished` (the solve-all game stays closed to grace runs). Update its comment at `test_services.py:175` ("or, later, the time limit hit") to say that only an all-solved finish closes the game to in-flight runs, because a timeout mid-run now counts.
- An all-solved game submitted to after its deadline returns `finished`, not `time_up`, and the sandbox is not called.
- `GameSession.timed_out` is true for a timed-out game that keeps `current_slug`, and false for an all-solved game, including one solved by a grace solve stamped at `deadline_at`.
- `expire_overdue()` finishes only overdue unfinished games, leaves finished and in-time games untouched, and is idempotent.
- `remaining_ms` is clamped at 0 and is 0 for finished games.
- Views: expired game → `/play` and `/` redirect to `/done`, `/done` renders. Late command → 409 `{"status": "time_up", "finished": true, ...}`. `remaining_ms` is present and roughly `GAME_DURATION_S*1000` on a fresh game's command response, and absent on `no_game`.

### Success Criteria:

#### Automated Verification:

- Game and challenge tests pass: `uv run python manage.py test game challenges`
- Django checks pass: `uv run python manage.py check`
- No missing migrations: `uv run python manage.py makemigrations --check --dry-run`
- Migration applies to an existing dev DB with S-01 games and backfills `deadline_at`: `uv run python manage.py migrate`

#### Manual Verification:

- With `BASHDASH_GAME_DURATION_S=30`, start a game, wait 30 s, then submit via the existing UI: the verdict says "Time's up.", the page goes to `/done`, and the admin shows `finished_at == deadline_at` with attempts unchanged

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Countdown and end-of-game UX

### Overview

Show the remaining time, keep it honest across reloads and suspended or backgrounded tabs (resync from the server), lock play at 0, and say why the game ended.

### Changes Required:

#### 1. Play page markup

**File**: `game/templates/game/play.html`

**Intent**: A server-rendered countdown that is correct even before the JS runs.

**Contract**: add a `Time: <strong id="timer" data-remaining-ms="{{ remaining_ms }}">m:ss</strong>` span to `.counters`. The initial `m:ss` is rendered server-side from `remaining_ms` (a small template filter in `game/templatetags/game_text.py`, or a context value from the view).

#### 2. Countdown logic

**File**: `game/static/game/play.js`

**Intent**: Tick the timer from a monotonic clock, resync from the server, and end cleanly.

**Contract**:
- `deadline = performance.now() + remaining_ms`, set from the data attribute on load and from `data.remaining_ms` on every command response that has it (any status).
- Tick with `setInterval` about every 250 ms. The displayed value is always `deadline - performance.now()`. Format as `m:ss` and floor at `0:00`.
- Resync from the server on `visibilitychange` to visible and on `pageshow` with `event.persisted`: `fetch` the state endpoint (see §5), set `deadline = performance.now() + remaining_ms`, and navigate to `form.dataset.doneUrl` if the response says `finished`. Don't rely on `performance.now()` alone to catch up after the device was suspended. A failed fetch keeps the current timer, because the server enforces the limit regardless.
- Add a `low` class to the timer at 30 s or less remaining.
- At 0: disable the input and button permanently (a separate flag from `busy`, so `setBusy(false)` after an in-flight response doesn't re-enable them) and show "Time's up." If no request is in flight, navigate to `form.dataset.doneUrl` about 1 s later. If one is in flight, let its `render` handle it: it will carry `finished: true`. If the response is a network error or abort, navigate to `/done` anyway.
- A submit attempted after 0 is blocked client-side. The server enforces the limit regardless.

#### 3. Styles

**File**: `game/static/game/game.css`

**Intent**: A readable timer on mobile, plus the low-time cue.

**Contract**: `#timer` uses the mono font (it inherits from `.counters`). `#timer.low { color: var(--warn); }`. The counters row must still fit at 320 px width with three items.

#### 4. Done page reason and rules text

**File**: `game/templates/game/done.html`, `game/templates/game/home.html`, `game/views.py`

**Intent**: The player understands why the game ended. The rules text matches the configured duration.

**Contract**:
- `done` passes the heading state derived from `game.timed_out` (the shared definition in the model). The heading reads "Time's up!" when `timed_out`. Otherwise it reads "All challenges solved!" only when `game.solved >= total playable challenges`, and falls back to the existing neutral "Finished!" when the catalog ran out through a cut (`current_challenge` cut path). A solve of the last challenge during the grace window clears `current_slug`, so it correctly reads "All challenges solved!". The rest of the page is unchanged (S-03 replaces it).
- `home` renders the duration from `settings.GAME_DURATION_S`, so the default still reads "5 minutes" (the existing test at `test_views.py:50` stays valid).

#### 5. Resync endpoint

**File**: `game/views.py`, the game URL conf (next to the existing `play`, `command` and `done` routes)

**Intent**: Let the client re-read the authoritative remaining time when its monotonic clock may have paused.

**Contract**: `GET /play/state` returns JSON `{"remaining_ms": int, "finished": bool}`. It goes through `_session_game`, so expiry is applied first, and `remaining_ms` comes from `services.remaining_ms`. Without a game in the session it returns the same `no_game` shape and status the command view uses. GET only, no side effects beyond expiry, so CSRF doesn't apply.

#### 6. Tests

**File**: `game/tests/test_views.py`

**Intent**: Pin the server-rendered parts of the UI and the resync endpoint.

**Contract**: `/play/state` returns `remaining_ms` roughly equal to the configured duration and `finished: false` for a fresh game, `remaining_ms == 0` and `finished: true` for an expired game, and the `no_game` response without a session game. `/play` contains `id="timer"` with a `data-remaining-ms` roughly equal to the configured duration and an initial `m:ss` text (for example `5:00` or `4:59`). `/done` shows "Time's up!" for an expired game, "All challenges solved!" for a solved-out game, and "Finished!" when the catalog ran out through a cut without everything solved. Home shows "5 minutes" by default and reflects `override_settings(GAME_DURATION_S=120)` as "2 minutes".

### Success Criteria:

#### Automated Verification:

- Game and challenge tests pass: `uv run python manage.py test game challenges`
- Django checks pass: `uv run python manage.py check`

#### Manual Verification:

- On a phone-width browser (Chrome Android or Safari iOS, or devtools emulation) with `BASHDASH_GAME_DURATION_S=60`, the timer counts down smoothly and turns warn-coloured at 0:30
- Reloading mid-game shows the same remaining time (±1 s), not a reset
- Backgrounding the tab or locking the phone for 20 s, then returning, shows the timer resynced with the server (within about 1 s of the true remaining time), on a real Android phone if available
- Changing the device clock mid-game neither extends nor shortens the countdown, and the server still ends the game on time
- At 0:00 the input locks, the page moves to `/done` within about 2 s, and it shows "Time's up!"
- A command sent in the last 1-2 s (use a slow one such as `sleep 3; ls`) still shows as counted in the admin, and the page then lands on `/done`
- A stale second tab of the same game, used after the deadline, gets "Time's up." and goes to `/done`
- Solving all challenges before time runs out shows "All challenges solved!"

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- Service-level time rules (Phase 1 §6): deadline at start, entry cut-off, sent-before grace in both race shapes, the non-clearing solve update, capped timestamps, idempotent bulk expiry, and the remaining-time clamp.
- View-level contract: redirects for expired games, the 409 `time_up` payload, `remaining_ms` presence and absence, the `/play/state` endpoint, and the rendered timer, done reason and rules text.

### Integration Tests:

- The existing `game/tests/test_integration.py` must stay green (the real sandbox with a default 300 s duration is unaffected). No new Docker-backed test is needed, because the time rules are pure DB and service logic.

### Manual Testing Steps:

1. `BASHDASH_GAME_DURATION_S=60 uv run python manage.py runserver`, then open `/` at phone width and start a game.
2. Watch the countdown, then reload at about 0:45: the time must not reset.
3. Background the tab (or lock the phone) for 20 s, return, and check that the timer resynced with the server.
4. At about 0:02, send `sleep 3; ls`. It should be counted (check the admin), and the page then goes to `/done` with "Time's up!".
5. Open a second tab on `/play` before expiry, wait past the deadline, and submit there: "Time's up." then `/done`.
6. In the admin, check `finished_at == deadline_at`, and that attempts match the Attempt rows.
7. With the default duration, solve everything quickly (or cut challenges via `excluded.yaml` for a short run): "All challenges solved!".

## Performance Considerations

`expire_overdue(game_id)` adds one indexed single-row UPDATE per request. It is negligible next to a 0.15-6 s sandbox run, and it stays outside the no-transaction-across-`run_command` rule because it runs before and after the run, never during it. The bulk version (later slices) touches only overdue rows via the `deadline_at` index.

## Migration Notes

`0002` backfills `deadline_at = started_at + 300 s` for any S-01 rows, so old dev games expire correctly on their next read. Nothing is deployed yet (F-02 is blocked), so there is no production data. Rolling back is `migrate game 0001`: the reverse drops the column, and the RunPython reverse is a no-op.

## References

- Roadmap: `context/foundation/roadmap.md` (S-02)
- PRD: `context/foundation/prd.md` (US-01 acceptance criteria, FR-006, FR-007, Guardrails, Business Logic)
- S-01 plan and addenda (guard reuse): `context/archive/2026-09-29-first-sandboxed-command/plan.md:514-531`
- S-01 impl review F2 (overlap semantics): `context/archive/2026-09-29-first-sandboxed-command/reviews/impl-review.md:80-99`
- Counting guard: `game/services.py:132-158`; submit flow: `game/services.py:98-129`; views: `game/views.py:52-162`; client: `game/static/game/play.js`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Server-side deadline and enforcement

#### Automated

- [ ] 1.1 Game and challenge tests pass: `uv run python manage.py test game challenges`
- [ ] 1.2 Django checks pass: `uv run python manage.py check`
- [ ] 1.3 No missing migrations: `uv run python manage.py makemigrations --check --dry-run`
- [ ] 1.4 Migration applies to an existing dev DB with S-01 games and backfills `deadline_at`: `uv run python manage.py migrate`

#### Manual

- [ ] 1.5 With `BASHDASH_GAME_DURATION_S=30`, start a game, wait 30 s, then submit via the existing UI: the verdict says "Time's up.", the page goes to `/done`, and the admin shows `finished_at == deadline_at` with attempts unchanged

### Phase 2: Countdown and end-of-game UX

#### Automated

- [ ] 2.1 Game and challenge tests pass: `uv run python manage.py test game challenges`
- [ ] 2.2 Django checks pass: `uv run python manage.py check`

#### Manual

- [ ] 2.3 On a phone-width browser (Chrome Android or Safari iOS, or devtools emulation) with `BASHDASH_GAME_DURATION_S=60`, the timer counts down smoothly and turns warn-coloured at 0:30
- [ ] 2.4 Reloading mid-game shows the same remaining time (±1 s), not a reset
- [ ] 2.5 Backgrounding the tab or locking the phone for 20 s, then returning, shows the timer resynced with the server (within about 1 s of the true remaining time), on a real Android phone if available
- [ ] 2.6 Changing the device clock mid-game neither extends nor shortens the countdown, and the server still ends the game on time
- [ ] 2.7 At 0:00 the input locks, the page moves to `/done` within about 2 s, and it shows "Time's up!"
- [ ] 2.8 A command sent in the last 1-2 s (use a slow one such as `sleep 3; ls`) still shows as counted in the admin, and the page then lands on `/done`
- [ ] 2.9 A stale second tab of the same game, used after the deadline, gets "Time's up." and goes to `/done`
- [ ] 2.10 Solving all challenges before time runs out shows "All challenges solved!"
