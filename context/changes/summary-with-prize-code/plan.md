# Summary with Prize Code Implementation Plan

## Overview

Replace the placeholder `/done` page with the real end-of-game summary (FR-008). It shows the number of challenges solved, the number of attempts, the player's current place in the ranking, and a unique 6-digit prize code. This slice also adds the ranking rule from the PRD Business Logic. S-04 (staff lookup by code) and S-05 (Hall of fame) reuse that rule, so it must live in exactly one place.

## Current State Analysis

- `GameSession` (`game/models.py:7-36`) already holds the ranking inputs as denormalised counters: `solved`, `attempts`, `started_at`, `last_solved_at` and `finished_at`. It has no prize code.
- The counters are trustworthy for ranking:
  - The guarded update runs first and gates the `Attempt` insert, so rows and counter agree (`game/services.py:164-195`; S-01 impl-review F2).
  - `last_solved_at` and `finished_at` are capped at `deadline_at` (`Least(now, F('deadline_at'))`, `services.py:188`), so tie-break times never exceed the limit.
- `solved > 0` ⇔ `last_solved_at IS NOT NULL`. `last_solved_at` is set only by the solve update, and a cut-finish never sets it (`services.py:117-118`).
- Every game is created through `services.start_game` (`services.py:72-83`). The callers are the view, `bench_game` and tests. There are no other `GameSession.objects.create` sites.
- Abandoned games stay unfinished until something reads them. `services.expire_overdue()` with no argument finishes every overdue game in bulk (`services.py:85-91`). The S-02 plan-brief states that S-03 must call it before ranking.
- `done` (`game/views.py:175-188`) renders `game/done.html`. The page has a heading (time up / all solved / finished), the nick, `solved / total` and attempts. It redirects to `/play` for an unfinished game and to `/` when the session has no game.
- `GameSessionAdmin` (`game/admin.py:26-30`) is read-only, with `search_fields = ('nick',)`.
- The dev `db.sqlite3` is behind (0002 is not applied). Migrations must backfill existing rows, as 0002 does.
- Baseline: `uv run python manage.py test game challenges` → 135 tests, OK.

## Desired End State

- Every game gets a unique 6-digit code (`000000`–`999999`, leading zeros kept) when it starts. A unique DB constraint guarantees uniqueness, and `start_game` retries on a collision.
- `/done` for a finished game shows:
  - the existing heading and nick;
  - Solved `X / total` and Attempts `N`;
  - Place `#R of M`, where M is the number of finished games;
  - the prize code, large and in monospace, with a line telling the player to show it at the booth.
- Place follows the PRD rule: solved ↓, then attempts ↑, then time from `started_at` to `last_solved_at` ↑. It uses competition ranking: players equal on all three keys share a place, and the next place is skipped (1, 2, 2, 4). Players with 0 solved have no solve time, so among them only attempts decide.
- Only finished games are ranked, and overdue games are finished (`expire_overdue()`) before ranking. Place is recomputed on every `/done` load, so it can move as others finish. The page says so.
- The code never appears on `/play`, in `/play/command` or `/play/state` JSON, or on `/`.
- Admin shows the code in the list and can search by it (a stopgap until S-04).

Verify: `uv run python manage.py test game challenges` is green. Then play two or three short games locally with `BASHDASH_GAME_DURATION_S=30` and check the places and codes on `/done` (see Manual Testing Steps).

### Key Discoveries:

- Ranking query verified on SQLite (throwaway in-memory DB): `ExpressionWrapper(F('last_solved_at') - F('started_at'), output_field=DurationField())` works in both `order_by` and `filter(elapsed__lt=...)`. A "count strictly better + 1" query gives correct competition ranks, including NULL-elapsed ties.
- `TIMED_OUT_Q` and `GameSession.timed_out` already exist for the heading. Don't derive "timed out" again (S-02 plan-review).
- Migration 0002 (`game/migrations/0002_gamesession_deadline_at.py`) is the house pattern for a non-null column on existing rows: add nullable → `RunPython` backfill → alter to non-null.

## What We're NOT Doing

- The staff lookup by code and "prize given" (S-04). The admin gets only a read-only code column and search.
- The Hall of fame, hiding nicks and disqualification (S-05). S-03 adds no `hidden` field. The ranking queryset is the single place where S-05 will add that filter.
- Freezing the place at finish time. The place is live.
- Showing the solve time on the summary. PRD: time is only a tie-break.
- Auto-refreshing `/done`, a "copy code" button, or a QR of the code.
- Making codes hard to guess or rate-limited. The PRD accepts that staff also ask for the nick (FR-011 note).
- Changing how games finish, how attempts are counted, or the time limit.
- JS changes. `/done` is a server-rendered page, and `play.js` already navigates there.
- Excluding test games from the ranking (review F3). Staff test games and `bench_game --keep` games count in every place and in the total M. Operational step: clear the database before the event.

## Implementation Approach

Two phases. Phase 1 adds the code: model field, migration with backfill, generation with a collision retry in `start_game`, and admin. It is invisible to players, but it is the part that must be airtight: the code is unique and every game has one. Phase 2 adds the ranking functions in `game/services.py` (the module that "knows the rules") and rebuilds the summary page on top of them.

The code is assigned at start rather than at finish. Games finish in four places: the bulk `expire_overdue` `UPDATE`, the solve update in `_record`, the cut path in `current_challenge`, and future staff tools. Assigning at finish would need code generation in each of them, and a bulk `UPDATE` cannot give each row a unique random value. An abandoned game uses up one of the 1,000,000 codes. At hackathon scale (hundreds of games) that is negligible.

## Critical Implementation Details

- **Collision retry needs a savepoint.** Wrap each `create` attempt in its own `transaction.atomic()`. Otherwise an `IntegrityError` breaks the enclosing transaction: the test-case transaction, or any caller's `atomic`. Retry a bounded number of times (e.g. 10), then raise `RuntimeError`. Catch only `IntegrityError`. `code` is the only unique column besides the UUID pk.
- **Don't add the field with a plain callable default in one step.** `AddField` evaluates a callable default once for all existing rows, which violates the unique constraint on a DB with more than one game. Follow 0002: add `null=True` (no unique), backfill each row with a distinct code in `RunPython`, then alter to non-null + `unique=True`. The final model field may keep `default=<generator>`, so direct `objects.create` in tests or future code still gets a code. `start_game` always passes one explicitly and handles the retry.
- **Rank a game only after the bulk expire.** Call `expire_overdue()` with no argument before counting. Otherwise overdue-but-unread games are missing from both the "better than" count and the total.

## Phase 1: Unique prize code per game

### Overview

Every `GameSession` has a unique 6-digit code from the moment it starts, including existing rows after migration.

### Changes Required:

#### 1. Model field

**File**: `game/models.py`

**Intent**: Store the prize code on the game. Staff identify a player by it (S-04), so it must be unique at the DB level, not just "probably unique".

**Contract**: `GameSession.code = CharField(max_length=6, unique=True, editable=False, default=<generator>)`. Code format: exactly 6 ASCII digits, zero-padded (`f'{secrets.randbelow(10**6):06d}'`). Put the generator in `game/models.py` (e.g. `generate_code()`) so both the migration and services can import it. Update the model docstring to mention the code. Include the code in `__str__` only if it helps admin readability (optional).

#### 2. Migration with backfill

**File**: `game/migrations/0003_gamesession_code.py`

**Intent**: Add the column to DBs that already have games, giving each existing row a distinct code.

**Contract**: The three-step pattern from 0002: `AddField(null=True)` with **no `default`** (a callable default there is evaluated once and written to every existing row, so a 0002-style `filter(code__isnull=True)` backfill would find nothing and the final unique `AlterField` would fail) → `RunPython(backfill, noop)` → `AlterField` to the final definition (unique, non-null). The backfill draws codes from the generator and skips any it has already used in this run (the set of existing codes is small). Reverse is `noop` plus the auto-reversed field ops.

#### 3. Generation with retry in `start_game`

**File**: `game/services.py`

**Intent**: Give every new game a code and never fail on a rare collision.

**Contract**: `start_game(nick)` keeps its signature and errors (`ValueError` for a bad nick, `RuntimeError` for no playable challenges). It generates a code, creates inside a per-attempt `transaction.atomic()`, and on `IntegrityError` retries with a new code, up to a module constant `CODE_ATTEMPTS = 10`. After that it raises `RuntimeError('could not allocate a unique prize code')`.

#### 4. Admin

**File**: `game/admin.py`

**Intent**: Staff can find a game by code before S-04 lands.

**Contract**: Add `code` to `GameSessionAdmin.list_display` and `search_fields`. The admin stays read-only.

#### 5. Tests

**File**: `game/tests/test_services.py` (plus a small migration test if practical)

**Intent**: Pin the uniqueness guarantee and the format.

**Contract**:
- `start_game` returns a game whose `code` matches `^\d{6}$`.
- Patch the generator where `start_game` looks it up (e.g. `game.services.generate_code` if services imports it by name). Patching `game.models.generate_code` does not affect a name imported into services.
- Patch the generator to return an existing game's code first, then a fresh one. `start_game` succeeds with the fresh code, and the test's outer transaction is still usable (a further query works).
- Patch the generator to always collide. `start_game` raises `RuntimeError` and creates no row.
- Two games never share a code (DB constraint: a direct `create` with a duplicate code raises `IntegrityError`).
- Leading zeros are preserved (generator patched to `'000042'` round-trips).

### Success Criteria:

#### Automated Verification:

- Game and challenge tests pass: `uv run python manage.py test game challenges`
- Django checks pass: `uv run python manage.py check`
- No missing migrations: `uv run python manage.py makemigrations --check --dry-run`
- Migration applies to the existing dev DB (with S-01 games, behind on 0002) and every row gets a distinct code: `uv run python manage.py migrate`, then `uv run python manage.py shell -c "from game.models import GameSession as G; n=G.objects.count(); assert n == G.objects.values('code').distinct().count() and not G.objects.filter(code__isnull=True).exists(), n"`

#### Manual Verification:

- In `/admin/game/gamesession/`, the code column shows 6-digit codes, and searching by a code finds the game.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Ranking and the summary page

### Overview

Add the ranking rule once in `game/services.py` and rebuild `/done` to show solved, attempts, place and code.

### Changes Required:

#### 1. Ranking functions

**File**: `game/services.py`

**Intent**: One definition of the PRD ranking rule that S-04 (place on lookup) and S-05 (top N) can reuse. Only finished games are ranked, and overdue ones are finished first.

**Contract**:
- `ranked_games() -> QuerySet[GameSession]`:
  - calls `expire_overdue()` (bulk);
  - returns finished games annotated with `elapsed = last_solved_at - started_at` (a `DurationField` expression; NULL when nothing is solved);
  - ordered by `-solved, attempts, elapsed, started_at`. The final `started_at` only makes list order deterministic; it does not affect place.
  - The docstring states that this is the single place S-05 adds its "hidden" filter.
- `rank_of(game) -> tuple[int, int] | None`:
  - returns `(place, total)` among `ranked_games()`, or `None` if the game is not finished;
  - `place = 1 + count of ranked games strictly better`. Strictly better means: more solved; or equal solved and fewer attempts; or equal solved and attempts and a smaller `elapsed` (only when the game's own `elapsed` is not NULL);
  - `total = ranked_games().count()`.
  - Call `ranked_games()` once per `rank_of` and reuse that queryset for both counts, so each call runs one bulk `UPDATE` (as Performance Considerations assumes).
  - Read the game's own `elapsed` from the annotated queryset (or compute it in Python from the refreshed row) so both sides use the same expression.

#### 2. `done` view

**File**: `game/views.py`

**Intent**: Pass the summary data to the template. The existing redirects and heading logic stay as they are.

**Contract**: The `done` context gains `place` and `ranked_total` (from `services.rank_of(game)`) and the code (via `game.code`). Existing keys stay: `game`, `total`, `timed_out`, `all_solved`. `_session_game` already expires this game. `rank_of` does the bulk expire for the rest.

#### 3. Summary template and styles

**Files**: `game/templates/game/done.html`, `game/static/game/game.css`

**Intent**: A phone-first summary a player can show at the booth. The code is the most prominent element.

**Contract**:
- `done.html`, in this order:
  - the existing heading and "Well played, nick";
  - a stats block: Solved `X / total`, Attempts `N`, Place `#R of M`;
  - a prize block: the code in a large monospace element (e.g. `<p class="prize-code">`), plus "Show this code at the booth to claim your prize." and "Take a screenshot so you don't lose it.";
  - a small muted note: "Your place can change as other players finish."
- CSS: a `.prize-code` style (large, letter-spaced, accent colour, centred, `user-select: all` so a tap selects it). It uses the existing `:root` tokens and must fit a 320 px wide screen without horizontal scroll.
- Copy stays in English, like the rest of the UI.

#### 4. Tests

**Files**: `game/tests/test_services.py`, `game/tests/test_views.py`

**Intent**: Pin the ranking rule and the page contract.

**Contract**:
- Services, `rank_of` / `ranked_games`:
  - Ordering: more solved beats fewer; for equal solved, fewer attempts wins; for equal both, shorter elapsed wins.
  - Exact ties share a place, and the next place is skipped (1, 2, 2, 4).
  - Two 0-solved games with equal attempts share a place. A 0-solved game ranks below any game with ≥1 solved.
  - Unfinished games are excluded from both place and total. `rank_of` returns `None` for an unfinished game.
  - An overdue unfinished game is expired by `ranked_games()` and counted.
  - A timed-out game and an all-solved game are both ranked.
- Views, `done`:
  - A finished game shows solved, attempts, `#place of total` and its 6-digit code.
  - The code is absent from `/play` HTML, the `/play/command` JSON and the `/play/state` JSON. Pin the code to a fixed value above 300000 (e.g. `'987654'`) first, so a random code can never match `remaining_ms` or other digits on the page by chance.
  - Existing redirects still hold (no game → `/`, active game → `/play`).
  - The `NoAnswerLinksTests` "no external links" check still passes for `/done`.

### Success Criteria:

#### Automated Verification:

- Game and challenge tests pass: `uv run python manage.py test game challenges`
- Django checks pass: `uv run python manage.py check`
- No missing migrations: `uv run python manage.py makemigrations --check --dry-run`

#### Manual Verification:

- At phone width (Chrome devtools, 360 px and 320 px), `/done` shows solved, attempts, place and a readable code without horizontal scroll.
- Play three short games in separate browsers or incognito windows with different results. Each `/done` shows the expected place, and reloading an earlier player's `/done` shows their place updated.
- A game abandoned mid-play (tab closed) and past its deadline counts in `M` the next time any `/done` loads.
- Reloading `/done` keeps showing the same code.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- Code format, collision retry (the outer transaction stays usable), retry exhaustion, and the DB uniqueness constraint.
- Ranking order across all three keys, competition-rank ties, NULL-elapsed (0-solved) ties, and exclusion of unfinished games plus the expire-before-rank behaviour.

### Integration Tests:

- View tests through the Django test client: start → finish (solve the last challenge with a patched `run_command`, or expire by moving `deadline_at`) → `/done` shows place and code.
- Negative: the code is not leaked on `/play` or in JSON endpoints.

### Manual Testing Steps:

1. `uv run python manage.py migrate` on the existing dev DB. Check that the admin shows codes for old games.
2. `BASHDASH_GAME_DURATION_S=30 uv run python manage.py runserver`. Open `/` at phone width, start a game, solve one challenge, and let time run out.
3. In an incognito window, start another game and solve nothing. It should rank below the first.
4. In a third window, solve one challenge with fewer attempts than the first player. It should rank above the first. Reload the first player's `/done` to see the place drop.
5. Search for one of the codes in the admin.

## Performance Considerations

Each `/done` load runs one bulk `UPDATE` (indexed on `deadline_at`, filtered on `finished_at IS NULL`) and two `COUNT` queries over finished games. At event scale (hundreds to low thousands of rows) this takes well under a millisecond on SQLite. `/done` is loaded once or twice per player. No caching is needed.

## Migration Notes

`0003_gamesession_code` backfills distinct codes for all existing rows, so it is safe on the dev DB and on any DB already deployed. Reversing drops the column.

## References

- Roadmap entry: `context/foundation/roadmap.md` (S-03); PRD FR-008, FR-011, and Business Logic in `context/foundation/prd.md`
- S-02 plan (`expire_overdue`, capped timestamps, `TIMED_OUT_Q`): `context/archive/2026-09-29-server-side-time-limit/plan.md`
- S-01 plan addenda and impl-review F2 (counter is the source of truth): `context/archive/2026-09-29-first-sandboxed-command/`
- Backfill migration pattern: `game/migrations/0002_gamesession_deadline_at.py`
- Game rules module: `game/services.py:72-91, 164-195`; summary view: `game/views.py:175-188`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Unique prize code per game

#### Automated

- [x] 1.1 Game and challenge tests pass: `uv run python manage.py test game challenges` — 318a63c
- [x] 1.2 Django checks pass: `uv run python manage.py check` — 318a63c
- [x] 1.3 No missing migrations: `uv run python manage.py makemigrations --check --dry-run` — 318a63c
- [x] 1.4 Migration applies to the existing dev DB and every row gets a distinct code — 318a63c

#### Manual

- [x] 1.5 Admin shows the code column and finds a game by code — 318a63c

### Phase 2: Ranking and the summary page

#### Automated

- [x] 2.1 Game and challenge tests pass: `uv run python manage.py test game challenges`
- [x] 2.2 Django checks pass: `uv run python manage.py check`
- [x] 2.3 No missing migrations: `uv run python manage.py makemigrations --check --dry-run`

#### Manual

- [ ] 2.4 `/done` at 360 px and 320 px shows solved, attempts, place and code without horizontal scroll
- [ ] 2.5 Three games in separate browsers rank as expected; reloading an earlier `/done` shows the updated place
- [x] 2.6 An abandoned overdue game is counted in the total on the next `/done` load
- [x] 2.7 Reloading `/done` keeps the same code
