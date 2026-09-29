# First Sandboxed Command Implementation Plan

## Overview

Roadmap slice **S-01** (north star). The player reads the rules, enters a nick and clicks "Start". They then solve main-set challenges in a fixed order by typing bash commands. Each command runs in the hardened sandbox from F-01, and the player sees its output plus a correct/incorrect verdict. Every command that runs increases an attempts counter. This slice also resolves F-01's carry-overs (a)–(d) and measures the roadmap unknown: does a command stay around 1 s with about 15 concurrent players?

PRD refs: US-01, FR-002, FR-003, FR-004, FR-005, NFR (command isolation, ≤ ~6 s per command).

## Current State Analysis

- The Django 6.1 scaffold has one app, `challenges` (F-01). It has no models, views, templates or player-facing URLs. `config/urls.py` routes only `admin/`.
- `challenges/sandbox.py::run_command(challenge, command, *, client=None, host_overrides=None) -> SandboxResult` already does everything the game needs from the sandbox:
  - It raises `ValueError` for commands over 300 chars.
  - It raises `SandboxUnavailable` if Docker fails before the container runs.
  - Otherwise it always returns a result with `correct`, `output` (capped at 64 KB), `error` (player-facing), `error_internal` (our bug), `timed_out` and `duration_s`, and it always removes the container.
- `challenges/catalog.py`: `main_set()` returns the playable challenges in upstream order (42 today, because `excluded.yaml` is `{}`). `get(slug)` also returns excluded challenges (carry-over d).
- Measured in F-01 on the dev host: a typical run takes ~0.14 s sequentially and ~0.3 s p95 at concurrency 8. `find_primes` is the outlier at ~1.5–2 s. Abuse runs (fork bomb, CPU spin, sleep) take ~5.2 s and do not affect other runs.
- Challenge `description` is plain text with Markdown-style backticks and ``` fences. It contains no HTML (none of the 42 descriptions has `<`). `title` comes from `disp_title`.
- SQLite is the database, with default options (`config/settings.py:77`). Default options mean concurrent writers can get "database is locked".
- Tests use Django's runner (`uv run python manage.py test`), with an in-memory docker fake in `challenges/tests/fakes.py`. The Docker integration tests `skipUnless` a daemon and image are present. 45 tests pass today.

### Carry-overs from F-01's implementation review (F9), which this plan must resolve

- **(a)** `reap_stale()` removes *any* `created`/`exited` labelled container regardless of age (`challenges/sandbox.py:228-245`). If it runs while another worker is between `wait` and `remove`, it deletes that worker's container and turns the run into an `error_internal`.
- **(b)** The module-cached client uses docker-py's default `max_pool_size=10` (`docker/constants.py:40`). Concurrency above 10 on the shared client churns the pool.
- **(c)** `client.images.get(SANDBOX_IMAGE)` runs on every command (`sandbox.py:179`), costing one extra API round trip per run.
- **(d)** `catalog.get(slug)` resolves excluded challenges. The game must only serve from `main_set()`.

## Desired End State

- `uv run python manage.py runserver`, then open `/` on a phone-width browser.
  - The page shows the rules: challenges in order, every command counts as an attempt, fewer attempts is better. A 5-minute limit is mentioned; S-02 enforces it.
  - It has a nick field and a "Start" button.
- After Start, `/play` shows the current challenge (number of total, title, description), a command input and an attempts counter.
- Submitting a command shows its output and a verdict ("Correct" / the player-facing error / "Timed out") without a full page reload.
  - A correct command advances to the next challenge.
  - An incorrect one keeps the player on the current challenge.
- Reloading `/play` returns to the same game: same challenge, same attempts, and the last attempt's output still visible.
- Solving the last challenge ends the game and shows a minimal "finished" page (solved count and attempts). S-03 replaces it with the real summary.
- Every run of a command in a game is stored as an `Attempt` row. The `GameSession` row holds the counters that S-02/S-03 build on: `started_at`, `attempts`, `solved`, `last_solved_at` and `finished_at`.
- Carry-overs (a)–(d) are fixed and covered by unit tests.
- `uv run python manage.py bench_game --players 15` reports the per-command latency p50/p95 through the game service. The numbers are recorded in `context/changes/first-sandboxed-command/verification.md`.

### Key Discoveries:

- `challenges/sandbox.py:155-218`: `run_command` never raises after the container starts. The only exceptions the game must handle are `ValueError` (length) and `SandboxUnavailable`.
- `challenges/sandbox.py:228-245`: `reap_stale` treats `created`/`exited`/`dead` as stale at any age. That is the race behind carry-over (a).
- `challenges/sandbox.py:76-85`: `_get_client()` is a lock-guarded lazy singleton (`docker.from_env()`). `from_env` accepts `max_pool_size` (docker-py `client.py:98`).
- `challenges/management/commands/verify_challenges.py:207`: the harness calls `reap_stale()` when nothing is in flight. It must keep being able to reap everything (minimum age 0).
- `challenges/tests/test_sandbox.py:149` (`test_missing_image_raises_sandbox_unavailable`) and `:203` (`test_client_is_created_lazily_and_cached`) depend on the image check and client construction. The implementer must update them together with (b)/(c).
- Django 6.1's SQLite backend takes `OPTIONS = {"transaction_mode": "IMMEDIATE", "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL", "timeout": 20}` (`django/db/backends/sqlite3/base.py:181-214`).
- `verification.md` (F-01): ~0.15 s per typical command and ~0.3 s at 8 concurrent. The concurrency cap default of 8 is inside the measured envelope.

## What We're NOT Doing

- **5-minute limit, countdown and "commands after time don't count".** That is S-02. S-01 records `started_at` so S-02 can enforce it server-side.
- **Summary with rank and 6-digit code.** That is S-03. S-01's "finished" page is a minimal placeholder.
- **QR token gate (S-06), staff lookup (S-04), Hall of fame (S-05).** A read-only admin registration of `GameSession` is added only for debugging during the event.
- **Soft block on a second game from the same browser (FR-016, parked).** S-01 only redirects an existing session to its game, which follows naturally from reload-safety. There is no "play again" button.
- **Production WSGI server, reverse proxy, deploy (F-02).** S-01 documents the concurrency contract F-02 must respect.
- **Hints, solutions, links to answers (PRD Non-Goals).** Also no Markdown library: descriptions are rendered as escaped text with a tiny backtick filter.
- **Anti-cheat.** Printing the expected answer is accepted where the verifier accepts it (PRD Business Logic).
- **i18n.** UI strings are English, hard-coded in templates.

## Implementation Approach

Build bottom-up in four phases, each independently testable:

1. **Harden the runner for the game** (carry-overs a–d) and make SQLite safe for concurrent writers. Everything stays inside the `challenges` app and settings.
2. **Game domain** in a new `game` app: models plus a service module that owns every rule (start, submit, count, advance, finish, concurrency limiting). Views stay thin, and all logic is unit-testable with a mocked `run_command`.
3. **Player UI**: server-rendered Django templates, plus one small vanilla-JS file that posts commands to a JSON endpoint. The page renders fully from the DB on load, so a reload is always correct.
4. **Measure**: a `bench_game` management command drives the real service with N concurrent simulated players against the real sandbox. The results go into `verification.md`, and the manual mobile check happens here.

Decisions taken in this planning session (unattended run: planner defaults, each the recommended option, all open to the user overturning them; see `plan-brief.md`). The user has since **confirmed** two of them: the English UI, and "What counts as an attempt" (our-side failures are not counted; timeouts and wrong answers are).

| Area | Decision |
| --- | --- |
| App layout | New Django app `game`; `challenges` stays the sandbox/catalog infrastructure layer |
| Player identity | `game_id` (UUID) stored in the Django session (DB-backed cookie session); no accounts |
| Progress pointer | `GameSession.current_slug` (not an index), resolved against `main_set()` so a mid-event cut cannot shift players onto the wrong challenge |
| Attempt log | One `Attempt` row per run (command, correct, error, timed_out, duration); `GameSession` holds denormalised counters |
| What counts as an attempt | Every run that reached a verdict, including timeouts and player errors. Not counted: over-length (400), sandbox unavailable (503), busy (503), `error_internal` (shown as "internal error, try again", logged) |
| Double submit | Conditional `UPDATE … WHERE current_slug = <slug>` so a correct answer advances exactly once; counters use `F()` increments; the UI disables submit while a request is in flight |
| Concurrency | Per-process `BoundedSemaphore(SANDBOX_MAX_CONCURRENT)`, default 8 (env `BASHDASH_SANDBOX_CONCURRENCY`). Waits up to `SANDBOX_QUEUE_TIMEOUT_S` = 10 s, then "busy". Docker pool size = cap + 2 |
| Reaping (a) | `reap_stale` gains a minimum age: the game reaps only containers older than 30 s, which makes it safe from any worker. It runs lazily once per process, before the first run. The harness keeps min age 0 |
| UI transport | JSON endpoint + vanilla JS `fetch`, CSRF via cookie header; no framework, no build step |
| UI language | English (the challenge texts are English) |

## Critical Implementation Details

**State sequencing / transactions.** Never hold a DB transaction open while `run_command` runs (0.15–6 s). With `transaction_mode=IMMEDIATE` that would lock out every other writer. The sequence per submit is:

1. A short read.
2. Sandbox run, with no transaction open.
3. One short `transaction.atomic()` that inserts the `Attempt` and applies the conditional counter/advance `UPDATE`.

`ATOMIC_REQUESTS` must stay `False`.

**Concurrency contract for F-02.** The semaphore and the docker client are per process. Total sandbox concurrency = number of worker processes × `SANDBOX_MAX_CONCURRENT`. The WSGI server needs at least `SANDBOX_MAX_CONCURRENT` + a few threads per process, so page loads are not starved by requests waiting on the semaphore. F-02 should run one process with threads (e.g. gunicorn `--workers 1 --threads 16`). If it uses more processes, it must scale the cap down. Record this in `verification.md`.

**Timeout arithmetic.** The worst-case request time is queue wait (10 s) + host timeout (6 s) + overhead. That is ~17 s, under common proxy defaults (60 s). The JS must not abort the fetch before ~25 s.

---

## Phase 1: Runner and database readiness (carry-overs a–d)

### Overview

Make `challenges.sandbox` and `challenges.catalog` safe and efficient for many concurrent game requests, and make SQLite tolerate concurrent writers. No player-visible change.

### Changes Required:

#### 1. Age-guarded reaping (carry-over a)

**File**: `challenges/sandbox.py`

**Intent**: Stop `reap_stale` from deleting a container that another worker is still reading. Only containers older than a minimum age become eligible, so calling it from any process at any time is safe. Add a once-per-process trigger the game can call before its first run.

**Contract**:
- `reap_stale(max_age_s: float = 60, *, min_age_s: float = 0, client=None) -> int`: a container is removed only if `age >= min_age_s` AND (`status in {created, exited, dead}` OR `age > max_age_s`). The default `min_age_s=0` keeps the harness behaviour unchanged.
- New constant `GAME_REAP_MIN_AGE_S = 30`, comfortably above `HOST_TIMEOUT_S` + the log/reload/remove tail.
- New `reap_stale_once() -> None`:
  - It is guarded by a module flag + lock and calls `reap_stale(min_age_s=GAME_REAP_MIN_AGE_S)` the first time in a process.
  - It swallows and logs `DockerException`, and leaves the flag unset on failure so the next call retries.
  - It is not called from `AppConfig.ready()`, because `ready()` also runs for `migrate`/`test` and must not touch Docker.

#### 2. Connection pool sized to concurrency (carry-over b)

**File**: `challenges/sandbox.py`, `config/settings.py`

**Intent**: Build the shared client with a pool large enough for the configured concurrency, so concurrent runs never queue on docker-py's pool.

**Contract**:
- `settings.SANDBOX_MAX_CONCURRENT = int(os.environ.get('BASHDASH_SANDBOX_CONCURRENCY', 8))`.
- `settings.SANDBOX_QUEUE_TIMEOUT_S = 10`.
- `settings.ALLOWED_HOSTS = [h for h in os.environ.get('BASHDASH_ALLOWED_HOSTS', '').split(',') if h]`. The empty default keeps today's behaviour (`[]`: with `DEBUG=True`, Django still allows localhost). Phase 4's LAN phone check sets it to the dev host's LAN IP. F-02 sets the real hostname.
- `_get_client()` calls `docker.from_env(max_pool_size=settings.SANDBOX_MAX_CONCURRENT + 2)`. The +2 leaves headroom for `reap_stale` and `bench_game`'s own calls.
- Update `test_client_is_created_lazily_and_cached` to assert the kwarg.

#### 3. Cached image check (carry-over c)

**File**: `challenges/sandbox.py`

**Intent**: Skip `images.get` after the first success, because the image only changes on deploy. Keep the clear `SandboxUnavailable` message when the image is missing.

**Contract**:
- A positive image check is cached per (client object, image name) behind the existing lock.
- If `containers.create` then raises `docker.errors.ImageNotFound`, the cache entry is dropped and `SandboxUnavailable` is raised as today.
- `clear_image_cache()` is exposed for tests.
- Existing test `test_missing_image_raises_sandbox_unavailable` still passes.
- New tests:
  - Two runs on the same fake client → `FakeImages.requested` has length 1.
  - An `ImageNotFound` from create invalidates the cache.

#### 4. Playable-only catalog lookups (carry-over d)

**File**: `challenges/catalog.py`

**Intent**: Give the game lookups that can only ever return playable challenges. `get()` stays for the harness, which needs excluded ones.

**Contract**:
- `playable(slug) -> Challenge | None`: from `main_set()` only.
- `first_playable() -> Challenge | None`.
- `next_playable(slug) -> Challenge | None`: the next playable challenge after `slug` in `all_main_set()` order. It works even if `slug` itself was cut, and returns `None` at the end.
- `get()` gets a docstring warning: "harness only; includes excluded challenges".
- Tests use `override_settings(CHALLENGES_EXCLUDED=<tmp file>)` + `clear_cache()` to show that an excluded slug is never returned and that `next_playable` skips it.

#### 5. SQLite for concurrent writers

**File**: `config/settings.py`

**Intent**: Avoid "database is locked" when several game requests write at once.

**Contract**: `DATABASES['default']['OPTIONS'] = {'transaction_mode': 'IMMEDIATE', 'timeout': 20, 'init_command': 'PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL'}`. `ATOMIC_REQUESTS` stays unset (False). `.gitignore` lists only `db.sqlite3` and `db.sqlite3-journal`, so add `db.sqlite3-wal` and `db.sqlite3-shm`. Note for F-02: the backup must use `sqlite3 .backup` (not `cp`) with WAL.

### Success Criteria:

#### Automated Verification:

- All tests pass: `uv run python manage.py test challenges`
- Django checks pass: `uv run python manage.py check`
- New unit tests exist and pass for: `reap_stale` min-age guard, `reap_stale_once` runs once and retries after a Docker error, `max_pool_size` passed, image-check caching and invalidation, `playable`/`next_playable` never returning an excluded slug
- The harness is unchanged in behaviour: `uv run python manage.py verify_challenges --only hello_world --skip-abuse` exits 0 and `docker ps -aq --filter label=bash-dash.sandbox` is empty afterwards
- WAL is active: `uv run python manage.py shell -c "from django.db import connection; c=connection.cursor(); c.execute('PRAGMA journal_mode'); print(c.fetchone())"` prints `('wal',)`

#### Manual Verification:

- Review the `reap_stale` diff: a container younger than `min_age_s` is never removed, whatever its status

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Game domain (models + service)

### Overview

New `game` app holding the game state and every gameplay rule, independent of HTTP.

### Changes Required:

#### 1. App and models

**File**: `game/apps.py`, `game/models.py`, `game/migrations/0001_initial.py`, `config/settings.py` (`INSTALLED_APPS += ['game']`)

**Intent**: Persist one game per player and one row per command run. The session row carries the denormalised counters S-02/S-03 need (time limit, ranking).

**Contract**:
- `GameSession`:
  - `id`: UUID pk, default uuid4.
  - `nick`: CharField max 20.
  - `started_at`: DateTimeField, `auto_now_add`, indexed.
  - `current_slug`: CharField max 64, nullable. `None` means finished.
  - `attempts`: PositiveIntegerField, default 0.
  - `solved`: PositiveIntegerField, default 0.
  - `last_solved_at`: DateTimeField, null.
  - `finished_at`: DateTimeField, null.
  - Property `is_finished` (`finished_at is not None`).
- `Attempt`:
  - `game`: FK GameSession, CASCADE, related_name `attempt_set`.
  - `slug`: CharField 64.
  - `command`: TextField.
  - `correct`: bool.
  - `output`: TextField.
  - `error`: CharField 255, blank.
  - `timed_out`: bool.
  - `duration_ms`: PositiveIntegerField.
  - `created_at`: auto_now_add.
  - Meta ordering `['created_at']`, index on `(game, created_at)`.
- `error_internal` runs are *not* stored as `Attempt`s. They are logged via `logging.getLogger('game')`.

#### 2. Service module

**File**: `game/services.py`

**Intent**: The only place that knows the rules: how a game starts, what a command does to it, and how sandbox concurrency is limited. Views and `bench_game` call it.

**Contract**:
- `start_game(nick: str) -> GameSession`:
  - Strips the nick and validates 1–20 chars (else raises `ValueError`).
  - Sets `current_slug = catalog.first_playable().slug`.
  - Raises `RuntimeError` if the catalog is empty.
- `current_challenge(game) -> Challenge | None`:
  - Returns `catalog.playable(game.current_slug)`.
  - If the slug was cut mid-game, it resolves to `catalog.next_playable(game.current_slug)` and persists that.
  - If no playable challenge follows (the cut slug was the last one), it persists `current_slug=None` **and** `finished_at=now` in the same `filter(pk=…, current_slug=<old>).update(…)`, without incrementing `solved`. This keeps `is_finished` and `current_slug is None` in agreement, so views never see an "active" game with no challenge.
  - `None` means finished.
- `submit_command(game_id, command: str) -> SubmitOutcome`, with `SubmitOutcome(status, result: SandboxResult | None, game: GameSession)`. `status` values:
  - `'ran'`: counted.
  - `'finished'`: game already over, not counted.
  - `'too_long'`: over 300 chars, not counted.
  - `'empty'`: blank command, not counted.
  - `'unavailable'`: `SandboxUnavailable`, not counted.
  - `'busy'`: the semaphore could not be acquired within `SANDBOX_QUEUE_TIMEOUT_S`, not counted.
  - `'internal'`: `result.error_internal` set, not counted, logged with slug + command.
- Order inside `submit_command`:
  1. Load the game and its challenge. Then run the cheap rejections before touching Docker or the semaphore, in this order: `finished` (game over or no current challenge), `empty` (`not command.strip()`), `too_long` (`len(command) > sandbox.MAX_COMMAND_CHARS`). The `ValueError` from `run_command` stays as a backstop only.
  2. `sandbox.reap_stale_once()`.
  3. Acquire the semaphore with `timeout=settings.SANDBOX_QUEUE_TIMEOUT_S`. On failure, return `busy`.
  4. `sandbox.run_command(challenge, command)` inside `try: … finally: semaphore.release()`, so a `SandboxUnavailable` (or any unexpected exception) never leaks a slot. `SandboxUnavailable` maps to `unavailable`.
  5. (Released in the `finally` above.)
  - The semaphore is created lazily by `_get_semaphore()`, a lock-guarded module singleton sized from `settings.SANDBOX_MAX_CONCURRENT` on first use. `_reset_semaphore()` is exposed for tests, so a test can `override_settings(SANDBOX_MAX_CONCURRENT=1, SANDBOX_QUEUE_TIMEOUT_S=0.01)`, reset the semaphore, hold the one slot, and assert `busy`.
  6. In one short `transaction.atomic()`:
     - Insert the `Attempt`.
     - `GameSession.objects.filter(pk=…, finished_at__isnull=True).update(attempts=F('attempts')+1)`.
     - If correct: `filter(pk=…, current_slug=<slug run>).update(solved=F('solved')+1, last_solved_at=now, current_slug=<next or None>, finished_at=<now if next is None else None>)`. The `current_slug` guard makes a duplicate correct submit advance once.
  7. Refresh and return.
- `last_attempt(game) -> Attempt | None`, for rendering after a reload.
- Commands are passed to the sandbox verbatim; no stripping beyond the emptiness check.

**Why the semaphore lives here, not in `run_command`**: the harness deliberately runs its own parallelism (`--parallel 8`) and must not be throttled by game settings.

### Success Criteria:

#### Automated Verification:

- Migration applies cleanly: `uv run python manage.py migrate`
- No missing migrations: `uv run python manage.py makemigrations --check --dry-run`
- Game unit tests pass: `uv run python manage.py test game` (with `sandbox.run_command` patched to return canned `SandboxResult`s). They cover:
  - start with a valid nick; empty and 21-char nicks rejected
  - an incorrect command increments attempts and stays on the challenge
  - a correct command increments attempts and solved, sets `last_solved_at` and advances
  - solving the last playable challenge sets `finished_at` and `current_slug=None`
  - a submit on a finished game returns `finished` and is not counted
  - `too_long`/`empty`/`unavailable`/`internal` are not counted, and `internal` creates no Attempt
  - a timed-out run is counted
  - busy: semaphore exhausted with a tiny timeout → `busy`, not counted
  - a duplicate correct submit for the same slug advances exactly once
  - a slug cut mid-game resolves to the next playable one; a cut last slug finishes the game (`finished_at` set, `solved` unchanged)
  - the semaphore slot is released when `run_command` raises `SandboxUnavailable`
- Full suite still passes: `uv run python manage.py test`

#### Manual Verification:

- `uv run python manage.py shell` → `start_game('me')` + `submit_command(g.id, 'echo "hello world"')` against the real sandbox returns `ran`, correct, and `g.current_slug == 'current_working_directory'`

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Player UI

### Overview

Mobile-first pages for rules + nick, play and finished, backed by the Phase 2 service.

### Changes Required:

#### 1. URLs and views

**File**: `game/urls.py`, `game/views.py`, `config/urls.py` (`path('', include('game.urls'))`)

**Intent**: Thin views that map HTTP to the service. The game is found via `request.session['game_id']`.

**Contract**:
- `GET /` (`game:home`):
  - Active game in session → redirect to `game:play`.
  - Finished game → redirect to `game:done`.
  - Otherwise render the rules + nick form.
- `POST /start` (`game:start`):
  - Validates the nick and calls `start_game`.
  - Stores `game_id` in the session and redirects to `game:play`.
  - An invalid nick re-renders home with an error.
  - If the session already has a game, redirect as in `/` (no second game).
- `GET /play` (`game:play`):
  - No game → redirect home. Finished → redirect `game:done`.
  - Otherwise render the current challenge: index "N / total", title, description, attempts, solved, and the last attempt's command/output/verdict.
- `POST /play/command` (`game:command`): JSON body `{"command": "..."}`, returns JSON. The response always carries `status`, `attempts`, `solved`, `finished`, and `challenge` (`{index, total, title, description_html}` for the *current* challenge after the submit) so the JS can advance without reload. It adds `result` (`{correct, output, message}`) when status is `ran`. Status mapping:

  | `status` | HTTP |
  | --- | --- |
  | `ran` | 200 |
  | `finished` | 409 |
  | `too_long` / `empty` | 400 |
  | `unavailable` / `busy` | 503 |
  | `internal` | 500 |

  `message` is the player-facing text: "Correct!", `result.error`, "Timed out (5 s limit)", or a fixed message per non-`ran` status. `message` is never `error_internal`. No game → 403.
- `GET /done` (`game:done`): minimal finished page with nick, solved of total, and attempts. No game → redirect home.
- CSRF: standard `CsrfViewMiddleware`. The JS reads the `csrftoken` cookie and sends `X-CSRFToken`.

#### 2. Templates, static and description filter

**File**: `game/templates/game/base.html`, `home.html`, `play.html`, `done.html`, `game/static/game/play.js`, `game/static/game/game.css`, `game/templatetags/game_text.py`

**Intent**: A readable, phone-first terminal feel with no external dependencies, and no links anywhere that lead to answers (PRD Non-Goals).

**Contract**:
- `base.html`: viewport meta, one CSS file, no external fonts or CDNs.
- `home.html`: rules text (challenges in order, no skipping, every command is an attempt incl. `ls`/`cat`, fewer attempts is better, 5 minutes). Nick input `maxlength=20 required`, "Start" button.
- `play.html`:
  - Challenge header, description, and a single-line command `<input>` with `maxlength=300`, `autocapitalize=off`, `autocorrect=off`, `autocomplete=off`, `spellcheck=false` and `enterkeyhint=send`.
  - Submit button, attempts/solved counters.
  - Output `<pre>` (escaped, max-height with scroll) and a verdict line.
  - Server-rendered from DB state so a reload restores everything.
- `play.js`:
  - On submit, disable the input and button and show "Running…".
  - `fetch` POST with a 25 s `AbortController` timeout.
  - Render the output (`textContent` only, never `innerHTML` for output) and the verdict.
  - Update the counters. If the challenge changed, swap in the new header/description (`description_html` is server-escaped) and clear the input.
  - If `finished`, navigate to `/done`.
  - Re-enable and refocus the input.
  - On network error, abort, 503 or 500 (`internal`), show the message and keep the command in the input for a retry. None of these counted as an attempt.
- `game_text.render_description` filter:
  - HTML-escape first.
  - Then convert ``` fenced blocks to `<pre>` and `` `x` `` to `<code>x</code>`, and turn remaining newlines into `<br>`.
  - Return `mark_safe`.
  - Used by both `play.html` and the JSON `description_html`.

#### 3. Read-only admin

**File**: `game/admin.py`

**Intent**: Let the operator inspect games during the event. S-04 builds the real staff tooling.

**Contract**:
- `GameSession`: list_display `nick, started_at, solved, attempts, finished_at`, read-only, with an `Attempt` inline, also read-only.
- No add/change/delete permissions.

### Success Criteria:

#### Automated Verification:

- View tests pass: `uv run python manage.py test game` (Django test `Client`, `run_command` patched). They cover:
  - home renders the rules and the form
  - start with a valid nick sets the session and redirects to play; an invalid nick shows an error
  - play shows challenge 1 of `len(main_set())`
  - a command POST returns the JSON contract for each status (200/400/403/409/500/503)
  - a correct answer returns the next challenge
  - play after a reload shows the last attempt's output
  - finishing redirects play → done
  - `/` with an active game redirects to play
  - a POST without a CSRF token is rejected (`Client(enforce_csrf_checks=True)`)
- The description filter escapes HTML (`<script>` in input comes out escaped) and renders backticks/fences
- No answer links: a test asserts the rendered home/play/done pages contain no `<a href` to external hosts
- Full suite passes: `uv run python manage.py test`
- Checks pass: `uv run python manage.py check`

#### Manual Verification:

- With `runserver` and the real sandbox, play through the first 5 challenges in a desktop browser at phone width (DevTools device mode). Check that the output and verdict appear, a wrong answer stays, a right answer advances, and the attempts counter increments on every run
- Reload mid-game: same challenge, same counters, last output visible
- Try `:(){ :|:& };:` and `sleep 60`. Each returns within ~6 s as "Timed out" and counts as an attempt. The page stays usable
- Output of `seq 1 100000` scrolls inside the output box without breaking the layout
- Stop Docker (or set `BASHDASH_SANDBOX_IMAGE` to a missing tag): submitting shows "sandbox unavailable, try again", the attempt is not counted, and the command stays in the input

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 4: Concurrency measurement and mobile check

### Overview

Answer the roadmap unknown ("~1 s at ~15 concurrent players?") with numbers from the real stack, and do the one real-phone check that the dev host allows.

### Changes Required:

#### 1. Benchmark command

**File**: `game/management/commands/bench_game.py`

**Intent**: Simulate N players, each in its own thread, starting a game and submitting commands in a loop through `game.services`. That exercises the semaphore, the docker pool, SQLite writes and the sandbox together. Report latency and any non-`ran` statuses.

**Contract**:
- Options:
  - `--players` (default 15).
  - `--commands` per player (default 10).
  - `--mix`: `typical` = a mix of correct examples and wrong answers; `with-abuse` = one player sends `sleep 60` repeatedly.
- Output: p50/p95/max of submit wall time, the count per status, and the number of `database is locked` errors (must be 0).
- It creates games with nick prefix `bench-` and deletes them (cascade) at the end unless `--keep`.
- Exit 1 if:
  - any `internal` or `unavailable` status appears,
  - any lock error occurs, or
  - labelled containers remain afterwards.

#### 2. Verification record

**File**: `context/changes/first-sandboxed-command/verification.md`

**Intent**: Record the measured latency and the concurrency contract for F-02.

**Contract**:
- Host details.
- `bench_game` results for `--players 15` (typical and with-abuse) and `--players 30` (typical), all at the default cap of 8.
  - These runs are necessarily unpinned. `bench_game` drives `game.services`, which never passes `host_overrides`, so `--host-cpus` pinning does not apply.
  - The event-VM re-run in F-02 provides the real-CPU numbers.
- A verdict on the "~1 s" unknown.
- The F-02 contract: processes × cap, thread count, WAL-safe backup. It also records that `verify_challenges` reaps with `min_age_s=0`, so it must not run on the event host while games are live, because it would delete in-flight game containers.
- A note to re-run on the event VM.

### Success Criteria:

#### Automated Verification:

- `uv run python manage.py bench_game --players 15` exits 0
- `uv run python manage.py bench_game --players 15 --mix with-abuse` exits 0
- Full suite passes: `uv run python manage.py test`
- No leaked containers: `docker ps -aq --filter label=bash-dash.sandbox` is empty

#### Manual Verification:

- `verification.md` records p50/p95 for 15 players. Typical p95 ≤ ~1 s, or the gap is explained and accepted against the PRD's "~1 s accepted" NFR
- Play on a real phone (Android Chrome and/or iOS Safari) over LAN (`BASHDASH_ALLOWED_HOSTS=<lan-ip> uv run python manage.py runserver 0.0.0.0:8000`). The keyboard does not autocapitalize or autocorrect, "send" submits, and the output is readable. Testing over mobile data is F-02's job
- The F-02 concurrency contract is written down in `verification.md`

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- `challenges/tests/test_sandbox.py`: reap min-age guard, `reap_stale_once`, pool size, image-check cache and invalidation.
- `challenges/tests/test_catalog.py`: `playable`, `first_playable`, `next_playable` with an exclusion file.
- `game/tests/test_services.py`: every `submit_command` status, counting rules, advance-once, finish, cut-mid-game, busy semaphore.
- `game/tests/test_views.py`: redirects, JSON contract per status, CSRF, reload restores the last attempt, no answer links, description filter escaping.

### Integration Tests:

- `game/tests/test_integration.py` (`skipUnless` Docker + image, same helper as `challenges/tests/test_sandbox_integration.py`): start a game, submit `hello_world`'s example → correct and advanced; submit a wrong command → incorrect, counted; no leaked containers.
- `bench_game` is the load-level integration check (Phase 4).

### Manual Testing Steps:

1. `uv run python manage.py migrate && uv run python manage.py runserver`, then open `/` in phone-width DevTools.
2. Enter a nick, Start, and solve `hello_world` with `echo hello world`. It advances, and the attempts counter reads 1.
3. Send `ls` on challenge 2. It counts, and you stay on challenge 2.
4. Reload. Same challenge, the counters match, and the last output is shown.
5. Send a fork bomb. It times out in ≤ ~6 s, is counted, and the next command works.
6. Open `/admin/`: the game and its attempts are visible read-only.

## Performance Considerations

- The expected per-command cost is ~0.15 s (F-01), plus a few ms of SQLite writes. Removing `images.get` saves one round trip per command.
- The semaphore bounds host load. With cap 8 and 0.5 CPU per container, the worst case is 4 CPUs of player load. Fork-bomb/CPU abuse holds a slot for ~5.2 s, so 8 simultaneous abusers would push others into the 10 s queue. The PRD accepts this (no performance guarantee under crowding), and `bench_game --mix with-abuse` measures one abuser's effect.
- WAL + IMMEDIATE + a 20 s busy timeout, with no transaction spanning the sandbox run, keeps SQLite writes serialised but short.

## Migration Notes

- First app with models: `game/migrations/0001_initial.py`. There is no existing data.
- Enabling WAL creates `db.sqlite3-wal`/`-shm` next to the DB. F-02's off-VM backup must use SQLite's online backup (`sqlite3 db.sqlite3 ".backup …"`), not a file copy.

## References

- Roadmap entry and carry-overs: `context/foundation/roadmap.md` (S-01)
- F-01 plan, review and verification: `context/archive/2026-09-29-sandbox-image-and-task-cut/` (`plan.md`, `reviews/impl-review.md` F9, `verification.md`)
- Runner: `challenges/sandbox.py:155-245`; catalog: `challenges/catalog.py:68-88`; test fakes: `challenges/tests/fakes.py`
- PRD: `context/foundation/prd.md` (US-01, FR-002–FR-005, NFRs, Business Logic, Non-Goals)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Runner and database readiness (carry-overs a–d)

#### Automated

- [ ] 1.1 All tests pass: `uv run python manage.py test challenges`
- [ ] 1.2 Django checks pass: `uv run python manage.py check`
- [ ] 1.3 New unit tests for reap min-age, reap_stale_once, pool size, image-check cache, playable lookups pass
- [ ] 1.4 Harness unchanged: `verify_challenges --only hello_world --skip-abuse` exits 0, no leaked containers
- [ ] 1.5 WAL is active (`PRAGMA journal_mode` returns `wal`)

#### Manual

- [ ] 1.6 Review `reap_stale` diff: containers younger than `min_age_s` never removed

### Phase 2: Game domain (models + service)

#### Automated

- [ ] 2.1 Migration applies cleanly: `uv run python manage.py migrate`
- [ ] 2.2 No missing migrations: `makemigrations --check --dry-run`
- [ ] 2.3 Game service unit tests pass: `uv run python manage.py test game`
- [ ] 2.4 Full suite passes: `uv run python manage.py test`

#### Manual

- [ ] 2.5 Shell: `start_game` + `submit_command` with the hello_world answer against the real sandbox advances to `current_working_directory`

### Phase 3: Player UI

#### Automated

- [ ] 3.1 View tests pass (redirects, JSON contract per status, CSRF, reload restores last attempt)
- [ ] 3.2 Description filter escapes HTML and renders backticks/fences
- [ ] 3.3 No answer links in rendered pages
- [ ] 3.4 Full suite passes: `uv run python manage.py test`
- [ ] 3.5 Checks pass: `uv run python manage.py check`

#### Manual

- [ ] 3.6 Play first 5 challenges at phone width: output, verdict, advance and attempts counter behave
- [ ] 3.7 Reload mid-game restores challenge, counters and last output
- [ ] 3.8 Fork bomb and `sleep 60` return within ~6 s as timed out and are counted
- [ ] 3.9 Large output scrolls inside the output box
- [ ] 3.10 Sandbox unavailable shows retry message, attempt not counted, command kept

### Phase 4: Concurrency measurement and mobile check

#### Automated

- [ ] 4.1 `bench_game --players 15` exits 0
- [ ] 4.2 `bench_game --players 15 --mix with-abuse` exits 0
- [ ] 4.3 Full suite passes: `uv run python manage.py test`
- [ ] 4.4 No leaked containers after bench runs

#### Manual

- [ ] 4.5 `verification.md` records 15-player p50/p95 with a verdict on the ~1 s unknown
- [ ] 4.6 Real phone over LAN: keyboard settings, send-to-submit, readable output
- [ ] 4.7 F-02 concurrency contract written down in `verification.md`
