<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Restrict Allowed Nicknames Implementation Plan

- **Plan**: context/changes/nickname-restrict/plan.md
- **Mode**: Deep
- **Date**: 2026-09-30
- **Verdict**: SOUND
- **Findings**: 0 critical, 1 warning, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | PASS |
| Plan Completeness | WARNING |

## Grounding

9/9 paths ✓ (services.py, views.py, home.html, bench_game.py, game.css, test_services/test_views/test_bench/test_staff_views.py), 8/8 symbols ✓ (`NICK_MAX_CHARS`, `CODE_RE`, `start_game`, `make_game`, `test_nick_is_escaped`, `test_nick_error_keeps_token`, `test_home_renders_rules_and_nick_form`, `--muted`), cited line numbers accurate, brief↔plan ✓, Progress↔Phase ✓ (6 + 5 items, 1:1), baseline `uv run python manage.py test game challenges` → 231 OK ✓.

Blast-radius sweep: every `start_game` caller is accounted for. The only callers the new rule breaks are `bench_game.py:62` (`bench-{i}`) and `test_staff_views.py:183` (`<b>x</b>`), both covered by the plan. Test nicks the plan does not list (`itest` in test_integration.py:21; `trinity`, `p`, `c` in test_services.py) already pass the new rule. No test asserts the old "Enter a nick of…" text. No `docs/reference/contract-surfaces.md` or `lessons.md` exists.

## Findings

### F1 — "Extend" the existing nick test leaves an assertion that now fails

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 1 — Changes Required §4 (`game/tests/test_services.py`)
- **Detail**: The plan says to extend `test_empty_and_too_long_nicks_are_rejected`, but that test (`test_services.py:51-56`) also calls `services.start_game('x' * 20)  # boundary is fine` and asserts `GameSession.objects.count() == 1`. Under the new rule the 20-char call raises `ValueError`, and mixing new accepted cases into the same test breaks the count check. The plan's "Tests that already cover the rule" note (line 16) lists only the rejected cases and misses this positive boundary.
- **Fix**: In Phase 1 §4, say to replace `'x' * 21` with `'x' * 13` and to remove the `'x' * 20` positive boundary from this test. Keep it rejection-only with `count() == 0`, and put all accepted cases (including `'x' * 12`) in the new sibling test.
- **Decision**: PENDING

### F2 — Template limit left as "hardcode or pass from view"

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 — Changes Required §1 and §3
- **Detail**: The plan leaves the choice to the implementer. Passing the limit from the view touches two render sites (`views.py:103` for GET home and `views.py:119` for the error re-render) and puts a regex into view context. Hardcoding is simpler, but the drift test in §3 only checks the literal `maxlength="12"`, so it would not catch drift from `NICK_MAX_CHARS`. §1 also says `NICK_RE` is "built from `NICK_MAX_CHARS`" but shows a literal `{1,12}`.
- **Fix**: Hardcode `maxlength="12"` and `pattern="[A-Za-z0-9_]{1,12}"` in `home.html`. Have the §3 test assert `f'maxlength="{services.NICK_MAX_CHARS}"'` and `f'pattern="{services.NICK_RE.pattern}"'`, so any drift fails the test and one test covers the §1 drift requirement.
- **Decision**: PENDING
