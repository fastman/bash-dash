# Server-side Time Limit — Plan Brief

> Full plan: `context/changes/server-side-time-limit/plan.md`

## What & Why

This enforces the 5-minute game limit on the server (roadmap S-02; PRD FR-006, FR-007 and the Guardrail "the limit can't be extended or reset"). Without it, a result isn't fair: a reload, a phone clock change or a stale tab could buy extra time, and commands sent after time would still count.

## Starting Point

S-01 delivered the playable loop. `GameSession` records `started_at`, and the game is tied to the Django session cookie, so a reload already returns to the same game. There is no deadline, no countdown and no expiry yet. S-01's guarded counter update in `_record` was built so S-02 could reuse it.

## Desired End State

Each game has a fixed `deadline_at`. The player sees an `m:ss` countdown that survives reloads, backgrounded tabs and clock changes. At 0 the input locks and the page moves to `/done` ("Time's up!" or "All challenges solved!"). The server rejects commands that arrive after the deadline (409 `time_up`, not counted). A command sent just before the deadline still counts, even if its run finishes a few seconds later.

## Key Decisions Made

Made without live Q&A (background run). Each one is the ⭐ recommended default, and the reasoning is in the plan's "Decisions" section.

| Decision            | Choice                                                        | Why (1 sentence)                                                                           |
| ------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Deadline storage    | `deadline_at` column set at start from `GAME_DURATION_S`      | Frozen per game, and gives simple indexed queries for expiry and S-03 ranking.             |
| Cut-off rule        | **Sent-before**: a request received before the deadline counts | The PRD says commands *sent* after time don't count; a last-second paid run shouldn't vanish. |
| Expiry              | Lazy on every read, plus bulk `expire_overdue()`              | No worker or cron exists; one indexed UPDATE per request is negligible.                     |
| Timeout stamp       | `finished_at = deadline_at`                                   | The end time is the limit, not whenever someone next looked.                               |
| `current_slug`      | Kept on timeout                                               | Lets an in-flight solve be credited, and records where the player stopped.                  |
| Client timer        | Server `remaining_ms` plus `performance.now()`, resynced per response and via `GET /play/state` when the tab becomes visible | Immune to phone clock changes. The resync covers suspended tabs, where `performance.now()` can pause. |
| Late command        | New 409 `time_up` / "Time's up.", with no sandbox run         | Distinct from `finished`, and saves sandbox capacity.                                      |
| Grace-solve times   | `last_solved_at` / `finished_at` capped at `deadline_at`      | S-03 tie-breaks never see times past the limit.                                            |
| Tests               | Backdate `deadline_at` in the DB; race via `run_command` side effect | Matches existing test style, with no time mocking.                                  |

## Scope

**In scope:** `deadline_at` plus migration and backfill, the `GAME_DURATION_S` setting (env `BASHDASH_GAME_DURATION_S`), lazy and bulk expiry, the sent-before cut-off, `remaining_ms` in the play page and command JSON, the countdown JS with low-time cue, end-of-game lock and a `GET /play/state` resync, the reason heading on `/done`, the rules text taken from the setting, and the admin column.

**Out of scope:** a background sweeper, the full summary, rank and prize code (S-03), cross-browser resume, extending or pausing time, refunding latency, the soft block on a second game (FR-016), and JS test infrastructure.

## Architecture / Approach

The service layer owns time. `start_game` stamps the deadline from the same instant as `started_at` (which moves from `auto_now_add` to `default=timezone.now`). `GameSession.timed_out` and a matching query condition define "the clock ended this game" once. `expire_overdue()` is a single UPDATE that sets `finished_at = deadline_at` on overdue unfinished games. Views call it for the session's game on every request, and `submit_command` calls it at entry and again after recording. Fully solved games answer `finished` first. Then the entry check (`now >= deadline_at` → `time_up`) enforces "sent after doesn't count". `_record`'s guard is widened so a sent-before run on an already-expired game still counts, and the solve update never clears an existing `finished_at`. The client displays `remaining_ms` against a monotonic clock and defers to the server on every response.

## Phases at a Glance

| Phase                                   | What it delivers                                                        | Key risk                                                                      |
| --------------------------------------- | ----------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| 1. Server-side deadline and enforcement | Limit fully enforced; `time_up` responses; `remaining_ms` in JSON; tests | The solve update un-finishing a timed-out game (explicitly guarded and tested) |
| 2. Countdown and end-of-game UX         | Visible timer, reload-safe; lock at 0; "Time's up!" on `/done`          | Mobile tab suspension and clock skew (server resync on return, plus ~1 s buffer)        |

**Prerequisites:** S-01 merged (done). The baseline 53 game tests are green.
**Estimated effort:** about 1 session, 2 phases.

## Open Risks & Assumptions

- The sent-before rule lets a run finish up to about 16 s after the deadline (10 s queue plus 6 s run). This is judged fair. Switch to recorded-before if the stricter reading is preferred, which simplifies `_record`.
- The client redirect at 0 may briefly bounce `/done` → `/play` if the phone is ahead of the server by more than the ~1 s buffer. This is self-correcting and cosmetic.
- Games abandoned mid-play stay unfinished in the DB until something reads them. S-03 and S-05 must call `expire_overdue()` before ranking.
- The decisions were not confirmed interactively. Review the Decisions table before implementing.

## Success Criteria (Summary)

- No way for a player to get more than 5 minutes: reloads, clock changes and stale tabs all fail, and late commands are never counted.
- The player always sees an accurate countdown, and the game ends cleanly on `/done` with the reason.
- `uv run python manage.py test game challenges` is green, with the time rules covered by tests.
