<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Staff Code Lookup and Prize Issuing Implementation Plan

- **Plan**: context/changes/staff-code-lookup-and-prize/plan.md
- **Mode**: Deep
- **Date**: 2026-09-29
- **Verdict**: REVISE
- **Findings**: 0 critical, 3 warnings, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | WARNING |
| Blind Spots | WARNING |
| Plan Completeness | WARNING |

## Grounding

Grounding: 8/8 paths ✓ (migration 0004 is the next free number), 7/7 symbols ✓ (`expire_overdue`, `rank_of`, `ranked_games`, `GameSession.code`, `catalog.main_set`, `staff_member_required`, CSS tokens `--accent`/`--warn`/`--bad`), brief↔plan ✓, Progress↔Phase ✓ (Phase 1: 4 automated and 1 manual; Phase 2: 3 automated and 4 manual; all match). Baseline: 149 tests, OK.

Deep verification confirmed the following:
- `expire_overdue(game_id)` touches only that game (`game/services.py:97-98`).
- `rank_of` re-reads the row by pk, bulk-expires through `ranked_games()`, and returns `None` for unfinished games (`services.py:108,114-123`).
- Django 6.1.1 needs a POST to log out of the admin.
- `staff_member_required` redirects to `admin:login`.
- The game app is mounted at `''`, so `/staff/` resolves.
- Messages are fully configured (`config/settings.py:39,51,66`). `base.html` does not render them, so the staff template must render them, as the plan says.
- Blast radius is small: nothing reads model fields generically.

## Findings

### F1 — Custom `/staff/` page contradicts tech-stack.md's admin-only staff tooling

- **Severity**: ⚠️ WARNING
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Architectural Fitness
- **Location**: Implementation Approach; Phase 2 (all of it); plan-brief "Open Risks"
- **Detail**: `context/foundation/tech-stack.md:24` says the Django admin "gives booth staff password login, lookup by 6-digit code, nick hiding and 'prize given' for free, which covers FR-011 to FR-013 without custom UI". The plan instead builds a custom `/staff/` page: a new `game/staff_views.py`, routes, a template, CSS and a view test module. It keeps the admin read-only. The plan gives its reasons (an admin action has a search → tick → action → Go flow that can mark the wrong row, and there is no phone-sized confirmation that shows place and "already given" before the click). But the decision was made in an unattended planning run, and the foundation doc was never updated. S-05 (nick hiding, FR-012) is also planned to go under `staff/`, so this choice sets the pattern for all staff tooling and moves away from the admin approach in the stack decision. The user has not confirmed this.
- **Fix A ⭐ Recommended**: Keep the custom `/staff/` page and record the decision. Amend `tech-stack.md:24` (and optionally the S-04/S-05 roadmap notes) to say the staff tooling is a small custom `staff/` area and the admin is only a read-only backup.
  - Strength: The phone-first, single-screen check (nick, place, "already given" before the click) matches FR-011/FR-013 and the PRD's main success criterion better. The guarded single-row UPDATE is cleaner than a bulk admin action. S-05 reuses the auth and URL pattern.
  - Tradeoff: About one extra view module, one template, CSS and around 12 view tests on a one-week solo build with the event on 2026-10-03.
  - Confidence: HIGH — every framework claim the plan relies on was checked against the code and Django 6.1.1.
  - Blind spot: Whether booth staff would actually get along fine with the admin on a phone has not been tested.
- **Fix B**: Go admin-only, as `tech-stack.md` says. Phase 2 becomes a `mark_prize_given` admin action (plus `has_change_permission`/action permission on `GameSessionAdmin`) that calls the Phase 1 service and reports the result with `message_user`. Drop `staff_views.py`, the routes, the template, the CSS and the view tests.
  - Strength: Follows the recorded stack decision; the least new code; no new URL space or auth surface.
  - Tradeoff: Staff use the admin changelist on a phone (search → tick → action → Go). There is no confirmation card with the place before marking, and the wrong row can be ticked. The admin also stops being fully read-only, which contradicts the plan's "What We're NOT Doing".
  - Confidence: MED — the admin action mechanics are standard, but how usable the admin is on a 320 px phone has not been checked.
  - Blind spot: S-05's nick hiding would then also need admin write access, which widens the non-read-only surface.
- **Decision**: Keep custom page; tech-stack.md updated

### F2 — Booth staff share a superuser account

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Migration Notes; Manual Testing Steps step 1; "What We're NOT Doing" (custom login / staff accounts)
- **Detail**: The plan's operational step is `createsuperuser` on the event VM, with the password shared among booth staff. `ReadOnlyMixin` covers only the `game` models. The `auth` User/Group admin stays fully writable, so anyone with the shared booth password can create users, change passwords or grant permissions in the admin. `staff_member_required` only needs `is_active and is_staff`, so the page works without superuser rights.
- **Fix**: Change Migration Notes and Manual Testing step 1 to create a dedicated `is_staff=True`, `is_superuser=False` account with no model permissions for the booth (for example `createsuperuser` followed by `User.objects.filter(username='booth').update(is_superuser=False)`, or a `create_user(..., is_staff=True)` shell one-liner). Keep the superuser for the operator. Add one view test showing that a staff user with no permissions can use `/staff/`.
  - Strength: The shared password gets only the prize desk, not user management. It costs one line of operations and one test.
  - Tradeoff: The operator has two accounts to manage.
  - Confidence: HIGH — the `staff_member_required` check was verified in Django 6.1.1.
  - Blind spot: If F1 goes with Fix B (admin-only), the booth account instead needs the `game.change_gamesession` permission.
- **Decision**: Keep shared superuser account (user chose to accept the risk)

### F3 — Staff login over the public HTTPS domain is not covered by settings

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Migration Notes; Manual Verification 2.4
- **Detail**: This is the first slice where someone logs in over a POST from a phone on the event domain. `config/settings.py` sets neither `CSRF_TRUSTED_ORIGINS` nor `SECURE_PROXY_SSL_HEADER`, and it has `DEBUG = True` and the insecure `SECRET_KEY` hard-coded (`:24,27`). Behind an HTTPS reverse proxy, Django's CSRF origin check can reject the admin login POST (403), so the booth cannot log in on the day. Local manual testing on `runserver` will not catch this. Most of this belongs to F-02 (event infrastructure), but S-04 is the slice that depends on it.
- **Fix**: Add a line to Migration Notes: "Requires F-02 to set `CSRF_TRUSTED_ORIGINS` / `SECURE_PROXY_SSL_HEADER` (and DEBUG off, secure cookies) for the public domain; verify the staff login on the deployed URL." Also add a matching unknown to the F-02 roadmap entry if it is not already there.
- **Decision**: Applied: F-02 settings note added to Migration section

### F4 — `mmss` filter partly duplicates `clock`; the choice is left open

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 §3 Template (last bullet); Phase 1 §3 `solve_time`
- **Detail**: The plan says "add `mmss` to `game_text.py` or pre-format in the view; pick the one with less code". `game_text.clock(remaining_ms)` (`game/templatetags/game_text.py:24-28`) already formats `m:ss`, but it rounds up, which suits a countdown and not an elapsed time. An implementer reusing `clock` would show solve times one second too long, and they would no longer match the ranking tie-break (`elapsed` in `ranked_games`).
- **Fix**: Specify it: add an `mmss(timedelta | None)` filter to `game_text.py` that floors seconds and renders "—" for `None`, with a one-line note not to reuse `clock` (it ceil-rounds).
- **Decision**: Applied: new round-down mmss filter specified

### F5 — Mixed trailing-slash style in the new routes

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 §2 Routes
- **Detail**: The plan adds `path('staff/', ...)` and `path('staff/prize', ...)`. Every existing route in `game/urls.py` has no trailing slash (`start`, `play/command`, `done`). With `APPEND_SLASH`, a typed `/staff` redirects to `/staff/` without trouble, but the plan mixes the two styles within one feature. S-05 will copy this.
- **Fix**: Pick one style and state it. For example, `path('staff', ...)` plus `path('staff/prize', ...)` to match the existing routes, with the tests and manual steps updated to `/staff`. Or keep `staff/` and add a note that it is intentional.
- **Decision**: Applied: routes are `staff` and `staff/prize` (no trailing slash on the index)
