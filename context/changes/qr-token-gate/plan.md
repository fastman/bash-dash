# QR Token Gate Implementation Plan

## Overview

A player can only start a game after scanning the current, rotating QR code on the booth's Hall of fame screen (FR-001, FR-017). The QR encodes `/?t=<token>`. The token is a server-signed issue time. It lets a player **start** a game for a staff-set time after it was issued (default 15 min; `0` = never expires). A missing, tampered or expired token gets a "Scan the QR code at the booth" refusal page (HTTP 403) instead of the start form. A game that has already started is never affected by the gate. It runs its full 5 minutes and survives refreshes, as before.

## Current State Analysis

- `views.home` (`game/views.py:84-90`) renders the rules and nick form for anyone without a game in the session. `views.start` (`game/views.py:92-106`) creates a game from any POST with a valid nick. Nothing checks where the player came from.
- Both views first call `_session_game()` and redirect a player who already has a game to `/play` or `/done` (`_redirect_existing`, `game/views.py:80`). Resume after refresh (FR-006) depends on this ordering.
- `services.start_game(nick)` (`game/services.py:76`) is also called directly by `bench_game` (`game/management/commands/bench_game.py:62`) and by `game/tests/test_integration.py:21`. A gate at the view level leaves both unaffected.
- S-05 left an empty `{% block qr %}` slot in `game/templates/game/staff/hall.html:10`, outside the polled `#board`. `hall.js` swaps `#board`'s innerHTML with `/staff/hall/board` every `HALL_REFRESH_S` (5 s). That endpoint returns 403 (not a login redirect) when the staff session has expired (`staff_views.hall_board`, `game/staff_views.py:74-79`).
- `/staff/moderate` (`game/templates/game/staff/moderate.html`) is the phone-sized control page for the screen. It uses POST + CSRF + `messages` + Post/Redirect/Get, the house pattern for staff mutations (`staff_views._toggle`).
- Settings follow the `BASHDASH_*` env var pattern (`config/settings.py:143-152`). No setting can be changed at runtime yet. The PRD requires staff (not the operator) to set the token TTL.
- No QR library is installed (`pyproject.toml`: django, docker, pyyaml). There is no JS build step, and the booth screen should not depend on a CDN.
- F-02 (public HTTPS deploy behind a proxy) is not done, so `request.build_absolute_uri()` may produce `http://` or an internal host behind the future reverse proxy.
- UI copy is English. Baseline: `uv run python manage.py test game challenges` → 196 tests, OK.

## Desired End State

- `GET /?t=<valid token>` shows the rules and nick form. The token travels in a hidden form field, and `POST /start` re-checks it (authoritative), so a token that expires between scanning and "Start" is refused.
- `GET /` or `POST /start` with a missing, malformed, tampered or expired token (and no game in the session) returns **403** with a page that says "Scan the QR code at the booth to play". An expired token adds "That code has expired." No game is created.
- A player who already has a game in the session is redirected to `/play` or `/done` exactly as today, with or without a token.
- `/staff/hall` shows a large QR next to the ranking. It rotates to a new token every `START_TOKEN_ROTATE_S` (default 60 s) through the existing board poll, with no page flash. The QR URL uses `BASHDASH_PUBLIC_URL` when set.
- `/staff/moderate` has a "Start QR" section. It shows the current token lifetime in minutes, with a form to change it (0, or 2–1440 minutes). Saving applies immediately to every token, including ones already issued. When set to 0, the page shows a warning that QR codes never expire.
- The TTL is stored in the database (single-row `GateSettings`), so it survives restarts and the off-VM backup. `BASHDASH_START_TOKEN_TTL_S` (default 900) only seeds the first row.

Verify: the test suite is green. Then run locally: open `/staff/hall`, scan the QR with a phone (or open its URL), start a game; set the TTL to 2 min, wait until an old token is over 2 min old, and confirm it is refused (see Manual Testing Steps).

### Key Discoveries:

- The gate must run **after** `_session_game()` in both `home` and `start`. Otherwise a refresh of `/` mid-game (without the token in the URL) would show the refusal page instead of resuming (`game/views.py:84-100`).
- A signed issue time (Django `signing.Signer` over an epoch timestamp) needs no token table. Its age is checked against the **current** TTL, so a staff change applies retroactively. Setting the TTL back to 15 min after running with 0 also invalidates every old, possibly leaked, token.
- Bucketing the issue time to the rotation period makes the token (and the SVG) identical for every poll within one period. The 5 s board swap then changes nothing visible until the period rolls over.
- The QR can ride inside the `/staff/hall/board` fragment. It inherits staff-only access, `never_cache`, the 403 → "Session expired" handling and "keep last board on failure" from S-05 with no JS change. The empty `{% block qr %}` slot is then removed.

## What We're NOT Doing

- Single-use or per-player tokens. Everyone at the booth scans the same code.
- A token-less fallback. With TTL 0, a token is still required, but any token ever shown keeps working (a phone photo of the screen can serve as a stand-in QR if the screen dies).
- Soft-blocking a second game from the same browser (FR-016, parked).
- Showing the token lifetime, a countdown or the raw URL on the public screen.
- Staff-editable rotation period, board size or refresh rate (these stay env settings for the operator).
- Rotating or revoking the signing secret (`SECRET_KEY` handling belongs to F-02).
- Reverse-proxy settings (`SECURE_PROXY_SSL_HEADER`, `ALLOWED_HOSTS`). `BASHDASH_PUBLIC_URL` covers the QR URL until F-02 does this.
- A printable QR page or QR on the staff lookup page.

## Implementation Approach

Two phases, following the house pattern: rules in `game/services.py`, thin views, staff pages in `game/staff_views.py`.

1. **Token rules and the player gate.** Add the `GateSettings` row and migration, plus services that issue a token for "now" and check a token against the current TTL. Gate `home` and `start` behind the check (after the existing resume redirect) and add the refusal template. All of this is testable before any QR exists: tests mint tokens through the service.
2. **QR on the screen and the staff TTL control.** Add `segno`, render the current token's URL as inline SVG in the board fragment, and style it for the big screen. Add the "Start QR" section with a POST form on `/staff/moderate`.

The TTL is checked at `POST /start`, not only when the QR is scanned. The PRD says a token lets a player *start* a game for about 15 min. Because the displayed token is at most one rotation period old, a scanner has at least `TTL − rotation` (about 14 min by default) to type a nick. Checking at the POST is the only check a player cannot skip by keeping an old form open.

## Critical Implementation Details

- **Order in the views.** `home` and `start`: (1) `_session_game()` → redirect if a game exists; (2) check the token → 403 refusal page if not valid; (3) the existing behaviour. A nick validation error on `start` re-renders the form with the same `t`, so the player does not have to rescan.
- **Deterministic token per rotation period.** Issue time = `floor(now_epoch / START_TOKEN_ROTATE_S) * START_TOKEN_ROTATE_S`, signed with `signing.Signer(salt='game.start-token')` (keyword args only in Django 6). Do not use `TimestampSigner`: it stamps the current second, so the QR would change on every 5 s poll. Check it with `unsign()`, parse an int, and compute `age = now_epoch − issued`. Use `now_epoch = int((now or timezone.now()).timestamp())`, the `services` clock convention, so that tests which mock `timezone.now` or pass `now` control both issuing and checking. Do not use `time.time()`. Treat `age < −START_TOKEN_ROTATE_S` (issued in the future) as invalid. With TTL > 0, treat `age > ttl` as expired.
- **TTL floor.** Staff input is limited to 0 or ≥ 2 min so that, with the 60 s default rotation, a freshly displayed token always has at least 1 min of life. If the operator raises `BASHDASH_START_TOKEN_ROTATE_S`, they must keep it at most half the smallest TTL staff will use. Note this next to the setting.

## Phase 1: Token rules and player gate

### Overview

Tokens can be issued and checked, the lifetime is stored in the DB, and the player start flow refuses anyone without a valid token, while leaving games in progress untouched.

### Changes Required:

#### 1. Settings

**File**: `config/settings.py`

**Intent**: Add the gate's operator settings under a new "QR start gate (S-06)" block, following the `BASHDASH_*` pattern.

**Contract**: `START_TOKEN_TTL_S = max(0, int(env BASHDASH_START_TOKEN_TTL_S, 900))`, which only seeds `GateSettings`; `START_TOKEN_ROTATE_S = max(10, int(env BASHDASH_START_TOKEN_ROTATE_S, 60))`, with a comment that it must be at most half the smallest TTL in use; `PUBLIC_BASE_URL = env BASHDASH_PUBLIC_URL` with the trailing `/` stripped, default `''` (used in Phase 2).

#### 2. Gate settings model and migration

**File**: `game/models.py`, `game/migrations/0006_gatesettings.py`

**Intent**: Store the staff-editable token lifetime so it survives restarts and backups.

**Contract**: `class GateSettings(models.Model)` with `token_ttl_s = PositiveIntegerField()` (0 = never expires) and `updated_at = DateTimeField(auto_now=True)`. A single row, `pk=1`. The docstring states the singleton convention. Generate the migration with `makemigrations` (next free number: 0006).

#### 3. Token services

**File**: `game/services.py`

**Intent**: One place that knows the gate rules: the current TTL, issuing the token shown on the screen, and checking a token a player brings.

**Contract**:
- `gate_settings() -> GateSettings`: `get_or_create(pk=1, defaults={'token_ttl_s': settings.START_TOKEN_TTL_S})`.
- `set_token_ttl(ttl_s: int) -> GateSettings`: raises `ValueError` unless `ttl_s == 0` or `TOKEN_TTL_MIN_S (120) <= ttl_s <= TOKEN_TTL_MAX_S (86400)`.
- `issue_start_token(now=None) -> str`: the signed, bucketed issue time (see Critical Implementation Details).
- `check_start_token(token: str | None, now=None) -> str`: returns one of the new constants `TOKEN_OK`, `TOKEN_MISSING` (None/empty), `TOKEN_INVALID` (bad signature, non-int, from the future), `TOKEN_EXPIRED`. It never raises on user input (it catches `signing.BadSignature` and `ValueError`).

#### 4. Gate in the player views

**File**: `game/views.py`

**Intent**: Refuse `home` and `start` without a valid token, after the resume redirect. Carry the token from the URL into the form.

**Contract**:
- `home`: read `request.GET['t']`. If the check is not `TOKEN_OK`, render `game/gate.html` with status 403 and `expired=(status == TOKEN_EXPIRED)`. Otherwise render `home.html` with `token` in the context.
- `start`: read `request.POST['t']`. Apply the same refusal (no game created). On a nick error, re-render `home.html` with the same `token`.
- A small helper (e.g. `_gate_refusal(request, status)`) keeps both views to a few lines.

#### 5. Templates

**File**: `game/templates/game/home.html`, `game/templates/game/gate.html` (new)

**Intent**: The start form posts the token back. The refusal page tells the player what to do and shows no start form.

**Contract**: `home.html` adds `<input type="hidden" name="t" value="{{ token }}">` inside the form. `gate.html` extends `base.html`: heading "Scan the QR code at the booth to play". When `expired`, it adds "That code has expired." It has no links and no form, and fits 320 px using the existing CSS.

#### 6. Tests

**File**: `game/tests/test_services.py`, `game/tests/test_views.py`

**Intent**: Cover the token rules at the service level and the gate at the view level. Keep the existing view tests working by minting a token in the helper.

**Contract**:
- `ViewTestCase.start(nick)` posts `t=services.issue_start_token()`. `test_home_renders_rules_and_nick_form` requests `/?t=<token>`.
- Other existing tests that reach `/` or `/start` without a token and must be updated (they break under the gate):
  - `test_views.py` `PlayTests.test_play_without_game_redirects_home` and `SummaryTests.test_done_redirects_still_hold`. `assertRedirects(..., reverse('game:home'))` fetches `/` and expects 200, but it now gets 403. Pass `fetch_redirect_response=False`.
  - `test_views.py` `test_home_duration_follows_setting` and `NoAnswerLinksTests.test_pages_contain_no_external_links` should GET `/?t=<token>`. Also keep the tokenless gate page in the no-external-links list.
  - `test_views.py` `DockerDownTests.setUp` and `test_staff_views.py` `test_disqualification_end_to_end_on_done` post `/start` directly. Add `'t': services.issue_start_token()`.
- Service tests (with an injected `now`): a fresh token is `TOKEN_OK`; the same period gives an identical token and the next period a different one; `ttl + 1` s old → `TOKEN_EXPIRED`; exactly `ttl` old → OK; TTL 0 → a very old token is OK; a tampered signature, a garbage string, `None` or `''` give `TOKEN_INVALID` or `TOKEN_MISSING`; a future issue time → `TOKEN_INVALID`; lowering the TTL expires an already-issued token (retroactive); `set_token_ttl` rejects 1, 119, 86401 and −1, and accepts 0, 120 and 86400; `gate_settings()` seeds from `START_TOKEN_TTL_S` (`override_settings`).
- View tests: `GET /` without `t` → 403 with the scan message, no nick field; expired `t` → 403 with "expired"; valid `t` → 200 with a hidden `t` field; `POST /start` without, or with an expired, `t` → 403 and `GameSession.objects.count() == 0`; a token valid at `GET /` but expired by the POST (mock `timezone.now`) → 403; nick error with a valid `t` → 200, the error shown and `t` preserved; a player with an active game hitting `/` or `/start` with no token → still redirected to `/play` (resume unaffected); a finished game → `/done`.

### Success Criteria:

#### Automated Verification:

- Game and challenge tests pass: `uv run python manage.py test game challenges`
- Django checks pass: `uv run python manage.py check`
- No missing migrations: `uv run python manage.py makemigrations --check --dry-run`
- Migration applies to the existing dev DB: `uv run python manage.py migrate`

#### Manual Verification:

- `/` in a phone-sized browser without a token shows the scan message (no form) and fits 320 px
- `/?t=<token from manage.py shell>` shows the form; Start begins a game; refreshing `/` mid-game (without the token) resumes `/play`

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: QR on the Hall of fame screen and staff TTL control

### Overview

The big screen shows a scannable, rotating QR. Staff can change the token lifetime from their phone.

### Changes Required:

#### 1. Dependency

**File**: `pyproject.toml`, `uv.lock`

**Intent**: Add `segno` (pure Python QR encoder, no dependencies) so the QR renders server-side as SVG with no CDN or JS library.

**Contract**: `uv add segno`.

#### 2. QR rendering service

**File**: `game/services.py` (the tests below reference `services.start_url` and `services.qr_svg`)

**Intent**: Build the absolute start URL for the current token and render it as inline SVG.

**Contract**: `start_url(request, token) -> str` gives `f'{settings.PUBLIC_BASE_URL}{reverse("game:home")}?t={quote(token)}'` when `PUBLIC_BASE_URL` is set, and otherwise `request.build_absolute_uri(...)`. `qr_svg(url) -> str` gives `segno.make(url, error='m').svg_inline(omitsize=True, border=2, dark=…, light='#fff')`. Use dark on white regardless of the page theme, because scanners need contrast. `omitsize=True` gives a `viewBox`-only SVG that CSS can size.

#### 3. Board fragment and hall page

**File**: `game/staff_views.py`, `game/templates/game/staff/_board.html`, `game/templates/game/staff/hall.html`, `game/static/game/game.css`

**Intent**: Put the QR into the polled board, so it rotates through the existing 5 s poll and inherits its auth and error handling. Remove the unused S-05 slot.

**Contract**:
- `_board_context()` stays as it is, because `moderate` uses it and needs no QR. A new `_hall_context(request)` returns `_board_context()` plus `qr_svg` (from `issue_start_token()` → `start_url` → `qr_svg`). `hall` and `hall_board` use `_hall_context(request)`.
- `_board.html` adds a `<section class="hall-qr">` with the SVG (`|safe`, since we generated it) and a caption "Scan to play". The moderation page includes a different template, so it is unaffected.
- `hall.html`: remove `{% block qr %}{% endblock %}`.
- CSS: `#board` becomes a three-column grid (ranking, recent, QR), or the QR sits at the top of the recent column. The implementer picks whichever fits 1366×768 without scrolling. The QR is at least ~35 vh tall, on a white tile with a quiet zone. Below 900 px it stacks like the existing columns.
- `hall.js` is unchanged.

#### 4. Staff TTL control

**File**: `game/staff_views.py`, `game/urls.py`, `game/templates/game/staff/moderate.html`, `game/static/game/game.css`

**Intent**: Let staff see and change the token lifetime from their phone.

**Contract**:
- `moderate` context gains `token_ttl_min` (the current TTL ÷ 60) and `token_never_expires`.
- A new `staff_views.set_token_ttl`: `@staff_member_required @require_POST`, route `staff/token-ttl` (name `staff_token_ttl`). It parses `minutes` as an int and calls `services.set_token_ttl(minutes * 60)`. On success it shows `messages.success('QR codes now expire after N min.')`, or `'QR codes now never expire.'` for 0. On a non-integer or out-of-range value it shows `messages.error('Enter 0 or 2–1440 minutes.')`. It then redirects to `staff_moderate` (PRG).
- `moderate.html`: a "Start QR" section at the top with `<input type="number" name="minutes" min="0" max="1440" inputmode="numeric">` pre-filled, a hint "0 = never expires", and a Save button. When the TTL is 0 it shows a persistent `.notice-warn` line: "QR codes never expire — anyone with an old code or photo can start a game." It fits 320 px.

#### 5. Tests

**File**: `game/tests/test_staff_views.py`, `game/tests/test_services.py`

**Contract**:
- `/staff/hall` and `/staff/hall/board` contain an `<svg` and "Scan to play". The embedded URL is not shown as text, but a start URL built for the current token is (checked via `services.start_url` + `issue_start_token`) and passes `check_start_token` → OK. Two board fetches in the same rotation period (mocked `now`) return an identical QR; the next period returns a different one. With `override_settings(PUBLIC_BASE_URL='https://dash.example')` the URL starts with it. The board still contains no prize codes (existing test stays green).
- Anonymous or non-staff requests to `/staff/hall/board` still get 403 (so the QR is never exposed without login).
- `POST /staff/token-ttl`: `minutes=5` → TTL 300 and a success message; `0` → TTL 0 and "never expire"; `1`, `abc`, `-3` and `1441` → an error and the TTL unchanged; anonymous → login redirect; no CSRF token → 403; GET → 405.
- `/staff/moderate` shows the current minutes. With TTL 0 it shows the warning.
- `qr_svg` returns a string starting with `<svg` that contains `viewBox`.

### Success Criteria:

#### Automated Verification:

- Game and challenge tests pass: `uv run python manage.py test game challenges`
- Django checks pass: `uv run python manage.py check`
- No missing migrations: `uv run python manage.py makemigrations --check --dry-run`
- Lockfile is in sync: `uv lock --check`

#### Manual Verification:

- QR on `/staff/hall` scans from ~1.5 m with an Android and an iOS phone camera and opens the start form
- Hall layout fits 1920×1080 and 1366×768 without scrolling; QR changes about once a minute without a flash
- Setting TTL to 2 min on `/staff/moderate` makes a token scanned >2 min earlier show "That code has expired"; setting 0 shows the warning and the old token works again
- Moderation page with the "Start QR" section fits 360 px and 320 px

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- Token issue and check with an injected `now`: boundaries at `ttl` and `ttl + 1`, TTL 0, tampering, garbage, future issue time, retroactive TTL change, determinism within a rotation period.
- TTL validation bounds (0, 119, 120, 86400, 86401, negative).

### Integration Tests:

- View-level gate: 403 refusal without, or with an expired, token on both `GET /` and `POST /start`; no game created; resume redirects unaffected; expiry between GET and POST refused.
- Staff: QR present only behind staff auth, rotates per period, honours `PUBLIC_BASE_URL`; the TTL form is validated, PRG, CSRF-protected.

### Manual Testing Steps:

1. `uv run python manage.py runserver 0.0.0.0:8000` with `BASHDASH_PUBLIC_URL=http://<LAN IP>:8000` and `BASHDASH_ALLOWED_HOSTS=<LAN IP>`. Log in as staff and open `/staff/hall` on a laptop.
2. Scan the QR with a phone on the same network. The start form appears. Enter a nick and play. Refresh mid-game and confirm it resumes.
3. On a second phone, open `/` without a token. The scan message appears.
4. On `/staff/moderate`, set 2 min. Reuse the URL from step 2 in a private tab after 2+ min. It shows "That code has expired". Set 0: the warning appears and the same URL now shows the form. Set back to 15.
5. Stop the server for 10 s. The hall keeps the last QR and shows "Reconnecting…", then recovers.

## Performance Considerations

Each board poll signs one string and encodes one small QR (about version 5–6), well under a millisecond, and reads the `GateSettings` row once per start or landing. There is only one screen, so this adds no meaningful load.

## Migration Notes

`0006_gatesettings` only adds a table. The row is created lazily on first use with `START_TOKEN_TTL_S`, so there is no data migration. Rollback: revert the code and migrate back to `0005`. Games are unaffected.

## References

- Roadmap slice: `context/foundation/roadmap.md` (S-06), PRD FR-001, FR-017, Access Control
- S-05 plan (QR slot, polling, 403 contract): `context/archive/2026-09-30-hall-of-fame-screen/plan.md`
- Start flow: `game/views.py:80-106`; staff PRG pattern: `game/staff_views.py:89-113`
- segno inline SVG: `/heuer/segno` docs (`svg_inline`, `omitsize`)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Token rules and player gate

#### Automated

- [x] 1.1 Game and challenge tests pass: `uv run python manage.py test game challenges` — d496cc0
- [x] 1.2 Django checks pass: `uv run python manage.py check` — d496cc0
- [x] 1.3 No missing migrations: `uv run python manage.py makemigrations --check --dry-run` — d496cc0
- [x] 1.4 Migration applies to the existing dev DB: `uv run python manage.py migrate` — d496cc0

#### Manual

- [ ] 1.5 `/` without a token shows the scan message (no form) and fits 320 px
- [ ] 1.6 `/?t=<token>` shows the form; Start begins a game; refreshing `/` mid-game resumes `/play`

### Phase 2: QR on the Hall of fame screen and staff TTL control

#### Automated

- [x] 2.1 Game and challenge tests pass: `uv run python manage.py test game challenges` — 6feae38
- [x] 2.2 Django checks pass: `uv run python manage.py check` — 6feae38
- [x] 2.3 No missing migrations: `uv run python manage.py makemigrations --check --dry-run` — 6feae38
- [x] 2.4 Lockfile is in sync: `uv lock --check` — 6feae38

#### Manual

- [ ] 2.5 QR scans from ~1.5 m with Android and iOS cameras and opens the start form
- [ ] 2.6 Hall layout fits 1920×1080 and 1366×768; QR rotates about once a minute without a flash
- [ ] 2.7 TTL 2 min expires an older token; TTL 0 shows the warning and switches to one fixed code (older rotating codes stop working)
- [ ] 2.8 Moderation page with "Start QR" fits 360 px and 320 px
