<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Web UI Redesign

- **Plan**: context/changes/ui-redesign/plan.md
- **Scope**: All phases (1–5 of 5)
- **Date**: 2026-09-30
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 6 observations

Automated checks: `uv run python manage.py test` passed (231 tests); `manage.py check` found no issues; `node --check game/static/game/play.js` passed. Plan drift check: every planned item matches, all ids, names, `data-*` attributes, csrf tokens and form actions are kept, and there are no Python or `hall.js` changes. Extras are small and harmless: a hall-only logo `font-size` override, a `.qr-text` wrapper, and a fixed podium `margin-right: 68px`.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

## Findings

### F1 — ASCII logo overflows at phone widths

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: game/static/game/game.css:99-103
- **Detail**: The logo is 59 columns wide, and monospace glyphs are about 0.6em wide. `clamp(9px, 2.6vw, 17px)` gives 10.1px at 390px, which is ≈359px of logo in a 354px content box. At 320px it is ≈319px in 284px. `.logo` sets `overflow: visible`, which overrides `pre`'s `overflow-x: auto`, so gate, home and done scroll sideways. The plan's "≈9.4px at 390px" was wrong: 2.6vw at 390px is 10.1px. This would fail manual checks 1.4 and 3.4.
- **Fix**: `font-size: clamp(5px, calc((100vw - 36px) / 36), 17px)` so the 59 columns always fit inside main's 18px gutters.
- **Decision**: FIXED (Fix now)

### F2 — Command input has no focus cue; caret lost without :has()

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: game/static/game/game.css:153, 208-211
- **Detail**: Inputs drop the outline on focus and use a pink border instead, but the command input has `border: 0` and `.command-box` is always pink, so focus changes nothing. The fake cursor also shows whenever the input is empty, even when it isn't focused (e.g. a reload with `last` set, where there is no autofocus). `caret-color: transparent` is unconditional while the fake cursor depends on `:has()`, so in browsers without `:has()` (Firefox <121, Safari <15.4) an empty input shows no caret at all.
- **Fix**: Show the cursor only on `input:focus:placeholder-shown`, move the caret-color rule inside `@supports selector(:has(*))`, and add a `.command-box:focus-within` ring.
- **Decision**: FIXED (Fix now)

### F3 — Hall tagline hard-codes "5 minutes"

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality (plan flaw)
- **Location**: game/templates/game/staff/hall.html:7
- **Detail**: The plan said to keep this static, as in the mockup, but the game length is configurable (`BASHDASH_GAME_DURATION_S`, config/settings.py:158). home.html renders it with `duration|duration_text`. If the setting changes, the booth screen shows the wrong duration.
- **Fix A ⭐ Recommended**: Drop the number, e.g. "bash only · ▌".
  - Strength: Template-only, so it stays inside the change's no-Python rule and can never be wrong.
  - Tradeoff: Loses the mockup's "5 minutes" hook.
  - Confidence: HIGH — one-line template edit.
  - Blind spot: The design owner may want the duration shown.
- **Fix B**: Add `duration` to the hall context and render `duration_text`.
  - Strength: Exact match to the mockup and always correct.
  - Tradeoff: Touches views.py, which this change ruled out; better as a follow-up.
  - Confidence: HIGH — the same filter is already used on home.
  - Blind spot: The context helper is shared with the board fragment; not checked for side effects.
- **Decision**: FIXED via Fix B (duration added in the `hall` view only, not the shared helper)

### F4 — color-mix() without fallback drops the QR ring

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: game/static/game/game.css:234, 328
- **Detail**: A browser without `color-mix` drops the whole box-shadow value, so the QR loses its 3px pink ring as well as the glow. The plan used hex tokens to avoid exactly this kind of fallback risk.
- **Fix**: Put a `box-shadow: 0 0 0 3px var(--pink);` line before the color-mix one.
- **Decision**: FIXED (Fix now)

### F5 — Hall grid gets squeezed between 900 and ~1150px

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: game/static/game/game.css:299-302
- **Detail**: The right column is fixed at 560px, with 112px of padding and a 64px gap. At 1000px the top-10 column gets about 264px, less than the rows need. This is fine at the target 1600×900.
- **Fix**: Use `minmax(0, 560px)` for the right column, or raise the stacking breakpoint to about 1200px.
- **Decision**: FIXED (Fix now)

### F6 — Accessibility slips: headings, logo label, logout target

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: home.html:6, staff/_board.html:2,15, _logo.html:1, game.css:292
- **Detail**: home.html lost its only heading (the h1 became `div.rule`), and the hall h2s became divs; moderate.html correctly uses `h2.rule`. `aria-label` on a plain `<pre>` isn't reliably announced. The Log out button is about 21px tall, while the plan asks for 44/56px targets.
- **Fix**: Use `<h1 class="rule">` and `<h2 class="rule">`, add `role="img"` to the logo `<pre>`, and give `.logout .link` `min-height: 44px`.
- **Decision**: FIXED (Fix now)

### F7 — celebrate() looks up #counters every time

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: game/static/game/play.js:40, 44
- **Detail**: Every other element in play.js is cached once at the top (lines 8-19).
- **Fix**: Add `var counters = document.getElementById('counters');` to the top-level lookups and use it.
- **Decision**: FIXED (Fix now)

### F8 — Duplicated CSS rules

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: game/static/game/game.css:84-104, 119, 217
- **Detail**: `.logo` repeats the `.gradient-text` block, `.badge.pink` repeats the base badge background, and `.verdict:empty` repeats `.verdict`'s min-height.
- **Fix**: Have `.logo` use `.gradient-text` in _logo.html, and delete the two redundant rules.
- **Decision**: FIXED (Fix now)

### F9 — All 27 manual checks are still pending

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/ui-redesign/plan.md:320-378
- **Detail**: The plan is closed out and change.md says `implemented`, but no manual row is ticked. The work is presentation-only, so these checks are the real acceptance test. F1 would already fail 1.4 and 3.4.
- **Fix**: Run the Manual Testing Steps (390px, 320px, 1600×900, reduced motion) and tick the rows before archiving.
- **Decision**: DONE — user ran the manual checks; plan Progress rows ticked (after F1/F2/F6 fixes)
