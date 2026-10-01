# Handoff: bash-dash Web UI redesign

## Overview
Visual redesign of the bash-dash Django app (hackathon bash challenge game): terminal look, dark background, vivid multi-colour accents, ASCII-art logo. **Functionality does not change** — same views, URLs, element IDs, forms and JS behaviour. Only `game/static/game/game.css` and the templates under `game/templates/game/` change (markup/classes), plus small additions in `play.js` for the "correct" effect.

## About the Design Files
`bash-dash Screens.dc.html` is a **design reference built in HTML** (opens in a browser), not production code. Recreate it in the existing Django templates + one stylesheet. All mockup styles are inline; in the real app move them into classes in `game.css` (keep existing class names where they exist, add new ones as needed).

**Keep intact** (used by `play.js` / `hall.js` / tests): ids `command-form`, `command`, `submit`, `verdict`, `last-command`, `output`, `attempts`, `solved`, `timer`, `challenge-index`, `challenge-title`, `challenge-description`, `board`, `hall-status`; `data-*` attributes; the verdict classes `ok / bad / warn / running`; `#timer.low`; all form actions, names and CSRF tokens. Run the test suite after changes.

## Fidelity
High-fidelity: final colours, type, spacing, copy. Mockups are 390 px wide (phone) and 1600×900 (hall screen).

## Design Tokens
Font (everything, body included): `ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace`. No web fonts (mobile data).

Colours:
- `--bg` `#0f0e14` · `--panel` `#16141d` · `--code-bg` `#1d1a27`
- `--border` `#2a2735` · `--border-soft` `#221f2c` · `--leader` (dotted) `#3a3649`
- `--fg` `#ecebf2` · `--fg-2` (body copy) `#cfccd9` · `--muted` `#908ba3`
- `--ink` (text on accent) `#0f0e14`
- `--pink` `oklch(0.8 0.15 350)` — brand, prompt `$`, primary buttons, focused inputs, cursor
- `--cyan` `oklch(0.8 0.15 210)` — info, inline code, links, section labels
- `--lime` `oklch(0.8 0.15 135)` — correct / success / place numbers
- `--yellow` `oklch(0.8 0.15 95)` — low time, prize code, #1, STAFF badge, warnings
- `--red` border `oklch(0.68 0.19 25)`, text `oklch(0.72 0.17 25)` — errors, Hide
- Logo gradient: `linear-gradient(90deg, pink, yellow, lime, cyan)` via `background-clip:text; -webkit-text-fill-color:transparent`

Radii: 4 (badges, code), 6 (large badges), 8 (small buttons/inputs), 10 (inputs, buttons, boxes), 12–14 (cards), 18 (hall QR card).
Spacing: 4 / 8 / 12 / 16 / 20 / 24; page padding 18–20 px mobile.
Type: body 15px/1.5; h1 21–24px bold; labels 11–12px uppercase, letter-spacing .08em, muted; inputs ≥16px (iOS zoom).
Buttons: min-height 48 (primary), 44 (row actions); pink bg, ink text, bold, radius 10, no border.
Inputs: bg panel, 1.5px pink border when focused, radius 10, padding 12, `caret-color: pink`.

## Shared components
- **Badge** (lipgloss-style): accent bg, ink text, bold, padding 1px 8px, radius 4.
- **Section rule**: flex row — label (badge or coloured bold text) + `flex:1; border-top:1px solid border`.
- **Key/value with dotted leader**: `label(muted) · flex:1 dotted border-bottom · value(bold)`.
- **Notices**: 1px border + text in the same colour (lime ok / yellow warn / red bad), radius 10, padding 10px 12px, prefixed `✓` / `!` / `✗`.
- **Small header** (play + staff screens): `$` pink + "bash-dash" gradient text, bold; right side a badge (`NN / 38` pink on play, `STAFF` yellow on staff).
- **Full ASCII logo** (gate, home, done, hall): `<pre>` with the logo, bold, line-height 1.12–1.15, gradient text. Mobile font-size ≈ 9.4px so 59 columns fit 350 px; on wider screens scale up (e.g. `font-size: clamp(9px, 2.6vw, 17px)`). Escape `>` as `&gt;`.
- **Blinking block cursor**: inline-block 0.6em × 1.15em, pink, `animation: blink 1.05s steps(1) infinite` (`0–49% opacity 1, 50–100% 0`). Shown as an overlay inside the empty command input (hide when input has a value), and after the static nick/code values.

## Screens
### Play (`play.html`) — priority
Column, gap 16. 1) small header with `challenge-index` as pink badge (zero-padded index "07 / 38" optional). 2) Counters: 3-column grid of boxes (border, radius 10, padding 8×10): label ATTEMPTS/SOLVED/TIME (11px muted), value 20px bold — attempts cyan, solved lime, time fg. `#timer.low` → yellow text + yellow box border. 3) Challenge: h1 21px + description (`fg-2`; `code` cyan on code-bg; `pre` panel box). 4) Command form: flex row — box (panel bg, 1.5px pink border, radius 10) containing `$` pink + input; Run button pink, min-height 48. 5) Verdict line (min-height 28). 6) Output panel: border, radius 10, panel bg; header strip (13px muted, border-bottom) shows `$ <last command>` (this is `#last-command`); `pre#output` padding 12, 13.5px, min-height 96, max-height 50vh.

Verdict states: `running` muted "⣾ Running…"; `bad` red bold "✗ …"; `warn` yellow; `ok` → lime badge "✓ Correct!" (lime bg, ink text, padding 2px 10px, radius 6).

**Correct effect**: on correct answer, restart animations on the verdict badge — `pop` 0.45s ease-out (scale .6→1.08→1, opacity 0→1) + `glow` 0.9s (box-shadow 0 0 0 0 lime/70% → 0 0 0 14px lime/0). Also for 1.1 s set command box border and SOLVED box border to lime (transition 0.3s), then back. In `play.js`: add/remove a `flash` class on the form and counters; restart the verdict animation by removing the class, forcing reflow (`void el.offsetWidth`), re-adding. Respect `prefers-reduced-motion`.

### Hall of fame (`staff/hall.html`, `_board.html`) — 1600×900 at booth
Padding 44/56. Top row: full ASCII logo (17px) left; right muted 22px text "5 minutes · bash only ·" + blinking cursor. Body grid `minmax(0,1fr) 560px`, gap 64.
- Left: section rule with pink badge "HALL OF FAME" (24px). Rows 30px, padding 7×8, border-bottom: place (min-width 76), nick (flex, ellipsis), `solved / total` fg-2, `att.` muted right-aligned min-width 150. Places 4+ in lime. Podium: bold; #1 yellow badge + yellow nick, #2 cyan, #3 pink.
- Right column (gap 40): QR card (panel bg, border, radius 18, padding 24, row gap 32): white QR tile 236×236, padding 12, radius 14, `box-shadow: 0 0 0 3px pink, 0 0 40px pink/35%`; next to it "Scan to play" 32px bold and code 46px bold yellow, letter-spacing .12em. Below: section rule with lime badge "JUST FINISHED"; rows 26px: nick, `solved/total`, att. muted, `#place` lime.
- `.hall-status` badge: keep fixed bottom-right; restyle with panel bg and yellow/red border.
- Keep `@media (max-width: 900px)` stacking to one column.

### Gate (`gate.html`)
Logo, h1 "Scan the QR code at the booth to play", red notice for expired/invalid, help text (fg-2), label CODE, input (22px, letter-spacing .15em), Continue button.

### Home (`home.html`)
Logo, section rule with cyan badge "How to play", rules list with pink `›` markers (no bullets), `ls`/`cat` as cyan code, duration in yellow bold. Label YOUR NICK, input, "Start ▸" button min-height 52 (keep button text "Start" if tests assert it). Error `.error` in red below input.

### Done (`done.html`)
Logo; h1 in yellow ("Time's up!" / "All challenges solved!" / "Finished!"); "Well played, <nick>." Stats box with dotted leaders: Solved (lime), Attempts (cyan), Place (pink). Prize box: 1.5px dashed yellow, radius 14, centred: label PRIZE CODE, code 50px bold yellow `user-select: all`, then the two instruction lines. Muted note at bottom.

### Prize desk (`staff/lookup.html`)
Small header + STAFF badge; h1; nav links cyan 13px separated by `·`. Messages as notices. Lookup row: code input (24px, letter-spacing .15em) + "Look up" button. Card (panel, radius 12, padding 16): nick 30px bold yellow, muted hint, dotted-leader stats (Solved, Attempts, Place, Solve time), "Finished … ago" muted, "Mark prize given" lime button min-height 56, 18px. Already-given → yellow notice. Log out as muted underlined text button.

### Moderation (`staff/moderate.html`)
Same header/nav. Sections with cyan section rules: Start QR (label, 72px number input right-aligned, Save pink button), "0 = never expires" muted; On screen lists: rows `#place` lime, nick ellipsis, `solved/total · att.` 12px muted, Hide button (transparent, red border + red text, min-height 44). Hidden: nick muted + strike-through, Unhide button (transparent, border, fg).

## Responsive
Player screens: `main { max-width: 44rem; margin: 0 auto; }` — works on desktop as a centred column; output max-height 50vh. Scale the logo with `clamp()`.

## Assets
QR is the existing server-rendered `qr_svg`. bash-dash logo is text. Camlin Group logo: `assets/camlin-logo.png` — placement and code in `CAMLIN_LOGO.md` (follow-up change, apply on top of the current repo state).

## Files
- `bash-dash Screens.dc.html` — all 7 screens; Play is interactive (try a command containing sed/awk/head/tail).
