<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Staff Code Lookup and Prize Issuing

- **Plan**: context/changes/staff-code-lookup-and-prize/plan.md
- **Scope**: Full plan (Phases 1–2 of 2)
- **Date**: 2026-09-29
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 2 observations

## Summary

The implementation closely matches the plan. Every planned file is in the diff: model field, migration 0004, `normalize_code` / `find_by_code` / `mark_prize_given` / `solve_time` in services, admin column and filter, `staff_views.py`, routes, template, CSS, `mmss` filter, and both test modules. The guarded single `UPDATE` and the expire-before-read/mark rules are implemented as specified. The only file outside "Changes Required" is `context/foundation/tech-stack.md`. That edit came from the plan-review decision commit (309de3f), so it is benign.

Automated verification (re-run during review):

| Command | Result |
|---|---|
| `uv run python manage.py test game challenges` | PASS — 169 tests OK (baseline 149, +20) |
| `uv run python manage.py check` | PASS — no issues |
| `uv run python manage.py makemigrations --check --dry-run` | PASS — No changes detected |
| `uv run python manage.py migrate` / `showmigrations game` | PASS — `0004_gamesession_prize_given_at` applied |

Deliberate-break check (by reading): removing either guard in `mark_prize_given` (`prize_given_at__isnull=True` or `finished_at__isnull=False`) would fail `test_mark_prize_given_only_once` or `test_mark_prize_refused_for_unfinished_game`. Removing `expire_overdue` would fail the two overdue tests.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

## Findings

### F1 — Manual criteria ticked without observable evidence

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/staff-code-lookup-and-prize/plan.md:288, :300, :302
- **Detail**: Three manual items are marked `[x]`, but nothing in the diff shows they were checked:
  - 1.5 is a visual check of the admin column, filter, and read-only state.
  - 2.4 says a logged-out user is sent to login "and returns after login". `AccessTests` only asserts that `Location` contains `/admin/login/`. It never checks `next=/staff`, and no test logs in and follows the redirect back.
  - 2.6 is annotated "verified by HTTP tests". The plan's criterion is an end-to-end real-app check: play a game, then compare solved, attempts and place with the player's `/done`. The HTTP test uses one synthetic game (`#1 of 1`) and never renders `/done`.

  Item 2.7 is reasonably covered by `test_unfinished_game_shows_in_progress_and_no_button`. Item 2.5 (the 320/360 px layout and numeric keyboard) is honestly left `[ ]` and is pending.
- **Fix**: Un-tick 1.5, 2.4 and 2.6 until a human runs Manual Testing Steps 1–6. Optionally add `self.assertIn('next=/staff', resp['Location'])` to `AccessTests` so part of 2.4 is automated.
- **Decision**: PENDING

### F2 — In-progress game shows "Place: not ranked"

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: game/templates/game/staff/lookup.html:21 (with game/staff_views.py:35)
- **Detail**: The view passes `rank=None` for unfinished games. The template renders `None` as "not ranked" no matter what state the game is in. The plan reserves "not ranked" for a *finished* game that `rank_of` excludes, which is the S-05 hidden/disqualified state. For a game still being played, the plan only calls for the identity data plus "Game in progress". So an in-progress card now shows "Place: not ranked", which reads like a disqualification. It also shows a live, still-changing solve time. Once S-05 lands, staff cannot tell "still playing" apart from "hidden" by the Place line alone.
- **Fix**: Wrap the Place line in `{% if game.is_finished %}…{% endif %}`, or render "—" for unfinished games. Also add `assertNotContains(resp, 'not ranked')` to the unfinished-game view test.
- **Decision**: PENDING

### F3 — "Already given (HH:MM)" is rendered in UTC at a Polish booth

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: game/templates/game/staff/lookup.html:27; config/settings.py:118
- **Detail**: `USE_TZ = True` and `TIME_ZONE = 'UTC'`, so `{{ game.prize_given_at|date:"H:i" }}` shows UTC. On the event day (2026-10-03, CEST = UTC+2), a prize given at 16:03 local time shows as "(14:03)". The plan acknowledged this ("UTC unless the operator changes `TIME_ZONE`"), but nothing makes the operator change it. The HH:MM is the one absolute time staff see, and it exists to settle disputes ("you got it at 14:03?"). A clock that is two hours off undermines that and can lead staff to wrongly doubt the warning. The admin's `prize_given_at`, `finished_at` and other columns are also shown in UTC.
- **Fix A ⭐ Recommended**: Set `TIME_ZONE = 'Europe/Warsaw'` in `config/settings.py`.
  - Strength: With `USE_TZ = True`, storage stays UTC and only display converts. This fixes the staff page and all admin datetime columns in one line.
  - Tradeoff: Any code that formats times without `localtime` still shows UTC. Tests that assert rendered clock times, if any exist, may need adjusting.
  - Confidence: HIGH — this is standard Django behavior with `USE_TZ=True`, and the 169-test suite would flag regressions.
  - Blind spot: Not checked whether F-02/deploy settings override `TIME_ZONE` through the environment.
- **Fix B**: Drop the `(H:i)` part and keep only the relative `timesince`.
  - Strength: Removes the misleading clock with no settings change.
  - Tradeoff: Loses the absolute time the plan wanted for disputes, and the admin still shows UTC.
  - Confidence: HIGH — a template-only change.
  - Blind spot: None significant.
- **Decision**: PENDING

### F4 — Booth runs on a shared superuser although `is_staff` is enough

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: plan.md:263 (Migration Notes, operational step); game/staff_views.py:20,39
- **Detail**: `staff_member_required` only checks `is_active and is_staff`. The plan still has booth staff share a `createsuperuser` account. The game models are read-only in the admin, but a superuser can also create users, change passwords, and edit groups and sessions through `django.contrib.auth`'s admin. The plan accepted this risk. A least-privilege account costs almost nothing and removes it.
- **Fix**: In the Migration Notes / runbook, create a dedicated booth account with `is_staff=True`, `is_superuser=False` and no model permissions (it can still use `/staff`). Keep the superuser for the operator only.
- **Decision**: PENDING

### F5 — Small test gaps against the plan's test contract

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: game/tests/test_staff_views.py
- **Detail**: Three behaviours in the Phase 2 contract are not asserted over HTTP:
  - the success message "Prize given to <nick>." (`test_post_marks_once_and_redirects` does not follow the first redirect);
  - "—" as the solve time for a finished 0-solved game (only the `mmss` unit test covers `None`);
  - the login redirect preserving `next` (see F1).

  None of these are bugs today. They are unpinned behaviour.
- **Fix**: Follow the first POST (`follow=True`) and assert `'Prize given to neo.'`. Add a `make_game(solved=0)` lookup test asserting `'—'`. Assert `next=` in `AccessTests`.
- **Decision**: PENDING
