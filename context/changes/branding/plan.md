# Camlin Branding (Sponsor Logo + Link) Implementation Plan

## Overview

Add the Camlin Group logo and a clickable `camlingroup.com` link to bash-dash, as specified in the Claude Design handoff `context/changes/branding/design_handoff_bash_dash_ui/CAMLIN_LOGO.md`. Players see a small sponsor footer on the gate, home, play and done screens. The hall-of-fame booth screen gets a large logo with the URL in its header. The staff prize-desk and moderation pages stay unbranded. Only templates, `game.css`, one new static image and tests change. Game logic, ids and JS stay as they are.

## Current State Analysis

- The full terminal-style redesign from the same handoff (`README.md`) is **already shipped**. It was the archived `context/archive/2026-09-30-ui-redesign/` change. Diffing the archived handoff against this one shows the only new material is the Camlin logo: one line in `README.md` → "Assets", the new `CAMLIN_LOGO.md`, `assets/camlin-logo.png`, and sponsor markup added to screens 01–05 of `bash-dash Screens.dc.html`. `support.js` is identical. This plan therefore covers `CAMLIN_LOGO.md` only.
- `game/templates/game/base.html:10-16`: `<main class="{% block main_class %}">` holds `{% block header %}` and `{% block content %}` directly. There is no sponsor block yet. Every page template extends it: gate, home, play, done, `staff/lookup`, `staff/moderate`, `staff/hall`.
- `game/static/game/game.css:42-46`: `main` is a plain block (`max-width: 44rem; padding: 18px 18px 32px`). Page spacing relies on **vertical margin collapsing** between the logo/brand header and the first content element. Examples: `.logo { margin: 0 0 16px }` followed by `h1.rule { margin: 20px 0 12px }` on home.
- `game/static/game/game.css:293-342`: hall styles. `.hall-header` is a flex row with `align-items: flex-end` (logo left, tagline right), `main.hall { padding: 44px 56px }` and `.hall .hall-row { padding: 7px 8px }`.
- `game/templates/game/staff/hall.html:5-8` overrides `{% block header %}` with the logo and tagline.
- **Conflicting guard test**: `game/tests/test_views.py:19` (`EXTERNAL_LINK` regex) and `:332-344` (`NoAnswerLinksTests.test_pages_contain_no_external_links`) fail on **any** `<a href="http(s)://…">` on gate, home, play and done. The test enforces the PRD non-goal "Na stronie nie może być żadnego linku prowadzącego do odpowiedzi" (`context/foundation/prd.md:211-213`): no link on the page may lead to answers. A sponsor link does not lead to answers, but the test as written will fail once the footer lands.
- Static files: WhiteNoise middleware (`config/settings.py:58`), default storage (no manifest hashing), `collectstatic` runs at Docker build (`Dockerfile:28`). A new file under `game/static/game/` is picked up automatically.
- Baseline: `uv run python manage.py test game` passes, 174 tests (2026-10-01).

## Desired End State

- `game/static/game/camlin-logo.png` exists (copied from the handoff, 720×240, transparent).
- The gate, home, play and done pages end with a centred sponsor footer: the 22px-tall logo plus an underlined cyan `camlingroup.com`, linking to `https://camlingroup.com/` with `target="_blank" rel="noopener"`. On short pages the footer sits at the bottom of the viewport. On long pages it sits below the content. Existing spacing on these pages is unchanged.
- `staff/lookup` and `staff/moderate` show no sponsor footer.
- In the hall screen header, the ASCII logo has the tagline ("5 minutes · bash only ·" + cursor) **below** it on the left. The right side shows the 88px Camlin logo with `camlingroup.com` (22px, cyan) under it. With 10 top rows and 5 recent rows, everything still fits in 1600×900 without scrolling. The ≤900px stacked layout still works.
- The external-link guard still fails for any external host **other than** `camlingroup.com`. New tests prove the footer is on the player pages, is absent on the staff pages, and that the hall carries the large logo.
- `uv run python manage.py test` and `uv run python manage.py check` pass.

### Key Discoveries:

- The handoff's direct `main:not(.hall) { display: flex; flex-direction: column }` would turn every child of `main` into a flex item. Flex items do not collapse margins, so gaps grow on gate (+4px), done (+4px) and home (+16px, logo 16 + `h1.rule` 20 no longer collapse to 20). The handoff itself notes "If the flex `main` change affects existing layouts…". It does, so the plan wraps header + content in one block-flow wrapper and makes only that wrapper and the footer flex items.
- Hall fit was measured, not estimated. Headless Chrome rendered `hall.html` with 10 top / 5 recent rows at 1600×900. Measured content heights: today **889px**. With the handoff's header as specified, **936px**: row #10 and the 5th recent row fall off-screen. With the handoff's fallback (`.hall-header` margin-bottom 24px), **928px**, still overflowing. The combination of `main.hall { padding: 32px 56px }`, `.hall-header { margin-bottom: 24px }` and `.hall .hall-row { padding: 5px 8px }` gives **874px**, leaving 26px of headroom.
- `play.js` / `hall.js` address elements only by id (`game/static/game/play.js:8-20`, `hall.js:3-4`). A wrapper element around the page content does not affect them.
- `test_staff_views.py:196-199` asserts the hall board fragment `_board.html` has no `<html`. The sponsor block lives in `base.html` and the hall header in `hall.html`, so the fragment is unaffected.

## What We're NOT Doing

- Re-applying the main UI redesign (already shipped in `ui-redesign`).
- Changing game logic, views, URLs, ids, `play.js` or `hall.js`.
- Optimising or re-encoding the PNG (49 KB, one browser-cached request per player). Shipped as-is per the handoff.
- Adding the logo to staff prize-desk/moderation pages or to Django admin.
- Adding "Camlin" text next to the image (the image already contains the wordmark).
- Recruiting CTAs or any other copy (PRD non-goal "Brak CTA rekrutacyjnego").
- Visual-regression tooling. Visual checks stay manual, as in `ui-redesign`.

## Implementation Approach

Two small phases, each independently shippable and testable:

1. **Player sponsor footer**: asset, `base.html` sponsor block plus layout wrapper, CSS, empty overrides on the staff pages, and test updates. This is where the external-link guard is narrowed, so the suite stays green in the same phase.
2. **Hall header branding**: restructure the hall header, add the large logo, and apply the measured tightening so 1600×900 still fits.

## Critical Implementation Details

- **User experience spec (layout wrapper)**: do not make header and content direct flex items of `main`. Wrap `{% block header %}` and `{% block content %}` together in one block-level wrapper (e.g. `<div class="page">`) inside `main`. Make `main:not(.hall)` the flex column with `min-height: 100vh; min-height: 100dvh` (the `vh` line is the fallback). Give the sponsor `margin-top: auto`. Inside the wrapper, normal block flow and margin collapsing are preserved, so every current gap stays pixel-identical.
- **Performance constraints (hall fit)**: the 1600×900 budget is tight. If the implementer deviates from the measured values (padding 32px 56px, header margin-bottom 24px, row padding 5px 8px), re-measure with 10 top + 5 recent rows (see Testing Strategy). The measurement is the content height; a kiosk in fullscreen has the full 900px.

## Phase 1: Player Sponsor Footer

### Overview

Ship the logo asset and the sponsor footer on gate, home, play and done. Keep it off the staff pages. Make the tests reflect the new allowed link.

### Changes Required:

#### 1. Static asset

**File**: `game/static/game/camlin-logo.png`

**Intent**: Copy `context/changes/branding/design_handoff_bash_dash_ui/assets/camlin-logo.png` byte-for-byte into the app's static directory.

**Contract**: New static path `game/camlin-logo.png` (served by WhiteNoise, collected at Docker build).

#### 2. Base template

**File**: `game/templates/game/base.html`

**Intent**: Add an overridable sponsor footer after the page content, and wrap header + content so the footer can be pushed to the viewport bottom without changing existing spacing.

**Contract**: Inside `<main>`: a wrapper element (class e.g. `page`) containing the existing `{% block header %}` and `{% block content %}`, followed by `{% block sponsor %}`. The block's default content is the handoff markup: `<a class="sponsor" href="https://camlingroup.com/" target="_blank" rel="noopener">` with `<img src="{% static 'game/camlin-logo.png' %}" alt="Camlin Group" width="66" height="22">` and `<span>camlingroup.com</span>`. `{% load static %}` is already present on line 1.

#### 3. Staff page overrides

**Files**: `game/templates/game/staff/lookup.html`, `game/templates/game/staff/moderate.html`, `game/templates/game/staff/hall.html`

**Intent**: Suppress the player footer on all staff screens. The hall gets its own large logo in Phase 2.

**Contract**: Each template adds an empty `{% block sponsor %}{% endblock %}`.

#### 4. Styles

**File**: `game/static/game/game.css`

**Intent**: Style the footer per the handoff and pin it to the bottom on short pages.

**Contract**: `main:not(.hall)` becomes a flex column with `min-height: 100vh` and then `min-height: 100dvh`. `.sponsor` uses `margin-top: auto; padding-top: 16px; border-top: 1px solid var(--border-soft)`, centred flex with a 12px gap, `font-size: 13px`, no underline on the anchor. `.sponsor img`: `height: 22px; width: auto; display: block`. `.sponsor span`: cyan, underlined, `text-underline-offset: 3px`. Optionally give the wrapper `margin-bottom` (~32px) so long pages keep breathing room above the footer rule. Do **not** change the `main` padding or any existing rule.

#### 5. Tests

**File**: `game/tests/test_views.py`

**Intent**: Keep the "no answer links" guard meaningful while allowing the single sponsor link, and add explicit coverage for the footer.

**Contract**:
- Narrow `NoAnswerLinksTests` so that the only external `<a href>` allowed on gate/home/play/done points to the host `camlingroup.com` (scheme `https`). Any other external host still fails. Suggested approach: collect all external hrefs with a capturing regex and assert each host equals `camlingroup.com`, rather than deleting the guard.
- Add a test that each of gate (no token), home (with token), play and done contains `class="sponsor"`, `href="https://camlingroup.com/"`, `rel="noopener"` and `alt="Camlin Group"`.
- Add a test that `django.contrib.staticfiles.finders.find('game/camlin-logo.png')` returns a path.

**File**: `game/tests/test_staff_views.py`

**Intent**: Prove the footer is absent on staff pages.

**Contract**: For a logged-in staff client, `staff_lookup` and `staff_moderate` responses do not contain `class="sponsor"`. For the hall, assert `class="sponsor"` is absent too (the Phase 2 test covers the hall's own logo).

### Success Criteria:

#### Automated Verification:

- Full test suite passes: `uv run python manage.py test`
- Django check passes: `uv run python manage.py check`
- Logo is collected: `uv run python manage.py findstatic game/camlin-logo.png`
- Narrowed guard still bites: temporarily adding `<a href="https://example.com/">` to `home.html` makes `NoAnswerLinksTests` fail (revert after checking)

#### Manual Verification:

- At 390px width, the gate, home, play and done pages show the footer centred at the bottom, with logo and underlined cyan URL, matching screens 01–05 of `bash-dash Screens.dc.html`
- Spacing above and between existing elements on gate, home and done is unchanged from before (compare with `git stash`)
- On a long play page (long output), the footer sits below the output panel, not overlapping
- Tapping the link opens camlingroup.com in a new tab; the game tab keeps running
- Prize desk and moderation pages show no footer

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Hall Header Branding

### Overview

Restructure the hall header so the large Camlin logo and URL sit top-right, with the tagline under the ASCII logo. Tighten spacing so the full board still fits 1600×900.

### Changes Required:

#### 1. Hall template header

**File**: `game/templates/game/staff/hall.html`

**Intent**: Move the tagline under the ASCII logo and add the large sponsor link on the right.

**Contract**: `{% block header %}` becomes `<header class="hall-header">` containing a `<div class="hall-brand">` (the `_logo.html` include plus the existing `hall-tagline` paragraph, unchanged) and an `<a class="hall-sponsor" href="https://camlingroup.com/" target="_blank" rel="noopener">` with `<img src="{% static 'game/camlin-logo.png' %}" alt="Camlin Group" width="264" height="88">` and `<span>camlingroup.com</span>`. `{% load static %}` is already loaded. Keep `#board`, `#hall-status` and the scripts block untouched.

#### 2. Hall styles

**File**: `game/static/game/game.css`

**Intent**: Apply the handoff's hall header CSS and the measured spacing reductions that keep 1600×900 scroll-free.

**Contract**:
- Handoff rules: `.hall-header { align-items: flex-start }` (was `flex-end`). `.hall-brand`: flex column, gap 14px. `.hall-sponsor`: flex column, `align-items: flex-end`, gap 12px, no underline. `.hall-sponsor img`: height 88px, auto width, block. `.hall-sponsor span`: 22px, cyan.
- Fit: change `main.hall` padding to `32px 56px` (was `44px 56px`), `.hall-header` margin-bottom to `24px` (was `32px`) and `.hall .hall-row` padding to `5px 8px` (was `7px 8px`).
- In the existing `@media (max-width: 900px)` block: `.hall-sponsor { align-items: flex-start }` and `.hall-sponsor img { height: 48px }`.

#### 3. Tests

**File**: `game/tests/test_staff_views.py`

**Intent**: Lock in the hall branding.

**Contract**: The staff hall page contains `class="hall-sponsor"`, `href="https://camlingroup.com/"` and `alt="Camlin Group"`, and still contains the `hall-tagline` text. The `hall_board` fragment still has no `<html` (existing test) and no `hall-sponsor`.

### Success Criteria:

#### Automated Verification:

- Full test suite passes: `uv run python manage.py test`
- Django check passes: `uv run python manage.py check`
- Hall content height at 1600×900 with 10 top + 5 recent rows is ≤ 900px (headless-Chrome measurement, see Testing Strategy)

#### Manual Verification:

- On the 1600×900 booth screen (fullscreen), the hall matches screen 02 of `bash-dash Screens.dc.html`: Camlin logo top-right with URL under it, tagline under the ASCII logo. All 10 top rows and 5 recent rows are visible, with no scrollbar.
- At ≤900px width, the header stacks and the logo shrinks to 48px, left-aligned
- Board polling (`hall.js`) still refreshes rows and the `hall-status` badge still appears bottom-right on errors

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- External-link guard narrowed to an allowlist of `camlingroup.com`; any other external host still fails.
- Sponsor footer present on gate, home, play and done; absent on lookup, moderate and hall.
- Hall page has `hall-sponsor`; board fragment does not.
- Static finder resolves `game/camlin-logo.png`.

### Integration Tests:

- None new. Existing view/integration tests must stay green, as they exercise all affected templates.

### Manual Testing Steps:

1. `uv run python manage.py runserver` and open gate → home → play → done at 390px width in DevTools. Check the footer position and that existing gaps are unchanged.
2. On play, run a command with long output and confirm the footer stays below the output panel.
3. Log in as staff: prize desk and moderation have no footer.
4. Hall at 1600×900 in fullscreen, with at least 10 finished games (e.g. via `bench_game` or the admin). Check all rows are visible and compare with mockup screen 02.
5. Hall fit measurement (automatable): render `game/staff/hall.html` via `render_to_string` with a `services.Board` of 10 top + 5 recent `BoardRow`s. Load it as a file alongside a copy of `game.css` in `google-chrome --headless=new --window-size=1600,900 --dump-dom`, with a script that writes `document.documentElement.scrollHeight` into `document.title`. The expected value is ~874px.

## Performance Considerations

One extra 49 KB PNG request per player page view. It is cached by the browser across gate → home → play → done, and the width/height attributes prevent layout shift. Acceptable for booth Wi-Fi/mobile; re-encoding is explicitly out of scope.

## Migration Notes

None. No data or schema changes. Static file is picked up by `collectstatic` at the next image build.

## References

- Design handoff: `context/changes/branding/design_handoff_bash_dash_ui/CAMLIN_LOGO.md`, `README.md` ("Assets"), `bash-dash Screens.dc.html` (screens 01–05)
- Prior redesign: `context/archive/2026-09-30-ui-redesign/plan.md`
- External-link guard origin: `context/archive/2026-09-29-first-sandboxed-command/plan.md:346,395`; PRD non-goals `context/foundation/prd.md:201-213`
- Base layout: `game/templates/game/base.html:10-16`; hall CSS `game/static/game/game.css:293-342`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Player Sponsor Footer

#### Automated

- [ ] 1.1 Full test suite passes: `uv run python manage.py test`
- [ ] 1.2 Django check passes: `uv run python manage.py check`
- [ ] 1.3 Logo is collected: `uv run python manage.py findstatic game/camlin-logo.png`
- [ ] 1.4 Narrowed guard still bites: temporary `https://example.com/` link makes `NoAnswerLinksTests` fail

#### Manual

- [ ] 1.5 Footer at bottom on gate/home/play/done at 390px, matches mockup screens 01–05
- [ ] 1.6 Existing spacing on gate/home/done unchanged
- [ ] 1.7 Footer below output on a long play page
- [ ] 1.8 Link opens camlingroup.com in a new tab; game tab keeps running
- [ ] 1.9 No footer on prize desk and moderation

### Phase 2: Hall Header Branding

#### Automated

- [ ] 2.1 Full test suite passes: `uv run python manage.py test`
- [ ] 2.2 Django check passes: `uv run python manage.py check`
- [ ] 2.3 Hall content height at 1600×900 with 10 top + 5 recent rows ≤ 900px

#### Manual

- [ ] 2.4 Booth screen matches mockup screen 02; all rows visible without scroll
- [ ] 2.5 ≤900px layout stacks with 48px left-aligned logo
- [ ] 2.6 Board polling and hall-status badge still work
