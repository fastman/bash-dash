<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Summary with Prize Code Implementation Plan

- **Plan**: context/changes/summary-with-prize-code/plan.md
- **Mode**: Deep
- **Date**: 2026-09-29
- **Verdict**: SOUND
- **Findings**: 0 critical, 0 warnings, 5 observations

> **Triage note:** This review ran as a background job with no interactive channel. The reviewer (Claude) triaged every finding **without the user**, using conservative defaults:
> - The reviewer applied pure clarifications (line references, test mechanics, an implicit migration detail) to the plan.
> - The one scope/ops item (F3) is left **PENDING** for the user.
> - No assumed-default design decision from `plan-brief.md` was changed: code at start, live place, 0-solved tie rule, competition ranking, the ranking functions in `services.py`, and the admin stopgap.
>
> To revisit, run `/10x-plan-review context/changes/summary-with-prize-code/reviews/plan-review.md`.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | PASS (2 observations) |
| Plan Completeness | PASS (3 observations) |

## Grounding

- **Paths:** 6/6 ✓ (`game/models.py`, `game/services.py`, `game/views.py`, `game/admin.py`, `game/templates/game/done.html`, `game/static/game/game.css`). Also present: migration `0002` (house pattern) and `test_services.py` / `test_views.py`. `0003` does not exist yet, as expected.
- **Symbols:** 7/7 ✓ (`start_game`, `expire_overdue`, `TIMED_OUT_Q`, `GameSession.timed_out`, `_session_game`, `NoAnswerLinksTests`, `:root` CSS tokens).
- **Brief↔plan:** ✓. Phases, decisions and scope match. The brief says "3+ finish paths" and the plan lists four; these are consistent.
- **Progress↔Phase:** ✓. Items 1.1–1.5 and 2.1–2.7 match the Success Criteria one to one, and there are no checkboxes outside Progress.
- **Contract surfaces:** skipped (`docs/reference/contract-surfaces.md` is absent).
- **Lessons:** none (`context/foundation/lessons.md` is absent).

### Deep verification (riskiest claims, run directly; the codebase is small)

1. **The SQLite ranking query works (`elapsed` in `order_by` and `filter(elapsed__lt=…)`, competition ranks, NULL-elapsed ties): CONFIRMED.**
   - Method: an in-memory SQLite DB with all migrations applied and 7 synthetic finished games.
   - Places came out 1, 2, 2, 4, 5, 6, 6 of 7. The 0-solved games ordered by attempts only, and NULL `elapsed` never won a tie.
2. **The dev DB is behind on 0002 and holds existing games: CONFIRMED.** `showmigrations` shows 0002 unapplied, and the DB has 3 rows. So step 1.4 exercises the backfill for real.
3. **`solved > 0` ⇔ `last_solved_at IS NOT NULL`, and the cut-finish path never sets `last_solved_at`: CONFIRMED.**
   - `last_solved_at` is written only in `_record` (services.py:189-194).
   - The cut path (services.py:117-118) sets only `current_slug` and `finished_at`.
4. **`start_game` is the only creation path: CONFIRMED.** The only callers are the `start` view, `bench_game` and tests. No production code calls `GameSession.objects.create` directly.
5. **Blast radius:** `done.html` is rendered only by `views.done`. `/done` is a plain server-rendered page (`play.js:45` navigates to it), so no JS change is needed. `NoAnswerLinksTests` already covers `/done`.

## Findings

### F1: Stale line references in Current State Analysis and References

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW (quick decision; the fix is obvious and narrowly scoped)
- **Dimension**: Plan Completeness
- **Location**: Current State Analysis; References
- **Detail**: Several line references had drifted:

  | Reference | Plan said | Actual |
  |---|---|---|
  | `_record` | `services.py:176-206` | 164-195 |
  | `Least(...)` | `:197` | 188 |
  | cut-finish | `:120-122` | 117-118 |
  | `expire_overdue` | `:86-92` | 85-91 |
  | `done` view | `views.py:189-202` | 175-188 |
  | `GameSession` | `models.py:7-35` | 7-36 |

  The claims themselves are correct; only the numbers had drifted.
- **Fix**: Update the line numbers.
- **Decision**: FIXED (auto-triaged without the user; line numbers corrected in plan.md)

### F2: Migration step 1 must not carry the callable default

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW (quick decision; the fix is obvious and narrowly scoped)
- **Dimension**: Blind Spots
- **Location**: Phase 1, §2 Migration with backfill; Critical Implementation Details
- **Detail**: The plan says "add `null=True` (no unique)" but does not say "no default".
  - The natural way to write 0003 is to run `makemigrations` and then split its output. That can leave `default=generate_code` on the `AddField`.
  - Django evaluates that default once and writes the same value to every existing row.
  - A 0002-style backfill (`filter(code__isnull=True)`) would then find nothing, and the final unique `AlterField` would fail on any DB with 2 or more games.
  - Step 1.4 would catch this on the dev DB (3 rows), so this is a clarity issue, not a hidden risk.
- **Fix**: State explicitly that the `AddField` has no `default`.
- **Decision**: FIXED (auto-triaged without the user; clarification added to Phase 1 §2 contract)

### F3: Rehearsal and test games will count in the live ranking at the event

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW (quick decision; the fix is obvious and narrowly scoped)
- **Dimension**: Blind Spots
- **Location**: Desired End State (Place `#R of M`); What We're NOT Doing
- **Detail**: `ranked_games()` ranks every finished game in the DB.
  - Staff smoke tests on the deployed instance, and any `bench_game --keep` runs, will appear in every player's `M` and can take top places. S-05's per-nick "hidden" filter does not exist yet and does not scale to bulk cleanup.
  - The plan has no pre-event data-reset note.
  - This is operational rather than a code defect, and adding it changes scope, so it is left for the user.
- **Fix**: Add one line to What We're NOT Doing or Migration Notes, e.g. "Before the event, delete rehearsal games (`GameSession.objects.all().delete()`) so places and `M` count only real players. Tooling for this is out of scope." Alternatively, defer it to F-02 or S-05.
- **Decision**: PENDING (not triaged without the user because it touches scope/ops)

### F4: `rank_of` could run the bulk expire twice

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW (quick decision; the fix is obvious and narrowly scoped)
- **Dimension**: Plan Completeness
- **Location**: Phase 2, §1 Ranking functions
- **Detail**: `ranked_games()` has a write side effect (`expire_overdue()`).
  - The contract describes the place as "count among `ranked_games()`" and the total as `ranked_games().count()`.
  - Read literally, that calls it twice, giving two `UPDATE`s. Performance Considerations assumes one.
  - This is harmless but avoidable.
- **Fix**: Specify that `rank_of` calls `ranked_games()` once and reuses the queryset.
- **Decision**: FIXED (auto-triaged without the user; bullet added to Phase 2 §1 contract)

### F5: Test mechanics: generator patch target and a deterministic leak check

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW (quick decision; the fix is obvious and narrowly scoped)
- **Dimension**: Plan Completeness
- **Location**: Phase 1 §5 Tests; Phase 2 §4 Tests
- **Detail**: Two small gaps in the test mechanics:
  - **(a) Patch target.** The generator lives in `game.models`. If services imports it by name, patching `game.models.generate_code` does nothing, and the "always collide" test fails confusingly.
  - **(b) Leak check.** The "code absent from `/play`" check compares a random 6-digit code against pages that contain 6-digit numbers (`data-remaining-ms="299…"`, and `remaining_ms` in JSON). The chance of a false failure is tiny, but it is non-zero.
- **Fix**: Name the patch target, and pin the code to a fixed value above 300000 (e.g. `'987654'`) in the leak tests.
- **Decision**: FIXED (auto-triaged without the user; both notes added to the Tests contracts)

## Triage summary

| Outcome | Findings |
|---|---|
| Fixed (auto-triaged, plan clarifications only) | F1, F2, F4, F5 |
| Pending (for the user) | F3 |
| Skipped / Accepted / Dismissed | none |

**Verdict after fixes:** SOUND (unchanged). The plan is ready for `/10x-implement` once F3 is decided or waved through.
