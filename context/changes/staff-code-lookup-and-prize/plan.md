# Staff Code Lookup and Prize Issuing Implementation Plan

## Overview

Booth staff log in with a password, type a player's 6-digit code, and see that game's result: nick, solved, attempts, place, solve time, and when it finished. They then mark "prize given" (FR-011, FR-013). A second attempt to give a prize for the same code is refused and shows when the first one was given. This meets the PRD's primary success criterion: every issued code can be verified at the booth.

## Current State Analysis

- `GameSession.code` (`game/models.py:32`) is a unique, non-null 6-digit `CharField`. It is assigned in `services.start_game` with a collision retry (`game/services.py:73-90`). The unique constraint also gives an index, so an exact lookup by code is cheap.
- The ranking rule exists once: `services.ranked_games()` and `services.rank_of(game) -> (place, total) | None` (`game/services.py:102-123`). `rank_of` bulk-expires overdue games first and returns `None` for an unfinished game. After S-05 it will also return `None` for a hidden game (S-03 impl-review F2).
- `services.expire_overdue(game_id)` (`services.py:93-99`) finishes one overdue game. Unfinished-but-overdue games exist until something reads them.
- The admin (`game/admin.py`) is fully read-only (`ReadOnlyMixin`). It lists and searches `code` (the S-03 stopgap). Its module docstring says "S-04 builds the real staff tooling".
- There is no staff-facing page and no "prize given" field. `django.contrib.auth`, `admin`, `sessions` and `messages` are installed (`config/settings.py:34-43`). The admin login at `/admin/login/` is the only login page.
- The player UI is server-rendered Django templates on `game/templates/game/base.html` with mobile-first CSS tokens in `game/static/game/game.css`. The copy is in English.
- Tests use Django `TestCase`. `game/tests/test_views.py` has a `ViewTestCase` base that patches the sandbox. The baseline is `uv run python manage.py test game challenges` → 149 tests, OK.

## Desired End State

- `GameSession.prize_given_at` (nullable datetime) records when the prize was handed out.
- `/staff/` (staff login required) shows a code input with a numeric keyboard on phones. Submitting a code shows one of these:
  - **Found, finished**: nick (large, with "Ask the player for their nick"), Solved `X / total`, Attempts, Place `#R of M`, Solve time `m:ss` (or "—" when 0 solved), "Finished N minutes ago", and the prize status: a "Mark prize given" button, or a warning "Prize already given N minutes ago (HH:MM)".
  - **Found, still playing**: the same identity data, "Game in progress", and no prize button.
  - **Found, not ranked** (`rank_of` → `None` for a finished game, which happens after S-05 hides a nick): place shows "not ranked". The prize button stays available. Disqualification only hides the nick, and prize policy stays with the staff.
  - **Not found / malformed**: "No game with code 123456" / "Enter a 6-digit code", with the input kept.
- `POST /staff/prize` marks the prize once (atomic conditional update), then redirects back to the lookup (Post/Redirect/Get) with a success message or an "already given" warning.
- Anonymous users and logged-in non-staff users are redirected to the admin login and never see game data.
- The admin shows `prize_given_at` as a column and as a "given / not given" filter. The admin stays read-only.

Verify: `uv run python manage.py test game challenges` is green. Then, locally, create a staff user, finish a short game, look up its code on `/staff/`, mark the prize, and try again (see Manual Testing Steps).

### Key Discoveries:

- `rank_of` already covers "place" and handles unfinished games. The lookup view must treat `None` as "not ranked", not unpack it blindly (the S-03 `done` view does unpack it; that is the S-05 carry-over).
- `django.contrib.admin.views.decorators.staff_member_required` gives password login for free. It redirects to `admin:login?next=/staff/...`, so the staff page needs no login template of its own.
- `solved > 0` ⇔ `last_solved_at IS NOT NULL` (S-03 plan). The solve time is `last_solved_at - started_at`, and it is `None` when nothing was solved.
- `TIME_ZONE = 'UTC'` (`config/settings.py:118`). Absolute clock times would read wrong at a Polish booth, so relative times (`timesince`) are the main display. `HH:MM` appears only in the "already given" warning, rendered with Django's `localtime` (UTC unless the operator changes `TIME_ZONE`).

## What We're NOT Doing

- Hiding nicks, disqualification, and the Hall of fame screen (S-05). The lookup only tolerates `rank_of() → None`.
- Undoing "prize given" in the UI. A mistaken mark is rare. Staff can hand the prize over anyway, and the operator can clear it from the shell: `GameSession.objects.filter(code='…').update(prize_given_at=None)`.
- Recording which staff member gave the prize. The booth likely shares one account.
- Different prizes by place (PRD Open Question 2). The mark is the same for every prize.
- Editing or voiding results (PRD Non-Goal; FR-014 was removed).
- Making the admin writable. It stays a read-only inspection tool.
- Rate-limiting or hardening the code lookup. Only logged-in staff can use it.
- Showing prize status to the player on `/done`.
- A custom login page, or creating staff accounts in a migration. Accounts are created with `createsuperuser` (an operational step).

## Implementation Approach

Two phases, following the house pattern: rules in `game/services.py` and thin views.

Phase 1 adds the data and the rules: the `prize_given_at` field and migration, `find_by_code()` and `mark_prize_given()` in services, and the admin column and filter. It can be tested without any UI.

Phase 2 adds the staff page: a separate `game/staff_views.py` module (it keeps player and staff code apart; S-05's Hall of fame will join it), routes under `staff/` in `game/urls.py`, one template, and a few CSS rules.

We use a custom page instead of an admin action. `tech-stack.md` assumed the Django admin would cover FR-011 to FR-013. But the admin flow for giving a prize is search → tick a checkbox → pick an action → Go. That can mark the wrong row, and it cannot show the result, the place, and an "already given" warning on one phone-sized screen before the click. The custom page is about one view module, one template and some tests. It also sets up the `staff/` URL space and the auth pattern that S-05 reuses.

## Critical Implementation Details

- **Expire before reading or marking.** Call `services.expire_overdue(game.pk)` before `rank_of`/`is_finished` in the lookup and before the conditional update in `mark_prize_given`. Otherwise an abandoned, overdue game shows "in progress" and cannot be given a prize.
- **Mark with one guarded UPDATE.** `mark_prize_given` does `filter(pk=…, finished_at__isnull=False, prize_given_at__isnull=True).update(prize_given_at=now)`. The row count says whether this call marked it. That makes two staff devices pressing at once safe with no read-modify-write. After that, re-read the row to report the stored timestamp.

## Phase 1: Prize flag and staff rules

### Overview

Every game can record when its prize was given. Services can find a game by code and mark its prize exactly once. The admin shows the flag.

### Changes Required:

#### 1. Model field

**File**: `game/models.py`

**Intent**: Store when the prize was handed out. A timestamp instead of a boolean, so the "already given" warning can say when.

**Contract**: `GameSession.prize_given_at = DateTimeField(null=True, blank=True, editable=False)`. Add `@property prize_given -> bool`. Mention the field in the model docstring.

#### 2. Migration

**File**: `game/migrations/0004_gamesession_prize_given_at.py`

**Intent**: Add the nullable column. Existing rows start as "not given". No backfill is needed.

**Contract**: A single `AddField`, generated by `makemigrations`.

#### 3. Services

**File**: `game/services.py`

**Intent**: Keep the prize rules in the rules module so views stay thin.

**Contract**:
- `CODE_RE = re.compile(r'^\d{6}$')` and `normalize_code(raw: str) -> str | None`: strip all whitespace (staff may type `987 654`). Return the code if it matches, else `None`.
- `find_by_code(code: str) -> GameSession | None`: run `expire_overdue` for the matching game, then return the fresh row (or `None`).
- `mark_prize_given(game_id, now=None) -> tuple[GameSession, bool]`: run `expire_overdue(game_id)`, then the guarded `UPDATE` (see Critical Implementation Details), then re-read. Return `(game, True)` if this call marked it. Return `(game, False)` if it was already marked or the game is unfinished; the caller tells the two apart with `game.is_finished` and `game.prize_given`. Raise `GameSession.DoesNotExist` for an unknown id.
- `solve_time(game) -> timedelta | None`: `last_solved_at - started_at`, or `None`. It lives here so S-05 and templates share one definition.

#### 4. Admin

**File**: `game/admin.py`

**Intent**: Let an operator see prize status in the admin as a backup to the staff page.

**Contract**: Add `prize_given_at` to `list_display`, and a `list_filter` for given / not given (`('prize_given_at', admin.EmptyFieldListFilter)`). Update the module docstring to point to `/staff/`. The admin stays read-only.

#### 5. Tests

**File**: `game/tests/test_services.py`

**Intent**: Pin down the once-only rule and the lookup edge cases.

**Contract**:
- `normalize_code`: `'987654'`, `' 987 654 '` → `'987654'`; `'000042'` keeps its leading zeros; `'12345'`, `'1234567'`, `'abcdef'`, `''` → `None`.
- `find_by_code`: finds by exact code; an unknown code → `None`; an overdue unfinished game comes back finished.
- `mark_prize_given`: the first call → `(game, True)` with `prize_given_at` set; the second call → `(game, False)` with the timestamp unchanged; an unfinished game → `(game, False)` with `prize_given_at` still `None`; an overdue unfinished game is expired and marked `True`; an unknown id raises `DoesNotExist`.
- `solve_time`: `None` for 0 solved; the right delta otherwise.

### Success Criteria:

#### Automated Verification:

- Game and challenge tests pass: `uv run python manage.py test game challenges`
- Django checks pass: `uv run python manage.py check`
- No missing migrations: `uv run python manage.py makemigrations --check --dry-run`
- Migration applies to the existing dev DB: `uv run python manage.py migrate`

#### Manual Verification:

- In `/admin/game/gamesession/`, the `prize given at` column and the given / not given filter are visible, and the admin is still read-only.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Staff lookup page

### Overview

A phone-friendly `/staff/` page where logged-in staff look up a code, see the result, and mark the prize given.

### Changes Required:

#### 1. Staff views

**File**: `game/staff_views.py` (new)

**Intent**: A thin HTTP layer for staff, separate from the player views. Every view requires a staff login.

**Contract**:
- Both views are decorated with `staff_member_required` (from `django.contrib.admin.views.decorators`).
- `lookup(request)`, `GET /staff/?code=…`:
  - no `code` → an empty form;
  - `normalize_code` fails → "Enter a 6-digit code.";
  - otherwise `find_by_code`. Not found → "No game with code NNNNNN." Found → the context holds `game`, `total` (= `len(catalog.main_set())`), `rank` (the `rank_of` result, which may be `None`), and `solve_time`.
- `give_prize(request)`, `POST /staff/prize` (`require_POST`, CSRF-protected), field `code`:
  - normalize and find the game (an unknown or malformed code → error message);
  - `mark_prize_given`;
  - add a `messages` success, warning, or error: "Prize given to nick." / "Prize was already given N minutes ago." / "Game still in progress — no prize yet.";
  - redirect to `lookup` with `?code=NNNNNN` (Post/Redirect/Get).

#### 2. Routes

**File**: `game/urls.py`

**Intent**: Put the staff pages under one prefix. S-05 adds its screen there.

**Contract**: `path('staff/', staff_views.lookup, name='staff_lookup')` and `path('staff/prize', staff_views.give_prize, name='staff_prize')`, in the existing `game` namespace.

#### 3. Template

**File**: `game/templates/game/staff/lookup.html` (new; extends `game/base.html`)

**Intent**: One screen that answers "is this the right person, how did they do, and did they already get a prize?" before the button is pressed.

**Contract**:
- Heading "Prize desk".
- Messages list.
- A GET form with a single input: `name="code"`, `inputmode="numeric"`, `autocomplete="off"`, `maxlength="7"`, autofocus, and the current code kept in it.
- Result card when a game is found, in this order:
  - the nick (large) and "Ask the player for their nick";
  - Solved `X / total`, Attempts, Place `#R of M` (or "not ranked"), Solve time `m:ss` (or "—");
  - "Finished {{ finished_at|timesince }} ago" or "Game in progress";
  - prize status: already given → a warning box with `timesince` and `HH:MM`; finished and not given → a POST form with a hidden `code`, `{% csrf_token %}`, and a big "Mark prize given" button; unfinished → no button.
- A small "Log out" link (a POST form to `admin:logout`, since Django 5+ requires POST for logout).
- Format the solve time with a small template filter (`game_text.py` already holds filters; add `mmss`) or pre-format it in the view. Either is fine; pick the one with less code.

#### 4. Styles

**File**: `game/static/game/game.css`

**Intent**: Make the card readable on a phone held at the booth.

**Contract**: `.staff-card` (panel background, border, padding), `.staff-nick` (large), `.notice-ok` / `.notice-warn` / `.notice-bad` using the existing `--accent`, `--warn` and `--bad` tokens, and a full-width prize button. No horizontal scroll at 320 px.

#### 5. Tests

**File**: `game/tests/test_staff_views.py` (new)

**Intent**: Pin down the access control, the lookup states, and the once-only prize flow over HTTP.

**Contract** (log in with `force_login` as a user with `is_staff=True`; create games with `services.start_game` and then `update(...)` to finish them, as `SummaryTests` does; use a fixed code such as `'987654'`):
- Anonymous GET `/staff/` and POST `/staff/prize` → redirect to the admin login. A logged-in non-staff user → the same. No game data in the response.
- GET with no code → the form, and no card.
- A malformed code → "Enter a 6-digit code". An unknown code → "No game with code".
- A code with spaces (`987 654`) finds the game.
- A finished game → the nick, `Solved`, `Attempts`, `#1 of 1`, the solve time, and the "Mark prize given" button.
- An unfinished game → "Game in progress", and no button.
- POST prize → a redirect to `?code=987654`; the DB has `prize_given_at` set; after following the redirect the page shows "already given" and no button.
- A second POST → a warning message, and the timestamp is unchanged.
- POST for an unfinished game → an error message, and `prize_given_at` is still `None`.
- POST without a CSRF token (`Client(enforce_csrf_checks=True)`) → 403.
- `rank_of` patched to return `None` for a finished game → "not ranked", and the button is still shown (the S-05 forward-compatibility guard).

### Success Criteria:

#### Automated Verification:

- Game and challenge tests pass: `uv run python manage.py test game challenges`
- Django checks pass: `uv run python manage.py check`
- No missing migrations: `uv run python manage.py makemigrations --check --dry-run`

#### Manual Verification:

- Logged out, `/staff/` goes to the admin login, and after login it returns to `/staff/`.
- At 360 px and 320 px width (Chrome devtools), the lookup form and the result card fit without horizontal scroll, and the code input opens a numeric keyboard on a real phone.
- End to end: play a short game, look up its code, see the same solved, attempts and place as the player's `/done`, mark the prize, and see the "already given" warning on a second lookup and a second press.
- Looking up the code of a game still in progress shows "Game in progress" and no prize button.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- Code normalization (whitespace, leading zeros, bad lengths and characters).
- `mark_prize_given`: once only, refused for unfinished games, expire-then-mark for overdue games.
- `find_by_code` expires overdue games.

### Integration Tests:

- Staff views through the Django test client: access control (anonymous, non-staff, staff), every lookup state, the Post/Redirect/Get prize flow, a double press, CSRF, and `rank_of → None`.

### Manual Testing Steps:

1. `uv run python manage.py migrate`, then `uv run python manage.py createsuperuser` (or set `is_staff` on an existing user).
2. `BASHDASH_GAME_DURATION_S=30 uv run python manage.py runserver`. Play a game at phone width and note the code on `/done`.
3. In another browser, open `/staff/`, log in, and enter the code (try it with a space in the middle). Compare the numbers with `/done`.
4. Press "Mark prize given". Check the success message. Press it again (or reload and look it up again) and check the warning.
5. Start a new game, and look up its code before it ends. It should show "Game in progress" and no button.
6. Check the admin list for the `prize given at` column and filter.

## Performance Considerations

A lookup runs one indexed `SELECT` by code, the bulk `expire_overdue` `UPDATE`, and the two `COUNT`s in `rank_of`. That is the same cost as a `/done` load, and it happens once per player at the booth. Marking is a single-row `UPDATE`. No caching is needed.

## Migration Notes

`0004_gamesession_prize_given_at` adds a nullable column, so it is safe on any existing DB. Reversing it drops the column. Operational step before the event: create at least one staff account (`createsuperuser`) on the event VM, and share the password with the booth staff.

## References

- Roadmap entry: `context/foundation/roadmap.md` (S-04). PRD: FR-011, FR-013, and Access Control in `context/foundation/prd.md`.
- Tech-stack rationale (admin for staff tooling): `context/foundation/tech-stack.md:24`.
- S-03 plan and impl-review F2 (`rank_of` → `None` after S-05): `context/archive/2026-09-29-summary-with-prize-code/`.
- Ranking and expiry: `game/services.py:93-123`. Code field: `game/models.py:32`. Admin: `game/admin.py`.
- View test patterns: `game/tests/test_views.py:22-41` (`ViewTestCase`) and `:373-399` (`SummaryTests`).

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Prize flag and staff rules

#### Automated

- [ ] 1.1 Game and challenge tests pass: `uv run python manage.py test game challenges`
- [ ] 1.2 Django checks pass: `uv run python manage.py check`
- [ ] 1.3 No missing migrations: `uv run python manage.py makemigrations --check --dry-run`
- [ ] 1.4 Migration applies to the existing dev DB: `uv run python manage.py migrate`

#### Manual

- [ ] 1.5 Admin shows the prize-given column and filter and stays read-only

### Phase 2: Staff lookup page

#### Automated

- [ ] 2.1 Game and challenge tests pass: `uv run python manage.py test game challenges`
- [ ] 2.2 Django checks pass: `uv run python manage.py check`
- [ ] 2.3 No missing migrations: `uv run python manage.py makemigrations --check --dry-run`

#### Manual

- [ ] 2.4 Logged-out `/staff/` goes to admin login and returns after login
- [ ] 2.5 Lookup form and card fit 360 px and 320 px; numeric keyboard on a real phone
- [ ] 2.6 End to end: lookup matches `/done`, prize marked, second press shows "already given"
- [ ] 2.7 In-progress game shows "Game in progress" and no prize button
