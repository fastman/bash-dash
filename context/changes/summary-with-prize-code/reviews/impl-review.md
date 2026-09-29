<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Summary with Prize Code Implementation Plan

- **Plan**: context/changes/summary-with-prize-code/plan.md
- **Scope**: Full plan (Phases 1–2 of 2; Phase 2 manual rows 2.4, 2.5 still pending)
- **Date**: 2026-09-29
- **Verdict**: APPROVED (2 minor findings; manual rows 2.4 and 2.5 still to be done by a human)
- **Findings**: 0 critical, 1 warning, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | PASS |
| Architecture | WARNING |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

## Evidence

Commits reviewed: 318a63c (p1), 5f8e1bf (p2), d56f2b2 (progress bookkeeping). Code files changed: `game/admin.py`, `game/migrations/0003_gamesession_code.py`, `game/models.py`, `game/services.py`, `game/static/game/game.css`, `game/templates/game/done.html`, `game/views.py`, `game/tests/test_services.py`, `game/tests/test_views.py`. Every file is in the plan, and nothing the plan lists is missing from the diff.

Plan drift check (all MATCH):
- Model: `generate_code()` in `game/models.py` uses `secrets.randbelow(10**6):06d`. The field is `CharField(max_length=6, unique=True, editable=False, default=generate_code)` and the docstring is updated.
- Migration 0003: `AddField(null=True)` with no default, then `RunPython(backfill, noop)` with a used-set, then `AlterField` to unique and non-null. This is the 0002 pattern, as the plan specifies.
- `start_game`: a per-attempt `transaction.atomic()` savepoint, catches only `IntegrityError`, `CODE_ATTEMPTS = 10`, then `RuntimeError('could not allocate a unique prize code')`. `generate_code` is imported by name, so the tests patch `services.generate_code`.
- Admin: `code` is in `list_display` and `search_fields`, and the admin stays read-only.
- `ranked_games()` / `rank_of()`: bulk `expire_overdue()` runs once per call, the `elapsed` annotation reads from the annotated queryset, strictly-better competition ranking, and the S-05 hidden-filter note is in the docstring.
- `done` view, template and CSS: the context adds `place` and `ranked_total`. Blocks appear in the planned order. `.prize-code` uses the `--mono` and `--accent` tokens, `clamp()` sizing and `user-select: all`.
- Tests: every contract bullet in both phases is covered, except the items noted in F1. There is no migration test; the plan marked it "if practical".

Safety scan: no issues. The code is digits only and auto-escaped. SQLite runs with `transaction_mode: IMMEDIATE`, so the nested `atomic()` in `start_game` becomes a savepoint inside callers' transactions, which is correct. On SQLite, NULL `elapsed` sorts first under ASC, but the NULL and non-NULL values never compete, because `solved > 0` ⇔ `last_solved_at IS NOT NULL` and `solved` is the first key.

Automated criteria (run during this review):
- `uv run python manage.py test game challenges`: OK, 149 tests (baseline 135).
- `uv run python manage.py check`: no issues.
- `uv run python manage.py makemigrations --check --dry-run`: no changes detected.
- `showmigrations game`: 0003 applied on the dev DB. The 1.4 uniqueness assertion passes (3 rows, 3 distinct codes, none NULL).

Manual criteria: 2.4 (320/360 px layout) and 2.5 (three-browser ranking) are unchecked and pending. 1.5, 2.6 and 2.7 are checked, but see F1.

## Findings

### F1 — Manual rows 2.6, 2.7 (and 1.5) ticked without human evidence

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Success Criteria
- **Location**: context/changes/summary-with-prize-code/plan.md:277, 291-292
- **Detail**: The implementation commits tick three Manual rows: 1.5 (admin code column and search), 2.6 (an abandoned overdue game counts in M on the next `/done` load) and 2.7 (reloading `/done` keeps the same code). The d56f2b2 commit message says "pending manual rows", and nothing records a human doing these checks. For 2.6, the only evidence is a service-level test (`RankingTests.test_overdue_unfinished_game_is_expired_and_counted`). No view test loads `/done` with another player's overdue game in the DB. For 2.7, no test reloads `/done` at all. Related gap: the plan says the code never appears on `/`, but `SummaryTests.test_code_is_not_leaked_on_play_or_json` covers only `/play`, `/play/command` and `/play/state`. In practice `/` either shows the start form or redirects, so the risk there is low.
- **Fix A ⭐ Recommended**: Uncheck 1.5, 2.6 and 2.7, and verify them by hand in the same session as 2.4 and 2.5 (Manual Testing Steps 1–5 already cover them).
  - Strength: Keeps the Progress section honest. Steps 1, 4 and 5 of the manual script already cover these checks, so there is little extra work.
  - Tradeoff: A few more minutes of manual testing before the change can close.
  - Confidence: HIGH — the checks are cheap, and the manual session is still due for 2.4 and 2.5.
  - Blind spot: None significant.
- **Fix B**: Keep the rows ticked and add two `SummaryTests` view tests. One loads `/done` with a second, overdue unfinished game and asserts `of 2`. The other gets `/done` twice and asserts the same code both times. Optionally add `/` to the no-leak test.
  - Strength: Turns the manual claims into regression tests that stay useful for S-04 and S-05.
  - Tradeoff: 1.5 (the admin UI) still has no evidence, and a unit test is not the end-to-end browser check the row describes.
  - Confidence: MED — the tests are easy to write, but they relabel manual rows as automated.
  - Blind spot: Whether the user counts the implementing agent's shell checks as a sufficient manual check.
- **Decision**: Fix A — rows 1.5, 2.6, 2.7 unticked in plan.md; to be checked by hand in Phase 9 (user decision)

### F2 — `done` unpacks `rank_of()` with no guard for `None`

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architecture
- **Location**: game/views.py:183
- **Detail**: `place, ranked_total = services.rank_of(game)` assumes a finished game always has a rank. That holds today. The plan and the `ranked_games()` docstring name that queryset as the place where S-05 adds its "hidden" filter. Once S-05 lands, a hidden or disqualified player who reloads `/done` gets a `TypeError` (HTTP 500) instead of their summary and code. S-04's lookup would also need to handle `None`.
- **Fix**: Bind `rank = services.rank_of(game)` and pass `place`/`ranked_total` as `None` when it is missing, with `{% if place %}` around the Place line in `done.html`. Alternatively, record this as an explicit S-05 plan requirement.
- **Decision**: Noted as carry-over on S-05 in roadmap.md; no code change now (user decision)
