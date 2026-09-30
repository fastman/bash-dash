<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Restrict Allowed Nicknames

- **Plan**: context/changes/nickname-restrict/plan.md
- **Scope**: Phases 1-2 of 2 (full plan)
- **Date**: 2026-09-30
- **Verdict**: APPROVED (2 minor warnings)
- **Findings**: 0 critical, 1 warning, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

## Evidence

- Diff `main..HEAD` (code): `game/services.py`, `game/views.py`, `game/templates/game/home.html`, `game/static/game/game.css`, `game/management/commands/bench_game.py`, `game/tests/{test_services,test_views,test_bench,test_staff_views}.py`. Every changed file is in the plan, and every planned file is in the diff.
- Plan drift: every planned change matches its contract. `NICK_RE` is built from `NICK_MAX_CHARS` and used with `fullmatch`, and the strip happens before validation. The error copy matches the plan. The bench nicks are now `bench_{i}` and the help text says `bench_*`. The escape test bypasses `start_game` and has a comment. The template has `maxlength`, `pattern`, `title`, `aria-describedby` and the hint, and the CSS adds one `.start .hint` rule. One benign extra: the home test also asserts `aria-describedby="nick-hint"`.
- Safety: the regex is an explicit ASCII class with `fullmatch`, so Unicode letters and digits and a trailing `\n` are rejected. The echoed nick is auto-escaped by Django, and the escaping test is preserved. No migration, as planned.
- Automated criteria (run during review):
  - `uv run python manage.py test game challenges` → Ran 233 tests, OK
  - `uv run python manage.py test game.tests.test_services game.tests.test_views` → Ran 124 tests, OK
  - `uv run python manage.py test game.tests.test_bench` → Ran 5 tests, OK
  - `grep -rn "bench-{" game/` → no output

## Findings

### F1 — Browser pattern refuses surrounding whitespace that the server deliberately strips

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: game/templates/game/home.html:20
- **Detail**: The plan's "Surrounding whitespace" decision says to strip, then validate, because "phones often add a trailing space after autocomplete". `start_game` does this (services.py:83). But `pattern="[A-Za-z0-9_]{1,12}"` is anchored and does not allow whitespace, so `"neo "` never reaches the server: the browser blocks it with the "(no spaces)" popup. The server-side leniency is dead code for normal browser users. `autocorrect="off"` and `autocomplete="off"` make this less likely, but it is not guaranteed on every mobile keyboard. The flaw is in the plan itself, which specified both behaviours.
- **Fix A ⭐ Recommended**: Allow optional surrounding whitespace in the HTML pattern (`\s*[A-Za-z0-9_]{1,12}\s*`). Expose it as a `services.NICK_HTML_PATTERN` string built next to `NICK_RE`, and point the drift test at that constant.
  - Strength: Browser and server agree, so the plan's stated reason for stripping holds for real users.
  - Tradeoff: A second pattern constant. `maxlength="12"` still counts spaces, so a 12-char nick plus a trailing space gets truncated by the browser, which is harmless.
  - Confidence: MED — `\s` is valid under the `v` flag, but this has not been tested on a real phone.
  - Blind spot: How often booth phones actually insert a trailing space with autocorrect off.
- **Fix B**: Keep the strict pattern and record in the plan that client-side whitespace is refused, so the server strip covers only non-browser clients.
  - Strength: No code change. The popup already says "(no spaces)", so users can fix it themselves.
  - Tradeoff: Leaves a small UX papercut the plan explicitly wanted to avoid.
  - Confidence: HIGH — behaviour is already tested and green.
  - Blind spot: None significant.
- **Decision**: PENDING

### F2 — Hint and title copy hardcode "12" outside the drift-guard test

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: game/templates/game/home.html:19,21
- **Detail**: The plan hardcodes `maxlength`/`pattern` and guards them with a test against `services.NICK_MAX_CHARS`/`NICK_RE.pattern`. The hint ("max 12") and `title` ("Use 1-12 …") also hardcode the limit, and no test guards them. If `NICK_MAX_CHARS` changes, the copy silently goes stale. The `title` also duplicates the view's error string (views.py:121).
- **Fix**: In `test_home_renders_rules_and_nick_form`, also assert `f'max {services.NICK_MAX_CHARS}'` and `f'title="Use 1-{services.NICK_MAX_CHARS} letters'`.
- **Decision**: PENDING

### F3 — Manual verification: Phase 1 rows ticked without evidence, Phase 2 rows pending

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/nickname-restrict/plan.md:224-238
- **Detail**: Manual rows 1.5 and 1.6 (browser start as `neo_42`, and `ab cd` with the pattern removed) are marked `[x] — 0d98a4c`. The plan was run non-interactively, and no evidence of a browser check exists (view tests cover the behaviour, but not a real browser). Rows 2.3-2.5 (phone viewport hint, 13th char blocked plus popup, 12-char nick shown in full on `/staff/hall`) are still `[ ]`. Row 2.5 matters because `.hall .hall-row .nick` truncates with `text-overflow: ellipsis` (game.css:308), so a full 12-char nick depends on the real row width.
- **Fix**: Run the Manual Testing Steps (`docker compose up`, phone plus `/staff/hall`). Tick 2.3-2.5, and re-confirm 1.5/1.6, before opening the PR.
- **Decision**: PENDING
