<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Camlin Branding (Sponsor Logo + Link)

- **Plan**: context/changes/branding/plan.md
- **Scope**: Full plan (Phases 1-2 of 2)
- **Date**: 2026-10-01
- **Verdict**: APPROVED
- **Findings**: 0 critical, 1 warning, 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

## Evidence

- Diff `main..HEAD` touches exactly the planned files: `game/static/game/camlin-logo.png`, `game.css`, `base.html`, `staff/{hall,lookup,moderate}.html`, `tests/test_views.py`, `tests/test_staff_views.py`. No unplanned code files. `play.js`/`hall.js`, views, URLs and ids are unchanged, as the plan requires.
- `camlin-logo.png` is byte-identical to the handoff asset (`cmp`).
- `base.html` wraps header and content in `<div class="page">` and adds an overridable `{% block sponsor %}` with the specified markup (66×22 image, `target="_blank" rel="noopener"`). All three staff templates override it with an empty block.
- CSS matches the contract. `main:not(.hall)` is a flex column with a `100vh`/`100dvh` min-height, `.page` has `margin-bottom: 32px` scoped to non-hall pages, and the `.sponsor` rules match the handoff. The hall rules match too: `align-items: flex-start`, `.hall-brand`/`.hall-sponsor`, padding `32px 56px`, header margin `24px`, row padding `5px 8px`, and the ≤900px overrides.
- `hall.html` places the header as `.hall-brand` (logo + tagline) followed by an `a.hall-sponsor` (264×88 image + URL); `#board`, `#hall-status` and the scripts are untouched.
- The external-link guard is narrowed to the exact `https://camlingroup.com/` href, which is stricter than the plan's host-equality check. An extra test, `test_guard_rejects_other_external_hosts`, also covers the regex.

## Success criteria re-run (2026-10-01)

| # | Check | Result |
|---|-------|--------|
| 1.1 / 2.1 | `uv run python manage.py test` | PASS, 243 tests OK |
| 1.2 / 2.2 | `uv run python manage.py check` | PASS, no issues |
| 1.3 | `uv run python manage.py findstatic game/camlin-logo.png` | PASS, found in `game/static/game/` |
| 1.4 | Temporary `<a href="https://example.com/">` inside `home.html`'s content block | PASS: `NoAnswerLinksTests` fails with `'https://example.com/' != 'https://camlingroup.com/'`, then reverted |
| 2.3 | Hall at 1600×900 with 10 top + 5 recent rows, headless Chrome `scrollHeight` | PASS, 874px (matches the plan) |

Manual items: 1.6 and 1.9 are checked. 1.9 is backed by `StaffNoSponsorFooterTests`; for 1.6 see F2. Items 1.5, 1.7, 1.8, 2.4, 2.5 and 2.6 are still pending (F1).

## Findings

### F1 — Six manual verification items still pending

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/branding/plan.md:242-260 (Progress)
- **Detail**: 1.5 (footer at 390px vs. mockup), 1.7 (footer below long play output), 1.8 (link opens a new tab, game keeps running), 2.4 (booth screen vs. mockup 02, no scroll), 2.5 (≤900px stacked layout) and 2.6 (polling and hall-status badge) are unchecked. The automated proxies are strong (fit measured at 874px; markup asserted by tests), but the visual and kiosk checks need a human.
- **Fix**: Run the manual steps from the plan's Testing Strategy (1-4) before merging, and tick the rows.
- **Decision**: OPEN — background review, deferred to the user

### F2 — Item 1.6 evidence covers gate/home/play, but the criterion names done

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/branding/plan.md:243
- **Detail**: The criterion is "Existing spacing on gate/home/done unchanged". The progress note says "before/after element offsets identical on gate/home/play". The done page is not mentioned, so its spacing check is unconfirmed. Risk is low because done uses the same `.page` wrapper, but the checkbox claims more than the note shows.
- **Fix**: Compare offsets on done as well (same headless-Chrome method), or reword the note to match what was measured.
- **Decision**: OPEN — background review, deferred to the user

### F3 — Sponsor-footer test does not pin response status

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: game/tests/test_views.py:356-360
- **Detail**: `test_player_pages_carry_sponsor_footer` calls `assertContains(..., status_code=resp.status_code)`, so it accepts any status. The plan's intent was gate = 403 and the others 200. Status codes are already covered by the existing gate/play/done tests, so this is not a defect; it only weakens this test on its own.
- **Fix**: Pass `status_code=403 if name == 'gate' else 200`.
- **Decision**: OPEN — background review, deferred to the user

### F4 — Staff lookup/moderate pages inherit the flex/min-height layout and the 32px `.page` margin

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: game/static/game/game.css:52-58
- **Detail**: `main:not(.hall)` and `main:not(.hall) .page` also match `staff/lookup` and `staff/moderate`, which have no footer. They now get `min-height: 100dvh` and an extra 32px of bottom whitespace. The plan didn't call this out ("Do not change ... any existing rule" is about player spacing). Visually harmless (trailing space only).
- **Fix**: Accept as is, or scope the rule to pages that render a sponsor (e.g. `.page:has(+ .sponsor)`) if the staff pages should stay pixel-identical.
- **Decision**: OPEN — background review, deferred to the user
