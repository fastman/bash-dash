<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Camlin Branding (Sponsor Logo + Link) Implementation Plan

- **Plan**: context/changes/branding/plan.md
- **Mode**: Deep
- **Date**: 2026-10-01
- **Verdict**: SOUND
- **Findings**: 0 critical, 0 warnings, 4 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | WARNING (1 observation) |
| Plan Completeness | WARNING (3 observations) |

## Grounding

Grounding: 11/11 paths ✓, 8/8 symbols ✓ (`EXTERNAL_LINK`, `NoAnswerLinksTests`, WhiteNoise middleware, `collectstatic` in Dockerfile, `{% load static %}` in base/hall, `Board`/`BoardRow`, hall CSS values at game.css:293-342, `main` at 42-46), brief↔plan ✓, Progress↔Phase ✓ (all 14 criteria mirrored, no checkboxes in phase bodies), handoff↔plan ✓ (deviations explicitly justified).

## Verification notes

- **Hall fit was re-measured independently.** hall.html was rendered with 10 top + 5 recent rows and loaded in headless Chrome at 1600×900. Results: today 889px, handoff as written 936px, handoff fallback 928px, plan values 874px. All four match the plan exactly.
- **Wrapper preserves spacing.** `main` has 18px top and 32px bottom padding, so no child margin ever collapsed through `main`. A flex-item wrapper (its own BFC) keeps the internal margin collapsing, so the "pixel-identical" claim holds. The bare-flex regression the plan describes is real: `.logo` 16px plus `h1.rule` 20px stop collapsing.
- **No blast radius beyond the plan.** `play.js`/`hall.js` select only by id (only `output.scrollTop` is touched). No `main >` child selectors exist in CSS. No `.page` class collision. No other test inspects external links on staff pages.
- **Departure from the handoff's "don't change tests".** This is unavoidable, because `NoAnswerLinksTests` would fail on any sponsor link. The plan handles it with an allowlist rather than deleting the guard.

## Findings

### F1 — Gate test must expect 403

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW (quick decision; the fix is obvious and narrowly scoped)
- **Dimension**: Plan Completeness
- **Location**: Phase 1, §5 Tests
- **Detail**: The new "footer present" test covers gate (home without a token). `_gate_refusal` renders gate.html with `status=403` (`game/views.py:89-91`). A plain `assertContains` defaults to `status_code=200` and would fail for a reason unrelated to the footer.
- **Fix**: Note in the test contract that the gate assertion needs `status_code=403`, following the existing gate tests (`test_views.py:94-115`).
- **Decision**: FIXED (note added to Phase 1 §5 Tests contract)

### F2 — "Optionally" wrapper margin-bottom leaves the long-page gap undecided

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW (quick decision; the fix is obvious and narrowly scoped)
- **Dimension**: Plan Completeness
- **Location**: Phase 1, §4 Styles
- **Detail**: On long pages, `margin-top: auto` resolves to 0. The gap between the last content element and the footer rule is then only that element's own bottom margin, plus the wrapper margin if the implementer chooses to add one. The plan says "Optionally give the wrapper margin-bottom (~32px)", and manual check 1.7 has no expected gap to compare against. The handoff's own fallback uses `.sponsor { margin-top: 32px }`.
- **Fix**: Decide now. For example, `.page { margin-bottom: 32px }` matches the handoff fallback, and `auto` still absorbs the extra space on short pages. This is a visual judgment call, so it was left for the author.
- **Decision**: PENDING (open item, a design judgment for the author)

### F3 — Hall-fit criterion 2.3 is a procedure, not a runnable command

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW (quick decision; the fix is obvious and narrowly scoped)
- **Dimension**: Plan Completeness
- **Location**: Phase 2 Success Criteria / Testing Strategy step 5
- **Detail**: The implementer has to rebuild the measurement harness. Reproducing it during this review took about 40 lines. One gotcha surfaced: game.css contains backslashes, so inlining it with `re.sub(pattern, css_string, …)` raises "invalid group reference". A function replacement (`lambda m: …`) is needed. The new header markup and the logo file also have to sit next to the rendered HTML.
- **Fix**: Either add the gotcha to Testing Strategy step 5, or treat the plan's original measurement (independently confirmed here: 874px) as sufficient and re-measure only if the CSS values deviate, which the Critical Implementation Details already say.
- **Decision**: PENDING (open item; current wording is workable)

### F4 — Clickable sponsor link on the booth kiosk

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW (quick decision; the fix is obvious and narrowly scoped)
- **Dimension**: Blind Spots
- **Location**: Phase 2, §1 Hall template header
- **Detail**: The hall's `<a class="hall-sponsor" target="_blank">` follows the handoff. If the booth display is a touchscreen, or a mouse is reachable, a passer-by tap opens camlingroup.com in a new tab over the board. The board stays hidden until staff switch tabs back. A non-interactive kiosk is not affected.
- **Fix**: Confirm the booth screen is non-interactive. If it is not, render the hall sponsor as a non-link block (`<div>`), keeping the visual design.
- **Decision**: PENDING (open item, which depends on booth hardware)
