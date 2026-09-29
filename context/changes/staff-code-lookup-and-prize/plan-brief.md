# Staff Code Lookup and Prize Issuing — Plan Brief

> Full plan: `context/changes/staff-code-lookup-and-prize/plan.md`

## What & Why

Booth staff need to check a player's 6-digit code and hand out a prize exactly once (FR-011, FR-013). This is the PRD's primary success criterion: "every issued code can be verified at the booth". Without a "prize given" mark, the same person can collect twice.

## Starting Point

S-03 gives every game a unique 6-digit `code` and a single ranking rule (`services.rank_of` → `(place, total)` or `None`). Staff can only find a code through the read-only Django admin search. There is no staff page and no prize flag.

## Desired End State

A logged-in staff member opens `/staff/` on a phone and types the code. One card then shows the nick, solved, attempts, place, solve time, and when the game finished, plus a big "Mark prize given" button. A second press, or a second lookup, shows "Prize already given N minutes ago" instead of the button. Games still in progress cannot get a prize. Anonymous and non-staff users are sent to the admin login.

## Key Decisions Made

These were decided in an unattended planning run (no interactive Q&A), grounded in the PRD, the tech stack, and the code. Review them before implementing.

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Staff UI | A custom `/staff/` page (the admin stays read-only as a backup) | An admin action (search → tick → action → Go) cannot show the result and an "already given" warning on one phone screen before the click; S-05 reuses the `staff/` space. |
| Auth | `staff_member_required` plus the existing admin login | Password login for free; no custom login page. |
| Prize flag | `prize_given_at` nullable datetime | The warning can say *when*; one field, no backfill. |
| Double-issue guard | One conditional `UPDATE … WHERE prize_given_at IS NULL AND finished_at IS NOT NULL` | Safe when two staff devices press at once; no read-modify-write. |
| Unfinished games | Lookup shows "Game in progress"; the prize is refused | The result isn't final yet; overdue games are expired first. |
| Undo | None in the UI; the operator clears it from the shell | Mistakes are rare, and the PRD keeps corrections out of the panel. |
| "Time" in FR-011 | Solve time `m:ss` + "finished N min ago" | The server runs in UTC, so relative times avoid wrong clock readings at the booth. |
| Hidden nick (S-05) | `rank_of → None` shows "not ranked"; the prize is still allowed | The page stays forward-compatible, and prize policy stays with the staff. |

## Scope

**In scope:** the `prize_given_at` field + migration; `normalize_code` / `find_by_code` / `mark_prize_given` / `solve_time` in services; admin column + filter; `/staff/` lookup and `/staff/prize` POST; template + CSS; service and view tests.

**Out of scope:** nick hiding and the Hall of fame (S-05); undo in the UI; recording which staff member gave the prize; prize tiers by place (OQ 2); editing results; a writable admin; showing prize status to the player.

## Architecture / Approach

Rules go in `game/services.py` (the module that "knows the rules"). A new `game/staff_views.py` holds thin, staff-only views, routed under `staff/` in `game/urls.py`. They render `game/staff/lookup.html` on the existing `base.html` and CSS tokens. The prize button is a POST that follows Post/Redirect/Get back to `?code=…` and shows the outcome through `django.contrib.messages`.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Prize flag and staff rules | Field, migration, services, admin column; unit tests | Forgetting to expire overdue games before marking |
| 2. Staff lookup page | `/staff/` page, prize POST, template, CSS; view tests | Access control or CSRF gaps; phone layout at 320 px |

**Prerequisites:** S-03 merged (done). Baseline: 149 tests green.
**Estimated effort:** about 1 session, 2 small phases.

## Open Risks & Assumptions

- The custom page departs from `tech-stack.md`'s "admin covers FR-011–013". If you'd rather use admin-only (an action plus a `prize_given_at` column), Phase 2 shrinks to an admin action.
- The booth staff share a staff account created with `createsuperuser` on the event VM (an operational step, not code).
- Nobody has decided whether prizes depend on place (PRD OQ 2). The mark is the same for every prize.

## Success Criteria (Summary)

- Staff can find any issued code on a phone and see the same numbers the player saw on `/done`.
- A prize can be marked once per code; a second attempt is clearly refused.
- Nobody without a staff login can see game data through `/staff/`.
