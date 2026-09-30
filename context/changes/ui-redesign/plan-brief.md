# Web UI Redesign — Plan Brief

> Full plan: `context/changes/ui-redesign/plan.md`

## What & Why

Restyle every screen of bash-dash to the terminal-style design in `context/changes/ui-redesign/design_handoff_bash_dash_ui/`: dark background, pink/cyan/lime/yellow accents, ASCII-art logo, and a "correct answer" effect. The goal is a look that fits the hackathon booth and phone use. Behaviour must not change.

## Starting Point

One stylesheet (`game.css`, GitHub-dark palette, sans-serif body), a fixed text header in `base.html`, and templates whose markup is simple. `play.js` sets verdict text/classes but has no effects. The hall board is a polled fragment swapped into `#board`.

## Desired End State

All seven screens (play, gate, home, done, hall, prize desk, moderation) match the mockup at 390px, and the hall at 1600×900. A correct answer shows a pop-and-glow badge and a brief lime flash on the command box and SOLVED counter. The test suite passes.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Scope of edits | `game.css`, templates, correct-effect in `play.js`, plus minimal test assertion updates | Your brief: no ids, behaviour or logic changes. |
| Key/value rows | Restructure markup to label + dotted leader + value | Matches the design; you approved adjusting the 2 affected test assertions. |
| Cursor | Blinking overlay in `#command` and on the hall tagline only | Matches the README spec; avoids clutter on other inputs. |
| Challenge index | Left unpadded in the DOM | `play.js` compares its text to detect a new challenge. |
| Verdict glyphs (✓ ✗ ! ⣾) | Added by CSS `::before` | Verdict text comes from the server and JS and must not change. |
| Timer box border | `:has(#timer.low)` in CSS | Avoids touching timer JS. |
| Verification | Automated tests each phase, visual check by you | Tests can't verify CSS; you judge the look. |

## Scope

**In scope:** `game.css`, `base.html`, new `_logo.html`, all page templates, the correct-answer effect in `play.js`, and the two test assertions tied to the key/value markup.

**Out of scope:** Python code, `hall.js`, ids/`data-*`/form names, web fonts and images, cursor on other inputs, automated screenshot tooling.

## Architecture / Approach

Tokens and shared components (badge, section rule, key/value row, cursor, logo) go into `game.css` first, and `base.html` gets a header block so pages pick the small header or the full logo. Then each screen is converted in priority order. The hall keeps its fragment order and gets its two-column layout from CSS grid on `#board`.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Foundation | Tokens, shared components, base header block, logo include | Global restyle briefly affects unconverted pages |
| 2. Play screen | Full play layout, verdict states, correct-answer effect | Animation restart and cursor overlay details |
| 3. Player pages | Gate, home, done with stats and prize box | Test-pinned markup on done page |
| 4. Hall of fame | Booth layout, podium, QR card, stacking | Polled fragment swap must keep the layout |
| 5. Staff pages | Prize desk and moderation | Test-pinned `Solve time` markup |

**Prerequisites:** none.
**Estimated effort:** ~3–5 sessions across 5 phases.

## Open Risks & Assumptions

- `:has()` and `oklch()` are assumed supported by the phones and the booth browser in use; if not, add fallback colours.
- Gradient logo (`background-clip: text`) renders differently in some browsers; check on the actual booth machine.
- Visual fidelity depends on your manual review at each phase.

## Success Criteria (Summary)

- Every screen looks like the mockup on phone and booth screen.
- Playing a full game, using the staff pages and the hall behaves exactly as before.
- Correct answers show the new effect, and reduced-motion users see no animation.
