# Restrict Allowed Nicknames Implementation Plan

## Overview

A nick may contain only ASCII letters (`a-z`, `A-Z`), digits (`0-9`) and underscores (`_`), and be at most 12 characters long. The server enforces this rule in `services.start_game`, the only way a game gets a nick. The start form also shows the rule and checks it in the browser, but the server check is the one that counts. The nicks appear on the public Hall of fame screen at the booth, so this limits what a troll can show there (see PRD FR-002 / FR-012) and keeps long nicks from being cut off in the ranking rows.

## Current State Analysis

- `services.start_game(nick)` (`game/services.py:81-84`) strips the nick and checks only `1 <= len(nick) <= NICK_MAX_CHARS` (`NICK_MAX_CHARS = 20`, `game/services.py:38`). It raises `ValueError` otherwise. Any characters are accepted: spaces, emoji, HTML, Polish letters.
- `views.start` (`game/views.py:115-121`) catches that `ValueError` and re-renders `game/home.html` with `error = 'Enter a nick of 1-{NICK_MAX_CHARS} characters.'`, the submitted `nick`, and the same `t` token.
- `game/templates/game/home.html:18-20`: the nick `<input>` has `maxlength="20" required` and no `pattern` or hint.
- `GameSession.nick` is `CharField(max_length=20)` (`game/models.py:24`). SQLite does not enforce the length.
- Other callers of `start_game` that the new rule breaks:
  - `bench_game` creates nicks `f'bench-{i}'` (`game/management/commands/bench_game.py:62`). The hyphen is not allowed. `game/tests/test_bench.py:43,47` look these games up with `nick__startswith='bench-'`, and the `--keep` help text says `bench-*` (`bench_game.py:49`).
  - `StaffTestCase.make_game` (`game/tests/test_staff_views.py:25-26`) goes through `start_game`. `test_nick_is_escaped` (`:183-187`) creates the nick `'<b>x</b>'`, which the new rule rejects.
- Tests that already cover the rule: `test_services.py:51-54` (empty, whitespace-only, 21 chars) and `test_views.py:59-64,124-129` (whitespace-only nick shows the error and keeps the token). All other test nicks (`neo`, `ann`, `bob`, `cy`, `dee`, `zed`, `x`, `again`, `b`) already pass the new rule.
- Baseline: `uv run python manage.py test game challenges` → 231 tests, OK. There is no linter or type checker in the project.

## Desired End State

- `start_game` strips leading and trailing whitespace, then accepts the nick only if it fully matches `[A-Za-z0-9_]{1,12}`. Otherwise it raises `ValueError`, and no game is created.
- `POST /start` with an invalid nick returns 200 with the start form. It shows the error "Use 1-12 letters, digits or _ (no spaces)." It keeps the typed nick and the `t` token, and does not set `game_id` in the session.
- The start form shows the rule under the field. The input has `maxlength="12"` and a matching `pattern`, so most bad nicks are caught before the POST.
- `bench_game` uses `bench_<i>` nicks and still cleans up after itself.
- Nicks already in the database (up to 20 chars, any characters) stay as they are. They keep rendering, escaped, as today.

Verify: the full test suite is green. Then, in a browser, try `neo_42` (accepted), `ab cd`, `zażółć`, `abc-def` and a 13-character nick (all refused, see Manual Testing Steps).

### Key Discoveries:

- One choke point: every game is created through `services.start_game` (`game/services.py:81`). The views, the bench and the tests all call it, so the rule goes there and nowhere else. It is not added to the model.
- Python's `\w` and `str.isalnum()` accept Unicode letters and digits (`ł`, `٣`). The rule must use the explicit class `[A-Za-z0-9_]` with `re.fullmatch` (or `\A…\Z`). `re.match(r'^…$')` also accepts a trailing `\n`.
- The error re-render already carries `nick` and `t` (`game/views.py:119-121`, tested by `test_nick_error_keeps_token`). Only the message text changes.
- The browser `pattern` attribute is anchored automatically and compiled with the `v` flag in current browsers. `[A-Za-z0-9_]{1,12}` is valid there.

## What We're NOT Doing

- No migration and no change to `GameSession.nick` (`max_length=20` stays). Old nicks stay valid in the DB and the admin. Hiding a nick (FR-012) is still the moderation tool.
- No profanity or blocklist filter.
- No uniqueness check. Nicks stay non-unique (PRD §Users).
- No automatic cleanup such as replacing spaces with `_` or removing accents. A bad nick is refused, not changed.
- No non-ASCII letters (Polish diacritics are refused, as the rule says "letters a-z/A-Z").
- No validation added to the Django admin edit form.
- No JS. The browser check is plain HTML attributes.

## Implementation Approach

Two small phases. Phase 1 makes the server rule authoritative and fixes every caller and test that the rule breaks. After Phase 1 the feature is complete and safe. Phase 2 is UX only: it tells the player the rule before they submit and catches most mistakes in the browser.

Decisions made while planning (this was a non-interactive run, so each one takes the recommended default; see Open Risks in the brief):

- **Surrounding whitespace**: strip it, then validate. Phones often add a trailing space after autocomplete. Spaces inside the nick are refused.
- **Letters**: ASCII only, exactly as the rule states.
- **Existing data**: left alone. Rows are not changed and there is no migration.
- **Error copy**: one message that states the full rule, so the player knows how to fix any mistake.

## Phase 1: Server-side nick rule

### Overview

Replace the length-only check in `start_game` with the character and length rule. Update the view's error message, the bench nicks and the tests.

### Changes Required:

#### 1. Nick rule in services

**File**: `game/services.py`

**Intent**: Make `start_game` refuse any nick that is not 1-12 ASCII letters, digits or underscores (after stripping). Keep one module-level definition of the rule, next to `CODE_RE`, so the view and the template can refer to it.

**Contract**: `NICK_MAX_CHARS = 12`. New `NICK_RE = re.compile(r'[A-Za-z0-9_]{1,12}')` (built from `NICK_MAX_CHARS`), always used with `.fullmatch(...)`. `start_game(nick: str) -> GameSession` keeps its signature. It still raises `ValueError` for an invalid nick, before any DB write. The stripped nick is what gets stored.

#### 2. Error message in the start view

**File**: `game/views.py`

**Intent**: Tell the player the whole rule when the nick is refused.

**Contract**: In `start`, in the `except ValueError` branch, the `error` context value becomes `f'Use 1-{services.NICK_MAX_CHARS} letters, digits or _ (no spaces).'`. The `nick` and `token` context values stay the same.

#### 3. Bench nicks

**File**: `game/management/commands/bench_game.py`

**Intent**: Make bench games pass the new rule.

**Contract**: The nick becomes `f'bench_{i}'` (line 62). The `--keep` help text says `bench_*` (line 49). `WRONG_COMMAND` (a shell command, not a nick) does not change.

#### 4. Tests

**File**: `game/tests/test_services.py`

**Intent**: Pin the rule in both directions.

**Contract**: Make `test_empty_and_too_long_nicks_are_rejected` rejection-only: drop its 20-character acceptance and the one-game assertion (`test_services.py:55-56`), use 13 characters as the too-long case, and assert the `GameSession` count is 0. It rejects: `''`, `'   '`, `'x' * 13`, `'ab cd'`, `'abc-def'`, `'zażółć'`, `'neo!'`, `'<b>x</b>'`, an inner newline (`'a\nb'`), and a Unicode digit (`'٣'`). Put all accepted cases in a new sibling test, which accepts `'x' * 12`, `'Neo_42'`, `'_'`, `'123'`, and `'  neo_1  '` (stored as `'neo_1'`). Assert that no `GameSession` is created for the rejected cases.

**File**: `game/tests/test_views.py`

**Intent**: Cover a rule-breaking (not just blank) nick through the view.

**Contract**: Add a test that posts `'bad nick!'` with a valid token and asserts: status 200, the new error text, the typed nick echoed back in the input, the token kept, no game, no `game_id` in the session.

**File**: `game/tests/test_bench.py`

**Contract**: The `nick__startswith` lookups (lines 43, 47) use `'bench_'`.

**File**: `game/tests/test_staff_views.py`

**Intent**: Keep the escaping test. Old rows and admin edits can still hold HTML-like nicks, so the templates must keep escaping them.

**Contract**: `test_nick_is_escaped` creates its game by making a valid game with `make_game()`, then setting `nick='<b>x</b>'` with `GameSession.objects.filter(...).update(...)`. This skips `start_game` on purpose, and a short comment says so. The assertions do not change.

### Success Criteria:

#### Automated Verification:

- Full suite passes: `uv run python manage.py test game challenges`
- New rule tests pass: `uv run python manage.py test game.tests.test_services game.tests.test_views`
- Bench still runs and cleans up: `uv run python manage.py test game.tests.test_bench`
- No old bench prefix left: `grep -rn "bench-{" game/` returns nothing

#### Manual Verification:

- With a valid QR token, starting as `neo_42` goes to `/play`
- Submitting `ab cd` (with the browser check bypassed, e.g. by removing the `pattern` in devtools) shows the new error, keeps the nick in the field, and lets you retry without rescanning

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Start form hint and browser check

### Overview

Show the rule on the start form and add matching HTML validation, so most players never see the server error.

### Changes Required:

#### 1. Start form

**File**: `game/templates/game/home.html`

**Intent**: State the rule next to the field and stop over-long or badly-formed nicks in the browser.

**Contract**: The nick `<input>` gets `maxlength="12"`, `pattern="[A-Za-z0-9_]{1,12}"` and a `title` with the same wording as the hint (browsers show it in the validation popup). Add a short hint line under the label, such as "Letters, digits and _ · max 12". Link it with `aria-describedby` on the input. The existing `autocapitalize/autocorrect/autocomplete/spellcheck` attributes stay. Hardcode `maxlength` and `pattern` in the template (do not pass them from the view). The test below compares them with `services.NICK_MAX_CHARS` and `services.NICK_RE.pattern` so drift is caught.

#### 2. Hint styling

**File**: `game/static/game/game.css`

**Intent**: Style the hint as quiet helper text inside the `.start` form flex column, using the existing muted token.

**Contract**: One small rule (for example `.start .hint`) using `var(--muted)` and a smaller font size. No layout change to `.start`.

#### 3. Test

**File**: `game/tests/test_views.py`

**Contract**: Extend `test_home_renders_rules_and_nick_form` (or add a test) to assert that the home page contains `maxlength="{services.NICK_MAX_CHARS}"` and `pattern="{services.NICK_RE.pattern}"`.

### Success Criteria:

#### Automated Verification:

- Full suite passes: `uv run python manage.py test game challenges`
- Home page renders `maxlength="12"` and the nick `pattern`: covered by the extended `test_views` test

#### Manual Verification:

- On a phone-sized viewport, the hint is readable under the "Your nick" label and does not crowd the Start button
- Typing a 13th character is blocked. Submitting `ab-cd` shows the browser's validation popup with the rule text
- The ranking rows on `/staff/hall` show a 12-character nick in full, without an ellipsis

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- `start_game` accepts the boundary and edge cases: 12 chars, underscore-only, digits-only, mixed case, surrounding whitespace.
- `start_game` rejects: empty, whitespace-only, 13 chars, an inner space, hyphen, punctuation, HTML, Polish diacritics, a Unicode digit, an inner newline.

### Integration Tests:

- `POST /start` with a rule-breaking nick: 200, error text, nick echoed, token kept, no game.
- The bench command still creates and cleans up its games under the new prefix.
- The staff board still escapes an HTML-like nick that was stored directly.

### Manual Testing Steps:

1. `docker compose up`, open `/staff/hall`, then open the QR URL on a phone.
2. Start as `neo_42`. Expect `/play`.
3. In a fresh browser session, try `ab cd`, `zażółć`, `abc-def`. Expect the browser popup (Phase 2), or the server error if the `pattern` is removed in devtools (Phase 1).
4. Paste a 13-character nick. Expect the field to cut it to 12 characters.

## Migration Notes

None. There is no schema change. Existing nicks (up to 20 chars, any characters) stay as they are. Staff can hide any offensive nick through `/staff/moderate`, as before.

## References

- PRD: `context/foundation/prd.md` FR-002 (nick before start), FR-012 (hide nick = disqualification)
- Rule choke point: `game/services.py:81-84`
- Error re-render pattern: `game/views.py:115-121`, `game/tests/test_views.py:124-129`
- Similar regex constant: `CODE_RE` at `game/services.py:39`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Server-side nick rule

#### Automated

- [x] 1.1 Full suite passes: `uv run python manage.py test game challenges` — 0d98a4c
- [x] 1.2 New rule tests pass: `uv run python manage.py test game.tests.test_services game.tests.test_views` — 0d98a4c
- [x] 1.3 Bench still runs and cleans up: `uv run python manage.py test game.tests.test_bench` — 0d98a4c
- [x] 1.4 No old bench prefix left: `grep -rn "bench-{" game/` returns nothing — 0d98a4c

#### Manual

- [x] 1.5 With a valid QR token, starting as `neo_42` goes to `/play` — 0d98a4c
- [x] 1.6 Submitting `ab cd` (browser check bypassed) shows the new error, keeps the nick, and allows a retry without rescanning — 0d98a4c

### Phase 2: Start form hint and browser check

#### Automated

- [x] 2.1 Full suite passes: `uv run python manage.py test game challenges` — 355c927
- [x] 2.2 Home page renders `maxlength="12"` and the nick `pattern` — 355c927

#### Manual

- [ ] 2.3 On a phone-sized viewport, the hint is readable and does not crowd the Start button
- [ ] 2.4 A 13th character is blocked, and `ab-cd` shows the browser validation popup with the rule text
- [ ] 2.5 A 12-character nick shows in full in the `/staff/hall` ranking rows
