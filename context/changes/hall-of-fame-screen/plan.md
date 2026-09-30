# Hall of Fame Screen with Nick Hiding Implementation Plan

## Overview

Booth staff open an auto-refreshing Hall of fame page on the screen at the booth. It shows the top N finished games (place, nick, solved, attempts) and next to them a list of the most recently finished games, so every player sees their result for a moment (FR-010). From a phone, staff can hide a game from the Hall of fame without deleting its result. Hiding works as disqualification: the game drops out of the ranking everywhere, and every other player's place and total are recomputed without it (FR-012). This slice also closes the S-03 carry-over: `/done` must not crash when `rank_of()` returns `None` for a hidden game.

## Current State Analysis

- The PRD ranking rule is defined in exactly one place: `services.ranked_games()` (`game/services.py:104-113`). It bulk-expires overdue games, keeps only finished games, annotates `elapsed = last_solved_at - started_at`, and orders by `-solved, attempts, elapsed, started_at`. Its docstring says: "S-05 adds its 'hidden' filter here."
- `services.rank_of(game)` (`game/services.py:116-125`) gives competition ranking (`1 + count(strictly better)`, where ties share a place) and returns `None` when the game is not in `ranked_games()`.
- `views.done` (`game/views.py:183`) does `place, ranked_total = services.rank_of(game)`. If `rank_of` returns `None`, that line raises a `TypeError` (HTTP 500). This is the S-03 impl-review F2 carry-over recorded on S-05 in the roadmap.
- The staff lookup (`game/staff_views.py:26-41`, `templates/game/staff/lookup.html`) already renders "not ranked" for a finished game with `rank=None`. It cannot tell "hidden" apart from other reasons.
- Staff pages use `staff_member_required` (it redirects to `admin:login`). Routes live under `staff` in the `game` namespace with no trailing slash (`game/urls.py`). Mutations use a POST form, `{% csrf_token %}`, `messages`, and Post/Redirect/Get (`staff_views.give_prize`).
- `GameSession` (`game/models.py`) has no hidden flag. `prize_given_at` set the precedent of a nullable timestamp that means "done, and when".
- The UI is server-rendered templates on `game/base.html` with a mobile-first stylesheet (`game/static/game/game.css`, `main { max-width: 44rem }`, colour tokens in `:root`). There is one JS file (`play.js`) and no build step. `tech-stack.md` says the leaderboard refreshes by polling, with no realtime layer.
- The admin (`game/admin.py`) is read-only and lists `prize_given_at` with an `EmptyFieldListFilter`.
- Settings follow the `BASHDASH_*` env var pattern (`config/settings.py:143-152`).
- Baseline: `uv run python manage.py test game challenges` → 170 tests, OK.

## Desired End State

- `GameSession.hidden_at` (nullable datetime) marks a game as hidden or disqualified. A hidden game:
  - is left out of `ranked_games()`, so it has no place, and it no longer counts in anyone's `M` or place (on `/done`, the staff lookup, and the Hall of fame);
  - never appears in the Hall of fame top N or in the recent list;
  - keeps its result, code and prize state untouched.
- `/staff/hall` (staff only) is a landscape big-screen page. On the left is "Hall of fame": top N rows showing place, nick, solved and attempts, with ties sharing a place. On the right is "Just finished": the last K finished, non-hidden games, each with nick, solved, attempts and current place. It shows no prize codes and no solve times. The board refreshes every few seconds with no page flash. If a refresh fails, it keeps the last good board and shows a small "reconnecting" badge. If the staff session has expired, it shows "Session expired — log in again".
- `/staff/moderate` (staff only, phone-sized) lists the same top N and recent games, each with a "Hide" button, plus a "Hidden" section that lists hidden games with an "Unhide" button. Hiding and unhiding are POST + CSRF + PRG, and each shows a flash message. The big screen reflects the change on its next refresh.
- A hidden player reloading `/done` still sees their summary and prize code. The Place line reads "not ranked" instead of raising a 500.
- The staff lookup shows "Hidden from Hall of fame (disqualified)" for hidden games instead of the ambiguous "not ranked". The prize button is still available, since prize policy stays with staff (S-04 decision).
- The staff lookup page links to the Hall of fame and the moderation pages.
- The admin lists `hidden_at` and offers a hidden / not hidden filter. It stays read-only.
- `HALL_TOP_N` (default 10), `HALL_RECENT_N` (default 5) and `HALL_REFRESH_S` (default 5) are settings that can be overridden through `BASHDASH_HALL_*` env vars (PRD Open Question 3).

Verify: the test suite is green. Then run locally: finish a few games, open `/staff/hall` on a wide window and `/staff/moderate` in a second browser, hide a row, and watch it disappear from the screen within one refresh (see Manual Testing Steps).

### Key Discoveries:

- One filter in `ranked_games()` (`game/services.py:104`) is enough to apply disqualification to `/done`, the lookup and the Hall of fame, because all of them go through it. The recent list is derived from the same ranked rows (sorted by finish time), so it needs no separate filter and cannot race with the ranking query (review F3).
- `solved > 0` ⇔ `last_solved_at IS NOT NULL` (S-03), so within one `solved` value `elapsed` is either always `None` or never `None`. That makes a single ordered pass over `ranked_games()` enough for competition ranking: rows share a place exactly when `(solved, attempts, elapsed)` are equal. This matches `rank_of`'s "strictly better" count.
- `staff_member_required` answers an unauthenticated request with a 302 to the login page. `fetch()` follows it silently and gets a 200 login page back. The polling endpoint therefore needs its own check that returns 403, so the JS can tell "session expired" apart from real board HTML.
- The prize code is the only thing that identifies a winner (PRD Access Control). The big screen is visible to everyone at the booth, so it must never render `code`.

## What We're NOT Doing

- The rotating QR code and start token (S-06). The screen layout leaves a slot (a template block) where S-06 puts the QR, but renders nothing there.
- Hiding by nick string (all games with a matching nick). Nicks are not unique, so each game is hidden on its own.
- Pre-moderation, a profanity filter, or nick rewriting (the PRD settled on reactive moderation).
- Hide/unhide controls on the big screen itself (the screen is public-facing) or in the staff lookup card (that card only shows the status).
- Telling a hidden player that they are disqualified. `/done` just shows "not ranked".
- A public ranking, websockets/SSE, or caching (the PRD rules out a public ranking; the tech stack says polling).
- Showing solve time on the Hall of fame (the PRD Business Logic says it is used only for tie-breaks).
- Staff-configurable N/K/refresh in the UI. These are env settings, changed by the operator.
- Stripping Unicode bidi/control characters from nicks. A nick that breaks the layout is handled by hiding it.
- Changing how `rank_of` computes a single place.

## Implementation Approach

Three phases, following the house pattern: the rules go in `game/services.py`, the views stay thin, and staff pages go in `game/staff_views.py`.

1. **Rules and data.** Add `hidden_at` and its migration. Add the hidden filter to `ranked_games()`. Add `hide_game` / `unhide_game` and a `hall_of_fame()` service that returns the top N and the recent rows, with places computed in one pass. Fix the `/done` `None` crash, show the hidden status on the lookup page, and update the admin. All of this can be tested without new pages.
2. **Big screen.** `/staff/hall` renders the full page with the board included server-side. `/staff/hall/board` returns just the board fragment for polling. A small `hall.js` swaps the fragment in every `HALL_REFRESH_S` seconds. It also gets its own wide-layout CSS.
3. **Moderation.** `/staff/moderate` lists what the screen shows and adds Hide/Unhide buttons. `POST /staff/hide` and `POST /staff/unhide` update the game and redirect back. The lookup page gets nav links.

We poll a server-rendered HTML fragment instead of doing a full-page `<meta refresh>` for three reasons:
- the page does not flash on a screen people are watching;
- a failed refresh keeps the last board instead of showing a browser error page at the booth;
- S-06's QR can later sit in a stable part of the page.

The fragment reuses the same template partial as the first render, so there is no client-side templating.

## Critical Implementation Details

- **Polling auth returns 403, not a redirect.** `/staff/hall/board` must not use `staff_member_required`. Check `request.user.is_active and request.user.is_staff` and otherwise return `HttpResponseForbidden`. In `hall.js`, treat `resp.status === 403` (or `resp.redirected`) as session expired. Only `resp.ok` responses replace the board.
- **One pass computes places.** `hall_of_fame()` iterates `ranked_games()` once. The place is the 1-based index, except that a row whose `(solved, attempts, elapsed)` equals the previous row's key reuses the previous place. Take the top N from the start of that pass and look up recent games' places in a dict keyed by `pk`. A test must check that these places equal `rank_of()` for every game in a mixed fixture that includes ties and zero-solve games.
- **Never render `code` on `/staff/hall`.** Rows passed to the board partial carry only nick, solved, attempts and place. The moderation page uses the game `pk` as the form key, not the code.

## Phase 1: Hidden flag and ranking rules

### Overview

Games can be hidden and unhidden. Hidden games leave the ranking everywhere. A service returns what the Hall of fame shows. `/done` and the staff lookup handle hidden games correctly.

### Changes Required:

#### 1. Model field

**File**: `game/models.py`

**Intent**: Record that staff hid (disqualified) a game, and when, without touching its result.

**Contract**: Add `hidden_at = DateTimeField(null=True, blank=True, editable=False, db_index=True)` and an `is_hidden -> bool` property. Mention both in the model docstring.

#### 2. Migration

**File**: `game/migrations/0005_gamesession_hidden_at.py`

**Intent**: Add the nullable column. Existing rows are not hidden.

**Contract**: A single `AddField`, generated by `makemigrations`.

#### 3. Settings

**File**: `config/settings.py`

**Intent**: Make the Open Question 3 values tunable during the event without a code change.

**Contract**: `HALL_TOP_N = int(os.environ.get('BASHDASH_HALL_TOP_N', 10))`, `HALL_RECENT_N` (`BASHDASH_HALL_RECENT_N`, 5), `HALL_REFRESH_S` (`BASHDASH_HALL_REFRESH_S`, 5), placed next to `GAME_DURATION_S`.

#### 4. Services

**File**: `game/services.py`

**Intent**: Keep disqualification and the Hall of fame data in the rules module, with the ranking rule still defined once.

**Contract**:
- `ranked_games()`: add `hidden_at__isnull=True` to the filter and update the docstring (hidden games are not ranked).
- `hide_game(game_id, now=None) -> tuple[GameSession, bool]`: a guarded `UPDATE … WHERE hidden_at IS NULL` sets `hidden_at=now`, then the row is re-read. Returns `True` if this call hid it.
- `unhide_game(game_id) -> tuple[GameSession, bool]`: a guarded `UPDATE … WHERE hidden_at IS NOT NULL` clears `hidden_at`. Both functions raise `GameSession.DoesNotExist` for an unknown id and must also treat a malformed id (Django raises `ValidationError` for a bad UUID) as `DoesNotExist` (review F4).
- A frozen dataclass `BoardRow(game_id, nick, solved, attempts, place)`.
- `hall_of_fame(top_n, recent_n) -> Board` (a frozen dataclass with `top: list[BoardRow]`, `recent: list[BoardRow]`, `ranked_total: int`). It makes one pass over `ranked_games()` (see Critical Implementation Details). `recent` is built from the same ranked rows (already finished and not hidden), sorted by `-finished_at, -pk` and cut to `recent_n`, so a game finishing between two queries cannot cause a `KeyError` (review F3). No separate recent query and no separate place lookup.
- `hidden_games() -> QuerySet`: hidden games ordered by `-hidden_at`, for the moderation page.

#### 5. `/done` carry-over

**Files**: `game/views.py`, `game/templates/game/done.html`

**Intent**: A hidden player reloading `/done` gets their summary and code, not a 500 (S-03 impl-review F2).

**Contract**: Bind `rank = services.rank_of(game)`. Pass `place`/`ranked_total` as `None` when `rank` is `None`. In the template, render `Place: #R of M` when `place` is set, otherwise `Place: not ranked`.

#### 6. Staff lookup status

**File**: `game/templates/game/staff/lookup.html`

**Intent**: Staff can tell a disqualified game apart from other unranked states.

**Contract**: For a finished game with `game.is_hidden`, the Place line reads "Hidden from Hall of fame (disqualified)". The "not ranked" text stays for any other `rank=None` case. The prize button logic is unchanged.

#### 7. Admin

**File**: `game/admin.py`

**Intent**: The operator can see hidden games in the admin as a backup.

**Contract**: Add `hidden_at` to `list_display` and `('hidden_at', admin.EmptyFieldListFilter)` to `list_filter`. The admin stays read-only.

#### 8. Tests

**Files**: `game/tests/test_services.py`, `game/tests/test_views.py`, `game/tests/test_staff_views.py`

**Intent**: Pin down disqualification semantics, the place parity, and the carry-over fix.

**Contract**:
- `ranked_games` / `rank_of`: a hidden game → `rank_of` returns `None`. The other games' places move up and their `M` drops by one. Unhiding restores both.
- `hide_game` / `unhide_game`: the first call returns `True`, a repeat returns `False` with the timestamp unchanged, an unknown id raises `DoesNotExist`, and `solved`/`attempts`/`code`/`prize_given_at` are untouched.
- `hall_of_fame`:
  - top N order, truncation and `ranked_total`;
  - ties share a place (competition ranking: 1, 2, 2, 4);
  - zero-solve games are ranked last;
  - hidden games are absent from `top` and `recent`, and unfinished games are absent;
  - overdue unfinished games are expired first and then appear;
  - `recent` is newest-first and capped at `recent_n`;
  - **parity**: for a mixed fixture, every `BoardRow.place` equals `rank_of(game)[0]`.
- `/done`: a hidden finished game → 200, shows "not ranked" and the prize code.
- Staff lookup: a hidden finished game → "disqualified" text, and the prize button is still present.

### Success Criteria:

#### Automated Verification:

- Game and challenge tests pass: `uv run python manage.py test game challenges`
- Django checks pass: `uv run python manage.py check`
- No missing migrations: `uv run python manage.py makemigrations --check --dry-run`
- Migration applies to the existing dev DB: `uv run python manage.py migrate`

#### Manual Verification:

- In `/admin/game/gamesession/`, the `hidden at` column and the hidden / not hidden filter are visible, and the admin is still read-only.
- After hiding a finished game from the shell (`services.hide_game(pk)`), that player's `/done` shows "not ranked" and their code, and the staff lookup shows "disqualified".

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Hall of fame screen

### Overview

A staff-only big-screen page that shows the top N and the recently finished games and refreshes itself.

### Changes Required:

#### 1. Staff views

**File**: `game/staff_views.py`

**Intent**: A full page for the first render and a fragment endpoint for polling, both built from `services.hall_of_fame()`.

**Contract**:
- `hall(request)`, `GET /staff/hall`, uses `staff_member_required`. It renders `game/staff/hall.html` with the board context (`board`, `total` = `len(catalog.main_set())`), `board_url`, and `refresh_ms` = `settings.HALL_REFRESH_S * 1000`.
- `hall_board(request)`, `GET /staff/hall/board`, does its own staff check and returns 403 on failure (see Critical Implementation Details). It renders only `game/staff/_board.html` with the same board context, with `Cache-Control: no-store` (Django's `never_cache`).
- Both pass `settings.HALL_TOP_N` and `settings.HALL_RECENT_N`.

#### 2. Routes

**File**: `game/urls.py`

**Contract**: `path('staff/hall', …, name='staff_hall')` and `path('staff/hall/board', …, name='staff_hall_board')`, with no trailing slash (matching the existing routes).

#### 3. Templates

**Files**: `game/templates/game/staff/hall.html` (new, extends `game/base.html`), `game/templates/game/staff/_board.html` (new partial)

**Intent**: A page readable from a few metres away on a landscape monitor, with the board markup defined once.

**Contract**:
- `hall.html`:
  - sets a wide-layout body/main class (add a `{% block main_class %}` hook to `base.html`, empty by default);
  - wraps the included partial in `<div id="board" data-board-url=… data-refresh-ms=…>`;
  - adds a status badge element and an empty `{% block qr %}` slot reserved for S-06;
  - loads `hall.js` via `{% block scripts %}`.
- `_board.html`:
  - two sections, "Hall of fame" and "Just finished";
  - top rows show `#place`, nick, `solved / total`, and attempts;
  - recent rows show nick, `solved / total`, attempts, and `#place`;
  - empty states: "No finished games yet" and "Nobody has finished yet";
  - no `code`, no solve time, no game ids. Nicks are auto-escaped (no `|safe`).

#### 4. Polling script

**File**: `game/static/game/hall.js` (new)

**Intent**: Refresh the board without a flash. Survive network blips and an expired session without leaving the screen blank.

**Contract**:
- Every `data-refresh-ms`, `fetch(boardUrl, {cache: 'no-store', credentials: 'same-origin'})`.
- On `resp.ok && !resp.redirected`, replace `#board`'s `innerHTML` with the response text and hide the badge.
- On 403 or a redirect, show "Session expired — log in again" and keep polling, so a re-login in another tab recovers.
- On a network error or another status, show "Reconnecting…" and keep the old board.
- Use one `setTimeout` chain so requests never overlap.

#### 5. Styles

**File**: `game/static/game/game.css`

**Intent**: A big-screen layout that does not affect the phone pages.

**Contract**: Every new rule is scoped under the hall class:
- a wide `main` (max-width about 110rem);
- a two-column grid (top N wider) that stacks below about 900 px;
- large type (rows about 2rem);
- a highlighted top 3;
- nicks truncated with an ellipsis;
- a small fixed status badge using `--warn`/`--bad`.

It reuses the existing tokens.

#### 6. Tests

**File**: `game/tests/test_staff_views.py`

**Contract**:
- Anonymous or non-staff: `/staff/hall` redirects to the admin login, and `/staff/hall/board` returns 403 (not a redirect).
- A staff user sees both sections, the rows in rank order with shared places for ties, and `solved / total`.
- The response never contains any game's `code` (assert for every fixture code), on both the page and the fragment.
- A hidden game's nick is absent.
- A nick of `<b>x</b>` is rendered escaped.
- The empty states render with zero games.
- The fragment carries `Cache-Control: no-store`.
- The page has `data-board-url` and a `data-refresh-ms` that follows `HALL_REFRESH_S` (via `override_settings`).
- `HALL_TOP_N=2` truncates the list.

### Success Criteria:

#### Automated Verification:

- Game and challenge tests pass: `uv run python manage.py test game challenges`
- Django checks pass: `uv run python manage.py check`
- No missing migrations: `uv run python manage.py makemigrations --check --dry-run`

#### Manual Verification:

- At 1920×1080 and 1366×768 the page shows both columns without scrolling for 10 + 5 rows and is readable from about 3 m away. Below 900 px the columns stack.
- A newly finished game appears in "Just finished" (and in the top N if it qualifies) within about `HALL_REFRESH_S`, without a visible flash.
- Stopping the dev server shows "Reconnecting…" and keeps the last board. Restarting it recovers on its own.
- Logging out in another tab shows "Session expired". Logging back in recovers without a reload.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Moderation (hide / unhide)

### Overview

A phone-friendly staff page to hide an offensive or duplicate nick from the Hall of fame and to undo a mistaken hide.

### Changes Required:

#### 1. Staff views

**File**: `game/staff_views.py`

**Intent**: Moderation that mirrors what the screen shows, with PRG mutations.

**Contract**:
- `moderate(request)`, `GET /staff/moderate`, uses `staff_member_required`. It renders `game/staff/moderate.html` with `board = services.hall_of_fame(HALL_TOP_N, HALL_RECENT_N)` and `hidden = services.hidden_games()`.
- `hide(request)` and `unhide(request)`, `POST /staff/hide` and `POST /staff/unhide`, use `staff_member_required` and `require_POST`. The field is `game_id`. A missing, malformed or unknown id → `messages.error("No such game.")`. Otherwise call the service and add `messages.success("Hidden <nick>." / "<nick> is back on the Hall of fame.")` or `messages.warning` ("already hidden" / "not hidden"; the existing staff template renders `info` in red, review F6). All three outcomes redirect to `game:staff_moderate`.

#### 2. Routes

**File**: `game/urls.py`

**Contract**: `staff/moderate` (`staff_moderate`), `staff/hide` (`staff_hide`), `staff/unhide` (`staff_unhide`).

#### 3. Template

**File**: `game/templates/game/staff/moderate.html` (new, extends `game/base.html`)

**Intent**: One phone screen that answers "which nick is on the screen right now, and how do I remove it?"

**Contract**:
- Heading "Hall of fame moderation", followed by the messages.
- Sections "On screen: top N" and "On screen: just finished". Each row shows the place, the nick, solved/attempts, and a POST form (`{% csrf_token %}`, a hidden `game_id`, a "Hide" button). A game that appears in both lists gets a button in each; both hide the same game.
- A "Hidden" section lists each hidden game's nick, solved/attempts, "hidden N min ago", and an "Unhide" button. When there are none, it shows "No hidden games".
- Links to `/staff/hall` and `/staff`.

#### 4. Lookup navigation

**File**: `game/templates/game/staff/lookup.html`

**Contract**: A small nav line under the heading with links to "Hall of fame screen" (`staff_hall`) and "Moderation" (`staff_moderate`).

#### 5. Styles

**File**: `game/static/game/game.css`

**Contract**: Moderation rows are a compact flex row (nick truncated, button on the right) that fits at 320 px. The Hide button uses the `--bad` token and Unhide uses the neutral style.

#### 6. Tests

**File**: `game/tests/test_staff_views.py`

**Contract**:
- `StaffTestCase.make_game` gets `code` and finish-time parameters (prize codes must be unique, and all games currently share one finish time) before multi-game tests are written (review F5).
- Anonymous or non-staff GET `/staff/moderate` and POST to hide/unhide redirect to the login page, and nothing changes in the DB.
- The moderation page lists top and recent rows with Hide forms, and hidden games with Unhide forms.
- POST hide → a redirect to moderation, `hidden_at` is set, and after following the redirect the success message appears, the nick is in "Hidden", and it is absent from `/staff/hall/board`.
- A second hide → an info message, and the timestamp is unchanged.
- Unhide → `hidden_at` is cleared, and the nick is back on the board.
- An unknown UUID or a malformed id → an error message and no exception.
- A POST without a CSRF token (`Client(enforce_csrf_checks=True)`) → 403.
- The hidden game's `/done` place is "not ranked" and the other players' `M` drops (end to end).
- The lookup page shows both nav links.

### Success Criteria:

#### Automated Verification:

- Game and challenge tests pass: `uv run python manage.py test game challenges`
- Django checks pass: `uv run python manage.py check`
- No missing migrations: `uv run python manage.py makemigrations --check --dry-run`

#### Manual Verification:

- With `/staff/hall` open on a wide window and `/staff/moderate` on a phone-width window, hiding a nick removes it from the screen within one refresh, and unhiding brings it back.
- The moderation page fits 360 px and 320 px without horizontal scroll, and the Hide buttons are easy to tap.
- The hidden player's `/done` still shows their code and "not ranked", and the staff lookup shows "disqualified" with the prize button available.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- `ranked_games` hidden filter: effect on `rank_of` places and totals, and restoration on unhide.
- `hide_game` / `unhide_game` idempotence and guarded updates.
- `hall_of_fame`: ordering, truncation, ties, zero-solve games, hidden and unfinished exclusion, recent ordering, and place parity with `rank_of`.

### Integration Tests:

- Staff views through the Django test client:
  - access control, including the fragment returning 403 instead of a redirect;
  - codes never leaked on the screen;
  - escaping;
  - empty states;
  - the hide/unhide PRG flow and CSRF;
  - the end-to-end disqualification effect on `/done` and the board.

### Manual Testing Steps:

1. `uv run python manage.py migrate`. Make sure a staff user exists (`createsuperuser`).
2. `BASHDASH_GAME_DURATION_S=30 BASHDASH_HALL_REFRESH_S=3 uv run python manage.py runserver`. Finish 4–6 short games from a phone-width window with different nicks, including two with identical results (a tie).
3. Open `/staff/hall` in a full-screen browser window. Check the top N order, the shared place for the tie, "Just finished" newest-first, and that no codes or times are shown.
4. Finish another game and watch it appear without a page flash.
5. In another browser, open `/staff/moderate` and hide one nick. Check that the screen drops it within about 3 s and the other places move up. Unhide it and check that it returns.
6. Reload the hidden player's `/done`: it should show "not ranked" plus the code. Look up that code on `/staff`: it should show "disqualified" and the prize button.
7. Stop `runserver` and see "Reconnecting…". Start it again and watch the board recover.

## Performance Considerations

Each refresh (once per `HALL_REFRESH_S`, one screen) runs the bulk `expire_overdue` `UPDATE`, one ordered `SELECT` over finished games (hundreds of rows at most for one event day), and one small `SELECT` for recent games. That is comparable to a `/done` load and negligible next to sandbox runs. The one-pass ranking is O(n) in Python. No caching is needed. With several screens or tabs open, the cost scales linearly and is still trivial.

## Migration Notes

`0005_gamesession_hidden_at` adds a nullable, indexed column. It is safe on the existing DB, and reversing it drops the column. Operational notes for the event:
- The display laptop stays logged in as a staff account, and `/staff` and `/staff/moderate` only check `is_staff`. A non-superuser, no-permission account keeps `/admin` out, but kiosk mode and watching the screen are the only protection for the desk and moderation pages. Follow-up: split permissions so the display account cannot reach them (impl review F3, Fix A).
- The display laptop stays logged in (the Django session lasts 2 weeks by default).
- Disable the display's screensaver and sleep.
- Rehearsal games should still be deleted before the event (S-03 plan-review note); hiding is not meant for bulk cleanup.

## References

- Roadmap entry: `context/foundation/roadmap.md` (S-05, including the S-03 carry-over). PRD: FR-010, FR-012, Business Logic, Access Control, and Open Question 3 in `context/foundation/prd.md`.
- Tech-stack decision (custom `staff` pages, polling leaderboard): `context/foundation/tech-stack.md` ("Why this stack").
- Ranking rule: `game/services.py:104-125`. `/done`: `game/views.py:176-194`. Staff views: `game/staff_views.py`.
- S-03 impl-review F2 (`rank_of → None` crash): `context/archive/2026-09-29-summary-with-prize-code/reviews/impl-review.md`.
- S-04 plan (staff page pattern, PRG, `staff_member_required`): `context/archive/2026-09-29-staff-code-lookup-and-prize/plan.md`.
- Test patterns: `game/tests/test_staff_views.py` (`StaffTestCase.make_game`), `game/tests/test_views.py` (`ViewTestCase`, `SummaryTests`).

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Hidden flag and ranking rules

#### Automated

- [x] 1.1 Game and challenge tests pass: `uv run python manage.py test game challenges` — 4042eef
- [x] 1.2 Django checks pass: `uv run python manage.py check` — 4042eef
- [x] 1.3 No missing migrations: `uv run python manage.py makemigrations --check --dry-run` — 4042eef
- [x] 1.4 Migration applies to the existing dev DB: `uv run python manage.py migrate` — 4042eef

#### Manual

- [x] 1.5 Admin shows the hidden-at column and filter and stays read-only — 4042eef
- [x] 1.6 Hidden game: `/done` shows "not ranked" and code; staff lookup shows "disqualified" — 4042eef

### Phase 2: Hall of fame screen

#### Automated

- [x] 2.1 Game and challenge tests pass: `uv run python manage.py test game challenges` — 33bdd9c
- [x] 2.2 Django checks pass: `uv run python manage.py check` — 33bdd9c
- [x] 2.3 No missing migrations: `uv run python manage.py makemigrations --check --dry-run` — 33bdd9c

#### Manual

- [x] 2.4 Both columns fit 1920×1080 and 1366×768, readable from ~3 m; stacks below 900 px
- [x] 2.5 New finished game appears within one refresh without a flash
- [x] 2.6 Server down shows "Reconnecting…" and keeps the board; recovers on restart
- [x] 2.7 Logout elsewhere shows "Session expired"; re-login recovers without reload

### Phase 3: Moderation (hide / unhide)

#### Automated

- [x] 3.1 Game and challenge tests pass: `uv run python manage.py test game challenges` — 9098968
- [x] 3.2 Django checks pass: `uv run python manage.py check` — 9098968
- [x] 3.3 No missing migrations: `uv run python manage.py makemigrations --check --dry-run` — 9098968

#### Manual

- [x] 3.4 Hiding removes the nick from the screen within one refresh; unhiding restores it
- [x] 3.5 Moderation page fits 360 px and 320 px; buttons easy to tap
- [x] 3.6 Hidden player's `/done` shows code and "not ranked"; lookup shows "disqualified" with prize button
