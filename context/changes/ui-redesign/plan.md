# Web UI Redesign Implementation Plan

## Overview

Restyle all seven screens (play, gate, home, done, hall of fame, prize desk, moderation) to the terminal design in `context/changes/ui-redesign/design_handoff_bash_dash_ui/`: dark background, four accents (pink, cyan, lime, yellow), an ASCII-art logo, and a "correct answer" effect. This is presentation only. Element ids, form actions and names, `data-*` attributes, views, URLs and logic do not change.

## Current State Analysis

- One stylesheet, `game/static/game/game.css` (186 lines), with a GitHub-dark palette and a sans-serif body font. The design wants a monospace body font and a different palette.
- `base.html` renders a fixed `<header class="brand">$ bash-dash</header>` on every page. The design needs a small header (play, staff) or a full ASCII logo (gate, home, done, hall).
- `play.html` keeps `#challenge-index` inside the challenge section and renders counters as inline `<span>`s. The design puts the index in a header badge and the counters in three boxes.
- `play.js` sets verdict text and class through `setVerdict()` (`verdict.className = 'verdict' + cls`). It does not restart animations, and it never touches the command box or the counters' classes.
- `_board.html` is polled and swapped into `#board` by `hall.js` (`board.innerHTML = html`). Its section order is top, recent, QR. The design's right column puts the QR card above "Just finished".
- The design's mockup file is a React-based design tool, not production code; only its inline styles and the README's tokens are used.

## Desired End State

Every screen matches the mockup at 390px (phone) and, for the hall, 1600×900. The play screen shows the pop/glow effect on a correct answer. `python manage.py test` passes, with only the test assertions listed below adjusted. Verified by the manual checks in each phase.

### Key Discoveries:

- `game/tests/test_views.py:458` asserts `Attempts:\s*<strong>3</strong>` and `:459` asserts `class="prize-code"` on the done page. The design's key/value rows need a label span, so the first assertion is adjusted (approved). `class="prize-code"` stays.
- `game/tests/test_staff_views.py:87` asserts `Solve time: <strong>—</strong>` on the prize desk. Adjusted the same way.
- `game/tests/test_staff_views.py:170,181` require that hall pages contain `3 / `, `#1`, `#2`, `#4`, never `#3` (a shared-place fixture), and that a nick renders as `>ann<` (its own element with no extra whitespace). Keep nick and place in separate elements and avoid adding text like `#3` anywhere in the fragment.
- `game/tests/test_views.py:62,128` require `class="error"` on the home page; `test_views.py:48-52` require `name="nick"`, `maxlength="20"`, `Start`, `attempt`, `5 minutes`. `Start ▸` still satisfies the `Start` check.
- `play.js` compares `#challenge-index`'s text against `ch.index + ' / ' + ch.total` to detect a new challenge (`play.js:90`). The index must stay unpadded in the DOM, so the design's optional "07 / 38" is not used.
- Verdict text comes from the server (`views.py:144,186`) and `play.js`. The ✓ / ✗ / ! / ⣾ glyphs are therefore added through CSS `::before`, not by changing strings.
- `hall.js` swaps `#board`'s children, so all hall layout must be driven by CSS on `#board` and classes inside the fragment; nothing outside `#board` can depend on fragment structure beyond the ids `board` and `hall-status`.

## What We're NOT Doing

- No changes to Python code (views, services, models, urls, template tags), `hall.js`, or any id, `data-*` attribute, form action, name or CSRF token.
- No web fonts, images or icon assets. The logo is text.
- No zero-padding of the challenge index (would break `play.js` comparison).
- No cursor overlay on gate, home or lookup inputs.
- No automated screenshot or visual-regression tooling; visual checks are manual.

## Implementation Approach

Build the shared foundation first (tokens, base template, logo include, shared component classes), then convert screens in priority order: play, player pages, hall, staff. Existing class names are kept where they exist, and new ones are added as needed. Each phase leaves the app working and the tests green, so any phase can be reviewed on its own.

## Critical Implementation Details

- **Cursor overlay:** the empty `#command` input needs a whitespace `placeholder=" "` so `:placeholder-shown` can toggle the blinking overlay, and `caret-color: transparent` while the placeholder is shown so the native caret and overlay don't double up. The overlay element has `pointer-events: none` and `aria-hidden="true"`, and is positioned absolutely inside the bordered command box, which gets `position: relative`.
- **Timer box border:** `#timer` is a child of the counter box, and `#timer.low` must also colour the box's border. Use `.counter:has(#timer.low)`, no JS.
- **Verdict animation trigger:** `play.html` renders `class="verdict ok"` server-side after a correct answer, so animations on `.verdict.ok` would replay on every reload or bfcache restore. Put `pop`/`glow` on a JS-only class, `.verdict.ok.celebrate`. The helper adds `celebrate` after `setVerdict(...)` using remove, `void el.offsetWidth`, add, so each correct answer restarts the animation explicitly. `setVerdict()` clears it on the next answer because it reassigns `className`.

## Phase 1: Foundation

### Overview

Replace the palette and typography, add shared components, and split `base.html`'s header so later phases can choose the small or full variant. Existing screens should look coherent (new colours and font) even before their own phase.

### Changes Required:

#### 1. Design tokens and base styles

**File**: `game/static/game/game.css`

**Intent**: Replace `:root` variables with the design tokens (bg, panel, code-bg, border, border-soft, leader, fg, fg-2, muted, ink, pink, cyan, lime, yellow, red border/text). Define the accent tokens as hex (converted once from the design's oklch values), not oklch(), so unsupported browsers don't lose button backgrounds; oklch versions may be added only inside `@supports (color: oklch(0 0 0))`. Make the body font monospace, and restyle `code`, `pre`, links, inputs (pink border on focus, 16px+ font, pink caret), primary buttons (min-height 48, pink, ink text, radius 10) and headings.

**Contract**: Keep current class names in use (`.brand`, `.counters`, `.verdict`, `.output`, `.prize-code`, `.notice-*`, `.hall*`, `.mod-row`, etc.). Add shared classes: `.badge` (with colour modifiers), `.rule` (section rule: label plus a flexible border line), `.kv` (label · dotted leader · value), `.cursor` (blinking block, `@keyframes blink`), `.logo` (gradient ASCII text). All animations respect `prefers-reduced-motion`.

#### 2. Header block and logo include

**Files**: `game/templates/game/base.html`, new `game/templates/game/_logo.html`

**Intent**: Give `base.html` a `{% block header %}` whose default is the small header (`$` in pink, "bash-dash" in gradient text, and a `{% block badge %}` slot on the right). `_logo.html` holds the full ASCII logo `<pre class="logo">` from the design, with `>` escaped as `&gt;`.

**Contract**: Pages needing the full logo override `{% block header %}` with `{% include 'game/_logo.html' %}`. The logo scales with `font-size: clamp(9px, 2.6vw, 17px)` and stays ≈9.4px at 390px so 59 columns fit.

### Success Criteria:

#### Automated Verification:

- Full test suite passes: `uv run python manage.py test`
- Django check passes: `uv run python manage.py check`

#### Manual Verification:

- All existing pages render with the new dark palette and monospace font, with no broken layout
- Logo renders on one line per row at 390px, no horizontal page scroll

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Play screen and correct-answer effect

### Overview

The priority screen: header badge, counter boxes, challenge block, command box, verdict, output panel, and the effect on correct answers.

### Changes Required:

#### 1. Play template

**File**: `game/templates/game/play.html`

**Intent**: Move `#challenge-index` into the header's badge slot (pink badge). Turn each counter into a box with an uppercase label (ATTEMPTS, SOLVED, TIME) and a value: attempts cyan, solved lime, time fg. Keep `#counters` with `data-attempts`, and the ids `attempts`, `solved`, `timer` (with `data-remaining-ms`). Wrap the `$` and input in a bordered box inside `#command-form`, and add the cursor overlay element after `#command` (with `placeholder=" "`). Wrap `#last-command` and `#output` in the panel: a header strip showing `$ <last command>` above the `<pre>`.

**Contract**: All ids, `data-*` attributes, `name`/`maxlength`/`autocapitalize` attributes and the `autofocus` condition remain unchanged. `#challenge-index` keeps the text `{{ info.index }} / {{ info.total }}`. `#last-command` keeps its current text content format `$ <command>` (JS writes `'$ ' + command`), so the panel strip must not add a second `$`.

#### 2. Play styles

**File**: `game/static/game/game.css`

**Intent**: Style the counters grid (3 columns, boxes with radius 10), `#timer.low` yellow text and border via `:has()`, the challenge block (h1 21px, description `fg-2`, code and pre styles), the command box (panel background, 1.5px pink border, radius 10), the Run button, and the output panel (header strip 13px muted, `pre` 13.5px, min-height 96px, max-height 50vh).

**Contract**: Verdict states: `.running` muted with `::before "⣾ "`; `.bad` red bold with `::before "✗ "`; `.warn` yellow with `::before "! "`; `.ok` lime badge (lime background, ink text, padding 2px 10px, radius 6, `width: fit-content`) with `::before "✓ "`. Glyphs apply only when the verdict is non-empty. `.flash` on `#command-form` and on `#counters` switches the command box border and the SOLVED box border to lime (0.3s transition). Keyframes `pop` (0.45s, scale 0.6 → 1.08 → 1, opacity 0 → 1) and `glow` (0.9s, lime box-shadow ring 0 → 14px fading out) apply to `.verdict.ok.celebrate` (a class added only by JS, never rendered by the server). Under `prefers-reduced-motion` the animations are disabled but the border flash colour may remain.

#### 3. Correct-answer effect

**File**: `game/static/game/play.js`

**Intent**: When a response has `data.result.correct`, restart the verdict badge's animation (add the `celebrate` class) and add `flash` to `#command-form` and `#counters` for 1.1 s, then remove it. Change nothing else in the file.

**Contract**: Add one small helper called from `render()` in the correct branch after `setVerdict(...)`. Restarting the animation: remove `celebrate`, read `void verdict.offsetWidth`, then add `celebrate`. Guard the timeout so overlapping correct answers don't clear a newer flash early (store and clear the previous timer). No changes to `busy`/`locked`/timer/resync logic.

### Success Criteria:

#### Automated Verification:

- Full test suite passes: `uv run python manage.py test`
- JS syntax check passes: `node --check game/static/game/play.js`

#### Manual Verification:

- Play screen matches the mockup at 390px: header badge, three counter boxes, command box, Run button, output panel
- Wrong answer shows red "✗ …"; network/warn shows yellow "! …"; running shows "⣾ Running…"
- Correct answer shows the lime "✓ …" badge with pop and glow, and the command and SOLVED borders flash lime for about 1 s
- Two correct answers in a row both play the animation
- Timer at or under 30 s turns yellow with a yellow box border
- The cursor overlay shows in the empty input, hides once you type, and the native caret is not doubled
- With OS "reduce motion" on, no pop/glow/blink animation runs
- Challenge switch after a correct answer still updates title, description and index and clears the input

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Player pages (gate, home, done)

### Overview

The three remaining player-facing pages, using the full logo.

### Changes Required:

#### 1. Gate

**File**: `game/templates/game/gate.html`

**Intent**: Full logo header, h1, a red notice (with ✗) for expired or invalid code, help text in `fg-2`, an uppercase CODE label, a 22px letter-spaced input, and the Continue button.

**Contract**: Keep `id="code"`, `name="t"`, `method="get"`, `action`, `pattern`, `maxlength`. The notice may use `notice-bad`; the tests check only the notice text on the gate page.

#### 2. Home

**File**: `game/templates/game/home.html`

**Intent**: Full logo, a cyan "How to play" badge with a section rule, rules list with pink `›` markers (no bullets), `ls`/`cat` as cyan code, the duration in yellow bold, label YOUR NICK, input, and a `Start ▸` button (min-height 52). `.error` stays as red text under the input.

**Contract**: Keep `class="error"` exactly, the hidden `t` input, the csrf token, and the text `Start` in the button. Wrap the duration in an element for the yellow colour without changing `duration_text` output.

#### 3. Done

**File**: `game/templates/game/done.html`, `game/tests/test_views.py`

**Intent**: Full logo, a yellow h1, "Well played, <nick>.", a stats box with `.kv` rows (Solved lime, Attempts cyan, Place pink), the dashed yellow prize box (label PRIZE CODE, 50px code with `user-select: all`, the two instruction lines), and the muted note.

**Contract**: Keep `class="prize-code"`. Rows become `<span class="k">Attempts</span><span class="leader"></span><strong>3</strong>`, so update the assertion at `test_views.py:458` to match the new markup to `r'Attempts</span>\s*<span class="leader"></span>\s*<strong>3</strong>'` (anchored to the markup, no DOTALL). No other test changes.

### Success Criteria:

#### Automated Verification:

- Full test suite passes: `uv run python manage.py test`

#### Manual Verification:

- Gate (with no code, an expired code and an invalid code), home (with and without a nick error) and done (time's up, all solved, finished; ranked and not ranked) match the mockup at 390px
- Prize code is easy to select and copy in one tap
- Logo fits without horizontal scroll at 320–390px, and scales up on a desktop-width window

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 4: Hall of fame

### Overview

The booth screen (1600×900) and its polled fragment.

### Changes Required:

#### 1. Hall page and fragment

**Files**: `game/templates/game/staff/hall.html`, `game/templates/game/staff/_board.html`

**Intent**: In `hall.html`, override the header block with a row: full logo on the left, muted text "5 minutes · bash only ·" plus a blinking cursor on the right. In `_board.html`, add the classes needed for the section rules (pink "HALL OF FAME" badge, lime "JUST FINISHED" badge), podium ranks (#1 yellow badge and yellow nick, #2 cyan, #3 pink), and the QR card (tile, "Scan to play", code).

**Contract**: `#board` keeps `data-board-url` and `data-refresh-ms`; `#hall-status` keeps `hidden` and its id. Fragment order stays top, recent, qr; the two-column layout is done in CSS grid on `#board` (top spans two rows in the left column, QR then recent in the right). Nick stays alone in its element (`>ann<`), and no `#N` text beyond the actual places is introduced. The `5 minutes` tagline text is static, as in the mockup.

#### 2. Hall styles

**File**: `game/static/game/game.css`

**Intent**: Padding 44/56, `#board` grid `minmax(0,1fr) 560px` with gap 64 (row gap 40), rows 30px with the place/nick/solved/att. columns from the README, places 4+ in lime, QR tile 236px white with the pink ring and glow, code 46px bold yellow, "Just finished" rows 26px, and `.hall-status` restyled (panel background, yellow or red border). Keep the `@media (max-width: 900px)` single-column stacking.

**Contract**: The hall page's existing 110rem (1760px) width cap already fits the 1600px layout; no change needed.

### Success Criteria:

#### Automated Verification:

- Full test suite passes: `uv run python manage.py test`

#### Manual Verification:

- At 1600×900 the hall matches the mockup with about 10 top rows and 5 recent rows (HALL_RECENT_N), with no scrolling
- Long nicks are ellipsised; the QR is readable and scannable from a phone
- Polling refresh keeps the layout intact (wait for one refresh), and the "Reconnecting…" badge appears bottom-right when the server is stopped
- Below 900px the layout stacks into one column

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 5: Staff pages (prize desk, moderation)

### Overview

The two phone-first staff screens, with the small header and a yellow STAFF badge.

### Changes Required:

#### 1. Prize desk

**Files**: `game/templates/game/staff/lookup.html`, `game/tests/test_staff_views.py`

**Intent**: Small header with the STAFF badge, h1, cyan nav links separated by `·`, notices with ✓ / ! / ✗ prefixes (CSS), the lookup row (24px letter-spaced code input plus the "Look up" button), the card (nick 30px bold yellow, muted hint, `.kv` stats for Solved, Attempts, Place, Solve time, muted "Finished … ago", a lime "Mark prize given" button at min-height 56 / 18px), the already-given notice, and Log out as a muted underlined text button.

**Contract**: Keep `name="code"`, `inputmode="numeric"`, `maxlength="7"`, form actions, csrf tokens, the hidden `code` input, and the button texts. The `Solve time` row markup changes to the `.kv` structure, so update `test_staff_views.py:87` to `r'Solve time</span>\s*<span class="leader"></span>\s*<strong>—</strong>'`. `Solved`, `Attempts`, `#1 of 1`, `1:15` and `not ranked` must still appear in the response.

#### 2. Moderation

**File**: `game/templates/game/staff/moderate.html`

**Intent**: Same header and nav, cyan section rules (Start QR, On screen: top N, On screen: just finished, Hidden), the lifetime row (72px right-aligned number input plus Save), `#place` lime, nick ellipsis, `solved/total · att.` at 12px muted, Hide buttons (transparent, red border and text, min-height 44), and Hidden rows with a struck-through muted nick and an Unhide button (transparent, border, fg).

**Contract**: Keep `id="minutes"`, `name="minutes"`, `game_id` hidden inputs, form actions, `hide-button`/`unhide-button` classes, and the texts asserted by tests (`Hall of fame moderation`, `Unhide`, `No hidden games`, notice messages). Row markup must keep the `>ann<` nick form only where tests check it (hall only).

### Success Criteria:

#### Automated Verification:

- Full test suite passes: `uv run python manage.py test`
- Django check passes: `uv run python manage.py check`

#### Manual Verification:

- Prize desk matches the mockup in its states: empty, found and finished, already given, in progress, unranked or hidden, and error/success notices
- Moderation matches the mockup with top, recent and hidden lists populated and empty
- Buttons are comfortable to tap at 390px (44/56 px targets), with no horizontal scroll
- Hide, Unhide, Mark prize given and Save still work end to end

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding.

---

## Testing Strategy

### Unit Tests:

- The existing suite is the regression net for markup contracts (ids, names, texts). Only the two assertions named above change (`test_views.py:458`, `test_staff_views.py:87`), and only to fit the `.kv` markup.
- No new automated tests for CSS. Optionally add one assertion that the play page still contains all ids listed in the design README; skip if the existing tests already cover them.

### Integration Tests:

- `game/tests/test_integration.py` is untouched; run it only if the Docker sandbox is available.

### Manual Testing Steps:

1. Run the dev server, open the gate, get a start token from the hall page, and play through: home → play → done.
2. On play, try a wrong command, an empty command, a correct command (twice in a row), and let the timer drop under 30 s.
3. Open the hall at 1600×900 and at 800px; wait for one refresh.
4. Log in as staff and exercise the prize desk and moderation states.
5. Repeat the play screen with OS "reduce motion" enabled.

## Performance Considerations

No new requests, fonts or images. The gradient logo is text. Keep CSS in the single existing stylesheet.

## Migration Notes

None. Static files are served by WhiteNoise; rebuild or `collectstatic` as the existing Docker flow already does.

## References

- Design handoff: `context/changes/ui-redesign/design_handoff_bash_dash_ui/README.md` and `bash-dash Screens.dc.html`
- Change brief: `context/changes/ui-redesign/change.md`
- Hall polling: `game/static/game/hall.js`
- Verdict rendering: `game/static/game/play.js` (`setVerdict`, `render`)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Foundation

#### Automated

- [x] 1.1 Full test suite passes: `uv run python manage.py test` — 5d20224
- [x] 1.2 Django check passes: `uv run python manage.py check` — 5d20224

#### Manual

- [ ] 1.3 All existing pages render with the new dark palette and monospace font, with no broken layout
- [ ] 1.4 Logo renders on one line per row at 390px, no horizontal page scroll

### Phase 2: Play screen and correct-answer effect

#### Automated

- [x] 2.1 Full test suite passes: `uv run python manage.py test`
- [x] 2.2 JS syntax check passes: `node --check game/static/game/play.js`

#### Manual

- [ ] 2.3 Play screen matches the mockup at 390px: header badge, three counter boxes, command box, Run button, output panel
- [ ] 2.4 Wrong answer shows red "✗ …"; network/warn shows yellow "! …"; running shows "⣾ Running…"
- [ ] 2.5 Correct answer shows the lime "✓ …" badge with pop and glow, and the command and SOLVED borders flash lime for about 1 s
- [ ] 2.6 Two correct answers in a row both play the animation
- [ ] 2.7 Timer at or under 30 s turns yellow with a yellow box border
- [ ] 2.8 The cursor overlay shows in the empty input, hides once you type, and the native caret is not doubled
- [ ] 2.9 With OS "reduce motion" on, no pop/glow/blink animation runs
- [ ] 2.10 Challenge switch after a correct answer still updates title, description and index and clears the input

### Phase 3: Player pages (gate, home, done)

#### Automated

- [ ] 3.1 Full test suite passes: `uv run python manage.py test`

#### Manual

- [ ] 3.2 Gate (with no code, an expired code and an invalid code), home (with and without a nick error) and done (time's up, all solved, finished; ranked and not ranked) match the mockup at 390px
- [ ] 3.3 Prize code is easy to select and copy in one tap
- [ ] 3.4 Logo fits without horizontal scroll at 320–390px, and scales up on a desktop-width window

### Phase 4: Hall of fame

#### Automated

- [ ] 4.1 Full test suite passes: `uv run python manage.py test`

#### Manual

- [ ] 4.2 At 1600×900 the hall matches the mockup with about 10 top rows and 5 recent rows (HALL_RECENT_N), with no scrolling
- [ ] 4.3 Long nicks are ellipsised; the QR is readable and scannable from a phone
- [ ] 4.4 Polling refresh keeps the layout intact (wait for one refresh), and the "Reconnecting…" badge appears bottom-right when the server is stopped
- [ ] 4.5 Below 900px the layout stacks into one column

### Phase 5: Staff pages (prize desk, moderation)

#### Automated

- [ ] 5.1 Full test suite passes: `uv run python manage.py test`
- [ ] 5.2 Django check passes: `uv run python manage.py check`

#### Manual

- [ ] 5.3 Prize desk matches the mockup in its states: empty, found and finished, already given, in progress, unranked or hidden, and error/success notices
- [ ] 5.4 Moderation matches the mockup with top, recent and hidden lists populated and empty
- [ ] 5.5 Buttons are comfortable to tap at 390px (44/56 px targets), with no horizontal scroll
- [ ] 5.6 Hide, Unhide, Mark prize given and Save still work end to end
