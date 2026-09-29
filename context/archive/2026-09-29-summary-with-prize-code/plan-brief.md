# Summary with Prize Code — Plan Brief

> Full plan: `context/changes/summary-with-prize-code/plan.md`

## What & Why

When the game ends, the player sees their result: challenges solved, attempts, their place in the ranking and a unique 6-digit code to claim a prize at the booth (FR-008). This closes the player's loop. It also adds the ranking rule (solved ↓, attempts ↑, time to last solve ↑) that S-04 staff lookup and S-05 Hall of fame reuse.

## Starting Point

`GameSession` already stores every ranking input (`solved`, `attempts`, `started_at`, `last_solved_at` capped at the deadline, `finished_at`), and S-02 added `expire_overdue()` for finishing abandoned games in bulk. `/done` is a placeholder that shows only a heading, `solved / total` and attempts. There is no prize code and no ranking.

## Desired End State

Every game gets a DB-unique 6-digit code when it starts. On `/done`, a finished player sees Solved `X / total`, Attempts `N`, Place `#R of M` and their code, large on a phone screen, with "show this at the booth". The place is recomputed live on each load, and staff can already search codes in the read-only admin.

## Key Decisions Made

All of these are the recommended defaults. This session ran as a background job with no interactive Q&A, so each one is open to a veto before implementation.

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| When the code is assigned | At game start (`start_game`) | Games finish in 3+ code paths, including a bulk `UPDATE` that cannot give each row a distinct random value; start has one path. |
| Code format and uniqueness | `CharField(6)`, zero-padded, `unique=True`, random via `secrets`, retry up to 10 times on `IntegrityError` | Staff identify players only by code, so uniqueness is enforced by the DB, not by luck. |
| Who is ranked | Finished games only, after a bulk `expire_overdue()` | Players still playing don't have a final score; abandoned overdue games do. |
| Ties | Competition ranking (1, 2, 2, 4); 0-solved players tie on attempts only | Equal on every PRD key means the same place, and a 0-solved player has no solve time. |
| Live vs frozen place | Live, recomputed on each `/done` load, with a note that it can change | The PRD accepted a changing place; freezing would disagree with S-04 and S-05. |
| Where the rule lives | `ranked_games()` + `rank_of()` in `game/services.py` | One definition for S-03, S-04 and S-05; S-05 adds its "hidden" filter there. |
| Solve time on summary | Not shown | PRD: time is only a tie-break. |
| Admin | Add `code` to list and search (read-only) | A zero-cost stopgap for staff until S-04. |

## Scope

**In scope:**
- `GameSession.code` + migration 0003 with a backfill for existing rows
- Code generation with a collision retry in `start_game`
- `ranked_games()` / `rank_of()` implementing the PRD rule
- The rebuilt `/done` template and CSS for the code
- Admin code column and search
- Service and view tests

**Out of scope:** staff lookup and "prize given" (S-04), Hall of fame and hiding nicks (S-05), freezing the place, auto-refresh, copy or QR for the code, anti-guessing measures, and any change to how games finish or attempts count.

## Architecture / Approach

The model gains `code`, generated in `start_game` inside a per-attempt savepoint so a collision can be retried safely. `services.ranked_games()` expires overdue games, keeps only finished ones, annotates `elapsed = last_solved_at − started_at` and orders by the PRD keys. `rank_of(game)` counts games that are strictly better, plus one, and gives the total. The `done` view adds place, total and code to the existing context. It was checked on SQLite that duration arithmetic works in both filter and order.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Unique prize code per game | `code` field, backfill migration, retrying generator, admin column | A one-step `AddField` with a callable default breaks uniqueness on existing rows (use the 0002 three-step pattern). |
| 2. Ranking and the summary page | `ranked_games` / `rank_of`, new `/done` page, tests | Forgetting the bulk expire before ranking undercounts abandoned games. |

**Prerequisites:** S-02 merged (done). The dev DB is behind on 0002, so `migrate` applies 0002 and 0003 together.
**Estimated effort:** ~1 session across 2 small phases.

## Open Risks & Assumptions

- All decisions above are assumed defaults (no live Q&A). The one most likely to be revisited is live vs frozen place.
- Prize rules are still open (PRD OQ 2). The plan assumes every finished player gets a code and a place, including those with 0 solved.
- S-05's "hidden" filter will change places after the fact. That is intended (disqualification).
- 6-digit codes can be guessed. Per PRD FR-011, staff also check the nick; no rate limiting is added here.

## Success Criteria (Summary)

- Every finished player sees solved, attempts, `#place of total` and a unique 6-digit code on their phone.
- Places follow the PRD rule, including ties, and include abandoned games once they are past their deadline.
- The code is never exposed outside `/done` (and admin), and no two games ever share one.
