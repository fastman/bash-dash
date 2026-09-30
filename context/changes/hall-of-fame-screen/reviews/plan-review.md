<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Hall of Fame Screen with Nick Hiding

- **Plan**: context/changes/hall-of-fame-screen/plan.md
- **Mode**: Deep (codebase verification done inline; blast radius was small)
- **Date**: 2026-09-30
- **Verdict**: REVISE (light — the plan is well grounded; it needs the user to confirm its decisions plus a few small edits)
- **Findings**: 0 critical, 3 warnings, 3 observations

> **Heads-up: the 9 design decisions in this plan are unconfirmed.** The planner ran unattended and
> chose each "Key Decision" in `plan-brief.md` without asking the user. See F1. Confirm or override
> them before running `/10x-implement`.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | WARNING |
| Plan Completeness | WARNING |

## Grounding

Grounding: 11/11 existing paths ✓ (models, services, views, staff_views, urls, admin, settings, game.css, base.html, done.html, staff/lookup.html; latest migration is 0004, so 0005 is correct), 7/7 symbols ✓ (`ranked_games` with its "S-05 adds its hidden filter here" docstring, `rank_of`, `views.done` unpacking at views.py:183, `staff_member_required`, `EmptyFieldListFilter`, `BASHDASH_*` settings pattern, `StaffTestCase.make_game`), brief↔plan ✓, Progress↔Phase ✓ (3/3 phases, 16/16 criteria rows), baseline 170 tests OK ✓.

Codebase verification:
- **Blast radius** is contained. `ranked_games()` is called only by `rank_of()`, and `rank_of()` only by `views.done` and `staff_views.lookup`. The hidden filter reaches exactly the surfaces the plan names.
- **One-pass place parity** holds. Within one `solved` value, `elapsed` is either always NULL or never NULL, and `solved` is the first sort key, so SQLite's NULLS-FIRST ordering of `elapsed` cannot interleave groups. The `(solved, attempts, elapsed)` key-equality rule matches `rank_of`'s "strictly better" count.
- **`never_cache`** sends `no-store`, so the plan's Cache-Control test will pass.

## Findings

### F1 — Nine design decisions were taken unattended and are unconfirmed

- **Severity**: ⚠️ WARNING
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Plan Completeness
- **Location**: plan-brief.md "Key Decisions Made"; the plan as a whole
- **Detail**: The brief says: "This was an unattended planning run with no interactive Q&A … Review them before implementing." Every decision is well argued and grounded in the PRD and code, but none was confirmed by the owner. Three of them carry product or policy weight rather than just technical weight:
  - (a) **A disqualified player keeps everything except the place.** `/done` still shows their prize code, and the staff lookup keeps the "Mark prize given" button. The PRD says hiding "works as disqualification" (FR-012), but the plan leaves prize eligibility to staff judgement. That is defensible, since prize policy is still PRD Open Question 2, but it is a policy call.
  - (b) **Hiding is per game, not per nick.** A troll who plays five times has to be hidden five times.
  - (c) **Defaults for PRD Open Question 3**: top 10, recent 5, refresh 5 s. The PRD owner is "user, during implementation".

  The other six decisions (timestamp field, filter in `ranked_games()`, Unhide, a separate `/staff/moderate` page, fragment polling, 403 on an expired session) follow directly from the code or the tech stack and are low-risk.
- **Fix**: Have the user confirm or override each of the 9 decisions. Record the outcome in plan-brief.md, changing the "unattended" note to "confirmed on <date>". If (a) is overridden, add hiding the prize button for hidden games to the Phase 1 lookup contract.
  - Strength: Removes the only real uncertainty in an otherwise sound plan, before any code is written.
  - Tradeoff: One round-trip with the user.
  - Confidence: HIGH — the decisions are explicit and listed in one table.
  - Blind spot: Prize policy (PRD Open Question 2) may still be unresolved, so (a) may have to stay provisional.
- **Decision**: PENDING

### F2 — Public booth display holds a permanently logged-in superuser session

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Migration Notes ("The display laptop logs in with the shared staff account and stays logged in"); Manual Testing step 1 (`createsuperuser`)
- **Detail**: S-04 accepted a shared `createsuperuser` account for staff (S-04 plan, Migration Notes), with the session held on a staff phone. S-05 adds a new exposure: that superuser session sits unattended for two weeks on a laptop at a public booth. Anyone who steps up to the keyboard can open `/staff` (mark prizes), `/staff/moderate` (hide players), or `/admin/auth/user/`. Only the game models are read-only in the admin; the auth User admin is not, so a visitor could change staff passwords or create users. The plan does not mention this.
- **Fix**: Add operational notes to Migration Notes:
  1. The display logs in with a dedicated account that has `is_staff=True`, `is_superuser=False` and no model permissions. The admin then shows nothing, but the `/staff/*` pages still work.
  2. Run the browser in kiosk/fullscreen mode, and keep the laptop out of visitors' reach (or keyboard-locked).
  - Strength: Needs no code, and removes the worst case (editing auth users) completely.
  - Tradeoff: That account can still reach `/staff` and `/staff/moderate`, so physical control of the laptop remains the real guard.
  - Confidence: HIGH — `staff_member_required` checks only `is_active` and `is_staff`, and admin model visibility is permission-based.
  - Blind spot: A read-only "display" role (a separate permission check on hide/prize) would close the gap fully, but it widens scope and was not evaluated.
- **Decision**: PENDING

### F3 — Recent-list place lookup can raise KeyError on a race

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Critical Implementation Details ("look up recent games' places in a dict keyed by pk"); Phase 1 §4 `hall_of_fame`
- **Detail**: `hall_of_fame()` runs one query for the ranked pass and a second for `recent`. `ATOMIC_REQUESTS` is False and SQLite does not share a snapshot between the two queries. A game that finishes (by `/command` or by another request's `expire_overdue`) between them lands in `recent` but not in the places dict. The lookup then raises `KeyError`, which means a 500 on `/staff/hall/board` (a brief "Reconnecting…") and on `/staff/moderate`. It is more likely at peak, which is exactly when the booth is busiest.
- **Fix**: Build `recent` from the rows of the ranked pass itself: take the ranked rows, sort them by `(-finished_at, -pk)` in Python, and take the first `recent_n`. This drops the second query and the separate `hidden_at__isnull=True` filter (Key Discovery bullet 1), and makes the KeyError impossible.
- **Decision**: PENDING

### F4 — A malformed game_id raises ValidationError, not DoesNotExist

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 1 §4 (`hide_game` / `unhide_game` contract); Phase 3 §1 (hide/unhide views)
- **Detail**: The service contract promises only `GameSession.DoesNotExist` for an unknown id. The Phase 3 tests expect a malformed id to produce an error message. Verified in this repo: `GameSession.objects.filter(pk='abc').update(...)` raises `django.core.exceptions.ValidationError` ("“abc” is not a valid UUID"). An implementer who follows the contract as written would let it escape as a 500.
- **Fix**: In the view contract, validate `game_id` with `uuid.UUID()` (or catch `ValidationError` alongside `DoesNotExist`) and map both to "No such game.".
- **Decision**: PENDING

### F5 — Staff test helper can't build the multi-game fixtures the plan needs

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 §6 and Phase 3 §6 tests; References ("`StaffTestCase.make_game`")
- **Detail**: `StaffTestCase.make_game` (game/tests/test_staff_views.py:24) always sets `code=CODE` ('987654'), and `code` is unique. A second call raises IntegrityError. It also gives every game the same `started_at + 75s` as `finished_at`, so "recent newest-first" is not testable with it. `-pk` on a random UUID is not a meaningful tie-break.
- **Fix**: Note in Phase 2 tests that `make_game` gains `code=` and `finished_offset=` (or `finished_at=`) parameters, with defaults that keep the existing tests unchanged.
- **Decision**: PENDING

### F6 — `messages.info` would render as a red error under the existing template pattern

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 3 §1 (`messages.info` for "already hidden" / "not hidden"); Phase 3 §3 template
- **Detail**: `staff/lookup.html` maps `success` to `notice-ok`, `warning` to `notice-warn`, and everything else to `notice-bad`. Copying that loop into `moderate.html` shows the harmless "already hidden" message in red. `give_prize` uses `messages.warning` for the equivalent case.
- **Fix**: Use `messages.warning` for the "already hidden" / "not hidden" outcomes, matching `give_prize`.
- **Decision**: PENDING
