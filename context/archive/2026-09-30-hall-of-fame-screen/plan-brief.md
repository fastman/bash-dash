# Hall of Fame Screen with Nick Hiding — Plan Brief

> Full plan: `context/changes/hall-of-fame-screen/plan.md`

## What & Why

Booth staff need a big-screen ranking that refreshes itself and builds competition at the booth. It shows the top N games (place, nick, solved, attempts) and next to them the games that just finished, so every player sees their result for a moment (FR-010). Staff must also be able to pull an offensive or duplicate nick off the screen without deleting the result. Hiding counts as disqualification (FR-012).

## Starting Point

S-03 defined the ranking rule once, in `services.ranked_games()` / `rank_of()`, and that is the place reserved for a "hidden" filter. S-04 built the `/staff` area (`staff_member_required`, POST + PRG, phone-first templates). There is no hidden flag and no Hall of fame page. `/done` crashes with a 500 if `rank_of()` ever returns `None` for a finished game (the S-03 carry-over).

## Desired End State

A logged-in laptop shows `/staff/hall` on the booth monitor: two large columns, "Hall of fame" (top 10, ties share a place) and "Just finished" (last 5), refreshing every 5 s without a flash. It shows no prize codes and no times. From a phone, staff open `/staff/moderate` and tap "Hide" on a row. Within one refresh the nick is gone and everyone else's place moves up. A mistaken hide can be undone. The hidden player still sees their summary and code on `/done` ("not ranked"), and the prize desk sees "disqualified".

## Key Decisions Made

This was an unattended planning run with no interactive Q&A. Each choice below is the recommended option, grounded in the PRD, the tech stack, and the S-03/S-04 code and reviews. Review them before implementing.

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Hide granularity | Per game (`GameSession.hidden_at` timestamp), not per nick string | Nicks are not unique; a timestamp matches the `prize_given_at` precedent and records when. |
| Where disqualification applies | One filter in `ranked_games()`, plus the recent-list query | `/done`, the lookup and the Hall of fame all rank through it, so places and totals stay consistent everywhere. |
| Undo | Yes, "Unhide" on the moderation page | Hide buttons sit in a list on a phone, so a mis-tap is likely; restoring is one guarded UPDATE. |
| Where staff hide | A separate `/staff/moderate` phone page mirroring the screen | The booth monitor is public-facing, and staff don't know a troll's prize code, so hiding by lookup doesn't work. |
| Refresh mechanism | JS polling of a server-rendered board fragment (`/staff/hall/board`) | No flash, keeps the last board on network errors, and gives S-06's QR a stable slot; `tech-stack.md` already says polling. |
| Expired session on screen | Fragment returns 403 (not a login redirect); the screen shows "Session expired" | `fetch` would otherwise swap the login page into the board. |
| Defaults (PRD OQ 3) | Top 10, recent 5, refresh 5 s, via `BASHDASH_HALL_*` env vars | Fits one landscape screen and can be tuned during the event without a deploy. |
| Hidden player's `/done` | Summary and code as usual, Place "not ranked" | Fixes the 500 and does not provoke the troll; prize policy stays with staff. |
| Places on the board | One ordered pass over `ranked_games()`, test-pinned to equal `rank_of()` | One query per refresh, while the rule stays defined in a single place. |

## Scope

**In scope:**
- the `hidden_at` field and migration, hide/unhide services, and the `hall_of_fame()` service;
- the `/done` `None` fix, and the "disqualified" status on the lookup;
- `/staff/hall` with polling (`hall.js`) and big-screen CSS;
- `/staff/moderate` with hide/unhide;
- admin column and filter, settings, and tests.

**Out of scope:**
- the QR code and token (S-06); only an empty slot is left for it;
- hiding every game with a given nick, pre-moderation or profanity filters;
- controls on the big screen;
- showing solve time;
- websockets or caching;
- UI for changing N/K/refresh.

## Architecture / Approach

The rules stay in `game/services.py`: `ranked_games()` gains `hidden_at IS NULL`, and `hall_of_fame(top_n, recent_n)` returns `BoardRow`s (nick, solved, attempts, place) with no codes. `game/staff_views.py` gains `hall` (full page), `hall_board` (fragment, 403 on no auth), `moderate`, `hide` and `unhide`. One `_board.html` partial serves both the first render and each poll. `hall.js` fetches the fragment on a `setTimeout` chain and swaps `#board`.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Hidden flag and ranking rules | `hidden_at`, hide/unhide, `hall_of_fame()`, `/done` fix, lookup status, admin | One-pass places drifting from `rank_of` (a parity test guards it) |
| 2. Hall of fame screen | `/staff/hall` + polling fragment + big-screen CSS | Leaking prize codes onto the public screen (a test asserts none) |
| 3. Moderation | `/staff/moderate`, `POST /staff/hide` / `unhide`, lookup nav | A mis-tap hides a legit player (mitigated by Unhide) |

**Prerequisites:** S-03 and S-04 merged (done); the test suite green (170 tests, OK).
**Estimated effort:** ~1 session across 3 small phases.

## Open Risks & Assumptions

- The defaults (10 / 5 / 5 s) are guesses for PRD Open Question 3. They can be changed through env vars.
- A hidden player is not told they were disqualified. If staff want that shown, it is a template change.
- The display laptop must stay logged in and awake. This is operational and noted in Migration Notes.
- Unicode bidi or control characters in a nick could garble a row. This is handled reactively by hiding.
- Hiding is per game, so a troll who plays several times has to be hidden row by row.

## Success Criteria (Summary)

- The booth monitor shows a readable, self-refreshing top N and a "just finished" list, with no codes, times or page flashes.
- Staff can remove a nick from the screen in one tap on a phone, see it gone within about 5 s, and undo it.
- A hidden game has no place anywhere, and other places close the gap. The hidden player's `/done` and the prize desk keep working.
